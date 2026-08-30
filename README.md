# Romule

Self-hosted library manager for your own game backups.

> **Status: pre-release (0.1.0 in progress).** This repository has just been
> extracted from a private, single-user project. It is **not ready to install
> yet** — the security hardening, the emulator-profile refactor, the English
> UI default, the documentation site and the release pipeline are still being
> worked through. Please do not deploy it publicly until 0.1.0 is tagged.

Romule ships no games, no console keys and no links to either. It manages a
library you already own.

## Development

```sh
python3 lancer_tests.py            # unit + end-to-end server suites + audit
python3 lancer_tests.py --tout     # adds the Chrome/CDP browser suites
python3 -m switchlib.audit         # self-audit (fails the build on "grave")
python3 outils/verifier-fuite.py   # refuses personal data in the git index
```

The library lives **outside** this repository. Point the app at it explicitly:

```sh
ROMULE_ROOT=/path/to/your/library python3 switch.py
```

Source comments and docstrings are written in French, deliberately: they carry
the reasoning behind the code. User-facing text, documentation and issues are
in English.
