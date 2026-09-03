"""The game systems the tool handles.

The Switch has its own engine (title IDs, nsz, titledb, GAMES/UPDATE/DLC) and
stays with scan.Library. Other systems use a much simpler "generic" engine: one
file is one game, no updates, no DLC, cover art looked up by name.

Rangement local :
  - switch    : at the library root (GAMES/UPDATE/DLC) — historical
  - the rest  : <root>/<folder>/   (e.g. PS2/, Dreamcast/)

Rangement console : <roms_root>/<folder>  (ex. .../emulation/ROMs/PS2)
"""

import re
from pathlib import Path

from . import config

# Common extensions per system. Deliberately broad: better to offer than to
# miss a file. Archives are handled upstream (_import).
SYSTEMS = [
    {"key": "switch",   "name": "Nintendo Switch",  "folder": "Switch",
     "engine": "switch", "exts": [".nsp", ".xci", ".nsz", ".xcz"]},
    {"key": "ps2",      "name": "PlayStation 2",    "folder": "PS2",
     "engine": "generic", "exts": [".iso", ".chd", ".bin", ".cue", ".gz", ".cso"]},
    {"key": "psx",      "name": "PlayStation",      "folder": "PSX",
     "engine": "generic", "exts": [".chd", ".cue", ".bin", ".pbp", ".m3u", ".iso"]},
    {"key": "psp",      "name": "PSP",              "folder": "PSP",
     "engine": "generic", "exts": [".iso", ".cso", ".chd"]},
    {"key": "gamecube", "name": "GameCube",         "folder": "GameCube",
     "engine": "generic", "exts": [".iso", ".rvz", ".gcm", ".ciso"]},
    {"key": "wii",      "name": "Wii",              "folder": "Wii",
     "engine": "generic", "exts": [".iso", ".rvz", ".wbfs"]},
    {"key": "3ds",      "name": "Nintendo 3DS",     "folder": "3DS",
     "engine": "generic", "exts": [".3ds", ".cia", ".cci", ".cxi"]},
    {"key": "nds",      "name": "Nintendo DS",      "folder": "NDS",
     "engine": "generic", "exts": [".nds", ".dsi"]},
    {"key": "n64",      "name": "Nintendo 64",      "folder": "N64",
     "engine": "generic", "exts": [".z64", ".n64", ".v64"]},
    {"key": "snes",     "name": "Super Nintendo",   "folder": "SNES",
     "engine": "generic", "exts": [".sfc", ".smc"]},
    {"key": "nes",      "name": "NES",              "folder": "NES",
     "engine": "generic", "exts": [".nes", ".fds"]},
    {"key": "gba",      "name": "Game Boy Advance", "folder": "GBA",
     "engine": "generic", "exts": [".gba"]},
    {"key": "gb",       "name": "Game Boy / Color", "folder": "GB",
     "engine": "generic", "exts": [".gb", ".gbc"]},
    {"key": "dreamcast", "name": "Dreamcast",       "folder": "Dreamcast",
     "engine": "generic", "exts": [".chd", ".gdi", ".cdi"]},
    {"key": "saturn",   "name": "Saturn",           "folder": "Saturn",
     "engine": "generic", "exts": [".chd", ".cue", ".bin"]},
    {"key": "megadrive", "name": "Mega Drive",      "folder": "MegaDrive",
     "engine": "generic", "exts": [".md", ".gen", ".bin", ".smd"]},
    {"key": "arcade",   "name": "Arcade (MAME/FBN)", "folder": "Arcade",
     "engine": "generic", "exts": [".zip", ".7z", ".chd"]},
    {"key": "ps3",      "name": "PlayStation 3",    "folder": "PS3",
     "engine": "generic", "exts": [".iso", ".pkg", ".bin"]},
    {"key": "psvita",   "name": "PS Vita",          "folder": "PSVita",
     "engine": "generic", "exts": [".vpk", ".iso", ".mai"]},
    {"key": "wiiu",     "name": "Wii U",            "folder": "WiiU",
     "engine": "generic", "exts": [".wud", ".wux", ".rpx", ".wua"]},
    {"key": "xbox",     "name": "Xbox",             "folder": "Xbox",
     "engine": "generic", "exts": [".iso", ".xbe"]},
    {"key": "xbox360",  "name": "Xbox 360",         "folder": "Xbox360",
     "engine": "generic", "exts": [".iso", ".xex", ".god"]},
    {"key": "pc",       "name": "PC",               "folder": "PC",
     "engine": "generic", "exts": [".exe", ".zip", ".7z", ".iso"]},
]

# Folder names are not standardised: every front-end (EmulationStation,
# RetroArch, Daijisho, Pegasus...) has its own habits. A "PS1" or "Sega" folder
# matched no platform, so its games stayed invisible — 85 titles in the case we
# hit. So we recognise the common spellings, without asking the user to rename
# anything.
ALIAS = {
    "psx": ["ps1", "playstation", "psone", "psxjap"],
    "ps2": ["playstation2"],
    "ps3": ["playstation3"],
    "psp": ["playstationportable"],
    "psvita": ["vita", "psvita", "playstationvita"],
    "megadrive": ["sega", "genesis", "megadrive32x", "smd", "segagenesis",
                  "segamegadrive"],
    "mastersystem": ["mastersystem", "sms"],
    "nds": ["ds", "nintendods"],
    "3ds": ["n3ds", "nintendo3ds"],
    "gb": ["gbc", "gameboy", "gameboycolor"],
    "gba": ["gameboyadvance"],
    "snes": ["supernintendo", "sfc", "supernes", "superfamicom"],
    "nes": ["famicom", "fc", "nintendo"],
    "n64": ["nintendo64"],
    "gamecube": ["gc", "ngc", "gamecube"],
    "wiiu": ["wii_u"],
    "xbox360": ["x360", "xbox_360"],
    "dreamcast": ["dc", "segadreamcast"],
    "saturn": ["segasaturn"],
    "arcade": ["mame", "fbneo", "fba", "neogeo", "cps1", "cps2", "cps3"],
    "switch": ["nintendoswitch", "nsw"],
}


def _normaliser(nom):
    return re.sub(r"[^a-z0-9]", "", (nom or "").lower())


# {forme normalisee -> cle de plateforme}, dossiers officiels compris.
_INDEX_ALIAS = {}
for _s in SYSTEMS:
    _INDEX_ALIAS[_normaliser(_s["folder"])] = _s["key"]
    _INDEX_ALIAS[_normaliser(_s["key"])] = _s["key"]
for _cle, _formes in ALIAS.items():
    for _f in _formes:
        _INDEX_ALIAS.setdefault(_normaliser(_f), _cle)


def plateforme_du_dossier(nom, cfg=None):
    """Cle de plateforme correspondant a un nom de dossier, alias compris.

    Returns None if the name evokes nothing known: better to ask than to file
    a folder at random.
    """
    n = _normaliser(nom)
    if not n:
        return None
    if cfg:
        # a folder the user explicitly mapped wins over everything
        for cle, chemin in (cfg.get("system_dirs") or {}).items():
            if _normaliser(Path(str(chemin)).name) == n:
                return cle
        for s in (cfg.get("systemes_perso") or []):
            if _normaliser(s.get("folder", "")) == n or _normaliser(s.get("key", "")) == n:
                return s.get("key")
    return _INDEX_ALIAS.get(n)

BY_KEY = {s["key"]: s for s in SYSTEMS}
SWITCH = BY_KEY["switch"]


def liste(cfg=None):
    """Known platforms: the shipped ones, plus those the user added.

    Not every console is in the shipped table, and some store their games in a
    way nobody could guess. Rather than waiting for a tool update, one can be
    declared: a name, a folder, some extensions.
    """
    cfg = cfg or config.load_config()
    out = list(SYSTEMS)
    for p in (cfg.get("systemes_perso") or []):
        cle = cle_sure(p.get("key"))
        if not cle or cle in BY_KEY:
            continue
        # The extensions end up in a `find` run on the console: an apostrophe
        # there would break the quoting. We only keep extensions that look like
        # extensions.
        exts = [x for x in (extension_sure(e) for e in (p.get("exts") or [])) if x]
        out.append({"key": cle, "name": p.get("name") or cle,
                    "folder": dossier_sur(p.get("folder"), cle),
                    "engine": "generic",
                    "exts": exts, "perso": True})
    return out


# A folder name coming from the configuration ends up as `config.LUDO / folder`
# and the tool MOVES files into it. "../.." was therefore enough to file ROMs
# anywhere on the host. Only a plain name is accepted.
_NOM_DOSSIER = re.compile(r"^[^/\\:\x00]{1,64}$")


def dossier_sur(nom, defaut):
    """A usable folder name, or `defaut` when the proposed one is not."""
    nom = str(nom or "").strip()
    if not nom or nom in (".", "..") or not _NOM_DOSSIER.match(nom):
        return defaut
    return nom


# The underscore is kept: harmless in a path as in a JavaScript string, and
# removing it would rename keys already in place.
_CLE_INTERDITE = re.compile(r"[^a-z0-9_]+")


def cle_sure(k):
    """A usable platform key, or "" if nothing usable is left of it.

    The name and the folder went through a filter, the key did not — it made do
    with a `strip().lower()`, which removes neither apostrophe, nor slash, nor
    angle bracket. Yet that key is the identifier everywhere: the platform
    index, `system_dirs`, and right into the interface's handlers.

    We NORMALISE rather than reject: refusing would silently make a platform
    someone had already declared disappear, and a lost platform is a library
    you cannot find again.
    """
    k = _CLE_INTERDITE.sub("-", str(k or "").strip().lower()).strip("-_")
    return k[:32]


def extension_sure(e):
    """A usable extension: it ends up inside remote commands."""
    e = str(e or "").strip().lower()
    if not e:
        return ""
    e = e if e.startswith(".") else "." + e
    return e if re.match(r"^\.[a-z0-9]{1,8}$", e) else ""


def assainir_perso(entrees):
    """Clean hand-added platforms before storing them.

    The same work `liste()` does on read, applied here on write. Two checks
    beat one when the field comes from an HTTP request and ends up in a file
    path or a remote command.
    """
    propres = []
    for p in (entrees or []):
        if not isinstance(p, dict):
            continue
        cle = cle_sure(p.get("key"))
        if not cle or cle in BY_KEY:
            continue
        exts = [x for x in (extension_sure(e) for e in (p.get("exts") or [])) if x]
        propres.append({"key": cle,
                        "name": str(p.get("name") or cle)[:80],
                        "folder": dossier_sur(p.get("folder"), cle),
                        "exts": exts})
    return propres


def get_cfg(key, cfg=None):
    """Like get(), but also knows the hand-added platforms."""
    for s in liste(cfg):
        if s["key"] == (key or "switch"):
            return s
    return SWITCH

# Name cleanup: (USA), [!], (v1.0.3), scene tags...
_CLEAN = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")


def get(key):
    return BY_KEY.get(key or "switch", SWITCH)


def pretty_name(filename):
    stem = Path(filename).stem
    return _CLEAN.sub("", stem).replace("_", " ").strip() or stem


def local_dir(sys_key, cfg=None):
    """A system's local folder (the Switch stays at the root, historically).

    `cfg` also finds hand-added platforms: without it, a ROM from a custom
    platform had nowhere to go.
    """
    s = get_cfg(sys_key, cfg) if cfg else get(sys_key)
    if s["engine"] == "switch":
        return config.LUDO
    chemin = (config.LUDO / s["folder"]).resolve()
    # Belt AND braces: even if a name slipped through the filter, the path we
    # build must never leave the library.
    if not str(chemin).startswith(str(config.LUDO.resolve())):
        raise ValueError("Dossier hors de la ludotheque : %s" % s["folder"])
    return chemin


def device_dir(sys_key, cfg):
    """This system's folder on the console.

    <root>/<Folder> by default, but each platform may have its own
    folder name: consoles do not all agree on "SNES" rather than
    "Super Nintendo". The setting lives in `system_dirs`, and saves having to
    type a path for each of them.
    """
    s = get_cfg(sys_key, cfg)
    if s["engine"] == "switch":
        return (cfg.get("device_dir") or "").rstrip("/")
    root = roms_root(cfg)
    if not root:
        return ""
    perso = (cfg.get("system_dirs") or {}).get(sys_key, "").strip()
    # An absolute path wins: consoles do not all keep their ROMs under one
    # root, and some name the folders differently ("PS1" rather than "PSX",
    # "Sega" rather than "MegaDrive").
    if perso.startswith("/"):
        return perso.rstrip("/")
    if perso:
        return root + "/" + perso.strip("/")
    return root + "/" + _dossier_reel(sys_key, s["folder"])


# Folder names actually seen under the ROMs root, remembered from the last read
# of the console. `device_dir` uses them to find a folder that does not carry
# the expected name — "PS1" for PSX, "Sega" for the Mega Drive. Without this the
# games exist, but the tool looks elsewhere.
_DOSSIERS_REELS = []


def memoriser_dossiers(noms):
    global _DOSSIERS_REELS
    _DOSSIERS_REELS = sorted({n for n in noms if n})


def _dossier_reel(sys_key, defaut):
    if not _DOSSIERS_REELS:
        return defaut
    reels = {_normaliser(n): n for n in _DOSSIERS_REELS}
    if _normaliser(defaut) in reels:
        return reels[_normaliser(defaut)]     # the expected name exists: nothing to do
    for norme, nom in sorted(reels.items()):
        if _INDEX_ALIAS.get(norme) == sys_key:
            return nom                        # a known alias points at us
    return defaut


def roms_root(cfg):
    """The ROMs root on the console: configured, or derived from the Switch folder."""
    explicit = (cfg.get("roms_root") or "").strip().rstrip("/")
    if explicit:
        return explicit
    d = (cfg.get("device_dir") or "").rstrip("/")
    if not d:
        return ""
    # .../emulation/ROMs/Switch -> .../emulation/ROMs
    parent = d.rsplit("/", 1)[0]
    return parent if d.rsplit("/", 1)[-1].lower() == SWITCH["folder"].lower() else d


def extensions_acceptees(cfg=None):
    """Every droppable extension: those of ALL platforms, plus archives.

    The drop folder only accepted Switch formats. A GBA ROM or a PS2 image was
    refused although the tool knows perfectly well where to file it — and a
    hand-added platform declares its own extensions, which cannot be known in
    advance.
    """
    exts = set(config.ARCHIVES)
    for s in liste(cfg):
        for e in (s.get("exts") or []):
            e = str(e).strip().lower()
            if e:
                exts.add(e if e.startswith(".") else "." + e)
    return exts


def system_for_file(filename):
    """Guess a file's system from its extension (None when ambiguous).

    Archive formats (.zip, .7z, .rar) are NEVER assigned to a platform, even if
    only one declares them: a .zip is almost always a compressed game waiting
    to be extracted. Two Switch games downloaded as .zip once ended up filed
    among the arcade ROMs that way.
    """
    ext = Path(filename).suffix.lower()
    if ext in config.ARCHIVES:
        return None
    hits = [s for s in SYSTEMS if ext in s["exts"]]
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    return None  # shared extension (.iso, .chd, .bin...): we do not guess


def scan_local(sys_key, cfg=None):
    """Generic inventory of a system: one file is one game."""
    s = get_cfg(sys_key, cfg)
    root = local_dir(sys_key)
    if s["engine"] == "switch" or not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in s["exts"]:
            continue
        # An archive is not a ROM: it is waiting to be extracted. Counting it
        # as a game showed two Switch titles in .zip among the arcade cabinets.
        if p.suffix.lower() in config.ARCHIVES:
            continue
        from . import meta
        fiche = meta.fiche_nom(p.name, cfg, reseau=False)   # cache only: never any network here
        out.append({
            "path": str(p),
            "rel": str(p.relative_to(config.LUDO)),
            "name": pretty_name(p.name),
            **_fiche_legere(fiche),
            "file": p.name,
            "ext": p.suffix.lower().lstrip("."),
            "size": p.stat().st_size,
            "system": s["key"],
        })
    return out


def detect_on_device(cfg):
    """Platforms actually present on the console, with their counts.

    Without this the user had to guess which folders existed and which were
    empty: we read the ROMs root once, then count by extension. One shell
    command, not one per platform.
    """
    from . import device
    racine = roms_root(cfg)
    if not racine or device.state() != "device":
        return {"racine": racine, "connectee": False, "plateformes": []}

    # a single `find` for the whole tree: the rest is local sorting
    fichiers = _lire_arbre(racine, _COMMANDE_FIND % (device._q(racine), device._q(racine)))
    _memoriser_depuis(racine, fichiers)

    out = []
    for s in liste(cfg):
        dossier = device_dir(s["key"], cfg)
        if not dossier:
            continue
        prefixe = dossier.rstrip("/") + "/"
        siens = [f for f in fichiers
                 if f["path"].startswith(prefixe)
                 and any(f["path"].lower().endswith(e) for e in s["exts"])]
        if not siens and not _dossier_existe(fichiers, prefixe):
            continue                      # neither folder nor file: we invent nothing
        out.append({"key": s["key"], "name": s["name"], "folder": s["folder"],
                    "dir": dossier, "count": len(siens),
                    "bytes": sum(f["size"] for f in siens)})
    return {"racine": racine, "connectee": True, "plateformes": out}


def tout(cfg):
    """Every generic platform at once: local games and console files.

    One read of the console for all of them, instead of one per platform:
    essential to show the whole library without making the user wait.
    """
    from . import device, meta
    racine = roms_root(cfg)
    distants = []
    if racine and device.state() == "device":
        distants = _lire_arbre(racine, _COMMANDE_FIND % (device._q(racine), device._q(racine)))
        _memoriser_depuis(racine, distants)

    out = []
    for s in liste(cfg):
        if s["engine"] == "switch":
            continue                       # gere par scan.Library
        dossier = device_dir(s["key"], cfg)
        prefixe = (dossier.rstrip("/") + "/") if dossier else None
        siens = []
        if prefixe:
            # The same official title as in the per-platform view: without it,
            # the "all platforms" view fell back to the file name.
            siens = [{"nom": f["name"], "chemin": f["path"], "taille": f["size"],
                      **_fiche_legere(meta.fiche_nom(f["name"], cfg, reseau=False))}
                     for f in distants
                     if f["path"].startswith(prefixe)
                     and any(f["path"].lower().endswith(e) for e in s["exts"])
                     and not any(f["path"].lower().endswith(a) for a in config.ARCHIVES)]
        locaux = scan_local(s["key"], cfg)
        if not locaux and not siens:
            continue                       # platform absent on both sides
        out.append({"key": s["key"], "name": s["name"], "folder": s["folder"],
                    "games": locaux, "console": siens})
    return out


_COMMANDE_FIND = (
    "find %s -maxdepth 3 -type f -printf '%%s|%%p\\n' 2>/dev/null "
    "|| find %s -maxdepth 3 -type f -exec stat -c '%%s|%%n' {} \\; 2>/dev/null")

# A full `find` on the console takes several seconds over Wi-Fi, and it was
# rerun on every page load. We keep the result for a short while: long enough
# that one render queries the console once, short enough not to hide a file you
# just pushed.
_CACHE_ARBRE = {"racine": None, "expire": 0.0, "fichiers": []}
DUREE_CACHE_ARBRE = 20.0


def vider_cache_arbre():
    """Call this as soon as we WRITE to the console: the cache must never
    survive a push or a deletion."""
    _CACHE_ARBRE["expire"] = 0.0


def _lire_arbre(racine, commande):
    import time as _t
    from . import device
    if _CACHE_ARBRE["racine"] == racine and _CACHE_ARBRE["expire"] > _t.monotonic():
        return _CACHE_ARBRE["fichiers"]
    fichiers = device.parse_find(device._shell(commande, timeout=180))
    _CACHE_ARBRE.update({"racine": racine, "fichiers": fichiers,
                         "expire": _t.monotonic() + DUREE_CACHE_ARBRE})
    return fichiers


def _fiche_legere(f):
    """What a game's card needs to know: title, summary, year.

    The rest of the record (identifiers, urls) has no business in a response
    sent for every single game.
    """
    f = f or {}
    return {"titre": f.get("nom", ""), "resume": f.get("resume", ""),
            "annee": f.get("annee", ""), "editeur": f.get("editeur", ""),
            # The summary's provenance travels with it: citing the source is
            # not optional when the text comes from Wikipedia.
            "source_resume": f.get("source_resume", ""),
            "url_resume": f.get("url_resume", "")}


def _memoriser_depuis(racine, fichiers):
    """Top-level folder names seen in the tree we read."""
    base = racine.rstrip("/") + "/"
    noms = {p[len(base):].split("/", 1)[0]
            for p in (f.get("path") or "" for f in fichiers) if p.startswith(base)}
    memoriser_dossiers(noms)


def _dossier_existe(fichiers, prefixe):
    return any(f["path"].startswith(prefixe) for f in fichiers)


def summary(cfg):
    """The systems with their local game counts (for the selector)."""
    out = []
    for s in liste(cfg):
        if s["engine"] == "switch":
            n = None          # compte fourni par scan.Library
        else:
            n = len(scan_local(s["key"], cfg))
        out.append({"key": s["key"], "name": s["name"], "folder": s["folder"],
                    "engine": s["engine"], "count": n,
                    "device_dir": device_dir(s["key"], cfg)})
    return out
