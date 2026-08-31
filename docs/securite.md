# Security and exposure

## Romule has no TLS

It speaks plain HTTP. Anything reachable from the internet needs a reverse
proxy terminating HTTPS in front of it. This is a deliberate limitation for
0.1.0, not an oversight: a hand-rolled TLS stack is a worse idea than
delegating to nginx, Caddy or Traefik.

## The reverse proxy trap

A proxy on the same host makes **every** request look like it comes from
`127.0.0.1`. Romule grants local requests full access, so a naive
implementation would let anyone on the internet through the moment you put a
proxy in front of it.

Romule therefore ignores `X-Forwarded-For` and `X-Real-IP` **unless you name
the proxy yourself**:

```sh
ROMULE_TRUSTED_PROXIES=127.0.0.1,::1
```

Without this, a forwarded header grants nothing — and a request arriving with
one is not treated as local either. With it, the client address is taken from
the header, but only when the request genuinely comes from a listed proxy.

!!! danger "Do not skip this"
    Behind a proxy and without `ROMULE_TRUSTED_PROXIES`, every user shares one
    apparent address. Rate limiting and access decisions both degrade.

## How access is decided

In order:

1. **Authentication active?** A valid session is required — including from the
   machine itself. Enabling SSO and staying reachable without a password from
   the host would empty the measure of its meaning on a shared computer.
2. **Request from this machine?** Allowed.
3. **A token is set?** It must match, compared in constant time.
4. **Otherwise** — allowed only if `lan_access` is on.

## The first-access token

A service that is reachable but has no account, no token and no LAN access
would refuse every request, including the one needed to reach the settings and
fix it. Rather than open the door, Romule generates a token on first start and
prints it with the full URL:

```
Acces : ce service est joignable par le reseau et n'a pas encore de compte.
        http://192.0.2.20:8787/?token=Kzrmfve...
```

It is stored in your library folder, survives restarts, and is never sent to
the browser with the rest of the configuration. Nothing is generated when
Romule listens on `127.0.0.1` only.

## Accounts and roles

- The **first account created is the administrator**. Only an administrator
  changes settings, manages accounts, or runs destructive actions.
- That first account can only be created **from the machine hosting the
  library** — otherwise "the first account governs" would mean "the first
  device on the network governs".
- There is never zero administrator: the last one cannot be deleted.
- Passwords use scrypt (N=2¹⁷). TOTP two-factor is available per account.

## Limits enforced

| Limit | Default | Why |
|---|---|---|
| Upload size | 64 GiB | A saturated disk is a denial of service |
| Free space kept | 2 GiB | Refuse the write rather than fill the disk |
| Socket timeout | 300 s | Slow connections must not hold threads |
| Connections | 64 | Bounded concurrency |
| Requests | 600/min per client | Rate limiting on all of `/api/*` |
| Path containment | — | Custom platform folders, extensions and title IDs are validated |

## Known weaknesses

**`script-src` allows `'unsafe-inline'`.** 124 inline event handlers depend on
it. Removing them means converting every one to delegated events — a project in
itself. Until then the CSP cannot forbid inline scripts without making every
button inert. Documented rather than quietly dropped.

**No TLS**, as above.

**[Beta features](beta.md)** carry their own risks, listed there. The most
security-relevant is OpenID Connect SSO.

## Check your own installation

```sh
python3 -m romule.audit
```

It reports on the configuration actually running: exposure, authentication,
headers, file permissions, dependencies, Python version. The CI fails on
anything it rates *grave*. Run it after any change.

## Reporting a vulnerability

Private reporting, not the issue tracker. See
[SECURITY.md](https://github.com/romule-app/romule/blob/main/SECURITY.md).
