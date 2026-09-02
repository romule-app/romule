"""Notifications sortantes : la forme attendue par chaque service, et le silence.

Deux exigences egales. Ce qui part doit avoir la forme que le destinataire
comprend — un JSON generique envoye a ntfy ne produit rien de lisible. Et rien
ne doit partir quand rien n'est configure : un service auto-heberge qui appelle
l'exterieur sans qu'on le lui demande est un probleme, pas une fonctionnalite.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp())
sys.path.insert(0, str(ICI.parent.parent))

PORT = int(os.environ.get("LUDO_PORT_NOTIF", "9931"))
BASE = "http://127.0.0.1:%d" % PORT
ok = fail = 0


def t(nom, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("      OK   %s" % nom)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (nom, detail))


def recu():
    return json.load(urllib.request.urlopen(BASE + "/_recu"))


def vider():
    urllib.request.urlopen(BASE + "/_vider").read()


def cfg_avec(*destinations):
    return {"notif_destinations": list(destinations)}


def main():
    srv = subprocess.Popen([sys.executable, str(ICI / "faux_notif.py"), str(PORT)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    try:
        from romule import notifs

        # --- la deduction du service depuis l'adresse -----------------------
        for url, attendu in (
                ("https://discord.com/api/webhooks/1/x", "discord"),
                ("https://discordapp.com/api/webhooks/1/x", "discord"),
                ("https://hooks.slack.com/services/T/B/x", "slack"),
                ("https://api.telegram.org/bot1:AA/sendMessage?chat_id=2", "telegram"),
                ("https://ntfy.sh/sujet", "ntfy"),
                ("https://ntfy.chez-moi.fr/sujet", "ntfy"),
                ("https://gotify.exemple.fr/message?token=A", "gotify"),
                ("https://exemple.fr/crochet", "webhook")):
            t("deduit %s" % attendu, notifs.deviner(url) == attendu,
              "%s -> %s" % (url, notifs.deviner(url)))

        # --- la FORME envoyee, service par service --------------------------
        formes = {
            "discord": lambda c: "embeds" in json.loads(c["corps"]),
            "slack": lambda c: "text" in json.loads(c["corps"]),
            "telegram": lambda c: c["corps"].startswith("text="),
            "gotify": lambda c: {"title", "message", "priority"} <= set(json.loads(c["corps"])),
            "webhook": lambda c: json.loads(c["corps"]).get("service") == "romule",
        }
        for service, correcte in formes.items():
            vider()
            cfg = cfg_avec({"id": "1", "url": BASE + "/x", "service": service,
                            "evenements": ["tache_ok"]})
            n = notifs.envoyer("tache_ok", "Titre", "Corps", "ok", cfg, attendre=True)
            r = recu()
            t("%s : un envoi part" % service, n == 1 and len(r) == 1, r)
            t("%s : la forme est celle du service" % service,
              bool(r) and correcte(r[0]), r[0]["corps"][:90] if r else "")

        # ntfy est a part : le titre voyage en EN-TETE, pas dans le corps.
        vider()
        cfg = cfg_avec({"id": "1", "url": BASE + "/sujet", "service": "ntfy",
                        "evenements": ["tache_ok"]})
        notifs.envoyer("tache_ok", "Pokémon terminé", "Corps", "error", cfg, attendre=True)
        r = recu()
        t("ntfy : le titre est un en-tete", bool(r) and r[0]["titre"], r)
        # Un en-tete HTTP ne porte pas d'accent : `Title: Pokémon` casserait
        # l'envoi entier, et c'est un nom de jeu parfaitement ordinaire.
        t("ntfy : le titre est reduit a l'ASCII",
          bool(r) and all(ord(c) < 128 for c in r[0]["titre"]), r[0]["titre"] if r else "")
        t("ntfy : la gravite devient une priorite",
          bool(r) and r[0]["priorite"] == "high", r)

        # --- le silence, qui compte autant ----------------------------------
        vider()
        t("rien de configure, rien n'est envoye",
          notifs.envoyer("tache_ok", "T", "", "ok", {}, attendre=True) == 0
          and recu() == [])

        cfg = cfg_avec({"id": "1", "url": BASE + "/x", "evenements": ["maj"]})
        t("un evenement non souscrit n'envoie rien",
          notifs.envoyer("tache_ok", "T", "", "ok", cfg, attendre=True) == 0)
        t("l'evenement souscrit, lui, part",
          notifs.envoyer("maj", "T", "", "ok", cfg, attendre=True) == 1)

        cfg = cfg_avec({"id": "1", "url": BASE + "/x", "evenements": ["tache_ok"],
                        "actif": False})
        t("une destination desactivee n'envoie rien",
          notifs.envoyer("tache_ok", "T", "", "ok", cfg, attendre=True) == 0)

        # Une liste vide veut dire TOUS les evenements : c'est ce qu'attend
        # quelqu'un qui colle une adresse sans rien cocher.
        cfg = cfg_avec({"id": "1", "url": BASE + "/x", "evenements": []})
        t("aucun evenement coche = tous",
          notifs.envoyer("tache_echec", "T", "", "error", cfg, attendre=True) == 1)

        # --- les pannes ne remontent pas ------------------------------------
        reussi, raison = notifs.tester(BASE + "/refuse")
        t("un 500 est rapporte comme un echec", reussi is False, raison)
        reussi, raison = notifs.tester("http://127.0.0.1:1/rien")
        t("un service injoignable ne leve pas", reussi is False, raison)
        reussi, raison = notifs.tester("file:///etc/passwd")
        t("une adresse `file://` est refusee", reussi is False, raison)
        t("et le refus dit pourquoi", "schema" in raison.lower(), raison)

        cfg = cfg_avec({"id": "1", "url": "http://127.0.0.1:1/rien",
                        "evenements": ["tache_ok"]})
        t("une destination en panne ne fait pas echouer l'envoi",
          notifs.envoyer("tache_ok", "T", "", "ok", cfg, attendre=True) == 1)

        # --- assainissement --------------------------------------------------
        cfg = cfg_avec({"url": ""}, "pas un dict",
                       {"id": "2", "url": BASE + "/x", "evenements": ["inconnu"]})
        d = notifs.destinations(cfg)
        t("les entrees vides ou malformees sont ecartees", len(d) == 1, d)
        t("un evenement inconnu est retire, et la liste retombe sur tous",
          d[0]["evenements"] == list(notifs.EVENEMENTS), d)

        beaucoup = cfg_avec(*[{"id": str(i), "url": BASE + "/x"}
                              for i in range(notifs.MAX_DESTINATIONS + 5)])
        t("le nombre de destinations est borne",
          len(notifs.destinations(beaucoup)) == notifs.MAX_DESTINATIONS)
    finally:
        srv.terminate()
    print("   ------------------------------------------------")
    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
