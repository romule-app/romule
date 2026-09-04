# Changelog

All notable changes to Romule are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Romule is at `0.x`: the HTTP API is **not** stable yet, and a minor release may
change it. Breaking changes are always listed under **Changed** with the reason.

## [Unreleased]

### Changed

- **The code is in English.** Comments, docstrings, function and variable
  names, CSS classes and the `data-act` action names. The repository is public,
  under the AGPL, with an English README, documentation and interface; French
  comments protected an internal consistency at the price of the only thing
  that matters for an open project — that one can get in.

  Nothing a user's disk holds moved. The configuration keys, the state files
  and the interface strings are French because they are DATA — the last of them
  are the i18n catalogue's keys, which is a mechanism, not a style.
  `test_cles_persistees.py` is what makes that a rule rather than an intention.

  Eleven modules were renamed: `rapprochement`→`matching`, `reseau`→`net`,
  `maj`→`updates`, `notifs`→`notify`, `doublons`→`duplicates`,
  `comptes`→`accounts`, `vues`→`views`, `sauvegarde`→`backup`,
  `profils`→`profiles`, `transferts`→`transfers`, `parcourir`→`browse`,
  `journal_acces`→`access_log`. `docs/openapi.json` is byte-identical: the
  public API did not move.

  The outputs of `cli.py` and `audit.py`, and the login pages, stay French:
  they do not go through the interface's catalogue, and translating them needs
  a server-side i18n Romule does not have. That limit is written in
  `docs/beta.md`.

### Added

- **A scheduler** (`romule/scheduler.py`). Five presets — never, at startup,
  hourly, every six hours, nightly at a chosen hour — on the five reversible
  tasks. No cron field: a syntax where a misplaced star means "every minute"
  has no place in a settings screen.

  If a task is already running when another falls due, the due one is
  **skipped** and logged — never queued. That is the same semantics as the
  API's 409: Romule does one thing at a time, and says so. The last run is
  persisted, without which a container that restarts often would run its
  nightly task all day.

  Emptying the trash, clearing the log and revoking a key are absent from the
  list, and that is not an oversight.

- **Several consoles** (`romule/consoles.py`). `wifi_addr` was singular, and so
  were `device_dir`, `roms_root`, `emulateur` and four more. Each console now
  keeps its own, and Romule remembers what each one held — so it can answer
  *which console is this game on?* about the one that is not plugged in.

  The migration is silent: an existing installation gets one console built from
  its current settings. The flat keys are still written, mirroring the active
  console, so a version that predates this reads the pairing where it left it.

- **Per-event notification subscriptions.** The event list went from five to
  nine: beside the two catch-alls — any task, by outcome — there are now
  specific ones for a transfer to the console, a conversion, the drop folder
  being filed, the entries being refreshed and an integrity check. Each
  destination has its own boxes in the settings, so a family channel can be
  told only when a transfer is over while an ops channel hears everything.

  A specific event also satisfies its catch-all, and a destination subscribed
  to both is told **once**. The specific ones fire whatever the outcome:
  someone watching for the end of a 12 GB transfer wants to know either way.

- **A library health screen** (`romule/report.py`, `/api/library-report`).
  Broken files, orphaned DLC, superseded versions, duplicates, games with no
  entry, what waits in the drop folder — each family with the button that
  deals with it. It assembles what already existed and computes nothing of its
  own. Coverage is shown beside it, because *no problem found* means something
  different at 4 % than at 100 %.

- **A dangling-attribute check** in `outils/verifier-imports.py`, after the
  module and the keyword: `notify.EVENEMENTS` and `apiv1.routes_decrites` both
  survived a rename and both lived in test files this machine cannot run. Only
  this package's modules are judged, and only where they are actually imported.

- **Three source checks**, each self-testing before it judges:
  `outils/verifier-anglais.py` (French prose in comments, docstrings and HTML
  comments), `outils/verifier-imports.py` (a module or a keyword a rename left
  behind) and `outils/verifier-classes.py` (a CSS class styled in one file and
  renamed in another). All three run in `lancer_tests.py` and in CI.

### Fixed

- **Three of the five notifiable events were never sent.** The settings offered
  *the console connected*, *a version is available* and *the drop folder was
  filed*; only `tache_ok` and `tache_echec` had an emitter. You could tick the
  other three and Romule would never say a word — no error, no log line,
  nothing to notice. A subscription to something nobody publishes is worse than
  a missing feature: it looks answered.

  The three are now emitted, and `test_events.py` compares the declared list
  against the emitters in both directions. `test_notify.py` could not catch it:
  it checks the shape of what leaves and the silence when nothing is
  configured, and both were true of an event nobody sent.

- **Two maintenance panels had been dead since 0.2.0.** `showMaintenance` and
  `openPlatform` read `getAttribute('onclick')` — an attribute phase 4 had
  removed. `null.includes` threw on the first line, so the five maintenance
  panels and the platform cards never opened: no request, no error on screen,
  nothing in the log. Found while adding the health screen beside them, and
  `test_ui_injection.js` now refuses any read of a handler attribute that no
  longer exists.

- **`server.py` imported `reseau` and called `net`.** The file parsed, the
  service started, and the failure waited for the first request on the route
  concerned. Found by `verifier-imports.py`, which was written for it — and
  which then immediately found two calls keeping a keyword a rename had moved.

## [0.3.1] — 2026-09-03

A follow-up to 0.3.0: the reverse-proxy example the documentation kept
promising, and the four defects that writing it uncovered.

### Added

- **`exemples/caddy/` — a complete reverse-proxy stack**, with Romule *not*
  published on the host: it is reachable only through Caddy. CI stands the
  stack up on every change and replays the matrix that matters:

  | | with `ROMULE_TRUSTED_PROXIES` | without |
  |---|---|---|
  | a genuinely local client, through the proxy | **200** | 403 |
  | an outside client forging `X-Forwarded-For: 127.0.0.1` | **403** | 403 |

  The two rows differ by one header and give opposite results. This cannot be
  proven with a double: what is being checked is what a *real* Caddy writes
  into the chain, and a double would only prove what it wrote itself.
- **`ROMULE_TRUSTED_PROXIES` accepts CIDR** — `172.16.0.0/12` beside
  `127.0.0.1`. Exact-string matching was fine while you wrote `127.0.0.1`; it
  stopped being fine the moment there was a container, because Docker assigns
  the proxy's address dynamically. The setting the documentation recommends was
  impractical in the deployment it recommends: you had to read an address after
  every `docker compose up` and fix it when it changed.

### Fixed

- **A network notation was compared as an address.** With
  `ROMULE_TRUSTED_PROXIES=10.0.0.0/8`, the literal string `10.0.0.0/8` was in
  the exact-match set, so a chain link equal to it counted as a declared relay.
  No exploitation is claimed — behind a real proxy the attacker's address is
  appended on the right and the walk stops there — but a notation is not an
  address, and it is fixed as the comparison bug it is.
- **The startup banner said "Network: disabled" right above the address to
  connect to.** The line followed the `lan_access` setting; in a container
  Romule listens on `0.0.0.0` and protects itself with a token, so the two
  disagreed in the most common case. It follows the socket now.

- **The update notice no longer reads "Version v0.3.0 available".** GitHub
  names its tags `v0.3.0` and the interface already writes the word *Version*
  in front. The prefix is stripped for display only — the comparison never read
  it. Noticed by running the notifier against the first real release.

## [0.3.0] — 2026-09-03

The release about the parts you touch. 0.2.0 made Romule publishable — public
repository, frozen API, strict CSP. This one is about the library itself: how
fast it answers, how it behaves on a phone and on a handheld, who is allowed to
do what, and what happens when something goes wrong at three in the morning
with no browser in reach.

### Added

- **The library opens on every platform at once, and switching is instant.**
  `setSystem` used to empty the grid *then* wait for a round trip: the content
  collapsed, the page jumped back to the top, and everything reappeared. The
  current view now holds until its replacement arrives, and each platform is
  kept in memory — going back is free. The cache is dropped on the only three
  events that change the inventory: a task ending, *Refresh*, and a file drop.
  A cache you cannot invalidate is a display bug on a timer.
- **Search that keeps up with typing.** Measured before, on 5 000 titles: 20.4 ms
  per keystroke, above the frame budget — the field felt sticky. The unified
  list only changes when the data, the platform or the sort order change, so it
  is memoised on exactly those; typing no longer rebuilds and re-sorts the whole
  library. The field is sticky, answers `/` and `⌘K`, and searches **all**
  platforms in the all-platforms view.
- **Saved filter views, kept on the server.** Search, status chip and advanced
  filters combine, and the combination can be named and found again — on your
  phone as on your desk. Sort order and tile size stay in the browser: those
  belong to the screen in front of you, not to the set of games.
- **One click clears every filter.** Three mechanisms filtered the library and
  nothing said how many were active; you could hunt for a while wondering why
  the grid was empty because of a chip set the day before. The button now
  carries the count of all three, and *Clear all* appears only when there is
  something to clear.
- **Two roles, SSO included.** The model existed by halves: the first account
  was administrator and 27 routes were reserved server-side, but the interface
  hid nothing, and an SSO session could **never** administer. `oidc_groupes`
  says who may enter; `oidc_admin_groupes` says who may administer. Empty means
  nobody — an empty setting must never mean everyone.
- **It behaves like an application, not a web page.** `100dvh`,
  `overscroll-behavior`, no tap highlight, safe-area insets, no long-press
  selection on chrome. The three gestures that gave away the web page are gone.
- **The D-pad walks the grid.** Retro handhelds are Android devices with a
  browser, a short screen and buttons rather than a precise finger. Arrow keys
  move card to card, Enter opens, Escape closes, and the focus ring is finally
  visible.
- **Ten device profiles in the responsive audit**, five of them handhelds:
  Anbernic RG35XX, Retroid Pocket 5, AYN Odin 2 / Thor, the Thor's second
  screen (360 × 413 — the only viewport taller than wide), and a Steam Deck.
- **An update notice.** A quiet pill in the header when a newer version exists,
  opening the release notes. It is an invitation, not an alarm: it appears only
  when there is something to read, blocks nothing, and can be ignored for
  weeks. One request to GitHub a day, and a setting to switch it off — the only
  time Romule reaches the internet unasked.
- **Notifications to Discord, Slack, Telegram, ntfy, Gotify — or any webhook.**
  Paste an address in Settings → Access; the service is worked out from it.
  Comparable tools reach for Apprise, which is a dependency; Romule has none,
  so the five families that cover most self-hosted setups are implemented in
  about a hundred lines of `urllib`, plus a generic webhook for the rest.
  The address is a bearer secret and is **never sent back** — the interface
  shows only the host, and it appears in no log, no API response and no
  `doctor` output.
- **`ROMULE_LOG` — five terminal log styles.** `quiet`, `normal`, `verbose`,
  `debug`, `json`. `JobRunner.log()` wrote to a file and an in-memory buffer
  and *never to stdout*, so `docker logs romule` showed almost nothing. It now
  writes to all three. `debug` adds each HTTP request with its status and
  duration, the module, the thread and seconds since startup; `verbose`
  deliberately stops short of it, because the interface polls `/api/job` in a
  loop and those lines would bury what you came to read.
- **A startup banner** naming the service and the facts you would otherwise
  spend half an hour looking for: version and Python, where settings live as
  opposed to games, who may connect, external tools found, the log file path.
- **Terminal commands for when the interface is not the answer** —
  `romule doctor`, `romule user list|passwd|admin|totp-off|rm`,
  `romule config list|get|set`. `user passwd` resets a password without the old
  one, invalidates that account's sessions and clears the lockout counter. They
  exist only on the command line: whoever can run them already has the
  service's files, so they grant nothing new — they only make it doable without
  mistakes.
- **Add a platform Romule does not know.** Twenty-three are recognised out of
  the box; a display name, a folder and a list of extensions adds any other.
  The feature existed and a button carried it — nothing said so.
- **A bilingual documentation site**, twelve pages in English and French, with
  CI checks that the settings reference, the environment variables, the OpenAPI
  specification, the numbers cited in prose and the two translation catalogues
  all still match the code.

### Changed

- **Plurals are real plurals.** 98 occurrences of `file(s)` — the most visible
  flaw in the interface, and on nearly every screen. A single rule would have
  traded one mistake for another: French puts 0 and 1 in the singular, English
  only 1. The template carries both forms, `{singular|plural}`, and the
  language picks — one catalogue key per sentence, and a translator writes the
  two forms of *their* language without needing to know French.
- **Undo instead of confirm.** The trash *is* the undo. Asking "are you sure?"
  charged the price of a mistake that costs nothing. The action happens, and
  the toast offers *Undo* for eight seconds. What genuinely cannot be undone —
  emptying the trash, clearing the log, revoking a key — still asks first.
- **On a phone, the content comes before the settings.** Nineteen controls used
  to sit between the top of the screen and the first cover. Filter and sort
  rows fold behind one button below 700 px; search stays reachable.
- **The library toolbar is aligned, and measured.** Three vertical axes in the
  same row — 245, 249 and 250 px — and three heights. `aria-expanded` carries
  the state and the CSS reads *that*, so there is one source of truth rather
  than a class to keep in step with what screen readers announce.
- **Installing no longer starts with `git clone`.** The container image is
  public on `ghcr.io/romule-app/romule` — `latest`, `0.3`, `0.3.0`, multi-arch,
  no authentication — so the recommended path is a Compose file you paste, with
  one line to change.
- **IGDB is now a second source for cover art.** SteamGridDB is a community
  *artwork* database: rich on what gets played with a keyboard, thin on
  handheld console catalogues. It does not have *Crazy Construction* — a real
  3DS game — while IGDB does, with its cover. Romule already queried IGDB for
  summaries and simply never asked it for images.
- **The library scan no longer uses `pathlib` in its hot loop.** Answering
  *"should this be in SQLite?"* honestly meant profiling it, and the profile
  said the bottleneck was never storage: on 20 000 titles, `Path.relative_to`
  was 39 % of the time and JSON serialisation did not appear at all. Rewritten
  with `os.walk` and strings, `/api/scan` went from **1 759 ms to 1 170 ms**
  and startup from **949 ms to 457 ms**. The rewrite was checked by replaying
  the old loop verbatim and comparing every field of 4 433 entries: zero
  differences. Written up in
  [Storage and performance](https://romule-app.github.io/romule/stockage/).

### Fixed

- **A wrong entry is worse than a missing one.** `covers.sgdb_infos()` took
  `found["data"][0]` — SteamGridDB's first autocomplete result, unchecked. On
  *Crazy Construction* it returns a game called *Crazy*, and since that title
  is then the pivot for the IGDB lookup, the card inherited both the name and
  the summary of a different game. One unchecked `[0]` produced both defects.
  Both sources now go through the same rule: a candidate must cover two thirds
  of the distinctive words of the title.
- **A cover source is consulted when there is no image, not when there is no
  address.** A `nlib` or SteamGridDB URL that answers 404 is still a URL; the
  fallback now runs after every candidate has been *downloaded* and rejected.
- **The title, not the file name, is sent to IGDB.** `Crazy Construction
  (Europe) (En,Fr,De).3ds` has `europe` and `3ds` among its distinctive words,
  so the matching rule rightly rejected the correct game. The fallback
  searched, found, and refused.
- **Two stray braces disabled half the stylesheet.** A lone `}` raises nothing
  visible: the browser resynchronises and silently drops everything up to the
  next safe point. The settings bar rendered as a vertical list on a 1500 px
  screen because its `display:flex` rule was simply no longer applied. Nothing
  caught it — not the tests, not CI, not me. I saw it by *looking at a
  screenshot*.
- **Commands exited 0 when they refused.** `romule user passwd` printed
  *"Refused: ..."* and reported success, so a script could not tell a refusal
  from a completed job. Found by the new tests — six perfectly worded refusals,
  all announced as successes.
- **Startup notices went to stdout.** `nsz absent — ...` was printed before
  every command, including ones whose output is meant to be read by a program:
  `VALUE=$(romule config get trash_days)` captured the notice along with the
  value. They go to stderr now. Found by CI, on a machine that has no `nsz`.
- **The documentation home page rendered its own markdown as text.** The card
  grid is written inside a `<div>`, and without the `md_in_html` extension
  everything in an HTML block is left verbatim. `--strict` cannot see it: it is
  not a MkDocs warning, it is a page that reads badly.
- **Numbers cited in the documentation are checked against the code.** The
  README claimed 37 settings when there were 41, and the roles page listed five
  families of admin-only routes when there are seven.
- **Two checks that guard against drift could not see it.** The settings
  reference and numbers checks lived in workflows filtered on `docs/**`: adding
  a setting without touching the docs never ran them. They moved to the
  unfiltered CI job, and `lancer_tests.py` now runs them locally too.
- **The access token and the activity log were documented in the wrong
  folder** — they live in the service data folder, not next to your games.
- **`beta.md` said the audit report and login pages were "English-only"** two
  lines above stating they are in French. They are in French, and so is the
  command line.
- **The contributing page still taught `'%d game(s) found'`**, the notation
  this release replaced with `{singular|plural}`.
- **Anchors are validated at build time.** A renamed heading used to leave
  `page.md#old-title` pointing nowhere, silently.

## [0.2.0] — 2026-09-01

### Added

- **A public HTTP API — `/api/v1`, fourteen routes, versioned and frozen.**
  Read the library, search it, watch the running task, start a scan, a
  conversion or a push. Within a major version no route disappears and no
  existing field changes name or type; new fields may appear.
  [Documented here](https://romule-app.github.io/romule/api/), with an OpenAPI
  3.1 specification served at `/api/v1/openapi.json` and checked in CI against
  the routes actually served.
  Romule's ~97 other `/api/...` routes exist for its own interface, follow it,
  and are **not** covered by that promise.
- **API keys.** Named, revocable one at a time, with a last-used date.
  Created from Settings → Access or with `romule apikey create <name>` —
  which is what makes the API usable inside a container, where there is no
  browser. Stored as a SHA-256 hash, so a leak of the state file is harmless
  and the key can never be shown again.
- **A key reaches `/api/v1/` and nothing else.** Presenting a key does not
  *grant* rights, it *selects a regime*: a request from `127.0.0.1` normally
  gets full local access, but the moment it carries `X-Api-Key` the key decides,
  and the key is scoped. A key can never widen an access — at most it narrows
  one.
- **`outils/essai-conteneur.py`** — a replayable full-scale container trial:
  build, health probe, token, the API from outside the container, key scope,
  restart persistence, revocation, audit. The CI compose step now runs the API
  half of it too, so the scope promise is verified against the shipped image
  and not only against `python3 -m romule`.
- The audit counts active API keys and flags those that have never been used.
  A key does not expire and reminds nobody it exists; the security report is
  the one place it gets re-read.

### Security

- **`script-src` no longer allows `'unsafe-inline'`.** This was the project's
  largest known weakness, listed in the README, in `SECURITY.md` and in the
  audit report. Removing it meant removing what depended on it: 153 inline
  event handlers, each one a reason the browser had to accept scripts written
  into the page. They now carry their action as data (`data-act`, `data-arg`),
  dispatched through a single delegated listener and an allow-list.
- **The gain is one parser fewer, not a stronger escape.** A value inside
  `onclick="app.do('HERE')"` crossed two parsers — HTML first, then JavaScript
  — which is what made the 0.1.0 stored XSS exploitable. Inside `data-arg` it
  crosses one, and nothing is ever compiled.
- **`jsq()` stays**, with its round-trip tests, as the guard for the day someone
  reintroduces an inline handler. Two stronger invariants replace its old role:
  no `on*=` attribute is generated anywhere, and every value interpolated into a
  `data-act`/`data-arg` goes through `esc()` — a double quote in a filename
  would otherwise leave the attribute.

### Added

- **A safety net for inert buttons.** A button that stops responding is
  invisible from the server: no request fails, nothing is logged. The test
  walks every screen, finds every clickable element, and fails if one has no
  handler — written *before* the first conversion, and green at every step
  while both mechanisms coexisted. It proves itself first, on six buttons built
  in the live page, one per form of coverage plus one genuinely inert.
- **A check that the CSP is actually enforced.** A violation does not break the
  page — the browser writes one console line and continues. The test listens for
  `securitypolicyviolation`, and proves the listener works by injecting an
  inline script and asserting the browser refuses to run it.
- `romule/tests/navigateur/ecrans.py` — the list of screens, in one place. Two
  tests sweep the rendered DOM; a screen added to only one of them would be a
  silent blind spot.

### Changed

- The anti-flash theme bootstrap moved from an inline `<script>` in
  `index.html` to `/theme.js`. It is still loaded blocking in `<head>`, which
  is the whole point of it. A single inline script was enough to require the
  CSP exception.
- Elements with `role="button"` now respond to Enter and Space through one
  general rule, replacing a hand-written `onkeydown` on the cover image.

### Fixed

- **`tid` was the fourth class doing double duty.** It marks a title ID, which
  must never be translated — but when a file has none, the same span carried
  the *label* “pas de title ID”, which must be. After `tid`, `cnom`, `jline`
  and now `tid` again, the pattern is settled: a CSS class cannot be both a
  style hook and a translation marker.
- **Two functions shadowed the translation helper.** `t()` translates; a local
  variable named `t` hides it for the whole scope, and the call becomes
  `t is not a function`. In `renderToolbar` it broke the *first* render, so the
  library never appeared and console detection never ran — and it worked fine
  on every later call, which is why nothing pointed at it. In `loadTrash` it is
  still latent: it throws as soon as the trash holds one batch, so the summary
  never renders — invisible on any test library, whose trash is empty. Twelve
  functions declare a local `t`; a test now asserts none of them also calls it.
- **`CLASSES_DONNEES` conflated a style hook with a "never translate" marker.**
  `jline`, `brow` and `crumb` wrap a *mixture*: a log line holds a timestamp, a
  level and a message, and only the message is data. Marking the wrapper froze
  the labels around it. The marker now sits on the data node itself, through
  `data-i18n-skip` — the attribute `traduisible()` already reads. This is the
  third instance of the same fault, after `tid` and `cnom`.
- **The browser test suites had never run in CI.** The guard looked for
  `/Applications/Google Chrome.app` — a macOS path — on an Ubuntu runner, so
  the whole family silently skipped and the job reported success. That included
  the anti-injection invariant. A test that runs nowhere is worse than no test:
  it hands out confidence. The guard now asks `cdp.trouver_chrome()`, and when
  `ROMULE_CHROME` is set — someone installed Chrome *for* these tests — a
  missing Chrome is a failure, not permission to move on.
- Chrome would not start on a Linux runner. `--no-sandbox` (only when `CI` is
  set) and `--disable-dev-shm-usage`, a 60 s wait instead of 24, and the error
  now carries what Chrome actually said instead of just "no answer".
- **The browser suites depended on the machine's hardware and on the author's
  own library.** They ran against the real library with the real `adb`, so the
  verdict changed depending on whether a console was plugged in, absent, or
  offline — three different answers for the same code. One assertion required
  the library to contain "Pokémon", "Mario" or "Animal Crossing". They now run
  on a fixed stage: a disposable root, three synthetic games, and a fake `adb`
  whose state is chosen. Same verdict in all three states, verified.
- Eight strings stayed in French in an English interface, seven of them only
  visible with a console connected — the branch the tests never rendered.
- The source-code link in the footer, which carries the AGPL source offer, had
  a 13 px tap target. It is now 44 px, the accessible minimum.

### Added

- **Attributes set before the catalogue loads stayed in the first language.**
  The observer only watches `childList`, so a `title` or `aria-label` written
  once at start-up was never revisited — and when its value was assembled from
  two labels, it was nobody's key either. Those attributes now keep their key
  on the element and are recomputed whenever the language changes.
- **The interface is fully translated.** 462 French phrases had no catalogue
  entry; the count is now zero, and the check that measures it blocks the
  build. Along the way, 62 sentences glued to a runtime value were rewritten
  as templates — a sentence assembled at runtime is nobody's key, and English
  cannot reorder what is already joined.
- **270 interface strings translated**, and the checker taught to stop
  over-reporting: a sentence too long for one line is written as two literals
  joined by `+`, and at runtime they are a single text node, so the key is the
  whole sentence. Testing the halves separately flagged 74 perfectly translated
  sentences as missing. Literals joined by `+` are now merged before the
  comparison, and tag fragments left by an interpolated value are stripped.
- **`outils/verifier-traduction.py` compares the code to the catalogue.** The
  existing check compares `fr.json` to `en.json` — parity is perfect, so it is
  green whatever happens. Nobody compared the *code* to the catalogue, which is
  the sole reason 462 French phrases accumulated without anything going red. It
  runs in CI as a warning until the backlog is cleared.
- **Responses are compressed** when the client accepts it. Measured on a
  2 000-title library: `/api/scan` goes from 2 088 KiB to 84 KiB (×25), and
  `app.js` + `app.css` + `index.html` from 508 KiB to 153 KiB (×3.3) — the
  latter matters because `_static` sends `Cache-Control: no-store`, so those
  508 KiB went out on *every* page load. Images are left alone, `gzip;q=0` is
  honoured, and the ETag distinguishes the two representations so a client
  that stops accepting gzip is not handed a 304 for a body it never had in
  that form.
- `ROMULE_ADB` points at the `adb` binary to run. Its purpose is to make the
  console's state choosable in tests, but it also serves anyone whose `adb`
  is not on the `PATH`.

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

- **Configured URLs were opened without checking their scheme.** `urlopen`
  accepts `file://` and `ftp://`, and three addresses come from settings — the
  artwork source, the titledb mirrors, the OIDC issuer. A `file:///etc/passwd`
  in the artwork field made the server read a local file and hand it back as an
  image. It takes an administrator to set those fields, which limits the reach,
  but an administrator should not be able to turn the service into a file
  reader through a settings box — and with authentication off there is no
  separate administrator at all. Every network call now goes through a single
  guarded exit, and a test asserts no direct call reappears elsewhere.


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

## [0.1.0] — 2026-09-01

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

- `script-src` still allows `'unsafe-inline'`: 152 inline event handlers
  depend on it. Documented, and slated for a later release.
- **No built-in TLS.** Exposing Romule to the internet requires a reverse
  proxy that terminates HTTPS.
- Emulator profiles other than Eden are untested on real hardware.

[Unreleased]: https://github.com/romule-app/romule/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/romule-app/romule/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/romule-app/romule/releases/tag/v0.1.0
