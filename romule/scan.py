"""Inventaire de la ludotheque, classement et diagnostics."""

import os
import time

from . import config, nsztool, titleid


def target_path(f):
    """Expected decompressed path for a compressed file, otherwise None."""
    if f["ext"] == "nsz":
        return f["path"][:-4] + ".nsp"
    if f["ext"] == "xcz":
        return f["path"][:-4] + ".xci"
    return None


def _is_converted(f):
    tgt = target_path(f)
    return bool(tgt and os.path.exists(tgt))


class Library:
    def __init__(self):
        self.files = []
        self.versions = {}
        self.versions_at = None
        self.maxkey = 0
        self.scanned_at = None
        self.keyfile = config.CLES

    # ------------------------------------------------------------ inventaire

    def _parcourir(self):
        """The files we keep, as sorted ABSOLUTE paths — without `pathlib`.

        This loop is the cost of every render: the inventory is not stored
        anywhere, it is REBUILT on each `/api/scan`. A profile over 20 000
        titles (39 525 files) gave 1 887 ms, of which:

            relative_to       744 ms   39 %
            sorted(Path)      362 ms   19 %   — 504 724 comparaisons
            stat              138 ms          — appele DEUX fois par fichier

        JSON serialisation did not even show up. Which is why a database would
        have changed nothing here: the time does not go into reading data, it
        goes into building `Path` objects and throwing them away. So we keep
        strings, and `os.scandir` — which gives the type and the size without a
        second system call.

        `os.walk` prunes ignored folders IN PLACE, which avoids descending into
        `_corbeille/` only to reject each file one by one. Pruning applies at
        the root only, as before: `rel.parts[0]` looked at the first segment
        and nothing else.
        """
        base = str(config.LUDO)
        coupe = len(base) + 1
        trouves = []
        for dossier, sous, fichiers in os.walk(base):
            if dossier == base:
                sous[:] = [d for d in sous if d not in config.IGNORE_DIRS]
            for nom in fichiers:
                ext = os.path.splitext(nom)[1].lower()
                if ext not in config.EXTS:
                    continue
                # The extension travels with the path: recomputing it below
                # would mean a second `splitext` per file, for a result we
                # already have.
                trouves.append((os.path.join(dossier, nom), ext))
        # `normcase` reproduces the order of `sorted(rglob("*"))` exactly:
        # `PurePath.__lt__` compares `_str_normcase`, that is, the whole string,
        # lowercased on Windows and unchanged elsewhere.
        trouves.sort(key=lambda c: os.path.normcase(c[0]))
        return trouves, coupe

    def scan(self, deep=True, log=lambda m, n=None: None):
        files = []
        deep = deep and nsztool.available()
        trouves, coupe = self._parcourir()
        for chemin, ext in trouves:
            nom = os.path.basename(chemin)
            rel = chemin[coupe:]
            tid = titleid.from_name(nom)
            ver = titleid.version_from_name(nom)
            if not tid and deep:
                log("Lecture du conteneur : %s" % nom)
                tid = nsztool.container_tid(chemin)
            elif deep and tid and titleid.tid_type(tid) == "BASE" and (
                    ver or (self.versions
                            and titleid.tid_patch(tid) not in self.versions)):
                # Two signals give away a lying file name:
                #   - a base announced with a version (a base is always v0):
                #     that is a mis-named update;
                #   - a title ID titledb does not know: one typo in the name is
                #     enough to forge an identifier that looks valid but does
                #     not exist, and the file then forms a phantom game of its
                #     own.
                # In both cases we decide on the contents.
                reel = nsztool.container_tid(chemin)
                if reel and reel != tid:
                    log("Nom trompeur : %s annonce %s, contient %s"
                        % (nom, tid, reel), "warn")
                    tid = reel
            # `os.path.dirname(rel)` returns "" at the root where
            # `Path.parent.relative_to` returned ".". The difference is visible
            # in the interface: it is the folder shown under each card.
            dossier_rel = os.path.dirname(rel) or "."
            try:
                taille = os.stat(chemin).st_size
            except OSError:
                # A file that vanishes between the walk and the read is not a
                # fault: a transfer may finish during the inventory. We skip it
                # rather than failing the whole thing.
                continue
            files.append({
                "path": chemin,
                "rel": rel,
                "dir": dossier_rel,
                "name": titleid.pretty_name(nom),
                "ext": ext.lstrip("."),
                "tid": tid,
                "type": titleid.tid_type(tid) if tid else "INCONNU",
                "version": ver,
                "size": taille,
            })
        self.files = files
        self.scanned_at = time.time()
        self.maxkey = nsztool.max_master_key(self.keyfile)
        return files

    # ------------------------------------------------------------ diagnostics

    def enrich(self):
        """Add the flags: converted, orphan, outdated version, patch/DLC."""
        from . import device  # late: device is not needed by the CLI off-console
        files = self.files
        vdb = self.versions

        bases = {f["tid"] for f in files if f["type"] == "BASE" and f["tid"]}
        live = [f for f in files if not _is_converted(f)]
        have = {f["tid"] for f in live if f["tid"]}

        owned = {}
        for f in live:
            if f["tid"] and f["version"] is not None:
                owned[f["tid"]] = max(owned.get(f["tid"], -1), f["version"])

        # Index of known DLC, built ONCE (avoids scanning titledb per game).
        dlc_index = {}
        for k in vdb:
            dlc_index.setdefault(k[:13], []).append(k)

        for f in files:
            flags = []
            f["converted"] = _is_converted(f)
            f["needs_convert"] = bool(target_path(f)) and not f["converted"]
            f["missing_dlc"] = []
            # An interrupted download produces an archive shorter than it
            # claims. Flagging it here avoids finding out at push time, or
            # worse on the console with a game that will not start.
            f["broken"] = device.integrity(f["path"])
            if f["broken"]:
                flags.append(("broken", "fichier incomplet"))

            if f["converted"]:
                flags.append(("done", "deja converti"))
            if f["type"] in ("UPDATE", "DLC") and f["tid"] \
                    and titleid.tid_base(f["tid"]) not in bases:
                flags.append(("orphan", "jeu de base absent"))
            if f["tid"] and f["version"] is not None \
                    and owned.get(f["tid"], -1) > f["version"]:
                flags.append(("old", "version plus recente presente"))

            if f["type"] == "BASE" and f["tid"] and vdb:
                pid = titleid.tid_patch(f["tid"])
                latest, mine = vdb.get(pid), owned.get(pid)
                if latest:
                    # These labels are shown as-is: they must say what the
                    # user should DO, not recite a version number that means
                    # nothing to them.
                    if mine is None:
                        flags.append(("nopatch",
                                      "Une mise à jour existe, tu ne l'as pas"))
                    elif mine < latest:
                        flags.append(("outdated",
                                      "Une mise à jour plus récente existe"))
                miss = [d for d in dlc_index.get(titleid.dlc_prefix(f["tid"]), [])
                        if d not in have]
                f["missing_dlc"] = miss
                if miss:
                    flags.append(("nodlc", "%d DLC existe(nt), tu ne les as pas"
                                  % len(miss)))

            f["flags"] = flags
        return files

    # ------------------------------------------------------------ rapports

    def shopping_list(self):
        """What is left to fetch: stale or missing patches, missing DLC."""
        vdb = self.versions
        live = [f for f in self.files if not _is_converted(f)]
        owned = {}
        for f in live:
            if f["tid"] and f["version"] is not None:
                owned[f["tid"]] = max(owned.get(f["tid"], -1), f["version"])

        out = []
        bases = sorted((x for x in self.files if x["type"] == "BASE" and x["tid"]),
                       key=lambda x: x["name"])
        for f in bases:
            items = []
            pid = titleid.tid_patch(f["tid"])
            latest, mine = vdb.get(pid), owned.get(pid)
            if latest and (mine is None or mine < latest):
                items.append({"kind": "patch", "tid": pid, "want": latest, "have": mine})
            for d in f.get("missing_dlc", []):
                items.append({"kind": "DLC", "tid": d.upper(),
                              "want": vdb.get(d, 0), "have": None})
            if items:
                out.append({"game": f["name"], "items": items})
        return out

    def nand_rows(self):
        """Decompressed UPDATE/DLC files to install into Eden's NAND."""
        return sorted(
            (f for f in self.files
             if f["type"] in ("UPDATE", "DLC") and f["ext"] in ("nsp", "xci")),
            key=lambda x: x["rel"])

    def stats(self):
        f = self.files
        # An age in hours, not a sentence: the sentence is translated on the
        # interface side. Sent ready-made, it stayed French in an English
        # interface, and nobody could translate it.
        heures = None
        if self.versions_at:
            heures = int((time.time() - self.versions_at) / 3600)
        return {
            "total": len(f),
            "base": sum(1 for x in f if x["type"] == "BASE"),
            "update": sum(1 for x in f if x["type"] == "UPDATE"),
            "dlc": sum(1 for x in f if x["type"] == "DLC"),
            "unknown": sum(1 for x in f if x["type"] == "INCONNU"),
            "to_convert": sum(1 for x in f if x.get("needs_convert")),
            "cleanable": sum(1 for x in f
                             if any(g[0] in ("orphan", "old", "done")
                                    for g in x.get("flags", []))),
            "outdated": sum(1 for x in f
                            if any(g[0] in ("outdated", "nopatch")
                                   for g in x.get("flags", []))),
            "missing_dlc": sum(len(x.get("missing_dlc", [])) for x in f),
            "bytes": sum(x["size"] for x in f),
            "maxkey": self.maxkey,
            "versions_h": heures,
        }


def shopping_text(rows):
    from datetime import datetime
    if not rows:
        return "Rien a recuperer : tout est a jour."
    lines = ["# A recuperer — genere le %s" % datetime.now().strftime("%F %T"), ""]
    for r in rows:
        lines.append(r["game"])
        for it in r["items"]:
            have = "tu as v%d" % it["have"] if it["have"] is not None else "absent"
            lines.append("    %-6s %s   v%-8d (%s)"
                         % (it["kind"], it["tid"].upper(), it["want"], have))
        lines.append("")
    return "\n".join(lines)


def write_nand_list(rows):
    from datetime import datetime
    lines = ["# Genere le %s par romule" % datetime.now().strftime("%F %T"),
             "# Eden : File > Install Files to NAND", ""]
    lines += ["[%s] %s" % (f["type"], f["rel"]) for f in rows]
    config.NAND_LIST.write_text("\n".join(lines) + "\n")
    return len(rows)
