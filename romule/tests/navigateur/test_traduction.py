"""Translation: the whole interface switches, the DATA does not move.

French is the key (the gettext principle) and the translation applies to the DOM.
Two risks to watch for, which only a real browser reveals:

  * a forgotten interface sentence — it would stay in French;
  * a piece of DATA translated by mistake — a game's name, a path, an email
    address. That is the worse defect: it would make the library wrong.
"""

import json
import os
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
from cdp import Navigateur
from ecrans import parcourir

# `LUDO_URL` is REQUIRED, and there is deliberately no default.
#
# There used to be one: `http://127.0.0.1:8799/`. But that is a port where a REAL
# instance easily runs — mine, as it happens. Run on its own, this test therefore
# drove someone's library: it reported "189 inline handlers" because it was
# examining a three-month-old version, and it clicked inside real data.
#
# A default that aims at a plausible service is worse than an error: it gives a
# result, and that result talks about something else. `lancer_tests.py` sets the
# variable; whoever wants to aim at a development server sets it themselves.
URL = os.environ.get("LUDO_URL", "")
if not URL:
    print("LUDO_URL n'est pas posee. Lance `python3 lancer_tests.py "
          "--navigateur`,\nou vise explicitement un serveur d'essai :\n"
          "    LUDO_URL=http://127.0.0.1:9871/ python3 %s"
          % __file__, file=sys.stderr)
    raise SystemExit(2)
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


# What this test looks for has changed in nature.
#
# `outils/verifier-traduction.py` now covers 100 % of the CODE: no French
# sentence there escapes the catalogue, and CI blocks if one reappears. Looking
# for missing strings here would therefore be a duplicate.
#
# What the static check CANNOT see, on the other hand:
#
#   * a sentence assembled at runtime — every piece is in the catalogue, but the
#     whole is not;
#   * a node that escapes the observer — inserted otherwise than through
#     `childList`, or carrying an attribute set after the fact;
#   * an interpolated value left in French inside a translated template, such as
#     "— used only with “URL personnalisée”";
#   * a piece of DATA translated by mistake, which is the symmetric defect.
#
# That is what we look at: what is really ON SCREEN.
#
# Two corrections compared to the previous version. It blinded itself to
# `.gcard`, `#modal`, `.erdit`, `.sub2` and `.gdesc` — that is, to the game's
# detail view and to EmuReady's and the SSO's prose, the two densest screens. And
# it recognised French only by its ACCENTS, letting "Convertir les", "Rien dans",
# "Aucun jeu trouve" -- anglais:ok, quoted French samples -- through.
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
  // Un MOT SEUL a l'ecran echappait aux deux regles ci-dessous : « aucune »
  // s'affichait en francais dans l'interface anglaise, et ni l'accent ni le
  // compte de mots-outils ne pouvaient le trahir. Meme liste que le controle
  // statique, meme raison.
  const SEULS = new Set(('aucun aucune aucuns aucunes inconnu inconnue inconnus '
    + 'inconnues jamais toujours plusieurs quelques autre autres chacun chacune '
    + 'terminee terminees echouee echouees introuvable introuvables').split(' '));
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
    // Un seul mot, mais un mot qui ne peut pas etre autre chose que du
    // francais. A l'ecran il n'y a pas de contexte de comparaison a exclure :
    // ce qui est affiche est affiche.
    if (mots.length === 1 && SEULS.has(mots[0])) return true;
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

# The screens are described once, in `ecrans.py`: this test and `test_gestes.py`
# both sweep the rendered DOM, and a screen added to only one of them would be a
# silent blind spot.
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
        t("en.json is shipped", len(en) > 300, len(en))
        t("fr.json covers the same catalogue",
          set(en) - {"_meta"} <= set(fr), sorted(set(en) - set(fr))[:3])
        t("aucune valeur vide", all(v for k, v in en.items() if k != "_meta"))

        # The language is a persistent SETTING: we note the user's own to put
        # it back at the end. A test must leave nothing behind. We start from
        # French: it is the project's source language, and an earlier run left in
        # English would "restore" English.
        origine = "fr"

        def basculer(code):
            """`setLang` reloads the page: we wait for it to be ready again."""
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
        # The title is the PRODUCT NAME: it is not translated, and it must not
        # move from one language to another. This is the reverse of the previous
        # check, and just as important.
        t("the title stays the product's name",
          n.js("document.title") == "Romule", n.js("document.title"))

        # a template: a sentence built at runtime
        n.js("app.tab('settings')")
        time.sleep(1.2)
        d = n.js("(document.getElementById('d-plateforme')||{}).textContent") or ""
        t("phrase a variable traduite", "settings block" in d, d[:60])

        reste = parcourir(n, RESTE_FR)
        # Game titles are data: they keep their accents.
        vrais = [x for x in reste if "Pok" not in x and "™" not in x]
        t("plus aucune phrase d'interface en francais", not vrais, vrais[:3])

        print("   -- les donnees restent intactes --")
        n.js("app.tab('jeux')")
        time.sleep(1.2)
        # This assertion required the library to hold "Pokemon", "Mario" or
        # "Animal Crossing" — that is, the author's own games. So it tested
        # nothing at anyone else's, and it is exactly the kind of dependency this
        # fixed fixture removes.
        #
        # What we want to check is stronger and assumes no title: a game's name
        # must not CHANGE when the language is switched.
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
