"""Une fiche fausse est pire qu'une fiche absente.

`covers.sgdb_infos()` prenait le PREMIER resultat de l'autocompletion, sans
rien verifier. Sur « Crazy Construction », SteamGridDB rend d'abord un jeu
nomme « Crazy » — et comme ce titre sert ensuite de pivot pour interroger IGDB,
la carte affichait le nom ET le resume d'un autre jeu.

Une fiche absente se VOIT : la carte reste sobre, le filtre « sans jaquette »
la trouve. Une fiche fausse se CROIT, et jette un doute sur toute la grille.

Le seuil est severe a dessein. Ce test tient les deux moities : ce qui doit
etre accepte l'est, et ce qui doit etre rejete l'est — sinon on aurait
simplement echange un defaut contre l'autre.
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


# (candidat, ce qu'on cherchait, doit-on l'accepter, pourquoi)
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
    """A couverture egale, le titre qui ajoute le moins de mots gagne : c'est
    ce qui separe « Mario Kart 8 » d'un pass de contenu additionnel."""
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
    """Le rapprochement doit servir aux DEUX sources de titre. Cablé dans une
    seule, l'autre continuerait de rendre le mauvais jeu."""
    racine = Path(__file__).resolve().parent.parent
    for fichier in ("covers.py", "igdb.py"):
        src = (racine / fichier).read_text(encoding="utf-8")
        t("%s passe par le rapprochement" % fichier,
          "rapprochement." in src, fichier)
    src = (racine / "covers.py").read_text(encoding="utf-8")
    # C'est le resultat de la RECHERCHE qui ne doit plus etre pris en aveugle.
    # Le `[0]` qui reste porte sur les jaquettes d'un jeu DEJA identifie : a ce
    # stade, prendre la premiere image est le bon geste.
    t("covers.py ne prend plus le premier resultat de recherche en aveugle",
      'found["data"][0]' not in src)


for fn in (test_le_seuil, test_le_meilleur_est_le_plus_court,
           test_aucun_candidat_acceptable, test_liste_vide,
           test_les_deux_sources_utilisent_la_regle):
    fn()
print("  %d controles OK, %d echec(s)" % (ok, ko))
sys.exit(1 if ko else 0)
