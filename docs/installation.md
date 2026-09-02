# Installation

Romule is one Python process with **no runtime dependencies**. Whatever route
you take, there is no database to provision, no message queue, no build step.

| Route | Good for |
|---|---|
| [Docker Compose](#docker-compose-recommended) | almost everyone — NAS, mini-PC, home server |
| [Docker run](#docker-run) | a quick trial, or an existing orchestrator |
| [From source](#from-source) | development, or a machine without a container runtime |
| [As a package](#as-a-python-package) | a system-wide install with `pipx` |

---

## Docker Compose (recommended)

Nothing to clone. Put this in a `docker-compose.yml`, change the one `volumes:`
line that points at your games, and start it:

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
      - romule-data:/data
      - /path/to/your/games:/library      # ← the only line to change

volumes:
  romule-data:
```

```sh
docker compose up -d
docker compose logs romule      # prints the URL with your access token
```

Open the address it prints, create your account in the wizard, and point Romule
at your games. The image ships `adb`, `nsz`, `unar` and `7z`, so nothing else
needs installing.

### The same file, with every option

The one above is the minimum. This is the same file with everything you might
want to set, commented — the repository ships it as `docker-compose.yml`, with
`build: .` in place of `image:` because someone who cloned the repository wants
to run what they just read.

```yaml
services:
  romule:
    image: ghcr.io/romule-app/romule:latest    # or, from a clone: build: .
    container_name: romule
    restart: unless-stopped

    ports:
      - "8787:8787"

    environment:
      # Romule's own state, inside the container. Do not change.
      ROMULE_ROOT: /data
      # Where the interface may browse for games. The exact folder is chosen
      # from the interface on first run — mount the parent and pick inside.
      ROMULE_BASES: /library
      ROMULE_WEB_PORT: "8787"
      TZ: Europe/Paris

      # Nothing else is required. On first start Romule generates an access
      # token and prints it with the full URL:
      #     docker compose logs romule
      #
      # To pin your own instead:
      #     python3 -c "import secrets; print(secrets.token_urlsafe(32))"
      # ROMULE_TOKEN: ""
      #
      # Trusted network and nobody else on it? You can do without a token —
      # but then every device on the LAN has every right.
      # ROMULE_LAN: "1"

    volumes:
      - romule-donnees:/data      # named volume: settings, accounts, artwork
      - ./library:/library        # ← your games
      - ./keys:/keys:ro           # ← the folder holding prod.keys (optional)

    # The image already runs as uid 1000. If yours differs (`id -u`), set it
    # here so dropped files belong to you and not to root.
    # user: "1000:1000"

volumes:
  romule-donnees:
```

### What to mount

| Container path | What goes there |
|---|---|
| `/data` | Romule's own state: settings, accounts, artwork, logs. A **named volume** — these files are not yours the way your games are, and they have no business sitting among them. |
| `/library` | Your games. Romule writes only `_import/` and `_corbeille/` alongside them. |
| `/keys` | The folder holding `prod.keys`, read-only. Optional — needed only for `.nsz` / `.xcz`. |

You are **not** required to mount the games folder exactly. Mount whatever
contains it — a whole disk, a share, a parent folder — and pick the right one
from the interface. That is what `ROMULE_BASES: /library` means: browse
anywhere under the mount, and nowhere else.

```yaml
    environment:
      ROMULE_BASES: /library
    volumes:
      - /mnt/nas:/library      # then choose /library/switch in the interface
```

To pin the folder instead and stop anyone changing it from the interface, set
`ROMULE_LIBRARY: /library`.

### Networking

The default file uses ordinary bridge networking with a published port. This
works everywhere, including Docker Desktop on macOS and Windows. **adb over
Wi-Fi works in this mode**: the container reaches your local network, and you
enter the console's address once.

=== "Wi-Fi (default, works everywhere)"

    ```yaml
    ports:
      - "8787:8787"
    ```

=== "Host networking (Linux only)"

    Needed only for the console to be *discovered* automatically over mDNS.

    ```yaml
    network_mode: host
    ```

=== "USB (Linux only)"

    This weakens container isolation. Enable knowingly.

    ```yaml
    devices:
      - /dev/bus/usb:/dev/bus/usb
    ```

### File ownership

The image runs as uid 1000, the first account on most distributions, so files
land owned by you rather than by root. If your uid differs (`id -u`), set
`user: "<uid>:<gid>"`.

---

## Docker run

Same thing without a compose file:

```sh
docker run -d --name romule --restart unless-stopped \
  -p 8787:8787 \
  -e ROMULE_ROOT=/data \
  -e ROMULE_BASES=/library \
  -v romule-donnees:/data \
  -v /mnt/games:/library \
  ghcr.io/romule-app/romule:latest

docker logs romule              # the URL with your access token
```

!!! tip "Available tags"
    `latest` follows the newest release. `0.2.0` pins an exact version and
    `0.2` follows its patches — pin one of those if you would rather choose
    when you upgrade. The image is multi-arch (`amd64` and `arm64`) and needs
    no authentication.

    ```sh
    docker pull ghcr.io/romule-app/romule:0.2.0
    ```

    You can also build it yourself — `docker compose up -d --build` produces
    the same image from the sources, and is the honest answer if you would
    rather not run a binary you did not build.

---

## From source

Python 3.10 or newer. No install step, no virtualenv, no build.

```sh
git clone https://github.com/romule-app/romule
cd romule
ROMULE_ROOT=/path/to/romule-data python3 -m romule
```

Romule refuses to start on a library root that is clearly wrong — the disk
root, your home folder, a code repository — because it moves files and creates
folders there.

### Running it as a service

=== "systemd (Linux)"

    `/etc/systemd/system/romule.service`:

    ```ini
    [Unit]
    Description=Romule
    After=network-online.target

    [Service]
    Type=simple
    User=romule
    Environment=ROMULE_ROOT=/var/lib/romule
    Environment=ROMULE_LIBRARY=/srv/games
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

    `~/Library/LaunchAgents/fr.romule.plist`, then
    `launchctl load ~/Library/LaunchAgents/fr.romule.plist`:

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
      <dict><key>ROMULE_ROOT</key><string>/Users/me/Library/romule</string></dict>
      <key>RunAtLoad</key><true/>
      <key>KeepAlive</key><true/>
    </dict></plist>
    ```

### External tools

All optional. A missing one disables a feature; none prevent startup. Romule
tells you what is missing and how to install it on your platform.

| Tool | Needed for | Debian/Ubuntu | macOS |
|---|---|---|---|
| `adb` | Talking to the console | `apt install android-tools-adb` | `brew install android-platform-tools` |
| `nsz` | Converting `.nsz` / `.xcz` | `pipx install nsz` | `brew install pipx && pipx install nsz` |
| `unar` | Unpacking `.rar` | `apt install unar` | `brew install unar` |
| `7z` | Unpacking `.7z` | `apt install p7zip-full` | `brew install p7zip` |

---

## As a Python package

Romule is **not on PyPI yet**, so install it from the repository:

```sh
pipx install git+https://github.com/romule-app/romule
ROMULE_ROOT=/path/to/romule-data romule serve
```

It pulls no dependencies — the standard library is all it uses.

---

## Behind a reverse proxy

Romule speaks plain HTTP. Anything reachable from the internet needs a proxy
terminating HTTPS in front of it.

!!! danger "Name your proxy, or forwarded headers grant nothing"
    A proxy on the same host makes **every** request look like it comes from
    `127.0.0.1`, and Romule grants local requests full access. It therefore
    ignores `X-Forwarded-For` unless you name the proxy yourself:

    ```sh
    ROMULE_TRUSTED_PROXIES=127.0.0.1,::1
    ```

    Without it, every user shares one apparent address and rate limiting
    degrades. See [Security and exposure](securite.md).

=== "Caddy"

    ```
    romule.example.com {
        reverse_proxy 127.0.0.1:8787
    }
    ```

=== "nginx"

    ```nginx
    server {
        server_name romule.example.com;
        client_max_body_size 0;          # uploads are whole games
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

=== "Traefik (labels)"

    ```yaml
    labels:
      - traefik.enable=true
      - traefik.http.routers.romule.rule=Host(`romule.example.com`)
      - traefik.http.routers.romule.tls.certresolver=le
      - traefik.http.services.romule.loadbalancer.server.port=8787
    ```

Whichever you use, raise the body size limit and the read timeout: a single
upload can be several gigabytes and take minutes.

---

## Updating

=== "Docker Compose"

    ```sh
    docker compose pull       # or: docker compose build --pull
    docker compose up -d
    ```

=== "From source"

    ```sh
    git pull
    # restart the service
    ```

Your state lives in the `/data` volume and survives. Romule tells you when a
newer version exists — once a day, in the header, with the release notes. Turn
it off in **Settings → Access** if you would rather it never asked.

## Backing up

Everything Romule owns is in one folder — `ROMULE_ROOT`, or the `/data` volume:

```sh
docker run --rm -v romule-donnees:/data -v "$PWD:/out" \
  alpine tar czf /out/romule-data.tgz -C /data .
```

Romule also writes its own settings snapshots under **Settings → Upkeep**,
which is enough to undo a bad configuration but is *not* a backup of your
games.

## Uninstalling

```sh
docker compose down -v          # -v also removes the state volume
```

Your games are untouched: they were only ever mounted. Nothing was written
inside them except `_import/` and `_corbeille/`, which you can delete.
