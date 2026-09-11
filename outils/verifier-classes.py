#!/usr/bin/env python3
"""A CSS class lives in three files, or it lives nowhere.

`app.css` styles it, `index.html` carries it, `app.js` adds and removes it. A
class renamed in two of the three still parses, still loads, and still shows a
page — with one rule that never matches. Nothing errors; the interface simply
looks wrong in one state, usually a state you have to provoke.

That is the same shape as the `data-act` failure, and it deserves the same kind
of net. This one reports:

  * a class STYLED but never used — dead rules, and the likely sign that a
    rename reached the CSS and stopped there;
  * a class USED but never styled — the reverse, and the one that shows.

Both are warnings by default, because a handful are legitimate: classes a
browser or a library owns, and classes built by string concatenation, which no
static reader can see. Those live in `TOLERATED`, each with its reason.

    python3 outils/verifier-classes.py            # the report
    python3 outils/verifier-classes.py --strict   # exit 1 if anything is new
    python3 outils/verifier-classes.py --autotest # checks the tool bites

The `--strict` form takes a frozen baseline: the point is not to reach zero, it
is that a rename must not CHANGE the two lists.
"""

import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CSS = RACINE / "romule" / "static" / "app.css"
JS = RACINE / "romule" / "static" / "app.js"
HTML = RACINE / "romule" / "static" / "index.html"
# The server writes HTML too — the login page and the token page — and it was
# outside this check. The CSS rename translated `.chargeur` into `.spinner` in
# the stylesheet and left `class='chargeur'` in `server.py`: both gate pages
# arrived unstyled, black on white, looking like a broken server rather than a
# door. They are the FIRST thing a protected installation shows.
SERVEUR = RACINE / "romule" / "server.py"
BASELINE = RACINE / "outils" / "classes-connues.json"

# Names that are not ours, or that are assembled at runtime. Each one is here
# with the reason it cannot be seen statically.
TOLERATED = {
    # Built by concatenation: `'taille-' + taille`, `'b-' + etat`.
    "taille-", "b-", "p-",
}


def _strip_css_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    # And the URLs. `url("data:image/svg+xml,…xmlns='http://www.w3.org/…'")`
    # gives `.w3` and `.org` to a reader that only looks for a dot followed by a
    # letter: two invented classes, reported as dead style at every pass. A URL
    # is not a selector.
    return re.sub(r"url\(.*?\)", "url()", text, flags=re.S)


def styled():
    """The classes `app.css` declares."""
    text = _strip_css_comments(CSS.read_text(encoding="utf-8"))
    # Only selectors: a `.` inside a value (`0.5`, `url(a.png)`) never starts a
    # class token that begins with a letter.
    return {m.group(1) for m in re.finditer(r"\.([a-zA-Z][\w-]*)", text)}


def _branches_de_classe(reste):
    """A ternary's literals, inside a `class` attribute.

    `'<i class="tem ' + (x ? 'p-oui' : 'p-non') + '"'`: the rest of this
    function stops at the first quote and sees `tem` only. Yet `p-oui` and
    `p-non` are spelled out in full — a static reader CAN name them, and not
    doing so made them pass for dead style.

    Counting the quotes is not a detail: `reste` begins with the one that
    CLOSES the opening literal. The literals are therefore the pairs after it,
    every other one, and getting the parity wrong returns ` + (x ? ` as a class
    name.
    """
    positions = [i for i, c in enumerate(reste) if c == "'"]
    out = set()
    for i in range(1, len(positions) - 1, 2):
        avant = reste[:positions[i]].rstrip()
        # `i.type === 'AMBIGU' ? ...`: that literal is a comparison operand,
        # not a class. Testing it by what comes before costs one line and avoids
        # inventing five classes that exist nowhere.
        if avant.endswith("=") or avant.endswith("!"):
            continue
        lit = reste[positions[i] + 1:positions[i + 1]].strip()
        if lit and re.fullmatch(r"[\w-][\w\s-]*", lit):
            out.update(lit.split())
    return out


def used():
    """The classes `index.html`, `app.js` and `server.py` mention."""
    out = set()
    # Single quotes here: the server writes its HTML from Python strings.
    for m in re.finditer(r"""class=['"]([^'"\n]*)['"]""",
                         SERVEUR.read_text(encoding="utf-8")):
        out.update(m.group(1).split())
    html = HTML.read_text(encoding="utf-8")
    for m in re.finditer(r'class="([^"]*)"', html):
        out.update(m.group(1).split())
    js = JS.read_text(encoding="utf-8")
    # The interface builds its HTML by concatenation, so a class attribute is
    # rarely a closed literal: `'<i class="tem ' + (x ? 'p-oui' : 'p-non') + '"'`.
    # We take the words that ARE literal and stop at the first interruption —
    # everything after it is an expression, and no static reader can name it.
    for m in re.finditer(r'class="([^"\n]*)', js):
        brut = m.group(1)
        head = re.split(r"['\"`]|\$\{", brut)[0]
        out.update(head.split())
        # A head ending in a dash (`tag t-`) is waiting for a SUFFIX: the
        # branches that follow complete a name, they are not one. Taking them
        # for classes would list `BASE` and `DLC` among the unstyled ones.
        if not head.rstrip().endswith("-"):
            out.update(_branches_de_classe(brut[len(head):]))
    # `el.className = 'toast agir' + …` is the same shape without an attribute,
    # and its ternary branches are just as nameable: `'essai ' + (ok ? 'reussi'
    # : 'rate')` was two live classes reported as dead style.
    for m in re.finditer(r"className\s*=\s*'([^']*)'([^\n]*)", js):
        out.update(m.group(1).split())
        out.update(_branches_de_classe("'" + m.group(2)))
    for m in re.finditer(r"classList\.(?:add|remove|toggle|contains)\(([^)]*)\)", js):
        out.update(re.findall(r"'([\w-]+)'", m.group(1)))
    for m in re.finditer(r"R\.classe\([^,]+,\s*'([\w-]+)'", js):
        out.add(m.group(1))
    for m in re.finditer(r"querySelector(?:All)?\('([^']+)'\)", js):
        out.update(re.findall(r"\.([a-zA-Z][\w-]*)", m.group(1)))
    for m in re.finditer(r"closest\('([^']+)'\)", js):
        out.update(re.findall(r"\.([a-zA-Z][\w-]*)", m.group(1)))
    return out


def _tolerated(name):
    # A name ending in `-` is the literal head of a concatenation (`'j-' + id`),
    # not a class. Reporting it would be reporting our own reading limit.
    return name.endswith("-") or any(name.startswith(p) for p in TOLERATED)


def report():
    s, u = styled(), used()
    dead = sorted(n for n in s - u if not _tolerated(n))
    unstyled = sorted(n for n in u - s if not _tolerated(n))
    return dead, unstyled


AUTOTEST_CSS = (".a{color:red}\n.b{color:blue}\n.d{color:green}\n"
                ".f{color:pink}\n.g{color:teal}\n")
AUTOTEST_HTML = '<div class="a"></div>'
AUTOTEST_JS = ("el.classList.add('c');\n"
               # `f` is named ONLY in a ternary branch, inside a `class`
               # attribute: the blind spot the rule closes.
               "el.innerHTML = '<i class=\"a ' + (x ? 'f' : '') + '\"></i>';\n"
               # `g` is named only in a ternary branch of a `className =`.
               "el.className = 'a ' + (x ? 'g' : '');")
# `d` is styled and written only by the server: it must NOT be called dead.
# `e` is written by the server and styled nowhere: it must be reported. That
# pair is the blind spot the login page fell into.
AUTOTEST_PY = """self._page("x", "<div class='d'><b class='e'>y</b></div>")"""


def autotest():
    """A check that never bites protects against nothing."""
    import tempfile
    ok = True
    global CSS, JS, HTML, SERVEUR
    keep = (CSS, JS, HTML, SERVEUR)
    with tempfile.TemporaryDirectory() as d:
        CSS, JS, HTML = Path(d) / "a.css", Path(d) / "a.js", Path(d) / "a.html"
        SERVEUR = Path(d) / "a.py"
        CSS.write_text(AUTOTEST_CSS, encoding="utf-8")
        JS.write_text(AUTOTEST_JS, encoding="utf-8")
        HTML.write_text(AUTOTEST_HTML, encoding="utf-8")
        SERVEUR.write_text(AUTOTEST_PY, encoding="utf-8")
        dead, unstyled = report()
        cases = [("a styled and used class is quiet", "a" not in dead + unstyled),
                 ("a styled but unused class is reported", dead == ["b"]),
                 ("a class named only in a ternary branch is seen", "f" not in dead),
                 ("…in a className assignment too", "g" not in dead),
                 # `in`, not `==`: the fixtures now carry a second unstyled
                 # class on purpose, and an exact list would make the case
                 # about the fixture rather than about the detector.
                 ("a used but unstyled class is reported", "c" in unstyled),
                 # The blind spot itself: a class the SERVER writes and the
                 # stylesheet no longer has.
                 ("a class only the server writes is seen", "d" not in dead),
                 ("and reported when the stylesheet lost it", "e" in unstyled)]
        for name, cond in cases:
            print(("  OK    " if cond else "  FAIL  ") + name)
            ok = ok and cond
    CSS, JS, HTML, SERVEUR = keep
    return 0 if ok else 1


def main(argv):
    if "--autotest" in argv:
        print("-- self-test of the detector --")
        return autotest()
    dead, unstyled = report()
    if "--ecrire" in argv:
        BASELINE.write_text(json.dumps({"styled_only": dead, "used_only": unstyled},
                                       indent=1) + "\n", encoding="utf-8")
        print("baseline written: %d styled-only, %d used-only"
              % (len(dead), len(unstyled)))
        return 0
    for n in dead:
        print("  STYLED ONLY  %s" % n)
    for n in unstyled:
        print("  USED ONLY    %s" % n)
    print("   %d styled and never used, %d used and never styled."
          % (len(dead), len(unstyled)))
    if "--strict" not in argv:
        return 0
    try:
        old = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("   no baseline: run with --ecrire once.")
        return 1
    new_dead = sorted(set(dead) - set(old.get("styled_only", [])))
    new_unstyled = sorted(set(unstyled) - set(old.get("used_only", [])))
    for n in new_dead:
        print("   NEW styled-only: %s" % n)
    for n in new_unstyled:
        print("   NEW used-only: %s" % n)
    return 1 if (new_dead or new_unstyled) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
