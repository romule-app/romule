# Installation

Romule est un seul processus Python **sans aucune dépendance d'exécution**.
Quelle que soit la voie choisie, il n'y a ni base de données à préparer, ni
file de messages, ni étape de compilation.

| Voie | Pour qui |
|---|---|
| [Docker Compose](#docker-compose-recommande) | presque tout le monde — NAS, mini-PC, serveur domestique |
| [Docker run](#docker-run) | un essai rapide, ou un orchestrateur déjà en place |
| [Depuis les sources](#depuis-les-sources) | développement, ou machine sans moteur de conteneurs |
| [En paquet Python](#en-paquet-python) | une installation système avec `pipx` |

---

## Docker Compose (recommandé)

Rien à cloner. Mets ceci dans un `docker-compose.yml`, change l'unique ligne de
`volumes:` qui désigne tes jeux, et démarre :

```yaml
services:
  romule:
    image: ghcr.io/romule-app/romule:latest
    container_name: romule
    restart: unless-stopped
    ports:
      - "8787:8787"
    environment:
      ROMULE_ROOT: /data
      ROMULE_BASES: /library
    volumes:
      - romule-donnees:/data
      - /chemin/vers/tes/jeux:/library    # ← la seule ligne à changer

volumes:
  romule-donnees:
```

```sh
docker compose up -d
docker compose logs romule      # affiche l'adresse avec ton jeton d'accès
```

Ouvre l'adresse affichée, crée ton compte dans l'assistant, et indique à Romule
où sont tes jeux. L'image embarque `adb`, `nsz`, `unar` et `7z` : il n'y a rien
d'autre à installer.

### Le même fichier, avec toutes les options

Celui du dessus est le minimum. Voici le même avec tout ce que tu peux vouloir
régler, commenté — le dépôt le livre sous le nom `docker-compose.yml`, avec
`build: .` à la place d'`image:` parce que qui a cloné le dépôt veut faire
tourner ce qu'il vient de lire.

```yaml
services:
  romule:
    image: ghcr.io/romule-app/romule:latest    # ou, depuis un clone : build: .
    container_name: romule
    restart: unless-stopped

    ports:
      - "8787:8787"

    environment:
      # L'état du service, dans le conteneur. Ne pas changer.
      ROMULE_ROOT: /data
      # Où l'interface a le droit de chercher des jeux. Le dossier exact se
      # choisit depuis l'interface au premier lancement — monte le parent et
      # sélectionne à l'intérieur.
      ROMULE_BASES: /library
      ROMULE_WEB_PORT: "8787"
      TZ: Europe/Paris

      # Rien d'autre n'est nécessaire. Au premier démarrage, Romule engendre un
      # jeton d'accès et l'affiche avec l'adresse complète :
      #     docker compose logs romule
      #
      # Pour imposer le tien plutôt que celui engendré :
      #     python3 -c "import secrets; print(secrets.token_urlsafe(32))"
      # ROMULE_TOKEN: ""
      #
      # Réseau de confiance et personne d'autre dessus ? On peut se passer de
      # jeton — mais alors tout appareil du réseau a tous les droits.
      # ROMULE_LAN: "1"

    volumes:
      - romule-donnees:/data      # volume nommé : réglages, comptes, jaquettes
      - ./library:/library        # ← tes jeux
      - ./keys:/keys:ro           # ← le dossier contenant prod.keys (facultatif)

    # L'image tourne déjà sous l'utilisateur 1000. Si le tien porte un autre
    # identifiant (`id -u`), pose-le ici pour que les fichiers déposés
    # t'appartiennent, et non à root.
    # user: "1000:1000"

volumes:
  romule-donnees:
```

### Ce qu'il faut monter

| Chemin dans le conteneur | Ce qu'on y met |
|---|---|
| `/data` | L'état du service : réglages, comptes, jaquettes, journaux. Un **volume nommé** — ces fichiers ne sont pas les tiens au même titre que tes jeux, et ils n'ont rien à faire au milieu d'eux. |
| `/library` | Tes jeux. Romule n'y écrit que `_import/` et `_corbeille/`. |
| `/keys` | Le dossier contenant `prod.keys`, en lecture seule. Facultatif — utile seulement pour les `.nsz` / `.xcz`. |

Tu n'es **pas** obligé de monter exactement le dossier des jeux. Monte ce qui
le contient — un disque entier, un partage, un dossier parent — et choisis le
bon depuis l'interface. C'est ce que veut dire `ROMULE_BASES: /library` :
parcourir n'importe où sous le montage, et nulle part ailleurs.

```yaml
    environment:
      ROMULE_BASES: /library
    volumes:
      - /mnt/nas:/library      # puis choisir /library/switch dans l'interface
```

Pour figer le dossier et interdire d'en changer depuis l'interface, pose
`ROMULE_LIBRARY: /library`.

### Réseau

Le fichier par défaut utilise un réseau *bridge* ordinaire avec un port publié.
Cela marche partout, y compris sous Docker Desktop sur macOS et Windows. **adb
par Wi-Fi fonctionne dans ce mode** : le conteneur atteint ton réseau local, et
tu saisis l'adresse de la console une fois.

=== "Wi-Fi (par défaut, marche partout)"

    ```yaml
    ports:
      - "8787:8787"
    ```

=== "Réseau de l'hôte (Linux seulement)"

    Nécessaire uniquement pour que la console soit *découverte* toute seule par
    mDNS.

    ```yaml
    network_mode: host
    ```

=== "USB (Linux seulement)"

    Cela affaiblit l'isolation du conteneur. À activer en connaissance de cause.

    ```yaml
    devices:
      - /dev/bus/usb:/dev/bus/usb
    ```

### À qui appartiennent les fichiers

L'image tourne sous l'uid 1000, le premier compte sur la plupart des
distributions : les fichiers t'appartiennent donc plutôt qu'à root. Si ton uid
diffère (`id -u`), pose `user: "<uid>:<gid>"`.

---

## Docker run

La même chose sans fichier compose :

```sh
docker run -d --name romule --restart unless-stopped \
  -p 8787:8787 \
  -e ROMULE_ROOT=/data \
  -e ROMULE_BASES=/library \
  -v romule-donnees:/data \
  -v /mnt/jeux:/library \
  ghcr.io/romule-app/romule:latest

docker logs romule              # l'adresse avec ton jeton d'accès
```

!!! tip "Les étiquettes disponibles"
    `latest` suit la dernière version publiée. `0.3.0` fige une version exacte
    et `0.3` en suit les correctifs — épingle l'une des deux si tu préfères
    choisir quand tu montes de version. L'image est multi-architecture
    (`amd64` et `arm64`) et ne demande aucune authentification.

    ```sh
    docker pull ghcr.io/romule-app/romule:0.3.0
    ```

    Tu peux aussi la construire toi-même : `docker compose up -d --build` rend
    la même image depuis les sources, et c'est la réponse honnête si tu
    préfères ne pas exécuter un binaire que tu n'as pas construit.

---

## Depuis les sources

Python 3.10 ou plus récent. Aucune étape d'installation, aucun environnement
virtuel, aucune compilation.

```sh
git clone https://github.com/romule-app/romule
cd romule
ROMULE_ROOT=/chemin/vers/romule-data python3 -m romule
```

Romule refuse de démarrer sur une racine manifestement fausse — la racine du
disque, ton dossier personnel, un dépôt de code — parce qu'il y déplace des
fichiers et y crée des dossiers.

### En faire un service

=== "systemd (Linux)"

    `/etc/systemd/system/romule.service` :

    ```ini
    [Unit]
    Description=Romule
    After=network-online.target

    [Service]
    Type=simple
    User=romule
    Environment=ROMULE_ROOT=/var/lib/romule
    Environment=ROMULE_LIBRARY=/srv/jeux
    Environment=ROMULE_BIND=127.0.0.1
    ExecStart=/usr/bin/python3 -m romule serve --no-browser
    WorkingDirectory=/opt/romule
    Restart=on-failure

    [Install]
    WantedBy=multi-user.target
    ```

    ```sh
    sudo systemctl enable --now romule
    journalctl -u romule -f
    ```

=== "launchd (macOS)"

    `~/Library/LaunchAgents/fr.romule.plist`, puis
    `launchctl load ~/Library/LaunchAgents/fr.romule.plist` :

    ```xml
    <?xml version="1.0" encoding="UTF-8"?>
    <plist version="1.0"><dict>
      <key>Label</key><string>fr.romule</string>
      <key>ProgramArguments</key>
      <array>
        <string>/usr/bin/python3</string><string>-m</string>
        <string>romule</string><string>serve</string><string>--no-browser</string>
      </array>
      <key>EnvironmentVariables</key>
      <dict><key>ROMULE_ROOT</key><string>/Users/moi/Library/romule</string></dict>
      <key>RunAtLoad</key><true/>
      <key>KeepAlive</key><true/>
    </dict></plist>
    ```

### Outils externes

Tous facultatifs. L'absence de l'un désactive une fonction ; aucun n'empêche le
démarrage. Romule dit ce qui manque et comment l'installer sur ta plateforme.

| Outil | Sert à | Debian/Ubuntu | macOS |
|---|---|---|---|
| `adb` | Parler à la console | `apt install android-tools-adb` | `brew install android-platform-tools` |
| `nsz` | Convertir les `.nsz` / `.xcz` | `pipx install nsz` | `brew install pipx && pipx install nsz` |
| `unar` | Extraire les `.rar` | `apt install unar` | `brew install unar` |
| `7z` | Extraire les `.7z` | `apt install p7zip-full` | `brew install p7zip` |

---

## En paquet Python

Romule **n'est pas encore sur PyPI** : installe-le depuis le dépôt.

```sh
pipx install git+https://github.com/romule-app/romule
ROMULE_ROOT=/chemin/vers/romule-data romule serve
```

Il n'entraîne aucune dépendance — la bibliothèque standard lui suffit.

---

## Derrière un proxy inverse

Romule parle du HTTP en clair. Tout ce qui est joignable depuis internet a
besoin d'un proxy qui termine le HTTPS devant lui.

!!! danger "Nomme ton proxy, sinon les en-têtes transmis ne valent rien"
    Un proxy sur la même machine fait paraître **toutes** les requêtes comme
    venant de `127.0.0.1`, et Romule accorde tous les droits aux requêtes
    locales. Il ignore donc `X-Forwarded-For` tant que tu ne nommes pas le
    proxy toi-même :

    ```sh
    ROMULE_TRUSTED_PROXIES=127.0.0.1,::1
    ```

    Sans cela, tous les utilisateurs partagent une seule adresse apparente et
    la limitation de débit se dégrade. Voir
    [Sécurité et exposition](securite.md).

=== "Caddy"

    ```
    romule.exemple.fr {
        reverse_proxy 127.0.0.1:8787
    }
    ```

=== "nginx"

    ```nginx
    server {
        server_name romule.exemple.fr;
        client_max_body_size 0;          # les dépôts sont des jeux entiers
        location / {
            proxy_pass http://127.0.0.1:8787;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_request_buffering off;
            proxy_read_timeout 3600s;
        }
    }
    ```

=== "Traefik (étiquettes)"

    ```yaml
    labels:
      - traefik.enable=true
      - traefik.http.routers.romule.rule=Host(`romule.exemple.fr`)
      - traefik.http.routers.romule.tls.certresolver=le
      - traefik.http.services.romule.loadbalancer.server.port=8787
    ```

Quel que soit le proxy, relève la taille de corps autorisée et le délai de
lecture : un seul envoi peut peser plusieurs gigaoctets et durer des minutes.

---

## Mettre à jour

=== "Docker Compose"

    ```sh
    docker compose pull       # ou : docker compose build --pull
    docker compose up -d
    ```

=== "Depuis les sources"

    ```sh
    git pull
    # puis redémarrer le service
    ```

Ton état vit dans le volume `/data` et survit. Romule te prévient quand une
version plus récente existe — une fois par jour, dans l'en-tête, avec les notes
de version. Coupe-le dans **Réglages → Accès** si tu préfères qu'il ne demande
jamais rien.

## Sauvegarder

Tout ce qui appartient à Romule tient dans un dossier — `ROMULE_ROOT`, ou le
volume `/data` :

```sh
docker run --rm -v romule-donnees:/data -v "$PWD:/out" \
  alpine tar czf /out/romule-data.tgz -C /data .
```

Romule écrit aussi ses propres instantanés de réglages sous
**Réglages → Entretien**, ce qui suffit à défaire une mauvaise configuration
mais n'est *pas* une sauvegarde de tes jeux.

## Désinstaller

```sh
docker compose down -v          # -v retire aussi le volume d'état
```

Tes jeux ne sont pas touchés : ils n'étaient que montés. Rien n'y a été écrit
sauf `_import/` et `_corbeille/`, que tu peux supprimer.
