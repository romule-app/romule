"""Lecture et ecriture de la configuration d'Eden (globale et par jeu).

Eden stocke ses reglages en INI facon Qt :

  config/config.ini            reglages globaux
  config/custom/<TITLEID>.ini  surcharges d'un jeu

Chaque cle est accompagnee de marqueurs :
  - global   : `cle\\default=true|false` puis `cle=valeur`
  - par jeu  : `cle\\use_global=false`, `cle\\default=false`, `cle=valeur`
    (`use_global=true` signifie « suivre le reglage global »)

On analyse et on reecrit le fichier en preservant l'ordre et les sections :
Eden reste maitre du fichier, on ne fait qu'y poser des valeurs.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from . import config, device, nand

CONFIG_DIR = nand.EDEN_FILES + "/config"
GLOBAL_INI = CONFIG_DIR + "/config.ini"
CUSTOM_DIR = CONFIG_DIR + "/custom"
PROFILES = config.ROOT / "_profils-eden"
BACKUP = config.ROOT / "_eden-backup"

_SECTION = re.compile(r"^\[(.+)\]\s*$")


# ------------------------------------------------------------------ analyse

def parse(texte):
    """INI -> [(section, [(cle, valeur), ...]), ...] en preservant l'ordre."""
    out, courante = [], None
    for ligne in texte.splitlines():
        m = _SECTION.match(ligne.strip())
        if m:
            courante = (m.group(1), [])
            out.append(courante)
        elif courante is not None and "=" in ligne:
            cle, _, val = ligne.partition("=")
            courante[1].append((cle.strip(), val.strip()))
    return out


def dump(data):
    """Reconstruit le texte INI a partir de la structure analysee."""
    blocs = []
    for nom, paires in data:
        lignes = ["[%s]" % nom] + ["%s=%s" % (k, v) for k, v in paires]
        blocs.append("\n".join(lignes))
    return "\n\n".join(blocs) + "\n"


def to_dict(data):
    """Vue simple : {section: {cle: valeur}} en ignorant les marqueurs."""
    out = {}
    for nom, paires in data:
        vals = {k: v for k, v in paires if "\\" not in k}
        if vals:
            out[nom] = vals
    return out


def apply_changes(data, changements, par_jeu):
    """Pose des valeurs dans la structure. changements = {section: {cle: val}}."""
    index = {nom: paires for nom, paires in data}
    poses = 0
    for section, valeurs in changements.items():
        paires = index.get(section)
        if paires is None:
            paires = []
            data.append((section, paires))
            index[section] = paires
        for cle, val in valeurs.items():
            marqueurs = [("%s\\use_global" % cle, "false")] if par_jeu else []
            marqueurs += [("%s\\default" % cle, "false"), (cle, str(val))]
            for mk, mv in marqueurs:
                for i, (k, _) in enumerate(paires):
                    if k == mk:
                        paires[i] = (mk, mv)
                        break
                else:
                    paires.append((mk, mv))
            poses += 1
    return poses


# ------------------------------------------------------------------ appareil

def _lire(chemin):
    return device._shell("cat %s 2>/dev/null" % device._q(chemin), timeout=60)


def _ecrire(chemin, texte, job):
    tmp = config.ROOT / "_import" / "_eden.ini"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(texte, encoding="utf-8")
    device._shell("mkdir -p %s" % device._q(chemin.rsplit("/", 1)[0]))
    rc, out, err = device._run(["push", str(tmp), chemin], timeout=120)
    tmp.unlink(missing_ok=True)
    if rc != 0:
        job.log("Ecriture impossible : %s" % ((err or out).strip().splitlines() or [""])[-1])
        return False
    device.ouvrir_droits(chemin)
    return True


def _sauvegarder(chemin, texte):
    BACKUP.mkdir(exist_ok=True)
    nom = chemin.rsplit("/", 1)[-1]
    horo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    (BACKUP / ("%s_%s" % (nom, horo))).write_text(texte or "", encoding="utf-8")


# Un title ID Switch fait 16 chiffres hexadecimaux, toujours. Le chemin
# construit ici part vers `adb push` et `adb shell rm -f` : sans cette
# verification, un « tid » comme « ../../../../data/x » ecrivait et effacait
# des fichiers arbitraires sur la console. La mise entre guillemets protege
# des metacaracteres du shell, pas des chemins relatifs.
_TID = __import__("re").compile(r"^[0-9A-Fa-f]{16}$")


def game_ini(tid):
    tid = str(tid or "").strip()
    if not _TID.match(tid):
        raise ValueError("Identifiant de jeu invalide : %r" % tid[:32])
    return "%s/%s.ini" % (CUSTOM_DIR, tid.upper())


def read_config(tid=None):
    """Configuration globale, ou celle d'un jeu. Renvoie (texte, structure)."""
    chemin = game_ini(tid) if tid else GLOBAL_INI
    texte = _lire(chemin)
    return texte, parse(texte)


def games_with_config():
    """Title IDs ayant une configuration propre sur la console."""
    out = device._shell("ls -1 %s 2>/dev/null" % device._q(CUSTOM_DIR), timeout=30)
    return [l.strip()[:-4].lower() for l in out.splitlines() if l.strip().endswith(".ini")]


def write_config(changements, job, tid=None):
    """Applique des valeurs a la config globale ou a celle d'un jeu."""
    if device.state() != "device":
        job.log("Console non connectee.")
        return False
    chemin = game_ini(tid) if tid else GLOBAL_INI
    texte = _lire(chemin)
    if not texte.strip() and tid:
        job.log("Aucune configuration pour ce jeu : creation.")
        data = []
    elif not texte.strip():
        job.log("Configuration globale introuvable sur la console.")
        return False
    else:
        data = parse(texte)
    _sauvegarder(chemin, texte)
    n = apply_changes(data, changements, par_jeu=bool(tid))
    if not _ecrire(chemin, dump(data), job):
        return False
    job.log("%d reglage(s) applique(s) %s." % (n, ("au jeu %s" % tid) if tid else "globalement"))
    job.log("Ancienne version conservee dans _eden-backup/.")
    return True


# Reglages qui decrivent la machine du contributeur, pas le jeu. Une config
# EmuReady les transporte telle quelle : driver_path pointe vers le dossier de
# l'appareil d'origine (souvent « Android/data/null/... ») et vers un pilote GPU
# que l'utilisateur n'a pas installe. Eden tente alors de charger un pilote
# introuvable et renonce a demarrer, sans afficher la moindre erreur.
CLES_LOCALES = ("driver_path",)


def _purger_locales(data, job=None):
    """Retire les reglages propres a l'appareil d'origine ; renvoie leur nombre."""
    retires = 0
    for _section, paires in data:
        garde, touche = [], False
        for cle, val in paires:
            racine = cle.split("\\", 1)[0]
            if racine in CLES_LOCALES:
                touche = True
                if cle == racine:
                    retires += 1
                continue
            garde.append((cle, val))
        if touche:
            for racine in CLES_LOCALES:
                garde.append(("%s\\use_global" % racine, "true"))
            paires[:] = garde
    if retires and job:
        job.log("%d reglage(s) propre(s) a l'appareil d'origine ignore(s) "
                "(pilote GPU) : le tien reste utilise." % retires, "warn")
    return retires


def write_raw(contenu, job, tid):
    """Remplace la configuration d'un jeu par un fichier fourni (EmuReady).

    Le fichier est valide avant ecriture : on refuse tout ce qui ne ressemble
    pas a une configuration Eden.
    """
    if not tid:
        job.log("Un jeu doit etre precise.")
        return False
    data = parse(contenu)
    if not data:
        job.log("Contenu invalide : aucune section reconnue.")
        return False
    _purger_locales(data, job)
    if device.state() != "device":
        job.log("Console non connectee.")
        return False
    chemin = game_ini(tid)
    _sauvegarder(chemin, _lire(chemin))
    if not _ecrire(chemin, dump(data), job):
        return False
    surcharges = contenu.count("use_global=false")
    job.log("Configuration appliquee : %d section(s), %d reglage(s) specifique(s)."
            % (len(data), surcharges))
    job.log("Ancienne version conservee dans _eden-backup/.")
    return True


# ------------------------------------------------------- retours en arriere

def backups_for(tid):
    """Sauvegardes disponibles pour un jeu, de la plus recente a la plus ancienne."""
    if not tid or not BACKUP.is_dir():
        return []
    prefixe = "%s.ini_" % tid.upper()
    out = []
    for p in sorted(BACKUP.glob(prefixe + "*"), reverse=True):
        horo = p.name[len(prefixe):]
        texte = ""
        try:
            texte = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass
        data = parse(texte)
        out.append({
            "fichier": p.name,
            "quand": horo.replace("_", " à ").replace("-", "/", 2),
            "octets": p.stat().st_size,
            "sections": len(data),
            "surcharges": texte.count("use_global=false"),
            "vide": not texte.strip(),
        })
    return out


def restore_backup(tid, fichier, job):
    """Remet une sauvegarde en place sur la console."""
    if not tid or not fichier:
        job.log("Sauvegarde non precisee.")
        return False
    p = BACKUP / Path(fichier).name          # jamais de chemin fourni par le client
    if not p.is_file() or not p.name.upper().startswith(tid.upper() + ".INI_"):
        job.log("Sauvegarde introuvable pour ce jeu.")
        return False
    if device.state() != "device":
        job.log("Console non connectee.")
        return False
    chemin = game_ini(tid)
    _sauvegarder(chemin, _lire(chemin))      # l'etat courant devient restaurable a son tour
    texte = p.read_text(encoding="utf-8", errors="ignore")
    if not texte.strip():
        # la sauvegarde correspond a « aucune configuration » : on efface
        device._shell("rm -f %s" % device._q(chemin))
        job.log("Configuration du jeu retiree (retour a l'etat d'origine).")
        return True
    if not _ecrire(chemin, texte, job):
        return False
    job.log("Configuration restauree (%s)." % fichier.rsplit("_", 1)[-1])
    return True


# ------------------------------------------------------------------ profils

def profile_list():
    PROFILES.mkdir(exist_ok=True)
    out = []
    for p in sorted(PROFILES.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"nom": p.stem, "portee": d.get("portee", "global"),
                        "reglages": sum(len(v) for v in d.get("valeurs", {}).values()),
                        "description": d.get("description", "")})
        except (ValueError, OSError):
            continue
    return out


def profile_read(nom):
    p = PROFILES / (re.sub(r"[^\w\-. ]", "", nom) + ".json")
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def profile_save(nom, valeurs, portee="global", description=""):
    PROFILES.mkdir(exist_ok=True)
    sur = re.sub(r"[^\w\-. ]", "", nom).strip() or "profil"
    p = PROFILES / (sur + ".json")
    p.write_text(json.dumps({"portee": portee, "description": description,
                             "valeurs": valeurs}, indent=2, ensure_ascii=False),
                 encoding="utf-8")
    return sur


def capture(tid=None, sections=None):
    """Capture la configuration actuelle (globale ou d'un jeu) en profil."""
    _, data = read_config(tid)
    vals = to_dict(data)
    if sections:
        vals = {k: v for k, v in vals.items() if k in sections}
    return vals
