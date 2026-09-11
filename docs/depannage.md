# Troubleshooting

## `docker compose up` works but the page is refused

Only when something already protects it. On a fresh installation the page
opens: until you answer the wizard's access step, the service answers
everybody — that is what makes the wizard reachable from your phone.

If it refuses, ask what is guarding it:

```sh
docker compose exec romule python3 -m romule access status
```

An account or an SSO: sign in. A token: paste it in the field the page shows
(`romule token show` prints it again). Locked out of all three:

```sh
docker compose exec romule python3 -m romule access open
docker compose restart
```

## I have lost the access token

Nothing generates one any more, but if you set one:

```sh
docker compose exec romule python3 -m romule token show
python3 -m romule token show            # without Docker
```

`token reset` replaces it — every browser that had remembered the old one is
asked for the new one on its next load.

## I forgot my password and there is no second account

```sh
docker compose exec romule python3 -m romule user passwd you@example.com
```

Or reopen the door and settle it from the interface:

```sh
docker compose exec romule python3 -m romule access open
docker compose restart
```

`open` switches the authentication off as well — the accounts are untouched,
and `access close` puts it back.

## The address printed at first start does not answer

If it starts with `172.` you read the container's own address on Docker's
network, which nothing routes. Romule no longer prints it, but an older version
did. From the machine hosting the container, `http://localhost:8787` works; for
every other machine, declare yours:

```yaml
environment:
  ROMULE_PUBLIC_HOST: "192.168.1.20"     # your machine, not the container
```

See [In a container](configuration.md#in-a-container).

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

The default provider works from Switch title IDs alone, so other platforms
need a key: **Settings → Covers and details**, then **Save and test**. If the
test fails, the key is wrong — the message says which service refused.

Covers have two sources, tried in that order. SteamGridDB is a community
*artwork* database and is thin on handheld console catalogues; IGDB is a game
database that publishes cover art too, and Romule falls back to it when the
first source returns no image. **Filling in the IGDB credentials therefore
fixes blank covers that a SteamGridDB key alone does not.**

Both sources must actually match the game: a candidate has to cover two thirds
of the distinctive words of the title. A file named `Some Game (Europe) (En,Fr)
[!].nds` is searched under `Some Game` — the region and dump tags are stripped
first. A cover belonging to another game would be worse than none.

## The same game appears twenty-five times

A CD game is not one file. `Rayman (Europe) (Track 01).bin` through
`(Track 25).bin` is **one** PlayStation title cut into tracks, and listing each
piece put twenty-five Raymans in the list.

Romule folds them back together: an index file — `.cue`, `.gdi`, `.ccd`,
`.toc` — is the game and the tracks that carry its name are its innards; with
no index, the tracks are grouped under the name they share and the set counts
once, weighing the whole disc.

The transfer is not fooled by the tidier list: sending the game sends every
piece, and the log says how many track files went along. A cue sheet whose
tracks stayed on the server is a game that does not start.

If a set still appears twice, the tracks are probably in **two different
folders** — Romule never merges across folders, because two folders are the one
reliable sign of two copies.

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

## Pairing succeeds, then a port is asked for again

This is the most frequent question, and a fair one: the port you typed *was*
right — it was the pairing one. The **connection** port is a different number,
which only the console shows, on a different screen.

Romule looks for it on its own right after the pairing; step 4 only appears
when that search found nothing.

In that case, check that
**wireless debugging is still on** — some devices turn it off when the console
sleeps — then copy the “IP address and Port” line from its screen.

## “Console connected”, but nothing in the header

It was a lie, and it lasted. `adb connect` prints “connected to
192.168.1.42:5555” and exits 0 even when the console then sits at `offline` or
`unauthorized` — two states Romule rightly refuses to drive. So the message
announced success, the header showed no console, and the settings offered again
the configuration you had just done. Three screens disagreeing, and the one
lying was the message.

Romule now **checks** the link instead of announcing it: a connection counts as
made only if adb lists the address as `device`. A link that stays `offline` is
retried once — adb sometimes holds a stale entry for that address — then refused
with its reason.

The two reasons you may see:

- **the console is asking for your permission.** Look at its screen and accept
  “Allow USB debugging”. Tick “Always allow”;
- **the console let the link drop.** The connection port changes every time
  wireless debugging restarts: read it again on the console's screen. If it is
  the right one, turn wireless debugging off and on again.

## “protocol fault (couldn't read status message): Success”

What adb says during pairing. The word “Success” at the end is a system error
code, not an outcome: it means nothing here.

Romule now starts the adb daemon before pairing and retries once — the most
frequent cause was `adb pair` starting the daemon itself and racing its own
startup. If the message comes back anyway:

1. the pairing code is good **once, and for a few minutes**. Close the window
   on the console and reopen “Pair device with pairing code”: you get a new
   code **and a new port**;
2. copy both, together. The pairing window's port changes every time it opens;
3. check that the console and Romule are on the same network. From a container
   in *bridge* mode they are, as long as the port is published — but a guest
   network, or Wi-Fi with client isolation, lets nothing through.

## Starting over to test the install from scratch

The service's state — configuration, accounts, cover art, token, "the assistant
has been seen" — lives in the named volume `romule-donnees`. **Your games are
not in it**: they are in the folder you mounted on `/library`, and nothing here
touches it.

```sh
docker compose down -v          # stops AND removes the data volume
docker compose up               # comes back up on a fresh install
```

The `-v` is the whole point: `docker compose down` on its own keeps the volume,
and you find the assistant already done, the access already chosen, the accounts
already there.

To see what is about to go before doing it:

```sh
docker volume ls | grep romule
```

If you mounted a host folder instead of the named volume, `-v` leaves it alone —
that is a `docker-compose.yml` choice, and the folder then has to be emptied by
hand.

## Pairing succeeded, but the console will not connect

Nearly always the same cause: the address entered to connect is the one from the
**pairing window**. Its port is disposable — it is used once and never again.

Close the code window. Behind it, the **Wireless debugging** screen shows its own
“IP address and Port” line, on a different port. That is the one step 4 of the
assistant is asking for.

If the address is right and connecting still fails, the console has most likely
left the network or changed address: the connection port changes every time
wireless debugging restarts, and step 4 has to be done again — not the pairing,
which stays.

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
- `_romule-lib.log` in the service data folder (`ROMULE_ROOT`, or the
  `/data` volume) holds the same, kept across
  restarts.

When opening an issue, include the version (interface footer, or
`python3 -m romule --version`), whether you run Docker or bare metal, and what
you expected.
