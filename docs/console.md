# Your console

Romule talks to an Android handheld through **adb**. It was built against an
AYN Thor running the Eden emulator, but the device and the emulator are
[profiles](profils.md), not hard-coded paths.

## Pairing over Wi-Fi

The settings hold a step-by-step assistant. In short:

1. **On the console** — Settings → System → Developer options → **Wireless
   debugging**, switch it on.
   *No developer options?* Settings → About phone, tap **Build number** seven
   times.
2. **On the console** — in the Wireless debugging screen, tap **Pair device
   with pairing code**. Leave the window open: the code expires when it closes.
   It shows a six-digit code and an address like `192.168.1.42:37105`.
3. **In Romule** — enter both. Once paired, the console is recognised on its
   own from then on.

!!! note "Wi-Fi is slower"
    Two to five times slower than USB for large transfers. Fine for a few
    games, noticeable for a full library.

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
elsewhere. The **ROMs folder** setting is the parent of every other platform,
each in its own subfolder (`GBA`, `SNES`, `PS2`…). Left empty, it is derived
from the Switch folder.

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
