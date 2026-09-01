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


# Ce que ce test cherche a change de nature.
#
# `outils/verifier-traduction.py` couvre desormais 100 % du CODE : aucune
# phrase francaise n'y echappe au catalogue, et la CI bloque si l'une
# reapparait. Chercher ici des chaines manquantes ferait donc doublon.
#
# Ce que le statique ne peut PAS voir, en revanche :
#
#   * une phrase assemblee a l'execution — chaque morceau est au catalogue,
#     mais le tout n'y est pas ;
#   * un noeud qui echappe a l'observateur — insere autrement qu'en
#     `childList`, ou porteur d'un attribut pose apres coup ;
#   * une valeur interpolee restee en francais dans un modele traduit, comme
#     « — used only with “URL personnalisée” » ;
#   * une DONNEE traduite par erreur, ce qui est le defaut symetrique.
#
# C'est cela qu'on regarde : ce qui est reellement A L'ECRAN.
#
# Deux corrections par rapport a la version precedente. Elle s'aveuglait sur
# `.gcard`, `#modal`, `.erdit`, `.sub2` et `.gdesc` — c'est-a-dire sur la fiche
# de jeu et sur la prose d'EmuReady et du SSO, les deux ecrans les plus denses.
# Et elle ne reconnaissait le francais qu'a ses ACCENTS, laissant passer
# « Convertir les », « Rien dans », « Aucun jeu trouve ».
RESTE_FR = r"""
(function () {
  const IGNORE = new Set(['CODE','PRE','SCRIPT','STYLE','TEXTAREA']);
  // Uniquement ce qui est ENTIEREMENT une donnee. `jline`, `brow` et `crumb`
  // n'y sont plus : elles enveloppent un melange, et leurs parties de donnee
  // portent maintenant `data-i18n-skip`. `erdit`, `sub2` et `gdesc` non plus :
  // c'est de la prose, et les exclure revenait a ne pas la tester.
  const DONNEES = ['gname','compte-mail','pfchemin','tid','hostchip','cnom',
                   'pfdir','pfnom'];
  const ACCENTS = /[àâçéèêëîïôûùüÿœÀÂÇÉÈÊËÎÏÔÛÙÜŸŒ]/;
  // Le francais ne se trahit pas que par ses accents. Deux mots-outils
  // suffisent, comme dans l'extracteur statique.
  const OUTILS = new Set(('le la les un une des du de au aux et ou en dans sur '
    + 'sous pour par avec sans vers est sont ce cette ces son sa ses ton ta '
    + 'aucun aucune rien tout toute tous chaque plus deja encore jamais que '
    + 'qui dont si mais donc car ne pas').split(' '));
  const out = new Set();
  function ok(n) {
    for (let e = n.parentElement; e; e = e.parentElement) {
      if (IGNORE.has(e.tagName)) return false;
      if (e.dataset && e.dataset.i18nSkip !== undefined) return false;
      // Le rapport d'audit est redige par le SERVEUR et renvoye tel quel.
      // L'i18n de Romule est entierement cote navigateur : ces phrases-la ne
      // passent par aucun catalogue, et les traduire demande de traduire
      // `romule/audit.py`, ce qui est un chantier a part et assume comme tel
      // (voir docs/beta.md). On l'ecarte ici EN LE DISANT, plutot que de
      // laisser le test rouge sur une limite connue.
      if (e.id === 'auditres') return false;
      if (e.classList && DONNEES.some(c => e.classList.contains(c))) return false;
    }
    return true;
  }
  function francais(s) {
    if (ACCENTS.test(s)) return true;
    const mots = (s.toLowerCase().match(/[a-zà-ÿ']{2,}/g) || []);
    return mots.filter(m => OUTILS.has(m)).length >= 2;
  }
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const s = (n.nodeValue || '').trim();
    if (s.length < 4 || s.length > 220 || !ok(n)) continue;
    if (francais(s)) out.add(s);
  }
  // Les attributs aussi : l'observateur n'ecoute que `childList`, donc un
  // `title` pose apres l'insertion lui echappe entierement.
  document.querySelectorAll('[title],[placeholder],[aria-label]').forEach(e => {
    if (e.closest('[data-i18n-skip]')) return;
    for (const a of ['title', 'placeholder', 'aria-label']) {
      const v = (e.getAttribute(a) || '').trim();
      if (v.length >= 4 && v.length <= 220 && francais(v)) out.add(a + '= ' + v);
    }
  });
  return [...out];
})()
"""

# Le balayage ne voit que ce qui est affiche : il faut donc ouvrir les ecrans.
# Huit y figuraient, sur la quinzaine que compte l'interface — l'assistant, les
# comptes, la fiche de jeu et EmuReady n'etaient jamais rendus, et c'est
# precisement la que se trouvait l'essentiel du francais residuel.
ETAPES = ["app.tab('jeux')", "app.tab('settings')",
          "app.voirEntretien('doublons')", "app.voirEntretien('integrite')",
          "app.voirEntretien('acces')", "app.auditer(true)",
          "app.toggleJournal()", "app.toggleDrop(true)",
          # Les sections de reglages sont exclusives : chacune doit etre ouverte.
          "document.querySelector(\"#setnav a[href='#sec-console']\").click()",
          "document.querySelector(\"#setnav a[href='#sec-biblio']\").click()",
          "document.querySelector(\"#setnav a[href='#sec-entretien']\").click()",
          "document.querySelector(\"#setnav a[href='#sec-acces']\").click()",
          "document.querySelector(\"#setnav a[href='#sec-interface']\").click()",
          # Le navigateur de dossiers du serveur, jamais visite jusqu'ici.
          "app.tab('settings'); app.ludoOuvrir()",
          # La fiche d'un jeu : l'ecran le plus dense, et le plus exclu.
          "app.tab('jeux'); (function(){const c=document.querySelector('#lib .gcard');"
          "if (c) app.openGame(c.dataset.key);})()",
          "app.closeGame(); app.openOnboard && app.openOnboard()",
          "app.closeOnboard && app.closeOnboard()"]


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
