#!/usr/bin/env python3
"""Every `fichier.md#ancre` link in the documentation points at a real heading.

Why this exists
---------------
Two links pointed at `securite.md#the-first-access-token`, an anchor that left
with the token model. MkDocs catches this — its strict build refuses — but it
only runs in CI, and only on pushes that touch `docs/**`. The links broke in a
commit that changed CODE, and stayed broken until a screenshot happened to
touch the documentation weeks later.

So the check runs locally, in the suite, with no MkDocs to install: the slug is
recomputed the way Python-Markdown's `toc` extension computes it, which is the
one MkDocs uses.

    python3 outils/verifier-liens-doc.py
    python3 outils/verifier-liens-doc.py --autotest
"""
import re
import sys
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOCS = RACINE / "docs"

TITRE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
LIEN = re.compile(r"\]\(([^)\s]+\.md)#([^)\s]+)\)")
# `{ #ancre }` — an explicit anchor wins over the computed one.
EXPLICITE = re.compile(r"\{\s*#([\w-]+)\s*\}\s*$")


def slug(titre):
    """The identifier Python-Markdown's `toc` gives a heading.

    Its default `slugify` strips the accents, lowercases, drops everything that
    is neither a word character nor a space, then joins on a dash. Reproducing
    it here is what lets this run without MkDocs.
    """
    titre = re.sub(r"<[^>]+>", "", titre)          # inline markup
    titre = re.sub(r"[*`_]", "", titre)
    titre = unicodedata.normalize("NFKD", titre)
    titre = "".join(c for c in titre if not unicodedata.combining(c))
    titre = re.sub(r"[^\w\s-]", "", titre, flags=re.U).strip().lower()
    return re.sub(r"[-\s]+", "-", titre)


def ancres(texte):
    """Every anchor a page offers."""
    out = set()
    for _, titre in TITRE.findall(texte):
        marque = EXPLICITE.search(titre)
        if marque:
            out.add(marque.group(1))
            titre = EXPLICITE.sub("", titre)
        out.add(slug(titre))
    return out


def liens_casses(pages):
    """`pages` maps a file name to its text. Returns the broken links."""
    casses = []
    par_page = {nom: ancres(txt) for nom, txt in pages.items()}
    for nom, texte in sorted(pages.items()):
        for cible, ancre in LIEN.findall(texte):
            # A link from `configuration.fr.md` to `securite.md` means the
            # FRENCH page: the translated pair is `securite.fr.md`, and MkDocs
            # resolves it that way through its i18n plugin.
            voulu = cible
            if nom.endswith(".fr.md") and not cible.endswith(".fr.md"):
                jumeau = cible[:-3] + ".fr.md"
                if jumeau in par_page:
                    voulu = jumeau
            if voulu not in par_page:
                casses.append((nom, "%s : page absente" % cible))
            elif ancre not in par_page[voulu]:
                casses.append((nom, "%s#%s : ancre absente" % (cible, ancre)))
    return casses


BON = {"a.md": "## Le premier accès\n",
       "b.md": "voir [ça](a.md#le-premier-acces)\n"}
MAUVAIS = {"a.md": "## Le premier accès\n",
           "b.md": "voir [ça](a.md#le-jeton-de-premier-acces)\n"}


def autotest():
    """A check that never bites protects against nothing."""
    ok = True
    if liens_casses(BON):
        print("   EPREUVE ECHOUEE : un lien valide est signale")
        ok = False
    if not liens_casses(MAUVAIS):
        print("   EPREUVE ECHOUEE : une ancre absente passe")
        ok = False
    if slug("A token, if you want one") != "a-token-if-you-want-one":
        print("   EPREUVE ECHOUEE : slug anglais faux")
        ok = False
    if slug("Un jeton, si tu en veux un") != "un-jeton-si-tu-en-veux-un":
        print("   EPREUVE ECHOUEE : slug accentue faux")
        ok = False
    if not liens_casses({"a.md": "# t\n", "b.md": "[x](absente.md#y)\n"}):
        print("   EPREUVE ECHOUEE : une page absente passe")
        ok = False
    return ok


def main(argv):
    if "--autotest" in argv:
        print("-- autotest du verificateur de liens --")
        return 0 if autotest() else 2
    if not autotest():
        return 2
    pages = {p.name: p.read_text(encoding="utf-8") for p in DOCS.glob("*.md")}
    casses = liens_casses(pages)
    for page, quoi in casses:
        print("   %s -> %s" % (page, quoi))
    print("   %d page(s), %d lien(s) casse(s)." % (len(pages), len(casses)))
    return 1 if casses else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
