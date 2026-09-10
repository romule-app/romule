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
        # The USB card says what the port shows, in one line. Offering « with a
        # cable » while saying nothing about whether a cable would even be seen
        # is asking someone to find out by failing.
        t("la carte USB dit ce que le port montre",
          n.js("!!document.querySelector('#onboard .onbcarte .onbcetat')"))
        for etat, attendu in (("pret", "onbcetat-ok"),
                              ("autorisation", "onbcetat-attn"),
                              ("invisible", "onbcetat-non")):
            vu = n.js("onbConsoleCorps({adb: true, usb: {etat: '%s', nom: 'RP5'}})"
                      % etat)
            t("l'etat USB %s a sa couleur" % etat, attendu in (vu or ""),
              (vu or "")[:80])
        t("une console vue met la carte USB en avant",
          "onbcarte-vise" in (n.js("onbConsoleCorps({adb: true,"
                                   " usb: {etat: 'pret', nom: 'RP5'}})") or ""))
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
        # Five panels, four steps: the fifth is the conclusion, not another
        # thing to do.
        t("l'assistant montre les memes panneaux que les reglages",
          n.js("document.querySelectorAll('#onb-pair-slot #pairwrap .wstep').length") == 5,
          n.js("document.querySelectorAll('#onb-pair-slot #pairwrap .wstep').length"))
        t("le champ de connexion est du voyage",
          n.js("!!document.querySelector('#onb-pair-slot #conn-addr')"))
        # The pairing line is static markup: it used to greet whoever
        # simply walked to step 4, and a green tick alone was read as
        # "everything is done" — which is why the header still showing no
        # console looked like a contradiction.
        t("la ligne d'appairage ne s'affiche pas sans appairage",
          n.js("(() => { const e = document.querySelector('#wstep4 .wok');"
               " return !e || getComputedStyle(e).display === 'none'; })()"))
        n.js("(() => { $('wstep4').dataset.appaire = '1'; })()")
        time.sleep(0.3)
        t("et s'affiche apres un appairage",
          n.js("getComputedStyle(document.querySelector('#wstep4 .wok'))"
               ".display") != "none")
        # The panel exists to CONNECT: once that is done it has nothing left to
        # ask, so the address field and the button give way to what the console
        # answered.
        t("le panneau a un etat 'connectee'",
          n.js("!!document.querySelector('#onb-pair-slot #wstep5 #conn-ok')"))
        n.js("app.wizStep(5)")
        time.sleep(0.4)
        t("l'etat connectee cache le champ d'adresse",
          n.js("getComputedStyle($('wstep4')).display") == "none"
          and n.js("getComputedStyle($('wstep5')).display") != "none")
        n.js("app.wizStep(4)")
        time.sleep(0.3)
        # Typing only the port means the same thing as retyping the whole
        # address: the field is pre-filled and the caret sits after the colon.
        # What is READ off a console's screen and typed back rarely arrives
        # clean. All of these mean the same thing, and refusing any of them
        # teaches nothing.
        for saisi, attendu in (
                ("41111", "192.0.2.4:41111"),            # the port alone
                ("192.0.2.4:41111", "192.0.2.4:41111"),  # the whole address
                (" 192.0.2.4 : 41111 ", "192.0.2.4:41111"),   # spaces around
                ("192.0.2.4:", ""),                      # nothing typed yet
                ("192.0.2.4:42653", "192.0.2.4:42653"),  # a five-digit port
                ("", "")):
            vu = n.js("app.adresseSaisie(%s, '192.0.2.4:37105')"
                      % json.dumps(saisi))
            t("saisie %r -> %r" % (saisi, attendu), vu == attendu, vu)
        # What is typed must survive whatever the interface does next. The
        # wizard rebuilds its own innerHTML on every health read, and the
        # pairing panel is a BORROWED node inside it — so a refresh landing
        # between typing the port and pressing the button is the ordinary case,
        # not an edge one.
        n.js("(() => { app.wizStep(4);"
             " $('conn-addr').value = '192.0.2.4:41111'; })()")
        time.sleep(0.3)
        n.js("(async () => { await app.checkHealth(true); })()")
        time.sleep(1.0)
        t("un rafraichissement n'efface pas le port saisi",
          n.js("(($('conn-addr') || {}).value) || ''") == "192.0.2.4:41111",
          n.js("(($('conn-addr') || {}).value) || ''"))
        # While something is in flight the fields must be out of reach. They
        # stayed live and silent, so pressing twice sent a second `adb connect`
        # into the middle of the first — which adb answers by refusing both.
        n.js("(() => { $('pairgo').disabled = true;"
             " pairOccupe(true, 'test'); })()")
        time.sleep(0.3)
        t("le panneau se voile pendant l'operation",
          n.js("$('pairwrap').classList.contains('occupe')"))
        t("et les champs deviennent inaccessibles",
          n.js("$('conn-addr').disabled") is True)
        n.js("pairOccupe(false)")
        time.sleep(0.3)
        t("le voile levé, les champs reviennent",
          n.js("$('conn-addr').disabled") is False)
        # A control disabled for its OWN reason must stay so: `#pairgo` waits
        # for the fields to validate.
        t("sauf ceux qui etaient deja desactives",
          n.js("$('pairgo').disabled") is True)
        n.js("(() => { $('pairgo').disabled = false; })()")

        t("et ne renvoie pas le panneau a sa premiere etape",
          n.js("(() => { const e ="
               " document.querySelector('#pairwrap .wstep.on');"
               " return e && e.id; })()") == "wstep4",
          n.js("(() => { const e ="
               " document.querySelector('#pairwrap .wstep.on');"
               " return e && e.id; })()"))
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
        t("elle ne mene plus par un chemin Switch",
          "/storage/emulated/0/Switch" not in (lie or ""))
        # ONE generic row: the Switch folder is a per-platform detail, and a
        # wizard step that asked about it was a Switch tool talking.
        # One folder row, and none of it addressed to the Switch: its name may
        # appear in the platform GRID below — that is where it belongs.
        t("l'etape demande la racine generique et rien d'autre",
          (lie or "").count("onbdoss\"") == 1
          and 'data-arg="switch"' not in (lie or ""),
          (lie or "").count("onbdoss\""))
        t("et laisse aller la chercher a la main",
          "onbParcourir" in (lie or ""))
        t("sans bouton de recensement ni de relien",
          "onbScanConsole" not in (lie or "")
          and "onbAutreLien" not in (lie or ""))
        # While the detection runs, the step says so instead of reporting a
        # failure that has not happened.
        occ = n.js("(() => { ONB.chercheDossiers = true;"
                   " const h = onbConsoleCorps({device:'wifi', adb:true,"
                   "   device_dir:'/x', console:{}});"
                   " ONB.chercheDossiers = false; return h; })()")
        t("pendant la recherche, l'etape le dit",
          "onbcherche" in (occ or "") and "onbdossvide" not in (occ or ""),
          (occ or "")[:80])
        # Folder navigation is a MODAL now, wherever it is asked for: three
        # callers used to reposition one panel, and each move was a chance for
        # the click to look dead.
        n.js("app.onbParcourir('roms')")
        time.sleep(0.6)
        t("choisir un dossier ouvre la modale de navigation",
          n.js("$('navmodal').classList.contains('open')"))
        t("et elle dit ce qu'elle choisit",
          "dossier des jeux" in (n.js("$('browsecible').textContent") or "").lower(),
          n.js("$('browsecible').textContent"))
        n.js("app.navFermer()")
        time.sleep(0.5)
        t("elle se ferme sans toucher a l'etape",
          not n.js("$('navmodal').classList.contains('open')")
          and n.js("$('onboard').classList.contains('open')"))
        # Closing must not gut it: its content is static markup, and emptying
        # it on close is why the navigator used to work once and never again.
        n.js("app.onbParcourir('roms')")
        time.sleep(0.6)
        t("elle se rouvre apres une fermeture",
          n.js("$('navmodal').classList.contains('open')")
          and n.js("!!$('browser')"))
        n.js("app.navFermer()")
        time.sleep(0.4)
        # And it sits ABOVE the wizard: z 50 under the onboarding's 60 opened
        # it behind its own caller.
        t("la modale de navigation passe devant l'assistant",
          int(n.js("parseInt(getComputedStyle($('navmodal')).zIndex) || 0")) >
          int(n.js("parseInt(getComputedStyle($('onboard')).zIndex) || 0")))
        # While the folder search runs, the wizard cannot be walked.
        n.js("(() => { ONB.chercheDossiers = true; renderOnboard(); })()")
        time.sleep(0.4)
        t("pendant la recherche, Suivant et Precedent sont bloques",
          n.js("(() => { const b = [...document.querySelectorAll("
               "'#onboard .onbpied button')];"
               " return b.filter(x => x.disabled).length >= 2; })()"))
        n.js("(() => { ONB.chercheDossiers = false; renderOnboard(); })()")
        time.sleep(0.4)
        # The same grid as the settings, from the same function.
        pf = n.js("(() => { PLATFORMS = [{key:'gba', name:'Game Boy Advance',"
                  " folder:'GBA', count:12, bytes:1024}];"
                  " return onbConsoleCorps({device:'wifi', adb:true,"
                  " device_dir:'/x', console:{}}); })()")
        t("les plateformes sont listees avec leur nombre",
          "pfgrille" in (pf or "") and ">12<" in (pf or ""), (pf or "")[:100])
        t("et portent un logo", "pflogo" in (pf or ""))
        n.js("(() => { PLATFORMS = []; })()")
        t("le panneau est revenu aux reglages, pas detruit",
          n.js("document.querySelectorAll('#pairwrap').length") == 1,
          n.js("document.querySelectorAll('#pairwrap').length"))
        n.js("app.closeOnboard()")
        time.sleep(0.6)
        t("il est rendu aux reglages, et masque",
          n.js("(() => { const p = document.getElementById('pairwrap');"
               " return !!p && !p.closest('#onboard')"
               " && p.style.display === 'none'; })()"))

        # The connect dialog: the same pairing panel, third home.
        print("   -- la modale de connexion --")
        n.js("app.closeOnboard()")
        time.sleep(0.6)
        n.js("app.ouvrirConnexion()")
        time.sleep(0.6)
        t("la modale de connexion s'ouvre sur le choix",
          n.js("$('connectmodal').classList.contains('open')")
          and n.js("document.querySelectorAll('#connect-corps .onbcarte').length") == 2)
        n.js("app.connectLien('wifi')")
        time.sleep(0.6)
        t("la voie sans fil emprunte le panneau d'appairage",
          n.js("!!document.querySelector('#connect-pair-slot #pairwrap')"))
        n.js("app.connectFermer()")
        time.sleep(0.6)
        t("fermer rend le panneau aux reglages",
          n.js("(() => { const p = $('pairwrap');"
               " return !!p && !p.closest('#connectmodal'); })()"))
        t("et se rouvre proprement",
          (n.js("(() => { app.ouvrirConnexion();"
                " return $('connectmodal').classList.contains('open'); })()"))
          is True)
        n.js("app.connectFermer()")
        time.sleep(0.4)

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
