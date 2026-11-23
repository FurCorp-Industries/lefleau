"""
cogs/economy.py
-----------------
Toutes les commandes économiques de base : gains d'argent et consultation
du profil/solde du joueur.
"""

import random

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from data.fruits import FRUITS
from utils.helpers import (
    format_berrys,
    format_duration,
    get_bounty_title,
    get_fruits_effect_value,
    get_equipped_fruits_and_levels,
    get_member_fleet,
)
from utils.image_gen import generate_wanted_poster


class ResetConfirmView(discord.ui.View):
    """
    Vue avec boutons de confirmation pour /reset.
    Seul l'auteur de la commande peut cliquer, et la vue expire après 30s.
    """

    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.confirmed: bool | None = None  # None = pas encore répondu / timeout

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seule la personne ayant lancé `/reset` peut confirmer.", ephemeral=True
            )
            return False
        return True

    async def _disable_all(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Confirmer la réinitialisation", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await self._disable_all()
        self.stop()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        await self._disable_all()
        self.stop()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        await self._disable_all()


class Economy(commands.Cog):
    """Commandes liées à l'économie : /daily, /work, /crime, /balance, /profile"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /daily
    # ------------------------------------------------------------------
    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne de pirate.")
    async def daily(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild_id
        user = await db.get_user(user_id, guild_id)
        equipped_fruits, fruit_levels = await get_equipped_fruits_and_levels(user_id, guild_id)

        # Application de la réduction de cooldown si Mera Mera (ou équivalent) équipé
        reduction = get_fruits_effect_value(equipped_fruits, "cooldown_reduction", fruit_levels)
        effective_cooldown = config.DAILY_COOLDOWN * (1 - reduction)

        remaining = db.get_cooldown_remaining(user["last_daily"], effective_cooldown)
        if remaining > 0:
            embed = discord.Embed(
                title="⏳ Pas si vite, moussaillon !",
                description=(
                    f"Tu dois attendre encore **{format_duration(remaining)}** "
                    f"avant de pouvoir réclamer ta récompense quotidienne."
                ),
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        amount = random.randint(config.DAILY_MIN, config.DAILY_MAX)
        doubled = False

        # Effet Ope Ope no Mi : chance de doubler le gain
        double_chance = get_fruits_effect_value(equipped_fruits, "daily_double_chance", fruit_levels)
        if double_chance and random.random() < double_chance:
            amount *= 2
            doubled = True

        await db.update_wallet(user_id, guild_id, amount)
        await db.set_cooldown(user_id, guild_id, "last_daily")

        description = f"Tu as reçu ta récompense quotidienne : **{format_berrys(amount)}** !"
        if doubled:
            description += "\n💠 **L'Ope Ope no Mi a doublé ton gain !**"

        embed = discord.Embed(
            title="☀️ Récompense quotidienne",
            description=description,
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /work
    # ------------------------------------------------------------------
    @app_commands.command(name="work", description="Travaille pour gagner des Berrys.")
    async def work(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild_id
        user = await db.get_user(user_id, guild_id)
        equipped_fruits, fruit_levels = await get_equipped_fruits_and_levels(user_id, guild_id)

        reduction = get_fruits_effect_value(equipped_fruits, "cooldown_reduction", fruit_levels)
        effective_cooldown = config.WORK_COOLDOWN * (1 - reduction)

        remaining = db.get_cooldown_remaining(user["last_work"], effective_cooldown)
        if remaining > 0:
            embed = discord.Embed(
                title="⏳ Repose-toi encore un peu",
                description=(
                    f"Tu es épuisé. Reviens dans **{format_duration(remaining)}** "
                    f"pour retravailler."
                ),
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        amount = random.randint(config.WORK_MIN, config.WORK_MAX)

        # Effet Gomu Gomu no Mi (et autres fruits work_boost) : cumul possible avec le passif
        work_boost = get_fruits_effect_value(equipped_fruits, "work_boost", fruit_levels)
        if work_boost:
            amount = int(amount * (1 + work_boost))

        await db.update_wallet(user_id, guild_id, amount)
        await db.set_cooldown(user_id, guild_id, "last_work")

        message = random.choice(config.WORK_MESSAGES).format(
            amount=format_berrys(amount), symbol=""
        )

        embed = discord.Embed(
            title="⚒️ Travail terminé",
            description=message,
            color=config.COLOR_SUCCESS,
        )
        if work_boost:
            embed.set_footer(text=f"🔴 Bonus de fruit(s) appliqué : +{int(work_boost * 100)}%")

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /crime et /pillage (alias, même logique)
    # ------------------------------------------------------------------
    async def _do_crime(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild_id
        user = await db.get_user(user_id, guild_id)
        equipped_fruits, fruit_levels = await get_equipped_fruits_and_levels(user_id, guild_id)

        reduction = min(get_fruits_effect_value(equipped_fruits, "cooldown_reduction", fruit_levels), 0.9)
        effective_cooldown = config.CRIME_COOLDOWN * (1 - reduction)

        remaining = db.get_cooldown_remaining(user["last_crime"], effective_cooldown)
        if remaining > 0:
            embed = discord.Embed(
                title="⏳ La Marine est sur ses gardes",
                description=(
                    f"Trop risqué pour l'instant. Retente ta chance dans "
                    f"**{format_duration(remaining)}**."
                ),
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.set_cooldown(user_id, guild_id, "last_crime")

        # Chance de se faire attraper, réduite par le Yami Yami no Mi (et autres, cumulables)
        fine_reduction = min(get_fruits_effect_value(equipped_fruits, "crime_fine_reduction", fruit_levels), 1.0)
        catch_chance = (1 - config.CRIME_SUCCESS_RATE) * (1 - fine_reduction)

        if random.random() < catch_chance:
            # Échec : amende de la Marine
            fine = random.randint(config.CRIME_FINE_MIN, config.CRIME_FINE_MAX)
            new_wallet = await db.update_wallet(user_id, guild_id, -fine)
            message = random.choice(config.CRIME_FAIL_MESSAGES).format(
                fine=format_berrys(fine), symbol=""
            )
            embed = discord.Embed(
                title="🚨 Capturé par la Marine !",
                description=message,
                color=config.COLOR_ERROR,
            )
            embed.set_footer(text=f"Nouveau solde : {format_berrys(new_wallet)}")
            if fine_reduction:
                embed.add_field(
                    name="🌑 Bonus de fruit(s)",
                    value=f"A réduit tes risques de {int(fine_reduction * 100)}% (pas assez cette fois...)",
                    inline=False,
                )
            await interaction.response.send_message(embed=embed)
            return

        # Réussite : butin
        amount = random.randint(config.CRIME_MIN, config.CRIME_MAX)
        crime_boost = get_fruits_effect_value(equipped_fruits, "crime_boost", fruit_levels)
        if crime_boost:
            amount = int(amount * (1 + crime_boost))

        await db.update_wallet(user_id, guild_id, amount)
        # La prime augmente avec les méfaits (moitié du butin)
        await db.update_bounty(user_id, guild_id, amount // 2)

        message = random.choice(config.CRIME_SUCCESS_MESSAGES).format(
            amount=format_berrys(amount), symbol=""
        )
        embed = discord.Embed(
            title="🏴‍☠️ Coup réussi !",
            description=message,
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="📈 Prime", value=f"+{format_berrys(amount // 2)}", inline=True)
        if crime_boost:
            embed.set_footer(text="💥 Bonus Gura Gura no Mi appliqué (+30% de butin)")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="crime", description="Tente un coup risqué pour gagner beaucoup de Berrys.")
    async def crime(self, interaction: discord.Interaction):
        await self._do_crime(interaction)

    @app_commands.command(name="pillage", description="Alias de /crime : tente un coup risqué pour gagner des Berrys.")
    async def pillage(self, interaction: discord.Interaction):
        await self._do_crime(interaction)

    # ------------------------------------------------------------------
    # /balance et /solde (alias)
    # ------------------------------------------------------------------
    async def _do_balance(self, interaction: discord.Interaction, member: discord.Member | None):
        target = member or interaction.user
        user = await db.get_user(target.id, interaction.guild_id)

        embed = discord.Embed(
            title=f"💰 Portefeuille de {target.display_name}",
            description=f"**{format_berrys(user['wallet'])}**",
            color=config.COLOR_ECONOMY,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="balance", description="Affiche ton solde en Berrys (ou celui d'un autre pirate).")
    @app_commands.describe(member="Le membre dont tu veux voir le solde (optionnel)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member | None = None):
        await self._do_balance(interaction, member)

    @app_commands.command(name="solde", description="Affiche ton solde en Berrys (ou celui d'un autre pirate).")
    @app_commands.describe(member="Le membre dont tu veux voir le solde (optionnel)")
    async def solde(self, interaction: discord.Interaction, member: discord.Member | None = None):
        await self._do_balance(interaction, member)

    # ------------------------------------------------------------------
    # /profile
    # ------------------------------------------------------------------
    @app_commands.command(name="profile", description="Affiche ton profil de pirate complet.")
    @app_commands.describe(member="Le membre dont tu veux voir le profil (optionnel)")
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None):
        target = member or interaction.user
        user = await db.get_user(target.id, interaction.guild_id)

        equipped_fruits, fruit_levels = await get_equipped_fruits_and_levels(target.id, interaction.guild_id)
        has_passive = await db.has_multi_fruit_passive(target.id, interaction.guild_id)

        if not equipped_fruits:
            fruit_text = "Aucun fruit équipé — un simple humain (pour l'instant)."
        else:
            lines = []
            for fruit_id in equipped_fruits:
                fruit = FRUITS.get(fruit_id)
                if not fruit:
                    continue
                level = fruit_levels.get(fruit_id, 1)
                stars = "⭐" * level
                lines.append(
                    f"{fruit['emoji']} **{fruit['name']}** ({fruit['type']}) — Niveau {level} {stars}\n"
                    f"_{fruit['bonus_text']}_"
                )
            fruit_text = "\n\n".join(lines)
            if has_passive:
                fruit_text += "\n\n🖤 **Passif Barbe Noire actif** — tous ces bonus se cumulent !"

        title = get_bounty_title(user["bounty"])
        fleet = get_member_fleet(target)
        fleet_and_title = f"{fleet} | {title}" if fleet else title

        await interaction.response.defer()  # la génération de l'affiche prend un instant

        poster_file = await generate_wanted_poster(
            member=target,
            fleet_and_title=fleet_and_title,
            bounty=user["bounty"],
        )

        embed = discord.Embed(
            title=f"🏴‍☠️ Profil de {target.display_name}",
            description=f"**{fleet_and_title}**",
            color=config.COLOR_ECONOMY,
        )
        embed.add_field(name="💰 Portefeuille", value=format_berrys(user["wallet"]), inline=True)
        embed.add_field(name="📜 Prime (Bounty)", value=format_berrys(user["bounty"]), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # espaceur
        embed.add_field(name="🍈 Fruit du Démon", value=fruit_text, inline=False)
        embed.set_image(url="attachment://wanted_poster.png")
        embed.set_footer(text="Que le Grand Line te soit favorable !")

        await interaction.followup.send(embed=embed, file=poster_file)

    # ------------------------------------------------------------------
    # /reset
    # ------------------------------------------------------------------
    @app_commands.command(name="reset", description="Recommence entièrement à zéro (solde, prime, fruits, cooldowns).")
    async def reset(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild_id

        confirm_embed = discord.Embed(
            title="⚠️ Confirmation requise",
            description=(
                "Es-tu sûr de vouloir **tout recommencer à zéro** sur ce serveur ?\n\n"
                "Cette action va :\n"
                f"• Remettre ton portefeuille à **{format_berrys(config.STARTING_WALLET)}**\n"
                "• Remettre ta prime à **0฿**\n"
                "• Déséquiper et **supprimer tous tes Fruits du Démon**\n"
                "• Réinitialiser tous tes cooldowns (`/daily`, `/work`, `/crime`)\n\n"
                "**⛔ Cette action est irréversible !**"
            ),
            color=config.COLOR_ERROR,
        )
        view = ResetConfirmView(author_id=user_id)
        await interaction.response.send_message(embed=confirm_embed, view=view, ephemeral=True)
        await view.wait()

        if view.confirmed:
            await db.reset_user(user_id, guild_id)
            result_embed = discord.Embed(
                title="🔄 Nouveau départ !",
                description=(
                    f"Tes données ont été réinitialisées. Tu repars avec "
                    f"**{format_berrys(config.STARTING_WALLET)}**, tel un moussaillon "
                    f"fraîchement débarqué sur le Grand Line."
                ),
                color=config.COLOR_SUCCESS,
            )
            await interaction.edit_original_response(embed=result_embed, view=None)
        elif view.confirmed is False:
            cancel_embed = discord.Embed(
                title="❌ Réinitialisation annulée",
                description="Tes données n'ont pas été touchées.",
                color=config.COLOR_MARINE,
            )
            await interaction.edit_original_response(embed=cancel_embed, view=None)
        else:
            timeout_embed = discord.Embed(
                title="⏳ Temps écoulé",
                description="Pas de réponse à temps : réinitialisation annulée par sécurité.",
                color=config.COLOR_MARINE,
            )
            await interaction.edit_original_response(embed=timeout_embed, view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
