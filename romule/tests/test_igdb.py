"""IGDB : plomberie verifiee contre un faux fournisseur.

Sans identifiants Twitch reels, c'est la seule facon de garantir que le jeton
est renouvele au bon moment, qu'un echec n'est pas rejoue en boucle, et que
l'absence de configuration ne declenche aucun appel reseau.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp())
sys.path.insert(0, str(ICI.parent.parent))

PORT = int(os.environ.get("LUDO_PORT_IGDB", "9911"))
BASE = "http://127.0.0.1:%d" % PORT
ok = fail = 0


def t(nom, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("      OK   %s" % nom)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (nom, detail))


def compteurs():
    return json.load(urllib.request.urlopen(BASE + "/_compteurs"))


def main():
    srv = subprocess.Popen([sys.executable, str(ICI / "faux_igdb.py"), str(PORT)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    try:
        from romule import igdb
        vide = {"igdb_client_id": "", "igdb_client_secret": ""}
        t("inactif sans identifiants", igdb.configure(vide) is False)
        t("aucun appel sans identifiants", igdb.chercher("Chrono Trigger", vide) is None)

        mauvais = {"igdb_client_id": "mauvais", "igdb_client_secret": "x",
                   "igdb_token_url": BASE + "/oauth2/token", "igdb_url": BASE}
        t("identifiants refuses", igdb.jeton(mauvais, force=True) == "")

        cfg = {"igdb_client_id": "bon-id", "igdb_client_secret": "bon-secret",
               "igdb_token_url": BASE + "/oauth2/token", "igdb_url": BASE}
        t("jeton obtenu", igdb.jeton(cfg, force=True) == "jeton-test")
        f = igdb.chercher("Chrono Trigger", cfg)
        t("resume recupere", bool(f) and f["resume"].startswith("Un groupe"), f)
        t("le nom renvoye correspond bien a la recherche",
          bool(f) and f["nom"] == "Chrono Trigger", f)
        t("annee deduite", bool(f) and f["annee"] == "1995", f)
        t("editeur, pas developpeur", bool(f) and f["editeur"] == "Square", f)

        avant = compteurs()["jetons"]
        igdb.chercher("Chrono Trigger", cfg)
        t("jeton reutilise", compteurs()["jetons"] == avant)

        t("jeu introuvable", igdb.chercher("titre introuvable zzz", cfg) is None)
        n = len(compteurs()["requetes"])
        igdb.chercher("titre introuvable zzz", cfg)
        t("echec non rejoue", len(compteurs()["requetes"]) == n)

        # --- La jaquette IGDB (repli quand SteamGridDB n'a rien) ------------
        #
        # Chaque controle est double : ce que le repli doit RENDRE, et ce
        # qu'il doit REFUSER. Un repli qui accepte tout rendrait des jaquettes
        # de jeux sans rapport, ce qui est pire qu'une pochette vide.
        u = igdb.jaquette("Chrono Trigger", cfg)
        t("jaquette : adresse construite depuis l'image_id",
          u == "https://images.igdb.com/igdb/image/upload/t_cover_big_2x/co-test.jpg", u)

        u = igdb.jaquette("un titre voisin", cfg)
        t("jaquette : un jeu sans rapport est refuse meme s'il a une image",
          u is None, u)

        u = igdb.jaquette("jeu sans image", cfg)
        t("jaquette : un jeu sans image ne rend rien", u is None, u)
        f2 = igdb.chercher("jeu sans image", cfg)
        t("jaquette : l'absence d'image ne raye pas le jeu pour son resume",
          bool(f2) and f2["resume"] == "Un jeu sans jaquette.", f2)

        t("jaquette : rien sans identifiants", igdb.jaquette("Chrono Trigger", vide) is None)
        n2 = len(compteurs()["requetes"])
        igdb.jaquette("titre introuvable zzz", cfg)
        t("jaquette : un jeu deja introuvable n'est pas redemande",
          len(compteurs()["requetes"]) == n2)

        r = igdb.tester(cfg)
        # La doublure renvoie desormais le titre CHERCHE : c'est ce que fait le
        # vrai IGDB, et c'est ce que le filtre anti-hack exige.
        t("test des identifiants",
          r["jeton"] and r["exemple"] == "The Legend of Zelda", r)
    finally:
        srv.terminate()
    print("   ------------------------------------------------")
    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
