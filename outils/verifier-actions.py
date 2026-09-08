#!/usr/bin/env python3
"""An action the interface offers must be one the interface can carry out.

Two shapes, both found the same afternoon, both silent:

  * `chooseConsole()` called `this.reveilConsole()` — a name the rename to
    English had replaced eight commits earlier. The call threw, and everything
    after it never ran. Choosing a console did nothing;
  * the three theme buttons and the three motion ones carried
    `data-val="sombre"` as a highlight marker. `argumentDe()` reads `data-val`
    as JSON, `JSON.parse('sombre')` throws, and the throw happens BEFORE the
    action is called. Six buttons, inert, with no error on screen.

What `test_ui_injection.js` already guards is the `data-act` triangle: the
attribute, the allow-list, the method. Neither of these defects is in that
triangle — one is a call between methods, the other an attribute that the
dispatcher reads before it gets that far.

Read statically, and on purpose: both defects only show when somebody clicks
the right button on the right screen, which is exactly what nobody does twice.
"""
import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
APP = RACINE / "romule" / "static" / "app.js"
HTML = RACINE / "romule" / "static" / "index.html"

# Methods of the `app` object literal: two spaces of indent, then the name.
DEFINIE = re.compile(r"^\s{2}(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.M)
APPELEE = re.compile(r"\b(?:this|app)\.([A-Za-z_$][\w$]*)\s*\(")
VALEUR = re.compile(r"""data-val=["']([^"']*)["']""")

# `this.` inside another object literal — a dialog's `faire`, a list's `remove`
# — is not a call on `app`. A static reader cannot tell the receiver apart, so
# the names that legitimately live elsewhere are named here.
AILLEURS = {"faire", "remove"}


def sans_commentaires(source):
    return re.sub(r"//[^\n]*", "", source)


def fantomes(source):
    """Methods called on `app` and defined nowhere."""
    net = sans_commentaires(source)
    return sorted(set(APPELEE.findall(net)) - set(DEFINIE.findall(net)) - AILLEURS)


def valeurs_illisibles(*sources):
    """`data-val` attributes that `JSON.parse` cannot read.

    The reader no longer throws on them — it falls back to the raw string — but
    an attribute that cannot be read as what it claims to be is still a trap,
    and it was the one that killed the theme.
    """
    out = []
    for source in sources:
        for v in VALEUR.findall(sans_commentaires(source)):
            try:
                json.loads(v)
            except ValueError:
                out.append(v)
    return sorted(set(out))


BON_JS = """
const app = {
  wakeConsole() { return 1; },
  chooseConsole() { return this.wakeConsole(); },
};
"""
MAUVAIS_JS = """
const app = {
  chooseConsole() { return this.reveilConsole(); },
};
"""
COMMENTAIRE_JS = """
const app = {
  // this.reveilConsole() was removed in 0.4.0
  chooseConsole() { return 1; },
};
"""
# `$('x')` returns the FIRST node carrying that id. Two nodes with the same
# one therefore make the lookup silently address the wrong element, and there is
# no error anywhere: the code runs, writes into a node nobody looks at, and the
# visible one keeps whatever placeholder it was built with.
#
# That is how the detail view spent a release showing `chargement des infos…`:
# a second `id="gm-desc"` had been added in the header while the real one sat in
# the body, and `$('gm-desc')` handed back the invisible one.
#
# Only ids that are ACTUALLY looked up are reported. A repeated id in markup
# nobody addresses by id is untidy, not broken, and reporting it would drown the
# reading that matters.
_ID = re.compile(r'''id=\\?["\']([A-Za-z][\w-]*)\\?["\']''')
_LOOKUP = re.compile(r"\$\('([\w-]+)'\)")


def ids_doubles(*sources):
    """Ids emitted more than once and read back by `$()`."""
    vus = {}
    cherches = set()
    for src in sources:
        propre = sans_commentaires(src)
        for nom in _ID.findall(propre):
            vus[nom] = vus.get(nom, 0) + 1
        cherches |= set(_LOOKUP.findall(propre))
    return sorted(n for n, c in vus.items() if c > 1 and n in cherches)


BON_ID = "h = '<p id=\"gm-desc\"></p>'; const d = $('gm-desc');"
MAUVAIS_ID = ("h = '<p id=\"gm-desc\"></p>' + '<p id=\"gm-desc\"></p>';"
              " const d = $('gm-desc');")
# Repeated, but never addressed by id: not this tool's business.
IGNORE_ID = "h = '<p id=\"ligne\"></p><p id=\"ligne\"></p>';"

BON_HTML = '<button data-act="setTheme" data-val="true">x</button>'
MAUVAIS_HTML = '<button data-act="setTheme" data-val="sombre">x</button>'


def epreuve():
    """Each half, on the shape it must catch and the ones it must ignore."""
    if fantomes(BON_JS):
        print("   EPREUVE ECHOUEE : une methode qui existe est signalee")
        return False
    if fantomes(MAUVAIS_JS) != ["reveilConsole"]:
        print("   EPREUVE ECHOUEE : une methode inexistante passe")
        return False
    if fantomes(COMMENTAIRE_JS):
        print("   EPREUVE ECHOUEE : un appel en commentaire est signale")
        return False
    if valeurs_illisibles(BON_HTML):
        print("   EPREUVE ECHOUEE : un data-val valide est signale")
        return False
    if valeurs_illisibles(MAUVAIS_HTML) != ["sombre"]:
        print("   EPREUVE ECHOUEE : un data-val illisible passe")
        return False
    if ids_doubles(BON_ID):
        print("   EPREUVE ECHOUEE : un id unique est signale")
        return False
    if ids_doubles(MAUVAIS_ID) != ["gm-desc"]:
        print("   EPREUVE ECHOUEE : un id en double passe")
        return False
    if ids_doubles(IGNORE_ID):
        print("   EPREUVE ECHOUEE : un id double jamais cherche est signale")
        return False
    return True


def main():
    if not epreuve():
        return 2
    js = APP.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    manque = fantomes(js)
    for m in manque:
        print("   app.%s() est appelee et definie nulle part" % m)
    illisibles = valeurs_illisibles(js, html)
    for v in illisibles:
        print("   data-val=%r n'est pas du JSON : le clic mourra avant l'action" % v)
    doubles = ids_doubles(js, html)
    for nom in doubles:
        print("   id=%r existe deux fois : $() rendra le mauvais noeud" % nom)
    print("   %d methode(s) fantome(s), %d data-val illisible(s), %d id(s) en double."
          % (len(manque), len(illisibles), len(doubles)))
    return 1 if (manque or illisibles or doubles) else 0


if __name__ == "__main__":
    sys.exit(main())
