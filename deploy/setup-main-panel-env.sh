#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/onepiece-bot

read -r -p "Client ID de l'application Discord du bot principal : " PANEL_ID
read -r -s -p "Client Secret OAuth2 de cette application : " PANEL_SECRET
echo

if [ -z "$PANEL_ID" ] || [ -z "$PANEL_SECRET" ]; then
    echo "Le Client ID et le Client Secret sont obligatoires."
    exit 1
fi

SESSION_SECRET="$(openssl rand -hex 32)"
TEMP_ENV="$(mktemp)"
trap 'rm -f "$TEMP_ENV"' EXIT

if [ -f .env ]; then
    grep -vE '^(PANEL_ENABLED|PANEL_CLIENT_ID|PANEL_CLIENT_SECRET|PANEL_BASE_URL|PANEL_SESSION_SECRET|PANEL_HOST|PANEL_PORT|PANEL_PREFIX|PANEL_COOKIE_DOMAIN)=' .env > "$TEMP_ENV" || true
fi

printf '%s\n' \
    "PANEL_ENABLED=true" \
    "PANEL_CLIENT_ID=$PANEL_ID" \
    "PANEL_CLIENT_SECRET=$PANEL_SECRET" \
    "PANEL_BASE_URL=https://panel.lefleau.online/le-fleau" \
    "PANEL_SESSION_SECRET=$SESSION_SECRET" \
    "PANEL_HOST=127.0.0.1" \
    "PANEL_PORT=8082" \
    "PANEL_PREFIX=le-fleau" \
    "PANEL_COOKIE_DOMAIN=.lefleau.online" >> "$TEMP_ENV"

install -m 600 "$TEMP_ENV" .env
unset PANEL_SECRET SESSION_SECRET
echo "Configuration du panel principal enregistrée dans .env."
