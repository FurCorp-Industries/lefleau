"""
cogs/boss.py
--------------
Système de combat communautaire : un boss unique par serveur, que tous
les membres peuvent attaquer. Quand il est vaincu, le butin est partagé
selon les dégâts infligés par chacun, et le boss suivant apparaît.
"""

import random

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from data.bosses import BOSS_ROSTER
from utils.helpers import (
    format_berrys,
    format_duration,
    format_hp_bar,
    get_fruits_combat_bonus,
    get_fruits_effect_value,
    get_equipped_fruits_and_levels,
)
from utils.boss_rewards import calculate_mvp_bonus, calculate_reward_pool


async def _ensure_boss(guild_id: int) -> dict:
    """Récupère le boss actuel du serveur, ou en crée un (le premier du roster) s'il n'existe pas encore."""
    boss = await db.get_boss(guild_id)
    if boss is None:
        first = BOSS_ROSTER[0]
        await db.set_boss(guild_id, 0, first["name"], first["max_hp"])
        boss = await db.get_boss(guild_id)
    return boss


def _boss_emoji(name: str) -> str:
    """Retrouve l'emoji associé à un boss du roster à partir de son nom (fallback générique sinon)."""
    for boss in BOSS_ROSTER:
        if boss["name"] == name:
            return boss["emoji"]
    return "👹"


async def _spawn_next_boss(guild_id: int) -> dict:
    """Fait apparaître le boss suivant du roster (boucle sur le premier après le dernier)."""
    current = await db.get_boss(guild_id)
    next_index = (current["boss_index"] + 1) % len(BOSS_ROSTER)
    next_boss = BOSS_ROSTER[next_index]
    await db.set_boss(guild_id, next_index, next_boss["name"], next_boss["max_hp"])
    return await db.get_boss(guild_id)


class Boss(commands.Cog):
    """Commandes de combat communautaire contre un boss."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /boss
    # ------------------------------------------------------------------
    @app_commands.command(name="boss", description="Affiche le boss actuel du serveur.")
    async def boss(self, interaction: discord.Interaction):
        boss = await _ensure_boss(interaction.guild_id)
        emoji = _boss_emoji(boss["name"])

        ranking = await db.get_boss_damage_ranking(interaction.guild_id)
        reward_pool = calculate_reward_pool(boss["max_hp"], config.BOSS_REWARD_SCALING)
        mvp_bonus = calculate_mvp_bonus(
            reward_pool,
            config.BOSS_MVP_BONUS_RATIO,
            config.BOSS_MVP_BONUS_MIN,
            config.BOSS_MVP_BONUS_MAX,
        )
        top_text = "Personne n'a encore attaqué ce boss !"
        if ranking:
            lines = []
            for i, (user_id, damage) in enumerate(ranking[:5], start=1):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"Joueur {user_id}"
                lines.append(f"{i}. **{name}** — {damage} dégâts")
            top_text = "\n".join(lines)

        embed = discord.Embed(
            title=f"{emoji} {boss['name']}",
            description=(
                f"{format_hp_bar(boss['current_hp'], boss['max_hp'])}\n"
                f"**{boss['current_hp']} / {boss['max_hp']} PV**"
            ),
            color=config.COLOR_ERROR,
        )
        embed.add_field(name="🏆 Meilleurs combattants", value=top_text, inline=False)
        embed.add_field(
            name="💰 Butin potentiel",
            value=(
                f"**{format_berrys(reward_pool)}** partagés selon les dégâts\n"
                f"Bonus MVP : **{format_berrys(mvp_bonus)}**"
            ),
            inline=False,
        )
        embed.set_footer(text="Utilise /attack pour rejoindre le combat !")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /attack
    # ------------------------------------------------------------------
    @app_commands.command(name="attack", description="Attaque le boss actuel du serveur !")
    async def attack(self, interaction: discord.Interaction):
        user_id, guild_id = interaction.user.id, interaction.guild_id
        user = await db.get_user(user_id, guild_id)
        equipped_fruits, fruit_levels = await get_equipped_fruits_and_levels(user_id, guild_id)

        reduction = min(get_fruits_effect_value(equipped_fruits, "cooldown_reduction", fruit_levels), 0.9)
        effective_cooldown = config.ATTACK_COOLDOWN * (1 - reduction)

        remaining = db.get_cooldown_remaining(user.get("last_attack"), effective_cooldown)
        if remaining > 0:
            embed = discord.Embed(
                title="⏳ Encore fatigué du dernier assaut",
                description=f"Tu pourras réattaquer dans **{format_duration(remaining)}**.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        boss = await _ensure_boss(guild_id)
        boss_index_before = boss["boss_index"]

        await db.set_cooldown(user_id, guild_id, "last_attack")

        combat_bonus = get_fruits_combat_bonus(equipped_fruits, fruit_levels)
        damage = random.randint(config.ATTACK_MIN, config.ATTACK_MAX)
        damage = int(damage * (1 + combat_bonus))

        new_hp = await db.damage_boss(guild_id, damage)
        await db.add_boss_damage(guild_id, user_id, damage)

        message = random.choice(config.ATTACK_MESSAGES).format(boss=boss["name"], damage=damage)

        embed = discord.Embed(
            title=f"⚔️ Attaque sur {boss['name']}",
            description=f"{message}\n\n{format_hp_bar(new_hp, boss['max_hp'])}\n**{new_hp} / {boss['max_hp']} PV**",
            color=config.COLOR_SUCCESS,
        )
        if combat_bonus:
            embed.set_footer(text=f"Bonus de combat de ton fruit : +{int(combat_bonus * 100)}%")

        await interaction.response.send_message(embed=embed)

        # --- Le boss est-il vaincu ? ---
        if new_hp <= 0:
            # Vérifie qu'un autre combattant n'a pas déjà traité la mort de ce boss
            # entre-temps (petite protection contre les doubles récompenses en cas
            # d'attaques quasi simultanées).
            current_check = await db.get_boss(guild_id)
            if current_check["boss_index"] == boss_index_before:
                await self._handle_boss_defeat(interaction, boss)

    async def _handle_boss_defeat(self, interaction: discord.Interaction, boss: dict):
        """Distribue les récompenses et fait apparaître le boss suivant."""
        guild_id = interaction.guild_id
        ranking = await db.get_boss_damage_ranking(guild_id)
        total_damage = sum(dmg for _, dmg in ranking) or 1
        reward_pool = calculate_reward_pool(boss["max_hp"], config.BOSS_REWARD_SCALING)
        mvp_bonus = calculate_mvp_bonus(
            reward_pool,
            config.BOSS_MVP_BONUS_RATIO,
            config.BOSS_MVP_BONUS_MIN,
            config.BOSS_MVP_BONUS_MAX,
        )

        reward_lines = []
        for i, (user_id, damage) in enumerate(ranking):
            share = int(reward_pool * damage / total_damage)
            if i == 0:
                share += mvp_bonus

            await db.update_wallet(user_id, guild_id, share)
            await db.update_bounty(user_id, guild_id, int(share * config.BOSS_BOUNTY_RATIO))

            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"Joueur {user_id}"
            mvp_tag = " 👑 MVP" if i == 0 else ""
            if i < 5:
                reward_lines.append(f"**{name}**{mvp_tag} — {format_berrys(share)} ({damage} dégâts)")

        if len(ranking) > 5:
            reward_lines.append(f"*Et {len(ranking) - 5} autre(s) combattant(s) récompensé(s).*")

        await db.clear_boss_damage(guild_id)
        next_boss = await _spawn_next_boss(guild_id)
        next_emoji = _boss_emoji(next_boss["name"])

        victory_embed = discord.Embed(
            title=f"🎉 {boss['name']} vaincu !",
            description="Le butin est réparti selon les dégâts infligés :\n\n" + "\n".join(reward_lines),
            color=config.COLOR_SUCCESS,
        )
        victory_embed.add_field(
            name="👹 Un nouveau boss apparaît...",
            value=f"{next_emoji} **{next_boss['name']}** — {next_boss['max_hp']} PV",
            inline=False,
        )
        await interaction.followup.send(embed=victory_embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Boss(bot))
