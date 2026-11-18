"""
data/titles.py
----------------
Titres affichés sur le /profile, débloqués automatiquement en fonction de
la prime (bounty) du joueur — plus ta prime grimpe, plus ton titre est
impressionnant. La liste est triée par seuil croissant.

Pour changer les seuils ou les noms, modifie directement TITLES ci-dessous.
"""

TITLES = [
    (0, "Moussaillon Inconnu"),
    (750_000, "Pirate en Herbe"),
    (3_000_000, "Brigand des Mers"),
    (10_000_000, "Pirate Redouté"),
    (30_000_000, "Terreur des Sept Mers"),
    (75_000_000, "Fléaux des Mers"),
    (150_000_000, "Empereur Déchu"),
    (350_000_000, "Seigneur des Abysses"),
    (700_000_000, "Roi sans Couronne"),
    (1_500_000_000, "Dieu de Grand Line"),
]


def get_title(bounty: int) -> str:
    """Retourne le titre correspondant à une prime donnée."""
    title = TITLES[0][1]
    for threshold, name in TITLES:
        if bounty >= threshold:
            title = name
        else:
            break
    return title
