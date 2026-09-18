import os
import re
import io
import asyncio
from datetime import timedelta
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
ENABLE_MEMBER_EVENTS = os.environ.get("ENABLE_MEMBER_EVENTS", "0") == "1"
ENABLE_MESSAGE_CONTENT = os.environ.get("ENABLE_MESSAGE_CONTENT", "0") == "1"
RUN_CLEANUP_ON_START = os.environ.get("RUN_CLEANUP_ON_START", "0") == "1"

intents = discord.Intents.default()
intents.guilds = True
intents.reactions = True
intents.members = ENABLE_MEMBER_EVENTS
intents.message_content = ENABLE_MESSAGE_CONTENT


BASE_MEMBER_PERMISSIONS = {
    "view_channel": True,
    "send_messages": True,
    "read_message_history": True,
    "add_reactions": True,
    "embed_links": True,
    "attach_files": True,
    "use_external_emojis": True,
    "use_external_stickers": True,
    "connect": True,
    "speak": True,
    "stream": True,
    "use_voice_activation": True,
    "use_application_commands": True,
    "create_public_threads": True,
    "send_messages_in_threads": True,
    "change_nickname": True,
}

LIGHT_ROLE_PERMISSIONS = {
    "view_channel": True,
    "read_message_history": True,
    "add_reactions": True,
    "use_application_commands": True,
}

ROLE_SPECS = {
    "Owner": {
        "emoji": "🔱",
        "colour": 0xE74C3C,
        "hoist": True,
        "permissions": {"administrator": True},
    },
    "Founder": {
        "emoji": "👑",
        "colour": 0xF1C40F,
        "hoist": True,
        "permissions": {"administrator": True},
    },
    "Developer": {
        "emoji": "🛠️",
        "colour": 0x3498DB,
        "hoist": True,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
            "view_audit_log": True,
            "manage_roles": True,
            "manage_channels": True,
            "manage_webhooks": True,
            "manage_messages": True,
            "manage_threads": True,
            "manage_events": True,
        },
    },
    "Community Manager": {
        "emoji": "🛡️",
        "colour": 0x9B59B6,
        "hoist": True,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
            "view_audit_log": True,
            "manage_roles": True,
            "manage_channels": True,
            "manage_messages": True,
            "manage_threads": True,
            "manage_nicknames": True,
            "moderate_members": True,
            "kick_members": True,
            "manage_events": True,
        },
    },
    "Moderator": {
        "emoji": "🔨",
        "colour": 0xE74C3C,
        "hoist": True,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
            "view_audit_log": True,
            "kick_members": True,
            "ban_members": True,
            "manage_messages": True,
            "manage_threads": True,
            "manage_nicknames": True,
            "moderate_members": True,
        },
    },
    "Helper": {
        "emoji": "🤝",
        "colour": 0x2ECC71,
        "hoist": True,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
            "manage_messages": True,
            "manage_threads": True,
        },
    },
    "Tester": {
        "emoji": "🧪",
        "colour": 0x1ABC9C,
        "hoist": True,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
        },
    },
    "Early Crew": {
        "emoji": "💎",
        "colour": 0xE67E22,
        "hoist": True,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
        },
    },
    "Bug Hunter": {
        "emoji": "🐛",
        "colour": 0x7CB342,
        "hoist": False,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
            "create_private_threads": True,
        },
    },
    "Content Creator": {
        "emoji": "🎬",
        "colour": 0xE91E63,
        "hoist": False,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
        },
    },
    "Contributor": {
        "emoji": "💡",
        "colour": 0x00BCD4,
        "hoist": False,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
        },
    },
    "Member": {
        "emoji": "✅",
        "colour": 0x95A5A6,
        "hoist": False,
        "permissions": {
            **BASE_MEMBER_PERMISSIONS,
        },
    },
    "Update Ping": {
        "emoji": "📢",
        "colour": 0x5865F2,
        "hoist": False,
        "permissions": {
            **LIGHT_ROLE_PERMISSIONS,
        },
    },
    "Playtest Ping": {
        "emoji": "🧪",
        "colour": 0x57F287,
        "hoist": False,
        "permissions": {
            **LIGHT_ROLE_PERMISSIONS,
        },
    },
    "Event Ping": {
        "emoji": "🎉",
        "colour": 0xFEE75C,
        "hoist": False,
        "permissions": {
            **LIGHT_ROLE_PERMISSIONS,
        },
    },
    "Sneak Peek Ping": {
        "emoji": "👀",
        "colour": 0xEB459E,
        "hoist": False,
        "permissions": {
            **LIGHT_ROLE_PERMISSIONS,
        },
    },
    "PC": {
        "emoji": "🖥️",
        "colour": 0x607D8B,
        "hoist": False,
        "permissions": {
            **LIGHT_ROLE_PERMISSIONS,
        },
    },
    "Mobile": {
        "emoji": "📱",
        "colour": 0x4CAF50,
        "hoist": False,
        "permissions": {
            **LIGHT_ROLE_PERMISSIONS,
        },
    },
    "Console": {
        "emoji": "🎮",
        "colour": 0x673AB7,
        "hoist": False,
        "permissions": {
            **LIGHT_ROLE_PERMISSIONS,
        },
    },
}

ROLE_ORDER = list(ROLE_SPECS.keys())

ROLE_DEFS = {name: spec["hoist"] for name, spec in ROLE_SPECS.items()}


SELF_ROLES = [
    ("Update Ping", "📢"),
    ("Playtest Ping", "🧪"),
    ("Event Ping", "🎉"),
    ("Sneak Peek Ping", "👀"),
    ("PC", "🖥️"),
    ("Mobile", "📱"),
    ("Console", "🎮"),
]

STAFF_ROLE_NAMES = {"Owner", "Founder", "Developer", "Community Manager", "Moderator"}
BROADCAST_WRITER_ROLE_NAMES = {
    "Owner",
    "Founder",
    "Developer",
    "Community Manager",
    "Moderator",
}

READ_ONLY_CHANNELS = {
    "choose-roles",
    "announcements",
    "sneak-peeks",
    "update-log",
    "hall-of-fame",
    "help-and-faq",
    "open-ticket",
    "test-info",
    "known-issues",
    "welcome",
    "goodbye",
}


CHANNEL_NAMES = {
    "start-here": "👋・start-here",
    "rules": "📜・rules",
    "verify": "✅・verify",
    "choose-roles": "🎭・choose-roles",
    "announcements": "📢・announcements",
    "sneak-peeks": "👀・sneak-peeks",
    "update-log": "📝・update-log",
    "general": "💬・general",
    "welcome": "👋・welcome",
    "goodbye": "👋・goodbye",
    "clips-and-loot": "💰・clips-and-loot",
    "find-a-crew": "🤝・find-a-crew",
    "polls-and-events": "🎉・polls-and-events",
    "hall-of-fame": "🏆・hall-of-fame",
    "help-and-faq": "❓・help-and-faq",
    "open-ticket": "🎫・open-ticket",
    "bug-reports": "🐛・bug-reports",
    "suggestions": "💡・suggestions",
    "test-info": "🎮・test-info",
    "tester-chat": "🧪・tester-chat",
    "known-issues": "🚧・known-issues",
    "staff-chat": "🛠・staff-chat",
    "mod-alerts": "🛡・mod-alerts",
    "bot-logs": "🤖・bot-logs",
    "mod-logs": "🧾・mod-logs",
    "ticket-logs": "📁・ticket-logs",
}

VOICE_NAMES = {
    "Hangout": "🔊・Hangout",
    "Crew Room": "👥・Crew Room",
    "Playtest Room": "🧪・Playtest Room",
    "Team Room": "🛠・Team Room",
}


CATEGORY_NAMES = {
    "START HERE": "🚪 START HERE",
    "GAME UPDATES": "📢 GAME UPDATES",
    "COMMUNITY": "🏙️ COMMUNITY",
    "SUPPORT": "🛟 SUPPORT",
    "PLAYTEST": "🧪 PLAYTEST",
    "TEAM": "🔒 TEAM",
    "TICKETS": "🎫 TICKETS",
}

TICKET_EMOJIS = {
    "help": "🎮",
    "player": "🚩",
    "exploit": "🔐",
}


def safe_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower().strip()).strip("-")
    return value[:50] or "member"


def role_display_name(name: str) -> str:
    spec = ROLE_SPECS.get(name)
    if not spec:
        return name
    return f"{spec['emoji']}・{name}"


def normalise_role_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^[^A-Za-z0-9]+", "", value)
    value = value.replace("・", " ").replace("|", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value.casefold()


def find_role(guild: discord.Guild, name: str) -> Optional[discord.Role]:
    display_name = role_display_name(name)
    exact = (
        discord.utils.get(guild.roles, name=display_name)
        or discord.utils.get(guild.roles, name=name)
    )
    if exact:
        return exact

    target = normalise_role_name(name)
    for role in guild.roles:
        if role.is_default():
            continue
        if normalise_role_name(role.name) == target:
            return role
    return None


def bot_can_manage_role(guild: discord.Guild, role: discord.Role) -> bool:
    me = guild.me
    return bool(
        me
        and not role.managed
        and role < me.top_role
        and me.guild_permissions.manage_roles
    )

def find_text(guild: discord.Guild, name: str) -> Optional[discord.TextChannel]:
    display_name = CHANNEL_NAMES.get(name, name)
    return (
        discord.utils.get(guild.text_channels, name=display_name)
        or discord.utils.get(guild.text_channels, name=name)
    )


def find_category(guild: discord.Guild, name: str) -> Optional[discord.CategoryChannel]:
    if name in CATEGORY_NAMES:
        display_name = CATEGORY_NAMES[name]
        return (
            discord.utils.get(guild.categories, name=display_name)
            or discord.utils.get(guild.categories, name=name)
        )

    plain_match = next(
        (plain for plain, display in CATEGORY_NAMES.items() if display == name),
        None,
    )
    if plain_match:
        return (
            discord.utils.get(guild.categories, name=name)
            or discord.utils.get(guild.categories, name=plain_match)
        )

    return discord.utils.get(guild.categories, name=name)


def is_staff(member: discord.Member) -> bool:
    staff_names = set(STAFF_ROLE_NAMES)
    staff_display_names = {role_display_name(name) for name in STAFF_ROLE_NAMES}
    return (
        member.guild.owner_id == member.id
        or member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
        or any(
            role.name in staff_names or role.name in staff_display_names
            for role in member.roles
        )
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


def ticket_metadata(channel: discord.TextChannel):
    topic = channel.topic or ""
    owner_match = re.search(r"ticket-owner:(\d+)", topic)
    type_match = re.search(r"type:([a-z-]+)", topic)
    number_match = re.search(r"ticket-number:(\d+)", topic)
    return {
        "owner_id": int(owner_match.group(1)) if owner_match else None,
        "type": type_match.group(1) if type_match else "unknown",
        "number": int(number_match.group(1)) if number_match else None,
    }


def can_close_ticket(member: discord.Member, channel: discord.TextChannel) -> bool:
    meta = ticket_metadata(channel)
    return (
        meta["owner_id"] == member.id
        or is_staff(member)
    )


async def next_ticket_number(guild: discord.Guild) -> int:
    async with ticket_counter_lock:
        panel = find_text(guild, "open-ticket")
        if not panel:
            return int(discord.utils.utcnow().timestamp()) % 100000

        topic = panel.topic or ""
        match = re.search(r"ticket-counter:(\d+)", topic)
        current = int(match.group(1)) if match else 0
        number = current + 1

        cleaned = re.sub(r"\s*\|?\s*ticket-counter:\d+", "", topic).strip(" |")
        new_topic = f"{cleaned} | ticket-counter:{number}" if cleaned else f"ticket-counter:{number}"
        await panel.edit(
            topic=new_topic[:1024],
            reason="Smash & Steal ticket counter",
        )
        return number


async def build_ticket_transcript(channel: discord.TextChannel) -> bytes:
    lines = [
        f"Smash & Steal Ticket Transcript",
        f"Channel: {channel.name}",
        f"Channel ID: {channel.id}",
        f"Topic: {channel.topic or ''}",
        "",
    ]

    try:
        async for message in channel.history(limit=None, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            author = f"{message.author} ({message.author.id})"
            content = message.content.strip() if message.content else "[no text content available]"
            lines.append(f"[{timestamp}] {author}")
            lines.append(content)

            if message.attachments:
                for attachment in message.attachments:
                    lines.append(f"[attachment] {attachment.url}")

            if message.embeds:
                lines.append(f"[embeds] {len(message.embeds)}")

            lines.append("")
    except discord.HTTPException as exc:
        lines.append(f"[transcript error] HTTP {exc.status}")

    return "\n".join(lines).encode("utf-8", errors="replace")


async def log_ticket_open(channel: discord.TextChannel, opener: discord.Member):
    log_channel = find_text(channel.guild, "ticket-logs")
    if not log_channel:
        return

    meta = ticket_metadata(channel)
    number = meta["number"]
    embed = discord.Embed(
        title=f"🎫 Ticket #{number:04d} opened" if number else "🎫 Ticket opened",
        description=f"{opener.mention} opened {channel.mention}.",
        colour=discord.Colour(0x57F287),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Type", value=meta["type"], inline=True)
    embed.add_field(name="User", value=f"{opener} ({opener.id})", inline=False)
    await log_channel.send(embed=embed)


async def log_ticket_close(
    channel: discord.TextChannel,
    closer: discord.Member,
    reason: str,
):
    log_channel = find_text(channel.guild, "ticket-logs")
    if not log_channel:
        return

    meta = ticket_metadata(channel)
    number = meta["number"]
    transcript = await build_ticket_transcript(channel)
    filename = f"ticket-{number:04d}.txt" if number else f"ticket-{channel.id}.txt"

    embed = discord.Embed(
        title=f"🔒 Ticket #{number:04d} closed" if number else "🔒 Ticket closed",
        colour=discord.Colour(0xED4245),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(
        name="Owner",
        value=f"<@{meta['owner_id']}>" if meta["owner_id"] else "Unknown",
        inline=True,
    )
    embed.add_field(name="Type", value=meta["type"], inline=True)
    embed.add_field(name="Closed by", value=f"{closer} ({closer.id})", inline=False)
    embed.add_field(name="Reason", value=reason[:1024], inline=False)

    await log_channel.send(
        embed=embed,
        file=discord.File(io.BytesIO(transcript), filename=filename),
    )


class CloseTicketModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(
        label="Reason for closing",
        placeholder="Resolved, duplicate, false report, etc.",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=2,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if (
            not interaction.guild
            or not isinstance(interaction.user, discord.Member)
            or not isinstance(interaction.channel, discord.TextChannel)
        ):
            await interaction.response.send_message(
                "This is not a valid ticket.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if not can_close_ticket(interaction.user, channel):
            await interaction.response.send_message(
                "Only the ticket owner or staff can close this ticket.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            await log_ticket_close(
                channel,
                interaction.user,
                str(self.reason.value),
            )
        except discord.HTTPException:
            pass

        await interaction.followup.send(
            "✅ Transcript saved. Closing ticket...",
            ephemeral=True,
        )
        await asyncio.sleep(1)

        try:
            await channel.delete(
                reason=f"Ticket closed by {interaction.user}: {self.reason.value}"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I could not delete the ticket channel.",
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
        if (
            not interaction.guild
            or not isinstance(interaction.user, discord.Member)
            or not isinstance(interaction.channel, discord.TextChannel)
        ):
            await interaction.response.send_message(
                "This is not a ticket channel.",
                ephemeral=True,
            )
            return

        if not can_close_ticket(interaction.user, interaction.channel):
            await interaction.response.send_message(
                "Only the ticket owner or staff can close this ticket.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(CloseTicketModal())


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
            await interaction.response.send_message(
                "This button only works in the server.",
                ephemeral=True,
            )
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
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False)
                },
                reason="Ticket system setup",
            )

        number = await next_ticket_number(guild)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
        }

        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                read_message_history=True,
                manage_messages=True,
                attach_files=True,
            )

        staff_names = {
            "Owner",
            "Founder",
            "Developer",
            "Community Manager",
            "Moderator",
        }
        if self.ticket_type == "help":
            staff_names.add("Helper")

        for role_name in staff_names:
            role = find_role(guild, role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                )

        try:
            ticket_emoji = TICKET_EMOJIS.get(self.ticket_type, "🎫")
            channel = await guild.create_text_channel(
                f"{ticket_emoji}・{number:04d}-{self.ticket_type}-{safe_name(user.display_name)}",
                category=category,
                topic=(
                    f"ticket-owner:{user.id} | "
                    f"type:{self.ticket_type} | "
                    f"ticket-number:{number}"
                ),
                overwrites=overwrites,
                reason=f"Ticket #{number:04d} opened by {user}",
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
            f"{user.mention} **Ticket #{number:04d}**\n"
            f"Type: **{self.ticket_type.upper()}**\n"
            f"{instructions[self.ticket_type]}",
            view=CloseTicketView(),
        )

        try:
            await log_ticket_open(channel, user)
        except discord.HTTPException:
            pass

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
setup_lock = asyncio.Lock()
startup_sync_lock = asyncio.Lock()
ticket_counter_lock = asyncio.Lock()
STARTUP_SYNC_DONE = False
VERIFY_MESSAGE_ID = None


def build_permissions(spec):
    permissions = discord.Permissions.none()
    for permission_name, enabled in spec.get("permissions", {}).items():
        if hasattr(permissions, permission_name):
            setattr(permissions, permission_name, enabled)
    return permissions


def role_audit(guild: discord.Guild, name: str):
    spec = ROLE_SPECS[name]
    role = find_role(guild, name)
    issues = []

    if not role:
        return None, ["missing"]

    expected_name = role_display_name(name)
    expected_permissions = build_permissions(spec)

    if role.name != expected_name:
        issues.append("name/emoji")
    if role.colour.value != spec["colour"]:
        issues.append("colour")
    if role.hoist != spec["hoist"]:
        issues.append("hoist")
    if role.permissions.value != expected_permissions.value:
        issues.append("permissions")
    if role.managed:
        issues.append("managed")
    if guild.me and role >= guild.me.top_role:
        issues.append("above bot")

    if "ROLE_ICONS" in guild.features and role.unicode_emoji != spec["emoji"]:
        issues.append("role icon")

    return role, issues


async def ensure_role(guild: discord.Guild, name: str, hoist: bool = False):
    spec = ROLE_SPECS.get(name, {
        "emoji": "",
        "colour": 0,
        "hoist": hoist,
        "permissions": {},
    })

    display_name = role_display_name(name)
    permissions = build_permissions(spec)
    colour = discord.Colour(spec.get("colour", 0))
    role_icon_supported = "ROLE_ICONS" in guild.features
    existing = find_role(guild, name)

    kwargs = {
        "name": display_name,
        "permissions": permissions,
        "colour": colour,
        "hoist": spec.get("hoist", hoist),
        "mentionable": False,
        "reason": "Smash & Steal role setup",
    }

    if role_icon_supported and spec.get("emoji"):
        kwargs["display_icon"] = spec["emoji"]

    if existing:
        if existing.managed:
            raise RuntimeError(f"{existing.name} is a managed Discord role")
        if not bot_can_manage_role(guild, existing):
            raise PermissionError(
                f"{existing.name} is above the bot role or Manage Roles is missing"
            )
        return await existing.edit(**kwargs)

    me = guild.me
    if not me or not me.guild_permissions.manage_roles:
        raise PermissionError("Bot is missing Manage Roles")
    return await guild.create_role(**kwargs)


async def reorder_managed_roles(guild: discord.Guild):
    me = guild.me
    if not me or not me.guild_permissions.manage_roles:
        return [], ["Bot is missing Manage Roles"]

    moved = []
    failed = []
    for name in reversed(ROLE_ORDER):
        role = find_role(guild, name)
        if not role or role.managed:
            continue
        if role >= me.top_role:
            failed.append(f"{role.name}: above bot")
            continue
        try:
            await role.move(
                below=me.top_role,
                reason="Smash & Steal role hierarchy",
            )
            moved.append(role.name)
            await asyncio.sleep(0.2)
        except (discord.Forbidden, discord.HTTPException, ValueError) as exc:
            failed.append(f"{role.name}: {type(exc).__name__}")
    return moved, failed

async def ensure_category(guild: discord.Guild, name: str, overwrites=None):
    existing = find_category(guild, name)
    if existing:
        return existing
    kwargs = {"reason": "Smash & Steal setup"}
    if overwrites is not None:
        kwargs["overwrites"] = overwrites
    return await guild.create_category(name, **kwargs)


async def ensure_text(guild, category, name, read_only=False, member_only=False):
    display_name = CHANNEL_NAMES.get(name, name)
    existing = find_text(guild, name)
    if existing:
        if existing.name != display_name:
            try:
                await existing.edit(name=display_name, reason="Smash & Steal channel emoji update")
            except discord.Forbidden:
                pass
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
        display_name,
        category=category,
        overwrites=overwrites,
        reason="Smash & Steal setup",
    )


async def ensure_voice(guild, category, name):
    display_name = VOICE_NAMES.get(name, name)
    existing = (
        discord.utils.get(guild.voice_channels, name=display_name)
        or discord.utils.get(guild.voice_channels, name=name)
    )
    if existing:
        if existing.name != display_name:
            try:
                await existing.edit(name=display_name, reason="Smash & Steal voice emoji update")
            except discord.Forbidden:
                pass
        return existing
    return await guild.create_voice_channel(display_name, category=category, reason="Smash & Steal setup")


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


async def setup_server(guild: discord.Guild, progress=None):
    created = []
    totals = {
        "roles": len(ROLE_DEFS),
        "categories": 7,
        "channels": 30,
        "permissions": 2,
    }
    done = {key: 0 for key in totals}

    async def tick(current: str, force: bool = False):
        if progress:
            await progress(done.copy(), totals, current, force)

    await tick("Starting setup...", True)

    for name, hoist in ROLE_DEFS.items():
        existed = find_role(guild, name)
        try:
            role = await ensure_role(guild, name, hoist)
            if not existed:
                created.append(f"role:{role.name}")
            current_role = role.name
        except (discord.Forbidden, discord.HTTPException, PermissionError, RuntimeError) as exc:
            current_role = f"{name} skipped: {type(exc).__name__}"
        done["roles"] += 1
        await tick(f"Role: {current_role}")

    category_specs = [
        ("start", "🚪 START HERE", None),
        ("updates", "📢 GAME UPDATES", None),
        ("community", "🏙️ COMMUNITY", None),
        ("support", "🛟 SUPPORT", None),
        ("playtest", "🧪 PLAYTEST", None),
        ("team", "🔒 TEAM", staff_overwrites(guild)),
        (
            "tickets",
            "🎫 TICKETS",
            {guild.default_role: discord.PermissionOverwrite(view_channel=False)},
        ),
    ]

    categories = {}
    for key, name, overwrites in category_specs:
        existed = find_category(guild, name)
        categories[key] = await ensure_category(guild, name, overwrites=overwrites)
        if not existed:
            created.append(f"category:{name}")
        done["categories"] += 1
        await tick(f"Category: {name}")

    start = categories["start"]
    updates = categories["updates"]
    community = categories["community"]
    support = categories["support"]
    playtest = categories["playtest"]
    team = categories["team"]

    channel_defs = [
        (start, "start-here", True, False),
        (start, "rules", True, False),
        (start, "verify", True, False),
        (start, "choose-roles", True, False),
        (updates, "announcements", True, False),
        (updates, "sneak-peeks", True, False),
        (updates, "update-log", True, False),
        (community, "general", False, True),
        (community, "welcome", True, True),
        (community, "goodbye", True, True),
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
        (team, "mod-logs", False, False),
        (team, "ticket-logs", False, False),
    ]

    for category, name, read_only, member_only in channel_defs:
        existed = find_text(guild, name)
        channel = await ensure_text(guild, category, name, read_only, member_only)
        if not existed:
            created.append(f"channel:{channel.name}")
        done["channels"] += 1
        await tick(f"Text channel: #{channel.name}")

    for category, name in [
        (community, "Hangout"),
        (community, "Crew Room"),
        (playtest, "Playtest Room"),
        (team, "Team Room"),
    ]:
        display_name = VOICE_NAMES.get(name, name)
        if not (
            discord.utils.get(guild.voice_channels, name=display_name)
            or discord.utils.get(guild.voice_channels, name=name)
        ):
            await ensure_voice(guild, category, name)
            created.append(f"voice:{display_name}")
        else:
            await ensure_voice(guild, category, name)
        done["channels"] += 1
        await tick(f"Voice channel: {name}")

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
    done["permissions"] += 1
    await tick("Permissions: tester-chat")

    playtest_room = (
        discord.utils.get(guild.voice_channels, name=VOICE_NAMES["Playtest Room"])
        or discord.utils.get(guild.voice_channels, name="Playtest Room")
    )
    if tester and playtest_room:
        await playtest_room.set_permissions(guild.default_role, view_channel=False)
        await playtest_room.set_permissions(
            tester,
            view_channel=True,
            connect=True,
            speak=True,
        )
    done["permissions"] += 1
    await tick("Permissions: Playtest Room", True)

    return created


def access_roles(guild: discord.Guild):
    names = [
        "Owner", "Founder", "Developer", "Community Manager", "Moderator",
        "Helper", "Tester", "Early Crew", "Bug Hunter", "Content Creator",
        "Contributor", "Member",
    ]
    return [role for name in names if (role := find_role(guild, name))]


def staff_roles(guild: discord.Guild):
    return [role for name in STAFF_ROLE_NAMES if (role := find_role(guild, name))]


def broadcast_writer_roles(guild: discord.Guild):
    return [
        role
        for name in BROADCAST_WRITER_ROLE_NAMES
        if (role := find_role(guild, name))
    ]


def bot_permission_overwrite(channel):
    if isinstance(channel, discord.VoiceChannel):
        return discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
            manage_channels=True,
        )
    return discord.PermissionOverwrite(
        view_channel=True,
        send_messages=True,
        read_message_history=True,
        add_reactions=True,
        manage_messages=True,
        manage_channels=True,
    )


async def replace_channel_overwrites(channel, overwrites):
    guild = channel.guild
    if guild.me:
        overwrites[guild.me] = bot_permission_overwrite(channel)
    await channel.edit(
        overwrites=overwrites,
        reason="Smash & Steal verification gate",
    )


async def set_hidden_until_member(channel, read_only=False):
    guild = channel.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False)
    }

    writers = set(broadcast_writer_roles(guild))

    for role in access_roles(guild):
        if isinstance(channel, discord.VoiceChannel):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
            )
            continue

        if read_only:
            can_write = role in writers
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=can_write,
                add_reactions=True,
                create_public_threads=can_write,
                create_private_threads=can_write,
                send_messages_in_threads=can_write,
                manage_messages=True if can_write else False,
                manage_threads=True if can_write else False,
            )
        else:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
                add_reactions=True,
                create_public_threads=True,
                send_messages_in_threads=True,
            )

    await replace_channel_overwrites(channel, overwrites)


async def set_staff_only(channel):
    guild = channel.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False)
    }
    for role in staff_roles(guild):
        if isinstance(channel, discord.VoiceChannel):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
            )
        else:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
            )
    await replace_channel_overwrites(channel, overwrites)


async def set_tester_only(channel):
    guild = channel.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False)
    }

    tester = find_role(guild, "Tester")
    if tester:
        if isinstance(channel, discord.VoiceChannel):
            overwrites[tester] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
            )
        else:
            overwrites[tester] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
            )

    for role in staff_roles(guild):
        if isinstance(channel, discord.VoiceChannel):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
            )
        else:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=True,
            )

    await replace_channel_overwrites(channel, overwrites)


async def apply_verification_gate(guild: discord.Guild):
    member = find_role(guild, "Member")
    if not member:
        raise RuntimeError("Member role is missing")

    start_here = find_text(guild, "start-here")
    rules = find_text(guild, "rules")
    verify = find_text(guild, "verify")
    choose_roles = find_text(guild, "choose-roles")

    for channel in [start_here, rules, verify]:
        if not channel:
            continue

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=False,
                add_reactions=(channel == verify),
                create_public_threads=False,
                create_private_threads=False,
                send_messages_in_threads=False,
            )
        }
        for role in access_roles(guild):
            can_write = role in set(broadcast_writer_roles(guild))
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=can_write if channel == start_here else False,
                add_reactions=(channel == verify),
                create_public_threads=False,
                create_private_threads=False,
                send_messages_in_threads=False,
            )
        await replace_channel_overwrites(channel, overwrites)

    if choose_roles:
        await set_hidden_until_member(choose_roles, read_only=True)

    read_only = sorted(READ_ONLY_CHANNELS - {"choose-roles"})
    writable = [
        "general", "clips-and-loot", "find-a-crew", "polls-and-events",
        "bug-reports", "suggestions",
    ]

    for name in read_only:
        channel = find_text(guild, name)
        if channel:
            await set_hidden_until_member(channel, read_only=True)

    for name in writable:
        channel = find_text(guild, name)
        if channel:
            await set_hidden_until_member(channel, read_only=False)

    tester_chat = find_text(guild, "tester-chat")
    if tester_chat:
        await set_tester_only(tester_chat)

    for name in ["staff-chat", "mod-alerts", "bot-logs", "mod-logs", "ticket-logs"]:
        channel = find_text(guild, name)
        if channel:
            await set_staff_only(channel)

    for base_name in ["Hangout", "Crew Room"]:
        display_name = VOICE_NAMES[base_name]
        channel = (
            discord.utils.get(guild.voice_channels, name=display_name)
            or discord.utils.get(guild.voice_channels, name=base_name)
        )
        if channel:
            await set_hidden_until_member(channel, read_only=False)

    playtest_room = (
        discord.utils.get(guild.voice_channels, name=VOICE_NAMES["Playtest Room"])
        or discord.utils.get(guild.voice_channels, name="Playtest Room")
    )
    if playtest_room:
        await set_tester_only(playtest_room)

    team_room = (
        discord.utils.get(guild.voice_channels, name=VOICE_NAMES["Team Room"])
        or discord.utils.get(guild.voice_channels, name="Team Room")
    )
    if team_room:
        await set_staff_only(team_room)

    entry_ids = {x.id for x in [start_here, rules, verify] if x}
    managed_ids = set(entry_ids)
    for name in CHANNEL_NAMES:
        channel = find_text(guild, name)
        if channel:
            managed_ids.add(channel.id)
    for display_name in VOICE_NAMES.values():
        channel = discord.utils.get(guild.voice_channels, name=display_name)
        if channel:
            managed_ids.add(channel.id)

    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        if channel.id in managed_ids:
            continue
        if channel.category and channel.category.name in {"🔒 TEAM", "🎫 TICKETS"}:
            continue
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }
        for role in access_roles(guild):
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)
        await replace_channel_overwrites(channel, overwrites)


async def upsert_bot_message(channel, marker, content, view=None, reaction=None):
    global VERIFY_MESSAGE_ID
    existing = None
    try:
        async for message in channel.history(limit=50):
            if message.author == channel.guild.me and message.content.startswith(marker):
                existing = message
                break
    except discord.HTTPException:
        pass

    if existing:
        await existing.edit(content=content, view=view)
        message = existing
    else:
        message = await channel.send(content, view=view)

    if reaction:
        try:
            await message.add_reaction(reaction)
        except discord.HTTPException:
            pass

    if marker.startswith("## ✅ Verify"):
        VERIFY_MESSAGE_ID = message.id

    try:
        if not message.pinned:
            await message.pin(reason="Smash & Steal core server message")
    except discord.HTTPException:
        pass

    return message


async def ensure_core_messages(guild: discord.Guild):
    start = find_text(guild, "start-here")
    rules = find_text(guild, "rules")
    verify = find_text(guild, "verify")
    choose_roles = find_text(guild, "choose-roles")
    tickets = find_text(guild, "open-ticket")

    if not all([start, rules, verify, choose_roles, tickets]):
        raise RuntimeError("One or more core channels are missing")

    await upsert_bot_message(
        start,
        "## 👋 Welcome to Smash & Steal",
        "## 👋 Welcome to Smash & Steal\n"
        "To unlock the server:\n"
        f"**1.** Read {rules.mention}\n"
        f"**2.** Go to {verify.mention}\n"
        "**3.** React with ✅ or press Get Member\n"
        f"**4.** After verification, choose your roles in {choose_roles.mention}\n\n"
        "Until you verify, the rest of the server stays hidden.",
    )

    await upsert_bot_message(
        rules,
        "## 📜 Smash & Steal Rules",
        "## 📜 Smash & Steal Rules\n"
        "**1. Respect other members.** No harassment, hate speech, threats, or targeted abuse.\n"
        "**2. No spam.** Do not flood chats, mass mention people, or repeatedly post the same content.\n"
        "**3. No scams or malicious links.** No phishing, malware, impersonation, or fake giveaways.\n"
        "**4. Keep content appropriate.** No NSFW, sexual, gore, or shock content.\n"
        "**5. No cheating or exploit distribution.** Report game exploits privately through tickets.\n"
        "**6. Protect privacy.** Do not post private information or doxx anyone.\n"
        "**7. Use channels for their purpose.** Keep discussions in the relevant channels.\n"
        "**8. Do not evade moderation.** Do not use alternate accounts to bypass restrictions.\n"
        "**9. Follow platform rules.** Discord and Roblox platform rules still apply.\n"
        "**10. Appeal staff actions privately.** Use a support ticket instead of public arguments.\n\n"
        "By verifying, you confirm that you have read and agree to these rules.",
    )

    await upsert_bot_message(
        verify,
        "## ✅ Verify",
        "## ✅ Verify\n"
        f"Read {rules.mention} first.\n\n"
        "**React with ✅ below** or press **Get Member**.\n"
        "The bot will give you the ✅・Member role and unlock the rest of the server.\n\n"
        "Reacting means you confirm that you have read and agree to the server rules.",
        view=VerifyView(),
        reaction="✅",
    )

    await upsert_bot_message(
        choose_roles,
        "## 🎭 Choose Your Roles",
        "## 🎭 Choose Your Roles\n"
        "Use the buttons below to toggle roles. Press the same button again to remove a role.\n\n"
        "**Notifications**\n"
        "📢 Update Ping: game updates\n"
        "🧪 Playtest Ping: testing announcements\n"
        "🎉 Event Ping: community events\n"
        "👀 Sneak Peek Ping: previews and teasers\n\n"
        "**Platform**\n"
        "🖥️ PC\n"
        "📱 Mobile\n"
        "🎮 Console\n\n"
        "These roles do not grant staff permissions.",
        view=RolePickerView(),
    )

    await upsert_bot_message(
        tickets,
        "## 🎫 Support",
        "## 🎫 Support\n"
        "Choose a ticket type below.\n\n"
        "🎮 Game Help: gameplay or account-related help\n"
        "🚩 Report Player: report rule-breaking with evidence\n"
        "🔐 Report Exploit: report a game exploit privately",
        view=TicketView(),
    )


async def ensure_entry_channels(guild: discord.Guild):
    start_category = find_category(guild, "🚪 START HERE")
    if not start_category:
        start_category = await ensure_category(guild, "🚪 START HERE")

    community = find_category(guild, "🏙️ COMMUNITY")
    if not community:
        community = await ensure_category(guild, "🏙️ COMMUNITY")

    support = find_category(guild, "🛟 SUPPORT")
    if not support:
        support = await ensure_category(guild, "🛟 SUPPORT")

    team = find_category(guild, "🔒 TEAM")
    if not team:
        team = await ensure_category(guild, "🔒 TEAM", overwrites=staff_overwrites(guild))

    await ensure_text(guild, team, "mod-logs", False, False)
    await ensure_text(guild, team, "ticket-logs", False, False)
    await ensure_text(guild, start_category, "start-here", True, False)
    await ensure_text(guild, start_category, "rules", True, False)
    await ensure_text(guild, start_category, "verify", True, False)
    await ensure_text(guild, start_category, "choose-roles", True, True)
    await ensure_text(guild, community, "welcome", True, True)
    await ensure_text(guild, community, "goodbye", True, True)
    await ensure_text(guild, support, "open-ticket", True, True)


async def ensure_entry_system(guild: discord.Guild):
    await ensure_entry_channels(guild)
    await apply_verification_gate(guild)
    await ensure_core_messages(guild)


async def post_panels(guild: discord.Guild):
    await ensure_entry_system(guild)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.guild_id != GUILD_ID or str(payload.emoji) != "✅":
        return
    if bot.user and payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    verify = find_text(guild, "verify")
    if not verify or payload.channel_id != verify.id:
        return
    if VERIFY_MESSAGE_ID and payload.message_id != VERIFY_MESSAGE_ID:
        return

    member = payload.member
    if not member or member.bot:
        return

    if getattr(member, "pending", False):
        try:
            await member.send(
                "Complete Discord membership screening first, then react with ✅ again."
            )
        except discord.HTTPException:
            pass
        return

    role = find_role(guild, "Member")
    if not role or role in member.roles:
        return

    try:
        await member.add_roles(role, reason="Verified with ✅ reaction")
    except discord.Forbidden:
        pass


@bot.event
async def on_member_join(member: discord.Member):
    if not ENABLE_MEMBER_EVENTS or member.guild.id != GUILD_ID or member.bot:
        return

    channel = find_text(member.guild, "welcome")
    if not channel:
        return

    rules = find_text(member.guild, "rules")
    verify = find_text(member.guild, "verify")
    rules_text = rules.mention if rules else "#rules"
    verify_text = verify.mention if verify else "#verify"

    embed = discord.Embed(
        title="👋 Welcome to Smash & Steal!",
        description=(
            f"Welcome {member.mention}!\n"
            f"Read {rules_text} and verify in {verify_text} to unlock the server."
        ),
        colour=discord.Colour(0x57F287),
    )
    embed.set_footer(text=f"Member #{member.guild.member_count}")
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


@bot.event
async def on_member_remove(member: discord.Member):
    if member.guild.id != GUILD_ID or member.bot:
        return

    was_kicked = await detect_and_log_kick(member)

    if not ENABLE_MEMBER_EVENTS:
        return

    channel = find_text(member.guild, "goodbye")
    if not channel:
        return

    embed = discord.Embed(
        title="👋 Goodbye",
        description=(
            f"**{member.display_name}** was removed from the server."
            if was_kicked
            else f"**{member.display_name}** left the server."
        ),
        colour=discord.Colour(0xED4245),
    )
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


def is_mod_log_channel(channel) -> bool:
    if not isinstance(channel, discord.TextChannel):
        return False
    return channel.name in {
        CHANNEL_NAMES.get("mod-logs"),
        CHANNEL_NAMES.get("ticket-logs"),
        CHANNEL_NAMES.get("bot-logs"),
    }


async def send_mod_log(
    guild: discord.Guild,
    title: str,
    description: str,
    *,
    colour: int = 0x5865F2,
    fields=None,
):
    channel = find_text(guild, "mod-logs")
    if not channel:
        return

    embed = discord.Embed(
        title=title,
        description=description[:4096],
        colour=discord.Colour(colour),
        timestamp=discord.utils.utcnow(),
    )
    for name, value, inline in fields or []:
        embed.add_field(
            name=name[:256],
            value=str(value)[:1024] or "None",
            inline=inline,
        )
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def recent_audit_entry(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: int,
    *,
    max_age_seconds: int = 10,
):
    me = guild.me
    if not me or not me.guild_permissions.view_audit_log:
        return None

    now = discord.utils.utcnow()
    try:
        async for entry in guild.audit_logs(limit=6, action=action):
            target = getattr(entry, "target", None)
            if getattr(target, "id", None) != target_id:
                continue
            age = (now - entry.created_at).total_seconds()
            if age <= max_age_seconds:
                return entry
    except discord.HTTPException:
        return None
    return None


def actor_can_target(actor: discord.Member, target: discord.Member):
    guild = actor.guild
    me = guild.me

    if actor.id == target.id:
        return False, "You cannot moderate yourself."
    if target.id == guild.owner_id:
        return False, "The server owner cannot be moderated."
    if me and target.top_role >= me.top_role:
        return False, "That member is above or equal to the bot role."
    if actor.id != guild.owner_id and target.top_role >= actor.top_role:
        return False, "That member is above or equal to your highest role."
    return True, None


@bot.event
async def on_message_delete(message: discord.Message):
    if (
        not message.guild
        or message.guild.id != GUILD_ID
        or is_mod_log_channel(message.channel)
    ):
        return

    text = message.content.strip() if message.content else "[content unavailable]"
    attachments = "\n".join(a.url for a in message.attachments) or "None"

    await send_mod_log(
        message.guild,
        "🗑️ Message deleted",
        f"Message by {message.author.mention} was deleted in {message.channel.mention}.",
        colour=0xED4245,
        fields=[
            ("Author", f"{message.author} ({message.author.id})", False),
            ("Content", text, False),
            ("Attachments", attachments, False),
            ("Message ID", message.id, True),
        ],
    )


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if (
        not after.guild
        or after.guild.id != GUILD_ID
        or is_mod_log_channel(after.channel)
        or before.author.bot
    ):
        return

    if before.content == after.content:
        return

    old_text = before.content.strip() if before.content else "[content unavailable]"
    new_text = after.content.strip() if after.content else "[content unavailable]"

    await send_mod_log(
        after.guild,
        "✏️ Message edited",
        f"{after.author.mention} edited a message in {after.channel.mention}.",
        colour=0xFEE75C,
        fields=[
            ("Before", old_text, False),
            ("After", new_text, False),
            ("Message", after.jump_url, False),
        ],
    )


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if after.guild.id != GUILD_ID:
        return

    before_ids = {role.id for role in before.roles}
    after_ids = {role.id for role in after.roles}
    added = [role for role in after.roles if role.id not in before_ids]
    removed = [role for role in before.roles if role.id not in after_ids]

    if added or removed:
        entry = await recent_audit_entry(
            after.guild,
            discord.AuditLogAction.member_role_update,
            after.id,
        )
        actor = getattr(entry, "user", None) if entry else None
        fields = []
        if added:
            fields.append(("Added", ", ".join(role.mention for role in added), False))
        if removed:
            fields.append(("Removed", ", ".join(role.mention for role in removed), False))
        fields.append(
            (
                "Changed by",
                f"{actor} ({actor.id})" if actor else "Bot/self-role/unknown",
                False,
            )
        )
        await send_mod_log(
            after.guild,
            "🎭 Member roles changed",
            f"Roles changed for {after.mention}.",
            fields=fields,
        )

    if before.timed_out_until != after.timed_out_until:
        entry = await recent_audit_entry(
            after.guild,
            discord.AuditLogAction.member_update,
            after.id,
        )
        actor = getattr(entry, "user", None) if entry else None
        reason = getattr(entry, "reason", None) if entry else None

        if after.timed_out_until:
            description = f"{after.mention} was timed out until <t:{int(after.timed_out_until.timestamp())}:F>."
            title = "⏳ Member timed out"
            colour = 0xFEE75C
        else:
            description = f"Timeout removed from {after.mention}."
            title = "✅ Timeout removed"
            colour = 0x57F287

        await send_mod_log(
            after.guild,
            title,
            description,
            colour=colour,
            fields=[
                ("Moderator", f"{actor} ({actor.id})" if actor else "Unknown", False),
                ("Reason", reason or "No reason recorded", False),
            ],
        )


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    if guild.id != GUILD_ID:
        return

    entry = await recent_audit_entry(
        guild,
        discord.AuditLogAction.ban,
        user.id,
    )
    actor = getattr(entry, "user", None) if entry else None
    reason = getattr(entry, "reason", None) if entry else None

    await send_mod_log(
        guild,
        "🔨 Member banned",
        f"**{user}** ({user.id}) was banned.",
        colour=0xED4245,
        fields=[
            ("Moderator", f"{actor} ({actor.id})" if actor else "Unknown", False),
            ("Reason", reason or "No reason recorded", False),
        ],
    )


@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    if guild.id != GUILD_ID:
        return

    entry = await recent_audit_entry(
        guild,
        discord.AuditLogAction.unban,
        user.id,
    )
    actor = getattr(entry, "user", None) if entry else None
    reason = getattr(entry, "reason", None) if entry else None

    await send_mod_log(
        guild,
        "🔓 Member unbanned",
        f"**{user}** ({user.id}) was unbanned.",
        colour=0x57F287,
        fields=[
            ("Moderator", f"{actor} ({actor.id})" if actor else "Unknown", False),
            ("Reason", reason or "No reason recorded", False),
        ],
    )


async def detect_and_log_kick(member: discord.Member) -> bool:
    entry = await recent_audit_entry(
        member.guild,
        discord.AuditLogAction.kick,
        member.id,
    )
    if not entry:
        return False

    actor = getattr(entry, "user", None)
    await send_mod_log(
        member.guild,
        "👢 Member kicked",
        f"**{member}** ({member.id}) was kicked.",
        colour=0xED4245,
        fields=[
            ("Moderator", f"{actor} ({actor.id})" if actor else "Unknown", False),
            ("Reason", entry.reason or "No reason recorded", False),
        ],
    )
    return True


def has_moderation_permission(member: discord.Member, permission: str) -> bool:
    return (
        member.guild.owner_id == member.id
        or member.guild_permissions.administrator
        or getattr(member.guild_permissions, permission, False)
    )


@bot.tree.command(
    name="kick",
    description="Kick a member from the server",
    guild=GUILD,
)
@app_commands.describe(member="Member to kick", reason="Reason for the kick")
async def kick_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided",
):
    actor = interaction.user
    if not isinstance(actor, discord.Member) or not has_moderation_permission(actor, "kick_members"):
        await interaction.response.send_message("You do not have Kick Members.", ephemeral=True)
        return

    allowed, error = actor_can_target(actor, member)
    if not allowed:
        await interaction.response.send_message(error, ephemeral=True)
        return

    try:
        await member.kick(reason=f"{actor}: {reason}")
        await interaction.response.send_message(
            f"👢 Kicked **{member}**. Reason: {reason}",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I cannot kick that member because of role hierarchy or permissions.",
            ephemeral=True,
        )


@bot.tree.command(
    name="ban",
    description="Ban a member from the server",
    guild=GUILD,
)
@app_commands.describe(member="Member to ban", reason="Reason for the ban")
async def ban_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided",
):
    actor = interaction.user
    if not isinstance(actor, discord.Member) or not has_moderation_permission(actor, "ban_members"):
        await interaction.response.send_message("You do not have Ban Members.", ephemeral=True)
        return

    allowed, error = actor_can_target(actor, member)
    if not allowed:
        await interaction.response.send_message(error, ephemeral=True)
        return

    try:
        await member.ban(reason=f"{actor}: {reason}")
        await interaction.response.send_message(
            f"🔨 Banned **{member}**. Reason: {reason}",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I cannot ban that member because of role hierarchy or permissions.",
            ephemeral=True,
        )


@bot.tree.command(
    name="unban",
    description="Unban a user by Discord user ID",
    guild=GUILD,
)
@app_commands.describe(user_id="Discord user ID", reason="Reason for the unban")
async def unban_cmd(
    interaction: discord.Interaction,
    user_id: str,
    reason: str = "No reason provided",
):
    actor = interaction.user
    if not isinstance(actor, discord.Member) or not has_moderation_permission(actor, "ban_members"):
        await interaction.response.send_message("You do not have Ban Members.", ephemeral=True)
        return

    try:
        target_id = int(user_id)
    except ValueError:
        await interaction.response.send_message("That is not a valid user ID.", ephemeral=True)
        return

    try:
        user = await bot.fetch_user(target_id)
        await interaction.guild.unban(user, reason=f"{actor}: {reason}")
        await interaction.response.send_message(
            f"🔓 Unbanned **{user}**. Reason: {reason}",
            ephemeral=True,
        )
    except discord.NotFound:
        await interaction.response.send_message("That user is not banned.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("I cannot unban that user.", ephemeral=True)


@bot.tree.command(
    name="timeout",
    description="Timeout a member",
    guild=GUILD,
)
@app_commands.describe(
    member="Member to timeout",
    minutes="Timeout length in minutes",
    reason="Reason for the timeout",
)
async def timeout_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "No reason provided",
):
    actor = interaction.user
    if not isinstance(actor, discord.Member) or not has_moderation_permission(actor, "moderate_members"):
        await interaction.response.send_message("You do not have Moderate Members.", ephemeral=True)
        return

    allowed, error = actor_can_target(actor, member)
    if not allowed:
        await interaction.response.send_message(error, ephemeral=True)
        return

    try:
        await member.timeout(
            timedelta(minutes=int(minutes)),
            reason=f"{actor}: {reason}",
        )
        await interaction.response.send_message(
            f"⏳ Timed out **{member}** for **{minutes} minutes**. Reason: {reason}",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I cannot timeout that member because of role hierarchy or permissions.",
            ephemeral=True,
        )


@bot.tree.command(
    name="untimeout",
    description="Remove a member timeout",
    guild=GUILD,
)
@app_commands.describe(member="Member whose timeout should be removed", reason="Reason")
async def untimeout_cmd(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided",
):
    actor = interaction.user
    if not isinstance(actor, discord.Member) or not has_moderation_permission(actor, "moderate_members"):
        await interaction.response.send_message("You do not have Moderate Members.", ephemeral=True)
        return

    allowed, error = actor_can_target(actor, member)
    if not allowed:
        await interaction.response.send_message(error, ephemeral=True)
        return

    try:
        await member.timeout(None, reason=f"{actor}: {reason}")
        await interaction.response.send_message(
            f"✅ Removed timeout from **{member}**.",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I cannot remove that timeout.",
            ephemeral=True,
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

    if setup_lock.locked():
        await interaction.response.send_message(
            "⚙️ Setup is already running. Wait for the current setup to finish.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    last_update = 0.0

    def render_progress(done, totals, current):
        completed = sum(done.values())
        total = sum(totals.values())
        percent = int((completed / total) * 100) if total else 100
        width = 14
        filled = round(width * completed / total) if total else width
        bar = "█" * filled + "░" * (width - filled)
        return (
            "## ⚙️ Smash & Steal Setup\n"
            f"`{bar}` **{percent}%**\n\n"
            f"🎭 Roles: **{done['roles']}/{totals['roles']}**\n"
            f"📁 Categories: **{done['categories']}/{totals['categories']}**\n"
            f"💬 Channels: **{done['channels']}/{totals['channels']}**\n"
            f"🔐 Permissions: **{done['permissions']}/{totals['permissions']}**\n\n"
            f"Current: `{current}`\n"
            "Do not run /setup again while this is running."
        )

    async def progress(done, totals, current, force=False):
        nonlocal last_update
        now = asyncio.get_running_loop().time()
        if not force and now - last_update < 1.5:
            return
        last_update = now
        try:
            await interaction.edit_original_response(
                content=render_progress(done, totals, current)
            )
        except discord.HTTPException:
            pass

    async with setup_lock:
        try:
            created = await setup_server(interaction.guild, progress=progress)
            summary = (
                "Nothing new was needed."
                if not created
                else f"Created **{len(created)}** missing server items."
            )
            await interaction.edit_original_response(
                content=(
                    "## ✅ Setup complete\n"
                    f"{summary}\n\n"
                    "Next command: `/panels`"
                )
            )
        except discord.Forbidden as exc:
            await interaction.edit_original_response(
                content=f"❌ Missing Discord permissions: `{exc}`"
            )
        except Exception as exc:
            await interaction.edit_original_response(
                content=f"❌ Setup stopped because of an error: `{type(exc).__name__}: {exc}`"
            )
            raise


@bot.tree.command(
    name="entrysetup",
    description="Fix verification gate, rules, verify and choose-role panels",
    guild=GUILD,
)
async def entrysetup_cmd(interaction: discord.Interaction):
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
        await ensure_entry_system(interaction.guild)
        await interaction.edit_original_response(
            content=(
                "## ✅ Entry system fixed\n"
                "Unverified users can now see only start-here, rules and verify.\n"
                "The ✅ reaction grants Member.\n"
                "choose-roles becomes visible after verification."
            )
        )
    except Exception as exc:
        await interaction.edit_original_response(
            content=f"❌ Entry setup failed: {type(exc).__name__}: {exc}"
        )


@bot.tree.command(
    name="channelpermissions",
    description="Fix read-only and writable channel permissions",
    guild=GUILD,
)
async def channelpermissions_cmd(interaction: discord.Interaction):
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
        await apply_verification_gate(interaction.guild)
        await interaction.edit_original_response(
            content=(
                "## ✅ Channel permissions fixed\n"
                "Read-only channels now block normal roles from sending messages and creating threads.\n"
                "Only Owner, Founder, Developer, Community Manager and Moderator can post there."
            )
        )
    except Exception as exc:
        await interaction.edit_original_response(
            content=f"❌ Channel permission update failed: {type(exc).__name__}: {exc}"
        )


@bot.tree.command(
    name="emojis",
    description="Fix emojis across Smash & Steal categories and channels",
    guild=GUILD,
)
async def emojis_cmd(interaction: discord.Interaction):
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
    guild = interaction.guild

    renamed_categories = []
    renamed_text = []
    renamed_voice = []
    renamed_tickets = []
    already_ok = []
    missing = []
    failed = []

    async def rename_channel(channel, display_name, bucket, label):
        if channel.name == display_name:
            already_ok.append(display_name)
            return
        try:
            await channel.edit(
                name=display_name,
                reason="Smash & Steal full emoji update",
            )
            bucket.append(display_name)
            await asyncio.sleep(0.25)
        except discord.Forbidden:
            failed.append(f"{label} (Missing Access)")
        except discord.HTTPException as exc:
            failed.append(f"{label} (HTTP {exc.status})")

    for plain_name, display_name in CATEGORY_NAMES.items():
        category = (
            discord.utils.get(guild.categories, name=display_name)
            or discord.utils.get(guild.categories, name=plain_name)
        )
        if not category:
            missing.append(f"Category: {plain_name}")
            continue
        await rename_channel(
            category,
            display_name,
            renamed_categories,
            f"Category: {plain_name}",
        )

    for base_name, display_name in CHANNEL_NAMES.items():
        channel = (
            discord.utils.get(guild.text_channels, name=display_name)
            or discord.utils.get(guild.text_channels, name=base_name)
        )
        if not channel:
            missing.append(f"Text: {base_name}")
            continue
        await rename_channel(
            channel,
            display_name,
            renamed_text,
            f"Text: {base_name}",
        )

    for base_name, display_name in VOICE_NAMES.items():
        channel = (
            discord.utils.get(guild.voice_channels, name=display_name)
            or discord.utils.get(guild.voice_channels, name=base_name)
        )
        if not channel:
            missing.append(f"Voice: {base_name}")
            continue
        await rename_channel(
            channel,
            display_name,
            renamed_voice,
            f"Voice: {base_name}",
        )

    for channel in list(guild.text_channels):
        topic = channel.topic or ""
        if "ticket-owner:" not in topic:
            continue

        type_match = re.search(r"type:(help|player|exploit)", topic)
        if not type_match:
            continue

        ticket_type = type_match.group(1)
        emoji = TICKET_EMOJIS.get(ticket_type, "🎫")
        current_base = re.sub(r"^[^a-zA-Z0-9]+・?", "", channel.name)
        if current_base.startswith(f"{ticket_type}-"):
            suffix = current_base[len(ticket_type) + 1:]
        else:
            suffix = safe_name(channel.name)

        display_name = f"{emoji}・{ticket_type}-{suffix}"
        await rename_channel(
            channel,
            display_name,
            renamed_tickets,
            f"Ticket: {channel.name}",
        )

    lines = [
        "## ✅ Full emoji update finished",
        f"📁 Categories renamed: **{len(renamed_categories)}**",
        f"💬 Text channels renamed: **{len(renamed_text)}**",
        f"🔊 Voice channels renamed: **{len(renamed_voice)}**",
        f"🎫 Ticket channels renamed: **{len(renamed_tickets)}**",
        f"✅ Already correct: **{len(already_ok)}**",
        f"❓ Missing: **{len(missing)}**",
        f"❌ Failed: **{len(failed)}**",
    ]

    if failed:
        lines.append(
            "\n**Could not rename:**\n"
            + "\n".join(f"• {item}" for item in failed[:20])
        )

    if missing:
        lines.append(
            "\n**Not found:**\n"
            + "\n".join(f"• {item}" for item in missing[:20])
        )

    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(
    name="rolesetup",
    description="Force-fix role names, colours, permissions and hierarchy",
    guild=GUILD,
)
async def rolesetup_cmd(interaction: discord.Interaction):
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
    guild = interaction.guild
    me = guild.me

    if not me or not me.guild_permissions.manage_roles:
        await interaction.followup.send(
            "❌ The bot does not have **Manage Roles**.",
            ephemeral=True,
        )
        return

    updated = []
    blocked = []
    created = []

    for index, (name, spec) in enumerate(ROLE_SPECS.items(), start=1):
        existing = find_role(guild, name)

        if existing and existing.managed:
            blocked.append(f"{existing.name}: managed by Discord")
            continue

        if existing and existing >= me.top_role:
            blocked.append(
                f"{existing.name}: move this role BELOW **{me.top_role.name}**"
            )
            continue

        try:
            result = await ensure_role(guild, name, spec["hoist"])
            if existing:
                updated.append(result.name)
            else:
                created.append(result.name)
            await asyncio.sleep(0.25)
        except PermissionError as exc:
            blocked.append(f"{name}: {exc}")
        except RuntimeError as exc:
            blocked.append(f"{name}: {exc}")
        except discord.Forbidden:
            blocked.append(f"{name}: Missing Access")
        except discord.HTTPException as exc:
            blocked.append(f"{name}: HTTP {exc.status}")

        if index % 5 == 0:
            await interaction.edit_original_response(
                content=(
                    "## 🎭 Role setup in progress\n"
                    f"Processed: **{index}/{len(ROLE_SPECS)}**\n"
                    f"Updated: **{len(updated)}**\n"
                    f"Created: **{len(created)}**\n"
                    f"Blocked: **{len(blocked)}**"
                )
            )

    moved, move_failed = await reorder_managed_roles(guild)
    blocked.extend(move_failed)

    compliant = []
    audit_issues = []
    for name in ROLE_SPECS:
        role, issues = role_audit(guild, name)
        if not issues:
            compliant.append(role.name)
        else:
            audit_issues.append(
                f"{role_display_name(name)}: {', '.join(issues)}"
            )

    lines = [
        "## ✅ Smash & Steal role setup finished",
        f"Updated: **{len(updated)}**",
        f"Created: **{len(created)}**",
        f"Hierarchy moves: **{len(moved)}**",
        f"Fully correct now: **{len(compliant)}/{len(ROLE_SPECS)}**",
        f"Blocked / still wrong: **{len(audit_issues)}**",
        "",
        f"Bot top role: **{me.top_role.name}**",
        "Emoji is always placed in the role name. A real separate role icon is added only when Discord enables ROLE_ICONS for the server.",
    ]

    if audit_issues:
        lines.append(
            "\n**Still needs attention:**\n"
            + "\n".join(f"• {item}" for item in audit_issues[:25])
        )

    if blocked:
        unique_blocked = list(dict.fromkeys(blocked))
        lines.append(
            "\n**Why some changes were blocked:**\n"
            + "\n".join(f"• {item}" for item in unique_blocked[:25])
        )

    await interaction.edit_original_response(content="\n".join(lines))


@bot.tree.command(
    name="roleaudit",
    description="Check every Smash & Steal role against its expected setup",
    guild=GUILD,
)
async def roleaudit_cmd(interaction: discord.Interaction):
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

    guild = interaction.guild
    good = []
    bad = []

    for name in ROLE_SPECS:
        role, issues = role_audit(guild, name)
        if not issues:
            good.append(role.name)
        else:
            bad.append(f"{role_display_name(name)}: {', '.join(issues)}")

    lines = [
        "## 🔎 Role audit",
        f"Correct: **{len(good)}/{len(ROLE_SPECS)}**",
        f"Needs fixing: **{len(bad)}**",
    ]

    if bad:
        lines.append(
            "\n**Problems:**\n"
            + "\n".join(f"• {item}" for item in bad[:30])
        )
    else:
        lines.append("\n✅ Every managed role matches the specification.")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


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


async def ensure_archive_category(guild: discord.Guild):
    archive = discord.utils.get(guild.categories, name="🗃️ ARCHIVE")
    if archive:
        return archive

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False)
    }
    for role in staff_roles(guild):
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            connect=True,
            speak=True,
        )
    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            connect=True,
            speak=True,
        )

    return await guild.create_category(
        "🗃️ ARCHIVE",
        overwrites=overwrites,
        reason="Smash & Steal safe cleanup archive",
    )


async def channel_has_messages(channel: discord.TextChannel) -> bool:
    try:
        async for _ in channel.history(limit=1):
            return True
    except discord.HTTPException:
        return True
    return False


async def safe_cleanup_server(guild: discord.Guild):
    report = {
        "roles_deleted": [],
        "members_migrated": 0,
        "text_deleted": [],
        "text_archived": [],
        "voice_deleted": [],
        "voice_archived": [],
        "categories_deleted": [],
        "channels_moved": [],
        "created": [],
        "skipped": [],
    }

    me = guild.me
    if not me:
        report["skipped"].append("Bot member unavailable")
        return report

    # 1. Role duplicates. Keep the exact canonical emoji role.
    for base_name in ROLE_SPECS:
        canonical_name = role_display_name(base_name)
        canonical = discord.utils.get(guild.roles, name=canonical_name)
        if not canonical:
            try:
                canonical = await ensure_role(
                    guild,
                    base_name,
                    ROLE_SPECS[base_name]["hoist"],
                )
                report["created"].append(f"role:{canonical.name}")
            except Exception as exc:
                report["skipped"].append(
                    f"Cannot create canonical role {canonical_name}: {type(exc).__name__}"
                )
                continue

        target_key = normalise_role_name(base_name)
        duplicates = [
            role
            for role in list(guild.roles)
            if not role.is_default()
            and not role.managed
            and role.id != canonical.id
            and normalise_role_name(role.name) == target_key
        ]

        for old_role in duplicates:
            if old_role >= me.top_role:
                report["skipped"].append(
                    f"Role above bot, not deleted: {old_role.name}"
                )
                continue

            for member in list(old_role.members):
                try:
                    if canonical not in member.roles:
                        await member.add_roles(
                            canonical,
                            reason="Smash & Steal role cleanup migration",
                        )
                    await member.remove_roles(
                        old_role,
                        reason="Smash & Steal role cleanup migration",
                    )
                    report["members_migrated"] += 1
                except discord.HTTPException:
                    report["skipped"].append(
                        f"Could not migrate {member} from {old_role.name}"
                    )

            try:
                await old_role.delete(reason="Smash & Steal duplicate role cleanup")
                report["roles_deleted"].append(old_role.name)
            except discord.HTTPException as exc:
                report["skipped"].append(
                    f"Could not delete role {old_role.name}: HTTP {exc.status}"
                )

    archive = None

    # 2. Duplicate text channels. Keep exact canonical. Delete only empty duplicates.
    for base_name, canonical_name in CHANNEL_NAMES.items():
        canonical = discord.utils.get(guild.text_channels, name=canonical_name)
        if not canonical:
            continue

        key = normalise_channel_name(base_name)
        duplicates = [
            channel
            for channel in list(guild.text_channels)
            if channel.id != canonical.id
            and normalise_channel_name(channel.name) == key
        ]

        for old in duplicates:
            if await channel_has_messages(old):
                if archive is None:
                    archive = await ensure_archive_category(guild)
                legacy_name = f"🗃️・legacy-{base_name}-{str(old.id)[-4:]}"
                try:
                    await old.edit(
                        name=legacy_name,
                        category=archive,
                        sync_permissions=False,
                        reason="Smash & Steal preserve legacy channel",
                    )
                    await set_staff_only(old)
                    report["text_archived"].append(legacy_name)
                except discord.HTTPException as exc:
                    report["skipped"].append(
                        f"Could not archive {old.name}: HTTP {exc.status}"
                    )
            else:
                old_name = old.name
                try:
                    await old.delete(reason="Smash & Steal empty duplicate channel cleanup")
                    report["text_deleted"].append(old_name)
                except discord.HTTPException as exc:
                    report["skipped"].append(
                        f"Could not delete {old_name}: HTTP {exc.status}"
                    )

    # 3. Duplicate voice channels.
    for base_name, canonical_name in VOICE_NAMES.items():
        canonical = discord.utils.get(guild.voice_channels, name=canonical_name)
        if not canonical:
            continue

        key = normalise_channel_name(base_name)
        duplicates = [
            channel
            for channel in list(guild.voice_channels)
            if channel.id != canonical.id
            and normalise_channel_name(channel.name) == key
        ]

        for old in duplicates:
            if old.members:
                if archive is None:
                    archive = await ensure_archive_category(guild)
                legacy_name = f"🗃️・legacy-{safe_name(base_name)}-{str(old.id)[-4:]}"
                try:
                    await old.edit(
                        name=legacy_name,
                        category=archive,
                        sync_permissions=False,
                        reason="Smash & Steal preserve occupied legacy voice",
                    )
                    await set_staff_only(old)
                    report["voice_archived"].append(legacy_name)
                except discord.HTTPException as exc:
                    report["skipped"].append(
                        f"Could not archive voice {old.name}: HTTP {exc.status}"
                    )
            else:
                old_name = old.name
                try:
                    await old.delete(reason="Smash & Steal duplicate voice cleanup")
                    report["voice_deleted"].append(old_name)
                except discord.HTTPException as exc:
                    report["skipped"].append(
                        f"Could not delete voice {old_name}: HTTP {exc.status}"
                    )

    # 4. Duplicate categories. Move remaining children into canonical category.
    for plain_name, canonical_name in CATEGORY_NAMES.items():
        canonical = discord.utils.get(guild.categories, name=canonical_name)
        if not canonical:
            continue

        key = normalise_channel_name(plain_name)
        duplicates = [
            category
            for category in list(guild.categories)
            if category.id != canonical.id
            and normalise_channel_name(category.name) == key
        ]

        for old_category in duplicates:
            for child in list(old_category.channels):
                try:
                    await child.edit(
                        category=canonical,
                        sync_permissions=False,
                        reason="Smash & Steal duplicate category cleanup",
                    )
                    report["channels_moved"].append(
                        f"{child.name} -> {canonical.name}"
                    )
                except discord.HTTPException as exc:
                    report["skipped"].append(
                        f"Could not move {child.name}: HTTP {exc.status}"
                    )

            if not old_category.channels:
                old_name = old_category.name
                try:
                    await old_category.delete(
                        reason="Smash & Steal duplicate category cleanup"
                    )
                    report["categories_deleted"].append(old_name)
                except discord.HTTPException as exc:
                    report["skipped"].append(
                        f"Could not delete category {old_name}: HTTP {exc.status}"
                    )

    # 5. Ensure missing managed voice channels exist.
    team_category = find_category(guild, "🔒 TEAM")
    if team_category:
        team_room = (
            discord.utils.get(guild.voice_channels, name=VOICE_NAMES["Team Room"])
            or discord.utils.get(guild.voice_channels, name="Team Room")
        )
        if not team_room:
            try:
                created = await ensure_voice(guild, team_category, "Team Room")
                report["created"].append(f"voice:{created.name}")
            except discord.HTTPException as exc:
                report["skipped"].append(
                    f"Could not create Team Room: HTTP {exc.status}"
                )

    # Re-apply all managed permissions and core messages after moving/deleting.
    await ensure_entry_system(guild)

    return report


def format_cleanup_report(report):
    lines = [
        "## 🧹 Smash & Steal Cleanup",
        f"Roles deleted: **{len(report['roles_deleted'])}**",
        f"Member-role migrations: **{report['members_migrated']}**",
        f"Empty text duplicates deleted: **{len(report['text_deleted'])}**",
        f"Legacy text channels archived: **{len(report['text_archived'])}**",
        f"Voice duplicates deleted: **{len(report['voice_deleted'])}**",
        f"Legacy voice channels archived: **{len(report['voice_archived'])}**",
        f"Duplicate categories deleted: **{len(report['categories_deleted'])}**",
        f"Channels moved: **{len(report['channels_moved'])}**",
        f"Missing items created: **{len(report['created'])}**",
        f"Skipped/errors: **{len(report['skipped'])}**",
    ]

    for title, key in [
        ("Deleted roles", "roles_deleted"),
        ("Deleted text channels", "text_deleted"),
        ("Archived text channels", "text_archived"),
        ("Deleted voice channels", "voice_deleted"),
        ("Deleted categories", "categories_deleted"),
        ("Created", "created"),
        ("Skipped", "skipped"),
    ]:
        values = report[key]
        if values:
            lines.append(
                f"\n**{title}:**\n"
                + "\n".join(f"• {value}" for value in values[:20])
            )

    return "\n".join(lines)


def normalise_channel_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^[^A-Za-z0-9]+", "", value)
    value = value.replace("・", "-").replace("_", "-").replace(" ", "-")
    value = re.sub(r"-+", "-", value).strip("-")
    return value.casefold()


def duplicate_groups(items, normalizer):
    groups = {}
    for item in items:
        key = normalizer(item.name)
        if not key:
            continue
        groups.setdefault(key, []).append(item)
    return {
        key: values
        for key, values in groups.items()
        if len(values) > 1
    }


async def find_core_bot_messages(channel, marker):
    matches = []
    try:
        async for message in channel.history(limit=100):
            if message.author == channel.guild.me and message.content.startswith(marker):
                matches.append(message)
    except discord.HTTPException:
        pass
    return matches


async def server_audit(guild: discord.Guild):
    issues = []
    warnings = []
    ok = []

    # Duplicates
    role_dupes = duplicate_groups(
        [role for role in guild.roles if not role.is_default() and not role.managed],
        normalise_role_name,
    )
    text_dupes = duplicate_groups(guild.text_channels, normalise_channel_name)
    voice_dupes = duplicate_groups(guild.voice_channels, normalise_channel_name)
    category_dupes = duplicate_groups(guild.categories, normalise_channel_name)

    if role_dupes:
        for key, values in role_dupes.items():
            issues.append("Duplicate roles: " + ", ".join(role.name for role in values))
    else:
        ok.append("No duplicate normal roles")

    if text_dupes:
        for key, values in text_dupes.items():
            issues.append("Duplicate text channels: " + ", ".join(ch.name for ch in values))
    else:
        ok.append("No duplicate text channels")

    if voice_dupes:
        for key, values in voice_dupes.items():
            issues.append("Duplicate voice channels: " + ", ".join(ch.name for ch in values))
    else:
        ok.append("No duplicate voice channels")

    if category_dupes:
        for key, values in category_dupes.items():
            issues.append("Duplicate categories: " + ", ".join(ch.name for ch in values))
    else:
        ok.append("No duplicate categories")

    # Required roles
    role_bad = []
    for name in ROLE_SPECS:
        role, role_issues = role_audit(guild, name)
        if role_issues:
            role_bad.append(f"{role_display_name(name)}: {', '.join(role_issues)}")
    if role_bad:
        issues.extend("Role: " + x for x in role_bad)
    else:
        ok.append(f"All {len(ROLE_SPECS)} managed roles match spec")

    # Required categories
    for display_name in CATEGORY_NAMES.values():
        if not discord.utils.get(guild.categories, name=display_name):
            issues.append(f"Missing category: {display_name}")

    # Required text channels
    for base_name, display_name in CHANNEL_NAMES.items():
        channel = find_text(guild, base_name)
        if not channel:
            issues.append(f"Missing text channel: {display_name}")
        elif channel.name != display_name:
            warnings.append(f"Channel name differs: {channel.name} -> {display_name}")

    # Required voice channels
    for base_name, display_name in VOICE_NAMES.items():
        channel = (
            discord.utils.get(guild.voice_channels, name=display_name)
            or discord.utils.get(guild.voice_channels, name=base_name)
        )
        if not channel:
            issues.append(f"Missing voice channel: {display_name}")
        elif channel.name != display_name:
            warnings.append(f"Voice name differs: {channel.name} -> {display_name}")

    # Verification gate. New users should see only start-here, rules, verify.
    entry_names = {"start-here", "rules", "verify"}
    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue

        base_match = None
        for base_name in CHANNEL_NAMES:
            if find_text(guild, base_name) and find_text(guild, base_name).id == channel.id:
                base_match = base_name
                break

        everyone_can_view = channel.permissions_for(guild.default_role).view_channel
        if base_match in entry_names:
            if not everyone_can_view:
                issues.append(f"Entry channel hidden from @everyone: {channel.name}")
        else:
            if everyone_can_view:
                issues.append(f"Unverified users can still see: {channel.name}")

    # Read-only channels.
    member = find_role(guild, "Member")
    writer_roles = broadcast_writer_roles(guild)
    if member:
        for name in READ_ONLY_CHANNELS:
            channel = find_text(guild, name)
            if not channel:
                continue
            member_perms = channel.permissions_for(member)
            if not member_perms.view_channel:
                issues.append(f"Member cannot view read-only channel: {channel.name}")
            if member_perms.send_messages:
                issues.append(f"Member can write in read-only channel: {channel.name}")
            if member_perms.create_public_threads or member_perms.send_messages_in_threads:
                issues.append(f"Member can use threads in read-only channel: {channel.name}")

            for role in writer_roles:
                perms = channel.permissions_for(role)
                if not perms.view_channel or not perms.send_messages:
                    warnings.append(f"Staff role cannot post in {channel.name}: {role.name}")

    # Normal writable channels.
    for name in [
        "general", "clips-and-loot", "find-a-crew", "polls-and-events",
        "bug-reports", "suggestions",
    ]:
        channel = find_text(guild, name)
        if channel and member:
            perms = channel.permissions_for(member)
            if not perms.view_channel or not perms.send_messages:
                issues.append(f"Member cannot write in normal channel: {channel.name}")

    # Tester/private channels.
    tester = find_role(guild, "Tester")
    tester_chat = find_text(guild, "tester-chat")
    if tester_chat and member and tester:
        if tester_chat.permissions_for(member).view_channel:
            issues.append("Member can see tester-chat")
        tester_perms = tester_chat.permissions_for(tester)
        if not tester_perms.view_channel or not tester_perms.send_messages:
            issues.append("Tester cannot use tester-chat")

    for name in ["staff-chat", "mod-alerts", "bot-logs"]:
        channel = find_text(guild, name)
        if channel and member and channel.permissions_for(member).view_channel:
            issues.append(f"Member can see staff-only channel: {channel.name}")

    # Core messages and panels.
    core_checks = [
        ("start-here", "## 👋 Welcome to Smash & Steal"),
        ("rules", "## 📜 Smash & Steal Rules"),
        ("verify", "## ✅ Verify"),
        ("choose-roles", "## 🎭 Choose Your Roles"),
        ("open-ticket", "## 🎫 Support"),
    ]

    core_messages = {}
    for channel_name, marker in core_checks:
        channel = find_text(guild, channel_name)
        if not channel:
            continue
        messages = await find_core_bot_messages(channel, marker)
        core_messages[channel_name] = messages
        if not messages:
            issues.append(f"Missing core bot message in {channel.name}")
        elif len(messages) > 1:
            warnings.append(f"Duplicate core bot messages in {channel.name}: {len(messages)}")

    verify_messages = core_messages.get("verify", [])
    if verify_messages:
        verify_message = verify_messages[0]
        has_check = any(str(reaction.emoji) == "✅" for reaction in verify_message.reactions)
        if not has_check:
            issues.append("Verify message is missing ✅ reaction")
        if not verify_message.components:
            issues.append("Verify message is missing Get Member button")
        else:
            ok.append("Verify reaction/button present")

    role_messages = core_messages.get("choose-roles", [])
    if role_messages:
        if not role_messages[0].components:
            issues.append("choose-roles has no buttons")
        else:
            component_count = sum(len(row.children) for row in role_messages[0].components)
            if component_count < len(SELF_ROLES):
                issues.append(
                    f"choose-roles has only {component_count}/{len(SELF_ROLES)} role buttons"
                )
            else:
                ok.append(f"choose-roles has {component_count} buttons")

    # Welcome/goodbye + runtime flags
    welcome = find_text(guild, "welcome")
    goodbye = find_text(guild, "goodbye")
    if welcome and goodbye and ENABLE_MEMBER_EVENTS and bot.intents.members:
        ok.append("Welcome/goodbye member events enabled")
    else:
        issues.append(
            "Welcome/goodbye event system is not fully enabled "
            f"(channels={bool(welcome and goodbye)}, env={ENABLE_MEMBER_EVENTS}, intent={bot.intents.members})"
        )

    # Bot permissions relevant to this server.
    me = guild.me
    if me:
        required_bot_permissions = {
            "manage_roles": me.guild_permissions.manage_roles,
            "manage_channels": me.guild_permissions.manage_channels,
            "send_messages": me.guild_permissions.send_messages,
            "read_message_history": me.guild_permissions.read_message_history,
            "add_reactions": me.guild_permissions.add_reactions,
        }
        missing = [name for name, value in required_bot_permissions.items() if not value]
        if missing:
            issues.append("Bot missing guild permissions: " + ", ".join(missing))
        else:
            ok.append("Bot has required guild permissions")

    return {
        "issues": issues,
        "warnings": warnings,
        "ok": ok,
        "counts": {
            "roles": len(guild.roles),
            "categories": len(guild.categories),
            "text_channels": len(guild.text_channels),
            "voice_channels": len(guild.voice_channels),
            "members": guild.member_count,
        },
    }


def format_server_audit(result, max_items=35):
    counts = result["counts"]
    issues = result["issues"]
    warnings = result["warnings"]
    lines = [
        "## 🔎 Smash & Steal Server Audit",
        f"Roles: **{counts['roles']}** | Categories: **{counts['categories']}** | "
        f"Text: **{counts['text_channels']}** | Voice: **{counts['voice_channels']}**",
        f"Problems: **{len(issues)}** | Warnings: **{len(warnings)}**",
    ]

    if issues:
        lines.append(
            "\n**❌ Problems**\n"
            + "\n".join(f"• {item}" for item in issues[:max_items])
        )
    if warnings:
        lines.append(
            "\n**⚠️ Warnings**\n"
            + "\n".join(f"• {item}" for item in warnings[:max_items])
        )
    if not issues and not warnings:
        lines.append("\n✅ No problems found in the managed server configuration.")

    return "\n".join(lines)


@bot.tree.command(
    name="cleanup",
    description="Safely clean duplicate roles, channels and categories",
    guild=GUILD,
)
async def cleanup_cmd(interaction: discord.Interaction):
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
    report = await safe_cleanup_server(interaction.guild)
    audit = await server_audit(interaction.guild)
    content = (
        format_cleanup_report(report)
        + "\n\n"
        + format_server_audit(audit, max_items=20)
    )
    await interaction.edit_original_response(content=content[:1990])


@bot.tree.command(
    name="serveraudit",
    description="Audit channels, roles, permissions, verification and panels",
    guild=GUILD,
)
async def serveraudit_cmd(interaction: discord.Interaction):
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
    result = await server_audit(interaction.guild)
    await interaction.edit_original_response(content=format_server_audit(result))


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
        "`/rolesetup` force-fix role colours, emojis, permissions and order\n"
        "`/roleaudit` check every managed role\n"
        "`/entrysetup` fix verification gate and entry channels\n"
        "`/channelpermissions` enforce read-only channel permissions\n"
        "`/serveraudit` audit roles, channels, permissions and panels\n"
        "`/cleanup` safely clean duplicate roles/channels/categories\n"
        "`/kick`, `/ban`, `/unban`, `/timeout`, `/untimeout` moderation\n"
        "`/emojis` fix channel emoji names\n"
        "`/panels` post interactive panels\n"
        "`/status` bot health check",
        ephemeral=True,
    )


async def auto_sync_roles_on_startup():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("ROLE AUTO-SYNC | guild not found", flush=True)
        return

    me = guild.me
    if not me:
        print("ROLE AUTO-SYNC | bot member missing", flush=True)
        return

    print(
        f"ROLE AUTO-SYNC | bot_top={me.top_role.name} | manage_roles={me.guild_permissions.manage_roles}",
        flush=True,
    )

    ok = 0
    blocked = []
    for name, spec in ROLE_SPECS.items():
        role = find_role(guild, name)
        if role and role.managed:
            blocked.append(f"{name}: managed")
            continue
        if role and role >= me.top_role:
            blocked.append(f"{name}: above bot")
            continue
        try:
            await ensure_role(guild, name, spec["hoist"])
            ok += 1
            await asyncio.sleep(0.15)
        except Exception as exc:
            blocked.append(f"{name}: {type(exc).__name__}")

    print(
        f"ROLE AUTO-SYNC DONE | ok={ok}/{len(ROLE_SPECS)} | blocked={blocked}",
        flush=True,
    )


@bot.event
async def on_ready():
    global STARTUP_SYNC_DONE
    print(
        f"BOT READY | {bot.user} | guild={GUILD_ID} | member_events={ENABLE_MEMBER_EVENTS}",
        flush=True,
    )

    async with startup_sync_lock:
        if STARTUP_SYNC_DONE:
            return
        STARTUP_SYNC_DONE = True

        await auto_sync_roles_on_startup()

        guild = bot.get_guild(GUILD_ID)
        if guild:
            if RUN_CLEANUP_ON_START:
                try:
                    cleanup_report = await safe_cleanup_server(guild)
                    print(
                        "CLEANUP DONE | "
                        f"roles_deleted={len(cleanup_report['roles_deleted'])} | "
                        f"text_deleted={len(cleanup_report['text_deleted'])} | "
                        f"text_archived={len(cleanup_report['text_archived'])} | "
                        f"voice_deleted={len(cleanup_report['voice_deleted'])} | "
                        f"categories_deleted={len(cleanup_report['categories_deleted'])} | "
                        f"created={cleanup_report['created']} | "
                        f"skipped={cleanup_report['skipped']}",
                        flush=True,
                    )
                except Exception as exc:
                    print(
                        f"CLEANUP FAILED | {type(exc).__name__}: {exc}",
                        flush=True,
                    )

            try:
                await ensure_entry_system(guild)
                print("ENTRY AUTO-SYNC DONE", flush=True)

                audit = await server_audit(guild)
                print(
                    "SERVER AUDIT | "
                    f"issues={len(audit['issues'])} | "
                    f"warnings={len(audit['warnings'])} | "
                    f"counts={audit['counts']}",
                    flush=True,
                )
                for item in audit["issues"]:
                    print(f"SERVER AUDIT ISSUE | {item}", flush=True)
                for item in audit["warnings"]:
                    print(f"SERVER AUDIT WARNING | {item}", flush=True)
            except Exception as exc:
                print(
                    f"ENTRY AUTO-SYNC FAILED | {type(exc).__name__}: {exc}",
                    flush=True,
                )


bot.run(TOKEN, log_handler=None)
