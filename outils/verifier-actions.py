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
    print("   %d methode(s) fantome(s), %d data-val illisible(s)."
          % (len(manque), len(illisibles)))
    return 1 if (manque or illisibles) else 0


if __name__ == "__main__":
    sys.exit(main())
