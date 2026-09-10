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


def main():
    from cdp import Navigateur
    racine = tempfile.mkdtemp(prefix="romule-captures-")
    semer(racine)
    faux_adb = RACINE / "romule" / "tests" / "navigateur" / ".." / "faux_adb.py"
    proc = subprocess.Popen(
        [sys.executable, "-m", "romule", "serve"], cwd=str(RACINE),
        env=dict(os.environ, ROMULE_ROOT=racine, ROMULE_WEB_PORT=str(PORT),
                 ROMULE_NO_BROWSER="1", ROMULE_LANG="en",
                 ROMULE_ADB=str(faux_adb.resolve()), ROMULE_FAUX_ADB="aucune"),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "http://127.0.0.1:%d" % PORT
    try:
        import urllib.request
        for _ in range(60):
            try:
                urllib.request.urlopen(url + "/api/health", timeout=2).read()
                break
            except Exception:
                time.sleep(0.5)
        n = Navigateur(port=9488, largeur=1600, hauteur=1150, dpr=2,
                       assistant=True)
        try:
            n.aller(url, attente=6.0)
            n.js("app.tab('jeux')")
            time.sleep(3.0)
            SORTIE.mkdir(parents=True, exist_ok=True)
            n.capture(str(SORTIE / "bibliotheque.png"), pleine=True)
            print("bibliotheque : capturee")
            # The desktop viewport, without scrolling the whole page: what
            # somebody actually sees when they open it.
            n.cmd("Emulation.setDeviceMetricsOverride",
                  {"width": 1440, "height": 900, "deviceScaleFactor": 2,
                   "mobile": False})
            time.sleep(1.5)
            n.capture(str(SORTIE / "apercu-bureau.png"))
            print("apercu-bureau : capturee")
            n.cmd("Emulation.setDeviceMetricsOverride",
                  {"width": 430, "height": 932, "deviceScaleFactor": 3,
                   "mobile": True})
            time.sleep(1.5)
            n.capture(str(SORTIE / "apercu-portables.png"))
            print("apercu-portables : capturee")
        finally:
            n.fermer()
    finally:
        proc.terminate()
        shutil.rmtree(racine, ignore_errors=True)
    for p in SORTIE.glob("*.png"):
        cible = p.with_suffix(".jpg")
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions",
                        "80", str(p), "--out", str(cible)],
                       capture_output=True, check=True)
        p.unlink()
        print("%s : %d ko" % (cible.name, cible.stat().st_size // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
