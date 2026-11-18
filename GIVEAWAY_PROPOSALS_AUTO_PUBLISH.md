# Giveaway proposals — publication automatique

## Membres

Dans **leur propre ticket**, les membres utilisent `/giveaways propose` et renseignent :

- `prize` : lot déjà configuré via `/points-admin item-add`
- `duration` : durée de 1 minute à 30 jours (`30m`, `2h`, `3d`, etc.)
- `channel` : salon texte public de publication
- `winners` : entre 1 et 20 (1 par défaut)
- `required_role` : rôle obligatoire, facultatif
- `bypass_role` : rôle pouvant contourner les conditions, facultatif
- `account_age` : ancienneté minimale du compte (`7d` ou `0`)
- `server_age` : ancienneté minimale dans le serveur (`3d` ou `0`)

Le bot publie une demande de validation dans le salon de logs des tickets et un message de suivi dans le ticket.

## Staff

Cliquer sur **Approve & publish** dans les logs, utiliser `/giveaways proposal-approve <proposition_id>` ou approuver depuis **Web > Points**.

Après approbation :
1. Le giveaway est immédiatement publié dans le salon choisi avec le bouton **Participer**.
2. Il est enregistré dans les giveaways actifs : les vérifications de participation, le tirage de fin et les autres fonctions existantes restent opérationnels.
3. Les points configurés pour le lot sont attribués à l'organisateur (et les rôles déblocables sont évalués).
4. Les messages de validation et de suivi sont actualisés, avec le lien du giveaway.

Cliquer sur **Refuser** ou `/giveaways proposal-deny` ne crée rien et n'attribue pas de points.

## Configuration

- Configurer les logs de tickets dans le système existant.
- Configurer au moins un lot pour les propositions.
- Vérifier les permissions du bot dans le salon public : voir le salon, envoyer des messages, intégrer des liens.
- L'autorisation **Gérer le serveur** est requise pour approuver/refuser, également depuis le panel web.
- Les données existantes sont conservées : les colonnes manquantes sont ajoutées au démarrage.
- Une proposition créée avec l'ancienne version ne contient pas les paramètres requis pour publication automatique. Elle doit être refusée et reproposée avec la nouvelle commande.

## Sécurité et limites

- Une seule proposition en attente par ticket.
- Un verrou protège les validations simultanées (bouton Discord, commande ou panel web) dans le processus du bot.
- L'approbation et l'enregistrement du giveaway sont effectués en une transaction SQLite ; si l'enregistrement échoue, le bot tente de retirer le message public déjà envoyé.
- En cas de redémarrage ou de panne réseau précisément entre l'envoi du message et sa sauvegarde, une vérification manuelle des messages peut être nécessaire.
- Aucune nouvelle commande slash racine : `/giveaways propose`, `/giveaways proposal-approve` et `/giveaways proposal-deny` restent les mêmes.
