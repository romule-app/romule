#!/usr/bin/env python3
"""The README's screenshots, from a library that belongs to nobody.

Why this exists
---------------
The published screenshots showed the author's OWN library: thirty-eight real
titles, their file sizes, and their publishers' cover art. Two problems in one
image — it says what somebody owns, and it redistributes artwork that is not
ours to redistribute. It had been fixed once by hand, and came back the next
time the pictures were refreshed, because "remember to use a fake library" is
not a mechanism.

So the pictures are GENERATED. The library is invented here, the covers are
drawn here, and there is nothing to remember.

    python3 outils/captures.py

Covers are drawn rather than downloaded: a gradient, a monogram, a title. They
look like covers at grid size, which is all a screenshot of a grid needs, and
they belong to this repository.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "romule" / "tests" / "navigateur"))

PORT = 9487
SORTIE = RACINE / "docs" / "images"

# Invented titles, invented publishers. Any resemblance to a real game is the
# fault of a language having only so many words.
CATALOGUE = [
    ("Aurora Drift", "switch", 11.1, ("upd", 3)),
    ("Cinder Vale", "switch", 9.4, ("upd", 0)),
    ("Harbour Lights", "switch", 1.1, None),
    ("Paper Lantern", "switch", 6.7, ("dlc", 1)),
    ("Quiet Harvest", "switch", 10.9, ("upd", 0)),
    ("Salt & Ember", "switch", 6.4, None),
    ("Tideglass", "switch", 4.2, ("upd", 0)),
    ("Verdant Hollow", "switch", 17.1, ("upd", 0)),
    ("Wander Nine", "switch", 2.5, ("upd", 2)),
    ("Zephyr Post", "switch", 3.8, None),
    ("Copper Kite", "switch", 5.4, ("dlc", 2)),
    ("Dune Sparrow", "switch", 6.5, None),
    ("Ember Circuit", "switch", 12.5, ("upd", 0)),
    ("Fathom Line", "switch", 8.0, ("upd", 1)),
    ("Glass Meridian", "switch", 6.2, None),
    ("Hollow Tide", "switch", 17.3, ("dlc", 4)),
    ("Iron Lantern", "gba", 0.008, None),
    ("Jade Circuit", "gba", 0.006, None),
    ("Kelp Forest", "gba", 0.004, None),
    ("Lumen Trail", "snes", 0.002, None),
    ("Marble Sky", "snes", 0.003, None),
    ("Nimbus Rally", "n64", 0.05, None),
    ("Onyx Harbour", "n64", 0.06, None),
    ("Pale Comet", "psx", 0.6, None),
    ("Quartz Divide", "psx", 0.7, None),
    ("River Sentinel", "ps2", 3.2, None),
    ("Silver Fathom", "ps2", 4.1, None),
    ("Thicket & Thorn", "psp", 1.2, None),
    ("Umber Station", "nds", 0.03, None),
    ("Violet Signal", "3ds", 1.4, None),
]

DOSSIERS = {"switch": "GAMES", "gba": "GBA", "snes": "SNES", "n64": "N64",
            "psx": "PSX", "ps2": "PS2", "psp": "PSP", "nds": "NDS",
            "3ds": "3DS"}
EXTS = {"switch": ".nsp", "gba": ".gba", "snes": ".sfc", "n64": ".z64",
        "psx": ".chd", "ps2": ".iso", "psp": ".iso", "nds": ".nds",
        "3ds": ".3ds"}

# One hue per initial, so the grid reads as varied without any choice to make.
TEINTES = [(196, 84, 66), (86, 122, 190), (120, 96, 176), (72, 150, 120),
           (200, 140, 60), (170, 80, 130), (90, 140, 180), (150, 110, 70)]


def _png(largeur, hauteur, pixels):
    """A PNG, written by hand: PIL is not a dependency of this project."""
    brut = b"".join(b"\x00" + bytes(ligne) for ligne in pixels)

    def bloc(nom, corps):
        return (struct.pack(">I", len(corps)) + nom + corps
                + struct.pack(">I", zlib.crc32(nom + corps) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + bloc(b"IHDR", struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0))
            + bloc(b"IDAT", zlib.compress(brut, 9))
            + bloc(b"IEND", b""))


def _jaquette(chemin, titre, teinte):
    """A drawn cover: a vertical gradient, darker at the foot.

    No text — a title rendered without a font library looks like a defect, and
    the interface already writes the name under the card.
    """
    L, H = 300, 400
    r, v, b = teinte
    lignes = []
    for y in range(H):
        k = 0.45 + 0.55 * (1 - y / H)          # light at the top
        bord = 1.0 if 6 < y < H - 6 else 0.55  # a thin frame
        ligne = []
        for x in range(L):
            d = 1.0 if 6 < x < L - 6 else 0.55
            f = k * min(bord, d)
            ligne += [int(r * f), int(v * f), int(b * f)]
        lignes.append(ligne)
    png = Path(str(chemin) + ".png")
    png.write_bytes(_png(L, H, lignes))
    subprocess.run(["sips", "-s", "format", "jpeg", str(png), "--out",
                    str(chemin)], capture_output=True, check=True)
    png.unlink()


def semer(racine):
    """The invented library, on disk."""
    racine = Path(racine)
    covers = racine / "_covers"
    covers.mkdir(parents=True, exist_ok=True)
    for i, (titre, sys_cle, gio, extra) in enumerate(CATALOGUE):
        dossier = racine / DOSSIERS[sys_cle]
        dossier.mkdir(parents=True, exist_ok=True)
        octets = max(2048, int(gio * 1024 * 1024 * 1024))
        # Sparse: a 17 GiB file that costs nothing on disk and reads as 17 GiB.
        if sys_cle == "switch":
            tid = "0100%02x0000%02x0000" % (i + 0x10, i + 1)
            f = dossier / ("%s [%s][v0]%s" % (titre, tid, EXTS[sys_cle]))
            _creuser(f, octets)
            _fiche(covers / ("%s.en.json" % tid), titre)
            _jaquette(covers / ("%s.jpg" % tid.lower()), titre,
                      TEINTES[i % len(TEINTES)])
            if extra and extra[0] == "upd":
                u = dossier / ("%s [%s][v65536]%s"
                               % (titre, tid[:13] + "800", EXTS[sys_cle]))
                _creuser(u, octets // 8)
            for n in range(extra[1] if extra and extra[0] == "dlc" else 0):
                # `tid[:13]`, not `[:12]`: a title ID is SIXTEEN characters,
                # and a fifteen-character one is not recognised as a DLC of
                # anything — each add-on then showed up as a game of its own.
                d = dossier / ("%s DLC %d [%s][v0]%s"
                               % (titre, n + 1, tid[:13] + "%03x" % (n + 1),
                                  EXTS[sys_cle]))
                _creuser(d, octets // 20)
        else:
            _creuser(dossier / (titre + EXTS[sys_cle]), octets)
    (racine / "_romule-config.json").write_text(json.dumps({
        "ui_lang": "en", "auth_mode": "aucun", "acces_choisi": True,
        "assistant_vu": True, "cover_provider": "nlib",
    }), encoding="utf-8")


def _creuser(chemin, octets):
    """A sparse file: the size is what the screenshot shows, and it costs
    nothing to make."""
    with open(chemin, "wb") as f:
        if octets > 1:
            f.seek(octets - 1)
            f.write(b"\0")


def _fiche(chemin, titre):
    chemin.write_text(json.dumps({
        "name": titre, "publisher": "Studio Romule", "releaseDate": "20240101",
        "intro": "An invented entry, for the documentation's screenshots.",
        "description": "This library is fabricated: no real title, no "
                       "third-party artwork, nobody's collection.",
    }), encoding="utf-8")


# Each shot: a file name, the viewport, and what to do before firing. The
# list is the contract — a screen added to the README is added HERE, not taken
# by hand, so the next refresh cannot quietly reintroduce a real library.
# `setSort('nom')` on every library shot: the default sorts by state, which
# puts everything still to transfer first — that is the right order to WORK in,
# and the wrong one to photograph, since it buries every cover at the bottom.
# What must never reach a published image, when `--url` points at a REAL
# installation. `verifier-fuite.py` reads text files; it cannot read a PNG. So
# the masking happens in the DOM, a moment before the shutter, and the shot is
# REFUSED if something it does not know how to mask is still on screen.
#
# The address of the console is the case that already cost a history rewrite:
# it sits in plain sight on the console settings screen. RFC 5737 reserves
# 192.0.2.0/24 for documentation, and RFC 2606 reserves example.org — a masked
# value must still look like what it replaces, or the picture stops explaining
# anything.
MASQUE = r"""
(function () {
  const IPV4 = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;
  const MAIL = /\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g;
  const SERIE = /\b[0-9A-Fa-f]{12,20}\b/g;
  const MAISON = /\/(?:Users|home)\/[^/\s"']+/g;
  const remplace = t => t
    .replace(MAIL, 'moi@exemple.org')
    .replace(IPV4, '192.0.2.10')
    .replace(MAISON, '/home/joueuse')
    .replace(SERIE, 'S0FAKE0SERIAL');
  const marche = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n, touches = 0;
  while ((n = marche.nextNode())) {
    const avant = n.nodeValue;
    const apres = remplace(avant);
    if (apres !== avant) { n.nodeValue = apres; touches++; }
  }
  // The attributes too: a tooltip carries the address as readily as a line of
  // text, and a screenshot taken with the pointer on it would show it.
  for (const el of document.querySelectorAll('[title],[aria-label],[value]')) {
    for (const a of ['title', 'aria-label', 'value']) {
      const v = el.getAttribute(a);
      if (v) el.setAttribute(a, remplace(v));
    }
  }
  // What is LEFT is the point of this function. Anything still matching is
  // something the masking does not know about, and the shot must not be taken.
  const reste = [];
  const texte = document.body.innerText || '';
  for (const [nom, re] of [['adresse', IPV4], ['courriel', MAIL],
                           ['chemin personnel', MAISON]]) {
    const m = texte.match(re) || [];
    for (const x of m) {
      if (x !== '192.0.2.10' && x !== 'moi@exemple.org' && x !== '/home/joueuse') {
        reste.push(nom + ' : ' + x);
      }
    }
  }
  return {touches: touches, reste: reste.slice(0, 6)};
})()
"""


PRISES = [
    ("bibliotheque", 1600, 1100, 2, "app.tab('jeux'); app.setSort('nom')", True),
    ("fiche", 1500, 1000, 2,
     "app.tab('jeux'); (function(){const c=document.querySelector('#lib .gcard');"
     "if (c) app.openGame(c.dataset.key);})()", False),
    ("console", 1500, 1250, 2,
     "app.closeGame(); app.tab('settings');"
     "document.querySelector(\"#setnav a[href='#sec-console']\").click();"
     "app.detectPlatforms(true)", False),
    ("sante", 1400, 950, 2,
     "app.tab('jeux'); app.showMaintenance('sante')", False),
    ("assistant", 1300, 1000, 2,
     "app.closeDialog(); app.showOnboard()", False),
    ("bureau", 1440, 900, 2,
     "app.closeOnboard(); app.tab('jeux'); app.setSort('nom')", False),
    # A handheld's screen is WIDE and short — 16:9 in the hand. Framing the
    # phone shot in a handheld shell showed a portrait screen in a landscape
    # shell, which is the one thing the picture is meant to explain.
    ("portable", 960, 560, 2, "app.tab('jeux'); app.setSort('nom')", False),
    ("telephone", 420, 880, 3, "app.tab('jeux'); app.setSort('nom')", False),
]

# The frames the old pictures had, drawn in CSS instead of Photoshop: a browser
# chrome, a handheld shell, a phone shell. A mock-up that cannot be regenerated
# is a mock-up that goes stale, and this one is rebuilt with the shots.
COMPOSITION = """<!doctype html><meta charset="utf-8"><style>
  body{margin:0;background:#0d0b10;font:14px/1.4 ui-monospace,Menlo,monospace;
       color:#8d8492;padding:56px 48px;display:flex;gap:48px;
       align-items:flex-end;justify-content:center}
  .piece{display:flex;flex-direction:column;align-items:center;gap:14px}
  .legende{letter-spacing:.16em;text-transform:uppercase;font-size:11px}
  .legende b{color:#e0a340;font-weight:400}
  /* A browser window: three dots and an address bar. */
  .bureau{width:1080px;border-radius:14px;overflow:hidden;
          border:1px solid #2a2630;background:#151219;
          box-shadow:0 30px 80px rgba(0,0,0,.55)}
  .barre{display:flex;align-items:center;gap:9px;padding:11px 14px;
         background:#1b1720;border-bottom:1px solid #2a2630}
  .pastille{width:11px;height:11px;border-radius:50%%}
  .adresse{flex:1;margin-left:10px;padding:5px 12px;border-radius:7px;
           background:#0f0d13;color:#6b6474;font-size:12px}
  .bureau img,.ecran img{display:block;width:100%%}
  /* A handheld: a wide screen between two grips. */
  .portable{position:relative;padding:30px 92px;border-radius:44px;
            background:linear-gradient(#2a2533,#1d1926);
            border:1px solid #342e40;box-shadow:0 24px 60px rgba(0,0,0,.5)}
  .portable::before,.portable::after{content:'';position:absolute;top:50%%;
            width:52px;height:52px;border-radius:50%%;background:#12101a;
            border:1px solid #3a3446;transform:translateY(-50%%)}
  .portable::before{left:22px} .portable::after{right:22px}
  .ecran{width:430px;border-radius:8px;overflow:hidden;background:#000}
  .telephone{padding:14px;border-radius:42px;background:#1d1926;
             border:1px solid #342e40;box-shadow:0 24px 60px rgba(0,0,0,.5)}
  .telephone .ecran{width:250px;border-radius:30px}
</style>
<div class="piece">
  <div class="bureau">
    <div class="barre">
      <span class="pastille" style="background:#e05a4f"></span>
      <span class="pastille" style="background:#e0a340"></span>
      <span class="pastille" style="background:#6fbf8b"></span>
      <span class="adresse">romule.local:8787</span>
    </div>
    <img src="%(bureau)s" alt="">
  </div>
  <div class="legende">Desktop &mdash; <b>every platform at once</b></div>
</div>
<div class="piece">
  <div class="portable"><div class="ecran"><img src="%(portable)s" alt=""></div></div>
  <div class="legende">Handheld &mdash; <b>the d-pad walks the grid</b></div>
</div>
<div class="piece">
  <div class="telephone"><div class="ecran"><img src="%(telephone)s" alt=""></div></div>
  <div class="legende">Phone &mdash; <b>filters folded away</b></div>
</div>
"""


def _data_uri(chemin):
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(
        Path(chemin).read_bytes()).decode("ascii")


def _en_jpeg(png, qualite="80", cote_max=2000):
    """JPEG, bounded. A retina full-page shot is 3200 px wide and close to a
    megabyte; the README shows it at 900. `cote_max` is what keeps a repository
    of pictures from outweighing its code."""
    cible = png.with_suffix(".jpg")
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions",
                    qualite, "-Z", str(cote_max), str(png), "--out",
                    str(cible)], capture_output=True, check=True)
    png.unlink()
    return cible


def _appel(url, chemin, corps=None):
    import json as _j
    import urllib.request as _u
    donnees = _j.dumps(corps or {}).encode() if corps is not None else None
    req = _u.Request(url + chemin, data=donnees,
                     headers={"Content-Type": "application/json"})
    with _u.urlopen(req, timeout=60) as r:
        return _j.loads(r.read())


def _reglage(url, cle):
    try:
        return (_appel(url, "/api/config", {}).get("config") or {}).get(cle)
    except Exception:
        return None


def _poser(url, valeurs):
    try:
        _appel(url, "/api/config", valeurs)
    except Exception:
        pass


def main(argv=()):
    """Take the shots. With no argument, from an invented library.

    `--url http://localhost:8787` photographs a RUNNING instance instead —
    yours, with your games in it. That is a deliberate choice and not the
    default: a shot taken from a real installation says what its owner owns,
    and carries somebody else's cover art into a public repository. It has
    happened twice here. The invented library exists so that the ordinary
    answer costs nothing.
    """
    from cdp import Navigateur
    externe = ""
    for i, a in enumerate(argv):
        if a == "--url" and i + 1 < len(argv):
            externe = argv[i + 1].rstrip("/")
        elif a.startswith("--url="):
            externe = a.split("=", 1)[1].rstrip("/")
    proc = None
    langue_avant = None
    if externe:
        url = externe
        print("  depuis %s (installation existante)" % url)
        # The published pages are in English, and the interface speaks whatever
        # `ui_lang` says — which on a real installation is its owner's
        # language. We borrow the setting and give it back, whatever happens
        # below: leaving somebody's interface in another language because a
        # screenshot failed is not an acceptable trace to leave.
        langue_avant = _reglage(url, "ui_lang")
        if langue_avant and langue_avant != "en":
            _poser(url, {"ui_lang": "en"})
            print("  langue : %s -> en (rendue a la fin)" % langue_avant)
    else:
        racine = tempfile.mkdtemp(prefix="romule-captures-")
        semer(racine)
        adb = RACINE / "outils" / "adb-vitrine.py"
        proc = subprocess.Popen(
            [sys.executable, "-m", "romule", "serve"], cwd=str(RACINE),
            env=dict(os.environ, ROMULE_ROOT=racine, ROMULE_WEB_PORT=str(PORT),
                     ROMULE_NO_BROWSER="1", ROMULE_LANG="en",
                     ROMULE_ADB=str(adb.resolve())),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = "http://127.0.0.1:%d" % PORT
    faites = {}
    try:
        import urllib.request
        for _ in range(60):
            try:
                urllib.request.urlopen(url + "/api/health", timeout=2).read()
                break
            except Exception:
                time.sleep(0.5)
        SORTIE.mkdir(parents=True, exist_ok=True)
        n = Navigateur(port=9488, largeur=1600, hauteur=1100, dpr=2,
                       assistant=True)
        try:
            n.aller(url, attente=6.0)
            n.js("app.detect()")
            time.sleep(3.0)
            for nom, L, H, dpr, geste, pleine in PRISES:
                n.cmd("Emulation.setDeviceMetricsOverride",
                      {"width": L, "height": H, "deviceScaleFactor": dpr,
                       "mobile": dpr >= 3})
                time.sleep(0.8)
                n.js(geste)
                time.sleep(2.2)
                if externe:
                    # A real installation: mask, then REFUSE if something the
                    # masking does not know is still readable. A warning here
                    # would be read after the image is published.
                    m = n.js(MASQUE) or {}
                    if m.get("reste"):
                        raise SystemExit(
                            "  %s : capture refusee, il reste %s"
                            % (nom, " ; ".join(m["reste"])))
                    time.sleep(0.3)
                png = SORTIE / (nom + ".png")
                n.capture(str(png), pleine=pleine)
                faites[nom] = _en_jpeg(png, "78", 1800)
                print("  %-12s %d ko%s" % (nom, faites[nom].stat().st_size // 1024,
                                           "" if not externe else "  (masque)"))
        finally:
            n.fermer()

        # The three framed pieces, from the shots just taken.
        page = Path(tempfile.mkdtemp()) / "composition.html"
        page.write_text(COMPOSITION % {
            "bureau": _data_uri(faites["bureau"]),
            "portable": _data_uri(faites["portable"]),
            "telephone": _data_uri(faites["telephone"]),
        }, encoding="utf-8")
        n = Navigateur(port=9489, largeur=2100, hauteur=1200, dpr=2,
                       assistant=True)
        try:
            n.aller(page.as_uri(), attente=3.0)
            # The viewport is resized to the CONTENT before firing: a full-page
            # capture is at least as tall as the window, and the composition is
            # shorter than that — which left a third of the picture black.
            haut = n.js("Math.ceil(document.body.getBoundingClientRect().height)")
            n.cmd("Emulation.setDeviceMetricsOverride",
                  {"width": 2100, "height": int(haut or 1200),
                   "deviceScaleFactor": 2, "mobile": False})
            time.sleep(1.0)
            png = SORTIE / "apercu.png"
            n.capture(str(png), pleine=True)
            cible = _en_jpeg(png, "82", 2600)
            print("  %-12s %d ko" % ("apercu", cible.stat().st_size // 1024))
        finally:
            n.fermer()
        # The framed picture replaces the two raw viewport shots.
        for nom in ("bureau", "portable", "telephone"):
            faites[nom].unlink(missing_ok=True)
        for vieux in ("apercu-bureau.jpg", "apercu-portables.jpg"):
            (SORTIE / vieux).unlink(missing_ok=True)
    finally:
        if langue_avant and langue_avant != "en":
            _poser(externe, {"ui_lang": langue_avant})
            print("  langue rendue : %s" % langue_avant)
        if proc is not None:
            proc.terminate()
            shutil.rmtree(racine, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
