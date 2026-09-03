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
FORBIDDEN_NAMES = [
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

PRIVATE_IP = re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))"
                       r"\.\d{1,3}\.\d{1,3}\b")
# Addresses quoted as examples in the documentation and the tests: a Docker
# network's default gateway and a few documentation addresses.
ALLOWED_IPS = {"192.168.1.42", "192.168.1.50", "192.168.0.1", "172.18.0.1"}

BINARIES = re.compile(r"\.(png|jpg|jpeg|gif|webp|ico|woff2?|zip|gz)$", re.I)

# A line carrying this marker is let through. It requires a justification
# WRITTEN beside the code: that is what tells an exception from an oversight. A
# list of allowed files, on the other hand, goes stale in silence.
MARKER = "fuite:ok"


def tracked_files(every):
    if every:
        return [p for p in Path(".").rglob("*")
                if p.is_file() and ".git/" not in str(p)]
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True)
    if out.returncode != 0:
        print("git ls-files failed: no repository?", file=sys.stderr)
        sys.exit(2)
    return [Path(n) for n in out.stdout.decode().split("\0") if n]


def inspect_files(paths):
    faults, warnings = [], []
    for p in paths:
        rel = str(p)
        # The detector is made of secret patterns: inspecting itself would have
        # only one possible outcome.
        if rel.endswith("outils/verifier-fuite.py"):
            continue
        for pattern, what in FORBIDDEN_NAMES:
            if pattern.search(rel):
                faults.append((rel, "forbidden name: %s" % what))
        if BINARIES.search(rel):
            continue
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\0" in raw:
            faults.append((rel, "null byte: git will take it for a binary"))
        text = raw.decode("utf-8", "replace")
        lines = text.split("\n")

        def exempt(n, lines=lines):
            """The marker covers its own line or the one before it.

            `lines` is bound as a default: the function is indeed called within
            the same iteration, but binding it makes that guarantee visible
            rather than dependent on the order of the calls.
            """
            for i in (n - 1, n - 2):
                if 0 <= i < len(lines) and MARKER in lines[i]:
                    return True
            return False

        for pattern, what in SECRETS:
            for m in pattern.finditer(text):
                line = text[:m.start()].count("\n") + 1
                if exempt(line):
                    continue
                faults.append(("%s:%d" % (rel, line), what))
        for m in PRIVATE_IP.finditer(text):
            if m.group(0) in ALLOWED_IPS:
                continue
            line = text[:m.start()].count("\n") + 1
            if exempt(line):
                continue
            warnings.append(("%s:%d" % (rel, line),
                            "private address %s" % m.group(0)))
    return faults, warnings


def autotest():
    """A check that never bites protects against nothing."""
    cases = [
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
        for name, content, should_bite in cases:
            f = Path(d) / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(content)
            faults, _ = inspect_files([f])
            bites = bool(faults)
            if bites != should_bite:
                ok = False
                print("  FAIL  %-34s expected %s, got %s"
                      % (name, should_bite, bites))
            else:
                print("  OK    %-34s %s" % (name, "detected" if bites else "let through"))
    return 0 if ok else 1


def main(argv):
    if "--autotest" in argv:
        print("-- self-test of the detector --")
        return autotest()
    faults, warnings = inspect_files(tracked_files("--tout" in argv))
    for where, what in warnings:
        print("  warning %-52s %s" % (where, what))
    for where, what in faults:
        print("  REFUSED %-52s %s" % (where, what))
    if faults:
        print("\n%d file(s) must not enter the repository." % len(faults))
        return 1
    print("No personal data detected (%d warning(s) to check by eye)."
          % len(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
