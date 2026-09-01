"""Les cles d'API : ce qu'elles ouvrent, et surtout ce qu'elles n'ouvrent pas.

Le controle qui compte n'est pas « une cle valide ouvre `/api/v1` » — il est
« une cle valide ne peut PAS atteindre `/api/comptes` ». Un test qui verifie
seulement la premiere moitie laisserait passer une cle qui ouvre tout, ce qui
est exactement le defaut qu'une cle d'API est censee eviter : donner a un
tableau de bord le droit de supprimer des comptes.

La portee est verifiee ici sur la fonction de decision elle-meme ; le parcours
complet par HTTP l'est dans `test_apiv1.py`.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Le magasin doit vivre dans un dossier jetable : ce test cree et revoque des
# cles, et il n'a rien a faire dans le fichier d'etat de l'utilisateur.
_TMP = Path(tempfile.mkdtemp(prefix="romule-cles-"))
from romule import apikeys                                      # noqa: E402
apikeys.FICHIER = _TMP / "_romule-cles.json"

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
    fiche, cle = apikeys.creer("tableau de bord")
    t("la cle porte le marqueur", cle.startswith("rml_"), cle[:8])
    t("la cle est longue", len(cle) >= 40, len(cle))
    t("le nom est conserve", fiche["nom"] == "tableau de bord")
    t("le prefixe est court", len(fiche["prefixe"]) == 12, fiche["prefixe"])
    t("la cle en clair n'est PAS dans la fiche",
      cle not in repr(fiche), repr(fiche)[:80])
    # Le fichier d'etat ne doit contenir aucune cle en clair : c'est ce qui
    # rend sa fuite inoffensive pour les cles elles-memes.
    brut = apikeys.FICHIER.read_text(encoding="utf-8")
    t("le fichier ne contient pas la cle en clair", cle not in brut)
    t("le fichier contient une empreinte", "empreinte" in brut)


def test_deux_cles_different():
    _, a = apikeys.creer("a")
    _, b = apikeys.creer("b")
    t("deux cles creees a la suite different", a != b)


def test_verification():
    fiche, cle = apikeys.creer("script")
    t("une cle valide est reconnue",
      (apikeys.verifier(cle) or {}).get("id") == fiche["id"])
    t("une cle inconnue est refusee", apikeys.verifier("rml_inexistante") is None)
    t("une chaine vide est refusee", apikeys.verifier("") is None)
    t("None est refuse", apikeys.verifier(None) is None)
    t("un secret sans marqueur est refuse",
      apikeys.verifier(cle[4:]) is None)
    # Le meme secret a un caractere pres : la comparaison porte sur
    # l'empreinte entiere, pas sur le prefixe qui sert a retrouver la fiche.
    faux = cle[:-1] + ("a" if cle[-1] != "a" else "b")
    t("un caractere different suffit a refuser", apikeys.verifier(faux) is None)


def test_revocation():
    fiche, cle = apikeys.creer("a jeter")
    t("valide avant revocation", apikeys.verifier(cle) is not None)
    t("la revocation reussit", apikeys.revoquer(fiche["id"]))
    t("refusee apres revocation", apikeys.verifier(cle) is None)
    t("revoquer deux fois ne reussit pas", not apikeys.revoquer(fiche["id"]))
    # Revoquee, pas supprimee : « cette cle a-t-elle servi apres que je l'ai
    # retiree ? » est une question qu'on se pose apres coup.
    ids = [k["id"] for k in apikeys.liste(avec_revoquees=True)]
    t("la cle revoquee reste consultable", fiche["id"] in ids)
    t("elle ne figure plus dans la liste courante",
      fiche["id"] not in [k["id"] for k in apikeys.liste()])


def test_dernier_usage():
    fiche, cle = apikeys.creer("sonde")
    t("aucun usage a la creation", fiche["dernier_usage"] is None)
    apikeys.verifier(cle)
    vu = [k for k in apikeys.liste() if k["id"] == fiche["id"]][0]
    t("l'usage est note", vu["dernier_usage"] is not None)


def test_portee():
    """Une cle n'ouvre QUE `/api/v1/`. C'est le controle central."""
    from romule import apiv1
    ouverts = ["/api/v1/library", "/api/v1/health", "/api/v1/jobs/abc"]
    fermes = ["/api/comptes", "/api/compte-supprimer", "/api/config",
              "/api/scan", "/", "/app.js", "/auth/connexion",
              # Les formes qui contournent une comparaison naive de prefixe.
              "/api/v1", "/api/v1x/library", "/api/../api/comptes",
              "//api/v1/library", "/API/V1/library"]
    for p in ouverts:
        t("cle admise sur %s" % p, apiv1.dans_la_portee(p), p)
    for p in fermes:
        t("cle refusee sur %s" % p, not apiv1.dans_la_portee(p), p)


def test_le_fichier_est_prive():
    apikeys.creer("droits")
    mode = apikeys.FICHIER.stat().st_mode & 0o777
    t("le fichier des cles est en 0600", mode == 0o600, oct(mode))


def test_pas_de_scrypt():
    """Le durcissement lent est correct pour un mot de passe et faux ici.

    scrypt N=2^17 mobilise ~128 Mio par calcul. Une cle est presentee a CHAQUE
    requete : une sonde de tableau de bord deviendrait un moyen de saturer la
    memoire du serveur. Un secret aleatoire de 256 bits n'a de toute facon
    aucune surface de force brute a proteger.
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
