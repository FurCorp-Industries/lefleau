"""Commandes RYUKAI : profils compétitifs et enregistrement des wars."""

import re

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils.ryukai_card import generate_ryukai_card_sync


MATCH_TYPES = [
    app_commands.Choice(name="War", value="war"),
    app_commands.Choice(name="Pub War", value="pub_war"),
    app_commands.Choice(name="1v1", value="duel"),
]
MATCH_LABELS = {"war": "War", "pub_war": "Pub War", "duel": "1v1"}


def member_ids_from_mentions(raw: str) -> list[int]:
    """Extrait les mentions ou IDs Discord séparés par des espaces/virgules."""
    return list(dict.fromkeys(int(value) for value in re.findall(r"\d{15,22}", raw)))


def _is_wars_administrator(interaction: discord.Interaction) -> bool:
    """Les administrateurs restent toujours capables de gérer l'accès."""
    return bool(
        interaction.guild
        and (interaction.guild.owner_id == interaction.user.id or interaction.permissions.manage_guild)
    )


async def can_view_wars(interaction: discord.Interaction) -> bool:
    """Autorise tous les membres tant qu'aucun rôle n'est configuré."""
    if _is_wars_administrator(interaction):
        return True
    role_ids = await db.list_ryukai_access_roles(interaction.guild_id)
    if not role_ids:
        return True
    member_roles = {role.id for role in getattr(interaction.user, "roles", [])}
    return not member_roles.isdisjoint(role_ids)


async def can_record_wars(interaction: discord.Interaction) -> bool:
    """Conserve les résultats réservés au staff jusqu'à la configuration des rôles."""
    if _is_wars_administrator(interaction):
        return True
    role_ids = await db.list_ryukai_access_roles(interaction.guild_id)
    if not role_ids:
        return False
    member_roles = {role.id for role in getattr(interaction.user, "roles", [])}
    return not member_roles.isdisjoint(role_ids)


class WarProfiles(commands.Cog):
    """Regroupe les commandes RYUKAI sous /wars afin de garder les racines propres."""

    wars = app_commands.Group(
        name="wars",
        description="Profils RYUKAI et enregistrement des résultats de war.",
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @wars.command(name="profile", description="Affiche la carte RYUKAI d'un membre.")
    @app_commands.describe(membre="Membre dont tu veux voir la carte (optionnel)")
    @app_commands.check(can_view_wars)
    async def profile(self, interaction: discord.Interaction, membre: discord.Member | None = None):
        target = membre or interaction.user
        profile = await db.get_ryukai_profile(target.id, interaction.guild_id)
        await interaction.response.defer()
        avatar_bytes = await target.display_avatar.replace(size=256, format="png").read()
        card = generate_ryukai_card_sync(avatar_bytes, target.display_name, profile)
        await interaction.followup.send(file=discord.File(card, filename="ryukai_profile.png"))

    @wars.command(name="access-add", description="[Admin] Autorise un rôle à utiliser les commandes /wars.")
    @app_commands.describe(role="Rôle qui pourra utiliser /wars profile et /wars result")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def access_add(self, interaction: discord.Interaction, role: discord.Role):
        added = await db.add_ryukai_access_role(interaction.guild_id, role.id, interaction.user.id)
        message = (
            f"{role.mention} peut maintenant utiliser les commandes `/wars`."
            if added else f"{role.mention} est déjà autorisé."
        )
        await interaction.response.send_message(message, ephemeral=True)

    @wars.command(name="access-remove", description="[Admin] Retire l'accès /wars à un rôle.")
    @app_commands.describe(role="Rôle à retirer de la liste d'accès")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def access_remove(self, interaction: discord.Interaction, role: discord.Role):
        removed = await db.remove_ryukai_access_role(interaction.guild_id, role.id)
        message = (
            f"Accès `/wars` retiré à {role.mention}."
            if removed else f"{role.mention} ne faisait pas partie des rôles autorisés."
        )
        await interaction.response.send_message(message, ephemeral=True)

    @wars.command(name="access-list", description="[Admin] Liste les rôles autorisés pour /wars.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def access_list(self, interaction: discord.Interaction):
        role_ids = await db.list_ryukai_access_roles(interaction.guild_id)
        if not role_ids:
            text = "Aucun rôle configuré : `/wars profile` reste public et `/wars result` reste réservé au staff."
        else:
            text = "Rôles autorisés : " + " ".join(f"<@&{role_id}>" for role_id in role_ids)
        await interaction.response.send_message(text, ephemeral=True)

    @wars.command(name="config", description="[Staff] Configure les informations RYUKAI d'un membre.")
    @app_commands.describe(
        membre="Membre dont la carte doit être configurée",
        team="Ex. S, Alpha, RYUKAI",
        rank="Ex. Fighter, Leader",
        platform="Ex. PC / Console",
        region="Ex. FR, EU, NA",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def config(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        team: str,
        rank: str,
        platform: str,
        region: str,
    ):
        values = (team, rank, platform, region)
        if any(not value.strip() or len(value) > 32 for value in values):
            await interaction.response.send_message(
                "Chaque champ doit contenir entre 1 et 32 caractères.", ephemeral=True
            )
            return
        await db.set_ryukai_profile(
            membre.id, interaction.guild_id,
            team.strip(), rank.strip(), platform.strip(), region.strip(),
        )
        await interaction.response.send_message(
            f"Carte RYUKAI de {membre.mention} mise à jour : "
            f"**{team.strip()} · {rank.strip()} · {platform.strip()} · {region.strip()}**.",
            ephemeral=True,
        )

    @wars.command(name="result", description="[Staff] Enregistre un résultat et crédite chaque participant.")
    @app_commands.describe(
        type="Catégorie du match",
        gagnants="Mentions ou IDs des gagnants, séparés par des espaces ou virgules",
        perdants="Mentions ou IDs des perdants, séparés par des espaces ou virgules",
        note="Contexte facultatif (adversaire, score, etc.)",
    )
    @app_commands.choices(type=MATCH_TYPES)
    @app_commands.check(can_record_wars)
    async def result(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        gagnants: str,
        perdants: str,
        note: str = "",
    ):
        winner_ids = member_ids_from_mentions(gagnants)
        loser_ids = member_ids_from_mentions(perdants)
        if not winner_ids or not loser_ids:
            await interaction.response.send_message(
                "Indique au moins un gagnant et un perdant avec leurs mentions ou IDs Discord.",
                ephemeral=True,
            )
            return
        if set(winner_ids) & set(loser_ids):
            await interaction.response.send_message(
                "Un membre ne peut pas être à la fois gagnant et perdant.", ephemeral=True
            )
            return
        if type.value == "duel" and (len(winner_ids) != 1 or len(loser_ids) != 1):
            await interaction.response.send_message(
                "Un résultat **1v1** doit contenir exactement un gagnant et un perdant.", ephemeral=True
            )
            return

        guild = interaction.guild
        if guild is None:
            return
        unknown_ids = [member_id for member_id in winner_ids + loser_ids if guild.get_member(member_id) is None]
        if unknown_ids:
            listed = ", ".join(str(member_id) for member_id in unknown_ids)
            await interaction.response.send_message(
                f"Membre introuvable sur ce serveur : `{listed}`.", ephemeral=True
            )
            return

        result_id = await db.record_ryukai_result(
            guild.id, type.value, winner_ids, loser_ids, interaction.user.id, note.strip()[:300]
        )
        winner_mentions = " ".join(f"<@{member_id}>" for member_id in winner_ids)
        loser_mentions = " ".join(f"<@{member_id}>" for member_id in loser_ids)
        description = f"🏆 **Gagnants :** {winner_mentions}\n💢 **Défaites :** {loser_mentions}"
        if note.strip():
            description += f"\n📝 {note.strip()[:300]}"
        embed = discord.Embed(
            title=f"RYUKAI — {MATCH_LABELS[type.value]} enregistré",
            description=description,
            color=0xE952B9,
        )
        embed.set_footer(text=f"Résultat #{result_id} · enregistré par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            message = "Permission **Gérer le serveur** requise."
        elif isinstance(error, app_commands.CheckFailure):
            message = "Cette commande `/wars` est réservée aux rôles autorisés par le staff."
        else:
            message = "Impossible d'enregistrer ce résultat. Réessaie ou contacte un administrateur."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(WarProfiles(bot))
