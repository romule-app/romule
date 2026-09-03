"""La bibliotheque : la bonne vue, gardee, alignee, et filtrable.

Ce que ce fichier tient, et que la lecture du code ne montre pas :

  * la bibliotheque **s'ouvre sur toutes les plateformes**, et le choix
    precedent de l'utilisateur prime — il etait ECRIT dans le stockage local a
    chaque changement, mais jamais relu, donc perdu a chaque ouverture ;
  * les trois rangees de la barre **partagent un axe et une hauteur**, et les
    gouttieres entre elles sont egales. Personne ne sait dire pourquoi une
    barre « fait desordre » ; on le mesure ;
  * la liste unifiee est **gardee** tant que rien ne bouge, et **reconstruite**
    des que quelque chose bouge — les deux moities comptent ;
  * **revenir sur une plateforme deja vue ne redemande rien** au serveur ;
  * les filtres se comptent, s'effacent d'un geste, et s'enregistrent.

Une promesse a ete RETIREE d'ici, et il vaut la peine de dire pourquoi : « la
grille ne se vide jamais pendant une bascule ». Trois versions du controle ont
ete essayees — la hauteur de `#lib` image par image, le nombre de cartes, puis
les deux avec 400 ms de latence emulee et 900 ms de retard force sur la
reponse. Les trois restaient VERTES sur le code casse, celui qui vidait les
listes avant d'attendre le reseau. Un controle qu'on n'a jamais vu echouer ne
prouve rien.

La propriete est donc tenue la ou elle se verifie sans ambiguite : un invariant
de source dans `test_ui_injection.js` interdit d'affecter une liste vide avant
le premier `await` de `setSystem`.
"""
import os
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
from cdp import Navigateur

# `LUDO_URL` est OBLIGATOIRE, et il n'y a volontairement pas de defaut.
#
# Il y en avait un : `http://127.0.0.1:8799/`. Or c'est un port ou tourne
# facilement une VRAIE instance — la mienne, en l'occurrence. Lance seul, ce
# test pilotait donc la ludotheque de quelqu'un : il rapportait « 189
# gestionnaires en ligne » parce qu'il examinait une version d'il y a trois
# mois, et il cliquait dans de vraies donnees.
#
# Un defaut qui vise un service plausible est pire qu'une erreur : il donne un
# resultat, et ce resultat parle d'autre chose. `lancer_tests.py` pose la
# variable ; qui veut viser un serveur de developpement la pose lui-meme.
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


# Compte les appels reseau. Pose avant le chargement de la page : c'est la
# seule facon de voir le tout premier appel.
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
    print("   -- la vue par defaut --")
    # Le choix precedent prime : on repart d'une ardoise propre pour eprouver
    # le DEFAUT et non un reste d'essai anterieur.
    n.js("localStorage.removeItem('systeme')")
    n.cmd("Page.reload", {})
    time.sleep(3)
    attendre_pret(n)
    time.sleep(2)
    t("la bibliotheque s'ouvre sur toutes les plateformes",
      n.js("SYS") == "all", n.js("SYS"))


def pluriels(n):
    print("   -- l'accord suit la langue --")
    # « 1 fichier(s) » n'est pas un pluriel, c'est un aveu. Et les regles ne
    # sont pas les memes : en francais 0 et 1 sont au singulier, en anglais
    # seul 1 l'est. On verifie les DEUX langues, sinon on remplace une faute
    # par une autre sans le voir.
    cas = n.js("""
      (async () => {
        const rendu = [];
        for (const langue of ['fr', 'en']) {
          await chargerLangue(langue);
          rendu.push([langue,
                      nb(0, '{fichier|fichiers}'),
                      nb(1, '{fichier|fichiers}'),
                      nb(2, '{fichier|fichiers}'),
                      phrase('%d {jeu|jeux} au total', 1),
                      phrase('%d {jeu|jeux} au total', 5)]);
        }
        await chargerLangue('fr');
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
        t("accord en %s" % langue, vus == attendu.get(langue), vus)
    t("les deux langues ont ete eprouvees", len(cas) == 2, len(cas))

    # Et rien a l'ecran ne doit plus porter la forme paresseuse.
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
    t("aucun « (s) » a l'ecran", not restes, restes[:3])


def mobile(n):
    print("   -- sur telephone, le contenu vient avant les reglages --")
    # Mesure avant : 19 controles entre le haut de l'ecran et la premiere
    # jaquette. On faisait defiler un panneau de configuration pour atteindre
    # ce qu'on etait venu voir.
    n.cmd("Emulation.setDeviceMetricsOverride",
          {"width": 430, "height": 932, "deviceScaleFactor": 2, "mobile": True})
    time.sleep(1.5)
    # Sans cette verification, tout ce qui suit serait mesure sur un ecran
    # large et passerait pour vrai : un test qui croit etre sur telephone et
    # ne l'est pas ne prouve rien.
    t("la fenetre est bien celle d'un telephone",
      n.js("window.matchMedia('(max-width:700px)').matches"),
      n.js("window.innerWidth"))
    # Ce qu'on compte : les controles DES BARRES DE LA BIBLIOTHEQUE — le
    # panneau qu'on fait defiler pour atteindre la grille. Pas l'en-tete de
    # l'application (onglets, etat de la console) : il est present sur tous les
    # ecrans et ne fait pas partie de ce qui s'interpose.
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
    t("des controles sont mesurables avant la premiere jaquette",
      avant is not None, avant)
    if avant is not None:
        t("moins de dix controles avant le premier jeu", avant < 10, avant)
    t("le bouton de repli est visible sur telephone",
      bool(n.js("document.getElementById('replier').getClientRects().length > 0")),
      n.js("""(function(){
        const r = document.getElementById('replier');
        return {replier: r ? getComputedStyle(r).display : 'absent',
                toolbar: getComputedStyle(document.getElementById('toolbar')).display,
                filters: getComputedStyle(document.getElementById('filters')).display,
                largeur: window.innerWidth};
      })()"""))
    n.js("app.basculerFiltres()")
    time.sleep(0.5)
    t("il deplie les filtres",
      bool(n.js("document.getElementById('toolbar').getClientRects().length > 0")))
    t("et l'annonce aux lecteurs d'ecran",
      n.js("document.getElementById('replier').getAttribute('aria-expanded')")
      == "true")
    n.js("app.basculerFiltres()")
    n.cmd("Emulation.setDeviceMetricsOverride",
          {"width": 1400, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
    time.sleep(1.0)


def croix(n):
    print("   -- la grille se parcourt a la croix directionnelle --")
    # Sur une console portable, le pouce est sur la croix. Ces appareils
    # emettent des evenements clavier standards : ce test les rejoue.
    n.js("app.effacerFiltres()")
    time.sleep(0.5)
    total = cartes(n)
    if total < 2:
        t("assez de cartes pour se deplacer", False, total)
        return
    n.js("document.querySelector('#lib .gcard').focus()")
    t("la premiere carte prend le focus",
      n.js("document.activeElement.classList.contains('gcard')"))
    t("elle porte un nom pour les lecteurs d'ecran",
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
    t("la fleche droite change de carte", apres != depart, (depart, apres))
    touche("ArrowLeft")
    t("la fleche gauche revient",
      n.js("document.activeElement.dataset.key") == depart)
    # Sortir de la grille ne doit RIEN faire : sur une console, un rebond se
    # lit comme un bouton qui n'a pas repondu.
    touche("ArrowLeft")
    t("sortir par la gauche ne bouge pas",
      n.js("document.activeElement.dataset.key") == depart)
    touche("ArrowDown")
    t("la fleche bas descend d'une rangee ou ne bouge pas",
      n.js("document.activeElement.classList.contains('gcard')"))
    t("l'anneau de focus est dessine",
      n.js("""(function(){
        const st = getComputedStyle(document.activeElement);
        return st.outlineStyle !== 'none' || st.boxShadow !== 'none';
      })()"""))


def annuler(n):
    print("   -- la corbeille se defait d'un clic --")
    # La corbeille EST l'annulation : demander « êtes-vous sûr ? » avant d'y
    # mettre un fichier fait payer a chaque fois le prix d'une erreur qui ne
    # coute rien. Encore faut-il que le bouton « Annuler » RESTAURE
    # reellement — sinon on a remplace une gene par un mensonge.
    n.js("app.effacerFiltres(); app.tab('jeux')")
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
        t("un fichier a mettre a la corbeille", False, cle)
        return
    n.js("app.trashFile('%s')" % chemin.replace("'", "\\'"))
    time.sleep(2.5)
    t("le jeu quitte la grille", cartes(n) < avant, (avant, cartes(n)))
    t("un toast propose d'annuler",
      bool(n.js("!!document.querySelector('.toast.agir button')")))
    n.js("document.querySelector('.toast.agir button').click()")
    time.sleep(3.0)
    t("annuler le remet dans la grille", cartes(n) == avant,
      (avant, cartes(n)))


def alignement(n):
    print("   -- les rangees de la barre sont alignees --")
    # Mesure avant correction : trois axes verticaux dans la MEME rangee
    # (245, 249, 250 px) et des gouttieres de 14 puis 10 px. Deux causes, dont
    # aucune ne se lit : un `margin-bottom` herite qui decale la boite centree,
    # et une bordure qui rend un groupe 2 px plus haut que ses voisins.
    geo = n.js(GEOMETRIE) or {}
    ctrl = geo.get("ctrl") or []
    t("les controles de la rangee sont mesurables", len(ctrl) >= 4, len(ctrl))
    if ctrl:
        hauts = sorted({c["h"] for c in ctrl})
        hauteurs = sorted({c["b"] - c["h"] for c in ctrl})
        t("ils partagent le meme axe a 1 px pres",
          max(hauts) - min(hauts) <= 1, hauts)
        t("ils ont la meme hauteur a 1 px pres",
          max(hauteurs) - min(hauteurs) <= 1, hauteurs)
    if geo.get("libbar") and geo.get("filtres") and geo.get("barre"):
        g1 = geo["filtres"]["h"] - geo["libbar"]["b"]
        g2 = geo["barre"]["h"] - geo["filtres"]["b"]
        t("les gouttieres entre rangees sont egales",
          abs(g1 - g2) <= 1, "%d puis %d" % (g1, g2))


def liste_gardee(n):
    print("   -- la liste unifiee est gardee, et refaite quand il faut --")
    # Reconstruire et RETRIER toute la bibliotheque coutait 16,5 ms sur 5 000
    # titres, a chaque frappe. Un cache qui ne se renouvelle pas afficherait
    # une liste perimee : on verifie les DEUX moities.
    t("deux appels de suite rendent la meme liste",
      n.js("jeuxUnifies() === jeuxUnifies()"))
    t("changer de tri la reconstruit", n.js("""
      (function () {
        const avant = jeuxUnifies();
        const ancien = TRI;
        const autre = Object.keys(TRIS).find(k => k !== ancien);
        if (!autre) return true;
        app.setTri(autre);
        const apres = jeuxUnifies();
        app.setTri(ancien);
        return apres !== avant;
      })()"""))
    t("un changement d'inventaire la reconstruit", n.js("""
      (function () {
        const avant = jeuxUnifies();
        inventaireChange();
        return jeuxUnifies() !== avant;
      })()"""))


def recherche(n):
    print("   -- la recherche filtre ce qui est affiche --")
    avant = cartes(n)
    n.js("document.getElementById('filter').value = 'zzzzimprobable';"
         " app.chercher()")
    time.sleep(0.6)
    t("une requete sans resultat vide la grille", cartes(n) == 0, avant)
    n.js("document.getElementById('filter').value = ''; app.chercher()")
    time.sleep(0.6)
    t("effacer la requete la remplit", cartes(n) == avant, avant)


def filtres(n):
    print("   -- filtres : compter, effacer --")
    n.js("app.effacerFiltres()")
    time.sleep(0.4)
    t("sans filtre, « Tout effacer » est cache",
      n.js("document.getElementById('effacefiltres').hidden"))
    n.js("document.getElementById('filter').value = 'jeu'; app.chercher()")
    time.sleep(0.5)
    t("avec un filtre, il apparait",
      not n.js("document.getElementById('effacefiltres').hidden"))
    t("le compteur figure sur le bouton",
      "1" in (n.js("document.getElementById('favbtn').textContent") or ""),
      n.js("document.getElementById('favbtn').textContent"))
    n.js("app.effacerFiltres()")
    time.sleep(0.4)
    t("« Tout effacer » vide la recherche",
      n.js("document.getElementById('filter').value") == "")
    t("et remet la pastille d'etat", n.js("FILTER") == "all", n.js("FILTER"))


def vues(n):
    print("   -- une vue enregistree se rejoue --")
    # Le parcours complet, par le serveur : c'est la seule facon de savoir
    # qu'une vue survit et se relit.
    n.js("document.getElementById('filter').value = 'jeu'; app.chercher()")
    time.sleep(0.4)
    n.js("""
      (async () => {
        const r = await api('/api/vue-creer',
          {nom: 'Essai', filtres: filtresCourants()});
        VUES = r.vues || []; dessinerVues();
      })()""")
    time.sleep(1.4)
    t("la vue apparait comme une puce",
      (n.js("document.querySelectorAll('#vues .vue').length") or 0) >= 1)
    n.js("app.effacerFiltres()")
    time.sleep(0.4)
    n.js("(function () { const v = VUES.find(x => x.nom === 'Essai');"
         " if (v) app.appliquerVue(v.id); })()")
    time.sleep(1.0)
    t("l'appliquer restaure la recherche",
      n.js("document.getElementById('filter').value") == "jeu",
      n.js("document.getElementById('filter').value"))
    n.js("(function () { const v = VUES.find(x => x.nom === 'Essai');"
         " if (v) app.supprimerVue(v.id); })()")
    time.sleep(1.2)
    t("l'oublier la retire",
      not any(v.get("nom") == "Essai" for v in (n.js("VUES") or [])))
    n.js("app.effacerFiltres()")


def cache(n, cible):
    print("   -- revenir ne redemande rien --")
    # Les DEUX vues sont d'abord chargees : sans cette mise en bouche on
    # compterait un premier chargement legitime et non un retour.
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
    t("aucun appel d'inventaire au retour sur une plateforme vue",
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

        # La plateforme cible doit avoir DES JEUX : basculer vers une liste
        # vide ne distingue pas un code qui vide la grille d'un code qui ne la
        # vide pas. `lancer_tests.py` seme une plateforme GBA pour cela.
        systemes = n.js("Array.from(document.getElementById('sysel').options)"
                        ".map(o => o.value)") or []
        cible = None
        for k in [x for x in systemes if x != "all"]:
            n.js("app.setSystem('%s')" % k)
            time.sleep(1.0)
            if cartes(n) > 0:
                cible = k
                break
        t("une seconde plateforme peuplee existe dans le decor", bool(cible),
          "aucune plateforme non-Switch ne contient de jeu")
        if cible:
            cache(n, cible)
    finally:
        n.fermer()
    print("   %d ok, %d echecs" % (ok, ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
