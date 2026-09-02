# Beta features

These work, and they are used. They are labelled beta because each carries a
specific risk worth knowing before you rely on it. The label appears in the
interface, next to the setting.

## OpenID Connect SSO

**Why beta.** Romule verifies RS256 identity tokens with an implementation
written for this project, with no third-party library. A JWT verifier is
exactly the kind of code where a subtle mistake is a security hole rather than
a crash.

Twenty tests forge tokens against it, one per known attack: `alg: none`,
RS256/HS256 confusion (the public key used as an HMAC secret), a foreign
signing key, an unknown `kid`, a tampered signature, a swapped payload keeping
the original signature, a wrong issuer, a wrong audience — alone or in a list —
an expired token, a token dated from the future, a mismatched nonce, and
malformed input of every shape. All are refused, and a control test checks that
a *valid* token still passes: a suite that rejects everything proves nothing.

**It is still labelled beta**, because tests prove the cases you thought of.
This code is young, it has had no outside scrutiny, and hand-written
cryptographic verification earns caution rather than confidence.

**The proven path** is internal accounts: email, password hashed with scrypt,
optional TOTP two-factor.

## Emulator configuration piloting

**Why beta.** Romule reads and writes the configuration files of *another
program*. That format belongs to the emulator, and it can change without
notice. A backup is taken before writing, but the feature is one upstream
release away from needing a fix.

Only profiles that declare a pilotable config expose this panel.

## EmuReady community settings

**Why beta.** The compatibility ratings and recommended settings come from
[emuready.com](https://www.emuready.com), a third-party community database.
Romule shows what it reports; it cannot vouch for it. Applying recommended
settings replaces your current configuration for those games.

## Transfer resume

**Why beta.** An interrupted transfer can be picked up from its saved state
rather than restarted. Resuming restarts from the last *confirmed* file. The
case is genuinely hard to test end to end — it needs an interruption at the
right moment, on real hardware.

When in doubt, discarding and sending again is safer.

## Wikipedia summaries

**Why beta.** For platforms IGDB does not know a title under, Romule falls back
to a Wikipedia lookup by name. Name matching is approximate: a wrong summary on
an obscure title is a normal outcome, not a bug.

## The audit report, the login pages and the CLI are French-only

**Not beta — a stated limitation.** Romule's interface translates completely:
every string lives in a catalogue, a CI check fails if one escapes it, and a
browser test walks seventeen screens looking for leftovers.

Three things fall outside that mechanism, because they are not built in the
browser at all. The **audit report** is composed by the server and returned as
finished sentences; the **login and access-denied pages** are served before any
JavaScript runs, which is the whole point of them; the **command line**
(`romule apikey`, `romule serve`) never loads the interface. Translating them
means translating `romule/audit.py`, `romule/cli.py` and the page templates in
`romule/server.py` — server-side i18n, which Romule does not have.

They are in French, the project's source language. This is set aside knowingly
rather than left as a red test: the browser test excludes the audit panel with
its reason written next to the exclusion.

---

## What is *not* beta

Taking stock of the library, cover art, transfers to the console, updates and
DLC relationships, internal accounts, TOTP, the audit, and the backup system.
These are the parts the test suites cover end to end.
