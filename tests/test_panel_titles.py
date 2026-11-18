"""Titres de serveurs du panel : balisage, chargement du bundle et route statique."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("PANEL_CLIENT_ID", "1")
os.environ.setdefault("PANEL_CLIENT_SECRET", "x")
os.environ.setdefault("PANEL_SESSION_SECRET", "y")

from aiohttp import web

from cogs import web_panel as wp


class TitleMarkupTests(unittest.TestCase):
    def test_server_title_escapes_the_name(self):
        html = wp.server_title('Evil "<b>name</b>" & co')
        self.assertNotIn("<b>", html)
        self.assertIn("&lt;b&gt;name&lt;/b&gt;", html)
        # Le texte reste dans la page quand le script ne se charge pas.
        self.assertIn('class="rt-title__text"', html)

    def test_assets_are_only_loaded_on_pages_with_titles(self):
        panel = wp.WebPanel(MagicMock())
        with_titles = panel._page("T", "<p>x</p>", None, titles=True).text
        without_titles = panel._page("T", "<p>x</p>", None).text
        self.assertIn(f"{wp.PREFIX}/static/refracted-titles.js?v=", with_titles)
        self.assertIn(f"{wp.PREFIX}/static/refracted-titles.css?v=", with_titles)
        self.assertNotIn("refracted-titles", without_titles)


class FakeIcon:
    """Imite discord.Asset : replace() renvoie un objet portant l'URL demandée."""

    def replace(self, size, format):
        return SimpleNamespace(url=f"https://cdn.example/icons/1.{format}?size={size}&x=<y>")


class GuildIconTests(unittest.TestCase):
    def test_uses_a_small_static_lazy_webp(self):
        html = wp.guild_icon(SimpleNamespace(id=1, name="Le Fléau", icon=FakeIcon()), 128)
        self.assertIn("1.webp?size=128", html)
        self.assertIn('loading="lazy"', html)
        self.assertIn('width="128"', html)
        self.assertNotIn("<y>", html)  # l'URL est échappée

    def test_initials_fallback_without_icon(self):
        html = wp.guild_icon(SimpleNamespace(id=361, name="one piece <b>", icon=None))
        self.assertIn(">OP<", html)
        self.assertIn("hsl(1 42% 30%)", html)  # teinte stable : id % 360
        self.assertNotIn("<img", html)
        self.assertEqual(wp.guild_icon(SimpleNamespace(id=2, name="", icon=None)).count("?"), 1)


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_cards_use_icons_and_plain_titles_without_the_webgl_bundle(self):
        guilds = [
            SimpleNamespace(id=1, name="Les Fléaux <Des Mers>", icon=FakeIcon(), member_count=257),
            SimpleNamespace(id=2, name="Abyss Nexus", icon=None, member_count=154),
        ]
        bot = MagicMock()
        bot.guilds = guilds
        panel = wp.WebPanel(bot)
        panel._require_session = lambda request: {"uid": "1", "name": "M", "csrf": "t", "exp": 9**10}

        async def allowed(user_id, guild):
            return True

        panel._can_access_guild = allowed
        html = (await panel.dashboard(SimpleNamespace())).text
        self.assertIn("Les Fléaux &lt;Des Mers&gt;", html)
        self.assertIn("1.webp?size=128", html)
        self.assertIn(">AN<", html)
        self.assertNotIn("rt-title", html.split("</style>", 1)[1])
        self.assertNotIn("refracted-titles", html)


class StaticRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.panel = wp.WebPanel(MagicMock())

    def request(self, name):
        return SimpleNamespace(match_info={"name": name})

    async def test_serves_the_bundle_with_long_cache(self):
        response = await self.panel.static_file(self.request("refracted-titles.js"))
        self.assertEqual(response.headers["Content-Type"], "application/javascript")
        self.assertIn("immutable", response.headers["Cache-Control"])

    async def test_refuses_unknown_files_and_traversal(self):
        for name in ("other.js", "../web_panel.py", "..%2Fweb_panel.py", "refracted-titles.js/../x"):
            with self.assertRaises(web.HTTPNotFound):
                await self.panel.static_file(self.request(name))

    async def test_security_headers_keep_the_asset_cache(self):
        async def handler(request):
            return web.Response(text="x", headers={"Cache-Control": "public, max-age=60"})

        response = await self.panel.security_headers(self.request("x"), handler)
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=60")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

        async def plain(request):
            return web.Response(text="x")

        response = await self.panel.security_headers(self.request("x"), plain)
        self.assertEqual(response.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
