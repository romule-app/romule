"""Bornes : ce qui vient de la configuration ou du reseau reste a sa place.

Trois familles de defauts sont verrouillees ici.

  * Des noms venus de la CONFIGURATION finissaient en chemins de fichiers et en
    commandes distantes sans etre verifies : un dossier « ../.. » deplacait des
    ROMs hors de la ludotheque, une extension avec une apostrophe cassait la
    mise entre guillemets d'un `find` sur la console.
  * Le mode jeton n'avait aucun test, alors que c'est le mode recommande pour
    un service expose en permanence.
  * Les depots de fichiers n'avaient aucun plafond.
"""
import http.cookiejar, json, os, secrets, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, RACINE_PROJET)

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c: ok += 1; print("      OK   %s" % n)
    else: fail += 1; print("      ECHEC %s  %s" % (n, d))


def libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return str(s.getsockname()[1])


print("   -- ce qui vient de la configuration --")
from romule import systems, edenconf

for mauvais in ("../../evasion", "/etc", "a/b", "..", ""):
    t("dossier refuse : %r" % mauvais,
      systems.dossier_sur(mauvais, "repli") == "repli")
t("dossier normal accepte", systems.dossier_sur("Mega Drive", "x") == "Mega Drive")
t("extension normale acceptee", systems.extension_sure("gba") == ".gba")
t("extension avec apostrophe refusee",
  systems.extension_sure(".gba' -o -name '*") == "")

for mauvais in ("../../../data/x", "0100", "", "01006F8002326000/../x"):
    try:
        edenconf.game_ini(mauvais)
        t("title ID refuse : %r" % mauvais, False, "accepte")
    except ValueError:
        t("title ID refuse : %r" % mauvais, True)
t("title ID valide accepte",
  edenconf.game_ini("01006f8002326000").endswith("01006F8002326000.ini"))

print("   -- mode jeton --")
JETON = secrets.token_urlsafe(24)
RACINE = tempfile.mkdtemp(prefix="ludo-limites-"); PORT = libre()
BASE = "http://127.0.0.1:" + PORT
srv = subprocess.Popen(
    [sys.executable, "-m", "romule", "serve"], cwd=RACINE_PROJET,
    env=dict(os.environ, ROMULE_ROOT=RACINE, ROMULE_WEB_PORT=PORT,
             ROMULE_NO_BROWSER="1", ROMULE_TOKEN=JETON,
             ROMULE_UPLOAD_MAX="1048576"),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def appel(chemin, entetes=None, op=None, donnees=None):
    op = op or urllib.request.build_opener()
    try:
        with op.open(urllib.request.Request(BASE + chemin, data=donnees,
                                            headers=entetes or {}), timeout=25) as r:
            return r.status, r.headers
    except urllib.error.HTTPError as x:
        return x.code, x.headers


# Le mode jeton refuse meme en local : on attend donc un 403, pas une panne.
for _ in range(60):
    try:
        appel("/api/job"); break
    except Exception:
        time.sleep(0.5)

try:
    # Depuis la machine, `_local()` accorde l'acces avant meme le jeton : on
    # se fait donc passer pour un appel distant, ce qui est le cas reel.
    distant = {"X-Forwarded-For": "203.0.113.4"}
    c, _ = appel("/api/job", distant)
    t("sans jeton, un appel distant est refuse", c == 403, c)
    c, _ = appel("/api/job", dict(distant, **{"X-Token": "mauvais"}))
    t("mauvais jeton refuse", c == 403, c)
    c, _ = appel("/api/job", dict(distant, **{"X-Token": JETON}))
    t("bon jeton accepte (en-tete)", c == 200, c)
    c, _ = appel("/api/job", dict(distant, **{"Cookie": "switch_token=" + JETON}))
    t("bon jeton accepte (cookie)", c == 200, c)
    c, _ = appel("/api/job", dict(distant, **{"Cookie": "autre=x; switch_token=" + JETON}))
    t("cookie lu comme un cookie, pas comme du texte", c == 200, c)
    c, _ = appel("/api/job", dict(distant, **{"Cookie": "x_switch_token=" + JETON}))
    t("un cookie au nom voisin ne passe pas", c == 403, c)
    c, e = appel("/?token=" + JETON, distant)
    pose = "".join(str(v) for k, v in (e or {}).items() if k.lower() == "set-cookie")
    t("le cookie du jeton est HttpOnly", "HttpOnly" in pose, pose[:80])

    print("   -- plafond de depot --")
    c, _ = appel("/api/upload",
                 dict(distant, **{"X-Token": JETON, "X-Filename": "jeu.nsp",
                                  "Origin": BASE}),
                 donnees=b"\0" * 4000)
    t("sous le plafond, accepte", c == 200, c)
finally:
    srv.terminate()
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
