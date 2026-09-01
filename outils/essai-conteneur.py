#!/usr/bin/env python3
"""Essai grandeur nature : Romule dans un conteneur, du build a l'API.

Pourquoi un OUTIL et pas une session de terminal
------------------------------------------------
Un essai qu'on ne peut pas refaire ne prouve rien la deuxieme fois. Celui-ci
est rejouable, il dit ce qu'il verifie, et il nettoie derriere lui.

Ce qu'il couvre, et que les suites de tests ne couvrent PAS :

  * l'image se construit et demarre — les suites tournent contre `python3 -m
    romule`, jamais contre le conteneur livre ;
  * la sonde de sante passe a *healthy*. Elle a deja ete cassee pendant des
    mois : elle interrogeait une route declaree en POST seulement, et le
    conteneur ne pouvait donc jamais etre declare sain ;
  * le jeton d'acces apparait dans les journaux et survit a un redemarrage ;
  * l'API repond DEPUIS L'EXTERIEUR du conteneur, avec une cle creee par
    `docker compose exec` — c'est le parcours reel de quelqu'un qui branche un
    tableau de bord ;
  * une cle revoquee est refusee, et une cle valide n'atteint pas `/api/comptes`.
    C'est la promesse de portee, verifiee sur le vrai routage.

L'essai construit l'image DEPUIS LES SOURCES. Verifier l'image publiee sur
ghcr.io est une question distincte : elle demande de pouvoir la tirer, donc un
depot public ou une authentification.

Usage :
    python3 outils/essai-conteneur.py            # construit, essaie, nettoie
    python3 outils/essai-conteneur.py --garder   # laisse la pile debout
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
    """`docker compose` dans le dossier du projet, avec la surcouche d'essai.

    `docker-compose.yml` laisse a dessein l'utilisateur designer son dossier de jeux
    depuis l'interface. Un conteneur neuf a donc une bibliotheque VIDE, ce qui
    est correct et rend un essai automatique aveugle : la surcouche fige
    `ROMULE_LIBRARY`, avec la variable que `docker-compose.yml` documente deja.
    """
    return subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml",
         "-f", "outils/compose.essai.yaml"] + list(args),
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
    """Les deux dossiers que le fichier compose monte, et de quoi scanner.

    La bibliotheque d'essai est SYNTHETIQUE : des fichiers vides aux noms
    plausibles. Aucun jeu reel n'entre ici, et l'essai doit pouvoir tourner sur
    la machine de n'importe qui.
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
    """La sonde du conteneur, pas la notre : c'est elle qui doit passer."""
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
    """Romule engendre un jeton au premier demarrage et l'affiche avec l'URL.
    Si on ne le retrouve pas ici, personne ne peut entrer."""
    sortie = dc("logs", "romule").stdout or ""
    m = re.search(r"token=([A-Za-z0-9_\-]{16,})", sortie)
    return m.group(1) if m else None


def main(argv):
    garder = "--garder" in argv

    if not shutil.which("docker"):
        print("docker introuvable — cet essai a besoin d'un moteur de conteneurs.")
        return 2

    titre("preparation")
    jeux = preparer()
    print("   bibliotheque d'essai : %s (%d fichiers)"
          % (jeux, len(list(jeux.glob("*.nsp")))))
    dc("down", "-v")                       # repartir d'une ardoise propre

    titre("construction et demarrage")
    debut = time.time()
    r = dc("up", "-d", "--build")
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
    # DEPUIS L'HOTE, la requete ne vient pas de 127.0.0.1 mais du pont Docker :
    # elle n'est donc PAS locale, et le jeton est exige. C'est precisement ce
    # qu'on veut verifier — un conteneur publie sur le reseau qui repondrait
    # sans jeton serait le defaut, pas l'inverse.
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
    # C'est le parcours reel : pas de navigateur dans un conteneur.
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
        # On ne retire `keys/` que s'il est vide : quelqu'un peut y avoir
        # depose son propre `prod.keys` avant de lancer l'essai.
        if cles.is_dir() and not any(cles.iterdir()):
            cles.rmdir()
        print("   pile arretee, volumes et bibliotheque d'essai supprimes")

    print("\n   %d controles OK, %d echec(s)" % (ok, ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
