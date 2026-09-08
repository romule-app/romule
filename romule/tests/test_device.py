"""Tests of the adb parsers (pure, with no device).

Run with:  python3 -m romule.tests.test_device
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from romule import device as d  # noqa: E402


def test_parse_devices():
    out = ("List of devices attached\n"
           "ABC123  device product:RP5 model:Retroid_Pocket_5 device:RP5 transport_id:1\n")
    devs = d.parse_devices(out)
    assert len(devs) == 1
    assert devs[0]["serial"] == "ABC123"
    assert devs[0]["state"] == "device"
    assert devs[0]["model"] == "Retroid_Pocket_5"


def test_parse_devices_empty():
    assert d.parse_devices("List of devices attached\n\n") == []


def test_parse_df():
    out = ("Filesystem     1K-blocks     Used Available Use% Mounted on\n"
           "/dev/fuse      245988864 12345678 233643186   6% /storage/emulated\n")
    total, free = d.parse_df(out)
    assert total == 245988864 * 1024
    assert free == 233643186 * 1024


def test_parse_df_garbage():
    assert d.parse_df("") == (None, None)
    assert d.parse_df("une seule ligne") == (None, None)


def test_parse_find():
    out = ("6442450944|/storage/emulated/0/Switch/Poke [0100F43008C44000][v0].nsp\n"
           "1073741824|/storage/emulated/0/Switch/Poke [0100F43008C44800][v262144].nsp\n"
           "ligne|sans|taille valide ignoree si pas de nombre\n")
    games = d.parse_find(out)
    assert len(games) == 3
    base = next(g for g in games if g["type"] == "BASE")
    upd = next(g for g in games if g["type"] == "UPDATE")
    assert base["tid"] == "0100f43008c44000"
    assert base["size"] == 6442450944
    assert upd["version"] == 262144


def test_reconcile():
    lib = [{"tid": "0100f43008c44000", "version": 0, "name": "Poke"}]
    games = [
        {"tid": "0100f43008c44000", "version": 0, "name": "base.nsp"},
        {"tid": "0100f43008c44800", "version": 262144, "name": "upd.nsp"},
    ]
    d.reconcile(games, lib)
    assert games[0]["in_library"] is True
    assert games[1]["in_library"] is False


def test_is_wireless():
    assert d.is_wireless("192.168.1.42:5555") is True
    assert d.is_wireless("58974b87") is False
    assert d.is_wireless(None) is False


def test_pick_prefers_usb():
    devs = [{"serial": "192.168.1.42:5555", "state": "device"},
            {"serial": "58974b87", "state": "device"}]
    # both links present: USB wins, it is far faster
    assert d._pick(devs)["serial"] == "58974b87"
    # with an explicit preference: the choice is honoured
    assert d._pick(devs, "192.168.1.42:5555")["serial"] == "192.168.1.42:5555"
    # wifi alone: we take it
    assert d._pick([devs[0]])["serial"] == "192.168.1.42:5555"


def test_pick_ignores_unauthorized():
    devs = [{"serial": "AAA", "state": "unauthorized"},
            {"serial": "BBB", "state": "device"}]
    assert d._pick(devs)["serial"] == "BBB"
    assert d._pick([{"serial": "AAA", "state": "offline"}]) is None


def test_parse_devices_two():
    out = ("List of devices attached\n"
           "58974b87            device product:Thor model:AYN_Thor\n"
           "192.168.1.42:5555   device product:Thor model:AYN_Thor\n")
    devs = d.parse_devices(out)
    assert len(devs) == 2
    assert sum(1 for x in devs if d.is_wireless(x["serial"])) == 1


class _FauxAdb:
    """Records what was run, and answers a scripted line each time."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.appels = []

    def __call__(self, cmd, **kw):
        self.appels.append(list(cmd))
        class R:
            stdout = self.reponses.pop(0) if self.reponses else ""
            stderr = ""
            returncode = 0
        return R()


def _avec_faux(faux, fn):
    """Run `fn` with adb replaced. Restored whatever happens: a stub left
    behind poisons every test after it, and the one that fails is not the one
    at fault."""
    import subprocess
    vrai_run, vrai_bin = subprocess.run, d._adb_binary
    subprocess.run = faux
    d._adb_binary = lambda: "/faux/adb"
    try:
        return fn()
    finally:
        subprocess.run, d._adb_binary = vrai_run, vrai_bin


def test_pair_demarre_le_demon_avant():
    """`adb pair` starting the daemon itself is what produced
    "protocol fault (couldn't read status message): Success" — the handshake
    racing the daemon's own startup. In a container the daemon is cold on every
    restart, so the race is the ordinary case there."""
    faux = _FauxAdb("", "Successfully paired to 192.0.2.4:5555")
    ok, _ = _avec_faux(faux, lambda: d.pair("192.0.2.4:37105", "123456"))
    assert ok, "un appairage reussi doit etre reconnu"
    assert faux.appels[0][1] == "start-server", faux.appels[0]
    assert faux.appels[1][1] == "pair", faux.appels[1]


def test_pair_reessaie_une_fois_sur_protocol_fault():
    faux = _FauxAdb("", "error: protocol fault (couldn't read status message): Success",
                    "Successfully paired to 192.0.2.4:5555")
    ok, _ = _avec_faux(faux, lambda: d.pair("192.0.2.4:37105", "123456"))
    assert ok, "la seconde tentative doit compter"
    pairs = [a for a in faux.appels if a[1] == "pair"]
    assert len(pairs) == 2, pairs


def test_pair_ne_reessaie_pas_une_autre_erreur():
    """A wrong code is the console's own answer. Repeating it would spend the
    reader's time and say nothing new."""
    faux = _FauxAdb("", "failed to authenticate to 192.0.2.4:37105")
    ok, msg = _avec_faux(faux, lambda: d.pair("192.0.2.4:37105", "000000"))
    assert not ok
    assert len([a for a in faux.appels if a[1] == "pair"]) == 1, faux.appels
    assert "code" in msg.lower(), msg


def test_pair_sans_adresse_ne_lance_rien():
    faux = _FauxAdb()
    ok, _ = _avec_faux(faux, lambda: d.pair("", "123456"))
    assert not ok and faux.appels == [], faux.appels


class _AdbListe:
    """A fake adb, driven by the SCENARIO rather than by a call count.

    Counting calls would make the test depend on how fast the poll spins, which
    is exactly what `time.sleep` being stubbed out changes. `apres_reprise` is
    the state the console reaches once the stale entry has been dropped.
    """

    def __init__(self, etat, apres_reprise=None,
                 connect="connected to 192.0.2.4:5555",
                 adresse="192.0.2.4:5555"):
        self.etat = etat
        self.apres_reprise = apres_reprise
        self.connect = connect
        # The address `adb devices` lists. Hard-coding it made a test connect to
        # one address and read the state of another.
        self.adresse = adresse
        self.appels = []

    def __call__(self, args, timeout=60, targeted=True):
        self.appels.append(list(args))
        if args[0] == "devices":
            corps = ("%s\t%s\n" % (self.adresse, self.etat)) if self.etat else ""
            return (0, "List of devices attached\n" + corps, "")
        if args[0] == "disconnect" and self.apres_reprise:
            self.etat = self.apres_reprise
            return (0, "", "")
        if args[0] == "connect":
            return (0, self.connect, "")
        return (0, "", "")


def _avec_liste(faux, fn):
    vrai_run, vrai_sleep = d._run, None
    import time
    vrai_sleep = time.sleep
    d._run = faux
    time.sleep = lambda s: None          # the poll must not slow the suite down
    try:
        return fn()
    finally:
        d._run, time.sleep = vrai_run, vrai_sleep


def test_connect_refuse_un_lien_qui_reste_offline():
    """adb prints "connected to ..." and exits 0 while the console sits at
    `offline` — a state `_pick` refuses to drive. Announcing success there is
    what made the toast say connected while the header showed no console and
    the settings still asked for the configuration just done."""
    faux = _AdbListe("offline")
    ok, msg = _avec_liste(faux, lambda: d.connect("192.0.2.4:5555", attente=0.5))
    assert not ok, "un lien offline ne doit pas passer pour connecte"
    assert "débogage sans fil" in msg, msg


def test_connect_reprend_un_lien_offline_puis_reussit():
    # offline, offline, then the retry brings it up.
    faux = _AdbListe("offline", apres_reprise="device")
    ok, _ = _avec_liste(faux, lambda: d.connect("192.0.2.4:5555", attente=0.5))
    assert ok, "la reprise doit compter"
    assert ["disconnect", "192.0.2.4:5555"] in faux.appels, faux.appels


def test_connect_dit_quoi_faire_quand_la_console_demande_l_autorisation():
    faux = _AdbListe("unauthorized")
    ok, msg = _avec_liste(faux, lambda: d.connect("192.0.2.4:5555", attente=0.5))
    assert not ok
    assert "autorisation" in msg.lower() or "autoriser" in msg.lower(), msg


def test_connect_accepte_un_lien_vraiment_pret():
    faux = _AdbListe("device")
    ok, _ = _avec_liste(faux, lambda: d.connect("192.0.2.4:5555", attente=0.5))
    assert ok
    assert ["disconnect", "192.0.2.4:5555"] not in faux.appels, faux.appels


def test_connect_refuse_quand_adb_dit_non():
    faux = _AdbListe("device", connect="cannot connect to 192.0.2.4:5555")
    ok, _ = _avec_liste(faux, lambda: d.connect("192.0.2.4:5555", attente=0.5))
    assert not ok
    # Refused twice before being believed: once is not a verdict.
    assert len([a for a in faux.appels if a[0] == "connect"]) == 2, faux.appels


def test_connect_reessaie_un_refus_franc():
    """Right after a pairing, adbd on the console is re-binding its connection
    port and answers nothing for a second or two. Giving up there is what made
    people type the very same address again and watch it work — a bug report in
    which the reader has already done the debugging."""
    class _Capricieux(_AdbListe):
        def __init__(self):
            _AdbListe.__init__(self, "device", adresse="192.0.2.4:42653")
            self.essais = 0

        def __call__(self, args, timeout=60, targeted=True):
            if args[0] == "connect":
                self.appels.append(list(args))
                self.essais += 1
                return (0, "failed to connect to 192.0.2.4:42653", "") \
                    if self.essais == 1 else (0, "connected to 192.0.2.4:42653", "")
            return _AdbListe.__call__(self, args, timeout, targeted)

    faux = _Capricieux()
    ok, _ = _avec_liste(faux, lambda: d.connect("192.0.2.4:42653", attente=0.5))
    assert ok, "le second essai doit compter"


class _AdbReseau:
    """A fake adb with a device list, an mDNS answer, and connect outcomes."""

    def __init__(self, liste=(), mdns=(), acceptees=()):
        self.liste = list(liste)          # (serial, state)
        self.mdns = list(mdns)
        self.acceptees = set(acceptees)   # addresses that reach `device`
        self.appels = []

    def __call__(self, args, timeout=60, targeted=True):
        self.appels.append(list(args))
        if args[0] == "devices":
            corps = "".join("%s\t%s\n" % (s, e) for s, e in self.liste)
            return (0, "List of devices attached\n" + corps, "")
        if args[0] == "mdns":
            return (0, "".join("adb-X\t_adb-tls-connect._tcp\t%s\n" % a
                               for a in self.mdns), "")
        if args[0] == "connect":
            addr = args[1]
            if addr in self.acceptees:
                if not any(s == addr for s, _ in self.liste):
                    self.liste.append((addr, "device"))
                else:
                    self.liste = [(s, "device" if s == addr else e)
                                  for s, e in self.liste]
                return (0, "connected to %s" % addr, "")
            return (0, "failed to connect to %s" % addr, "")
        return (0, "", "")


def _avec_reseau(faux, fn):
    import time
    vrai_run, vrai_sleep = d._run, time.sleep
    d._run = faux
    time.sleep = lambda s: None
    try:
        return fn()
    finally:
        d._run, time.sleep = vrai_run, vrai_sleep


def test_candidats_essaie_d_abord_l_adresse_appairee():
    """The one candidate certain to be worth a try was the only one never tried.

    On a good many devices the pairing port and the connection port are the same
    number; `candidats` stripped the port on its very first line, so the wizard
    went on asking for a port the reader had already typed — which then worked
    when typed a second time.
    """
    faux = _AdbReseau(mdns=["192.0.2.4:41111"])
    liste = _avec_reseau(faux, lambda: d.candidats("192.0.2.4:42653"))
    assert liste[0] == "192.0.2.4:42653", liste


def test_relier_reussit_avec_le_port_de_l_appairage():
    faux = _AdbReseau(mdns=[], acceptees=["192.0.2.4:42653"])
    addr, essayees = _avec_reseau(
        faux, lambda: d.relier_apres_appairage("192.0.2.4:42653", attente=0.4))
    assert addr == "192.0.2.4:42653", (addr, essayees)
    # And without ever reaching the sweep, which costs seconds.
    assert essayees == ["192.0.2.4:42653"], essayees


def test_candidats_ignore_une_adresse_sans_port():
    faux = _AdbReseau(mdns=[])
    liste = _avec_reseau(faux, lambda: d.candidats("192.0.2.4"))
    assert liste == ["192.0.2.4:5555"], liste


def test_candidats_prefere_la_console_appairee():
    """`discover()[0]` was taken as the answer. On a network with two consoles
    that is a coin toss, and the wrong side connects to somebody else's."""
    faux = _AdbReseau(mdns=["192.0.2.9:41000", "192.0.2.4:41111"])
    liste = _avec_reseau(faux, lambda: d.candidats("192.0.2.4:37105"))
    # Past the paired address itself, which always comes first.
    reste = [a for a in liste if a != "192.0.2.4:37105"]
    assert reste[0] == "192.0.2.4:41111", liste


def test_candidats_reutilise_ce_qu_adb_sait_deja():
    """The connection port holds as long as wireless debugging stays on, so an
    entry left by a previous session — even `offline` — carries the right port.
    That is what makes a reconnection after a restart ask nothing."""
    faux = _AdbReseau(liste=[("192.0.2.4:41111", "offline")], mdns=[])
    liste = _avec_reseau(faux, lambda: d.candidats("192.0.2.4:37105"))
    reste = [a for a in liste if a != "192.0.2.4:37105"]
    assert reste[0] == "192.0.2.4:41111", liste


def test_relier_apres_appairage_trouve_sans_rien_demander():
    faux = _AdbReseau(mdns=["192.0.2.4:41111"], acceptees=["192.0.2.4:41111"])
    addr, _ = _avec_reseau(
        faux, lambda: d.relier_apres_appairage("192.0.2.4:37105", attente=0.4))
    assert addr == "192.0.2.4:41111", addr


def test_relier_apres_appairage_essaie_le_port_par_defaut_en_dernier():
    """5555 is what a console listens on after `adb tcpip 5555`, never what
    wireless debugging picks. Worth one refused round trip, last."""
    faux = _AdbReseau(mdns=["192.0.2.4:41111"], acceptees=["192.0.2.4:5555"])
    addr, essayees = _avec_reseau(
        faux, lambda: d.relier_apres_appairage("192.0.2.4:37105", attente=0.4))
    assert addr == "192.0.2.4:5555", (addr, essayees)
    assert essayees.index("192.0.2.4:41111") < essayees.index("192.0.2.4:5555")


def test_relier_apres_appairage_abandonne_proprement():
    """Nothing works: the port really does have to be read off the console.

    `scruter=False` so the suite does not spend the sweep's budget waiting on an
    address that answers nothing — the sweep has its own tests.
    """
    faux = _AdbReseau(mdns=[])
    addr, essayees = _avec_reseau(
        faux, lambda: d.relier_apres_appairage("192.0.2.4:37105", attente=0.4,
                                               scruter=False))
    assert addr is None, addr
    # The paired address first, the default port last: nothing else is known.
    assert essayees == ["192.0.2.4:37105", "192.0.2.4:5555"], essayees


def test_usb_dit_ce_que_le_port_montre():
    vrai = d.adb_available
    d.adb_available = lambda: True
    try:
        faux = _AdbReseau(liste=[("ABC123", "device")])
        assert _avec_reseau(faux, d.usb_state)["etat"] == "pret"
        faux = _AdbReseau(liste=[("ABC123", "unauthorized")])
        assert _avec_reseau(faux, d.usb_state)["etat"] == "autorisation"
        faux = _AdbReseau(liste=[])
        assert _avec_reseau(faux, d.usb_state)["etat"] == "aucune"
        # A wireless link is not the USB port: it used to be the same list.
        faux = _AdbReseau(liste=[("192.0.2.4:41111", "device")])
        assert _avec_reseau(faux, d.usb_state)["etat"] == "aucune"
    finally:
        d.adb_available = vrai


def test_usb_le_dit_quand_le_port_n_est_pas_visible():
    """Inside a container `/dev/bus/usb` is not mapped unless the operator said
    so. A card inviting you to plug a cable in there is an invitation to fail."""
    from romule import config
    vrai_adb, vrai_cont = d.adb_available, config.in_container
    vrai_isdir = os.path.isdir
    d.adb_available = lambda: True
    config.in_container = lambda: True
    os.path.isdir = lambda p: False if p == "/dev/bus/usb" else vrai_isdir(p)
    try:
        faux = _AdbReseau(liste=[])
        assert _avec_reseau(faux, d.usb_state)["etat"] == "invisible"
    finally:
        d.adb_available, config.in_container = vrai_adb, vrai_cont
        os.path.isdir = vrai_isdir


def test_le_balayage_marche_avec_beaucoup_de_descripteurs_ouverts():
    """The condition that made the first version find nothing, silently.

    `select.select()` raises `ValueError: filedescriptor out of range` as soon
    as ANY descriptor is 1024 or above. A running server — its HTTP socket, its
    clients, its log files — is always in that state, and eight hundred fresh
    sockets land far above it. The sweep therefore worked perfectly when tried
    on its own and found nothing at all in the only process where it mattered.

    So the test puts the process in that state FIRST. Without it, this file
    would go on passing while the feature stayed broken.
    """
    import socket as _s
    gardes = [_s.socket() for _ in range(1100)]
    srv = _s.socket()
    try:
        assert max(g.fileno() for g in gardes) > 1024, "condition non reproduite"
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        vu = d.ports_ouverts("127.0.0.1", debut=port, fin=port, budget=2.0,
                             delai=0.4)
        assert vu == [port], vu
    finally:
        srv.close()
        for g in gardes:
            g.close()


def test_le_balayage_trouve_un_port_qui_repond():
    """The console announces its wireless-debugging port over mDNS, and
    multicast does not cross a Docker bridge. Asking the host directly is what
    replaces the third number the reader was being sent to fetch."""
    import socket as _s
    srv = _s.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        ouverts = d.ports_ouverts("127.0.0.1", debut=port, fin=port,
                                  budget=2.0, delai=0.4)
        assert ouverts == [port], ouverts
    finally:
        srv.close()


def test_le_balayage_est_borne_dans_le_temps():
    """TEST-NET-1 answers nothing, ever. The sweep is bounded by a budget and
    not by its own size: an unbounded one is a hang, and a hang in a wizard is
    indistinguishable from a crash."""
    import time as _t
    debut = _t.monotonic()
    d.ports_ouverts("192.0.2.1", debut=30000, fin=65535, budget=1.0)
    ecoule = _t.monotonic() - debut
    assert ecoule < 4.0, "balayage non borne : %.1fs" % ecoule


def test_le_balayage_ignore_un_hote_vide():
    assert d.ports_ouverts("") == []


def test_le_balayage_essaie_d_abord_les_ports_voisins_de_l_appairage():
    """Android hands the pairing port and the connection port out of the same
    ephemeral pool, moments apart: they land near each other far more often than
    chance would put them. A console can answer on a dozen ports, of which one
    is adb, and we only get to try twelve."""
    faux = _AdbReseau(mdns=[], acceptees=["192.0.2.4:37200"])
    vrai = d.ports_ouverts
    d.ports_ouverts = lambda h, **kw: [31000, 60000, 37200, 45000]
    try:
        addr, essayees = _avec_reseau(
            faux, lambda: d.relier_apres_appairage("192.0.2.4:37105",
                                                   attente=0.4))
    finally:
        d.ports_ouverts = vrai
    assert addr == "192.0.2.4:37200", (addr, essayees)
    balayes = [a for a in essayees
               if a not in ("192.0.2.4:5555", "192.0.2.4:37105")]
    assert balayes[0] == "192.0.2.4:37200", balayes


def test_relier_bascule_sur_le_balayage_quand_rien_d_autre_ne_marche():
    faux = _AdbReseau(mdns=[], acceptees=["192.0.2.4:41111"])
    vrai = d.ports_ouverts
    d.ports_ouverts = lambda h, **kw: [41111]
    try:
        addr, essayees = _avec_reseau(
            faux, lambda: d.relier_apres_appairage("192.0.2.4:37105",
                                                   attente=0.4))
    finally:
        d.ports_ouverts = vrai
    assert addr == "192.0.2.4:41111", (addr, essayees)
    # The default port is tried BEFORE the sweep: one round trip beats a scan.
    assert essayees.index("192.0.2.4:5555") < essayees.index("192.0.2.4:41111")


def test_relier_peut_se_passer_du_balayage():
    """`scruter=False` for callers that must answer at once — a startup
    reconnection must not hold the service for eight seconds."""
    faux = _AdbReseau(mdns=[])
    appelee = []
    vrai = d.ports_ouverts
    d.ports_ouverts = lambda h, **kw: appelee.append(h) or []
    try:
        _avec_reseau(faux, lambda: d.relier_apres_appairage(
            "192.0.2.4:37105", attente=0.4, scruter=False))
    finally:
        d.ports_ouverts = vrai
    assert appelee == [], appelee


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("  ok   %s" % fn.__name__)
        except AssertionError as exc:
            failed += 1
            print("  FAIL %s : %s" % (fn.__name__, exc or "assertion"))
    print("\n%d/%d test(s) reussi(s)." % (len(fns) - failed, len(fns)))
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
