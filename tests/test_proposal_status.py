"""Tests du suivi public des propositions de giveaway et du regroupement des commandes de points."""

import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

import config
import database as db
from cogs import community_tools as ct


PROPOSAL = {"id": 7, "proposer_id": 500, "prize_name": "💎 Nitro", "prize_points": 50,
            "ticket_channel_id": 5, "status_message_id": 9001}


class EmbedTests(unittest.TestCase):
    def test_pending_approved_denied(self):
        pending = ct.build_proposal_status_embed(PROPOSAL, "Étoiles", "pending")
        self.assertEqual(pending.color.value, config.COLOR_ECONOMY)
        self.assertIn("En attente", pending.fields[2].value)
        self.assertIn("après validation", pending.fields[3].value)

        role = SimpleNamespace(mention="<@&10>")
        approved = ct.build_proposal_status_embed(PROPOSAL, "Étoiles", "approved", "<@1>", 70, [role])
        self.assertEqual(approved.color.value, config.COLOR_SUCCESS)
        text = " ".join(f.value for f in approved.fields)
        self.assertIn("70", text)
        self.assertIn("<@&10>", text)
        self.assertIn("<@1>", text)

        denied = ct.build_proposal_status_embed(PROPOSAL, "Étoiles", "denied", "<@1>")
        self.assertEqual(denied.color.value, config.COLOR_ERROR)
        self.assertIn("Aucun point", " ".join(f.value for f in denied.fields))


class UpdateMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_edits_status_message(self):
        message = MagicMock(); message.edit = AsyncMock()
        channel = MagicMock(spec=discord.TextChannel); channel.fetch_message = AsyncMock(return_value=message)
        guild = SimpleNamespace(get_channel=lambda i: channel)
        self.assertTrue(await ct.update_proposal_status_message(guild, PROPOSAL, "approved", "Étoiles", "<@1>", 70))
        channel.fetch_message.assert_awaited_once_with(9001)
        message.edit.assert_awaited_once()

    async def test_old_proposal_without_status_message_is_ignored(self):
        guild = SimpleNamespace(get_channel=lambda i: None)
        legacy = {**PROPOSAL, "status_message_id": None}
        self.assertFalse(await ct.update_proposal_status_message(guild, legacy, "denied", "Étoiles"))


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_message_column_is_added_to_existing_database(self):
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        with sqlite3.connect(path) as conn:  # table créée avant l'ajout de la colonne
            conn.execute(
                "CREATE TABLE giveaway_proposals (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, "
                "ticket_channel_id INTEGER NOT NULL, proposer_id INTEGER NOT NULL, prize_item_id INTEGER, "
                "prize_name TEXT NOT NULL, prize_points INTEGER NOT NULL CHECK(prize_points > 0), "
                "status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','denied')), "
                "created_at TEXT NOT NULL, reviewed_by INTEGER, reviewed_at TEXT, log_channel_id INTEGER, log_message_id INTEGER)"
            )
        previous = config.DATABASE_PATH
        config.DATABASE_PATH = path
        try:
            await db.init_db()
            pid = await db.create_giveaway_proposal({
                "guild_id": 1, "ticket_channel_id": 5, "proposer_id": 2, "prize_item_id": None,
                "prize_name": "x", "prize_points": 3,
            })
            await db.set_giveaway_proposal_status_message(pid, 1234)
            self.assertEqual((await db.get_giveaway_proposal(pid))["status_message_id"], 1234)
        finally:
            config.DATABASE_PATH = previous


class CommandGroupTests(unittest.TestCase):
    def test_points_commands_are_grouped(self):
        cog = ct.CommunityTools.__new__(ct.CommunityTools)
        public = {c.name for c in ct.CommunityTools.points.commands}
        admin = {c.name for c in ct.CommunityTools.points_admin.commands}
        self.assertEqual(public, {"profile", "roles"})
        self.assertEqual(admin, {"config", "add", "item-add", "item-list", "item-remove", "role-add", "role-remove"})
        self.assertEqual(ct.CommunityTools.points_admin.default_permissions.manage_guild, True)
        self.assertIsNone(ct.CommunityTools.points.default_permissions)


if __name__ == "__main__":
    unittest.main()
