"""Orchestrations lancees en tache de fond (import, conversion, transfert)."""

import shutil
import subprocess
import zipfile
from pathlib import Path

from . import (config, convert, device, edenconf, emuready, integrity, nand,
               saves, systems, titleid, trash)


# --------------------------------------------------------------- dossier depot

def scan_import():
    """Fichiers et archives en attente dans _import, avec leur destination."""
    if not config.IMPORT.is_dir():
        return []
    out = []
    for p in sorted(config.IMPORT.rglob("*")):
        # `.DS_Store` et consorts ne sont pas des jeux : les lister ne fait
        # qu'ajouter du bruit et une fausse alerte a chaque rangement.
        if not p.is_file() or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        if ext in config.ARCHIVES:
            out.append({
                "path": str(p), "name": p.name, "size": p.stat().st_size,
                "tid": None, "type": "ARCHIVE", "dest": "sera décompressé",
                "systeme": None, "systeme_nom": "À décompresser",
            })
        elif ext in config.EXTS:
            tid = titleid.from_name(p.name)
            out.append({
                "path": str(p), "name": p.name, "size": p.stat().st_size,
                "tid": tid, "type": titleid.tid_type(tid) if tid else "INCONNU",
                "systeme": "switch", "systeme_nom": systems.SWITCH["name"],
                "dest": _destination_for(tid, p.name),
            })
        else:
            # ROM d'une autre plateforme : l'apercu annoncait « GAMES » pour un
            # fichier .gba, alors que le rangement, lui, le mettait au bon endroit.
            s = systems.system_for_file(p.name)
            if s:
                out.append({
                    "path": str(p), "name": p.name, "size": p.stat().st_size,
                    "tid": None, "type": "ROM",
                    "systeme": s["key"], "systeme_nom": s["name"],
                    "dest": s["folder"],
                })
            else:
                # Extension partagee (.iso : PS2, PSP, Wii, Xbox…) ou inconnue.
                # Ne PAS la lister revenait a la faire disparaitre : elle ne
                # s'affichait nulle part et le rangement l'ignorait en silence.
                cands = [x["name"] for x in systems.liste()
                         if p.suffix.lower() in x["exts"]]
                out.append({
                    "path": str(p), "name": p.name, "size": p.stat().st_size,
                    "tid": None, "type": "AMBIGU", "systeme": None,
                    "systeme_nom": ("Plusieurs plateformes possibles"
                                    if len(cands) > 1 else "Extension inconnue"),
                    "candidats": cands,
                    "dest": "à classer toi-même",
                })
    return out


def _destination_for(tid, filename, files=None, cfg=None):
    """Dossier ou ranger un fichier. Layout 'type' -> GAMES/UPDATE/DLC ;
    layout 'game' -> dossier du jeu de base (ancien comportement)."""
    layout = (cfg or config.load_config()).get("local_layout", "type")
    if layout == "type":
        return config.LAYOUT_FOLDER[titleid.tid_type(tid) if tid else "INCONNU"]
    files = files if files is not None else []
    if tid:
        base = titleid.tid_base(tid)
        for f in files:
            if f["tid"] and titleid.tid_base(f["tid"]) == base:
                return f["dir"]
    return titleid.pretty_name(filename)


# --------------------------------------------------------------- archives

def _extract_one(archive, job):
    """Extrait les jeux ET les archives imbriquees d'une archive vers _import."""
    wanted = config.EXTS | config.ARCHIVES
    ext = archive.suffix.lower()
    n = 0
    if ext == ".zip":
        try:
            with zipfile.ZipFile(archive) as z:
                for m in z.namelist():
                    if Path(m).suffix.lower() in wanted:
                        dest = config.IMPORT / Path(m).name
                        with z.open(m) as src, dest.open("wb") as out:
                            shutil.copyfileobj(src, out)
                        n += 1
        except (zipfile.BadZipFile, OSError) as exc:
            job.log("  Archive illisible : %s" % exc)
            return (False, 0)
        return (True, n)

    # .7z / .rar via un outil externe (7-Zip ou The Unarchiver)
    sevenzip = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
    if not sevenzip and not shutil.which("unar"):
        job.log("  Aucun outil pour cette archive (installe The Unarchiver : brew install unar).")
        return (False, 0)
    tmp = config.IMPORT / ("_x_" + archive.stem)
    tmp.mkdir(exist_ok=True)
    ok = True
    try:
        if sevenzip:
            subprocess.run([sevenzip, "x", "-y", "-o" + str(tmp), str(archive)],
                           capture_output=True, timeout=7200)
        else:
            subprocess.run(["unar", "-quiet", "-force-overwrite",
                            "-output-directory", str(tmp), str(archive)],
                           capture_output=True, timeout=7200)
        for p in tmp.rglob("*"):
            if p.is_file() and p.suffix.lower() in wanted:
                shutil.move(str(p), str(config.IMPORT / p.name))
                n += 1
    except (OSError, subprocess.SubprocessError) as exc:
        job.log("  Extraction impossible : %s" % exc)
        ok = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return (ok, n)


def _extract_archives(job):
    """Decompresse toutes les archives de _import (sous-dossiers et archives
    imbriquees compris), puis met en corbeille celles qui ont reussi."""
    done, total = set(), 0
    for _ in range(6):  # plusieurs passes : une archive peut en contenir d'autres
        archives = [p for p in config.IMPORT.rglob("*")
                    if p.is_file() and p.suffix.lower() in config.ARCHIVES
                    and str(p) not in done]
        if not archives:
            break
        for a in archives:
            done.add(str(a))
            job.log("Decompression de %s..." % a.name)
            ok, n = _extract_one(a, job)
            if not ok:
                continue  # erreur / pas d'outil : on la laisse dans _import
            if n:
                job.log("  %d element(s) extrait(s)." % n)
                trash.move([str(a)], "archive decompressee", job.log)
            else:
                job.log("  Aucun jeu dedans (donnees non installables) -> corbeille.")
                trash.move([str(a)], "archive sans contenu jouable", job.log)
            total += 1
    return total


def _clean_import_dirs():
    """Supprime les sous-dossiers vides de _import apres rangement."""
    dirs = [p for p in config.IMPORT.rglob("*") if p.is_dir()]
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass


# --------------------------------------------------------------- taches de fond

def suggestions_import(cfg=None):
    """Pour chaque fichier que l'extension ne suffit pas a classer, propose une
    plateforme.

    L'extension donne les candidats POSSIBLES (.iso : sept plateformes) ; IGDB
    dit sur lesquelles le jeu est REELLEMENT sorti. L'intersection tranche
    souvent toute seule, et sinon elle reduit la liste a trois choix au lieu de
    sept.
    """
    from . import igdb
    cfg = cfg or config.load_config()
    out = []
    for item in scan_import():
        if item["type"] != "AMBIGU":
            continue
        ext = Path(item["name"]).suffix.lower()
        candidats = [x for x in systems.liste(cfg) if ext in x["exts"]]
        cles = [x["key"] for x in candidats]
        propose = []
        if len(cles) > 1 and igdb.configure(cfg):
            from . import covers
            vues = igdb.plateformes(covers.search_name(item["name"]), cfg)
            propose = [k for k in vues if k in cles]
        out.append({
            "chemin": item["path"], "nom": item["name"], "taille": item["size"],
            "extension": ext,
            "candidats": [{"key": x["key"], "name": x["name"]} for x in candidats],
            "suggestion": propose[0] if propose else "",
            "proposes": propose,
        })
    return out


def classer_import(cfg, job, assignations):
    """Range les fichiers du depot selon le choix de l'utilisateur."""
    n, ranges = 0, []
    for chemin, cle in (assignations or {}).items():
        src = Path(chemin)
        if not src.is_file() or str(src.parent) != str(config.IMPORT):
            job.log("Ignore (hors du depot) : %s" % src.name, "warn")
            continue
        try:
            dest_dir = systems.local_dir(cle, cfg)
        except Exception:
            job.log("Plateforme inconnue pour %s : %s" % (src.name, cle), "warn")
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            job.log("Deja present : %s" % src.name, "warn")
            continue
        try:
            shutil.move(str(src), str(dest))
            job.log("Range : %s -> %s/" % (src.name, systems.get_cfg(cle, cfg)["folder"]))
            ranges.append(str(dest))
            n += 1
        except OSError as exc:
            job.log("Impossible de ranger %s : %s" % (src.name, exc), "error")
    job.log("%d fichier(s) classe(s) a la main." % n)
    _fiches_des_nouveaux(ranges, cfg, job)
    return n


def _fiches_des_nouveaux(chemins, cfg, job):
    """Titre, resume et jaquette des jeux qui viennent d'etre ranges."""
    from . import covers, meta
    nouveaux = [Path(c) for c in (chemins or [])]
    if not nouveaux:
        return
    job.log("Recherche des fiches de %d nouveau(x) jeu(x)…" % len(nouveaux))
    faits = 0
    for p in nouveaux:
        if not job.checkpoint():
            job.log("Fiches interrompues (%d/%d)." % (faits, len(nouveaux)), "warn")
            return
        job.set_detail(p.name[:48])
        tid = titleid.from_name(p.name)
        try:
            if tid:
                meta.fetch(titleid.tid_base(tid), cfg)
            else:
                meta.fiche_nom(p.name, cfg)
            # la jaquette se telecharge et se met en cache au passage
            covers.fetch(titleid.tid_base(tid) if tid else "", p.name, cfg)
            faits += 1
        except Exception as exc:
            job.log("Fiche indisponible pour %s : %s" % (p.name[:40], exc), "warn")
    job.set_detail("")
    job.log("%d fiche(s) recuperee(s) sur %d." % (faits, len(nouveaux)))


def _expliquer_ambigus(items, job):
    """Dire pourquoi un fichier reste dans le depot.

    Le laisser dormir sans explication est la pire des reponses : l'utilisateur
    croit que l'import a echoue alors que l'outil ne peut simplement pas
    deviner la plateforme.
    """
    for item in items:
        cands = item.get("candidats") or []
        ext = Path(item["name"]).suffix or "(sans extension)"
        if len(cands) > 1:
            job.log("%s reste dans le dépôt : l'extension %s est partagée par %s. "
                    "Range-le dans le dossier voulu."
                    % (item["name"], ext, ", ".join(cands[:5])), "warn")
        else:
            job.log("%s reste dans le dépôt : aucune plateforme ne reconnaît %s."
                    % (item["name"], ext), "warn")


def import_files(lib, cfg, job, convert_after=True):
    _extract_archives(job)
    # On ne range ici QUE les fichiers Switch. Une archive non extraite reste
    # dans _import ; une ROM d'une autre plateforme est traitee plus bas, par la
    # boucle qui connait son dossier.
    #
    # Sans ce filtre, cette boucle prenait TOUT : un fichier sans title ID
    # tombait dans la branche « INCONNU » de `_destination_for`, c'est-a-dire
    # GAMES/. Une ROM 3DS ou GBA atterrissait donc parmi les jeux Switch, et la
    # boucle suivante ne trouvait plus rien a ranger.
    pending = [i for i in scan_import()
               if i["type"] not in ("ARCHIVE", "AMBIGU")
               and i.get("systeme") in (None, "switch")]
    # Pas de retour anticipe sur `pending` seul : il ne contient que les
    # fichiers Switch. Les ROMs des autres plateformes sont rangees plus bas,
    # et sortir ici les laissait indefiniment dans _import.
    roms = [i for i in scan_import()
            if i["type"] not in ("ARCHIVE", "AMBIGU")
            and i.get("systeme") not in (None, "switch")]
    ambigus = [i for i in scan_import() if i["type"] == "AMBIGU"]
    if not pending and not roms:
        if ambigus:
            _expliquer_ambigus(ambigus, job)
        else:
            job.log("Aucun jeu a ranger dans _import "
                    "(archives non extraites eventuellement laissees).")
        return
    # Recalcule les destinations en tenant compte des jeux deja presents.
    moved = []
    for item in pending:
        src = Path(item["path"])
        dest_sub = _destination_for(item["tid"], src.name, lib.files, cfg)
        outdir = config.LUDO / dest_sub
        outdir.mkdir(parents=True, exist_ok=True)
        dest = outdir / src.name
        if dest.exists():
            job.log("Deja present, ignore : %s" % src.name)
            continue
        try:
            shutil.move(str(src), str(dest))
            job.log("Range : %s -> %s/" % (src.name, dest_sub))
            moved.append(str(dest))
        except OSError as exc:
            job.log("Impossible de ranger %s : %s" % (src.name, exc))

    # ROMs d'autres consoles presentes dans _import : chacune part dans son dossier
    for s in systems.liste(cfg):          # plateformes ajoutees a la main comprises
        if s["engine"] == "switch":
            continue
        hits = [p for p in config.IMPORT.rglob("*")
                if p.is_file() and p.suffix.lower() in s["exts"]
                and systems.system_for_file(p.name)  # extension non ambigue seulement
                and systems.system_for_file(p.name)["key"] == s["key"]]
        if not hits:
            continue
        outdir = systems.local_dir(s["key"], cfg)
        outdir.mkdir(parents=True, exist_ok=True)
        for p in hits:
            dest = outdir / p.name
            if dest.exists():
                continue
            try:
                shutil.move(str(p), str(dest))
                job.log("Range : %s -> %s/" % (p.name, s["folder"]))
                moved.append(str(dest))
            except OSError as exc:
                job.log("Impossible de ranger %s : %s" % (p.name, exc))

    # Ce qui reste et qu'on n'a pas su placer : le dire, plutot que de le
    # laisser dormir dans _import sans explication. Une extension comme .iso est
    # revendiquee par sept plateformes — l'outil ne peut pas deviner.
    _expliquer_ambigus([i for i in scan_import() if i["type"] == "AMBIGU"], job)

    _clean_import_dirs()
    lib.scan(log=job.log)
    # Un jeu qui vient d'arriver n'a ni titre ni jaquette : les chercher tout de
    # suite evite d'avoir une carte vide jusqu'a la prochaine synchronisation.
    # On ne s'occupe QUE des nouveaux venus : relire les 120 autres a chaque
    # import serait absurde.
    _fiches_des_nouveaux(moved, cfg, job)
    _auto_nand(lib, cfg, job, moved)
    todo = [p for p in moved if Path(p).suffix.lower() in config.COMPRESSED]
    if convert_after and todo:
        job.log("Conversion des %d fichier(s) importe(s)..." % len(todo))
        convert.run(todo, cfg["jobs"], convert.default_threads(),
                    True, lib.maxkey, job)
    else:
        job.log("Import termine (%d fichier(s))." % len(moved))
    lib.scan(log=job.log)


def convert_files(lib, cfg, job, paths):
    convert.run(paths, cfg["jobs"], convert.default_threads(),
                True, lib.maxkey, job)
    lib.scan(log=job.log)


def _types_connus(lib):
    """Type reel de chaque fichier, tel que la bibliotheque l'a determine."""
    return {f["path"]: f["type"] for f in lib.files}


def push_files(lib, cfg, job, paths):
    device.push(paths, cfg["device_dir"], job,
                cfg.get("verify_mode", "size"),
                cfg.get("push_layout", "type"),
                cfg.get("incremental", True),
                _types_connus(lib))


def remove_from_device(lib, cfg, job, paths):
    device.remove(paths, job)


def organize_device(lib, cfg, job):
    import os
    types = {os.path.basename(f["path"]): f["type"] for f in lib.files}
    device.organize(cfg["device_dir"], job, types)


# --------------------------------------------------------------- multi-systemes

def push_system(lib, cfg, job, sys_key, paths):
    """Envoie des ROMs d'un systeme non-Switch vers son dossier sur la console."""
    target = systems.device_dir(sys_key, cfg)
    device.push_generic(paths, target, job,
                        cfg.get("verify_mode", "size") != "none",
                        cfg.get("incremental", True))


def import_system_files(lib, cfg, job, sys_key):
    """Range les ROMs de _import appartenant a un systeme donne."""
    s = systems.get(sys_key)
    dest_dir = systems.local_dir(sys_key)
    dest_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for p in sorted(config.IMPORT.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in s["exts"]:
            continue
        dest = dest_dir / p.name
        if dest.exists():
            job.log("Deja present, ignore : %s" % p.name)
            continue
        try:
            shutil.move(str(p), str(dest))
            job.log("Range : %s -> %s/" % (p.name, s["folder"]))
            moved += 1
        except OSError as exc:
            job.log("Impossible de ranger %s : %s" % (p.name, exc))
    _clean_import_dirs()
    job.log("%d fichier(s) range(s) dans %s." % (moved, s["name"]))


# --------------------------------------------------------------- integrite / saves

def verify_library(lib, cfg, job, deep=False, sys_key=None, budget_go=None):
    """Verifie l'integrite des fichiers (empreintes + conteneurs Switch).

    `budget_go` limite le passage a une tranche : la verification devient une
    habitude de quelques minutes plutot qu'une operation qu'on ne lance jamais.
    """
    if sys_key and systems.get(sys_key)["engine"] != "switch":
        files = systems.scan_local(sys_key)
    else:
        lib.scan(log=job.log)
        files = lib.files
    if not files:
        job.log("Aucun fichier a verifier.")
        return
    job.log("Verification de %d fichier(s)%s…" % (len(files), " (approfondie)" if deep else ""))
    integrity.check(files, job, deep,
                    budget_octets=int(budget_go * 2 ** 30) if budget_go else None)


def backup_saves(lib, cfg, job):
    saves.backup(job, cfg)


def sync_meta(lib, cfg, job):
    """Telecharge les fiches de jeu manquantes (titre traduit, resume)."""
    from . import meta
    # Le title ID du JEU, pas celui du fichier : un jeu dont on ne possede que
    # la mise a jour, ou dont la base est un pack .xci non typé, n'a aucun
    # fichier « BASE » — sa fiche n'etait donc jamais demandee.
    tids = [titleid.tid_base(f["tid"]) for f in lib.files if f["tid"]]
    a_faire = meta.manquants(tids, cfg)
    if not a_faire:
        job.log("Fiches Switch : toutes deja en cache.")
    job.set_total(len(a_faire))
    if a_faire:
        job.log("Recuperation de %d fiche(s) Switch en %s..."
                % (len(a_faire), cfg.get("meta_lang", "fr")))
    ok = 0
    for tid in a_faire:
        if not job.checkpoint():
            job.log("Interrompu (%d/%d)." % (ok, len(a_faire)))
            return
        d = meta.fetch(tid, cfg)
        if d and d.get("name"):
            ok += 1
            job.set_detail(d["name"][:48])
        job.tick()
    if a_faire:
        job.set_detail("")
        job.log("%d fiche(s) Switch recuperee(s) sur %d." % (ok, len(a_faire)))

    # Les autres plateformes n'ont pas de title ID : leur titre officiel vient
    # de SteamGridDB, la meme source que les jaquettes.
    from . import igdb
    if not (cfg.get("steamgriddb_key") or "").strip() and not igdb.configure(cfg):
        job.log("Sans cle SteamGridDB ni identifiants IGDB, les jeux des autres "
                "plateformes gardent le nom de leur fichier.", "warn")
        return
    # Les jeux des autres plateformes vivent souvent UNIQUEMENT sur la console :
    # ne regarder que le serveur laissait leur titre introuvable.
    noms = []
    for sys in systems.tout(cfg):
        noms += [f["file"] for f in sys["games"]]
        noms += [x["nom"] for x in sys["console"]]
    # Une fiche deja en cache mais SANS resume n'est pas une fiche faite : les
    # premieres ont ete creees avant qu'IGDB ne soit configure, et les
    # considerer comme terminees condamnait ces jeux a n'avoir jamais de
    # description.
    langue = (cfg.get("meta_lang") or "fr").strip().lower()
    avec_resume = igdb.configure(cfg)

    def a_completer(nom):
        f = meta.fiche_nom(nom, cfg, reseau=False)
        if not f:
            return True
        if avec_resume and not f.get("resume"):
            return True
        # Un resume anglais alors que l'utilisateur lit le francais : la fiche
        # est incomplete, meme si elle a l'air remplie.
        return (langue not in ("", "en")
                and bool(f.get("resume"))
                and not str(f.get("source_resume", "")).endswith(langue))

    tous = list(dict.fromkeys(noms))
    restants = [n for n in tous if a_completer(n)]
    if not restants:
        job.log("Fiches des autres plateformes : les %d sont completes." % len(tous))
        return
    job.set_total(len(restants))
    job.log("%d jeu(x) sur les autres plateformes : recherche du titre%s…"
            % (len(restants), " et du résumé" if avec_resume else ""))
    trouves = resumes = 0
    for n in restants:
        if not job.checkpoint():
            job.log("Interrompu : %d fiche(s) traitee(s) sur %d."
                    % (trouves, len(restants)), "warn")
            return
        d = meta.fiche_nom(n, cfg)
        if d and d.get("nom"):
            trouves += 1
            resumes += 1 if d.get("resume") else 0
            job.set_detail(d["nom"][:48])
        else:
            job.log("Aucune fiche trouvee : %s" % n[:64], "warn")
        job.tick()
    job.set_detail("")
    dans_la_langue = sum(
        1 for n in restants
        if str((meta.fiche_nom(n, cfg, reseau=False) or {}).get("source_resume", ""))
        .endswith(langue))
    job.log("%d titre(s) sur %d, dont %d avec un resume (%d en %s)."
            % (trouves, len(restants), resumes, dans_la_langue, langue))
    if avec_resume and resumes < trouves:
        job.log("%d jeu(x) sans resume : IGDB ne les connait pas sous ce nom."
                % (trouves - resumes), "warn")


def analyser_console(lib, cfg, job):
    """Passe en revue toutes les plateformes de la console, et le dit.

    Une detection silencieuse laisse l'utilisateur sans moyen de comprendre
    pourquoi telle plateforme reste vide. Ici chaque etape est journalisee :
    dossier examine, extensions attendues, verdict.
    """
    racine = systems.roms_root(cfg)
    if not racine:
        job.log("Aucune racine de ROMs definie : renseigne-la d'abord.", "error")
        return
    if device.state() != "device":
        job.log("Console non connectee.", "error")
        return

    plateformes = systems.liste(cfg)
    job.set_total(len(plateformes))
    job.log("Analyse de %s (%d plateforme(s) connues)." % (racine, len(plateformes)))
    trouvees, total, vides = 0, 0, []
    for s in plateformes:
        if not job.checkpoint():
            job.log("Analyse interrompue.", "warn")
            return
        dossier = systems.device_dir(s["key"], cfg)
        job.set_detail(s["name"])
        if not dossier:
            job.tick()
            continue
        fichiers = device.find_games(dossier, s["exts"])
        if fichiers:
            trouvees += 1
            total += len(fichiers)
            job.log("  %-20s %4d jeu(x)  %s" % (s["name"], len(fichiers), dossier))
        else:
            vides.append(s["name"])
        job.tick()

    job.set_detail("")
    job.log("%d plateforme(s) avec des jeux, %d jeu(x) au total." % (trouvees, total))
    if vides:
        job.log("Sans jeu (dossier absent ou vide) : %s" % ", ".join(vides[:12])
                + (" …" if len(vides) > 12 else ""), "warn")
        job.log("Si l'une d'elles existe sous un autre nom, ouvre sa fiche dans "
                "les Reglages et indique son dossier.", "warn")


def apply_eden_config(lib, cfg, job, changements, tid=None):
    """Ecrit des reglages dans la configuration d'Eden (globale ou d'un jeu)."""
    edenconf.write_config(changements, job, tid or None)


def apply_eden_profile(lib, cfg, job, nom, tid=None):
    """Applique un profil enregistre a la config globale ou a un jeu."""
    prof = edenconf.profile_read(nom)
    if not prof:
        job.log("Profil introuvable : %s" % nom)
        return
    job.log("Application du profil « %s »…" % nom)
    edenconf.write_config(prof.get("valeurs", {}), job, tid or None)


def emuready_sync(lib, cfg, job, force=False):
    """Recupere l'etat de compatibilite des jeux depuis EmuReady."""
    bases = [f for f in lib.files if f["type"] == "BASE" and f["tid"]]
    job.log("Consultation d'EmuReady pour %d jeu(x)…" % len(bases))
    emuready.sync(bases, cfg, job, force)


def emuready_apply(lib, cfg, job, listing_id, tid):
    """Applique a un jeu la configuration recommandee par la communaute."""
    try:
        contenu = emuready.config_of(listing_id)
    except Exception as exc:
        job.log("Configuration indisponible : %s" % exc)
        return
    if not contenu.strip():
        job.log("Ce rapport ne contient aucune configuration.")
        return
    job.log("Configuration recuperee (%d octets)." % len(contenu))
    edenconf.write_raw(contenu, job, tid)


def _auto_nand(lib, cfg, job, chemins):
    """Active dans Eden les MAJ/DLC qui viennent d'arriver, si l'option est mise.

    Sans cela un fichier importe reste inerte : present sur le disque mais
    invisible du jeu tant qu'il n'est pas inscrit dans la memoire de l'emulateur.
    """
    if not cfg.get("auto_nand"):
        return
    if device.connection()["kind"] is None:
        job.log("Activation automatique : console non connectee, reporte.", "warn")
        return
    interesse = {str(Path(c)) for c in chemins}
    cibles = [f["path"] for f in lib.files
              if f["path"] in interesse and f["type"] in ("UPDATE", "DLC")
              and f["ext"] in ("nsp", "xci")]
    if not cibles:
        return
    etats = {e["path"]: e for e in nand.status(cibles)}
    restants = [c for c in cibles if etats.get(c, {}).get("etat") in ("absent", "partiel")]
    if not restants:
        return
    job.log("Activation automatique de %d mise(s) a jour / DLC dans l'emulateur."
            % len(restants))
    nand.install(restants, job)


def deploy_games(lib, cfg, job, a_envoyer, a_activer, configs=None):
    """Rend des jeux jouables sur la console, en une seule operation.

    Trois mecanismes distincts d'Eden, un seul geste pour l'utilisateur :
      1. copier les fichiers jouables (.nsp/.xci) dans le dossier des jeux,
      2. installer mises a jour et DLC dans la memoire interne de l'emulateur,
      3. poser les reglages recommandes par la communaute (optionnel).
    """
    configs = configs or []
    etapes = 2 + (1 if configs else 0)

    if a_envoyer:
        job.log("Etape 1/%d — copie de %d fichier(s) vers la console." % (etapes, len(a_envoyer)))
        device.push(a_envoyer, cfg["device_dir"], job,
                    cfg.get("verify_mode", "size"), cfg.get("push_layout", "type"),
                    cfg.get("incremental", True), _types_connus(lib))
    else:
        job.log("Etape 1/%d — aucun fichier a copier." % etapes)
    if not job.checkpoint():
        return

    if a_activer:
        job.log("Etape 2/%d — activation de %d mise(s) a jour / DLC dans l'emulateur."
                % (etapes, len(a_activer)))
        nand.install(a_activer, job)
    else:
        job.log("Etape 2/%d — rien a activer." % etapes)
    if not job.checkpoint():
        return

    poses = 0
    if configs:
        job.log("Etape 3/%d — reglages recommandes pour %d jeu(x)." % (etapes, len(configs)))
        for c in configs:
            if not job.checkpoint():
                return
            tid = (c.get("tid") or "").upper()
            try:
                contenu = emuready.config_of(c.get("listing_id"))
            except Exception as exc:
                job.log("  %s : configuration indisponible (%s)" % (tid, exc), "warn")
                continue
            if not contenu.strip():
                job.log("  %s : rapport sans configuration." % tid, "warn")
            elif edenconf.write_raw(contenu, job, tid):
                poses += 1

    if configs and poses < len(configs):
        job.log("Termine, mais %d reglage(s) sur %d n'ont pas pu etre appliques."
                % (len(configs) - poses, len(configs)), "warn")
    else:
        job.log("Console a jour.", "ok")


def restore_eden_config(lib, cfg, job, tid, fichier):
    """Remet une configuration de jeu telle qu'elle etait avant modification."""
    edenconf.restore_backup(tid, fichier, job)


def install_nand(lib, cfg, job, paths):
    """Installe des MAJ/DLC dans la NAND d'Eden (sinon ils restent inactifs)."""
    nand.install(paths, job)


def _clean_empty_dirs():
    keep = set(config.LAYOUT_FOLDER.values())
    dirs = [p for p in config.LUDO.rglob("*") if p.is_dir()]
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        rel = d.relative_to(config.LUDO)
        if rel.parts[0] in config.IGNORE_DIRS or d.name in keep:
            continue
        try:
            d.rmdir()  # ne reussit que si vide
        except OSError:
            pass


def reorganize_local(lib, cfg, job):
    """Range toute la bibliotheque locale : chaque fichier va dans GAMES/UPDATE/DLC
    selon son type, meme s'il etait dans un dossier de jeu a la racine. Les
    dossiers devenus vides sont supprimes."""
    lib.scan(log=job.log)
    job.set_total(len(lib.files))
    moved = 0
    for f in list(lib.files):
        folder = config.LAYOUT_FOLDER.get(f["type"], "GAMES")
        src = Path(f["path"])
        dst = config.LUDO / folder / src.name
        if src.resolve() == dst.resolve():
            job.tick()
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dst))
            job.log("Range : %s -> %s/" % (src.name, folder))
            moved += 1
        except (OSError, shutil.Error) as exc:
            job.log("Echec (%s) : %s" % (src.name, exc))
        job.tick()
    _clean_empty_dirs()
    job.log("%d fichier(s) range(s) en GAMES / UPDATE / DLC." % moved)
    lib.scan(log=job.log)


def import_from_device(lib, cfg, job, remote_paths, convert_after=True):
    """Recupere des jeux depuis la console, les range et (option) les convertit."""
    got = device.pull(remote_paths, job)
    if not got:
        job.log("Rien de recupere depuis la console.")
        return
    import_files(lib, cfg, job, convert_after)
