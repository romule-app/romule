"""API keys: what they open, and above all what they do not.

The check that matters is not "a valid key opens `/api/v1`" — it is "a valid key
CANNOT reach `/api/comptes`". A test that checks only the first half would let
through a key that opens everything, which is exactly the defect an API key is
meant to avoid: giving a dashboard the right to delete accounts.

The scope is checked here on the decision function itself; the full HTTP journey
is checked in `test_apiv1.py`.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# The store must live in a throwaway folder: this test creates and revokes keys,
# and it has no business inside the user's state file.
_TMP = Path(tempfile.mkdtemp(prefix="romule-cles-"))
from romule import apikeys                                      # noqa: E402
apikeys.FILE = _TMP / "_romule-cles.json"

ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % nom)
    else:
        ko += 1
        print("  ECHEC %s   %s" % (nom, detail))


def test_creation():
    fiche, cle = apikeys.create("tableau de bord")
    t("la cle porte le marqueur", cle.startswith("rml_"), cle[:8])
    t("la cle est longue", len(cle) >= 40, len(cle))
    t("le nom est conserve", fiche["nom"] == "tableau de bord")
    t("le prefixe est court", len(fiche["prefixe"]) == 12, fiche["prefixe"])
    t("la cle en clair n'est PAS dans la fiche",
      cle not in repr(fiche), repr(fiche)[:80])
    # The state file must hold no key in the clear: that is what makes its leak
    # harmless for the keys themselves.
    brut = apikeys.FILE.read_text(encoding="utf-8")
    t("le fichier ne contient pas la cle en clair", cle not in brut)
    t("le fichier contient une empreinte", "empreinte" in brut)


def test_deux_cles_different():
    _, a = apikeys.create("a")
    _, b = apikeys.create("b")
    t("deux cles creees a la suite different", a != b)


def test_verification():
    fiche, cle = apikeys.create("script")
    t("une cle valide est reconnue",
      (apikeys.verify(cle) or {}).get("id") == fiche["id"])
    t("une cle inconnue est refusee", apikeys.verify("rml_inexistante") is None)
    t("une chaine vide est refusee", apikeys.verify("") is None)
    t("None est refuse", apikeys.verify(None) is None)
    t("un secret sans marqueur est refuse",
      apikeys.verify(cle[4:]) is None)
    # The same secret to within one character: the comparison is on the whole
    # fingerprint, not on the prefix that serves to find the record.
    faux = cle[:-1] + ("a" if cle[-1] != "a" else "b")
    t("un caractere different suffit a refuser", apikeys.verify(faux) is None)


def test_revocation():
    fiche, cle = apikeys.create("a jeter")
    t("valide avant revocation", apikeys.verify(cle) is not None)
    t("la revocation reussit", apikeys.revoke(fiche["id"]))
    t("refusee apres revocation", apikeys.verify(cle) is None)
    t("revoquer deux fois ne reussit pas", not apikeys.revoke(fiche["id"]))
    # Revoked, not deleted: "was this key used after I withdrew it?" is a
    # question one asks after the fact.
    ids = [k["id"] for k in apikeys.list_all(with_revoked=True)]
    t("la cle revoquee reste consultable", fiche["id"] in ids)
    t("elle ne figure plus dans la liste courante",
      fiche["id"] not in [k["id"] for k in apikeys.list_all()])


def test_dernier_usage():
    fiche, cle = apikeys.create("sonde")
    t("aucun usage a la creation", fiche["dernier_usage"] is None)
    apikeys.verify(cle)
    vu = [k for k in apikeys.list_all() if k["id"] == fiche["id"]][0]
    t("l'usage est note", vu["dernier_usage"] is not None)


def test_portee():
    """A key opens ONLY `/api/v1/`. This is the central check."""
    from romule import apiv1
    ouverts = ["/api/v1/library", "/api/v1/health", "/api/v1/jobs/abc"]
    fermes = ["/api/comptes", "/api/compte-supprimer", "/api/config",
              "/api/scan", "/", "/app.js", "/auth/connexion",
              # The shapes that bypass a naive prefix comparison.
              "/api/v1", "/api/v1x/library", "/api/../api/comptes",
              "//api/v1/library", "/API/V1/library"]
    for p in ouverts:
        t("cle admise sur %s" % p, apiv1.dans_la_portee(p), p)
    for p in fermes:
        t("cle refusee sur %s" % p, not apiv1.dans_la_portee(p), p)


def test_le_fichier_est_prive():
    apikeys.create("droits")
    mode = apikeys.FILE.stat().st_mode & 0o777
    t("le fichier des cles est en 0600", mode == 0o600, oct(mode))


def test_pas_de_scrypt():
    """Slow hardening is right for a password and wrong here.

    scrypt N=2^17 commits ~128 MiB per computation. A key is presented on EVERY
    request: a dashboard's probe would become a way to exhaust the server's
    memory. A random 256-bit secret has no brute-force surface to protect
    anyway.
    """
    src = (Path(__file__).resolve().parent.parent / "apikeys.py").read_text(
        encoding="utf-8")
    code = "\n".join(l for l in src.splitlines()
                     if not l.lstrip().startswith("#"))
    code = code.split('"""')[0] + '"""'.join(code.split('"""')[2:])
    t("apikeys n'appelle pas scrypt", "hashlib.scrypt" not in code)
    t("apikeys compare en temps constant", "compare_digest" in code)


for fn in (test_creation, test_deux_cles_different, test_verification,
           test_revocation, test_dernier_usage, test_portee,
           test_le_fichier_est_prive, test_pas_de_scrypt):
    fn()
print("  %d controles OK, %d echec(s)" % (ok, ko))
sys.exit(1 if ko else 0)
