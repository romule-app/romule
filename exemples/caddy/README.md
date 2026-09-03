# Romule behind Caddy

A complete reverse-proxy stack: Caddy terminates TLS, Romule speaks plain HTTP
on the internal network and is **not** published on the host.

```sh
docker compose up -d
docker compose logs romule      # prints the URL with your access token
```

Then open <http://localhost/>. For a real domain, replace `:80` in the
`Caddyfile` with your hostname and Caddy gets a Let's Encrypt certificate on
its own.

## The one setting that matters

```yaml
ROMULE_TRUSTED_PROXIES: 172.16.0.0/12
```

A proxy makes **every** request look like it comes from the proxy. Romule
grants full rights to local requests, so a naive setup would hand the internet
whatever the machine itself is allowed to do.

Romule therefore ignores `X-Forwarded-For` until you name the proxy yourself.
Without the declaration, a forwarded header grants nothing — and a request
carrying one is not treated as local either. **The default refuses.**

CIDR notation is what you want under Docker: the proxy's address is assigned
dynamically, so a fixed address would be wrong after the first
`docker compose down`. Plain addresses still work — `127.0.0.1,::1` for a proxy
installed directly on the host.

## Why a forged header still gets you nowhere

Caddy **appends** the peer address to the right of any existing
`X-Forwarded-For` rather than replacing it. Romule walks that chain **from the
right**, skipping addresses that are themselves declared proxies, and stops at
the first one that is not.

So a client that sends `X-Forwarded-For: 127.0.0.1` through this stack produces
`127.0.0.1, <their real address>` — and Romule reads *their real address*, not
the `127.0.0.1` they wrote. This is checked end to end in CI, against this exact
stack, because it is the kind of property a mock would prove about itself.

## What is deliberately absent

- **No `ports:` on the `romule` service.** It is reachable only through Caddy.
  Publishing its port as well would leave a door open next to the one you just
  locked.
- **No TLS inside Romule.** It speaks plain HTTP by design; a hand-written TLS
  stack would be a worse idea than delegating to Caddy.

## nginx and Traefik

Same principle, different syntax — see
[Installation → Behind a reverse proxy](https://romule-app.github.io/romule/installation/#behind-a-reverse-proxy).
Whichever you use, raise the body-size limit and the read timeout: one upload
can be several gigabytes and take minutes.
