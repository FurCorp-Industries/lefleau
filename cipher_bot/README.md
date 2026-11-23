# Cipher Bot

Bot Discord autonome de restructuration, modération, sécurité, tickets, rôles, niveaux, rappels et sondages. Il fonctionne séparément de `onepiece-bot` : il utilise son propre token, ses propres données (`cipher_bot/data.json`) et son service `cipher-bot`.

Le tableau web intégré reprend les fonctions web du bot : gestion des serveurs autorisés, messages de restructuration, salons temporaires, annonces, envoi de messages, bannissement, inactifs, restructuration, journaux et paramètres de sécurité.

## Déploiement

1. Crée une seconde application/bot dans le portail Discord et active les intents **Server Members** et **Message Content**.
2. Ajoute `https://cipher.lefleau.online/callback` dans les Redirects OAuth2 de cette application.
3. Copie `.env.example` vers `.env`, renseigne uniquement les nouveaux secrets et mets le fichier en permission `600`.
4. Installe le service et le proxy fournis dans `deploy/`.

Ne copie jamais `start.bat`, `data.json` ni les secrets provenant de l'archive d'origine.
