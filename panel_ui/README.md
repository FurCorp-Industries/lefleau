# Panel UI

Front-end du panel web : remplace le titre de la page d'un serveur par le composant
**Refracted Text** de ReactDrops (verre réfracté en WebGL 2.0). La liste des serveurs, elle,
n'utilise pas WebGL : icône du serveur (WebP statique, chargement différé) et titre en texte simple.

- Le serveur écrit chaque titre en texte simple (`server_title()` dans `cogs/web_panel.py`) ;
  `static/panel/refracted-titles.js` le remplace dans le navigateur.
- Sans JavaScript ou sans WebGL 2.0, le texte reste affiché tel quel.
- Les fichiers compilés sont dans `static/panel/` : **Node n'est pas nécessaire pour faire tourner le bot**.

## Reconstruire le bundle

```bash
cd panel_ui
npm ci
npm run typecheck
npm run build      # écrit ../static/panel/refracted-titles.{js,css}
```

## Où régler le rendu

- Props du composant (couleurs, durées, easing…) : `REFRACTED_CONFIG` dans `src/main.tsx`.
- Retour à la ligne des noms longs : `MAX_LINE_LENGTH` et `MAX_LINES` dans `src/main.tsx`.
- Maximum de titres animés par page (un contexte WebGL chacun) : `MAX_WEBGL_LINES`.

## Polices d'origine

`src/components/refracted-text.css` contient les règles de mise en page seulement.
Le CSS du registre embarque aussi deux polices (`ReactDrops Librestile` et
`ReactDrops Square Display`) qui ne sont pas incluses ici : le composant utilise
donc `Arial Black` / `sans-serif`. Pour retrouver les polices d'origine :

```bash
# dans un projet de test shadcn
npx shadcn@latest add https://reactdrops.dev/r/refracted-text.json
# puis copier le refracted-text.css généré dans panel_ui/src/components/ et relancer npm run build
```

## Licence

Les fichiers `src/components/refracted-*` viennent de ReactDrops et restent sous la
**ReactDrops Component License 1.0** (en-tête conservé dans chaque fichier). Elle autorise
l'usage dans un produit fini comme ce panel, mais interdit de redistribuer le composant
comme kit, template ou bibliothèque réutilisable.
