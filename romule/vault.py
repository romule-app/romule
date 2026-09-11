"""Copying what cannot be downloaded again, somewhere other than where it lives.

Three things already did a third of this job, and none of them said WHERE the
copy lands:

  * `backup.py` copies the configuration and the accounts into `_sauvegardes/`;
  * `saves.py` pulls the console's game saves into `_saves/`;
  * the library itself sits in one folder, on one disk.

All three write to the same disk as the thing they protect, which is the one
failure a backup exists for. So this module adds the two things they lacked — a
DESTINATION the user chooses, and a ROTATION so the history cannot fill it —
and treats the rest as sources it collects.

A run, in order:

  1. resolve the chosen sources into a list of files, with their total size;
  2. REFUSE if the destination has not got the room — before copying anything.
     Finding out at 94 % is finding out too late, and it leaves a half batch
     that looks like a whole one;
  3. copy, with progress and an ETA computed from the measured rate;
  4. write `manifeste.json` into the batch: what it holds, when, from where.
     A batch must be readable without Romule — that is the point of a backup;
  5. rotate, oldest first, down to the number of batches asked for.

Every step goes into the journal, because an unattended copy that says nothing
is a copy nobody checks.

Where the destination may be
----------------------------
`config.within_bases`, the same rule as browsing and as choosing the library.
The reasoning is in `browse.py`: in a container the mounts are the allow-list
and the kernel enforces it; natively it is the service account. An external
disk or a folder synced by a cloud client is, from here, just a path — which is
why those destinations need no credentials and no network code.
"""

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from . import config, langue, messages

# The marker that makes a folder recognisable as ours. Rotation DELETES, so it
# must never be able to mistake somebody's documents for one of its batches.
MARQUE = "manifeste.json"
PREFIXE = "romule-"

# How many batches are kept when nothing is set. Five nights is enough to
# notice a mistake and go back before it; more, and a library backup fills any
# disk you point it at.
GARDER_DEFAUT = 5

# A backup that fills the disk it lands on takes the machine down with it, and
# the copy is unusable anyway. We keep a floor free rather than aim at the last
# byte.
_MARGE = 256 * 1024 * 1024

# What can be copied. `kind` says who holds it: the SERVER (files we can stat)
# or the CONSOLE (pulled over adb, and therefore only when one answers).
SOURCES = [
    {"cle": "sauvegardes", "kind": "console", "libelle": 'Sauvegardes de jeu'},
    {"cle": "jeux", "kind": "serveur", "libelle": 'Jeux'},
    {"cle": "maj", "kind": "serveur", "libelle": 'Mises à jour'},
    {"cle": "dlc", "kind": "serveur", "libelle": 'DLC'},
    {"cle": "jaquettes", "kind": "serveur", "libelle": 'Jaquettes et fiches'},
    {"cle": "config", "kind": "serveur", "libelle": 'Configuration et comptes'},
]
CLES = [s["cle"] for s in SOURCES]

# A library file's `type`, as `scan.py` writes it, and the source it belongs to.
# `INCONNU` is not a gap: a Mega Drive ROM has no title ID, and it is a game.
_PAR_TYPE = {"BASE": "jeux", "UPDATE": "maj", "DLC": "dlc", "INCONNU": "jeux"}


def _human(b):
    if b is None:
        return "?"
    for u in ("o", "Kio", "Mio", "Gio", "Tio"):
        if b < 1024:
            return "%d %s" % (b, u) if u == "o" else "%.1f %s" % (b, u)
        b /= 1024
    return "%.1f Pio" % b


# --------------------------------------------------------------- destinations

# Where removable media get mounted, per system. A backup's natural home is a
# disk you can unplug and carry away.
_MONTAGES = ("/Volumes", "/media", "/run/media", "/mnt")

# Folders a cloud client keeps in sync. Romule does not talk to Dropbox or to
# Drive: it writes into the folder their own client already watches, which is
# the only way a tool with no dependencies can reach them — and the only way
# that keeps working when their API changes.
_NUAGES = (
    ("Dropbox", "Dropbox"),
    ("Google Drive", "Google Drive"),
    ("Google Drive", "GoogleDrive"),
    ("OneDrive", "OneDrive"),
    ("Nextcloud", "Nextcloud"),
    ("pCloud", "pCloudDrive"),
    ("Syncthing", "Sync"),
)


def _lisible(p):
    try:
        return p.is_dir() and os.access(p, os.W_OK)
    except OSError:
        return False


def _espace(p):
    try:
        return shutil.disk_usage(str(p)).free
    except OSError:
        return None


def destinations(cfg=None):
    """The places offered, discovered rather than typed.

    Typing a path is the fallback, not the offer: someone who has just plugged
    a disk in wants to see its name, not to remember where their system mounts
    it.
    """
    out, vus = [], set()

    def ajoute(genre, nom, chemin):
        p = Path(chemin)
        try:
            p = p.resolve()
        except OSError:
            return
        if str(p) in vus or not _lisible(p) or not config.within_bases(p):
            return
        vus.add(str(p))
        out.append({"genre": genre, "nom": nom, "chemin": str(p),
                    "libre": _espace(p), "lots": len(lots(p))})

    for racine in _MONTAGES:
        base = Path(racine)
        if not base.is_dir():
            continue
        try:
            entrees = sorted(base.iterdir())
        except OSError:
            continue
        for e in entrees:
            if e.name.startswith("."):
                continue
            # /media/<user>/<disk> on Linux: the disk is one level further
            # down, under the account's name. Offering the account's folder
            # would name a place nobody plugged in.
            enfants = []
            if racine in ("/media", "/run/media"):
                try:
                    enfants = [c for c in sorted(e.iterdir()) if c.is_dir()]
                except OSError:
                    enfants = []
            for cible in (enfants or [e]):
                ajoute("externe", cible.name, cible)

    maison = Path.home()
    for nom, rel in _NUAGES:
        ajoute("nuage", nom, maison / rel)
    # macOS files every cloud client under one folder, one entry per ACCOUNT:
    # `GoogleDrive-someone@example.org/My Drive`. The parent is not a
    # destination — nothing syncs it — so we go one level down and read the
    # provider off the name.
    nuage = maison / "Library" / "CloudStorage"
    if nuage.is_dir():
        try:
            comptes = sorted(nuage.iterdir())
        except OSError:
            comptes = []
        for c in comptes:
            if not c.is_dir() or c.name.startswith("."):
                continue
            fournisseur = c.name.split("-")[0]
            for cible in sorted(c.iterdir()) if c.is_dir() else []:
                if cible.is_dir():
                    ajoute("nuage", "%s — %s" % (fournisseur, cible.name), cible)

    # Last, and never first: the service's own disk. It is a destination — a
    # copy beats no copy — but it is the one that does not survive the failure
    # this module exists for, so its genre is said out loud beside it. It is
    # offered even before it exists: a folder we create on first use is not a
    # place the user has to go and make.
    local = config.ROOT / "_coffre"
    if local.is_dir():
        ajoute("local", 'Dossier de données du service', local)
    elif config.within_bases(config.ROOT) and os.access(str(config.ROOT), os.W_OK):
        out.append({"genre": "local", "nom": 'Dossier de données du service',
                    "chemin": str(local), "libre": _espace(config.ROOT), "lots": 0})
    return out


def dest_defaut(cfg):
    """The destination in force: the one chosen, or nothing."""
    choisi = str((cfg or {}).get("backup_dest") or "").strip()
    return choisi


def verifier_dest(chemin, creer=False):
    """Resolve a destination, or say why not. Never raises."""
    brut = str(chemin or "").strip()
    if not brut:
        return None, messages.CF_DEST_ABSENTE
    p = Path(brut).expanduser()
    try:
        p = p.resolve()
    except OSError as exc:
        return None, langue.phrase(messages.CF_DEST_ILLISIBLE, exc)
    if not config.within_bases(p):
        return None, messages.CHEMIN_HORS_BASES
    if not p.is_dir():
        if not creer:
            return None, messages.CF_DEST_INEXISTANTE
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return None, langue.phrase(messages.CF_DEST_ILLISIBLE, exc)
    if not os.access(p, os.W_OK):
        return None, messages.CF_DEST_LECTURE_SEULE
    return p, None


# --------------------------------------------------------------- the batches


def lots(dest):
    """The batches present at a destination, newest first.

    Only folders carrying our manifest count. Rotation deletes, and it must be
    incapable of mistaking somebody's holiday photos for a batch of ours.
    """
    out = []
    try:
        p = Path(dest)
        if not p.is_dir():
            return []
        entrees = sorted(p.iterdir(), reverse=True)
    except OSError:
        return []
    for d in entrees:
        if not d.is_dir() or not d.name.startswith(PREFIXE):
            continue
        m = d / MARQUE
        if not m.is_file():
            continue
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        out.append({"nom": d.name, "chemin": str(d),
                    "date": data.get("date", ""),
                    "sources": data.get("sources", []),
                    "fichiers": data.get("fichiers", 0),
                    "octets": data.get("octets", 0),
                    "complet": bool(data.get("complet"))})
    return out


# ------------------------------------------------------ what we are copying


def _fichiers_serveur(lib, cfg, sources):
    """The server-side files to copy, as (absolute path, path inside the batch)."""
    items = []
    voulus = set(sources)
    if voulus & {"jeux", "maj", "dlc"}:
        for f in (getattr(lib, "files", None) or []):
            cle = _PAR_TYPE.get(f.get("type"), "jeux")
            if cle not in voulus:
                continue
            items.append((Path(f["path"]), Path(cle) / f["rel"], f.get("size") or 0))
    if "jaquettes" in voulus:
        items += _arbre(config.ROOT / "_covers", "jaquettes")
    if "config" in voulus:
        from . import accounts
        for src in (config.CONFIG_FILE, accounts.FILE):
            p = Path(src)
            if p.is_file():
                items.append((p, Path("config") / p.name, p.stat().st_size))
        items += _arbre(config.ROOT / "_sauvegardes", "config/historique")
    return items


def _arbre(racine, prefixe):
    """Every file under a folder, with its place inside the batch."""
    racine = Path(racine)
    out = []
    if not racine.is_dir():
        return out
    for chemin, _dirs, noms in os.walk(str(racine)):
        for n in noms:
            p = Path(chemin) / n
            try:
                taille = p.stat().st_size
            except OSError:
                continue
            out.append((p, Path(prefixe) / p.relative_to(racine), taille))
    return out


def apercu(lib, cfg, sources=None):
    """What each source weighs, without copying anything.

    The interface shows this BEFORE the destination is chosen: the question
    "have I got the room" has to be answerable while there is still time to
    answer it differently.
    """
    voulus = [c for c in (sources if sources is not None else CLES) if c in CLES]
    detail = []
    for s in SOURCES:
        if s["kind"] == "console":
            detail.append({"cle": s["cle"], "libelle": s["libelle"],
                           "kind": s["kind"], "fichiers": None, "octets": None})
            continue
        items = _fichiers_serveur(lib, cfg, [s["cle"]])
        detail.append({"cle": s["cle"], "libelle": s["libelle"], "kind": s["kind"],
                       "fichiers": len(items),
                       "octets": sum(t for _, _, t in items)})
    total = sum(d["octets"] or 0 for d in detail if d["cle"] in voulus)
    return {"detail": detail, "octets": total, "sources": voulus}


# ------------------------------------------------------------------ la course


def run(job, lib, cfg, sources=None, dest=None, garder=None):
    """Copy the chosen sources into a new batch, then rotate.

    Returns the batch's path, or None. Nothing here raises at the caller: a
    backup that crashes the job thread is a backup nobody is told about.
    """
    voulus = [c for c in (sources if sources is not None
                          else (cfg or {}).get("backup_sources") or ["sauvegardes"])
              if c in CLES]
    if not voulus:
        job.log(messages.CF_RIEN_CHOISI, "warn")
        return None

    racine, erreur = verifier_dest(dest or dest_defaut(cfg), creer=True)
    if erreur:
        job.log(erreur, "warn")
        return None

    garder = int(garder if garder is not None
                 else (cfg or {}).get("backup_keep") or GARDER_DEFAUT)
    garder = max(1, min(99, garder))

    # --- 1. what we are about to write
    items = _fichiers_serveur(lib, cfg, voulus)
    attendu = sum(t for _, _, t in items)
    console = "sauvegardes" in voulus
    dossiers_console = []
    if console:
        from . import device, saves
        if device.state() != "device":
            job.log(messages.CF_CONSOLE_ABSENTE, "warn")
            console = False
        else:
            dossiers_console = saves.find_dirs(cfg)
            if not dossiers_console:
                job.log(messages.SAUVEGARDES_ABSENTES, "warn")
                console = False

    if not items and not console:
        job.log(messages.CF_RIEN_A_COPIER, "warn")
        return None

    # --- 2. the room, checked before anything is written
    libre = _espace(racine)
    job.log(langue.phrase(messages.CF_PREVISION, _human(attendu), _human(libre)))
    if libre is not None and attendu + _MARGE > libre:
        job.log(langue.phrase(messages.CF_PLACE_INSUFFISANTE,
                              _human(attendu), _human(libre)))
        # Making room is what rotation is for — so we try it here rather than
        # give up in front of a disk holding nine old batches.
        _rotation(job, racine, garder, avant=True)
        libre = _espace(racine)
        if libre is not None and attendu + _MARGE > libre:
            job.log(messages.CF_ABANDON_PLACE, "warn")
            return None

    # The name carries the date to the second, and two backups can land in the
    # same one: the scheduler firing while somebody clicks, or simply two
    # clicks. `exist_ok=False` then refused the second and blamed an "unusable
    # destination", which points at the wrong culprit. We suffix rather than
    # overwrite: an existing batch is a backup, and we never write over a
    # backup.
    horodate = PREFIXE + datetime.now().strftime("%Y-%m-%d_%H%M%S")
    lot = racine / horodate
    suffixe = 1
    while lot.exists() and suffixe < 100:
        suffixe += 1
        lot = racine / ("%s-%d" % (horodate, suffixe))
    try:
        lot.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        job.log(langue.phrase(messages.CF_DEST_ILLISIBLE, exc), "warn")
        return None
    job.log(langue.phrase(messages.CF_DEBUT, lot.name, str(racine)))

    # --- 3. the copy
    total = len(items) + len(dossiers_console)
    job.set_total(total)
    faits = copies = 0
    octets = 0
    depart = time.time()
    interrompu = False

    for src, rel, taille in items:
        if not job.checkpoint():
            interrompu = True
            break
        cible = lot / rel
        try:
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(cible))
            copies += 1
            octets += taille
        except OSError as exc:
            job.log(langue.phrase(messages.CF_FICHIER_ECHEC, src.name, exc), "warn")
        faits += 1
        job.tick()
        _detail(job, depart, octets, attendu)

    if console and not interrompu:
        from . import device
        for d in dossiers_console:
            if not job.checkpoint():
                interrompu = True
                break
            job.log(langue.phrase(messages.S_RECUPERATION, d))
            sous = lot / "sauvegardes" / d.strip("/").replace("/", "_")
            sous.mkdir(parents=True, exist_ok=True)
            rc, out, err = device._run(["pull", d, str(sous)], timeout=3600)
            if rc == 0:
                n = 0
                for p in sous.rglob("*"):
                    if p.is_file():
                        n += 1
                        try:
                            octets += p.stat().st_size
                        except OSError:
                            pass
                copies += n
                job.log(langue.phrase(messages.S_SAUVEGARDES, n))
            else:
                job.log(langue.phrase(messages.S_ECHEC,
                                      ((err or out).strip().splitlines() or [""])[-1]))
            job.tick()

    job.set_detail("")

    # --- 4. the manifest: a batch must be readable without Romule
    manifeste = {
        "outil": "romule",
        "date": datetime.now().strftime("%F %T"),
        "sources": voulus,
        "fichiers": copies,
        "octets": octets,
        "complet": not interrompu,
        "ludotheque": str(config.LUDO),
    }
    try:
        (lot / MARQUE).write_text(
            json.dumps(manifeste, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    except OSError as exc:
        job.log(langue.phrase(messages.CF_DEST_ILLISIBLE, exc), "warn")

    if interrompu:
        job.log(langue.phrase(messages.CF_INTERROMPUE, copies, _human(octets)), "warn")
    else:
        job.log(langue.phrase(messages.CF_TERMINEE, copies, _human(octets), lot.name))

    # --- 5. rotation, once the new batch exists and not before
    _rotation(job, racine, garder)
    return str(lot)


def _detail(job, depart, octets, attendu):
    ecoule = max(0.1, time.time() - depart)
    vitesse = octets / ecoule
    reste = max(0, attendu - octets)
    eta = reste / vitesse if vitesse > 0 else 0
    job.set_detail("%s/s · reste %s (~%d min)"
                   % (_human(int(vitesse)), _human(reste), round(eta / 60)))


def _rotation(job, racine, garder, avant=False):
    """Delete the oldest batches past `garder`.

    Only complete batches count towards the quota, and an interrupted one is
    the FIRST to go: keeping a half copy in place of a whole one is the one way
    rotation can make things worse.
    """
    presents = lots(racine)
    if len(presents) <= garder:
        return
    # Oldest last in `lots`; we drop from the end, interrupted ones first.
    surplus = presents[garder:]
    incomplets = [l for l in presents if not l["complet"]]
    a_supprimer = []
    for l in incomplets + surplus:
        if l not in a_supprimer:
            a_supprimer.append(l)
    a_supprimer = a_supprimer[:max(0, len(presents) - garder)]
    for l in a_supprimer:
        try:
            shutil.rmtree(l["chemin"])
            job.log(langue.phrase(messages.CF_ROTATION, l["nom"], garder))
        except OSError as exc:
            job.log(langue.phrase(messages.CF_ROTATION_ECHEC, l["nom"], exc), "warn")
    if avant:
        job.log(messages.CF_ROTATION_PLACE)


def etat(lib, cfg):
    """Everything the settings screen needs, in one answer."""
    choisi = dest_defaut(cfg)
    racine, erreur = (verifier_dest(choisi) if choisi else (None, None))
    return {
        "sources": SOURCES,
        "choix": [c for c in ((cfg or {}).get("backup_sources") or ["sauvegardes"])
                  if c in CLES],
        "dest": choisi,
        "dest_ok": bool(racine),
        "dest_erreur": str(erreur) if erreur else "",
        "libre": _espace(racine) if racine else None,
        "garder": int((cfg or {}).get("backup_keep") or GARDER_DEFAUT),
        "destinations": destinations(cfg),
        "lots": lots(racine) if racine else [],
        "apercu": apercu(lib, cfg),
    }
