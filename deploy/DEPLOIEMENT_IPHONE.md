# 📱 Déployer sur Oracle Cloud depuis un iPhone (sans PC)

Ce guide permet de tout faire depuis **Safari**, en utilisant le **Cloud
Shell** intégré à la console Oracle Cloud — pas besoin d'installer une
app SSH séparée ni de gérer un fichier de clé sur ton téléphone.

---

## Étape 1 — Compte Oracle Cloud

Sur https://www.oracle.com/cloud/free/, crée ton compte (carte bancaire
demandée pour vérification, jamais facturée en restant "Always Free").
Choisis une région proche de la France (`eu-paris-1` ou `eu-marseille-1`).

💡 Astuce Safari : active *"Demander la version pour ordinateur"* (bouton
"aA" dans la barre d'adresse) pour que la console Oracle s'affiche
correctement sur mobile.

## Étape 2 — Ouvrir le Cloud Shell et générer une clé SSH

1. Une fois connecté à la console OCI, tape sur l'icône **Cloud Shell**
   (icône de terminal `>_` en haut de l'écran). Un terminal s'ouvre dans
   ton navigateur — patiente, ça prend quelques secondes à démarrer.
2. Dans ce terminal, tape :
   ```
   ssh-keygen -t rsa -N "" -f ~/.ssh/onepiece_key
   ```
3. Affiche la clé publique et garde-la sous les yeux (tu vas la copier
   au prochain écran) :
   ```
   cat ~/.ssh/onepiece_key.pub
   ```
   Sélectionne tout le texte affiché (`ssh-rsa AAAA...`) et copie-le.

## Étape 3 — Créer l'instance (le serveur)

1. Menu ☰ → **Compute → Instances → Create Instance**.
2. **Image** : Edit → Change Image → **Ubuntu** (22.04 ou 24.04 LTS).
3. **Shape** : **Ampere (VM.Standard.A1.Flex)** — 2 OCPU / 8-12 Go RAM
   suffisent largement.
4. Section **Add SSH keys** : choisis **"Paste public keys"**, colle la
   clé publique copiée à l'étape 2.
5. Clique sur **Create**. Après ~1 minute, note l'**adresse IP publique**
   affichée sur la page de l'instance (tu en auras besoin partout).

*(Si tu as une erreur "Out of capacity", réessaie plus tard ou change de
domaine de disponibilité dans la même région.)*

## Étape 4 — Envoyer le bot sur le serveur

D'abord, télécharge le fichier `onepiece-bot.zip` (partagé dans notre
conversation) sur ton iPhone — il atterrit normalement dans
**Fichiers → Téléchargements**.

Retourne dans le **Cloud Shell** (toujours dans le navigateur) :

1. Clique sur l'icône **⋮** (ou l'icône d'upload) dans la barre d'outils
   du Cloud Shell → **Upload**. Choisis `onepiece-bot.zip` depuis
   l'app Fichiers de ton iPhone. Il est maintenant dans le stockage du
   Cloud Shell.
2. Envoie-le vers ton serveur avec `scp` (remplace `IP_INSTANCE`) :
   ```
   scp -i ~/.ssh/onepiece_key onepiece-bot.zip ubuntu@IP_INSTANCE:~/
   ```
   Tape `yes` si on te demande de confirmer la connexion.

## Étape 5 — Se connecter au serveur et tout installer

Toujours dans le Cloud Shell :

```
ssh -i ~/.ssh/onepiece_key ubuntu@IP_INSTANCE
```

Une fois connecté (le prompt change pour `ubuntu@instance:~$`) :

```
sudo apt update
sudo apt install -y unzip python3 python3-venv python3-pip
unzip onepiece-bot.zip
cd onepiece-bot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Étape 6 — Configurer le token (sans nano, plus simple au clavier tactile)

```
cat > .env << 'EOF'
DISCORD_TOKEN=colle_ton_token_ici
GUILD_ID=colle_ton_id_serveur_ici
EOF
```

Remplace `colle_ton_token_ici` par ton vrai token avant de valider (tu
peux coller depuis où tu l'as sauvegardé — appui long → Coller dans le
terminal du Cloud Shell fonctionne).

## Étape 7 — Lancer le bot en service permanent

```
sudo cp deploy/onepiece-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable onepiece-bot
sudo systemctl start onepiece-bot
sudo systemctl status onepiece-bot
```

Tu dois voir `active (running)` en vert. Pour voir les logs en direct :

```
journalctl -u onepiece-bot -f
```
(`Ctrl+C` pour quitter la vue des logs, ça n'arrête pas le bot.)

---

## ℹ️ À savoir

- Le **panel de contrôle en terminal** (`console.py`) ne fonctionnera
  pas via systemd (pas de terminal interactif attaché) — c'est normal,
  le bot le détecte tout seul et continue de tourner sans lui.
- Une fois le Cloud Shell fermé (ou ta session Safari terminée), ton
  **serveur continue de tourner** — le Cloud Shell n'était qu'un pont
  pour t'y connecter, il n'héberge rien lui-même.
- Pour te reconnecter plus tard : rouvre le Cloud Shell depuis la
  console OCI, puis refais `ssh -i ~/.ssh/onepiece_key ubuntu@IP_INSTANCE`
  (la clé reste stockée dans ton Cloud Shell d'une session à l'autre).
