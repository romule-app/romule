"""The access log, written to disk.

The interface's log lives in memory: a restart wipes the trace of login
attempts. Yet that is precisely what you want to read back afterwards, when
wondering whether someone tried to get in.

Format: one JSON line per event (JSONL), 0600, rotated by size. Nothing else is
kept — no password, no cookie, no token: a log holding secrets becomes a secret
to protect in its own right.
"""

import json
import os
import time

from . import config

FICHIER = config.state_file("_romule-acces.log", "_switch-acces.log")
TAILLE_MAX = 1 << 20            # 1 MiB, then rotation
ARCHIVES = 3


def _rotate():
    try:
        if FICHIER.exists() and FICHIER.stat().st_size > TAILLE_MAX:
            for i in range(ARCHIVES - 1, 0, -1):
                vieux = FICHIER.with_suffix(".log.%d" % i)
                if vieux.exists():
                    vieux.replace(FICHIER.with_suffix(".log.%d" % (i + 1)))
            FICHIER.replace(FICHIER.with_suffix(".log.1"))
    except OSError:
        pass


def record(event, ip="", email="", detail=""):
    """Record an access event. Never raises: a log that breaks authentication
    would be worse than no log at all."""
    try:
        _rotate()
        ligne = json.dumps({
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "e": event,               # connexion | refus | deconnexion | compte
            "ip": str(ip or "")[:45],
            "email": str(email or "")[:120],
            "detail": str(detail or "")[:200],
        }, ensure_ascii=False)
        neuf = not FICHIER.exists()
        with FICHIER.open("a", encoding="utf-8") as f:
            f.write(ligne + "\n")
        if neuf:
            os.chmod(FICHIER, 0o600)
    except Exception:
        pass


def latest(n=200):
    """The last n events, newest first."""
    try:
        lignes = FICHIER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for l in reversed(lignes[-n:]):
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def summary():
    """Enough to answer "did somebody try to get in?"."""
    ev = latest(500)
    refus = [e for e in ev if e.get("e") == "refus"]
    return {
        "evenements": len(ev),
        "refus": len(refus),
        "derniers_refus": refus[:5],
        "derniere_connexion": next((e for e in ev if e.get("e") == "connexion"), None),
    }
