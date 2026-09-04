"""Responsive audit: what a finger can really reach, size by size.

Three defects are looked for, all invisible when reading the CSS:
  * the page overflows horizontally;
  * a control is covered by something else and does not catch the tap;
  * a control is too small for a finger (44 px is the common minimum).
"""
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp import Navigateur

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
# Five phones and tablets, then the retro handhelds — Android devices with a
# browser, a SHORT screen, and buttons rather than a precise finger. None of them
# was tested.
#
# The viewports are the ones the browser really announces: the resolution divided
# by the density. A 6-inch 1080p screen renders about 720 x 405 CSS points, not
# 1920 x 1080.
SIZES = [
    ("iPhone SE       ", 375, 667, 2),
    ("iPhone 15 Pro   ", 393, 852, 3),
    ("iPhone 15 PM    ", 430, 932, 3),
    ("paysage         ", 852, 393, 3),
    ("tablette        ", 768, 1024, 2),

    # The smallest 4:3 screen still sold. If it holds here, it holds anywhere.
    ("Anbernic RG35XX ", 640, 480, 1),
    # A very short 16:9: the case `@media (max-height:460px)` targets.
    ("Retroid Pocket 5", 640, 360, 3),
    # A 6-inch 1080p in landscape — the most widespread format among Android
    # handhelds. The Odin 2 and the Thor share this viewport; one profile
    # therefore covers both.
    ("AYN Odin 2/Thor ", 720, 405, 2.66),
    # The Thor's SECOND screen: 3.92 inches at 1080 x 1240. It is the list's
    # only viewport taller than it is wide AND nearly square — a grid tuned for
    # 16:9 meets a ratio there it has never seen.
    ("AYN Thor 2e ecr.", 360, 413, 3),
    # Wide but short, and running Linux.
    ("Steam Deck      ", 1280, 800, 1),
]

SONDE = r"""
(function () {
  const MIN = 44;
  const res = {debord: document.documentElement.scrollWidth - innerWidth,
               bloques: [], petits: [], total: 0};

  // Un element d'un panneau ferme n'est pas « recouvert » : il n'est pas la.
  // On ne garde que ce qui est reellement affiche ET reellement cliquable,
  // en remontant toute la chaine des parents.
  function utilisable(el) {
    if (el.checkVisibility && !el.checkVisibility(
        {opacityProperty: true, visibilityProperty: true})) return false;
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const st = getComputedStyle(n);
      if (st.pointerEvents === 'none') return false;
      if (+st.opacity === 0) return false;
      if (st.display === 'none' || st.visibility === 'hidden') return false;
    }
    return true;
  }

  // Un element sorti du cadre d'un conteneur DEFILANT n'est pas « recouvert » :
  // il n'est pas a l'ecran, et un geste de defilement le ramene. Sans cette
  // distinction, la barre des reglages — qui defile a l'horizontale sur un
  // petit ecran — faisait signaler son dernier onglet comme inatteignable,
  // alors qu'il suffit de faire glisser la barre.
  //
  // `getBoundingClientRect()` rend la position de MISE EN PAGE, pas ce qui est
  // reellement peint : un element rogne par le `overflow` d'un ancetre garde
  // un rectangle a sa place theorique. C'est ce qui rendait le faux positif
  // invisible a la lecture.
  function rogne(el) {
    const r = el.getBoundingClientRect();
    for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
      const st = getComputedStyle(n);
      if (!/auto|scroll|hidden/.test(st.overflowX + ' ' + st.overflowY)) continue;
      const c = n.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      if (cx < c.left || cx > c.right || cy < c.top || cy > c.bottom) return true;
    }
    return false;
  }

  // `[data-act]` a remplace `[onclick]` : depuis la phase 4, un element
  // cliquable porte son action en donnee, pas en code. Il n'y a plus un seul
  // `onclick` dans le projet, et `test_ui_injection.js` echoue si l'un revient.
  const sel = 'button, a[href], select, input:not([type=hidden]), '
            + '[data-act], [data-act-change], .chip';
  for (const el of document.querySelectorAll(sel)) {
    if (!utilisable(el)) continue;
    if (rogne(el)) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (r.bottom < 8 || r.top > innerHeight - 8) continue;      // hors de la vue
    if (r.right < 8 || r.left > innerWidth - 8) continue;
    res.total++;
    const nom = (el.id ? '#' + el.id : '') ||
                (el.className && typeof el.className === 'string'
                  ? '.' + el.className.split(' ')[0] : el.tagName);
    const etiq = (el.textContent || el.value || '').trim().slice(0, 22);
    // Un en-tete colle recouvre par definition ce qui a defile dessous :
    // ce n'est pas un defaut, on ne teste donc pas cette bande.
    const tete = document.querySelector('header');
    const basTete = (tete && getComputedStyle(tete).position === 'sticky')
      ? tete.getBoundingClientRect().bottom : 0;
    const x = Math.min(innerWidth - 2, Math.max(2, r.left + r.width / 2));
    const y = Math.min(innerHeight - 2, Math.max(2, r.top + r.height / 2));
    if (y < basTete) continue;
    const d = document.elementFromPoint(x, y);
    if (!(d && (d === el || el.contains(d) || d.contains(el)))) {
      res.bloques.push(nom + ' « ' + etiq + ' » recouvert par ' +
        (d ? (d.id ? '#' + d.id : '.' + String(d.className).split(' ')[0]) : 'rien'));
    }
    if (r.height < MIN - 6) {
      res.petits.push(nom + ' « ' + etiq + ' » ' +
        Math.round(r.width) + 'x' + Math.round(r.height));
    }
  }
  return res;
})()
"""


def uniq(xs):
    vus, out = set(), []
    for x in xs:
        if x not in vus:
            vus.add(x)
            out.append(x)
    return out


# The probe gained a filter — "clipped by a scrolling container, therefore not
# covered" — and a filter can blind as much as it sharpens. So we show it BOTH
# cases in a real page before trusting it: a button really covered must be
# reported, the same one taken out of a scrolling frame must not.
EPREUVE = r"""
(function () {
  const z = document.createElement('div');
  z.id = 'zone-epreuve';
  // DANS le champ de vision : ajoute en fin de page, le decor tombait sous la
  // ligne de flottaison et la sonde le sautait comme « hors de la vue ». Mon
  // epreuve ne prouvait alors rien — elle disait « manque » pour une raison
  // qui n'avait rien a voir avec le filtre teste.
  // SOUS l'en-tete colle, mesure a l'execution. Une position fixe en dur
  // (120 px) a fini par tomber DANS l'en-tete quand celui-ci a grandi, et la
  // sonde sautait le decor comme « recouvert par l'en-tete, ce qui est
  // normal » — donc l'epreuve annoncait un manque qui n'en etait pas un.
  const tete = document.querySelector('header');
  const bas = tete ? Math.ceil(tete.getBoundingClientRect().bottom) : 0;
  z.style.cssText = 'position:fixed;left:20px;z-index:5;background:#111;'
                  + 'padding:6px;top:' + (bas + 24) + 'px';
  z.innerHTML =
    '<div style="position:relative;height:60px">'
  +   '<button id="e-couvert" style="position:absolute;left:0;top:0;'
  +     'width:120px;height:44px">couvert</button>'
  +   '<div style="position:absolute;left:0;top:0;width:120px;height:44px;'
  +     'background:#000"></div>'
  + '</div>'
  + '<div id="e-cadre" style="width:80px;overflow-x:auto;white-space:nowrap">'
  +   '<button style="width:60px;height:44px">a</button>'
  +   '<button id="e-rogne" style="width:300px;height:44px">hors cadre</button>'
  + '</div>';
  document.body.appendChild(z);
})()
"""


def eprouver(n):
    """Rend (couvert_signale, rogne_signale)."""
    n.js(EPREUVE)
    time.sleep(0.4)
    vus = (n.js(SONDE) or {}).get("bloques") or []
    texte = " | ".join(vus)
    n.js("document.getElementById('zone-epreuve').remove()")
    return "#e-couvert" in texte, "#e-rogne" in texte


def main():
    total_pb = 0
    # The port derives from the INDEX, not from the width: two profiles can
    # share the same width (640 for the RG35XX and the Retroid Pocket 5) and
    # would then fight over the same port.
    for i, (nom, l, h, dpr) in enumerate(SIZES):
        n = Navigateur(port=9400 + i, largeur=l, hauteur=h, dpr=dpr)
        try:
            n.aller(URL, attente=3)
            for _ in range(40):
                if n.js("document.body.classList.contains('pret')"):
                    break
                time.sleep(1.5)
            time.sleep(1)
            if i == 0:                       # once only: the probe is the same
                couvert, rogne_ = eprouver(n)
                print("   sonde : recouvrement reel %s | rognage ignore %s"
                      % ("vu" if couvert else "MANQUE",
                         "oui" if not rogne_ else "NON"))
                if not couvert or rogne_:
                    print("   ::error:: la sonde ne distingue plus recouvert "
                          "et rogne — les resultats qui suivent ne valent rien")
                    total_pb += 1
            for onglet, libelle in (("jeux", "Jeux"), ("settings", "Réglages")):
                n.js("app.tab('%s')" % onglet)
                time.sleep(0.6)
                r = n.js(SONDE)
                pb = []
                if r["debord"] > 1:
                    pb.append("deborde de %d px" % r["debord"])
                bl, pt = uniq(r["bloques"]), uniq(r["petits"])
                if bl:
                    pb.append("%d recouvert(s)" % len(bl))
                if pt:
                    pb.append("%d trop petit(s)" % len(pt))
                total_pb += len(bl) + len(pt) + (1 if r["debord"] > 1 else 0)
                etat = " | ".join(pb) if pb else "rien a signaler"
                print("   %s %-9s %3d controles  %s" % (nom, libelle, r["total"], etat))
                for x in bl[:4]:
                    print("        recouvert : %s" % x)
                for x in pt[:4]:
                    print("        trop petit: %s" % x)
        finally:
            n.fermer()
    print("   ------------------------------------------------")
    print("   %d probleme(s) au total" % total_pb)
    return 1 if total_pb else 0


if __name__ == "__main__":
    sys.exit(main())
