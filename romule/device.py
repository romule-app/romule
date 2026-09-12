"""Couche adb : detection de la console, exploration, import (pull) et push.

Target: an Android handheld running Eden, plugged in over USB with debugging
enabled. The `parse_*` functions and `reconcile` are pure (testable with no
device); everything that talks to adb goes through `_run` / `_shell`.
"""

import hashlib
import itertools
import os
import re
import select
import shutil
import socket
import subprocess
import time
from pathlib import Path

from . import config, titleid
from . import messages
from . import langue

SD_RE = re.compile(r"^[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$")
_GAME_FIND = (r"\( -iname '*.nsp' -o -iname '*.xci' "
              r"-o -iname '*.nsz' -o -iname '*.xcz' \)")


# ------------------------------------------------------------- appels adb bruts

def _adb_binary():
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
    return _adb_binary() is not None


# adb keeps its identity — the key the console TRUSTS after pairing — in
# `$ANDROID_USER_HOME`, or in `$HOME/.android` when that is unset. In a
# container, `$HOME` belongs to the image: rebuilding for an update generates a
# brand-new key, the console no longer recognises it, and the user is asked to
# pair again for no reason they can see. It looks, from the outside, exactly
# like "the console will not reconnect since the update".
#
# So the key lives beside the rest of the persisted state, in the data folder.
# An installation that already had one keeps it: we move it across on the first
# start rather than make this fix cost one last re-pairing.
_CLES_POSEES = [False]


def _cles_adb():
    # Not conditioned on which adb BINARY is in use: where the key lives has
    # nothing to do with that, and making it depend on `ROMULE_ADB` would have
    # left the relocation silent for anyone naming their own adb.
    if _CLES_POSEES[0]:
        return
    _CLES_POSEES[0] = True
    if os.environ.get("ANDROID_USER_HOME"):
        return                       # deliberately set: we do not override it
    cible = config.ROOT / ".android"
    try:
        cible.mkdir(parents=True, exist_ok=True)
        os.chmod(cible, 0o700)
    except OSError:
        return
    os.environ["ANDROID_USER_HOME"] = str(cible)
    if (cible / "adbkey").exists():
        return
    ancien = Path(os.path.expanduser("~")) / ".android"
    for nom in ("adbkey", "adbkey.pub"):
        src = ancien / nom
        try:
            if src.is_file():
                shutil.copy2(str(src), str(cible / nom))
        except OSError:
            pass


# Serial of the targeted device. Useful when USB and Wi-Fi are connected at the
# same time: without it adb refuses to act ("more than one device").
_SERIAL = None


def set_target(serial):
    global _SERIAL
    _SERIAL = serial or None


def _run(args, timeout=60, targeted=True):
    """Return (returncode, stdout, stderr). `targeted` aims at the chosen device."""
    binaire = _adb_binary()
    if not binaire:
        return 1, "", "adb introuvable"
    _cles_adb()
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


# The last state we saw, so that a CHANGE can be told from a reading. `state()`
# is called several times a second by the interface's polling: notifying on the
# state rather than on the transition would be a message per poll.
#
# `_UNSEEN` and not `None`: `None` is a real state — no console at all — and
# using it as "not yet looked" would announce a disconnection at startup to
# everyone who has no console plugged in.
_UNSEEN = object()
_LAST_STATE = [_UNSEEN]


def _announce(new):
    """Say it once, when it changes. Never raises: a notification is a
    convenience, and a console reading must not fail because Discord is down."""
    was = _LAST_STATE[0]
    _LAST_STATE[0] = new
    if was is _UNSEEN or was == new:
        return                       # first reading, or nothing moved
    try:
        from . import notify
        if new == "device":
            notify.send("console_liee", "Romule", "Console connectee.", "ok")
        elif was == "device":
            notify.send("console_liee", "Romule", "Console deconnectee.", "warn")
    except Exception:
        pass


def state(prefer=None):
    """'device', 'unauthorized', 'offline'... ou None. Gere plusieurs appareils."""
    devs = devices()
    if not devs:
        _announce(None)
        return None
    d = _pick(devs, prefer)
    if d:
        set_target(d["serial"])
        _announce("device")
        return "device"
    set_target(None)
    etat = devs[0].get("state")
    _announce(etat)
    return etat


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
            "depuis": _since(d["serial"])}


# How long this link has held. Measured from the first time we see this serial:
# adb does not provide the information, and it says far more than "connected" —
# a wireless link that just came back is not as trustworthy as one established
# two hours ago.
_SEEN = {}


def _since(serial):
    import time as _t
    if serial not in _SEEN:
        _SEEN[serial] = _t.time()
    # forget vanished links, otherwise the duration would be wrong on return
    vivants = {d["serial"] for d in devices()}
    for s in list(_SEEN):
        if s not in vivants:
            del _SEEN[s]
    return int(_t.time() - _SEEN.get(serial, _t.time()))


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


def usb_state():
    """What the USB port has to say, for the step that asks how to connect.

    Four answers and no more, because the card showing them has room for one
    line: ready (and which console), waiting for the prompt on the console's
    screen, nothing plugged in, or a port this machine cannot see at all.

    The last one is the honest answer inside a container: `/dev/bus/usb` is not
    mapped unless the operator said so, and a card inviting you to plug a cable
    in there is an invitation to fail.
    """
    from . import config
    if not adb_available():
        return {"etat": "invisible", "nom": ""}
    if config.in_container() and not os.path.isdir("/dev/bus/usb"):
        return {"etat": "invisible", "nom": ""}
    filaires = [d for d in devices() if not is_wireless(d.get("serial") or "")]
    pret = [d for d in filaires if d.get("state") == "device"]
    if pret:
        d = pret[0]
        return {"etat": "pret",
                "nom": d.get("model") or d.get("device") or d.get("serial") or ""}
    if any(d.get("state") == "unauthorized" for d in filaires):
        return {"etat": "autorisation", "nom": ""}
    return {"etat": "aucune", "nom": ""}


def _hote(addr):
    return str(addr or "").rsplit(":", 1)[0]


# The range Android picks its wireless-debugging port from, and the shape of the
# sweep.
#
# `poll`, never `select`: `select.select()` fails with
# `ValueError: filedescriptor out of range` as soon as ANY descriptor is 1024 or
# above, and in a running server — an HTTP socket, its clients, the log files —
# eight hundred fresh sockets land far above that. The first version caught that
# ValueError and moved on, so the sweep found nothing at all, silently, in the
# only process where it mattered. It worked perfectly when tried on its own,
# which is exactly how a defect like this survives.
_PLAGE_ADB = (30000, 65535)


def _ordre_des_ports(debut, fin, autour):
    """The ports to try, nearest `autour` first.

    Android hands the pairing port and the connection port out of the same
    ephemeral pool, moments apart: they land close to each other far more often
    than chance would put them. Sweeping outward from the one we know turns a
    search of thirty-five thousand ports into one that usually answers in the
    first few hundred.
    """
    if not autour or not (debut <= autour <= fin):
        return range(debut, fin + 1)

    def suite():
        yield autour
        for ecart in range(1, max(autour - debut, fin - autour) + 1):
            bas, haut = autour - ecart, autour + ecart
            if bas >= debut:
                yield bas
            if haut <= fin:
                yield haut
    return suite()


def _hote_scrutable(hote):
    """Only a PRIVATE address may be swept.

    The sweep exists to find a handheld's connection port, and a handheld sits
    on the local network by definition. Without this bound the server was a
    port scanner by proxy: `/api/wifi-pair` takes the target from the client,
    and on an unclaimed installation — open to everybody by design, and loudly
    said to be — anybody who could reach the page could have this host sweep
    thirty-five thousand TCP ports of any machine on the internet.

    `is_private` covers RFC 1918, loopback and link-local; 100.64.0.0/10 is
    added by hand for the Tailscale-style overlays it serves, which Python
    counts as neither private nor global.
    """
    import ipaddress
    try:
        ip = ipaddress.ip_address(str(hote or "").strip())
    except ValueError:
        return False                       # a hostname is not a console screen
    return ip.is_private or ip in ipaddress.ip_network("100.64.0.0/10")


def ports_ouverts(hote, debut=None, fin=None, budget=8.0, lot=800, delai=0.25,
                  autour=None):
    """The TCP ports answering on this host, within the wireless-debugging range.

    Why this exists
    ---------------
    Android announces its wireless-debugging port over mDNS, and multicast does
    not cross a Docker bridge. From a container the port therefore cannot be
    discovered — and the interface had no answer but to send the reader back to
    the console for a second number, after they had already copied one. That is
    the step people give up on.

    So we look. The host is one the user has just typed and paired with, on
    their own network, and the range is the ephemeral one Android picks from —
    not a sweep of anything else. It is bounded in TIME rather than in scope: a
    connection that has not answered within `budget` seconds is not the console
    someone is waiting on.
    """
    if not hote or not _hote_scrutable(hote):
        return []
    debut = _PLAGE_ADB[0] if debut is None else debut
    fin = _PLAGE_ADB[1] if fin is None else fin
    ouverts = []
    depart = time.monotonic()
    restants = iter(_ordre_des_ports(debut, fin, autour))
    while time.monotonic() - depart < budget:
        paquet = list(itertools.islice(restants, lot))
        if not paquet:
            break
        prises, sondeur = {}, select.poll()
        for p in paquet:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(False)
            try:
                s.connect_ex((hote, p))
            except OSError:
                s.close()
                continue
            prises[s.fileno()] = (s, p)
            sondeur.register(s.fileno(), select.POLLOUT)
        limite = time.monotonic() + delai
        while prises and time.monotonic() < limite:
            restant = max(0.0, limite - time.monotonic())
            for fd, _ in sondeur.poll(restant * 1000):
                paire = prises.pop(fd, None)
                if not paire:
                    continue
                s, p = paire
                sondeur.unregister(fd)
                try:
                    if s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
                        ouverts.append(p)
                except OSError:
                    pass
                s.close()
        for s, _ in prises.values():
            s.close()
        # Answered already: no reason to sweep the rest of the range.
        if ouverts:
            break
    return ouverts


def candidats(adresse):
    """Addresses worth trying for this console, most likely first.

    FIRST of all: the address that was just paired with, port included.

    On a good many devices the pairing port and the connection port are the
    same number, and this code threw it away on its first line — `_hote()`
    strips the port before anything else looks at it. So the one candidate that
    was certain to be worth a try was the only one never tried, and the wizard
    went on asking for a port the reader had already typed, which then worked
    when typed a second time. Every other source here was written to work
    around an obvious one that was missing.

    Then, in order of how much they know:

      * what adb already lists for that host — a link from a previous session,
        possibly `offline`, whose port is still the right one. The connection
        port holds as long as wireless debugging stays on, so this is what makes
        a reconnection after a restart work without asking anything;
      * what the consoles announce over mDNS, FILTERED to this host;
      * the rest of what mDNS announced, last, for the case where the pairing
        address and the connection address differ by more than their port.
    """
    appairee = str(adresse or "").strip()
    hote = _hote(appairee)
    vus, annonces = [], discover()
    if ":" in appairee and appairee.rsplit(":", 1)[1].isdigit():
        vus.append(appairee)
    for d in devices():
        s = d.get("serial") or ""
        if ":" in s and _hote(s) == hote and s not in vus:
            vus.append(s)
    memes = [a for a in annonces if _hote(a) == hote and a not in vus]
    autres = [a for a in annonces if _hote(a) != hote]
    # Last, and only last: 5555 is the port a console listens on when someone
    # ran `adb tcpip 5555`, not the one wireless debugging picks — that one is
    # random. It costs a single refused round trip when it is wrong, and it is
    # the whole answer when it is right.
    defaut = ["%s:5555" % hote] if hote and "%s:5555" % hote not in vus else []
    return vus + memes + autres + defaut


def relier_apres_appairage(hote, attente=6.0, scruter=True,
                           budget_scrutation=8.0):
    """Connect the console just paired, without asking for its port.

    Returns (address, tried) — the address that worked, or None.

    Pairing and connecting use two different ports, and only the console's own
    screen shows the second one. Asking for it is the step people gave up on:
    they had just copied an address and a code, and were sent back to the
    console for a third number.

    So it is not asked for unless everything else has failed. adb often knows
    it already; and when it does not — the ordinary case in a container, where
    mDNS reaches nothing — the host the user has just paired with is asked
    directly, by looking at which of its ports answer.
    """
    lien = connection()
    if lien.get("kind") == "wifi" and lien.get("serial"):
        return (lien["serial"], [])
    essayees = []
    for addr in candidats(hote)[:4]:
        essayees.append(addr)
        ok, _ = connect(addr, attente=attente)
        if ok:
            return (addr, essayees)
    if not scruter:
        return (None, essayees)
    # Closest to the PAIRING port first. Android hands both out of the same
    # ephemeral pool, moments apart, so they land near each other far more often
    # than chance would put them — and a console can answer on a dozen ports,
    # of which only one is adb.
    #
    # A handful at most: each wrong one costs an adb round trip, and beyond a
    # dozen we are guessing rather than looking.
    try:
        repere = int(str(hote).rsplit(":", 1)[1])
    except (IndexError, ValueError):
        repere = 0
    trouves = ports_ouverts(_hote(hote), budget=budget_scrutation,
                            autour=repere or None)
    if repere:
        trouves.sort(key=lambda p: abs(p - repere))
    for port in trouves[:12]:
        addr = "%s:%d" % (_hote(hote), port)
        if addr in essayees:
            continue
        essayees.append(addr)
        ok, _ = connect(addr, attente=attente)
        if ok:
            return (addr, essayees)
    return (None, essayees)


def _etat_de(addr):
    """The state adb gives this address, or None when it lists it at all."""
    for d in devices():
        if d.get("serial") == addr:
            return d.get("state")
    return None


def _attendre_pret(addr, delai=8.0):
    """Poll until the address is usable, or give up. Returns the last state.

    `adb connect` answers before the link is usable: the entry shows up as
    `offline` for a moment and settles a second or two later. Reading `adb
    devices` once, straight after, therefore says "offline" about a connection
    that was going to work.
    """
    import time as _t
    fin = _t.monotonic() + delai
    etat = None
    while _t.monotonic() < fin:
        etat = _etat_de(addr)
        if etat == "device":
            return etat
        _t.sleep(0.4)
    return etat


def connect(addr, timeout=20, attente=8.0):
    """Connect to a console over the network. Returns (ok, message).

    adb's word is not taken for it. `adb connect` prints "connected to
    192.168.1.42:5555" and exits 0 in cases where the console then sits at
    `offline` or `unauthorized` — states `_pick` rightly refuses to drive. The
    interface said `Console connectée sans fil.`, the header showed no console,
    and the settings went on asking for the configuration that had just been
    done. Three screens disagreeing, and the one that was lying was the toast.

    So the link is CHECKED, not announced: usable means adb lists this address
    as `device`.
    """
    if not addr:
        return (False, messages.ADRESSE_MANQUANTE)

    def _tenter():
        rc, out, err = _run(["connect", addr], timeout=timeout, targeted=False)
        lignes = (out + err).strip().splitlines()
        return lignes[-1] if lignes else ""

    msg = _tenter()
    if "connected" not in msg.lower() or "cannot" in msg.lower():
        # A flat refusal right after a pairing is the ordinary case, not a
        # verdict: adbd on the console is re-binding its connection port, and
        # for a second or two it answers nothing. Giving up there is what made
        # people type the very same address again and watch it work — which is
        # a bug report where the reader has already done the debugging.
        time.sleep(1.2)
        msg = _tenter()
        if "connected" not in msg.lower() or "cannot" in msg.lower():
            return (False, msg or messages.D_LIEN_ABSENT)

    etat = _attendre_pret(addr, attente)
    if etat != "device":
        # `offline` after a successful `connect` is adb holding a stale entry
        # for that address — a previous session the console has forgotten.
        # Dropping it and asking again is what clears it, and it costs one
        # round trip.
        _run(["disconnect", addr], timeout=10, targeted=False)
        _run(["connect", addr], timeout=timeout, targeted=False)
        etat = _attendre_pret(addr, attente)

    if etat == "device":
        set_target(addr)
        return (True, msg or ("connecte a %s" % addr))
    if etat == "unauthorized":
        return (False, messages.D_LIEN_NON_AUTORISE)
    if etat == "offline":
        return (False, messages.D_LIEN_HORS_LIGNE)
    return (False, messages.D_LIEN_ABSENT)


def disconnect(addr=None):
    _run(["disconnect"] + ([addr] if addr else []), timeout=15, targeted=False)
    set_target(None)


def pair(addr, code):
    """Wireless pairing (Android 11+). Returns (ok, message)."""
    if not addr or not code:
        return (False, messages.ADRESSE_OU_CODE_MANQUANT)
    # This function bypassed `_run`: it ran a hard-coded "adb", with no
    # existence guard. It was therefore the one call `ROMULE_ADB` would have
    # missed, and the one to raise when adb is absent.
    binaire = _adb_binary()
    if not binaire:
        return (False, messages.ADB_INTROUVABLE)
    # The daemon FIRST, on its own. `adb pair` starts one when none is running,
    # and the pairing handshake then races that startup: adb reports
    # "protocol fault (couldn't read status message): Success" — the word
    # `Success` at the end being errno, not an outcome. In a container the
    # daemon is cold on every restart, so this is the ordinary case there
    # rather than a rare one.
    try:
        subprocess.run([binaire, "start-server"], capture_output=True,
                       text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass                      # `pair` will start it itself, as before

    def _essai():
        p = subprocess.run([binaire, "pair", addr, str(code)],
                           capture_output=True, text=True, timeout=60)
        lignes = (p.stdout + p.stderr).strip().splitlines()
        return lignes[-1] if lignes else ""

    try:
        brut = _essai()
        # One retry, and only on that fault. The pairing code survives a failed
        # attempt — it is spent by a SUCCESSFUL pairing or by its own timeout —
        # so trying twice costs nothing and covers the daemon still settling.
        # Any other refusal is answered by the console and repeating it would
        # only spend the reader's time.
        if "protocol fault" in brut.lower():
            brut = _essai()
        # `adb pair` exits 0 on failures too. Trusting the return code alone
        # announced "paired" and then refused every connection — the interface
        # said both things in a row and the user had to guess which was true.
        # Only adb's own word for success counts.
        ok = "successfully" in brut.lower()
        return (ok, brut if ok else _pair_reason(brut))
    except (OSError, subprocess.SubprocessError) as exc:
        return (False, str(exc))


# What adb says, and what it means. Its wording is aimed at whoever wrote adb:
# handing it over untouched — "protocol fault (couldn't read status message):
# Success" — tells the reader nothing, least of all that the word "Success" at
# the end means nothing here.
_RAISONS = (
    ("protocol fault",
     "La console a coupé la conversation. Le code d'appairage n'est valable "
     "qu'une fois et quelques minutes : rouvre « Débogage sans fil » sur la "
     "console pour en obtenir un nouveau, avec SON port — il change à chaque "
     "fois."),
    ("failed to authenticate",
     "La console a refusé l'appairage : le code ne correspond pas."),
    ("connection refused",
     "Rien n'écoute à cette adresse. Verifie le port : celui de l'appairage "
     "n'est pas celui de la connexion."),
    ("no route to host",
     "Cette adresse n'est pas joignable depuis le serveur. La console et "
     "Romule sont-ils sur le même réseau ?"),
)


def _pair_reason(brut):
    """A sentence somebody can act on, keeping adb's own line behind it."""
    bas = (brut or "").lower()
    for motif, phrase in _RAISONS:
        if motif in bas:
            return "%s (adb : %s)" % (phrase, brut)
    return brut or "L'appairage a échoué sans que adb dise pourquoi."


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


def _find_exts(cfg=None):
    """A `find` expression matching every ROM extension we know.

    Built from the platform table rather than written out: a platform declared
    by hand carries its own extensions, and they must be looked for too.
    """
    from . import systems
    exts = sorted({e.lower() for e in systems.accepted_exts(cfg)
                   if e.startswith(".") and len(e) <= 6})
    if not exts:
        return _GAME_FIND
    dedans = " -o ".join("-iname '*%s'" % e for e in exts)
    return r"\( %s \)" % dedans


# The extensions that mean "Switch". Its folder is detected on its own, and
# counting it here would hand the whole of internal storage the win on any
# console that keeps it apart from the rest.
_EXTS_SWITCH = (".nsp", ".xci", ".nsz", ".xcz")


def detect_roms_root(cfg=None, profondeur=4):
    """The folder holding the OTHER platforms' folders, on the console.

    The Switch folder has been detected since the beginning; the ROMs root was
    guessed from it — the parent of `.../Switch` — and typed by hand whenever
    that guess was wrong. Which is most of the time: a console with 133 games
    filed under `Emulation/roms/` shows a Switch folder at
    `/storage/emulated/0/Switch` and nothing else where Romule looked, so every
    other platform counted zero and the selector stopped saying how many.

    Two ways of recognising a platform folder, because either alone is blind:

      * by NAME — `systems.platform_for_folder` knows `gba`, and the aliases
        too: `PS1` for the PlayStation, `Sega` for the Mega Drive. Cheap, and it
        works on an empty folder;
      * by CONTENT — a folder holding game files IS a platform folder, whatever
        it is called. `Nintendo - Game Boy Advance` and `psx-eur` say nothing by
        their names, and this is the only thing that finds them.

    What the second one does NOT try to do is say WHICH platform: `.cue` and
    `.iso` are claimed by every disc console at once. It does not need to —
    finding the ROOT only requires knowing that a child holds games.

    The winner is the directory with the most such children, and two are the
    minimum: a lone `Wii` folder proves nothing, and answering with a wrong root
    would point every platform into it.
    """
    if state() != "device":
        return None
    from . import systems
    # parent -> {child folder name: the platform key when it is known}
    par_parent = {}

    for v in volumes():
        racine = v["path"].rstrip("/")
        cmd = ("find %s -maxdepth %d -type d 2>/dev/null"
               % (_q(racine), int(profondeur)))
        for ligne in _shell(cmd, timeout=120).splitlines():
            chemin = ligne.strip().rstrip("/")
            if not chemin or "/" not in chemin:
                continue
            parent, nom = chemin.rsplit("/", 1)
            cle = systems.platform_for_folder(nom, cfg)
            if cle and cle != "switch":
                par_parent.setdefault(parent, {})[nom] = cle

        cmd = ("find %s -maxdepth %d -type f %s 2>/dev/null"
               % (_q(racine), int(profondeur) + 2, _find_exts(cfg)))
        for ligne in _shell(cmd, timeout=180).splitlines():
            fichier = ligne.strip()
            if not fichier or fichier.count("/") < 2:
                continue
            if fichier.lower().endswith(_EXTS_SWITCH):
                continue
            dossier, _ = fichier.rsplit("/", 1)
            parent, nom = dossier.rsplit("/", 1)
            if systems.platform_for_folder(nom, cfg) == "switch":
                continue
            par_parent.setdefault(parent, {}).setdefault(
                nom, systems.platform_for_folder(nom, cfg))

    if not par_parent:
        return None
    # The most platform folders; on a tie the shallowest path, which is the one
    # a person would call the root.
    parent, trouves = max(par_parent.items(),
                          key=lambda kv: (len(kv[1]), -kv[0].count("/")))
    if len(trouves) < 2:
        return None
    # The names actually seen, so `device_dir` finds "PS1" when it expects
    # "PSX".
    systems.remember_folders(trouves)
    return parent


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
    _invalidate_cache()
    return tree_status(device_dir)


def organize(device_dir, job, types=None):
    """Tidy the console: every file goes to GAMES/UPDATE/DLC by type (even if
    it sat in a per-game folder), then empty folders are removed."""
    if state() != "device":
        # `warn`, and a sentence that says what to do. At `info` the line does
        # not reach the terminal in normal mode, and « Console non prete. »
        # alone reads as a status rather than as the reason nothing happened —
        # the action looked like it had done nothing at all, in silence.
        job.log(messages.RANGEMENT_SANS_CONSOLE, "warn")
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
        job.log(langue.phrase(messages.D_RANGE, g["name"], folder))
        moved += 1
        job.tick()
    # remove per-game folders that became empty (except GAMES/UPDATE/DLC)
    keep = " ".join("-not -name %s" % _q(tf) for tf in sorted(set(reels.values())))
    _shell("find %s -mindepth 1 -type d -empty %s -delete 2>/dev/null" % (_q(base), keep))
    _shell("find %s -mindepth 1 -type d -empty %s -delete 2>/dev/null" % (_q(base), keep))
    # Say it even when nothing moved: "already tidy" is an answer, and the
    # absence of one is what makes people click again.
    job.log(messages.D_CONSOLE_DEJA_RANGEE if not moved
            else langue.phrase(messages.D_RANGES_GUD_CONSOLE, moved), "ok")


    _invalidate_cache()

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


def _invalidate_cache():
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
            job.log(langue.phrase(messages.D_SUPPRIME, p.rsplit("/", 1)[-1]))
            n += 1
        else:
            job.log(langue.phrase(messages.D_ECHEC_SUPPR, p))
        job.tick()
    job.log(langue.phrase(messages.D_SUPPRIMES, n))


    _invalidate_cache()

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
            job.log(langue.phrase(messages.D_ECHEC_RETRY, msg or "inconnu"))
            time.sleep(2)
        else:
            job.log(langue.phrase(messages.D_ECHEC_FINAL, msg or "inconnu"))
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
            job.log(langue.phrase(messages.D_RECUP_INTERROMPUE, len(got)))
            break
        name = rp.rsplit("/", 1)[-1]
        dest = config.IMPORT / name
        job.log(langue.phrase(messages.D_RECUPERATION, name))
        rc, out, err = _run(["pull", rp, str(dest)], timeout=7200)
        if rc == 0 and dest.exists():
            job.log(langue.phrase(messages.D_RECU_MO, dest.stat().st_size / 1048576))
            got.append(str(dest))
        else:
            msg = (err or out or "").strip().splitlines()
            job.log(langue.phrase(messages.D_ECHEC, msg[-1] if msg else "adb pull"))
        job.tick()
    return got


def push_generic(paths, target_dir, job, verify=True, incremental=True):
    """Send ROMs (non-Switch systems) into a single folder on the console."""
    st = state()
    if st != "device":
        job.log(langue.phrase(messages.D_AUCUN_APPAREIL, st or "non connecte"))
        return
    base = target_dir.rstrip("/")
    if not base:
        job.log(messages.DOSSIER_CIBLE_INCONNU)
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
        job.log(langue.phrase(messages.D_DEJA_CONSOLE, nskip))
    job.set_total(len(todo))
    if not todo:
        job.log(messages.RIEN_A_ENVOYER)
        return

    okc = 0
    for f in todo:
        if not job.checkpoint():
            job.log(langue.phrase(messages.D_INTERROMPU, okc, len(todo)))
            return
        job.log(langue.phrase(messages.D_ENVOI, f.name))
        res = _send_one(f, base, base + "/" + f.name, f.stat().st_size,
                        "size" if verify else "none", job)
        if res == "gone":
            job.log(langue.phrase(messages.D_DECONNECTEE, okc, len(todo)))
            job.log(messages.REBRANCHE_LA)
            return
        if res == "ok":
            job.log(langue.phrase(messages.D_OK, f.name))
            okc += 1
        job.tick()
    job.log(langue.phrase(messages.D_TERMINE, okc, len(todo), base))


    _invalidate_cache()

def _target_folder(path, layout, known_type=None):
    """A file's target subfolder for the chosen layout.

    `type_connu` comes from the library, which read the container: it always
    wins over the file name, often incomplete or misleading.
    """
    if layout == "flat":
        return ""
    if layout == "game":  # mirror: the source per-game folder (parent)
        return str(path.parent.relative_to(config.LUDO))
    if known_type in config.LAYOUT_FOLDER:
        return config.LAYOUT_FOLDER[known_type]
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


def open_permissions(*paths):
    """Make the files adb just wrote reachable by Eden.

    A file pushed by adb belongs to the `shell` user, mode 644. Eden, running
    under another UID, is therefore merely "other": it can read but not write.
    Yet it opens its configs and its NAND contents read-write, and a refusal
    makes it give up silently, with no visible error. So we widen the
    permissions after every write.
    """
    for path in paths:
        if not path:
            continue
        q = _q(path)
        # A folder keeps its execute bit, without which it can no longer be
        # traversed: 777 for folders, 666 for files.
        _shell("if [ -d %s ]; then "
               "find %s -type f -exec chmod 666 {} + 2>/dev/null; "
               "find %s -type d -exec chmod 777 {} + 2>/dev/null; "
               "else chmod 666 %s 2>/dev/null; fi" % (q, q, q, q))


    _invalidate_cache()

# Android codes from `dumpsys battery`. The raw numbers say nothing on screen:
# we translate them here, once, rather than on every render.
_BATTERY_STATE = {1: "inconnu", 2: "charge", 3: "decharge",
                  4: "pause", 5: "pleine"}
_BATTERY_HEALTH = {1: "inconnue", 2: "bonne", 3: "surchauffe", 4: "hors service",
                   5: "surtension", 6: "defaillante", 7: "froide"}


def battery():
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
    etat = _BATTERY_STATE.get(entier("status") or 1, "inconnu")
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
        "sante": _BATTERY_HEALTH.get(entier("health") or 1, "inconnue"),
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
    except nand.Incomplete as exc:
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
        job.log(langue.phrase(messages.D_AUCUN_APPAREIL, st or "non connecte"))
        job.log(messages.BRANCHE_EN_USB)
        return

    items = plan(paths, device_dir, layout, incremental, types)
    casses = [it for it in items if it.get("broken")]
    todo = [it for it in items if not it["skip"] and not it.get("broken")]
    nskip = sum(1 for it in items if it["skip"] and not it.get("broken"))
    job.set_total(len(todo))
    if nskip:
        job.log(langue.phrase(messages.D_IDENTIQUES, nskip))
    for it in casses:
        job.log(langue.phrase(messages.D_REFUSE_INCOMPLET, it["name"], it["broken"]), "error")
    if casses:
        job.log(messages.FICHIER_INCOMPLET, "warn")
    if not todo:
        job.log(messages.RIEN_A_ENVOYER_A_JOUR)
        return

    total_bytes = sum(it["size"] for it in todo)
    done_bytes = 0
    start = time.time()
    okc, made = 0, set()

    # We record what is left to do: if the transfer stops, the user does not
    # have to rebuild the same selection to resume.
    from . import transfers
    transfers.start([it["local"] for it in todo], device_dir, "switch")

    for it in todo:
        if not job.checkpoint():
            job.log(langue.phrase(messages.D_INTERROMPU_ENVOYES, okc, len(todo)))
            job.log(messages.REPRISE_PROPOSEE, "warn")
            return
        if it["remote_dir"] not in made:
            _shell("mkdir -p %s" % _q(it["remote_dir"]))
            made.add(it["remote_dir"])
        job.log(langue.phrase(messages.D_ENVOI_VERS, it["name"], it["folder"]))
        res = _send_one(it["local"], it["remote_dir"], it["remote"], it["size"],
                        verify_mode, job)
        if res == "gone":
            job.log(langue.phrase(messages.D_DECONNECTEE, okc, len(todo)))
            job.log(messages.REBRANCHE_LA)
            job.set_detail("")
            return
        if res == "ok":
            job.log(langue.phrase(messages.D_OK, it["name"]))
            transfers.mark_done(it["local"])
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
    job.log(langue.phrase(messages.D_TERMINE, okc, len(todo), device_dir))
    if okc == len(todo):
        transfers.finish()          # nothing to resume
    _invalidate_cache()
