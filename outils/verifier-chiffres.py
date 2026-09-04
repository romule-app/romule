#!/usr/bin/env python3
"""Are the numbers quoted in the documentation still true?

"Twenty-seven reserved routes", "37 settings", "fourteen routes": those numbers
are what makes a text credible, and they drift in silence. The README announced
37 settings when the code had 40 — nobody could see it, because no check ties a
sentence to a `len()`.

Every claim is therefore tied to the value that produces it. Adding a setting or
a route now brings the build down until the sentence has followed.

Numbers written out in words are accepted: that is how one writes in a text, and
forbidding them would push towards writing worse.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp(prefix="chiffres-"))

# Numbers written out in words, from 1 to 40: past that, a text writes them as
# digits anyway. A partial table turns against its author — the first version did
# not know "seventeen" and reported a perfectly correct sentence.
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
    """The acceptable spellings of a number: digits, English, French.

    Every variant, because this check exists to catch DRIFT, not to dictate
    spelling. "trente et une routes" -- anglais:ok, a French example -- is the
    correct French (*route* is feminine) and the 1990 reform also admits
    "trente-et-une". A tool that accepted only one spelling would have the
    sentence rewritten to please it, which is the opposite of the point.
    """
    f = {str(n)}
    for mot in MOTS.get(n, ()):
        variantes = {mot, mot.replace("-et-", " et ")}
        # Gender agreement: "vingt et une routes", "trente et une lignes" --
        # anglais:ok, French examples.
        variantes |= {v[:-2] + "une" for v in list(variantes) if v.endswith("un")}
        f |= variantes | {v.capitalize() for v in variantes}
    return f


def valeurs():
    """What the code really says, at the moment we look."""
    from romule import apiv1, config, systems
    sys.path.insert(0, str(RACINE / "romule" / "tests" / "navigateur"))
    import ecrans
    reserve = (RACINE / "romule" / "server.py").read_text(encoding="utf-8")
    bloc = reserve[reserve.index("ADMIN_ONLY = frozenset({"):]
    bloc = bloc[:bloc.index("})")]
    audit = (RACINE / "romule" / "tests" / "navigateur"
             / "audit_responsive.py").read_text(encoding="utf-8")
    profils = audit[audit.index("TAILLES = ["):]
    profils = profils[:profils.index("\n]")]
    return {
        "reglages": len(config.DEFAULTS),
        "routes_v1": len(apiv1.documented_routes()),
        "plateformes": len(systems.SYSTEMS),
        "routes_admin": len(re.findall(r'"/api/[^"]+"', bloc)),
        "profils_ecran": len(re.findall(r'^\s*\("', profils, re.M)),
        "ecrans_traduits": len(ecrans.ETAPES),
    }


# Every pattern carries a `%s` where the number goes. The file is at fault if the
# pattern is not found there with ANY spelling of the expected value.
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
    """Returns the list of claims that no longer match the code."""
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
        # Does the sentence exist with ANOTHER number? We say so, which is more
        # useful than "not found": the reader will know what to correct.
        large = re.search(motif % r"([\w-]+)", texte, re.I)
        trouve = large.group(1) if large else "phrase absente"
        fautes.append((fichier, cle, "%s, attendu %d" % (trouve, n)))
    return fautes


BONNES = {"x": 27}
EPREUVE_OK = [("README.md", "x", r"All %s settings in the configuration file")]


def epreuve():
    """Can the check fall, and can it keep quiet when it should?"""
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
