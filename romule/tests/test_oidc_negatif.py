"""What a FORGED identity token must be refused.

The existing SSO suite proved one thing only: a valid token, issued by a working
provider, is accepted. That is the nominal path — the one an attacker takes no
interest in.

A JWT verifier is exactly the kind of code where a quiet mistake is a hole and
not a crash. Every check below matches a known and documented attack:

  * `alg: none`        — the token dictates its own algorithm, and skips the
                         signature;
  * RS256/HS confusion — the PUBLIC key, known to all, serves as the HMAC secret;
  * wrong issuer       — a valid token from ANOTHER provider;
  * wrong audience     — a valid token meant for ANOTHER application;
  * expired token      — replayed later;
  * altered payload    — the claims changed, the original signature kept;
  * unknown kid        — a key the provider has never published.

The last check verifies that a VALID token passes: a suite that refuses
everything proves nothing.
"""
import base64
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent.parent))
sys.path.insert(0, str(ICI))

from romule import auth                                          # noqa: E402
import faux_oidc as fp                                           # noqa: E402

PORT = "9903"
BASE = "http://127.0.0.1:" + PORT

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c:
        ok += 1
        print("      OK   %s" % n)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (n, d))


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def signer(claims, entete=None, cle=None):
    """Forges a token with the requested header and key."""
    e = dict({"alg": "RS256", "kid": "test"}, **(entete or {}))
    e64 = b64u(json.dumps(e).encode())
    c64 = b64u(json.dumps(claims).encode())
    signe = (e64 + "." + c64).encode()
    n, d = cle or (fp.N, fp.D)
    taille = (n.bit_length() + 7) // 8
    suf = fp.DER + hashlib.sha256(signe).digest()
    em = b"\x00\x01" + b"\xff" * (taille - len(suf) - 3) + b"\x00" + suf
    sig = pow(int.from_bytes(em, "big"), d, n).to_bytes(taille, "big")
    return e64 + "." + c64 + "." + b64u(sig)


def claims_valides(**remplace):
    c = {"iss": "http://127.0.0.1:" + PORT, "aud": "ludotheque", "sub": "u-42",
         "exp": time.time() + 300, "iat": time.time(), "nonce": "N0NCE",
         "email": "dino@exemple.fr"}
    c.update(remplace)
    return c


def refuse(nom, jeton, nonce="N0NCE"):
    """The token must be refused — and by a ValueError, not by a crash."""
    try:
        auth.verifier_id_token(jeton, DOC, "ludotheque", nonce)
    except ValueError as exc:
        t(nom, True)
        return str(exc)
    except Exception as exc:                                     # noqa: BLE001
        t(nom, False, "refuse, mais par %s : %s" % (type(exc).__name__, exc))
        return ""
    t(nom, False, "ACCEPTE alors qu'il devait etre refuse")
    return ""


# ---------------------------------------------------------------- provider
srv = subprocess.Popen([sys.executable, str(ICI / "faux_oidc.py"), PORT],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/jwks", timeout=2).read()
            break
        except Exception:
            time.sleep(0.5)
    else:
        print("      ECHEC le faux fournisseur n'a pas demarre")
        sys.exit(1)

    DOC = {"issuer": BASE, "jwks_uri": BASE + "/jwks"}

    print("   -- 1. l'algorithme annonce par le jeton ne fait pas foi --")
    # `alg: none`: the reference hole. The signature is empty, and a naive
    # library trusts the header to know what to verify.
    sans_sig = (b64u(json.dumps({"alg": "none", "kid": "test"}).encode()) + "."
                + b64u(json.dumps(claims_valides()).encode()) + ".")
    refuse("alg: none refuse", sans_sig)

    # RS256/HS256 confusion: the PUBLIC key is known to all. If the verifier
    # follows the header, it becomes a shared HMAC secret.
    e64 = b64u(json.dumps({"alg": "HS256", "kid": "test"}).encode())
    c64 = b64u(json.dumps(claims_valides()).encode())
    import hmac as _hmac
    pub = fp.N.to_bytes((fp.N.bit_length() + 7) // 8, "big")
    hs = b64u(_hmac.new(pub, (e64 + "." + c64).encode(), hashlib.sha256).digest())
    refuse("confusion RS256/HS256 refusee", e64 + "." + c64 + "." + hs)

    refuse("algorithme inconnu refuse",
           signer(claims_valides(), entete={"alg": "RS512"}))

    print("   -- 2. la signature doit tenir --")
    jeton = signer(claims_valides())
    e, c, s = jeton.split(".")
    # One byte flipped in the signature
    brut = bytearray(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))
    brut[0] ^= 0x01
    refuse("signature alteree refusee", "%s.%s.%s" % (e, c, b64u(bytes(brut))))

    # Payload replaced, original signature kept: the most direct attack once a
    # legitimate token has been intercepted.
    autre = b64u(json.dumps(claims_valides(sub="admin", email="pirate@ailleurs")).encode())
    refuse("charge alteree, signature d'origine refusee", "%s.%s.%s" % (e, autre, s))

    # Signed with ANOTHER RSA key, of the right shape but unknown to the provider
    import random as _r
    rnd = _r.Random(4321)
    p2, q2 = fp.premier(512, rnd), fp.premier(512, rnd)
    n2 = p2 * q2
    d2 = pow(65537, -1, (p2 - 1) * (q2 - 1))
    refuse("signature d'une cle etrangere refusee",
           signer(claims_valides(), cle=(n2, d2)))

    refuse("kid inconnu refuse", signer(claims_valides(), entete={"kid": "inexistant"}))

    print("   -- 3. le jeton doit nous etre destine, et venir du bon emetteur --")
    refuse("emetteur different refuse",
           signer(claims_valides(iss="http://malveillant.example")))
    refuse("public different refuse", signer(claims_valides(aud="autre-app")))
    refuse("public en liste sans nous refuse",
           signer(claims_valides(aud=["autre-app", "encore-une-autre"])))

    print("   -- 4. la fenetre de temps --")
    refuse("jeton expire refuse", signer(claims_valides(exp=time.time() - 3600)))
    refuse("jeton date du futur refuse",
           signer(claims_valides(iat=time.time() + 4000)))
    refuse("nonce different refuse", signer(claims_valides(nonce="AUTRE")))

    print("   -- 5. entrees malformees : refus, jamais plantage --")
    refuse("jeton en deux morceaux refuse", "aaa.bbb")
    refuse("jeton vide refuse", "")
    refuse("base64 invalide refuse", "!!!.???.***")
    refuse("charge non-JSON refusee",
           "%s.%s.%s" % (e, b64u(b"pas du json"), s))
    try:
        auth.verifier_id_token(signer(claims_valides()), {"issuer": BASE},
                               "ludotheque", "N0NCE")
        t("fournisseur sans jwks_uri refuse", False, "ACCEPTE")
    except ValueError:
        t("fournisseur sans jwks_uri refuse", True)

    print("   -- 6. temoin : un jeton valide passe --")
    # Without this check, a suite that refuses everything would look perfect.
    try:
        c = auth.verifier_id_token(signer(claims_valides()), DOC, "ludotheque", "N0NCE")
        t("jeton valide accepte", c.get("email") == "dino@exemple.fr", c)
    except ValueError as exc:
        t("jeton valide accepte", False, str(exc))

    # The nonce is only checked if it was requested.
    try:
        auth.verifier_id_token(signer(claims_valides(nonce=None)), DOC, "ludotheque", "")
        t("nonce non demande : non exige", True)
    except ValueError as exc:
        t("nonce non demande : non exige", False, str(exc))

finally:
    srv.kill()

print("      ------------------------------------------------")
print("      %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
