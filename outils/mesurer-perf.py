#!/usr/bin/env python3
"""Measures the cost of displaying a synthetic library.

Why this tool exists: `/api/scan` went from 3 871 ms to 60 ms the day the title
IDs read inside the containers were cached. Nothing guards that gain. A
regression of that kind breaks no test — it merely makes the product unpleasant,
and you notice three versions later.

    python3 outils/mesurer-perf.py                  # 500 titles, prints the times
    python3 outils/mesurer-perf.py --titres 2000
    python3 outils/mesurer-perf.py --strict         # exits in error if a threshold breaks
    python3 outils/mesurer-perf.py --json           # for CI

The measurements are taken on a FABRICATED library, made of empty files: we
measure the cost of the walk, the matching and the serialisation, not the disk's.
That is precisely what regresses when a loop becomes quadratic.
"""
import argparse
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Thresholds. Deliberately wide: they catch a collapse, not a 20 % variation
# between two machines. A tight threshold on a shared runner reports nothing but
# noise, and the job ends up ignored.
SEUILS = {
    "demarrage_ms": 4000,      # importing the package + the first inventory
    "scan_froid_ms": 6000,     # the first /api/scan, caches empty
    "scan_chaud_ms": 1200,     # the following ones: what every display pays
    "page_ms": 1500,           # HTML + JS + CSS served
}

JEUX = ["Adventure", "Kingdom", "Racer", "Puzzle", "Chronicles", "Legends",
        "Quest", "Warriors", "Tactics", "Odyssey", "Saga", "Arena"]
RETRO = [("megadrive", ".md"), ("snes", ".sfc"), ("gba", ".gba"),
         ("nes", ".nes"), ("n64", ".z64")]


def fabriquer(racine, titres):
    """A plausible library: games, their updates, a few DLC."""
    alea = random.Random(1234)          # the same library on every run
    games = racine / "GAMES"
    games.mkdir(parents=True, exist_ok=True)
    n = 0
    for i in range(titres):
        tid = "0100%012x" % (i * 0x2000 + 0x1000)
        nom = "%s %s %d" % (alea.choice(JEUX), alea.choice(JEUX), i)
        (games / ("%s [%s][v0].nsp" % (nom, tid))).touch()
        n += 1
        if i % 3 == 0:                  # one update per three titles
            maj = tid[:-3] + "800"
            (games / ("%s [%s][v131072].nsp" % (nom, maj))).touch()
            n += 1
        if i % 7 == 0:                  # un DLC sur sept
            dlc = "%015x1" % (int(tid, 16) >> 4)
            (games / ("%s DLC [%s][v0].nsp" % (nom, dlc))).touch()
            n += 1
    for dossier, ext in RETRO:
        d = racine / dossier
        d.mkdir(parents=True, exist_ok=True)
        for i in range(titres // 10):
            (d / ("%s %d (USA)%s" % (alea.choice(JEUX), i, ext))).touch()
            n += 1
    return n


def _appel(url, timeout=120):
    debut = time.perf_counter()
    with urllib.request.urlopen(url, timeout=timeout) as r:
        r.read()
    return (time.perf_counter() - debut) * 1000


def mesurer(racine, port, repetitions):
    env = dict(os.environ, ROMULE_ROOT=str(racine), ROMULE_WEB_PORT=str(port),
               ROMULE_NO_BROWSER="1", PYTHONUNBUFFERED="1")
    debut = time.perf_counter()
    proc = subprocess.Popen([sys.executable, "-m", "romule", "serve"],
                            cwd=str(RACINE), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % port
    try:
        for _ in range(600):            # up to 60 s: the first inventory counts
            try:
                urllib.request.urlopen(base + "/api/health", timeout=3).read()
                break
            except Exception:
                if proc.poll() is not None:
                    raise RuntimeError(
                        "le serveur s'est arrete au demarrage") from None
                time.sleep(0.1)
        else:
            raise RuntimeError("le serveur n'a pas repondu en 60 s")
        demarrage = (time.perf_counter() - debut) * 1000

        froid = _appel(base + "/api/scan")
        chauds = [_appel(base + "/api/scan") for _ in range(repetitions)]
        # What a display really costs: the page AND the two files without which
        # it shows nothing. Measuring "/" alone returned 0 ms and proved nothing
        # but the speed of a `sendfile`.
        pages = [sum(_appel(base + c) for c in ("/", "/app.js", "/app.css"))
                 for _ in range(repetitions)]
        return {
            "demarrage_ms": round(demarrage),
            "scan_froid_ms": round(froid),
            # the median, not the mean: one garbage-collector pause must not
            # decide on its own whether the version passes
            "scan_chaud_ms": round(statistics.median(chauds)),
            "scan_chaud_max_ms": round(max(chauds)),
            "page_ms": round(statistics.median(pages)),
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


def main():
    ap = argparse.ArgumentParser(description="Mesure de performance de Romule")
    ap.add_argument("--titres", type=int, default=500)
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--repetitions", type=int, default=5)
    ap.add_argument("--strict", action="store_true",
                    help="sortir en erreur si un seuil est depasse")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    racine = Path(tempfile.mkdtemp(prefix="romule-perf-"))
    try:
        t0 = time.perf_counter()
        fichiers = fabriquer(racine, a.titres)
        if not a.json:
            print("Ludotheque fabriquee : %d fichiers pour %d titres (%.1f s)"
                  % (fichiers, a.titres, time.perf_counter() - t0))
        r = mesurer(racine, a.port, a.repetitions)
    finally:
        shutil.rmtree(racine, ignore_errors=True)

    r["titres"] = a.titres
    r["fichiers"] = fichiers
    depasses = [(k, r[k], s) for k, s in SEUILS.items() if r.get(k, 0) > s]

    if a.json:
        r["depasses"] = [k for k, _, _ in depasses]
        print(json.dumps(r, indent=2))
    else:
        print()
        etiquettes = {
            "demarrage_ms": "Demarrage (import + premier inventaire)",
            "scan_froid_ms": "/api/scan a froid (caches vides)",
            "scan_chaud_ms": "/api/scan a chaud  <- paye a CHAQUE affichage",
            "page_ms": "Page d'accueil (HTML + JS + CSS)",
        }
        for cle, texte in etiquettes.items():
            seuil = SEUILS[cle]
            etat = "DEPASSE" if r[cle] > seuil else "ok"
            print("  %-44s %6d ms   (seuil %5d)  %s" % (texte, r[cle], seuil, etat))
        print("  %-44s %6d ms" % ("/api/scan a chaud, pire cas", r["scan_chaud_max_ms"]))
        print()

    for cle, valeur, seuil in depasses:
        print("::warning title=Performance::%s vaut %d ms, au-dessus du seuil de %d ms"
              % (cle, valeur, seuil), file=sys.stderr)
    if depasses and a.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
