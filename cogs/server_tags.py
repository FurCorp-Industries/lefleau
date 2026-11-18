"""Détection des tags de serveur Discord et attribution automatique de rôles."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils.server_tags import (
    get_primary_guild_identity,
    normalize_server_tag,
    user_matches_server_tag,
)

logger = logging.getLogger("onepiece-bot.server-tags")


class ServerTags(commands.Cog):

    tags = app_commands.Group(name="tags", description="Tags serveur et règles de rôles", guild_only=True)
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _validate_tag(tag: str) -> tuple[str, str] | None:
        display = tag.strip()
        if not display or len(display) > 4:
            return None
        return display, normalize_server_tag(display)

    @staticmethod
    def _role_problem(interaction: discord.Interaction, role: discord.Role) -> str | None:
        guild = interaction.guild
        member = interaction.user
        bot_member = guild.me
        if role.is_default():
            return "Le rôle `@everyone` ne peut pas être utilisé."
        if role.managed:
            return "Ce rôle est géré par Discord ou une intégration."
        if bot_member is None or not bot_member.guild_permissions.manage_roles:
            return "Le bot doit posséder la permission **Gérer les rôles**."
        if role >= bot_member.top_role:
            return "Le rôle choisi doit être placé sous le rôle le plus élevé du bot."
        if guild.owner_id != member.id and role >= member.top_role:
            return "Tu ne peux pas configurer un rôle égal ou supérieur à ton rôle principal."
        return None

    async def _send_change_log(
        self,
        member: discord.Member,
        role: discord.Role,
        tag: str,
        added: bool,
    ):
        channel_id = await db.get_log_channel(member.guild.id, "membres")
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title="🏷️ Tag de serveur détecté",
            description=f"Le rôle {role.mention} a été **{'ajouté' if added else 'retiré'}** à {member.mention}.",
            color=config.COLOR_SUCCESS if added else config.COLOR_MARINE,
        )
        embed.add_field(name="Tag surveillé", value=f"`{tag}`", inline=True)
        embed.add_field(name="Membre", value=f"{member} (`{member.id}`)", inline=False)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def _apply_rules(
        self,
        member: discord.Member,
        rules: list[dict] | None = None,
    ) -> tuple[int, int, int]:
        """Applique les règles et retourne (ajouts, retraits, erreurs)."""
        if member.bot:
            return 0, 0, 0
        rules = rules if rules is not None else await db.get_server_tag_rules(member.guild.id)
        added = removed = errors = 0

        for rule in rules:
            role = member.guild.get_role(rule["role_id"])
            if role is None:
                errors += 1
                continue

            matches = user_matches_server_tag(
                member,
                rule["tag_key"],
                rule["source_guild_id"],
            )
            assigned_by_bot = await db.has_server_tag_assignment(rule["id"], member.id)

            if matches and role not in member.roles:
                try:
                    await member.add_roles(
                        role,
                        reason=f"Tag de serveur détecté : {rule['tag']}",
                    )
                    await db.save_server_tag_assignment(
                        rule["id"], member.guild.id, member.id, role.id
                    )
                    added += 1
                    await self._send_change_log(member, role, rule["tag"], True)
                except (discord.Forbidden, discord.HTTPException):
                    errors += 1
            elif not matches and assigned_by_bot:
                try:
                    if role in member.roles:
                        await member.remove_roles(
                            role,
                            reason=f"Tag de serveur retiré ou modifié : {rule['tag']}",
                        )
                        removed += 1
                        await self._send_change_log(member, role, rule["tag"], False)
                    await db.delete_server_tag_assignment(rule["id"], member.id)
                except (discord.Forbidden, discord.HTTPException):
                    errors += 1

        return added, removed, errors

    @tags.command(
        name="rule-add",
        description="[Admin] Donne automatiquement un rôle aux membres portant un tag de serveur.",
    )
    @app_commands.describe(
        tag="Tag Discord à détecter (1 à 4 caractères)",
        role="Rôle donné lorsque le tag est affiché",
        serveur_origine_id="ID du serveur propriétaire du tag (optionnel mais recommandé)",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def tag_rule_add(
        self,
        interaction: discord.Interaction,
        tag: str,
        role: discord.Role,
        serveur_origine_id: str | None = None,
    ):
        validated = self._validate_tag(tag)
        if validated is None:
            await interaction.response.send_message(
                "Le tag doit contenir entre **1 et 4 caractères**.", ephemeral=True
            )
            return
        role_problem = self._role_problem(interaction, role)
        if role_problem:
            await interaction.response.send_message(role_problem, ephemeral=True)
            return

        source_guild_id = 0
        if serveur_origine_id:
            raw_id = serveur_origine_id.strip()
            if not raw_id.isdigit() or int(raw_id) <= 0:
                await interaction.response.send_message(
                    "L'ID du serveur d'origine doit être un identifiant Discord valide.",
                    ephemeral=True,
                )
                return
            source_guild_id = int(raw_id)

        display_tag, tag_key = validated
        rule_id = await db.add_server_tag_rule(
            interaction.guild_id,
            display_tag,
            tag_key,
            source_guild_id,
            role.id,
            interaction.user.id,
        )
        source_text = f"serveur `{source_guild_id}`" if source_guild_id else "n'importe quel serveur utilisant ce tag"
        embed = discord.Embed(
            title="✅ Règle de tag enregistrée",
            description=(
                f"Les membres affichant **`{display_tag}`** recevront {role.mention}.\n"
                f"Origine : {source_text}.\n\n"
                "Utilise `/tag-scan` une fois pour contrôler les membres déjà présents."
            ),
            color=config.COLOR_SUCCESS,
        )
        embed.set_footer(text=f"Règle #{rule_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tags.command(name="rule-list", description="[Admin] Liste les règles de tags du serveur.")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def tag_rule_list(self, interaction: discord.Interaction):
        rules = await db.get_server_tag_rules(interaction.guild_id)
        if not rules:
            await interaction.response.send_message(
                "Aucune règle de tag n'est configurée.", ephemeral=True
            )
            return
        lines = []
        for rule in rules:
            role = interaction.guild.get_role(rule["role_id"])
            role_text = role.mention if role else f"rôle supprimé (`{rule['role_id']}`)"
            source = f" • origine `{rule['source_guild_id']}`" if rule["source_guild_id"] else ""
            lines.append(f"**#{rule['id']}** • `{rule['tag']}` → {role_text}{source}")
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🏷️ Règles de tags de serveur",
                description="\n".join(lines)[:4096],
                color=config.COLOR_MARINE,
            ),
            ephemeral=True,
        )

    @tags.command(name="rule-remove", description="[Admin] Supprime une règle de tag.")
    @app_commands.describe(regle_id="Numéro affiché par /tag-rule-list")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def tag_rule_remove(self, interaction: discord.Interaction, regle_id: int):
        rule = await db.get_server_tag_rule(interaction.guild_id, regle_id)
        if rule is None:
            await interaction.response.send_message("Règle introuvable.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        role = interaction.guild.get_role(rule["role_id"])
        assignments = await db.get_server_tag_rule_assignments(interaction.guild_id, regle_id)
        removed = errors = 0
        if role is not None:
            for assignment in assignments:
                member = interaction.guild.get_member(assignment["user_id"])
                if member is None or role not in member.roles:
                    continue
                try:
                    await member.remove_roles(role, reason=f"Suppression de la règle de tag #{regle_id}")
                    removed += 1
                except (discord.Forbidden, discord.HTTPException):
                    errors += 1
        await db.delete_server_tag_rule(interaction.guild_id, regle_id)
        message = f"Règle **#{regle_id}** supprimée. {removed} rôle(s) retiré(s)."
        if errors:
            message += f" ⚠️ {errors} retrait(s) impossible(s)."
        await interaction.followup.send(message, ephemeral=True)

    @tags.command(name="scan", description="[Admin] Vérifie les tags de tous les membres présents.")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def tag_scan(self, interaction: discord.Interaction):
        rules = await db.get_server_tag_rules(interaction.guild_id)
        if not rules:
            await interaction.response.send_message(
                "Configure d'abord une règle avec `/tag-rule-add`.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        added = removed = errors = checked = 0
        for member in interaction.guild.members:
            if member.bot:
                continue
            result = await self._apply_rules(member, rules)
            added += result[0]
            removed += result[1]
            errors += result[2]
            checked += 1
        await interaction.followup.send(
            f"Analyse terminée : **{checked}** membres vérifiés, **{added}** rôles ajoutés, "
            f"**{removed}** retirés, **{errors}** erreur(s).",
            ephemeral=True,
        )

    @tags.command(name="check", description="[Admin] Affiche le tag actuellement détecté sur un membre.")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def tag_check(self, interaction: discord.Interaction, membre: discord.Member):
        tag_key, source_guild_id = get_primary_guild_identity(membre)
        if tag_key is None:
            description = f"Aucun tag de serveur public n'est détecté pour {membre.mention}."
        else:
            description = (
                f"Tag détecté pour {membre.mention} : **`{tag_key}`**\n"
                f"Serveur d'origine : `{source_guild_id or 'non communiqué par Discord'}`"
            )
        await interaction.response.send_message(
            embed=discord.Embed(title="🏷️ Détection du tag", description=description, color=config.COLOR_MARINE),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._apply_rules(member)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if get_primary_guild_identity(before) == get_primary_guild_identity(after):
            return
        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if member is not None:
                await self._apply_rules(member)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        if isinstance(error, app_commands.MissingPermissions):
            message = "Tu dois posséder la permission **Gérer les rôles**."
        else:
            logger.exception("Erreur dans une commande de tags", exc_info=error)
            message = "Une erreur est survenue pendant la gestion des tags."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerTags(bot))
