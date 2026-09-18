import os
import re
import asyncio
from typing import Optional

import discord
from discord import app_commands

TOKEN = os.environ.get("DISCORD_TOKEN")
GUILD_ID_RAW = os.environ.get("GUILD_ID")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing")
if not GUILD_ID_RAW or not GUILD_ID_RAW.isdigit():
    raise RuntimeError("GUILD_ID is missing or invalid")
GUILD_ID = int(GUILD_ID_RAW)

intents = discord.Intents.default()
intents.guilds = True

ROLE_DEFS = {
    "Founder": True,
    "Developer": True,
    "Community Manager": True,
    "Moderator": True,
    "Helper": True,
    "Tester": False,
    "Early Crew": False,
    "Bug Hunter": False,
    "Content Creator": False,
    "Contributor": False,
    "Member": False,
    "Update Ping": False,
    "Playtest Ping": False,
    "Event Ping": False,
    "Sneak Peek Ping": False,
    "PC": False,
    "Mobile": False,
    "Console": False,
}

SELF_ROLES = [
    ("Update Ping", "📢"),
    ("Playtest Ping", "🧪"),
    ("Event Ping", "🎉"),
    ("Sneak Peek Ping", "👀"),
    ("PC", "🖥️"),
    ("Mobile", "📱"),
    ("Console", "🎮"),
]

STAFF_ROLE_NAMES = {"Founder", "Developer", "Community Manager", "Moderator"}


def safe_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower().strip()).strip("-")
    return value[:50] or "member"


def find_role(guild: discord.Guild, name: str) -> Optional[discord.Role]:
    return discord.utils.get(guild.roles, name=name)


def find_text(guild: discord.Guild, name: str) -> Optional[discord.TextChannel]:
    return discord.utils.get(guild.text_channels, name=name)


def find_category(guild: discord.Guild, name: str) -> Optional[discord.CategoryChannel]:
    return discord.utils.get(guild.categories, name=name)


def is_staff(member: discord.Member) -> bool:
    return (
        member.guild.owner_id == member.id
        or member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
        or any(role.name in STAFF_ROLE_NAMES for role in member.roles)
    )


class RoleToggleButton(discord.ui.Button):
    def __init__(self, role_name: str, emoji: str, row: int):
        super().__init__(
            label=role_name,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"sas:role:{role_name}",
            row=row,
        )
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This button only works in the server.", ephemeral=True)
            return
        role = find_role(interaction.guild, self.role_name)
        if not role:
            await interaction.response.send_message("That role is missing. Staff should run /setup.", ephemeral=True)
            return
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Self role toggle")
                msg = f"Removed **{role.name}**."
            else:
                await interaction.user.add_roles(role, reason="Self role toggle")
                msg = f"Added **{role.name}**."
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I cannot manage that role. Move my bot role above it and enable Manage Roles.",
                ephemeral=True,
            )


class RolePickerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for index, (role_name, emoji) in enumerate(SELF_ROLES):
            self.add_item(RoleToggleButton(role_name, emoji, index // 4))


class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Get Member",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="sas:verify:member",
    )
    async def get_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This button only works in the server.", ephemeral=True)
            return
        member = interaction.user
        if getattr(member, "pending", False):
            await interaction.response.send_message(
                "Accept the server rules first, then press this button again.",
                ephemeral=True,
            )
            return
        role = find_role(interaction.guild, "Member")
        if not role:
            await interaction.response.send_message("Member role is missing. Staff should run /setup.", ephemeral=True)
            return
        if role in member.roles:
            await interaction.response.send_message("You already have the Member role.", ephemeral=True)
            return
        try:
            await member.add_roles(role, reason="Member verification")
            await interaction.response.send_message(
                "✅ Verified. You now have the **Member** role.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I cannot assign Member. Move my bot role above Member and enable Manage Roles.",
                ephemeral=True,
            )


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="sas:ticket:close",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
            return
        owner_match = re.search(r"ticket-owner:(\d+)", interaction.channel.topic or "")
        is_owner = bool(owner_match and int(owner_match.group(1)) == interaction.user.id)
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not is_owner and not (member and is_staff(member)):
            await interaction.response.send_message(
                "Only the ticket owner or staff can close this ticket.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Closing ticket in 3 seconds...", ephemeral=True)
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            pass


class TicketButton(discord.ui.Button):
    def __init__(self, label: str, emoji: str, ticket_type: str, style: discord.ButtonStyle):
        super().__init__(
            label=label,
            emoji=emoji,
            style=style,
            custom_id=f"sas:ticket:{ticket_type}",
        )
        self.ticket_type = ticket_type

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This button only works in the server.", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user
        marker = f"ticket-owner:{user.id}"

        for channel in guild.text_channels:
            if channel.topic and marker in channel.topic:
                await interaction.response.send_message(
                    f"You already have an open ticket: {channel.mention}",
                    ephemeral=True,
                )
                return

        category = find_category(guild, "🎫 TICKETS")
        if not category:
            category = await guild.create_category(
                "🎫 TICKETS",
                overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                reason="Ticket system setup",
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
            ),
        }

        staff_names = {"Founder", "Developer", "Community Manager", "Moderator"}
        if self.ticket_type == "help":
            staff_names.add("Helper")
        for role_name in staff_names:
            role = find_role(guild, role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

        try:
            channel = await guild.create_text_channel(
                f"{self.ticket_type}-{safe_name(user.display_name)}",
                category=category,
                topic=f"ticket-owner:{user.id} | type:{self.ticket_type}",
                overwrites=overwrites,
                reason=f"Ticket opened by {user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I cannot create ticket channels. Enable Manage Channels.",
                ephemeral=True,
            )
            return

        instructions = {
            "help": "Describe what you need help with. Add screenshots if useful.",
            "player": "Explain what happened, who was involved, and add evidence if you have it.",
            "exploit": "Describe the exploit privately. Do not post exploit steps in public channels.",
        }
        await channel.send(
            f"{user.mention} **{self.ticket_type.upper()} ticket**\n{instructions[self.ticket_type]}",
            view=CloseTicketView(),
        )
        await interaction.response.send_message(
            f"Ticket created: {channel.mention}",
            ephemeral=True,
        )


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketButton("Game Help", "🎮", "help", discord.ButtonStyle.primary))
        self.add_item(TicketButton("Report Player", "🚩", "player", discord.ButtonStyle.secondary))
        self.add_item(TicketButton("Report Exploit", "🔐", "exploit", discord.ButtonStyle.danger))


class SmashStealBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(VerifyView())
        self.add_view(RolePickerView())
        self.add_view(TicketView())
        self.add_view(CloseTicketView())
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))


bot = SmashStealBot()
GUILD = discord.Object(id=GUILD_ID)


async def ensure_role(guild: discord.Guild, name: str, hoist: bool = False):
    existing = find_role(guild, name)
    if existing:
        return existing
    return await guild.create_role(name=name, hoist=hoist, reason="Smash & Steal setup")


async def ensure_category(guild: discord.Guild, name: str, overwrites=None):
    existing = find_category(guild, name)
    if existing:
        return existing
    return await guild.create_category(name, overwrites=overwrites, reason="Smash & Steal setup")


async def ensure_text(guild, category, name, read_only=False, member_only=False):
    existing = find_text(guild, name)
    if existing:
        return existing

    overwrites = {}
    if read_only:
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
        )
    elif member_only:
        member_role = find_role(guild, "Member")
        overwrites[guild.default_role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
        )
        if member_role:
            overwrites[member_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )

    return await guild.create_text_channel(
        name,
        category=category,
        overwrites=overwrites,
        reason="Smash & Steal setup",
    )


async def ensure_voice(guild, category, name):
    existing = discord.utils.get(guild.voice_channels, name=name)
    if existing:
        return existing
    return await guild.create_voice_channel(name, category=category, reason="Smash & Steal setup")


def staff_overwrites(guild):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False)
    }
    for role_name in STAFF_ROLE_NAMES:
        role = find_role(guild, role_name)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            read_message_history=True,
        )
    return overwrites


async def setup_server(guild: discord.Guild):
    created = []

    for name, hoist in ROLE_DEFS.items():
        if not find_role(guild, name):
            await ensure_role(guild, name, hoist)
            created.append(f"role:{name}")

    start = await ensure_category(guild, "🚪 START HERE")
    updates = await ensure_category(guild, "📢 GAME UPDATES")
    community = await ensure_category(guild, "🏙️ COMMUNITY")
    support = await ensure_category(guild, "🛟 SUPPORT")
    playtest = await ensure_category(guild, "🧪 PLAYTEST")
    team = await ensure_category(guild, "🔒 TEAM", overwrites=staff_overwrites(guild))

    channel_defs = [
        (start, "start-here", True, False),
        (start, "rules", True, False),
        (start, "verify", True, False),
        (start, "choose-roles", True, False),
        (updates, "announcements", True, False),
        (updates, "sneak-peeks", True, False),
        (updates, "update-log", True, False),
        (community, "general", False, True),
        (community, "clips-and-loot", False, True),
        (community, "find-a-crew", False, True),
        (community, "polls-and-events", False, True),
        (community, "hall-of-fame", True, False),
        (support, "help-and-faq", True, False),
        (support, "open-ticket", True, False),
        (support, "bug-reports", False, True),
        (support, "suggestions", False, True),
        (playtest, "test-info", True, False),
        (playtest, "tester-chat", False, False),
        (playtest, "known-issues", True, False),
        (team, "staff-chat", False, False),
        (team, "mod-alerts", False, False),
        (team, "bot-logs", False, False),
    ]

    for category, name, read_only, member_only in channel_defs:
        if not find_text(guild, name):
            await ensure_text(guild, category, name, read_only, member_only)
            created.append(f"channel:{name}")

    for category, name in [
        (community, "Hangout"),
        (community, "Crew Room"),
        (playtest, "Playtest Room"),
        (team, "Team Room"),
    ]:
        if not discord.utils.get(guild.voice_channels, name=name):
            await ensure_voice(guild, category, name)
            created.append(f"voice:{name}")

    if not find_category(guild, "🎫 TICKETS"):
        await guild.create_category(
            "🎫 TICKETS",
            overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
            reason="Ticket system setup",
        )
        created.append("category:TICKETS")

    tester = find_role(guild, "Tester")
    tester_chat = find_text(guild, "tester-chat")
    if tester and tester_chat:
        await tester_chat.set_permissions(guild.default_role, view_channel=False)
        await tester_chat.set_permissions(
            tester,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        )

    playtest_room = discord.utils.get(guild.voice_channels, name="Playtest Room")
    if tester and playtest_room:
        await playtest_room.set_permissions(guild.default_role, view_channel=False)
        await playtest_room.set_permissions(
            tester,
            view_channel=True,
            connect=True,
            speak=True,
        )

    return created


async def post_panels(guild: discord.Guild):
    verify = find_text(guild, "verify")
    choose_roles = find_text(guild, "choose-roles")
    tickets = find_text(guild, "open-ticket")
    if not verify or not choose_roles or not tickets:
        raise RuntimeError("Required channels are missing. Run /setup first.")

    await verify.send(
        "## ✅ Verify\nAccept the server rules first. Then press **Get Member** to unlock Member access.",
        view=VerifyView(),
    )
    await choose_roles.send(
        "## 🎭 Choose your roles\nToggle the notifications and platforms you want. These roles do not grant staff access.",
        view=RolePickerView(),
    )
    await tickets.send(
        "## 🎫 Support\nChoose the ticket type you need. Player reports and exploit reports stay private.",
        view=TicketView(),
    )


@bot.tree.command(
    name="setup",
    description="Create or update the Smash & Steal server structure",
    guild=GUILD,
)
async def setup_cmd(interaction: discord.Interaction):
    if (
        not interaction.guild
        or not isinstance(interaction.user, discord.Member)
        or not is_staff(interaction.user)
    ):
        await interaction.response.send_message(
            "Only the server owner or staff can run this command.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        created = await setup_server(interaction.guild)
        summary = (
            "Nothing new was needed."
            if not created
            else f"Created {len(created)} missing server items."
        )
        await interaction.followup.send(
            f"✅ Setup complete. {summary}\nNext run `/panels`.",
            ephemeral=True,
        )
    except discord.Forbidden as exc:
        await interaction.followup.send(
            f"❌ Missing Discord permissions: {exc}",
            ephemeral=True,
        )


@bot.tree.command(
    name="panels",
    description="Post Verify, role picker and ticket panels",
    guild=GUILD,
)
async def panels_cmd(interaction: discord.Interaction):
    if (
        not interaction.guild
        or not isinstance(interaction.user, discord.Member)
        or not is_staff(interaction.user)
    ):
        await interaction.response.send_message(
            "Only the server owner or staff can run this command.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await post_panels(interaction.guild)
        await interaction.followup.send("✅ Panels posted.", ephemeral=True)
    except Exception as exc:
        await interaction.followup.send(
            f"❌ Could not post panels: {exc}",
            ephemeral=True,
        )


@bot.tree.command(
    name="status",
    description="Check whether the bot is online",
    guild=GUILD,
)
async def status_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"✅ Smash & Steal bot is online. Ping: **{round(bot.latency * 1000)} ms**",
        ephemeral=True,
    )


@bot.tree.command(
    name="help",
    description="Show Smash & Steal bot commands",
    guild=GUILD,
)
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**Commands**\n"
        "`/setup` create missing server structure\n"
        "`/panels` post interactive panels\n"
        "`/status` bot health check",
        ephemeral=True,
    )


@bot.event
async def on_ready():
    print(f"BOT READY | {bot.user} | guild={GUILD_ID}", flush=True)


bot.run(TOKEN, log_handler=None)
