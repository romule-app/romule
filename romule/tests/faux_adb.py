#!/usr/bin/env python3
"""Un faux `adb`, pour que la suite de tests cesse de dependre du materiel.

Les tests donnaient trois resultats differents selon qu'une console etait
branchee, absente, ou branchee mais hors ligne — et personne ne choisissait
lequel. C'est ce qui a laisse cinq chaines francaises sur l'ecran d'accueil
pendant des semaines : la branche « aucune console » ne s'affichait jamais sur
la machine qui faisait tourner les tests.

Ce script se substitue au binaire par `ROMULE_ADB`. L'etat rejoue vient de
`ROMULE_FAUX_ADB` :

    pret        une console repond, tout va bien (defaut)
    hors-ligne  une console est vue, mais elle refuse de parler
    aucune      rien n'est branche

Il ne cherche pas a imiter adb : il rend ce que le code lit reellement. Toute
commande inconnue rend 0 et une sortie vide, ce que `_shell` interprete deja
comme « rien trouve ».
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
    # `_run` insere « -s <serie> » : on l'ecarte avant de lire la commande.
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

    # Tout ce qui suit suppose une console qui repond.
    if ETAT != "pret":
        sortir("error: device offline", 1)

    if cmd == "get-serialno":
        sortir(SERIE)
    if cmd == "shell":
        ligne = " ".join(reste)
        if ligne.startswith("getprop "):
            sortir(PROPS.get(ligne.split(None, 1)[1].strip(), ""))
        # Le reste — df, dumpsys, find, ls — rend vide : le code sait deja
        # traiter « rien trouve », et une console de test n'a pas de jeux.
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
