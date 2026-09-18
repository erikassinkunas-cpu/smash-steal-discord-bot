import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import discord

from moderation_store import ModerationError, ModerationStore
from moderation_v2 import ModerationV2, classify_message, install_moderation, timeout_minutes


class ModerationStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "moderation.sqlite3"
        self.store = ModerationStore(self.path)
        self.store.initialise()

    def add(self, user="10", reason="Testing warning reason", source="manual"):
        return self.store.add_warning("1", user, "99", reason, source, now=time.time())

    def test_add_warning_increments_active_count(self):
        first, count1 = self.add()
        second, count2 = self.add(reason="Another valid warning reason")
        self.assertGreater(second["id"], first["id"])
        self.assertEqual((count1, count2), (1, 2))

    def test_persists_after_restart(self):
        warning, _ = self.add()
        other = ModerationStore(self.path)
        other.initialise()
        rows = other.list_warnings("1", "10")
        self.assertEqual(rows[0]["id"], warning["id"])

    def test_clear_single_warning(self):
        warning, _ = self.add()
        self.add(reason="Second persistent warning")
        self.assertTrue(self.store.clear_warning("1", "10", warning["id"], "99"))
        self.assertEqual(self.store.active_count("1", "10"), 1)

    def test_clear_wrong_member_does_not_clear(self):
        warning, _ = self.add()
        self.assertFalse(self.store.clear_warning("1", "11", warning["id"], "99"))
        self.assertEqual(self.store.active_count("1", "10"), 1)

    def test_clear_all(self):
        self.add()
        self.add(reason="Second persistent warning")
        self.assertEqual(self.store.clear_all("1", "10", "99"), 2)
        self.assertEqual(self.store.active_count("1", "10"), 0)

    def test_inactive_history_can_be_read(self):
        warning, _ = self.add()
        self.store.clear_warning("1", "10", warning["id"], "99")
        self.assertEqual(self.store.list_warnings("1", "10"), [])
        history = self.store.list_warnings("1", "10", active_only=False)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["active"], 0)

    def test_invalid_reason_rejected(self):
        with self.assertRaises(ModerationError):
            self.store.add_warning("1", "10", "99", "x", "manual")

    def test_stats_integrity(self):
        self.add()
        stats = self.store.stats()
        self.assertEqual(stats["active_warnings"], 1)
        self.assertEqual(stats["members_with_warnings"], 1)
        self.assertEqual(stats["integrity"], "ok")


class AutoModRuleTests(unittest.TestCase):
    def test_clean_message_allowed(self):
        self.assertIsNone(classify_message("hello everyone"))

    def test_mass_mentions(self):
        rule = classify_message("hey", mention_total=5)
        self.assertEqual(rule[0], "mass-mention")

    def test_everyone_mention(self):
        rule = classify_message("@everyone hi", mention_everyone=True)
        self.assertEqual(rule[0], "mass-mention")

    def test_new_account_link(self):
        rule = classify_message("https://example.com", account_age_hours=12)
        self.assertEqual(rule[0], "new-account-link")

    def test_old_account_normal_link_allowed(self):
        self.assertIsNone(
            classify_message("https://example.com", account_age_hours=1000)
        )

    def test_scam_phrase_with_link(self):
        rule = classify_message(
            "claim your reward https://example.com",
            account_age_hours=1000,
        )
        self.assertEqual(rule[0], "scam-link")

    def test_scam_phrase_without_link_allowed(self):
        self.assertIsNone(
            classify_message("someone said free robux is fake", account_age_hours=1000)
        )

    def test_two_invites_same_message(self):
        rule = classify_message(
            "discord.gg/abc discord.gg/xyz",
            account_age_hours=1000,
            invite_recent=1,
        )
        self.assertEqual(rule[0], "invite-spam")

    def test_single_invite_old_account_allowed(self):
        self.assertIsNone(
            classify_message(
                "discord.gg/abc",
                account_age_hours=1000,
                invite_recent=1,
            )
        )

    def test_repeated_invites_trigger(self):
        rule = classify_message(
            "discord.gg/abc",
            account_age_hours=1000,
            invite_recent=3,
        )
        self.assertEqual(rule[0], "invite-spam")

    def test_flood_trigger(self):
        rule = classify_message("spam", flood_count=6)
        self.assertEqual(rule[0], "flood")

    def test_warning_escalation(self):
        expected = {
            0: 0,
            1: 0,
            2: 0,
            3: 10,
            4: 10,
            5: 60,
            6: 60,
            7: 1440,
            12: 1440,
        }
        for warnings, minutes in expected.items():
            with self.subTest(warnings=warnings):
                self.assertEqual(timeout_minutes(warnings), minutes)


class DiscordIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_commands_register(self):
        client = discord.Client(intents=discord.Intents.none())
        client.tree = discord.app_commands.CommandTree(client)
        ns = {
            "bot": client,
            "GUILD_ID": 1,
            "is_staff": lambda member: False,
            "send_mod_log": lambda *args, **kwargs: None,
        }
        controller = install_moderation(ns)
        self.assertIs(controller, install_moderation(ns))
        commands = client.tree.get_commands(guild=discord.Object(id=1))
        self.assertEqual(
            {command.name for command in commands},
            {"warn", "warnings", "clearwarn", "automod-status"},
        )
        await client.close()

    async def test_railway_requires_volume(self):
        client = discord.Client(intents=discord.Intents.none())
        controller = ModerationV2(
            {
                "bot": client,
                "GUILD_ID": 1,
                "is_staff": lambda member: False,
                "send_mod_log": lambda *args, **kwargs: None,
            }
        )
        with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT_ID": "test"}, clear=True):
            with self.assertRaises(RuntimeError):
                await controller.prepare()
        await client.close()


if __name__ == "__main__":
    unittest.main()
