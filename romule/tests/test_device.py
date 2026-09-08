"""Tests of the adb parsers (pure, with no device).

Run with:  python3 -m romule.tests.test_device
"""

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
