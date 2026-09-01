"""Verification d'integrite de la ludotheque.

Deux niveaux :
  - empreinte SHA-1 de chaque fichier, memorisee dans `_integrity.json` :
    au passage suivant, un fichier dont la taille n'a pas bouge mais dont
    l'empreinte a change est corrompu (corruption silencieuse du disque).
  - pour les conteneurs Switch, verification interne via `nsz --verify`.
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
    # Meme raison que `device.local_sha1` : on detecte un fichier abime, pas un
    # fichier remplace. Le registre sert a reperer une copie qui a mal tourne.
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
    """Verification interne d'un conteneur Switch via nsz. (ok, message)"""
    if not nsztool.available():
        return (True, "nsz absent")
    try:
        r = subprocess.run(["nsz", "--verify", str(path)],
                           capture_output=True, text=True, timeout=3600)
        return (r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-1:] or [""])
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, str(exc))


def resume(files=None):
    """Etat du registre : ce qui est couvert, et depuis quand.

    Sans cela on ne sait pas si « aucun probleme » veut dire « tout est sain »
    ou « rien n'a jamais ete verifie ».
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
    """Ordre de passage : jamais verifie d'abord, puis le plus ancien."""
    e = reg.get(f.get("rel") or Path(f["path"]).name)
    return (1, e.get("checked", "")) if e else (0, "")


def check(files, job, deep=False, budget_octets=None):
    """Verifie une liste de fichiers ({path,rel,size}). Renvoie le rapport.

    `budget_octets` permet une verification TOURNANTE : on traite d'abord ce
    qui n'a jamais ete verifie, puis le plus ancien, jusqu'a epuisement du
    budget. Une ludotheque de 160 Go demande une dizaine de minutes en un
    bloc — personne ne lance ca souvent, donc en pratique rien n'etait jamais
    verifie. Par tranches, la couverture progresse a chaque passage.
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
        if digest is None:            # interrompu pendant le hash
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

        # `mtime` distingue « tu as remplace le fichier » de « le disque l'a
        # abime » : sans lui, une empreinte differente a taille egale etait le
        # seul indice, et il manque le cas d'un remplacement de meme taille.
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
