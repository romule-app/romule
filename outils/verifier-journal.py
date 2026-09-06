#!/usr/bin/env python3
"""The sentences the SERVER logs are read in the interface too.

`job.log("Console non connectee.")` lands in the Log panel, beside everything
`app.js` writes. `app.js`'s sentences go through the catalogue; the server's did
not, so an English interface showed French lines with no warning — which is what
a user reported, on that exact sentence.

They need no `t()` call: the interface's MutationObserver translates every text
node whose sentence is a catalogue key. The only thing missing was the key. So
this checks the one thing that can be checked: that each FIXED sentence the
server logs exists in `fr.json`.

What it leaves alone, and why
-----------------------------
A sentence carrying a `%s` is not a key: the catalogue holds templates for the
interface, resolved on the client from the format AND its arguments, and the
server sends an already-assembled line. Translating those needs a server-side
i18n Romule does not have — the limit is written in `docs/beta.md`. Reporting
them here would mean reporting something nobody can fix, which is how a check
gets ignored.

The key is the sentence AS THE SERVER WRITES IT, accents and all. Most of the
server's are unaccented; that is not tidy, but a key that does not match to the
byte translates nothing, and matching is the whole job.
"""
import ast
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CATALOGUE = RACINE / "romule" / "locales" / "fr.json"
# Where a logged sentence goes to be read.
SORTIES = ("log", "say", "event")


def phrases(source):
    """The fixed sentences this source logs: (line, text)."""
    out = []
    for n in ast.walk(ast.parse(source)):
        if not isinstance(n, ast.Call) or getattr(n.func, "attr", "") not in SORTIES:
            continue
        if not n.args or not isinstance(n.args[0], ast.Constant):
            continue
        v = n.args[0].value
        # A template is assembled server-side and cannot be a key; a single
        # word is a label, not a sentence somebody reads for meaning.
        if isinstance(v, str) and "%" not in v and len(v.split()) >= 2:
            out.append((n.lineno, v))
    return out


BON = '''
job.log("Console non connectee.")
'''
GABARIT = '''
job.log("Copie de %s vers la console." % nom)
'''
UN_MOT = '''
job.log("Termine.")
'''


def epreuve():
    """The shape it must catch, and the two it must leave alone."""
    if not phrases(BON):
        print("   SELF-TEST FAILED: a fixed sentence is not seen")
        return False
    if phrases(GABARIT):
        print("   SELF-TEST FAILED: a template is reported, and nobody can fix it")
        return False
    if phrases(UN_MOT):
        print("   SELF-TEST FAILED: a single word is reported")
        return False
    return True


def main():
    if not epreuve():
        return 2
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    total = manquantes = 0
    for chemin in sorted((RACINE / "romule").glob("*.py")):
        for ligne, texte in phrases(chemin.read_text(encoding="utf-8")):
            total += 1
            if texte not in catalogue:
                manquantes += 1
                print("   %s:%d  %s"
                      % (chemin.relative_to(RACINE), ligne, texte[:78]))
    if manquantes:
        print("   %d phrase(s) journalisee(s) hors catalogue : elles s'afficheront"
              " en francais dans une interface anglaise." % manquantes)
    print("   %d phrase(s) fixe(s) journalisee(s), %d hors catalogue."
          % (total, manquantes))
    return 1 if manquantes else 0


if __name__ == "__main__":
    sys.exit(main())
