"""Integrity checking for the library.

Two levels:
  - a SHA-1 digest of every file, recorded in `_integrity.json`: on the next
    pass, a file whose size has not moved but whose digest has is corrupt
    (silent disk corruption).
  - for Switch containers, an internal check through `nsz --verify`.
"""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

from . import config, nsztool

REGISTRY = config.ROOT / "_integrity.json"


def _load():
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {}


def _save(reg):
    try:
        REGISTRY.write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def sha1(path, job=None, chunk=1 << 22):
    # Same reason as `device.local_sha1`: we detect a damaged file, not a
    # replaced one. The register is there to spot a copy that went wrong.
    h = hashlib.sha1(usedforsecurity=False)
    with open(path, "rb") as f:
        while True:
            if job is not None and not job.checkpoint():
                return None
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def deep_verify(path):
    """Internal check of a Switch container through nsz. (ok, message)"""
    if not nsztool.available():
        return (True, "nsz absent")
    try:
        r = subprocess.run(["nsz", "--verify", str(path)],
                           capture_output=True, text=True, timeout=3600)
        return (r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-1:] or [""])
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, str(exc))


def resume(files=None):
    """State of the register: what is covered, and since when.

    Without it there is no telling whether "no problem" means "everything is
    sound" or "nothing has ever been checked".
    """
    reg = _load()
    dates = sorted(v.get("checked", "") for v in reg.values() if v.get("checked"))
    out = {"empreintes": len(reg),
           "plus_ancienne": dates[0] if dates else None,
           "plus_recente": dates[-1] if dates else None}
    if files is not None:
        connus = {f.get("rel") or Path(f["path"]).name for f in files}
        couverts = connus & set(reg)
        out["fichiers"] = len(connus)
        out["couverts"] = len(couverts)
        out["sans_empreinte"] = len(connus) - len(couverts)
    return out


def _priorite(f, reg):
    """Order of processing: never-checked first, then the oldest."""
    e = reg.get(f.get("rel") or Path(f["path"]).name)
    return (1, e.get("checked", "")) if e else (0, "")


def check(files, job, deep=False, budget_octets=None):
    """Check a list of files ({path,rel,size}). Returns the report.

    `budget_octets` allows a ROLLING check: never-verified files first, then
    the oldest, until the budget runs out. A 160 GB library takes ten minutes
    in one go — nobody runs that often, so in practice nothing was ever
    checked. In slices, coverage grows on every pass.
    """
    reg = _load()
    if budget_octets:
        files = sorted(files, key=lambda f: _priorite(f, reg))
        retenus, cumul = [], 0
        for f in files:
            if cumul and cumul + f.get("size", 0) > budget_octets:
                break
            retenus.append(f)
            cumul += f.get("size", 0)
        job.log("Verification tournante : %d fichier(s) sur %d, %.1f Go."
                % (len(retenus), len(files), cumul / 2 ** 30))
        files = retenus
    job.set_total(len(files))
    changed, missing, verified = [], [], 0

    for f in files:
        if not job.checkpoint():
            job.log("Verification interrompue.")
            break
        p = Path(f["path"])
        rel = f.get("rel") or p.name
        if not p.is_file():
            missing.append(rel)
            job.log("MANQUANT : %s" % rel)
            job.tick()
            continue

        size = p.stat().st_size
        job.set_detail("empreinte de %s…" % p.name[:48])
        digest = sha1(p, job)
        if digest is None:            # interrupted during hashing
            break
        old = reg.get(rel)
        mtime = int(p.stat().st_mtime)
        remplace = old and old.get("mtime") is not None and old["mtime"] != mtime
        if old and old.get("sha1") != digest and old.get("size") == size and not remplace:
            changed.append(rel)
            job.log("CORROMPU : contenu different, taille ET date inchangees — %s" % rel)
        elif old and old.get("sha1") != digest and remplace:
            job.log("Remplace depuis la derniere verification : %s" % rel)
        elif old and old.get("sha1") != digest:
            job.log("Modifie (taille differente, normal si tu l'as remplace) : %s" % rel)
        else:
            verified += 1

        # `mtime` tells "you replaced the file" from "the disk damaged it":
        # without it, a differing digest at equal size was the only clue, and
        # it misses the case of a same-size replacement.
        reg[rel] = {"sha1": digest, "size": size, "mtime": int(p.stat().st_mtime),
                    "checked": datetime.now().strftime("%F %T")}

        if deep and p.suffix.lower() in config.EXTS:
            ok, msg = deep_verify(p)
            if not ok:
                changed.append(rel)
                job.log("Conteneur invalide : %s (%s)" % (rel, msg))
        job.tick()

    _save(reg)
    job.set_detail("")
    job.log("Verification terminee : %d fichier(s) sains, %d suspect(s), %d manquant(s)."
            % (verified, len(changed), len(missing)))
    if changed:
        job.log("A recuperer a nouveau : " + ", ".join(changed[:10]))
    return {"verified": verified, "changed": changed, "missing": missing}
