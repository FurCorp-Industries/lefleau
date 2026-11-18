"""
utils/cards.py
-----------------
Moteur de cartes partagé entre les jeux de casino (/blackjack, /poker) :
paquet de cartes, calcul de valeur blackjack, évaluation de main de poker.
"""

import random
from collections import Counter

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUES = {rank: index + 2 for index, rank in enumerate(RANKS)}  # 2..14 (As haut)


class Deck:
    """Paquet de 52 cartes mélangé, avec pioche simple."""

    def __init__(self):
        self.cards = [(rank, suit) for rank in RANKS for suit in SUITS]
        random.shuffle(self.cards)

    def draw(self, n: int = 1) -> list[tuple[str, str]]:
        """Pioche n cartes du dessus du paquet et les retire du paquet."""
        drawn, self.cards = self.cards[:n], self.cards[n:]
        return drawn


def card_str(card: tuple[str, str]) -> str:
    """Représentation textuelle d'une carte, ex: 'K♠'."""
    rank, suit = card
    return f"{rank}{suit}"


def hand_str(cards: list[tuple[str, str]]) -> str:
    """Représentation textuelle d'une main de cartes, séparées par des espaces."""
    return "  ".join(card_str(c) for c in cards)


# --- Blackjack ---

def blackjack_value(cards: list[tuple[str, str]]) -> int:
    """Calcule la valeur d'une main au blackjack (As = 1 ou 11 automatiquement)."""
    total = 0
    aces = 0
    for rank, _ in cards:
        if rank == "A":
            total += 11
            aces += 1
        elif rank in ("J", "Q", "K"):
            total += 10
        else:
            total += int(rank)

    while total > 21 and aces > 0:
        total -= 10
        aces -= 1

    return total


def is_blackjack(cards: list[tuple[str, str]]) -> bool:
    """Vrai si la main est un blackjack naturel (21 avec exactement 2 cartes)."""
    return len(cards) == 2 and blackjack_value(cards) == 21


# --- Poker (vidéo-poker façon "Jacks or Better") ---

# Table des gains : multiplicateur de la mise selon la main obtenue
POKER_PAYOUTS = {
    "royal_flush": 250,
    "straight_flush": 50,
    "four_of_a_kind": 25,
    "full_house": 9,
    "flush": 6,
    "straight": 4,
    "three_of_a_kind": 3,
    "two_pair": 2,
    "jacks_or_better": 1,
    "nothing": 0,
}

POKER_HAND_NAMES = {
    "royal_flush": "Quinte Flush Royale",
    "straight_flush": "Quinte Flush",
    "four_of_a_kind": "Carré",
    "full_house": "Full House",
    "flush": "Couleur",
    "straight": "Suite",
    "three_of_a_kind": "Brelan",
    "two_pair": "Double Paire",
    "jacks_or_better": "Paire de Valets ou mieux",
    "nothing": "Rien (carte haute)",
}


def evaluate_poker_hand(cards: list[tuple[str, str]]) -> str:
    """
    Évalue une main de 5 cartes et retourne la clé de la combinaison obtenue
    (voir POKER_PAYOUTS pour la liste des clés possibles).
    """
    ranks = sorted((RANK_VALUES[rank] for rank, _ in cards), reverse=True)
    suits = [suit for _, suit in cards]
    rank_counts = Counter(ranks)
    counts = sorted(rank_counts.values(), reverse=True)
    is_flush = len(set(suits)) == 1

    unique_ranks = sorted(set(ranks), reverse=True)
    is_straight = False
    is_wheel = False  # quinte "roue" : As-2-3-4-5 (As compte comme carte basse)
    if len(unique_ranks) == 5:
        if unique_ranks[0] - unique_ranks[4] == 4:
            is_straight = True
        elif unique_ranks == [14, 5, 4, 3, 2]:
            is_straight = True
            is_wheel = True

    if is_straight and is_flush:
        if unique_ranks[0] == 14 and not is_wheel:
            return "royal_flush"
        return "straight_flush"

    if counts[0] == 4:
        return "four_of_a_kind"

    if counts[0] == 3 and counts[1] == 2:
        return "full_house"

    if is_flush:
        return "flush"

    if is_straight:
        return "straight"

    if counts[0] == 3:
        return "three_of_a_kind"

    if counts[0] == 2 and counts[1] == 2:
        return "two_pair"

    if counts[0] == 2:
        pair_rank = next(rank for rank, count in rank_counts.items() if count == 2)
        if pair_rank >= RANK_VALUES["J"]:
            return "jacks_or_better"
        return "nothing"

    return "nothing"
