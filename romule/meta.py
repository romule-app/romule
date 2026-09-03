"""Game details (name, description, publisher...) through nlib, cached locally.

Source: https://api.nlib.cc/nx/<tid> (JSON). Independent of the cover-art
source. Cached in `_covers/<tid>.json`. Failures remembered for the session.
"""

import json
import threading
import urllib.request

from . import config, reseau

_FAILED = set()
_LOCK = threading.Lock()
_KEEP = ("name", "description", "publisher", "releaseDate",
         "numberOfPlayers", "category", "size", "rating", "intro")


def _path(tid, lang):
    return config.COVERS / ("%s.%s.json" % (tid.lower(), lang))


def fiche_nom(nom, cfg=None, reseau=True):
    """Details for a game WITHOUT a title ID (every platform but the Switch).

    nlib only knows Switch games. For the rest, the one source already at hand
    is SteamGridDB, which gives an official title along with the artwork. The
    entry is filed under the same key as the cover, so as not to multiply
    caches.
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
    # An entry cached BEFORE IGDB was configured holds only a title. Returning
    # it as-is condemned those games never to have a summary: we complete it as
    # soon as a source can supply one.
    from . import igdb as _igdb
    _cfg = cfg or config.load_config()
    _langue = (_cfg.get("meta_lang") or "fr").strip().lower()

    def _complete(f):
        """An entry is complete when there is nothing left to fetch.

        "It has a summary" is not enough: an ENGLISH summary while the user
        reads French still leaves work to do. Without that nuance, the entry
        was returned as-is and Wikipedia was never consulted.
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
    # The title comes from SteamGridDB, the summary from IGDB: the two sources
    # are independent, and the absence of one must not block the other.
    from . import igdb, wikipedia
    if igdb.configure(cfg):
        fiche = igdb.chercher(d["nom"] or covers.search_name(nom), cfg)
        if fiche:
            d["nom"] = d["nom"] or fiche.get("nom") or ""
            for cle in ("resume", "annee", "editeur"):
                if fiche.get(cle):
                    d[cle] = fiche[cle]

    # IGDB only publishes its summaries in English. If the user reads French,
    # Wikipedia takes over — the English title is the pivot for finding the
    # right article. The English summary stays as a fallback.
    langue = (cfg.get("meta_lang") or "fr").strip().lower()
    if langue not in ("", "en"):
        pivot = d.get("nom") or covers.search_name(nom)
        texte, url = wikipedia.resume(pivot, langue)
        if texte:
            d["resume_en"] = d.get("resume", "")
            d["resume"] = texte
            d["source_resume"] = "wikipedia:" + langue
            # Without the article's address, the interface cannot cite its
            # source — and Wikipedia's licence requires it.
            d["url_resume"] = url
    config.COVERS.mkdir(exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def cached(tid, cfg=None):
    """An entry already in cache, never touching the network.

    The library needs the translated title of EVERY game: doing that with
    network calls would block the render. So we read the cache, and downloading
    the missing entries is a separate job (`/api/meta-sync`).
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
    """{tid: {nom, resume}} for the entries already in cache."""
    cfg = cfg or config.load_config()
    out = {}
    for tid in {(t or "").lower() for t in tids if t}:
        d = cached(tid, cfg)
        if not d:
            continue
        entree = {}
        if d.get("name"):
            entree["nom"] = d["name"]
        # nlib gives the full date; the year is enough to sort and filter by,
        # and it is the only part we show.
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
    """Title IDs with no cached entry, in the order received."""
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
        with reseau.ouvrir(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        keep = {k: data.get(k) for k in _KEEP if data.get(k) not in (None, "")}
        config.COVERS.mkdir(exist_ok=True)
        p.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
        return keep
    except Exception:
        with _LOCK:
            _FAILED.add(key)
        return None
