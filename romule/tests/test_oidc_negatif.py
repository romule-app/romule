"""Ce qu'un jeton d'identite FORGE doit se voir refuser.

La suite SSO existante ne prouvait qu'une chose : un jeton valide, emis par un
fournisseur qui fonctionne, est accepte. C'est le chemin nominal — celui qui
n'interesse pas un attaquant.

Un verificateur de JWT est exactement le genre de code ou une erreur discrete
est une faille et non un plantage. Chaque controle ci-dessous correspond a une
attaque connue et documentee :

  * `alg: none`        — le jeton dicte son propre algorithme, et se dispense
                         de signature ;
  * confusion RS256/HS — la cle PUBLIQUE, connue de tous, sert de secret HMAC ;
  * mauvais emetteur   — un jeton valide d'un AUTRE fournisseur ;
  * mauvais public     — un jeton valide destine a une AUTRE application ;
  * jeton expire       — rejoue plus tard ;
  * charge alteree     — les claims changes, la signature d'origine gardee ;
  * kid inconnu        — une cle que le fournisseur n'a jamais publiee.

Le dernier controle verifie qu'un jeton VALIDE passe : une suite qui refuse
tout ne prouve rien.
"""
import base64
import hashlib
import json
import os
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
    """Forge un jeton avec l'entete et la cle demandees."""
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
    """Le jeton doit etre refuse — et par une ValueError, pas par un plantage."""
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
    # `alg: none` : la faille de reference. La signature est vide, et une
    # bibliotheque naive fait confiance a l'entete pour savoir quoi verifier.
    sans_sig = (b64u(json.dumps({"alg": "none", "kid": "test"}).encode()) + "."
                + b64u(json.dumps(claims_valides()).encode()) + ".")
    refuse("alg: none refuse", sans_sig)

    # Confusion RS256/HS256 : la cle PUBLIQUE est connue de tous. Si le
    # verificateur suit l'entete, elle devient un secret HMAC partage.
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
    # Un octet retourne dans la signature
    brut = bytearray(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))
    brut[0] ^= 0x01
    refuse("signature alteree refusee", "%s.%s.%s" % (e, c, b64u(bytes(brut))))

    # Charge remplacee, signature d'origine conservee : l'attaque la plus
    # directe une fois un jeton legitime intercepte.
    autre = b64u(json.dumps(claims_valides(sub="admin", email="pirate@ailleurs")).encode())
    refuse("charge alteree, signature d'origine refusee", "%s.%s.%s" % (e, autre, s))

    # Signe avec une AUTRE cle RSA, du bon format mais inconnue du fournisseur
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
    # Sans ce controle, une suite qui refuse tout aurait l'air parfaite.
    try:
        c = auth.verifier_id_token(signer(claims_valides()), DOC, "ludotheque", "N0NCE")
        t("jeton valide accepte", c.get("email") == "dino@exemple.fr", c)
    except ValueError as exc:
        t("jeton valide accepte", False, str(exc))

    # Le nonce n'est controle que s'il a ete demande.
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
