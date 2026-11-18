import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


import database as db


class GlobalBlacklistDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "blacklist.db")
        self.path_patch = patch("config.DATABASE_PATH", self.database_path)
        self.path_patch.start()
        await db.init_db()

    async def asyncTearDown(self):
        self.path_patch.stop()
        self.temp_dir.cleanup()

    async def test_blacklist_is_persistent_and_can_be_removed(self):
        added = await db.add_global_blacklist(99, "Raid", 42)
        self.assertEqual(added["user_id"], 99)
        self.assertEqual(added["reason"], "Raid")
        self.assertEqual((await db.get_global_blacklist_entry(99))["added_by"], 42)
        self.assertEqual(len(await db.get_global_blacklist()), 1)

        updated = await db.add_global_blacklist(99, "Raids répétés", 43)
        self.assertEqual(updated["reason"], "Raids répétés")
        self.assertEqual(updated["added_by"], 43)

        self.assertTrue(await db.remove_global_blacklist(99))
        self.assertIsNone(await db.get_global_blacklist_entry(99))
        self.assertFalse(await db.remove_global_blacklist(99))


if __name__ == "__main__":
    unittest.main()
