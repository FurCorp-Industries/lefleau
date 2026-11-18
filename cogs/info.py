"""
cogs/info.py
--------------
Commandes d'information générales sur le bot (changelog, about/help, etc).
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
from data.changelog import CHANGELOG


def build_about_embed(client: discord.Client) -> discord.Embed:
    """Construit l'embed de présentation rapide du bot (page 1 de /about)."""
    bot_name = client.user.display_name if client.user else "Ce bot"
    embed = discord.Embed(
        title=f"🏴‍☠️ {bot_name} — Courtier de Grand Line & Intendant du Serveur",
        description=(
            "**💰 Économie**\n"
            "Gagne des Berrys (฿), achète des Fruits du Démon et monte ta prime !\n\n"
            "**⚔️ Boss**\n"
            "Affronte en équipe le boss du serveur avec `/attack` — le butin est "
            "réparti selon les dégâts infligés, et tes Fruits du Démon boostent tes coups !\n\n"
            "**⚓ Marine**\n"
            "Gardien de la paix (modération & sécurité).\n\n"
            "Tape `/help` ou `/profile` pour démarrer ton aventure.\n\n"
            "**🛠️ Support / Admin**\n"
            "DM @Maxana_The_Avali"
        ),
        color=config.COLOR_ECONOMY,
    )
    embed.set_footer(text="Clique ci-dessous pour un guide de démarrage pas à pas.")
    return embed


def build_tutorial_embed() -> discord.Embed:
    """Construit l'embed du tutoriel de démarrage (page 2 de /about)."""
    embed = discord.Embed(
        title="📖 Comment commencer ton aventure ?",
        description="Voici les premiers pas pour te lancer sur le Grand Line :",
        color=config.COLOR_SHOP,
    )
    embed.add_field(
        name="1️⃣ Récupère ton premier argent",
        value="`/daily` — récompense quotidienne gratuite (cooldown 24h)",
        inline=False,
    )
    embed.add_field(
        name="2️⃣ Gagne des Berrys régulièrement",
        value="`/work` — un petit boulot sûr, cooldown plus court",
        inline=False,
    )
    embed.add_field(
        name="3️⃣ Tente ta chance",
        value="`/crime` ou `/pillage` — plus risqué (la Marine peut te choper), mais bien plus payant",
        inline=False,
    )
    embed.add_field(
        name="4️⃣ Équipe-toi d'un pouvoir",
        value="`/shop` pour voir les Fruits du Démon, `/buy` pour en acheter un, puis `/eat` pour l'activer",
        inline=False,
    )
    embed.add_field(
        name="5️⃣ Suis ta progression",
        value="`/profile` affiche ton avis de recherche : avatar, flotte, titre et prime",
        inline=False,
    )
    embed.add_field(
        name="⚓ Reste dans les règles",
        value="La Marine (modération) veille sur le serveur — un peu de sagesse t'évitera un séjour à Impel Down.",
        inline=False,
    )
    embed.set_footer(text="Bon vent, moussaillon !")
    return embed


class AboutView(discord.ui.View):
    """Vue de la page 1 de /about, avec un bouton vers le tutoriel."""

    def __init__(self):
        super().__init__(timeout=180)
        self.message: discord.Message | None = None

    @discord.ui.button(label="Comment commencer ?", style=discord.ButtonStyle.primary, emoji="🧭")
    async def show_tutorial(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = TutorialView()
        await interaction.response.edit_message(embed=build_tutorial_embed(), view=view)
        view.message = interaction.message

    async def on_timeout(self):
        if self.message is None:
            return
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass


class TutorialView(discord.ui.View):
    """Vue de la page 2 de /about (le tutoriel), avec un bouton retour."""

    def __init__(self):
        super().__init__(timeout=180)
        self.message: discord.Message | None = None

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AboutView()
        await interaction.response.edit_message(embed=build_about_embed(interaction.client), view=view)
        view.message = interaction.message

    async def on_timeout(self):
        if self.message is None:
            return
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass


class Info(commands.Cog):
    """Commandes d'information sur le bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /about et /help (alias, même contenu)
    # ------------------------------------------------------------------
    async def _send_about(self, interaction: discord.Interaction):
        view = AboutView()
        await interaction.response.send_message(embed=build_about_embed(interaction.client), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="about", description="Présentation rapide du bot et de ses fonctionnalités.")
    async def about(self, interaction: discord.Interaction):
        await self._send_about(interaction)

    @app_commands.command(name="help", description="Présentation rapide du bot et guide de démarrage.")
    async def help_cmd(self, interaction: discord.Interaction):
        await self._send_about(interaction)

    # ------------------------------------------------------------------
    # /changelog
    # ------------------------------------------------------------------
    @app_commands.command(name="changelog", description="Affiche l'historique des mises à jour du bot.")
    async def changelog(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📜 Journal de bord du Log Pose",
            description="Historique des mises à jour du bot, de la plus récente à la plus ancienne.",
            color=config.COLOR_ECONOMY,
        )

        # Limite Discord : 25 fields max par embed -> on garde les 10 versions les plus récentes
        for entry in CHANGELOG[:10]:
            value = "\n".join(f"• {change}" for change in entry["changes"])
            embed.add_field(
                name=f"Version {entry['version']} — {entry['date']}",
                value=value,
                inline=False,
            )

        embed.set_footer(text="Que l'aventure continue ! 🏴‍☠️")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
