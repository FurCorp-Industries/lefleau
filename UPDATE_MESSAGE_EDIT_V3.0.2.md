# V3.0.2 — Edition des messages depuis Discord

## Nouvelle commande

`/message-edit message:<lien Discord> [salon]`

- Copie le lien d'un message publié par le bot (clic droit / appui long → Copier le lien du message).
- Utilise `/message-edit` et colle le lien dans `message`.
- Le formulaire s'ouvre avec les champs de l'embed déjà remplis : titre, description, couleur, pied de page, URL de l'image.
- Si le message est un message texte classique (sans embed), le formulaire affiche directement son contenu.
- Tu peux aussi indiquer un ID de message, en précisant obligatoirement le `salon`.
- Enregistre : le bot modifie le message existant (même ID et même lien), puis actualise le suivi du panel web.

### Accès
- Utilisateur ayant « Gérer le serveur » : peut modifier les messages non interactifs de ce bot.
- Rôle « éditeur de messages » défini sur le panel : peut modifier uniquement les messages suivis en base.
- Autres utilisateurs : accès refusé.
- Jamais de modification de messages écrits par une autre personne ou par un autre bot.
- Messages avec boutons ou menus non modifiables depuis ce formulaire, pour ne pas détruire des interfaces de tickets/giveaways.
- Messages avec plusieurs embeds non pris en charge.

### Compatibilité
- `/message-send` reste disponible et suit désormais ses messages dans le panel web.
- Le correctif V3.0.1 de `cogs/web_panel.py` est intégré dans le ZIP complet.
- Les anciennes commandes de modération restent directes.
- Le changelog passe à V3.0.2.
- Aucun changement requis dans `.env` ni dans la base de données (schéma existant de V3.0).

## Installation du patch léger
Depuis le dossier où tu as placé `onepiece-message-edit-patch-v3.0.2.zip` :

```bash
unzip -o onepiece-message-edit-patch-v3.0.2.zip -d /tmp/onepiece-message-edit
bash /tmp/onepiece-message-edit/install.sh
```

Le script crée une sauvegarde des fichiers remplacés, vérifie la compilation, puis redémarre `onepiece-bot`.

Si ton panel a toujours le bug 502 de la V3.0 d'origine, le patch contient également le `web_panel.py` corrigé.
