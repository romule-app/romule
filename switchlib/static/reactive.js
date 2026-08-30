"use strict";
/* Rendu de listes par reconciliation — ~120 lignes, aucune dependance.

   Pourquoi ce fichier existe
   --------------------------
   Toute l'interface reconstruisait ses listes en reecrivant `innerHTML`. Trois
   defauts en decoulaient, tous rencontres pour de vrai :
     - l'animation d'entree rejouait a chaque changement, donnant l'impression
       que la page se rechargeait ;
     - l'etat visuel (coche, classe « selectionne ») devait etre resynchronise
       a la main, et on oubliait des cas ;
     - le defilement et le focus sautaient.
   La parade etait de rustiner : signature de rendu, mise a jour manuelle du
   DOM… Autant de code fragile pour un probleme deja resolu.

   Ce que ca fait
   --------------
   `liste()` compare la liste demandee aux noeuds deja presents, en s'appuyant
   sur une CLE stable. Un element inchange n'est pas touche ; un element modifie
   est mis a jour en place ; seuls les vrais ajouts creent un noeud (et donc
   animent). C'est le minimum utile d'un framework, sans build ni dependance.

   Ce que ca ne fait pas
   ---------------------
   Ni etat global, ni templates, ni routage. Si un besoin depasse ce fichier,
   c'est le signe qu'il faut en discuter, pas l'etendre en douce.
*/

(function (global) {

  /* Applique une liste d'elements a un conteneur.
       conteneur : l'element parent
       items     : tableau de donnees
       o.cle     : (item) -> identifiant stable et unique
       o.creer   : (item) -> HTMLElement  (appele uniquement pour un nouvel item)
       o.majEl   : (el, item) -> void     (appele pour chaque item conserve)
     Renvoie le nombre de noeuds crees : utile pour les tests et la mise au point. */
  function liste(conteneur, items, o) {
    if (!conteneur) return 0;
    const existants = new Map();
    for (const el of Array.from(conteneur.children)) {
      const k = el.dataset ? el.dataset.rkey : null;
      if (k != null && !existants.has(k)) existants.set(k, el);
      else el.remove();                 // doublon ou noeud etranger : on nettoie
    }

    let crees = 0;
    let ancre = null;                   // noeud apres lequel inserer
    for (const item of items) {
      const k = String(o.cle(item));
      let el = existants.get(k);
      if (el) {
        existants.delete(k);
        if (o.majEl) o.majEl(el, item);
      } else {
        el = o.creer(item);
        if (!el) continue;
        el.dataset.rkey = k;
        crees++;
      }
      // place le noeud juste apres l'ancre s'il n'y est pas deja
      const attendu = ancre ? ancre.nextSibling : conteneur.firstChild;
      if (el !== attendu) conteneur.insertBefore(el, attendu);
      ancre = el;
    }
    // ce qui reste n'est plus dans la liste
    for (const el of existants.values()) el.remove();
    return crees;
  }

  /* Pose une classe seulement si elle change : evite de relancer une transition
     CSS pour rien, et rend les mises a jour idempotentes. */
  function classe(el, nom, actif) {
    if (!el) return;
    if (el.classList.contains(nom) !== !!actif) el.classList.toggle(nom, !!actif);
  }

  /* Ecrit un texte seulement s'il differe : ne casse pas la selection en cours. */
  function texte(el, valeur) {
    if (el && el.textContent !== String(valeur)) el.textContent = String(valeur);
  }

  /* Ecrit du HTML seulement s'il differe. A reserver aux fragments que l'on
     construit soi-meme : le contenu doit deja etre echappe par l'appelant. */
  function html(el, valeur) {
    if (el && el.innerHTML !== valeur) el.innerHTML = valeur;
  }

  /* Pose un attribut, ou le retire si la valeur est nulle/false. */
  function attr(el, nom, valeur) {
    if (!el) return;
    if (valeur == null || valeur === false) {
      if (el.hasAttribute(nom)) el.removeAttribute(nom);
    } else if (el.getAttribute(nom) !== String(valeur)) {
      el.setAttribute(nom, String(valeur));
    }
  }

  /* Fabrique un element depuis une chaine HTML. Le contenu doit etre echappe
     en amont : cette fonction ne desinfecte rien, elle ne fait que parser. */
  function depuisHtml(s) {
    const t = document.createElement('template');
    t.innerHTML = String(s).trim();
    return t.content.firstElementChild;
  }

  global.R = {liste, classe, texte, html, attr, depuisHtml};

})(typeof window !== 'undefined' ? window : globalThis);
