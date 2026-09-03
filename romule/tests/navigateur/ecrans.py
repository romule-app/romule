"""The interface's screens, in one single place.

Two tests sweep the rendered DOM — the sentences left in French, and the
clickable elements gone inert. Neither of them sees what is not DISPLAYED: the
screens must therefore be opened one by one.

This list used to be duplicated inside the first of those tests. Moving it here
is not tidying: a screen added to the interface must be added in ONE place,
otherwise the second test will silently go on not seeing it — which is exactly
the defect phase 3.5 fixed.
"""

import time

# Each entry opens a screen. The order matters: some depend on the previous one
# (closing the detail view before opening the wizard).
ETAPES = [
    "app.tab('jeux')",
    "app.tab('settings')",
    "app.voirEntretien('doublons')",
    "app.voirEntretien('integrite')",
    "app.voirEntretien('acces')",
    "app.auditer(true)",
    "app.toggleJournal()",
    "app.toggleDrop(true)",
    # The settings sections are exclusive: each must be opened.
    "document.querySelector(\"#setnav a[href='#sec-console']\").click()",
    "document.querySelector(\"#setnav a[href='#sec-biblio']\").click()",
    "document.querySelector(\"#setnav a[href='#sec-entretien']\").click()",
    "document.querySelector(\"#setnav a[href='#sec-acces']\").click()",
    "document.querySelector(\"#setnav a[href='#sec-interface']\").click()",
    # The server's folder browser.
    "app.tab('settings'); app.ludoOuvrir()",
    # A game's detail view: the densest screen.
    "app.tab('jeux'); (function(){const c=document.querySelector('#lib .gcard');"
    "if (c) app.openGame(c.dataset.key);})()",
    "app.closeGame(); app.openOnboard && app.openOnboard()",
    "app.closeOnboard && app.closeOnboard()",
]


def parcourir(n, releve, pause=0.9):
    """Opens each screen and applies `releve` (a JS expression) to each of them.

    Returns the union of everything `releve` reported. A step that fails is
    ignored: a screen unavailable in the current state must not bring down the
    sweep of the others.
    """
    vu = set()
    for code in ETAPES:
        try:
            n.js(code)
        except Exception:
            pass
        time.sleep(pause)
        vu |= set(n.js(releve) or [])
    return vu
