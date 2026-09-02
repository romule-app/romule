"""Audit responsive : ce qu'un doigt peut reellement atteindre, taille par taille.

Trois defauts recherches, tous invisibles a la lecture du CSS :
  * la page deborde horizontalement ;
  * un controle est recouvert par autre chose et n'attrape pas l'appui ;
  * un controle est trop petit pour un doigt (44 px est le minimum courant).
"""
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp import Navigateur

import os
URL = os.environ.get("LUDO_URL", "http://127.0.0.1:8799/")
# Cinq telephones et tablettes, puis les consoles portables de retrogaming —
# des appareils Android avec un navigateur, un ecran COURT, et des boutons
# plutot qu'un doigt precis. Aucune n'etait testee.
#
# Les viewports sont ceux que le navigateur annonce reellement : la resolution
# divisee par la densite. Un 1080p de 6 pouces rend environ 720 x 405 points
# CSS, pas 1920 x 1080.
TAILLES = [
    ("iPhone SE       ", 375, 667, 2),
    ("iPhone 15 Pro   ", 393, 852, 3),
    ("iPhone 15 PM    ", 430, 932, 3),
    ("paysage         ", 852, 393, 3),
    ("tablette        ", 768, 1024, 2),

    # Le plus petit ecran 4:3 encore vendu. S'il tient ici, il tient partout.
    ("Anbernic RG35XX ", 640, 480, 1),
    # 16:9 tres court : le cas que vise `@media (max-height:460px)`.
    ("Retroid Pocket 5", 640, 360, 3),
    # 6 pouces 1080p en paysage — le format le plus repandu des consoles
    # Android. L'Odin 2 et le Thor partagent ce viewport ; un seul profil suffit
    # donc a couvrir les deux.
    ("AYN Odin 2/Thor ", 720, 405, 2.66),
    # Le SECOND ecran du Thor : 3,92 pouces en 1080 x 1240. C'est le seul
    # viewport plus haut que large ET presque carre de la liste — une grille
    # reglee pour du 16:9 y rencontre un rapport qu'elle n'a jamais vu.
    ("AYN Thor 2e ecr.", 360, 413, 3),
    # Large mais court, et sous Linux.
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


# La sonde a gagne un filtre — « rogne par un conteneur defilant, donc pas
# recouvert » — et un filtre peut aveugler autant qu'il precise. On lui montre
# donc les DEUX cas dans une page reelle avant de lui faire confiance : un
# bouton reellement recouvert doit etre signale, le meme sorti d'un cadre
# defilant ne doit pas l'etre.
EPREUVE = r"""
(function () {
  const z = document.createElement('div');
  z.id = 'zone-epreuve';
  // DANS le champ de vision : ajoute en fin de page, le decor tombait sous la
  // ligne de flottaison et la sonde le sautait comme « hors de la vue ». Mon
  // epreuve ne prouvait alors rien — elle disait « manque » pour une raison
  // qui n'avait rien a voir avec le filtre teste.
  z.style.cssText = 'position:fixed;left:20px;top:120px;z-index:5;'
                  + 'background:#111;padding:6px';
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
    # Le port derive de l'INDEX, pas de la largeur : deux profils peuvent
    # partager la meme largeur (640 pour le RG35XX et le Retroid Pocket 5) et
    # se disputeraient alors le meme port.
    for i, (nom, l, h, dpr) in enumerate(TAILLES):
        n = Navigateur(port=9400 + i, largeur=l, hauteur=h, dpr=dpr)
        try:
            n.aller(URL, attente=3)
            for _ in range(40):
                if n.js("document.body.classList.contains('pret')"):
                    break
                time.sleep(1.5)
            time.sleep(1)
            if i == 0:                       # une seule fois : la sonde est la meme
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
