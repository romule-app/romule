"""Serveur web (bibliotheque standard seule).

Listens on 127.0.0.1 by default. It only opens to the network when its owner
has asked for it: the `lan_access` setting, ROMULE_LAN, ROMULE_TOKEN, or
running in a container — where publishing a port stands for an explicit
decision. The previous docstring claimed to listen on 127.0.0.1 only while the
socket had been bound to 0.0.0.0 all along.
"""

import gzip
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
import json
import os
import secrets
import shutil
import sys
import signal
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from html import escape as html_escape
from urllib.parse import parse_qs, unquote

from . import (actions, apikeys, apiv1, audit, auth, comptes, config, console,
               covers, maj, notifs, reseau,
               device, edenconf,
               doublons, emuready, igdb, integrity, journal_acces, meta, nand,
               parcourir, sauvegarde, saves,
               scan, systems, titleid, transferts, trash, versions, vues,
               profils, nsztool)
from . import cli
from . import LICENCE, SOURCE_URL, __version__
from .jobs import JobRunner

LIB = scan.Library()
JOB = JobRunner(config.LOGFILE)
CFG = config.load_config()

_CTYPES = {".html": "text/html", ".js": "application/javascript", ".css": "text/css"}

LOCALES = config.PKG / "locales"


def _langues():
    """The available languages, read from romule/locales/ (outside the code)."""
    out = []
    for f in sorted(LOCALES.glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8")).get("_meta", {})
            # The file says "langue", not "nom": the read therefore always
            # fell back to the file name, and the selector offered "fr" and
            # "en" instead of "Francais" and "English".
            out.append({"code": m.get("code", f.stem),
                        "nom": m.get("langue") or m.get("nom") or f.stem})
        except (ValueError, OSError):
            continue
    return out

MANIFEST = {
    "name": "Romule",
    "short_name": "Romule",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0d1016",
    "theme_color": "#0d1016",
    "orientation": "any",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
    ],
}


def _png_icon(size):
    """A PNG icon generated with no dependency: dark square, amber cartouche."""
    import struct
    import zlib
    bg, fg = (0x15, 0x1A, 0x23), (0xFF, 0xB4, 0x54)
    m = size // 4                       # margins of the central cartouche
    rows = bytearray()
    for y in range(size):
        rows.append(0)                  # filtre de ligne : aucun
        inside_y = m <= y < size - m
        for x in range(size):
            c = fg if (inside_y and m <= x < size - m) else bg
            rows += bytes(c)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + chunk(b"IEND", b""))


# Fields that must never leave the server in the clear.
#   auth_secret        : signs the session cookies — reading it means being able
#                        to forge a valid session for anybody;
#   oidc_client_secret : authenticates the application to the provider.
MASQUE = "\u2022" * 8
SECRETS = ("oidc_client_secret", "igdb_client_secret")
PRIVES = ("auth_secret", "jeton_auto")


def _config_publique():
    """Copie de la configuration destinee au navigateur, expurgee."""
    pub = {k: v for k, v in CFG.items() if k not in PRIVES}
    for k in SECRETS:
        if pub.get(k):
            pub[k] = MASQUE
    return pub


def _lib_response():
    LIB.scan(log=JOB.log)
    LIB.enrich()
    shop = LIB.shopping_list()
    a_installer = LIB.nand_rows()      # do not shadow the `nand` module
    return {
        "files": LIB.files,
        "stats": LIB.stats(),
        "shop": shop,
        "shop_text": scan.shopping_text(shop),
        "nand": [{"type": f["type"], "rel": f["rel"], "path": f["path"]}
                 for f in a_installer],
        "pending": actions.scan_import(),
        "config": _config_publique(),
        "device": device.state(),
        "covers_v": covers.version(),
        # translated titles and summaries already cached: disk reads only, so
        # that rendering never depends on the network
        "meta": meta.bulk([titleid.tid_base(f["tid"]) for f in LIB.files if f["tid"]], CFG),
    }


def _taille(n):
    """A readable size: raw bytes say nothing inside a message."""
    for unite in ("o", "Kio", "Mio", "Gio", "Tio"):
        if n < 1024 or unite == "Tio":
            return "%.1f %s" % (n, unite) if unite != "o" else "%d o" % n
        n /= 1024.0


# ---------------------------------------------------------------- LIMITS
# A server that accepts everything eventually meets the first person who
# insists. Three limits, all tunable, all generous: they do not hinder normal
# use and they make the worst case finite.
DELAI_SOCKET = int(config.env("TIMEOUT", "300"))       # secondes
CONNEXIONS_MAX = int(config.env("MAX_CONN", "64"))
APPELS_PAR_MINUTE = int(config.env("RATE", "600"))

_PLACES = threading.BoundedSemaphore(CONNEXIONS_MAX)

# A per-client call counter. Deliberately coarse: a one-minute window, reset
# wholesale. An exact limiter would need state that grows; this one empties
# itself.
_CADENCE = {}
_CADENCE_VERROU = threading.Lock()


def _trop_vite(client):
    """Has this client exceeded its quota for the current minute?"""
    minute = int(time.time() // 60)
    with _CADENCE_VERROU:
        fenetre, compte = _CADENCE.get(client, (minute, 0))
        if fenetre != minute:
            fenetre, compte = minute, 0
        compte += 1
        _CADENCE[client] = (fenetre, compte)
        # The dictionary must not grow forever: we empty it when it gets big,
        # which incidentally grants everyone a free round — of no consequence,
        # the window only lasts a minute.
        if len(_CADENCE) > 4096:
            _CADENCE.clear()
        return compte > APPELS_PAR_MINUTE


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        # `BaseHTTPRequestHandler`'s own format goes to stderr, with no level
        # and no usable timestamp. We replace it with ours, in
        # `handle_one_request`, where the response CODE and the duration are
        # known.
        pass

    def send_response_only(self, code, message=None):
        # The one point both `send_response` AND `send_error` go through:
        # recording the code here records it for every route, including the
        # ones that fail — precisely the ones we are after.
        self._code = code
        BaseHTTPRequestHandler.send_response_only(self, code, message)

    def handle_one_request(self):
        debut = time.monotonic()
        self._code = 0
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        finally:
            # `ROMULE_LOG=debug` only: the interface polls `/api/job` in a
            # loop, and these lines would drown out everything else elsewhere.
            if console.montre("debug") and getattr(self, "command", None):
                ms = (time.monotonic() - debut) * 1000
                code = self._code or 0
                console.evenement(
                    "%-4s %-3d %6.1fms %s" % (self.command, code, ms, self.path),
                    "error" if code >= 500 else "warn" if code >= 400 else "debug",
                    "http", client=self.client_address[0] if self.client_address else "?")

    # ---------------------------------------------------------- helpers

    def send_response(self, code, message=None):
        self._secu_faite = False
        BaseHTTPRequestHandler.send_response(self, code, message)

    def end_headers(self):
        # A single point of application: impossible to forget a route.
        if not getattr(self, "_secu_faite", True):
            self._secu_faite = True
            self._entetes_securite()
        BaseHTTPRequestHandler.end_headers(self)

    # Types worth compressing. `application/javascript` is listed explicitly:
    # it is the largest body the server sends (app.js, 300 KiB) and it does not
    # start with `text/`.
    TYPES_GZIP = ("application/json", "application/javascript",
                  "application/manifest+json", "text/", "image/svg+xml")
    # Below this, the header and the compression time cost more than the gain.
    SEUIL_GZIP = 1024

    def _accepte_gzip(self):
        """Can the client read gzip?

        `gzip;q=0` means "definitely not": rare, but ignoring it would send an
        unreadable body to someone who explicitly refused it.
        """
        for bout in self.headers.get("Accept-Encoding", "").lower().split(","):
            morceaux = [m.strip() for m in bout.split(";")]
            if morceaux[0] not in ("gzip", "*"):
                continue
            for p in morceaux[1:]:
                if p.replace(" ", "").startswith("q="):
                    try:
                        return float(p.split("=", 1)[1]) > 0
                    except ValueError:
                        return False
            return True
        return False

    def _compressible(self, corps, ctype):
        return (len(corps) >= self.SEUIL_GZIP
                and any(ctype.startswith(t) for t in self.TYPES_GZIP)
                and self._accepte_gzip())

    def _ecrire(self, corps, ctype, code=200, entetes=(), cookie=False):
        """Write a response, compressed when it is worth it.

        One path, because there were six: compressing in `_json` alone would
        have let `_static` through, which is where it matters — app.js, app.css
        and index.html weigh 507 KiB and go out on EVERY load, since `_static`
        sets `Cache-Control: no-store`.

        Measured on a 2 000-title library: /api/scan goes from 2.04 MiB to
        0.08 MiB, and the three static files from 507 to 153 KiB.

        `Vary: Accept-Encoding` is set even when we do not compress: without it,
        an intermediate cache serves the compressed variant to a client that
        cannot read it.
        """
        entetes = list(entetes)
        if self._compressible(corps, ctype):
            corps = gzip.compress(corps, 6)
            entetes.append(("Content-Encoding", "gzip"))
        entetes.append(("Vary", "Accept-Encoding"))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(corps)))
        for k, v in entetes:
            self.send_header(k, v)
        if cookie:
            self._set_token_cookie()
        self.end_headers()
        self.wfile.write(corps)

    def _json(self, obj, code=200):
        self._ecrire(json.dumps(obj).encode(),
                     "application/json; charset=utf-8", code)

    def _json_revalide(self, obj, volatiles=()):
        """JSON with an ETag: the tool's heaviest response (the inventory,
        ~130 KB) only goes out in full when it has changed. The browser
        revalidates every time — so never stale data — but receives a 304 and a
        few bytes while nothing moves. This is the most expensive part of
        startup on a phone over Wi-Fi."""
        body = json.dumps(obj).encode()
        # Some keys carry a timestamp regenerated on every call: including them
        # would make every response unique and the ETag useless. They always
        # derive from another key, which is compared properly.
        empreinte = json.dumps({k: v for k, v in obj.items() if k not in volatiles},
                               sort_keys=True, default=str).encode()
        # The ETag must tell the two representations apart: the compressed one
        # and the other do not share bytes. Without this suffix, a client that
        # stops accepting gzip would receive a 304 for a body it never had in
        # that form.
        gz = self._compressible(body, "application/json")
        etag = '"%s%s"' % (hashlib.sha256(empreinte).hexdigest()[:32],
                           "-gz" if gz else "")
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Vary", "Accept-Encoding")
            self.end_headers()
            return
        self._ecrire(body, "application/json; charset=utf-8", 200,
                     entetes=[("ETag", etag),
                              ("Cache-Control", "no-cache")])  # revalidate, not ignore

    def _static(self, name):
        path = config.STATIC / name
        if not path.is_file():
            self._json({"error": "introuvable"}, 404)
            return
        self._ecrire(path.read_bytes(),
                     _CTYPES.get(path.suffix, "application/octet-stream")
                     + "; charset=utf-8", 200,
                     # always the latest version
                     entetes=[("Cache-Control", "no-store")], cookie=True)

    # A JSON request body has no reason to exceed a few hundred kilobytes: the
    # largest is a list of paths. Without a bound, a POST announcing 4 GB filled
    # the server's memory before it was even parsed. File uploads have their own
    # route, streamed.
    CORPS_MAX = 1 << 20            # 1 MiB

    def _payload(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > self.CORPS_MAX:
            raise ValueError("corps de requete trop volumineux (%d octets)" % n)
        return json.loads(self.rfile.read(n) or b"{}")

    # ---------------------------------------------------------- GET

    # With no timeout, a connection opened and left silent pins a thread
    # forever: that is the whole principle of the "slowloris" attack.
    timeout = DELAI_SOCKET

    def handle(self):
        """A slot, or a polite refusal.

        `ThreadingHTTPServer` creates a thread per connection, with no ceiling.
        A thousand simultaneous connections created a thousand threads before
        any rule at all applied.
        """
        if not _PLACES.acquire(timeout=10):
            try:
                self.send_response(503)
                self.send_header("Retry-After", "5")
                self.send_header("Content-Length", "0")
                self.end_headers()
            except Exception:
                pass
            return
        try:
            BaseHTTPRequestHandler.handle(self)
        finally:
            _PLACES.release()

    def _cookie(self, nom):
        """A cookie's value, read as a cookie and not as text.

        The previous read looked for the substring "switch_token=<token>" in
        the raw header: a neighbouring cookie named `x_switch_token`, or a value
        containing the token as a prefix, satisfied the test.
        """
        brut = self.headers.get("Cookie")
        if not brut:
            return ""
        try:
            pot = SimpleCookie()
            pot.load(brut)
        except CookieError:
            return ""
        morceau = pot.get(nom)
        return morceau.value if morceau else ""

    def _token_ok(self):
        """Jeton fourni par cookie, en-tete ou ?token= (service expose 24/7).

        Constant-time comparison: an `==` on a string stops at the first
        differing byte, which lets the correct prefix be measured.
        """
        if not config.TOKEN:
            return False
        attendu = config.TOKEN
        candidats = [self.headers.get("X-Token", "").strip(),
                     self._cookie("switch_token")]
        q = parse_qs(self.path.partition("?")[2]).get("token")
        if q:
            candidats.append(q[0])
        return any(hmac.compare_digest(c, attendu) for c in candidats if c)

    # Headers added by a relay. Their mere presence means the request is NOT
    # arriving directly from its author.
    ENTETES_RELAI = ("X-Forwarded-For", "X-Real-IP", "Forwarded",
                     "X-Forwarded-Host", "X-Forwarded-Proto")

    def _relayee(self):
        return any(self.headers.get(h) for h in self.ENTETES_RELAI)

    def _client_reel(self):
        """The request author's address, or None when it cannot be determined.

        The TCP peer is enough while nobody relays. As soon as a relay steps
        in, it becomes the RELAY's address — and behind a reverse proxy on the
        same machine, that is 127.0.0.1 for everybody, the whole internet
        included. That is the hole this method closes: a header is only
        believed when it comes from a declared proxy.
        """
        pair = self.client_address[0]
        if not self._relayee():
            return pair
        if not config.proxy_de_confiance(pair):
            return None                     # somebody is relaying without a mandate
        # The declared proxy appended the peer it saw on the right. We walk
        # back up the chain, skipping relays that are themselves declared.
        chaine = [a.strip() for a in
                  (self.headers.get("X-Forwarded-For") or "").split(",") if a.strip()]
        for adresse in reversed(chaine):
            if not config.proxy_de_confiance(adresse):
                return adresse
        # The whole chain is made of declared addresses. That happens when the
        # client is ITSELF on the proxy's machine — the common case of a local
        # nginx in front of the application. The first entry is then the only
        # candidate left.
        if chaine:
            return chaine[0]
        return self.headers.get("X-Real-IP", "").strip() or None

    def _local(self):
        return self._client_reel() in ("127.0.0.1", "::1", "localhost")

    def _secure(self):
        """La requete arrive-t-elle en HTTPS (directement ou via un proxy) ?"""
        return (self.headers.get("X-Forwarded-Proto", "").lower() == "https"
                or self.headers.get("X-Forwarded-Ssl", "").lower() == "on")

    def _hote_attendu(self):
        return (self.headers.get("X-Forwarded-Host")
                or self.headers.get("Host") or "").lower()

    def _meme_origine(self):
        """Does the browser say the request really comes from THIS page?

        Without this check, a third-party site open in another tab could make
        the library perform any action using the user's session cookie (CSRF).
        The cookie is `SameSite=Lax`, which already covers recent browsers;
        this closes the rest.
        """
        origine = self.headers.get("Origin") or ""
        if not origine:
            # Some clients (curl, the installed app) send no Origin. Failing
            # Origin, we fall back to Referer when it is there.
            ref = self.headers.get("Referer") or ""
            if not ref:
                return True
            origine = ref
        hote = self._hote_attendu()
        try:
            depuis = origine.split("//", 1)[1].split("/", 1)[0].lower()
        except IndexError:
            return False
        return bool(hote) and depuis == hote

    def _entetes_securite(self):
        """Headers applied to every response.

        The interface calls no third-party domain and loads no external script:
        a strict policy breaks nothing and blocks the injection of remote
        content.
        """
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        # None of these capabilities is used by the interface: refusing them
        # explicitly stops a future injection from getting hold of one.
        self.send_header("Permissions-Policy",
                         "camera=(), microphone=(), geolocation=(), "
                         "payment=(), usb=(), interest-cohort=()")
        # Isolate the page from other tabs: a window opened from here keeps no
        # hold on this one.
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        # Responses carrying accounts or settings must leave no trace in a
        # shared cache — neither proxy nor disk.
        if any(self.path.startswith(x) for x in
               ("/api/comptes", "/api/config", "/auth/", "/api/compte-")):
            self.send_header("Cache-Control", "no-store, private")
        # HSTS only when the link is already encrypted: announcing it in the
        # clear would lock the user out of an installation without TLS, and
        # most are.
        if self._secure():
            self.send_header("Strict-Transport-Security",
                             "max-age=15552000; includeSubDomains")
        # `script-src 'self'` with no tolerance for inline. That was
        # impossible while the interface rested on 153 `onclick` attributes:
        # refusing them would have made almost every button inert, silently.
        # They all moved to `data-act` (phase 4), and a single inline <script>
        # remained — the theme — which became `/theme.js`. A browser now
        # refuses any script this origin did not serve, including one a
        # successful injection would write into the page.
        #
        # `style-src` keeps 'unsafe-inline': `style=` attributes are still
        # numerous, and a style does not execute. That is an exception of a
        # different nature, and it is documented as such.
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; "
                         "style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; "
                         "connect-src 'self'; frame-ancestors 'none'; "
                         "base-uri 'none'; form-action 'self'")

    def _cadence_ok(self):
        """Refuse past the quota, with a 429 and the wait time.

        Only the login was rate-limited until now. Everything else — token
        attempts and file uploads included — could be repeated endlessly.
        """
        client = self._client_reel() or self.client_address[0]
        if not _trop_vite(client):
            return True
        try:
            self.send_response(429)
            self.send_header("Retry-After", "60")
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            corps = b"Trop de requetes. Reessaie dans une minute.\n"
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
        except Exception:
            pass
        return False

    def _cle_api(self):
        """The key presented, if there is one.

        The header is the normal form. The parameter exists because some
        clients — a dashboard tile that only takes a URL, a `wget` in a cron —
        cannot set a header. It is the worse option: a URL ends up in the
        proxy's logs and in the history. That is written in the documentation
        rather than refused here.
        """
        entete = self.headers.get("X-Api-Key")
        if entete:
            return entete.strip()
        requete = self.path.partition("?")[2]
        if "apikey=" in requete:
            return parse_qs(requete).get("apikey", [""])[0].strip()
        return None

    def _allowed(self):
        """Who is allowed in.

        SSO authentication, when active, applies LOCALLY too: switching on an
        SSO and then staying reachable without a password from the machine
        itself would empty the measure of its meaning as soon as the desk is
        shared.
        """
        # The API key comes BEFORE the SSO, and that is deliberate. As things
        # stand `auth.actif()` refuses anything without a session cookie: right
        # for a browser, and it would make the API unusable precisely in the
        # installations that protect it best.
        #
        # It is SCOPED TO THE PATH. Without that limit, a key handed to a
        # dashboard would also open `/api/compte-supprimer` — which would
        # amount to distributing the administrator's password under another
        # name.
        cle = self._cle_api()
        if cle:
            if not apiv1.dans_la_portee(self.path.partition("?")[0]):
                return False
            qui = apikeys.verifier(cle)
            if qui:
                self.cle_api = qui
                return True
            return False

        if auth.actif(CFG):
            if self.path.startswith("/auth/"):
                return True                       # the login flow itself
            return bool(auth.session(self.headers.get("Cookie")))
        if self._local():
            return True
        if config.TOKEN:
            return self._token_ok()
        return bool(CFG.get("lan_access"))

    def _deny(self):
        # With an SSO configured we do not show a blunt refusal: we send the
        # user to log in, which is precisely what they came for.
        if auth.actif(CFG):
            return self._page_connexion()
        if config.TOKEN:
            msg = ("Acces protege.\n\nAjoute ?token=TON_JETON a l'adresse, "
                   "par exemple :\n  http://<serveur>:%d/?token=..." % config.PORT)
        else:
            msg = ("Acces reseau desactive.\n\nActive-le dans Reglages > "
                   "Acces depuis le telephone.")
        self._ecrire(msg.encode(), "text/plain; charset=utf-8", 403)

    def _set_token_cookie(self):
        """Remember the token after a ?token= access: no need to retype it."""
        if config.TOKEN and "token=" in self.path:
            # HttpOnly: no script needs to read this token back, and hiding it
            # removes a target from injections. Secure as soon as the link is
            # encrypted, so it never goes back out in the clear.
            self.send_header("Set-Cookie",
                             "switch_token=%s; Path=/; Max-Age=31536000; "
                             "SameSite=Lax; HttpOnly%s"
                             % (config.TOKEN, "; Secure" if self._secure() else ""))

    # ------------------------------------------------------- connexion SSO

    def _base_retour(self):
        """The return address presented to the provider. It must match, word
        for word, the one declared in Authentik / Keycloak: so we build it
        predictably, and let the user pin it when their installation goes
        through a proxy."""
        fixe = (CFG.get("oidc_redirect") or "").strip().rstrip("/")
        if fixe:
            return fixe + "/auth/callback"
        hote = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") \
            or ("127.0.0.1:%d" % config.PORT)
        schema = "https" if self._secure() else "http"
        return "%s://%s/auth/callback" % (schema, hote)

    def _page(self, titre, corps, code=200, entetes=()):
        html = ("<!doctype html><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>%s</title><link rel='stylesheet' href='/app.css'>"
                "<body><div class='chargeur' style='opacity:1;pointer-events:auto'>"
                "<div class='chargeur-in'>%s</div></div>" % (titre, corps))
        self._ecrire(html.encode("utf-8"), "text/html; charset=utf-8",
                     code, entetes)

    CHAMP = ("padding:10px 12px;border-radius:9px;border:1px solid #3a3540;"
             "background:#221e28;color:#eee")

    def _page_connexion(self, message="", code=401, email="", second=False):
        """The login page. `second` asks for the one-time code: the password
        has already been validated, we do not make them type it again."""
        erreur = ("<span class='tid' style='color:#f2a2a2'>%s</span>"
                  % html_escape(message)) if message else ""
        if CFG.get("auth_mode") == "interne":
            champs = [
                "<input name='email' type='email' autocomplete='username' required "
                "placeholder='Adresse email' value='%s' style='%s'%s>"
                % (html_escape(email), self.CHAMP, " readonly" if second else ""),
                "<input name='mdp' type='password' required "
                "autocomplete='current-password' placeholder='Mot de passe' "
                "style='%s'>" % self.CHAMP,
            ]
            if second:
                champs.append(
                    "<input name='code' inputmode='numeric' maxlength='6' required "
                    "autocomplete='one-time-code' autofocus "
                    "placeholder='Code à 6 chiffres' "
                    "style='%s;letter-spacing:.32em;text-align:center'>" % self.CHAMP)
            corps = ("<b>Connexion</b>" + erreur
                     + "<form method='post' action='/auth/connexion' "
                       "style='display:flex;flex-direction:column;gap:10px;"
                       "min-width:min(300px,80vw);margin-top:14px'>"
                     + "".join(champs)
                     + "<button type='submit' style='padding:10px 16px;"
                       "border-radius:9px;border:0;background:#e0a340;color:#17141a;"
                       "font-weight:600;cursor:pointer'>Se connecter</button></form>")
        else:
            corps = ("<b>Cette ludotheque est protegee</b>" + erreur
                     + "<p><a class='go' style='padding:9px 16px;border-radius:9px;"
                       "background:#e0a340;color:#17141a;text-decoration:none' "
                       "href='/auth/login'>Se connecter</a></p>")
        self._page("Connexion", corps, code=code)

    def _auth_route(self, p):
        """Return True when the request was handled by the SSO flow."""
        if p == "/auth/login":
            try:
                url, transit = auth.demarrer(CFG, self._base_retour())
            except Exception as exc:
                return self._page_connexion(str(exc)) or True
            self.send_response(302)
            self.send_header("Location", url)
            self.send_header("Set-Cookie", auth.entete_transit(transit, self._secure()))
            self.end_headers()
            return True

        if p == "/auth/callback":
            params = {k: v[0] for k, v in
                      parse_qs(self.path.partition("?")[2]).items()}
            try:
                session, qui = auth.terminer(
                    CFG, params, auth.transit(self.headers.get("Cookie")),
                    self._base_retour())
            except Exception as exc:
                JOB.log("Connexion refusee : %s" % exc, "warn")
                return self._page_connexion(str(exc)) or True
            JOB.log("Connexion de %s" % (qui.get("nom") or qui.get("sub")))
            journal_acces.noter("connexion", self.client_address[0],
                                qui.get("email") or qui.get("sub"), "sso")
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", auth.entete_cookie(session, self._secure()))
            self.send_header("Set-Cookie", auth.entete_transit("", self._secure()))
            self.end_headers()
            return True

        if p == "/auth/logout":
            qui = auth.session(self.headers.get("Cookie")) or {}
            journal_acces.noter("deconnexion", self.client_address[0], qui.get("email", ""))
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", auth.entete_cookie("", self._secure()))
            self.end_headers()
            return True

        if p == "/auth/moi":
            self._json({"actif": auth.actif(CFG),
                        "mode": auth.mode(CFG),
                        "demande": CFG.get("auth_mode", "aucun"),
                        "comptes": comptes.nombre(),
                        "incomplet": auth.incomplet(CFG),
                        "session": auth.session(self.headers.get("Cookie"))})
            return True
        return False

    def _connexion_interne(self):
        """Handle the email + password form. Always over POST."""
        if not self._meme_origine():
            return self._page_connexion("Requete rejetee : origine inattendue.", 403)
        n = min(int(self.headers.get("Content-Length", 0) or 0), 4096)
        champs = parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
        email = (champs.get("email") or [""])[0]
        try:
            u = comptes.connecter(email, (champs.get("mdp") or [""])[0],
                                  self.client_address[0],
                                  (champs.get("code") or [""])[0])
        except comptes.BesoinCode as exc:
            # The password is right: we only ask for the code again.
            journal_acces.noter("refus", self.client_address[0], email, str(exc))
            return self._page_connexion(str(exc), 401, email, second=True)
        except ValueError as exc:
            JOB.log("Connexion refusee pour %s depuis %s : %s"
                    % (email or "(vide)", self.client_address[0], exc), "warn")
            journal_acces.noter("refus", self.client_address[0], email, str(exc))
            return self._page_connexion(str(exc), 401, email)
        JOB.log("Connexion de %s depuis %s" % (u["email"], self.client_address[0]))
        journal_acces.noter("connexion", self.client_address[0], u["email"], "interne")
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie",
                         auth.entete_cookie(auth.session_interne(u), self._secure()))
        self.end_headers()

    def _binary(self, body, ctype):
        # PNGs and JPEGs come through here: `TYPES_GZIP` does not list them,
        # so they go out untouched. The manifest, on the other hand, is
        # compressed.
        self._ecrire(body, ctype, 200,
                     entetes=[("Cache-Control", "max-age=86400")])

    def do_GET(self):
        if not self._cadence_ok():
            return
        p = self.path.partition("?")[0]      # ignore ?token=... et autres parametres
        if p.startswith("/auth/") and self._auth_route(p):
            return
        if not self._allowed():
            return self._deny()
        if p == "/manifest.webmanifest":
            return self._binary(json.dumps(MANIFEST).encode(),
                                "application/manifest+json; charset=utf-8")
        if p.startswith("/icon-"):
            size = 512 if "512" in p else 192
            return self._binary(_png_icon(size), "image/png")
        if p.startswith(apiv1.PREFIXE):
            return self._api_v1(p, "GET")
        if p in ("/", "/index.html"):
            self._static("index.html")
        elif p in ("/app.js", "/app.css", "/reactive.js", "/theme.js"):
            self._static(p.lstrip("/"))
        elif p == "/api/scan":
            # `shop_text` carries the generation date: it changes every second
            # while the inventory itself is identical.
            #
            # `moi` tells the interface what it may SHOW. This is not a
            # security measure — `RESERVE_ADMIN` is what refuses, server-side,
            # and a test checks it. Hiding an action you cannot perform is a
            # courtesy: without it a non-administrator opens Settings and
            # collects 403s without understanding why.
            rep = _lib_response()
            rep["moi"] = self._moi()
            self._json_revalide(rep, volatiles=("shop_text", "moi"))
        elif p == "/api/job":
            self._json(JOB.snapshot())
        elif p == "/api/import-list":
            self._json({"items": actions.scan_import()})
        elif p == "/api/langues":
            self._json({"langues": _langues(), "courante": CFG.get("ui_lang", "en")})
        elif p.startswith("/locales/"):
            f = LOCALES / (p.rsplit("/", 1)[-1].replace("..", ""))
            if f.is_file() and f.suffix == ".json":
                # Translations change with the code: caching them for a day
                # means showing the old version after every upgrade. We
                # revalidate, as with the inventory.
                self._json_revalide(json.loads(f.read_text(encoding="utf-8")))
            else:
                self._json({"error": "langue inconnue"}, 404)
        elif p == "/api/maj":
            # Lazy: it returns what it knows and only goes out when the cache
            # is more than a day old. A GitHub outage answers "I don't know",
            # never an error — a failed check must not show.
            self._json(maj.etat(CFG))
        elif p == "/api/vues":
            self._json({"vues": vues.liste()})
        elif p == "/api/notifs":
            # The ADDRESS is never returned in full. A Discord webhook is a
            # bearer secret: whoever gets it can post in the channel. Showing it
            # in an HTTP response would put it in the browser history, in the
            # proxy's logs, and on any screenshot of the settings page.
            self._json({"destinations": [_notif_public(x)
                                         for x in notifs.destinations(CFG)],
                        "evenements": notifs.EVENEMENTS,
                        "services": list(notifs.SERVICES)})

        elif p == "/api/cles":
            # The interface is a browser with a session: it cannot go through
            # /api/v1, which requires a key in the first place. These three
            # internal routes manage the keys; they are not public and are
            # therefore not frozen.
            self._json({"cles": apikeys.liste(avec_revoquees=True)})
        elif p == "/api/trash-list":
            # Automatic purging only acts when the user set a delay: by
            # default (0) the trash is never emptied on its own.
            jours = CFG.get("trash_days", 0)
            if jours:
                n, octets = trash.purge(jours, JOB.log)
                if n:
                    JOB.log("Purge automatique : %d lot(s), %.1f Go liberes"
                            % (n, octets / 2 ** 30))
            self._json({"items": trash.listing(), "resume": trash.resume(),
                        "jours": jours})
        elif p == "/api/health":
            # The container's probe queries this route with GET. It was only
            # declared for POST: the Dockerfile's HEALTHCHECK had therefore been
            # getting "unknown route" all along, and the container could never
            # be declared healthy.
            self._json(_health())
        elif p == "/api/systems":          # lecture seule : accessible en GET
            self._json({"systems": systems.summary(CFG),
                        "roms_root": systems.roms_root(CFG),
                        # the drop folder uses this to filter, and so does the
                        # file-picker dialog
                        "extensions": sorted(systems.extensions_acceptees(CFG))})
        elif p == "/api/saves-list":
            self._json({"items": saves.listing(), "dirs": saves.find_dirs(CFG)})
        elif p == "/api/device":
            conn = device.connection()
            self._json({"state": device.state(), "connection": conn,
                        "info": device.info(), "volumes": device.volumes(),
                        "batterie": device.batterie(),
                        "wifi_addr": CFG.get("wifi_addr", "")})
        elif p.startswith("/photo/"):
            octets, mime = comptes.photo_lire(p[len("/photo/"):])
            if not octets:
                self.send_response(404)
                self.end_headers()
            else:
                self._binary(octets, mime)
        elif p.startswith("/cover/"):
            # self.path, not p: _cover needs the ?name=..., which the
            # search-by-name uses when the file carries no title ID.
            self._cover(self.path[len("/cover/"):])
        else:
            JOB.log("Route GET inconnue : %s" % p)
            self._json({"error": "route inconnue : " + p}, 404)

    def _cover(self, rest):
        tid_part, _, query = rest.partition("?")
        tid = "".join(c for c in tid_part if c in "0123456789abcdefABCDEF")[:16]
        name = None
        if query:
            vals = parse_qs(query).get("name")
            name = vals[0] if vals else None
        path = covers.fetch(tid, name, CFG)
        if not path:
            self.send_response(404)
            self.end_headers()
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    # ---------------------------------------------------------- POST

    def _upload(self):
        name = os.path.basename(unquote(self.headers.get("X-Filename", ""))).strip()
        # Every platform, not just the Switch: the tool knows how to file a GBA
        # ROM or a PS2 image, there is no reason to refuse one. A hand-added
        # platform brings its own extensions.
        permises = systems.extensions_acceptees(CFG)
        if not name or Path(name).suffix.lower() not in permises:
            return self._json(
                {"error": "Type non géré : %s. Formats acceptés : %s."
                          % (Path(name).suffix or "(sans extension)",
                             ", ".join(sorted(permises)))}, 400)
        config.IMPORT.mkdir(exist_ok=True)
        dest = config.IMPORT / name
        left = int(self.headers.get("Content-Length", 0))
        # Two refusals BEFORE opening the file: an upload with no ceiling let
        # any authorised device fill the host's disk, and a full disk breaks
        # more than the import — it breaks the library.
        if left > config.TELEVERSEMENT_MAX:
            return self._json(
                {"error": "Fichier trop volumineux : %s pour un maximum de %s."
                          % (_taille(left), _taille(config.TELEVERSEMENT_MAX))}, 413)
        try:
            libre = shutil.disk_usage(config.IMPORT).free
        except OSError:
            libre = None
        if libre is not None and left + config.DISQUE_MARGE > libre:
            return self._json(
                {"error": "Espace insuffisant : %s disponibles, %s demandes "
                          "(marge de securite de %s)."
                          % (_taille(libre), _taille(left),
                             _taille(config.DISQUE_MARGE))}, 507)
        try:
            with dest.open("wb") as fh:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    fh.write(chunk)
                    left -= len(chunk)
        except OSError as exc:
            return self._json({"error": str(exc)}, 500)
        JOB.log("Recu par glisser-deposer : %s" % name)
        self._json({"message": name, "size": dest.stat().st_size})

    def _admin_requis(self):
        """Return a reason to refuse, or "" when the caller may administer.

        The rule depends on the mode, and that is deliberate:

        * authentication ON  -> a session is required, and it must carry the
          administrator role;
        * authentication OFF -> there is no identity to check. Requiring a
          session would make the tool unusable in its most common mode.
          `_allowed()` has already decided: this caller is entitled to be here,
          and in that mode they have every right — the audit reports it as a
          point of attention, which it is.

        A case apart is creating the FIRST account: it must remain possible
        while no session can exist, but not from anywhere. Without that, "the
        first account is the administrator" would mean "the first person on the
        network becomes the administrator".
        """
        if not auth.actif(CFG):
            return ""
        # The anti-lockout session: handed to whoever just switched
        # authentication on from an already-authorised access, so they do not
        # lock themselves out. It therefore counts as administration —
        # otherwise enabling a mis-configured SSO would make the settings
        # unreachable to everybody, the person who just changed them included.
        jeton = auth.session(self.headers.get("Cookie"))
        if jeton and jeton.get("src") == "config":
            return ""
        if not auth.session(self.headers.get("Cookie")):
            return "Aucun compte connecte."
        if not self._est_admin():
            return "Reserve a un administrateur."
        return ""

    def _qui(self):
        """Compte INTERNE connecte, ou None.

        Returns nothing for an SSO session: there is no local record to
        return. `_est_admin()` is what answers the role question, for both
        sources.
        """
        s = auth.session(self.headers.get("Cookie"))
        return comptes.par_id(s.get("sub")) if s and s.get("src") == "interne" else None

    def _moi(self):
        """Who is looking, and with what role.

        `authentification` says whether there is an identity to have: without
        one, everybody is an administrator — Romule's most common mode, and the
        audit already reports it as a point of attention.
        """
        s = auth.session(self.headers.get("Cookie"))
        return {"authentification": bool(auth.actif(CFG)),
                "connecte": bool(s),
                "nom": (s or {}).get("nom") or "",
                "source": (s or {}).get("src") or "",
                "admin": (not auth.actif(CFG)) or self._est_admin()}

    def _est_admin(self):
        """The role, whatever the session came from.

        An internal account carries its role in the accounts file; an SSO
        session carries it in its token, written at login from the provider's
        groups. Without this second branch, `_qui()` recognising only internal
        accounts, NO SSO session could administer — and nothing allowed giving
        it the role.
        """
        s = auth.session(self.headers.get("Cookie"))
        if not s:
            return False
        if s.get("src") == "oidc":
            return bool(s.get("admin"))
        u = comptes.par_id(s.get("sub")) if s.get("src") == "interne" else None
        return bool(u and comptes.est_admin(u["id"]))

    def _photo_envoi(self):
        u = self._qui()
        if not u:
            return self._json({"error": "Aucun compte connecte."}, 401)
        taille = int(self.headers.get("Content-Length", 0) or 0)
        if taille > comptes.PHOTO_MAX:
            return self._json({"error": "Image trop lourde (maximum %d Mo)."
                               % (comptes.PHOTO_MAX // 2 ** 20)}, 413)
        try:
            d = comptes.photo_ecrire(u["id"], self.rfile.read(taille))
        except ValueError as exc:
            return self._json({"error": str(exc)}, 400)
        self._json({"message": "Photo mise a jour.", **d})

    def do_POST(self):
        if not self._cadence_ok():
            return
        if self.path.partition("?")[0] == "/auth/connexion":
            if CFG.get("auth_mode") != "interne":
                return self._json({"error": "connexion interne desactivee"}, 404)
            return self._connexion_interne()
        if not self._allowed():
            return self._deny()
        # Every POST changes state: we require that it comes from this page.
        if not self._meme_origine():
            JOB.log("POST rejete sur %s : origine %s"
                    % (self.path, self.headers.get("Origin") or "?"), "warn")
            return self._json({"error": "origine inattendue"}, 403)
        chemin = self.path.partition("?")[0]
        if chemin.startswith(apiv1.PREFIXE):
            return self._api_v1(chemin, "POST")
        if self.path == "/api/upload":
            return self._upload()
        if self.path == "/api/compte-photo":
            return self._photo_envoi()
        p = self.path
        try:
            d = self._payload()
        except (ValueError, OSError) as exc:
            JOB.log("Requete invalide sur %s : %s" % (p, exc))
            return self._json({"error": "requete invalide"}, 400)
        refus = self._reserve_admin(p)
        if refus:
            JOB.log("%s refuse : %s" % (p, refus), "warn")
            return self._json({"error": refus}, 403)
        try:
            self._route_post(p, d)
        except Exception as exc:
            JOB.log("Erreur serveur sur %s : %s" % (p, exc))
            self._json({"error": "%s : %s" % (p, exc)}, 500)

    # The role model said "only an administrator changes the configuration,
    # manages the accounts AND launches the destructive actions". The first two
    # were enforced route by route; the third was not. Concretely, any
    # non-administrator account could restore a backup — which contains the
    # accounts file, hence hands the administrator role back to whoever lost
    # it — clear the log, or read the access log.
    #
    # One list in one place rather than a call repeated across thirty branches:
    # a guard you must remember to add is a guard you forget. In the
    # no-authentication mode, `_admin_requis()` lets everything through: there
    # is no identity to tell apart, and `_allowed()` has already decided.
    RESERVE_ADMIN = frozenset({
        # --- erase or restore data
        "/api/sauvegarde-restaurer",   # contains the accounts file
        "/api/sauvegarde-creer",
        "/api/trash-purge",
        "/api/restore",
        "/api/covers-clear",
        "/api/meta-oublier",
        "/api/journal-clear",          # the first thing erased to cover tracks
        "/api/emuready-clear",
        # --- move files in bulk
        "/api/reorganize-local",
        "/api/device-organize",
        "/api/device-mktree",
        # --- write into another program's files
        "/api/eden-apply",
        "/api/eden-restore",
        "/api/eden-profile-save",
        "/api/eden-profile-apply",
        "/api/emuready-apply",
        "/api/nand-install",
        "/api/nand-write",
        # --- changent la liaison a la console
        "/api/wifi-pair",
        "/api/wifi-connect",
        "/api/wifi-switch",
        "/api/wifi-forget",
        # --- choose where the service reads and writes on the host
        "/api/parcourir",             # reveals the host's directory tree
        "/api/ludotheque",
        # --- send outward in the service's name
        "/api/notifs",              # the addresses are bearer secrets
        "/api/notif-creer",
        "/api/notif-supprimer",
        "/api/notif-tester",        # otherwise: a port scanner by proxy
        # --- report on who connects, and on the security posture
        "/api/acces",
        "/api/audit",
        "/api/auth-test",
    })

    def _reserve_admin(self, p):
        """A reason to refuse when the route requires the administrator role."""
        return self._admin_requis() if p in self.RESERVE_ADMIN else ""

    def _route_post(self, p, d):
        if p == "/api/versions":
            versions.load(LIB, force=bool(d.get("force")), log=JOB.log)
            self._json(_lib_response())

        elif p == "/api/vue-creer":
            v = vues.creer(d.get("nom"), d.get("filtres"))
            if not v:
                return self._json({"error": "Trop de vues enregistrees (%d)."
                                   % vues.MAX_VUES}, 400)
            self._json({"vue": v, "vues": vues.liste()})

        elif p == "/api/vue-supprimer":
            vues.supprimer(str(d.get("id") or ""))
            self._json({"vues": vues.liste()})

        elif p == "/api/notif-creer":
            url = str(d.get("url") or "").strip()
            if not url:
                return self._json({"error": "An address is required."}, 400)
            try:
                reseau.verifier(url)
            except reseau.SchemaRefuse as exc:
                # The same check as for cover art and the OIDC issuer: a
                # settings field must not be able to make the server read a
                # local file.
                return self._json({"error": str(exc)}, 400)
            liste = list(CFG.get("notif_destinations") or [])
            if len(liste) >= notifs.MAX_DESTINATIONS:
                return self._json({"error": "Too many destinations (%d)."
                                   % notifs.MAX_DESTINATIONS}, 400)
            liste.append({"id": secrets.token_hex(8),
                          "nom": str(d.get("nom") or "")[:60],
                          "url": url,
                          "service": d.get("service"),
                          "evenements": d.get("evenements") or [],
                          "actif": True})
            CFG["notif_destinations"] = liste
            config.save_config(CFG)
            JOB.log("Destination de notification ajoutee : %s"
                    % (d.get("nom") or notifs.deviner(url)))
            self._json({"destinations": [_notif_public(x)
                                         for x in notifs.destinations(CFG)]})

        elif p == "/api/notif-supprimer":
            nid = str(d.get("id") or "")
            CFG["notif_destinations"] = [x for x in (CFG.get("notif_destinations") or [])
                                         if str(x.get("id")) != nid]
            config.save_config(CFG)
            self._json({"destinations": [_notif_public(x)
                                         for x in notifs.destinations(CFG)]})

        elif p == "/api/notif-tester":
            # Two cases: an address typed but not yet saved, or an existing
            # destination — whose URL never leaves the server and must
            # therefore be found by its identifier.
            url = str(d.get("url") or "").strip()
            if not url:
                cible = next((x for x in notifs.destinations(CFG)
                              if x["id"] == str(d.get("id") or "")), None)
                if not cible:
                    return self._json({"error": "Unknown destination."}, 404)
                url, service = cible["url"], cible["service"]
            else:
                service = d.get("service")
            reussi, raison = notifs.tester(url, service)
            self._json({"ok": reussi, "detail": raison})

        elif p == "/api/cle-creer":
            fiche, cle = apikeys.creer(d.get("nom") or "")
            JOB.log("Cle d'API creee : %s" % fiche["nom"])
            # The plaintext key goes out HERE and only once: it is stored as a
            # digest and nothing else.
            self._json({"cle": fiche, "secret": cle})

        elif p == "/api/cle-revoquer":
            cid = str(d.get("id") or "")
            fait = apikeys.revoquer(cid)
            if fait:
                JOB.log("Cle d'API revoquee : %s" % cid)
            self._json({"ok": fait})

        elif p == "/api/convert":
            self._job(actions.convert_files, LIB, CFG, JOB, d.get("paths", []))

        elif p == "/api/push":
            self._job(actions.push_files, LIB, CFG, JOB, d.get("paths", []))

        elif p == "/api/reorganize-local":
            self._job(actions.reorganize_local, LIB, CFG, JOB)

        elif p == "/api/import":
            self._job(actions.import_files, LIB, CFG, JOB, bool(d.get("convert", True)))

        elif p == "/api/trash":
            n, where = trash.move(d.get("paths", []),
                                  "ecarte depuis l'interface web", JOB.log)
            # We return FACTS, not a sentence. The sentence used to be
            # composed here, in French, and showed as-is in an English
            # interface — Romule's i18n lives entirely in the browser. `lot` is
            # the timestamped folder's name: it is what `/api/restore` expects,
            # so it is what makes the undo possible.
            self._json({"n": n, "dossier": where,
                        "lot": where.rsplit("/", 1)[-1]})

        # ---- comptes internes
        elif p == "/api/comptes":
            self._json({"comptes": comptes.liste(),
                        "moi": (self._qui() or {}).get("id", ""),
                        "mdp_min": comptes.MDP_MIN})

        elif p == "/api/compte-creer":
            if not comptes.liste():
                # The very first account: it becomes the administrator, so its
                # creation cannot be open to the network. Otherwise "the first
                # account governs" would mean "the first device on the network
                # governs" — and passwordless network access is a mode the tool
                # offers.
                if not self._local():
                    return self._json(
                        {"error": "Le premier compte se cree depuis la machine "
                                  "qui heberge la ludotheque."}, 403)
            else:
                refus = self._admin_requis()
                if refus:
                    return self._json({"error": refus}, 403)
            try:
                u = comptes.creer(d.get("email", ""), d.get("mdp", ""), d.get("nom", ""))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            sauvegarde.auto("comptes")
            JOB.log("Compte cree : %s" % u["email"])
            journal_acces.noter("compte", self.client_address[0], u["email"], "creation")
            self._json({"message": "Compte cree pour %s." % u["email"],
                        "compte": u, "comptes": comptes.liste()})

        elif p == "/api/compte-modifier":
            u = self._qui()
            if not u:
                return self._json({"error": "Aucun compte connecte."}, 401)
            try:
                v = comptes.modifier(u["id"], d.get("nom"), d.get("email"))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            self._json({"message": "Profil enregistre.", "compte": v})

        elif p == "/api/compte-mdp":
            u = self._qui()
            if not u:
                return self._json({"error": "Aucun compte connecte."}, 401)
            try:
                comptes.changer_mdp(u["id"], d.get("ancien", ""), d.get("nouveau", ""))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            JOB.log("Mot de passe change : %s" % u["email"])
            journal_acces.noter("compte", self.client_address[0], u["email"],
                                "mot de passe change")
            # The current session was signed before the change: we hand THIS
            # browser a valid one, the others are cut.
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", auth.entete_cookie(
                auth.session_interne(comptes.par_id(u["id"])), self._secure()))
            corps = json.dumps({"message": "Mot de passe change. Les autres "
                                           "appareils ont ete deconnectes."}).encode()
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        elif p == "/api/compte-supprimer":
            refus = self._admin_requis()
            if refus:
                return self._json({"error": refus}, 403)
            try:
                comptes.supprimer(d.get("id", ""))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            JOB.log("Compte supprime.")
            self._json({"message": "Compte supprime.", "comptes": comptes.liste()})

        elif p == "/api/compte-totp-preparer":
            u = self._qui()
            if not u:
                return self._json({"error": "Aucun compte connecte."}, 401)
            self._json(comptes.totp_preparer(u["id"]))

        elif p == "/api/compte-totp-activer":
            u = self._qui()
            if not u:
                return self._json({"error": "Aucun compte connecte."}, 401)
            try:
                comptes.totp_activer(u["id"], d.get("code", ""))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            journal_acces.noter("compte", self.client_address[0], u["email"],
                                "double facteur active")
            self._json({"message": "Double authentification activée."})

        elif p == "/api/compte-totp-desactiver":
            u = self._qui()
            if not u:
                return self._json({"error": "Aucun compte connecte."}, 401)
            try:
                comptes.totp_desactiver(u["id"], d.get("mdp", ""))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            journal_acces.noter("compte", self.client_address[0], u["email"],
                                "double facteur desactive")
            self._json({"message": "Double authentification retirée."})

        elif p == "/api/compte-photo-effacer":
            u = self._qui()
            if not u:
                return self._json({"error": "Aucun compte connecte."}, 401)
            comptes.photo_effacer(u["id"])
            self._json({"message": "Photo retiree."})

        elif p == "/api/sgdb-test":
            ok, msg = covers.tester_cle(CFG)
            self._json({"ok": ok, "message": msg})

        elif p == "/api/igdb-test":
            try:
                self._json({"ok": True, "infos": igdb.tester(CFG)})
            except Exception as exc:
                self._json({"ok": False, "message": str(exc)})

        elif p == "/api/transfert-etat":
            self._json({"reprise": transferts.resume()})

        elif p == "/api/transfert-reprendre":
            r = transferts.resume()
            if not r:
                return self._json({"error": "Aucun transfert a reprendre."}, 400)
            self._job(actions.deploy_games, LIB, CFG, JOB, r["chemins"], [], [])

        elif p == "/api/transfert-oublier":
            transferts.terminer()
            self._json({"message": "Reprise abandonnée."})

        elif p == "/api/import-suggestions":
            self._json({"items": actions.suggestions_import(CFG)})

        elif p == "/api/import-classer":
            n = actions.classer_import(CFG, JOB, d.get("assignations") or {})
            LIB.scan(log=JOB.log)
            self._json({"message": "%d fichier(s) rangé(s)." % n,
                        "items": actions.scan_import()})

        elif p == "/api/doublons":
            r = doublons.rapport(LIB, CFG)
            # The full entries are heavy: the client only needs the name, the
            # size and the path in order to decide.
            def _leger(e):
                return {"nom": e["nom"], "chemin": e["chemin"],
                        "taille": e["taille"], "plateforme": e["plateforme"]}
            self._json({
                "identiques": r["identiques"][:50],
                "multi_plateformes": [{"titre": x["titre"],
                                       "plateformes": x["plateformes"],
                                       "entrees": [_leger(e) for e in x["entrees"]]}
                                      for x in r["multi_plateformes"][:50]],
                "regions": [{"titre": x["titre"], "plateforme": x["plateforme"],
                             "octets": x["octets"],
                             "entrees": [_leger(e) for e in x["entrees"]]}
                            for x in r["regions"][:50]],
                "recuperable": r["recuperable"]})

        elif p == "/api/integrite":
            self._json({"resume": integrity.resume(LIB.files)})

        elif p == "/api/sauvegardes":
            self._json({"lots": sauvegarde.listing()})

        elif p == "/api/sauvegarde-creer":
            self._json({"message": "Sauvegarde enregistree.",
                        **sauvegarde.creer("manuelle"),
                        "lots": sauvegarde.listing()})

        elif p == "/api/sauvegarde-restaurer":
            try:
                remis = sauvegarde.restaurer(d.get("lot", ""))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            CFG.clear()
            CFG.update(config.load_config())
            JOB.log("Configuration restauree : %s" % ", ".join(remis), "warn")
            self._json({"message": "Restauré : %s. L'état précédent a été "
                                   "sauvegardé avant." % ", ".join(remis),
                        "lots": sauvegarde.listing()})

        elif p == "/api/acces":
            self._json({"resume": journal_acces.resume(),
                        "evenements": journal_acces.dernieres(120)})

        elif p == "/api/audit":
            self._json(audit.lancer(CFG, hors_ligne=bool(d.get("hors_ligne"))))

        elif p == "/api/auth-test":
            try:
                self._json({"ok": True, "infos": auth.tester(CFG),
                            "retour": self._base_retour()})
            except Exception as exc:
                self._json({"ok": False, "message": str(exc),
                            "retour": self._base_retour()})

        elif p == "/api/library-all":
            self._json({"systemes": systems.tout(CFG)})

        elif p == "/api/console-analyse":
            self._job(actions.analyser_console, LIB, CFG, JOB)

        elif p == "/api/systems-detect":
            self._json(systems.detect_on_device(CFG))

        elif p == "/api/meta-oublier":
            # Force the details to be fetched again: we clear the cache, not
            # the covers already downloaded (they have their own button).
            n = 0
            for f in config.COVERS.glob("*.fiche.json"):
                try:
                    f.unlink(); n += 1
                except OSError:
                    pass
            for f in config.COVERS.glob("*.json"):
                if f.name.endswith(".fiche.json"):
                    continue
                try:
                    f.unlink(); n += 1
                except OSError:
                    pass
            JOB.log("%d fiche(s) oubliee(s) : elles seront retelechargees." % n)
            self._json({"message": "%d fiche(s) à retélécharger." % n})

        elif p == "/api/meta-sync":
            self._job(actions.sync_meta, LIB, CFG, JOB)

        elif p == "/api/trash-purge":
            jours = d.get("jours", CFG.get("trash_days", 0))
            n, octets = trash.purge(jours, JOB.log)
            self._json({"message": "%d lot(s) purge(s), %.1f Go liberes"
                        % (n, octets / 2 ** 30) if n
                        else "Rien a purger (aucun lot au-dela du delai).",
                        "resume": trash.resume()})

        elif p == "/api/restore":
            self._json({"message": trash.restore(d.get("name", ""))})

        elif p == "/api/nand-write":
            n = scan.write_nand_list(LIB.nand_rows())
            self._json({"message": "%d ligne(s) ecrite(s) dans %s"
                        % (n, config.NAND_LIST.name)})

        elif p == "/api/device-browse":
            self._json({"items": device.list_dir(d.get("path", CFG["device_dir"]))})

        # ---- where the games are, on the machine hosting the service
        elif p == "/api/parcourir":
            self._json(parcourir.lister(d.get("chemin", ""), CFG))

        elif p == "/api/ludotheque":
            # A running job holds absolute paths already computed: moving the
            # library out from under it would write a conversion into the old
            # folder, or fail a move halfway. We refuse; we do not queue.
            if JOB.running:
                return self._json(
                    {"error": "un travail est en cours — reessaie apres"}, 409)
            souci = config.definir_ludotheque(d.get("chemin", ""),
                                              creer=bool(d.get("creer")))
            if souci:
                return self._json({"error": souci}, 400)
            # Empty when the choice falls back to the service folder: the
            # configuration then says "default", and will follow the day the
            # deployment changes that folder.
            CFG["library_path"] = ("" if config.LUDO == config.ROOT
                                   else str(config.LUDO))
            config.save_config(CFG)
            JOB.log("Ludotheque : %s" % config.LUDO)
            self._json(_lib_response())

        elif p == "/api/device-games":
            games = device.find_games(d.get("root", CFG["device_dir"]))
            device.reconcile(games, LIB.files)
            device.analyze(games)
            new = sum(1 for g in games if not g["in_library"])
            self._json({"games": games, "total": len(games), "new": new})

        elif p == "/api/device-import":
            self._job(actions.import_from_device, LIB, CFG, JOB,
                      d.get("paths", []), bool(d.get("convert", True)))

        elif p == "/api/device-remove":
            self._job(actions.remove_from_device, LIB, CFG, JOB, d.get("paths", []))

        elif p == "/api/device-detect-dir":
            self._json({"dir": device.detect_games_dir()})

        # ---- setting up access on the console
        elif p == "/api/emulateur-detecter":
            # The Android package name changes from one emulator version to
            # the next. We ask the console which one is installed and remember
            # it, rather than asking again on every render.
            refus = self._admin_requis()
            if refus:
                return self._json({"error": refus}, 403)
            trouve = profils.detecter(CFG)
            if trouve:
                CFG["emulateur_paquet"] = trouve
                config.save_config(CFG)
                JOB.log("Emulateur detecte sur la console : %s" % trouve)
            self._json({"paquet": trouve})

        elif p == "/api/health":
            self._json(_health())

        elif p == "/api/console-url":
            ip = _lan_ip()
            self._json({"ip": ip, "port": config.PORT,
                        "url": "http://%s:%d" % (ip, config.PORT) if ip else None,
                        "lan": bool(CFG.get("lan_access")),
                        "connected": device.connection()["kind"]})

        elif p == "/api/console-open":
            ip = _lan_ip()
            if not ip:
                self._json({"ok": False, "message": "Adresse reseau du serveur introuvable."})
            elif not CFG.get("lan_access"):
                self._json({"ok": False, "message": "Active d'abord l'acces reseau (Reglages)."})
            elif device.connection()["kind"] is None:
                self._json({"ok": False, "message": "Connecte d'abord la console."})
            else:
                url = "http://%s:%d" % (ip, config.PORT)
                ok, msg = device.open_url(url)
                if ok:
                    JOB.log("Interface ouverte sur la console : %s" % url)
                self._json({"ok": ok, "url": url,
                            "message": msg or ("Ouvert sur la console : %s" % url)})

        # ---- wireless connection
        elif p == "/api/wifi-switch":
            ok, addr, msg = device.switch_to_wifi()
            if ok:
                CFG["wifi_addr"] = addr
                config.save_config(CFG)
                JOB.log("Console basculee en wifi : %s" % addr)
            self._json({"ok": ok, "addr": addr, "message": msg})

        elif p == "/api/wifi-pair":
            ok, msg = device.pair(d.get("addr", "").strip(), d.get("code", "").strip())
            found = device.discover() if ok else []
            addr = None
            if ok and found:
                cok, cmsg = device.connect(found[0])
                if cok:
                    addr = found[0]
                    CFG["wifi_addr"] = addr
                    config.save_config(CFG)
                    msg = "Appairee et connectee (%s)." % addr
                else:
                    msg = "Appairee, mais connexion refusee : %s" % cmsg
            self._json({"ok": ok, "addr": addr, "found": found, "message": msg})

        elif p == "/api/wifi-connect":
            addr = (d.get("addr") or CFG.get("wifi_addr") or "").strip()
            ok, msg = device.connect(addr)
            if ok:
                CFG["wifi_addr"] = addr
                config.save_config(CFG)
            self._json({"ok": ok, "addr": addr, "message": msg})

        elif p == "/api/wifi-discover":
            self._json({"found": device.discover()})

        elif p == "/api/wifi-forget":
            device.disconnect(CFG.get("wifi_addr") or None)
            CFG["wifi_addr"] = ""
            config.save_config(CFG)
            self._json({"ok": True, "message": "Connexion sans fil oubliee."})

        elif p == "/api/device-tree":
            self._json({"tree": device.tree_status(CFG["device_dir"])})

        elif p == "/api/device-mktree":
            JOB.log("Creation de l'arborescence GAMES/UPDATE/DLC sur la console.")
            self._json({"tree": device.make_tree(CFG["device_dir"])})

        elif p == "/api/device-organize":
            self._job(actions.organize_device, LIB, CFG, JOB)

        elif p == "/api/game-meta":
            self._json({"meta": meta.fetch(d.get("tid"), CFG)})

        elif p == "/api/push-plan":
            layout = d.get("layout", CFG.get("push_layout", "type"))
            items = device.plan(d.get("paths", []), CFG["device_dir"], layout,
                                CFG.get("incremental", True),
                                {f["path"]: f["type"] for f in LIB.files})
            todo = [i for i in items if not i["skip"] and not i.get("broken")]
            self._json({
                "plan": items,
                "total": sum(i["size"] for i in items),
                "to_send": sum(i["size"] for i in todo),
                "skipped": sum(1 for i in items if i["skip"] and not i.get("broken")),
                "broken": sum(1 for i in items if i.get("broken")),
                "free": device.free_of(CFG["device_dir"]),
                "device_dir": CFG["device_dir"],
                "layout": layout,
            })

        elif p == "/api/covers-clear":
            self._json({"message": "%d jaquette(s) effacee(s)." % covers.clear()})

        # ---- multi-systemes
        elif p == "/api/systems":
            self._json({"systems": systems.summary(CFG),
                        "roms_root": systems.roms_root(CFG)})

        elif p == "/api/system-games":
            key = d.get("system", "switch")
            dossier = systems.device_dir(key, CFG)
            # What is already on the console for THIS system: without this
            # list the other consoles had no state at all, unlike the Switch.
            distants = []
            if dossier and device.state() == "device":
                distants = [
                    {"nom": g["name"], "chemin": g["path"], "taille": g["size"],
                     **systems._fiche_legere(meta.fiche_nom(g["name"], CFG, reseau=False))}
                    for g in device.find_games(dossier, systems.get_cfg(key, CFG)["exts"])]
            self._json({"system": key, "games": systems.scan_local(key, CFG),
                        "console": distants, "device_dir": dossier})

        elif p == "/api/system-push":
            self._job(actions.push_system, LIB, CFG, JOB,
                      d.get("system", ""), d.get("paths", []))

        elif p == "/api/system-import":
            self._job(actions.import_system_files, LIB, CFG, JOB, d.get("system", ""))

        # ---- integrite / sauvegardes
        elif p == "/api/verify":
            self._job(actions.verify_library, LIB, CFG, JOB,
                      bool(d.get("deep")), d.get("system"), d.get("budget_go"))

        elif p == "/api/deploy":
            self._job(actions.deploy_games, LIB, CFG, JOB,
                      d.get("envoyer", []), d.get("activer", []), d.get("configs", []))

        elif p == "/api/nand-install":
            self._job(actions.install_nand, LIB, CFG, JOB, d.get("paths", []))

        # ---- EmuReady (beta) : reglages recommandes par la communaute
        elif p == "/api/emuready-state":
            c = emuready.cached()
            self._json({"actif": bool(CFG.get("emuready")),
                        "appareil": CFG.get("emuready_device", ""),
                        "appareil_nom": CFG.get("emuready_device_nom", ""),
                        "jeux": c.get("jeux", {}), "maj": c.get("maj", 0)})

        elif p == "/api/emuready-devices":
            modele = (device.info() or {}).get("model") or ""
            self._json({"suggestions": emuready.suggest_devices(modele),
                        "tous": emuready.devices(d.get("recherche", "")),
                        "modele_detecte": modele})

        elif p == "/api/emuready-sync":
            self._job(actions.emuready_sync, LIB, CFG, JOB, bool(d.get("force")))

        elif p == "/api/emuready-game":
            tid = (d.get("tid") or "").lower()
            self._json({"tid": tid, "entree": emuready.cached()["jeux"].get(tid)})

        elif p == "/api/emuready-preview":
            try:
                contenu = emuready.config_of(d.get("listing_id", ""))
                data = edenconf.parse(contenu)
                self._json({"contenu": contenu, "sections": len(data),
                            "surcharges": contenu.count("use_global=false"),
                            "octets": len(contenu)})
            except Exception as exc:
                self._json({"error": "configuration indisponible : %s" % exc})

        elif p == "/api/eden-backups":
            self._json({"items": edenconf.backups_for(d.get("tid", ""))})

        elif p == "/api/eden-restore":
            self._job(actions.restore_eden_config, LIB, CFG, JOB,
                      (d.get("tid") or "").upper(), d.get("fichier", ""))

        elif p == "/api/emuready-apply":
            self._job(actions.emuready_apply, LIB, CFG, JOB,
                      d.get("listing_id", ""), (d.get("tid") or "").upper())

        elif p == "/api/emuready-clear":
            emuready.clear()
            self._json({"message": "Cache EmuReady vide."})

        # ---- Eden's configuration
        elif p in ("/api/eden-config", "/api/eden-apply", "/api/emuready-apply") \
                and not edenconf.pilotable():
            # Not every emulator exposes settings we know how to read:
            # Ryujinx keeps them in JSON, with a different layout. Better to say
            # so than to write at random into its files.
            return self._json(
                {"error": "Les reglages de %s ne sont pas pilotables depuis "
                          "Romule." % profils.actif(CFG)["nom"]}, 400)

        elif p == "/api/eden-config":
            tid = (d.get("tid") or "").strip() or None
            texte, data = edenconf.read_config(tid)
            self._json({"tid": tid, "existe": bool(texte.strip()),
                        "valeurs": edenconf.to_dict(data),
                        "jeux": edenconf.games_with_config()})

        elif p == "/api/eden-apply":
            self._job(actions.apply_eden_config, LIB, CFG, JOB,
                      d.get("changements", {}), d.get("tid"))

        elif p == "/api/eden-profiles":
            self._json({"profils": edenconf.profile_list()})

        elif p == "/api/eden-profile-save":
            vals = d.get("valeurs") or edenconf.capture(
                (d.get("tid") or "").strip() or None, d.get("sections"))
            nom = edenconf.profile_save(d.get("nom", "profil"), vals,
                                        d.get("portee", "global"),
                                        d.get("description", ""))
            self._json({"nom": nom, "profils": edenconf.profile_list()})

        elif p == "/api/eden-profile-apply":
            self._job(actions.apply_eden_profile, LIB, CFG, JOB,
                      d.get("nom", ""), d.get("tid"))

        elif p == "/api/nand-status":
            rows = LIB.nand_rows()
            branchee = device.connection()["kind"] is not None
            inst = nand.installed_ids() if branchee else False
            etats = {e["path"]: e for e in nand.status([f["path"] for f in rows], inst)}
            items = []
            for f in rows:
                e = etats.get(f["path"], {})
                items.append({"path": f["path"], "rel": f["rel"], "type": f["type"],
                              "tid": f["tid"], "name": f["name"], "size": f["size"],
                              "etat": e.get("etat", "inconnu"),
                              "contenus": e.get("contenus", 0)})
            self._json({"items": items, "connectee": branchee,
                        "installes": len(inst) if isinstance(inst, set) else 0})

        elif p == "/api/nand-inspect":
            out, err = [], []
            for x in d.get("paths", []):
                try:
                    out.append(nand.inspect(x))
                except Exception as exc:
                    err.append({"fichier": x.rsplit("/", 1)[-1], "erreur": str(exc)})
            self._json({"items": out, "erreurs": err,
                        "installed": len(nand.installed_ids())})

        elif p == "/api/saves-backup":
            self._job(actions.backup_saves, LIB, CFG, JOB)

        elif p == "/api/saves-list":
            self._json({"items": saves.listing(), "dirs": saves.find_dirs(CFG)})

        # ---- controle de la tache en cours
        elif p == "/api/journal-clear":
            JOB.clear()
            JOB.log("Journal efface.", "info")
            self._json(JOB.snapshot())

        elif p == "/api/job-control":
            act = d.get("action")
            if act == "pause":
                JOB.pause()
            elif act == "resume":
                JOB.resume()
            elif act == "cancel":
                JOB.cancel()
            self._json(JOB.snapshot())

        elif p == "/api/config":
            # The state BEFORE any change: `CFG` is mutated just after, so
            # reading it later would always answer "already active".
            refus = self._admin_requis()
            if refus:
                return self._json({"error": refus}, 403)
            avant = auth.actif(CFG)
            # A field returned masked means "do not change": otherwise saving
            # the settings would erase the secret every time.
            for k in SECRETS:
                if d.get(k) == MASQUE:
                    d.pop(k)
            # A CLOSED list of the settings a client may write. A key declared
            # in `config.DEFAULTS`, shown by the interface, and missing from
            # here produces the worst behaviour there is: the field fills in,
            # the server answers 200, and nothing changes. `oidc_admin_groupes`
            # and `emulateur` were in that state — choosing an emulator profile
            # did not save it. `test_reglages.py` now compares this list against
            # `DEFAULTS` in both directions.
            for k in ("device_dir", "jobs", "push_layout", "verify_mode",
                      "incremental", "cover_provider", "cover_url",
                      "steamgriddb_key", "igdb_client_id", "igdb_client_secret",
                      "meta_lang", "local_layout",
                      "versions_urls", "lan_access", "notify", "roms_root",
                      "saves_dir", "emuready", "emuready_device",
                      "emuready_device_nom", "ui_lang", "auto_nand",
                      "trash_days", "system_dirs", "systemes_perso", "auth_mode",
                      "oidc_issuer", "oidc_client_id", "oidc_client_secret",
                      "oidc_scopes", "oidc_redirect", "oidc_emails",
                      "oidc_groupes", "oidc_admin_groupes", "emulateur",
                      "maj_check"):
                if k in d:
                    CFG[k] = d[k]
            # Hand-added platforms are sanitised ON WRITE, not only on read.
            # `systems.liste()` already puts the folder through `dossier_sur`,
            # so nothing escapes today — but keeping a `../../..` in the
            # configuration file arms the trap for the next person who reads
            # that field directly.
            if "systemes_perso" in d:
                CFG["systemes_perso"] = systems.assainir_perso(CFG["systemes_perso"])
            config.save_config(CFG)
            sauvegarde.auto("reglages")
            JOB.notify_end = bool(CFG.get("notify", True))

            # Switching authentication on from a browser that has no session
            # yet ejected it immediately: the NEXT request got the login page,
            # including the one that would have undone the change. Whoever just
            # made that change was entitled to: we open them a session.
            corps = json.dumps({"config": _config_publique()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if (not avant and auth.actif(CFG)
                    and not auth.session(self.headers.get("Cookie"))):
                u = None
                if CFG.get("auth_mode") == "interne":
                    liste = comptes.liste()
                    u = comptes.par_id(liste[0]["id"]) if liste else None
                # This token is tied to no account: it is a bridge, just long
                # enough to finish configuring and log in properly. Giving it
                # the twelve hours of a real session made it an anonymous
                # administrator access lasting half a day.
                jeton = (auth.session_interne(u) if u else
                         auth._signer({"sub": "local", "nom": "Accès local",
                                       "email": "", "src": "config",
                                       "exp": time.time() + auth.DUREE_PONT}))
                self.send_header("Set-Cookie", auth.entete_cookie(jeton, self._secure()))
                JOB.log("Authentification activée : ce navigateur reste connecté.",
                        "warn")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        else:
            JOB.log("Route POST inconnue : %s (serveur a jour ?)" % p)
            self._json({"error": "route inconnue : " + p}, 404)

    def _api_v1(self, chemin, methode):
        """The public surface. It shares NOTHING with the internal routing:
        that is what allows promising it will not move while the interface goes
        on evolving."""
        params = parse_qs(self.path.partition("?")[2])
        try:
            reponse = apiv1.router(chemin, params, methode, _contexte_v1())
        except Exception as exc:
            JOB.log("Erreur API v1 sur %s : %s" % (chemin, exc), "warn")
            # The exception message is not returned: it often carries an
            # absolute path, hence the server's directory tree.
            return self._json({"error": "internal_error",
                               "message": "The request could not be served."},
                              500)
        if reponse is None:
            return self._json({"error": "not_found",
                               "message": "Unknown route. See "
                                          "/api/v1/openapi.json."}, 404)
        code, corps = reponse
        self._json(corps, code)

    def _job(self, fn, *args):
        ok = JOB.start(fn.__name__, fn, *args)
        self._json({} if ok else {"error": "Une tache est deja en cours."})


DEMARRAGE = time.time()


def _inventaire_v1():
    """The enriched inventory, without the shopping list or the paste-ready text.

    `_lib_response()` also builds what a screen needs — the shopping list, its
    text rendering, the files waiting to be imported. The API has no use for
    that, and `shopping_text` changes every second, which would make any
    client-side caching pointless.
    """
    LIB.scan(log=JOB.log)
    LIB.enrich()
    return {"files": LIB.files, "stats": LIB.stats()}


def _lancer_v1(quoi):
    """Return (started, reason). One task at a time: that is how Romule works,
    and the API says so rather than pretending there is a queue."""
    if JOB.snapshot()["running"]:
        return False, "Another task is already running."
    if quoi == "scan":
        return JOB.start("scan", _inventaire_v1), ""
    if quoi == "convert":
        return JOB.start("convert", actions.convert_files, LIB, CFG, JOB, []), ""
    if quoi == "push":
        return JOB.start("push", actions.push_files, LIB, CFG, JOB, []), ""
    return False, "Unknown task."


def _contexte_v1():
    return {
        "health": _health,
        "demarrage": DEMARRAGE,
        "inventaire": _inventaire_v1,
        "plateformes": lambda: systems.summary(CFG),
        "console": device.state,
        "job": JOB.snapshot,
        "corbeille": trash.listing,
        "lancer": _lancer_v1,
    }


def _health():
    """Etat de preparation : sert a la sonde Docker et au parcours de demarrage."""
    keyfile = LIB.keyfile
    conn = device.connection()
    return {
        "ok": True,
        # The AGPL requires that a user reaching the service over the network
        # be able to obtain its source. Saying it here makes it readable by a
        # tool as much as by the interface.
        "version": __version__,
        "licence": LICENCE,
        "source": SOURCE_URL,
        "first_run": not config.CONFIG_FILE.exists(),
        "root": str(config.ROOT),
        # The library is distinct from the service root: it is the one the
        # wizard and the settings offer to choose.
        "ludotheque": str(config.LUDO),
        "ludotheque_imposee": config.LUDO_IMPOSEE,
        "problemes": list(config.PROBLEMES),
        "checks": {
            "nsz": bool(shutil.which("nsz")),
            "adb": device.adb_available(),
            "keys": keyfile.exists(),
            "keys_path": str(keyfile),
            "library": len(LIB.files),
            "versions": bool(LIB.versions),
            "device": conn["kind"],
            "device_dir": CFG.get("device_dir", ""),
            "lan": bool(CFG.get("lan_access")),
            "token": bool(config.TOKEN),
            # The browser needs this BEFORE sending: refusing mid-transfer
            # cuts the connection, and the message never arrives.
            "televersement_max": config.TELEVERSEMENT_MAX,
            "container": _in_container(),
            # Installation advice suited to THIS machine. The wizard used to
            # show a Homebrew command to everyone, including on a Debian NAS or
            # inside a container.
            "remede_nsz": cli.remede("nsz"),
            "remede_adb": cli.remede("adb"),
            # Enough to judge whether access must be protected BEFORE anything
            # else: a service reachable over the network with no authentication
            # is the worst defect a fresh installation can have.
            "ecoute": _adresse_ecoute(),
            "expose": _adresse_ecoute() != "127.0.0.1",
            "auth_mode": CFG.get("auth_mode", "aucun"),
            "comptes": len(comptes.liste()),
            "emulateur": CFG.get("emulateur") or profils.DEFAUT,
        },
        "profils": profils.public(),
    }


def _adresse_ecoute():
    """Sur quelle interface se poser.

    The socket used to be bound to `0.0.0.0` in all circumstances, with
    filtering done request by request. That works, but it exposes a port to the
    whole network for an installation its owner believes local — and any error
    in the filtering becomes immediately reachable from anywhere.

    So we only open on an explicit decision. In a container, the decision is
    made by whoever publishes the port: staying on 127.0.0.1 there would make
    the application unreachable.
    """
    if config.env("BIND", "").strip():
        return config.env("BIND").strip()
    ouvert = (CFG.get("lan_access") or config.ENV_LAN or config.TOKEN
              or _in_container())
    # bandit flags any listen on 0.0.0.0. Here it is CONDITIONAL: it only
    # happens when the operator has opened access (the `lan_access` setting,
    # ROMULE_LAN, a token set, or a container — where listening locally would
    # be pointless since the port is published). The default stays 127.0.0.1.
    # That is precisely what the tool cannot see, hence the marker.
    return "0.0.0.0" if ouvert else "127.0.0.1"  # nosec B104


def _in_container():
    """Detect a containerised deployment (no browser to open).

    The detection lives in `config`: `cli` needs it before importing the server
    at all, to tailor the remedy it offers.
    """
    return config.en_conteneur()


def adb_hint():
    return device.adb_available()


def _lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 1))     # a test address: no packet is sent
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _reconnect_wifi():
    """Find the console again over Wi-Fi at startup, asking the user nothing."""
    addr = (CFG.get("wifi_addr") or "").strip()
    if not addr or device.connection()["kind"]:
        return
    ok, msg = device.connect(addr, timeout=8)
    print("Console    : %s" % ("retrouvee en wifi (%s)" % addr if ok
                               else "pas en wifi (%s)" % msg))


def _audit_demarrage():
    """Run the audit on every launch and surface what is wrong.

    Offline: an audit must never delay startup nor depend on the network. The
    Python version check happens on demand instead.
    """
    try:
        r = audit.lancer(CFG, hors_ligne=True)
    except Exception as exc:                  # a broken audit does not break the tool
        JOB.log("Audit de securite indisponible : %s" % exc, "warn")
        return
    for c in r["controles"]:
        if c["niveau"] == "grave":
            JOB.log("Securite — %s : %s" % (c["titre"], c["constat"]), "error")
        elif c["niveau"] == "alerte":
            JOB.log("Securite — %s : %s" % (c["titre"], c["constat"]), "warn")
    n = r["resume"]["grave"] + r["resume"]["alerte"]
    if n:
        console.dit("Securite : %d point(s) a regarder — `python3 -m romule.audit`"
                    % n, "warn", "audit")
    else:
        console.dit("Securite : aucun point d'attention.", "ok", "audit")


def _notif_public(d):
    """A destination as it may leave the server.

    The address is REPLACED by a preview — the host, and nothing more. A Discord
    webhook is a bearer secret: whoever holds it can post in the channel.
    Returning it to the interface would put it in the browser history, in the
    proxy's logs, and on any screenshot of the settings.

    The host alone is enough to tell which is which, and that is the only thing
    this display is asked to do.
    """
    hote = urllib.parse.urlparse(d.get("url") or "").netloc or "?"
    return {"id": d.get("id"), "nom": d.get("nom"), "service": d.get("service"),
            "evenements": d.get("evenements"), "actif": d.get("actif"),
            "apercu": hote}


def _jeton_de_premier_demarrage():
    """Make an exposed service reachable when it has no way in yet.

    The problem, found while writing the image's smoke test: a container binds
    to 0.0.0.0 (otherwise it would be unreachable from the host), but with no
    account, no token and no `lan_access`, `_autorise()` refuses every non-local
    client. `docker compose up` therefore returned a 403 saying "enable access
    in the settings" — settings that could not be reached. A complete deadlock,
    on the main installation path.

    Opening access by default would have solved the deadlock by handing a
    passwordless service to the whole network. So we generate a token, once, and
    print it: that is what comparable self-hosted tools do, and it leaves the
    installation safe by default AND usable.

    Nothing is generated when the operator has already decided — an account, an
    SSO, an environment token or network access taken on knowingly: their
    decision always wins.
    """
    if _adresse_ecoute() == "127.0.0.1":
        return None
    if config.TOKEN or auth.actif(CFG) or CFG.get("lan_access"):
        return None
    jeton = (CFG.get("jeton_auto") or "").strip()
    if not jeton:
        jeton = secrets.token_urlsafe(24)
        CFG["jeton_auto"] = jeton
        config.save_config(CFG)
        JOB.log("Jeton d'acces engendre au premier demarrage.")
    # `config.TOKEN` is read everywhere else: setting it here avoids
    # duplicating every authorisation check.
    config.TOKEN = jeton
    return jeton


def _faits_de_demarrage(url, ip, jeton_auto):
    """What you want to read first when a service does not do what you think.

    Every line answers a question that otherwise costs half an hour of
    searching: "which version is really running", "where does it keep my
    configuration", "why does the published port not answer", "why is it
    converting nothing". So they are said at startup rather than being
    available somewhere.
    """
    modes = {"aucun": "aucune", "interne": "comptes internes", "oidc": "OpenID Connect"}
    outils = [n for n, present in (("adb", bool(adb_hint())),
                                   ("nsz", nsztool.available()),
                                   ("unar", bool(shutil.which("unar"))),
                                   ("7z", bool(shutil.which("7z") or shutil.which("7zz"))))
              if present]
    faits = [
        ("Version", "%s   Python %d.%d.%d sur %s"
         % (__version__, sys.version_info[0], sys.version_info[1],
            sys.version_info[2], sys.platform)),
        ("Interface", "%s   (Ctrl+C pour arreter)" % url),
    ]
    # The line follows what the SOCKET does, not the `lan_access` setting. The
    # two diverge in the most common case: in a container Romule listens on
    # 0.0.0.0 and protects itself with a token — `lan_access` stays false, and
    # the banner announced "Network: disabled" two lines above the address you
    # had just been invited to enter by.
    if _adresse_ecoute() == "127.0.0.1":
        faits.append(("Reseau", "cette machine seulement — ROMULE_BIND=0.0.0.0, "
                                "ROMULE_LAN=1 ou un jeton, puis redemarrer"))
    else:
        faits.append(("Reseau", "http://%s:%d   (telephone, console, tablette)"
                      % (ip or "<adresse-du-serveur>", config.PORT)))
    faits += [
        ("Acces", modes.get(CFG.get("auth_mode"), CFG.get("auth_mode"))
         + (" + jeton" if config.TOKEN and not jeton_auto else "")
         + (" + jeton engendre" if jeton_auto else "")),
        ("Comptes", "%d" % comptes.nombre()),
        ("Ludotheque", "%s   (%s)"
         % (config.LUDO, "imposee par ROMULE_LIBRARY" if config.LUDO_IMPOSEE
            else "modifiable depuis l'interface")),
    ]
    # The two folders are only distinguished when they differ: otherwise you
    # go looking for your configuration in the games folder, or the reverse.
    if config.LUDO != config.ROOT:
        faits.append(("Donnees", "%s   (configuration, comptes, jaquettes)"
                      % config.ROOT))
    faits += [
        ("Depot", "%s   (glisse tes fichiers ici)" % config.IMPORT),
        ("Journal", str(config.LOGFILE)),
        ("Outils", ", ".join(outils) if outils else
         "aucun — conversion et console indisponibles"),
        ("Jaquettes", CFG.get("cover_provider", "nlib")
         + (" + IGDB" if (CFG.get("igdb_client_id") or "").strip() else "")),
        ("Journalisation", "ROMULE_LOG=%s   (quiet, normal, verbose, debug, json)"
         % console.STYLE),
    ]
    return faits


def serve(open_browser=True):
    # The data folder has already been validated by `cli._verifier_racine()`.
    # The drop folder, on the other hand, is a CONVENIENCE: the library may be
    # read-only and the rest of the service stay perfectly useful. We report,
    # we do not stop.
    try:
        config.IMPORT.mkdir(exist_ok=True)
    except OSError as exc:
        JOB.log("Depot indisponible (%s) : %s" % (config.IMPORT, exc), "warn")
    # Accounts created before roles existed carry none: without this catch-up,
    # an existing installation would find itself with no administrator after
    # the upgrade.
    comptes.reprendre_roles()
    JOB.notify_end = bool(CFG.get("notify", True))
    jeton_auto = _jeton_de_premier_demarrage()
    url = "http://127.0.0.1:%d" % config.PORT
    ip = _lan_ip()
    console.banniere(_faits_de_demarrage(url, ip, jeton_auto))
    threading.Thread(target=_reconnect_wifi, daemon=True).start()
    LIB.scan(log=JOB.log)
    versions.load(LIB, log=JOB.log)
    # ROMULE_NO_BROWSER: a library started by launchd on every login must not
    # open a browser unasked.
    service = (_in_container() or config.ENV_LAN or config.TOKEN
               or config.env("NO_BROWSER", "").strip() not in ("", "0"))
    _audit_demarrage()
    for souci in config.PROBLEMES:
        console.dit(souci, "warn", "config")
    if CFG.get("lan_access") and not config.TOKEN:
        console.dit("Accessible SANS MOT DE PASSE par tout appareil du reseau.",
                    "warn", "acces")
    if jeton_auto:
        # Without the full address, the token is a string the user has to
        # paste back by hand in the right place — that is where it fails.
        console.dit("Ce service est joignable par le reseau et n'a pas encore "
                    "de compte. Ouvre cette adresse, puis cree ton compte :",
                    "warn", "acces")
        console.dit("  http://%s:%d/?token=%s"
                    % (ip or "<adresse-du-serveur>", config.PORT, jeton_auto),
                    "warn", "acces")
    if not adb_hint():
        console.dit("adb absent — la console ne pourra pas etre pilotee",
                    "warn", "device")
    if open_browser and not service:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    srv = ThreadingHTTPServer((_adresse_ecoute(), config.PORT), Handler)

    def stop(*_):
        # `docker stop` sends SIGTERM: we warn the running task and hand back
        # cleanly rather than being killed outright.
        console.dit("Arret demande, fermeture...", "info", "serveur")
        JOB.cancel()
        threading.Thread(target=srv.shutdown, daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, stop)
        except (ValueError, OSError):
            pass                      # no signals outside the main thread

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        stop()
    finally:
        srv.server_close()
        print("Arrete.")
