"""Backing up the configuration and the accounts.

Neither file can be reconstructed: the configuration carries API keys and the
session signing secret, the accounts file carries password digests. They weigh
a few kilobytes, so we keep a history rather than one copy overwritten every
time — a single corrupt backup is worth nothing.

None of this touches the games: they are too large and already exist in two
copies (server and console).
"""

import json
import os
import shutil
import time
from pathlib import Path

from . import config

FOLDER = config.ROOT / "_sauvegardes"
KEEP = 20                       # nombre de copies conservees


def _sources():
    from . import comptes
    return [config.CONFIG_FILE, comptes.FICHIER]


_LAST_AUTO = [0.0]
AUTO_INTERVAL = 3600.0        # at most one automatic backup an hour


def auto(reason="auto"):
    """A backup triggered by a change, but not by every keystroke.

    Without a limit, every toggle would create a batch: the history would fill
    with noise and the real versions would be pushed out.
    """
    if time.time() - _LAST_AUTO[0] < AUTO_INTERVAL:
        return None
    _LAST_AUTO[0] = time.time()
    try:
        return create(reason)
    except Exception:
        return None


def create(reason="manuelle"):
    """Copy the sensitive files into a timestamped batch. Returns the batch."""
    FOLDER.mkdir(exist_ok=True)
    os.chmod(FOLDER, 0o700)
    batch = FOLDER / (time.strftime("%Y-%m-%d_%H%M%S") + "_" + reason)
    batch.mkdir(exist_ok=True)
    copies = []
    for src in _sources():
        if not Path(src).exists():
            continue
        dst = batch / Path(src).name
        shutil.copy2(src, dst)
        os.chmod(dst, 0o600)
        copies.append(Path(src).name)
    (batch / "_infos.json").write_text(json.dumps({
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "motif": reason,
        "fichiers": copies,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    _prune()
    return {"lot": batch.name, "fichiers": copies}


def _prune():
    lots = sorted([d for d in FOLDER.iterdir() if d.is_dir()])
    for vieux in lots[:-KEEP]:
        shutil.rmtree(vieux, ignore_errors=True)


def listing():
    if not FOLDER.exists():
        return []
    out = []
    for d in sorted((x for x in FOLDER.iterdir() if x.is_dir()), reverse=True):
        try:
            infos = json.loads((d / "_infos.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            infos = {"date": d.name, "motif": "?", "fichiers": []}
        infos["lot"] = d.name
        infos["octets"] = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
        out.append(infos)
    return out


def restore(batch):
    """Restore a batch's files, after backing up the current state first."""
    d = FOLDER / batch
    try:
        d.resolve().relative_to(FOLDER.resolve())
    except (ValueError, OSError) as exc:
        raise ValueError("Lot invalide.") from exc
    if not d.is_dir():
        raise ValueError("Lot introuvable.")
    create("avant-restauration")          # the current state is never lost
    remis = []
    for src in _sources():
        copie = d / Path(src).name
        if copie.exists():
            shutil.copy2(copie, src)
            os.chmod(src, 0o600)
            remis.append(Path(src).name)
    return remis
