"""The library report assembles; it must not invent.

Two properties matter, and they pull in opposite directions:

  * everything wrong is named — a family missing from the report is a problem
    nobody will ever look at, because the screen said there was none;
  * nothing is named twice, and a family with nothing in it is absent — a list
    of "0 problems" is what turns a health screen into wallpaper.

The third is that it never raises. Half a report is useful; a stack trace where
a screen should be is not.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from romule import report                                        # noqa: E402

ok = ko = 0


def t(name, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        ko += 1
        print("  FAIL %s   %s" % (name, detail))


class FakeLib:
    def __init__(self, files):
        self.files = files


def game(rel, tid="0100000000001000", **extra):
    d = {"rel": rel, "name": rel, "tid": tid, "type": "BASE", "size": 1}
    d.update(extra)
    return d


def families(rep):
    return {f["cle"]: f for f in rep["familles"]}


def test_an_untroubled_library_says_so():
    rep = report.build(FakeLib([game("Ok.nsp")]), {},
                       meta_cache={"0100000000001000": {"nom": "Ok"}})
    t("no family is invented", rep["familles"] == [], rep["familles"])
    t("the total is zero", rep["total"] == 0, rep["total"])
    t("coverage is still reported", "integrite" in rep, sorted(rep))


def test_each_defect_lands_in_its_family():
    files = [
        game("Casse.nsp", flags=[("broken", "fichier incomplet")]),
        game("Orphelin.nsp", tid="0100000000002800",
             flags=[("orphan", "jeu de base absent")]),
        game("Vieux.nsp", tid="0100000000003000", flags=[("old", "plus recente")]),
        game("Gros.nsp", tid="0100000000004000", needs_convert=True),
    ]
    rep = report.build(FakeLib(files), {}, meta_cache={
        "0100000000001000": 1, "0100000000002000": 1,
        "0100000000003000": 1, "0100000000004000": 1})
    f = families(rep)
    t("a broken file is named", f.get("incomplets", {}).get("nombre") == 1, f)
    t("an orphan is named", f.get("orphelins", {}).get("nombre") == 1, f)
    t("a superseded version is named", f.get("depassees", {}).get("nombre") == 1, f)
    t("something to convert is named", f.get("aconvertir", {}).get("nombre") == 1, f)
    t("the total adds them up", rep["total"] == 4, rep["total"])


def test_a_file_counts_once_per_family():
    """A file carrying two flags of the same family must not be listed twice:
    a number that double-counts is a number nobody can act on."""
    files = [game("Deux.nsp", flags=[("old", "a"), ("outdated", "b")])]
    rep = report.build(FakeLib(files), {}, meta_cache={"0100000000001000": 1})
    t("two flags of one family count once",
      families(rep)["depassees"]["nombre"] == 1, rep["familles"])


def test_a_game_without_an_entry_is_named():
    files = [game("Sans.nsp", tid="0100000000005000")]
    rep = report.build(FakeLib(files), {}, meta_cache={})
    t("a game with no entry is reported",
      families(rep).get("fiches", {}).get("nombre") == 1, rep["familles"])
    rep = report.build(FakeLib(files), {},
                       meta_cache={"0100000000005000": {"nom": "Sans"}})
    t("and not when it has one", "fiches" not in families(rep), rep["familles"])


def test_the_drop_folder_is_part_of_the_picture():
    rep = report.build(FakeLib([]), {}, pending=[{"rel": "a.nsp", "etat": "pret"}])
    t("what waits in the drop folder is named",
      families(rep).get("depot", {}).get("nombre") == 1, rep["familles"])


def test_every_family_carries_what_to_do():
    files = [game("Casse.nsp", flags=[("broken", "x")]),
             game("Gros.nsp", tid="0100000000004000", needs_convert=True)]
    rep = report.build(FakeLib(files), {}, meta_cache={
        "0100000000001000": 1, "0100000000004000": 1})
    f = families(rep)
    t("the broken family points at a verification",
      f["incomplets"]["action"] == "verify", f["incomplets"])
    t("the conversion family points at the conversion",
      f["aconvertir"]["action"] == "convertAll", f["aconvertir"])
    t("every family explains itself",
      all(x["detail"] for x in rep["familles"]), rep["familles"])


def test_examples_are_bounded():
    """A family with 4 000 files must not send 4 000 lines to a browser."""
    files = [game("f%d.nsp" % i, tid="01000000000%05d" % i,
                  flags=[("broken", "x")]) for i in range(50)]
    rep = report.build(FakeLib(files), {}, meta_cache={})
    f = families(rep)["incomplets"]
    t("the count is whole", f["nombre"] == 50, f["nombre"])
    t("the examples are cut short", len(f["exemples"]) <= 8, len(f["exemples"]))


def test_a_broken_source_does_not_break_the_report():
    """`duplicates.report` reads the console and the disk. When it fails, the
    rest of the screen must still arrive."""
    class Explodes:
        files = [game("Casse.nsp", flags=[("broken", "x")])]

        def __getattr__(self, name):
            raise RuntimeError("boom")

    rep = report.build(Explodes(), {}, meta_cache={"0100000000001000": 1})
    t("the report survives a source that fails", rep["total"] >= 1, rep)


for fn in (test_an_untroubled_library_says_so, test_each_defect_lands_in_its_family,
           test_a_file_counts_once_per_family, test_a_game_without_an_entry_is_named,
           test_the_drop_folder_is_part_of_the_picture,
           test_every_family_carries_what_to_do, test_examples_are_bounded,
           test_a_broken_source_does_not_break_the_report):
    fn()
print("  %d checks OK, %d failure(s)" % (ok, ko))
sys.exit(1 if ko else 0)
