"""Aucun element cliquable n'est inerte.

C'est le filet de la phase 4. On remplace 153 gestionnaires `on*=` en ligne
par de la delegation ; le risque propre a cette operation est qu'un bouton
cesse de repondre. Ce defaut-la est INVISIBLE cote serveur : aucune requete
n'echoue, aucune trace n'est ecrite, rien ne casse — le bouton ne fait
simplement plus rien. C'est deja arrive dans ce projet.

Le test doit donc exister AVANT la premiere conversion, et rester vert a
chaque etape intermediaire, alors meme que les deux mecanismes coexistent.

Comment on sait qu'un element repond
-------------------------------------
Un gestionnaire en ligne se lit dans le DOM. Un ecouteur pose par
`addEventListener` ne s'y lit pas : il n'existe nulle part dans l'arbre. On
enveloppe donc `addEventListener` AVANT le chargement de la page et on note
sur quels elements il est appele. Un element est couvert s'il porte un
gestionnaire en ligne, s'il a recu un ecouteur en propre, ou s'il porte un
`data-act` sous un ancetre qui en a recu un — la forme deleguee.

Le troisieme cas est le seul qui puisse mentir : une delegation posee sur
`document` rendrait TOUT « couvert ». C'est pourquoi il exige `data-act`, et
c'est pourquoi les deux controles suivants existent.

Les deux controles qui empechent le filet de mentir
---------------------------------------------------
Un `data-act` mal orthographie produit exactement le symptome qu'on cherche a
eviter : l'element parait couvert, et ne fait rien. On verifie donc que chaque
`data-act` present a l'ecran figure dans la liste blanche `app.ACTES`, et que
chaque nom de cette liste designe une fonction qui existe reellement.

La liste blanche n'est pas une precaution de style. Sans elle, la delegation
serait `app[el.dataset.act]()` — un appel dynamique par nom, ou un attribut
suffirait a atteindre n'importe quelle methode, y compris celles qui
suppriment. C'est la meme famille de faille que l'XSS corrigee en 0.1.0.
"""

import os
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
from cdp import Navigateur
from ecrans import parcourir

URL = os.environ.get("LUDO_URL", "http://127.0.0.1:8799/")
ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("      OK   %s" % nom)
    else:
        ko += 1
        print("      ECHEC %s   %s" % (nom, detail))


# Pose avant tout script de la page : `addEventListener` doit etre enveloppe
# avant qu'app.js n'ait eu l'occasion de l'appeler.
MOUCHARD = r"""
(function () {
  const vrai = EventTarget.prototype.addEventListener;
  const marques = new WeakSet();
  const GESTES = new Set(['click', 'change', 'input', 'keydown', 'submit',
                          'pointerdown', 'mousedown', 'touchstart']);
  EventTarget.prototype.addEventListener = function (type, fn, opt) {
    if (GESTES.has(type)) { try { marques.add(this); } catch (e) {} }
    return vrai.call(this, type, fn, opt);
  };
  window.__ecoute = el => marques.has(el);
})()
"""

# Ce qui compte comme cliquable. Les balises d'abord, puis les elements que le
# STYLE annonce comme cliquables : `cursor: pointer` est une promesse faite a
# l'utilisateur, et c'est precisement sur ces div-boutons que l'inertie passe
# inapercue.
#
# Un element repond de CINQ facons, et les cinq sont necessaires — la premiere
# version de ce test n'en connaissait qu'une et rapportait 54 faux positifs :
#
#   1. un attribut `on*=` : c'est ce que la phase 4 retire ;
#   2. une PROPRIETE `el.onclick = fn`, posee en JavaScript. Elle n'apparait
#      dans aucun attribut et `querySelectorAll('[onclick]')` ne la voit pas ;
#   3. un ecouteur recu en propre, note par le mouchard ;
#   4. la forme deleguee : une cle `data-*` connue, sous un ancetre qui ecoute ;
#   5. son propre fonctionnement natif : un `select`, une case a cocher, ou le
#      `<label>` qui les enveloppe. Le geste a un effet visible et la valeur
#      est relue a l'enregistrement — l'element n'est pas inerte, il n'a
#      simplement pas besoin de code.
#
# Le point 4 est le seul qui pourrait mentir : `document` porte un ecouteur de
# clic (`cacherApercu`), donc « un ancetre ecoute » est vrai pour TOUT
# l'arbre. C'est pourquoi la cle est exigee, et pourquoi elle est prise dans
# une liste FERMEE. Les cles autres que `data-act` sont les delegations qui
# existaient avant la phase 4 ; cette liste doit retrecir, jamais grandir.
INERTES = r"""
(function () {
  const CLIQUABLE = 'button, [role=button], [onclick], [data-act], '
                  + '[data-act-change], [data-act-input], '
                  + 'a[href^="#"], a:not([href])';
  const CLES = ['act', 'actChange', 'actInput', 'tab', 'f', 'jl', 'path',
                'lpath', 'di', 'i', 'a', 'grp'];
  const GESTES = ['onclick', 'onchange', 'oninput', 'onkeydown', 'onsubmit'];
  const out = [];
  const vus = new Set();
  const tous = new Set(document.querySelectorAll(CLIQUABLE));
  // Les faux boutons : styles comme cliquables sans en etre.
  document.querySelectorAll('div, span, li, i, img').forEach(e => {
    if (getComputedStyle(e).cursor === 'pointer') tous.add(e);
  });
  // `document` n'est pas un Element : la chaine des `parentElement` s'arrete a
  // <html> et ne l'atteint jamais. Or c'est la que porte la delegation
  // generale — sans ce cas, tout element delegue serait declare inerte.
  const ecouteAuDessus = el => {
    for (let p = el.parentElement; p; p = p.parentElement)
      if (window.__ecoute(p)) return true;
    return window.__ecoute(document);
  };
  for (const el of tous) {
    // Un element cache n'est pas atteignable : le juger serait un faux positif.
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    // Desactive : ne rien faire EST son comportement attendu.
    if (el.disabled) continue;
    // Interieur d'un element deja cliquable : il herite du geste.
    if (el.parentElement && el.parentElement.closest(
          'button, a, label, [onclick], [data-act], [role=button]')) continue;
    // 5. natif
    if (el.closest('label')) continue;

    // 1. attribut
    if ([...el.attributes].some(a => /^on[a-z]+$/.test(a.name))) continue;
    // 2. propriete posee en JavaScript
    if (GESTES.some(g => typeof el[g] === 'function')) continue;
    // 3. ecouteur en propre
    if (window.__ecoute(el)) continue;
    // 4. delegation : une cle connue sous un ancetre qui ecoute
    if (CLES.some(k => el.dataset[k] !== undefined) && ecouteAuDessus(el)) continue;

    // Identite lisible : c'est ce que l'humain lira dans le rapport d'echec.
    const id = el.id ? '#' + el.id
             : (el.className && typeof el.className === 'string'
                ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.')
                : el.tagName.toLowerCase());
    const cle = id + '|' + (el.textContent || '').trim().slice(0, 30);
    if (vus.has(cle)) continue;
    vus.add(cle);
    out.push(cle);
  }
  return out;
})()
"""

# Le compteur d'avancement, et les deux controles sur la liste blanche.
RELEVE = r"""
(function () {
  const enLigne = document.querySelectorAll(
    '[onclick],[onchange],[oninput],[onkeydown],[onsubmit],[onload],[onerror]');
  const actes = new Set();
  for (const [sel, cle] of [['data-act', 'act'],
                            ['data-act-change', 'actChange'],
                            ['data-act-input', 'actInput']])
    document.querySelectorAll('[' + sel + ']')
            .forEach(e => actes.add(e.dataset[cle]));
  return {enLigne: enLigne.length, actes: [...actes]};
})()
"""


def main():
    n = Navigateur(port=9403, largeur=1500, hauteur=1300, dpr=1)
    try:
        n.cmd("Page.addScriptToEvaluateOnNewDocument", {"source": MOUCHARD})
        n.cmd("Emulation.setDeviceMetricsOverride",
              {"width": 1500, "height": 1300, "deviceScaleFactor": 1,
               "mobile": False})
        n.aller(URL, attente=3)
        for _ in range(40):
            if n.js("document.body.classList.contains('pret')"):
                break
            time.sleep(1.5)

        t("le mouchard est en place", n.js("typeof window.__ecoute") == "function")

        print("   -- le detecteur voit-il ce qu'il pretend voir ? --")
        # Un filet qu'on n'a jamais vu attraper quoi que ce soit ne prouve
        # rien. On lui presente donc les cinq formes de couverture plus la
        # forme nue, dans un coin de page reel, et on verifie qu'il ne rapporte
        # QUE celle qui est reellement inerte.
        n.js("""
          (function () {
            const b = document.createElement('div');
            b.id = 'zone-essai';
            b.innerHTML =
              '<button id="e-nu">nu</button>'
            + '<button id="e-attr" onclick="void 0">attribut</button>'
            + '<button id="e-prop">propriete</button>'
            + '<button id="e-propre">propre</button>'
            + '<div id="e-parent"><button id="e-delegue" data-act="x">delegue</button>'
            + '<button id="e-sanscle">sans cle</button></div>';
            document.body.appendChild(b);
            document.getElementById('e-prop').onclick = () => {};
            document.getElementById('e-propre')
                    .addEventListener('click', () => {});
            document.getElementById('e-parent')
                    .addEventListener('click', () => {});
          })()""")
        vu = set(n.js(INERTES) or [])
        def presente(x):
            return any(c.startswith('#' + x + '|') for c in vu)
        t("un bouton sans rien -> rapporte", presente('e-nu'))
        t("un attribut on* -> ignore", not presente('e-attr'))
        t("une propriete el.onclick -> ignore", not presente('e-prop'))
        t("un ecouteur en propre -> ignore", not presente('e-propre'))
        t("une delegation sur l'ancetre -> ignore", not presente('e-delegue'))
        # `e-sanscle` n'a pas de cle `data-*` : l'ancetre a beau ecouter, rien
        # ne dit qu'il le concerne. C'est exactement la fausse assurance que la
        # liste fermee de cles est la pour empecher.
        t("sous un ancetre qui ecoute mais sans cle -> rapporte",
          presente('e-sanscle'), sorted(vu)[:4])
        n.js("document.getElementById('zone-essai').remove()")

        print("   -- balayage des ecrans --")
        inertes = sorted(parcourir(n, INERTES))
        t("aucun element cliquable inerte", not inertes,
          "%d : %s" % (len(inertes), inertes[:4]))

        print("   -- le fond de fenetre ferme, l'interieur non --")
        # Quatre panneaux portaient `onclick="event.stopPropagation()"` pour
        # empecher le clic d'atteindre le fond. La delegation ecoute sur
        # `document` : arreter la propagation la n'aurait plus aucun effet.
        # On l'a donc retire — en verifiant que le comportement tient, parce
        # qu'il tient pour une AUTRE raison : `closeGame` et `closeDialog`
        # comparent `e.target` a l'element precis du fond. Le test le prouve,
        # au lieu de faire confiance a la lecture.
        n.js("app.tab('jeux'); (function(){const c=document.querySelector("
             "'#lib .gcard'); if (c) app.openGame(c.dataset.key);})()")
        time.sleep(1.2)
        ouvert = n.js("document.getElementById('modal').classList.contains('open')")
        t("la fiche s'ouvre", ouvert)
        n.js("document.querySelector('#modal [data-interieur]').click()")
        time.sleep(0.5)
        t("un clic DANS la fiche ne la ferme pas",
          n.js("document.getElementById('modal').classList.contains('open')"))
        n.js("document.getElementById('modal').click()")
        time.sleep(0.5)
        t("un clic sur le FOND la ferme",
          not n.js("document.getElementById('modal').classList.contains('open')"))

        print("   -- liste blanche des actions --")
        # `app.ACTES` n'existe pas encore au debut de la phase 4 : tant qu'il
        # n'y a aucun `data-act`, il n'y a rien a verifier, et exiger la liste
        # ferait echouer le filet avant meme la premiere conversion.
        vus = set()
        restants = 0
        for code in __import__("ecrans").ETAPES:
            try:
                n.js(code)
            except Exception:
                pass
            time.sleep(0.6)
            r = n.js(RELEVE) or {}
            vus |= set(r.get("actes") or [])
            restants = max(restants, r.get("enLigne", 0))

        # Une action speciale est une entree de table, pas une methode : elle
        # est autorisee au meme titre, et c'est la table qui la definit.
        blanche = set(n.js("Array.from(app.ACTES || [])") or []) \
            | set(n.js("Object.keys(app.ACTES_SPECIAUX || {})") or [])
        if vus or blanche:
            t("chaque data-act figure dans la liste blanche",
              vus <= blanche, sorted(vus - blanche)[:5])
            manquants = n.js(
                "Array.from(app.ACTES || []).filter(k => typeof app[k] "
                "!== 'function' && !(app.ACTES_SPECIAUX || {})[k])") or []
            t("chaque action de la liste designe une fonction",
              not manquants, manquants[:5])
        print("      .... %d gestionnaires en ligne, %d actions deleguees"
              % (restants, len(vus)))
    finally:
        n.fermer()
    print("   %d ok, %d echecs" % (ok, ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
