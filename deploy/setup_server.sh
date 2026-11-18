#!/bin/bash
# =============================================================
# setup_server.sh
# ---------------------------------------------------------------
# Script d'installation automatique du bot One Piece sur un
# serveur Ubuntu fraîchement créé (Oracle Cloud Always Free, ou
# n'importe quel autre VPS Ubuntu 22.04/24.04).
#
# À exécuter UNE FOIS, après avoir uploadé le dossier onepiece-bot
# sur le serveur (voir README_HEBERGEMENT.md pour le détail complet).
#
# Utilisation :
#   chmod +x setup_server.sh
#   ./setup_server.sh
# =============================================================

set -e  # arrête le script à la moindre erreur

echo "🏴‍☠️ Installation du bot One Piece sur le serveur..."

# --- 1. Mise à jour du système et installation des dépendances ---
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# --- 2. Création de l'environnement virtuel Python ---
cd ~/onepiece-bot
python3 -m venv venv
source venv/bin/activate

# --- 3. Installation des dépendances du bot ---
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Dépendances installées."
echo ""
echo "⚠️  N'oublie pas de créer ton fichier .env avant de continuer :"
echo "    cp .env.example .env"
echo "    nano .env    (colle ton DISCORD_TOKEN et ton GUILD_ID)"
echo ""
echo "Ensuite, installe le service systemd avec :"
echo "    sudo cp deploy/onepiece-bot.service /etc/systemd/system/"
echo "    sudo systemctl daemon-reload"
echo "    sudo systemctl enable onepiece-bot"
echo "    sudo systemctl start onepiece-bot"
echo ""
echo "🎉 Une fois lancé, le bot tournera H24, même après un redémarrage du serveur."
