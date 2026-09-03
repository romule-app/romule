"""Is there a newer version, and what does it bring?

A self-hosted tool you install once and forget ends up running for months on a
version that has since received security fixes. Nothing in the interface said
so.

Three things are worth explaining, because none of them is obvious.

**We ask once a day, and never at startup.** GitHub limits anonymous requests
to sixty an hour per address, and several instances behind the same public
address share that budget. The answer is therefore kept on disk, along with
the time it was read.

**The network must never make the interface wait.** The check is lazy: the
route returns what it knows, and only goes out when the cache has expired. A
GitHub outage answers "I don't know", not an error.

**It can be switched off.** Some people self-host precisely so as to talk to
nobody. The `maj_check` setting exists, it is documented, and the audit
reports what it does.
"""

import json
import re
import time

from . import config, reseau
from . import __version__

# Published version: `v0.2.0` or `0.2.0`, possibly followed by a suffix.
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")

SOURCE = "https://api.github.com/repos/romule-app/romule/releases/latest"
CACHE = config.fichier_etat("_romule-maj.json", "_romule-maj.json")
DUREE = 24 * 3600
# Past this, the release note is truncated: it shows in a dialog, not in a
# documentation browser.
MAX_NOTES = 4000


def _triplet(v):
    m = _VERSION.match(str(v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def plus_recente(publiee, courante=None):
    """Is `publiee` strictly newer than `courante`?

    Compares NUMBERS, not strings: "0.10.0" comes after "0.9.0", which a
    lexical comparison gets wrong. A version we cannot read triggers nothing —
    better to stay silent than to cry out wrongly.
    """
    a, b = _triplet(publiee), _triplet(courante or __version__)
    return bool(a and b and a > b)


def _lire_cache():
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire_cache(d):
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    except OSError:
        pass                      # a full disk must not break the interface


def _demander():
    """Ask GitHub. Returns a dict, or raises."""
    req = reseau.urllib.request.Request(
        SOURCE, headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "romule"})
    with reseau.ouvrir(req, timeout=8) as r:
        d = json.loads(r.read().decode("utf-8"))
    # The tag's `v` is stripped: the interface already writes "Version %s
    # available", and "Version v0.3.0 available" reads twice. The comparison
    # does not care either way — `_triplet` ignores the prefix.
    return {"version": str(d.get("tag_name") or "").lstrip("vV"),
            "titre": str(d.get("name") or ""),
            "notes": str(d.get("body") or "")[:MAX_NOTES],
            "url": str(d.get("html_url") or ""),
            "publiee": str(d.get("published_at") or "")}


def etat(cfg=None, forcer=False):
    """What we know about the latest version. Never raises.

    Always returns the same keys, so the interface need not tell "not checked
    yet" from "error": in both cases `disponible` is false and there is nothing
    to show.
    """
    cfg = cfg or config.load_config()
    reponse = {"courante": __version__, "disponible": False, "version": "",
               "titre": "", "notes": "", "url": "", "verifie": 0,
               "actif": bool(cfg.get("maj_check", True))}
    if not reponse["actif"]:
        return reponse

    cache = _lire_cache()
    frais = (time.time() - float(cache.get("verifie") or 0)) < DUREE
    if forcer or not frais:
        try:
            cache = _demander()
            cache["verifie"] = int(time.time())
            _ecrire_cache(cache)
        except Exception:
            # Network down, GitHub unavailable, quota reached: keep what we
            # had. A failed check is not an event.
            if not cache:
                return reponse

    reponse.update({k: cache.get(k, reponse[k])
                    for k in ("version", "titre", "notes", "url")})
    reponse["verifie"] = int(cache.get("verifie") or 0)
    reponse["disponible"] = plus_recente(cache.get("version"))
    return reponse
