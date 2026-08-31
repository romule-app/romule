# Troubleshooting

## `docker compose up` works but the page is refused

Expected on first start. The container is reachable but has no account yet, so
Romule generates a token:

```sh
docker compose logs romule
```

Open the address it prints, token included. See
[the first-access token](securite.md#the-first-access-token).

## Romule refuses the folder I picked

It refuses locations that are clearly wrong — the disk root, your home folder,
a code repository, anything read-only — because it moves files and creates
folders there. Pick a folder that holds only your games.

The same rule applies to `ROMULE_ROOT` at startup, and there the service stops
rather than writing into the wrong place.

## The folder picker says "outside the allowed folders"

`ROMULE_BASES` is set and the path is outside it. In Docker this usually means
the folder is not mounted at all: add it to `volumes:`. Nothing the interface
can do reaches a path the container cannot see.

## The scan finds nothing

Check the path shown in the wizard is the one you expect. Romule reads a folder
tree, so games may sit in subfolders, but the root must be right. Files whose
extension it does not recognise are ignored — the wizard tells you how many
extensions it knows.

## Cover art stays blank

The default provider works from Switch title IDs. For other platforms you need
a SteamGridDB key: **Settings → Covers and details**, then **Save and test**.
If the test fails, the key is wrong — the message says which service refused.

## `.nsz` / `.xcz` files will not convert

They need the `nsz` tool **and** `prod.keys`:

```sh
pipx install nsz          # Debian/Ubuntu
brew install pipx && pipx install nsz   # macOS
```

Then point `ROMULE_KEYS` at your keys file, or mount it at `/keys/prod.keys` in
Docker. Romule supplies neither the tool's keys nor any way to obtain them.

## The console is not detected

1. Is `adb` installed? Romule says so on the main screen if not.
2. Is USB debugging (or wireless debugging) on, on the console?
3. Did you accept the authorisation prompt on the console's screen?
4. Under Docker with bridge networking, USB is not visible. Use Wi-Fi pairing,
   or see [Installation](installation.md#networking).

## Transfers over Wi-Fi are slow

Two to five times slower than USB, by nature. For a first bulk transfer, cable
is worth it.

## Behind a reverse proxy, everyone sees everyone's session

Set `ROMULE_TRUSTED_PROXIES` — see [the reverse proxy
trap](securite.md#the-reverse-proxy-trap). Without it every request appears to
come from the proxy.

## The interface is in French

**Settings → Interface → Language**, or set `ui_lang` to `en`. English is the
default; a French locale ships alongside it.

## Something else

- `python3 -m romule.audit` — reports on the running configuration.
- The **Log** panel, right-hand side, holds what Romule did and why it failed.
- `_romule-lib.log` in your library folder holds the same, kept across
  restarts.

When opening an issue, include the version (interface footer, or
`python3 -m romule --version`), whether you run Docker or bare metal, and what
you expected.
