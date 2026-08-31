# Security policy

## Supported versions

Romule is at `0.x`. Only the latest release receives security fixes.

| Version | Supported |
|---------|-----------|
| 0.1.x   | yes       |
| < 0.1   | no        |

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private reporting instead:
[Report a vulnerability](https://github.com/romule-app/romule/security/advisories/new).
It is private to the maintainers until an advisory is published.

What helps, in order of usefulness:

1. What an attacker gains — read a file, run a command, bypass authentication.
2. The smallest sequence of requests that shows it.
3. The configuration it needs (`auth_mode`, `lan_access`, reverse proxy or not,
   Docker or bare metal) — several settings change the exposed surface a lot.
4. The version, from the interface footer or `python3 -m romule --version`.

### What to expect

| Stage | Target |
|-------|--------|
| Acknowledgement | 7 days |
| Initial assessment | 14 days |
| Fix or documented mitigation | 90 days |

This is a spare-time project by one maintainer, not a company with an on-call
rotation. Those targets are honest intentions, not a contractual SLA. If a
report gets no acknowledgement after 14 days, a public issue saying only *"I
sent a security report on <date>, no reply"* — with no details — is a
reasonable nudge.

Coordinated disclosure is welcome. Credit is given in the advisory and the
changelog unless you prefer otherwise.

## What counts as a vulnerability

Romule is designed to be run **on a private network**, listening on
`127.0.0.1` by default, and to be exposed only behind a reverse proxy that
terminates TLS. Reports are assessed against that model.

**In scope**

- Authentication or authorisation bypass (including privilege escalation
  between accounts, and the proxy-trust path).
- Path traversal or arbitrary write outside the library root.
- Remote code execution, command injection, SSRF via configuration.
- Session handling: forgery, fixation, replay of a TOTP window.
- Anything letting an unauthenticated network client read the library, the
  configuration, or the account file.

**Out of scope** — these are known, documented design decisions, not findings:

- **No built-in TLS.** Romule speaks plain HTTP and expects a reverse proxy in
  front of it. Documented in the README and stated at first run.
- **`script-src 'unsafe-inline'` in the Content-Security-Policy.** 124 inline
  event handlers depend on it. Removing them is planned; until then, the CSP
  cannot forbid inline scripts without making every button inert.
- **Network access without a password**, when the operator has explicitly
  chosen it. It is a supported mode, off by default, and the built-in audit
  reports it at every startup.
- Anything requiring an attacker who already has a shell on the host, or write
  access to the library folder.
- Missing hardening headers with no demonstrated impact.
- Reports from automated scanners with no working proof of concept.

## Hardening checklist for operators

- Put a reverse proxy with TLS in front of anything reachable from the
  internet, and name it in `ROMULE_TRUSTED_PROXIES` — otherwise its forwarded
  headers are ignored, by design.
- Create an account. The first one is the administrator.
- Keep `prod.keys` mounted read-only, and outside the library folder.
- Run `python3 -m romule.audit` after any configuration change.
