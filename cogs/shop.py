"""
cogs/shop.py
-------------
Gestion de la boutique de Fruits du Démon : consultation, achat,
inventaire, équipement/déséquipement, et le passif spécial Barbe Noire
qui permet d'équiper plusieurs fruits à la fois.
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from data.fruits import FRUITS
from utils.helpers import format_berrys


async def fruit_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplétion générique pour /buy et /eat (tous les fruits du jeu)."""
    choices = [
        app_commands.Choice(name=f"{fruit['emoji']} {fruit['name']}", value=fruit_id)
        for fruit_id, fruit in FRUITS.items()
        if current.lower() in fruit["name"].lower()
    ]
    return choices[:25]


async def equipped_fruit_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplétion pour /unequip : ne propose que les fruits actuellement équipés."""
    equipped_ids = await db.get_equipped_fruits(interaction.user.id, interaction.guild_id)
    choices = []
    for fruit_id in equipped_ids:
        fruit = FRUITS.get(fruit_id)
        if fruit and current.lower() in fruit["name"].lower():
            choices.append(app_commands.Choice(name=f"{fruit['emoji']} {fruit['name']}", value=fruit_id))
    return choices[:25]


class Shop(commands.Cog):
    """Commandes liées à la boutique, aux Fruits du Démon et au passif Barbe Noire."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /shop
    # ------------------------------------------------------------------
    @app_commands.command(name="shop", description="Affiche la boutique des Fruits du Démon.")
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🍈 Boutique des Fruits du Démon",
            description=(
                "Utilise `/buy <fruit>` pour acheter un fruit, puis `/eat <fruit>` "
                "pour l'équiper. **Un seul fruit actif à la fois**, sauf passif spécial ⬇️"
            ),
            color=config.COLOR_SHOP,
        )

        for fruit in FRUITS.values():
            embed.add_field(
                name=f"{fruit['emoji']} {fruit['name']} — {format_berrys(fruit['price'])}",
                value=f"_{fruit['description']}_\n✨ {fruit['bonus_text']}",
                inline=False,
            )

        embed.add_field(
            name=f"🖤 Passif Barbe Noire — {format_berrys(config.BARBE_NOIRE_PRICE)}",
            value=(
                "Débloque la capacité unique d'équiper **autant de Fruits du Démon "
                "que tu veux en même temps** — tous leurs bonus s'additionnent sans "
                "limite. Utilise `/barbenoire` pour l'acheter (achat définitif)."
            ),
            inline=False,
        )

        embed.add_field(
            name="🛒 Boutique personnalisée du serveur",
            value="Utilise `/custom-shop` pour voir les objets ajoutés par les administrateurs de ce serveur.",
            inline=False,
        )

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /buy
    # ------------------------------------------------------------------
    @app_commands.command(name="buy", description="Achète un Fruit du Démon dans la boutique.")
    @app_commands.describe(fruit="Le fruit que tu veux acheter")
    @app_commands.autocomplete(fruit=fruit_autocomplete)
    async def buy(self, interaction: discord.Interaction, fruit: str):
        fruit_data = FRUITS.get(fruit)
        if fruit_data is None:
            embed = discord.Embed(
                title="❌ Fruit inconnu",
                description="Ce fruit n'existe pas. Utilise `/shop` pour voir la liste.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_id, guild_id = interaction.user.id, interaction.guild_id

        if await db.has_fruit(user_id, guild_id, fruit):
            embed = discord.Embed(
                title="🤔 Déjà en ta possession",
                description=f"Tu possèdes déjà le **{fruit_data['name']}** !",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user = await db.get_user(user_id, guild_id)
        if user["wallet"] < fruit_data["price"]:
            embed = discord.Embed(
                title="💸 Fonds insuffisants",
                description=(
                    f"Le **{fruit_data['name']}** coûte {format_berrys(fruit_data['price'])}, "
                    f"mais tu n'as que {format_berrys(user['wallet'])}."
                ),
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.update_wallet(user_id, guild_id, -fruit_data["price"])
        await db.add_fruit_to_inventory(user_id, guild_id, fruit)

        embed = discord.Embed(
            title="✅ Achat réussi !",
            description=(
                f"Tu as acheté le {fruit_data['emoji']} **{fruit_data['name']}** pour "
                f"{format_berrys(fruit_data['price'])} !\n\n"
                f"Utilise `/eat {fruit_data['name']}` pour l'équiper."
            ),
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /inventory
    # ------------------------------------------------------------------
    @app_commands.command(name="inventory", description="Affiche les Fruits du Démon que tu possèdes.")
    async def inventory(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild_id
        owned_ids = await db.get_inventory(user_id, guild_id)
        equipped_ids = set(await db.get_equipped_fruits(user_id, guild_id))

        if not owned_ids:
            embed = discord.Embed(
                title="🎒 Inventaire vide",
                description="Tu ne possèdes aucun Fruit du Démon. Rends-toi sur `/shop` !",
                color=config.COLOR_SHOP,
            )
            await interaction.response.send_message(embed=embed)
            return

        lines = []
        for fruit_id in owned_ids:
            fruit = FRUITS.get(fruit_id)
            if not fruit:
                continue
            level = await db.get_fruit_level(user_id, guild_id, fruit_id)
            marker = " ✅ **(équipé)**" if fruit_id in equipped_ids else ""
            lines.append(
                f"{fruit['emoji']} **{fruit['name']}** — Niveau {level}{marker}\n_{fruit['bonus_text']}_"
            )

        embed = discord.Embed(
            title=f"🎒 Inventaire de {interaction.user.display_name}",
            description="\n\n".join(lines),
            color=config.COLOR_SHOP,
        )
        if await db.has_multi_fruit_passive(user_id, guild_id):
            embed.set_footer(text="🖤 Passif Barbe Noire actif : équipe autant de fruits que tu veux avec /eat")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /eat
    # ------------------------------------------------------------------
    @app_commands.command(name="eat", description="Mange (équipe) un Fruit du Démon de ton inventaire.")
    @app_commands.describe(fruit="Le fruit que tu veux équiper")
    @app_commands.autocomplete(fruit=fruit_autocomplete)
    async def eat(self, interaction: discord.Interaction, fruit: str):
        fruit_data = FRUITS.get(fruit)
        if fruit_data is None:
            embed = discord.Embed(
                title="❌ Fruit inconnu",
                description="Ce fruit n'existe pas. Utilise `/shop` pour voir la liste.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_id, guild_id = interaction.user.id, interaction.guild_id

        if not await db.has_fruit(user_id, guild_id, fruit):
            embed = discord.Embed(
                title="❌ Tu ne possèdes pas ce fruit",
                description=f"Achète-le d'abord avec `/buy {fruit_data['name']}`.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        currently_equipped = await db.get_equipped_fruits(user_id, guild_id)
        if fruit in currently_equipped:
            embed = discord.Embed(
                title="🤔 Déjà équipé",
                description=f"Le **{fruit_data['name']}** est déjà actif !",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        has_passive = await db.has_multi_fruit_passive(user_id, guild_id)
        await db.equip_fruit(user_id, guild_id, fruit)

        if has_passive:
            description = (
                f"Tu as mangé le {fruit_data['emoji']} **{fruit_data['name']}** !\n"
                f"✨ Effet actif : {fruit_data['bonus_text']}\n\n"
                f"🖤 Grâce au passif Barbe Noire, tes autres fruits restent actifs "
                f"— tous leurs bonus se cumulent désormais !"
            )
        else:
            warning = ""
            if currently_equipped:
                old_fruit = FRUITS.get(currently_equipped[0])
                old_name = old_fruit["name"] if old_fruit else currently_equipped[0]
                warning = f"\n⚠️ Ton ancien pouvoir (**{old_name}**) s'est désactivé — on ne mange pas deux fruits impunément (sauf avec `/barbenoire`) !"
            description = (
                f"Tu as mangé le {fruit_data['emoji']} **{fruit_data['name']}** !\n"
                f"✨ Effet actif : {fruit_data['bonus_text']}"
                f"{warning}"
            )

        embed = discord.Embed(title="🍈 Fruit du Démon dévoré !", description=description, color=config.COLOR_SUCCESS)
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /unequip
    # ------------------------------------------------------------------
    @app_commands.command(name="unequip", description="Déséquipe un Fruit du Démon (ou tous, si aucun n'est précisé).")
    @app_commands.describe(fruit="Le fruit à déséquiper (laisse vide pour tout déséquiper)")
    @app_commands.autocomplete(fruit=equipped_fruit_autocomplete)
    async def unequip(self, interaction: discord.Interaction, fruit: str | None = None):
        user_id, guild_id = interaction.user.id, interaction.guild_id
        equipped_ids = await db.get_equipped_fruits(user_id, guild_id)

        if not equipped_ids:
            embed = discord.Embed(
                title="🤔 Aucun fruit équipé",
                description="Tu n'as actuellement aucun Fruit du Démon actif.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if fruit is not None and fruit not in equipped_ids:
            embed = discord.Embed(
                title="❌ Ce fruit n'est pas équipé",
                description="Utilise `/inventory` pour voir tes fruits actuellement actifs.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.unequip_fruit(user_id, guild_id, fruit)

        if fruit is not None:
            fruit_data = FRUITS.get(fruit)
            fruit_name = fruit_data["name"] if fruit_data else fruit
            fruit_emoji = fruit_data["emoji"] if fruit_data else "🍈"
            description = (
                f"Tu as déséquipé le {fruit_emoji} **{fruit_name}**. Ses effets ne "
                f"s'appliquent plus, mais il reste dans ton `/inventory`."
            )
        else:
            names = ", ".join(FRUITS[f]["name"] for f in equipped_ids if f in FRUITS)
            description = f"Tu as tout déséquipé ({names}). Utilise `/eat` pour réactiver un fruit quand tu veux."

        embed = discord.Embed(title="🫙 Fruit(s) déséquipé(s)", description=description, color=config.COLOR_SUCCESS)
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /barbenoire
    # ------------------------------------------------------------------
    @app_commands.command(
        name="barbenoire",
        description=f"Débloque le passif Barbe Noire ({format_berrys(config.BARBE_NOIRE_PRICE)}) : équipe des fruits en illimité.",
    )
    async def barbenoire(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild_id

        if await db.has_multi_fruit_passive(user_id, guild_id):
            embed = discord.Embed(
                title="🖤 Déjà débloqué",
                description="Tu possèdes déjà le passif Barbe Noire — équipe autant de fruits que tu veux avec `/eat` !",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user = await db.get_user(user_id, guild_id)
        if user["wallet"] < config.BARBE_NOIRE_PRICE:
            embed = discord.Embed(
                title="💸 Fonds largement insuffisants",
                description=(
                    f"Le passif Barbe Noire coûte **{format_berrys(config.BARBE_NOIRE_PRICE)}** — "
                    f"un prix à la hauteur de son pouvoir. Tu n'as que {format_berrys(user['wallet'])}."
                ),
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.update_wallet(user_id, guild_id, -config.BARBE_NOIRE_PRICE)
        await db.unlock_multi_fruit_passive(user_id, guild_id)

        embed = discord.Embed(
            title="🖤 Le pouvoir de Barbe Noire est tien !",
            description=(
                "Ton corps peut désormais absorber plusieurs Fruits du Démon sans "
                "en mourir, comme le tristement célèbre Marshall D. Teach.\n\n"
                f"Coût : **{format_berrys(config.BARBE_NOIRE_PRICE)}**\n\n"
                "À partir de maintenant, `/eat` **ajoute** un fruit à tes pouvoirs "
                "actifs au lieu de remplacer l'ancien — tous leurs bonus se cumulent, "
                "sans limite."
            ),
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
