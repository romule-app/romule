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

STEP = 30                 # how long a code lives, in seconds
DIGITS = 6
TOLERANCE = 1            # windows accepted either side


def new_secret(nbytes=20):
    """Shared secret, base32 without padding — the format authenticator apps
    expect."""
    return base64.b32encode(secrets.token_bytes(nbytes)).decode("ascii").rstrip("=")


def _key(secret):
    s = (secret or "").strip().replace(" ", "").upper()
    s += "=" * (-len(s) % 8)
    return base64.b32decode(s, casefold=True)


def code(secret, when=None, offset=0):
    """The 6-digit code for the given when."""
    counter = int((when if when is not None else time.time()) // STEP) + offset
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    # RFC 4226 "dynamic truncation": the last 4 bits say where to read the
    # 31 bits that produce the code.
    start = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[start:start + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** DIGITS)).zfill(DIGITS)


def verify(secret, entered, when=None, used=None):
    """True if `entered` is a valid code that has not been used already.

    `used` is the set of counters already accepted for this account; the
    one just used is added to it, which forbids replaying the same code.
    """
    clean = "".join(c for c in str(entered or "") if c.isdigit())
    if len(clean) != DIGITS:
        return False, None
    base = int((when if when is not None else time.time()) // STEP)
    for d in range(-TOLERANCE, TOLERANCE + 1):
        # constant-time comparison: the code is a short-lived secret
        if hmac.compare_digest(code(secret, when, d), clean):
            counter = base + d
            if used is not None and counter in used:
                return False, None          # already used: replay refused
            return True, counter
    return False, None


def uri(secret, email, issuer="Ma ludotheque"):
    """The `otpauth://` address to enter in the authenticator app."""
    label = urllib.parse.quote("%s:%s" % (issuer, email or "compte"))
    params = urllib.parse.urlencode({
        "secret": secret, "issuer": issuer,
        "algorithm": "SHA1", "digits": DIGITS, "period": STEP})
    return "otpauth://totp/%s?%s" % (label, params)


def readable(secret):
    """Secret split into groups of 4: it can be typed by hand without getting lost."""
    s = (secret or "").replace(" ", "")
    return " ".join(s[i:i + 4] for i in range(0, len(s), 4))
