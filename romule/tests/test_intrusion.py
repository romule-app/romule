"""Attack scenarios, played against a real server.

The other suites check functions; this one sends hostile requests to a running
server and watches what it does with them. Each scenario matches a point of the
security plan, and becomes a permanent check: a protection nobody replays is a
protection you lose without noticing.

  1. Path traversal through a hand-added platform.
  2. Command injection through a file extension.
  3. Brute force on the access token.
  4. An oversized upload.
  5. A slow connection holding a thread open.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)
JETON = "jeton-de-test-tres-long-et-inutile"

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
    """This machine's address ON the network, or None.

    Querying 127.0.0.1 proves nothing about a token: that address is local, so
    allowed outright. A token only guards the others.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))     # reseau de documentation
            a = s.getsockname()[0]
        return None if a.startswith("127.") else a
    except OSError:
        return None


def demarrer(racine, port, **env):
    srv = subprocess.Popen(
        [sys.executable, "-m", "romule", "serve"], cwd=RACINE_PROJET,
        env=dict(os.environ, ROMULE_ROOT=racine, ROMULE_WEB_PORT=port,
                 ROMULE_NO_BROWSER="1", **env),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:" + port
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/api/health", timeout=3).read()
            return srv, base
        except urllib.error.HTTPError:
            return srv, base
        except Exception:
            if srv.poll() is not None:
                break
            time.sleep(0.5)
    srv.kill()
    raise RuntimeError("le serveur n'a pas demarre")


def appel(base, chemin, corps=None, entetes=None, donnees=None):
    e = dict(entetes or {})
    d = donnees
    if corps is not None:
        d = json.dumps(corps).encode()
        e["Content-Type"] = "application/json"
        e.setdefault("Origin", base)
    try:
        with urllib.request.urlopen(
                urllib.request.Request(base + chemin, data=d, headers=e),
                timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as x:
        return x.code, x.read()
    except Exception as exc:
        return 0, str(exc).encode()


racine = tempfile.mkdtemp(prefix="ludo-intrusion-")
port = libre()
# Ceilings lowered to make the limits observable within a few seconds.
srv, base = demarrer(racine, port, ROMULE_TOKEN=JETON,
                     ROMULE_UPLOAD_MAX="4096", ROMULE_TIMEOUT="2")
AUTH = {"X-Token": JETON}

try:
    print("   -- 1. traversee de chemin par une plateforme ajoutee a la main --")
    _, b = appel(base, "/api/config", {"systemes_perso": [{
        "key": "evade", "name": "Evade",
        "folder": "../../../../tmp/evade-romule",
        "exts": [".bin"]}]}, AUTH)
    stocke = json.loads(b)["config"]["systemes_perso"][0]
    t("le dossier est assaini a l'ECRITURE", stocke["folder"] == "evade", stocke)

    _, b = appel(base, "/api/systems", entetes=AUTH)
    vu = [s for s in json.loads(b)["systems"] if s["key"] == "evade"]
    t("et il reste assaini a la LECTURE",
      vu and ".." not in vu[0]["folder"], vu)
    t("rien n'a ete cree hors de la ludotheque",
      not Path("/tmp/evade-romule").exists())

    print("   -- 2. injection de commande par une extension --")
    # The extensions end up in a `find` run on the console: an apostrophe or a
    # semicolon there would break the quoting.
    _, b = appel(base, "/api/config", {"systemes_perso": [{
        "key": "inject", "name": "Inject",
        "folder": "inject",
        "exts": [".bin", "; rm -rf /", "' ; id ; '", ".a$(whoami)"]}]}, AUTH)
    exts = json.loads(b)["config"]["systemes_perso"][0]["exts"]
    t("seules les vraies extensions survivent", exts == [".bin"], exts)

    print("   -- 3. force brute sur le jeton --")
    reseau = adresse_reseau()
    if not reseau:
        print("      (pas d'adresse reseau sur cette machine : scenario non joue)")
    else:
        # A dedicated server: throttling the main one would fail the following
        # scenarios for an unrelated reason.
        r2 = tempfile.mkdtemp(prefix="ludo-brute-")
        p2 = libre()
        s2, _ = demarrer(r2, p2, ROMULE_TOKEN=JETON, ROMULE_BIND="0.0.0.0",
                         ROMULE_RATE="30")
        distant = "http://%s:%s" % (reseau, p2)
        try:
            refus = sum(1 for i in range(20)
                        if appel(distant, "/api/health",
                                 entetes={"X-Token": "faux-%d" % i})[0] == 403)
            t("chaque essai errone est refuse", refus == 20,
              "%d refus sur 20" % refus)
            t("le bon jeton, lui, passe",
              appel(distant, "/api/health", entetes=AUTH)[0] == 200)
            # Without a limiter, a token is guessed at network speed.
            codes = [appel(distant, "/api/health",
                           entetes={"X-Token": "faux"})[0] for _ in range(40)]
            t("le limiteur de cadence finit par couper", 429 in codes,
              "codes vus : %s" % sorted(set(codes)))
        finally:
            s2.terminate()
            try:
                s2.wait(timeout=15)
            except subprocess.TimeoutExpired:
                s2.kill()

    print("   -- 4. depot surdimensionne --")
    c, b = appel(base, "/api/upload",
                 entetes=dict(AUTH, **{"X-Filename": "gros.nsp", "Origin": base}),
                 donnees=b"\0" * 40000)
    t("au-dessus du plafond, refuse", c in (400, 413), "recu %s : %s" % (c, b[:80]))
    c, _ = appel(base, "/api/upload",
                 entetes=dict(AUTH, **{"X-Filename": "petit.nsp", "Origin": base}),
                 donnees=b"\0" * 100)
    t("sous le plafond, accepte", c == 200, c)

    print("   -- 5. connexion lente --")
    # A client that opens a connection and sends nothing ties up a thread.
    # Without a timeout, a few dozen are enough to block the service.
    s = socket.create_connection(("127.0.0.1", int(port)), timeout=30)
    s.sendall(b"GET /api/health HTTP/1.1\r\nHost: x\r\n")   # requete inachevee
    debut = time.time()
    try:
        s.settimeout(20)
        ferme = s.recv(1) == b""
    except socket.timeout:
        ferme = False
    except OSError:
        ferme = True
    ecoule = time.time() - debut
    s.close()
    t("le serveur ferme une connexion inachevee",
      ferme and ecoule < 15, "ferme=%s apres %.1f s" % (ferme, ecoule))
    t("et il repond toujours ensuite",
      appel(base, "/api/health", entetes=AUTH)[0] == 200)

finally:
    srv.terminate()
    try:
        srv.wait(timeout=15)
    except subprocess.TimeoutExpired:
        srv.kill()

print("      ------------------------------------------------")
print("      %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
