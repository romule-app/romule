"""API keys — named tokens, revocable one at a time.

Romule already had `ROMULE_TOKEN`: ONE secret, every right, which cannot be
named or revoked without changing it for everybody. It stays, because it solves
a different problem — opening the interface to a browser with no account.

An API key solves this one: giving a dashboard, a backup script or a scheduled
job an access that can be withdrawn on its own, and whose last use is visible.

Three choices that are not obvious
----------------------------------

**The `rml_` prefix is not decorative.** It makes a key recognisable in a log,
a configuration file or a public repository. It is what lets a reader — human
or machine — say "this is a secret" without knowing Romule. GitHub and Stripe
do it for that reason.

**SHA-256, and above all not `accounts.hash_password()`.** The project hashes passwords
with scrypt N=2^17, about 128 MiB of memory per computation. That is deliberate
and correct: a password is chosen by a human, therefore guessable, and every
attempt must be made expensive.

An API key is not that. It is a RANDOM 256-bit secret: there is nothing to
guess, and no amount of computation adds security. A key is, on the other hand,
presented on EVERY request — a dashboard polling every thirty seconds would on
its own allocate 128 MiB per poll. The hardening would turn into a way of
bringing the server to its knees.

**Lookup is by prefix.** Comparing the presented key against every stored
digest would cost a full scan on each request. The first twelve characters
identify the key; the digest, compared in constant time, decides.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

from . import config

FILE = config.state_file("_romule-cles.json", "_romule-cles.json")

# `rml_` + 43 base64url characters (32 bytes). The displayed prefix covers the
# marker and the first eight characters of the secret: enough to recognise a
# key in a list, far too little to rebuild it.
PREFIX_MARK = "rml_"
_SIZE = 32
_PREFIX_LEN = 12

_LOCK = threading.RLock()


# ------------------------------------------------------------------ stockage

def _read():
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "cles": []}
    if not isinstance(d, dict) or not isinstance(d.get("cles"), list):
        return {"version": 1, "cles": []}
    return d


def _write(d):
    """Atomic write in 0600, like the accounts file: a digest must only be
    readable by the system account running Romule."""
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FILE)


def _digest(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# -------------------------------------------------------------------- lecture

def _public(k):
    """What may be shown. The digest is not part of it: it does not reveal the
    key, but it would allow VERIFYING one offline — that is, testing a list of
    candidates without going through the server."""
    return {"id": k["id"], "nom": k["nom"], "prefixe": k["prefixe"],
            "cree": k["cree"], "dernier_usage": k.get("dernier_usage"),
            "revoquee": bool(k.get("revoquee"))}


def list_all(with_revoked=False):
    cles = _read()["cles"]
    return [_public(k) for k in cles
            if with_revoked or not k.get("revoquee")]


def count():
    return len([k for k in _read()["cles"] if not k.get("revoquee")])


# -------------------------------------------------------------------- ecriture

def create(name):
    """Rend (fiche_publique, cle_en_clair).

    The plaintext key is returned HERE and nowhere else: it is stored nowhere,
    and the caller is the only one able to show it. That is what makes a leak
    of the state file harmless for the keys themselves.
    """
    name = (name or "").strip()[:60] or "sans nom"
    key = PREFIX_MARK + secrets.token_urlsafe(_SIZE)
    with _LOCK:
        d = _read()
        fiche = {"id": secrets.token_hex(8),
                 "nom": name,
                 "prefixe": key[:_PREFIX_LEN],
                 "empreinte": _digest(key),
                 "cree": int(time.time()),
                 "dernier_usage": None,
                 "revoquee": False}
        d["cles"].append(fiche)
        _write(d)
    return _public(fiche), key


def revoke(cid):
    """Revoke rather than delete: the name and the last-used date stay
    readable. "Did this key get used after I withdrew it?" is a question you
    ask afterwards, not before."""
    with _LOCK:
        d = _read()
        for k in d["cles"]:
            if k["id"] == cid and not k.get("revoquee"):
                k["revoquee"] = True
                k["revoquee_le"] = int(time.time())
                _write(d)
                return True
    return False


def rename(cid, name):
    name = (name or "").strip()[:60]
    if not name:
        return False
    with _LOCK:
        d = _read()
        for k in d["cles"]:
            if k["id"] == cid:
                k["nom"] = name
                _write(d)
                return True
    return False


# ---------------------------------------------------------------- verification

def verify(presented):
    """Return the public record if the key is valid, otherwise None.

    The last-used date is written at most once a minute: without that, a
    dashboard poll would rewrite the file on every call.
    """
    if not presented or not isinstance(presented, str):
        return None
    presented = presented.strip()
    if not presented.startswith(PREFIX_MARK):
        return None
    prefixe = presented[:_PREFIX_LEN]
    emp = _digest(presented)
    with _LOCK:
        d = _read()
        for k in d["cles"]:
            if k.get("revoquee") or k.get("prefixe") != prefixe:
                continue
            # Constant time: an ordinary comparison stops at the first
            # differing character, and the response TIME then tells how many
            # characters were right.
            if not hmac.compare_digest(k.get("empreinte", ""), emp):
                continue
            maintenant = int(time.time())
            if maintenant - (k.get("dernier_usage") or 0) >= 60:
                k["dernier_usage"] = maintenant
                try:
                    _write(d)
                except OSError:
                    pass          # a full disk must not close the API
            return _public(k)
    return None
