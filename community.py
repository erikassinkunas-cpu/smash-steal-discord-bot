"""Suggestions V2 and polls. Install once before the existing Client.run call."""
import asyncio
import logging
import os
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from community_store import CommunityError, Store, code, validate

LOG = logging.getLogger('sas.community')
NONE = discord.AllowedMentions.none()
LABELS = {'open': 'New', 'accepted': 'Accepted', 'planned': 'Planned',
          'denied': 'Denied', 'closed': 'Closed', 'removed': 'Removed'}
COLOURS = {'open': 0x5865F2, 'accepted': 0x57F287, 'planned': 0xFEE75C,
           'denied': 0xED4245, 'closed': 0x95A5A6, 'removed': 0x95A5A6}


def safe(value):
    return discord.utils.escape_mentions(str(value))


def footer(item):
    return f'SAS Community V2 | {code(item)} | item:{item["id"]}'


def voting_open(item):
    return item['status'] == 'open' and (item['closes'] is None or time.time() < item['closes'])


def item_embed(item):
    label = LABELS[item['status']]
    if item['kind'] == 'poll' and item['status'] == 'open':
        label = 'Open'
    title = f'{"💡" if item["kind"] == "suggestion" else "📊"} {code(item)} | {label}'
    embed = discord.Embed(title=title, description=safe(item['body']),
                          colour=COLOURS[item['status']])
    embed.add_field(name='Author', value=f'<@{item["author_id"]}>', inline=True)
    total = sum(item['counts'])
    if item['kind'] == 'suggestion':
        embed.add_field(name='Votes', value=f'👍 {item["counts"][0]}   👎 {item["counts"][1]}', inline=True)
    else:
        for index, (option, count) in enumerate(zip(item['choices'], item['counts']), 1):
            percent = round(count / total * 100) if total else 0
            embed.add_field(name=f'{index}. {safe(option)}', value=f'{count} votes ({percent}%)', inline=False)
        embed.add_field(name='Total voters', value=str(total), inline=True)
        embed.add_field(name='Voting ends', value=f'<t:{int(item["closes"])}:F>', inline=True)
    if item['reason']:
        embed.add_field(name='Staff decision' if item['kind'] == 'suggestion' else 'Closed',
                        value=safe(item['reason']), inline=False)
    if item['source_id'] and item['source_id'].startswith('m:'):
        mid = item['source_id'][2:]
        embed.add_field(name='Original suggestion',
                        value=f'[Open message](https://discord.com/channels/{item["guild_id"]}/{item["channel_id"]}/{mid})', inline=False)
    embed.set_footer(text=footer(item))
    return embed


async def respond(interaction, text):
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True, allowed_mentions=NONE)
    else:
        await interaction.response.send_message(text, ephemeral=True, allowed_mentions=NONE)


class VoteButton(discord.ui.Button):
    def __init__(self, controller, item, choice, label, emoji=None, row=0):
        super().__init__(label=label, emoji=emoji, row=row,
                         style=discord.ButtonStyle.secondary,
                         custom_id=f'sas:community:v1:{item["id"]}:{choice}',
                         disabled=not voting_open(item))
        self.controller, self.item_id, self.choice = controller, item['id'], choice

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            self.controller.authorise(interaction.user, interaction.guild)
            if interaction.message is None:
                raise CommunityError('Use the original voting message.')
            answer = await asyncio.to_thread(self.controller.store.vote,
                                             self.item_id, interaction.user.id, self.choice,
                                             interaction.guild_id, interaction.channel_id,
                                             interaction.message.id)
            await respond(interaction, answer + ' Totals refresh within a few seconds.')
        except CommunityError as exc:
            await respond(interaction, str(exc))
        except Exception:
            LOG.exception('VOTE FAILED item=%s', self.item_id)
            await respond(interaction, 'The vote could not be saved. Please try again.')


class VoteView(discord.ui.View):
    def __init__(self, controller, item):
        super().__init__(timeout=None)
        if item['kind'] == 'suggestion':
            self.add_item(VoteButton(controller, item, 0, 'Support', '👍'))
            self.add_item(VoteButton(controller, item, 1, 'Oppose', '👎'))
            remove_row = 0
        else:
            for index, label in enumerate(item['choices']):
                self.add_item(VoteButton(controller, item, index, f'{index + 1}. {label}'[:80], row=index // 5))
            remove_row = 2
        self.add_item(VoteButton(controller, item, -1, 'Remove my vote', row=remove_row))


class SuggestModal(discord.ui.Modal, title='New Smash & Steal suggestion'):
    idea = discord.ui.TextInput(label='Your suggestion', style=discord.TextStyle.paragraph,
                               min_length=10, max_length=1600, required=True,
                               placeholder='Explain what should change and why.')

    def __init__(self, controller):
        super().__init__(timeout=300)
        self.controller = controller

    async def on_submit(self, interaction):
        await self.controller.submit_suggestion(interaction, str(self.idea.value))


class SuggestPanel(discord.ui.View):
    def __init__(self, controller):
        super().__init__(timeout=None)
        self.controller = controller

    @discord.ui.button(label='Submit suggestion', emoji='💡', style=discord.ButtonStyle.primary,
                       custom_id='sas:community:new-suggestion:v1')
    async def new_suggestion(self, interaction, button):
        try:
            self.controller.authorise(interaction.user, interaction.guild)
            await interaction.response.send_modal(SuggestModal(self.controller))
        except CommunityError as exc:
            await respond(interaction, str(exc))


class Community:
    def __init__(self, ns):
        self.ns, self.bot, self.guild_id = ns, ns['bot'], ns['GUILD_ID']
        self.store = None
        self.ready = False
        self.start_lock = asyncio.Lock()
        self.render_lock = asyncio.Lock()
        self.retry_at = {}
        self.hints = {}

    def authorise(self, member, guild, staff_only=False):
        if not self.ready:
            raise CommunityError('The community features are starting. Try again shortly.')
        if guild is None or guild.id != self.guild_id or not isinstance(member, discord.Member) or member.bot:
            raise CommunityError('Use this command in the Smash & Steal server.')
        if member.pending:
            raise CommunityError('Accept the server rules and verify first.')
        staff = self.ns['is_staff'](member)
        if staff_only:
            if not staff:
                raise CommunityError('Only the server team can do this.')
        elif not staff:
            role = self.ns['find_role'](guild, 'Member')
            if role is None or role not in member.roles:
                raise CommunityError('Verify and get the Member role first.')

    def target_channel(self, kind):
        guild = self.bot.get_guild(self.guild_id)
        key = 'suggestions' if kind == 'suggestion' else 'polls-and-events'
        channel = self.ns['find_text'](guild, key) if guild else None
        if channel is None:
            raise CommunityError(f'The {key} channel is missing. Contact the server team.')
        perms = channel.permissions_for(guild.me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links and perms.read_message_history):
            raise CommunityError(f'The bot needs View Channel, Send Messages, Embed Links and Read Message History in {key}.')
        return channel

    async def prepare(self):
        mount = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH')
        if os.environ.get('RAILWAY_ENVIRONMENT_ID') and not mount:
            raise RuntimeError('A persistent Railway volume is required for community voting.')
        path = Path(mount or os.environ.get('COMMUNITY_DATA_DIR', 'data')) / 'community.sqlite3'
        self.store = Store(path)
        await asyncio.to_thread(self.store.initialise)
        await asyncio.to_thread(self.store.expire)
        rows = await asyncio.to_thread(self.store.rows)
        self.bot.add_view(SuggestPanel(self))
        for item in rows:
            if item['message_id']:
                self.bot.add_view(VoteView(self, item), message_id=int(item['message_id']))
        LOG.info('COMMUNITY STORAGE path=%s persistent=%s restored=%s', path, bool(mount), len(rows))

    async def upsert_panel(self, channel, marker, content, view=None):
        stored = await asyncio.to_thread(self.store.meta, marker)
        message = None
        if stored:
            try:
                message = await channel.fetch_message(int(stored))
            except discord.NotFound:
                pass
        if message is None:
            async for candidate in channel.history(limit=100):
                if candidate.author.id == self.bot.user.id and candidate.content.startswith(marker):
                    message = candidate
                    break
        text = marker + '\n' + content
        if message is None:
            message = await channel.send(text, view=view, allowed_mentions=NONE)
        else:
            await message.edit(content=text, view=view, allowed_mentions=NONE)
        await asyncio.to_thread(self.store.meta, marker, message.id)

    async def start(self):
        async with self.start_lock:
            if self.ready:
                return
            suggestions = self.target_channel('suggestion')
            polls = self.target_channel('poll')
            await self.upsert_panel(
                suggestions, '## 💡 Suggestions V2',
                'Post a new message here, use **/suggest**, or press the button below.\n'
                'Every idea gets a **SUG ID** and **👍 / 👎 voting buttons**.\n'
                'One vote per Member. Change or remove your vote at any time while voting is open.\n'
                'Reply to a message for discussion; replies are not new suggestions. Original messages are kept.\n'
                'One new suggestion per minute. Staff can mark ideas **Accepted**, **Planned** or **Denied** with a reason.\n'
                'These decisions close voting. Votes inform the team; they do not promise an implementation date.',
                SuggestPanel(self))
            await self.upsert_panel(
                polls, '## 📊 Community Polls',
                'The server team creates polls with **/poll**. Verified Members vote using the numbered buttons.\n'
                'Each account has one vote per poll. You can change it or choose **Remove my vote**.\n'
                'Polls support **2 to 10 options** and run for **1 to 168 hours**. The default is 24 hours.\n'
                'They close automatically at their deadline. Staff can also use **/poll-close**.\n'
                'Counts are visible to everyone who can view this channel; votes are stored for counting.')
            self.ready = True
            if not self.maintenance.is_running():
                self.maintenance.start()
            stats = await asyncio.to_thread(self.store.stats)
            LOG.info('COMMUNITY READY suggestions_channel=%s polls_channel=%s stats=%s', suggestions.id, polls.id, stats)

    async def refresh(self, item_id):
        async with self.render_lock:
            item = await asyncio.to_thread(self.store.get, item_id)
            channel = self.bot.get_channel(int(item['channel_id']))
            if channel is None or getattr(channel, 'guild', None) is None or channel.guild.id != self.guild_id:
                raise CommunityError('The destination channel is unavailable.')
            message = None
            if item['message_id']:
                try:
                    message = await channel.fetch_message(int(item['message_id']))
                except discord.NotFound:
                    await asyncio.to_thread(self.store.missing, item_id)
                    return None
            else:
                # Recover the send/commit crash window without reposting the same item.
                async for candidate in channel.history(limit=100):
                    if candidate.author.id == self.bot.user.id and any(e.footer.text == footer(item) for e in candidate.embeds):
                        message = candidate
                        break
            if message is None:
                kwargs = {}
                if item['source_id'] and item['source_id'].startswith('m:'):
                    kwargs['reference'] = discord.MessageReference(
                        message_id=int(item['source_id'][2:]), channel_id=channel.id, fail_if_not_exists=False)
                message = await channel.send(embed=item_embed(item), view=VoteView(self, item),
                                             allowed_mentions=NONE, **kwargs)
                await asyncio.to_thread(self.store.attach, item_id, message.id)
            else:
                await message.edit(embed=item_embed(item), view=VoteView(self, item), allowed_mentions=NONE)
                if item['message_id'] is None:
                    await asyncio.to_thread(self.store.attach, item_id, message.id)
            await asyncio.to_thread(self.store.mark_rendered, item_id, item['revision'])
            self.retry_at.pop(item_id, None)
            return message

    async def create_item(self, kind, user, body, source_id, choices=None, hours=24):
        channel = self.target_channel(kind)
        item = await asyncio.to_thread(self.store.create, kind, self.guild_id, channel.id,
                                      user.id, body, choices, hours, source_id)
        try:
            message = await self.refresh(item['id'])
            suffix = message.jump_url if message else 'Stored; the voting message is unavailable.'
        except (discord.HTTPException, CommunityError):
            LOG.exception('PUBLISH PENDING item=%s', item['id'])
            suffix = 'Saved. Publishing is pending; the bot will retry.'
        return f'**{code(item)}**: {suffix}'

    async def submit_suggestion(self, interaction, text):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            self.authorise(interaction.user, interaction.guild)
            answer = await self.create_item('suggestion', interaction.user, text, f'i:{interaction.id}')
            await respond(interaction, answer)
        except CommunityError as exc:
            await respond(interaction, str(exc))
        except Exception:
            LOG.exception('SUGGESTION FAILED')
            await respond(interaction, 'The suggestion could not be saved. Please try again.')

    async def on_message(self, message):
        if not self.ready or message.guild is None or message.guild.id != self.guild_id or message.author.bot or message.webhook_id or message.reference:
            return
        channel = self.ns['find_text'](message.guild, 'suggestions')
        if channel is None or message.channel.id != channel.id:
            return
        try:
            self.authorise(message.author, message.guild)
            validate('suggestion', message.content)
            await self.create_item('suggestion', message.author, message.content, f'm:{message.id}')
        except CommunityError as exc:
            now = time.monotonic()
            if now - self.hints.get(message.author.id, 0) >= 30:
                self.hints[message.author.id] = now
                await message.reply(str(exc), mention_author=False, allowed_mentions=NONE)
        except Exception:
            LOG.exception('AUTO SUGGESTION FAILED message=%s', message.id)

    @tasks.loop(seconds=5)
    async def maintenance(self):
        try:
            await asyncio.to_thread(self.store.expire)
            for item in await asyncio.to_thread(self.store.rows, True):
                if time.monotonic() < self.retry_at.get(item['id'], 0):
                    continue
                try:
                    await self.refresh(item['id'])
                except (discord.HTTPException, CommunityError):
                    self.retry_at[item['id']] = time.monotonic() + 60
                    LOG.warning('COMMUNITY refresh deferred item=%s', item['id'])
        except Exception:
            LOG.exception('COMMUNITY MAINTENANCE FAILED')

    async def suggest(self, interaction: discord.Interaction, text: str):
        await self.submit_suggestion(interaction, text)

    async def change_status(self, interaction, item_code, status, reason, kind='suggestion'):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            self.authorise(interaction.user, interaction.guild, staff_only=True)
            item = await asyncio.to_thread(self.store.lookup, item_code, kind)
            await asyncio.to_thread(self.store.decide, item['id'], status, interaction.user.id, reason, self.guild_id)
            try:
                await self.refresh(item['id'])
            except (discord.HTTPException, CommunityError):
                LOG.warning('STATUS display pending item=%s', item['id'])
            await respond(interaction, f'**{code(item)}** marked **{LABELS[status]}**. The decision is saved.')
            await self.ns['send_mod_log'](
                interaction.guild, '💡 Community decision',
                f'{code(item)} set to {LABELS[status]} by {interaction.user.id}.',
                fields=[('Reason', safe(reason), False)])
        except CommunityError as exc:
            await respond(interaction, str(exc))
        except Exception:
            LOG.exception('STATUS FAILED')
            await respond(interaction, 'A status update failed. Check the item before retrying.')

    async def suggest_accept(self, interaction: discord.Interaction, suggestion_id: str, reason: str):
        await self.change_status(interaction, suggestion_id, 'accepted', reason)

    async def suggest_deny(self, interaction: discord.Interaction, suggestion_id: str, reason: str):
        await self.change_status(interaction, suggestion_id, 'denied', reason)

    async def suggest_planned(self, interaction: discord.Interaction, suggestion_id: str, reason: str):
        await self.change_status(interaction, suggestion_id, 'planned', reason)

    async def poll(self, interaction: discord.Interaction, question: str, options: str,
                   hours: app_commands.Range[int, 1, 168] = 24):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            self.authorise(interaction.user, interaction.guild, staff_only=True)
            answer = await self.create_item('poll', interaction.user, question, f'i:{interaction.id}',
                                            options.split('|'), int(hours))
            await respond(interaction, answer)
        except CommunityError as exc:
            await respond(interaction, str(exc))
        except Exception:
            LOG.exception('POLL CREATE FAILED')
            await respond(interaction, 'The poll could not be saved. Please try again.')

    async def poll_close(self, interaction: discord.Interaction, poll_id: str,
                         reason: str = 'Closed by the server team.'):
        await self.change_status(interaction, poll_id, 'closed', reason, 'poll')

    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            self.authorise(interaction.user, interaction.guild, staff_only=True)
            stats = await asyncio.to_thread(self.store.stats)
            await respond(interaction, f'Community V2: **online**\nSuggestions: {stats.get("suggestion", 0)}\n'
                          f'Polls: {stats.get("poll", 0)}\nVotes: {stats["votes"]}\n'
                          f'Pending display updates: {stats["pending"]}\nDatabase check: {stats["integrity"]}')
        except CommunityError as exc:
            await respond(interaction, str(exc))


def install_community(ns):
    """Register with the existing bot, preserving every pre-existing event handler."""
    if '_community_v2' in ns:
        return ns['_community_v2']
    required = ('bot', 'GUILD_ID', 'find_role', 'find_text', 'is_staff', 'send_mod_log')
    if any(name not in ns for name in required):
        raise RuntimeError('The base bot is missing a required community integration hook.')
    if not LOG.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s %(name)s %(message)s'))
        LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False
    controller = Community(ns)
    bot = ns['bot']
    guild = discord.Object(id=ns['GUILD_ID'])
    specs = [
        ('suggest', 'Submit a game suggestion (10 to 1600 characters)', controller.suggest, False),
        ('suggest-accept', 'Accept a suggestion and record the reason', controller.suggest_accept, True),
        ('suggest-deny', 'Decline a suggestion and record the reason', controller.suggest_deny, True),
        ('suggest-planned', 'Mark a suggestion as planned', controller.suggest_planned, True),
        ('poll', 'Create a poll. Separate 2 to 10 options with |', controller.poll, True),
        ('poll-close', 'Close a poll early', controller.poll_close, True),
        ('community-status', 'Check community voting and storage', controller.status, True),
    ]
    for name, description, callback, staff_only in specs:
        command = app_commands.Command(name=name, description=description, callback=callback)
        if staff_only:
            command.default_permissions = discord.Permissions(manage_messages=True)
        bot.tree.add_command(command, guild=guild)

    original_setup = bot.setup_hook
    original_ready = getattr(bot, 'on_ready', None)
    original_message = getattr(bot, 'on_message', None)

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
            LOG.exception('COMMUNITY START FAILED')

    @bot.event
    async def on_message(message):
        if original_message:
            await original_message(message)
        await controller.on_message(message)

    ns['_community_v2'] = controller
    return controller
