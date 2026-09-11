"""A CD game is one game, not one game per track.

« Rayman (Europe) (Track 01).bin » through « (Track 25) » is a single
PlayStation title cut into twenty-five pieces. Listed piece by piece, it filled
the list with twenty-five Raymans — reported from a real library.

Two things have to hold at once, and only one of them is about reading:

  * the LIST shows one game, and its size is the whole disc;
  * the TRANSFER still sends every piece. A `.cue` whose tracks stayed on the
    server is a game that does not start, and nothing would say so.
"""
import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE))
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp(prefix="disques-"))

from romule import systems                                          # noqa: E402

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c:
        ok += 1
        print("      OK   %s" % n)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (n, d))


def item(nom, dossier="/roms/PSX", taille=100):
    return {"name": nom, "path": dossier + "/" + nom, "size": taille}


def _run():
    global ok, fail
    ok = fail = 0

    # --- tracks with no index: the set counts once, and weighs the whole disc
    pistes = [item("Rayman (Europe) (En,Fr,De) (Track %02d).bin" % i)
              for i in range(1, 26)]
    r = systems.fusionner_disques(pistes)
    t("vingt-cinq pistes font un jeu", len(r) == 1, [x["name"] for x in r])
    t("le nom perd le numero de piste",
      r and r[0]["name"] == "Rayman (Europe) (En,Fr,De).bin", r and r[0]["name"])
    t("la taille est celle du disque entier", r and r[0]["size"] == 2500,
      r and r[0]["size"])
    t("le nombre de pistes est dit", r and r[0]["pistes"] == 25)

    # --- an index file is the game; its tracks are its innards
    r = systems.fusionner_disques([
        item("Tekken 3.cue", taille=1),
        item("Tekken 3 (Track 01).bin", taille=10),
        item("Tekken 3 (Track 02).bin", taille=20)])
    t("le .cue est le jeu, pas ses pistes",
      [x["name"] for x in r] == ["Tekken 3.cue"], [x["name"] for x in r])

    # --- the plain pair, which is the ordinary case
    r = systems.fusionner_disques([item("Doom.cue"), item("Doom.bin")])
    t("un couple .cue/.bin ne fait qu'un jeu",
      [x["name"] for x in r] == ["Doom.cue"], [x["name"] for x in r])

    # --- what must NOT be merged
    r = systems.fusionner_disques([
        item("Crash Bandicoot.chd"), item("Spyro.chd"),
        item("Final Fantasy VII (Disc 1).cue"),
        item("Final Fantasy VII (Disc 2).cue")])
    t("des jeux distincts le restent", len(r) == 4, [x["name"] for x in r])

    # --- same name, two folders: two games
    r = systems.fusionner_disques([
        item("Rayman (Track 01).bin", dossier="/roms/PSX/a"),
        item("Rayman (Track 01).bin", dossier="/roms/PSX/b")])
    t("deux dossiers, deux jeux", len(r) == 2, [x["path"] for x in r])

    # --- an index in ANOTHER folder does not claim these tracks
    r = systems.fusionner_disques([
        item("Rayman.cue", dossier="/roms/PSX/a"),
        item("Rayman (Track 01).bin", dossier="/roms/PSX/b")])
    t("un index d'ailleurs ne revendique rien", len(r) == 2,
      [x["path"] for x in r])

    # --- the field names of the console listing, which are not the local ones
    distants = [{"nom": "Rayman (Track %02d).bin" % i,
                 "chemin": "/storage/ROMs/PSX/Rayman (Track %02d).bin" % i,
                 "taille": 10} for i in range(1, 4)]
    r = systems.fusionner_disques(distants, nom="nom", chemin="chemin",
                                  taille="taille")
    t("la liste de la console se fusionne aussi", len(r) == 1
      and r[0]["taille"] == 30, r)

    # --- and the transfer puts the pieces back
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "Tekken 3.cue").write_bytes(b"c")
        for i in (1, 2, 3):
            (d / ("Tekken 3 (Track %02d).bin" % i)).write_bytes(b"x")
        (d / "Autre jeu.chd").write_bytes(b"z")
        comp = systems.compagnons(str(d / "Tekken 3.cue"))
        t("le .cue rapatrie ses trois pistes", len(comp) == 3, comp)
        t("et rien d'autre",
          all("Tekken" in c for c in comp), comp)
        comp = systems.compagnons(str(d / "Tekken 3 (Track 01).bin"))
        t("depuis une piste, on retrouve l'index et les autres",
          len(comp) == 3 and any(c.endswith(".cue") for c in comp), comp)
        t("un jeu d'un seul fichier n'entraine rien",
          systems.compagnons(str(d / "Autre jeu.chd")) == [])

    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return fail == 0


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
