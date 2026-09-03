"""Finding duplicates in the library.

Three shapes, with different consequences:

  * **identical file** — same digest, two locations. That is wasted space and
    nothing else: one can be deleted without thinking;
  * **same game, two platforms** — "Pokemon FireRed" on Switch and on GBA.
    Not a mistake, a choice; we report it and propose nothing;
  * **same game, several regions or revisions** — "(Europe)", "(USA)",
    "(Rev 1)". A choice too, but often an unintended one: the same title was
    downloaded twice without anyone noticing.

Nothing is ever deleted here. The module answers "what looks like a
duplicate?"; the decision stays with the user.
"""

import re
import unicodedata

from . import systems

# What is stripped from a file name to compare TITLES: region, language,
# revision, version number, scene tags, extension.
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

# Words that do not tell two titles apart.
_VIDES = {"the", "a", "le", "la", "les", "of", "de", "du", "and", "et"}


def titre_reduit(nom):
    """A comparable form of a game name: lowercase, no region, no version."""
    # Without unfolding accents, "Pokémon" becomes "poke mon": two words where
    # there is one, and a reduced title that reads as nonsense in the report.
    s = unicodedata.normalize("NFKD", nom or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    for motif in _BRUIT:
        s = re.sub(motif, " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    mots = [m for m in s.split() if m and m not in _VIDES]
    return " ".join(mots)


def _entrees(lib, cfg):
    """Every known game, Switch and other platforms, in one common shape."""
    out = []
    for f in lib.files:
        # An update or a DLC is not a duplicate of the game: we only compare
        # what is playable on its own.
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
    """Return the three families of duplicates."""
    entrees = _entrees(lib, cfg)

    # 1. strictly identical files (same known digest)
    identiques = []
    if empreintes:
        par_sha = {}
        for rel, e in empreintes.items():
            par_sha.setdefault(e.get("sha1"), []).append((rel, e.get("size", 0)))
        for sha, lot in par_sha.items():
            if sha and len(lot) > 1:
                identiques.append({"empreinte": sha, "taille": lot[0][1],
                                   "fichiers": [r for r, _ in lot]})

    # 2. same title, different platforms
    # 3. same title, same platform (regions/revisions)
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
        # On the Switch, two files sharing a base title ID are the same copy
        # seen twice, not a duplicate.
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
