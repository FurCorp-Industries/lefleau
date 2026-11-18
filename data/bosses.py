"""
data/bosses.py
-----------------
Roster des boss combattus via /boss et /attack. Le bot fait défiler cette
liste dans l'ordre : quand un boss est vaincu, le suivant apparaît
automatiquement. Une fois le dernier vaincu, ça reboucle sur le premier.

Pour ajouter/retirer un boss ou changer ses PV, modifie directement
BOSS_ROSTER ci-dessous.
"""

BOSS_ROSTER = [
    {"name": "Arlong", "emoji": "🦈", "max_hp": 4000},
    {"name": "Crocodile", "emoji": "🏜️", "max_hp": 9000},
    {"name": "Enel", "emoji": "⚡", "max_hp": 15000},
    {"name": "Doflamingo", "emoji": "🦩", "max_hp": 25000},
    {"name": "Katakuri", "emoji": "🍡", "max_hp": 40000},
    {"name": "Kaido", "emoji": "🐉", "max_hp": 70000},
    {"name": "Big Mom", "emoji": "🍰", "max_hp": 70000},
    {"name": "Blackbeard", "emoji": "🖤", "max_hp": 100000},
    {"name": "Im-sama", "emoji": "👁️", "max_hp": 200000},
]
