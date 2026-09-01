"""Serveur web (bibliotheque standard seule).

Ecoute sur 127.0.0.1 par defaut. Il ne s'ouvre au reseau que si son
proprietaire l'a demande : reglage `lan_access`, ROMULE_LAN, ROMULE_TOKEN,
ou execution en conteneur — ou la publication de port fait office de
decision explicite. La docstring precedente affirmait n'ecouter que sur
127.0.0.1 alors que le socket etait lie a 0.0.0.0 depuis toujours.
"""

import gzip
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
import json
import os
import secrets
import shutil
import signal
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from html import escape as html_escape
from urllib.parse import parse_qs, unquote

from . import (actions, audit, auth, comptes, config, covers, device, edenconf,
               doublons, emuready, igdb, integrity, journal_acces, meta, nand,
               parcourir, sauvegarde, saves,
               scan, systems, titleid, transferts, trash, versions, profils)
from . import cli
from . import LICENCE, SOURCE_URL, __version__
from .jobs import JobRunner

LIB = scan.Library()
JOB = JobRunner(config.LOGFILE)
CFG = config.load_config()

_CTYPES = {".html": "text/html", ".js": "application/javascript", ".css": "text/css"}

LOCALES = config.PKG / "locales"


def _langues():
    """Langues disponibles, lues dans romule/locales/ (hors du code)."""
    out = []
    for f in sorted(LOCALES.glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8")).get("_meta", {})
            # Le fichier dit « langue », pas « nom » : la lecture se rabattait
            # donc toujours sur le nom du fichier, et le selecteur proposait
            # « fr » et « en » au lieu de « Francais » et « English ».
            out.append({"code": m.get("code", f.stem),
                        "nom": m.get("langue") or m.get("nom") or f.stem})
        except (ValueError, OSError):
            continue
    return out

MANIFEST = {
    "name": "Ma ludotheque",
    "short_name": "Ludotheque",
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
    """Icone PNG generee sans dependance : carre sombre, cartouche ambre."""
    import struct
    import zlib
    bg, fg = (0x15, 0x1A, 0x23), (0xFF, 0xB4, 0x54)
    m = size // 4                       # marges du cartouche central
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


# Champs qui ne doivent jamais quitter le serveur en clair.
#   auth_secret        : signe les cookies de session — le lire, c'est pouvoir
#                        fabriquer une session valide pour n'importe qui ;
#   oidc_client_secret : authentifie l'application aupres du fournisseur.
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
    a_installer = LIB.nand_rows()      # ne pas masquer le module `nand`
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
        # titres traduits et resumes deja en cache : lecture disque seule, pour
        # que l'affichage ne depende jamais du reseau
        "meta": meta.bulk([titleid.tid_base(f["tid"]) for f in LIB.files if f["tid"]], CFG),
    }


def _taille(n):
    """Taille lisible : les octets bruts ne disent rien dans un message."""
    for unite in ("o", "Kio", "Mio", "Gio", "Tio"):
        if n < 1024 or unite == "Tio":
            return "%.1f %s" % (n, unite) if unite != "o" else "%d o" % n
        n /= 1024.0


# --------------------------------------------------------------- BORNES
# Un serveur qui accepte tout finit par tomber sur le premier venu qui insiste.
# Trois limites, toutes reglables, toutes larges : elles ne genent pas un usage
# normal et rendent le pire cas fini.
DELAI_SOCKET = int(config.env("TIMEOUT", "300"))       # secondes
CONNEXIONS_MAX = int(config.env("MAX_CONN", "64"))
APPELS_PAR_MINUTE = int(config.env("RATE", "600"))

_PLACES = threading.BoundedSemaphore(CONNEXIONS_MAX)

# Compteur d'appels par client. Volontairement grossier : une fenetre d'une
# minute, remise a zero d'un bloc. Un limiteur exact demanderait un etat qui
# grandit ; celui-ci se vide tout seul.
_CADENCE = {}
_CADENCE_VERROU = threading.Lock()


def _trop_vite(client):
    """Ce client a-t-il depasse son quota sur la minute en cours ?"""
    minute = int(time.time() // 60)
    with _CADENCE_VERROU:
        fenetre, compte = _CADENCE.get(client, (minute, 0))
        if fenetre != minute:
            fenetre, compte = minute, 0
        compte += 1
        _CADENCE[client] = (fenetre, compte)
        # Le dictionnaire ne doit pas grandir indefiniment : on le vide quand
        # il devient gros, ce qui offre au passage un tour de grace a tout le
        # monde — sans consequence, la fenetre ne dure qu'une minute.
        if len(_CADENCE) > 4096:
            _CADENCE.clear()
        return compte > APPELS_PAR_MINUTE


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---------------------------------------------------------- helpers

    def send_response(self, code, message=None):
        self._secu_faite = False
        BaseHTTPRequestHandler.send_response(self, code, message)

    def end_headers(self):
        # Un seul endroit d'application : impossible d'oublier une route.
        if not getattr(self, "_secu_faite", True):
            self._secu_faite = True
            self._entetes_securite()
        BaseHTTPRequestHandler.end_headers(self)

    # Types qui gagnent a etre compresses. `application/javascript` y figure
    # explicitement : c'est le plus gros corps que le serveur envoie (app.js,
    # 300 Kio) et il ne commence pas par `text/`.
    TYPES_GZIP = ("application/json", "application/javascript",
                  "application/manifest+json", "text/", "image/svg+xml")
    # En dessous, l'en-tete et le temps de compression coutent plus que le gain.
    SEUIL_GZIP = 1024

    def _accepte_gzip(self):
        """Le client sait-il lire du gzip ?

        `gzip;q=0` veut dire « surtout pas » : c'est rare, mais l'ignorer
        enverrait un corps illisible a qui l'a explicitement refuse.
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
        """Ecrit une reponse, compressee quand cela vaut la peine.

        Un seul chemin, parce qu'il y en avait six : compresser dans `_json`
        seul aurait laisse passer `_static`, c'est-a-dire l'essentiel — app.js,
        app.css et index.html font 507 Kio et repartent a CHAQUE chargement,
        `_static` posant `Cache-Control: no-store`.

        Mesure sur une ludotheque de 2 000 titres : /api/scan passe de 2,04 Mio
        a 0,08 Mio, et les trois fichiers statiques de 507 a 153 Kio.

        `Vary: Accept-Encoding` est pose meme quand on ne compresse pas : sans
        lui, un cache intermediaire sert la variante compressee a un client qui
        ne sait pas la lire.
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
        """JSON avec ETag : la reponse la plus lourde de l'outil (l'inventaire,
        ~130 Ko) ne repart en entier que si elle a change. Le navigateur
        revalide a chaque fois — donc jamais de donnee perimee — mais recoit
        304 et quelques octets tant que rien ne bouge. C'est le poste le plus
        couteux du demarrage sur telephone en Wi-Fi."""
        body = json.dumps(obj).encode()
        # Certaines cles portent un horodatage regenere a chaque appel : les
        # inclure rendrait chaque reponse unique et l'ETag inutile. Elles
        # derivent toujours d'une autre cle, elle bien comparee.
        empreinte = json.dumps({k: v for k, v in obj.items() if k not in volatiles},
                               sort_keys=True, default=str).encode()
        # L'ETag doit distinguer les deux representations : la compressee et
        # l'autre n'ont pas les memes octets. Sans ce suffixe, un client qui
        # cesse d'accepter le gzip recevrait un 304 pour un corps qu'il n'a
        # jamais eu sous cette forme.
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
                              ("Cache-Control", "no-cache")])  # revalider, pas ignorer

    def _static(self, name):
        path = config.STATIC / name
        if not path.is_file():
            self._json({"error": "introuvable"}, 404)
            return
        self._ecrire(path.read_bytes(),
                     _CTYPES.get(path.suffix, "application/octet-stream")
                     + "; charset=utf-8", 200,
                     # toujours la derniere version
                     entetes=[("Cache-Control", "no-store")], cookie=True)

    # Un corps de requete JSON n'a aucune raison de depasser quelques centaines
    # de kilo-octets : le plus gros est une liste de chemins. Sans borne, un
    # POST annoncant 4 Go remplissait la memoire du serveur avant meme d'etre
    # analyse. Les envois de fichiers ont leur propre route, en flux.
    CORPS_MAX = 1 << 20            # 1 Mio

    def _payload(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > self.CORPS_MAX:
            raise ValueError("corps de requete trop volumineux (%d octets)" % n)
        return json.loads(self.rfile.read(n) or b"{}")

    # ---------------------------------------------------------- GET

    # Sans delai, une connexion ouverte et laissee muette immobilise un fil
    # pour toujours : c'est le principe meme de l'attaque « slowloris ».
    timeout = DELAI_SOCKET

    def handle(self):
        """Une place, ou un refus poli.

        `ThreadingHTTPServer` cree un fil par connexion, sans plafond. Un
        millier de connexions simultanees creait un millier de fils avant que
        la moindre regle ne s'applique.
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
        """Valeur d'un cookie, lue comme un cookie et non comme du texte.

        La lecture precedente cherchait la sous-chaine « switch_token=<jeton> »
        dans l'en-tete brut : un cookie voisin nomme `x_switch_token`, ou une
        valeur qui contenait le jeton en prefixe, satisfaisaient le test.
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

        Comparaison a temps constant : un `==` sur une chaine s'arrete au
        premier octet different, ce qui laisse mesurer le prefixe correct.
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

    # En-tetes ajoutes par un relais. Leur seule presence signifie que la
    # requete n'arrive PAS directement de son auteur.
    ENTETES_RELAI = ("X-Forwarded-For", "X-Real-IP", "Forwarded",
                     "X-Forwarded-Host", "X-Forwarded-Proto")

    def _relayee(self):
        return any(self.headers.get(h) for h in self.ENTETES_RELAI)

    def _client_reel(self):
        """Adresse de l'auteur de la requete, ou None si elle est indeterminable.

        Le pair TCP suffit tant que personne ne relaie. Des qu'un relais
        s'intercale, il devient l'adresse du RELAIS — et derriere un reverse
        proxy pose sur la meme machine, c'est 127.0.0.1 pour tout le monde,
        y compris pour l'Internet entier. C'est la faille que cette methode
        ferme : on ne croit un en-tete que s'il vient d'un proxy declare.
        """
        pair = self.client_address[0]
        if not self._relayee():
            return pair
        if pair not in config.PROXYS_CONFIANCE:
            return None                     # quelqu'un relaie sans mandat
        # Le proxy declare a ajoute a droite le pair qu'il a vu. On remonte la
        # chaine en sautant les relais eux-memes declares.
        chaine = [a.strip() for a in
                  (self.headers.get("X-Forwarded-For") or "").split(",") if a.strip()]
        for adresse in reversed(chaine):
            if adresse not in config.PROXYS_CONFIANCE:
                return adresse
        # Toute la chaine est faite d'adresses declarees. Cela arrive quand le
        # client est LUI-MEME sur la machine du proxy — le cas courant d'un
        # nginx local devant l'application. La premiere entree reste alors la
        # seule candidate.
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
        """Le navigateur annonce-t-il que la requete part bien de CETTE page ?

        Sans ce controle, un site tiers ouvert dans un autre onglet pourrait
        faire poster n'importe quelle action a la ludotheque avec le cookie de
        session de l'utilisateur (CSRF). Le cookie est en `SameSite=Lax`, ce qui
        couvre deja les navigateurs recents ; ceci ferme le reste.
        """
        origine = self.headers.get("Origin") or ""
        if not origine:
            # Certains clients (curl, l'app installee) n'envoient pas d'Origin.
            # Faute d'Origin, on se rabat sur Referer quand il existe.
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
        """En-tetes appliques a toutes les reponses.

        L'interface n'appelle aucun domaine tiers et ne charge aucun script
        externe : une politique stricte ne casse rien et bloque l'injection de
        contenu distant.
        """
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        # Aucune de ces capacites n'est utilisee par l'interface : les refuser
        # explicitement evite qu'une injection future en dispose.
        self.send_header("Permissions-Policy",
                         "camera=(), microphone=(), geolocation=(), "
                         "payment=(), usb=(), interest-cohort=()")
        # Isole la page des autres onglets : une fenetre ouverte depuis ici ne
        # garde aucune prise sur celle-ci.
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        # Les reponses qui portent des comptes ou des reglages ne doivent
        # laisser aucune trace dans un cache partage — ni proxy, ni disque.
        if any(self.path.startswith(x) for x in
               ("/api/comptes", "/api/config", "/auth/", "/api/compte-")):
            self.send_header("Cache-Control", "no-store, private")
        # HSTS uniquement quand la liaison est deja chiffree : l'annoncer en
        # clair enfermerait l'utilisateur hors d'une installation sans TLS,
        # et la plupart le sont.
        if self._secure():
            self.send_header("Strict-Transport-Security",
                             "max-age=15552000; includeSubDomains")
        # `script-src 'self'` sans tolerance pour l'inline. C'etait impossible
        # tant que l'interface reposait sur 153 attributs `onclick` : les
        # refuser aurait rendu la quasi-totalite des boutons inertes, en
        # silence. Ils sont tous passes en `data-act` (phase 4), et un seul
        # <script> en ligne subsistait — le theme — qui est devenu
        # `/theme.js`. Un navigateur refuse desormais tout script qui n'a pas
        # ete servi par cette origine, y compris celui qu'une injection
        # reussie ecrirait dans la page.
        #
        # `style-src` garde 'unsafe-inline' : les attributs `style=` restent
        # nombreux, et un style ne s'execute pas. C'est une exception d'une
        # autre nature, et elle est documentee comme telle.
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; "
                         "style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; "
                         "connect-src 'self'; frame-ancestors 'none'; "
                         "base-uri 'none'; form-action 'self'")

    def _cadence_ok(self):
        """Refuse au-dela du quota, avec un 429 et le delai d'attente.

        Seule la connexion etait limitee jusqu'ici. Tout le reste — y compris
        les essais de jeton et les depots de fichiers — pouvait etre repete
        sans fin.
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

    def _allowed(self):
        """Qui a le droit d'entrer.

        L'authentification SSO, quand elle est active, s'applique AUSSI en local :
        activer un SSO puis rester joignable sans mot de passe depuis la machine
        elle-meme viderait la mesure de son sens des que le poste est partage.
        """
        if auth.actif(CFG):
            if self.path.startswith("/auth/"):
                return True                       # le flux de connexion lui-meme
            return bool(auth.session(self.headers.get("Cookie")))
        if self._local():
            return True
        if config.TOKEN:
            return self._token_ok()
        return bool(CFG.get("lan_access"))

    def _deny(self):
        # Avec un SSO configure, on n'affiche pas un refus sec : on envoie
        # l'utilisateur se connecter, ce qu'il vient precisement chercher.
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
        """Memorise le jeton apres un acces par ?token= : plus besoin de le retaper."""
        if config.TOKEN and "token=" in self.path:
            # HttpOnly : aucun script n'a besoin de relire ce jeton, et le
            # cacher retire une cible aux injections. Secure des que la
            # liaison est chiffree, pour qu'il ne reparte jamais en clair.
            self.send_header("Set-Cookie",
                             "switch_token=%s; Path=/; Max-Age=31536000; "
                             "SameSite=Lax; HttpOnly%s"
                             % (config.TOKEN, "; Secure" if self._secure() else ""))

    # ------------------------------------------------------- connexion SSO

    def _base_retour(self):
        """Adresse de retour presentee au fournisseur. Elle doit correspondre au
        mot pres a celle declaree dans Authentik / Keycloak : on la construit
        donc de facon previsible, et on laisse l'utilisateur la figer si son
        installation passe par un proxy."""
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
        """Page de connexion. `second` demande le code a usage unique : le mot
        de passe est deja valide, on ne le refait pas saisir."""
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
        """Retourne True si la requete a ete traitee par le flux SSO."""
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
        """Traite le formulaire email + mot de passe. Toujours en POST."""
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
            # Le mot de passe est bon : on redemande seulement le code.
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
        # Les PNG et JPEG passent ici : `TYPES_GZIP` ne les contient pas, donc
        # ils ressortent tels quels. Le manifeste, lui, est compresse.
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
        if p in ("/", "/index.html"):
            self._static("index.html")
        elif p in ("/app.js", "/app.css", "/reactive.js", "/theme.js"):
            self._static(p.lstrip("/"))
        elif p == "/api/scan":
            # `shop_text` contient la date de generation : elle change a chaque
            # seconde alors que l'inventaire, lui, est identique.
            self._json_revalide(_lib_response(), volatiles=("shop_text",))
        elif p == "/api/job":
            self._json(JOB.snapshot())
        elif p == "/api/import-list":
            self._json({"items": actions.scan_import()})
        elif p == "/api/langues":
            self._json({"langues": _langues(), "courante": CFG.get("ui_lang", "en")})
        elif p.startswith("/locales/"):
            f = LOCALES / (p.rsplit("/", 1)[-1].replace("..", ""))
            if f.is_file() and f.suffix == ".json":
                # Les traductions changent avec le code : les mettre en cache un
                # jour, c'est afficher l'ancienne version apres chaque mise a
                # jour. On revalide, comme pour l'inventaire.
                self._json_revalide(json.loads(f.read_text(encoding="utf-8")))
            else:
                self._json({"error": "langue inconnue"}, 404)
        elif p == "/api/trash-list":
            # La purge automatique n'agit que si l'utilisateur a fixe un delai :
            # par defaut (0) la corbeille n'est jamais videe toute seule.
            jours = CFG.get("trash_days", 0)
            if jours:
                n, octets = trash.purge(jours, JOB.log)
                if n:
                    JOB.log("Purge automatique : %d lot(s), %.1f Go liberes"
                            % (n, octets / 2 ** 30))
            self._json({"items": trash.listing(), "resume": trash.resume(),
                        "jours": jours})
        elif p == "/api/health":
            # La sonde du conteneur interroge cette route en GET. Elle n'etait
            # declaree qu'en POST : le HEALTHCHECK du Dockerfile recevait donc
            # « route inconnue » depuis toujours, et le conteneur ne pouvait
            # jamais etre declare sain.
            self._json(_health())
        elif p == "/api/systems":          # lecture seule : accessible en GET
            self._json({"systems": systems.summary(CFG),
                        "roms_root": systems.roms_root(CFG),
                        # le depot s'en sert pour filtrer, et pour la boite de
                        # dialogue de choix de fichier
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
            # self.path, pas p : _cover a besoin du ?name=..., que la recherche
            # par nom utilise quand le fichier ne porte aucun title ID.
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
        # Toutes les plateformes, pas seulement la Switch : l'outil sait ranger
        # une ROM GBA ou une image PS2, il n'y a aucune raison de la refuser.
        # Une plateforme ajoutee a la main apporte ses propres extensions.
        permises = systems.extensions_acceptees(CFG)
        if not name or Path(name).suffix.lower() not in permises:
            return self._json(
                {"error": "Type non géré : %s. Formats acceptés : %s."
                          % (Path(name).suffix or "(sans extension)",
                             ", ".join(sorted(permises)))}, 400)
        config.IMPORT.mkdir(exist_ok=True)
        dest = config.IMPORT / name
        left = int(self.headers.get("Content-Length", 0))
        # Deux refus AVANT d'ouvrir le fichier : un depot sans plafond laissait
        # n'importe quel appareil autorise saturer le disque de l'hote, et un
        # disque plein ne casse pas que l'import — il casse la ludotheque.
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
        """Renvoie une raison de refus, ou "" si l'appelant peut administrer.

        La regle depend du mode, et c'est volontaire :

        * authentification ACTIVE  -> il faut une session, et elle doit porter
          le role d'administrateur ;
        * authentification ETEINTE -> il n'existe aucune identite a verifier.
          Exiger une session rendrait l'outil inutilisable dans son mode le
          plus courant. `_allowed()` a deja tranche : cet appelant a le droit
          d'etre la, et dans ce mode il a tous les droits — l'audit le signale
          comme un point d'attention, ce qu'il est.

        Cas a part, la creation du PREMIER compte : elle doit rester possible
        alors qu'aucune session ne peut exister, mais pas depuis n'importe ou.
        Sans cela, « le premier compte est administrateur » signifierait « le
        premier venu sur le reseau devient administrateur ».
        """
        if not auth.actif(CFG):
            return ""
        # Session d'anti-verrouillage : elle est remise a celui qui vient
        # d'activer l'authentification depuis un acces deja autorise, pour
        # qu'il ne s'enferme pas dehors. Elle vaut donc administration — sinon
        # activer un SSO mal configure rendrait les reglages inaccessibles a
        # tout le monde, y compris a celui qui vient de les changer.
        jeton = auth.session(self.headers.get("Cookie"))
        if jeton and jeton.get("src") == "config":
            return ""
        u = self._qui()
        if not u:
            return "Aucun compte connecte."
        if not comptes.est_admin(u["id"]):
            return "Reserve a un administrateur."
        return ""

    def _qui(self):
        """Compte connecte, ou None si l'authentification est desactivee."""
        s = auth.session(self.headers.get("Cookie"))
        return comptes.par_id(s.get("sub")) if s and s.get("src") == "interne" else None

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
        # Tout POST modifie l'etat : on exige qu'il vienne de cette page.
        if not self._meme_origine():
            JOB.log("POST rejete sur %s : origine %s"
                    % (self.path, self.headers.get("Origin") or "?"), "warn")
            return self._json({"error": "origine inattendue"}, 403)
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

    # Le modele de roles disait « seul un administrateur modifie la
    # configuration, gere les comptes ET lance les actions destructives ».
    # Les deux premiers points etaient tenus route par route ; le troisieme ne
    # l'etait pas. Concretement, tout compte non-administrateur pouvait
    # restaurer une sauvegarde — qui contient le fichier des comptes, donc
    # rendre le role d'administrateur a qui l'avait perdu —, effacer le
    # journal, ou lire le journal des acces.
    #
    # Une liste a un seul endroit plutot qu'un appel repete dans trente
    # branches : une garde qu'on doit se souvenir d'ajouter est une garde qu'on
    # oublie. En mode sans authentification, `_admin_requis()` laisse passer :
    # il n'y a pas d'identite a distinguer, et `_allowed()` a deja tranche.
    RESERVE_ADMIN = frozenset({
        # --- effacent ou remettent en place des donnees
        "/api/sauvegarde-restaurer",   # contient le fichier des comptes
        "/api/sauvegarde-creer",
        "/api/trash-purge",
        "/api/restore",
        "/api/covers-clear",
        "/api/meta-oublier",
        "/api/journal-clear",          # ce qu'on efface d'abord pour se cacher
        "/api/emuready-clear",
        # --- deplacent des fichiers en masse
        "/api/reorganize-local",
        "/api/device-organize",
        "/api/device-mktree",
        # --- ecrivent dans les fichiers d'un logiciel tiers
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
        # --- designent ou le service lit et ecrit sur la machine hote
        "/api/parcourir",             # revele l'arborescence de l'hote
        "/api/ludotheque",
        # --- renseignent sur qui se connecte, et sur la posture de securite
        "/api/acces",
        "/api/audit",
        "/api/auth-test",
    })

    def _reserve_admin(self, p):
        """Raison de refus si la route demande le role d'administrateur."""
        return self._admin_requis() if p in self.RESERVE_ADMIN else ""

    def _route_post(self, p, d):
        if p == "/api/versions":
            versions.load(LIB, force=bool(d.get("force")), log=JOB.log)
            self._json(_lib_response())

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
            self._json({"message": "%d fichier(s) deplace(s) dans %s" % (n, where)})

        # ---- comptes internes
        elif p == "/api/comptes":
            self._json({"comptes": comptes.liste(),
                        "moi": (self._qui() or {}).get("id", ""),
                        "mdp_min": comptes.MDP_MIN})

        elif p == "/api/compte-creer":
            if not comptes.liste():
                # Tout premier compte : il devient administrateur, donc sa
                # creation ne peut pas etre ouverte au reseau. Sinon « le
                # premier compte gouverne » signifierait « le premier appareil
                # du reseau gouverne » — et l'acces reseau sans mot de passe
                # est un mode que l'outil propose.
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
            # La session actuelle a ete signee avant le changement : on en
            # redonne une valide a CE navigateur, les autres sont coupes.
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
            # Les entrees completes sont lourdes : le client n'a besoin que du
            # nom, de la taille et du chemin pour decider.
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
            # Forcer la reprise des fiches : on efface le cache, pas les
            # jaquettes deja telechargees (elles ont leur propre bouton).
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

        # ---- ou sont les jeux, sur la machine qui heberge le service
        elif p == "/api/parcourir":
            self._json(parcourir.lister(d.get("chemin", ""), CFG))

        elif p == "/api/ludotheque":
            # Un travail en cours tient des chemins absolus deja calcules :
            # deplacer la ludotheque sous ses pieds ferait ecrire une
            # conversion dans l'ancien dossier, ou echouer un deplacement a
            # mi-parcours. On refuse, on ne met pas en file.
            if JOB.running:
                return self._json(
                    {"error": "un travail est en cours — reessaie apres"}, 409)
            souci = config.definir_ludotheque(d.get("chemin", ""),
                                              creer=bool(d.get("creer")))
            if souci:
                return self._json({"error": souci}, 400)
            # Vide quand le choix retombe sur le dossier du service : la
            # configuration dit alors « par defaut », et suivra le jour ou le
            # deploiement changera ce dossier.
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

        # ---- installer l'acces sur la console
        elif p == "/api/emulateur-detecter":
            # Le nom du paquet Android change d'une version d'emulateur a
            # l'autre. On demande a la console lequel est installe et on le
            # retient, plutot que de reinterroger a chaque affichage.
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

        # ---- connexion sans fil
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
            # Ce qui est deja sur la console pour CE systeme : sans cette liste,
            # les autres consoles n'avaient aucun etat, contrairement a la Switch.
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

        # ---- configuration d'Eden
        elif p in ("/api/eden-config", "/api/eden-apply", "/api/emuready-apply") \
                and not edenconf.pilotable():
            # Tous les emulateurs n'exposent pas des reglages que l'on sache
            # lire : Ryujinx les range en JSON, avec une autre arborescence.
            # Mieux vaut le dire que d'ecrire au hasard dans ses fichiers.
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
            # L'etat AVANT toute modification : `CFG` est mute juste apres,
            # donc le lire ensuite repondrait toujours « deja actif ».
            refus = self._admin_requis()
            if refus:
                return self._json({"error": refus}, 403)
            avant = auth.actif(CFG)
            # Un champ renvoye masque signifie « ne change pas » : sinon
            # enregistrer les reglages effacerait le secret a chaque fois.
            for k in SECRETS:
                if d.get(k) == MASQUE:
                    d.pop(k)
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
                      "oidc_groupes"):
                if k in d:
                    CFG[k] = d[k]
            # Les plateformes ajoutees a la main sont assainies A L'ECRITURE,
            # et pas seulement a la lecture. `systems.liste()` fait deja passer
            # le dossier par `dossier_sur`, donc rien ne s'echappe aujourd'hui —
            # mais garder un `../../..` dans le fichier de configuration, c'est
            # armer le piege pour le prochain qui lira ce champ directement.
            if "systemes_perso" in d:
                CFG["systemes_perso"] = systems.assainir_perso(CFG["systemes_perso"])
            config.save_config(CFG)
            sauvegarde.auto("reglages")
            JOB.notify_end = bool(CFG.get("notify", True))

            # Activer l'authentification depuis un navigateur qui n'a pas encore
            # de session l'ejectait aussitot : la requete SUIVANTE recevait la
            # page de connexion, y compris celle qui aurait servi a revenir en
            # arriere. Celui qui vient de faire le changement etait bien
            # autorise a le faire : on lui ouvre une session.
            corps = json.dumps({"config": _config_publique()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if (not avant and auth.actif(CFG)
                    and not auth.session(self.headers.get("Cookie"))):
                u = None
                if CFG.get("auth_mode") == "interne":
                    liste = comptes.liste()
                    u = comptes.par_id(liste[0]["id"]) if liste else None
                # Ce jeton n'est rattache a aucun compte : c'est un pont, le
                # temps de finir de se configurer et de se connecter pour de
                # bon. Lui donner les douze heures d'une vraie session en
                # faisait un acces administrateur anonyme d'une demi-journee.
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

    def _job(self, fn, *args):
        ok = JOB.start(fn.__name__, fn, *args)
        self._json({} if ok else {"error": "Une tache est deja en cours."})


def _health():
    """Etat de preparation : sert a la sonde Docker et au parcours de demarrage."""
    keyfile = LIB.keyfile
    conn = device.connection()
    return {
        "ok": True,
        # La licence AGPL demande qu'un utilisateur qui atteint le service par
        # le reseau puisse en obtenir le code. Le dire ici le rend lisible par
        # un outil autant que par l'interface.
        "version": __version__,
        "licence": LICENCE,
        "source": SOURCE_URL,
        "first_run": not config.CONFIG_FILE.exists(),
        "root": str(config.ROOT),
        # La ludotheque est distincte de la racine du service : c'est elle que
        # l'assistant et les reglages proposent de choisir.
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
            # Le navigateur en a besoin AVANT d'envoyer : refuser en cours de
            # transfert coupe la connexion, et le message n'arrive jamais.
            "televersement_max": config.TELEVERSEMENT_MAX,
            "container": _in_container(),
            # Conseils d'installation adaptes a CETTE machine. L'assistant
            # affichait une commande Homebrew a tout le monde, y compris sur
            # un NAS Debian ou dans un conteneur.
            "remede_nsz": cli.remede("nsz"),
            "remede_adb": cli.remede("adb"),
            # De quoi juger si l'acces doit etre protege AVANT toute autre
            # chose : un service joignable par le reseau et sans authentification
            # est le defaut le plus grave qu'une installation neuve puisse avoir.
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

    Le socket etait lie a `0.0.0.0` en toutes circonstances, le filtrage se
    faisant requete par requete. Cela marche, mais cela expose un port a tout
    le reseau pour une installation que son proprietaire croit locale — et
    toute erreur dans le filtrage devient immediatement joignable de partout.

    On ne s'ouvre donc que sur decision explicite. En conteneur, la decision
    est prise par celui qui publie le port : y rester sur 127.0.0.1 rendrait
    l'application injoignable.
    """
    if config.env("BIND", "").strip():
        return config.env("BIND").strip()
    ouvert = (CFG.get("lan_access") or config.ENV_LAN or config.TOKEN
              or _in_container())
    # bandit signale toute ecoute sur 0.0.0.0. Ici elle est CONDITIONNELLE :
    # elle n'a lieu que si l'operateur a ouvert l'acces (reglage `lan_access`,
    # ROMULE_LAN, un jeton pose, ou un conteneur — ou une ecoute locale ne
    # servirait a rien puisque le port est publie). Le defaut reste 127.0.0.1.
    # C'est precisement ce que l'outil ne peut pas voir, d'ou la marque.
    return "0.0.0.0" if ouvert else "127.0.0.1"  # nosec B104


def _in_container():
    """Detecte un deploiement conteneurise (pas de navigateur a ouvrir).

    La detection vit dans `config` : `cli` en a besoin avant tout import du
    serveur, pour adapter le remede qu'il propose.
    """
    return config.en_conteneur()


def adb_hint():
    return device.adb_available()


def _lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 1))     # adresse de test : aucun paquet n'est emis
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _reconnect_wifi():
    """Retrouve la console en wifi au demarrage, sans rien demander a l'utilisateur."""
    addr = (CFG.get("wifi_addr") or "").strip()
    if not addr or device.connection()["kind"]:
        return
    ok, msg = device.connect(addr, timeout=8)
    print("Console    : %s" % ("retrouvee en wifi (%s)" % addr if ok
                               else "pas en wifi (%s)" % msg))


def _audit_demarrage():
    """Passe l'audit a chaque lancement et remonte ce qui cloche.

    Hors ligne : un audit ne doit jamais retarder le demarrage ni dependre du
    reseau. Le controle de version de Python, lui, se fait a la demande.
    """
    try:
        r = audit.lancer(CFG, hors_ligne=True)
    except Exception as exc:                  # un audit casse ne casse pas l'outil
        JOB.log("Audit de securite indisponible : %s" % exc, "warn")
        return
    for c in r["controles"]:
        if c["niveau"] == "grave":
            JOB.log("Securite — %s : %s" % (c["titre"], c["constat"]), "error")
        elif c["niveau"] == "alerte":
            JOB.log("Securite — %s : %s" % (c["titre"], c["constat"]), "warn")
    n = r["resume"]["grave"] + r["resume"]["alerte"]
    if n:
        print("Securite   : %d point(s) a regarder — voir le journal, "
              "ou `python3 -m romule.audit`" % n)
    else:
        print("Securite   : aucun point d'attention.")


def _jeton_de_premier_demarrage():
    """Rend joignable un service expose qui n'a encore aucun moyen d'entrer.

    Le probleme, decouvert en ecrivant le test de fumee de l'image : un
    conteneur se lie a 0.0.0.0 (sinon il serait injoignable depuis l'hote),
    mais sans compte, sans jeton et sans `lan_access`, `_autorise()` refuse
    tout client non local. `docker compose up` donnait donc un 403 disant
    « active l'acces dans les reglages » — des reglages qu'on ne pouvait pas
    atteindre. Un blocage complet, sur le chemin d'installation principal.

    Ouvrir l'acces par defaut aurait resolu le blocage en livrant un service
    sans mot de passe a tout le reseau. On engendre donc un jeton, une fois,
    et on l'affiche : c'est ce que font les outils auto-heberges comparables,
    et cela laisse l'installation sure par defaut ET utilisable.

    Rien n'est engendre si l'operateur a deja tranche — compte, SSO, jeton
    d'environnement ou acces reseau assume : sa decision prime toujours.
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
    # `config.TOKEN` est lu partout ailleurs : le renseigner ici evite de
    # doubler chaque controle d'autorisation.
    config.TOKEN = jeton
    return jeton


def serve(open_browser=True):
    # Le dossier de donnees a deja ete valide par `cli._verifier_racine()`.
    # Le depot, lui, est un CONFORT : la ludotheque peut etre en lecture seule
    # et le reste du service rester parfaitement utile. On signale, on ne
    # s'arrete pas.
    try:
        config.IMPORT.mkdir(exist_ok=True)
    except OSError as exc:
        JOB.log("Depot indisponible (%s) : %s" % (config.IMPORT, exc), "warn")
    # Les comptes crees avant l'existence des roles n'en portent aucun :
    # sans cette reprise, une installation existante se retrouverait sans
    # administrateur apres la mise a jour.
    comptes.reprendre_roles()
    JOB.notify_end = bool(CFG.get("notify", True))
    threading.Thread(target=_reconnect_wifi, daemon=True).start()
    LIB.scan(log=JOB.log)
    versions.load(LIB, log=JOB.log)
    jeton_auto = _jeton_de_premier_demarrage()
    url = "http://127.0.0.1:%d" % config.PORT
    # ROMULE_NO_BROWSER : la ludotheque lancee par launchd a chaque ouverture
    # de session ne doit pas ouvrir un navigateur sans qu'on lui demande.
    service = (_in_container() or config.ENV_LAN or config.TOKEN
               or config.env("NO_BROWSER", "").strip() not in ("", "0"))
    _audit_demarrage()
    print("Ludotheque : %s" % config.LUDO)
    # Les deux dossiers sont affiches separement des qu'ils different : sinon
    # on cherche sa configuration dans le dossier des jeux, ou l'inverse.
    if config.LUDO != config.ROOT:
        print("Donnees    : %s  (configuration, comptes, jaquettes)" % config.ROOT)
    print("Depot      : %s  (glisse tes fichiers ici)" % config.IMPORT)
    for souci in config.PROBLEMES:
        print("Attention  : %s" % souci)
    print("Interface  : %s   (Ctrl+C pour arreter)" % url)
    ip = _lan_ip()
    if CFG.get("lan_access"):
        if ip:
            print("Reseau     : http://%s:%d   (telephone, console, tablette...)" % (ip, config.PORT))
        if config.TOKEN:
            print("Acces      : protege par jeton — ajoute ?token=... a l'adresse")
        else:
            print("             ATTENTION : accessible sans mot de passe par tout appareil du reseau.")
    else:
        # Le socket est desormais lie a 127.0.0.1 seul : le reglage ne peut
        # plus prendre effet a chaud, et le dire faussement enverrait
        # l'utilisateur chercher une panne qui n'existe pas.
        print("Reseau     : desactive — pour ouvrir : ROMULE_BIND=0.0.0.0, "
              "ROMULE_LAN=1 ou un jeton, puis redemarrer")
    if jeton_auto:
        # Sans l'adresse complete, le jeton est une chaine que l'utilisateur
        # doit recoller a la main au bon endroit — c'est la que ca echoue.
        print("Acces      : ce service est joignable par le reseau et n'a pas "
              "encore de compte.")
        print("             Ouvre cette adresse, puis cree ton compte dans "
              "l'assistant :")
        print("               http://%s:%d/?token=%s"
              % (ip or "<adresse-du-serveur>", config.PORT, jeton_auto))
    if not adb_hint():
        print("adb        : absent — la console ne pourra pas etre pilotee")
    if open_browser and not service:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    srv = ThreadingHTTPServer((_adresse_ecoute(), config.PORT), Handler)

    def stop(*_):
        # `docker stop` envoie SIGTERM : on previent la tache en cours et on
        # rend la main proprement plutot que d'etre tue net.
        print("\nArret demande, fermeture...")
        JOB.cancel()
        threading.Thread(target=srv.shutdown, daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, stop)
        except (ValueError, OSError):
            pass                      # pas de signaux hors du thread principal

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        stop()
    finally:
        srv.server_close()
        print("Arrete.")
