"""
data/materials.py
--------------------
Matériaux obtenus via /quest, utilisés pour améliorer les Fruits du Démon
via /enhance. Chaque matériau a une "drop_chance" (probabilité d'obtention
à chaque quête réussie) — la somme de toutes les drop_chance doit faire 1.0.
"""

MATERIALS = {
    "kairoseki": {
        "id": "kairoseki",
        "name": "Éclat de Kairoseki",
        "emoji": "🪨",
        "rarity": "Commun",
        "drop_chance": 0.50,
    },
    "log_pose": {
        "id": "log_pose",
        "name": "Fragment de Log Pose",
        "emoji": "🧭",
        "rarity": "Peu commun",
        "drop_chance": 0.30,
    },
    "poneglyph": {
        "id": "poneglyph",
        "name": "Fragment de Poneglyphe",
        "emoji": "🗿",
        "rarity": "Rare",
        "drop_chance": 0.15,
    },
    "adam_wood": {
        "id": "adam_wood",
        "name": "Bois d'Adam",
        "emoji": "🌳",
        "rarity": "Épique",
        "drop_chance": 0.05,
    },
}


def get_material(material_id: str) -> dict | None:
    return MATERIALS.get(material_id)


def roll_material() -> str:
    """Tire un matériau au hasard selon les probabilités définies (drop_chance)."""
    import random

    roll = random.random()
    cumulative = 0.0
    for material_id, data in MATERIALS.items():
        cumulative += data["drop_chance"]
        if roll <= cumulative:
            return material_id
    return list(MATERIALS.keys())[-1]  # filet de sécurité (arrondis flottants)
