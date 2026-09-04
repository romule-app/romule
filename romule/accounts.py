"""Internal accounts: email plus password, with no dependency at all.

The alternative to SSO for anyone not running an OIDC provider. The security
choices follow current guidance (NIST SP 800-63B, OWASP ASVS v4 chapter 2):

  * `scrypt` digests — a memory-hard function, far more expensive to attack
    with a GPU than a plain SHA; a random salt per account, and the parameters
    stored alongside the digest so they can be hardened later without breaking
    existing accounts;
  * constant-time comparison, and a decoy digest computed when the email is
    unknown: the response time does not reveal whether an account exists;
  * one single error message for "unknown email" and "wrong password";
  * exponential backoff after repeated failures, counted both per account
    (persisted to disk, so a restart does not clear it) and per IP address;
  * a password rule based on length and on refusing common passwords, with no
    special-character requirement and no expiry — both of those practices are
    now discouraged;
  * changing a password invalidates every session open elsewhere.

The accounts file is separate from the configuration: it must never travel in
a settings backup nor be shown in the interface. It is written 0600, and the
photo folder 0700.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import unicodedata

from . import config

FILE = config.fichier_etat("_romule-comptes.json", "_switch-comptes.json")
PHOTOS = config.ROOT / "_comptes"

# Parameters recommended by OWASP (Password Storage Cheat Sheet): N=2^17,
# r=8, p=1 — 128 MB of memory and about 200 ms per computation on a recent Mac.
# The memory cost is what matters: it makes a mass GPU attack far more
# expensive than a plain SHA, whatever the number of attempts. The parameters
# are written INSIDE the digest: raising them later invalidates no existing
# account.
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2 ** 17, 8, 1, 32
SCRYPT_MAXMEM = 192 * 1024 * 1024

MDP_MIN, MDP_MAX = 12, 128
PHOTO_MAX = 2 * 1024 * 1024

# The threshold at which we start delaying, and the ceiling on that delay.
FAILURES_BEFORE_WAIT = 3
MAX_WAIT = 15 * 60

_LOCK = threading.RLock()
_IP_FAILURES = {}                # {ip: (nombre, jusqu_a)} — memoire seule

# The passwords most common in public breaches. The list is deliberately
# short: it stops the most obvious choices without pretending to replace a
# service like "Have I Been Pwned".
COMMON_PASSWORDS = {
    "password", "motdepasse", "123456", "12345678", "123456789", "1234567890",
    "azertyuiop", "qwertyuiop", "azerty123", "qwerty123", "motdepasse1",
    "password1", "password123", "administrateur", "administrator", "iloveyou",
    "bonjour123", "changeme", "letmein", "welcome1", "monmotdepasse",
    "abcd1234", "1qaz2wsx", "passw0rd", "p@ssw0rd", "motdepasse123",
    "nintendo", "nintendoswitch", "switch123", "ludotheque",
}


# ------------------------------------------------------------------ stockage

def _read():
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "comptes": []}
    if not isinstance(d, dict) or not isinstance(d.get("comptes"), list):
        return {"version": 1, "comptes": []}
    return d


def _write(d):
    """Atomic write, 0600: the digests must only be readable by the system
    account running the server."""
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FILE)


def count():
    return len(_read()["comptes"])


def _public(u):
    return {"id": u["id"], "email": u["email"], "nom": u.get("nom") or u["email"],
            "photo": bool(u.get("photo")), "cree": u.get("cree", 0),
            "derniere": u.get("derniere", 0),
            "admin": bool(u.get("admin")),
            "double_facteur": bool((u.get("totp") or {}).get("actif"))}


def list_all():
    """The existing accounts, with nothing password-related."""
    return [_public(u) for u in _read()["comptes"]]


def by_id(uid):
    for u in _read()["comptes"]:
        if u["id"] == uid:
            return u
    return None


def is_admin(uid):
    u = by_id(uid)
    return bool(u and u.get("admin"))


def set_admin(uid, admin=True):
    """Grant or withdraw the administrator role."""
    with _LOCK:
        d = _read()
        for u in d["comptes"]:
            if u["id"] == uid:
                if not admin and not any(
                        v.get("admin") for v in d["comptes"] if v["id"] != uid):
                    raise ValueError("Il doit rester au moins un administrateur.")
                u["admin"] = bool(admin)
                _write(d)
                return _public(u)
    raise ValueError("Compte introuvable.")


def refresh_roles():
    """Accounts created before roles existed carry none.

    Without this catch-up, an existing installation would find itself with no
    administrator at all after the upgrade: nobody could touch the settings any
    more. The oldest account, the installer's, becomes one.
    """
    with _LOCK:
        d = _read()
        if not d["comptes"] or any(u.get("admin") for u in d["comptes"]):
            return
        plus_ancien = min(d["comptes"], key=lambda u: u.get("cree", 0))
        plus_ancien["admin"] = True
        _write(d)


def _email_index(d, email):
    for i, u in enumerate(d["comptes"]):
        if u["email"] == email:
            return i
    return -1


# ------------------------------------------------------------ mots de passe

def _normalise(password):
    """NFKC: an "e-acute" typed directly or composed yields the same digest."""
    return unicodedata.normalize("NFKC", password or "")


# scrypt at N=2^17 uses about 128 MiB per computation. That is deliberate: it
# is what makes an offline attack expensive. But nothing limited the number of
# SIMULTANEOUS computations — a handful of parallel login attempts was enough
# to exhaust the server's memory, turning a protection into a lever. Two at a
# time: enough not to slow normal use, few enough that the worst case stays
# bounded.
_SCRYPT_SLOTS = threading.BoundedSemaphore(
    int(config.env("SCRYPT_PARALLELE", "2")))


def hash_password(password):
    sel = secrets.token_bytes(16)
    with _SCRYPT_SLOTS:
        dk = hashlib.scrypt(_normalise(password).encode("utf-8"), salt=sel,
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                            dklen=SCRYPT_LEN, maxmem=SCRYPT_MAXMEM)
    return "scrypt$%d$%d$%d$%s$%s" % (
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(sel).decode(), base64.b64encode(dk).decode())


def verify_password(password, digest):
    """Constant-time comparison. False for any unreadable digest."""
    try:
        algo, n, r, p, sel, dk = str(digest).split("$")
        if algo != "scrypt":
            return False
        attendu = base64.b64decode(dk)
        with _SCRYPT_SLOTS:
            calcule = hashlib.scrypt(
                _normalise(password).encode("utf-8"), salt=base64.b64decode(sel),
                n=int(n), r=int(r), p=int(p), dklen=len(attendu),
                maxmem=SCRYPT_MAXMEM)
    except Exception:
        return False
    return hmac.compare_digest(calcule, attendu)


# A throwaway digest, computed once: it keeps the processor busy for as long
# on an unknown email as on a known one.
_DECOY = None


def _spend_time(password):
    global _DECOY
    if _DECOY is None:
        _DECOY = hash_password(secrets.token_urlsafe(32))
    verify_password(password, _DECOY)


def check_password(password, email=""):
    """Raise ValueError with a displayable message if the password will not do."""
    password = _normalise(password)
    if len(password) < MDP_MIN:
        raise ValueError("Le mot de passe doit faire au moins %d caracteres."
                         % MDP_MIN)
    if len(password) > MDP_MAX:
        raise ValueError("Le mot de passe ne peut pas depasser %d caracteres."
                         % MDP_MAX)
    bas = password.lower()
    if bas in COMMON_PASSWORDS:
        raise ValueError("Ce mot de passe figure parmi les plus utilises : "
                         "choisis-en un autre.")
    # A password made of the same letter repeated passes the length rule and
    # is worth nothing.
    if len(set(bas)) < 5:
        raise ValueError("Ce mot de passe est trop repetitif.")
    local = (email or "").split("@")[0].lower()
    if len(local) >= 4 and local in bas:
        raise ValueError("Le mot de passe ne doit pas contenir ton adresse email.")
    return password


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


def check_email(email):
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e) or len(e) > 254:
        raise ValueError("Adresse email invalide.")
    return e


# ------------------------------------------------------------- temporisation

def _wait_for(failures):
    """1st, 2nd, 3rd attempt: free. Then 2 s, 4 s, 8 s... up to the ceiling."""
    if failures < FAILURES_BEFORE_WAIT:
        return 0
    return min(2 ** (failures - FAILURES_BEFORE_WAIT + 1), MAX_WAIT)


def _remaining(until):
    return max(0, int(until - time.time()))


def _refuse_for(seconds):
    if seconds >= 60:
        duree = "%d minute(s)" % ((seconds + 59) // 60)
    else:
        duree = "%d seconde(s)" % seconds
    return ValueError("Trop de tentatives. Reessaie dans %s." % duree)


def _ip_lock(ip):
    n, until = _IP_FAILURES.get(ip or "?", (0, 0))
    return _remaining(until)


def _ip_failure(ip):
    ip = ip or "?"
    n = _IP_FAILURES.get(ip, (0, 0))[0] + 1
    _IP_FAILURES[ip] = (n, time.time() + _wait_for(n))


# ----------------------------------------------------------------- operations

def create(email, password, name="", cfg=None):
    """Create an account. Raises ValueError if the email is taken or the password weak."""
    email = check_email(email)
    check_password(password, email)
    with _LOCK:
        d = _read()
        if _email_index(d, email) >= 0:
            raise ValueError("Un compte existe deja avec cette adresse.")
        # The FIRST account is the administrator. That is the convention among
        # self-hosted tools (Jellyfin, Immich, Paperless): whoever installs it
        # governs. With no roles at all, any user could delete the others or
        # switch authentication off.
        premier = not d["comptes"]
        u = {"id": secrets.token_urlsafe(9), "email": email,
             "nom": (name or "").strip()[:80] or email.split("@")[0],
             "hash": hash_password(password), "cree": int(time.time()),
             "maj_mdp": int(time.time()), "echecs": 0, "bloque": 0,
             "photo": "", "derniere": 0, "admin": premier}
        d["comptes"].append(u)
        _write(d)
    return _public(u)


class CodeNeeded(ValueError):
    """Password correct, but the second factor is missing or does not match.

    A distinct exception: the form must then ask for the code without making
    the user retype the password. It is only raised after the password has been
    verified, so it reveals the existence of no account.
    """


def totp_prepare(uid):
    """Create a secret, not yet active: it only becomes so once a valid code
    has been supplied. Without that step, a mis-configured app would lock the
    account out."""
    from . import totp
    with _LOCK:
        d = _read()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            secret = totp.new_secret()
            d["comptes"][i]["totp"] = {"secret": secret, "actif": False, "utilises": []}
            _write(d)
            return {"secret": secret, "lisible": totp.readable(secret),
                    "uri": totp.uri(secret, u["email"])}
    raise ValueError("Compte introuvable.")


def totp_enable(uid, entered):
    from . import totp
    with _LOCK:
        d = _read()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            conf = u.get("totp") or {}
            if not conf.get("secret"):
                raise ValueError("Commence par générer un secret.")
            bon, counter = totp.verify(conf["secret"], entered,
                                        used=set(conf.get("utilises") or []))
            if not bon:
                raise ValueError("Code incorrect. Vérifie l'heure de ton téléphone.")
            conf.update({"actif": True, "utilises": [counter]})
            d["comptes"][i]["totp"] = conf
            _write(d)
            return True
    raise ValueError("Compte introuvable.")


def totp_disable(uid, password):
    """Requires the password: removing a factor is a weakening."""
    with _LOCK:
        d = _read()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            if not verify_password(password, u["hash"]):
                raise ValueError("Mot de passe incorrect.")
            d["comptes"][i]["totp"] = {}
            _write(d)
            return True
    raise ValueError("Compte introuvable.")


def totp_active(u):
    return bool((u or {}).get("totp", {}).get("actif"))


def _consume_code(email, counter):
    """Record the counter used, so the same code cannot be replayed."""
    with _LOCK:
        d = _read()
        i = _email_index(d, email)
        if i < 0:
            return
        conf = d["comptes"][i].get("totp") or {}
        vus = [c for c in (conf.get("utilises") or []) if c > counter - 10]
        vus.append(counter)
        conf["utilises"] = vus[-10:]
        d["comptes"][i]["totp"] = conf
        _write(d)


def login(email, password, ip="", code=""):
    """Return the account if the credentials are right, else raise ValueError.

    The error message is the same for an unknown email and a wrong password:
    giving a different message amounts to publishing the list of accounts.
    """
    reste = _ip_lock(ip)
    if reste:
        raise _refuse_for(reste)
    email = (email or "").strip().lower()
    with _LOCK:
        d = _read()
        i = _email_index(d, email)
        u = d["comptes"][i] if i >= 0 else None
        if u:
            attente = _remaining(u.get("bloque", 0))
            if attente:
                raise _refuse_for(attente)

    if not u:
        _spend_time(password)          # same cost as for a real account
        _ip_failure(ip)
        raise ValueError("Email ou mot de passe incorrect.")

    if not verify_password(password, u["hash"]):
        _ip_failure(ip)
        with _LOCK:
            d = _read()
            i = _email_index(d, email)
            if i >= 0:
                n = d["comptes"][i].get("echecs", 0) + 1
                d["comptes"][i]["echecs"] = n
                d["comptes"][i]["bloque"] = time.time() + _wait_for(n)
                _write(d)
        raise ValueError("Email ou mot de passe incorrect.")

    # Password valid. If a second factor exists, it is still to be cleared:
    # the failure counters are therefore not reset yet.
    if totp_active(u):
        from . import totp
        bon, counter = totp.verify(u["totp"]["secret"], code,
                                    used=set(u["totp"].get("utilises") or []))
        if not bon:
            _ip_failure(ip)
            raise CodeNeeded("Code à usage unique requis." if not code
                             else "Code incorrect ou déjà utilisé.")
        _consume_code(email, counter)

    with _LOCK:
        d = _read()
        i = _email_index(d, email)
        if i >= 0:
            d["comptes"][i]["echecs"] = 0
            d["comptes"][i]["bloque"] = 0
            d["comptes"][i]["derniere"] = int(time.time())
            _write(d)
            u = d["comptes"][i]
    _IP_FAILURES.pop(ip or "?", None)
    return u


def change_password(uid, old, new):
    """Requires the current password: a stolen cookie must not be enough to
    take the account for good."""
    with _LOCK:
        d = _read()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            if not verify_password(old, u["hash"]):
                raise ValueError("Mot de passe actuel incorrect.")
            check_password(new, u["email"])
            if verify_password(new, u["hash"]):
                raise ValueError("Le nouveau mot de passe est identique a l'ancien.")
            d["comptes"][i]["hash"] = hash_password(new)
            # Move the account's epoch: every session signed before this
            # instant stops being valid (see auth.session).
            d["comptes"][i]["maj_mdp"] = int(time.time())
            _write(d)
            return _public(d["comptes"][i])
    raise ValueError("Compte introuvable.")


def reset_password(email, new):
    """Reset the password WITHOUT knowing the old one. From the terminal only.

    This is the way back in for a locked-out administrator: no password left,
    no second factor, and nobody else to promote an account.
    The only alternative was editing `_romule-comptes.json` by hand — that is,
    pasting an scrypt digest computed elsewhere, which nobody gets right first
    time.

    It is reachable ONLY from the command line, never through an HTTP route: a
    reset with no proof of identity is exactly what an attacker wants. Whoever
    can run `romule` already has the service's rights, hence access to the
    accounts file: the command grants nothing the filesystem did not already
    grant, it merely makes it doable without mistakes.
    """
    email = check_email(email)
    check_password(new, email)
    with _LOCK:
        d = _read()
        i = _email_index(d, email)
        if i < 0:
            raise ValueError("Aucun compte avec cette adresse.")
        d["comptes"][i]["hash"] = hash_password(new)
        # Cut every open session: if the account was taken over, reclaiming it
        # must not leave the other party logged in.
        d["comptes"][i]["maj_mdp"] = int(time.time())
        # An account locked by repeated failures must be released: otherwise
        # the reset succeeds and the login fails anyway.
        d["comptes"][i]["echecs"] = 0
        d["comptes"][i]["bloque"] = 0
        _write(d)
        return _public(d["comptes"][i])


def disable_totp(email):
    """Remove the second factor. For a lost phone, from the terminal.

    `totp_desactiver()` requires the password, which is right from the
    interface. Here we are already on the machine: requiring the password would
    add no proof, and requiring it for an account whose second factor has just
    been lost would lock the user out for good.
    """
    email = check_email(email)
    with _LOCK:
        d = _read()
        i = _email_index(d, email)
        if i < 0:
            raise ValueError("Aucun compte avec cette adresse.")
        avait = bool((d["comptes"][i].get("totp") or {}).get("actif"))
        # `{}` rather than a removed key: that is what `totp_desactiver`
        # already does, and two representations of the same state always end up
        # diverging somewhere.
        d["comptes"][i]["totp"] = {}
        _write(d)
        return avait


def by_email(email):
    """The account bearing this address, or None. For the command line."""
    d = _read()
    i = _email_index(d, check_email(email))
    return _public(d["comptes"][i]) if i >= 0 else None


def update(uid, name=None, email=None):
    with _LOCK:
        d = _read()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            if name is not None:
                d["comptes"][i]["nom"] = str(name).strip()[:80] or u["email"].split("@")[0]
            if email is not None:
                e = check_email(email)
                j = _email_index(d, e)
                if j >= 0 and j != i:
                    raise ValueError("Un compte existe deja avec cette adresse.")
                d["comptes"][i]["email"] = e
            _write(d)
            return _public(d["comptes"][i])
    raise ValueError("Compte introuvable.")


def delete(uid):
    """Refuses to delete the last account: nobody could get in any more."""
    with _LOCK:
        d = _read()
        if len(d["comptes"]) <= 1:
            raise ValueError("C'est le dernier compte : il doit rester quelqu'un "
                             "pour se connecter.")
        reste = [u for u in d["comptes"] if u["id"] != uid]
        if len(reste) == len(d["comptes"]):
            raise ValueError("Compte introuvable.")
        # "Someone must remain" is not enough: someone WHO CAN ADMINISTER
        # must remain. Otherwise the settings become unreachable without
        # editing the accounts file by hand.
        if not any(u.get("admin") for u in reste):
            raise ValueError("C'est le dernier administrateur : promeus "
                             "quelqu'un d'autre avant de le supprimer.")
        d["comptes"] = reste
        _write(d)
    for ext in (".png", ".jpg", ".gif", ".webp"):
        p = PHOTOS / (uid + ext)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    return True


# ---------------------------------------------------------------- photo

# We do not trust the type the browser announces: we read the first bytes. A
# file renamed to .png will not get through.
SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
    (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
    (b"GIF87a", ".gif", "image/gif"),
    (b"GIF89a", ".gif", "image/gif"),
]


def _image_type(data):
    for magie, ext, mime in SIGNATURES:
        if data.startswith(magie):
            return ext, mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None, None


def photo_write(uid, data):
    if len(data) > PHOTO_MAX:
        raise ValueError("Image trop lourde (maximum %d Mo)." % (PHOTO_MAX // 2 ** 20))
    ext, mime = _image_type(data or b"")
    if not ext:
        raise ValueError("Format d'image non reconnu (PNG, JPEG, GIF ou WebP).")
    with _LOCK:
        d = _read()
        i = next((k for k, u in enumerate(d["comptes"]) if u["id"] == uid), -1)
        if i < 0:
            raise ValueError("Compte introuvable.")
        PHOTOS.mkdir(parents=True, exist_ok=True)
        os.chmod(PHOTOS, 0o700)
        for vieux in (".png", ".jpg", ".gif", ".webp"):
            p = PHOTOS / (uid + vieux)
            if p.exists() and vieux != ext:
                try:
                    p.unlink()
                except OSError:
                    pass
        (PHOTOS / (uid + ext)).write_bytes(data)
        d["comptes"][i]["photo"] = uid + ext
        _write(d)
    return {"photo": uid + ext, "type": mime}


def photo_read(uid):
    """(octets, type) de la photo, ou (None, None)."""
    u = by_id(uid)
    name = (u or {}).get("photo") or ""
    if not name:
        return None, None
    p = PHOTOS / name
    # The name comes from the accounts file, but we check all the same that it
    # stays inside the intended folder.
    try:
        p.resolve().relative_to(PHOTOS.resolve())
    except (ValueError, OSError):
        return None, None
    if not p.exists():
        return None, None
    _, mime = _image_type(p.read_bytes()[:16])
    return p.read_bytes(), mime or "application/octet-stream"


def photo_delete(uid):
    with _LOCK:
        d = _read()
        for i, u in enumerate(d["comptes"]):
            if u["id"] == uid:
                name = u.get("photo") or ""
                d["comptes"][i]["photo"] = ""
                _write(d)
                if name:
                    try:
                        (PHOTOS / name).unlink()
                    except OSError:
                        pass
                return True
    return False
