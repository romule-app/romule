#!/usr/bin/env python3
"""Point d'entree de la ludotheque Switch.

    python3 switch.py            interface web locale (http://127.0.0.1:8787)
    python3 switch.py scan       inventaire en ligne de commande
    python3 switch.py --help     aide complete

Aucune dependance : bibliotheque standard Python 3.9+. La logique vit dans
le paquet switchlib/ (moteur partage web + CLI). Rien n'est jamais supprime.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from switchlib import cli  # noqa: E402


def _require_nsz():
    if not shutil.which("nsz"):
        print("nsz introuvable dans le PATH.")
        print("  brew install pipx && pipx ensurepath && pipx install nsz")
        sys.exit(1)


if __name__ == "__main__":
    # 'test' n'a pas besoin de nsz ; tout le reste si.
    if "test" not in sys.argv[1:2]:
        _require_nsz()
    cli.main(sys.argv[1:])
