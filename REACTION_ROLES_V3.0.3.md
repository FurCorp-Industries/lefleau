# OnePiece Bot V3.0.3 — Reaction Roles

Le cog `cogs/reaction_roles.py` ajoute un système persistant de rôles par réactions.

## Commandes (permission **Gérer les rôles**)

- `/reaction-roles create channel:#roles title:"Choisis tes rôles"` : publie l'embed.
- `/reaction-roles add message_id:123... emoji:🎮 role:@Gamer` : lie un emoji au rôle ; répéter pour d'autres emojis.
- `/reaction-roles remove message_id:123... emoji:🎮` : supprime le lien.
- `/reaction-roles list` : affiche les panneaux et associations.
- `/reaction-roles delete message_id:123...` : désactive le panneau sans supprimer le message.

L'ID du panneau est retourné lors de la création (il se trouve aussi dans **Copier l'identifiant du message** dans Discord, mode développeur).

### Comportement

- Ajouter la réaction : le rôle est attribué.
- Enlever la réaction : le rôle est retiré.
- Réactions natives et emojis personnalisés utilisables par le bot.
- Les paramètres sont conservés dans SQLite, même après redémarrage.
- Une modification d'association n'affecte pas rétroactivement les utilisateurs ayant déjà réagi ; ils doivent enlever puis remettre leur réaction.
- Supprimer une association ou un panneau ne retire pas les rôles déjà donnés.
- Maximum de 20 emojis par panneau.

### Permissions

Le bot doit posséder **Gérer les rôles**, **Voir le salon**, **Envoyer des messages**, **Intégrer des liens**, **Ajouter des réactions** et **Lire l'historique**. Son rôle principal doit être **au-dessus** des rôles attribués. Les **Server Members Intent** doivent être activés dans le portail développeur Discord (déjà utilisés par le bot).

## Installation patch

Transfère l'archive patch sur le VPS, puis :

```bash
cd /home/ubuntu
unzip -o onepiece-reaction-roles-patch-v3.0.3.zip -d reaction-patch
bash reaction-patch/install.sh
```

Le script sauvegarde les fichiers concernés dans `/home/ubuntu/onepiece-bot/.reaction-role-backups/` et vérifie la syntaxe avant de redémarrer `onepiece-bot`.

Aucune modification du fichier `.env`, des tickets ou des données existantes n'est nécessaire.
