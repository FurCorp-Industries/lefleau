"""
cogs/quests.py
-----------------
Système de progression à long terme : les quêtes rapportent des Berrys et
des matériaux, utilisés ensuite pour améliorer (/enhance) les Fruits du
Démon équipés et ainsi augmenter durablement leurs effets.
"""

import random

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from data.fruits import FRUITS
from data.materials import MATERIALS, roll_material
from data.quests import QUESTS
from utils.helpers import format_berrys, format_duration


async def owned_fruit_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplétion pour /enhance : ne propose que les fruits possédés par le joueur."""
    owned_ids = await db.get_inventory(interaction.user.id, interaction.guild_id)
    choices = []
    for fruit_id in owned_ids:
        fruit = FRUITS.get(fruit_id)
        if fruit and current.lower() in fruit["name"].lower():
            choices.append(app_commands.Choice(name=f"{fruit['emoji']} {fruit['name']}", value=fruit_id))
    return choices[:25]


class Quests(commands.Cog):
    """Commandes de quêtes, matériaux et amélioration de fruits."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /quest
    # ------------------------------------------------------------------
    @app_commands.command(name="quest", description="Pars en mission pour gagner des Berrys et des matériaux.")
    async def quest(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild_id
        user = await db.get_user(user_id, guild_id)

        remaining = db.get_cooldown_remaining(user.get("last_quest"), config.QUEST_COOLDOWN)
        if remaining > 0:
            embed = discord.Embed(
                title="⏳ Aucune mission disponible pour l'instant",
                description=f"Reviens dans **{format_duration(remaining)}** pour une nouvelle quête.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.set_cooldown(user_id, guild_id, "last_quest")

        quest = random.choice(QUESTS)
        amount = random.randint(config.QUEST_MIN, config.QUEST_MAX)
        await db.update_wallet(user_id, guild_id, amount)

        description = f"**{quest['name']}**\n_{quest['description']}_\n\n💰 Récompense : {format_berrys(amount)}"

        material_line = ""
        if random.random() < config.QUEST_MATERIAL_CHANCE:
            material_id = roll_material()
            material = MATERIALS[material_id]
            await db.add_material(user_id, guild_id, material_id, 1)
            material_line = f"\n{material['emoji']} Matériau trouvé : **{material['name']}** ({material['rarity']})"

        embed = discord.Embed(
            title="🗺️ Quête terminée !",
            description=description + material_line,
            color=config.COLOR_SUCCESS,
        )
        embed.set_footer(text="Utilise /materials pour voir ce que tu as accumulé.")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /materials
    # ------------------------------------------------------------------
    @app_commands.command(name="materials", description="Affiche les matériaux que tu as accumulés via les quêtes.")
    async def materials(self, interaction: discord.Interaction):
        owned = await db.get_materials(interaction.user.id, interaction.guild_id)

        if not owned:
            embed = discord.Embed(
                title="🎒 Aucun matériau",
                description="Tu n'as encore aucun matériau. Utilise `/quest` pour en trouver !",
                color=config.COLOR_SHOP,
            )
            await interaction.response.send_message(embed=embed)
            return

        lines = []
        for material_id, qty in owned.items():
            material = MATERIALS.get(material_id)
            if not material:
                continue
            lines.append(f"{material['emoji']} **{material['name']}** ({material['rarity']}) — x{qty}")

        embed = discord.Embed(
            title=f"🎒 Matériaux de {interaction.user.display_name}",
            description="\n".join(lines),
            color=config.COLOR_SHOP,
        )
        embed.set_footer(text="Utilise /enhance pour améliorer un Fruit du Démon avec ces matériaux.")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /enhance
    # ------------------------------------------------------------------
    @app_commands.command(name="enhance", description="Améliore un Fruit du Démon possédé avec des matériaux.")
    @app_commands.describe(fruit="Le fruit à améliorer")
    @app_commands.autocomplete(fruit=owned_fruit_autocomplete)
    async def enhance(self, interaction: discord.Interaction, fruit: str):
        user_id, guild_id = interaction.user.id, interaction.guild_id
        fruit_data = FRUITS.get(fruit)

        if fruit_data is None or not await db.has_fruit(user_id, guild_id, fruit):
            embed = discord.Embed(
                title="❌ Fruit introuvable",
                description="Tu ne possèdes pas ce fruit. Utilise `/inventory` pour voir les tiens.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        current_level = await db.get_fruit_level(user_id, guild_id, fruit)

        if current_level >= config.MAX_FRUIT_LEVEL:
            embed = discord.Embed(
                title="✨ Niveau maximum atteint",
                description=f"Le **{fruit_data['name']}** est déjà au niveau maximum ({config.MAX_FRUIT_LEVEL}).",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        next_level = current_level + 1
        requirement = config.FRUIT_UPGRADE_REQUIREMENTS[next_level]
        berrys_cost = requirement["berrys"]
        materials_cost = requirement["materials"]

        user = await db.get_user(user_id, guild_id)
        owned_materials = await db.get_materials(user_id, guild_id)

        missing = []
        if user["wallet"] < berrys_cost:
            missing.append(f"💰 {format_berrys(berrys_cost)} requis (tu as {format_berrys(user['wallet'])})")
        for material_id, qty in materials_cost.items():
            owned_qty = owned_materials.get(material_id, 0)
            if owned_qty < qty:
                material = MATERIALS[material_id]
                missing.append(f"{material['emoji']} {material['name']} x{qty} requis (tu as x{owned_qty})")

        if missing:
            embed = discord.Embed(
                title="❌ Ressources insuffisantes",
                description=(
                    f"Améliorer le **{fruit_data['name']}** au niveau {next_level} nécessite :\n\n"
                    + "\n".join(missing)
                ),
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.update_wallet(user_id, guild_id, -berrys_cost)
        await db.spend_materials(user_id, guild_id, materials_cost)
        await db.set_fruit_level(user_id, guild_id, fruit, next_level)

        materials_text = ", ".join(f"{MATERIALS[m]['emoji']} x{q}" for m, q in materials_cost.items())

        embed = discord.Embed(
            title="✨ Fruit amélioré !",
            description=(
                f"Le **{fruit_data['name']}** passe au niveau **{next_level}** "
                f"({'⭐' * next_level}) !\n\n"
                f"Coût : {format_berrys(berrys_cost)} + {materials_text}\n\n"
                f"Ses effets sont maintenant **{int(config.FRUIT_LEVEL_BONUS * (next_level - 1) * 100)}% plus puissants** "
                f"que la version de base."
            ),
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Quests(bot))
