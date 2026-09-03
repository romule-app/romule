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

_WORDS = re.compile(r"[a-z0-9]+")

# Words that do not help tell two games apart: they are ignored in the COUNT,
# but not stripped from the candidate — "The Last of Us" must not become
# "Last Us" along the way.
_STOPWORDS = {"the", "a", "an", "of", "and", "le", "la", "les", "de", "des",
              "du", "et", "version", "edition", "deluxe", "hd", "remastered"}


def words(text):
    """The words of a title, with accents removed.

    Without this normalisation, "Pokémon" was split into "pok" and "mon" — the
    pattern only knows ASCII — and could therefore never match "Pokemon" as
    written in a file name. Exactly the kind of detail that would have rejected
    perfectly good entries.
    """
    flat = unicodedata.normalize("NFKD", text or "")
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return set(_WORDS.findall(flat.lower()))


def distinctive(target):
    """The words that carry identity. If none survive, keep them all: a title
    made entirely of common words exists ("The Witness")."""
    useful = target - _STOPWORDS
    return useful or target


def coverage(candidate, wanted):
    """Share of the distinctive words of `wanted` that `candidate` repeats, 0 to 1."""
    target = distinctive(words(wanted))
    if not target:
        return 0.0
    return len(target & words(candidate)) / len(target)


def close_enough(candidate, wanted, threshold=2 / 3):
    """Does the candidate cover enough of what was being searched for?"""
    target = distinctive(words(wanted))
    if not target:
        return False
    required = max(1, math.ceil(len(target) * threshold))
    return len(target & words(candidate)) >= required


def best(candidates, wanted, name=lambda x: x):
    """The closest candidate, or None if none is close enough.

    At equal coverage the SHORTEST title wins: it adds fewer words nobody asked
    for, so it strays less — which is what separates "Mario Kart 8" from
    "Mario Kart 8 Deluxe Booster Course Pass".
    """
    kept = [c for c in (candidates or []) if close_enough(name(c), wanted)]
    if not kept:
        return None
    return max(kept, key=lambda c: (coverage(name(c), wanted),
                                    -len(words(name(c)))))
