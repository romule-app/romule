"""Game descriptions in the user's language, via Wikidata + Wikipedia.

IGDB only publishes its summaries in English: its `game_localizations`
translate the TITLE and nothing else. For a description in French, the only
free, key-less source covering every platform is Wikipedia.

The hard part is not reading the article, it is finding the RIGHT one. A direct
search on fr.wikipedia answers "Mario Kart" (the series) when you look for
"Mario Kart: Super Circuit", and "Sonic the Hedgehog" when you look for "Sonic
the Hedgehog 2". So we go through Wikidata:

  1. find the entity by its English title — the one IGDB gave us;
  2. keep only those that are **a video game** (P31);
  3. follow the link to the article in the language we want.

The English title is the pivot: it saves us guessing the translation. "Kirby &
The Amazing Mirror" leads to the French article "Kirby et le Labyrinthe des
Miroirs" -- anglais:ok, that is the French title being quoted -- which no
string comparison would ever have found.

No key is needed. Both APIs do, however, expect an identifiable `User-Agent`
and a reasonable pace.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Wikimedia requires a `User-Agent` that identifies the tool AND gives a way
# to reach its author: a project handed to strangers cannot present itself as
# "personal game library" with no contact. Too vague an identity gets everyone
# rate-limited, then blocked, all at once.
from . import SOURCE_URL, __version__, net

AGENT = "Romule/%s (%s)" % (__version__, SOURCE_URL)
WIKIDATA = "https://www.wikidata.org/w/api.php"

# Wikidata: "video game" and its common subclasses. Without this filter, a
# search brings back a film or a character bearing the same name just as
# readily.
VIDEO_GAME = {
    "Q7889",      # video game
    "Q865493",    # role-playing video game
    "Q4393107",   # video game series (accepted: often the only article)
    "Q16070115",  # platform video game
    "Q17517379",  # action video game
    "Q28058561",  # racing video game
}

INTERVAL = 0.7          # the Wikimedia APIs answer 429 if you push
_PACE = threading.Lock()
_LAST = [0.0]
_FAILURES = set()


def _wait():
    with _PACE:
        creux = INTERVAL - (time.monotonic() - _LAST[0])
        if creux > 0:
            time.sleep(creux)
        _LAST[0] = time.monotonic()


def _read(url, attempts=3):
    for essai in range(attempts):
        _wait()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with net.open_url(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(1.5 * (essai + 1))
                continue
            return None
        except Exception:
            return None
    return None


def _article(english_title, lang):
    """(Wikidata identifier, article title) in the language we want."""
    q = urllib.parse.urlencode({
        "action": "wbsearchentities", "format": "json", "language": "en",
        "uselang": "en", "type": "item", "limit": 6, "search": english_title})
    d = _read(WIKIDATA + "?" + q)
    ids = [x["id"] for x in (d or {}).get("search", [])]
    if not ids:
        return None, None
    site = lang + "wiki"
    q2 = urllib.parse.urlencode({
        "action": "wbgetentities", "format": "json", "ids": "|".join(ids),
        "props": "claims|sitelinks", "sitefilter": site})
    e = _read(WIKIDATA + "?" + q2)
    for i in ids:                       # the search order is authoritative
        ent = ((e or {}).get("entities") or {}).get(i) or {}
        types = {(c.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id")
                 for c in (ent.get("claims") or {}).get("P31", [])}
        if not (types & VIDEO_GAME):
            continue
        lien = (ent.get("sitelinks") or {}).get(site)
        if lien:
            return i, lien["title"]
    return None, None


def _intro(article, lang, sentences=3):
    """The article's introduction, as plain text."""
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": article,
        "prop": "extracts", "exintro": 1, "explaintext": 1, "redirects": 1})
    d = _read("https://%s.wikipedia.org/w/api.php?%s" % (lang, q))
    for p in (((d or {}).get("query") or {}).get("pages") or {}).values():
        text = " ".join((p.get("extract") or "").split())
        if not text:
            return ""
        # Three sentences are enough on a game card; the whole article would
        # overflow it by a mile.
        bouts, out = text.split(". "), []
        for b in bouts:
            out.append(b)
            if len(out) >= sentences or len(" ".join(out)) > 420:
                break
        return ". ".join(out).rstrip(".") + "."
    return ""


def summary(english_title, lang="fr"):
    """(text, url) in the requested language, or ("", "") if nothing is found.

    English is never returned through this path: the caller then keeps IGDB's
    summary, which is already English. Returning the same language twice from
    two different sources would add nothing.

    The URL is not a bonus: Wikipedia text is CC BY-SA, and that licence
    requires citing the source. Returning it here is the only way the interface
    can do so.
    """
    english_title = (english_title or "").strip()
    if not english_title or lang in ("", "en"):
        return "", ""
    cle = (english_title.lower(), lang)
    with _PACE:
        if cle in _FAILURES:
            return "", ""
    _, article = _article(english_title, lang)
    if not article:
        with _PACE:
            _FAILURES.add(cle)
        return "", ""
    text = _intro(article, lang)
    if not text:
        with _PACE:
            _FAILURES.add(cle)
        return "", ""
    url = "https://%s.wikipedia.org/wiki/%s" % (
        lang, urllib.parse.quote(article.replace(" ", "_")))
    return text, url
