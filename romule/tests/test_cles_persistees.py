"""Les noms ecrits sur le disque ne se renomment pas.

Ce test existe pour la traduction du code en anglais, et il y survivra.

Un identifiant qu'on renomme est sans consequence : le programme est recompile
d'un bloc, et la suite de tests dit tout de suite si quelque chose manque. Une
CLE ECRITE SUR DISQUE, elle, ne se renomme pas — elle est deja dans le fichier
de configuration de chaque installation. La renommer ne casse rien ici : ca
casse chez les autres, au premier redemarrage, en silence. Le service repart
sur ses valeurs par defaut et l'utilisateur decouvre que sa console n'est plus
appairee, que son emulateur est revenu a Eden, et que ses cles d'API ne sont
plus reconnues.

D'ou cette liste, figee a la main. Elle n'est pas engendree depuis le code :
une liste engendree suivrait le renommage et ne prouverait rien. Elle dit ce
qui est sur le disque des gens, et le test echoue quand le code s'en ecarte.

Ajouter une cle est normal et demande de l'ajouter ici — c'est le seul cout,
et il rappelle au passage qu'une cle nouvelle est un engagement.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE))
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp(prefix="cles-"))

from romule import apikeys, comptes, config, vues                 # noqa: E402

ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % nom)
    else:
        ko += 1
        print("  ECHEC %s   %s" % (nom, detail))


# --- `_romule-config.json` -------------------------------------------------
#
# Les 41 reglages, tels qu'ils sont ecrits aujourd'hui chez tout le monde.
CONFIG = {
    "auth_mode", "auth_secret", "auto_nand", "cover_provider", "cover_url",
    "device_dir", "emulateur", "emulateur_paquet", "emuready",
    "emuready_device", "emuready_device_nom", "igdb_client_id",
    "igdb_client_secret", "incremental", "jobs", "lan_access", "library_path",
    "local_layout", "maj_check", "meta_lang", "notif_destinations", "notify",
    "oidc_admin_groupes", "oidc_client_id", "oidc_client_secret", "oidc_emails",
    "oidc_groupes", "oidc_issuer", "oidc_redirect", "oidc_scopes",
    "push_layout", "roms_root", "saves_dir", "steamgriddb_key",
    "system_dirs", "systemes_perso", "trash_days", "ui_lang", "verify_mode",
    "versions_urls", "wifi_addr",
}

# Ecrite par le serveur, pas declaree dans DEFAULTS : le jeton engendre au
# premier demarrage. La perdre, c'est enfermer dehors une instance exposee.
HORS_DEFAUTS = {"jeton_auto"}

# --- Les autres fichiers d'etat --------------------------------------------
# `version` figure dans les trois fichiers : c'est le numero de format, celui
# qui permettra un jour de lire un ancien fichier sans se tromper. Il manquait
# a ma premiere liste, et le test l'a trouve des son premier passage — ce qui
# est precisement ce qu'on lui demande.
COMPTES = {"version", "comptes", "id", "email", "nom", "hash", "cree",
           "maj_mdp", "echecs", "bloque", "photo", "derniere", "admin", "totp"}
CLES_API = {"version", "cles", "id", "nom", "prefixe", "empreinte", "cree",
            "dernier_usage", "revoquee"}
VUES = {"version", "vues", "id", "nom", "filtres", "cree",
        "systeme", "recherche", "etat", "avances"}

# --- Ce qui porte un nom sur le systeme de fichiers -------------------------
FICHIERS = {"_romule-config.json", "_romule-comptes.json", "_romule-cles.json",
            "_romule-vues.json", "_romule-lib.log", "_romule-acces.log",
            "_romule-maj.json", "_covers", "_corbeille", "_import"}


def _cles_du_disque(chemin):
    """Toutes les cles d'un JSON, a tous les niveaux."""
    def descendre(x):
        if isinstance(x, dict):
            for k, v in x.items():
                yield k
                yield from descendre(v)
        elif isinstance(x, list):
            for v in x:
                yield from descendre(v)
    return set(descendre(json.loads(Path(chemin).read_text(encoding="utf-8"))))


def test_les_reglages():
    reels = set(config.DEFAULTS)
    partis = sorted(CONFIG - reels)
    t("aucun reglage n'a disparu ni change de nom", not partis,
      "ces cles sont sur le disque de chaque installation : %s" % partis)
    neufs = sorted(reels - CONFIG)
    # Un reglage ajoute est normal ; il faut juste le declarer ici, et ce
    # rappel est le seul cout du filet.
    t("tout reglage nouveau est declare dans ce test", not neufs,
      "ajoute(s) au code mais pas a la liste figee : %s" % neufs)


def test_le_jeton_engendre():
    src = (config.PKG / "server.py").read_text(encoding="utf-8")
    for cle in HORS_DEFAUTS:
        t("`%s` est toujours ecrit sous ce nom" % cle, '"%s"' % cle in src,
          "sans lui, une instance exposee s'enferme dehors")


def test_les_comptes():
    d = Path(tempfile.mkdtemp()) / "c.json"
    comptes.creer("essai@exemple.fr", "brouette-tranquille-42", "Essai")
    ecrites = _cles_du_disque(config.fichier_etat("_romule-comptes.json",
                                                  "_romule-comptes.json"))
    manquantes = sorted(ecrites - COMPTES)
    t("aucun champ de compte inconnu n'est ecrit", not manquantes,
      "champs ecrits mais non declares : %s" % manquantes)
    t("les champs declares sont bien ceux ecrits",
      {"comptes", "id", "email", "hash", "admin"} <= ecrites,
      sorted(ecrites))
    del d


def test_les_cles_api():
    apikeys.creer("essai")
    ecrites = _cles_du_disque(apikeys.FICHIER)
    manquantes = sorted(ecrites - CLES_API)
    t("aucun champ de cle d'API inconnu n'est ecrit", not manquantes,
      "champs ecrits mais non declares : %s" % manquantes)
    # L'empreinte est ce qui rend une fuite du fichier inoffensive : si ce
    # champ disparaissait au profit d'un autre nom, la cle ne serait plus
    # reconnue et personne ne saurait pourquoi.
    t("l'empreinte porte toujours ce nom", "empreinte" in ecrites, sorted(ecrites))


def test_les_vues():
    vues.creer("essai", {"systeme": "switch", "recherche": "mario",
                         "etat": "all", "avances": []})
    ecrites = _cles_du_disque(vues.FICHIER)
    manquantes = sorted(ecrites - VUES)
    t("aucun champ de vue inconnu n'est ecrit", not manquantes,
      "champs ecrits mais non declares : %s" % manquantes)


def test_les_noms_de_fichiers():
    src = "\n".join(p.read_text(encoding="utf-8")
                    for p in (config.PKG).rglob("*.py"))
    absents = sorted(f for f in FICHIERS if f not in src)
    t("aucun fichier ou dossier d'etat n'a change de nom", not absents,
      "ces noms existent sur le disque des installations : %s" % absents)


def epreuve():
    """Le filet attrape-t-il un renommage ?

    On simule ce qu'on cherche a empecher — une cle qui disparait de
    `DEFAULTS` — et on verifie que la comparaison le voit. Sans cette
    epreuve, une liste figee qui aurait derive avec le code passerait pour
    une protection.
    """
    faux = set(CONFIG) - {"emulateur"}
    if not (CONFIG - faux):
        print("  EPREUVE ECHOUEE : la comparaison ne voit pas une cle retiree")
        return False
    if CONFIG - set(CONFIG):
        print("  EPREUVE ECHOUEE : elle signale un ensemble identique")
        return False
    return True


if not epreuve():
    sys.exit(2)

for fn in (test_les_reglages, test_le_jeton_engendre, test_les_comptes,
           test_les_cles_api, test_les_vues, test_les_noms_de_fichiers):
    fn()
print("  %d controles OK, %d echec(s)" % (ok, ko))
sys.exit(1 if ko else 0)
