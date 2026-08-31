"""Fiches de jeux (nom, description, editeur...) via nlib, avec cache local.

Source : https://api.nlib.cc/nx/<tid> (JSON). Independant de la source des
jaquettes. Cache dans `_covers/<tid>.json`. Echecs memorises pour la session.
"""

import json
import threading
import urllib.request

from . import config

_FAILED = set()
_LOCK = threading.Lock()
_KEEP = ("name", "description", "publisher", "releaseDate",
         "numberOfPlayers", "category", "size", "rating", "intro")


def _path(tid, lang):
    return config.COVERS / ("%s.%s.json" % (tid.lower(), lang))


def fiche_nom(nom, cfg=None, reseau=True):
    """Fiche d'un jeu SANS title ID (toutes les plateformes hors Switch).

    nlib ne connait que les jeux Switch. Pour le reste, la seule source dont on
    dispose deja est SteamGridDB, qui donne un titre officiel en meme temps que
    la jaquette. On range la fiche sous la meme cle que la jaquette, pour ne pas
    multiplier les caches.
    """
    from . import covers
    cle = covers.cle_cache("", nom)
    if not cle:
        return None
    cfg = cfg or config.load_config()
    p = config.COVERS / (cle + ".fiche.json")
    en_cache = None
    if p.exists():
        try:
            en_cache = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            en_cache = None
    # Une fiche mise en cache AVANT qu'IGDB ne soit configure ne contient qu'un
    # titre. La renvoyer telle quelle condamnait ces jeux a n'avoir jamais de
    # resume : on la complete des qu'une source peut le fournir.
    from . import igdb as _igdb
    _cfg = cfg or config.load_config()
    _langue = (_cfg.get("meta_lang") or "fr").strip().lower()

    def _complete(f):
        """Une fiche est complete quand il n'y a plus rien a aller chercher.

        « Elle a un resume » ne suffit pas : un resume ANGLAIS alors que
        l'utilisateur lit le francais laisse encore du travail. Sans cette
        nuance, la fiche etait renvoyee telle quelle et Wikipédia n'etait
        jamais consulte.
        """
        if not f:
            return False
        if not f.get("resume"):
            return not _igdb.configure(_cfg)
        if _langue in ("", "en"):
            return True
        return str(f.get("source_resume", "")).endswith(_langue)

    if en_cache and (_complete(en_cache) or not reseau):
        return en_cache
    if not reseau:
        return None
    key = (cfg.get("steamgriddb_key") or "").strip()
    if not key and not _igdb.configure(cfg):
        return None                       # aucune source configuree
    infos = covers.sgdb_infos(nom, key) if key else None
    d = dict(en_cache or {})
    d["nom"] = d.get("nom") or (infos or {}).get("titre") or ""
    # Le titre vient de SteamGridDB, le resume d'IGDB : les deux sources sont
    # independantes, et l'absence de l'une ne doit pas empecher l'autre.
    from . import igdb, wikipedia
    if igdb.configure(cfg):
        fiche = igdb.chercher(d["nom"] or covers.search_name(nom), cfg)
        if fiche:
            d["nom"] = d["nom"] or fiche.get("nom") or ""
            for cle in ("resume", "annee", "editeur"):
                if fiche.get(cle):
                    d[cle] = fiche[cle]

    # IGDB ne publie ses resumes qu'en anglais. Si l'utilisateur lit le
    # francais, Wikipédia prend le relais — le titre anglais sert de pivot pour
    # retrouver le bon article. Le resume anglais reste en secours.
    langue = (cfg.get("meta_lang") or "fr").strip().lower()
    if langue not in ("", "en"):
        pivot = d.get("nom") or covers.search_name(nom)
        texte = wikipedia.resume(pivot, langue)
        if texte:
            d["resume_en"] = d.get("resume", "")
            d["resume"] = texte
            d["source_resume"] = "wikipedia:" + langue
    config.COVERS.mkdir(exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def cached(tid, cfg=None):
    """Fiche deja en cache, sans jamais toucher au reseau.

    La bibliotheque a besoin du titre traduit de CHAQUE jeu : le faire par des
    appels reseau bloquerait l'affichage. On lit donc le cache, et le
    telechargement des fiches manquantes est un travail separe (`/api/meta-sync`).
    """
    if not tid:
        return None
    lang = (cfg or config.load_config()).get("meta_lang", "fr") or "en"
    p = _path(tid.lower(), lang)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def bulk(tids, cfg=None):
    """{tid: {nom, resume}} pour les fiches deja en cache."""
    cfg = cfg or config.load_config()
    out = {}
    for tid in {(t or "").lower() for t in tids if t}:
        d = cached(tid, cfg)
        if not d:
            continue
        entree = {}
        if d.get("name"):
            entree["nom"] = d["name"]
        # nlib donne la date complete ; l'annee suffit pour trier et filtrer,
        # et c'est la seule chose qu'on affiche.
        brut = str(d.get("releaseDate") or "")
        chiffres = "".join(c for c in brut if c.isdigit())
        if len(chiffres) >= 4 and chiffres[:4].isdigit():
            entree["annee"] = chiffres[:4]
        if d.get("publisher"):
            entree["editeur"] = d["publisher"]
        resume = (d.get("intro") or d.get("description") or "").strip()
        if resume:
            entree["resume"] = " ".join(resume.split())
        if entree:
            out[tid] = entree
    return out


def manquants(tids, cfg=None):
    """Title IDs sans fiche en cache, dans l'ordre recu."""
    cfg = cfg or config.load_config()
    vus, out = set(), []
    for tid in tids:
        t = (tid or "").lower()
        if not t or t in vus:
            continue
        vus.add(t)
        if not cached(t, cfg):
            out.append(t)
    return out


def fetch(tid, cfg=None):
    if not tid:
        return None
    tid = tid.lower()
    lang = (cfg or config.load_config()).get("meta_lang", "fr") or "en"
    p = _path(tid, lang)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    key = tid + "/" + lang
    with _LOCK:
        if key in _FAILED:
            return None
    try:
        url = "https://api.nlib.cc/nx/%s?lang=%s" % (tid, lang)
        req = urllib.request.Request(url, headers={"User-Agent": "romule"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        keep = {k: data.get(k) for k in _KEEP if data.get(k) not in (None, "")}
        config.COVERS.mkdir(exist_ok=True)
        p.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
        return keep
    except Exception:
        with _LOCK:
            _FAILED.add(key)
        return None
