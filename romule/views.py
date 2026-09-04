"""Saved views — a combination of filters you find again in one click.

Three filters coexist in the library: the search, the status chip, and the
advanced filters. They compose, but replaying them means repeating all three
gestures every time. A view keeps them together.

What a view remembers, and what it does not
--------------------------------------------
It remembers what DEFINES a subset of the library: the platform, the search,
the status, the advanced filters.

It remembers neither the sort order, nor the tile size, nor the pagination.
Those are DISPLAY preferences: they apply to everything you look at, and
locking them into a view would make it surprising — you would recall "Games to
convert" and the grid order would change without being asked.

On the server, not in the browser
----------------------------------
Sort order and tile size live in `localStorage`: they belong to the screen in
front of you. A view is something you built, that you want back on your phone
as on your desk, and that must not vanish because you cleared your browser.
"""

import json
import os
import secrets
import threading
import time

from . import config

FILE = config.state_file("_romule-vues.json", "_romule-vues.json")

# What we agree to store. A CLOSED list: the browser sends whatever it likes,
# and without this barrier a future client version could grow the state file
# with anything at all.
FIELDS = ("systeme", "recherche", "etat", "avances")

MAX_VIEWS = 50           # past this it is a list, not a shortcut
_LOCK = threading.RLock()


def _read():
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "vues": []}
    if not isinstance(d, dict) or not isinstance(d.get("vues"), list):
        return {"version": 1, "vues": []}
    return d


def _write(d):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FILE)


def _clean(filters):
    """Keep only the known fields, and bound what can be bounded."""
    f = filters if isinstance(filters, dict) else {}
    out = {
        "systeme": str(f.get("systeme") or "all")[:40],
        "recherche": str(f.get("recherche") or "")[:120],
        "etat": str(f.get("etat") or "all")[:40],
        "avances": [str(x)[:40] for x in (f.get("avances") or [])
                    if isinstance(x, str)][:20],
    }
    return out


def list_all():
    return _read()["vues"]


def create(name, filters):
    """Return the created view, or None if the limit is reached."""
    name = (name or "").strip()[:60] or "Sans nom"
    with _LOCK:
        d = _read()
        if len(d["vues"]) >= MAX_VIEWS:
            return None
        vue = {"id": secrets.token_hex(8), "nom": name,
               "filtres": _clean(filters), "cree": int(time.time())}
        d["vues"].append(vue)
        _write(d)
    return vue


def delete(vid):
    with _LOCK:
        d = _read()
        restantes = [v for v in d["vues"] if v["id"] != vid]
        if len(restantes) == len(d["vues"]):
            return False
        d["vues"] = restantes
        _write(d)
    return True
