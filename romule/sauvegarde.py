"""Sauvegarde de la configuration et des comptes.

Ces deux fichiers ne sont pas reconstituables : la configuration porte des
cles d'API et le secret de signature des sessions, le fichier des comptes
porte les empreintes de mots de passe. Ils tiennent en quelques kilo-octets,
donc on garde un historique plutot qu'une seule copie ecrasee a chaque fois —
une sauvegarde unique corrompue ne vaut rien.

Rien de tout cela ne touche aux jeux : ils sont trop gros et deja presents en
deux exemplaires (serveur et console).
"""

import json
import os
import shutil
import time
from pathlib import Path

from . import config

DOSSIER = config.ROOT / "_sauvegardes"
GARDE = 20                       # nombre de copies conservees


def _sources():
    from . import comptes
    return [config.CONFIG_FILE, comptes.FICHIER]


_DERNIERE_AUTO = [0.0]
DELAI_AUTO = 3600.0        # au plus une sauvegarde automatique par heure


def auto(motif="auto"):
    """Sauvegarde declenchee par un changement, mais pas a chaque frappe.

    Sans limite, chaque bascule d'interrupteur creerait un lot : l'historique
    se remplirait de bruit et les vraies versions seraient chassees.
    """
    if time.time() - _DERNIERE_AUTO[0] < DELAI_AUTO:
        return None
    _DERNIERE_AUTO[0] = time.time()
    try:
        return creer(motif)
    except Exception:
        return None


def creer(motif="manuelle"):
    """Copie les fichiers sensibles dans un lot horodate. Renvoie le lot."""
    DOSSIER.mkdir(exist_ok=True)
    os.chmod(DOSSIER, 0o700)
    lot = DOSSIER / (time.strftime("%Y-%m-%d_%H%M%S") + "_" + motif)
    lot.mkdir(exist_ok=True)
    copies = []
    for src in _sources():
        if not Path(src).exists():
            continue
        dst = lot / Path(src).name
        shutil.copy2(src, dst)
        os.chmod(dst, 0o600)
        copies.append(Path(src).name)
    (lot / "_infos.json").write_text(json.dumps({
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "motif": motif,
        "fichiers": copies,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    _elaguer()
    return {"lot": lot.name, "fichiers": copies}


def _elaguer():
    lots = sorted([d for d in DOSSIER.iterdir() if d.is_dir()])
    for vieux in lots[:-GARDE]:
        shutil.rmtree(vieux, ignore_errors=True)


def listing():
    if not DOSSIER.exists():
        return []
    out = []
    for d in sorted((x for x in DOSSIER.iterdir() if x.is_dir()), reverse=True):
        try:
            infos = json.loads((d / "_infos.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            infos = {"date": d.name, "motif": "?", "fichiers": []}
        infos["lot"] = d.name
        infos["octets"] = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
        out.append(infos)
    return out


def restaurer(lot):
    """Remet en place les fichiers d'un lot, apres en avoir sauvegarde l'etat actuel."""
    d = DOSSIER / lot
    try:
        d.resolve().relative_to(DOSSIER.resolve())
    except (ValueError, OSError) as exc:
        raise ValueError("Lot invalide.") from exc
    if not d.is_dir():
        raise ValueError("Lot introuvable.")
    creer("avant-restauration")          # on ne perd jamais l'etat courant
    remis = []
    for src in _sources():
        copie = d / Path(src).name
        if copie.exists():
            shutil.copy2(copie, src)
            os.chmod(src, 0o600)
            remis.append(Path(src).name)
    return remis
