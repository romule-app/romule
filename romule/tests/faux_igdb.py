"""A fake IGDB + a fake Twitch, to validate the plumbing without real credentials."""
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
            # We return a game that CARRIES the name searched for: since the
            # client sets aside unrelated results (ROM hacks with a neighbouring
            # title), a fixed answer would be rejected — rightly so.
            import re as _re
            m = _re.search(r'search "([^"]*)"', corps)
            cherche = (m.group(1) if m else "Chrono Trigger").strip()
            bas = cherche.lower()
            if "voisin" in bas:
                # The trap the real SteamGridDB set on "Crazy Construction": an
                # UNRELATED game, but well ranked, and equipped with a cover. The
                # client must refuse it.
                return self._j([{"name": "Autre Chose Entierement",
                                 "cover": {"image_id": "co-piege"}}])
            if "sans image" in bas:
                # A known game, but with no cover: that is not a search
                # failure, and it must not strike it off for the summaries.
                return self._j([{"name": cherche, "category": 0,
                                 "summary": "Un jeu sans jaquette."}])
            return self._j([{
                "name": cherche,
                "cover": {"image_id": "co-test"},
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
