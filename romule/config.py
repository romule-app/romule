"""Chemins, constantes et configuration persistante."""

import json
import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
STATIC = PKG / "static"

# ----------------------------------------------------------------- LA RACINE
# La ludotheque — jeux, jaquettes, comptes, journaux — vit dans un dossier
# DISTINCT du code. Elle valait auparavant `PKG.parent`, c'est-a-dire le
# dossier qui contient le paquet : le code se retrouvait donc installe au
# milieu des jeux, et l'application ecrivait son etat dans ses propres sources.
# Tant que l'outil n'avait qu'un utilisateur, cela passait ; pour un depot
# public, c'est un piege — quiconque clone le projet voit sa bibliotheque
# apparaitre dans `git status`, et un `git add` emporte ses cles de console.
#
# Ordre retenu, du plus explicite au plus implicite :
#   1. ROMULE_ROOT   — le nom du projet
#   2. SWITCH_ROOT   — l'ancien nom, encore accepte
#   3. ~/.local/share/romule (ou XDG_DATA_HOME), cree au besoin
def _racine_par_defaut():
    base = os.environ.get("XDG_DATA_HOME", "").strip()
    return Path(base or (Path.home() / ".local" / "share")) / "romule"


# Les variables du projet s'appellent ROMULE_*. Les anciennes, SWITCH_*, sont
# encore lues : quelqu'un qui met a jour ne doit pas voir son service s'arreter
# parce qu'un nom a change. Elles sont signalees une fois au demarrage.
ANCIENNES_UTILISEES = []


def env(nom, defaut=""):
    """Valeur de ROMULE_<nom>, ou de SWITCH_<nom> si elle seule est posee."""
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
    """La racine designe-t-elle un endroit ou l'on ne doit rien ecrire ?

    L'application deplace des fichiers et cree des dossiers. Une racine mal
    reglee n'est pas une gene : c'est une perte de donnees. On refuse donc les
    emplacements dont on est sur qu'ils ne sont pas une ludotheque.
    """
    c = Path(chemin or ROOT).resolve()
    if c == Path(c.anchor):
        return "la racine du disque"
    if c == Path.home().resolve():
        return "le dossier personnel"
    if (c / "romule").is_dir() or (c / ".git").is_dir():
        return "un depot de code (le code et les jeux doivent rester separes)"
    return ""

TRASH = ROOT / "_corbeille"
IMPORT = ROOT / "_import"
VCACHE = ROOT / "_cache_versions.txt"
# Title IDs deja lus a l'interieur des conteneurs. Chaque lecture lance `nsz`,
# soit un quart de seconde par fichier mal nomme — et ce cout etait paye a
# chaque affichage de la page, pour un resultat qui ne change jamais tant que
# le fichier ne change pas.
TIDCACHE = ROOT / "_cache_conteneurs.json"
NAND_LIST = ROOT / "_a_installer_dans_NAND.txt"
LOGFILE = ROOT / "_switch-lib.log"
CONFIG_FILE = ROOT / "_switch-config.json"

EXTS = {".nsz", ".xcz", ".nsp", ".xci"}
COMPRESSED = {".nsz", ".xcz"}
PLAYABLE = {".nsp", ".xci"}

# Dossiers a ne jamais parcourir pendant le scan de la ludotheque.
IGNORE_DIRS = {"_corbeille", "_import", "_covers", "_saves", "romule", ".git"}

PORT = int(env("WEB_PORT", "8787"))

# Deploiement en service (NAS, Docker) : regles fixees par l'environnement.
#   ROMULE_LAN=1     autorise les appareils du reseau des le demarrage
#   ROMULE_TOKEN=... exige ce jeton pour tout acces distant (recommande 24/7)
#   ROMULE_ROOT=...  emplacement de la ludotheque
ENV_LAN = env_bool("LAN")
TOKEN = env("TOKEN").strip()

# Adresses des reverse proxys autorises a parler au nom de leurs clients.
# Sans cette declaration, un en-tete `X-Forwarded-For` ne prouve rien :
# n'importe qui peut l'ecrire. Avec elle, et seulement depuis ces adresses,
# l'application accepte de lire la vraie adresse du client.
#     ROMULE_TRUSTED_PROXIES=127.0.0.1,172.18.0.1
# Plafond d'un fichier depose par le navigateur. Genereux : une image Switch
# depasse couramment 15 Gio. Mais un plafond genereux reste un plafond — sans
# lui, tout appareil autorise pouvait remplir le disque de l'hote.
TELEVERSEMENT_MAX = int(env("UPLOAD_MAX", 64 * 2 ** 30))
# On refuse aussi d'ecrire si le disque tomberait sous ce seuil.
DISQUE_MARGE = int(env("DISK_MARGIN", 2 * 2 ** 30))

# Jetons d'exemple : les laisser en place revient a n'avoir aucun jeton, et
# c'est le defaut que prend quiconque copie le fichier compose sans le lire.
# Emplacement de prod.keys. Il etait fige a ~/.switch/prod.keys, ce qui ne
# survit ni a un conteneur tournant sous un autre utilisateur, ni a quelqu'un
# qui range ses cles ailleurs.
def _cles_par_defaut():
    """~/.romule/prod.keys, ou l'ancien ~/.switch/prod.keys s'il existe encore.

    Changer un emplacement par defaut sans regarder l'ancien, c'est casser
    l'installation de ceux qui mettent a jour.
    """
    neuf = Path.home() / ".romule" / "prod.keys"
    ancien = Path.home() / ".switch" / "prod.keys"
    return ancien if (ancien.exists() and not neuf.exists()) else neuf


CLES = Path(env("KEYS") or _cles_par_defaut()).expanduser()

# fuite:ok cette liste EST le garde-fou contre ces valeurs : elle doit les citer
JETONS_INTERDITS = {"change-moi", "changeme", "change-me", "secret", "token",
                    "colle-le-ici", "a-changer", "tondejeton"}

PROXYS_CONFIANCE = {a.strip() for a in env("TRUSTED_PROXIES").split(",")
                    if a.strip()}

# titledb : liste ordonnee, on essaie chaque miroir jusqu'au premier qui repond.
VERSIONS_URLS = [
    "https://raw.githubusercontent.com/blawar/titledb/master/versions.txt",
]

DEFAULTS = {
    # Emulateur cible. Ce qui etait fige sur Eden — nom de paquet, chemins,
    # format des reglages — vient desormais de romule/profils/*.json.
    "emulateur": "eden",
    "emulateur_paquet": "",     # rempli par la detection sur la console
    "device_dir": "/storage/emulated/0/Switch",  # ou l'emulateur lit ses jeux
    "jobs": 3,                                    # conversions en parallele
    "push_layout": "type",                        # type | game | flat (voir device.py)
    "verify_mode": "size",                        # none | size | hash (apres push)
    "incremental": True,                          # ne pousser que ce qui manque/differe
    "cover_provider": "nlib",                     # nlib | steamgriddb | custom
    "cover_url": "https://api.nlib.cc/nx/{tid}/icon/256/256",  # provider custom
    "steamgriddb_key": "",                        # cle API si provider steamgriddb
    # IGDB (via Twitch) : seule source gratuite de RESUMES pour les plateformes
    # autres que la Switch. Vide = fonctionnalite inactive, rien n'est appele.
    "igdb_client_id": "",
    "igdb_client_secret": "",
    # Anglais par defaut : c'est la langue d'un projet auto-heberge public.
    # Le francais reste livre, et se choisit dans les reglages.
    "meta_lang": "en",                            # langue des fiches de jeu (nlib)
    "local_layout": "type",                       # rangement local : type | game
    "versions_urls": list(VERSIONS_URLS),         # miroirs titledb, essayes dans l'ordre
    "lan_access": False,                          # ouvrir l'interface au reseau local
    "notify": True,                               # notification macOS en fin de tache
    "roms_root": "",                              # racine des ROMs sur la console (multi-systemes)
    "saves_dir": "",                              # dossier des sauvegardes sur la console
    "wifi_addr": "",                              # derniere adresse de la console en wifi
    "emuready": False,                            # reglages communautaires (beta)
    "emuready_device": "",                        # identifiant de MA variante de console
    "emuready_device_nom": "",                    # son nom lisible
    "ui_lang": "en",                              # langue de l'interface
    "auto_nand": False,                           # activer MAJ/DLC des qu'ils arrivent
    "trash_days": 0,                              # purge auto de la corbeille (0 = jamais)
    "system_dirs": {},                            # nom de dossier par plateforme, si different
    "systemes_perso": [],                         # plateformes ajoutees a la main
    # --- authentification : "aucun" (defaut) ou "oidc" (SSO)
    "auth_mode": "aucun",
    "oidc_issuer": "",                            # ex. https://auth.exemple.fr/application/o/ludo/
    "oidc_client_id": "",
    "oidc_client_secret": "",
    "oidc_scopes": "openid profile email",
    "oidc_redirect": "",                          # adresse publique, si proxy
    "oidc_emails": "",                            # liste blanche, separee par des virgules
    "oidc_groupes": "",                           # ou par groupes
    "auth_secret": "",                            # signature des cookies, genere seul
}

SAVES = ROOT / "_saves"

# Archives acceptees dans _import (decompressees automatiquement).
ARCHIVES = {".zip", ".7z", ".rar"}

# Sous-dossiers cibles quand push_layout == "type" (organisation pour Eden).
LAYOUT_FOLDER = {"BASE": "GAMES", "UPDATE": "UPDATE", "DLC": "DLC", "INCONNU": "GAMES"}

COVERS = ROOT / "_covers"


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except (ValueError, OSError):
            pass
    # En service, l'environnement a le dernier mot sur l'ouverture reseau.
    if ENV_LAN or TOKEN:
        cfg["lan_access"] = True
    return cfg


def save_config(cfg):
    # `auth_secret` est cree a la volee par auth.py, apres le chargement de la
    # configuration : la copie que detient l'appelant ne le contient donc pas
    # forcement. L'ecraser par une chaine vide changerait la cle de signature
    # des cookies, et deconnecterait tout le monde a chaque enregistrement des
    # reglages. On ne laisse jamais un secret vide remplacer un secret existant.
    if not cfg.get("auth_secret") and CONFIG_FILE.exists():
        try:
            ancien = json.loads(CONFIG_FILE.read_text()).get("auth_secret")
            if ancien:
                cfg = dict(cfg, auth_secret=ancien)
        except (ValueError, OSError):
            pass
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        # Le fichier porte la cle de signature des sessions et les cles d'API :
        # il n'a aucune raison d'etre lisible par les autres comptes de la
        # machine.
        os.chmod(CONFIG_FILE, 0o600)
        return True
    except OSError:
        return False
