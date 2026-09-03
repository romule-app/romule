# Security and exposure

See also **[Roles and access](roles.md)** for who may do what, in each of the
three authentication modes.

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
ROMULE_TRUSTED_PROXIES=127.0.0.1,::1        # proxy on the host
ROMULE_TRUSTED_PROXIES=172.16.0.0/12        # proxy in a container
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

It is stored in the service data folder — as `jeton_auto` in
`_romule-config.json` — survives restarts, and is never sent to
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

## Browsing the host filesystem

The library picker lists folders on the machine running Romule. That is a
disclosure primitive, and it is treated as one:

- it is **administrator-only**, like every destructive route;
- it returns **folders only** — no filenames ever leave the server. The one
  extra number is a count of recognised games, because that is what lets you
  tell your library from a folder that merely looks like it;
- selecting a folder is bound by the same rule as browsing it, so typing a
  path is not a way around `ROMULE_BASES`.

`ROMULE_BASES` is unset by default. That is deliberate: in a container the
boundary is the `volumes:` list, enforced by the kernel rather than by
application code, and on a bare install it is the Unix account the service runs
as. An application-level allowlist on top would mostly give the impression of
one. Set `ROMULE_BASES` when you run natively under a broad account.

## Limits enforced

| Limit | Default | Why |
|---|---|---|
| Upload size | 64 GiB | A saturated disk is a denial of service |
| Free space kept | 2 GiB | Refuse the write rather than fill the disk |
| Socket timeout | 300 s | Slow connections must not hold threads |
| Connections | 64 | Bounded concurrency |
| Requests | 600/min per client | Rate limiting on all of `/api/*` |
| Path containment | — | Custom platform folders, extensions and title IDs are validated |
| Library location | — | Refused if read-only, or if it is your home folder, a disk root or a code repository |

## Known weaknesses

**`script-src` is `'self'` — no inline scripts.** This was the project's
largest known weakness until 0.2.0, and removing it took the whole of phase 4:
153 inline event handlers, each one a reason the browser had to accept scripts
written into the page.

The order mattered. A button that stops responding is invisible from the
server — no request fails, no line is logged — so the safety net was written
*first*: a test that walks every screen, finds every clickable element, and
fails if one has no handler. Writing it honestly took three corrections, each
worth stating because each was a wrong assumption about the DOM:

- a handler assigned as a **property** (`el.onclick = fn`) appears in no
  attribute, and `querySelectorAll('[onclick]')` does not see it;
- a `<select>` or a checkbox responds **natively** — the gesture has a visible
  effect and the value is read at save time. Not inert, just codeless;
- `document` is not an `Element`, so walking `parentElement` never reaches it —
  and that is where the delegation listens.

The handlers now carry their action as **data**: `data-act` names the action,
`data-arg` its argument. `ACTES` is an allow-list, not a dynamic lookup —
`app[el.dataset.act]()` would have been sixty lines shorter and would have let
any attribute reach any method, including the ones that delete.

The security gain is not a stronger escape, it is **one parser fewer**. A value
inside `onclick="app.do('HERE')"` crossed **two**: the HTML parser decoded
entities first, then the JavaScript engine compiled what was left — so
`esc()`'s `&#39;` became an apostrophe *before* the script was read, closing the
string and turning the rest of the value into code. A filename was enough to
build one, and a card's key is the file's path. That was the stored XSS fixed in
0.1.0, and `jsq()` was the correct patch for it.

Inside `data-arg="HERE"` there is one parser and nothing is ever compiled.
`esc()` is sufficient — and a test asserts it is present at all 28 sites, since
a double quote in a filename would otherwise leave the attribute.

`jsq()` stays defined, with its round-trip tests, as the guard for the day
someone reintroduces an inline handler. Two stronger invariants replace its old
role: no `on*=` attribute is generated anywhere, in either file, and the browser
test listens for `securitypolicyviolation` — a CSP violation does not break the
page, it writes one console line and continues, which is exactly the kind of
silent failure this project keeps finding. That check is itself proven: it
injects an inline script and asserts the browser refuses to run it.

**`style-src` still allows `'unsafe-inline'`.** Inline `style=` attributes
remain common in the generated markup. A style is not executed, so this is a
weakness of a different nature from the one above — kept, and stated.

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
