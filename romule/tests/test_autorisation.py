"""Not all accounts are equal.

There used to be no roles at all: any logged-in user could delete the others, or
post `auth_mode: "aucun"` and switch authentication off for everybody. And two
routes — creating and deleting an account — did not even check a session existed.

Three rules are checked here:
  * the first account is an administrator, and is created from the machine alone;
  * an ordinary user touches neither the settings nor the other accounts;
  * there must always remain one administrator.
"""
import http.cookiejar, json, os, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)


def libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return str(s.getsockname()[1])


RACINE = tempfile.mkdtemp(prefix="ludo-autor-"); PORT = libre()
BASE = "http://127.0.0.1:" + PORT
srv = subprocess.Popen(
    [sys.executable, "-m", "romule", "serve"], cwd=RACINE_PROJET,
    env=dict(os.environ, ROMULE_ROOT=RACINE, ROMULE_WEB_PORT=PORT,
             ROMULE_NO_BROWSER="1"),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def navigateur():
    pot = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pot))


def appel(op, chemin, corps=None, entetes=None, forme=False):
    e = {"Origin": BASE}
    e.update(entetes or {})
    d = None
    if corps is not None and forme:
        # `/auth/connexion` receives a form, not JSON: it is the login page
        # served by the server itself that posts it.
        d = urllib.parse.urlencode(corps).encode()
        e["Content-Type"] = "application/x-www-form-urlencoded"
    elif corps is not None:
        d = json.dumps(corps).encode(); e["Content-Type"] = "application/json"
    try:
        with op.open(urllib.request.Request(BASE + chemin, data=d, headers=e),
                     timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as x:
        return x.code, x.read()


def js(b):
    try: return json.loads(b or b"{}")
    except Exception: return {}


patron = navigateur()
for _ in range(60):
    try: appel(patron, "/api/job"); break
    except Exception: time.sleep(0.5)

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c: ok += 1; print("      OK   %s" % n)
    else: fail += 1; print("      ECHEC %s  %s" % (n, d))


try:
    print("   -- creation du premier compte --")
    c, b = appel(patron, "/api/compte-creer",
                 {"email": "chef@exemple.fr", "mdp": "un mot de passe long"},
                 {"X-Forwarded-For": "203.0.113.9"})
    t("refusee depuis le reseau", c == 403, (c, js(b)))
    c, b = appel(patron, "/api/compte-creer",
                 {"email": "chef@exemple.fr", "mdp": "un mot de passe long"})
    chef = js(b).get("compte", {})
    t("acceptee depuis la machine", c == 200, js(b))
    t("le premier compte est administrateur", chef.get("admin") is True, chef)

    c, b = appel(patron, "/api/compte-creer",
                 {"email": "simple@exemple.fr", "mdp": "encore un mot long"})
    simple = js(b).get("compte", {})
    t("le second ne l'est pas", simple.get("admin") is False, simple)

    print("   -- un utilisateur ordinaire est limite --")
    appel(patron, "/api/config", {"auth_mode": "interne"})
    lambda_ = navigateur()
    c, b = appel(lambda_, "/auth/connexion",
                 {"email": "simple@exemple.fr", "mdp": "encore un mot long"},
                 forme=True)
    t("il peut se connecter", c == 200, (c, js(b)))
    c, b = appel(lambda_, "/api/job")
    t("il peut consulter", c == 200, c)
    c, b = appel(lambda_, "/api/config", {"auth_mode": "aucun"})
    t("il ne peut pas eteindre l'authentification", c == 403, (c, js(b)))
    c, b = appel(lambda_, "/api/compte-supprimer", {"id": chef.get("id")})
    t("il ne peut pas supprimer l'administrateur", c == 403, (c, js(b)))
    c, b = appel(lambda_, "/api/compte-creer",
                 {"email": "x@exemple.fr", "mdp": "un mot de passe long"})
    t("il ne peut pas creer de compte", c == 403, (c, js(b)))
    c, b = appel(lambda_, "/api/compte-mdp",
                 {"ancien": "encore un mot long", "nouveau": "son nouveau mot long"})
    t("il change SON mot de passe", c == 200, (c, js(b)))

    print("   -- ni lancer les actions destructives --")
    # The role model announced three reserved areas: the configuration, the
    # accounts, and the destructive actions. The first two were honoured, the
    # third was not. The worst of them: restoring a backup puts the ACCOUNTS FILE
    # back in place, so it hands administration back to whoever had lost it. The
    # other two erase the traces.
    for route, corps, quoi in (
            ("/api/sauvegarde-restaurer", {"lot": "x"}, "restaurer une sauvegarde"),
            ("/api/journal-clear", {}, "effacer le journal"),
            ("/api/acces", {}, "lire le journal des acces"),
            ("/api/trash-purge", {}, "vider la corbeille"),
            ("/api/reorganize-local", {}, "reorganiser la ludotheque"),
            ("/api/wifi-forget", {}, "oublier la console"),
            ("/api/audit", {}, "lancer l'audit de securite"),
    ):
        c, b = appel(lambda_, route, corps)
        t("il ne peut pas %s" % quoi, c == 403, (c, js(b)))

    # The seven routes above were chosen by hand. But the reserved set holds
    # twenty-seven, and nothing guaranteed the other twenty honoured it: a route
    # added to `ADMIN_ONLY` without being exercised is a reserve nobody has
    # checked. So we take them ALL, read from the server itself so the list
    # cannot drift.
    print("   -- et aucune des routes reservees, sans exception --")
    sys.path.insert(0, RACINE_PROJET)
    from romule.server import Handler                              # noqa: E402
    reservees = sorted(Handler.ADMIN_ONLY)
    t("la reserve est lue dans le serveur", len(reservees) >= 20, len(reservees))
    passees = []
    for route in reservees:
        c, b = appel(lambda_, route, {})
        if c != 403:
            passees.append("%s -> %s" % (route, c))
    t("les %d routes reservees refusent un compte ordinaire" % len(reservees),
      not passees, passees[:5])

    print("   -- et l'interface sait quel role elle sert --")
    c, b = appel(lambda_, "/api/scan")
    moi = js(b).get("moi") or {}
    t("/api/scan annonce le role", bool(moi), moi)
    t("un compte ordinaire n'est pas administrateur", moi.get("admin") is False, moi)
    t("et il est bien reconnu comme connecte", moi.get("connecte") is True, moi)

    # And it keeps what belongs to ordinary use: without that, the reserve
    # would turn an ordinary account into a spectator.
    c, b = appel(lambda_, "/api/push-plan", {"paths": []})
    t("il peut toujours preparer un envoi", c == 200, (c, js(b)))

    print("   -- l'administrateur, lui, peut --")
    chefnav = navigateur()
    c, b = appel(chefnav, "/auth/connexion",
                 {"email": "chef@exemple.fr", "mdp": "un mot de passe long"},
                 forme=True)
    t("connexion de l'administrateur", c == 200, (c, js(b)))
    c, b = appel(chefnav, "/api/compte-supprimer", {"id": simple.get("id")})
    t("il supprime un autre compte", c == 200, (c, js(b)))
    c, b = appel(chefnav, "/api/journal-clear", {})
    t("il efface le journal", c == 200, (c, js(b)))
    c, b = appel(chefnav, "/api/acces", {})
    t("il lit le journal des acces", c == 200, (c, js(b)))
    c, b = appel(chefnav, "/api/config", {"auth_mode": "aucun"})
    t("il modifie les reglages", c == 200, (c, js(b)))
    c, b = appel(chefnav, "/api/scan")
    t("et l'interface le sait administrateur",
      (js(b).get("moi") or {}).get("admin") is True, js(b).get("moi"))

    # Authentication switched off: there is no identity left to tell apart, and
    # the reserve must not turn the most common mode into a dead end.
    c, b = appel(chefnav, "/api/journal-clear", {})
    t("sans authentification, la reserve ne bloque plus", c == 200, (c, js(b)))
finally:
    srv.terminate()
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
