"""
cogs/casino.py
-----------------
Jeux de casino classiques sur le thème de Baratie/Sabaody : roulette,
blackjack et poker vidéo (façon "Jacks or Better").
"""

import random

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
from utils.cards import (
    Deck,
    blackjack_value,
    is_blackjack,
    evaluate_poker_hand,
    card_str,
    hand_str,
    POKER_PAYOUTS,
    POKER_HAND_NAMES,
)
from utils.helpers import format_berrys


# ------------------------------------------------------------------
# Validation commune des mises
# ------------------------------------------------------------------

async def validate_bet(interaction: discord.Interaction, mise: int) -> bool:
    """
    Vérifie que la mise est valide (montant autorisé + fonds suffisants).
    Envoie un message d'erreur et retourne False si ce n'est pas le cas.
    """
    if mise < config.CASINO_MIN_BET or mise > config.CASINO_MAX_BET:
        embed = discord.Embed(
            title="❌ Mise invalide",
            description=(
                f"La mise doit être comprise entre {format_berrys(config.CASINO_MIN_BET)} "
                f"et {format_berrys(config.CASINO_MAX_BET)}."
            ),
            color=config.COLOR_ERROR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    user = await db.get_user(interaction.user.id, interaction.guild_id)
    if user["wallet"] < mise:
        embed = discord.Embed(
            title="💸 Fonds insuffisants",
            description=f"Tu n'as que {format_berrys(user['wallet'])}, impossible de miser {format_berrys(mise)}.",
            color=config.COLOR_ERROR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    return True


# ------------------------------------------------------------------
# Blackjack : logique de résolution pure (testable sans Discord)
# ------------------------------------------------------------------

def resolve_blackjack(
    bet: int,
    player_value: int,
    dealer_value: int,
    player_bust: bool,
    dealer_bust: bool,
    player_natural: bool,
    dealer_natural: bool,
) -> tuple[int, str]:
    """
    Détermine l'issue d'une partie de blackjack.
    Retourne (gain_net, résultat) où gain_net est le montant à ajouter
    au portefeuille (négatif en cas de défaite, 0 en cas d'égalité).
    """
    if player_natural and dealer_natural:
        return 0, "push"
    if player_natural:
        return int(bet * (config.BLACKJACK_NATURAL_MULTIPLIER - 1)), "blackjack"
    if dealer_natural:
        return -bet, "lose"
    if player_bust:
        return -bet, "bust"
    if dealer_bust:
        return bet, "win"
    if player_value > dealer_value:
        return bet, "win"
    if player_value < dealer_value:
        return -bet, "lose"
    return 0, "push"


BLACKJACK_RESULT_TEXT = {
    "push": "🤝 Égalité — ta mise t'est rendue.",
    "blackjack": "🃏 BLACKJACK NATUREL ! Paiement bonus !",
    "lose": "💀 Le croupier gagne.",
    "bust": "💥 Tu as dépassé 21, tu perds la main.",
    "win": "🎉 Tu bats le croupier !",
}


class BlackjackView(discord.ui.View):
    """Vue interactive du blackjack : boutons Tirer / Rester."""

    def __init__(self, author_id: int, guild_id: int, bet: int, deck: Deck,
                 player_cards: list, dealer_cards: list):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.guild_id = guild_id
        self.bet = bet
        self.deck = deck
        self.player_cards = player_cards
        self.dealer_cards = dealer_cards
        self.message: discord.Message | None = None
        self.resolved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce n'est pas ta partie !", ephemeral=True)
            return False
        return True

    def _build_embed(self, reveal_dealer: bool, result: str | None = None, net: int = 0) -> discord.Embed:
        player_val = blackjack_value(self.player_cards)
        embed = discord.Embed(title="🃏 Blackjack", color=config.COLOR_SHOP)
        embed.add_field(
            name=f"Ta main ({player_val})",
            value=hand_str(self.player_cards),
            inline=False,
        )

        if reveal_dealer:
            dealer_val = blackjack_value(self.dealer_cards)
            embed.add_field(
                name=f"Main du croupier ({dealer_val})",
                value=hand_str(self.dealer_cards),
                inline=False,
            )
        else:
            embed.add_field(
                name="Main du croupier (?)",
                value=f"{card_str(self.dealer_cards[0])}  🂠",
                inline=False,
            )

        embed.add_field(name="💰 Mise", value=format_berrys(self.bet), inline=True)

        if result:
            embed.add_field(name="Résultat", value=BLACKJACK_RESULT_TEXT[result], inline=True)
            sign = "+" if net > 0 else ""
            embed.add_field(name="Gain net", value=f"{sign}{format_berrys(net)}", inline=True)
            embed.color = config.COLOR_SUCCESS if net > 0 else (config.COLOR_ERROR if net < 0 else config.COLOR_MARINE)

        return embed

    async def _finish(self, interaction: discord.Interaction, reveal_dealer: bool, result: str, net: int):
        self.resolved = True
        for child in self.children:
            child.disabled = True
        await db.update_wallet(self.author_id, self.guild_id, net)
        embed = self._build_embed(reveal_dealer=reveal_dealer, result=result, net=net)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Tirer", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player_cards.append(self.deck.draw(1)[0])
        value = blackjack_value(self.player_cards)

        if value > 21:
            net, result = resolve_blackjack(self.bet, value, 0, True, False, False, False)
            await self._finish(interaction, reveal_dealer=True, result=result, net=net)
            return

        embed = self._build_embed(reveal_dealer=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Rester", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        while blackjack_value(self.dealer_cards) < 17:
            self.dealer_cards.append(self.deck.draw(1)[0])

        player_value = blackjack_value(self.player_cards)
        dealer_value = blackjack_value(self.dealer_cards)
        dealer_bust = dealer_value > 21

        net, result = resolve_blackjack(
            self.bet, player_value, dealer_value, False, dealer_bust, False, False
        )
        await self._finish(interaction, reveal_dealer=True, result=result, net=net)

    async def on_timeout(self):
        if self.resolved or self.message is None:
            return
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass


# ------------------------------------------------------------------
# Poker vidéo
# ------------------------------------------------------------------

class PokerView(discord.ui.View):
    """Vue interactive du poker vidéo : 5 cartes à garder/défausser, puis tirage."""

    def __init__(self, author_id: int, guild_id: int, bet: int, deck: Deck, hand: list):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.guild_id = guild_id
        self.bet = bet
        self.deck = deck
        self.hand = hand
        self.held = [False] * 5
        self.message: discord.Message | None = None
        self.resolved = False

        self.card_buttons: list[discord.ui.Button] = []
        for i, card in enumerate(hand):
            btn = discord.ui.Button(label=card_str(card), style=discord.ButtonStyle.secondary, row=0)
            btn.callback = self._make_toggle(i, btn)
            self.add_item(btn)
            self.card_buttons.append(btn)

        draw_btn = discord.ui.Button(label="Tirer", style=discord.ButtonStyle.primary, emoji="🃏", row=1)
        draw_btn.callback = self._on_draw
        self.add_item(draw_btn)
        self.draw_button = draw_btn

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce n'est pas ta partie !", ephemeral=True)
            return False
        return True

    def _build_embed(self, final: bool = False, hand_key: str | None = None, net: int = 0) -> discord.Embed:
        embed = discord.Embed(title="🎰 Poker Vidéo", color=config.COLOR_SHOP)
        cards_display = "   ".join(
            (f"🔒{card_str(c)}" if self.held[i] else card_str(c)) for i, c in enumerate(self.hand)
        )
        embed.add_field(name="Ta main", value=cards_display, inline=False)
        embed.add_field(name="💰 Mise", value=format_berrys(self.bet), inline=True)

        if not final:
            embed.set_footer(text="Clique sur les cartes à garder (🔒), puis sur Tirer.")
        else:
            hand_name = POKER_HAND_NAMES.get(hand_key, "Rien")
            embed.add_field(name="Main obtenue", value=hand_name, inline=True)
            sign = "+" if net > 0 else ""
            embed.add_field(name="Gain net", value=f"{sign}{format_berrys(net)}", inline=True)
            embed.color = config.COLOR_SUCCESS if net > 0 else (config.COLOR_ERROR if net < 0 else config.COLOR_MARINE)

        return embed

    def _make_toggle(self, index: int, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("Ce n'est pas ta partie !", ephemeral=True)
                return
            self.held[index] = not self.held[index]
            button.style = discord.ButtonStyle.success if self.held[index] else discord.ButtonStyle.secondary
            await interaction.response.edit_message(embed=self._build_embed(), view=self)
        return callback

    async def _on_draw(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce n'est pas ta partie !", ephemeral=True)
            return

        for i in range(5):
            if not self.held[i]:
                self.hand[i] = self.deck.draw(1)[0]

        hand_key = evaluate_poker_hand(self.hand)
        multiplier = POKER_PAYOUTS.get(hand_key, 0)
        net = int(self.bet * (multiplier - 1)) if multiplier > 0 else -self.bet

        await db.update_wallet(self.author_id, self.guild_id, net)

        self.resolved = True
        for child in self.children:
            child.disabled = True

        embed = self._build_embed(final=True, hand_key=hand_key, net=net)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        if self.resolved or self.message is None:
            return
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass


# ------------------------------------------------------------------
# Roulette : logique de résolution pure (testable sans Discord)
# ------------------------------------------------------------------

def parse_roulette_bet(pari: str) -> tuple[str, object] | None:
    """Parse le pari du joueur. Retourne (type_pari, valeur) ou None si invalide."""
    p = pari.strip().lower()

    if p.isdigit() and 0 <= int(p) <= 36:
        return ("number", int(p))
    if p in ("rouge", "red"):
        return ("color", "red")
    if p in ("noir", "black"):
        return ("color", "black")
    if p in ("pair", "even"):
        return ("parity", "even")
    if p in ("impair", "odd"):
        return ("parity", "odd")
    if p in ("manque", "low"):
        return ("range", "low")
    if p in ("passe", "high"):
        return ("range", "high")
    return None


def spin_roulette(bet_type: str, value, result: int) -> tuple[bool, int]:
    """
    Détermine si le pari est gagnant pour un numéro tiré donné.
    Retourne (gagné, multiplicateur_total_si_gagné).
    """
    if result == 0:
        color, parity, rng = "green", None, None
    else:
        color = "red" if result in config.ROULETTE_RED_NUMBERS else "black"
        parity = "even" if result % 2 == 0 else "odd"
        rng = "low" if result <= 18 else "high"

    if bet_type == "number":
        return (value == result), config.ROULETTE_STRAIGHT_MULTIPLIER
    if bet_type == "color":
        return (value == color), config.ROULETTE_EVEN_CHANCE_MULTIPLIER
    if bet_type == "parity":
        return (value == parity), config.ROULETTE_EVEN_CHANCE_MULTIPLIER
    if bet_type == "range":
        return (value == rng), config.ROULETTE_EVEN_CHANCE_MULTIPLIER
    return False, 0


ROULETTE_SUGGESTIONS = [
    ("🔴 Rouge", "rouge"),
    ("⚫ Noir", "noir"),
    ("Pair", "pair"),
    ("Impair", "impair"),
    ("Manque (1-18)", "manque"),
    ("Passe (19-36)", "passe"),
] + [(str(n), str(n)) for n in range(37)]


async def roulette_bet_autocomplete(interaction: discord.Interaction, current: str):
    current = current.lower()
    matches = [
        app_commands.Choice(name=name, value=value)
        for name, value in ROULETTE_SUGGESTIONS
        if current in name.lower() or current in value.lower()
    ]
    return matches[:25]


# ------------------------------------------------------------------
# Le Cog
# ------------------------------------------------------------------

class Casino(commands.Cog):
    """Jeux de casino : /roulette, /blackjack, /poker."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /roulette
    # ------------------------------------------------------------------
    @app_commands.command(name="roulette", description="Joue à la roulette (rouge/noir, pair/impair, ou un numéro précis).")
    @app_commands.describe(
        mise="Montant à miser",
        pari="rouge, noir, pair, impair, manque, passe, ou un numéro (0-36)",
    )
    @app_commands.autocomplete(pari=roulette_bet_autocomplete)
    async def roulette(self, interaction: discord.Interaction, mise: int, pari: str):
        if not await validate_bet(interaction, mise):
            return

        parsed = parse_roulette_bet(pari)
        if parsed is None:
            embed = discord.Embed(
                title="❌ Pari invalide",
                description="Utilise `rouge`, `noir`, `pair`, `impair`, `manque`, `passe`, ou un numéro entre 0 et 36.",
                color=config.COLOR_ERROR,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        bet_type, value = parsed
        result = random.randint(0, 36)
        won, multiplier = spin_roulette(bet_type, value, result)

        color = "green" if result == 0 else ("red" if result in config.ROULETTE_RED_NUMBERS else "black")
        color_emoji = {"red": "🔴", "black": "⚫", "green": "🟢"}[color]

        if won:
            payout = mise * multiplier
            net = payout - mise
        else:
            net = -mise

        await db.update_wallet(interaction.user.id, interaction.guild_id, net)

        embed = discord.Embed(
            title="🎡 Roulette",
            description=f"La bille s'arrête sur... **{result}** {color_emoji}",
            color=config.COLOR_SUCCESS if net > 0 else config.COLOR_ERROR,
        )
        embed.add_field(name="Ton pari", value=pari, inline=True)
        embed.add_field(name="💰 Mise", value=format_berrys(mise), inline=True)
        sign = "+" if net > 0 else ""
        embed.add_field(name="Résultat", value=f"{sign}{format_berrys(net)}", inline=True)
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # /blackjack
    # ------------------------------------------------------------------
    @app_commands.command(name="blackjack", description="Joue une main de blackjack contre le croupier.")
    @app_commands.describe(mise="Montant à miser")
    async def blackjack(self, interaction: discord.Interaction, mise: int):
        if not await validate_bet(interaction, mise):
            return

        deck = Deck()
        player_cards = deck.draw(2)
        dealer_cards = deck.draw(2)

        player_natural = is_blackjack(player_cards)
        dealer_natural = is_blackjack(dealer_cards)

        view = BlackjackView(interaction.user.id, interaction.guild_id, mise, deck, player_cards, dealer_cards)

        if player_natural or dealer_natural:
            net, result = resolve_blackjack(
                mise, blackjack_value(player_cards), blackjack_value(dealer_cards),
                False, False, player_natural, dealer_natural,
            )
            await db.update_wallet(interaction.user.id, interaction.guild_id, net)
            view.resolved = True
            for child in view.children:
                child.disabled = True
            embed = view._build_embed(reveal_dealer=True, result=result, net=net)
            await interaction.response.send_message(embed=embed, view=view)
            return

        embed = view._build_embed(reveal_dealer=False)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    # ------------------------------------------------------------------
    # /poker
    # ------------------------------------------------------------------
    @app_commands.command(name="poker", description="Joue au poker vidéo (garde tes meilleures cartes, façon Jacks or Better).")
    @app_commands.describe(mise="Montant à miser")
    async def poker(self, interaction: discord.Interaction, mise: int):
        if not await validate_bet(interaction, mise):
            return

        deck = Deck()
        hand = deck.draw(5)

        view = PokerView(interaction.user.id, interaction.guild_id, mise, deck, hand)
        embed = view._build_embed()
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(Casino(bot))
