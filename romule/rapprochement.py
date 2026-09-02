"""Ce candidat correspond-il vraiment a ce qu'on cherchait ?

Deux sources donnent un titre officiel a partir d'un nom de fichier :
SteamGridDB pour les jeux sans identifiant, IGDB pour les resumes. Toutes deux
rendent une LISTE de candidats classes par leur propre pertinence, qui n'est
pas la notre : elles cherchent a repondre quelque chose, nous cherchons a
repondre juste.

`covers.sgdb_infos()` prenait le premier resultat, sans rien verifier. Sur
« Crazy Construction », SteamGridDB rendait un jeu nomme « Crazy » — et comme
ce titre sert ensuite de pivot pour interroger IGDB, la carte affichait le nom
ET le resume d'un autre jeu. Un seul `[0]` non verifie produisait les deux
defauts, et le resultat etait pire qu'une fiche absente : une fiche absente se
voit, une fiche fausse se croit.

La regle
--------
Un candidat doit couvrir la MAJORITE des mots cherches. « Crazy » couvre un mot
sur deux : ce n'est pas assez. « Batman: Arkham Asylum » couvre les trois mots
de « Batman Arkham Asylum » : c'est le bon.

Le seuil est aux deux tiers, arrondi au superieur — donc deux mots sur deux,
deux sur trois, trois sur quatre. Il est volontairement severe : ne rien
afficher coute une ligne vide, afficher le mauvais jeu coute la confiance dans
tout le reste de la grille.
"""

import math
import re
import unicodedata

_MOTS = re.compile(r"[a-z0-9]+")

# Des mots qui n'aident pas a distinguer deux jeux : ils sont ignores dans le
# COMPTE, mais pas retires du candidat — « The Last of Us » ne doit pas devenir
# « Last Us » pour autant.
_VIDES = {"the", "a", "an", "of", "and", "le", "la", "les", "de", "des", "du",
          "et", "version", "edition", "deluxe", "hd", "remastered"}


def mots(texte):
    """Les mots d'un titre, accents retires.

    Sans cette normalisation, « Pokémon » se coupait en « pok » et « mon » — le
    motif ne connait que l'ASCII — et ne pouvait donc jamais correspondre a
    « Pokemon » ecrit dans un nom de fichier. C'est exactement le genre de
    detail qui aurait fait rejeter des fiches parfaitement bonnes.
    """
    plat = unicodedata.normalize("NFKD", texte or "")
    plat = "".join(c for c in plat if not unicodedata.combining(c))
    return set(_MOTS.findall(plat.lower()))


def distinctifs(vise):
    """Les mots qui portent l'identite. Si on n'en garde aucun, on garde tout :
    un titre entierement fait de mots courants existe (« The Witness »)."""
    utiles = vise - _VIDES
    return utiles or vise


def couverture(candidat, cherche):
    """Part des mots distinctifs de `cherche` que `candidat` reprend, de 0 a 1."""
    vise = distinctifs(mots(cherche))
    if not vise:
        return 0.0
    return len(vise & mots(candidat)) / len(vise)


def assez_proche(candidat, cherche, seuil=2 / 3):
    """Le candidat couvre-t-il assez de ce qu'on cherchait ?"""
    vise = distinctifs(mots(cherche))
    if not vise:
        return False
    requis = max(1, math.ceil(len(vise) * seuil))
    return len(vise & mots(candidat)) >= requis


def meilleur(candidats, cherche, nom=lambda x: x):
    """Le candidat le plus proche, ou None si aucun n'est assez proche.

    A couverture egale, le titre le plus COURT gagne : il ajoute moins de mots
    qu'on n'a pas demandes, donc il s'ecarte moins — c'est ce qui separe
    « Mario Kart 8 » de « Mario Kart 8 Deluxe Booster Course Pass ».
    """
    retenus = [c for c in (candidats or []) if assez_proche(nom(c), cherche)]
    if not retenus:
        return None
    return max(retenus, key=lambda c: (couverture(nom(c), cherche),
                                       -len(mots(nom(c)))))
