"""
utils/helpers.py
------------------
Petites fonctions utilitaires réutilisées dans plusieurs Cogs :
formatage des montants/durées, calcul des effets de fruits,
parsing de durée pour le /timeout, etc.
"""

import re
import unicodedata

import config
import database as db
from data.fruits import FRUITS
from data.titles import get_title
from data.fleets import FLEETS


def format_berrys(amount: int) -> str:
    """Formate un montant en Berrys avec séparateur de milliers : 12 345฿"""
    return f"{amount:,}".replace(",", " ") + config.CURRENCY_SYMBOL


def format_duration(seconds: float) -> str:
    """Formate une durée en secondes en texte lisible (ex: '2h 15m 3s')."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def get_bounty_title(bounty: int) -> str:
    """Retourne le titre de pirate correspondant à une prime donnée (voir data/titles.py)."""
    return get_title(bounty)


def _normalize(text: str) -> str:
    """Normalise une chaîne pour comparaison : minuscules, sans accents, espaces simplifiés."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.lower().split())


def get_member_fleet(member) -> str | None:
    """
    Détermine la flotte d'un membre à partir de ses rôles Discord.
    Retourne le nom d'affichage de la flotte la plus puissante que le membre
    possède, ou None s'il n'a aucun rôle de flotte reconnu.

    La comparaison ignore la casse, les accents et les espaces superflus,
    pour éviter les faux négatifs liés à de petites différences de saisie.
    """
    member_role_names = {_normalize(role.name) for role in getattr(member, "roles", [])}

    for fleet in FLEETS:
        if _normalize(fleet["role_name"]) in member_role_names:
            return fleet["display_name"]

    return None


async def get_equipped_fruits_and_levels(user_id: int, guild_id: int) -> tuple[list[str], dict[str, int]]:
    """
    Récupère en une fois la liste des fruits équipés d'un joueur ainsi que
    le niveau de chacun — pratique pour éviter de répéter cette logique
    dans chaque commande qui a besoin des bonus de fruits.
    """
    fruit_ids = await db.get_equipped_fruits(user_id, guild_id)
    levels = {fid: await db.get_fruit_level(user_id, guild_id, fid) for fid in fruit_ids}
    return fruit_ids, levels


def get_fruits_effect_value(fruit_ids: list[str], effect_key: str, levels: dict[str, int]) -> float:
    """
    Retourne la somme des valeurs d'un effet donné sur TOUS les fruits
    équipés (normalement un seul, sauf avec le passif Barbe Noire qui
    permet d'en cumuler plusieurs — voir /barbenoire). Chaque fruit est
    mis à l'échelle selon son propre niveau d'amélioration (/enhance).

    `levels` est un dict {fruit_id: niveau}, niveau par défaut 1 si absent.
    """
    total = 0.0
    for fruit_id in fruit_ids:
        fruit = FRUITS.get(fruit_id)
        if fruit is None or fruit["effect"] != effect_key:
            continue
        level = levels.get(fruit_id, 1)
        total += fruit["value"] * (1 + config.FRUIT_LEVEL_BONUS * (level - 1))
    return total


DURATION_REGEX = re.compile(r"(\d+)\s*(s|m|h|d|j)", re.IGNORECASE)
DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "j": 86400,  # "j" pour "jours", pratique pour les francophones
}


def parse_duration(duration_str: str) -> int | None:
    """
    Parse une durée écrite en langage humain (ex: '10m', '1h', '2d', '30s')
    et retourne le nombre de secondes correspondant.
    Retourne None si le format n'est pas reconnu.
    """
    match = DURATION_REGEX.match(duration_str.strip())
    if not match:
        return None

    value, unit = match.groups()
    return int(value) * DURATION_UNITS[unit.lower()]


def get_fruits_combat_bonus(fruit_ids: list[str], levels: dict[str, int]) -> float:
    """
    Retourne la somme des bonus de dégâts (en fraction, ex: 0.15 = +15%)
    de TOUS les fruits équipés, mis à l'échelle selon leur niveau
    d'amélioration respectif. 0.0 si aucun fruit équipé.
    """
    total = 0.0
    for fruit_id in fruit_ids:
        fruit = FRUITS.get(fruit_id)
        if fruit is None:
            continue
        level = levels.get(fruit_id, 1)
        base = fruit.get("combat_bonus", 0.0)
        total += base * (1 + config.FRUIT_LEVEL_BONUS * (level - 1))
    return total


def format_hp_bar(current: int, maximum: int, length: int = 20) -> str:
    """Construit une barre de PV textuelle du type [██████░░░░] 60%."""
    if maximum <= 0:
        ratio = 0.0
    else:
        ratio = max(0.0, min(1.0, current / maximum))

    filled = round(ratio * length)
    bar = "█" * filled + "░" * (length - filled)
    percent = round(ratio * 100)
    return f"`[{bar}]` {percent}%"
