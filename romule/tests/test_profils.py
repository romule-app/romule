"""The emulator profiles describe paths: all of them must resolve.

Without hardware, one cannot prove a profile WORKS — hence the `verifie` flag,
true for Eden alone. What can be proved is that no profile is inconsistent:
well-formed paths, packages filled in when a data folder calls for them, and a
settings format either known or frankly absent.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from romule import profils

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c: ok += 1; print("      OK   %s" % n)
    else: fail += 1; print("      ECHEC %s  %s" % (n, d))


def _run():
    global ok, fail
    ok = fail = 0
    liste = profils.tous()
    t("des profils sont livres", len(liste) >= 5, len(liste))
    t("le profil par defaut existe", profils.get(profils.DEFAUT)["cle"] == profils.DEFAUT)

    cles = [p["cle"] for p in liste]
    t("aucune cle en double", len(cles) == len(set(cles)), cles)

    for p in liste:
        cle = p["cle"]
        cfg = {"emulateur": cle}
        for champ in ("cle", "nom", "paquets", "donnees", "config", "sauvegardes"):
            t("%s : champ %s present" % (cle, champ), champ in p)
        gabarit = p.get("donnees") or ""
        if gabarit:
            t("%s : au moins un paquet candidat" % cle, bool(p.get("paquets")),
              p.get("paquets"))
            chemin = profils.dossier_donnees(cfg)
            t("%s : le dossier se resout" % cle,
              chemin.startswith("/") and "{paquet}" not in chemin, chemin)
        conf = p.get("config")
        t("%s : format de reglages connu ou absent" % cle,
          conf is None or conf.get("format") == "ini-qt", conf)
        if conf:
            t("%s : les chemins de reglages se resolvent" % cle,
              profils.sous(conf["dossier"], cfg).startswith("/"))

    t("un profil inconnu retombe sur le defaut",
      profils.get("nexistepas")["cle"] == profils.DEFAUT)
    t("le profil generique n'annonce aucun reglage",
      not profils.config_pilotable({"emulateur": "generique"}))
    t("Eden est le seul profil verifie sur materiel",
      [p["cle"] for p in liste if p.get("verifie")] == ["eden"],
      [p["cle"] for p in liste if p.get("verifie")])

    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return fail == 0


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
