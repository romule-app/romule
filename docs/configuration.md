# Configuration

Two layers. **Environment variables** cover what must be known before Romule
starts. Everything else lives in the interface and is stored in
`_romule-config.json` inside the service data folder.

Romule keeps two folders apart, and the distinction runs through this whole
page:

- the **data folder** belongs to the service — settings, accounts, cover art,
  logs, backups. It is fixed by your deployment and has no reason to move.
- the **library** belongs to you — your games. It usually lives on another
  disk, and you pick it **from the interface**, not from a compose file.

By default the library *is* the data folder, so a single-folder install keeps
working exactly as before.

## Environment variables

| Variable | Default | What it does |
|---|---|---|
| `ROMULE_ROOT` | `~/.local/share/romule` | Service data folder: settings, accounts, artwork, logs |
| `ROMULE_LIBRARY` | — | Pins the games folder and **locks it** — the interface can no longer change it |
| `ROMULE_BASES` | — | Folders the interface may browse, separated like a `PATH`. Unset means everything the process can see. |
| `ROMULE_WEB_PORT` | `8787` | Port to listen on |
| `ROMULE_BIND` | see below | Interface to bind to |
| `ROMULE_TOKEN` | — | Access token; overrides the generated one |
| `ROMULE_LAN` | — | `1` opens network access **without a password** |
| `ROMULE_KEYS` | `~/.romule/prod.keys` | Path to the decryption keys |
| `ROMULE_TRUSTED_PROXIES` | — | Addresses whose forwarded headers are honoured, comma-separated. **CIDR is accepted** (`172.16.0.0/12`), which is what you want under Docker where the proxy's address is assigned dynamically. |
| `ROMULE_UPLOAD_MAX` | 64 GiB | Largest accepted upload, bytes |
| `ROMULE_DISK_MARGIN` | 2 GiB | Free space kept in reserve, bytes |
| `ROMULE_NO_BROWSER` | — | `1` stops Romule opening a browser at startup |
| `ROMULE_TIMEOUT` | `300` | Socket timeout, seconds |
| `ROMULE_MAX_CONN` | `64` | Simultaneous connections |
| `ROMULE_RATE` | `600` | Requests per minute per client |
| `ROMULE_CHROME` | — | Chrome binary for the browser test suite |
| `ROMULE_SCRYPT_PARALLELE` | `2` | How many password hashes may run at once. scrypt deliberately costs ~128 MiB each; without a cap, a handful of parallel sign-in attempts would exhaust the server's memory and turn a protection into a lever. |
| `ROMULE_LOG` | `normal` | How much Romule writes to the **terminal** — `quiet`, `normal`, `verbose`, `debug`, `json`. Unrelated to the Log panel in the interface: this is what `docker logs` and a systemd journal show. See [Reading the logs](#reading-the-logs). |
| `NO_COLOR` | — | Any value turns off colour, per the [no-color.org](https://no-color.org) convention. Colour is also off automatically when the output is not a terminal. |
| `ROMULE_ADB` | `adb` on the `PATH` | Path to the `adb` binary. A path that does not exist means “no console”, which is how the test suite stays independent of what is plugged in. |

`ROMULE_BIND` defaults to `127.0.0.1`, except in a container or once network
access is enabled — otherwise a published port would reach nothing.

`ROMULE_BASES` is not a sandbox and is not set by default. In a container the
real boundary is the `volumes:` list, applied by the kernel; on a bare install
it is the Unix account the service runs as. Jellyfin, Sonarr and qBittorrent
all work this way. Set `ROMULE_BASES` when you run natively under a broad
account and want to narrow the browser anyway. When it is set, it bounds both
what you can browse **and** what you can select — typing a path is not a way
around it.

!!! info "Old names still work"
    `SWITCH_*` variables are still read, and Romule prints their replacement at
    startup. They will be dropped in a later release.

## Reading the logs

Two logs answer two different questions, and they are not the same log.

The **Log panel** in the interface tells whoever is looking at their library
what it is currently doing. The **terminal** is where you find out why a
service will not start, on a machine where nobody can open a browser — a
container, a NAS, an ssh session. `ROMULE_LOG` controls the second one only.

| Value | What you get |
|---|---|
| `quiet` | Errors only |
| `normal` *(default)* | The startup banner, the facts it lists, warnings and errors |
| `verbose` | Plus every task event, timestamped |
| `debug` | Plus each HTTP request with its status and duration, the module, the thread, and seconds since startup |
| `json` | One JSON object per line, for a log collector |

```sh
docker compose logs -f romule                  # whatever the style is set to
ROMULE_LOG=debug python3 -m romule serve       # when something is wrong
```

!!! tip "`verbose` deliberately hides `debug`"
    The interface polls `/api/job` continuously while a task runs, and those
    requests are logged at `debug`. A `verbose` that showed them would bury the
    task events under dozens of lines a second — that is, make unreadable
    exactly what you opened it to read.

The startup banner is not decoration. It answers, before you go looking: which
version is actually running, where it keeps your settings as opposed to your
games, who may connect, which external tools it found, and where the log file
is. Each of those lines is a question that otherwise costs half an hour.

## Settings

All of these are edited from the interface. The names are the keys stored in
`_romule-config.json`; you should not normally need to edit that file by hand.

### Access

| Key | Default | Meaning |
|---|---|---|
| `auth_mode` | `aucun` | `aucun`, `interne` (accounts), or `oidc` ([beta](beta.md)) |
| `lan_access` | `false` | Allow the network in **without a password** |
| `maj_check` | `true` | Ask GitHub once a day whether a newer version exists. This is the **only** time Romule reaches the internet without being asked; turn it off and it never does. |
| `notif_destinations` | `[]` | Outgoing [notification](#notifications) destinations. Set from Settings → Access, not here: the address is checked and the count is capped. |
| `auth_secret` | generated | Signing key for session cookies. Never leaves the server. |
| `jeton_auto` | generated | The first-access token, kept so it survives restarts. Written only when the service is reachable and has no account, no `ROMULE_TOKEN` and no network access — see [Security](securite.md#the-first-access-token). |
| `oidc_issuer` | — | Provider URL |
| `oidc_client_id` / `oidc_client_secret` | — | Client credentials |
| `oidc_redirect` | — | Redirect URI registered with the provider |
| `oidc_scopes` | `openid profile email` | Scopes requested |
| `oidc_emails` / `oidc_groupes` | — | Restrict **who may log in** |
| `oidc_admin_groupes` | — | Groups whose members **may administer**. Empty: nobody does. |

!!! warning "Two different questions"
    `oidc_groupes` decides who gets in. `oidc_admin_groupes` decides who may
    open Settings and manage the tool. Confusing them would hand administration
    to everyone who can log in.

    The role is read from the token **at sign-in**, so removing someone from a
    group demotes them at their next session, not in the middle of the current
    one. See [Roles and access](roles.md).

### Your console

| Key | Default | Meaning |
|---|---|---|
| `emulateur` | `eden` | [Profile](profils.md) deciding all paths on the console |
| `emulateur_paquet` | — | Android package, detected from the console |
| `device_dir` | `/storage/emulated/0/Switch` | Switch games folder on the console |
| `roms_root` | — | Parent folder of the other platforms. Empty: derived from `device_dir`. |
| `wifi_addr` | — | Console address, remembered after pairing |
| `push_layout` | `type` | `type` sorts into `GAMES`/`UPDATE`/`DLC`; `plat` keeps it flat |
| `saves_dir` | — | Where game saves are backed up |
| `auto_nand` | `false` | Install into the emulator's NAND automatically |

### Library

| Key | Default | Meaning |
|---|---|---|
| `library_path` | — | The folder scanned for games. Empty means the data folder. Set from **Settings → Your library → Location**, not by hand. |
| `local_layout` | `type` | Same idea, on the server side |
| `systemes_perso` | `[]` | Extra platforms you define yourself |
| `system_dirs` | `{}` | Folder overrides per platform |
| `trash_days` | `0` | Days before the trash empties itself. `0` never. |
| `verify_mode` | `size` | `size` compares size and date; `hash` fingerprints the contents |
| `incremental` | `true` | Only re-read what changed |
| `jobs` | `3` | Parallel conversions |
| `versions_urls` | titledb | Mirrors for the Switch version database |

### On its own

Romule does nothing unasked until you tell it to. These two keys are what
change that, and only the first is yours to set.

| Key | Default | What it does |
|---|---|---|
| `schedule` | `{}` | What runs on its own: `{task: preset}`. The tasks are `scan`, `import`, `convert`, `push`, `meta`; the presets are `never`, `startup`, `hourly`, `6h` and `nightly:HH`. Set from **Settings → Maintenance → On its own**. |
| `schedule_state` | `{}` | When each scheduled task last ran. Written by Romule, never by hand: without it a restart makes every nightly task due again. |

Only reversible tasks can be scheduled. Emptying the trash, clearing the log
and revoking a key are absent from the list, and that is not an oversight: an
unattended action must be one whose result you can still look at in the
morning.

If a task is already running when another falls due, the due one is **skipped**
and said so in the log — it is not queued. Romule does one thing at a time.

### Covers and details

| Key | Default | Meaning |
|---|---|---|
| `cover_provider` | `nlib` | `nlib`, `steamgriddb`, or `custom` |
| `cover_url` | nlib template | Used when `cover_provider` is `custom`. `{tid}` is substituted. |
| `steamgriddb_key` | — | SteamGridDB API key |
| `igdb_client_id` / `igdb_client_secret` | — | IGDB credentials. Used for summaries **and**, when the chosen provider has no artwork, as a second cover source. |
| `meta_lang` | `en` | Language for titles and summaries |
| `emuready` | `false` | Community compatibility ratings ([beta](beta.md)) |
| `emuready_device` | — | Which device to match ratings against |
| `emuready_device_nom` | — | Its display name, remembered so the list need not be fetched again |

!!! info "Why covers have two sources"
    SteamGridDB is a community *artwork* database — rich on what gets played
    with a keyboard, thin on handheld console catalogues. IGDB is a game
    database, and it publishes cover art too. Romule already asked it for
    summaries; it now asks for artwork as well, but only after the chosen
    provider has failed to return an **image** — not merely an address, since
    a URL that answers 404 is still a URL.

    Both sources go through the same matching rule: a candidate has to cover
    two thirds of the distinctive words of the title. A cover that belongs to
    another game is worse than no cover at all.

### Interface

| Key | Default | Meaning |
|---|---|---|
| `ui_lang` | `en` | `en` or `fr`. Adding a language is a JSON file — see [Contributing](contribuer.md). |
| `notify` | `true` | Notify when a job finishes |

## Notifications

Romule could already tell you a task had finished — but only the person sitting
in front of it, with a desktop notification. What it does takes time: a
thirty-file conversion, a multi-gigabyte transfer. Those are precisely the
moments when you are **not** in front of the screen.

**Settings → Access → Notifications.** Paste a webhook address, give it a name,
done. The service is worked out from the address:

| Service | What to paste |
|---|---|
| Discord | `https://discord.com/api/webhooks/…` — Server settings → Integrations → Webhooks |
| Slack | `https://hooks.slack.com/services/…` — an Incoming Webhook |
| Telegram | `https://api.telegram.org/bot<token>/sendMessage?chat_id=<id>` |
| ntfy | `https://ntfy.sh/your-topic`, or your own instance |
| Gotify | `https://gotify.example.com/message?token=…` |
| Anything else | Any URL — Romule POSTs a plain JSON object |

Each destination can be tested before or after saving, and the result says
which side refused: a wrong address and a service that is down do not look the
same.

!!! warning "A webhook address is a bearer secret"
    Whoever holds it can post in your channel. Romule therefore **never sends
    it back** — the interface shows only the host, which is enough to tell two
    destinations apart. The address is not in the API responses, not in the
    log, and not in `romule doctor` output. Managing notifications is
    administrator-only, and so is testing one: an endpoint that fetches an
    arbitrary URL on demand is a port scanner by proxy.

Nothing is sent when nothing is configured. A self-hosted service that reaches
outward on its own is a problem, not a feature.

## Debugging from the terminal

These commands exist for the moment when the interface is **not** the answer:
no password left, no second factor, a service that will not start, or a
container with no browser. Until they existed, the only way out was editing
`_romule-comptes.json` by hand — pasting an scrypt hash computed elsewhere,
which nobody gets right the first time.

They grant nothing new. Whoever can run `romule` already has the service's
rights, and therefore its files. They only make doable, without mistakes, what
the filesystem already allowed.

```sh
romule doctor                              # everything a bug report should contain
romule user list
romule user passwd you@example.com         # asks twice, no echo
romule user admin you@example.com          # grant administration
romule user admin you@example.com --retirer
romule user totp-off you@example.com       # lost phone
romule user rm someone@example.com --oui
romule config list                         # secrets shown as "(n characters, masked)"
romule config get auth_mode
romule config set trash_days 7
```

Under Docker, prefix with `docker compose exec romule python3 -m romule`.

`romule user passwd` resets a password **without knowing the old one**. That is
why it exists only here and never as an HTTP route: a reset without proof of
identity is exactly what an attacker wants. It also invalidates every open
session for that account, and clears the failure counter — a lockout from
repeated wrong attempts would otherwise survive the reset and make the new
password look broken.

!!! tip "`romule doctor` is what to paste into an issue"
    Version, paths and their permissions, which port is taken, which external
    tools are on `PATH`, which remote services are configured, how many
    accounts and administrators, and the library breakdown per platform. It
    contains no password, no key, and no webhook address — that is checked by
    a test, not by intention.

Every one of these commands **exits non-zero when it refuses**. That sounds
obvious; it was not true when they were written, and a test caught six
perfectly worded refusals all reported as success.

## Where the files live

Everything Romule writes is prefixed with `_`, and lands in one of the two
folders.

In the **data folder** (`ROMULE_ROOT`):

| File | What it holds |
|---|---|
| `_romule-config.json` | The settings above. `chmod 600`. |
| `_romule-comptes.json` | Accounts: scrypt hashes and TOTP secrets |
| `_romule-lib.log` | Activity log, rotated at 2 MiB, 3 files kept |
| `_romule-acces.log` | Access log |
| `_covers/` | Cached cover art |
| `_sauvegardes/` | Automatic config and account backups |

Next to your **games** (`library_path`):

| File | What it holds |
|---|---|
| `_import/` | Drop files here to import them |
| `_corbeille/` | Trash |

These two follow the games rather than the service on purpose. Setting a game
aside has to stay a rename: across two filesystems `shutil.move` copies
instead, which turns discarding one title into several gigabytes of I/O.

!!! warning "Back these up"
    `_romule-config.json` and `_romule-comptes.json` are your settings and your
    accounts. They are not recoverable from anywhere else.
