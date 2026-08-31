# Changelog

All notable changes to Romule are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Romule is at `0.x`: the HTTP API is **not** stable yet, and a minor release may
change it. Breaking changes are always listed under **Changed** with the reason.

## [Unreleased]

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
