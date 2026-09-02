# Configuration

Deux couches. Les **variables d'environnement** couvrent ce qu'il faut savoir
avant que Romule ne démarre. Tout le reste vit dans l'interface et se range
dans `_romule-config.json`, à l'intérieur du dossier de données du service.

Romule sépare deux dossiers, et cette distinction traverse toute la page :

- le **dossier de données** appartient au service — réglages, comptes,
  jaquettes, journaux, sauvegardes. Il est fixé par ton déploiement et n'a
  aucune raison de bouger ;
- la **ludothèque** t'appartient — tes jeux. Elle vit d'ordinaire sur un autre
  disque, et tu la choisis **depuis l'interface**, pas depuis un fichier
  compose.

Par défaut, la ludothèque *est* le dossier de données : une installation en un
seul dossier continue donc de fonctionner exactement comme avant.

## Variables d'environnement

| Variable | Défaut | Ce qu'elle fait |
|---|---|---|
| `ROMULE_ROOT` | `~/.local/share/romule` | Dossier de données du service : réglages, comptes, jaquettes, journaux |
| `ROMULE_LIBRARY` | — | Fige le dossier des jeux et le **verrouille** — l'interface ne peut plus en changer |
| `ROMULE_BASES` | — | Dossiers que l'interface a le droit de parcourir, séparés comme un `PATH`. Non renseigné : tout ce que le processus peut voir. |
| `ROMULE_WEB_PORT` | `8787` | Port d'écoute |
| `ROMULE_BIND` | voir plus bas | Interface sur laquelle écouter |
| `ROMULE_TOKEN` | — | Jeton d'accès ; remplace celui qui est engendré |
| `ROMULE_LAN` | — | `1` ouvre l'accès réseau **sans mot de passe** |
| `ROMULE_KEYS` | `~/.romule/prod.keys` | Chemin du fichier de clés de déchiffrement |
| `ROMULE_TRUSTED_PROXIES` | — | Adresses, séparées par des virgules, dont les en-têtes transmis sont honorés |
| `ROMULE_UPLOAD_MAX` | 64 Gio | Plus grand envoi accepté, en octets |
| `ROMULE_DISK_MARGIN` | 2 Gio | Espace libre gardé en réserve, en octets |
| `ROMULE_NO_BROWSER` | — | `1` empêche Romule d'ouvrir un navigateur au démarrage |
| `ROMULE_TIMEOUT` | `300` | Délai de socket, en secondes |
| `ROMULE_MAX_CONN` | `64` | Connexions simultanées |
| `ROMULE_RATE` | `600` | Requêtes par minute et par client |
| `ROMULE_CHROME` | — | Binaire Chrome pour la famille de tests navigateur |
| `ROMULE_SCRYPT_PARALLELE` | `2` | Combien de hachages de mot de passe peuvent tourner à la fois. scrypt coûte volontairement ~128 Mio chacun ; sans plafond, quelques tentatives de connexion en parallèle épuiseraient la mémoire du serveur et transformeraient une protection en levier. |
| `ROMULE_ADB` | `adb` dans le `PATH` | Chemin du binaire `adb`. Un chemin qui n'existe pas veut dire « pas de console », et c'est ainsi que la suite de tests reste indépendante de ce qui est branché. |

`ROMULE_BIND` vaut `127.0.0.1` par défaut, sauf dans un conteneur ou une fois
l'accès réseau activé — sans quoi un port publié n'atteindrait rien.

`ROMULE_BASES` n'est pas un bac à sable, et n'est pas renseigné par défaut.
Dans un conteneur, la vraie frontière est la liste des `volumes:`, appliquée
par le noyau ; sur une installation directe, c'est le compte Unix qui fait
tourner le service. Jellyfin, Sonarr et qBittorrent fonctionnent tous ainsi.
Renseigne `ROMULE_BASES` quand tu tournes en direct sous un compte large et que
tu veux quand même restreindre le sélecteur. Quand il est posé, il borne aussi
bien ce que tu peux parcourir **que** ce que tu peux choisir : taper un chemin
n'est pas un moyen de le contourner.

!!! info "Les anciens noms fonctionnent encore"
    Les variables `SWITCH_*` sont toujours lues, et Romule affiche leur
    remplaçante au démarrage. Elles disparaîtront dans une version ultérieure.

## Réglages

Tous se modifient depuis l'interface. Les noms sont les clés rangées dans
`_romule-config.json` ; tu ne devrais normalement pas avoir à éditer ce fichier
à la main.

### Accès

| Clé | Défaut | Signification |
|---|---|---|
| `auth_mode` | `aucun` | `aucun`, `interne` (comptes), ou `oidc` ([bêta](beta.md)) |
| `lan_access` | `false` | Laisse entrer le réseau **sans mot de passe** |
| `maj_check` | `true` | Demande à GitHub une fois par jour s'il existe une version plus récente. C'est la **seule** fois où Romule sort sur internet sans qu'on le lui demande ; coupé, il ne le fait jamais. |
| `auth_secret` | engendrée | Clé de signature des cookies de session. Ne quitte jamais le serveur. |
| `oidc_issuer` | — | Adresse du fournisseur |
| `oidc_client_id` / `oidc_client_secret` | — | Identifiants du client |
| `oidc_redirect` | — | URI de redirection déclarée chez le fournisseur |
| `oidc_scopes` | `openid profile email` | Portées demandées |
| `oidc_emails` / `oidc_groupes` | — | Restreignent **qui peut se connecter** |
| `oidc_admin_groupes` | — | Groupes dont les membres **peuvent administrer**. Vide : personne. |

!!! warning "Deux questions différentes"
    `oidc_groupes` décide qui entre. `oidc_admin_groupes` décide qui peut
    ouvrir les Réglages et gérer l'outil. Les confondre donnerait
    l'administration à tous ceux qui peuvent se connecter.

    Le rôle est lu dans le jeton **à la connexion** : retirer quelqu'un d'un
    groupe le déclasse à sa session suivante, pas au milieu de celle en cours.
    Voir [Rôles et accès](roles.md).

### Ta console

| Clé | Défaut | Signification |
|---|---|---|
| `emulateur` | `eden` | [Profil](profils.md) qui décide de tous les chemins sur la console |
| `emulateur_paquet` | — | Paquet Android, détecté depuis la console |
| `device_dir` | `/storage/emulated/0/Switch` | Dossier des jeux Switch sur la console |
| `roms_root` | — | Dossier parent des autres plateformes. Vide : déduit de `device_dir`. |
| `wifi_addr` | — | Adresse de la console, retenue après appairage |
| `push_layout` | `type` | `type` range en `GAMES`/`UPDATE`/`DLC` ; `plat` laisse à plat |
| `saves_dir` | — | Où les sauvegardes de jeu sont archivées |
| `auto_nand` | `false` | Installer automatiquement dans la NAND de l'émulateur |

### Ludothèque

| Clé | Défaut | Signification |
|---|---|---|
| `library_path` | — | Le dossier analysé. Vide : le dossier de données. Se pose depuis **Réglages → Ta ludothèque → Emplacement**, pas à la main. |
| `local_layout` | `type` | Même idée, côté serveur |
| `systemes_perso` | `[]` | Plateformes supplémentaires que tu définis toi-même |
| `system_dirs` | `{}` | Dossiers imposés par plateforme |
| `trash_days` | `0` | Jours avant que la corbeille ne se vide seule. `0` : jamais. |
| `verify_mode` | `size` | `size` compare taille et date ; `hash` prend l'empreinte du contenu |
| `incremental` | `true` | Ne relire que ce qui a changé |
| `jobs` | `3` | Conversions en parallèle |
| `versions_urls` | titledb | Miroirs de la base des versions Switch |

### Jaquettes et fiches

| Clé | Défaut | Signification |
|---|---|---|
| `cover_provider` | `nlib` | `nlib`, `steamgriddb`, ou `custom` |
| `cover_url` | gabarit nlib | Utilisé quand `cover_provider` vaut `custom`. `{tid}` est substitué. |
| `steamgriddb_key` | — | Clé d'API SteamGridDB |
| `igdb_client_id` / `igdb_client_secret` | — | Identifiants IGDB. Servent aux résumés **et**, quand la source choisie n'a pas d'image, de seconde source de jaquettes. |
| `meta_lang` | `en` | Langue des titres et des résumés |
| `emuready` | `false` | Notes de compatibilité communautaires ([bêta](beta.md)) |
| `emuready_device` | — | L'appareil auquel comparer les notes |
| `emuready_device_nom` | — | Son nom d'affichage, retenu pour ne pas redemander la liste |

!!! info "Pourquoi les jaquettes ont deux sources"
    SteamGridDB est une base de *visuels* communautaires : riche sur ce qui se
    joue au clavier, pauvre sur les catalogues de consoles portables. IGDB est
    une base de jeux, et elle publie aussi des jaquettes. Romule lui demandait
    déjà les résumés ; il lui demande désormais les images — mais seulement
    après que la source choisie a échoué à rendre une **image**, et non une
    simple adresse : une URL qui répond 404 reste une URL.

    Les deux sources passent par le même rapprochement : un candidat doit
    couvrir les deux tiers des mots distinctifs du titre. Une jaquette qui est
    celle d'un autre jeu est pire qu'une pochette vide.

### Interface

| Clé | Défaut | Signification |
|---|---|---|
| `ui_lang` | `en` | `en` ou `fr`. Ajouter une langue est un fichier JSON — voir [Contribuer](contribuer.md). |
| `notify` | `true` | Prévenir quand une tâche se termine |

## Où vivent les fichiers

Tout ce que Romule écrit est préfixé d'un `_`, et atterrit dans l'un des deux
dossiers.

Dans le **dossier de données** (`ROMULE_ROOT`) :

| Fichier | Ce qu'il contient |
|---|---|
| `_romule-config.json` | Les réglages ci-dessus. En `chmod 600`. |
| `_romule-comptes.json` | Les comptes : empreintes scrypt et secrets TOTP |
| `_romule-lib.log` | Journal d'activité, tourné à 2 Mio, 3 fichiers gardés |
| `_romule-acces.log` | Journal des accès |
| `_covers/` | Jaquettes en cache |
| `_sauvegardes/` | Sauvegardes automatiques des réglages et des comptes |

À côté de tes **jeux** (`library_path`) :

| Fichier | Ce qu'il contient |
|---|---|
| `_import/` | Dépose des fichiers ici pour les importer |
| `_corbeille/` | La corbeille |

Ces deux-là suivent les jeux plutôt que le service, et c'est voulu : écarter un
jeu doit rester un renommage. À travers deux systèmes de fichiers,
`shutil.move` copie au lieu de déplacer, ce qui transformerait la mise à
l'écart d'un titre en plusieurs gigaoctets d'entrées-sorties.

!!! warning "Sauvegarde ces deux fichiers"
    `_romule-config.json` et `_romule-comptes.json` sont tes réglages et tes
    comptes. Ils ne sont récupérables de nulle part ailleurs.
