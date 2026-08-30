"""Jaquettes des jeux : telechargement paresseux + cache local `_covers/`.

Trois sources (config `cover_provider`) :
  - nlib        : icone Switch officielle par title ID (defaut, sans cle)
  - steamgriddb : recherche par nom, necessite une cle API
  - custom      : modele d'URL libre (`cover_url`, {tid} remplace)

Les echecs sont memorises pour la session afin de ne pas retenter en boucle.
Tout est optionnel : sans source valide, l'UI affiche un placeholder.
"""

import hashlib
import json as _json
import re
import threading
import time
import urllib.parse
import urllib.request

from . import config

NLIB = "https://api.nlib.cc/nx/{tid}/icon/256/256"

_FAILED = {}
_LOCK = threading.Lock()


def path_for(tid):
    return config.COVERS / (tid.lower() + ".jpg")


def version():
    """Jeton de fraicheur du cache : change des qu'une image est ajoutee ou
    supprimee. Sert a invalider le cache du navigateur (sans lui, il garde
    ses anciennes images pendant des heures)."""
    try:
        return int(config.COVERS.stat().st_mtime)
    except OSError:
        return 0


MINI = 100          # meme seuil qu'au telechargement : sous cette taille, ce
                    # n'est pas une image mais une reponse vide ou une erreur


def cached(tid):
    p = path_for(tid)
    # Un fichier non vide n'est pas forcement une image : des reponses de
    # quelques octets sont restees en cache et privaient le jeu de jaquette
    # pour toujours, puisqu'elles passaient pour valides.
    return p if (p.exists() and p.stat().st_size >= MINI) else None


_JUNK = re.compile(r"[\[\(][^\])]*[\])]|\bv\d+(\.\d+)*\b|\b\d{4,}\b", re.I)


def search_name(name):
    """Nettoie un nom de fichier pour une recherche par titre.

    « Super Smash Bros. Ultimate (01006A800016E000)(v0) » -> « Super Smash Bros. Ultimate »
    """
    # toute extension de ROM, pas seulement celles de la Switch : « .gba », « .md »…
    s = re.sub(r"\.[a-z0-9]{2,4}$", "", name or "", flags=re.I)
    s = _JUNK.sub(" ", s)
    s = re.sub(r"[_\-–]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" .-—")
    return s


def cle_cache(tid, name=None):
    """Identifiant sous lequel une jaquette est rangee.

    Certains fichiers ne portent aucun title ID exploitable — les packs XCI qui
    fusionnent jeu, mises a jour et DLC, notamment. Ils avaient droit a une
    vignette vide alors qu'une recherche par nom aurait suffi : on leur donne
    donc une cle derivee du nom.
    """
    if tid:
        return tid.lower()
    propre = search_name(name or "")
    if not propre:
        return None
    return "n" + hashlib.sha1(propre.encode("utf-8")).hexdigest()[:15]


def fetch(tid, name=None, cfg=None):
    cle = cle_cache(tid, name)
    if not cle:
        return None
    tid = (tid or "").lower()
    hit = cached(cle)
    if hit:
        return hit
    if _echec_recent(cle):
        return None
    cfg = cfg or config.load_config()

    # On essaie la source choisie, puis on se rabat sur l'icone officielle :
    # mieux vaut une image correcte que pas d'image du tout.
    urls = []
    principal = _resolve_url(tid, name, cfg)
    if principal:
        urls.append(principal)
    if tid and cfg.get("cover_provider") != "nlib":
        urls.append(NLIB.replace("{tid}", tid))
    if not urls and name and (cfg.get("steamgriddb_key") or "").strip():
        # sans title ID, SteamGridDB reste joignable par le nom
        secours = _sgdb_url(name, cfg["steamgriddb_key"].strip())
        if secours:
            urls.append(secours)

    for url in urls:
        try:
            data = _download(url)
            if len(data) < MINI:
                continue
            config.COVERS.mkdir(exist_ok=True)
            path_for(cle).write_bytes(data)
            return path_for(cle)
        except Exception:
            continue
    _fail(cle)
    return None


ECHEC_TTL = 600          # on retente au bout de 10 min plutot que jamais


def _fail(tid):
    with _LOCK:
        _FAILED[tid] = time.time()


def _echec_recent(tid):
    """Un echec passager ne doit pas priver le jeu de jaquette pour toujours."""
    with _LOCK:
        t = _FAILED.get(tid)
        if t is None:
            return False
        if time.time() - t > ECHEC_TTL:
            del _FAILED[tid]
            return False
        return True


def _resolve_url(tid, name, cfg):
    provider = cfg.get("cover_provider", "nlib")
    if provider == "steamgriddb":
        key = (cfg.get("steamgriddb_key") or "").strip()
        return _sgdb_url(name, key) if (key and name) else None
    if provider == "custom":
        tpl = cfg.get("cover_url") or ""
        return tpl.replace("{tid}", tid) if "{tid}" in tpl else None
    return NLIB.replace("{tid}", tid)


def _download(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "switchlib"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def sgdb_infos(name, key):
    """Cherche un jeu sur SteamGridDB : renvoie {titre, url} ou None.

    La meme requete sert au titre ET a la jaquette : c'est le seul endroit ou
    l'on dispose d'un nom officiel pour une ROM qui ne porte aucun identifiant.
    """
    base = "https://www.steamgriddb.com/api/v2"
    h = {"Authorization": "Bearer " + key, "User-Agent": "switchlib"}
    try:
        found = _json.loads(_download(base + "/search/autocomplete/"
                                      + urllib.parse.quote(search_name(name)), h))
        jeu = found["data"][0]
        infos = {"titre": jeu.get("name") or "", "url": None}
        try:
            grids = _json.loads(_download(
                base + "/grids/game/%d?dimensions=600x900&limit=1&types=static" % jeu["id"], h))
            infos["url"] = grids["data"][0]["url"]
        except Exception:
            pass
        return infos
    except Exception:
        return None


def _sgdb_url(name, key):
    infos = sgdb_infos(name, key)
    return infos["url"] if infos else None


def clear():
    """Vide le cache disque et la liste d'echecs."""
    with _LOCK:
        _FAILED.clear()
    n = 0
    if config.COVERS.is_dir():
        for p in list(config.COVERS.glob("*.jpg")) + list(config.COVERS.glob("*.json")):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    return n
