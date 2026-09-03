"""The package's entry point: `python3 -m romule`.

The root `switch.py` script still works — it is what the tests run and what the
old project documented — but an installed package has no script at its root.
This file cannot be called `romule.py`: it would sit beside the `romule/`
folder and Python would no longer know which to import.
"""
import sys

from . import cli


def main():
    return cli.main(sys.argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main())
