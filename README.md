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
python3 -m romule.audit         # self-audit (fails the build on "grave")
python3 outils/verifier-fuite.py   # refuses personal data in the git index
```

The library lives **outside** this repository. Point the app at it explicitly:

```sh
ROMULE_ROOT=/path/to/your/library python3 -m romule
```

Source comments and docstrings are written in French, deliberately: they carry
the reasoning behind the code. User-facing text, documentation and issues are
in English.

## Project documents

| Document | What it covers |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | What changed, release by release |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Zero-dependency rule, house style, how to run the suites |
| [SECURITY.md](SECURITY.md) | How to report a vulnerability, and what is in scope |
| [LICENSE](LICENSE) | GNU AGPL-3.0-or-later |

## Licence

Romule is free software under the
[GNU Affero General Public License v3.0 or later](LICENSE).

The AGPL was chosen deliberately: Romule is a **network service**, and the
AGPL is what keeps a hosted fork open. If you run a modified Romule and let
others reach it over a network, section 13 requires you to offer them your
source. The interface footer carries that offer — it links to the source and
shows the running version, and `/api/health` reports both as well. Keep it
working if you fork.
