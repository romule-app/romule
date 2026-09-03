"""Game details for platforms other than the Switch, via IGDB.

nlib only knows the Switch, and SteamGridDB only serves artwork and titles.
IGDB is the only free database covering every platform with a written summary.
Access needs a (free) Twitch application:

    1. https://dev.twitch.tv/console/apps  -> "Register Your Application"
    2. note the Client ID and the Client Secret
    3. paste them into Settings > Covers and details

Without those credentials the module stays inert: it blocks nothing, downloads
nothing, and the tool behaves exactly as before.

The access token is obtained through "client credentials" and kept in memory
until it expires: IGDB limits how often a token may be requested.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config, net
from . import matching

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.igdb.com/v4"

_JETON = {"valeur": "", "expire": 0.0}
_LOCK = threading.Lock()
_ECHECS = set()          # names searched in vain: we do not retry in a loop


def configure(cfg=None):
    cfg = cfg or config.load_config()
    return (bool((cfg.get("igdb_client_id") or "").strip())
            and bool((cfg.get("igdb_client_secret") or "").strip()))


def _base(cfg):
    """Base address, overridable for tests."""
    return (cfg.get("igdb_url") or "").strip().rstrip("/") or API_URL


def _url_jeton(cfg):
    return (cfg.get("igdb_token_url") or "").strip() or TOKEN_URL


def jeton(cfg=None, force=False):
    """Application token, renewed only when it expires."""
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
            with net.open_url(req, timeout=15) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            return ""
        _JETON["valeur"] = d.get("access_token", "")
        _JETON["expire"] = time.time() + float(d.get("expires_in", 3600))
        return _JETON["valeur"]


# IGDB accepts 4 requests a second. Without spacing, fetching 80 entries sends
# 80 at once: half come back 429, and those failures were then mistaken for
# "game not found".
INTERVALLE = 0.26
_DERNIERE = [0.0]
# A separate lock: sleeping while holding the token's would block everything else.
_RYTHME = threading.Lock()


def _attendre_son_tour():
    with _RYTHME:
        creux = INTERVALLE - (time.monotonic() - _DERNIERE[0])
        if creux > 0:
            time.sleep(creux)
        _DERNIERE[0] = time.monotonic()


def _requete(cfg, chemin, corps, essais=3):
    """Return the list of results, or None if the request FAILED.

    The distinction matters: an empty list means "IGDB does not have this game"
    and is worth remembering; None means "we could not ask" and must be
    retryable.
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
            with net.open_url(req, timeout=20) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            return d if isinstance(d, list) else []
        except urllib.error.HTTPError as exc:
            if exc.code == 401:                 # token expired ahead of time
                t = jeton(cfg, force=True)
                continue
            if exc.code == 429:                 # too fast: let it settle
                time.sleep(1.0 + essai)
                continue
            return None
        except Exception:
            return None
    return None


def _echapper(s):
    return str(s or "").replace('"', " ").replace("\\", " ")


def chercher(nom, cfg=None):
    """A game's details: {nom, resume, annee, editeur} or None.

    We ask for the short summary (`summary`) rather than the full article
    (`storyline`): on a game card, three lines beat a truncated paragraph.
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
            _ECHECS.add(cle)           # genuinely not found
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


# `t_cover_big_2x` returns 528 x 704: the size of a card's cover, without
# fetching the original, which can weigh several megabytes for nothing.
IMAGE = "https://images.igdb.com/igdb/image/upload/t_cover_big_2x/%s.jpg"


def jaquette(nom, cfg=None):
    """The IGDB cover URL for a game, or None.

    IGDB publishes cover art, and Romule never asked for it: it only queried
    IGDB for summaries and relied on SteamGridDB for images. But SteamGridDB is
    a community ARTWORK database, rich on what gets played with a keyboard and
    thin on handheld console catalogues — "Crazy Construction", a perfectly
    real 3DS game, is not in it, while IGDB knows it and has its cover.

    So this is not a last-ditch fallback: it is a second source, consulted when
    the first has nothing. It goes through the same matching rule, for the same
    reason: a cover that is not the game's is worse than an empty sleeve.
    """
    cfg = cfg or config.load_config()
    if not configure(cfg) or not (nom or "").strip():
        return None
    cle = nom.strip().lower()
    with _LOCK:
        if cle in _ECHECS:
            return None       # IGDB does not know this game: no cover either
    corps = ('search "%s"; fields name,cover.image_id; limit 10;'
             % _echapper(nom))
    jeux = _requete(cfg, "games", corps)
    if jeux is None:
        return None                    # echec technique : on reessaiera
    if not jeux:
        with _LOCK:
            _ECHECS.add(cle)           # genuinely not found
        return None
    # Games without a cover are dropped BEFORE matching, so that one without
    # an image does not deny Romule the cover of a neighbouring edition.
    #
    # A known game that simply has no image does NOT join `_ECHECS`: it exists,
    # and `chercher()` must still be able to get a summary out of it.
    avec = [j for j in jeux if (j.get("cover") or {}).get("image_id")]
    j = matching.best(avec, nom, name=lambda x: x.get("name") or "")
    return IMAGE % j["cover"]["image_id"] if j else None


# IGDB platform names -> our keys. IGDB knows hundreds of them; we only map
# the ones we know how to file.
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
    """The platforms this game was released on, according to IGDB.

    Used to decide when the extension is not enough: an `.iso` may be a PS2, a
    Wii or an Xbox, but "Metal Gear Solid 3" only came out on one of them.
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


# IGDB categories: 0 = main game, 3 = bundle, 5 = mod, 6 = fan game…
# The first search result is often a HACK bearing almost the same name:
# "Castlevania: Aria of Sorrow" used to return the summary of a modified
# version. So we prefer the main game, then the closest title.
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
        # a title that piles on words ("… Randomizer", "… Hack") strays from
        # what we asked for
        penalite = len(t - vise)
        principal = 1 if j.get("category", JEU_PRINCIPAL) == JEU_PRINCIPAL else 0
        avec_resume = 1 if (j.get("summary") or "").strip() else 0
        return (principal, commun - penalite * 0.5, avec_resume,
                -(j.get("category") or 0))

    retenu = max(jeux, key=score)
    # "At least one word in common" was far too permissive: "Crazy" passed for
    # "Crazy Construction". A candidate must cover the MAJORITY of distinctive
    # words — same rule as for SteamGridDB, same reason.
    return retenu if matching.close_enough(retenu.get("name"), cherche) else None


def tester(cfg=None):
    """Check that the credentials work, without saving anything."""
    cfg = cfg or config.load_config()
    if not configure(cfg):
        raise ValueError("Client ID et Client Secret Twitch sont necessaires.")
    if not jeton(cfg, force=True):
        raise ValueError("Twitch a refuse ces identifiants.")
    essai = chercher("The Legend of Zelda", cfg)
    return {"jeton": True, "exemple": (essai or {}).get("nom") or "(aucun resultat)"}
