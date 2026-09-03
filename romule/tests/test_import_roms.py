"""The drop folder files each ROM into ITS platform's folder.

Three traps met for real, all of them silent:
  * a file with no title ID fell into the "UNKNOWN" branch and landed in GAMES/,
    among the Switch games;
  * an early return left before the ROMs were even examined;
  * a shared extension (.iso) was not listed at all — the file disappeared from
    the interface without a word.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp(prefix="ludo-import-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from romule import actions, config, systems  # noqa: E402

ok = fail = 0


def t(nom, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("      OK   %s" % nom)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (nom, detail))


class Journal:
    def __init__(self):
        self.lignes = []

    def log(self, m, n="info"):
        self.lignes.append(str(m))

    def set_total(self, *a): pass
    def set_detail(self, *a): pass
    def tick(self, *a): pass
    def checkpoint(self, *a): return True


class Biblio:
    files = []

    def scan(self, log=None): pass


def main():
    cfg = config.load_config()
    config.IMPORT.mkdir(parents=True, exist_ok=True)
    fichiers = {"Zelda.3ds": "3ds", "Sonic.gba": "gba", "Chrono.sfc": "snes",
                "Mario.nds": "nds", "Sonic2.md": "megadrive"}
    for nom in list(fichiers) + ["Metal Slug.iso", ".DS_Store"]:
        (config.IMPORT / nom).write_bytes(b"x" * 2048)

    items = actions.scan_import()
    t("les fichiers caches ne sont pas listes",
      not any(i["name"].startswith(".") for i in items),
      [i["name"] for i in items])
    t("l'extension partagee est signalee",
      any(i["type"] == "AMBIGU" and i["name"] == "Metal Slug.iso" for i in items),
      [i["type"] for i in items])

    j = Journal()
    actions.import_files(Biblio(), cfg, j, convert_after=False)

    for nom, cle in fichiers.items():
        attendu = systems.local_dir(cle, cfg) / nom
        t("%s -> %s/" % (nom, systems.get(cle)["folder"]), attendu.is_file(),
          "introuvable : %s" % attendu)
    t("aucune ROM dans GAMES/",
      not any(p.suffix.lower() in (".3ds", ".gba", ".sfc", ".nds", ".md")
              for p in (config.ROOT / "GAMES").rglob("*") if p.is_file())
      if (config.ROOT / "GAMES").exists() else True)
    t("le fichier ambigu reste dans le depot",
      (config.IMPORT / "Metal Slug.iso").is_file())
    t("et l'utilisateur en est informe",
      any("partagée" in x for x in j.lignes),
      [x[:60] for x in j.lignes[-3:]])
    print("   ------------------------------------------------")
    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
