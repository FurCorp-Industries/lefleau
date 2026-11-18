> **Mise à jour des commandes :** 104 actions slash sont conservées, mais regroupées en 44 commandes racines. Voir [MIGRATION_COMMANDES.md](MIGRATION_COMMANDES.md) pour les anciens et nouveaux noms.

# 🏴‍☠️ One Piece Economy Bot

Bot Discord thématique One Piece avec système d'économie complet (Berrys ฿,
Fruits du Démon) et modération façon Marine. Basé sur `discord.py` 2.x et
les Slash Commands, avec persistance SQLite.

## Panel web du bot principal

Le panel unifié utilise Discord OAuth2 sur
`https://tickets panel.lefleau.online/le-fleau`. L'accueil permet de choisir entre
**Le Fleau** et **Lyrania**. L'espace Le Fleau permet de gérer l'économie,
les accès par rôles, l'anti-raid, les logs, les tickets, le registre des
sanctions, les giveaways et la boutique personnalisée de chaque serveur.
Les modifications économiques restent réservées
aux administrateurs Discord. Le service écoute uniquement sur `127.0.0.1:8082`
derrière Nginx et conserve toutes les données dans `data/economy.db`.

Le panel global Owner est séparé sur `https://owner.lefleau.online`. Il
écoute sur `127.0.0.1:8083`, utilise une session distincte et refuse tout
compte absent de `OWNER_PANEL_USER_IDS`. Il présente l'état du bot, les
statistiques globales et tous les serveurs, puis donne accès à leur page de
configuration. Un propriétaire peut générer une invitation temporaire de
10 minutes et utilisable une seule fois, si le bot possède la permission
« Créer une invitation » dans au moins un salon. Une zone dangereuse permet
aussi de faire quitter un serveur au bot après avoir recopié exactement son
nom; les données du serveur sont conservées. Le panel Owner peut également
supprimer tous les salons et catégories d'un serveur après une double
confirmation (nom exact du serveur et phrase contenant son ID). Cette action
irréversible n'est exposée dans aucun autre panel ni aucune commande Discord.
Une section **Blacklist globale** permet aussi d'enregistrer un ID Discord
avec un motif et de le bannir de tous les serveurs accessibles au bot. La
protection est persistante et rebannit automatiquement l'utilisateur s'il
rejoint plus tard. Retirer un ID de cette liste ne supprime volontairement pas
les bans locaux déjà appliqués.
Les fichiers de déploiement correspondants sont
`deploy/setup-owner-panel-env.sh` et `deploy/owner.lefleau.online.conf`.

---

## 📁 Structure du projet

```
onepiece-bot/
├── bot.py                  # Point d'entrée, chargement des Cogs, sync des slash commands
├── clear_commands.py        # Script à lancer 1 fois pour nettoyer d'anciennes slash commands
├── config.py                # Constantes de configuration (équilibrage économie, couleurs...)
├── database.py               # Couche d'accès SQLite (aiosqlite)
├── requirements.txt
├── .env.example              # Modèle de fichier d'environnement
├── data/
│   ├── economy.db            # Base SQLite (créée automatiquement au premier lancement)
│   ├── fruits.py              # Catalogue des Fruits du Démon (effets éco + bonus combat)
│   ├── titles.py                # Les 10 titres débloqués selon la prime
│   ├── fleets.py                 # Mapping rôle Discord -> Flotte
│   ├── bosses.py                  # Roster des boss (combats communautaires)
│   ├── materials.py                # Matériaux d'artisanat obtenus via /quest
│   ├── quests.py                     # Textes des quêtes (/quest)
│   ├── bloxfruits_items.py            # Listes fruits/épées/armes/styles pour /bloxfruits
│   └── changelog.py            # Historique des mises à jour (affiché par /changelog)
├── assets/
│   └── fonts/                  # Polices .ttf personnalisées (optionnel) pour l'affiche /profile
├── utils/
│   ├── helpers.py             # Fonctions utilitaires (formatage, effets, durées, flotte)
│   ├── image_gen.py            # Génération de l'affiche "avis de recherche" dynamique
│   └── cards.py                 # Deck, valeur blackjack, évaluation de mains de poker
└── cogs/
    ├── economy.py             # /daily /work /crime /pillage /balance /solde /profile /reset
    ├── shop.py                 # /shop /buy /inventory /eat /unequip /barbenoire
    ├── custom_shop.py          # Boutique et inventaire d'objets propres à chaque serveur
    ├── moderation.py           # /kick /ban /clear /timeout /mute
    ├── admin_economy.py        # /berrys-admin add /berrys-admin remove
    ├── info.py                  # /about /help /changelog
    ├── boss.py                   # /boss /attack
    ├── server_tags.py            # Tags de serveur et attribution automatique de rôles
    ├── custom_messages.py        # Publication de messages personnalisés par formulaire
    ├── casino.py                  # /roulette /blackjack /poker
    ├── quests.py                   # /quest /materials /enhance
    ├── tickets.py                    # /tickets open /tickets setup /tickets list /tickets remove
    ├── logs.py                        # /logs setup /logs disable /logs status
    └── bloxfruits.py                   # /bloxfruits /bloxfruits-profil /bloxfruits-liste
```

---

## 🗄️ Schéma de la base de données

La base est créée automatiquement au premier lancement (`database.init_db()`),
mais voici le schéma SQL pour référence :

```sql
-- Table des utilisateurs : solde, prime, fruit équipé, cooldowns
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    wallet INTEGER NOT NULL DEFAULT 500,
    bounty INTEGER NOT NULL DEFAULT 0,
    equipped_fruit TEXT DEFAULT NULL,
    last_daily TEXT DEFAULT NULL,
    last_work TEXT DEFAULT NULL,
    last_crime TEXT DEFAULT NULL,
    PRIMARY KEY (user_id, guild_id)
);

-- Table de l'inventaire : Fruits du Démon possédés par chaque joueur
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    fruit_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    UNIQUE(user_id, guild_id, fruit_id)
);
```

> 💡 Tout est scopé par `guild_id` : un même joueur a un solde différent sur
> chaque serveur où le bot est présent.

---

## 🚀 Installation

### 1. Prérequis
- Python 3.10 ou supérieur
- Un bot Discord créé sur le [Discord Developer Portal](https://discord.com/developers/applications)

### 2. Cloner / copier le projet et installer les dépendances

```bash
cd onepiece-bot
python -m venv venv

# Activation de l'environnement virtuel
source venv/bin/activate       # Linux / macOS
venv\Scripts\activate          # Windows

pip install -r requirements.txt
```

### 3. Créer ton application Discord

1. Va sur https://discord.com/developers/applications → **New Application**
2. Onglet **Bot** → **Reset Token** → copie le token (garde-le secret !)
3. Toujours dans l'onglet **Bot**, active l'intent **SERVER MEMBERS INTENT**
   (nécessaire pour `/kick`, `/ban`, `/timeout`...)
4. Onglet **OAuth2 → URL Generator** :
   - Scopes : `bot` + `applications.commands`
   - Permissions bot : `Kick Members`, `Ban Members`, `Moderate Members`,
     `Manage Messages`, `Send Messages`, `Embed Links`, `Read Message History`
   - Copie l'URL générée et ouvre-la dans ton navigateur pour inviter le bot
     sur ton serveur.

### 4. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Édite le fichier `.env` :

```env
DISCORD_TOKEN=ton_token_ici
GUILD_ID=id_de_ton_serveur   # optionnel, pour une sync instantanée en dev
```

### 5. Lancer le bot

```bash
python bot.py
```

Si tout se passe bien, tu devrais voir dans la console :

```
... Base de données initialisée.
... Extension chargée : cogs.economy
... Extension chargée : cogs.shop
... Extension chargée : cogs.moderation
... Extension chargée : cogs.admin_economy
... X commande(s) synchronisée(s) sur le serveur ...
... Connecté en tant que TonBot#1234 (ID: ...)
```

---

## 🎮 Liste des commandes

### Giveaways, anti-raid et synchronisation

| Commande | Description |
|---|---|
| `/giveaways create` | Crée un giveaway persistant avec durée, nombre de gagnants, rôle requis, rôle de bypass, âge minimal du compte et ancienneté minimale |
| `/giveaways end <message_id>` | Termine immédiatement un giveaway et effectue le tirage |
| `/giveaways reroll <message_id>` | Effectue un nouveau tirage parmi les participants |
| `/antiraid-config` | Configure le seuil d'arrivées, la fenêtre, l'âge minimal, les logs et le rôle exempté |
| `/sanctions-log-config` | Envoie une copie des nouvelles sanctions dans un salon central, éventuellement sur un autre serveur |
| `/sanctions-import` | Importe les bans et avertissements déjà existants dans le registre partagé |
| `/sanctions-search <utilisateur>` | Recherche les sanctions par pseudo, nom affiché, mention ou identifiant Discord |

Le giveaway et ses participations sont enregistrés dans SQLite : le tirage reprend donc après un redémarrage. Le rôle de bypass contourne le rôle requis, l'âge minimal du compte et l'ancienneté sur le serveur.

L'anti-raid ne sanctionne qu'après franchissement du seuil configuré et seulement les comptes plus récents que l'âge minimal choisi. Le bot doit avoir la permission **Bannir des membres** et son rôle doit être suffisamment haut.

La centralisation des sanctions est uniquement informative : elle ne bannit personne sur le serveur de destination. Pour envoyer les logs sur un autre serveur, le bot doit être présent sur les deux serveurs et l'auteur de la configuration doit être administrateur sur les deux. Les kicks historiques et timeouts expirés ne sont pas récupérables via Discord et ne peuvent donc pas être importés rétroactivement.

### Économie
| Commande | Description |
|---|---|
| `/daily` | Récompense quotidienne (500-1500฿, cooldown 24h) |
| `/work` | Travailler pour gagner des Berrys (200-800฿, cooldown 1h) |
| `/crime` ou `/pillage` | Coup risqué (800-2000฿, 60% de réussite, cooldown 2h) |
| `/balance` ou `/solde [membre]` | Affiche le solde |
| `/profile [membre]` | Profil complet (solde, prime, fruit équipé) |
| `/reset` | Remet tes données à zéro (solde, prime, fruits, cooldowns) — demande confirmation |

### Boutique & Fruits du Démon
| Commande | Description |
|---|---|
| `/shop` | Liste des fruits disponibles à l'achat |
| `/buy <fruit>` | Acheter un fruit |
| `/inventory` | Voir tes fruits possédés |
| `/eat <fruit>` | Équiper un fruit (un seul actif à la fois) |
| `/unequip [fruit]` | Déséquiper un fruit précis, ou tous si omis (reste dans l'inventaire) |
| `/barbenoire` | Débloque le multi-équipement de fruits (750 000฿, achat unique) |

### Boutique personnalisée par serveur

| Commande | Permission | Description |
|---|---|---|
| `/custom-shop item-add <nom> <prix> <description> [emoji]` | Gérer le serveur | Ajoute un objet, ou met à jour/réactive un objet portant le même nom |
| `/custom-shop item-remove <objet>` | Gérer le serveur | Retire l'objet de la vente sans l'effacer des inventaires existants |
| `/custom-shop item-list [inclure_desactives] [page]` | Gérer le serveur | Affiche la configuration du catalogue |
| `/custom-shop shop [page]` | Tout le monde | Affiche les objets vendus sur le serveur actuel |
| `/custom-shop buy <objet> [quantite]` | Tout le monde | Achète 1 à 99 exemplaires avec les Berrys du serveur |
| `/custom-shop inventory [membre] [page]` | Tout le monde | Affiche les objets personnalisés possédés |

Les catalogues, achats et inventaires sont isolés par serveur. `/reset`
supprime également l'inventaire personnalisé du joueur sur le serveur où
la commande est utilisée.

**Fruits disponibles :**

| Fruit | Type | Prix | Effet |
|---|---|---|---|
| 🔴 Gomu Gomu no Mi | Paramecia | 15 000฿ | +15% sur `/work` |
| 🏜️ Suna Suna no Mi | Logia | 18 000฿ | +20% sur `/work` |
| 🔥 Mera Mera no Mi | Logia | 20 000฿ | -20% sur tous les cooldowns |
| 💠 Ope Ope no Mi | Paramecia | 24 000฿ | 25% de chance de doubler le `/daily` |
| ❄️ Hie Hie no Mi | Logia | 25 000฿ | -30% de risque de se faire attraper |
| 💥 Gura Gura no Mi | Paramecia | 30 000฿ | +30% sur le butin max du `/crime` |
| 🌑 Yami Yami no Mi | Logia | 35 000฿ | -50% de risque de se faire attraper |
| ⚡ Goro Goro no Mi | Logia | 45 000฿ | -30% sur tous les cooldowns |

### 🖤 Passif Barbe Noire

Achat unique et très cher (`/barbenoire`, 750 000฿ par défaut, réglable
via `BARBE_NOIRE_PRICE` dans `config.py`) qui débloque la capacité
d'équiper **plusieurs Fruits du Démon en même temps**. Tous leurs bonus
s'additionnent sans limite (`/eat` ajoute un fruit au lieu de remplacer
l'ancien). `/reset` retire ce passif comme le reste.

### Modération (permissions requises)
| Commande | Permission requise | Description |
|---|---|---|
| `/kick <membre> [raison]` | Expulser des membres | Expulse un membre |
| `/ban <membre> [raison]` | Bannir des membres | Bannit un membre |
| `/unban <utilisateur> [raison]` | Bannir des membres | Débannit un utilisateur (autocomplétion sur les membres bannis) |
| `/warn <membre> <raison>` | Modérer les membres | Avertit un membre (MP automatique si possible) |
| `/warnings <membre>` | Modérer les membres | Affiche l'historique complet des avertissements |
| `/unwarn <membre> <avertissement>` | Modérer les membres | Retire un avertissement précis (autocomplétion) |
| `/clearwarns <membre>` | Modérer les membres | Efface tout le casier d'un membre |
| `/clear <nombre>` | Gérer les messages | Supprime 1-100 messages |
| `/lock [salon] [raison]` | Gérer les salons | Verrouille un salon (par défaut : le salon actuel) |
| `/unlock [salon] [raison]` | Gérer les salons | Déverrouille — restaure l'état exact d'avant, pas un simple reset |
| `/modperms [membre]` | Gérer le serveur | Vérifie les permissions de modération d'un membre (et via quel rôle) |
| `/modroles` | Gérer le serveur | Audite tous les rôles ayant une permission de modération |
| `/timeout` ou `/mute <membre> <durée> [raison]` | Modérer les membres | Timeout (ex: durée = `10m`, `1h`, `2d`) |
| `/unmute` ou `/untimeout <membre> [raison]` | Modérer les membres | Lève une sourdine avant son terme |

### Système de Logs (Gérer le serveur)
| Commande | Description |
|---|---|
| `/logs setup <catégorie> <salon>` | Active une catégorie de logs dans un salon précis |
| `/logs disable <catégorie>` | Désactive une catégorie (garde le salon en mémoire) |
| `/logs status` | Affiche l'état de toutes les catégories |

Catégories disponibles, chacune activable dans un salon différent (ou le
même) : **Messages** (suppressions/modifications), **Membres**
(arrivées/départs/bans/rôles/pseudo/mute), **Salons**
(création/suppression/modification), **Rôles**
(création/suppression/modification), **Vocal**
(connexions/déconnexions/changements de salon), **Serveur** (nom/icône),
**Boosts** (annonce automatique quand un membre booste le serveur, avec
le nombre total de boosts et le niveau du serveur).

Les messages envoyés par des bots ne sont jamais journalisés dans la
catégorie "Messages" (évite le bruit des embeds temporaires). Les autres
catégories journalisent tout, sans exception.

⚠️ **Nécessite l'intent privilégié "MESSAGE CONTENT INTENT"** activé sur
le [Developer Portal](https://discord.com/developers/applications) (onglet
Bot, comme "SERVER MEMBERS INTENT") — sans ça, le contenu des messages
supprimés/modifiés n'apparaîtra pas dans les logs (voire le bot refusera
de démarrer si l'intent est demandé côté code mais pas activé côté portail).

### Système de Tickets (indépendant de l'économie)
| Commande | Description |
|---|---|
| `/tickets setup <nom> <catégorie> [rôle] [rôle_2] ... [message] [emoji]` | [Gérer les salons] Configure une catégorie avec jusqu'à cinq rôles via Discord |
| `/tickets update <nom> [...]` | [Gérer les salons] Modifie une catégorie existante — ne change QUE les champs fournis |
| `/tickets list` | [Gérer les salons] Liste les catégories configurées |
| `/tickets remove <nom>` | [Gérer les salons] Supprime une catégorie |
| `/tickets logs <salon>` | [Gérer les salons] Définit le salon où envoyer les transcriptions |
| `/tickets tracking-setup <salon>` | [Gérer le serveur] Définit le salon public pour le mode suivi (`/tickets track`) |
| `/tickets panel [titre] [description]` | [Gérer les salons] Poste un panneau **permanent** — tu choisis les catégories incluses |
| `/tickets open` | Ouvre le même menu déroulant, mais version éphémère (visible juste par toi) |
| `/tickets add-user <membre>` | [Gérer les salons] Ajoute un membre à CE ticket uniquement |
| `/tickets remove-user <membre>` | [Gérer les salons] Retire un membre de CE ticket uniquement |
| `/tickets add-role <rôle>` | [Gérer les salons] Donne accès à CE ticket à tout un rôle |
| `/tickets remove-role <rôle>` | [Gérer les salons] Retire l'accès à CE ticket à un rôle |
| `/tickets claim` | [Gérer les salons] Prend en charge CE ticket ; un seul responsable peut être assigné à la fois |
| `/tickets unclaim` | [Gérer les salons] Libère la prise en charge de CE ticket |
| `/tickets track <état>` | [Gérer les salons] Publie ou modifie l'état public de CE ticket : En attente, En examen, Acceptée ou Refusée |
| `/tickets untrack` | [Gérer les salons] Désactive le suivi public de CE ticket |

Chaque catégorie de ticket a son propre salon Discord parent, ses rôles à
ping (optionnels), son message d'ouverture (personnalisable, sinon un
message par défaut), et un **emoji** optionnel pour l'illustrer dans le
menu déroulant (emoji classique ou emoji personnalisé — mais uniquement
un emoji appartenant à CE serveur, les emojis d'autres serveurs sont
refusés). `/tickets setup` accepte jusqu'à cinq rôles. Le panel web permet
d'en sélectionner jusqu'à dix sans copier leurs IDs. Tous reçoivent l'accès
au salon et sont mentionnés lors de son ouverture.

**`/tickets update`** modifie une catégorie existante **sans écraser les
champs que tu ne précises pas** — par exemple, `/tickets update nom:Support
nouvel_emoji:🔥` ne touche qu'à l'emoji, la catégorie/rôle/message restent
identiques. Pour retirer un rôle ou un emoji déjà configuré (plutôt que
les remplacer), utilise `retirer_role:True` ou `retirer_emoji:True`.

**`/tickets panel`** poste un message qui reste dans le salon indéfiniment (menu
déroulant persistant, fonctionne même après un redémarrage du bot) —
pratique pour un salon `#support` fixe. S'il y a plus d'une catégorie
configurée, un menu à choix multiple s'affiche d'abord pour que tu
choisisses lesquelles inclure dans **ce** panneau précis (pratique pour
poser des panneaux différents dans plusieurs salons, chacun avec un
sous-ensemble de catégories). **`/tickets open`** fait la même chose mais en
message éphémère et avec toujours toutes les catégories, pratique si tu
ne veux pas polluer un salon.

**Fermeture et transcription** : le bouton **🔒 Fermer le ticket**
propose 4 choix — envoyer la transcription en MP aux membres du ticket,
la poster dans le salon de logs (`/tickets logs`), les deux, ou fermer
sans transcription. Les "membres du ticket" incluent l'auteur ainsi que
toute personne ajoutée via `/tickets add-user`. Le salon est supprimé
quelques secondes après le choix.

**Prise en charge** : le bouton persistant **🙋 Prendre en charge** et la
commande `/tickets claim` assignent le ticket au premier membre du staff qui
agit. Les autres membres voient qui en est responsable. `/tickets unclaim`
libère le ticket. Si le suivi public est activé, son message affiche et met à
jour automatiquement le responsable sans changer l'état de la demande.

**`/tickets add-user` / `/tickets add-role`** (et leurs équivalents "remove")
s'utilisent **à l'intérieur du salon de ticket concerné** — ils ne
modifient que ce ticket précis, jamais la configuration générale ni les
autres tickets en cours.

Un membre ne peut pas ouvrir deux tickets dans la même catégorie en même temps.

**Mode suivi (`/tickets track` / `/tickets untrack`)** : configure d'abord un salon public
avec `/tickets tracking-setup` (différent du salon de logs, qui lui reste privé
pour le staff). Ensuite, depuis **l'intérieur d'un ticket**, utilise
`/tickets track <état>` pour afficher l'avancement de la demande : 🟡 En attente,
🔵 En examen, 🟢 Acceptée ou 🔴 Refusée. Réutiliser `/tickets track` modifie le
même message public sans en créer un nouveau. À la fermeture du ticket,
le message passe automatiquement à ⚫ Ticket fermé. `/tickets untrack` arrête le
suivi manuellement à tout moment.

### Administration économie (Administrateur uniquement)
| Commande | Description |
|---|---|
| `/berrys-admin add <membre> <montant>` | Ajoute des Berrys à un joueur |
| `/berrys-admin remove <membre> <montant>` | Retire des Berrys à un joueur |

### Quêtes & Amélioration
| Commande | Description |
|---|---|
| `/quest` | Part en mission (cooldown 3h) : Berrys + chance d'obtenir un matériau |
| `/materials` | Affiche les matériaux accumulés |
| `/enhance <fruit>` | Améliore un fruit possédé (niveau 1 à 5) avec Berrys + matériaux |

Chaque niveau au-dessus de 1 rend l'effet du fruit **+15% plus fort**
(`FRUIT_LEVEL_BONUS` dans `config.py`), aussi bien son effet économique
que son bonus de combat contre les boss. Les coûts par palier (Berrys +
matériaux requis) sont dans `config.py` (`FRUIT_UPGRADE_REQUIREMENTS`),
et les matériaux eux-mêmes dans `data/materials.py`.

### Combats de Boss
| Commande | Description |
|---|---|
| `/boss` | Affiche le boss actuel du serveur (PV, meilleurs combattants) |
| `/attack` | Attaque le boss (cooldown 45s, réduit par les fruits `cooldown_reduction`) |

Le boss est **commun à tout le serveur** : tout le monde peut l'attaquer, les
dégâts de chacun sont cumulés, et quand il tombe à 0 PV, le butin est
réparti selon les dégâts infligés (+ bonus MVP pour le meilleur combattant).
Le boss suivant apparaît immédiatement (roster dans `data/bosses.py`).
Chaque fruit équipé donne un bonus de dégâts (`combat_bonus` dans
`data/fruits.py`), le Goro Goro no Mi étant le plus puissant en combat (+30%).

### Casino
| Commande | Description |
|---|---|
| `/roulette <mise> <pari>` | Rouge/noir, pair/impair, manque/passe (x2) ou un numéro précis (x36) |
| `/blackjack <mise>` | Blackjack classique contre le croupier, avec boutons Tirer/Rester |
| `/poker <mise>` | Poker vidéo façon "Jacks or Better" : garde tes cartes, puis tire |

Mise min/max configurable via `CASINO_MIN_BET` / `CASINO_MAX_BET` dans
`config.py`. Les tables de gains (roulette, blackjack, poker) sont aussi
dans `config.py` et `utils/cards.py`.

### Info
| Commande | Description |
|---|---|
| `/about` ou `/help` | Présentation du bot + bouton vers un tutoriel de démarrage pas à pas |
| `/changelog` | Affiche l'historique des mises à jour du bot |

> 💡 `data/changelog.py` est mis à jour à chaque nouvelle fonctionnalité
> ajoutée au bot — la commande `/changelog` reflète toujours l'historique
> réel des changements.

### Blox Fruits (jeu Roblox, indépendant de l'économie du bot)
| Commande | Description |
|---|---|
| `/bloxfruits <bounty> [fruit] [sword] [gun] [style]` | Renseigne (ou met à jour) ton bounty et ton équipement précis |
| `/bloxfruits-profil [membre]` | Affiche le profil Blox Fruits d'un membre (toi par défaut) |
| `/bloxfruits-liste` | Liste tous les profils renseignés sur le serveur |

Le `bounty` est un champ texte libre (accepte `500M`, `1.2B`, `999T`, ou
le nombre exact). Les 4 autres champs (`fruit`, `sword`, `gun`, `style`)
sont **tous optionnels** (renseigne au moins un des quatre) et utilisent
l'**autocomplétion** — tape quelques lettres et Discord te propose des
suggestions parmi les objets connus du jeu (41 fruits, une sélection
d'épées/armes/styles). Comme Blox Fruits est mis à jour très souvent, ces
listes ne sont pas garanties exhaustives : le champ reste du texte libre,
donc tu peux toujours taper un nom absent de la liste si besoin. Pour
compléter les listes, édite `data/bloxfruits_items.py`
(`FRUITS_LIST`, `SWORDS_LIST`, `GUNS_LIST`, `FIGHTING_STYLES_LIST`).

---

## 🖥️ Panel de contrôle (terminal)

Dès que le bot est connecté, un panel de contrôle s'active automatiquement
dans le **même terminal** où tu as lancé `python bot.py` — pas besoin de
config supplémentaire. Tape simplement une commande après le `bot>` :

| Commande | Effet |
|---|---|
| `help` | Liste toutes les commandes |
| `stats` | Statistiques globales (joueurs, Berrys en circulation, primes...) |
| `guilds` | Liste des serveurs où le bot est présent |
| `boss` | État du boss actuel de chaque serveur |
| `give <user_id> <guild_id> <montant>` | Ajoute des Berrys à un joueur |
| `remove <user_id> <guild_id> <montant>` | Retire des Berrys à un joueur |
| `reset <user_id> <guild_id>` | Réinitialise complètement un joueur |
| `broadcast <channel_id> <message>` | Envoie un message dans un salon précis |
| `clear` | Efface l'écran du terminal |
| `stop` (ou `quit`/`exit`) | Arrête proprement le bot |

Le panel tourne dans son propre thread et ne bloque jamais le bot — tu
peux taper une commande à tout moment, même en pleine activité Discord.

> 💡 Pour trouver un `guild_id`, active le mode développeur Discord puis
> clic droit sur le serveur → "Copier l'identifiant du serveur". Pour un
> `user_id`, clic droit sur le membre → "Copier l'identifiant utilisateur".

## ⚙️ Personnalisation

Tous les montants, cooldowns et taux de réussite se règlent dans
**`config.py`**. Les fruits (prix, effets, descriptions) se règlent dans
**`data/fruits.py`** — tu peux facilement en ajouter de nouveaux en suivant
le même format, il te suffira ensuite de gérer le nouvel `effect` dans les
Cogs concernés (`cogs/economy.py` notamment).

### 🎖️ Titres

Les 10 titres affichés sur `/profile` (ex: *Fléaux des Mers*, *Dieu de
Grand Line*) se débloquent automatiquement selon la prime du joueur. Pour
ajouter/modifier des titres ou leurs seuils, édite **`data/titles.py`**.

### ⚓ Flottes

Le bot détecte automatiquement la Flotte d'un membre à partir de ses rôles
Discord, et l'affiche avant son titre (ex: `Fléaux de la Guerre | Dieu de
Grand Line`). Configure le mapping rôle ↔ flotte dans **`data/fleets.py`**.

> ⚠️ Le `role_name` doit correspondre exactement au nom du rôle sur ton
> serveur (la casse n'a pas d'importance, mais l'orthographe si). Si un
> membre possède plusieurs rôles de flotte, c'est la plus puissante
> (en haut de la liste) qui est affichée.

### 🖼️ Affiche dynamique (/profile)

`/profile` génère à la volée une image façon "avis de recherche" avec
l'avatar du membre découpé en rond, sa Flotte + son titre, et sa prime —
le tout dessiné avec Pillow, sans aucune image externe (donc aucun souci
de droits d'auteur). Tu peux déposer tes propres polices `.ttf` dans
`assets/fonts/` (voir le README de ce dossier) pour personnaliser le rendu.

---

## 💡 Idées d'améliorations futures

- `/leaderboard` : classement des plus grosses primes du serveur
- Fruits rendus **uniques** globalement (un seul joueur peut le posséder à
  la fois, comme dans le canon — nécessiterait de retirer le fruit du
  vendeur précédent ou de le rendre indisponible en boutique une fois vendu)
- Système de **bank** séparé du **wallet** (pour se protéger du `/crime`
  d'autres joueurs si tu ajoutes un système de vol PvP)
- Commandes `/give` pour transférer des Berrys entre joueurs

## ✉️ Messages Discord depuis le panel web

Après avoir configuré le panel OAuth (`PANEL_ENABLED`, client Discord et session, voir la documentation précédente), ouvrir **Dashboard → Serveur → Messages Discord**, ou directement `<PANEL_PREFIX>/guild/ID_DU_SERVEUR/messages`.

- **Publier** : sélectionner un salon, choisir « Message normal » ou « Embed », saisir les champs et cliquer sur **Envoyer le message**. Les embeds proposent titre, description, couleur, pied de page, image HTTPS et contenu facultatif au-dessus de l'embed.
- **Modifier** : dans la liste des messages publiés depuis cette page, cliquer sur **Modifier**. Le formulaire est prérempli : modifier seulement les champs voulus, puis enregistrer. Le bot édite le **même message Discord**, sans le republier.
- **Supprimer** : le bouton **Supprimer** efface le message sur Discord et dans le suivi du panel (réservé aux personnes qui peuvent publier).
- **Déléguer l'édition** : un administrateur choisit un ou plusieurs **Rôles autorisés à modifier** depuis la page Messages. Ces rôles accèdent aux seuls messages suivis et peuvent les modifier avec le formulaire, **sans pouvoir en publier, en supprimer ni accéder aux autres paramètres du panel** (sauf si d'autres droits de panel leur ont également été accordés).

Les administrateurs du serveur, les membres disposant de « Gérer le serveur » et les rôles ayant déjà un accès général au panel peuvent publier et modifier. Les rôles éditeurs de messages disposent uniquement de l'édition. La connexion Discord, la protection CSRF et le contrôle de rôle sont vérifiés à chaque action. Les mentions automatiques (everyone / here / rôles / utilisateurs) ne sont pas déclenchées. Le bot doit disposer de **Voir le salon**, **Envoyer des messages** et **Intégrer des liens** pour les embeds.

Seuls les **messages publiés depuis cette nouvelle page** sont repris dans la liste et modifiables. Les messages existants d'autres commandes ne sont pas importés automatiquement. Les tables SQLite sont créées automatiquement au démarrage, sans supprimer les données existantes.
