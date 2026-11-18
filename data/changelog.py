"""
data/changelog.py
--------------------
Historique des changements apportés au bot.

⚠️ Ce fichier est mis à jour à chaque modification demandée dans la
conversation avec Claude. La version la plus récente est en premier.
Affiché en jeu via la commande /changelog.
"""

CHANGELOG = [
    {
        "version": "3.0.3",
        "date": "15 novembre 2026",
        "changes": [
            "🎭 Nouveau système de rôles par réactions : création de panneaux et attribution/retrait automatique des rôles",
            "🛠️ Commandes /reaction-roles create, add, remove, list et delete pour la configuration sur Discord",
            "💾 Configuration persistante après redémarrage, emojis Unicode et personnalisés, contrôles de permissions",
            "🛡️ Commandes de modération directes conservées",
        ],
    },
    {
        "version": "3.0.2",
        "date": "13 novembre 2026",
        "changes": [
            "✏️ Nouvelle commande /message-edit : modifier un message du bot directement dans Discord à partir de son lien ou de son ID",
            "📝 Formulaire prérempli pour les embeds (titre, description, couleur, pied de page, image) et messages texte",
            "🔐 Permissions compatibles avec les rôles éditeurs du panel ; protection des messages interactifs et des messages d'autres auteurs",
            "🌐 Les messages envoyés ou modifiés depuis Discord sont suivis dans le panel web",
            "🛠️ Correctif V3.0.1 inclus : réparation de la syntaxe de cogs/web_panel.py qui bloquait le démarrage du panel",
        ],
    },
    {
        "version": "3.0",
        "date": "13 novembre 2026",
        "changes": [
            "🎁 Propositions de giveaways enrichies : durée, salon, gagnants et conditions de participation",
            "✅ Validation staff : publication automatique du giveaway, programmation du tirage et mise à jour du ticket et des logs",
            "🌐 Panel web : création, modification et suppression des messages Discord, classiques ou embeds",
            "🔐 Permissions par rôle pour modifier les messages depuis des formulaires préremplis sur le site",
            "🗂️ Commandes slash regroupées en sous-commandes avec des noms anglais pour réduire le nombre de commandes racines",
            "🛡️ Commandes de modération conservées en accès direct pour intervenir rapidement",
        ],
    },
    {
        "version": "2.21",
        "date": "1 novembre 2026",
        "changes": [
            "✨ Le titre de la page d'un serveur du panel web utilise le composant Refracted Text (verre réfracté WebGL 2.0)",
            "🖼️ La liste des serveurs affiche l'icône de chaque serveur (ou ses initiales) avec un titre simple et léger",
            "📱 Texte simple conservé automatiquement sans JavaScript, sans WebGL 2.0 ou si le nom est trop long",
            "📦 Nouveau dossier `panel_ui/` (sources du bundle) et `static/panel/` (fichiers compilés servis par le panel)",
        ],
    },
    {
        "version": "2.20",
        "date": "28 octobre 2026",
        "changes": [
            "👋 Nouveau système de rôles d'arrivée : `/autorole add`, `remove`, `list` et `screening`",
            "🎯 Chaque rôle peut cibler tout le monde, les membres uniquement ou les bots uniquement (10 rôles maximum)",
            "📜 Les rôles peuvent n'être donnés qu'après validation du règlement du serveur (activé par défaut)",
            "🌐 Gestion des rôles d'arrivée disponible aussi depuis le panel web",
        ],
    },
    {
        "version": "2.19",
        "date": "28 octobre 2026",
        "changes": [
            "🗂️ Commandes de points regroupées : `/points profile`, `/points roles` et `/points-admin ...` (config, add, item-add, item-list, item-remove, role-add, role-remove)",
            "📌 `/giveaway-propose` répond désormais publiquement avec un embed de statut dans le ticket",
            "🔄 L'embed se met à jour automatiquement quand le staff valide ou refuse la proposition (Discord ou panel web)",
            "🌐 Nouvelle page du panel web pour gérer les points, lots, rôles de seuil et propositions",
        ],
    },
    {
        "version": "2.18",
        "date": "28 octobre 2026",
        "changes": [
            "🎁 Les membres peuvent proposer un giveaway depuis leur ticket en choisissant un lot configuré",
            "🛡️ Le staff valide ou refuse la proposition depuis les logs avant de créer le giveaway public",
            "🏆 Les points et rôles de seuil récompensent l'organisateur après validation",
            "➕ Ajout de `/points-add` pour créditer manuellement les points d'un membre",
        ],
    },
    {
        "version": "2.17",
        "date": "12 septembre 2026",
        "changes": [
            "📝 Ajout de `/message-send` pour publier un message personnalisé depuis un formulaire Discord",
            "🎨 Le formulaire permet de choisir le titre, le texte, la couleur, le pied de page et une image facultative",
        ],
    },
    {
        "version": "2.16",
        "date": "30 août 2026",
        "changes": [
            "🏷️ Détection des tags de serveur affichés sur les profils Discord",
            "🎭 Attribution et retrait automatique d'un rôle selon le tag configuré",
            "🛠️ Ajout de `/tag-rule-add`, `/tag-rule-list`, `/tag-rule-remove`, `/tag-scan` et `/tag-check`",
        ],
    },
    {
        "version": "2.15",
        "date": "30 août 2026",
        "changes": [
            "📈 Les récompenses de boss évoluent maintenant par tranches selon leurs PV maximum",
            "👑 Le bonus MVP devient proportionnel au butin, avec un minimum et un plafond anti-inflation",
            "💰 Tous les participants reçoivent désormais leur part, même si seuls les cinq premiers sont détaillés",
        ],
    },
    {
        "version": "2.14",
        "date": "28 août 2026",
        "changes": [
            "🚫 Ajout d'une blacklist globale persistante dans le panel Owner",
            "🛡️ Les IDs blacklistés sont bannis des serveurs actuels et automatiquement à leur prochaine arrivée",
            "🔒 La gestion reste exclusivement réservée aux propriétaires déclarés du bot",
        ],
    },
    {
        "version": "2.13",
        "date": "23 août 2026",
        "changes": [
            "⚠️ Le panel Owner peut supprimer tous les salons et catégories d'un serveur après une double confirmation",
            "🔒 Cette action est réservée au panel Owner et n'est disponible dans aucun autre panel ni aucune commande Discord",
        ],
    },
    {
        "version": "2.12",
        "date": "19 août 2026",
        "changes": [
            "🙋 Ajout de la prise en charge des tickets par bouton ou avec `/ticket-claim`",
            "↩️ Ajout de `/ticket-unclaim` pour libérer un ticket pris en charge",
            "📡 Le suivi public indique maintenant le membre du staff responsable du ticket",
        ],
    },
    {
        "version": "2.11",
        "date": "18 août 2026",
        "changes": [
            "🛒 Ajout d'une boutique d'objets personnalisés indépendante pour chaque serveur",
            "⚙️ Les administrateurs gèrent le catalogue avec `/custom-item-add`, `/custom-item-remove` et `/custom-item-list`",
            "🎒 Les membres utilisent `/custom-shop`, `/custom-buy` et `/custom-inventory`",
            "🌐 Le catalogue peut également être administré depuis le panel web de Le Fleau",
            "👑 Ajout d'un panel Owner séparé avec contrôle d'accès strict par ID Discord",
            "🔗 Le panel Owner peut créer une invitation temporaire à usage unique pour rejoindre un serveur du bot",
            "🚪 Le panel Owner peut faire quitter un serveur au bot après confirmation exacte de son nom",
            "🎫 Chaque catégorie de ticket accepte désormais plusieurs rôles à autoriser et à ping",
        ],
    },
    {
        "version": "2.10",
        "date": "1 août 2026",
        "changes": [
            "🚀 Ajout de la catégorie de logs \"Boosts\" : annonce automatique des boosts serveur",
            "⚙️ Se configure avec la commande `/logs-setup` déjà existante (rien de nouveau à apprendre)",
        ],
    },
    {
        "version": "2.9",
        "date": "1 août 2026",
        "changes": [
            "🎯 `/panel` permet de choisir quelles catégories inclure (menu à choix multiple)",
            "📡 Ajout du mode suivi de ticket : `/tracking-setup`, `/track`, `/untrack`",
            "📌 Le statut du ticket suivi se met à jour en direct dans un salon public (sans spam)",
        ],
    },
    {
        "version": "2.8",
        "date": "1 août 2026",
        "changes": [
            "🛡️ Ajout de `/modperms` et `/modroles` : audit des permissions de modération (membres/rôles)",
            "🍈 `/bloxfruits` détaillé : fruit, épée, arme et style de combat précis (avec autocomplétion)",
        ],
    },
    {
        "version": "2.7",
        "date": "1 août 2026",
        "changes": [
            "🍈 Ajout de `/bloxfruits` : renseigne ton bounty et ton build du jeu Roblox Blox Fruits",
            "📋 Ajout de `/bloxfruits-profil` et `/bloxfruits-liste` pour consulter les profils",
        ],
    },
    {
        "version": "2.6",
        "date": "1 août 2026",
        "changes": [
            "🔒 Ajout de `/lock` et `/unlock` — le déverrouillage restaure l'état exact d'avant (pas un reset brutal)",
            "🔊 Ajout de `/unmute` (et alias `/untimeout`) pour lever une sourdine avant son terme",
        ],
    },
    {
        "version": "2.5",
        "date": "1 août 2026",
        "changes": [
            "📋 Ajout du système de logs configurable : `/logs-setup`, `/logs-disable`, `/logs-status`",
            "🗂️ 6 catégories indépendantes : messages, membres, salons, rôles, vocal, serveur",
        ],
    },
    {
        "version": "2.4",
        "date": "1 août 2026",
        "changes": [
            "⚠️ Ajout du système d'avertissements : `/warn`, `/warnings`, `/unwarn`, `/clearwarns`",
            "📨 `/warn` envoie automatiquement un MP au membre averti (si ses MPs sont ouverts)",
        ],
    },
    {
        "version": "2.3",
        "date": "1 août 2026",
        "changes": [
            "🕊️ Ajout de `/unban` dans la modération, avec autocomplétion listant les membres bannis",
        ],
    },
    {
        "version": "2.2",
        "date": "1 août 2026",
        "changes": [
            "✨ Ajout de `/ticket-update` : modifie une catégorie de ticket sans écraser les champs non précisés",
            "🎨 Les catégories de ticket peuvent maintenant avoir un emoji (du serveur) pour les illustrer",
        ],
    },
    {
        "version": "2.1",
        "date": "1 août 2026",
        "changes": [
            "📌 Ajout de `/panel` : panneau de tickets permanent avec menu déroulant persistant",
            "📋 Fermeture de ticket : choix de transcription (MP aux membres et/ou salon de logs via `/ticket-logs`)",
            "👥 Ajout de `/ticket-adduser`, `/ticket-removeuser`, `/ticket-addrole`, `/ticket-removerole`",
        ],
    },
    {
        "version": "2.0",
        "date": "1 août 2026",
        "changes": [
            "🎫 Ajout du système de tickets configurable, indépendant de l'économie",
            "⚙️ `/ticket-setup` : nom, catégorie Discord, rôle à ping et message perso par catégorie",
            "📋 `/ticket` : menu déroulant pour ouvrir un ticket dans la catégorie de son choix",
        ],
    },
    {
        "version": "1.9",
        "date": "1 août 2026",
        "changes": [
            "🖤 Ajout du passif Barbe Noire (`/barbenoire`, 750 000฿) : équipe des fruits en illimité, bonus cumulés",
            "🍈 `/eat` et `/unequip` gèrent maintenant plusieurs fruits actifs à la fois",
            "💰 Refonte des prix des Fruits du Démon (environ x3) suite à l'inflation des quêtes/boss/casino",
        ],
    },
    {
        "version": "1.8",
        "date": "28 juillet 2026",
        "changes": [
            "🗺️ Ajout de `/quest` : missions rapportant Berrys + matériaux (cooldown 3h)",
            "🎒 Ajout de `/materials` pour consulter son inventaire de matériaux",
            "✨ Ajout de `/enhance` : améliore un fruit (niveau 1 à 5, +15% d'effet par niveau)",
        ],
    },
    {
        "version": "1.7",
        "date": "28 juillet 2026",
        "changes": [
            "🖥️ Ajout d'un panel de contrôle en terminal (démarre automatiquement avec le bot)",
            "📊 Commandes admin en local : stats, guilds, boss, give, remove, reset, broadcast, stop",
        ],
    },
    {
        "version": "1.6",
        "date": "28 juillet 2026",
        "changes": [
            "⚔️ Ajout du système de Boss communautaire : `/boss` et `/attack`",
            "🍈 Les Fruits du Démon donnent maintenant un bonus de dégâts en combat",
            "🎲 Ajout du casino : `/roulette`, `/blackjack` et `/poker` (vidéo-poker)",
        ],
    },
    {
        "version": "1.5",
        "date": "28 juillet 2026",
        "changes": [
            "🧭 Ajout de `/about` (et son alias `/help`) : présentation rapide du bot",
            "📖 Ajout d'une page tutoriel accessible par bouton, pour guider les nouveaux joueurs",
        ],
    },
    {
        "version": "1.4",
        "date": "28 juillet 2026",
        "changes": [
            "🏜️ Ajout du Suna Suna no Mi (Logia) : +20% sur /work",
            "❄️ Ajout du Hie Hie no Mi (Logia) : -30% de risque de se faire attraper en /crime",
            "⚡ Ajout du Goro Goro no Mi (Logia) : -30% sur tous les cooldowns",
        ],
    },
    {
        "version": "1.3",
        "date": "28 juillet 2026",
        "changes": [
            "🎖️ Ajout de 10 titres débloqués progressivement selon la prime (visibles sur /profile)",
            "⚓ Détection automatique de la Flotte du membre via ses rôles Discord, affichée avant son titre",
            "🖼️ /profile génère maintenant une affiche \"avis de recherche\" dynamique avec l'avatar en rond",
        ],
    },
    {
        "version": "1.2",
        "date": "28 juillet 2026",
        "changes": [
            "🫙 Ajout de `/unequip` pour déséquiper un fruit sans le perdre de l'inventaire",
            "🔄 Ajout de `/reset` pour recommencer entièrement à zéro (avec confirmation par boutons)",
            "📜 Ajout de `/changelog` pour suivre l'historique des mises à jour du bot",
        ],
    },
    {
        "version": "1.1",
        "date": "27 juillet 2026",
        "changes": [
            "🧹 Ajout du script `clear_commands.py` pour nettoyer les anciennes slash commands en double",
        ],
    },
    {
        "version": "1.0",
        "date": "27 juillet 2026",
        "changes": [
            "🎉 Création initiale du bot One Piece Economy",
            "💰 Système d'économie complet : `/daily`, `/work`, `/crime`, `/pillage`, `/balance`, `/solde`, `/profile`",
            "🍈 Système de Fruits du Démon : `/shop`, `/buy`, `/inventory`, `/eat`",
            "⚓ Modération thème Marine : `/kick`, `/ban`, `/clear`, `/timeout`, `/mute`",
            "🏛️ Administration économie : `/add-berrys`, `/remove-berrys`",
        ],
    },
]
