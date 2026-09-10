# Your console

Romule talks to an Android handheld through **adb**. It was built against an
AYN Thor running the Eden emulator, but the device and the emulator are
[profiles](profils.md), not hard-coded paths.

## Pairing over Wi-Fi

The first-start assistant asks first **how the console is connected** — with
or without a cable — and shows only the matching path. The settings hold the
same step-by-step assistant. In short:

1. **On the console** — Settings → System → Developer options → **Wireless
   debugging**, switch it on.
   *No developer options?* Settings → About phone, tap **Build number** seven
   times.
2. **On the console** — in the Wireless debugging screen, tap **Pair device
   with pairing code**. Leave the window open: the code expires when it closes.
   It shows a six-digit code and an address like `192.168.1.42:37105`.
3. **In Romule** — enter that address and that code, then confirm the
   pairing. Romule then connects on its own, starting with **that very
   address**: on a good many devices the pairing port and the connection port
   are the same number. Failing that, it tries a link left by a previous
   session, what the consoles announce over mDNS, then port 5555.
4. **On the console** *(only if none of them worked)* — close the code window.
   The Wireless debugging screen
   behind it shows **its own “IP address and Port” line**, and it is not the
   same one: the pairing port is used only once. Copy that one into Romule,
   then **Connect the console**.

Once connected, the console is recognised on its own from then on.

Once connected, the panel asks nothing more: it shows what the console
answered — its name, its address, its Android version, its battery level, how
long the link has held. None of that can appear unless the console replied,
which makes it worth more than a plain “connected”.

!!! note "Under Docker, step 4 is the rule"
    The console announces its connection port over **mDNS**, and multicast does
    not cross the Docker bridge. From a container Romule therefore cannot guess
    it: it has to be read off the console's screen. On a direct install
    discovery works, and step 4 almost never appears.

!!! info "Why two ports?"
    Android's wireless debugging exposes **two services**, each on its own
    random port:

    - `_adb-tls-pairing` exists only while the code window is on screen. It
      exchanges a TLS certificate, checked against the six-digit code, and then
      closes;
    - `_adb-tls-connect` is the adb daemon itself. It stays open for as long as
      wireless debugging does, and accepts only the certificates obtained by
      pairing.

    Both ports come from the same ephemeral pool and are handed out moments
    apart, so they are often neighbours — which is what Romule uses to find the
    second one without asking for it.

!!! warning "Two addresses, two ports"
    This is where it goes wrong. The code window gives a pairing port, good for
    one use; the Wireless debugging screen gives another one, for the
    connection. Entering the first at step 4 fails without explaining itself.

!!! note "Wi-Fi is slower"
    Two to five times slower than USB for large transfers. Fine for a few
    games, noticeable for a full library.

### When folder names say nothing

Recognising `gba` or `PS1` works on a console that names them that way, and
finds nothing at all on one filing games under `Nintendo - Game Boy Advance` or
`psx-eur`. So Romule looks at the **contents** too: a folder holding game files
IS a platform folder, whatever it is called.

Finding the root does not require knowing WHICH platform — just as well, since
`.cue` and `.iso` are claimed by every disc console at once.

And when none of that works, both the wizard and the settings let you **browse
the console** and point at the folder by hand.

## USB

Plug the console in with debugging enabled and press **Detect**. Under Docker,
USB requires `devices: - /dev/bus/usb:/dev/bus/usb` and Linux — see
[Installation](installation.md#networking).

## The games folder

Romule detects it, and shows it once connected:

```
/storage/emulated/0/Switch
```

Change it in **Settings → Your console** if your emulator keeps games
elsewhere.

The **ROMs folder** — the parent of every other platform, each in its own
subfolder — is found the same way, by **recognising folder names**: `gba`,
`snes`, but also `PS1` for the PlayStation or `Sega` for the Mega Drive. The
folder holding the most of them wins, and at least two are needed: a lone `Wii`
folder proves nothing.

That is what saves typing the path. Deriving it from the Switch folder — its
parent — was right only on consoles that keep everything side by side;
elsewhere every platform counted zero, and the library's selector stopped
showing their numbers.

## A platform Romule does not know

Twenty-three platforms are recognised out of the box, and the list is not a
limit. **Settings → Your console → Add a platform…** takes three things:

| Field | Example | What it is for |
|---|---|---|
| Display name | `Neo Geo` | What you will see in the platform selector |
| Folder on the console | `NeoGeo` | A subfolder of the ROMs folder above |
| Extensions | `zip, neo` | What counts as a game for that platform |

That is enough for the platform to be scanned, filtered, counted and pushed
like any other. It is also the answer when a console *is* known but you keep it
in a folder Romule would not guess — declare it under the name you actually
use.

The added platforms are stored as `systemes_perso` in the settings file, and
travel with your backups.

!!! note "What it does not do"
    Declaring a platform does not teach Romule to read the *inside* of its
    files. Switch is the only one it opens: title IDs, base/update/DLC
    relationships and missing updates come from parsing the container. Every
    other platform — built-in or added — is identified by folder and extension.

## Layout on the console

Switch files are sorted into `GAMES`, `UPDATE` and `DLC`. The type comes from
the file's *contents* when Romule knows it, not from its name — a name lies
often enough: a truncated title ID, a missing one, or a file announcing a base
game that is really an update.

## What is already on it

**List the games on the console** reports what it holds and how many of those
are missing from your library, so you do not re-import what is already there.

## Adb is not installed

Romule says so and gives the command for your platform. Nothing else stops
working: the library, the cover art and the inventory do not need a console.
