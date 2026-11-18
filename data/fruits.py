"""
data/fruits.py
----------------
Catalogue statique des Fruits du Démon disponibles dans la boutique.
Chaque fruit a un "effect" (clé technique utilisée dans les Cogs pour
appliquer le boost économique) et une "value" (intensité du boost),
plus un "combat_bonus" optionnel (bonus de dégâts en % lors des
combats de boss, voir cogs/boss.py).

Effets économiques reconnus par le code :
- "work_boost"           : multiplie les gains de /work
- "cooldown_reduction"    : réduit tous les cooldowns (daily/work/crime/attack)
- "crime_boost"           : augmente le gain max lors d'un /crime réussi
- "daily_double_chance"    : chance de doubler le gain du /daily
- "crime_fine_reduction"   : réduit la probabilité de se faire choper (et l'amende)

Prix relevés (~x3) en juillet 2026 : entre les quêtes, le casino et les
combats de boss, les fruits étaient devenus trop accessibles.
"""

FRUITS = {
    "gomu_gomu": {
        "id": "gomu_gomu",
        "name": "Gomu Gomu no Mi",
        "type": "Paramecia",
        "emoji": "🔴",
        "price": 15000,
        "description": "Ton corps devient élastique comme du caoutchouc.",
        "bonus_text": "+15% de gains sur /work",
        "effect": "work_boost",
        "value": 0.15,
        "combat_bonus": 0.05,
    },
    "mera_mera": {
        "id": "mera_mera",
        "name": "Mera Mera no Mi",
        "type": "Logia",
        "emoji": "🔥",
        "price": 20000,
        "description": "Ton corps se transforme en flammes vivantes.",
        "bonus_text": "-20% sur tous les cooldowns (daily/work/crime/attack)",
        "effect": "cooldown_reduction",
        "value": 0.20,
        "combat_bonus": 0.15,
    },
    "gura_gura": {
        "id": "gura_gura",
        "name": "Gura Gura no Mi",
        "type": "Paramecia",
        "emoji": "💥",
        "price": 30000,
        "description": "Le fruit le plus destructeur du monde, capable de fissurer le monde lui-même.",
        "bonus_text": "+30% sur le butin maximum obtenu lors d'un /crime réussi",
        "effect": "crime_boost",
        "value": 0.30,
        "combat_bonus": 0.25,
    },
    "ope_ope": {
        "id": "ope_ope",
        "name": "Ope Ope no Mi",
        "type": "Paramecia",
        "emoji": "💠",
        "price": 24000,
        "description": "Le fruit du chirurgien de la mort, crée un espace où tout devient possible.",
        "bonus_text": "25% de chances de doubler les gains du /daily",
        "effect": "daily_double_chance",
        "value": 0.25,
        "combat_bonus": 0.05,
    },
    "yami_yami": {
        "id": "yami_yami",
        "name": "Yami Yami no Mi",
        "type": "Logia",
        "emoji": "🌑",
        "price": 35000,
        "description": "Le fruit maudit des ténèbres, il attire tout vers le néant... même la poisse.",
        "bonus_text": "-50% de chances de se faire attraper par la Marine lors d'un /crime",
        "effect": "crime_fine_reduction",
        "value": 0.50,
        "combat_bonus": 0.10,
    },
    "suna_suna": {
        "id": "suna_suna",
        "name": "Suna Suna no Mi",
        "type": "Logia",
        "emoji": "🏜️",
        "price": 18000,
        "description": "Ton corps se transforme en sable, capable d'assécher tout ce qu'il touche.",
        "bonus_text": "+20% de gains sur /work",
        "effect": "work_boost",
        "value": 0.20,
        "combat_bonus": 0.10,
    },
    "hie_hie": {
        "id": "hie_hie",
        "name": "Hie Hie no Mi",
        "type": "Logia",
        "emoji": "❄️",
        "price": 25000,
        "description": "Ton corps se transforme en glace, capable de geler une mer entière.",
        "bonus_text": "-30% de chances de se faire attraper par la Marine lors d'un /crime",
        "effect": "crime_fine_reduction",
        "value": 0.30,
        "combat_bonus": 0.15,
    },
    "goro_goro": {
        "id": "goro_goro",
        "name": "Goro Goro no Mi",
        "type": "Logia",
        "emoji": "⚡",
        "price": 45000,
        "description": "Ton corps se transforme en foudre, l'un des fruits les plus redoutés du monde.",
        "bonus_text": "-30% sur tous les cooldowns (daily/work/crime/attack)",
        "effect": "cooldown_reduction",
        "value": 0.30,
        "combat_bonus": 0.30,
    },
}


def get_fruit(fruit_id: str) -> dict | None:
    """Retourne les données d'un fruit à partir de son identifiant, ou None."""
    return FRUITS.get(fruit_id)
