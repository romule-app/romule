"""Traduction : l'interface entiere bascule, les DONNEES ne bougent pas.

Le francais est la cle (principe gettext) et la traduction s'applique au DOM.
Deux risques a surveiller, que seul un vrai navigateur revele :

  * une phrase d'interface oubliee — elle resterait en francais ;
  * une DONNEE traduite par erreur — un nom de jeu, un chemin, une adresse
    email. C'est le defaut le plus grave : il rendrait la bibliotheque fausse.
"""

import json
import os
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
from cdp import Navigateur

URL = os.environ.get("LUDO_URL", "http://127.0.0.1:8799/")
LOCALES = ICI.parent.parent / "locales"
ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("      OK   %s" % nom)
    else:
        ko += 1
        print("      ECHEC %s   %s" % (nom, detail))


# Accents restants HORS donnees : ce qui n'aurait pas ete traduit.
RESTE_FR = r"""
(function () {
  const IGNORE = new Set(['CODE','PRE','SCRIPT','STYLE','TEXTAREA']);
  const DONNEES = ['gname','compte-mail','pfchemin','tid','jline','hostchip',
                   'cnom','brow','crumb','pfdir','gdesc','sub2','erdit','pfnom'];
  const ACCENTS = /[àâçéèêëîïôûùüÿœÀÂÇÉÈÊËÎÏÔÛÙÜŸŒ]/;
  const out = new Set();
  function ok(n) {
    for (let e = n.parentElement; e; e = e.parentElement) {
      if (IGNORE.has(e.tagName)) return false;
      if (e.classList && DONNEES.some(c => e.classList.contains(c))) return false;
      if (e.classList && e.classList.contains('gcard')) return false;
      if (e.closest && e.closest('#modal')) return false;
    }
    return true;
  }
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const s = (n.nodeValue || '').trim();
    if (s.length < 4 || s.length > 220 || !ok(n)) continue;
    if (ACCENTS.test(s)) out.add(s);
  }
  return [...out];
})()
"""

ETAPES = ["app.tab('jeux')", "app.tab('settings')",
          "app.voirEntretien('doublons')", "app.voirEntretien('integrite')",
          "app.voirEntretien('acces')", "app.auditer(true)",
          "app.toggleJournal()", "app.toggleDrop(true)"]


def main():
    origine = "fr"
    n = Navigateur(port=9401, largeur=1500, hauteur=1300, dpr=1)
    try:
        n.cmd("Emulation.setDeviceMetricsOverride",
              {"width": 1500, "height": 1300, "deviceScaleFactor": 1, "mobile": False})
        n.aller(URL, attente=3)
        for _ in range(40):
            if n.js("document.body.classList.contains('pret')"):
                break
            time.sleep(1.5)

        print("   -- catalogue --")
        en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
        fr = json.loads((LOCALES / "fr.json").read_text(encoding="utf-8"))
        t("en.json fourni", len(en) > 300, len(en))
        t("fr.json couvre le meme catalogue",
          set(en) - {"_meta"} <= set(fr), sorted(set(en) - set(fr))[:3])
        t("aucune valeur vide", all(v for k, v in en.items() if k != "_meta"))

        # La langue est un REGLAGE persistant : on note celle de l'utilisateur
        # pour la remettre a la fin. Un test ne doit rien laisser derriere lui.
        # On repartira du francais : c'est la langue source du projet, et un
        # essai precedent laisse en anglais ferait « restaurer » l'anglais.
        origine = "fr"

        def basculer(code):
            """`setLang` recharge la page : on attend qu'elle soit de nouveau prete."""
            n.js("app.setLang('%s')" % code)
            time.sleep(2)
            for _ in range(40):
                if n.js("document.body.classList.contains('pret')"):
                    return
                time.sleep(1.2)

        print("   -- francais : rien ne bouge --")
        basculer("fr")
        avant = n.js("document.querySelector('#tabs button').textContent")
        t("libelle francais intact", avant == "Jeux", avant)

        print("   -- bascule en anglais --")
        basculer("en")
        t("onglet traduit",
          n.js("document.querySelector('#tabs button').textContent") == "Games")
        t("titre de la page traduit", n.js("document.title") == "My library")

        # gabarit : une phrase construite a l'execution
        n.js("app.tab('settings')")
        time.sleep(1.2)
        d = n.js("(document.getElementById('d-plateforme')||{}).textContent") or ""
        t("phrase a variable traduite", "settings block" in d, d[:60])

        reste = set()
        for code in ETAPES:
            try:
                n.js(code)
            except Exception:
                pass
            time.sleep(0.9)
            reste |= set(n.js(RESTE_FR) or [])
        # Les titres de jeux sont des donnees : ils gardent leurs accents.
        vrais = [x for x in reste if "Pok" not in x and "™" not in x]
        t("plus aucune phrase d'interface en francais", not vrais, vrais[:3])

        print("   -- les donnees restent intactes --")
        n.js("app.tab('jeux')")
        time.sleep(1.2)
        # Cette assertion exigeait que la ludotheque contienne « Pokemon »,
        # « Mario » ou « Animal Crossing » — c'est-a-dire les jeux de l'auteur.
        # Elle ne testait donc rien chez quelqu'un d'autre, et elle est
        # justement le genre de dependance que ce decor fixe supprime.
        #
        # Ce qu'on veut verifier est plus fort et ne suppose aucun titre : un
        # nom de jeu ne doit pas CHANGER quand on bascule de langue.
        noms = n.js("[...document.querySelectorAll('.gname')].map(e=>e.textContent).slice(0,6)")
        t("des noms de jeux sont affiches", bool(noms), noms)
        basculer("fr")
        avant = n.js("[...document.querySelectorAll('.gname')].map(e=>e.textContent).slice(0,6)")
        basculer("en")
        apres = n.js("[...document.querySelectorAll('.gname')].map(e=>e.textContent).slice(0,6)")
        t("les noms de jeux ne sont pas traduits", avant == apres,
          {"fr": (avant or [])[:3], "en": (apres or [])[:3]})
        chemin = n.js("(document.querySelector('.pfchemin')||{}).textContent") or ""
        t("les chemins ne sont pas traduits", "/" in chemin or chemin == "", chemin[:40])

        print("   -- retour au francais --")
        basculer("fr")
        t("retour au francais apres bascule",
          n.js("document.querySelector('#tabs button').textContent") == "Jeux",
          n.js("document.querySelector('#tabs button').textContent"))
    finally:
        try:
            n.js("app.setLang('%s')" % origine)
            time.sleep(1.5)
        except Exception:
            pass
        n.fermer()
    print("   ------------------------------------------------")
    print("   %d controles OK, %d echec(s)" % (ok, ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
