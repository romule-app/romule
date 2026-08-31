#!/usr/bin/env python3
"""Lance toute la batterie de tests de la ludotheque.

    python3 lancer_tests.py                 # tout ce qui ne demande pas de navigateur
    python3 lancer_tests.py --navigateur    # ajoute les tests dans un vrai Chrome
    python3 lancer_tests.py --tout

Trois familles :

  * **unitaires** — title IDs, couche adb : rapides, sans reseau ;
  * **serveur**   — authentification interne et SSO, joues de bout en bout
    contre un serveur reel demarre sur une racine JETABLE. La ludotheque de
    l'utilisateur n'est jamais touchee ;
  * **navigateur** — Chrome sans tete pilote en CDP. C'est la seule famille
    capable de voir qu'un bouton ne repond plus : une politique de securite
    trop stricte a deja rendu toute l'interface inerte sans qu'aucun test
    hors navigateur ne s'en apercoive.

Aucune dependance : ni pytest, ni selenium, ni playwright.
"""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent
TESTS = RACINE / "romule" / "tests"
PORT_NAV = int(os.environ.get("LUDO_PORT_TESTS", "8798"))

VERT, ROUGE, GRIS, RAZ = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


def titre(t):
    # Les sous-processus ecrivent directement sur la sortie : sans vidage, les
    # titres arrivent apres leur propre contenu et le rapport devient illisible.
    print("\n%s== %s %s%s" % (GRIS, t, "=" * max(0, 58 - len(t)), RAZ), flush=True)


def unitaires():
    """Tests unitaires deja presents dans romule/tests/.

    Ce sont de simples fonctions `test_*` executees par le module lui-meme,
    pas des `unittest.TestCase` : la decouverte automatique de `unittest` ne
    les voit pas. On les lance donc comme ils sont concus pour l'etre.
    """
    titre("unitaires")
    ok = True
    for mod in ("romule.tests.test_titleid", "romule.tests.test_device",
                "romule.tests.test_import_roms",
                "romule.tests.test_totp_unite",
                "romule.tests.test_profils"):
        r = subprocess.run([sys.executable, "-m", mod], cwd=str(RACINE))
        print("   %-34s %s" % (mod, "OK" if r.returncode == 0 else "ECHEC"), flush=True)
        ok = (r.returncode == 0) and ok
    return ok


def script(chemin, args=()):
    """Un test autonome : son code de sortie fait foi."""
    r = subprocess.run([sys.executable, str(chemin), *args], cwd=str(RACINE))
    return r.returncode == 0


def script_node(chemin):
    if not _node_present():
        print("   node absent : test ignore (%s)" % Path(chemin).name)
        return None
    r = subprocess.run(["node", str(chemin)], cwd=str(RACINE))
    return r.returncode == 0


def _node_present():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def serveur():
    titre("serveur : authentification et sources externes")
    ok = True
    for f in ("test_auth_interne.py", "test_oidc_sso.py", "test_totp.py",
              "test_verrouillage.py", "test_proxy.py",
              "test_autorisation.py", "test_limites.py", "test_premier_acces.py", "test_igdb.py"):
        ok = script(TESTS / f) and ok
    return ok


def syntaxe():
    titre("syntaxe")
    ok = subprocess.run([sys.executable, "-m", "compileall", "-q",
                         "romule"], cwd=str(RACINE)).returncode == 0
    print("   Python : %s" % ("OK" if ok else "ECHEC"))
    if _node_present():
        for f in ("app.js", "reactive.js"):
            r = subprocess.run(["node", "--check", "romule/static/" + f],
                               cwd=str(RACINE))
            ok = (r.returncode == 0) and ok
        print("   JavaScript : %s" % ("OK" if ok else "ECHEC"))
    return ok


def audit_securite():
    titre("audit de securite")
    r = subprocess.run([sys.executable, "-m", "romule.audit", "--hors-ligne"],
                       cwd=str(RACINE), capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(vide)")
    # 2 = probleme grave. On ne fait pas echouer la batterie sur un choix
    # d'installation (reseau ouvert), mais on l'affiche.
    return r.returncode != 2 or "ouverte au reseau" in r.stdout


def _demarrer_serveur():
    """Serveur de test, sur la ludotheque reelle : les tests navigateur ne font
    que LIRE l'interface. Rien n'est ecrit."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "romule", "serve"], cwd=str(RACINE),
        env=dict(os.environ, ROMULE_WEB_PORT=str(PORT_NAV),
                 ROMULE_NO_BROWSER="1"),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "http://127.0.0.1:%d/" % PORT_NAV
    for _ in range(90):
        try:
            urllib.request.urlopen(url, timeout=2)
            return proc, url
        except urllib.error.HTTPError:
            return proc, url
        except Exception:
            time.sleep(1)
    proc.kill()
    raise RuntimeError("le serveur de test n'a pas demarre")


def navigateur():
    titre("navigateur (Chrome sans tete)")
    if not Path("/Applications/Google Chrome.app").exists():
        print("   Chrome introuvable : famille ignoree")
        return None
    proc, url = _demarrer_serveur()
    os.environ["LUDO_URL"] = url
    try:
        ok = True
        for f in ("audit_responsive.py", "test_parcours_mobile.py",
                  "test_traduction.py"):
            ok = script(TESTS / "navigateur" / f) and ok
        for f in ("test_ui_comptes.js", "test_ui_temoin.js"):
            r = script_node(TESTS / "navigateur" / f)
            ok = (r is not False) and ok
        return ok
    finally:
        proc.terminate()


def main(argv):
    avec_nav = "--navigateur" in argv or "--tout" in argv
    resultats = [("syntaxe", syntaxe()),
                 ("unitaires", unitaires()),
                 ("serveur", serveur()),
                 ("audit", audit_securite())]
    if avec_nav:
        resultats.append(("navigateur", navigateur()))
    else:
        print("\n%s(tests navigateur non lances : --navigateur pour les inclure)%s"
              % (GRIS, RAZ))

    titre("resume")
    dur = 0
    for nom, ok in resultats:
        if ok is None:
            print("   %-12s ignore" % nom)
            continue
        print("   %-12s %s" % (nom, (VERT + "OK" + RAZ) if ok else (ROUGE + "ECHEC" + RAZ)))
        dur += 0 if ok else 1
    print()
    return 1 if dur else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
