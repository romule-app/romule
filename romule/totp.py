"""One-time codes (TOTP, RFC 6238), with no dependency.

A stolen password is enough to get in. A second factor changes that: you also
need the device generating the code. It is the only protection that holds if
the library is reachable from outside.

Compatible with every common app (Google Authenticator, Aegis, Bitwarden,
1Password, Ente Auth): HMAC-SHA1, 30-second step, 6 digits — what those apps
assume by default.

Two precautions the algorithm alone does not provide:

  * **one window of tolerance** either side, because the phone's clock and the
    server's are never exactly in step;
  * **refusing to replay a code already used**: without that, an intercepted
    code stays valid for up to 90 seconds.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

PAS = 30                 # how long a code lives, in seconds
CHIFFRES = 6
TOLERANCE = 1            # windows accepted either side


def secret_neuf(octets=20):
    """Shared secret, base32 without padding — the format authenticator apps
    expect."""
    return base64.b32encode(secrets.token_bytes(octets)).decode("ascii").rstrip("=")


def _cle(secret):
    s = (secret or "").strip().replace(" ", "").upper()
    s += "=" * (-len(s) % 8)
    return base64.b32decode(s, casefold=True)


def code(secret, moment=None, decalage=0):
    """The 6-digit code for the given moment."""
    compteur = int((moment if moment is not None else time.time()) // PAS) + decalage
    empreinte = hmac.new(_cle(secret), struct.pack(">Q", compteur), hashlib.sha1).digest()
    # RFC 4226 "dynamic truncation": the last 4 bits say where to read the
    # 31 bits that produce the code.
    debut = empreinte[-1] & 0x0F
    valeur = struct.unpack(">I", empreinte[debut:debut + 4])[0] & 0x7FFFFFFF
    return str(valeur % (10 ** CHIFFRES)).zfill(CHIFFRES)


def verifier(secret, saisie, moment=None, utilises=None):
    """True if `saisie` is a valid code that has not been used already.

    `utilises` is the set of counters already accepted for this account; the
    one just used is added to it, which forbids replaying the same code.
    """
    propre = "".join(c for c in str(saisie or "") if c.isdigit())
    if len(propre) != CHIFFRES:
        return False, None
    base = int((moment if moment is not None else time.time()) // PAS)
    for d in range(-TOLERANCE, TOLERANCE + 1):
        # constant-time comparison: the code is a short-lived secret
        if hmac.compare_digest(code(secret, moment, d), propre):
            compteur = base + d
            if utilises is not None and compteur in utilises:
                return False, None          # already used: replay refused
            return True, compteur
    return False, None


def uri(secret, email, emetteur="Ma ludotheque"):
    """The `otpauth://` address to enter in the authenticator app."""
    label = urllib.parse.quote("%s:%s" % (emetteur, email or "compte"))
    params = urllib.parse.urlencode({
        "secret": secret, "issuer": emetteur,
        "algorithm": "SHA1", "digits": CHIFFRES, "period": PAS})
    return "otpauth://totp/%s?%s" % (label, params)


def lisible(secret):
    """Secret split into groups of 4: it can be typed by hand without getting lost."""
    s = (secret or "").replace(" ", "")
    return " ".join(s[i:i + 4] for i in range(0, len(s), 4))
