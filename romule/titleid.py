"""Decodage des title ID Switch — LA source unique de verite.

Convention Nintendo (16 hexa, 64 bits), 13e nibble = index 12 :
  BASE   : 13e nibble pair, 3 derniers = 000
  UPDATE : base | 0x800            -> 3 derniers = 800
  DLC    : base + 0x1000 + index   -> 13e nibble impair (base pair + 1)

Les bases ayant toujours un 13e nibble pair, l'incrementation vers le DLC
(+1) ne provoque jamais de retenue au-dela de ce nibble pour un nombre de
DLC realiste (< 4096), donc l'heuristique est stable.
"""

import re
from pathlib import Path

TID_RE = re.compile(r"01[0-9A-Fa-f]{14}")
VER_RE = re.compile(r"\[v(\d+)\]")


def is_valid(tid):
    return bool(tid) and len(tid) == 16 and all(c in "0123456789abcdef" for c in tid.lower())


def from_name(name):
    """Extrait le title ID d'un nom de fichier, ou None."""
    m = TID_RE.search(name)
    return m.group(0).lower() if m else None


def version_from_name(name):
    """Extrait le numero de version de [vN], ou None."""
    m = VER_RE.search(name)
    return int(m.group(1)) if m else None


def pretty_name(name):
    """Nom lisible : on coupe a partir du crochet de title ID."""
    stem = Path(name).stem
    return re.sub(r"\s*\[0100.*", "", stem).strip() or stem


def _nibble(tid):
    return int(tid[12], 16)


def tid_type(tid):
    t = tid.lower()
    n = _nibble(t)
    if n % 2 == 0:
        if t[13:16] == "000":
            return "BASE"
        if t[13:16] == "800":
            return "UPDATE"
    return "DLC"


def tid_base(tid):
    """Title ID du jeu de base correspondant a un update ou un DLC."""
    t = tid.lower()
    n = _nibble(t)
    if n % 2 == 1:
        n -= 1
    return "%s%x000" % (t[:12], n)


def tid_patch(tid):
    """Title ID du patch (update) d'un jeu de base."""
    t = tid.lower()
    return "%s%s800" % (t[:12], t[12])


def dlc_prefix(base_tid):
    """Prefixe (13 hexa) que partagent tous les DLC d'un jeu de base."""
    t = base_tid.lower()
    return "%s%x" % (t[:12], _nibble(t) + 1)


def revision(version):
    """Version Nintendo -> numero de revision lisible (v0, rev 3...)."""
    if version and version > 0:
        return "rev %d" % (version // 65536)
    return "v0"
