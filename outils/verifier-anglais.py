#!/usr/bin/env python3
"""Is there any French left in the comments and the docstrings?

Romule's code is moving to English: the repository is public, under the AGPL,
with an English README, documentation and interface. French comments protected an
internal consistency at the price of the only thing that matters for an open
project — that one can get in.

Without this check, the translation degrades again at the first comment written
by reflex, and nobody notices until there are a hundred.

What it looks at, and what it does NOT
--------------------------------------
Only PROSE: `#` comments, docstrings, `//` and `/* */` comments.

French stays legitimate elsewhere, and confusing it with an oversight would
report perfectly correct lines:

  * `romule/locales/fr.json` IS the translation catalogue — its keys are French
    sentences, that is the mechanism, not a style;
  * the configuration keys (`emulateur`, `systemes_perso`) are written on every
    installation's disk and are not renamed;
  * `app.js`'s interface strings are the keys of that same catalogue.

A line may carry `anglais:ok` when it deliberately QUOTES French — to explain a
catalogue key, for instance. The marker asks for a reason beside it, like
`i18n:ok` and `fuite:ok` elsewhere in the project.

It covers the whole BLOCK, not the line alone. A quotation often spills over two
lines — "Kirby et le Labyrinthe des Miroirs" does not fit on the one that would
carry the marker — and demanding one marker per line would push towards twisting
the sentence to please the tool, which is the opposite of the point.
"""
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# French function words with NO ambiguity against English. The false friends are
# deliberately absent: "car", "on", "a", "an", "son", "plus", "la", "no", "pain",
# "comment" are English words, and including them would report irreproachable
# English prose.
MARQUEURS = {
    "le", "les", "du", "des", "une", "qui", "que", "quoi", "pour", "pas",
    "est", "sont", "etait", "dans", "avec", "mais", "donc", "quand", "cette",
    "ce", "ces", "cet", "elle", "ils", "elles", "nous", "vous", "leur", "aux",
    "sans", "sous", "etre", "peut", "doit", "faut", "fait", "avoir", "deja",
    "ainsi", "alors", "aussi", "encore", "toujours", "jamais", "rien", "tout",
    "toute", "toutes", "tous", "chaque", "meme", "plutot", "parce", "afin",
    "lorsque", "puisque", "cela", "celui", "ceux", "celle", "ici", "la-bas",
    "trop", "moins", "beaucoup", "peu", "assez", "bien", "mal", "vraiment",
    "seulement", "surtout", "notamment", "ensuite", "puis", "enfin", "voici",
    "voila", "sinon", "sauf", "selon", "vers", "chez", "entre", "pendant",
    "depuis", "avant", "apres", "au-dela", "par-dessus", "n'est", "c'est",
    "qu'il", "qu'elle", "qu'on", "d'un", "d'une", "l'on", "s'il", "j'ai",
    "n'a", "n'y", "y a",
}

# Elisions: `l'interface`, `d'acces`, `qu'un`. Two letters at most before the
# apostrophe, which excludes the English possessive (`user's`, `Romule's`).
ELISION = re.compile(r"\b(?:[ldjmtscn]|qu|jusqu|lorsqu|puisqu)'[a-zA-Zàâéèêëîïôûùç]", re.I)

MOT = re.compile(r"[a-zàâäéèêëîïôöûùüç'-]+", re.I)

# What sits between backticks is quoted CODE, not prose. Without this cut,
# `_est_admin()` and `_qui()` made irreproachable English sentences get reported —
# "est" and "qui" are French markers, but here they are pieces of function names.
# The alternative — scattering `anglais:ok` markers on every line that quotes an
# identifier — would have made the detector unbearable, and therefore disabled.
_CODE = re.compile(r"`[^`]*`")

MUETTES = {".git", "node_modules", "__pycache__", "site", "locales"}


def francais(texte):
    """The French markers found in this text, or an empty set."""
    prose = _CODE.sub(" ", texte)
    mots = {m.lower() for m in MOT.findall(prose)}
    trouves = mots & MARQUEURS
    if ELISION.search(prose):
        trouves.add("elision")
    return trouves


def blocs(lignes):
    """Groups neighbouring (number, text) pairs, and sets aside the marked ones.

    The `anglais:ok` marker covers the whole block: a French quotation inside
    English prose spreads over several lines, and the marker only sits on one of
    them.
    """
    groupes, courant = [], []
    for num, texte in lignes:
        if courant and num - courant[-1][0] > 1:
            groupes.append(courant); courant = []
        courant.append((num, texte))
    if courant:
        groupes.append(courant)
    gardes = []
    for g in groupes:
        if any("anglais:ok" in t for _, t in g):
            continue
        gardes.extend(g)
    return gardes


def prose_python(source):
    """The (line number, text) pairs of the comments and docstrings."""
    lignes = source.splitlines()
    sorties, dans_doc, delim = [], False, ""
    for i, ligne in enumerate(lignes, 1):
        nu = ligne.strip()
        if dans_doc:
            sorties.append((i, ligne))
            if delim in nu:
                dans_doc = False
            continue
        # A `#` inside a string is not a comment. So we cut on the first `#`
        # that is not preceded by an odd number of quotes.
        if "#" in ligne:
            avant = ligne.split("#", 1)[0]
            if avant.count('"') % 2 == 0 and avant.count("'") % 2 == 0:
                sorties.append((i, ligne.split("#", 1)[1]))
        for d in ('"""', "'''"):
            if nu.startswith(d) or nu.startswith("r" + d) or nu.startswith("f" + d):
                reste = nu.split(d, 1)[1]
                sorties.append((i, reste))
                if d not in reste:
                    dans_doc, delim = True, d
                break
    return sorties


def prose_js(source):
    sorties, dans_bloc = [], False
    for i, ligne in enumerate(source.splitlines(), 1):
        nu = ligne.strip()
        if dans_bloc:
            sorties.append((i, ligne))
            if "*/" in nu:
                dans_bloc = False
            continue
        if nu.startswith("//"):
            sorties.append((i, nu[2:]))
        elif "//" in ligne and "://" not in ligne:
            sorties.append((i, ligne.split("//", 1)[1]))
        if "/*" in nu:
            sorties.append((i, nu.split("/*", 1)[1]))
            if "*/" not in nu.split("/*", 1)[1]:
                dans_bloc = True
    return sorties


BON_PY = '''# The trash IS the undo: asking "are you sure?" charges the price of a
# mistake that costs nothing.
def move_to_trash(path):
    """Move a file aside. Nothing is erased; everything stays restorable."""
    return path
'''

MAUVAIS_PY = '''# La corbeille EST l'annulation : demander « etes-vous sur ? » fait payer
# le prix d'une erreur qui ne coute rien.
def move_to_trash(path):
    return path
'''

# English that TALKS ABOUT French: the marker must let it through.
CITATION_PY = '''# `fr.json` holds keys like "Aucune destination" -- anglais:ok, quoted key
NAME = "x"
'''


# The same quotation, spread over two lines: the marker sits on the first and
# must cover the second.
CITATION_LONGUE_PY = '''# The English title is the pivot -- anglais:ok, quoting a
# French title: "Kirby et le Labyrinthe des Miroirs".
NAME = "x"
'''


# A French identifier quoted in an English sentence: `_est_admin` carries
# "est", `_qui` carries "qui". Those are names, not prose.
IDENTIFIANT_PY = '''# `_est_admin()` answers the role question, and `_qui()` does not.
NAME = "x"
'''



# A rename that walked into a sentence people read. The identifier around it is
# rightly English; the sentence is not an identifier.
ABIME_PY = '''def probe(cfg):
    return (False, "Aucune key renseignee.")
'''

# The same sentence, intact. And an English sentence in an English string, which
# is not this check's business at all.
SAIN_PY = '''def probe(cfg):
    if not cfg:
        return (False, "Aucune cle renseignee.")
    return (True, "the key was accepted by the provider")
'''

# Markup: `class="lead"` and `data-act="refreshAll"` are English on purpose and
# have nothing to do with the sentence they surround.
BALISE_PY = '''HTML = "<p class=\'lead\'>Aucun doublon repere pour le moment.</p>"
'''


def epreuve():
    """Does the detector see French, and keep quiet about English?

    All three cases matter equally. A detector that reports correct English
    would be switched off within a week, and nothing would be left.
    """
    if any(francais(t) for _, t in prose_python(BON_PY)):
        print("   SELF-TEST FAILED: correct English is reported")
        return False
    if not any(francais(t) for _, t in prose_python(MAUVAIS_PY)):
        print("   SELF-TEST FAILED: obvious French gets through")
        return False
    if any(francais(t) for _, t in blocs(prose_python(CITATION_PY))):
        print("   SELF-TEST FAILED: the `anglais:ok` marker does not protect")
        return False
    # The marker must cover the block, not only its own line: a French
    # quotation almost always spills over onto the next line.
    if any(francais(t) for _, t in blocs(prose_python(CITATION_LONGUE_PY))):
        print("   SELF-TEST FAILED: the marker does not cover the whole block")
        return False
    if not any(francais(t) for _, t in blocs(prose_python(MAUVAIS_PY))):
        print("   SELF-TEST FAILED: grouping into blocks lets French through")
        return False
    # A French function name inside an English sentence is not French: it is an
    # identifier, and it will be translated by the identifier phase, not by the
    # prose one.
    if any(francais(t) for _, t in blocs(prose_python(IDENTIFIANT_PY))):
        print("   SELF-TEST FAILED: an identifier between backticks is reported")
        return False
    # The mirror half, on the shape it must catch AND the two it must ignore.
    if not any(anglicismes(t) for _, t in chaines_python(ABIME_PY)):
        print("   SELF-TEST FAILED: an English word wedged into a French"
              " sentence gets through")
        return False
    if any(anglicismes(t) for _, t in chaines_python(SAIN_PY)):
        print("   SELF-TEST FAILED: an intact sentence is reported")
        return False
    if any(anglicismes(t) for _, t in chaines_python(BALISE_PY)):
        print("   SELF-TEST FAILED: a class name inside markup is reported")
        return False
    return True



# ---------------------------------------------------------------------------
# The mirror defect: an English word inside a sentence people READ
# ---------------------------------------------------------------------------
#
# Renaming `cle` to `key` across covers.py turned a displayed sentence into
# "Aucune key renseignee." — a French sentence with an English word wedged into
# it, shown as-is in the interface. Nothing saw it: ruff reads syntax, this
# tool's other half reads comments, and the sentence was not a comment.
#
# In app.js the catalogue catches this shape by itself: a damaged sentence is no
# longer a key, and `verifier-traduction.py` says so. Python strings go through
# no catalogue, so this is the only thing between them and the screen.
#
# The vocabulary is the ENGLISH SIDE of the renames actually carried out. It is
# frozen by hand rather than derived: a list computed from the diff would grow a
# new word every time a variable is renamed, and would report the sentences that
# legitimately quote one.
ANGLICISMES = {
    "key", "keys", "name", "file", "files", "path", "size", "list", "folder",
    "settings", "cover", "duplicates", "views", "backup", "accounts", "trash",
    "transfers", "browse", "updates", "matching", "notify", "game", "games",
    "push", "send", "device", "report", "scheduler", "consoles",
}

# What sits inside a tag is markup: `class="lead"`, `data-act="refreshAll"`.
# Those names are English on purpose and have nothing to do with the sentence.
_BALISE = re.compile(r"<[^>]*>")

# A string literal, and not the apostrophe of `l'interface`: a French
# apostrophe is always preceded by a letter, an opening quote never is.
_CHAINE = re.compile(r"""(?<![A-Za-zÀ-ÿ0-9_])(["'])((?:\\.|(?!\1).)*)\1""")


# A displayed sentence is short, and `MARQUEURS` was drawn for paragraphs of
# comment: "Aucune cle renseignee." carries none of its words. This wider set is
# only ever consulted together with `ANGLICISMES`, so a false positive needs to
# be wrong TWICE — which is what lets it include short words safely.
MARQUEURS_COURTS = MARQUEURS | {
    "aucun", "aucune", "un", "une", "la", "le", "du", "de", "des", "sur",
    "vers", "ton", "ta", "tes", "cette", "ces", "trop", "plus", "moins",
    "impossible", "introuvable", "inconnu", "inconnue", "invalide",
    "manquant", "manquante", "renseignee", "active", "activee",
}


# Three shapes where an English word inside a French sentence is right:
#
#   `master key`  the Switch's own vocabulary — there is no French for it, and
#                 the interface has always said it;
#   `title.keys`  a file name, and a name is not a word;
#   `GAMES/DLC`   the folders the console itself creates, in capitals.
_TERMES = re.compile(r"\bmaster\s+keys?\b|\b[\w-]+\.[a-z]+\b|\b[A-Z]{3,}\b")


def anglicismes(texte):
    """The English words wedged into this French sentence, or an empty set."""
    prose = _TERMES.sub(" ", _CODE.sub(" ", _BALISE.sub(" ", texte)))
    mots = {m.lower() for m in MOT.findall(prose)}
    if not (mots & MARQUEURS_COURTS or ELISION.search(prose)):
        return set()          # an English sentence is not the subject here
    return mots & ANGLICISMES


def chaines_python(source):
    """The (line number, content) pairs of the string literals.

    Comments are left out on purpose: they are the other half of this tool, and
    an English word in an English comment is the point.
    """
    out = []
    for i, ligne in enumerate(source.splitlines(), 1):
        nu = ligne.strip()
        # A docstring is prose, and prose is the other half of this tool. A line
        # that OPENS with a quote is a docstring or the continuation of one;
        # a sentence shown to somebody is always the argument of something.
        if nu.startswith("#") or nu[:1] in ('"', "'") or nu[:2] in ('r"', "f'"):
            continue
        for _, contenu in _CHAINE.findall(ligne):
            # Fewer than three words is a key, a format or a fragment, not a
            # sentence anybody reads.
            if len(contenu.split()) >= 3:
                out.append((i, contenu))
    return out


def prose_html(source):
    """The (line number, text) pairs of `<!-- -->` comments.

    `index.html` carries a hundred lines of them, and they were invisible to
    this check for as long as it only read .py, .js and .css — which is exactly
    how a blind spot survives: not by being argued for, but by never being
    looked at.
    """
    out, inside = [], False
    for i, line in enumerate(source.splitlines(), 1):
        rest = line
        if not inside:
            if "<!--" not in rest:
                continue
            rest = rest.split("<!--", 1)[1]
            inside = True
        if "-->" in rest:
            out.append((i, rest.split("-->", 1)[0]))
            inside = False
        else:
            out.append((i, rest))
    return out


def fichiers():
    for motif, extracteur in (("*.py", prose_python), ("*.js", prose_js),
                              ("*.css", prose_js), ("*.html", prose_html)):
        for p in sorted(RACINE.rglob(motif)):
            if any(part in MUETTES for part in p.parts):
                continue
            if p.name == "verifier-anglais.py":       # it quotes what it looks for
                continue
            yield p, extracteur


def main(argv):
    if not epreuve():
        return 2
    limite = 40 if "--tout" not in argv else 10 ** 6
    total, montres = 0, 0
    for p, extracteur in fichiers():
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for num, texte in blocs(extracteur(src)):
            mots = francais(texte)
            if not mots:
                continue
            total += 1
            if montres < limite:
                montres += 1
                rel = p.relative_to(RACINE)
                print("   %s:%d  %s" % (rel, num, " ".join(texte.split())[:88]))
    # The mirror half. Shipped Python only: the tests speak to whoever runs
    # them, and app.js is already covered by the catalogue.
    abimees = 0
    for p in sorted((RACINE / "romule").glob("*.py")):
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for num, contenu in chaines_python(src):
            intrus = anglicismes(contenu)
            if intrus:
                abimees += 1
                print("   %s:%d  %s\n        -> %s"
                      % (p.relative_to(RACINE), num, contenu[:80],
                         ", ".join(sorted(intrus))))
    if abimees:
        print("   %d displayed sentence(s) carry an English word: a rename"
              " walked into a string." % abimees)
    if total > montres:
        print("   ... and %d more (`--tout` for the full list)"
              % (total - montres))
    print("   %d line(s) of prose still in French." % total)
    return 1 if (total or abimees) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
