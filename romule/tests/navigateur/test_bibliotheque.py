"""The library: the right view, kept, aligned, and filterable.

What this file holds, and that reading the code does not show:

  * the library **opens on all platforms**, and the user's previous choice wins
    — it WAS written to local storage on every change, but never read back, so
    lost on every opening;
  * the bar's three rows **share an axis and a height**, and the gutters between
    them are equal. Nobody can say why a bar "looks untidy"; we measure it;
  * the unified list is **kept** as long as nothing moves, and **rebuilt** as
    soon as something moves — both halves matter;
  * **returning to an already-seen platform asks the server for nothing**;
  * the filters are counted, cleared in one gesture, and saved.

One promise was REMOVED from here, and it is worth saying why: "the grid never
empties during a switch". Three versions of the check were tried — `#lib`'s
height frame by frame, the number of cards, then both with 400 ms of emulated
latency and a 900 ms forced delay on the answer. All three stayed GREEN on the
broken code, the one that emptied the lists before waiting for the network. A
check nobody has ever seen fail proves nothing.

So the property is held where it can be checked without ambiguity: a source
invariant in `test_ui_injection.js` forbids assigning an empty list before
`setSystem`'s first `await`.
"""
import os
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
from cdp import Navigateur

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
    print("LUDO_URL is not set. Run `python3 lancer_tests.py "
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
        print("      FAIL  %s   %s" % (nom, detail))


# Counts the network calls. Set before the page loads: the only way to see the
# very first call.
MOUCHARD = r"""
(function () {
  window.__appels = [];
  const vrai = window.fetch;
  window.fetch = function (u, o) {
    window.__appels.push(String(u && u.url ? u.url : u));
    return vrai.apply(this, arguments);
  };
})()
"""

GEOMETRIE = r"""
(function () {
  const box = s => {
    const el = document.querySelector(s);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {h: Math.round(r.top), b: Math.round(r.bottom)};
  };
  const ctrl = ['.toolbar .tlbl', '#sens', '#favbtn', '#parpage', '#tailles']
    .map(box).filter(Boolean);
  return {ctrl: ctrl, libbar: box('.libbar'),
          filtres: box('#filters'), barre: box('#toolbar')};
})()
"""


def attendre_pret(n, tours=40):
    for _ in range(tours):
        if n.js("document.body.classList.contains('pret')"):
            return True
        time.sleep(1.5)
    return False


def cartes(n):
    return n.js("document.querySelectorAll('#lib .gcard').length") or 0


def vue_par_defaut(n):
    print("   -- the default view --")
    # The previous choice wins: we start from a clean slate to test the
    # DEFAULT and not a leftover from an earlier run.
    n.js("localStorage.removeItem('systeme')")
    n.cmd("Page.reload", {})
    time.sleep(3)
    attendre_pret(n)
    time.sleep(2)
    t("the library opens on all platforms",
      n.js("SYS") == "all", n.js("SYS"))


def pluriels(n):
    print("   -- agreement follows the language --")
    # "1 fichier(s)" is not a plural, it is a confession. And the rules are not
    # the same: in French 0 and 1 are singular, in English only 1 is. We check
    # BOTH languages, otherwise one mistake replaces another unnoticed.
    cas = n.js("""
      (async () => {
        const rendu = [];
        for (const langue of ['fr', 'en']) {
          await loadLanguage(langue);
          rendu.push([langue,
                      countPhrase(0, '{fichier|fichiers}'),
                      countPhrase(1, '{fichier|fichiers}'),
                      countPhrase(2, '{fichier|fichiers}'),
                      tpl('%d {jeu|jeux} au total', 1),
                      tpl('%d {jeu|jeux} au total', 5)]);
        }
        await loadLanguage('fr');
        return rendu;
      })()""") or []
    attendu = {
        "fr": ["0 fichier", "1 fichier", "2 fichiers",
               "1 jeu au total", "5 jeux au total"],
        "en": ["0 files", "1 file", "2 files",
               "1 game in total", "5 games in total"],
    }
    for ligne in cas:
        langue, *vus = ligne
        t("agreement in %s" % langue, vus == attendu.get(langue), vus)
    t("both languages were exercised", len(cas) == 2, len(cas))

    # And nothing on screen may carry the lazy form any more.
    restes = n.js(r"""
      (function () {
        const out = [];
        const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let x = w.nextNode(); x; x = w.nextNode()) {
          const s = (x.nodeValue || '').trim();
          if (/[A-Za-zÀ-ÿ]\([sx]\)/.test(s)) out.push(s.slice(0, 60));
        }
        return out;
      })()""") or []
    t("no \"(s)\" on screen", not restes, restes[:3])


def mobile(n):
    print("   -- on a phone, the content comes before the settings --")
    # Measured before: 19 controls between the top of the screen and the first
    # cover. You scrolled through a configuration panel to reach what you had
    # come to see.
    n.cmd("Emulation.setDeviceMetricsOverride",
          {"width": 430, "height": 932, "deviceScaleFactor": 2, "mobile": True})
    time.sleep(1.5)
    # Without this check, everything that follows would be measured on a wide
    # screen and would pass for true: a test that believes it is on a phone and
    # is not proves nothing.
    t("the viewport really is a phone's",
      n.js("window.matchMedia('(max-width:700px)').matches"),
      n.js("window.innerWidth"))
    # What is counted: the controls OF THE LIBRARY'S BARS — the panel you
    # scroll through to reach the grid. Not the application's header (tabs,
    # console state): it is present on every screen and is not part of what
    # stands in the way.
    avant = n.js("""
      (function () {
        // Chaque terme doit etre prefixe : `'.libbar ' + 'a, b'` ne porte que
        // sur le premier, et les suivants redeviennent globaux. Ma premiere
        // mesure comptait ainsi toutes les cartes de la grille.
        const parts = ['button', 'select', 'input:not([type=hidden])',
                       '[role=button]'];
        const sel = ['.libbar', '#filters', '#toolbar', '#vues']
          .flatMap(z => parts.map(p => z + ' ' + p)).join(', ');
        return [...document.querySelectorAll(sel)]
          .filter(e => e.getClientRects().length > 0).length;
      })()""")
    t("controls are measurable before the first cover",
      avant is not None, avant)
    if avant is not None:
        t("fewer than ten controls before the first game", avant < 10, avant)
    t("the fold button is visible on a phone",
      bool(n.js("document.getElementById('replier').getClientRects().length > 0")),
      n.js("""(function(){
        const r = document.getElementById('replier');
        return {replier: r ? getComputedStyle(r).display : 'absent',
                toolbar: getComputedStyle(document.getElementById('toolbar')).display,
                filters: getComputedStyle(document.getElementById('filters')).display,
                largeur: window.innerWidth};
      })()"""))
    n.js("app.toggleFilters()")
    time.sleep(0.5)
    t("it unfolds the filters",
      bool(n.js("document.getElementById('toolbar').getClientRects().length > 0")))
    t("and announces it to screen readers",
      n.js("document.getElementById('replier').getAttribute('aria-expanded')")
      == "true")
    n.js("app.toggleFilters()")
    n.cmd("Emulation.setDeviceMetricsOverride",
          {"width": 1400, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
    time.sleep(1.0)


def croix(n):
    print("   -- the grid is walked with the D-pad --")
    # On a handheld, the thumb is on the D-pad. These devices emit standard
    # keyboard events: this test replays them.
    n.js("app.clearFilters()")
    time.sleep(0.5)
    total = cartes(n)
    if total < 2:
        t("enough cards to move around", False, total)
        return
    n.js("document.querySelector('#lib .gcard').focus()")
    t("the first card takes the focus",
      n.js("document.activeElement.classList.contains('gcard')"))
    t("it carries a name for screen readers",
      bool(n.js("document.activeElement.getAttribute('aria-label')")))

    def touche(k):
        n.cmd("Input.dispatchKeyEvent",
              {"type": "rawKeyDown", "key": k, "code": k,
               "windowsVirtualKeyCode": {"ArrowRight": 39, "ArrowLeft": 37,
                                         "ArrowDown": 40, "ArrowUp": 38}[k]})
        n.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": k, "code": k})
        time.sleep(0.25)

    depart = n.js("document.activeElement.dataset.key")
    touche("ArrowRight")
    apres = n.js("document.activeElement.dataset.key")
    t("the right arrow changes card", apres != depart, (depart, apres))
    touche("ArrowLeft")
    t("the left arrow comes back",
      n.js("document.activeElement.dataset.key") == depart)
    # Leaving the grid must do NOTHING: on a handheld, a wrap-around reads as a
    # button that did not answer.
    touche("ArrowLeft")
    t("leaving on the left does not move",
      n.js("document.activeElement.dataset.key") == depart)
    touche("ArrowDown")
    t("the down arrow moves one row down or not at all",
      n.js("document.activeElement.classList.contains('gcard')"))
    t("the focus ring is drawn",
      n.js("""(function(){
        const st = getComputedStyle(document.activeElement);
        return st.outlineStyle !== 'none' || st.boxShadow !== 'none';
      })()"""))


def annuler(n):
    print("   -- the trash is undone in one click --")
    # The trash IS the undo: asking "are you sure?" before putting a file in it
    # charges every time the price of a mistake that costs nothing. But the
    # "Undo" button must really RESTORE — otherwise an annoyance has been
    # replaced by a lie.
    n.js("app.clearFilters(); app.tab('jeux')")
    time.sleep(0.8)
    avant = cartes(n)
    cle = n.js("(document.querySelector('#lib .gcard') || {}).dataset ?"
               " document.querySelector('#lib .gcard').dataset.key : ''")
    chemin = n.js("""
      (function () {
        const g = jeuxUnifies().find(x => x.g.key === %s);
        return g && g.g.files && g.g.files[0] ? g.g.files[0].path : '';
      })()""" % ("'" + (cle or "").replace("'", "\\'") + "'"))
    if not chemin:
        t("a file to send to the trash", False, cle)
        return
    n.js("app.trashFile('%s')" % chemin.replace("'", "\\'"))
    time.sleep(2.5)
    t("the game leaves the grid", cartes(n) < avant, (avant, cartes(n)))
    t("a toast offers to undo",
      bool(n.js("!!document.querySelector('.toast.agir button')")))
    n.js("document.querySelector('.toast.agir button').click()")
    time.sleep(3.0)
    t("undoing puts it back in the grid", cartes(n) == avant,
      (avant, cartes(n)))


def alignement(n):
    print("   -- the bar's rows are aligned --")
    # Measured before the fix: three vertical axes within the SAME row (245,
    # 249, 250 px) and gutters of 14 then 10 px. Two causes, neither of them
    # readable: an inherited `margin-bottom` that offsets the centred box, and a
    # border that makes one group 2 px taller than its neighbours.
    geo = n.js(GEOMETRIE) or {}
    ctrl = geo.get("ctrl") or []
    t("the row's controls are measurable", len(ctrl) >= 4, len(ctrl))
    if ctrl:
        hauts = sorted({c["h"] for c in ctrl})
        hauteurs = sorted({c["b"] - c["h"] for c in ctrl})
        t("they share the same axis to within 1 px",
          max(hauts) - min(hauts) <= 1, hauts)
        t("they have the same height to within 1 px",
          max(hauteurs) - min(hauteurs) <= 1, hauteurs)
    if geo.get("libbar") and geo.get("filtres") and geo.get("barre"):
        g1 = geo["filtres"]["h"] - geo["libbar"]["b"]
        g2 = geo["barre"]["h"] - geo["filtres"]["b"]
        t("the gutters between rows are equal",
          abs(g1 - g2) <= 1, "%d puis %d" % (g1, g2))


def liste_gardee(n):
    print("   -- the unified list is kept, and redone when needed --")
    # Rebuilding and RE-SORTING the whole library cost 16.5 ms across 5 000
    # titles, on every keystroke. A cache that never refreshes would show a stale
    # list: we check BOTH halves.
    t("two calls in a row return the same list",
      n.js("jeuxUnifies() === jeuxUnifies()"))
    t("changing the sort rebuilds it", n.js("""
      (function () {
        const avant = jeuxUnifies();
        const ancien = TRI;
        const autre = Object.keys(TRIS).find(k => k !== ancien);
        if (!autre) return true;
        app.setSort(autre);
        const apres = jeuxUnifies();
        app.setSort(ancien);
        return apres !== avant;
      })()"""))
    t("a change of inventory rebuilds it", n.js("""
      (function () {
        const avant = jeuxUnifies();
        inventaireChange();
        return jeuxUnifies() !== avant;
      })()"""))


def recherche(n):
    print("   -- the search filters what is displayed --")
    avant = cartes(n)
    n.js("document.getElementById('filter').value = 'zzzzimprobable';"
         " app.filterGames()")
    time.sleep(0.6)
    t("a query with no result empties the grid", cartes(n) == 0, avant)
    n.js("document.getElementById('filter').value = ''; app.filterGames()")
    time.sleep(0.6)
    t("clearing the query fills it again", cartes(n) == avant, avant)


def filtres(n):
    print("   -- filters: counting, clearing --")
    n.js("app.clearFilters()")
    time.sleep(0.4)
    t("with no filter, \"Clear all\" is hidden",
      n.js("document.getElementById('effacefiltres').hidden"))
    n.js("document.getElementById('filter').value = 'jeu'; app.filterGames()")
    time.sleep(0.5)
    t("with a filter, it appears",
      not n.js("document.getElementById('effacefiltres').hidden"))
    t("the counter shows on the button",
      "1" in (n.js("document.getElementById('favbtn').textContent") or ""),
      n.js("document.getElementById('favbtn').textContent"))
    n.js("app.clearFilters()")
    time.sleep(0.4)
    t("\"Clear all\" empties the search",
      n.js("document.getElementById('filter').value") == "")
    t("and resets the state pill", n.js("FILTER") == "all", n.js("FILTER"))


def vues(n):
    print("   -- a saved view replays --")
    # The full round trip, through the server: the only way to know a view
    # survives and is read back.
    n.js("document.getElementById('filter').value = 'jeu'; app.filterGames()")
    time.sleep(0.4)
    n.js("""
      (async () => {
        const r = await api('/api/vue-creer',
          {nom: 'Essai', filtres: filtresCourants()});
        VUES = r.vues || []; renderViews();
      })()""")
    time.sleep(1.4)
    t("the view appears as a pill",
      (n.js("document.querySelectorAll('#vues .vue').length") or 0) >= 1)
    n.js("app.clearFilters()")
    time.sleep(0.4)
    n.js("(function () { const v = VUES.find(x => x.nom === 'Essai');"
         " if (v) app.applyView(v.id); })()")
    time.sleep(1.0)
    t("applying it restores the search",
      n.js("document.getElementById('filter').value") == "jeu",
      n.js("document.getElementById('filter').value"))
    n.js("(function () { const v = VUES.find(x => x.nom === 'Essai');"
         " if (v) app.deleteView(v.id); })()")
    time.sleep(1.2)
    t("forgetting it removes it",
      not any(v.get("nom") == "Essai" for v in (n.js("VUES") or [])))
    n.js("app.clearFilters()")


def cache(n, cible):
    print("   -- returning asks for nothing --")
    # BOTH views are loaded first: without this warm-up we would be counting a
    # legitimate first load and not a return.
    n.js("app.setSystem('%s')" % cible)
    time.sleep(1.8)
    n.js("app.setSystem('all')")
    time.sleep(1.8)
    n.js("window.__appels = []")
    n.js("app.setSystem('%s')" % cible)
    time.sleep(1.5)
    n.js("app.setSystem('all')")
    time.sleep(1.5)
    appels = [a for a in (n.js("window.__appels") or [])
              if "/api/library-all" in a or "/api/system-games" in a]
    t("no inventory call when returning to a seen platform",
      not appels, appels)


def main():
    n = Navigateur(port=9405, largeur=1400, hauteur=1000, dpr=1)
    try:
        n.cmd("Page.addScriptToEvaluateOnNewDocument", {"source": MOUCHARD})
        n.cmd("Emulation.setDeviceMetricsOverride",
              {"width": 1400, "height": 1000, "deviceScaleFactor": 1,
               "mobile": False})
        n.aller(URL, attente=3)
        attendre_pret(n)
        n.js("app.tab('jeux')")
        time.sleep(2.5)

        vue_par_defaut(n)
        n.js("app.tab('jeux')")
        time.sleep(1.5)
        alignement(n)
        pluriels(n)
        mobile(n)
        croix(n)
        annuler(n)
        liste_gardee(n)
        recherche(n)
        filtres(n)
        vues(n)

        # The target platform must have GAMES: switching to an empty list does
        # not tell code that empties the grid from code that does not.
        # `lancer_tests.py` seeds a GBA platform for this.
        systemes = n.js("Array.from(document.getElementById('sysel').options)"
                        ".map(o => o.value)") or []
        cible = None
        for k in [x for x in systemes if x != "all"]:
            n.js("app.setSystem('%s')" % k)
            time.sleep(1.0)
            if cartes(n) > 0:
                cible = k
                break
        t("a second populated platform exists in the fixture", bool(cible),
          "aucune plateforme non-Switch ne contient de jeu")
        if cible:
            cache(n, cible)
    finally:
        n.fermer()
    print("   %d ok, %d failures" % (ok, ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
