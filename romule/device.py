"""Couche adb : detection de la console, exploration, import (pull) et push.

Target: an Android handheld running Eden, plugged in over USB with debugging
enabled. The `parse_*` functions and `reconcile` are pure (testable with no
device); everything that talks to adb goes through `_run` / `_shell`.
"""

import hashlib
import os
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

def _binaire_adb():
    """Path of the adb binary to run, or None when there is none.

    `ROMULE_ADB` comes first. It is what lets the test suite point at a fake
    adb, and therefore FIX the console's state instead of suffering it: without
    it, the tests gave three different results depending on whether a device
    was plugged in, absent, or plugged in but offline. That is exactly what
    left five French strings on the home screen for weeks — the "no console"
    branch never rendered on the machine running the tests.

    A path that points at nothing means "no adb": the simplest way to replay a
    machine with no adb at all.
    """
    impose = config.env("ADB").strip()
    if impose:
        return impose if os.path.exists(impose) else None
    return shutil.which("adb")


def adb_available():
    return _binaire_adb() is not None


# Serial of the targeted device. Useful when USB and Wi-Fi are connected at the
# same time: without it adb refuses to act ("more than one device").
_SERIAL = None


def set_target(serial):
    global _SERIAL
    _SERIAL = serial or None


def _run(args, timeout=60, targeted=True):
    """Return (returncode, stdout, stderr). `targeted` aims at the chosen device."""
    binaire = _binaire_adb()
    if not binaire:
        return 1, "", "adb introuvable"
    cmd = [binaire]
    if targeted:
        # Pick the target ON DEMAND. Without this, a process's first command
        # went out without `-s`: with two transports attached (a console linked
        # over Wi-Fi often exposes two, IP and mDNS), adb answered "more than
        # one device" and _shell returned an empty string — a failure that
        # passed for an empty folder.
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
    """Run a command in the device's shell, return stdout."""
    rc, out, _ = _run(["shell", cmd], timeout=timeout)
    return out if rc == 0 else ""


def _q(path):
    """Quote a path for the remote shell."""
    return "'" + str(path).replace("'", "'\\''") + "'"


# ------------------------------------------------------------- detection

def is_wireless(serial):
    """Does the link go over the network?

    Two forms exist: "192.168.1.42:5555" for a classic `adb connect`, and
    "adb-XXXX-YYYY._adb-tls-connect._tcp" for an adb-TLS connection announced
    over mDNS. The second contains NO colon: testing only that character made
    it pass for USB, and the tool announced a cable was plugged in while
    everything went over Wi-Fi.
    """
    s = str(serial or "")
    return ":" in s or "_adb-tls-" in s or s.endswith("._tcp")


def _pick(devs, prefer=None):
    """Pick the device to drive: the requested one, else USB (2 to 5 times
    faster and steadier than Wi-Fi), else Wi-Fi."""
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
    """How the console is linked: {'kind': 'wifi'|'usb'|None, 'serial', 'name'}."""
    devs = devices()
    d = _pick(devs, _SERIAL)
    if not d:
        return {"kind": None, "serial": None,
                "state": devs[0].get("state") if devs else None}
    set_target(d["serial"])
    return {"kind": "wifi" if is_wireless(d["serial"]) else "usb",
            "serial": d["serial"], "state": "device",
            "depuis": _depuis(d["serial"])}


# How long this link has held. Measured from the first time we see this serial:
# adb does not provide the information, and it says far more than "connected" —
# a wireless link that just came back is not as trustworthy as one established
# two hours ago.
_VUS = {}


def _depuis(serial):
    import time as _t
    if serial not in _VUS:
        _VUS[serial] = _t.time()
    # forget vanished links, otherwise the duration would be wrong on return
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


# ---------------------------------------------------------------- wireless

def device_ip():
    """The console's Wi-Fi IP address (as it sees itself)."""
    out = _shell("ip -f inet addr show wlan0 2>/dev/null")
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
    if m:
        return m.group(1)
    out = _shell("ip route 2>/dev/null")
    m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else None


def discover():
    """Connection addresses announced by consoles in wireless debugging."""
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
    """Connect to a console over the network. Returns (ok, message)."""
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
    """Wireless pairing (Android 11+). Returns (ok, message)."""
    if not addr or not code:
        return (False, "adresse ou code manquant")
    # This function bypassed `_run`: it ran a hard-coded "adb", with no
    # existence guard. It was therefore the one call `ROMULE_ADB` would have
    # missed, and the one to raise when adb is absent.
    binaire = _binaire_adb()
    if not binaire:
        return (False, "adb introuvable")
    try:
        p = subprocess.run([binaire, "pair", addr, str(code)],
                           capture_output=True, text=True, timeout=60)
        msg = (p.stdout + p.stderr).strip().splitlines()
        msg = msg[-1] if msg else ""
        return ("successfully" in msg.lower() or p.returncode == 0, msg)
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, str(exc))


def switch_to_wifi(port=5555):
    """Move a USB-connected console over to Wi-Fi. Returns (ok, addr, msg)."""
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
    time.sleep(1.5)                     # the device restarts its adb service
    addr = "%s:%d" % (ip, port)
    ok, msg = connect(addr)
    return (ok, addr if ok else None, msg)


def open_url(url):
    """Open an address in the console's browser. Returns (ok, message)."""
    rc, out, err = _run(["shell", "am", "start", "-a", "android.intent.action.VIEW",
                         "-d", url], timeout=30)
    txt = (out + err).strip()
    if rc == 0 and "error" not in txt.lower():
        return (True, "")
    return (False, (txt.splitlines() or ["ouverture impossible"])[-1])


def info():
    """Identity card of the connected console."""
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
    """(total_bytes, free_bytes) from a `df -k` output, otherwise (None, None)."""
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
    """A path's volume root (to measure space, even when the target folder does
    not exist yet)."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "storage":
        if parts[1] == "emulated":
            return "/storage/emulated/%s" % (parts[2] if len(parts) >= 3 else "0")
        return "/storage/%s" % parts[1]
    return "/" + parts[0] if parts else path


def free_of(path):
    """Free bytes on the volume holding `path`, or None."""
    return _df(volume_root(path))[1]


def volumes():
    """Storage volumes: internal plus SD card(s), with free space."""
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
    """Contents of a folder on the device (folders first)."""
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
    """Game files under a folder on the device.

    `exts` allows querying a system other than the Switch (.iso, .chd…):
    without it, the other consoles had no way of knowing what was already in
    place, and inherited a stateless view.
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
    """Guess the games root: the longest common ancestor of every Switch file
    found on the device (handles a flat folder as well as per-game or per-type
    trees)."""
    if state() != "device":
        return None

    def ancetre(dirs):
        common = []
        # `strict=False` spelled out: stopping at the shortest path is exactly
        # what a common ancestor should do.
        for parts in zip(*[d.split("/") for d in dirs], strict=False):
            if len(set(parts)) == 1:
                common.append(parts[0])
            else:
                break
        return "/".join(common) or dirs[0]

    # A common ancestor computed across ALL volumes at once yields "/storage"
    # as soon as games exist both on the SD card and internally — a path that
    # points at nothing. So we reason volume by volume, and keep the one
    # carrying the most games.
    best, best_n = None, 0
    for v in volumes():
        cmd = ("find %s -maxdepth 7 -type f %s 2>/dev/null"
               % (_q(v["path"]), _GAME_FIND))
        dirs = [l.strip().rsplit("/", 1)[0]
                for l in _shell(cmd, timeout=120).splitlines() if l.strip()]
        if not dirs or len(dirs) <= best_n:
            continue
        racine = ancetre(dirs)
        # never higher than the volume itself
        if not racine.startswith(v["path"].rstrip("/")):
            racine = v["path"].rstrip("/")
        best, best_n = racine, len(dirs)
    return best


def _tree_folders():
    return sorted(set(config.LAYOUT_FOLDER.values()))  # GAMES, UPDATE, DLC


def real_folders(device_dir):
    """Each type folder's real name on the console: {"GAMES": "Games", ...}.

    The SD card is case-insensitive: a folder created long ago as "Games"
    answers to "GAMES" just as well. Shell commands cope, but our path
    comparisons in Python match nothing any more — a check can then run on
    emptiness and look fine. Worse, the "do not delete the type folders" guard
    stops recognising them. So we read the names as they really are.
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
    """Whether the layout subfolders (GAMES/UPDATE/DLC) exist on the console."""
    base = device_dir.rstrip("/")
    if state() != "device" or not base:
        return {}
    out = {}
    for name in _tree_folders():
        r = _shell("[ -d %s ] && echo 1 || echo 0" % _q(base + "/" + name)).strip()
        out[name] = r.endswith("1")
    return out


def make_tree(device_dir):
    """Create the missing layout subfolders. Returns the new state."""
    base = device_dir.rstrip("/")
    if state() == "device" and base:
        for name in _tree_folders():
            _shell("mkdir -p %s" % _q(base + "/" + name))
    _invalider_cache()
    return tree_status(device_dir)


def organize(device_dir, job, types=None):
    """Tidy the console: every file goes to GAMES/UPDATE/DLC by type (even if
    it sat in a per-game folder), then empty folders are removed."""
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
        # The library's known type wins: it comes from the file's contents,
        # whereas here we only have the name — and a name sometimes lies
        # (truncated title ID, missing one, or announcing a base when it is an
        # update).
        typ = (types or {}).get(g["name"])
        if typ not in config.LAYOUT_FOLDER:
            typ = titleid.tid_type(g["tid"]) if g["tid"] else "INCONNU"
        folder = reels[config.LAYOUT_FOLDER[typ]]
        dst = "%s/%s/%s" % (base, folder, g["name"])
        # already in the right place (directly under the right type folder)?
        if g["path"] == dst:
            job.tick()
            continue
        _shell("mv %s %s" % (_q(g["path"]), _q(dst)))
        job.log("Range : %s -> %s/" % (g["name"], folder))
        moved += 1
        job.tick()
    # remove per-game folders that became empty (except GAMES/UPDATE/DLC)
    keep = " ".join("-not -name %s" % _q(tf) for tf in sorted(set(reels.values())))
    _shell("find %s -mindepth 1 -type d -empty %s -delete 2>/dev/null" % (_q(base), keep))
    _shell("find %s -mindepth 1 -type d -empty %s -delete 2>/dev/null" % (_q(base), keep))
    job.log("%d fichier(s) range(s) en GAMES / UPDATE / DLC sur la console." % moved)


    _invalider_cache()

def analyze(games):
    """Flag the console's games: orphans and stale versions (dflags)."""
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
    """Any write to the console expires the cached view of its tree.

    Without this, a file you just pushed would stay invisible until the cache
    expired — and the user would think the transfer had failed.
    """
    try:
        from . import systems
        systems.clear_tree_cache()
    except Exception:
        pass


def remove(paths, job):
    """Delete files on the console (confirmation happens client-side)."""
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
    """Flag each of the device's games: already in the library or not."""
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
    """Send one file with verification, cleanup of the truncated remains and a
    retry. Returns 'ok' | 'fail' | 'gone' (console vanished)."""
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

        # failure: remove the partial file so no truncated game is left behind
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
    # A CORRUPTION digest: it answers "did the copy arrive whole?", not "did
    # someone substitute the file?". No cryptographic property is expected
    # here.
    h = hashlib.sha1(usedforsecurity=False)
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
    """Fetch files from the device into _import. Returns the local paths."""
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
    """Send ROMs (non-Switch systems) into a single folder on the console."""
    st = state()
    if st != "device":
        job.log("Aucun appareil adb pret (etat : %s)." % (st or "non connecte"))
        return
    base = target_dir.rstrip("/")
    if not base:
        job.log("Dossier cible inconnu sur la console.")
        return
    _shell("mkdir -p %s" % _q(base))

    # index of the sizes already present (for the incremental mode)
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
    """A file's target subfolder for the chosen layout.

    `type_connu` comes from the library, which read the container: it always
    wins over the file name, often incomplete or misleading.
    """
    if layout == "flat":
        return ""
    if layout == "game":  # mirror: the source per-game folder (parent)
        return str(path.parent.relative_to(config.LUDO))
    if type_connu in config.LAYOUT_FOLDER:
        return config.LAYOUT_FOLDER[type_connu]
    tid = titleid.from_name(path.name)  # last resort: the name
    return config.LAYOUT_FOLDER[titleid.tid_type(tid) if tid else "INCONNU"]


def _console_index(device_dir):
    """Fingerprints of the games already on the console (title ID+version and
    file name), to spot a game present whatever folder it is filed in."""
    keys = set()
    for g in find_games(device_dir):
        if g["tid"]:
            keys.add((g["tid"], g["version"]))
        keys.add(("name", g["name"].lower()))
    return keys


def ouvrir_droits(*chemins):
    """Make the files adb just wrote reachable by Eden.

    A file pushed by adb belongs to the `shell` user, mode 644. Eden, running
    under another UID, is therefore merely "other": it can read but not write.
    Yet it opens its configs and its NAND contents read-write, and a refusal
    makes it give up silently, with no visible error. So we widen the
    permissions after every write.
    """
    for chemin in chemins:
        if not chemin:
            continue
        q = _q(chemin)
        # A folder keeps its execute bit, without which it can no longer be
        # traversed: 777 for folders, 666 for files.
        _shell("if [ -d %s ]; then "
               "find %s -type f -exec chmod 666 {} + 2>/dev/null; "
               "find %s -type d -exec chmod 777 {} + 2>/dev/null; "
               "else chmod 666 %s 2>/dev/null; fi" % (q, q, q, q))


    _invalider_cache()

# Android codes from `dumpsys battery`. The raw numbers say nothing on screen:
# we translate them here, once, rather than on every render.
_ETAT_BATTERIE = {1: "inconnu", 2: "charge", 3: "decharge",
                  4: "pause", 5: "pleine"}
_SANTE_BATTERIE = {1: "inconnue", 2: "bonne", 3: "surchauffe", 4: "hors service",
                   5: "surtension", 6: "defaillante", 7: "froide"}


def batterie():
    """The console's battery state, or None when it does not answer.

    A console that dies in the middle of a 12 GB transfer means a file to send
    again: better to see its level before starting.
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
    # `status` reads "discharging" even when plugged in on some devices: the
    # presence of a power source is a more reliable way to say "charging".
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
        # `temperature` is in tenths of a degree
        "temperature": round(temp / 10.0, 1) if temp is not None else None,
        "volts": round((entier("voltage") or 0) / 1000.0, 2) or None,
    }


def integrity(path):
    """A reason to refuse when the .nsp is truncated, otherwise None.

    An interrupted download produces an archive announcing more content than it
    carries. Sent as-is, it shows up in Eden as a game that never starts —
    better to stop it here.
    """
    if Path(path).suffix.lower() != ".nsp":
        return None
    from . import nand  # tardif : nand importe device
    try:
        nand.read_pfs0(path)
    except nand.Incomplet as exc:
        return str(exc)
    except Exception:
        return None  # unexpected format: we do not block on a mere doubt
    return None


def plan(paths, device_dir, layout="type", incremental=False, types=None):
    """Build the transfer plan (what -> where) from a list of files. When
    incremental and the device is connected, marks `skip` for games already on
    the console (by title ID/version or by name, whatever folder they are
    in)."""
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
        folder = reels.get(folder, folder)  # honour the casing already in place
        remote_dir = base + ("/" + folder if folder else "")
        remote = remote_dir + "/" + f.name
        size = f.stat().st_size
        tid = titleid.from_name(f.name)
        key = (tid, titleid.version_from_name(f.name)) if tid else ("name", f.name.lower())
        skip = bool(check and (key in index or remote_size(remote) == size))
        items.append({
            "local": str(f), "name": f.name,
            # the library's known type wins: the name sometimes lies
            "type": connu or (titleid.tid_type(tid) if tid else "INCONNU"),
            "size": size, "folder": folder or "/",
            "remote_dir": remote_dir, "remote": remote, "skip": skip,
            "broken": integrity(f),
        })
    return items


def push(paths, device_dir, job, verify_mode="size", layout="type", incremental=True, types=None):
    """Send the .nsp/.xci files, filed by layout, with rate/ETA and
    verification (none | size | hash). Incremental skips identical files."""
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

    # We record what is left to do: if the transfer stops, the user does not
    # have to rebuild the same selection to resume.
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
        transferts.terminer()          # nothing to resume
    _invalider_cache()
