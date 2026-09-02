<h1 align="center">Romule</h1>

<p align="center">
  <strong>Self-hosted manager for the game library you already own.</strong><br>
  Sorts it, fills in the cover art, and pushes titles to an Android handheld over adb.
</p>

<p align="center">
  <a href="#licence"><img alt="Licence AGPL-3.0" src="https://img.shields.io/badge/licence-AGPL--3.0-blue"></a>
  <img alt="Version 0.2.0" src="https://img.shields.io/badge/version-0.2.0-orange">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-green">
  <img alt="Zero dependencies" src="https://img.shields.io/badge/dependencies-none-brightgreen">
  <img alt="Beta" src="https://img.shields.io/badge/status-beta-yellow">
</p>

> **Beta.** Romule works and is used daily, but it is young. Some features are
> explicitly labelled beta in the interface. The public `/api/v1` **is** stable;
> the routes the interface uses for itself are not, and are not documented as
> such. Read [Known limitations](#️-known-limitations) before exposing it to the
> internet.

<p align="center">
  <img src="docs/images/apercu-bureau.jpg" alt="Romule in a desktop browser: a
  grid of game cards with cover art, size, platform and update badges, a
  platform selector, a search field and filter chips above."
  width="900">
</p>

<p align="center">
  <img src="docs/images/apercu-portables.jpg" alt="Romule on a retro handheld
  console and on a phone. On the handheld, the filter and sort rows are folded
  behind a single button so the cover art starts near the top of the short
  screen. On the phone, the same folding leaves the platform selector, the
  search field and one button."
  width="900">
</p>

---

## ✨ Key features

- 🗂️ **Your library, whatever it holds.** Nintendo Switch in detail — title
  IDs, base/update/DLC relationships, missing updates, orphaned DLC — plus 22
  other platforms identified per file, **and any platform you declare
  yourself**.
- ⚡ **No waiting between platforms.** The **“all platforms”** view is the
  default, because that is what you own. Per-platform views are one click away
  and stay in memory: switching back is instant, and the grid never blanks.
- 🖼️ **Cover art and details, cached.** SteamGridDB for artwork, IGDB for
  summaries, year, publisher — and for artwork too when SteamGridDB has none.
  Everything is stored on disk, so the grid never waits on the network.
- 🔍 **Find things.** Search by name or title ID, combine it with status chips
  and advanced filters, clear all three in one click — and **save a combination
  as a view**, kept on the server so it is the same on your phone and on your
  desk.
- 📲 **Push to a handheld** over adb, by USB or Wi‑Fi, with a pairing assistant,
  resumable transfers and free-space checks. Emulator layouts are
  **profiles**, not hard-coded paths.
- 🎮 **Works where you actually are.** The interface folds down for phones and
  for retro handhelds — short landscape screens included — and the grid is
  walkable with a **D-pad**: arrow keys move from card to card, Enter opens.
  The responsive audit runs on ten device profiles in CI, from a 640 × 480
  Anbernic to a Steam Deck.
- 👥 **Two roles, and nothing else to reason about.** Administrators change
  settings and manage accounts; everyone else gets the library and its actions.
  Works with internal accounts (scrypt, optional TOTP) or with your OpenID
  Connect provider, where a group decides who administers.
- 🔌 **Scriptable.** A small, versioned
  [HTTP API](https://romule-app.github.io/romule/api/) with named, revocable
  keys — for a dashboard, a cron job, or a shell script.
- ↩️ **Reversible.** Sending a file to the trash does not ask you to confirm:
  it happens, and the toast offers *Undo*. Only what cannot be undone asks
  first.
- 🔔 **Tells you when it is out of date.** One request to GitHub a day, the
  release notes in the interface, and a setting to switch it off. That is the
  only time Romule reaches the internet unasked.
- 🔒 **Yours.** Romule ships no games, no console keys, and no links to either.

### 🔗 Integrations

| | |
|---|---|
| **Emulators** | Eden, Yuzu, Sudachi, Citron, Ryujinx — as [profiles](https://romule-app.github.io/romule/profils/), not hard-coded paths |
| **Handhelds** | Any Android device over **adb**, USB or Wi‑Fi: AYN Odin 2 / Odin 3 / Thor, Retroid Pocket, Anbernic, AYANEO, GPD |
| **Artwork & metadata** | SteamGridDB (covers), IGDB / Twitch (summaries, year, publisher), Wikipedia (fallback), titledb (Switch versions) |
| **Community settings** | EmuReady — per-game emulator settings, matched to your device *(beta)* |
| **Conversion** | `nsz` for `.nsz` / `.xcz`, `unar` and `7z` for archives dropped into `_import` |
| **Authentication** | Internal accounts with scrypt + TOTP, or **OpenID Connect** — Authentik, Keycloak, Authelia, Pocket ID, Zitadel, Google, GitHub |
| **Reverse proxies** | Traefik, Caddy, nginx, NGINX Proxy Manager — with `ROMULE_TRUSTED_PROXIES` so forwarded headers are only honoured from proxies you name |
| **Dashboards & automation** | Any client that can send a header: Homarr, Homepage, Glance, Uptime Kuma, n8n, cron, `curl` — through the [HTTP API](https://romule-app.github.io/romule/api/) |
| **Containers** | Docker and Docker Compose, multi-arch `amd64` / `arm64` — Synology, unRAID, TrueNAS, Proxmox LXC, Raspberry Pi |
| **Desktop & mobile** | Installable as a PWA (standalone window, home-screen icon) on macOS, Windows, Linux, iOS and Android |

---

## 🚀 Quick start

```sh
git clone https://github.com/romule-app/romule
cd romule
docker compose up -d
docker compose logs romule      # prints the URL with your access token
```

Open the address it prints, create your account in the six-step wizard, and
point Romule at your library. Nothing else needs configuring.

<details>
<summary>Without Docker</summary>

```sh
git clone https://github.com/romule-app/romule
cd romule
python3 -m romule
```

Romule starts on `~/.local/share/romule` and asks you where your games are —
you pick the folder from the interface. Pass `ROMULE_ROOT` to put its own
data (settings, accounts, artwork) somewhere else.

Python 3.10 or newer. No install step, no virtualenv, no build — Romule uses
the standard library only.
</details>

### 🔑 Why a token, and where it comes from

The container is reachable from your network but has no account yet. Rather
than open the service without a password, Romule generates an access token on
first start and prints it with the full URL. It is stored in your library
folder and does not change when the container restarts. A service that only
listens on `127.0.0.1` gets no token — nothing to protect it from.

---

## 🎮 Platforms and emulators

### 🕹️ Supported platforms

Twenty-three are recognised out of the box:

Nintendo Switch · PlayStation 1/2/3 · PSP · PS Vita · GameCube · Wii · Wii U ·
Nintendo 3DS · DS · 64 · SNES · NES · Game Boy Advance · Game Boy / Color ·
Dreamcast · Saturn · Mega Drive · Arcade (MAME/FBN) · Xbox · Xbox 360 · PC

**The list is not a limit.** *Settings → Your console → Add a platform…* takes
a display name, a folder on the console and a list of extensions — Neo Geo,
MSX, a handheld nobody ported yet — and that platform is then scanned,
filtered, counted and pushed like any other. It is also how you handle a
console Romule *does* know but that you keep in a folder it would not guess.
[How to add one](https://romule-app.github.io/romule/console/#a-platform-romule-does-not-know).

Switch is the only platform whose files Romule opens: title IDs, base/update/DLC
relationships and missing updates come from reading the container. Every other
platform — built-in or added — is identified by folder and extension.

### 🎛️ Emulator profiles

The target device and emulator are profiles, not hard-coded paths.

| Profile | Verified on real hardware |
|---|---|
| **Eden** | yes — the reference profile |
| Yuzu, Sudachi, Citron, Ryujinx | no, provided as-is |
| Generic (games folder only) | no |

Unverified profiles are labelled as such in the interface. Pick yours in
**Settings → Your console**.

---

## ⚙️ Configuration

Romule reads its settings from the interface; environment variables cover what
must be known before it starts.

| Variable | Default | What it does |
|---|---|---|
| `ROMULE_ROOT` | `~/.local/share/romule` | Service data folder: settings, accounts, artwork, logs |
| `ROMULE_LIBRARY` | — | Pins the games folder and locks it against changes from the interface |
| `ROMULE_BASES` | — | Folders the interface may browse, separated like a `PATH` |
| `ROMULE_WEB_PORT` | `8787` | Port to listen on |
| `ROMULE_BIND` | see below | Interface to bind to |
| `ROMULE_TOKEN` | — | Access token; overrides the generated one |
| `ROMULE_LAN` | — | `1` opens network access **without a password** |
| `ROMULE_KEYS` | `~/.romule/prod.keys` | Path to the decryption keys |
| `ROMULE_TRUSTED_PROXIES` | — | Comma-separated IPs whose forwarded headers are honoured |
| `ROMULE_UPLOAD_MAX` | 64 GiB | Largest accepted upload |
| `ROMULE_DISK_MARGIN` | 2 GiB | Free space kept in reserve |
| `ROMULE_NO_BROWSER` | — | `1` stops Romule opening a browser at startup |
| `ROMULE_TIMEOUT` | `300` | Socket timeout, seconds |
| `ROMULE_MAX_CONN` | `64` | Simultaneous connections |
| `ROMULE_RATE` | `600` | Requests per minute per client |

`ROMULE_BIND` defaults to `127.0.0.1`, except in a container or when network
access has been enabled — otherwise a published port would reach nothing.

All 40 settings in the configuration file are edited from the interface and
documented on the
[documentation site](https://romule-app.github.io/romule/).

### 🧰 External tools

All optional. Missing ones disable a feature; none prevent Romule from
starting. The Docker image ships all of them.

| Tool | Needed for |
|---|---|
| `adb` | Talking to the console |
| `nsz` | Converting `.nsz` / `.xcz` (also needs `prod.keys`) |
| `unar`, `7z` | Unpacking archives dropped into `_import` |

---

## 🔒 Security

**Romule has no built-in TLS.** It speaks plain HTTP and expects a reverse
proxy in front of it for anything reachable from the internet. If you run one,
name it in `ROMULE_TRUSTED_PROXIES` — otherwise its forwarded headers grant
nothing, by design, because a proxy on the same host makes every request look
local.

A few things it does on its own:

- Binds to `127.0.0.1` unless you say otherwise.
- The first account created is the administrator; only an administrator changes
  settings or manages accounts. The very first account can only be created from
  the machine hosting the library.
- Passwords are hashed with scrypt; TOTP two-factor is available.
- Upload caps, free-space checks, socket timeouts, a connection cap and a rate
  limiter.

Run `python3 -m romule.audit` after any change: it reports on the configuration
actually running, and the CI fails on anything it rates *grave*.

Reporting a vulnerability: see [SECURITY.md](SECURITY.md).

### ⚠️ Known limitations

- **No TLS.** A reverse proxy is required for internet exposure.
- **`style-src` allows `'unsafe-inline'`.** Inline `style=` attributes are
  common in the generated markup. A style is not executed, so this is a much
  narrower exception than the `script-src` one removed in 0.2.0.
- **Beta features**, labelled in the interface: OpenID Connect SSO (RS256
  verification written for Romule, no third-party library), emulator
  configuration piloting (Romule writes into another program's files),
  EmuReady community settings, transfer resume.
- Emulator profiles other than Eden are untested on real hardware.

---

## 🤖 This application is vibe coded

Said plainly, because you are about to run it on your own machine.

Romule was written with an AI assistant — most of its code, its tests and its
documentation. It was not typed line by line by a person who holds the whole
design in their head. That has consequences worth knowing:

- **Nobody has read every line.** The code is reviewed, but not with the
  familiarity a hand-written codebase gives its author.
- **What holds it up is the checks, not the memory of the author.** Five test
  suites — unit, end-to-end HTTP, security audit, real-browser interface, leak
  detection — run on every change, across four Python versions. CodeQL analyses
  both languages, Trivy scans the image. That is deliberate: it is the part
  that scales when the writing does not.
- **Bugs will look different.** Expect the plausible-but-wrong over the typo:
  code that reads well and does the wrong thing at an edge. If something looks
  odd, it may well be.
- **Comments explain *why*.** They carry the reasoning that would otherwise be
  lost, including the mistakes that were made and corrected. They are in French
  — deliberately, see [CONTRIBUTING.md](CONTRIBUTING.md).

If that is not for you, that is a fair call. If it is, bug reports are
especially useful here.

---

## ⚖️ Legal

Romule is a library manager. It **does not** provide games, console keys, or
any means of obtaining them, and it contains no links to either. It manages
files that are already on your disk.

Whether you may legally hold those files depends on where you live and how you
obtained them. That question is yours, not this project's. Please do not open
issues asking where to find games or keys; they will be closed.

### 🗝️ Console keys

Romule never ships, generates, or helps you obtain console keys. Decrypting
`.nsz` / `.xcz` is delegated to [`nsz`](https://github.com/nicoboss/nsz), a
separate tool you install yourself and point at a key file you supply. Romule
works without any of it — keys are needed only for those two formats.

Be aware that in some jurisdictions, extracting or using such keys may be
restricted **even for content you own**. Romule takes no position on that and
gives no guidance on it.

### 👾 Emulators

Romule bundles no emulator and distributes none. An emulator *profile* is
nothing more than a description of where a given third-party program keeps its
files, so that Romule can copy games to the right place. Naming a program is
not an endorsement, a partnership, or a claim that anyone authorised it.

### ™️ Trademarks

Nintendo Switch, and the names of every console, publisher and emulator
mentioned here, are trademarks of their respective owners. Romule is an
independent project, not affiliated with, endorsed by, or connected to any of
them. Those names are used only to say what the software works with.

---

## 📚 Project documents

| Document | What it covers |
|---|---|
| [Documentation site](https://romule-app.github.io/romule/) | Install, first run, console setup, full configuration reference — **in English and French** |
| [Documentation en français](https://romule-app.github.io/romule/fr/) | La même, traduite intégralement |
| [HTTP API](https://romule-app.github.io/romule/api/) | Keys, the fourteen routes, pagination, errors |
| [Roles and access](https://romule-app.github.io/romule/roles/) | The two roles, the three modes, and OIDC group mapping |
| [CHANGELOG.md](CHANGELOG.md) | What changed, release by release |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Zero-dependency rule, house style, how to run the suites |
| [SECURITY.md](SECURITY.md) | How to report a vulnerability, and what is in scope |

## 🛠️ Development

```sh
python3 lancer_tests.py               # unit, server and audit suites
python3 lancer_tests.py --navigateur  # adds the real-Chrome interface suites
python3 -m romule.audit               # self-audit
python3 outils/verifier-fuite.py      # refuses personal data in the git index
python3 outils/mesurer-perf.py        # timings on a synthetic library
```

## Licence

Romule is free software under the
[GNU Affero General Public License v3.0 or later](LICENSE).

The AGPL was chosen deliberately: Romule is a **network service**, and the AGPL
is what keeps a hosted fork open. If you run a modified Romule and let others
reach it over a network, section 13 requires you to offer them your source. The
interface footer carries that offer — it links to the source and shows the
running version, and `/api/health` reports both. Keep it working if you fork.
