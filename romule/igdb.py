"""Fiches de jeu pour les plateformes autres que la Switch, via IGDB.

nlib ne connait que la Switch, et SteamGridDB ne sert que des visuels et des
titres. IGDB est la seule base gratuite qui couvre toutes les plateformes avec
un resume redige. L'acces demande un identifiant Twitch (gratuit) :

    1. https://dev.twitch.tv/console/apps  -> « Register Your Application »
    2. noter le Client ID et le Client Secret
    3. les coller dans Reglages > Jaquettes et fiches

Sans ces identifiants le module reste inerte : il ne bloque rien, il ne
telecharge rien, et l'outil se comporte comme avant.

Le jeton d'acces est obtenu par « client credentials » et garde en memoire
jusqu'a son expiration : IGDB limite le nombre de demandes de jeton.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config, reseau
from . import rapprochement

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.igdb.com/v4"

_JETON = {"valeur": "", "expire": 0.0}
_LOCK = threading.Lock()
_ECHECS = set()          # noms cherches en vain : on ne reessaie pas en boucle


def configure(cfg=None):
    cfg = cfg or config.load_config()
    return (bool((cfg.get("igdb_client_id") or "").strip())
            and bool((cfg.get("igdb_client_secret") or "").strip()))


def _base(cfg):
    """Adresse de base, surchargeable pour les tests."""
    return (cfg.get("igdb_url") or "").strip().rstrip("/") or API_URL


def _url_jeton(cfg):
    return (cfg.get("igdb_token_url") or "").strip() or TOKEN_URL


def jeton(cfg=None, force=False):
    """Jeton d'application, renouvele seulement quand il expire."""
    cfg = cfg or config.load_config()
    if not configure(cfg):
        return ""
    with _LOCK:
        if not force and _JETON["valeur"] and _JETON["expire"] > time.time() + 60:
            return _JETON["valeur"]
        donnees = urllib.parse.urlencode({
            "client_id": cfg["igdb_client_id"].strip(),
            "client_secret": cfg["igdb_client_secret"].strip(),
            "grant_type": "client_credentials",
        }).encode()
        try:
            req = urllib.request.Request(_url_jeton(cfg), data=donnees)
            with reseau.ouvrir(req, timeout=15) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            return ""
        _JETON["valeur"] = d.get("access_token", "")
        _JETON["expire"] = time.time() + float(d.get("expires_in", 3600))
        return _JETON["valeur"]


# IGDB accepte 4 requetes par seconde. Sans espacement, une recuperation de
# 80 fiches en envoie 80 d'un coup : la moitie repart en 429, et ces echecs
# etaient ensuite pris pour des « jeu introuvable ».
INTERVALLE = 0.26
_DERNIERE = [0.0]
# Verrou distinct : dormir en tenant celui du jeton bloquerait tout le reste.
_RYTHME = threading.Lock()


def _attendre_son_tour():
    with _RYTHME:
        creux = INTERVALLE - (time.monotonic() - _DERNIERE[0])
        if creux > 0:
            time.sleep(creux)
        _DERNIERE[0] = time.monotonic()


def _requete(cfg, chemin, corps, essais=3):
    """Renvoie la liste des resultats, ou None si la requete a ECHOUE.

    La distinction compte : une liste vide veut dire « ce jeu n'existe pas chez
    IGDB » et merite d'etre memorisee ; None veut dire « on n'a pas pu
    demander » et doit pouvoir etre reessaye.
    """
    t = jeton(cfg)
    if not t:
        return None
    for essai in range(essais):
        _attendre_son_tour()
        req = urllib.request.Request(
            _base(cfg) + "/" + chemin, data=corps.encode("utf-8"),
            headers={"Client-ID": cfg["igdb_client_id"].strip(),
                     "Authorization": "Bearer " + t,
                     "Accept": "application/json"})
        try:
            with reseau.ouvrir(req, timeout=20) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            return d if isinstance(d, list) else []
        except urllib.error.HTTPError as exc:
            if exc.code == 401:                 # jeton perime avant l'heure
                t = jeton(cfg, force=True)
                continue
            if exc.code == 429:                 # trop vite : on laisse retomber
                time.sleep(1.0 + essai)
                continue
            return None
        except Exception:
            return None
    return None


def _echapper(s):
    return str(s or "").replace('"', " ").replace("\\", " ")


def chercher(nom, cfg=None):
    """Fiche d'un jeu : {nom, resume, annee, editeur} ou None.

    On demande le resume court (`summary`) plutot que l'article complet
    (`storyline`) : sur une carte de jeu, trois lignes valent mieux qu'un
    paragraphe tronque.
    """
    cfg = cfg or config.load_config()
    if not configure(cfg) or not (nom or "").strip():
        return None
    cle = nom.strip().lower()
    with _LOCK:
        if cle in _ECHECS:
            return None
    corps = ('search "%s"; fields name,summary,category,first_release_date,'
             'involved_companies.company.name,involved_companies.publisher; '
             'limit 10;' % _echapper(nom))
    jeux = _requete(cfg, "games", corps)
    if jeux is None:
        return None                    # echec technique : on reessaiera
    if not jeux:
        with _LOCK:
            _ECHECS.add(cle)           # vraiment introuvable
        return None
    j = _meilleur(jeux, nom)
    if j is None:
        with _LOCK:
            _ECHECS.add(cle)
        return None
    editeur = ""
    for ic in (j.get("involved_companies") or []):
        if ic.get("publisher") and (ic.get("company") or {}).get("name"):
            editeur = ic["company"]["name"]
            break
    annee = ""
    if j.get("first_release_date"):
        try:
            annee = time.strftime("%Y", time.gmtime(int(j["first_release_date"])))
        except (ValueError, OSError):
            annee = ""
    return {"nom": j.get("name") or "", "resume": (j.get("summary") or "").strip(),
            "annee": annee, "editeur": editeur}


# Noms de plateformes chez IGDB -> cles de l'outil. IGDB en connait des
# centaines ; on ne mappe que celles qu'on sait ranger.
_PLATEFORMES = {
    "nintendo switch": "switch", "nintendo switch 2": "switch",
    "playstation 2": "ps2", "playstation": "psx", "playstation 3": "ps3",
    "playstation portable": "psp", "playstation vita": "psvita",
    "nintendo gamecube": "gamecube", "wii": "wii", "wii u": "wiiu",
    "nintendo 3ds": "3ds", "new nintendo 3ds": "3ds",
    "nintendo ds": "nds", "nintendo dsi": "nds",
    "nintendo 64": "n64", "super nintendo entertainment system": "snes",
    "super famicom": "snes", "nintendo entertainment system": "nes",
    "family computer": "nes",
    "game boy advance": "gba", "game boy": "gb", "game boy color": "gb",
    "dreamcast": "dreamcast", "sega saturn": "saturn",
    "sega mega drive/genesis": "megadrive", "sega mega drive": "megadrive",
    "sega genesis": "megadrive",
    "xbox": "xbox", "xbox 360": "xbox360", "pc (microsoft windows)": "pc",
    "arcade": "arcade", "neo geo": "arcade",
}


def plateformes(nom, cfg=None):
    """Plateformes sur lesquelles ce jeu est sorti, d'apres IGDB.

    Sert a trancher quand l'extension ne suffit pas : un `.iso` peut etre une
    PS2, une Wii ou une Xbox, mais « Metal Gear Solid 3 » n'est sorti que sur
    l'une d'elles.
    """
    cfg = cfg or config.load_config()
    if not configure(cfg) or not (nom or "").strip():
        return []
    jeux = _requete(cfg, "games",
                    'search "%s"; fields name,platforms.name; limit 3;'
                    % _echapper(nom))
    if not jeux:
        return []
    vues, out = set(), []
    for j in jeux:
        for pf in (j.get("platforms") or []):
            cle = _PLATEFORMES.get((pf.get("name") or "").strip().lower())
            if cle and cle not in vues:
                vues.add(cle)
                out.append(cle)
    return out


# Categories IGDB : 0 = jeu principal, 3 = compilation, 5 = mod, 6 = fan game…
# Le premier resultat d'une recherche est souvent un HACK portant presque le
# meme nom : « Castlevania: Aria of Sorrow » ramenait ainsi le resume d'une
# version modifiee. On privilegie donc le jeu principal, puis le titre le plus
# proche.
JEU_PRINCIPAL = 0
_MOTS = __import__("re").compile(r"[a-z0-9]+")


def _tokens(t):
    return set(_MOTS.findall((t or "").lower()))


def _meilleur(jeux, cherche):
    vise = _tokens(cherche)
    if not vise:
        return jeux[0] if jeux else None

    def score(j):
        t = _tokens(j.get("name"))
        commun = len(vise & t)
        # un titre qui ajoute beaucoup de mots (« … Randomizer », « … Hack »)
        # s'eloigne de ce qu'on cherche
        penalite = len(t - vise)
        principal = 1 if j.get("category", JEU_PRINCIPAL) == JEU_PRINCIPAL else 0
        avec_resume = 1 if (j.get("summary") or "").strip() else 0
        return (principal, commun - penalite * 0.5, avec_resume,
                -(j.get("category") or 0))

    retenu = max(jeux, key=score)
    # « Au moins un mot en commun » etait trop permissif : « Crazy » passait
    # pour « Crazy Construction ». Il faut couvrir la MAJORITE des mots
    # distinctifs — meme regle que pour SteamGridDB, meme raison.
    return retenu if rapprochement.assez_proche(retenu.get("name"), cherche) else None


def tester(cfg=None):
    """Verifie que les identifiants fonctionnent, sans rien enregistrer."""
    cfg = cfg or config.load_config()
    if not configure(cfg):
        raise ValueError("Client ID et Client Secret Twitch sont necessaires.")
    if not jeton(cfg, force=True):
        raise ValueError("Twitch a refuse ces identifiants.")
    essai = chercher("The Legend of Zelda", cfg)
    return {"jeton": True, "exemple": (essai or {}).get("nom") or "(aucun resultat)"}
