import os
import tempfile
import unittest

import config
import database as db


class RyukaiDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.previous_path = config.DATABASE_PATH
        config.DATABASE_PATH = self.path
        await db.init_db()

    async def asyncTearDown(self):
        config.DATABASE_PATH = self.previous_path
        os.unlink(self.path)

    async def test_profile_defaults_and_configuration_are_persisted(self):
        profile = await db.get_ryukai_profile(10, 20)
        self.assertEqual(profile["team"], "—")
        self.assertEqual(profile["war_wins"], 0)

        await db.set_ryukai_profile(10, 20, "S", "Fighter", "PC / Console", "EU")
        profile = await db.get_ryukai_profile(10, 20)
        self.assertEqual(profile["team"], "S")
        self.assertEqual(profile["rank_name"], "Fighter")
        self.assertEqual(profile["region"], "EU")

    async def test_war_result_updates_every_participant_and_keeps_categories_separate(self):
        result_id = await db.record_ryukai_result(20, "war", [10, 11], [12], 99, "2-1")
        self.assertGreater(result_id, 0)
        await db.record_ryukai_result(20, "pub_war", [12], [10], 99)
        await db.record_ryukai_result(20, "duel", [10], [12], 99)

        first = await db.get_ryukai_profile(10, 20)
        teammate = await db.get_ryukai_profile(11, 20)
        opponent = await db.get_ryukai_profile(12, 20)
        self.assertEqual((first["war_wins"], first["war_losses"]), (1, 0))
        self.assertEqual((teammate["war_wins"], teammate["war_losses"]), (1, 0))
        self.assertEqual((first["pub_war_wins"], first["pub_war_losses"]), (0, 1))
        self.assertEqual((first["duel_wins"], first["duel_losses"]), (1, 0))
        self.assertEqual((opponent["war_wins"], opponent["war_losses"]), (0, 1))
        self.assertEqual((opponent["pub_war_wins"], opponent["pub_war_losses"]), (1, 0))
        self.assertEqual((opponent["duel_wins"], opponent["duel_losses"]), (0, 1))

    async def test_result_rejects_a_member_on_both_sides(self):
        with self.assertRaises(ValueError):
            await db.record_ryukai_result(20, "war", [10], [10], 99)

