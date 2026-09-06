#!/usr/bin/env python3
"""The sentences the SERVER writes are read in the interface too.

`job.log("Console non connectee.")` lands in the Log panel, beside everything
`app.js` writes. `app.js`'s sentences go through the catalogue; the server's did
not, so an English interface showed French lines with no warning — which is what
a user reported, on that exact sentence.

They need no `t()` call: the interface's MutationObserver translates every text
node whose sentence is a catalogue key. The only thing missing was the key. So
this checks the one thing that can be checked: that each FIXED sentence the
server logs exists in `fr.json`.

It covers two shapes: what the server LOGS, and what it ANSWERS —
`{"error": ...}` and `{"message": ...}`, which `app.js` shows as they arrive. A
refused SteamGridDB key answered "Cle refusee par SteamGridDB." in an English
interface, and no catalogue held it.

What it leaves alone, and why
-----------------------------
An ENGLISH sentence is out of scope. `/api/v1` answers in English by contract —
"q is required.", "Unknown console." — and translating those would break every
client written against them. Only a French sentence is reported, because only a
French sentence is one the catalogue can carry.


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
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CATALOGUE = RACINE / "romule" / "locales" / "fr.json"
# Where a logged sentence goes to be read.
SORTIES = ("log", "say", "event")


# French function words with no ambiguity against English. A sentence carrying
# one of them — or an accent — is one the catalogue can hold.
# The false friends are deliberately absent -- anglais:ok, it lists the words
# it excludes. They are English words as well as French ones, and including
# them made `Unknown console.` — an /api/v1 message, English by contract —
# look French.
MARQUEURS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "est", "sont", "pas",
    "aucun", "aucune", "avec", "sans", "pour", "dans", "que", "qui", "deja",
    "cette", "ces", "vers", "chez", "hors", "trop", "abord", "toujours",
    "jamais", "cle", "jeton", "dossier", "chemin", "compte", "acces", "tache",
    "reglages", "adresse", "requete", "sauvegarde", "connexion", "mot",
    "introuvable", "inconnue", "inconnu", "manquante", "manquant", "refusee",
    "refuse", "enregistre", "enregistree", "connectee", "connecte", "non",
    "prete", "engendre", "efface", "interrompue", "annulee", "reessaie",
    "autorises", "desactivee", "activee", "retiree", "abandonnee",
}
_MOT = re.compile(r"[a-zàâäéèêëîïôöûùüç']+", re.I)


def francaise(texte):
    """Is this a sentence the catalogue could carry?"""
    if any(c in texte for c in "àâäéèêëîïôöûùüçÀÉÈÊÎÔÛÙÇ«»"):
        return True
    return bool({m.lower() for m in _MOT.findall(texte)} & MARQUEURS)


def phrases(source):
    """The fixed French sentences this source shows: (line, text).

    Two shapes: what it LOGS, and what it ANSWERS — the interface renders both,
    side by side in the Log panel and in a toast.
    """
    out = []
    arbre = ast.parse(source)
    for n in ast.walk(arbre):
        candidats = []
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in SORTIES:
            if n.args and isinstance(n.args[0], ast.Constant):
                candidats.append(n.args[0])
        elif isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values, strict=False):
                if (isinstance(k, ast.Constant) and k.value in ("error", "message")
                        and isinstance(v, ast.Constant)):
                    candidats.append(v)
        elif isinstance(n, ast.Tuple) and len(n.elts) == 2:
            # `return (False, "...")`: how the probes answer.
            a, b = n.elts
            if (isinstance(a, ast.Constant) and a.value is False
                    and isinstance(b, ast.Constant)):
                candidats.append(b)
        for c in candidats:
            v = c.value
            # A template is assembled server-side and cannot be a key; a single
            # word is a label, not a sentence somebody reads for meaning; an
            # English one belongs to the /api/v1 contract.
            if (isinstance(v, str) and "%" not in v and len(v.split()) >= 2
                    and francaise(v)):
                out.append((c.lineno, v))
    return out


BON = '''
job.log("Console non connectee.")
'''
REPONSE = '''
self._json({"error": "Cle refusee par SteamGridDB."}, 400)
'''
CONTRAT_V1 = '''
self._json({"error": "Unknown console."}, 404)
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
    if not phrases(REPONSE):
        print("   SELF-TEST FAILED: an answered sentence is not seen")
        return False
    # The /api/v1 contract is English on purpose: translating it would break
    # every client written against it.
    if phrases(CONTRAT_V1):
        print("   SELF-TEST FAILED: an English API message is reported")
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
