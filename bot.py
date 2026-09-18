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
ENABLE_MEMBER_EVENTS = os.environ.get("ENABLE_MEMBER_EVENTS", "0") == "1"

intents = discord.Intents.default()
intents.guilds = True
intents.reactions = True
intents.members = ENABLE_MEMBER_EVENTS


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
            ticket_emoji = TICKET_EMOJIS.get(self.ticket_type, "🎫")
            channel = await guild.create_text_channel(
                f"{ticket_emoji}・{self.ticket_type}-{safe_name(user.display_name)}",
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
setup_lock = asyncio.Lock()
startup_sync_lock = asyncio.Lock()
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
        "channels": 28,
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


async def allow_bot(channel):
    if channel.guild.me:
        await channel.set_permissions(
            channel.guild.me,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            add_reactions=True,
            manage_messages=True,
            manage_channels=True,
        )


async def set_hidden_until_member(channel, read_only=False):
    guild = channel.guild
    await channel.set_permissions(guild.default_role, view_channel=False)
    for role in access_roles(guild):
        await channel.set_permissions(
            role,
            view_channel=True,
            read_message_history=True,
            send_messages=False if read_only else True,
        )
    await allow_bot(channel)


async def set_staff_only(channel):
    guild = channel.guild
    await channel.set_permissions(guild.default_role, view_channel=False)
    member = find_role(guild, "Member")
    if member:
        await channel.set_permissions(member, view_channel=False)
    for role in staff_roles(guild):
        await channel.set_permissions(
            role,
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            connect=True if isinstance(channel, discord.VoiceChannel) else None,
            speak=True if isinstance(channel, discord.VoiceChannel) else None,
        )
    await allow_bot(channel)


async def set_tester_only(channel):
    guild = channel.guild
    await channel.set_permissions(guild.default_role, view_channel=False)
    for role in access_roles(guild):
        await channel.set_permissions(role, view_channel=False)
    tester = find_role(guild, "Tester")
    if tester:
        if isinstance(channel, discord.VoiceChannel):
            await channel.set_permissions(tester, view_channel=True, connect=True, speak=True)
        else:
            await channel.set_permissions(
                tester,
                view_channel=True,
                read_message_history=True,
                send_messages=True,
            )
    for role in staff_roles(guild):
        if isinstance(channel, discord.VoiceChannel):
            await channel.set_permissions(role, view_channel=True, connect=True, speak=True)
        else:
            await channel.set_permissions(
                role,
                view_channel=True,
                read_message_history=True,
                send_messages=True,
            )
    await allow_bot(channel)


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
        await channel.set_permissions(
            guild.default_role,
            view_channel=True,
            read_message_history=True,
            send_messages=False,
            add_reactions=(channel == verify),
        )
        for role in access_roles(guild):
            await channel.set_permissions(
                role,
                view_channel=True,
                read_message_history=True,
                send_messages=False,
                add_reactions=(channel == verify),
            )
        await allow_bot(channel)

    if choose_roles:
        await set_hidden_until_member(choose_roles, read_only=True)

    read_only = [
        "announcements", "sneak-peeks", "update-log", "hall-of-fame",
        "help-and-faq", "open-ticket", "test-info", "known-issues",
        "welcome", "goodbye",
    ]
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

    for name in ["staff-chat", "mod-alerts", "bot-logs"]:
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
            await channel.set_permissions(guild.default_role, view_channel=False)
            for role in access_roles(guild):
                await channel.set_permissions(role, view_channel=True, connect=True, speak=True)

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
    special = {x.id for x in [choose_roles, tester_chat, playtest_room, team_room] if x}

    for channel in guild.channels:
        if isinstance(channel, discord.CategoryChannel):
            continue
        if channel.id in entry_ids or channel.id in special:
            continue
        if channel.category and channel.category.name in {"🔒 TEAM", "🎫 TICKETS"}:
            continue
        await channel.set_permissions(guild.default_role, view_channel=False)


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
    if not ENABLE_MEMBER_EVENTS or member.guild.id != GUILD_ID or member.bot:
        return

    channel = find_text(member.guild, "goodbye")
    if not channel:
        return

    embed = discord.Embed(
        title="👋 Goodbye",
        description=f"**{member.display_name}** left the server.",
        colour=discord.Colour(0xED4245),
    )
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


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
            try:
                await ensure_entry_system(guild)
                print("ENTRY AUTO-SYNC DONE", flush=True)
            except Exception as exc:
                print(
                    f"ENTRY AUTO-SYNC FAILED | {type(exc).__name__}: {exc}",
                    flush=True,
                )


bot.run(TOKEN, log_handler=None)
