"""La verification de version : elle informe, elle ne derange pas.

Trois proprietes, et la troisieme est celle qui compte le plus :

  * la comparaison porte sur des NOMBRES. « 0.10.0 » vient apres « 0.9.0 »,
    ce qu'une comparaison de chaines rend faux — et un outil qui annonce une
    mise a jour a l'envers perd toute credibilite ;
  * elle se coupe, et le reglage est respecte AVANT toute sortie reseau ;
  * une panne ne se voit pas. GitHub indisponible, quota atteint, machine hors
    ligne : la fonction rend « je ne sais pas », jamais une erreur. Une
    verification ratee n'est pas un evenement pour l'utilisateur.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
_TMP = Path(tempfile.mkdtemp(prefix="romule-maj-"))
from romule import maj                                          # noqa: E402
maj.CACHE = _TMP / "_romule-maj.json"

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
        v = maj.plus_recente(publiee, courante)
        t("%-10s > %-9s -> %s" % (repr(publiee), repr(courante), attendu),
          v == attendu, "obtenu %s (%s)" % (v, pourquoi))


def test_le_reglage_coupe_avant_le_reseau():
    """Le reglage doit etre lu AVANT la sortie : sinon « desactive » voudrait
    dire « on interroge quand meme, mais on n'affiche pas »."""
    appels = []
    vrai = maj.reseau.ouvrir
    maj.reseau.ouvrir = lambda *a, **k: appels.append(a) or (_ for _ in ()).throw(
        RuntimeError("ne doit pas etre appele"))
    try:
        r = maj.etat({"maj_check": False})
        t("desactive : aucune sortie reseau", not appels, appels)
        t("desactive : rien a montrer", r["disponible"] is False and not r["version"])
        t("desactive : l'interface le sait", r["actif"] is False)
    finally:
        maj.reseau.ouvrir = vrai


def test_une_panne_ne_se_voit_pas():
    maj.CACHE.unlink(missing_ok=True)
    vrai = maj.reseau.ouvrir

    def casse(*a, **k):
        raise OSError("reseau coupe")

    maj.reseau.ouvrir = casse
    try:
        r = maj.etat({"maj_check": True})
        t("reseau coupe : pas d'exception", isinstance(r, dict))
        t("reseau coupe : rien a annoncer", r["disponible"] is False)
        t("reseau coupe : la version courante est quand meme rendue",
          r["courante"] == maj.__version__)
    finally:
        maj.reseau.ouvrir = vrai


def test_le_cache_evite_les_appels():
    """GitHub limite les requetes anonymes. Un cache frais doit suffire."""
    maj.CACHE.write_text(json.dumps({
        "version": "v99.0.0", "titre": "Essai", "notes": "des notes",
        "url": "https://exemple.fr", "verifie": int(__import__("time").time())}),
        encoding="utf-8")
    appels = []
    vrai = maj.reseau.ouvrir
    maj.reseau.ouvrir = lambda *a, **k: appels.append(a) or (_ for _ in ()).throw(
        RuntimeError("ne doit pas etre appele"))
    try:
        r = maj.etat({"maj_check": True})
        t("cache frais : aucun appel reseau", not appels, appels)
        t("cache frais : la version est rendue", r["version"] == "v99.0.0")
        t("cache frais : elle est annoncee plus recente", r["disponible"] is True)
        t("cache frais : les notes suivent", r["notes"] == "des notes")
    finally:
        maj.reseau.ouvrir = vrai
        maj.CACHE.unlink(missing_ok=True)


def test_le_prefixe_du_tag_est_retire():
    """« Version v0.3.0 disponible » fait doublon a l'ecran.

    GitHub nomme ses tags `v0.3.0` ; l'interface ecrit deja le mot « Version »
    devant. On retire donc le prefixe a l'AFFICHAGE — sans toucher a la
    comparaison, qui ne l'a jamais lu.
    """
    import io

    class Fausse(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    corps = json.dumps({"tag_name": "v9.9.9", "name": "Essai",
                        "body": "notes", "html_url": "https://exemple.fr",
                        "published_at": "2026-01-01T00:00:00Z"}).encode()
    vrai = maj.reseau.ouvrir
    maj.reseau.ouvrir = lambda *a, **k: Fausse(corps)
    try:
        r = maj.etat({"maj_check": True}, forcer=True)
        t("le `v` du tag ne remonte pas a l'interface", r["version"] == "9.9.9",
          r["version"])
        t("et la version reste reconnue comme plus recente",
          r["disponible"] is True, r)
        # Le prefixe n'a jamais gene la comparaison : `_triplet` l'ignore. Le
        # verifier evite de croire que ce nettoyage la corrige.
        t("la comparaison acceptait deja le prefixe",
          maj.plus_recente("v9.9.9", "0.1.0") is True)
    finally:
        maj.reseau.ouvrir = vrai
        maj.CACHE.unlink(missing_ok=True)


def test_la_sortie_est_gardee():
    """Toute sortie reseau de Romule passe par `reseau.ouvrir()`, qui refuse
    les schemas autres que http/https. Ce module ne doit pas y echapper."""
    src = (Path(maj.__file__)).read_text(encoding="utf-8")
    t("maj.py n'appelle pas urlopen directement",
      "urlopen(" not in src)
    t("maj.py passe par reseau.ouvrir", "reseau.ouvrir(" in src)


for fn in (test_comparaison, test_le_reglage_coupe_avant_le_reseau,
           test_une_panne_ne_se_voit_pas, test_le_cache_evite_les_appels,
           test_le_prefixe_du_tag_est_retire,
           test_la_sortie_est_gardee):
    fn()
print("  %d controles OK, %d echec(s)" % (ok, ko))
sys.exit(1 if ko else 0)
