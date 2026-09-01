#!/usr/bin/env python3
"""Refuse qu'une phrase francaise entre dans le code sans entrer au catalogue.

L'interface est traduite par un mecanisme de type gettext ou la CLE est la
phrase francaise : `romule/locales/fr.json` est le catalogue des chaines
traduisibles, `en.json` porte leurs traductions.

Il existait deja un controle de parite entre ces deux fichiers — et il est
parfait, donc vert quoi qu'il arrive. Ce qui manquait est l'autre moitie :
personne ne comparait le CODE au catalogue. Environ 360 phrases francaises
n'avaient donc aucune entree et s'affichaient telles quelles dans une interface
anglaise, dont cinq sur l'ecran d'accueil d'une installation neuve.

Ce script fait ce controle. Il lit les litteraux de `app.js` et les textes
d'`index.html`, retient ceux qui ressemblent a du francais, et signale ceux
qu'aucune cle ne couvre.

Il n'y a pas d'analyseur JavaScript dans la bibliotheque standard, et une
expression reguliere sur des chaines echoue des la premiere apostrophe dans un
commentaire. On lit donc le fichier caractere par caractere, avec un automate
qui sait ou il se trouve : code, commentaire, chaine, gabarit, ou expression
reguliere.

Exemptions — toujours avec leur motif ecrit a cote, jamais par liste de
fichiers, qui se perime en silence :

    JS    'AGPL-3.0'   // i18n:ok - nom de licence, pas une phrase
    HTML  <span data-i18n-skip>…</span>

`data-i18n-skip` est deja lu a l'execution par `traduisible()` : une exemption
ne peut donc pas mentir, elle vaut pour l'outil ET pour l'affichage.

    python3 outils/verifier-traduction.py            # signale les manquantes
    python3 outils/verifier-traduction.py --liste    # avec leur ligne
    python3 outils/verifier-traduction.py --json
    python3 outils/verifier-traduction.py --autotest # verifie que le script mord

Sortie 0 si rien ne manque, 1 sinon.
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

# Mots-outils : deux d'entre eux suffisent a trahir du francais sans accent.
# « Convertir les », « Rien dans », « Aucun jeu trouve » n'ont pas d'accent et
# passaient sous le radar du test navigateur, qui ne cherchait que ceux-la.
OUTILS = set((
    "le la les un une des du de d au aux et ou en dans sur sous pour par avec "
    "sans vers est sont ete etre a ce cette ces son sa ses ton ta tes votre "
    "aucun aucune rien tout toute tous chaque plus moins deja encore jamais "
    "il elle on nous vous ils elles que qui quoi dont si mais donc car ne pas"
).split())
ACCENTS = re.compile(r"[àâäçéèêëîïôöûùüÿœÀÂÄÇÉÈÊËÎÏÔÖÛÙÜŸŒ]")
# Ce qui n'est pas de la prose : selecteurs, chemins, adresses, identifiants.
NON_PROSE = re.compile(
    r"^\s*[<.#/]|://|^[a-z0-9_-]+$|^%[sd]$|^[-+*/=<>|&,;:()\[\]{}\s]+$")


# ----------------------------------------------------------- lecture du JS

def litteraux_js(source):
    """(ligne, texte) de chaque litteral de chaine du fichier.

    L'automate distingue sept etats. Le seul reellement delicat est la barre
    oblique : elle ouvre une expression reguliere ou une division selon ce qui
    precede. On tranche sur le dernier caractere significatif — un identifiant,
    une parenthese fermante ou un chiffre annoncent une division, tout le reste
    une expression reguliere. Se tromper avale une chaine, ce qui est un faux
    NEGATIF, donc silencieux : d'ou l'autotest.
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
                elif source[i] == "[":                # classe : / n'y ferme rien
                    while i < n and source[i] != "]":
                        i += 2 if source[i] == "\\" else 1
                elif source[i] == "\n":
                    break
                i += 1
            i += 1
            continue
        if c in "'\"`":
            debut, quote = ligne, c
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
            sorties.append((debut, brut))
            precedent = quote
            continue
        if not c.isspace():
            precedent = c
        i += 1
    return sorties


# --------------------------------------------------------- lecture du HTML

class LecteurHTML(HTMLParser):
    """Textes affiches et attributs traduisibles, en sautant les exemptions."""

    ATTRIBUTS = ("title", "placeholder", "aria-label")
    MUETS = {"script", "style", "code", "pre", "textarea"}
    # Elements sans fermeture : sans cette liste, `handle_endtag` n'est jamais
    # appele pour eux et la pile ne redescend plus.
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
        # Les attributs sont releves AVANT d'entrer dans la zone muette, et
        # seulement si l'element n'est pas lui-meme exempte. La version
        # precedente disait `or exempte`, ce qui les relevait malgre
        # l'exemption : une exemption qui ne dispense de rien.
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


# ------------------------------------------------------------- le catalogue

def _plat(s):
    """Meme normalisation que `_plat()` dans app.js."""
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


# ------------------------------------------------------------- l'heuristique

def candidat(texte):
    """Ce texte ressemble-t-il a une phrase d'interface en francais ?"""
    t = _plat(texte)
    if not (4 <= len(t) <= 220):
        return False
    if NON_PROSE.search(t):
        return False
    if ACCENTS.search(t):
        return True
    mots = [m for m in re.findall(r"[a-zA-ZÀ-ÿ']+", t.lower())]
    return sum(1 for m in mots if m in OUTILS) >= 2


def manquantes(source_js=None, source_html=None, catalogue=None):
    """Liste de (fichier, ligne, texte) non couverts."""
    cat = catalogue if catalogue is not None else json.loads(
        CATALOGUE.read_text(encoding="utf-8"))
    plates, gabarits = couverture(cat)
    out = []

    js = source_js if source_js is not None else JS.read_text(encoding="utf-8")
    lignes_js = js.splitlines()
    for ligne, texte in litteraux_js(js):
        brut = lignes_js[ligne - 1] if ligne - 1 < len(lignes_js) else ""
        if MARQUE in brut:
            continue
        if candidat(texte) and not couvert(texte, plates, gabarits):
            out.append(("app.js", ligne, _plat(texte)))

    html = source_html if source_html is not None else HTML.read_text(encoding="utf-8")
    lecteur = LecteurHTML()
    lecteur.feed(html)
    lignes_html = html.splitlines()
    for ligne, texte in lecteur.trouves:
        brut = lignes_html[ligne - 1] if ligne - 1 < len(lignes_html) else ""
        if MARQUE in brut:
            continue
        if candidat(texte) and not couvert(texte, plates, gabarits):
            out.append(("index.html", ligne, _plat(texte)))
    return out


# ----------------------------------------------------------------- autotest

def autotest():
    """Un detecteur qu'on n'a pas vu detecter ne prouve rien."""
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
           "Bonjour %s, tout va bien": "Hello %s, all is well"}

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
    ]
    for nom, code, attendu in cas:
        vu = bool(manquantes(source_js=code, source_html="", catalogue=cat))
        t(nom, vu == attendu, "detecte=%s" % vu)

    # Les phrases d'epreuve portent deux mots-outils : c'est le seuil, et un
    # cas de test qui ne l'atteint pas mesurerait le cas de test, pas l'outil.
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

    print("  %d controles OK, %d echec(s)" % (ok, ko))
    return 1 if ko else 0


# --------------------------------------------------------------------- main

def main(argv):
    if "--autotest" in argv:
        print("-- autotest du detecteur --")
        return autotest()
    trous = manquantes()
    if "--json" in argv:
        print(json.dumps([{"fichier": f, "ligne": n, "texte": t}
                          for f, n, t in trous], ensure_ascii=False, indent=2))
        return 1 if trous else 0
    if not trous:
        print("Toutes les phrases du code sont au catalogue.")
        return 0
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
