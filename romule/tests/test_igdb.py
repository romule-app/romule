"""IGDB: plumbing checked against a fake provider.

Without real Twitch credentials, this is the only way to guarantee that the token
is renewed at the right moment, that a failure is not replayed in a loop, and
that the absence of configuration triggers no network call.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp())
sys.path.insert(0, str(ICI.parent.parent))

def _port_libre(variable):
    """A port asked of the system, rather than a frozen number.

    A fixed port eventually meets a server left by an earlier run, or anything
    else on the machine: the test then talks to THAT service, and returns a
    result that says nothing about the code just written. The variable is still
    accepted for whoever wants to pin it.
    """
    fixe = os.environ.get(variable)
    if fixe:
        return int(fixe)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


PORT = _port_libre("LUDO_PORT_IGDB")
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
        t("aucun appel sans identifiants", igdb.search("Chrono Trigger", vide) is None)

        mauvais = {"igdb_client_id": "mauvais", "igdb_client_secret": "x",
                   "igdb_token_url": BASE + "/oauth2/token", "igdb_url": BASE}
        t("identifiants refuses", igdb.token(mauvais, force=True) == "")

        cfg = {"igdb_client_id": "bon-id", "igdb_client_secret": "bon-secret",
               "igdb_token_url": BASE + "/oauth2/token", "igdb_url": BASE}
        t("jeton obtenu", igdb.token(cfg, force=True) == "jeton-test")
        f = igdb.search("Chrono Trigger", cfg)
        t("resume recupere", bool(f) and f["resume"].startswith("Un groupe"), f)
        t("le nom renvoye correspond bien a la recherche",
          bool(f) and f["nom"] == "Chrono Trigger", f)
        t("annee deduite", bool(f) and f["annee"] == "1995", f)
        t("editeur, pas developpeur", bool(f) and f["editeur"] == "Square", f)

        avant = compteurs()["jetons"]
        igdb.search("Chrono Trigger", cfg)
        t("jeton reutilise", compteurs()["jetons"] == avant)

        t("jeu introuvable", igdb.search("titre introuvable zzz", cfg) is None)
        n = len(compteurs()["requetes"])
        igdb.search("titre introuvable zzz", cfg)
        t("echec non rejoue", len(compteurs()["requetes"]) == n)

        # --- The IGDB cover (the fallback when SteamGridDB has nothing) -----
        #
        # Every check is double: what the fallback must RETURN, and what it must
        # REFUSE. A fallback that accepts everything would return covers of
        # unrelated games, which is worse than an empty sleeve.
        u = igdb.cover_url("Chrono Trigger", cfg)
        t("jaquette : adresse construite depuis l'image_id",
          u == "https://images.igdb.com/igdb/image/upload/t_cover_big_2x/co-test.jpg", u)

        u = igdb.cover_url("un titre voisin", cfg)
        t("jaquette : un jeu sans rapport est refuse meme s'il a une image",
          u is None, u)

        u = igdb.cover_url("jeu sans image", cfg)
        t("jaquette : un jeu sans image ne rend rien", u is None, u)
        f2 = igdb.search("jeu sans image", cfg)
        t("jaquette : l'absence d'image ne raye pas le jeu pour son resume",
          bool(f2) and f2["resume"] == "Un jeu sans jaquette.", f2)

        t("jaquette : rien sans identifiants", igdb.cover_url("Chrono Trigger", vide) is None)
        n2 = len(compteurs()["requetes"])
        igdb.cover_url("titre introuvable zzz", cfg)
        t("jaquette : un jeu deja introuvable n'est pas redemande",
          len(compteurs()["requetes"]) == n2)

        r = igdb.probe(cfg)
        # The double now returns the title SEARCHED FOR: that is what the real
        # IGDB does, and what the anti-mismatch filter requires.
        t("test des identifiants",
          r["token"] and r["exemple"] == "The Legend of Zelda", r)
    finally:
        srv.terminate()
    print("   ------------------------------------------------")
    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
