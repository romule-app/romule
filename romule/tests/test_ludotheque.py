"""The games folder is chosen from the interface, not in a compose file.

`ROOT` mixed two things: the service's workspace (configuration, accounts, logs,
covers) and the library (the games). Separating them makes it possible to point
at the second from the settings screen without touching the first — so without
losing your accounts when you change disk.

What is checked here:
  * the default does not move: with no setting, the library IS the root;
  * the folder browser returns only folders, and counts the games;
  * changing library changes the inventory, and nothing else;
  * the trash and the drop folder follow the GAMES, not the configuration;
  * the choice survives a restart;
  * it is reserved to the administrator;
  * `ROMULE_LIBRARY` and `ROMULE_BASES` are honoured.
"""
import http.cookiejar, json, os, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)


def libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return str(s.getsockname()[1])


def navigateur():
    pot = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(pot))


def appel(base, op, chemin, corps=None, entetes=None, forme=False):
    e = {"Origin": base}
    e.update(entetes or {})
    d = None
    if corps is not None and forme:
        d = urllib.parse.urlencode(corps).encode()
        e["Content-Type"] = "application/x-www-form-urlencoded"
    elif corps is not None:
        d = json.dumps(corps).encode(); e["Content-Type"] = "application/json"
    try:
        with op.open(urllib.request.Request(base + chemin, data=d, headers=e),
                     timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as x:
        return x.code, x.read()


def js(b):
    try: return json.loads(b or b"{}")
    except Exception: return {}


def demarrer(racine, extra=None):
    """Starts a server and waits for it to answer. Returns (process, base)."""
    port = libre()
    base = "http://127.0.0.1:" + port
    env = dict(os.environ, ROMULE_ROOT=racine, ROMULE_WEB_PORT=port,
               ROMULE_NO_BROWSER="1")
    env.update(extra or {})
    p = subprocess.Popen([sys.executable, "-m", "romule", "serve"],
                         cwd=RACINE_PROJET, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    op = navigateur()
    for _ in range(60):
        try:
            appel(base, op, "/api/job"); break
        except Exception:
            time.sleep(0.5)
    return p, base, op


def jeu(dossier, nom, tid):
    """A file that looks like a game. The scan reads the NAME, not the content."""
    dossier.mkdir(parents=True, exist_ok=True)
    f = dossier / ("%s [%s][v0].nsp" % (nom, tid))
    f.write_bytes(b"\0" * 32)
    return f


ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c: ok += 1; print("      OK   %s" % n)
    else: fail += 1; print("      ECHEC %s  %s" % (n, d))


def temporaire(prefixe):
    """A temporary folder, with its REAL path.

    On macOS, /var is a link to /private/var: `mkdtemp` returns the short form,
    the server resolves the long one, and any path comparison fails for a reason
    that has nothing to do with what is being tested.
    """
    return str(Path(tempfile.mkdtemp(prefix=prefixe)).resolve())


# Three distinct locations, so that nothing can be confused.
DONNEES = temporaire("ludo-donnees-")
JEUX = temporaire("ludo-jeux-")
VIDE = temporaire("ludo-vide-")

# One game in the service's root, three in the other folder: the two inventories
# must be visibly different.
jeu(Path(DONNEES) / "GAMES", "Jeu Racine", "0100000000001000")
for i, nom in enumerate(("Alpha", "Beta", "Gamma")):
    jeu(Path(JEUX) / "GAMES", nom, "010000000000%d000" % (2 + i))

srv, BASE, nav = demarrer(DONNEES)
try:
    print("   -- par defaut, la ludotheque est la racine du service --")
    sante = js(appel(BASE, nav, "/api/health")[1])
    t("ludotheque annoncee", sante.get("ludotheque") == DONNEES, sante.get("ludotheque"))
    t("non imposee", sante.get("ludotheque_imposee") is False, sante.get("ludotheque_imposee"))
    inv = js(appel(BASE, nav, "/api/scan")[1])
    t("un seul jeu au depart", len(inv.get("files", [])) == 1, len(inv.get("files", [])))

    print("   -- le navigateur de dossiers --")
    c, b = appel(BASE, nav, "/api/parcourir", {"chemin": JEUX})
    r = js(b)
    t("il repond", c == 200, (c, r))
    t("il voit le sous-dossier", "GAMES" in [d["nom"] for d in r.get("dossiers", [])],
      r.get("dossiers"))
    t("il compte les jeux", r.get("jeux") == 3, r.get("jeux"))
    t("il dit si c'est ecrivable", r.get("ecrivable") is True, r.get("ecrivable"))
    t("il propose un parent", bool(r.get("parent")), r.get("parent"))
    t("il propose des raccourcis", len(r.get("raccourcis", [])) >= 2, r.get("raccourcis"))
    # What must NOT come out: file names.
    t("il ne rend aucun fichier",
      all(not d["nom"].endswith(".nsp") for d in r.get("dossiers", [])),
      r.get("dossiers"))
    c, b = appel(BASE, nav, "/api/parcourir", {"chemin": JEUX + "/introuvable"})
    t("un chemin inexistant est refuse", bool(js(b).get("error")), (c, js(b)))

    print("   -- changer de ludotheque --")
    c, b = appel(BASE, nav, "/api/ludotheque", {"chemin": "pas/absolu"})
    t("un chemin relatif est refuse", c == 400, (c, js(b)))
    c, b = appel(BASE, nav, "/api/ludotheque", {"chemin": str(Path.home())})
    t("le dossier personnel est refuse", c == 400, (c, js(b)))
    c, b = appel(BASE, nav, "/api/ludotheque", {"chemin": JEUX + "/absent"})
    t("un dossier absent est refuse", c == 400, (c, js(b)))

    c, b = appel(BASE, nav, "/api/ludotheque", {"chemin": JEUX})
    r = js(b)
    t("le changement est accepte", c == 200, (c, r))
    t("l'inventaire suit aussitot", len(r.get("files", [])) == 3, len(r.get("files", [])))
    sante = js(appel(BASE, nav, "/api/health")[1])
    t("la sante annonce la nouvelle", sante.get("ludotheque") == JEUX, sante.get("ludotheque"))
    t("la racine du service n'a pas bouge", sante.get("root") == DONNEES, sante.get("root"))

    print("   -- la configuration reste ou elle etait --")
    t("le fichier de configuration est dans les donnees",
      (Path(DONNEES) / "_romule-config.json").exists(),
      sorted(p.name for p in Path(DONNEES).iterdir()))
    t("rien n'a ete ecrit dans les jeux",
      not (Path(JEUX) / "_romule-config.json").exists(),
      sorted(p.name for p in Path(JEUX).iterdir()))

    print("   -- la corbeille suit les jeux, pas la configuration --")
    # A trash kept beside the configuration would often be on another disk:
    # setting a game aside would stop being a rename and become a copy of
    # several gigabytes.
    cible = str(Path(JEUX) / "GAMES" / "Alpha [0100000000002000][v0].nsp")
    c, b = appel(BASE, nav, "/api/trash", {"paths": [cible]})
    t("l'ecart repond", c == 200, (c, js(b)))
    t("la corbeille est dans les jeux", (Path(JEUX) / "_corbeille").is_dir(),
      sorted(p.name for p in Path(JEUX).iterdir()))
    t("et pas dans les donnees", not (Path(DONNEES) / "_corbeille").is_dir(), "")

    print("   -- creation d'un dossier a la demande --")
    neuf = str(Path(VIDE) / "ma-ludotheque")
    c, b = appel(BASE, nav, "/api/ludotheque", {"chemin": neuf})
    t("sans le drapeau, on refuse", c == 400, (c, js(b)))
    c, b = appel(BASE, nav, "/api/ludotheque", {"chemin": neuf, "creer": True})
    t("avec le drapeau, on cree", c == 200 and Path(neuf).is_dir(), (c, js(b)))

    print("   -- le choix survit au redemarrage --")
    appel(BASE, nav, "/api/ludotheque", {"chemin": JEUX})
finally:
    srv.terminate(); srv.wait(timeout=10)

srv, BASE, nav = demarrer(DONNEES)
try:
    sante = js(appel(BASE, nav, "/api/health")[1])
    t("la ludotheque est retrouvee", sante.get("ludotheque") == JEUX, sante.get("ludotheque"))

    print("   -- reserve a l'administrateur --")
    appel(BASE, nav, "/api/compte-creer",
          {"email": "chef@exemple.fr", "mdp": "un mot de passe long"})
    appel(BASE, nav, "/api/compte-creer",
          {"email": "simple@exemple.fr", "mdp": "encore un mot long"})
    appel(BASE, nav, "/api/config", {"auth_mode": "interne"})
    lam = navigateur()
    appel(BASE, lam, "/auth/connexion",
          {"email": "simple@exemple.fr", "mdp": "encore un mot long"}, forme=True)
    c, b = appel(BASE, lam, "/api/parcourir", {"chemin": JEUX})
    t("un compte ordinaire ne parcourt pas l'hote", c == 403, (c, js(b)))
    c, b = appel(BASE, lam, "/api/ludotheque", {"chemin": VIDE})
    t("ni ne deplace la ludotheque", c == 403, (c, js(b)))
    chef = navigateur()
    appel(BASE, chef, "/auth/connexion",
          {"email": "chef@exemple.fr", "mdp": "un mot de passe long"}, forme=True)
    c, b = appel(BASE, chef, "/api/parcourir", {"chemin": JEUX})
    t("l'administrateur, si", c == 200, (c, js(b)))
finally:
    srv.terminate(); srv.wait(timeout=10)

print("   -- ROMULE_LIBRARY impose et verrouille --")
IMPOSE = temporaire("ludo-impose-")
D2 = temporaire("ludo-donnees2-")
jeu(Path(IMPOSE) / "GAMES", "Impose", "0100000000009000")
srv, BASE, nav = demarrer(D2, {"ROMULE_LIBRARY": IMPOSE})
try:
    sante = js(appel(BASE, nav, "/api/health")[1])
    t("la variable gagne", sante.get("ludotheque") == IMPOSE, sante.get("ludotheque"))
    t("et le dit", sante.get("ludotheque_imposee") is True, sante.get("ludotheque_imposee"))
    c, b = appel(BASE, nav, "/api/ludotheque", {"chemin": JEUX})
    t("l'interface ne peut plus en changer", c == 400, (c, js(b)))
finally:
    srv.terminate(); srv.wait(timeout=10)

print("   -- ROMULE_BASES confine la navigation --")
D3 = temporaire("ludo-donnees3-")
srv, BASE, nav = demarrer(D3, {"ROMULE_BASES": JEUX})
try:
    c, b = appel(BASE, nav, "/api/parcourir", {"chemin": JEUX})
    t("dans la base, autorise", not js(b).get("error"), js(b))
    c, b = appel(BASE, nav, "/api/parcourir", {"chemin": "/etc"})
    t("hors base, refuse", bool(js(b).get("error")), js(b))
    c, b = appel(BASE, nav, "/api/parcourir", {"chemin": str(Path(JEUX).parent)})
    t("le parent de la base aussi", bool(js(b).get("error")), js(b))
    c, b = appel(BASE, nav, "/api/ludotheque", {"chemin": VIDE})
    t("et on ne peut pas s'y installer", c == 400, (c, js(b)))
    # The default library (the data folder) is here OUTSIDE the bases: opening
    # the dialog with no argument must still lead somewhere.
    c, b = appel(BASE, nav, "/api/parcourir", {})
    r = js(b)
    t("sans argument, on retombe sur la base", r.get("chemin") == JEUX, r)
finally:
    srv.terminate(); srv.wait(timeout=10)

print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
