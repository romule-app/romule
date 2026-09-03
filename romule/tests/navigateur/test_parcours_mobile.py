"""A real journey on a phone: we open every surface and check it displays,
fits on the screen, and answers a finger.

The static audit only sees what is on screen at load time. Here we scroll the
page and open the panels, where the user got stuck.
"""
import sys
from pathlib import Path
import time

RACINE = str(Path(__file__).resolve().parent)
sys.path.insert(0, RACINE)
from cdp import Navigateur
from audit_responsive import SONDE

import os
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


def centre(n, sel):
    return n.js("(()=>{const e=document.querySelector(%r);if(!e)return null;"
                "const r=e.getBoundingClientRect();"
                "return {x:r.left+r.width/2,y:r.top+r.height/2,"
                "vu:r.top>=0&&r.bottom<=innerHeight};})()" % sel)


def taper_sel(n, sel):
    c = centre(n, sel)
    if not c:
        return False
    if not c["vu"]:
        n.js("document.querySelector(%r).scrollIntoView({block:'center'})" % sel)
        time.sleep(0.4)
        c = centre(n, sel)
    n.taper(c["x"], c["y"])
    return True


def main():
    n = Navigateur(port=9360, largeur=393, hauteur=852, dpr=3)
    try:
        n.aller(URL, attente=3)
        for _ in range(40):
            if n.js("document.body.classList.contains('pret')"):
                break
            time.sleep(1.5)
        time.sleep(1.5)

        print("   -- 1. demarrage silencieux --")
        t("aucune notification empilee",
          n.js("document.querySelectorAll('#toasts .toast').length") == 0,
          n.js("[...document.querySelectorAll('#toasts .toast')].map(x=>x.textContent)"))
        # This assertion required "Console détectée", so a console PLUGGED IN.
        # It failed as soon as there was none — that is, at every new user's, and
        # on every continuous-integration runner. What we want to check here is
        # that the startup leaves a trace in the log, not which one.
        t("les evenements sont au journal",
          n.js("JLOG.length") >= 1, n.js("JLOG.map(l=>l.m)"))
        t("le bouton du journal signale du nouveau",
          n.js("document.getElementById('journalbtn').classList.contains('news')"))

        print("   -- 2. defilement : rien ne deborde, rien n'est recouvert --")
        hauteur = n.js("document.documentElement.scrollHeight")
        pas, y, pbs = 700, 0, []
        while y < min(hauteur, 6000):
            n.js("scrollTo(0,%d)" % y)
            time.sleep(0.35)
            r = n.js(SONDE)
            if r["debord"] > 1:
                pbs.append("deborde de %d px a y=%d" % (r["debord"], y))
            pbs += ["%s (y=%d)" % (b, y) for b in r["bloques"]]
            pbs += ["%s (y=%d)" % (p, y) for p in r["petits"]]
            y += pas
        t("page entiere sans defaut", not pbs, " | ".join(pbs[:3]))
        n.js("scrollTo(0,0)")
        time.sleep(0.3)

        print("   -- 3. journal --")
        taper_sel(n, "#journalbtn")
        time.sleep(0.5)
        t("le tiroir s'ouvre",
          n.js("document.getElementById('jdrawer').classList.contains('open')"))
        t("il tient dans l'ecran",
          n.js("document.getElementById('jdrawer').getBoundingClientRect().width") <= 393)
        t("il contient les evenements du demarrage",
          n.js("document.querySelectorAll('#jdrawer .jline, #jdrawer [class*=jl]').length") >= 1,
          n.js("document.getElementById('jdrawer').textContent.length"))
        n.capture(RACINE + "/m-journal.png")
        n.js("app.toggleJournal()")
        time.sleep(0.4)

        print("   -- 4. fiche d'un jeu --")
        t("le bouton Détails ouvre la fiche", taper_sel(n, ".gcard button.pinfo"))
        time.sleep(1.2)
        ouvert = n.js("document.getElementById('modal').classList.contains('open')")
        t("la fiche est ouverte", ouvert)
        if ouvert:
            m = n.js("(()=>{const s=document.querySelector('#modal .sheet');"
                     "const r=s.getBoundingClientRect();"
                     "return {l:Math.round(r.width), deborde:r.width>innerWidth,"
                     "titre:(s.querySelector('h3')||{}).textContent,"
                     "actions:s.querySelectorAll('.acts button').length};})()")
            t("elle tient dans la largeur", not m["deborde"], m)
            t("elle a un titre", bool(m["titre"]), m)
            t("ses actions sont presentes", m["actions"] > 0, m)
            n.capture(RACINE + "/m-fiche.png")
            n.js("app.closeGame()")
            time.sleep(0.4)

        print("   -- 5. panneau d'ajout de jeux --")
        taper_sel(n, "#fab")
        time.sleep(0.5)
        t("le panneau s'ouvre",
          n.js("document.getElementById('dropwrap').classList.contains('on')"))
        t("il tient dans la largeur",
          n.js("document.getElementById('dropwrap').getBoundingClientRect().right") <= 394,
          n.js("document.getElementById('dropwrap').getBoundingClientRect().right"))
        n.js("app.toggleDrop(false)")
        time.sleep(0.3)

        print("   -- 6. onglet Réglages --")
        n.js("app.tab('settings')")
        time.sleep(0.8)
        t("les groupes de reglages s'affichent",
          n.js("document.querySelectorAll('#panel-settings .setgroup').length") > 5,
          n.js("document.querySelectorAll('#panel-settings .setgroup').length"))
        t("aucun controle ne deborde",
          n.js("document.documentElement.scrollWidth - innerWidth") <= 1)
        n.capture(RACINE + "/m-reglages.png")

        print("   -- 7. proposition d'installation --")
        t("la banniere existe dans le DOM", n.js("!!document.getElementById('a2hs')"))
        t("l'evenement d'installation est capte",
          n.js("typeof INSTALL_EVT !== 'undefined'"))
        t("le manifeste est servi",
          n.js("!!document.querySelector('link[rel=manifest]')"))

    finally:
        n.fermer()
    print("   ------------------------------------------------")
    print("   %d controles OK, %d echec(s)" % (ok, ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
