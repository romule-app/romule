# Contributing to Romule

Bug reports, fixes and translations are all welcome. Please read the two
constraints below first — they shape almost every review comment.

## Two rules that are not negotiable

**1. Zero runtime dependencies.** Romule runs on the Python standard library
alone. `python3 lancer_tests.py` fails if a non-stdlib import appears. External
binaries (`adb`, `nsz`, `unar`, `7z`) are optional: their absence disables a
feature and never prevents the service from starting.

**2. No personal data, no game data, no keys.** `outils/verifier-fuite.py`
refuses console keys, ROMs, cover images, state files, credentials and private
IP addresses in the git index. Run it before every commit. Romule ships no
games, no `prod.keys`, and no links to either.

## Getting set up

```bash
git clone https://github.com/romule-app/romule
cd romule
ROMULE_ROOT=/tmp/romule-test python3 -m romule serve
```

No install step, no virtualenv, no build. Python 3.10 or newer.

## Before you open a pull request

```bash
python3 lancer_tests.py --navigateur   # all five suites
python3 outils/verifier-fuite.py       # leak check
python3 -m romule.audit                # 0 grave, 0 alerte expected
uvx ruff check romule outils lancer_tests.py   # exactly what CI runs
```

`ruff` is a development tool, not a runtime dependency — running it through
`uvx` (or `pipx run ruff`) keeps it out of the environment. CI runs the same
command and it blocks, so running it locally saves a round trip.

`lancer_tests.py` already runs the source checks — the leak check is separate
because it reads the git index, not the working tree:

| Check | What it refuses |
|---|---|
| `verifier-anglais.py` | French prose in comments, docstrings and HTML comments |
| `verifier-imports.py` | a module or a keyword a rename left behind |
| `verifier-classes.py` | a CSS class styled in one file and renamed in another |
| `verifier-traduction.py` | a French sentence in the code with no catalogue entry |
| `verifier-chiffres.py` | a number in the documentation the code no longer backs |
| `verifier-reglages-doc.py` | a setting with no line in the reference |

Each one self-tests before it judges: a check nobody has seen fail proves
nothing.

The browser suite drives a real headless Chrome and catches what reading CSS
cannot: overflow, controls covered by other controls, untranslated strings.
If you touch the interface, run it.

Opening a pull request additionally runs CodeQL on both languages, builds the
Docker image for amd64 and arm64, starts it and checks that it answers. None of
that needs an account or a secret, so it works the same on a pull request from
your fork as it does on a branch here.

## House style

The codebase has conventions that are deliberate, not accidental:

- **Comments and docstrings are in English**, like everything else the
  repository shows: README, documentation, default interface language.
  `outils/verifier-anglais.py` refuses French prose in comments and docstrings,
  and CI runs it. A line that deliberately *quotes* French — a catalogue key,
  for instance — carries `anglais:ok` with its reason beside it.
- **A comment says why, never what.** If it restates the line below it, delete
  it. The ones worth writing explain a constraint that is invisible in the
  code: a rule that fights another rule, a value that was measured, a bug that
  a naive rewrite would bring back.
- **French is the i18n key.** `romule/locales/fr.json` is the catalogue,
  `en.json` the translation. A missing entry falls back to French. This is a
  mechanism, not a style: the interface strings in the code are French because
  they are the catalogue's keys, and that has not changed.
- **Never assemble a translatable sentence from fragments.** `'Found ' + n + '
  games'` produces three keys no catalogue can hold. Use a `%s` / `%d`
  template and translate it whole.
- `%`-formatting, not f-strings, throughout — for consistency, nothing more.

## Adding a translation

Copy `romule/locales/fr.json` to `xx.json`, keep the French keys, translate the
values, and set `_meta.langue` to the language's own name. It appears in the
selector automatically. The browser suite checks that no French text survives
when another language is active.

## Adding an emulator profile

Drop a JSON file in `romule/profils/`, modelled on `eden.json`. Set
`"verifie": false` unless you have run it on real hardware — the interface
labels unverified profiles, and that label is the honest default.

## Commit messages

Say what changed and why it was wrong before. A subject line, a blank line,
then prose. The reason matters more than the diff, which is already visible.

## Reporting a bug

Include the version (interface footer, or `python3 -m romule --version`), how
it is running (Docker or bare metal), and what you expected. If it involves the
console, `python3 -m romule.audit` output helps.

Security problems go through
[private reporting](https://github.com/romule-app/romule/security/advisories/new),
not the issue tracker. See [SECURITY.md](SECURITY.md).

## Licence

Contributions are accepted under the [AGPL-3.0-or-later](LICENSE), the
project's licence.
