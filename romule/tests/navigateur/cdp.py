"""Client Chrome DevTools minimal, en bibliotheque standard seule.

Assez pour piloter un vrai navigateur : dimensions d'ecran, navigation,
evaluation de JavaScript, clics reels et captures d'ecran. Sans cela, on ne
peut que supposer ce que fait la mise en page sur telephone.
"""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

# Chemins usuels, du plus specifique au plus generique. Un seul chemin en dur
# rendait ces tests impossibles a jouer ailleurs que sur un Mac — donc absents
# de l'integration continue, la ou ils servent le plus.
CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
]


def trouver_chrome():
    """Chemin de Chrome, ou une erreur qui dit quoi faire.

    ROMULE_CHROME passe avant tout : c'est ce qui permet a un poste ou a un
    conteneur de designer un binaire que cette liste ne connait pas.
    """
    impose = os.environ.get("ROMULE_CHROME", "").strip()
    if impose:
        if not Path(impose).exists():
            raise RuntimeError("ROMULE_CHROME designe un fichier absent : %s" % impose)
        return impose
    for c in CHROMES:
        if Path(c).exists():
            return c
    for nom in ("google-chrome", "chromium", "chromium-browser"):
        trouve = shutil.which(nom)
        if trouve:
            return trouve
    raise RuntimeError(
        "Chrome introuvable. Installe-le, ou indique-le par ROMULE_CHROME.\n"
        "  macOS  : brew install --cask google-chrome\n"
        "  Debian : apt install chromium\n"
        "  CI     : browser-actions/setup-chrome")


class WS:
    """Client WebSocket reduit au strict necessaire (RFC 6455, trames texte)."""

    def __init__(self, url):
        _, _, reste = url.partition("://")
        hote, _, chemin = reste.partition("/")
        h, _, p = hote.partition(":")
        self.s = socket.create_connection((h, int(p or 80)), timeout=30)
        cle = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((
            "GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (chemin, hote, cle)).encode())
        tampon = b""
        while b"\r\n\r\n" not in tampon:
            tampon += self.s.recv(4096)
        self.reste = tampon.split(b"\r\n\r\n", 1)[1]

    def envoyer(self, texte):
        charge = texte.encode()
        n = len(charge)
        entete = b"\x81"
        if n < 126:
            entete += bytes([0x80 | n])
        elif n < 65536:
            entete += b"\xfe" + struct.pack(">H", n)
        else:
            entete += b"\xff" + struct.pack(">Q", n)
        masque = os.urandom(4)
        self.s.sendall(entete + masque
                       + bytes(c ^ masque[i % 4] for i, c in enumerate(charge)))

    def _lire(self, n):
        while len(self.reste) < n:
            bloc = self.s.recv(65536)
            if not bloc:
                raise EOFError("connexion fermee")
            self.reste += bloc
        out, self.reste = self.reste[:n], self.reste[n:]
        return out

    def recevoir(self):
        while True:
            e = self._lire(2)
            op, n = e[0] & 0x0F, e[1] & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._lire(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._lire(8))[0]
            charge = self._lire(n)
            if op == 1:
                return charge.decode("utf-8", "replace")
            if op == 8:
                raise EOFError("fermeture")


class Navigateur:
    def __init__(self, port=9333, largeur=430, hauteur=932, dpr=3):
        self.proc = subprocess.Popen(
            [trouver_chrome(), "--headless=new", "--remote-debugging-port=%d" % port,
             "--no-first-run", "--no-default-browser-check", "--disable-gpu",
             "--hide-scrollbars", "--user-data-dir=%s" % (Path(tempfile.gettempdir()) / ("cdp-profil-%d" % port)),
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cible = None
        for _ in range(60):
            try:
                d = json.load(urllib.request.urlopen(
                    "http://127.0.0.1:%d/json" % port, timeout=2))
                cible = next((t for t in d if t["type"] == "page"), None)
                if cible:
                    break
            except Exception:
                pass
            time.sleep(0.4)
        if not cible:
            raise RuntimeError("Chrome n'a pas repondu")
        self.ws = WS(cible["webSocketDebuggerUrl"])
        self.n = 0
        self.cmd("Page.enable")
        self.cmd("Runtime.enable")
        self.cmd("Emulation.setDeviceMetricsOverride", {
            "width": largeur, "height": hauteur, "deviceScaleFactor": dpr,
            "mobile": True})
        self.cmd("Emulation.setTouchEmulationEnabled", {"enabled": True,
                                                        "maxTouchPoints": 5})
        # Le profil est reutilise d'un essai a l'autre : un fichier mis en cache
        # avec une longue duree de vie survivrait au changement de reglage cote
        # serveur, et le test jugerait une version perimee.
        self.cmd("Network.enable")
        self.cmd("Network.clearBrowserCache")
        self.cmd("Network.setCacheDisabled", {"cacheDisabled": True})

    def cmd(self, methode, params=None, timeout=30):
        self.n += 1
        self.ws.envoyer(json.dumps({"id": self.n, "method": methode,
                                    "params": params or {}}))
        fin = time.time() + timeout
        while time.time() < fin:
            m = json.loads(self.ws.recevoir())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError("%s : %s" % (methode, m["error"]))
                return m.get("result", {})
        raise TimeoutError(methode)

    def aller(self, url, attente=4.0):
        self.cmd("Page.navigate", {"url": url})
        time.sleep(attente)

    def js(self, expression):
        r = self.cmd("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": True})
        if r.get("exceptionDetails"):
            return {"_erreur": r["exceptionDetails"].get("text", "?")}
        return r.get("result", {}).get("value")

    def taper(self, x, y):
        """Un vrai tap : c'est ce que le navigateur route vers l'element du
        DESSUS, ce qu'aucune inspection du DOM ne peut simuler."""
        for t in ("mousePressed", "mouseReleased"):
            self.cmd("Input.dispatchMouseEvent", {
                "type": t, "x": x, "y": y, "button": "left", "clickCount": 1})
        time.sleep(0.35)

    def capture(self, chemin, pleine=False):
        r = self.cmd("Page.captureScreenshot",
                     {"format": "png", "captureBeyondViewport": pleine})
        with open(chemin, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        return chemin

    def fermer(self):
        try:
            self.proc.terminate()
        except Exception:
            pass
