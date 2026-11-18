"""Liaison sécurisée Discord ↔ Roblox via OAuth 2.0 Authorization Code + PKCE."""

import base64
import hashlib
import html
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import aiohttp
import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands

import config
import database as db

logger = logging.getLogger("onepiece-bot.roblox")

AUTHORIZE_URL = "https://apis.roblox.com/oauth/v1/authorize"
TOKEN_URL = "https://apis.roblox.com/oauth/v1/token"
USERINFO_URL = "https://apis.roblox.com/oauth/v1/userinfo"


def _page(title: str, message: str, success: bool = False) -> str:
    color = "#43d17a" if success else "#ff647c"
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#090b10;color:#f4f6fb;
font:16px/1.6 system-ui}}main{{width:min(620px,calc(100% - 48px));padding:36px;border:1px solid #252b38;
border-radius:18px;background:#11151e}}h1{{margin:0 0 12px;color:{color}}}p{{color:#bdc4d3}}a{{color:#aa98ff}}</style>
</head><body><main><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>
<p>Vous pouvez fermer cette page et retourner sur Discord.</p><a href="/privacy/">Confidentialité</a></main></body></html>"""


class RobloxLink(commands.Cog):

    roblox = app_commands.Group(name="roblox", description="Liaison des comptes Roblox", guild_only=True)
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.session: aiohttp.ClientSession | None = None
        self.web_oauth_states: dict[str, dict[str, str | datetime]] = {}

    async def cog_load(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        if not config.ROBLOX_CLIENT_ID or not config.ROBLOX_CLIENT_SECRET:
            logger.warning("OAuth Roblox désactivé : ROBLOX_CLIENT_ID/ROBLOX_CLIENT_SECRET manquant.")
            return
        app = web.Application(client_max_size=1024 * 1024)
        app.router.add_get("/roblox/login", self.web_login)
        app.router.add_get("/roblox/callback", self.oauth_callback)
        app.router.add_get("/roblox/health", self.health)
        self.runner = web.AppRunner(app, access_log=logger)
        await self.runner.setup()
        site = web.TCPSite(self.runner, config.ROBLOX_WEB_HOST, config.ROBLOX_WEB_PORT)
        await site.start()
        logger.info("Service OAuth Roblox actif sur %s:%s", config.ROBLOX_WEB_HOST, config.ROBLOX_WEB_PORT)

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()
        if self.session:
            await self.session.close()

    @staticmethod
    def configured() -> bool:
        return bool(config.ROBLOX_CLIENT_ID and config.ROBLOX_CLIENT_SECRET)

    async def health(self, request: web.Request):
        return web.json_response({"status": "ok"})

    async def web_login(self, request: web.Request):
        """Start a public Roblox identification without linking Discord."""
        if not self.configured():
            return web.Response(
                text=_page("Service indisponible", "La connexion Roblox n'est pas encore configuree."),
                content_type="text/html",
                status=503,
            )

        now = datetime.now(timezone.utc)
        self.web_oauth_states = {
            key: value for key, value in self.web_oauth_states.items()
            if value["expires_at"] >= now
        }
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        self.web_oauth_states[state] = {
            "code_verifier": verifier,
            "expires_at": now + timedelta(minutes=10),
        }
        params = urlencode({
            "client_id": config.ROBLOX_CLIENT_ID,
            "redirect_uri": config.ROBLOX_REDIRECT_URI,
            "scope": "openid profile",
            "response_type": "code",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account consent",
        })
        raise web.HTTPFound(f"{AUTHORIZE_URL}?{params}")

    @roblox.command(name="link", description="Relie officiellement ton compte Roblox à ton compte Discord.")
    async def roblox_link(self, interaction: discord.Interaction):
        if not self.configured():
            await interaction.response.send_message("La liaison Roblox n'est pas encore configurée.", ephemeral=True)
            return
        if interaction.guild_id is None:
            await interaction.response.send_message("Utilise cette commande depuis le serveur.", ephemeral=True)
            return

        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        await db.create_roblox_oauth_state(state, interaction.user.id, interaction.guild_id, verifier, expires)
        params = urlencode({
            "client_id": config.ROBLOX_CLIENT_ID,
            "redirect_uri": config.ROBLOX_REDIRECT_URI,
            "scope": "openid profile",
            "response_type": "code",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account consent",
        })
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Lier mon compte Roblox", emoji="🔗",
                                        style=discord.ButtonStyle.link, url=f"{AUTHORIZE_URL}?{params}"))
        embed = discord.Embed(
            title="🔗 Liaison Roblox",
            description=("Clique sur le bouton puis connecte-toi uniquement sur le site officiel Roblox. "
                         "Le lien expire dans **10 minutes**.\n\n"
                         "Le bot ne reçoit jamais ton mot de passe ni ton cookie Roblox."),
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def oauth_callback(self, request: web.Request):
        if request.query.get("error"):
            return web.Response(text=_page("Autorisation annulée", "Roblox n'a pas autorisé la liaison."),
                                content_type="text/html")
        code, state = request.query.get("code"), request.query.get("state")
        if not code or not state:
            return web.Response(text=_page("Lien invalide", "Code ou état OAuth manquant."),
                                content_type="text/html", status=400)
        web_saved = self.web_oauth_states.pop(state, None)
        saved = web_saved or await db.consume_roblox_oauth_state(state)
        if not saved:
            return web.Response(text=_page("Lien expiré", "Recommence la connexion depuis la page d'accueil."),
                                content_type="text/html", status=400)
        expires_at = saved["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at < datetime.now(timezone.utc):
            return web.Response(text=_page("Lien expiré", "Recommence la connexion depuis la page d'accueil."),
                                content_type="text/html", status=400)

        assert self.session is not None
        token_data = {
            "grant_type": "authorization_code", "code": code,
            "client_id": config.ROBLOX_CLIENT_ID, "client_secret": config.ROBLOX_CLIENT_SECRET,
            "redirect_uri": config.ROBLOX_REDIRECT_URI, "code_verifier": saved["code_verifier"],
        }
        try:
            async with self.session.post(TOKEN_URL, data=token_data) as response:
                if response.status != 200:
                    logger.error("Échange OAuth Roblox refusé (HTTP %s)", response.status)
                    raise RuntimeError("token exchange failed")
                tokens = await response.json()
            async with self.session.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
            ) as response:
                if response.status != 200:
                    raise RuntimeError("userinfo failed")
                profile = await response.json()
        except (aiohttp.ClientError, KeyError, RuntimeError):
            logger.exception("Échec du callback OAuth Roblox")
            return web.Response(text=_page("Erreur de liaison", "Roblox n'a pas pu confirmer le compte. Réessaie."),
                                content_type="text/html", status=502)

        if web_saved is not None:
            username = profile.get("preferred_username", profile["sub"])
            return web.Response(
                text=_page(
                    "Connexion Roblox réussie !",
                    f"Le compte {username} a bien été identifié. Aucune donnée de connexion n'a été conservée.",
                    True,
                ),
                content_type="text/html",
            )

        success, error = await db.save_roblox_link(saved["discord_user_id"], saved["guild_id"], profile)
        if not success:
            return web.Response(text=_page("Liaison refusée", error or "Compte déjà utilisé."),
                                content_type="text/html", status=409)

        guild = self.bot.get_guild(saved["guild_id"])
        member = guild.get_member(saved["discord_user_id"]) if guild else None
        if member and config.ROBLOX_VERIFIED_ROLE_ID:
            role = guild.get_role(int(config.ROBLOX_VERIFIED_ROLE_ID))
            if role:
                try:
                    await member.add_roles(role, reason="Compte Roblox vérifié via OAuth")
                except discord.Forbidden:
                    logger.warning("Impossible d'attribuer le rôle Roblox vérifié à %s", member.id)
        if member:
            try:
                await member.send(f"✅ Ton compte Roblox **{profile.get('preferred_username', profile['sub'])}** est lié.")
            except discord.Forbidden:
                pass
        return web.Response(
            text=_page("Compte Roblox lié !",
                       f"Le compte {profile.get('preferred_username', profile['sub'])} est maintenant associé à Discord.", True),
            content_type="text/html",
        )

    @roblox.command(name="profile", description="Affiche le compte Roblox lié d'un membre.")
    @app_commands.describe(membre="Membre à consulter (toi par défaut)")
    async def roblox_profile(self, interaction: discord.Interaction, membre: discord.Member | None = None):
        target = membre or interaction.user
        link = await db.get_roblox_link(target.id)
        if not link:
            await interaction.response.send_message(f"{target.mention} n'a pas de compte Roblox lié.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🎮 {link['roblox_display_name']}",
                              url=link["profile_url"] or f"https://www.roblox.com/users/{link['roblox_user_id']}/profile",
                              description=f"@{link['roblox_username']}", color=config.COLOR_SUCCESS)
        embed.add_field(name="Identifiant Roblox", value=f"`{link['roblox_user_id']}`")
        embed.add_field(name="Lié à", value=target.mention)
        if link["picture_url"]:
            embed.set_thumbnail(url=link["picture_url"])
        embed.set_footer(text=f"Liaison effectuée le {link['linked_at'][:10]}")
        await interaction.response.send_message(embed=embed)

    @roblox.command(name="unlink", description="Supprime la liaison entre tes comptes Discord et Roblox.")
    async def roblox_unlink(self, interaction: discord.Interaction):
        removed = await db.delete_roblox_link(interaction.user.id)
        if not removed:
            await interaction.response.send_message("Tu n'as aucun compte Roblox lié.", ephemeral=True)
            return
        if interaction.guild and config.ROBLOX_VERIFIED_ROLE_ID:
            role = interaction.guild.get_role(int(config.ROBLOX_VERIFIED_ROLE_ID))
            if role and role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(role, reason="Compte Roblox délié")
                except discord.Forbidden:
                    pass
        await interaction.response.send_message("✅ Ton compte Roblox a été délié et supprimé de la base.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RobloxLink(bot))
