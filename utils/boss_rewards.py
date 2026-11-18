"""Calculs purs utilisés pour équilibrer les récompenses des boss."""

from collections.abc import Iterable


def calculate_reward_pool(
    max_hp: int,
    scaling: Iterable[tuple[int | None, float]],
) -> int:
    """Calcule le butin commun avec la première tranche de PV applicable."""
    if max_hp <= 0:
        return 0

    for hp_limit, berry_per_hp in scaling:
        if hp_limit is None or max_hp <= hp_limit:
            return int(max_hp * berry_per_hp)

    raise RuntimeError("Le barème des boss ne contient aucune tranche finale")


def calculate_mvp_bonus(
    reward_pool: int,
    ratio: float,
    minimum: int,
    maximum: int,
) -> int:
    """Calcule le bonus MVP proportionnel, puis applique son plancher/plafond."""
    if reward_pool <= 0:
        return 0
    return min(maximum, max(minimum, int(reward_pool * ratio)))
