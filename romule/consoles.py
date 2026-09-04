"""Several consoles, each with its own settings.

`device.py` is HOW we talk to a console: adb, the serial, the shell. This file
is WHICH one we are talking to, and what is remembered about it. The two names
are close on purpose — they are two halves of the same subject — and the one
they are not is `devices.py`, which next to `device.py` would be a typo waiting
to happen.

The gap this fills
------------------
`wifi_addr` was singular. So were `device_dir`, `roms_root`, `emulateur` and
the rest: a single console's worth of settings, in a tool aimed at people who
own an Odin *and* a Retroid. Pairing the second one overwrote the first, and
nothing said which console a game was on.

How it stays compatible
-----------------------
The per-console fields keep living at the top level of the configuration, and
`load_config()` overlays the ACTIVE console's values on top of them. Every one
of the seventy-odd `cfg["device_dir"]` reads in the code therefore keeps
working, unchanged, and reads the right console.

`save_config()` mirrors the other way: the flat keys are written back into the
active console's entry. That is what lets someone go back a version without
losing their pairing — the old code reads the flat keys and finds exactly what
it left there.

The migration is silent, and happens once
-----------------------------------------
An installation that has never seen this file has no `devices` list and a set
of flat keys. On first load it gets one console, named "Ma console", carrying
those values. Nobody is asked anything, and nothing is lost.

A fresh installation gets that console too, built from the defaults. There is
therefore ALWAYS exactly one console to talk about, which is what keeps an
"if no console is declared" branch out of every screen and every route.
"""

import json
import time

from . import config

# What each console was last seen holding. Kept on disk rather than in memory
# because the question it answers — "this game, which console is it on?" — is
# asked about the console that is NOT plugged in. An inventory that only exists
# while a console is connected cannot answer it.
#
# Only file names are stored, not the tree: the answer is "the Odin has it", not
# "here is its path", and a path from a console nobody has read for a week is a
# path that has probably moved.
INVENTORY = config.state_file("_romule-consoles.json", "_romule-consoles.json")

# Past this, an inventory is shown with its age rather than as fact. Nothing is
# erased: knowing a console held a game a month ago beats knowing nothing, as
# long as the screen says it is a month old.
STALE_AFTER = 30 * 24 * 3600

# The settings that belong to a CONSOLE rather than to the service. Anything
# not in this list — the covers provider, the language, the schedule — is the
# same whichever console is plugged in, and stays where it is.
PER_DEVICE = ("serial", "wifi_addr", "emulateur", "emulateur_paquet",
              "device_dir", "roms_root", "push_layout", "auto_nand")

MAX_DEVICES = 8
DEFAULT_NAME = "Ma console"


def _clean_one(entry, index=0):
    """One console's entry, with only the fields we know."""
    if not isinstance(entry, dict):
        return None
    out = {
        "id": str(entry.get("id") or "")[:32] or ("c%d" % (index + 1)),
        "nom": str(entry.get("nom") or DEFAULT_NAME)[:60],
    }
    for key in PER_DEVICE:
        value = entry.get(key)
        if key == "auto_nand":
            out[key] = bool(value)
        else:
            out[key] = str(value or "")
    return out


def list_all(cfg):
    """The declared consoles, sanitised. Never empty once migration has run."""
    raw = cfg.get("devices")
    if not isinstance(raw, list):
        return []
    out = []
    for i, entry in enumerate(raw[:MAX_DEVICES]):
        clean = _clean_one(entry, i)
        if clean:
            out.append(clean)
    return out


def _new_id(existing):
    """An identifier no console already has. Time-based rather than counted:
    a counter reuses the number of a console that was removed, and the removed
    one's remembered inventory would then belong to its replacement."""
    base = "c%d" % int(time.time())
    taken = {d["id"] for d in existing}
    if base not in taken:
        return base
    for n in range(1, 100):
        if "%s-%d" % (base, n) not in taken:
            return "%s-%d" % (base, n)
    return base + "-x"


def migrate(cfg):
    """Build the first console from the flat keys. True if anything changed.

    Called on every load and does nothing on all but the first: the test is
    "is the list empty", not a version number, so an installation that has had
    its list emptied by hand recovers rather than losing its pairing.

    There is ALWAYS one console once this has run, even on an installation that
    has never paired anything. The alternative — an empty list until the first
    pairing — buys nothing and costs an "no console declared" branch in every
    screen and every route that reads one.
    """
    if list_all(cfg):
        return False
    first = _clean_one({k: cfg.get(k) for k in PER_DEVICE}, 0)
    first["nom"] = DEFAULT_NAME
    first["id"] = _new_id([])
    cfg["devices"] = [first]
    cfg["active_device"] = first["id"]
    return True


def active(cfg):
    """The console being driven, or None when none is declared."""
    known = list_all(cfg)
    if not known:
        return None
    wanted = str(cfg.get("active_device") or "")
    for d in known:
        if d["id"] == wanted:
            return d
    # A pointer at a console that no longer exists is not an error worth an
    # exception: it happens the moment one is removed. The first one answers.
    return known[0]


def overlay(cfg):
    """`cfg` with the active console's fields on top. Returns the same dict.

    This is what keeps every existing `cfg["device_dir"]` honest without
    touching a single call site.
    """
    current = active(cfg)
    if not current:
        return cfg
    for key in PER_DEVICE:
        cfg[key] = current[key]
    cfg["active_device"] = current["id"]
    return cfg


def mirror(cfg):
    """The reverse: the flat keys are written back into the active console.

    Called on save. Without it, `/api/config` would change `device_dir` at the
    top level only, and switching console would bring the old value back —
    the change would look accepted and be gone a click later.
    """
    known = list_all(cfg)
    if not known:
        return cfg
    wanted = str(cfg.get("active_device") or "")
    for d in known:
        if d["id"] == wanted or (wanted == "" and d is known[0]):
            for key in PER_DEVICE:
                if key in cfg:
                    d[key] = bool(cfg[key]) if key == "auto_nand" else str(cfg[key] or "")
            break
    cfg["devices"] = known
    return cfg


def add(cfg, nom=""):
    """Declare a console. Returns its entry, or None when the list is full."""
    known = list_all(cfg)
    if len(known) >= MAX_DEVICES:
        return None
    entry = _clean_one({"nom": nom or DEFAULT_NAME}, len(known))
    entry["id"] = _new_id(known)
    known.append(entry)
    cfg["devices"] = known
    return entry


def remove(cfg, device_id):
    """Forget a console. The last one cannot be removed while it is the only
    one holding the pairing: an empty list means the flat keys migrate again,
    and the user would find their old console back."""
    known = list_all(cfg)
    kept = [d for d in known if d["id"] != str(device_id or "")]
    if len(kept) == len(known):
        return False
    cfg["devices"] = kept
    if kept and str(cfg.get("active_device") or "") not in {d["id"] for d in kept}:
        cfg["active_device"] = kept[0]["id"]
    if not kept:
        cfg["active_device"] = ""
    return True


def select(cfg, device_id):
    """Drive another console. False when it is not one we know."""
    if str(device_id or "") not in {d["id"] for d in list_all(cfg)}:
        return False
    cfg["active_device"] = str(device_id)
    overlay(cfg)
    return True


def rename(cfg, device_id, nom):
    known = list_all(cfg)
    for d in known:
        if d["id"] == str(device_id or ""):
            d["nom"] = str(nom or DEFAULT_NAME)[:60]
            cfg["devices"] = known
            return True
    return False


# ------------------------------------------------------ what each one holds


def _read_inventory():
    try:
        d = json.loads(INVENTORY.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_inventory(d):
    try:
        INVENTORY.parent.mkdir(parents=True, exist_ok=True)
        tmp = INVENTORY.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(INVENTORY)
    except OSError:
        pass                      # a full disk must not break a console read


def remember(cfg, names, device_id=None):
    """Note what the console currently being driven holds.

    `names` is whatever the caller has: file names, paths, entries. Only the
    base name is kept — see INVENTORY for why.
    """
    current = active(cfg)
    device_id = device_id or (current["id"] if current else "")
    if not device_id:
        return False
    clean = sorted({str(n).rsplit("/", 1)[-1] for n in (names or []) if n})
    d = _read_inventory()
    d[device_id] = {"at": int(time.time()), "files": clean}
    _write_inventory(d)
    return True


def inventory(device_id):
    """What that console was last seen holding: (epoch, [names])."""
    entry = _read_inventory().get(str(device_id or "")) or {}
    return int(entry.get("at") or 0), list(entry.get("files") or [])


def forget_inventory(device_id):
    d = _read_inventory()
    if str(device_id or "") in d:
        del d[str(device_id)]
        _write_inventory(d)
        return True
    return False


def where_is(cfg, name):
    """Which declared consoles were last seen holding this file.

    Returns a list of {id, nom, at}, oldest reading last. This is the whole
    point of keeping the inventory: answering for a console that is not
    plugged in.
    """
    wanted = str(name or "").rsplit("/", 1)[-1]
    if not wanted:
        return []
    d = _read_inventory()
    out = []
    for console in list_all(cfg):
        entry = d.get(console["id"]) or {}
        if wanted in (entry.get("files") or []):
            out.append({"id": console["id"], "nom": console["nom"],
                        "at": int(entry.get("at") or 0)})
    return sorted(out, key=lambda x: -x["at"])


def held_summary(cfg):
    """Per console: how many files, and how old the reading is."""
    d = _read_inventory()
    now = int(time.time())
    out = []
    for console in list_all(cfg):
        entry = d.get(console["id"]) or {}
        at = int(entry.get("at") or 0)
        out.append({"id": console["id"], "nom": console["nom"],
                    "fichiers": len(entry.get("files") or []),
                    "lu": at,
                    "vieux": bool(at and now - at > STALE_AFTER)})
    return out


def public(cfg):
    """What the interface needs: the list, and which one is being driven."""
    known = list_all(cfg)
    current = active(cfg)
    return {"devices": [{"id": d["id"], "nom": d["nom"],
                         "device_dir": d["device_dir"],
                         "emulateur": d["emulateur"],
                         "wifi_addr": d["wifi_addr"]} for d in known],
            "active_device": current["id"] if current else ""}
