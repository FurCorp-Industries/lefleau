"""Panel global réservé aux propriétaires déclarés du bot."""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from urllib.parse import urlencode

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands

import config
import database as db
from cogs.web_panel import CSS, esc


logger = logging.getLogger("onepiece-bot.owner-panel")
DISCORD_AUTHORIZE = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN = "https://discord.com/api/v10/oauth2/token"
DISCORD_ME = "https://discord.com/api/v10/users/@me"
COOKIE_NAME = "lefleau_owner_panel_session"
STATE_COOKIE = "lefleau_owner_oauth_state"

OWNER_CSS = CSS + """
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:22px}
.stat{background:linear-gradient(145deg,var(--card2),var(--card));border:1px solid var(--line);
border-radius:14px;padding:17px}.stat strong{display:block;font-size:25px;margin-top:4px}.server-meta{
display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.owner-warning{border-color:#8a6b20;background:#2b2411}
.blacklist-entry{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;
padding:15px 0;border-bottom:1px solid var(--line)}.blacklist-entry:last-child{border:0}
.blacklist-entry form{flex:0 0 auto}.blacklist-entry .btn{margin-top:0}
"""


class OwnerPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.http: aiohttp.ClientSession | None = None
        self.oauth_states: dict[str, float] = {}
        self.channel_delete_locks: set[int] = set()
        self.blacklist_locks: set[int] = set()
        self.blacklist_sync_lock = asyncio.Lock()
        self.blacklist_initial_sync_done = False
        self.started_at = time.monotonic()

    async def cog_load(self):
        if not config.OWNER_PANEL_ENABLED:
            logger.info("Panel Owner désactivé (OWNER_PANEL_ENABLED=false).")
            return
        if not config.OWNER_PANEL_USER_IDS:
            logger.error("Panel Owner désactivé : OWNER_PANEL_USER_IDS est vide.")
            return
        if not all((
            config.OWNER_PANEL_CLIENT_ID,
            config.OWNER_PANEL_CLIENT_SECRET,
            config.OWNER_PANEL_SESSION_SECRET,
        )):
            logger.error("Panel Owner désactivé : configuration OAuth/session incomplète.")
            return

        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        app = web.Application(client_max_size=128 * 1024, middlewares=[self.security_headers])
        app.router.add_get("/", self.home)
        app.router.add_get("/health", self.health)
        app.router.add_get("/auth/login", self.login)
        app.router.add_get("/auth/callback", self.callback)
        app.router.add_post("/auth/logout", self.logout)
        app.router.add_get("/dashboard", self.dashboard)
        app.router.add_get("/blacklist", self.blacklist_page)
        app.router.add_post("/blacklist/add", self.add_blacklist_entry)
        app.router.add_post("/blacklist/{user_id}/remove", self.remove_blacklist_entry)
        app.router.add_get("/guild/{guild_id}", self.guild_page)
        app.router.add_post("/guild/{guild_id}/invite", self.create_guild_invite)
        app.router.add_post("/guild/{guild_id}/delete-channels", self.delete_guild_channels)
        app.router.add_post("/guild/{guild_id}/leave", self.leave_guild)
        self.runner = web.AppRunner(app, access_log=logger)
        await self.runner.setup()
        await web.TCPSite(
            self.runner, config.OWNER_PANEL_HOST, config.OWNER_PANEL_PORT
        ).start()
        logger.info(
            "Panel Owner actif sur %s:%s",
            config.OWNER_PANEL_HOST,
            config.OWNER_PANEL_PORT,
        )

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()
        if self.http:
            await self.http.close()

    @web.middleware
    async def security_headers(self, request: web.Request, handler):
        response = await handler(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"
        response.headers["Cache-Control"] = "no-store"
        return response

    def _page(self, title: str, body: str, session: dict | None = None, login_page: bool = False):
        user = ""
        if session:
            user = (
                f'<div class="user"><span>{esc(session["name"])}</span>'
                f'<form method="post" action="/auth/logout"><input type="hidden" name="csrf" '
                f'value="{esc(session["csrf"])}"><button class="btn secondary" style="margin:0">Déconnexion</button></form></div>'
            )
        nav = f'<header class="top"><a class="brand" href="/dashboard">Le Fleau <span>Owner</span></a>{user}</header>'
        container = f'<main class="{"login" if login_page else "wrap"}">{body}</main>'
        return web.Response(
            text=(
                '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{esc(title)} · Le Fleau Owner</title><style>{OWNER_CSS}</style>'
                f'</head><body>{nav}{container}</body></html>'
            ),
            content_type="text/html",
        )

    def _encode_session(self, data: dict) -> str:
        body = base64.urlsafe_b64encode(
            json.dumps(data, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        signature = hmac.new(
            config.OWNER_PANEL_SESSION_SECRET.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        return f"{body}.{signature}"

    def _decode_session(self, value: str | None) -> dict | None:
        if not value or "." not in value:
            return None
        body, signature = value.rsplit(".", 1)
        expected = hmac.new(
            config.OWNER_PANEL_SESSION_SECRET.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        try:
            signature_matches = hmac.compare_digest(signature.encode("ascii"), expected.encode("ascii"))
        except UnicodeEncodeError:
            return None
        if not signature_matches:
            return None
        try:
            padded = body + "=" * (-len(body) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded).decode())
            user_id = int(data["uid"])
            if int(data["exp"]) <= int(time.time()) or user_id not in config.OWNER_PANEL_USER_IDS:
                return None
            return data
        except (ValueError, KeyError, json.JSONDecodeError):
            return None

    def _session(self, request: web.Request) -> dict | None:
        return self._decode_session(request.cookies.get(COOKIE_NAME))

    def _require_owner(self, request: web.Request) -> dict:
        session = self._session(request)
        if not session:
            raise web.HTTPFound("/auth/login")
        return session

    @staticmethod
    def _csrf(request: web.Request, session: dict, form) -> None:
        if not hmac.compare_digest(str(form.get("csrf", "")), str(session.get("csrf", ""))):
            raise web.HTTPForbidden(text="Jeton de sécurité invalide. Recharge la page.")

    async def health(self, request):
        return web.json_response({"status": "ok", "bot_ready": self.bot.is_ready()})

    async def home(self, request):
        if self._session(request):
            raise web.HTTPFound("/dashboard")
        body = (
            '<section class="card"><span class="pill">Accès strictement privé</span>'
            '<h1>Panel Owner de Le Fleau</h1><p>Supervision globale du bot et de tous ses serveurs.</p>'
            '<div class="flash owner-warning">Seuls les comptes Discord explicitement déclarés comme propriétaires peuvent entrer.</div>'
            '<a class="btn" href="/auth/login">Continuer avec Discord</a></section>'
        )
        return self._page("Connexion", body, login_page=True)

    async def login(self, request):
        now = time.time()
        self.oauth_states = {
            key: expires for key, expires in self.oauth_states.items() if expires > now
        }
        state = secrets.token_urlsafe(32)
        self.oauth_states[state] = now + 600
        params = urlencode({
            "client_id": config.OWNER_PANEL_CLIENT_ID,
            "redirect_uri": f"{config.OWNER_PANEL_BASE_URL}/auth/callback",
            "response_type": "code",
            "scope": "identify",
            "state": state,
        })
        response = web.HTTPFound(f"{DISCORD_AUTHORIZE}?{params}")
        response.set_cookie(
            STATE_COOKIE, state, max_age=600, secure=True, httponly=True, samesite="Lax"
        )
        raise response

    async def callback(self, request):
        state = request.query.get("state", "")
        expected = request.cookies.get(STATE_COOKIE, "")
        if (
            not state
            or not hmac.compare_digest(state, expected)
            or self.oauth_states.pop(state, 0) < time.time()
        ):
            raise web.HTTPBadRequest(text="Connexion expirée ou invalide.")
        code = request.query.get("code")
        if not code or not self.http:
            raise web.HTTPBadRequest(text="Discord n'a pas fourni de code d'autorisation.")

        async with self.http.post(DISCORD_TOKEN, data={
            "client_id": config.OWNER_PANEL_CLIENT_ID,
            "client_secret": config.OWNER_PANEL_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{config.OWNER_PANEL_BASE_URL}/auth/callback",
        }) as token_response:
            if token_response.status != 200:
                logger.error("Échange OAuth Owner refusé (HTTP %s)", token_response.status)
                raise web.HTTPBadGateway(text="Discord a refusé la connexion.")
            token = await token_response.json()
        async with self.http.get(
            DISCORD_ME,
            headers={"Authorization": f"Bearer {token['access_token']}"},
        ) as me_response:
            if me_response.status != 200:
                raise web.HTTPBadGateway(text="Impossible de lire le profil Discord.")
            user = await me_response.json()

        user_id = int(user["id"])
        if user_id not in config.OWNER_PANEL_USER_IDS:
            logger.warning("Accès Owner refusé au compte Discord %s", user_id)
            raise web.HTTPForbidden(text="Ce compte Discord n'est pas autorisé à utiliser le panel Owner.")
        session = {
            "uid": str(user_id),
            "name": user.get("global_name") or user["username"],
            "csrf": secrets.token_urlsafe(24),
            "exp": int(time.time()) + 4 * 3600,
        }
        response = web.HTTPFound("/dashboard")
        response.set_cookie(
            COOKIE_NAME,
            self._encode_session(session),
            max_age=4 * 3600,
            secure=True,
            httponly=True,
            samesite="Strict",
            path="/",
        )
        response.del_cookie(STATE_COOKIE)
        raise response

    async def logout(self, request):
        session = self._require_owner(request)
        form = await request.post()
        self._csrf(request, session, form)
        response = web.HTTPFound("/")
        response.del_cookie(COOKIE_NAME, path="/")
        raise response

    async def dashboard(self, request):
        session = self._require_owner(request)
        stats = await db.get_global_stats()
        uptime = int(time.monotonic() - self.started_at)
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        latency = round(self.bot.latency * 1000) if self.bot.is_ready() else 0
        stat_cards = "".join((
            f'<div class="stat"><span class="muted">Serveurs</span><strong>{len(self.bot.guilds):,}</strong></div>',
            f'<div class="stat"><span class="muted">Utilisateurs économiques</span><strong>{stats["user_count"]:,}</strong></div>',
            f'<div class="stat"><span class="muted">{esc(config.CURRENCY_NAME)} en circulation</span><strong>{stats["total_wallet"]:,}</strong></div>',
            f'<div class="stat"><span class="muted">Objets personnalisés actifs</span><strong>{stats["active_custom_items"]:,}</strong></div>',
            f'<div class="stat"><span class="muted">Latence Discord</span><strong>{latency} ms</strong></div>',
            f'<div class="stat"><span class="muted">Temps en ligne</span><strong>{hours:02d}:{minutes:02d}:{seconds:02d}</strong></div>',
        ))
        guild_cards = "".join(
            f'<a class="server" href="/guild/{guild.id}">'
            f'<span class="pill">{guild.member_count or 0:,} membres</span>'
            f'<h2>{esc(guild.name)}</h2><p>ID : {guild.id}</p></a>'
            for guild in sorted(self.bot.guilds, key=lambda item: item.name.casefold())
        ) or '<div class="card"><h2>Aucun serveur</h2><p class="hint">Le bot ne se trouve actuellement sur aucun serveur.</p></div>'
        flash = (
            f'<div class="flash">{esc(request.query.get("ok"))}</div>'
            if request.query.get("ok")
            else ""
        )
        body = (
            f'{flash}<div class="hero"><div><h1>Vue globale</h1><p>État en direct du bot principal Le Fleau.</p></div>'
            f'<div><span class="pill">{"En ligne" if self.bot.is_ready() else "Connexion en cours"}</span> '
            f'<a class="btn danger" href="/blacklist">Gérer la blacklist</a></div></div>'
            f'<div class="stats">{stat_cards}</div><h2>Serveurs du bot</h2><div class="grid">{guild_cards}</div>'
        )
        return self._page("Vue globale", body, session)

    async def blacklist_page(self, request):
        session = self._require_owner(request)
        entries = await db.get_global_blacklist()
        notice = (
            f'<div class="flash">{esc(request.query.get("ok"))}</div>'
            if request.query.get("ok")
            else ""
        )
        entry_rows = "".join(
            f'''<div class="blacklist-entry"><div><strong>ID : {entry["user_id"]}</strong>
            <p class="hint">Motif : {esc(entry["reason"])}</p>
            <p class="muted">Ajouté par {entry["added_by"]} · {esc(entry["added_at"])}</p></div>
            <form method="post" action="/blacklist/{entry["user_id"]}/remove">
            <input type="hidden" name="csrf" value="{esc(session["csrf"])}">
            <button class="btn secondary">Retirer de la blacklist</button></form></div>'''
            for entry in entries
        ) or '<p class="hint">Aucun utilisateur ne figure actuellement dans la blacklist globale.</p>'

        body = f'''{notice}<div class="hero"><div><a class="muted" href="/dashboard">← Vue globale</a>
        <h1>Blacklist globale</h1><p>Les IDs enregistrés sont bannis de tous les serveurs accessibles au bot.</p></div>
        <span class="pill">{len(entries)} utilisateur(s)</span></div>
        <div class="sections"><section class="card owner-warning"><h2>Ajouter un ID Discord</h2>
        <p class="hint">Le bannissement est immédiat sur chaque serveur où Le Fleau possède la permission Bannir des membres.</p>
        <form method="post" action="/blacklist/add">
        <input type="hidden" name="csrf" value="{esc(session["csrf"])}">
        <label>ID Discord de l'utilisateur</label>
        <input name="user_id" inputmode="numeric" pattern="[0-9]+" required autocomplete="off" placeholder="123456789012345678">
        <label>Motif</label><textarea name="reason" required maxlength="300" placeholder="Motif de la blacklist globale"></textarea>
        <label>Confirmation : écris BLACKLIST suivi de l'ID</label>
        <input name="confirmation" required autocomplete="off" placeholder="BLACKLIST 123456789012345678">
        <button class="btn danger">Blacklister et bannir partout</button></form></section>
        <section class="card"><h2>Comportement</h2>
        <p>La blacklist reste active après un redémarrage et s'applique automatiquement aux nouvelles arrivées.</p>
        <p class="hint">Retirer un ID arrête les futurs bannissements automatiques, mais ne débannit pas la personne des serveurs : cela évite d'effacer une sanction locale légitime.</p>
        </section><section class="card wide"><h2>IDs blacklistés</h2>{entry_rows}</section></div>'''
        return self._page("Blacklist globale", body, session)

    def _is_protected_blacklist_id(self, user_id: int) -> bool:
        """Protège toujours le bot et les propriétaires, y compris pour d'anciennes entrées."""
        bot_user_id = self.bot.user.id if self.bot.user else None
        return user_id in config.OWNER_PANEL_USER_IDS or user_id == bot_user_id

    async def _ban_user_from_guild(self, guild: discord.Guild, user_id: int, reason: str) -> bool:
        """Tente d'appliquer un ban global sur un serveur et retourne son succès."""
        if self._is_protected_blacklist_id(user_id):
            logger.error("Application refusée pour l'ID blacklist protégé %s.", user_id)
            return False
        if guild.me is None or not guild.me.guild_permissions.ban_members:
            return False
        try:
            await guild.ban(
                discord.Object(id=user_id),
                reason=f"Blacklist globale Le Fleau : {reason}"[:512],
                delete_message_seconds=0,
            )
            return True
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            logger.exception(
                "Impossible d'appliquer la blacklist de %s sur %s (%s).",
                user_id,
                guild.name,
                guild.id,
            )
            return False

    async def _ban_user_everywhere(self, user_id: int, reason: str) -> tuple[int, int]:
        """Applique un ID blacklisté à tous les serveurs actuels du bot."""
        succeeded = failed = 0
        for guild in list(self.bot.guilds):
            if await self._ban_user_from_guild(guild, user_id, reason):
                succeeded += 1
            else:
                failed += 1
        return succeeded, failed

    async def add_blacklist_entry(self, request):
        session = self._require_owner(request)
        form = await request.post()
        self._csrf(request, session, form)
        raw_user_id = str(form.get("user_id", "")).strip()
        if not raw_user_id.isdigit():
            raise web.HTTPBadRequest(text="L'ID Discord doit contenir uniquement des chiffres.")
        user_id = int(raw_user_id)
        if user_id <= 0 or user_id > 9_223_372_036_854_775_807:
            raise web.HTTPBadRequest(text="ID Discord invalide.")
        expected_confirmation = f"BLACKLIST {user_id}"
        confirmation = str(form.get("confirmation", "")).strip()
        if not hmac.compare_digest(confirmation.encode(), expected_confirmation.encode()):
            raise web.HTTPBadRequest(
                text=f"Confirmation incorrecte : écris exactement {expected_confirmation}."
            )
        if self._is_protected_blacklist_id(user_id):
            raise web.HTTPBadRequest(
                text="Un propriétaire déclaré ou le bot lui-même ne peut pas être blacklisté."
            )
        reason = str(form.get("reason", "")).strip()
        if not reason:
            raise web.HTTPBadRequest(text="Le motif est obligatoire.")
        reason = reason[:300]
        if user_id in self.blacklist_locks:
            raise web.HTTPConflict(text="Une opération de blacklist est déjà en cours pour cet ID.")

        self.blacklist_locks.add(user_id)
        try:
            await db.add_global_blacklist(user_id, reason, int(session["uid"]))
            succeeded, failed = await self._ban_user_everywhere(user_id, reason)
        finally:
            self.blacklist_locks.discard(user_id)
        logger.warning(
            "Owner %s a blacklisté %s : %s ban(s) appliqué(s), %s échec(s). Motif : %s",
            session["uid"], user_id, succeeded, failed, reason,
        )
        message = f"ID {user_id} blacklisté : {succeeded} serveur(s) traité(s)"
        if failed:
            message += f", {failed} échec(s) ou permission(s) manquante(s)"
        message += "."
        raise web.HTTPFound(f"/blacklist?{urlencode({'ok': message})}")

    async def remove_blacklist_entry(self, request):
        session = self._require_owner(request)
        form = await request.post()
        self._csrf(request, session, form)
        try:
            user_id = int(request.match_info["user_id"])
        except ValueError:
            raise web.HTTPNotFound()
        removed = await db.remove_global_blacklist(user_id)
        logger.warning(
            "Owner %s a retiré %s de la blacklist globale (présent=%s).",
            session["uid"], user_id, removed,
        )
        message = (
            f"ID {user_id} retiré de la blacklist. Les bans locaux existants sont conservés."
            if removed
            else f"L'ID {user_id} n'était plus dans la blacklist."
        )
        raise web.HTTPFound(f"/blacklist?{urlencode({'ok': message})}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        entry = await db.get_global_blacklist_entry(member.id)
        if entry:
            await self._ban_user_from_guild(member.guild, member.id, entry["reason"])

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        for entry in await db.get_global_blacklist():
            await self._ban_user_from_guild(guild, entry["user_id"], entry["reason"])

    @commands.Cog.listener()
    async def on_ready(self):
        if self.blacklist_initial_sync_done:
            return
        async with self.blacklist_sync_lock:
            if self.blacklist_initial_sync_done:
                return
            for entry in await db.get_global_blacklist():
                await self._ban_user_everywhere(entry["user_id"], entry["reason"])
            self.blacklist_initial_sync_done = True

    async def guild_page(self, request):
        session = self._require_owner(request)
        try:
            guild_id = int(request.match_info["guild_id"])
        except ValueError:
            raise web.HTTPNotFound()
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise web.HTTPNotFound(text="Le bot n'est pas présent sur ce serveur.")

        economy = await db.get_guild_economy_stats(guild.id)
        custom_items = await db.get_custom_items(guild.id, include_inactive=True)
        active_items = sum(bool(item["active"]) for item in custom_items)
        ticket_categories = await db.get_ticket_categories(guild.id)
        log_settings = await db.get_all_log_settings(guild.id)
        anti = await db.get_antiraid_settings(guild.id) or {}
        owner_name = guild.owner.display_name if guild.owner else str(guild.owner_id)
        configure_url = f"{config.PANEL_BASE_URL}/guild/{guild.id}"
        invite_url = request.query.get("invite", "")
        invite_notice = (
            f'<div class="flash">Invitation temporaire créée : '
            f'<a href="{esc(invite_url)}" rel="noreferrer">{esc(invite_url)}</a> '
            f'(10 minutes, une utilisation).</div>'
            if invite_url.startswith("https://discord.gg/") or invite_url.startswith("https://discord.com/invite/")
            else ""
        )

        body = f'''{invite_notice}<div class="hero"><div><a class="muted" href="/dashboard">← Vue globale</a>
        <h1>{esc(guild.name)}</h1><p>ID : {guild.id}</p></div><div>
        <a class="btn secondary" href="{esc(configure_url)}">Ouvrir la configuration</a>
        <form method="post" action="/guild/{guild.id}/invite" style="display:inline">
        <input type="hidden" name="csrf" value="{esc(session["csrf"])}">
        <button class="btn">Créer une invitation</button></form></div></div>
        <div class="stats">
        <div class="stat"><span class="muted">Membres</span><strong>{guild.member_count or 0:,}</strong></div>
        <div class="stat"><span class="muted">Joueurs économiques</span><strong>{economy["user_count"]:,}</strong></div>
        <div class="stat"><span class="muted">{esc(config.CURRENCY_NAME)}</span><strong>{economy["total_wallet"]:,}</strong></div>
        <div class="stat"><span class="muted">Objets en vente</span><strong>{active_items}/{len(custom_items)}</strong></div>
        </div><div class="sections">
        <section class="card"><h2>Serveur Discord</h2><p>Propriétaire : <strong>{esc(owner_name)}</strong></p>
        <p>Créé le : {guild.created_at.strftime("%d/%m/%Y")}</p><p>Salons : {len(guild.channels)} · Rôles : {len(guild.roles)}</p></section>
        <section class="card"><h2>Modules configurés</h2><p>Catégories de tickets : <strong>{len(ticket_categories)}</strong></p>
        <p>Catégories de logs actives : <strong>{sum(bool(row["enabled"]) for row in log_settings)}</strong></p>
        <p>Protection anti-raid : <strong>{"Active" if anti.get("enabled") else "Inactive"}</strong></p></section>
        <section class="card wide owner-warning"><h2>Supprimer tous les salons</h2>
        <p class="hint">Action irréversible : tous les salons et toutes les catégories de ce serveur seront supprimés. Le serveur et ses rôles resteront présents.</p>
        <form method="post" action="/guild/{guild.id}/delete-channels">
        <input type="hidden" name="csrf" value="{esc(session["csrf"])}">
        <label>Recopie exactement le nom du serveur</label>
        <input name="confirmation" required autocomplete="off" placeholder="{esc(guild.name)}">
        <label>Écris ensuite <strong>SUPPRIMER {guild.id}</strong></label>
        <input name="destructive_confirmation" required autocomplete="off" placeholder="SUPPRIMER {guild.id}">
        <button class="btn danger">Supprimer définitivement tous les salons</button></form></section>
        <section class="card wide owner-warning"><h2>Faire quitter le serveur au bot</h2>
        <p class="hint">Le bot quittera immédiatement ce serveur. Les données conservées dans la base ne seront pas supprimées.</p>
        <form method="post" action="/guild/{guild.id}/leave">
        <input type="hidden" name="csrf" value="{esc(session["csrf"])}">
        <label>Recopie exactement le nom du serveur pour confirmer</label>
        <input name="confirmation" required autocomplete="off" placeholder="{esc(guild.name)}">
        <button class="btn danger">Faire quitter le serveur au bot</button></form></section>
        </div>'''
        return self._page(guild.name, body, session)

    async def create_guild_invite(self, request):
        session = self._require_owner(request)
        form = await request.post()
        self._csrf(request, session, form)
        try:
            guild_id = int(request.match_info["guild_id"])
        except ValueError:
            raise web.HTTPNotFound()
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.me:
            raise web.HTTPNotFound(text="Le bot n'est pas présent sur ce serveur.")

        channel = next(
            (
                candidate
                for candidate in guild.text_channels
                if candidate.permissions_for(guild.me).view_channel
                and candidate.permissions_for(guild.me).create_instant_invite
            ),
            None,
        )
        if channel is None:
            raise web.HTTPForbidden(
                text="Le bot ne possède la permission Créer une invitation dans aucun salon visible."
            )
        try:
            invite = await channel.create_invite(
                max_age=600,
                max_uses=1,
                unique=True,
                reason=f"Invitation Owner demandée par {session['name']} ({session['uid']})",
            )
        except discord.Forbidden:
            raise web.HTTPForbidden(text="Discord a refusé la création de l'invitation.")
        except discord.HTTPException:
            raise web.HTTPBadGateway(text="Discord n'a pas pu créer l'invitation.")
        raise web.HTTPFound(f"/guild/{guild.id}?{urlencode({'invite': invite.url})}")

    async def leave_guild(self, request):
        session = self._require_owner(request)
        form = await request.post()
        self._csrf(request, session, form)
        try:
            guild_id = int(request.match_info["guild_id"])
        except ValueError:
            raise web.HTTPNotFound()
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise web.HTTPNotFound(text="Le bot n'est déjà plus présent sur ce serveur.")
        confirmation = form.get("confirmation", "").strip()
        if not hmac.compare_digest(confirmation.encode("utf-8"), guild.name.encode("utf-8")):
            raise web.HTTPBadRequest(
                text="Confirmation incorrecte : recopie exactement le nom du serveur."
            )

        guild_name = guild.name
        try:
            await guild.leave()
        except discord.HTTPException:
            raise web.HTTPBadGateway(text="Discord n'a pas permis au bot de quitter ce serveur.")
        logger.warning(
            "Le propriétaire Discord %s a fait quitter le serveur %s (%s) au bot.",
            session["uid"],
            guild_name,
            guild_id,
        )
        message = f"Le bot a quitté « {guild_name} » ({guild_id}). Les données ont été conservées."
        raise web.HTTPFound(f"/dashboard?{urlencode({'ok': message})}")

    async def delete_guild_channels(self, request):
        """Supprime tous les salons d'un serveur, uniquement depuis le panel Owner."""
        session = self._require_owner(request)
        form = await request.post()
        self._csrf(request, session, form)
        try:
            guild_id = int(request.match_info["guild_id"])
        except ValueError:
            raise web.HTTPNotFound()
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise web.HTTPNotFound(text="Le bot n'est pas présent sur ce serveur.")

        confirmation = str(form.get("confirmation", "")).strip()
        destructive_confirmation = str(form.get("destructive_confirmation", "")).strip()
        expected_destructive_confirmation = f"SUPPRIMER {guild.id}"
        if not hmac.compare_digest(confirmation.encode("utf-8"), guild.name.encode("utf-8")):
            raise web.HTTPBadRequest(
                text="Confirmation incorrecte : recopie exactement le nom du serveur."
            )
        if not hmac.compare_digest(
            destructive_confirmation.encode("utf-8"),
            expected_destructive_confirmation.encode("utf-8"),
        ):
            raise web.HTTPBadRequest(
                text=f"Confirmation incorrecte : écris exactement {expected_destructive_confirmation}."
            )
        if guild.id in self.channel_delete_locks:
            raise web.HTTPConflict(text="Une suppression des salons est déjà en cours sur ce serveur.")

        self.channel_delete_locks.add(guild.id)
        deleted = 0
        failed = 0
        try:
            # Les catégories sont supprimées en dernier pour conserver une
            # structure Discord cohérente pendant toute l'opération.
            channels = sorted(
                list(guild.channels),
                key=lambda channel: channel.type is discord.ChannelType.category,
            )
            for channel in channels:
                try:
                    await channel.delete(
                        reason=(
                            "Suppression de tous les salons depuis le panel Owner "
                            f"par {session['name']} ({session['uid']})"
                        )
                    )
                    deleted += 1
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    failed += 1
                    logger.exception(
                        "Échec de suppression du salon %s (%s) sur %s (%s).",
                        getattr(channel, "name", "inconnu"),
                        getattr(channel, "id", "inconnu"),
                        guild.name,
                        guild.id,
                    )
        finally:
            self.channel_delete_locks.discard(guild.id)

        logger.warning(
            "Le propriétaire Discord %s a demandé la suppression de tous les salons de %s (%s) : %s supprimé(s), %s échec(s).",
            session["uid"],
            guild.name,
            guild.id,
            deleted,
            failed,
        )
        message = f"Suppression terminée sur « {guild.name} » : {deleted} salon(s) supprimé(s)"
        if failed:
            message += f", {failed} échec(s) à vérifier dans les logs"
        message += "."
        raise web.HTTPFound(f"/guild/{guild.id}?{urlencode({'ok': message})}")


async def setup(bot: commands.Bot):
    await bot.add_cog(OwnerPanel(bot))
