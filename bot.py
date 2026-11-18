"""
bot.py
-------
Point d'entrée principal du bot One Piece.

Lancement : python bot.py
(assure-toi d'avoir configuré ton fichier .env au préalable, voir .env.example)
"""

import asyncio
import logging

import discord
from discord.ext import commands

import config
import database as db
from console import AdminConsole

# --- Configuration du logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("onepiece-bot")

# --- Liste des Cogs à charger au démarrage ---
INITIAL_EXTENSIONS = [
    "cogs.economy",
    "cogs.shop",
    "cogs.custom_shop",
    "cogs.moderation",
    "cogs.admin_economy",
    "cogs.info",
    "cogs.boss",
    "cogs.casino",
    "cogs.quests",
    "cogs.tickets",
    "cogs.logs",
    "cogs.bloxfruits",
    "cogs.community_tools",
    "cogs.roblox_link",
    "cogs.web_panel",
    "cogs.owner_panel",
    "cogs.server_tags",
    "cogs.join_roles",
    "cogs.custom_messages",
    "cogs.reaction_roles",
]

# --- Intents : on active les intents nécessaires ---
intents = discord.Intents.default()
intents.members = True  # nécessaire pour /kick, /ban, /timeout, etc.
intents.message_content = True  # nécessaire pour logger le contenu des messages supprimés/modifiés


class OnePieceBot(commands.Bot):
    """Bot Discord principal, sous-classé pour gérer proprement le setup_hook."""

    def __init__(self):
        super().__init__(command_prefix="op!", intents=intents, help_command=None)

    async def setup_hook(self):
        # Initialisation de la base de données AVANT de charger les Cogs
        await db.init_db()
        logger.info("Base de données initialisée.")

        # Chargement de tous les Cogs
        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
                logger.info(f"Extension chargée : {extension}")
            except Exception as e:
                logger.error(f"Échec du chargement de {extension} : {e}")

        # Synchronisation des Slash Commands
        if config.GUILD_ID:
            # Sync rapide sur un serveur précis (pratique en dev)
            guild = discord.Object(id=int(config.GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(f"{len(synced)} commande(s) synchronisée(s) sur le serveur {config.GUILD_ID}.")
        else:
            # Sync globale (peut prendre jusqu'à 1h pour se propager)
            synced = await self.tree.sync()
            logger.info(f"{len(synced)} commande(s) synchronisée(s) globalement.")

    async def on_ready(self):
        logger.info(f"Connecté en tant que {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="le Grand Line 🏴‍☠️ | /profile",
            )
        )

        # Démarre le panel de contrôle en terminal (une seule fois, même si
        # on_ready se redéclenche après une reconnexion Discord).
        if not getattr(self, "_console_started", False):
            self._console_started = True
            console = AdminConsole(self, asyncio.get_running_loop())
            console.start()


bot = OnePieceBot()


async def main():
    if not config.TOKEN:
        logger.error(
            "Aucun TOKEN trouvé ! Vérifie que ton fichier .env contient bien "
            "DISCORD_TOKEN=ton_token_ici"
        )
        return

    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
