"""Conversion .nsz/.xcz -> .nsp/.xci via nsz, en parallele et sans surprise."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import nsztool


def run(paths, jobs, threads, precheck, maxkey, job, verify=True):
    """Convertit une liste de fichiers. Precontrole optionnel des master keys."""
    jobs = max(1, jobs)
    tpj = max(1, threads // jobs)

    todo = []
    if precheck and maxkey:
        job.log("Controle des master keys (%d fichier(s))..." % len(paths))
        for p in paths:
            need = nsztool.required_master_key(p)
            if need is not None and need > maxkey:
                job.log("EXCLU %s : exige master_key_%d, tu as %d"
                        % (Path(p).name, need, maxkey))
            else:
                todo.append(p)
    else:
        todo = list(paths)

    job.set_total(len(todo))
    if not todo:
        job.log("Rien a convertir.")
        return []

    converted = []

    def one(p):
        if not job.checkpoint():
            return
        src = Path(p)
        job.log("Conversion : %s" % src.name)
        ok, tgt, err = nsztool.convert(src, src.parent, tpj, verify)
        if ok:
            job.log("OK  %s (%.1f Mo)" % (tgt.name, tgt.stat().st_size / 1048576))
            converted.append(str(src))
        else:
            job.log("ECHEC %s : %s" % (src.name, err))
        job.tick()

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(one, todo))

    job.log("Conversion terminee (%d/%d)." % (len(converted), len(todo)))
    return converted


def default_threads():
    return os.cpu_count() or 4
