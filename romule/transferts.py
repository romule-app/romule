"""Memory of interrupted transfers.

A send of several dozen gigabytes stops for three reasons: the console is
unplugged, the user pauses, or the server is stopped. In all three cases the
files already sent are sound — the size check guarantees it, and a partial file
is erased — but the LIST of what was left to do was lost: you had to rebuild
the same selection by hand.

So we keep the to-do list in a small file. It holds nothing but paths: no
secrets, nothing bulky.
"""

import json
import time
from pathlib import Path

from . import config

FICHIER = config.ROOT / "_transfert-en-cours.json"


def demarrer(chemins, destination, genre="switch"):
    _ecrire({"debut": time.time(), "genre": genre, "destination": destination,
             "restants": [str(c) for c in chemins], "faits": []})


def marquer_fait(chemin):
    d = etat()
    if not d:
        return
    c = str(chemin)
    d["restants"] = [x for x in d["restants"] if x != c]
    d["faits"].append(c)
    _ecrire(d)


def terminer():
    """The transfer went all the way: nothing left to resume."""
    try:
        FICHIER.unlink()
    except OSError:
        pass


def etat():
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("restants") else None


def resume():
    """What to show the user, or None when there is nothing."""
    d = etat()
    if not d:
        return None
    restants = [c for c in d["restants"] if Path(c).is_file()]
    if not restants:
        terminer()
        return None
    return {
        "genre": d.get("genre", "switch"),
        "destination": d.get("destination", ""),
        "restants": len(restants),
        "faits": len(d.get("faits", [])),
        "octets": sum(Path(c).stat().st_size for c in restants),
        "depuis": int(time.time() - d.get("debut", time.time())),
        "chemins": restants,
    }


def _ecrire(d):
    try:
        FICHIER.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
