"""A minimal fake OIDC provider, to test the flow end to end.

It exposes the discovery document, an authorisation endpoint that redirects
straight away, a token endpoint that signs a real RS256 id_token, and the
matching JWKS.
"""
import base64, hashlib, json, random, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9901
BASE = "http://127.0.0.1:%d" % PORT
CLIENT = "ludotheque"
SECRET = "s3cr3t"


def premier(bits, rnd):
    while True:
        n = rnd.getrandbits(bits) | (1 << (bits - 1)) | 1
        if all(n % p for p in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)) and pow(2, n - 1, n) == 1:
            return n


rnd = random.Random(1234)
P, Q = premier(512, rnd), premier(512, rnd)
N, E = P * Q, 65537
D = pow(E, -1, (P - 1) * (Q - 1))
TAILLE = (N.bit_length() + 7) // 8
DER = bytes.fromhex("3031300d060960864801650304020105000420")
b64u = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()

DEMANDES = {}          # code -> (nonce, defi)


def signer_jwt(claims):
    e64 = b64u(json.dumps({"alg": "RS256", "kid": "test"}).encode())
    c64 = b64u(json.dumps(claims).encode())
    signe = (e64 + "." + c64).encode()
    suf = DER + hashlib.sha256(signe).digest()
    em = b"\x00\x01" + b"\xff" * (TAILLE - len(suf) - 3) + b"\x00" + suf
    sig = pow(int.from_bytes(em, "big"), D, N).to_bytes(TAILLE, "big")
    return e64 + "." + c64 + "." + b64u(sig)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, o, code=200):
        b = json.dumps(o).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        chemin, _, q = self.path.partition("?")
        p = urllib.parse.parse_qs(q)
        if chemin == "/.well-known/openid-configuration":
            return self._j({
                "issuer": BASE,
                "authorization_endpoint": BASE + "/authorize",
                "token_endpoint": BASE + "/token",
                "jwks_uri": BASE + "/jwks",
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["client_secret_basic"],
            })
        if chemin == "/jwks":
            return self._j({"keys": [{"kty": "RSA", "kid": "test", "alg": "RS256", "use": "sig",
                                      "n": b64u(N.to_bytes(TAILLE, "big")),
                                      "e": b64u(E.to_bytes(3, "big"))}]})
        if chemin == "/authorize":
            code = "code-" + base64.urlsafe_b64encode(random.randbytes(9)).decode()
            DEMANDES[code] = (p.get("nonce", [""])[0], p.get("code_challenge", [""])[0])
            dest = p.get("redirect_uri", [""])[0] + "?" + urllib.parse.urlencode(
                {"code": code, "state": p.get("state", [""])[0]})
            self.send_response(302)
            self.send_header("Location", dest)
            self.end_headers()
            return
        self._j({"error": "not_found"}, 404)

    def do_POST(self):
        if not self.path.startswith("/token"):
            return self._j({"error": "not_found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        d = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
        code = d.get("code", "")
        if code not in DEMANDES:
            return self._j({"error": "invalid_grant"}, 400)
        nonce, defi = DEMANDES.pop(code)
        # PKCE: the verifier must match the challenge announced at the start
        calcul = b64u(hashlib.sha256(d.get("code_verifier", "").encode()).digest())
        if defi and calcul != defi:
            return self._j({"error": "invalid_grant", "error_description": "PKCE"}, 400)
        import time
        return self._j({"access_token": "at", "token_type": "Bearer",
                        "id_token": signer_jwt({
                            "iss": BASE, "aud": CLIENT, "sub": "u-42",
                            "exp": time.time() + 300, "iat": time.time(),
                            "nonce": nonce, "name": "Dino",
                            "email": "dino@exemple.fr", "groups": ["ludo"]})})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
