"""Ligne de commande minimale, adossee au meme moteur que l'interface web.

    python3 -m romule                 lance l'interface web (defaut)
    python3 -m romule scan            affiche l'inventaire
    python3 -m romule convert [--only MOTIF] [--dry-run]
    python3 -m romule push [--only MOTIF]     envoie vers le handheld adb
    python3 -m romule test            joue les tests unitaires
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

from . import __version__, config, console, convert, device, scan, versions
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


def cmd_apikey(args):
    """Gerer les cles d'API sans navigateur.

    C'est ce qui rend l'API utilisable dans un conteneur : `docker compose exec
    romule python3 -m romule apikey create tableau-de-bord` suffit, sans ouvrir
    l'interface ni creer de compte.
    """
    from . import apikeys
    action = getattr(args, "action", None) or "list"

    if action == "create":
        fiche, cle = apikeys.creer(args.nom)
        print("Cle creee : %s" % fiche["nom"])
        print()
        print("  %s" % cle)
        print()
        # Elle n'est stockee que hachee : ce n'est pas une precaution de style,
        # c'est ce qui rend une fuite du fichier d'etat inoffensive. Le prix
        # est qu'on ne peut pas la reafficher, et il faut le dire ici.
        print("Note-la maintenant : elle n'est conservee que sous forme")
        print("d'empreinte et ne pourra pas etre reaffichee.")
        return

    if action == "revoke":
        if apikeys.revoquer(args.id):
            print("Cle %s revoquee." % args.id)
        else:
            print("Aucune cle active avec cet identifiant : %s" % args.id)
            sys.exit(1)
        return

    cles = apikeys.liste(avec_revoquees=bool(getattr(args, "all", False)))
    if not cles:
        print("Aucune cle. `romule apikey create <nom>` en cree une.")
        return
    print("%-18s %-14s %-24s %s" % ("ID", "PREFIXE", "NOM", "DERNIER USAGE"))
    for k in cles:
        vu = k.get("dernier_usage")
        vu = time.strftime("%Y-%m-%d %H:%M", time.localtime(vu)) if vu else "jamais"
        etat = " (revoquee)" if k.get("revoquee") else ""
        print("%-18s %-14s %-24s %s%s"
              % (k["id"], k["prefixe"] + "…", k["nom"][:24], vu, etat))


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
    # L'ordre compte, et il a ete appris a la dure. L'heuristique passait en
    # premier : elle regarde DANS le dossier, donc elle levait avant tout le
    # reste des que le processus n'avait pas le droit d'y entrer. On etablit
    # donc d'abord que le dossier existe et nous appartient, ensuite seulement
    # on se demande s'il ressemble a une ludotheque.
    #
    # La racine par defaut n'existe pas a la premiere ouverture, et son parent
    # non plus : sans cette creation, tout nouvel utilisateur tombait sur un
    # FileNotFoundError des le lancement.
    if not os.path.isdir(config.ROOT):
        try:
            config.ROOT.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print("Impossible de creer le dossier de donnees : %s" % exc)
            print("    %s" % config.ROOT)
            sys.exit(1)
    if not os.access(config.ROOT, os.W_OK):
        print("Le dossier de donnees n'est pas inscriptible :")
        print("    %s" % config.ROOT)
        print("Romule y ecrit sa configuration, ses comptes et ses journaux.")
        if config.en_conteneur():
            print("En conteneur, c'est presque toujours l'identifiant du")
            print("proprietaire : l'image tourne sous 1000:1000.")
            print("    chown -R 1000:1000 <le dossier de l'hote>")
            print("ou adapte `user:` dans docker-compose.yml a ton identifiant")
            print("(`id -u` / `id -g`). Un volume nomme evite la question.")
        sys.exit(1)
    souci = config.racine_douteuse()
    if not souci:
        return
    print("Le dossier de donnees designe %s :" % souci)
    print("    %s" % config.ROOT)
    print("Indique un dossier de donnees explicite :")
    print("    ROMULE_ROOT=/chemin/vers/les/donnees python3 -m romule")
    print("Le dossier des JEUX, lui, se choisit dans l'interface.")
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


# ---------------------------------------------------------------- depannage
#
# Ces commandes existent pour le moment ou l'interface n'est PAS la reponse :
# plus de mot de passe, plus de second facteur, un service qui ne demarre pas,
# ou un conteneur sans navigateur. Jusqu'ici la seule issue etait d'editer
# `_romule-comptes.json` a la main — c'est-a-dire d'y coller une empreinte
# scrypt calculee ailleurs, ce que personne ne reussit du premier coup.
#
# Elles n'ouvrent aucun droit nouveau : qui peut lancer `romule` a deja les
# droits du service, donc l'acces a ses fichiers. Elles rendent seulement
# faisable, sans se tromper, ce que le systeme de fichiers permettait deja.


def _demander_mdp(invite="Nouveau mot de passe : "):
    """Demande un mot de passe deux fois, sans echo.

    Le lire en argument de commande le poserait dans l'historique du shell et
    dans la liste des processus, ou n'importe qui sur la machine peut le voir.
    `--mdp` existe quand meme, pour un script qui sait ce qu'il fait, mais ce
    n'est pas le chemin par defaut.
    """
    import getpass
    un = getpass.getpass(invite)
    deux = getpass.getpass("Confirme               : ")
    if un != deux:
        print("Les deux saisies different.")
        return None
    return un


def cmd_user(args):
    """Comptes : lister, reinitialiser, promouvoir, retirer le second facteur."""
    from . import comptes
    action = getattr(args, "action", None) or "list"

    if action == "list":
        liste = comptes.liste()
        if not liste:
            print("Aucun compte. Le premier cree sera administrateur.")
            return
        print("%-34s %-20s %-6s %-6s %s"
              % ("EMAIL", "NOM", "ADMIN", "2FA", "DERNIERE CONNEXION"))
        for u in liste:
            vu = (time.strftime("%F %H:%M", time.localtime(u["derniere"]))
                  if u.get("derniere") else "jamais")
            print("%-34s %-20s %-6s %-6s %s"
                  % (u["email"][:34], (u.get("nom") or "")[:20],
                     "oui" if u.get("admin") else "-",
                     "oui" if u.get("double_facteur") else "-", vu))
        return

    if action == "passwd":
        mdp = args.mdp or _demander_mdp()
        if mdp is None:
            return 1
        try:
            u = comptes.reinitialiser_mdp(args.email, mdp)
        except ValueError as exc:
            print("Refuse : %s" % exc)
            return 1
        print("Mot de passe repose pour %s." % u["email"])
        # Deux consequences que l'utilisateur doit connaitre AVANT de chercher
        # pourquoi il a ete deconnecte partout.
        print("Toutes les sessions ouvertes de ce compte sont invalidees.")
        print("Le compteur d'echecs et le blocage eventuel sont remis a zero.")
        return

    if action == "admin":
        try:
            u = comptes.par_email(args.email)
        except ValueError as exc:
            print("Refuse : %s" % exc)
            return 1
        if not u:
            print("Aucun compte avec cette adresse.")
            return 1
        vise = not args.retirer
        try:
            comptes.promouvoir(u["id"], vise)
        except ValueError as exc:
            # « On ne retire pas le dernier administrateur » : une instance que
            # personne ne peut administrer se repare a la main, dans un fichier.
            print("Refuse : %s" % exc)
            return 1
        print("%s %s administrateur."
              % (u["email"], "est desormais" if vise else "n'est plus"))
        return

    if action == "totp-off":
        try:
            avait = comptes.desactiver_totp(args.email)
        except ValueError as exc:
            print("Refuse : %s" % exc)
            return 1
        if avait:
            print("Second facteur retire pour %s." % args.email)
        else:
            print("Ce compte n'avait pas de second facteur actif.")
        return

    if action == "rm":
        u = comptes.par_email(args.email)
        if not u:
            print("Aucun compte avec cette adresse.")
            return 1
        if not args.oui:
            print("Ceci supprimera definitivement %s." % u["email"])
            print("Relance avec --oui pour confirmer.")
            return 1
        try:
            comptes.supprimer(u["id"])
        except ValueError as exc:
            print("Refuse : %s" % exc)
            return 1
        print("Compte supprime : %s" % u["email"])
        return


def cmd_config(args):
    """Lire et ecrire un reglage sans navigateur."""
    from . import config as cfgmod
    cfg = cfgmod.load_config()
    # Ce qui ne doit jamais s'afficher : une valeur secrete lue par-dessus
    # l'epaule, ou copiee dans un rapport de bogue avec le reste de la sortie.
    SECRETS = ("auth_secret", "jeton_auto", "steamgriddb_key",
               "igdb_client_secret", "oidc_client_secret")

    def montrer(cle, valeur):
        if cle in SECRETS and valeur:
            return "(%d caracteres, masque)" % len(str(valeur))
        return json.dumps(valeur, ensure_ascii=False)

    action = getattr(args, "action", None) or "list"
    if action == "list":
        for cle in sorted(cfg):
            print("%-26s %s" % (cle, montrer(cle, cfg[cle])))
        return
    if action == "get":
        if args.cle not in cfg:
            print("Reglage inconnu : %s" % args.cle)
            return 1
        print(montrer(args.cle, cfg[args.cle]))
        return
    if action == "set":
        if args.cle not in cfgmod.DEFAULTS:
            print("Reglage inconnu : %s" % args.cle)
            print("`romule config list` donne la liste.")
            return 1
        # La valeur est lue en JSON quand c'est possible : sans cela `false`
        # deviendrait la chaine « false », qui est vraie.
        try:
            valeur = json.loads(args.valeur)
        except ValueError:
            valeur = args.valeur
        attendu = type(cfgmod.DEFAULTS[args.cle])
        if not isinstance(valeur, attendu) and cfgmod.DEFAULTS[args.cle] is not None:
            print("Type refuse : %s attend %s, pas %s."
                  % (args.cle, attendu.__name__, type(valeur).__name__))
            return 1
        cfg[args.cle] = valeur
        cfgmod.save_config(cfg)
        print("%s = %s" % (args.cle, montrer(args.cle, valeur)))
        return


def cmd_doctor(args):
    """Tout ce qu'on demanderait dans un rapport de bogue, en une commande.

    L'audit repond « ce service est-il sur ». Celle-ci repond « pourquoi ne
    fait-il pas ce que je crois » : quelle version, quels chemins, quels
    droits, quels outils, quelle configuration reseau. Ce sont les questions
    qu'on pose en premier a quelqu'un qui ouvre un ticket.
    """
    import platform
    import socket
    from . import comptes, notifs, systems
    cfg = config.load_config()

    def bloc(titre):
        print("\n\033[90m-- %s %s\033[0m" % (titre, "-" * max(0, 56 - len(titre))))

    def ligne(cle, valeur):
        print("  %-22s %s" % (cle, valeur))

    bloc("version")
    ligne("Romule", __version__)
    ligne("Python", "%s  (%s)" % (platform.python_version(), sys.executable))
    ligne("Systeme", "%s %s  %s" % (platform.system(), platform.release(),
                                    platform.machine()))
    ligne("Conteneur", "oui" if os.path.exists("/.dockerenv") else "non")

    bloc("chemins")
    for nom, chemin in (("Donnees (ROMULE_ROOT)", config.ROOT),
                        ("Ludotheque", config.LUDO),
                        ("Depot", config.IMPORT),
                        ("Journal", config.LOGFILE),
                        ("Configuration", config.CONFIG_FILE)):
        p = Path(chemin)
        etat = []
        etat.append("existe" if p.exists() else "ABSENT")
        if p.exists():
            etat.append("inscriptible" if os.access(p, os.W_OK) else "LECTURE SEULE")
            etat.append(oct(p.stat().st_mode & 0o777))
        ligne(nom, "%s  [%s]" % (chemin, ", ".join(etat)))
    if config.LUDO_IMPOSEE:
        ligne("", "ludotheque imposee par ROMULE_LIBRARY")

    bloc("acces")
    ligne("Mode", cfg.get("auth_mode"))
    ligne("Comptes", "%d (%d administrateur(s))"
          % (comptes.nombre(),
             sum(1 for u in comptes.liste() if u.get("admin"))))
    ligne("Reseau ouvert", "oui" if cfg.get("lan_access") else "non")
    ligne("Jeton", "pose" if config.TOKEN else "aucun")
    ligne("Proxies de confiance", config.env("TRUSTED_PROXIES") or "aucun")
    ligne("Ecoute", "%s:%d" % (config.env("BIND") or "(defaut)", config.PORT))
    try:
        with socket.socket() as s:
            s.settimeout(0.5)
            libre = s.connect_ex(("127.0.0.1", config.PORT)) != 0
        ligne("Port %d" % config.PORT, "libre" if libre else "DEJA PRIS")
    except OSError as exc:
        ligne("Port %d" % config.PORT, "indeterminable (%s)" % exc)

    bloc("outils externes")
    for outil in ("adb", "nsz", "unar", "7z", "7zz"):
        ligne(outil, shutil.which(outil) or "absent")

    bloc("services distants")
    ligne("Jaquettes", cfg.get("cover_provider"))
    for cle, nom in (("steamgriddb_key", "SteamGridDB"),
                     ("igdb_client_id", "IGDB"),
                     ("oidc_issuer", "OIDC")):
        ligne(nom, "configure" if (cfg.get(cle) or "").strip() else "non configure")
    dests = notifs.destinations(cfg)
    ligne("Notifications", "%d destination(s) : %s" % (
        len(dests), ", ".join(d["service"] for d in dests) or "aucune"))

    bloc("ludotheque")
    try:
        lib = scan.Library()
        lib.scan()
        par_sys = {}
        for f in lib.files:
            par_sys[f.get("systeme", "?")] = par_sys.get(f.get("systeme", "?"), 0) + 1
        ligne("Fichiers reconnus", str(len(lib.files)))
        for cle in sorted(par_sys, key=lambda k: -par_sys[k])[:8]:
            ligne("  " + str(systems.get(cle).get("name", cle)), str(par_sys[cle]))
    except Exception as exc:
        ligne("Analyse", "IMPOSSIBLE : %s" % exc)

    bloc("journalisation")
    ligne("ROMULE_LOG", console.STYLE)
    ligne("Styles", ", ".join(console.STYLES))
    print()
    print("Colle ce rapport dans un ticket : il ne contient ni mot de passe,")
    print("ni cle, ni adresse de webhook.")


def main(argv):
    _verifier_racine()
    _verifier_jeton()
    _signaler_anciennes_variables()
    _signaler_outils()
    parser = argparse.ArgumentParser(
        prog="romule",
        description="Romule — ludotheque de jeux auto-hebergee")
    parser.add_argument("--version", action="version",
                        version="romule %s" % __version__)
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

    pk = sub.add_parser("apikey", help="cles d'API (lister, creer, revoquer)")
    ka = pk.add_subparsers(dest="action")
    kl = ka.add_parser("list", help="lister les cles")
    kl.add_argument("--all", action="store_true",
                    help="inclure les cles revoquees")
    kc = ka.add_parser("create", help="creer une cle")
    kc.add_argument("nom", help="a quoi elle sert (« tableau-de-bord », « sauvegarde »)")
    kr = ka.add_parser("revoke", help="revoquer une cle")
    kr.add_argument("id", help="identifiant montre par `apikey list`")

    pu = sub.add_parser("user", help="comptes : lister, reinitialiser, promouvoir")
    ua = pu.add_subparsers(dest="action")
    ua.add_parser("list", help="lister les comptes")
    up = ua.add_parser("passwd", help="reposer un mot de passe oublie")
    up.add_argument("email")
    up.add_argument("--mdp", help="ne pas demander (le shell le retiendra)")
    um = ua.add_parser("admin", help="donner ou retirer l'administration")
    um.add_argument("email")
    um.add_argument("--retirer", action="store_true", help="retirer au lieu de donner")
    ut = ua.add_parser("totp-off", help="retirer le second facteur (telephone perdu)")
    ut.add_argument("email")
    ur = ua.add_parser("rm", help="supprimer un compte")
    ur.add_argument("email")
    ur.add_argument("--oui", action="store_true", help="confirmer la suppression")

    pg = sub.add_parser("config", help="lire ou ecrire un reglage")
    ga = pg.add_subparsers(dest="action")
    ga.add_parser("list", help="tout afficher")
    gg = ga.add_parser("get", help="lire un reglage")
    gg.add_argument("cle")
    gs = ga.add_parser("set", help="ecrire un reglage")
    gs.add_argument("cle")
    gs.add_argument("valeur")

    sub.add_parser("doctor", help="tout ce qu'un ticket devrait contenir")

    # tolere les options globales inconnues (ex : --no-browser)
    args, _ = parser.parse_known_args([a for a in argv if a != "--no-browser"])
    # Le code de retour est PROPAGE. Sans lui, `romule user passwd` affichait
    # « Refuse : ... » et sortait quand meme sur 0 : un script ne pouvait pas
    # distinguer un refus d'un succes, et un `&&` enchainait sur une commande
    # qui n'avait rien fait. C'est le test des commandes de depannage qui l'a
    # trouve — six refus parfaitement rediges, tous annonces comme reussis.
    return {
        None: cmd_serve, "serve": cmd_serve, "scan": cmd_scan,
        "convert": cmd_convert, "push": cmd_push, "device": cmd_device,
        "test": cmd_test, "apikey": cmd_apikey,
        "user": cmd_user, "config": cmd_config, "doctor": cmd_doctor,
    }[args.cmd](args) or 0
