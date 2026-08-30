"""Le SSO fonctionne-t-il toujours apres l'ajout des comptes internes ?"""
import atexit, http.cookiejar, json, os, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request

RACINE = tempfile.mkdtemp(prefix="ludo-oidc-"); PORT="8812"; FP="9902"
BASE="http://127.0.0.1:"+PORT
S = os.path.dirname(os.path.abspath(__file__))
for p in (PORT, FP):
    subprocess.run(["bash","-c","lsof -nP -iTCP:%s -sTCP:LISTEN 2>/dev/null|tail -n +2|awk '{print $2}'|xargs -r kill -9"%p])
fp = subprocess.Popen([sys.executable, os.path.join(S,"faux_oidc.py"), FP],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
srv = subprocess.Popen([sys.executable,"switch.py"],
                       env=dict(os.environ, SWITCH_ROOT=RACINE, SWITCH_WEB_PORT=PORT, SWITCH_NO_BROWSER="1"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(lambda: (fp.kill(), srv.kill()))
pot = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pot))

def appel(c, corps=None):
    e={"Origin":BASE}; d=None
    if corps is not None:
        d=json.dumps(corps).encode(); e["Content-Type"]="application/json"
    try:
        with op.open(urllib.request.Request(BASE+c,data=d,headers=e),timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as x: return x.code, x.read()

for _ in range(60):
    try: appel("/api/job"); break
    except Exception: time.sleep(0.5)

ok=fail=0
def t(n,c,d=""):
    global ok,fail
    if c: ok+=1; print("      OK   %s"%n)
    else: fail+=1; print("      ECHEC %s  %s"%(n,d))

appel("/api/config", {"auth_mode":"oidc","oidc_issuer":"http://127.0.0.1:"+FP,
                      "oidc_client_id":"ludotheque","oidc_client_secret":"s3cr3t",
                      "oidc_redirect":BASE})
c,b = appel("/auth/moi")
t("SSO actif", json.loads(b).get("mode")=="oidc", b[:120])
pot.clear()
c,b = appel("/api/job"); t("refuse sans session", c==401, c)
c,b = appel("/auth/login")           # suit les redirections jusqu'au callback
t("flux de connexion complet", c==200, c)
c,b = appel("/auth/moi")
s=(json.loads(b) or {}).get("session") or {}
t("identite recuperee", s.get("email")=="dino@exemple.fr", s)
c,b = appel("/api/job"); t("acces accorde", c==200, c)
c,b = appel("/api/comptes", {})
t("comptes internes vides en mode SSO", json.loads(b)["comptes"]==[], b[:80])
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)"%(ok,fail))
sys.exit(1 if fail else 0)
