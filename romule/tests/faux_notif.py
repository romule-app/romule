"""A fake Discord / Slack / Telegram / ntfy / Gotify, to check the SHAPE.

Sending the same JSON everywhere would work for none of these services: Discord
wants `embeds`, Slack wants `text`, ntfy wants plain text with the title in a
header. A test content with "a request went out" would let five mute
integrations through.
"""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9931
RECU = []


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
        corps = self.rfile.read(n).decode("utf-8", "replace")
        RECU.append({"chemin": self.path, "corps": corps,
                     "type": self.headers.get("Content-Type", ""),
                     "titre": self.headers.get("Title", ""),
                     "priorite": self.headers.get("Priority", "")})
        if self.path.startswith("/refuse"):
            return self._j({"error": "non"}, 500)
        self._j({"ok": True})

    def do_GET(self):
        if self.path == "/_recu":
            return self._j(RECU)
        if self.path == "/_vider":
            RECU.clear()
            return self._j({"ok": True})
        self._j({"error": "?"}, 404)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
