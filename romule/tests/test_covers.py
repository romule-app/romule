"""Covers: the order of the sources, and what really triggers the fallback.

The IGDB fallback must answer the question "no IMAGE", not "no ADDRESS". The
distinction is not theoretical: an nlib or SteamGridDB address that returns a 404
is still an address. A fallback wired to the list of addresses would therefore
never have served the games that need it most — the ones whose main source
answers beside the point.

Every check is double: what the fallback must do, and what it must not do. A
fallback nobody has ever seen hold back proves nothing.
"""
import os
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp())
sys.path.insert(0, str(ICI.parent.parent))

ok = fail = 0
IMAGE = b"\x89PNG\r\n\x1a\n" + b"x" * 5000        # above covers.MINI


def t(nom, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("      OK   %s" % nom)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (nom, detail))


def main():
    from romule import covers, igdb

    appels = {"telecharge": [], "igdb": []}

    def faux_download(url, headers=None):
        appels["telecharge"].append(url)
        if "igdb" in url:
            return IMAGE
        raise OSError("404")            # la source principale repond a cote

    def fausse_jaquette(nom, cfg=None):
        appels["igdb"].append(nom)
        return "https://images.igdb.com/x.jpg"

    vrai_dl, vraie_jq = covers._download, igdb.jaquette
    covers._download, igdb.jaquette = faux_download, fausse_jaquette
    cfg = {"cover_provider": "nlib"}
    try:
        # --- The main source returns an address, but no image ---------------
        covers._FAILED.clear()
        p = covers.fetch("0100abcdef000000", "Un Jeu (Europe) (En,Fr).3ds", cfg)
        t("une adresse qui echoue laisse sa chance a IGDB", p is not None, p)
        # The name passed to IGDB must be the TITLE, not the file name: its
        # distinctive words would include "europe" and "3ds", and the matching
        # would reject the right game. That is exactly what deprived "Crazy
        # Construction" of a cover after the fallback.
        t("IGDB recoit le titre nettoye, pas le nom de fichier",
          appels["igdb"] == ["Un Jeu"], appels["igdb"])
        t("la source principale a ete essayee D'ABORD",
          len(appels["telecharge"]) == 2 and "igdb" not in appels["telecharge"][0],
          appels["telecharge"])
        t("l'image rangee est celle d'IGDB",
          p and p.read_bytes() == IMAGE)

        # --- The main source returns an image: IGDB has nothing to do ------
        appels["telecharge"].clear(); appels["igdb"].clear()
        covers._FAILED.clear()
        covers._download = lambda url, headers=None: (
            appels["telecharge"].append(url) or IMAGE)
        p = covers.fetch("0100feedbeef0000", "Un Autre Jeu", cfg)
        t("la source principale suffit", p is not None, p)
        t("IGDB n'est PAS appele quand une image a ete obtenue",
          appels["igdb"] == [], appels["igdb"])

        # --- No source has an image ----------------------------------------
        appels["telecharge"].clear(); appels["igdb"].clear()
        covers._FAILED.clear()
        covers._download = faux_download
        igdb.jaquette = lambda nom, cfg=None: (appels["igdb"].append(nom) or None)
        p = covers.fetch("0100000000000000", "Introuvable Partout", cfg)
        t("sans image nulle part, on rend None", p is None, p)
        t("l'echec est memorise pour ne pas etre rejoue",
          covers._echec_recent(covers.cle_cache("0100000000000000", None)))

        # --- With no name, IGDB cannot be queried ---------------------------
        appels["igdb"].clear()
        covers._FAILED.clear()
        covers.fetch("0100111111110000", None, cfg)
        t("aucun appel IGDB sans nom de jeu", appels["igdb"] == [], appels["igdb"])
    finally:
        covers._download, igdb.jaquette = vrai_dl, vraie_jq

    print("   ------------------------------------------------")
    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
