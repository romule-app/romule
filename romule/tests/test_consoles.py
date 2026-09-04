"""Several consoles, and the settings that must not leak between them.

What is checked here is mostly what must NOT happen. Adding a second console is
easy; the defects are quiet ones:

  * a configuration written before this existed loses its pairing;
  * switching console shows the other one's folder;
  * a setting saved for one console is read back on the other;
  * going back a version finds nothing where it left its pairing.

The last one is the reason the flat keys still exist, and it is checked by
reading them the way the old code did.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["ROMULE_ROOT"] = tempfile.mkdtemp(prefix="romule-consoles-")

from romule import config, consoles                              # noqa: E402

ok = ko = 0


def t(name, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        ko += 1
        print("  FAIL %s   %s" % (name, detail))


def write_config(d):
    """Write a raw configuration file, as an older version would have left it."""
    config.CONFIG_FILE.write_text(json.dumps(d), encoding="utf-8")


def test_a_flat_configuration_migrates():
    write_config({"device_dir": "/storage/emulated/0/Switch",
                  "wifi_addr": "192.0.2.9:5555", "emulateur": "eden",
                  "roms_root": "/storage/emulated/0/ROMs"})
    cfg = config.load_config()
    known = consoles.list_all(cfg)
    t("the flat keys become one console", len(known) == 1, known)
    t("its name is readable", known[0]["nom"] == consoles.DEFAULT_NAME, known[0])
    t("the pairing is carried over",
      known[0]["wifi_addr"] == "192.0.2.9:5555", known[0])
    t("so is the folder",
      known[0]["device_dir"] == "/storage/emulated/0/Switch", known[0])
    t("and it is the active one",
      consoles.active(cfg)["id"] == cfg["active_device"])
    # Migrating twice would give the same installation a second console on
    # every restart.
    before = cfg["devices"]
    t("a second load migrates nothing", not consoles.migrate(dict(cfg)), before)


def test_a_fresh_install_still_has_one():
    write_config({})
    cfg = config.load_config()
    t("a fresh install has exactly one console",
      len(consoles.list_all(cfg)) == 1, consoles.list_all(cfg))


def test_each_console_keeps_its_own_settings():
    write_config({"device_dir": "/A", "wifi_addr": "10.0.0.1:5555"})
    cfg = config.load_config()
    first = consoles.active(cfg)["id"]
    second = consoles.add(cfg, "Retroid")
    t("a second console can be declared", bool(second), second)

    # Set the second one's folder the way the interface does: choose it, write
    # the flat key, save.
    consoles.select(cfg, second["id"])
    cfg["device_dir"] = "/B"
    cfg["wifi_addr"] = "10.0.0.2:5555"
    config.save_config(cfg)

    back = config.load_config()
    t("the active console is remembered across a reload",
      back["active_device"] == second["id"], back["active_device"])
    t("the active console's folder is the one read", back["device_dir"] == "/B",
      back["device_dir"])

    consoles.select(back, first)
    t("switching back brings the FIRST console's folder", back["device_dir"] == "/A",
      back["device_dir"])
    t("and its own pairing", back["wifi_addr"] == "10.0.0.1:5555",
      back["wifi_addr"])
    # The defect this whole file exists for: one console's setting read on the
    # other.
    by_id = {d["id"]: d for d in consoles.list_all(back)}
    t("nothing leaked between the two",
      by_id[first]["device_dir"] == "/A" and by_id[second["id"]]["device_dir"] == "/B",
      [(d["nom"], d["device_dir"]) for d in consoles.list_all(back)])


def test_the_flat_keys_stay_readable():
    """An older version reads `device_dir` at the top level and nothing else.
    It must find the active console's value there, not an empty string."""
    write_config({"device_dir": "/A"})
    cfg = config.load_config()
    second = consoles.add(cfg, "Odin")
    consoles.select(cfg, second["id"])
    cfg["device_dir"] = "/B"
    config.save_config(cfg)
    raw = json.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
    t("the flat key is written, not only the list", raw.get("device_dir") == "/B",
      raw.get("device_dir"))
    t("the list holds both", len(raw.get("devices") or []) == 2,
      raw.get("devices"))


def test_removing_and_renaming():
    write_config({"device_dir": "/A"})
    cfg = config.load_config()
    first = consoles.active(cfg)["id"]
    second = consoles.add(cfg, "Odin")
    t("renaming works", consoles.rename(cfg, second["id"], "Odin 2"))
    t("the new name is kept",
      any(d["nom"] == "Odin 2" for d in consoles.list_all(cfg)))
    consoles.select(cfg, second["id"])
    t("removing the active one falls back to another",
      consoles.remove(cfg, second["id"]) and cfg["active_device"] == first,
      cfg["active_device"])
    t("removing something unknown changes nothing",
      not consoles.remove(cfg, "no-such-console"))


def test_only_known_fields_are_stored():
    write_config({"device_dir": "/A"})
    cfg = config.load_config()
    cfg["devices"] = [{"id": "x", "nom": "X", "device_dir": "/X",
                       "surprise": "should not survive"}]
    kept = consoles.list_all(cfg)[0]
    t("an unknown field is dropped", "surprise" not in kept, kept)
    t("every known field is present",
      all(k in kept for k in consoles.PER_DEVICE), kept)
    t("a non-dict entry is ignored",
      consoles.list_all({"devices": ["nonsense", {"id": "y"}]})[0]["id"] == "y")


def test_the_list_is_bounded():
    write_config({})
    cfg = config.load_config()
    for i in range(consoles.MAX_DEVICES + 3):
        consoles.add(cfg, "c%d" % i)
    t("the list stops at its ceiling",
      len(consoles.list_all(cfg)) == consoles.MAX_DEVICES,
      len(consoles.list_all(cfg)))


def test_what_the_interface_sees():
    write_config({"device_dir": "/A"})
    cfg = config.load_config()
    pub = consoles.public(cfg)
    t("the interface gets a list and a pointer",
      "devices" in pub and "active_device" in pub, sorted(pub))
    # A console entry has no business carrying a secret today, and this check is
    # what makes that a rule rather than a coincidence.
    t("no field beyond what a selector needs",
      set(pub["devices"][0]) == {"id", "nom", "device_dir", "emulateur", "wifi_addr"},
      sorted(pub["devices"][0]))


for fn in (test_a_flat_configuration_migrates, test_a_fresh_install_still_has_one,
           test_each_console_keeps_its_own_settings,
           test_the_flat_keys_stay_readable, test_removing_and_renaming,
           test_only_known_fields_are_stored, test_the_list_is_bounded,
           test_what_the_interface_sees):
    fn()
print("  %d checks OK, %d failure(s)" % (ok, ko))
sys.exit(1 if ko else 0)
