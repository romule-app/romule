"use strict";
// Interface de la ludotheque Switch. Tout l'etat metier vient du serveur ;
// ce fichier l'affiche, gere les onglets, les animations et relaie les actions.

let DATA = {files: [], stats: {}, config: {}};
let GAMES = [];                 // jeux regroupes (vue bibliotheque)
let DGAMES = [];                // fichiers listes sur la console
let CONSET = new Set();          // empreintes (tid|version) des jeux sur la console
let BROWSE_PATH = "";            // dossier courant du navigateur de la console
let CIBLE_PARCOURS = 'roms';     // ce que le navigateur enregistrera : 'roms', 'switch' ou une plateforme
let TREE = {};                   // etat des dossiers GAMES/UPDATE/DLC sur la console
let FILTER = "all";             // all | update | convert | clean
let CONN = {};                  // lien vers la console : {kind: 'usb'|'wifi'|null}
let CONN_INFO = null;           // identite de la console reliee (nom, serie)
let META = {};                  // {tid: {nom, resume}} — fiches officielles en cache
let NANDST = [];                // MAJ/DLC et leur etat vis-a-vis d'Eden
let NANDCONN = false;           // la console repond-elle ?
let SYSTEMS = [];               // consoles/systemes disponibles
// La bibliotheque s'ouvre sur TOUTES les plateformes : c'est ce qu'on possede,
// et non l'une de ses parties. Le choix precedent de l'utilisateur prime — il
// etait ECRIT dans le stockage local a chaque changement, mais n'etait jamais
// relu, donc perdu a chaque ouverture.
let SYS = (() => {
  try { return localStorage.getItem('systeme') || 'all'; } catch (e) { return 'all'; }
})();
let SGAMES = [];                // jeux du systeme generique courant
let SCONSOLE = [];              // noms de fichiers de ce systeme sur la console
let SCONSOLE_PATHS = [];        // leurs chemins complets, pour pouvoir les retirer
let SCONSOLE_TAILLES = {};      // taille par chemin : la fiche affichait 0 octet
let SCONSOLE_TITRES = {};       // titre officiel par chemin, quand il est connu
let SALL = [];                  // toutes les plateformes, pour la vue d'ensemble
// Ce qu'on a deja recu, par plateforme. Un cache de SESSION : il ne survit pas
// au rechargement de la page, et il est vide des que l'inventaire bouge —
// fin de tache, « Actualiser », depot de fichiers. Un cache qu'on ne sait pas
// invalider est un bug d'affichage a retardement.
const CACHE_SYS = {};
// Numero de la demande en cours : une reponse plus lente qu'un second clic ne
// doit pas ecraser l'inventaire de la plateforme finalement choisie.
let CHARGE_SYS = 0;

function oublierCacheSysteme() {
  for (const k of Object.keys(CACHE_SYS)) delete CACHE_SYS[k];
}

function appliquerSysteme(d) {
  SALL = d.tout || [];
  SGAMES = d.games || [];
  SCONSOLE = (d.console || []).map(x => x.nom || x);
  SCONSOLE_PATHS = (d.console || []).map(x => x.chemin || '').filter(Boolean);
  SCONSOLE_TAILLES = {};
  SCONSOLE_TITRES = {};
  (d.console || []).forEach(x => {
    if (!x.chemin) return;
    SCONSOLE_TAILLES[x.chemin] = x.taille || 0;
    SCONSOLE_TITRES[x.chemin] = x.titre || '';
  });
}

const $ = id => document.getElementById(id);
// Les unites binaires ne s'ecrivent pas pareil partout : « Gio » en francais,
// « GiB » en anglais. Elles apparaissent sur CHAQUE jaquette — c'etait le
// francais le plus visible de toute l'interface anglaise.
const UNITES = {
  fr: ['o', 'Kio', 'Mio', 'Gio', 'Tio'],
  en: ['B', 'KiB', 'MiB', 'GiB', 'TiB'],
};
const fmt = b => {
  if (b == null) return '?';
  const u = UNITES[LANGUE] || UNITES.en;
  let i = 0;
  while (b >= 1024 && i < 4) { b /= 1024; i++; }
  return (i ? b.toFixed(1) : b) + ' ' + u[i];
};
const esc = s => String(s).replace(/[&<>"']/g,
  c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

// Une valeur qui entre dans une CHAINE JavaScript a l'interieur d'un attribut
// de gestionnaire — `onclick="app.faire('ICI')"` — traverse DEUX analyseurs :
// l'analyseur HTML decode d'abord les entites, puis le moteur JavaScript
// compile ce qu'il en reste.
//
// `esc()` ne repond qu'au premier, et c'est ce qui rendait le trou invisible :
// il transforme bien l'apostrophe en `&#39;`, mais l'analyseur HTML la rend
// AVANT que le JavaScript ne soit lu. La chaine se referme, et la suite de la
// valeur devient du code.
//
// Il n'y a rien d'exotique a fabriquer une telle valeur : la cle d'une carte
// EST le chemin du fichier, et rien n'interdit l'apostrophe dans un nom de
// fichier. `x',alert(1),'.gba` suffit.
//
// On echappe donc pour le contexte JavaScript D'ABORD, pour le contexte HTML
// ensuite. L'ordre compte : l'inverse laisserait `esc` reintroduire des
// entites que le moteur JavaScript ne sait pas relire.
//
// Le vrai remede reste de sortir ces valeurs des attributs — `data-grp` le
// fait deja pour la cle de groupe. Tant que les gestionnaires en ligne sont
// la, c'est cet encodage qui tient.
// Alias de `t()`, pour les rares fonctions dont un parametre s'appelle deja
// `t` — un title ID, un element. Renommer le parametre serait plus propre ;
// l'alias evite de toucher a des signatures utilisees partout, et le garde-fou
// de test_ui_injection.js continue d'interdire les autres masquages.
const t18n = (texte, defaut) => t(texte, defaut);

const jsq = v => esc(JSON.stringify(String(v == null ? '' : v))
  .slice(1, -1)                    // JSON rend une chaine entre guillemets
  .replace(/'/g, "\\'")            // que JSON, lui, n'echappe pas
  // JSON laisse passer U+2028/2029 bruts ; le moteur JavaScript les a longtemps
  // lus comme des fins de ligne, donc comme une chaine non terminee.
  .replace(/\u2028/g, '\\u2028')
  .replace(/\u2029/g, '\\u2029'));
// Titre officiel dans la langue choisie, quand la fiche est en cache ; sinon le
// nom du fichier. Un nom de fichier dit « [Game] Pokemon Sword [0100ABF...] » la
// ou l'editeur dit « Pokémon Épée ».
// Quand aucune fiche n'existe — un pack .xci ne porte aucun title ID et `nsz`
// echoue a le lire — on rend le nom de fichier presentable plutot que d'afficher
// « Mario.Kart.8.Deluxe.(v3.0.3 & DLC).SuperXCI -MBC ».
const GROUPES_SCENE = /\b(superxci|xci|nsp|nsz|xcz|mbc|upd|repack|nsw|switch|multi\d*|fr|eu|us|jp|eur|usa|jpn)\b/gi;

function nomLisible(fichier) {
  // toute extension de ROM, pas seulement celles de la Switch : « .gba »,
  // « .iso », « .chd »… La borne 2-4 caracteres evite de tronquer un titre.
  let s = String(fichier || '').replace(/\.[a-z0-9]{2,4}$/i, '');
  s = s.replace(/[\[\(][^\])]*[\])]/g, ' ');       // [tid], (EU), (v3.0.3 & DLC)
  s = s.replace(/\bv\d+(\.\d+)*\b/gi, ' ');        // v1.0.1, v262144
  // les noms « scene » separent par des points : on ne remplace que si le nom
  // en compte plus que de vrais espaces, pour ne pas casser « Super Smash Bros. »
  const pts = (s.match(/\./g) || []).length, esp = (s.match(/ /g) || []).length;
  if (pts > esp) s = s.replace(/\./g, ' ');
  s = s.replace(/[-_]+/g, ' ').replace(GROUPES_SCENE, ' ');
  // crochets et parentheses orphelins : certains noms sont mal formes, comme
  // « … [0100ABF008968000][v0][US]) », et laissent une parenthese seule
  s = s.replace(/[\[\]{}()]/g, ' ');
  s = s.replace(/\s{2,}/g, ' ').replace(/^[\s.\-–]+|[\s.\-–]+$/g, '');
  return s || pretty(fichier);
}

function nomJeu(g) {
  const m = g && g.tid && META[String(g.tid).toLowerCase()];
  if (m && m.nom) return m.nom.replace(/^\(([^)]{2,14})\)\s*/, '').trim();
  // hors Switch : titre officiel resolu par SteamGridDB, s'il a ete recupere
  const t = g && (g.titre || (g.files && g.files[0] && g.files[0].titre));
  if (t) return t;
  return nomLisible(pretty((g && g.name) || ''));
}
// Provenance du resume affiche. Aujourd'hui une seule source demande d'etre
// citee — Wikipedia, sous CC BY-SA — mais la forme se prete a d'autres.
function creditResume(g) {
  const f = (g && (g.files && g.files[0])) || g || {};
  const src = String(f.source_resume || g.source_resume || '');
  if (!src.startsWith('wikipedia:')) return '';
  const url = f.url_resume || g.url_resume || '';
  const nom = t('Wikipédia');
  const lien = url
    ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' +
      esc(nom) + '</a>'
    : esc(nom);
  return phrase('Résumé issu de %s, sous licence CC BY-SA.', lien);
}

function resumeJeu(g) {
  const m = g && g.tid && META[String(g.tid).toLowerCase()];
  if (m && m.resume) return m.resume;
  // Hors Switch, le resume vient d'IGDB et voyage avec le jeu : sans ce repli,
  // aucune description ne s'affichait jamais pour ces plateformes.
  const f = g && (g.resume || (g.files && g.files[0] && g.files[0].resume));
  return f || '';
}

// Annee et editeur, quand la source les fournit (IGDB pour les non-Switch).
function contexteJeu(g) {
  const f = g && (g.files && g.files[0]) || g || {};
  return [f.annee || g.annee, f.editeur || g.editeur].filter(Boolean).join('  ·  ');
}
// Un compteur qui passe de 34 a 10 d'un seul coup ne se remarque pas : on ne
// sait pas s'il a change ni dans quel sens. En le faisant defiler, le
// mouvement dit « ca vient de bouger, et ca descend ».
const CHIFFRE_MS = 340;
const CHIFFRE_EN_COURS = new WeakMap();

function chiffreAnime(el, cible) {
  cible = Number(cible) || 0;
  const depart = Number(el.textContent.replace(/\D/g, ''));
  const enCours = CHIFFRE_EN_COURS.get(el);
  if (enCours) cancelAnimationFrame(enCours);
  // Rien a raconter : premier affichage, valeur inchangee, mouvement coupe —
  // ou DOM simplifie des tests, qui n'a pas d'horloge d'animation.
  if (!Number.isFinite(depart) || depart === cible ||
      typeof requestAnimationFrame !== 'function' ||
      document.documentElement.dataset.mvt === 'aucun') {
    el.textContent = String(cible);
    return;
  }
  const t0 = performance.now();
  const pas = (maintenant) => {
    const p = Math.min(1, (maintenant - t0) / CHIFFRE_MS);
    // depart lent puis arret net : le chiffre « se pose » sur sa valeur
    const doux = 1 - Math.pow(1 - p, 3);
    el.textContent = String(Math.round(depart + (cible - depart) * doux));
    if (p < 1) CHIFFRE_EN_COURS.set(el, requestAnimationFrame(pas));
    else CHIFFRE_EN_COURS.delete(el);
  };
  CHIFFRE_EN_COURS.set(el, requestAnimationFrame(pas));
}

// Coupe proprement sur un mot, jamais au milieu.
function extrait(t, n) {
  t = String(t || '').trim();
  if (t.length <= n) return t;
  const c = t.slice(0, n);
  return c.slice(0, Math.max(c.lastIndexOf(' '), n - 20)).replace(/[\s,;:.]+$/, '') + '…';
}

// remplace les colons modificateurs des noms de fichiers Switch par ':'
const pretty = s => String(s).replace(/[꞉∶：]/g, ':');
const tidBase = tid => {
  let n = parseInt(tid[12], 16); if (n % 2) n--;
  return tid.slice(0, 12) + n.toString(16) + '000';
};
function tidHtml(t) {   // title ID decoupe (detail uniquement)
  // La classe `tid` est dans CLASSES_DONNEES : elle porte un identifiant, qui
  // ne se traduit pas. Mais quand il n'y en a pas, elle portait un LIBELLE, qui
  // lui doit se traduire — et restait donc en francais. Meme defaut que `cnom`,
  // pour la quatrieme fois : une classe ne peut pas etre a la fois un style et
  // un marqueur. Le libelle prend sa propre classe.
  if (!t) return '<span class="tid-vide">' + esc(t18n('pas de title ID')) + '</span>';
  return '<span class="tid">' + t.slice(0, 12) + '<b>' + t[12] + '</b>' +
    t.slice(13) + '</span>';
}
// `discret` : l'appelant affiche lui-meme le refus. Un mot de passe trop
// court est une correction a faire, pas une panne : la fenetre « Une action
// n'a pas abouti » serait hors sujet.
async function api(path, body, discret) {
  let j;
  try {
    const r = await fetch(path, body
      ? {method: 'POST',
         headers: {'Content-Type': 'application/json'},  // i18n:ok - type MIME
         body: JSON.stringify(body)}
      : {});
    j = await r.json();
  } catch (e) {
    // Une reponse HTML au lieu de JSON, c'est la page de connexion : la session
    // a expire, ou l'authentification vient d'etre activee ailleurs. Le message
    // brut (« Unexpected token '<' ») ne disait rien a personne.
    j = /Unexpected token '<'|not valid JSON/.test(e.message || '')
      ? {error: 'Session expirée : reconnecte-toi.', _session: true}
      : {error: phrase('réseau : %s', e.message)};
  }
  if (j && j._session) {
    dialogue({
      titre: 'Session expirée',
      niveau: 'warn',
      message: "La ludothèque demande maintenant une connexion. Recharge la page "
             + 'pour t\'identifier.',
      actions: [{libelle: 'Recharger', principal: true,
                 faire: () => location.reload()}],
    });
    return j;
  }
  if (j && j.error) {
    journal(path + ' : ' + j.error, 'error');
    if (discret) return j;
    dialogue({
      titre: 'Une action n\'a pas abouti',
      niveau: 'error',
      message: messageLisible(path, j.error),
      detail: path + '\n' + j.error,
      actions: [{libelle: 'Copier le détail',
                 faire: () => navigator.clipboard.writeText(path + ' : ' + j.error)
                   .then(() => toast('Détail copié.', 'ok')).catch(() => {})},
                {libelle: 'Ouvrir le journal',
                 faire: () => { if (!$('jdrawer').classList.contains('open')) app.toggleJournal();
                                app.setJFilter('error'); }}],
    });
  }
  return j;
}
// ------------------------------------------------------------ traductions
// Les libelles vivent dans romule/locales/<code>.json, jamais dans le code.
// Le texte FRANCAIS est la cle de traduction (principe gettext). Deux raisons :
// on n'invente pas 570 identifiants, et une traduction manquante retombe sur
// une phrase lisible plutot que sur « lib.filter.all ».
//
// La traduction s'applique au DOM une fois celui-ci construit, pas a chaque
// endroit du code qui fabrique du texte. Un observateur suffit donc a couvrir
// l'interface entiere, y compris ce qui est genere en JavaScript, sans qu'on
// ait a modifier 400 appels — et sans qu'un oubli soit possible.
let I18N = {};
// Langue d'affichage. La CLE de traduction reste la phrase francaise — c'est
// le principe gettext retenu par le projet — mais la langue par defaut est
// l'anglais : `en.json` traduit ces cles au chargement.
let LANGUE = 'en';

// Ce qu'on ne traduit JAMAIS : du code, des chemins, et surtout les donnees de
// l'utilisateur (noms de jeux, adresses email, chemins de fichiers).
const NON_TRADUIT = new Set(['CODE', 'PRE', 'SCRIPT', 'STYLE', 'TEXTAREA']);
// Ces classes marquent des noeuds dont TOUT le contenu est une donnee : un
// titre de jeu, une adresse, un chemin. Elles ne doivent jamais servir aussi de
// selecteur de style pour du texte d'interface — c'est le defaut qui a fige
// `tid`, puis `cnom`, puis le journal entier.
//
// `jline`, `brow` et `crumb` en sont sorties : elles enveloppent un MELANGE.
// Une ligne de journal contient l'horodatage, le niveau et le message ; seul
// le message est une donnee. Les envelopper entierement gelait « Dossier
// vide. », « .. (dossier parent) » et tout le journal, qui restait donc en
// francais dans une interface anglaise.
//
// La donnee porte desormais `data-i18n-skip`, l'attribut que `traduisible()`
// lit deja : il marque le noeud exact, pas son voisinage.
const CLASSES_DONNEES = ['gname', 'compte-mail', 'pfchemin', 'tid',
                         'hostchip', 'cnom'];

// Les phrases du HTML sont reparties sur plusieurs lignes : le noeud de texte
// contient des retours a la ligne et des indentations que la cle n'a pas. On
// compare donc sur une forme a espaces normalises.
let I18N_PLAT = {};
// Les phrases construites a l'execution (« 12 plateforme(s) sous … ») ne
// peuvent pas correspondre exactement. Une entree contenant %s devient un
// gabarit : on retrouve la phrase et on replace les parties variables.
let I18N_GABARITS = [];

function _plat(s) {
  return String(s || "").replace(/\s+/g, ' ').trim();
}

function _compilerGabarits() {
  I18N_PLAT = {};
  I18N_GABARITS = [];
  for (const [fr, en] of Object.entries(I18N)) {
    const plat = _plat(fr);
    I18N_PLAT[plat] = en;
    if (plat.includes('%s')) {
      const motif = plat.split('%s')
        .map(x => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
        .join('(.+?)');
      I18N_GABARITS.push({re: new RegExp('^' + motif + '$'), en});
    }
  }
}

function traduit(texte) {
  const plat = _plat(texte);
  const direct = I18N_PLAT[plat];
  if (direct && !plat.includes('%s')) return direct;
  for (const g of I18N_GABARITS) {
    const m = plat.match(g.re);
    if (m) {
      let i = 1;
      return g.en.replace(/%s/g, () => m[i++] ?? '');
    }
  }
  return null;
}

// Un nombre suivi de son unite : « 15 jeu(x) ». Ecrit `n + ' jeu(x)'`, cela
// formait une chaine dont le NOMBRE fait partie — donc introuvable dans un
// catalogue, donc jamais traduite. Le nombre reste dehors, l'unite seule est
// une cle.
function nb(n, unite) {
  return n + ' ' + t(unite);
}

// Une phrase entiere ou le nombre est au milieu. `%d` est remplace dans
// l'ordre par chaque valeur donnee.
function phrase(modele, ...valeurs) {
  // Les deux marqueurs sont remplaces DANS L'ORDRE, et non par type : une
  // traduction peut les inverser, mais elle garde leur nombre. Ne connaitre
  // que %d laissait un « %s » brut a l'ecran des qu'un chemin ou un nom
  // entrait dans une phrase.
  let sortie = t(modele);
  valeurs.forEach(v => { sortie = sortie.replace(/%[sd]/, v); });
  return sortie;
}

function t(texte, defaut) {
  return traduit(texte) || defaut || texte;
}

// Un attribut pose AVANT que le catalogue ne soit lu reste dans la langue du
// premier passage : l'observateur n'ecoute que `childList`, et sa valeur —
// souvent assemblee — n'est la cle de rien. On garde donc la ou les cles SUR
// l'element, et on recalcule les attributs a chaque changement de langue.
//
//   poserAttr(el, 'title', 'Une phrase.')
//   poserAttr(el, 'aria-label', '%s — %s', nom, aide)
//
// Les valeurs interpolees repassent elles aussi par `t()` au recalcul : ce
// sont des libelles ici, et `t()` rend son entree telle quelle quand aucune
// cle ne correspond, donc un chemin ou un nom de fichier n'y risque rien.
function poserAttr(el, attribut, cle, ...valeurs) {
  if (!el) return;
  const table = JSON.parse(el.dataset.i18nAttrs || '{}');
  table[attribut] = [cle, ...valeurs];
  el.dataset.i18nAttrs = JSON.stringify(table);
  appliquerAttrs(el);
}

function appliquerAttrs(el) {
  const table = JSON.parse(el.dataset.i18nAttrs || '{}');
  for (const [attribut, [cle, ...vals]] of Object.entries(table)) {
    el.setAttribute(attribut, vals.length
      ? phrase(cle, ...vals.map(v => t(String(v))))
      : t(cle));
  }
}

function retraduireAttributs(racine) {
  (racine || document).querySelectorAll('[data-i18n-attrs]')
    .forEach(appliquerAttrs);
}

function traduisible(noeud) {
  for (let n = noeud.parentElement; n; n = n.parentElement) {
    if (NON_TRADUIT.has(n.tagName)) return false;
    if (n.dataset && n.dataset.i18nSkip !== undefined) return false;
    if (n.classList && CLASSES_DONNEES.some(c => n.classList.contains(c))) return false;
  }
  return true;
}

let EN_TRADUCTION = false;

function traduireDOM(racine) {
  if (LANGUE === 'fr' || !Object.keys(I18N).length) return;
  EN_TRADUCTION = true;
  try {
    const marcheur = document.createTreeWalker(racine || document.body,
                                               NodeFilter.SHOW_TEXT);
    const aChanger = [];
    for (let n = marcheur.nextNode(); n; n = marcheur.nextNode()) {
      const brut = n.nodeValue;
      const net = brut.trim();
      if (!net || !traduisible(n)) continue;
      const en = traduit(net);
      if (!en) continue;
      // on conserve les espaces autour : ils portent la mise en page
      aChanger.push([n, brut.replace(net, en)]);
    }
    aChanger.forEach(([n, v]) => { n.nodeValue = v; });

    (racine || document.body).querySelectorAll('[placeholder],[title],[aria-label]')
      .forEach(el => {
        ['placeholder', 'title', 'aria-label'].forEach(a => {
          const en = v => v && traduit(v);
          const v = el.getAttribute(a);
          const w = en(v);
          if (w) el.setAttribute(a, w);
        });
      });
  } finally {
    EN_TRADUCTION = false;
  }
}

// Tout ce qui est ajoute plus tard (cartes, fiches, dialogues) passe aussi par
// la traduction : sans cela, seule la page initiale serait traduite.
const OBSERVATEUR = new MutationObserver(mutations => {
  if (EN_TRADUCTION || LANGUE === 'fr') return;
  for (const m of mutations) {
    if (m.type === 'childList' && m.addedNodes.length) {
      m.addedNodes.forEach(n => {
        if (n.nodeType === 1) { traduireDOM(n); return; }
        if (n.nodeType !== 3 || !traduisible(n)) return;
        const net = (n.nodeValue || '').trim();
        const en = net && traduit(net);
        if (!en) return;
        EN_TRADUCTION = true;
        n.nodeValue = n.nodeValue.replace(net, en);
        EN_TRADUCTION = false;
      });
    }
  }
});

async function chargerLangue(code) {
  LANGUE = code || 'en';
  // L'attribut `lang` de la page etait fige a « fr », quelle que soit la langue
  // choisie : les lecteurs d'ecran prononcaient l'anglais avec une phonetique
  // francaise, et la correction orthographique des champs de saisie se
  // trompait de dictionnaire.
  document.documentElement.setAttribute('lang', LANGUE);
  // Le francais est la langue SOURCE : ses cles sont deja les phrases
  // affichees, il n'y a rien a traduire.
  if (LANGUE === 'fr') { I18N = {}; return; }
  try {
    const r = await fetch('/locales/' + LANGUE + '.json');
    if (!r.ok) return;
    const d = await r.json();
    delete d._meta;
    I18N = d;
    _compilerGabarits();
    traduireDOM(document.body);
    retraduireAttributs();
    OBSERVATEUR.observe(document.body, {childList: true, subtree: true});
  } catch (e) { /* on garde les libelles francais */ }
}

// Position de lecture de chaque onglet, pour y revenir tel qu'on l'a laisse.
const DEFILEMENT = {};

// Plafond d'un fichier depose, annonce par /api/health. 0 = pas encore connu.
let TELEVERSEMENT_MAX = 0;

let JLOG = [];              // evenements recus du serveur
let JFILTRE = 'all';        // all | error | warn | info
// Ce qui etait affiche au rendu precedent, pour n'animer que les lignes
// reellement nouvelles. `sig` retient le filtre et la recherche : changer de
// filtre reconstruit la liste sans qu'aucune ligne ne soit « arrivee ».
let JVUES = {sig: '', n: 0};

function messageLisible(chemin, err) {
  const e = String(err).toLowerCase();
  // Ce n'est pas du texte affiche : c'est le message BRUT du serveur, qu'on
  // reconnait pour le remplacer par la phrase lisible juste en dessous. Le
  // traduire ferait echouer la reconnaissance.
  if (e.includes('route inconnue'))   // i18n:ok
    return "Cette fonction n'existe pas sur le serveur. Il tourne probablement " +
           "sur une version plus ancienne : arrête-le et relance python3 -m romule.";
  if (e.includes('reseau') || e.includes('failed to fetch'))
    return 'Le serveur ne répond plus. Vérifie qu\'il tourne toujours.';
  if (e.includes('tache est deja en cours'))  // i18n:ok - message compare, pas affiche
    return 'Une autre opération est en cours. Attends qu\'elle se termine.';
  if (chemin.includes('/api/eden') || chemin.includes('/api/nand'))
    return 'Action sur la console impossible. Vérifie qu\'elle est bien connectée.';
  if (chemin.includes('/api/emuready'))
    return 'EmuReady est injoignable. Réessaie plus tard, ta ludothèque n\'est pas affectée.';
  return 'Le serveur a refusé cette action.';
}

// Une modale qui disparait d'un coup se lit comme un bug plutot que comme une
// fermeture. On la laisse donc s'effacer, puis on vide son contenu — jamais
// avant, sinon la fenetre se vide sous les yeux pendant qu'elle recule.
const FERMETURE_MS = 160;

function fermerVoile(el) {
  if (!el || !el.classList.contains('open')) return;
  if (document.documentElement.dataset.mvt === 'aucun') {
    el.classList.remove('open', 'sansentree');
    el.innerHTML = '';
    return;
  }
  el.classList.add('ferme');
  setTimeout(() => {
    // Une fenetre a pu etre rouverte entre-temps — un bouton de dialogue qui
    // ferme puis pose la question suivante, par exemple. L'ouverture retire
    // `ferme` ; sans ce controle, on viderait la nouvelle fenetre.
    if (!el.classList.contains('ferme')) return;
    el.classList.remove('open', 'ferme', 'sansentree');
    el.innerHTML = '';
  }, FERMETURE_MS);
}

/* La jaquette cliquee GRANDIT jusqu'a devenir celle de la fiche, au lieu que
   la fenetre apparaisse d'un coup sans lien visible avec la carte. C'est le
   navigateur qui interpole : on se contente de donner le MEME nom de
   transition aux deux images, et de muter le DOM dans le rappel.

   Le nom doit etre unique dans la page pendant la transition — deux elements
   qui le portent en meme temps annulent l'effet — d'ou le nettoyage a la fin,
   y compris si la transition est interrompue. */
const NOM_TRANSITION = 'jaquette';

function ouvrirDepuisJaquette(cle, muter) {
  const source = document.querySelector(
    '.gcard[data-key="' + (window.CSS && CSS.escape ? CSS.escape(cle) : cle) + '"] .art img');
  if (!source || !document.startViewTransition ||
      document.documentElement.dataset.mvt === 'aucun') { muter(); return; }

  const cible = () => $('modal').querySelector('.cover');
  const nettoyer = () => {
    source.style.viewTransitionName = '';
    const c = cible();
    if (c) c.style.viewTransitionName = '';
    document.documentElement.classList.remove('vt-fiche');
  };
  source.style.viewTransitionName = NOM_TRANSITION;
  document.documentElement.classList.add('vt-fiche');
  // La fenetre est deja entree : c'est la jaquette qui l'a amenee. Sans cette
  // marque, retirer `vt-fiche` a la fin de la transition rendait son animation
  // d'entree — qui se declenchait alors, une fois le mouvement termine, en
  // faisant sauter la fiche de 28 px vers le bas avant de la faire remonter.
  $('modal').classList.add('sansentree');
  try {
    const t = document.startViewTransition(() => {
      // La carte CEDE le nom avant que la fiche ne le prenne. Deux elements
      // qui le portent en meme temps dans l'etat d'arrivee font echouer la
      // transition entiere (« aborted because of invalid state ») : la carte
      // reste dans la page derriere la fenetre, elle ne disparait pas.
      source.style.viewTransitionName = '';
      muter();
      const c = cible();
      if (c) c.style.viewTransitionName = NOM_TRANSITION;
    });
    t.finished.then(nettoyer, nettoyer);
  } catch (e) {
    nettoyer();
    muter();
  }
}

/* Le serveur ne connait que la tache EN COURS : son journal repart de zero a
   chaque nouvelle tache. Le recopier tel quel — `JLOG = j.log` — effacait donc
   tout ce qui precedait : les evenements du navigateur, et l'historique des
   taches precedentes. Supprimer un jeu sur la console suffisait a vider le
   journal, puisque la suppression ouvre une tache dont le journal est presque
   vide.

   On n'ajoute donc que ce qui est apparu depuis le dernier sondage. Une liste
   plus COURTE qu'au tour precedent signale une tache neuve : le serveur a
   remis son compteur a zero, on remet le notre. */
let JLOG_SERVEUR = 0;

function fusionnerJournal(recu) {
  if (recu.length < JLOG_SERVEUR) JLOG_SERVEUR = 0;   // nouvelle tache
  if (recu.length === JLOG_SERVEUR) return;
  JLOG = JLOG.concat(recu.slice(JLOG_SERVEUR)).slice(-800);
  JLOG_SERVEUR = recu.length;
}

function journal(line, niveau) {
  // evenement cote navigateur : meme presentation que ceux du serveur
  const d = new Date();
  JLOG.push({t: d.toTimeString().slice(0, 8), n: niveau || 'error', m: String(line)});
  JLOG = JLOG.slice(-800);
  renderJournal();
  const b = $('journalbtn');
  if (b && !$('jdrawer').classList.contains('open')) b.classList.add('news');
}

function renderJournal() {
  const q = ($('jsearch').value || '').toLowerCase();
  const nerr = JLOG.filter(e => e.n === 'error').length;
  const nwarn = JLOG.filter(e => e.n === 'warn').length;
  $('j-nerr').textContent = nerr;
  $('j-nwarn').textContent = nwarn;
  let vues = JLOG;
  if (JFILTRE === 'error') vues = vues.filter(e => e.n === 'error');
  else if (JFILTRE === 'warn') vues = vues.filter(e => e.n === 'warn' || e.n === 'error');
  else if (JFILTRE === 'info') vues = vues.filter(e => e.n === 'info' || e.n === 'ok');
  if (q) vues = vues.filter(e => e.m.toLowerCase().includes(q));
  const el = $('log');
  el.innerHTML = vues.length
    ? vues.map(e => '<div class="jline j-' + e.n + '">' +
        '<span class="jt" data-i18n-skip>' + e.t + '</span>' +
        // Niveau machine (error, warn, info, ok) et message tel que le serveur
        // l'a ecrit : deux donnees, pas des libelles.
        '<span class="jn" data-i18n-skip>' + e.n + '</span>' +
        '<span class="jm" data-i18n-skip>' + esc(e.m) + '</span></div>').join('')
    : '<div class="jempty">' + (q
        ? phrase('Aucun événement pour « %s ».', esc(q))
        : t('Aucun événement.')) + '</div>';

  // Comme un terminal : seules les lignes qui viennent d'arriver s'animent.
  // Tout le bloc est reconstruit a chaque rendu, donc sans ce reperage c'est
  // le journal ENTIER qui rejouerait son entree a chaque evenement — un
  // clignotement permanent des que quelque chose tourne.
  // Separateur impossible dans un nom de filtre. Ecrit en SEQUENCE
  // d'echappement : un octet nul brut dans le fichier le fait passer pour
  // binaire aux yeux de git et de grep, qui cessent alors d'en montrer le
  // contenu.
  const signature = JFILTRE + '\u0000' + q;
  const neuves = signature === JVUES.sig ? vues.length - JVUES.n : 0;
  if (neuves > 0 && neuves <= 40) {
    const lignes = el.querySelectorAll('.jline');
    for (let i = lignes.length - neuves; i < lignes.length; i++)
      lignes[i].classList.add('neuve');
  }
  JVUES = {sig: signature, n: vues.length};
  // Comme un terminal : on suit le flux tant qu'on est en bas, et on cesse de
  // sauter des qu'on remonte pour lire. Forcer le defilement rendait le journal
  // illisible pendant une tache.
  if (JSUIVI) el.scrollTop = el.scrollHeight;
  majBoutonSuivi();
}

// Vrai tant que l'utilisateur n'a pas remonte le journal.
let JSUIVI = true;

function majBoutonSuivi() {
  const b = $('jsuivi');
  if (!b) return;
  R.classe(b, 'on', JSUIVI);
  R.texte(b, JSUIVI ? 'Suivi auto' : 'Suivi arrêté');
  poserAttr(b, 'title', JSUIVI ? 'Le journal descend avec les nouvelles lignes.'
                               : 'Le journal reste où tu l\'as laissé.');
}

// ------------------------------------------------------------ dialogue
// Une erreur ne doit pas se contenter d'un message fugace : on explique ce
// qui a echoue, ce que ca implique, et on donne le detail technique a copier.
const D_ICONE = {error: '⚠️', warn: '⚠️', ok: '✅', info: 'ℹ️'};

function dialogue({titre, niveau = 'info', message = '', detail = '', options = [],
                   champs = [], actions = [], fermer = 'Fermer'}) {
  const el = $('dialog');
  const boutons = actions.map((a, i) =>
    '<button class="' + (a.principal ? 'go' : 'ghost') + '" data-di="' + i + '">' +
    esc(a.libelle) + '</button>').join('');
  // Options a cocher : un seul point de decision plutot qu'une suite de fenetres.
  const opts = options.length ? '<div class="dopts">' + options.map(o =>
    '<label class="dopt' + (o.desactive ? ' off' : '') + '">' +
    '<input type="checkbox" data-opt="' + o.id + '"' +
    (o.coche ? ' checked' : '') + (o.desactive ? ' disabled' : '') + '>' +
    '<span><b>' + esc(o.libelle) + '</b>' +
    (o.detail ? '<span class="dsub">' + esc(o.detail) + '</span>' : '') +
    '</span></label>').join('') + '</div>' : '';
  // Champs de saisie : meme fenetre, meme validation, plutot qu'une succession
  // de prompt() sans contexte.
  const saisies = champs.length ? '<div class="dchamps">' + champs.map(c =>
    '<label class="dchamp"><span>' + esc(c.libelle) + '</span>' +
    // `type` permet un champ mot de passe : le saisir en clair a l'ecran
    // n'est pas acceptable.
    '<input type="' + esc(c.type || 'text') + '" data-champ="' + esc(c.id) + '" ' +
    'autocomplete="' + esc(c.auto || 'off') + '" ' +
    'value="' + esc(c.valeur || '') + '" ' +
    'placeholder="' + esc(c.exemple || '') + '"></label>').join('') + '</div>' : '';
  el.innerHTML = '<div class="sheet dlg d-' + niveau + '" data-interieur>' +
    '<div class="dhead"><span class="dico">' + (D_ICONE[niveau] || 'ℹ️') + '</span>' +
    '<div><h3>' + esc(titre) + '</h3>' +
    (message ? '<p class="dmsg">' + esc(message) + '</p>' : '') + '</div></div>' + opts + saisies +
    (detail ? '<details class="ddet"><summary>Détail technique</summary>' +
      '<pre>' + esc(detail) + '</pre></details>' : '') +
    '<div class="acts">' + boutons +
    '<button class="ghost" data-di="close">' + esc(fermer) + '</button></div></div>';
  // Rouvrir annule une fermeture en cours : sans cela, le nettoyage
  // differe de `fermerVoile` viderait la fenetre qu'on vient d'ouvrir.
  el.classList.remove('ferme');
  el.classList.add('open');
  const premier = el.querySelector('[data-champ]');
  if (premier) premier.focus();
  const choix = () => {
    const c = {};
    el.querySelectorAll('[data-opt]').forEach(i => { c[i.dataset.opt] = i.checked; });
    el.querySelectorAll('[data-champ]').forEach(i => { c[i.dataset.champ] = i.value; });
    return c;
  };
  el.querySelectorAll('[data-di]').forEach(b => b.addEventListener('click', () => {
    const k = b.dataset.di, c = choix();
    app.closeDialog();
    if (k !== 'close' && actions[+k] && actions[+k].faire) actions[+k].faire(c);
  }));
}

// Trois notifications au maximum, et jamais deux fois le meme texte : une pile
// qui s'allonge recouvre l'interface au lieu de l'expliquer.
const TOAST_MAX = 3;

function toast(msg, kind) {
  const pile = $('toasts');
  const jumeau = [...pile.children].find(t => t.dataset.msg === msg);
  if (jumeau) {                             // deja affiche : on le compte
    const n = (+jumeau.dataset.n || 1) + 1;
    jumeau.dataset.n = n;
    jumeau.textContent = msg + '  ×' + n;
    return;
  }
  while (pile.children.length >= TOAST_MAX) pile.firstChild.remove();
  const el = document.createElement('div');
  el.className = 'toast' + (kind ? ' ' + kind : '');
  el.dataset.msg = msg;
  el.textContent = msg;
  pile.appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 300); }, 3600);
}

// Au demarrage, l'etat est deja lisible dans l'en-tete et dans les compteurs :
// empiler des notifications par-dessus n'apprend rien et masque l'interface.
// Elles vont donc au journal seul, qui est fait pour ca.
let DEMARRAGE = true;

function annonce(msg, kind) {
  journal(msg, kind === 'warn' ? 'warn' : 'ok');
  if (!DEMARRAGE) toast(msg, kind);
}
// `say` decrit ce qui se passe A L'INSTANT (« Envoi de X… »). Le NOM de la
// tache, lui, vient du travail en cours : les melanger laissait un vieux
// libelle en titre longtemps apres.
function say(t) { R.texte($('tachedetail'), t || ''); }

// --------------------------------------------------------------- tache en cours
// Le temps restant est estime ICI, a partir de l'avancement observe : le serveur
// ne le calcule que pour les transferts, alors qu'une conversion ou une lecture
// de conteneurs en a tout autant besoin. On lisse sur une fenetre glissante pour
// qu'un a-coup ne fasse pas bondir l'estimation.
let TACHE = {debut: 0, points: []};

function estimeReste(done, total) {
  const t = Date.now();
  if (!total || done <= 0) { TACHE = {debut: t, points: []}; return null; }
  const p = TACHE.points;
  if (!p.length || p[p.length - 1].done !== done) p.push({t, done});
  while (p.length > 12) p.shift();
  if (p.length < 3) return null;
  const a = p[0], b = p[p.length - 1];
  const ecoule = (b.t - a.t) / 1000, faits = b.done - a.done;
  if (ecoule <= 0 || faits <= 0) return null;
  return Math.round((total - done) / (faits / ecoule));
}

function texteReste(s) {
  if (s == null) return '';
  if (s < 45) return 'moins d\'une minute';
  const m = Math.round(s / 60);
  if (m < 60) return '~' + m + ' min';
  const h = Math.floor(m / 60);
  return '~' + h + ' h' + (m % 60 ? String(m % 60).padStart(2, '0') : '');
}

// --------------------------------------------------- temoin d'activite (bouton +)
// Deux choses peuvent tourner : une tache du serveur, ou un envoi de fichiers
// depuis ce navigateur. Le bouton n'en montre qu'une a la fois, avec une regle
// simple : l'envoi passe devant, parce que c'est l'utilisateur qui vient de le
// declencher et qu'il attend un retour immediat.
let ACT_SERVEUR = null;      // {titre, pct, reste, detail}
let ACT_ENVOI = null;

function activite() { return ACT_ENVOI || ACT_SERVEUR; }

// L'anneau suit le contour du bouton, qui change de taille selon ce qu'il
// affiche. `pathLength=100` normalise le perimetre : la jauge se pilote en
// pourcentage sans jamais recalculer une circonference.
function majAnneau() {
  const btn = $('fab'), svg = $('fabring');
  if (!btn || !svg) return;
  const l = btn.offsetWidth, h = btn.offsetHeight;
  if (!l || !h) return;
  const e = 3;                                   // epaisseur du trait
  svg.setAttribute('viewBox', '0 0 ' + l + ' ' + h);
  [$('fabpiste'), $('fabjauge')].forEach(r => {
    if (!r) return;
    r.setAttribute('x', e / 2); r.setAttribute('y', e / 2);
    r.setAttribute('width', Math.max(0, l - e));
    r.setAttribute('height', Math.max(0, h - e));
    r.setAttribute('rx', Math.max(0, (h - e) / 2));
  });
}

// Temps restant en trois caracteres ou presque : le bouton fait 54 px, il n'y
// a pas la place pour « moins d'une minute ». La phrase complete reste dans le
// panneau et dans l'infobulle.
function resteCourt(s) {
  if (s == null) return '';
  if (s < 60) return Math.max(1, Math.round(s)) + ' s';
  const m = Math.round(s / 60);
  if (m < 60) return m + ' min';
  const h = Math.floor(m / 60);
  return h + ' h' + String(m % 60).padStart(2, '0');
}

// Ce que le bouton affiche en son centre, par ordre de precision : le temps
// restant s'il est estimable, sinon l'avancement, sinon rien — l'anneau qui
// tourne dit deja « ca travaille ».
// Marqueur : trois points qui s'allument tour a tour. Afficher « 0 % » serait
// plus simple, mais ce serait faux — au demarrage d'un import la console n'a
// pas encore dit combien de fichiers elle attend, donc il n'y a pas de
// pourcentage a montrer. Les points disent la seule chose vraie : ca commence.
const FAB_ATTENTE = '…';
const FAB_POINTS =
  '<i class="fabpoints"><span></span><span></span><span></span></i>';

function coeurFab(a) {
  if (!a) return '';
  if (a.pause) return '⏸';                 // pause
  const t = resteCourt(a.secs);
  if (t) return t;
  if (a.pct != null) return a.pct + ' %';
  return FAB_ATTENTE;
}

let FAB_COEUR = '';
let FAB_TRAVAILLAIT = false;

function majFab() {
  const btn = $('fab');
  if (!btn) return;
  const a = activite();
  R.classe(btn, 'travaille', !!a);
  R.texte($('fabtitre'), a ? a.titre : '');
  R.texte($('fabreste'), a ? (a.reste || '') : '');

  // Sans total connu, la jauge tourne au lieu de mentir sur l'avancement.
  const indetermine = !a || a.pct == null;
  R.classe(btn, 'cherche', !!a && indetermine);
  const jauge = $('fabjauge');
  if (jauge) {
    jauge.style.strokeDasharray = indetermine
      ? '18 82'
      : Math.max(0, Math.min(100, a.pct)) + ' 100';
  }

  // Le chiffre du centre. On ne le reecrit que s'il a change : sinon
  // l'animation de bascule rejouerait a chaque sondage du serveur, deux fois
  // par seconde, et le bouton clignoterait sans arret.
  const coeur = coeurFab(a);
  const eta = $('fabeta');
  if (eta && coeur !== FAB_COEUR) {
    if (coeur === FAB_ATTENTE) eta.innerHTML = FAB_POINTS;
    else eta.textContent = coeur;
    if (coeur) {
      eta.classList.remove('change');
      void eta.offsetWidth;                     // redemarre l'animation
      eta.classList.add('change');
    }
    FAB_COEUR = coeur;
  }
  R.classe(btn, 'pause', !!(a && a.pause));

  // Fin de tache : l'anneau se remplit et s'eteint en vert. Sans ce signal,
  // le bouton redevient simplement un « + » et rien ne dit que ce qu'on
  // attendait est termine.
  if (FAB_TRAVAILLAIT && !a) {
    btn.classList.remove('fini');
    void btn.offsetWidth;
    btn.classList.add('fini');
    setTimeout(() => btn.classList.remove('fini'), 1200);
  }
  FAB_TRAVAILLAIT = !!a;

  btn.title = a ? a.titre + (a.reste ? ' — ' + a.reste : '') : 'Ajouter des jeux';
  btn.setAttribute('aria-label', btn.title);
  requestAnimationFrame(majAnneau);
}

window.addEventListener('resize', majAnneau);

// Vrai tant qu'une recherche de fiches tourne REELLEMENT.
//
// Le bandeau « Recherche des infos… » s'affichait sur toute carte sans fiche,
// qu'une recherche soit en cours ou non. Pour un jeu qu'aucune base ne connait
// — un titre trop recent, un homebrew, un nom de fichier trop abime — il ne
// disparaissait donc JAMAIS : la carte annoncait un travail en cours qui
// n'aurait jamais lieu. C'est un mensonge de l'interface, pas un detail
// d'affichage, et il etait sous les yeux de tout le monde sur la capture du
// README.
//
// Une carte sans fiche ne dit maintenant plus rien : son absence de resume se
// voit deja, et « Fiches manquantes » est la pour aller les chercher.
let RECHERCHE_FICHES = false;

// Les libelles que le serveur donne aux taches qui remplissent les fiches.
// Ce sont des noms de FONCTION Python, pas du texte affiche : ils ne se
// traduisent pas.
const TACHES_FICHES = ['sync_meta', 'meta_sync'];   // i18n:ok

function renderTache(j) {
  const el = $('tache');
  const cherche = !!j.running && TACHES_FICHES.includes(j.label);
  if (cherche !== RECHERCHE_FICHES) {
    RECHERCHE_FICHES = cherche;
    // La fin de la recherche doit effacer les bandeaux restants : sans ce
    // rendu, ils tiendraient jusqu'au prochain passage sur la grille.
    if (typeof renderLib === 'function') renderLib();
  }
  R.classe(el, 'on', !!j.running);
  R.classe($('journalbtn'), 'occupe', !!j.running);
  if (!j.running) {
    $('bar').style.width = '0';
    R.texte($('tacheavance'), '');
    R.texte($('tachereste'), '');
    TACHE = {debut: 0, points: []};
    ACT_SERVEUR = null;
    R.texte($('tachelbl'), 'Tâche en cours');
    R.texte($('tachedetail'), '');
    majFab();
    majPanneauTaches(j);
    return;
  }
  const pct = j.total ? Math.min(100, Math.round(100 * j.done / j.total)) : null;
  $('bar').style.width = (pct == null ? 0 : pct) + '%';
  R.classe(el, 'indetermine', pct == null);   // total inconnu : barre en va-et-vient

  // avancement : le compte d'abord, le detail du serveur (debit) ensuite
  const bouts = [];
  if (j.total) bouts.push(j.done + ' / ' + j.total + (pct != null ? '  ·  ' + pct + ' %' : ''));
  if (j.detail) bouts.push(j.detail);
  R.texte($('tacheavance'), bouts.join('  ·  ') || 'en cours…');
  const secs = j.paused ? null : estimeReste(j.done, j.total);
  const reste = j.paused ? 'en pause' : texteReste(secs);
  R.texte($('tachereste'), reste);
  R.texte($('pausebtn'), j.paused ? 'Reprendre' : 'Pause');

  R.texte($('tachelbl'), nomTache(j));
  ACT_SERVEUR = {
    titre: nomTache(j),
    pct: pct,
    secs: secs,
    pause: !!j.paused,
    reste: [j.total ? j.done + '/' + j.total : '', reste].filter(Boolean).join(' · '),
  };
  majFab();
  majPanneauTaches(j);
}

// Le panneau du bouton « + » : ce qui tourne, ou l'on en est, et combien de
// temps il reste. Le journal, lui, raconte ce qui S'EST passe — les deux ne se
// recouvrent pas.
function majPanneauTaches(j) {
  const bloc = $('tache'), vide = $('tachevide');
  if (!bloc || !vide) return;
  const enCours = !!(j && j.running);
  const envoi = !!ACT_ENVOI;
  bloc.hidden = !enCours && !envoi;
  vide.hidden = enCours || envoi;
  R.classe(bloc, 'on', enCours || envoi);
  if (envoi && !enCours) {
    R.texte($('tachelbl'), ACT_ENVOI.titre);
    R.texte($('tacheavance'), ACT_ENVOI.reste || '');
    R.texte($('tachereste'), ACT_ENVOI.pct != null ? ACT_ENVOI.pct + ' %' : '');
    R.texte($('tachedetail'), '');
    $('bar').style.width = (ACT_ENVOI.pct || 0) + '%';
    ['pausebtn', 'cancelbtn'].forEach(i => { if ($(i)) $(i).hidden = true; });
    return;
  }
  ['pausebtn', 'cancelbtn'].forEach(i => { if ($(i)) $(i).hidden = !enCours; });
  R.texte($('tachedetail'), (j && j.detail) ? j.detail : '');
}

// `label` porte le nom de la fonction Python qui tourne : il ne parle qu'au
// code. On le traduit en une phrase courte, reconnaissable d'un coup d'oeil.
const NOMS_TACHE = {
  analyser_console:    'Analyse de la console',
  apply_eden_config:   'Réglages Eden',
  apply_eden_profile:  'Profil Eden',
  backup_saves:        'Sauvegardes',
  convert_files:       'Conversion',
  deploy_games:        'Envoi vers la console',
  emuready_apply:      'Réglages EmuReady',
  emuready_sync:       'Lecture EmuReady',
  import_files:        'Rangement du dépôt',
  import_from_device:  'Import depuis la console',
  import_system_files: 'Import des ROMs',
  install_nand:        'Installation NAND',
  organize_device:     'Rangement de la console',
  push_files:          'Envoi vers la console',
  push_system:         'Envoi des ROMs',
  remove_from_device:  'Suppression sur la console',
  reorganize_local:    'Rangement local',
  restore_eden_config: 'Restauration Eden',
  scan_import:         'Lecture du dépôt',
  sync_meta:           'Fiches de jeu',
  verify_library:      'Vérification',
};

function nomTache(j) {
  return NOMS_TACHE[j.label] || 'Tâche en cours';
}

// ---------------------------------------------------------------- regroupement
function groupGames() {
  // Un fichier sans title ID exploitable (pack .xci, nom mal forme) etait
  // regroupe par DOSSIER. Deux consequences, toutes deux vues en vrai :
  // deux jeux differents du meme dossier atterrissaient sur une seule carte,
  // et un jeu apparaissait deux fois des lors qu'il avait par ailleurs une
  // mise a jour correctement nommee. On rapproche donc par titre reduit.
  const parTitre = {};
  DATA.files.forEach(f => { if (f.tid) parTitre[titreNormalise(f.name)] = tidBase(f.tid); });

  const games = {};
  DATA.files.forEach(f => {
    const t = titreNormalise(f.name);
    const key = f.tid ? tidBase(f.tid) : (parTitre[t] || 'nom:' + t);
    const g = games[key] || (games[key] = {key, tid: key.startsWith('nom:') ? null : key,
      baseName: null, files: [], dirs: new Set()});
    g.files.push(f); g.dirs.add(f.dir);
    if (f.type === 'BASE') g.baseName = f.name;
  });
  return Object.values(games).map(g => {
    const base = g.files.find(f => f.type === 'BASE');
    // Nom de repli quand un jeu n'en a aucun : il est AFFICHE, donc traduit.
  // La recherche de jaquette par nom n'aurait de toute facon rien trouve.
  g.name = g.baseName || (g.files[0] && g.files[0].name) || t('Inconnu');
    // Un pack .xci qui fusionne jeu, MAJ et DLC ne porte pas de title ID : il est
    // classe INCONNU alors qu'il CONTIENT le jeu. Le compter comme base evite
    // d'annoncer « le jeu de base manque » sur un jeu parfaitement jouable.
    g.hasBase = !!base || g.files.some(f =>
      ['nsp', 'xci'].includes(f.ext) && !['UPDATE', 'DLC'].includes(f.type));
    g.needsConvert = g.files.some(f => f.needs_convert);
    g.cleanable = g.files.some(f => (f.flags || []).some(x => ['orphan', 'old', 'done'].includes(x[0])));
    const uf = base && (base.flags || []).find(x => ['outdated', 'nopatch'].includes(x[0]));
    g.updateAvail = !!uf; g.updateText = uf ? uf[1] : '';
    g.missingDlc = base && base.missing_dlc ? base.missing_dlc.length : 0;
    g.updCount = g.files.filter(f => f.type === 'UPDATE').length;
    g.dlcCount = g.files.filter(f => f.type === 'DLC').length;
    g.size = g.files.reduce((s, f) => s + f.size, 0);
    return g;
  }).sort((a, b) => a.name.localeCompare(b.name));
}

function coverImg(g, cls, attrs) {
  // Sans title ID, on demande quand meme la jaquette : le serveur sait chercher
  // par nom. Renvoyer '' condamnait les packs XCI a une vignette vide.
  if (!g.tid && !g.name) return '';
  // le jeton `v` change des que le cache serveur bouge : sans lui le
  // navigateur garderait ses anciennes images pendant des heures.
  const v = (DATA && DATA.covers_v) || 0;
  return '<img class="' + (cls || '') + '" src="/cover/' + (g.tid || '') + '?v=' + v +
    '&name=' + encodeURIComponent(g.name || '') + '" loading="lazy" ' +
    'data-cover' +
    (attrs ? ' ' + attrs : '') + '>';
}

/* ---------------------------------------------------------------- couleurs
   La couleur dominante d'une pochette sert deux fois : elle remplit
   l'emplacement AVANT que l'image n'arrive (la grille ne clignote plus au
   defilement), et elle teinte l'en-tete de la fiche du jeu.

   Elle est calculee une seule fois par jeu, dans le navigateur, puis rangee
   localement : la recalculer a chaque affichage ferait travailler le
   processeur pour un resultat toujours identique. */
const COULEURS = (() => {
  try { return JSON.parse(localStorage.getItem('couleurs') || '{}') || {}; }
  catch (e) { return {}; }
})();
let COULEURS_A_ECRIRE = 0;

function cleCouleur(g) {
  return String((g && (g.tid || g.key)) || '').toLowerCase();
}

function rangerCouleurs() {
  clearTimeout(COULEURS_A_ECRIRE);
  // Une ecriture par salve : 48 jaquettes qui arrivent ensemble
  // declencheraient 48 serialisations du meme objet.
  COULEURS_A_ECRIRE = setTimeout(() => {
    try { localStorage.setItem('couleurs', JSON.stringify(COULEURS)); }
    catch (e) { /* quota plein : la couleur se recalculera, sans dommage */ }
  }, 800);
}

const ECH = 18;            // la pochette est reduite a 18x18 avant analyse

function couleurDominante(img) {
  let d;
  try {
    const c = document.createElement('canvas');
    c.width = c.height = ECH;
    const ctx = c.getContext('2d', {willReadFrequently: true});
    ctx.drawImage(img, 0, 0, ECH, ECH);
    d = ctx.getImageData(0, 0, ECH, ECH).data;
  } catch (e) {
    return '';               // canvas indisponible : on s'en passe
  }
  const seaux = new Map();
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], v = d[i + 1], b = d[i + 2];
    if (d[i + 3] < 200) continue;
    const haut = Math.max(r, v, b), bas = Math.min(r, v, b);
    const clarte = (haut + bas) / 2;
    // Le presque-noir et le presque-blanc sont des bords et des aplats de
    // fond : ils dominent en surface sans jamais caracteriser une pochette.
    if (clarte < 34 || clarte > 226) continue;
    const cle = (r >> 4) + ',' + (v >> 4) + ',' + (b >> 4);
    const s = seaux.get(cle) || {n: 0, r: 0, v: 0, b: 0, poids: 0};
    s.n++; s.r += r; s.v += v; s.b += b;
    s.poids += 1 + (haut - bas) / 64;      // une couleur franche pese plus
    seaux.set(cle, s);
  }
  let chef = null;
  for (const s of seaux.values()) if (!chef || s.poids > chef.poids) chef = s;
  if (!chef) return '';
  return 'rgb(' + Math.round(chef.r / chef.n) + ' ' +
                  Math.round(chef.v / chef.n) + ' ' +
                  Math.round(chef.b / chef.n) + ')';
}

// Attributs a poser sur une carte ou une fiche : de quoi retrouver la couleur
// apres coup, et la couleur elle-meme si elle est deja connue — c'est ce qui
// evite le clignotement, puisqu'elle s'applique AVANT le chargement de
// l'image.
function attrsTeinte(g) {
  const cle = cleCouleur(g);
  const c = COULEURS[cle];
  return ' data-couleur="' + esc(cle) + '"' +
         (c ? ' style="--jaq:' + esc(c) + '"' : '');
}

// ---------------------------------------------------------------- rendu
function render() {
  const s = DATA.stats;
  META = DATA.meta || {};
  GAMES = groupGames();
  renderLib();
  // Ce qui manque officiellement (patches, DLC) n'est plus une liste a part :
  // l'information vit sur la carte du jeu concerne, la ou elle est utile.
  renderImport(DATA.pending || []);
  renderTree();
  $('organizewrap').style.display = DATA.device === 'device' ? '' : 'none';
  fillSettings();
}

// ------------------------------------------------- systemes (autres consoles)
function renderSysSelect() {
  const el = $('sysel');
  // On compte des JEUX, pas des fichiers : pour la Switch, le total incluait
  // les mises a jour et les DLC, ce qui gonflait le chiffre sans rien dire
  // d'utile (148 fichiers pour 22 jeux).
  // Le compte local seul mentait : la plupart des plateformes n'existent que sur
  // la console. On retient donc le plus grand des deux (local, console detectee).
  const compte = s => {
    if (s.count === null) return GAMES.length;          // Switch : jeux regroupes
    const d = PLATEFORMES.find(x => x.key === s.key);
    return Math.max(s.count || 0, d ? d.count : 0);
  };
  const signature = SYSTEMS.map(s => s.key + ':' + compte(s)).join();
  if (!SYSTEMS.length || el.dataset.sig === signature) { el.value = SYS; return; }
  el.dataset.sig = signature;
  const total = SYSTEMS.reduce((n, s) => n + compte(s), 0);
  el.innerHTML = '<option value="all">Toutes les plateformes' +
      (total ? ' (' + total + ')' : '') + '</option>' +
    SYSTEMS.map(s => {
      const n = compte(s);
      return '<option value="' + s.key + '">' + esc(s.name) + (n ? ' (' + n + ')' : '') + '</option>';
    }).join('');
  el.value = SYS;
}
function isSwitch() { return SYS === 'switch'; }
function vueTotale() { return SYS === 'all'; }
// Libelle court d'une plateforme : « GBA », pas « Game Boy Advance ».
function libelleSysteme(key) {
  const s = SYSTEMS.find(x => x.key === key);
  return (s && s.folder) || key;
}


function renderLib() {
  renderSysSelect();
  // Les filtres d'etat propres a la Switch (MAJ, DLC, conversion) n'ont pas de
  // sens ailleurs : on les masque, le reste de la vue est commun.
  const suisse = isSwitch();
  ['activer', 'convert', 'probleme', 'importer'].forEach(k => {
    const chip = document.querySelector('#filters [data-f="' + k + '"]');
    if (chip) chip.dataset.horsSwitch = suisse ? '' : '1';
  });
  $('bulkconv').style.display = suisse ? '' : 'none';

  const tous = jeuxUnifies();
  // Les gabarits de resume se reperent en comparant les jeux entre eux : la
  // liste complete doit donc etre connue avant de dessiner la moindre carte.
  majModelesResume(tous);
  renderToolbar(tous);

  // compteurs : un filtre qui ne peut rien dire est masque, pas affiche a zero
  const n = {all: tous.length, envoyer: 0, activer: 0, importer: 0, convert: 0, probleme: 0};
  tous.forEach(({e}) => { if (n[e.etat] !== undefined) n[e.etat]++; });
  Object.keys(n).forEach(k => {
    const chip = document.querySelector('#filters [data-f="' + k + '"]');
    if (!chip) return;
    const c = $('c-' + k);
    if (c) chiffreAnime(c, n[k]);
    chip.style.display = (ETATS_CONSOLE.includes(k) && !consoleLue()) ? 'none' : '';
  });
  if (ETATS_CONSOLE.includes(FILTER) && !consoleLue()) { FILTER = 'all'; majChips(); }

  const bulk = $('bulkconv');
  if (n.convert) { bulk.style.display = ''; bulk.textContent = phrase('Convertir les %s restants', n.convert); }
  else bulk.style.display = 'none';

  const q = ($('filter').value || '').toLowerCase();
  // Le regroupement vient APRES le filtrage : un groupe ne doit compter que
  // les versions effectivement visibles, sinon il annoncerait « 5 versions »
  // dans une liste qui n'en montre qu'une.
  const list = regrouper(jeuxFiltres(tous));

  const lib = $('lib');
  if (!DATA.files.length && !tous.length) {
    lib.innerHTML = '<div class="empty">' +
      esc(t('Aucun fichier Switch dans ce dossier.')) + '<br>' +
      phrase('Dépose des jeux avec le bouton %s, en bas à droite.', '+') +
      '</div>';
    $('pager').innerHTML = ''; renderActionBar(); return;
  }
  if (!list.length) {
    lib.innerHTML = '<div class="empty">' + (FILTER === 'all'
      ? phrase('Aucun jeu ne correspond à « %s ».', esc($('filter').value))
      : phrase('Rien dans « %s » — tout est en ordre de ce côté.',
              t(ETATS[FILTER][1]))) + '</div>';
    $('pager').innerHTML = ''; renderActionBar(); return;
  }

  // pagination : la taille de page suit la taille des cartes
  const parPage = PARPAGE || Math.max(1, list.length);   // 0 = tout sur une page
  const pages = Math.ceil(list.length / parPage);
  if (PAGE >= pages) PAGE = 0;
  const vus = list.slice(PAGE * parPage, (PAGE + 1) * parPage);

  lib.style.setProperty('--carte', TAILLES[TAILLE][1] + 'px');
  VUS_PAGE = vus.map(({g}) => g.key);

  // La grille est reconciliee, plus reecrite : une carte inchangee n'est pas
  // touchee, donc son animation ne rejoue pas et sa coche n'a pas besoin d'etre
  // resynchronisee a la main. C'est ce que reactive.js apporte.
  let grille = lib.firstElementChild;
  if (!grille || !grille.classList.contains('games')) {
    lib.innerHTML = '';
    grille = document.createElement('div');
    lib.appendChild(grille);
  }
  grille.className = 'games taille-' + TAILLE  // i18n:ok - classe CSS;

  R.liste(grille, vus, {
    // L'etat deplie fait partie de l'identite de la carte : sans lui, la
    // reconciliation reutiliserait la meme vignette et le chevron resterait
    // tourne dans le mauvais sens.
    cle: ({g}) => g.key,
    creer: (x) => R.depuisHtml(carteHtml(x)),
    majEl: (el, x) => majCarte(el, x),
  });

  renderAlphabet(list);
  renderPager(list.length, pages, parPage);
  renderActionBar();
}

// ------------------------------------------------------- index alphabetique
// Une lettre par groupe existant, comme dans une mediatheque. Il n'a de sens
// que si la liste EST triee par nom : sur un tri par taille, sauter a « M »
// ne voudrait rien dire, donc l'index disparait.
function lettreDe(g) {
  const t = (nomJeu(g) || '').trim();
  // On deplie les accents : « Ecran » et « Écran » se rangent au meme endroit.
  const c = t.normalize('NFD').replace(/[\u0300-\u036f]/g, '')[0] || '';
  if (/[0-9]/.test(c)) return '#';
  return /[a-z]/i.test(c) ? c.toUpperCase() : '#';
}

let ALPHA_POS = new Map();      // lettre -> rang dans la liste filtree
// Lettre demandee par un clic. Dans une grille, la carte visee tombe souvent au
// milieu d'une ligne : aucun calcul de position ne peut alors deviner « la »
// lettre courante. Apres un clic, c'est l'intention de l'utilisateur qui fait
// foi ; le premier defilement rend la main au calcul.
let ALPHA_VISEE = '';
// Instant du dernier saut. Le defilement fluide emet une dizaine d'evenements :
// un drapeau a usage unique n'en absorbait qu'un, et l'index reprenait la main
// avant meme d'etre arrive.
let ALPHA_JUSQUA = 0;

function renderAlphabet(list) {
  const nav = $('alphabet');
  if (!nav) return;
  const actif = TRI === 'nom' && list.length >= 12;
  nav.hidden = !actif;
  if (!actif) { ALPHA_POS = new Map(); return; }
  ALPHA_POS = new Map();
  list.forEach((x, i) => {
    const l = lettreDe(x.g);
    if (!ALPHA_POS.has(l)) ALPHA_POS.set(l, i);
  });
  const toutes = ['#'].concat('ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split(''));
  R.liste(nav, toutes, {
    cle: l => l,
    creer: l => {
      const b = document.createElement('button');
      b.className = 'alpha';
      b.textContent = l;
      b.onclick = () => app.allerLettre(l);
      return b;
    },
    majEl: (el, l) => R.texte(el, l),
  });
  majAlphabet();
}

// La lettre qu'on est en train de lire est mise en avant : sans cela l'index
// dit ou l'on PEUT aller, jamais ou l'on EST.
function majAlphabet() {
  const nav = $('alphabet');
  if (!nav || nav.hidden) return;
  const cartes = [...document.querySelectorAll('#lib .gcard')];
  let courante = '';
  // La lettre courante est celle de la PREMIERE carte encore visible, pas de la
  // derniere passee : dans une grille, plusieurs cartes partagent une ligne, et
  // prendre la derniere designait la lettre suivante des qu'un groupe tenait
  // sur une seule ligne.
  const tete = document.querySelector('header');
  const seuil = (tete ? tete.getBoundingClientRect().bottom : 60) + 24;
  for (const c of cartes) {
    if (c.getBoundingClientRect().bottom > seuil) {
      courante = c.dataset.lettre || '';
      break;
    }
  }
  if (ALPHA_VISEE) courante = ALPHA_VISEE;
  if (!courante && cartes.length) {
    courante = cartes[cartes.length - 1].dataset.lettre || '';
  }
  [...nav.children].forEach(b => {
    const dispo = ALPHA_POS.has(b.textContent);
    R.classe(b, 'vide', !dispo);
    b.disabled = !dispo;
    R.classe(b, 'on', dispo && b.textContent === courante);
  });
}

// UNE ligne sous le titre, et la plus utile des six possibles. Empiler taille,
// contenu, note EmuReady et remarque donnait quatre lignes concurrentes dont
// aucune ne ressortait ; la taille et le contenu vivent desormais sur la
// jaquette, ou ils se lisent sans lire.
// La carte parle du JEU, pas de l'outil : elle porte le resume, rien d'autre.
// L'etat (« MAJ à activer », « Problème ») est deja dit par l'etiquette de la
// jaquette ; le detail — quelle mise a jour, pourquoi un fichier est incomplet —
// appartient a la fiche, ou il y a la place de l'expliquer.
function carteLigne(x) {
  const resume = resumeUtile(x.g);
  return resume ? ['resume', extrait(resume, 96)] : ['', ''];
}

// Mots trop courants pour peser dans la comparaison : les garder ferait passer
// n'importe quelle phrase pour « proche du titre ».
const VIDES = new Set(('le la les un une des du de d l a au aux et ou en dans sur '  // i18n:ok - mots vides, pas de l'interface
  + 'pour par avec sans version edition the a an of and or in on for with your '
  + 'this that new').split(' '));

function motsUtiles(t) {
  return (String(t || '').toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .match(/[a-z0-9]{2,}/g) || []).filter(m => !VIDES.has(m));
}

// Un resume qui ne fait que repeter le titre occupe trois lignes pour ne rien
// dire : « Revivez l'aventure Pokémon Blattgrüne Edition ! » sur la carte de
// Pokémon Blattgrüne Edition. On l'ecarte quand l'essentiel de ses mots vient
// deja du titre — mais seulement s'il est court : une vraie description qui
// commence par le nom du jeu doit rester.
const RESUME_COURT = 9;          // mots utiles au-dela desquels on ne juge plus
const RESUME_REDONDANT = 0.5;    // part des mots deja presents dans le titre

// Deuxieme filet, celui-la fonde sur la ludotheque elle-meme. La comparaison
// au titre ne rattrape pas « Revivez l'aventure Pokémon Edición Rojo Fuego ! »
// sur une carte intitulee « Pokémon FireRed Version » : aucun mot commun, et
// pourtant la phrase ne dit rien. En revanche elle commence comme sept autres
// de la bibliotheque — c'est un GABARIT, et c'est mesurable sans connaitre la
// langue ni la source.
const MODELE_MOTS = 3;           // longueur du debut compare
const MODELE_MINI = 3;           // nombre de jeux au-dela duquel c'est un gabarit
const MODELE_LONG = 12;          // une vraie description echappe a la regle
let RESUMES_MODELES = new Set();

function majModelesResume(tous) {
  const compte = new Map();
  for (const x of tous) {
    const mots = motsUtiles(resumeJeu(x.g));
    if (mots.length < 2) continue;
    const debut = mots.slice(0, MODELE_MOTS).join(' ');
    compte.set(debut, (compte.get(debut) || 0) + 1);
  }
  RESUMES_MODELES = new Set(
    [...compte].filter(([, n]) => n >= MODELE_MINI).map(([k]) => k));
}

function resumeUtile(g) {
  const brut = resumeJeu(g);
  if (!brut) return '';
  const mots = motsUtiles(brut);
  if (!mots.length) return '';
  if (mots.length <= MODELE_LONG &&
      RESUMES_MODELES.has(mots.slice(0, MODELE_MOTS).join(' '))) return '';
  if (mots.length > RESUME_COURT) return brut;
  const titre = new Set(motsUtiles(nomJeu(g)));
  const repris = mots.filter(m => titre.has(m)).length;
  return repris / mots.length >= RESUME_REDONDANT ? '' : brut;
}

// Etiquette du bas : a gauche OU est le jeu, a droite ce qu'il reste a faire.
// Deux temoins allumes/eteints se lisent plus vite qu'une phrase, et gardent
// le vocabulaire de l'appareil plutot que celui du formulaire.
// Version courte de l'etat, pour le bandeau d'une carte. « Pas sur la
// console » ne tenait pas a cote des mots MAC et CONSOLE : le bandeau se
// terminait par « PAS SUR LA … » sur chaque jaquette, donc ne disait rien.
// Le texte entier reste accessible en infobulle et dans la fiche.
// « Prêt » et « À envoyer » decrivaient l'etat du FICHIER ; ce que
// l'utilisateur veut savoir, c'est s'il peut jouer, et sinon ce qu'il reste a
// faire. Chaque mot est donc soit « jouable », soit un verbe d'action — et la
// pastille console, juste au-dessus, dit deja ou se trouve le jeu.
const ETAT_COURT = {
  probleme: 'Problème', importer: 'À rapatrier', envoyer: 'À transférer',
  activer: 'À activer', convert: 'À convertir', pret: 'Jouable',
  local: 'Sur le serveur',
};

function carteEtiquette({e}) {
  const p = e.presence || {mac: true, console: 'inconnu'};
  const tMac = p.mac ? 'Présent sur le serveur' : 'Absent du serveur';
  const tCons = t(TITRE_PRESENCE[p.console] || '');
  // Pastilles muettes : la couleur porte l'information, l'infobulle la nomme.
  // Les mots « MAC » et « CONSOLE » mangeaient les deux tiers de la largeur
  // pour repeter un ordre qui ne change jamais (le serveur d'abord).
  // La console a quitte ce bandeau pour la pastille du haut, ou elle se lit
  // d'un coup d'oeil sur toute la grille. La repeter ici dirait deux fois la
  // meme chose a 200 px d'ecart.
  return '<span class="temoins">' +
      '<i class="tem ' + (p.mac ? 'p-oui' : 'p-non') + '" title="' + esc(tMac) +
        '" aria-label="' + esc(tMac) + '"></i>' +
    '</span>' +
    // `e.txt` est un libelle d'etat pris dans `ETATS` : il doit passer par le
    // catalogue comme le texte visible juste a cote.
    '<span class="etatmot ' + ETATS[e.etat][0] + '" title="' + esc(t(e.txt)) + '">' +
      esc(ETAT_COURT[e.etat] || e.txt) + '</span>';
}
const TITRE_PRESENCE = {
  oui: 'Présent sur la console', partiel: 'En partie sur la console',
  non: 'Absent de la console', inconnu: 'Console non consultée',
};

// Pastilles posees sur la jaquette : ce qui se chiffre (taille, MAJ, DLC).
/* ============================================================================
   SUPPORTS PHYSIQUES
   ----------------------------------------------------------------------------
   Vingt-trois plateformes, mais seulement six FORMES de support : une
   cartouche de salon, une cartouche de poche, une carte, un disque, une carte
   Switch, un circuit d'arcade. Dessiner vingt-trois silhouettes distinctes
   serait un mensonge — a 46 px, une cartouche SNES et une cartouche Mega Drive
   sont le meme objet.

   Elles servent la ou il n'y a rien a montrer : un jeu sans jaquette affichait
   une grosse lettre dans un rectangle gris. Elles disent aussi, dans la fiche,
   sur quoi le jeu tournait vraiment.
   ========================================================================== */
const MEDIA_PLATEFORME = {
  switch: 'switch',
  gb: 'poche', gba: 'poche',
  nes: 'cartouche', snes: 'cartouche', megadrive: 'cartouche', n64: 'cartouche',
  nds: 'carte', '3ds': 'carte', psvita: 'carte',
  psx: 'disque', ps2: 'disque', ps3: 'disque', psp: 'disque',
  gamecube: 'disque', wii: 'disque', wiiu: 'disque',
  dreamcast: 'disque', saturn: 'disque',
  xbox: 'disque', xbox360: 'disque', pc: 'disque',
  arcade: 'borne',
};

// Dessins en `currentColor`, sur une grille de 48 : ils heritent donc de la
// couleur du texte partout ou on les pose, sans variante a maintenir.
const SILHOUETTES = {
  // Toutes suivent la meme regle : UN chemin plein, et les details sont des
  // TROUS (`fill-rule="evenodd"`). Poser un detail par-dessus le corps en
  // baissant son opacite ne l'eclaircit pas — il se peint dans la meme
  // couleur, donc il disparait. C'est la decoupe qui le fait exister.

  // Carte Switch : coin biseaute et ergot de detrompage.
  switch:
    '<path fill-rule="evenodd" d="M15 5h13l5 5v29a4 4 0 0 1-4 4H15' +
      'a4 4 0 0 1-4-4V9a4 4 0 0 1 4-4zm3 30h8v4h-8z"/>',
  // Cartouche de poche : haute, coin inferieur biseaute, fenetre d'etiquette.
  poche:
    '<path fill-rule="evenodd" d="M12 4h24v32l-7 7H12V4zm4 5h16v14H16V9z' +
      'm1 21h10v3H17v-3z"/>',
  // Cartouche de salon : large, etiquette et peigne du connecteur.
  cartouche:
    '<path fill-rule="evenodd" d="M12 4h24a2 2 0 0 1 2 2v38H10V6a2 2 0 0 1 2-2z' +
      'm3 5h18v13H15V9zm-1 27h20v3H14v-3z"/>',
  // Carte memoire : presque carree, coin coupe.
  carte:
    '<path fill-rule="evenodd" d="M11 11h19l6 6v20a3 3 0 0 1-3 3H11' +
      'a3 3 0 0 1-3-3V14a3 3 0 0 1 3-3zm2 20h10v3H13v-3z"/>',
  // Disque optique : le trou est decoupe, pas peint.
  disque:
    '<path fill-rule="evenodd" d="M24 6a18 18 0 1 0 .01 0zm0 12.5' +
      'a5.5 5.5 0 1 0 .01 0z"/>' +
    '<path d="M24 10.5a13.5 13.5 0 0 1 11.7 6.8" fill="none"' +
      ' stroke="currentColor" stroke-width="2" stroke-linecap="round"' +
      ' opacity=".45"/>',
  // Borne d'arcade : ecran et panneau de commande decoupes dans le meuble.
  borne:
    '<path fill-rule="evenodd" d="M13 4h22a3 3 0 0 1 3 3v34a3 3 0 0 1-3 3H13' +
      'a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3zm2 5h18v13H15V9zm0 18h18v5H15v-5z"/>',
};

function plateformeDe(g) {
  if (!g) return '';
  return g.tid ? 'switch' : (g.systeme || SYS || '');
}

function mediaDe(g) {
  return MEDIA_PLATEFORME[plateformeDe(g)] || '';
}

function nomPlateforme(g) {
  const cle = plateformeDe(g);
  const s = (SYSTEMS || []).find(x => x.key === cle);
  return (s && s.name) || g.sysNom || cle || '';
}

function silhouetteHtml(g, cls) {
  const media = mediaDe(g);
  if (!media) return '';
  return '<svg class="' + (cls || 'support') + '" viewBox="0 0 48 48"' +
    ' aria-hidden="true" focusable="false" fill="currentColor">' +
    SILHOUETTES[media] + '</svg>';
}

// Silhouette de console : un boitier et son ecran. A 11 px, un dessin se
// reconnait la ou un mot ne se lit plus — et il ne demande aucune traduction.
const GLYPHE_CONSOLE =
  '<svg viewBox="0 0 14 14" width="11" height="11" aria-hidden="true">' +
    '<rect x="1" y="3" width="12" height="8" rx="2.2" fill="none"' +
      ' stroke="currentColor" stroke-width="1.4"/>' +
    '<rect class="ecran" x="4.4" y="5.2" width="5.2" height="3.6" rx=".8"' +
      ' fill="currentColor"/>' +
  '</svg>';

function carteOverlay({g, e}) {
  const bouts = [];
  // « Est-il sur la console ? » est LA question qu'on se pose en parcourant la
  // grille. Elle vit donc sur la jaquette, pas dans le bandeau du bas ou elle
  // se noyait entre deux autres informations. Trois etats seulement, et rien
  // du tout tant que la console n'a pas repondu : afficher un temoin eteint
  // pour « je ne sais pas » serait un mensonge.
  const p = (e && e.presence) || {};
  if (p.console && p.console !== 'inconnu') {
    bouts.push('<span class="ov ovconsole p-' + p.console + '" title="' +
      esc(t(TITRE_PRESENCE[p.console] || '')) + '" aria-label="' +
      esc(t(TITRE_PRESENCE[p.console] || '')) + '">' + GLYPHE_CONSOLE + '</span>');
  }
  // Le nom de la plateforme, indispensable des que plusieurs se melangent, et
  // utile ailleurs pour lever toute ambiguite sur ce qu'on regarde.
  if (g.sysNom) bouts.push('<span class="ov ovsys">' + esc(g.sysNom) + '</span>');
  // La langue vaut pour TOUS les jeux, pas seulement les versions groupees :
  // savoir qu'une cartouche est en japonais avant de la lancer evite un
  // aller-retour. Et pour trois versions au meme titre, c'est la seule chose
  // qui les distingue.
  const lg = etiquetteLangues(g);
  if (lg) {
    bouts.push('<span class="ov ovlangue" title="' + esc(lg.long) +
      '" aria-label="' + esc(lg.long) + '">' + esc(lg.court) + '</span>');
  }
  if (g.updCount) bouts.push('<span class="ov">'
    + (g.updCount > 1 ? g.updCount + '&nbsp;' + t('MAJ') : t('MAJ')) + '</span>');
  if (g.dlcCount) bouts.push('<span class="ov">' + g.dlcCount + '&nbsp;DLC</span>');
  return '<span class="ovtaille">' + esc(fmt(g.size)) + '</span>' +
         (bouts.length ? '<span class="ovdroite">' + bouts.join('') + '</span>' : '');
}

// Un jeu qui vient d'arriver n'a encore ni titre officiel ni jaquette. Plutot
// qu'une carte vide dont on ne sait pas si elle finira par se remplir, on
// annonce que la recherche est en cours.
function sansFiche(g) {
  if (!g) return false;
  if (g.tid) return !(META[String(g.tid).toLowerCase()] || {}).nom;
  const f = (g.files && g.files[0]) || g;
  return !(g.titre || f.titre);
}
// Une ligne de la fenetre des versions : de quoi choisir sans ouvrir chaque
// fiche — la langue, la taille, l'etat, et ou se trouve le fichier.
// La derniere fenetre ouverte passe devant, et elle seule. On ne fait pas
// grimper un compteur : les couches au-dessus (assistant, loupe, voile de
// depot) doivent rester au-dessus, quoi qu'il arrive.
function auPremierPlan(el) {
  document.querySelectorAll('.modal').forEach(m => m.classList.remove('devant'));
  el.classList.add('devant');
}

function ligneVersion(x) {
  const {g, e} = x;
  const lg = etiquetteLangues(g);
  const etat = e && ETATS[e.etat] ? ETATS[e.etat] : null;
  return '<div class="vrow">' +
    '<span class="vcover">' + (coverImg(g) || '') + '</span>' +
    '<span class="vnom">' + esc(nomJeu(g)) +
      '<span class="vfichier">' + esc(extrait(g.name || '', 46)) + '</span></span>' +
    (lg ? '<span class="vlangue" title="' + esc(lg.long) + '">' +
          esc(lg.court) + '</span>' : '') +
    '<span class="vtaille">' + esc(fmt(g.size)) + '</span>' +
    (etat ? '<span class="vetat ' + etat[0] + '">' +
            esc(ETAT_COURT[e.etat] || etat[1]) + '</span>' : '') +
    '<button class="ghost" data-act="openGame" data-arg="' + esc(g.key) + '">' +
      'Détails</button>' +
  '</div>';
}

function carteHtml(x) {
  const {g, e} = x;
  const coche = dsel2.has(g.key);
  const [cls, txt] = carteLigne(x);
  const attente = RECHERCHE_FICHES && sansFiche(g);
  return '<div class="gcard' + (coche ? ' sel' : '') + (attente ? ' sansfiche' : '') +
    (g.groupeN ? ' groupe' : '') +
    // Le support sert de liseré en vue « toutes les plateformes » : c'est la
    // seule ou il apprend quelque chose. Dans une vue Switch, trente-quatre
    // liserés identiques ne seraient que du bruit.
    '" data-media="' + esc(vueTotale() ? mediaDe(g) : '') +
    '" data-lettre="' + esc(lettreDe(g)) +
    '" data-key="' + esc(g.key) + '"' + attrsTeinte(g) +
    ' tabindex="0" role="button" aria-label="' + esc(nomJeu(g)) + '"' +
    ' data-act="cardClick" data-arg="' + esc(g.key) + '">' +
    '<div class="art">' + coverImg(g) +
    // Sans jaquette, la silhouette du support dit au moins de quoi il s'agit.
    // Une initiale geante ne disait rien : deux jeux sur trois commencent par
    // la meme lettre dans une bibliotheque triee.
    '<span class="ph">' + (silhouetteHtml(g) ||
       esc((nomJeu(g)[0] || '?').toUpperCase())) + '</span>' +
    '<span class="ovslot">' + carteOverlay(x) + '</span>' +
    '<span class="badge">' + carteEtiquette(x) + '</span>' +
    '<span class="pcheck' + (coche ? ' on' : '') + '">' + (coche ? '✓' : '') + '</span>' +
    (attente ? '<span class="enattente">Recherche des infos…</span>' : '') + '</div>' +
    '<div class="cap"><div class="gname">' + esc(nomJeu(g)) + '</div>' +
    '<div class="ligne ' + cls + '">' + esc(txt) + '</div>' +
    // La cle du groupe vient d'un nom de fichier : elle passe par un attribut
    // `data-`, jamais dans la chaine JavaScript du `onclick` — une apostrophe
    // dans un titre y casserait le gestionnaire.
    (g.groupeN ? '<button class="pgrp" data-grp="' + esc(g.groupeCle) +
       '" data-act="voirVersions" data-arg="' + esc(g.groupeCle) + '">' +
       g.groupeN + ' versions…</button>' : '') +
    '<button class="pinfo" data-act="openGame" data-arg="' + esc(g.key) + '">Détails</button></div></div>';
}

// Met a jour une carte deja presente. Chaque ecriture est conditionnelle : rien
// ne bouge si rien n'a change, donc aucune transition ne se relance pour rien.
function majCarte(el, x) {
  const {g, e} = x;
  const coche = dsel2.has(g.key);
  R.classe(el, 'sel', coche);
  // Des que la fiche arrive, le voile d'attente disparait sans redessiner
  // la carte — donc sans faire clignoter la jaquette.
  const attente = RECHERCHE_FICHES && sansFiche(g);
  R.classe(el, 'sansfiche', attente);
  const art = el.querySelector('.art');
  const voile = el.querySelector('.enattente');
  if (attente && !voile && art) {
    const sp = document.createElement('span');
    sp.className = 'enattente';
    sp.textContent = 'Recherche des infos…';
    art.appendChild(sp);
  } else if (!attente && voile) {
    voile.remove();
  }
  R.html(el.querySelector('.badge'), carteEtiquette(x));
  const c = el.querySelector('.pcheck');
  if (c) { R.classe(c, 'on', coche); R.texte(c, coche ? '✓' : ''); }
  R.html(el.querySelector('.ovslot'), carteOverlay(x));
  const [cls, txt] = carteLigne(x);
  const l = el.querySelector('.ligne');
  if (l) { l.className = 'ligne ' + cls; R.texte(l, txt); }
}

function majChips() {
  document.querySelectorAll('#filters .chip').forEach(c =>
    c.classList.toggle('on', c.dataset.f === FILTER));
}

function renderToolbar(tous) {
  // Nomme `selTri` et non `t` : `t()` est la fonction de traduction, et une
  // variable locale de ce nom la masque dans toute la fonction. L'appel
  // devient alors « t is not a function » — au premier rendu seulement, donc
  // un ecran blanc au demarrage et rien du tout ensuite.
  const selTri = $('tri');
  if (selTri && !selTri.dataset.rempli) {
    selTri.dataset.rempli = '1';
    selTri.innerHTML = Object.entries(TRIS).map(([k, v]) =>
      '<option value="' + k + '">' + esc(v[0]) + '</option>').join('');
  }
  if (selTri) selTri.value = TRI;
  const pp = $('parpage');
  if (pp && !pp.dataset.rempli) {
    pp.dataset.rempli = '1';
    pp.innerHTML = PAR_PAGE.map(n =>
      '<option value="' + n + '">' +
      (n ? phrase('%s par page', n) : t('Tout afficher')) + '</option>').join('');
  }
  if (pp) pp.value = String(PARPAGE);
  const s = $('sens');
  if (s) { s.textContent = SENS === 1 ? '↑' : '↓';
           s.title = SENS === 1 ? 'Ordre croissant' : 'Ordre inverse'; }
  document.querySelectorAll('#tailles .szbtn').forEach(b =>
    b.classList.toggle('on', b.dataset.sz === TAILLE));

  // Chaque filtre avance affiche combien de jeux il retiendrait : on sait
  // avant de cliquer si ca vaut la peine.
  const pop = $('favlist');
  if (pop) pop.innerHTML = Object.entries(FAVANCES).map(([k, [lib, fn]]) =>
    '<label class="favrow"><input type="checkbox" ' + (FAV.has(k) ? 'checked ' : '') +
    'data-act-change="toggleFav" data-arg="' + esc(k) + '"><span class="grow">' + esc(lib) + '</span>' +
    '<span class="mono">' + tous.filter(fn).length + '</span></label>').join('');
  const b = $('favbtn');
  if (b) { b.classList.toggle('on', FAV.size > 0);
           b.textContent = FAV.size ? 'Filtres (' + FAV.size + ')' : 'Plus de filtres'; }
}

function renderPager(total, pages, parPage) {
  const el = $('pager');
  if (pages <= 1) {
    el.innerHTML = '<span class="mono">' + nb(total, 'jeu(x)') + '</span>';
    return;
  }
  const de = PAGE * parPage + 1, a = Math.min(total, (PAGE + 1) * parPage);
  el.innerHTML =
    '<button class="ghost" ' + (PAGE ? '' : 'disabled') + ' data-act="page" data-val="-1">‹ Précédent</button>' +
    '<span class="mono">' + de + '–' + a + ' sur ' + total + '</span>' +
    '<button class="ghost" ' + (PAGE < pages - 1 ? '' : 'disabled') + ' data-act="page" data-val="1">Suivant ›</button>';
}

// La barre d'actions n'apparait qu'une fois des jeux coches, et ne propose que
// ce qui est realisable sur CETTE selection : un bouton grise sans explication
// laisse l'utilisateur deviner pourquoi.
function renderActionBar() {
  const bar = $('actionbar');
  if (!isSwitch() || !dsel2.size) { bar.classList.remove('on'); return; }
  bar.classList.add('on');
  const c = deployCibles();
  const surConsole = c.supprConsole.length;
  const boutons = [];
  if (c.envoyer.length || c.activer.length)
    // Meme action que le bouton de la fiche : meme phrase. « Mettre sur la
    // console » et « Envoyer vers la console » designaient le meme geste, ce
    // qui oblige a verifier a chaque fois qu'il s'agit bien de la meme chose.
    boutons.push(['go', 'appliquer', 'Envoyer vers la console',
                  c.envoyer.length ? fmt(c.poids)
                                   : nb(c.activer.length, 'MAJ/DLC')]);
  if (c.importer.length)
    boutons.push(['go', 'appliquer', 'Copier vers le serveur', nb(c.importer.length, 'fichier(s)')]);
  if (surConsole)
    boutons.push(['warn', 'supprimerConsole', 'Retirer de la console', nb(surConsole, 'fichier(s)')]);
  if (c.local.length)
    boutons.push(['', 'corbeilleSelection', 'Mettre à la corbeille', nb(c.local.length, 'fichier(s)')]);

  // Le compteur est ecrit UNE fois puis mis a jour en place : le reconstruire
  // a chaque clic remplacerait le <b>, et le chiffre sauterait au lieu de
  // defiler.
  const som = $('deploysum');
  if (!som.firstElementChild) som.innerHTML = t('<b>0</b> jeu(x) sélectionné(s)');
  chiffreAnime(som.firstElementChild, dsel2.size);

  // « Tout cocher » disparait quand tout est deja coche : un bouton qui ne
  // peut rien faire est un bouton qui ment.
  const visibles = jeuxFiltres(jeuxUnifies()).length;
  const tout = $('touscocher');
  if (tout) {
    tout.style.display = dsel2.size >= visibles ? 'none' : '';
    tout.textContent = 'Tout cocher';
  }
  $('actions').innerHTML = boutons.map(([cls, fn, lib, det]) =>
    // `fn` vient de la liste `boutons` ecrite dix lignes plus haut, donc de
    // noms litteraux. Ce qui garantit qu'il en restera ainsi n'est pas cette
    // proximite, c'est `ACTES` : un nom absent de la liste blanche ne fait
    // rien, et `test_gestes.py` echoue si l'un d'eux y manque.
    '<button class="' + cls + '" data-act="' + esc(fn) + '">' + esc(lib) +
    '<span class="mono"> · ' + esc(det) + '</span></button>').join('') ||
    '<span class="mono">Rien à faire sur cette sélection.</span>';
}

// ---------------------------------------------------------------- detail jeu
// Section « Mises à jour » de la fiche. C'est ici, et nulle part ailleurs, que
// l'on parle de versions : la carte doit rester consacrée au jeu lui-même.
// Chaque affirmation est sourcée — l'utilisateur doit pouvoir aller vérifier.
const SOURCE_MAJ = 'https://github.com/blawar/titledb';

function majSection(g, e) {
  if (g.console) return '';
  const maj = g.files.filter(f => f.type === 'UPDATE');
  const vers = maj.map(f => f.version).filter(v => v != null);
  const mienne = vers.length ? Math.max.apply(null, vers) : null;
  const base = g.files.find(f => f.type === 'BASE') || {};
  const drapeaux = (base.flags || []).filter(x => ['nopatch', 'outdated', 'nodlc'].includes(x[0]));
  const casses = (e.casses || []).filter(f => f.type !== 'BASE');

  // rien a dire : ni mise a jour connue, ni DLC manquant, ni fichier abime
  if (!maj.length && !drapeaux.length && !casses.length && !g.dlcCount
      && !(e.aActiver || []).length) return '';

  const l = [];
  // Un seul mot, sans accent : ni le controle statique ni le test navigateur
  // ne pouvaient le voir — leurs deux heuristiques demandent un accent OU deux
  // mots-outils. Le plancher a ete abaisse depuis, mais ces deux-la avaient
  // deja traverse, et « aucune » s'affichait dans une interface anglaise.
  l.push('<div class="majrow"><span>Version installée</span><b>' +
    (mienne != null ? 'v' + mienne
                    : t(maj.length ? 'inconnue' : 'aucune')) + '</b></div>');
  if (g.dlcCount)
    l.push('<div class="majrow"><span>DLC présents</span><b>' + g.dlcCount + '</b></div>');

  // Ce qui est copie sur la console mais pas encore actif dans Eden. L'action
  // vit ici, a cote du fait qui la justifie, plutot que dans une barre lointaine.
  if ((e.aActiver || []).length) {
    l.push('<div class="majrow act"><span>À activer dans Eden</span>' +
      '<b class="p-partiel">' + nb(e.aActiver.length, 'élément(s)') + '</b>' +
      '<button class="go" ' + (CONN.kind ? '' : 'disabled title="Console non connectée"') +
      ' data-act="activerJeu" data-arg="' + esc(g.key) + '">Activer</button></div>');
  }
  drapeaux.forEach(([code, txt]) => l.push(
    '<div class="majrow"><span>' +
    (code === 'nodlc' ? 'DLC manquants' : 'D\'après titledb') +
    '</span><b class="' + (code === 'nodlc' ? 'p-partiel' : 'p-partiel') + '">' +
    esc(txt) + '</b></div>'));
  casses.forEach(f => l.push(
    '<div class="majrow"><span>Fichier incomplet</span><b class="p-non">' +
    esc(pretty(f.name)) + '</b></div>'));

  return '<div class="ssect">Mises à jour</div>' +
    '<div class="majbloc">' + l.join('') + '</div>' +
    '<p class="erdit petit">Ces informations viennent de <a href="' + SOURCE_MAJ +
    '" target="_blank" rel="noopener">titledb</a>, la base communautaire des versions ' +
    'Switch. L\'outil n\'y télécharge rien : il compare seulement ce que tu possèdes ' +
    'à ce qui existe.</p>';
}

function openGameHtml(g) {
  const lines = [];
  const e = etatDe(g);
  // L'etat ne parle QUE de disponibilite : le detail des mises a jour a sa
  // propre section plus bas, avec le bouton qui va avec.
  const libelles = {
    pret:     ['ok',   'Prêt à jouer sur la console'],
    activer:  ['upd',  'Sur la console — voir « Mises à jour » ci-dessous'],
    envoyer:  ['conv', phrase('%d fichier(s) à envoyer sur la console', e.aEnvoyer.length)],
    importer: ['conv', 'Sur la console seulement — à importer vers le serveur'],
    convert:  ['conv', 'À convertir avant envoi'],
    probleme: ['orph', e.casses.length ? 'Fichier incomplet — à remplacer'
                                       : 'Le jeu de base est absent'],
    local:    ['dlc',  'Sur le serveur — branche la console pour en savoir plus'],
  };
  if (libelles[e.etat]) lines.push(libelles[e.etat]);
  if (e.raison) lines.push(['orph', e.raison]);
  if (e.note) lines.push(['upd', e.note]);
  if (!lines.length) lines.push(['ok', 'À jour, rien à signaler']);

  const files = g.files.slice().sort((a, b) =>
    ({BASE: 0, UPDATE: 1, DLC: 2, INCONNU: 3}[a.type] - {BASE: 0, UPDATE: 1, DLC: 2, INCONNU: 3}[b.type]));
  const frows = files.map(f =>
    '<div class="frow"><span class="tag t-' + f.type + '">' + f.type + '</span>' +
    '<span class="grow"><div class="fname">' + esc(pretty(f.name)) +
    (f.version != null ? ' <span class="mono">v' + f.version + '</span>' : '') + '</div></span>' +
    (f.converted ? '<span class="flag f-done">converti</span>' : '') +
    '<span class="size">' + fmt(f.size) + '</span>' +
    '<button class="iconbtn" data-act="trashFile" data-arg="' + esc(f.path) + '">corbeille</button></div>').join('');

  // Les actions proposees dependent de l'etat : proposer « Envoyer vers la
  // console » a un jeu qui n'existe QUE sur la console n'a aucun sens.
  const acts = [];
  if (g.needsConvert)
    acts.push('<button class="go" data-act="convertGame" data-arg="' + esc(g.key) + '">Convertir ce jeu</button>');
  if (g.console)
    acts.push('<button class="go" data-act="importerJeu" data-arg="' + esc(g.key) + '">Copier vers le serveur</button>');
  else if (e.aEnvoyer.length)
    acts.push('<button class="go" data-act="sendGame" data-arg="' + esc(g.key) + '">Envoyer vers la console</button>');
  acts.push('<button class="ghost" data-act="closeGame">Fermer</button>');

  return '<div class="sheet"' + attrsTeinte(g) + ' data-interieur>' +
    // La jaquette ne dependait que du title ID Switch : tous les jeux des
    // autres plateformes ouvraient donc une fiche sans image, alors meme que
    // leur carte en affichait une. `coverImg` sait chercher par nom — c'est
    // deja ce qu'il fait dans la grille.
    '<div class="top">' + (coverImg(g, 'cover',
        'role="button" tabindex="0" title="' +
        esc(t('Voir la jaquette en grand')) + '"' +
        ' data-act="loupeJaquette"') ||
      '<div class="cover"></div>') +
    '<div><h3>' + esc(nomJeu(g)) + '</h3>' +
    // Le support, en toutes lettres et en image : c'est l'information qui
    // manquait le plus dans une ludotheque qui melange vingt-trois consoles.
    '<div class="supportligne">' + silhouetteHtml(g, 'support gros') +
      '<span>' + esc(nomPlateforme(g)) + '</span>' +
      // Ici, la place ne manque pas : on nomme les langues au lieu de les
      // reduire a « MULTI » comme sur la jaquette.
      (function () {
        const l = etiquetteLangues(g);
        return l ? '<span class="sep">·</span><span class="langues">' +
                   esc(l.long) + '</span>' : '';
      })() +
    '</div>' +
    '<div class="sub2" id="gm-info">' + (g.tid ? 'chargement des infos…' : '') + '</div>' +
    // Un etat par ligne, avec une pastille de couleur : empiler des pastilles
    // encadrees rendait la fiche illisible des qu'il y avait deux informations.
    '<div class="status">' + lines.map(l =>
      '<div class="stline s-' + l[0] + '"><i></i><span>' + esc(l[1]) + '</span></div>').join('') +
    '</div></div></div>' +
    '<div class="body">' +
    '<p class="gdesc" id="gm-desc"></p>' +
    // Le texte de Wikipedia est sous CC BY-SA : cette licence demande de citer
    // la source. La ligne reste vide quand le resume vient d'ailleurs.
    '<p class="gcredit" id="gm-credit">' + creditResume(g) + '</p>' +
    '<div class="chiffres">' +
      '<div><b>' + fmt(g.size) + '</b><span>total</span></div>' +
      '<div class="pres"><b class="' + (e.presence.mac ? 'p-oui' : 'p-non') + '">' +
        (e.presence.mac ? 'oui' : 'non') + '</b><span>sur le serveur</span></div>' +
      '<div class="pres"><b class="p-' + e.presence.console + '">' +
        {oui: 'oui', partiel: 'en partie', non: 'non', inconnu: '?'}[e.presence.console] +
        '</b><span>sur la console</span></div>' +
      '<div><b>' + (g.updCount || 0) + '</b><span>mise(s) à jour</span></div>' +
      '<div><b>' + (g.dlcCount || 0) + '</b><span>DLC</span></div>' +
    '</div>' +
    majSection(g, e) +
    erSection(g) +
    '<div class="ssect">Fichiers <span class="mono">' + g.files.length + '</span></div>' +
    frows + '</div>' +
    '<div class="acts">' + acts.join('') + '</div></div>';
}
function fmtDate(d) {
  const s = String(d);
  return /^\d{8}$/.test(s) ? s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6, 8) : s;
}

// ---------------------------------------------------------------- depot
// Depot : l'apercu regroupe par plateforme, pour qu'on voie d'un coup ce qui
// va ou. Une ROM .gba etait auparavant annoncee dans « GAMES », le dossier
// Switch, alors que le rangement la mettait au bon endroit — un apercu qui ment
// est pire que pas d'apercu.
// Le bouton de classement n'a de sens que s'il reste quelque chose a classer :
// affiche en permanence, il donnait a croire qu'une action etait en attente.
function majBoutonClasser(n) {
  const b = $('btnclasser');
  if (!b) return;
  b.hidden = !n;
  R.texte(b, phrase('À classer (%s)', n || 0));
}

function renderImport(items) {
  const d = $('drop'), btn = $('importbtn'), info = $('importinfo');
  majBoutonClasser(items.filter(i => i.type === 'AMBIGU').length);
  if (!items.length) {
    d.innerHTML = '<div class="dropvide">' +
      '<div class="dropicone">↓</div>' +
      '<b>Glisse tes jeux ici</b>' +
      '<span>Switch, GBA, PS2, SNES… l\'outil reconnaît la plateforme et range ' +
      'chaque fichier au bon endroit.</span>' +
      '<span class="mono">Archives .zip / .7z / .rar acceptées : elles sont décompressées.</span>' +
      '</div>';
    if (btn) { btn.disabled = true; btn.textContent = 'Importer'; }
    if (info) info.textContent = '';
    return;
  }
  if (btn) {
    btn.disabled = false;
    btn.textContent = phrase('Importer %s élément(s)', items.length);
  }
  if (info) info.textContent = fmt(items.reduce((s, i) => s + (i.size || 0), 0)) + ' en attente';

  const groupes = new Map();
  items.forEach(i => {
    const cle = i.systeme_nom || t('Plateforme inconnue');
    if (!groupes.has(cle)) groupes.set(cle, []);
    groupes.get(cle).push(i);
  });
  d.innerHTML = [...groupes.entries()].map(([nom, lot]) =>
    '<div class="dgroupe"><div class="dgtete">' + esc(nom) +
      '<span class="mono">' + nb(lot.length, 'fichier(s)') + ' · ' +
      fmt(lot.reduce((s, i) => s + (i.size || 0), 0)) + '</span></div>' +
    lot.map(i =>
      '<div class="drow' + (i.type === 'AMBIGU' ? ' aclasser' : '') + '"><span class="tag t-' +
      (i.type === 'ARCHIVE' ? 'INCONNU' : i.type === 'AMBIGU' ? 'AMBIGU' : i.type === 'ROM' ? 'BASE' : i.type) + '">' +
      esc(i.type === 'AMBIGU' ? 'À CLASSER' : i.type) + '</span>' +
      '<span class="grow">' + esc(nomLisible(pretty(i.name))) + '</span>' +
      '<span class="size">' + fmt(i.size) + '</span>' +
      '<span class="ddest">&rarr; ' + esc(i.dest) + '</span></div>').join('') +
    '</div>').join('');
}

// ---------------------------------------------------------------- console
// L'etat de la console vit dans un seul bloc (renderConn).
//
// Cette fonction declenchait une detection quand elle voyait un appareil sans
// connexion connue. Un rendu qui lance un appel reseau produit exactement ce
// qu'on a observe : `render()` appelait `detect()`, qui rendait, qui rappelait
// detect... d'ou les notifications en double au demarrage. Un rendu decrit un
// etat, il ne provoque rien.
// Il n'y a plus de pastille distincte a mettre a jour : `renderConn` dessine
// l'etat complet de la console, pastille comprise. Cette fonction ne servait
// plus qu'a relancer une detection depuis un rendu, ce qui doublait les
// appels et les notifications au demarrage.

// « il y a 3 min », « depuis 2 h » — une duree se lit mieux qu'un horodatage.
function duree(s) {
  s = Math.max(0, Math.round(s || 0));
  if (s < 60) return 'à l\'instant';
  const m = Math.round(s / 60);
  if (m < 60) return 'depuis ' + m + ' min';
  const h = Math.floor(m / 60);
  return 'depuis ' + h + ' h' + (m % 60 ? String(m % 60).padStart(2, '0') : '');
}

// Batterie de la console : une pastille dessinee, pas un pourcentage perdu
// dans une phrase. Le remplissage suit le niveau reel, la couleur previent
// avant qu'un transfert de 12 Go ne s'arrete en chemin.
// ------------------------------------------------------------- entretien
function _lignes(paires) {
  return '<div class="majbloc">' + paires.map(([k, v]) =>
    '<div class="majrow"><span>' + esc(k) + '</span><b>' + v + '</b></div>').join('')
    + '</div>';
}

function renduDoublons(r) {
  const rien = !r.identiques.length && !r.regions.length && !r.multi_plateformes.length;
  if (rien) return '<p class="lead">Aucun doublon repéré.</p>';
  let h = _lignes([
    ['Fichiers identiques', r.identiques.length],
    ['Mêmes titres, régions différentes', r.regions.length],
    ['Mêmes jeux sur plusieurs plateformes', r.multi_plateformes.length],
    ['Place récupérable', fmt(r.recuperable)],
  ]);
  if (r.identiques.length) {
    h += '<h4 class="entretien-t">Fichiers rigoureusement identiques</h4>'
      + '<p class="mono">Même empreinte : en supprimer un ne perd rien.</p>'
      + '<ul class="entretien-l">' + r.identiques.map(x =>
        '<li>' + fmt(x.taille) + ' × ' + x.fichiers.length + '<br>'
        + x.fichiers.map(f => '<code>' + esc(f) + '</code>').join('<br>') + '</li>').join('')
      + '</ul>';
  }
  if (r.regions.length) {
    h += '<h4 class="entretien-t">Mêmes titres, régions ou révisions</h4>'
      + '<p class="mono">Souvent involontaire — mais parfois voulu. À toi de voir.</p>'
      + '<ul class="entretien-l">' + r.regions.map(x =>
        '<li><b>' + esc(x.titre) + '</b> — ' + x.entrees.length + ' exemplaires, '
        + fmt(x.octets) + ' en trop<br>'
        + x.entrees.map(e => '<code>' + esc(e.nom) + '</code>').join('<br>')
        + '</li>').join('') + '</ul>';
  }
  if (r.multi_plateformes.length) {
    h += '<h4 class="entretien-t">Mêmes jeux sur plusieurs plateformes</h4>'
      + '<ul class="entretien-l">' + r.multi_plateformes.map(x =>
        '<li><b>' + esc(x.titre) + '</b> — ' + x.plateformes.map(esc).join(', ')
        + '</li>').join('') + '</ul>';
  }
  return h;
}

function renduIntegrite(r) {
  const s = r.resume || {};
  const couvert = s.fichiers ? Math.round(100 * s.couverts / s.fichiers) : 0;
  return _lignes([
    ['Fichiers de la bibliothèque', s.fichiers || 0],
    ['Avec une empreinte connue', (s.couverts || 0) + ' (' + couvert + ' %)'],
    ['Jamais vérifiés', s.sans_empreinte || 0],
    ['Vérification la plus ancienne', esc(s.plus_ancienne || '—')],
  ])
  + '<p class="mono">Une empreinte différente à taille ET date identiques signale '
  + 'une corruption silencieuse du disque.</p>'
  + '<div class="bar" style="margin-top:10px">'
  + '<button class="go" data-act="verify-20">Vérifier 20 Go</button>'
  + '<button class="ghost" data-act="verify" data-val="false">Tout vérifier</button></div>';
}

function renduSauvegardes(r) {
  const lots = r.lots || [];
  return '<p class="mono">Réglages et comptes uniquement — jamais les jeux. '
    + 'Une sauvegarde est prise automatiquement à chaque changement, au plus '
    + 'une par heure.</p>'
    + '<div class="bar" style="margin:10px 0">'
    + '<button class="go" data-act="sauvegarder">Sauvegarder maintenant</button></div>'
    + (lots.length ? '<ul class="entretien-l">' + lots.map(l =>
        '<li><b>' + esc(l.date || l.lot) + '</b> <span class="mono">' + esc(l.motif || '')
        + ' · ' + nb((l.fichiers || []).length, 'fichier(s)') + '</span>'
        + ' <button class="ghost mini" data-act="restaurerSauvegarde" data-arg="' + esc(l.lot) + '">Restaurer</button></li>').join('') + '</ul>'
      : '<p class="lead">Aucune sauvegarde pour l\'instant.</p>');
}

function renduAcces(r) {
  const s = r.resume || {};
  const ev = r.evenements || [];
  const nom = {connexion: 'Connexion', refus: 'Refusée', deconnexion: 'Déconnexion',
               compte: 'Compte'};
  return _lignes([
    ['Événements enregistrés', s.evenements || 0],
    ['Tentatives refusées', s.refus || 0],
    ['Dernière connexion', esc((s.derniere_connexion || {}).t || '—')],
  ])
  + (ev.length ? '<ul class="entretien-l entretien-acces">' + ev.slice(0, 40).map(e =>
      '<li class="ac-' + esc(e.e) + '"><span class="mono">' + esc(e.t) + '</span> '
      + esc(nom[e.e] || e.e) + (e.email ? ' — ' + esc(e.email) : '')
      + (e.ip ? ' <span class="mono">' + esc(e.ip) + '</span>' : '')
      + (e.detail ? '<br><span class="mono">' + esc(e.detail) + '</span>' : '')
      + '</li>').join('') + '</ul>'
    : '<p class="lead">Aucun événement — l\'authentification n\'est pas active.</p>');
}

function renduTransfert(r) {
  const t = r.reprise;
  if (!t) return '<p class="lead">Aucun transfert interrompu.</p>';
  return _lignes([
    ['Fichiers déjà envoyés', t.faits],
    ['Restant à envoyer', t.restants + '  ·  ' + fmt(t.octets)],
    ['Destination', '<code>' + esc(t.destination) + '</code>'],
    ['Interrompu depuis', duree(t.depuis)],
  ])
  + '<p class="lead"><span class="beta">bêta</span> La reprise repart du dernier '
  + 'fichier confirmé. En cas de doute, abandonner puis renvoyer reste plus sûr.</p>'
  + '<div class="bar" style="margin-top:10px">'
  + '<button class="go" data-act="reprendreTransfert">Reprendre</button>'
  + '<button class="ghost" data-act="oublierTransfert">Abandonner</button></div>';
}

function batterieHtml(b) {
  if (!b || b.pourcent == null) return '';
  const p = Math.max(0, Math.min(100, b.pourcent));
  const charge = b.etat === 'charge' || b.branchee;
  const niveau = charge ? 'charge' : p <= 10 ? 'critique' : p <= 25 ? 'faible' : 'ok';
  const detail = [p + ' %',
                  charge ? 'en charge' : 'sur batterie',
                  b.temperature != null ? b.temperature + ' °C' : '',
                  b.sante && b.sante !== 'bonne' ? 'santé : ' + b.sante : '']
    .filter(Boolean).join(' · ');
  return '<span class="batt batt-' + niveau + '" title="' + esc(detail) + '">'
    + '<span class="batt-corps"><i style="width:' + p + '%"></i></span>'
    + '<span class="batt-borne"></span>'
    + (charge ? '<span class="batt-eclair">⚡</span>' : '')
    + '<span class="batt-txt">' + p + '%</span></span>';
}

function renderConn(d) {
  // Bloc unique de l'en-tete. Il repond a quatre questions et pas une de plus :
  // quelle console, par quel lien, depuis quand, sous quel Android. L'adresse
  // IP et le numero de serie appartiennent aux Reglages, pas a l'en-tete.
  const c = (d && d.connection) || {};
  CONN = c;
  if (d && d.info) CONN_INFO = d.info;
  if (d && 'batterie' in d) BATTERIE = d.batterie;
  renderLib();
  const el = $('conn');
  const i = CONN_INFO || {};
  const h = DATA.stats ? DATA.stats.versions_h : null;
  const vers = h == null ? ''
    : h < 1 ? t('base des versions à l\'instant')
            : t('base des versions il y a %d h').replace('%d', h);

  if (c.kind) {
    const faits = [c.kind === 'usb' ? 'USB' : 'Wi-Fi'];
    if (c.depuis != null) faits.push(duree(c.depuis));
    if (i.android) faits.push('Android ' + i.android);
    if (vers) faits.push(vers);
    el.className = 'conn on';
    el.innerHTML = '<span class="cdot on"></span>' +
      '<span class="cnom">' + esc(i.name || 'Console') + '</span>' +
      batterieHtml(BATTERIE) +
      '<span class="cfaits">' + faits.map(esc).join('<i>·</i>') + '</span>';
    el.title = 'Connectée ' + (c.kind === 'usb' ? 'par câble USB' : 'en Wi-Fi') +
               (c.serial ? ' — ' + c.serial : '');
  } else {
    el.className = 'conn off';
    el.innerHTML = '<span class="cdot off"></span>' +
      // `cnom` porte le NOM de la console, une donnee : il est dans
      // CLASSES_DONNEES pour n'etre jamais traduit. Le libelle « aucune
      // console », lui, doit l'etre — et il portait la meme classe, donc il
      // restait en francais dans une interface anglaise. Meme defaut que la
      // classe `tid`, qui servait a la fois de marqueur et de style.
      '<span class="cvide">Aucune console</span>' +
      '<span class="cfaits">' +
        '<button class="lien" data-act="detect">Détecter</button><i>·</i>' +
        '<button class="lien" data-act="togglePair">sans câble</button>' +
        (vers ? '<i>·</i>' + esc(vers) : '') +
      '</span>';
    el.title = t('Branche le câble USB, ou connecte la console sans fil.');
  }
}

// Les actions proposees dependent de l'etat : inviter a « Détecter » une console
// deja connectee n'apprend rien et encombre.
function renderBarreConsole(info) {
  const el = $('barreconsole');
  if (!el) return;
  const ok = info && info.connected;
  el.innerHTML = ok
    ? '<button class="ghost" data-act="actualiser">Relire les jeux</button>' +
      '<span style="flex:1"></span>' +
      '<button class="ghost" data-act="detect">Re-détecter</button>' +
      (CONN.kind === 'usb'
        ? '<button class="ghost" data-act="wifiSwitch">Passer en Wi-Fi</button>'
        : '<button class="ghost" data-act="wifiForget">Oublier ce lien</button>')
    : '<button class="go" data-act="detect">Détecter la console</button>' +
      '<button class="ghost" data-act="togglePair">' +
        esc(t('Connecter sans câble')) + '</button>';
}

function renderDeviceCard(info, volumes) {
  renderBarreConsole(info);
  const el = $('device');
  if (!info.connected) {
    el.innerHTML = '<div class="empty">' + esc(t('Aucune console prête.')) + '<br>' +
      esc(t('Branche la console en USB, autorise le débogage, puis clique sur « Détecter ».')) +
      '</div>';
    return;
  }
  const vols = (volumes || []).map(v => {
    const used = (v.total && v.free != null) ? (v.total - v.free) / v.total : 0;
    const spc = v.free != null ? fmt(v.free) + ' libre / ' + fmt(v.total) : 'espace inconnu';
    return '<div class="vol" data-act="setDpath" data-arg="' + esc(v.path) + '" title="Explorer ce volume">' +
      '<span class="tag t-' + (v.kind === 'SD' ? 'DLC' : 'BASE') + '">' + esc(v.kind) + '</span>' +
      '<span class="grow"><div>' + esc(v.label) + '</div><span class="mono">' + esc(v.path) + '</span></span>' +
      '<span class="meter' + (used > 0.9 ? ' tight' : '') + '"><i style="width:' + Math.round(used * 100) + '%"></i></span>' +
      '<span class="size" style="width:auto">' + spc + '</span></div>';
  }).join('') || '<div class="vol"><span class="mono">aucun volume detecte</span></div>';
  el.innerHTML = '<div class="card"><div class="ghead"><span class="gname">' + esc(info.name) +
    '</span><span class="mono">Android ' + esc(info.android || '?') + ' &middot; ' + esc(info.serial || '') +
    '</span></div>' + vols + '</div>';
}
function renderCrumb(path) {
  const parts = path.split('/').filter(Boolean);
  let acc = '';
  const segs = ['<a data-path="/">racine</a>'];
  parts.forEach(p => { acc += '/' + p; segs.push('<a data-path="' + esc(acc) +
      '" data-i18n-skip>' + esc(p) + '</a>'); });
  $('crumb').innerHTML = segs.join('<span class="sep">&rsaquo;</span>');
}
function renderBrowser(path, items) {
  renderCrumb(path);
  const isGame = n => /\.(nsz|xcz|nsp|xci)$/i.test(n);
  const join = n => (path === '/' ? '/' + n : path.replace(/\/+$/, '') + '/' + n);
  const parent = path.replace(/\/+$/, '').replace(/\/[^/]*$/, '') || '/';
  const up = path === '/' ? '' :
    '<div class="brow dir up" data-path="' + esc(parent) + '"><span class="ic">&uarr;</span>' +
    '<span class="fn">.. (dossier parent)</span></div>';
  const dirs = items.filter(i => i.is_dir).map(i =>
    '<div class="brow dir" data-path="' + esc(join(i.name)) + '"><span class="ic">&#128193;</span>' +
    '<span class="fn" data-i18n-skip>' + esc(i.name) + '</span></div>');
  const files = items.filter(i => !i.is_dir).map(i =>
    '<div class="brow file' + (isGame(i.name) ? ' game' : '') + '"><span class="ic">' +
    (isGame(i.name) ? '&#9679;' : '&middot;') + '</span><span class="fn" data-i18n-skip>' + esc(i.name) + '</span></div>');
  $('browser').innerHTML = '<div class="card">' + up + (dirs.concat(files).join('') ||
    '<div class="brow"><span class="fn">Dossier vide.</span></div>') + '</div>';
}
// ---- navigateur du SERVEUR (a ne pas confondre avec celui de la console)
// Celui-ci ne rend que des dossiers : le serveur ne renvoie aucun nom de
// fichier. Le seul chiffre affiche est le nombre de jeux reconnus, parce que
// c'est ce qui permet de reconnaitre sa ludotheque sans ouvrir un terminal.
// `cible` dit lequel des deux ecrans affiche le navigateur. L'assistant se
// redessine en entier a chaque changement d'etat : y injecter le resultat d'un
// appel asynchrone serait efface au rendu suivant. Il lit donc `LUDO.etat`.
let LUDO = {chemin: '', etat: null, cible: 'set'};

function htmlLudo(r) {
  const parts = String(r.chemin || '').split('/').filter(Boolean);
  let acc = '';
  const segs = ['<a data-lpath="/">' + esc(t('racine')) + '</a>'];
  parts.forEach(p => { acc += '/' + p; segs.push('<a data-lpath="' + esc(acc) +
      '" data-i18n-skip>' + esc(p) + '</a>'); });
  const bouts = [nb(r.jeux || 0, 'jeu(x) reconnu(s)')];
  if (!r.ecrivable) bouts.push(t('lecture seule'));
  if (r.douteux) bouts.push(t('emplacement déconseillé'));
  const up = r.parent
    ? '<div class="brow dir up" data-lpath="' + esc(r.parent) + '"><span class="ic">&uarr;</span>' +
      '<span class="fn">' + esc(t('.. (dossier parent)')) + '</span></div>'
    : '';
  const dirs = (r.dossiers || []).map(d =>
    '<div class="brow dir' + (d.lisible ? '' : ' muet') + '" data-lpath="' + esc(d.chemin) + '">' +
    '<span class="ic">&#128193;</span><span class="fn" data-i18n-skip>' + esc(d.nom) + '</span></div>');
  return {
    crumb: segs.join('<span class="sep">&rsaquo;</span>'),
    raccourcis: (r.raccourcis || []).map(x =>
      '<button class="ghost" data-lpath="' + esc(x.chemin) + '">' + esc(t(x.nom)) +
      '</button>').join(''),
    etat: bouts.join(' · '),
    browser: '<div class="card">' + up + (dirs.join('') ||
      '<div class="brow"><span class="fn">' + esc(t('Aucun sous-dossier.')) +
      '</span></div>') + '</div>',
  };
}

function renderLudo(r) {
  LUDO.etat = r;
  LUDO.chemin = r.chemin || '';
  const h = htmlLudo(r);
  $('ludocrumb').innerHTML = h.crumb;
  $('ludoraccourcis').innerHTML = h.raccourcis;
  $('ludoetat').textContent = h.etat;
  $('ludobrowser').innerHTML = h.browser;
}

// Le meme navigateur, en chaine, pour l'etape « ta bibliotheque ».
function renduLudoOnboard() {
  if (!LUDO.etat) return '';
  const h = htmlLudo(LUDO.etat);
  return '<div class="ludopick">' +
    '<div class="bar">' + h.raccourcis + '</div>' +
    '<div class="crumb">' + h.crumb + '</div>' +
    '<div class="onbnote">' + esc(h.etat) + '</div>' +
    h.browser +
    '<div class="bar">' +
      '<button class="go" data-act="ludoValider">' +
        esc(t('Utiliser ce dossier')) + '</button>' +
      '<button class="ghost" data-act="ludoAnnulerOnb">' +
        esc(t('Annuler')) + '</button>' +
    '</div></div>';
}

// Le chemin affiche dans les reglages, et le bouton qui va avec. Une
// ludotheque imposee par ROMULE_LIBRARY doit se voir : sans cela on clique sur
// « Changer » et on ne comprend pas le refus.
function majLudotheque() {
  const el = $('s-ludo'), b = $('b-ludo');
  if (!el || !HEALTH) return;
  el.textContent = HEALTH.ludotheque || HEALTH.root || '';
  el.title = el.textContent;
  if (b) {
    b.disabled = !!HEALTH.ludotheque_imposee;
    b.title = HEALTH.ludotheque_imposee
      ? t('Imposé par la variable ROMULE_LIBRARY.') : '';
  }
  (HEALTH.problemes || []).forEach(p => annonce(p, 'warn'));
}

// Nom de fichier nu, seul repere fiable quand le title ID du nom est absent
// ou mensonger : c'est ce nom qu'adb a ecrit sur la console.

function baseName(f) {
  return String(f.rel || f.path || f.name || '').split('/').pop().toLowerCase();
}

function buildConset() {
  CONSET = new Set();
  DGAMES.forEach(g => {
    if (g.tid) CONSET.add(g.tid + '|' + g.version);
    if (g.name) CONSET.add('n|' + g.name.toLowerCase());
  });
}

// Un fichier de la bibliotheque est-il deja sur la console ? Le title ID de la
// bibliotheque vient du contenu, celui de la console du nom du fichier : quand
// le nom ment ou n'en porte pas, les deux ne peuvent pas se rencontrer. On
// retombe alors sur le nom de fichier, comme le fait _console_index cote serveur.
function surLaConsole(f) {
  return (f.tid && CONSET.has(f.tid + '|' + f.version)) || CONSET.has('n|' + baseName(f));
}
function consoleName(n) {
  return n.replace(/\.(nsz|xcz|nsp|xci)$/i, '').replace(/\s*\[0100.*/i, '').trim() || n;
}

// Titre reduit a son essence, pour reconnaitre deux fichiers du meme jeu quand
// leurs noms different : « MARVEL Cosmic Invasion (v1.0.1) (EU) SuperXCI-MBC.xci »
// et « MARVEL Cosmic Invasion v1.0.2[...] » designent bien le meme jeu.
function titreNormalise(n) {
  return String(n || '')
    .replace(/\.(nsz|xcz|nsp|xci)$/i, '')
    .replace(/[\[\(][^\])]*[\])]/g, ' ')        // [tid], (EU), (v1.0.1)…
    .replace(/\bv\d+(\.\d+)*\b/gi, ' ')         // v1.0.2, v262144
    .replace(/\b(superxci|xci|nsp|mbc|upd|dlc|eu|us|jp|fr)\b/gi, ' ')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim().toLowerCase();
}
function groupDeviceGames(games) {
  const gm = {};
  games.forEach(g => {
    const key = g.tid ? tidBase(g.tid) : 'name:' + consoleName(g.name).toLowerCase();
    const grp = gm[key] || (gm[key] = {key, baseName: null, files: []});
    grp.files.push(g);
    if (g.type === 'BASE') grp.baseName = consoleName(g.name);
  });
  return Object.values(gm).map(grp => {
    grp.name = grp.baseName || consoleName(grp.files[0].name);
    grp.hasBase = grp.files.some(f => f.type === 'BASE');
    grp.updCount = grp.files.filter(f => f.type === 'UPDATE').length;
    grp.dlcCount = grp.files.filter(f => f.type === 'DLC').length;
    grp.anyNew = grp.files.some(f => !f.in_library);
    grp.orphan = grp.files.some(f => (f.dflags || []).includes('orphan'));
    grp.paths = grp.files.map(f => f.path);
    grp.size = grp.files.reduce((s, f) => s + f.size, 0);
    return grp;
  }).sort((a, b) => a.name.localeCompare(b.name));
}

// Ce que la console heberge vraiment. Cliquer une ligne bascule la bibliotheque
// sur cette plateforme : le reglage devient un point de depart, pas une impasse.
function renderPlateformes(r) {
  const el = $('plateformes');
  if (!el) return;
  if (!r || !r.connectee) {
    el.innerHTML = '<div class="mono">Branche la console, puis lance la détection : ' +
      'l\'outil listera les plateformes qu\'elle héberge.</div>';
    return;
  }
  const p = r.plateformes || [];
  if (!p.length) {
    el.innerHTML = '<div class="mono">' + phrase(
      'Aucun jeu trouvé sous %s. Vérifie le dossier des ROMs juste au-dessus.',
      '<code>' + esc(r.racine || '') + '</code>') + '</div>';
    return;
  }
  PLATEFORMES = p;
  el.innerHTML = '<div class="pfgrille">' + p.map(s =>
    '<button class="pfcarte' + (s.key === PF_OUVERTE ? ' on' : '') +
    '" data-act="ouvrirPlateforme" data-arg="' + esc(s.key) + '" ' +
    'title="' + esc(phrase('Détail de %s', s.name)) + '">' +
      '<span class="pfnom">' + esc(s.name) + '</span>' +
      '<span class="pfn">' + s.count + '</span>' +
      '<span class="pftaille">' + fmt(s.bytes) + '</span>' +
      '<span class="pfdir">' + esc(s.folder) + '/</span>' +
    '</button>').join('') + '</div>' +
    '<div class="mono" style="margin-top:8px">' +
    phrase('%s plateforme(s) sous %s', p.length,
           '<code>' + esc(r.racine) + '</code>') + ' · ' +
    phrase('%d jeu(x) au total', p.reduce((n, s) => n + s.count, 0)) + '</div>';
  // Le detail d'une plateforme vit desormais dans « Console et émulateur » :
  // cliquer une carte y conduit, plutot que d'ouvrir un second editeur ici.
}

let BATTERIE = null;
let PLATEFORMES = [], PF_OUVERTE = '';

// ------------------------------------------------- reglages par plateforme
// Un seul endroit decide de quelle console on parle. Le selecteur choisit,
// `#pf-commun` montre ce que TOUTE plateforme possede (son dossier sur la
// console), et `#pf-specifique` ne laisse visibles que les blocs portant le
// `data-plateforme` correspondant.
let PF_REGLAGES = localStorage.getItem('pf-reglages') || 'switch';

// « generic » et « switch » sont des mots du code : a l'ecran ils ne disent
// rien. On nomme ce que l'utilisateur reconnait.
function moteurLisible(engine) {
  return {switch: 'Eden', generic: 'lecteur de ROMs (RetroArch, autonome…)'}[engine]
    || engine || '—';
}

function remplirSelecteurPlateforme() {
  const sel = $('s-plateforme');
  if (!sel || !SYSTEMS.length) return;
  // Les plateformes qui ont des reglages propres passent devant : ce sont
  // celles pour lesquelles on vient ici.
  const propres = new Set([...document.querySelectorAll('#pf-specifique [data-plateforme]')]
    .map(e => e.dataset.plateforme));
  const ordre = [...SYSTEMS].sort((a, b) =>
    (propres.has(b.key) - propres.has(a.key)) || a.name.localeCompare(b.name));
  if (!ordre.some(x => x.key === PF_REGLAGES)) PF_REGLAGES = ordre[0].key;
  sel.innerHTML = ordre.map(x =>
    '<option value="' + esc(x.key) + '"' + (x.key === PF_REGLAGES ? ' selected' : '') + '>' +
    esc(x.name) + (propres.has(x.key) ? ' — ' + esc(moteurLisible(x.engine)) : '') +
    '</option>').join('');
  sel.value = PF_REGLAGES;
}

function majReglagesPlateforme() {
  const sys = SYSTEMS.find(x => x.key === PF_REGLAGES);
  const propre = [...document.querySelectorAll('#pf-specifique [data-plateforme]')];
  let visibles = 0;
  propre.forEach(el => {
    const oui = el.dataset.plateforme === PF_REGLAGES;
    el.hidden = !oui;
    if (oui) visibles++;
  });

  const d = $('d-plateforme');
  if (d) {
    R.texte(d, !sys ? 'Ses réglages et son dossier sur la console.'
      : visibles
        ? phrase('%s a %s bloc(s) de réglages qui lui sont propres.',
                 sys.name, visibles)
        : phrase("%s n'a pas de réglage propre : seul son dossier se règle ici.",
                 sys.name));
  }
  renderPfCommun(sys);
}

// Le dossier sur la console : le seul reglage que TOUTE plateforme possede.
// Il se saisissait auparavant a deux endroits — ici et dans la fiche d'une
// plateforme detectee — avec le risque d'afficher deux valeurs differentes.
function renderPfCommun(sys) {
  const el = $('pf-commun');
  if (!el) return;
  if (!sys) { el.innerHTML = ''; return; }
  const perso = ((DATA.config || {}).system_dirs || {})[sys.key] || '';
  const vu = PLATEFORMES.find(x => x.key === sys.key);
  const lignes = [
    ['Moteur', esc(moteurLisible(sys.engine))],
    ['Dossier local', '<code>' + esc(sys.folder) + '/</code>'],
  ];
  if (vu) lignes.push(['Sur la console',
                     nb(vu.count, 'jeu(x)') + '  ·  ' + fmt(vu.bytes)]);

  el.innerHTML =
    '<div class="majbloc">' +
      '<div class="majrow act"><span>Dossier sur la console</span>' +
        '<b><code class="pfchemin">' + esc(perso || sys.device_dir || '—') + '</code></b>' +
        '<button class="ghost" data-act="parcourir" data-arg="' + esc(sys.key) + '" data-arg2="' + esc(sys.device_dir || '') + '">Parcourir…</button>' +
        (perso ? '<button class="ghost" data-act="oublierDossier" data-arg="' + esc(sys.key) + '">Par défaut</button>' : '') +
      '</div>' +
      lignes.map(([k, v]) => '<div class="majrow"><span>' + k + '</span><b>' + v + '</b></div>').join('') +
    '</div>' +
    '<div class="bar" style="margin-top:10px">' +
      '<button class="ghost" data-act="allerSysteme" data-arg="' + esc(sys.key) + '">' +
        'Voir ses jeux</button>' +
      (sys.engine === 'switch'
        ? '<button class="ghost" data-act="mkTree">Créer GAMES / UPDATE / DLC</button>' +
          '<button class="ghost" data-act="organize">Ranger par type</button>' : '') +
    '</div>' +
    (sys.engine === 'switch'
      ? '<p class="erdit petit">La Switch est la seule plateforme à séparer jeux, mises à '
        + 'jour et DLC : Eden en a besoin. Les autres rangent tout à plat.</p>' : '');
}

function renderTreeDans(id) {
  const el = $(id);
  if (!el) return;
  const noms = ['GAMES', 'UPDATE', 'DLC'];
  el.innerHTML = noms.map(f => TREE[f] === true
    ? '<span class="tok">' + f + '</span>'
    : TREE[f] === false ? '<span class="tko">' + f + ' manquant</span>'
    : '<span class="mono">' + f + ' ?</span>').join(' ');
}

function renderTree() {
  const el = $('tree');
  const dir = DATA.config && DATA.config.device_dir;
  const layout = (DATA.config && DATA.config.push_layout) || 'type';
  // ne rien afficher tant que l'utilisateur n'a pas choisi son dossier cible
  if (!dir || layout !== 'type') { el.innerHTML = ''; return; }
  const folders = ['GAMES', 'UPDATE', 'DLC'];
  const missing = folders.some(f => TREE[f] === false);
  const rows = folders.map(f => {
    const st = TREE[f];
    const mark = st === true ? '<span class="tok">✓ existe</span>'
      : st === false ? '<span class="tko">✗ sera créé</span>'
      : '<span class="mono">à vérifier</span>';
    return '<div class="trow">📁 <b>' + f + '/</b> ' + mark + '</div>';
  }).join('');
  el.innerHTML = '<div class="treebox">' +
    '<div class="tlbl">Aperçu de l\'arborescence sous <b>' + esc(dir) + '</b> :</div>' +
    '<div class="troot">📂 ' + esc(dir.split('/').filter(Boolean).pop() || dir) + '/</div>' + rows +
    (missing ? '<button class="go" style="margin-top:9px" data-act="mkTree">Créer les dossiers manquants</button>' : '') +
    '</div>';
}
// statut d'un jeu vis-a-vis de la console : ['ok','sur la console'] | ['upd','en partie'] | ['conv','nouveau'] | null (console non lue)
// ------------------------------------------------- configuration d'Eden
// Reglages les plus utiles, avec leur nom technique : on n'invente pas de
// libelle qui masquerait la cle reelle attendue par l'emulateur.
const EC_CLES = [
  ['Renderer', 'resolution_setup', 'Résolution'],
  ['Renderer', 'scaling_filter', 'Filtre de mise à l\'échelle'],
  ['Renderer', 'anti_aliasing', 'Anticrénelage'],
  ['Renderer', 'use_vsync', 'Synchro verticale'],
  ['Renderer', 'fsr_sharpening_slider', 'Netteté FSR'],
  ['Renderer', 'aspect_ratio', 'Format d\'image'],
  ['Renderer', 'use_asynchronous_gpu_emulation', 'GPU asynchrone'],
  ['Core', 'use_multi_core', 'Multi-cœur'],
  ['Core', 'use_speed_limit', 'Limiter la vitesse'],
  ['Core', 'speed_limit', 'Limite de vitesse (%)'],
  ['Cpu', 'cpu_accuracy', 'Précision CPU'],
  ['System', 'use_docked_mode', 'Mode station d\'accueil'],
  ['Audio', 'volume', 'Volume'],
];
let ECVALS = {}, ECTID = '';

function renderEcTable(valeurs, existe) {
  ECVALS = valeurs || {};
  const lignes = EC_CLES.map(([sec, cle, label]) => {
    const v = (ECVALS[sec] || {})[cle];
    const herite = v === undefined;
    return '<div class="setrow"><div class="setlab"><b>' + esc(label) + '</b>' +
      '<span>' + sec + ' · <code>' + cle + '</code>' +
      (herite ? ' — hérité du réglage global' : '') + '</span></div>' +
      '<div class="setctl"><input type="text" data-sec="' + sec + '" data-cle="' + cle +
      '" value="' + esc(v === undefined ? '' : v) + '" placeholder="' +
      (herite ? 'hérité' : '') + '"></div></div>';
  }).join('');
  $('ec-table').innerHTML = '<div class="setgroup">' +
    '<div class="setgt">' + (ECTID ? 'Réglages du jeu' : 'Réglages globaux') + '</div>' +
    lignes + '</div>';
  $('ec-info').textContent = ECTID
    ? (existe ? 'Configuration propre à ce jeu.' : 'Ce jeu n\'a pas encore de configuration : elle sera créée.')
    : 'Configuration globale d\'Eden.';
}

function renderEcProfiles(profils) {
  const el = $('ec-profiles');
  if (!profils.length) {
    el.innerHTML = '<div class="hintline" style="margin-top:12px">' +
      '<span class="hicon">💾</span><span class="grow">Aucun profil enregistré. ' +
      'Règle un jeu comme tu l\'aimes, puis « Enregistrer comme profil » pour le réutiliser ailleurs.</span></div>';
    return;
  }
  el.innerHTML = '<h3 style="margin:16px 0 8px;font-size:13.5px">Profils enregistrés</h3>' +
    '<div class="card">' + profils.map(p =>
      '<div class="row"><span class="grow"><div class="fname">' + esc(p.nom) + '</div>' +
      '<span class="mono">' + nb(p.reglages, 'réglage(s)') + ' · ' +
      esc(p.portee) + '</span></span>' +
      '<button class="go" data-act="ecApplyProfile" data-arg="' + esc(p.nom) + '">Appliquer ici</button></div>'
    ).join('') + '</div>' +  // i18n:ok - nom de dossier
    '<p class="lead" style="margin-top:8px">Les profils sont des fichiers JSON dans ' +
    '<code>_profils-eden/</code> : tu peux les partager ou en déposer d\'autres.</p>';
}

// --------------------------------------- EmuReady (beta) : compatibilite
let ER = {actif: false, jeux: {}, appareil: '', appareil_nom: ''};
let ER_DEVICES = [];
const ER_CLS = {parfait: 'b-ok', jouable: 'b-upd', limite: 'b-orph', inconnu: 'b-dlc'};
const ER_NIV = {1: ['parfait', 'Parfait'], 2: ['parfait', 'Très bon'], 3: ['jouable', 'Jouable'],
                4: ['limite', 'Problèmes'], 5: ['limite', 'Problèmes'], 6: ['limite', 'Ne démarre pas'],
                7: ['limite', 'Ne démarre pas'], 8: ['limite', 'Ne démarre pas']};

// Renvoie [classe, note, entree, appareil] — `appareil` n'est renseigne que si
// le rapport vient d'une AUTRE console que la tienne. « (autre appareil) » ne
// disait pas lequel : nommer la machine reste informatif sans etre enigmatique.
function erBadge(tid) {
  if (!ER.actif || !tid) return null;
  const e = ER.jeux[tid.toLowerCase()];
  if (!e || e.etat === 'absent') return null;
  if (!e.meilleur) return ['inconnu', 'Non testé', e, null];
  const [cls, txt] = ER_NIV[e.meilleur.rang] || ['inconnu', e.meilleur.note];
  const autre = !e.pour_mon_appareil ? (e.meilleur.appareil || null) : null;
  return [cls, txt, e, autre];
}

// Bloc EmuReady de la fiche. UNE regle par situation, et jamais deux messages
// qui se contredisent — l'ancien affichait « voici les autres appareils »
// juste avant « aucun rapport pour ce jeu ».
//
//   1. module desactive .................. rien
//   2. jeu introuvable sur EmuReady ...... une phrase, fin
//   3. jeu trouve, personne n'a partage .. une phrase, fin
//   4. reglages pour TA console .......... les tiens d'abord, puis les autres
//   5. reglages d'autres consoles seules . on le dit une fois, puis la liste
//   6. ta console non renseignee ......... invitation a la preciser
// Le mode d'emploi (« Voir »/retour arriere) n'apparait QUE s'il y a au moins
// un reglage a poser.
function erSection(g) {
  if (!ER.actif || (g.systeme && g.systeme !== 'switch')) return '';
  const tete = '<div class="ssect">Réglages communautaires <span class="mono">EmuReady</span></div>';
  const e = (ER.jeux[(g.tid || '').toLowerCase()]) || null;

  if (!e || e.etat === 'absent')
    return tete + '<p class="erdit">Ce jeu n\'est pas référencé sur EmuReady.</p>';

  const rapports = e.rapports || [];
  if (!rapports.length)
    return tete + '<p class="erdit">Personne n\'a encore partagé de réglages pour ce jeu.</p>';

  const miens = rapports.filter(r => ER.appareil && r.appareil_id === ER.appareil);
  const autres = rapports.filter(r => !miens.includes(r)).slice(0, 4 - miens.length);

  let intro;
  if (!ER.appareil)
    intro = 'Indique ta console dans les Réglages pour savoir lesquels te concernent.';
  else if (miens.length)
    intro = phrase('%s réglage(s) testé(s) sur ta %s.',
                   miens.length, esc(ER.appareil_nom));
  else
    intro = phrase('Rien de testé sur ta %s. Voici d\'autres appareils, '
                   + 'à titre indicatif.', esc(ER.appareil_nom));

  // Le titre trouve ne s'affiche que s'il y a un doute : sinon c'est du bruit.
  const doute = e.confiance === 'incertain'
    ? '<p class="erdit alerte">' +
      phrase('Le titre trouvé est « %s » : vérifie qu\'il s\'agit bien de ton jeu.',
             esc(e.titre || '')) + '</p>'
    : '';

  const ligne = (r, mien) => {
    const [cls, txt] = ER_NIV[r.rang] || ['inconnu', r.note];
    return '<div class="errow' + (mien ? ' mien' : '') + '">' +
      '<span class="note ' + ER_CLS[cls] + '"><i></i>' + esc(txt) + '</span>' +
      '<span class="grow">' + esc(r.appareil) + (mien ? ' · ta console' : '') + '</span>' +
      '<button class="ghost" data-act="erPreview" data-arg="' + esc(r.id) + '" data-arg2="' + esc(g.tid || '') + '" data-arg3="' + esc(r.appareil) + '">Voir</button>' +
      '<button class="ghost" data-act="erApply" data-arg="' + esc(r.id) + '" data-arg2="' + esc(g.tid || '') + '">Appliquer</button></div>';
  };

  return tete + doute +
    '<p class="erdit">' + intro + '</p>' +
    miens.map(r => ligne(r, true)).join('') +
    autres.map(r => ligne(r, false)).join('') +
    '<p class="erdit petit">« Voir » montre les réglages avant de les poser. ' +
    'Ta configuration actuelle est sauvegardée : le retour en arrière est toujours possible.</p>' +
    '<div id="er-backups"></div>';
}

// ------------------------------------------------ etat d'un jeu sur la console
// Un jeu est « pret » quand ses fichiers jouables sont sur la console ET que
// ses mises a jour / DLC sont actifs dans Eden. On fusionne les deux sources.
const dsel2 = new Set();                 // jeux selectionnes pour le deploiement

function nandParChemin() {
  const m = {};
  NANDST.forEach(x => { m[x.path] = x; });
  return m;
}

// Un seul vocabulaire pour toute l'interface. Avant, la bibliotheque parlait de
// « MAJ dispo / a convertir / a nettoyer » et la console de « a completer /
// prets » : deux echelles pour les memes jeux, d'ou les doublons a l'ecran.
// Les deux sens de transfert doivent se lire sans effort. « À importer » se
// comprenait a l'envers : on dit maintenant OU le jeu manque, et le bouton dit
// quoi faire. Le badge constate, l'action decide.
const ETATS = {
  probleme: ['b-orph', 'Problème'],
  importer: ['b-conv', 'Pas sur le serveur'],
  envoyer:  ['b-conv', 'Pas sur la console'],
  activer:  ['b-upd',  'MAJ à activer'],
  convert:  ['b-upd',  'À convertir'],
  pret:     ['b-ok',   'Prêt'],
  local:    ['b-dlc',  'Sur le serveur'],
};
// Ces etats n'ont de sens que si la console a repondu : sans elle on ne peut pas
// savoir ce qui y manque, et afficher « 0 » serait une reponse inventee.
const ETATS_CONSOLE = ['envoyer', 'activer', 'importer'];

// La console n'est « lue » que lorsqu'on a vraiment liste ses fichiers. Se
// contenter de NANDCONN (Eden repond) laisserait croire, le temps que la liste
// arrive, qu'aucun jeu n'est sur la console : tout s'afficherait « a envoyer ».
function consoleLue() { return CONSET.size > 0; }

function etatDuJeu(g, nmap) {
  nmap = nmap || nandParChemin();
  if (g.console) {   // present sur la console, absent de la bibliotheque
    return {etat: 'importer', txt: ETATS.importer[1], aEnvoyer: [], aActiver: [],
            casses: [], raison: '', note: '', taille: g.size,
            presence: {mac: false, console: 'oui'}};
  }
  const jouables = g.files.filter(f => ['nsp', 'xci'].includes(f.ext));
  const extras = g.files.filter(f => ['UPDATE', 'DLC'].includes(f.type));

  const aEnvoyer = consoleLue() ? jouables.filter(f => !surLaConsole(f)) : [];

  // fichiers incomplets : soit signales par le serveur, soit vus dans la NAND
  const casses = g.files.filter(f => f.broken);
  const aActiver = [];
  extras.forEach(f => {
    const e = nmap[f.path];
    if (!e) return;
    if (['incomplet', 'illisible'].includes(e.etat)) { if (!f.broken) casses.push(f); }
    else if (['absent', 'partiel'].includes(e.etat)) aActiver.push(f);
  });
  // Un jeu ne devient « Probleme » que si c'est SA BASE qui est atteinte. Une
  // mise a jour cassee n'empeche pas d'y jouer : elle merite une remarque, pas
  // un drapeau rouge sur un jeu qui tourne.
  const cassesBase = casses.filter(f => f.type === 'BASE');
  const cassesExtra = casses.filter(f => f.type !== 'BASE');

  // Un etat « Probleme » sans motif oblige a ouvrir la fiche pour comprendre :
  // on porte donc toujours la raison avec l'etat.
  let etat, raison = '', note = '';
  if (cassesExtra.length) {
    note = cassesExtra.length === 1
      ? phrase('Mise à jour incomplète (%s) — le jeu reste jouable',
                 pretty(cassesExtra[0].name))
      : cassesExtra.length + ' MAJ/DLC incomplets — le jeu reste jouable';
  }
  if (cassesBase.length) {
    etat = 'probleme';
    raison = phrase('%s est incomplet — à remplacer', pretty(cassesBase[0].name));
  } else if (!jouables.length) {
    etat = g.needsConvert ? 'convert' : 'probleme';
    if (etat === 'probleme') raison = 'Aucun fichier jouable (.nsp ou .xci)';
  } else if (!g.hasBase) {
    etat = 'probleme';
    raison = 'Le jeu de base manque : ces MAJ/DLC sont inutilisables';
  } else if (!consoleLue()) {
    etat = g.needsConvert ? 'convert' : 'local';
  } else if (aEnvoyer.length) etat = 'envoyer';
  else if (aActiver.length) etat = 'activer';
  else if (g.needsConvert) etat = 'convert';
  else etat = 'pret';
  // Ou se trouve le jeu : deux faits independants, que l'etat seul ne dit pas.
  // « Prêt » n'indiquait pas qu'il est des deux cotes, et une presence partielle
  // ne se distinguait pas d'une absence.
  const presence = {
    mac: true,
    console: !consoleLue() ? 'inconnu'
           : !aEnvoyer.length ? 'oui'
           : aEnvoyer.length < jouables.length ? 'partiel' : 'non',
  };
  return {etat, raison, note, presence, txt: ETATS[etat][1], aEnvoyer, aActiver, casses,
          taille: aEnvoyer.reduce((s, f) => s + f.size, 0)};
}

// Jeux presents sur la console mais absents de la bibliotheque : ils rejoignent
// la meme liste au lieu d'avoir leur propre section.
function jeuxConsoleSeuls() {
  if (!DGAMES.length) return [];
  const connus = new Set(GAMES.map(g => g.key));
  // Le nom de fichier tranche quand le title ID manque ou ment : sans lui, un
  // jeu deja dans la bibliotheque se retrouverait annonce « a importer ».
  const nomsLib = new Set();
  GAMES.forEach(g => g.files.forEach(f => nomsLib.add(baseName(f))));
  // Un jeu de la bibliotheque peut porter un nom different sur la console :
  // le titre reduit reste le seul point commun fiable.
  const titresLib = new Set(GAMES.map(g => titreNormalise(g.name)));
  const dejaLa = f => f.in_library || nomsLib.has(String(f.name || '').toLowerCase())
                   || titresLib.has(titreNormalise(f.name));
  const bruts = groupDeviceGames(DGAMES)
    .filter(grp => !connus.has(grp.key) && !grp.files.some(dejaLa));

  // Un pack .xci sans title ID et la mise a jour du meme jeu formaient deux
  // groupes distincts : le jeu apparaissait deux fois. On les rapproche par
  // leur titre reduit.
  const parTitre = new Map();
  bruts.forEach(grp => {
    const t = titreNormalise(grp.name);
    const deja = parTitre.get(t);
    if (!deja) { parTitre.set(t, grp); return; }
    deja.files = deja.files.concat(grp.files);
    deja.paths = deja.paths.concat(grp.paths);
    deja.size += grp.size;
    deja.updCount += grp.updCount;
    deja.dlcCount += grp.dlcCount;
    deja.hasBase = deja.hasBase || grp.hasBase;
    // Le nom affiche doit etre celui du JEU, pas celui d'une mise a jour. Un
    // pack .xci sans title ID est classe INCONNU alors qu'il contient le jeu :
    // on considere donc « porteur du jeu » tout fichier qui n'est ni MAJ ni DLC.
    const porteJeu = g => g.files.some(f => !['UPDATE', 'DLC'].includes(f.type));
    const a = porteJeu(grp), b = porteJeu(deja);
    if (a && !b) deja.name = grp.name;
    else if (a === b && grp.name.length < deja.name.length) deja.name = grp.name;
  });

  return [...parTitre.values()]
    .map(grp => ({
      key: grp.key, name: grp.name, files: grp.files, size: grp.size,
      // title ID du JEU, pas du fichier : une jaquette n'existe que pour la base
      tid: (f => f ? tidBase(f.tid) : null)(grp.files.find(x => x.tid)),
      updCount: grp.updCount, dlcCount: grp.dlcCount, hasBase: grp.hasBase,
      paths: grp.paths, console: true,
    }));
}

// Tri : chaque critere repond a une question concrete que l'on se pose devant
// sa ludotheque (« lequel est le plus gros ? », « qu'est-ce qui coince ? »).
// L'annee vient d'IGDB : elle n'existait pas avant, d'ou l'absence de ce tri.
function anneeJeu(g) {
  if (!g) return 0;
  // Switch : l'annee vient de nlib, via META. Autres plateformes : d'IGDB, et
  // elle voyage avec le jeu. Sans les deux chemins, le tri par annee ne voyait
  // qu'une poignee de titres.
  const m = g.tid && META[String(g.tid).toLowerCase()];
  const f = (g.files && g.files[0]) || {};
  const a = parseInt((m && m.annee) || g.annee || f.annee || 0, 10);
  return Number.isFinite(a) && a > 1970 ? a : 0;
}

const TRIS = {
  nom:     ['Nom (A → Z)',        (a, b) => nomJeu(a.g).localeCompare(nomJeu(b.g))],
  annee:   ['Année (récent → ancien)',
            (a, b) => (anneeJeu(b.g) - anneeJeu(a.g))
                   || nomJeu(a.g).localeCompare(nomJeu(b.g))],
  taille:  ['Taille (gros → petit)', (a, b) => b.g.size - a.g.size],
  etat:    ['État (à traiter d\'abord)',
            (a, b) => (ORDRE_ETAT[a.e.etat] - ORDRE_ETAT[b.e.etat])
                   || nomJeu(a.g).localeCompare(nomJeu(b.g))],
  contenu: ['Nombre de MAJ / DLC',
            (a, b) => ((b.g.updCount || 0) + (b.g.dlcCount || 0))
                    - ((a.g.updCount || 0) + (a.g.dlcCount || 0))],
};
const ORDRE_ETAT = {probleme: 0, envoyer: 1, importer: 2, activer: 3,
                    convert: 4, local: 5, pret: 6};
const TAILLES = {compact: ['Compact', 112], moyen: ['Moyen', 158], grand: ['Grand', 230]};
// Le nombre par page etait impose par la taille des vignettes : on le choisit
// desormais, y compris « tout afficher » pour une grande ludotheque.
const PAR_PAGE = [24, 48, 96, 200, 0];   // 0 = tout

let TRI = localStorage.getItem('tri') || 'etat';
let SENS = localStorage.getItem('sens') === '-1' ? -1 : 1;   // 1 croissant, -1 inverse
let TAILLE = localStorage.getItem('taille') || 'moyen';
let PARPAGE = parseInt(localStorage.getItem('parpage'), 10);
if (!PAR_PAGE.includes(PARPAGE)) PARPAGE = 48;
let PAGE = 0;
let VUS_PAGE = [];          // cles affichees sur la page courante (selection par plage)
let DERNIER_CLIC = null;    // ancre du Maj+clic

// Filtres avances, cumulables avec l'etat. Ils repondent a des questions que le
// seul etat ne couvre pas : « lesquels ont des DLC ? », « lesquels sont gros ? »
const FAVANCES = {
  maj:      ['Avec mise à jour', x => x.g.updCount > 0],
  sansmaj:  ['Sans mise à jour', x => !x.g.updCount],
  dlc:      ['Avec DLC',         x => x.g.dlcCount > 0],
  gros:     ['Plus de 5 Go',     x => x.g.size > 5 * 1024 ** 3],
  erok:     ['EmuReady : bon',   x => {
              const b = x.g.console ? null : erBadge(x.g.tid);
              return !!b && ['parfait', 'jouable'].includes(b[0]);
            }],
  ernon:    ['EmuReady : non testé', x => {
              const b = x.g.console ? null : erBadge(x.g.tid);
              return !b || b[0] === 'inconnu';
            }],
  // Depuis qu'on connait l'annee et le resume, deux questions deviennent
  // possibles : « qu'est-ce qui est recent ? » et « a quoi manque-t-il une
  // fiche ? ». La seconde est la plus utile : elle montre le travail restant.
  recent:   ['Sorti après 2015',  x => anneeJeu(x.g) >= 2015],
  retro:    ['Sorti avant 2000',  x => { const a = anneeJeu(x.g); return a && a < 2000; }],
  sansfiche: ['Sans description', x => !resumeJeu(x.g)],
  sansjaq:  ['Sans jaquette',     x => sansFiche(x.g)],
};
let FAV = new Set(JSON.parse(localStorage.getItem('fav') || '[]'));

// Un jeu d'une autre console prend la MEME forme qu'un jeu Switch, pour passer
// dans le meme rendu : memes jaquettes, meme selection, memes actions groupees.
// Sans cela les autres systemes heritaient d'une vue au rabais.
function jeuxSysteme() {
  const surConsole = new Set(SCONSOLE.map(n => String(n).toLowerCase()));
  const locaux = SGAMES.map(f => ({
    key: f.path,
    name: f.name,
    tid: null,
    titre: f.titre || '',
    resume: f.resume || '', annee: f.annee || '', editeur: f.editeur || '',
    files: [{...f, type: 'BASE'}],
    size: f.size,
    updCount: 0, dlcCount: 0, hasBase: true,
    systeme: SYS, sysNom: libelleSysteme(SYS),
    _surConsole: surConsole.has(String(f.file || '').toLowerCase()),
  }));
  // Presents sur la console mais pas sur le serveur : sans eux, 19 jeux GBA
  // n'apparaissaient nulle part et ne pouvaient pas etre rapatries.
  const nomsLocaux = new Set(SGAMES.map(f => String(f.file || '').toLowerCase()));
  const distants = SCONSOLE_PATHS
    .filter(p => !nomsLocaux.has(p.split('/').pop().toLowerCase()))
    .map(p => {
      const fichier = p.split('/').pop();
      return {
        key: 'console:' + p, name: fichier, tid: null, titre: SCONSOLE_TITRES[p] || '',
        files: [{path: p, file: fichier, name: fichier, type: 'BASE',
                 ext: (fichier.split('.').pop() || '').toLowerCase(),
                 size: SCONSOLE_TAILLES[p] || 0}],
        size: SCONSOLE_TAILLES[p] || 0, updCount: 0, dlcCount: 0, hasBase: true,
        systeme: SYS, sysNom: libelleSysteme(SYS), console: true, paths: [p],
      };
    });
  return locaux.concat(distants);
}

function etatSysteme(g) {
  // Pas de mises a jour ni de DLC hors Switch : l'etat se resume a « ou est le
  // jeu ? ». Inventer d'autres etats serait mentir.
  if (g.console)
    return {etat: 'importer', raison: '', note: '', txt: ETATS.importer[1],
            aEnvoyer: [], aActiver: [], casses: [], taille: 0,
            presence: {mac: false, console: 'oui'}};
  const lue = consoleLuePour(g);
  const etat = !lue ? 'local' : (g._surConsole ? 'pret' : 'envoyer');
  return {etat, raison: '', note: '', txt: ETATS[etat][1],
          aEnvoyer: g._surConsole ? [] : g.files, aActiver: [], casses: [],
          taille: g._surConsole ? 0 : g.size,
          presence: {mac: true, console: !lue ? 'inconnu' : (g._surConsole ? 'oui' : 'non')}};
}

// Etat d'un jeu, quelle que soit sa plateforme.
function etatDe(g) {
  return (g.systeme && g.systeme !== 'switch') ? etatSysteme(g) : etatDuJeu(g, nandParChemin());
}

// En vue d'ensemble, SCONSOLE est vide : l'appartenance console est portee par
// le jeu lui-meme, pas par la plateforme selectionnee.
function consoleLuePour(g) {
  return vueTotale() ? !!CONN.kind : (isSwitch() ? consoleLue() : SCONSOLE.length > 0);
}

// Toutes les plateformes reunies. Chaque jeu porte le nom de la sienne, sans
// quoi une liste de 200 titres melanges serait illisible.
function jeuxTous() {
  const out = [];
  GAMES.concat(jeuxConsoleSeuls()).forEach(g => {
    if (g.console || g.files.length) out.push({g: Object.assign({}, g, {sysNom: 'Switch'}),
                                               e: etatDuJeu(g, nandParChemin())});
  });
  SALL.forEach(sys => {
    const surConsole = new Set(sys.console.map(x => String(x.nom).toLowerCase()));
    const nomsLocaux = new Set(sys.games.map(f => String(f.file || '').toLowerCase()));
    sys.games.forEach(f => {
      // resume / annee / editeur voyagent avec le jeu : sans eux, la vue
      // « toutes les plateformes » perdait ce que le serveur avait envoye.
      const g = {key: f.path, name: f.name, tid: null, titre: f.titre || '',
                 resume: f.resume || '', annee: f.annee || '', editeur: f.editeur || '',
                 files: [{...f, type: 'BASE'}],
                 size: f.size, updCount: 0, dlcCount: 0, hasBase: true,
                 systeme: sys.key, sysNom: sys.folder,
                 _surConsole: surConsole.has(String(f.file || '').toLowerCase())};
      out.push({g, e: etatSysteme(g)});
    });
    sys.console.forEach(x => {
      const fichier = String(x.chemin).split('/').pop();
      if (nomsLocaux.has(fichier.toLowerCase())) return;
      const g = {key: 'console:' + x.chemin, name: fichier, tid: null, titre: x.titre || '',
                 resume: x.resume || '', annee: x.annee || '', editeur: x.editeur || '',
                 files: [{path: x.chemin, file: fichier, name: fichier, type: 'BASE',
                          ext: (fichier.split('.').pop() || '').toLowerCase(),
                          size: x.taille || 0}],
                 size: x.taille || 0, updCount: 0, dlcCount: 0, hasBase: true,
                 systeme: sys.key, sysNom: sys.folder, console: true, paths: [x.chemin]};
      out.push({g, e: etatSysteme(g)});
    });
  });
  return out;
}

function jeuxUnifies() {
  const cmp = (TRIS[TRI] || TRIS.nom)[1];
  if (vueTotale()) return jeuxTous().sort((a, b) => cmp(a, b) * SENS);
  if (!isSwitch())
    return jeuxSysteme().map(g => ({g, e: etatSysteme(g)})).sort((a, b) => cmp(a, b) * SENS);
  const nmap = nandParChemin();
  return GAMES.concat(jeuxConsoleSeuls())
    .filter(g => g.console || g.files.length)
    .map(g => ({g: Object.assign({}, g, {sysNom: 'Switch'}), e: etatDuJeu(g, nmap)}))
    .sort((a, b) => cmp(a, b) * SENS);
}

/* ============================================================================
   VARIANTES REGIONALES
   ----------------------------------------------------------------------------
   Dix des trente-quatre cartes Switch de cette ludotheque sont DEUX jeux :
   Pokémon FireRed et LeafGreen, chacun en cinq langues. Un tiers de la grille
   pour deux titres.

   Les regrouper par leur nom AFFICHE est impossible : la version allemande
   s'appelle « Pokémon Feuerrote Edition », l'italienne « Versione Rosso
   Fuoco ». Aucune comparaison de chaines ne les rapproche, et il faudrait une
   table de traduction par jeu.

   Le nom de FICHIER, lui, porte la relation :

       Pokémon FireRed Version (German Ver.)
       Pokémon FireRed Version (English Ver.)
       Pokémon FireRed Version (Japanese Ver.)

   On retire donc le marqueur final quand il ne contient QUE des noms de
   langue ou de region. Cette condition est essentielle : sans elle, « Mario
   Party (2019) » et « Mario Party » fusionneraient, ce qui serait faux.
   ========================================================================== */
const LANGUES_REGIONS = new Set((
  'german english spanish french italian japanese korean chinese dutch ' +
  'portuguese russian polish swedish danish norwegian finnish brazilian ' +
  'deutsch francais italiano espanol japonais nederlands portugues ' +
  'usa europe eur jpn jap japan world us eu jp en fr de es it nl pt ru kr cn ' +
  'multi multi3 multi5 pal ntsc intl international rev').split(' '));
// Mots de decor : ils accompagnent le marqueur sans le caracteriser.
const MOTS_DECOR = new Set(['ver', 'version', 'edition', 'ed', 'v']);
const MARQUEUR_FINAL = /\s*[([]([^)\]]{1,28})[)\]]\s*$/;

// Renvoie [nom de base, un marqueur a-t-il ete retire ?].
function baseSansMarqueur(nom) {
  let base = String(nom || '').trim();
  let trouve = false;
  // Un fichier peut en porter deux : « Jeu (English Ver.) [EUR] ».
  for (let tour = 0; tour < 3; tour++) {
    const m = base.match(MARQUEUR_FINAL);
    if (!m) break;
    const mots = m[1].toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .split(/[\s,+._\-/]+/).filter(Boolean)
      .map(w => w.replace(/\.$/, ''))
      .filter(w => !MOTS_DECOR.has(w));
    // Un marqueur vide (« (Ver.) ») ou contenant autre chose qu'une langue
    // arrete le decoupage : on ne devine pas.
    if (!mots.length || !mots.every(w => LANGUES_REGIONS.has(w))) break;
    base = base.slice(0, m.index).trim();
    trouve = true;
  }
  return [base.toLowerCase(), trouve];
}

/* ---------------------------------------------------------------- LANGUES
   Aucune source de fiches ne donne les langues d'un jeu : ni nlib, ni IGDB
   dans ce qu'on leur demande. Le NOM DE FICHIER, lui, les porte — c'est la
   convention des jeux de ROMs :

       Zen Pinball 3D (Europe) (En,Fr,De,Es,It) (eShop).3ds
       Pokémon FireRed Version (French Ver.)

   On ne lit donc que ce qui est ecrit, et on n'affiche rien quand rien n'est
   ecrit : deviner « probablement anglais » serait inventer une information que
   l'utilisateur croirait verifiee. */
const CODES_LANGUE = new Set(('en fr de es it ja nl pt sv no da fi ko zh ru pl ' +  // i18n:ok - codes de langue
  'cs hu tr el ca').split(' '));
const MOT_VERS_CODE = {
  french: 'fr', german: 'de', deutsch: 'de', english: 'en', spanish: 'es',
  espanol: 'es', italian: 'it', italiano: 'it', japanese: 'ja', korean: 'ko',
  chinese: 'zh', dutch: 'nl', portuguese: 'pt', russian: 'ru',
  brazilian: 'pt', japonais: 'ja',
};
const NOM_CODE = {
  fr: 'Français', en: 'Anglais', de: 'Allemand', es: 'Espagnol',
  it: 'Italien', ja: 'Japonais', nl: 'Néerlandais', pt: 'Portugais',
  sv: 'Suédois', no: 'Norvégien', da: 'Danois', fi: 'Finnois',
  ko: 'Coréen', zh: 'Chinois', ru: 'Russe', pl: 'Polonais',
  cs: 'Tchèque', hu: 'Hongrois', tr: 'Turc', el: 'Grec', ca: 'Catalan',
};
const GROUPES_NOM = /[([][^)\]]{1,40}[)\]]/g;

function languesJeu(g) {
  const vues = [];
  for (const groupe of String((g && g.name) || '').match(GROUPES_NOM) || []) {
    const dedans = groupe.slice(1, -1).trim();
    // « En,Fr,De,Es,It » : le groupe ENTIER doit etre fait de codes connus,
    // sinon « (US) » ou « (v1.0.1) » passeraient pour des langues.
    const bouts = dedans.split(',').map(x => x.trim().toLowerCase()).filter(Boolean);
    if (bouts.length && bouts.every(x => CODES_LANGUE.has(x))) {
      for (const b of bouts) if (!vues.includes(b)) vues.push(b);
      continue;
    }
    // « French Ver. », « (Japanese) »
    for (const mot of dedans.toLowerCase().split(/[\s._-]+/)) {
      const c = MOT_VERS_CODE[mot.replace(/\.$/, '')];
      if (c && !vues.includes(c)) vues.push(c);
    }
  }
  return vues;
}

// Une seule langue : son code, court et sans ambiguite. Plusieurs : « MULTI »,
// parce qu'aligner cinq codes sur une jaquette de 158 px la rendrait illisible
// — le detail va dans l'infobulle et dans la fiche.
function etiquetteLangues(g) {
  const codes = languesJeu(g);
  if (!codes.length) return null;
  const noms = codes.map(c => NOM_CODE[c] || c.toUpperCase()).join(', ');
  return codes.length === 1
    ? {court: codes[0].toUpperCase(), long: noms}
    : {court: 'MULTI', long: noms};
}


// Quelle version represente le groupe : celle de la langue de l'interface si
// elle existe, sinon l'anglaise, sinon la premiere venue. Montrer la version
// japonaise d'un jeu a un utilisateur francophone serait un choix arbitraire.
const LANGUE_MARQUEUR = {fr: 'french', en: 'english'};

function representantGroupe(membres) {
  const voulu = LANGUE_MARQUEUR[LANGUE] || 'english';
  const noteDe = x => {
    const n = String(x.g.name || '').toLowerCase();
    if (n.includes(voulu)) return 3;
    if (n.includes('english')) return 2;
    return 1;
  };
  return membres.reduce((a, b) => (noteDe(b) > noteDe(a) ? b : a), membres[0]);
}

// Les membres de chaque groupe, tels que la derniere liste affichee les a
// vus. La fenetre des versions les relit : elle montre exactement ce que la
// bibliotheque contient au moment ou on l'ouvre, filtres compris.
let GROUPES = new Map();

function regrouper(liste) {
  const paquets = new Map();
  for (const x of liste) {
    const [base, marque] = baseSansMarqueur(x.g.name);
    if (!base) continue;
    const p = paquets.get(base) || {membres: [], marque: false};
    p.membres.push(x);
    p.marque = p.marque || marque;
    paquets.set(base, p);
  }
  // Un groupe n'existe que si plusieurs jeux le composent ET qu'au moins l'un
  // d'eux portait vraiment un marqueur de langue.
  GROUPES = new Map();
  for (const [base, p] of paquets)
    if (p.membres.length > 1 && p.marque) GROUPES.set(base, p.membres);
  if (!GROUPES.size) return liste;

  // Le groupe occupe UNE carte, toujours. Deplier les versions au milieu de la
  // grille les melangeait aux autres jeux : rien ne disait ou le groupe
  // commencait ni ou il finissait. Elles ont maintenant leur fenetre.
  const sortie = [], vus = new Set();
  for (const x of liste) {
    const [base] = baseSansMarqueur(x.g.name);
    const membres = GROUPES.get(base);
    if (!membres) { sortie.push(x); continue; }
    if (vus.has(base)) continue;
    vus.add(base);
    const chef = representantGroupe(membres);
    sortie.push(Object.assign({}, chef, {
      g: Object.assign({}, chef.g, {groupeCle: base, groupeN: membres.length}),
    }));
  }
  return sortie;
}

// Liste effectivement affichee : recherche + etat + filtres avances cumules.
function jeuxFiltres(tous) {
  const q = ($('filter').value || '').toLowerCase();
  // la recherche porte sur les DEUX noms : celui du fichier et le titre officiel
  let l = tous.filter(({g}) => !q || g.name.toLowerCase().includes(q)
                            || nomJeu(g).toLowerCase().includes(q));
  if (FILTER !== 'all') l = l.filter(({e}) => e.etat === FILTER);
  FAV.forEach(k => { if (FAVANCES[k]) l = l.filter(FAVANCES[k][1]); });
  return l;
}



// Tout ce que la selection permet de faire, dans les deux sens : ce qui manque
// sur la console, ce qui manque sur le serveur, et ce qu'on peut retirer de chaque cote.
function deployCibles() {
  // Hors Switch : pas de NAND ni de MAJ, mais les memes gestes — envoyer,
  // retirer de la console, mettre a la corbeille.
  if (!isSwitch()) {
    const envoyer = [], supprConsole = [], local = [], importer = [];
    let poids = 0;
    const distants = {};
    SCONSOLE_PATHS.forEach(p => { distants[p.split('/').pop().toLowerCase()] = p; });
    jeuxSysteme().forEach(g => {
      if (!dsel2.has(g.key)) return;
      if (g.console) { (g.paths || []).forEach(p => { importer.push(p); supprConsole.push(p); }); return; }
      local.push(g.key);
      if (!g._surConsole) { envoyer.push(g.key); poids += g.size; }
      const d = distants[String(g.files[0].file || '').toLowerCase()];
      if (d) supprConsole.push(d);
    });
    return {envoyer, activer: [], importer, supprConsole, local, poids};
  }
  const nmap = nandParChemin();
  const envoyer = [], activer = [], importer = [], supprConsole = [], local = [];
  let poids = 0;
  const nomsConsole = {};
  DGAMES.forEach(d => { nomsConsole[String(d.name || '').toLowerCase()] = d.path; });

  GAMES.concat(jeuxConsoleSeuls()).forEach(g => {
    if (!dsel2.has(g.key)) return;
    if (g.console) {
      (g.paths || []).forEach(p => { importer.push(p); supprConsole.push(p); });
      return;
    }
    const e = etatDuJeu(g, nmap);
    e.aEnvoyer.forEach(f => { envoyer.push(f.path); poids += f.size; });
    e.aActiver.forEach(f => activer.push(f.path));
    g.files.forEach(f => {
      local.push(f.path);
      const dist = nomsConsole[baseName(f)];
      if (dist) supprConsole.push(dist);
    });
  });
  return {envoyer, activer, importer, supprConsole, local, poids};
}


// ---------------------------------------------------------------- reglages
// Description affichee sous chaque menu : l'utilisateur voit l'effet de son
// choix sans avoir a deplier trois pavés de texte.
const SET_DESC = {
  'd-layout': {type: 'Chaque fichier est classé selon sa nature. Le plus clair pour l\'émulateur.',
               game: 'Reproduit l\'arborescence du serveur : un dossier par jeu.',
               flat: 'Tout dans le dossier cible, sans sous-dossier.'},
  'd-local': {type: 'Comme sur la console. Recommandé pour rester cohérent.',
              game: 'Un dossier par jeu, nommé d\'après le jeu.'},
  'd-verify': {size: 'Rapide, suffisant dans la plupart des cas.',
               hash: 'Sûr mais plus lent : relit chaque fichier des deux côtés.',
               none: 'Aucun contrôle. Le plus rapide.'},
  'd-cover': {nlib: 'Icône officielle par title ID, sans configuration.',
              steamgriddb: 'Jaquettes verticales de qualité. Nécessite une clé API.',
              custom: 'Ton propre modèle d\'URL.'},
};
// Les champs du SSO n'ont de sens qu'en mode SSO : on les masque sinon, plutot
// que de laisser une dizaine de champs inertes a l'ecran.
function majBlocAuth() {
  const sel = $('s-authmode'), bloc = $('blocoidc'), interne = $('blocinterne');
  if (!sel || !bloc) return;
  const mode = sel.value;
  bloc.style.display = mode === 'oidc' ? '' : 'none';
  if (interne) interne.hidden = mode !== 'interne';
  const c = DATA.config || {};
  // Un mode annonce mais inutilisable ne protege rien : le dire franchement
  // vaut mieux que de laisser croire que l'acces est verrouille.
  const sansFournisseur = mode === 'oidc'
    && !((c.oidc_issuer || '').trim() && (c.oidc_client_id || '').trim());
  const sansCompte = mode === 'interne' && !COMPTES.length;
  const d = $('d-auth');
  if (d) {
    d.textContent =
      mode === 'aucun'
        ? "Sans authentification, seul l'accès local est ouvert."
      : sansFournisseur
        ? 'Fournisseur non renseigné : le SSO reste INACTIF tant que l\'adresse et '
          + 'le client ID ne sont pas remplis.'
      : sansCompte
        ? "Aucun compte n'existe encore : la protection reste INACTIVE tant que "
          + 'personne ne peut se connecter.'
      : mode === 'interne'
        ? 'Chaque personne se connecte avec son adresse et son mot de passe, '
          + 'y compris depuis cette machine.'
        : 'La connexion est déléguée au fournisseur, y compris depuis cette machine.';
    R.classe(d, 'avert', sansFournisseur || sansCompte);
  }
  if (mode === 'interne') chargerComptes();
  chargerCles();
}

// ------------------------------------------------------------------ cles d'API
// Elles ne sont montrees qu'une fois. Le magasin n'en garde qu'une empreinte,
// ce qui rend une fuite du fichier d'etat inoffensive — mais interdit de les
// reafficher. Toute l'ergonomie de ce bloc decoule de cette contrainte : la
// cle apparait en grand a la creation, avec un bouton copier, et l'utilisateur
// est prevenu qu'elle ne reviendra pas.
let CLES = [];

async function chargerCles() {
  const r = await api('/api/cles', null, true);
  if (!r || r.error) return;
  CLES = r.cles || [];
  dessinerCles();
}

function dessinerCles() {
  const boite = $('listecles');
  if (!boite) return;
  const vivantes = CLES.filter(k => !k.revoquee);
  if (!vivantes.length) {
    boite.innerHTML = '<p class="lead" style="margin:0 0 8px">'
      + esc(t('Aucune clé. L\'API n\'est atteignable par personne.'))
      + '</p>';
    return;
  }
  boite.innerHTML = vivantes.map(k =>
    '<div class="compte-ligne">'
    + '<span class="compte-nom" data-i18n-skip>' + esc(k.nom) + '</span>'
    + '<span class="compte-mail tid" data-i18n-skip>' + esc(k.prefixe) + '…</span>'
    + '<span class="mono" data-i18n-skip>' + esc(dateCle(k.dernier_usage)) + '</span>'
    + '<button class="ghost mini" data-act="revoquerCle" data-arg="'
    + esc(k.id) + '">' + esc(t('Révoquer')) + '</button>'
    + '</div>').join('');
}

function dateCle(t0) {
  // « jamais » est un fait a signaler, pas une absence a masquer : une cle
  // creee pour un essai et jamais utilisee ouvre toujours l'API.
  if (!t0) return t('jamais utilisée');
  // Les etiquettes de langue ne sont pas du texte d'interface : elles ne
  // se traduisent pas, elles se choisissent.
  const etiquette = LANGUE === 'fr' ? 'fr-FR' : 'en-GB';   // i18n:ok
  return new Date(t0 * 1000).toLocaleDateString(etiquette);
}

async function creerCle() {
  const champ = $('s-clenom');
  const nom = (champ && champ.value || '').trim();
  if (!nom) {
    toast(t('Donne un nom à la clé : c\'est ce qui permettra de savoir '
            + 'laquelle révoquer.'), 'warn');
    if (champ) champ.focus();
    return;
  }
  const r = await api('/api/cle-creer', {nom});
  if (!r || r.error) return;
  if (champ) champ.value = '';
  await chargerCles();
  dialogue({
    titre: t('Clé créée'),
    niveau: 'ok',
    message: t('Note-la maintenant : elle n\'est conservée que sous forme '
               + 'd\'empreinte et ne pourra pas être réaffichée.'),
    detail: r.secret,
    actions: [{libelle: t('Copier'), principal: true, action: () => {
      navigator.clipboard.writeText(r.secret)
        .then(() => toast(t('Clé copiée.'), 'ok'))
        // Le presse-papiers est refuse hors contexte securise : sans ce
        // rattrapage le bouton ne ferait rien, sans un mot. La cle reste
        // lisible dans le detail de la fenetre, donc selectionnable a la main.
        .catch(() => toast(t('Copie refusée par le navigateur : '
                             + 'sélectionne la clé dans le détail.'), 'warn'));
    }}],
  });
}

async function revoquerCle(id) {
  const k = CLES.find(x => x.id === id) || {};
  dialogue({
    titre: t('Révoquer cette clé ?'),
    niveau: 'avert',
    message: phrase('%s cessera de fonctionner immédiatement. C\'est '
                    + 'irréversible : il faudra en créer une autre.',
                    k.nom || id),
    actions: [{libelle: t('Révoquer'), principal: true, action: async () => {
      const r = await api('/api/cle-revoquer', {id});
      if (r && r.ok) toast(t('Clé révoquée.'), 'ok');
      chargerCles();
    }}],
  });
}

// ------------------------------------------------------------ comptes internes
let COMPTES = [], MOI = '', MDP_MIN = 12;

async function chargerComptes() {
  const r = await api('/api/comptes', {}, true);
  if (!r || r.error) return;
  COMPTES = r.comptes || [];
  MOI = r.moi || '';
  MDP_MIN = r.mdp_min || 12;
  dessinerComptes();
}

function dessinerComptes() {
  const boite = $('listecomptes');
  if (boite) {
    const remplir = (el, c) => {
      R.texte(el.querySelector('.compte-nom'), c.nom);
      R.texte(el.querySelector('.compte-mail'),
              c.email + (c.id === MOI ? ' — toi' : ''));
      const b = el.querySelector('button');
      // On ne propose pas de retirer le dernier compte : plus personne ne
      // pourrait entrer.
      b.hidden = COMPTES.length < 2;
      b.onclick = () => supprimerCompte(c);
    };
    R.liste(boite, COMPTES, {
      cle: c => c.id,
      creer: c => {
        const el = document.createElement('div');
        el.className = 'compte-ligne';
        el.innerHTML = '<span class="compte-nom"></span>'
          + '<span class="compte-mail tid"></span>'
          + '<button class="ghost mini">Retirer</button>';
        remplir(el, c);
        return el;
      },
      majEl: remplir,
    });
    R.classe(boite, 'vide', !COMPTES.length);
  }
  const carte = $('moncompte');
  if (!carte) return;
  const moi = COMPTES.find(c => c.id === MOI);
  if (!moi) { carte.innerHTML = ''; return; }
  carte.innerHTML = '<div class="moncompte">'
    + '<div class="avatar"></div>'
    + '<div class="moncompte-txt"><b class="compte-nom"></b>'
    + '<span class="compte-mail tid"></span></div>'
    + '<div class="moncompte-act">'
    + '<button class="ghost mini" data-a="photo">Changer la photo</button>'
    + '<button class="ghost mini" data-a="nom">Renommer</button>'
    + '<button class="ghost mini" data-a="mdp">Mot de passe</button>'
    + '<button class="ghost mini" data-a="totp">' + (moi.double_facteur
        ? 'Retirer le 2e facteur' : 'Double authentification') + '</button>'
    + '<button class="ghost mini" data-a="sortir">Se déconnecter</button>'
    + '</div></div>';
  const av = carte.querySelector('.avatar');
  if (moi.photo) {
    // `?v=` : sans lui, le navigateur reafficherait l'ancienne photo apres
    // un changement, la reponse etant mise en cache.
    av.style.backgroundImage = "url('/photo/" + moi.id + "?v=" + Date.now() + "')";  // i18n:ok - URL CSS
  } else {
    av.textContent = (moi.nom || moi.email).slice(0, 1).toUpperCase();
  }
  R.texte(carte.querySelector('.compte-nom'), moi.nom);
  R.texte(carte.querySelector('.compte-mail'), moi.email);
  const actions = {photo: choisirPhoto, nom: renommerCompte,
                   mdp: changerMotDePasse,
                   totp: () => moi.double_facteur ? retirerDoubleFacteur()
                                                  : activerDoubleFacteur(),
                   sortir: () => location.href = '/auth/logout'};
  carte.querySelectorAll('[data-a]').forEach(b => { b.onclick = actions[b.dataset.a]; });
}

// Les routes de compte renvoient leurs refus en clair (mot de passe trop
// court, email deja pris...) : on les montre tels quels plutot que de laisser
// remonter la fenetre d'erreur generique.
async function envoiCompte(chemin, corps, apres) {
  const r = await api(chemin, corps, true);
  if (!r) return false;
  if (r.error) { toast(r.error, 'warn'); return false; }
  if (r.comptes) COMPTES = r.comptes;
  if (apres) await apres(r);
  toast(r.message || 'Enregistré.', 'ok');
  return true;
}

function ajouterCompte() {
  dialogue({
    titre: 'Ajouter une personne',
    message: 'Elle pourra ouvrir la ludothèque avec ces identifiants.',
    champs: [{id: 'nom', libelle: 'Nom affiché', exemple: 'Prénom'},
             {id: 'email', libelle: 'Adresse email', exemple: 'nom@exemple.fr'},
             {id: 'mdp',
              libelle: phrase('Mot de passe (%s caractères minimum)', MDP_MIN),
              type: 'password', auto: 'new-password'}],
    actions: [{libelle: 'Créer le compte', principal: true, faire: v =>
      envoiCompte('/api/compte-creer', v, () => { dessinerComptes(); majBlocAuth(); })}],
    fermer: 'Annuler',
  });
}

function supprimerCompte(c) {
  dialogue({
    titre: 'Retirer ' + c.email + ' ?',
    niveau: 'warn',
    message: 'Cette personne ne pourra plus ouvrir la ludothèque.',
    actions: [{libelle: 'Retirer', principal: true, faire: () =>
      envoiCompte('/api/compte-supprimer', {id: c.id}, dessinerComptes)}],
    fermer: 'Annuler',
  });
}

function renommerCompte() {
  const moi = COMPTES.find(c => c.id === MOI) || {};
  dialogue({
    titre: 'Mon profil',
    champs: [{id: 'nom', libelle: 'Nom affiché', valeur: moi.nom},
             {id: 'email', libelle: 'Adresse email', valeur: moi.email}],
    actions: [{libelle: 'Enregistrer', principal: true, faire: v =>
      envoiCompte('/api/compte-modifier', v, chargerComptes)}],
    fermer: 'Annuler',
  });
}

function changerMotDePasse() {
  dialogue({
    titre: 'Changer mon mot de passe',
    message: 'Les autres appareils encore connectés seront déconnectés.',
    champs: [{id: 'ancien', libelle: 'Mot de passe actuel', type: 'password',
              auto: 'current-password'},
             {id: 'nouveau',
              libelle: phrase('Nouveau mot de passe (%s caractères minimum)',
                              MDP_MIN), type: 'password',
              auto: 'new-password'},
             {id: 'confirme', libelle: 'Répéter le nouveau', type: 'password',
              auto: 'new-password'}],
    actions: [{libelle: 'Changer', principal: true, faire: v => {
      if (v.nouveau !== v.confirme) return toast('Les deux saisies diffèrent.', 'warn');
      envoiCompte('/api/compte-mdp', {ancien: v.ancien, nouveau: v.nouveau});
    }}],
    fermer: 'Annuler',
  });
}

// Deux etapes volontaires : on ne declare le facteur actif qu'apres avoir vu
// un code valide. Sinon une application mal configuree verrouille le compte.
async function activerDoubleFacteur() {
  const p = await api('/api/compte-totp-preparer', {}, true);
  if (!p || p.error) return toast((p && p.error) || 'Préparation impossible.', 'warn');
  dialogue({
    titre: 'Double authentification',
    message: "Ajoute ce compte dans ton application d'authentification "
           + '(Aegis, Ente, Bitwarden, Google Authenticator…), puis saisis le '
           + "code qu'elle affiche.",
    detail: phrase('Clé à saisir manuellement :\n%s\n\nAdresse otpauth :\n%s',
                   p.lisible, p.uri),
    champs: [{id: 'code', libelle: 'Code à 6 chiffres', exemple: '123456'}],
    actions: [{libelle: 'Activer', principal: true, faire: v =>
      envoiCompte('/api/compte-totp-activer', {code: v.code}, chargerComptes)}],
    fermer: 'Annuler',
  });
}

function retirerDoubleFacteur() {
  dialogue({
    titre: 'Retirer la double authentification ?',
    niveau: 'warn',
    message: 'Le mot de passe seul suffira de nouveau à ouvrir la ludothèque.',
    champs: [{id: 'mdp', libelle: 'Mot de passe actuel', type: 'password',
              auto: 'current-password'}],
    actions: [{libelle: 'Retirer', principal: true, faire: v =>
      envoiCompte('/api/compte-totp-desactiver', {mdp: v.mdp}, chargerComptes)}],
    fermer: 'Annuler',
  });
}

// Une seule fenetre pour TOUS les fichiers a classer : en ouvrir une par
// fichier serait insupportable des qu'on en depose dix.
function ouvrirChoixPlateforme(items) {
  const el = $('dialog');
  const ligne = it => {
    const opts = it.candidats.map(c =>
      '<option value="' + esc(c.key) + '"'
      + (c.key === it.suggestion ? ' selected' : '') + '>'
      + esc(c.name) + (c.key === it.suggestion ? '  ✓ proposé' : '') + '</option>').join('');
    const pourquoi = it.proposes && it.proposes.length
      ? phrase('Sorti sur %s de ces plateformes d\'après IGDB.', it.proposes.length)
      : phrase('Aucune information : %s plateformes utilisent ',
                 it.candidats.length)
        + esc(it.extension) + '.';
    return '<div class="classer-l">'
      + '<div class="classer-n"><b>' + esc(it.nom) + '</b>'
      + '<span class="mono">' + fmt(it.taille) + '  ·  ' + esc(pourquoi) + '</span></div>'
      + '<select data-chemin="' + esc(it.chemin) + '">'
      + '<option value="">— laisser dans le dépôt —</option>' + opts + '</select></div>';
  };
  el.innerHTML = '<div class="sheet dlg d-info" data-interieur>'
    + '<div class="dhead"><span class="dico">📦</span><div>'
    + '<h3>Sur quelle plateforme ?</h3>'
    + '<p class="dmsg">' + phrase('%d fichier(s) portent une extension que ', items.length)
    + 'plusieurs plateformes utilisent. Choisis, ou laisse-les dans le dépôt.</p>'
    + '</div></div>'
    + '<div class="classer">' + items.map(ligne).join('') + '</div>'
    + '<div class="acts"><button class="go" data-di="ok">Ranger</button>'
    + '<button class="ghost" data-di="close">Plus tard</button></div></div>';
  // Rouvrir annule une fermeture en cours : sans cela, le nettoyage
  // differe de `fermerVoile` viderait la fenetre qu'on vient d'ouvrir.
  el.classList.remove('ferme');
  el.classList.add('open');
  el.querySelectorAll('[data-di]').forEach(b => b.addEventListener('click', async () => {
    const valider = b.dataset.di === 'ok';
    const choix = {};
    el.querySelectorAll('select[data-chemin]').forEach(sel => {
      if (sel.value) choix[sel.dataset.chemin] = sel.value;
    });
    app.closeDialog();
    if (!valider || !Object.keys(choix).length) return;
    const r = await api('/api/import-classer', {assignations: choix}, true);
    if (r && r.error) return toast(r.error, 'warn');
    toast((r && r.message) || 'Rangé.', 'ok');
    app.reloadImport();
    app.scan();
  }));
}

function choisirPhoto() {
  const f = document.createElement('input');
  f.type = 'file';
  f.accept = 'image/png,image/jpeg,image/gif,image/webp';
  f.onchange = async () => {
    const fichier = f.files && f.files[0];
    if (!fichier) return;
    let r = {};
    try {
      r = await (await fetch('/api/compte-photo', {method: 'POST', body: fichier})).json();
    } catch (e) { return toast('Envoi impossible.', 'warn'); }
    if (r.error) return toast(r.error, 'warn');
    await chargerComptes();
    toast(r.message || 'Photo mise à jour.', 'ok');
  };
  f.click();
}

function syncSetDesc() {
  const paires = [['s-layout', 'd-layout'], ['s-local', 'd-local'],
                  ['s-verify', 'd-verify'], ['s-coverprov', 'd-cover']];
  paires.forEach(([sel, desc]) => {
    const t = (SET_DESC[desc] || {})[$(sel).value];
    if (t) $(desc).textContent = t;
  });
  // Les champs lies a une source restent TOUJOURS visibles : on ne cache pas
  // un reglage que l'utilisateur pourrait chercher. On signale juste qu'il est
  // inactif avec la source choisie.
  const prov = $('s-coverprov').value;
  const marquer = (row, actif, quand) => {
    $(row).classList.toggle('inactive', !actif);
    // Ce texte etait rendu par `content: attr(data-note)` en CSS : il n'est
    // alors JAMAIS un noeud de texte, donc ni l'observateur ni aucun outil ne
    // peut le voir — et il ne pouvait pas etre traduit. Il devient un vrai
    // element, rempli par `textContent`.
    const cible = $(row).querySelector('.setlab span');
    let note = cible && cible.querySelector('.setnote');
    if (cible && !note) {
      note = document.createElement('span');
      note.className = 'setnote';
      cible.appendChild(note);
    }
    if (note) {
      note.textContent = actif ? ''
        // `quand` est lui-meme un libelle : le laisser brut affichait
        // « — used only with “URL personnalisée” », a moitie traduit.
        : phrase('— utilisée seulement avec « %s »', t(quand));
    }
  };
  marquer('row-sgkey', prov === 'steamgriddb', 'SteamGridDB');
  marquer('row-coverurl', prov === 'custom', 'URL personnalisée');
}
function fillSettings() {
  const c = DATA.config || {};
  // un champ peut avoir ete retire de la page : on ne suppose jamais sa presence
  const set = (id, v) => {
    const el = $(id);
    if (el && v != null && document.activeElement !== el) el.value = v;
  };
  set('s-oidcissuer', c.oidc_issuer); set('s-oidcclient', c.oidc_client_id);
  set('s-oidcsecret', c.oidc_client_secret); set('s-oidcemails', c.oidc_emails);
  set('s-oidcgroupes', c.oidc_groupes); set('s-oidcredirect', c.oidc_redirect);
  // `aucun` est la VALEUR du reglage, pas son libelle : l'option affichee
  // vit dans index.html et passe par le catalogue.
  if ($('s-authmode')) $('s-authmode').value = c.auth_mode || 'aucun';  // i18n:ok
  majBlocAuth();
  set('s-jobs', c.jobs); set('s-cover', c.cover_url); set('s-sgkey', c.steamgriddb_key);
  set('s-igdbid', c.igdb_client_id); set('s-igdbsecret', c.igdb_client_secret);
  set('s-romsroot', c.roms_root); set('s-savesdir', c.saves_dir);
  if (c.meta_lang) $('s-lang').value = c.meta_lang;
  if (document.activeElement !== $('s-mirrors')) $('s-mirrors').value = (c.versions_urls || []).join('\n');
  $('s-incr').checked = c.incremental !== false;
  $('s-lan').checked = !!c.lan_access;
  $('s-emuready').checked = !!c.emuready;
  $('s-autonand').checked = !!c.auto_nand;
  $('s-notify').checked = c.notify !== false;
  $('s-layout').value = c.push_layout || 'type';
  $('s-local').value = c.local_layout || 'type';
  $('s-verify').value = c.verify_mode || 'size';
  $('s-coverprov').value = c.cover_provider || 'nlib';
  syncSetDesc();
}

// ---------------------------------------------------------------- app
// Les profils viennent de /api/health : le serveur seul sait lesquels sont
// livres, et lequel est actif.
function nomEmulateur(cle) {
  const p = ((HEALTH && HEALTH.profils) || []).find(x => x.cle === cle);
  return p ? p.nom : (cle || '');
}

// Le pied de page tient l'offre de code source exigee par l'AGPL. Les valeurs
// viennent du serveur : une version ecrite en dur dans la page finit toujours
// par mentir apres une mise a jour.
function renderPied() {
  if (!HEALTH) return;
  const v = $('pied-version');
  if (v && HEALTH.version) v.textContent = 'Romule ' + HEALTH.version;
  const l = $('pied-licence');
  if (l && HEALTH.licence) l.textContent = HEALTH.licence.replace('-or-later', '');
  const a = $('pied-source');
  if (a && HEALTH.source) a.href = HEALTH.source;
}

function renderChoixEmulateur() {
  const el = $('choixemulateur');
  if (!el || !HEALTH) return;
  const profils = HEALTH.profils || [];
  if (!profils.length) { el.innerHTML = ''; return; }
  const actif = (HEALTH.checks || {}).emulateur || '';
  // Un `<option>` ne contient que du texte : on ne peut pas y isoler le nom du
  // profil de sa mention « non verifie ». La phrase est donc assemblee DEJA
  // traduite, sinon le parcours du DOM cherche « Eden — not verified » comme
  // une seule cle, qu'aucun catalogue ne contiendra jamais.
  el.innerHTML = '<select id="selemulateur" data-act-change="choisirEmulateur">' +
    profils.map(x => {
      const nom = t(x.nom);
      return '<option value="' + esc(x.cle) + '"' +
        (x.cle === actif ? ' selected' : '') + '>' +
        esc(x.verifie ? nom : t('%s (non vérifié)').replace('%s', nom)) +
        '</option>';
    }).join('') + '</select>';
}

const app = {
  tab(name) {
    // On note ou en etait la lecture avant de changer d'onglet : revenir des
    // reglages renvoyait jusqu'ici tout en haut de la bibliotheque, ce qui
    // oblige a retrouver a la main la carte qu'on regardait.
    const actuel = document.querySelector('.panel.active');
    if (actuel) DEFILEMENT[actuel.id] = scrollY;
    const poser = () => {
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
      $('panel-' + name).classList.add('active');
      // La jaquette d'exemple des apercus n'existe qu'une fois la ludotheque
      // lue : au premier passage dans les reglages, elle est enfin connue.
      if (name === 'settings') majApercuJaquette();
      // Restauration apres le changement de panneau : avant, la hauteur de
      // page est encore celle de l'ancien onglet et le navigateur ecrete la
      // position demandee.
      const y = DEFILEMENT['panel-' + name];
      requestAnimationFrame(() => scrollTo({top: y || 0, behavior: 'instant'}));
    };
    // Fondu croise natif quand le navigateur sait le faire. Sans lui, les deux
    // panneaux s'echangent d'un coup ; avec, l'ancien s'efface pendant que le
    // nouveau se pose. Aucune bibliotheque : c'est une API du navigateur.
    // On l'evite si l'utilisateur a coupe le mouvement, sinon la transition
    // continue de tourner alors qu'il a demande le contraire.
    const bouge = document.documentElement.dataset.mvt !== 'aucun';
    if (bouge && document.startViewTransition) {
      // Marque le TYPE de transition : l'ouverture d'une fiche en utilise une
      // autre, et les deux se partagent les memes pseudo-elements.
      document.documentElement.classList.add('vt-onglet');
      const t = document.startViewTransition(poser);
      const fini = () => document.documentElement.classList.remove('vt-onglet');
      t.finished.then(fini, fini);
    } else poser();
  },
  // La console est interrogee une seule fois, au demarrage : la liste des jeux
  // en depend, et elle n'est plus derriere un onglet qu'il faudrait ouvrir.
  _consoleReady: false,
  async reveilConsole() {
    if (this._consoleReady) return;
    this._consoleReady = true;
    // `detect()` enchaine deja sur la lecture des fichiers et de la NAND :
    // les refaire ici doublait chaque appel, et chaque notification.
    await this.detect();
    if (!CONN.kind) return;                 // rien a lire : on reste hors ligne
    this.ecLoad();
  },
  setFilter(f) {
    FILTER = f; PAGE = 0;   // changer de filtre ramene toujours a la premiere page
    majChips();
    renderLib();
  },

  // appele a chaque frappe dans la recherche : la page courante n'a plus de sens
  renderLib() { PAGE = 0; renderLib(); },

  // ---- bibliotheque : actions par jeu
  // Cherche dans la liste AFFICHEE, pas seulement dans la bibliotheque Switch :
  // les jeux des autres plateformes et ceux presents uniquement sur la console
  // n'y figurent pas, et leur fiche restait donc vide.
  gameByKey(k) {
    const t = jeuxUnifies().find(x => x.g.key === k);
    return t && t.g;
  },
  async openGame(k) {
    const g = this.gameByKey(k); if (!g) return;
    ouvrirDepuisJaquette(k, () => {
      $('modal').innerHTML = openGameHtml(g);
      // Rouvrir annule une fermeture en cours : sans cela, le nettoyage
      // differe de `fermerVoile` viderait la fenetre qu'on vient d'ouvrir.
      $('modal').classList.remove('ferme');
      $('modal').classList.add('open');
      auPremierPlan($('modal'));
    });
    const info = $('gm-info'), desc = $('gm-desc');

    // Ce que l'on sait deja, tout de suite : la fiche ne doit jamais rester
    // bloquee sur « chargement… » quand aucune fiche distante n'existe.
    const resume = resumeJeu(g);
    if (desc && resume) desc.textContent = resume;
    if (!g.tid) {
      const sys = SYSTEMS.find(x => x.key === (g.systeme || SYS));
      const bits = [sys && sys.name,
                    nb(g.files.length, 'fichier(s)'),
                    ((g.files[0] || {}).ext || '').toUpperCase()].filter(Boolean);
      if (info) info.textContent = bits.join('  ·  ');
      return;
    }
    this.loadBackups(g.tid.toUpperCase());   // historique des configurations
    const r = await api('/api/game-meta', {tid: g.tid});
    const m = r.meta;
    if (!m || !info) { if (info) info.textContent = ''; return; }
    const bits = [m.publisher, m.releaseDate ? fmtDate(m.releaseDate) : null,
      m.numberOfPlayers ? m.numberOfPlayers + ' joueur(s)' : null].filter(Boolean);
    info.textContent = bits.join('  ·  ');
    if (desc && m.description) desc.textContent = m.description;
  },
  closeDialog(e) {
    if (!e || e.target === $('dialog')) fermerVoile($('dialog'));
  },
  closeGame(e) { if (!e || e.target === $('modal')) fermerVoile($('modal')); },
  // Active dans Eden les MAJ/DLC d'UN seul jeu, depuis sa fiche. Le meme
  // traitement en masse reste accessible par la selection.
  async activerJeu(k) {
    const g = this.gameByKey(k);
    if (!g) return;
    if (!CONN.kind) return toast('Connecte d\'abord la console.', 'warn');
    const e = etatDuJeu(g, nandParChemin());
    if (!e.aActiver.length) return toast('Rien à activer pour ce jeu.', 'warn');
    const r = await api('/api/deploy', {envoyer: [], activer: e.aActiver.map(f => f.path), configs: []});
    if (!r.error) {
      toast(phrase('Activation de %s élément(s) lancée.', e.aActiver.length), 'ok');
      this.closeGame();
      this.poll();
    }
  },
  // Rapatrie un jeu qui n'existe que sur la console, depuis sa fiche.
  async importerJeu(k) {
    const g = this.gameByKey(k);
    if (!g || !g.paths || !g.paths.length) return;
    const r = await api('/api/device-import',
                        {paths: g.paths, convert: !g.systeme || g.systeme === 'switch'});
    if (!r.error) { toast('Copie vers le serveur lancée.', 'ok'); this.closeGame(); this.poll(); }
  },
  async convertGame(k) {
    const g = this.gameByKey(k); if (!g) return;
    const paths = g.files.filter(f => f.needs_convert).map(f => f.path);
    if (!paths.length) return toast('Rien à convertir pour ce jeu.', 'warn');
    this.closeGame();
    const r = await api('/api/convert', {paths});
    r.error || (toast('Conversion lancée.', 'ok'), this.poll());
  },
  async convertAll() {
    const paths = DATA.files.filter(f => f.needs_convert).map(f => f.path);
    if (!paths.length) return toast('Rien à convertir.', 'warn');
    const r = await api('/api/convert', {paths});
    r.error || (toast(phrase('Conversion de %d fichier(s) lancée.', paths.length), 'ok'), this.poll());
  },
  // L'envoi depend de la plateforme : la Switch passe par le rangement
  // GAMES/UPDATE/DLC et n'accepte que des conteneurs decompresses ; les autres
  // consoles recoivent leur ROM telle quelle. Sans cette distinction, un jeu
  // 3DS ou GBA se voyait repondre « aucun fichier a envoyer » alors qu'il etait
  // bien la — son extension n'etait simplement pas celle d'un jeu Switch.
  async sendGame(k) {
    const g = this.gameByKey(k); if (!g) return;
    const sys = g.systeme || (g.files && g.files[0] && g.files[0].system) || 'switch';
    const locaux = (g.files || []).filter(f => f && f.path);

    if (sys !== 'switch') {
      const paths = locaux.map(f => f.path);
      if (!paths.length) {
        return toast(phrase('« %s » n\'est pas sur le serveur : rien à envoyer.',
                            nomJeu(g)),
                     'warn');
      }
      this.closeGame();
      this.basculerTaches(true);
      const r = await api('/api/system-push', {system: sys, paths});
      if (!r || r.error) return;
      toast(phrase('Envoi de « %s » lancé.', nomJeu(g)), 'ok');
      return this.poll();
    }

    const paths = locaux.filter(f => ['nsp', 'xci'].includes(f.ext)).map(f => f.path);
    if (!paths.length) {
      const compresses = locaux.filter(f => ['nsz', 'xcz'].includes(f.ext));
      return toast(compresses.length
        ? phrase('Ce jeu est compressé (.%s) : convertis-le d\'abord, '
                 + 'Eden ne lit pas ce format.', compresses[0].ext)
        : phrase('« %s » n\'est pas sur le serveur : rien à envoyer.',
                 nomJeu(g)), 'warn');
    }
    this.closeGame();
    this.basculerTaches(true);
    const r = await api('/api/push', {paths});
    if (!r || r.error) return;
    toast(phrase('Envoi de « %s » lancé.', nomJeu(g)), 'ok');
    this.poll();
  },
  async trashFile(path) {
    if (!confirm('Mettre ce fichier a la corbeille ? Il reste restaurable.')) return;
    const r = await api('/api/trash', {paths: [path]});
    toast(r.message, 'ok'); this.closeGame(); this.scan();
  },

  // ---- systemes / autres consoles
  // Deux appels rapproches partagent la meme promesse : la liste des
  // plateformes etait relue deux fois au demarrage, une par la sequence de
  // lancement et une par la detection.
  loadSystems() {
    if (this._chargeSystems) return this._chargeSystems;
    this._chargeSystems = (async () => {
      try {
        const r = await api('/api/systems');
        SYSTEMS = r.systems || [];
        if (r.extensions && r.extensions.length) EXTS_ACCEPTEES = r.extensions;
        majZoneDepot();
        renderSysSelect();
        remplirSelecteurPlateforme();
        majReglagesPlateforme();
      } finally {
        this._chargeSystems = null;
      }
    })();
    return this._chargeSystems;
  },
  // Changer de plateforme ne doit ni sauter, ni recharger ce qu'on a deja vu.
  //
  // L'ancienne version vidait `SGAMES`, `SCONSOLE` et `SALL` PUIS attendait un
  // aller-retour reseau. Entre les deux, la grille etait vide : le contenu
  // s'effondrait, la page remontait, puis tout revenait. Et rien n'etait garde,
  // donc revenir sur une plateforme deja vue la retelechargait.
  //
  // Deux changements, et l'ordre compte : on garde l'affichage courant jusqu'a
  // ce qu'on ait de quoi le remplacer, et on memorise ce qu'on a recu.
  async setSystem(key) {
    if (SYS === key && CACHE_SYS[key]) return;    // deja la, rien a faire
    SYS = key; dsel2.clear(); PAGE = 0;
    localStorage.setItem('systeme', key);

    const garde = CACHE_SYS[key];
    if (garde) { appliquerSysteme(garde); renderLib(); return; }

    // Rien en cache : on annonce le chargement SANS vider, pour que la hauteur
    // de la grille ne bouge pas — c'est elle qui faisait sauter la page.
    R.classe($('lib'), 'charge', true);
    const jeton = ++CHARGE_SYS;
    try {
      const donnees = vueTotale()
        ? {tout: (await api('/api/library-all', {})).systemes || []}
        : isSwitch() ? {switch: true}
                     : await api('/api/system-games', {system: key});
      // Une reponse arrivee apres qu'on a change d'avis ne doit rien ecraser :
      // deux clics rapides produisaient sinon l'inventaire de la PREMIERE
      // plateforme sous le nom de la seconde.
      if (jeton !== CHARGE_SYS) return;
      CACHE_SYS[key] = donnees;
      appliquerSysteme(donnees);
      renderLib();
    } finally {
      if (jeton === CHARGE_SYS) R.classe($('lib'), 'charge', false);
    }
  },
  // Une seule action principale hors Switch aussi : elle envoie vers la console
  // ce qui manque, et rapatrie ce qui n'existe que la-bas.
  async sendSystem() {
    const c = deployCibles();
    if (!c.envoyer.length && !c.importer.length)
      return toast('Rien à transférer dans cette sélection.', 'warn');
    let lance = false;
    if (c.envoyer.length) {
      const r = await api('/api/system-push', {system: SYS, paths: c.envoyer});
      if (!r.error) lance = true;
    }
    if (c.importer.length) {
      const r = await api('/api/device-import', {paths: c.importer, convert: false});
      if (!r.error) lance = true;
    }
    if (lance) { dsel2.clear(); toast('Transfert lancé.', 'ok'); this.poll(); }
  },
  async importSystem() {
    const r = await api('/api/system-import', {system: SYS});
    r.error || (toast('Rangement lancé.', 'ok'), this.poll());
  },

  // ---- integrite / sauvegardes
  // `budgetGo` limite le passage a une tranche : ce qui n'a jamais ete
  // verifie d'abord, puis le plus ancien. Une verification complete de 160 Go
  // ne se lance jamais en pratique ; par tranches, la couverture progresse.
  async verify(approfondie, budgetGo) {
    const deep = approfondie === undefined
      ? isSwitch() && confirm('Vérification approfondie ?\n\n'
          + "OK = contrôle aussi l'intérieur de chaque fichier (lent)."
          + '\nAnnuler = empreintes seulement (rapide).')
      : !!approfondie;
    const r = await api('/api/verify', {deep, system: SYS, budget_go: budgetGo || null});
    r.error || (toast(budgetGo ? phrase('Vérification de %s Go lancée.', budgetGo)
                               : t('Vérification lancée.'), 'ok'), this.poll());
  },
  async backupSaves() {
    const r = await api('/api/saves-backup', {});
    r.error || (toast('Sauvegarde des parties lancée.', 'ok'), this.poll());
  },
  async loadSaves() {
    const r = await api('/api/saves-list');
    const dirs = (r.dirs || []).length
      ? '<div class="mono" style="margin-bottom:8px">' + t('Source sur la console :') + ' ' +
        (r.dirs || []).map(esc).join('<br>') + '</div>' : '';
    $('saves').innerHTML = dirs + ((r.items || []).length
      ? '<div class="card">' + r.items.map(i => '<div class="row"><span class="grow">' +
          esc(i.name) + '</span><span class="mono">' + nb(i.count, 'fichier(s)') + '</span>' +
          '<span class="size">' + fmt(i.size) + '</span></div>').join('') + '</div>'
      : '<div class="empty">Aucune sauvegarde enregistrée pour l\'instant.</div>');
  },

  // ---- controle de la tache
  async togglePause() {
    const j = await api('/api/job-control', {action: this._paused ? 'resume' : 'pause'});
    this._paused = j.paused;
    $('pausebtn').textContent = j.paused ? 'Reprendre' : 'Pause';
    toast(j.paused ? 'En pause.' : 'Reprise.', 'ok');
  },
  async cancelJob() {
    if (!confirm('Arrêter la tâche en cours ?')) return;
    await api('/api/job-control', {action: 'cancel'});
    toast('Arrêt demandé…', 'warn');
  },

  async scan() {
    DATA = await api('/api/scan');
    render();
    this.loadTrash();
    return this.loadSystems();     // attendue : la sequence de lancement en depend
  },
  async versions(force) { say('Vérification des versions...'); DATA = await api('/api/versions', {force: !!force}); render(); toast('Mises à jour vérifiées.', 'ok'); },
  async doImport() { const r = await api('/api/import', {convert: true}); r.error || (toast('Import lancé.', 'ok'), this.poll()); },
  async reloadImport() { const r = await api('/api/import-list'); renderImport(r.items); toast(phrase('%d élément(s) dans le dépôt.', r.items.length)); },
  copyShop() {
    navigator.clipboard.writeText(DATA.shop_text || '')
      .then(() => toast('Liste copiee.', 'ok')).catch(() => toast('Copie impossible, selectionne le texte.', 'warn'));
  },
  async nandWrite() { const r = await api('/api/nand-write', {}); toast(r.message, 'ok'); },
  // ---- apparence : theme, animation des jaquettes, mouvement
  // Ces trois reglages restent dans le navigateur et non dans la config du
  // serveur : ils decrivent un ECRAN, pas une ludotheque. La meme
  // bibliotheque se consulte en clair sur une tablette et en sombre sur la
  // console, et une preference d'appareil n'a pas a voyager.
  setTheme(v) { poserApparence('theme', v, ['sombre', 'clair', 'auto']); },
  setCarte(v) { poserApparence('carte', v, ['aucune', '0', '1', '2', '3', '4', '5']); },
  // Les trois valeurs autorisees du reglage, pas des libelles.
  setMouvement(v) { poserApparence('mvt', v, ['complet', 'reduit', 'aucun']); },  // i18n:ok

  // ---- langue de l'interface
  async langLoad() {
    const r = await api('/api/langues');
    const sel = $('s-uilang');
    if (sel) {
      sel.innerHTML = (r.langues || []).map(l =>
        '<option value="' + l.code + '">' + esc(l.nom) + '</option>').join('');
      sel.value = r.courante || 'fr';
    }
    await chargerLangue(r.courante || 'fr');
  },
  async setLang(code) {
    if (code === LANGUE) return;
    await this.saveField('ui_lang', code);
    // La traduction remplace le texte DANS le DOM : revenir en arriere
    // demanderait de memoriser chaque original. Une relecture de la page part
    // du bon pied, et la langue est deja enregistree cote serveur.
    location.reload();
  },

  // ---- EmuReady (beta)
  async erLoad() {
    const r = await api('/api/emuready-state', {});
    ER = {actif: !!r.actif, jeux: r.jeux || {}, appareil: r.appareil || '',
          appareil_nom: r.appareil_nom || ''};
    const n = Object.values(ER.jeux).filter(e => e.etat === 'trouve').length;
    const absents = Object.values(ER.jeux).filter(e => e.etat === 'absent').length;
    const info = $('ersync-info');
    if (info) info.textContent = !ER.actif
      ? 'Active EmuReady pour analyser ta ludothèque.'
      : !Object.keys(ER.jeux).length
        ? 'Jamais analysé — clique « Actualiser » pour interroger EmuReady.'
        : phrase('%d jeu(x) reconnus', n)
          + (absents ? phrase(', %d absent(s) de leur base', absents) : '')
          + t('. Les badges apparaissent sur les jaquettes.');
    renderLib();
  },
  async erDevices() {
    const r = await api('/api/emuready-devices', {});
    ER_DEVICES = (r.tous || []);
    const sug = r.suggestions || [];
    // les variantes de la console detectee d'abord, puis tout le reste
    const liste = sug.concat(ER_DEVICES.filter(d => !sug.some(x => x.id === d.id)));
    $('erdevices').innerHTML = liste.map(d =>
      '<option value="' + esc(d.nom) + '">').join('');
    $('s-erdevice').value = ER.appareil_nom || '';
    const h = $('erdev-help');
    if (!h) return;
    if (sug.length && r.modele_detecte) {
      h.textContent = phrase('Détecté : « %s » — choisis ta variante (%s).',
                             r.modele_detecte, sug.map(d => d.nom).join(', '));
    } else if (!ER.appareil) {
      h.textContent = 'Facultatif. Sans modèle, les notes affichées viennent d\'autres ' +
        'appareils et sont marquées d\'une astérisque.';
    } else {
      h.textContent = phrase('Notes calculées pour %s.', ER.appareil_nom);
    }
  },
  async erPickDevice(saisie) {
    const nom = (saisie || '').trim();
    if (!nom) {                       // champ vide : on retire le modele
      await this.saveField('emuready_device', '');
      await this.saveField('emuready_device_nom', '');
      ER.appareil = ''; ER.appareil_nom = '';
      return this.erDevices();
    }
    const d = ER_DEVICES.find(x => x.nom.toLowerCase() === nom.toLowerCase());
    if (!d) return toast('Modèle inconnu : choisis-en un dans la liste proposée.', 'warn');
    await this.saveField('emuready_device', d.id);
    await this.saveField('emuready_device_nom', d.nom);
    ER.appareil = d.id; ER.appareil_nom = d.nom;
    this.erDevices();
    // les rapports memorises etaient tries pour l'ancien modele : on refait
    // l'analyse tout de suite, sinon l'utilisateur voit d'autres consoles.
    toast('Console : ' + d.nom + '. Recalcul des notes…', 'ok');
    this.erSync(true);
  },
  async erSync(force) {
    if (!ER.actif) return toast('Active d\'abord EmuReady dans les réglages.', 'warn');
    const r = await api('/api/emuready-sync', {force: !!force});
    r.error || (toast('Consultation d\'EmuReady…', 'ok'), this.poll());
  },
  // Voir avant d'appliquer : on montre les reglages reels du rapport.
  async erPreview(listingId, tid, appareil) {
    say('Lecture de la configuration…');
    const r = await api('/api/emuready-preview', {listing_id: listingId});
    if (r.error) return;
    const lignes = (r.contenu || '').split('\n');
    // on met en avant les reglages reellement imposes par ce rapport
    const imposes = [];
    lignes.forEach((l, i) => {
      if (l.includes('\\use_global=false')) {
        const cle = l.split('\\')[0].trim();
        const val = (lignes.slice(i, i + 4).find(x => x.trim().startsWith(cle + '=')) || '')
          .split('=')[1];
        if (val !== undefined) imposes.push(cle + ' = ' + val.trim());
      }
    });
    dialogue({
      titre: 'Configuration proposée',
      niveau: 'info',
      message: phrase('Testée sur %s · %s section(s), %s réglage(s) '
                      + 'spécifique(s). Le reste suit tes réglages globaux.',
                      appareil, r.sections, r.surcharges),
      detail: (imposes.length ? 'RÉGLAGES IMPOSÉS PAR CE RAPPORT\n' + imposes.join('\n') +
               '\n\n— fichier complet —\n' : '') + (r.contenu || ''),
      fermer: 'Fermer',
      actions: [{libelle: 'Appliquer ces réglages', principal: true,
                 faire: () => this.erApply(listingId, tid)}],
    });
  },

  // Historique : chaque écriture a laissé une sauvegarde restaurable.
  async loadBackups(tid) {
    const el = $('er-backups');
    if (!el || !tid) return;
    const r = await api('/api/eden-backups', {tid});
    const items = r.items || [];
    if (!items.length) { el.innerHTML = ''; return; }
    el.innerHTML = '<div class="mono" style="margin:10px 0 4px">Revenir en arrière :</div>' +
      items.slice(0, 4).map(b =>
        '<div class="errow"><span class="grow">' + esc(b.quand) + ' · ' +
        (b.vide ? 'aucune configuration' : b.sections + ' section(s), ' + b.surcharges + ' réglage(s)') +
        '</span><button class="ghost" data-act="edenRestore" data-arg="' + esc(tid) + '" data-arg2="' + esc(b.fichier) + '">Restaurer</button></div>').join('');
  },
  async edenRestore(tid, fichier) {
    if (!CONN.kind) return toast('Connecte d\'abord la console.', 'warn');
    if (!confirm('Restaurer cette configuration ?\n\nL\'état actuel est lui aussi sauvegardé ' +
                 'avant, tu pourras revenir dessus.')) return;
    this.closeGame();
    const r = await api('/api/eden-restore', {tid, fichier});
    r.error || (toast('Restauration en cours…', 'ok'), this.poll());
  },

  async erApply(listingId, tid) {
    if (!CONN.kind) return toast('Connecte d\'abord la console.', 'warn');
    if (!confirm('Appliquer cette configuration communautaire à ce jeu ?\n\n' +
                 'Elle remplace la configuration actuelle du jeu dans Eden.\n' +
                 'L\'ancienne version est sauvegardée dans _eden-backup.')) return;
    this.closeGame();
    const r = await api('/api/emuready-apply', {listing_id: listingId, tid});
    r.error || (toast('Application en cours…', 'ok'), this.poll());
  },

  // ---- configuration d'Eden
  ecFillScope(jeux) {
    const sel = $('ec-scope');
    const avant = sel.value;
    const connus = new Map(GAMES.filter(g => g.tid).map(g => [g.tid.toUpperCase(), nomJeu(g)]));
    (jeux || []).forEach(t => { if (!connus.has(t.toUpperCase())) connus.set(t.toUpperCase(), t); });
    sel.innerHTML = '<option value="">Réglages globaux</option>' +
      [...connus.entries()].sort((a, b) => a[1].localeCompare(b[1]))
        .map(([t, n]) => '<option value="' + t + '">' + esc(n) + '</option>').join('');
    sel.value = avant || '';
  },
  async ecLoad() {
    ECTID = $('ec-scope').value || '';
    const r = await api('/api/eden-config', {tid: ECTID});
    if (r.error) return;
    this.ecFillScope(r.jeux);
    $('ec-scope').value = ECTID;
    renderEcTable(r.valeurs, r.existe);
    const pr = await api('/api/eden-profiles', {});
    renderEcProfiles(pr.profils || []);
  },
  _ecChanges() {
    const ch = {};
    $('ec-table').querySelectorAll('input[data-cle]').forEach(i => {
      const v = i.value.trim();
      if (!v) return;                                   // vide = ne pas toucher
      const actuel = (ECVALS[i.dataset.sec] || {})[i.dataset.cle];
      if (String(actuel) === v) return;                 // inchange
      (ch[i.dataset.sec] = ch[i.dataset.sec] || {})[i.dataset.cle] = v;
    });
    return ch;
  },
  async ecApply() {
    const ch = this._ecChanges();
    const n = Object.values(ch).reduce((s, o) => s + Object.keys(o).length, 0);
    if (!n) return toast('Aucune modification à appliquer.', 'warn');
    if (!CONN.kind) return toast('Connecte d\'abord la console.', 'warn');
    if (!confirm(phrase(
          'Appliquer %s réglage(s) %s ?\n\n'
          + 'L\'ancienne version est sauvegardée dans _eden-backup.',
          n, t(ECTID ? 'à ce jeu' : 'à la configuration globale')))) return;
    const r = await api('/api/eden-apply', {tid: ECTID, changements: ch});
    r.error || (toast('Application en cours…', 'ok'), this.poll());
  },
  async ecSaveProfile() {
    const nom = prompt('Nom du profil :', ECTID ? 'Profil jeu' : 'Profil global');
    if (!nom) return;
    const r = await api('/api/eden-profile-save',
      {nom, tid: ECTID, portee: ECTID ? 'jeu' : 'global',
       sections: EC_CLES.map(c => c[0]).filter((v, i, a) => a.indexOf(v) === i)});
    toast(phrase('Profil « %s » enregistré.', r.nom), 'ok');
    renderEcProfiles(r.profils || []);
  },
  async ecApplyProfile(nom) {
    if (!CONN.kind) return toast('Connecte d\'abord la console.', 'warn');
    if (!confirm(phrase('Appliquer le profil « %s » %s ?',
                        nom, t(ECTID ? 'à ce jeu' : 'globalement')))) return;
    const r = await api('/api/eden-profile-apply', {nom, tid: ECTID});
    r.error || (toast('Profil appliqué.', 'ok'), this.poll());
  },

  async loadNand() {
    const r = await api('/api/nand-status', {});
    NANDST = r.items || []; NANDCONN = !!r.connectee;
    renderLib();          // l'etat NAND nourrit la vue unifiee
  },




  // ---- console
  // ---- connexion sans fil
  togglePair() {
    // l'appairage vit dans les reglages : on y emmene l'utilisateur plutot que
    // de lui ouvrir un bloc qu'il ne verrait pas depuis la liste des jeux
    this.tab('settings');
    const w = $('pairwrap');
    const ouvre = w.style.display === 'none';
    w.style.display = ouvre ? '' : 'none';
    if (ouvre) { this.wizStep(1); w.scrollIntoView({block: 'center', behavior: 'smooth'}); }
  },
  // Assistant : une seule etape visible a la fois, chacune disant OU agir.
  wizStep(n) {
    for (let i = 1; i <= 3; i++) {
      const el = $('wstep' + i);
      if (el) el.classList.toggle('on', i === n);
    }
    const b = $('wizbar');
    if (b) b.style.width = Math.round(n / 3 * 100) + '%';
    if (n === 3) {
      this.wizCheck();
      this.wifiDiscover();               // pre-remplit l'adresse si elle est trouvable
      const a = $('pair-addr'); if (a && !a.value) a.focus();
    }
  },
  // Valide au fur et a mesure : l'utilisateur voit ce qui manque avant d'echouer.
  wizCheck() {
    const addr = ($('pair-addr').value || '').trim();
    const code = ($('pair-code').value || '').trim();
    const okAddr = /^\d{1,3}(\.\d{1,3}){3}:\d{2,5}$/.test(addr);
    const okCode = /^\d{6}$/.test(code);
    const msgs = [];
    if (addr && !okAddr) {
      msgs.push(phrase('L\'adresse doit ressembler à %s, port compris.',
                       '<code>192.168.1.42:37105</code>'));
    }
    if (code && !okCode) msgs.push('Le code fait exactement 6 chiffres.');
    const m = $('wizmsg');
    if (m) { m.innerHTML = msgs.join('<br>'); m.classList.toggle('on', msgs.length > 0); }
    const b = $('pairgo');
    if (b) b.disabled = !(okAddr && okCode);
    return okAddr && okCode;
  },
  async wifiSwitch() {
    say('Bascule en Wi-Fi…');
    const r = await api('/api/wifi-switch', {});
    if (r.ok) {
      toast(phrase('Wi-Fi activé (%s). Tu peux retirer le câble.', r.addr), 'ok');
      this.detect();
    }
    else toast(r.message || 'Bascule impossible.', 'err');
  },
  async wifiPair() {
    const addr = $('pair-addr').value.trim(), code = $('pair-code').value.trim();
    if (!addr || !code) return toast('Recopie l\'adresse et le code affichés sur la console.', 'warn');
    say('Association en cours…');
    const r = await api('/api/wifi-pair', {addr, code});
    if (r.ok && r.addr) {
      toast(r.message, 'ok'); $('pairwrap').style.display = 'none'; this.detect();
    } else if (r.ok) {
      toast('Associée, mais adresse de connexion introuvable — utilise « Chercher ».', 'warn');
      this.wifiDiscover();
    } else toast(r.message || 'Association refusée.', 'err');
  },
  async wifiDiscover() {
    const r = await api('/api/wifi-discover', {});
    const found = r.found || [];
    $('pairfound').innerHTML = found.length
      ? '<div class="card">' + found.map(a => '<div class="row"><span class="grow">' + esc(a) +
          '</span><button class="go" data-act="wifiConnect" data-arg="' + esc(a) + '">Connecter</button></div>').join('') + '</div>'
      : '<div class="mono" style="margin-top:8px">' +
        esc(t('Aucune console visible. Vérifie que le débogage sans fil est activé '
              + 'et que la console est sur le même réseau.')) + '</div>';
  },
  async wifiConnect(addr) {
    say('Connexion…');
    const r = await api('/api/wifi-connect', addr ? {addr} : {});
    if (r.ok) { toast('Console connectée sans fil.', 'ok'); $('pairwrap').style.display = 'none'; this.detect(); }
    else toast(r.message || 'Connexion impossible.', 'err');
  },
  async wifiForget() {
    if (!confirm('Oublier la connexion sans fil ?')) return;
    const r = await api('/api/wifi-forget', {});
    toast(r.message, 'ok'); this.detect();
  },

  // ---- ouvrir l'interface sur la console
  async refreshInstall() {
    const r = await api('/api/console-url', {});
    const wrap = $('installwrap');
    // Bouton compact de l'en-tete : le libelle reste court, l'explication passe
    // en infobulle. Desactive plutot que masque quand ce n'est pas encore pret,
    // pour que l'utilisateur sache que la fonction existe.
    if (!r.connected) { wrap.style.display = 'none'; return; }
    wrap.style.display = '';
    R.texte($('installurl'), r.url || '');
    const pret = !!(r.lan && r.url);
    wrap.disabled = !pret;
    R.texte($('installlead'), 'Sur la console');
    wrap.title = !r.lan
      ? 'Active « Accès depuis le téléphone » dans les Réglages pour piloter l\'outil depuis la console.'
      : !r.url
        ? 'Adresse réseau introuvable : vérifie la connexion Wi-Fi du serveur.'
        : phrase('Ouvrir cette interface sur l\'écran de la console (%s)', r.url);
  },
  // ---- premier lancement
  async checkHealth(force) {
    HEALTH = await api('/api/health', {});
    // Le plafond d'envoi vient du serveur : le figer dans le navigateur
    // signifierait mentir des que l'hebergeur le change.
    TELEVERSEMENT_MAX = ((HEALTH || {}).checks || {}).televersement_max || 0;
    const vu = localStorage.getItem('onboard-vu') === '1';
    renderChoixEmulateur();
    renderPied();
    majLudotheque();
    if (force || (HEALTH.first_run && !vu)) renderOnboard();
    return HEALTH;
  },
  // Depuis l'assistant : emmener l'utilisateur la ou se cree un compte, plutot
  // que de lui decrire le chemin.
  allerComptes() {
    this.closeOnboard();
    this.tab('settings');
    voirSectionReglages('sec-acces');
  },

  // Le profil d'emulateur dicte tous les chemins sur la console : le changer
  // depuis l'assistant evite d'avoir a le chercher dans les reglages avant
  // meme d'avoir compris a quoi il sert.
  async choisirEmulateur(cle) {
    await this.saveField('emulateur', cle);
    // Le nom du paquet Android differe d'une version a l'autre : on demande a
    // la console lequel est reellement installe, plutot que de le deviner.
    try { await api('/api/emulateur-detecter', {}); } catch (e) { /* console absente */ }
    await this.checkHealth(true);
  },

  // ---- assistant de premier demarrage ------------------------------------
  onbPrec() { onbAller(ONB.i - 1); },
  onbSuiv() { onbAller(ONB.i + 1); },
  onbAller(i) { onbAller(i); },

  // Compter les jeux par plateforme, c'est la seule facon de savoir si le
  // dossier indique est le bon. Un chemin accepte sans rien dedans est un
  // chemin faux qu'on ne decouvre qu'une heure plus tard.
  async onbScanner() {
    ONB.occupe = true; renderOnboard();
    let lib = {}, sys = {};
    try {
      [lib, sys] = await Promise.all([api('/api/scan'), api('/api/systems')]);
    } finally {
      ONB.occupe = false;
    }
    const stats = lib.stats || {};
    const plateformes = [];
    let total = 0;
    (sys.systems || []).forEach(x => {
      // Les jeux Switch ne sont pas comptes par `systems` : ils viennent de
      // l'inventaire, seul a savoir distinguer un jeu de sa mise a jour.
      const n = x.engine === 'switch' ? (stats.base || 0) : (x.count || 0);
      if (n > 0) { plateformes.push({nom: x.name, n: n}); total += n; }
    });
    plateformes.sort((a, b) => b.n - a.n);
    ONB.resultatScan = {
      total: total, plateformes: plateformes,
      extensions: (sys.extensions || []).length,
    };
    if (total) {
      DATA = lib; GAMES = groupGames(); renderLib();
    }
    renderOnboard();
  },

  async onbCreerCompte() {
    const mail = ($('onb-mail').value || '').trim();
    const mdp = $('onb-mdp').value || '';
    const msg = $('onb-mdp-msg');
    if (!mail || !mdp) {
      msg.textContent = t('Renseigne une adresse et un mot de passe.');
      return;
    }
    const r = await api('/api/compte-creer', {email: mail, mdp: mdp}, true);
    if (r.error) { msg.textContent = r.error; return; }
    toast('Compte administrateur créé.', 'ok');
    await this.checkHealth(true);
  },

  // Enregistrer sans verifier, c'est laisser l'utilisateur decouvrir dans un
  // mois que sa cle etait mal collee. On demande donc une jaquette tout de
  // suite, sur un jeu qu'il vient de scanner.
  async onbTesterFiches() {
    const sgdb = ($('onb-sgdb').value || '').trim();
    const cid = ($('onb-igdb-id').value || '').trim();
    const sec = ($('onb-igdb-secret').value || '').trim();
    ONB.testJaquettes = t('Vérification…');
    const msg = $('onb-fiches-msg');
    if (msg) msg.textContent = ONB.testJaquettes;
    if (sgdb) {
      await this.saveField('steamgriddb_key', sgdb);
      await this.saveField('cover_provider', 'steamgriddb');
    }
    if (cid) await this.saveField('igdb_client_id', cid);
    if (sec) await this.saveField('igdb_client_secret', sec);
    const dits = [];
    if (sgdb) {
      const r = await api('/api/sgdb-test', {}, true);
      dits.push('SteamGridDB : ' + (r.message || (r.ok ? t('clé acceptée') : t('refusée'))));
    }
    if (cid && sec) {
      const r = await api('/api/igdb-test', {}, true);
      dits.push('IGDB : ' + (r.ok ? t('accès accepté') : (r.message || t('refusé'))));
    }
    ONB.testJaquettes = dits.length ? dits.join(' — ')
      : t('Rien à vérifier : les deux champs sont vides.');
    renderOnboard();
  },

  // La connexion sans fil a deja son assistant complet dans les reglages : le
  // refaire ici en plus petit ne servirait qu'a en avoir deux a maintenir.
  // « Ce que la console contient deja » est la premiere question qu'on se pose
  // une fois branche, et la seule qui evite de reimporter ce qui y est deja.
  async onbScannerConsole() {
    ONB.occupe = true; renderOnboard();
    try {
      ONB.consoleScan = await api('/api/device-games', {});
    } finally {
      ONB.occupe = false;
    }
    renderOnboard();
  },

  async onbChercherConsole() {
    ONB.occupe = true; renderOnboard();
    let etat = {};
    try {
      etat = await api('/api/device');
      if (etat.state !== 'ok') {
        const dec = await api('/api/wifi-discover');
        const trouve = (dec.found || [])[0];
        if (trouve) await api('/api/wifi-connect', {addr: trouve});
      }
      etat = await api('/api/device');
      if (etat.state === 'ok') await api('/api/device-detect-dir', {});
    } finally {
      ONB.occupe = false;
    }
    if (etat.state === 'ok') toast('Console trouvée.', 'ok');
    else {
      this.closeOnboard();
      this.tab('settings');
      voirSectionReglages('sec-console');
      this.togglePair();
      return;
    }
    await this.checkHealth(true);
  },

  closeOnboard() {
    localStorage.setItem('onboard-vu', '1');
    $('onboard').classList.remove('open');
  },
  async showOnboard() { await this.checkHealth(true); },

  dismissA2HS() { localStorage.setItem('a2hs-off', '1'); renderA2HS(); },
  async installApp() {
    if (!INSTALL_EVT) return renderA2HS();
    INSTALL_EVT.prompt();
    const res = await INSTALL_EVT.userChoice.catch(() => null);
    INSTALL_EVT = null;
    if (res && res.outcome === 'accepted') toast('Installation lancée.', 'ok');
    renderA2HS();
  },

  // Une jaquette absente au premier essai (recherche en ligne en cours) est
  // retentee une fois avant d'abandonner : sinon elle ne revient jamais.
  coverRate(img) {
    // Une image cassee affiche la boite grise du navigateur avec son texte
    // alternatif — pendant les 2,5 s du reessai, la fiche montrait donc un
    // rectangle brise. On la cache tout de suite : le fond de `.cover` fait
    // deja office de pochette vide, comme dans la grille.
    img.classList.add('vide');
    if (img.dataset.retry) { img.remove(); return; }
    img.dataset.retry = '1';
    const base = img.src.split('&r=')[0];
    setTimeout(() => { img.src = base + '&r=1'; }, 2500);
  },

  // Une jaquette vient d'arriver : on en tire sa couleur si on ne la connait
  // pas encore, et on la pose sur la carte (ou sur la fiche). Le calcul est
  // fait une seule fois par jeu dans la vie du navigateur.
  // La jaquette de la fiche s'ouvre en grand. On passe par l'element plutot
  // que par une URL en dur : c'est la MEME image, deja chargee, donc
  // l'agrandissement est instantane.
  loupeJaquette(img) {
    if (!img || !img.src) return;
    const feuille = img.closest('.sheet');
    const titre = feuille ? (feuille.querySelector('h3') || {}).textContent : '';
    ouvrirLoupe(img.src, titre || '');
  },

  coverVue(img) {
    img.classList.remove('vide');
    const hote = img.closest('.gcard') || img.closest('.sheet');
    if (!hote) return;
    const cle = (hote.dataset.couleur || '').toLowerCase();
    if (!cle) return;
    let c = COULEURS[cle];
    if (!c) {
      c = couleurDominante(img);
      if (!c) return;
      COULEURS[cle] = c;
      rangerCouleurs();
    }
    hote.style.setProperty('--jaq', c);
  },

  toggleInstallHelp(e) {
    if (e) e.preventDefault();
    const h = $('installhelp');
    h.style.display = h.style.display === 'none' ? '' : 'none';
  },
  async openOnConsole() {
    const r = await api('/api/console-open', {});
    if (r.ok) toast('Navigateur ouvert sur la console.', 'ok');
    else toast(r.message || 'Ouverture impossible.', 'warn');
  },

  async detect() {
    say(t('Détection de la console...'));
    const d = await api('/api/device');
    renderConn(d); this.refreshInstall();
    renderDeviceCard(d.info || {}, d.volumes || []);
    if (d.info && d.info.connected) {
      annonce(phrase('Console détectée : %s', d.info.name), 'ok');
      await this.chargerConsole();
    } else {
      // Assemblee, la phrase n'etait traduisible par aucun catalogue.
      annonce(phrase('Aucune console prête (%s).', d.state || t('non connectée')), 'warn');
    }
  },

  // Lire ce que porte la console passe TOUJOURS par ici. Deux appels qui se
  // chevauchent partagent la meme promesse au lieu de relancer la lecture :
  // c'est ce qui produisait « 148 fichier(s)… » trois fois de suite.
  chargerConsole() {
    if (this._lectureConsole) return this._lectureConsole;
    this._lectureConsole = (async () => {
      try {
        if (DATA.config && DATA.config.device_dir) await this.explore();
        else await this.detectDir();   // aucun dossier connu : on le cherche
        await this.loadNand();         // l'etat NAND n'a de sens qu'une fois connecte
      } finally {
        this._lectureConsole = null;
      }
    })();
    return this._lectureConsole;
  },
  refreshConsole() { this.explore(); },
  async saveConfig(patch) {
    const r = await api('/api/config', patch);
    if (r.config) {
      DATA.config = r.config;
      fillSettings();
      renderLib();
      majReglagesPlateforme();     // le dossier affiche vient de la configuration
    }
    return r.config;
  },
  async detectDir() {
    say('Recherche du dossier de jeux...');
    const r = await api('/api/device-detect-dir', {});
    if (!r.dir) return toast('Aucun dossier trouvé. Utilise « changer » pour naviguer.', 'warn');
    const actuel = (DATA.config || {}).device_dir;
    // Ne jamais remplacer en silence un dossier deja choisi : une detection
    // approximative a deja efface un reglage correct.
    if (actuel && actuel !== r.dir) {
      return dialogue({
        titre: 'Changer le dossier des jeux ?',
        niveau: 'warn',
        message: 'La détection propose un autre dossier que celui enregistré.',
        detail: phrase('actuel : %s\ntrouvé : %s', actuel, r.dir),
        fermer: 'Garder l\'actuel',
        actions: [{libelle: 'Utiliser celui trouvé', principal: true, faire: async () => {
          await this.saveConfig({device_dir: r.dir});
          BROWSE_PATH = r.dir; this.explore();
        }}],
      });
    }
    await this.saveConfig({device_dir: r.dir});
    BROWSE_PATH = r.dir;
    toast(phrase('Dossier des jeux trouvé : %s', r.dir), 'ok');
    this.explore();
  },
  // Le meme navigateur sert a choisir la racine des ROMs, le dossier Switch ou
  // celui de n'importe quelle plateforme : seule la CIBLE change.
  parcourir(cible, depart) {
    CIBLE_PARCOURS = cible || 'roms';
    const w = $('browserwrap');
    w.style.display = '';
    R.texte($('browsecible'), {
      roms: 'Choisir la racine des ROMs',
      switch: 'Choisir le dossier des jeux Switch',
    }[CIBLE_PARCOURS] ||
      phrase('Choisir le dossier de %s', libelleSysteme(CIBLE_PARCOURS)));
    this.browse(depart || BROWSE_PATH || (DATA.config || {}).roms_root
                || (DATA.config || {}).device_dir);
    w.scrollIntoView({block: 'center', behavior: 'smooth'});
  },

  async browse(path) {
    path = (path || BROWSE_PATH || (DATA.config && DATA.config.device_dir) || '/storage/emulated/0');
    BROWSE_PATH = path.replace(/\/+$/, '') || '/';
    say(phrase('Lecture de %s…', BROWSE_PATH));
    const r = await api('/api/device-browse', {path: BROWSE_PATH});
    if (!r.error) renderBrowser(BROWSE_PATH, r.items || []);
  },
  bup() { const p = BROWSE_PATH.replace(/\/+$/, ''); this.browse(p.substring(0, p.lastIndexOf('/')) || '/'); },
  async useDir() {
    if (!BROWSE_PATH) return toast('Ouvre d\'abord un dossier.', 'warn');
    if (CIBLE_PARCOURS === 'roms') {
      await this.saveField('roms_root', BROWSE_PATH);
      toast(phrase('Racine des ROMs : %s', BROWSE_PATH), 'ok');
    } else if (CIBLE_PARCOURS === 'switch') {
      await this.saveConfig({device_dir: BROWSE_PATH});
      toast(phrase('Dossier Switch : %s', BROWSE_PATH), 'ok');
      this.explore();
    } else {
      // chemin absolu : il prime sur le nom de sous-dossier deduit de la racine
      const dirs = Object.assign({}, (DATA.config || {}).system_dirs || {});
      dirs[CIBLE_PARCOURS] = BROWSE_PATH;
      await this.saveField('system_dirs', dirs);
      toast(libelleSysteme(CIBLE_PARCOURS) + ' : ' + BROWSE_PATH, 'ok');
    }
    $('browserwrap').style.display = 'none';
    majReglagesPlateforme();       // le chemin affiche suit immediatement
    this.detecterPlateformes();
  },
  setDpath(p) { BROWSE_PATH = p; this.tab('settings'); $('browserwrap').style.display = ''; this.browse(p); },

  // ---- ou sont les jeux, sur la machine qui heberge le service
  ludoOuvrir(depart) {
    if (HEALTH && HEALTH.ludotheque_imposee) {
      return toast(t('Imposé par la variable ROMULE_LIBRARY.'), 'warn');
    }
    LUDO.cible = 'set';
    const w = $('ludowrap');
    w.hidden = false;
    this.ludoAller(depart || (HEALTH && HEALTH.ludotheque) || '');
    w.scrollIntoView({block: 'center', behavior: 'smooth'});
  },
  ludoFermer() { $('ludowrap').hidden = true; },
  async ludoAller(chemin) {
    const r = await api('/api/parcourir', {chemin: chemin || ''}, true);
    if (r.error) {
      // Discret volontairement : se heurter a un dossier interdit en navigant
      // est banal, et ouvrir une fenetre d'erreur a chaque clic serait pire
      // que le probleme.
      if (LUDO.cible === 'onb') return toast(r.error, 'warn');
      $('ludoetat').textContent = r.error;
      return;
    }
    if (LUDO.cible === 'onb') {
      LUDO.etat = r; LUDO.chemin = r.chemin || '';
      return renderOnboard();
    }
    renderLudo(r);
  },
  onbChoisirDossier() {
    LUDO.cible = 'onb';
    this.ludoAller((HEALTH && HEALTH.ludotheque) || '');
  },
  ludoAnnulerOnb() { LUDO.cible = 'set'; LUDO.etat = null; renderOnboard(); },
  async ludoValider(creer) {
    if (!LUDO.chemin) return toast(t('Ouvre d\'abord un dossier.'), 'warn');
    const r = await api('/api/ludotheque', {chemin: LUDO.chemin, creer: !!creer});
    if (r.error) return;
    HEALTH = await api('/api/health', {});
    majLudotheque();
    this.ludoFermer();
    // La reponse PORTE deja l'inventaire du nouveau dossier : relancer
    // `/api/scan` ici, c'est parcourir deux fois une arborescence qui peut
    // faire plusieurs teraoctets.
    DATA = r;
    render();
    this.loadTrash();
    await this.loadSystems();
    annonce(phrase('Ludothèque : %s — %d jeu(x).', LUDO.chemin,
                   (r.files || []).length), 'ok');
    if (LUDO.cible === 'onb') {
      // Le resultat d'analyse portait sur l'ANCIEN dossier : le garder
      // validerait l'etape avec un chiffre qui ne correspond plus a rien.
      LUDO.cible = 'set'; LUDO.etat = null; ONB.resultatScan = null;
      renderOnboard();
    }
  },
  async ludoNouveau() {
    if (!LUDO.chemin) return toast(t('Ouvre d\'abord un dossier.'), 'warn');
    const nom = prompt(t('Nom du nouveau dossier :'), 'Romule');
    if (!nom) return;
    // Un nom, pas un chemin : la saisie ne doit pas servir a remonter
    // l'arborescence. Le serveur refuserait, mais autant ne pas le proposer.
    const propre = String(nom).replace(/[\\/]/g, '').trim();
    if (!propre) return;
    LUDO.chemin = LUDO.chemin.replace(/\/+$/, '') + '/' + propre;
    await this.ludoValider(true);
  },
  async explore() {
    const root = (DATA.config && DATA.config.device_dir) || '';
    if (!root) return toast('Le dossier des jeux n\'est pas defini (bouton « changer le dossier »).', 'warn');
    say('Lecture des jeux de la console...');
    const r = await api('/api/device-games', {root});
    if (r.error) return;
    DGAMES = r.games || []; buildConset();
    renderLib(); this.checkTree();
    annonce(phrase('%d fichier(s) sur la console, %d absent(s) du serveur.',
               r.total, r.new),
            r.total ? 'ok' : 'warn');
  },
  async checkTree() {
    if (!(DATA.config && DATA.config.device_dir)) { TREE = {}; renderTree(); return; }
    const r = await api('/api/device-tree', {}); TREE = r.tree || {}; renderTree();
  },
  async mkTree() {
    const r = await api('/api/device-mktree', {}); TREE = r.tree || {}; renderTree();
    toast('Dossiers GAMES / UPDATE / DLC créés sur la console.', 'ok');
  },
  async organize() {
    if (!confirm('Ranger les jeux déjà sur la console dans GAMES / UPDATE / DLC ?\nChaque jeu, mise à jour et DLC sera classé par type ; les dossiers vides seront supprimés.')) return;
    const r = await api('/api/device-organize', {});
    r.error || (toast('Rangement en cours…', 'ok'), this.poll());
  },

  // ---- selection et action principale
  // Un clic sur une carte coche le jeu s'il reste quelque chose a lui faire,
  // sinon il ouvre sa fiche : le meme geste ne fait jamais deux choses au hasard.
  // Clic = cocher. Maj+clic = cocher toute la plage depuis le dernier clic,
  // comme dans un explorateur de fichiers. La fiche s'ouvre par « Détails ».
  cardClick(ev, key) {
    if (ev && ev.shiftKey && DERNIER_CLIC) {
      const a = VUS_PAGE.indexOf(DERNIER_CLIC), b = VUS_PAGE.indexOf(key);
      if (a >= 0 && b >= 0) {
        const on = !dsel2.has(key);
        VUS_PAGE.slice(Math.min(a, b), Math.max(a, b) + 1)
          .forEach(k => on ? dsel2.add(k) : dsel2.delete(k));
        DERNIER_CLIC = key;
        renderLib();
        return;
      }
    }
    DERNIER_CLIC = key;
    this.deployToggle(key, !dsel2.has(key));
  },
  // Cocher un jeu ne doit toucher QUE sa carte. Redessiner toute la liste
  // rejouait l'animation d'entree des dizaines de vignettes : visuellement,
  // on croyait la page rechargee a chaque clic.
  // Plus de mise a jour manuelle du DOM : renderLib() reconcilie, donc cocher
  // ne touche que la carte concernee, sans reconstruire ni ranimer la grille.
  deployToggle(key, on) {
    on ? dsel2.add(key) : dsel2.delete(key);
    renderLib();
  },
  page(d) { PAGE = Math.max(0, PAGE + d); renderLib(); window.scrollTo({top: 0, behavior: 'smooth'}); },
  setTri(v) { TRI = v; localStorage.setItem('tri', v); PAGE = 0; renderLib(); },
  setTaille(v) { TAILLE = v; localStorage.setItem('taille', v); PAGE = 0; renderLib(); },
  setParPage(v) {
    PARPAGE = parseInt(v, 10) || 0;
    localStorage.setItem('parpage', String(PARPAGE));
    PAGE = 0; renderLib();
  },

  // Retirer des fichiers de la console : action destructrice, donc on montre
  // exactement ce qui part avant de demander confirmation.
  async supprimerConsole() {
    const {supprConsole} = deployCibles();
    if (!supprConsole.length) return toast('Rien à retirer de la console.', 'warn');
    dialogue({
      titre: phrase('Retirer %d fichier(s) de la console ?', supprConsole.length),
      niveau: 'warn',
      message: 'Ces fichiers seront supprimés de la console. Tes copies sur le serveur ne sont pas touchées.',
      detail: supprConsole.slice(0, 20).map(p => p.split('/').pop()).join('\n') +
              (supprConsole.length > 20 ? '\n… et ' + (supprConsole.length - 20) + ' autre(s)' : ''),
      fermer: 'Annuler',
      actions: [{libelle: 'Retirer', principal: true, faire: async () => {
        const r = await api('/api/device-remove', {paths: supprConsole});
        if (!r.error) { dsel2.clear(); toast('Suppression lancée.', 'ok'); this.poll(); }
      }}],
    });
  },
  // Corbeille locale : rien n'est efface, tout reste restaurable.
  async corbeilleSelection() {
    const {local} = deployCibles();
    if (!local.length) return toast('Rien à mettre à la corbeille.', 'warn');
    dialogue({
      titre: phrase('Mettre %d fichier(s) à la corbeille ?', local.length),
      niveau: 'warn',
      message: 'Ils quittent la bibliothèque mais restent dans _corbeille/, restaurables à tout moment.',
      detail: local.slice(0, 20).map(p => p.split('/').pop()).join('\n') +
              (local.length > 20 ? '\n… et ' + (local.length - 20) + ' autre(s)' : ''),
      fermer: 'Annuler',
      actions: [{libelle: 'Mettre à la corbeille', principal: true, faire: async () => {
        const r = await api('/api/trash', {paths: local});
        if (!r.error) { dsel2.clear(); toast(r.message || 'Déplacé.', 'ok'); this.scan(); }
      }}],
    });
  },
  // « Tout cocher » porte sur l'ensemble des resultats filtres, pas seulement
  // sur la page visible : sinon le geste ment des qu'il y a une pagination.
  // Les versions d'un jeu ont leur propre fenetre. Elle passe par `#dialog` et
  // non par `#modal` : ouvrir la fiche d'une version depuis la liste doit
  // pouvoir se poser PAR-DESSUS, et Echap refermer l'une puis l'autre.
  voirVersions(cle) {
    const membres = GROUPES.get(cle);
    if (!membres || !membres.length) return;
    const el = $('dialog');
    const titre = nomJeu(representantGroupe(membres).g);
    el.innerHTML =
      '<div class="sheet dlg d-info" data-interieur>' +
        '<div class="dlghead"><h3>' + esc(titre) + '</h3>' +
          '<span class="mono">' + membres.length + ' versions</span></div>' +
        '<div class="versions">' + membres.map(x => ligneVersion(x)).join('') +
        '</div>' +
        '<div class="acts"><button class="ghost" data-act="closeDialog">' +
          'Fermer</button></div>' +
      '</div>';
    el.classList.remove('ferme');
    el.classList.add('open');
    auPremierPlan(el);
    traduireDOM(el);
  },

  deployPick(all) {
    dsel2.clear();
    DERNIER_CLIC = null;
    if (all) jeuxFiltres(jeuxUnifies()).forEach(({g}) => dsel2.add(g.key));
    renderLib();
  },
  setSens() { SENS = -SENS; localStorage.setItem('sens', String(SENS)); PAGE = 0; renderLib(); },
  toggleFav(k) {
    FAV.has(k) ? FAV.delete(k) : FAV.add(k);
    localStorage.setItem('fav', JSON.stringify([...FAV]));
    PAGE = 0; renderLib();
  },
  clearFav() { FAV.clear(); localStorage.removeItem('fav'); PAGE = 0; renderLib(); },
  toggleFavPop(e) {
    if (e) e.stopPropagation();
    $('favpop').classList.toggle('on');
  },
  // Un seul bouton « Actualiser » : relire le serveur ET la console. Avoir cinq
  // rafraichissements differents obligeait a deviner lequel repondait a quoi.
  // « Actualiser » ne relisait que la bibliotheque Switch : sur une autre
  // plateforme, ou en vue « toutes les plateformes », le bouton semblait ne
  // rien faire. Il relit maintenant ce qui est REELLEMENT a l'ecran.
  async actualiser() {
    oublierCacheSysteme();                        // c'est le geste qui dit « relis »
    await this.scan();                            // fichiers du serveur
    if (CONN.kind) {
      await this.explore();                       // ce qui est deja sur la console
      await this.loadNand();                      // ce qui est actif dans Eden
    }
    await this.setSystem(SYS);                    // la liste affichee, quelle qu'elle soit
    renderLib();
    toast('À jour.', 'ok');
  },

  // Rafraichir les FICHES : titres, resumes, jaquettes. C'est une operation
  // reseau, distincte de la relecture des fichiers.
  async actualiserFiches(force) {
    if (force) {
      const r = await api('/api/meta-oublier', {}, true);
      if (r && r.error) return toast(r.error, 'warn');
    }
    const r = await api('/api/meta-sync', {});
    if (r && r.error) return;
    toast(force ? 'Toutes les fiches vont être retéléchargées.'
                : 'Recherche des fiches manquantes…', 'ok');
    this.basculerTaches(true);
    this.poll();
  },
  // Une seule action principale, quel que soit le sens du transfert : l'outil
  // deduit de la selection ce qu'il faut faire, et le montre avant de lancer.
  async appliquer() { return isSwitch() ? this.deploy() : this.sendSystem(); },

  async deploy() {
    if (!dsel2.size) return toast('Coche au moins un jeu.', 'warn');
    if (!CONN.kind) return toast('Connecte d\'abord la console.', 'warn');
    const {envoyer, activer, importer} = deployCibles();

    // configurations recommandees disponibles pour les jeux selectionnes
    const configs = [];
    if (ER.actif) {
      GAMES.forEach(g => {
        if (!dsel2.has(g.key) || !g.tid) return;
        const e = ER.jeux[g.tid.toLowerCase()];
        if (e && e.meilleur) configs.push({tid: g.tid, listing_id: e.meilleur.id,
                                           jeu: nomJeu(g), note: e.meilleur.note});
      });
    }
    const poids = GAMES.filter(g => dsel2.has(g.key))
      .reduce((s, g) => s + etatDuJeu(g, nandParChemin()).taille, 0);

    if (!envoyer.length && !activer.length && !configs.length && !importer.length)
      return toast('Ces jeux sont déjà complets sur la console.', 'warn');

    // Une seule fenetre : tout ce qui va se passer, modifiable avant de lancer.
    const options = [];
    if (importer.length) options.push({id: 'importer', coche: true,
      libelle: 'Copier vers le serveur les jeux qui n\'y sont pas',
      detail: phrase('%d fichier(s) depuis la console', importer.length)});
    if (envoyer.length) options.push({id: 'fichiers', coche: true,
      libelle: 'Copier les fichiers de jeu',
      detail: nb(envoyer.length, 'fichier(s)') + ' · ' + fmt(poids)});
    if (activer.length) options.push({id: 'activer', coche: true,
      libelle: 'Activer les mises à jour et DLC dans Eden',
      detail: phrase('%s élément(s) — sans ça ils resteraient inactifs',
                     activer.length)});
    if (configs.length) options.push({id: 'config', coche: false,
      libelle: 'Appliquer les réglages recommandés (EmuReady)',
      detail: phrase('%d jeu(x) :', configs.length) + ' '
              + configs.slice(0, 2).map(c => c.jeu + ' (' + c.note + ')').join(', ')
              + (configs.length > 2 ? '…' : '')
              + t(' — remplace leur configuration actuelle')});
    if (!options.length) return toast('Rien à faire sur ces jeux.', 'warn');

    dialogue({
      titre: phrase('Traiter %d jeu(x)', dsel2.size),
      niveau: 'info',
      message: 'Choisis ce que l\'outil doit faire. Tout est sauvegardé avant écriture.',
      options,
      fermer: 'Annuler',
      actions: [{libelle: 'Lancer', principal: true, faire: async (c) => {
        let lance = false;
        if (c.importer && importer.length) {
          const ri = await api('/api/device-import', {paths: importer, convert: true});
          if (!ri.error) lance = true;
        }
        if (c.fichiers || c.activer || c.config) {
          const r = await api('/api/deploy', {
            envoyer: c.fichiers ? envoyer : [],
            activer: c.activer ? activer : [],
            configs: c.config ? configs.map(x => ({tid: x.tid, listing_id: x.listing_id})) : [],
          });
          if (!r.error) lance = true;
        }
        if (lance) { dsel2.clear(); toast('Traitement lancé.', 'ok'); this.poll(); }
      }}],
    });
  },

  clearManifest() { const m = $('manifest'); if (m) m.innerHTML = ''; },

  // ---- reglages
  // Enregistre un seul reglage : impossible d'effacer les autres par erreur.
  async saveField(cle, valeur) {
    const avant = (DATA.config || {})[cle];
    const r = await api('/api/config', {[cle]: valeur});
    if (!r.config) return;
    DATA.config = r.config;
    const imagesTouchees = ['cover_provider', 'steamgriddb_key', 'cover_url', 'meta_lang'];
    if (imagesTouchees.includes(cle) && avant !== valeur) {
      await api('/api/covers-clear', {});
      GAMES = groupGames(); renderLib();
    }
    if (cle === 'device_dir') { majReglagesPlateforme(); this.checkTree(); }
    if (cle === 'push_layout' || cle === 'device_dir') { renderTree(); renderLib(); }
    if (cle === 'lan_access') this.refreshInstall();
    if (cle === 'emuready') { ER.actif = !!valeur; this.erLoad(); this.erDevices(); }
    this.flashSaved();
  },
  // La confirmation vit dans le sommaire, qui est colle : au bas d'une page de
  // 5 000 px, personne ne la voyait. Au repos elle n'affiche rien — le chapeau
  // dit deja que tout s'enregistre au fur et a mesure.
  flashSaved() {
    const h = $('savehint');
    if (!h) return;
    R.texte(h, 'Enregistré ✓');
    R.classe(h, 'okflash', true);
    clearTimeout(this._saveT);
    this._saveT = setTimeout(() => {
      R.texte(h, '');
      R.classe(h, 'okflash', false);
    }, 2200);
  },

  async saveSettings(silent) {
    const c = DATA.config || {};
    // device_dir n'est volontairement PAS dans ce corps : il se choisit par le
    // navigateur de la console (useDir). L'inclure ici a deja permis de l'effacer
    // avec une valeur vide au chargement, avant que la config ne soit lue.
    const body = {
      jobs: Math.max(1, parseInt($('s-jobs').value, 10) || 3),
      push_layout: $('s-layout').value || 'type',
      local_layout: $('s-local').value || 'type',
      verify_mode: $('s-verify').value || 'size',
      cover_provider: $('s-coverprov').value || 'nlib',
      steamgriddb_key: $('s-sgkey').value.trim(),
      meta_lang: $('s-lang').value,
      incremental: $('s-incr').checked,
      cover_url: $('s-cover').value.trim(),
      versions_urls: $('s-mirrors').value.split('\n').map(s => s.trim()).filter(Boolean),
      lan_access: $('s-lan').checked,
      notify: $('s-notify').checked,
      roms_root: $('s-romsroot').value.trim(),
      saves_dir: $('s-savesdir').value.trim(),
    };
    const coversChanged = body.cover_provider !== c.cover_provider ||
      body.steamgriddb_key !== c.steamgriddb_key || body.cover_url !== c.cover_url ||
      body.meta_lang !== c.meta_lang;
    const r = await api('/api/config', body);
    if (!r.config) return;
    DATA.config = r.config; fillSettings(); this.refreshInstall();
    if (coversChanged) { await api('/api/covers-clear', {}); GAMES = groupGames(); renderLib(); }
    const h = $('savehint');
    if (h) {
      h.textContent = 'Enregistré ✓';
      clearTimeout(this._saveT);
      this._saveT = setTimeout(() => { h.textContent = 'Les modifications sont enregistrées automatiquement.'; }, 2200);
    }
    if (!silent) toast('Réglages enregistrés.', 'ok');
  },
  async reorganizeLocal() {
    if (!confirm('Réorganiser toute la bibliothèque locale en GAMES / UPDATE / DLC ?\nLes fichiers seront déplacés sur le serveur.')) return;
    const r = await api('/api/reorganize-local', {});
    r.error || (toast('Réorganisation en cours…', 'ok'), this.poll());
  },
  // Les fiches manquantes se telechargent a la demande : l'affichage ne doit
  // jamais attendre le reseau, et changer de langue en redemande de nouvelles.
  // Plug & play : une seule lecture de la console dit ce qu'elle heberge.
  // L'utilisateur n'a plus a connaitre les noms de dossiers attendus.
  // depuis les Reglages, aller voir les jeux d'une plateforme
  // Le clic sur une plateforme la DETAILLE ; c'est un bouton dedie qui emmene
  // vers la bibliotheque. Rediriger d'office privait l'utilisateur des reglages
  // propres a cette plateforme.
  // Une plateforme detectee amene a SES reglages, plus haut dans la page.
  // Auparavant elle ouvrait un second editeur de dossier : le meme reglage a
  // deux endroits, donc deux valeurs pouvant differer a l'ecran.
  ouvrirPlateforme(key) {
    if (!key) return;
    PF_OUVERTE = key;
    document.querySelectorAll('.pfcarte').forEach(b =>
      R.classe(b, 'on', b.getAttribute('onclick').includes("'" + key + "'")));
    this.choisirPlateformeReglages(key);
    const sel = $('s-plateforme');
    if (sel) sel.value = key;
    if (key === 'switch') this.checkTree();
    const cible = $('groupe-console');
    if (cible) cible.scrollIntoView({behavior: 'smooth', block: 'start'});
  },
  // Revenir au dossier deduit de la racine des ROMs.
  async oublierDossier(key) {
    const dirs = Object.assign({}, (DATA.config || {}).system_dirs || {});
    delete dirs[key];
    await this.saveField('system_dirs', dirs);
    toast('Dossier par défaut rétabli.', 'ok');
    this.detecterPlateformes();
  },
  allerSysteme(key) {
    this.tab('jeux');
    $('sysel').value = key;
    this.setSystem(key);
  },
  // Analyse complete : elle passe par le systeme de taches, donc barre de
  // progression et journal detaille — on voit CE QUI a ete cherche, et ou.
  async analyseGlobale() {
    const r = await api('/api/console-analyse', {});
    if (r.error) return;
    toast('Analyse lancée.', 'ok');
    await this.poll();
    this.detecterPlateformes(true);
  },

  // Declarer une plateforme absente de la table livree.
  ajouterPlateforme() {
    dialogue({
      titre: 'Ajouter une plateforme',
      niveau: 'info',
      message: 'Pour une console absente de la liste, ou rangée d\'une façon '
             + 'que l\'outil ne devine pas.',
      champs: [
        {id: 'nom', libelle: 'Nom affiché', exemple: 'Neo Geo'},
        {id: 'dossier', libelle: 'Dossier sur la console', exemple: 'NeoGeo'},
        {id: 'exts', libelle: 'Extensions, séparées par des virgules', exemple: 'zip, neo'},
      ],
      fermer: 'Annuler',
      actions: [{libelle: 'Ajouter', principal: true, faire: async (v) => {
        const nom = (v.nom || '').trim();
        const dossier = (v.dossier || '').trim().replace(/^\/+|\/+$/g, '');
        const exts = (v.exts || '').split(',').map(x => x.trim().replace(/^\./, ''))
                       .filter(Boolean);
        if (!nom || !dossier || !exts.length)
          return toast('Nom, dossier et au moins une extension sont nécessaires.', 'warn');
        const cle = nom.toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 20) || 'perso';
        const liste = ((DATA.config || {}).systemes_perso || []).slice();
        if (liste.some(x => x.key === cle)) return toast('Cette plateforme existe déjà.', 'warn');
        liste.push({key: cle, name: nom, folder: dossier, exts});
        await this.saveField('systemes_perso', liste);
        toast(phrase('%s ajoutée.', nom), 'ok');
        await this.loadSystems();
        this.detecterPlateformes();
      }}],
    });
  },

  async detecterPlateformes(silencieux) {
    if (!silencieux) say('Lecture des plateformes de la console…');
    const r = await api('/api/systems-detect', {});
    if (r.error) return;
    renderPlateformes(r);
    renderSysSelect();                 // les compteurs en dependent
    if (silencieux) return;
    if (r.plateformes && r.plateformes.length)
      annonce(phrase('%s plateforme(s) trouvée(s).', r.plateformes.length), 'ok');
    else annonce('Aucune plateforme trouvée sous ce dossier.', 'warn');
    this.loadSystems();
  },
  // L'audit dit ce qui protege l'installation ET ce qui ne la protege pas :
  // les deux comptent, donc on affiche aussi les controles reussis.
  async auditer(horsLigne) {
    const boite = $('auditres');
    R.texte(boite, 'Audit en cours...');
    const r = await api('/api/audit', {hors_ligne: !!horsLigne}, true);
    if (!r || r.error) { R.texte(boite, r && r.error || 'Audit indisponible.'); return; }
    const rang = {grave: 0, alerte: 1, info: 2, bon: 3};
    const libelle = {grave: 'Grave', alerte: 'À regarder', info: 'Pour info', bon: 'Conforme'};
    boite.innerHTML = '<div class="auditliste">'
      + r.controles.slice().sort((a, b) => rang[a.niveau] - rang[b.niveau]).map(c =>
        '<div class="auditc a-' + c.niveau + '">'
        + '<span class="auditn">' + esc(libelle[c.niveau]) + '</span>'
        + '<div><b>' + esc(c.titre) + '</b>'
        + '<div class="odesc">' + esc(c.constat) + '</div>'
        + (c.remede ? '<div class="oaide">' + esc(c.remede) + '</div>' : '')
        + '</div></div>').join('')
      + '</div>';
    const n = r.resume.grave + r.resume.alerte;
    toast(n ? phrase('%d point(s) à regarder.', n) : t('Rien à signaler.'),
          n ? 'warn' : 'ok');
  },

  // Gestion des comptes internes : les fonctions vivent plus haut, avec le
  // reste de la logique d'authentification.
  // IGDB : on verifie AVANT de lancer une recuperation de fiches, sinon
  // l'echec n'apparait qu'au milieu d'une tache longue.
  async testerIgdb() {
    const b = $('igdbtest');
    R.texte(b, 'Vérification…');
    const r = await api('/api/igdb-test', {}, true);
    if (!r || !r.ok) {
      R.texte(b, (r && (r.message || r.error)) || 'Vérification impossible.');
      R.classe(b, 'avert', true);
      return;
    }
    R.classe(b, 'avert', false);
    R.texte(b, phrase('Identifiants valides — exemple retrouvé : %s',
                      r.infos.exemple));
  },

  // Entretien : chaque volet repond a UNE question, et n'agit jamais tout
  // seul. Voir n'est pas decider.
  async voirEntretien(quoi) {
    const b = $('entretien');
    document.querySelectorAll('.entretien button').forEach(x =>
      R.classe(x, 'on', x.getAttribute('onclick').includes("'" + quoi + "'")));
    R.texte(b, 'Lecture…');
    const rendus = {
      doublons: renduDoublons, integrite: renduIntegrite,
      sauvegardes: renduSauvegardes, acces: renduAcces, transfert: renduTransfert,
    };
    const routes = {
      doublons: '/api/doublons', integrite: '/api/integrite',
      sauvegardes: '/api/sauvegardes', acces: '/api/acces',
      transfert: '/api/transfert-etat',
    };
    const r = await api(routes[quoi], {}, true);
    if (!r || r.error) return R.texte(b, (r && r.error) || 'Lecture impossible.');
    b.innerHTML = rendus[quoi](r);
  },

  async sauvegarder() {
    const r = await api('/api/sauvegarde-creer', {}, true);
    if (r && r.error) return toast(r.error, 'warn');
    toast((r && r.message) || 'Sauvegardé.', 'ok');
    this.voirEntretien('sauvegardes');
  },

  restaurerSauvegarde(lot) {
    dialogue({
      titre: 'Restaurer ' + lot + ' ?',
      niveau: 'warn',
      message: 'Les réglages et les comptes actuels seront remplacés. '
             + "L'état présent est sauvegardé juste avant, donc rien n'est perdu.",
      actions: [{libelle: 'Restaurer', principal: true, faire: async () => {
        const r = await api('/api/sauvegarde-restaurer', {lot}, true);
        if (r && r.error) return toast(r.error, 'warn');
        toast(r.message, 'ok');
        await app.scan();
        app.voirEntretien('sauvegardes');
      }}],
      fermer: 'Annuler',
    });
  },

  async reprendreTransfert() {
    const r = await api('/api/transfert-reprendre', {}, true);
    if (r && r.error) return toast(r.error, 'warn');
    toast('Reprise lancée.', 'ok');
    this.poll();
  },

  async oublierTransfert() {
    await api('/api/transfert-oublier', {}, true);
    this.voirEntretien('transfert');
  },

  // Certaines extensions ne designent pas une plateforme (.iso : PS2, Wii,
  // Xbox…). Plutot que de laisser ces fichiers dormir dans le depot, on demande
  // — une seule fois, pour tous les fichiers concernes.
  async classerImports(silencieux) {
    const r = await api('/api/import-suggestions', {}, true);
    const items = (r && r.items) || [];
    if (!items.length) {
      if (!silencieux) toast('Rien à classer : tout a trouvé sa plateforme.', 'ok');
      return;
    }
    ouvrirChoixPlateforme(items);
  },

  // Choisir dans le Finder : le glisser-deposer ne convient pas a tout le
  // monde, et sur telephone il n'existe pas.
  choisirFichiers() {
    const f = document.createElement('input');
    f.type = 'file';
    f.multiple = true;
    f.accept = EXTS_ACCEPTEES.join(',');
    f.onchange = () => { if (f.files && f.files.length) uploadFiles(f.files); };
    f.click();
  },

  basculerSuivi() {
    JSUIVI = !JSUIVI;
    majBoutonSuivi();
    if (JSUIVI) { const el = $('log'); el.scrollTop = el.scrollHeight; }
  },

  // Tout reprendre est destructif pour le cache : on le dit avant.
  forcerFiches() {
    dialogue({
      titre: 'Tout retélécharger ?',
      niveau: 'warn',
      message: "Les fiches actuelles seront oubliées et reprises depuis zéro. "
             + 'Utile si les descriptions sont dans la mauvaise langue ou fausses ; '
             + 'compter quelques minutes pour une grande ludothèque.',
      actions: [{libelle: 'Tout retélécharger', principal: true,
                 faire: () => app.actualiserFiches(true)}],
      fermer: 'Annuler',
    });
  },

  // Aller a une lettre : la pagination complique les choses, car la lettre
  // visee n'est pas forcement sur la page courante. On change donc de page
  // AVANT de faire defiler, sinon le clic ne menait nulle part.
  allerLettre(lettre) {
    const rang = ALPHA_POS.get(lettre);
    if (rang == null) return;
    const parPage = PARPAGE || 1e9;
    const page = Math.floor(rang / parPage);
    const dansLaPage = rang - page * parPage;
    const bouger = () => {
      const cartes = document.querySelectorAll('#lib .gcard');
      const cible = cartes[dansLaPage];
      if (!cible) return;
      cible.scrollIntoView({behavior: 'smooth', block: 'start'});
      // Un repere visuel bref : sans lui, on ne sait pas laquelle des dix
      // cartes visibles est celle qu'on visait.
      R.classe(cible, 'visee', true);
      setTimeout(() => R.classe(cible, 'visee', false), 1400);
      setTimeout(majAlphabet, 420);
    };
    // La lettre cliquee accuse le coup : sans ce retour, un clic sur une
    // lettre deja courante ne produit aucun signe visible et passe pour un
    // bouton mort.
    const bouton = [...document.querySelectorAll('#alphabet .alpha')]
      .find(b => b.textContent === lettre);
    if (bouton) {
      bouton.classList.remove('atteinte');
      void bouton.offsetWidth;          // force le redemarrage de l'animation
      bouton.classList.add('atteinte');
      setTimeout(() => bouton.classList.remove('atteinte'), 600);
    }
    ALPHA_VISEE = lettre;
    ALPHA_JUSQUA = Date.now() + 1400;   // le temps que le defilement se pose
    majAlphabet();
    if (page !== PAGE) { PAGE = page; renderLib(); requestAnimationFrame(bouger); }
    else bouger();
  },

  ajouterCompte,
  creerCle, revoquerCle,
  chargerComptes,

  // Choix de la plateforme dont on regle les options.
  choisirPlateformeReglages(key) {
    PF_REGLAGES = key;
    localStorage.setItem('pf-reglages', key);
    // Le selecteur doit toujours montrer la plateforme affichee : appele
    // depuis ailleurs (une carte de plateforme), il restait sur l'ancienne.
    const sel = $('s-plateforme');
    if (sel && sel.value !== key) sel.value = key;
    majReglagesPlateforme();
  },

  // Verifie que le fournisseur repond AVANT d'activer le SSO : se verrouiller
  // dehors avec une adresse mal saisie serait le pire scenario.
  async testerAuth() {
    const el = $('authtest');
    el.innerHTML = '<p class="erdit">Interrogation du fournisseur…</p>';
    const r = await api('/api/auth-test', {});
    if (!r.ok) {
      el.innerHTML = '<p class="erdit alerte">' +
        phrase('Échec : %s', esc(r.message || t('inconnu'))) + '</p>' +
        '<p class="erdit petit">Adresse de retour à déclarer chez le fournisseur : <code>' +
        esc(r.retour || '') + '</code></p>';
      return;
    }
    const i = r.infos;
    el.innerHTML = '<div class="majbloc">' +
      [['Fournisseur joint', esc(i.issuer)],
       ['Clés publiques', i.cles + (i.cles ? '' : '  — aucune, la signature ne pourra pas être vérifiée')],
       ['PKCE S256', i.pkce ? 'annoncé' : 'non annoncé (utilisé quand même)'],
       ['Client secret', i.secret ? 'fourni' : 'aucun — client public'],
       ['Adresse de retour', '<code>' + esc(r.retour) + '</code>']]
      .map(([k, v]) => '<div class="majrow"><span>' + k + '</span><b>' + v + '</b></div>').join('') +
      '</div>' +
      '<p class="erdit petit">Déclare cette adresse de retour chez ton fournisseur, ' +
      'puis passe le mode sur « SSO ». Une adresse qui ne correspond pas au caractère ' +
      'près sera refusée.</p>';
  },
  copierRetour() {
    const c = ($('authtest').textContent.match(/https?:\/\/\S+\/auth\/callback/) || [])[0];
    if (!c) return toast('Lance d\'abord le test.', 'warn');
    navigator.clipboard.writeText(c).then(() => toast('Adresse copiée.', 'ok')).catch(() => {});
  },
  async syncMeta() {
    const r = await api('/api/meta-sync', {});
    r.error || (toast('Récupération des fiches lancée.', 'ok'), this.poll());
  },
  async clearCovers() { const r = await api('/api/covers-clear', {}); toast(r.message, 'ok'); render(); },

  // ---- corbeille + journal
  // La corbeille se lit d'abord en une phrase. Le detail, souvent long
  // (40 lots ici), reste replie tant qu'on ne le demande pas.
  async loadTrash() {
    // `rep` et non `t` : `t()` est la fonction de traduction, et la masquer ici
    // faisait lever « t is not a function » des que la corbeille contenait un
    // lot — le resume ne s'affichait alors jamais. Invisible tant que la
    // corbeille reste vide, ce qui est le cas de toute ludotheque de test.
    const rep = await api('/api/trash-list');
    const r = rep.resume || {lots: 0, fichiers: 0, octets: 0, plus_vieux: 0};
    const s = $('trashsum');
    if (s) s.innerHTML = r.lots
      ? '<b>' + r.lots + '</b> ' + t('lot(s)') + ' &middot; <b>' + r.fichiers
        + '</b> ' + t('fichier(s)') + ' &middot; <b>' + fmt(r.octets) + '</b> '
        + t('récupérables')
        + (r.plus_vieux ? ' <span class="mono">'
           + phrase('— le plus ancien a %d jour(s)', r.plus_vieux) + '</span>' : '')
      : '<span class="mono">Corbeille vide.</span>';
    const sel = $('s-trashdays');
    if (sel && t.jours != null) sel.value = String(t.jours);
    $('trash').innerHTML = t.items.length
      ? '<div class="card">' + t.items.map(i => '<div class="row"><span class="grow">' +
          esc(i.name) + '</span><span class="mono">' + nb(i.count, 'fichier(s)') + ' · ' +
          fmt(i.size || 0) + '</span>' +
          '<button data-act="restore" data-arg="' + esc(i.name) + '">Restaurer</button></div>').join('') + '</div>'
      : '<div class="empty">Rien en corbeille.</div>';
  },
  toggleTrashList(e) {
    if (e) e.preventDefault();
    const d = $('trash'), a = $('trashmore');
    const ouvert = d.style.display !== 'none';
    d.style.display = ouvert ? 'none' : '';
    if (a) a.textContent = ouvert ? 'voir le détail' : 'masquer le détail';
  },
  async purgeTrash() {
    const jours = parseInt(($('s-trashdays') || {}).value, 10) || 0;
    dialogue({
      titre: 'Vider la corbeille ?',
      niveau: 'warn',
      message: jours
        ? phrase('Les lots de plus de %d jour(s) seront supprimés définitivement.', jours)
        : 'Aucun délai n\'est configuré : choisis d\'abord « Vider automatiquement », '
          + 'ou confirme pour tout supprimer maintenant.',
      detail: 'C\'est la seule opération de l\'outil qui efface réellement des fichiers.',
      fermer: 'Annuler',
      actions: [{libelle: jours ? 'Purger' : 'Tout supprimer', principal: true, faire: async () => {
        const r = await api('/api/trash-purge', {jours: jours || 1});
        if (!r.error) { toast(r.message, 'ok'); this.loadTrash(); }
      }}],
    });
  },
  toggleDrop(force) {
    const w = $('dropwrap');
    const ouvert = force === undefined ? !w.classList.contains('on') : !!force;
    if (ouvert) this.basculerTaches(false);      // un seul panneau a la fois
    R.classe(w, 'on', ouvert);
    R.classe($('fab'), 'on', ouvert && !activite());
  },

  basculerTaches(force) {
    const w = $('tachewrap');
    const ouvert = force === undefined ? !w.classList.contains('on') : !!force;
    if (ouvert) R.classe($('dropwrap'), 'on', false);
    R.classe(w, 'on', ouvert);
    R.classe($('fab'), 'on', ouvert);
    if (ouvert) this.poll();                     // rafraichir tout de suite
  },

  // Le bouton « + » a deux roles selon l'etat : quand quelque chose tourne, il
  // ouvre le detail de ce qui tourne ; sinon il sert a ajouter des jeux. C'est
  // la que l'utilisateur regarde deja, puisque l'anneau y tourne.
  actionFab() {
    if (activite()) this.basculerTaches();
    else this.toggleDrop();
  },
  async restore(n) { const r = await api('/api/restore', {name: n}); toast(r.message, 'ok'); this.scan(); },
  setJFilter(f) {
    JFILTRE = f;
    document.querySelectorAll('#jfilters .chip').forEach(c => c.classList.toggle('on', c.dataset.jl === f));
    renderJournal();
  },
  async journalClear() {
    JLOG = []; renderJournal();
    await api('/api/journal-clear', {});
    toast('Journal effacé.', 'ok');
  },
  journalCopy() {
    const txt = JLOG.map(e => e.t + ' [' + e.n + '] ' + e.m).join('\n');
    navigator.clipboard.writeText(txt)
      .then(() => toast('Journal copié.', 'ok'))
      .catch(() => toast('Copie impossible.', 'warn'));
  },
  renderJournal() { renderJournal(); },
  // Le journal s'ouvre en tiroir sur la droite : il ne recouvre plus le bouton
  // d'ajout ni la barre d'actions, et se referme d'un clic sur le voile.
  toggleJournal() {
    const ouvert = $('jdrawer').classList.toggle('open');
    $('jvoile').classList.toggle('on', ouvert);
    $('journalbtn').classList.remove('news');
    $('journalbtn').classList.toggle('masque', ouvert);
    document.body.classList.toggle('sansdefilement', ouvert && window.innerWidth < 900);
    if (ouvert) renderJournal();
  },

  async poll() {
    const j = await api('/api/job');
    if (Array.isArray(j.log)) { fusionnerJournal(j.log); renderJournal(); }
    const dernier = j.log && j.log.length ? j.log[j.log.length - 1] : null;
    if (dernier) say(j.detail || dernier.m || dernier);
    this._paused = j.paused;
    renderTache(j);
    if (j.running) setTimeout(() => this.poll(), 900);
    else {
      // Une tache qui se termine a presque toujours deplace, converti ou
      // supprime des fichiers : ce qu'on garde en cache ne vaut plus rien.
      oublierCacheSysteme();
      const soucis = (j.log || []).filter(e => e.n === 'error');
      const alertes = (j.log || []).filter(e => e.n === 'warn');
      if (soucis.length) {
        dialogue({
          titre: 'Tâche terminée avec des erreurs',
          niveau: 'error',
          message: phrase('%s erreur(s) et %s alerte(s). Le reste s\'est bien '
                          + 'déroulé.', soucis.length, alertes.length),
          detail: soucis.slice(-12).map(e => e.t + '  ' + e.m).join('\n'),
          actions: [{libelle: 'Voir le journal', principal: true,
                     faire: () => { if (!$('jdrawer').classList.contains('open')) app.toggleJournal();
                                app.setJFilter('error'); }}],
        });
      } else toast('Terminé.', 'ok');
      this.scan();
      if (NANDST.length) this.loadNand();
      if (!isSwitch()) this.setSystem(SYS);
    }
  },
};

function renderManifest(r) {
  const groups = {};
  r.plan.forEach(it => { (groups[it.folder] = groups[it.folder] || []).push(it); });
  const tight = r.free != null && r.to_send > r.free;
  const body = Object.keys(groups).sort().map(folder => {
    const items = groups[folder].map(it => {
      if (it.broken) return '<div class="mfitem bad"><span>&#9888; ' + esc(it.name) +
        '<br><span class="mono">' +
        phrase('fichier incomplet : %s — à remplacer', esc(it.broken)) +
        '</span></span><span>' + t('non envoyé') + '</span></div>';
      return '<div class="mfitem"><span>' + (it.skip ? '&check; ' : '') + esc(it.name) + '</span><span>' +
        (it.skip ? 'déjà sur la console' : fmt(it.size)) + '</span></div>';
    }).join('');
    return '<div class="mfgroup"><div class="mflabel"><span class="arrow">&rarr;</span>' +
      esc(folder) + ' <span class="mono">(' + groups[folder].length + ')</span></div>' + items + '</div>';
  }).join('');
  $('manifest').innerHTML = '<div class="manifest"><div class="mfhead">' +
    '<span><b>' + fmt(r.to_send) + '</b> ' +
    phrase('à envoyer vers %s', esc(r.device_dir)) +
    (r.skipped ? ' <span class="mono">('
      + phrase('%d déjà sur la console', r.skipped) + ')</span>' : '') +
    (r.broken ? ' <span class="bad">'
      + phrase('— %d fichier(s) incomplet(s) bloqué(s)', r.broken) + '</span>' : '') + '</span>' +
    '<span class="' + (tight ? 'bad' : '') + '">' +
    (r.free != null ? 'libre : ' + fmt(r.free) + (tight ? ' — insuffisant !' : '') : 'espace inconnu') +
    '</span></div>' + body + '</div>';
}

// ------------------------------------------------- parcours de premier lancement
// Chaque etape est verifiee cote serveur (/api/health) : on ne raconte pas a
// l'utilisateur qu'il lui manque quelque chose qu'il a deja fait.
let HEALTH = null;

/* ============================================================================
   PREMIER DEMARRAGE
   ----------------------------------------------------------------------------
   Un parcours, pas une liste de controles. La version precedente affichait sept
   diagnostics d'un bloc : l'utilisateur les lisait tous, n'en comprenait aucun,
   et n'avait rien a faire dessus.

   Ici, une etape a la fois, chacune avec une action reelle et un statut :
   OBLIGATOIRE ou FACULTATIF. Ce qui est propre a une console — emulateur,
   cles de dechiffrement, dossiers distants — n'y figure pas : cela se regle
   plus tard, quand on sait de quoi il s'agit. Ce qui compte au premier
   lancement, c'est ou sont les jeux, qui a le droit d'entrer, et de quoi
   remplir les jaquettes.
   ========================================================================== */
let ONB = {i: 0, sens: 1, occupe: false, resultatScan: null,
           consoleScan: null, testJaquettes: ''};

function onbEtapes(h) {
  const c = (h && h.checks) || {};
  return [
    {
      cle: 'bienvenue', titre: 'Bienvenue dans Romule', requis: null,
      sous: 'Trois minutes pour mettre ta ludothèque en route.',
      corps: () =>
        '<p class="onbp">Romule range et transfère une bibliothèque de jeux que ' +
        'tu possèdes déjà. Il ne télécharge aucun jeu et ne fournit aucune clé.</p>' +
        '<ul class="onbliste">' +
        '<li><b>Ta bibliothèque</b><span class="onbdesc">Où sont tes fichiers, ' +
          'et ce qu\'on y trouve.</span></li>' +
        '<li><b>Ton accès</b><span class="onbdesc">Qui a le droit d\'ouvrir ' +
          'cette page.</span></li>' +
        '<li><b>Les jaquettes</b><span class="onbdesc">Facultatif, mais c\'est ' +
          'ce qui rend la grille lisible.</span></li>' +
        '<li><b>Ta console</b><span class="onbdesc">Facultatif, et faisable ' +
          'plus tard.</span></li>' +
        '</ul>',
    },
    {
      cle: 'biblio', titre: 'Ta bibliothèque', requis: true,
      sous: 'Le dossier qui contient tous tes jeux, toutes plateformes confondues.',
      corps: () => {
        const r = ONB.resultatScan;
        // Choisir le dossier depuis ici, plutot que de renvoyer vers une
        // variable d'environnement : sur un NAS, cela voulait dire ouvrir un
        // terminal et redemarrer un conteneur au beau milieu de l'assistant.
        if (LUDO.cible === 'onb') return renduLudoOnboard();
        return '<p class="onbp">Romule analyse ce dossier :</p>' +
          '<div class="onbchemin">' + esc(h.ludotheque || h.root || '') + '</div>' +
          (h.ludotheque_imposee
            ? '<p class="onbnote">Il est fixé par le déploiement (variable ' +
              'ROMULE_LIBRARY) : pour en changer, modifie ton fichier compose.</p>'
            : '<button class="ghost" data-act="onbChoisirDossier">' +
              'Choisir un autre dossier…</button>') +
          '<p class="onbnote">Le dossier reste à toi : Romule n\'y écrit que ses ' +
          'propres fichiers, tous préfixés d\'un tiret bas. Sa configuration et ' +
          'tes comptes, eux, vivent ailleurs et ne suivent pas ce dossier.</p>' +
          '<button class="go" data-act="onbScanner"' + (ONB.occupe ? ' disabled' : '') +
          '>' + (ONB.occupe ? 'Lecture…' : 'Analyser le dossier') + '</button>' +
          (r ? renduScanOnboard(r) : '');
      },
      valide: () => !!(ONB.resultatScan && ONB.resultatScan.total > 0),
      manque: 'Analyse le dossier pour vérifier que tes jeux sont bien vus.',
    },
    {
      cle: 'compte', titre: 'Ton accès', requis: !!c.expose,
      sous: c.expose
        ? 'Ce serveur écoute sur le réseau : il lui faut un compte.'
        : 'Un compte protège l\'accès si tu ouvres un jour Romule au réseau.',
      corps: () => c.comptes
        ? '<p class="onbok">Un compte administrateur existe déjà.</p>'
        : '<p class="onbp">Le premier compte créé devient administrateur : lui ' +
          'seul pourra changer les réglages et gérer les autres comptes.</p>' +
          '<div class="onbchamps">' +
          '<label>Adresse e-mail<input type="email" id="onb-mail" ' +
            'autocomplete="username" placeholder="toi@exemple.fr"></label>' +
          '<label>Mot de passe<input type="password" id="onb-mdp" ' +
            'autocomplete="new-password" placeholder="12 caractères minimum"></label>' +
          '</div>' +
          '<button class="go" data-act="onbCreerCompte">Créer le compte</button>' +
          '<p class="onbnote" id="onb-mdp-msg"></p>',
      valide: () => !c.expose || c.comptes > 0,
      manque: 'Crée un compte : sans lui, n\'importe quel appareil du réseau peut tout faire.',
    },
    {
      cle: 'fiches', titre: 'Jaquettes et fiches', requis: false,
      sous: 'Deux services gratuits remplissent les pochettes et les résumés.',
      corps: () =>
        '<p class="onbp">Sans eux, la bibliothèque fonctionne, mais elle ' +
        'n\'affiche que des noms de fichiers.</p>' +
        '<div class="onbchamps">' +
        '<label>Clé SteamGridDB <span class="onbaide">jaquettes — ' +
          'steamgriddb.com/profile/preferences/api</span>' +
          '<input type="text" id="onb-sgdb" autocomplete="off"></label>' +
        '<label>IGDB — Client ID <span class="onbaide">résumés, année, éditeur — ' +
          'dev.twitch.tv/console/apps</span>' +
          '<input type="text" id="onb-igdb-id" autocomplete="off"></label>' +
        '<label>IGDB — Client Secret' +
          '<input type="password" id="onb-igdb-secret" autocomplete="off"></label>' +
        '</div>' +
        '<button class="go" data-act="onbTesterFiches">Enregistrer et tester</button>' +
        '<p class="onbnote" id="onb-fiches-msg">' + esc(ONB.testJaquettes) + '</p>',
    },
    {
      cle: 'console', titre: 'Ta console', requis: false,
      sous: 'Facultatif, et faisable à tout moment depuis les réglages.',
      corps: () => c.device
        ? '<p class="onbok">' + t('Console reliée en %s.')
            .replace('%s', c.device === 'wifi' ? 'Wi-Fi' : 'USB') + '</p>' +
          '<p class="onbnote">Le dossier de jeux repéré sur la console :</p>' +
          '<div class="onbchemin" data-i18n-skip>' + esc(c.device_dir || '') + '</div>' +
          '<button class="ghost" data-act="onbScannerConsole"' +
            (ONB.occupe ? ' disabled' : '') + '>' +
            (ONB.occupe ? 'Lecture…' : 'Recenser les jeux de la console') + '</button>' +
          (ONB.consoleScan ? renduScanConsole(ONB.consoleScan) : '')
        : '<p class="onbp">Romule transfère les jeux vers une console Android par ' +
          'adb. Branche-la en USB, ou active le débogage sans fil et indique son ' +
          'adresse.</p>' +
          (c.adb ? '' : '<p class="onbnote">adb n\'est pas installé sur cette ' +
             'machine. Pour l\'ajouter :</p>' +
             '<div class="onbchemin" data-i18n-skip>' + esc(c.remede_adb || '') +
             '</div>') +
          '<button class="ghost" data-act="onbChercherConsole"' +
            (c.adb ? '' : ' disabled') + '>Chercher une console</button>',
    },
    {
      cle: 'fin', titre: 'C\'est prêt', requis: null,
      sous: 'Le reste se règle depuis les réglages, quand le besoin se présente.',
      corps: () =>
        '<ul class="onbliste">' +
        '<li><b>Jeux compressés</b>' +
          '<span class="onbdesc">' + (c.nsz
            ? 'L\'outil nsz est installé : les .nsz et .xcz seront convertis.'
            : 'Les .nsz et .xcz demandent l\'outil nsz et un fichier prod.keys, ' +
              'à fournir dans les réglages.') + '</span></li>' +
        '<li><b>Émulateur</b>' +
          '<span class="onbdesc">' + t('Romule vise %s par défaut. Réglages → Ta console.')
            .replace('%s', esc(nomEmulateur(c.emulateur))) + '</span></li>' +
        '<li><b>Accès à distance</b>' +
          '<span class="onbdesc">Ouvrir la ludothèque depuis le téléphone ou ' +
          'l\'extérieur se règle dans Réglages → Accès.</span></li>' +
        '</ul>',
    },
  ];
}

function renduScanOnboard(r) {
  if (!r.total) {
    return '<div class="onbresultat vide"><b>Aucun jeu trouvé.</b>' +
      '<p class="onbnote">Dépose tes fichiers dans ce dossier, puis relance ' +
      'l\'analyse.</p><p class="onbnote">' +
      t('Romule reconnaît %d extensions de fichier.')
        .replace('%d', r.extensions || 0) + '</p></div>';
  }
  return '<div class="onbresultat"><b>' +
    t('%d jeux répartis sur %d plateformes')
      .replace('%d', r.total).replace('%d', r.plateformes.length) + '</b>' +
    '<div class="onbpf">' + r.plateformes.map(p =>
      '<span class="onbpuce"><b>' + p.n + '</b> ' + esc(p.nom) + '</span>').join('') +
    '</div></div>';
}

function renduScanConsole(r) {
  if (!r.total) {
    return '<div class="onbresultat vide"><b>Aucun jeu sur la console.</b></div>';
  }
  return '<div class="onbresultat"><b>' +
    t('%d jeux sur la console').replace('%d', r.total) + '</b>' +
    '<p class="onbnote">' + (r.new
      ? t('%d ne sont pas encore dans ta bibliothèque.').replace('%d', r.new)
      : 'Tous sont déjà dans ta bibliothèque.') + '</p></div>';
}

function onbAller(i) {
  const etapes = onbEtapes(HEALTH);
  const cible = Math.max(0, Math.min(etapes.length - 1, i));
  ONB.sens = cible >= ONB.i ? 1 : -1;
  ONB.i = cible;
  renderOnboard();
}

function renderOnboard() {
  const el = $('onboard');
  if (!HEALTH) { el.classList.remove('open'); return; }
  const etapes = onbEtapes(HEALTH);
  ONB.i = Math.max(0, Math.min(etapes.length - 1, ONB.i));
  const e = etapes[ONB.i];
  const dernier = ONB.i === etapes.length - 1;
  const bloque = e.requis && e.valide && !e.valide();

  el.innerHTML = '<div class="obox onbcarte">' +
    '<div class="onbtete">' +
      '<span class="onbrang">' + t('Étape %d sur %d')
        .replace('%d', ONB.i + 1).replace('%d', etapes.length) + '</span>' +
      // `null` : une etape qui n'attend aucune action ne peut etre ni
      // obligatoire ni facultative — la dire « facultative » suggere a tort
      // qu'il y aurait quelque chose a y faire.
      '<span class="onbbadge ' +
        (e.requis === null ? 'nul' : e.requis ? 'req' : 'opt') + '">' +
        (e.requis === null ? 'Pour info' : e.requis ? 'Obligatoire' : 'Facultatif') +
        '</span>' +
    '</div>' +
    '<h2 class="obt">' + esc(e.titre) + '</h2>' +
    '<p class="lead">' + esc(e.sous) + '</p>' +
    '<div class="onbcorps" data-sens="' + ONB.sens + '">' + e.corps() + '</div>' +
    (bloque ? '<p class="onbmanque">' + esc(e.manque || '') + '</p>' : '') +
    '<div class="onbpied">' +
      '<button class="ghost" data-act="onbPrec"' +
        (ONB.i === 0 ? ' disabled' : '') + '>Précédent</button>' +
      '<div class="onbpoints">' + etapes.map((x, i) =>
        '<button class="onbpoint' + (i === ONB.i ? ' on' : '') +
          (i < ONB.i ? ' fait' : '') + '" title="' + esc(x.titre) +
          '" aria-label="' + esc(x.titre) + '" data-act="onbAller" data-arg=" + i + ">' +
        '</button>').join('') + '</div>' +
      (dernier
        ? '<button class="go" data-act="closeOnboard">Terminer</button>'
        : '<button class="go" data-act="onbSuiv"' + (bloque ? ' disabled' : '') +
          '>Suivant</button>') +
    '</div>' +
    '<button class="onbpasser" data-act="closeOnboard">Passer l\'assistant</button>' +
    '</div>';
  traduireDOM(el);
  el.classList.add('open');
}

// ------------------------------------------- proposition d'installation (a2hs)
// Detecte automatiquement le contexte : on ne propose l'installation QUE si la
// page est ouverte a distance (console, telephone) et pas deja installee.
let INSTALL_EVT = null;

function installContext() {
  const standalone = (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches)
    || window.navigator.standalone === true;
  const local = ['127.0.0.1', 'localhost', '::1', ''].includes(location.hostname);
  const ua = navigator.userAgent || '';
  const ios = /iPad|iPhone|iPod/.test(ua);
  return {
    standalone, local, ios,
    android: /Android/.test(ua),
    dismissed: localStorage.getItem('a2hs-off') === '1',
  };
}

// Quand on pilote depuis la console ou le telephone, on rappelle que la
// bibliotheque et les actions vivent sur le serveur, pas sur l'appareil.
function renderHost() {
  const c = installContext();
  const el = $('hostchip');
  if (!el) return;
  if (c.local) { el.style.display = 'none'; return; }
  el.style.display = '';
  el.textContent = 'serveur ' + location.hostname;
  el.title = 'La bibliothèque et les traitements sont sur cette machine.';
}

function renderA2HS() {
  const el = $('a2hs');
  const c = installContext();
  if (c.standalone || c.local || c.dismissed) { el.style.display = 'none'; return; }

  const how = c.ios
    ? 'appuie sur <b>Partager</b> puis <b>Sur l\'écran d\'accueil</b>'
    : 'ouvre le menu <b>⋮</b> du navigateur puis <b>Ajouter à l\'écran d\'accueil</b>';
  const action = INSTALL_EVT
    ? '<button class="go" data-act="installApp">Installer l\'application</button>'
    : '<span class="mono">' + how + '</span>';

  el.style.display = '';
  el.innerHTML = '<span class="a2icon">📲</span>' +
    '<span class="grow"><b>Ajoute la ludothèque à ton écran d\'accueil</b>' +
    '<div class="mono">Elle s\'ouvrira en plein écran, comme une vraie application.</div></span>' +
    action + '<button class="ghost" data-act="dismissA2HS">Plus tard</button>';
}

// Chrome propose parfois une vraie installation : on l'utilise si elle arrive.
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault(); INSTALL_EVT = e; renderA2HS();
});
window.addEventListener('appinstalled', () => {
  INSTALL_EVT = null; localStorage.setItem('a2hs-off', '1'); renderA2HS();
  toast('Application installée. Retrouve-la sur ton écran d\'accueil.', 'ok');
});

// ---------------------------------------------------------------- glisser-deposer
// La liste vient du serveur : elle depend des plateformes connues ET de celles
// que l'utilisateur a ajoutees a la main, avec leurs propres extensions. La
// figer ici aurait refuse une ROM que l'outil sait pourtant ranger.
let EXTS_ACCEPTEES = ['.nsz', '.xcz', '.nsp', '.xci', '.zip', '.7z', '.rar'];

// Le voile de depot et le champ « Ajouter des jeux » annoncent la MEME liste
// que celle reellement acceptee : une liste figee dans le HTML mentait des que
// l'utilisateur ajoutait une plateforme.
function majZoneDepot() {
  const t = $('dropexts');
  if (!t) return;
  // Une liste alphabetique (« .3ds .bin .cci… ») n'apprend rien. Ce que
  // l'utilisateur veut savoir, c'est QUELLES CONSOLES sont reconnues.
  const noms = (SYSTEMS || []).map(x => x.name).filter(Boolean);
  const apercu = noms.slice(0, 4).join(', ');
  const n = EXTS_ACCEPTEES.length;
  R.texte(t, (apercu ? apercu + '… ' : '')
    + n + ' formats reconnus, archives comprises');
}

function extensionAcceptee(nom) {
  const m = /\.[a-z0-9]+$/i.exec(nom || '');
  return !!m && EXTS_ACCEPTEES.includes(m[0].toLowerCase());
}

// L'avancement est calcule sur le VOLUME total, pas sur le nombre de fichiers :
// deposer un jeu de 12 Go et un patch de 30 Mo ne fait pas « 50 % » a mi-chemin.
function uploadFiles(files) {
  // Le depot ajoute des fichiers a la ludotheque : le cache est perime avant
  // meme que le transfert ne se termine.
  oublierCacheSysteme();
  let list = [...files].filter(f => extensionAcceptee(f.name));
  const rejetes = [...files].length - list.length;
  if (!list.length) {
    return toast(t('Aucun fichier reconnu.') + ' ' +
                 phrase('%s formats acceptés — voir « Ajouter des jeux ».',
                        EXTS_ACCEPTEES.length), 'warn');
  }
  if (rejetes) journal(phrase('%d fichier(s) ignoré(s) : type non géré.', rejetes), 'warn');

  // Le plafond est verifie ICI, avant d'ouvrir la moindre connexion. Le
  // serveur le fait aussi — c'est lui qui fait autorite — mais il ne peut
  // repondre qu'apres coup : il coupe alors la connexion en pleine reception,
  // et le navigateur n'affiche qu'une « erreur reseau » qui n'explique rien.
  const plafond = TELEVERSEMENT_MAX;
  if (plafond) {
    const trop = list.filter(f => f.size > plafond);
    if (trop.length) {
      trop.forEach(f => journal('Trop volumineux : ' + f.name + ' (' + fmt(f.size)
                                + ', maximum ' + fmt(plafond) + ')', 'error'));
      toast(phrase('%d fichier(s) dépassent %s.', trop.length)
        .replace('%s', fmt(plafond)), 'warn');
      list = list.filter(f => f.size <= plafond);
      if (!list.length) return;
    }
  }

  const octets = list.reduce((n, f) => n + f.size, 0);
  const debut = Date.now();
  let envoyes = 0, i = 0;

  const avancer = (enCours, nom) => {
    const fait = envoyes + enCours;
    const pct = octets ? Math.round(100 * fait / octets) : null;
    const ecoule = (Date.now() - debut) / 1000;
    // Pas d'estimation avant d'avoir observe un vrai debit : une ETA fondee sur
    // les premieres millisecondes annonce n'importe quoi.
    const secs = (ecoule > 2 && fait > 0)
      ? Math.round((octets - fait) / (fait / ecoule)) : null;
    const reste = texteReste(secs);
    ACT_ENVOI = {
      titre: 'Envoi' + (list.length > 1 ? ' ' + (i) + '/' + list.length : ''),
      pct: pct,
      // Le bouton affiche le temps restant EN CHIFFRES : il lui faut la
      // valeur, pas la phrase deja mise en forme pour le panneau.
      secs: secs,
      reste: [nom ? extrait(nom, 22) : '', reste].filter(Boolean).join(' · '),
    };
    majFab();
    $('bar').style.width = (pct || 0) + '%';
  };

  const next = () => {
    if (i >= list.length) {
      ACT_ENVOI = null;
      majFab();
      $('bar').style.width = '0';
      toast(phrase('%d fichier(s) déposé(s).', list.length), 'ok');
      // Le depot etant desormais possible n'importe ou, l'utilisateur n'a pas
      // forcement le panneau sous les yeux : on l'ouvre sur la liste fraiche,
      // pour que l'etape suivante soit la ou il regarde.
      app.toggleDrop(true);
      app.reloadImport();
      app.classerImports(true);        // s'il reste des extensions ambigues
      return;
    }
    const file = list[i++];
    say(phrase('Envoi de %s…', file.name));
    avancer(0, file.name);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
    xhr.upload.onprogress = e => { if (e.lengthComputable) avancer(e.loaded, file.name); };
    xhr.onload = () => {
      envoyes += file.size; journal(phrase('Reçu : %s', file.name), 'ok'); next();
    };
    xhr.onerror = () => {
      envoyes += file.size;
      toast(phrase('Échec de l\'envoi : %s', file.name), 'warn');
      next();
    };
    xhr.send(file);
  };
  next();
}

// ---------------------------------------------------------------- init
$('tabs').addEventListener('click', e => { if (e.target.dataset.tab) app.tab(e.target.dataset.tab); });
$('filters').addEventListener('click', e => { const b = e.target.closest('.chip'); if (b) app.setFilter(b.dataset.f); });
$('jfilters').addEventListener('click', e => { const b = e.target.closest('.chip'); if (b) app.setJFilter(b.dataset.jl); });
// Un reglage modifie = on envoie CE reglage uniquement. Envoyer tout le
// formulaire exposait a ecraser la configuration avec des champs vides.
const SET_FIELDS = {
  's-romsroot': ['roms_root', 'text'],
  's-savesdir': ['saves_dir', 'text'], 's-sgkey': ['steamgriddb_key', 'text'],
  's-igdbid': ['igdb_client_id', 'text'],
  's-igdbsecret': ['igdb_client_secret', 'text'],
  's-cover': ['cover_url', 'text'], 's-jobs': ['jobs', 'int'],
  's-layout': ['push_layout', 'val'], 's-local': ['local_layout', 'val'],
  's-verify': ['verify_mode', 'val'], 's-coverprov': ['cover_provider', 'val'],
  's-lang': ['meta_lang', 'val'], 's-incr': ['incremental', 'bool'],
  's-lan': ['lan_access', 'bool'], 's-notify': ['notify', 'bool'],
  's-mirrors': ['versions_urls', 'lines'],
  's-emuready': ['emuready', 'bool'],
  's-autonand': ['auto_nand', 'bool'],
  's-trashdays': ['trash_days', 'int0'],
  's-authmode': ['auth_mode', 'val'], 's-oidcissuer': ['oidc_issuer', 'text'],
  's-oidcclient': ['oidc_client_id', 'text'], 's-oidcsecret': ['oidc_client_secret', 'text'],
  's-oidcemails': ['oidc_emails', 'text'], 's-oidcgroupes': ['oidc_groupes', 'text'],
  's-oidcredirect': ['oidc_redirect', 'text'],
};
$('panel-settings').addEventListener('change', e => {
  const spec = SET_FIELDS[e.target.id];
  if (!spec) return;
  const [cle, type] = spec;
  const v = type === 'bool' ? e.target.checked
    : type === 'int0' ? Math.max(0, parseInt(e.target.value, 10) || 0)   // 0 autorise
    : type === 'int' ? Math.max(1, parseInt(e.target.value, 10) || 3)
    : type === 'lines' ? e.target.value.split('\n').map(s => s.trim()).filter(Boolean)
    : type === 'text' ? e.target.value.trim() : e.target.value;
  app.saveField(cle, v);
});
$('panel-settings').addEventListener('input', syncSetDesc);
$('panel-settings').addEventListener('change', majBlocAuth);
$('s-erdevice').addEventListener('change', e => app.erPickDevice(e.target.value));
$('s-uilang').addEventListener('change', e => app.setLang(e.target.value));
$('s-plateforme').addEventListener('change', e => app.choisirPlateformeReglages(e.target.value));

// Hauteur reelle de l'en-tete et du sommaire : elles changent avec la largeur
// (les onglets passent a la ligne) et avec le mode paysage, ou l'en-tete n'est
// plus colle. Les figer dans le CSS decalerait les ancres d'une barre.
function mesurerBarres() {
  const tete = document.querySelector('header');
  const nav = $('setnav');
  const colle = tete && getComputedStyle(tete).position === 'sticky';
  const h = colle ? Math.round(tete.getBoundingClientRect().height) : 0;
  document.documentElement.style.setProperty('--tete-h', h + 'px');
  if (nav) {
    document.documentElement.style.setProperty(
      '--somm-h', Math.round(nav.getBoundingClientRect().height) + 'px');
  }
}
addEventListener('resize', mesurerBarres);
// L'index suit la lecture : on recalcule au defilement, jamais plus d'une fois
// par image.
(function () {
  let prevu = false;
  addEventListener('scroll', () => {
    if (prevu) return;
    prevu = true;
    requestAnimationFrame(() => {
      prevu = false;
      // Un defilement volontaire rend la main au calcul de position. Le saut
      // lui-meme en declenche un : on le laisse passer.
      if (Date.now() > ALPHA_JUSQUA) ALPHA_VISEE = '';
      majAlphabet();
    });
  }, {passive: true});
})();
// Une mesure unique au chargement se trompe : l'en-tete grandit quand la
// connexion s'affiche, et le sommaire n'existe qu'une fois l'onglet ouvert.
// On suit donc leur taille reelle.
if ('ResizeObserver' in window) {
  const suivi = new ResizeObserver(mesurerBarres);
  const tete = document.querySelector('header');
  if (tete) suivi.observe(tete);
  const barre = $('setnav');
  if (barre) suivi.observe(barre);
}

/* Les reglages sont maintenant des ONGLETS : une seule section a l'ecran.
   Les cinq bout a bout faisaient une page de plusieurs ecrans ou l'on
   naviguait au defilement, et le sommaire ne servait qu'a se reperer dans ce
   defilement. Avec des onglets, il choisit vraiment ce qu'on regarde — et la
   page redevient courte, ce qui compte sur un handheld.

   La section ouverte est retenue : on revient presque toujours dans celle
   qu'on reglait. */
const SECTIONS_REGLAGES = [];
let SECTION_ACTIVE = '';

function voirSectionReglages(id, memoriser) {
  if (!SECTIONS_REGLAGES.length) return;
  const cible = SECTIONS_REGLAGES.find(s => s.sec.id === id) || SECTIONS_REGLAGES[0];
  SECTION_ACTIVE = cible.sec.id;
  for (const s of SECTIONS_REGLAGES) {
    const on = s === cible;
    s.sec.hidden = !on;
    R.classe(s.a, 'on', on);
    s.a.setAttribute('aria-selected', String(on));
    s.a.tabIndex = on ? 0 : -1;
  }
  if (memoriser !== false) {
    try { localStorage.setItem('reglages-section', SECTION_ACTIVE); } catch (e) {}
  }
  mesurerBarres();
}

(function () {
  const nav = $('setnav');
  if (!nav) return;
  const liens = [...nav.querySelectorAll('a')]
    .map(a => ({a, sec: $(a.getAttribute('href').slice(1))}))
    .filter(x => x.sec);
  if (!liens.length) return;
  SECTIONS_REGLAGES.push(...liens);

  nav.setAttribute('role', 'tablist');
  for (const {a, sec} of liens) {
    a.setAttribute('role', 'tab');
    a.setAttribute('aria-controls', sec.id);
    sec.setAttribute('role', 'tabpanel');
    sec.setAttribute('aria-labelledby', sec.id + '-onglet');
    a.id = sec.id + '-onglet';
    a.addEventListener('click', ev => {
      // L'ancre reste dans le HTML : sans JavaScript, elle continue de mener
      // a la section, qui est alors simplement affichee a la suite.
      ev.preventDefault();
      voirSectionReglages(sec.id);
      scrollTo({top: 0, behavior: 'instant'});
    });
  }
  // Fleches gauche/droite dans la barre d'onglets : c'est ce qu'attend
  // n'importe quel lecteur d'ecran, et c'est plus rapide a la main.
  nav.addEventListener('keydown', ev => {
    const pas = ev.key === 'ArrowRight' ? 1 : ev.key === 'ArrowLeft' ? -1 : 0;
    if (!pas) return;
    ev.preventDefault();
    const i = liens.findIndex(l => l.sec.id === SECTION_ACTIVE);
    const suivant = liens[(i + pas + liens.length) % liens.length];
    voirSectionReglages(suivant.sec.id);
    suivant.a.focus();
  });

  let depart = '';
  try { depart = localStorage.getItem('reglages-section') || ''; } catch (e) {}
  voirSectionReglages(depart, false);
  addEventListener('resize', mesurerBarres);
  mesurerBarres();
})();
$('browser').addEventListener('click', e => { const el = e.target.closest('.brow.dir'); if (el && el.dataset.path) app.browse(el.dataset.path); });
$('crumb').addEventListener('click', e => { const a = e.target.closest('a'); if (a && a.dataset.path) app.browse(a.dataset.path); });
// Un seul attribut pour le navigateur du serveur — `data-lpath` — et une
// delegation par conteneur. L'assistant est redessine en entier a chaque
// etape : ecouter sur `#onboard` survit a ses rendus.
['ludowrap', 'onboard'].forEach(id => {
  $(id).addEventListener('click', e => {
    const el = e.target.closest('[data-lpath]');
    if (el) app.ludoAller(el.dataset.lpath);
  });
});
// --- Depot : la fenetre entiere accepte les fichiers.
// Le petit rectangle en pointilles restait a trouver, et n'etait visible qu'une
// fois le panneau ouvert. Deposer n'importe ou est le geste attendu ; le
// rectangle reste, comme repere quand le panneau est ouvert.
const drop = $('drop');
const voile = $('dropzone');

// `dragenter` et `dragleave` se declenchent AUSSI en passant d'un element a
// l'autre : sans compteur, le voile clignoterait pendant tout le survol.
let profondeur = 0;

function transporteDesFichiers(e) {
  const t = e.dataTransfer && e.dataTransfer.types;
  return !!t && [...t].includes('Files');
}

function montrerVoile(oui) {
  if (!voile) return;
  R.classe(voile, 'on', oui);
  voile.setAttribute('aria-hidden', oui ? 'false' : 'true');
}

window.addEventListener('dragenter', e => {
  if (!transporteDesFichiers(e)) return;
  profondeur++;
  montrerVoile(true);
});
window.addEventListener('dragover', e => {
  if (!transporteDesFichiers(e)) return;
  e.preventDefault();                       // sans ca, le navigateur ouvre le fichier
  e.dataTransfer.dropEffect = 'copy';
});
window.addEventListener('dragleave', e => {
  if (!transporteDesFichiers(e)) return;
  profondeur = Math.max(0, profondeur - 1);
  if (!profondeur) montrerVoile(false);
});
window.addEventListener('drop', e => {
  if (!transporteDesFichiers(e)) return;
  e.preventDefault();
  profondeur = 0;
  montrerVoile(false);
  drop.classList.remove('over');
  uploadFiles(e.dataTransfer.files);
});
// Le rectangle du panneau se met simplement en evidence au survol.
['dragover', 'dragenter'].forEach(ev =>
  drop.addEventListener(ev, () => drop.classList.add('over')));
['dragleave', 'dragend', 'drop'].forEach(ev =>
  drop.addEventListener(ev, () => drop.classList.remove('over')));
// Remonter dans le journal coupe le suivi ; redescendre au bas le reprend.
// C'est le comportement d'un terminal, et il n'a pas besoin d'etre explique.
$('log').addEventListener('scroll', () => {
  const el = $('log');
  const enBas = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  if (enBas !== JSUIVI) { JSUIVI = enBas; majBoutonSuivi(); }
}, {passive: true});

document.addEventListener('keydown', e => { if (e.key === 'Escape') { app.closeGame(); app.closeDialog(); } });
/* ---------------------------------------------------------------------------
   DELEGATION — un seul ecouteur par geste, une liste blanche

   Les gestionnaires `onclick="app.faire('x')"` obligeaient la politique de
   securite a tolerer `'unsafe-inline'`, c'est-a-dire a autoriser n'importe
   quel script pose dans la page. C'est ce qui a rendu exploitable l'XSS
   stockee corrigee en 0.1.0 : un nom de fichier suffisait a fermer la chaine
   et a ecrire du code. Deplacer la valeur dans un `data-*` ne DEPLACE pas le
   probleme, il le supprime : un attribut de donnee n'est jamais compile.

   `ACTES` est une liste BLANCHE, pas un appel dynamique. `app[el.dataset.act]`
   sans ce filtre laisserait n'importe quel attribut atteindre n'importe quelle
   methode — y compris celles qui suppriment. Le cout est une ligne par action ;
   le prix de l'autre solution est une faille de la meme famille que celle
   qu'on vient de fermer.

   Un attribut PAR GESTE, et non un seul pour tous : un clic sur un `<select>`
   precede le changement de valeur, donc un attribut commun aurait declenche
   l'action avec l'ANCIENNE valeur avant de la rejouer avec la bonne.

     data-act        au clic
     data-act-change au changement de valeur
     data-act-input  a la frappe

   L'argument, quand il y en a un :
     data-arg="jeux"     une CHAINE, toujours, jamais reinterpretee ;
     data-val="2"        du JSON, pour un nombre ou un booleen ;
     (rien)              la valeur du champ, si l'element en est un.
   Cette separation n'est pas du zele : en 4.4 les arguments deviendront des
   chemins de fichiers, et « 2024 » est un nom de dossier parfaitement legitime
   qu'une coercition silencieuse transformerait en nombre.
   ------------------------------------------------------------------------- */
const ACTES = new Set([
  // Les trois premiers ne figurent dans AUCUN attribut du source : ils sont
  // poses a l'execution depuis la liste `boutons` de `renderActions`.
  'appliquer', 'corbeilleSelection', 'supprimerConsole',
  'actionFab', 'activerJeu', 'actualiser', 'actualiserFiches',
  'ajouterCompte', 'ajouterPlateforme', 'allerSysteme', 'analyseGlobale',
  'auditer', 'backupSaves', 'basculerSuivi', 'basculerTaches', 'browse',
  'cancelJob', 'choisirEmulateur', 'choisirFichiers', 'classerImports',
  'clearCovers', 'clearFav', 'closeOnboard', 'convertAll', 'convertGame',
  'copierRetour', 'deployPick', 'detect', 'dismissA2HS', 'doImport',
  'ecApply', 'ecApplyProfile', 'ecLoad', 'ecSaveProfile', 'edenRestore',
  'erApply', 'erPreview', 'erSync', 'forcerFiches', 'importerJeu',
  'creerCle', 'installApp', 'journalClear', 'journalCopy', 'loadSaves',
  'loadTrash', 'revoquerCle',
  'ludoAnnulerOnb', 'ludoFermer', 'ludoNouveau', 'ludoOuvrir',
  'ludoValider', 'mkTree', 'onbAller', 'onbChercherConsole',
  'onbChoisirDossier', 'onbCreerCompte', 'onbPrec', 'onbScanner',
  'onbScannerConsole', 'onbSuiv', 'onbTesterFiches', 'openGame',
  'openOnConsole', 'organize', 'oublierDossier', 'oublierTransfert',
  'ouvrirPlateforme', 'page', 'parcourir', 'purgeTrash', 'reloadImport',
  'renderJournal', 'renderLib', 'reorganizeLocal', 'reprendreTransfert',
  'restaurerSauvegarde', 'restore', 'sauvegarder', 'sendGame', 'setDpath',
  'setMouvement', 'setParPage', 'setSens', 'setSystem', 'setTaille',
  'setTheme', 'setTri', 'showOnboard', 'testerAuth', 'testerIgdb',
  'toggleDrop', 'toggleFav', 'toggleJournal', 'togglePair', 'togglePause',
  'trashFile', 'useDir', 'verify', 'voirEntretien', 'voirVersions',
  'wifiConnect', 'wifiDiscover', 'wifiForget', 'wifiPair', 'wifiSwitch',
  'wizCheck', 'wizStep',
]);

// Les cas qui ne se ramenent pas a « une methode, un argument ». Ceux-ci ont
// besoin de l'EVENEMENT : ce sont des fonds de fenetre, qui ne se ferment que
// si le clic les a touches eux et non leur contenu. Un appel sans l'evenement
// fermerait la fenetre des qu'on clique dedans.
const ACTES_SPECIAUX = {
  'closeDialog': (el, ev) => app.closeDialog(ev),
  'closeGame': (el, ev) => app.closeGame(ev),
  'toggleFavPop': (el, ev) => app.toggleFavPop(ev),
  'toggleTrashList': (el, ev) => app.toggleTrashList(ev),
  // Deux arguments : `data-val` n'en porte qu'un, et lui en faire porter une
  // liste rendrait ambigu le jour ou une action prendra un tableau.
  'verify-20': () => app.verify(false, 20),
  // La carte entiere est cliquable, et son geste depend de l'evenement
  // (touche enfoncee, bouton du milieu). Les boutons POSES DESSUS ont leur
  // propre `data-act` : `closest` retient le plus proche, donc le bouton
  // l'emporte sur la carte sans qu'on ait a arreter la propagation.
  'cardClick': (el, ev) => app.cardClick(ev, el.dataset.arg),
  // Prend l'element lui-meme : c'est de son image qu'on veut l'agrandissement.
  'loupeJaquette': el => app.loupeJaquette(el),
  // Fermer le panneau des taches ET ouvrir le depot : deux appels, un geste.
  'taches-vers-depot': () => { app.basculerTaches(false); app.toggleDrop(true); },
};

function argumentDe(el) {
  if (el.dataset.val !== undefined) return [JSON.parse(el.dataset.val)];
  if (el.dataset.arg !== undefined) {
    const a = [el.dataset.arg];
    if (el.dataset.arg2 !== undefined) a.push(el.dataset.arg2);
    if (el.dataset.arg3 !== undefined) a.push(el.dataset.arg3);
    return a;
  }
  if (/^(SELECT|INPUT|TEXTAREA)$/.test(el.tagName)) return [el.value];
  return [];
}

function distributeur(attribut, cle) {
  return ev => {
    const el = ev.target.closest('[' + attribut + ']');
    if (!el || el.disabled) return;
    const nom = el.dataset[cle];
    const special = ACTES_SPECIAUX[nom];
    if (special) { special(el, ev); return; }
    // Silence volontaire : un nom absent de la liste blanche ne fait RIEN. Le
    // test `test_gestes.py` verifie qu'aucun `data-act` de l'interface n'est
    // dans ce cas — c'est la qu'une faute de frappe doit se voir, pas ici.
    if (!ACTES.has(nom)) return;
    const f = app[nom];
    if (typeof f === 'function') f.apply(app, argumentDe(el));
  };
}

document.addEventListener('click', distributeur('data-act', 'act'));
document.addEventListener('change', distributeur('data-act-change', 'actChange'));
document.addEventListener('input', distributeur('data-act-input', 'actInput'));

// Un element rendu cliquable par `role="button"` doit repondre au clavier. Un
// vrai <button> le fait tout seul ; ici c'est une image, et c'est ce qu'un
// `onkeydown` ecrit a la main faisait sur la jaquette. En le posant une fois
// pour toutes, la regle vaut pour tout faux bouton present ou a venir.
document.addEventListener('keydown', ev => {
  if (ev.key !== 'Enter' && ev.key !== ' ') return;
  const el = ev.target.closest('[data-act][role=button]');
  if (!el) return;
  ev.preventDefault();
  el.click();
});

// `load` et `error` d'une image ne REMONTENT pas : aucun ecouteur sur
// `document` ne les verrait en phase de bouillonnement. Ils passent en
// revanche par la phase de CAPTURE, qui descend depuis document — d'ou le
// troisieme argument. C'est la seule facon de deleguer ces deux gestes.
for (const geste of ['load', 'error']) {
  document.addEventListener(geste, ev => {
    const img = ev.target;
    if (img.tagName !== 'IMG' || img.dataset.cover === undefined) return;
    if (geste === 'load') app.coverVue(img); else app.coverRate(img);
  }, true);
}

app.ACTES = ACTES;
app.ACTES_SPECIAUX = ACTES_SPECIAUX;
window.app = app;

// Sequence de demarrage. Tant que l'inventaire n'est pas revenu, on affiche un
/* ============================================================================
   APPARENCE — theme, animation des jaquettes, mouvement
   ----------------------------------------------------------------------------
   Le choix initial est pose par le script en tete de index.html, avant le
   premier rendu. Ce bloc-ci ne sert qu'a le CHANGER et a tenir les reglages a
   jour ; il n'a pas a s'executer pour que la page s'affiche correctement.
   ========================================================================== */

// Le libelle et la description de chaque variante. Le meme tableau sert a
// construire les vignettes et a nommer le reglage : deux listes separees
// finiraient par diverger.
const ANIMATIONS = [
  ['1', 'Affiche inclinée', 'La carte s\'incline et un reflet balaie la jaquette.'],
  ['2', 'Élévation et halo', 'La carte se détache du fond, cerclée de laiton.'],
  ['5', 'Profondeur', 'La jaquette et l\'étiquette bougent à des vitesses différentes.'],
  ['4', 'Liseré tournant', 'Un filet lumineux parcourt le bord de la carte.'],
  ['3', 'Titre révélé', 'La jaquette occupe toute la carte ; le titre remonte au survol.'],
  ['0', 'Sobre', 'La carte monte de trois pixels. L\'effet d\'origine.'],
  ['aucune', 'Aucune', 'Le survol se contente de marquer la carte visée.'],
];

// La couleur de la barre systeme sur mobile suit le fond de page : sans cela,
// l'encoche reste noire au milieu d'une interface claire.
const TEINTE_BARRE = {sombre: '#141216', clair: '#efeae4'};

// `matchMedia` manque dans le DOM simplifie des tests Node, et un navigateur
// tres ancien peut l'ignorer. Son absence vaut « aucune preference exprimee »,
// ce qui ramene au theme sombre : le defaut du projet.
function media(requete) {
  return typeof matchMedia === 'function' ? matchMedia(requete) : null;
}

const CLAIR_SYSTEME = '(prefers-color-scheme: light)';

function themeEffectif() {
  const t = document.documentElement.dataset.theme || 'sombre';
  if (t !== 'auto') return t;
  const m = media(CLAIR_SYSTEME);
  return m && m.matches ? 'clair' : 'sombre';
}

function poserApparence(cle, valeur, permis) {
  if (!permis.includes(valeur)) return;
  const d = document.documentElement;
  if (d.dataset[cle] === valeur) return;
  // Le fondu n'est actif QUE pendant le changement : une transition
  // permanente sur `background` rendrait poisseux chaque survol de ligne.
  if (cle === 'theme') {
    d.classList.add('vire');
    setTimeout(() => d.classList.remove('vire'), 420);
  }
  d.dataset[cle] = valeur;
  try { localStorage.setItem(cle, valeur); } catch (e) { /* navigation privee */ }
  majApparence();
}

function majApparence() {
  const d = document.documentElement;
  const paire = [['s-theme', d.dataset.theme], ['s-mvt', d.dataset.mvt]];
  for (const [id, actif] of paire) {
    const bloc = $(id);
    if (!bloc) continue;
    bloc.querySelectorAll('button').forEach(b => {
      const on = b.dataset.val === actif;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
    });
  }
  document.querySelectorAll('#s-carte .animopt').forEach(b =>
    b.classList.toggle('on', b.dataset.apercu === d.dataset.carte));
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', TEINTE_BARRE[themeEffectif()]);
}

function construireChoixCartes() {
  const hote = $('s-carte');
  if (!hote || hote.childElementCount) return;
  for (const [cle, nom, aide] of ANIMATIONS) {
    const b = document.createElement('button');
    b.className = 'animopt';
    b.type = 'button';
    b.dataset.apercu = cle;
    // Ces deux attributs sont poses au chargement du module, donc AVANT que
    // le catalogue ne soit lu — et leur valeur est assemblee, donc cle de
    // rien. Deux raisons independantes de rester en francais, qu'aucun
    // controle sur le source ne pouvait reveler.
    poserAttr(b, 'title', aide);
    poserAttr(b, 'aria-label', '%s — %s', nom, aide);
    // La vignette imite une carte de jeu — un rectangle de jaquette surmonte
    // d'un bandeau d'etat — sans porter de vraie pochette : une image de jeu
    // ici laisserait croire que le reglage ne concerne que ce jeu-la. Un
    // simple numero, lui, ne montrait pas ce que l'effet fait a une carte.
    const vue = document.createElement('span');
    vue.className = 'apercu';
    const img = document.createElement('img');
    img.className = 'apimg';
    img.alt = '';
    // La source arrive plus tard : au moment ou ce bloc se construit, la
    // ludotheque n'est pas encore lue. En attendant, le degrade tient lieu
    // de jaquette.
    //
    // Si elle echoue — et elle echoue des que le jeu choisi n'a pas encore de
    // pochette en cache, ce qui est le cas courant d'une installation neuve —
    // on retombe sur la pochette generique AU LIEU de retirer l'image. La
    // retirer laissait l'apercu vide pour de bon : les trois effets a comparer
    // n'avaient plus rien a habiller, et aucun rechargement n'y changeait rien.
    img.onerror = function () {
      if (this.dataset.repli) { this.remove(); return; }   // meme le repli a echoue
      this.dataset.repli = '1';
      this.src = JAQUETTE_EXEMPLE;
    };
    vue.appendChild(img);
    const bandeau = document.createElement('span');
    bandeau.className = 'apbandeau';
    vue.appendChild(bandeau);
    const lab = document.createElement('span');
    lab.className = 'anom';
    lab.textContent = nom;
    // `appendChild` plutot que `append` : c'est la seule des deux que
    // fournit le DOM simplifie des tests, et elle suffit ici.
    b.appendChild(vue);
    b.appendChild(lab);
    b.onclick = () => app.setCarte(cle);
    hote.appendChild(b);
  }
  traduireDOM(hote);
  majApercuJaquette();
  majApparence();
}

// Un rectangle gris ne montre pas grand-chose : c'est sur une VRAIE pochette
// qu'on juge un reflet ou une inclinaison. On prend donc le premier jeu de la
// ludotheque qui en a une, plutot qu'une image livree avec l'outil — celle-ci
// aurait vieilli a part, et n'aurait rien dit du rendu sur les jaquettes de
// l'utilisateur.
// Aucune pochette disponible — installation neuve, aucune fiche en cache, ou
// simplement une ludotheque sans jeu Switch. L'apercu restait alors vide, et
// les trois effets a comparer n'avaient rien a habiller : on reglait a
// l'aveugle. On dessine donc une pochette generique. Elle ne represente aucun
// jeu, ce qui est exactement ce qu'on veut ici — et elle est en `data:`, donc
// servie par la page elle-meme, sans requete ni exception a la CSP.
const JAQUETTE_EXEMPLE = 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 450">' +
    '<defs><linearGradient id="f" x1="0" y1="0" x2="0.4" y2="1">' +
      '<stop offset="0" stop-color="#33344180"/>' +
      '<stop offset="1" stop-color="#15161d"/></linearGradient></defs>' +
    '<rect width="300" height="450" fill="#1b1c24"/>' +
    '<rect width="300" height="450" fill="url(#f)"/>' +
    // La silhouette d'une cartouche, la meme que sur une carte sans jaquette :
    // l'apercu doit ressembler a ce que l'utilisateur verra vraiment.
    '<rect x="110" y="146" width="80" height="126" rx="13" fill="#40425200"' +
      ' stroke="#5a5d70" stroke-width="3"/>' +
    '<rect x="132" y="240" width="36" height="13" rx="4" fill="#5a5d70"/>' +
  '</svg>');

function jaquetteExemple() {
  let liste = [];
  // Meme en cas d'echec, on rend la pochette generique : un apercu vide ne
  // dit rien, et l'echec ici n'a rien a voir avec le reglage qu'on regarde.
  try { liste = jeuxUnifies() || []; } catch (e) { return JAQUETTE_EXEMPLE; }
  const v = (DATA && DATA.covers_v) || 0;
  for (const x of liste) {
    const g = (x && x.g) || x;
    if (!g || (!g.tid && !g.name)) continue;
    if (sansFiche(g)) continue;             // fiche absente : jaquette probable­ment vide
    return '/cover/' + (g.tid || '') + '?v=' + v +
           '&name=' + encodeURIComponent(g.name || '');
  }
  return JAQUETTE_EXEMPLE;
}

function majApercuJaquette() {
  const hote = $('s-carte');
  if (!hote) return;
  const src = jaquetteExemple();
  if (!src) return;
  hote.querySelectorAll('.apimg').forEach(img => {
    if (img.getAttribute('src') !== src) img.setAttribute('src', src);
  });
}

// En « automatique », le systeme peut basculer pendant que la page est
// ouverte (coucher du soleil, mode nuit programme) : la teinte de la barre
// doit suivre, les couleurs le font deja seules via la requete media.
(function () {
  const suivi = media(CLAIR_SYSTEME);
  if (suivi && suivi.addEventListener) suivi.addEventListener('change', majApparence);
})();

// L'en-tete ne prend son ombre qu'une fois la page defilee : au repos, une
// ombre permanente donne l'impression d'un bandeau qui flotte au-dessus du
// vide.
(function () {
  const tete = document.querySelector('header');
  if (!tete) return;
  let prevu = false;
  addEventListener('scroll', () => {
    if (prevu) return;
    prevu = true;
    requestAnimationFrame(() => {
      prevu = false;
      tete.classList.toggle('defile', scrollY > 6);
      // Compactage : deux seuils differents, sinon la barre grandit et
      // retrecit sans arret quand on s'arrete pile a la limite — et comme
      // elle change la hauteur de page, elle provoquerait sa propre bascule.
      const compact = document.body.classList.contains('compact');
      if (!compact && scrollY > 220) document.body.classList.add('compact');
      else if (compact && scrollY < 140) document.body.classList.remove('compact');
      // La hauteur des barres ne change qu'a la bascule. La remesurer a chaque
      // image forcerait un calcul de mise en page a chaque cran de molette,
      // pour un resultat identique 99 fois sur 100.
      if (document.body.classList.contains('compact') !== compact) {
        // La transition dure : on relit une fois qu'elle est posee.
        setTimeout(mesurerBarres, 320);
      }
    });
  }, {passive: true});
})();

/* ============================================================================
   LOUPE — la jaquette en grand
   ----------------------------------------------------------------------------
   Une pochette de 104 px dans la fiche ne se regarde pas, elle s'identifie.
   Pour la LIRE — la tranche, le logo de l'editeur, la mention PEGI, le petit
   texte du dos — il faut l'agrandir et pouvoir s'y promener.

   Le deplacement se fait au curseur plutot qu'avec des barres : on pointe le
   coin qu'on veut voir, il vient. C'est le geste d'une loupe posee sur une
   photo, et il ne demande rien a apprendre.
   ========================================================================== */
// Inclinaison maximale, en degres. Au-dela, l'affiche se deforme au lieu de
// tourner : le raccourci de perspective devient plus visible que le relief.
const LOUPE_INCLIN = 11;

function loupeEl() {
  let el = $('loupe');
  if (el) return el;
  el = document.createElement('div');
  el.id = 'loupe';
  el.className = 'loupe';
  el.innerHTML =
    '<div class="loupecadre" id="loupecadre">' +
      '<div class="loupeplan" id="loupeplan">' +
        '<img id="loupeimg" alt="">' +
        '<span class="loupereflet" id="loupereflet"></span>' +
      '</div>' +
    '</div>' +
    '<div class="loupepied"><span id="loupetitre"></span>' +
      '<span class="loupeaide">L\'affiche suit la souris  ·  clic ou Échap pour fermer</span>' +
    '</div>';
  document.body.appendChild(el);

  const cadre = el.querySelector('#loupecadre');
  const plan = el.querySelector('#loupeplan');
  const reflet = el.querySelector('#loupereflet');

  // L'affiche ne grossit pas : elle TOURNE. On la regarde sous un angle, comme
  // un boitier qu'on incline dans la main, et la lumiere glisse dessus. Le
  // zoom, lui, obligeait a promener la souris pour reconstituer une image
  // qu'on ne voyait jamais en entier.
  cadre.addEventListener('mousemove', ev => {
    const r = cadre.getBoundingClientRect();
    // -1 a gauche/en haut, +1 a droite/en bas.
    const x = ((ev.clientX - r.left) / r.width) * 2 - 1;
    const y = ((ev.clientY - r.top) / r.height) * 2 - 1;
    plan.style.transform =
      'rotateY(' + (x * LOUPE_INCLIN).toFixed(2) + 'deg)' +
      ' rotateX(' + (-y * LOUPE_INCLIN).toFixed(2) + 'deg)';
    // Le point brillant se place la ou la souris est : c'est ce qui fait
    // croire a une surface vernie plutot qu'a une image qui pivote.
    reflet.style.setProperty('--rx', ((x + 1) / 2 * 100).toFixed(1) + '%');
    reflet.style.setProperty('--ry', ((y + 1) / 2 * 100).toFixed(1) + '%');
    reflet.style.opacity = '1';
  });
  cadre.addEventListener('mouseleave', () => {
    plan.style.transform = '';
    reflet.style.opacity = '0';
  });
  cadre.addEventListener('click', ev => {
    ev.stopPropagation();
    fermerLoupe();
  });
  el.addEventListener('click', fermerLoupe);
  return el;
}

function ouvrirLoupe(src, titre) {
  if (!src) return;
  const el = loupeEl();
  const img = $('loupeimg');
  $('loupeplan').style.transform = '';
  $('loupereflet').style.opacity = '0';
  img.src = src;
  img.alt = titre || '';
  $('loupetitre').textContent = titre || '';
  el.classList.add('on');
}

function fermerLoupe() {
  const el = $('loupe');
  if (el) el.classList.remove('on');
}

function loupeOuverte() {
  const el = $('loupe');
  return !!el && el.classList.contains('on');
}

/* ============================================================================
   PALETTE DE COMMANDES
   ----------------------------------------------------------------------------
   Sur 273 jeux, retrouver un titre a la souris est le vrai goulot : deplier le
   selecteur de plateforme, viser le champ, effacer, taper, parcourir. La
   palette fait les deux choses d'un coup — aller a un JEU, ou declencher une
   ACTION — au clavier, sans quitter les mains.

   La recherche est « approximative par sous-suite » : les lettres tapees
   doivent apparaitre dans l'ordre, pas forcement cote a cote. « anch » trouve
   « ANimal CHrossing »… et surtout « hgl » trouve « HoGwarts Legacy ». Une
   recherche stricte obligerait a connaitre l'orthographe exacte, ce qui est
   precisement ce qu'on cherche a eviter.
   ========================================================================== */

// Les actions offertes. Chaque entree porte de quoi la retrouver (`mots`) :
// « sombre » doit tomber sur le theme meme si le libelle dit « Thème sombre ».
function commandesDisponibles() {
  const c = [
    // i18n:ok - les seconds champs sont des mots-cles de recherche,
    // jamais affiches ; seuls les libelles le sont.
    ['Aller à la bibliothèque', 'jeux grille', () => app.tab('jeux')],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Ouvrir les réglages', 'settings options', () => app.tab('settings')],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Actualiser la bibliothèque', 'refresh relire', () => app.actualiser()],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Chercher les fiches manquantes', 'jaquettes resume metadata', () => app.actualiserFiches()],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Importer des jeux', 'ajouter deposer fichiers', () => app.toggleDrop(true)],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Ouvrir le journal', 'log evenements terminal', () => app.toggleJournal()],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Tout cocher', 'selection tous', () => app.deployPick(1)],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Tout décocher', 'selection aucune annuler', () => app.deployPick(0)],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Thème sombre', 'apparence nuit', () => app.setTheme('sombre')],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Thème clair', 'apparence jour blanc', () => app.setTheme('clair')],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Thème automatique', 'apparence systeme', () => app.setTheme('auto')],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Couper les animations', 'mouvement aucun repos', () => app.setMouvement('aucun')],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Rétablir les animations', 'mouvement complet', () => app.setMouvement('complet')],  // i18n:ok - 2e champ : mot-cle de recherche
    ['Voir l\'état de l\'installation', 'diagnostic sante', () => app.showOnboard()],  // i18n:ok - 2e champ : mot-cle de recherche
  ];
  // Chaque plateforme devient une destination : c'est le menu qu'on ouvre le
  // plus souvent, et il est en haut de page, loin des mains.
  for (const s of (SYSTEMS || [])) {
    c.push(['Plateforme : ' + s.name, 'console systeme ' + (s.folder || ''),
            () => app.setSystem(s.key)]);
  }
  return c.map(([titre, mots, faire]) => ({titre, mots, faire, type: 'action'}));
}

// Score d'une sous-suite. Plus les lettres trouvees sont contigues et plus
// elles tombent en debut de mot, meilleur est le score — sans quoi « mario »
// remonterait n'importe quel titre contenant ces cinq lettres eparpillees.
function scoreFlou(texte, cherche) {
  const t = texte.toLowerCase(), q = cherche;
  let i = 0, score = 0, suite = 0;
  for (let j = 0; j < t.length && i < q.length; j++) {
    if (t[j] !== q[i]) { suite = 0; continue; }
    suite++;
    score += 1 + suite;
    if (j === 0 || /[\s:,\-–—(\[]/.test(t[j - 1])) score += 6;   // debut de mot
    i++;
  }
  if (i < q.length) return -1;                    // toutes les lettres ? sinon rien
  return score - t.length * 0.02;                 // a egalite, le titre le plus court
}

const PALETTE_MAX = 9;
let PALETTE_CHOIX = [];
let PALETTE_INDEX = 0;

function paletteEl() {
  let el = $('palette');
  if (el) return el;
  el = document.createElement('div');
  el.id = 'palette';
  el.className = 'palette';
  el.innerHTML =
    '<div class="palboite" role="dialog" aria-label="Palette de commandes">' +
      '<input type="text" id="palsaisie" autocomplete="off" spellcheck="false"' +
        ' placeholder="Aller à un jeu, lancer une action…"' +
        ' data-i18n-ph="palette.placeholder" aria-label="Rechercher">' +
      '<div class="palliste" id="palliste" role="listbox"></div>' +
      '<div class="palpied"><span><b>↑</b><b>↓</b> parcourir</span>' +
        '<span><b>↵</b> ouvrir</span><span><b>Échap</b> fermer</span></div>' +
    '</div>';
  document.body.appendChild(el);
  el.addEventListener('click', ev => { if (ev.target === el) fermerPalette(); });
  $('palsaisie').addEventListener('input', () => remplirPalette($('palsaisie').value));
  traduireDOM(el);
  return el;
}

function remplirPalette(q) {
  const cherche = String(q || '').trim().toLowerCase();
  const candidats = [];

  for (const cmd of commandesDisponibles()) {
    const s = cherche
      ? Math.max(scoreFlou(cmd.titre, cherche), scoreFlou(cmd.mots, cherche) - 4)
      : 0;
    if (s >= 0) candidats.push({...cmd, score: s + 2});   // les actions passent devant a egalite
  }
  let jeux = [];
  try { jeux = jeuxUnifies(); } catch (e) { jeux = []; }
  for (const x of jeux) {
    const nom = nomJeu(x.g);
    const s = cherche ? scoreFlou(nom, cherche) : 0;
    if (s < 0) continue;
    candidats.push({
      titre: nom, type: 'jeu', score: s,
      detail: [x.g.sysNom, fmt(x.g.size)].filter(Boolean).join('  ·  '),
      etat: x.e && ETATS[x.e.etat] ? [ETATS[x.e.etat][0], ETAT_COURT[x.e.etat]] : null,
      faire: () => app.openGame(x.g.key),
    });
  }

  candidats.sort((a, b) => b.score - a.score);
  PALETTE_CHOIX = candidats.slice(0, PALETTE_MAX);
  PALETTE_INDEX = 0;
  dessinerPalette();
}

function dessinerPalette() {
  const liste = $('palliste');
  if (!PALETTE_CHOIX.length) {
    liste.innerHTML = '<div class="palvide">Rien ne correspond.</div>';
    traduireDOM(liste);
    return;
  }
  liste.innerHTML = PALETTE_CHOIX.map((c, i) =>
    '<div class="palitem' + (i === PALETTE_INDEX ? ' on' : '') + '" role="option" data-i="' + i + '">' +
      '<span class="paltype">' + (c.type === 'jeu' ? 'JEU' : 'ACTION') + '</span>' +
      '<span class="paltitre">' + esc(c.titre) + '</span>' +
      (c.etat ? '<span class="paletat ' + c.etat[0] + '">' + esc(c.etat[1]) + '</span>' : '') +
      (c.detail ? '<span class="paldetail">' + esc(c.detail) + '</span>' : '') +
    '</div>').join('');
  liste.querySelectorAll('.palitem').forEach(el =>
    el.addEventListener('click', () => lancerPalette(+el.dataset.i)));
  traduireDOM(liste);
}

function bougerPalette(pas) {
  if (!PALETTE_CHOIX.length) return;
  PALETTE_INDEX = (PALETTE_INDEX + pas + PALETTE_CHOIX.length) % PALETTE_CHOIX.length;
  dessinerPalette();
  const on = $('palliste').querySelector('.palitem.on');
  if (on) on.scrollIntoView({block: 'nearest'});
}

function lancerPalette(i) {
  const c = PALETTE_CHOIX[i == null ? PALETTE_INDEX : i];
  if (!c) return;
  // On ferme AVANT d'agir : plusieurs actions ouvrent une fenetre, et la
  // palette resterait posee par-dessus.
  fermerPalette();
  try { c.faire(); } catch (e) { toast('Action impossible.', 'warn'); }
}

function ouvrirPalette() {
  const el = paletteEl();
  el.classList.add('on');
  $('palsaisie').value = '';
  remplirPalette('');
  $('palsaisie').focus();
}

function fermerPalette() {
  const el = $('palette');
  if (el) el.classList.remove('on');
}

function paletteOuverte() {
  const el = $('palette');
  return !!el && el.classList.contains('on');
}

/* ============================================================================
   CLAVIER
   ----------------------------------------------------------------------------
   L'outil se pilote depuis un ordinateur, et tout y passait par la souris : viser une
   jaquette de 158 px pour lire son etat, revenir a la recherche, recommencer.
   Les raccourcis retenus sont ceux que l'on trouve dans un gestionnaire de
   fichiers ou une mediatheque — rien a apprendre.

     /            aller a la recherche          Fleches  se deplacer dans la grille
     Entree       ouvrir la fiche               Espace   cocher / decocher
     Debut / Fin  premiere / derniere carte     Echap    fermer, ou vider la recherche
   ========================================================================== */

// Un champ de saisie garde ses touches : y taper « / » doit ecrire « / ».
function dansUneSaisie(el) {
  if (!el) return false;
  const t = (el.tagName || '').toUpperCase();
  return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT' || el.isContentEditable;
}

function cartesVisibles() {
  return [...document.querySelectorAll('#lib .gcard')];
}

// Nombre de cartes par rangee, mesure plutot que calcule : la grille est en
// `auto-fill`, donc le compte depend de la largeur reelle et de la taille
// choisie. Toutes les cartes d'une rangee partagent leur bord superieur.
function cartesParRangee(cartes) {
  if (cartes.length < 2) return 1;
  const haut = cartes[0].getBoundingClientRect().top;
  let n = 0;
  for (const c of cartes) {
    if (Math.abs(c.getBoundingClientRect().top - haut) > 4) break;
    n++;
  }
  return Math.max(1, n);
}

function bougerDansGrille(pas) {
  const cartes = cartesVisibles();
  if (!cartes.length) return false;
  const ici = cartes.indexOf(document.activeElement.closest
    ? document.activeElement.closest('.gcard') : null);
  let cible;
  if (ici < 0) cible = 0;                      // rien de vise : on entre par la premiere
  else cible = Math.min(cartes.length - 1, Math.max(0, ici + pas));
  cartes[cible].focus({preventScroll: true});
  cartes[cible].scrollIntoView({block: 'nearest', behavior: 'smooth'});
  return true;
}

addEventListener('keydown', ev => {
  // ⌘K sur Mac, Ctrl+K ailleurs : la combinaison est celle qu'attendent tous
  // ceux qui ont deja vu une palette. Elle passe AVANT le filtre des
  // modificateurs, et meme depuis un champ de saisie.
  if ((ev.metaKey || ev.ctrlKey) && (ev.key === 'k' || ev.key === 'K')) {
    ev.preventDefault();
    paletteOuverte() ? fermerPalette() : ouvrirPalette();
    return;
  }
  // Tant que la palette est ouverte, elle capte le clavier : les fleches y
  // parcourent la liste, elles ne doivent pas bouger la grille derriere.
  if (paletteOuverte()) {
    if (ev.key === 'Escape') { ev.preventDefault(); fermerPalette(); }
    else if (ev.key === 'ArrowDown') { ev.preventDefault(); bougerPalette(1); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); bougerPalette(-1); }
    else if (ev.key === 'Enter') { ev.preventDefault(); lancerPalette(); }
    return;
  }
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const saisie = dansUneSaisie(ev.target);

  if (ev.key === 'Escape') {
    // La loupe est posee par-dessus la fiche : elle se ferme la premiere.
    if (loupeOuverte()) return fermerLoupe();
    if ($('modal').classList.contains('open')) return app.closeGame();
    if ($('dialog').classList.contains('open')) return app.closeDialog();
    cacherApercu();
    // Dans la recherche, Echap efface d'abord, puis rend la main.
    if (ev.target === $('filter')) {
      if ($('filter').value) { $('filter').value = ''; app.renderLib(); }
      else $('filter').blur();
    }
    return;
  }
  if (saisie) return;
  if ($('modal').classList.contains('open') || $('dialog').classList.contains('open')) return;
  if (!$('panel-jeux').classList.contains('active')) return;

  const carte = document.activeElement && document.activeElement.closest
    ? document.activeElement.closest('#lib .gcard') : null;
  const cartes = cartesVisibles();
  const colonnes = cartesParRangee(cartes);

  switch (ev.key) {
    case '/':
      ev.preventDefault();
      $('filter').focus();
      $('filter').select();
      return;
    case 'ArrowRight': ev.preventDefault(); bougerDansGrille(1); return;
    case 'ArrowLeft':  ev.preventDefault(); bougerDansGrille(-1); return;
    case 'ArrowDown':  ev.preventDefault(); bougerDansGrille(colonnes); return;
    case 'ArrowUp':    ev.preventDefault(); bougerDansGrille(-colonnes); return;
    case 'Home':
      if (!cartes.length) return;
      ev.preventDefault();
      cartes[0].focus();
      cartes[0].scrollIntoView({block: 'center', behavior: 'smooth'});
      return;
    case 'End':
      if (!cartes.length) return;
      ev.preventDefault();
      cartes[cartes.length - 1].focus();
      cartes[cartes.length - 1].scrollIntoView({block: 'center', behavior: 'smooth'});
      return;
    case 'Enter':
      if (!carte) return;
      ev.preventDefault();
      app.openGame(carte.dataset.key);
      return;
    case ' ':
      if (!carte) return;
      ev.preventDefault();
      // La grille est redessinee : le focus DOM est perdu avec l'ancien
      // noeud, on le repose sur la carte qui a pris sa place.
      app.cardClick({shiftKey: ev.shiftKey}, carte.dataset.key);
      redonnerFocus(carte.dataset.key);
      return;
    default: return;
  }
});

function redonnerFocus(cle) {
  requestAnimationFrame(() => {
    const c = document.querySelector('#lib .gcard[data-key="' +
      (window.CSS && CSS.escape ? CSS.escape(cle) : cle) + '"]');
    if (c) c.focus({preventScroll: true});
  });
}

/* ============================================================================
   APERCU AU SURVOL PROLONGE
   ----------------------------------------------------------------------------
   Ouvrir la fiche pour savoir si un jeu tient sur la console, puis la fermer,
   puis recommencer sur le suivant : c'est le geste qu'on repete le plus. Un
   survol appuye repond a la question sans quitter la grille.

   Le delai compte autant que le contenu : trop court, l'apercu clignote des
   qu'on traverse la grille ; trop long, on l'a deja abandonne. 600 ms
   correspond a « je me suis arrete sur celui-la ».
   ========================================================================== */
const APERCU_MS = 600;
let APERCU_MINUTEUR = 0;
let APERCU_CARTE = null;

function apercuEl() {
  let el = $('apercujeu');
  if (!el) {
    el = document.createElement('div');
    el.id = 'apercujeu';
    el.className = 'apercujeu';
    el.setAttribute('role', 'tooltip');
    document.body.appendChild(el);
  }
  return el;
}

function cacherApercu() {
  clearTimeout(APERCU_MINUTEUR);
  APERCU_CARTE = null;
  const el = $('apercujeu');
  if (el) el.classList.remove('on');
}

function contenuApercu(g, e) {
  const bouts = [];
  const pousser = (etiq, val) => bouts.push(
    '<div class="apl"><span>' + esc(etiq) + '</span><b>' + esc(val) + '</b></div>');
  pousser('Taille', fmt(g.size));
  if (g.sysNom) pousser('Plateforme', g.sysNom);
  if (g.files && g.files.length) pousser('Fichiers', String(g.files.length));
  if (g.updCount) pousser('Mises à jour', String(g.updCount));
  if (g.dlcCount) pousser('DLC', String(g.dlcCount));
  const p = (e && e.presence) || {};
  if (p.console) pousser('Console', TITRE_PRESENCE[p.console] || '—');
  const resume = resumeUtile(g);
  return '<div class="aptitre">' + esc(nomJeu(g)) + '</div>' +
    (e ? '<div class="apetat ' + ETATS[e.etat][0] + '">' + esc(e.txt) + '</div>' : '') +
    '<div class="apgrille">' + bouts.join('') + '</div>' +
    (resume ? '<p class="apresume">' + esc(extrait(resume, 190)) + '</p>' : '');
}

function poserApercu(carte) {
  const g = app.gameByKey(carte.dataset.key);
  if (!g) return;
  let e = null;
  try { e = etatDe(g); } catch (err) { e = null; }
  const el = apercuEl();
  el.innerHTML = contenuApercu(g, e);
  traduireDOM(el);
  el.classList.add('on');

  // Place l'apercu du cote ou il tient. Le mesurer APRES l'avoir rendu
  // visible : un element cache n'a pas de dimensions.
  const r = carte.getBoundingClientRect();
  const b = el.getBoundingClientRect();
  const marge = 12;
  let x = r.right + marge;
  if (x + b.width > innerWidth - 8) x = r.left - b.width - marge;
  if (x < 8) x = Math.max(8, Math.min(r.left, innerWidth - b.width - 8));
  let y = r.top;
  if (y + b.height > innerHeight - 8) y = innerHeight - b.height - 8;
  el.style.left = Math.round(x) + 'px';
  el.style.top = Math.round(Math.max(8, y)) + 'px';
}

// Un seul ecouteur pour toute la grille : poser un `mouseenter` sur chaque
// carte obligerait a le refaire a chaque rendu.
// `mousemove` plutot que `mouseover` : ce dernier ne se declenche qu'au
// franchissement d'une frontiere, donc jamais quand la grille se redessine
// sous un curseur immobile — ni sous un navigateur pilote. Le cout est nul,
// la premiere ligne du gestionnaire ecarte tout ce qui ne change rien.
document.addEventListener('mousemove', ev => {
  if (!matchMedia('(hover: hover)').matches) return;
  if (document.documentElement.dataset.mvt === 'aucun') return;
  const carte = ev.target.closest && ev.target.closest('#lib .gcard');
  if (carte === APERCU_CARTE) return;
  cacherApercu();
  if (!carte) return;
  // Pas d'apercu par-dessus une fenetre ouverte : il la recouvrirait.
  if ($('modal').classList.contains('open')) return;
  APERCU_CARTE = carte;
  APERCU_MINUTEUR = setTimeout(() => poserApercu(carte), APERCU_MS);
});
addEventListener('scroll', cacherApercu, {passive: true});
document.addEventListener('click', cacherApercu);

// Douze silhouettes : de quoi remplir la premiere hauteur d'ecran sans
// pretendre annoncer le nombre reel de jeux, qu'on ne connait pas encore.
function poserSquelettes(combien) {
  const hote = $('libsquelette');
  if (!hote || hote.childElementCount) return;
  for (let i = 0; i < combien; i++) {
    const c = document.createElement('div');
    c.className = 'gcard squelette-carte';
    c.innerHTML = '<div class="art"></div><div class="cap">' +
      '<div class="gname"></div><div class="meta"></div></div>';
    hote.appendChild(c);
  }
}

poserSquelettes(12);
construireChoixCartes();
majApparence();

// etat de chargement plutot que des compteurs a zero et une console « absente » :
// afficher une information fausse, meme une seconde, est pire que ne rien dire.
(async () => {
  document.body.classList.add('chargement');
  renderHost();
  renderA2HS();
  app.langLoad();
  try {
    await app.scan();              // fichiers du serveur : la base de tout
    // La bibliotheque s'affiche des que le serveur a repondu. Attendre en plus la
    // console retardait tout l'ecran de deux secondes et demie pour une
    // information qui n'occupe que trois puces de filtre — et `renderLib`
    // sait deja se passer d'elle.
    // Les lancer EN PARALLELE a ete essaye : le premier affichage y gagnait
    // 0,7 s, mais les deux lectures se disputaient le disque et l'adb, et
    // l'etat de la console mettait 10 s au lieu de 2,5 s a arriver. Mauvais
    // echange.
    document.body.classList.remove('chargement');
    document.body.classList.add('pret');
    // La vue « toutes les plateformes » montre DEJA les jeux Switch a cet
    // instant : `jeuxTous()` part de `GAMES`, que `scan()` vient de remplir.
    // Les autres plateformes s'ajoutent ensuite, sans que rien ne disparaisse
    // entre-temps. On ne l'attend donc pas avant d'afficher : mesure a 21 ms a
    // froid, mais une ludotheque avec quinze plateformes n'a aucune raison de
    // retarder le premier ecran.
    app.setSystem(SYS);
    // `DEMARRAGE` reste vrai : il ne dit pas « la page est visible » mais
    // « l'utilisateur n'a encore rien demande ». Le passer a faux ici ferait
    // remonter en notifications les messages de la console — « Console
    // détectée », « 152 fichiers sur la console » — que personne n'a
    // sollicites et qui sont deja au journal.
    await app.reveilConsole();     // etat de la console, puis ses fichiers
    // La console est maintenant connue : `systems.tout()` peut lire son arbre,
    // ce qu'il n'avait pas pu faire au premier appel. On refait donc UNE fois
    // la vue d'ensemble, sinon les fichiers presents uniquement sur la console
    // n'y apparaitraient jamais.
    if (vueTotale() && CONN.kind) { oublierCacheSysteme(); app.setSystem('all'); }
  } finally {
    document.body.classList.remove('chargement');
    document.body.classList.add('pret');
    DEMARRAGE = false;               // a partir d'ici, l'utilisateur agit
  }
  // le reste peut arriver apres : rien n'en depend pour un premier affichage
  app.checkHealth();
  app.erLoad();
  app.erDevices();
  // `scan()` a deja lu la liste des plateformes et l'attend : la redemander
  // ici la lisait deux fois a chaque lancement.
  // Les compteurs du selecteur dependent de ce que porte la console : on la lit
  // une fois, en arriere-plan, plutot que d'afficher des zeros trompeurs.
  if (CONN.kind) app.detecterPlateformes(true);
})();

/* ------------------------------------------------- bouton du journal mobile
   Le bouton pend au milieu du bord droit. Selon la page et la taille de
   l'ecran, il tombe pile sur ce qu'on veut lire — et il n'y avait aucun moyen
   de le pousser. On le rend glissable de haut en bas, et sa position tient
   d'une session a l'autre.

   Trois details qui font la difference entre « glissable » et « utilisable » :

   * un glissement ne doit pas ouvrir le journal. On distingue le clic du
     glissement par un seuil de quelques pixels, et on annule le clic qui suit
     un vrai deplacement — en phase de CAPTURE, pour passer avant le
     gestionnaire en ligne du bouton ;
   * la position est bornee a l'ecran et re-bornee au redimensionnement, sinon
     un bouton range en bas d'un grand ecran devient injoignable sur un petit ;
   * le clavier fait la meme chose. Une poignee qui n'obeit qu'a la souris
     n'existe pas pour qui n'en utilise pas. */
(function boutonJournalDeplacable() {
  const btn = $('journalbtn');
  if (!btn) return;
  const MARGE = 8, CLE = 'jfab-y', SEUIL = 4;

  function borner(y) {
    const h = btn.offsetHeight || 120;
    return Math.max(MARGE, Math.min(y, window.innerHeight - h - MARGE));
  }
  function poser(y, garder) {
    const v = borner(y);
    btn.style.top = v + 'px';
    btn.style.transform = 'none';
    if (garder) localStorage.setItem(CLE, String(v));
    return v;
  }
  const enregistre = parseInt(localStorage.getItem(CLE), 10);
  if (!isNaN(enregistre)) poser(enregistre, false);

  let depart = 0, origine = 0, bouge = false, actif = false, finGlisse = 0;
  btn.addEventListener('pointerdown', e => {
    if (e.button !== undefined && e.button !== 0) return;
    actif = true; bouge = false;
    depart = e.clientY;
    origine = btn.getBoundingClientRect().top;
    btn.setPointerCapture(e.pointerId);
  });
  btn.addEventListener('pointermove', e => {
    if (!actif) return;
    const delta = e.clientY - depart;
    if (!bouge && Math.abs(delta) < SEUIL) return;
    bouge = true;
    btn.classList.add('glisse');
    poser(origine + delta, false);
  });
  btn.addEventListener('pointerup', e => {
    if (!actif) return;
    actif = false;
    btn.classList.remove('glisse');
    try { btn.releasePointerCapture(e.pointerId); } catch (_) { /* deja relache */ }
    if (bouge) { poser(btn.getBoundingClientRect().top, true); finGlisse = performance.now(); }
  });
  btn.addEventListener('pointercancel', () => {
    actif = false; bouge = false; btn.classList.remove('glisse');
  });
  // Capture : le gestionnaire en ligne du bouton est en phase de bulle, donc
  // il passe apres celui-ci. C'est ce qui permet d'annuler le clic.
  btn.addEventListener('click', e => {
    // Fenetre courte plutot que drapeau persistant : un glissement qui ne
    // produit aucun clic — pointeur relache ailleurs, geste tactile annule —
    // laissait le drapeau leve, et c'est le clic suivant qui etait mange.
    if (performance.now() - finGlisse > 300) return;
    e.stopPropagation();
    e.preventDefault();
  }, true);

  btn.addEventListener('keydown', e => {
    if (!e.shiftKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
    e.preventDefault();
    poser(btn.getBoundingClientRect().top + (e.key === 'ArrowUp' ? -24 : 24), true);
  });

  window.addEventListener('resize', () => {
    const y = parseInt(localStorage.getItem(CLE), 10);
    if (!isNaN(y)) poser(y, false);
  });
})();
