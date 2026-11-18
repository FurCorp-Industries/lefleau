"""Persistent reaction roles configured through Discord slash commands.

Commands: /reaction-roles create|add|remove|list|delete.
Reactions apply immediately via raw gateway events, including after restarts.
"""

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils.role_checks import role_assign_problem

logger = logging.getLogger('onepiece-bot.reaction-roles')
CUSTOM_EMOJI = re.compile(r'^<a?:[^:>]+:(\d{15,22})>$')
MAX_BINDINGS = 20


def emoji_key(value: str) -> str:
    """Normalize custom emoji syntax/ID, keep Unicode emoji as-is."""
    value = value.strip()
    match = CUSTOM_EMOJI.fullmatch(value)
    if match:
        return match.group(1)
    if value.isdecimal() and 15 <= len(value) <= 22:
        return value
    return value


def key_from_payload(emoji: discord.PartialEmoji) -> str:
    return str(emoji.id) if emoji.id else emoji.name or ''


class ReactionRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    reaction_roles = app_commands.Group(
        name='reaction-roles', description='Manage self-assignable roles via reactions.',
        guild_only=True, default_permissions=discord.Permissions(manage_roles=True),
    )

    async def _panel(self, interaction: discord.Interaction, message_id: str):
        if not message_id.isdecimal():
            await interaction.response.send_message('Indique un ID de message numérique.', ephemeral=True)
            return None
        panel = await db.get_reaction_role_panel(interaction.guild_id, int(message_id))
        if panel is None:
            await interaction.response.send_message('Panneau introuvable. Utilise `/reaction-roles create`.', ephemeral=True)
            return None
        return panel

    @reaction_roles.command(name='create', description='Publie un panneau de rôles par réactions.')
    @app_commands.describe(channel='Salon de publication', title='Titre de l’embed', description='Texte d’explication')
    @app_commands.checks.has_permissions(manage_roles=True)
    async def create(self, interaction: discord.Interaction, channel: discord.TextChannel,
                     title: str = '🎭 Choisis tes rôles', description: str = 'Réagis pour recevoir un rôle. Retire ta réaction pour le perdre.'):
        me = interaction.guild.me
        if me is None:
            return await interaction.response.send_message('Bot introuvable dans ce serveur.', ephemeral=True)
        p = channel.permissions_for(me)
        if not (p.send_messages and p.embed_links and p.add_reactions and p.read_message_history and p.view_channel):
            return await interaction.response.send_message(
                'Il me faut Voir le salon, Envoyer des messages, Intégrer des liens, Ajouter des réactions et Lire l’historique.', ephemeral=True)
        if len(title) > 256 or len(description) > 4096:
            return await interaction.response.send_message('Titre ou description trop long.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            message = await channel.send(embed=discord.Embed(title=title, description=description, color=0x5865F2),
                                         allowed_mentions=discord.AllowedMentions.none())
            await db.create_reaction_role_panel(interaction.guild_id, channel.id, message.id)
        except (discord.HTTPException, discord.Forbidden) as exc:
            logger.warning('Creation du panneau impossible: %s', exc)
            return await interaction.followup.send('Impossible de publier le panneau dans ce salon.', ephemeral=True)
        await interaction.followup.send(
            f'✅ Panneau créé : {message.jump_url}\n**ID du message :** `{message.id}`\n'
            'Associe ensuite des emojis avec `/reaction-roles add`.', ephemeral=True)

    @reaction_roles.command(name='add', description='Associe un emoji à un rôle sur un panneau (ou remplace une association).')
    @app_commands.describe(message_id='ID du panneau', emoji='Emoji Unicode ou emoji personnalisé du serveur', role='Rôle attribué')
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
        panel = await self._panel(interaction, message_id)
        if panel is None:
            return
        problem = role_assign_problem(interaction.guild, role, member=interaction.user)
        if problem:
            return await interaction.response.send_message(problem, ephemeral=True)
        key = emoji_key(emoji)
        if not key:
            return await interaction.response.send_message('Emoji invalide.', ephemeral=True)
        mappings = await db.list_reaction_role_mappings(interaction.guild_id, int(message_id))
        if len(mappings) >= MAX_BINDINGS and key not in {r['emoji_key'] for r in mappings}:
            return await interaction.response.send_message(f'Maximum {MAX_BINDINGS} emojis par panneau.', ephemeral=True)
        channel = interaction.guild.get_channel(panel['channel_id'])
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message('Salon du panneau introuvable.', ephemeral=True)
        try:
            message = await channel.fetch_message(panel['message_id'])
            await message.add_reaction(emoji)
        except (discord.HTTPException, discord.Forbidden, ValueError) as exc:
            logger.warning('Emoji non utilisable: %s', exc)
            return await interaction.response.send_message(
                'Impossible d’ajouter cet emoji. Utilise un emoji disponible pour le bot.', ephemeral=True)
        await db.upsert_reaction_role_mapping(interaction.guild_id, int(message_id), key, emoji, role.id)
        await interaction.response.send_message(
            f'✅ {emoji} attribuera maintenant {role.mention}. Retirer sa réaction enlèvera ce rôle.\n'
            'Les réactions déjà présentes avant cette configuration ne sont pas rétroactives.', ephemeral=True)

    @reaction_roles.command(name='remove', description='Supprime une association emoji/rôle d’un panneau.')
    @app_commands.describe(message_id='ID du panneau', emoji='Emoji à retirer')
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove(self, interaction: discord.Interaction, message_id: str, emoji: str):
        panel = await self._panel(interaction, message_id)
        if panel is None:
            return
        deleted = await db.delete_reaction_role_mapping(interaction.guild_id, int(message_id), emoji_key(emoji))
        if not deleted:
            return await interaction.response.send_message('Aucune association correspondante.', ephemeral=True)
        await interaction.response.send_message('✅ Association supprimée. Les rôles déjà attribués ne sont pas retirés.', ephemeral=True)

    @reaction_roles.command(name='list', description='Affiche les panneaux et les rôles associés.')
    @app_commands.checks.has_permissions(manage_roles=True)
    async def list_panels(self, interaction: discord.Interaction):
        panels = await db.list_reaction_role_panels(interaction.guild_id)
        if not panels:
            return await interaction.response.send_message('Aucun panneau configuré.', ephemeral=True)
        lines = []
        for panel in panels[:20]:
            pairs = await db.list_reaction_role_mappings(interaction.guild_id, panel['message_id'])
            details = ', '.join(f"{x['emoji_display']} → <@&{x['role_id']}>" for x in pairs) or 'Aucun rôle associé'
            lines.append(f"• <#{panel['channel_id']}> · `{panel['message_id']}` : {details}")
        text = '\n'.join(lines)
        if len(text) > 1900:
            text = text[:1870] + '\n… (liste tronquée)'
        await interaction.response.send_message(text, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @reaction_roles.command(name='delete', description='Désactive un panneau et ses associations (sans effacer le message).')
    @app_commands.describe(message_id='ID du panneau à désactiver')
    @app_commands.checks.has_permissions(manage_roles=True)
    async def delete(self, interaction: discord.Interaction, message_id: str):
        panel = await self._panel(interaction, message_id)
        if panel is None:
            return
        await db.delete_reaction_role_panel(interaction.guild_id, int(message_id))
        await interaction.response.send_message(
            '✅ Panneau désactivé. Le message Discord reste visible ; supprime-le manuellement si nécessaire.', ephemeral=True)

    async def _handle(self, payload: discord.RawReactionActionEvent, adding: bool):
        if payload.guild_id is None or payload.user_id == (self.bot.user.id if self.bot.user else None):
            return
        mapping = await db.get_reaction_role_mapping(payload.guild_id, payload.message_id,
                                                     key_from_payload(payload.emoji))
        if mapping is None or mapping['channel_id'] != payload.channel_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(mapping['role_id'])
        if role is None or role_assign_problem(guild, role, privileged=True):
            return
        member = payload.member if adding else None
        if member is None:
            member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        if member.bot:
            return
        try:
            if adding and role not in member.roles:
                await member.add_roles(role, reason='Reaction role: reaction added')
            elif not adding and role in member.roles:
                await member.remove_roles(role, reason='Reaction role: reaction removed')
        except (discord.Forbidden, discord.HTTPException):
            logger.warning('Cannot update reaction role %s for member %s', role.id, payload.user_id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle(payload, True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle(payload, False)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.guild_id is not None:
            await db.delete_reaction_role_panel(payload.guild_id, payload.message_id)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = ('Permission **Gérer les rôles** requise.' if isinstance(error, app_commands.MissingPermissions)
               else 'Une erreur est survenue. Vérifie les logs du bot.')
        if not isinstance(error, app_commands.MissingPermissions):
            logger.error('Reaction roles command error: %s', error, exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
