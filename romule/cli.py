"""Ligne de commande minimale, adossee au meme moteur que l'interface web.

    python3 -m romule                 lance l'interface web (defaut)
    python3 -m romule scan            affiche l'inventaire
    python3 -m romule convert [--only MOTIF] [--dry-run]
    python3 -m romule push [--only MOTIF]     envoie vers le handheld adb
    python3 -m romule test            joue les tests unitaires
"""

import argparse
import shutil
import sys
from pathlib import Path

from . import config, convert, device, scan, versions
from .jobs import JobRunner


def _print_log(msg):
    print("  " + msg)


class _PrintJob(JobRunner):
    """JobRunner synchrone qui imprime au lieu de journaliser en tache de fond."""
    def log(self, line):
        print("  " + line)
    def start(self, label, fn, *args):
        fn(*args)
        return True


def _match(f, only):
    return not only or only.lower() in f["rel"].lower()


def cmd_scan(args):
    lib = scan.Library()
    lib.scan()
    versions.load(lib)
    lib.enrich()
    s = lib.stats()
    print("%d fichiers · %d jeux · %d maj · %d DLC · %d inconnu(s)"
          % (s["total"], s["base"], s["update"], s["dlc"], s["unknown"]))
    print("%d a convertir · %d peuvent partir · %d patches perimes · %d DLC manquants"
          % (s["to_convert"], s["cleanable"], s["outdated"], s["missing_dlc"]))
    for f in lib.files:
        flags = " ".join("[%s]" % g[1] for g in f.get("flags", []))
        print("  %-8s %-6s %s %s" % (f["type"], f["ext"], f["rel"], flags))


def cmd_convert(args):
    lib = scan.Library()
    lib.scan()
    lib.enrich()
    todo = [f["path"] for f in lib.files if f.get("needs_convert") and _match(f, args.only)]
    if not todo:
        print("Rien a convertir.")
        return
    print("%d fichier(s) a convertir :" % len(todo))
    for p in todo:
        print("  %s" % p)
    if args.dry_run:
        print("(--dry-run : rien n'est fait)")
        return
    convert.run(todo, config.load_config()["jobs"], convert.default_threads(),
                True, lib.maxkey, _PrintJob())


def cmd_push(args):
    lib = scan.Library()
    lib.scan()
    lib.enrich()
    cfg = config.load_config()
    paths = [f["path"] for f in lib.files
             if f["ext"] in ("nsp", "xci") and _match(f, args.only)]
    if not paths:
        print("Aucun .nsp/.xci a envoyer.")
        return
    print("Envoi vers %s (appareil : %s)"
          % (cfg["device_dir"], device.state() or "non connecte"))
    device.push(paths, cfg["device_dir"], _PrintJob(),
                cfg.get("verify_mode", "size"), cfg.get("push_layout", "type"),
                cfg.get("incremental", True))


def _human(b):
    if b is None:
        return "?"
    for u in ("o", "Kio", "Mio", "Gio", "Tio"):
        if b < 1024:
            return "%d %s" % (b, u) if u == "o" else "%.1f %s" % (b, u)
        b /= 1024
    return "%.1f Pio" % b


def cmd_device(args):
    if not device.adb_available():
        print("adb introuvable. brew install android-platform-tools")
        return
    inf = device.info()
    if not inf.get("connected"):
        print("Aucune console prete (etat : %s)." % (inf.get("state") or "non connectee"))
        print("Branche le handheld en USB et autorise le debogage.")
        return
    print("Console : %s  (Android %s, serie %s)"
          % (inf["name"], inf["android"], inf["serial"]))
    for v in device.volumes():
        print("  %-14s %-24s libre %s / %s"
              % (v["kind"], v["path"], _human(v["free"]), _human(v["total"])))
    cfg = config.load_config()
    root = args.root or cfg["device_dir"]
    print("\nJeux sous %s :" % root)
    games = device.find_games(root)
    lib = scan.Library()
    lib.scan()
    device.reconcile(games, lib.files)
    if not games:
        print("  (aucun fichier Switch trouve)")
    for g in games:
        tag = "deja en biblio" if g["in_library"] else "NOUVEAU"
        print("  %-8s %-9s %-12s %s" % (g["type"], _human(g["size"]), tag, g["name"]))


def cmd_test(args):
    from .tests import test_titleid, test_device
    ok = test_titleid._run() and test_device._run()
    sys.exit(0 if ok else 1)


def cmd_serve(args):
    from . import server
    server.serve(open_browser="--no-browser" not in sys.argv)


def _verifier_racine():
    """Refuse de travailler sur un dossier qui n'est manifestement pas une
    ludotheque.

    L'outil deplace des fichiers, en cree, en met a la corbeille. Une racine
    mal reglee — le dossier personnel, la racine du disque, un depot de code —
    n'est pas une gene : c'est une perte de donnees. Mieux vaut refuser de
    demarrer que de ranger des jeux dans `~`.
    """
    souci = config.racine_douteuse()
    if not souci:
        # La racine par defaut n'existe pas a la premiere ouverture, et son
        # parent non plus : sans cette creation, tout nouvel utilisateur
        # tombait sur un FileNotFoundError des le lancement.
        try:
            config.ROOT.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print("Impossible de creer la ludotheque : %s" % exc)
            print("    %s" % config.ROOT)
            sys.exit(1)
        return
    print("La ludotheque designe %s :" % souci)
    print("    %s" % config.ROOT)
    print("Indique un dossier de donnees explicite :")
    print("    ROMULE_ROOT=/chemin/vers/ta/ludotheque python3 -m romule")
    sys.exit(1)


# Conseils d'installation, par systeme. L'ancien message ne connaissait que
# Homebrew : sur un NAS ou une machine Linux, il envoyait l'utilisateur nulle
# part.
REMEDES = {
    "nsz": {
        "quoi": "conversion des .nsz/.xcz",
        "macos": "brew install pipx && pipx install nsz",
        "debian": "sudo apt install pipx && pipx install nsz",
        "arch": "sudo pacman -S python-pipx && pipx install nsz",
        "autre": "pipx install nsz  (ou pip install --user nsz)",
    },
    "adb": {
        "quoi": "pilotage de la console",
        "macos": "brew install android-platform-tools",
        "debian": "sudo apt install android-tools-adb",
        "arch": "sudo pacman -S android-tools",
        "autre": "installe les « platform-tools » d'Android",
    },
}


def _famille():
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        for fichier, cle in (("/etc/debian_version", "debian"),
                             ("/etc/arch-release", "arch")):
            if Path(fichier).exists():
                return cle
    return "autre"


def remede(outil):
    """Comment installer un outil manquant, sur CETTE machine."""
    r = REMEDES.get(outil) or {}
    return r.get(_famille()) or r.get("autre") or ""


def _signaler_outils():
    """Signale les outils absents sans empecher de demarrer.

    L'entree du programme s'arretait net quand `nsz` manquait, avec un conseil
    Homebrew pour toute reponse. Or `nsz` ne sert qu'a convertir : sans lui, on
    peut parfaitement consulter sa ludotheque, la ranger, la transferer. Un
    outil absent desactive SA fonction, il n'interdit pas l'application.
    """
    for outil in ("nsz", "adb"):
        if shutil.which(outil):
            continue
        print("%-4s absent — %s desactivee." % (outil, REMEDES[outil]["quoi"]))
        conseil = remede(outil)
        if conseil:
            print("     %s" % conseil)


def _verifier_jeton():
    """Un jeton d'exemple n'est pas un jeton.

    Le fichier compose en proposait un tout fait. Celui qui le laisse en place
    croit son service protege alors que le mot de passe est ecrit dans le
    depot public — c'est pire que pas de jeton du tout, parce qu'on ne s'en
    mefie pas.
    """
    if config.TOKEN and config.TOKEN.strip().lower() in config.JETONS_INTERDITS:
        print("ROMULE_TOKEN vaut encore une valeur d'exemple : %r" % config.TOKEN)
        print("Genere le tien :")
        print("    python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"")
        sys.exit(1)


def _signaler_anciennes_variables():
    """Les noms SWITCH_* marchent encore, mais ils ne sont plus les bons."""
    if not config.ANCIENNES_UTILISEES:
        return
    noms = sorted(set(config.ANCIENNES_UTILISEES))
    print("Variables d'environnement a renommer : %s" % ", ".join(noms))
    print("     %s" % ", ".join(n.replace("SWITCH_", "ROMULE_") for n in noms))


def main(argv):
    _verifier_racine()
    _verifier_jeton()
    _signaler_anciennes_variables()
    _signaler_outils()
    parser = argparse.ArgumentParser(
        prog="romule",
        description="Romule — ludotheque de jeux auto-hebergee")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("serve", help="interface web (defaut)")
    sub.add_parser("scan", help="afficher l'inventaire")

    pc = sub.add_parser("convert", help="convertir les .nsz/.xcz restants")
    pc.add_argument("--only", help="ne traiter que les chemins contenant MOTIF")
    pc.add_argument("--dry-run", action="store_true", help="ne rien ecrire")

    pp = sub.add_parser("push", help="envoyer les jeux vers le handheld adb")
    pp.add_argument("--only", help="ne traiter que les chemins contenant MOTIF")

    pd = sub.add_parser("device", help="detecter la console et lister ses jeux")
    pd.add_argument("--root", help="dossier a explorer sur l'appareil")

    sub.add_parser("test", help="jouer les tests unitaires")

    # tolere les options globales inconnues (ex : --no-browser)
    args, _ = parser.parse_known_args([a for a in argv if a != "--no-browser"])
    {
        None: cmd_serve, "serve": cmd_serve, "scan": cmd_scan,
        "convert": cmd_convert, "push": cmd_push, "device": cmd_device,
        "test": cmd_test,
    }[args.cmd](args)
