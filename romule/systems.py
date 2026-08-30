"""Systemes de jeu geres par l'outil.

Le Switch a son moteur dedie (title IDs, nsz, titledb, GAMES/UPDATE/DLC) : il
reste traite par scan.Library. Les autres systemes utilisent un moteur
"generique" beaucoup plus simple : un fichier = un jeu, pas de mise a jour ni
de DLC, jaquette cherchee par nom.

Rangement local :
  - switch    : a la racine de la ludotheque (GAMES/UPDATE/DLC) — historique
  - les autres: <racine>/<folder>/   (ex. PS2/, Dreamcast/)

Rangement console : <roms_root>/<folder>  (ex. .../emulation/ROMs/PS2)
"""

import re
from pathlib import Path

from . import config

# Extensions courantes par systeme. Volontairement large : mieux vaut proposer
# que rater un fichier. Les archives sont gerees en amont (_import).
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

# Les noms de dossier ne sont pas normalises : chaque frontal (EmulationStation,
# RetroArch, Daijisho, Pegasus...) a ses habitudes. Un dossier « PS1 » ou
# « Sega » n'etait rattache a aucune plateforme, donc ses jeux restaient
# invisibles — 85 titres dans le cas rencontre. On reconnait donc les
# appellations courantes, sans obliger l'utilisateur a renommer quoi que ce soit.
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

    Renvoie None si le nom n'evoque rien de connu : mieux vaut demander que
    ranger un dossier au hasard.
    """
    n = _normaliser(nom)
    if not n:
        return None
    if cfg:
        # un dossier explicitement associe par l'utilisateur prime sur tout
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
    """Plateformes connues : celles livrees, plus celles ajoutees par l'utilisateur.

    Toutes les consoles ne sont pas dans la table livree, et certaines rangent
    leurs jeux d'une facon qu'on ne peut pas deviner. Plutot que d'attendre une
    mise a jour de l'outil, on laisse en declarer une : un nom, un dossier, des
    extensions.
    """
    cfg = cfg or config.load_config()
    out = list(SYSTEMS)
    for p in (cfg.get("systemes_perso") or []):
        cle = str(p.get("key") or "").strip().lower()
        if not cle or cle in BY_KEY:
            continue
        # Les extensions partent dans un `find` execute sur la console : une
        # apostrophe y casserait la mise entre guillemets. On ne garde que des
        # extensions qui ressemblent a des extensions.
        exts = [x for x in (extension_sure(e) for e in (p.get("exts") or [])) if x]
        out.append({"key": cle, "name": p.get("name") or cle,
                    "folder": dossier_sur(p.get("folder"), cle),
                    "engine": "generic",
                    "exts": exts, "perso": True})
    return out


# Un nom de dossier venu de la configuration finit en `config.ROOT / folder`,
# et l'outil DEPLACE des fichiers dedans. « ../.. » y suffisait donc a ranger
# des ROMs n'importe ou sur la machine hote. On n'accepte qu'un nom simple.
_NOM_DOSSIER = re.compile(r"^[^/\\:\x00]{1,64}$")


def dossier_sur(nom, defaut):
    """Nom de dossier utilisable, ou `defaut` si celui propose ne l'est pas."""
    nom = str(nom or "").strip()
    if not nom or nom in (".", "..") or not _NOM_DOSSIER.match(nom):
        return defaut
    return nom


def extension_sure(e):
    """Extension utilisable : elle finit dans des commandes distantes."""
    e = str(e or "").strip().lower()
    if not e:
        return ""
    e = e if e.startswith(".") else "." + e
    return e if re.match(r"^\.[a-z0-9]{1,8}$", e) else ""


def get_cfg(key, cfg=None):
    """Comme get(), mais connait aussi les plateformes ajoutees a la main."""
    for s in liste(cfg):
        if s["key"] == (key or "switch"):
            return s
    return SWITCH

# Nettoyage des noms : (USA), [!], (v1.0.3), tags de scene...
_CLEAN = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")


def get(key):
    return BY_KEY.get(key or "switch", SWITCH)


def pretty_name(filename):
    stem = Path(filename).stem
    return _CLEAN.sub("", stem).replace("_", " ").strip() or stem


def local_dir(sys_key, cfg=None):
    """Dossier local d'un systeme (le Switch reste a la racine, historique).

    `cfg` permet de trouver aussi les plateformes ajoutees a la main : sans lui,
    une ROM d'une plateforme perso n'avait nulle part ou aller.
    """
    s = get_cfg(sys_key, cfg) if cfg else get(sys_key)
    if s["engine"] == "switch":
        return config.ROOT
    chemin = (config.ROOT / s["folder"]).resolve()
    # Ceinture ET bretelles : meme si un nom passait le filtre, le chemin
    # construit ne doit jamais sortir de la ludotheque.
    if not str(chemin).startswith(str(config.ROOT.resolve())):
        raise ValueError("Dossier hors de la ludotheque : %s" % s["folder"])
    return chemin


def device_dir(sys_key, cfg):
    """Dossier de ce systeme sur la console.

    Par defaut <racine>/<Folder>, mais chaque plateforme peut avoir son propre
    nom de dossier : les consoles ne s'accordent pas toutes sur « SNES » plutot
    que « Super Nintendo ». Le reglage vit dans `system_dirs`, et evite d'avoir
    un chemin a saisir pour chacune.
    """
    s = get_cfg(sys_key, cfg)
    if s["engine"] == "switch":
        return (cfg.get("device_dir") or "").rstrip("/")
    root = roms_root(cfg)
    if not root:
        return ""
    perso = (cfg.get("system_dirs") or {}).get(sys_key, "").strip()
    # Un chemin absolu prime : les consoles ne rangent pas toutes leurs ROMs sous
    # une meme racine, et certaines nomment les dossiers autrement (« PS1 » plutot
    # que « PSX », « Sega » plutot que « MegaDrive »).
    if perso.startswith("/"):
        return perso.rstrip("/")
    if perso:
        return root + "/" + perso.strip("/")
    return root + "/" + _dossier_reel(sys_key, s["folder"])


# Noms de dossiers reellement vus sous la racine des ROMs, memorises lors de la
# derniere lecture de la console. `device_dir` s'en sert pour retrouver un
# dossier qui ne porte pas le nom attendu — « PS1 » pour PSX, « Sega » pour la
# Mega Drive. Sans cela les jeux existent, mais l'outil regarde ailleurs.
_DOSSIERS_REELS = []


def memoriser_dossiers(noms):
    global _DOSSIERS_REELS
    _DOSSIERS_REELS = sorted({n for n in noms if n})


def _dossier_reel(sys_key, defaut):
    if not _DOSSIERS_REELS:
        return defaut
    reels = {_normaliser(n): n for n in _DOSSIERS_REELS}
    if _normaliser(defaut) in reels:
        return reels[_normaliser(defaut)]     # le nom attendu existe : rien a faire
    for norme, nom in sorted(reels.items()):
        if _INDEX_ALIAS.get(norme) == sys_key:
            return nom                        # un alias connu pointe vers nous
    return defaut


def roms_root(cfg):
    """Racine des ROMs sur la console : configuree, ou deduite du dossier Switch."""
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
    """Toutes les extensions deposables : celles de TOUTES les plateformes,
    plus les archives.

    Le depot n'acceptait que les formats Switch. Une ROM GBA ou une image PS2
    etait refusee alors que l'outil sait parfaitement ou la ranger — et une
    plateforme ajoutee a la main declare ses propres extensions, qu'on ne peut
    pas connaitre a l'avance.
    """
    exts = set(config.ARCHIVES)
    for s in liste(cfg):
        for e in (s.get("exts") or []):
            e = str(e).strip().lower()
            if e:
                exts.add(e if e.startswith(".") else "." + e)
    return exts


def system_for_file(filename):
    """Devine le systeme d'un fichier d'apres son extension (None si ambigu).

    Les formats d'archive (.zip, .7z, .rar) ne sont JAMAIS attribues a une
    plateforme, meme si une seule les declare : un .zip est presque toujours un
    jeu compresse a extraire. Deux jeux Switch telecharges en .zip s'etaient
    ainsi retrouves ranges parmi les ROMs d'arcade.
    """
    ext = Path(filename).suffix.lower()
    if ext in config.ARCHIVES:
        return None
    hits = [s for s in SYSTEMS if ext in s["exts"]]
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    return None  # extension partagee (.iso, .chd, .bin...) : on ne devine pas


def scan_local(sys_key, cfg=None):
    """Inventaire generique d'un systeme : un fichier = un jeu."""
    s = get_cfg(sys_key, cfg)
    root = local_dir(sys_key)
    if s["engine"] == "switch" or not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in s["exts"]:
            continue
        # Une archive n'est pas une ROM : elle attend d'etre extraite. La compter
        # comme un jeu affichait deux jeux Switch en .zip parmi les bornes d'arcade.
        if p.suffix.lower() in config.ARCHIVES:
            continue
        from . import meta
        fiche = meta.fiche_nom(p.name, cfg, reseau=False)   # cache seul : jamais de reseau ici
        out.append({
            "path": str(p),
            "rel": str(p.relative_to(config.ROOT)),
            "name": pretty_name(p.name),
            **_fiche_legere(fiche),
            "file": p.name,
            "ext": p.suffix.lower().lstrip("."),
            "size": p.stat().st_size,
            "system": s["key"],
        })
    return out


def detect_on_device(cfg):
    """Plateformes reellement presentes sur la console, avec leur decompte.

    Sans cela, l'utilisateur devait deviner quels dossiers existaient et lesquels
    etaient vides : on lit une fois la racine des ROMs, puis on compte par
    extension. Une seule commande shell, pas une par plateforme.
    """
    from . import device, meta
    racine = roms_root(cfg)
    if not racine or device.state() != "device":
        return {"racine": racine, "connectee": False, "plateformes": []}

    # un seul `find` pour tout l'arbre : le reste est du classement local
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
            continue                      # ni dossier ni fichier : on n'invente pas
        out.append({"key": s["key"], "name": s["name"], "folder": s["folder"],
                    "dir": dossier, "count": len(siens),
                    "bytes": sum(f["size"] for f in siens)})
    return {"racine": racine, "connectee": True, "plateformes": out}


def tout(cfg):
    """Toutes les plateformes generiques d'un coup : jeux locaux et fichiers console.

    Une seule lecture de la console pour l'ensemble, au lieu d'une par
    plateforme : indispensable pour afficher la ludotheque complete sans faire
    attendre l'utilisateur.
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
            # Meme titre officiel que dans la vue par plateforme : sans lui, la
            # vue « toutes les plateformes » retombait sur le nom de fichier.
            siens = [{"nom": f["name"], "chemin": f["path"], "taille": f["size"],
                      **_fiche_legere(meta.fiche_nom(f["name"], cfg, reseau=False))}
                     for f in distants
                     if f["path"].startswith(prefixe)
                     and any(f["path"].lower().endswith(e) for e in s["exts"])
                     and not any(f["path"].lower().endswith(a) for a in config.ARCHIVES)]
        locaux = scan_local(s["key"], cfg)
        if not locaux and not siens:
            continue                       # plateforme absente des deux cotes
        out.append({"key": s["key"], "name": s["name"], "folder": s["folder"],
                    "games": locaux, "console": siens})
    return out


_COMMANDE_FIND = (
    "find %s -maxdepth 3 -type f -printf '%%s|%%p\\n' 2>/dev/null "
    "|| find %s -maxdepth 3 -type f -exec stat -c '%%s|%%n' {} \\; 2>/dev/null")

# Le `find` complet sur la console prend plusieurs secondes en Wi-Fi, et il
# etait relance a chaque lecture de page. On garde le resultat un court
# instant : assez pour qu'un affichage n'interroge la console qu'une fois,
# trop peu pour masquer un fichier qu'on vient d'envoyer.
_CACHE_ARBRE = {"racine": None, "expire": 0.0, "fichiers": []}
DUREE_CACHE_ARBRE = 20.0


def vider_cache_arbre():
    """A appeler des qu'on ECRIT sur la console : le cache ne doit jamais
    survivre a un envoi ou a une suppression."""
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
    """Ce que la carte d'un jeu a besoin de savoir : titre, resume, annee.

    Le reste de la fiche (identifiants, url) n'a rien a faire dans une reponse
    envoyee pour chaque jeu.
    """
    f = f or {}
    return {"titre": f.get("nom", ""), "resume": f.get("resume", ""),
            "annee": f.get("annee", ""), "editeur": f.get("editeur", "")}


def _memoriser_depuis(racine, fichiers):
    """Noms de dossiers de premier niveau vus dans l'arborescence lue."""
    base = racine.rstrip("/") + "/"
    noms = {p[len(base):].split("/", 1)[0]
            for p in (f.get("path") or "" for f in fichiers) if p.startswith(base)}
    memoriser_dossiers(noms)


def _dossier_existe(fichiers, prefixe):
    return any(f["path"].startswith(prefixe) for f in fichiers)


def summary(cfg):
    """Liste des systemes avec le nombre de jeux locaux (pour le selecteur)."""
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
