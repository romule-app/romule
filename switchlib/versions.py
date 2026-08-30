"""Base de versions titledb : telechargement, cache 24 h, parsing."""

import time
import urllib.request

from . import config


def load(lib, force=False, log=lambda m, n=None: None):
    """Charge la base de versions dans lib.versions. Telecharge si perimee."""
    fresh = (config.VCACHE.exists()
             and (time.time() - config.VCACHE.stat().st_mtime) < 86400)
    if force or not fresh:
        _download(log)
    if not config.VCACHE.exists():
        lib.versions = {}
        lib.versions_at = None
        return {}

    vdb = {}
    for line in config.VCACHE.read_text(errors="ignore").splitlines()[1:]:
        parts = line.split("|")
        if len(parts) == 3 and parts[2].strip().isdigit():
            vdb[parts[0].strip().lower()] = int(parts[2])
    lib.versions = vdb
    lib.versions_at = config.VCACHE.stat().st_mtime
    return vdb


def _download(log):
    urls = config.load_config().get("versions_urls") or config.VERSIONS_URLS
    for url in urls:
        log("Telechargement de la base de versions...")
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                data = r.read()
            if b"version" not in data[:80]:
                raise ValueError("contenu inattendu")
            config.VCACHE.write_bytes(data)
            log("Base de versions enregistree (%.1f Mo)" % (len(data) / 1048576))
            return
        except Exception as exc:  # reseau/miroir indisponible : on tente le suivant
            log("Miroir indisponible (%s) : %s" % (url.split("/")[2], exc))
    log("Telechargement impossible — on garde le cache existant s'il y en a un.")
