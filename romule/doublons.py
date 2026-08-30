"""Detection des doublons dans la ludotheque.

Trois formes, qui n'ont pas les memes consequences :

  * **fichier identique** — meme empreinte, deux emplacements. C'est de la
    place perdue, rien de plus : on peut en supprimer un sans reflechir ;
  * **meme jeu, deux plateformes** — « Pokemon FireRed » en Switch et en GBA.
    Ce n'est pas une erreur, c'est un choix ; on le signale sans rien proposer ;
  * **meme jeu, plusieurs regions ou revisions** — « (Europe) », « (USA) »,
    « (Rev 1) ». La aussi c'est un choix, mais il est souvent involontaire :
    on a telecharge deux fois le meme titre sans s'en rendre compte.

On ne supprime jamais rien ici. Le module repond a « qu'est-ce qui fait
doublon ? », la decision reste a l'utilisateur.
"""

import re
import unicodedata
from pathlib import Path

from . import config, systems

# Ce qu'on retire d'un nom de fichier pour comparer des TITRES : region,
# langue, revision, numero de version, marqueurs de scene, extension.
_BRUIT = [
    r"\((?:europe|usa|japan|france|germany|spain|italy|world|eur|us|jp|fr|de|es|it|"
    r"en|multi\d*|rev\s*\d+|v\d[\d.]*|proto|beta|demo|unl|beta\d*)\)",
    r"\[(?:[^\]]*)\]",
    r"\((?:[^)]*(?:ver|version)[^)]*)\)",
    r"\b(?:usa|europe|japan|world|rev\s*\d+)\b",
    r"\bv\d[\d.]*\b",
    r"\.(?:nsp|nsz|xci|xcz|iso|chd|cue|bin|gba|gb|gbc|nds|sfc|smc|z64|n64|v64|"
    r"md|gen|smd|nes|fds|3ds|cia|rvz|wbfs|pbp|cso|zip|7z|rar|gdi|cdi|wud|wux)$",
]

# Mots qui ne distinguent pas deux titres.
_VIDES = {"the", "a", "le", "la", "les", "of", "de", "du", "and", "et"}


def titre_reduit(nom):
    """Forme comparable d'un nom de jeu : minuscules, sans region ni version."""
    # Sans depliage des accents, « Pokémon » devient « poke mon » : deux mots
    # la ou il n'y en a qu'un, et un titre reduit illisible dans le rapport.
    s = unicodedata.normalize("NFKD", nom or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    for motif in _BRUIT:
        s = re.sub(motif, " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    mots = [m for m in s.split() if m and m not in _VIDES]
    return " ".join(mots)


def _entrees(lib, cfg):
    """Tous les jeux connus, Switch et autres plateformes, sous une meme forme."""
    out = []
    for f in lib.files:
        # Une mise a jour ou un DLC n'est pas un doublon du jeu : on ne compare
        # que ce qui est jouable seul.
        if f.get("type") in ("UPDATE", "DLC"):
            continue
        out.append({"plateforme": "switch", "nom": f["name"], "chemin": f["path"],
                    "taille": f.get("size", 0), "tid": (f.get("tid") or "").lower()})
    for s in systems.liste(cfg):
        if s["engine"] == "switch":
            continue
        for f in systems.scan_local(s["key"], cfg):
            out.append({"plateforme": s["key"], "nom": f["file"],
                        "chemin": f["path"], "taille": f.get("size", 0), "tid": ""})
    return out


def chercher(lib, cfg, empreintes=None):
    """Renvoie les trois familles de doublons."""
    entrees = _entrees(lib, cfg)

    # 1. fichiers rigoureusement identiques (meme empreinte connue)
    identiques = []
    if empreintes:
        par_sha = {}
        for rel, e in empreintes.items():
            par_sha.setdefault(e.get("sha1"), []).append((rel, e.get("size", 0)))
        for sha, lot in par_sha.items():
            if sha and len(lot) > 1:
                identiques.append({"empreinte": sha, "taille": lot[0][1],
                                   "fichiers": [r for r, _ in lot]})

    # 2. meme titre, plateformes differentes
    # 3. meme titre, meme plateforme (regions/revisions)
    par_titre = {}
    for e in entrees:
        cle = titre_reduit(e["nom"])
        if len(cle) < 3:
            continue
        par_titre.setdefault(cle, []).append(e)

    multi, regions = [], []
    for cle, lot in sorted(par_titre.items()):
        if len(lot) < 2:
            continue
        plateformes = {e["plateforme"] for e in lot}
        # Sur la Switch, deux fichiers de meme title ID de base sont le meme
        # exemplaire vu deux fois, pas un doublon.
        tids = {e["tid"][:13] for e in lot if e["tid"]}
        if len(plateformes) > 1:
            multi.append({"titre": cle, "plateformes": sorted(plateformes),
                          "entrees": lot})
        elif len(lot) > 1 and len(tids) != 1:
            regions.append({"titre": cle, "plateforme": lot[0]["plateforme"],
                            "entrees": lot,
                            "octets": sum(e["taille"] for e in lot[1:])})

    return {
        "identiques": sorted(identiques, key=lambda x: -x["taille"]),
        "multi_plateformes": multi,
        "regions": sorted(regions, key=lambda x: -x["octets"]),
        "recuperable": sum(x["taille"] * (len(x["fichiers"]) - 1) for x in identiques)
                       + sum(x["octets"] for x in regions),
    }


def rapport(lib, cfg):
    from . import integrity
    return chercher(lib, cfg, integrity._load())
