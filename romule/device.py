"""Couche adb : detection de la console, exploration, import (pull) et push.

Cible : handheld Android sous Eden, branche en USB avec le debogage active.
Les fonctions `parse_*` et `reconcile` sont pures (testables sans appareil) ;
tout ce qui parle a adb passe par `_run` / `_shell`.
"""

import hashlib
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import config, titleid

SD_RE = re.compile(r"^[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$")
_GAME_FIND = (r"\( -iname '*.nsp' -o -iname '*.xci' "
              r"-o -iname '*.nsz' -o -iname '*.xcz' \)")


# ------------------------------------------------------------- appels adb bruts

def adb_available():
    return shutil.which("adb") is not None


# Serie de l'appareil vise. Utile quand l'USB et le wifi sont connectes en
# meme temps : sans cela adb refuse d'agir ("more than one device").
_SERIAL = None


def set_target(serial):
    global _SERIAL
    _SERIAL = serial or None


def _run(args, timeout=60, targeted=True):
    """Renvoie (returncode, stdout, stderr). `targeted` vise l'appareil choisi."""
    if not adb_available():
        return 1, "", "adb introuvable"
    cmd = ["adb"]
    if targeted:
        # Choisir la cible AU BESOIN. Sans cela, la premiere commande d'un
        # processus partait sans `-s` : avec deux transports attaches (une
        # console reliee en Wi-Fi en expose souvent deux, IP et mDNS), adb
        # repondait « more than one device » et _shell renvoyait une chaine
        # vide — un echec qui passait pour un dossier vide.
        if not _SERIAL:
            d = _pick(devices())
            if d:
                set_target(d["serial"])
        if _SERIAL:
            cmd += ["-s", _SERIAL]
    try:
        r = subprocess.run(cmd + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)


def _shell(cmd, timeout=30):
    """Execute une commande dans le shell de l'appareil, renvoie stdout."""
    rc, out, _ = _run(["shell", cmd], timeout=timeout)
    return out if rc == 0 else ""


def _q(path):
    """Quote un chemin pour le shell distant."""
    return "'" + str(path).replace("'", "'\\''") + "'"


# ------------------------------------------------------------- detection

def is_wireless(serial):
    """Le lien passe-t-il par le reseau ?

    Deux formes existent : « 192.168.1.42:5555 » pour un `adb connect` classique,
    et « adb-XXXX-YYYY._adb-tls-connect._tcp » pour une connexion adb-TLS
    annoncee en mDNS. La seconde ne contient PAS de deux-points : ne tester que
    ce caractere la faisait passer pour de l'USB, et l'outil annoncait un cable
    branche alors que tout transitait par le wifi.
    """
    s = str(serial or "")
    return ":" in s or "_adb-tls-" in s or s.endswith("._tcp")


def _pick(devs, prefer=None):
    """Choisit l'appareil a piloter : celui demande, sinon l'USB (2 a 5 fois plus
    rapide et plus stable que le wifi), sinon le wifi."""
    ready = [d for d in devs if d.get("state") == "device"]
    if not ready:
        return None
    if prefer:
        for d in ready:
            if d["serial"] == prefer:
                return d
    for d in ready:
        if not is_wireless(d["serial"]):
            return d
    return ready[0]


def state(prefer=None):
    """'device', 'unauthorized', 'offline'... ou None. Gere plusieurs appareils."""
    devs = devices()
    if not devs:
        return None
    d = _pick(devs, prefer)
    if d:
        set_target(d["serial"])
        return "device"
    set_target(None)
    return devs[0].get("state")


def connection():
    """Comment la console est reliee : {'kind': 'wifi'|'usb'|None, 'serial', 'name'}."""
    devs = devices()
    d = _pick(devs, _SERIAL)
    if not d:
        return {"kind": None, "serial": None,
                "state": devs[0].get("state") if devs else None}
    set_target(d["serial"])
    return {"kind": "wifi" if is_wireless(d["serial"]) else "usb",
            "serial": d["serial"], "state": "device",
            "depuis": _depuis(d["serial"])}


# Depuis quand ce lien tient. Mesure a partir de la premiere fois qu'on voit ce
# serial : l'information n'existe pas dans adb, et elle dit bien plus que
# « connectee » — une connexion sans fil qui vient de repartir n'a pas la meme
# fiabilite qu'une autre etablie depuis deux heures.
_VUS = {}


def _depuis(serial):
    import time as _t
    if serial not in _VUS:
        _VUS[serial] = _t.time()
    # on oublie les liens disparus, sinon la duree serait fausse au retour
    vivants = {d["serial"] for d in devices()}
    for s in list(_VUS):
        if s not in vivants:
            del _VUS[s]
    return int(_t.time() - _VUS.get(serial, _t.time()))


def parse_devices(out):
    devices = []
    for line in out.splitlines()[1:]:  # 1re ligne = "List of devices attached"
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        entry = {"serial": parts[0], "state": parts[1] if len(parts) > 1 else "?"}
        for kv in parts[2:]:
            if ":" in kv:
                k, v = kv.split(":", 1)
                entry[k] = v
        devices.append(entry)
    return devices


def devices():
    _, out, _ = _run(["devices", "-l"], targeted=False)
    return parse_devices(out)


# ------------------------------------------------------------- sans fil (wifi)

def device_ip():
    """Adresse IP wifi de la console (vue depuis elle-meme)."""
    out = _shell("ip -f inet addr show wlan0 2>/dev/null")
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
    if m:
        return m.group(1)
    out = _shell("ip route 2>/dev/null")
    m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else None


def discover():
    """Adresses de connexion annoncees par les consoles en debogage sans fil."""
    rc, out, _ = _run(["mdns", "services"], timeout=15, targeted=False)
    found = []
    for line in out.splitlines():
        if "_adb-tls-connect" in line:
            m = re.search(r"(\d+\.\d+\.\d+\.\d+):(\d+)", line)
            if m:
                addr = "%s:%s" % (m.group(1), m.group(2))
                if addr not in found:
                    found.append(addr)
    return found


def connect(addr, timeout=20):
    """Se connecte a une console par le reseau. Renvoie (ok, message)."""
    if not addr:
        return (False, "adresse manquante")
    rc, out, err = _run(["connect", addr], timeout=timeout, targeted=False)
    msg = (out + err).strip().splitlines()
    msg = msg[-1] if msg else ""
    ok = "connected" in msg.lower() and "cannot" not in msg.lower()
    if ok:
        set_target(addr)
    return (ok, msg or ("connecte a %s" % addr))


def disconnect(addr=None):
    _run(["disconnect"] + ([addr] if addr else []), timeout=15, targeted=False)
    set_target(None)


def pair(addr, code):
    """Appairage sans fil (Android 11+). Renvoie (ok, message)."""
    if not addr or not code:
        return (False, "adresse ou code manquant")
    try:
        p = subprocess.run(["adb", "pair", addr, str(code)],
                           capture_output=True, text=True, timeout=60)
        msg = (p.stdout + p.stderr).strip().splitlines()
        msg = msg[-1] if msg else ""
        return ("successfully" in msg.lower() or p.returncode == 0, msg)
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, str(exc))


def switch_to_wifi(port=5555):
    """Bascule une console branchee en USB vers le wifi. Renvoie (ok, addr, msg)."""
    devs = devices()
    usb = next((d for d in devs if d.get("state") == "device" and not is_wireless(d["serial"])), None)
    if not usb:
        return (False, None, "Branche d'abord la console en USB.")
    set_target(usb["serial"])
    ip = device_ip()
    if not ip:
        return (False, None, "La console n'a pas d'adresse wifi (connecte-la au meme reseau).")
    rc, out, err = _run(["tcpip", str(port)], timeout=30)
    if rc != 0:
        return (False, None, ((err or out).strip().splitlines() or ["echec"])[-1])
    time.sleep(1.5)                     # l'appareil redemarre son service adb
    addr = "%s:%d" % (ip, port)
    ok, msg = connect(addr)
    return (ok, addr if ok else None, msg)


def open_url(url):
    """Ouvre une adresse dans le navigateur de la console. Renvoie (ok, message)."""
    rc, out, err = _run(["shell", "am", "start", "-a", "android.intent.action.VIEW",
                         "-d", url], timeout=30)
    txt = (out + err).strip()
    if rc == 0 and "error" not in txt.lower():
        return (True, "")
    return (False, (txt.splitlines() or ["ouverture impossible"])[-1])


def info():
    """Carte d'identite de la console connectee."""
    st = state()
    if st != "device":
        return {"connected": False, "state": st}
    prop = lambda p: _shell("getprop %s" % p).strip()
    model = prop("ro.product.model")
    manuf = prop("ro.product.manufacturer")
    _, serial, _ = _run(["get-serialno"], timeout=10)
    if model and manuf and model.lower().startswith(manuf.lower()):
        name = model  # evite "AYN AYN Thor"
    else:
        name = (" ".join(x for x in (manuf, model) if x)).strip() or "Appareil Android"
    return {
        "connected": True,
        "state": st,
        "name": name,
        "model": model,
        "manufacturer": manuf,
        "android": prop("ro.build.version.release"),
        "serial": serial.strip(),
    }


# ------------------------------------------------------------- volumes / SD

def parse_df(out):
    """(total_octets, libre_octets) depuis une sortie `df -k`, sinon (None, None)."""
    lines = [l for l in out.splitlines() if l.strip()]
    if len(lines) < 2:
        return (None, None)
    nums = [int(c) for c in lines[-1].split() if c.isdigit()]
    if len(nums) >= 3:  # 1K-blocks, Used, Available
        return (nums[0] * 1024, nums[2] * 1024)
    return (None, None)


def _df(path):
    return parse_df(_shell("df -k %s 2>/dev/null" % _q(path)))


def volume_root(path):
    """Racine de volume d'un chemin (pour mesurer l'espace, meme si le dossier
    cible n'existe pas encore)."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "storage":
        if parts[1] == "emulated":
            return "/storage/emulated/%s" % (parts[2] if len(parts) >= 3 else "0")
        return "/storage/%s" % parts[1]
    return "/" + parts[0] if parts else path


def free_of(path):
    """Octets libres sur le volume qui contient path, ou None."""
    return _df(volume_root(path))[1]


def volumes():
    """Volumes de stockage : interne + carte(s) SD, avec espace libre."""
    if state() != "device":
        return []
    vols = []
    total, free = _df("/storage/emulated/0")
    vols.append({"path": "/storage/emulated/0", "label": "Stockage interne",
                 "kind": "interne", "total": total, "free": free})
    for line in _shell("ls -1 /storage 2>/dev/null").splitlines():
        e = line.strip().rstrip("/")
        if SD_RE.match(e):
            t, f = _df("/storage/%s" % e)
            vols.append({"path": "/storage/%s" % e, "label": "Carte SD (%s)" % e,
                         "kind": "SD", "total": t, "free": f})
    return vols


# ------------------------------------------------------------- exploration

def list_dir(remote):
    """Contenu d'un dossier de l'appareil (dossiers d'abord)."""
    out = _shell("ls -1 -p %s 2>/dev/null" % _q(remote))
    items = []
    for l in out.splitlines():
        if not l.strip():
            continue
        items.append({"name": l.rstrip("/"), "is_dir": l.endswith("/")})
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return items


def parse_find(out):
    """Lignes 'taille|chemin' -> liste de jeux classifies."""
    games = []
    for line in out.splitlines():
        size, sep, path = line.partition("|")
        if not sep:
            continue
        path = path.strip()
        if not path:
            continue
        name = path.rsplit("/", 1)[-1]
        tid = titleid.from_name(name)
        games.append({
            "path": path, "name": name,
            "size": int(size.strip()) if size.strip().isdigit() else 0,
            "tid": tid,
            "type": titleid.tid_type(tid) if tid else "INCONNU",
            "version": titleid.version_from_name(name),
        })
    games.sort(key=lambda g: g["path"].lower())
    return games


def find_games(root, exts=None):
    """Fichiers de jeu sous un dossier de l'appareil.

    `exts` permet d'interroger un autre systeme que la Switch (.iso, .chd…) :
    sans lui, les autres consoles n'avaient aucun moyen de savoir ce qui etait
    deja en place, et heritaient d'une vue sans etat.
    """
    if exts:
        motifs = " -o ".join("-iname '*%s'" % e for e in sorted(exts))
        filtre = r"\( %s \)" % motifs
    else:
        filtre = _GAME_FIND
    cmd = ("find %s -type f %s -exec stat -c '%%s|%%n' {} \\; 2>/dev/null"
           % (_q(root), filtre))
    return parse_find(_shell(cmd, timeout=180))


def detect_games_dir():
    """Devine le dossier racine des jeux : le plus long ancetre commun a tous
    les fichiers Switch trouves sur l'appareil (gere aussi bien un dossier a plat
    que des arborescences par jeu ou par type)."""
    if state() != "device":
        return None

    def ancetre(dirs):
        common = []
        # `strict=False` explicite : s'arreter au chemin le plus court est
        # exactement ce qu'on veut d'un ancetre commun.
        for parts in zip(*[d.split("/") for d in dirs], strict=False):
            if len(set(parts)) == 1:
                common.append(parts[0])
            else:
                break
        return "/".join(common) or dirs[0]

    # Un ancetre commun calcule sur TOUS les volumes a la fois donne « /storage »
    # des que des jeux existent a la fois sur la carte SD et en interne — un
    # chemin qui ne designe rien. On raisonne donc volume par volume, et on
    # retient celui qui porte le plus de jeux.
    best, best_n = None, 0
    for v in volumes():
        cmd = ("find %s -maxdepth 7 -type f %s 2>/dev/null"
               % (_q(v["path"]), _GAME_FIND))
        dirs = [l.strip().rsplit("/", 1)[0]
                for l in _shell(cmd, timeout=120).splitlines() if l.strip()]
        if not dirs or len(dirs) <= best_n:
            continue
        racine = ancetre(dirs)
        # jamais plus haut que le volume lui-meme
        if not racine.startswith(v["path"].rstrip("/")):
            racine = v["path"].rstrip("/")
        best, best_n = racine, len(dirs)
    return best


def _tree_folders():
    return sorted(set(config.LAYOUT_FOLDER.values()))  # GAMES, UPDATE, DLC


def real_folders(device_dir):
    """Nom reel de chaque dossier de type sur la console : {"GAMES": "Games", ...}.

    La carte SD est insensible a la casse : un dossier cree jadis sous le nom
    « Games » repond aussi bien a « GAMES ». Les commandes shell s'en accommodent,
    mais nos comparaisons de chemins en Python, elles, ne matchent plus rien —
    une verification peut alors passer a vide et paraitre bonne. Pire, la
    protection « ne supprime pas les dossiers de type » ne les reconnait plus.
    On lit donc les noms tels qu'ils existent reellement.
    """
    canon = _tree_folders()
    out = {c: c for c in canon}
    base = device_dir.rstrip("/")
    if not base or state() != "device":
        return out
    presents = {}
    for ligne in (_shell("ls -1 %s" % _q(base)) or "").splitlines():
        nom = ligne.strip()
        if nom:
            presents[nom.lower()] = nom
    for c in canon:
        if c.lower() in presents:
            out[c] = presents[c.lower()]
    return out


def tree_status(device_dir):
    """Presence des sous-dossiers d'organisation (GAMES/UPDATE/DLC) sur la console."""
    base = device_dir.rstrip("/")
    if state() != "device" or not base:
        return {}
    out = {}
    for name in _tree_folders():
        r = _shell("[ -d %s ] && echo 1 || echo 0" % _q(base + "/" + name)).strip()
        out[name] = r.endswith("1")
    return out


def make_tree(device_dir):
    """Cree les sous-dossiers d'organisation manquants. Renvoie le nouvel etat."""
    base = device_dir.rstrip("/")
    if state() == "device" and base:
        for name in _tree_folders():
            _shell("mkdir -p %s" % _q(base + "/" + name))
    _invalider_cache()
    return tree_status(device_dir)


def organize(device_dir, job, types=None):
    """Range la console : chaque fichier va dans GAMES/UPDATE/DLC selon son type
    (meme s'il etait dans un dossier de jeu), puis on supprime les dossiers vides."""
    if state() != "device":
        job.log("Console non prete.")
        return
    make_tree(device_dir)
    base = device_dir.rstrip("/")
    reels = real_folders(device_dir)
    games = find_games(device_dir)
    job.set_total(len(games))
    moved = 0
    for g in games:
        # Le type connu de la ludotheque prime : il vient du contenu du fichier,
        # alors qu'ici on ne dispose que du nom — et un nom ment parfois (title ID
        # tronque, absent, ou annoncant une base alors que c'est une mise a jour).
        typ = (types or {}).get(g["name"])
        if typ not in config.LAYOUT_FOLDER:
            typ = titleid.tid_type(g["tid"]) if g["tid"] else "INCONNU"
        folder = reels[config.LAYOUT_FOLDER[typ]]
        dst = "%s/%s/%s" % (base, folder, g["name"])
        # deja au bon endroit (directement sous le bon dossier de type) ?
        if g["path"] == dst:
            job.tick()
            continue
        _shell("mv %s %s" % (_q(g["path"]), _q(dst)))
        job.log("Range : %s -> %s/" % (g["name"], folder))
        moved += 1
        job.tick()
    # supprime les dossiers de jeux devenus vides (hors GAMES/UPDATE/DLC)
    keep = " ".join("-not -name %s" % _q(tf) for tf in sorted(set(reels.values())))
    _shell("find %s -mindepth 1 -type d -empty %s -delete 2>/dev/null" % (_q(base), keep))
    _shell("find %s -mindepth 1 -type d -empty %s -delete 2>/dev/null" % (_q(base), keep))
    job.log("%d fichier(s) range(s) en GAMES / UPDATE / DLC sur la console." % moved)


    _invalider_cache()

def analyze(games):
    """Marque les jeux de la console : orphelins et versions perimees (dflags)."""
    bases = {g["tid"] for g in games if g["type"] == "BASE" and g["tid"]}
    owned = {}
    for g in games:
        if g["tid"] and g["version"] is not None:
            owned[g["tid"]] = max(owned.get(g["tid"], -1), g["version"])
    for g in games:
        fl = []
        if g["type"] in ("UPDATE", "DLC") and g["tid"] \
                and titleid.tid_base(g["tid"]) not in bases:
            fl.append("orphan")
        if g["tid"] and g["version"] is not None \
                and owned.get(g["tid"], -1) > g["version"]:
            fl.append("old")
        g["dflags"] = fl
    return games


def _invalider_cache():
    """Toute ecriture sur la console perime la vue en cache de son arborescence.

    Sans cela, un fichier qu'on vient d'envoyer resterait invisible jusqu'a
    l'expiration du cache — et l'utilisateur croirait le transfert rate.
    """
    try:
        from . import systems
        systems.vider_cache_arbre()
    except Exception:
        pass


def remove(paths, job):
    """Supprime des fichiers sur la console (confirmation cote client)."""
    job.set_total(len(paths))
    n = 0
    for p in paths:
        _run(["shell", "rm -f %s" % _q(p)])
        if remote_size(p) is None:
            job.log("Supprime : %s" % p.rsplit("/", 1)[-1])
            n += 1
        else:
            job.log("Echec suppression : %s" % p)
        job.tick()
    job.log("%d fichier(s) supprime(s) de la console." % n)


    _invalider_cache()

def reconcile(device_games, lib_files):
    """Marque chaque jeu de l'appareil : deja present en biblio ou non."""
    def key(f):
        if f.get("tid"):
            return (f["tid"], f.get("version"))
        return ("name", (f.get("name") or "").lower())

    have = {key(f) for f in lib_files}
    for g in device_games:
        g["in_library"] = key(g) in have
    return device_games


# ------------------------------------------------------------- transfert

def remote_size(remote):
    out = _shell("stat -c %%s %s 2>/dev/null" % _q(remote)).strip()
    return int(out) if out.isdigit() else None


def remote_rm(remote):
    _shell("rm -f %s" % _q(remote))


def _send_one(local, remote_dir, remote, size, verify_mode, job, attempts=2):
    """Envoie un fichier avec verification, nettoyage du reste tronque et
    nouvelle tentative. Renvoie 'ok' | 'fail' | 'gone' (console disparue)."""
    for attempt in range(1, attempts + 1):
        rc, out, err = _run(["push", str(local), remote_dir + "/"], timeout=7200)
        msg = ((err or out) or "").strip().splitlines()
        msg = msg[-1] if msg else ""

        if rc != 0 and state() != "device":
            return "gone"

        good = rc == 0
        if good and verify_mode == "size":
            good = remote_size(remote) == size
            if not good:
                msg = "taille incoherente apres transfert"
        elif good and verify_mode == "hash":
            job.set_detail("verification (sha1) de %s…" % Path(local).name[:40])
            good = remote_sha1(remote) == local_sha1(local)
            if not good:
                msg = "empreinte sha1 differente"

        if good:
            return "ok"

        # echec : on retire le fichier partiel pour ne pas laisser un jeu tronque
        remote_rm(remote)
        if attempt < attempts:
            job.log("  echec (%s) — nouvelle tentative…" % (msg or "inconnu"))
            time.sleep(2)
        else:
            job.log("  ECHEC definitif : %s" % (msg or "inconnu"))
    return "fail"


def remote_sha1(remote):
    out = _shell("sha1sum %s 2>/dev/null" % _q(remote), timeout=600).split()
    return out[0].lower() if out else None


def local_sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _human(b):
    if b is None:
        return "?"
    for u in ("o", "Kio", "Mio", "Gio", "Tio"):
        if b < 1024:
            return "%d %s" % (b, u) if u == "o" else "%.1f %s" % (b, u)
        b /= 1024
    return "%.1f Pio" % b


def pull(remote_paths, job):
    """Recupere des fichiers de l'appareil vers _import. Renvoie les chemins locaux."""
    config.IMPORT.mkdir(exist_ok=True)
    job.set_total(len(remote_paths))
    got = []
    for rp in remote_paths:
        if not job.checkpoint():
            job.log("Recuperation interrompue (%d fichier(s) recu(s))." % len(got))
            break
        name = rp.rsplit("/", 1)[-1]
        dest = config.IMPORT / name
        job.log("Recuperation : %s" % name)
        rc, out, err = _run(["pull", rp, str(dest)], timeout=7200)
        if rc == 0 and dest.exists():
            job.log("  recu (%.1f Mo)" % (dest.stat().st_size / 1048576))
            got.append(str(dest))
        else:
            msg = (err or out or "").strip().splitlines()
            job.log("  ECHEC : %s" % (msg[-1] if msg else "adb pull"))
        job.tick()
    return got


def push_generic(paths, target_dir, job, verify=True, incremental=True):
    """Envoie des ROMs (systemes non-Switch) dans un dossier unique de la console."""
    st = state()
    if st != "device":
        job.log("Aucun appareil adb pret (etat : %s)." % (st or "non connecte"))
        return
    base = target_dir.rstrip("/")
    if not base:
        job.log("Dossier cible inconnu sur la console.")
        return
    _shell("mkdir -p %s" % _q(base))

    # index des tailles deja presentes (pour l'incrementiel)
    present = {}
    if incremental:
        out = _shell("find %s -maxdepth 2 -type f -exec stat -c '%%s|%%n' {} \\; 2>/dev/null"
                     % _q(base), timeout=180)
        for line in out.splitlines():
            size, sep, pth = line.partition("|")
            if sep and size.strip().isdigit():
                present[pth.strip().rsplit("/", 1)[-1]] = int(size)

    todo = []
    for p in paths:
        f = Path(p)
        if f.is_file() and present.get(f.name) != f.stat().st_size:
            todo.append(f)
    nskip = len(paths) - len(todo)
    if nskip:
        job.log("%d fichier(s) deja sur la console, ignore(s)." % nskip)
    job.set_total(len(todo))
    if not todo:
        job.log("Rien a envoyer.")
        return

    okc = 0
    for f in todo:
        if not job.checkpoint():
            job.log("Transfert interrompu (%d/%d)." % (okc, len(todo)))
            return
        job.log("Envoi : %s" % f.name)
        res = _send_one(f, base, base + "/" + f.name, f.stat().st_size,
                        "size" if verify else "none", job)
        if res == "gone":
            job.log("Console deconnectee — transfert arrete (%d/%d envoyes)." % (okc, len(todo)))
            job.log("Rebranche-la : la reprise ne renverra que ce qui manque.")
            return
        if res == "ok":
            job.log("OK  %s" % f.name)
            okc += 1
        job.tick()
    job.log("Transfert termine (%d/%d) vers %s." % (okc, len(todo), base))


    _invalider_cache()

def _target_folder(path, layout, type_connu=None):
    """Sous-dossier cible d'un fichier selon le layout choisi.

    `type_connu` vient de la bibliotheque, qui a lu le conteneur : il prime
    toujours sur le nom du fichier, souvent incomplet ou trompeur.
    """
    if layout == "flat":
        return ""
    if layout == "game":  # miroir : le dossier de jeu source (parent)
        return str(path.parent.relative_to(config.ROOT))
    if type_connu in config.LAYOUT_FOLDER:
        return config.LAYOUT_FOLDER[type_connu]
    tid = titleid.from_name(path.name)  # dernier recours : le nom
    return config.LAYOUT_FOLDER[titleid.tid_type(tid) if tid else "INCONNU"]


def _console_index(device_dir):
    """Empreintes des jeux deja sur la console (title ID+version et nom de
    fichier), pour reperer un jeu present quel que soit son rangement."""
    keys = set()
    for g in find_games(device_dir):
        if g["tid"]:
            keys.add((g["tid"], g["version"]))
        keys.add(("name", g["name"].lower()))
    return keys


def ouvrir_droits(*chemins):
    """Rend accessibles a Eden les fichiers qu'adb vient d'ecrire chez lui.

    Un fichier pousse par adb appartient a l'utilisateur `shell`, en mode 644.
    Eden, qui tourne sous un autre UID, n'est donc qu'« autre » : il peut lire
    mais pas ecrire. Or il ouvre ses configs et ses contenus NAND en
    lecture-ecriture, et un refus le fait renoncer en silence, sans erreur
    visible. On elargit donc les droits apres chaque ecriture.
    """
    for chemin in chemins:
        if not chemin:
            continue
        q = _q(chemin)
        # Un dossier garde son bit d'execution, sans quoi on ne peut plus le
        # traverser : 777 pour les dossiers, 666 pour les fichiers.
        _shell("if [ -d %s ]; then "
               "find %s -type f -exec chmod 666 {} + 2>/dev/null; "
               "find %s -type d -exec chmod 777 {} + 2>/dev/null; "
               "else chmod 666 %s 2>/dev/null; fi" % (q, q, q, q))


    _invalider_cache()

# Codes Android de `dumpsys battery`. Les nombres bruts ne disent rien a
# l'ecran : on les traduit ici, une fois, plutot qu'a chaque affichage.
_ETAT_BATTERIE = {1: "inconnu", 2: "charge", 3: "decharge",
                  4: "pause", 5: "pleine"}
_SANTE_BATTERIE = {1: "inconnue", 2: "bonne", 3: "surchauffe", 4: "hors service",
                   5: "surtension", 6: "defaillante", 7: "froide"}


def batterie():
    """Etat de la batterie de la console, ou None si elle ne repond pas.

    Une console qui tombe en panne au milieu d'un transfert de 12 Go, c'est un
    fichier a renvoyer : autant voir son niveau avant de lancer.
    """
    sortie = _shell("dumpsys battery")
    if not sortie:
        return None
    champs = {}
    for ligne in sortie.splitlines():
        cle, _, val = ligne.partition(":")
        cle, val = cle.strip().lower(), val.strip()
        if cle and val:
            champs[cle] = val

    def entier(cle):
        try:
            return int(champs.get(cle, ""))
        except ValueError:
            return None

    niveau, echelle = entier("level"), entier("scale") or 100
    if niveau is None:
        return None
    pourcent = max(0, min(100, round(100 * niveau / echelle)))
    etat = _ETAT_BATTERIE.get(entier("status") or 1, "inconnu")
    # `status` vaut « decharge » meme branche sur certains appareils : la
    # presence d'une alimentation est plus fiable pour dire « en charge ».
    branchee = any(champs.get(c, "").lower() == "true"
                   for c in ("ac powered", "usb powered", "wireless powered"))
    if branchee and etat == "decharge":
        etat = "charge"
    temp = entier("temperature")
    return {
        "pourcent": pourcent,
        "etat": etat,
        "branchee": branchee,
        "sante": _SANTE_BATTERIE.get(entier("health") or 1, "inconnue"),
        # `temperature` est en dixiemes de degre
        "temperature": round(temp / 10.0, 1) if temp is not None else None,
        "volts": round((entier("voltage") or 0) / 1000.0, 2) or None,
    }


def integrity(path):
    """Motif de refus si le .nsp est tronque, sinon None.

    Un telechargement interrompu produit une archive qui annonce plus de
    contenu qu'elle n'en porte. Envoyee telle quelle, elle apparait dans Eden
    comme un jeu qui ne demarre jamais — mieux vaut la bloquer ici.
    """
    if Path(path).suffix.lower() != ".nsp":
        return None
    from . import nand  # tardif : nand importe device
    try:
        nand.read_pfs0(path)
    except nand.Incomplet as exc:
        return str(exc)
    except Exception:
        return None  # format inattendu : on ne bloque pas sur un simple doute
    return None


def plan(paths, device_dir, layout="type", incremental=False, types=None):
    """Construit le plan de transfert (quoi -> ou) a partir d'une liste de
    fichiers. Si incremental et l'appareil est branche, marque `skip` les jeux
    deja presents sur la console (par title ID/version ou nom, peu importe leur
    dossier)."""
    base = device_dir.rstrip("/")
    check = incremental and state() == "device"
    index = _console_index(device_dir) if check else set()
    reels = real_folders(device_dir)
    items = []
    for pth in paths:
        f = Path(pth)
        if not f.is_file() or f.suffix.lower() not in config.PLAYABLE:
            continue
        connu = (types or {}).get(str(f))
        folder = _target_folder(f, layout, connu)
        folder = reels.get(folder, folder)  # respecte la casse deja en place
        remote_dir = base + ("/" + folder if folder else "")
        remote = remote_dir + "/" + f.name
        size = f.stat().st_size
        tid = titleid.from_name(f.name)
        key = (tid, titleid.version_from_name(f.name)) if tid else ("name", f.name.lower())
        skip = bool(check and (key in index or remote_size(remote) == size))
        items.append({
            "local": str(f), "name": f.name,
            # le type connu de la bibliotheque prime : le nom ment parfois
            "type": connu or (titleid.tid_type(tid) if tid else "INCONNU"),
            "size": size, "folder": folder or "/",
            "remote_dir": remote_dir, "remote": remote, "skip": skip,
            "broken": integrity(f),
        })
    return items


def push(paths, device_dir, job, verify_mode="size", layout="type", incremental=True, types=None):
    """Envoie les .nsp/.xci, ranges selon le layout, avec debit/ETA et
    verification (none | size | hash). En incremental, saute l'existant identique."""
    st = state()
    if st != "device":
        job.log("Aucun appareil adb pret (etat : %s)." % (st or "non connecte"))
        job.log("Branche le handheld en USB, autorise le debogage, puis reessaie.")
        return

    items = plan(paths, device_dir, layout, incremental, types)
    casses = [it for it in items if it.get("broken")]
    todo = [it for it in items if not it["skip"] and not it.get("broken")]
    nskip = sum(1 for it in items if it["skip"] and not it.get("broken"))
    job.set_total(len(todo))
    if nskip:
        job.log("%d fichier(s) deja presents a l'identique, ignore(s)." % nskip)
    for it in casses:
        job.log("Refuse : %s est incomplet — %s" % (it["name"], it["broken"]), "error")
    if casses:
        job.log("Un fichier incomplet apparait dans Eden comme un jeu qui ne "
                "demarre pas. Retelecharge-le, puis relance l'envoi.", "warn")
    if not todo:
        job.log("Rien a envoyer : la console est deja a jour.")
        return

    total_bytes = sum(it["size"] for it in todo)
    done_bytes = 0
    start = time.time()
    okc, made = 0, set()

    # On note ce qu'il reste a faire : si le transfert s'arrete, l'utilisateur
    # n'a pas a retrouver la meme selection pour reprendre.
    from . import transferts
    transferts.demarrer([it["local"] for it in todo], device_dir, "switch")

    for it in todo:
        if not job.checkpoint():
            job.log("Transfert interrompu (%d/%d envoyes)." % (okc, len(todo)))
            job.log("La reprise est proposee au prochain envoi.", "warn")
            return
        if it["remote_dir"] not in made:
            _shell("mkdir -p %s" % _q(it["remote_dir"]))
            made.add(it["remote_dir"])
        job.log("Envoi : %s  ->  %s/" % (it["name"], it["folder"]))
        res = _send_one(it["local"], it["remote_dir"], it["remote"], it["size"],
                        verify_mode, job)
        if res == "gone":
            job.log("Console deconnectee — transfert arrete (%d/%d envoyes)."
                    % (okc, len(todo)))
            job.log("Rebranche-la : la reprise ne renverra que ce qui manque.")
            job.set_detail("")
            return
        if res == "ok":
            job.log("OK  %s" % it["name"])
            transferts.marquer_fait(it["local"])
            okc += 1
            done_bytes += it["size"]
        job.tick()

        elapsed = max(0.1, time.time() - start)
        speed = done_bytes / elapsed
        remaining = total_bytes - done_bytes
        eta = remaining / speed if speed > 0 else 0
        job.set_detail("%s/s · reste %s (~%d min)"
                       % (_human(int(speed)), _human(remaining), round(eta / 60)))

    job.set_detail("")
    job.log("Transfert termine (%d/%d) vers %s." % (okc, len(todo), device_dir))
    if okc == len(todo):
        transferts.terminer()          # rien a reprendre
    _invalider_cache()
