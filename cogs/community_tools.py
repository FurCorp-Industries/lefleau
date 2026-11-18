"""Giveaways persistants, protection anti-raid et transfert contrôlé de sanctions."""

import random
import asyncio
from collections import defaultdict, deque
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database as db
from utils.helpers import parse_duration, format_duration


GIVEAWAY_BUTTON_ID = "giveaway_enter"


async def giveaway_prize_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Propose les lots configurés pour le serveur courant."""
    if interaction.guild_id is None:
        return []
    items = await db.search_giveaway_prize_items(interaction.guild_id, current)
    return [
        app_commands.Choice(
            name=f"{item['emoji']} {item['name']} — {item['points']} pts"[:100],
            value=str(item["id"]),
        )
        for item in items
    ]


PROPOSAL_STATUS = {
    "pending": ("⏳ En attente de validation du staff", config.COLOR_ECONOMY),
    "approved": ("✅ Validée par le staff", config.COLOR_SUCCESS),
    "denied": ("❌ Refusée par le staff", config.COLOR_ERROR),
}


def build_proposal_status_embed(
    proposal: dict, point_name: str, status: str, reviewer: str | None = None,
    total: int | None = None, roles: list | None = None,
) -> discord.Embed:
    """Embed public de suivi d'une proposition de giveaway (affiché dans le ticket)."""
    label, color = PROPOSAL_STATUS[status]
    embed = discord.Embed(title=f"🎁 Proposition de giveaway #{proposal['id']}", color=color)
    embed.add_field(name="Organisateur", value=f"<@{proposal['proposer_id']}>", inline=True)
    embed.add_field(name="Lot proposé", value=proposal["prize_name"], inline=True)
    embed.add_field(name="Statut", value=label, inline=False)
    if proposal.get("duration_seconds"):
        embed.add_field(name="Configuration", value=(
            f"Salon : <#{proposal['target_channel_id']}> · "
            f"Durée : {format_duration(proposal['duration_seconds'])} · "
            f"Gagnants : {proposal['winner_count']}"), inline=False)
    points = proposal["prize_points"]
    if status == "approved":
        reward = f"**{points} {point_name}** attribués"
        if total is not None:
            reward += f" (total : **{total}**)"
        embed.add_field(name="Récompense", value=reward, inline=False)
        if roles:
            embed.add_field(name="Rôle(s) débloqué(s)", value=", ".join(role.mention for role in roles), inline=False)
        if proposal.get("published_message_id") and proposal.get("target_channel_id"):
            embed.add_field(name="Giveaway publié", value=(
                f"https://discord.com/channels/{proposal['guild_id']}/"
                f"{proposal['target_channel_id']}/{proposal['published_message_id']}"), inline=False)
        embed.set_footer(text="Giveaway public créé automatiquement.")
    elif status == "denied":
        embed.add_field(name="Récompense", value="Aucun point attribué.", inline=False)
    else:
        embed.add_field(name="Récompense", value=f"**{points} {point_name}** après validation", inline=False)
    if reviewer and status != "pending":
        embed.add_field(name="Décision de", value=reviewer, inline=False)
    return embed


async def update_proposal_status_message(
    guild: discord.Guild, proposal: dict, status: str, point_name: str,
    reviewer: str | None = None, total: int | None = None, roles: list | None = None,
) -> bool:
    """Met à jour l'embed de statut du ticket. Retourne False si le message est introuvable."""
    message_id = proposal.get("status_message_id")
    channel = guild.get_channel(proposal["ticket_channel_id"]) if guild else None
    if not message_id or not isinstance(channel, discord.abc.Messageable):
        return False
    try:
        message = await channel.fetch_message(message_id)
        await message.edit(embed=build_proposal_status_embed(proposal, point_name, status, reviewer, total, roles))
    except discord.HTTPException:
        return False
    return True


class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Participer", emoji="🎉", style=discord.ButtonStyle.success,
                       custom_id=GIVEAWAY_BUTTON_ID)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        giveaway = await db.get_giveaway(interaction.message.id)
        if giveaway is None or giveaway["ended"]:
            await interaction.response.send_message("Ce giveaway est terminé.", ephemeral=True)
            return

        member = interaction.user
        role_ids = {role.id for role in member.roles}
        bypass = giveaway["bypass_role_id"] in role_ids if giveaway["bypass_role_id"] else False

        if not bypass and giveaway["required_role_id"] and giveaway["required_role_id"] not in role_ids:
            role = interaction.guild.get_role(giveaway["required_role_id"])
            await interaction.response.send_message(
                f"Tu dois posséder le rôle {role.mention if role else 'requis'} pour participer.", ephemeral=True
            )
            return

        now = discord.utils.utcnow()
        if not bypass:
            account_age = (now - member.created_at).total_seconds()
            if account_age < giveaway["min_account_age_seconds"]:
                missing = giveaway["min_account_age_seconds"] - account_age
                await interaction.response.send_message(
                    f"Ton compte est trop récent. Il manque environ **{format_duration(missing)}**.", ephemeral=True
                )
                return
            if member.joined_at:
                membership = (now - member.joined_at).total_seconds()
                if membership < giveaway["min_membership_seconds"]:
                    missing = giveaway["min_membership_seconds"] - membership
                    await interaction.response.send_message(
                        f"Tu dois être sur le serveur depuis encore **{format_duration(missing)}**.", ephemeral=True
                    )
                    return

        added = await db.enter_giveaway(interaction.message.id, member.id)
        await interaction.response.send_message(
            "🎉 Participation enregistrée !" if added else "Tu participes déjà à ce giveaway.", ephemeral=True
        )


class GiveawayProposalReviewView(discord.ui.View):
    """Boutons persistants placés dans le salon de logs des tickets."""
    def __init__(self, cog: "CommunityTools", proposal_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.proposal_id = proposal_id
        approve = discord.ui.Button(
            label="Approve & publish", emoji="✅", style=discord.ButtonStyle.success,
            custom_id=f"giveaway_proposal:approve:{proposal_id}",
        )
        deny = discord.ui.Button(
            label="Refuser", emoji="❌", style=discord.ButtonStyle.danger,
            custom_id=f"giveaway_proposal:deny:{proposal_id}",
        )
        approve.callback = self.approve
        deny.callback = self.deny
        self.add_item(approve)
        self.add_item(deny)

    async def approve(self, interaction: discord.Interaction):
        await self.cog.review_giveaway_proposal(interaction, self.proposal_id, approved=True)

    async def deny(self, interaction: discord.Interaction):
        await self.cog.review_giveaway_proposal(interaction, self.proposal_id, approved=False)


class CommunityTools(commands.Cog):

    giveaways = app_commands.Group(name="giveaways", description="Création et gestion des giveaways", guild_only=True)
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent_joins: dict[int, deque[tuple[float, discord.Member]]] = defaultdict(deque)
        self._proposal_locks: dict[int, asyncio.Lock] = {}
        self.bot.add_view(GiveawayView())
        self.giveaway_watcher.start()

    async def cog_load(self):
        # Réenregistre les boutons des propositions toujours en attente après un redémarrage.
        for proposal in await db.get_pending_giveaway_proposals():
            self.bot.add_view(
                GiveawayProposalReviewView(self, proposal["id"]),
                message_id=proposal["log_message_id"],
            )

    async def cog_unload(self):
        self.giveaway_watcher.cancel()

    @staticmethod
    def _duration(value: str, allow_zero: bool = True) -> int | None:
        if allow_zero and value.strip() in {"0", "aucune", "non"}:
            return 0
        return parse_duration(value)

    @staticmethod
    def _role_problem(interaction: discord.Interaction, role: discord.Role) -> str | None:
        guild = interaction.guild
        bot_member = guild.me
        if role.is_default() or role.managed:
            return "Ce rôle ne peut pas être utilisé pour les récompenses de points."
        if bot_member is None or not bot_member.guild_permissions.manage_roles:
            return "Le bot doit posséder la permission **Gérer les rôles**."
        if role >= bot_member.top_role:
            return "Le rôle choisi doit être placé sous le rôle le plus élevé du bot."
        if guild.owner_id != interaction.user.id and role >= interaction.user.top_role:
            return "Tu ne peux pas configurer un rôle égal ou supérieur à ton rôle principal."
        return None

    async def _grant_point_roles(self, member: discord.Member, points: int) -> list[discord.Role]:
        """Ajoute les rôles dont les seuils sont atteints. Ne retire jamais un rôle acquis."""
        granted = []
        for reward in await db.get_giveaway_point_roles(member.guild.id):
            if points < reward["points_required"]:
                continue
            role = member.guild.get_role(reward["role_id"])
            if role is None or role in member.roles:
                continue
            try:
                await member.add_roles(
                    role,
                    reason=f"Seuil de points giveaway atteint : {points}",
                )
                granted.append(role)
            except (discord.Forbidden, discord.HTTPException):
                continue
        return granted

    @giveaways.command(name="create", description="[Admin] Crée un giveaway.")
    @app_commands.describe(
        lot="Lot à faire gagner", duree="Durée : 30m, 2h, 3d...", salon="Salon du giveaway",
        gagnants="Nombre de gagnants", role_requis="Rôle obligatoire",
        role_bypass="Rôle qui contourne toutes les conditions",
        age_compte="Âge minimal du compte (ex: 7d, 0)",
        anciennete_serveur="Ancienneté minimale sur le serveur (ex: 3d, 0)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway(self, interaction: discord.Interaction, lot: str, duree: str,
                       salon: discord.TextChannel | None = None,
                       gagnants: app_commands.Range[int, 1, 20] = 1,
                       role_requis: discord.Role | None = None,
                       role_bypass: discord.Role | None = None,
                       age_compte: str = "0", anciennete_serveur: str = "0"):
        seconds = self._duration(duree, allow_zero=False)
        account_age = self._duration(age_compte)
        membership = self._duration(anciennete_serveur)
        if not seconds or account_age is None or membership is None:
            await interaction.response.send_message(
                "Durée invalide. Utilise par exemple `30m`, `2h`, `3d`, ou `0` pour désactiver une condition.",
                ephemeral=True,
            )
            return

        target = salon or interaction.channel
        ends_at = discord.utils.utcnow().timestamp() + seconds
        conditions = []
        if role_requis:
            conditions.append(f"Rôle requis : {role_requis.mention}")
        if account_age:
            conditions.append(f"Âge minimal du compte : {format_duration(account_age)}")
        if membership:
            conditions.append(f"Présence minimale : {format_duration(membership)}")
        if role_bypass:
            conditions.append(f"Contournement : {role_bypass.mention}")

        embed = discord.Embed(title="🎉 GIVEAWAY", description=f"## {lot[:200]}", color=config.COLOR_SUCCESS)
        embed.add_field(name="Fin", value=f"<t:{int(ends_at)}:R>", inline=True)
        embed.add_field(name="Gagnant(s)", value=str(gagnants), inline=True)
        embed.add_field(name="Conditions", value="\n".join(conditions) if conditions else "Aucune", inline=False)
        embed.set_footer(text=f"Organisé par {interaction.user.display_name}")
        try:
            message = await target.send(embed=embed, view=GiveawayView())
        except discord.Forbidden:
            await interaction.response.send_message("Je ne peux pas écrire dans ce salon.", ephemeral=True)
            return

        await db.create_giveaway({
            "message_id": message.id, "guild_id": interaction.guild_id, "channel_id": target.id,
            "prize": lot[:200], "winner_count": gagnants,
            "ends_at": datetime.fromtimestamp(ends_at, timezone.utc).isoformat(),
            "required_role_id": role_requis.id if role_requis else None,
            "bypass_role_id": role_bypass.id if role_bypass else None,
            "min_account_age_seconds": account_age, "min_membership_seconds": membership,
            "host_id": interaction.user.id,
            "prize_item_id": None, "prize_points": 0,
        })
        await interaction.response.send_message(f"Giveaway créé : {message.jump_url}", ephemeral=True)

    # Commandes regroupées pour économiser des emplacements (limite Discord : 100).
    points = app_commands.Group(
        name="points", description="Consulte les points de giveaway.", guild_only=True,
    )
    points_admin = app_commands.Group(
        name="points-admin", description="[Admin] Gère les points de giveaway.", guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @points_admin.command(name="config", description="[Admin] Définit le nom des points de giveaway.")
    @app_commands.describe(nom="Exemples : Tickets, Étoiles, Crédits")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def points_config(self, interaction: discord.Interaction, nom: str):
        name = nom.strip()
        if not 1 <= len(name) <= 32:
            await interaction.response.send_message("Le nom doit contenir entre 1 et 32 caractères.", ephemeral=True)
            return
        await db.set_giveaway_points_name(interaction.guild_id, name)
        await interaction.response.send_message(f"✅ Les points s'appellent maintenant **{name}**.", ephemeral=True)

    @points_admin.command(name="item-add", description="[Admin] Ajoute un lot sélectionnable pour les giveaways.")
    @app_commands.describe(nom="Nom du lot", points="Points attribués à l'organisateur après validation", emoji="Emoji facultatif")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def points_item_add(self, interaction: discord.Interaction, nom: str,
                              points: app_commands.Range[int, 1, 1_000_000], emoji: str = "🎁"):
        name = nom.strip()
        if not 1 <= len(name) <= 80:
            await interaction.response.send_message("Le nom du lot doit contenir entre 1 et 80 caractères.", ephemeral=True)
            return
        item = await db.upsert_giveaway_prize_item(interaction.guild_id, name, points, emoji[:32], interaction.user.id)
        point_name = await db.get_giveaway_points_name(interaction.guild_id)
        await interaction.response.send_message(
            f"✅ Lot configuré : {item['emoji']} **{item['name']}** — **{item['points']} {point_name}** "
            "pour l'organisateur, après validation du staff.",
            ephemeral=True,
        )

    @points_admin.command(name="item-list", description="[Admin] Liste les lots configurés pour les giveaways.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def points_item_list(self, interaction: discord.Interaction):
        items = await db.get_giveaway_prize_items(interaction.guild_id, include_inactive=True)
        point_name = await db.get_giveaway_points_name(interaction.guild_id)
        if not items:
            await interaction.response.send_message("Aucun lot configuré. Utilise `/points-admin item-add`.", ephemeral=True)
            return
        lines = [
            f"**#{item['id']}** {item['emoji']} **{item['name']}** — {item['points']} {point_name}"
            f"{' *(désactivé)*' if not item['active'] else ''}"
            for item in items
        ]
        await interaction.response.send_message(
            embed=discord.Embed(title="🎁 Lots de giveaway", description="\n".join(lines)[:4096], color=config.COLOR_SUCCESS),
            ephemeral=True,
        )

    @points_admin.command(name="item-remove", description="[Admin] Retire un lot de la liste des giveaways.")
    @app_commands.describe(item_id="Identifiant affiché par /points-admin item-list")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def points_item_remove(self, interaction: discord.Interaction, item_id: int):
        removed = await db.deactivate_giveaway_prize_item(interaction.guild_id, item_id)
        await interaction.response.send_message(
            "✅ Lot retiré de la liste." if removed else "Lot introuvable.", ephemeral=True
        )

    @points_admin.command(name="role-add", description="[Admin] Ajoute un rôle attribué à un seuil de points.")
    @app_commands.describe(role="Rôle à attribuer", points="Nombre de points requis")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def points_role_add(self, interaction: discord.Interaction, role: discord.Role,
                              points: app_commands.Range[int, 1, 1_000_000]):
        problem = self._role_problem(interaction, role)
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await db.add_giveaway_point_role(interaction.guild_id, role.id, points, interaction.user.id)
        point_name = await db.get_giveaway_points_name(interaction.guild_id)
        granted = 0
        for balance in await db.get_giveaway_member_point_balances(interaction.guild_id):
            if balance["points"] < points:
                continue
            member = interaction.guild.get_member(balance["user_id"])
            if member and role not in member.roles:
                if role in await self._grant_point_roles(member, balance["points"]):
                    granted += 1
        await interaction.followup.send(
            f"✅ {role.mention} sera ajouté automatiquement à partir de **{points} {point_name}**. "
            f"Synchronisation : **{granted}** rôle(s) ajouté(s).", ephemeral=True
        )

    @points_admin.command(name="role-remove", description="[Admin] Retire une règle de rôle liée aux points.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def points_role_remove(self, interaction: discord.Interaction, role: discord.Role):
        removed = await db.remove_giveaway_point_role(interaction.guild_id, role.id)
        await interaction.response.send_message(
            "✅ Règle de rôle supprimée." if removed else "Ce rôle n'a pas de seuil configuré.", ephemeral=True
        )

    @points.command(name="roles", description="Affiche les rôles déblocables par points.")
    async def points_role_list(self, interaction: discord.Interaction):
        rewards = await db.get_giveaway_point_roles(interaction.guild_id)
        point_name = await db.get_giveaway_points_name(interaction.guild_id)
        if not rewards:
            await interaction.response.send_message("Aucun rôle de points n'est configuré.", ephemeral=True)
            return
        lines = []
        for reward in rewards:
            role = interaction.guild.get_role(reward["role_id"])
            role_label = role.mention if role else f"Rôle supprimé (`{reward['role_id']}`)"
            lines.append(f"{role_label} — **{reward['points_required']} {point_name}**")
        await interaction.response.send_message(
            embed=discord.Embed(title="🏆 Rôles de points", description="\n".join(lines), color=config.COLOR_SUCCESS),
            ephemeral=True,
        )

    @points.command(name="profile", description="Affiche les points giveaway et les rôles débloqués d'un membre.")
    async def points_profile(self, interaction: discord.Interaction, membre: discord.Member | None = None):
        member = membre or interaction.user
        points = await db.get_giveaway_member_points(interaction.guild_id, member.id)
        point_name = await db.get_giveaway_points_name(interaction.guild_id)
        rewards = await db.get_giveaway_point_roles(interaction.guild_id)
        unlocked = []
        future = []
        for reward in rewards:
            role = interaction.guild.get_role(reward["role_id"])
            if role is None:
                continue
            if role in member.roles:
                unlocked.append(role.mention)
            else:
                missing = max(0, reward["points_required"] - points)
                suffix = f"{missing} restant(s)" if missing else "en attente de synchronisation"
                future.append(f"{role.mention} ({suffix})")
        embed = discord.Embed(title=f"🏆 Points de {member.display_name}", color=config.COLOR_SUCCESS)
        embed.add_field(name=point_name, value=f"**{points}**", inline=False)
        embed.add_field(name="Rôles de points débloqués", value=", ".join(unlocked) or "Aucun", inline=False)
        if future:
            embed.add_field(name="Prochains rôles", value="\n".join(future)[:1024], inline=False)
        await interaction.response.send_message(embed=embed)

    @points_admin.command(name="add", description="[Admin] Ajoute manuellement des points à un membre.")
    @app_commands.describe(membre="Membre à créditer", points="Nombre de points à ajouter")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def points_add(self, interaction: discord.Interaction, membre: discord.Member,
                         points: app_commands.Range[int, 1, 1_000_000]):
        total = await db.add_giveaway_member_points(interaction.guild_id, membre.id, points)
        roles = await self._grant_point_roles(membre, total)
        point_name = await db.get_giveaway_points_name(interaction.guild_id)
        extra = f" Rôle(s) ajouté(s) : {', '.join(role.mention for role in roles)}." if roles else ""
        await interaction.response.send_message(
            f"✅ {membre.mention} reçoit **{points} {point_name}** (total : **{total}**).{extra}",
            ephemeral=True,
        )

    @giveaways.command(name="propose", description="Propose a complete giveaway from your ticket.")
    @app_commands.describe(
        prize="Configured prize", duration="Duration: 30m, 2h, 3d",
        channel="Public channel where the giveaway will be published",
        winners="Number of winners (1-20)", required_role="Required role (optional)",
        bypass_role="Role bypassing all participation conditions (optional)",
        account_age="Minimum Discord account age: 7d or 0",
        server_age="Minimum server membership: 3d or 0",
    )
    @app_commands.autocomplete(prize=giveaway_prize_autocomplete)
    async def giveaway_propose(self, interaction: discord.Interaction, prize: str,
                               duration: str, channel: discord.TextChannel,
                               winners: app_commands.Range[int, 1, 20] = 1,
                               required_role: discord.Role | None = None,
                               bypass_role: discord.Role | None = None,
                               account_age: str = "0", server_age: str = "0"):
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Cette commande doit être utilisée sur un serveur.", ephemeral=True)
            return
        ticket = await db.get_ticket_by_channel(interaction.channel.id)
        if ticket is None or ticket["guild_id"] != interaction.guild_id:
            await interaction.response.send_message("Utilise cette commande depuis un ticket ouvert.", ephemeral=True)
            return
        if ticket["user_id"] != interaction.user.id:
            await interaction.response.send_message("Seul le créateur du ticket peut proposer un giveaway.", ephemeral=True)
            return
        if await db.get_pending_giveaway_proposal_for_ticket(interaction.channel.id):
            await interaction.response.send_message("Une proposition est déjà en attente dans ce ticket.", ephemeral=True)
            return
        seconds = self._duration(duration, allow_zero=False)
        account_age = self._duration(account_age)
        membership = self._duration(server_age)
        if (not seconds or seconds < 60 or seconds > 30 * 86400 or
                account_age is None or membership is None or account_age < 0 or membership < 0):
            await interaction.response.send_message(
                "Durée invalide (1m à 30d). Pour les conditions, utilise `7d`, `3d` ou `0`.", ephemeral=True)
            return
        bot_member = interaction.guild.me
        permissions = channel.permissions_for(bot_member) if bot_member else None
        if not permissions or not permissions.send_messages or not permissions.embed_links or not permissions.view_channel:
            await interaction.response.send_message(
                "Le bot doit pouvoir voir le channel, envoyer des messages et intégrer des liens.", ephemeral=True)
            return
        try:
            item = await db.get_giveaway_prize_item(interaction.guild_id, int(prize))
        except ValueError:
            item = None
        if item is None:
            await interaction.response.send_message("Choisis un prize existant dans la liste proposée.", ephemeral=True)
            return
        log_channel_id = await db.get_ticket_log_channel(interaction.guild_id)
        log_channel = interaction.guild.get_channel(log_channel_id) if log_channel_id else None
        if not isinstance(log_channel, discord.TextChannel):
            await interaction.response.send_message(
                "Les logs de tickets ne sont pas configurés.", ephemeral=True)
            return
        data = {
            "guild_id": interaction.guild_id, "ticket_channel_id": interaction.channel.id,
            "proposer_id": interaction.user.id, "prize_item_id": item["id"],
            "prize_name": f"{item['emoji']} {item['name']}", "prize_points": item["points"],
            "duration_seconds": seconds, "target_channel_id": channel.id,
            "winner_count": winners, "required_role_id": required_role.id if required_role else None,
            "bypass_role_id": bypass_role.id if bypass_role else None,
            "min_account_age_seconds": account_age, "min_membership_seconds": membership,
        }
        try:
            proposal_id = await db.create_giveaway_proposal(data)
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                await interaction.response.send_message("Une proposition est déjà en attente dans ce ticket.", ephemeral=True)
                return
            raise
        proposal = {**data, "id": proposal_id}
        point_name = await db.get_giveaway_points_name(interaction.guild_id)
        embed = build_proposal_status_embed(proposal, point_name, "pending")
        embed.add_field(name="Ticket", value=interaction.channel.mention, inline=True)
        embed.add_field(name="Rôle requis", value=required_role.mention if required_role else "Aucun", inline=True)
        embed.add_field(name="Rôle bypass", value=bypass_role.mention if bypass_role else "Aucun", inline=True)
        embed.add_field(name="Ancienneté du compte", value=format_duration(account_age), inline=True)
        embed.add_field(name="Ancienneté sur le serveur", value=format_duration(membership), inline=True)
        embed.add_field(name="Action du staff", value="Approve & publish lance automatiquement le giveaway public et attribue les points.", inline=False)
        try:
            message = await log_channel.send(embed=embed, view=GiveawayProposalReviewView(self, proposal_id))
        except discord.HTTPException:
            await db.delete_giveaway_proposal(proposal_id)
            await interaction.response.send_message("Impossible d'envoyer la proposition dans les logs.", ephemeral=True)
            return
        await db.set_giveaway_proposal_log(proposal_id, log_channel.id, message.id)
        self.bot.add_view(GiveawayProposalReviewView(self, proposal_id), message_id=message.id)
        await interaction.response.send_message(embed=build_proposal_status_embed(proposal, point_name, "pending"))
        try:
            status_message = await interaction.original_response()
            await db.set_giveaway_proposal_status_message(proposal_id, status_message.id)
        except discord.HTTPException:
            pass

    async def process_giveaway_proposal(self, guild: discord.Guild, proposal_id: int,
                                        reviewer_id: int, approved: bool) -> str:
        """Point d'entrée unique pour boutons, slash et panel web ; protection double clic."""
        lock = self._proposal_locks.setdefault(proposal_id, asyncio.Lock())
        async with lock:
            proposal = await db.get_giveaway_proposal(proposal_id)
            if not proposal or proposal["guild_id"] != guild.id:
                raise ValueError("Proposition introuvable.")
            if proposal["status"] != "pending":
                raise ValueError("Cette proposition a déjà été traitée.")
            published = None
            if approved:
                if not proposal.get("duration_seconds") or not proposal.get("target_channel_id"):
                    raise ValueError("Ancienne proposition sans configuration de publication : crée une nouvelle proposition.")
                target = guild.get_channel(proposal["target_channel_id"])
                if not isinstance(target, discord.TextChannel):
                    raise ValueError("Le salon de publication n'existe plus.")
                bot_member = guild.me
                perms = target.permissions_for(bot_member) if bot_member else None
                if not perms or not (perms.view_channel and perms.send_messages and perms.embed_links):
                    raise ValueError("Le bot ne peut pas publier dans le salon demandé.")
                seconds = proposal["duration_seconds"]
                if not 60 <= seconds <= 30 * 86400 or not 1 <= proposal["winner_count"] <= 20:
                    raise ValueError("Les paramètres de durée ou de gagnants sont invalides.")
                ends_at = discord.utils.utcnow().timestamp() + seconds
                conditions = []
                if proposal["required_role_id"]:
                    conditions.append(f"Rôle requis : <@&{proposal['required_role_id']}>")
                if proposal["min_account_age_seconds"]:
                    conditions.append(f"Âge minimal du compte : {format_duration(proposal['min_account_age_seconds'])}")
                if proposal["min_membership_seconds"]:
                    conditions.append(f"Présence minimale : {format_duration(proposal['min_membership_seconds'])}")
                if proposal["bypass_role_id"]:
                    conditions.append(f"Contournement : <@&{proposal['bypass_role_id']}>")
                embed = discord.Embed(
                    title="🎉 GIVEAWAY", description=f"## {proposal['prize_name'][:200]}",
                    color=config.COLOR_SUCCESS)
                embed.add_field(name="Fin", value=f"<t:{int(ends_at)}:R>", inline=True)
                embed.add_field(name="Gagnant(s)", value=str(proposal["winner_count"]), inline=True)
                embed.add_field(name="Conditions", value="\n".join(conditions) or "Aucune", inline=False)
                embed.set_footer(text=f"Organisé par le membre {proposal['proposer_id']}")
                try:
                    published = await target.send(embed=embed, view=GiveawayView(),
                                                  allowed_mentions=discord.AllowedMentions.none())
                    saved = await db.approve_published_giveaway_proposal(
                        proposal_id, guild.id, reviewer_id, published.id, {
                            "channel_id": target.id, "prize": proposal["prize_name"][:200],
                            "winner_count": proposal["winner_count"],
                            "ends_at": datetime.fromtimestamp(ends_at, timezone.utc).isoformat(),
                            "required_role_id": proposal["required_role_id"],
                            "bypass_role_id": proposal["bypass_role_id"],
                            "min_account_age_seconds": proposal["min_account_age_seconds"],
                            "min_membership_seconds": proposal["min_membership_seconds"],
                            "host_id": proposal["proposer_id"],
                            "prize_item_id": proposal["prize_item_id"], "prize_points": 0,
                        })
                    if not saved:
                        raise ValueError("Cette proposition a déjà été traitée.")
                except Exception:
                    if published is not None:
                        try:
                            await published.delete()
                        except discord.HTTPException:
                            pass
                    raise
            else:
                if not await db.review_giveaway_proposal(proposal_id, guild.id, "denied", reviewer_id):
                    raise ValueError("Cette proposition a déjà été traitée.")
            proposal = await db.get_giveaway_proposal(proposal_id)
            point_name = await db.get_giveaway_points_name(guild.id)
            total = None
            roles = []
            if approved:
                total = await db.award_giveaway_points(
                    proposal["log_message_id"] or -proposal_id, guild.id,
                    proposal["proposer_id"], proposal["prize_points"])
                member = guild.get_member(proposal["proposer_id"])
                roles = await self._grant_point_roles(member, total) if member and total is not None else []
                details = (f"✅ Approuvé par <@{reviewer_id}>. Giveaway publié : {published.jump_url}\n"
                           f"<@{proposal['proposer_id']}> reçoit **{proposal['prize_points']} {point_name}**"
                           f" (total : **{total}**).")
                color = config.COLOR_SUCCESS
            else:
                details = f"❌ Refusé par <@{reviewer_id}>. Aucun point attribué."
                color = config.COLOR_ERROR
            channel = guild.get_channel(proposal["log_channel_id"]) if proposal["log_channel_id"] else None
            if isinstance(channel, discord.TextChannel) and proposal["log_message_id"]:
                try:
                    msg = await channel.fetch_message(proposal["log_message_id"])
                    log_embed = msg.embeds[0].copy() if msg.embeds else discord.Embed()
                    log_embed.color = color
                    log_embed.add_field(name="Décision", value=details[:1024], inline=False)
                    await msg.edit(embed=log_embed, view=None)
                except discord.HTTPException:
                    pass
            try:
                await update_proposal_status_message(guild, proposal,
                    "approved" if approved else "denied", point_name,
                    reviewer=f"<@{reviewer_id}>", total=total, roles=roles)
            except discord.HTTPException:
                pass
            return details

    async def review_giveaway_proposal(self, interaction: discord.Interaction,
                                       proposal_id: int, approved: bool):
        if interaction.guild is None or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Tu dois avoir la permission Gérer le serveur.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            details = await self.process_giveaway_proposal(
                interaction.guild, proposal_id, interaction.user.id, approved)
        except (ValueError, discord.HTTPException) as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
        else:
            await interaction.followup.send(details, ephemeral=True)

    @giveaways.command(name="proposal-approve", description="[Admin] Valide une proposition de giveaway.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_proposal_approve(self, interaction: discord.Interaction, proposition_id: int):
        await self.review_giveaway_proposal(interaction, proposition_id, approved=True)

    @giveaways.command(name="proposal-deny", description="[Admin] Refuse une proposition de giveaway.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_proposal_deny(self, interaction: discord.Interaction, proposition_id: int):
        await self.review_giveaway_proposal(interaction, proposition_id, approved=False)

    @tasks.loop(seconds=15)
    async def giveaway_watcher(self):
        now = datetime.now(timezone.utc)
        for giveaway in await db.get_active_giveaways():
            if datetime.fromisoformat(giveaway["ends_at"]) <= now:
                await self._finish_giveaway(giveaway)

    @giveaway_watcher.before_loop
    async def before_giveaway_watcher(self):
        await self.bot.wait_until_ready()

    async def _finish_giveaway(self, giveaway: dict):
        # Marque d'abord terminé pour rendre le tirage idempotent.
        await db.end_giveaway(giveaway["message_id"])
        guild = self.bot.get_guild(giveaway["guild_id"])
        channel = guild.get_channel(giveaway["channel_id"]) if guild else None
        if channel is None:
            return
        entries = await db.get_giveaway_entries(giveaway["message_id"])
        valid = [uid for uid in entries if guild.get_member(uid) is not None]
        count = min(giveaway["winner_count"], len(valid))
        winners = random.sample(valid, count) if count else []
        mentions = ", ".join(f"<@{uid}>" for uid in winners) if winners else "Aucun participant valide"
        try:
            message = await channel.fetch_message(giveaway["message_id"])
            embed = discord.Embed(title="🎉 GIVEAWAY TERMINÉ", description=f"## {giveaway['prize']}",
                                  color=discord.Color.gold())
            embed.add_field(name="Gagnant(s)", value=mentions, inline=False)
            await message.edit(embed=embed, view=None)
            announcement = f"🎊 {mentions} — vous remportez **{giveaway['prize']}** !"
            await channel.send(announcement)
        except discord.HTTPException:
            pass

    @giveaways.command(name="end", description="[Admin] Termine immédiatement un giveaway.")
    @app_commands.describe(message_id="ID du message du giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_end(self, interaction: discord.Interaction, message_id: str):
        try:
            giveaway = await db.get_giveaway(int(message_id))
        except ValueError:
            giveaway = None
        if giveaway is None or giveaway["guild_id"] != interaction.guild_id or giveaway["ended"]:
            await interaction.response.send_message("Giveaway actif introuvable.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self._finish_giveaway(giveaway)
        await interaction.followup.send("Giveaway terminé et gagnant(s) tiré(s).", ephemeral=True)

    @giveaways.command(name="reroll", description="[Admin] Effectue un nouveau tirage parmi les participants.")
    @app_commands.describe(message_id="ID du message du giveaway", gagnants="Nombre de nouveaux gagnants")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_reroll(self, interaction: discord.Interaction, message_id: str,
                              gagnants: app_commands.Range[int, 1, 20] = 1):
        try:
            giveaway = await db.get_giveaway(int(message_id))
        except ValueError:
            giveaway = None
        if giveaway is None or giveaway["guild_id"] != interaction.guild_id:
            await interaction.response.send_message("Giveaway introuvable sur ce serveur.", ephemeral=True)
            return
        entries = await db.get_giveaway_entries(giveaway["message_id"])
        valid = [uid for uid in entries if interaction.guild.get_member(uid) is not None]
        if not valid:
            await interaction.response.send_message("Aucun participant valide.", ephemeral=True)
            return
        winners = random.sample(valid, min(gagnants, len(valid)))
        mentions = ", ".join(f"<@{uid}>" for uid in winners)
        await interaction.response.send_message(
            f"🔁 Nouveau tirage pour **{giveaway['prize']}** : {mentions}"
        )

    @app_commands.command(name="antiraid-config", description="[Admin] Configure la protection contre les raids de comptes récents.")
    @app_commands.describe(active="Active ou désactive", seuil="Arrivées déclenchant l'alerte",
                           fenetre="Fenêtre de détection (ex: 10s)", age_minimum="Âge minimal du compte (ex: 7d)",
                           salon_logs="Salon des alertes", role_bypass="Rôle jamais sanctionné")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def antiraid_config(self, interaction: discord.Interaction, active: bool,
                              seuil: app_commands.Range[int, 3, 50] = 6, fenetre: str = "10s",
                              age_minimum: str = "7d", salon_logs: discord.TextChannel | None = None,
                              role_bypass: discord.Role | None = None):
        window = parse_duration(fenetre)
        min_age = parse_duration(age_minimum)
        if not window or min_age is None:
            await interaction.response.send_message("Durée invalide (`10s`, `5m`, `7d`...).", ephemeral=True)
            return
        await db.set_antiraid_settings(interaction.guild_id, active, seuil, window, min_age,
                                       salon_logs.id if salon_logs else None,
                                       role_bypass.id if role_bypass else None)
        await interaction.response.send_message(
            f"Protection anti-raid **{'activée' if active else 'désactivée'}** : {seuil} arrivées en "
            f"{format_duration(window)}, comptes de moins de {format_duration(min_age)} sanctionnés.", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await db.get_antiraid_settings(member.guild.id)
        if not settings or not settings["enabled"]:
            return
        now = discord.utils.utcnow().timestamp()
        queue = self.recent_joins[member.guild.id]
        queue.append((now, member))
        while queue and now - queue[0][0] > settings["window_seconds"]:
            queue.popleft()
        if len(queue) < settings["join_threshold"]:
            return

        candidates = list(queue)
        queue.clear()
        banned = []
        for _, target in candidates:
            if settings["bypass_role_id"] and any(r.id == settings["bypass_role_id"] for r in target.roles):
                continue
            age = (discord.utils.utcnow() - target.created_at).total_seconds()
            if age >= settings["min_account_age_seconds"]:
                continue
            try:
                await member.guild.ban(target, reason="Anti-raid : arrivée massive de comptes récents")
                banned.append(f"{target} (`{target.id}`)")
                await self.record_sanction(
                    member.guild, target, "antiraid", None,
                    "Arrivée massive de comptes récents détectée par l'anti-raid",
                )
            except discord.Forbidden:
                pass
        log_channel = member.guild.get_channel(settings["log_channel_id"]) if settings["log_channel_id"] else None
        if log_channel:
            embed = discord.Embed(title="🚨 Raid détecté", color=config.COLOR_ERROR,
                                  description=f"{len(candidates)} arrivées rapides détectées.\n"
                                              f"{len(banned)} compte(s) récent(s) banni(s).")
            if banned:
                embed.add_field(name="Comptes sanctionnés", value="\n".join(banned)[:1024], inline=False)
            await log_channel.send(embed=embed)

    async def record_sanction(self, guild: discord.Guild, member: discord.abc.User,
                              sanction_type: str, moderator: discord.abc.User | None,
                              reason: str, duration_seconds: int | None = None):
        """Enregistre une sanction et l'envoie au salon central configuré, sans la reproduire ailleurs."""
        record_id = await db.add_sanction_record(
            guild.id, member.id, str(member), getattr(member, "display_name", member.name),
            sanction_type, moderator.id if moderator else None, str(moderator) if moderator else None,
            reason, duration_seconds,
        )
        settings = await db.get_sanction_log(guild.id)
        if not settings:
            return record_id
        destination_guild = self.bot.get_guild(settings["destination_guild_id"])
        channel = destination_guild.get_channel(settings["destination_channel_id"]) if destination_guild else None
        if channel is None:
            return record_id
        labels = {"ban": "🔨 Bannissement", "warn": "⚠️ Avertissement",
                  "timeout": "🔇 Timeout", "kick": "👢 Expulsion", "antiraid": "🚨 Anti-raid"}
        embed = discord.Embed(title=labels.get(sanction_type, f"⚖️ {sanction_type}"),
                              color=config.COLOR_ERROR, timestamp=discord.utils.utcnow())
        embed.add_field(name="Membre", value=f"{member} (`{member.id}`)", inline=False)
        embed.add_field(name="Serveur d'origine", value=f"{guild.name} (`{guild.id}`)", inline=False)
        embed.add_field(name="Modérateur", value=str(moderator) if moderator else "Automatique", inline=True)
        if duration_seconds:
            embed.add_field(name="Durée", value=format_duration(duration_seconds), inline=True)
        embed.add_field(name="Raison", value=reason[:1024], inline=False)
        embed.set_footer(text=f"Sanction #{record_id}")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass
        return record_id

    @app_commands.command(name="sanctions-log-config", description="[Admin] Configure le salon central recevant les sanctions.")
    @app_commands.describe(active="Active ou désactive les logs", serveur_destination="ID du serveur du salon",
                           salon_destination="ID du salon de logs")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def sanctions_log_config(self, interaction: discord.Interaction, active: bool,
                                   serveur_destination: str | None = None,
                                   salon_destination: str | None = None):
        if not active:
            await db.disable_sanction_log(interaction.guild_id)
            await interaction.response.send_message("Logs centralisés désactivés.", ephemeral=True)
            return
        try:
            target_id = int(serveur_destination)
            channel_id = int(salon_destination)
        except (TypeError, ValueError):
            await interaction.response.send_message("Indique les ID valides du serveur et du salon.", ephemeral=True)
            return
        target = self.bot.get_guild(target_id)
        target_member = target.get_member(interaction.user.id) if target else None
        if target is None or target_member is None or not target_member.guild_permissions.administrator:
            await interaction.response.send_message(
                "Le bot doit être sur le serveur cible et tu dois y être administrateur.", ephemeral=True
            )
            return
        channel = target.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Salon texte introuvable sur le serveur cible.", ephemeral=True)
            return
        await db.set_sanction_log(interaction.guild_id, target.id, channel.id)
        await interaction.response.send_message(
            f"Les nouvelles sanctions de **{interaction.guild.name}** seront journalisées dans "
            f"**{target.name}** → {channel.mention}. Elles ne seront pas appliquées sur ce serveur.", ephemeral=True
        )

    @app_commands.command(name="sanctions-search", description="[Staff] Recherche les sanctions provenant d'un serveur choisi.")
    @app_commands.describe(utilisateur="Pseudo, nom affiché, mention ou ID Discord",
                           serveur_origine="ID du serveur d'origine des sanctions")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.default_permissions(moderate_members=True)
    async def sanctions_search(self, interaction: discord.Interaction, utilisateur: str,
                               serveur_origine: str):
        try:
            source_id = int(serveur_origine.strip())
            if source_id <= 0:
                raise ValueError
        except (AttributeError, ValueError):
            await interaction.response.send_message(
                "L'ID du serveur d'origine est invalide.", ephemeral=True
            )
            return

        source_guild = self.bot.get_guild(source_id)
        if source_guild is None:
            await interaction.response.send_message(
                "Le bot n'est pas présent sur ce serveur d'origine.", ephemeral=True
            )
            return

        source_member = source_guild.get_member(interaction.user.id)
        source_staff = bool(
            source_member and
            (source_member.guild_permissions.moderate_members or
             source_member.guild_permissions.administrator)
        )
        log_settings = await db.get_sanction_log(source_id)
        linked_destination = bool(
            log_settings and log_settings["destination_guild_id"] == interaction.guild_id
        )
        if source_id != interaction.guild_id and not source_staff and not linked_destination:
            await interaction.response.send_message(
                "Tu n'as pas accès aux sanctions de ce serveur d'origine.", ephemeral=True
            )
            return

        records = await db.search_sanction_records(utilisateur, guild_id=source_id)
        if not records:
            await interaction.response.send_message(
                f"Aucune sanction trouvée pour **{utilisateur}** provenant de "
                f"**{source_guild.name}** (`{source_id}`).", ephemeral=True
            )
            return
        first = records[0]
        embed = discord.Embed(
            title=f"⚖️ Casier de {first['display_name']}",
            description=(f"ID : `{first['user_id']}` • Origine : **{source_guild.name}** "
                         f"(`{source_id}`) • {len(records)} résultat(s) affiché(s)"),
            color=config.COLOR_MARINE,
        )
        labels = {"ban": "🔨 Ban", "warn": "⚠️ Warn", "timeout": "🔇 Timeout",
                  "kick": "👢 Kick", "antiraid": "🚨 Anti-raid"}
        for record in records[:25]:
            guild = self.bot.get_guild(record["guild_id"])
            guild_name = guild.name if guild else str(record["guild_id"])
            duration = f" • {format_duration(record['duration_seconds'])}" if record["duration_seconds"] else ""
            embed.add_field(
                name=f"#{record['id']} • {labels.get(record['sanction_type'], record['sanction_type'])}",
                value=(f"**Serveur :** {guild_name}{duration}\n**Raison :** {record['reason'][:500]}\n"
                       f"**Date :** {record['created_at'][:16].replace('T', ' ')} UTC\n"
                       f"**Par :** {record['moderator_name'] or 'Automatique'}"),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="sanctions-import", description="[Admin] Importe les bans et avertissements déjà existants dans le registre.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def sanctions_import(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        imported_bans = imported_warns = 0
        try:
            async for entry in interaction.guild.bans(limit=None):
                reason = entry.reason or "Aucune raison disponible"
                if await db.sanction_record_exists(interaction.guild_id, entry.user.id, "ban", reason):
                    continue
                await db.add_sanction_record(
                    interaction.guild_id, entry.user.id, str(entry.user),
                    getattr(entry.user, "display_name", entry.user.name), "ban", None, None, reason,
                )
                imported_bans += 1
        except discord.Forbidden:
            await interaction.followup.send(
                "Import impossible : le bot n'a pas la permission de consulter les bannissements.", ephemeral=True
            )
            return

        for warning in await db.get_all_warnings_for_guild(interaction.guild_id):
            if await db.sanction_record_exists(
                interaction.guild_id, warning["user_id"], "warn", warning["reason"]
            ):
                continue
            member = interaction.guild.get_member(warning["user_id"])
            moderator = interaction.guild.get_member(warning["moderator_id"])
            username = str(member) if member else f"Utilisateur {warning['user_id']}"
            display_name = member.display_name if member else username
            await db.add_sanction_record(
                interaction.guild_id, warning["user_id"], username, display_name, "warn",
                warning["moderator_id"], str(moderator) if moderator else None, warning["reason"],
            )
            imported_warns += 1
        await interaction.followup.send(
            f"Import terminé : **{imported_bans} bans** et **{imported_warns} avertissements** ajoutés au registre.",
            ephemeral=True,
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("Permission administrateur requise.", ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(CommunityTools(bot))
