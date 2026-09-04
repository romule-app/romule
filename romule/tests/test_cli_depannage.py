"""Troubleshooting commands: the emergency door, and its locks.

`user passwd` sets a password again WITHOUT knowing the old one. That is exactly
what an attacker is after, and it is why it exists only on the command line:
whoever can run it already has the service's rights, so access to the accounts
file. It grants nothing more, it merely makes doable without mistakes what the
file system already allowed.

So what these tests check is as much what works as what stays refused: the last
administrator, a weak password, an unknown account, and the secrets that must
never be displayed.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
ok = fail = 0


def t(nom, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("      OK   %s" % nom)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (nom, detail))


def lancer(racine, *args, chemin=None):
    """Runs the command in a real sub-process, as a user would.

    Returns (code, stdout, stderr) SEPARATELY: that distinction is what matters
    for a command whose output is read by a program.
    """
    env = dict(os.environ, ROMULE_ROOT=str(racine), ROMULE_NO_BROWSER="1",
               ROMULE_ADB="/inexistant", NO_COLOR="1")
    if chemin is not None:
        env["PATH"] = chemin
    r = subprocess.run([sys.executable, "-m", "romule"] + list(args),
                       cwd=str(RACINE), env=env, capture_output=True, text=True,
                       timeout=180)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def romule(racine, *args):
    """Both outputs together, for the checks that do not tell them apart."""
    code, out, err = lancer(racine, *args)
    return code, out + err


def main():
    racine = Path(tempfile.mkdtemp(prefix="cli-"))
    sys.path.insert(0, str(RACINE))
    os.environ["ROMULE_ROOT"] = str(racine)
    from romule import accounts
    accounts.create("chef@exemple.fr", "brouette-tranquille-42", "Chef")
    accounts.create("bob@exemple.fr", "guitare-nuageuse-77", "Bob")

    # --- lister ----------------------------------------------------------
    code, sortie = romule(racine, "user", "list")
    t("`user list` reussit", code == 0, sortie)
    t("les deux comptes apparaissent",
      "chef@exemple.fr" in sortie and "bob@exemple.fr" in sortie, sortie)
    t("le premier compte est marque administrateur",
      "oui" in sortie.split("chef@exemple.fr")[1].split("\n")[0], sortie)
    # The accounts file holds scrypt hashes. Displaying them would hand a bug
    # report the material for an offline attack.
    t("aucune empreinte de mot de passe n'est affichee",
      "scrypt" not in sortie and "$" not in sortie, sortie)

    # --- reposer un mot de passe -----------------------------------------
    code, sortie = romule(racine, "user", "passwd", "chef@exemple.fr",
                          "--mdp", "clavier-orageux-99")
    t("`user passwd` reussit", code == 0, sortie)
    t("il dit que les sessions sont coupees",
      "session" in sortie.lower(), sortie)
    d = json.loads((racine / "_romule-comptes.json").read_text())
    u = [x for x in d["comptes"] if x["email"] == "chef@exemple.fr"][0]
    t("le nouveau mot de passe est accepte",
      accounts.verify_password("clavier-orageux-99", u["hash"]))
    t("l'ancien ne l'est plus",
      not accounts.verify_password("brouette-tranquille-42", u["hash"]))

    # An account locked by repeated failures must start again: otherwise the
    # reset succeeds and the login fails all the same.
    d["comptes"][0]["echecs"] = 9
    d["comptes"][0]["bloque"] = 2 ** 31
    (racine / "_romule-comptes.json").write_text(json.dumps(d))
    romule(racine, "user", "passwd", "chef@exemple.fr", "--mdp", "tourterelle-vive-31")
    d = json.loads((racine / "_romule-comptes.json").read_text())
    t("le blocage est leve par la reinitialisation",
      d["comptes"][0]["echecs"] == 0 and d["comptes"][0]["bloque"] == 0,
      d["comptes"][0])

    # --- what must be refused --------------------------------------------
    code, sortie = romule(racine, "user", "passwd", "chef@exemple.fr", "--mdp", "court")
    t("un mot de passe trop faible est refuse", code == 1, sortie)
    t("et le refus dit pourquoi", "12" in sortie, sortie)

    code, sortie = romule(racine, "user", "passwd", "vide@exemple.fr", "--mdp", "clavier-orageux-99")
    t("un compte inconnu est refuse", code == 1, sortie)

    romule(racine, "user", "admin", "bob@exemple.fr")
    romule(racine, "user", "admin", "chef@exemple.fr", "--retirer")
    code, sortie = romule(racine, "user", "admin", "bob@exemple.fr", "--retirer")
    # An instance nobody can administer is repaired by hand, in a file. So the
    # command must not be able to lead there.
    t("le dernier administrateur ne peut pas etre retire", code == 1, sortie)
    t("et le refus l'explique", "administrateur" in sortie.lower(), sortie)

    code, sortie = romule(racine, "user", "rm", "bob@exemple.fr")
    t("une suppression sans --oui ne supprime rien", code == 1, sortie)
    code, sortie = romule(racine, "user", "list")
    t("le compte est toujours la", "bob@exemple.fr" in sortie, sortie)

    # --- config ------------------------------------------------------------
    code, sortie = romule(racine, "config", "set", "trash_days", "7")
    t("`config set` accepte un entier", code == 0 and "7" in sortie, sortie)
    code, out, err = lancer(racine, "config", "get", "trash_days")
    t("`config get` le relit", out.strip() == "7", (out, err))

    # The defect CI found and my machine hid: the preliminary notices ("nsz
    # absent — ...") went to STDOUT, so `VALUE=$(romule config get x)` captured
    # them along with the value. We force the tools' absence here, instead of
    # hoping they are missing: the check must hold on every machine, not only on
    # those without `nsz`.
    vide = str(racine / "aucun-outil-ici")
    os.makedirs(vide, exist_ok=True)
    code, out, err = lancer(racine, "config", "get", "trash_days", chemin=vide)
    t("un outil absent produit bien un avis", "absent" in err, (out, err))
    t("mais l'avis va sur stderr, pas sur stdout",
      out.strip() == "7", (out, err))
    # Without JSON parsing, "false" would become the string "false", which is
    # truthy.
    romule(racine, "config", "set", "incremental", "false")
    cfg = json.loads((racine / "_romule-config.json").read_text())
    t("« false » devient un booleen, pas une chaine",
      cfg["incremental"] is False, cfg.get("incremental"))
    code, sortie = romule(racine, "config", "set", "trash_days", "sept")
    t("un type incorrect est refuse", code == 1, sortie)
    code, sortie = romule(racine, "config", "set", "cle_inventee", "x")
    t("un reglage inconnu est refuse", code == 1, sortie)

    # --- the secrets are not displayed --------------------------------------
    cfg["auth_secret"] = "un-secret-de-signature"
    cfg["steamgriddb_key"] = "une-cle-sgdb"
    cfg["notif_destinations"] = [{"id": "1", "nom": "salon",
                                  "url": "https://discord.com/api/webhooks/1/TRES-SECRET"}]
    (racine / "_romule-config.json").write_text(json.dumps(cfg))
    code, sortie = romule(racine, "config", "list")
    t("`config list` masque le secret de session",
      "un-secret-de-signature" not in sortie, sortie)
    t("`config list` masque la cle SteamGridDB",
      "une-cle-sgdb" not in sortie, sortie)
    t("mais il dit que la valeur existe", "masque" in sortie, sortie)

    # --- doctor --------------------------------------------------------------
    code, sortie = romule(racine, "doctor")
    t("`doctor` reussit", code == 0, sortie[-300:])
    for attendu in ("Romule", "Python", "ROMULE_ROOT", "Comptes", "adb",
                    "Notifications", "ROMULE_LOG"):
        t("doctor rapporte : %s" % attendu, attendu in sortie, "")
    # A diagnostic report ends up pasted into a public ticket.
    t("doctor ne divulgue aucun secret",
      "un-secret-de-signature" not in sortie and "une-cle-sgdb" not in sortie
      and "TRES-SECRET" not in sortie, sortie)
    t("doctor ne divulgue pas l'adresse du webhook",
      "discord.com/api/webhooks" not in sortie, sortie)

    print("   ------------------------------------------------")
    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
