#!/usr/bin/env python3
"""Every sentence `romule/messages.py` holds must be in the catalogue.

The sentences the server writes are read in the interface too:
`job.log(messages.CONSOLE_NON_CONNECTEE)` lands in the Log panel beside
everything `app.js` writes, and `{"error": …}` comes back as a toast. They need
no `t()` call — the interface's MutationObserver translates any text node whose
sentence is a catalogue key — so the only thing that can go missing is the key.

This used to walk thirty files looking for the shapes that reach a user. It no
longer has to: every one of those sentences now lives in one module, named. The
check is therefore exact rather than heuristic, and the place to look when it
fails is a single file.

What it leaves alone
--------------------
The `V1_` constants. `/api/v1` answers in English by contract — "Unknown
console.", "q is required." — and translating them would break every client
written against them.

A sentence carrying a `%s` is still a key: the interface resolves the template
on the client. What is NOT a key is a sentence assembled by the server from
several pieces, and none of those live here.

The second half: the CALL SITES
-------------------------------
Naming the sentences is only half of it. The terminal translates what it is
given — `console._dire` looks the sentence up in the same catalogue — so a call
site writing its own text bypasses the whole mechanism and prints French into an
English log. Worse, a call site that INTERPOLATES first
(`job.log("Rangé : %s" % nom)`) hands over a string no catalogue can hold: the
lookup misses silently, and nothing anywhere reports it.

So every literal reaching a logging call must be a catalogue key, and one
carrying values must arrive unassembled, through `langue.phrase(...)`.
"""
import ast
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from romule import messages                                      # noqa: E402

CATALOGUE = RACINE / "romule" / "locales" / "fr.json"


def phrases():
    """(name, sentence) for everything the module offers, contract aside."""
    return [(nom, getattr(messages, nom)) for nom in sorted(dir(messages))
            if nom.isupper() and not nom.startswith("V1_")
            and isinstance(getattr(messages, nom), str)]


def contrat():
    return [(nom, getattr(messages, nom)) for nom in sorted(dir(messages))
            if nom.startswith("V1_") and isinstance(getattr(messages, nom), str)]


def _sorties(arbre):
    """(node, interpolated?) for the first argument of every logging call."""
    out = []
    for n in ast.walk(arbre):
        if not isinstance(n, ast.Call) or not n.args:
            continue
        f = n.func
        vise = (isinstance(f, ast.Attribute)
                and ((isinstance(f.value, ast.Name) and f.value.id == "console"
                      and f.attr in ("say", "event")) or f.attr == "log"))
        if not vise:
            continue
        a = n.args[0]
        interp = isinstance(a, ast.BinOp) and isinstance(a.op, ast.Mod)
        g = a.left if interp else a
        if isinstance(g, ast.Constant) and isinstance(g.value, str):
            out.append((n.lineno, g.value, interp))
    return out


def points_d_appel(source, catalogue):
    """What a file's logging calls get wrong."""
    soucis = []
    for ligne, texte, interp in _sorties(ast.parse(source)):
        if not texte.strip():
            continue
        if interp:
            soucis.append((ligne, "assemblee avant la traduction", texte))
        elif texte not in catalogue:
            soucis.append((ligne, "hors catalogue", texte))
    return soucis


BON = 'job.log(messages.RANGE)\nconsole.say(langue.phrase(messages.RANGE, n))\n'
ASSEMBLEE = 'job.log("Rangé : %s" % nom)\n'
INCONNUE = 'job.log("Une phrase que personne n\'a mise au catalogue.")\n'
AILLEURS = 'print("Rangé : %s" % nom)\n'


def epreuve():

    """Does it see the module, and tell the two halves apart?"""
    if not phrases():
        print("   EPREUVE ECHOUEE : aucune phrase lue dans messages.py")
        return False
    if any(nom.startswith("V1_") for nom, _ in phrases()):
        print("   EPREUVE ECHOUEE : le contrat /api/v1 est melange aux phrases")
        return False
    if not contrat():
        print("   EPREUVE ECHOUEE : le contrat /api/v1 n'est pas reconnu")
        return False
    # A sentence with no accent at all, in a French corpus, is what this whole
    # module was written to stop coming back.
    cat = {"Rangé : %s": "Filed: %s"}
    if points_d_appel(BON, cat):
        print("   EPREUVE ECHOUEE : un point d'appel correct est signale")
        return False
    if not points_d_appel(ASSEMBLEE, cat):
        print("   EPREUVE ECHOUEE : une phrase assemblee avant traduction passe")
        return False
    if not points_d_appel(INCONNUE, cat):
        print("   EPREUVE ECHOUEE : une phrase hors catalogue passe")
        return False
    if points_d_appel(AILLEURS, cat):
        print("   EPREUVE ECHOUEE : un print() est pris pour un journal")
        return False
    return True


def main():
    if not epreuve():
        return 2
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    manquantes = [(n, t) for n, t in phrases() if t not in catalogue]
    for nom, texte in manquantes:
        print("   messages.%s n'est pas au catalogue : %s" % (nom, texte[:64]))
    if manquantes:
        print("   %d phrase(s) hors catalogue : elles s'afficheront en francais"
              " dans une interface anglaise." % len(manquantes))
    fautes = []
    for f in sorted((RACINE / "romule").glob("*.py")):
        try:
            fautes += [(f.name,) + x
                       for x in points_d_appel(f.read_text(encoding="utf-8"),
                                               catalogue)]
        except SyntaxError:
            continue
    for nom, ligne, quoi, texte in fautes:
        print("   %s:%d  %s : %s" % (nom, ligne, quoi, texte[:56]))
    print("   %d phrase(s) dans messages.py, %d du contrat /api/v1, %d hors"
          " catalogue, %d point(s) d'appel fautif(s)."
          % (len(phrases()), len(contrat()), len(manquantes), len(fautes)))
    return 1 if (manquantes or fautes) else 0


if __name__ == "__main__":
    sys.exit(main())
