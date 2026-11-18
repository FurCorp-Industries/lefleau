"""Panel web sécurisé du bot principal, protégé par Discord OAuth2."""

import base64
import hashlib
import hmac
import html
import json
import logging
import secrets
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands

import config
import database as db
from cogs.community_tools import GiveawayView, update_proposal_status_message
from cogs.join_roles import MAX_JOIN_ROLES, TARGET_LABELS
from utils.role_checks import role_assign_problem
from utils.helpers import format_duration, parse_duration

logger = logging.getLogger("onepiece-bot.panel")
PREFIX = config.PANEL_PREFIX

# Bundle front-end des titres de serveurs (voir panel_ui/). Les titres restent du
# texte simple dans le HTML : sans le bundle ou sans WebGL 2.0, rien ne change.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "panel"
STATIC_FILES = {
    "refracted-titles.js": "application/javascript",
    "refracted-titles.css": "text/css",
}
_asset_versions: dict[str, str] = {}


def asset_version(name: str) -> str | None:
    """Empreinte du fichier (pour l'URL versionnée), ou None s'il est absent."""
    if name not in _asset_versions:
        try:
            _asset_versions[name] = hashlib.sha1((STATIC_DIR / name).read_bytes()).hexdigest()[:10]
        except OSError:
            return None
    return _asset_versions[name]


def server_title(name: str) -> str:
    """Titre de serveur : texte simple, remplacé côté navigateur par RefractedText."""
    return (
        f'<span class="rt-title" data-rt-title="{esc(name)}">'
        f'<span class="rt-title__text">{esc(name)}</span></span>'
    )


def guild_icon(guild, size: int = 128, css_class: str = "gicon") -> str:
    """Icône du serveur (WebP statique, chargement différé) ou pastille avec les initiales."""
    icon = getattr(guild, "icon", None)
    if icon:
        # Le format WebP d'une icône animée reste statique : léger pour une simple liste.
        url = icon.replace(size=size, format="webp").url
        return (
            f'<img class="{css_class}" src="{esc(url)}" alt="" width="{size}" height="{size}" '
            f'loading="lazy" decoding="async" referrerpolicy="no-referrer">'
        )
    initials = "".join(word[0] for word in str(guild.name).split()[:2]).upper() or "?"
    hue = int(guild.id) % 360
    return (
        f'<span class="{css_class} {css_class}--fallback" aria-hidden="true" '
        f'style="background:hsl({hue} 42% 30%)">{esc(initials)}</span>'
    )

DISCORD_AUTHORIZE = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN = "https://discord.com/api/v10/oauth2/token"
DISCORD_ME = "https://discord.com/api/v10/users/@me"
COOKIE_NAME = "lefleau_unified_panel_session"
STATE_COOKIE = "onepiece_panel_oauth_state"
LOG_CATEGORIES = {
    "messages": "Messages",
    "membres": "Membres",
    "salons": "Salons",
    "roles": "Rôles",
    "vocal": "Vocal",
    "serveur": "Serveur",
    "boosts": "Boosts",
}

CSS = """
:root{color-scheme:dark;--bg:#080b12;--card:#111722;--card2:#171f2d;--line:#263246;
--text:#f4f7fb;--muted:#9cabc0;--accent:#6c8cff;--ok:#44d18d;--danger:#ff647c}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 12% 0,#17213b 0,
var(--bg) 38%);color:var(--text);font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif}
a{color:inherit}.top{height:68px;border-bottom:1px solid var(--line);display:flex;align-items:center;
justify-content:space-between;padding:0 max(24px,calc((100% - 1180px)/2));background:#0b1019dd;
position:sticky;top:0;backdrop-filter:blur(14px);z-index:5}.brand{font-size:19px;font-weight:800;
text-decoration:none}.brand span{color:var(--accent)}.user{display:flex;gap:12px;align-items:center;color:var(--muted)}
.wrap{width:min(1180px,calc(100% - 32px));margin:34px auto 80px}.hero{display:flex;justify-content:
space-between;gap:20px;align-items:end;margin-bottom:26px}.hero h1{font-size:34px;line-height:1.1;margin:0 0 8px}
.hero p{margin:0;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,
minmax(270px,1fr));gap:16px}.server,.card{display:block;background:linear-gradient(145deg,var(--card2),
var(--card));border:1px solid var(--line);border-radius:16px;padding:20px;text-decoration:none;box-shadow:
0 12px 30px #0003}.server:hover{border-color:var(--accent);transform:translateY(-2px)}.server h2,
.card h2{margin:0 0 6px;font-size:18px}.server p,.hint{color:var(--muted);margin:0}.sections{display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.card{margin:0}.wide{grid-column:1/-1}
label{display:block;color:#ccd5e2;font-weight:650;margin:13px 0 6px}input,select,textarea{width:100%;
border:1px solid var(--line);background:#0c111b;color:var(--text);border-radius:9px;padding:10px 11px;
font:inherit}select[multiple]{min-height:130px}textarea{min-height:90px;resize:vertical}.row{display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.check{display:flex;align-items:center;gap:9px;
margin:14px 0}.check input{width:auto}.btn{display:inline-flex;align-items:center;justify-content:center;border:0;
border-radius:9px;padding:10px 15px;background:var(--accent);color:white;font-weight:750;cursor:pointer;
text-decoration:none;margin-top:15px}.btn.secondary{background:#273248}.btn.danger{background:#a93449}.flash{padding:12px 15px;
border:1px solid #27674c;background:#112c24;border-radius:10px;color:#8df0bf;margin-bottom:18px}
.login{min-height:calc(100vh - 68px);display:grid;place-items:center}.login .card{width:min(520px,
calc(100% - 32px));padding:34px}.login h1{font-size:32px;margin:0 0 10px}.login p{color:var(--muted)}
.pill{display:inline-block;padding:3px 8px;border:1px solid var(--line);border-radius:99px;color:var(--muted);
font-size:12px}.category{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;
border-bottom:1px solid var(--line)}.category:last-child{border:0}.muted{color:var(--muted)}
.hero>div:first-child{flex:1;min-width:0}.rt-title{display:block;width:100%;max-width:min(100%,880px);
container-type:inline-size}.rt-title__lines{display:grid;gap:.3em;width:100%}.rt-title--ready .rt-title__text{display:none}
.hero-title{display:flex;align-items:center;gap:18px;margin:6px 0 8px}.hero-title h1{flex:1;min-width:0;margin:0}
.gicon{width:52px;height:52px;border-radius:14px;flex:none;object-fit:cover;background:#0c111b}
.gicon--fallback{display:grid;place-items:center;font-weight:800;font-size:18px;color:#fff}
.hero-title .gicon{width:76px;height:76px;border-radius:20px;font-size:26px}
.server-head{display:flex;align-items:center;gap:14px;margin-bottom:14px}.server-meta{min-width:0}
.server-meta h2{margin:0 0 6px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;line-clamp:2;
-webkit-box-orient:vertical;overflow-wrap:anywhere;line-height:1.25}
@media(max-width:780px){.sections{grid-template-columns:1fr}.wide{grid-column:auto}.row{grid-template-columns:1fr}
.hero{display:block}.top{padding:0 16px}.user span{display:none}}
"""


def esc(value) -> str:
    return html.escape(str(value), quote=True)


class WebPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.http: aiohttp.ClientSession | None = None
        self.oauth_states: dict[str, float] = {}

    async def cog_load(self):
        if not config.PANEL_ENABLED:
            logger.info("Panel web desactive (PANEL_ENABLED=false).")
            return
        if not all((config.PANEL_CLIENT_ID, config.PANEL_CLIENT_SECRET, config.PANEL_SESSION_SECRET)):
            logger.error("Panel web desactive : configuration OAuth/session incomplete.")
            return
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        app = web.Application(client_max_size=256 * 1024, middlewares=[self.security_headers])
        app.router.add_get(PREFIX + "/", self.home)
        app.router.add_get(PREFIX + "/health", self.health)
        app.router.add_get(PREFIX + "/static/{name}", self.static_file)
        app.router.add_get(PREFIX + "/auth/login", self.login)
        app.router.add_get(PREFIX + "/auth/callback", self.callback)
        app.router.add_post(PREFIX + "/auth/logout", self.logout)
        app.router.add_get(PREFIX + "/dashboard", self.dashboard)
        app.router.add_get(PREFIX + "/guild/{guild_id}", self.guild_page)
        app.router.add_get(PREFIX + "/guild/{guild_id}/messages", self.messages_page)
        app.router.add_post(PREFIX + "/guild/{guild_id}/messages/create", self.messages_create)
        app.router.add_post(PREFIX + "/guild/{guild_id}/messages/edit", self.messages_edit)
        app.router.add_post(PREFIX + "/guild/{guild_id}/messages/delete", self.messages_delete)
        app.router.add_post(PREFIX + "/guild/{guild_id}/messages/roles", self.messages_roles)
        app.router.add_post(PREFIX + "/guild/{guild_id}/access", self.save_access)
        app.router.add_post(PREFIX + "/guild/{guild_id}/antiraid", self.save_antiraid)
        app.router.add_post(PREFIX + "/guild/{guild_id}/logs", self.save_logs)
        app.router.add_post(PREFIX + "/guild/{guild_id}/tickets", self.save_tickets)
        app.router.add_post(PREFIX + "/guild/{guild_id}/ticket-category", self.save_ticket_category)
        app.router.add_post(PREFIX + "/guild/{guild_id}/ticket-category-delete", self.delete_ticket_category)
        app.router.add_post(PREFIX + "/guild/{guild_id}/sanctions", self.save_sanctions)
        app.router.add_post(PREFIX + "/guild/{guild_id}/giveaway", self.create_giveaway)
        app.router.add_post(PREFIX + "/guild/{guild_id}/economy", self.save_economy)
        app.router.add_get(PREFIX + "/guild/{guild_id}/points", self.points_page)
        app.router.add_post(PREFIX + "/guild/{guild_id}/points/config", self.points_save_config)
        app.router.add_post(PREFIX + "/guild/{guild_id}/points/add", self.points_add)
        app.router.add_post(PREFIX + "/guild/{guild_id}/points/item", self.points_save_item)
        app.router.add_post(PREFIX + "/guild/{guild_id}/points/item-remove", self.points_remove_item)
        app.router.add_post(PREFIX + "/guild/{guild_id}/points/role", self.points_save_role)
        app.router.add_post(PREFIX + "/guild/{guild_id}/points/role-remove", self.points_remove_role)
        app.router.add_post(PREFIX + "/guild/{guild_id}/points/proposal", self.points_review_proposal)
        app.router.add_get(PREFIX + "/guild/{guild_id}/join-roles", self.join_roles_page)
        app.router.add_post(PREFIX + "/guild/{guild_id}/join-roles/add", self.join_roles_add)
        app.router.add_post(PREFIX + "/guild/{guild_id}/join-roles/remove", self.join_roles_remove)
        app.router.add_post(PREFIX + "/guild/{guild_id}/join-roles/settings", self.join_roles_settings)
        app.router.add_post(PREFIX + "/guild/{guild_id}/custom-item", self.save_custom_item)
        app.router.add_post(PREFIX + "/guild/{guild_id}/custom-item-toggle", self.toggle_custom_item)
        self.runner = web.AppRunner(app, access_log=logger)
        await self.runner.setup()
        await web.TCPSite(self.runner, config.PANEL_HOST, config.PANEL_PORT).start()
        logger.info("Panel web actif sur %s:%s", config.PANEL_HOST, config.PANEL_PORT)

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
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    def _page(self, title: str, body: str, session: dict | None = None, login_page: bool = False,
              titles: bool = False):
        user = ""
        if session:
            user = (
                f'<div class="user"><span>{esc(session["name"])}</span>'
                f'<form method="post" action="{PREFIX}/auth/logout"><input type="hidden" name="csrf" '
                f'value="{esc(session["csrf"])}"><button class="btn secondary" style="margin:0">Déconnexion</button></form></div>'
            )
        nav = f'<header class="top"><a class="brand" href="/">Le Fleau <span>Panel</span></a>{user}</header>'
        container = f'<main class="{"login" if login_page else "wrap"}">{body}</main>'
        assets = ""
        if titles and asset_version("refracted-titles.js"):
            assets = (
                f'<link rel="stylesheet" href="{PREFIX}/static/refracted-titles.css?v={asset_version("refracted-titles.css")}">'
                f'<script defer src="{PREFIX}/static/refracted-titles.js?v={asset_version("refracted-titles.js")}"></script>'
            )
        return web.Response(
            text=f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" '
                 f'content="width=device-width,initial-scale=1"><title>{esc(title)} · Le Fleau Panel</title>'
                 f'<style>{CSS}</style>{assets}</head><body>{nav}{container}</body></html>',
            content_type="text/html",
        )

    def _encode_session(self, data: dict) -> str:
        body = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()
        signature = hmac.new(config.PANEL_SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{signature}"

    def _decode_session(self, value: str | None) -> dict | None:
        if not value or "." not in value:
            return None
        body, signature = value.rsplit(".", 1)
        expected = hmac.new(config.PANEL_SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        try:
            signature_matches = hmac.compare_digest(signature.encode("ascii"), expected.encode("ascii"))
        except UnicodeEncodeError:
            return None
        if not signature_matches:
            return None
        try:
            padded = body + "=" * (-len(body) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded).decode())
            return data if int(data["exp"]) > int(time.time()) else None
        except (ValueError, KeyError, json.JSONDecodeError):
            return None

    def _session(self, request: web.Request) -> dict | None:
        return self._decode_session(request.cookies.get(COOKIE_NAME))

    def _require_session(self, request: web.Request) -> dict:
        session = self._session(request)
        if not session:
            raise web.HTTPFound(f"{PREFIX}/auth/login")
        return session

    @staticmethod
    def _csrf(request: web.Request, session: dict, form) -> None:
        if not hmac.compare_digest(str(form.get("csrf", "")), str(session.get("csrf", ""))):
            raise web.HTTPForbidden(text="Jeton de sécurité invalide. Recharge la page.")

    async def _access(self, request: web.Request, require_admin: bool = False):
        session = self._require_session(request)
        try:
            guild_id = int(request.match_info["guild_id"])
        except ValueError:
            raise web.HTTPNotFound()
        guild = self.bot.get_guild(guild_id)
        user_id = int(session["uid"])
        is_bot_owner = user_id in config.OWNER_PANEL_USER_IDS
        member = guild.get_member(user_id) if guild else None
        if not guild or (not member and not is_bot_owner):
            raise web.HTTPForbidden(text="Tu n'es pas membre de ce serveur ou le bot n'y est pas présent.")
        is_admin = is_bot_owner or guild.owner_id == member.id or member.guild_permissions.administrator
        is_manager = is_admin or (member and member.guild_permissions.manage_guild)
        allowed_roles = set(await db.get_panel_access_roles(guild.id))
        delegated = bool(member and allowed_roles.intersection(role.id for role in member.roles))
        if require_admin and not is_admin:
            raise web.HTTPForbidden(text="Seul un administrateur peut modifier les accès au panel.")
        if not (is_manager or delegated):
            raise web.HTTPForbidden(text="Tu n'as pas accès au panel de ce serveur.")
        return session, guild, member, is_admin

    async def _message_access(self, request: web.Request):
        # Admins/managers can publish; dedicated roles can edit tracked messages only.
        session = self._require_session(request)
        try:
            guild_id = int(request.match_info["guild_id"])
        except ValueError:
            raise web.HTTPNotFound()
        guild = self.bot.get_guild(guild_id)
        user_id = int(session["uid"])
        owner = user_id in config.OWNER_PANEL_USER_IDS
        member = guild.get_member(user_id) if guild else None
        if guild is None or (member is None and not owner):
            raise web.HTTPForbidden(text="Serveur inaccessible.")
        admin = owner or bool(member and (guild.owner_id == user_id or member.guild_permissions.administrator))
        manager = admin or bool(member and member.guild_permissions.manage_guild)
        panel_roles = set(await db.get_panel_access_roles(guild.id))
        editor_roles = set(await db.get_message_editor_roles(guild.id))
        member_roles = {role.id for role in member.roles} if member else set()
        can_publish = manager or bool(member_roles & panel_roles)
        can_edit = can_publish or bool(member_roles & editor_roles)
        if not can_edit:
            raise web.HTTPForbidden(text="Tu ne peux pas modifier les messages de ce serveur.")
        return session, guild, admin, can_publish

    async def _can_access_guild(self, user_id: int, guild: discord.Guild) -> bool:
        if user_id in config.OWNER_PANEL_USER_IDS:
            return True
        member = guild.get_member(user_id)
        if not member:
            return False
        if member.guild_permissions.manage_guild or member.guild_permissions.administrator:
            return True
        allowed = set(await db.get_panel_access_roles(guild.id))
        if allowed.intersection(role.id for role in member.roles):
            return True
        editor_roles = set(await db.get_message_editor_roles(guild.id))
        return bool(editor_roles.intersection(role.id for role in member.roles))

    @staticmethod
    def _redirect(guild_id: int, message: str):
        raise web.HTTPFound(f"{PREFIX}/guild/{guild_id}?{urlencode({'ok': message})}")

    @staticmethod
    def _select(name: str, items, selected=None, allow_none=True, multiple=False):
        attrs = " multiple" if multiple else ""
        html_items = []
        if allow_none and not multiple:
            html_items.append('<option value="">— Aucun —</option>')
        selected_set = set(selected or []) if multiple else set()
        for item_id, label in items:
            chosen = item_id in selected_set if multiple else str(item_id) == str(selected)
            html_items.append(f'<option value="{item_id}"{" selected" if chosen else ""}>{esc(label)}</option>')
        return f'<select name="{esc(name)}"{attrs}>{"".join(html_items)}</select>'

    async def static_file(self, request):
        name = request.match_info["name"]
        content_type = STATIC_FILES.get(name)
        path = STATIC_DIR / name
        if content_type is None or not path.is_file():
            raise web.HTTPNotFound()
        response = web.FileResponse(path, headers={
            "Content-Type": content_type,
            # L'URL contient l'empreinte du fichier : le cache peut être long.
            "Cache-Control": "public, max-age=31536000, immutable",
        })
        return response

    async def health(self, request):
        return web.json_response({"status": "ok", "bot_ready": self.bot.is_ready()})

    async def home(self, request):
        if self._session(request):
            raise web.HTTPFound(f"{PREFIX}/dashboard")
        body = ('<section class="card"><span class="pill">Bot principal · Administration sécurisée</span>'
                '<h1>Administre Le Fleau.</h1><p>Configure l’économie, les tickets, les logs, l’anti-raid, '
                'les sanctions, les giveaways et la boutique personnalisée depuis une seule interface.</p>'
                f'<a class="btn" href="{PREFIX}/auth/login">Continuer avec Discord</a></section>')
        return self._page("Connexion", body, login_page=True)

    async def login(self, request):
        now = time.time()
        self.oauth_states = {key: expires for key, expires in self.oauth_states.items() if expires > now}
        state = secrets.token_urlsafe(32)
        self.oauth_states[state] = now + 600
        params = urlencode({
            "client_id": config.PANEL_CLIENT_ID,
            "redirect_uri": f"{config.PANEL_BASE_URL}/auth/callback",
            "response_type": "code",
            "scope": "identify",
            "state": state,
        })
        response = web.HTTPFound(f"{DISCORD_AUTHORIZE}?{params}")
        response.set_cookie(STATE_COOKIE, state, max_age=600, secure=True, httponly=True, samesite="Lax")
        raise response

    async def callback(self, request):
        state = request.query.get("state", "")
        expected = request.cookies.get(STATE_COOKIE, "")
        if not state or not hmac.compare_digest(state, expected) or self.oauth_states.pop(state, 0) < time.time():
            raise web.HTTPBadRequest(text="Connexion expirée ou invalide.")
        code = request.query.get("code")
        if not code or not self.http:
            raise web.HTTPBadRequest(text="Discord n'a pas fourni de code d'autorisation.")
        async with self.http.post(DISCORD_TOKEN, data={
            "client_id": config.PANEL_CLIENT_ID,
            "client_secret": config.PANEL_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{config.PANEL_BASE_URL}/auth/callback",
        }) as token_response:
            if token_response.status != 200:
                logger.error("Echange OAuth Discord refuse (HTTP %s)", token_response.status)
                raise web.HTTPBadGateway(text="Discord a refusé la connexion.")
            token = await token_response.json()
        async with self.http.get(DISCORD_ME, headers={"Authorization": f"Bearer {token['access_token']}"}) as me_response:
            if me_response.status != 200:
                raise web.HTTPBadGateway(text="Impossible de lire le profil Discord.")
            user = await me_response.json()
        session = {
            "uid": str(user["id"]),
            "name": user.get("global_name") or user["username"],
            "csrf": secrets.token_urlsafe(24),
            "exp": int(time.time()) + 8 * 3600,
        }
        response = web.HTTPFound(f"{PREFIX}/dashboard")
        response.set_cookie(COOKIE_NAME, self._encode_session(session), max_age=8 * 3600,
                            secure=True, httponly=True, samesite="Lax",
                            domain=config.PANEL_COOKIE_DOMAIN, path="/")
        response.del_cookie(STATE_COOKIE)
        raise response

    async def logout(self, request):
        session = self._require_session(request)
        form = await request.post()
        self._csrf(request, session, form)
        response = web.HTTPFound("/")
        response.del_cookie(COOKIE_NAME, domain=config.PANEL_COOKIE_DOMAIN, path="/")
        raise response

    async def dashboard(self, request):
        session = self._require_session(request)
        accessible = [guild for guild in self.bot.guilds if await self._can_access_guild(int(session["uid"]), guild)]
        cards = "".join(
            f'<a class="server" href="{PREFIX}/guild/{guild.id}"><div class="server-head">{guild_icon(guild)}'
            f'<div class="server-meta"><h2>{esc(guild.name)}</h2>'
            f'<span class="pill">{guild.member_count or 0} membres</span></div></div>'
            f'<p>Configurer le bot →</p></a>' for guild in accessible
        ) or '<div class="card"><h2>Aucun serveur accessible</h2><p class="hint">Tu dois avoir la permission Gérer le serveur ou un rôle autorisé.</p></div>'
        body = f'<div class="hero"><div><h1>Tes serveurs</h1><p>Sélectionne un serveur à configurer.</p></div></div><div class="grid">{cards}</div>'
        return self._page("Tableau de bord", body, session)

    async def guild_page(self, request):
        # Les éditeurs de messages ne voient jamais les autres fonctions du panel.
        try:
            session, guild, member, is_admin = await self._access(request)
        except web.HTTPForbidden:
            session, guild, _, _ = await self._message_access(request)
            raise web.HTTPFound(f"{PREFIX}/guild/{guild.id}/messages")
        text_channels = [(c.id, f"#{c.name}") for c in guild.text_channels]
        categories = [(c.id, c.name) for c in guild.categories]
        roles = [(r.id, f"@{r.name}") for r in guild.roles if r != guild.default_role and not r.managed]
        panel_roles = await db.get_panel_access_roles(guild.id)
        anti = await db.get_antiraid_settings(guild.id) or {}
        log_rows = {row["category"]: row for row in await db.get_all_log_settings(guild.id)}
        ticket_log = await db.get_ticket_log_channel(guild.id)
        tracking = await db.get_tracking_channel(guild.id)
        ticket_categories = await db.get_ticket_categories(guild.id)
        sanction = await db.get_sanction_log(guild.id) or {}
        economy = await db.get_guild_economy_stats(guild.id)
        custom_items = await db.get_custom_items(guild.id, include_inactive=True)
        csrf = esc(session["csrf"])
        flash = f'<div class="flash">{esc(request.query.get("ok"))}</div>' if request.query.get("ok") else ""

        access_card = ""
        economy_card = ""
        if is_admin:
            access_card = f'''<section class="card"><h2>Accès au panel</h2><p class="hint">Les administrateurs ont toujours accès. Sélectionne les rôles supplémentaires autorisés.</p>
            <form method="post" action="{PREFIX}/guild/{guild.id}/access"><input type="hidden" name="csrf" value="{csrf}">
            <label>Rôles autorisés</label>{self._select("role_ids", roles, panel_roles, False, True)}
            <button class="btn">Enregistrer les accès</button></form></section>'''
            economy_card = f'''<section class="card wide"><h2>Économie du serveur</h2>
            <p class="hint">{economy["user_count"]} joueurs · {economy["total_wallet"]:,} {config.CURRENCY_NAME} en circulation · {economy["total_bounty"]:,} de primes</p>
            <form method="post" action="{PREFIX}/guild/{guild.id}/economy"><input type="hidden" name="csrf" value="{csrf}">
            <label>ID du membre Discord</label><input name="user_id" inputmode="numeric" required placeholder="123456789...">
            <div class="row"><div><label>Modification des {esc(config.CURRENCY_NAME)} (+ ou −)</label>
            <input type="number" name="wallet_delta" min="-1000000000" max="1000000000" value="0"></div>
            <div><label>Modification de la prime (+ ou −)</label>
            <input type="number" name="bounty_delta" min="-1000000000" max="1000000000" value="0"></div></div>
            <button class="btn">Appliquer la modification</button></form></section>'''

        log_controls = "".join(
            f'<label>{esc(label)}</label>{self._select("log_" + key, text_channels, (log_rows.get(key) or {}).get("channel_id") if (log_rows.get(key) or {}).get("enabled") else None)}'
            for key, label in LOG_CATEGORIES.items()
        )
        category_row_parts = []
        for cat in ticket_categories:
            configured_roles = [guild.get_role(role_id) for role_id in cat.get("role_ids", [])]
            role_names = ", ".join(f"@{role.name}" for role in configured_roles if role) or "Aucun rôle pingé"
            category_row_parts.append(
                f'<div class="category"><div><strong>{esc(cat["display_name"])}</strong>'
                f'<div class="muted">{esc(cat["name"])} · {esc(role_names)}</div></div>'
                f'<form method="post" action="{PREFIX}/guild/{guild.id}/ticket-category-delete">'
                f'<input type="hidden" name="csrf" value="{csrf}">'
                f'<input type="hidden" name="name" value="{esc(cat["name"])}">'
                f'<button class="btn danger">Supprimer</button></form></div>'
            )
        category_rows = "".join(category_row_parts) or '<p class="hint">Aucune catégorie configurée.</p>'
        destination_guilds = [(g.id, g.name) for g in self.bot.guilds if await self._can_access_guild(int(session["uid"]), g)]
        custom_item_rows = "".join(
            f'<div class="category"><div><strong>{esc(item["emoji"])} {esc(item["name"])}</strong>'
            f'<div class="muted">{item["price"]:,} {esc(config.CURRENCY_NAME)} · '
            f'{"En vente" if item["active"] else "Désactivé"}</div><div>{esc(item["description"])}</div></div>'
            f'<form method="post" action="{PREFIX}/guild/{guild.id}/custom-item-toggle">'
            f'<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="name" value="{esc(item["name"])}">'
            f'<input type="hidden" name="active" value="{0 if item["active"] else 1}">'
            f'<button class="btn {"danger" if item["active"] else "secondary"}">'
            f'{"Retirer" if item["active"] else "Réactiver"}</button></form></div>'
            for item in custom_items
        ) or '<p class="hint">Aucun objet personnalisé configuré.</p>'

        body = f'''{flash}<div class="hero"><div><a class="muted" href="{PREFIX}/dashboard">← Serveurs</a><div class="hero-title">{guild_icon(guild, 256)}<h1>{server_title(guild.name)}</h1></div><p>Configuration appliquée immédiatement au bot.</p></div></div>
        <div class="sections">
        {access_card}
        {economy_card}
        <section class="card wide"><h2>Boutique personnalisée</h2>
        <p class="hint">Le catalogue est propre à ce serveur. Ajouter un objet portant un nom existant met à jour son prix, sa description et son emoji.</p>
        <div class="row"><div>{custom_item_rows}</div>
        <form method="post" action="{PREFIX}/guild/{guild.id}/custom-item"><input type="hidden" name="csrf" value="{csrf}">
        <label>Nom de l’objet</label><input name="name" minlength="1" maxlength="50" required placeholder="Clé VIP">
        <div class="row"><div><label>Prix unitaire</label><input type="number" name="price" min="1" max="1000000000" required></div>
        <div><label>Emoji</label><input name="emoji" maxlength="32" value="📦"></div></div>
        <label>Description</label><textarea name="description" minlength="1" maxlength="300" required placeholder="Décris l’utilité de cet objet."></textarea>
        <button class="btn">Ajouter ou mettre à jour</button></form></div></section>
        <section class="card"><h2>Protection anti-raid</h2><form method="post" action="{PREFIX}/guild/{guild.id}/antiraid"><input type="hidden" name="csrf" value="{csrf}">
        <label class="check"><input type="checkbox" name="enabled" value="1" {"checked" if anti.get("enabled") else ""}> Protection activée</label>
        <div class="row"><div><label>Seuil d’arrivées</label><input type="number" min="3" max="50" name="threshold" value="{anti.get('join_threshold',6)}"></div>
        <div><label>Fenêtre</label><input name="window" value="{format_duration(anti.get('window_seconds',10))}"></div></div>
        <label>Âge minimal du compte</label><input name="min_age" value="{format_duration(anti.get('min_account_age_seconds',604800))}">
        <div class="row"><div><label>Salon d’alertes</label>{self._select("log_channel", text_channels, anti.get("log_channel_id"))}</div>
        <div><label>Rôle exempté</label>{self._select("bypass_role", roles, anti.get("bypass_role_id"))}</div></div>
        <button class="btn">Enregistrer l’anti-raid</button></form></section>

        <section class="card"><h2>Logs Discord</h2><p class="hint">Choisis un salon ou « Aucun » pour désactiver la catégorie.</p>
        <form method="post" action="{PREFIX}/guild/{guild.id}/logs"><input type="hidden" name="csrf" value="{csrf}">{log_controls}<button class="btn">Enregistrer les logs</button></form></section>

        <section class="card"><h2>Réglages des tickets</h2><form method="post" action="{PREFIX}/guild/{guild.id}/tickets"><input type="hidden" name="csrf" value="{csrf}">
        <label>Salon des transcriptions</label>{self._select("ticket_log", text_channels, ticket_log)}
        <label>Salon du suivi public</label>{self._select("tracking", text_channels, tracking)}
        <button class="btn">Enregistrer les tickets</button></form></section>

        <section class="card wide"><h2>Catégories de tickets</h2><div class="row"><div>{category_rows}</div><form method="post" action="{PREFIX}/guild/{guild.id}/ticket-category">
        <input type="hidden" name="csrf" value="{csrf}"><label>Nom</label><input name="name" maxlength="80" required placeholder="Support">
        <label>Catégorie Discord</label>{self._select("category_id", categories, None, False)}
        <label>Rôles du staff à autoriser et ping</label>
        <p class="hint">Maintiens Ctrl (ou Cmd sur Mac) pour sélectionner plusieurs rôles, jusqu’à 10.</p>
        {self._select("role_ids", roles, [], False, True)}<label>Emoji facultatif</label><input name="emoji" maxlength="32" placeholder="🎫">
        <label>Message d’ouverture</label><textarea name="message" required>Merci d'avoir ouvert un ticket. Décris précisément ta demande.</textarea>
        <button class="btn">Ajouter ou remplacer</button></form></div></section>

        <section class="card"><h2>Registre des sanctions</h2><form method="post" action="{PREFIX}/guild/{guild.id}/sanctions"><input type="hidden" name="csrf" value="{csrf}">
        <label>Serveur central</label>{self._select("destination_guild", destination_guilds, sanction.get("destination_guild_id"))}
        <label>ID du salon central</label><input name="destination_channel" inputmode="numeric" value="{esc(sanction.get('destination_channel_id',''))}" placeholder="123456789...">
        <button class="btn">Enregistrer le registre</button></form></section>

        <section class="card"><h2>Créer un giveaway</h2><form method="post" action="{PREFIX}/guild/{guild.id}/giveaway"><input type="hidden" name="csrf" value="{csrf}">
        <label>Lot</label><input name="prize" maxlength="200" required><div class="row"><div><label>Durée</label><input name="duration" value="1d" required></div>
        <div><label>Gagnants</label><input type="number" name="winners" min="1" max="20" value="1"></div></div>
        <label>Salon</label>{self._select("channel", text_channels, None, False)}
        <div class="row"><div><label>Rôle requis</label>{self._select("required_role", roles)}</div><div><label>Rôle de bypass</label>{self._select("bypass_role", roles)}</div></div>
        <div class="row"><div><label>Âge du compte</label><input name="account_age" value="0"></div><div><label>Ancienneté serveur</label><input name="membership" value="0"></div></div>
        <button class="btn">Publier le giveaway</button></form></section>

        <section class="card"><h2>Messages Discord</h2>
        <p class="hint">Publier des messages simples ou des embeds, les modifier par formulaire et déléguer l'édition à des rôles.</p>
        <a class="btn" href="{PREFIX}/guild/{guild.id}/messages">Gérer les messages →</a></section>

        <section class="card"><h2>Points de giveaway</h2>
        <p class="hint">Nom des points, lots, rôles par seuil, classement, ajout manuel et validation des propositions.</p>
        <a class="btn" href="{PREFIX}/guild/{guild.id}/points">Gérer les points →</a></section>

        <section class="card"><h2>Rôles d'arrivée</h2>
        <p class="hint">Rôles donnés automatiquement aux nouveaux membres et aux bots.</p>
        <a class="btn" href="{PREFIX}/guild/{guild.id}/join-roles">Gérer les rôles d'arrivée →</a></section>
        </div>'''
        return self._page(guild.name, body, session, titles=True)

    async def save_economy(self, request):
        session, guild, _, _ = await self._access(request, require_admin=True)
        form = await request.post(); self._csrf(request, session, form)
        try:
            user_id = int(form.get("user_id", ""))
            wallet_delta = int(form.get("wallet_delta", "0"))
            bounty_delta = int(form.get("bounty_delta", "0"))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="ID ou montant invalide.")
        if not guild.get_member(user_id):
            raise web.HTTPBadRequest(text="Ce membre est introuvable sur le serveur.")
        if not wallet_delta and not bounty_delta:
            raise web.HTTPBadRequest(text="Indique au moins une modification différente de zéro.")
        if any(abs(value) > 1_000_000_000 for value in (wallet_delta, bounty_delta)):
            raise web.HTTPBadRequest(text="Une modification dépasse la limite autorisée.")
        current = await db.get_user(user_id, guild.id)
        wallet = current["wallet"]
        bounty = current["bounty"]
        if wallet_delta:
            wallet = await db.update_wallet(user_id, guild.id, wallet_delta)
        if bounty_delta:
            bounty = await db.update_bounty(user_id, guild.id, bounty_delta)
        target = guild.get_member(user_id)
        self._redirect(
            guild.id,
            f"Économie de {target.display_name} mise à jour : {wallet:,} {config.CURRENCY_NAME}, prime {bounty:,}.",
        )

    async def save_custom_item(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        name = " ".join(form.get("name", "").split())
        description = form.get("description", "").strip()
        emoji = form.get("emoji", "").strip() or "📦"
        try:
            price = int(form.get("price", ""))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="Le prix de l'objet est invalide.")
        if not 1 <= len(name) <= 50:
            raise web.HTTPBadRequest(text="Le nom doit contenir entre 1 et 50 caractères.")
        if not 1 <= len(description) <= 300:
            raise web.HTTPBadRequest(text="La description doit contenir entre 1 et 300 caractères.")
        if len(emoji) > 32:
            raise web.HTTPBadRequest(text="L'emoji est trop long.")
        if not 1 <= price <= 1_000_000_000:
            raise web.HTTPBadRequest(text="Le prix doit être compris entre 1 et 1 000 000 000.")
        previous = await db.get_custom_item(guild.id, name, include_inactive=True)
        await db.upsert_custom_item(guild.id, name, description, price, emoji, int(session["uid"]))
        action = "mis à jour et réactivé" if previous else "ajouté"
        self._redirect(guild.id, f"Objet « {name} » {action}.")

    async def toggle_custom_item(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        name = form.get("name", "").strip()
        active = form.get("active") == "1"
        if not name or not await db.set_custom_item_active(guild.id, name, active):
            raise web.HTTPNotFound(text="Cet objet n'existe plus sur ce serveur.")
        self._redirect(guild.id, f"Objet « {name} » {'réactivé' if active else 'retiré de la vente'}.")

    # ------------------------------------------------------------------
    # Points de giveaway (équivalent des commandes /points, /points-admin et des propositions)
    # ------------------------------------------------------------------

    @staticmethod
    def _points_redirect(guild_id: int, message: str):
        raise web.HTTPFound(f"{PREFIX}/guild/{guild_id}/points?{urlencode({'ok': message})}")

    @staticmethod
    def _int_field(form, name: str, low: int, high: int, label: str) -> int:
        try:
            value = int(str(form.get(name, "")).strip())
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text=f"{label} invalide.")
        if not low <= value <= high:
            raise web.HTTPBadRequest(text=f"{label} doit être compris entre {low:,} et {high:,}.")
        return value

    def _points_role_problem(self, guild: discord.Guild, role: discord.Role, member, user_id: int) -> str | None:
        """Mêmes contrôles que /points-admin role-add, adaptés au panel."""
        me = guild.me
        if role.is_default() or role.managed:
            return "Ce rôle ne peut pas être utilisé pour les récompenses de points."
        if me is None or not me.guild_permissions.manage_roles:
            return "Le bot doit posséder la permission Gérer les rôles."
        if role >= me.top_role:
            return "Le rôle choisi doit être placé sous le rôle le plus élevé du bot."
        privileged = user_id in config.OWNER_PANEL_USER_IDS or guild.owner_id == user_id
        if not privileged and member is not None and role >= member.top_role:
            return "Tu ne peux pas configurer un rôle égal ou supérieur à ton rôle principal."
        return None

    async def _grant_roles(self, member: discord.Member | None, points: int | None) -> list[discord.Role]:
        cog = self.bot.get_cog("CommunityTools")
        if cog is None or member is None or points is None:
            return []
        return await cog._grant_point_roles(member, points)

    async def points_page(self, request):
        session, guild, member, is_admin = await self._access(request)
        csrf = esc(session["csrf"])
        hidden = f'<input type="hidden" name="csrf" value="{csrf}">'
        base = f"{PREFIX}/guild/{guild.id}/points"
        point_name = await db.get_giveaway_points_name(guild.id)
        items = await db.get_giveaway_prize_items(guild.id, include_inactive=True)
        point_roles = await db.get_giveaway_point_roles(guild.id)
        balances = await db.get_giveaway_member_point_balances(guild.id)
        proposals = [p for p in await db.get_pending_giveaway_proposals() if p["guild_id"] == guild.id]
        roles = [(r.id, f"@{r.name}") for r in guild.roles if r != guild.default_role and not r.managed]
        flash = f'<div class="flash">{esc(request.query.get("ok"))}</div>' if request.query.get("ok") else ""

        # --- Propositions en attente
        proposal_parts = []
        for prop in proposals:
            proposer = guild.get_member(prop["proposer_id"])
            proposer_name = proposer.display_name if proposer else f"ID {prop['proposer_id']}"
            ticket = guild.get_channel(prop["ticket_channel_id"])
            ticket_name = f"#{ticket.name}" if ticket else "ticket supprimé"
            proposal_parts.append(
                f'<div class="category"><div><strong>#{prop["id"]} · {esc(prop["prize_name"])}</strong>'
                f'<div class="muted">{esc(proposer_name)} · {esc(ticket_name)} · '
                f'{prop["prize_points"]:,} {esc(point_name)} à la validation · '
                f'Salon : {esc(guild.get_channel(prop["target_channel_id"]).mention if prop.get("target_channel_id") and guild.get_channel(prop["target_channel_id"]) else "non configuré")} · '
                f'Gagnants : {prop.get("winner_count", 1)} · '
                f'Durée : {esc(format_duration(prop["duration_seconds"]) if prop.get("duration_seconds") else "non configurée")}</div></div>'
                f'<form method="post" action="{base}/proposal" style="display:flex;gap:8px">{hidden}'
                f'<input type="hidden" name="proposal_id" value="{prop["id"]}">'
                f'<button class="btn" name="decision" value="approve" style="margin:0">Approve &amp; publish</button>'
                f'<button class="btn danger" name="decision" value="deny" style="margin:0">Refuser</button></form></div>'
            )
        proposal_rows = "".join(proposal_parts) or '<p class="hint">Aucune proposition en attente.</p>'

        # --- Lots
        item_parts = []
        for item in items:
            state = "" if item["active"] else " · désactivé"
            if item["active"]:
                action = (
                    f'<form method="post" action="{base}/item-remove">{hidden}'
                    f'<input type="hidden" name="item_id" value="{item["id"]}">'
                    f'<button class="btn danger" style="margin:0">Retirer</button></form>'
                )
            else:
                action = (
                    f'<form method="post" action="{base}/item">{hidden}'
                    f'<input type="hidden" name="name" value="{esc(item["name"])}">'
                    f'<input type="hidden" name="points" value="{item["points"]}">'
                    f'<input type="hidden" name="emoji" value="{esc(item["emoji"])}">'
                    f'<button class="btn secondary" style="margin:0">Réactiver</button></form>'
                )
            item_parts.append(
                f'<div class="category"><div><strong>{esc(item["emoji"])} {esc(item["name"])}</strong>'
                f'<div class="muted">#{item["id"]} · {item["points"]:,} {esc(point_name)}{state}</div></div>{action}</div>'
            )
        item_rows = "".join(item_parts) or '<p class="hint">Aucun lot configuré.</p>'

        # --- Rôles par seuil
        role_parts = []
        for reward in point_roles:
            role = guild.get_role(reward["role_id"])
            label = f"@{role.name}" if role else f"Rôle supprimé ({reward['role_id']})"
            role_parts.append(
                f'<div class="category"><div><strong>{esc(label)}</strong>'
                f'<div class="muted">À partir de {reward["points_required"]:,} {esc(point_name)}</div></div>'
                f'<form method="post" action="{base}/role-remove">{hidden}'
                f'<input type="hidden" name="role_id" value="{reward["role_id"]}">'
                f'<button class="btn danger" style="margin:0">Retirer</button></form></div>'
            )
        role_rows = "".join(role_parts) or '<p class="hint">Aucun rôle de points configuré.</p>'

        # --- Classement
        board_parts = []
        for rank, balance in enumerate(balances[:15], start=1):
            holder = guild.get_member(balance["user_id"])
            holder_name = holder.display_name if holder else f"ID {balance['user_id']}"
            board_parts.append(
                f'<div class="category"><div><strong>{rank}. {esc(holder_name)}</strong>'
                f'<div class="muted">{balance["user_id"]}</div></div>'
                f'<span class="pill">{balance["points"]:,} {esc(point_name)}</span></div>'
            )
        board_rows = "".join(board_parts) or '<p class="hint">Personne n\'a encore de points.</p>'
        board_hint = f"{len(balances)} membre(s) avec des points." if balances else ""

        body = f'''{flash}<div class="hero"><div><a class="muted" href="{PREFIX}/guild/{guild.id}">← {esc(guild.name)}</a>
        <h1>Points de giveaway</h1><p>Les points s'appellent « {esc(point_name)} » sur ce serveur.</p></div></div>
        <div class="sections">
        <section class="card wide"><h2>Propositions en attente</h2>
        <p class="hint">Approve &amp; publish publie immédiatement le giveaway et attribue les points au proposant. Les messages de suivi sont mis à jour.</p>{proposal_rows}</section>

        <section class="card"><h2>Nom des points</h2>
        <form method="post" action="{base}/config">{hidden}
        <label>Nom (exemples : Tickets, Étoiles, Crédits)</label>
        <input name="name" minlength="1" maxlength="32" required value="{esc(point_name)}">
        <button class="btn">Enregistrer le nom</button></form></section>

        <section class="card"><h2>Ajouter des points à un membre</h2>
        <form method="post" action="{base}/add">{hidden}
        <label>ID du membre Discord</label><input name="user_id" inputmode="numeric" required placeholder="123456789...">
        <label>Points à ajouter</label><input type="number" name="points" min="1" max="1000000" value="1" required>
        <button class="btn">Ajouter les points</button></form></section>

        <section class="card"><h2>Lots de giveaway</h2>{item_rows}
        <form method="post" action="{base}/item">{hidden}
        <label>Nom du lot</label><input name="name" minlength="1" maxlength="80" required placeholder="Nitro 1 mois">
        <div class="row"><div><label>Points attribués</label><input type="number" name="points" min="1" max="1000000" required></div>
        <div><label>Emoji</label><input name="emoji" maxlength="32" value="🎁"></div></div>
        <button class="btn">Ajouter ou mettre à jour</button></form></section>

        <section class="card"><h2>Rôles par seuil de points</h2>{role_rows}
        <form method="post" action="{base}/role">{hidden}
        <label>Rôle à attribuer</label>{self._select("role_id", roles, None, False)}
        <label>Points requis</label><input type="number" name="points" min="1" max="1000000" required>
        <button class="btn">Ajouter ou mettre à jour</button></form>
        <p class="hint">Les membres qui ont déjà assez de points reçoivent le rôle immédiatement. Un rôle acquis n'est jamais retiré.</p></section>

        <section class="card wide"><h2>Classement</h2><p class="hint">{esc(board_hint)}</p>{board_rows}</section>
        </div>'''
        return self._page("Points de giveaway", body, session)

    async def points_save_config(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        name = " ".join(form.get("name", "").split())
        if not 1 <= len(name) <= 32:
            raise web.HTTPBadRequest(text="Le nom doit contenir entre 1 et 32 caractères.")
        await db.set_giveaway_points_name(guild.id, name)
        self._points_redirect(guild.id, f"Les points s'appellent maintenant « {name} ».")

    async def points_add(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        user_id = self._int_field(form, "user_id", 1, 2**63 - 1, "L'ID du membre")
        points = self._int_field(form, "points", 1, 1_000_000, "Le nombre de points")
        target = guild.get_member(user_id)
        if target is None:
            raise web.HTTPBadRequest(text="Ce membre est introuvable sur le serveur.")
        total = await db.add_giveaway_member_points(guild.id, user_id, points)
        granted = await self._grant_roles(target, total)
        point_name = await db.get_giveaway_points_name(guild.id)
        message = f"{target.display_name} reçoit {points:,} {point_name} (total : {total:,})."
        if granted:
            message += " Rôle(s) ajouté(s) : " + ", ".join(f"@{role.name}" for role in granted) + "."
        self._points_redirect(guild.id, message)

    async def points_save_item(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        name = " ".join(form.get("name", "").split())
        emoji = form.get("emoji", "").strip()[:32] or "🎁"
        points = self._int_field(form, "points", 1, 1_000_000, "Le nombre de points")
        if not 1 <= len(name) <= 80:
            raise web.HTTPBadRequest(text="Le nom du lot doit contenir entre 1 et 80 caractères.")
        item = await db.upsert_giveaway_prize_item(guild.id, name, points, emoji, int(session["uid"]))
        self._points_redirect(guild.id, f"Lot configuré : {item['emoji']} {item['name']} ({item['points']:,} points).")

    async def points_remove_item(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        item_id = self._int_field(form, "item_id", 1, 2**63 - 1, "L'identifiant du lot")
        if not await db.deactivate_giveaway_prize_item(guild.id, item_id):
            raise web.HTTPNotFound(text="Lot introuvable.")
        self._points_redirect(guild.id, "Lot retiré de la liste.")

    async def points_save_role(self, request):
        session, guild, member, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        role_id = self._int_field(form, "role_id", 1, 2**63 - 1, "Le rôle")
        points = self._int_field(form, "points", 1, 1_000_000, "Le nombre de points")
        role = guild.get_role(role_id)
        if role is None:
            raise web.HTTPBadRequest(text="Rôle introuvable sur ce serveur.")
        user_id = int(session["uid"])
        problem = self._points_role_problem(guild, role, member, user_id)
        if problem:
            raise web.HTTPBadRequest(text=problem)
        await db.add_giveaway_point_role(guild.id, role.id, points, user_id)
        synced = 0
        for balance in await db.get_giveaway_member_point_balances(guild.id):
            if balance["points"] < points:
                continue
            holder = guild.get_member(balance["user_id"])
            if holder and role not in holder.roles:
                if role in await self._grant_roles(holder, balance["points"]):
                    synced += 1
        point_name = await db.get_giveaway_points_name(guild.id)
        self._points_redirect(
            guild.id,
            f"@{role.name} sera ajouté dès {points:,} {point_name}. Synchronisation : {synced} rôle(s) ajouté(s).",
        )

    async def points_remove_role(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        role_id = self._int_field(form, "role_id", 1, 2**63 - 1, "Le rôle")
        if not await db.remove_giveaway_point_role(guild.id, role_id):
            raise web.HTTPNotFound(text="Ce rôle n'a pas de seuil configuré.")
        self._points_redirect(guild.id, "Règle de rôle supprimée.")

    async def points_review_proposal(self, request):
        session, guild, member, is_admin = await self._access(request)
        if not (is_admin or (member and member.guild_permissions.manage_guild)):
            raise web.HTTPForbidden(text="Seuls les responsables du serveur peuvent traiter les propositions.")
        form = await request.post(); self._csrf(request, session, form)
        proposal_id = self._int_field(form, "proposal_id", 1, 2**63 - 1, "La proposition")
        decision = form.get("decision", "")
        if decision not in {"approve", "deny"}:
            raise web.HTTPBadRequest(text="Décision invalide.")
        approved = decision == "approve"
        proposal = await db.get_giveaway_proposal(proposal_id)
        if proposal is None or proposal["guild_id"] != guild.id:
            raise web.HTTPNotFound(text="Proposition introuvable.")
        reviewer_id = int(session["uid"])
        cog = self.bot.get_cog("CommunityTools")
        if cog is None:
            raise web.HTTPServiceUnavailable(text="Le module Giveaway n'est pas disponible.")
        try:
            details = await cog.process_giveaway_proposal(guild, proposal_id, reviewer_id, approved)
        except ValueError as exc:
            self._points_redirect(guild.id, f"Erreur : {exc}")
        except discord.HTTPException as exc:
            self._points_redirect(guild.id, f"Publication impossible : {exc}")
        self._points_redirect(guild.id, details)

    # ------------------------------------------------------------------
    # Rôles d'arrivée (équivalent de /autorole)
    # ------------------------------------------------------------------

    @staticmethod
    def _join_roles_redirect(guild_id: int, message: str):
        raise web.HTTPFound(f"{PREFIX}/guild/{guild_id}/join-roles?{urlencode({'ok': message})}")

    async def join_roles_page(self, request):
        session, guild, member, is_admin = await self._access(request)
        hidden = f'<input type="hidden" name="csrf" value="{esc(session["csrf"])}">'
        base = f"{PREFIX}/guild/{guild.id}/join-roles"
        rules = await db.get_join_roles(guild.id)
        settings = await db.get_join_role_settings(guild.id)
        roles = [(r.id, f"@{r.name}") for r in guild.roles if r != guild.default_role and not r.managed]
        flash = f'<div class="flash">{esc(request.query.get("ok"))}</div>' if request.query.get("ok") else ""

        rows = []
        for rule in rules:
            role = guild.get_role(rule["role_id"])
            label = f"@{role.name}" if role else f"Rôle supprimé ({rule['role_id']})"
            rows.append(
                f'<div class="category"><div><strong>{esc(label)}</strong>'
                f'<div class="muted">{esc(TARGET_LABELS[rule["target"]])}</div></div>'
                f'<form method="post" action="{base}/remove">{hidden}'
                f'<input type="hidden" name="role_id" value="{rule["role_id"]}">'
                f'<button class="btn danger" style="margin:0">Retirer</button></form></div>'
            )
        rule_rows = "".join(rows) or '<p class="hint">Aucun rôle d\'arrivée configuré.</p>'
        target_options = "".join(
            f'<option value="{value}">{esc(label)}</option>' for value, label in TARGET_LABELS.items()
        )
        wait = settings["wait_screening"]

        body = f'''{flash}<div class="hero"><div><a class="muted" href="{PREFIX}/guild/{guild.id}">← {esc(guild.name)}</a>
        <h1>Rôles d'arrivée</h1><p>Donnés automatiquement quand quelqu'un rejoint le serveur ({len(rules)}/{MAX_JOIN_ROLES}).</p></div></div>
        <div class="sections">
        <section class="card"><h2>Rôles configurés</h2>{rule_rows}</section>

        <section class="card"><h2>Ajouter un rôle</h2>
        <form method="post" action="{base}/add">{hidden}
        <label>Rôle à donner</label>{self._select("role_id", roles, None, False)}
        <label>Qui le reçoit ?</label><select name="target">{target_options}</select>
        <button class="btn">Ajouter ou mettre à jour</button></form></section>

        <section class="card"><h2>Validation du règlement</h2>
        <p class="hint">Si l'écran d'accueil Discord (règlement à accepter) est activé, les rôles peuvent être donnés seulement une fois le règlement validé.</p>
        <form method="post" action="{base}/settings">{hidden}
        <label>Moment de l'attribution</label>
        <select name="wait_screening">
        <option value="1"{" selected" if wait else ""}>Après validation du règlement</option>
        <option value="0"{"" if wait else " selected"}>Dès l'arrivée</option></select>
        <button class="btn">Enregistrer</button></form></section>
        </div>'''
        return self._page("Rôles d'arrivée", body, session)

    async def join_roles_add(self, request):
        session, guild, member, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        role_id = self._int_field(form, "role_id", 1, 2**63 - 1, "Le rôle")
        target = form.get("target", "all")
        if target not in TARGET_LABELS:
            raise web.HTTPBadRequest(text="Cible invalide.")
        role = guild.get_role(role_id)
        if role is None:
            raise web.HTTPBadRequest(text="Rôle introuvable sur ce serveur.")
        user_id = int(session["uid"])
        privileged = user_id in config.OWNER_PANEL_USER_IDS or guild.owner_id == user_id
        problem = role_assign_problem(guild, role, member, privileged)
        if problem:
            raise web.HTTPBadRequest(text=problem)
        existing = {rule["role_id"] for rule in await db.get_join_roles(guild.id)}
        if len(existing) >= MAX_JOIN_ROLES and role.id not in existing:
            raise web.HTTPBadRequest(text=f"Maximum {MAX_JOIN_ROLES} rôles d'arrivée.")
        await db.add_join_role(guild.id, role.id, target, user_id)
        self._join_roles_redirect(guild.id, f"@{role.name} sera donné à l'arrivée ({TARGET_LABELS[target].lower()}).")

    async def join_roles_remove(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        role_id = self._int_field(form, "role_id", 1, 2**63 - 1, "Le rôle")
        if not await db.remove_join_role(guild.id, role_id):
            raise web.HTTPNotFound(text="Ce rôle n'est pas un rôle d'arrivée.")
        self._join_roles_redirect(guild.id, "Rôle retiré des rôles d'arrivée.")

    async def join_roles_settings(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        wait = form.get("wait_screening") == "1"
        await db.set_join_role_wait_screening(guild.id, wait)
        self._join_roles_redirect(
            guild.id,
            "Les rôles seront donnés après validation du règlement." if wait else "Les rôles seront donnés dès l'arrivée.",
        )

    async def save_access(self, request):
        session, guild, _, _ = await self._access(request, require_admin=True)
        form = await request.post(); self._csrf(request, session, form)
        valid = {role.id for role in guild.roles if not role.managed}
        role_ids = [int(value) for value in form.getall("role_ids", []) if value.isdigit() and int(value) in valid]
        await db.set_panel_access_roles(guild.id, role_ids)
        self._redirect(guild.id, "Accès au panel enregistrés.")

    async def save_antiraid(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        window, min_age = parse_duration(form.get("window", "")), parse_duration(form.get("min_age", ""))
        threshold = int(form.get("threshold", 6))
        if not window or min_age is None or not 3 <= threshold <= 50:
            raise web.HTTPBadRequest(text="Paramètres anti-raid invalides.")
        channel = guild.get_channel(int(form["log_channel"])) if form.get("log_channel", "").isdigit() else None
        role = guild.get_role(int(form["bypass_role"])) if form.get("bypass_role", "").isdigit() else None
        await db.set_antiraid_settings(guild.id, form.get("enabled") == "1", threshold, window, min_age,
                                       channel.id if isinstance(channel, discord.TextChannel) else None,
                                       role.id if role else None)
        self._redirect(guild.id, "Protection anti-raid mise à jour.")

    async def save_logs(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        for key in LOG_CATEGORIES:
            value = form.get("log_" + key, "")
            channel = guild.get_channel(int(value)) if value.isdigit() else None
            if isinstance(channel, discord.TextChannel):
                await db.set_log_channel(guild.id, key, channel.id)
            else:
                await db.disable_log_category(guild.id, key)
        self._redirect(guild.id, "Configuration des logs enregistrée.")

    async def save_tickets(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        log = guild.get_channel(int(form["ticket_log"])) if form.get("ticket_log", "").isdigit() else None
        tracking = guild.get_channel(int(form["tracking"])) if form.get("tracking", "").isdigit() else None
        await db.set_ticket_log_channel(guild.id, log.id if isinstance(log, discord.TextChannel) else None)
        await db.set_tracking_channel(guild.id, tracking.id if isinstance(tracking, discord.TextChannel) else None)
        self._redirect(guild.id, "Réglages des tickets enregistrés.")

    async def save_ticket_category(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        category = guild.get_channel(int(form.get("category_id", 0)))
        valid_role_ids = {
            role.id for role in guild.roles if role != guild.default_role and not role.managed
        }
        role_ids = list(dict.fromkeys(
            int(value)
            for value in form.getall("role_ids", [])
            if value.isdigit() and int(value) in valid_role_ids
        ))
        if len(role_ids) > 10:
            raise web.HTTPBadRequest(text="Une catégorie peut contenir au maximum 10 rôles de staff.")
        name, message = form.get("name", "").strip(), form.get("message", "").strip()
        if not name or not message or not isinstance(category, discord.CategoryChannel):
            raise web.HTTPBadRequest(text="Catégorie de ticket invalide.")
        await db.set_ticket_category(
            guild.id,
            name,
            category.id,
            role_ids[0] if role_ids else None,
            message[:2000],
            form.get("emoji", "").strip() or None,
            role_ids=role_ids,
        )
        self._redirect(guild.id, "Catégorie de ticket enregistrée.")

    async def delete_ticket_category(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        await db.remove_ticket_category(guild.id, form.get("name", ""))
        self._redirect(guild.id, "Catégorie de ticket supprimée.")

    async def save_sanctions(self, request):
        session, guild, _, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        if not form.get("destination_guild", "").isdigit() or not form.get("destination_channel", "").isdigit():
            raise web.HTTPBadRequest(text="Serveur ou salon central invalide.")
        destination = self.bot.get_guild(int(form["destination_guild"]))
        if not destination or not await self._can_access_guild(int(session["uid"]), destination):
            raise web.HTTPForbidden(text="Tu n'as pas accès au serveur central choisi.")
        channel = destination.get_channel(int(form["destination_channel"]))
        if not isinstance(channel, discord.TextChannel):
            raise web.HTTPBadRequest(text="Salon central introuvable.")
        await db.set_sanction_log(guild.id, destination.id, channel.id)
        self._redirect(guild.id, "Registre des sanctions configuré.")

    async def create_giveaway(self, request):
        session, guild, member, _ = await self._access(request)
        form = await request.post(); self._csrf(request, session, form)
        seconds = parse_duration(form.get("duration", ""))
        account_age = 0 if form.get("account_age", "0").strip() == "0" else parse_duration(form.get("account_age", ""))
        membership = 0 if form.get("membership", "0").strip() == "0" else parse_duration(form.get("membership", ""))
        winners = int(form.get("winners", 1))
        channel = guild.get_channel(int(form.get("channel", 0)))
        required = guild.get_role(int(form["required_role"])) if form.get("required_role", "").isdigit() else None
        bypass = guild.get_role(int(form["bypass_role"])) if form.get("bypass_role", "").isdigit() else None
        prize = form.get("prize", "").strip()
        if not prize or not seconds or account_age is None or membership is None or not 1 <= winners <= 20 or not isinstance(channel, discord.TextChannel):
            raise web.HTTPBadRequest(text="Paramètres du giveaway invalides.")
        ends_at = datetime.now(timezone.utc).timestamp() + seconds
        conditions = []
        if required: conditions.append(f"Rôle requis : {required.mention}")
        if account_age: conditions.append(f"Âge minimal du compte : {format_duration(account_age)}")
        if membership: conditions.append(f"Présence minimale : {format_duration(membership)}")
        if bypass: conditions.append(f"Contournement : {bypass.mention}")
        embed = discord.Embed(title="🎉 GIVEAWAY", description=f"## {prize[:200]}", color=config.COLOR_SUCCESS)
        embed.add_field(name="Fin", value=f"<t:{int(ends_at)}:R>", inline=True)
        embed.add_field(name="Gagnant(s)", value=str(winners), inline=True)
        embed.add_field(name="Conditions", value="\n".join(conditions) if conditions else "Aucune", inline=False)
        organizer_name = member.display_name if member else session["name"]
        embed.set_footer(text=f"Organisé depuis le panel par {organizer_name}")
        message = await channel.send(embed=embed, view=GiveawayView())
        await db.create_giveaway({
            "message_id": message.id, "guild_id": guild.id, "channel_id": channel.id,
            "prize": prize[:200], "winner_count": winners,
            "ends_at": datetime.fromtimestamp(ends_at, timezone.utc).isoformat(),
            "required_role_id": required.id if required else None,
            "bypass_role_id": bypass.id if bypass else None,
            "min_account_age_seconds": account_age, "min_membership_seconds": membership,
            "host_id": int(session["uid"]),
            "prize_item_id": None, "prize_points": 0,
        })
        self._redirect(guild.id, "Giveaway publié avec succès.")


    @staticmethod
    def _message_redirect(guild_id: int, message: str):
        raise web.HTTPFound(f"{PREFIX}/guild/{guild_id}/messages?{urlencode({'ok': message})}")

    @staticmethod
    def _message_values(form) -> dict:
        kind = str(form.get("message_type", "text"))
        if kind not in ("text", "embed"):
            raise web.HTTPBadRequest(text="Type de message invalide.")
        values = {"message_type": kind}
        limits = {"content": 2000, "embed_title": 256, "embed_description": 4096,
                  "embed_footer": 2048, "embed_image": 1000}
        for name, limit in limits.items():
            value = str(form.get(name, "")).strip()
            if len(value) > limit:
                raise web.HTTPBadRequest(text=f"Champ {name} trop long (max {limit}).")
            values[name] = value
        color = str(form.get("embed_color", "#5865F2")).strip()
        if len(color) != 7 or not color.startswith("#") or any(c not in "0123456789abcdefABCDEF" for c in color[1:]):
            raise web.HTTPBadRequest(text="Couleur hexadécimale invalide.")
        values["embed_color"] = color
        if kind == "embed" and (len(values["embed_title"]) + len(values["embed_description"]) +
                                len(values["embed_footer"]) > 6000):
            raise web.HTTPBadRequest(text="Un embed Discord ne peut pas dépasser 6000 caractères au total.")
        image = values["embed_image"]
        if image and (not image.startswith("https://") or any(c.isspace() for c in image)):
            raise web.HTTPBadRequest(text="L'image doit être une URL HTTPS valide.")
        if kind == "text" and not values["content"]:
            raise web.HTTPBadRequest(text="Le message texte ne peut pas être vide.")
        if kind == "embed" and not (values["embed_title"] or values["embed_description"] or
                                     values["embed_image"]):
            raise web.HTTPBadRequest(text="L'embed doit contenir un titre, une description ou une image.")
        return values

    @staticmethod
    def _message_payload(values: dict) -> dict:
        if values["message_type"] == "text":
            return {"content": values["content"], "embed": None,
                    "allowed_mentions": discord.AllowedMentions.none()}
        embed = discord.Embed(title=values["embed_title"] or None,
                              description=values["embed_description"] or None,
                              color=int(values["embed_color"][1:], 16))
        if values["embed_footer"]:
            embed.set_footer(text=values["embed_footer"])
        if values["embed_image"]:
            embed.set_image(url=values["embed_image"])
        return {"content": values["content"] or None, "embed": embed,
                "allowed_mentions": discord.AllowedMentions.none()}

    def _message_form(self, guild_id: int, csrf: str, channels: list, data: dict | None = None):
        data = data or {}
        editing = bool(data.get("message_id"))
        action = "edit" if editing else "create"
        kind = data.get("message_type", "text")
        fields = ''.join(
            f'<input type="hidden" name="{name}" value="{esc(value)}">'
            for name, value in (("csrf", csrf), ("message_id", data.get("message_id", "")))
        )
        channel_html = (f'<p class="hint">Salon : #{esc(data.get("channel_name", data.get("channel_id", "")))}</p>'
                        if editing else f'<label>Salon Discord</label>{self._select("channel_id", channels, None, False)}')
        type_select = (f'<select name="message_type"><option value="text"{" selected" if kind == "text" else ""}>Message normal</option>'
                       f'<option value="embed"{" selected" if kind == "embed" else ""}>Embed</option></select>')
        return f'''<form method="post" action="{PREFIX}/guild/{guild_id}/messages/{action}">
        {fields}{channel_html}<label>Format du message</label>{type_select}
        <label>Contenu du message (facultatif avec embed)</label><textarea name="content" maxlength="2000">{esc(data.get('content', ''))}</textarea>
        <p class="hint">Pour un message normal, remplir le contenu. Pour un embed, remplir les champs ci-dessous.</p>
        <div class="row"><div><label>Titre de l'embed</label><input name="embed_title" maxlength="256" value="{esc(data.get('embed_title', ''))}"></div>
        <div><label>Couleur de l'embed</label><input type="color" name="embed_color" value="{esc(data.get('embed_color', '#5865F2'))}"></div></div>
        <label>Description de l'embed</label><textarea name="embed_description" maxlength="4096">{esc(data.get('embed_description', ''))}</textarea>
        <label>Pied de page</label><input name="embed_footer" maxlength="2048" value="{esc(data.get('embed_footer', ''))}">
        <label>URL de l'image (HTTPS, optionnel)</label><input name="embed_image" maxlength="1000" value="{esc(data.get('embed_image', ''))}" placeholder="https://...">
        <button class="btn">{"Enregistrer les modifications" if editing else "Envoyer le message"}</button>
        {f'<a class="btn secondary" href="{PREFIX}/guild/{guild_id}/messages">Annuler</a>' if editing else ''}</form>'''

    async def messages_page(self, request):
        session, guild, is_admin, can_publish = await self._message_access(request)
        messages = await db.list_panel_messages(guild.id)
        edit_id = request.query.get("edit", "")
        edited = None
        if edit_id:
            if not edit_id.isdigit():
                raise web.HTTPBadRequest(text="Identifiant invalide.")
            edited = await db.get_panel_message(guild.id, int(edit_id))
            if not edited:
                raise web.HTTPNotFound(text="Message non suivi par le panel.")
            channel = guild.get_channel(edited["channel_id"])
            edited["channel_name"] = channel.name if isinstance(channel, discord.TextChannel) else str(edited["channel_id"])
        channels = [(c.id, f"#{c.name}") for c in guild.text_channels if c.permissions_for(guild.me).send_messages] if guild.me else []
        form = self._message_form(guild.id, session["csrf"], channels, edited) if (edited or can_publish) else '<p class="hint">Ton rôle permet de modifier les messages existants, pas d’en publier.</p>'
        rows = []
        for msg in messages:
            channel = guild.get_channel(msg["channel_id"])
            channel_name = f"#{channel.name}" if channel else "Salon introuvable"
            label = msg["embed_title"] or msg["content"] or msg["embed_description"] or "Embed"
            link = f"https://discord.com/channels/{guild.id}/{msg['channel_id']}/{msg['message_id']}"
            delete_form = (f'<form method="post" action="{PREFIX}/guild/{guild.id}/messages/delete" onsubmit="return confirm(\'Supprimer ce message sur Discord ?\')">'
                           f'<input type="hidden" name="csrf" value="{esc(session["csrf"])}">'
                           f'<input type="hidden" name="message_id" value="{msg["message_id"]}">'
                           '<button class="btn danger">Supprimer</button></form>') if can_publish else ''
            rows.append(f'<div class="category"><div><strong>{esc(label[:100])}</strong><p class="hint">{esc(channel_name)} · {esc(msg["message_type"])} · '
                        f'<a href="{link}" target="_blank" rel="noopener noreferrer">Voir sur Discord</a></p></div>'
                        f'<div><a class="btn secondary" href="{PREFIX}/guild/{guild.id}/messages?edit={msg["message_id"]}">Modifier</a>{delete_form}</div></div>')
        roles_card = ""
        if is_admin:
            roles = [(r.id, f"@{r.name}") for r in guild.roles if r != guild.default_role and not r.managed]
            selected = await db.get_message_editor_roles(guild.id)
            roles_card = f'''<section class="card wide"><h2>Rôles autorisés à modifier</h2>
            <p class="hint">Ces rôles ont accès uniquement à la page Messages : ils peuvent modifier les messages suivis, mais pas en envoyer ou supprimer, ni administrer le reste du bot.</p>
            <form method="post" action="{PREFIX}/guild/{guild.id}/messages/roles">
            <input type="hidden" name="csrf" value="{esc(session['csrf'])}">
            <label>Rôles éditeurs (Ctrl/Cmd pour plusieurs)</label>{self._select('role_ids', roles, selected, False, True)}
            <button class="btn">Enregistrer les rôles</button></form></section>'''
        flash = f'<div class="flash">{esc(request.query["ok"])}</div>' if request.query.get("ok") else ""
        empty_message = '<p class="hint">Aucun message envoyé depuis cette page.</p>'
        body = (f'<div class="hero"><div><h1>Messages · {esc(guild.name)}</h1>'
                f'<p>Envoyer, gérer et modifier les messages du bot depuis le site.</p></div>'
                f'<a class="btn secondary" href="{PREFIX}/dashboard">Mes serveurs</a></div>{flash}'
                f'<div class="sections"><section class="card wide"><h2>{"Modifier le message" if edited else "Nouveau message"}</h2>{form}</section>'
                f'<section class="card wide"><h2>Messages du bot suivis ({len(messages)})</h2>'
                f'{"".join(rows) or empty_message}</section>{roles_card}</div>')
        return self._page("Gestion des messages", body, session)

    async def messages_create(self, request):
        session, guild, _, can_publish = await self._message_access(request)
        if not can_publish:
            raise web.HTTPForbidden(text="Ce rôle peut modifier mais pas publier.")
        form = await request.post()
        self._csrf(request, session, form)
        channel_id = str(form.get("channel_id", ""))
        channel = guild.get_channel(int(channel_id)) if channel_id.isdigit() else None
        if not isinstance(channel, discord.TextChannel):
            raise web.HTTPBadRequest(text="Salon Discord invalide.")
        values = self._message_values(form)
        try:
            message = await channel.send(**self._message_payload(values))
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Publication impossible dans %s : %s", channel.id, exc)
            raise web.HTTPBadGateway(text="Impossible de publier : vérifie les permissions du bot dans ce salon.")
        await db.save_panel_message(guild.id, channel.id, message.id, values, int(session["uid"]))
        self._message_redirect(guild.id, "Message publié. Il est désormais modifiable depuis le panel.")

    async def messages_edit(self, request):
        session, guild, _, _ = await self._message_access(request)
        form = await request.post()
        self._csrf(request, session, form)
        message_id = str(form.get("message_id", ""))
        existing = await db.get_panel_message(guild.id, int(message_id)) if message_id.isdigit() else None
        if not existing:
            raise web.HTTPNotFound(text="Ce message ne fait pas partie des messages gérés.")
        channel = guild.get_channel(existing["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            raise web.HTTPNotFound(text="Salon Discord supprimé ou inaccessible.")
        values = self._message_values(form)
        try:
            message = await channel.fetch_message(existing["message_id"])
            if message.author.id != self.bot.user.id:
                raise web.HTTPForbidden(text="Seuls les messages envoyés par ce bot sont modifiables.")
            await message.edit(**self._message_payload(values))
        except discord.NotFound:
            raise web.HTTPNotFound(text="Message supprimé sur Discord.")
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Édition impossible du message %s : %s", message_id, exc)
            raise web.HTTPBadGateway(text="Discord a refusé la modification du message.")
        await db.save_panel_message(guild.id, existing["channel_id"], existing["message_id"],
                                    values, int(session["uid"]))
        self._message_redirect(guild.id, "Message modifié sur Discord.")

    async def messages_delete(self, request):
        session, guild, _, can_publish = await self._message_access(request)
        if not can_publish:
            raise web.HTTPForbidden(text="Tu ne peux pas supprimer de messages.")
        form = await request.post()
        self._csrf(request, session, form)
        message_id = str(form.get("message_id", ""))
        existing = await db.get_panel_message(guild.id, int(message_id)) if message_id.isdigit() else None
        if not existing:
            raise web.HTTPNotFound(text="Message introuvable.")
        channel = guild.get_channel(existing["channel_id"])
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(existing["message_id"])
                if message.author.id != self.bot.user.id:
                    raise web.HTTPForbidden(text="Ce message n'a pas été envoyé par le bot.")
                await message.delete()
            except discord.NotFound:
                pass
            except (discord.Forbidden, discord.HTTPException):
                raise web.HTTPBadGateway(text="Discord a refusé la suppression.")
        await db.remove_panel_message(guild.id, existing["message_id"])
        self._message_redirect(guild.id, "Message supprimé et retiré de la liste.")

    async def messages_roles(self, request):
        session, guild, is_admin, _ = await self._message_access(request)
        if not is_admin:
            raise web.HTTPForbidden(text="Seuls les administrateurs peuvent choisir les rôles éditeurs.")
        form = await request.post()
        self._csrf(request, session, form)
        valid = {r.id for r in guild.roles if r != guild.default_role and not r.managed}
        ids = [int(v) for v in form.getall("role_ids", []) if v.isdigit() and int(v) in valid]
        await db.set_message_editor_roles(guild.id, ids)
        self._message_redirect(guild.id, "Rôles éditeurs enregistrés.")


async def setup(bot: commands.Bot):
    await bot.add_cog(WebPanel(bot))
