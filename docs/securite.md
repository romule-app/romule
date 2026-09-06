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

## The first access

An installation nobody has claimed **answers everybody**. That is deliberate,
and it is what every comparable tool does: Jellyfin, Home Assistant and the
*arr stack all open on their setup screen.

The alternative was tried and does not work. Romule used to generate a token,
print it in the logs, and refuse everything else. It had to be copied out of a
terminal onto every device — a phone, a tablet, the laptop — and the first
account still could not be created, because that was refused unless the request
came from `127.0.0.1`. Under Docker that is nobody: a request through the
published port arrives from the bridge. The main installation path ended in a
wall no token opened.

So the wizard's **access step** is what claims the installation, and it cannot
be skipped:

- **an account** — the first one becomes the administrator, internal
  authentication is switched on by the same gesture, and that browser is signed
  in on the spot;
- **no password** — a legitimate choice on a trusted network, and the one most
  self-hosted tools make.

Until one of the two is answered, the terminal says so at every start, in
capitals, and the audit reports it.

### The window this accepts

Between `docker compose up` and your answer, anyone who can reach the address
can claim the installation. It is the same trust-on-first-use window every tool
in this family lives with. Two things keep it short: the wizard is the first
thing shown, and it cannot be dismissed.

### "No password" means everybody

The choice is not restricted to private addresses. Behind a reverse proxy or a
domain name, an open installation is open to whoever finds the address. Romule
says this beside the button rather than deciding for you — but it is your call
and your exposure.

### From the terminal

The day the interface is the thing that is broken — a password forgotten with
no second account, an SSO whose provider is down, a `close` regretted from the
wrong network — access is settled where the data is:

```sh
romule access status    # what is protecting this installation
romule access open      # no password (switches authentication OFF)
romule access close     # require a login again
romule user create you@example.com
```

`open` turns the authentication off as well as opening the network. It has to:
the server consults the session before the setting, so `lan_access` alone would
have reopened nothing and answered "opened" all the same. `close` puts it back
— the accounts were never touched.

## A token, if you want one

Nothing generates one any more, but `ROMULE_TOKEN` still works and
`romule token reset` sets one deliberately. When a token protects the
installation, the refusal page carries a field to paste it into and a cookie
remembers it for that browser, for a year.

```sh
romule token show     # print it again
romule token reset    # replace it
```

The stylesheet, and only the stylesheet, is served to a client that has not got
in yet: the refusal page links it, and without it the page arrived unstyled and
read as a broken server rather than as a door. `app.js`, the interface and
every route stay behind the check.

## Accounts and roles

- The **first account created is the administrator**. Only an administrator
  changes settings, manages accounts, or runs destructive actions.
- That first account can only be created **from the machine hosting the
  library** — otherwise "the first account governs" would mean "the first
  device on the network governs".
- There is never zero administrator: the last one cannot be deleted.
- Passwords use scrypt (N=2¹⁷). TOTP two-factor is available per account,
  and the setup screen shows a **QR code** to scan — drawn by `romule/qr.py`,
  which is a QR encoder written against the standard library because Romule
  has no runtime dependency and would not gain one for a single image. The key
  is still shown, for anyone who cannot scan.

  A QR code that is subtly wrong looks fine and simply does not scan, so
  `test_qr.py` reads the matrix back: it recovers the mask from the format
  information, undoes it, walks the same zigzag, de-interleaves the blocks and
  returns the payload — for every version, at the size that forces it. It also
  checks the Reed-Solomon syndromes, an independent computation from the
  division that produced them, and the error-correction bytes match the
  published reference vector for `HELLO WORLD`.

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
