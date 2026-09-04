"""Cover art: lazy download plus a local `_covers/` cache.

Three sources (`cover_provider` setting):
  - nlib        : official Switch icon by title ID (default, no key needed)
  - steamgriddb : search by name, requires an API key
  - custom      : free-form URL template (`cover_url`, {tid} substituted)

Failures are remembered for the session so we do not retry in a loop.
All of it is optional: with no working source the interface shows a placeholder.
"""

import hashlib
import json as _json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config, net
from . import matching

NLIB = "https://api.nlib.cc/nx/{tid}/icon/256/256"

_FAILED = {}
_LOCK = threading.Lock()


def path_for(tid):
    return config.COVERS / (tid.lower() + ".jpg")


def version():
    """Cache freshness token: changes as soon as an image is added or removed.
    Used to invalidate the browser cache (without it, the browser keeps its old
    images for hours)."""
    try:
        return int(config.COVERS.stat().st_mtime)
    except OSError:
        return 0


MINI = 100          # same threshold as on download: below this size it is not
                    # an image but an empty response or an error


def cached(tid):
    p = path_for(tid)
    # A non-empty file is not necessarily an image: a few-byte response once
    # stayed in the cache and denied the game its artwork forever, because it
    # passed for valid.
    return p if (p.exists() and p.stat().st_size >= MINI) else None


_JUNK = re.compile(r"[\[\(][^\])]*[\])]|\bv\d+(\.\d+)*\b|\b\d{4,}\b", re.I)


def search_name(name):
    """Clean a file name for a search by title.

    "Super Smash Bros. Ultimate (01006A800016E000)(v0)" -> "Super Smash Bros. Ultimate"
    """
    # any ROM extension, not only the Switch ones: ".gba", ".md"…
    s = re.sub(r"\.[a-z0-9]{2,4}$", "", name or "", flags=re.I)
    s = _JUNK.sub(" ", s)
    s = re.sub(r"[_\-–]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" .-—")
    return s


def cache_key(tid, name=None):
    """The identifier a cover is filed under.

    Some files carry no usable title ID — XCI packs that merge game, updates
    and DLC, notably. They got an empty thumbnail when a search by name would
    have been enough, so they get a key derived from the name instead.
    """
    if tid:
        return tid.lower()
    propre = search_name(name or "")
    if not propre:
        return None
    # A cache key, not a security digest: we want a short, stable file name
    # for a given title. `usedforsecurity=False` says so to the API — and that
    # is what lets Romule run on a FIPS-mode Python, where SHA-1 is refused by
    # default.
    return "n" + hashlib.sha1(propre.encode("utf-8"),
                              usedforsecurity=False).hexdigest()[:15]


def fetch(tid, name=None, cfg=None):
    key = cache_key(tid, name)
    if not key:
        return None
    tid = (tid or "").lower()
    hit = cached(key)
    if hit:
        return hit
    if _recent_failure(key):
        return None
    cfg = cfg or config.load_config()

    # Try the chosen source, then fall back to the official icon: a correct
    # image beats no image at all.
    urls = []
    principal = _resolve_url(tid, name, cfg)
    if principal:
        urls.append(principal)
    if tid and cfg.get("cover_provider") != "nlib":
        urls.append(NLIB.replace("{tid}", tid))
    if not urls and name and (cfg.get("steamgriddb_key") or "").strip():
        # without a title ID, SteamGridDB is still reachable by name
        secours = _sgdb_url(name, cfg["steamgriddb_key"].strip())
        if secours:
            urls.append(secours)

    def try_url(url):
        """Store the image and return its path, or None if it is worthless."""
        try:
            data = _download(url)
        except Exception:
            return None
        if len(data) < MINI:
            return None
        config.COVERS.mkdir(exist_ok=True)
        path_for(key).write_bytes(data)
        return path_for(key)

    for url in urls:
        p = try_url(url)
        if p:
            return p

    # A SECOND source, not a last-ditch fallback. SteamGridDB is a community
    # artwork database: rich on what gets played with a keyboard, thin on
    # handheld console catalogues. IGDB, which Romule already queried for
    # summaries, publishes cover art too — it was simply never asked.
    #
    # It is consulted AFTER the loop, not appended to `urls`: the question to
    # answer is "no image", not "no address". Placed before, an nlib or
    # SteamGridDB URL answering 404 would have been enough to rule IGDB out —
    # and the fallback would never have served the games that need it most.
    if name:
        # `search_name` and not `name`: here `name` is the FILE NAME, and its
        # distinctive words include "europe", "fr" and "3ds". The matching
        # rule, which demands two thirds of them, therefore rejected the right
        # game — the fallback ran, searched, found, and refused. `sgdb_infos`
        # cleans internally; IGDB expects an already-clean title, as for
        # `chercher()`.
        from . import igdb
        from_igdb = igdb.jaquette(search_name(name), cfg)
        if from_igdb:
            p = try_url(from_igdb)
            if p:
                return p
    _fail(key)
    return None


FAILURE_TTL = 600          # retry after 10 min rather than never


def _fail(tid):
    with _LOCK:
        _FAILED[tid] = time.time()


def _recent_failure(tid):
    """A passing failure must not deny the game its cover forever."""
    with _LOCK:
        t = _FAILED.get(tid)
        if t is None:
            return False
        if time.time() - t > FAILURE_TTL:
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
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "romule"})
    with net.open_url(req, timeout=25) as r:
        return r.read()


def sgdb_infos(name, key):
    """Look a game up on SteamGridDB: returns {titre, url} or None.

    The same request serves the title AND the artwork: it is the only place
    where an official name is available for a ROM carrying no identifier.
    """
    base = "https://www.steamgriddb.com/api/v2"
    h = {"Authorization": "Bearer " + key, "User-Agent": "romule"}
    try:
        cherche = search_name(name)
        found = _json.loads(_download(base + "/search/autocomplete/"
                                      + urllib.parse.quote(cherche), h))
        # NOT `data[0]`. SteamGridDB ranks by ITS relevance, which is not
        # ours: on "Crazy Construction" it returns a game called "Crazy" first.
        # That title was then the pivot for the IGDB lookup, so the card showed
        # the name AND the summary of a different game.
        #
        # A missing entry is visible; a wrong one is believed. We would rather
        # return nothing.
        jeu = matching.best(found.get("data") or [], cherche,
                            name=lambda j: j.get("name") or "")
        if not jeu:
            return None
        infos = {"titre": jeu.get("name") or "", "url": None}
        try:
            grids = _json.loads(_download(
                base + "/grids/game/%d?dimensions=600x900&limit=1&types=static" % jeu["id"], h))
            # This `[0]` is legitimate: the game is already identified, and
            # we simply take its first cover.
            infos["url"] = grids["data"][0]["url"]
        except Exception:
            pass
        return infos
    except Exception:
        return None


def test_key(cfg):
    """Check a SteamGridDB key and return (ok, message).

    `sgdb_infos` swallows every error: the right behaviour when fetching one
    cover among hundreds, but the wizard needs to know WHY it did not work. A
    mis-pasted key and a game that does not exist are not fixed the same way.
    """
    key = (cfg.get("steamgriddb_key") or "").strip()
    if not key:
        return (False, "Aucune key renseignee.")
    url = ("https://www.steamgriddb.com/api/v2/search/autocomplete/"
           + urllib.parse.quote("zelda"))
    try:
        _download(url, {"Authorization": "Bearer " + key, "User-Agent": "romule"})
        return (True, "Cle acceptee.")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return (False, "Cle refusee par SteamGridDB.")
        return (False, "SteamGridDB repond %d." % exc.code)
    except Exception as exc:
        return (False, "Contact impossible : %s" % exc)


def _sgdb_url(name, key):
    infos = sgdb_infos(name, key)
    return infos["url"] if infos else None


def clear():
    """Empty the on-disk cache and the failure list."""
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
