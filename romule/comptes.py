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

FICHIER = config.fichier_etat("_romule-comptes.json", "_switch-comptes.json")
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
ECHECS_AVANT_ATTENTE = 3
ATTENTE_MAX = 15 * 60

_LOCK = threading.RLock()
_ECHECS_IP = {}                # {ip: (nombre, jusqu_a)} — memoire seule

# The passwords most common in public breaches. The list is deliberately
# short: it stops the most obvious choices without pretending to replace a
# service like "Have I Been Pwned".
COURANTS = {
    "password", "motdepasse", "123456", "12345678", "123456789", "1234567890",
    "azertyuiop", "qwertyuiop", "azerty123", "qwerty123", "motdepasse1",
    "password1", "password123", "administrateur", "administrator", "iloveyou",
    "bonjour123", "changeme", "letmein", "welcome1", "monmotdepasse",
    "abcd1234", "1qaz2wsx", "passw0rd", "p@ssw0rd", "motdepasse123",
    "nintendo", "nintendoswitch", "switch123", "ludotheque",
}


# ------------------------------------------------------------------ stockage

def _lire():
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "comptes": []}
    if not isinstance(d, dict) or not isinstance(d.get("comptes"), list):
        return {"version": 1, "comptes": []}
    return d


def _ecrire(d):
    """Atomic write, 0600: the digests must only be readable by the system
    account running the server."""
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FICHIER)


def nombre():
    return len(_lire()["comptes"])


def _public(u):
    return {"id": u["id"], "email": u["email"], "nom": u.get("nom") or u["email"],
            "photo": bool(u.get("photo")), "cree": u.get("cree", 0),
            "derniere": u.get("derniere", 0),
            "admin": bool(u.get("admin")),
            "double_facteur": bool((u.get("totp") or {}).get("actif"))}


def liste():
    """The existing accounts, with nothing password-related."""
    return [_public(u) for u in _lire()["comptes"]]


def par_id(uid):
    for u in _lire()["comptes"]:
        if u["id"] == uid:
            return u
    return None


def est_admin(uid):
    u = par_id(uid)
    return bool(u and u.get("admin"))


def promouvoir(uid, admin=True):
    """Grant or withdraw the administrator role."""
    with _LOCK:
        d = _lire()
        for u in d["comptes"]:
            if u["id"] == uid:
                if not admin and not any(
                        v.get("admin") for v in d["comptes"] if v["id"] != uid):
                    raise ValueError("Il doit rester au moins un administrateur.")
                u["admin"] = bool(admin)
                _ecrire(d)
                return _public(u)
    raise ValueError("Compte introuvable.")


def reprendre_roles():
    """Accounts created before roles existed carry none.

    Without this catch-up, an existing installation would find itself with no
    administrator at all after the upgrade: nobody could touch the settings any
    more. The oldest account, the installer's, becomes one.
    """
    with _LOCK:
        d = _lire()
        if not d["comptes"] or any(u.get("admin") for u in d["comptes"]):
            return
        plus_ancien = min(d["comptes"], key=lambda u: u.get("cree", 0))
        plus_ancien["admin"] = True
        _ecrire(d)


def _index_email(d, email):
    for i, u in enumerate(d["comptes"]):
        if u["email"] == email:
            return i
    return -1


# ------------------------------------------------------------ mots de passe

def _normaliser(mdp):
    """NFKC: an "e-acute" typed directly or composed yields the same digest."""
    return unicodedata.normalize("NFKC", mdp or "")


# scrypt at N=2^17 uses about 128 MiB per computation. That is deliberate: it
# is what makes an offline attack expensive. But nothing limited the number of
# SIMULTANEOUS computations — a handful of parallel login attempts was enough
# to exhaust the server's memory, turning a protection into a lever. Two at a
# time: enough not to slow normal use, few enough that the worst case stays
# bounded.
_PLACES_SCRYPT = threading.BoundedSemaphore(
    int(config.env("SCRYPT_PARALLELE", "2")))


def hacher(mdp):
    sel = secrets.token_bytes(16)
    with _PLACES_SCRYPT:
        dk = hashlib.scrypt(_normaliser(mdp).encode("utf-8"), salt=sel,
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                            dklen=SCRYPT_LEN, maxmem=SCRYPT_MAXMEM)
    return "scrypt$%d$%d$%d$%s$%s" % (
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(sel).decode(), base64.b64encode(dk).decode())


def verifier_mdp(mdp, empreinte):
    """Constant-time comparison. False for any unreadable digest."""
    try:
        algo, n, r, p, sel, dk = str(empreinte).split("$")
        if algo != "scrypt":
            return False
        attendu = base64.b64decode(dk)
        with _PLACES_SCRYPT:
            calcule = hashlib.scrypt(
                _normaliser(mdp).encode("utf-8"), salt=base64.b64decode(sel),
                n=int(n), r=int(r), p=int(p), dklen=len(attendu),
                maxmem=SCRYPT_MAXMEM)
    except Exception:
        return False
    return hmac.compare_digest(calcule, attendu)


# A throwaway digest, computed once: it keeps the processor busy for as long
# on an unknown email as on a known one.
_LEURRE = None


def _perdre_du_temps(mdp):
    global _LEURRE
    if _LEURRE is None:
        _LEURRE = hacher(secrets.token_urlsafe(32))
    verifier_mdp(mdp, _LEURRE)


def valider_mdp(mdp, email=""):
    """Raise ValueError with a displayable message if the password will not do."""
    mdp = _normaliser(mdp)
    if len(mdp) < MDP_MIN:
        raise ValueError("Le mot de passe doit faire au moins %d caracteres."
                         % MDP_MIN)
    if len(mdp) > MDP_MAX:
        raise ValueError("Le mot de passe ne peut pas depasser %d caracteres."
                         % MDP_MAX)
    bas = mdp.lower()
    if bas in COURANTS:
        raise ValueError("Ce mot de passe figure parmi les plus utilises : "
                         "choisis-en un autre.")
    # A password made of the same letter repeated passes the length rule and
    # is worth nothing.
    if len(set(bas)) < 5:
        raise ValueError("Ce mot de passe est trop repetitif.")
    local = (email or "").split("@")[0].lower()
    if len(local) >= 4 and local in bas:
        raise ValueError("Le mot de passe ne doit pas contenir ton adresse email.")
    return mdp


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


def valider_email(email):
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e) or len(e) > 254:
        raise ValueError("Adresse email invalide.")
    return e


# ------------------------------------------------------------- temporisation

def _attente(echecs):
    """1st, 2nd, 3rd attempt: free. Then 2 s, 4 s, 8 s... up to the ceiling."""
    if echecs < ECHECS_AVANT_ATTENTE:
        return 0
    return min(2 ** (echecs - ECHECS_AVANT_ATTENTE + 1), ATTENTE_MAX)


def _reste(jusqu_a):
    return max(0, int(jusqu_a - time.time()))


def _refus_temporise(secondes):
    if secondes >= 60:
        duree = "%d minute(s)" % ((secondes + 59) // 60)
    else:
        duree = "%d seconde(s)" % secondes
    return ValueError("Trop de tentatives. Reessaie dans %s." % duree)


def _verrou_ip(ip):
    n, jusqu_a = _ECHECS_IP.get(ip or "?", (0, 0))
    return _reste(jusqu_a)


def _echec_ip(ip):
    ip = ip or "?"
    n = _ECHECS_IP.get(ip, (0, 0))[0] + 1
    _ECHECS_IP[ip] = (n, time.time() + _attente(n))


# ----------------------------------------------------------------- operations

def creer(email, mdp, nom="", cfg=None):
    """Create an account. Raises ValueError if the email is taken or the password weak."""
    email = valider_email(email)
    valider_mdp(mdp, email)
    with _LOCK:
        d = _lire()
        if _index_email(d, email) >= 0:
            raise ValueError("Un compte existe deja avec cette adresse.")
        # The FIRST account is the administrator. That is the convention among
        # self-hosted tools (Jellyfin, Immich, Paperless): whoever installs it
        # governs. With no roles at all, any user could delete the others or
        # switch authentication off.
        premier = not d["comptes"]
        u = {"id": secrets.token_urlsafe(9), "email": email,
             "nom": (nom or "").strip()[:80] or email.split("@")[0],
             "hash": hacher(mdp), "cree": int(time.time()),
             "maj_mdp": int(time.time()), "echecs": 0, "bloque": 0,
             "photo": "", "derniere": 0, "admin": premier}
        d["comptes"].append(u)
        _ecrire(d)
    return _public(u)


class BesoinCode(ValueError):
    """Password correct, but the second factor is missing or does not match.

    A distinct exception: the form must then ask for the code without making
    the user retype the password. It is only raised after the password has been
    verified, so it reveals the existence of no account.
    """


def totp_preparer(uid):
    """Create a secret, not yet active: it only becomes so once a valid code
    has been supplied. Without that step, a mis-configured app would lock the
    account out."""
    from . import totp
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            secret = totp.new_secret()
            d["comptes"][i]["totp"] = {"secret": secret, "actif": False, "utilises": []}
            _ecrire(d)
            return {"secret": secret, "lisible": totp.readable(secret),
                    "uri": totp.uri(secret, u["email"])}
    raise ValueError("Compte introuvable.")


def totp_activer(uid, saisie):
    from . import totp
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            conf = u.get("totp") or {}
            if not conf.get("secret"):
                raise ValueError("Commence par générer un secret.")
            bon, compteur = totp.verify(conf["secret"], saisie,
                                          utilises=set(conf.get("utilises") or []))
            if not bon:
                raise ValueError("Code incorrect. Vérifie l'heure de ton téléphone.")
            conf.update({"actif": True, "utilises": [compteur]})
            d["comptes"][i]["totp"] = conf
            _ecrire(d)
            return True
    raise ValueError("Compte introuvable.")


def totp_desactiver(uid, mdp):
    """Requires the password: removing a factor is a weakening."""
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            if not verifier_mdp(mdp, u["hash"]):
                raise ValueError("Mot de passe incorrect.")
            d["comptes"][i]["totp"] = {}
            _ecrire(d)
            return True
    raise ValueError("Compte introuvable.")


def totp_actif(u):
    return bool((u or {}).get("totp", {}).get("actif"))


def _consommer_code(email, compteur):
    """Record the counter used, so the same code cannot be replayed."""
    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        if i < 0:
            return
        conf = d["comptes"][i].get("totp") or {}
        vus = [c for c in (conf.get("utilises") or []) if c > compteur - 10]
        vus.append(compteur)
        conf["utilises"] = vus[-10:]
        d["comptes"][i]["totp"] = conf
        _ecrire(d)


def connecter(email, mdp, ip="", code=""):
    """Return the account if the credentials are right, else raise ValueError.

    The error message is the same for an unknown email and a wrong password:
    giving a different message amounts to publishing the list of accounts.
    """
    reste = _verrou_ip(ip)
    if reste:
        raise _refus_temporise(reste)
    email = (email or "").strip().lower()
    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        u = d["comptes"][i] if i >= 0 else None
        if u:
            attente = _reste(u.get("bloque", 0))
            if attente:
                raise _refus_temporise(attente)

    if not u:
        _perdre_du_temps(mdp)          # same cost as for a real account
        _echec_ip(ip)
        raise ValueError("Email ou mot de passe incorrect.")

    if not verifier_mdp(mdp, u["hash"]):
        _echec_ip(ip)
        with _LOCK:
            d = _lire()
            i = _index_email(d, email)
            if i >= 0:
                n = d["comptes"][i].get("echecs", 0) + 1
                d["comptes"][i]["echecs"] = n
                d["comptes"][i]["bloque"] = time.time() + _attente(n)
                _ecrire(d)
        raise ValueError("Email ou mot de passe incorrect.")

    # Password valid. If a second factor exists, it is still to be cleared:
    # the failure counters are therefore not reset yet.
    if totp_actif(u):
        from . import totp
        bon, compteur = totp.verify(u["totp"]["secret"], code,
                                      utilises=set(u["totp"].get("utilises") or []))
        if not bon:
            _echec_ip(ip)
            raise BesoinCode("Code à usage unique requis." if not code
                             else "Code incorrect ou déjà utilisé.")
        _consommer_code(email, compteur)

    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        if i >= 0:
            d["comptes"][i]["echecs"] = 0
            d["comptes"][i]["bloque"] = 0
            d["comptes"][i]["derniere"] = int(time.time())
            _ecrire(d)
            u = d["comptes"][i]
    _ECHECS_IP.pop(ip or "?", None)
    return u


def changer_mdp(uid, ancien, nouveau):
    """Requires the current password: a stolen cookie must not be enough to
    take the account for good."""
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            if not verifier_mdp(ancien, u["hash"]):
                raise ValueError("Mot de passe actuel incorrect.")
            valider_mdp(nouveau, u["email"])
            if verifier_mdp(nouveau, u["hash"]):
                raise ValueError("Le nouveau mot de passe est identique a l'ancien.")
            d["comptes"][i]["hash"] = hacher(nouveau)
            # Move the account's epoch: every session signed before this
            # instant stops being valid (see auth.session).
            d["comptes"][i]["maj_mdp"] = int(time.time())
            _ecrire(d)
            return _public(d["comptes"][i])
    raise ValueError("Compte introuvable.")


def reinitialiser_mdp(email, nouveau):
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
    email = valider_email(email)
    valider_mdp(nouveau, email)
    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        if i < 0:
            raise ValueError("Aucun compte avec cette adresse.")
        d["comptes"][i]["hash"] = hacher(nouveau)
        # Cut every open session: if the account was taken over, reclaiming it
        # must not leave the other party logged in.
        d["comptes"][i]["maj_mdp"] = int(time.time())
        # An account locked by repeated failures must be released: otherwise
        # the reset succeeds and the login fails anyway.
        d["comptes"][i]["echecs"] = 0
        d["comptes"][i]["bloque"] = 0
        _ecrire(d)
        return _public(d["comptes"][i])


def desactiver_totp(email):
    """Remove the second factor. For a lost phone, from the terminal.

    `totp_desactiver()` requires the password, which is right from the
    interface. Here we are already on the machine: requiring the password would
    add no proof, and requiring it for an account whose second factor has just
    been lost would lock the user out for good.
    """
    email = valider_email(email)
    with _LOCK:
        d = _lire()
        i = _index_email(d, email)
        if i < 0:
            raise ValueError("Aucun compte avec cette adresse.")
        avait = bool((d["comptes"][i].get("totp") or {}).get("actif"))
        # `{}` rather than a removed key: that is what `totp_desactiver`
        # already does, and two representations of the same state always end up
        # diverging somewhere.
        d["comptes"][i]["totp"] = {}
        _ecrire(d)
        return avait


def par_email(email):
    """The account bearing this address, or None. For the command line."""
    d = _lire()
    i = _index_email(d, valider_email(email))
    return _public(d["comptes"][i]) if i >= 0 else None


def modifier(uid, nom=None, email=None):
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] != uid:
                continue
            if nom is not None:
                d["comptes"][i]["nom"] = str(nom).strip()[:80] or u["email"].split("@")[0]
            if email is not None:
                e = valider_email(email)
                j = _index_email(d, e)
                if j >= 0 and j != i:
                    raise ValueError("Un compte existe deja avec cette adresse.")
                d["comptes"][i]["email"] = e
            _ecrire(d)
            return _public(d["comptes"][i])
    raise ValueError("Compte introuvable.")


def supprimer(uid):
    """Refuses to delete the last account: nobody could get in any more."""
    with _LOCK:
        d = _lire()
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
        _ecrire(d)
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


def _type_image(octets):
    for magie, ext, mime in SIGNATURES:
        if octets.startswith(magie):
            return ext, mime
    if octets[:4] == b"RIFF" and octets[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None, None


def photo_ecrire(uid, octets):
    if len(octets) > PHOTO_MAX:
        raise ValueError("Image trop lourde (maximum %d Mo)." % (PHOTO_MAX // 2 ** 20))
    ext, mime = _type_image(octets or b"")
    if not ext:
        raise ValueError("Format d'image non reconnu (PNG, JPEG, GIF ou WebP).")
    with _LOCK:
        d = _lire()
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
        (PHOTOS / (uid + ext)).write_bytes(octets)
        d["comptes"][i]["photo"] = uid + ext
        _ecrire(d)
    return {"photo": uid + ext, "type": mime}


def photo_lire(uid):
    """(octets, type) de la photo, ou (None, None)."""
    u = par_id(uid)
    nom = (u or {}).get("photo") or ""
    if not nom:
        return None, None
    p = PHOTOS / nom
    # The name comes from the accounts file, but we check all the same that it
    # stays inside the intended folder.
    try:
        p.resolve().relative_to(PHOTOS.resolve())
    except (ValueError, OSError):
        return None, None
    if not p.exists():
        return None, None
    _, mime = _type_image(p.read_bytes()[:16])
    return p.read_bytes(), mime or "application/octet-stream"


def photo_effacer(uid):
    with _LOCK:
        d = _lire()
        for i, u in enumerate(d["comptes"]):
            if u["id"] == uid:
                nom = u.get("photo") or ""
                d["comptes"][i]["photo"] = ""
                _ecrire(d)
                if nom:
                    try:
                        (PHOTOS / nom).unlink()
                    except OSError:
                        pass
                return True
    return False
