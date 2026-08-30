#!/usr/bin/env python3
"""Lancement depuis une copie du depot.

    python3 switch.py            interface web locale (http://127.0.0.1:8787)
    python3 switch.py scan       inventaire en ligne de commande
    python3 switch.py --help     aide complete

Equivalent a `python3 -m romule`, qui est la forme a privilegier une fois le
paquet installe. Ce fichier existe pour qu'un `git clone` suivi d'un
`python3 switch.py` fonctionne sans rien installer.

Aucune dependance Python : bibliotheque standard seule.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from romule import cli  # noqa: E402

if __name__ == "__main__":
    cli.main(sys.argv[1:])
