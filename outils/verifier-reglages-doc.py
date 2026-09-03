#!/usr/bin/env python3
"""Does every setting in the code have its line in the reference?

Documentation that drifts from the code is worse than absent: it sends you
looking for a field that does not exist, or past a field that does.

This check lived as YAML inside the workflow, so nowhere on a development
machine. The predictable result: you find out about it in continuous
integration, after pushing. A check you cannot run before pushing is a check you
merely endure.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp(prefix="reglagesdoc-"))

from romule import config                                        # noqa: E402


def epreuve():
    """Does the detector see an absence, and keep quiet about a presence?"""
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
    return 1 if manquantes else 0


if __name__ == "__main__":
    sys.exit(main())
