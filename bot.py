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


ROLE_SPECS = {
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
            "view_audit_log": True,
            "manage_channels": True,
            "manage_webhooks": True,
            "manage_threads": True,
        },
    },
    "Community Manager": {
        "emoji": "🛡️",
        "colour": 0x9B59B6,
        "hoist": True,
        "permissions": {
            "view_audit_log": True,
            "manage_channels": True,
            "manage_messages": True,
            "manage_threads": True,
            "manage_nicknames": True,
            "moderate_members": True,
            "manage_events": True,
        },
    },
    "Moderator": {
        "emoji": "🔨",
        "colour": 0xE74C3C,
        "hoist": True,
        "permissions": {
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
            "manage_messages": True,
            "manage_threads": True,
        },
    },
    "Tester": {
        "emoji": "🧪",
        "colour": 0x1ABC9C,
        "hoist": True,
        "permissions": {},
    },
    "Early Crew": {
        "emoji": "💎",
        "colour": 0xE67E22,
        "hoist": True,
        "permissions": {},
    },
    "Bug Hunter": {
        "emoji": "🐛",
        "colour": 0x7CB342,
        "hoist": False,
        "permissions": {},
    },
    "Content Creator": {
        "emoji": "🎬",
        "colour": 0xE91E63,
        "hoist": False,
        "permissions": {},
    },
    "Contributor": {
        "emoji": "💡",
        "colour": 0x00BCD4,
        "hoist": False,
        "permissions": {},
    },
    "Member": {
        "emoji": "✅",
        "colour": 0x95A5A6,
        "hoist": False,
        "permissions": {},
    },
    "Update Ping": {
        "emoji": "📢",
        "colour": 0x5865F2,
        "hoist": False,
        "permissions": {},
    },
    "Playtest Ping": {
        "emoji": "🧪",
        "colour": 0x57F287,
        "hoist": False,
        "permissions": {},
    },
    "Event Ping": {
        "emoji": "🎉",
        "colour": 0xFEE75C,
        "hoist": False,
        "permissions": {},
    },
    "Sneak Peek Ping": {
        "emoji": "👀",
        "colour": 0xEB459E,
        "hoist": False,
        "permissions": {},
    },
    "PC": {
        "emoji": "🖥️",
        "colour": 0x607D8B,
        "hoist": False,
        "permissions": {},
    },
    "Mobile": {
        "emoji": "📱",
        "colour": 0x4CAF50,
        "hoist": False,
        "permissions": {},
    },
    "Console": {
        "emoji": "🎮",
        "colour": 0x673AB7,
        "hoist": False,
        "permissions": {},
    },
}

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

STAFF_ROLE_NAMES = {"Founder", "Developer", "Community Manager", "Moderator"}


CHANNEL_NAMES = {
    "start-here": "👋・start-here",
    "rules": "📜・rules",
    "verify": "✅・verify",
    "choose-roles": "🎭・choose-roles",
    "announcements": "📢・announcements",
    "sneak-peeks": "👀・sneak-peeks",
    "update-log": "📝・update-log",
    "general": "💬・general",
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
    return f"{spec['emoji']} {name}"


def find_role(guild: discord.Guild, name: str) -> Optional[discord.Role]:
    display_name = role_display_name(name)
    return (
        discord.utils.get(guild.roles, name=display_name)
        or discord.utils.get(guild.roles, name=name)
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


def build_permissions(spec):
    permissions = discord.Permissions.none()
    for permission_name, enabled in spec.get("permissions", {}).items():
        if hasattr(permissions, permission_name):
            setattr(permissions, permission_name, enabled)
    return permissions


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
        return await existing.edit(**kwargs)

    return await guild.create_role(**kwargs)


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
        "channels": 26,
        "permissions": 2,
    }
    done = {key: 0 for key in totals}

    async def tick(current: str, force: bool = False):
        if progress:
            await progress(done.copy(), totals, current, force)

    await tick("Starting setup...", True)

    for name, hoist in ROLE_DEFS.items():
        existed = find_role(guild, name)
        role = await ensure_role(guild, name, hoist)
        if not existed:
            created.append(f"role:{role.name}")
        done["roles"] += 1
        await tick(f"Role: {role.name}")

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
    description="Apply Smash & Steal role names, colours and permissions",
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
    updated = []
    failed = []
    skipped = []

    for name, spec in ROLE_SPECS.items():
        role = find_role(guild, name)
        if role and role.managed:
            skipped.append(f"{name} (managed role)")
            continue

        if role and guild.me and role >= guild.me.top_role:
            failed.append(f"{name} (role is above or equal to the bot role)")
            continue

        try:
            result = await ensure_role(guild, name, spec["hoist"])
            updated.append(result.name)
            await asyncio.sleep(0.25)
        except discord.Forbidden:
            failed.append(f"{name} (Missing Access / Manage Roles)")
        except discord.HTTPException as exc:
            failed.append(f"{name} (HTTP {exc.status})")

    role_icons = "ROLE_ICONS" in guild.features
    lines = [
        "## ✅ Role setup finished",
        f"Updated or created: **{len(updated)}**",
        f"Skipped: **{len(skipped)}**",
        f"Failed: **{len(failed)}**",
        "",
        f"Actual Discord role icons available: **{'Yes' if role_icons else 'No'}**",
        "Every managed role still gets an emoji in its role name.",
    ]

    if failed:
        lines.append(
            "\n**Could not update:**\n"
            + "\n".join(f"• {item}" for item in failed[:20])
        )
    if skipped:
        lines.append(
            "\n**Skipped:**\n"
            + "\n".join(f"• {item}" for item in skipped[:20])
        )

    await interaction.followup.send("\n".join(lines), ephemeral=True)


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
        "`/rolesetup` apply role colours, emojis and permissions\n"
        "`/emojis` fix channel emoji names\n"
        "`/panels` post interactive panels\n"
        "`/status` bot health check",
        ephemeral=True,
    )


@bot.event
async def on_ready():
    print(f"BOT READY | {bot.user} | guild={GUILD_ID}", flush=True)


bot.run(TOKEN, log_handler=None)
