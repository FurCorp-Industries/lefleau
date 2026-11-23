"""
Bot Discord de restructuration de serveur - version PANNEAU.

Une seule commande : /panel
Le panneau affiche l'état du serveur et des boutons pour :
  - modifier le message d'information, l'aperçu, l'annoncer
  - créer / supprimer des salons temporaires
  - lancer la restructuration (propriétaire uniquement + confirmation)

Placeholders utilisables dans le message : {server}, {date}, {members}
"""

import asyncio
import difflib
import hmac
import json
import os
import re
import secrets
import threading
import unicodedata
import uuid

from discord.ext import tasks
from collections import defaultdict, deque
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

import discord
import requests
from discord import app_commands
from flask import (
    Flask, Response, abort, redirect, render_template_string,
    request, session, url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix

TOKEN = os.environ["DISCORD_TOKEN"]
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"

# --- Dashboard web (facultatif) ---------------------------------------------
# Laisse ces 4 variables vides (via les variables d'environnement) si tu ne veux
# pas du site web : le bot fonctionne normalement sans lui.
OAUTH_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.environ.get("DASHBOARD_REDIRECT_URI", "")  # ex: https://xxxx.trycloudflare.com/callback
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "")
DASHBOARD_HOST = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "8091"))


def ids_from_env(name: str) -> set[int]:
    """Lit des IDs Discord séparés par des virgules sans les inscrire dans le code."""
    return {int(value) for value in os.environ.get(name, "").split(",") if value.strip().isdigit()}

# IDs Discord de personnes de confiance (en plus des admins / du propriétaire).
# Elles pourront utiliser le panneau ET lancer la restructuration. Exemple : {123456789012345678}
ALLOWED_USER_IDS = ids_from_env("CIPHER_ALLOWED_USER_IDS")

# IDs Discord des propriétaires du bot : accès total à TOUS les serveurs où le
# bot est présent via le dashboard, même sans permission Discord sur place.
# Ne mets ici QUE des comptes en qui tu as une confiance totale : elles
# pourront tout faire (y compris restructurer/bannir) sur n'importe quel
# serveur où le bot est installé.
BOT_OWNER_IDS = ids_from_env("CIPHER_OWNER_IDS")

DEFAULT_MESSAGE = {
    "title": "🚧 Restructuration du serveur",
    "body": (
        "Bonjour à tous !\n\n"
        "**{server}** est en cours de restructuration (le {date}).\n"
        "Les anciens salons et rôles ont été supprimés, une nouvelle organisation "
        "arrive très bientôt.\n\n"
        "Vous pouvez discuter dans les salons temporaires en attendant. Merci de votre patience !"
    ),
}

# --------------------------------------------------------------------------- #
# Langue du bot (/langue)
# --------------------------------------------------------------------------- #
# Couvre les messages les plus visibles (panneau, bannir/kick/mute, tickets, vérification, niveaux).
# Le reste des commandes (descriptions, erreurs moins courantes) reste en français pour l'instant.
TRANSLATIONS = {
    "fr": {
        "panel_title": "🛠️ Panneau de restructuration",
        "panel_server_stat": "{channels} salons/catégories\n{roles} rôles\n{members} membres",
        "panel_temp_channels": "🚧 Salons temporaires",
        "panel_message_field": "✉️ Message actuel",
        "panel_footer": "🚀 Lancer = suppression irréversible • réservé au propriétaire",
        "ban_confirm_label": "Confirmer la suppression",
        "banned": "🔨 Membre `{user}` banni.",
        "ban_protected": "⛔ Ce membre est protégé (propriétaire/admin/modérateur), impossible de le bannir ainsi.",
        "muted": "🔇 {member} mute pour {minutes} minute(s).",
        "unmuted": "🔊 {member} n'est plus en sourdine.",
        "kicked_escalation": "Escalade automatique : {total} avertissements",
        "warned": "✅ {member} averti ({total} avertissement(s) au total).",
        "ticket_open": "✅ Ticket créé : {channel}",
        "ticket_already": "Tu as déjà un ticket ouvert : {channel}",
        "ticket_closing": "🔒 Fermeture du ticket dans 5 secondes…",
        "verify_success": "✅ Tu es vérifié, bienvenue !",
        "level_up": "🎉 {member} passe niveau **{level}** !",
        "level_card": "📈 {member} est niveau **{level}** ({xp} XP).",
        "leaderboard_title": "🏆 **Classement XP**",
        "leaderboard_empty": "Pas encore de données.",
        "lockdown_on": "🔒 Serveur verrouillé",
        "lockdown_off": "🔓 Serveur déverrouillé",
        "admin_only": "⛔ Réservé aux administrateurs.",
    },
    "en": {
        "panel_title": "🛠️ Restructuring panel",
        "panel_server_stat": "{channels} channels/categories\n{roles} roles\n{members} members",
        "panel_temp_channels": "🚧 Temporary channels",
        "panel_message_field": "✉️ Current message",
        "panel_footer": "🚀 Launch = irreversible deletion • owner only",
        "ban_confirm_label": "Confirm deletion",
        "banned": "🔨 Member `{user}` banned.",
        "ban_protected": "⛔ This member is protected (owner/admin/moderator), can't be banned this way.",
        "muted": "🔇 {member} muted for {minutes} minute(s).",
        "unmuted": "🔊 {member} is no longer muted.",
        "kicked_escalation": "Automatic escalation: {total} warnings",
        "warned": "✅ {member} warned ({total} warning(s) total).",
        "ticket_open": "✅ Ticket created: {channel}",
        "ticket_already": "You already have an open ticket: {channel}",
        "ticket_closing": "🔒 Closing this ticket in 5 seconds…",
        "verify_success": "✅ You're verified, welcome!",
        "level_up": "🎉 {member} reached level **{level}**!",
        "level_card": "📈 {member} is level **{level}** ({xp} XP).",
        "leaderboard_title": "🏆 **XP Leaderboard**",
        "leaderboard_empty": "No data yet.",
        "lockdown_on": "🔒 Server locked down",
        "lockdown_off": "🔓 Server unlocked",
        "admin_only": "⛔ Administrators only.",
    },
}


def t(guild_id: int, key: str, **kwargs) -> str:
    lang = guild_conf(guild_id).get("lang", "fr")
    table = TRANSLATIONS.get(lang, TRANSLATIONS["fr"])
    text = table.get(key) or TRANSLATIONS["fr"].get(key, key)
    return text.format(**kwargs) if kwargs else text


# --------------------------------------------------------------------------- #
# Stockage
# --------------------------------------------------------------------------- #
DATA_BACKUP_FILE = Path("data.json.bak")


def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fichier corrompu (ex: coupure de courant en pleine écriture) -> on retente avec la sauvegarde
            if DATA_BACKUP_FILE.exists():
                try:
                    return json.loads(DATA_BACKUP_FILE.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            print("⚠️ data.json est corrompu et illisible (même la sauvegarde) : redémarrage à vide.")
            return {}
    return {}


def save_data(data: dict) -> None:
    """Écriture atomique : on écrit dans un fichier temporaire puis on remplace, pour ne jamais
    laisser data.json à moitié écrit en cas de coupure. Une copie de secours est gardée à côté."""
    tmp_path = Path("data.json.tmp")
    raw = json.dumps(data, indent=2, ensure_ascii=False)
    tmp_path.write_text(raw, encoding="utf-8")
    if DATA_FILE.exists():
        try:
            DATA_BACKUP_FILE.write_text(DATA_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    tmp_path.replace(DATA_FILE)


def guild_conf(guild_id: int) -> dict:
    conf = load_data().get(str(guild_id), {})
    conf.setdefault("message", DEFAULT_MESSAGE.copy())
    conf.setdefault("temp_channels", [])
    conf.setdefault("activity", {})
    conf.setdefault("logs", [])
    conf.setdefault("warnings", {})
    conf.setdefault("reminders", [])
    conf.setdefault("auto_role", None)
    conf.setdefault("security", {
        "antispam": {
            "enabled": False,
            "max_messages": 5,      # messages...
            "window_seconds": 7,    # ...en X secondes -> considéré comme spam
            "mute_minutes": 10,
            "max_mentions": 5,      # mentions dans un seul message -> spam
            "block_links": False,
            "allowed_domains": [],  # domaines autorisés même si block_links=True
        },
        "antiraid": {
            "enabled": False,
            "join_threshold": 5,    # arrivées...
            "window_seconds": 10,   # ...en X secondes -> déclenche l'action
            "new_account_days": 7,  # comptes créés il y a moins de X jours = suspects
            "action": "lockdown",   # lockdown | kick | ban
        },
        "lockdown_backup": {},      # permissions sauvegardées pour pouvoir déverrouiller
        "antiusurpation": {
            "enabled": False,
            "threshold": 0.82,   # ressemblance (0 à 1) à partir de laquelle on considère que c'est suspect
            "action": "alerter",  # alerter | kick
        },
        "antidelete": {
            "enabled": False,
            "threshold": 3,          # nb de suppressions...
            "window_seconds": 20,    # ...en X secondes -> déclenche la protection
            "action": "alerter",     # alerter | retirer_roles | kick | ban
            "bloquer_roles_dangereux": False,  # supprime un rôle Administrateur créé par qqn d'autre que le bot
        },
        "escalade": {
            "enabled": False,
            "mute_a": 3,       # nb d'avertissements -> mute auto
            "mute_minutes": 15,
            "kick_a": 5,       # nb d'avertissements -> kick auto (prioritaire sur le mute)
            "expiration_jours": 90,  # un avertissement plus vieux que ça ne compte plus (0 = jamais)
        },
        "surveiller_webhooks": False,
        "verrouiller_vocaux": True,  # le lockdown couvre aussi les salons vocaux si activé
        "filtre_mots": {
            "enabled": False,
            "mots": [],
        },
        "verification": {
            "enabled": False,
            "role_id": None,  # rôle donné à l'arrivée, retiré quand le membre clique sur "vérifier"
        },
    })
    conf.setdefault("temp_roles", [])
    conf.setdefault("role_reactions", {})
    conf.setdefault("log_channel_id", None)
    conf.setdefault("leveling_announce", True)
    conf.setdefault("lang", "fr")
    return conf


def log_action(guild_id: int, actor: str, action: str) -> None:
    """Enregistre une ligne de log (visible sur le site web), et la poste dans le salon de logs si réglé."""
    conf = guild_conf(guild_id)
    conf["logs"].append({"ts": datetime.now().isoformat(timespec="seconds"), "actor": actor, "action": action})
    conf["logs"] = conf["logs"][-200:]
    set_guild_conf(guild_id, conf)
    channel_id = conf.get("log_channel_id")
    if channel_id:
        guild = bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if channel is not None:
            try:
                asyncio.run_coroutine_threadsafe(channel.send(f"📝 **{actor}** : {action}"), bot.loop)
            except Exception:
                pass


def set_guild_conf(guild_id: int, conf: dict) -> None:
    data = load_data()
    data[str(guild_id)] = conf
    save_data(data)


XP_PAR_MESSAGE = 10
XP_COOLDOWN_SECONDS = 60  # un seul gain d'XP par minute, pour éviter de farmer en spammant


def touch_activity(guild_id: int, user_id: int) -> bool:
    """Enregistre que ce membre vient d'envoyer un message (horodatage + compteur + XP).
    Retourne True si ce message fait passer le membre à un niveau supérieur."""
    data = load_data()
    conf = data.setdefault(str(guild_id), {})
    conf.setdefault("message", DEFAULT_MESSAGE.copy())
    conf.setdefault("temp_channels", [])
    activity = conf.setdefault("activity", {})
    entry = activity.get(str(user_id))
    if not isinstance(entry, dict):  # compatibilité avec l'ancien format (juste une date)
        entry = {"last": entry, "count": 0, "xp": 0, "last_xp": None}
    entry.setdefault("xp", 0)
    entry.setdefault("last_xp", None)

    now = datetime.now()
    entry["last"] = now.isoformat()
    entry["count"] = entry.get("count", 0) + 1

    leveled_up = False
    last_xp = datetime.fromisoformat(entry["last_xp"]) if entry.get("last_xp") else None
    if last_xp is None or (now - last_xp).total_seconds() >= XP_COOLDOWN_SECONDS:
        old_level = entry["xp"] // 100
        entry["xp"] += XP_PAR_MESSAGE
        entry["last_xp"] = now.isoformat()
        leveled_up = (entry["xp"] // 100) > old_level

    activity[str(user_id)] = entry
    save_data(data)
    return leveled_up


def last_seen(guild_id: int, user_id: int) -> datetime | None:
    raw = guild_conf(guild_id).get("activity", {}).get(str(user_id))
    if not raw:
        return None
    last = raw["last"] if isinstance(raw, dict) else raw  # compatibilité ancien format
    return datetime.fromisoformat(last) if last else None


def message_count(guild_id: int, user_id: int) -> int:
    raw = guild_conf(guild_id).get("activity", {}).get(str(user_id))
    return raw.get("count", 0) if isinstance(raw, dict) else 0


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #
def build_embed(guild: discord.Guild) -> discord.Embed:
    msg = guild_conf(guild.id)["message"]
    fmt = {
        "server": guild.name,
        "date": datetime.now().strftime("%d/%m/%Y"),
        "members": guild.member_count,
    }
    try:
        body = msg["body"].format(**fmt)
    except (KeyError, IndexError, ValueError):
        body = msg["body"]
    return discord.Embed(
        title=msg["title"][:256],
        description=body[:4000],
        color=discord.Color.orange(),
        timestamp=datetime.now(),
    )


def temp_text_channels(guild: discord.Guild) -> list[discord.TextChannel]:
    ids = guild_conf(guild.id)["temp_channels"]
    return [c for c in (guild.get_channel(i) for i in ids) if isinstance(c, discord.TextChannel)]


def clean_names(raw: str) -> list[str]:
    return [n.strip().lower().replace(" ", "-") for n in raw.split(",") if n.strip()]


def yes(value: str) -> bool:
    return value.strip().lower() in {"oui", "o", "yes", "y", "true", "1"}


async def create_temp_channels(guild: discord.Guild, names: list[str]) -> list[discord.abc.GuildChannel]:
    """Crée une catégorie 'Restructuration' + les salons (le 1er en lecture seule)."""
    category = await guild.create_category("🚧 Restructuration")
    created: list[discord.abc.GuildChannel] = [category]
    for i, name in enumerate(names):
        overwrites = (
            {guild.default_role: discord.PermissionOverwrite(send_messages=False)} if i == 0 else {}
        )
        created.append(await guild.create_text_channel(name, category=category, overwrites=overwrites))
        await asyncio.sleep(0.3)

    conf = guild_conf(guild.id)
    conf["temp_channels"] = list({*conf["temp_channels"], *[c.id for c in created]})
    set_guild_conf(guild.id, conf)
    return created


async def run_restructure(guild: discord.Guild, names: list[str], delete_roles: bool, ping: bool) -> dict:
    stats = {"channels": 0, "roles": 0, "errors": 0}

    # 1) Salons temporaires créés EN PREMIER (le serveur n'est jamais sans salon)
    temp = await create_temp_channels(guild, names)
    keep_ids = {c.id for c in temp}
    text_temp = [c for c in temp if isinstance(c, discord.TextChannel)]

    # 2) Suppression de tous les autres salons
    for ch in list(guild.channels):
        if ch.id in keep_ids:
            continue
        try:
            await ch.delete(reason="Restructuration du serveur")
            stats["channels"] += 1
            await asyncio.sleep(0.4)
        except discord.HTTPException:
            stats["errors"] += 1

    # 3) Suppression des rôles (sauf @everyone, rôles de bots, rôles >= rôle du bot)
    if delete_roles:
        top = guild.me.top_role
        for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
            if role.is_default() or role.managed or role >= top:
                continue
            try:
                await role.delete(reason="Restructuration du serveur")
                stats["roles"] += 1
                await asyncio.sleep(0.4)
            except discord.HTTPException:
                stats["errors"] += 1

    # 4) Message d'information
    if text_temp:
        await text_temp[0].send(
            content="@everyone" if ping else None,
            embed=build_embed(guild),
            allowed_mentions=discord.AllowedMentions(everyone=ping),
        )
    return stats


# --------------------------------------------------------------------------- #
# Panneau : embed d'état
# --------------------------------------------------------------------------- #
def panel_embed(guild: discord.Guild) -> discord.Embed:
    conf = guild_conf(guild.id)
    temps = temp_text_channels(guild)
    e = discord.Embed(
        title=t(guild.id, "panel_title"),
        description=f"Serveur : **{guild.name}**",
        color=discord.Color.blurple(),
        timestamp=datetime.now(),
    )
    e.add_field(
        name="📊 Serveur actuel",
        value=t(guild.id, "panel_server_stat", channels=len(guild.channels), roles=len(guild.roles) - 1, members=guild.member_count),
        inline=True,
    )
    e.add_field(
        name=t(guild.id, "panel_temp_channels"),
        value="\n".join(c.mention for c in temps) or "Aucun",
        inline=True,
    )
    e.add_field(name=t(guild.id, "panel_message_field"), value=f"**{conf['message']['title']}**", inline=False)
    e.set_footer(text=t(guild.id, "panel_footer"))
    return e


# --------------------------------------------------------------------------- #
# Modals
# --------------------------------------------------------------------------- #
class MessageModal(discord.ui.Modal, title="Message de restructuration"):
    titre = discord.ui.TextInput(label="Titre", max_length=256)
    corps = discord.ui.TextInput(
        label="Message ({server}, {date}, {members})",
        style=discord.TextStyle.paragraph,
        max_length=4000,
    )

    def __init__(self, current: dict):
        super().__init__()
        self.titre.default = current["title"]
        self.corps.default = current["body"]

    async def on_submit(self, interaction: discord.Interaction):
        conf = guild_conf(interaction.guild_id)
        conf["message"] = {"title": str(self.titre), "body": str(self.corps)}
        set_guild_conf(interaction.guild_id, conf)
        log_action(interaction.guild_id, f"{interaction.user} (Discord)", "Message modifié")
        await interaction.response.send_message(
            "✅ Message enregistré. Aperçu :", embed=build_embed(interaction.guild), ephemeral=True
        )


class TempCreateModal(discord.ui.Modal, title="Créer un salon temporaire"):
    nom = discord.ui.TextInput(label="Nom du salon", max_length=100)
    message = discord.ui.TextInput(
        label="Message à poster (optionnel)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=2000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        ch = await interaction.guild.create_text_channel(str(self.nom).lower().replace(" ", "-"))
        conf = guild_conf(interaction.guild_id)
        conf["temp_channels"].append(ch.id)
        set_guild_conf(interaction.guild_id, conf)
        if str(self.message).strip():
            await ch.send(str(self.message), allowed_mentions=discord.AllowedMentions.none())
        log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Salon temporaire créé : #{ch.name}")
        await interaction.response.send_message(f"✅ {ch.mention} créé.", ephemeral=True)


class LaunchModal(discord.ui.Modal, title="⚠️ Lancer la restructuration"):
    salons = discord.ui.TextInput(
        label="Salons temporaires (virgules)",
        default="annonces-restructuration,discussion-temporaire",
        max_length=300,
    )
    roles = discord.ui.TextInput(label="Supprimer aussi les rôles ? (oui/non)", default="oui", max_length=3)
    ping = discord.ui.TextInput(label="Mentionner @everyone ? (oui/non)", default="non", max_length=3)
    confirm = discord.ui.TextInput(
        label="Écris CONFIRMER pour valider", placeholder="CONFIRMER", max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if str(self.confirm).strip().upper() != "CONFIRMER":
            return await interaction.response.send_message("Annulé (confirmation incorrecte).", ephemeral=True)
        names = clean_names(str(self.salons))
        if not names:
            return await interaction.response.send_message("Indique au moins un salon.", ephemeral=True)

        await interaction.response.send_message(
            "⏳ Restructuration en cours, patiente…",
            ephemeral=True,
        )
        try:
            stats = await run_restructure(guild, names, yes(str(self.roles)), yes(str(self.ping)))
            report = (
                f"✅ Terminé : {stats['channels']} salons et {stats['roles']} rôles supprimés, "
                f"{stats['errors']} erreurs."
            )
        except discord.HTTPException as e:
            report = f"❌ Erreur : {e}"
        log_action(guild.id, f"{interaction.user} (Discord)", f"Restructuration lancée — {report}")
        # Le salon d'origine a pu être supprimé -> rapport en MP
        try:
            await interaction.user.send(report)
        except discord.HTTPException:
            pass


def extract_user_id(text: str) -> int | None:
    """Récupère un ID numérique depuis une mention <@123>, <@!123> ou un ID brut."""
    digits = re.findall(r"\d{15,21}", text)
    return int(digits[0]) if digits else None


class BanModal(discord.ui.Modal, title="🔨 Bannir un membre"):
    cible = discord.ui.TextInput(label="ID ou @mention du membre", placeholder="123456789012345678")
    raison = discord.ui.TextInput(label="Raison", style=discord.TextStyle.paragraph, required=False, max_length=400)
    confirm = discord.ui.TextInput(label="Écris CONFIRMER pour valider", placeholder="CONFIRMER", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if str(self.confirm).strip().upper() != "CONFIRMER":
            return await interaction.response.send_message("Annulé (confirmation incorrecte).", ephemeral=True)
        user_id = extract_user_id(str(self.cible))
        if user_id is None:
            return await interaction.response.send_message("ID ou mention invalide.", ephemeral=True)

        target_member = guild.get_member(user_id)
        if target_member and (target_member.id == guild.owner_id or is_protected(target_member, guild)):
            return await interaction.response.send_message(
                t(guild.id, "ban_protected"),
                ephemeral=True,
            )

        raison = str(self.raison) or "Non précisée"
        try:
            await guild.ban(discord.Object(id=user_id), reason=f"{raison} (par {interaction.user})")
        except discord.HTTPException as e:
            return await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
        log_action(guild.id, f"{interaction.user} (Discord)", f"Membre {user_id} banni : {raison}")
        await interaction.response.send_message(t(guild.id, "banned", user=user_id), ephemeral=True)


# --------------------------------------------------------------------------- #
# Panneau : boutons
# --------------------------------------------------------------------------- #
def is_trusted(user: discord.Member) -> bool:
    return user.guild_permissions.administrator or user.id in ALLOWED_USER_IDS


class VerifyView(discord.ui.View):
    """Bouton persistant de vérification à l'arrivée (captcha simple)."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Je suis humain", emoji="✅", style=discord.ButtonStyle.success, custom_id="verify:click")
    async def verify(self, interaction: discord.Interaction, _: discord.ui.Button):
        conf = guild_conf(interaction.guild_id)["security"]["verification"]
        role_id = conf.get("role_id")
        role = interaction.guild.get_role(role_id) if role_id else None
        if role and role in interaction.user.roles:
            try:
                await interaction.user.remove_roles(role, reason="Vérification effectuée")
            except discord.HTTPException:
                pass
        log_action(interaction.guild_id, f"{interaction.user} (vérification)", "Membre vérifié")
        await interaction.response.send_message(t(interaction.guild_id, "verify_success"), ephemeral=True)


class TicketCloseView(discord.ui.View):
    """Bouton persistant pour fermer un ticket."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fermer le ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
        member = interaction.user
        is_owner_of_ticket = interaction.channel.name == f"ticket-{member.id}"
        if not is_trusted(member) and not is_owner_of_ticket:
            return await interaction.response.send_message("⛔ Tu ne peux pas fermer ce ticket.", ephemeral=True)
        await interaction.response.send_message(t(interaction.guild_id, "ticket_closing"))
        log_action(interaction.guild_id, f"{member} (ticket)", f"Ticket fermé : #{interaction.channel.name}")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Ticket fermé")
        except discord.HTTPException:
            pass


class TicketPanelView(discord.ui.View):
    """Bouton persistant pour ouvrir un ticket."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ouvrir un ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, _: discord.ui.Button):
        guild = interaction.guild
        name = f"ticket-{interaction.user.id}"
        existing = discord.utils.get(guild.text_channels, name=name)
        if existing:
            return await interaction.response.send_message(t(interaction.guild_id, "ticket_already", channel=existing.mention), ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_messages:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        try:
            channel = await guild.create_text_channel(name, overwrites=overwrites, reason="Ticket ouvert")
        except discord.HTTPException as e:
            return await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
        await channel.send(
            f"🎫 Ticket de {interaction.user.mention}. Un membre du staff va te répondre.",
            view=TicketCloseView(),
        )
        log_action(guild.id, f"{interaction.user} (ticket)", f"Ticket ouvert : #{channel.name}")
        await interaction.response.send_message(t(interaction.guild_id, "ticket_open", channel=channel.mention), ephemeral=True)


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # persistant

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild and is_trusted(interaction.user):
            return True
        await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
        return False

    # ---- Ligne 1 : message ----
    @discord.ui.button(label="Modifier le message", emoji="✏️", style=discord.ButtonStyle.primary,
                       custom_id="panel:edit", row=0)
    async def edit_msg(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(MessageModal(guild_conf(interaction.guild_id)["message"]))

    @discord.ui.button(label="Aperçu", emoji="👁️", style=discord.ButtonStyle.secondary,
                       custom_id="panel:preview", row=0)
    async def preview(self, interaction: discord.Interaction, _):
        await interaction.response.send_message(embed=build_embed(interaction.guild), ephemeral=True)

    @discord.ui.button(label="Annoncer", emoji="📣", style=discord.ButtonStyle.success,
                       custom_id="panel:announce", row=0)
    async def announce(self, interaction: discord.Interaction, _):
        temps = temp_text_channels(interaction.guild)
        if not temps:
            return await interaction.response.send_message(
                "Aucun salon temporaire. Crée-en un d'abord.", ephemeral=True
            )
        await temps[0].send(embed=build_embed(interaction.guild))
        log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Message annoncé dans #{temps[0].name}")
        await interaction.response.send_message(f"✅ Message posté dans {temps[0].mention}.", ephemeral=True)

    # ---- Ligne 2 : salons temporaires ----
    @discord.ui.button(label="Créer salon temp.", emoji="➕", style=discord.ButtonStyle.secondary,
                       custom_id="panel:temp_create", row=1)
    async def temp_create(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(TempCreateModal())

    @discord.ui.button(label="Supprimer salons temp.", emoji="🗑️", style=discord.ButtonStyle.secondary,
                       custom_id="panel:temp_delete", row=1)
    async def temp_delete(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        conf = guild_conf(interaction.guild_id)
        count = 0
        for cid in conf["temp_channels"]:
            ch = interaction.guild.get_channel(cid)
            if ch:
                try:
                    await ch.delete(reason="Fin de la restructuration")
                    count += 1
                except discord.HTTPException:
                    pass
        conf["temp_channels"] = []
        set_guild_conf(interaction.guild_id, conf)
        log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"{count} salon(s) temporaire(s) supprimé(s)")
        await interaction.followup.send(f"🗑️ {count} salons temporaires supprimés.", ephemeral=True)

    # ---- Ligne 3 : modération ----
    @discord.ui.button(label="Bannir un membre", emoji="🔨", style=discord.ButtonStyle.danger,
                       custom_id="panel:ban", row=2)
    async def ban(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(BanModal())

    # ---- Ligne 4 : actualiser + lancer ----
    @discord.ui.button(label="Actualiser", emoji="🔄", style=discord.ButtonStyle.secondary,
                       custom_id="panel:refresh", row=3)
    async def refresh(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=panel_embed(interaction.guild), view=self)

    @discord.ui.button(label="Lancer la restructuration", emoji="🚀", style=discord.ButtonStyle.danger,
                       custom_id="panel:launch", row=3)
    async def launch(self, interaction: discord.Interaction, _):
        if interaction.user.id != interaction.guild.owner_id and interaction.user.id not in ALLOWED_USER_IDS:
            return await interaction.response.send_message(
                "⛔ Seul le propriétaire du serveur peut lancer la restructuration.", ephemeral=True
            )
        await interaction.response.send_modal(LaunchModal())


# --------------------------------------------------------------------------- #
# Bot
# --------------------------------------------------------------------------- #
class RestructureBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True          # nécessaire pour /inactifs (liste des membres)
        intents.message_content = True  # nécessaire pour l'anti-spam (lire le texte des messages)
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(PanelView())        # les boutons restent actifs après un redémarrage
        self.add_view(VerifyView())
        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())
        await self.tree.sync()


bot = RestructureBot()


@bot.tree.command(name="panel", description="Ouvrir le panneau de restructuration")
@app_commands.describe(public="Afficher le panneau dans le salon (il sera supprimé avec le salon au lancement)")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def cmd_panel(interaction: discord.Interaction, public: bool = False):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    await interaction.response.send_message(
        embed=panel_embed(interaction.guild), view=PanelView(), ephemeral=not public
    )


MAX_MESSAGES = 300  # plafond de sécurité par commande
SEND_DELAY = 1.2    # secondes entre deux messages (évite les limites de débit de Discord)

messages_group = app_commands.Group(
    name="messages",
    description="Envoyer des messages via le bot",
    guild_only=True,
    default_permissions=discord.Permissions(administrator=True),
)


@messages_group.command(name="envoyer", description="Faire envoyer un message plusieurs fois par le bot")
@app_commands.describe(
    nombre=f"Nombre de messages à envoyer (1 à {MAX_MESSAGES})",
    texte="Ce que le bot doit dire. Utilise \\n pour un retour à la ligne et {n} pour le numéro du message",
    salon="Salon où envoyer (par défaut : le salon actuel)",
)
async def cmd_messages_send(
    interaction: discord.Interaction,
    nombre: app_commands.Range[int, 1, MAX_MESSAGES],
    texte: app_commands.Range[str, 1, 2000],
    salon: discord.TextChannel | None = None,
):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)

    channel = salon or interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return await interaction.response.send_message("Choisis un salon textuel.", ephemeral=True)
    if not channel.permissions_for(interaction.guild.me).send_messages:
        return await interaction.response.send_message(
            f"⛔ Je n'ai pas la permission d'écrire dans {channel.mention}.", ephemeral=True
        )

    await interaction.response.send_message(
        f"⏳ Envoi de {nombre} message(s) dans {channel.mention}…", ephemeral=True
    )
    sent = 0
    for i in range(1, nombre + 1):
        content = texte.replace("\\n", "\n").replace("{n}", str(i))
        try:
            await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
            sent += 1
        except discord.HTTPException:
            break
        await asyncio.sleep(SEND_DELAY)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"{sent} message(s) envoyés dans #{channel.name}")
    await interaction.followup.send(f"✅ {sent}/{nombre} message(s) envoyé(s) dans {channel.mention}.", ephemeral=True)


bot.tree.add_command(messages_group)


# --------------------------------------------------------------------------- #
# Nettoyage des comptes inactifs
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Sécurité : anti-spam, anti-raid, avertissements, mute, lockdown
# --------------------------------------------------------------------------- #
# Suivi en mémoire seulement (pas besoin de le garder après un redémarrage du bot)
_recent_messages: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=50))
_recent_joins: dict[int, deque] = defaultdict(lambda: deque(maxlen=50))

URL_RE = re.compile(r"https?://([^/\s]+)", re.IGNORECASE)


def is_protected(member: discord.Member, guild: discord.Guild) -> bool:
    return (
        member.bot
        or member.id == guild.owner_id
        or member.guild_permissions.administrator
        or member.guild_permissions.manage_messages
        or member.guild_permissions.kick_members
        or member.guild_permissions.ban_members
        or member.guild_permissions.manage_guild
    )


def normalize_name(name: str) -> str:
    """Enlève accents, espaces et caractères spéciaux pour comparer des pseudos."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


async def handle_impersonation(member: discord.Member):
    guild = member.guild
    conf = guild_conf(guild.id)["security"]["antiusurpation"]
    if not conf["enabled"] or is_protected(member, guild):
        return
    suspect_names = {member.display_name, member.name}
    for cand in guild.members:
        if cand.id == member.id or not is_protected(cand, guild):
            continue
        cand_names = {cand.display_name, cand.name}
        best = max((name_similarity(a, b) for a in suspect_names for b in cand_names), default=0.0)
        if best >= conf["threshold"]:
            msg = f"⚠️ {member} ressemble fortement à {cand} (administrateur/modérateur) — usurpation possible"
            log_action(guild.id, "Bot (anti-usurpation)", msg)
            if conf["action"] == "kick":
                try:
                    await member.kick(reason="Anti-usurpation : pseudo trop proche d'un administrateur")
                    log_action(guild.id, "Bot (anti-usurpation)", f"{member} expulsé (usurpation)")
                except discord.HTTPException:
                    pass
            try:
                if guild.owner:
                    await guild.owner.send(f"{msg} sur **{guild.name}**.")
            except discord.HTTPException:
                pass
            return


_recent_deletions: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=50))


async def get_audit_executor(guild: discord.Guild, action: discord.AuditLogAction, target_id: int):
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            if entry.target and getattr(entry.target, "id", None) == target_id:
                return entry.user
    except discord.Forbidden:
        return None
    return None


async def handle_mass_deletion(guild: discord.Guild, executor, kind: str):
    conf = guild_conf(guild.id)["security"]["antidelete"]
    if not conf["enabled"] or executor is None:
        return
    if executor.id == bot.user.id or executor.id == guild.owner_id:
        return  # le bot lui-même (restructuration normale) et le propriétaire ne sont jamais sanctionnés

    key = (guild.id, executor.id)
    now = datetime.now()
    _recent_deletions[key].append(now)
    window_start = now - timedelta(seconds=conf["window_seconds"])
    count = sum(1 for t in _recent_deletions[key] if t >= window_start)
    if count < conf["threshold"]:
        return

    member = guild.get_member(executor.id)
    action_taken = "aucune (membre introuvable)"
    if member and conf["action"] != "alerter":
        action_taken = "échec (droits insuffisants)"
        try:
            if conf["action"] in ("retirer_roles", "kick", "ban"):
                roles_to_remove = [r for r in member.roles if not r.is_default() and r < guild.me.top_role]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason="Anti-suppression massive")
                action_taken = "rôles retirés"
            if conf["action"] == "kick":
                await member.kick(reason="Anti-suppression massive")
                action_taken = "expulsé"
            elif conf["action"] == "ban":
                await member.ban(reason="Anti-suppression massive")
                action_taken = "banni"
        except discord.HTTPException:
            action_taken = "échec (droits insuffisants)"
    elif conf["action"] == "alerter":
        action_taken = "alerte seulement"

    msg = f"🚨 {executor} a supprimé {count} {kind}(s) en {conf['window_seconds']}s — action : {action_taken}"
    log_action(guild.id, "Bot (anti-suppression)", msg)
    try:
        if guild.owner:
            await guild.owner.send(f"{msg} sur **{guild.name}**.")
    except discord.HTTPException:
        pass
    _recent_deletions[key].clear()


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    try:
        executor = await get_audit_executor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        await handle_mass_deletion(channel.guild, executor, "salon")
    except Exception as e:
        print(f"Erreur anti-suppression (salon) : {e}")


@bot.event
async def on_guild_role_delete(role: discord.Role):
    try:
        executor = await get_audit_executor(role.guild, discord.AuditLogAction.role_delete, role.id)
        await handle_mass_deletion(role.guild, executor, "rôle")
    except Exception as e:
        print(f"Erreur anti-suppression (rôle) : {e}")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.display_name != after.display_name:
        try:
            await handle_impersonation(after)
        except Exception as e:
            print(f"Erreur anti-usurpation : {e}")


async def alert_owner(guild: discord.Guild, message: str) -> None:
    try:
        if guild.owner:
            await guild.owner.send(f"{message} sur **{guild.name}**.")
    except discord.HTTPException:
        pass


@bot.event
async def on_guild_role_create(role: discord.Role):
    try:
        conf = guild_conf(role.guild.id)["security"]["antidelete"]
        if not conf.get("bloquer_roles_dangereux", False) or not role.permissions.administrator:
            return
        executor = await get_audit_executor(role.guild, discord.AuditLogAction.role_create, role.id)
        if executor is None or executor.id == bot.user.id or executor.id == role.guild.owner_id:
            return
        if role >= role.guild.me.top_role:
            log_action(role.guild.id, "Bot (anti-nuke)", f"⚠️ Rôle Administrateur '{role.name}' créé par {executor} — trop haut pour être supprimé par le bot")
            await alert_owner(role.guild, f"🚨 {executor} a créé un rôle **Administrateur** ('{role.name}') que je ne peux pas supprimer (trop haut dans la hiérarchie)")
            return
        try:
            await role.delete(reason="Anti-nuke : rôle Administrateur créé par un membre non autorisé")
            log_action(role.guild.id, "Bot (anti-nuke)", f"Rôle Administrateur '{role.name}' créé par {executor} -> supprimé automatiquement")
            await alert_owner(role.guild, f"🚨 {executor} a créé un rôle **Administrateur** ('{role.name}'), supprimé automatiquement")
        except discord.HTTPException:
            pass
    except Exception as e:
        print(f"Erreur anti-nuke (rôle dangereux) : {e}")


@bot.event
async def on_webhooks_update(channel: discord.abc.GuildChannel):
    try:
        conf = guild_conf(channel.guild.id)["security"]
        if not conf.get("surveiller_webhooks", False):
            return
        executor = None
        try:
            async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
                executor = entry.user
                break
        except discord.Forbidden:
            pass
        if executor and executor.id != bot.user.id:
            log_action(channel.guild.id, "Bot (surveillance webhooks)", f"Webhook créé par {executor} dans #{channel.name}")
            await alert_owner(channel.guild, f"⚠️ Un webhook a été créé par {executor} dans #{channel.name}")
    except Exception as e:
        print(f"Erreur surveillance webhooks : {e}")


def active_warnings(guild_id: int, user_id: int) -> list[dict]:
    """Avertissements non expirés (selon security.escalade.expiration_jours ; 0 = jamais expirer)."""
    conf = guild_conf(guild_id)
    all_warns = conf["warnings"].get(str(user_id), [])
    days = conf["security"]["escalade"].get("expiration_jours", 90)
    if not days:
        return all_warns
    cutoff = datetime.now() - timedelta(days=days)
    return [w for w in all_warns if datetime.fromisoformat(w["ts"]) >= cutoff]


def add_warning(guild_id: int, user_id: int, reason: str, by: str) -> int:
    """Ajoute un avertissement et retourne le nombre d'avertissements ENCORE ACTIFS (non expirés)."""
    conf = guild_conf(guild_id)
    conf["warnings"].setdefault(str(user_id), [])
    conf["warnings"][str(user_id)].append(
        {"ts": datetime.now().isoformat(timespec="seconds"), "reason": reason, "by": by}
    )
    set_guild_conf(guild_id, conf)
    return len(active_warnings(guild_id, user_id))


async def apply_warning_escalation(member: discord.Member, total: int) -> None:
    """Mute ou kick automatique une fois un certain nombre d'avertissements atteint."""
    conf = guild_conf(member.guild.id)["security"]["escalade"]
    if not conf["enabled"] or is_protected(member, member.guild):
        return
    if conf["kick_a"] and total >= conf["kick_a"]:
        try:
            await member.kick(reason=f"Escalade automatique : {total} avertissements")
            log_action(member.guild.id, "Bot (escalade auto)", f"{member} expulsé après {total} avertissements")
        except discord.HTTPException:
            pass
    elif conf["mute_a"] and total >= conf["mute_a"]:
        try:
            await member.timeout(timedelta(minutes=conf["mute_minutes"]), reason=f"Escalade automatique : {total} avertissements")
            log_action(member.guild.id, "Bot (escalade auto)", f"{member} mute {conf['mute_minutes']} min après {total} avertissements")
        except discord.HTTPException:
            pass


async def lockdown_guild(guild: discord.Guild, lock: bool, actor: str) -> int:
    conf = guild_conf(guild.id)
    count = 0
    include_voice = conf["security"].get("verrouiller_vocaux", True)
    channels = list(guild.text_channels) + (list(guild.voice_channels) if include_voice else [])

    if lock:
        backup = {}
        for ch in channels:
            ow = ch.overwrites_for(guild.default_role)
            is_voice = isinstance(ch, discord.VoiceChannel)
            attr = "connect" if is_voice else "send_messages"
            backup[str(ch.id)] = {"attr": attr, "value": getattr(ow, attr)}
            new_ow = ow
            setattr(new_ow, attr, False)
            try:
                await ch.set_permissions(guild.default_role, overwrite=new_ow, reason="Lockdown")
                count += 1
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.3)
        conf["security"]["lockdown_backup"] = backup
    else:
        backup = conf["security"].get("lockdown_backup", {})
        for ch in channels:
            saved = backup.get(str(ch.id))
            if saved is None:
                continue
            ow = ch.overwrites_for(guild.default_role)
            setattr(ow, saved["attr"], saved["value"])
            try:
                await ch.set_permissions(guild.default_role, overwrite=ow, reason="Fin du lockdown")
                count += 1
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.3)
        conf["security"]["lockdown_backup"] = {}
    set_guild_conf(guild.id, conf)
    log_action(guild.id, actor, f"{'Lockdown activé' if lock else 'Lockdown désactivé'} ({count} salon(s))")
    return count


async def handle_antispam(message: discord.Message):
    guild, author = message.guild, message.author
    if guild is None or author.bot or is_protected(author, guild):
        return
    sec = guild_conf(guild.id)["security"]
    conf = sec["antispam"]

    # Filtre de mots interdits (indépendant de l'activation de l'anti-spam)
    fm = sec.get("filtre_mots", {"enabled": False, "mots": []})
    if fm["enabled"] and fm["mots"]:
        content_lower = (message.content or "").lower()
        hit = next((w for w in fm["mots"] if w.lower() in content_lower), None)
        if hit:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            total = add_warning(guild.id, author.id, "Mot interdit détecté", "Bot (auto)")
            await apply_warning_escalation(author, total)
            log_action(guild.id, "Bot (auto)", f"Message de {author} supprimé (mot interdit)")
            return

    if not conf["enabled"]:
        return

    # Mentions en masse
    total_mentions = len(message.mentions) + len(message.role_mentions)
    if total_mentions > conf["max_mentions"]:
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        total = add_warning(guild.id, author.id, "Mentions en masse (anti-spam)", "Bot (auto)")
        await apply_warning_escalation(author, total)
        log_action(guild.id, "Bot (auto)", f"Message de {author} supprimé (mentions en masse)")
        return

    # Liens non autorisés
    if conf["block_links"]:
        domains = URL_RE.findall(message.content or "")
        not_allowed = [d for d in domains if not any(d.endswith(a) for a in conf["allowed_domains"])]
        if not_allowed:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            total = add_warning(guild.id, author.id, f"Lien non autorisé : {not_allowed[0]}", "Bot (auto)")
            await apply_warning_escalation(author, total)
            log_action(guild.id, "Bot (auto)", f"Message de {author} supprimé (lien non autorisé)")
            return

    # Messages répétés / trop rapides
    key = (guild.id, author.id)
    now = datetime.now()
    _recent_messages[key].append(now)
    window_start = now - timedelta(seconds=conf["window_seconds"])
    count = sum(1 for t in _recent_messages[key] if t >= window_start)
    if count > conf["max_messages"]:
        try:
            await message.channel.purge(limit=conf["max_messages"] + 5, check=lambda m: m.author.id == author.id)
        except discord.HTTPException:
            pass
        try:
            await author.timeout(timedelta(minutes=conf["mute_minutes"]), reason="Anti-spam : trop de messages")
        except discord.HTTPException:
            pass
        total = add_warning(guild.id, author.id, "Spam de messages (anti-spam)", "Bot (auto)")
        log_action(guild.id, "Bot (auto)", f"{author} mis en sourdine {conf['mute_minutes']} min (spam)")
        _recent_messages[key].clear()


async def handle_antiraid(member: discord.Member):
    guild = member.guild
    conf = guild_conf(guild.id)["security"]["antiraid"]
    if not conf["enabled"]:
        return
    now = datetime.now()
    _recent_joins[guild.id].append(now)
    window_start = now - timedelta(seconds=conf["window_seconds"])
    count = sum(1 for t in _recent_joins[guild.id] if t >= window_start)
    if count < conf["join_threshold"]:
        return

    account_age_days = (now - member.created_at.replace(tzinfo=None)).days
    suspicious = account_age_days < conf["new_account_days"]

    if conf["action"] == "lockdown":
        await lockdown_guild(guild, True, "Bot (anti-raid auto)")
        log_action(guild.id, "Bot (anti-raid auto)", f"Arrivée massive détectée ({count} en {conf['window_seconds']}s)")
    elif suspicious and conf["action"] in ("kick", "ban"):
        try:
            if conf["action"] == "ban":
                await member.ban(reason="Anti-raid : compte récent pendant une arrivée massive")
            else:
                await member.kick(reason="Anti-raid : compte récent pendant une arrivée massive")
            log_action(guild.id, "Bot (anti-raid auto)", f"{member} {conf['action']} (anti-raid, compte récent)")
        except discord.HTTPException:
            pass


@bot.event
async def on_member_join(member: discord.Member):
    if member.bot:
        try:
            executor = await get_audit_executor(member.guild, discord.AuditLogAction.bot_add, member.id)
            who = str(executor) if executor else "quelqu'un (introuvable dans le journal d'audit)"
            log_action(member.guild.id, "Bot (surveillance)", f"Nouveau bot ajouté : {member} par {who}")
            await alert_owner(member.guild, f"🤖 Un nouveau bot ({member}) a été ajouté, par {who}")
        except Exception as e:
            print(f"Erreur surveillance ajout de bot : {e}")
        return  # on n'applique pas l'anti-raid/vérification/auto-rôle à un bot
    try:
        await handle_antiraid(member)
    except Exception as e:  # on ne veut jamais planter le bot à cause de l'anti-raid
        print(f"Erreur anti-raid : {e}")
    try:
        await handle_impersonation(member)
    except Exception as e:
        print(f"Erreur anti-usurpation : {e}")
    auto_role_id = guild_conf(member.guild.id).get("auto_role")
    if auto_role_id:
        role = member.guild.get_role(auto_role_id)
        if role:
            try:
                await member.add_roles(role, reason="Auto-rôle")
            except discord.HTTPException:
                pass
    verif = guild_conf(member.guild.id)["security"]["verification"]
    if verif["enabled"] and verif.get("role_id"):
        role = member.guild.get_role(verif["role_id"])
        if role:
            try:
                await member.add_roles(role, reason="Vérification requise à l'arrivée")
            except discord.HTTPException:
                pass


@bot.event
async def on_message(message: discord.Message):
    if message.guild and not message.author.bot:
        leveled_up = touch_activity(message.guild.id, message.author.id)
        if leveled_up and guild_conf(message.guild.id).get("leveling_announce", True):
            entry = guild_conf(message.guild.id)["activity"].get(str(message.author.id), {})
            level = entry.get("xp", 0) // 100
            try:
                await message.channel.send(t(message.guild.id, "level_up", member=message.author.mention, level=level))
            except discord.HTTPException:
                pass
        try:
            await handle_antispam(message)
        except Exception as e:  # idem : ne jamais planter le bot à cause de l'anti-spam
            print(f"Erreur anti-spam : {e}")


security_group = app_commands.Group(
    name="securite",
    description="Sécurité du serveur : anti-spam, anti-raid, avertissements, mute, lockdown",
    guild_only=True,
    default_permissions=discord.Permissions(administrator=True),
)


@security_group.command(name="configurer", description="Activer/régler l'anti-spam et l'anti-raid")
@app_commands.describe(
    antispam="Activer l'anti-spam",
    max_messages="Nb de messages autorisés sur la fenêtre de temps avant mute",
    fenetre_secondes="Durée de la fenêtre de temps (secondes) pour l'anti-spam",
    max_mentions="Nb de mentions dans un seul message avant suppression",
    bloquer_liens="Supprimer les messages contenant un lien non autorisé",
    antiraid="Activer l'anti-raid",
    seuil_arrivees="Nb d'arrivées qui déclenche l'anti-raid",
    fenetre_arrivees_secondes="Durée de la fenêtre de temps (secondes) pour l'anti-raid",
    action_antiraid="Que faire quand l'anti-raid se déclenche",
    usurpation="Activer l'alerte anti-usurpation de pseudo",
    seuil_similarite="Ressemblance (0.5 à 1.0) à partir de laquelle un pseudo est suspect",
    action_usurpation="Que faire en cas d'usurpation détectée",
    antisuppression="Activer la protection anti-suppression massive",
    seuil_suppressions="Nb de salons/rôles supprimés qui déclenche la protection",
    fenetre_suppressions_secondes="Durée de la fenêtre de temps (secondes) pour l'anti-suppression",
    action_antisuppression="Que faire en cas de suppression massive détectée",
    escalade="Activer l'escalade automatique des avertissements",
    escalade_mute_a="Nb d'avertissements qui déclenche un mute automatique",
    escalade_mute_minutes="Durée du mute automatique (minutes)",
    escalade_kick_a="Nb d'avertissements qui déclenche un kick automatique",
    filtre_mots="Activer le filtre de mots interdits (liste via /securite mots)",
    expiration_avertissements="Nb de jours avant qu'un avertissement n'expire (0 = jamais)",
    surveiller_webhooks="Alerter si un webhook est créé (vecteur de spam courant)",
    verrouiller_vocaux="Le lockdown verrouille aussi les salons vocaux",
    bloquer_roles_dangereux="Supprimer automatiquement un rôle Administrateur créé par qqn d'autre que toi/le bot",
)
@app_commands.choices(action_antiraid=[
    app_commands.Choice(name="Verrouiller le serveur (lockdown)", value="lockdown"),
    app_commands.Choice(name="Expulser les comptes récents (kick)", value="kick"),
    app_commands.Choice(name="Bannir les comptes récents (ban)", value="ban"),
])
@app_commands.choices(action_usurpation=[
    app_commands.Choice(name="Alerter seulement (recommandé)", value="alerter"),
    app_commands.Choice(name="Expulser (kick)", value="kick"),
])
@app_commands.choices(action_antisuppression=[
    app_commands.Choice(name="Alerter seulement (recommandé)", value="alerter"),
    app_commands.Choice(name="Retirer les rôles", value="retirer_roles"),
    app_commands.Choice(name="Expulser (kick)", value="kick"),
    app_commands.Choice(name="Bannir (ban)", value="ban"),
])
async def cmd_security_configure(
    interaction: discord.Interaction,
    antispam: bool | None = None,
    max_messages: app_commands.Range[int, 2, 50] | None = None,
    fenetre_secondes: app_commands.Range[int, 2, 120] | None = None,
    max_mentions: app_commands.Range[int, 1, 50] | None = None,
    bloquer_liens: bool | None = None,
    antiraid: bool | None = None,
    seuil_arrivees: app_commands.Range[int, 2, 100] | None = None,
    fenetre_arrivees_secondes: app_commands.Range[int, 2, 300] | None = None,
    action_antiraid: app_commands.Choice[str] | None = None,
    usurpation: bool | None = None,
    seuil_similarite: app_commands.Range[float, 0.5, 1.0] | None = None,
    action_usurpation: app_commands.Choice[str] | None = None,
    antisuppression: bool | None = None,
    seuil_suppressions: app_commands.Range[int, 2, 50] | None = None,
    fenetre_suppressions_secondes: app_commands.Range[int, 5, 600] | None = None,
    action_antisuppression: app_commands.Choice[str] | None = None,
    escalade: bool | None = None,
    escalade_mute_a: app_commands.Range[int, 1, 20] | None = None,
    escalade_mute_minutes: app_commands.Range[int, 1, 10080] | None = None,
    escalade_kick_a: app_commands.Range[int, 1, 20] | None = None,
    filtre_mots: bool | None = None,
    expiration_avertissements: app_commands.Range[int, 0, 3650] | None = None,
    surveiller_webhooks: bool | None = None,
    verrouiller_vocaux: bool | None = None,
    bloquer_roles_dangereux: bool | None = None,
):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    conf = guild_conf(interaction.guild_id)
    s = conf["security"]
    if antispam is not None:
        s["antispam"]["enabled"] = antispam
    if max_messages is not None:
        s["antispam"]["max_messages"] = max_messages
    if fenetre_secondes is not None:
        s["antispam"]["window_seconds"] = fenetre_secondes
    if max_mentions is not None:
        s["antispam"]["max_mentions"] = max_mentions
    if bloquer_liens is not None:
        s["antispam"]["block_links"] = bloquer_liens
    if antiraid is not None:
        s["antiraid"]["enabled"] = antiraid
    if seuil_arrivees is not None:
        s["antiraid"]["join_threshold"] = seuil_arrivees
    if fenetre_arrivees_secondes is not None:
        s["antiraid"]["window_seconds"] = fenetre_arrivees_secondes
    if action_antiraid is not None:
        s["antiraid"]["action"] = action_antiraid.value
    if usurpation is not None:
        s["antiusurpation"]["enabled"] = usurpation
    if seuil_similarite is not None:
        s["antiusurpation"]["threshold"] = seuil_similarite
    if action_usurpation is not None:
        s["antiusurpation"]["action"] = action_usurpation.value
    if antisuppression is not None:
        s["antidelete"]["enabled"] = antisuppression
    if seuil_suppressions is not None:
        s["antidelete"]["threshold"] = seuil_suppressions
    if fenetre_suppressions_secondes is not None:
        s["antidelete"]["window_seconds"] = fenetre_suppressions_secondes
    if action_antisuppression is not None:
        s["antidelete"]["action"] = action_antisuppression.value
    if escalade is not None:
        s["escalade"]["enabled"] = escalade
    if escalade_mute_a is not None:
        s["escalade"]["mute_a"] = escalade_mute_a
    if escalade_mute_minutes is not None:
        s["escalade"]["mute_minutes"] = escalade_mute_minutes
    if escalade_kick_a is not None:
        s["escalade"]["kick_a"] = escalade_kick_a
    if filtre_mots is not None:
        s["filtre_mots"]["enabled"] = filtre_mots
    if expiration_avertissements is not None:
        s["escalade"]["expiration_jours"] = expiration_avertissements
    if surveiller_webhooks is not None:
        s["surveiller_webhooks"] = surveiller_webhooks
    if verrouiller_vocaux is not None:
        s["verrouiller_vocaux"] = verrouiller_vocaux
    if bloquer_roles_dangereux is not None:
        s["antidelete"]["bloquer_roles_dangereux"] = bloquer_roles_dangereux
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", "Réglages de sécurité modifiés")
    await interaction.response.send_message(
        f"✅ Réglages mis à jour :\n```json\n{json.dumps(s, indent=2, ensure_ascii=False)}\n```", ephemeral=True
    )


@security_group.command(name="statut", description="Voir les réglages de sécurité actuels")
async def cmd_security_status(interaction: discord.Interaction):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    s = guild_conf(interaction.guild_id)["security"]
    await interaction.response.send_message(
        f"```json\n{json.dumps(s, indent=2, ensure_ascii=False)}\n```", ephemeral=True
    )


@security_group.command(name="lockdown", description="Verrouiller ou déverrouiller tous les salons")
@app_commands.describe(activer="True = verrouiller, False = déverrouiller")
async def cmd_lockdown(interaction: discord.Interaction, activer: bool):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    count = await lockdown_guild(interaction.guild, activer, f"{interaction.user} (Discord)")
    await interaction.followup.send(
        f"{t(interaction.guild_id, 'lockdown_on' if activer else 'lockdown_off')} ({count} salon(s)).", ephemeral=True
    )


@security_group.command(name="avertir", description="Donner un avertissement à un membre")
@app_commands.describe(membre="Le membre à avertir", raison="Raison de l'avertissement")
async def cmd_warn(interaction: discord.Interaction, membre: discord.Member, raison: str):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    total = add_warning(interaction.guild_id, membre.id, raison, str(interaction.user))
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"{membre} averti ({total} total) : {raison}")
    try:
        await membre.send(f"⚠️ Tu as reçu un avertissement sur **{interaction.guild.name}** : {raison}")
    except discord.HTTPException:
        pass
    await apply_warning_escalation(membre, total)
    await interaction.response.send_message(t(interaction.guild_id, "warned", member=membre.mention, total=total), ephemeral=True)


@security_group.command(name="avertissements", description="Voir les avertissements d'un membre")
@app_commands.describe(membre="Le membre à consulter")
async def cmd_warnings(interaction: discord.Interaction, membre: discord.Member):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    warns = active_warnings(interaction.guild_id, membre.id)
    if not warns:
        return await interaction.response.send_message(f"{membre.mention} n'a aucun avertissement actif.", ephemeral=True)
    txt = "\n".join(f"- {w['ts']} par {w['by']} : {w['reason']}" for w in warns)
    await interaction.response.send_message(
        f"**{len(warns)} avertissement(s) actif(s) pour {membre.mention} :**\n{txt}", ephemeral=True
    )


@security_group.command(name="mute", description="Mettre un membre en sourdine temporairement")
@app_commands.describe(membre="Le membre à mute", minutes="Durée en minutes", raison="Raison")
async def cmd_mute(interaction: discord.Interaction, membre: discord.Member,
                   minutes: app_commands.Range[int, 1, 40320], raison: str = "Non précisée"):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    try:
        await membre.timeout(timedelta(minutes=minutes), reason=raison)
    except discord.HTTPException as e:
        return await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"{membre} mute {minutes} min : {raison}")
    await interaction.response.send_message(t(interaction.guild_id, "muted", member=membre.mention, minutes=minutes), ephemeral=True)


@security_group.command(name="demute", description="Retirer la sourdine d'un membre")
@app_commands.describe(membre="Le membre à démute")
async def cmd_unmute(interaction: discord.Interaction, membre: discord.Member):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    try:
        await membre.timeout(None)
    except discord.HTTPException as e:
        return await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"{membre} démute")
    await interaction.response.send_message(t(interaction.guild_id, "unmuted", member=membre.mention), ephemeral=True)


@security_group.command(name="verification", description="Vérification à l'arrivée (captcha simple)")
@app_commands.describe(
    activer="Activer/désactiver la vérification",
    role="Rôle donné aux non-vérifiés (restreins son accès via les permissions Discord)",
    canal="Si fourni, poste le bouton de vérification dans ce salon",
)
async def cmd_verification(
    interaction: discord.Interaction, activer: bool,
    role: discord.Role | None = None, canal: discord.TextChannel | None = None,
):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    conf = guild_conf(interaction.guild_id)
    conf["security"]["verification"]["enabled"] = activer
    if role is not None:
        conf["security"]["verification"]["role_id"] = role.id
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Vérification {'activée' if activer else 'désactivée'}")
    msg = f"✅ Vérification {'activée' if activer else 'désactivée'}."
    if canal:
        embed = discord.Embed(
            title="🔒 Vérification requise",
            description="Clique sur le bouton ci-dessous pour accéder au reste du serveur.",
            color=discord.Color.blurple(),
        )
        await canal.send(embed=embed, view=VerifyView())
        msg += f" Message posté dans {canal.mention}."
    await interaction.response.send_message(msg, ephemeral=True)


@security_group.command(name="liens", description="Gérer les domaines autorisés pour le filtre de liens")
@app_commands.describe(action="ajouter, retirer ou lister", domaine="Le domaine concerné (ex: youtube.com)")
@app_commands.choices(action=[
    app_commands.Choice(name="Ajouter", value="ajouter"),
    app_commands.Choice(name="Retirer", value="retirer"),
    app_commands.Choice(name="Lister", value="lister"),
])
async def cmd_security_links(interaction: discord.Interaction, action: app_commands.Choice[str], domaine: str | None = None):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    conf = guild_conf(interaction.guild_id)
    domains = conf["security"]["antispam"]["allowed_domains"]
    if action.value == "lister":
        return await interaction.response.send_message(
            "Domaines autorisés : " + (", ".join(domains) if domains else "aucun"), ephemeral=True
        )
    if not domaine:
        return await interaction.response.send_message("Indique un domaine.", ephemeral=True)
    domaine = domaine.lower().strip()
    if action.value == "ajouter" and domaine not in domains:
        domains.append(domaine)
    elif action.value == "retirer" and domaine in domains:
        domains.remove(domaine)
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Domaine {domaine} {action.value}")
    await interaction.response.send_message(f"✅ Domaines autorisés : {', '.join(domains) if domains else 'aucun'}", ephemeral=True)


@security_group.command(name="mots", description="Gérer la liste des mots interdits (filtre de mots)")
@app_commands.describe(action="ajouter, retirer ou lister", mot="Le mot/expression concerné")
@app_commands.choices(action=[
    app_commands.Choice(name="Ajouter", value="ajouter"),
    app_commands.Choice(name="Retirer", value="retirer"),
    app_commands.Choice(name="Lister", value="lister"),
])
async def cmd_security_words(interaction: discord.Interaction, action: app_commands.Choice[str], mot: str | None = None):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    conf = guild_conf(interaction.guild_id)
    mots = conf["security"]["filtre_mots"]["mots"]
    if action.value == "lister":
        return await interaction.response.send_message(
            "Mots interdits : " + (", ".join(mots) if mots else "aucun"), ephemeral=True
        )
    if not mot:
        return await interaction.response.send_message("Indique un mot.", ephemeral=True)
    mot = mot.lower().strip()
    if action.value == "ajouter" and mot not in mots:
        mots.append(mot)
    elif action.value == "retirer" and mot in mots:
        mots.remove(mot)
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Mot interdit {action.value} : {mot}")
    await interaction.response.send_message(f"✅ Mots interdits : {', '.join(mots) if mots else 'aucun'}", ephemeral=True)


@security_group.command(name="canal_logs", description="Choisir le salon où le bot poste ses actions en direct")
@app_commands.describe(canal="Salon pour les logs (laisse vide pour désactiver)")
async def cmd_security_log_channel(interaction: discord.Interaction, canal: discord.TextChannel | None = None):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    conf = guild_conf(interaction.guild_id)
    conf["log_channel_id"] = canal.id if canal else None
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Salon de logs : {canal.mention if canal else 'désactivé'}")
    await interaction.response.send_message(
        f"✅ Salon de logs : {canal.mention if canal else 'désactivé'}.", ephemeral=True
    )


bot.tree.add_command(security_group)


# --------------------------------------------------------------------------- #
# Nouveautés du bot
# --------------------------------------------------------------------------- #
BOT_VERSION = "1.6"
CHANGELOG = [
    {
        "version": "1.6",
        "date": "22/11/2026",
        "items": [
            "🌐 /langue : français ou anglais (messages les plus visibles traduits)",
            "🧱 Anti-nuke renforcé : rôles Administrateur créés par un tiers, webhooks surveillés, ajout de bot signalé",
            "🔇 Le lockdown couvre aussi les salons vocaux",
            "⏳ Expiration des avertissements après X jours",
            "💾 data.json protégé contre la corruption (écriture atomique + sauvegarde)",
            "📖 /aide : liste toutes les commandes",
            "🎫 /ticket_liste : voir les tickets ouverts",
        ],
    },
    {
        "version": "1.5",
        "date": "22/11/2026",
        "items": [
            "⚠️ Escalade automatique des avertissements (mute/kick après X avertissements)",
            "🚫 Filtre de mots interdits (/securite mots)",
            "🔒 Vérification à l'arrivée / captcha simple (/securite verification)",
            "📝 Salon de logs dédié (/securite canal_logs)",
            "🔗 Gestion simplifiée des domaines autorisés (/securite liens)",
            "🎭 Rôles par réaction (/role_reaction) et rôles temporaires (/role temporaire)",
            "🎫 Système de tickets (/ticket_configurer)",
            "📅 Annonces programmées avec l'embed personnalisé (/annonce_programmee)",
            "📈 Système de niveaux/XP (/niveau, /classement)",
            "📋 /role liste pour voir les membres d'un rôle",
        ],
    },
    {
        "version": "1.3",
        "date": "22/11/2026",
        "items": [
            "🎭 /role ajouter / retirer / auto (auto-rôle à l'arrivée)",
            "📊 /sondage : créer un sondage avec réactions",
            "📈 /stats : statistiques du serveur et membres les plus actifs",
            "⏰ /rappel, /rappels, /rappel_annuler : messages programmés",
        ],
    },
    {
        "version": "1.2",
        "date": "22/11/2026",
        "items": [
            "⚠️ Anti-usurpation de pseudo (alerte si un pseudo copie un admin/modérateur)",
            "🚨 Anti-suppression massive de salons/rôles (protection anti-nuke)",
            "📜 Commande /nouveautes pour voir les mises à jour du bot",
        ],
    },
    {
        "version": "1.1",
        "date": "22/11/2026",
        "items": [
            "🛡️ Anti-spam (messages répétés, mentions en masse, liens non autorisés)",
            "🛡️ Anti-raid (arrivées massives → lockdown ou kick/ban des comptes récents)",
            "⚠️ Système d'avertissements, /securite mute et demute",
            "🔒 Commande /securite lockdown",
        ],
    },
    {
        "version": "1.0",
        "date": "22/11/2026",
        "items": [
            "🛠️ /panel : panneau de restructuration (message, salons temporaires, lancement)",
            "😴 /inactifs : expulser/bannir les comptes inactifs depuis X jours",
            "✉️ /messages envoyer : faire envoyer plusieurs messages par le bot",
        ],
    },
]


@bot.tree.command(name="nouveautes", description="Voir les dernières nouveautés du bot")
async def cmd_changelog(interaction: discord.Interaction):
    embed = discord.Embed(title=f"📦 Nouveautés du bot — v{BOT_VERSION}", color=discord.Color.blurple())
    for entry in CHANGELOG[:5]:
        embed.add_field(
            name=f"v{entry['version']} — {entry['date']}",
            value="\n".join(f"• {item}" for item in entry["items"]),
            inline=False,
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="aide", description="Voir toutes les commandes du bot")
async def cmd_help(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Commandes du bot", color=discord.Color.blurple())
    embed.add_field(
        name="🛠️ Restructuration",
        value="`/panel` · `/messages envoyer` · `/inactifs`",
        inline=False,
    )
    embed.add_field(
        name="🛡️ Sécurité",
        value=(
            "`/securite configurer/statut/lockdown/avertir/avertissements/mute/demute`\n"
            "`/securite verification/liens/mots/canal_logs`"
        ),
        inline=False,
    )
    embed.add_field(
        name="🎭 Rôles",
        value="`/role ajouter/retirer/auto/liste/temporaire` · `/role_reaction`",
        inline=False,
    )
    embed.add_field(
        name="⚙️ Général",
        value="`/sondage` · `/stats` · `/niveau` · `/classement` · `/rappel` · `/rappels` · `/rappel_annuler` · `/annonce_programmee`",
        inline=False,
    )
    embed.add_field(
        name="🎫 Tickets",
        value="`/ticket_configurer` · `/ticket_liste`",
        inline=False,
    )
    embed.add_field(
        name="📜 Autres",
        value="`/nouveautes` · `/langue` · `/aide`",
        inline=False,
    )
    embed.set_footer(text="La plupart des commandes sont réservées aux administrateurs.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="langue", description="Changer la langue des messages du bot sur ce serveur")
@app_commands.describe(choix="Langue à utiliser")
@app_commands.choices(choix=[
    app_commands.Choice(name="Français", value="fr"),
    app_commands.Choice(name="English", value="en"),
])
async def cmd_language(interaction: discord.Interaction, choix: app_commands.Choice[str]):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message(t(interaction.guild_id, "admin_only"), ephemeral=True)
    conf = guild_conf(interaction.guild_id)
    conf["lang"] = choix.value
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Langue changée : {choix.value}")
    confirm = "✅ Langue changée : Français." if choix.value == "fr" else "✅ Language changed: English."
    await interaction.response.send_message(confirm, ephemeral=True)


# --------------------------------------------------------------------------- #
# Système de tickets
# --------------------------------------------------------------------------- #
@bot.tree.command(name="ticket_configurer", description="Poster le bouton pour ouvrir des tickets de support")
@app_commands.describe(salon="Salon où poster le bouton (par défaut : le salon actuel)")
async def cmd_ticket_setup(interaction: discord.Interaction, salon: discord.TextChannel | None = None):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    channel = salon or interaction.channel
    embed = discord.Embed(
        title="🎫 Support",
        description="Clique sur le bouton ci-dessous pour ouvrir un salon privé avec le staff.",
        color=discord.Color.blurple(),
    )
    await channel.send(embed=embed, view=TicketPanelView())
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Panneau de tickets posté dans #{channel.name}")
    await interaction.response.send_message(f"✅ Panneau posté dans {channel.mention}.", ephemeral=True)


@bot.tree.command(name="ticket_liste", description="Voir les tickets actuellement ouverts")
async def cmd_ticket_list(interaction: discord.Interaction):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    tickets = [c for c in interaction.guild.text_channels if c.name.startswith("ticket-")]
    if not tickets:
        return await interaction.response.send_message("Aucun ticket ouvert actuellement.", ephemeral=True)
    lines = []
    for ch in tickets:
        user_id = ch.name.removeprefix("ticket-")
        member = interaction.guild.get_member(int(user_id)) if user_id.isdigit() else None
        lines.append(f"- {ch.mention} ({member.display_name if member else 'membre inconnu'})")
    await interaction.response.send_message(f"**{len(tickets)} ticket(s) ouvert(s) :**\n" + "\n".join(lines), ephemeral=True)


# --------------------------------------------------------------------------- #
# Gestion des rôles
# --------------------------------------------------------------------------- #
role_group = app_commands.Group(
    name="role",
    description="Gérer les rôles des membres",
    guild_only=True,
    default_permissions=discord.Permissions(administrator=True),
)


@role_group.command(name="ajouter", description="Donner un rôle à un membre")
@app_commands.describe(membre="Le membre concerné", role="Le rôle à donner")
async def cmd_role_add(interaction: discord.Interaction, membre: discord.Member, role: discord.Role):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    try:
        await membre.add_roles(role, reason=f"Ajouté par {interaction.user}")
    except discord.HTTPException as e:
        return await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Rôle {role.name} donné à {membre}")
    await interaction.response.send_message(f"✅ {role.mention} donné à {membre.mention}.", ephemeral=True)


@role_group.command(name="retirer", description="Retirer un rôle à un membre")
@app_commands.describe(membre="Le membre concerné", role="Le rôle à retirer")
async def cmd_role_remove(interaction: discord.Interaction, membre: discord.Member, role: discord.Role):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    try:
        await membre.remove_roles(role, reason=f"Retiré par {interaction.user}")
    except discord.HTTPException as e:
        return await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Rôle {role.name} retiré à {membre}")
    await interaction.response.send_message(f"✅ {role.mention} retiré à {membre.mention}.", ephemeral=True)


@role_group.command(name="auto", description="Donner automatiquement un rôle aux nouveaux membres")
@app_commands.describe(role="Rôle à donner automatiquement (laisse vide pour désactiver)")
async def cmd_role_auto(interaction: discord.Interaction, role: discord.Role | None = None):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    conf = guild_conf(interaction.guild_id)
    conf["auto_role"] = role.id if role else None
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Auto-rôle : {role.name if role else 'désactivé'}")
    if role:
        await interaction.response.send_message(f"✅ Les nouveaux membres recevront automatiquement {role.mention}.", ephemeral=True)
    else:
        await interaction.response.send_message("✅ Auto-rôle désactivé.", ephemeral=True)


@role_group.command(name="liste", description="Voir les membres ayant un rôle donné")
@app_commands.describe(role="Le rôle à consulter")
async def cmd_role_list(interaction: discord.Interaction, role: discord.Role):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    members = role.members
    if not members:
        return await interaction.response.send_message(f"Personne n'a le rôle {role.mention}.", ephemeral=True)
    lines = "\n".join(f"- {m.display_name}" for m in members[:50])
    more = f"\n… et {len(members) - 50} autre(s)" if len(members) > 50 else ""
    await interaction.response.send_message(f"**{len(members)} membre(s) avec {role.mention} :**\n{lines}{more}", ephemeral=True)


@role_group.command(name="temporaire", description="Donner un rôle pour une durée limitée (retiré automatiquement)")
@app_commands.describe(membre="Le membre concerné", role="Le rôle à donner", minutes="Durée en minutes avant retrait automatique")
async def cmd_role_temp(interaction: discord.Interaction, membre: discord.Member, role: discord.Role,
                        minutes: app_commands.Range[int, 1, 43200]):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    try:
        await membre.add_roles(role, reason=f"Rôle temporaire ({minutes} min) par {interaction.user}")
    except discord.HTTPException as e:
        return await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
    when = datetime.now() + timedelta(minutes=minutes)
    conf = guild_conf(interaction.guild_id)
    conf["temp_roles"].append({"user_id": membre.id, "role_id": role.id, "when": when.isoformat()})
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"{role.name} donné à {membre} pour {minutes} min")
    await interaction.response.send_message(f"✅ {role.mention} donné à {membre.mention} pour {minutes} minute(s).", ephemeral=True)


bot.tree.add_command(role_group)


# --------------------------------------------------------------------------- #
# Rôles par réaction
# --------------------------------------------------------------------------- #
@bot.tree.command(name="role_reaction", description="Créer un message où réagir donne un rôle (jusqu'à 5 rôles)")
@app_commands.describe(
    titre="Titre du message", salon="Salon où poster (par défaut : le salon actuel)",
    role1="1er rôle", emoji1="Emoji pour ce rôle (ex: 🔴)",
    role2="2e rôle (optionnel)", emoji2="Emoji pour ce rôle",
    role3="3e rôle (optionnel)", emoji3="Emoji pour ce rôle",
    role4="4e rôle (optionnel)", emoji4="Emoji pour ce rôle",
    role5="5e rôle (optionnel)", emoji5="Emoji pour ce rôle",
)
async def cmd_role_reaction(
    interaction: discord.Interaction, titre: str, role1: discord.Role, emoji1: str,
    salon: discord.TextChannel | None = None,
    role2: discord.Role | None = None, emoji2: str | None = None,
    role3: discord.Role | None = None, emoji3: str | None = None,
    role4: discord.Role | None = None, emoji4: str | None = None,
    role5: discord.Role | None = None, emoji5: str | None = None,
):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    pairs = [(role1, emoji1)]
    for r, e in [(role2, emoji2), (role3, emoji3), (role4, emoji4), (role5, emoji5)]:
        if r and e:
            pairs.append((r, e))

    channel = salon or interaction.channel
    embed = discord.Embed(
        title=titre,
        description="\n".join(f"{e} → {r.mention}" for r, e in pairs),
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(f"✅ Message créé dans {channel.mention}.", ephemeral=True)
    msg = await channel.send(embed=embed)
    mapping = {}
    for r, e in pairs:
        try:
            await msg.add_reaction(e)
            mapping[e] = r.id
        except discord.HTTPException:
            pass
    conf = guild_conf(interaction.guild_id)
    conf["role_reactions"][str(msg.id)] = mapping
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Message de rôles par réaction créé (#{channel.name})")


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.guild_id is None or payload.member is None or payload.member.bot:
        return
    mapping = guild_conf(payload.guild_id).get("role_reactions", {}).get(str(payload.message_id))
    if not mapping:
        return
    role_id = mapping.get(str(payload.emoji))
    if not role_id:
        return
    guild = bot.get_guild(payload.guild_id)
    role = guild.get_role(role_id) if guild else None
    if role:
        try:
            await payload.member.add_roles(role, reason="Rôle par réaction")
        except discord.HTTPException:
            pass


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.guild_id is None:
        return
    mapping = guild_conf(payload.guild_id).get("role_reactions", {}).get(str(payload.message_id))
    if not mapping:
        return
    role_id = mapping.get(str(payload.emoji))
    if not role_id:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    member = guild.get_member(payload.user_id)
    role = guild.get_role(role_id)
    if member and role and not member.bot:
        try:
            await member.remove_roles(role, reason="Rôle par réaction retiré")
        except discord.HTTPException:
            pass


# --------------------------------------------------------------------------- #
# Sondages
# --------------------------------------------------------------------------- #
POLL_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


@bot.tree.command(name="sondage", description="Créer un sondage avec réactions")
@app_commands.describe(
    question="La question du sondage",
    option1="Option 1 (laisse les options vides pour un simple 👍/👎)",
    option2="Option 2", option3="Option 3", option4="Option 4", option5="Option 5",
)
async def cmd_poll(
    interaction: discord.Interaction, question: str,
    option1: str | None = None, option2: str | None = None,
    option3: str | None = None, option4: str | None = None, option5: str | None = None,
):
    options = [o for o in [option1, option2, option3, option4, option5] if o]
    embed = discord.Embed(title="📊 Sondage", description=question, color=discord.Color.blurple())
    embed.set_footer(text=f"Créé par {interaction.user.display_name}")
    if options:
        embed.add_field(
            name="Options",
            value="\n".join(f"{POLL_EMOJIS[i]} {o}" for i, o in enumerate(options)),
            inline=False,
        )
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    try:
        if options:
            for i in range(len(options)):
                await msg.add_reaction(POLL_EMOJIS[i])
        else:
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
    except discord.HTTPException:
        pass


# --------------------------------------------------------------------------- #
# Statistiques
# --------------------------------------------------------------------------- #
@bot.tree.command(name="stats", description="Statistiques du serveur")
async def cmd_stats(interaction: discord.Interaction):
    guild = interaction.guild
    activity = guild_conf(guild.id).get("activity", {})
    counts = [
        (uid, e.get("count", 0)) for uid, e in activity.items()
        if isinstance(e, dict) and e.get("count", 0) > 0
    ]
    counts.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(title=f"📊 Statistiques de {guild.name}", color=discord.Color.blurple())
    embed.add_field(name="Membres", value=str(guild.member_count), inline=True)
    embed.add_field(name="Salons", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="Rôles", value=str(len(guild.roles) - 1), inline=True)

    top_lines = []
    for uid, c in counts[:5]:
        member = guild.get_member(int(uid))
        name = member.display_name if member else f"Utilisateur {uid}"
        top_lines.append(f"{name} — {c} message(s)")
    embed.add_field(
        name="Membres les plus actifs",
        value="\n".join(top_lines) if top_lines else "Pas encore de données.",
        inline=False,
    )
    embed.set_footer(text="Les messages ne sont comptés que depuis que le bot tourne sur ce serveur.")
    await interaction.response.send_message(embed=embed)


# --------------------------------------------------------------------------- #
# Niveaux / XP
# --------------------------------------------------------------------------- #
@bot.tree.command(name="niveau", description="Voir ton niveau et ton XP (ou ceux d'un autre membre)")
@app_commands.describe(membre="Membre à consulter (par défaut : toi-même)")
async def cmd_level(interaction: discord.Interaction, membre: discord.Member | None = None):
    target = membre or interaction.user
    entry = guild_conf(interaction.guild_id).get("activity", {}).get(str(target.id), {})
    xp = entry.get("xp", 0) if isinstance(entry, dict) else 0
    await interaction.response.send_message(t(interaction.guild_id, "level_card", member=target.mention, level=xp // 100, xp=xp))


@bot.tree.command(name="classement", description="Voir le classement XP du serveur")
async def cmd_leaderboard(interaction: discord.Interaction):
    activity = guild_conf(interaction.guild_id).get("activity", {})
    ranked = sorted(
        ((uid, e.get("xp", 0)) for uid, e in activity.items() if isinstance(e, dict)),
        key=lambda x: x[1], reverse=True,
    )[:10]
    lines = []
    for i, (uid, xp) in enumerate(ranked, 1):
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"Utilisateur {uid}"
        lines.append(f"**{i}.** {name} — niveau {xp // 100} ({xp} XP)")
    title = t(interaction.guild_id, "leaderboard_title")
    empty = t(interaction.guild_id, "leaderboard_empty")
    await interaction.response.send_message(f"{title}\n" + ("\n".join(lines) if lines else empty))


# --------------------------------------------------------------------------- #
# Rappels programmés
# --------------------------------------------------------------------------- #
@bot.tree.command(name="rappel", description="Programmer un message automatique")
@app_commands.describe(
    dans_minutes="Dans combien de minutes envoyer le message",
    texte="Le message à envoyer",
    salon="Salon où l'envoyer (par défaut : le salon actuel)",
)
async def cmd_remind(
    interaction: discord.Interaction,
    dans_minutes: app_commands.Range[int, 1, 43200],
    texte: app_commands.Range[str, 1, 1900],
    salon: discord.TextChannel | None = None,
):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    channel = salon or interaction.channel
    when = datetime.now() + timedelta(minutes=dans_minutes)
    conf = guild_conf(interaction.guild_id)
    conf.setdefault("reminders", [])
    rid = uuid.uuid4().hex[:8]
    conf["reminders"].append({"id": rid, "channel_id": channel.id, "when": when.isoformat(), "text": texte})
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Rappel `{rid}` programmé pour {when.strftime('%d/%m %H:%M')}")
    await interaction.response.send_message(
        f"⏰ Rappel `{rid}` programmé dans {dans_minutes} minute(s) dans {channel.mention}.", ephemeral=True
    )


@bot.tree.command(name="annonce_programmee", description="Programmer l'envoi du message de restructuration (celui de /panel) plus tard")
@app_commands.describe(
    dans_minutes="Dans combien de minutes l'envoyer",
    salon="Salon où l'envoyer (par défaut : le salon actuel)",
)
async def cmd_scheduled_announce(
    interaction: discord.Interaction,
    dans_minutes: app_commands.Range[int, 1, 43200],
    salon: discord.TextChannel | None = None,
):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    channel = salon or interaction.channel
    when = datetime.now() + timedelta(minutes=dans_minutes)
    conf = guild_conf(interaction.guild_id)
    rid = uuid.uuid4().hex[:8]
    conf["reminders"].append({"id": rid, "channel_id": channel.id, "when": when.isoformat(), "text": "", "embed": True})
    set_guild_conf(interaction.guild_id, conf)
    log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"Annonce programmée `{rid}` pour {when.strftime('%d/%m %H:%M')}")
    await interaction.response.send_message(
        f"⏰ Annonce programmée dans {dans_minutes} minute(s) dans {channel.mention}.", ephemeral=True
    )


@bot.tree.command(name="rappels", description="Voir les rappels programmés")
async def cmd_reminders_list(interaction: discord.Interaction):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    reminders = guild_conf(interaction.guild_id).get("reminders", [])
    if not reminders:
        return await interaction.response.send_message("Aucun rappel programmé.", ephemeral=True)
    lines = []
    for r in reminders:
        when = datetime.fromisoformat(r["when"])
        channel = interaction.guild.get_channel(r["channel_id"])
        lines.append(f"`{r['id']}` — {when.strftime('%d/%m %H:%M')} dans {channel.mention if channel else '?'} : {r['text'][:50]}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="rappel_annuler", description="Annuler un rappel programmé")
@app_commands.describe(id="Identifiant du rappel (voir /rappels)")
async def cmd_reminder_cancel(interaction: discord.Interaction, id: str):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
    conf = guild_conf(interaction.guild_id)
    before = len(conf.get("reminders", []))
    conf["reminders"] = [r for r in conf.get("reminders", []) if r["id"] != id]
    set_guild_conf(interaction.guild_id, conf)
    if len(conf["reminders"]) < before:
        await interaction.response.send_message("✅ Rappel annulé.", ephemeral=True)
    else:
        await interaction.response.send_message("Rappel introuvable.", ephemeral=True)


@tasks.loop(seconds=30)
async def reminder_loop():
    data = load_data()
    now = datetime.now()
    changed = False
    for gid, conf in list(data.items()):
        guild = bot.get_guild(int(gid))

        # Rappels / annonces programmées
        reminders = conf.get("reminders", [])
        if reminders:
            remaining = []
            for r in reminders:
                if datetime.fromisoformat(r["when"]) <= now:
                    channel = guild.get_channel(r["channel_id"]) if guild else None
                    if channel:
                        try:
                            if r.get("embed") and guild:
                                await channel.send(embed=build_embed(guild))
                            else:
                                await channel.send(f"⏰ **Rappel :** {r['text']}")
                        except discord.HTTPException:
                            pass
                    changed = True
                else:
                    remaining.append(r)
            conf["reminders"] = remaining

        # Rôles temporaires
        temp_roles = conf.get("temp_roles", [])
        if temp_roles:
            remaining_roles = []
            for tr in temp_roles:
                if datetime.fromisoformat(tr["when"]) <= now:
                    if guild:
                        member = guild.get_member(tr["user_id"])
                        role = guild.get_role(tr["role_id"])
                        if member and role and role in member.roles:
                            try:
                                await member.remove_roles(role, reason="Fin du rôle temporaire")
                            except discord.HTTPException:
                                pass
                    changed = True
                else:
                    remaining_roles.append(tr)
            conf["temp_roles"] = remaining_roles
    if changed:
        save_data(data)


async def find_inactive(guild: discord.Guild, days: int) -> list[discord.Member]:
    cutoff_ts = datetime.now().timestamp() - days * 86400
    result = []
    async for member in guild.fetch_members(limit=None):
        if is_protected(member, guild):
            continue
        seen = last_seen(guild.id, member.id)
        # Pas de message enregistré -> on se base sur la date d'arrivée (le bot ne connaît
        # pas l'historique d'avant son installation).
        reference = seen or member.joined_at.replace(tzinfo=None) if member.joined_at else None
        if reference is None or reference.timestamp() < cutoff_ts:
            result.append(member)
    return result


class InactiveConfirmView(discord.ui.View):
    def __init__(self, author_id: int, members: list[discord.Member], action: str):
        super().__init__(timeout=120)
        self.author_id, self.members, self.action = author_id, members, action

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(content="⏳ Traitement en cours…", view=None)
        done, errors = 0, 0
        for m in self.members:
            try:
                if self.action == "ban":
                    await m.ban(reason=f"Inactivité > seuil fixé", delete_message_days=0)
                else:
                    await m.kick(reason="Inactivité > seuil fixé")
                done += 1
            except discord.HTTPException:
                errors += 1
            await asyncio.sleep(1.0)
        verbe = "bannis" if self.action == "ban" else "expulsés"
        log_action(interaction.guild_id, f"{interaction.user} (Discord)", f"{done} membre(s) {verbe} pour inactivité")
        await interaction.followup.send(f"✅ {done} membre(s) {verbe}, {errors} erreur(s).", ephemeral=True)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(content="Annulé.", view=None)
        self.stop()


@bot.tree.command(name="inactifs", description="Expulser ou bannir les comptes inactifs depuis X jours")
@app_commands.describe(
    jours="Nombre de jours sans message",
    action="kick (expulser, réversible) ou ban (bannir, empêche de revenir)",
)
@app_commands.choices(action=[
    app_commands.Choice(name="Expulser (kick)", value="kick"),
    app_commands.Choice(name="Bannir (ban)", value="ban"),
])
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def cmd_inactive(interaction: discord.Interaction, jours: app_commands.Range[int, 1, 3650],
                       action: app_commands.Choice[str]):
    if not is_trusted(interaction.user):
        return await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    members = await find_inactive(interaction.guild, jours)
    if not members:
        return await interaction.followup.send("Aucun compte inactif trouvé avec ce seuil.", ephemeral=True)

    preview = "\n".join(f"- {m.mention} ({m.display_name})" for m in members[:25])
    more = f"\n… et {len(members) - 25} autre(s)" if len(members) > 25 else ""
    verbe = "bannir" if action.value == "ban" else "expulser"
    view = InactiveConfirmView(interaction.user.id, members, action.value)
    await interaction.followup.send(
        f"⚠️ **{len(members)} compte(s)** inactif(s) depuis plus de {jours} jour(s) vont être **{verbe}s** "
        f"(propriétaire, admins et modérateurs exclus) :\n{preview}{more}\n\n"
        "Note : l'activité n'est suivie que depuis que le bot tourne ; sans message enregistré, "
        "la date d'arrivée sur le serveur sert de référence.\nConfirme dans les 2 minutes :",
        view=view,
        ephemeral=True,
    )


# --------------------------------------------------------------------------- #
# Site web (dashboard) : contrôler le bot et voir les logs depuis un navigateur
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
TOKEN_URL = "https://discord.com/api/oauth2/token"
USER_URL = "https://discord.com/api/users/@me"

NAV = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard restructuration</title>
<style>
body{font-family:system-ui,sans-serif;background:#1e1f22;color:#e3e5e8;margin:0}
.nav{background:#2b2d31;padding:12px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.nav a{color:#e3e5e8;text-decoration:none} .nav a:hover{text-decoration:underline}
.container{padding:24px;max-width:900px;margin:auto}
.card{background:#2b2d31;border-radius:8px;padding:16px;margin-bottom:16px}
input,textarea,select{width:100%;padding:8px;margin:6px 0 12px;border-radius:4px;border:1px solid #4b4d52;background:#1e1f22;color:#fff;box-sizing:border-box}
label{font-size:0.85em;color:#b5b8bd}
button{background:#5865f2;color:#fff;border:none;padding:10px 16px;border-radius:4px;cursor:pointer}
button.danger{background:#da373c}
.flash{padding:10px;border-radius:4px;margin-bottom:12px;background:#2d4f3a}
.flash.err{background:#5c2b2b}
.muted{color:#9a9ca0;font-size:0.9em}
table{width:100%;border-collapse:collapse} td,th{padding:6px;border-bottom:1px solid #3a3c41;text-align:left;font-size:0.9em}
</style></head><body>
<div class="nav">
<a href="{{ url_for('home') }}">🛠️ Dashboard</a>
{% if guild %}<a href="{{ url_for('guild_page', guild_id=guild.id) }}">{{ guild.name }}</a>
<a href="{{ url_for('guild_security', guild_id=guild.id) }}">Sécurité</a>
<a href="{{ url_for('guild_logs', guild_id=guild.id) }}">Logs</a>{% endif %}
<span style="flex:1"></span>
{% if session.get('username') %}<span class="muted">{{ session['username'] }}</span> · <a href="{{ url_for('logout') }}">Déconnexion</a>{% endif %}
</div>
<div class="container">
{% if flash %}<div class="flash {{ 'err' if flash_err else '' }}">{{ flash }}</div>{% endif %}
__BODY__
</div></body></html>"""


def render(body: str, guild=None, flash: str = "", flash_err: bool = False):
    csrf_token = session.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        session["csrf_token"] = csrf_token
    # Toutes les pages du tableau utilisent des formulaires HTML simples. On
    # ajoute le jeton à chacun ici pour ne pas oublier une action sensible.
    body = re.sub(
        r"(<form\b[^>]*\bmethod=['\"]post['\"][^>]*>)",
        rf'\1<input type="hidden" name="csrf_token" value="{csrf_token}">',
        body,
        flags=re.IGNORECASE,
    )
    tpl = NAV.replace("__BODY__", body)
    return render_template_string(tpl, guild=guild, session=session, flash=flash, flash_err=flash_err)


@app.before_request
def check_csrf():
    if request.method != "POST":
        return
    expected = session.get("csrf_token", "")
    supplied = request.form.get("csrf_token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(400, "Requête invalide ou expirée. Recharge la page et réessaie.")


def call_bot(coro):
    """Exécute une coroutine du bot depuis une requête web (thread séparé) et attend le résultat."""
    fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    return fut.result(timeout=120)


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def get_authorized_guild(guild_id: int) -> discord.Guild:
    guild = bot.get_guild(guild_id)
    if guild is None:
        abort(404, "Le bot n'est pas sur ce serveur.")
    if session["user_id"] in BOT_OWNER_IDS:
        return guild  # propriétaire du bot : accès total, sans vérif locale
    member = guild.get_member(session["user_id"])
    if member is None or not is_trusted(member):
        abort(403, "Tu n'as pas les droits sur ce serveur.")
    return guild


@app.route("/")
def home():
    if "user_id" not in session:
        body = (
            "<div class='card'><h1>🛠️ Dashboard de restructuration</h1>"
            "<p>Connecte-toi avec ton compte Discord pour gérer les serveurs où le bot est présent.</p>"
            f"<a href='{url_for('login')}'><button>Se connecter avec Discord</button></a></div>"
        )
        return render(body)

    if session["user_id"] in BOT_OWNER_IDS:
        guilds = list(bot.guilds)
    else:
        guilds = [g for g in bot.guilds if (m := g.get_member(session["user_id"])) and is_trusted(m)]
    if not guilds:
        body = "<div class='card'>Tu n'es administrateur sur aucun serveur où le bot est présent.</div>"
    else:
        rows = "".join(
            f"<tr><td>{g.name}</td><td>{g.member_count} membres</td>"
            f"<td><a href='{url_for('guild_page', guild_id=g.id)}'>Ouvrir →</a></td></tr>"
            for g in guilds
        )
        body = f"<h1>Tes serveurs</h1><div class='card'><table>{rows}</table></div>"
    return render(body)


@app.route("/login")
def login():
    params = {
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
    }
    return redirect(AUTHORIZE_URL + "?" + urlencode(params))


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Connexion refusée par Discord.", 400
    data = {
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": OAUTH_REDIRECT_URI,
    }
    r = requests.post(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if r.status_code != 200:
        return f"Erreur d'authentification Discord ({r.status_code}).", 400
    access_token = r.json()["access_token"]
    u = requests.get(USER_URL, headers={"Authorization": f"Bearer {access_token}"}).json()
    session["user_id"] = int(u["id"])
    session["username"] = u.get("username", "Utilisateur")
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/guild/<int:guild_id>")
@login_required
def guild_page(guild_id):
    guild = get_authorized_guild(guild_id)
    conf = guild_conf(guild_id)
    temps = temp_text_channels(guild)
    temp_list = ", ".join(f"#{c.name}" for c in temps) or "Aucun"
    channel_options = "".join(f"<option value='{c.id}'>#{c.name}</option>" for c in guild.text_channels)
    member_options = "".join(
        f"<option value='{m.id}'>{m.display_name} ({m})</option>"
        for m in sorted(guild.members, key=lambda m: m.display_name.lower())
        if not is_protected(m, guild)
    )

    body = f"""
    <h1>{guild.name}</h1>
    <div class='card muted'>{len(guild.channels)} salons/catégories · {len(guild.roles) - 1} rôles ·
    {guild.member_count} membres · Salons temporaires : {temp_list}</div>

    <div class='card'><h3>✏️ Message d'information</h3>
    <form method='post' action='{url_for('guild_message', guild_id=guild_id)}'>
      <label>Titre</label><input name='titre' value="{conf['message']['title']}">
      <label>Message ({{server}}, {{date}}, {{members}})</label>
      <textarea name='corps' rows='5'>{conf['message']['body']}</textarea>
      <button>Enregistrer</button>
    </form></div>

    <div class='card'><h3>📣 Annoncer</h3>
    <p class='muted'>Poste le message ci-dessus dans le premier salon temporaire.</p>
    <form method='post' action='{url_for('guild_announce', guild_id=guild_id)}'><button>Annoncer</button></form></div>

    <div class='card'><h3>🚧 Salons temporaires</h3>
    <form method='post' action='{url_for('guild_temp_create', guild_id=guild_id)}'>
      <label>Nom du salon</label><input name='nom' required>
      <label>Message à poster (optionnel)</label><textarea name='message' rows='3'></textarea>
      <button>Créer</button>
    </form>
    <form method='post' action='{url_for('guild_temp_delete', guild_id=guild_id)}' style='margin-top:10px'>
      <button class='danger'>Supprimer tous les salons temporaires</button>
    </form></div>

    <div class='card'><h3>✉️ Envoyer des messages</h3>
    <form method='post' action='{url_for('guild_messages_send', guild_id=guild_id)}'>
      <label>Salon</label><select name='salon'>{channel_options}</select>
      <label>Nombre (max {MAX_MESSAGES})</label><input type='number' name='nombre' min='1' max='{MAX_MESSAGES}' value='1'>
      <label>Texte (utilise {{n}} pour le numéro)</label><textarea name='texte' rows='3' required></textarea>
      <button>Envoyer</button>
    </form></div>

    <div class='card'><h3>🔨 Bannir un membre</h3>
    <form method='post' action='{url_for('guild_ban', guild_id=guild_id)}'
          onsubmit="return confirm('Bannir ce membre ?');">
      <label>Membre</label><select name='membre' required>{member_options}</select>
      <label>Raison</label><input name='raison' placeholder='Non précisée'>
      <button class='danger'>Bannir</button>
    </form></div>

    <div class='card'><h3>😴 Comptes inactifs</h3>
    <form method='post' action='{url_for('guild_inactifs', guild_id=guild_id)}'>
      <label>Jours sans message</label><input type='number' name='jours' min='1' value='30'>
      <label>Action</label><select name='action'><option value='kick'>Expulser (kick)</option><option value='ban'>Bannir (ban)</option></select>
      <button class='danger'>Trouver et expulser/bannir</button>
    </form></div>

    <div class='card'><h3>🚀 Lancer la restructuration</h3>
    <p class='muted'>⚠️ Action irréversible : supprime tous les salons (et les rôles si choisi), puis crée les salons temporaires.</p>
    <form method='post' action='{url_for('guild_launch', guild_id=guild_id)}'
          onsubmit="return confirm('Tous les salons vont être supprimés. Confirmer ?');">
      <label>Salons temporaires (virgules)</label><input name='salons' value='annonces-restructuration,discussion-temporaire'>
      <label><input type='checkbox' name='roles' value='1' checked style='width:auto;display:inline'> Supprimer aussi les rôles</label>
      <label><input type='checkbox' name='ping' value='1' style='width:auto;display:inline'> Mentionner @everyone</label>
      <button class='danger'>Lancer</button>
    </form></div>
    """
    return render(body, guild=guild)


@app.route("/guild/<int:guild_id>/ban", methods=["POST"])
@login_required
def guild_ban(guild_id):
    guild = get_authorized_guild(guild_id)
    membre_id = int(request.form["membre"])
    raison = request.form.get("raison", "").strip() or "Non précisée"

    target_member = guild.get_member(membre_id)
    if target_member and (target_member.id == guild.owner_id or is_protected(target_member, guild)):
        abort(403, "Ce membre est protégé, impossible de le bannir ainsi.")

    async def _ban():
        await guild.ban(discord.Object(id=membre_id), reason=f"{raison} (par {session['username']} via le site)")

    try:
        call_bot(_ban())
    except Exception as e:
        abort(400, f"Erreur lors du bannissement : {e}")
    log_action(guild_id, f"{session['username']} (Site web)", f"Membre {membre_id} banni : {raison}")
    return redirect(url_for("guild_page", guild_id=guild_id))


@app.route("/guild/<int:guild_id>/message", methods=["POST"])
@login_required
def guild_message(guild_id):
    guild = get_authorized_guild(guild_id)
    conf = guild_conf(guild_id)
    conf["message"] = {"title": request.form["titre"][:256], "body": request.form["corps"][:4000]}
    set_guild_conf(guild_id, conf)
    log_action(guild_id, f"{session['username']} (Site web)", "Message modifié")
    return redirect(url_for("guild_page", guild_id=guild_id))


@app.route("/guild/<int:guild_id>/announce", methods=["POST"])
@login_required
def guild_announce(guild_id):
    guild = get_authorized_guild(guild_id)
    temps = temp_text_channels(guild)
    if temps:
        call_bot(temps[0].send(embed=build_embed(guild)))
        log_action(guild_id, f"{session['username']} (Site web)", f"Message annoncé dans #{temps[0].name}")
    return redirect(url_for("guild_page", guild_id=guild_id))


@app.route("/guild/<int:guild_id>/temp/create", methods=["POST"])
@login_required
def guild_temp_create(guild_id):
    guild = get_authorized_guild(guild_id)
    nom = request.form["nom"].strip().lower().replace(" ", "-")
    message = request.form.get("message", "").strip()

    async def _create():
        ch = await guild.create_text_channel(nom)
        conf = guild_conf(guild_id)
        conf["temp_channels"].append(ch.id)
        set_guild_conf(guild_id, conf)
        if message:
            await ch.send(message, allowed_mentions=discord.AllowedMentions.none())
        return ch

    ch = call_bot(_create())
    log_action(guild_id, f"{session['username']} (Site web)", f"Salon temporaire créé : #{ch.name}")
    return redirect(url_for("guild_page", guild_id=guild_id))


@app.route("/guild/<int:guild_id>/temp/delete", methods=["POST"])
@login_required
def guild_temp_delete(guild_id):
    guild = get_authorized_guild(guild_id)
    conf = guild_conf(guild_id)

    async def _delete():
        count = 0
        for cid in conf["temp_channels"]:
            ch = guild.get_channel(cid)
            if ch:
                try:
                    await ch.delete(reason="Fin de la restructuration")
                    count += 1
                except discord.HTTPException:
                    pass
        return count

    count = call_bot(_delete())
    conf["temp_channels"] = []
    set_guild_conf(guild_id, conf)
    log_action(guild_id, f"{session['username']} (Site web)", f"{count} salon(s) temporaire(s) supprimé(s)")
    return redirect(url_for("guild_page", guild_id=guild_id))


@app.route("/guild/<int:guild_id>/messages/send", methods=["POST"])
@login_required
def guild_messages_send(guild_id):
    guild = get_authorized_guild(guild_id)
    channel = guild.get_channel(int(request.form["salon"]))
    nombre = max(1, min(MAX_MESSAGES, int(request.form["nombre"])))
    texte = request.form["texte"]
    if not isinstance(channel, discord.TextChannel):
        abort(400, "Salon invalide.")

    async def _send():
        sent = 0
        for i in range(1, nombre + 1):
            content = texte.replace("\\n", "\n").replace("{n}", str(i))
            try:
                await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
                sent += 1
            except discord.HTTPException:
                break
            await asyncio.sleep(SEND_DELAY)
        return sent

    sent = call_bot(_send())
    log_action(guild_id, f"{session['username']} (Site web)", f"{sent} message(s) envoyés dans #{channel.name}")
    return redirect(url_for("guild_page", guild_id=guild_id))


@app.route("/guild/<int:guild_id>/inactifs", methods=["POST"])
@login_required
def guild_inactifs(guild_id):
    guild = get_authorized_guild(guild_id)
    jours = max(1, int(request.form["jours"]))
    action = request.form["action"]

    async def _run():
        members = await find_inactive(guild, jours)
        done, errors = 0, 0
        for m in members:
            try:
                if action == "ban":
                    await m.ban(reason="Inactivité > seuil fixé", delete_message_days=0)
                else:
                    await m.kick(reason="Inactivité > seuil fixé")
                done += 1
            except discord.HTTPException:
                errors += 1
            await asyncio.sleep(1.0)
        return done, errors

    done, errors = call_bot(_run())
    verbe = "bannis" if action == "ban" else "expulsés"
    log_action(guild_id, f"{session['username']} (Site web)", f"{done} membre(s) {verbe} pour inactivité")
    return redirect(url_for("guild_page", guild_id=guild_id))


@app.route("/guild/<int:guild_id>/launch", methods=["POST"])
@login_required
def guild_launch(guild_id):
    guild = get_authorized_guild(guild_id)
    names = clean_names(request.form["salons"])
    delete_roles = "roles" in request.form
    ping = "ping" in request.form
    if not names:
        abort(400, "Indique au moins un salon.")

    stats = call_bot(run_restructure(guild, names, delete_roles, ping))
    log_action(
        guild_id, f"{session['username']} (Site web)",
        f"Restructuration lancée — {stats['channels']} salons et {stats['roles']} rôles supprimés, {stats['errors']} erreurs",
    )
    return redirect(url_for("guild_page", guild_id=guild_id))


@app.route("/guild/<int:guild_id>/logs")
@login_required
def guild_logs(guild_id):
    guild = get_authorized_guild(guild_id)
    conf = guild_conf(guild_id)
    rows = "".join(
        f"<tr><td>{l['ts']}</td><td>{l['actor']}</td><td>{l['action']}</td></tr>"
        for l in reversed(conf["logs"])
    ) or "<tr><td colspan='3'>Aucun log pour l'instant.</td></tr>"
    body = f"<h1>Logs — {guild.name}</h1><div class='card'><table><tr><th>Date</th><th>Auteur</th><th>Action</th></tr>{rows}</table></div>"
    return render(body, guild=guild)


@app.route("/guild/<int:guild_id>/securite")
@login_required
def guild_security(guild_id):
    guild = get_authorized_guild(guild_id)
    s = guild_conf(guild_id)["security"]

    def chk(cond):
        return "checked" if cond else ""

    body = f"""
    <h1>🛡️ Sécurité — {guild.name}</h1>
    <form method='post' action='{url_for('guild_security_save', guild_id=guild_id)}'>

    <div class='card'><h3>Anti-spam</h3>
    <label><input type='checkbox' name='antispam' {chk(s['antispam']['enabled'])} style='width:auto;display:inline'> Activer</label>
    <label>Messages max avant mute</label><input type='number' name='max_messages' value='{s['antispam']['max_messages']}'>
    <label>Fenêtre (secondes)</label><input type='number' name='fenetre_secondes' value='{s['antispam']['window_seconds']}'>
    <label>Mentions max avant suppression</label><input type='number' name='max_mentions' value='{s['antispam']['max_mentions']}'>
    <label><input type='checkbox' name='bloquer_liens' {chk(s['antispam']['block_links'])} style='width:auto;display:inline'> Bloquer les liens non autorisés</label>
    </div>

    <div class='card'><h3>Anti-raid</h3>
    <label><input type='checkbox' name='antiraid' {chk(s['antiraid']['enabled'])} style='width:auto;display:inline'> Activer</label>
    <label>Seuil d'arrivées</label><input type='number' name='seuil_arrivees' value='{s['antiraid']['join_threshold']}'>
    <label>Fenêtre (secondes)</label><input type='number' name='fenetre_arrivees' value='{s['antiraid']['window_seconds']}'>
    <label>Action</label>
    <select name='action_antiraid'>
      <option value='lockdown' {"selected" if s['antiraid']['action']=='lockdown' else ""}>Verrouiller (lockdown)</option>
      <option value='kick' {"selected" if s['antiraid']['action']=='kick' else ""}>Expulser les comptes récents</option>
      <option value='ban' {"selected" if s['antiraid']['action']=='ban' else ""}>Bannir les comptes récents</option>
    </select>
    </div>

    <div class='card'><h3>Escalade des avertissements</h3>
    <label><input type='checkbox' name='escalade' {chk(s['escalade']['enabled'])} style='width:auto;display:inline'> Activer</label>
    <label>Mute à partir de X avertissements</label><input type='number' name='mute_a' value='{s['escalade']['mute_a']}'>
    <label>Kick à partir de X avertissements</label><input type='number' name='kick_a' value='{s['escalade']['kick_a']}'>
    <label>Expiration des avertissements (jours, 0 = jamais)</label><input type='number' name='expiration_jours' value='{s['escalade']['expiration_jours']}'>
    </div>

    <div class='card'><h3>Autres protections</h3>
    <label><input type='checkbox' name='usurpation' {chk(s['antiusurpation']['enabled'])} style='width:auto;display:inline'> Anti-usurpation de pseudo</label><br>
    <label><input type='checkbox' name='antisuppression' {chk(s['antidelete']['enabled'])} style='width:auto;display:inline'> Anti-suppression massive</label><br>
    <label><input type='checkbox' name='filtre_mots' {chk(s['filtre_mots']['enabled'])} style='width:auto;display:inline'> Filtre de mots interdits</label><br>
    <label><input type='checkbox' name='surveiller_webhooks' {chk(s.get('surveiller_webhooks', False))} style='width:auto;display:inline'> Surveiller les webhooks</label><br>
    <label><input type='checkbox' name='verrouiller_vocaux' {chk(s.get('verrouiller_vocaux', True))} style='width:auto;display:inline'> Le lockdown couvre aussi les vocaux</label>
    </div>

    <button>Enregistrer</button>
    </form>
    """
    return render(body, guild=guild)


@app.route("/guild/<int:guild_id>/securite/save", methods=["POST"])
@login_required
def guild_security_save(guild_id):
    guild = get_authorized_guild(guild_id)
    conf = guild_conf(guild_id)
    s = conf["security"]
    f = request.form

    s["antispam"]["enabled"] = "antispam" in f
    s["antispam"]["max_messages"] = int(f.get("max_messages", s["antispam"]["max_messages"]))
    s["antispam"]["window_seconds"] = int(f.get("fenetre_secondes", s["antispam"]["window_seconds"]))
    s["antispam"]["max_mentions"] = int(f.get("max_mentions", s["antispam"]["max_mentions"]))
    s["antispam"]["block_links"] = "bloquer_liens" in f

    s["antiraid"]["enabled"] = "antiraid" in f
    s["antiraid"]["join_threshold"] = int(f.get("seuil_arrivees", s["antiraid"]["join_threshold"]))
    s["antiraid"]["window_seconds"] = int(f.get("fenetre_arrivees", s["antiraid"]["window_seconds"]))
    s["antiraid"]["action"] = f.get("action_antiraid", s["antiraid"]["action"])

    s["escalade"]["enabled"] = "escalade" in f
    s["escalade"]["mute_a"] = int(f.get("mute_a", s["escalade"]["mute_a"]))
    s["escalade"]["kick_a"] = int(f.get("kick_a", s["escalade"]["kick_a"]))
    s["escalade"]["expiration_jours"] = int(f.get("expiration_jours", s["escalade"]["expiration_jours"]))

    s["antiusurpation"]["enabled"] = "usurpation" in f
    s["antidelete"]["enabled"] = "antisuppression" in f
    s["filtre_mots"]["enabled"] = "filtre_mots" in f
    s["surveiller_webhooks"] = "surveiller_webhooks" in f
    s["verrouiller_vocaux"] = "verrouiller_vocaux" in f

    set_guild_conf(guild_id, conf)
    log_action(guild_id, f"{session['username']} (Site web)", "Réglages de sécurité modifiés")
    return redirect(url_for("guild_security", guild_id=guild_id))


def run_dashboard():
    if not (OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET and OAUTH_REDIRECT_URI and FLASK_SECRET_KEY):
        print("ℹ️  Dashboard désactivé : identifiants OAuth2 ou FLASK_SECRET_KEY manquants.")
        return
    print(f"🌐 Dashboard démarré sur http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, use_reloader=False)


_dashboard_started = False


@bot.event
async def on_ready():
    global _dashboard_started
    print(f"Connecté en tant que {bot.user} ({len(bot.guilds)} serveurs)")
    if not _dashboard_started:
        _dashboard_started = True
        threading.Thread(target=run_dashboard, daemon=True).start()
    if not reminder_loop.is_running():
        reminder_loop.start()


bot.run(TOKEN)
