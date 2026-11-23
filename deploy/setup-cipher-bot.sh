#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/home/ubuntu/cipher-bot
REPO_DIR=/home/ubuntu/onepiece-bot

if [ ! -d "$APP_DIR" ]; then
  echo "Crée d'abord $APP_DIR et copie-y le dossier cipher_bot de cette version."
  exit 1
fi

cd "$APP_DIR"
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "Renseigne $APP_DIR/.env avant de démarrer le service."
  exit 1
fi

chmod 600 .env
sudo install -m 644 "$REPO_DIR/deploy/cipher-bot.service" /etc/systemd/system/cipher-bot.service
sudo install -m 644 "$REPO_DIR/deploy/cipher.lefleau.online.conf" /etc/nginx/sites-available/cipher.lefleau.online
sudo ln -sfn /etc/nginx/sites-available/cipher.lefleau.online /etc/nginx/sites-enabled/cipher.lefleau.online
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now cipher-bot
sudo systemctl reload nginx

echo "Ensuite : sudo certbot --nginx -d cipher.lefleau.online"
