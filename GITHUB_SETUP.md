# Publier sur GitHub (dépôt privé recommandé)

Ce dossier contient le code de **OnePiece Bot V3.0.3**, préparé pour un dépôt Git.

## Sécurité

Ne publiez jamais votre `.env`, le token Discord, les secrets OAuth, les bases SQLite, les logs ou les sauvegardes du VPS. Le `.gitignore` exclut ces fichiers. L'exemple `.env.example` ne contient que des valeurs de démonstration. Avant un premier push, vérifiez les fichiers indexés : `git status --short` et `git diff --cached --name-only`. Si un secret a été publié, révoquez-le immédiatement auprès du fournisseur.

## Créer le dépôt privé via GitHub CLI

1. Installer et authentifier `gh` (GitHub CLI) : `gh auth login`.
2. Ouvrir un terminal dans ce dossier.
3. Lancer :

```bash
git init
git add .
git commit -m "Initial import: OnePiece Bot v3.0.3"
gh repo create onepiece-discord-bot --private --source=. --remote=origin --push
```

Si un dépôt GitHub existe déjà, configurez plutôt son URL comme `origin` et poussez la branche souhaitée.

## Mise à jour du serveur

Utilisez un clone de travail et une méthode de déploiement avec sauvegarde. **Ne remplacez jamais le `.env` ou la base SQLite du VPS par des fichiers GitHub.** Exécutez les tests et vérifiez les journaux `systemd` après déploiement.
