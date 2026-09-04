"""No clickable element is inert.

This is phase 4's safety net. We replace 153 inline `on*=` handlers with
delegation; the risk specific to that operation is that a button stops
answering. That defect is INVISIBLE server-side: no request fails, no trace is
written, nothing breaks — the button simply does nothing any more. It has
already happened in this project.

So the test must exist BEFORE the first conversion, and stay green at every
intermediate step, even while the two mechanisms coexist.

How we know an element answers
------------------------------
An inline handler can be read from the DOM. A listener set by
`addEventListener` cannot: it exists nowhere in the tree. So we wrap
`addEventListener` BEFORE the page loads and note which elements it is called
on. An element is covered if it carries an inline handler, if it received a
listener of its own, or if it carries a `data-act` under an ancestor that
received one — the delegated form.

The third case is the only one that can lie: a delegation set on `document`
would make EVERYTHING "covered". That is why it requires `data-act`, and why the
two checks that follow exist.

The two checks that stop the net from lying
-------------------------------------------
A misspelled `data-act` produces exactly the symptom we are trying to avoid: the
element looks covered, and does nothing. So we check that every `data-act`
present on screen appears in the `app.ACTES` allow-list, and that every name in
that list points at a function that really exists.

The allow-list is not a stylistic precaution. Without it, the delegation would be
`app[el.dataset.act]()` — a dynamic call by name, where one attribute would be
enough to reach any method, including the ones that delete. It is the same family
of hole as the XSS fixed in 0.1.0.
"""

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
ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("      OK   %s" % nom)
    else:
        ko += 1
        print("      ECHEC %s   %s" % (nom, detail))


# Set before any of the page's scripts: `addEventListener` must be wrapped
# before app.js has had a chance to call it.
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
  // La politique de contenu refuse desormais tout script en ligne. Une
  // violation ne fait pas echouer la page : le navigateur ecrit une ligne en
  // console et continue, donc le defaut est SILENCIEUX pour tout le monde
  // sauf pour celui qui a la console ouverte. On les collecte.
  window.__csp = [];
  document.addEventListener('securitypolicyviolation', e => {
    window.__csp.push(e.violatedDirective + ' : '
                      + (e.blockedURI || '') + ' ' + (e.sourceFile || ''));
  });
})()
"""

# What counts as clickable. The tags first, then the elements the STYLE
# announces as clickable: `cursor: pointer` is a promise made to the user, and it
# is precisely on those div-buttons that inertia goes unnoticed.
#
# An element answers in FIVE ways, and all five are needed — this test's first
# version knew only one and reported 54 false positives:
#
#   1. an `on*=` attribute: that is what phase 4 removes;
#   2. a PROPERTY `el.onclick = fn`, set in JavaScript. It appears in no
#      attribute and `querySelectorAll('[onclick]')` does not see it;
#   3. a listener received in its own right, noted by the probe;
#   4. the delegated form: a known `data-*` key, under a listening ancestor;
#   5. its own native behaviour: a `select`, a checkbox, or the `<label>` that
#      wraps them. The gesture has a visible effect and the value is read back on
#      saving — the element is not inert, it simply needs no code.
#
# Point 4 is the only one that could lie: `document` carries a click listener
# (`hidePreview`), so "an ancestor listens" is true for the WHOLE tree. That is
# why the key is required, and why it is drawn from a CLOSED list. The keys other
# than `data-act` are the delegations that existed before phase 4; this list must
# shrink, never grow.
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

# The progress counter, and the two checks on the allow-list.
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

        t("the probe is in place", n.js("typeof window.__ecoute") == "function")

        print("   -- does the detector see what it claims to see? --")
        # A net nobody has ever seen catch anything proves nothing. So we show it
        # the five forms of coverage plus the bare form, in a real corner of the
        # page, and check it reports ONLY the one that is really inert.
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
        t("a delegation on the ancestor -> ignored", not presente('e-delegue'))
        # `e-sanscle` has no `data-*` key: the ancestor may well listen, but
        # nothing says it concerns this element. That is exactly the false
        # assurance the closed list of keys exists to prevent.
        t("under a listening ancestor but with no key -> reported",
          presente('e-sanscle'), sorted(vu)[:4])
        n.js("document.getElementById('zone-essai').remove()")

        print("   -- balayage des ecrans --")
        inertes = sorted(parcourir(n, INERTES))
        t("aucun element cliquable inerte", not inertes,
          "%d : %s" % (len(inertes), inertes[:4]))

        print("   -- the dialog backdrop closes, its inside does not --")
        # Four panels carried `onclick="event.stopPropagation()"` to stop the
        # click reaching the backdrop. The delegation listens on `document`:
        # stopping propagation there would have no effect any more. So it was
        # removed — while checking the behaviour holds, because it holds for
        # ANOTHER reason: `closeGame` and `closeDialog` compare `e.target` to the
        # backdrop's precise element. The test proves it, instead of trusting a
        # reading.
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

        print("   -- the content policy blocks nothing --")
        # This check comes AFTER the sweep: it must have seen every screen being
        # built, since it is at render time that an inline script would be
        # refused.
        viol = n.js("window.__csp || []") or []
        t("no content-policy violation", not viol, viol[:3])
        # Green means nothing until red has been seen. So we provoke a violation:
        # an inline script added to the page. If it runs, the header is not
        # arriving — and the check above proved nothing.
        n.js("""
          (function () {
            window.__temoin = 'pas execute';
            const sc = document.createElement('script');
            sc.textContent = "window.__temoin = 'execute';";
            document.body.appendChild(sc);
            sc.remove();
          })()""")
        time.sleep(0.4)
        t("un script en ligne est REFUSE",
          n.js("window.__temoin") == "pas execute", n.js("window.__temoin"))
        t("et la violation est rapportee",
          len(n.js("window.__csp || []") or []) > len(viol),
          n.js("window.__csp || []"))

        print("   -- the actions' allow-list --")
        # `app.ACTES` does not exist yet at the start of phase 4: as long as
        # there is no `data-act`, there is nothing to check, and requiring the
        # list would fail the net before the first conversion.
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

        # A special action is a table entry, not a method: it is allowed on the
        # same footing, and the table is what defines it.
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
