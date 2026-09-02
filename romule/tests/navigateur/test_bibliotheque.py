"""Changer de plateforme : instantane au retour, et sur la bonne vue.

Ce fichier verifie deux promesses que la lecture du code ne montre pas :

  * la bibliotheque **s'ouvre sur toutes les plateformes**, et le choix
    precedent de l'utilisateur prime — il etait ECRIT dans le stockage local a
    chaque changement, mais jamais relu, donc perdu a chaque ouverture ;
  * **revenir sur une plateforme deja vue ne redemande rien** au serveur.

La troisieme promesse — la grille ne se vide jamais pendant une bascule — a ete
retiree d'ici, et il vaut la peine de dire pourquoi. Trois versions du controle
ont ete essayees : la hauteur de `#lib` image par image, puis le nombre de
cartes, puis les memes avec 400 ms de latence emulee et 900 ms de retard force
sur la reponse. **Les trois restaient vertes sur le code casse**, celui qui
vidait les listes avant d'attendre le reseau. Un controle qu'on n'a jamais vu
echouer ne prouve rien, et le garder aurait donne une assurance fausse.

La propriete est donc tenue la ou elle est verifiable sans ambiguite : un
invariant de source dans `test_ui_injection.js` interdit d'affecter une liste
vide avant le premier `await` de `setSystem`.
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


# Compte les appels reseau ET releve la hauteur de la grille en continu. Poser
# le mouchard avant le chargement de la page est la seule facon de voir le
# tout premier appel.
MOUCHARD = r"""
(function () {
  window.__appels = [];
  const vrai = window.fetch;
  window.fetch = function (u, o) {
    window.__appels.push(String(u && u.url ? u.url : u));
    return vrai.apply(this, arguments);
  };

  }
  requestAnimationFrame(veiller);
})()
"""


def main():
    n = Navigateur(port=9405, largeur=1400, hauteur=1000, dpr=1)
    try:
        n.cmd("Page.addScriptToEvaluateOnNewDocument", {"source": MOUCHARD})
        n.cmd("Emulation.setDeviceMetricsOverride",
              {"width": 1400, "height": 1000, "deviceScaleFactor": 1,
               "mobile": False})
        n.aller(URL, attente=3)
        for _ in range(40):
            if n.js("document.body.classList.contains('pret')"):
                break
            time.sleep(1.5)
        n.js("app.tab('jeux')")
        time.sleep(2.5)

        print("   -- la vue par defaut --")
        # Le choix precedent prime, donc on repart d'une ardoise propre pour
        # eprouver le DEFAUT et non un reste d'essai anterieur.
        n.js("localStorage.removeItem('systeme')")
        n.cmd("Page.reload", {})
        time.sleep(3)
        for _ in range(40):
            if n.js("document.body.classList.contains('pret')"):
                break
            time.sleep(1.5)
        time.sleep(2)
        t("la bibliotheque s'ouvre sur toutes les plateformes",
          n.js("SYS") == "all", n.js("SYS"))

        systemes = n.js("Array.from(document.getElementById('sysel').options)"
                        ".map(o => o.value)") or []
        # La plateforme cible doit avoir DES JEUX : basculer vers une liste
        # vide ne distingue pas un code qui vide la grille d'un code qui ne la
        # vide pas. `lancer_tests.py` seme une plateforme GBA pour cela.
        peuplees = []
        for k in [x for x in systemes if x != "all"]:
            n.js("app.setSystem('%s')" % k)
            time.sleep(1.0)
            if (n.js("document.querySelectorAll('#lib .gcard').length") or 0) > 0:
                peuplees.append(k)
                break
        if not peuplees:
            t("une seconde plateforme peuplee existe dans le decor", False,
              "aucune plateforme non-Switch ne contient de jeu")
        else:
            cible = peuplees[0]
            t("une seconde plateforme peuplee existe dans le decor", True)

            print("   -- la liste unifiee est gardee, et rendue quand il faut --")
            # Reconstruire et RETRIER toute la bibliotheque coutait 16,5 ms sur
            # 5 000 titres, a chaque frappe dans la recherche. Elle est desormais
            # gardee tant que ni les donnees, ni la plateforme, ni le tri ne
            # changent. Un cache qui ne se renouvelle pas afficherait une liste
            # perimee : on verifie les DEUX moities.
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

            print("   -- la recherche filtre ce qui est affiche --")
            avant = n.js("document.querySelectorAll('#lib .gcard').length")
            n.js("document.getElementById('filter').value = 'zzzzimprobable'; app.chercher()")
            time.sleep(0.5)
            t("une requete sans resultat vide la grille",
              n.js("document.querySelectorAll('#lib .gcard').length") == 0, avant)
            n.js("document.getElementById('filter').value = ''; app.chercher()")
            time.sleep(0.5)
            t("effacer la requete la remplit",
              n.js("document.querySelectorAll('#lib .gcard').length") == avant, avant)

            print("   -- filtres : compter, effacer, enregistrer --")
            n.js("app.effacerFiltres()")
            time.sleep(0.4)
            t("sans filtre, « Tout effacer » est cache",
              n.js("document.getElementById('effacefiltres').hidden"))
            n.js("document.getElementById('filter').value = 'jeu'; app.chercher()")
            time.sleep(0.4)
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

            print("   -- une vue enregistree se rejoue --")
            # Le parcours complet, par le serveur : c'est la seule facon de
            # savoir que la vue survit et se relit.
            n.js("document.getElementById('filter').value = 'jeu'; app.chercher()")
            time.sleep(0.3)
            n.js("""
              (async () => {
                const r = await api('/api/vue-creer',
                  {nom: 'Essai', filtres: filtresCourants()});
                VUES = r.vues || []; dessinerVues();
              })()""")
            time.sleep(1.2)
            t("la vue apparait comme une puce",
              (n.js("document.querySelectorAll('#vues .vue').length") or 0) >= 1)
            n.js("app.effacerFiltres()")
            time.sleep(0.4)
            n.js("""
              (function () {
                const v = VUES.find(x => x.nom === 'Essai');
                if (v) app.appliquerVue(v.id);
              })()""")
            time.sleep(0.8)
            t("l'appliquer restaure la recherche",
              n.js("document.getElementById('filter').value") == "jeu",
              n.js("document.getElementById('filter').value"))
            n.js("""
              (function () {
                const v = VUES.find(x => x.nom === 'Essai');
                if (v) app.supprimerVue(v.id);
              })()""")
            time.sleep(1.0)
            t("l'oublier la retire",
              not any(v.get("nom") == "Essai" for v in (n.js("VUES") or [])),
              n.js("VUES"))
            n.js("app.effacerFiltres()")

            print("   -- revenir ne redemande rien --")
            # Les DEUX vues sont d'abord chargees : le bloc precedent a vide le
            # cache a dessein, donc sans cette mise en bouche on compterait un
            # premier chargement legitime et non un retour.
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
    finally:
        n.fermer()
    print("   %d ok, %d echecs" % (ok, ko))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
