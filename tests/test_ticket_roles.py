import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config
import database as db


class TicketRoleDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        config.DATABASE_PATH = str(Path(self.temp_dir.name) / "economy.db")
        await db.init_db()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_category_supports_multiple_roles(self):
        await db.set_ticket_category(
            1, "Support", 100, 10, "Bienvenue", "🎫", role_ids=[10, 20, 10]
        )
        category = await db.get_ticket_category(1, "support")

        self.assertEqual(category["role_ids"], [10, 20])
        self.assertEqual(category["role_id"], 10)

        await db.update_ticket_category(1, "Support", role_ids=[20, 30])
        updated = await db.get_ticket_category(1, "Support")
        self.assertEqual(updated["role_ids"], [20, 30])
        self.assertEqual(updated["role_id"], 20)

    async def test_removing_category_removes_role_links(self):
        await db.set_ticket_category(
            1, "Partenariat", 100, 10, "Bienvenue", role_ids=[10, 20]
        )
        self.assertTrue(await db.remove_ticket_category(1, "Partenariat"))

        connection = sqlite3.connect(config.DATABASE_PATH)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM ticket_category_roles WHERE guild_id = 1"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 0)


class LegacyTicketRoleMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_single_role_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config.DATABASE_PATH = str(Path(temp_dir) / "legacy.db")
            connection = sqlite3.connect(config.DATABASE_PATH)
            connection.execute("""
                CREATE TABLE ticket_categories (
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    discord_category_id INTEGER NOT NULL,
                    role_id INTEGER,
                    message TEXT NOT NULL,
                    emoji TEXT,
                    PRIMARY KEY (guild_id, name)
                )
            """)
            connection.execute(
                "INSERT INTO ticket_categories VALUES (?, ?, ?, ?, ?, ?, ?)",
                (1, "support", "Support", 100, 55, "Bienvenue", "🎫"),
            )
            connection.commit()
            connection.close()

            await db.init_db()
            category = await db.get_ticket_category(1, "Support")

            self.assertEqual(category["role_ids"], [55])


if __name__ == "__main__":
    unittest.main()
