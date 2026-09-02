"""Un reglage que le serveur refuse d'ecrire est un reglage qui ment.

`/api/config` ne copie que les cles d'une liste blanche. C'est juste : sans
elle, un client pourrait ecrire n'importe quoi dans le fichier d'etat.

Mais une cle qui existe dans `config.DEFAULTS`, que l'interface affiche, et que
cette liste ne connait pas produit le pire des comportements : le champ
s'affiche, on le remplit, on enregistre, le serveur repond 200 — et rien n'a
change. C'est arrive avec `oidc_admin_groupes` : le reglage etait declare,
l'interface le montrait, le serveur le jetait, et le role SSO ne s'activait
jamais. Aucune erreur nulle part.

Ce controle tient les deux sens :

  * la liste blanche ne cite que des cles qui EXISTENT — sinon c'est une faute
    de frappe qui ne fera jamais rien ;
  * toute cle affichee par l'interface est dans la liste blanche — sauf celles
    qui n'ont rien a y faire, nommees ici avec leur raison.
"""
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE))
from romule import config                                       # noqa: E402

ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % nom)
    else:
        ko += 1
        print("  ECHEC %s   %s" % (nom, detail))


# Ce que l'interface ne doit PAS pouvoir ecrire, et pourquoi.
HORS_INTERFACE = {
    # Le secret qui signe les sessions. Le laisser modifier reviendrait a
    # deconnecter tout le monde, ou pire, a le fixer a une valeur connue.
    "auth_secret",
    # Le dossier des jeux se choisit par `/api/ludotheque`, qui verifie que le
    # chemin est autorise et qu'il existe. Passer par les reglages generiques
    # contournerait ce controle.
    "library_path",
    # Ecrites par l'outil lui-meme au fil de son usage, jamais saisies.
    "wifi_addr", "emuready_device", "emuready_device_nom",
    "systemes_perso", "emulateur_paquet",
    # Les destinations de notification passent par `/api/notif-creer`, qui
    # verifie le schema de l'adresse (`reseau.verifier`) et borne leur nombre.
    # Les laisser entrer par les reglages generiques contournerait les deux —
    # et une URL de reglage qui devient un `file://` est justement le defaut
    # que `reseau.py` existe pour empecher.
    "notif_destinations",
}


def liste_blanche():
    """Les cles que `/api/config` accepte, lues dans le source du serveur."""
    src = (config.PKG / "server.py").read_text(encoding="utf-8")
    d = src.index('elif p == "/api/config":')
    bloc = src[d:d + 4000]
    m = re.search(r"for k in \(([^)]*)\):", bloc, re.S)
    return set(re.findall(r'"([a-z_]+)"', m.group(1))) if m else set()


def test_la_liste_ne_cite_que_des_cles_reelles():
    inconnues = sorted(liste_blanche() - set(config.DEFAULTS))
    t("la liste blanche ne cite aucune cle inexistante", not inconnues, inconnues)


def test_tout_reglage_saisi_est_acceptable():
    manquantes = sorted(set(config.DEFAULTS) - liste_blanche() - HORS_INTERFACE)
    t("tout reglage modifiable figure dans la liste blanche",
      not manquantes,
      "declares mais jamais ecrits : %s" % manquantes)


def test_les_exceptions_existent_encore():
    """Une exception qui designe une cle disparue n'exempte plus rien : elle
    masque juste le controle pour un nom qui n'existe pas."""
    fantomes = sorted(HORS_INTERFACE - set(config.DEFAULTS))
    t("les exceptions designent des cles reelles", not fantomes, fantomes)


for fn in (test_la_liste_ne_cite_que_des_cles_reelles,
           test_tout_reglage_saisi_est_acceptable,
           test_les_exceptions_existent_encore):
    fn()
print("  %d controles OK, %d echec(s)" % (ok, ko))
sys.exit(1 if ko else 0)
