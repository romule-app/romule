"""Lancement automatique de la ludotheque (macOS, launchd).

Sans cela il faut ouvrir un terminal et lancer `python3 switch.py` avant de
pouvoir consulter sa ludotheque depuis le telephone. Un agent launchd la
demarre a l'ouverture de session et la relance si elle s'arrete.

    python3 -m switchlib.service installer
    python3 -m switchlib.service etat
    python3 -m switchlib.service retirer

On ecrit dans ~/Library/LaunchAgents : un agent utilisateur, pas un daemon
systeme. Il n'a donc aucun privilege particulier, et tourne sous le compte de
l'utilisateur — c'est necessaire pour qu'adb retrouve ses autorisations.
"""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from . import config

ETIQUETTE = "fr.ludotheque.switch"
PLIST = Path.home() / "Library" / "LaunchAgents" / (ETIQUETTE + ".plist")


def _definition(port=None):
    return {
        "Label": ETIQUETTE,
        "ProgramArguments": [sys.executable, str(config.ROOT / "switch.py")],
        "WorkingDirectory": str(config.ROOT),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},   # relance si ca plante, pas si on arrete
        "EnvironmentVariables": {
            "SWITCH_ROOT": str(config.ROOT),
            "SWITCH_WEB_PORT": str(port or config.PORT),
            # Le navigateur ne doit pas s'ouvrir a chaque ouverture de session.
            "SWITCH_NO_BROWSER": "1",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        },
        "StandardOutPath": str(config.ROOT / "_service.log"),
        "StandardErrorPath": str(config.ROOT / "_service.log"),
    }


def installer(port=None):
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(_definition(port)))
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(PLIST)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "launchctl a refuse le chargement")
    return str(PLIST)


def retirer():
    if not PLIST.exists():
        return False
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    PLIST.unlink()
    return True


def etat():
    if not PLIST.exists():
        return {"installe": False, "actif": False, "plist": str(PLIST)}
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    ligne = next((l for l in r.stdout.splitlines() if ETIQUETTE in l), "")
    champs = ligne.split()
    return {
        "installe": True,
        "actif": bool(ligne),
        "pid": champs[0] if champs and champs[0] != "-" else None,
        "dernier_code": champs[1] if len(champs) > 1 else None,
        "plist": str(PLIST),
        "port": plistlib.loads(PLIST.read_bytes())
                .get("EnvironmentVariables", {}).get("SWITCH_WEB_PORT"),
    }


def main(argv):
    action = argv[0] if argv else "etat"
    if action == "installer":
        port = int(argv[1]) if len(argv) > 1 else None
        print("Agent installe : %s" % installer(port))
        print("La ludotheque demarre maintenant a chaque ouverture de session.")
    elif action == "retirer":
        print("Agent retire." if retirer() else "Aucun agent installe.")
    else:
        for k, v in etat().items():
            print("%-14s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
