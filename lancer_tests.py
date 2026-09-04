#!/usr/bin/env python3
"""Runs the library's whole test battery.

    python3 lancer_tests.py                 # everything that needs no browser
    python3 lancer_tests.py --navigateur    # adds the tests in a real Chrome
    python3 lancer_tests.py --tout

Three families:

  * **unitaires** — title IDs, the adb layer: fast, no network;
  * **serveur**   — internal and SSO authentication, played end to end against a
    real server started on a THROWAWAY root. The user's own library is never
    touched;
  * **navigateur** — headless Chrome driven over CDP. It is the only family able
    to see that a button has stopped answering: a security policy that was too
    strict once made the whole interface inert without any non-browser test
    noticing.

No dependency: no pytest, no selenium, no playwright.
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent
TESTS = RACINE / "romule" / "tests"
def _port_libre():
    """A port nobody occupies, asked of the system.

    The port used to be fixed at 8798. A server left over from an earlier run —
    or anything else on the machine — settled there, and the suite tested THAT
    service: the results became another version's, red or green with no relation
    to the code just written. It happened, and the diagnosis cost an hour.

    `LUDO_PORT_TESTS` is still accepted for whoever wants to fix the port by
    hand.
    """
    fixe = os.environ.get("LUDO_PORT_TESTS")
    if fixe:
        return int(fixe)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


PORT_NAV = _port_libre()

VERT, ROUGE, GRIS, RAZ = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


def titre(t):
    # The sub-processes write straight to the output: without a flush, the
    # headings arrive after their own content and the report becomes
    # unreadable.
    print("\n%s== %s %s%s" % (GRIS, t, "=" * max(0, 58 - len(t)), RAZ), flush=True)


def unitaires():
    """The unit tests already present in romule/tests/.

    These are plain `test_*` functions run by the module itself, not
    `unittest.TestCase`s: `unittest`'s automatic discovery does not see them. So
    we run them the way they are designed to be run.
    """
    titre("unitaires")
    ok = True
    for mod in ("romule.tests.test_titleid", "romule.tests.test_device",
                "romule.tests.test_import_roms",
                "romule.tests.test_totp_unite",
                "romule.tests.test_profils",
                "romule.tests.test_net",
                "romule.tests.test_apikeys",
                "romule.tests.test_reglages",
                "romule.tests.test_matching",
                "romule.tests.test_updates",
                "romule.tests.test_covers",
                "romule.tests.test_console",
                "romule.tests.test_cli_depannage",
                "romule.tests.test_cles_persistees"):
        r = subprocess.run([sys.executable, "-m", mod], cwd=str(RACINE))
        print("   %-34s %s" % (mod, "OK" if r.returncode == 0 else "ECHEC"), flush=True)
        ok = (r.returncode == 0) and ok
    return ok


def script(chemin, args=()):
    """A standalone test: its exit code is the authority."""
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
              "test_apiv1.py", "test_notifs.py"):
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
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(empty)")
    # 2 = a serious problem. We do not fail the battery over an installation
    # choice (an open network), but we do display it.
    return r.returncode != 2 or "ouverte au reseau" in r.stdout


# The browser tests used to run on the workstation's REAL library and on the
# machine's REAL adb. Their result therefore depended on what was plugged in and
# on what the author owned — three different verdicts for the same code. That is
# what hid five French strings on the home screen.
#
# They are now given a fixed fixture: a throwaway root, a few fabricated games, a
# configuration already written (otherwise the first-run wizard covers the whole
# screen and nothing is clickable), and a fake adb in the chosen state.
FAUX_ADB = TESTS / "navigateur" / ".." / "faux_adb.py"

TITRES_TEST = [
    ("Aurora Drift",   "0100aa0000010000"),
    ("Cinder Vale",    "0100bb0000020000"),
    ("Harbour Lights", "0100cc0000030000"),
]


def _semer(racine):
    """A small predictable library: with no game, half the screens are empty."""
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
    # A SECOND platform, populated. Without it the whole fixture is Switch and
    # switching from one platform to another has nothing to show: a test that
    # measures the move from one list to another stayed green even on code that
    # emptied the grid, for want of a second list. Five files are enough.
    gba = Path(racine) / "GBA"
    gba.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        (gba / ("Un jeu portable %02d.gba" % i)).write_bytes(b"\0" * 2048)

    # A configuration present = `first_run` false = no wizard on top.
    (Path(racine) / "_romule-config.json").write_text(
        json.dumps({"ui_lang": "fr", "auth_mode": "aucun"}), encoding="utf-8")


def _demarrer_serveur(etat=None):
    """A test server on a fixed fixture. `etat` is the fake adb's state.

    By default: the environment's, so "none" — every new user's state, and the
    one whose display branch was never exercised. Letting it read the environment
    makes it possible to replay the whole suite in all three states and check it
    returns the same verdict.
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
    """The suites that drive a real Chrome.

    The guard looked for `/Applications/Google Chrome.app` — a macOS path. On a
    Linux runner it does not exist, so the family skipped itself and the job
    returned 0. The result: the six browser suites NEVER ran in continuous
    integration, the anti-injection invariant included. A test that runs nowhere
    is worse than absent: it gives an assurance.

    `cdp.trouver_chrome()` already knows how to look on all three systems and
    honours ROMULE_CHROME. We ask it, rather than guess.

    And above all: when ROMULE_CHROME is set — so when someone installed Chrome
    ON PURPOSE for these tests — not finding Chrome is a FAILURE, not permission
    to walk on by. That is what stops the silence from coming back.
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


def coherence_doc():
    """The checks that tie the documentation to the code.

    They lived as YAML inside the workflows, so nowhere on a development machine:
    you found out about them after pushing. A check you cannot run before pushing
    is a check you merely endure.

    `verifier-rendu.py` is NOT here: it reads the built site, which requires
    MkDocs — a dependency this repository does not have. It stays in the
    documentation workflow, which already installs it.

    `verifier-anglais.py` is here rather than with the documentation checks: it
    reads the SOURCE, and the moment it stops being run is the moment the first
    French comment comes back.
    """
    titre("coherence de la documentation")
    ok = True
    for outil in ("verifier-reglages-doc.py", "verifier-chiffres.py",
                  "verifier-traduction.py", "verifier-anglais.py",
                  "verifier-imports.py"):
        r = subprocess.run([sys.executable, str(RACINE / "outils" / outil)],
                           cwd=str(RACINE), capture_output=True, text=True)
        etat = "OK" if r.returncode == 0 else "ECHEC"
        print("   %-28s %s" % (outil, etat), flush=True)
        if r.returncode != 0:
            print((r.stdout or "") + (r.stderr or ""), end="")
        ok = (r.returncode == 0) and ok
    return ok


def main(argv):
    # The machine's adb is neutralised for the WHOLE suite, not only for the
    # browser tests: every test starts a server that inherits the environment,
    # so a plugged-in device silently changed the fixture. `setdefault` leaves
    # the choice open: setting ROMULE_ADB yourself makes it possible to replay
    # against a real device when that is what you want.
    os.environ.setdefault("ROMULE_ADB", str(FAUX_ADB.resolve()))
    os.environ.setdefault("ROMULE_FAUX_ADB", "aucune")

    avec_nav = "--navigateur" in argv or "--tout" in argv
    resultats = [("syntaxe", syntaxe()),
                 ("unitaires", unitaires()),
                 ("serveur", serveur()),
                 ("audit", audit_securite()),
                 ("doc", coherence_doc())]
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
