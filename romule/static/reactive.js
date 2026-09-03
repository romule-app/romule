"use strict";
/* List rendering by reconciliation — ~120 lines, no dependency.

   Why this file exists
   --------------------
   The whole interface rebuilt its lists by rewriting `innerHTML`. Three defects
   followed from that, all of them met for real:
     - the entry animation replayed on every change, giving the impression the
       page was reloading;
     - the visual state (the tick, the "selected" class) had to be resynchronised
       by hand, and cases were forgotten;
     - the scroll position and the focus jumped.
   The answer was to patch around it: a render signature, manual DOM updates…
   All of it fragile code for a problem already solved.

   What it does
   ------------
   `liste()` compares the requested list to the nodes already present, relying on
   a stable KEY. An unchanged element is not touched; a modified element is
   updated in place; only real additions create a node (and therefore animate).
   It is the useful minimum of a framework, with no build and no dependency.

   What it does not do
   -------------------
   No global state, no templates, no routing. If a need outgrows this file, that
   is a sign it should be discussed, not quietly extended.
*/

(function (global) {

  /* Applies a list of items to a container.
       conteneur : the parent element
       items     : an array of data
       o.cle     : (item) -> a stable and unique identifier
       o.creer   : (item) -> HTMLElement  (called only for a new item)
       o.majEl   : (el, item) -> void     (called for every kept item)
     Returns how many nodes were created: useful for tests and debugging. */
  function liste(conteneur, items, o) {
    if (!conteneur) return 0;
    const existants = new Map();
    for (const el of Array.from(conteneur.children)) {
      const k = el.dataset ? el.dataset.rkey : null;
      if (k != null && !existants.has(k)) existants.set(k, el);
      else el.remove();                 // doublon ou noeud etranger : on nettoie
    }

    let crees = 0;
    let ancre = null;                   // the node to insert after
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
      // put the node right after the anchor if it is not already there
      const attendu = ancre ? ancre.nextSibling : conteneur.firstChild;
      if (el !== attendu) conteneur.insertBefore(el, attendu);
      ancre = el;
    }
    // whatever remains is no longer in the list
    for (const el of existants.values()) el.remove();
    return crees;
  }

  /* Sets a class only if it changes: avoids restarting a CSS transition for
     nothing, and makes the updates idempotent. */
  function classe(el, nom, actif) {
    if (!el) return;
    if (el.classList.contains(nom) !== !!actif) el.classList.toggle(nom, !!actif);
  }

  /* Writes text only if it differs: does not break a selection in progress. */
  function texte(el, valeur) {
    if (el && el.textContent !== String(valeur)) el.textContent = String(valeur);
  }

  /* Writes HTML only if it differs. To be kept for fragments we build
     ourselves: the content must already be escaped by the caller. */
  function html(el, valeur) {
    if (el && el.innerHTML !== valeur) el.innerHTML = valeur;
  }

  /* Sets an attribute, or removes it if the value is null/false. */
  function attr(el, nom, valeur) {
    if (!el) return;
    if (valeur == null || valeur === false) {
      if (el.hasAttribute(nom)) el.removeAttribute(nom);
    } else if (el.getAttribute(nom) !== String(valeur)) {
      el.setAttribute(nom, String(valeur));
    }
  }

  /* Builds an element from an HTML string. The content must be escaped
     upstream: this function sanitises nothing, it only parses. */
  function depuisHtml(s) {
    const t = document.createElement('template');
    t.innerHTML = String(s).trim();
    return t.content.firstElementChild;
  }

  global.R = {liste, classe, texte, html, attr, depuisHtml};

})(typeof window !== 'undefined' ? window : globalThis);
