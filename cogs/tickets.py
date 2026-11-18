"""
cogs/tickets.py
------------------
Système de tickets configurable, indépendant du reste du bot :
- /ticket-setup /ticket-list /ticket-remove : configuration des catégories
- /panel : panneau permanent (persistant) avec menu déroulant dans un salon
- /ticket : version éphémère du même menu, utilisable par n'importe qui
- Fermeture avec option de transcription (MP aux membres et/ou salon de logs)
- /ticket-adduser /ticket-removeuser /ticket-addrole /ticket-removerole :
  gestion des accès d'UN ticket précis, sans toucher aux autres
"""

import asyncio
import io
import re
import unicodedata

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db

DEFAULT_TICKET_MESSAGE = (
    "Merci d'avoir ouvert un ticket ! Décris ta demande le plus "
    "précisément possible, un membre du staff te répondra dès que possible."
)

PANEL_SELECT_CUSTOM_ID = "ticket_panel_select"
CLOSE_BUTTON_CUSTOM_ID = "ticket_close_button"
CLAIM_BUTTON_CUSTOM_ID = "ticket_claim_button"

TRACKING_STATUSES = {
    "attente": {
        "label": "En attente",
        "emoji": "🟡",
        "color": discord.Color.gold(),
    },
    "examen": {
        "label": "En examen",
        "emoji": "🔵",
        "color": discord.Color.blue(),
    },
    "acceptee": {
        "label": "Acceptée",
        "emoji": "🟢",
        "color": discord.Color.green(),
    },
    "refusee": {
        "label": "Refusée",
        "emoji": "🔴",
        "color": discord.Color.red(),
    },
    "closed": {
        "label": "Ticket fermé",
        "emoji": "⚫",
        "color": discord.Color.dark_grey(),
    },
}

def _sanitize_channel_name(text: str) -> str:
    """Transforme un texte libre en nom de salon Discord valide (minuscules, tirets, sans accents)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:90] or "ticket"


def _validate_emoji(guild: discord.Guild, raw: str) -> str | None:
    """
    Valide un emoji saisi par l'admin. Accepte un emoji unicode classique,
    ou un emoji personnalisé du serveur (doit appartenir à CE serveur).
    Retourne la représentation à stocker, ou None si invalide.
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        partial = discord.PartialEmoji.from_str(raw)
    except Exception:
        return None

    if partial.id is not None:
        # Emoji personnalisé : doit appartenir à ce serveur précis
        if not any(e.id == partial.id for e in guild.emojis):
            return None

    return str(partial)


def _configured_ticket_roles(guild: discord.Guild, category: dict) -> list[discord.Role]:
    """Résout les rôles configurés, avec repli sur l'ancien champ unique."""
    role_ids = category.get("role_ids") or ([category["role_id"]] if category.get("role_id") else [])
    roles = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role and role != guild.default_role and role not in roles:
            roles.append(role)
    return roles


async def ticket_category_autocomplete(interaction: discord.Interaction, current: str):
    """Autocomplétion listant les catégories de ticket déjà configurées sur ce serveur."""
    categories = await db.get_ticket_categories(interaction.guild_id)
    return [
        app_commands.Choice(name=cat["display_name"], value=cat["name"])
        for cat in categories
        if current.lower() in cat["display_name"].lower()
    ][:25]


# ------------------------------------------------------------------
# Menu déroulant (partagé entre /panel [persistant] et /ticket [éphémère])
# ------------------------------------------------------------------

class TicketCategorySelect(discord.ui.Select):
    def __init__(self, categories: list[dict] | None, persistent: bool):
        if categories:
            options = [
                discord.SelectOption(
                    label=cat["display_name"][:100],
                    value=cat["name"],
                    description="Ouvrir un ticket dans cette catégorie",
                    emoji=cat.get("emoji") or None,
                )
                for cat in categories[:25]
            ]
        else:
            options = [discord.SelectOption(label="Chargement...", value="_placeholder")]

        kwargs = dict(
            placeholder="Choisis une catégorie de ticket...",
            options=options,
            min_values=1,
            max_values=1,
        )
        if persistent:
            kwargs["custom_id"] = PANEL_SELECT_CUSTOM_ID
        super().__init__(**kwargs)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if value == "_placeholder":
            await interaction.response.send_message(
                "Ce panneau ne semble plus valide, demande à un admin de reposter `/panel`.", ephemeral=True
            )
            return
        cog = interaction.client.get_cog("Tickets")
        await cog.create_ticket_channel(interaction, value)


class TicketMenuView(discord.ui.View):
    """Vue éphémère (le menu de /ticket, expire après 3 minutes)."""

    def __init__(self, categories: list[dict]):
        super().__init__(timeout=180)
        self.add_item(TicketCategorySelect(categories, persistent=False))


class PersistentPanelView(discord.ui.View):
    """Vue persistante (le menu de /panel, survit aux redémarrages du bot)."""

    def __init__(self, categories: list[dict] | None = None):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect(categories, persistent=True))


class PanelCategoryPickerSelect(discord.ui.Select):
    """Menu à choix multiple : quelles catégories inclure dans le panneau qu'on va poster."""

    def __init__(self, categories: list[dict], titre: str | None, description: str | None):
        options = [
            discord.SelectOption(
                label=cat["display_name"][:100],
                value=cat["name"],
                emoji=cat.get("emoji") or None,
            )
            for cat in categories[:25]
        ]
        super().__init__(
            placeholder="Choisis les catégories à inclure dans ce panneau...",
            options=options,
            min_values=1,
            max_values=len(options),
        )
        self.titre = titre
        self.description = description

    async def callback(self, interaction: discord.Interaction):
        selected = set(self.values)
        all_categories = await db.get_ticket_categories(interaction.guild_id)
        chosen = [cat for cat in all_categories if cat["name"] in selected]

        embed = discord.Embed(
            title=self.titre or "🎫 Support — Ouvrir un ticket",
            description=self.description or "Sélectionne une catégorie ci-dessous pour ouvrir un ticket avec notre équipe.",
            color=config.COLOR_MARINE,
        )
        for cat in chosen:
            emoji_prefix = f"{cat['emoji']} " if cat.get("emoji") else "🔹 "
            embed.add_field(name=f"{emoji_prefix}{cat['display_name']}", value="\u200b", inline=True)
        embed.set_footer(text="Un salon privé sera créé rien que pour toi.")

        await interaction.channel.send(embed=embed, view=PersistentPanelView(chosen))
        await interaction.response.edit_message(
            content=f"✅ Panneau posté avec {len(chosen)} catégorie(s) !", view=None
        )


class PanelCategoryPickerView(discord.ui.View):
    """Vue éphémère affichée le temps que l'admin choisisse les catégories du panneau."""

    def __init__(self, categories: list[dict], titre: str | None, description: str | None):
        super().__init__(timeout=120)
        self.add_item(PanelCategoryPickerSelect(categories, titre, description))


# ------------------------------------------------------------------
# Fermeture de ticket + choix de transcription
# ------------------------------------------------------------------

class TranscriptChoiceView(discord.ui.View):
    """Proposée après un clic sur "Fermer le ticket" : que faire de la transcription ?"""

    def __init__(self, ticket: dict):
        super().__init__(timeout=60)
        self.ticket = ticket

    async def _finalize(self, interaction: discord.Interaction, send_dm: bool, send_log: bool):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="🔒 Fermeture du ticket en cours...", view=self)

        cog = interaction.client.get_cog("Tickets")
        await cog.finalize_ticket_closure(
            channel=interaction.channel,
            ticket=self.ticket,
            send_dm=send_dm,
            send_log=send_log,
            closer=interaction.user,
        )
        self.stop()

    @discord.ui.button(label="MP aux membres", style=discord.ButtonStyle.primary, emoji="📨", row=0)
    async def dm_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction, send_dm=True, send_log=False)

    @discord.ui.button(label="Dans les logs", style=discord.ButtonStyle.primary, emoji="📋", row=0)
    async def log_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction, send_dm=False, send_log=True)

    @discord.ui.button(label="MP + Logs", style=discord.ButtonStyle.success, emoji="✅", row=0)
    async def both(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction, send_dm=True, send_log=True)

    @discord.ui.button(label="Sans transcription", style=discord.ButtonStyle.secondary, emoji="🚫", row=1)
    async def none(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finalize(interaction, send_dm=False, send_log=False)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="❌", row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Fermeture annulée.", view=self)
        self.stop()


class CloseTicketView(discord.ui.View):
    """Vue persistante affichée dans chaque salon de ticket."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Prendre en charge",
        style=discord.ButtonStyle.success,
        emoji="🙋",
        custom_id=CLAIM_BUTTON_CUSTOM_ID,
    )
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("Tickets")
        await cog.handle_ticket_claim(interaction)

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id=CLOSE_BUTTON_CUSTOM_ID)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await db.get_ticket_by_channel(interaction.channel_id)
        if ticket is None:
            await interaction.response.send_message(
                "Ce salon n'est plus reconnu comme un ticket actif.", ephemeral=True
            )
            return

        is_owner = interaction.user.id == ticket["user_id"]
        is_staff = interaction.user.guild_permissions.manage_channels
        if not (is_owner or is_staff):
            await interaction.response.send_message(
                "Seul l'auteur du ticket ou un membre du staff peut le fermer.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Comment veux-tu gérer la transcription avant de fermer ce ticket ?",
            view=TranscriptChoiceView(ticket),
            ephemeral=True,
        )


class Tickets(commands.Cog):
    """Commandes du système de tickets (config, panneau, ouverture, fermeture, gestion des accès)."""

    tickets = app_commands.Group(name="tickets", description="Tickets : ouverture, suivi, accès et configuration", guild_only=True)

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Vues persistantes : doivent fonctionner même après un redémarrage du bot.
        self.bot.add_view(CloseTicketView())
        self.bot.add_view(PersistentPanelView())

    @tickets.command(name="close", description="Ferme le ticket actuel avec les options de transcription.")
    async def ticket_close(self, interaction: discord.Interaction):
        ticket = await db.get_ticket_by_channel(interaction.channel_id)
        if ticket is None:
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un ticket actif.", ephemeral=True
            )
            return

        is_owner = interaction.user.id == ticket["user_id"]
        is_staff = interaction.user.guild_permissions.manage_channels
        if not (is_owner or is_staff):
            await interaction.response.send_message(
                "Seul l'auteur du ticket ou un membre du staff peut le fermer.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Comment veux-tu gérer la transcription avant de fermer ce ticket ?",
            view=TranscriptChoiceView(ticket),
            ephemeral=True,
        )

    async def handle_ticket_claim(self, interaction: discord.Interaction):
        """Logique commune au bouton persistant et à /ticket-claim."""
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "Seul un membre du staff pouvant gérer les salons peut prendre en charge ce ticket.",
                ephemeral=True,
            )
            return
        result = await db.claim_ticket(interaction.channel_id, interaction.user.id)
        if result["status"] == "not_found":
            await interaction.response.send_message(
                "Ce salon n'est plus reconnu comme un ticket actif.", ephemeral=True
            )
            return
        if result["status"] == "already_yours":
            await interaction.response.send_message(
                "Tu prends déjà en charge ce ticket.", ephemeral=True
            )
            return
        if result["status"] == "already_claimed":
            claimant = interaction.guild.get_member(result["ticket"]["claimed_by"])
            await interaction.response.send_message(
                f"Ce ticket est déjà pris en charge par {claimant.mention if claimant else '`Utilisateur inconnu`'}.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🙋 Ticket pris en charge",
            description=f"{interaction.user.mention} s'occupe maintenant de cette demande.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)
        await self._refresh_tracking_claim(interaction.channel)

    @tickets.command(name="claim", description="[Staff] Prend en charge le ticket actuel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_claim(self, interaction: discord.Interaction):
        await self.handle_ticket_claim(interaction)

    @tickets.command(name="unclaim", description="[Staff] Libère la prise en charge du ticket actuel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_unclaim(self, interaction: discord.Interaction):
        result = await db.unclaim_ticket(interaction.channel_id)
        if result["status"] == "not_found":
            await interaction.response.send_message(
                "Cette commande doit être utilisée dans un ticket actif.", ephemeral=True
            )
            return
        if result["status"] == "not_claimed":
            await interaction.response.send_message(
                "Ce ticket n'est actuellement pris en charge par personne.", ephemeral=True
            )
            return
        previous = interaction.guild.get_member(result["previous_claimant"])
        previous_text = previous.mention if previous else "le précédent responsable"
        embed = discord.Embed(
            title="↩️ Ticket libéré",
            description=f"{interaction.user.mention} a retiré la prise en charge de {previous_text}.",
            color=config.COLOR_MARINE,
        )
        await interaction.response.send_message(embed=embed)
        await self._refresh_tracking_claim(interaction.channel)

    # ------------------------------------------------------------------
    # /ticket-setup (admin)
    # ------------------------------------------------------------------
    @tickets.command(name="setup", description="[Admin] Configure (ou met à jour) une catégorie de ticket.")
    @app_commands.describe(
        nom="Nom de cette catégorie de ticket (ex: Support, Signalement, Partenariat...)",
        categorie="Catégorie Discord dans laquelle créer les salons de ticket",
        role="Premier rôle à mentionner (optionnel)",
        role_2="Deuxième rôle à mentionner (optionnel)",
        role_3="Troisième rôle à mentionner (optionnel)",
        role_4="Quatrième rôle à mentionner (optionnel)",
        role_5="Cinquième rôle à mentionner (optionnel)",
        message="Message affiché à l'ouverture du ticket (optionnel, message par défaut sinon)",
        emoji="Emoji pour illustrer cette catégorie dans le menu (optionnel, emoji du serveur ou classique)",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        nom: str,
        categorie: discord.CategoryChannel,
        role: discord.Role | None = None,
        role_2: discord.Role | None = None,
        role_3: discord.Role | None = None,
        role_4: discord.Role | None = None,
        role_5: discord.Role | None = None,
        message: str | None = None,
        emoji: str | None = None,
    ):
        final_message = message.strip() if message and message.strip() else DEFAULT_TICKET_MESSAGE
        configured_roles = list(dict.fromkeys(
            configured_role for configured_role in (role, role_2, role_3, role_4, role_5)
            if configured_role is not None and configured_role != interaction.guild.default_role
        ))

        final_emoji = None
        if emoji:
            final_emoji = _validate_emoji(interaction.guild, emoji)
            if final_emoji is None:
                embed = discord.Embed(
                    title="❌ Emoji invalide",
                    description="Utilise un emoji classique, ou un emoji personnalisé appartenant à CE serveur.",
                    color=config.COLOR_ERROR,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        await db.set_ticket_category(
            guild_id=interaction.guild_id,
            name=nom,
            discord_category_id=categorie.id,
            role_id=role.id if role else None,
            message=final_message,
            emoji=final_emoji,
            role_ids=[configured_role.id for configured_role in configured_roles],
        )

        embed = discord.Embed(
            title="✅ Catégorie de ticket configurée",
            description=f"**{nom.strip()}** est prête à être utilisée via `/ticket` ou `/panel`.",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="📁 Salon parent", value=categorie.mention, inline=True)
        embed.add_field(
            name="🔔 Rôles pingés",
            value=", ".join(configured_role.mention for configured_role in configured_roles) or "Aucun",
            inline=True,
        )
        embed.add_field(name="✨ Emoji", value=final_emoji or "Aucun", inline=True)
        embed.add_field(name="💬 Message d'ouverture", value=final_message, inline=False)
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /ticket-update (admin) — modifie uniquement les champs fournis
    # ------------------------------------------------------------------
    @tickets.command(name="update", description="[Admin] Modifie une catégorie de ticket existante (seuls les champs fournis changent).")
    @app_commands.describe(
        nom="Catégorie de ticket à modifier",
        nouvelle_categorie="Nouvelle catégorie Discord (optionnel)",
        nouveau_role="Premier rôle de la nouvelle liste (optionnel)",
        nouveau_role_2="Deuxième rôle de la nouvelle liste (optionnel)",
        nouveau_role_3="Troisième rôle de la nouvelle liste (optionnel)",
        nouveau_role_4="Quatrième rôle de la nouvelle liste (optionnel)",
        nouveau_role_5="Cinquième rôle de la nouvelle liste (optionnel)",
        retirer_role="Retire tous les rôles actuellement configurés",
        nouveau_message="Nouveau message d'ouverture (optionnel)",
        nouvel_emoji="Nouvel emoji pour illustrer cette catégorie (optionnel)",
        retirer_emoji="Retire l'emoji actuellement configuré (ignore nouvel_emoji si activé)",
    )
    @app_commands.autocomplete(nom=ticket_category_autocomplete)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_update(
        self,
        interaction: discord.Interaction,
        nom: str,
        nouvelle_categorie: discord.CategoryChannel | None = None,
        nouveau_role: discord.Role | None = None,
        nouveau_role_2: discord.Role | None = None,
        nouveau_role_3: discord.Role | None = None,
        nouveau_role_4: discord.Role | None = None,
        nouveau_role_5: discord.Role | None = None,
        retirer_role: bool = False,
        nouveau_message: str | None = None,
        nouvel_emoji: str | None = None,
        retirer_emoji: bool = False,
    ):
        current = await db.get_ticket_category(interaction.guild_id, nom)
        if current is None:
            embed = discord.Embed(
                title="❌ Catégorie introuvable",
                description="Utilise `/ticket-list` pour voir les catégories existantes.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # --- Emoji ---
        emoji_update = db.UNSET
        if retirer_emoji:
            emoji_update = None
        elif nouvel_emoji:
            parsed_emoji = _validate_emoji(interaction.guild, nouvel_emoji)
            if parsed_emoji is None:
                embed = discord.Embed(
                    title="❌ Emoji invalide",
                    description="Utilise un emoji classique, ou un emoji personnalisé appartenant à CE serveur.",
                    color=config.COLOR_ERROR,
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            emoji_update = parsed_emoji

        # --- Rôle ---
        roles_update = db.UNSET
        if retirer_role:
            roles_update = []
        else:
            requested_roles = list(dict.fromkeys(
                configured_role
                for configured_role in (
                    nouveau_role, nouveau_role_2, nouveau_role_3, nouveau_role_4, nouveau_role_5
                )
                if configured_role is not None and configured_role != interaction.guild.default_role
            ))
            if requested_roles:
                roles_update = [configured_role.id for configured_role in requested_roles]

        # --- Catégorie Discord ---
        category_update = nouvelle_categorie.id if nouvelle_categorie is not None else db.UNSET

        # --- Message ---
        message_update = db.UNSET
        if nouveau_message and nouveau_message.strip():
            message_update = nouveau_message.strip()

        if all(update is db.UNSET for update in (emoji_update, roles_update, category_update, message_update)):
            embed = discord.Embed(
                title="🤔 Rien à modifier",
                description="Fournis au moins un champ à changer.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.update_ticket_category(
            guild_id=interaction.guild_id,
            name=nom,
            discord_category_id=category_update,
            role_ids=roles_update,
            message=message_update,
            emoji=emoji_update,
        )

        updated = await db.get_ticket_category(interaction.guild_id, nom)
        updated_channel = interaction.guild.get_channel(updated["discord_category_id"])
        updated_roles = _configured_ticket_roles(interaction.guild, updated)

        embed = discord.Embed(
            title="✅ Catégorie mise à jour",
            description=f"**{updated['display_name']}** a été modifiée.",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="📁 Salon parent", value=updated_channel.mention if updated_channel else "⚠️ introuvable", inline=True)
        embed.add_field(
            name="🔔 Rôles pingés",
            value=", ".join(role.mention for role in updated_roles) or "Aucun",
            inline=True,
        )
        embed.add_field(name="✨ Emoji", value=updated["emoji"] or "Aucun", inline=True)
        embed.add_field(name="💬 Message d'ouverture", value=updated["message"], inline=False)
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /ticket-list (admin)
    # ------------------------------------------------------------------
    @tickets.command(name="list", description="[Admin] Liste les catégories de ticket configurées.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_list(self, interaction: discord.Interaction):
        categories = await db.get_ticket_categories(interaction.guild_id)

        if not categories:
            embed = discord.Embed(
                title="🎫 Aucune catégorie configurée",
                description="Utilise `/ticket-setup` pour en créer une.",
                color=config.COLOR_MARINE,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(title="🎫 Catégories de ticket configurées", color=config.COLOR_MARINE)
        for cat in categories:
            category_channel = interaction.guild.get_channel(cat["discord_category_id"])
            configured_roles = _configured_ticket_roles(interaction.guild, cat)
            embed.add_field(
                name=f"{(cat.get('emoji') + ' ') if cat.get('emoji') else ''}{cat['display_name']}",
                value=(
                    f"📁 {category_channel.mention if category_channel else '⚠️ salon introuvable'}\n"
                    f"🔔 {', '.join(role.mention for role in configured_roles) or 'Aucun rôle'}"
                ),
                inline=True,
            )

        log_channel_id = await db.get_ticket_log_channel(interaction.guild_id)
        log_channel = interaction.guild.get_channel(log_channel_id) if log_channel_id else None
        embed.set_footer(text=f"Salon de logs : {'#' + log_channel.name if log_channel else 'non configuré (/ticket-logs)'}")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /ticket-remove (admin)
    # ------------------------------------------------------------------
    @tickets.command(name="remove", description="[Admin] Supprime une catégorie de ticket.")
    @app_commands.describe(nom="Nom de la catégorie à supprimer")
    @app_commands.autocomplete(nom=ticket_category_autocomplete)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_remove(self, interaction: discord.Interaction, nom: str):
        removed = await db.remove_ticket_category(interaction.guild_id, nom)

        if not removed:
            embed = discord.Embed(
                title="❌ Catégorie introuvable",
                description="Utilise `/ticket-list` pour voir les catégories existantes.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🗑️ Catégorie supprimée",
            description=f"**{nom}** ne sera plus proposée dans `/ticket` ou `/panel`.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /ticket-logs (admin)
    # ------------------------------------------------------------------
    @tickets.command(name="logs", description="[Admin] Définit le salon où envoyer les transcriptions de tickets.")
    @app_commands.describe(salon="Salon où seront postées les transcriptions")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_logs(self, interaction: discord.Interaction, salon: discord.TextChannel):
        await db.set_ticket_log_channel(interaction.guild_id, salon.id)
        embed = discord.Embed(
            title="✅ Salon de logs configuré",
            description=f"Les transcriptions de tickets seront envoyées dans {salon.mention}.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /panel (admin) — panneau persistant
    # ------------------------------------------------------------------
    @tickets.command(name="panel", description="[Admin] Poste un panneau permanent pour ouvrir des tickets.")
    @app_commands.describe(
        titre="Titre du panneau (optionnel)",
        description="Texte d'introduction du panneau (optionnel)",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def panel(
        self,
        interaction: discord.Interaction,
        titre: str | None = None,
        description: str | None = None,
    ):
        categories = await db.get_ticket_categories(interaction.guild_id)
        if not categories:
            embed = discord.Embed(
                title="❌ Aucune catégorie configurée",
                description="Utilise `/ticket-setup` avant de poster un panneau.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if len(categories) == 1:
            # Une seule catégorie existe : pas besoin de demander à choisir.
            embed = discord.Embed(
                title=titre or "🎫 Support — Ouvrir un ticket",
                description=description or "Sélectionne une catégorie ci-dessous pour ouvrir un ticket avec notre équipe.",
                color=config.COLOR_MARINE,
            )
            cat = categories[0]
            emoji_prefix = f"{cat['emoji']} " if cat.get("emoji") else "🔹 "
            embed.add_field(name=f"{emoji_prefix}{cat['display_name']}", value="\u200b", inline=True)
            embed.set_footer(text="Un salon privé sera créé rien que pour toi.")
            await interaction.channel.send(embed=embed, view=PersistentPanelView(categories))
            await interaction.response.send_message("✅ Panneau posté !", ephemeral=True)
            return

        view = PanelCategoryPickerView(categories, titre, description)
        await interaction.response.send_message(
            "Quelles catégories veux-tu inclure dans ce panneau ?", view=view, ephemeral=True
        )

    # ------------------------------------------------------------------
    # /ticket (tout le monde) — version éphémère du menu
    # ------------------------------------------------------------------
    @tickets.command(name="open", description="Ouvre un ticket auprès du staff du serveur.")
    async def ticket(self, interaction: discord.Interaction):
        categories = await db.get_ticket_categories(interaction.guild_id)

        if not categories:
            embed = discord.Embed(
                title="🎫 Système de tickets non configuré",
                description="Aucune catégorie de ticket n'a encore été configurée sur ce serveur.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🎫 Ouvrir un ticket",
            description="Choisis une catégorie dans le menu ci-dessous.",
            color=config.COLOR_MARINE,
        )
        await interaction.response.send_message(embed=embed, view=TicketMenuView(categories), ephemeral=True)

    # ------------------------------------------------------------------
    # Création effective du salon de ticket (appelée par le menu déroulant)
    # ------------------------------------------------------------------
    async def create_ticket_channel(self, interaction: discord.Interaction, category_name: str):
        guild = interaction.guild
        user = interaction.user

        cat_config = await db.get_ticket_category(guild.id, category_name)
        if cat_config is None:
            await interaction.response.send_message("Cette catégorie n'existe plus.", ephemeral=True)
            return

        existing = await db.get_open_ticket(guild.id, user.id, category_name)
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            if channel:
                await interaction.response.send_message(
                    f"Tu as déjà un ticket ouvert dans cette catégorie : {channel.mention}", ephemeral=True
                )
                return
            await db.close_ticket(existing["channel_id"])

        await interaction.response.defer(ephemeral=True)

        discord_category = guild.get_channel(cat_config["discord_category_id"])
        configured_roles = _configured_ticket_roles(guild, cat_config)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for configured_role in configured_roles:
            overwrites[configured_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel_name = f"ticket-{_sanitize_channel_name(category_name)}-{_sanitize_channel_name(user.name)}"[:100]

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=discord_category if isinstance(discord_category, discord.CategoryChannel) else None,
            overwrites=overwrites,
            topic=f"Ticket {cat_config['display_name']} ouvert par {user} ({user.id})",
            reason=f"Ticket ouvert par {user}",
        )

        await db.create_ticket(ticket_channel.id, guild.id, user.id, category_name)

        role_mentions = " ".join(configured_role.mention for configured_role in configured_roles)
        opening_embed = discord.Embed(
            title=f"{(cat_config['emoji'] + ' ') if cat_config.get('emoji') else '🎫 '}Ticket : {cat_config['display_name']}",
            description=cat_config["message"],
            color=config.COLOR_MARINE,
        )
        await ticket_channel.send(
            content=f"{user.mention} {role_mentions}".strip(),
            embed=opening_embed,
            view=CloseTicketView(),
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=[user],
                roles=configured_roles,
            ),
        )

        warning = "" if discord_category else "\n⚠️ La catégorie Discord configurée est introuvable, le salon a été créé hors catégorie."
        await interaction.followup.send(f"✅ Ton ticket a été créé : {ticket_channel.mention}{warning}", ephemeral=True)

    # ------------------------------------------------------------------
    # Transcription + fermeture définitive
    # ------------------------------------------------------------------
    async def _generate_transcript_text(self, channel: discord.TextChannel) -> str:
        """Récupère l'historique du salon et le formate en texte lisible."""
        lines = []
        async for message in channel.history(limit=None, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = message.content or ""
            if message.embeds:
                content += " [Embed]"
            if message.attachments:
                content += " " + " ".join(a.url for a in message.attachments)
            lines.append(f"[{timestamp}] {message.author}: {content}")
        return "\n".join(lines) or "(Aucun message dans ce ticket)"

    def _make_transcript_file(self, text: str, channel_name: str) -> discord.File:
        """Crée un nouveau discord.File à partir du texte (les File ne sont utilisables qu'une fois)."""
        return discord.File(io.BytesIO(text.encode("utf-8")), filename=f"transcript-{channel_name}.txt")

    async def finalize_ticket_closure(
        self,
        channel: discord.TextChannel,
        ticket: dict,
        send_dm: bool,
        send_log: bool,
        closer: discord.Member,
    ):
        """Génère la transcription si demandé, l'envoie où il faut, puis supprime le salon."""
        transcript_text = None
        if send_dm or send_log:
            transcript_text = await self._generate_transcript_text(channel)

        if send_dm and transcript_text is not None:
            member_ids = {ticket["user_id"]}
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Member) and overwrite.view_channel:
                    member_ids.add(target.id)

            for uid in member_ids:
                member = channel.guild.get_member(uid)
                if member is None or member.bot:
                    continue
                try:
                    await member.send(
                        f"📋 Voici la transcription de ton ticket **#{channel.name}** :",
                        file=self._make_transcript_file(transcript_text, channel.name),
                    )
                except discord.Forbidden:
                    pass  # MPs fermés, on ignore silencieusement

        if send_log and transcript_text is not None:
            log_channel_id = await db.get_ticket_log_channel(channel.guild.id)
            log_channel = channel.guild.get_channel(log_channel_id) if log_channel_id else None
            if log_channel:
                await log_channel.send(
                    f"📋 Transcription du ticket **#{channel.name}** (fermé par {closer.mention})",
                    file=self._make_transcript_file(transcript_text, channel.name),
                )

        await self._update_tracking_status(channel, status="closed", closer=closer)

        await db.close_ticket(channel.id)
        await asyncio.sleep(3)
        try:
            await channel.delete(reason=f"Ticket fermé par {closer}")
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------
    # Mode "tracking" : statut public d'un ticket, mis à jour en direct
    # ------------------------------------------------------------------
    def _build_tracking_embed(
        self,
        category_display_name: str,
        opener: discord.abc.User | None,
        channel: discord.TextChannel,
        status: str,
        claimant: discord.abc.User | None = None,
    ) -> discord.Embed:
        status_data = TRACKING_STATUSES.get(status, TRACKING_STATUSES["attente"])
        member_name = f"@{opener.display_name}" if opener else "Membre inconnu"
        embed = discord.Embed(
            title=f"Ticket de {member_name} : {category_display_name}",
            color=status_data["color"],
        )
        embed.add_field(
            name="État actuel",
            value=f"{status_data['emoji']} **{status_data['label']}**",
            inline=True,
        )
        embed.add_field(
            name="Pris en charge par",
            value=claimant.mention if claimant else "Personne pour le moment",
            inline=True,
        )
        embed.set_footer(text=f"Salon : #{channel.name}")
        return embed

    async def _refresh_tracking_claim(self, channel: discord.TextChannel):
        """Actualise le responsable sans modifier l'état public du ticket."""
        tracked = await db.get_tracked_ticket(channel.id)
        if tracked:
            await self._update_tracking_status(
                channel,
                status=tracked.get("status") or "attente",
            )

    async def _update_tracking_status(self, channel: discord.TextChannel, status: str, closer: discord.Member | None = None):
        """Met à jour (sans spammer) le message de statut public d'un ticket suivi, s'il y en a un."""
        tracked = await db.get_tracked_ticket(channel.id)
        if tracked is None:
            return

        status_channel = channel.guild.get_channel(tracked["status_channel_id"])
        if status_channel is None:
            await db.stop_tracking(channel.id)
            return

        try:
            message = await status_channel.fetch_message(tracked["status_message_id"])
        except discord.NotFound:
            await db.stop_tracking(channel.id)
            return

        ticket = await db.get_ticket_by_channel(channel.id)
        opener = channel.guild.get_member(ticket["user_id"]) if ticket else None
        claimant = channel.guild.get_member(ticket["claimed_by"]) if ticket and ticket.get("claimed_by") else None
        cat_config = await db.get_ticket_category(channel.guild.id, ticket["category_name"]) if ticket else None
        category_name = cat_config["display_name"] if cat_config else "Ticket"

        embed = self._build_tracking_embed(category_name, opener, channel, status, claimant)
        if status == "closed" and closer:
            embed.add_field(name="Fermé par", value=closer.mention, inline=True)

        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            pass

        await db.update_tracked_ticket_status(channel.id, status)

        if status == "closed":
            await db.stop_tracking(channel.id)

    @tickets.command(name="tracking-setup", description="[Admin] Définit le salon public où seront postés les suivis de tickets.")
    @app_commands.describe(salon="Le salon public où poster les messages de suivi")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def tracking_setup(self, interaction: discord.Interaction, salon: discord.TextChannel):
        await db.set_tracking_channel(interaction.guild_id, salon.id)
        embed = discord.Embed(
            title="✅ Salon de suivi configuré",
            description=f"Les tickets suivis (`/track`) afficheront leur statut dans {salon.mention}.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @tickets.command(name="track", description="[Staff] Publie ou modifie l'état public de CE ticket.")
    @app_commands.describe(etat="Nouvel état de la demande")
    @app_commands.choices(
        etat=[
            app_commands.Choice(name="🟡 En attente", value="attente"),
            app_commands.Choice(name="🔵 En examen", value="examen"),
            app_commands.Choice(name="🟢 Acceptée", value="acceptee"),
            app_commands.Choice(name="🔴 Refusée", value="refusee"),
        ]
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def track(self, interaction: discord.Interaction, etat: app_commands.Choice[str]):
        ticket = await self._require_ticket_channel(interaction)
        if ticket is None:
            return

        tracking_channel_id = await db.get_tracking_channel(interaction.guild_id)
        tracking_channel = interaction.guild.get_channel(tracking_channel_id) if tracking_channel_id else None
        if tracking_channel is None:
            embed = discord.Embed(
                title="❌ Aucun salon de suivi configuré",
                description="Un admin doit d'abord utiliser `/tracking-setup`.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        cat_config = await db.get_ticket_category(interaction.guild_id, ticket["category_name"])
        category_name = cat_config["display_name"] if cat_config else "Ticket"
        opener = interaction.guild.get_member(ticket["user_id"])
        claimant = interaction.guild.get_member(ticket["claimed_by"]) if ticket.get("claimed_by") else None
        status_data = TRACKING_STATUSES[etat.value]
        embed = self._build_tracking_embed(
            category_name,
            opener,
            interaction.channel,
            status=etat.value,
            claimant=claimant,
        )

        tracked = await db.get_tracked_ticket(interaction.channel_id)
        if tracked:
            old_status_channel = interaction.guild.get_channel(tracked["status_channel_id"])
            status_message = None
            if old_status_channel is not None:
                try:
                    status_message = await old_status_channel.fetch_message(tracked["status_message_id"])
                    await status_message.edit(embed=embed)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    status_message = None

            if status_message is None:
                try:
                    status_message = await tracking_channel.send(embed=embed)
                except discord.Forbidden:
                    error_embed = discord.Embed(
                        title="❌ Permission refusée",
                        description=f"Je ne peux pas écrire dans {tracking_channel.mention}.",
                        color=config.COLOR_ERROR,
                    )
                    await interaction.response.send_message(embed=error_embed, ephemeral=True)
                    return

                await db.start_tracking(
                    channel_id=interaction.channel_id,
                    guild_id=interaction.guild_id,
                    status_channel_id=tracking_channel.id,
                    status_message_id=status_message.id,
                    tracked_by=interaction.user.id,
                    status=etat.value,
                )

            await db.update_tracked_ticket_status(interaction.channel_id, etat.value)

            confirm = discord.Embed(
                title="✅ État du ticket modifié",
                description=(
                    f"La demande est maintenant {status_data['emoji']} **{status_data['label']}** "
                    f"dans {tracking_channel.mention}."
                ),
                color=status_data["color"],
            )
            await interaction.response.send_message(embed=confirm, ephemeral=True)
            return

        try:
            status_message = await tracking_channel.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission refusée",
                description=f"Je ne peux pas écrire dans {tracking_channel.mention}.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await db.start_tracking(
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            status_channel_id=tracking_channel.id,
            status_message_id=status_message.id,
            tracked_by=interaction.user.id,
            status=etat.value,
        )

        confirm = discord.Embed(
            title="📡 Suivi activé",
            description=(
                f"La demande est maintenant visible dans {tracking_channel.mention} avec l'état "
                f"{status_data['emoji']} **{status_data['label']}**.\n"
                "Réutilise `/track` pour modifier son état sans créer un nouveau message."
            ),
            color=status_data["color"],
        )
        await interaction.response.send_message(embed=confirm, ephemeral=True)

    @tickets.command(name="untrack", description="[Staff] Désactive le suivi public de CE ticket.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def untrack(self, interaction: discord.Interaction):
        if await self._require_ticket_channel(interaction) is None:
            return

        tracked = await db.get_tracked_ticket(interaction.channel_id)
        if tracked is None:
            embed = discord.Embed(
                title="🤔 Pas suivi",
                description="Ce ticket n'est pas en mode suivi.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        status_channel = interaction.guild.get_channel(tracked["status_channel_id"])
        if status_channel:
            try:
                message = await status_channel.fetch_message(tracked["status_message_id"])
                embed = message.embeds[0] if message.embeds else discord.Embed(title="🎫 Suivi de ticket")
                embed.color = discord.Color.greyple()
                embed.add_field(name="Suivi", value="⏹️ Désactivé manuellement", inline=False)
                await message.edit(embed=embed)
            except (discord.NotFound, discord.HTTPException):
                pass

        await db.stop_tracking(interaction.channel_id)

        embed = discord.Embed(
            title="✅ Suivi désactivé",
            description="Ce ticket n'est plus suivi publiquement.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Gestion des accès d'UN ticket précis (sans toucher aux autres)
    # ------------------------------------------------------------------
    async def _require_ticket_channel(self, interaction: discord.Interaction) -> dict | None:
        ticket = await db.get_ticket_by_channel(interaction.channel_id)
        if ticket is None:
            embed = discord.Embed(
                title="❌ Pas un salon de ticket",
                description="Cette commande doit être utilisée à l'intérieur d'un salon de ticket.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return None
        return ticket

    @tickets.command(name="add-user", description="[Staff] Ajoute un membre à CE ticket uniquement.")
    @app_commands.describe(membre="Le membre à ajouter à ce ticket")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_adduser(self, interaction: discord.Interaction, membre: discord.Member):
        if await self._require_ticket_channel(interaction) is None:
            return
        await interaction.channel.set_permissions(
            membre, view_channel=True, send_messages=True, read_message_history=True,
            reason=f"Ajouté au ticket par {interaction.user}",
        )
        embed = discord.Embed(
            title="✅ Membre ajouté",
            description=f"{membre.mention} peut maintenant voir ce ticket.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @tickets.command(name="remove-user", description="[Staff] Retire un membre de CE ticket uniquement.")
    @app_commands.describe(membre="Le membre à retirer de ce ticket")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_removeuser(self, interaction: discord.Interaction, membre: discord.Member):
        if await self._require_ticket_channel(interaction) is None:
            return
        await interaction.channel.set_permissions(
            membre, overwrite=None, reason=f"Retiré du ticket par {interaction.user}",
        )
        embed = discord.Embed(
            title="✅ Membre retiré",
            description=f"{membre.mention} n'a plus accès à ce ticket.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @tickets.command(name="add-role", description="[Staff] Donne accès à CE ticket à un rôle entier.")
    @app_commands.describe(role="Le rôle à ajouter à ce ticket")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_addrole(self, interaction: discord.Interaction, role: discord.Role):
        if await self._require_ticket_channel(interaction) is None:
            return
        await interaction.channel.set_permissions(
            role, view_channel=True, send_messages=True, read_message_history=True,
            reason=f"Ajouté au ticket par {interaction.user}",
        )
        embed = discord.Embed(
            title="✅ Rôle ajouté",
            description=f"{role.mention} peut maintenant voir ce ticket.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @tickets.command(name="remove-role", description="[Staff] Retire l'accès à CE ticket à un rôle.")
    @app_commands.describe(role="Le rôle à retirer de ce ticket")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_removerole(self, interaction: discord.Interaction, role: discord.Role):
        if await self._require_ticket_channel(interaction) is None:
            return
        await interaction.channel.set_permissions(
            role, overwrite=None, reason=f"Retiré du ticket par {interaction.user}",
        )
        embed = discord.Embed(
            title="✅ Rôle retiré",
            description=f"{role.mention} n'a plus accès à ce ticket.",
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Gestion des erreurs de permissions
    # ------------------------------------------------------------------
    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="🚫 Accès refusé",
                description="Seuls les membres avec la permission *Gérer les salons* peuvent faire ça.",
                color=config.COLOR_ERROR,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
