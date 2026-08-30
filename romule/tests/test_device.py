"""Tests des parsers adb (purs, sans appareil).

Lancer :  python3 -m romule.tests.test_device
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
    # les deux liens presents : l'USB gagne, il est bien plus rapide
    assert d._pick(devs)["serial"] == "58974b87"
    # avec preference explicite : on respecte le choix
    assert d._pick(devs, "192.168.1.42:5555")["serial"] == "192.168.1.42:5555"
    # wifi seul : on le prend
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
