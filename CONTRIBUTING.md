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
```

The browser suite drives a real headless Chrome and catches what reading CSS
cannot: overflow, controls covered by other controls, untranslated strings.
If you touch the interface, run it.

## House style

The codebase has conventions that are deliberate, not accidental:

- **Comments and docstrings are in French.** Everything user-facing — README,
  documentation, default interface language — is in English. Do not translate
  the comments; do not write new ones in English.
- **A comment says why, never what.** If it restates the line below it, delete
  it. The ones worth writing explain a constraint that is invisible in the
  code: a rule that fights another rule, a value that was measured, a bug that
  a naive rewrite would bring back.
- **French is the i18n key.** `romule/locales/fr.json` is the catalogue,
  `en.json` the translation. A missing entry falls back to French.
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
