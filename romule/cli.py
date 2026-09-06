"""A minimal command line, backed by the same engine as the web interface.

    python3 -m romule                 start the web interface (default)
    python3 -m romule scan            print the inventory
    python3 -m romule convert [--only PATTERN] [--dry-run]
    python3 -m romule push [--only PATTERN]   send to the adb handheld
    python3 -m romule test            run the unit tests
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
    """A synchronous JobRunner that prints instead of logging in the background."""
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


def cmd_access(args):
    """Open or close passwordless access, from the terminal.

    The escape hatch. Everything else about access is decided in the interface,
    which is the right place — until the day you cannot reach the interface:
    a password forgotten with no second account, an SSO whose provider is down,
    a `close` regretted from the wrong network. Then there has to be a way in
    that does not go through the thing that is broken.

    It runs where the data is — inside the container, over `docker compose
    exec` — which is exactly the access that proves you are the operator.
    """
    from . import auth, config
    action = getattr(args, "action", None) or "status"
    cfg = config.load_config()

    if action == "open":
        # `lan_access` alone reopens NOTHING when an authentication is active:
        # the server consults the session first and never reaches the setting.
        # An escape hatch that answers "opened" and leaves the door shut is
        # worse than no hatch, so this switches the authentication off too, and
        # says exactly what it turned off.
        etait = auth.enabled(cfg)
        mode = cfg.get("auth_mode")
        cfg["lan_access"] = True
        cfg["acces_choisi"] = True
        cfg["auth_mode"] = "aucun"
        config.save_config(cfg)
        print("Acces ouvert SANS MOT DE PASSE.")
        if etait:
            print("L'authentification (%s) est DESACTIVEE." % mode)
            print("Les comptes existent toujours : `romule access close` la")
            print("remet en service.")
        print()
        print("Tout appareil capable de joindre cette adresse a tous les")
        print("droits — y compris derriere un proxy inverse. Redemarre le")
        print("service pour que ce soit pris en compte.")
        return

    if action == "close":
        # Closing with no way in left would lock everybody out, including the
        # person typing this. That is the deadlock the whole first-access
        # design exists to avoid, so it is refused rather than obeyed.
        # `close` is also what puts an authentication back after `open` turned
        # it off: accounts survive, only the mode was changed.
        from . import accounts
        if not auth.enabled(cfg) and accounts.count():
            cfg["auth_mode"] = "interne"
        if not auth.enabled(cfg):
            print("Refuse : aucun compte ni SSO utilisable.")
            print()
            print("Fermer l'acces maintenant enfermerait tout le monde dehors,")
            print("toi compris. Cree d'abord un compte :")
            print("    romule user create toi@exemple.fr")
            return 1
        cfg["lan_access"] = False
        cfg["acces_choisi"] = True
        config.save_config(cfg)
        print("Acces sans mot de passe desactive.")
        print("Il faut desormais se connecter. Redemarre le service.")
        return

    protege = []
    if auth.enabled(cfg):
        protege.append("authentification (%s)" % cfg.get("auth_mode"))
    if (cfg.get("jeton_auto") or "").strip() or config.TOKEN:
        protege.append("jeton")
    if cfg.get("lan_access"):
        print("Acces : OUVERT sans mot de passe.")
    elif protege:
        print("Acces : protege par %s." % ", ".join(protege))
    elif not cfg.get("acces_choisi"):
        print("Acces : PERSONNE N'A ENCORE CHOISI.")
        print()
        print("L'installation repond a tout le monde jusqu'a ce que l'etape")
        print("« Ton acces » de l'assistant soit renseignee.")
    else:
        print("Acces : cette machine seulement.")
    print()
    print("  romule access open     ouvrir sans mot de passe")
    print("  romule access close    exiger une connexion")


def cmd_token(args):
    """Show or replace the access token, from the terminal.

    The token is announced ONCE, at first start: a secret reprinted at every
    restart ends up in every log a user attaches to a bug report. Which means
    there has to be a way to see it again — otherwise "announced once" is just
    "lost", and the answer becomes wiping the volume.

    Unlike an API key, the token is stored in clear: it is not a credential
    identifying somebody, it is the shared way in for an installation that has
    no account yet. So it CAN be shown again, and that is the point of `show`.
    """
    from . import config
    action = getattr(args, "action", None) or "show"
    cfg = config.load_config()

    if action == "reset":
        import secrets
        jeton = secrets.token_urlsafe(24)
        cfg["jeton_auto"] = jeton
        # Announced again at the next start: a new token nobody has been told
        # about is a lock-out.
        cfg["jeton_annonce"] = False
        config.save_config(cfg)
        print("Nouveau jeton d'acces :")
        print()
        print("  %s" % jeton)
        print()
        print("L'ancien ne fonctionne plus. Les navigateurs qui l'avaient")
        print("retenu redemanderont celui-ci au prochain chargement.")
        print("Redemarre le service pour qu'il le prenne en compte.")
        return

    jeton = (cfg.get("jeton_auto") or "").strip() or config.env("TOKEN", "").strip()
    if not jeton:
        print("Aucun jeton d'acces.")
        print()
        print("Il n'en est engendre un que lorsque le service ecoute sur le")
        print("reseau sans compte ni SSO — sur cette machine seulement, il n'y")
        print("a rien a proteger. `romule token reset` en pose un quand meme.")
        return
    print("Jeton d'acces :")
    print()
    print("  %s" % jeton)
    print()
    print("Colle-le dans l'ecran d'accueil de l'interface.")


def cmd_apikey(args):
    """Manage API keys without a browser.

    This is what makes the API usable inside a container: `docker compose exec
    romule python3 -m romule apikey create tableau-de-bord` is enough, with no
    interface to open and no account to create.
    """
    from . import apikeys
    action = getattr(args, "action", None) or "list"

    if action == "create":
        fiche, cle = apikeys.create(args.nom)
        print("Cle creee : %s" % fiche["nom"])
        print()
        print("  %s" % cle)
        print()
        # It is only stored hashed: not a stylistic precaution, but what makes
        # a leak of the state file harmless. The price is that it cannot be
        # shown again, and that has to be said here.
        print("Note-la maintenant : elle n'est conservee que sous forme")
        print("d'empreinte et ne pourra pas etre reaffichee.")
        return

    if action == "revoke":
        if apikeys.revoke(args.id):
            print("Cle %s revoquee." % args.id)
        else:
            print("Aucune cle active avec cet identifiant : %s" % args.id)
            sys.exit(1)
        return

    cles = apikeys.list_all(with_revoked=bool(getattr(args, "all", False)))
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


def _check_root():
    """Refuse to work on a folder that is plainly not a game library.

    The tool moves files, creates them, trashes them. A mis-set root — the home
    folder, the disk root, a code repository — is not an inconvenience: it is
    data loss. Better to refuse to start than to file games into `~`.
    """
    # The order matters, and it was learnt the hard way. The heuristic came
    # first: it looks INSIDE the folder, so it raised before everything else as
    # soon as the process was not allowed in. So we first establish that the
    # folder exists and is ours, and only then ask whether it looks like a game
    # library.
    #
    # The default root does not exist on first launch, and neither does its
    # parent: without this creation, every new user hit a FileNotFoundError on
    # startup.
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
        if config.in_container():
            print("En conteneur, c'est presque toujours l'identifiant du")
            print("proprietaire : l'image tourne sous 1000:1000.")
            print("    chown -R 1000:1000 <le dossier de l'hote>")
            print("ou adapte `user:` dans docker-compose.yml a ton identifiant")
            print("(`id -u` / `id -g`). Un volume nomme evite la question.")
        sys.exit(1)
    souci = config.root_looks_wrong()
    if not souci:
        return
    print("Le dossier de donnees designe %s :" % souci)
    print("    %s" % config.ROOT)
    print("Indique un dossier de donnees explicite :")
    print("    ROMULE_ROOT=/chemin/vers/les/donnees python3 -m romule")
    print("Le dossier des JEUX, lui, se choisit dans l'interface.")
    sys.exit(1)


# Installation advice, per system. The old message only knew Homebrew: on a
# NAS or a Linux machine it sent the user nowhere.
REMEDIES = {
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


def _family():
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        for fichier, cle in (("/etc/debian_version", "debian"),
                             ("/etc/arch-release", "arch")):
            if Path(fichier).exists():
                return cle
    return "autre"


def remedy(tool):
    """How to install a missing tool, on THIS machine."""
    r = REMEDIES.get(tool) or {}
    return r.get(_family()) or r.get("autre") or ""


def _notice(*lines):
    """Un avis preliminaire, sur STDERR.

    These messages precede every command, including the ones whose output is
    meant to be read by a program. On stdout they polluted it:
    `VALUE=$(romule config get trash_days)` reported "nsz absent — ..." stuck to
    the value. CI is what showed it — that machine has no `nsz`, mine does, and
    the defect was therefore only visible over there.

    stderr exists for this: visible in a terminal, out of the way of a pipe.
    """
    for ligne in lines:
        print(ligne, file=sys.stderr)


def _report_tools():
    """Report missing tools without preventing startup.

    The program's entry point used to stop dead when `nsz` was missing, with a
    Homebrew hint for an answer. But `nsz` only serves conversion: without it
    you can perfectly well browse your library, tidy it, transfer it. A missing
    tool disables ITS feature, it does not forbid the application.
    """
    for tool in ("nsz", "adb"):
        if shutil.which(tool):
            continue
        _notice("%-4s absent — %s desactivee." % (tool, REMEDIES[tool]["quoi"]))
        conseil = remedy(tool)
        if conseil:
            _notice("     %s" % conseil)


def _check_token():
    """An example token is not a token.

    The compose file used to offer a ready-made one. Whoever leaves it in place
    believes their service protected while the password is written in the
    public repository — worse than no token at all, because nobody is wary of
    it.
    """
    if config.TOKEN and config.TOKEN.strip().lower() in config.FORBIDDEN_TOKENS:
        _notice("ROMULE_TOKEN vaut encore une valeur d'exemple : %r" % config.TOKEN,
              "Genere le tien :",
              "    python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"")
        sys.exit(1)


def _report_legacy_vars():
    """The SWITCH_* names still work, but they are no longer the right ones."""
    if not config.LEGACY_FILES_USED:
        return
    noms = sorted(set(config.LEGACY_FILES_USED))
    _notice("Variables d'environnement a renommer : %s" % ", ".join(noms),
          "     %s" % ", ".join(n.replace("SWITCH_", "ROMULE_") for n in noms))


# ---------------------------------------------------------------- depannage
#
# These commands exist for the moment when the interface is NOT the answer: no
# password left, no second factor, a service that will not start, or a
# container with no browser. Until now the only way out was editing
# `_romule-comptes.json` by hand — that is, pasting an scrypt digest computed
# elsewhere, which nobody gets right first time.
#
# They grant no new rights: whoever can run `romule` already has the service's
# rights, hence access to its files. They merely make doable, without mistakes,
# what the filesystem already allowed.


def _ask_password(prompt="Nouveau mot de passe : "):
    """Ask for a password twice, with no echo.

    Reading it as a command argument would put it in the shell history and in
    the process list, where anyone on the machine can see it. `--mdp` exists
    all the same, for a script that knows what it is doing, but it is not the
    default path.
    """
    import getpass
    un = getpass.getpass(prompt)
    deux = getpass.getpass("Confirme               : ")
    if un != deux:
        print("Les deux saisies different.")
        return None
    return un


def cmd_user(args):
    """Accounts: list, reset, promote, remove the second factor."""
    from . import accounts
    action = getattr(args, "action", None) or "list"

    if action == "list":
        liste = accounts.list_all()
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

    if action == "create":
        # This was missing, and its absence was a wall. The wizard refused to
        # create the first account unless the request came from 127.0.0.1 —
        # nobody, under Docker — and there was no way round from the terminal
        # either. A container install could not get an account at all.
        from . import auth, config
        mdp = args.mdp or _ask_password()
        premier = not accounts.list_all()
        try:
            u = accounts.create(args.email, mdp, args.nom or "")
        except ValueError as exc:
            print("Refuse : %s" % exc)
            return 1
        print("Compte cree : %s%s" % (u["email"], "  (administrateur)" if premier else ""))
        if premier:
            # An account that guards nothing is not an answer. Creating the
            # first one IS the choice, so it switches the mode on — the same
            # thing the wizard does.
            cfg = config.load_config()
            cfg["auth_mode"] = "interne"
            cfg["lan_access"] = False
            cfg["acces_choisi"] = True
            config.save_config(cfg)
            print("Authentification interne activee. Redemarre le service.")
        elif not auth.enabled(config.load_config()):
            print("Note : l'authentification n'est pas active "
                  "(Reglages > Acces, ou `romule access close`).")
        return

    if action == "passwd":
        mdp = args.mdp or _ask_password()
        if mdp is None:
            return 1
        try:
            u = accounts.reset_password(args.email, mdp)
        except ValueError as exc:
            print("Refuse : %s" % exc)
            return 1
        print("Mot de passe repose pour %s." % u["email"])
        # Two consequences the user needs to know BEFORE wondering why they
        # were logged out everywhere.
        print("Toutes les sessions ouvertes de ce compte sont invalidees.")
        print("Le compteur d'echecs et le blocage eventuel sont remis a zero.")
        return

    if action == "admin":
        try:
            u = accounts.by_email(args.email)
        except ValueError as exc:
            print("Refuse : %s" % exc)
            return 1
        if not u:
            print("Aucun compte avec cette adresse.")
            return 1
        vise = not args.retirer
        try:
            accounts.set_admin(u["id"], vise)
        except ValueError as exc:
            # "The last administrator cannot be removed": an instance nobody
            # can administer is repaired by hand, in a file.
            print("Refuse : %s" % exc)
            return 1
        print("%s %s administrateur."
              % (u["email"], "est desormais" if vise else "n'est plus"))
        return

    if action == "totp-off":
        try:
            avait = accounts.disable_totp(args.email)
        except ValueError as exc:
            print("Refuse : %s" % exc)
            return 1
        if avait:
            print("Second facteur retire pour %s." % args.email)
        else:
            print("Ce compte n'avait pas de second facteur actif.")
        return

    if action == "rm":
        u = accounts.by_email(args.email)
        if not u:
            print("Aucun compte avec cette adresse.")
            return 1
        if not args.oui:
            print("Ceci supprimera definitivement %s." % u["email"])
            print("Relance avec --oui pour confirmer.")
            return 1
        try:
            accounts.delete(u["id"])
        except ValueError as exc:
            print("Refuse : %s" % exc)
            return 1
        print("Compte supprime : %s" % u["email"])
        return


def cmd_config(args):
    """Read and write a setting without a browser."""
    from . import config as cfgmod
    cfg = cfgmod.load_config()
    # What must never be displayed: a secret value read over a shoulder, or
    # copied into a bug report along with the rest of the output.
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
        # The value is read as JSON when possible: without that, `false` would
        # become the string "false", which is truthy.
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
    """Everything a bug report should contain, in one command.

    The audit answers "is this service safe". This one answers "why is it not
    doing what I think": which version, which paths, which permissions, which
    tools, which network configuration. Those are the first questions you ask
    anyone opening a ticket.
    """
    import platform
    import socket
    from . import accounts, notify, systems
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
    if config.LIBRARY_FORCED:
        ligne("", "ludotheque imposee par ROMULE_LIBRARY")

    bloc("acces")
    ligne("Mode", cfg.get("auth_mode"))
    ligne("Comptes", "%d (%d administrateur(s))"
          % (accounts.count(),
             sum(1 for u in accounts.list_all() if u.get("admin"))))
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
    for tool in ("adb", "nsz", "unar", "7z", "7zz"):
        ligne(tool, shutil.which(tool) or "absent")

    bloc("services distants")
    ligne("Jaquettes", cfg.get("cover_provider"))
    for cle, nom in (("steamgriddb_key", "SteamGridDB"),
                     ("igdb_client_id", "IGDB"),
                     ("oidc_issuer", "OIDC")):
        ligne(nom, "configure" if (cfg.get(cle) or "").strip() else "non configure")
    dests = notify.destinations(cfg)
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
    _check_root()
    _check_token()
    _report_legacy_vars()
    _report_tools()
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

    pa = sub.add_parser("access", help="acces sans mot de passe : ouvrir ou fermer")
    aa = pa.add_subparsers(dest="action")
    aa.add_parser("status", help="dire ce qui protege l'acces (defaut)")
    aa.add_parser("open", help="ouvrir sans mot de passe")
    aa.add_parser("close", help="exiger une connexion")

    pj = sub.add_parser("token", help="jeton d'acces : afficher ou renouveler")
    ja = pj.add_subparsers(dest="action")
    ja.add_parser("show", help="reafficher le jeton (defaut)")
    ja.add_parser("reset", help="en engendrer un nouveau")

    pu = sub.add_parser("user", help="comptes : lister, reinitialiser, promouvoir")
    ua = pu.add_subparsers(dest="action")
    ua.add_parser("list", help="lister les comptes")
    uc = ua.add_parser("create", help="creer un compte (le premier est administrateur)")
    uc.add_argument("email")
    uc.add_argument("--nom", help="nom affiche")
    uc.add_argument("--mdp", help="ne pas demander (le shell le retiendra)")
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

    # tolerate unknown global options (e.g. --no-browser)
    args, _ = parser.parse_known_args([a for a in argv if a != "--no-browser"])
    # The exit code is PROPAGATED. Without it, `romule user passwd` printed
    # "Refused: ..." and exited 0 anyway: a script could not tell a refusal
    # from a success, and an `&&` chained onto a command that had done nothing.
    # The debug-commands test is what found it — six perfectly worded refusals,
    # every one announced as a success.
    return {
        None: cmd_serve, "serve": cmd_serve, "scan": cmd_scan,
        "convert": cmd_convert, "push": cmd_push, "device": cmd_device,
        "test": cmd_test, "apikey": cmd_apikey, "token": cmd_token,
        "access": cmd_access,
        "user": cmd_user, "config": cmd_config, "doctor": cmd_doctor,
    }[args.cmd](args) or 0
