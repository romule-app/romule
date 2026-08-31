"""Un service expose doit etre joignable — et seulement par qui detient le jeton.

Le defaut que ces controles empechent de revenir : un conteneur se lie a
0.0.0.0, sinon il serait injoignable depuis l'hote. Mais sans compte, sans
jeton et sans `lan_access`, toute requete non locale etait refusee — avec un
message invitant a « activer l'acces dans les reglages », reglages qu'on ne
pouvait justement pas atteindre. `docker compose up` menait donc a un 403 sans
issue, sur le chemin d'installation principal.

Trois proprietes, et la troisieme compte autant que les deux premieres :

  1. un service EXPOSE sans moyen d'entrer engendre un jeton et l'affiche ;
  2. ce jeton, et lui seul, ouvre l'acces ;
  3. un service LOCAL n'en engendre aucun — sinon on imposerait un jeton a qui
     n'a jamais demande a etre joignable.
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)
JETON_DANS_URL = re.compile(r"token=([A-Za-z0-9_-]+)")

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c:
        ok += 1
        print("      OK   %s" % n)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (n, d))


def libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return str(s.getsockname()[1])


def adresse_reseau():
    """L'adresse de cette machine SUR le reseau, ou None.

    Interroger 127.0.0.1 ne prouve rien : cette adresse est locale par
    definition, donc toujours autorisee. Le refus ne se constate que depuis une
    adresse que le serveur ne reconnait pas comme la sienne.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))     # reseau de documentation : aucun paquet
            a = s.getsockname()[0]
        return None if a.startswith("127.") else a
    except OSError:
        return None


def demarrer(racine, port, **env):
    """Lance un serveur en capturant sa sortie : le jeton s'y trouve."""
    srv = subprocess.Popen(
        [sys.executable, "-u", "-m", "romule", "serve"], cwd=RACINE_PROJET,
        env=dict(os.environ, ROMULE_ROOT=racine, ROMULE_WEB_PORT=port,
                 ROMULE_NO_BROWSER="1", **env),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = "http://127.0.0.1:" + port
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=5)
            break
        except urllib.error.HTTPError:
            break
        except Exception:
            if srv.poll() is not None:
                break
            time.sleep(0.5)
    return srv, base


def arreter(srv):
    """Rend la sortie complete du serveur, une fois qu'il a fini d'ecrire."""
    srv.terminate()
    try:
        return srv.communicate(timeout=20)[0] or ""
    except subprocess.TimeoutExpired:
        srv.kill()
        return srv.communicate()[0] or ""


def code(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as x:
        return x.code
    except Exception:
        return 0


print("   -- 1. service expose, aucun moyen d'entrer --")
racine = tempfile.mkdtemp(prefix="ludo-acces-")
port = libre()
srv, base = demarrer(racine, port, ROMULE_BIND="0.0.0.0")
reseau = adresse_reseau()
distant = "http://%s:%s" % (reseau, port) if reseau else None
sans = code(distant + "/") if distant else None
sortie = arreter(srv)
m = JETON_DANS_URL.search(sortie)
jeton = m.group(1) if m else ""

t("un jeton est engendre et affiche", bool(jeton), sortie[-300:])
t("l'adresse complete est donnee, pas seulement le jeton",
  "http://" in sortie and "?token=" in sortie)
if distant:
    t("depuis le reseau, sans jeton : refuse", sans == 403, "recu %s" % sans)
else:
    print("      (pas d'adresse reseau sur cette machine : refus non verifiable)")

# Il doit etre range hors de la configuration publique : /api/scan renvoie la
# configuration au navigateur, et un jeton qui s'y trouve n'en est plus un.
conf = json.loads((Path(racine) / "_romule-config.json").read_text())
t("le jeton est bien conserve sur disque", conf.get("jeton_auto") == jeton)

print("   -- 2. le jeton ouvre, et reste le meme --")
port2 = libre()
srv, base = demarrer(racine, port2, ROMULE_BIND="0.0.0.0")
distant2 = "http://%s:%s" % (reseau, port2) if reseau else base
avec = code("%s/?token=%s" % (distant2, jeton))
faux = code("%s/?token=%s" % (distant2, "x" * len(jeton)))
try:
    pub = json.loads(urllib.request.urlopen(
        "%s/api/scan?token=%s" % (base, jeton), timeout=30).read())
except Exception:
    pub = {}
sortie2 = arreter(srv)
m2 = JETON_DANS_URL.search(sortie2)

t("avec le jeton, l'acces est accorde", avec == 200, "recu %s" % avec)
if reseau:
    t("un jeton faux reste refuse", faux == 403, "recu %s" % faux)
else:
    print("      (pas d'adresse reseau : jeton faux non verifiable)")
t("le jeton ne change pas au redemarrage", bool(m2) and m2.group(1) == jeton)
t("le jeton n'est pas envoye au navigateur",
  "jeton_auto" not in (pub.get("config") or {}))

print("   -- 3. service local : rien ne doit etre impose --")
racine3 = tempfile.mkdtemp(prefix="ludo-acces-local-")
port3 = libre()
srv, base = demarrer(racine3, port3)
local = code(base + "/")
sortie3 = arreter(srv)
f3 = Path(racine3) / "_romule-config.json"
conf3 = json.loads(f3.read_text()) if f3.exists() else {}

t("aucun jeton engendre pour une ecoute locale",
  not JETON_DANS_URL.search(sortie3) and not conf3.get("jeton_auto"))
t("l'acces local reste direct", local == 200, "recu %s" % local)

print("      ------------------------------------------------")
print("      %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
