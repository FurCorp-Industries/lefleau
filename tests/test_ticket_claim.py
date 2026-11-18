import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite

import database as db


class TicketClaimTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "tickets.db")
        self.path_patch = patch("config.DATABASE_PATH", self.database_path)
        self.path_patch.start()
        await db.init_db()

    async def asyncTearDown(self):
        self.path_patch.stop()
        self.temp_dir.cleanup()

    async def test_claim_and_unclaim_cycle(self):
        await db.create_ticket(channel_id=101, guild_id=10, user_id=20, category_name="Support")

        first_claim = await db.claim_ticket(101, 30)
        self.assertEqual(first_claim["status"], "ok")
        self.assertEqual(first_claim["ticket"]["claimed_by"], 30)
        self.assertIsNotNone(first_claim["ticket"]["claimed_at"])

        self.assertEqual((await db.claim_ticket(101, 30))["status"], "already_yours")
        other_staff = await db.claim_ticket(101, 40)
        self.assertEqual(other_staff["status"], "already_claimed")
        self.assertEqual(other_staff["ticket"]["claimed_by"], 30)

        unclaimed = await db.unclaim_ticket(101)
        self.assertEqual(unclaimed["status"], "ok")
        self.assertEqual(unclaimed["previous_claimant"], 30)
        ticket = await db.get_ticket_by_channel(101)
        self.assertIsNone(ticket["claimed_by"])
        self.assertIsNone(ticket["claimed_at"])
        self.assertEqual((await db.unclaim_ticket(101))["status"], "not_claimed")

    async def test_only_one_concurrent_claim_wins(self):
        await db.create_ticket(channel_id=102, guild_id=10, user_id=21, category_name="Aide")
        results = await asyncio.gather(db.claim_ticket(102, 31), db.claim_ticket(102, 41))
        statuses = [result["status"] for result in results]
        self.assertEqual(statuses.count("ok"), 1)
        self.assertEqual(statuses.count("already_claimed"), 1)

    async def test_tracking_status_is_preserved_for_claim_refresh(self):
        await db.start_tracking(
            channel_id=103,
            guild_id=10,
            status_channel_id=200,
            status_message_id=300,
            tracked_by=31,
            status="examen",
        )
        self.assertEqual((await db.get_tracked_ticket(103))["status"], "examen")
        await db.update_tracked_ticket_status(103, "acceptee")
        self.assertEqual((await db.get_tracked_ticket(103))["status"], "acceptee")

    async def test_existing_database_is_migrated_without_losing_tickets(self):
        legacy_path = str(Path(self.temp_dir.name) / "legacy.db")
        async with aiosqlite.connect(legacy_path) as connection:
            await connection.execute(
                "CREATE TABLE tickets ("
                "channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, "
                "user_id INTEGER NOT NULL, category_name TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            await connection.execute(
                "INSERT INTO tickets VALUES (104, 10, 22, 'support', '2026-01-01T00:00:00+00:00')"
            )
            await connection.execute(
                "CREATE TABLE tracked_tickets ("
                "channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, "
                "status_channel_id INTEGER NOT NULL, status_message_id INTEGER NOT NULL, "
                "tracked_by INTEGER NOT NULL, tracked_at TEXT NOT NULL)"
            )
            await connection.commit()

        with patch("config.DATABASE_PATH", legacy_path):
            await db.init_db()
            ticket = await db.get_ticket_by_channel(104)
            self.assertEqual(ticket["user_id"], 22)
            self.assertIsNone(ticket["claimed_by"])
            self.assertIsNone(ticket["claimed_at"])


if __name__ == "__main__":
    unittest.main()
