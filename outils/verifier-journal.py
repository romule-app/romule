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
"""
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
    print("   %d phrase(s) dans messages.py, %d du contrat /api/v1, %d hors"
          " catalogue." % (len(phrases()), len(contrat()), len(manquantes)))
    return 1 if manquantes else 0


if __name__ == "__main__":
    sys.exit(main())
