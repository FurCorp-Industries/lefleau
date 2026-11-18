"""
data/fleets.py
----------------
Flottes du serveur. Chaque flotte correspond à un rôle Discord précis.
La liste est triée de la flotte la PLUS puissante à la MOINS puissante :
si un membre possède plusieurs rôles de flotte (normalement rare), c'est
la plus puissante qui est affichée en priorité sur son /profile.

⚠️ IMPORTANT : "role_name" doit correspondre EXACTEMENT au nom du rôle
Discord sur ton serveur (la comparaison ignore la casse et les accents,
mais pas les mots en trop). Ex: si ton rôle s'appelle "Les Fléaux Des
Mers", il faut bien écrire "Les Fléaux Des Mers" ici, pas juste "Fléaux
des Mers". Seule "Les Fléaux De La Galaxie" (Flotte 3) a été confirmée
d'après une capture d'écran de tes rôles — vérifie que les 3 autres
noms ci-dessous collent bien à tes rôles réels, et corrige si besoin.
"""

FLEETS = [
    {"role_name": "Les Fléaux Des Mers", "display_name": "Fléaux des Mers"},          # Flotte 1
    {"role_name": "Les Fléaux Des Aurores", "display_name": "Fléaux Des Aurores"},     # Flotte 2
    {"role_name": "Les Fléaux De La Galaxie", "display_name": "Fléaux de la Galaxie"},  # Flotte 3 (confirmé)
    {"role_name": "Les Fléaux De La Guerre", "display_name": "Fléaux de la Guerre"},    # Flotte 4
]
