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
import tempfile
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
                "romule.tests.test_profils",
                "romule.tests.test_reseau",
                "romule.tests.test_apikeys",
                "romule.tests.test_reglages",
                "romule.tests.test_rapprochement",
                "romule.tests.test_maj"):
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
              "test_autorisation.py", "test_limites.py", "test_premier_acces.py", "test_oidc_negatif.py", "test_intrusion.py", "test_ludotheque.py", "test_compression.py", "test_igdb.py",
              "test_apiv1.py"):
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


# Les tests navigateur tournaient sur la ludotheque REELLE du poste et sur
# l'adb REEL de la machine. Leur resultat dependait donc de ce qui etait branche
# et de ce que l'auteur possedait — trois verdicts differents pour le meme code.
# C'est ce qui a cache cinq chaines francaises sur l'ecran d'accueil.
#
# On leur donne desormais un decor fixe : une racine jetable, quelques jeux
# fabriques, une configuration deja ecrite (sinon l'assistant de premier
# demarrage recouvre tout l'ecran et rien n'est cliquable), et un faux adb dans
# l'etat choisi.
FAUX_ADB = TESTS / "navigateur" / ".." / "faux_adb.py"

TITRES_TEST = [
    ("Aurora Drift",   "0100aa0000010000"),
    ("Cinder Vale",    "0100bb0000020000"),
    ("Harbour Lights", "0100cc0000030000"),
]


def _semer(racine):
    """Une petite ludotheque previsible : sans jeu, la moitie des ecrans est vide."""
    import json
    jeux = Path(racine) / "GAMES"
    jeux.mkdir(parents=True, exist_ok=True)
    covers = Path(racine) / "_covers"
    covers.mkdir(exist_ok=True)
    for nom, tid in TITRES_TEST:
        (jeux / ("%s [%s][v0].nsp" % (nom, tid))).write_bytes(b"\0" * 4096)
        (covers / ("%s.en.json" % tid)).write_text(json.dumps({
            "name": nom, "publisher": "Romule", "releaseDate": "20240101",
            "intro": "A test entry, not a real game."}), encoding="utf-8")
    # Une SECONDE plateforme, peuplee. Sans elle, tout le decor est en Switch
    # et la bascule d'une plateforme a l'autre n'a rien a montrer : un test qui
    # mesure le passage d'une liste a une autre restait vert meme sur du code
    # qui vidait la grille, faute de seconde liste. Cinq fichiers suffisent.
    gba = Path(racine) / "GBA"
    gba.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (gba / ("Un jeu portable %02d.gba" % i)).write_bytes(b"\0" * 2048)

    # Une configuration presente = `first_run` faux = pas d'assistant par-dessus.
    (Path(racine) / "_romule-config.json").write_text(
        json.dumps({"ui_lang": "fr", "auth_mode": "aucun"}), encoding="utf-8")


def _demarrer_serveur(etat=None):
    """Serveur de test sur un decor fixe. `etat` est celui du faux adb.

    Par defaut : celui de l'environnement, donc « aucune » — l'etat de tout
    nouvel utilisateur, et celui dont la branche d'affichage n'etait jamais
    exercee. Le laisser lire l'environnement permet de rejouer la suite
    entiere dans les trois etats et de verifier qu'elle rend le meme verdict.
    """
    etat = etat or os.environ.get("ROMULE_FAUX_ADB", "aucune")
    racine = tempfile.mkdtemp(prefix="ludo-navigateur-")
    _semer(racine)
    proc = subprocess.Popen(
        [sys.executable, "-m", "romule", "serve"], cwd=str(RACINE),
        env=dict(os.environ, ROMULE_ROOT=racine,
                 ROMULE_WEB_PORT=str(PORT_NAV), ROMULE_NO_BROWSER="1",
                 ROMULE_ADB=str(FAUX_ADB.resolve()), ROMULE_FAUX_ADB=etat),
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
    """Suites qui pilotent un vrai Chrome.

    La garde cherchait `/Applications/Google Chrome.app` — un chemin macOS.
    Sur un runner Linux il n'existe pas, la famille se sautait donc, et le job
    rendait 0. Resultat : les six suites navigateur n'ont JAMAIS tourne en
    integration continue, y compris l'invariant anti-injection. Un test qui ne
    s'execute nulle part est pire qu'absent : il donne une assurance.

    `cdp.trouver_chrome()` sait deja chercher sur les trois systemes et
    respecte ROMULE_CHROME. On lui demande, plutot que de deviner.

    Et surtout : quand ROMULE_CHROME est pose — donc quand quelqu'un a installe
    Chrome EXPRES pour ces tests — ne pas trouver Chrome est un ECHEC, pas une
    permission de passer son chemin. C'est ce qui empeche le silence de
    revenir.
    """
    titre("navigateur (Chrome sans tete)")
    sys.path.insert(0, str(TESTS / "navigateur"))
    try:
        from cdp import trouver_chrome
        trouver_chrome()
    except Exception as exc:
        if os.environ.get("ROMULE_CHROME", "").strip():
            print("   ECHEC : ROMULE_CHROME est pose mais Chrome est inutilisable")
            print("   %s" % exc)
            return False
        print("   Chrome introuvable : famille ignoree")
        print("   (pose ROMULE_CHROME pour en faire un echec)")
        return None
    proc, url = _demarrer_serveur()
    os.environ["LUDO_URL"] = url
    try:
        ok = True
        for f in ("audit_responsive.py", "test_parcours_mobile.py",
                  "test_traduction.py", "test_gestes.py",
                  "test_bibliotheque.py"):
            ok = script(TESTS / "navigateur" / f) and ok
        for f in ("test_ui_comptes.js", "test_ui_temoin.js", "test_ui_injection.js"):
            r = script_node(TESTS / "navigateur" / f)
            ok = (r is not False) and ok
        return ok
    finally:
        proc.terminate()


def main(argv):
    # L'adb de la machine est neutralise pour TOUTE la suite, pas seulement pour
    # les tests navigateur : chaque test lance un serveur qui herite de
    # l'environnement, et un appareil branche changeait donc silencieusement le
    # decor. `setdefault` laisse la main : poser ROMULE_ADB soi-meme permet de
    # rejouer contre un vrai appareil quand c'est ce qu'on veut.
    os.environ.setdefault("ROMULE_ADB", str(FAUX_ADB.resolve()))
    os.environ.setdefault("ROMULE_FAUX_ADB", "aucune")

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
