"""Does this candidate really match what we were looking for?

Two sources turn a file name into an official title: SteamGridDB for games
without an identifier, IGDB for summaries. Both return a LIST of candidates
ranked by their own idea of relevance, which is not ours: they try to answer
something, we try to answer correctly.

`covers.sgdb_infos()` took the first result, unchecked. On "Crazy
Construction", SteamGridDB returns a game called "Crazy" — and since that title
is then the pivot for the IGDB lookup, the card showed the name AND the summary
of a different game. One unchecked `[0]` produced both defects, and the result
was worse than a missing entry: a missing entry is visible, a wrong one is
believed.

The rule
--------
A candidate must cover the MAJORITY of the words being searched for. "Crazy"
covers one word out of two: not enough. "Batman: Arkham Asylum" covers all
three words of "Batman Arkham Asylum": that is the one.

The threshold is two thirds, rounded up — so two words out of two, two out of
three, three out of four. It is deliberately strict: showing nothing costs an
empty line, showing the wrong game costs the trust placed in the whole grid.
"""

import math
import re
import unicodedata

_MOTS = re.compile(r"[a-z0-9]+")

# Words that do not help tell two games apart: they are ignored in the COUNT,
# but not stripped from the candidate — "The Last of Us" must not become
# "Last Us" along the way.
_VIDES = {"the", "a", "an", "of", "and", "le", "la", "les", "de", "des", "du",
          "et", "version", "edition", "deluxe", "hd", "remastered"}


def mots(texte):
    """The words of a title, with accents removed.

    Without this normalisation, "Pokémon" was split into "pok" and "mon" — the
    pattern only knows ASCII — and could therefore never match "Pokemon" as
    written in a file name. Exactly the kind of detail that would have rejected
    perfectly good entries.
    """
    plat = unicodedata.normalize("NFKD", texte or "")
    plat = "".join(c for c in plat if not unicodedata.combining(c))
    return set(_MOTS.findall(plat.lower()))


def distinctifs(vise):
    """The words that carry identity. If none survive, keep them all: a title
    made entirely of common words exists ("The Witness")."""
    utiles = vise - _VIDES
    return utiles or vise


def couverture(candidat, cherche):
    """Share of the distinctive words of `cherche` that `candidat` repeats, 0 to 1."""
    vise = distinctifs(mots(cherche))
    if not vise:
        return 0.0
    return len(vise & mots(candidat)) / len(vise)


def assez_proche(candidat, cherche, seuil=2 / 3):
    """Does the candidate cover enough of what was being searched for?"""
    vise = distinctifs(mots(cherche))
    if not vise:
        return False
    requis = max(1, math.ceil(len(vise) * seuil))
    return len(vise & mots(candidat)) >= requis


def meilleur(candidats, cherche, nom=lambda x: x):
    """The closest candidate, or None if none is close enough.

    At equal coverage the SHORTEST title wins: it adds fewer words nobody asked
    for, so it strays less — which is what separates "Mario Kart 8" from
    "Mario Kart 8 Deluxe Booster Course Pass".
    """
    retenus = [c for c in (candidats or []) if assez_proche(nom(c), cherche)]
    if not retenus:
        return None
    return max(retenus, key=lambda c: (couverture(nom(c), cherche),
                                       -len(mots(nom(c)))))
