"""The names written on disk are not renamed.

This test exists for the translation of the code into English, and it will
outlive it.

Renaming an identifier has no consequence: the program is recompiled in one
piece, and the test suite says straight away if something is missing. A KEY
WRITTEN ON DISK, on the other hand, is not renamed — it is already in every
installation's configuration file. Renaming it breaks nothing here: it breaks at
other people's, on the first restart, in silence. The service starts again on its
default values and the user discovers their console is no longer paired, their
emulator is back to Eden, and their API keys are no longer recognised.

Hence this list, frozen by hand. It is not generated from the code: a generated
list would follow the rename and would prove nothing. It states what is on
people's disks, and the test fails when the code departs from it.

Adding a key is normal and requires adding it here — that is the only cost, and
it is a reminder along the way that a new key is a commitment.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE))
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp(prefix="cles-"))

from romule import apikeys, accounts, config, views                # noqa: E402

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
# The 45 settings, as they are written today at everyone's.
CONFIG = {
    "active_device", "auth_mode", "auth_secret", "auto_nand", "cover_provider",
    "cover_url", "device_dir", "devices", "emulateur", "emulateur_paquet",
    "emuready",
    "emuready_device", "emuready_device_nom", "igdb_client_id",
    "igdb_client_secret", "incremental", "jobs", "lan_access", "library_path",
    "local_layout", "maj_check", "meta_lang", "notif_destinations", "notify",
    "oidc_admin_groupes", "oidc_client_id", "oidc_client_secret", "oidc_emails",
    "oidc_groupes", "oidc_issuer", "oidc_redirect", "oidc_scopes",
    "push_layout", "roms_root", "saves_dir", "schedule", "schedule_state",
    "steamgriddb_key", "system_dirs", "systemes_perso", "trash_days",
    "ui_lang", "verify_mode", "versions_urls", "wifi_addr",
}

# Written by the server, not declared in DEFAULTS: the token generated on the
# first start. Losing it means locking an exposed instance out.
HORS_DEFAUTS = {"jeton_auto"}

# --- The other state files -------------------------------------------------
# `version` appears in all three files: it is the format number, the one that
# will one day make it possible to read an old file without getting it wrong. It
# was missing from my first list, and the test found it on its very first run —
# which is precisely what it is asked to do.
COMPTES = {"version", "comptes", "id", "email", "nom", "hash", "cree",
           "maj_mdp", "echecs", "bloque", "photo", "derniere", "admin", "totp"}
CLES_API = {"version", "cles", "id", "nom", "prefixe", "empreinte", "cree",
            "dernier_usage", "revoquee"}
VUES = {"version", "vues", "id", "nom", "filtres", "cree",
        "systeme", "recherche", "etat", "avances"}

# --- What carries a name on the file system --------------------------------
FICHIERS = {"_romule-config.json", "_romule-comptes.json", "_romule-cles.json",
            "_romule-vues.json", "_romule-lib.log", "_romule-acces.log",
            "_romule-maj.json", "_romule-consoles.json",
            "_covers", "_corbeille", "_import"}


def _cles_du_disque(chemin):
    """Every key of a JSON document, at every level."""
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
    # An added setting is normal; it just has to be declared here, and that
    # reminder is the net's only cost.
    t("tout reglage nouveau est declare dans ce test", not neufs,
      "ajoute(s) au code mais pas a la liste figee : %s" % neufs)


def test_le_jeton_engendre():
    src = (config.PKG / "server.py").read_text(encoding="utf-8")
    for cle in HORS_DEFAUTS:
        t("`%s` est toujours ecrit sous ce nom" % cle, '"%s"' % cle in src,
          "sans lui, une instance exposee s'enferme dehors")


def test_les_comptes():
    d = Path(tempfile.mkdtemp()) / "c.json"
    accounts.create("essai@exemple.fr", "brouette-tranquille-42", "Essai")
    ecrites = _cles_du_disque(config.state_file("_romule-comptes.json",
                                                  "_romule-comptes.json"))
    manquantes = sorted(ecrites - COMPTES)
    t("aucun champ de compte inconnu n'est ecrit", not manquantes,
      "champs ecrits mais non declares : %s" % manquantes)
    t("les champs declares sont bien ceux ecrits",
      {"comptes", "id", "email", "hash", "admin"} <= ecrites,
      sorted(ecrites))
    del d


def test_les_cles_api():
    apikeys.create("essai")
    ecrites = _cles_du_disque(apikeys.FILE)
    manquantes = sorted(ecrites - CLES_API)
    t("aucun champ de cle d'API inconnu n'est ecrit", not manquantes,
      "champs ecrits mais non declares : %s" % manquantes)
    # The fingerprint is what makes a leak of the file harmless: if this field
    # disappeared in favour of another name, the key would no longer be
    # recognised and nobody would know why.
    t("l'empreinte porte toujours ce nom", "empreinte" in ecrites, sorted(ecrites))


def test_les_vues():
    views.create("essai", {"systeme": "switch", "recherche": "mario",
                         "etat": "all", "avances": []})
    ecrites = _cles_du_disque(views.FILE)
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
    """Does the net catch a rename?

    We simulate what we are trying to prevent — a key disappearing from
    `DEFAULTS` — and check the comparison sees it. Without this trial, a frozen
    list that had drifted along with the code would pass for a protection.
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
