import asyncio
import ast
import importlib.util
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from community_store import CommunityError, Store, code, validate
from integrate_community import integrate


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'community.sqlite3'
        self.db = Store(self.path)
        self.db.initialise()
        self.now = time.time()

    def create(self, kind='suggestion', author='10', source='m:100', **kwargs):
        return self.db.create(kind, '1', '2', author, 'Add a new district to the game',
                              ['Option one', 'Option two'] if kind == 'poll' else None,
                              source_id=source, now=self.now, **kwargs)

    def active(self, kind='suggestion'):
        item = self.create(kind)
        self.db.attach(item['id'], '300')
        return self.db.get(item['id'])

    def vote(self, item, user='10', choice=0, **kwargs):
        return self.db.vote(item['id'], user, choice, '1', '2', '300', now=kwargs.get('now', self.now))

    def test_separate_sequences(self):
        a = self.create()
        b = self.create('poll', source='i:102')
        self.assertEqual((code(a), code(b)), ('SUG-001', 'POLL-001'))

    def test_idempotent_source(self):
        self.assertEqual(self.create()['id'], self.create()['id'])
        self.assertEqual(self.db.stats()['suggestion'], 1)

    def test_cooldown_survives_restart(self):
        self.create()
        self.db = Store(self.path)
        self.db.initialise()
        with self.assertRaises(CommunityError):
            self.create(source='i:101')

    def test_cooldown_expiry(self):
        self.create()
        self.now += 61
        self.assertEqual(code(self.create(source='m:101')), 'SUG-002')

    def test_votes_survive_restart(self):
        item = self.active()
        self.vote(item)
        other = Store(self.path)
        other.initialise()
        result = other.get(item['id'])
        self.assertEqual(result['counts'], [1, 0])
        self.assertEqual(result['message_id'], '300')

    def test_repeat_not_duplicate(self):
        item = self.active()
        self.vote(item)
        self.vote(item)
        self.assertEqual(self.db.get(item['id'])['counts'], [1, 0])

    def test_change_vote(self):
        item = self.active()
        self.vote(item)
        self.vote(item, choice=1)
        self.assertEqual(self.db.get(item['id'])['counts'], [0, 1])

    def test_remove_vote(self):
        item = self.active()
        self.vote(item)
        self.vote(item, choice=-1)
        self.assertEqual(self.db.get(item['id'])['counts'], [0, 0])

    def test_concurrent_same_voter(self):
        item = self.active()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n: self.vote(item, choice=n % 2), range(40)))
        self.assertEqual(sum(self.db.get(item['id'])['counts']), 1)

    def test_concurrent_different_voters(self):
        item = self.active()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n: self.vote(item, user=str(n), choice=n % 2), range(20)))
        self.assertEqual(self.db.get(item['id'])['counts'], [10, 10])

    def test_reject_cross_guild_message(self):
        item = self.active()
        for context in [('9', '2', '300'), ('1', '9', '300'), ('1', '2', '999')]:
            with self.assertRaises(CommunityError):
                self.db.vote(item['id'], '10', 0, *context)
        self.assertEqual(self.db.stats()['votes'], 0)

    def test_bad_option(self):
        item = self.active()
        for option in [-2, 2, 300, True]:
            with self.assertRaises(CommunityError):
                self.vote(item, choice=option)

    def test_deadline_rejected_before_loop(self):
        item = self.active('poll')
        with self.assertRaises(CommunityError):
            self.vote(item, now=item['closes'])

    def test_overdue_poll_closes_after_restart(self):
        item = self.active('poll')
        other = Store(self.path)
        self.assertEqual(other.expire(now=item['closes'] + 1), 1)
        self.assertEqual(other.get(item['id'])['status'], 'closed')

    def test_status_locks_vote_preserves_counts(self):
        item = self.active()
        self.vote(item)
        self.db.decide(item['id'], 'accepted', '42', 'We will add it.', '1')
        with self.assertRaises(CommunityError):
            self.vote(item, choice=1)
        self.assertEqual(self.db.get(item['id'])['counts'], [1, 0])

    def test_wrong_status_type(self):
        item = self.active('poll')
        with self.assertRaises(CommunityError):
            self.db.decide(item['id'], 'accepted', '42', 'Not a suggestion.', '1')

    def test_reason_required(self):
        item = self.active()
        with self.assertRaises(CommunityError):
            self.db.decide(item['id'], 'denied', '42', '', '1')

    def test_cross_guild_status_denied(self):
        item = self.active()
        with self.assertRaises(CommunityError):
            self.db.decide(item['id'], 'accepted', '42', 'Testing cross guild.', '99')

    def test_dirty_revision_not_lost(self):
        item = self.active()
        self.vote(item)
        self.db.mark_rendered(item['id'], item['revision'])
        self.assertEqual(self.db.get(item['id'])['dirty'], 1)
        latest = self.db.get(item['id'])
        self.db.mark_rendered(item['id'], latest['revision'])
        self.assertEqual(self.db.get(item['id'])['dirty'], 0)

    def test_lookup(self):
        self.create()
        self.assertEqual(self.db.lookup('sug-001', 'suggestion')['number'], 1)
        with self.assertRaises(CommunityError):
            self.db.lookup('POLL-001', 'suggestion')

    def test_metadata_survives_restart(self):
        self.db.meta('panel', '123')
        self.assertEqual(Store(self.path).meta('panel'), '123')

    def test_removed_message_not_republished(self):
        item = self.active()
        self.db.missing(item['id'])
        self.assertEqual(self.db.rows(), [])
        with self.assertRaises(CommunityError):
            self.vote(item)

    def test_validation(self):
        for kind, text, options in [('suggestion', 'x', None), ('suggestion', 'x' * 1601, None),
                                    ('poll', 'Question here', ['one']), ('poll', 'Question here', ['A', 'a']),
                                    ('poll', 'Question here', ['x' * 81, 'b']), ('bad', 'Invalid kind', None)]:
            with self.assertRaises(CommunityError):
                validate(kind, text, options)
        self.assertEqual(self.db.stats()['integrity'], 'ok')


class IntegrationTests(unittest.TestCase):
    def test_idempotent_integration(self):
        source = 'TOKEN="test"\nbot=None\nbot.run(TOKEN, log_handler=None)\n'
        output = integrate(source)
        self.assertEqual(integrate(output), output)
        self.assertEqual(output.count('install_community(globals())'), 1)
        ast.parse(output)

    def test_unexpected_startup_fails_closed(self):
        with self.assertRaises(ValueError):
            integrate('print("unexpected entrypoint")')

    def test_only_startup_changes(self):
        source = '# Keep this code\nvalue = 42\nbot.run(TOKEN, log_handler=None)\n'
        self.assertTrue(integrate(source).startswith('# Keep this code\nvalue = 42\n'))


HAS_DISCORD = importlib.util.find_spec('discord') is not None
if os.environ.get('REQUIRE_DISCORD_TESTS') == '1' and not HAS_DISCORD:
    raise RuntimeError('discord.py is required for deployment tests')


@unittest.skipUnless(HAS_DISCORD, 'discord.py is not installed in this local test environment')
class DiscordTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import discord
        import community
        self.discord, self.community = discord, community
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Store(Path(self.tmp.name) / 'test.sqlite3')
        self.db.initialise()
        self.item = self.db.create('suggestion', 1, 2, 3, 'A new district to explore', source_id='m:44')

    async def test_views_are_persistent(self):
        view = self.community.VoteView(None, self.item)
        self.assertTrue(view.is_persistent())
        self.assertEqual(len({x.custom_id for x in view.children}), 3)
        self.assertTrue(self.community.SuggestPanel(None).is_persistent())

    async def test_closed_view_disabled(self):
        self.item['status'] = 'accepted'
        self.assertTrue(all(x.disabled for x in self.community.VoteView(None, self.item).children))

    async def test_ten_option_poll_fits(self):
        poll = self.db.create('poll', 1, 2, 3, 'Choose the next feature', [str(i) for i in range(10)], source_id='i:99')
        view = self.community.VoteView(None, poll)
        self.assertEqual(len(view.children), 11)
        self.assertEqual(len(view.to_components()), 3)
        embed = self.community.item_embed(poll)
        self.assertLess(len(embed), 6000)

    async def test_commands_register_once(self):
        client = self.discord.Client(intents=self.discord.Intents.none())
        client.tree = self.discord.app_commands.CommandTree(client)
        ns = dict(bot=client, GUILD_ID=1, find_role=lambda *a: None, find_text=lambda *a: None,
                  is_staff=lambda *a: False, send_mod_log=lambda *a, **k: None)
        c = self.community.install_community(ns)
        self.assertIs(c, self.community.install_community(ns))
        commands = client.tree.get_commands(guild=self.discord.Object(id=1))
        self.assertEqual(len(commands), 7)
        for command in commands:
            data = command.to_dict(client.tree)
            self.assertIn('name', data)
        self.assertIsNotNone(next(x for x in commands if x.name == 'poll').default_permissions)
        await client.close()

    async def test_member_cannot_moderate(self):
        class FakeMember:
            bot = False
            pending = False
            roles = ['member']
        c = self.community.Community(dict(bot=None, GUILD_ID=1,
                                         is_staff=lambda m: False,
                                         find_role=lambda *a: 'member'))
        c.ready = True
        with patch.object(self.community.discord, 'Member', FakeMember):
            c.authorise(FakeMember(), SimpleNamespace(id=1))
            with self.assertRaises(CommunityError):
                c.authorise(FakeMember(), SimpleNamespace(id=1), staff_only=True)

    async def test_unverified_and_cross_guild_rejected(self):
        class FakeMember:
            bot = False
            pending = False
            roles = []
        c = self.community.Community(dict(bot=None, GUILD_ID=1,
                                         is_staff=lambda m: False,
                                         find_role=lambda *a: 'member'))
        c.ready = True
        with patch.object(self.community.discord, 'Member', FakeMember):
            for gid in (1, 2):
                with self.assertRaises(CommunityError):
                    c.authorise(FakeMember(), SimpleNamespace(id=gid))

    async def test_mentions_disabled(self):
        self.assertNotIn('@everyone', self.community.safe('@everyone'))
        self.assertEqual(self.community.NONE.to_dict()['parse'], [])

    async def test_railway_requires_volume(self):
        c = self.community.Community(dict(bot=None, GUILD_ID=1))
        with patch.dict(os.environ, {'RAILWAY_ENVIRONMENT_ID': 'test'}, clear=True):
            with self.assertRaises(RuntimeError):
                await c.prepare()


if __name__ == '__main__':
    unittest.main()
