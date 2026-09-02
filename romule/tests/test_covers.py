"""Jaquettes : l'ordre des sources, et ce qui declenche vraiment le repli.

Le repli IGDB doit repondre a la question « aucune IMAGE », pas « aucune
ADRESSE ». La nuance n'est pas theorique : une adresse nlib ou SteamGridDB qui
rend un 404 est une adresse quand meme. Un repli branche sur la liste des
adresses n'aurait donc jamais servi les jeux qui en ont le plus besoin — ceux
dont la source principale repond a cote.

Chaque controle est double : ce que le repli doit faire, et ce qu'il ne doit
pas faire. Un repli qu'on n'a jamais vu s'abstenir ne prouve rien.
"""
import os
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp())
sys.path.insert(0, str(ICI.parent.parent))

ok = fail = 0
IMAGE = b"\x89PNG\r\n\x1a\n" + b"x" * 5000        # au-dela de covers.MINI


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
        # --- La source principale rend une adresse, mais pas d'image --------
        covers._FAILED.clear()
        p = covers.fetch("0100abcdef000000", "Un Jeu (Europe) (En,Fr).3ds", cfg)
        t("une adresse qui echoue laisse sa chance a IGDB", p is not None, p)
        # Le nom passe a IGDB doit etre le TITRE, pas le nom de fichier : ses
        # mots distinctifs comprendraient « europe » et « 3ds », et le
        # rapprochement rejetterait le bon jeu. C'est exactement ce qui
        # privait « Crazy Construction » de jaquette apres le repli.
        t("IGDB recoit le titre nettoye, pas le nom de fichier",
          appels["igdb"] == ["Un Jeu"], appels["igdb"])
        t("la source principale a ete essayee D'ABORD",
          len(appels["telecharge"]) == 2 and "igdb" not in appels["telecharge"][0],
          appels["telecharge"])
        t("l'image rangee est celle d'IGDB",
          p and p.read_bytes() == IMAGE)

        # --- La source principale rend une image : IGDB n'a rien a faire ---
        appels["telecharge"].clear(); appels["igdb"].clear()
        covers._FAILED.clear()
        covers._download = lambda url, headers=None: (
            appels["telecharge"].append(url) or IMAGE)
        p = covers.fetch("0100feedbeef0000", "Un Autre Jeu", cfg)
        t("la source principale suffit", p is not None, p)
        t("IGDB n'est PAS appele quand une image a ete obtenue",
          appels["igdb"] == [], appels["igdb"])

        # --- Aucune source n'a d'image -------------------------------------
        appels["telecharge"].clear(); appels["igdb"].clear()
        covers._FAILED.clear()
        covers._download = faux_download
        igdb.jaquette = lambda nom, cfg=None: (appels["igdb"].append(nom) or None)
        p = covers.fetch("0100000000000000", "Introuvable Partout", cfg)
        t("sans image nulle part, on rend None", p is None, p)
        t("l'echec est memorise pour ne pas etre rejoue",
          covers._echec_recent(covers.cle_cache("0100000000000000", None)))

        # --- Sans nom, IGDB n'est pas interrogeable -------------------------
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
