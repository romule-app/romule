#!/usr/bin/env python3
"""Refuse to let a French sentence enter the code without entering the catalogue.

The interface is translated by a gettext-style mechanism where the KEY is the
French sentence: `romule/locales/fr.json` is the catalogue of translatable
strings, `en.json` carries their translations.

A parity check between those two files already existed — and it is perfect, so
green whatever happens. What was missing is the other half: nobody compared the
CODE to the catalogue. About 360 French sentences therefore had no entry and
were displayed as they stood inside an English interface, five of them on the
home screen of a fresh install.

This script does that check. It reads `app.js`'s literals and `index.html`'s
texts, keeps those that look like French, and reports the ones no key covers.

There is no JavaScript parser in the standard library, and a regular expression
over strings fails at the first apostrophe inside a comment. So the file is read
character by character, with a state machine that knows where it is: code,
comment, string, template, or regular expression.

Exemptions — always with their reason written beside them, never by a list of
files, which goes stale in silence:

    JS    'AGPL-3.0'   // i18n:ok - a licence name, not a sentence
    HTML  <span data-i18n-skip>…</span>

`data-i18n-skip` is already read at runtime by `traduisible()`: an exemption
therefore cannot lie, it holds for the tool AND for the display.

    python3 outils/verifier-traduction.py            # reports the missing ones
    python3 outils/verifier-traduction.py --liste    # with their line
    python3 outils/verifier-traduction.py --json
    python3 outils/verifier-traduction.py --autotest # checks the script bites

Exits 0 if nothing is missing, 1 otherwise.
"""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
JS = RACINE / "romule" / "static" / "app.js"
HTML = RACINE / "romule" / "static" / "index.html"
CATALOGUE = RACINE / "romule" / "locales" / "fr.json"

MARQUE = "i18n:ok"

# Function words: two of them are enough to give away accent-free French.
# "Convertir les", "Rien dans", "Aucun jeu trouve" -- anglais:ok, quoted French
# samples -- carry no accent and slipped under the radar of the browser test,
# which looked only for those.
OUTILS = set((
    "le la les un une des du de d au aux et ou en dans sur sous pour par avec "
    "sans vers est sont ete etre a ce cette ces son sa ses ton ta tes votre "
    "aucun aucune rien tout toute tous chaque plus moins deja encore jamais "
    "il elle on nous vous ils elles que qui quoi dont si mais donc car ne pas"
).split())
ACCENTS = re.compile(r"[àâäçéèêëîïôöûùüÿœÀÂÄÇÉÈÊËÎÏÔÖÛÙÜŸŒ]")
# What is not prose: selectors, paths, addresses, identifiers.
NON_PROSE = re.compile(
    r"^\s*[.#/]|://|^[a-z0-9_-]+$|^%[sd]$|^[-+*/=<>|&,;:()\[\]{}\s]+$"
    # `attribute="value"`: markup, not a sentence.
    r'|[a-z-]+="')
# A SINGLE lowercase WORD is rejected by NON_PROSE, because it is almost always
# an identifier or a setting's value. Almost: "aucune" and "inconnue" were
# displayed in a game's detail view, in French, inside an English interface — and
# neither this check nor the browser test could see them, one throwing them away
# as identifiers, the other demanding an accent or two function words.
#
# This list reopens the door for the words whose use as an identifier is rare and
# whose use as text is certain. It will produce a few false positives — a French
# word IS sometimes a setting's value — and that is the sense of the trade-off: a
# false positive shows and is lifted with `i18n:ok` and its reason, an omission
# does not show at all.
SEULS = set((
    "aucun aucune aucuns aucunes inconnu inconnue inconnus inconnues "
    "jamais toujours plusieurs quelques autre autres chacun chacune "
    "terminee terminees echouee echouees introuvable introuvables"
).split())
BALISE = re.compile(r"<[^>]*>")
_CODE_HTML = re.compile(r"<code\b[^>]*>.*?</code>", re.S | re.I)
MOT = re.compile(r"[a-zA-ZÀ-ÿ']{2,}")


# ----------------------------------------------------------- reading the JS

def litteraux_js(source):
    """(line, text) for every string literal in the file.

    The state machine distinguishes seven states. The only really delicate one is
    the slash: it opens either a regular expression or a division depending on
    what precedes it. We decide on the last significant character — an
    identifier, a closing parenthesis or a digit announce a division, everything
    else a regular expression. Getting it wrong swallows a string, which is a
    false NEGATIVE, so silent: hence the self-test.
    """
    sorties = []
    i, n, ligne = 0, len(source), 1
    precedent = ""
    while i < n:
        c = source[i]
        if c == "\n":
            ligne += 1
            i += 1
            continue
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and source[i + 1] == "*":
            i += 2
            while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
                if source[i] == "\n":
                    ligne += 1
                i += 1
            i += 2
            continue
        if c == "/" and not (precedent.isalnum() or precedent in ")]_$"):
            i += 1                                   # expression reguliere
            while i < n and source[i] != "/":
                if source[i] == "\\":
                    i += 1
                elif source[i] == "[":                # a class: / closes nothing there
                    while i < n and source[i] != "]":
                        i += 2 if source[i] == "\\" else 1
                elif source[i] == "\n":
                    break
                i += 1
            i += 1
            continue
        if c in "'\"`":
            debut, quote, depart_litteral = ligne, c, i
            i += 1
            morceaux = []
            while i < n and source[i] != quote:
                if source[i] == "\\":
                    morceaux.append(source[i:i + 2])
                    i += 2
                    continue
                if source[i] == "\n":
                    ligne += 1
                    if quote != "`":
                        break                        # chaine non terminee
                morceaux.append(source[i])
                i += 1
            i += 1
            brut = "".join(morceaux)
            for seq, rempl in (("\\n", "\n"), ("\\t", "\t"), ("\\'", "'"),
                               ('\\"', '"'), ("\\\\", "\\")):
                brut = brut.replace(seq, rempl)
            sorties.append([debut, brut, depart_litteral, i])
            precedent = quote
            continue
        if not c.isspace():
            precedent = c
        i += 1
    return _recoller(sorties, source)


def _recoller(litteraux, source):
    """Merges the literals `+` joins: at runtime they make only one.

    A sentence too long for one line is written as two pieces glued by `+`. The
    DOM only sees a single text node, so the KEY is the whole sentence. Testing
    them separately reported perfectly translated sentences as missing — and
    would have led to writing keys that serve no purpose.
    """
    out = []
    for ligne, texte, debut, fin in litteraux:
        if out:
            entre = source[out[-1][3]:debut]
            # An end-of-line comment can slip in there — that is even where an
            # exemption mark is put. It does not break the concatenation, so it
            # must not break the merging.
            entre = re.sub(r"//[^\n]*", "", entre)
            entre = re.sub(r"/\*.*?\*/", "", entre, flags=re.S)
            # Only `+` and whitespace: this is a continuation.
            if entre.strip() == "+":
                out[-1][1] += texte
                out[-1][3] = fin
                continue
        out.append([ligne, texte, debut, fin])
    return [(l, t) for l, t, _, _ in out]


# --------------------------------------------------------- reading the HTML

class LecteurHTML(HTMLParser):
    """Displayed texts and translatable attributes, skipping the exemptions."""

    ATTRIBUTS = ("title", "placeholder", "aria-label")
    MUETS = {"script", "style", "code", "pre", "textarea"}
    # Elements without a closing tag: without this list, `handle_endtag` is
    # never called for them and the stack never comes back down.
    ORPHELINS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.trouves = []
        self.pile = []
        self.saute = 0

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        exempte = "data-i18n-skip" in d
        muet = tag in self.MUETS or exempte
        # The attributes are collected BEFORE entering the mute zone, and only
        # if the element is not itself exempt. The previous version said
        # `or exempte`, which collected them despite the exemption: an exemption
        # that exempts from nothing.
        if not self.saute and not muet:
            for a in self.ATTRIBUTS:
                if d.get(a):
                    self.trouves.append((self.getpos()[0], d[a]))
        if muet:
            self.saute += 1
        if tag not in self.ORPHELINS:
            self.pile.append((tag, muet))
        elif muet:
            self.saute -= 1          # il se referme aussitot

    def handle_endtag(self, tag):
        while self.pile:
            t, muet = self.pile.pop()
            if muet:
                self.saute = max(0, self.saute - 1)
            if t == tag:
                break

    def handle_data(self, data):
        if not self.saute and data.strip():
            self.trouves.append((self.getpos()[0], data))


# ------------------------------------------------------------- the catalogue

def _plat(s):
    """The same normalisation as `_plat()` in app.js."""
    return re.sub(r"\s+", " ", str(s or "")).strip()


def couverture(catalogue):
    """(cles a plat, gabarits compiles) — miroir de `_compilerGabarits()`."""
    plates, gabarits = set(), []
    for fr in catalogue:
        if fr == "_meta":
            continue
        plat = _plat(fr)
        plates.add(plat)
        if "%s" in plat:
            motif = "(.+?)".join(re.escape(x) for x in plat.split("%s"))
            gabarits.append(re.compile("^" + motif + "$", re.S))
    return plates, gabarits


def couvert(texte, plates, gabarits):
    plat = _plat(texte)
    if plat in plates:
        return True
    return any(g.match(plat) for g in gabarits)


# ------------------------------------------------------------- the heuristic

def morceaux_de_texte(litteral):
    """A literal's TEXT fragments, with the tags removed.

    This code builds its interface by concatenating HTML: most sentences live in
    strings that start with `<div class=...>`. Rejecting every literal starting
    with `<`, as the first version did, therefore threw away most of the seam —
    "Aucun événement" fell off the radar because its string starts with
    `<div class="jempty">`.
    """
    if "<" not in litteral and ">" not in litteral:
        return [litteral]
    # What a `<code>` holds is a command to type, not a sentence to translate —
    # the same rule the HTML reader already applies. Without it, growing the
    # catalogue eventually turns every command into a false positive: adding
    # `romule access close    exiger une connexion` taught the vocabulary the
    # words `access` and `close`, and the command itself was then reported as
    # untranslated French.
    # Its CONTENT goes, its tags stay: at runtime a `<code>` splits the text
    # into separate nodes, so the surrounding fragments are the keys, and
    # removing the element whole would glue them into a sentence that never
    # exists on the page.
    litteral = _CODE_HTML.sub("<code></code>", litteral)
    bouts = []
    for m in BALISE.split(litteral):
        # A literal can start or end in the MIDDLE of a tag — when an
        # interpolated value cuts it in two: `...onclick="f(' + x + ')">
        # Détails</button>`. A piece of tag then remains around the text.
        # Interface text never contains an angle bracket: we keep what follows
        # the last `>` and what precedes the first `<`.
        if ">" in m:
            m = m.rsplit(">", 1)[1]
        if "<" in m:
            m = m.split("<", 1)[0]
        m = m.strip()
        if m:
            bouts.append(m)
    return bouts


def vocabulaire(catalogue):
    """The words already seen in known French sentences.

    Rather than a hand-written dictionary — which would be wrong and would go
    stale — we use the catalogue itself: by construction, those are French
    interface sentences. "Dossier vide." has neither accent nor function word,
    but both its words appear in existing keys.
    """
    mots = set()
    for cle in catalogue:
        if cle != "_meta":
            mots.update(m.lower() for m in MOT.findall(cle))
    return mots


# A line that COMPARES shows nothing: `dataset.mvt === 'aucun'` tests a
# setting's value, `i.type === 'ARCHIVE' ? 'INCONNU' : …` picks a CSS class
# suffix. Context is what tells a value from a label, and it is the only way to
# open the door to single words without drowning the report.
COMPARAISON = re.compile(r"===|!==|\bcase\s")


def candidat(texte, vocab=frozenset(), ligne_brute=""):
    """Does this text look like a French interface sentence?"""
    t = _plat(texte)
    if not (4 <= len(t) <= 220):
        return False
    # Before NON_PROSE: it is what threw those words away.
    if t.strip().lower() in SEULS:
        return not COMPARAISON.search(ligne_brute)
    if NON_PROSE.search(t):
        return False
    if ACCENTS.search(t):
        return True
    mots = [m.lower() for m in MOT.findall(t)]
    if sum(1 for m in mots if m in OUTILS) >= 2:
        return True
    # A bundle of clues: at least two words, most of them already seen in a
    # known French sentence. That is what catches "Dossier vide.", which neither
    # the accent nor the function words give away.
    if len(mots) >= 2 and vocab:
        connus = sum(1 for m in mots if m in vocab)
        return connus >= 2 and connus / len(mots) >= 0.6
    return False


def manquantes(source_js=None, source_html=None, catalogue=None):
    """Liste de (fichier, ligne, texte) non couverts."""
    cat = catalogue if catalogue is not None else json.loads(
        CATALOGUE.read_text(encoding="utf-8"))
    plates, gabarits = couverture(cat)
    vocab = vocabulaire(cat)
    out = []

    js = source_js if source_js is not None else JS.read_text(encoding="utf-8")
    lignes_js = js.splitlines()
    for ligne, texte in litteraux_js(js):
        brut = lignes_js[ligne - 1] if ligne - 1 < len(lignes_js) else ""
        if MARQUE in brut:
            continue
        for bout in morceaux_de_texte(texte):
            if candidat(bout, vocab, brut) and not couvert(bout, plates, gabarits):
                out.append(("app.js", ligne, _plat(bout)))

    html = source_html if source_html is not None else HTML.read_text(encoding="utf-8")
    lecteur = LecteurHTML()
    lecteur.feed(html)
    lignes_html = html.splitlines()
    for ligne, texte in lecteur.trouves:
        brut = lignes_html[ligne - 1] if ligne - 1 < len(lignes_html) else ""
        if MARQUE in brut:
            continue
        if candidat(texte, vocab, brut) and not couvert(texte, plates, gabarits):
            out.append(("index.html", ligne, _plat(texte)))
    return out


# ------------------------------------------------------- pluriels paresseux

# "1 fichier(s)" is not a plural, it is a confession — and it was on nearly
# every screen. The `{singular|plural}` notation replaces it, and the language
# chooses: in French 0 and 1 are singular, in English only 1 is.
#
# This check forbids the lazy form from coming back. It looks only at STRINGS:
# `String(s)` and `compte(s)` are function calls, and a first version that swept
# the whole file had transformed them.
PARESSEUX = re.compile(r"[0-9A-Za-zÀ-ÿ'’/-]+\((s|x|es)\)")


def pluriels_paresseux(source_js=None, source_html=None):
    out = []
    js = source_js if source_js is not None else JS.read_text(encoding="utf-8")
    lignes = js.splitlines()
    for ligne, texte in litteraux_js(js):
        brut = lignes[ligne - 1] if ligne - 1 < len(lignes) else ""
        if MARQUE in brut:
            continue
        m = PARESSEUX.search(texte)
        if m:
            out.append(("app.js", ligne, m.group(0)))
    html = source_html if source_html is not None else HTML.read_text(encoding="utf-8")
    lecteur = LecteurHTML()
    lecteur.feed(html)
    for ligne, texte in lecteur.trouves:
        m = PARESSEUX.search(texte)
        if m:
            out.append(("index.html", ligne, m.group(0)))
    return out


# ----------------------------------------------------------------- autotest

def autotest():
    """A detector nobody has seen detect proves nothing."""
    ok = ko = 0

    def t(nom, cond, detail=""):
        nonlocal ok, ko
        if cond:
            ok += 1
            print("  ok   %s" % nom)
        else:
            ko += 1
            print("  ECHEC %s   %s" % (nom, detail))

    cat = {"Déjà traduit": "Already translated",
           "Bonjour %s, tout va bien": "Hello %s, all is well",
           "Un mot traduit ici": "A word translated here"}

    cas = [
        ("une phrase absente est signalee",
         "toast('Une phrase absente du catalogue.');", True),
        ("une phrase presente est ignoree",
         "toast('Déjà traduit');", False),
        ("un gabarit %s est reconnu",
         "toast('Bonjour %s, tout va bien');", False),
        ("le francais SANS accent est vu",
         "toast('Convertir les fichiers qui restent dans le dossier');", True),
        ("une exemption motivee est respectee",
         "toast('Une phrase absente du catalogue.');  // i18n:ok - motif", False),
        ("un commentaire n'est pas du code",
         "// toast('Une phrase absente du catalogue.');", False),
        ("une apostrophe dans une expression reguliere ne decale pas",
         "const r = /l'un/; toast('Déjà traduit');", False),
        ("une division n'est pas prise pour une expression reguliere",
         "const x = (a) / 2; toast('Déjà traduit');", False),
        ("un identifiant n'est pas une phrase",
         "const k = 'switch-lite';", False),
        ("un selecteur CSS n'est pas une phrase",
         "el.querySelector('.gcard .gname');", False),
        # This code builds its interface by concatenating HTML: rejecting every
        # literal starting with `<` threw away most of the seam.
        ("une phrase noyee dans un fragment HTML est vue",
         "el.innerHTML = '<div class=\"x\">Une phrase absente du catalogue.</div>';",
         True),
        ("un fragment HTML sans texte est ignore",
         "el.innerHTML = '<div class=\"jempty\"></div>';", False),
        # A `<code>` holds a command to type. The HTML reader has always known
        # that; the JS side did not, and every command became a false positive
        # as soon as the catalogue had learnt its words elsewhere.
        ("une commande dans un <code>, en JS, est ignoree",
         "el.innerHTML = '<code>romule access close</code>';", False),
        ("mais la phrase autour ne l'est pas",
         "el.innerHTML = 'Une phrase absente du catalogue.<code>romule x</code>';",
         True),
        # The vocabulary comes from the catalogue itself: a sentence with no
        # accent and no function word is recognised if its words have already
        # served elsewhere.
        ("une phrase sans accent ni mot-outil est reconnue par son vocabulaire",
         "toast('Bonjour traduit');", True),
        # A sentence too long for one line is written as two pieces glued by
        # `+`. At runtime they make a single text node: the key is the whole
        # sentence, and testing them separately reported perfectly translated
        # sentences as missing.
        ("deux morceaux colles par + ne font qu'une phrase",
         "toast('Déjà ' +\n      'traduit');", False),
        ("deux chaines SANS + restent distinctes",
         "f('Déjà traduit', 'Une phrase absente du catalogue.');", True),
    ]
    for nom, code, attendu in cas:
        vu = bool(manquantes(source_js=code, source_html="", catalogue=cat))
        t(nom, vu == attendu, "detecte=%s" % vu)

    # The trial sentences carry two function words: that is the threshold, and a
    # test case that does not reach it would measure the test case, not the tool.
    ABSENTE = "Une phrase absente du catalogue."
    html_cas = [
        ("un texte HTML absent est signale", "<p>%s</p>" % ABSENTE, True),
        ("un texte exempte est ignore",
         "<p data-i18n-skip>%s</p>" % ABSENTE, False),
        ("le contenu d'un <code> est ignore", "<code>%s</code>" % ABSENTE, False),
        ("un attribut title est examine",
         '<button title="%s">x</button>' % ABSENTE, True),
        ("un attribut d'un element exempte est ignore",
         '<button data-i18n-skip title="%s">x</button>' % ABSENTE, False),
        ("un <script> n'est pas du texte affiche",
         "<script>var s = '%s';</script>" % ABSENTE, False),
    ]
    for nom, html, attendu in html_cas:
        vu = bool(manquantes(source_js="", source_html=html, catalogue=cat))
        t(nom, vu == attendu, "detecte=%s" % vu)

    # Emphasis that CUTS a sentence. The failure it stands for: an English page
    # reading `That is pas the port`, because `<b>pas</b>` sits mid-sentence and
    # the fragment is too short to ever be a key. What must NOT be reported is
    # emphasis around a whole sentence — the shape used all over this interface.
    coupe_cas = [
        ("une emphase au milieu d'une phrase -> detectee",
         "<p>Ce n'est <b>pas</b> le port.</p>", {"pas"}),
        ("une emphase sur la phrase entiere -> ignoree",
         "<p><b>Ce n'est pas le port.</b></p>", set()),
        ("une emphase seule sur sa ligne -> ignoree",
         "<div>\n  <b>Glisse tes jeux ici</b>\n</div>", set()),
        ("une emphase en TETE de phrase -> ignoree",
         "<p><b>Attention</b> au port indique.</p>", set()),
        ("une emphase en FIN de phrase -> ignoree",
         "<p>Recopie le port <b>d'appairage</b></p>", set()),
        ("une emphase dans un autre parent ne compte pas",
         "<p><span>Avant</span><b>Seul</b></p>", set()),
        ("une donnee emphasee n'est pas une phrase",
         "<p>du type <b>192.168.1.42</b> exactement.</p>", set()),
        ("un <i> decoratif n'est pas une emphase",
         "<p>Avant <i>\u00b7</i> apres</p>", set()),
        ("une emphase imbriquee est lue en entier",
         "<p>Va dans <b>Para<em>metres</em></b> puis la.</p>", {"Parametres"}),
    ]
    for nom, html, attendu in coupe_cas:
        t(nom, emphases_html(html) == attendu, emphases_html(html))

    js_coupe_cas = [
        ("une emphase au milieu, en JS -> detectee",
         "h = 'appuie sur <b>Partager</b> puis la;';", {"Partager"}),
        ("une phrase entiere emphasee, en JS -> ignoree",
         "h = '<b>Glisse tes jeux ici</b>' + reste;", set()),
        ("une valeur construite par le code -> ignoree",
         "h = 'sous <b>' + esc(dir) + '</b> :';", set()),
    ]
    for nom, js, attendu in js_coupe_cas:
        t(nom, emphases_js(js) == attendu, emphases_js(js))

    # The SINGLE word: the class that let "aucune" show in French inside an
    # English interface. NON_PROSE threw it away as an identifier, and both
    # heuristics demanded an accent or two function words.
    seuls_cas = [
        ("un mot francais seul, affiche -> detecte",
         "el.textContent = 'aucune';", True),
        ("le meme dans une comparaison -> ignore",
         "if (d.mvt === 'aucun') muter();", False),
        ("le meme dans un ternaire de valeur -> ignore",
         "cls = i.type === 'ARCHIVE' ? 'INCONNU' : i.type;", False),
        ("un identifiant qui n'est pas un mot francais -> ignore",
         "el.className = 'gcard';", False),
        ("un mot francais seul en gabarit HTML -> detecte",
         "h = '<b>' + 'introuvable' + '</b>';", True),
    ]
    for nom, js, attendu in seuls_cas:
        vu = bool(manquantes(source_js=js, source_html="", catalogue=cat))
        t(nom, vu == attendu, "detecte=%s" % vu)

    paresse_cas = [
        ("un pluriel paresseux -> detecte", "x = 'Trouve %d fichier(s).';", True),
        ("la forme accordee -> ignore",
         "x = 'Trouve %d {fichier|fichiers}.';", False),
        ("un appel de fonction -> ignore", "const e = s => String(s).trim();", False),
        ("une phrase sans nombre -> ignore", "x = 'Rien a signaler.';", False),
    ]
    for nom, js, attendu in paresse_cas:
        t(nom, bool(pluriels_paresseux(source_js=js, source_html="")) == attendu)

    print("  %d controles OK, %d echec(s)" % (ok, ko))
    return 1 if ko else 0


# --------------------------------------------------------------------- main

# A literal handed to `t()` is an EXPLICIT request to translate. No heuristic
# is needed there and none should apply: the length rules that keep this tool
# from reporting identifiers also let "Nom" and "Renommer" through, and both
# were shown untranslated on the console buttons.
_APPEL_T = re.compile(r"""\bt\(\s*(['"])((?:\\.|(?!\1).)*)\1\s*\)""")


_LIBELLE = re.compile(r"""libelle:\s*(['"])((?:\\.|(?!\1).)+)\1""")


def libelles(source):
    """The captions of dialog buttons.

    They are written as bare literals — the DOM observer translates them — so
    nothing looked at them, and « Activer » and « Lancer » sat untranslated in
    an English interface. A caption is shown to somebody; it has to be a key.
    """
    out = set()
    for _, brut in _LIBELLE.findall(re.sub(r"//[^\n]*", "", source)):
        texte = brut.replace("\\'", "'").replace('\\"', '"')
        # A caption assembled from a template is resolved elsewhere.
        if texte and "%" not in texte:
            out.add(texte)
    return out


def appels_t(source):
    """The literals passed to `t()`, unescaped."""
    out = set()
    for _, brut in _APPEL_T.findall(re.sub(r"//[^\n]*", "", source)):
        texte = brut.replace("\\'", "'").replace('\\"', '"')
        if texte:
            out.add(texte)
    return out


# An emphasis in the MIDDLE of a sentence: `Ce n'est <b>pas</b> le port`. Every
# extractor here splits on tags, so one sentence becomes three fragments. The
# short one falls under every length threshold used to avoid reporting
# identifiers, so it is never a key and stays in French inside an English page
# — which is what happened to `pas`, to `Partager`, and to the wireless
# debugging paragraph.
#
# Being at the catalogue does NOT excuse it: a half-sentence key cannot be
# reordered by a translator, and the two halves drift apart the first time one
# of them is reworded.
#
# Emphasis around a WHOLE sentence is fine — that is a single text node, hence a
# single key. Telling the two apart is the whole difficulty, and it is why this
# walks the document instead of matching a pattern: `<b>` alone on its line is
# preceded by a newline and some indentation, which any "a character, then the
# tag" rule reads as text. The question is not what characters sit next to the
# tag, it is whether the tag has non-empty text on BOTH sides WITHIN ITS PARENT.
# `<i>` is not in this set: here it is a decorative separator and an icon
# holder — `<i>·</i>`, `<i></i>` — never emphasis carrying words.
_EMPHASE_TAGS = {"b", "em", "strong"}
# Data, not prose: an address, a version, a path, a symbol. Shown as they are.
_DONNEE = re.compile(r"^[\d.:/_\-]+$|^[A-Z_]{3,}$|^[^\w\s]+$")


class _Coupures(HTMLParser):
    """Emphasis tags with text on both sides inside the same parent."""

    def __init__(self):
        HTMLParser.__init__(self)
        # One entry per open element: the text seen before the current child,
        # the emphases opened at this level and still awaiting text after them.
        self.pile = [{"avant": "", "attente": []}]
        self.profond = 0
        self.courant = None
        self.trouve = set()

    def _texte(self, data):
        niveau = self.pile[-1]
        if data.strip():
            # Everything still waiting at this level now has text after it.
            for texte in niveau["attente"]:
                self.trouve.add(texte)
            niveau["attente"] = []
            niveau["avant"] += data

    def handle_starttag(self, tag, attrs):
        if self.courant is not None:
            self.profond += 1
            return
        if tag in _EMPHASE_TAGS and self.pile[-1]["avant"].strip():
            self.courant, self.profond = [], 0
            return
        self.pile.append({"avant": "", "attente": []})

    def handle_endtag(self, tag):
        if self.courant is not None:
            if self.profond:
                self.profond -= 1
                return
            texte = " ".join("".join(self.courant).split())
            self.courant = None
            if texte and not _DONNEE.match(texte):
                self.pile[-1]["attente"].append(texte)
            return
        if len(self.pile) > 1:
            self.pile.pop()

    def handle_data(self, data):
        if self.courant is not None:
            self.courant.append(data)
        else:
            self._texte(data)


def emphases_html(source):
    lecteur = _Coupures()
    lecteur.feed(source)
    return lecteur.trouve


# In `app.js` the markup lives inside string literals, so there is no document
# to walk. A quote, a `+` or a brace is a boundary rather than text — that is
# what tells `'<b>Whole sentence</b>' +` from `'... sur <b>Partager</b> puis'`.
_BORD = r"[^\s<>'\"+`;{}(),\[\]]"
_EMPHASE_JS = re.compile(_BORD + r"[ \t]*<(b|em|strong)>([^<>]{1,40})</\1>"
                         r"[ \t]*" + _BORD)


# A fragment the INTERFACE builds: `<b>' + esc(x) + '</b>`. What lands there is
# a value, not a sentence, and no catalogue can hold it.
_CODE = ("' +", "+ '", "${", "esc(", "$1", '" +', '+ "')


def emphases_js(source):
    out = set()
    for _, brut in _EMPHASE_JS.findall(source):
        texte = " ".join(brut.split()).replace("\\'", "'")
        if not texte or _DONNEE.match(texte):
            continue
        if any(marque in texte for marque in _CODE):
            continue
        out.add(texte)
    return out


def entetes():
    """Does each catalogue announce ITSELF?

    `_meta` is what `/api/langues` reads to fill the language selector — in the
    settings and, since the wizard, on its first step. A catalogue whose `code`
    names another language makes the selector offer the same one twice, and the
    other becomes unreachable: the interface stays in a language nobody can
    leave.

    It happened by copy: `fr.json` was rebuilt from `en.json` and took its
    `_meta` along. Nothing failed — the file parsed, every sentence was there,
    and the only symptom was a dropdown offering "English, English".
    """
    soucis, vus = [], {}
    for f in sorted((RACINE / "romule" / "locales").glob("*.json")):
        try:
            meta = json.loads(f.read_text(encoding="utf-8")).get("_meta") or {}
        except (ValueError, OSError) as exc:
            soucis.append("%s : illisible (%s)" % (f.name, exc))
            continue
        code, nom = meta.get("code"), meta.get("langue") or meta.get("nom")
        if code != f.stem:
            soucis.append("%s : _meta.code vaut %r au lieu de %r"
                          % (f.name, code, f.stem))
        if not nom:
            soucis.append("%s : _meta ne donne aucun nom lisible" % f.name)
        elif nom in vus:
            soucis.append("%s : porte le meme nom que %s (%r)"
                          % (f.name, vus[nom], nom))
        else:
            vus[nom] = f.name
    return soucis


def pourcents_doubles(catalogues):
    """`%%` is printf's escape. JavaScript has none.

    `tpl()` replaces `%s` and `%d` and leaves everything else alone, so a
    doubled per-cent written out of Python habit reaches the screen as it
    stands: « Fingerprints known for 0 %% of the library ». Found on a
    published screenshot, which is a late place to find it.
    """
    soucis = []
    for nom, catalogue in catalogues.items():
        for cle, valeur in catalogue.items():
            if cle == "_meta":
                continue
            for quoi, texte in (("cle", cle), ("valeur", valeur)):
                if isinstance(texte, str) and "%%" in texte:
                    soucis.append("%s : %%%% n'est pas un echappement en "
                                  "JavaScript (%s %r)" % (nom, quoi, texte))
    return soucis


def main(argv):
    if "--autotest" in argv:
        print("-- autotest du detecteur --")
        return autotest()
    trous = manquantes()
    paresse = pluriels_paresseux()
    # Checked FIRST, and outside the "are all the sentences there" question: a
    # catalogue can be complete to the last entry and still announce itself as
    # another language, which is how "English, English" reached the selector.
    soucis = entetes()
    catalogue = json.loads((RACINE / "romule" / "locales" / "fr.json")
                           .read_text(encoding="utf-8"))
    tous = {f.name: json.loads(f.read_text(encoding="utf-8"))
            for f in sorted((RACINE / "romule" / "locales").glob("*.json"))}
    soucis += pourcents_doubles(tous)
    js = (RACINE / "romule" / "static" / "app.js").read_text(encoding="utf-8")
    for texte in sorted(appels_t(js)):
        if texte not in catalogue:
            soucis.append("t(%r) n'est pas au catalogue" % texte)
    for texte in sorted(libelles(js)):
        if texte not in catalogue:
            soucis.append("le libelle de bouton %r n'est pas au catalogue" % texte)
    html = (RACINE / "romule" / "static" / "index.html").read_text(encoding="utf-8")
    for texte in sorted(emphases_html(html) | emphases_js(js)):
        soucis.append("l'emphase %r coupe une phrase en deux : porte-la sur la"
                      " phrase entiere, ou retire-la" % texte)
    for souci in soucis:
        print("  ENTETE   %s" % souci)
    if paresse:
        for fichier, ligne, forme in paresse:
            print("  PLURIEL  %s:%d  %s  ->  {%s|%s%s}"
                  % (fichier, ligne, forme, forme[:-3], forme[:-3], forme[-2]))
        print("\n%d pluriel(s) paresseux : ecrire {singulier|pluriel}, la langue "
              "choisit." % len(paresse))
    if "--json" in argv:
        print(json.dumps([{"fichier": f, "ligne": n, "texte": t}
                          for f, n, t in trous], ensure_ascii=False, indent=2))
        return 1 if trous else 0
    if not trous and not paresse and not soucis:
        print("Toutes les phrases du code sont au catalogue.")
        return 0
    if not trous:
        return 1
    if "--liste" in argv:
        for f, n, t in trous:
            print("  %s:%d  %s" % (f, n, t[:110]))
    par_fichier = {}
    for f, _, _ in trous:
        par_fichier[f] = par_fichier.get(f, 0) + 1
    print("%d phrase(s) absente(s) de fr.json : %s"
          % (len(trous), ", ".join("%s %d" % (f, n)
                                   for f, n in sorted(par_fichier.items()))))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
