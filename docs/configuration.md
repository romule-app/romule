# Configuration

Two layers. **Environment variables** cover what must be known before Romule
starts. Everything else lives in the interface and is stored in
`_romule-config.json` inside your library folder.

## Environment variables

| Variable | Default | What it does |
|---|---|---|
| `ROMULE_ROOT` | `~/.local/share/romule` | Your library folder. **Set this.** |
| `ROMULE_WEB_PORT` | `8787` | Port to listen on |
| `ROMULE_BIND` | see below | Interface to bind to |
| `ROMULE_TOKEN` | — | Access token; overrides the generated one |
| `ROMULE_LAN` | — | `1` opens network access **without a password** |
| `ROMULE_KEYS` | `~/.romule/prod.keys` | Path to the decryption keys |
| `ROMULE_TRUSTED_PROXIES` | — | Comma-separated IPs whose forwarded headers are honoured |
| `ROMULE_UPLOAD_MAX` | 64 GiB | Largest accepted upload, bytes |
| `ROMULE_DISK_MARGIN` | 2 GiB | Free space kept in reserve, bytes |
| `ROMULE_NO_BROWSER` | — | `1` stops Romule opening a browser at startup |
| `ROMULE_TIMEOUT` | `300` | Socket timeout, seconds |
| `ROMULE_MAX_CONN` | `64` | Simultaneous connections |
| `ROMULE_RATE` | `600` | Requests per minute per client |
| `ROMULE_CHROME` | — | Chrome binary for the browser test suite |

`ROMULE_BIND` defaults to `127.0.0.1`, except in a container or once network
access is enabled — otherwise a published port would reach nothing.

!!! info "Old names still work"
    `SWITCH_*` variables are still read, and Romule prints their replacement at
    startup. They will be dropped in a later release.

## Settings

All of these are edited from the interface. The names are the keys stored in
`_romule-config.json`; you should not normally need to edit that file by hand.

### Access

| Key | Default | Meaning |
|---|---|---|
| `auth_mode` | `aucun` | `aucun`, `interne` (accounts), or `oidc` ([beta](beta.md)) |
| `lan_access` | `false` | Allow the network in **without a password** |
| `auth_secret` | generated | Signing key for session cookies. Never leaves the server. |
| `oidc_issuer` | — | Provider URL |
| `oidc_client_id` / `oidc_client_secret` | — | Client credentials |
| `oidc_redirect` | — | Redirect URI registered with the provider |
| `oidc_scopes` | `openid profile email` | Scopes requested |
| `oidc_emails` / `oidc_groupes` | — | Restrict who may log in |

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
| `local_layout` | `type` | Same idea, on the server side |
| `systemes_perso` | `[]` | Extra platforms you define yourself |
| `system_dirs` | `{}` | Folder overrides per platform |
| `trash_days` | `0` | Days before the trash empties itself. `0` never. |
| `verify_mode` | `size` | `size` compares size and date; `hash` fingerprints the contents |
| `incremental` | `true` | Only re-read what changed |
| `jobs` | `3` | Parallel conversions |
| `versions_urls` | titledb | Mirrors for the Switch version database |

### Covers and details

| Key | Default | Meaning |
|---|---|---|
| `cover_provider` | `nlib` | `nlib`, `steamgriddb`, or `custom` |
| `cover_url` | nlib template | Used when `cover_provider` is `custom`. `{tid}` is substituted. |
| `steamgriddb_key` | — | SteamGridDB API key |
| `igdb_client_id` / `igdb_client_secret` | — | IGDB credentials |
| `meta_lang` | `en` | Language for titles and summaries |
| `emuready` | `false` | Community compatibility ratings ([beta](beta.md)) |
| `emuready_device` | — | Which device to match ratings against |
| `emuready_device_nom` | — | Its display name, remembered so the list need not be fetched again |

### Interface

| Key | Default | Meaning |
|---|---|---|
| `ui_lang` | `en` | `en` or `fr`. Adding a language is a JSON file — see [Contributing](contribuer.md). |
| `notify` | `true` | Notify when a job finishes |

## Where the files live

Everything Romule writes sits in the library folder, prefixed with `_`:

| File | What it holds |
|---|---|
| `_romule-config.json` | The settings above. `chmod 600`. |
| `_romule-comptes.json` | Accounts: scrypt hashes and TOTP secrets |
| `_romule-lib.log` | Activity log, rotated at 2 MiB, 3 files kept |
| `_romule-acces.log` | Access log |
| `_covers/` | Cached cover art |
| `_import/` | Drop files here to import them |
| `_corbeille/` | Trash |
| `_sauvegardes/` | Automatic config and account backups |

!!! warning "Back these up"
    `_romule-config.json` and `_romule-comptes.json` are your settings and your
    accounts. They are not recoverable from anywhere else.
