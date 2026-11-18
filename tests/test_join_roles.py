"""Tests des rôles d'arrivée (/autorole)."""

import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

import config
import database as db
from cogs import join_roles as jr
from utils.role_checks import role_assign_problem


class FakeRole:
    def __init__(self, role_id, position, managed=False):
        self.id, self.position, self.managed = role_id, position, managed
        self.mention = f"<@&{role_id}>"
        self.name = f"role{role_id}"

    def is_default(self):
        return self.id == 1

    def __ge__(self, other):
        return self.position >= other.position

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return self.id


EVERYONE, LOW, OTHER, HIGH, BOT_ROLE = FakeRole(1, 0), FakeRole(10, 1), FakeRole(11, 1), FakeRole(12, 9), FakeRole(99, 5)
ROLES = {r.id: r for r in (EVERYONE, LOW, OTHER, HIGH, BOT_ROLE)}


def make_guild(can_manage=True):
    me = SimpleNamespace(guild_permissions=SimpleNamespace(manage_roles=can_manage), top_role=BOT_ROLE)
    return SimpleNamespace(id=42, me=me, get_role=ROLES.get, get_channel=lambda i: None, owner_id=1)


def make_member(guild, bot=False, pending=False, roles=()):
    member = MagicMock()
    member.guild, member.bot, member.pending, member.roles = guild, bot, pending, list(roles)
    member.id = 500
    member.add_roles = AsyncMock()
    return member


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous = config.DATABASE_PATH
        config.DATABASE_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
        await db.init_db()

    async def asyncTearDown(self):
        config.DATABASE_PATH = self.previous

    async def test_add_update_remove(self):
        await db.add_join_role(1, 10, "all", 7)
        await db.add_join_role(1, 10, "bots", 7)  # mise à jour, pas de doublon
        await db.add_join_role(1, 11, "humans", 7)
        rules = await db.get_join_roles(1)
        self.assertEqual({(r["role_id"], r["target"]) for r in rules}, {(10, "bots"), (11, "humans")})
        self.assertEqual(await db.get_join_roles(2), [])
        self.assertTrue(await db.remove_join_role(1, 10))
        self.assertFalse(await db.remove_join_role(1, 10))

    async def test_invalid_target_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            await db.add_join_role(1, 10, "everyone", 7)

    async def test_screening_setting_defaults_to_waiting(self):
        self.assertTrue((await db.get_join_role_settings(1))["wait_screening"])
        await db.set_join_role_wait_screening(1, False)
        self.assertFalse((await db.get_join_role_settings(1))["wait_screening"])
        await db.set_join_role_wait_screening(1, True)
        self.assertTrue((await db.get_join_role_settings(1))["wait_screening"])


class ApplyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous = config.DATABASE_PATH
        config.DATABASE_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
        await db.init_db()
        self.cog = jr.JoinRoles(MagicMock())
        self.guild = make_guild()

    async def asyncTearDown(self):
        config.DATABASE_PATH = self.previous

    async def test_target_filtering(self):
        await db.add_join_role(42, 10, "humans", 1)
        await db.add_join_role(42, 11, "bots", 1)
        human, robot = make_member(self.guild), make_member(self.guild, bot=True)
        self.assertEqual(await self.cog.apply_join_roles(human), [LOW])
        self.assertEqual(await self.cog.apply_join_roles(robot), [OTHER])
        human.add_roles.assert_awaited_once()

    async def test_target_all_applies_to_everyone(self):
        await db.add_join_role(42, 10, "all", 1)
        for bot in (False, True):
            self.assertEqual(await self.cog.apply_join_roles(make_member(self.guild, bot=bot)), [LOW])

    async def test_already_held_and_missing_roles_are_skipped(self):
        await db.add_join_role(42, 10, "all", 1)
        await db.add_join_role(42, 777, "all", 1)  # rôle supprimé
        member = make_member(self.guild, roles=[LOW])
        self.assertEqual(await self.cog.apply_join_roles(member), [])
        member.add_roles.assert_not_awaited()

    async def test_unsafe_role_is_skipped(self):
        await db.add_join_role(42, 12, "all", 1)  # au-dessus du rôle du bot
        member = make_member(self.guild)
        self.assertEqual(await self.cog.apply_join_roles(member), [])
        member.add_roles.assert_not_awaited()

    async def test_waits_for_screening_by_default(self):
        await db.add_join_role(42, 10, "all", 1)
        member = make_member(self.guild, pending=True)
        self.assertEqual(await self.cog.apply_join_roles(member), [])
        self.assertEqual(await self.cog.apply_join_roles(member, after_screening=True), [LOW])

    async def test_screening_wait_can_be_disabled(self):
        await db.add_join_role(42, 10, "all", 1)
        await db.set_join_role_wait_screening(42, False)
        self.assertEqual(await self.cog.apply_join_roles(make_member(self.guild, pending=True)), [LOW])

    async def test_discord_errors_are_swallowed(self):
        await db.add_join_role(42, 10, "all", 1)
        for error in (discord.NotFound(MagicMock(status=404), "x"), discord.Forbidden(MagicMock(status=403), "x")):
            member = make_member(self.guild)
            member.add_roles = AsyncMock(side_effect=error)
            self.assertEqual(await self.cog.apply_join_roles(member), [])

    async def test_listeners(self):
        member = make_member(self.guild)
        with patch.object(self.cog, "apply_join_roles", AsyncMock()) as apply:
            await self.cog.on_member_join(member)
            apply.assert_awaited_once_with(member)
            apply.reset_mock()
            before, after = make_member(self.guild, pending=True), make_member(self.guild, pending=False)
            await self.cog.on_member_update(before, after)
            apply.assert_awaited_once_with(after, after_screening=True)
            apply.reset_mock()
            await self.cog.on_member_update(after, after)  # pas de changement de statut
            apply.assert_not_awaited()


class StructureTests(unittest.TestCase):
    def test_group_commands_and_permissions(self):
        names = {c.name for c in jr.JoinRoles.autorole.commands}
        self.assertEqual(names, {"add", "remove", "list", "screening"})
        self.assertTrue(jr.JoinRoles.autorole.default_permissions.manage_roles)

    def test_role_assign_problem(self):
        guild = make_guild()
        admin = SimpleNamespace(top_role=HIGH)
        self.assertIn("everyone", role_assign_problem(guild, EVERYONE))
        self.assertIn("intégration", role_assign_problem(guild, FakeRole(20, 1, managed=True)))
        self.assertIn("sous le rôle", role_assign_problem(guild, HIGH))
        self.assertIn("permission", role_assign_problem(make_guild(can_manage=False), LOW))
        self.assertIn("rôle principal", role_assign_problem(guild, OTHER, SimpleNamespace(top_role=LOW)))
        self.assertIsNone(role_assign_problem(guild, LOW, admin))
        self.assertIsNone(role_assign_problem(guild, OTHER, SimpleNamespace(top_role=LOW), privileged=True))


if __name__ == "__main__":
    unittest.main()
