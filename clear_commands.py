"""
clear_commands.py
--------------------
Script à lancer UNE SEULE FOIS pour supprimer toutes les anciennes
slash commands (globales ET spécifiques à un serveur) avant de relancer
bot.py proprement.

Utile quand tu vois des commandes en double, ou des commandes d'un
ancien projet/bot qui traînent encore dans la liste Discord.

Lancement : python clear_commands.py
"""

import asyncio
import discord
from discord.ext import commands

import config

intents = discord.Intents.default()


async def main():
    if not config.TOKEN:
        print("❌ Aucun TOKEN trouvé dans .env")
        return

    bot = commands.Bot(command_prefix="op!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"Connecté en tant que {bot.user}\n")

        # --- 1. Nettoyage des commandes GLOBALES ---
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()
        print("✅ Commandes globales effacées (peut prendre jusqu'à 1h pour disparaître partout).")

        # --- 2. Nettoyage des commandes du serveur configuré (si GUILD_ID renseigné) ---
        if config.GUILD_ID:
            guild = discord.Object(id=int(config.GUILD_ID))
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
            print(f"✅ Commandes du serveur {config.GUILD_ID} effacées (instantané).")
        else:
            print("ℹ️ Aucun GUILD_ID configuré dans .env, nettoyage global uniquement.")

        print("\n🧹 Nettoyage terminé ! Relance maintenant : python bot.py")
        await bot.close()

    await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
