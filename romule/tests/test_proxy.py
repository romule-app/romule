"""Un en-tete de proxy ne doit jamais suffire a se faire passer pour local.

L'acces sans authentification repose sur `_local()` : « la requete vient de
cette machine, donc elle vient de son proprietaire ». Derriere un reverse
proxy installe sur le meme hote — nginx, Caddy, Traefik, ce que recommande
tout guide d'auto-hebergement — TOUTES les requetes arrivent de 127.0.0.1.
La supposition s'effondre, et le jeton comme le reglage « acces reseau »
deviennent decoratifs.

On distingue donc deux situations :

  * personne ne relaie  -> une requete de 127.0.0.1 est bien locale ;
  * quelqu'un relaie    -> l'adresse du pair ne dit plus rien, sauf si
                           l'operateur a DECLARE son proxy.
"""
import http.cookiejar, json, os, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)


def libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return str(s.getsockname()[1])


ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c: ok += 1; print("      OK   %s" % n)
    else: fail += 1; print("      ECHEC %s  %s" % (n, d))


def demarrer(**env):
    racine = tempfile.mkdtemp(prefix="ludo-proxy-")
    port = libre()
    srv = subprocess.Popen(
        [sys.executable, "-m", "romule", "serve"], cwd=RACINE_PROJET,
        env=dict(os.environ, ROMULE_ROOT=racine, ROMULE_WEB_PORT=port,
                 ROMULE_NO_BROWSER="1", **env),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:" + port
    for _ in range(60):
        try:
            urllib.request.urlopen(base + "/api/job", timeout=5); break
        except urllib.error.HTTPError:
            break
        except Exception:
            time.sleep(0.5)
    return srv, base


def appel(base, chemin, entetes=None, corps=None):
    pot = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pot))
    e = dict(entetes or {})
    d = None
    if corps is not None:
        d = json.dumps(corps).encode()
        e["Content-Type"] = "application/json"
        e["Origin"] = base
    try:
        with op.open(urllib.request.Request(base + chemin, data=d, headers=e),
                     timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as x:
        return x.code


srv = autre = None
try:
    print("   -- aucun proxy declare --")
    srv, base = demarrer()
    t("sans en-tete, 127.0.0.1 est bien local",
      appel(base, "/api/job") == 200)
    t("avec X-Forwarded-For, l'acces est refuse",
      appel(base, "/api/job", {"X-Forwarded-For": "203.0.113.7"}) in (401, 403),
      appel(base, "/api/job", {"X-Forwarded-For": "203.0.113.7"}))
    t("avec X-Real-IP, l'acces est refuse",
      appel(base, "/api/job", {"X-Real-IP": "203.0.113.7"}) in (401, 403))
    t("avec Forwarded, l'acces est refuse",
      appel(base, "/api/job", {"Forwarded": "for=203.0.113.7"}) in (401, 403))
    t("un POST relaye est refuse lui aussi",
      appel(base, "/api/config", {"X-Forwarded-For": "203.0.113.7"},
            {"lan_access": True}) in (401, 403))
    srv.terminate(); srv = None

    print("   -- proxy declare de confiance --")
    autre, base2 = demarrer(ROMULE_TRUSTED_PROXIES="127.0.0.1")
    t("le proxy annonce un client local : accepte",
      appel(base2, "/api/job", {"X-Forwarded-For": "127.0.0.1"}) == 200)
    t("le proxy annonce un client distant : refuse",
      appel(base2, "/api/job", {"X-Forwarded-For": "203.0.113.7"}) in (401, 403))
    t("chaine de proxys : seul le client compte",
      appel(base2, "/api/job",
            {"X-Forwarded-For": "203.0.113.7, 127.0.0.1"}) in (401, 403))
finally:
    for p in (srv, autre):
        if p: p.terminate()
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
