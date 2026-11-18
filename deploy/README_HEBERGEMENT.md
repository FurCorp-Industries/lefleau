# 🌐 Héberger le bot H24 gratuitement (Oracle Cloud Always Free)

Ce guide t'explique comment faire tourner ton bot en continu, sans dépendre
de ton PC, en utilisant l'offre **Always Free** d'Oracle Cloud — un vrai
serveur (VPS) gratuit à vie, avec stockage persistant (compatible SQLite).

> ⚠️ Pourquoi pas Replit / Render gratuit ? Leur système de fichiers n'est
> **pas persistant** sur le tier gratuit : ta base `economy.db` (soldes,
> primes, fruits...) serait effacée à chaque redémarrage du service. Oracle
> Cloud te donne un vrai disque qui garde tes données.

---

## Étape 1 — Créer ton compte Oracle Cloud

1. Va sur https://www.oracle.com/cloud/free/ et crée un compte.
2. Une carte bancaire est demandée pour vérification d'identité — **tu ne
   seras jamais facturé** tant que tu restes dans les limites "Always Free".
3. Choisis une région proche de chez toi (ex: `eu-paris-1` ou `eu-marseille-1`
   pour la France) au moment de l'inscription — ce choix est définitif pour
   ton compte, donc prends le temps de bien choisir.

## Étape 2 — Créer l'instance (le serveur)

1. Dans la console OCI, va dans **Compute → Instances → Create Instance**.
2. **Image** : clique sur *Edit* → *Change Image* → choisis **Ubuntu**
   (la version 22.04 ou 24.04 LTS).
3. **Shape** : choisis **Ampere (VM.Standard.A1.Flex)** — c'est le processeur
   ARM gratuit. Configure-le avec par exemple 2 OCPU / 8 Go de RAM (largement
   suffisant pour ce bot, qui consomme très peu de ressources).
4. Si tu as un message d'avertissement du style *"Out of capacity"*, c'est
   fréquent — réessaie plus tard, ou change de "domaine de disponibilité"
   dans la même région.
5. Dans **Add SSH keys**, laisse Oracle générer une paire de clés et
   **télécharge la clé privée** (`.key`) — c'est ce qui te permettra de te
   connecter au serveur.
6. Clique sur **Create**. Après ~1 minute, ton serveur est prêt et tu as son
   adresse IP publique affichée sur la page de l'instance.

## Étape 3 — Se connecter au serveur en SSH

Depuis PowerShell (Windows) ou un terminal :

```powershell
ssh -i "chemin\vers\ta-cle.key" ubuntu@IP_DE_TON_SERVEUR
```

(Remplace `IP_DE_TON_SERVEUR` par l'adresse IP publique affichée dans la
console Oracle.)

## Étape 4 — Envoyer les fichiers du bot sur le serveur

Depuis ton PC, dans le dossier qui contient `onepiece-bot` :

```powershell
scp -i "chemin\vers\ta-cle.key" -r onepiece-bot ubuntu@IP_DE_TON_SERVEUR:~/
```

Ça copie tout le dossier du bot sur le serveur, dans `~/onepiece-bot`.

## Étape 5 — Installer et lancer le bot

Reconnecte-toi en SSH (étape 3), puis :

```bash
cd ~/onepiece-bot
chmod +x deploy/setup_server.sh
./deploy/setup_server.sh
```

Ce script installe Python, crée l'environnement virtuel et installe les
dépendances automatiquement. Ensuite, configure ton token :

```bash
cp .env.example .env
nano .env
```

Colle ton `DISCORD_TOKEN` (et éventuellement `GUILD_ID`), puis `Ctrl+X`,
`Y`, `Entrée` pour sauvegarder et quitter nano.

## Étape 6 — Installer le service H24 (systemd)

C'est ce qui garde le bot **actif en permanence**, même si tu fermes la
session SSH, et le **relance automatiquement** en cas de crash ou de
redémarrage du serveur :

```bash
sudo cp deploy/onepiece-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable onepiece-bot
sudo systemctl start onepiece-bot
```

## Étape 7 — Vérifier que ça tourne

```bash
sudo systemctl status onepiece-bot
```

Tu dois voir `active (running)` en vert. Pour voir les logs en direct
(utile pour déboguer) :

```bash
journalctl -u onepiece-bot -f
```

(`Ctrl+C` pour quitter la vue des logs — ça n'arrête pas le bot, juste
l'affichage.)

---

## 🔁 Mettre à jour le bot plus tard

Quand tu modifies le code (nouvelle commande, correction de bug...) :

```powershell
# Depuis ton PC : renvoie les fichiers modifiés
scp -i "ta-cle.key" -r onepiece-bot ubuntu@IP_DE_TON_SERVEUR:~/
```

```bash
# Sur le serveur : redémarre le service pour appliquer les changements
sudo systemctl restart onepiece-bot
```

## 💾 Sauvegarder régulièrement ta base de données

Même avec un disque persistant, c'est une bonne habitude de sauvegarder
`data/economy.db` de temps en temps (au cas où tu casses quelque chose en
bidouillant le serveur) :

```powershell
scp -i "ta-cle.key" ubuntu@IP_DE_TON_SERVEUR:~/onepiece-bot/data/economy.db ./backup-economy.db
```

---

## 🆘 Commandes utiles

| Commande | Effet |
|---|---|
| `sudo systemctl restart onepiece-bot` | Redémarre le bot |
| `sudo systemctl stop onepiece-bot` | Arrête le bot |
| `sudo systemctl status onepiece-bot` | Voir si le bot tourne |
| `journalctl -u onepiece-bot -f` | Voir les logs en direct |
| `journalctl -u onepiece-bot -n 100` | Voir les 100 dernières lignes de logs |

---

## Alternative si Oracle Cloud ne fonctionne pas pour toi

Si l'inscription Oracle pose problème (refus, capacité indisponible dans ta
région...), l'alternative la plus simple reste **Replit + UptimeRobot**
(gratuit), mais avec une réserve importante : le système de fichiers de
Replit n'est **pas garanti persistant à 100%** sur le tier gratuit — pense à
sauvegarder `economy.db` régulièrement si tu pars sur cette option. Dis-moi
si tu veux que je te prépare ce guide-là aussi.
