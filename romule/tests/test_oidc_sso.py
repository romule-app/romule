"""Does SSO still work after the internal accounts were added?"""
import atexit, http.cookiejar, json, os, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request

RACINE = tempfile.mkdtemp(prefix="ludo-oidc-"); PORT="8812"; FP="9902"
BASE="http://127.0.0.1:"+PORT
S = os.path.dirname(os.path.abspath(__file__))
for p in (PORT, FP):
    subprocess.run(["bash","-c","lsof -nP -iTCP:%s -sTCP:LISTEN 2>/dev/null|tail -n +2|awk '{print $2}'|xargs -r kill -9"%p])
fp = subprocess.Popen([sys.executable, os.path.join(S,"faux_oidc.py"), FP],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
srv = subprocess.Popen([sys.executable, "-m", "romule", "serve"],
                       env=dict(os.environ, ROMULE_ROOT=RACINE, ROMULE_WEB_PORT=PORT, ROMULE_NO_BROWSER="1"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(lambda: (fp.kill(), srv.kill()))
pot = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pot))

# A SECOND browser, kept intact: it is the one that enabled SSO, and the server
# hands it a 30-minute anti-lockout "bridge" to finish configuring itself.
# Without it, enabling an SSO with no administration group would make the
# instance unadministrable — including by whoever has just enabled it. That
# bridge already exists in the server; this test takes it, and proves along the
# way that it does its job.
pont = http.cookiejar.CookieJar()
op_pont = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pont))

def appel(c, corps=None, avec=None):
    op_ = avec or op
    e={"Origin":BASE}; d=None
    if corps is not None:
        d=json.dumps(corps).encode(); e["Content-Type"]="application/json"
    try:
        with op_.open(urllib.request.Request(BASE+c,data=d,headers=e),timeout=20) as r:
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
                      "oidc_redirect":BASE}, avec=op_pont)
c,b = appel("/auth/moi")
t("SSO actif", json.loads(b).get("mode")=="oidc", b[:120])
pot.clear()
c,b = appel("/api/job"); t("refuse sans session", c==401, c)
c,b = appel("/auth/login")           # follows the redirects to the callback
t("flux de connexion complet", c==200, c)
c,b = appel("/auth/moi")
s=(json.loads(b) or {}).get("session") or {}
t("identite recuperee", s.get("email")=="dino@exemple.fr", s)
c,b = appel("/api/job"); t("acces accorde", c==200, c)
c,b = appel("/api/comptes", {})
t("comptes internes vides en mode SSO", json.loads(b)["comptes"]==[], b[:80])

# ----------------------------------------------------------------- the role
#
# `oidc_groupes` says WHO MAY ENTER. `oidc_admin_groupes` says WHO ADMINISTERS.
# Those are two different questions: confusing them would hand administration to
# everyone, and make the role model decorative.
#
# The fake provider puts this user in the "ludo" group.
print("   -- le role vient des groupes, et le defaut refuse --")

# By default, `oidc_admin_groupes` is empty: nobody administers. An empty
# setting must NEVER mean "everybody".
c,b = appel("/api/scan")
moi = (json.loads(b) or {}).get("moi") or {}
t("sans groupe d'administration, la session SSO ne l'est pas",
  moi.get("admin") is False, moi)
t("elle est bien reconnue comme session SSO", moi.get("source")=="oidc", moi)
c,b = appel("/api/journal-clear", {})
t("et elle est refusee sur une route reservee", c==403, c)

# The "ludo" group grants administration. You have to log in again: the role is
# written into the TOKEN at login, it does not change mid-session — that is how
# most SSOs behave, and it is documented.
pot.clear()
c,_ = appel("/api/config", {"oidc_admin_groupes":"ludo"}, avec=op_pont)
t("le pont d'anti-verrouillage permet encore de configurer", c==200, c)
c,b = appel("/auth/login")
c,b = appel("/api/scan")
moi = (json.loads(b) or {}).get("moi") or {}
t("le groupe d'administration donne le role", moi.get("admin") is True, moi)
c,b = appel("/api/journal-clear", {})
t("et la route reservee s'ouvre", c==200, c)

# Removed from the group: the CURRENT session keeps its role — that is what was
# announced — but the next one does not.
appel("/api/config", {"oidc_admin_groupes":"autre-groupe"}, avec=op_pont)
c,b = appel("/api/scan")
t("la session en cours conserve son role",
  ((json.loads(b) or {}).get("moi") or {}).get("admin") is True)
pot.clear()
c,b = appel("/auth/login")
c,b = appel("/api/scan")
moi = (json.loads(b) or {}).get("moi") or {}
t("la session suivante ne l'a plus", moi.get("admin") is False, moi)
c,b = appel("/api/journal-clear", {})
t("et la route reservee se referme", c==403, c)
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)"%(ok,fail))
sys.exit(1 if fail else 0)
