"""A proxy header must never be enough to pass for local.

Access without authentication rests on `_local()`: "the request comes from this
machine, so it comes from its owner". Behind a reverse proxy installed on the
same host — nginx, Caddy, Traefik, what every self-hosting guide recommends —
ALL requests arrive from 127.0.0.1. The assumption collapses, and both the token
and the "network access" setting become decorative.

So two situations are told apart:

  * nobody relays    -> a request from 127.0.0.1 really is local;
  * somebody relays  -> the peer's address says nothing any more, unless the
                        operator has DECLARED their proxy.
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
    autre.terminate(); autre = None

    print("   -- proxy declare en CIDR --")
    # Under Docker, the proxy's address is assigned dynamically: an exact
    # address would be wrong at the first `docker compose down`. The setting the
    # documentation recommends was therefore unusable in the deployment it
    # recommends.
    autre, base3 = demarrer(ROMULE_TRUSTED_PROXIES="127.0.0.0/8")
    t("un pair dans le reseau declare est cru",
      appel(base3, "/api/job", {"X-Forwarded-For": "127.0.0.1"}) == 200)
    t("et il ne fait pas croire n'importe qui",
      appel(base3, "/api/job", {"X-Forwarded-For": "203.0.113.7"}) in (401, 403))
    autre.terminate(); autre = None

    print("   -- la notation CIDR n'est pas une adresse --")
    # A network notation is not an address, and must never be compared as one.
    # If "10.0.0.0/8" stayed in the set of EXACT addresses, writing that string
    # into X-Forwarded-For would be enough to pass there for a declared relay —
    # and so to choose which link Romule keeps while walking the chain.
    #
    # No real exploitation was demonstrated: behind a real proxy, the attacker's
    # address is appended ON THE RIGHT and the walk stops there. This is a
    # comparison defect, fixed as such — not a hole anyone claims to have proved.
    autre, base4 = demarrer(ROMULE_TRUSTED_PROXIES="127.0.0.1,10.0.0.0/8")
    t("un maillon egal a la notation CIDR n'est pas un relais de confiance",
      appel(base4, "/api/job",
            {"X-Forwarded-For": "127.0.0.1, 10.0.0.0/8"}) in (401, 403))
    t("mais une vraie adresse du reseau declare l'est",
      appel(base4, "/api/job",
            {"X-Forwarded-For": "127.0.0.1, 10.1.2.3"}) == 200)
finally:
    for p in (srv, autre):
        if p: p.terminate()
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
