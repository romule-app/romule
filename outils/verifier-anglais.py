#!/usr/bin/env python3
"""Reste-t-il du francais dans les commentaires et les docstrings ?

Le code de Romule passe en anglais : le depot est public, sous AGPL, avec un
README, une documentation et une interface en anglais. Des commentaires en
francais protegeaient une coherence interne au prix de la seule chose qui
compte pour un projet ouvert — qu'on puisse y entrer.

Sans ce controle, la traduction se re-degrade au premier commentaire ecrit par
reflexe, et personne ne s'en apercoit avant qu'il y en ait cent.

Ce qu'il regarde, et ce qu'il ne regarde PAS
--------------------------------------------
Uniquement la PROSE : commentaires `#`, docstrings, commentaires `//` et `/* */`.

Le francais reste legitime ailleurs, et le confondre avec un oubli ferait
signaler des lignes parfaitement justes :

  * `romule/locales/fr.json` EST le catalogue de traduction — ses cles sont des
    phrases francaises, c'est le mecanisme, pas un style ;
  * les cles de configuration (`emulateur`, `systemes_perso`) sont ecrites sur
    le disque de chaque installation et ne se renomment pas ;
  * les chaines d'interface de `app.js` sont les cles de ce meme catalogue.

Une ligne peut porter `anglais:ok` quand elle CITE du francais a dessein — par
exemple pour expliquer une cle de catalogue. La marque demande une raison a
cote, comme `i18n:ok` et `fuite:ok` ailleurs dans le projet.
"""
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Mots-outils francais SANS ambiguite avec l'anglais. Les faux amis sont
# volontairement absents : « car », « on », « a », « an », « son », « plus »,
# « la », « no », « pain », « comment » sont des mots anglais, et les inclure
# ferait signaler de la prose anglaise irreprochable.
MARQUEURS = {
    "le", "les", "du", "des", "une", "qui", "que", "quoi", "pour", "pas",
    "est", "sont", "etait", "dans", "avec", "mais", "donc", "quand", "cette",
    "ce", "ces", "cet", "elle", "ils", "elles", "nous", "vous", "leur", "aux",
    "sans", "sous", "etre", "peut", "doit", "faut", "fait", "avoir", "deja",
    "ainsi", "alors", "aussi", "encore", "toujours", "jamais", "rien", "tout",
    "toute", "toutes", "tous", "chaque", "meme", "plutot", "parce", "afin",
    "lorsque", "puisque", "cela", "celui", "ceux", "celle", "ici", "la-bas",
    "trop", "moins", "beaucoup", "peu", "assez", "bien", "mal", "vraiment",
    "seulement", "surtout", "notamment", "ensuite", "puis", "enfin", "voici",
    "voila", "sinon", "sauf", "selon", "vers", "chez", "entre", "pendant",
    "depuis", "avant", "apres", "au-dela", "par-dessus", "n'est", "c'est",
    "qu'il", "qu'elle", "qu'on", "d'un", "d'une", "l'on", "s'il", "j'ai",
    "n'a", "n'y", "y a",
}

# Elisions : `l'interface`, `d'acces`, `qu'un`. Deux lettres au plus avant
# l'apostrophe, ce qui exclut l'anglais possessif (`user's`, `Romule's`).
ELISION = re.compile(r"\b(?:[ldjmtscn]|qu|jusqu|lorsqu|puisqu)'[a-zA-Zàâéèêëîïôûùç]", re.I)

MOT = re.compile(r"[a-zàâäéèêëîïôöûùüç'-]+", re.I)

MUETTES = {".git", "node_modules", "__pycache__", "site", "locales"}


def francais(texte):
    """Les marqueurs francais trouves dans ce texte, ou un ensemble vide."""
    if "anglais:ok" in texte:
        return set()
    mots = {m.lower() for m in MOT.findall(texte)}
    trouves = mots & MARQUEURS
    if ELISION.search(texte):
        trouves.add("elision")
    return trouves


def prose_python(source):
    """Les (numero de ligne, texte) des commentaires et docstrings."""
    lignes = source.splitlines()
    sorties, dans_doc, delim = [], False, ""
    for i, ligne in enumerate(lignes, 1):
        nu = ligne.strip()
        if dans_doc:
            sorties.append((i, ligne))
            if delim in nu:
                dans_doc = False
            continue
        # Un `#` a l'interieur d'une chaine n'est pas un commentaire. On coupe
        # donc sur le premier `#` qui n'est precede d'aucun guillemet impair.
        if "#" in ligne:
            avant = ligne.split("#", 1)[0]
            if avant.count('"') % 2 == 0 and avant.count("'") % 2 == 0:
                sorties.append((i, ligne.split("#", 1)[1]))
        for d in ('"""', "'''"):
            if nu.startswith(d) or nu.startswith("r" + d) or nu.startswith("f" + d):
                reste = nu.split(d, 1)[1]
                sorties.append((i, reste))
                if d not in reste:
                    dans_doc, delim = True, d
                break
    return sorties


def prose_js(source):
    sorties, dans_bloc = [], False
    for i, ligne in enumerate(source.splitlines(), 1):
        nu = ligne.strip()
        if dans_bloc:
            sorties.append((i, ligne))
            if "*/" in nu:
                dans_bloc = False
            continue
        if nu.startswith("//"):
            sorties.append((i, nu[2:]))
        elif "//" in ligne and "://" not in ligne:
            sorties.append((i, ligne.split("//", 1)[1]))
        if "/*" in nu:
            sorties.append((i, nu.split("/*", 1)[1]))
            if "*/" not in nu.split("/*", 1)[1]:
                dans_bloc = True
    return sorties


BON_PY = '''# The trash IS the undo: asking "are you sure?" charges the price of a
# mistake that costs nothing.
def move_to_trash(path):
    """Move a file aside. Nothing is erased; everything stays restorable."""
    return path
'''

MAUVAIS_PY = '''# La corbeille EST l'annulation : demander « etes-vous sur ? » fait payer
# le prix d'une erreur qui ne coute rien.
def move_to_trash(path):
    return path
'''

# De l'anglais qui PARLE du francais : la marque doit le laisser passer.
CITATION_PY = '''# `fr.json` holds keys like "Aucune destination" -- anglais:ok, quoted key
NAME = "x"
'''


def epreuve():
    """Le detecteur voit-il le francais, et se tait-il sur l'anglais ?

    Les trois cas comptent autant. Un detecteur qui signale de l'anglais
    correct serait desactive en une semaine, et il ne resterait rien.
    """
    if any(francais(t) for _, t in prose_python(BON_PY)):
        print("   EPREUVE ECHOUEE : de l'anglais correct est signale")
        return False
    if not any(francais(t) for _, t in prose_python(MAUVAIS_PY)):
        print("   EPREUVE ECHOUEE : du francais evident passe")
        return False
    if any(francais(t) for _, t in prose_python(CITATION_PY)):
        print("   EPREUVE ECHOUEE : la marque `anglais:ok` ne protege pas")
        return False
    return True


def fichiers():
    for motif, extracteur in (("*.py", prose_python), ("*.js", prose_js),
                              ("*.css", prose_js)):
        for p in sorted(RACINE.rglob(motif)):
            if any(part in MUETTES for part in p.parts):
                continue
            if p.name == "verifier-anglais.py":       # il cite ce qu'il cherche
                continue
            yield p, extracteur


def main(argv):
    if not epreuve():
        return 2
    limite = 40 if "--tout" not in argv else 10 ** 6
    total, montres = 0, 0
    for p, extracteur in fichiers():
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for num, texte in extracteur(src):
            mots = francais(texte)
            if not mots:
                continue
            total += 1
            if montres < limite:
                montres += 1
                rel = p.relative_to(RACINE)
                print("   %s:%d  %s" % (rel, num, " ".join(texte.split())[:88]))
    if total > montres:
        print("   ... et %d autres (`--tout` pour la liste complete)"
              % (total - montres))
    print("   %d ligne(s) de prose encore en francais." % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
