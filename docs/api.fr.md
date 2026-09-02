# API HTTP

Romule expose une API petite et stable, pour interroger ta ludothèque depuis un
tableau de bord, un script ou une tâche planifiée — sans navigateur et sans
session.

[Télécharger la spécification OpenAPI 3.1](openapi.json){ .md-button }

## La promesse, précisément

Dans une même version majeure :

- aucune route ne disparaît ;
- aucun champ existant ne change de nom ni de type ;
- des champs **peuvent** apparaître — ignore donc ceux que tu ne connais pas.

C'est toute la promesse. Romule sert une centaine d'autres routes `/api/...` ;
elles existent pour sa propre interface, elles changent quand un écran change,
et elles ne sont **pas** couvertes. Si tu construis dessus, attends-toi à ce
qu'elles bougent.

!!! info "Pourquoi une surface à part"
    Geler les routes de l'interface reviendrait à geler l'interface. L'API
    publique est délibérément plus petite que ce dont l'application se sert,
    pour la même raison que Sonarr et Radarr publient une surface choisie
    plutôt que leurs entrailles.

## Obtenir une clé

Chaque requête a besoin d'une clé d'API. Les clés sont nommées, révocables une
par une, et montrent leur dernière utilisation.

**Depuis l'interface** — Réglages → Accès → Clés d'API. Donne-lui un nom qui
dise à quoi elle sert (`tableau-de-bord`, `sauvegarde-nuit`) : ce nom est ce qui te
permettra plus tard de savoir laquelle révoquer.

**En ligne de commande** — utile dans un conteneur, où il n'y a parfois aucun
navigateur :

```sh
romule apikey create tableau-de-bord
# sous Docker :
docker compose exec romule python3 -m romule apikey create tableau-de-bord
```

```
Cle creee : tableau-de-bord

  rml_Ac0ffee1S3cr3t...

Note-la maintenant : elle n'est conservee que sous forme
d'empreinte et ne pourra pas etre reaffichee.
```

!!! note "La sortie est sans accents"
    Elle est reproduite telle quelle. Comme le rapport d'audit et les pages de
    connexion, la ligne de commande est composée par le serveur et ne passe
    jamais par le catalogue de traduction de l'interface — voir
    [Fonctions bêta](beta.md#le-rapport-daudit-les-pages-de-connexion-et-la-ligne-de-commande-sont-en-francais).

!!! warning "Montrée une fois, et une seule"
    Romule range une empreinte SHA-256 de la clé, jamais la clé elle-même.
    C'est ce qui rend une fuite de son fichier d'état inoffensive — et c'est
    aussi pourquoi la clé ne peut plus jamais être réaffichée. Note-la à la
    création.

`romule apikey list` montre les clés, leur préfixe et leur dernier usage.
`romule apikey revoke <id>` en retire une. Une clé révoquée reste listée, pour
que tu puisses encore répondre à « est-ce que cette clé a servi après que je
l'ai retirée ? ».

## S'authentifier

Envoie la clé dans un en-tête :

```sh
curl -H "X-Api-Key: rml_..." http://localhost:8787/api/v1/stats
```

Un paramètre d'URL marche aussi, pour les clients à qui l'on ne peut donner
qu'une adresse — une tuile de tableau de bord, un `wget` dans un cron :

```sh
curl "http://localhost:8787/api/v1/stats?apikey=rml_..."
```

!!! warning "L'en-tête vaut mieux"
    Une URL finit dans les journaux du proxy, dans l'historique du navigateur
    et dans celui du shell. N'utilise le paramètre que si un en-tête est
    réellement impossible.

### Ce qu'une clé peut atteindre

Une clé atteint `/api/v1/` **et rien d'autre**. Elle ne peut ni ouvrir
l'interface, ni lire la configuration, ni toucher aux comptes.

C'est plus strict qu'il n'y paraît : présenter une clé ne *donne* pas des
droits, cela *choisit un régime*. Une requête venue de `127.0.0.1` obtient
normalement tous les droits locaux — mais dès qu'elle porte `X-Api-Key`, c'est
la clé qui décide, et la clé est portée. Une clé ne peut donc jamais élargir un
accès : au mieux, elle le restreint.

### CSRF

Romule refuse les requêtes qui modifient l'état et annoncent une origine
étrangère. Un client en ligne de commande n'envoie aucun en-tête `Origin` et
est accepté — c'est la clé qui protège ces routes, et un navigateur ne
l'attache jamais tout seul comme il attache un cookie.

## Les routes

L'adresse de base est ton instance, `http://localhost:8787` ci-dessous.

### Lire la ludothèque

| Route | Ce qu'elle donne |
|---|---|
| `GET /api/v1/health` | vivant — c'est aussi la sonde du conteneur |
| `GET /api/v1/system` | version, licence, source, temps de fonctionnement |
| `GET /api/v1/stats` | décomptes et taille totale |
| `GET /api/v1/library` | l'inventaire, paginé |
| `GET /api/v1/library/{cle}` | un jeu |
| `GET /api/v1/search?q=` | recherche par nom ou par title ID |
| `GET /api/v1/platforms` | plateformes configurées |
| `GET /api/v1/device` | état de la console connectée |
| `GET /api/v1/job` | la tâche en cours, s'il y en a une |
| `GET /api/v1/trash` | ce qui est encore restaurable |

```sh
curl -H "X-Api-Key: $CLE" http://localhost:8787/api/v1/stats
```

```json
{ "total": 412, "base": 180, "update": 150, "dlc": 82,
  "bytes": 174929203200, "to_convert": 3 }
```

La **clé** d'un jeu est son chemin relatif à la ludothèque — le même
identifiant que celui de l'interface. Elle contient des espaces et des
crochets : encode-la.

```sh
curl -H "X-Api-Key: $CLE" \
  "http://localhost:8787/api/v1/library/GAMES%2FUn%20Jeu%20%5B0100ABC%5D.nsp"
```

Aucun champ ne contient de chemin absolu. Il n'apprendrait rien à un client et
révélerait l'arborescence du serveur — souvent, le nom de compte de quelqu'un.

### Lancer une tâche

| Route | |
|---|---|
| `POST /api/v1/scan` | relire la ludothèque |
| `POST /api/v1/convert` | convertir les `.nsz` / `.xcz` restants |
| `POST /api/v1/push` | envoyer les jeux en attente vers la console |

```sh
curl -X POST -H "X-Api-Key: $CLE" http://localhost:8787/api/v1/scan
```

Romule exécute **une tâche à la fois** — il n'y a pas de file d'attente, et
l'API le dit plutôt que de faire semblant. Un démarrage rend `202` ; si quelque
chose tourne déjà, tu reçois `409`, et réessayer plus tard est la bonne
réponse.

Suis l'avancement avec `GET /api/v1/job` :

```json
{ "running": true, "label": "convert", "done": 2, "total": 5,
  "detail": "Un Jeu.nsz" }
```

## Pagination

`GET /api/v1/library` et `GET /api/v1/search` acceptent `page` (à partir de 1)
et `limit` (50 par défaut, 200 au maximum), et répondent avec la page et son
contexte :

```json
{ "page": 2, "limit": 50, "total": 412, "pages": 9, "items": [ … ] }
```

Deux comportements, volontairement différents :

- une valeur **illisible** (`page=zero`) retombe sur le défaut — le client
  s'est trompé de type, il n'y a rien à en tirer ;
- une valeur **hors bornes** (`limit=100000`, `limit=-4`) est ramenée dans les
  bornes — l'intention est claire, et la refuser obligerait chaque client à
  connaître le plafond avant de demander.

Une page au-delà de la fin rend un `items` vide, pas une erreur.

## Erreurs

| Code | |
|---|---|
| `400` | un paramètre obligatoire manque |
| `401` / `403` | pas de clé, clé inconnue, clé révoquée, ou hors de portée |
| `404` | route inconnue, ou clé de jeu inconnue |
| `409` | une tâche tourne déjà |
| `429` | débit limité — `Retry-After` dit combien de temps |
| `500` | quelque chose a échoué côté serveur |

Les corps d'erreur portent un `error` stable et un `message` lisible :

```json
{ "error": "busy", "message": "Another task is already running." }
```

Le `message` ne contient jamais de chemin du serveur : une panne interne est
rendue comme `internal_error` avec une phrase générique, et le détail va dans
le journal de Romule.

## Un exemple complet

Me prévenir quand plus de trois fichiers restent à convertir :

```sh
#!/bin/sh
CLE=rml_...
N=$(curl -fsS -H "X-Api-Key: $CLE" http://localhost:8787/api/v1/stats \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["to_convert"])')
[ "$N" -gt 3 ] && echo "$N fichiers à convertir" && \
  curl -fsS -X POST -H "X-Api-Key: $CLE" http://localhost:8787/api/v1/convert
```
