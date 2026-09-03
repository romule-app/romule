"""TOTP de bout en bout : activation, connexion en deux temps, rejeu, retrait."""
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, RACINE_PROJET)


def _port_libre():
    """A port assigned by the system: a test must not fail because another
    process happened to occupy a fixed number."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return str(s.getsockname()[1])


RACINE = tempfile.mkdtemp(prefix="ludo-totp-")
PORT = os.environ.get("LUDO_PORT_TOTP") or _port_libre()
BASE = "http://127.0.0.1:" + PORT
srv = subprocess.Popen([sys.executable, "-m", "romule", "serve"], cwd=RACINE_PROJET,
                       env=dict(os.environ, ROMULE_ROOT=RACINE, ROMULE_WEB_PORT=PORT, ROMULE_NO_BROWSER="1"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
pot = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pot))
def appel(c, corps=None, forme=False):
    e = {"Origin": BASE}; d = None
    if forme:
        d = urllib.parse.urlencode(corps).encode(); e["Content-Type"] = "application/x-www-form-urlencoded"
    elif corps is not None:
        d = json.dumps(corps).encode(); e["Content-Type"] = "application/json"
    try:
        with op.open(urllib.request.Request(BASE+c, data=d, headers=e), timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as x: return x.code, x.read()
for _ in range(60):
    try: appel("/api/job"); break
    except Exception: time.sleep(0.5)
from romule import totp
ok = fail = 0
def t(n, c, d=""):
    global ok, fail
    if c: ok += 1; print("      OK   %s" % n)
    else: fail += 1; print("      ECHEC %s  %s" % (n, d))
try:
    MDP = "grand cheval bleu 42"
    appel("/api/compte-creer", {"email": "d@e.fr", "mdp": MDP, "nom": "Dino"})
    appel("/api/config", {"auth_mode": "interne"})
    c, b = appel("/auth/connexion", {"email": "d@e.fr", "mdp": MDP}, forme=True)
    t("connexion sans second facteur", c == 200, c)

    c, b = appel("/api/compte-totp-preparer", {})
    prep = json.loads(b); secret = prep["secret"]
    t("secret genere", len(secret) >= 26 and prep["uri"].startswith("otpauth://"), prep)
    c, b = appel("/api/compte-totp-activer", {"code": "000000"})
    t("mauvais code refuse a l'activation", c == 400, b[:80])
    c, b = appel("/api/compte-totp-activer", {"code": totp.code(secret)})
    t("activation avec un vrai code", c == 200, b[:80])
    c, b = appel("/api/comptes", {})
    t("le compte est marque a double facteur",
      json.loads(b)["comptes"][0]["double_facteur"] is True)

    pot.clear()
    c, b = appel("/auth/connexion", {"email": "d@e.fr", "mdp": MDP}, forme=True)
    t("mot de passe seul ne suffit plus", c == 401, c)
    t("le formulaire demande le code", b"name='code'" in b)
    t("le mot de passe n'est pas redemande a l'aveugle", b"readonly" in b)
    c, b = appel("/auth/connexion",
                 {"email": "d@e.fr", "mdp": MDP, "code": "123456"}, forme=True)
    t("code faux refuse", c == 401, c)
    # Enabling has just consumed the current window's code: we take the next
    # window's, as a user would 30 s later.
    code = totp.code(secret, time.time() + 30)
    c, b = appel("/auth/connexion", {"email": "d@e.fr", "mdp": MDP, "code": code}, forme=True)
    t("code valide accepte", c == 200, c)
    t("acces retabli", appel("/api/job")[0] == 200)

    pot.clear()
    c, b = appel("/auth/connexion", {"email": "d@e.fr", "mdp": MDP, "code": code}, forme=True)
    t("le MEME code ne peut pas etre rejoue", c == 401, c)

    # Clock TOLERANCE (plus or minus one window) is checked in
    # test_totp_unite.py, where the instant is supplied. Here, the test cannot
    # know whether the previous window has already been used: when a window
    # boundary fell between the login above and the check, the code named a
    # consumed window and was refused as a replay. The failure then looked like a
    # tolerance defect, one time in five.
    time.sleep(4)                     # lets the per-IP back-off settle
    # We log in again BEFORE the deliberately wrong attempts that follow: every
    # failure pushes the next attempt back exponentially, and the login ended up
    # behind a lockout it had caused itself. A successful login resets that
    # counter.
    #
    # Crossing the boundary also guarantees this code belongs to a window
    # strictly later than every window already consumed: it therefore cannot be
    # taken for a replay.
    # Crossing ONE boundary is not enough: the previous login used the NEXT
    # window's code, so that is exactly the window we land in. We aim at the one
    # after, which has never been used and stays within the plus-or-minus-one
    # tolerance.
    time.sleep(31 - (time.time() % 30))
    c, b = appel("/auth/connexion",
                 {"email": "d@e.fr", "mdp": MDP,
                  "code": totp.code(secret, time.time() + 30)},
                 forme=True)
    t("un code frais, d'une fenetre jamais utilisee, est accepte", c == 200, c)

    c, b = appel("/auth/connexion",
                 {"email": "d@e.fr", "mdp": MDP, "code": totp.code(secret, time.time() + 120)},
                 forme=True)
    t("code trop decale refuse", c == 401, c)
    time.sleep(5)
    appel("/auth/connexion",
          {"email": "d@e.fr", "mdp": MDP, "code": totp.code(secret, time.time() - 60)},
          forme=True)
    c, b = appel("/api/compte-totp-desactiver", {"mdp": "faux"})
    t("desactivation exige le mot de passe", c == 400, b[:60])
    c, b = appel("/api/compte-totp-desactiver", {"mdp": MDP})
    t("desactivation possible avec le mot de passe", c == 200, b[:60])
finally:
    srv.terminate()
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
