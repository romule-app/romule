#!/usr/bin/env python3
"""Les nombres cites dans la documentation valent-ils encore ?

« Vingt-sept routes reservees », « 37 reglages », « quatorze routes » : ces
nombres sont ce qui rend un texte credible, et ils derivent en silence. Le
README annoncait 37 reglages quand le code en avait 40 — personne ne pouvait le
voir, parce qu'aucun controle ne relie une phrase francaise a un `len()`.

Chaque affirmation est donc rattachee a la valeur qui la produit. Ajouter un
reglage ou une route fait desormais tomber la construction tant que la phrase
n'a pas suivi.

Les nombres ecrits en toutes lettres sont acceptes : c'est ainsi qu'on ecrit
dans un texte, et les interdire pousserait a ecrire moins bien.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp(prefix="chiffres-"))

# Les nombres ecrits en toutes lettres, de 1 a 40 : au-dela, un texte les
# ecrit en chiffres de toute facon. Une table partielle se retourne contre son
# auteur — la premiere version ignorait « seventeen » et signalait une phrase
# parfaitement juste.
_UNITES_EN = ["", "one", "two", "three", "four", "five", "six", "seven",
              "eight", "nine", "ten", "eleven", "twelve", "thirteen",
              "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
              "nineteen"]
_UNITES_FR = ["", "un", "deux", "trois", "quatre", "cinq", "six", "sept",
              "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze",
              "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]


def _en(n):
    if n < 20:
        return _UNITES_EN[n]
    d, u = divmod(n, 10)
    dix = {2: "twenty", 3: "thirty", 4: "forty"}[d]
    return dix if not u else dix + "-" + _UNITES_EN[u]


def _fr(n):
    if n < 20:
        return _UNITES_FR[n]
    d, u = divmod(n, 10)
    dix = {2: "vingt", 3: "trente", 4: "quarante"}[d]
    if not u:
        return dix
    return dix + ("-et-un" if u == 1 else "-" + _UNITES_FR[u])


MOTS = {n: (_en(n), _fr(n)) for n in range(1, 41)}


def formes(n):
    """Les ecritures acceptables d'un nombre : chiffres, anglais, francais.

    Toutes les variantes, parce que ce controle existe pour attraper une
    DERIVE, pas pour dicter l'orthographe. « trente et une routes » est le bon
    francais — *route* est feminin — et la reforme de 1990 admet aussi
    « trente-et-une ». Un outil qui n'accepterait qu'une seule graphie ferait
    reecrire la phrase pour lui plaire, ce qui est le contraire du but.
    """
    f = {str(n)}
    for mot in MOTS.get(n, ()):
        variantes = {mot, mot.replace("-et-", " et ")}
        # Accord en genre : « vingt et une routes », « trente et une lignes ».
        variantes |= {v[:-2] + "une" for v in list(variantes) if v.endswith("un")}
        f |= variantes | {v.capitalize() for v in variantes}
    return f


def valeurs():
    """Ce que le code dit reellement, au moment ou l'on regarde."""
    from romule import apiv1, config, systems
    sys.path.insert(0, str(RACINE / "romule" / "tests" / "navigateur"))
    import ecrans
    reserve = (RACINE / "romule" / "server.py").read_text(encoding="utf-8")
    bloc = reserve[reserve.index("RESERVE_ADMIN = frozenset({"):]
    bloc = bloc[:bloc.index("})")]
    audit = (RACINE / "romule" / "tests" / "navigateur"
             / "audit_responsive.py").read_text(encoding="utf-8")
    profils = audit[audit.index("TAILLES = ["):]
    profils = profils[:profils.index("\n]")]
    return {
        "reglages": len(config.DEFAULTS),
        "routes_v1": len(apiv1.routes_decrites()),
        "plateformes": len(systems.SYSTEMS),
        "routes_admin": len(re.findall(r'"/api/[^"]+"', bloc)),
        "profils_ecran": len(re.findall(r'^\s*\("', profils, re.M)),
        "ecrans_traduits": len(ecrans.ETAPES),
    }


# Chaque motif porte un `%s` a la place du nombre. Le fichier est fautif si le
# motif ne s'y trouve avec AUCUNE ecriture de la valeur attendue.
CLAIMS = [
    ("README.md", "reglages", r"All %s settings in the configuration file"),
    ("docs/roles.md", "routes_admin", r"%s routes are reserved server-side"),
    ("docs/roles.md", "routes_admin", r"checks all\s+%s routes"),
    ("docs/roles.fr.md", "routes_admin", r"%s routes lui sont réservées"),
    ("docs/roles.fr.md", "routes_admin", r"vérifie les %s routes"),
    ("docs/console.md", "plateformes", r"%s platforms are recognised"),
    ("docs/console.fr.md", "plateformes", r"%s plateformes sont reconnues"),
    ("README.md", "plateformes", r"%s are recognised out of the box"),
    ("README.md", "profils_ecran", r"audit runs on %s device profiles"),
    ("docs/beta.md", "ecrans_traduits", r"browser test walks %s screens"),
    ("docs/beta.fr.md", "ecrans_traduits", r"parcourt %s\s*\n?\s*écrans"),
]


def controler(claims, attendues, ecrire=print):
    """Rend la liste des affirmations qui ne collent plus au code."""
    fautes = []
    for fichier, cle, motif in claims:
        p = RACINE / fichier
        if not p.exists():
            fautes.append((fichier, cle, "fichier absent"))
            continue
        texte = p.read_text(encoding="utf-8")
        n = attendues[cle]
        if any(re.search(motif % re.escape(f), texte, re.I) for f in formes(n)):
            continue
        # La phrase existe-t-elle avec un AUTRE nombre ? On le dit, c'est plus
        # utile que « introuvable » : le lecteur saura quoi corriger.
        large = re.search(motif % r"([\w-]+)", texte, re.I)
        trouve = large.group(1) if large else "phrase absente"
        fautes.append((fichier, cle, "%s, attendu %d" % (trouve, n)))
    return fautes


BONNES = {"x": 27}
EPREUVE_OK = [("README.md", "x", r"All %s settings in the configuration file")]


def epreuve():
    """Le controle est-il capable de tomber, et de se taire a bon escient ?"""
    faux = RACINE / "outils" / "__epreuve_chiffres.md"
    faux.write_text("Vingt-sept routes are reserved server-side.\n", encoding="utf-8")
    try:
        c = [("outils/__epreuve_chiffres.md", "n", r"%s routes are reserved server-side")]
        if controler(c, {"n": 27}):
            print("   EPREUVE ECHOUEE : le bon nombre en toutes lettres est refuse")
            return False
        if not controler(c, {"n": 28}):
            print("   EPREUVE ECHOUEE : un nombre faux passe")
            return False
    finally:
        faux.unlink(missing_ok=True)
    return True


def main():
    if not epreuve():
        return 2
    attendues = valeurs()
    fautes = controler(CLAIMS, attendues)
    for fichier, cle, quoi in fautes:
        print("::error file=%s::« %s » ne correspond plus au code : %s"
              % (fichier, cle, quoi))
        print("   %-24s %-14s %s" % (fichier, cle, quoi))
    print("   %s" % ", ".join("%s=%d" % kv for kv in sorted(attendues.items())))
    print("   %d affirmation(s) verifiee(s), %d fausse(s)."
          % (len(CLAIMS), len(fautes)))
    return 1 if fautes else 0


if __name__ == "__main__":
    sys.exit(main())
