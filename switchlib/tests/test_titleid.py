"""Tests de la logique title ID — le coeur du classement.

Lancer :  python3 -m switchlib.tests.test_titleid
(ou avec pytest si installe)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from switchlib import titleid as t  # noqa: E402

# title ID reels tires de la ludotheque
BASE_POKE = "0100f43008c44000"
UPD_POKE = "0100f43008c44800"
DLC_POKE = "0100f43008c45002"
BASE_DIGI = "01007ea015520000"
DLC_DIGI = "01007ea015521001"
BASE_MK = "01005e902232a000"


def test_type():
    assert t.tid_type(BASE_POKE) == "BASE"
    assert t.tid_type(UPD_POKE) == "UPDATE"
    assert t.tid_type(DLC_POKE) == "DLC"
    assert t.tid_type(BASE_DIGI) == "BASE"
    assert t.tid_type(DLC_DIGI) == "DLC"
    assert t.tid_type(BASE_MK) == "BASE"


def test_base():
    assert t.tid_base(UPD_POKE) == BASE_POKE
    assert t.tid_base(DLC_POKE) == BASE_POKE
    assert t.tid_base(DLC_DIGI) == BASE_DIGI
    assert t.tid_base(BASE_POKE) == BASE_POKE  # une base reste elle-meme


def test_patch():
    assert t.tid_patch(BASE_POKE) == UPD_POKE
    assert t.tid_patch(BASE_MK) == "01005e902232a800"


def test_dlc_prefix():
    # les DLC de Pokemon partagent 0100f43008c4 + '5'
    assert DLC_POKE.startswith(t.dlc_prefix(BASE_POKE))
    assert DLC_DIGI.startswith(t.dlc_prefix(BASE_DIGI))


def test_parse():
    n = "Pokemon Legends Z-A [0100F43008C44800][v262144].nsp"
    assert t.from_name(n) == UPD_POKE
    assert t.version_from_name(n) == 262144
    assert t.pretty_name(n) == "Pokemon Legends Z-A"
    assert t.from_name("sans_id.nsp") is None
    assert t.version_from_name("sans_version.nsp") is None


def test_case_insensitive():
    assert t.tid_type("0100F43008C44000") == "BASE"
    assert t.from_name("X [0100F43008C45002].nsp") == DLC_POKE


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
