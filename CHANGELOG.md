# Changelog

All notable changes to Romule are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Romule is at `0.x`: the HTTP API is **not** stable yet, and a minor release may
change it. Breaking changes are always listed under **Changed** with the reason.

## [Unreleased]

### Added

- **The games folder is chosen from the interface.** A folder picker in
  **Settings → Your library → Location**, and in the first-run wizard, browses
  the machine hosting the service. Administrator-only, folders only, with a
  count of recognised games so you can tell you are in the right place.
- `ROMULE_LIBRARY` pins that folder and locks the picker, for managed
  deployments. `ROMULE_BASES` bounds where the picker may go — and, equally,
  where a typed path may point.

### Changed

- **`ROMULE_ROOT` no longer means "your library".** It is now the service data
  folder: settings, accounts, cover art, logs, backups. The games live wherever
  `library_path` says, and default to the same folder — so an existing install
  sees no difference until it chooses otherwise.
- `_import/` and `_corbeille/` follow the **games** rather than the service.
  Setting a title aside has to stay a rename; across two filesystems
  `shutil.move` copies instead, turning a discard into gigabytes of I/O.
- The Docker image now exposes `/data` (named volume) alongside `/library`, so
  Romule's own state is no longer written among your games.

### Changed

- **Summaries taken from Wikipedia are now credited**, with a link to the
  article and the CC BY-SA licence — that licence requires attribution, and the
  source was recorded but never shown. The Wikimedia request now identifies the
  project and gives a contact URL, as their User-Agent policy asks; it claimed
  to be a "personal library" with no way to reach anyone.
- **The README screenshot was the author's own library** — fifteen real Switch
  titles, their publisher cover art, their file sizes and the console's name.
  A screenshot should show the software. It is now generated from a synthetic
  library: invented titles, no third-party artwork, no console.
- The legal section now states plainly that Romule bundles no emulator, never
  ships or helps obtain console keys, and that decryption is delegated to a
  separate tool you install yourself. It also carries the trademark notice that
  was missing: every console, publisher and emulator name belongs to its owner,
  and Romule is affiliated with none of them.
- Wording that implied games are obtained by download — "a game can be
  downloaded again", "incomplete file — download it again" — now says
  "reinstalled" and "replace it". Romule takes no position on where your files
  came from, and its interface should not either.

### Added

- **The journal button can be dragged up and down** the right edge, and stays
  where you put it. It used to hang at mid-height, which on some pages is
  exactly over what you are reading. Shift + arrow keys do the same thing, so
  the handle exists for people who do not use a mouse.

### Security

- **Stored XSS through filenames.** Values interpolated into inline event
  handlers were escaped for the HTML context only. A value inside
  `onclick="app.do('HERE')"` crosses two parsers: the HTML parser decodes
  `&#39;` back to an apostrophe *before* the JavaScript engine compiles the
  handler, so the string closed and the rest of the value ran as code. A card's
  key is the file's path, and nothing forbids an apostrophe in a filename —
  `x',alert(1),'.gba` uploaded through `/api/upload` was enough, and it ran in
  the session of whoever clicked the card, including an administrator. All 26
  interpolation points now use a JavaScript-context encoder, and a test asserts
  no handler can be added without one — a test that first proves it detects the
  violation shapes it claims to, line-wrapped ones included.
- Custom platform keys were only lowercased, never filtered, while the name and
  folder were. The key is an identifier everywhere — platform index,
  `system_dirs`, interface handlers. It is now normalised rather than rejected,
  so no already-declared platform disappears.

### Fixed

- **A game sheet opened from the versions list stayed behind it.** Both windows
  sit on the same layer, and at equal depth the DOM order decides — the
  versions list comes last. The sheet was drawn, just invisible. The last
  window opened now comes to the front, and closing it hands back to the one
  underneath.
- **The cover preview in the appearance settings was empty.** It borrows a real
  cover from your library, and when that image failed to load — the ordinary
  case on a fresh install — the code *removed* the image instead of falling
  back, so the seven effects had nothing left to show and no reload helped.
  There is now a generic cover, drawn inline, used both when no cover exists
  and when one fails to load.
- `en` was missing from the list of language markers used to group versions of
  the same game, while `fr`, `de`, `es`, `it`, `nl`, `pt`, `ru`, `kr` and `cn`
  were all there. `Game (EN)` and `Game (FR)` were not recognised as the same
  title.
- **Five strings stayed in French in an English interface**, all on the path a
  brand-new user takes: the "no console" header, its two hints, the empty
  library, and the state shown on **every** card when no console is connected.
  They were never caught because the test machine always had a console
  attached, so those branches never rendered. One was the same structural
  fault as an earlier one: the `cnom` class marked "never translate" because it
  carries the console's name, reused for a literal label that must be.
- **The service died at startup on an unwritable data folder**, on a raw
  traceback from `mkdir`. That is the most common containerised deployment
  mistake — a host folder bind-mounted into the container belongs to the host
  UID while the image runs as 1000 — and `Permission denied` alone says
  nothing about whose permission, or how to fix it. Startup now checks and
  names the remedy, and the import folder being unavailable is a warning
  rather than a fatal error.
- The onboarding step for the library sent you off to restart the service with
  an environment variable — on a NAS, that meant opening a terminal in the
  middle of the wizard.
- `phrase()` in the interface substituted only `%d`, leaving a raw `%s` on
  screen as soon as a path or a name entered a translated sentence.

## [0.1.0] — unreleased

First public release. Everything below is new by definition; the list covers
what the release actually contains rather than how it was built.

### Added

- **Library.** Inventory of a folder you already own, across Nintendo Switch
  (title IDs, base/update/DLC relationships, missing updates and orphaned DLC)
  and 22 retro platforms identified per file.
- **Transfer to an Android handheld** over adb, by USB or Wi-Fi, with pairing
  assistant, resumable transfers and free-space checks.
- **Emulator profiles** (`romule/profils/*.json`) for Eden, Yuzu, Sudachi,
  Citron, Ryujinx and a generic folder-only profile. Only Eden is verified on
  real hardware; the others are provided as-is and labelled as such.
- **First-run wizard**: six steps covering the library path with a scan that
  reports the platforms found, the first account, SteamGridDB and IGDB
  credentials tested on the spot, and optional console pairing.
- **Cover art and metadata** from SteamGridDB and IGDB, cached on disk so the
  grid never waits on the network.
- **Authentication**: internal accounts (scrypt), TOTP two-factor, and OIDC
  single sign-on. The first account created becomes the administrator.
- **Two interface languages**, English and French, switchable at runtime.
  Counts, units and badges are translated too: sizes read `GiB`/`MiB` in
  English and `Gio`/`Mio` in French, and phrases carrying a number go through a
  template rather than being glued together — which is what had left 49 of them
  in French inside an English interface, invisible to the translation check.
- **Documentation site** (MkDocs Material, GitHub Pages) covering installation,
  first run, the console, every one of the 37 settings, security and exposure,
  troubleshooting, and what each beta feature actually risks. A CI step fails if
  a setting exists in the code but not in the reference.
- **Themes** (light, dark, automatic), three cover animations, and a reduced
  motion setting honoured throughout.
- **Built-in security audit** (`python3 -m romule.audit`) reporting on the
  running configuration.
- **Docker image** with adb, nsz, unar and 7z included, running as a non-root
  user, plus a `docker-compose.yml`.
- **Zero runtime dependencies**: Python standard library only, enforced by the
  test suite.
- **First-access token.** A service that is reachable over the network but has
  no account, no token and no LAN access would refuse every request — including
  the one needed to reach the settings and fix it. Romule now generates an
  access token on first start in that situation, and prints it with the full
  URL. `docker compose up`, then `docker compose logs romule`, and you are in.
  Nothing is generated for a service listening on loopback only.

### Security

- The service binds to `127.0.0.1` unless network access is explicitly enabled.
- CodeQL analyses both the Python and the JavaScript sources; Trivy reports
  fixable HIGH/CRITICAL vulnerabilities in the published image. Neither existed
  before: the 6 500-line front-end had only a syntax check, and the image was
  not scanned at all.
- Every GitHub Action is pinned by commit SHA rather than by a mutable tag, and
  Dependabot proposes a grouped update once a month.
- A reachable service is never left open by default: the first-access token is
  generated instead of opening the door, it is stored outside the
  browser-visible configuration, and it stays stable across restarts.
- `X-Forwarded-For` and `X-Real-IP` grant nothing unless the operator names
  their proxies in `ROMULE_TRUSTED_PROXIES`.
- Account creation and deletion require an administrator; the very first
  account can only be created from the machine hosting the library.
- **Destructive actions require an administrator too.** Restoring a backup
  (which contains the accounts file, so it can hand administration back to
  whoever lost it), clearing the activity log, reading the access log, purging
  the trash, reorganising the library, writing into the emulator's own
  configuration, changing the console pairing, and running the security audit
  are all reserved. Ordinary accounts keep normal library use.
- The configuration file is written **atomically and with 0600 set before it
  takes its final name**. It previously appeared with the default umask for a
  moment while holding the session signing key, the API keys and the access
  token — and a crash mid-write truncated it, losing every setting.
- Upload size cap, free-space check, socket timeouts, connection cap and a
  request rate limiter.
- Path containment on custom platform folders, file extensions and title IDs —
  enforced both when reading *and* when writing, so a hostile value never even
  reaches the configuration file.
- **Twenty tests forge OpenID Connect identity tokens**, one per known attack:
  `alg: none`, RS256/HS256 confusion, a foreign signing key, an unknown `kid`,
  a tampered signature, a swapped payload keeping the original signature, wrong
  issuer, wrong audience, expired, dated from the future, mismatched nonce, and
  malformed input. All refused; a control test checks a valid token still
  passes.
- **Intrusion scenarios run against a live server**: path traversal and command
  injection through a custom platform, token brute force against the rate
  limiter, oversized upload, and a connection that opens and never finishes.

### Verified before release

- 302 checks across five suites, green on Python 3.10 through 3.13.
- Built as a wheel, installed into a clean virtualenv: no dependencies pulled,
  the `romule` command works, static files and locales ship with it.
- Dry run from a fresh `git clone` on an empty library: starts, serves, and
  passes its own suites. This is what caught `romule/__main__.py` never being
  committed — `.gitignore` excluded it, so the README's first command failed
  for everyone but the author.

### Known limitations

- `script-src` still allows `'unsafe-inline'`: 124 inline event handlers
  depend on it. Documented, and slated for a later release.
- **No built-in TLS.** Exposing Romule to the internet requires a reverse
  proxy that terminates HTTPS.
- Emulator profiles other than Eden are untested on real hardware.

[Unreleased]: https://github.com/romule-app/romule/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/romule-app/romule/releases/tag/v0.1.0
