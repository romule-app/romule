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

# `api('/api/x')`, `fetch('/api/x')`, and the same in double quotes. The rest
# of the call matters as much as the path: `api()` sends a GET when it has no
# body, so `api('/api/x')` and `api('/api/x', {})` reach two different halves of
# the server. The wizard's « chercher la console » called a POST-only route
# without a body and came back "route inconnue" — a dialog telling the user
# their server was out of date.
APPEL = re.compile(
    r"""(?:api|fetch)\(\s*['"](/api/[\w./-]+)['"]\s*(,\s*[^)]*)?\)""")
# A route the server compares against, plus the ones it lists (reserves,
# rate limits): a listed route is one it knows about.
ROUTE = re.compile(r"""["'](/api/[\w./-]+)["']""")


def appelees(source):
    """The routes this source CALLS, as {(path, method)}.

    Comments are cut here rather than by the caller, so that what the self-test
    judges is what actually runs: a route named in a note about its own removal
    is not a call, and reporting it for ever would get the tool switched off.
    """
    out = set()
    for chemin, reste in APPEL.findall(re.sub(r"//[^\n]*", "", source)):
        # Only the SECOND argument decides. `api(path, null, true)` — the third
        # argument asks for a quiet failure — is still a GET, and reading the
        # whole tail made three of those look like POSTs.
        out.add((chemin, "GET" if _sans_corps(reste) else "POST"))
    return out


def _sans_corps(reste):
    """Is `api()`'s second argument absent, `null` or `undefined`?

    Split at depth zero: an object literal carries commas of its own, and
    cutting on the first one would read `api(p, {a: 1, b: 2})` as having no
    body at all.
    """
    tail = (reste or "").lstrip()
    if not tail.startswith(","):
        return True
    tail, profondeur, premier = tail[1:], 0, ""
    for c in tail:
        if c in "{[(":
            profondeur += 1
        elif c in "}])":
            profondeur -= 1
        elif c == "," and profondeur == 0:
            break
        premier += c
    premier = premier.strip()
    return premier in ("", "null", "undefined")


def connues_par_methode(source):
    """The routes the server answers, split by the handler they live in."""
    out = {}
    for methode, debut in (("GET", source.index("def do_GET")),
                           ("POST", source.index("def do_POST"))):
        fin = min((source.index(m, debut + 10) for m in ("\n    def do_",)
                   if m in source[debut + 10:]), default=len(source))
        out[methode] = set(ROUTE.findall(source[debut:fin]))
    return out


def connues(source):
    return set(ROUTE.findall(source))


BON = """
  const r = await api('/api/parcourir', {chemin: ''});
"""
MAUVAIS = """
  const r = await api('/api/browseServer', {chemin: ''});
"""
SERVEUR_FACTICE_COMPLET = '''
    def do_GET(self):
        pass

    def do_POST(self):
        elif p == "/api/parcourir":
            self._json(browse.listing(d.get("chemin")))
'''


SERVEUR_METHODES = '''
    def do_GET(self):
        if p == "/api/health":
            self._json(_health())

    def do_POST(self):
        if p == "/api/parcourir":
            self._json(browse.listing(d.get("chemin")))
'''


def manquants(js, serveur):
    """The (path, method) pairs the server does not answer."""
    par_methode = connues_par_methode(serveur)
    return sorted((c, m) for c, m in appelees(js)
                  if c not in par_methode.get(m, set()))


def epreuve():
    """Does it see the defect, and stay quiet on the sound version?"""
    if manquants(BON, SERVEUR_FACTICE_COMPLET):
        print("   SELF-TEST FAILED: a route that exists is reported")
        return False
    if not manquants(MAUVAIS, SERVEUR_FACTICE_COMPLET):
        print("   SELF-TEST FAILED: a route that does not exist gets through")
        return False
    # A route named in a comment is not a call: the detector must read calls.
    if manquants("// api('/api/inventee') was removed in 0.3",
                 SERVEUR_FACTICE_COMPLET):
        print("   SELF-TEST FAILED: a route quoted in a comment is reported")
        return False
    # THE shape this half exists for: the route is there, on the other verb.
    # `api()` sends a GET when it has no body, and a POST-only route then
    # answers "route inconnue" — which the interface shows as "your server is
    # out of date".
    # Three arguments, no body: the third asks for a quiet failure and must
    # not be mistaken for one.
    if manquants("api('/api/health', null, true);", SERVEUR_METHODES):
        print("   SELF-TEST FAILED: `api(p, null, true)` is read as a POST")
        return False
    if manquants("api('/api/parcourir', {a: 1, b: 2});", SERVEUR_METHODES):
        print("   SELF-TEST FAILED: an object literal's own commas break the read")
        return False
    if not manquants("api('/api/parcourir');", SERVEUR_METHODES):
        print("   SELF-TEST FAILED: a POST-only route called without a body"
              " gets through")
        return False
    if manquants("api('/api/parcourir', {});", SERVEUR_METHODES):
        print("   SELF-TEST FAILED: the same route called properly is reported")
        return False
    if manquants("api('/api/health');", SERVEUR_METHODES):
        print("   SELF-TEST FAILED: a GET route called with a GET is reported")
        return False
    return True


def main():
    if not epreuve():
        return 2
    js = APP.read_text(encoding="utf-8")
    absentes = manquants(js, SERVEUR.read_text(encoding="utf-8"))
    for chemin, methode in absentes:
        print("   %s en %s : app.js l'appelle, le serveur ne repond pas"
              % (chemin, methode))
    print("   %d appel(s) de route, %d sans reponse."
          % (len(appelees(js)), len(absentes)))
    return 1 if absentes else 0


if __name__ == "__main__":
    sys.exit(main())
