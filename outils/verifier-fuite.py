#!/usr/bin/env python3
"""Refuse to let personal data enter the repository.

This project was born INSIDE its author's games folder: the code, the ROMs, the
console keys and the API credentials lived together for a long time. The public
repository was extracted by hand, but "by hand" is not a guarantee that holds
over time.

This script makes one: it inspects what git is about to track — not the disk, the
INDEX — and refuses three things.

  * a forbidden file NAME: a console key, a game image, a state file;
  * CONTENT that looks like a credential: an API key, a secret, a token;
  * a null byte, which would make git and grep take a source file for a binary
    (it has already happened to `app.js`).

Private IP addresses are reported without blocking: the code legitimately holds
some as documentation examples, and only a human can tell "192.168.1.42" from a
real console address.

    python3 outils/verifier-fuite.py            # what git tracks
    python3 outils/verifier-fuite.py --tout     # the whole working tree
    python3 outils/verifier-fuite.py --autotest # checks the script bites

Exits 0 if nothing, 1 otherwise. Usable as a pre-commit hook and in CI.
"""

import re
import subprocess
import sys
from pathlib import Path

# --- noms interdits ---------------------------------------------------------
NOMS_INTERDITS = [
    (re.compile(r"(^|/)(prod|title|dev)\.keys$", re.I), "console key"),
    (re.compile(r"\.(nsp|nsz|xci|xcz|iso|wbfs|rvz|chd|cia|gba|nds|3ds|sfc|smc|"
                r"n64|z64|gen|wad)$", re.I), "game image"),
    (re.compile(r"(^|/)_[^/]*\.(json|log|txt)$"), "application state file"),
    (re.compile(r"(^|/)\.env$"), "environment file"),
    (re.compile(r"\.(pem|p12|pfx|key)$", re.I), "cryptographic material"),
]

# --- forbidden content ------------------------------------------------------
# Every pattern targets a SHAPE of credential, never a precise value: writing
# someone's real secrets in here in order to detect them would be absurd.
SECRETS = [
    (re.compile(r"""(?ix)
        \b(api[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?secret|
           password|passwd|mot[_-]?de[_-]?passe)\b
        \s*[=:]\s*
        ["'][A-Za-z0-9/+_.\-]{16,}["']
    """), "credential in the clear"),
    (re.compile(r"\bscrypt\$\d+\$\d+\$\d+\$"), "password hash"),
    # The word "otpauth" on its own leaks nothing: it is a format name, quoted
    # in the code that builds it and in the tests that check it. What leaks is a
    # URI that CARRIES the seed.
    (re.compile(r"otpauth://[^\s\"']*secret="), "two-factor secret"),
    (re.compile(r"(?i)\bCHANGE-MOI\b"), "example credential left in place"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
]

IP_PRIVEE = re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))"
                       r"\.\d{1,3}\.\d{1,3}\b")
# Addresses quoted as examples in the documentation and the tests: a Docker
# network's default gateway and a few documentation addresses.
IP_TOLEREES = {"192.168.1.42", "192.168.1.50", "192.168.0.1", "172.18.0.1"}

BINAIRES = re.compile(r"\.(png|jpg|jpeg|gif|webp|ico|woff2?|zip|gz)$", re.I)

# A line carrying this marker is let through. It requires a justification
# WRITTEN beside the code: that is what tells an exception from an oversight. A
# list of allowed files, on the other hand, goes stale in silence.
MARQUEUR = "fuite:ok"


def fichiers_suivis(tout):
    if tout:
        return [p for p in Path(".").rglob("*")
                if p.is_file() and ".git/" not in str(p)]
    sortie = subprocess.run(["git", "ls-files", "-z"], capture_output=True)
    if sortie.returncode != 0:
        print("git ls-files failed: no repository?", file=sys.stderr)
        sys.exit(2)
    return [Path(n) for n in sortie.stdout.decode().split("\0") if n]


def examiner(chemins):
    fautes, alertes = [], []
    for p in chemins:
        rel = str(p)
        # The detector is made of secret patterns: inspecting itself would have
        # only one possible outcome.
        if rel.endswith("outils/verifier-fuite.py"):
            continue
        for motif, quoi in NOMS_INTERDITS:
            if motif.search(rel):
                fautes.append((rel, "forbidden name: %s" % quoi))
        if BINAIRES.search(rel):
            continue
        try:
            brut = p.read_bytes()
        except OSError:
            continue
        if b"\0" in brut:
            fautes.append((rel, "null byte: git will take it for a binary"))
        texte = brut.decode("utf-8", "replace")
        lignes = texte.split("\n")

        def exemptee(n, lignes=lignes):
            """The marker covers its own line or the one before it.

            `lignes` is bound as a default: the function is indeed called within
            the same iteration, but binding it makes that guarantee visible
            rather than dependent on the order of the calls.
            """
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
                            "private address %s" % m.group(0)))
    return fautes, alertes


def autotest():
    """A check that never bites protects against nothing."""
    cas = [
        ("keys/prod.keys", b"never mind", True),
        ("jeu.nsp", b"peu importe", True),
        ("_romule-config.json", b"{}", True),
        ("_romule-comptes.json", b"{}", True),
        ("a.py", b'client_secret = "5atv8sim2f34pabfoik2o07ie62csa"', True),
        ("b.json", b'"mdp": "scrypt$131072$8$1$sel$empreinte"', True),
        ("c.yml", b'ROMULE_TOKEN: "CHANGE-MOI"', True),
        ("g.txt", b"otpauth://totp/App:moi?secret=JBSWY3DPEHPK3PXP", True),
        ("h.py", b'return "otpauth://totp/%s?%s" % (label, params)', False),
        ("d.js", b"const s = 'a' + '\x00' + 'b';", True),
        ("romule/__init__.py", b'__version__ = "0.1.0"', False),
        ("e.py", b'exemple = "192.168.1.42:5555"', False),
        ("f.py", b'# fuite:ok a documentation example\nk = "api_key: \'abcdef0123456789\'"', False),
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
                print("  FAIL  %-34s expected %s, got %s"
                      % (nom, doit_mordre, mord))
            else:
                print("  OK    %-34s %s" % (nom, "detected" if mord else "let through"))
    return 0 if ok else 1


def main(argv):
    if "--autotest" in argv:
        print("-- self-test of the detector --")
        return autotest()
    fautes, alertes = examiner(fichiers_suivis("--tout" in argv))
    for ou, quoi in alertes:
        print("  warning %-52s %s" % (ou, quoi))
    for ou, quoi in fautes:
        print("  REFUSED %-52s %s" % (ou, quoi))
    if fautes:
        print("\n%d file(s) must not enter the repository." % len(fautes))
        return 1
    print("No personal data detected (%d warning(s) to check by eye)."
          % len(alertes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
