"""
cogs/admin_economy.py
------------------------
Commandes réservées aux administrateurs pour gérer manuellement
l'économie du serveur (donner ou retirer des Berrys).
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils.helpers import format_berrys


class AdminEconomy(commands.Cog):
    """Commandes d'administration de l'économie (Gouvernement Mondial)."""

    berrys_admin = app_commands.Group(name="berrys-admin", description="Administration des Berrys", guild_only=True)

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /add-berrys
    # ------------------------------------------------------------------
    @berrys_admin.command(name="add", description="[Admin] Donne des Berrys à un joueur.")
    @app_commands.describe(membre="Le joueur qui reçoit les Berrys", montant="Montant à ajouter")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def add_berrys(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        montant: app_commands.Range[int, 1, 1_000_000_000],
    ):
        new_wallet = await db.update_wallet(membre.id, interaction.guild_id, montant)

        embed = discord.Embed(
            title="💰 Trésor du Gouvernement Mondial distribué",
            description=(
                f"**{format_berrys(montant)}** ont été ajoutés au compte de "
                f"**{membre.display_name}**."
            ),
            color=config.COLOR_SUCCESS,
        )
        embed.set_footer(text=f"Nouveau solde : {format_berrys(new_wallet)}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /remove-berrys
    # ------------------------------------------------------------------
    @berrys_admin.command(name="remove", description="[Admin] Retire des Berrys à un joueur.")
    @app_commands.describe(membre="Le joueur à qui retirer des Berrys", montant="Montant à retirer")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def remove_berrys(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        montant: app_commands.Range[int, 1, 1_000_000_000],
    ):
        new_wallet = await db.update_wallet(membre.id, interaction.guild_id, -montant)

        embed = discord.Embed(
            title="⚓ Saisie de fonds par la Marine",
            description=(
                f"**{format_berrys(montant)}** ont été confisqués à "
                f"**{membre.display_name}**."
            ),
            color=config.COLOR_MARINE,
        )
        embed.set_footer(text=f"Nouveau solde : {format_berrys(new_wallet)}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Gestion des erreurs
    # ------------------------------------------------------------------
    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="🚫 Accès refusé",
                description="Seuls les administrateurs du Gouvernement Mondial peuvent faire ça.",
                color=config.COLOR_ERROR,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminEconomy(bot))
