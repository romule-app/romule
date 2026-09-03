"""A setting the server refuses to write is a setting that lies.

`/api/config` copies only the keys of an allow-list. That is right: without it, a
client could write anything into the state file.

But a key that exists in `config.DEFAULTS`, that the interface displays, and that
this list does not know produces the worst possible behaviour: the field shows,
you fill it in, you save, the server answers 200 — and nothing has changed. It
happened with `oidc_admin_groupes`: the setting was declared, the interface
showed it, the server threw it away, and the SSO role never activated. No error
anywhere.

This check holds in both directions:

  * the allow-list names only keys that EXIST — otherwise it is a typo that will
    never do anything;
  * every key the interface displays is in the allow-list — except those that
    have no business being there, named here with their reason.
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


# What the interface must NOT be able to write, and why.
HORS_INTERFACE = {
    # The secret that signs the sessions. Letting it be edited would log
    # everyone out, or worse, pin it to a known value.
    "auth_secret",
    # The games folder is chosen through `/api/ludotheque`, which checks the path
    # is allowed and that it exists. Going through the generic settings would
    # bypass that check.
    "library_path",
    # Written by the tool itself as it is used, never typed in.
    "wifi_addr", "emuready_device", "emuready_device_nom",
    "systemes_perso", "emulateur_paquet",
    # The notification destinations go through `/api/notif-creer`, which checks
    # the address's scheme (`reseau.verifier`) and bounds their number. Letting
    # them in through the generic settings would bypass both — and a setting's
    # URL that becomes a `file://` is precisely the defect `reseau.py` exists to
    # prevent.
    "notif_destinations",
}


def liste_blanche():
    """The keys `/api/config` accepts, read from the server's source."""
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
    """An exception naming a key that has disappeared exempts nothing any more:
    it merely hides the check for a name that does not exist."""
    fantomes = sorted(HORS_INTERFACE - set(config.DEFAULTS))
    t("les exceptions designent des cles reelles", not fantomes, fantomes)


for fn in (test_la_liste_ne_cite_que_des_cles_reelles,
           test_tout_reglage_saisi_est_acceptable,
           test_les_exceptions_existent_encore):
    fn()
print("  %d controles OK, %d echec(s)" % (ok, ko))
sys.exit(1 if ko else 0)
