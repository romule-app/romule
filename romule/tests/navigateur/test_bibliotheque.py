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
