#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/onepiece-bot

if [ ! -f .env ] || ! grep -qE '^PANEL_CLIENT_ID=.+$' .env || ! grep -qE '^PANEL_CLIENT_SECRET=.+$' .env; then
    echo "Configure d'abord le panel principal : ses identifiants OAuth2 seront réutilisés."
    exit 1
fi

read -r -p "ID Discord du propriétaire (plusieurs IDs séparés par des virgules) : " OWNER_IDS
if ! printf '%s' "$OWNER_IDS" | grep -qE '^[0-9]+(,[0-9]+)*$'; then
    echo "Format invalide. Exemple : 123456789012345678,987654321098765432"
    exit 1
fi

SESSION_SECRET="$(openssl rand -hex 32)"
TEMP_ENV="$(mktemp)"
trap 'rm -f "$TEMP_ENV"' EXIT

grep -vE '^(OWNER_PANEL_ENABLED|OWNER_PANEL_USER_IDS|OWNER_PANEL_BASE_URL|OWNER_PANEL_SESSION_SECRET|OWNER_PANEL_HOST|OWNER_PANEL_PORT|OWNER_PANEL_CLIENT_ID|OWNER_PANEL_CLIENT_SECRET)=' .env > "$TEMP_ENV" || true

printf '%s\n' \
    "OWNER_PANEL_ENABLED=true" \
    "OWNER_PANEL_USER_IDS=$OWNER_IDS" \
    "OWNER_PANEL_BASE_URL=https://owner.lefleau.online" \
    "OWNER_PANEL_SESSION_SECRET=$SESSION_SECRET" \
    "OWNER_PANEL_HOST=127.0.0.1" \
    "OWNER_PANEL_PORT=8083" >> "$TEMP_ENV"

install -m 600 "$TEMP_ENV" .env
unset SESSION_SECRET
echo "Configuration du panel Owner enregistrée dans .env."
echo "Ajoute maintenant https://owner.lefleau.online/auth/callback aux Redirects OAuth2 de Discord."
