"""Chemins, constantes et configuration persistante."""

import ipaddress
import json
import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
STATIC = PKG / "static"

# -------------------------------------------------------------------- ROOT
# The library — games, cover art, accounts, logs — lives in a folder SEPARATE
# from the code. It used to be `PKG.parent`, that is, the folder containing the
# package: the code therefore ended up installed among the games, and the
# application wrote its state into its own sources. While the tool had one
# user that passed; for a public repository it is a trap — anyone cloning the
# project sees their library turn up in `git status`, and one `git add` carries
# off their console keys.
#
# Order of preference, from most explicit to most implicit:
#   1. ROMULE_ROOT   — the project's name
#   2. SWITCH_ROOT   — the old name, still accepted
#   3. ~/.local/share/romule (or XDG_DATA_HOME), created if needed
def _racine_par_defaut():
    base = os.environ.get("XDG_DATA_HOME", "").strip()
    return Path(base or (Path.home() / ".local" / "share")) / "romule"


# The project's variables are named ROMULE_*. The old SWITCH_* ones are still
# read: someone upgrading must not see their service stop because a name
# changed. They are reported once at startup.
ANCIENNES_UTILISEES = []


def env(nom, defaut=""):
    """The value of ROMULE_<name>, or of SWITCH_<name> if only that one is set."""
    v = os.environ.get("ROMULE_" + nom)
    if v is not None:
        return v
    v = os.environ.get("SWITCH_" + nom)
    if v is not None:
        ANCIENNES_UTILISEES.append("SWITCH_" + nom)
        return v
    return defaut


def env_bool(nom):
    return env(nom, "").strip().lower() in ("1", "true", "yes", "on")


ROOT = Path(env("ROOT") or _racine_par_defaut()).expanduser().resolve()


def racine_douteuse(chemin=None):
    """Does the root point somewhere nothing should be written?

    The application moves files and creates folders. A mis-set root is not an
    inconvenience: it is data loss. So we refuse the locations we are sure are
    not a game library.
    """
    c = Path(chemin or ROOT).resolve()
    if c == Path(c.anchor):
        return "la racine du disque"
    if c == Path.home().resolve():
        return "le dossier personnel"
    # `os.path.isdir` rather than `Path.is_dir`: the former returns False when
    # it cannot look, the latter raises. And this is a HEURISTIC — being unable
    # to read the folder does not make it a code repository, and an exception
    # here killed startup before the check that does know how to explain.
    if os.path.isdir(c / "romule") or os.path.isdir(c / ".git"):
        return "un depot de code (le code et les jeux doivent rester separes)"
    return ""


def en_conteneur():
    """Containerised deployment? The remedy to offer is not the same."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup") as fh:
            return any(k in fh.read() for k in ("docker", "kubepods", "containerd"))
    except OSError:
        return False

# ----------------------------------------------------------------- LIBRARY
# `ROOT` conflated two things of different natures.
#
#   * THE SERVICE'S WORKSPACE — configuration, accounts, logs, cover art,
#     caches, backups. It is fixed by the deployment: a volume in a container,
#     an XDG folder natively. Moving it means changing installation.
#   * THE LIBRARY — the games. That is user data. It often lives on another
#     disk, and it is the one you want to be able to point at from the
#     interface without editing a compose file.
#
# Conflating them forced you to choose your games folder through an environment
# variable, and changing your mind lost your accounts along the way. Every
# self-hosted tool separates the two: the data folder comes from the
# deployment, libraries are added from the settings screen.
#
# By default the library IS the root: an existing installation sees no
# difference, and nothing moves on its own.
LUDO_IMPOSEE = bool(env("LIBRARY").strip())
LUDO = Path(env("LIBRARY").strip() or ROOT).expanduser().resolve()

# Folders the interface may enter, separated like a PATH.
# Empty — the default — means "everything the process can see", which is how
# self-hosted tools behave: in a container the boundary is the kernel-enforced
# `volumes:`; natively it is the service's Unix account. Declaring it stays
# useful to anyone installing natively under a broad account.
#
# This check lives HERE, and not in the browsing module, because confining the
# browsing dialog is not enough: without it, one could still TYPE a path
# outside the bases and settle there. Every file operation then followed the
# library outside the declared perimeter, and the confinement was no more than
# a display inconvenience.
BASES = [Path(b).expanduser().resolve()
         for b in env("BASES").split(os.pathsep) if b.strip()]


def dans_les_bases(chemin):
    """Is the path inside the declared bases? True when none is declared."""
    if not BASES:
        return True
    c = Path(chemin).resolve()
    return any(c == b or b in c.parents for b in BASES)

# Problems met while reading the configuration, reported at startup.
# They do not justify refusing to start: a path gone invalid — an external disk
# unplugged — must leave the service reachable, otherwise you cannot even log
# in to fix it.
PROBLEMES = []


def _chemins_ludotheque():
    """Recompute what must follow the games rather than the service's state.

    The trash and the drop folder live NEXT TO the games, not next to the
    configuration. Across filesystems, `shutil.move` stops being a rename and
    copies instead: fifteen gigabytes to set one title aside.
    """
    global TRASH, IMPORT
    TRASH = LUDO / "_corbeille"
    IMPORT = LUDO / "_import"


def definir_ludotheque(chemin, creer=False):
    """Change the scanned folder. Returns "" or the reason for refusal.

    A refusal always states why: this path is typed by a human in a settings
    dialog, and "failed" with no reason leaves them with no recourse.
    """
    global LUDO
    if LUDO_IMPOSEE:
        return "la ludotheque est imposee par ROMULE_LIBRARY"
    brut = str(chemin or "").strip()
    if not brut:
        # Returning to the default is a legitimate operation, not an error.
        LUDO = ROOT
        _chemins_ludotheque()
        return ""
    c = Path(brut).expanduser()
    if not c.is_absolute():
        return "il faut un chemin absolu"
    if creer and not c.exists():
        try:
            c.mkdir(parents=True)
        except OSError as exc:
            return "creation impossible : %s" % exc
    if not c.is_dir():
        return "ce dossier n'existe pas"
    c = c.resolve()
    douteux = racine_douteuse(c)
    if douteux:
        return "emplacement refuse : %s" % douteux
    if not dans_les_bases(c):
        return "hors des dossiers autorises (ROMULE_BASES)"
    # Romule moves and converts files. Accepting a read-only folder promises a
    # service that will fail on its first action.
    if not os.access(c, os.W_OK):
        return "dossier en lecture seule"
    LUDO = c
    _chemins_ludotheque()
    return ""


TRASH = LUDO / "_corbeille"
IMPORT = LUDO / "_import"
VCACHE = ROOT / "_cache_versions.txt"
# Title IDs already read from inside containers. Each read runs `nsz`, about a
# quarter of a second per badly named file — and that cost was paid on every
# page render, for a result that never changes while the file does not.
TIDCACHE = ROOT / "_cache_conteneurs.json"
NAND_LIST = ROOT / "_a_installer_dans_NAND.txt"


def fichier_etat(nom, ancien_nom):
    """Path of a state file, picking up the old name if it still exists.

    State files used to carry the previous project's name. Settling for the new
    name means making anyone who upgrades lose their configuration and their
    accounts: the service would restart on a blank installation without saying
    so. The rename happens once, and its failure is not a fault — we simply go
    on reading where the data is.
    """
    neuf = ROOT / nom
    ancien = ROOT / ancien_nom
    # `exists()` can raise: a folder the process may not even enter refuses
    # the `stat`. This function runs at module IMPORT time — an exception here
    # kills the program before anyone could explain anything, and the user
    # reads a stack trace instead of the remedy. We return the new path and let
    # the startup check do its job.
    try:
        if neuf.exists() or not ancien.exists():
            return neuf
    except OSError:
        return neuf
    try:
        ancien.rename(neuf)
        return neuf
    except OSError:
        return ancien


LOGFILE = fichier_etat("_romule-lib.log", "_switch-lib.log")
CONFIG_FILE = fichier_etat("_romule-config.json", "_switch-config.json")

EXTS = {".nsz", ".xcz", ".nsp", ".xci"}
COMPRESSED = {".nsz", ".xcz"}
PLAYABLE = {".nsp", ".xci"}

# Folders never to walk during the library scan.
IGNORE_DIRS = {"_corbeille", "_import", "_covers", "_saves", "romule", ".git"}

PORT = int(env("WEB_PORT", "8787"))

# Service deployment (NAS, Docker): rules set by the environment.
#   ROMULE_LAN=1     lets devices on the network in from startup
#   ROMULE_TOKEN=... requires this token for any remote access (recommended 24/7)
#   ROMULE_ROOT=...  where the library lives
ENV_LAN = env_bool("LAN")
TOKEN = env("TOKEN").strip()

# Addresses of the reverse proxies allowed to speak for their clients.
# Without this declaration an `X-Forwarded-For` header proves nothing: anyone
# can write it. With it, and only from those addresses, the application agrees
# to read the client's real address.
#     ROMULE_TRUSTED_PROXIES=127.0.0.1,172.18.0.1
# Ceiling on a file dropped by the browser. Generous: a Switch image commonly
# exceeds 15 GiB. But a generous ceiling is still a ceiling — without it, any
# authorised device could fill the host's disk.
TELEVERSEMENT_MAX = int(env("UPLOAD_MAX", 64 * 2 ** 30))
# We also refuse to write if the disk would drop below this threshold.
DISQUE_MARGE = int(env("DISK_MARGIN", 2 * 2 ** 30))

# Example tokens: leaving them in place amounts to having no token at all, and
# that is the default anyone gets who copies the compose file without reading
# it.
# Where prod.keys lives. It used to be pinned to ~/.switch/prod.keys, which
# survives neither a container running as another user, nor someone who keeps
# their keys elsewhere.
def _cles_par_defaut():
    """~/.romule/prod.keys, or the old ~/.switch/prod.keys if it still exists.

    Changing a default location without looking at the old one breaks the
    installation of everyone who upgrades.
    """
    neuf = Path.home() / ".romule" / "prod.keys"
    ancien = Path.home() / ".switch" / "prod.keys"
    return ancien if (ancien.exists() and not neuf.exists()) else neuf


CLES = Path(env("KEYS") or _cles_par_defaut()).expanduser()

# fuite:ok this list IS the guard against these values: it has to quote them
JETONS_INTERDITS = {"change-moi", "changeme", "change-me", "secret", "token",
                    "colle-le-ici", "a-changer", "tondejeton"}

_DECLARES = {a.strip() for a in env("TRUSTED_PROXIES").split(",") if a.strip()}


def _reseaux_de_confiance(entrees):
    """The entries written in CIDR, converted once and for all.

    Exact string comparison was enough while you wrote `127.0.0.1`. It stopped
    being enough the moment a container was involved: Docker assigns the
    proxy's address dynamically, so the setting the documentation recommends
    became impractical in the deployment it recommends — you had to read an
    address after every `docker compose up`, and fix it when it changed.

    So `172.16.0.0/12` is accepted alongside `127.0.0.1`. Both forms coexist:
    an existing installation has nothing to change.
    """
    reseaux = []
    for entree in entrees:
        if "/" not in entree:
            continue
        try:
            reseaux.append(ipaddress.ip_network(entree, strict=False))
        except ValueError:
            # An unreadable entry must above all not become permissive.
            # We report it at startup and ignore it.
            PROBLEMES.append("ROMULE_TRUSTED_PROXIES : %r n'est pas un reseau "
                             "valide, entree ignoree" % entree)
    return reseaux


RESEAUX_CONFIANCE = _reseaux_de_confiance(_DECLARES)
# CIDR entries are REMOVED from the set of exact addresses. Without that, the
# string "172.16.0.0/12" would sit in it verbatim — and `_client_reel()`
# compares the links of `X-Forwarded-For`, which come from the client. Writing
# that string into the header would have been enough to pass for a declared
# relay, hence to choose which link Romule keeps.
PROXYS_CONFIANCE = {a for a in _DECLARES if "/" not in a}


def proxy_de_confiance(adresse):
    """Is this the address of a declared relay?

    The default is ALWAYS refusal: with no declaration, no forwarded header is
    worth anything. It is the only safe answer, because an `X-Forwarded-For`
    can be written by hand by anybody.
    """
    if not adresse:
        return False
    if adresse in PROXYS_CONFIANCE:
        return True
    if not RESEAUX_CONFIANCE:
        return False
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    return any(ip in reseau for reseau in RESEAUX_CONFIANCE)

# titledb: an ordered list; we try each mirror until one answers.
VERSIONS_URLS = [
    "https://raw.githubusercontent.com/blawar/titledb/master/versions.txt",
]

DEFAULTS = {
    # Target emulator. What used to be pinned to Eden — package name, paths,
    # settings format — now comes from romule/profils/*.json.
    "emulateur": "eden",
    "emulateur_paquet": "",     # filled in by detection on the console
    "device_dir": "/storage/emulated/0/Switch",  # where the emulator reads its games
    "jobs": 3,                                    # parallel conversions
    "push_layout": "type",                        # type | game | flat (see device.py)
    "verify_mode": "size",                        # none | size | hash (after push)
    "incremental": True,                          # only push what is missing or differs
    "cover_provider": "nlib",                     # nlib | steamgriddb | custom
    "cover_url": "https://api.nlib.cc/nx/{tid}/icon/256/256",  # provider custom
    "steamgriddb_key": "",                        # API key when the provider is steamgriddb
    # IGDB (through Twitch): the only free source of SUMMARIES for platforms
    # other than the Switch. Empty = feature inactive, nothing is called.
    "igdb_client_id": "",
    "igdb_client_secret": "",
    # English by default: it is the language of a public self-hosted project.
    # French is still shipped, and is chosen in the settings.
    "meta_lang": "en",                            # language of the game details (nlib)
    "local_layout": "type",                       # local filing: type | game
    "versions_urls": list(VERSIONS_URLS),         # titledb mirrors, tried in order
    "lan_access": False,                          # open the interface to the local network
    "notify": True,                               # macOS notification when a task ends
    "notif_destinations": [],                     # Discord, Slack, Telegram, ntfy, Gotify, webhook
    "roms_root": "",                              # ROMs root on the console (multi-system)
    "saves_dir": "",                              # save folder on the console
    "wifi_addr": "",                              # the console's last Wi-Fi address
    "emuready": False,                            # reglages communautaires (beta)
    "emuready_device": "",                        # identifiant de MA variante de console
    "emuready_device_nom": "",                    # its readable name
    "ui_lang": "en",                              # interface language
    "auto_nand": False,                           # activate updates/DLC as soon as they arrive
    "trash_days": 0,                              # auto-purge of the trash (0 = never)
    "system_dirs": {},                            # folder name per platform, when different
    "systemes_perso": [],                         # hand-added platforms
    # The scanned folder. Empty = the service root, that is, the previous
    # behaviour: nobody sees their inventory change on upgrading.
    "library_path": "",
    # --- authentification : "aucun" (defaut) ou "oidc" (SSO)
    "auth_mode": "aucun",
    "oidc_issuer": "",                            # ex. https://auth.exemple.fr/application/o/ludo/
    "oidc_client_id": "",
    "oidc_client_secret": "",
    "oidc_scopes": "openid profile email",
    "oidc_redirect": "",                          # public address, when behind a proxy
    "oidc_emails": "",                            # allow-list, comma-separated
    "oidc_groupes": "",                           # or by group
    # WHO ADMINISTERS, which is not the same question as WHO MAY ENTER.
    # Empty = no SSO session is an administrator: the default refuses.
    "oidc_admin_groupes": "",
    # Check once a day whether a newer version exists. This is the ONLY
    # outbound call Romule makes unasked; some people self-host precisely so as
    # to talk to nobody.
    "maj_check": True,
    "auth_secret": "",                            # cookie signing key, generated on its own
}

SAVES = ROOT / "_saves"

# Archives accepted in _import (extracted automatically).
ARCHIVES = {".zip", ".7z", ".rar"}

# Target subfolders when push_layout == "type" (Eden's layout).
LAYOUT_FOLDER = {"BASE": "GAMES", "UPDATE": "UPDATE", "DLC": "DLC", "INCONNU": "GAMES"}

COVERS = ROOT / "_covers"


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except (ValueError, OSError):
            pass
    # As a service, the environment has the last word on network access.
    if ENV_LAN or TOKEN:
        cfg["lan_access"] = True
    # The games folder is re-read HERE, and not only at startup: restoring a
    # backup reloads the configuration, and the library must follow.
    if not LUDO_IMPOSEE:
        souci = definir_ludotheque(cfg.get("library_path", ""))
        if souci:
            # The fallback must be EXPLICIT. Without it, a refused path leaves
            # `LUDO` on its previous value: the service would go on working on
            # the old library while announcing the new one.
            definir_ludotheque("")
            # The value stays in the configuration: erasing it would make the
            # user think they never chose anything, when their disk may simply
            # be unplugged.
            avis = ("Ludotheque « %s » inutilisable (%s) — les jeux sont "
                    "cherches dans %s" % (cfg.get("library_path", ""), souci, ROOT))
            if avis not in PROBLEMES:      # `load_config` is called several times
                PROBLEMES.append(avis)
    return cfg


def save_config(cfg):
    # `auth_secret` is created on the fly by auth.py, after the configuration
    # has been loaded: the copy the caller holds therefore may not contain it.
    # Overwriting it with an empty string would change the cookie signing key
    # and log everybody out every time the settings are saved. An empty secret
    # is never allowed to replace an existing one.
    if not cfg.get("auth_secret") and CONFIG_FILE.exists():
        try:
            ancien = json.loads(CONFIG_FILE.read_text()).get("auth_secret")
            if ancien:
                cfg = dict(cfg, auth_secret=ancien)
        except (ValueError, OSError):
            pass
    # Atomic write, with permissions set BEFORE the file takes its final name.
    # Two defects the previous pattern let through:
    #
    #   * `write_text` creates the file with the current umask — often 0644 —
    #     and the `chmod` only came afterwards. In between, the session signing
    #     key, the API keys and the access token were readable by every account
    #     on the machine;
    #   * an interruption mid-write left a truncated file. That loses
    #     `auth_secret` — hence every session — and every setting.
    #
    # `comptes.py` already did it this way for password digests.
    tmp = CONFIG_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, CONFIG_FILE)
        return True
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass          # nothing to clean, or no rights left: of no consequence
        return False
