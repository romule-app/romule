"""Encapsulation de l'outil `nsz` (inspection, conversion, master keys)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

MK_RE = re.compile(r"master_key_(\d+)")
CONTAINER_TID_RE = re.compile(r"titleId = (01[0-9A-Fa-f]{14})")


def available():
    return shutil.which("nsz") is not None


def _inspect(path):
    try:
        r = subprocess.run(["nsz", "-i", str(path)],
                           capture_output=True, text=True, timeout=120)
        return r.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


"""Cache des title IDs lus dans les conteneurs.

Chaque lecture lance `nsz -i`, un sous-processus qui coute environ un quart de
seconde. Huit fichiers mal nommes suffisaient a rallonger de deux secondes
CHAQUE affichage de la page — alors que le title ID grave dans un fichier ne
change pas tant que le fichier lui-meme ne change pas.

La cle retient la taille et la date de modification : remplacer un fichier par
un autre invalide donc l'entree. L'absence de title ID (`None`) est memorisee
elle aussi — c'est un resultat comme un autre, et il coutait aussi cher.
"""
_TID_CACHE = None


def _cache_charger():
    global _TID_CACHE
    if _TID_CACHE is not None:
        return _TID_CACHE
    try:
        from . import config
        _TID_CACHE = json.loads(config.TIDCACHE.read_text(encoding="utf-8"))
        if not isinstance(_TID_CACHE, dict):
            _TID_CACHE = {}
    except Exception:
        _TID_CACHE = {}
    return _TID_CACHE


def _cache_ecrire():
    try:
        from . import config
        config.TIDCACHE.write_text(
            json.dumps(_TID_CACHE, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass          # cache non ecrit : on relira, sans dommage


def _signature(path):
    st = Path(path).stat()
    return "%d:%d" % (st.st_size, st.st_mtime_ns)


def container_tid(path):
    """Lit le title ID a l'interieur du conteneur (pour les fichiers mal nommes)."""
    cle = str(path)
    cache = _cache_charger()
    try:
        sig = _signature(path)
    except OSError:
        sig = None
    if sig is not None:
        entree = cache.get(cle)
        if isinstance(entree, list) and len(entree) == 2 and entree[0] == sig:
            return entree[1]
    m = CONTAINER_TID_RE.search(_inspect(path))
    tid = m.group(1).lower() if m else None
    if sig is not None:
        cache[cle] = [sig, tid]
        _cache_ecrire()
    return tid


def required_master_key(path):
    """Plus haute master key exigee par un conteneur, ou None."""
    keys = [int(x) for x in MK_RE.findall(_inspect(path))]
    return max(keys) if keys else None


def max_master_key(keyfile):
    """Plus haute master key disponible dans prod.keys (0 si aucune)."""
    keyfile = Path(keyfile)
    if not keyfile.exists():
        return 0
    best = 0
    try:
        for line in keyfile.read_text(errors="ignore").splitlines():
            m = re.match(r"\s*master_key_([0-9a-fA-F]{2})", line)
            if m:
                best = max(best, int(m.group(1), 16))
    except OSError:
        pass
    return best


def convert(src, outdir, threads, verify=True):
    """Decompresse un .nsz/.xcz. Renvoie (ok, chemin_cible, message_erreur)."""
    src = Path(src)
    outdir = Path(outdir)
    ext = src.suffix.lower()
    tgt_ext = {".nsz": ".nsp", ".xcz": ".xci"}.get(ext)
    if tgt_ext is None:
        return (False, None, "extension non convertible")
    tgt = outdir / (src.stem + tgt_ext)

    cmd = ["nsz", "-D", "-w"]
    if verify:
        cmd.append("--quick-verify")
    cmd += ["--threads", str(threads), "--output", str(outdir), str(src)]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, tgt, str(exc))

    if r.returncode == 0 and tgt.exists():
        return (True, tgt, "")

    if tgt.exists():  # sortie partielle : on ne garde pas de fichier tronque
        try:
            tgt.unlink()
        except OSError:
            pass
    out = (r.stdout or "") + (r.stderr or "")
    reasons = [l for l in out.splitlines()
               if re.search(r"error|missing|key|exception|traceback", l, re.I)]
    return (False, tgt, reasons[0].strip() if reasons else "cause inconnue")
