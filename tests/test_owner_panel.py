import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import discord
from aiohttp import web
from discord.ext import commands

import config
from cogs.owner_panel import COOKIE_NAME, OwnerPanel


class OwnerPanelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        config.OWNER_PANEL_SESSION_SECRET = "test-secret"
        config.OWNER_PANEL_USER_IDS = {42}

    def test_session_is_limited_to_declared_owners(self):
        panel = OwnerPanel(commands.Bot(command_prefix="!", intents=discord.Intents.none()))
        valid = panel._encode_session({
            "uid": "42", "name": "Owner", "csrf": "x", "exp": int(time.time()) + 60
        })
        denied = panel._encode_session({
            "uid": "43", "name": "Intrus", "csrf": "x", "exp": int(time.time()) + 60
        })

        self.assertEqual(panel._decode_session(valid)["uid"], "42")
        self.assertIsNone(panel._decode_session(denied))
        self.assertIsNone(panel._decode_session(valid + "altéré"))

    async def test_owner_http_routes_start(self):
        config.OWNER_PANEL_ENABLED = True
        config.OWNER_PANEL_CLIENT_ID = "client-id"
        config.OWNER_PANEL_CLIENT_SECRET = "client-secret"
        config.OWNER_PANEL_HOST = "127.0.0.1"
        config.OWNER_PANEL_PORT = 0
        panel = OwnerPanel(commands.Bot(command_prefix="!", intents=discord.Intents.none()))

        await panel.cog_load()
        try:
            routes = {route.resource.canonical for route in panel.runner.app.router.routes()}
            self.assertIn("/", routes)
            self.assertIn("/auth/callback", routes)
            self.assertIn("/dashboard", routes)
            self.assertIn("/blacklist", routes)
            self.assertIn("/blacklist/add", routes)
            self.assertIn("/blacklist/{user_id}/remove", routes)
            self.assertIn("/guild/{guild_id}", routes)
            self.assertIn("/guild/{guild_id}/invite", routes)
            self.assertIn("/guild/{guild_id}/delete-channels", routes)
            self.assertIn("/guild/{guild_id}/leave", routes)
        finally:
            await panel.cog_unload()

    async def test_invite_is_temporary_and_single_use(self):
        bot = Mock()
        panel = OwnerPanel(bot)
        session = panel._encode_session({
            "uid": "42", "name": "Owner", "csrf": "token", "exp": int(time.time()) + 60
        })
        permissions = SimpleNamespace(view_channel=True, create_instant_invite=True)
        channel = SimpleNamespace(
            permissions_for=Mock(return_value=permissions),
            create_invite=AsyncMock(return_value=SimpleNamespace(url="https://discord.gg/test")),
        )
        guild = SimpleNamespace(id=1, me=object(), text_channels=[channel])
        bot.get_guild.return_value = guild

        request = SimpleNamespace(
            match_info={"guild_id": "1"},
            cookies={COOKIE_NAME: session},
            post=AsyncMock(return_value={"csrf": "token"}),
        )
        with self.assertRaises(web.HTTPFound) as redirect:
            await panel.create_guild_invite(request)

        channel.create_invite.assert_awaited_once()
        arguments = channel.create_invite.await_args.kwargs
        self.assertEqual(arguments["max_age"], 600)
        self.assertEqual(arguments["max_uses"], 1)
        self.assertIn("discord.gg%2Ftest", redirect.exception.location)

    async def test_leaving_a_guild_requires_its_exact_name(self):
        bot = Mock()
        panel = OwnerPanel(bot)
        session = panel._encode_session({
            "uid": "42", "name": "Owner", "csrf": "token", "exp": int(time.time()) + 60
        })
        guild = SimpleNamespace(id=1, name="Serveur Démo", leave=AsyncMock())
        bot.get_guild.return_value = guild

        wrong_request = SimpleNamespace(
            match_info={"guild_id": "1"},
            cookies={COOKIE_NAME: session},
            post=AsyncMock(return_value={"csrf": "token", "confirmation": "Mauvais nom"}),
        )
        with self.assertRaises(web.HTTPBadRequest):
            await panel.leave_guild(wrong_request)
        guild.leave.assert_not_awaited()

        valid_request = SimpleNamespace(
            match_info={"guild_id": "1"},
            cookies={COOKIE_NAME: session},
            post=AsyncMock(return_value={"csrf": "token", "confirmation": "Serveur Démo"}),
        )
        with self.assertRaises(web.HTTPFound) as redirect:
            await panel.leave_guild(valid_request)

        guild.leave.assert_awaited_once()
        self.assertTrue(redirect.exception.location.startswith("/dashboard?"))

    async def test_deleting_channels_requires_both_confirmations_and_deletes_categories_last(self):
        bot = Mock()
        panel = OwnerPanel(bot)
        session = panel._encode_session({
            "uid": "42", "name": "Owner", "csrf": "token", "exp": int(time.time()) + 60
        })
        deletion_order = []

        async def delete_text(**kwargs):
            deletion_order.append("text")

        async def delete_category(**kwargs):
            deletion_order.append("category")

        text_channel = SimpleNamespace(
            id=10,
            name="général",
            type=discord.ChannelType.text,
            delete=AsyncMock(side_effect=delete_text),
        )
        category = SimpleNamespace(
            id=20,
            name="Informations",
            type=discord.ChannelType.category,
            delete=AsyncMock(side_effect=delete_category),
        )
        guild = SimpleNamespace(
            id=1,
            name="Serveur Démo",
            channels=[category, text_channel],
        )
        bot.get_guild.return_value = guild

        wrong_request = SimpleNamespace(
            match_info={"guild_id": "1"},
            cookies={COOKIE_NAME: session},
            post=AsyncMock(return_value={
                "csrf": "token",
                "confirmation": "Serveur Démo",
                "destructive_confirmation": "SUPPRIMER",
            }),
        )
        with self.assertRaises(web.HTTPBadRequest):
            await panel.delete_guild_channels(wrong_request)
        text_channel.delete.assert_not_awaited()
        category.delete.assert_not_awaited()

        valid_request = SimpleNamespace(
            match_info={"guild_id": "1"},
            cookies={COOKIE_NAME: session},
            post=AsyncMock(return_value={
                "csrf": "token",
                "confirmation": "Serveur Démo",
                "destructive_confirmation": "SUPPRIMER 1",
            }),
        )
        with self.assertRaises(web.HTTPFound) as redirect:
            await panel.delete_guild_channels(valid_request)

        self.assertEqual(deletion_order, ["text", "category"])
        self.assertTrue(redirect.exception.location.startswith("/guild/1?"))

    async def test_blacklist_requires_confirmation_and_protects_owner_ids(self):
        bot = Mock()
        bot.user = SimpleNamespace(id=500)
        panel = OwnerPanel(bot)
        session = panel._encode_session({
            "uid": "42", "name": "Owner", "csrf": "token", "exp": int(time.time()) + 60
        })

        wrong_request = SimpleNamespace(
            cookies={COOKIE_NAME: session},
            post=AsyncMock(return_value={
                "csrf": "token", "user_id": "99", "reason": "Raid",
                "confirmation": "BLACKLIST",
            }),
        )
        with self.assertRaises(web.HTTPBadRequest):
            await panel.add_blacklist_entry(wrong_request)

        protected_request = SimpleNamespace(
            cookies={COOKIE_NAME: session},
            post=AsyncMock(return_value={
                "csrf": "token", "user_id": "42", "reason": "Erreur",
                "confirmation": "BLACKLIST 42",
            }),
        )
        with self.assertRaises(web.HTTPBadRequest):
            await panel.add_blacklist_entry(protected_request)

    async def test_blacklist_is_saved_and_applied_to_all_guilds(self):
        bot = Mock()
        bot.user = SimpleNamespace(id=500)
        panel = OwnerPanel(bot)
        panel._ban_user_everywhere = AsyncMock(return_value=(3, 1))
        session = panel._encode_session({
            "uid": "42", "name": "Owner", "csrf": "token", "exp": int(time.time()) + 60
        })
        request = SimpleNamespace(
            cookies={COOKIE_NAME: session},
            post=AsyncMock(return_value={
                "csrf": "token", "user_id": "99", "reason": "Raids répétés",
                "confirmation": "BLACKLIST 99",
            }),
        )

        with patch("cogs.owner_panel.db.add_global_blacklist", new=AsyncMock()) as save:
            with self.assertRaises(web.HTTPFound) as redirect:
                await panel.add_blacklist_entry(request)

        save.assert_awaited_once_with(99, "Raids répétés", 42)
        panel._ban_user_everywhere.assert_awaited_once_with(99, "Raids répétés")
        self.assertTrue(redirect.exception.location.startswith("/blacklist?"))

    async def test_blacklisted_member_is_banned_when_joining(self):
        panel = OwnerPanel(Mock())
        panel._ban_user_from_guild = AsyncMock(return_value=True)
        member = SimpleNamespace(id=99, guild=SimpleNamespace(id=1))

        with patch(
            "cogs.owner_panel.db.get_global_blacklist_entry",
            new=AsyncMock(return_value={"user_id": 99, "reason": "Blacklist globale"}),
        ):
            await panel.on_member_join(member)

        panel._ban_user_from_guild.assert_awaited_once_with(
            member.guild, 99, "Blacklist globale"
        )


if __name__ == "__main__":
    unittest.main()
