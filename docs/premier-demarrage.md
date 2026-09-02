# First run

The wizard is six steps, one at a time. Each says whether it is **required**,
**optional**, or **for information**. You can skip it entirely and come back
later from the settings.

## 1. Welcome — for information

What Romule does, and what it does not: it downloads no games and supplies no
keys.

## 2. Your library — required

The folder holding all your games, every platform together.

Press **Scan the folder**. Romule reports what it found, per platform:

> **4 games across 2 platforms** — 2 Nintendo Switch · 2 Mega Drive

This is the only proof the folder you pointed at is the right one. A path
accepted with nothing in it is a wrong path you discover an hour later, so the
step will not let you continue until the scan finds something.

To use a different folder, click **Choose another folder…** and browse to it.
Nothing to restart, and no file to edit — the same picker is in
**Settings → Your library → Location** afterwards.

If the button is missing, the folder was pinned by your deployment with
`ROMULE_LIBRARY`; change it in your compose file.

!!! note "Your folder stays yours"
    Romule writes only `_import/` and `_corbeille/` next to your games. Its
    settings, your accounts and the cover art live in the service data folder,
    and do not follow the games when you move them.

## 3. Your access — required when reachable

The first account created becomes the **administrator**: it alone changes
settings and manages other accounts.

This step is marked required when the service listens on the network, and
optional when it only listens on `127.0.0.1`. The very first account can only
be created from the machine hosting the library — otherwise "the first account
governs" would mean "the first device on the network governs".

## 4. Covers and details — optional

Two free services fill in the artwork and the summaries. Without them the
library works, but it only shows file names.

| Service | What it gives | Where to get a key |
|---|---|---|
| SteamGridDB | Cover art | [steamgriddb.com/profile/preferences/api](https://www.steamgriddb.com/profile/preferences/api) |
| IGDB | Summaries, year, publisher — **and cover art when SteamGridDB has none** | [dev.twitch.tv/console/apps](https://dev.twitch.tv/console/apps) |

Fill in both. SteamGridDB is a community *artwork* database, rich on what gets
played with a keyboard and thin on handheld console catalogues; IGDB covers
what it misses. With only one of the two, some games keep an empty sleeve.

**Save and test** checks the credentials on the spot. Saving without checking
means finding out in a month that a key was pasted wrong.

## 5. Your console — optional

Romule looks for a console over adb, retrieves the games folder, and can list
what is already on it. Everything here is doable later from
**Settings → Your console** — see [Your console](console.md).

## 6. You're set — for information

What remains, and where it lives:

- **Compressed games** (`.nsz`, `.xcz`) need the `nsz` tool and a `prod.keys`
  file, both supplied in the settings. They are not required for Romule to
  work — only to convert those two formats.
- **Emulator** — Romule targets Eden by default; pick another profile in
  Settings → Your console.
- **Remote access** — Settings → Access.

## Why prod.keys is not in the wizard

It is only needed to convert `.nsz` and `.xcz` files. Everything else — taking
stock, cover art, transfers, updates and DLC — works without it. Asking for it
up front would suggest Romule cannot run without it, which is not true.
