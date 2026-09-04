"""Emulator profiles: where the games, the NAND and the saves live.

The tool was written for ONE emulator — Eden — whose Android package name and
directory layout were hard-coded across `nand.py`, `saves.py` and
`edenconf.py`. Three modules to edit to try another one, and two of them did
not even agree on the package name: `nand.py` said `dev.eden.eden_emulator`,
`saves.py` said `dev.eden_emu.eden`. So a profile carries SEVERAL candidate
names, and we ask the console which one is actually installed.

Un profil decrit :

    paquets      the possible Android names, newest first
    donnees      template of the data folder, where {paquet} is substituted
    jeux_defaut  where the emulator reads its games, on first setup
    config       the settings format, or null when they cannot be driven
    sauvegardes  save paths, relative to the data folder
    verifie      has this profile been tried on real hardware

`verifie` matters and is deliberately visible: only Eden is. Announcing support
we could not put to the test would be an empty promise.
"""

import json
from pathlib import Path

from . import config

DOSSIER = Path(__file__).resolve().parent / "profils"
DEFAULT = "eden"

_CACHE = None


def all_profiles():
    """Every shipped profile, in display order."""
    global _CACHE
    if _CACHE is None:
        out = []
        for f in sorted(DOSSIER.glob("*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue          # an unreadable profile does not stop the others
        _CACHE = sorted(out, key=lambda p: (p.get("ordre", 50), p.get("nom", "")))
    return _CACHE


def get(cle):
    for p in all_profiles():
        if p.get("cle") == cle:
            return p
    for p in all_profiles():
        if p.get("cle") == DEFAULT:
            return p
    return {"cle": "generique", "nom": "Autre", "paquets": [], "donnees": "",
            "config": None, "sauvegardes": [], "verifie": False}


def active(cfg=None):
    cfg = cfg if cfg is not None else config.load_config()
    return get(cfg.get("emulateur") or DEFAULT)


def package(cfg=None):
    """The package name we keep: the one detected on the console, else the first.

    Detection happens elsewhere and is stored in the configuration: resolving it
    here would mean querying the console on every call, including to render a
    page.
    """
    cfg = cfg if cfg is not None else config.load_config()
    trouve = (cfg.get("emulateur_paquet") or "").strip()
    if trouve:
        return trouve
    liste = active(cfg).get("paquets") or []
    return liste[0] if liste else ""


def data_dir(cfg=None):
    """The emulator's data folder on the console, or "" when unknown."""
    cfg = cfg if cfg is not None else config.load_config()
    gabarit = active(cfg).get("donnees") or ""
    p = package(cfg)
    if not gabarit or (not p and "{paquet}" in gabarit):
        return ""
    return gabarit.replace("{paquet}", p)


def under(path, cfg=None):
    """A path under the data folder, or "" when that folder is unknown."""
    base = data_dir(cfg)
    return (base + "/" + path.lstrip("/")) if base else ""


def config_editable(cfg=None):
    """Can we read and write this emulator's settings?"""
    return bool((active(cfg).get("config") or {}).get("format") == "ini-qt")


def detect(cfg=None):
    """Ask the console which of the candidate packages is installed.

    Returns the package name, or "" when none is. This is what replaces the
    hard-coded name: two emulators of the same profile may carry different
    names depending on their version.
    """
    from . import device
    if not device.adb_available():
        return ""
    for p in (active(cfg).get("paquets") or []):
        sortie = device._shell("pm path %s 2>/dev/null" % device._q(p), timeout=20)
        if sortie and "package:" in sortie:
            return p
    return ""


def public():
    """What the interface needs to know, without the layout details."""
    return [{"cle": p["cle"], "nom": p["nom"], "verifie": bool(p.get("verifie")),
             "reglages": bool((p.get("config") or {}).get("format")),
             "note": p.get("note", "")} for p in all_profiles()]
