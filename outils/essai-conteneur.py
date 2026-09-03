#!/usr/bin/env python3
"""A full-scale trial: Romule in a container, from the build to the API.

Why a TOOL and not a terminal session
-------------------------------------
A trial you cannot repeat proves nothing the second time. This one is
replayable, it says what it checks, and it cleans up after itself.

What it covers, and that the test suites do NOT:

  * the image builds and starts — the suites run against `python3 -m romule`,
    never against the shipped container;
  * the health probe reaches *healthy*. It was broken for months: it queried a
    route declared POST-only, so the container could never be declared healthy;
  * the access token appears in the logs and survives a restart;
  * the API answers FROM OUTSIDE the container, with a key created through
    `docker compose exec` — the real journey of someone plugging in a dashboard;
  * a revoked key is refused, and a valid key does not reach `/api/comptes`.
    That is the scope promise, checked on the real routing.

By default the trial builds the image FROM SOURCE. `--image` pulls it from the
registry instead: that is not the same question. Building proves the
`Dockerfile` holds; pulling proves that what was PUBLISHED starts — two things
that part company as soon as a publishing step exists.

Usage:
    python3 outils/essai-conteneur.py            # builds, tries, cleans up
    python3 outils/essai-conteneur.py --garder   # leaves the stack standing
    python3 outils/essai-conteneur.py --image    # pulls ghcr.io/...:latest
    python3 outils/essai-conteneur.py --image ghcr.io/romule-app/romule:0.2.0
"""

import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8787"
PUBLIEE = "ghcr.io/romule-app/romule:latest"
EPINGLE = RACINE / "outils" / "compose.image.yaml"

# Renseigne par `--image` : la reference a tirer au lieu de construire.
IMAGE = None

ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("   ok    %s" % nom)
    else:
        ko += 1
        print("   ECHEC %s   %s" % (nom, detail))
    return bool(cond)


def titre(x):
    print("\n\033[90m-- %s %s\033[0m" % (x, "-" * max(0, 58 - len(x))))


def dc(*args, **kw):
    """`docker compose` in the project's folder, with the trial overlay.

    `docker-compose.yml` deliberately lets the user point at their games folder
    from the interface. A fresh container therefore has an EMPTY library, which
    is correct and leaves an automatic trial blind: the overlay pins
    `ROMULE_LIBRARY`, with the variable `docker-compose.yml` already documents.
    """
    fichiers = ["-f", "docker-compose.yml", "-f", "outils/compose.essai.yaml"]
    if IMAGE:
        fichiers += ["-f", str(EPINGLE.relative_to(RACINE))]
    return subprocess.run(
        ["docker", "compose"] + fichiers + list(args),
        cwd=str(RACINE), capture_output=True, text=True, **kw)


def http(chemin, entetes=None, methode="GET", timeout=15):
    req = urllib.request.Request(BASE + chemin, headers=entetes or {},
                                 method=methode)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            corps = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(corps)
            except ValueError:
                return r.status, corps
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:
        return 0, str(e)


def preparer():
    """The two folders the compose file mounts, and something to scan.

    The trial library is SYNTHETIC: empty files with plausible names. No real
    game enters here, and the trial must be able to run on anyone's machine.
    """
    jeux = RACINE / "library" / "GAMES"
    jeux.mkdir(parents=True, exist_ok=True)
    (RACINE / "keys").mkdir(exist_ok=True)
    for i in range(5):
        f = jeux / ("Essai numero %02d [0100%012x][v0].nsp" % (i, i))
        if not f.exists():
            f.write_bytes(b"\0" * 1024)
    return jeux


def attendre_sain(limite=180):
    """The container's probe, not ours: it is the one that must pass."""
    debut = time.time()
    dernier = ""
    while time.time() - debut < limite:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", "romule"],
            capture_output=True, text=True)
        dernier = (r.stdout or r.stderr).strip()
        if dernier == "healthy":
            return True, int(time.time() - debut)
        if dernier == "unhealthy":
            return False, int(time.time() - debut)
        time.sleep(3)
    return False, int(time.time() - debut), dernier


def jeton_des_journaux():
    """Romule generates a token on the first start and prints it with the URL.
    If it cannot be found here, nobody can get in."""
    sortie = dc("logs", "romule").stdout or ""
    m = re.search(r"token=([A-Za-z0-9_\-]{16,})", sortie)
    return m.group(1) if m else None


def main(argv):
    global IMAGE
    garder = "--garder" in argv

    if "--image" in argv:
        i = argv.index("--image")
        suite = argv[i + 1] if len(argv) > i + 1 else ""
        IMAGE = suite if suite and not suite.startswith("--") else PUBLIEE
        # `image:` replaces `build:` in the overlay. Written here rather than
        # shipped as a frozen file: the reference changes with every version, and
        # a file holding it would be stale from the next release on.
        EPINGLE.write_text("services:\n  romule:\n    image: %s\n" % IMAGE,
                           encoding="utf-8")

    if not shutil.which("docker"):
        print("docker introuvable — cet essai a besoin d'un moteur de conteneurs.")
        return 2

    titre("preparation")
    jeux = preparer()
    print("   bibliotheque d'essai : %s (%d fichiers)"
          % (jeux, len(list(jeux.glob("*.nsp")))))
    dc("down", "-v")                       # start from a clean slate

    if IMAGE:
        titre("tirage de l'image publiee")
        print("   %s" % IMAGE)
        r = dc("pull", "romule")
        # A refused pull is the failure we came to check: it deserves a check
        # of its own, rather than being drowned in `up`'s failure.
        if not t("l'image se tire SANS authentification", r.returncode == 0,
                 (r.stderr or "")[-300:]):
            return 1

    titre("construction et demarrage" if not IMAGE else "demarrage")
    debut = time.time()
    r = dc("up", "-d", "--no-build") if IMAGE else dc("up", "-d", "--build")
    if not t("`docker compose up` reussit", r.returncode == 0,
             (r.stderr or "")[-400:]):
        return 1
    print("   %d s" % int(time.time() - debut))

    titre("sonde de sante")
    etat = attendre_sain()
    t("le conteneur devient *healthy*", etat[0],
      "etat=%s apres %ss" % (etat[2] if len(etat) > 2 else "?", etat[1]))
    print("   %d s pour devenir sain" % etat[1])

    titre("acces")
    jeton = jeton_des_journaux()
    t("le jeton d'acces est affiche dans les journaux", bool(jeton),
      "aucun `token=` dans `docker compose logs`")
    # FROM THE HOST, the request does not come from 127.0.0.1 but from the
    # Docker bridge: it is therefore NOT local, and the token is required. That
    # is precisely what we want to check — a container published on the network
    # that answered without a token would be the defect, not the reverse.
    code, _ = http("/api/health")
    t("sans jeton, l'hote est refuse", code in (401, 403), code)
    q = "?token=" + (jeton or "")
    code, sante = http("/api/health" + q)
    t("avec le jeton, /api/health repond", code == 200, code)
    if isinstance(sante, dict):
        print("   version %s, premier lancement : %s"
              % (sante.get("version"), sante.get("first_run")))
    code, _ = http("/" + q)
    t("avec le jeton, l'interface est servie", code == 200, code)

    titre("cle d'API creee depuis le conteneur")
    # This is the real journey: there is no browser inside a container.
    r = dc("exec", "-T", "romule", "python3", "-m", "romule", "apikey",
           "create", "essai-conteneur")
    m = re.search(r"(rml_[A-Za-z0-9_\-]+)", r.stdout or "")
    cle = m.group(1) if m else None
    if not t("`apikey create` rend une cle", bool(cle),
             (r.stdout or r.stderr)[-300:]):
        return 1
    entete = {"X-Api-Key": cle}

    titre("l'API repond depuis l'exterieur du conteneur")
    routes = ["health", "system", "stats", "library", "platforms", "device",
              "job", "trash", "openapi.json", "search?q=essai"]
    for nom in routes:
        code, _ = http("/api/v1/" + nom, entete)
        t("/api/v1/%s" % nom, code == 200, code)
    code, lib = http("/api/v1/library", entete)
    t("la bibliotheque montee est vue", isinstance(lib, dict) and lib.get("total") == 5,
      lib.get("total") if isinstance(lib, dict) else lib)
    code, st = http("/api/v1/stats", entete)
    t("les statistiques comptent les memes fichiers",
      isinstance(st, dict) and st.get("total") == 5, st)

    titre("la portee de la cle")
    for chemin in ("/api/comptes", "/api/config", "/api/scan", "/"):
        code, _ = http(chemin, entete)
        t("cle refusee sur %s" % chemin, code in (401, 403), code)
    code, _ = http("/api/v1/system", {"X-Api-Key": "rml_inventee"})
    t("une cle inventee est refusee", code in (401, 403), code)

    titre("une tache se lance par l'API")
    code, rep = http("/api/v1/scan", entete, methode="POST")
    t("POST /api/v1/scan est accepte", code in (202, 409), "%s %s" % (code, rep))

    titre("redemarrage : l'etat survit")
    dc("restart", "romule")
    etat = attendre_sain()
    t("le conteneur redevient sain", etat[0], etat[1])
    code, _ = http("/api/v1/system", entete)
    t("la cle fonctionne encore apres redemarrage", code == 200, code)
    t("le jeton n'a pas change", jeton_des_journaux() == jeton)

    titre("revocation")
    r = dc("exec", "-T", "romule", "python3", "-m", "romule", "apikey", "list")
    m = re.search(r"^([0-9a-f]{16})\s", r.stdout or "", re.M)
    cid = m.group(1) if m else None
    if t("`apikey list` montre la cle", bool(cid), (r.stdout or "")[-200:]):
        dc("exec", "-T", "romule", "python3", "-m", "romule", "apikey",
           "revoke", cid)
        code, _ = http("/api/v1/system", entete)
        t("la cle revoquee est refusee aussitot", code in (401, 403), code)

    titre("audit dans le conteneur")
    r = dc("exec", "-T", "romule", "python3", "-m", "romule.audit")
    sortie = r.stdout or ""
    m = re.search(r"(\d+) grave", sortie)
    t("l'audit ne signale aucun probleme grave",
      bool(m) and m.group(1) == "0", sortie.strip().splitlines()[-1:] or r.stderr[-200:])
    print("   %s" % (sortie.strip().splitlines() or ["(rien)"])[-1])

    if garder:
        print("\n   pile laissee debout : %s" % BASE)
        print("   `docker compose down -v` pour l'arreter.")
    else:
        titre("nettoyage")
        dc("down", "-v")
        shutil.rmtree(RACINE / "library", ignore_errors=True)
        cles = RACINE / "keys"
        # We only remove `keys/` if it is empty: someone may have dropped their
        # own `prod.keys` in there before starting the trial.
        if cles.is_dir() and not any(cles.iterdir()):
            cles.rmdir()
        print("   pile arretee, volumes et bibliotheque d'essai supprimes")

    print("\n   %d controles OK, %d echec(s)" % (ok, ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
