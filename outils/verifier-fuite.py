#!/usr/bin/env python3
"""Refuse qu'une donnee personnelle entre dans le depot.

Ce projet est ne DANS le dossier de jeux de son auteur : le code, les ROMs, les
cles de console et les identifiants d'API ont longtemps cohabite. Le depot
public a ete extrait a la main, mais « a la main » n'est pas une garantie qui
tient dans le temps.

Ce script en fait une : il inspecte ce que git s'apprete a suivre — pas le
disque, l'INDEX — et refuse trois choses.

  * un NOM de fichier interdit : cle de console, image de jeu, fichier d'etat ;
  * un CONTENU qui ressemble a un identifiant : cle d'API, secret, jeton ;
  * un octet nul, qui ferait passer un fichier source pour un binaire aux yeux
    de git et de grep (c'est deja arrive a `app.js`).

Les adresses IP privees sont signalees sans bloquer : le code en contient
legitimement comme exemples de documentation, et seul un humain sait
distinguer « 192.168.1.42 » d'une vraie adresse de console.

    python3 outils/verifier-fuite.py            # ce que git suit
    python3 outils/verifier-fuite.py --tout     # tout l'arbre de travail
    python3 outils/verifier-fuite.py --autotest # verifie que le script mord

Sortie 0 si rien, 1 sinon. Utilisable en hook pre-commit et en CI.
"""

import re
import subprocess
import sys
from pathlib import Path

# --- noms interdits ---------------------------------------------------------
NOMS_INTERDITS = [
    (re.compile(r"(^|/)(prod|title|dev)\.keys$", re.I), "cle de console"),
    (re.compile(r"\.(nsp|nsz|xci|xcz|iso|wbfs|rvz|chd|cia|gba|nds|3ds|sfc|smc|"
                r"n64|z64|gen|wad)$", re.I), "image de jeu"),
    (re.compile(r"(^|/)_[^/]*\.(json|log|txt)$"), "fichier d'etat de l'application"),
    (re.compile(r"(^|/)\.env$"), "fichier d'environnement"),
    (re.compile(r"\.(pem|p12|pfx|key)$", re.I), "materiel cryptographique"),
]

# --- contenus interdits -----------------------------------------------------
# Chaque motif vise une FORME d'identifiant, jamais une valeur precise : y
# ecrire les vrais secrets de quelqu'un pour les detecter serait absurde.
SECRETS = [
    (re.compile(r"""(?ix)
        \b(api[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?secret|
           password|passwd|mot[_-]?de[_-]?passe)\b
        \s*[=:]\s*
        ["'][A-Za-z0-9/+_.\-]{16,}["']
    """), "identifiant en clair"),
    (re.compile(r"\bscrypt\$\d+\$\d+\$\d+\$"), "empreinte de mot de passe"),
    # Le mot « otpauth » seul ne fuit rien : c'est un nom de format, cite dans
    # le code qui le construit et dans les tests qui le verifient. Ce qui fuit,
    # c'est une URI qui PORTE la graine.
    (re.compile(r"otpauth://[^\s\"']*secret="), "secret de double authentification"),
    (re.compile(r"(?i)\bCHANGE-MOI\b"), "identifiant d'exemple laisse en place"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "cle privee"),
]

IP_PRIVEE = re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))"
                       r"\.\d{1,3}\.\d{1,3}\b")
# Adresses citees en exemple dans la documentation et les tests.
# Adresses citees en exemple : la passerelle par defaut d'un reseau Docker
# et quelques adresses de documentation.
IP_TOLEREES = {"192.168.1.42", "192.168.1.50", "192.168.0.1", "172.18.0.1"}

BINAIRES = re.compile(r"\.(png|jpg|jpeg|gif|webp|ico|woff2?|zip|gz)$", re.I)

# Une ligne portant ce marqueur est laissee passer. Il exige une justification
# ECRITE a cote du code : c'est ce qui distingue une exception d'un oubli. Une
# liste de fichiers autorises, elle, se perime en silence.
MARQUEUR = "fuite:ok"


def fichiers_suivis(tout):
    if tout:
        return [p for p in Path(".").rglob("*")
                if p.is_file() and ".git/" not in str(p)]
    sortie = subprocess.run(["git", "ls-files", "-z"], capture_output=True)
    if sortie.returncode != 0:
        print("git ls-files a echoue : depot absent ?", file=sys.stderr)
        sys.exit(2)
    return [Path(n) for n in sortie.stdout.decode().split("\0") if n]


def examiner(chemins):
    fautes, alertes = [], []
    for p in chemins:
        rel = str(p)
        # Le detecteur est fait de motifs de secrets : s'inspecter lui-meme
        # n'aurait qu'un resultat possible.
        if rel.endswith("outils/verifier-fuite.py"):
            continue
        for motif, quoi in NOMS_INTERDITS:
            if motif.search(rel):
                fautes.append((rel, "nom interdit : %s" % quoi))
        if BINAIRES.search(rel):
            continue
        try:
            brut = p.read_bytes()
        except OSError:
            continue
        if b"\0" in brut:
            fautes.append((rel, "octet nul : git le prendra pour un binaire"))
        texte = brut.decode("utf-8", "replace")
        lignes = texte.split("\n")

        def exemptee(n):
            """Le marqueur vaut pour sa ligne ou pour celle qui la precede."""
            for i in (n - 1, n - 2):
                if 0 <= i < len(lignes) and MARQUEUR in lignes[i]:
                    return True
            return False

        for motif, quoi in SECRETS:
            for m in motif.finditer(texte):
                ligne = texte[:m.start()].count("\n") + 1
                if exemptee(ligne):
                    continue
                fautes.append(("%s:%d" % (rel, ligne), quoi))
        for m in IP_PRIVEE.finditer(texte):
            if m.group(0) in IP_TOLEREES:
                continue
            ligne = texte[:m.start()].count("\n") + 1
            if exemptee(ligne):
                continue
            alertes.append(("%s:%d" % (rel, ligne),
                            "adresse privee %s" % m.group(0)))
    return fautes, alertes


def autotest():
    """Un controle qui ne mord jamais ne protege de rien."""
    cas = [
        ("keys/prod.keys", b"peu importe", True),
        ("jeu.nsp", b"peu importe", True),
        ("_switch-config.json", b"{}", True),
        ("a.py", b'client_secret = "5atv8sim2f34pabfoik2o07ie62csa"', True),
        ("b.json", b'"mdp": "scrypt$131072$8$1$sel$empreinte"', True),
        ("c.yml", b'SWITCH_TOKEN: "CHANGE-MOI"', True),
        ("g.txt", b"otpauth://totp/App:moi?secret=JBSWY3DPEHPK3PXP", True),
        ("h.py", b'return "otpauth://totp/%s?%s" % (label, params)', False),
        ("d.js", b"const s = 'a' + '\x00' + 'b';", True),
        ("romule/__init__.py", b'__version__ = "0.1.0"', False),
        ("e.py", b'exemple = "192.168.1.42:5555"', False),
        ("f.py", b'# fuite:ok exemple de documentation\nk = "api_key: \'abcdef0123456789\'"', False),
    ]
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as d:
        for nom, contenu, doit_mordre in cas:
            f = Path(d) / nom
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(contenu)
            fautes, _ = examiner([f])
            mord = bool(fautes)
            if mord != doit_mordre:
                ok = False
                print("  ECHEC %-34s attendu %s, obtenu %s"
                      % (nom, doit_mordre, mord))
            else:
                print("  OK    %-34s %s" % (nom, "detecte" if mord else "laisse passer"))
    return 0 if ok else 1


def main(argv):
    if "--autotest" in argv:
        print("-- autotest du detecteur --")
        return autotest()
    fautes, alertes = examiner(fichiers_suivis("--tout" in argv))
    for ou, quoi in alertes:
        print("  alerte  %-52s %s" % (ou, quoi))
    for ou, quoi in fautes:
        print("  REFUS   %-52s %s" % (ou, quoi))
    if fautes:
        print("\n%d fichier(s) ne doivent pas entrer dans le depot." % len(fautes))
        return 1
    print("Aucune donnee personnelle detectee (%d alerte(s) a verifier a l'oeil)."
          % len(alertes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
