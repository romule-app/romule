"""An exposed service must be reachable — and only by whoever holds the token.

The defect these checks stop from coming back: a container binds to 0.0.0.0,
otherwise it would be unreachable from the host. But with no account, no token
and no `lan_access`, every non-local request was refused — with a message
inviting you to "enable access in the settings", settings you could precisely not
reach. `docker compose up` therefore led to a dead-end 403, on the main
installation path.

Three properties, and the third matters as much as the first two:

  1. an EXPOSED service with no way in generates a token and prints it;
  2. that token, and it alone, opens access;
  3. a LOCAL service generates none — otherwise a token would be forced on
     whoever never asked to be reachable.
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
# The token is printed on its own line now, not inside an address. A container
# cannot know the address anyone reaches it at (see `server._lan_ip`), and a
# secret reprinted at every restart ends up in every log attached to a bug
# report. So: the string, once, and a field in the interface to paste it into.
# The token is announced on the line that FOLLOWS the instruction, and only
# there. Anchoring on the instruction rather than on the shape of the string is
# what stops the test's own temporary folder — `/var/folders/7c/rv0vjgfj36bc…`
# on macOS — from passing for a secret, which it did.
ANNONCE = re.compile(r"colle ce jeton[^\n]*\n[^\n]*?([A-Za-z0-9_-]{30,})", re.I)


def jeton_de(sortie):
    """The announced token, or "" when nothing was announced."""
    m = ANNONCE.search(sortie)
    return m.group(1) if m else ""

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

    Querying 127.0.0.1 proves nothing: that address is local by definition, so
    always allowed. The refusal can only be observed from an address the server
    does not recognise as its own.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))     # reseau de documentation : aucun paquet
            a = s.getsockname()[0]
        return None if a.startswith("127.") else a
    except OSError:
        return None


def demarrer(racine, port, **env):
    """Starts a server capturing its output: the token is in there."""
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
    """Returns the server's full output, once it has finished writing."""
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
jeton = jeton_de(sortie)

t("un jeton est engendre et affiche", bool(jeton), sortie[-300:])
t("l'adresse a ouvrir est donnee avec", "http://" in sortie, sortie[-300:])
t("et ce qu'il faut faire du jeton", "colle ce jeton" in sortie.lower(),
  sortie[-300:])
# The one thing that must NOT be there: a link carrying the secret, which is
# what made it end up in shared logs and in browser history.
t("le jeton ne voyage plus dans l'adresse", "?token=" not in sortie)
if distant:
    # 401 and a FIELD, not a 403 and a sentence: the refusal is now a door.
    t("depuis le reseau, sans jeton : un champ est propose", sans == 401,
      "recu %s" % sans)
else:
    print("      (pas d'adresse reseau sur cette machine : refus non verifiable)")

# It must be stored outside the public configuration: /api/scan returns the
# configuration to the browser, and a token found there is no longer one.
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
jeton2 = jeton_de(sortie2)

t("avec le jeton, l'acces est accorde", avec == 200, "recu %s" % avec)
if reseau:
    t("un jeton faux reste refuse", faux == 401, "recu %s" % faux)
else:
    print("      (pas d'adresse reseau : jeton faux non verifiable)")
# ANNOUNCED once, not generated once: the second start must not reprint it.
t("le jeton n'est pas reaffiche au redemarrage", not jeton2, sortie2[-300:])
t("mais il est rappele qu'il en existe un",
  "romule token show" in sortie2, sortie2[-300:])
conf2 = json.loads((Path(racine) / "_romule-config.json").read_text())
t("le jeton ne change pas au redemarrage", conf2.get("jeton_auto") == jeton)
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
  not jeton_de(sortie3) and not conf3.get("jeton_auto"))
t("l'acces local reste direct", local == 200, "recu %s" % local)

print("   -- 4. le champ ou coller le jeton --")
racine4 = tempfile.mkdtemp(prefix="ludo-acces-champ-")
port4 = libre()
srv, base4 = demarrer(racine4, port4, ROMULE_BIND="0.0.0.0")
distant4 = "http://%s:%s" % (reseau, port4) if reseau else base4


def page(url, donnees=None, entetes=None):
    """(code, body). A form POST, or a plain GET."""
    req = urllib.request.Request(
        url, data=donnees.encode() if donnees else None,
        headers=entetes or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as x:
        return x.code, x.read().decode("utf-8", "replace")
    except Exception as exc:
        return 0, str(exc)


c4, corps = page(distant4 + "/")
t("le refus est une page, pas une phrase", c4 == 401 and "<form" in corps,
  "%s %s" % (c4, corps[:120]))
t("elle porte un champ pour le jeton", "name='jeton'" in corps, corps[:200])
t("elle dit ou retrouver le jeton", "romule token show" in corps, corps[:400])
# Unstyled, the page arrived as black on white and read as a broken server.
# The stylesheet is the only file served before anyone has got in.
t("la feuille de style est joignable sans jeton",
  code(distant4 + "/app.css") == 200)
t("et rien d'autre ne l'est", code(distant4 + "/app.js") == 401,
  "recu %s" % code(distant4 + "/app.js"))

jeton4 = jeton_de(arreter(srv))
srv, base4 = demarrer(racine4, port4, ROMULE_BIND="0.0.0.0")
entetes = {"Content-Type": "application/x-www-form-urlencoded",
           "Origin": distant4}
c_faux, _ = page(distant4 + "/auth/jeton", "jeton=pas-le-bon", entetes)
t("un jeton faux est refuse par le champ", c_faux == 401, "recu %s" % c_faux)
# The redirect must NOT be followed here. `urlopen` follows it by itself and
# drops the `Set-Cookie` on the way, so the final answer is the 401 of a
# browser that kept nothing — which says nothing about what we are checking.
class _SansSuivi(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


sans_suivi = urllib.request.build_opener(_SansSuivi)
req = urllib.request.Request(distant4 + "/auth/jeton",
                             data=("jeton=" + jeton4).encode(), headers=entetes)
try:
    with sans_suivi.open(req, timeout=20) as r:
        c_bon, cookie = r.status, r.headers.get("Set-Cookie") or ""
except urllib.error.HTTPError as x:
    c_bon, cookie = x.code, x.headers.get("Set-Cookie") or ""
t("le bon jeton fait entrer", c_bon == 302, "recu %s" % c_bon)
t("et le navigateur repart avec le cookie",
  "switch_token=" in cookie and "HttpOnly" in cookie, cookie[:90])
# A POST from elsewhere must not be able to plant the cookie.
c_ailleurs, _ = page(distant4 + "/auth/jeton", "jeton=" + jeton4,
                     {"Content-Type": "application/x-www-form-urlencoded",
                      "Origin": "http://ailleurs.invalid"})
t("une origine etrangere est rejetee", c_ailleurs == 403, "recu %s" % c_ailleurs)
arreter(srv)

print("   -- 5. renouveler le jeton depuis le terminal --")
avant = json.loads((Path(racine4) / "_romule-config.json").read_text())["jeton_auto"]
subprocess.run([sys.executable, "-m", "romule", "token", "reset"],
               cwd=RACINE_PROJET, env=dict(os.environ, ROMULE_ROOT=racine4),
               capture_output=True, text=True)
apres = json.loads((Path(racine4) / "_romule-config.json").read_text())
t("le jeton change", apres["jeton_auto"] != avant and apres["jeton_auto"])
# Otherwise a new token nobody has been told about is a lock-out.
t("et il sera annonce au prochain demarrage",
  apres.get("jeton_annonce") is False, apres.get("jeton_annonce"))
montre = subprocess.run([sys.executable, "-m", "romule", "token", "show"],
                        cwd=RACINE_PROJET,
                        env=dict(os.environ, ROMULE_ROOT=racine4),
                        capture_output=True, text=True).stdout
t("`token show` redonne le nouveau", apres["jeton_auto"] in montre, montre[:120])

print("      ------------------------------------------------")
print("      %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
