#!/usr/bin/env python3
"""A fake `adb`, so the test suite stops depending on hardware.

The tests gave three different results depending on whether a console was
plugged in, absent, or plugged in but offline — and nobody chose which. That is
what left five French strings on the home screen for weeks: the "no console"
branch never displayed on the machine that ran the tests.

This script stands in for the binary through `ROMULE_ADB`. The state replayed
comes from `ROMULE_FAUX_ADB`:

    pret        a console answers, all is well (default)
    hors-ligne  a console is seen, but refuses to talk
    aucune      nothing is plugged in

It does not try to imitate adb: it returns what the code really reads. Any
unknown command returns 0 and an empty output, which `_shell` already reads as
"nothing found".
"""
import os
import sys

ETAT = os.environ.get("ROMULE_FAUX_ADB", "pret").strip().lower()
SERIE = "192.0.2.10:5555"          # RFC 5737 : ne designe aucune vraie machine

PROPS = {
    "ro.product.model": "Console De Test",
    "ro.product.manufacturer": "Romule",
    "ro.build.version.release": "13",
}


def sortir(texte="", code=0):
    if texte:
        sys.stdout.write(texte if texte.endswith("\n") else texte + "\n")
    raise SystemExit(code)


def main(argv):
    # `_run` inserts "-s <serial>": we set it aside before reading the command.
    if len(argv) >= 2 and argv[0] == "-s":
        argv = argv[2:]
    if not argv:
        sortir("", 1)
    cmd, reste = argv[0], argv[1:]

    if cmd == "devices":
        entete = "List of devices attached"
        if ETAT == "aucune":
            sortir(entete)
        etat = "offline" if ETAT == "hors-ligne" else "device"
        sortir("%s\n%s\t%s product:test model:Console_De_Test device:test"
               % (entete, SERIE, etat))

    # Everything below assumes a console that answers.
    if ETAT != "pret":
        sortir("error: device offline", 1)

    if cmd == "get-serialno":
        sortir(SERIE)
    if cmd == "shell":
        ligne = " ".join(reste)
        if ligne.startswith("getprop "):
            sortir(PROPS.get(ligne.split(None, 1)[1].strip(), ""))
        # The rest — df, dumpsys, find, ls — returns empty: the code already
        # knows how to handle "nothing found", and a test console has no games.
        sortir("")
    if cmd in ("connect", "disconnect"):
        sortir("connected to %s" % SERIE)
    if cmd == "pair":
        sortir("Successfully paired to %s" % SERIE)
    if cmd == "mdns":
        sortir("")
    sortir("")


if __name__ == "__main__":
    main(sys.argv[1:])
