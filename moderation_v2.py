"""AutoMod + persistent warning system for Smash & Steal."""
import asyncio
import logging
import os
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands

from moderation_store import ModerationError, ModerationStore

LOG = logging.getLogger("sas.moderation")
NONE = discord.AllowedMentions.none()

FLOOD_COUNT = 6
FLOOD_WINDOW = 8
MASS_MENTION_LIMIT = 5
NEW_ACCOUNT_HOURS = 72
INVITE_WINDOW = 60
INVITE_WINDOW_LIMIT = 3
ACTION_COOLDOWN = 20

URL_RE = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite|discord\.gg)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)
SUSPICIOUS_PHRASES = (
    "free nitro",
    "free robux",
    "steam gift",
    "discord gift",
    "claim reward",
    "claim your reward",
    "verify your account",
    "verify account",
    "wallet connect",
    "connect wallet",
    "airdrop",
)


def timeout_minutes(active_warnings: int) -> int:
    if active_warnings >= 7:
        return 24 * 60
    if active_warnings >= 5:
        return 60
    if active_warnings >= 3:
        return 10
    return 0


def classify_message(
    content: str,
    *,
    mention_total: int = 0,
    mention_everyone: bool = False,
    account_age_hours: float = 999999,
    invite_recent: int = 0,
    flood_count: int = 0,
):
    text = content or ""
    lowered = text.casefold()
    invites = INVITE_RE.findall(text)
    has_url = bool(URL_RE.search(text) or invites)

    if mention_everyone or mention_total >= MASS_MENTION_LIMIT:
        return (
            "mass-mention",
            f"Mass mention spam ({MASS_MENTION_LIMIT}+ mentions or @everyone/@here).",
        )

    if account_age_hours < NEW_ACCOUNT_HOURS and has_url:
        return (
            "new-account-link",
            "A link was posted by an account newer than 3 days.",
        )

    if has_url and any(phrase in lowered for phrase in SUSPICIOUS_PHRASES):
        return (
            "scam-link",
            "Suspicious scam or phishing-style link.",
        )

    if len(invites) >= 2 or invite_recent >= INVITE_WINDOW_LIMIT:
        return (
            "invite-spam",
            "Discord invite spam.",
        )

    if flood_count >= FLOOD_COUNT:
        return (
            "flood",
            f"Message flood ({FLOOD_COUNT}+ messages in {FLOOD_WINDOW} seconds).",
        )

    return None


async def respond(interaction: discord.Interaction, text: str):
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True, allowed_mentions=NONE)
    else:
        await interaction.response.send_message(text, ephemeral=True, allowed_mentions=NONE)


class ModerationV2:
    def __init__(self, ns):
        self.ns = ns
        self.bot = ns["bot"]
        self.guild_id = ns["GUILD_ID"]
        self.store = None
        self.ready = False
        self.start_lock = asyncio.Lock()
        self.message_windows = defaultdict(deque)
        self.invite_windows = defaultdict(deque)
        self.last_actions = {}

    async def prepare(self):
        mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
        if os.environ.get("RAILWAY_ENVIRONMENT_ID") and not mount:
            raise RuntimeError("Persistent Railway storage is required for warnings.")
        path = Path(mount or os.environ.get("MODERATION_DATA_DIR", "data")) / "moderation.sqlite3"
        self.store = ModerationStore(path)
        await asyncio.to_thread(self.store.initialise)
        stats = await asyncio.to_thread(self.store.stats)
        LOG.info(
            "MODERATION STORAGE path=%s persistent=%s stats=%s",
            path,
            bool(mount),
            stats,
        )

    async def start(self):
        async with self.start_lock:
            if self.ready:
                return
            self.ready = True
            stats = await asyncio.to_thread(self.store.stats)
            LOG.info(
                "AUTOMOD READY flood=%s/%ss mentions=%s new_account=%sh "
                "invite=%s/%ss warnings=%s integrity=%s",
                FLOOD_COUNT,
                FLOOD_WINDOW,
                MASS_MENTION_LIMIT,
                NEW_ACCOUNT_HOURS,
                INVITE_WINDOW_LIMIT,
                INVITE_WINDOW,
                stats["active_warnings"],
                stats["integrity"],
            )

    def is_staff(self, member):
        return bool(isinstance(member, discord.Member) and self.ns["is_staff"](member))

    def target_allowed(self, actor: discord.Member, target: discord.Member):
        checker = self.ns.get("actor_can_target")
        if checker:
            return checker(actor, target)
        if actor.id == target.id:
            return False, "You cannot moderate yourself."
        if target.id == actor.guild.owner_id:
            return False, "The server owner cannot be moderated."
        if actor.id != actor.guild.owner_id and target.top_role >= actor.top_role:
            return False, "That member is above or equal to your highest role."
        me = actor.guild.me
        if me and target.top_role >= me.top_role:
            return False, "That member is above or equal to the bot role."
        return True, None

    async def issue_warning(
        self,
        member: discord.Member,
        moderator_id: int,
        reason: str,
        source: str,
    ):
        warning, count = await asyncio.to_thread(
            self.store.add_warning,
            member.guild.id,
            member.id,
            moderator_id,
            reason,
            source,
        )

        minutes = timeout_minutes(count)
        timeout_result = "No automatic timeout."
        if minutes:
            me = member.guild.me
            if (
                me
                and me.guild_permissions.moderate_members
                and member.id != member.guild.owner_id
                and member.top_role < me.top_role
            ):
                try:
                    desired_until = discord.utils.utcnow() + timedelta(minutes=minutes)
                    current_until = member.timed_out_until
                    if not current_until or current_until < desired_until:
                        await member.timeout(
                            timedelta(minutes=minutes),
                            reason=f"{source}: {count} active warnings",
                        )
                    timeout_result = f"Automatic timeout: {minutes} minutes."
                except discord.HTTPException:
                    timeout_result = "Automatic timeout failed because of Discord permissions/API."
            else:
                timeout_result = "Automatic timeout could not be applied because of role hierarchy/permissions."

        try:
            await member.send(
                f"⚠️ **Smash & Steal warning #{warning['id']}**\n"
                f"Reason: {reason}\n"
                f"Active warnings: {count}\n"
                f"{timeout_result}",
                allowed_mentions=NONE,
            )
        except discord.HTTPException:
            pass

        await self.ns["send_mod_log"](
            member.guild,
            "⚠️ Warning issued",
            f"{member.mention} received warning **#{warning['id']}**.",
            colour=0xFEE75C,
            fields=[
                ("Source", source, True),
                ("Active warnings", count, True),
                ("Reason", reason, False),
                ("Escalation", timeout_result, False),
                ("Moderator", f"<@{moderator_id}> ({moderator_id})", False),
            ],
        )

        return warning, count, minutes

    async def block_message(self, message: discord.Message, source: str, reason: str):
        try:
            await message.delete(reason=f"AutoMod: {source}")
        except discord.HTTPException:
            pass

        now = time.monotonic()
        key = (message.author.id, source)
        if now - self.last_actions.get(key, 0) < ACTION_COOLDOWN:
            return True
        self.last_actions[key] = now

        if source == "flood":
            self.message_windows[message.author.id].clear()
        if source == "invite-spam":
            self.invite_windows[message.author.id].clear()

        try:
            await self.issue_warning(
                message.author,
                self.bot.user.id if self.bot.user else 0,
                reason,
                source,
            )
        except Exception:
            LOG.exception("AUTOMOD WARNING FAILED user=%s source=%s", message.author.id, source)

        return True

    async def on_message(self, message: discord.Message):
        if (
            not self.ready
            or message.guild is None
            or message.guild.id != self.guild_id
            or message.author.bot
            or message.webhook_id
            or not isinstance(message.author, discord.Member)
        ):
            return False

        if self.is_staff(message.author):
            return False

        category_name = getattr(getattr(message.channel, "category", None), "name", "")
        if category_name in {"🎫 TICKETS", "🔒 TEAM"}:
            return False

        now = time.monotonic()
        user_id = message.author.id

        message_window = self.message_windows[user_id]
        message_window.append(now)
        while message_window and now - message_window[0] > FLOOD_WINDOW:
            message_window.popleft()

        invites = INVITE_RE.findall(message.content or "")
        invite_window = self.invite_windows[user_id]
        if invites:
            invite_window.append(now)
        while invite_window and now - invite_window[0] > INVITE_WINDOW:
            invite_window.popleft()

        mention_ids = {member.id for member in message.mentions}
        mention_ids.update(role.id for role in message.role_mentions)
        age_hours = (
            discord.utils.utcnow() - message.author.created_at
        ).total_seconds() / 3600

        violation = classify_message(
            message.content,
            mention_total=len(mention_ids),
            mention_everyone=message.mention_everyone,
            account_age_hours=age_hours,
            invite_recent=len(invite_window),
            flood_count=len(message_window),
        )
        if violation:
            source, reason = violation
            return await self.block_message(message, source, reason)
        return False

    async def on_member_join(self, member: discord.Member):
        if (
            not self.ready
            or member.guild.id != self.guild_id
            or member.bot
        ):
            return
        age_hours = (discord.utils.utcnow() - member.created_at).total_seconds() / 3600
        if age_hours >= NEW_ACCOUNT_HOURS:
            return
        await self.ns["send_mod_log"](
            member.guild,
            "🆕 New account joined",
            f"{member.mention} joined with an account newer than 3 days.",
            colour=0xFEE75C,
            fields=[
                ("Account age", f"{age_hours:.1f} hours", True),
                ("User ID", member.id, True),
            ],
        )

    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        actor = interaction.user
        if not isinstance(actor, discord.Member) or not self.is_staff(actor):
            await respond(interaction, "Only the server team can issue warnings.")
            return
        allowed, error = self.target_allowed(actor, member)
        if not allowed:
            await respond(interaction, error)
            return
        try:
            warning, count, minutes = await self.issue_warning(
                member,
                actor.id,
                reason,
                "manual",
            )
            suffix = f" Auto timeout: **{minutes} min**." if minutes else ""
            await respond(
                interaction,
                f"⚠️ Warning **#{warning['id']}** added to **{member}**. "
                f"Active warnings: **{count}**.{suffix}",
            )
        except ModerationError as exc:
            await respond(interaction, str(exc))
        except Exception:
            LOG.exception("MANUAL WARN FAILED")
            await respond(interaction, "The warning could not be saved.")

    async def warnings(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ):
        actor = interaction.user
        if not isinstance(actor, discord.Member) or interaction.guild is None:
            await respond(interaction, "Use this command in the server.")
            return

        target = member or actor
        if target.id != actor.id and not self.is_staff(actor):
            await respond(interaction, "You can only view your own warnings.")
            return

        rows = await asyncio.to_thread(
            self.store.list_warnings,
            interaction.guild.id,
            target.id,
            True,
            10,
        )
        if not rows:
            await respond(interaction, f"✅ **{target}** has no active warnings.")
            return

        lines = []
        for row in rows:
            timestamp = int(row["created"])
            lines.append(
                f"**#{row['id']}** · {row['source']} · <t:{timestamp}:R>\n"
                f"{discord.utils.escape_mentions(row['reason'])}"
            )
        count = await asyncio.to_thread(
            self.store.active_count,
            interaction.guild.id,
            target.id,
        )
        await respond(
            interaction,
            f"## ⚠️ Warnings for {target}\nActive: **{count}**\n\n"
            + "\n\n".join(lines),
        )

    async def clearwarn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        warning_id: Optional[int] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        actor = interaction.user
        if not isinstance(actor, discord.Member) or not self.is_staff(actor):
            await respond(interaction, "Only the server team can clear warnings.")
            return

        if warning_id is None:
            cleared = await asyncio.to_thread(
                self.store.clear_all,
                interaction.guild.id,
                member.id,
                actor.id,
            )
            await respond(
                interaction,
                f"✅ Cleared **{cleared}** active warning(s) from **{member}**.",
            )
            detail = f"All active warnings cleared ({cleared})."
        else:
            cleared = await asyncio.to_thread(
                self.store.clear_warning,
                interaction.guild.id,
                member.id,
                warning_id,
                actor.id,
            )
            if not cleared:
                await respond(
                    interaction,
                    f"Warning **#{warning_id}** is not an active warning for **{member}**.",
                )
                return
            await respond(
                interaction,
                f"✅ Cleared warning **#{warning_id}** from **{member}**.",
            )
            detail = f"Warning #{warning_id} cleared."

        await self.ns["send_mod_log"](
            interaction.guild,
            "✅ Warning cleared",
            f"{actor.mention} changed warnings for {member.mention}.",
            colour=0x57F287,
            fields=[("Action", detail, False)],
        )

    async def automod_status(self, interaction: discord.Interaction):
        actor = interaction.user
        if not isinstance(actor, discord.Member) or not self.is_staff(actor):
            await respond(interaction, "Only the server team can view AutoMod status.")
            return
        stats = await asyncio.to_thread(self.store.stats)
        await respond(
            interaction,
            "## 🛡️ AutoMod V2\n"
            f"Flood: **{FLOOD_COUNT} messages / {FLOOD_WINDOW}s**\n"
            f"Mass mentions: **{MASS_MENTION_LIMIT}+**\n"
            f"New-account link protection: **{NEW_ACCOUNT_HOURS // 24} days**\n"
            f"Invite spam: **{INVITE_WINDOW_LIMIT} posts / {INVITE_WINDOW}s**\n"
            "Escalation: **3 warns = 10m, 5 = 1h, 7 = 24h**\n\n"
            f"Active warnings: **{stats['active_warnings']}**\n"
            f"Members with warnings: **{stats['members_with_warnings']}**\n"
            f"Database: **{stats['integrity']}**",
        )


def install_moderation(ns):
    """Install AutoMod after Community V2 while preserving legacy callbacks."""
    if "_moderation_v2" in ns:
        return ns["_moderation_v2"]

    required = (
        "bot",
        "GUILD_ID",
        "is_staff",
        "send_mod_log",
    )
    if any(name not in ns for name in required):
        raise RuntimeError("The base bot is missing a required moderation integration hook.")

    if not LOG.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False

    controller = ModerationV2(ns)
    bot = ns["bot"]
    guild = discord.Object(id=ns["GUILD_ID"])

    specs = [
        ("warn", "Issue a persistent warning to a member", controller.warn, True),
        ("warnings", "View active warnings", controller.warnings, False),
        ("clearwarn", "Clear one warning, or all active warnings", controller.clearwarn, True),
        ("automod-status", "Show AutoMod rules and warning storage status", controller.automod_status, True),
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
    original_join = getattr(bot, "on_member_join", None)

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
            LOG.exception("AUTOMOD START FAILED")

    @bot.event
    async def on_message(message):
        try:
            blocked = await controller.on_message(message)
        except Exception:
            LOG.exception("AUTOMOD MESSAGE CHECK FAILED message=%s", getattr(message, "id", None))
            blocked = False
        if not blocked and original_message:
            await original_message(message)

    @bot.event
    async def on_member_join(member):
        if original_join:
            await original_join(member)
        try:
            await controller.on_member_join(member)
        except Exception:
            LOG.exception("AUTOMOD JOIN CHECK FAILED member=%s", getattr(member, "id", None))

    ns["_moderation_v2"] = controller
    return controller
