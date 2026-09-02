# Premier démarrage

L'assistant tient en six étapes, une à la fois. Chacune dit si elle est
**obligatoire**, **facultative**, ou **pour information**. Tu peux le passer
entièrement et y revenir plus tard depuis les réglages.

## 1. Bienvenue — pour information

Ce que Romule fait, et ce qu'il ne fait pas : il ne télécharge aucun jeu et ne
fournit aucune clé.

## 2. Ta ludothèque — obligatoire

Le dossier qui contient tous tes jeux, toutes plateformes confondues.

Appuie sur **Analyser le dossier**. Romule rapporte ce qu'il a trouvé, par
plateforme :

> **4 jeux sur 2 plateformes** — 2 Nintendo Switch · 2 Mega Drive

C'est la seule preuve que le dossier désigné est le bon. Un chemin accepté sans
rien dedans est un mauvais chemin qu'on découvre une heure plus tard : l'étape
ne laisse donc pas continuer tant que l'analyse ne trouve rien.

Pour un autre dossier, clique sur **Choisir un autre dossier…** et navigue.
Rien à redémarrer, aucun fichier à éditer — le même sélecteur se retrouve
ensuite dans **Réglages → Ta ludothèque → Emplacement**.

Si le bouton manque, le dossier a été figé par ton déploiement avec
`ROMULE_LIBRARY` ; change-le dans ton fichier compose.

!!! note "Ton dossier reste le tien"
    Romule n'écrit que `_import/` et `_corbeille/` à côté de tes jeux. Ses
    réglages, tes comptes et les jaquettes vivent dans le dossier de données du
    service, et ne suivent pas les jeux quand tu les déplaces.

## 3. Ton accès — obligatoire dès qu'il est joignable

Le premier compte créé devient l'**administrateur** : lui seul change les
réglages et gère les autres comptes.

Cette étape est marquée obligatoire quand le service écoute sur le réseau, et
facultative quand il n'écoute que sur `127.0.0.1`. Le tout premier compte ne
peut être créé que depuis la machine qui héberge la ludothèque — sinon « le
premier compte gouverne » voudrait dire « le premier appareil du réseau
gouverne ».

## 4. Jaquettes et fiches — facultatif

Deux services gratuits complètent les images et les résumés. Sans eux la
bibliothèque fonctionne, mais elle n'affiche que des noms de fichiers.

| Service | Ce qu'il donne | Où obtenir une clé |
|---|---|---|
| SteamGridDB | Les jaquettes | [steamgriddb.com/profile/preferences/api](https://www.steamgriddb.com/profile/preferences/api) |
| IGDB | Résumés, année, éditeur | [dev.twitch.tv/console/apps](https://dev.twitch.tv/console/apps) |

**Enregistrer et tester** vérifie les identifiants sur-le-champ. Enregistrer
sans vérifier, c'est découvrir dans un mois qu'une clé a été mal collée.

## 5. Ta console — facultatif

Romule cherche une console par adb, récupère le dossier des jeux, et sait
lister ce qui s'y trouve déjà. Tout est faisable plus tard depuis
**Réglages → Ta console** — voir [Ta console](console.md).

## 6. C'est prêt — pour information

Ce qui reste, et où cela se trouve :

- **Les jeux compressés** (`.nsz`, `.xcz`) demandent l'outil `nsz` et un
  fichier `prod.keys`, tous deux renseignés dans les réglages. Ils ne sont pas
  nécessaires au fonctionnement de Romule — seulement à la conversion de ces
  deux formats.
- **Émulateur** — Romule vise Eden par défaut ; choisis un autre profil dans
  Réglages → Ta console.
- **Accès à distance** — Réglages → Accès.

## Pourquoi prod.keys n'est pas dans l'assistant

Il ne sert qu'à convertir les `.nsz` et les `.xcz`. Tout le reste —
l'inventaire, les jaquettes, les transferts, les mises à jour et les DLC —
fonctionne sans lui. Le demander d'emblée laisserait croire que Romule ne
tourne pas sans, ce qui est faux.
