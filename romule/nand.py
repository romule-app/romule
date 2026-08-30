"""Installation de mises a jour et DLC dans la NAND virtuelle d'Eden.

Un `.nsp` est une archive **PFS0** dont les entrees sont deja nommees par leur
content ID (`<32 hex>.nca`, `<32 hex>.cnmt.nca`) — exactement le nom qu'Eden
attend dans `nand/user/Contents/registered/`. Installer revient donc a :

  1. extraire les .nca de l'archive,
  2. les deposer dans registered/,
  3. inscrire la cle de titre du ticket (.tik) dans `keys/title.keys`,
     sans quoi le contenu chiffre reste illisible.

Rien n'est ecrase : l'etat de la NAND est sauvegarde avant toute ecriture.
"""

import struct
from datetime import datetime
from pathlib import Path

from . import config, device, profils

# Ces chemins dependent de l'emulateur choisi : ils ne peuvent plus etre des
# constantes de module. Ils l'etaient, figes sur Eden, ce qui rendait tout
# autre emulateur inatteignable sans modifier le code.


def dossier():
    """Dossier de donnees de l'emulateur actif, ou "" s'il est inconnu."""
    return profils.dossier_donnees()


def registered():
    return profils.sous("nand/user/Contents/registered")


def title_keys():
    return profils.sous("keys/title.keys")

# Emplacements du ticket (format Nintendo) : cle de titre chiffree et rights ID.
TIK_KEY_OFF, TIK_RIGHTS_OFF = 0x180, 0x2A0


# --------------------------------------------------------------------- PFS0

class Incomplet(ValueError):
    """L'archive annonce plus de donnees qu'elle n'en contient (telechargement rate)."""


def read_pfs0(path):
    """Liste le contenu d'un .nsp : [(nom, offset_absolu, taille)].

    L'archive est verifiee : un fichier tronque annonce des contenus qui
    depassent sa taille reelle. Mieux vaut le refuser ici que d'installer
    des donnees incompletes dans la NAND.
    """
    reel = Path(path).stat().st_size
    with open(path, "rb") as fh:
        tete = fh.read(16)
        if len(tete) < 16:
            raise Incomplet("fichier vide ou tronque")
        magic, count, strtab, _ = struct.unpack("<4sIII", tete)
        if magic != b"PFS0":
            raise ValueError("ce fichier n'est pas une archive NSP (PFS0)")
        entries = [struct.unpack("<QQII", fh.read(24)) for _ in range(count)]
        names = fh.read(strtab)
        base = 16 + count * 24 + strtab
        out, attendu = [], base
        for off, size, noff, _pad in entries:
            nom = names[noff:names.index(b"\0", noff)].decode("utf-8", "replace")
            out.append((nom, base + off, size))
            attendu = max(attendu, base + off + size)
        if attendu > reel:
            manque = attendu - reel
            raise Incomplet("il manque %.1f Mo (fichier de %.1f Mo, %.1f Mo attendus)"
                            % (manque / 1048576, reel / 1048576, attendu / 1048576))
        return out


def extract(path, entry, dest_dir):
    """Extrait une entree du .nsp vers un dossier local."""
    nom, off, size = entry
    dest = Path(dest_dir) / nom
    with open(path, "rb") as src, dest.open("wb") as out:
        src.seek(off)
        reste = size
        while reste > 0:
            bloc = src.read(min(1 << 22, reste))
            if not bloc:
                break
            out.write(bloc)
            reste -= len(bloc)
    return dest


# ------------------------------------------------------------------ tickets

def ticket_key(path):
    """(rights_id, cle_de_titre_chiffree) d'un .tik, en hexa. None si illisible."""
    data = Path(path).read_bytes()
    if len(data) < TIK_RIGHTS_OFF + 16:
        return None
    key = data[TIK_KEY_OFF:TIK_KEY_OFF + 16]
    rights = data[TIK_RIGHTS_OFF:TIK_RIGHTS_OFF + 16]
    if not any(rights):
        return None
    return (rights.hex(), key.hex())


# ------------------------------------------------------------------ analyse

def inspect(nsp_path):
    """Ce que l'installation deposerait, sans rien ecrire."""
    contenu = read_pfs0(nsp_path)
    ncas = [(n, o, s) for n, o, s in contenu if n.lower().endswith(".nca")]
    tiks = [(n, o, s) for n, o, s in contenu if n.lower().endswith(".tik")]
    return {
        "fichier": Path(nsp_path).name,
        "nca": [{"nom": n, "taille": s} for n, _, s in ncas],
        "tickets": len(tiks),
        "octets": sum(s for _, _, s in ncas),
    }


# ---------------------------------------------------------------- sauvegarde

def backup_state(job):
    """Note l'etat de registered/ et de title.keys avant d'y toucher."""
    liste = device._shell("ls -1 %s 2>/dev/null" % device._q(registered()), timeout=60)
    cles = device._shell("cat %s 2>/dev/null" % device._q(title_keys()), timeout=60)
    dossier = config.ROOT / "_eden-backup"
    dossier.mkdir(exist_ok=True)
    horo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    (dossier / ("registered_%s.txt" % horo)).write_text(liste, encoding="utf-8")
    (dossier / ("title.keys_%s" % horo)).write_text(cles, encoding="utf-8")
    n = len([l for l in liste.splitlines() if l.strip()])
    job.log("Etat sauvegarde : %d fichier(s) deja dans la NAND (_eden-backup/)." % n)
    return horo


def installed_ids():
    """Content IDs deja presents dans la NAND d'Eden."""
    out = device._shell("ls -1 %s 2>/dev/null" % device._q(registered()), timeout=60)
    return {l.strip() for l in out.splitlines() if l.strip()}


def content_names(nsp_path):
    """Noms des .nca d'un .nsp. Renvoie (noms, probleme)."""
    try:
        return [n for n, _, _ in read_pfs0(nsp_path) if n.lower().endswith(".nca")], None
    except Incomplet as exc:
        return [], "incomplet : %s" % exc
    except (ValueError, OSError, struct.error) as exc:
        return [], "illisible : %s" % exc


def status(paths, installed=None):
    """Pour chaque .nsp : est-il actif dans Eden ?

    'actif'     tous ses contenus sont dans la NAND
    'partiel'   installation incomplete (interrompue ?)
    'absent'    rien n'est installe
    'incomplet' le fichier source est tronque : inutilisable
    'illisible' fichier corrompu
    'inconnu'   console non consultee, on ne peut rien affirmer
    """
    if installed is None:
        installed = installed_ids()
        connectee = True
    else:
        connectee = installed is not False
    inst = installed if isinstance(installed, set) else set()
    out = []
    for p in paths:
        noms, probleme = content_names(p)
        if probleme:
            etat = "incomplet" if probleme.startswith("incomplet") else "illisible"
        elif not connectee:
            etat = "inconnu"
        else:
            presents = sum(1 for n in noms if n in inst)
            etat = ("actif" if presents == len(noms)
                    else "partiel" if presents else "absent")
        out.append({"path": str(p), "nom": Path(p).name, "contenus": len(noms),
                    "etat": etat, "probleme": probleme})
    return out


# --------------------------------------------------------------- installation

def install(paths, job):
    """Installe des .nsp (MAJ/DLC) dans la NAND d'Eden, via adb."""
    if device.state() != "device":
        job.log("Console non connectee.")
        return
    if not device._shell("[ -d %s ] && echo 1" % device._q(dossier())).strip():
        job.log("%s introuvable sur la console (%s)."
                % (profils.actif()["nom"], profils.paquet() or "paquet inconnu"))
        return

    backup_state(job)
    device._shell("mkdir -p %s" % device._q(registered()))
    deja = installed_ids()
    tmp = Path(config.ROOT) / "_import" / "_nand_tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    job.set_total(len(paths))
    nouvelles_cles, poses, ignores = {}, 0, 0
    try:
        for p in paths:
            if not job.checkpoint():
                job.log("Installation interrompue.")
                break
            src = Path(p)
            job.log("Lecture de %s…" % src.name)
            try:
                contenu = read_pfs0(src)
            except Incomplet as exc:
                job.log("  ignore, telechargement incomplet : %s" % exc, "warn")
                job.tick()
                continue
            except (ValueError, OSError, struct.error) as exc:
                job.log("  ignore, fichier illisible : %s" % exc, "warn")
                job.tick()
                continue

            for nom, off, taille in contenu:
                bas = nom.lower()
                if bas.endswith(".nca"):
                    if nom in deja:
                        ignores += 1
                        continue
                    f = extract(src, (nom, off, taille), tmp)
                    local = f.stat().st_size
                    if local != taille:
                        job.log("  ECHEC %s : donnees incompletes dans l'archive "
                                "(%.1f Mo lus sur %.1f attendus)"
                                % (nom[:20] + "…", local / 1048576, taille / 1048576))
                        f.unlink(missing_ok=True)
                        continue
                    rc, out, err = device._run(["push", str(f), registered() + "/"], timeout=3600)
                    distant = device.remote_size(registered() + "/" + nom)
                    if rc == 0 and distant == taille:
                        poses += 1
                        device.ouvrir_droits(registered() + "/" + nom)
                        job.log("  installe %s (%.1f Mo)" % (nom[:20] + "…", taille / 1048576))
                    else:
                        # ne jamais laisser un contenu partiel dans la NAND :
                        # Eden le chargerait et le jeu planterait.
                        device.remote_rm(registered() + "/" + nom)
                        job.log("  ECHEC %s : %s" % (nom[:20] + "…",
                                "copie incomplete (%s sur %s octets), retiree de la console"
                                % (distant, taille) if rc == 0
                                else ((err or out).strip().splitlines() or ["transfert refuse"])[-1]))
                    f.unlink(missing_ok=True)
                elif bas.endswith(".tik"):
                    f = extract(src, (nom, off, taille), tmp)
                    kv = ticket_key(f)
                    if kv:
                        nouvelles_cles[kv[0]] = kv[1]
                    f.unlink(missing_ok=True)
            job.tick()

        if nouvelles_cles:
            _merge_title_keys(nouvelles_cles, job)
    finally:
        for reste in tmp.glob("*"):
            reste.unlink(missing_ok=True)
        tmp.rmdir()

    job.log("Termine : %d fichier(s) installe(s), %d deja present(s), %d cle(s) de titre."
            % (poses, ignores, len(nouvelles_cles)))
    if poses:
        job.log("Relance Eden pour que les mises a jour et DLC soient pris en compte.")


def _merge_title_keys(nouvelles, job):
    """Ajoute les cles de titre sans toucher a celles deja presentes."""
    actuel = device._shell("cat %s 2>/dev/null" % device._q(title_keys()), timeout=60)
    lignes, connues = [], set()
    for l in actuel.splitlines():
        lignes.append(l.rstrip())
        if "=" in l:
            connues.add(l.split("=")[0].strip().lower())
    ajout = 0
    for rights, key in sorted(nouvelles.items()):
        if rights.lower() in connues:
            continue
        lignes.append("%s = %s" % (rights, key))
        ajout += 1
    if not ajout:
        job.log("Cles de titre : rien de nouveau.")
        return
    local = config.ROOT / "_import" / "_title.keys"
    local.write_text("\n".join([l for l in lignes if l.strip()]) + "\n", encoding="utf-8")
    device._shell("mkdir -p %s" % device._q(dossier() + "/keys"))
    device._run(["push", str(local), title_keys()], timeout=120)
    device.ouvrir_droits(title_keys())
    local.unlink(missing_ok=True)
    job.log("Cles de titre : %d ajoutee(s) dans title.keys." % ajout)
