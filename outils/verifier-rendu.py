#!/usr/bin/env python3
"""Does the built site display markdown on screen?

`mkdocs build --strict` catches dead links, not this: a block placed inside an
HTML tag without the `md_in_html` extension is rendered AS IT STANDS. The home
page displayed its card grid in the clear that way — `**[Installation]
(installation.md)** — Docker...` — for several versions. It is not a MkDocs
warning, it is text that displays badly, and nothing was watching for it.

The check reads the BUILT site rather than the sources: that is what a reader
sees, and it is the only way to catch a missing extension, a wrong admonition
indent, or a badly closed tab — three failures, none of them visible in the
markdown.

Code areas are set aside: `**` and `[x](y)` are legitimate text there.
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SITE = RACINE / "site"

# What these tags contain is not prose: we do not judge it.
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
    """A page's visible text, without what the mute tags carry."""

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
    """The raw-markdown patterns found in a page's prose."""
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
    """Is the detector capable of failing?

    A check nobody has ever seen fall proves nothing. So this one is run against
    a healthy page AND against the exact failure it must catch, on every run,
    before being believed.
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
