"""Le serveur ne compressait rien.

Mesure a l'origine de ce travail, sur une ludotheque de 2 000 titres :
`/api/scan` pesait 2,04 Mio et repartait en entier a chaque affichage, et les
trois fichiers statiques 507 Kio — `_static` posant `Cache-Control: no-store`,
ils repartent a CHAQUE chargement de page. Pour un outil auto-heberge qu'on
atteint souvent depuis l'exterieur, c'est le poste le plus lourd.

Ce qui est verifie ici n'est pas « ca compresse » mais les quatre proprietes
qui font qu'une compression est correcte :

  * le corps decompresse est IDENTIQUE a l'original ;
  * `Content-Length` annonce la taille reellement envoyee ;
  * `Vary: Accept-Encoding` accompagne la reponse, sinon un cache
    intermediaire sert la variante compressee a qui ne sait pas la lire ;
  * un client qui refuse le gzip recoit du clair.

Plus deux pieges specifiques a ce serveur : les images ne doivent pas etre
recompressees, et l'ETag doit distinguer les deux representations — sans quoi
un client qui cesse d'accepter le gzip recevrait un 304 pour un corps qu'il n'a
jamais eu sous cette forme.
"""
import gzip, json, os, socket, subprocess, sys, tempfile, time
import urllib.error, urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)


def libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return str(s.getsockname()[1])


RACINE = str(Path(tempfile.mkdtemp(prefix="ludo-gzip-")).resolve())
jeux = Path(RACINE) / "GAMES"
jeux.mkdir(parents=True)
# Assez de titres pour que l'inventaire depasse largement le seuil.
for i in range(400):
    (jeux / ("Titre numero %03d [0100%012x][v0].nsp" % (i, i))).write_bytes(b"\0" * 64)

PORT = libre()
BASE = "http://127.0.0.1:" + PORT
srv = subprocess.Popen(
    [sys.executable, "-m", "romule", "serve"], cwd=RACINE_PROJET,
    env=dict(os.environ, ROMULE_ROOT=RACINE, ROMULE_WEB_PORT=PORT,
             ROMULE_NO_BROWSER="1", ROMULE_ADB="/inexistant"),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(120):
    try:
        urllib.request.urlopen(BASE + "/api/health", timeout=2); break
    except Exception:
        time.sleep(0.5)

ok = fail = 0


def t(n, c, d=""):
    global ok, fail
    if c: ok += 1; print("      OK   %s" % n)
    else: fail += 1; print("      ECHEC %s  %s" % (n, d))


def demander(chemin, encodage):
    r = urllib.request.Request(BASE + chemin)
    r.add_header("Accept-Encoding", encodage)
    with urllib.request.urlopen(r, timeout=90) as rep:
        return rep.read(), dict(rep.headers), rep.status


try:
    print("   -- les corps qui valent la peine sont compresses --")
    for chemin in ("/api/scan", "/app.js", "/app.css", "/"):
        nu, _, _ = demander(chemin, "identity")
        comp, hc, _ = demander(chemin, "gzip")
        t("%s : compresse" % chemin, hc.get("Content-Encoding") == "gzip",
          hc.get("Content-Encoding"))
        t("%s : identique une fois decompresse" % chemin,
          gzip.decompress(comp) == nu, "%d vs %d" % (len(comp), len(nu)))
        t("%s : plus leger" % chemin, len(comp) < len(nu),
          "%d vs %d" % (len(comp), len(nu)))
        t("%s : Content-Length = ce qui part" % chemin,
          int(hc.get("Content-Length", -1)) == len(comp), hc.get("Content-Length"))
        t("%s : Vary annonce" % chemin,
          "accept-encoding" in (hc.get("Vary", "") or "").lower(), hc.get("Vary"))

    print("   -- qui refuse le gzip recoit du clair --")
    nu, hn, _ = demander("/api/scan", "identity")
    t("aucun Content-Encoding", "Content-Encoding" not in hn, hn.get("Content-Encoding"))
    t("c'est du JSON lisible", nu.lstrip()[:1] == b"{", nu[:20])
    zero, hz, _ = demander("/api/scan", "gzip;q=0")
    t("gzip;q=0 est respecte", "Content-Encoding" not in hz, hz.get("Content-Encoding"))

    print("   -- ce qui ne doit pas etre recompresse --")
    _, hi, _ = demander("/icon-192.png", "gzip")
    t("une icone PNG part telle quelle", "Content-Encoding" not in hi,
      hi.get("Content-Encoding"))

    print("   -- l'ETag distingue les deux representations --")
    _, hgz, _ = demander("/api/scan", "gzip")
    _, hnu, _ = demander("/api/scan", "identity")
    t("ETag different selon l'encodage", hgz.get("ETag") != hnu.get("ETag"),
      (hgz.get("ETag"), hnu.get("ETag")))
    r = urllib.request.Request(BASE + "/api/scan")
    r.add_header("Accept-Encoding", "gzip")
    r.add_header("If-None-Match", hgz.get("ETag"))
    try:
        with urllib.request.urlopen(r, timeout=90) as rep:
            code = rep.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    t("le meme ETag rend 304", code == 304, code)
finally:
    srv.terminate()
print("   ------------------------------------------------")
print("   %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
