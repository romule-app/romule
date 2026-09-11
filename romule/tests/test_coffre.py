"""The vault: what gets copied, where, and what gets deleted.

Two of this module's gestures cannot be taken back — writing gigabytes to a
place the caller names, and DELETING folders in the name of rotation. Those are
exactly the two that re-reading the code does not cover.

What these cases prove, in the order things can go wrong:

  * a destination outside the allowed folders is refused, and nothing is
    written;
  * the room is checked BEFORE the copy, not at 94 %;
  * rotation deletes batches of ours and never a neighbouring folder — the
    most expensive defect here, and the one no re-reading catches;
  * an interrupted batch goes before a complete one;
  * the manifest says what the batch holds, with no Romule to read it.
"""
import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE))
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp(prefix="coffre-"))

from romule import config, vault                                   # noqa: E402

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c:
        ok += 1
        print("      OK   %s" % n)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (n, d))


class FauxJob:
    """Enough of `jobs.JobRunner` for `vault.run` to run, and nothing more."""

    def __init__(self, stop_apres=None):
        self.lignes = []
        self.total = self.fait = 0
        self.detail = ""
        self.stop_apres = stop_apres

    def log(self, ligne, niveau=None):
        self.lignes.append(str(ligne))

    def set_total(self, n):
        self.total = n

    def tick(self):
        self.fait += 1

    def set_detail(self, texte):
        self.detail = texte

    def checkpoint(self):
        # `None` = never stop; an integer = stop after n steps.
        return self.stop_apres is None or self.fait < self.stop_apres

    def dit(self, bout):
        return any(bout in l for l in self.lignes)


class FausseLudo:
    def __init__(self, fichiers):
        self.files = fichiers


def _ludo(base, n=3, taille=1024):
    """A library of n games, really written: we are measuring bytes."""
    dossier = base / "jeux"
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers = []
    for i in range(n):
        p = dossier / ("jeu%d.nsp" % i)
        p.write_bytes(b"x" * taille)
        fichiers.append({"path": str(p), "rel": p.name, "type": "BASE",
                         "size": taille})
    return FausseLudo(fichiers)


def _run():
    global ok, fail
    ok = fail = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        lib = _ludo(base)
        dest = base / "disque"
        dest.mkdir()

        # --- the preview, before anything is copied
        ap = vault.apercu(lib, {}, ["jeux"])
        t("l'apercu pese les jeux sans rien copier",
          ap["octets"] == 3 * 1024, ap["octets"])
        t("les sauvegardes de console ne sont pas chiffrees d'ici",
          [d for d in ap["detail"] if d["cle"] == "sauvegardes"][0]["octets"] is None)

        # --- a destination outside the bases is refused
        bases_avant = list(config.BASES)
        config.BASES[:] = [base / "autorise"]
        (base / "autorise").mkdir()
        _, erreur = vault.verifier_dest(str(base / "ailleurs"), creer=True)
        t("une destination hors des dossiers autorises est refusee", bool(erreur))
        t("et elle n'a pas ete creee au passage", not (base / "ailleurs").exists())
        config.BASES[:] = bases_avant

        # --- the room is checked before, not during
        job = FauxJob()
        vraie_taille = vault._espace
        vault._espace = lambda p: 1024          # far below the floor
        try:
            r = vault.run(job, lib, {}, sources=["jeux"], dest=str(dest))
        finally:
            vault._espace = vraie_taille
        t("place insuffisante : rien n'est lance", r is None)
        t("et le journal le dit avant la copie", job.dit("Place insuffisante"))
        t("aucun lot n'a ete cree", not vault.lots(dest))

        # --- a real copy
        job = FauxJob()
        lot = vault.run(job, lib, {}, sources=["jeux"], dest=str(dest), garder=3)
        t("la copie rend le chemin du lot", bool(lot))
        lots = vault.lots(dest)
        t("le lot est visible a la destination", len(lots) == 1, lots)
        t("il porte les trois fichiers", lots and lots[0]["fichiers"] == 3)
        t("il se dit complet", lots and lots[0]["complet"])
        t("le manifeste existe et nomme les sources",
          lots and lots[0]["sources"] == ["jeux"])
        copie = Path(lot) / "jeux" / "jeu0.nsp"
        t("le fichier est reellement la, et de la bonne taille",
          copie.is_file() and copie.stat().st_size == 1024)
        t("un ETA a ete pose pendant la copie, puis retire", job.detail == "")

        # --- rotation touches ONLY batches of ours
        voisin = dest / "photos-de-vacances"
        voisin.mkdir()
        (voisin / "plage.jpg").write_bytes(b"jpeg")
        faux_lot = dest / (vault.PREFIXE + "2000-01-01_000000")
        faux_lot.mkdir()                        # right name, no manifest
        (faux_lot / "rien").write_bytes(b"")
        for _ in range(3):
            job = FauxJob()
            vault.run(job, lib, {}, sources=["jeux"], dest=str(dest), garder=2)
        restants = vault.lots(dest)
        t("la rotation garde le nombre demande", len(restants) == 2, restants)
        t("le dossier voisin est intact", (voisin / "plage.jpg").is_file())
        t("un dossier sans manifeste n'est pas pris pour un lot",
          faux_lot.is_dir())

        # --- an interrupted batch goes first
        dest2 = base / "disque2"
        dest2.mkdir()
        vault.run(FauxJob(stop_apres=1), lib, {}, sources=["jeux"],
                  dest=str(dest2), garder=9)
        vault.run(FauxJob(), lib, {}, sources=["jeux"], dest=str(dest2), garder=9)
        avant = vault.lots(dest2)
        t("les deux lots sont la, l'un incomplet",
          len(avant) == 2 and sum(1 for l in avant if not l["complet"]) == 1, avant)
        job = FauxJob()
        vault._rotation(job, dest2, 1)
        apres = vault.lots(dest2)
        t("la rotation sacrifie l'interrompu et garde le complet",
          len(apres) == 1 and apres[0]["complet"], apres)

        # --- no source, no damage
        job = FauxJob()
        t("sans source choisie, rien ne se passe",
          vault.run(job, lib, {}, sources=[], dest=str(dest)) is None)
        t("et le journal le dit", job.dit("Aucune source"))

    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return fail == 0


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
