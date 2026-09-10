#!/usr/bin/env python3
"""A fake `adb` that answers like a console with games on it.

`romule/tests/faux_adb.py` is deliberately spare: the tests need a state
machine — ready, offline, absent — and nothing else. The screenshots need the
opposite: a console that reports storage, a battery, an Android version and a
tree of games, so the pictures show the interface doing its job rather than its
empty state.

Two files rather than one switch, because the two have opposite goals. This one
may invent as much as it likes; the other must stay boring.
"""
import sys

SERIE = "192.0.2.10:5555"          # RFC 5737: designates no real machine
PROPS = {
    "ro.product.model": "Pocket 9",
    "ro.product.manufacturer": "Vitrine",
    "ro.build.version.release": "13",
}

# The same invented catalogue as `captures.py`, with the folders a console
# would really carry.
JEUX = {
    "GAMES": [("Aurora Drift [0100100000010000][v0].nsp", 12_000_000_000),
              ("Cinder Vale [0100110000020000][v0].nsp", 10_600_000_000),
              ("Copper Kite [0100120000030000][v0].nsp", 5_900_000_000)],
    "GBA": [("Iron Lantern.gba", 8_600_000), ("Jade Circuit.gba", 6_400_000)],
    "SNES": [("Lumen Trail.sfc", 2_100_000)],
    "PSX": [("Pale Comet.chd", 644_000_000)],
}


RACINE_JEUX = "/storage/emulated/0/Emulation/roms"


def _racine_du_find(ligne):
    """The path `find` was pointed at: its first argument, quotes stripped."""
    morceaux = ligne.split()
    for m in morceaux[1:]:
        if not m.startswith("-"):
            return m.strip("'\"").rstrip("/")
    return "/"


def sortir(texte="", code=0):
    if texte:
        sys.stdout.write(texte if texte.endswith("\n") else texte + "\n")
    raise SystemExit(code)


def _shell(ligne):
    if ligne.startswith("getprop "):
        sortir(PROPS.get(ligne.split(None, 1)[1].strip(), ""))
    if ligne.startswith("df"):
        sortir("Filesystem     1K-blocks      Used Available Use% Mounted on\n"
               "/dev/fuse      229376000  88604672  140771328  39% /storage/emulated\n"
               "/dev/block/sd  500097024 210489344  289607680  43% /storage/1A2B-3C4D")
    if ligne.startswith("dumpsys battery"):
        sortir("Current Battery Service state:\n"
               "  AC powered: false\n  USB powered: false\n"
               "  status: 3\n  level: 78\n  scale: 100\n  temperature: 291")
    if "find" in ligne:
        # The searched root, as `find` was given it. Answering the whole tree
        # whatever was asked made a per-platform scan find every platform's
        # files at once — and, worse, find nothing when the caller filtered on a
        # subfolder that the answer never mentioned.
        racine = _racine_du_find(ligne)
        dossiers = ["/storage/emulated/0/Emulation",
                    "/storage/emulated/0/Emulation/roms"]
        fichiers = []
        for dossier, contenu in JEUX.items():
            dossiers.append("%s/%s" % (RACINE_JEUX, dossier))
            for nom, _ in contenu:
                fichiers.append("%s/%s/%s" % (RACINE_JEUX, dossier, nom))
        sortie = dossiers if "-type d" in ligne else fichiers
        sortir("\n".join(x for x in sortie if x.startswith(racine)))
    if ligne.startswith("ls"):
        sortir("\n".join(JEUX))
    sortir("")


def main(argv):
    if len(argv) >= 2 and argv[0] == "-s":
        argv = argv[2:]
    if not argv:
        sortir("", 1)
    cmd, reste = argv[0], argv[1:]
    if cmd == "devices":
        sortir("List of devices attached\n%s\tdevice product:pocket9 "
               "model:Pocket_9 device:pocket9" % SERIE)
    if cmd == "get-serialno":
        sortir(SERIE)
    if cmd == "shell":
        _shell(" ".join(reste))
    if cmd in ("connect", "disconnect"):
        sortir("connected to %s" % SERIE)
    if cmd == "pair":
        sortir("Successfully paired to %s" % SERIE)
    sortir("")


if __name__ == "__main__":
    main(sys.argv[1:])
