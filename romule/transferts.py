"""Memoire des transferts interrompus.

Un envoi de plusieurs dizaines de gigaoctets s'arrete pour trois raisons :
la console est debranchee, l'utilisateur met en pause, ou le serveur est
arrete. Dans les trois cas les fichiers deja envoyes sont bons — la
verification de taille le garantit, et un fichier partiel est efface — mais
la LISTE de ce qu'il restait a faire etait perdue : il fallait retrouver la
meme selection a la main.

On garde donc le reste-a-faire dans un petit fichier. Il ne contient que des
chemins : aucun secret, rien de volumineux.
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
    """Transfert alle au bout : plus rien a reprendre."""
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
    """Ce qu'il faut montrer a l'utilisateur, ou None s'il n'y a rien."""
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
