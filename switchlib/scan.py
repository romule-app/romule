"""Inventaire de la ludotheque, classement et diagnostics."""

import os
import time
from pathlib import Path

from . import config, nsztool, titleid


def target_path(f):
    """Chemin decompresse attendu pour un fichier compresse, sinon None."""
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

    def scan(self, deep=True, log=lambda m, n=None: None):
        files = []
        deep = deep and nsztool.available()
        for p in sorted(config.ROOT.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in config.EXTS:
                continue
            rel = p.relative_to(config.ROOT)
            if rel.parts and rel.parts[0] in config.IGNORE_DIRS:
                continue
            tid = titleid.from_name(p.name)
            ver = titleid.version_from_name(p.name)
            if not tid and deep:
                log("Lecture du conteneur : %s" % p.name)
                tid = nsztool.container_tid(p)
            elif deep and tid and titleid.tid_type(tid) == "BASE" and (
                    ver or (self.versions
                            and titleid.tid_patch(tid) not in self.versions)):
                # Deux signaux trahissent un nom de fichier menteur :
                #   - une base annoncee avec une version (une base est toujours
                #     en v0) : c'est une mise a jour mal nommee ;
                #   - un title ID que titledb ne connait pas : une coquille dans
                #     le nom suffit a fabriquer un identifiant valide en apparence
                #     mais inexistant, et le fichier forme alors un faux jeu a part.
                # Dans les deux cas on tranche sur le contenu.
                reel = nsztool.container_tid(p)
                if reel and reel != tid:
                    log("Nom trompeur : %s annonce %s, contient %s"
                        % (p.name, tid, reel), "warn")
                    tid = reel
            files.append({
                "path": str(p),
                "rel": str(rel),
                "dir": str(p.parent.relative_to(config.ROOT)),
                "name": titleid.pretty_name(p.name),
                "ext": p.suffix.lower().lstrip("."),
                "tid": tid,
                "type": titleid.tid_type(tid) if tid else "INCONNU",
                "version": titleid.version_from_name(p.name),
                "size": p.stat().st_size,
            })
        self.files = files
        self.scanned_at = time.time()
        self.maxkey = nsztool.max_master_key(self.keyfile)
        return files

    # ------------------------------------------------------------ diagnostics

    def enrich(self):
        """Ajoute les drapeaux : converti, orphelin, version obsolete, patch/DLC."""
        from . import device  # tardif : device n'est pas requis par la CLI hors console
        files = self.files
        vdb = self.versions

        bases = {f["tid"] for f in files if f["type"] == "BASE" and f["tid"]}
        live = [f for f in files if not _is_converted(f)]
        have = {f["tid"] for f in live if f["tid"]}

        owned = {}
        for f in live:
            if f["tid"] and f["version"] is not None:
                owned[f["tid"]] = max(owned.get(f["tid"], -1), f["version"])

        # Index DLC connus, construit UNE fois (evite un balayage de titledb par jeu).
        dlc_index = {}
        for k in vdb:
            dlc_index.setdefault(k[:13], []).append(k)

        for f in files:
            flags = []
            f["converted"] = _is_converted(f)
            f["needs_convert"] = bool(target_path(f)) and not f["converted"]
            f["missing_dlc"] = []
            # Un telechargement interrompu produit une archive plus courte que ce
            # qu'elle annonce. Le signaler ici evite de le decouvrir a l'envoi,
            # ou pire sur la console avec un jeu qui ne demarre pas.
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
                    # Ces libelles s'affichent tels quels : ils doivent dire ce
                    # que l'utilisateur doit FAIRE, pas reciter un numero de
                    # version qui ne lui evoque rien.
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
        """Ce qu'il reste a recuperer : patches perimes/absents, DLC manquants."""
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
        """Fichiers UPDATE/DLC decompresses a installer dans la NAND d'Eden."""
        return sorted(
            (f for f in self.files
             if f["type"] in ("UPDATE", "DLC") and f["ext"] in ("nsp", "xci")),
            key=lambda x: x["rel"])

    def stats(self):
        f = self.files
        age = None
        if self.versions_at:
            h = (time.time() - self.versions_at) / 3600
            age = "il y a %d h" % h if h >= 1 else "a l'instant"
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
            "versions_age": age,
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
    lines = ["# Genere le %s par switchlib" % datetime.now().strftime("%F %T"),
             "# Eden : File > Install Files to NAND", ""]
    lines += ["[%s] %s" % (f["type"], f["rel"]) for f in rows]
    config.NAND_LIST.write_text("\n".join(lines) + "\n")
    return len(rows)
