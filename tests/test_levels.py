import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import discord

from levels_store import (
    LevelStore,
    message_fingerprint,
    level_from_total,
    xp_for_next,
)
from levels_v1 import (
    REWARD_ROLES,
    LevelsV1,
    install_levels,
    next_reward,
    progress_bar,
    unlocked_rewards,
)


class LevelMathTests(unittest.TestCase):
    def test_level_zero(self):
        level, progress, needed = level_from_total(0)
        self.assertEqual((level, progress, needed), (0, 0, 100))

    def test_first_level(self):
        self.assertEqual(level_from_total(100)[:2], (1, 0))

    def test_multiple_levels(self):
        total = xp_for_next(0) + xp_for_next(1) + 10
        self.assertEqual(level_from_total(total)[:2], (2, 10))

    def test_negative_total_is_clamped(self):
        self.assertEqual(level_from_total(-100), (0, 0, 100))

    def test_progress_bar_length(self):
        self.assertEqual(len(progress_bar(50, 100)), 12)
        self.assertEqual(progress_bar(100, 100), "█" * 12)

    def test_fingerprint_normalizes_case_and_spaces(self):
        a = message_fingerprint(" Hello   WORLD ")
        b = message_fingerprint("hello world")
        self.assertEqual(a, b)

    def test_attachment_changes_fingerprint(self):
        self.assertNotEqual(
            message_fingerprint("", ["a.png"]),
            message_fingerprint("", ["b.png"]),
        )

    def test_reward_thresholds(self):
        self.assertEqual(unlocked_rewards(4), [])
        self.assertEqual(
            [reward[1] for reward in unlocked_rewards(20)],
            ["Active", "Regular", "Veteran"],
        )
        self.assertEqual(
            [reward[0] for reward in REWARD_ROLES],
            [5, 10, 20, 30, 50],
        )

    def test_next_reward(self):
        self.assertEqual(next_reward(0)[:2], (5, "Active"))
        self.assertEqual(next_reward(29)[:2], (30, "Elite"))
        self.assertIsNone(next_reward(50))


class LevelStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "levels.sqlite3"
        self.store = LevelStore(self.path)
        self.store.initialise()

    def test_award_xp(self):
        result = self.store.award("1", "10", "hash-a", now=1000)
        self.assertEqual(result["total_xp"], 20)

    def test_cooldown_blocks_fast_award(self):
        self.store.award("1", "10", "hash-a", now=1000)
        self.assertIsNone(
            self.store.award("1", "10", "hash-b", now=1050)
        )
        self.assertEqual(self.store.get("1", "10")["total_xp"], 20)

    def test_after_cooldown_awards(self):
        self.store.award("1", "10", "hash-a", now=1000)
        result = self.store.award("1", "10", "hash-b", now=1061)
        self.assertEqual(result["total_xp"], 40)

    def test_duplicate_message_blocked_for_ten_minutes(self):
        self.store.award("1", "10", "same", now=1000)
        self.assertIsNone(
            self.store.award("1", "10", "same", now=1100)
        )
        self.assertEqual(self.store.get("1", "10")["total_xp"], 20)

    def test_duplicate_allowed_after_window(self):
        self.store.award("1", "10", "same", now=1000)
        result = self.store.award("1", "10", "same", now=1601)
        self.assertEqual(result["total_xp"], 40)

    def test_level_up_detected(self):
        self.store.adjust("1", "10", 90, now=900)
        result = self.store.award("1", "10", "new", now=1000)
        self.assertTrue(result["leveled_up"])
        self.assertEqual(result["level"], 1)
        self.assertEqual(result["progress"], 10)

    def test_persistence_after_restart(self):
        self.store.adjust("1", "10", 777, now=1000)
        other = LevelStore(self.path)
        other.initialise()
        self.assertEqual(other.get("1", "10")["total_xp"], 777)

    def test_leaderboard_order(self):
        self.store.adjust("1", "10", 100)
        self.store.adjust("1", "20", 500)
        self.store.adjust("1", "30", 300)
        rows = self.store.leaderboard("1")
        self.assertEqual([row["user_id"] for row in rows], ["20", "30", "10"])

    def test_rank(self):
        self.store.adjust("1", "10", 100)
        self.store.adjust("1", "20", 500)
        self.assertEqual(self.store.get("1", "10")["rank"], 2)
        self.assertEqual(self.store.get("1", "20")["rank"], 1)

    def test_remove_does_not_go_negative(self):
        self.store.adjust("1", "10", 50)
        result = self.store.adjust("1", "10", -999)
        self.assertEqual(result["total_xp"], 0)

    def test_stats_integrity(self):
        self.store.adjust("1", "10", 100)
        stats = self.store.stats("1")
        self.assertEqual(stats["members"], 1)
        self.assertEqual(stats["total_xp"], 100)
        self.assertEqual(stats["integrity"], "ok")

    def test_persisted_levels_map(self):
        self.store.adjust("1", "10", 100)
        self.store.adjust("1", "20", 0)
        levels = self.store.levels("1")
        self.assertEqual(levels["10"], 1)
        self.assertEqual(levels["20"], 0)


class DiscordIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_commands_register(self):
        client = discord.Client(intents=discord.Intents.none())
        client.tree = discord.app_commands.CommandTree(client)
        ns = {
            "bot": client,
            "GUILD_ID": 1,
            "find_role": lambda *args: None,
            "find_text": lambda *args: None,
            "is_staff": lambda member: False,
            "send_mod_log": lambda *args, **kwargs: None,
        }
        controller = install_levels(ns)
        self.assertIs(controller, install_levels(ns))
        commands = client.tree.get_commands(guild=discord.Object(id=1))
        self.assertEqual(
            {command.name for command in commands},
            {"rank", "rewards", "leaderboard", "level-status", "xp-add", "xp-remove"},
        )
        await client.close()

    async def test_railway_requires_volume(self):
        client = discord.Client(intents=discord.Intents.none())
        controller = LevelsV1(
            {
                "bot": client,
                "GUILD_ID": 1,
                "find_role": lambda *args: None,
                "find_text": lambda *args: None,
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
