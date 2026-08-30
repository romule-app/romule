"""Faux IGDB + faux Twitch, pour valider la plomberie sans identifiants reels."""
import json, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9911
DEMANDES = {"jetons": 0, "requetes": []}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _j(self, o, code=200):
        b = json.dumps(o).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        corps = self.rfile.read(n).decode()
        if self.path.startswith("/oauth2/token"):
            d = urllib.parse.parse_qs(corps)
            if d.get("client_id", [""])[0] != "bon-id":
                return self._j({"status": 403, "message": "invalid client"}, 403)
            DEMANDES["jetons"] += 1
            return self._j({"access_token": "jeton-test", "expires_in": 3600})
        if self.path.endswith("/games"):
            if self.headers.get("Authorization") != "Bearer jeton-test":
                return self._j({"message": "Unauthorized"}, 401)
            DEMANDES["requetes"].append(corps)
            if "introuvable" in corps.lower():
                return self._j([])
            # On renvoie un jeu qui PORTE le nom cherche : depuis que le client
            # ecarte les resultats sans rapport (hacks de ROM au titre voisin),
            # une reponse fixe serait rejetee — a juste titre.
            import re as _re
            m = _re.search(r'search "([^"]*)"', corps)
            cherche = (m.group(1) if m else "Chrono Trigger").strip()
            return self._j([{
                "name": cherche,
                "category": 0,
                "summary": "Un groupe d'aventuriers voyage a travers le temps.",
                "first_release_date": 793843200,
                "involved_companies": [
                    {"publisher": False, "company": {"name": "Studio X"}},
                    {"publisher": True, "company": {"name": "Square"}}],
            }])
        self._j({"error": "route inconnue"}, 404)

    def do_GET(self):
        if self.path == "/_compteurs":
            return self._j(DEMANDES)
        self._j({"error": "?"}, 404)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
