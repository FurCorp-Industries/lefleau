#!/bin/bash
set -euo pipefail

ENV_FILE="/home/ubuntu/onepiece-bot/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Erreur : $ENV_FILE est introuvable."
    exit 1
fi

read -r -p "Client ID Roblox : " CLIENT_ID
read -r -s -p "Client Secret Roblox (masqué) : " CLIENT_SECRET
echo
read -r -p "ID du rôle Discord Vérifié (Entrée pour aucun) : " ROLE_ID

if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ]; then
    echo "Erreur : le Client ID et le Client Secret sont obligatoires."
    exit 1
fi

TMP_FILE=$(mktemp)
trap 'rm -f "$TMP_FILE"' EXIT
grep -vE '^(ROBLOX_CLIENT_ID|ROBLOX_CLIENT_SECRET|ROBLOX_REDIRECT_URI|PUBLIC_BASE_URL|ROBLOX_WEB_HOST|ROBLOX_WEB_PORT|ROBLOX_VERIFIED_ROLE_ID)=' "$ENV_FILE" > "$TMP_FILE" || true

{
    echo
    echo "# Liaison Roblox OAuth 2.0"
    printf 'ROBLOX_CLIENT_ID=%s\n' "$CLIENT_ID"
    printf 'ROBLOX_CLIENT_SECRET=%s\n' "$CLIENT_SECRET"
    echo 'ROBLOX_REDIRECT_URI=https://verify.lefleau.online/roblox/callback'
    echo 'PUBLIC_BASE_URL=https://verify.lefleau.online'
    echo 'ROBLOX_WEB_HOST=127.0.0.1'
    echo 'ROBLOX_WEB_PORT=8080'
    printf 'ROBLOX_VERIFIED_ROLE_ID=%s\n' "$ROLE_ID"
} >> "$TMP_FILE"

sudo install -o ubuntu -g ubuntu -m 600 "$TMP_FILE" "$ENV_FILE"
unset CLIENT_SECRET
echo "Configuration Roblox enregistrée dans $ENV_FILE avec permissions 600."
