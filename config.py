"""
config.py
----------
Toutes les constantes de configuration du bot sont centralisées ici.
Ça permet d'ajuster facilement l'équilibrage de l'économie sans
fouiller dans le code des Cogs.
"""

import os
from dotenv import load_dotenv

# Charge les variables d'environnement depuis le fichier .env
load_dotenv()

# --- Token & IDs ---
TOKEN = os.getenv("DISCORD_TOKEN")
# GUILD_ID optionnel : si renseigné, les slash commands se synchronisent
# instantanément sur CE serveur (pratique en développement).
# Si vide, la sync est globale (peut prendre jusqu'à 1h pour apparaître).
GUILD_ID = os.getenv("GUILD_ID")

# --- Liaison Roblox OAuth 2.0 ---
ROBLOX_CLIENT_ID = os.getenv("ROBLOX_CLIENT_ID")
ROBLOX_CLIENT_SECRET = os.getenv("ROBLOX_CLIENT_SECRET")
ROBLOX_REDIRECT_URI = os.getenv(
    "ROBLOX_REDIRECT_URI", "https://verify.lefleau.online/roblox/callback"
)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://verify.lefleau.online")
ROBLOX_WEB_HOST = os.getenv("ROBLOX_WEB_HOST", "127.0.0.1")
ROBLOX_WEB_PORT = int(os.getenv("ROBLOX_WEB_PORT", "8080"))
ROBLOX_VERIFIED_ROLE_ID = os.getenv("ROBLOX_VERIFIED_ROLE_ID")

# --- Panel web du bot principal ---
PANEL_ENABLED = os.getenv("PANEL_ENABLED", "false").lower() in {"1", "true", "yes", "oui"}
PANEL_CLIENT_ID = os.getenv("PANEL_CLIENT_ID", "")
PANEL_CLIENT_SECRET = os.getenv("PANEL_CLIENT_SECRET", "")
PANEL_BASE_URL = os.getenv(
    "PANEL_BASE_URL", "https://panel.lefleau.online/le-fleau"
).rstrip("/")
PANEL_SESSION_SECRET = os.getenv("PANEL_SESSION_SECRET", "")
PANEL_HOST = os.getenv("PANEL_HOST", "127.0.0.1")
PANEL_PORT = int(os.getenv("PANEL_PORT", "8082"))
PANEL_PREFIX = "/" + os.getenv("PANEL_PREFIX", "le-fleau").strip("/")
PANEL_COOKIE_DOMAIN = os.getenv("PANEL_COOKIE_DOMAIN", ".lefleau.online")

# --- Panel Owner séparé ---
# Peut réutiliser l'application OAuth2 du panel principal, à condition
# d'ajouter https://owner.lefleau.online/auth/callback à ses Redirects OAuth2.
OWNER_PANEL_ENABLED = os.getenv("OWNER_PANEL_ENABLED", "false").lower() in {"1", "true", "yes", "oui"}
OWNER_PANEL_CLIENT_ID = os.getenv("OWNER_PANEL_CLIENT_ID") or PANEL_CLIENT_ID
OWNER_PANEL_CLIENT_SECRET = os.getenv("OWNER_PANEL_CLIENT_SECRET") or PANEL_CLIENT_SECRET
OWNER_PANEL_BASE_URL = os.getenv("OWNER_PANEL_BASE_URL", "https://owner.lefleau.online").rstrip("/")
OWNER_PANEL_SESSION_SECRET = os.getenv("OWNER_PANEL_SESSION_SECRET", "")
OWNER_PANEL_HOST = os.getenv("OWNER_PANEL_HOST", "127.0.0.1")
OWNER_PANEL_PORT = int(os.getenv("OWNER_PANEL_PORT", "8083"))
OWNER_PANEL_USER_IDS = {
    int(value.strip())
    for value in os.getenv("OWNER_PANEL_USER_IDS", "").split(",")
    if value.strip().isdigit()
}

# --- Base de données ---
DATABASE_PATH = "data/economy.db"

# --- Monnaie ---
CURRENCY_NAME = "Berrys"
CURRENCY_SYMBOL = "฿"

# --- Couleurs des embeds (thématique) ---
COLOR_ECONOMY = 0xF1C40F      # Or, couleur "trésor"
COLOR_SUCCESS = 0x2ECC71      # Vert
COLOR_ERROR = 0xE74C3C        # Rouge
COLOR_MARINE = 0x3498DB       # Bleu Marine (modération)
COLOR_SHOP = 0x9B59B6         # Violet (boutique / fruits du démon)

# --- Solde de départ pour un nouveau pirate ---
STARTING_WALLET = 500

# --- /daily ---
DAILY_MIN = 500
DAILY_MAX = 1500
DAILY_COOLDOWN = 24 * 60 * 60  # 24h en secondes

# --- /work ---
WORK_MIN = 200
WORK_MAX = 800
WORK_COOLDOWN = 60 * 60  # 1h en secondes

WORK_MESSAGES = [
    "Tu as aidé Franky à réparer le Thousand Sunny et gagné {amount}{symbol} !",
    "Tu as pêché un poisson géant à Fish-Man Island et tu l'as revendu {amount}{symbol} !",
    "Tu as servi des ramens dans le restaurant du Baratie et empoché {amount}{symbol} !",
    "Sanji t'a payé {amount}{symbol} pour ne pas avoir brûlé la cuisine.",
    "Usopp t'a vendu une invention douteuse... mais ça a rapporté {amount}{symbol} !",
    "Tu as vendu des cartes au trésor (probablement fausses) pour {amount}{symbol}.",
    "Nami t'a donné {amount}{symbol}... et t'a fait signer des intérêts à 300%.",
    "Tu as livré du courrier via un Den Den Mushi et touché {amount}{symbol}.",
    "Zoro s'est perdu en allant travailler mais a quand même ramené {amount}{symbol}.",
    "Tu as réparé le mât endommagé pendant la tempête, gain de {amount}{symbol}.",
]

# --- /crime (ou /pillage) ---
CRIME_MIN = 800
CRIME_MAX = 2000
CRIME_COOLDOWN = 2 * 60 * 60  # 2h en secondes
CRIME_SUCCESS_RATE = 0.60  # 60% de chances de réussir le coup

CRIME_FINE_MIN = 300
CRIME_FINE_MAX = 1000

CRIME_SUCCESS_MESSAGES = [
    "Tu as pillé un navire marchand sous le nez des Marines et récupéré {amount}{symbol} !",
    "Un raid éclair sur l'entrepôt de la Marine t'a rapporté {amount}{symbol} !",
    "Tu as dévalisé un noble mondial imprudent : {amount}{symbol} en poche !",
    "Coup de maître à Loguetown, tu repars avec {amount}{symbol} !",
]

CRIME_FAIL_MESSAGES = [
    "Un Marine de faction t'a repéré ! Tu payes une amende de {fine}{symbol}.",
    "Smoker t'a mis la main dessus. Amende salée : {fine}{symbol}.",
    "Le CP9 t'a intercepté avant que tu ne t'enfuies. Amende de {fine}{symbol}.",
    "Un Pacifista t'a canardé pendant ta fuite. Tu perds {fine}{symbol} en soins.",
]

# --- Titres de prime : voir data/titles.py (10 titres débloqués selon la prime) ---
# --- Flottes du serveur : voir data/fleets.py (mapping rôle Discord -> flotte) ---

# --- Combats de Boss (/boss, /attack) ---
ATTACK_MIN = 80
ATTACK_MAX = 200
ATTACK_COOLDOWN = 45  # secondes entre deux attaques

# Le rendement augmente avec la difficulté du boss. La première limite dont
# les PV sont inférieurs ou égaux est utilisée ; ``None`` couvre les boss plus
# puissants ajoutés ultérieurement au roster.
BOSS_REWARD_SCALING = (
    (10_000, 0.40),   # Jusqu'à 10 000 PV : 0,40 Berry par PV
    (25_000, 0.45),   # Jusqu'à 25 000 PV : 0,45 Berry par PV
    (50_000, 0.50),   # Jusqu'à 50 000 PV : 0,50 Berry par PV
    (100_000, 0.55),  # Jusqu'à 100 000 PV : 0,55 Berry par PV
    (None, 0.60),     # Plus de 100 000 PV : 0,60 Berry par PV
)
BOSS_MVP_BONUS_RATIO = 0.10   # Bonus MVP égal à 10 % du pool commun
BOSS_MVP_BONUS_MIN = 500      # Plancher du bonus MVP
BOSS_MVP_BONUS_MAX = 10_000   # Plafond anti-inflation du bonus MVP
BOSS_BOUNTY_RATIO = 0.25      # Fraction du gain en Berrys aussi ajoutée à la prime

ATTACK_MESSAGES = [
    "Tu frappes {boss} de toutes tes forces et inflige {damage} dégâts !",
    "Un coup bien placé sur {boss} : {damage} dégâts !",
    "Tu esquives une attaque et contre-attaques {boss} pour {damage} dégâts !",
    "{boss} encaisse {damage} dégâts de ta part !",
]

# --- Casino : Blackjack (/blackjack) ---
BLACKJACK_NATURAL_MULTIPLIER = 2.5  # Blackjack naturel (21 avec 2 cartes) : mise x2.5
BLACKJACK_WIN_MULTIPLIER = 2.0       # Victoire normale : mise x2

# --- Casino : Roulette (/roulette) ---
ROULETTE_STRAIGHT_MULTIPLIER = 36    # Pari sur un numéro précis (0-36) : mise x36
ROULETTE_EVEN_CHANCE_MULTIPLIER = 2  # Pari rouge/noir/pair/impair/manque/passe : mise x2

ROULETTE_RED_NUMBERS = {
    1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36,
}

# --- Casino : Poker vidéo (/poker) ---
# La table des gains (POKER_PAYOUTS) et les noms de mains (POKER_HAND_NAMES)
# vivent dans utils/cards.py, à côté de la logique d'évaluation des mains.

# --- Mise minimale/maximale pour tous les jeux de casino ---
CASINO_MIN_BET = 10
CASINO_MAX_BET = 100_000

# --- Quêtes (/quest) ---
QUEST_MIN = 400
QUEST_MAX = 1200
QUEST_COOLDOWN = 3 * 60 * 60  # 3h en secondes
QUEST_MATERIAL_CHANCE = 0.70   # probabilité d'obtenir un matériau en plus des Berrys

# --- Amélioration des Fruits du Démon (/enhance) ---
MAX_FRUIT_LEVEL = 5
FRUIT_LEVEL_BONUS = 0.15  # +15% d'efficacité par niveau au-dessus de 1

# Coût pour passer AU niveau indiqué (ex: 2 = coût pour passer de 1 à 2)
FRUIT_UPGRADE_REQUIREMENTS = {
    2: {"berrys": 3000, "materials": {"kairoseki": 3}},
    3: {"berrys": 8000, "materials": {"kairoseki": 5, "log_pose": 2}},
    4: {"berrys": 20000, "materials": {"log_pose": 5, "poneglyph": 2}},
    5: {"berrys": 50000, "materials": {"poneglyph": 3, "adam_wood": 1}},
}

# --- Passif spécial : Barbe Noire (/barbenoire) ---
# Débloque le multi-équipement de Fruits du Démon (cumul illimité des bonus).
# Prix volontairement énorme : c'est un objectif de fin de jeu.
BARBE_NOIRE_PRICE = 750_000
