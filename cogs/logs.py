"""
cogs/logs.py
--------------
Système de logs configurable, catégorie par catégorie : messages
(suppressions/modifications), membres (arrivées/départs/bans/rôles),
salons, rôles, vocal, et paramètres du serveur. Chaque catégorie peut
être activée dans un salon différent, ou désactivée indépendamment
des autres.

⚠️ Nécessite l'intent privilégié "MESSAGE CONTENT INTENT" activé sur le
Discord Developer Portal (comme "SERVER MEMBERS INTENT") pour pouvoir
logger le contenu des messages supprimés/modifiés.
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db

LOG_CATEGORY_CHOICES = [
    app_commands.Choice(name="Messages (suppressions / modifications)", value="messages"),
    app_commands.Choice(name="Membres (arrivées / départs / bans / rôles / pseudo)", value="membres"),
    app_commands.Choice(name="Salons (création / suppression / modification)", value="salons"),
    app_commands.Choice(name="Rôles (création / suppression / modification)", value="roles"),
    app_commands.Choice(name="Vocal (connexions / déconnexions / changements)", value="vocal"),
    app_commands.Choice(name="Serveur (nom / icône)", value="serveur"),
    app_commands.Choice(name="Boosts (nouveau boost du serveur)", value="boosts"),
]

CATEGORY_LABELS = {choice.value: choice.name for choice in LOG_CATEGORY_CHOICES}


class Logs(commands.Cog):
    """Système de logs du serveur, configurable par catégorie."""

    logs = app_commands.Group(name="logs", description="Gestion des journaux serveur", guild_only=True)

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, guild_id: int, category: str, embed: discord.Embed):
        """Envoie un embed dans le salon configuré pour cette catégorie, si activé."""
        channel_id = await db.get_log_channel(guild_id, category)
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    # Commandes de configuration (admin)
    # ------------------------------------------------------------------
    @logs.command(name="setup", description="[Admin] Active un type de logs et choisit son salon.")
    @app_commands.describe(categorie="Le type d'événements à journaliser", salon="Le salon où envoyer ces logs")
    @app_commands.choices(categorie=LOG_CATEGORY_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def logs_setup(
        self,
        interaction: discord.Interaction,
        categorie: app_commands.Choice[str],
        salon: discord.TextChannel,
    ):
        await db.set_log_channel(interaction.guild_id, categorie.value, salon.id)
        embed = discord.Embed(
            title="✅ Logs activés",
            description=f"**{categorie.name}** sera désormais journalisé dans {salon.mention}.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @logs.command(name="disable", description="[Admin] Désactive un type de logs.")
    @app_commands.describe(categorie="Le type d'événements à arrêter de journaliser")
    @app_commands.choices(categorie=LOG_CATEGORY_CHOICES)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def logs_disable(self, interaction: discord.Interaction, categorie: app_commands.Choice[str]):
        await db.disable_log_category(interaction.guild_id, categorie.value)
        embed = discord.Embed(
            title="🔇 Logs désactivés",
            description=f"**{categorie.name}** ne sera plus journalisé (le salon reste mémorisé pour une réactivation rapide).",
            color=config.COLOR_MARINE,
        )
        await interaction.response.send_message(embed=embed)

    @logs.command(name="status", description="[Admin] Affiche la configuration actuelle des logs.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def logs_status(self, interaction: discord.Interaction):
        settings = {s["category"]: s for s in await db.get_all_log_settings(interaction.guild_id)}

        embed = discord.Embed(title="📋 Configuration des logs", color=config.COLOR_MARINE)
        for value, label in CATEGORY_LABELS.items():
            entry = settings.get(value)
            if entry and entry["enabled"]:
                channel = interaction.guild.get_channel(entry["channel_id"])
                status = channel.mention if channel else "⚠️ salon introuvable"
            else:
                status = "❌ désactivé"
            embed.add_field(name=label, value=status, inline=False)

        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="🚫 Accès refusé",
                description="Seuls les membres avec la permission *Gérer le serveur* peuvent faire ça.",
                color=config.COLOR_ERROR,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            raise error

    # ------------------------------------------------------------------
    # Catégorie : messages
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        embed = discord.Embed(
            title="🗑️ Message supprimé",
            description=message.content[:2000] if message.content else "*(pas de texte — embed ou pièce jointe seule)*",
            color=config.COLOR_ERROR,
        )
        embed.add_field(name="Auteur", value=message.author.mention, inline=True)
        embed.add_field(name="Salon", value=message.channel.mention, inline=True)
        if message.attachments:
            embed.add_field(
                name="Pièces jointes",
                value="\n".join(a.url for a in message.attachments)[:1024],
                inline=False,
            )
        embed.set_footer(text=f"ID utilisateur : {message.author.id}")
        await self._send_log(message.guild.id, "messages", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(title="✏️ Message modifié", color=config.COLOR_MARINE)
        embed.add_field(name="Auteur", value=before.author.mention, inline=True)
        embed.add_field(name="Salon", value=before.channel.mention, inline=True)
        embed.add_field(name="Avant", value=(before.content or "*(vide)*")[:1024], inline=False)
        embed.add_field(name="Après", value=(after.content or "*(vide)*")[:1024], inline=False)
        embed.add_field(name="Lien", value=f"[Aller au message]({after.jump_url})", inline=False)
        await self._send_log(before.guild.id, "messages", embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages or messages[0].guild is None:
            return
        embed = discord.Embed(
            title="🗑️ Suppression en masse",
            description=f"**{len(messages)}** messages supprimés dans {messages[0].channel.mention}.",
            color=config.COLOR_ERROR,
        )
        await self._send_log(messages[0].guild.id, "messages", embed)

    # ------------------------------------------------------------------
    # Catégorie : membres
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="📥 Nouveau membre",
            description=f"{member.mention} a rejoint le serveur.",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="Compte créé", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID : {member.id}")
        await self._send_log(member.guild.id, "membres", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="📤 Membre parti",
            description=f"**{member}** a quitté (ou a été expulsé) le serveur.",
            color=config.COLOR_ERROR,
        )
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        if roles:
            embed.add_field(name="Rôles qu'il avait", value=", ".join(roles)[:1024], inline=False)
        embed.set_footer(text=f"ID : {member.id}")
        await self._send_log(member.guild.id, "membres", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="⛔ Membre banni", description=f"**{user}** a été banni.", color=config.COLOR_ERROR
        )
        embed.set_footer(text=f"ID : {user.id}")
        await self._send_log(guild.id, "membres", embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🕊️ Membre débanni", description=f"**{user}** a été débanni.", color=config.COLOR_SUCCESS
        )
        embed.set_footer(text=f"ID : {user.id}")
        await self._send_log(guild.id, "membres", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Boost du serveur (Nitro)
        if before.premium_since is None and after.premium_since is not None:
            embed = discord.Embed(
                title="🚀 Nouveau boost !",
                description=f"{after.mention} vient de booster le serveur ! Merci pour ton soutien 💖",
                color=0xF47FFF,  # rose "Nitro Boost"
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="Boosts totaux du serveur", value=str(after.guild.premium_subscription_count or 0), inline=True)
            embed.add_field(name="Niveau du serveur", value=f"Niveau {after.guild.premium_tier}", inline=True)
            await self._send_log(after.guild.id, "boosts", embed)

        # Mise en sourdine (timeout)
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until and after.timed_out_until > discord.utils.utcnow():
                embed = discord.Embed(
                    title="🔇 Mise en sourdine",
                    description=f"{after.mention} est en sourdine jusqu'à {discord.utils.format_dt(after.timed_out_until)}.",
                    color=config.COLOR_MARINE,
                )
            else:
                embed = discord.Embed(
                    title="🔊 Sourdine levée", description=f"{after.mention} n'est plus en sourdine.", color=config.COLOR_SUCCESS
                )
            await self._send_log(after.guild.id, "membres", embed)

        # Pseudo
        if before.nick != after.nick:
            embed = discord.Embed(title="✏️ Pseudo modifié", color=config.COLOR_MARINE)
            embed.add_field(name="Membre", value=after.mention, inline=False)
            embed.add_field(name="Avant", value=before.nick or before.name, inline=True)
            embed.add_field(name="Après", value=after.nick or after.name, inline=True)
            await self._send_log(after.guild.id, "membres", embed)

        # Rôles
        before_roles, after_roles = set(before.roles), set(after.roles)
        added, removed = after_roles - before_roles, before_roles - after_roles
        if added or removed:
            embed = discord.Embed(title="🎭 Rôles modifiés", color=config.COLOR_MARINE)
            embed.add_field(name="Membre", value=after.mention, inline=False)
            if added:
                embed.add_field(name="Ajoutés", value=", ".join(r.mention for r in added)[:1024], inline=True)
            if removed:
                embed.add_field(name="Retirés", value=", ".join(r.mention for r in removed)[:1024], inline=True)
            await self._send_log(after.guild.id, "membres", embed)

    # ------------------------------------------------------------------
    # Catégorie : salons
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="➕ Salon créé", description=f"{channel.mention} (`{channel.type}`)", color=config.COLOR_SUCCESS
        )
        await self._send_log(channel.guild.id, "salons", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="➖ Salon supprimé", description=f"**#{channel.name}** (`{channel.type}`)", color=config.COLOR_ERROR
        )
        await self._send_log(channel.guild.id, "salons", embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        changes = []
        if before.name != after.name:
            changes.append(f"Nom : `{before.name}` → `{after.name}`")
        if isinstance(before, discord.TextChannel) and isinstance(after, discord.TextChannel) and before.topic != after.topic:
            changes.append("Description modifiée")
        if not changes:
            return
        embed = discord.Embed(
            title="✏️ Salon modifié", description=f"{after.mention}\n" + "\n".join(changes), color=config.COLOR_MARINE
        )
        await self._send_log(after.guild.id, "salons", embed)

    # ------------------------------------------------------------------
    # Catégorie : rôles
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = discord.Embed(title="➕ Rôle créé", description=role.mention, color=config.COLOR_SUCCESS)
        await self._send_log(role.guild.id, "roles", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = discord.Embed(title="➖ Rôle supprimé", description=f"**@{role.name}**", color=config.COLOR_ERROR)
        await self._send_log(role.guild.id, "roles", embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = []
        if before.name != after.name:
            changes.append(f"Nom : `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append("Couleur modifiée")
        if before.permissions != after.permissions:
            changes.append("Permissions modifiées")
        if not changes:
            return
        embed = discord.Embed(
            title="✏️ Rôle modifié", description=f"{after.mention}\n" + "\n".join(changes), color=config.COLOR_MARINE
        )
        await self._send_log(after.guild.id, "roles", embed)

    # ------------------------------------------------------------------
    # Catégorie : vocal
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        if before.channel == after.channel:
            return  # mute/deaf uniquement, ignoré pour éviter le bruit

        if before.channel is None and after.channel is not None:
            embed = discord.Embed(
                title="🔊 Rejoint un vocal", description=f"{member.mention} → {after.channel.mention}", color=config.COLOR_SUCCESS
            )
        elif before.channel is not None and after.channel is None:
            embed = discord.Embed(
                title="🔇 Quitté un vocal", description=f"{member.mention} quitte {before.channel.mention}", color=config.COLOR_ERROR
            )
        else:
            embed = discord.Embed(
                title="🔀 Changement de vocal",
                description=f"{member.mention} : {before.channel.mention} → {after.channel.mention}",
                color=config.COLOR_MARINE,
            )
        await self._send_log(member.guild.id, "vocal", embed)

    # ------------------------------------------------------------------
    # Catégorie : serveur
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        changes = []
        if before.name != after.name:
            changes.append(f"Nom : `{before.name}` → `{after.name}`")
        if before.icon != after.icon:
            changes.append("Icône modifiée")
        if not changes:
            return
        embed = discord.Embed(title="⚙️ Serveur modifié", description="\n".join(changes), color=config.COLOR_MARINE)
        await self._send_log(after.id, "serveur", embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
