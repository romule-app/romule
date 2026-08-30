"""Profils d'emulateur : ou vivent les jeux, la NAND, les sauvegardes.

L'outil etait ecrit pour UN emulateur — Eden — dont le nom de paquet Android et
l'arborescence etaient ecrits en dur dans `nand.py`, `saves.py` et
`edenconf.py`. Trois modules a modifier pour en essayer un autre, et deux
d'entre eux ne s'accordaient meme pas sur le nom du paquet : `nand.py` disait
`dev.eden.eden_emulator`, `saves.py` disait `dev.eden_emu.eden`. Un profil
porte donc PLUSIEURS noms candidats, et l'on demande a la console lequel est
reellement installe.

Un profil decrit :

    paquets      les noms Android possibles, du plus recent au plus ancien
    donnees      gabarit du dossier de donnees, ou {paquet} est substitue
    jeux_defaut  ou l'emulateur lit ses jeux, au premier reglage
    config       format des reglages, ou null s'ils ne sont pas pilotables
    sauvegardes  chemins des sauvegardes, relatifs au dossier de donnees
    verifie      ce profil a-t-il ete essaye sur du materiel reel

`verifie` est important et volontairement visible : seul Eden l'est. Annoncer
une prise en charge qu'on n'a pas pu eprouver serait une promesse en l'air.
"""

import json
from pathlib import Path

from . import config

DOSSIER = Path(__file__).resolve().parent / "profils"
DEFAUT = "eden"

_CACHE = None


def tous():
    """Tous les profils livres, dans l'ordre d'affichage."""
    global _CACHE
    if _CACHE is None:
        out = []
        for f in sorted(DOSSIER.glob("*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue          # un profil illisible n'empeche pas les autres
        _CACHE = sorted(out, key=lambda p: (p.get("ordre", 50), p.get("nom", "")))
    return _CACHE


def get(cle):
    for p in tous():
        if p.get("cle") == cle:
            return p
    for p in tous():
        if p.get("cle") == DEFAUT:
            return p
    return {"cle": "generique", "nom": "Autre", "paquets": [], "donnees": "",
            "config": None, "sauvegardes": [], "verifie": False}


def actif(cfg=None):
    cfg = cfg if cfg is not None else config.load_config()
    return get(cfg.get("emulateur") or DEFAUT)


def paquet(cfg=None):
    """Nom de paquet retenu : celui detecte sur la console, sinon le premier.

    La detection est faite ailleurs et rangee dans la configuration : la
    resoudre ici obligerait a interroger la console a chaque appel, y compris
    pour afficher une page.
    """
    cfg = cfg if cfg is not None else config.load_config()
    trouve = (cfg.get("emulateur_paquet") or "").strip()
    if trouve:
        return trouve
    liste = actif(cfg).get("paquets") or []
    return liste[0] if liste else ""


def dossier_donnees(cfg=None):
    """Dossier de donnees de l'emulateur sur la console, ou "" si inconnu."""
    cfg = cfg if cfg is not None else config.load_config()
    gabarit = actif(cfg).get("donnees") or ""
    p = paquet(cfg)
    if not gabarit or (not p and "{paquet}" in gabarit):
        return ""
    return gabarit.replace("{paquet}", p)


def sous(chemin, cfg=None):
    """Chemin sous le dossier de donnees, ou "" si celui-ci est inconnu."""
    base = dossier_donnees(cfg)
    return (base + "/" + chemin.lstrip("/")) if base else ""


def config_pilotable(cfg=None):
    """Peut-on lire et ecrire les reglages de cet emulateur ?"""
    return bool((actif(cfg).get("config") or {}).get("format") == "ini-qt")


def detecter(cfg=None):
    """Demande a la console lequel des paquets candidats est installe.

    Renvoie le nom du paquet, ou "" si aucun. C'est ce qui remplace le nom
    ecrit en dur : deux emulateurs du meme profil peuvent porter des noms
    differents selon leur version.
    """
    from . import device
    if not device.adb_available():
        return ""
    for p in (actif(cfg).get("paquets") or []):
        sortie = device._shell("pm path %s 2>/dev/null" % device._q(p), timeout=20)
        if sortie and "package:" in sortie:
            return p
    return ""


def public():
    """Ce que l'interface a besoin de savoir, sans les details d'arborescence."""
    return [{"cle": p["cle"], "nom": p["nom"], "verifie": bool(p.get("verifie")),
             "reglages": bool((p.get("config") or {}).get("format")),
             "note": p.get("note", "")} for p in tous()]
