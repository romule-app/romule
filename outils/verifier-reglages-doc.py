#!/usr/bin/env python3
"""Does every setting have its line in the reference — and every link its heading?

Documentation that drifts from the code is worse than absent: it sends you
looking for a field that does not exist, or past a field that does.

This check lived as YAML inside the workflow, so nowhere on a development
machine. The predictable result: you find out about it in continuous
integration, after pushing. A check you cannot run before pushing is a check you
merely endure.
"""
import os
import re
import unicodedata
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp(prefix="reglagesdoc-"))

from romule import config                                        # noqa: E402


def ancres(markdown):
    """The anchors mkdocs makes out of this file's headings.

    Its rule, followed here: lowercase, spaces become hyphens, punctuation and
    accents go. Approximate enough to catch a renamed heading, which is the
    only thing this is for.
    """
    out = set()
    for ligne in markdown.splitlines():
        if not ligne.startswith("#"):
            continue
        titre = ligne.lstrip("#").strip()
        titre = unicodedata.normalize("NFD", titre)
        titre = "".join(c for c in titre if unicodedata.category(c) != "Mn")
        out.add(re.sub(r"[^a-z0-9]+", "-", titre.lower()).strip("-"))
    return out


def liens_interface():
    """(page, French anchor, English anchor) for every `docLien()` in app.js.

    The interface sends people to a HEADING of the published documentation.
    Rename the heading and the link still opens the page — at the top, on
    whatever happens to be there. Nothing fails, and nobody hears about it.
    """
    js = (RACINE / "romule" / "static" / "app.js").read_text(encoding="utf-8")
    return re.findall(
        r"docLien\(\s*'([\w-]+)'\s*,\s*'([\w-]+)'\s*,\s*\n?\s*'([\w-]+)'", js)


def epreuve():
    """Does the detector see an absence, and keep quiet about a presence?"""
    if "jaquettes-et-fiches" not in ancres("### Jaquettes et fiches\n"):
        print("   EPREUVE ECHOUEE : une ancre francaise n'est pas reconnue")
        return False
    if "covers-and-details" not in ancres("### Covers and details\n"):
        print("   EPREUVE ECHOUEE : une ancre anglaise n'est pas reconnue")
        return False
    if "titre-absent" in ancres("### Un autre titre\n"):
        print("   EPREUVE ECHOUEE : une ancre inexistante est vue")
        return False
    doc = "| `un_reglage` | ... |"
    cites = set(re.findall(r"`([a-z][a-z_]+)`", doc))
    if "un_reglage" not in cites:
        print("   EPREUVE ECHOUEE : une cle citee n'est pas vue")
        return False
    if "jamais_cite" in cites:
        print("   EPREUVE ECHOUEE : une cle absente est vue quand meme")
        return False
    return True


def main():
    if not epreuve():
        return 2
    doc = (RACINE / "docs" / "configuration.md").read_text(encoding="utf-8")
    cites = set(re.findall(r"`([a-z][a-z_]+)`", doc))
    manquantes = sorted(set(config.DEFAULTS) - cites)
    for k in manquantes:
        print("::error title=Reglage non documente::%s existe dans le code "
              "mais pas dans docs/configuration.md" % k)
        print("   %s" % k)
    print("   %d reglages, %d documentes."
          % (len(config.DEFAULTS), len(config.DEFAULTS) - len(manquantes)))

    # The links the interface offers must land on a heading that exists, in
    # BOTH languages: the French pages are published under /fr/ and have their
    # own headings.
    casses = 0
    for page, fr, en in liens_interface():
        for suffixe, ancre in ((".fr", fr), ("", en)):
            chemin = RACINE / "docs" / ("%s%s.md" % (page, suffixe))
            if not chemin.exists():
                casses += 1
                print("   %s : page absente pour l'interface" % chemin.name)
                continue
            if ancre not in ancres(chemin.read_text(encoding="utf-8")):
                casses += 1
                print("   %s#%s : l'interface pointe une ancre qui n'existe pas"
                      % (chemin.name, ancre))
    print("   %d lien(s) de doc dans l'interface, %d casse(s)."
          % (len(liens_interface()) * 2, casses))
    return 1 if (manquantes or casses) else 0


if __name__ == "__main__":
    sys.exit(main())
