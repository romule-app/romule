"""Trash: nothing is deleted, everything is moved and restorable."""

import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import config

STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")

_RESTORE_SCRIPT = (
    "#!/usr/bin/env bash\n"
    "# Remet chaque fichier de cette corbeille a sa place d'origine.\n"
    'set -uo pipefail\n'
    'HERE="$(cd "$(dirname "$0")" && pwd)"\n'
    'DEST="$(cd "$HERE/../.." && pwd)"\n'
    'n=0\n'
    "while IFS=$'\\t' read -r rp _; do\n"
    '  [ -z "$rp" ] && continue\n'
    '  [ -f "$HERE/$rp" ] || continue\n'
    '  mkdir -p "$DEST/$(dirname "$rp")"\n'
    '  mv -n "$HERE/$rp" "$DEST/$rp" && n=$((n+1))\n'
    'done <"$HERE/manifeste.tsv"\n'
    'echo "$n fichier(s) restaure(s)"\n'
)


def _new_run_dir():
    d = config.TRASH / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    man = d / "manifeste.tsv"
    if not man.exists():
        man.touch()
        script = d / "restaurer.sh"
        script.write_text(_RESTORE_SCRIPT)
        script.chmod(0o755)
    return d


def move(paths, reason, log=lambda m: None):
    """Move files into a timestamped trash batch. Returns (n, relative_dir)."""
    d = _new_run_dir()
    moved = 0
    with (d / "manifeste.tsv").open("a") as man:
        for p in paths:
            src = Path(p)
            if not src.is_file():
                continue
            try:
                rp = src.relative_to(config.LUDO)
            except ValueError:
                log("Hors ludotheque, ignore : %s" % src)
                continue
            dest = d / rp
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(src), str(dest))
                man.write("%s\t%s\n" % (rp, reason))
                log("Corbeille : %s" % rp)
                moved += 1
            except OSError as exc:
                log("Deplacement impossible (%s) : %s" % (rp, exc))
    return moved, str(d.relative_to(config.LUDO))


def _taille(d):
    total = 0
    for p in d.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def listing():
    out = []
    if config.TRASH.is_dir():
        for d in sorted(config.TRASH.iterdir(), reverse=True):
            man = d / "manifeste.tsv"
            if man.is_file():
                lines = [l for l in man.read_text(errors="ignore").splitlines() if l.strip()]
                out.append({"name": d.name, "count": len(lines),
                            "size": _taille(d), "age": _age_jours(d)})
    return out


def _age_jours(d):
    return int((time.time() - d.stat().st_mtime) / 86400)


def resume():
    """Overall figures: enough to decide without reading a 50-line list."""
    lots = listing()
    return {"lots": len(lots),
            "fichiers": sum(l["count"] for l in lots),
            "octets": sum(l["size"] for l in lots),
            "plus_vieux": max((l["age"] for l in lots), default=0)}


def purge(jours, log=lambda m: None):
    """Permanently delete batches older than `jours`. 0 = never.

    This is the only function in the tool that really erases data: it acts on
    the trash alone, and only on batches the user chose to let age past the
    delay they set themselves.
    """
    jours = int(jours or 0)
    if jours <= 0 or not config.TRASH.is_dir():
        return 0, 0
    n, octets = 0, 0
    for d in sorted(config.TRASH.iterdir()):
        if not d.is_dir() or not STAMP_RE.match(d.name):
            continue
        if not (d / "manifeste.tsv").is_file():
            continue          # unexpected folder: we leave it alone
        if _age_jours(d) < jours:
            continue
        taille = _taille(d)
        try:
            shutil.rmtree(d)
        except OSError as exc:
            log("Purge impossible (%s) : %s" % (d.name, exc))
            continue
        n += 1
        octets += taille
        log("Corbeille purgee : %s (%.1f Go)" % (d.name, taille / 2 ** 30))
    return n, octets


def restore(name):
    if not STAMP_RE.match(name or ""):
        return "Nom de corbeille invalide."
    script = config.TRASH / name / "restaurer.sh"
    if not script.is_file():
        return "Corbeille introuvable."
    res = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    return res.stdout.strip() or "Restauration terminee."
