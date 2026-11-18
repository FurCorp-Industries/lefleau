"""
cogs/bloxfruits.py
---------------------
Petit système indépendant de l'économie du bot : permet aux membres de
renseigner leur bounty et leur équipement précis (fruit, épée, arme à
feu, style de combat) sur le jeu Roblox "Blox Fruits", et de les
consulter. Utilise l'autocomplétion plutôt qu'un menu figé, car le jeu
compte largement plus de 25 objets par catégorie (limite d'un menu
déroulant Discord) et reçoit des mises à jour fréquentes.
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from data.bloxfruits_items import FRUITS_LIST, SWORDS_LIST, GUNS_LIST, FIGHTING_STYLES_LIST


def _make_autocomplete(items: list[str]):
    """Fabrique une fonction d'autocomplétion filtrant une liste statique selon le texte tapé."""

    async def autocomplete(interaction: discord.Interaction, current: str):
        current = current.lower()
        matches = [item for item in items if current in item.lower()]
        return [app_commands.Choice(name=item, value=item) for item in matches[:25]]

    return autocomplete


fruit_autocomplete = _make_autocomplete(FRUITS_LIST)
sword_autocomplete = _make_autocomplete(SWORDS_LIST)
gun_autocomplete = _make_autocomplete(GUNS_LIST)
style_autocomplete = _make_autocomplete(FIGHTING_STYLES_LIST)


class BloxFruits(commands.Cog):
    """Commandes pour le profil Blox Fruits (bounty + fruit + épée + arme + style)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /bloxfruits — renseigner son propre profil
    # ------------------------------------------------------------------
    @app_commands.command(name="bloxfruits", description="Renseigne ton bounty et ton équipement sur Blox Fruits.")
    @app_commands.describe(
        bounty="Ton bounty actuel (ex: 500M, 1.2B, 999T, ou le nombre exact)",
        fruit="Ton Fruit du Démon (optionnel)",
        sword="Ton épée (optionnel)",
        gun="Ton arme à feu (optionnelle)",
        style="Ton style de combat / mêlée (optionnel)",
    )
    @app_commands.autocomplete(fruit=fruit_autocomplete, sword=sword_autocomplete, gun=gun_autocomplete, style=style_autocomplete)
    async def bloxfruits(
        self,
        interaction: discord.Interaction,
        bounty: str,
        fruit: str | None = None,
        sword: str | None = None,
        gun: str | None = None,
        style: str | None = None,
    ):
        bounty_clean = bounty.strip()[:50]
        if not bounty_clean:
            embed = discord.Embed(
                title="❌ Bounty invalide",
                description="Donne un bounty non vide (ex: `500M`, `1.2B`, `999,000,000`).",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not any([fruit, sword, gun, style]):
            embed = discord.Embed(
                title="🤔 Renseigne au moins un équipement",
                description="Précise au moins ton fruit, ton épée, ton arme, ou ton style de combat.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.set_bloxfruits_profile(
            interaction.user.id, interaction.guild_id,
            bounty=bounty_clean, fruit=fruit, sword=sword, gun=gun, fighting_style=style,
        )

        embed = discord.Embed(
            title="✅ Profil Blox Fruits mis à jour",
            description=f"C'est enregistré, {interaction.user.mention} !",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="💰 Bounty", value=bounty_clean, inline=False)
        if fruit:
            embed.add_field(name="🍈 Fruit", value=fruit, inline=True)
        if sword:
            embed.add_field(name="⚔️ Épée", value=sword, inline=True)
        if gun:
            embed.add_field(name="🔫 Arme", value=gun, inline=True)
        if style:
            embed.add_field(name="🥋 Style de combat", value=style, inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /bloxfruits-profil — consulter le profil d'un membre (ou le sien)
    # ------------------------------------------------------------------
    @app_commands.command(name="bloxfruits-profil", description="Affiche le profil Blox Fruits d'un membre.")
    @app_commands.describe(membre="Le membre à consulter (toi par défaut)")
    async def bloxfruits_profil(self, interaction: discord.Interaction, membre: discord.Member | None = None):
        target = membre or interaction.user
        profile = await db.get_bloxfruits_profile(target.id, interaction.guild_id)

        if profile is None:
            is_self = target.id == interaction.user.id
            desc = (
                "Tu n'as" if is_self else f"**{target.display_name}** n'a"
            ) + " pas encore renseigné de profil Blox Fruits. Utilise `/bloxfruits` pour le faire."
            embed = discord.Embed(title="🤷 Aucun profil renseigné", description=desc, color=config.COLOR_MARINE)
            await interaction.response.send_message(embed=embed, ephemeral=is_self)
            return

        embed = discord.Embed(
            title=f"🍈 Profil Blox Fruits de {target.display_name}",
            color=config.COLOR_ECONOMY,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="💰 Bounty", value=profile["bounty"], inline=False)
        if profile.get("fruit"):
            embed.add_field(name="🍈 Fruit", value=profile["fruit"], inline=True)
        if profile.get("sword"):
            embed.add_field(name="⚔️ Épée", value=profile["sword"], inline=True)
        if profile.get("gun"):
            embed.add_field(name="🔫 Arme", value=profile["gun"], inline=True)
        if profile.get("fighting_style"):
            embed.add_field(name="🥋 Style de combat", value=profile["fighting_style"], inline=True)
        embed.set_footer(text=f"Dernière mise à jour : {profile['updated_at'][:10]}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /bloxfruits-liste — tous les profils renseignés sur le serveur
    # ------------------------------------------------------------------
    @app_commands.command(name="bloxfruits-liste", description="Liste tous les profils Blox Fruits renseignés sur ce serveur.")
    async def bloxfruits_liste(self, interaction: discord.Interaction):
        profiles = await db.get_all_bloxfruits_profiles(interaction.guild_id)

        if not profiles:
            embed = discord.Embed(
                title="🤷 Aucun profil renseigné",
                description="Personne n'a encore utilisé `/bloxfruits` sur ce serveur.",
                color=config.COLOR_MARINE,
            )
            await interaction.response.send_message(embed=embed)
            return

        lines = []
        for p in profiles[:25]:
            member = interaction.guild.get_member(p["user_id"])
            name = member.display_name if member else f"Membre {p['user_id']}"
            parts = [x for x in [p.get("fruit"), p.get("sword"), p.get("gun"), p.get("fighting_style")] if x]
            equip_text = " / ".join(parts) if parts else "Non précisé"
            lines.append(f"**{name}** — 💰 {p['bounty']} — {equip_text}")

        embed = discord.Embed(
            title="🍈 Profils Blox Fruits du serveur",
            description="\n".join(lines),
            color=config.COLOR_ECONOMY,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BloxFruits(bot))
