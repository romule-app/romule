"""Browsing the folders of the machine hosting the service.

Why this module exists: until now the games folder could only be named through
an environment variable. On a NAS that means opening a terminal, editing a
compose file and restarting a container — for a piece of information the
interface is the only natural place to type.

A file browser inside a network service is a sensitive primitive: it reveals
the machine's directory tree. Three things hold it.

1. It is administrator-only (`RESERVE_ADMIN` in server.py).
2. It lists FOLDERS and nothing else. File contents, and even file names, do
   not leave here — only a count of recognised games is returned, because that
   is what lets the user recognise their library.
3. `ROMULE_BASES` can confine browsing to a list of folders.

That last point needs explaining, because the default may surprise:
`ROMULE_BASES` is NOT set by default. It is the choice Jellyfin, Sonarr and
qBittorrent make, and it is not a relaxation — it is an acknowledgement of who
really holds the boundary:

  * in a container, the process only sees what is mounted. The compose file's
    `volumes:` IS the allow-list, and it is enforced by the kernel rather than
    by application code;
  * natively, the boundary is the Unix account running the service.

An application-level allow-list on top would mostly give the illusion of a
protection. `ROMULE_BASES` stays available for anyone installing natively under
a broad account who wants to restrict themselves anyway.
"""

import os
from pathlib import Path

from . import config, systems

# `BASES` and the membership check live in `config`: the same rule must hold
# for what we BROWSE and for what we CHOOSE.
BASES = config.BASES
autorise = config.dans_les_bases

# Counting ceilings. A folder may hold a million files, and the user is
# waiting for an answer while the dialog is open.
PROFONDEUR = 3
PLAFOND = 20000


def _extensions(cfg=None):
    """Every recognised extension, Switch and retro platforms alike.

    `cfg` is passed by the caller when it already has it: without it,
    `systems.liste()` re-reads the configuration file on every click in the
    browsing dialog.
    """
    exts = set(config.EXTS)
    for s in systems.liste(cfg):
        exts.update(e.lower() for e in s.get("exts", []))
    return exts


def compter_jeux(dossier, exts=None, cfg=None):
    """How many recognised files live under this folder, bounded by depth.

    Bounded, not exact: this number answers "yes, that is my library", it does
    not take stock. Making it exact would cost a full traversal on every click
    in the dialog.
    """
    exts = exts if exts is not None else _extensions(cfg)
    vus = 0
    trouves = 0
    piles = [(Path(dossier), 0)]
    while piles:
        d, prof = piles.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    vus += 1
                    if vus > PLAFOND:
                        return trouves
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if prof < PROFONDEUR and e.name not in config.IGNORE_DIRS:
                                piles.append((Path(e.path), prof + 1))
                        elif os.path.splitext(e.name)[1].lower() in exts:
                            trouves += 1
                    except OSError:
                        continue
        except (OSError, ValueError):
            continue
    return trouves


def lister(chemin="", cfg=None):
    """A path's subfolders. Returns a dict, or {"error": ...}."""
    brut = str(chemin or "").strip()
    # Starting point: the current library. But it may sit OUTSIDE the declared
    # bases — that is even the normal case for a container that keeps its data
    # in a volume and confines browsing to the games mount. Without this
    # fallback, opening the dialog answered "path outside the allowed folders"
    # to someone who had not asked for anything yet.
    depart = config.LUDO
    if not config.dans_les_bases(depart) and config.BASES:
        depart = config.BASES[0]
    cible = Path(brut).expanduser() if brut else depart
    try:
        cible = cible.resolve()
    except OSError as exc:
        return {"error": "chemin illisible : %s" % exc}
    if not autorise(cible):
        # Deliberately stingy: confirming that a path outside the bases
        # exists would already answer the question we are refusing.
        return {"error": "chemin hors des dossiers autorises"}
    if not cible.is_dir():
        return {"error": "ce dossier n'existe pas"}

    dossiers = []
    try:
        with os.scandir(cible) as it:
            for e in it:
                try:
                    if not e.is_dir():          # follows links: a link to a
                        continue                # folder is still a folder
                except OSError:
                    continue
                p = Path(e.path)
                if not autorise(p):
                    continue
                dossiers.append({
                    "nom": e.name,
                    "chemin": str(p),
                    "cache": e.name.startswith("."),
                    "lisible": os.access(p, os.R_OK | os.X_OK),
                })
    except PermissionError:
        return {"error": "lecture refusee sur ce dossier"}
    except OSError as exc:
        return {"error": "lecture impossible : %s" % exc}
    dossiers.sort(key=lambda d: d["nom"].lower())

    parent = cible.parent
    return {
        "chemin": str(cible),
        # No parent outside the bases: the dialog must not offer a button
        # that will answer "refused".
        "parent": str(parent) if parent != cible and autorise(parent) else "",
        "dossiers": dossiers,
        "ecrivable": os.access(cible, os.W_OK),
        "jeux": compter_jeux(cible, cfg=cfg),
        "douteux": config.racine_douteuse(cible),
        "raccourcis": raccourcis(),
    }


def raccourcis():
    """The starting points offered in the dialog."""
    vus = set()
    out = []
    for libelle, p in (("Ludothèque actuelle", config.LUDO),
                       ("Données du service", config.ROOT),
                       ("Dossier personnel", Path.home()),
                       ("Racine", Path(Path.cwd().anchor or "/"))):
        try:
            p = Path(p).resolve()
        except OSError:
            continue
        if str(p) in vus or not p.is_dir() or not autorise(p):
            continue
        vus.add(str(p))
        out.append({"nom": libelle, "chemin": str(p)})
    # The declared bases are, by definition, the places to go.
    for b in BASES:
        if str(b) not in vus and b.is_dir():
            vus.add(str(b))
            out.append({"nom": b.name or str(b), "chemin": str(b)})
    return out
