#!/usr/bin/env python3
"""Every route the interface calls must be one the server answers.

Why this exists
---------------
The rename to English translated `'/api/parcourir'` into `'/api/browseServer'`
inside `app.js` — a STRING, not an identifier — while the server kept the route
it always had. The "choose another folder" button of the setup wizard therefore
called a route that does not exist, and the server answered
`route inconnue`. On screen: nothing. The failure is quiet by design, because
running into a forbidden folder while browsing is ordinary and an error dialog
on every click would be worse than the problem.

Nothing could see it. `ruff` reads Python, `verifier-traduction.py` reads
sentences, `verifier-imports.py` reads imports and attributes. A route is a
string on one side and a comparison on the other: the coupling only exists at
run time, and only when somebody clicks.

This is the same shape as the `data-act` three-place coupling that
`test_ui_injection.js` guards, one layer further out.

What it does NOT do
-------------------
It does not report a server route the interface never calls: `/api/v1/*` is a
public API meant for other clients, and half the internal routes are used by
the CLI or by a dashboard rather than by `app.js`. Absence of a caller is not a
defect; a caller with no route is.
"""
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
APP = RACINE / "romule" / "static" / "app.js"
SERVEUR = RACINE / "romule" / "server.py"

# `api('/api/x')`, `fetch('/api/x')`, and the same in double quotes.
APPEL = re.compile(r"""(?:api|fetch)\(\s*['"](/api/[\w./-]+)['"]""")
# A route the server compares against, plus the ones it lists (reserves,
# rate limits): a listed route is one it knows about.
ROUTE = re.compile(r"""["'](/api/[\w./-]+)["']""")


def appelees(source):
    """The routes this source CALLS.

    Comments are cut here rather than by the caller, so that what the self-test
    judges is what actually runs: a route named in a note about its own removal
    is not a call, and reporting it for ever would get the tool switched off.
    """
    return set(APPEL.findall(re.sub(r"//[^\n]*", "", source)))


def connues(source):
    return set(ROUTE.findall(source))


BON = """
  const r = await api('/api/parcourir', {chemin: ''});
"""
MAUVAIS = """
  const r = await api('/api/browseServer', {chemin: ''});
"""
SERVEUR_FACTICE = '''
        elif p == "/api/parcourir":
            self._json(browse.listing(d.get("chemin")))
'''


def epreuve():
    """Does it see the defect, and stay quiet on the sound version?"""
    su = connues(SERVEUR_FACTICE)
    if appelees(BON) - su:
        print("   SELF-TEST FAILED: a route that exists is reported")
        return False
    if not appelees(MAUVAIS) - su:
        print("   SELF-TEST FAILED: a route that does not exist gets through")
        return False
    # A route named in a comment is not a call: the detector must read calls.
    if appelees("// api('/api/inventee') was removed in 0.3") - su:
        print("   SELF-TEST FAILED: a route quoted in a comment is reported")
        return False
    return True


def main():
    if not epreuve():
        return 2
    js = APP.read_text(encoding="utf-8")
    manquantes = sorted(appelees(js) - connues(SERVEUR.read_text(encoding="utf-8")))
    for r in manquantes:
        print("   %s  appelee par app.js, inconnue du serveur" % r)
    print("   %d route(s) appelee(s), %d sans reponse."
          % (len(appelees(js)), len(manquantes)))
    return 1 if manquantes else 0


if __name__ == "__main__":
    sys.exit(main())
