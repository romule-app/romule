#!/usr/bin/env python3
"""Le site construit n'affiche-t-il pas du markdown a l'ecran ?

`mkdocs build --strict` attrape les liens morts, pas ceci : un bloc place dans
une balise HTML sans l'extension `md_in_html` est rendu TEL QUEL. La page
d'accueil affichait ainsi sa grille de cartes en clair — `**[Installation]
(installation.md)** — Docker...` — pendant plusieurs versions. Ce n'est pas un
avertissement de MkDocs, c'est du texte qui s'affiche mal, et rien ne le
regardait.

Le controle lit le site CONSTRUIT plutot que les sources : c'est ce que voit un
lecteur, et c'est la seule facon d'attraper une extension manquante, une
indentation d'admonition fausse, ou un onglet mal ferme — trois pannes dont
aucune n'est visible dans le markdown.

Les zones de code sont ecartees : `**` et `[x](y)` y sont du texte legitime.
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SITE = RACINE / "site"

# Ce que ces balises contiennent n'est pas de la prose : on ne le juge pas.
MUETTES = {"pre", "code", "script", "style", "textarea"}

MOTIFS = [
    (re.compile(r"\*\*\S"), "du gras en clair (`**`)"),
    (re.compile(r"\[[^\]\n]{1,60}\]\([^)\n]{1,80}\)"), "un lien en clair"),
    (re.compile(r"^\s*!!!\s+\w", re.M), "une admonition non rendue (`!!!`)"),
    (re.compile(r'^\s*===\s+"', re.M), "un onglet non rendu (`===`)"),
    (re.compile(r"\|\s*-{3,}"), "un tableau non rendu"),
    (re.compile(r"^\s*#{1,6}\s+\w", re.M), "un titre en clair (`#`)"),
]


class Prose(HTMLParser):
    """Le texte visible d'une page, sans ce que portent les balises muettes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.morceaux = []
        self._muet = 0

    def handle_starttag(self, tag, attrs):
        if tag in MUETTES:
            self._muet += 1

    def handle_endtag(self, tag):
        if tag in MUETTES and self._muet:
            self._muet -= 1

    def handle_data(self, data):
        if not self._muet:
            self.morceaux.append(data)

    def texte(self):
        return "".join(self.morceaux)


def fautes(html):
    """Les motifs de markdown brut trouves dans la prose d'une page."""
    p = Prose()
    p.feed(html)
    texte = p.texte()
    vues = []
    for motif, quoi in MOTIFS:
        m = motif.search(texte)
        if m:
            extrait = texte[max(0, m.start() - 30):m.start() + 70]
            vues.append((quoi, " ".join(extrait.split())))
    return vues


BON = """<article><p>Voir <a href="x/"><strong>Installation</strong></a> —
  Docker.</p><pre><code>curl -H "X" | python3 -c '**pas du gras**'</code></pre>
  <p>Un <code>[lien](faux.md)</code> cite dans du code.</p>
  <table><thead><tr><th>Cle</th></tr></thead></table></article>"""

MAUVAIS = """<article><div class="grid cards">
  - **[Installation](installation.md)** — Docker, or Python
  </div></article>"""


def epreuve():
    """Le detecteur est-il capable d'echouer ?

    Un controle qu'on n'a jamais vu tomber ne prouve rien. Celui-ci est donc
    passe sur une page saine ET sur la panne exacte qu'il doit attraper, a
    chaque execution, avant d'etre cru.
    """
    if fautes(BON):
        print("   EPREUVE ECHOUEE : une page saine est signalee — %s"
              % fautes(BON))
        return False
    if not fautes(MAUVAIS):
        print("   EPREUVE ECHOUEE : la grille de cartes non rendue passe")
        return False
    return True


def main():
    if not epreuve():
        return 2
    if not SITE.exists():
        print("   site/ absent — construis-le d'abord : mkdocs build")
        return 2
    pages = sorted(SITE.rglob("*.html"))
    total = 0
    for p in pages:
        for quoi, extrait in fautes(p.read_text(encoding="utf-8", errors="replace")):
            total += 1
            rel = p.relative_to(SITE)
            print("::error file=docs/%s::%s s'affiche en clair : %s"
                  % (rel, quoi, extrait))
            print("   %s : %s" % (rel, quoi))
            print("      %s" % extrait)
    print("   %d page(s) verifiee(s), %d probleme(s) de rendu." % (len(pages), total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
