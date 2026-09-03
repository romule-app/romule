"""A wrong entry is worse than a missing one.

`covers.sgdb_infos()` took the FIRST autocomplete result, checking nothing. On
"Crazy Construction", SteamGridDB returns a game called "Crazy" first — and since
that title then serves as the pivot for querying IGDB, the card displayed the
name AND the summary of a different game.

A missing entry is SEEN: the card stays plain, and the "no cover" filter finds
it. A wrong entry is BELIEVED, and casts doubt over the whole grid.

The threshold is deliberately strict. This test holds both halves: what must be
accepted is, and what must be rejected is — otherwise one defect would simply
have been traded for the other.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from romule import matching as m                                 # noqa: E402

ok = ko = 0


def t(name, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        ko += 1
        print("  FAIL %s   %s" % (name, detail))


# (candidate, what was being searched for, should it be accepted, why)
CASES = [
    ("Crazy", "Crazy Construction", False,
     "the real case: one word out of two is not enough"),
    ("Crazy Construction", "Crazy Construction", True, "exact"),
    ("Batman: Arkham Asylum", "Batman Arkham Asylum", True,
     "punctuation does not count"),
    ("Pokémon FireRed Version", "Pokemon FireRed", True,
     "accents are normalised, \"Version\" is a stopword"),
    ("Pokémon Version Rouge Feu", "Pokemon FireRed", False,
     "same game, another language: there is no way to know"),
    ("Animal Crossing: New Horizons", "Animal Crossing New Horizons", True, ""),
    ("Hogwarts Legacy Digital Deluxe", "Hogwarts Legacy", True,
     "a longer candidate stays good if it covers everything"),
    ("Sonic", "Sonic Frontiers", False, "the same trap as \"Crazy\""),
    ("The Witness", "The Witness", True,
     "a title made entirely of common words exists"),
    ("Mario Kart 8 Deluxe", "Mario Kart 8 Deluxe", True, ""),
    ("Doom", "Doom Eternal", False, ""),
    ("", "Crazy Construction", False, "an empty candidate is never good"),
    ("Crazy Construction", "", False, "with no query, nothing can be concluded"),
]


def test_the_threshold():
    for candidate, wanted, expected, why in CASES:
        v = m.close_enough(candidate, wanted)
        t("%-30s <- %-28s %s" % (repr(candidate)[:30], repr(wanted)[:28],
                                 "accepted" if expected else "rejected"),
          v == expected, "got %s  (%s)" % (v, why))


def test_the_best_is_the_shortest():
    """At equal coverage, the title that adds the fewest words wins: that is
    what separates "Mario Kart 8" from a downloadable-content pass."""
    candidates = [{"n": "Mario Kart 8 Deluxe Booster Course Pass"},
                  {"n": "Mario Kart 8 Deluxe"}]
    choice = m.best(candidates, "Mario Kart 8 Deluxe", name=lambda c: c["n"])
    t("the shortest wins at equal coverage",
      choice and choice["n"] == "Mario Kart 8 Deluxe", choice)


def test_no_acceptable_candidate():
    candidates = [{"n": "Crazy"}, {"n": "Crazy Taxi"}, {"n": "Crazy Machines"}]
    choice = m.best(candidates, "Crazy Construction", name=lambda c: c["n"])
    t("no close candidate: we return nothing", choice is None, choice)


def test_empty_list():
    t("an empty list does not bring it down", m.best([], "Anything at all") is None)


def test_both_sources_use_the_rule():
    """The matching must serve BOTH title sources. Wired into only one, the
    other would go on returning the wrong game."""
    root = Path(__file__).resolve().parent.parent
    for filename in ("covers.py", "igdb.py"):
        src = (root / filename).read_text(encoding="utf-8")
        t("%s goes through the matching" % filename,
          "matching." in src, filename)
    src = (root / "covers.py").read_text(encoding="utf-8")
    # It is the SEARCH's result that must no longer be taken blind. The `[0]`
    # that remains is about the covers of an ALREADY identified game: at that
    # stage, taking the first image is the right move.
    t("covers.py no longer takes the first search result blind",
      'found["data"][0]' not in src)


for fn in (test_the_threshold, test_the_best_is_the_shortest,
           test_no_acceptable_candidate, test_empty_list,
           test_both_sources_use_the_rule):
    fn()
print("  %d checks OK, %d failure(s)" % (ok, ko))
sys.exit(1 if ko else 0)
