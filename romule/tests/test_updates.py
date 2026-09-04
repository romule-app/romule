"""The version check: it informs, it does not intrude.

Three properties, and the third is the one that matters most:

  * the comparison is on NUMBERS. "0.10.0" comes after "0.9.0", which a string
    comparison gets wrong — and a tool that announces an update backwards loses
    all credibility;
  * it can be switched off, and the setting is honoured BEFORE any network call;
  * a failure does not show. GitHub unavailable, quota reached, machine offline:
    the function returns "I don't know", never an error. A failed check is not an
    event for the user.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
_TMP = Path(tempfile.mkdtemp(prefix="romule-maj-"))
from romule import updates                                          # noqa: E402
updates.CACHE = _TMP / "_romule-updates.json"

ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % nom)
    else:
        ko += 1
        print("  ECHEC %s   %s" % (nom, detail))


def test_comparaison():
    CAS = [
        ("v0.3.0", "0.2.0", True, "le prefixe v est tolere"),
        ("0.10.0", "0.9.0", True, "dix vient apres neuf — le piege lexical"),
        ("0.2.0", "0.2.0", False, "identique"),
        ("0.1.9", "0.2.0", False, "anterieure"),
        ("1.0.0", "0.99.99", True, ""),
        ("v0.3.0-rc1", "0.2.0", True, "un suffixe ne gene pas"),
        ("main", "0.2.0", False, "illisible : on se tait plutot que crier"),
        ("", "0.2.0", False, "vide"),
    ]
    for publiee, courante, attendu, pourquoi in CAS:
        v = updates.newer_than(publiee, courante)
        t("%-10s > %-9s -> %s" % (repr(publiee), repr(courante), attendu),
          v == attendu, "obtenu %s (%s)" % (v, pourquoi))


def test_le_reglage_coupe_avant_le_reseau():
    """The setting must be read BEFORE going out: otherwise "disabled" would
    mean "we ask anyway, but we do not display"."""
    appels = []
    vrai = updates.net.open_url
    updates.net.open_url = lambda *a, **k: appels.append(a) or (_ for _ in ()).throw(
        RuntimeError("ne doit pas etre appele"))
    try:
        r = updates.state({"maj_check": False})
        t("desactive : aucune sortie reseau", not appels, appels)
        t("desactive : rien a montrer", r["disponible"] is False and not r["version"])
        t("desactive : l'interface le sait", r["actif"] is False)
    finally:
        updates.net.open_url = vrai


def test_une_panne_ne_se_voit_pas():
    updates.CACHE.unlink(missing_ok=True)
    vrai = updates.net.open_url

    def casse(*a, **k):
        raise OSError("network down")

    updates.net.open_url = casse
    try:
        r = updates.state({"maj_check": True})
        t("network down: no exception", isinstance(r, dict))
        t("network down: nothing to announce", r["disponible"] is False)
        t("network down: the current version is returned all the same",
          r["courante"] == updates.__version__)
    finally:
        updates.net.open_url = vrai


def test_le_cache_evite_les_appels():
    """GitHub limits anonymous requests. A fresh cache must be enough."""
    updates.CACHE.write_text(json.dumps({
        "version": "v99.0.0", "titre": "Essai", "notes": "des notes",
        "url": "https://exemple.fr", "verifie": int(__import__("time").time())}),
        encoding="utf-8")
    appels = []
    vrai = updates.net.open_url
    updates.net.open_url = lambda *a, **k: appels.append(a) or (_ for _ in ()).throw(
        RuntimeError("ne doit pas etre appele"))
    try:
        r = updates.state({"maj_check": True})
        t("cache frais : aucun appel reseau", not appels, appels)
        t("cache frais : la version est rendue", r["version"] == "v99.0.0")
        t("cache frais : elle est annoncee plus recente", r["disponible"] is True)
        t("cache frais : les notes suivent", r["notes"] == "des notes")
    finally:
        updates.net.open_url = vrai
        updates.CACHE.unlink(missing_ok=True)


def test_le_prefixe_du_tag_est_retire():
    """"Version v0.3.0 available" reads twice on screen.

    GitHub names its tags `v0.3.0`; the interface already writes the word
    "Version" in front. So the prefix is stripped for DISPLAY — without touching
    the comparison, which never read it.
    """
    import io

    class Fausse(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    corps = json.dumps({"tag_name": "v9.9.9", "name": "Essai",
                        "body": "notes", "html_url": "https://exemple.fr",
                        "published_at": "2026-01-01T00:00:00Z"}).encode()
    vrai = updates.net.open_url
    updates.net.open_url = lambda *a, **k: Fausse(corps)
    try:
        r = updates.state({"maj_check": True}, force=True)
        t("le `v` du tag ne remonte pas a l'interface", r["version"] == "9.9.9",
          r["version"])
        t("et la version reste reconnue comme plus recente",
          r["disponible"] is True, r)
        # The prefix never troubled the comparison: `_triplet` ignores it.
        # Checking it avoids believing this cleanup fixes it.
        t("la comparaison acceptait deja le prefixe",
          updates.newer_than("v9.9.9", "0.1.0") is True)
    finally:
        updates.net.open_url = vrai
        updates.CACHE.unlink(missing_ok=True)


def test_la_sortie_est_gardee():
    """Every outbound call in Romule goes through `net.open_url()`, which
    refuses schemes other than http/https. This module must not escape it."""
    src = (Path(updates.__file__)).read_text(encoding="utf-8")
    t("updates.py n'appelle pas urlopen directement",
      "urlopen(" not in src)
    t("updates.py goes through net.open_url", "net.open_url(" in src)


for fn in (test_comparaison, test_le_reglage_coupe_avant_le_reseau,
           test_une_panne_ne_se_voit_pas, test_le_cache_evite_les_appels,
           test_le_prefixe_du_tag_est_retire,
           test_la_sortie_est_gardee):
    fn()
print("  %d controles OK, %d echec(s)" % (ok, ko))
sys.exit(1 if ko else 0)
