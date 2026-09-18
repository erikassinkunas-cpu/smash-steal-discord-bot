"""Persistent message XP and leveling for Smash & Steal."""
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands

from levels_store import (
    DUPLICATE_WINDOW_SECONDS,
    XP_COOLDOWN_SECONDS,
    XP_PER_MESSAGE,
    LevelStore,
    message_fingerprint,
)

LOG = logging.getLogger("sas.levels")
NONE = discord.AllowedMentions.none()

ELIGIBLE_CHANNELS = (
    "general",
    "clips-and-loot",
    "find-a-crew",
    "polls-and-events",
    "tester-chat",
)
MIN_TEXT_LENGTH = 5
BAR_LENGTH = 12


def progress_bar(progress: int, needed: int) -> str:
    if needed <= 0:
        return "█" * BAR_LENGTH
    filled = min(BAR_LENGTH, max(0, int((progress / needed) * BAR_LENGTH)))
    return "█" * filled + "░" * (BAR_LENGTH - filled)


async def respond(interaction, *, content=None, embed=None, ephemeral=True):
    kwargs = {
        "ephemeral": ephemeral,
        "allowed_mentions": NONE,
    }
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed

    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


class LevelsV1:
    def __init__(self, ns):
        self.ns = ns
        self.bot = ns["bot"]
        self.guild_id = ns["GUILD_ID"]
        self.store = None
        self.ready = False
        self.start_lock = asyncio.Lock()
        self.eligible_channel_ids = set()
        self.level_channel_id = None

    async def prepare(self):
        mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
        if os.environ.get("RAILWAY_ENVIRONMENT_ID") and not mount:
            raise RuntimeError("Persistent Railway storage is required for levels.")

        path = Path(mount or os.environ.get("LEVELS_DATA_DIR", "data")) / "levels.sqlite3"
        self.store = LevelStore(path)
        await asyncio.to_thread(self.store.initialise)
        LOG.info("LEVEL STORAGE path=%s persistent=%s", path, bool(mount))

    def refresh_channels(self, guild):
        self.eligible_channel_ids = {
            channel.id
            for key in ELIGIBLE_CHANNELS
            if (channel := self.ns["find_text"](guild, key))
        }
        level_channel = self.ns["find_text"](guild, "levels")
        self.level_channel_id = level_channel.id if level_channel else None
        return level_channel

    async def upsert_panel(self, channel):
        marker = "## ⭐ Smash & Steal Levels"
        content = (
            f"{marker}\n"
            f"Earn **{XP_PER_MESSAGE} XP** for normal activity, at most once every "
            f"**{XP_COOLDOWN_SECONDS} seconds**.\n\n"
            "XP channels: 💬 general, 💰 clips-and-loot, 🤝 find-a-crew, "
            "🎉 polls-and-events and 🧪 tester-chat.\n"
            f"Messages need at least **{MIN_TEXT_LENGTH} characters**, unless they contain an attachment. "
            f"Repeating the same message within **{DUPLICATE_WINDOW_SECONDS // 60} minutes** gives no XP.\n"
            "Deleted, blocked, bot and ticket messages do not earn XP.\n\n"
            "Use **/rank** to see your progress and **/leaderboard** for the server top 10."
        )

        existing = None
        try:
            async for message in channel.history(limit=50):
                if message.author == channel.guild.me and message.content.startswith(marker):
                    existing = message
                    break
        except discord.HTTPException:
            pass

        if existing:
            await existing.edit(content=content, allowed_mentions=NONE)
            message = existing
        else:
            message = await channel.send(content, allowed_mentions=NONE)

        try:
            if not message.pinned:
                await message.pin(reason="Smash & Steal level system info")
        except discord.HTTPException:
            pass

    async def start(self):
        async with self.start_lock:
            if self.ready:
                return

            guild = self.bot.get_guild(self.guild_id)
            if guild is None:
                raise RuntimeError("Level system guild is unavailable.")

            level_channel = self.refresh_channels(guild)
            if level_channel is None:
                raise RuntimeError("The levels channel is missing.")

            await self.upsert_panel(level_channel)
            stats = await asyncio.to_thread(self.store.stats, self.guild_id)
            self.ready = True
            LOG.info(
                "LEVELS READY channel=%s xp=%s cooldown=%ss participants=%s integrity=%s",
                level_channel.id,
                XP_PER_MESSAGE,
                XP_COOLDOWN_SECONDS,
                stats["members"],
                stats["integrity"],
            )

    def can_earn(self, member: discord.Member) -> bool:
        if member.bot or member.pending:
            return False
        if self.ns["is_staff"](member):
            return True
        role = self.ns["find_role"](member.guild, "Member")
        return bool(role and role in member.roles)

    async def announce_level(self, member: discord.Member, result):
        channel = self.bot.get_channel(self.level_channel_id) if self.level_channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return

        bar = progress_bar(result["progress"], result["needed"])
        embed = discord.Embed(
            title="🎉 Level Up!",
            description=f"{member.mention} reached **Level {result['level']}**!",
            colour=discord.Colour(0xFEE75C),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Next level",
            value=f"{bar}\n{result['progress']} / {result['needed']} XP",
            inline=False,
        )
        embed.set_footer(text=f"Total XP: {result['total_xp']}")

        try:
            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=False,
                    replied_user=False,
                ),
            )
        except discord.HTTPException:
            LOG.warning("LEVEL ANNOUNCEMENT FAILED user=%s", member.id)

    async def on_message(self, message: discord.Message):
        if (
            not self.ready
            or message.guild is None
            or message.guild.id != self.guild_id
            or message.author.bot
            or message.webhook_id
            or not isinstance(message.author, discord.Member)
            or message.channel.id not in self.eligible_channel_ids
            or not self.can_earn(message.author)
        ):
            return

        clean = " ".join((message.content or "").split())
        attachment_names = [attachment.filename for attachment in message.attachments]

        if len(clean) < MIN_TEXT_LENGTH and not attachment_names:
            return

        fingerprint = message_fingerprint(clean, attachment_names)
        result = await asyncio.to_thread(
            self.store.award,
            self.guild_id,
            message.author.id,
            fingerprint,
        )
        if not result:
            return

        if result["leveled_up"]:
            await self.announce_level(message.author, result)

    async def rank(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ):
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await respond(interaction, content="Use this command in the Smash & Steal server.")
            return

        target = member or interaction.user
        if not isinstance(target, discord.Member) or target.bot:
            await respond(interaction, content="That account does not have a player rank.")
            return

        data = await asyncio.to_thread(self.store.get, self.guild_id, target.id)
        bar = progress_bar(data["progress"], data["needed"])
        embed = discord.Embed(
            title=f"⭐ {target.display_name}'s Rank",
            colour=discord.Colour(0x5865F2),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Server rank", value=f"#{data['rank']}", inline=True)
        embed.add_field(name="Level", value=str(data["level"]), inline=True)
        embed.add_field(name="Total XP", value=f"{data['total_xp']:,}", inline=True)
        embed.add_field(
            name="Progress",
            value=f"{bar}\n**{data['progress']:,} / {data['needed']:,} XP**",
            inline=False,
        )
        await respond(interaction, embed=embed, ephemeral=True)

    async def leaderboard(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await respond(interaction, content="Use this command in the Smash & Steal server.")
            return

        rows = await asyncio.to_thread(self.store.leaderboard, self.guild_id, 10)
        if not rows:
            await respond(
                interaction,
                content="No XP has been earned yet. Start chatting in the community channels.",
                ephemeral=True,
            )
            return

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for row in rows:
            icon = medals.get(row["rank"], f"#{row['rank']}")
            member = interaction.guild.get_member(int(row["user_id"]))
            name = discord.utils.escape_markdown(member.display_name) if member else f"User {row['user_id']}"
            lines.append(
                f"{icon} **{name}** · Level **{row['level']}** · **{row['total_xp']:,} XP**"
            )

        embed = discord.Embed(
            title="🏆 Smash & Steal Leaderboard",
            description="\n".join(lines),
            colour=discord.Colour(0xF1C40F),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Top 10 by total XP")
        await respond(interaction, embed=embed, ephemeral=False)

    async def level_status(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not self.ns["is_staff"](interaction.user):
            await respond(interaction, content="Only the server team can view level system status.")
            return

        stats = await asyncio.to_thread(self.store.stats, self.guild_id)
        await respond(
            interaction,
            content=(
                "## ⭐ Level System\n"
                f"XP per eligible message: **{XP_PER_MESSAGE}**\n"
                f"Cooldown: **{XP_COOLDOWN_SECONDS}s**\n"
                f"Duplicate window: **{DUPLICATE_WINDOW_SECONDS // 60} min**\n"
                f"Participants: **{stats['members']}**\n"
                f"Total XP earned: **{stats['total_xp']:,}**\n"
                f"Database: **{stats['integrity']}**"
            ),
        )

    async def adjust_xp(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: int,
        reason: str,
        sign: int,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        actor = interaction.user
        if not isinstance(actor, discord.Member) or not self.ns["is_staff"](actor):
            await respond(interaction, content="Only the server team can adjust XP.")
            return
        if member.bot:
            await respond(interaction, content="Bots do not participate in levels.")
            return

        reason = (reason or "").strip()
        if not 3 <= len(reason) <= 300:
            await respond(interaction, content="Give a reason between 3 and 300 characters.")
            return

        delta = int(amount) * int(sign)
        data = await asyncio.to_thread(
            self.store.adjust,
            self.guild_id,
            member.id,
            delta,
        )
        action = "added to" if sign > 0 else "removed from"
        actual_change = data["total_xp"] - data["before_total"]

        await self.ns["send_mod_log"](
            interaction.guild,
            "⭐ XP adjusted",
            f"{actor.mention} adjusted XP for {member.mention}.",
            colour=0x5865F2,
            fields=[
                ("Change", f"{actual_change:+,} XP", True),
                ("New total", f"{data['total_xp']:,} XP", True),
                ("Level", data["level"], True),
                ("Reason", discord.utils.escape_mentions(reason), False),
            ],
        )
        await respond(
            interaction,
            content=(
                f"✅ **{abs(actual_change):,} XP** {action} **{member}**. "
                f"New total: **{data['total_xp']:,} XP**, Level **{data['level']}**."
            ),
        )

    async def xp_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 100000],
        reason: str,
    ):
        await self.adjust_xp(interaction, member, int(amount), reason, 1)

    async def xp_remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 100000],
        reason: str,
    ):
        await self.adjust_xp(interaction, member, int(amount), reason, -1)


def install_levels(ns):
    """Install levels before AutoMod wraps on_message, so blocked spam earns no XP."""
    if "_levels_v1" in ns:
        return ns["_levels_v1"]

    required = (
        "bot",
        "GUILD_ID",
        "find_role",
        "find_text",
        "is_staff",
        "send_mod_log",
    )
    if any(name not in ns for name in required):
        raise RuntimeError("The base bot is missing a required level integration hook.")

    if not LOG.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False

    controller = LevelsV1(ns)
    bot = ns["bot"]
    guild = discord.Object(id=ns["GUILD_ID"])

    specs = [
        ("rank", "Show your level, XP and server rank", controller.rank, False),
        ("leaderboard", "Show the top 10 members by XP", controller.leaderboard, False),
        ("level-status", "Show level system health and XP totals", controller.level_status, True),
        ("xp-add", "Add XP to a member", controller.xp_add, True),
        ("xp-remove", "Remove XP from a member", controller.xp_remove, True),
    ]
    for name, description, callback, staff_only in specs:
        command = app_commands.Command(
            name=name,
            description=description,
            callback=callback,
        )
        if staff_only:
            command.default_permissions = discord.Permissions(manage_messages=True)
        bot.tree.add_command(command, guild=guild)

    original_setup = bot.setup_hook
    original_ready = getattr(bot, "on_ready", None)
    original_message = getattr(bot, "on_message", None)

    async def setup_hook():
        await controller.prepare()
        await original_setup()

    bot.setup_hook = setup_hook

    @bot.event
    async def on_ready():
        if original_ready:
            await original_ready()
        try:
            await controller.start()
        except Exception:
            LOG.exception("LEVELS START FAILED")

    @bot.event
    async def on_message(message):
        if original_message:
            await original_message(message)
        try:
            await controller.on_message(message)
        except Exception:
            LOG.exception("LEVEL XP FAILED message=%s", getattr(message, "id", None))

    ns["_levels_v1"] = controller
    return controller
