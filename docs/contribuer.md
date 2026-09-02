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

## Adding a translation

Copy `romule/locales/fr.json` to `xx.json`, keep the French keys, translate the
values, set `_meta.langue` to the language's own name. It appears in the
selector on its own.

!!! warning "Never assemble a sentence from fragments"
    `'Found ' + n + ' games'` produces three keys no catalogue can hold. Use
    `phrase('%d games found', n)`, or `nb(n, '{game|games}')` for a bare count.
    This mistake hid 49 phrases from the translation check once already.

!!! tip "Plurals are written `{singular|plural}`"
    `1 file(s)` is not a plural, it is an admission. Both forms go in the
    string — `nb(n, '{file|files}')` — and the catalogue picks one **per
    language**, because the rules differ: French writes *0 fichier* in the
    singular, English writes *0 files* in the plural. A single rule for both
    would trade one mistake for another.

## Adding an emulator profile

Drop a JSON file in `romule/profils/`, modelled on `eden.json`. Set
`"verifie": false` unless you have run it against real hardware — the interface
labels unverified profiles, and that label is the honest default.

## House style

Comments and docstrings are **in French**; everything user-facing is in
English. A comment says *why*, never *what*: if it restates the line below it,
delete it. The ones worth writing explain a constraint invisible in the code —
a rule fighting another rule, a measured value, a bug a naive rewrite would
bring back.
