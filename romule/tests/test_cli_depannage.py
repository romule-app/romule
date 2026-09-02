"""Commandes de depannage : la porte de secours, et ses serrures.

`user passwd` repose un mot de passe SANS connaitre l'ancien. C'est
exactement ce qu'un attaquant cherche, et c'est pourquoi elle n'existe que
sur la ligne de commande : qui peut la lancer a deja les droits du service,
donc l'acces au fichier des comptes. Elle ne donne rien de plus, elle rend
seulement faisable sans se tromper ce que le systeme de fichiers permettait.

Ce que ces tests verifient est donc autant ce qui marche que ce qui reste
refuse : le dernier administrateur, un mot de passe faible, un compte
inconnu, et les secrets qui ne doivent jamais s'afficher.
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


def romule(racine, *args):
    """Lance la commande dans un vrai sous-processus, comme un utilisateur."""
    env = dict(os.environ, ROMULE_ROOT=str(racine), ROMULE_NO_BROWSER="1",
               ROMULE_ADB="/inexistant", NO_COLOR="1")
    r = subprocess.run([sys.executable, "-m", "romule"] + list(args),
                       cwd=str(RACINE), env=env, capture_output=True, text=True,
                       timeout=180)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    racine = Path(tempfile.mkdtemp(prefix="cli-"))
    sys.path.insert(0, str(RACINE))
    os.environ["ROMULE_ROOT"] = str(racine)
    from romule import comptes
    comptes.creer("chef@exemple.fr", "brouette-tranquille-42", "Chef")
    comptes.creer("bob@exemple.fr", "guitare-nuageuse-77", "Bob")

    # --- lister ----------------------------------------------------------
    code, sortie = romule(racine, "user", "list")
    t("`user list` reussit", code == 0, sortie)
    t("les deux comptes apparaissent",
      "chef@exemple.fr" in sortie and "bob@exemple.fr" in sortie, sortie)
    t("le premier compte est marque administrateur",
      "oui" in sortie.split("chef@exemple.fr")[1].split("\n")[0], sortie)
    # Le fichier des comptes contient des empreintes scrypt. Les afficher
    # serait offrir a un rapport de bogue de quoi attaquer hors ligne.
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
      comptes.verifier_mdp("clavier-orageux-99", u["hash"]))
    t("l'ancien ne l'est plus",
      not comptes.verifier_mdp("brouette-tranquille-42", u["hash"]))

    # Un compte bloque par des echecs repetes doit repartir : sinon la
    # reinitialisation reussit et la connexion echoue quand meme.
    d["comptes"][0]["echecs"] = 9
    d["comptes"][0]["bloque"] = 2 ** 31
    (racine / "_romule-comptes.json").write_text(json.dumps(d))
    romule(racine, "user", "passwd", "chef@exemple.fr", "--mdp", "tourterelle-vive-31")
    d = json.loads((racine / "_romule-comptes.json").read_text())
    t("le blocage est leve par la reinitialisation",
      d["comptes"][0]["echecs"] == 0 and d["comptes"][0]["bloque"] == 0,
      d["comptes"][0])

    # --- ce qui doit etre refuse -----------------------------------------
    code, sortie = romule(racine, "user", "passwd", "chef@exemple.fr", "--mdp", "court")
    t("un mot de passe trop faible est refuse", code == 1, sortie)
    t("et le refus dit pourquoi", "12" in sortie, sortie)

    code, sortie = romule(racine, "user", "passwd", "vide@exemple.fr", "--mdp", "clavier-orageux-99")
    t("un compte inconnu est refuse", code == 1, sortie)

    romule(racine, "user", "admin", "bob@exemple.fr")
    romule(racine, "user", "admin", "chef@exemple.fr", "--retirer")
    code, sortie = romule(racine, "user", "admin", "bob@exemple.fr", "--retirer")
    # Une instance que personne ne peut administrer se repare a la main, dans
    # un fichier. La commande ne doit donc pas pouvoir y mener.
    t("le dernier administrateur ne peut pas etre retire", code == 1, sortie)
    t("et le refus l'explique", "administrateur" in sortie.lower(), sortie)

    code, sortie = romule(racine, "user", "rm", "bob@exemple.fr")
    t("une suppression sans --oui ne supprime rien", code == 1, sortie)
    code, sortie = romule(racine, "user", "list")
    t("le compte est toujours la", "bob@exemple.fr" in sortie, sortie)

    # --- config ------------------------------------------------------------
    code, sortie = romule(racine, "config", "set", "trash_days", "7")
    t("`config set` accepte un entier", code == 0 and "7" in sortie, sortie)
    code, sortie = romule(racine, "config", "get", "trash_days")
    t("`config get` le relit", sortie.strip() == "7", sortie)
    # Sans lecture JSON, « false » deviendrait la chaine « false », qui est vraie.
    romule(racine, "config", "set", "incremental", "false")
    cfg = json.loads((racine / "_romule-config.json").read_text())
    t("« false » devient un booleen, pas une chaine",
      cfg["incremental"] is False, cfg.get("incremental"))
    code, sortie = romule(racine, "config", "set", "trash_days", "sept")
    t("un type incorrect est refuse", code == 1, sortie)
    code, sortie = romule(racine, "config", "set", "cle_inventee", "x")
    t("un reglage inconnu est refuse", code == 1, sortie)

    # --- les secrets ne s'affichent pas -------------------------------------
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
    # Un rapport de diagnostic finit colle dans un ticket public.
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
