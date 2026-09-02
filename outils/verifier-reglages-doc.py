#!/usr/bin/env python3
"""Chaque reglage du code a-t-il sa ligne dans la reference ?

Une documentation qui derive du code est pire qu'absente : elle fait chercher
un champ qui n'existe pas, ou passer a cote d'un champ qui existe.

Ce controle vivait en YAML dans le workflow, donc nulle part sur une machine de
developpement. Resultat previsible : on le decouvre en integration continue,
apres avoir pousse. Un controle qu'on ne peut pas lancer avant de pousser est
un controle qu'on subit.
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
    """Le detecteur voit-il une absence, et se tait-il sur une presence ?"""
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
