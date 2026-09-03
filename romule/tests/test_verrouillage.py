"""Enabling authentication must NEVER lock out whoever enables it."""
import http.cookiejar, json, os, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path
RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)
def libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return str(s.getsockname()[1])
RACINE = tempfile.mkdtemp(prefix="ludo-verrou-"); PORT = libre()
BASE = "http://127.0.0.1:" + PORT
srv = subprocess.Popen([sys.executable, "-m", "romule", "serve"], cwd=RACINE_PROJET,
                       env=dict(os.environ, ROMULE_ROOT=RACINE, ROMULE_WEB_PORT=PORT, ROMULE_NO_BROWSER="1"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
pot = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pot))
def appel(c, corps=None):
    e = {"Origin": BASE}; d = None
    if corps is not None:
        d = json.dumps(corps).encode(); e["Content-Type"] = "application/json"
    try:
        with op.open(urllib.request.Request(BASE+c, data=d, headers=e), timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as x: return x.code, x.read()
for _ in range(60):
    try: appel("/api/job"); break
    except Exception: time.sleep(0.5)
ok = fail = 0
def t(n, c, d=""):
    global ok, fail
    if c: ok += 1; print("      OK   %s" % n)
    else: fail += 1; print("      ECHEC %s  %s" % (n, d))
try:
    print("   -- mode « comptes internes » --")
    appel("/api/compte-creer", {"email": "a@b.fr", "mdp": "un mot de passe long"})
    c, b = appel("/api/config", {"auth_mode": "interne"})
    t("le changement repond en JSON", c == 200 and b.strip().startswith(b"{"), b[:60])
    c, b = appel("/api/job")
    t("l'appel suivant passe encore", c == 200, c)
    c, b = appel("/api/config", {"auth_mode": "aucun"})
    t("retour arriere possible", c == 200 and b.strip().startswith(b"{"), b[:60])

    print("   -- mode SSO mal configure --")
    c, b = appel("/api/config", {"auth_mode": "oidc", "oidc_issuer": "https://x.test",
                                 "oidc_client_id": "abc"})
    t("changement accepte", c == 200 and b.strip().startswith(b"{"), b[:60])
    c, b = appel("/api/job")
    t("pas de verrouillage immediat", c == 200, c)
    c, b = appel("/api/config", {"auth_mode": "aucun"})
    t("retour arriere possible", c == 200, c)

    print("   -- un navigateur SANS session reste bien refuse --")
    appel("/api/config", {"auth_mode": "interne"})
    autre = urllib.request.build_opener()
    try:
        with autre.open(urllib.request.Request(BASE + "/api/job"), timeout=10) as r:
            code = r.status
    except urllib.error.HTTPError as x: code = x.code
    t("un autre navigateur est refuse", code == 401, code)
finally:
    srv.terminate()
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
