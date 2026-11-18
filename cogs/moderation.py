"""
cogs/moderation.py
--------------------
Commandes de modération classiques, habillées sur le thème de la Marine /
Gouvernement Mondial. Toutes nécessitent les permissions Discord adéquates
(vérifiées à la fois côté Discord et manuellement, par sécurité).
"""

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils.helpers import parse_duration, format_duration

# Permissions liées à la modération, vérifiées par /modperms et /modroles
MOD_PERMISSIONS = [
    ("kick_members", "👢 Expulser des membres"),
    ("ban_members", "🔨 Bannir des membres"),
    ("moderate_members", "🔇 Modérer les membres (timeout)"),
    ("manage_messages", "🗑️ Gérer les messages"),
    ("manage_channels", "📁 Gérer les salons"),
    ("manage_roles", "🎭 Gérer les rôles"),
    ("manage_guild", "⚙️ Gérer le serveur"),
    ("administrator", "👑 Administrateur"),
]


async def warning_id_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplétion pour /unwarn : liste les avertissements du membre déjà sélectionné."""
    membre = getattr(interaction.namespace, "membre", None)
    if membre is None:
        return []

    user_id = membre.id if hasattr(membre, "id") else int(membre)
    warns = await db.get_warnings(interaction.guild_id, user_id)

    choices = []
    for w in warns:
        label = f"#{w['id']} — {w['reason'][:60]} ({w['created_at'][:10]})"
        if current in str(w["id"]) or current.lower() in w["reason"].lower():
            choices.append(app_commands.Choice(name=label[:100], value=w["id"]))
    return choices[:25]


async def banned_user_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplétion pour /unban : liste les membres actuellement bannis du serveur."""
    choices = []
    try:
        async for ban_entry in interaction.guild.bans(limit=100):
            user = ban_entry.user
            label = f"{user} ({user.id})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=str(user.id)))
            if len(choices) >= 25:
                break
    except discord.Forbidden:
        pass
    return choices


class Moderation(commands.Cog):
    """Commandes de modération façon Marine."""


    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _record_sanction(self, interaction: discord.Interaction, membre: discord.abc.User,
                               sanction_type: str, raison: str, duration_seconds: int | None = None):
        registry = self.bot.get_cog("CommunityTools")
        if registry is not None:
            await registry.record_sanction(
                interaction.guild, membre, sanction_type, interaction.user, raison, duration_seconds
            )

    # ------------------------------------------------------------------
    # /kick
    # ------------------------------------------------------------------
    @app_commands.command(name="kick", description="[Marine] Expulse un membre du serveur.")
    @app_commands.describe(membre="Le membre à expulser", raison="Raison de l'expulsion")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.default_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        raison: str = "Aucune raison fournie",
    ):
        if membre.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            embed = discord.Embed(
                title="❌ Grade insuffisant",
                description="Tu ne peux pas expulser un membre de rang égal ou supérieur au tien.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            await membre.kick(reason=f"{raison} — par {interaction.user}")
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission refusée",
                description="Je n'ai pas la permission d'expulser ce membre (rôle trop haut ?).",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await self._record_sanction(interaction, membre, "kick", raison)

        embed = discord.Embed(
            title="⚓ Membre expulsé par la Marine",
            description=f"**{membre}** a été escorté hors d'Impel Down (le serveur).",
            color=config.COLOR_MARINE,
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.set_footer(text=f"Ordre exécuté par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /ban
    # ------------------------------------------------------------------
    @app_commands.command(name="ban", description="[Marine] Bannit un membre du serveur.")
    @app_commands.describe(membre="Le membre à bannir", raison="Raison du bannissement")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        raison: str = "Aucune raison fournie",
    ):
        if membre.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            embed = discord.Embed(
                title="❌ Grade insuffisant",
                description="Tu ne peux pas bannir un membre de rang égal ou supérieur au tien.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            await membre.ban(reason=f"{raison} — par {interaction.user}")
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission refusée",
                description="Je n'ai pas la permission de bannir ce membre (rôle trop haut ?).",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await self._record_sanction(interaction, membre, "ban", raison)

        embed = discord.Embed(
            title="⛓️ Membre banni — Envoyé à Impel Down",
            description=f"**{membre}** a été banni définitivement du serveur.",
            color=config.COLOR_MARINE,
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.set_footer(text=f"Ordre exécuté par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /unban
    # ------------------------------------------------------------------
    @app_commands.command(name="unban", description="[Marine] Débannit un utilisateur du serveur.")
    @app_commands.describe(utilisateur="L'utilisateur banni à débannir", raison="Raison du débannissement")
    @app_commands.autocomplete(utilisateur=banned_user_autocomplete)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.default_permissions(ban_members=True)
    async def unban(
        self,
        interaction: discord.Interaction,
        utilisateur: str,
        raison: str = "Aucune raison fournie",
    ):
        try:
            user_id = int(utilisateur.strip())
        except ValueError:
            embed = discord.Embed(
                title="❌ Identifiant invalide",
                description="Choisis un utilisateur dans la liste proposée par l'autocomplétion, ou donne son ID Discord.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            ban_entry = await interaction.guild.fetch_ban(discord.Object(id=user_id))
        except discord.NotFound:
            embed = discord.Embed(
                title="❌ Utilisateur non banni",
                description="Cet utilisateur ne figure pas dans la liste des bannis de ce serveur.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            await interaction.guild.unban(ban_entry.user, reason=f"{raison} — par {interaction.user}")
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission refusée",
                description="Je n'ai pas la permission de débannir cet utilisateur.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🕊️ Libéré d'Impel Down",
            description=f"**{ban_entry.user}** a été débanni et peut désormais rejoindre le serveur.",
            color=config.COLOR_MARINE,
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.set_footer(text=f"Ordre exécuté par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /warn
    # ------------------------------------------------------------------
    @app_commands.command(name="warn", description="[Marine] Avertit un membre pour un comportement inapproprié.")
    @app_commands.describe(membre="Le membre à avertir", raison="Raison de l'avertissement")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        raison: str,
    ):
        if membre.bot:
            embed = discord.Embed(
                title="🤖 Impossible",
                description="On n'avertit pas les bots, ils n'ont pas de conscience à réveiller.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        warning_id = await db.add_warning(interaction.guild_id, membre.id, interaction.user.id, raison)
        await self._record_sanction(interaction, membre, "warn", raison)
        total = await db.get_warning_count(interaction.guild_id, membre.id)

        embed = discord.Embed(
            title="⚠️ Avertissement émis",
            description=f"**{membre}** a été averti par la Marine.",
            color=config.COLOR_MARINE,
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.add_field(name="N° d'avertissement", value=f"#{warning_id}", inline=True)
        embed.add_field(name="Total pour ce membre", value=str(total), inline=True)
        embed.set_footer(text=f"Ordre exécuté par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

        try:
            dm_embed = discord.Embed(
                title="⚠️ Tu as reçu un avertissement",
                description=f"Tu as été averti sur **{interaction.guild.name}**.",
                color=config.COLOR_ERROR,
            )
            dm_embed.add_field(name="Raison", value=raison, inline=False)
            dm_embed.set_footer(text=f"Total d'avertissements sur ce serveur : {total}")
            await membre.send(embed=dm_embed)
        except discord.Forbidden:
            pass  # MPs fermés, on ignore silencieusement

    # ------------------------------------------------------------------
    # /warnings
    # ------------------------------------------------------------------
    @app_commands.command(name="warnings", description="[Marine] Affiche l'historique des avertissements d'un membre.")
    @app_commands.describe(membre="Le membre dont tu veux voir les avertissements")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def warnings_cmd(self, interaction: discord.Interaction, membre: discord.Member):
        warns = await db.get_warnings(interaction.guild_id, membre.id)

        if not warns:
            embed = discord.Embed(
                title="✅ Casier vierge",
                description=f"**{membre}** n'a aucun avertissement sur ce serveur.",
                color=config.COLOR_SUCCESS,
            )
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(
            title=f"⚠️ Avertissements de {membre.display_name}",
            description=f"**{len(warns)}** avertissement(s) au total.",
            color=config.COLOR_MARINE,
        )
        for w in warns[:25]:
            moderator = interaction.guild.get_member(w["moderator_id"])
            mod_name = moderator.display_name if moderator else f"Modérateur {w['moderator_id']}"
            embed.add_field(
                name=f"#{w['id']} — {w['created_at'][:10]}",
                value=f"{w['reason']}\n_par {mod_name}_",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /unwarn
    # ------------------------------------------------------------------
    @app_commands.command(name="unwarn", description="[Marine] Retire un avertissement précis d'un membre.")
    @app_commands.describe(membre="Le membre concerné", avertissement="L'avertissement à retirer")
    @app_commands.autocomplete(avertissement=warning_id_autocomplete)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def unwarn(self, interaction: discord.Interaction, membre: discord.Member, avertissement: int):
        removed = await db.remove_warning(avertissement, interaction.guild_id)

        if not removed:
            embed = discord.Embed(
                title="❌ Avertissement introuvable",
                description="Utilise `/warnings` pour voir les avertissements actifs de ce membre.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        total = await db.get_warning_count(interaction.guild_id, membre.id)
        embed = discord.Embed(
            title="✅ Avertissement retiré",
            description=f"L'avertissement **#{avertissement}** a été retiré de **{membre}**.",
            color=config.COLOR_SUCCESS,
        )
        embed.set_footer(text=f"Il lui en reste {total}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /clearwarns
    # ------------------------------------------------------------------
    @app_commands.command(name="clearwarns", description="[Marine] Efface TOUS les avertissements d'un membre.")
    @app_commands.describe(membre="Le membre dont il faut effacer le casier")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def clearwarns(self, interaction: discord.Interaction, membre: discord.Member):
        count = await db.clear_warnings(interaction.guild_id, membre.id)

        embed = discord.Embed(
            title="🧹 Casier effacé",
            description=f"**{count}** avertissement(s) de **{membre}** ont été supprimés.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /lock
    # ------------------------------------------------------------------
    @app_commands.command(name="lock", description="[Marine] Verrouille un salon (empêche l'envoi de messages).")
    @app_commands.describe(
        salon="Le salon à verrouiller (par défaut : le salon actuel)",
        raison="Raison du verrouillage",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def lock(
        self,
        interaction: discord.Interaction,
        salon: discord.TextChannel | None = None,
        raison: str = "Aucune raison fournie",
    ):
        channel = salon or interaction.channel

        if await db.get_lock_state(channel.id):
            embed = discord.Embed(
                title="🤔 Déjà verrouillé",
                description=f"{channel.mention} est déjà verrouillé. Utilise `/unlock` d'abord si tu veux changer la raison.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        everyone = interaction.guild.default_role
        overwrite = channel.overwrites_for(everyone)
        previous_value = overwrite.send_messages

        await db.save_lock_state(interaction.guild_id, channel.id, previous_value, interaction.user.id)

        overwrite.send_messages = False
        try:
            await channel.set_permissions(
                everyone, overwrite=overwrite, reason=f"Verrouillé par {interaction.user} : {raison}"
            )
        except discord.Forbidden:
            await db.remove_lock_state(channel.id)
            embed = discord.Embed(
                title="❌ Permission refusée",
                description="Je n'ai pas la permission de modifier les droits de ce salon.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🔒 Salon verrouillé",
            description=f"{channel.mention} a été verrouillé — personne ne peut plus y écrire.",
            color=config.COLOR_MARINE,
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.set_footer(text=f"Ordre exécuté par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

        if channel.id != interaction.channel.id:
            notice = discord.Embed(
                title="🔒 Ce salon a été verrouillé",
                description=raison,
                color=config.COLOR_MARINE,
            )
            try:
                await channel.send(embed=notice)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # /unlock
    # ------------------------------------------------------------------
    @app_commands.command(name="unlock", description="[Marine] Déverrouille un salon précédemment verrouillé.")
    @app_commands.describe(
        salon="Le salon à déverrouiller (par défaut : le salon actuel)",
        raison="Raison du déverrouillage",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(
        self,
        interaction: discord.Interaction,
        salon: discord.TextChannel | None = None,
        raison: str = "Aucune raison fournie",
    ):
        channel = salon or interaction.channel
        lock_state = await db.get_lock_state(channel.id)

        if lock_state is None:
            embed = discord.Embed(
                title="🤔 Pas verrouillé",
                description=f"{channel.mention} n'a pas été verrouillé via `/lock`.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        everyone = interaction.guild.default_role
        overwrite = channel.overwrites_for(everyone)
        overwrite.send_messages = lock_state["previous_send_messages"]

        try:
            if overwrite.is_empty():
                await channel.set_permissions(
                    everyone, overwrite=None, reason=f"Déverrouillé par {interaction.user} : {raison}"
                )
            else:
                await channel.set_permissions(
                    everyone, overwrite=overwrite, reason=f"Déverrouillé par {interaction.user} : {raison}"
                )
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission refusée",
                description="Je n'ai pas la permission de modifier les droits de ce salon.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.remove_lock_state(channel.id)

        embed = discord.Embed(
            title="🔓 Salon déverrouillé",
            description=f"{channel.mention} a été déverrouillé — l'état des permissions d'avant a été restauré.",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.set_footer(text=f"Ordre exécuté par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

        if channel.id != interaction.channel.id:
            notice = discord.Embed(
                title="🔓 Ce salon a été déverrouillé",
                description=raison,
                color=config.COLOR_SUCCESS,
            )
            try:
                await channel.send(embed=notice)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # /clear
    # ------------------------------------------------------------------
    @app_commands.command(name="clear", description="[Marine] Supprime un nombre de messages dans le salon.")
    @app_commands.describe(nombre="Nombre de messages à supprimer (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.default_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, nombre: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=nombre)

        embed = discord.Embed(
            title="🧹 Nettoyage effectué",
            description=f"**{len(deleted)}** messages ont été supprimés par ordre du Gouvernement Mondial.",
            color=config.COLOR_MARINE,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /timeout et /mute (alias)
    # ------------------------------------------------------------------
    async def _do_timeout(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        duree: str,
        raison: str,
    ):
        seconds = parse_duration(duree)
        if seconds is None:
            embed = discord.Embed(
                title="❌ Format de durée invalide",
                description=(
                    "Utilise un format comme `10m`, `1h`, `2d` ou `30s`.\n"
                    "Exemples : `30s` (30 secondes), `10m` (10 minutes), `1h` (1 heure), `2d` (2 jours)."
                ),
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if seconds > 28 * 24 * 60 * 60:  # limite Discord : 28 jours max
            embed = discord.Embed(
                title="❌ Durée trop longue",
                description="Discord limite les mises en sourdine à 28 jours maximum.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            await membre.timeout(discord.utils.utcnow() + timedelta(seconds=seconds), reason=raison)
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission refusée",
                description="Je n'ai pas la permission de mettre ce membre en sourdine.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await self._record_sanction(interaction, membre, "timeout", raison, seconds)

        embed = discord.Embed(
            title="🔇 Mis aux fers de la Marine",
            description=f"**{membre}** est réduit au silence pendant **{format_duration(seconds)}**.",
            color=config.COLOR_MARINE,
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.set_footer(text=f"Ordre exécuté par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="timeout", description="[Marine] Met un membre en sourdine temporairement.")
    @app_commands.describe(
        membre="Le membre à mettre en sourdine",
        duree="Durée (ex: 10m, 1h, 2d)",
        raison="Raison de la sanction",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        duree: str,
        raison: str = "Aucune raison fournie",
    ):
        await self._do_timeout(interaction, membre, duree, raison)

    @app_commands.command(name="mute", description="Alias de /timeout : met un membre en sourdine temporairement.")
    @app_commands.describe(
        membre="Le membre à mettre en sourdine",
        duree="Durée (ex: 10m, 1h, 2d)",
        raison="Raison de la sanction",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        duree: str,
        raison: str = "Aucune raison fournie",
    ):
        await self._do_timeout(interaction, membre, duree, raison)

    # ------------------------------------------------------------------
    # /unmute (et alias /untimeout)
    # ------------------------------------------------------------------
    async def _do_untimeout(self, interaction: discord.Interaction, membre: discord.Member, raison: str):
        if membre.timed_out_until is None:
            embed = discord.Embed(
                title="🤔 Pas en sourdine",
                description=f"**{membre}** n'est actuellement pas mis en sourdine.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            await membre.timeout(None, reason=f"{raison} — par {interaction.user}")
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission refusée",
                description="Je n'ai pas la permission de lever la sourdine de ce membre.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🔊 Sourdine levée",
            description=f"**{membre}** peut de nouveau parler et écrire normalement.",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="Raison", value=raison, inline=False)
        embed.set_footer(text=f"Ordre exécuté par {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unmute", description="[Marine] Lève la mise en sourdine d'un membre avant son terme.")
    @app_commands.describe(membre="Le membre à sortir de la sourdine", raison="Raison de la levée")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        raison: str = "Aucune raison fournie",
    ):
        await self._do_untimeout(interaction, membre, raison)

    @app_commands.command(name="untimeout", description="Alias de /unmute : lève la mise en sourdine d'un membre.")
    @app_commands.describe(membre="Le membre à sortir de la sourdine", raison="Raison de la levée")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        raison: str = "Aucune raison fournie",
    ):
        await self._do_untimeout(interaction, membre, raison)

    # ------------------------------------------------------------------
    # /modperms
    # ------------------------------------------------------------------
    @app_commands.command(name="modperms", description="[Marine] Vérifie les permissions de modération d'un membre.")
    @app_commands.describe(membre="Le membre à vérifier (toi par défaut)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def modperms(self, interaction: discord.Interaction, membre: discord.Member | None = None):
        target = membre or interaction.user
        perms = target.guild_permissions

        lines = []
        for attr, label in MOD_PERMISSIONS:
            if not getattr(perms, attr):
                lines.append(f"❌ {label}")
                continue

            granting_roles = [
                r.mention for r in target.roles
                if not r.is_default() and getattr(r.permissions, attr)
            ]
            if granting_roles:
                source = ", ".join(granting_roles)
            elif getattr(target.roles[-1].permissions, "administrator", False) is False and perms.administrator:
                source = "un rôle Administrateur"
            else:
                source = "@everyone"
            lines.append(f"✅ {label} — via {source}")

        embed = discord.Embed(
            title=f"🛡️ Permissions de modération de {target.display_name}",
            description="\n".join(lines),
            color=config.COLOR_MARINE,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"ID : {target.id}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /modroles
    # ------------------------------------------------------------------
    @app_commands.command(name="modroles", description="[Marine] Liste tous les rôles ayant des permissions de modération.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def modroles(self, interaction: discord.Interaction):
        entries = []
        for role in reversed(interaction.guild.roles):  # du plus élevé au plus bas dans la hiérarchie
            if role.is_default():
                continue
            granted = [label for attr, label in MOD_PERMISSIONS if getattr(role.permissions, attr)]
            if granted:
                entries.append((role, granted))

        if not entries:
            embed = discord.Embed(
                title="🛡️ Audit des rôles de modération",
                description="Aucun rôle (hors @everyone) n'a de permission de modération.",
                color=config.COLOR_MARINE,
            )
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(
            title="🛡️ Rôles avec des permissions de modération",
            description=f"{len(entries)} rôle(s) concerné(s), du plus élevé au plus bas dans la hiérarchie.",
            color=config.COLOR_MARINE,
        )
        for role, granted in entries[:25]:
            embed.add_field(name=f"@{role.name}", value="\n".join(granted), inline=True)

        if len(entries) > 25:
            embed.set_footer(text=f"+ {len(entries) - 25} autre(s) rôle(s) non affiché(s) (limite Discord)")

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Gestion des erreurs (permissions manquantes, etc.)
    # ------------------------------------------------------------------
    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="🚫 Accès refusé",
                description="Seuls les officiers de la Marine (administrateurs) peuvent faire ça.",
                color=config.COLOR_ERROR,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
