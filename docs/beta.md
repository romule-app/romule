# Beta features

These work, and they are used. They are labelled beta because each carries a
specific risk worth knowing before you rely on it. The label appears in the
interface, next to the setting.

## OpenID Connect SSO

**Why beta.** Romule verifies RS256 identity tokens with an implementation
written for this project, with no third-party library. A JWT verifier is
exactly the kind of code where a subtle mistake is a security hole rather than
a crash — and the current test suite only covers the **happy path**: a valid
token from a working provider is accepted, and the login flow completes.

The negative cases that matter most are **not covered yet**: a token signed
with `alg: none`, a wrong audience or issuer, an expired token, a tampered
signature. Each is a way in if the verifier gets it wrong, and none of them is
proven closed by a test today. That is the single strongest reason this feature
carries a beta label.

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

---

## What is *not* beta

Taking stock of the library, cover art, transfers to the console, updates and
DLC relationships, internal accounts, TOTP, the audit, and the backup system.
These are the parts the test suites cover end to end.
