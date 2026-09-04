"""Backing up game saves from the console to the server.

This is the most precious content: a game can be downloaded again, 200 hours of
progress cannot. Saves go into `_saves/<date>/`, never overwritten.

Where the saves live depends on the emulator and its version: we look through
the known locations, and the user can pin one.
"""

from datetime import datetime

from . import config, device

def candidates():
    """Where to look for saves, from the most specific to the most general.

    This list used to be hard-coded, and it named Eden under a package
    (`dev.eden_emu.eden`) that `nand.py` spelled differently
    (`dev.eden.eden_emulator`): one of the two was necessarily wrong. We now
    start from the active profile, then all the others — someone switching
    emulator wants their old saves back.
    """
    from . import profiles
    out = []
    base = profiles.data_dir()
    if base:
        for rel in (profiles.active().get("sauvegardes") or []):
            out.append(base + "/" + rel.lstrip("/"))
        out.append(base)
    gabarit = "/storage/emulated/0/Android/data/%s/files"
    for prof in profiles.all_profiles():
        for paquet in (prof.get("paquets") or []):
            racine = gabarit % paquet
            for rel in (prof.get("sauvegardes") or ["nand/user/save"]):
                out.append(racine + "/" + rel.lstrip("/"))
    # Older installations, from before emulators moved to Android's
    # application folder.
    out += ["/storage/emulated/0/eden/nand/user/save",
            "/storage/emulated/0/yuzu/nand/user/save"]
    vus, uniques = set(), []
    for c in out:
        if c not in vus:
            vus.add(c)
            uniques.append(c)
    return uniques

SAVES = config.ROOT / "_saves"


def _exists(remote):
    return device._shell("[ -d %s ] && echo 1 || echo 0" % device._q(remote)).strip().endswith("1")


def find_dirs(cfg=None):
    """Emplacements de sauvegardes presents sur la console."""
    if device.state() != "device":
        return []
    found = []
    manual = ((cfg or {}).get("saves_dir") or "").strip().rstrip("/")
    for c in ([manual] if manual else []) + candidates():
        if c and _exists(c) and c not in found:
            found.append(c)
    if found:
        return found
    # nothing known: look for a "save" folder under the emulators' data
    out = device._shell(
        "find /storage/emulated/0/Android/data -maxdepth 6 -type d -name save 2>/dev/null | head -5")
    return [l.strip() for l in out.splitlines() if l.strip()]


def backup(job, cfg=None):
    """Copy the console's saves into _saves/<date>/."""
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
