# Contributing

The full guide lives in
[CONTRIBUTING.md](https://github.com/romule-app/romule/blob/main/CONTRIBUTING.md).
The short version:

## Two rules that are not negotiable

**Zero runtime dependencies.** Romule runs on the Python standard library
alone, and a blocking CI job fails if a non-stdlib import appears. External
binaries (`adb`, `nsz`, `unar`, `7z`) are optional: a missing one disables a
feature, never startup.

**No personal data, no game data, no keys.** `outils/verifier-fuite.py` refuses
console keys, ROMs, cover images, state files, credentials and private IP
addresses in the git index.

## Running the checks

```sh
python3 lancer_tests.py --navigateur   # all five suites
python3 outils/verifier-fuite.py       # leak check
python3 -m romule.audit                # 0 grave, 0 alerte expected
```

The browser suite drives a real headless Chrome and catches what reading CSS
cannot: overflow, controls covered by other controls, untranslated strings. If
you touch the interface, run it.

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

## Adding a translation

Copy `romule/locales/fr.json` to `xx.json`, keep the French keys, translate the
values, set `_meta.langue` to the language's own name. It appears in the
selector on its own.

!!! warning "Never assemble a sentence from fragments"
    `'Found ' + n + ' games'` produces three keys no catalogue can hold. Use
    `tpl('%d games found', n)`, or `countPhrase(n, '{game|games}')` for a bare count.
    This mistake hid 49 phrases from the translation check once already.

!!! tip "Plurals are written `{singular|plural}`"
    `1 file(s)` is not a plural, it is an admission. Both forms go in the
    string — `countPhrase(n, '{file|files}')` — and the catalogue picks one **per
    language**, because the rules differ: French writes *0 fichier* in the
    singular, English writes *0 files* in the plural. A single rule for both
    would trade one mistake for another.

## Retaking the screenshots

```sh
python3 outils/captures.py
```

From an **invented** library — thirty titles, nine platforms, covers drawn on
the spot, and a stand-in console. That is the default, and it is the answer for
almost every change: a shot taken from a real installation says what its owner
owns, and carries somebody else's cover art into a public repository.

Two ways to photograph a real one, when the point IS the real one:

```sh
python3 outils/captures.py --racine ~/mes-donnees      # from the source tree
python3 outils/captures.py --url http://localhost:8787 # an instance already up
```

`--racine` starts a server from the working tree on that data folder, takes the
shots, and stops it. Prefer it while developing. `--url` against a container
means rebuilding the image for every fix — and a rebuild restarts the adb
server, which drops the console, which is the pairing the shots need. From the
source tree there is no rebuild: the code is whatever is on disk.

Either way the tool masks addresses, e-mail addresses, serial numbers and home
paths before the shutter, and **refuses the shot** if anything it does not know
how to mask is still readable. `outils/verifier-fuite.py` reads text files; it
cannot read a PNG, and the console's address sits in plain sight on one of
these screens.

## Adding an emulator profile

Drop a JSON file in `romule/profils/`, modelled on `eden.json`. Set
`"verifie": false` unless you have run it against real hardware — the interface
labels unverified profiles, and that label is the honest default.

## House style

Comments and docstrings are **in English**, like everything else the repository
shows. `outils/verifier-anglais.py` refuses French prose there and CI runs it; a
line that deliberately quotes French carries `anglais:ok` with its reason. The
interface strings themselves stay French — they are the i18n catalogue's keys,
which is a mechanism, not a style.

A comment says *why*, never *what*: if it restates the line below it, delete it.
The ones worth writing explain a constraint invisible in the code — a rule
fighting another rule, a measured value, a bug a naive rewrite would bring
back.
