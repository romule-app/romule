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
    """Port attribue par le systeme : un test ne doit pas echouer parce qu'un
    autre processus occupait un numero fixe."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return str(s.getsockname()[1])


RACINE = tempfile.mkdtemp(prefix="ludo-totp-")
PORT = os.environ.get("LUDO_PORT_TOTP") or _port_libre()
BASE = "http://127.0.0.1:" + PORT
srv = subprocess.Popen([sys.executable, "switch.py"], cwd=RACINE_PROJET,
                       env=dict(os.environ, SWITCH_ROOT=RACINE, SWITCH_WEB_PORT=PORT, SWITCH_NO_BROWSER="1"),
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
    # L'activation vient de consommer le code de la fenetre courante : on prend
    # celui de la fenetre suivante, comme le ferait un utilisateur 30 s plus tard.
    code = totp.code(secret, time.time() + 30)
    c, b = appel("/auth/connexion", {"email": "d@e.fr", "mdp": MDP, "code": code}, forme=True)
    t("code valide accepte", c == 200, c)
    t("acces retabli", appel("/api/job")[0] == 200)

    pot.clear()
    c, b = appel("/auth/connexion", {"email": "d@e.fr", "mdp": MDP, "code": code}, forme=True)
    t("le MEME code ne peut pas etre rejoue", c == 401, c)

    # La TOLERANCE d'horloge (plus ou moins une fenetre) se verifie dans
    # test_totp_unite.py, ou l'instant est fourni. Ici, le test ne peut pas
    # savoir si la fenetre precedente a deja servi : quand une frontiere de
    # fenetre tombait entre la connexion ci-dessus et le controle, le code
    # designait une fenetre consommee et se faisait refuser comme un rejeu.
    # L'echec ressemblait alors a un defaut de tolerance, une fois sur cinq.
    time.sleep(4)                     # laisse retomber la temporisation par IP
    # On se reconnecte AVANT les essais volontairement faux qui suivent : chaque
    # echec repousse exponentiellement la prochaine tentative, et la reconnexion
    # se retrouvait derriere un blocage qu'elle avait elle-meme provoque. Une
    # connexion reussie remet ce compteur a zero.
    #
    # Le passage de frontiere garantit par ailleurs que ce code appartient a une
    # fenetre strictement posterieure a toutes celles deja consommees : il ne
    # peut donc pas etre pris pour un rejeu.
    # Franchir UNE frontiere ne suffit pas : la connexion precedente avait
    # utilise le code de la fenetre SUIVANTE, c'est donc exactement dans
    # celle-la qu'on atterrit. On vise la fenetre d'apres, qui n'a jamais servi
    # et reste dans la tolerance de plus ou moins une.
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
