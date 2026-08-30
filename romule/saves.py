"""Sauvegarde des sauvegardes de jeu depuis la console vers le Mac.

C'est le contenu le plus precieux : un jeu se re-telecharge, pas 200 h de
progression. Les sauvegardes partent dans `_saves/<date>/`, jamais ecrasees.

Le chemin des saves depend de l'emulateur et de sa version : on cherche parmi
les emplacements connus, et l'utilisateur peut en imposer un.
"""

from datetime import datetime

from . import config, device

# Emplacements connus des donnees d'emulateurs Switch sous Android.
CANDIDATES = [
    "/storage/emulated/0/Android/data/dev.eden_emu.eden/files/nand/user/save",
    "/storage/emulated/0/Android/data/dev.eden_emu.eden/files",
    "/storage/emulated/0/Android/data/org.yuzu.yuzu_emu/files/nand/user/save",
    "/storage/emulated/0/Android/data/org.citron.citron_emu/files/nand/user/save",
    "/storage/emulated/0/Android/data/org.sudachi.sudachi_emu/files/nand/user/save",
    "/storage/emulated/0/eden/nand/user/save",
    "/storage/emulated/0/yuzu/nand/user/save",
]

SAVES = config.ROOT / "_saves"


def _exists(remote):
    return device._shell("[ -d %s ] && echo 1 || echo 0" % device._q(remote)).strip().endswith("1")


def find_dirs(cfg=None):
    """Emplacements de sauvegardes presents sur la console."""
    if device.state() != "device":
        return []
    found = []
    manual = ((cfg or {}).get("saves_dir") or "").strip().rstrip("/")
    for c in ([manual] if manual else []) + CANDIDATES:
        if c and _exists(c) and c not in found:
            found.append(c)
    if found:
        return found
    # rien de connu : on cherche un dossier "save" sous les donnees d'emulateurs
    out = device._shell(
        "find /storage/emulated/0/Android/data -maxdepth 6 -type d -name save 2>/dev/null | head -5")
    return [l.strip() for l in out.splitlines() if l.strip()]


def backup(job, cfg=None):
    """Copie les sauvegardes de la console vers _saves/<date>/."""
    if device.state() != "device":
        job.log("Console non connectee.")
        return None
    dirs = find_dirs(cfg)
    if not dirs:
        job.log("Aucun dossier de sauvegardes trouve sur la console.")
        job.log("Indique son chemin dans les Reglages si tu le connais.")
        return None

    dest = SAVES / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    job.set_total(len(dirs))
    ok = 0
    for d in dirs:
        if not job.checkpoint():
            job.log("Sauvegarde interrompue.")
            break
        job.log("Recuperation de %s…" % d)
        sub = dest / d.strip("/").replace("/", "_")
        sub.mkdir(parents=True, exist_ok=True)
        rc, out, err = device._run(["pull", d, str(sub)], timeout=3600)
        if rc == 0:
            n = sum(1 for _ in sub.rglob("*") if _.is_file())
            job.log("  %d fichier(s) sauvegarde(s)." % n)
            ok += 1
        else:
            job.log("  Echec : %s" % ((err or out).strip().splitlines() or [""])[-1])
        job.tick()

    if not ok:
        job.log("Rien n'a pu etre sauvegarde.")
        return None
    job.log("Sauvegardes enregistrees dans _saves/%s" % dest.name)
    return str(dest.relative_to(config.ROOT))


def listing():
    out = []
    if SAVES.is_dir():
        for d in sorted(SAVES.iterdir(), reverse=True):
            if d.is_dir():
                files = [p for p in d.rglob("*") if p.is_file()]
                out.append({"name": d.name, "count": len(files),
                            "size": sum(p.stat().st_size for p in files)})
    return out
