# Emulator profiles

The emulator decides where Romule drops games and where it reads saves. It is
described by a JSON file in `romule/profils/`, not by code.

| Profile | Verified on real hardware | Notes |
|---|---|---|
| **Eden** | **yes** | The reference profile. Romule was built against it. |
| Yuzu | no | Eden descends from it: same layout, same config format. |
| Sudachi | no | Yuzu fork. |
| Citron | no | Yuzu fork. |
| Ryujinx | no | JSON configuration, and a different layout. |
| Other emulator | no | Games folder only, nothing else. |

Unverified profiles are labelled in the interface. That label is the honest
default, not a disclaimer: only Eden has been run against a real device.

Pick yours in **Settings → Your console**.

## What a profile holds

```json
{
  "cle": "eden",
  "nom": "Eden",
  "paquets": ["dev.eden.eden_emulator", "dev.eden_emu.eden"],
  "donnees": "/storage/emulated/0/Android/data/{paquet}/files",
  "config": { "format": "ini-qt", "fichier": "config/qt-config.ini" },
  "sauvegardes": "nand/user/save",
  "verifie": true
}
```

`paquets` lists candidate Android package names, because they change between
emulator versions. Romule asks the console which one is actually installed
rather than guessing, and remembers the answer.

`config` is `null` for profiles whose settings Romule cannot pilot. When it is
set, the emulator settings panel appears — and is labelled **beta**, because
Romule writes into another program's files and that format can change without
notice.

## Adding a profile

Copy `romule/profils/eden.json`, adjust it, and set `"verifie": false` unless
you have run it against a real device. See
[Contributing](contribuer.md).
