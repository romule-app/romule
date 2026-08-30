"""Verifie le mode « comptes internes » de bout en bout, sur une racine jetable."""
import atexit, json, os, subprocess, sys, tempfile, time, http.cookiejar
import urllib.error, urllib.parse, urllib.request

RACINE = tempfile.mkdtemp(prefix="ludo-test-")
PORT = "8811"
BASE = "http://127.0.0.1:" + PORT
env = dict(os.environ, SWITCH_ROOT=RACINE, SWITCH_WEB_PORT=PORT, SWITCH_NO_BROWSER="1")
subprocess.run(["bash", "-c",
                "lsof -nP -iTCP:%s -sTCP:LISTEN 2>/dev/null | tail -n +2 "
                "| awk '{print }' | xargs -r kill -9" % PORT])
time.sleep(0.5)
srv = subprocess.Popen([sys.executable, "switch.py"], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

atexit.register(lambda: srv.kill())
pot = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pot),
                                 urllib.request.HTTPRedirectHandler())

def appel(chemin, corps=None, origine=BASE, forme=False, brut=None, methode=None):
    e = {"Origin": origine} if origine else {}
    donnees = None
    if brut is not None:
        donnees = brut
    elif forme:
        donnees = urllib.parse.urlencode(corps).encode()
        e["Content-Type"] = "application/x-www-form-urlencoded"
    elif corps is not None:
        donnees = json.dumps(corps).encode()
        e["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + chemin, data=donnees, headers=e, method=methode)
    try:
        with op.open(r, timeout=20) as rep:
            return rep.status, rep.read(), dict(rep.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read(), dict(ex.headers)

for _ in range(60):
    try:
        appel("/api/job"); break
    except Exception: time.sleep(0.5)

def js(b):
    try: return json.loads(b)
    except Exception: return {}

ok = fail = 0
def t(nom, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print("      OK   %s" % nom)
    else:    fail += 1; print("      ECHEC %s  %s" % (nom, detail))

print("   -- 1. avant tout compte, l'acces local reste libre --")
c, b, h = appel("/api/job")
t("serveur joignable", c == 200, c)
t("en-tete CSP present", "Content-Security-Policy" in h)
t("nosniff present", h.get("X-Content-Type-Options") == "nosniff")

print("   -- 2. creation du premier compte --")
c, b, _ = appel("/api/compte-creer", {"email": "dino@exemple.fr",
                                      "mdp": "grand cheval bleu 42", "nom": "Dino"})
t("compte cree", c == 200 and js(b).get("compte"), js(b))
c, b, _ = appel("/api/compte-creer", {"email": "faible@exemple.fr", "mdp": "123456"})
t("mot de passe faible refuse", c == 400, js(b))
c, b, _ = appel("/api/compte-creer", {"email": "dino@exemple.fr", "mdp": "autre chose longue"})
t("email deja pris refuse", c == 400, js(b))

print("   -- 3. bascule en mode interne --")
c, b, _ = appel("/api/config", {"auth_mode": "interne"})
t("mode enregistre", c == 200 and js(b)["config"]["auth_mode"] == "interne")
c, b, _ = appel("/auth/moi")
t("auth active", js(b).get("actif") is True and js(b).get("mode") == "interne", js(b))

print("   -- 4. sans session, tout est refuse (meme en local) --")
pot.clear()
c, b, _ = appel("/api/job")
t("401 sans session", c == 401, c)
t("formulaire de connexion servi", b"action='/auth/connexion'" in b)

print("   -- 5. connexion --")
c, b, _ = appel("/auth/connexion", {"email": "dino@exemple.fr", "mdp": "mauvais"}, forme=True)
t("mauvais mot de passe refuse", c == 401)
t("message unique", b"Email ou mot de passe incorrect" in b)
c, b, _ = appel("/auth/connexion", {"email": "dino@exemple.fr",
                                    "mdp": "grand cheval bleu 42"}, forme=True)
t("connexion acceptee", c == 200, c)
c, b, _ = appel("/api/job")
t("acces retabli", c == 200, c)
c, b, _ = appel("/auth/moi")
t("session lisible", (js(b).get("session") or {}).get("email") == "dino@exemple.fr", js(b))

print("   -- 6. CSRF --")
c, b, _ = appel("/api/config", {"lan_access": True}, origine="http://mechant.fr")
t("POST d'une autre origine rejete", c == 403, c)

print("   -- 7. secrets jamais renvoyes --")
appel("/api/config", {"oidc_client_secret": "tres-secret"})
c, b, _ = appel("/api/config", {})
cfg = js(b)["config"]
t("auth_secret absent", "auth_secret" not in cfg, list(cfg)[:3])
t("client_secret masque", cfg.get("oidc_client_secret") == "•" * 8, cfg.get("oidc_client_secret"))
appel("/api/config", {"oidc_client_secret": "•" * 8})
import pathlib
reel = json.loads(pathlib.Path(RACINE, "_switch-config.json").read_text())
t("secret conserve apres renvoi du masque", reel.get("oidc_client_secret") == "tres-secret", reel.get("oidc_client_secret"))

print("   -- 8. changement de mot de passe --")
c, b, _ = appel("/api/compte-mdp", {"ancien": "faux", "nouveau": "un autre tres long"})
t("ancien mot de passe exige", c == 400, js(b))
biscuits_avant = [c.value for c in pot if c.name == "switch_session"][0]
c, b, _ = appel("/api/compte-mdp", {"ancien": "grand cheval bleu 42",
                                    "nouveau": "petite lune verte 77"})
t("mot de passe change", c == 200, js(b))
# un autre navigateur qui detenait l'ancienne session
autre = urllib.request.build_opener()
r = urllib.request.Request(BASE + "/api/job", headers={"Cookie": "switch_session=" + biscuits_avant})
try:
    with autre.open(r, timeout=10) as rep: code = rep.status
except urllib.error.HTTPError as ex: code = ex.code
t("ancienne session invalidee ailleurs", code == 401, code)
c, b, _ = appel("/api/job")
t("session courante conservee", c == 200, c)

print("   -- 9. photo de profil --")
png = bytes.fromhex("89504e470d0a1a0a") + b"reste du fichier"
c, b, _ = appel("/api/compte-photo", brut=png)
t("PNG accepte", c == 200, js(b))
c, b, _ = appel("/api/compte-photo", brut=b"MZ ceci est un executable")
t("fichier non-image refuse", c == 400, js(b))
uid = js(appel("/api/comptes", {})[1])["moi"]
c, b, _ = appel("/photo/" + uid)
t("photo servie", c == 200 and b == png, c)
c, b, _ = appel("/photo/../_switch-comptes.json")
t("traversee de chemin bloquee", c == 404, c)

print("   -- 10. suppression et roles --")
c, b, _ = appel("/api/compte-supprimer", {"id": uid})
t("dernier compte non supprimable", c == 400, js(b))
c, b, _ = appel("/api/compte-creer", {"email": "deux@exemple.fr", "mdp": "encore un mot long"})
second = js(b).get("compte", {})
t("le premier compte est administrateur, le second non",
  not second.get("admin"), second)
# Le compte connecte est le premier, donc l'administrateur : supprimer le
# SECOND est permis.
c, b, _ = appel("/api/compte-supprimer", {"id": second.get("id")})
t("un administrateur supprime un autre compte", c == 200, js(b))
# Mais se supprimer lui-meme ne doit pas laisser la ludotheque sans personne
# pour l'administrer.
appel("/api/compte-creer", {"email": "trois@exemple.fr", "mdp": "un troisieme mot long"})
c, b, _ = appel("/api/compte-supprimer", {"id": uid})
t("le dernier administrateur n'est pas supprimable", c == 400, js(b))

print("   -- 11. le fichier des comptes ne contient aucun mot de passe --")
brut = pathlib.Path(RACINE, "_switch-comptes.json").read_text()
t("mot de passe absent du disque", "petite lune verte" not in brut and "encore un mot long" not in brut)
# fuite:ok ce test garantit justement qu'aucun mot de passe n'est stocke en clair
t("empreinte scrypt", "scrypt$131072$8$1$" in brut, brut[:80])

srv.terminate()
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)   (racine jetable : %s)" % (ok, fail, RACINE))
sys.exit(1 if fail else 0)
