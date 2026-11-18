"""Rôles d'arrivée : attribution automatique de rôles aux nouveaux membres."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils.role_checks import role_assign_problem

logger = logging.getLogger("onepiece-bot.join-roles")

MAX_JOIN_ROLES = 10
TARGET_LABELS = {"all": "Tout le monde", "humans": "Membres uniquement", "bots": "Bots uniquement"}


def target_matches(target: str, member: discord.Member) -> bool:
    """Indique si une règle de rôle d'arrivée s'applique à ce compte (membre ou bot)."""
    if target == "bots":
        return member.bot
    if target == "humans":
        return not member.bot
    return True


class JoinRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    autorole = app_commands.Group(
        name="autorole",
        description="[Admin] Rôles donnés automatiquement à l'arrivée.",
        guild_only=True,
        default_permissions=discord.Permissions(manage_roles=True),
    )

    # ------------------------------------------------------------------
    # Attribution
    # ------------------------------------------------------------------

    async def _send_log(self, member: discord.Member, roles: list[discord.Role]):
        channel_id = await db.get_log_channel(member.guild.id, "membres")
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title="👋 Rôle(s) d'arrivée attribué(s)",
            description=f"{member.mention} a reçu : {', '.join(role.mention for role in roles)}",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="Membre", value=f"{member} (`{member.id}`)", inline=False)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def apply_join_roles(self, member: discord.Member, *, after_screening: bool = False) -> list[discord.Role]:
        """Donne les rôles d'arrivée applicables. Retourne les rôles réellement ajoutés."""
        guild = member.guild
        rules = await db.get_join_roles(guild.id)
        if not rules:
            return []
        settings = await db.get_join_role_settings(guild.id)
        if settings["wait_screening"] and member.pending and not after_screening:
            return []  # le membre n'a pas encore accepté le règlement : on attend

        roles: list[discord.Role] = []
        for rule in rules:
            if not target_matches(rule["target"], member):
                continue
            role = guild.get_role(rule["role_id"])
            if role is None or role in member.roles:
                continue
            problem = role_assign_problem(guild, role, privileged=True)
            if problem:
                logger.warning("Rôle d'arrivée %s ignoré sur %s : %s", role.id, guild.id, problem)
                continue
            roles.append(role)
        if not roles:
            return []
        try:
            await member.add_roles(*roles, reason="Rôle d'arrivée")
        except discord.NotFound:
            return []  # le membre est déjà reparti (ou a été banni)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Impossible d'attribuer les rôles d'arrivée à %s sur %s", member.id, guild.id)
            return []
        await self._send_log(member, roles)
        return roles

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.apply_join_roles(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Le membre vient de valider le règlement du serveur (écran d'accueil Discord).
        if before.pending and not after.pending:
            await self.apply_join_roles(after, after_screening=True)

    # ------------------------------------------------------------------
    # Commandes
    # ------------------------------------------------------------------

    @autorole.command(name="add", description="Ajoute un rôle donné automatiquement aux nouveaux arrivants.")
    @app_commands.describe(role="Rôle à donner à l'arrivée", cible="Qui reçoit ce rôle (par défaut : tout le monde)")
    @app_commands.choices(cible=[app_commands.Choice(name=label, value=value) for value, label in TARGET_LABELS.items()])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_add(
        self, interaction: discord.Interaction, role: discord.Role,
        cible: app_commands.Choice[str] | None = None,
    ):
        problem = role_assign_problem(
            interaction.guild, role, interaction.user, privileged=interaction.guild.owner_id == interaction.user.id
        )
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        existing = await db.get_join_roles(interaction.guild_id)
        if len(existing) >= MAX_JOIN_ROLES and role.id not in {r["role_id"] for r in existing}:
            await interaction.response.send_message(
                f"Tu peux configurer **{MAX_JOIN_ROLES} rôles d'arrivée** au maximum.", ephemeral=True
            )
            return
        target = cible.value if cible else "all"
        await db.add_join_role(interaction.guild_id, role.id, target, interaction.user.id)
        await interaction.response.send_message(
            f"{role.mention} sera donné à l'arrivée ({TARGET_LABELS[target].lower()}).",
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _configured_roles_autocomplete(self, interaction: discord.Interaction, current: str):
        rules = await db.get_join_roles(interaction.guild_id)
        choices = []
        for rule in rules:
            role = interaction.guild.get_role(rule["role_id"])
            label = f"@{role.name}" if role else f"Rôle supprimé ({rule['role_id']})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=str(rule["role_id"])))
        return choices[:25]

    @autorole.command(name="remove", description="Retire un rôle de la liste des rôles d'arrivée.")
    @app_commands.describe(role="Rôle à retirer de la liste")
    @app_commands.autocomplete(role=_configured_roles_autocomplete)
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_remove(self, interaction: discord.Interaction, role: str):
        try:
            role_id = int(role)
        except ValueError:
            await interaction.response.send_message("Choisis un rôle dans la liste proposée.", ephemeral=True)
            return
        if await db.remove_join_role(interaction.guild_id, role_id):
            await interaction.response.send_message("Rôle retiré des rôles d'arrivée.", ephemeral=True)
        else:
            await interaction.response.send_message("Ce rôle n'est pas un rôle d'arrivée.", ephemeral=True)

    @autorole.command(name="list", description="Affiche les rôles donnés à l'arrivée.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_list(self, interaction: discord.Interaction):
        rules = await db.get_join_roles(interaction.guild_id)
        settings = await db.get_join_role_settings(interaction.guild_id)
        if not rules:
            await interaction.response.send_message(
                "Aucun rôle d'arrivée configuré. Utilise `/autorole add`.", ephemeral=True
            )
            return
        lines = []
        for rule in rules:
            role = interaction.guild.get_role(rule["role_id"])
            label = role.mention if role else f"Rôle supprimé (`{rule['role_id']}`)"
            lines.append(f"{label} — {TARGET_LABELS[rule['target']]}")
        embed = discord.Embed(title="👋 Rôles d'arrivée", description="\n".join(lines), color=config.COLOR_MARINE)
        embed.add_field(
            name="Validation du règlement",
            value="Les rôles sont donnés après validation du règlement." if settings["wait_screening"]
            else "Les rôles sont donnés dès l'arrivée.",
            inline=False,
        )
        await interaction.response.send_message(
            embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )

    @autorole.command(
        name="screening",
        description="Attendre ou non la validation du règlement avant de donner les rôles.",
    )
    @app_commands.describe(attendre="Oui : rôles donnés après validation du règlement (écran d'accueil Discord)")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorole_screening(self, interaction: discord.Interaction, attendre: bool):
        await db.set_join_role_wait_screening(interaction.guild_id, attendre)
        await interaction.response.send_message(
            "Les rôles seront donnés **après validation du règlement**." if attendre
            else "Les rôles seront donnés **dès l'arrivée**.",
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            message = "Tu dois posséder la permission **Gérer les rôles**."
        else:
            logger.exception("Erreur dans une commande de rôles d'arrivée", exc_info=error)
            message = "Une erreur est survenue pendant la gestion des rôles d'arrivée."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(JoinRoles(bot))
