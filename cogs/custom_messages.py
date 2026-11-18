"""Publier et modifier des messages du bot via des formulaires Discord.

Les messages sont également suivis par le panel web pour permettre leur édition
à partir des deux interfaces.
"""

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from utils.custom_messages import is_valid_image_url, parse_embed_color

logger = logging.getLogger(__name__)

MESSAGE_LINK = re.compile(
    r"https?://(?:(?:canary|ptb)\.)?(?:discord(?:app)?\.com)/channels/"
    r"(?P<guild>\d{15,22})/(?P<channel>\d{15,22})/(?P<message>\d{15,22})/?(?:\?.*)?",
    re.IGNORECASE,
)


def parse_message_reference(reference: str, guild_id: int, channel_id: int | None = None):
    """Return (channel_id, message_id), or None for an invalid/wrong-guild link."""
    value = reference.strip().strip("<>")
    match = MESSAGE_LINK.fullmatch(value)
    if match:
        if int(match.group("guild")) != guild_id:
            return None
        return int(match.group("channel")), int(match.group("message"))
    if value.isdigit() and 15 <= len(value) <= 22 and channel_id is not None:
        return channel_id, int(value)
    return None


def values_for_panel(message: discord.Message, embed: discord.Embed | None = None) -> dict:
    """Convert a bot message to the format stored by the web panel."""
    current = embed if embed is not None else (message.embeds[0] if message.embeds else None)
    return {
        "message_type": "embed" if current else "text",
        "content": message.content or "",
        "embed_title": (current.title or "") if current else "",
        "embed_description": (current.description or "") if current else "",
        "embed_color": f"#{current.color.value:06X}" if current and current.color else "#5865F2",
        "embed_footer": (current.footer.text or "") if current else "",
        "embed_image": (current.image.url or "") if current and current.image else "",
    }


async def track_message(message: discord.Message, editor_id: int, embed: discord.Embed | None = None):
    """Persist a message for future updates from the web panel."""
    try:
        await db.save_panel_message(
            message.guild.id, message.channel.id, message.id,
            values_for_panel(message, embed), editor_id,
        )
    except Exception:
        logger.exception("Impossible d'enregistrer le message %s dans le panel", message.id)
        return False
    return True


class CustomMessageModal(discord.ui.Modal, title="Créer un message personnalisé"):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=600)
        self.channel = channel
        self.message_title = discord.ui.TextInput(
            label="Titre", placeholder="Ex. 📜 Règlement du serveur",
            required=False, max_length=256,
        )
        self.content = discord.ui.TextInput(
            label="Texte du message", placeholder="Écris ton annonce ici...",
            style=discord.TextStyle.paragraph, required=False, max_length=4000,
        )
        self.color = discord.ui.TextInput(
            label="Couleur (hexadécimale)", placeholder="#5865F2",
            default="#5865F2", required=False, max_length=7,
        )
        self.footer = discord.ui.TextInput(
            label="Pied de page", required=False, max_length=2048,
        )
        self.image_url = discord.ui.TextInput(
            label="URL d'image (facultatif)", required=False, max_length=512,
        )
        for item in (self.message_title, self.content, self.color, self.footer, self.image_url):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        color = parse_embed_color(self.color.value)
        if color is None:
            return await interaction.response.send_message(
                "La couleur doit être au format `#RRGGBB`.", ephemeral=True,
            )
        if not is_valid_image_url(self.image_url.value):
            return await interaction.response.send_message(
                "L'image doit commencer par `https://` ou `http://`.", ephemeral=True,
            )
        title, description = self.message_title.value.strip(), self.content.value.strip()
        footer, image_url = self.footer.value.strip(), self.image_url.value.strip()
        if not (title or description or image_url):
            return await interaction.response.send_message(
                "Indique au moins un titre, du texte ou une image.", ephemeral=True,
            )
        if len(title) + len(description) + len(footer) > 6000:
            return await interaction.response.send_message(
                "Le contenu de l'embed dépasse la limite de 6000 caractères.", ephemeral=True,
            )
        embed = discord.Embed(title=title or None, description=description or None, color=color)
        if footer:
            embed.set_footer(text=footer)
        if image_url:
            embed.set_image(url=image_url)
        try:
            message = await self.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            return await interaction.response.send_message(
                f"Je dois pouvoir envoyer des messages et des embeds dans {self.channel.mention}.",
                ephemeral=True,
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "Discord a refusé l'envoi du message.", ephemeral=True,
            )
        tracked = await track_message(message, interaction.user.id, embed)
        suffix = "" if tracked else " (Attention : suivi sur le panel indisponible.)"
        await interaction.response.send_message(
            f"✅ Message publié dans {self.channel.mention} : {message.jump_url}{suffix}",
            ephemeral=True,
        )


class EditMessageModal(discord.ui.Modal, title="Modifier le message du bot"):
    def __init__(self, message: discord.Message):
        super().__init__(timeout=600)
        self.message = message
        self.is_embed = bool(message.embeds)
        self.original_embed = message.embeds[0] if self.is_embed else None
        if self.is_embed:
            embed = self.original_embed
            inputs = (
                discord.ui.TextInput(label="Titre", required=False, max_length=256, default=embed.title or ""),
                discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph,
                                     required=False, max_length=4000, default=embed.description or ""),
                discord.ui.TextInput(label="Couleur (#RRGGBB)", required=False, max_length=7,
                                     default=f"#{embed.color.value:06X}" if embed.color else "#5865F2"),
                discord.ui.TextInput(label="Pied de page", required=False, max_length=2048,
                                     default=embed.footer.text or ""),
                discord.ui.TextInput(label="URL de l'image", required=False, max_length=1000,
                                     default=(embed.image.url or "")[:1000]),
            )
            self.message_title, self.description, self.color, self.footer, self.image_url = inputs
        else:
            inputs = (discord.ui.TextInput(
                label="Contenu du message", style=discord.TextStyle.paragraph,
                max_length=2000, default=message.content or "", required=True,
            ),)
            self.content = inputs[0]
        for item in inputs:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        # A second permission check makes previously opened modals safe if roles changed.
        if not await can_edit_message(interaction, self.message):
            return await interaction.response.send_message(
                "Tu n'as plus l'autorisation de modifier ce message.", ephemeral=True,
            )
        try:
            if self.is_embed:
                color = parse_embed_color(self.color.value)
                if color is None:
                    return await interaction.response.send_message(
                        "Couleur invalide. Utilise `#RRGGBB`.", ephemeral=True,
                    )
                title = self.message_title.value.strip()
                description = self.description.value.strip()
                footer = self.footer.value.strip()
                image_url = self.image_url.value.strip()
                if not is_valid_image_url(image_url):
                    return await interaction.response.send_message(
                        "L'image doit être une URL HTTP(S).", ephemeral=True,
                    )
                if not (title or description or image_url):
                    return await interaction.response.send_message(
                        "Conserve au moins un titre, une description ou une image.", ephemeral=True,
                    )
                if len(title) + len(description) + len(footer) > 6000:
                    return await interaction.response.send_message(
                        "Le contenu de l'embed dépasse 6000 caractères.", ephemeral=True,
                    )
                embed = discord.Embed(title=title or None, description=description or None, color=color)
                if footer:
                    embed.set_footer(text=footer)
                if image_url:
                    embed.set_image(url=image_url)
                # Keep an optional existing text body and do not alter other embeds.
                embeds = [embed, *self.message.embeds[1:]]
                updated = await self.message.edit(embeds=embeds, allowed_mentions=discord.AllowedMentions.none())
                panel_embed = embed
            else:
                updated = await self.message.edit(content=self.content.value.strip(),
                                        allowed_mentions=discord.AllowedMentions.none())
                panel_embed = None
        except discord.NotFound:
            return await interaction.response.send_message("Ce message n'existe plus.", ephemeral=True)
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.response.send_message(
                "Discord a refusé la modification. Vérifie les permissions du bot.", ephemeral=True,
            )

        tracked = await track_message(updated, interaction.user.id, panel_embed)
        suffix = "" if tracked else " (Suivi web indisponible.)"
        await interaction.response.send_message(
            f"✅ Message modifié : {self.message.jump_url}{suffix}", ephemeral=True,
        )


async def can_edit_message(interaction: discord.Interaction, message: discord.Message) -> bool:
    """Managers may edit bot messages; web editor roles may edit tracked ones."""
    member = interaction.user
    if interaction.guild is None or not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.manage_guild or member.guild_permissions.administrator:
        return True
    roles = set(await db.get_message_editor_roles(interaction.guild.id))
    if not roles.intersection(role.id for role in member.roles):
        return False
    return bool(await db.get_panel_message(interaction.guild.id, message.id))


class CustomMessages(commands.Cog):
    """Commandes de publication et d'édition depuis Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="message-send", description="[Admin] Publie un embed dans un salon.")
    @app_commands.describe(salon="Salon où publier le message")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def message_send(self, interaction: discord.Interaction, salon: discord.TextChannel):
        bot_member = interaction.guild.me
        if bot_member is None:
            return await interaction.response.send_message(
                "Impossible de vérifier mes permissions pour le moment.", ephemeral=True,
            )
        permissions = salon.permissions_for(bot_member)
        if not permissions.send_messages or not permissions.embed_links:
            return await interaction.response.send_message(
                f"Je dois pouvoir envoyer des messages et intégrer des liens dans {salon.mention}.",
                ephemeral=True,
            )
        await interaction.response.send_modal(CustomMessageModal(salon))

    @app_commands.command(name="message-edit", description="Modifie un message du bot via un formulaire prérempli.")
    @app_commands.describe(
        message="Lien du message Discord ou ID du message",
        salon="Salon contenant le message (nécessaire si tu utilises un ID seul)",
    )
    @app_commands.guild_only()
    async def message_edit(
        self, interaction: discord.Interaction, message: str,
        salon: discord.TextChannel | None = None,
    ):
        reference = parse_message_reference(message, interaction.guild.id, salon.id if salon else None)
        if reference is None:
            return await interaction.response.send_message(
                "Donne le **lien Discord du message**, ou son **ID** en précisant `salon`.",
                ephemeral=True,
            )
        channel_id, message_id = reference
        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "Salon introuvable sur ce serveur.", ephemeral=True,
            )
        bot_member = interaction.guild.me
        if bot_member is None or not channel.permissions_for(bot_member).read_message_history:
            return await interaction.response.send_message(
                "Le bot doit pouvoir lire l'historique de ce salon.", ephemeral=True,
            )
        try:
            target = await channel.fetch_message(message_id)
        except discord.NotFound:
            return await interaction.response.send_message("Message introuvable.", ephemeral=True)
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.response.send_message(
                "Impossible d'accéder à ce message. Vérifie les permissions du bot.", ephemeral=True,
            )
        if self.bot.user is None or target.author.id != self.bot.user.id:
            return await interaction.response.send_message(
                "Je peux modifier uniquement **mes propres messages**.", ephemeral=True,
            )
        if target.components:
            return await interaction.response.send_message(
                "Ce message contient des boutons ou menus interactifs : modifie-le via sa fonctionnalité d'origine.",
                ephemeral=True,
            )
        if len(target.embeds) > 1:
            return await interaction.response.send_message(
                "Ce message comporte plusieurs embeds et ne peut pas être modifié avec ce formulaire.",
                ephemeral=True,
            )
        if not await can_edit_message(interaction, target):
            return await interaction.response.send_message(
                "Permission **Gérer le serveur** ou rôle éditeur autorisé sur le panel requis. "
                "Les rôles éditeurs peuvent modifier uniquement les messages suivis.",
                ephemeral=True,
            )
        if target.embeds and (len(target.embeds[0].description or "") > 4000 or
                              len(target.embeds[0].image.url or "") > 1000):
            return await interaction.response.send_message(
                "Cet embed est trop long pour le formulaire Discord. Utilise le panel web.",
                ephemeral=True,
            )
        if not target.embeds and not target.content:
            return await interaction.response.send_message(
                "Ce message ne contient pas de texte ou d'embed modifiable.", ephemeral=True,
            )
        await interaction.response.send_modal(EditMessageModal(target))

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            message = "Tu dois posséder la permission **Gérer le serveur**."
        else:
            logger.error("Erreur CustomMessages : %s", error, exc_info=True)
            message = "Une erreur est survenue pendant la gestion du message."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomMessages(bot))
