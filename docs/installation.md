# Installation

## Docker (recommended)

```sh
git clone https://github.com/romule-app/romule
cd romule
docker compose up -d
docker compose logs romule      # prints the URL with your access token
```

Open the address it prints. The image ships `adb`, `nsz`, `unar` and `7z`, so
nothing else needs installing.

### What to mount

| Container path | What goes there |
|---|---|
| `/data` | Romule's own state: settings, accounts, artwork, logs. A named volume — leave it alone. |
| `/library` | Your games. Romule writes only `_import/` and `_corbeille/` alongside them. |
| `/keys` | The folder holding `prod.keys`, read-only. Optional. |

Edit the `volumes:` lines in `docker-compose.yml` to point at your folders.

You are **not** required to mount the games folder exactly. Mount whatever
contains it — a whole disk, a share, a parent folder — and pick the right one
from the interface on first run. That is what `ROMULE_BASES: /library` in the
compose file means: browse anywhere under the mount, and nowhere else.

```yaml
    environment:
      ROMULE_BASES: /library
    volumes:
      - /mnt/nas:/library      # then choose /library/switch in the interface
```

To fix the folder instead and stop anyone changing it from the interface, set
`ROMULE_LIBRARY: /library`.

### Networking

The default compose file uses ordinary bridge networking with a published
port. This works everywhere, including Docker Desktop on macOS and Windows.
adb over Wi-Fi works in this mode: the container reaches your local network,
you enter the console's address once.

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

The image runs as uid 1000, which is the first account on most distributions,
so files land owned by you rather than by root. If your uid differs, set
`user: "<uid>:<gid>"` in the compose file.

## Without Docker

Python 3.10 or newer. No install step, no virtualenv, no build.

```sh
git clone https://github.com/romule-app/romule
cd romule
ROMULE_ROOT=/path/to/romule-data python3 -m romule
```

Romule refuses to start on a library root that is clearly wrong — the disk
root, your home folder, or a code repository — because it moves files and
creates folders there.

### External tools

All optional. A missing one disables a feature; none prevent startup. Romule
tells you what is missing and how to install it on your platform.

| Tool | Needed for | Debian/Ubuntu | macOS |
|---|---|---|---|
| `adb` | Talking to the console | `apt install android-tools-adb` | `brew install android-platform-tools` |
| `nsz` | Converting `.nsz` / `.xcz` | `pipx install nsz` | `brew install pipx && pipx install nsz` |
| `unar` | Unpacking `.rar` | `apt install unar` | `brew install unar` |
| `7z` | Unpacking `.7z` | `apt install p7zip-full` | `brew install p7zip` |

## As a Python package

```sh
pip install romule
ROMULE_ROOT=/path/to/romule-data romule serve
```

It pulls no dependencies — the standard library is all it uses.
