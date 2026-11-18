"""Boutique d'objets personnalisés, indépendante pour chaque serveur Discord."""

import math

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils.helpers import format_berrys


ITEMS_PER_PAGE = 10


async def active_item_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild_id is None:
        return []
    needle = current.casefold()
    items = await db.get_custom_items(interaction.guild_id)
    return [
        app_commands.Choice(name=f"{item['emoji']} {item['name']}"[:100], value=item["name"])
        for item in items
        if needle in item["name"].casefold()
    ][:25]


class CustomShop(commands.Cog):
    """Catalogue et inventaire d'objets propres à chaque serveur."""

    boutique = app_commands.Group(name="custom-shop", description="Boutique personnalisée du serveur", guild_only=True)

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _page(items: list[dict], page: int) -> tuple[list[dict], int, int]:
        page_count = max(1, math.ceil(len(items) / ITEMS_PER_PAGE))
        current_page = min(page, page_count)
        start = (current_page - 1) * ITEMS_PER_PAGE
        return items[start:start + ITEMS_PER_PAGE], current_page, page_count

    @boutique.command(
        name="item-add",
        description="[Admin] Ajoute, modifie ou réactive un objet propre à ce serveur.",
    )
    @app_commands.describe(
        nom="Nom unique de l'objet (50 caractères maximum)",
        prix="Prix unitaire en Berrys",
        description="Description de l'objet (300 caractères maximum)",
        emoji="Emoji affiché devant l'objet (📦 par défaut)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def custom_item_add(
        self,
        interaction: discord.Interaction,
        nom: str,
        prix: app_commands.Range[int, 1, 1_000_000_000],
        description: str,
        emoji: str = "📦",
    ):
        nom = " ".join(nom.split())
        description = description.strip()
        emoji = emoji.strip() or "📦"
        if not nom or len(nom) > 50:
            await interaction.response.send_message(
                "❌ Le nom doit contenir entre 1 et 50 caractères.", ephemeral=True
            )
            return
        if not description or len(description) > 300:
            await interaction.response.send_message(
                "❌ La description doit contenir entre 1 et 300 caractères.", ephemeral=True
            )
            return
        if len(emoji) > 32:
            await interaction.response.send_message(
                "❌ L'emoji est trop long.", ephemeral=True
            )
            return

        previous = await db.get_custom_item(interaction.guild_id, nom, include_inactive=True)
        item = await db.upsert_custom_item(
            interaction.guild_id,
            nom,
            description,
            prix,
            emoji,
            interaction.user.id,
        )
        action = "mis à jour et réactivé" if previous else "ajouté"
        embed = discord.Embed(
            title=f"✅ Objet {action}",
            description=f"{item['emoji']} **{item['name']}**\n{item['description']}",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="Prix", value=format_berrys(item["price"]))
        embed.set_footer(text="Visible immédiatement dans /custom-shop")
        await interaction.response.send_message(embed=embed)

    @boutique.command(
        name="item-remove",
        description="[Admin] Retire un objet de la boutique de ce serveur.",
    )
    @app_commands.describe(objet="Objet à retirer de la vente")
    @app_commands.autocomplete(objet=active_item_autocomplete)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def custom_item_remove(self, interaction: discord.Interaction, objet: str):
        removed = await db.disable_custom_item(interaction.guild_id, objet)
        if not removed:
            await interaction.response.send_message(
                "❌ Cet objet n'existe pas ou a déjà été retiré.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"✅ **{objet}** a été retiré de la boutique. Les exemplaires déjà achetés restent dans les inventaires."
        )

    @boutique.command(
        name="item-list",
        description="[Admin] Affiche les objets configurés sur ce serveur.",
    )
    @app_commands.describe(
        inclure_desactives="Inclure les objets qui ne sont plus vendus",
        page="Numéro de la page à afficher",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def custom_item_list(
        self,
        interaction: discord.Interaction,
        inclure_desactives: bool = False,
        page: app_commands.Range[int, 1, 1000] = 1,
    ):
        items = await db.get_custom_items(interaction.guild_id, inclure_desactives)
        if not items:
            await interaction.response.send_message(
                "Aucun objet personnalisé n'est configuré sur ce serveur.", ephemeral=True
            )
            return
        shown, current_page, page_count = self._page(items, page)
        lines = []
        for item in shown:
            status = "🟢 En vente" if item["active"] else "🔴 Désactivé"
            lines.append(
                f"{item['emoji']} **{item['name']}** — {format_berrys(item['price'])}\n"
                f"{status} · {item['description']}"
            )
        embed = discord.Embed(
            title="⚙️ Objets personnalisés du serveur",
            description="\n\n".join(lines),
            color=config.COLOR_SHOP,
        )
        embed.set_footer(text=f"Page {current_page}/{page_count} · {len(items)} objet(s)")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @boutique.command(
        name="shop",
        description="Affiche la boutique d'objets personnalisés de ce serveur.",
    )
    @app_commands.describe(page="Numéro de la page à afficher")
    @app_commands.guild_only()
    async def custom_shop(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1, 1000] = 1,
    ):
        items = await db.get_custom_items(interaction.guild_id)
        if not items:
            await interaction.response.send_message(
                "🛒 Ce serveur ne propose actuellement aucun objet personnalisé.",
                ephemeral=True,
            )
            return
        shown, current_page, page_count = self._page(items, page)
        lines = [
            f"{item['emoji']} **{item['name']}** — {format_berrys(item['price'])}\n_{item['description']}_"
            for item in shown
        ]
        embed = discord.Embed(
            title=f"🛒 Boutique de {interaction.guild.name}",
            description="\n\n".join(lines),
            color=config.COLOR_SHOP,
        )
        embed.set_footer(
            text=f"Page {current_page}/{page_count} · Achat avec /custom-buy"
        )
        await interaction.response.send_message(embed=embed)

    @boutique.command(
        name="buy",
        description="Achète un objet personnalisé proposé par ce serveur.",
    )
    @app_commands.describe(objet="Objet à acheter", quantite="Nombre d'exemplaires")
    @app_commands.autocomplete(objet=active_item_autocomplete)
    @app_commands.guild_only()
    async def custom_buy(
        self,
        interaction: discord.Interaction,
        objet: str,
        quantite: app_commands.Range[int, 1, 99] = 1,
    ):
        result = await db.purchase_custom_item(
            interaction.user.id, interaction.guild_id, objet, quantite
        )
        if result["status"] == "not_found":
            await interaction.response.send_message(
                "❌ Cet objet n'existe pas ou n'est plus en vente.", ephemeral=True
            )
            return
        if result["status"] == "insufficient_funds":
            await interaction.response.send_message(
                f"💸 Il faut {format_berrys(result['total'])}, mais tu ne possèdes que "
                f"{format_berrys(result['wallet'])}.",
                ephemeral=True,
            )
            return

        item = result["item"]
        embed = discord.Embed(
            title="✅ Achat réussi",
            description=(
                f"Tu as acheté **{quantite}× {item['emoji']} {item['name']}** pour "
                f"{format_berrys(result['total'])}."
            ),
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="Quantité possédée", value=str(result["quantity_owned"]))
        embed.add_field(name="Nouveau solde", value=format_berrys(result["wallet"]))
        await interaction.response.send_message(embed=embed)

    @boutique.command(
        name="inventory",
        description="Affiche les objets personnalisés possédés par un membre.",
    )
    @app_commands.describe(membre="Membre à consulter", page="Numéro de la page")
    @app_commands.guild_only()
    async def custom_inventory(
        self,
        interaction: discord.Interaction,
        membre: discord.Member | None = None,
        page: app_commands.Range[int, 1, 1000] = 1,
    ):
        target = membre or interaction.user
        items = await db.get_custom_inventory(target.id, interaction.guild_id)
        if not items:
            await interaction.response.send_message(
                f"🎒 {target.display_name} ne possède aucun objet personnalisé.",
                ephemeral=target.id == interaction.user.id,
            )
            return
        shown, current_page, page_count = self._page(items, page)
        lines = []
        for item in shown:
            unavailable = " · _plus en vente_" if not item["active"] else ""
            lines.append(
                f"{item['emoji']} **{item['name']}** × **{item['quantity']}**{unavailable}\n"
                f"_{item['description']}_"
            )
        embed = discord.Embed(
            title=f"🎒 Objets de {target.display_name}",
            description="\n\n".join(lines),
            color=config.COLOR_SHOP,
        )
        embed.set_footer(text=f"Page {current_page}/{page_count}")
        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            message = "🚫 Tu dois avoir la permission **Gérer le serveur** pour utiliser cette commande."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return
        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomShop(bot))
