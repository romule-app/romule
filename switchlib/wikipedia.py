"""Descriptions de jeu dans la langue de l'utilisateur, via Wikidata + Wikipédia.

IGDB ne publie ses resumes qu'en anglais : ses `game_localizations` ne
traduisent que le TITRE. Pour une description en francais, la seule source
libre et sans cle qui couvre toutes les plateformes est Wikipédia.

La difficulte n'est pas de lire l'article, c'est de trouver le BON. Une
recherche directe sur fr.wikipedia repond « Mario Kart » (la serie) quand on
cherche « Mario Kart: Super Circuit », et « Sonic the Hedgehog » quand on
cherche « Sonic the Hedgehog 2 ». On passe donc par Wikidata :

  1. chercher l'entite par son titre anglais — celui qu'IGDB nous a donne ;
  2. ne garder que celles qui sont **un jeu video** (P31) ;
  3. suivre le lien vers l'article de la langue voulue.

Le titre anglais sert de pivot : il evite d'avoir a deviner la traduction.
« Kirby & The Amazing Mirror » mene ainsi a « Kirby et le Labyrinthe des
Miroirs », ce qu'aucune comparaison de chaines n'aurait trouve.

Aucune cle n'est necessaire. Les deux API demandent en revanche un
`User-Agent` identifiable et un rythme raisonnable.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

AGENT = "switchlib/1.0 (ludotheque personnelle)"
WIKIDATA = "https://www.wikidata.org/w/api.php"

# Wikidata : « jeu video » et ses sous-classes courantes. Sans ce filtre, une
# recherche ramene aussi bien un film qu'un personnage portant le meme nom.
JEU_VIDEO = {
    "Q7889",      # jeu video
    "Q865493",    # jeu video de role
    "Q4393107",   # serie de jeux video (accepte : souvent le seul article)
    "Q16070115",  # jeu video de plateforme
    "Q17517379",  # jeu video d'action
    "Q28058561",  # jeu video de course
}

INTERVALLE = 0.7          # les API Wikimedia repondent 429 si on insiste
_RYTHME = threading.Lock()
_DERNIERE = [0.0]
_ECHECS = set()


def _attendre():
    with _RYTHME:
        creux = INTERVALLE - (time.monotonic() - _DERNIERE[0])
        if creux > 0:
            time.sleep(creux)
        _DERNIERE[0] = time.monotonic()


def _lire(url, essais=3):
    for essai in range(essais):
        _attendre()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENT})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(1.5 * (essai + 1))
                continue
            return None
        except Exception:
            return None
    return None


def _article(titre_anglais, langue):
    """(identifiant Wikidata, titre de l'article) dans la langue voulue."""
    q = urllib.parse.urlencode({
        "action": "wbsearchentities", "format": "json", "language": "en",
        "uselang": "en", "type": "item", "limit": 6, "search": titre_anglais})
    d = _lire(WIKIDATA + "?" + q)
    ids = [x["id"] for x in (d or {}).get("search", [])]
    if not ids:
        return None, None
    site = langue + "wiki"
    q2 = urllib.parse.urlencode({
        "action": "wbgetentities", "format": "json", "ids": "|".join(ids),
        "props": "claims|sitelinks", "sitefilter": site})
    e = _lire(WIKIDATA + "?" + q2)
    for i in ids:                       # l'ordre de la recherche fait foi
        ent = ((e or {}).get("entities") or {}).get(i) or {}
        types = {(c.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id")
                 for c in (ent.get("claims") or {}).get("P31", [])}
        if not (types & JEU_VIDEO):
            continue
        lien = (ent.get("sitelinks") or {}).get(site)
        if lien:
            return i, lien["title"]
    return None, None


def _intro(article, langue, phrases=3):
    """Introduction de l'article, en texte brut."""
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": article,
        "prop": "extracts", "exintro": 1, "explaintext": 1, "redirects": 1})
    d = _lire("https://%s.wikipedia.org/w/api.php?%s" % (langue, q))
    for p in (((d or {}).get("query") or {}).get("pages") or {}).values():
        texte = " ".join((p.get("extract") or "").split())
        if not texte:
            return ""
        # Trois phrases suffisent sur une carte de jeu ; l'article entier
        # deborderait largement.
        bouts, out = texte.split(". "), []
        for b in bouts:
            out.append(b)
            if len(out) >= phrases or len(" ".join(out)) > 420:
                break
        return ". ".join(out).rstrip(".") + "."
    return ""


def resume(titre_anglais, langue="fr"):
    """Resume dans la langue demandee, ou "" si l'article n'existe pas.

    On ne renvoie jamais l'anglais par ce chemin : l'appelant garde alors le
    resume d'IGDB, qui est deja anglais. Retourner deux fois la meme langue par
    deux sources differentes n'apporterait rien.
    """
    titre_anglais = (titre_anglais or "").strip()
    if not titre_anglais or langue in ("", "en"):
        return ""
    cle = (titre_anglais.lower(), langue)
    with _RYTHME:
        if cle in _ECHECS:
            return ""
    _, article = _article(titre_anglais, langue)
    if not article:
        with _RYTHME:
            _ECHECS.add(cle)
        return ""
    texte = _intro(article, langue)
    if not texte:
        with _RYTHME:
            _ECHECS.add(cle)
    return texte
