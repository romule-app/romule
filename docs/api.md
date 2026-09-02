# HTTP API

Romule exposes a small, stable API so you can query your library from a
dashboard, a script, or a scheduled job — without a browser and without a
session.

[Download the OpenAPI 3.1 specification](openapi.json){ .md-button }

## The promise, precisely

Within a major version:

- no route disappears;
- no existing field changes name or type;
- new fields **may** appear — so ignore the ones you do not know.

That is the whole promise. Romule serves about a hundred other `/api/...`
routes; they exist for its own interface, they change when a screen changes,
and they are **not** covered. If you build on them, expect them to move.

!!! info "Why a separate surface"
    Freezing the interface's own routes would mean freezing the interface. The
    public API is deliberately smaller than what the app uses, for the same
    reason Sonarr and Radarr publish a curated surface rather than their
    internals.

## Getting a key

Every request needs an API key. Keys are named, revocable one at a time, and
show you when they were last used.

**From the interface** — Settings → Access → API keys. Give it a name that says
what it is for (`dashboard`, `nightly-backup`); that name is what will tell you
which one to revoke later.

**From the command line** — useful in a container, where there may be no
browser at all:

```sh
romule apikey create dashboard
# in Docker:
docker compose exec romule python3 -m romule apikey create dashboard
```

```
Cle creee : dashboard

  rml_Ac0ffee1S3cr3t...

Note-la maintenant : elle n'est conservee que sous forme
d'empreinte et ne pourra pas etre reaffichee.
```

!!! note "The command line speaks French"
    That output is verbatim, not a translation slip. Like the audit report and
    the login pages, the CLI is composed by the server and never passes through
    the interface's translation catalogue — see
    [Beta features](beta.md#the-audit-report-the-login-pages-and-the-cli-are-french-only).
    The commands, their arguments and everything on this page are English; only
    what the command prints back is not.

!!! warning "Shown once, and only once"
    Romule stores a SHA-256 hash of the key, never the key itself. That is what
    makes a leak of its state file harmless — and it is also why the key can
    never be displayed again. Write it down when you create it.

`romule apikey list` shows the keys, their prefix, and their last use.
`romule apikey revoke <id>` retires one. A revoked key stays listed, so you can
still answer "did that key get used after I retired it?".

## Authenticating

Send the key in a header:

```sh
curl -H "X-Api-Key: rml_..." http://localhost:8787/api/v1/stats
```

A query parameter also works, for clients that can only be given a URL — a
dashboard tile, a `wget` in a cron job:

```sh
curl "http://localhost:8787/api/v1/stats?apikey=rml_..."
```

!!! warning "The header is better"
    A URL ends up in proxy logs, in browser history, and in shell history. Use
    the parameter only when a header is genuinely impossible.

### What a key can reach

A key reaches `/api/v1/` **and nothing else**. It cannot open the interface,
read the configuration, or touch accounts.

This is stricter than it may look: presenting a key does not *grant* rights, it
*selects a regime*. A request from `127.0.0.1` normally gets full local access —
but the moment it carries `X-Api-Key`, the key decides, and the key is scoped.
A key can therefore never widen an access; at most it narrows one.

### CSRF

Romule rejects state-changing requests that announce a foreign origin. A
command-line client sends no `Origin` header at all and is accepted — the key
is what protects those routes, and a browser never attaches it on its own the
way it attaches a cookie.

## The routes

Base URL is your Romule instance, `http://localhost:8787` below.

### Read the library

| Route | What it gives |
|---|---|
| `GET /api/v1/health` | liveness — also the container probe |
| `GET /api/v1/system` | version, licence, source, uptime |
| `GET /api/v1/stats` | counts and total size |
| `GET /api/v1/library` | the inventory, paginated |
| `GET /api/v1/library/{key}` | one game |
| `GET /api/v1/search?q=` | search by name or title ID |
| `GET /api/v1/platforms` | configured platforms |
| `GET /api/v1/device` | state of the connected handheld |
| `GET /api/v1/job` | the running task, if any |
| `GET /api/v1/trash` | what can still be restored |

```sh
curl -H "X-Api-Key: $KEY" http://localhost:8787/api/v1/stats
```

```json
{ "total": 412, "base": 180, "update": 150, "dlc": 82,
  "bytes": 174929203200, "to_convert": 3 }
```

A game's **key** is its path relative to the library — the same identifier the
interface uses. It contains spaces and brackets, so percent-encode it:

```sh
curl -H "X-Api-Key: $KEY" \
  "http://localhost:8787/api/v1/library/GAMES%2FSome%20Game%20%5B0100ABC%5D.nsp"
```

Fields never include an absolute path. It would tell a client nothing and would
reveal the server's directory layout — often including someone's account name.

### Start a task

| Route | |
|---|---|
| `POST /api/v1/scan` | rescan the library |
| `POST /api/v1/convert` | convert the remaining `.nsz`/`.xcz` |
| `POST /api/v1/push` | send pending games to the handheld |

```sh
curl -X POST -H "X-Api-Key: $KEY" http://localhost:8787/api/v1/scan
```

Romule runs **one task at a time** — there is no queue, and the API says so
rather than pretending otherwise. A start returns `202`; if something is
already running you get `409`, and retrying later is the right response.

Watch progress with `GET /api/v1/job`:

```json
{ "running": true, "label": "convert", "done": 2, "total": 5,
  "detail": "Some Game.nsz" }
```

## Pagination

`GET /api/v1/library` and `GET /api/v1/search` take `page` (from 1) and `limit`
(default 50, maximum 200), and answer with the page plus its context:

```json
{ "page": 2, "limit": 50, "total": 412, "pages": 9, "items": [ … ] }
```

Two behaviours, deliberately different:

- an **unreadable** value (`page=zero`) falls back to the default — the client
  got the type wrong, there is nothing to salvage;
- an **out-of-range** value (`limit=100000`, `limit=-4`) is clamped into the
  bounds — the intent is clear, and refusing it would force every client to
  know the ceiling before asking.

A page past the end is an empty `items`, not an error.

## Errors

| Code | |
|---|---|
| `400` | a required parameter is missing |
| `401` / `403` | no key, unknown key, revoked key, or out of scope |
| `404` | unknown route, or unknown game key |
| `409` | a task is already running |
| `429` | rate limited — `Retry-After` says how long |
| `500` | something failed server-side |

Error bodies carry a stable `error` slug and a human `message`:

```json
{ "error": "busy", "message": "Another task is already running." }
```

The `message` never contains a server path: an internal failure is reported as
`internal_error` with a generic sentence, and the detail goes to Romule's own
log.

## A worked example

Warn me when more than three files still need converting:

```sh
#!/bin/sh
KEY=rml_...
N=$(curl -fsS -H "X-Api-Key: $KEY" http://localhost:8787/api/v1/stats \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["to_convert"])')
[ "$N" -gt 3 ] && echo "$N files to convert" && \
  curl -fsS -X POST -H "X-Api-Key: $KEY" http://localhost:8787/api/v1/convert
```
