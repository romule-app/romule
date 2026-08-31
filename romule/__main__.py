"""Point d'entree du paquet : `python3 -m romule`.

Le script `switch.py` a la racine reste valable — c'est ce que lancent les
tests et ce que documentait l'ancien projet — mais un paquet installe n'a pas
de script a la racine. Le fichier ne peut pas s'appeler `romule.py` : il vivrait
a cote du dossier `romule/` et Python ne saurait plus lequel importer.
"""
import sys

from . import cli


def main():
    cli.main(sys.argv[1:])


if __name__ == "__main__":
    main()
