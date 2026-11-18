# 📱 Garder le bot en ligne pendant une absence (PC allumé + accès distant)

Ce guide couvre la solution "je laisse mon PC allumé chez moi et je le
pilote depuis mon iPhone si besoin" — parfait pour une absence de
quelques jours sans migrer vers un serveur cloud.

---

## 1. Utilise le script anti-crash (`run_bot_loop.bat`)

Au lieu de lancer `python bot.py` directement, utilise le fichier
`run_bot_loop.bat` fourni à la racine du projet : double-clique dessus
(ou lance-le depuis PowerShell). Si le bot plante pour une raison
quelconque, il redémarre automatiquement 5 secondes après, sans que tu
aies besoin d'intervenir. Laisse simplement la fenêtre ouverte.

## 2. Empêche le PC de se mettre en veille

**Paramètres → Système → Alimentation et mise en veille** (ou cherche
"veille" dans la barre de recherche Windows) :
- Mets **"Mettre en veille"** sur **Jamais** (aussi bien sur secteur que
  sur batterie, mais branche le PC de toute façon).
- L'écran peut se mettre en veille (pas grave), c'est juste la **mise en
  veille système** qu'il faut empêcher — elle couperait le bot.

⚠️ Vérifie aussi qu'aucune mise en veille prolongée / veille automatique
n'est configurée dans le BIOS ou via un logiciel tiers (certains
laptops ont leurs propres réglages constructeur).

## 3. Mets en pause les mises à jour Windows

Un redémarrage forcé par Windows Update couperait le bot sans prévenir.
**Paramètres → Windows Update → Options avancées → Suspendre les mises
à jour** pendant quelques jours (7 jours max par défaut, largement
suffisant pour ton absence).

## 4. Vérifie ta connexion internet

Le PC doit rester connecté en Wi-Fi (ou idéalement en Ethernet, plus
stable) pendant toute ton absence. Si ta box internet redémarre ou coupe,
le bot perdra sa connexion Discord (il se reconnectera tout seul dès que
le réseau revient, aucune action nécessaire de ta part).

## 5. Installe Chrome Remote Desktop (accès à distance)

**Sur ton PC :**
1. Ouvre Chrome, va sur https://remotedesktop.google.com/access
2. Clique sur l'icône de téléchargement pour installer l'extension/app
   Chrome Remote Desktop si ce n'est pas déjà fait.
3. Clique sur **"Activer l'accès à distance"**, choisis un nom pour ce
   PC, puis définis un **code PIN** (au moins 6 chiffres) — c'est ce PIN
   qui te permettra de te connecter depuis ton iPhone.
4. Laisse cette page/le PC allumés.

**Sur ton iPhone :**
1. Installe l'app **"Chrome à distance"** (Chrome Remote Desktop) depuis
   l'App Store.
2. Connecte-toi avec le **même compte Google** que sur ton PC.
3. Ton PC doit apparaître dans la liste — tape dessus, entre ton PIN.
4. Tu vois maintenant l'écran de ton PC depuis ton téléphone, et tu peux
   contrôler la souris/clavier (un peu comme du VNC/TeamViewer).

## 6. Que faire une fois connecté à distance depuis ton iPhone

- Regarde la fenêtre PowerShell/CMD où tourne `run_bot_loop.bat` — si le
  bot est en train de tourner normalement, tu verras les logs défiler
  normalement (connexions, commandes, etc.).
- Si besoin de relancer manuellement : ferme la fenêtre, redouble-clique
  sur `run_bot_loop.bat`.
- Tu peux aussi utiliser le **panel de contrôle en terminal** directement
  depuis cette session à distance (tape `stats`, `boss`, `give`, etc. —
  voir la section dédiée du README principal).

---

## ⚠️ Limites de cette solution

- Si le PC s'éteint physiquement (coupure de courant, redémarrage
  Windows imprévu malgré la pause des mises à jour...), tu ne pourras
  **rien faire à distance** tant qu'il n'est pas rallumé physiquement —
  contrairement à un vrai serveur cloud qui redémarre tout seul.
- Chrome Remote Desktop a lui-même besoin que le PC soit allumé et
  connecté à internet pour fonctionner — ce n'est pas un miracle, juste
  un moyen de surveiller/relancer le bot sans être devant l'écran.
- Pour une solution vraiment "increvable" sans dépendre de ton PC, la
  migration vers un VPS (Oracle Cloud gratuit, voir
  `deploy/README_HEBERGEMENT.md`) reste la meilleure option sur le long
  terme.
