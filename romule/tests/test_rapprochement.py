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
from romule import rapprochement as r                            # noqa: E402

ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % nom)
    else:
        ko += 1
        print("  ECHEC %s   %s" % (nom, detail))


# (candidate, what was being searched for, should it be accepted, why)
CAS = [
    ("Crazy", "Crazy Construction", False,
     "le cas reel : un mot sur deux ne suffit pas"),
    ("Crazy Construction", "Crazy Construction", True, "exact"),
    ("Batman: Arkham Asylum", "Batman Arkham Asylum", True,
     "la ponctuation ne compte pas"),
    ("Pokémon FireRed Version", "Pokemon FireRed", True,
     "les accents sont normalises, « Version » est un mot vide"),
    ("Pokémon Version Rouge Feu", "Pokemon FireRed", False,
     "meme jeu, autre langue : on ne peut pas le savoir"),
    ("Animal Crossing: New Horizons", "Animal Crossing New Horizons", True, ""),
    ("Hogwarts Legacy Digital Deluxe", "Hogwarts Legacy", True,
     "un candidat plus long reste bon s'il couvre tout"),
    ("Sonic", "Sonic Frontiers", False, "meme piege que « Crazy »"),
    ("The Witness", "The Witness", True,
     "un titre entierement fait de mots courants existe"),
    ("Mario Kart 8 Deluxe", "Mario Kart 8 Deluxe", True, ""),
    ("Doom", "Doom Eternal", False, ""),
    ("", "Crazy Construction", False, "un candidat vide n'est jamais bon"),
    ("Crazy Construction", "", False, "sans requete, on ne conclut rien"),
]


def test_le_seuil():
    for cand, cherche, attendu, pourquoi in CAS:
        v = r.assez_proche(cand, cherche)
        t("%-30s <- %-28s %s" % (repr(cand)[:30], repr(cherche)[:28],
                                 "accepte" if attendu else "rejete"),
          v == attendu, "obtenu %s  (%s)" % (v, pourquoi))


def test_le_meilleur_est_le_plus_court():
    """At equal coverage, the title that adds the fewest words wins: that is
    what separates "Mario Kart 8" from a downloadable-content pass."""
    candidats = [{"n": "Mario Kart 8 Deluxe Booster Course Pass"},
                 {"n": "Mario Kart 8 Deluxe"}]
    choix = r.meilleur(candidats, "Mario Kart 8 Deluxe", nom=lambda c: c["n"])
    t("le plus court l'emporte a couverture egale",
      choix and choix["n"] == "Mario Kart 8 Deluxe", choix)


def test_aucun_candidat_acceptable():
    candidats = [{"n": "Crazy"}, {"n": "Crazy Taxi"}, {"n": "Crazy Machines"}]
    choix = r.meilleur(candidats, "Crazy Construction", nom=lambda c: c["n"])
    t("aucun candidat proche : on ne rend rien", choix is None, choix)


def test_liste_vide():
    t("une liste vide ne fait pas tomber", r.meilleur([], "Quoi que ce soit") is None)


def test_les_deux_sources_utilisent_la_regle():
    """The matching must serve BOTH title sources. Wired into only one, the
    other would go on returning the wrong game."""
    racine = Path(__file__).resolve().parent.parent
    for fichier in ("covers.py", "igdb.py"):
        src = (racine / fichier).read_text(encoding="utf-8")
        t("%s passe par le rapprochement" % fichier,
          "rapprochement." in src, fichier)
    src = (racine / "covers.py").read_text(encoding="utf-8")
    # It is the SEARCH's result that must no longer be taken blind. The `[0]`
    # that remains is about the covers of an ALREADY identified game: at that
    # stage, taking the first image is the right move.
    t("covers.py ne prend plus le premier resultat de recherche en aveugle",
      'found["data"][0]' not in src)


for fn in (test_le_seuil, test_le_meilleur_est_le_plus_court,
           test_aucun_candidat_acceptable, test_liste_vide,
           test_les_deux_sources_utilisent_la_regle):
    fn()
print("  %d controles OK, %d echec(s)" % (ok, ko))
sys.exit(1 if ko else 0)
