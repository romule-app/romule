"""Walk the interface and count what breaks on the way.

Seventeen defects came out of one session of installing Romule and using it.
Twelve of them were of a kind nothing here could see, because nothing here
opened a screen and pressed a button:

  * the theme and the motion settings did nothing — `JSON.parse('sombre')`
    threw inside the click dispatcher, before the action was reached;
  * choosing a console did nothing — it called a method that the rename to
    English had replaced eight commits earlier;
  * « chercher la console » answered "route inconnue" — the call carried no
    body, so `api()` sent a GET to a POST-only route.

None of them fails server-side. No request 500s, nothing is written to the log,
no test goes red. The button simply stops answering.

`ecrans.py` already walks the screens — for the two sweeps that read the
rendered DOM, looking for French and for inert elements. It swallows a step
that raises, on purpose: a screen unavailable in the current state must not
bring down the sweep of the others. That tolerance is exactly what let a step
that RAISES go unnoticed.

So this walks the same screens and counts instead:

  * every JS exception, including the ones a click swallows;
  * every request that does not come back 2xx or 304;
  * every screen whose opening raises.

It presses the controls too — but only the ones that read. What deletes, sends
or overwrites is named in `DESTRUCTIF` and left alone: a test that empties the
trash to prove the button is wired has proved something nobody wanted.
"""

import json
import os
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
from cdp import Navigateur                                        # noqa: E402
from ecrans import ETAPES                                         # noqa: E402

URL = os.environ.get("LUDO_URL", "")
if not URL:
    print("LUDO_URL n'est pas posee. Lance `python3 lancer_tests.py "
          "--navigateur`.", file=sys.stderr)
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


# Installed BEFORE the page's own scripts: an exception thrown while app.js
# loads is one of the things we are here to catch.
MOUCHARD = r"""
window.__erreurs = [];
window.__requetes = [];
window.addEventListener('error', function (e) {
  window.__erreurs.push(String((e.error && e.error.stack) || e.message || e));
});
window.addEventListener('unhandledrejection', function (e) {
  window.__erreurs.push('promesse : ' + String((e.reason && e.reason.stack) || e.reason));
});
(function () {
  var vrai = window.fetch;
  window.fetch = function () {
    var url = String(arguments[0]);
    return vrai.apply(this, arguments).then(function (r) {
      if (!r.ok && r.status !== 304) {
        window.__requetes.push(url + ' -> ' + r.status);
      }
      return r;
    }).catch(function (e) {
      window.__requetes.push(url + ' -> ' + e.message);
      throw e;
    });
  };
})();
"""

# Controls that only READ, pressed by their selector. Anything that deletes,
# sends, writes to the console or leaves the page is absent on purpose: a test
# that empties the trash to prove the button is wired has proved something
# nobody wanted.
#
# The three appearance groups are here because they are the ones that were
# dead — six buttons, inert, with nothing on screen to say so.
LECTURES = [
    "#s-theme button[data-arg='clair']",
    "#s-theme button[data-arg='sombre']",
    "#s-mvt button[data-arg='reduit']",
    "#s-mvt button[data-arg='complet']",
    "#s-carte .animopt",
    "[data-act='showMaintenance'][data-arg='sante']",
    "[data-act='showMaintenance'][data-arg='doublons']",
    "[data-act='toggleJournal']",
    "[data-act='detect']",
    "[data-act='refreshAll']",
    "[data-act='toggleFavPop']",
    "[data-act='togglePairing']",
]


def main():
    n = Navigateur(port=9412, largeur=1280, hauteur=1000, dpr=1, assistant=True)
    try:
        n.cmd("Page.addScriptToEvaluateOnNewDocument", {"source": MOUCHARD})
        n.aller(URL, attente=5.0)

        # Answer the access question: an unclaimed installation opens on the
        # wizard and will not let it be dismissed, which is right and would
        # make the rest of this sweep meaningless.
        n.js("(async () => { await api('/api/acces-ouvert', {ouvert: true});"
             " await app.checkHealth(true); app.closeOnboard(); })()")
        time.sleep(2.5)

        print("   -- chaque ecran s'ouvre sans lever --")
        casses = []
        for code in ETAPES:
            # No escaping at all: the protocol's own JSON encoder carries the
            # quotes. Escaping them by hand — the steps contain both kinds,
            # `a[href='#sec-console']` inside a double-quoted call — produced a
            # broken expression that reported three screens as raising when it
            # was the test that was malformed. `eval` is not an option either:
            # the page's CSP is `script-src 'self'`.
            r = n.js("(() => { try { " + code.rstrip(";")
                     + "; return ''; } catch (e) { "
                     "return String(e && e.message || e); } })()")
            if r:
                casses.append("%s -> %s" % (code[:44], r))
            time.sleep(0.55)
        t("aucun ecran ne leve a l'ouverture", not casses, " | ".join(casses[:3]))

        print("   -- les controles qui lisent repondent --")
        # Pressed one at a time, through the real dispatcher — that is where
        # `JSON.parse('sombre')` threw, before the action was ever reached.
        #
        # A curated list rather than every `data-act` on screen: clicking them
        # all opens dialogs, changes tab mid-loop and eventually blocks the
        # evaluation. What matters is that each of these goes THROUGH the
        # dispatcher, not that the sweep is exhaustive — the exhaustive half is
        # static, and `verifier-actions.py` does it.
        morts = []
        for selecteur in LECTURES:
            r = n.js("""(() => {
              const el = document.querySelector(%s);
              if (!el || el.disabled) return '';
              const avant = window.__erreurs.length;
              try { el.click(); } catch (e) { return String(e.message || e); }
              return window.__erreurs.length > avant
                ? window.__erreurs[avant] : '';
            })()""" % json.dumps(selecteur))
            if r:
                morts.append("%s : %s" % (selecteur, r))
            time.sleep(0.35)
        t("aucun controle ne leve au clic", not morts, " | ".join(morts[:3]))

        # The theme and the motion settings by name: they are the two that were
        # dead, and a sweep that happened to skip them would say nothing.
        print("   -- le theme et le mouvement changent vraiment --")
        n.js("app.setTheme('clair')")
        time.sleep(0.4)
        t("le theme passe en clair",
          n.js("document.documentElement.dataset.theme") == "clair",
          n.js("document.documentElement.dataset.theme"))
        n.js("app.setMotion('reduit')")
        time.sleep(0.4)
        t("le mouvement passe en reduit",
          n.js("document.documentElement.dataset.mvt") == "reduit",
          n.js("document.documentElement.dataset.mvt"))
        n.js("app.setTheme('sombre'); app.setMotion('complet')")

        # The pairing panel exists ONCE and the wizard borrows it. It used to
        # carry a copy, and the copy fell behind: the settings grew a fourth
        # step — the connection address, which is not the pairing address —
        # while the wizard still stopped at « Associer ». A successful pairing
        # then hid a panel and moved to a step that were not on the screen, so
        # it looked like nothing had happened at all.
        print("   -- l'assistant emprunte le panneau d'appairage --")
        n.js("(() => { const e = onbEtapes(HEALTH);"
             " onbGo(e.findIndex(x => x.cle === 'console')); })()")
        time.sleep(0.8)
        # One question at a time. Both ways of plugging a console in used to be
        # stacked on the same screen — including a search that finds nothing
        # inside a container — with nothing saying which half was yours.
        t("l'etape demande d'abord comment la console est reliee",
          n.js("document.querySelectorAll('#onboard .onbcarte').length") == 2,
          n.js("document.querySelectorAll('#onboard .onbcarte').length"))
        t("et ne montre aucun champ d'appairage avant qu'on ait choisi",
          not n.js("!!document.querySelector('#onb-pair-slot')"))
        n.js("app.onbLien('usb')")
        time.sleep(0.5)
        t("la voie USB ne montre pas le panneau sans fil",
          n.js("!!document.querySelector('#onboard [data-voie=\"usb\"]')")
          and not n.js("!!document.querySelector('#onb-pair-slot #pairwrap')"))
        n.js("app.onbAutreLien()")
        time.sleep(0.4)
        t("on peut revenir au choix",
          n.js("document.querySelectorAll('#onboard .onbcarte').length") == 2)
        n.js("app.onbLien('wifi')")
        time.sleep(0.6)
        t("le panneau est dans l'etape de l'assistant",
          n.js("!!document.querySelector('#onb-pair-slot #pairwrap')"))
        t("l'assistant montre les quatre memes etapes",
          n.js("document.querySelectorAll('#onb-pair-slot #pairwrap .wstep').length") == 4,
          n.js("document.querySelectorAll('#onb-pair-slot #pairwrap .wstep').length"))
        t("le champ de connexion est du voyage",
          n.js("!!document.querySelector('#onb-pair-slot #conn-addr')"))
        # Changing step must not lose it, and must not leave a copy behind:
        # `renderOnboard` rewrites its own innerHTML, which would destroy the
        # settings' panel if it were still inside.
        n.js("(() => { const e = onbEtapes(HEALTH);"
             " onbGo(e.findIndex(x => x.cle === 'console') > 0 ? 0 : 1); })()")
        time.sleep(0.6)
        t("il n'en reste pas une copie dans l'assistant",
          n.js("document.querySelectorAll('#pairwrap').length") == 1,
          n.js("document.querySelectorAll('#pairwrap').length"))
        # Linked, the step must show the CONSOLE, not the form that found it.
        # It kept the address and code fields on screen under a toast claiming
        # success — three screens disagreeing, and the toast was the one lying.
        # Rendered directly rather than by mutating HEALTH: the interface polls,
        # and a refresh landing mid-assertion would overwrite the state under
        # the test — which is a race in the TEST, not a defect in the step.
        lie = n.js("onbConsoleCorps({device: 'wifi',"
                   " device_dir: '/storage/emulated/0/Switch', adb: true})")
        t("une fois reliee, l'etape montre la console",
          "onblie" in (lie or ""), (lie or "")[:90])
        t("et plus aucun champ d'appairage",
          "onb-pair-slot" not in (lie or "") and "conn-addr" not in (lie or ""))
        t("elle nomme le dossier repere sur la console",
          "/storage/emulated/0/Switch" in (lie or ""))
        t("et laisse relier autrement", "onbAutreLien" in (lie or ""))
        t("le panneau est revenu aux reglages, pas detruit",
          n.js("document.querySelectorAll('#pairwrap').length") == 1,
          n.js("document.querySelectorAll('#pairwrap').length"))
        n.js("app.closeOnboard()")
        time.sleep(0.6)
        t("il est rendu aux reglages, et masque",
          n.js("(() => { const p = document.getElementById('pairwrap');"
               " return !!p && !p.closest('#onboard')"
               " && p.style.display === 'none'; })()"))

        print("   -- rien n'a echoue en chemin --")
        erreurs = n.js("window.__erreurs") or []
        t("aucune exception JavaScript", not erreurs, " | ".join(erreurs[:2]))
        requetes = n.js("window.__requetes") or []
        # 401 and 403 are answers, not failures: the sweep presses buttons an
        # unauthenticated or non-administrator viewer is right to be refused.
        vraies = [r for r in requetes
                  if not r.endswith(" -> 401") and not r.endswith(" -> 403")]
        t("aucune requete sans reponse", not vraies, " | ".join(vraies[:3]))
    finally:
        n.fermer()

    print("      ------------------------------------------------")
    print("      %d controles OK, %d echec(s)" % (ok, ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
