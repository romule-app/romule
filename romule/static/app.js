"use strict";
// The game library's interface. All business state comes from the server;
// this file renders it, handles the tabs, the animations, and relays actions.

let DATA = {files: [], stats: {}, config: {}};
let GAMES = [];                 // jeux regroupes (vue bibliotheque)
let DGAMES = [];                // files listed on the console
let CONSET = new Set();          // fingerprints (tid|version) of the games on the console
let BROWSE_PATH = "";            // current folder of the console browser
let CIBLE_PARCOURS = 'roms';     // what the browser will save: 'roms', 'switch' or a platform
let TREE = {};                   // state of the GAMES/UPDATE/DLC folders on the console
let FILTER = "all";             // all | update | convert | clean
let CONN = {};                  // link to the console: {kind: 'usb'|'wifi'|null}
let CONN_INFO = null;           // identity of the linked console (name, serial)
let META = {};                  // {tid: {nom, resume}} — official details, cached
let NANDST = [];                // updates/DLC and their state as far as Eden goes
let NANDCONN = false;           // is the console answering?
let SYSTEMS = [];               // available consoles/systems
// The library opens on ALL platforms: that is what you own, not one slice of
// it. The user's previous choice wins — it was WRITTEN to local storage on
// every change, but never read back, so lost on every visit.
let SYS = (() => {
  try { return localStorage.getItem('systeme') || 'all'; } catch (e) { return 'all'; }
})();
let SGAMES = [];                // games of the current generic system
let SCONSOLE = [];              // that system's file names on the console
let SCONSOLE_PATHS = [];        // their full paths, so they can be removed
let SCONSOLE_TAILLES = {};      // size per path: the card used to show 0 bytes
let SCONSOLE_TITRES = {};       // official title per path, when it is known
let SALL = [];                  // every platform, for the overview
// What we have already received, per platform. A SESSION cache: it does not
// survive a page reload, and it is emptied as soon as the inventory moves —
// task end, "Refresh", file drop. A cache you cannot invalidate is a display
// bug on a timer.
const CACHE_SYS = {};
// Number of the request in flight: an answer slower than a second click must
// not overwrite the inventory of the platform finally chosen.
let CHARGE_SYS = 0;

function oublierCacheSysteme() {
  for (const k of Object.keys(CACHE_SYS)) delete CACHE_SYS[k];
}

function appliquerSysteme(d) {
  inventaireChange();
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
// Binary units are not written the same everywhere: "Gio" in French, "GiB" in
// English. They appear on EVERY cover — it was the most visible French in the
// whole English interface.
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

// A value entering a JavaScript STRING inside a handler attribute —
// `onclick="app.faire('HERE')"` — crosses TWO parsers: the HTML parser decodes
// the entities first, then the JavaScript engine compiles whatever is left.
//
// `esc()` only answers the first, and that is what made the hole invisible: it
// does turn the apostrophe into `&#39;`, but the HTML parser gives it back
// BEFORE the JavaScript is read. The string closes, and the rest of the value
// becomes code.
//
// There is nothing exotic about producing such a value: a card's key IS the
// file path, and nothing forbids an apostrophe in a file name.
// `x',alert(1),'.gba` is enough.
//
// So we escape for the JavaScript context FIRST, for the HTML context second.
// The order matters: the reverse would let `esc` reintroduce entities the
// JavaScript engine cannot read back.
//
// The real remedy is still to get these values out of attributes — `data-grp`
// already does so for the group key. While inline handlers are around, this
// encoding is what holds.
// An alias for `t()`, for the few functions whose parameter is already called
// `t` — a title ID, an element. Renaming the parameter would be cleaner; the
// alias avoids touching signatures used everywhere, and the guard in
// test_ui_injection.js still forbids the other shadowings.
const t18n = (texte, defaut) => t(texte, defaut);

const jsq = v => esc(JSON.stringify(String(v == null ? '' : v))
  .slice(1, -1)                    // JSON returns a quoted string
  .replace(/'/g, "\\'")            // which JSON itself does not escape
  // JSON lets raw U+2028/2029 through; the JavaScript engine long read them as
  // line terminators, hence as an unterminated string.
  .replace(/\u2028/g, '\\u2028')
  .replace(/\u2029/g, '\\u2029'));
// The official title in the chosen language, when the entry is cached;
// otherwise the file name. A file name says "[Game] Pokemon Sword
// [0100ABF...]" where the publisher says "Pokémon Sword".
// When no entry exists — an .xci pack carries no title ID and `nsz` fails to
// read it — we make the file name presentable rather than showing
// "Mario.Kart.8.Deluxe.(v3.0.3 & DLC).SuperXCI -MBC".
const GROUPES_SCENE = /\b(superxci|xci|nsp|nsz|xcz|mbc|upd|repack|nsw|switch|multi\d*|fr|eu|us|jp|eur|usa|jpn)\b/gi;

function nomLisible(fichier) {
  // any ROM extension, not only the Switch ones: ".gba", ".iso", ".chd"… The
  // 2-4 character bound avoids truncating a title.
  let s = String(fichier || '').replace(/\.[a-z0-9]{2,4}$/i, '');
  s = s.replace(/[\[\(][^\])]*[\])]/g, ' ');       // [tid], (EU), (v3.0.3 & DLC)
  s = s.replace(/\bv\d+(\.\d+)*\b/gi, ' ');        // v1.0.1, v262144
  // "scene" names separate with dots: we only replace when the name has more
  // of them than real spaces, so as not to break "Super Smash Bros."
  const pts = (s.match(/\./g) || []).length, esp = (s.match(/ /g) || []).length;
  if (pts > esp) s = s.replace(/\./g, ' ');
  s = s.replace(/[-_]+/g, ' ').replace(GROUPES_SCENE, ' ');
  // orphan brackets and parentheses: some names are malformed, like
  // "… [0100ABF008968000][v0][US])", and leave a lone parenthesis
  s = s.replace(/[\[\]{}()]/g, ' ');
  s = s.replace(/\s{2,}/g, ' ').replace(/^[\s.\-–]+|[\s.\-–]+$/g, '');
  return s || pretty(fichier);
}

function nomJeu(g) {
  const m = g && g.tid && META[String(g.tid).toLowerCase()];
  if (m && m.nom) return m.nom.replace(/^\(([^)]{2,14})\)\s*/, '').trim();
  // off-Switch: official title resolved by SteamGridDB, when it was fetched
  const t = g && (g.titre || (g.files && g.files[0] && g.files[0].titre));
  if (t) return t;
  return nomLisible(pretty((g && g.name) || ''));
}
// Where the shown summary came from. Today only one source requires citing —
// Wikipedia, under CC BY-SA — but the shape allows for others.
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
  // Off-Switch the summary comes from IGDB and travels with the game: without
  // this fallback, no description ever showed for those platforms.
  const f = g && (g.resume || (g.files && g.files[0] && g.files[0].resume));
  return f || '';
}

// Year and publisher, when the source supplies them (IGDB for non-Switch).
function contexteJeu(g) {
  const f = g && (g.files && g.files[0]) || g || {};
  return [f.annee || g.annee, f.editeur || g.editeur].filter(Boolean).join('  ·  ');
}
// A counter jumping from 34 to 10 in one go goes unnoticed: you cannot tell
// whether it changed, nor in which direction. Rolling it makes the movement
// say "that just moved, and it is going down".
const CHIFFRE_MS = 340;
const CHIFFRE_EN_COURS = new WeakMap();

function chiffreAnime(el, cible) {
  cible = Number(cible) || 0;
  const depart = Number(el.textContent.replace(/\D/g, ''));
  const enCours = CHIFFRE_EN_COURS.get(el);
  if (enCours) cancelAnimationFrame(enCours);
  // Nothing to tell: first render, unchanged value, motion switched off — or
  // the tests' simplified DOM, which has no animation clock.
  if (!Number.isFinite(depart) || depart === cible ||
      typeof requestAnimationFrame !== 'function' ||
      document.documentElement.dataset.mvt === 'aucun') {
    el.textContent = String(cible);
    return;
  }
  const t0 = performance.now();
  const pas = (maintenant) => {
    const p = Math.min(1, (maintenant - t0) / CHIFFRE_MS);
    // slow start then a sharp stop: the number "lands" on its value
    const doux = 1 - Math.pow(1 - p, 3);
    el.textContent = String(Math.round(depart + (cible - depart) * doux));
    if (p < 1) CHIFFRE_EN_COURS.set(el, requestAnimationFrame(pas));
    else CHIFFRE_EN_COURS.delete(el);
  };
  CHIFFRE_EN_COURS.set(el, requestAnimationFrame(pas));
}

// Cut cleanly on a word, never in the middle of one.
function extrait(t, n) {
  t = String(t || '').trim();
  if (t.length <= n) return t;
  const c = t.slice(0, n);
  return c.slice(0, Math.max(c.lastIndexOf(' '), n - 20)).replace(/[\s,;:.]+$/, '') + '…';
}

// replace the modifier colons of Switch file names with ':'
const pretty = s => String(s).replace(/[꞉∶：]/g, ':');
const tidBase = tid => {
  let n = parseInt(tid[12], 16); if (n % 2) n--;
  return tid.slice(0, 12) + n.toString(16) + '000';
};
function tidHtml(t) {   // the title ID, split up (detail view only)
  // The `tid` class is in CLASSES_DONNEES: it carries an identifier, which is
  // not translated. But when there is none, it carried a LABEL, which must be
  // — and so stayed French. The same defect as `cnom`, for the fourth time: a
  // class cannot be both a style and a marker. The label gets its own class.
  if (!t) return '<span class="tid-vide">' + esc(t18n('pas de title ID')) + '</span>';
  return '<span class="tid">' + t.slice(0, 12) + '<b>' + t[12] + '</b>' +
    t.slice(13) + '</span>';
}
// `discret`: the caller shows the refusal itself. A password that is too short
// is a correction to make, not a fault: the "An action did not complete"
// dialog would be beside the point.
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
    // An HTML response instead of JSON is the login page: the session expired,
    // or authentication was just switched on elsewhere. The raw message
    // ("Unexpected token '<'") told nobody anything.
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
// ----------------------------------------------------------- translations
// The labels live in romule/locales/<code>.json, never in the code. The FRENCH
// text is the translation key (the gettext principle). Two reasons: we do not
// invent 570 identifiers, and a missing translation falls back to a readable
// sentence rather than to "lib.filter.all".
//
// Translation is applied to the DOM once it is built, not at every place in the
// code that produces text. One observer therefore covers the whole interface,
// including what JavaScript generates, without touching 400 call sites — and
// without any possibility of forgetting one.
let I18N = {};
// Display language. The translation KEY stays the French sentence — the
// gettext principle this project adopted — but the default language is
// English: `en.json` translates those keys on load.
let LANGUE = 'en';

// What we NEVER translate: code, paths, and above all the user's data (game
// names, email addresses, file paths).
const NON_TRADUIT = new Set(['CODE', 'PRE', 'SCRIPT', 'STYLE', 'TEXTAREA']);
// These classes mark nodes whose ENTIRE content is data: a game title, an
// address, a path. They must never double as a style selector for interface
// text — that is the defect that froze `tid`, then `cnom`, then the whole log.
//
// `jline`, `brow` and `crumb` were taken out: they wrap a MIXTURE. A log line
// holds the timestamp, the level and the message; only the message is data.
// Wrapping them whole froze "Dossier vide.", ".. (dossier parent)" and the
// entire log, which therefore stayed French in an English interface.
//
// The data now carries `data-i18n-skip`, the attribute `traduisible()` already
// reads: it marks the exact node, not its neighbourhood.
const CLASSES_DONNEES = ['gname', 'compte-mail', 'pfchemin', 'tid',
                         'hostchip', 'cnom'];

// The HTML's sentences are spread over several lines: the text node holds
// newlines and indentation the key does not have. So we compare on a
// whitespace-normalised form.
let I18N_PLAT = {};
// Sentences built at run time ("12 platforms under …") cannot match exactly.
// An entry containing %s becomes a template: we find the sentence again and put
// the variable parts back.
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

// A number followed by its unit: "15 games". Written `n + ' game(s)'`, that
// formed a string the NUMBER was part of — hence unfindable in a catalogue,
// hence never translated. The number stays outside; the unit alone is a key.
// "file(s)" is not a plural, it is an admission. And replacing it with a single
// rule would swap one mistake for another: languages do not agree the same way.
// In French, 0 and 1 are SINGULAR — "0 fichier", "1 fichier". In English, only
// 1 is — "0 files".
//
// So the template carries both forms, `{singular|plural}`, and the language
// picks. One catalogue key per sentence, and the translator writes the two
// forms of THEIR language without needing to know the French ones.
const PLURIEL = {
  fr: n => (Math.abs(n) < 2 ? 0 : 1),
  en: n => (Math.abs(n) === 1 ? 0 : 1),
};

function accorder(texte, n) {
  if (typeof n !== 'number' || !isFinite(n)) return texte;
  const i = (PLURIEL[LANGUE] || PLURIEL.en)(n);
  return String(texte).replace(/\{([^{}|]*)\|([^{}|]*)\}/g,
                               (_, sing, plur) => (i ? plur : sing));
}

// `nb(3, '{fichier|fichiers}')` -> "3 fichiers". The same notation as in
// sentences: one convention to remember, and one to translate.
function nb(n, unite) {
  return n + ' ' + accorder(t(unite), n);
}

// A whole sentence with the number in the middle. `%d` is replaced, in order,
// by each value given.
function phrase(modele, ...valeurs) {
  // Both markers are replaced IN ORDER, not by type: a translation may swap
  // them round, but it keeps their count. Knowing only %d left a raw "%s" on
  // screen as soon as a path or a name entered a sentence.
  let sortie = t(modele);
  valeurs.forEach(v => { sortie = sortie.replace(/%[sd]/, v); });
  // The number driving agreement is the FIRST numeric argument: in "%d files
  // out of %d", it is the first that says how many files.
  const compte = valeurs.find(v => typeof v === 'number'
                                   || (typeof v === 'string' && /^\d+$/.test(v)));
  return accorder(sortie, compte === undefined ? undefined : Number(compte));
}

function t(texte, defaut) {
  return traduit(texte) || defaut || texte;
}

// An attribute set BEFORE the catalogue is read stays in the language of the
// first pass: the observer only listens to `childList`, and its value — often
// assembled — is the key to nothing. So we keep the key or keys ON the element,
// and recompute the attributes on every language change.
//
//   poserAttr(el, 'title', 'Une phrase.')
//   poserAttr(el, 'aria-label', '%s — %s', nom, aide)
//
// The interpolated values go through `t()` again on recompute: they are labels
// here, and `t()` returns its input unchanged when no key matches, so a path or
// a file name risks nothing.
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
      // keep the surrounding whitespace: it carries the layout
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

// Everything added later (cards, detail views, dialogs) goes through the
// translation too: without that, only the initial page would be translated.
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
  // The page's `lang` attribute was pinned to "fr" whatever the chosen
  // language: screen readers pronounced English with French phonetics, and the
  // spell-checking of input fields used the wrong dictionary.
  document.documentElement.setAttribute('lang', LANGUE);
  // French is the SOURCE language: its keys are already the displayed
  // sentences, there is nothing to translate.
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
  } catch (e) { /* keep the French labels */ }
}

// Each tab's reading position, so it comes back as it was left.
const DEFILEMENT = {};

// Ceiling on an uploaded file, announced by /api/health. 0 = not known yet.
let TELEVERSEMENT_MAX = 0;

let JLOG = [];              // events received from the server
let JFILTRE = 'all';        // all | error | warn | info
// What was shown on the previous render, so only genuinely new lines are
// animated. `sig` records the filter and the search: changing filter rebuilds
// the list without any line having "arrived".
let JVUES = {sig: '', n: 0};

function messageLisible(chemin, err) {
  const e = String(err).toLowerCase();
  // This is not displayed text: it is the server's RAW message, which we
  // recognise in order to replace it with the readable sentence just below.
  // Translating it would make the recognition fail.
  if (e.includes('route inconnue'))   // i18n:ok
    return "Cette fonction n'existe pas sur le serveur. Il tourne probablement " +
           "sur une version plus ancienne : arrête-le et relance python3 -m romule.";
  if (e.includes('reseau') || e.includes('failed to fetch'))
    return 'Le serveur ne répond plus. Vérifie qu\'il tourne toujours.';
  if (e.includes('tache est deja en cours'))  // i18n:ok - message compared, not shown
    return 'Une autre opération est en cours. Attends qu\'elle se termine.';
  if (chemin.includes('/api/eden') || chemin.includes('/api/nand'))
    return 'Action sur la console impossible. Vérifie qu\'elle est bien connectée.';
  if (chemin.includes('/api/emuready'))
    return 'EmuReady est injoignable. Réessaie plus tard, ta ludothèque n\'est pas affectée.';
  return 'Le serveur a refusé cette action.';
}

// A modal that vanishes at once reads as a bug rather than as a closing. So we
// let it fade, then empty its content — never before, or the dialog empties
// itself before your eyes while it is still receding.
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
    // A dialog may have been reopened meanwhile — a dialog button that closes
    // then asks the next question, for instance. Opening removes `ferme`;
    // without this check we would empty the new dialog.
    if (!el.classList.contains('ferme')) return;
    el.classList.remove('open', 'ferme', 'sansentree');
    el.innerHTML = '';
  }, FERMETURE_MS);
}

/* The clicked cover GROWS into the one on the detail view, instead of the
   dialog appearing at once with no visible link to the card. The browser does
   the interpolation: we merely give the SAME transition name to both images,
   and mutate the DOM inside the callback.

   The name must be unique in the page during the transition — two elements
   carrying it at once cancel the effect — hence the cleanup at the end,
   including when the transition is interrupted. */
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
  // The dialog has already entered: the cover brought it. Without this mark,
  // removing `vt-fiche` at the end of the transition gave it back its entry
  // animation — which then fired, once the movement was over, jumping the card
  // 28 px down before pulling it back up.
  $('modal').classList.add('sansentree');
  try {
    const t = document.startViewTransition(() => {
      // The card GIVES UP the name before the detail view takes it. Two
      // elements carrying it at once in the end state make the whole
      // transition fail ("aborted because of invalid state"): the card stays
      // in the page behind the dialog, it does not disappear.
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

/* The server only knows the CURRENT task: its log restarts from zero with each
   new one. Copying it wholesale — `JLOG = j.log` — therefore erased everything
   before it: the browser's own events, and the history of previous tasks.
   Deleting one game on the console was enough to empty the log, since the
   deletion opens a task whose log is almost empty.

   So we only append what has appeared since the last poll. A list SHORTER than
   the previous round signals a new task: the server reset its counter, we reset
   ours. */
let JLOG_SERVEUR = 0;

function fusionnerJournal(recu) {
  if (recu.length < JLOG_SERVEUR) JLOG_SERVEUR = 0;   // nouvelle tache
  if (recu.length === JLOG_SERVEUR) return;
  JLOG = JLOG.concat(recu.slice(JLOG_SERVEUR)).slice(-800);
  JLOG_SERVEUR = recu.length;
}

function journal(line, niveau) {
  // a browser-side event: presented exactly like the server ones
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
        // Machine level (error, warn, info, ok) and the message as the server
        // wrote it: two pieces of data, not labels.
        '<span class="jn" data-i18n-skip>' + e.n + '</span>' +
        '<span class="jm" data-i18n-skip>' + esc(e.m) + '</span></div>').join('')
    : '<div class="jempty">' + (q
        ? phrase('Aucun événement pour « %s ».', esc(q))
        : t('Aucun événement.')) + '</div>';

  // Like a terminal: only the lines that just arrived animate. The whole block
  // is rebuilt on every render, so without this bookkeeping it is the ENTIRE
  // log that would replay its entrance on every event — a permanent flicker
  // whenever anything runs.
  // A separator impossible in a filter name. Written as an ESCAPE SEQUENCE: a
  // raw null byte in the file makes it look binary to git and grep, which then
  // stop showing its contents.
  const signature = JFILTRE + '\u0000' + q;
  const neuves = signature === JVUES.sig ? vues.length - JVUES.n : 0;
  if (neuves > 0 && neuves <= 40) {
    const lignes = el.querySelectorAll('.jline');
    for (let i = lignes.length - neuves; i < lignes.length; i++)
      lignes[i].classList.add('neuve');
  }
  JVUES = {sig: signature, n: vues.length};
  // Like a terminal: we follow the stream while at the bottom, and stop
  // jumping as soon as you scroll up to read. Forcing the scroll made the log
  // unreadable during a task.
  if (JSUIVI) el.scrollTop = el.scrollHeight;
  majBoutonSuivi();
}

// True while the user has not scrolled the log up.
let JSUIVI = true;

function majBoutonSuivi() {
  const b = $('jsuivi');
  if (!b) return;
  R.classe(b, 'on', JSUIVI);
  R.texte(b, JSUIVI ? 'Suivi auto' : 'Suivi arrêté');
  poserAttr(b, 'title', JSUIVI ? 'Le journal descend avec les nouvelles lignes.'
                               : 'Le journal reste où tu l\'as laissé.');
}

// ------------------------------------------------------------- dialog
// An error must not settle for a fleeting message: we explain what failed, what
// it implies, and we give the technical detail to copy.
const D_ICONE = {error: '⚠️', warn: '⚠️', ok: '✅', info: 'ℹ️'};

function dialogue({titre, niveau = 'info', message = '', detail = '', options = [],
                   champs = [], actions = [], fermer = 'Fermer'}) {
  const el = $('dialog');
  const boutons = actions.map((a, i) =>
    '<button class="' + (a.principal ? 'go' : 'ghost') + '" data-di="' + i + '">' +
    esc(a.libelle) + '</button>').join('');
  // Checkable options: one decision point rather than a run of dialogs.
  const opts = options.length ? '<div class="dopts">' + options.map(o =>
    '<label class="dopt' + (o.desactive ? ' off' : '') + '">' +
    '<input type="checkbox" data-opt="' + o.id + '"' +
    (o.coche ? ' checked' : '') + (o.desactive ? ' disabled' : '') + '>' +
    '<span><b>' + esc(o.libelle) + '</b>' +
    (o.detail ? '<span class="dsub">' + esc(o.detail) + '</span>' : '') +
    '</span></label>').join('') + '</div>' : '';
  // Input fields: the same dialog, the same validation, rather than a
  // succession of context-free prompt() calls.
  const saisies = champs.length ? '<div class="dchamps">' + champs.map(c =>
    '<label class="dchamp"><span>' + esc(c.libelle) + '</span>' +
    // `type` allows a password field: typing one in the clear on screen is
    // not acceptable.
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
  // Reopening cancels a closing in progress: without this, `fermerVoile`'s
  // deferred cleanup would empty the dialog we just opened.
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

// Three notifications at most, and never the same text twice: a stack that
// grows covers the interface instead of explaining it.
const TOAST_MAX = 3;

function toast(msg, kind) {
  const pile = $('toasts');
  const jumeau = [...pile.children].find(t => t.dataset.msg === msg);
  if (jumeau) {                             // already shown: we count it
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

// A toast carrying an ACTION, which lives longer.
//
// The trash IS the undo: asking "are you sure?" before putting a file in it
// charges, every time, the price of a mistake that costs nothing. We act, and
// we offer to go back — eight seconds, long enough to notice the mistake.
//
// The TRULY irreversible actions — emptying the trash, clearing the log,
// revoking a key — keep their confirmation. The rule: confirm what cannot be
// undone, offer to undo the rest.
function toastAction(msg, libelle, faire, kind) {
  const pile = $('toasts');
  while (pile.children.length >= TOAST_MAX) pile.firstChild.remove();
  const el = document.createElement('div');
  el.className = 'toast agir' + (kind ? ' ' + kind : '');
  const txt = document.createElement('span');
  txt.textContent = msg;
  const b = document.createElement('button');
  b.className = 'ghost mini';
  b.textContent = libelle;
  let fini = false;
  const fermer = () => {
    if (fini) return;
    fini = true;
    el.classList.add('out');
    setTimeout(() => el.remove(), 300);
  };
  b.addEventListener('click', () => { fermer(); faire(); });
  el.append(txt, b);
  pile.appendChild(el);
  setTimeout(fermer, 8000);
  return fermer;
}

// At startup the state is already legible in the header and in the counters:
// piling notifications on top teaches nothing and hides the interface. So they
// go to the log alone, which is made for it.
let DEMARRAGE = true;

function annonce(msg, kind) {
  journal(msg, kind === 'warn' ? 'warn' : 'ok');
  if (!DEMARRAGE) toast(msg, kind);
}
// `say` describes what is happening RIGHT NOW ("Sending X…"). The task's NAME,
// on the other hand, comes from the running job: mixing them left a stale label
// as the title long afterwards.
function say(t) { R.texte($('tachedetail'), t || ''); }

// ----------------------------------------------------------- running task
// The time remaining is estimated HERE, from observed progress: the server only
// computes it for transfers, while a conversion or a container read needs it
// just as much. We smooth over a sliding window so that a hiccup does not make
// the estimate jump.
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

// ------------------------------------------------ activity indicator (+ button)
// Two things can be running: a server task, or a file upload from this browser.
// The button shows one at a time, with a simple rule: the upload comes first,
// because the user just triggered it and is waiting for an immediate answer.
let ACT_SERVEUR = null;      // {titre, pct, reste, detail}
let ACT_ENVOI = null;

function activite() { return ACT_ENVOI || ACT_SERVEUR; }

// The ring follows the button's outline, which changes size with what it
// shows. `pathLength=100` normalises the perimeter: the gauge is driven as a
// percentage without ever recomputing a circumference.
function majAnneau() {
  const btn = $('fab'), svg = $('fabring');
  if (!btn || !svg) return;
  const l = btn.offsetWidth, h = btn.offsetHeight;
  if (!l || !h) return;
  const e = 3;                                   // stroke thickness
  svg.setAttribute('viewBox', '0 0 ' + l + ' ' + h);
  [$('fabpiste'), $('fabjauge')].forEach(r => {
    if (!r) return;
    r.setAttribute('x', e / 2); r.setAttribute('y', e / 2);
    r.setAttribute('width', Math.max(0, l - e));
    r.setAttribute('height', Math.max(0, h - e));
    r.setAttribute('rx', Math.max(0, (h - e) / 2));
  });
}

// Time remaining in three characters or so: the button is 54 px, there is no
// room for "less than a minute". The full sentence stays in the panel and in
// the tooltip.
function resteCourt(s) {
  if (s == null) return '';
  if (s < 60) return Math.max(1, Math.round(s)) + ' s';
  const m = Math.round(s / 60);
  if (m < 60) return m + ' min';
  const h = Math.floor(m / 60);
  return h + ' h' + String(m % 60).padStart(2, '0');
}

// What the button shows at its centre, in order of precision: the time
// remaining when it can be estimated, else the progress, else nothing — the
// spinning ring already says "it is working".
// A marker: three dots lighting in turn. Showing "0 %" would be simpler, but it
// would be false — at the start of an import the console has not yet said how
// many files it expects, so there is no percentage to show. The dots say the
// only true thing: it is starting.
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

  // With no known total, the gauge spins instead of lying about progress.
  const indetermine = !a || a.pct == null;
  R.classe(btn, 'cherche', !!a && indetermine);
  const jauge = $('fabjauge');
  if (jauge) {
    jauge.style.strokeDasharray = indetermine
      ? '18 82'
      : Math.max(0, Math.min(100, a.pct)) + ' 100';
  }

  // The centre figure. We only rewrite it when it has changed: otherwise the
  // flip animation would replay on every server poll, twice a second, and the
  // button would flicker without stopping.
  const coeur = coeurFab(a);
  const eta = $('fabeta');
  if (eta && coeur !== FAB_COEUR) {
    if (coeur === FAB_ATTENTE) eta.innerHTML = FAB_POINTS;
    else eta.textContent = coeur;
    if (coeur) {
      eta.classList.remove('change');
      void eta.offsetWidth;                     // restart the animation
      eta.classList.add('change');
    }
    FAB_COEUR = coeur;
  }
  R.classe(btn, 'pause', !!(a && a.pause));

  // Task end: the ring fills and fades out in green. Without that signal, the
  // button simply becomes a "+" again and nothing says that what you were
  // waiting for has finished.
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

// True while a details lookup is REALLY running.
//
// The "Fetching details…" banner showed on any card without details, whether a
// lookup was running or not. For a game no database knows — too recent a title,
// a homebrew, a file name too mangled — it therefore NEVER went away: the card
// announced work in progress that would never happen. That is the interface
// lying, not a display detail, and it was in front of everyone on the README
// screenshot.
//
// A card without details now says nothing: its missing summary is visible
// enough, and "Missing details" is there to go and fetch them.
let RECHERCHE_FICHES = false;

// The labels the server gives to the tasks that fill in the details. These are
// Python FUNCTION names, not displayed text: they are not translated.
const TACHES_FICHES = ['sync_meta', 'meta_sync'];   // i18n:ok

function renderTache(j) {
  const el = $('tache');
  const cherche = !!j.running && TACHES_FICHES.includes(j.label);
  if (cherche !== RECHERCHE_FICHES) {
    RECHERCHE_FICHES = cherche;
    // The end of the lookup must clear the remaining banners: without this
    // render they would hold until the next pass over the grid.
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

  // progress: the count first, the server's detail (rate) second
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

// The "+" button's panel: what is running, how far along, and how much time is
// left. The log, for its part, tells what HAS happened — the two do not
// overlap.
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

// `label` carries the name of the running Python function: it speaks to the
// code alone. We turn it into a short phrase, recognisable at a glance.
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
  // A file with no usable title ID (an .xci pack, a malformed name) was
  // grouped by FOLDER. Two consequences, both seen for real: two different
  // games from the same folder landed on one card, and a game appeared twice
  // as soon as it also had a correctly named update. So we match on the
  // reduced title instead.
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
    // A fallback name when a game has none: it is DISPLAYED, hence translated.
  // A cover search by name would have found nothing anyway.
  g.name = g.baseName || (g.files[0] && g.files[0].name) || t('Inconnu');
    // An .xci pack merging game, updates and DLC carries no title ID: it is
    // classed INCONNU although it CONTAINS the game. Counting it as a base
    // avoids announcing "the base game is missing" for a perfectly playable
    // game.
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
  // With no title ID we still ask for the cover: the server can search by
  // name. Returning '' condemned XCI packs to an empty thumbnail.
  if (!g.tid && !g.name) return '';
  // the `v` token changes as soon as the server cache moves: without it the
  // browser would keep its old images for hours.
  const v = (DATA && DATA.covers_v) || 0;
  return '<img class="' + (cls || '') + '" src="/cover/' + (g.tid || '') + '?v=' + v +
    '&name=' + encodeURIComponent(g.name || '') + '" loading="lazy" ' +
    'data-cover' +
    (attrs ? ' ' + attrs : '') + '>';
}

/* ------------------------------------------------------------------ colours
   A cover's dominant colour serves twice: it fills the slot BEFORE the image
   arrives (the grid no longer flickers while scrolling), and it tints the
   header of the game's detail view.

   It is computed once per game, in the browser, then stored locally:
   recomputing it on every render would make the processor work for an
   always-identical result. */
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
  // One write per burst: 48 covers arriving together would trigger 48
  // serialisations of the same object.
  COULEURS_A_ECRIRE = setTimeout(() => {
    try { localStorage.setItem('couleurs', JSON.stringify(COULEURS)); }
    catch (e) { /* quota full: the colour will be recomputed, no harm done */ }
  }, 800);
}

const ECH = 18;            // the cover is scaled to 18x18 before analysis

function couleurDominante(img) {
  let d;
  try {
    const c = document.createElement('canvas');
    c.width = c.height = ECH;
    const ctx = c.getContext('2d', {willReadFrequently: true});
    ctx.drawImage(img, 0, 0, ECH, ECH);
    d = ctx.getImageData(0, 0, ECH, ECH).data;
  } catch (e) {
    return '';               // no canvas available: we do without
  }
  const seaux = new Map();
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], v = d[i + 1], b = d[i + 2];
    if (d[i + 3] < 200) continue;
    const haut = Math.max(r, v, b), bas = Math.min(r, v, b);
    const clarte = (haut + bas) / 2;
    // Near-black and near-white are edges and flat backgrounds: they dominate
    // by area without ever characterising a cover.
    if (clarte < 34 || clarte > 226) continue;
    const cle = (r >> 4) + ',' + (v >> 4) + ',' + (b >> 4);
    const s = seaux.get(cle) || {n: 0, r: 0, v: 0, b: 0, poids: 0};
    s.n++; s.r += r; s.v += v; s.b += b;
    s.poids += 1 + (haut - bas) / 64;      // a vivid colour weighs more
    seaux.set(cle, s);
  }
  let chef = null;
  for (const s of seaux.values()) if (!chef || s.poids > chef.poids) chef = s;
  if (!chef) return '';
  return 'rgb(' + Math.round(chef.r / chef.n) + ' ' +
                  Math.round(chef.v / chef.n) + ' ' +
                  Math.round(chef.b / chef.n) + ')';
}

// Attributes to set on a card or a detail view: enough to find the colour again
// afterwards, and the colour itself when it is already known — that is what
// avoids the flicker, since it applies BEFORE the image loads.
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
  inventaireChange();
  renderLib();
  // What is officially missing (patches, DLC) is no longer a separate list:
  // the information lives on the card of the game concerned, where it is
  // useful.
  renderImport(DATA.pending || []);
  renderTree();
  $('organizewrap').style.display = DATA.device === 'device' ? '' : 'none';
  fillSettings();
}

// ------------------------------------------------- systemes (autres consoles)
function renderSysSelect() {
  const el = $('sysel');
  // We count GAMES, not files: for the Switch the total included updates and
  // DLC, which inflated the figure while saying nothing useful (148 files for
  // 22 games).
  // The local count alone lied: most platforms only exist on the console. So we
  // keep the larger of the two (local, detected console).
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
// A platform's short label: "GBA", not "Game Boy Advance".
function libelleSysteme(key) {
  const s = SYSTEMS.find(x => x.key === key);
  return (s && s.folder) || key;
}


// Typing must not redraw the grid on every keystroke.
//
// `renderLib()` was called directly by the `input` event: typing eight
// characters triggered eight full renders, seven of them thrown away at once.
// We coalesce onto the next frame — that is the screen's rhythm, and the only
// moment a render can be seen.
let RENDU_PREVU = 0;
let VUES = [];                  // saved views, served by the server
// Who is looking, and with what role. Without authentication everybody is an
// administrator — Romule's most common mode.
let ROLE = {authentification: false, connecte: false, admin: true, nom: ''};

// The interface does not show what you cannot do.
//
// This is NOT a security measure: `RESERVE_ADMIN`, server-side, is what
// refuses, and a test checks it across all the reserved routes. Hiding is a
// courtesy — without it, a non-administrator opens Settings, clicks, and
// collects 403s without understanding what is happening.
function appliquerRole() {
  const onglet = document.querySelector('#tabs [data-tab="settings"]');
  if (onglet) onglet.hidden = !ROLE.admin;
  document.body.classList.toggle('sansadmin', !ROLE.admin);
  // Already on the settings when the role arrives: we go back to the games
  // rather than leaving a screen nobody is allowed to use.
  if (!ROLE.admin && document.querySelector('#panel-settings.active'))
    app.tab('jeux');
}

// What DEFINES the displayed subset. Not the sort order, not the tile size,
// not the page: those are display preferences, they apply to everything you
// look at.
function filtresCourants() {
  return {systeme: SYS,
          recherche: (($('filter') || {}).value || '').trim(),
          etat: FILTER,
          avances: [...FAV]};
}

function nbFiltresActifs() {
  const f = filtresCourants();
  return (f.recherche ? 1 : 0) + (f.etat !== 'all' ? 1 : 0) + f.avances.length;
}

function resumeFiltres(f) {
  const bouts = [];
  bouts.push(phrase('Plateforme : %s',
                    f.systeme === 'all' ? t('toutes') : libelleSysteme(f.systeme)));
  if (f.recherche) bouts.push(phrase('Recherche : %s', f.recherche));
  if (f.etat !== 'all') bouts.push(phrase('État : %s', f.etat));
  if (f.avances.length)
    bouts.push(phrase('Filtres avancés : %s',
                      f.avances.map(k => t((FAVANCES[k] || [k])[0])).join(', ')));
  return bouts.join('\n');
}

function dessinerVues() {
  const boite = $('vues');
  if (boite)
    boite.innerHTML = VUES.map(v =>
      '<span class="vue" data-act="appliquerVue" data-arg="' + esc(v.id) + '"'
      + ' data-i18n-skip>' + esc(v.nom)
      + '<button class="oter" data-act="supprimerVue" data-arg="' + esc(v.id)
      + '" title="' + esc(t('Oublier cette vue')) + '"'
      + ' aria-label="' + esc(t('Oublier cette vue')) + '">×</button></span>').join('');
  majBarreFiltres();
}

function majBarreFiltres() {
  const n = nbFiltresActifs();
  const eff = $('effacefiltres');
  if (eff) eff.hidden = n === 0;
  const enr = $('enregistrervue');
  if (enr) enr.hidden = n === 0;
  const b = $('favbtn');
  if (b) R.texte(b, n ? phrase('Plus de filtres · %d', n) : t('Plus de filtres'));
}

// ------------------------------------------------------------ mise a jour
//
// An invitation, not an alarm: the pill only appears when there really is a
// newer version, and nothing is blocked while you ignore it.
let MAJ = null;

async function chargerMaj() {
  const r = await api('/api/maj', null, true);
  if (!r || r.error) return;
  MAJ = r;
  const b = $('majpuce');
  if (b) b.hidden = !r.disponible;
}

// The notes come from GitHub: this is text WRITTEN BY SOMEONE ELSE. So it
// never enters HTML — `dialogue()` sets its `detail` through `textContent`. We
// merely lighten the noisiest Markdown syntax, without ever interpreting it.
function notesLisibles(md) {
  return String(md || '')
    .replace(/\r/g, '')
    .replace(/^#{1,6}\s*/gm, '')        // titres
    .replace(/^\s*[-*]\s+/gm, '• ')     // puces
    .replace(/\*\*([^*]+)\*\*/g, '$1')  // gras
    .replace(/`([^`]+)`/g, '$1')        // code
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

async function chargerVues() {
  const r = await api('/api/vues', null, true);
  if (!r || r.error) return;
  VUES = r.vues || [];
  dessinerVues();
}

function renderLibBientot() {
  if (RENDU_PREVU) return;
  RENDU_PREVU = requestAnimationFrame(() => { RENDU_PREVU = 0; renderLib(); });
}

function renderLib() {
  renderSysSelect();
  majBarreFiltres();
  // The Switch-specific status filters (updates, DLC, conversion) make no
  // sense elsewhere: we hide them, the rest of the view is shared.
  const suisse = isSwitch();
  ['activer', 'convert', 'probleme', 'importer'].forEach(k => {
    const chip = document.querySelector('#filters [data-f="' + k + '"]');
    if (chip) chip.dataset.horsSwitch = suisse ? '' : '1';
  });
  $('bulkconv').style.display = suisse ? '' : 'none';

  const tous = jeuxUnifies();
  // Boilerplate summaries are spotted by comparing games with one another: the
  // full list must therefore be known before drawing a single card.
  majModelesResume(tous);
  renderToolbar(tous);

  // counters: a filter with nothing to say is hidden, not shown as zero
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
  // Grouping comes AFTER filtering: a group must only count the versions
  // actually visible, otherwise it would announce "5 versions" in a list that
  // shows one.
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

  // pagination: the page size follows the card size
  const parPage = PARPAGE || Math.max(1, list.length);   // 0 = everything on one page
  const pages = Math.ceil(list.length / parPage);
  if (PAGE >= pages) PAGE = 0;
  const vus = list.slice(PAGE * parPage, (PAGE + 1) * parPage);

  lib.style.setProperty('--carte', TAILLES[TAILLE][1] + 'px');
  VUS_PAGE = vus.map(({g}) => g.key);

  // The grid is reconciled, no longer rewritten: an unchanged card is left
  // alone, so its animation does not replay and its checkbox needs no manual
  // resynchronisation. That is what reactive.js brings.
  let grille = lib.firstElementChild;
  if (!grille || !grille.classList.contains('games')) {
    lib.innerHTML = '';
    grille = document.createElement('div');
    lib.appendChild(grille);
  }
  grille.className = 'games taille-' + TAILLE  // i18n:ok - classe CSS;

  R.liste(grille, vus, {
    // The expanded state is part of the card's identity: without it,
    // reconciliation would reuse the same tile and the chevron would stay
    // pointing the wrong way.
    cle: ({g}) => g.key,
    creer: (x) => R.depuisHtml(carteHtml(x)),
    majEl: (el, x) => majCarte(el, x),
  });

  renderAlphabet(list);
  renderPager(list.length, pages, parPage);
  renderActionBar();
}

// -------------------------------------------------------- alphabetical index
// One letter per existing group, as in a library. It only makes sense when the
// list IS sorted by name: with a sort by size, jumping to "M" would mean
// nothing, so the index disappears.
function lettreDe(g) {
  const t = (nomJeu(g) || '').trim();
  // Accents are unfolded: "Ecran" and "Écran" file in the same place.
  const c = t.normalize('NFD').replace(/[\u0300-\u036f]/g, '')[0] || '';
  if (/[0-9]/.test(c)) return '#';
  return /[a-z]/i.test(c) ? c.toUpperCase() : '#';
}

let ALPHA_POS = new Map();      // letter -> rank in the filtered list
// The letter asked for by a click. In a grid, the target card often falls in
// the middle of a row: no position calculation can then guess "the" current
// letter. After a click the user's intent is authoritative; the first scroll
// hands control back to the calculation.
let ALPHA_VISEE = '';
// When the last jump happened. Smooth scrolling emits a dozen events: a
// single-use flag absorbed only one, and the index took control back before
// even arriving.
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

// The letter you are currently reading is highlighted: without that the index
// says where you CAN go, never where you ARE.
function majAlphabet() {
  const nav = $('alphabet');
  if (!nav || nav.hidden) return;
  const cartes = [...document.querySelectorAll('#lib .gcard')];
  let courante = '';
  // The current letter is that of the FIRST card still visible, not the last
  // one passed: in a grid several cards share a row, and taking the last one
  // pointed at the next letter as soon as a group fitted on one line.
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

// ONE line under the title, and the most useful of the six possible ones.
// Stacking size, contents, EmuReady rating and remark gave four competing lines
// none of which stood out; size and contents now live on the cover, where they
// are read without reading.
// The card talks about the GAME, not about the tool: it carries the summary and
// nothing else. The status ("Update to activate", "Problem") is already said by
// the cover's badge; the detail — which update, why a file is incomplete —
// belongs to the detail view, where there is room to explain it.
function carteLigne(x) {
  const resume = resumeUtile(x.g);
  return resume ? ['resume', extrait(resume, 96)] : ['', ''];
}

// Words too common to weigh in the comparison: keeping them would make any
// sentence pass for "close to the title".
const VIDES = new Set(('le la les un une des du de d l a au aux et ou en dans sur '  // i18n:ok - stop words, not interface text
  + 'pour par avec sans version edition the a an of and or in on for with your '
  + 'this that new').split(' '));

function motsUtiles(t) {
  return (String(t || '').toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .match(/[a-z0-9]{2,}/g) || []).filter(m => !VIDES.has(m));
}

// A summary that merely repeats the title takes three lines to say nothing:
// "Relive the Pokémon Blattgrüne Edition adventure!" on the card for Pokémon
// Blattgrüne Edition. We drop it when most of its words already come from the
// title — but only when it is short: a real description starting with the
// game's name must stay.
const RESUME_COURT = 9;          // useful words past which we stop judging
const RESUME_REDONDANT = 0.5;    // share of words already present in the title

// A second net, this one based on the library itself. Comparing against the
// title does not catch "Relive the Pokémon Edición Rojo Fuego adventure!" on a
// card titled "Pokémon FireRed Version": not one word in common, and yet the
// sentence says nothing. It does, however, start like seven others in the
// library — that is BOILERPLATE, and it is measurable without knowing the
// language or the source.
const MODELE_MOTS = 3;           // length of the compared opening
const MODELE_MINI = 3;           // number of games past which it is boilerplate
const MODELE_LONG = 12;          // a real description escapes the rule
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

// The bottom badge: on the left WHERE the game is, on the right what is left to
// do. Two lit/unlit indicators read faster than a sentence, and keep the
// vocabulary of the device rather than that of a form.
// A short version of the status, for a card's strip. "Not on the console" did
// not fit beside the words MAC and CONSOLE: the strip ended with "NOT ON THE …"
// on every cover, and therefore said nothing. The full text stays available as
// a tooltip and in the detail view.
// "Ready" and "To send" described the FILE's state; what the user wants to know
// is whether they can play, and if not what is left to do. So every word is
// either "playable" or an action verb — and the console pill, just above,
// already says where the game is.
const ETAT_COURT = {
  probleme: 'Problème', importer: 'À rapatrier', envoyer: 'À transférer',
  activer: 'À activer', convert: 'À convertir', pret: 'Jouable',
  local: 'Sur le serveur',
};

function carteEtiquette({e}) {
  const p = e.presence || {mac: true, console: 'inconnu'};
  const tMac = p.mac ? 'Présent sur le serveur' : 'Absent du serveur';
  const tCons = t(TITRE_PRESENCE[p.console] || '');
  // Wordless pills: the colour carries the information, the tooltip names it.
  // The words "MAC" and "CONSOLE" ate two thirds of the width to repeat an
  // order that never changes (the server first).
  // The console left this strip for the pill at the top, where it reads at a
  // glance across the whole grid. Repeating it here would say the same thing
  // twice, 200 px apart.
  return '<span class="temoins">' +
      '<i class="tem ' + (p.mac ? 'p-oui' : 'p-non') + '" title="' + esc(tMac) +
        '" aria-label="' + esc(tMac) + '"></i>' +
    '</span>' +
    // `e.txt` is a status label taken from `ETATS`: it must go through the
    // catalogue like the visible text right beside it.
    '<span class="etatmot ' + ETATS[e.etat][0] + '" title="' + esc(t(e.txt)) + '">' +
      esc(ETAT_COURT[e.etat] || e.txt) + '</span>';
}
const TITRE_PRESENCE = {
  oui: 'Présent sur la console', partiel: 'En partie sur la console',
  non: 'Absent de la console', inconnu: 'Console non consultée',
};

// Pills placed on the cover: what can be counted (size, updates, DLC).
/* ============================================================================
   SUPPORTS PHYSIQUES
   ----------------------------------------------------------------------------
   Twenty-three platforms, but only six SHAPES of medium: a home cartridge, a
   handheld cartridge, a card, a disc, a Switch card, an arcade board. Drawing
   twenty-three distinct silhouettes would be a lie — at 46 px, a SNES cartridge
   and a Mega Drive cartridge are the same object.

   They serve where there is nothing to show: a game without a cover used to
   display a big letter in a grey rectangle. They also say, in the detail view,
   what the game really ran on.
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

// Drawings in `currentColor`, on a 48-unit grid: they inherit the text colour
// wherever they are placed, with no variant to maintain.
const SILHOUETTES = {
  // They all follow the same rule: ONE filled path, and the details are HOLES
  // (`fill-rule="evenodd"`). Laying a detail over the body at reduced opacity
  // does not lighten it — it paints in the same colour, so it vanishes. It is
  // the cut-out that makes it exist.

  // Carte Switch : coin biseaute et ergot de detrompage.
  switch:
    '<path fill-rule="evenodd" d="M15 5h13l5 5v29a4 4 0 0 1-4 4H15' +
      'a4 4 0 0 1-4-4V9a4 4 0 0 1 4-4zm3 30h8v4h-8z"/>',
  // Handheld cartridge: tall, bevelled bottom corner, label window.
  poche:
    '<path fill-rule="evenodd" d="M12 4h24v32l-7 7H12V4zm4 5h16v14H16V9z' +
      'm1 21h10v3H17v-3z"/>',
  // Home cartridge: wide, label and connector comb.
  cartouche:
    '<path fill-rule="evenodd" d="M12 4h24a2 2 0 0 1 2 2v38H10V6a2 2 0 0 1 2-2z' +
      'm3 5h18v13H15V9zm-1 27h20v3H14v-3z"/>',
  // Carte memoire : presque carree, coin coupe.
  carte:
    '<path fill-rule="evenodd" d="M11 11h19l6 6v20a3 3 0 0 1-3 3H11' +
      'a3 3 0 0 1-3-3V14a3 3 0 0 1 3-3zm2 20h10v3H13v-3z"/>',
  // Optical disc: the hole is cut out, not painted.
  disque:
    '<path fill-rule="evenodd" d="M24 6a18 18 0 1 0 .01 0zm0 12.5' +
      'a5.5 5.5 0 1 0 .01 0z"/>' +
    '<path d="M24 10.5a13.5 13.5 0 0 1 11.7 6.8" fill="none"' +
      ' stroke="currentColor" stroke-width="2" stroke-linecap="round"' +
      ' opacity=".45"/>',
  // Arcade cabinet: screen and control panel cut out of the cabinet.
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
  // "Is it on the console?" is THE question you ask while scanning the grid.
  // So it lives on the cover, not in the bottom strip where it drowned between
  // two other pieces of information. Three states only, and nothing at all
  // while the console has not answered: showing an unlit indicator for "I do
  // not know" would be a lie.
  const p = (e && e.presence) || {};
  if (p.console && p.console !== 'inconnu') {
    bouts.push('<span class="ov ovconsole p-' + p.console + '" title="' +
      esc(t(TITRE_PRESENCE[p.console] || '')) + '" aria-label="' +
      esc(t(TITRE_PRESENCE[p.console] || '')) + '">' + GLYPHE_CONSOLE + '</span>');
  }
  // The platform's name, essential as soon as several are mixed, and useful
  // elsewhere to remove any doubt about what you are looking at.
  if (g.sysNom) bouts.push('<span class="ov ovsys">' + esc(g.sysNom) + '</span>');
  // Language matters for ALL games, not only for grouped versions: knowing a
  // cartridge is Japanese before launching it saves a round trip. And for three
  // versions under the same title, it is the only thing telling them apart.
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

// A game that just arrived has neither an official title nor a cover yet.
// Rather than an empty card you cannot tell will ever fill in, we say the
// lookup is running.
function sansFiche(g) {
  if (!g) return false;
  if (g.tid) return !(META[String(g.tid).toLowerCase()] || {}).nom;
  const f = (g.files && g.files[0]) || g;
  return !(g.titre || f.titre);
}
// One row of the versions dialog: enough to choose without opening every
// detail view — the language, the size, the status, and where the file is.
// The last dialog opened comes to the front, and it alone. We do not push a
// counter up: the layers above (wizard, magnifier, drop overlay) must stay
// above, whatever happens.
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
    // The medium serves as an edging in the "all platforms" view: the only one
    // where it teaches anything. In a Switch view, thirty-four identical
    // edgings would be noise.
    '" data-media="' + esc(vueTotale() ? mediaDe(g) : '') +
    '" data-lettre="' + esc(lettreDe(g)) +
    '" data-key="' + esc(g.key) + '"' + attrsTeinte(g) +
    ' tabindex="0" role="button" aria-label="' + esc(nomJeu(g)) + '"' +
    ' data-act="cardClick" data-arg="' + esc(g.key) + '">' +
    '<div class="art">' + coverImg(g) +
    // With no cover, the medium's silhouette at least says what this is. A
    // giant initial said nothing: two games in three start with the same letter
    // in a sorted library.
    '<span class="ph">' + (silhouetteHtml(g) ||
       esc((nomJeu(g)[0] || '?').toUpperCase())) + '</span>' +
    '<span class="ovslot">' + carteOverlay(x) + '</span>' +
    '<span class="badge">' + carteEtiquette(x) + '</span>' +
    '<span class="pcheck' + (coche ? ' on' : '') + '">' + (coche ? '✓' : '') + '</span>' +
    (attente ? '<span class="enattente">Recherche des infos…</span>' : '') + '</div>' +
    '<div class="cap"><div class="gname">' + esc(nomJeu(g)) + '</div>' +
    '<div class="ligne ' + cls + '">' + esc(txt) + '</div>' +
    // The group key comes from a file name: it travels through a `data-`
    // attribute, never inside the `onclick`'s JavaScript string — an apostrophe
    // in a title would break the handler there.
    (g.groupeN ? '<button class="pgrp" data-grp="' + esc(g.groupeCle) +
       '" data-act="voirVersions" data-arg="' + esc(g.groupeCle) + '">' +
       g.groupeN + ' versions…</button>' : '') +
    '<button class="pinfo" data-act="openGame" data-arg="' + esc(g.key) + '">Détails</button></div></div>';
}

// Update a card already present. Every write is conditional: nothing moves if
// nothing changed, so no transition restarts for nothing.
function majCarte(el, x) {
  const {g, e} = x;
  const coche = dsel2.has(g.key);
  R.classe(el, 'sel', coche);
  // As soon as the details arrive, the waiting veil disappears without
  // redrawing the card — hence without making the cover flicker.
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
  // Named `selTri` and not `t`: `t()` is the translation function, and a local
  // variable of that name shadows it throughout the function. The call then
  // becomes "t is not a function" — on the first render only, hence a blank
  // screen at startup and nothing at all afterwards.
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

  // Each advanced filter shows how many games it would keep: you know before
  // clicking whether it is worth it.
  const pop = $('favlist');
  if (pop) pop.innerHTML = Object.entries(FAVANCES).map(([k, [lib, fn]]) =>
    '<label class="favrow"><input type="checkbox" ' + (FAV.has(k) ? 'checked ' : '') +
    'data-act-change="toggleFav" data-arg="' + esc(k) + '"><span class="grow">' + esc(lib) + '</span>' +
    '<span class="mono">' + tous.filter(fn).length + '</span></label>').join('');
  // This button's LABEL belongs to `majBarreFiltres()`, and to it alone: here
  // it counted only the advanced filters, while the search and the status chip
  // filter just as much. Two writers on the same text means the last one wins —
  // and it was the one that counted worst.
  const b = $('favbtn');
  if (b) b.classList.toggle('on', FAV.size > 0);
  majBarreFiltres();
}

function renderPager(total, pages, parPage) {
  const el = $('pager');
  if (pages <= 1) {
    el.innerHTML = '<span class="mono">' + nb(total, '{jeu|jeux}') + '</span>';
    return;
  }
  const de = PAGE * parPage + 1, a = Math.min(total, (PAGE + 1) * parPage);
  el.innerHTML =
    '<button class="ghost" ' + (PAGE ? '' : 'disabled') + ' data-act="page" data-val="-1">‹ Précédent</button>' +
    '<span class="mono">' + de + '–' + a + ' sur ' + total + '</span>' +
    '<button class="ghost" ' + (PAGE < pages - 1 ? '' : 'disabled') + ' data-act="page" data-val="1">Suivant ›</button>';
}

// The action bar only appears once games are ticked, and only offers what is
// doable on THIS selection: a greyed-out button with no explanation leaves the
// user guessing why.
function renderActionBar() {
  const bar = $('actionbar');
  if (!isSwitch() || !dsel2.size) { bar.classList.remove('on'); return; }
  bar.classList.add('on');
  const c = deployCibles();
  const surConsole = c.supprConsole.length;
  const boutons = [];
  if (c.envoyer.length || c.activer.length)
    // The same action as the detail view's button: the same words. "Put on the
    // console" and "Send to the console" named the same gesture, which forces
    // you to check every time that it really is the same thing.
    boutons.push(['go', 'appliquer', 'Envoyer vers la console',
                  c.envoyer.length ? fmt(c.poids)
                                   : nb(c.activer.length, 'MAJ/DLC')]);
  if (c.importer.length)
    boutons.push(['go', 'appliquer', 'Copier vers le serveur', nb(c.importer.length, '{fichier|fichiers}')]);
  if (surConsole)
    boutons.push(['warn', 'supprimerConsole', 'Retirer de la console', nb(surConsole, '{fichier|fichiers}')]);
  if (c.local.length)
    boutons.push(['', 'corbeilleSelection', 'Mettre à la corbeille', nb(c.local.length, '{fichier|fichiers}')]);

  // The counter is written ONCE then updated in place: rebuilding it on every
  // click would replace the <b>, and the number would jump instead of
  // rolling.
  const som = $('deploysum');
  if (!som.firstElementChild) som.innerHTML = t('<b>0</b> {jeu|jeux} {sélectionné|sélectionnés}');
  chiffreAnime(som.firstElementChild, dsel2.size);

  // "Select all" disappears once everything is ticked: a button that can do
  // nothing is a button that lies.
  const visibles = jeuxFiltres(jeuxUnifies()).length;
  const tout = $('touscocher');
  if (tout) {
    tout.style.display = dsel2.size >= visibles ? 'none' : '';
    tout.textContent = 'Tout cocher';
  }
  $('actions').innerHTML = boutons.map(([cls, fn, lib, det]) =>
    // `fn` comes from the `boutons` list written ten lines above, hence from
    // literal names. What guarantees it stays that way is not that proximity,
    // it is `ACTES`: a name missing from the allow-list does nothing, and
    // `test_gestes.py` fails when one of them is absent from it.
    '<button class="' + cls + '" data-act="' + esc(fn) + '">' + esc(lib) +
    '<span class="mono"> · ' + esc(det) + '</span></button>').join('') ||
    '<span class="mono">Rien à faire sur cette sélection.</span>';
}

// -------------------------------------------------------------- game detail
// The detail view's "Updates" section. Here, and nowhere else, is where
// versions are discussed: the card must stay devoted to the game itself.
// Every claim is sourced — the user must be able to go and check.
const SOURCE_MAJ = 'https://github.com/blawar/titledb';

function majSection(g, e) {
  if (g.console) return '';
  const maj = g.files.filter(f => f.type === 'UPDATE');
  const vers = maj.map(f => f.version).filter(v => v != null);
  const mienne = vers.length ? Math.max.apply(null, vers) : null;
  const base = g.files.find(f => f.type === 'BASE') || {};
  const drapeaux = (base.flags || []).filter(x => ['nopatch', 'outdated', 'nodlc'].includes(x[0]));
  const casses = (e.casses || []).filter(f => f.type !== 'BASE');

  // nothing to say: no known update, no missing DLC, no damaged file
  if (!maj.length && !drapeaux.length && !casses.length && !g.dlcCount
      && !(e.aActiver || []).length) return '';

  const l = [];
  // A single word, without an accent: neither the static check nor the browser
  // test could see it — both heuristics need an accent OR two function words.
  // The floor has been lowered since, but these two had already got through,
  // and "aucune" showed in an English interface.
  l.push('<div class="majrow"><span>Version installée</span><b>' +
    (mienne != null ? 'v' + mienne
                    : t(maj.length ? 'inconnue' : 'aucune')) + '</b></div>');
  if (g.dlcCount)
    l.push('<div class="majrow"><span>DLC présents</span><b>' + g.dlcCount + '</b></div>');

  // What is copied to the console but not yet active in Eden. The action lives
  // here, beside the fact that justifies it, rather than in a distant bar.
  if ((e.aActiver || []).length) {
    l.push('<div class="majrow act"><span>À activer dans Eden</span>' +
      '<b class="p-partiel">' + nb(e.aActiver.length, '{élément|éléments}') + '</b>' +
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
  // The status talks ONLY about availability: the update detail has its own
  // section below, with the button that goes with it.
  const libelles = {
    pret:     ['ok',   'Prêt à jouer sur la console'],
    activer:  ['upd',  'Sur la console — voir « Mises à jour » ci-dessous'],
    envoyer:  ['conv', phrase('%d {fichier|fichiers} à envoyer sur la console', e.aEnvoyer.length)],
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

  // The offered actions depend on the status: offering "Send to the console"
  // for a game that exists ONLY on the console makes no sense.
  const acts = [];
  if (g.needsConvert)
    acts.push('<button class="go" data-act="convertGame" data-arg="' + esc(g.key) + '">Convertir ce jeu</button>');
  if (g.console)
    acts.push('<button class="go" data-act="importerJeu" data-arg="' + esc(g.key) + '">Copier vers le serveur</button>');
  else if (e.aEnvoyer.length)
    acts.push('<button class="go" data-act="sendGame" data-arg="' + esc(g.key) + '">Envoyer vers la console</button>');
  acts.push('<button class="ghost" data-act="closeGame">Fermer</button>');

  return '<div class="sheet"' + attrsTeinte(g) + ' data-interieur>' +
    // The cover depended on the Switch title ID alone: every game from the
    // other platforms therefore opened a detail view with no image, even
    // though its card showed one. `coverImg` can search by name — that is
    // already what it does in the grid.
    '<div class="top">' + (coverImg(g, 'cover',
        'role="button" tabindex="0" title="' +
        esc(t('Voir la jaquette en grand')) + '"' +
        ' data-act="loupeJaquette"') ||
      '<div class="cover"></div>') +
    '<div><h3>' + esc(nomJeu(g)) + '</h3>' +
    // The medium, spelled out and drawn: the piece of information most missing
    // from a library that mixes twenty-three consoles.
    '<div class="supportligne">' + silhouetteHtml(g, 'support gros') +
      '<span>' + esc(nomPlateforme(g)) + '</span>' +
      // Here there is room: we name the languages instead of reducing them to
      // "MULTI" as on the cover.
      (function () {
        const l = etiquetteLangues(g);
        return l ? '<span class="sep">·</span><span class="langues">' +
                   esc(l.long) + '</span>' : '';
      })() +
    '</div>' +
    '<div class="sub2" id="gm-info">' + (g.tid ? 'chargement des infos…' : '') + '</div>' +
    // One status per line, with a coloured dot: stacking framed pills made the
    // detail view unreadable as soon as there were two pieces of information.
    '<div class="status">' + lines.map(l =>
      '<div class="stline s-' + l[0] + '"><i></i><span>' + esc(l[1]) + '</span></div>').join('') +
    '</div></div></div>' +
    '<div class="body">' +
    '<p class="gdesc" id="gm-desc"></p>' +
    // Wikipedia's text is CC BY-SA: that licence requires citing the source.
    // The line stays empty when the summary comes from elsewhere.
    '<p class="gcredit" id="gm-credit">' + creditResume(g) + '</p>' +
    '<div class="chiffres">' +
      '<div><b>' + fmt(g.size) + '</b><span>total</span></div>' +
      '<div class="pres"><b class="' + (e.presence.mac ? 'p-oui' : 'p-non') + '">' +
        (e.presence.mac ? 'oui' : 'non') + '</b><span>sur le serveur</span></div>' +
      '<div class="pres"><b class="p-' + e.presence.console + '">' +
        {oui: 'oui', partiel: 'en partie', non: 'non', inconnu: '?'}[e.presence.console] +
        '</b><span>sur la console</span></div>' +
      '<div><b>' + (g.updCount || 0) + '</b><span>{mise|mises} à jour</span></div>' +
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

// ------------------------------------------------------------ drop folder
// The drop folder: the preview groups by platform, so you see at a glance what
// goes where. A .gba ROM used to be announced under "GAMES", the Switch folder,
// while the filing put it in the right place — a preview that lies is worse
// than no preview.
// The filing button only makes sense while something is left to file: shown
// permanently, it suggested an action was pending.
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
    btn.textContent = phrase('Importer %s {élément|éléments}', items.length);
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
      '<span class="mono">' + nb(lot.length, '{fichier|fichiers}') + ' · ' +
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

// ----------------------------------------------------------------- console
// The console's state lives in a single block (renderConn).
//
// This function used to trigger a detection when it saw a device with no known
// connection. A render that starts a network call produces exactly what we
// observed: `render()` called `detect()`, which rendered, which called detect
// again... hence the duplicate notifications at startup. A render describes a
// state, it causes nothing.
// There is no longer a separate pill to update: `renderConn` draws the
// console's full state, pill included. This function only served to restart a
// detection from a render, which doubled the calls and the notifications at
// startup.

// "3 min ago", "for 2 h" — a duration reads better than a timestamp.
function duree(s) {
  s = Math.max(0, Math.round(s || 0));
  if (s < 60) return 'à l\'instant';
  const m = Math.round(s / 60);
  if (m < 60) return 'depuis ' + m + ' min';
  const h = Math.floor(m / 60);
  return 'depuis ' + h + ' h' + (m % 60 ? String(m % 60).padStart(2, '0') : '');
}

// The console's battery: a drawn pill, not a percentage lost inside a
// sentence. The fill follows the real level, the colour warns before a 12 GB
// transfer stops halfway.
// ---------------------------------------------------------- maintenance
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
        + ' · ' + nb((l.fichiers || []).length, '{fichier|fichiers}') + '</span>'
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
  // The header's single block. It answers four questions and not one more:
  // which console, over which link, for how long, on which Android. The IP
  // address and the serial number belong in Settings, not in the header.
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
      // `cnom` carries the console's NAME, a piece of data: it is in
      // CLASSES_DONNEES so as never to be translated. The "no console" label,
      // on the other hand, must be — and it carried the same class, so it
      // stayed French in an English interface. The same defect as the `tid`
      // class, which served as both marker and style.
      '<span class="cvide">Aucune console</span>' +
      '<span class="cfaits">' +
        '<button class="lien" data-act="detect">Détecter</button><i>·</i>' +
        '<button class="lien" data-act="togglePair">sans câble</button>' +
        (vers ? '<i>·</i>' + esc(vers) : '') +
      '</span>';
    el.title = t('Branche le câble USB, ou connecte la console sans fil.');
  }
}

// The offered actions depend on the state: inviting you to "Detect" a console
// that is already connected teaches nothing and clutters.
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
// ---- the SERVER's browser (not to be confused with the console's)
// This one only returns folders: the server sends back no file name. The one
// figure shown is the count of recognised games, because that is what lets you
// recognise your library without opening a terminal.
// `cible` says which of the two screens is showing the browser. The wizard
// redraws entirely on every state change: injecting the result of an async call
// into it would be wiped by the next render. So it reads `LUDO.etat`.
let LUDO = {chemin: '', etat: null, cible: 'set'};

function htmlLudo(r) {
  const parts = String(r.chemin || '').split('/').filter(Boolean);
  let acc = '';
  const segs = ['<a data-lpath="/">' + esc(t('racine')) + '</a>'];
  parts.forEach(p => { acc += '/' + p; segs.push('<a data-lpath="' + esc(acc) +
      '" data-i18n-skip>' + esc(p) + '</a>'); });
  const bouts = [nb(r.jeux || 0, '{jeu|jeux} {reconnu|reconnus}')];
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

// The same browser, as a string, for the "your library" step.
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

// The path shown in the settings, and the button beside it. A library pinned by
// ROMULE_LIBRARY must be visible: without that you click "Change" and do not
// understand the refusal.
function majLudotheque() {
  const el = $('s-ludo'), b = $('b-ludo');
  if (!el || !HEALTH) return;
  // The full path stays in the tooltip: the box truncates it in the middle, and
  // a truncated path you cannot read in full is a path you cannot check.
  //
  // A direct assignment and NOT `poserAttr()`: that one keeps the value as a
  // translation key to replay on every language change. A path is data, not a
  // sentence.
  const chemin = HEALTH.ludotheque || HEALTH.root || '';
  // `<bdi>` isolates the path from the RTL direction forced on the box.
  // Without it, the leading slash visually migrated to the END: the path looked
  // as if it ended with "/", which is false and misleading.
  el.innerHTML = '<bdi>' + esc(chemin) + '</bdi>';
  el.title = chemin;
  if (b) {
    b.disabled = !!HEALTH.ludotheque_imposee;
    b.title = HEALTH.ludotheque_imposee
      ? t('Imposé par la variable ROMULE_LIBRARY.') : '';
  }
  (HEALTH.problemes || []).forEach(p => annonce(p, 'warn'));
}

// The bare file name, the only reliable marker when the title ID in the name is
// missing or lying: it is the name adb wrote on the console.

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

// Is a library file already on the console? The library's title ID comes from
// the contents, the console's from the file name: when the name lies or carries
// none, the two cannot meet. We then fall back to the file name, as
// _console_index does server-side.
function surLaConsole(f) {
  return (f.tid && CONSET.has(f.tid + '|' + f.version)) || CONSET.has('n|' + baseName(f));
}
function consoleName(n) {
  return n.replace(/\.(nsz|xcz|nsp|xci)$/i, '').replace(/\s*\[0100.*/i, '').trim() || n;
}

// A title reduced to its essence, to recognise two files of the same game when
// their names differ: "MARVEL Cosmic Invasion (v1.0.1) (EU) SuperXCI-MBC.xci"
// and "MARVEL Cosmic Invasion v1.0.2[...]" do name the same game.
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

// What the console really holds. Clicking a row switches the library to that
// platform: the setting becomes a starting point, not a dead end.
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
    phrase('%s {plateforme|plateformes} sous %s', p.length,
           '<code>' + esc(r.racine) + '</code>') + ' · ' +
    phrase('%d {jeu|jeux} au total', p.reduce((n, s) => n + s.count, 0)) + '</div>';
  // A platform's detail now lives in "Console and emulator": clicking a card
  // leads there, rather than opening a second editor here.
}

let BATTERIE = null;
let PLATEFORMES = [], PF_OUVERTE = '';

// -------------------------------------------------- per-platform settings
// One place decides which console we are talking about. The selector chooses,
// `#pf-commun` shows what EVERY platform has (its folder on the console), and
// `#pf-specifique` only leaves visible the blocks carrying the matching
// `data-plateforme`.
let PF_REGLAGES = localStorage.getItem('pf-reglages') || 'switch';

// "generic" and "switch" are words from the code: on screen they say nothing.
// We name what the user recognises.
function moteurLisible(engine) {
  return {switch: 'Eden', generic: 'lecteur de ROMs (RetroArch, autonome…)'}[engine]
    || engine || '—';
}

function remplirSelecteurPlateforme() {
  const sel = $('s-plateforme');
  if (!sel || !SYSTEMS.length) return;
  // Platforms with settings of their own come first: they are the ones you
  // come here for.
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
        ? phrase('%s a %s {bloc|blocs} de réglages qui lui sont propres.',
                 sys.name, visibles)
        : phrase("%s n'a pas de réglage propre : seul son dossier se règle ici.",
                 sys.name));
  }
  renderPfCommun(sys);
}

// The folder on the console: the one setting EVERY platform has. It used to be
// typed in two places — here and in a detected platform's card — with the risk
// of showing two different values.
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
                     nb(vu.count, '{jeu|jeux}') + '  ·  ' + fmt(vu.bytes)]);

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
  // show nothing until the user has chosen their target folder
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
// a game's status regarding the console: ['ok','on the console'] | ['upd','partly'] | ['conv','new'] | null (console not read)
// ---------------------------------------------------- Eden configuration
// The most useful settings, with their technical name: we do not invent a label
// that would hide the real key the emulator expects.
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
      '<span class="mono">' + nb(p.reglages, '{réglage|réglages}') + ' · ' +
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

// Returns [class, rating, entry, device] — `device` is only set when the report
// comes from a console OTHER than yours. "(another device)" did not say which:
// naming the machine stays informative without being cryptic.
function erBadge(tid) {
  if (!ER.actif || !tid) return null;
  const e = ER.jeux[tid.toLowerCase()];
  if (!e || e.etat === 'absent') return null;
  if (!e.meilleur) return ['inconnu', 'Non testé', e, null];
  const [cls, txt] = ER_NIV[e.meilleur.rang] || ['inconnu', e.meilleur.note];
  const autre = !e.pour_mon_appareil ? (e.meilleur.appareil || null) : null;
  return [cls, txt, e, autre];
}

// The detail view's EmuReady block. ONE rule per situation, and never two
// messages that contradict each other — the old one showed "here are the other
// devices" right before "no report for this game".
//
//   1. module disabled ................... nothing
//   2. game not found on EmuReady ........ one sentence, done
//   3. game found, nobody shared ......... one sentence, done
//   4. settings for YOUR console ......... yours first, then the others
//   5. other consoles' settings only ..... said once, then the list
//   6. your console not specified ........ an invitation to say which
// The instructions ("View"/undo) only appear when there is at least one setting
// to apply.
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
    intro = phrase('%s {réglage|réglages} {testé|testés} sur ta %s.',
                   miens.length, esc(ER.appareil_nom));
  else
    intro = phrase('Rien de testé sur ta %s. Voici d\'autres appareils, '
                   + 'à titre indicatif.', esc(ER.appareil_nom));

  // The title found is only shown when there is doubt: otherwise it is noise.
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

// -------------------------------------------- a game's state on the console
// A game is "ready" when its playable files are on the console AND
// its updates and DLC are active in Eden. We merge the two sources.
const dsel2 = new Set();                 // games selected for deployment

function nandParChemin() {
  const m = {};
  NANDST.forEach(x => { m[x.path] = x; });
  return m;
}

// One vocabulary for the whole interface. Before, the library spoke of "update
// available / to convert / to clean" and the console of "to complete / ready":
// two scales for the same games, hence the duplicates on screen.
// Both directions of transfer must read effortlessly. "To import" was
// understood backwards: we now say WHERE the game is missing, and the button
// says what to do. The badge states, the action decides.
const ETATS = {
  probleme: ['b-orph', 'Problème'],
  importer: ['b-conv', 'Pas sur le serveur'],
  envoyer:  ['b-conv', 'Pas sur la console'],
  activer:  ['b-upd',  'MAJ à activer'],
  convert:  ['b-upd',  'À convertir'],
  pret:     ['b-ok',   'Prêt'],
  local:    ['b-dlc',  'Sur le serveur'],
};
// These states only make sense once the console has answered: without it we
// cannot know what is missing there, and showing "0" would be an invented
// answer.
const ETATS_CONSOLE = ['envoyer', 'activer', 'importer'];

// The console counts as "read" only once its files have really been listed.
// Settling for NANDCONN (Eden answers) would suggest, while the list is on its
// way, that no game is on the console: everything would show as "to send".
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

  // incomplete files: either flagged by the server, or seen in the NAND
  const casses = g.files.filter(f => f.broken);
  const aActiver = [];
  extras.forEach(f => {
    const e = nmap[f.path];
    if (!e) return;
    if (['incomplet', 'illisible'].includes(e.etat)) { if (!f.broken) casses.push(f); }
    else if (['absent', 'partiel'].includes(e.etat)) aActiver.push(f);
  });
  // A game only becomes "Problem" when ITS BASE is affected. A broken update
  // does not stop you playing: it deserves a remark, not a red flag on a game
  // that runs.
  const cassesBase = casses.filter(f => f.type === 'BASE');
  const cassesExtra = casses.filter(f => f.type !== 'BASE');

  // A "Problem" status with no reason forces you to open the detail view to
  // understand: so the reason always travels with the status.
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
  // Where the game is: two independent facts the status alone does not give.
  // "Ready" did not say it was on both sides, and a partial presence was
  // indistinguishable from an absence.
  const presence = {
    mac: true,
    console: !consoleLue() ? 'inconnu'
           : !aEnvoyer.length ? 'oui'
           : aEnvoyer.length < jouables.length ? 'partiel' : 'non',
  };
  return {etat, raison, note, presence, txt: ETATS[etat][1], aEnvoyer, aActiver, casses,
          taille: aEnvoyer.reduce((s, f) => s + f.size, 0)};
}

// Games present on the console but absent from the library: they join the same
// list instead of having a section of their own.
function jeuxConsoleSeuls() {
  if (!DGAMES.length) return [];
  const connus = new Set(GAMES.map(g => g.key));
  // The file name decides when the title ID is missing or lying: without it, a
  // game already in the library would be announced as "to import".
  const nomsLib = new Set();
  GAMES.forEach(g => g.files.forEach(f => nomsLib.add(baseName(f))));
  // A library game may carry a different name on the console: the reduced
  // title stays the only reliable common ground.
  const titresLib = new Set(GAMES.map(g => titreNormalise(g.name)));
  const dejaLa = f => f.in_library || nomsLib.has(String(f.name || '').toLowerCase())
                   || titresLib.has(titreNormalise(f.name));
  const bruts = groupDeviceGames(DGAMES)
    .filter(grp => !connus.has(grp.key) && !grp.files.some(dejaLa));

  // An .xci pack with no title ID and the same game's update formed two
  // separate groups: the game appeared twice. We match them on their reduced
  // title.
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
    // The displayed name must be the GAME's, not an update's. An .xci pack with
    // no title ID is classed INCONNU although it contains the game: so we treat
    // as "carrying the game" any file that is neither an update nor a DLC.
    const porteJeu = g => g.files.some(f => !['UPDATE', 'DLC'].includes(f.type));
    const a = porteJeu(grp), b = porteJeu(deja);
    if (a && !b) deja.name = grp.name;
    else if (a === b && grp.name.length < deja.name.length) deja.name = grp.name;
  });

  return [...parTitre.values()]
    .map(grp => ({
      key: grp.key, name: grp.name, files: grp.files, size: grp.size,
      // the GAME's title ID, not the file's: a cover only exists for the base
      tid: (f => f ? tidBase(f.tid) : null)(grp.files.find(x => x.tid)),
      updCount: grp.updCount, dlcCount: grp.dlcCount, hasBase: grp.hasBase,
      paths: grp.paths, console: true,
    }));
}

// Sorting: each criterion answers a concrete question you ask in front of your
// library ("which is the biggest?", "what is stuck?"). The year comes from IGDB:
// it did not exist before, hence the absence of that sort.
function anneeJeu(g) {
  if (!g) return 0;
  // Switch: the year comes from nlib, through META. Other platforms: from
  // IGDB, and it travels with the game. Without both paths, the sort by year
  // saw only a handful of titles.
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
// The page size used to be dictated by the tile size: it is now chosen,
// including "show everything" for a large library.
const PAR_PAGE = [24, 48, 96, 200, 0];   // 0 = everything

let TRI = localStorage.getItem('tri') || 'etat';
let SENS = localStorage.getItem('sens') === '-1' ? -1 : 1;   // 1 croissant, -1 inverse
let TAILLE = localStorage.getItem('taille') || 'moyen';
let PARPAGE = parseInt(localStorage.getItem('parpage'), 10);
if (!PAR_PAGE.includes(PARPAGE)) PARPAGE = 48;
let PAGE = 0;
let VUS_PAGE = [];          // keys shown on the current page (range selection)
let DERNIER_CLIC = null;    // anchor for Shift+click

// Advanced filters, combinable with the status. They answer questions the
// status alone does not cover: "which have DLC?", "which are large?"
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
  // Now that the year and the summary are known, two questions become
  // possible: "what is recent?" and "what is missing its details?". The second
  // is the more useful: it shows the work left to do.
  recent:   ['Sorti après 2015',  x => anneeJeu(x.g) >= 2015],
  retro:    ['Sorti avant 2000',  x => { const a = anneeJeu(x.g); return a && a < 2000; }],
  sansfiche: ['Sans description', x => !resumeJeu(x.g)],
  sansjaq:  ['Sans jaquette',     x => sansFiche(x.g)],
};
let FAV = new Set(JSON.parse(localStorage.getItem('fav') || '[]'));

// A game from another console takes the SAME shape as a Switch game, so it goes
// through the same render: same covers, same selection, same bulk actions.
// Without that the other systems inherited a second-rate view.
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
  // Present on the console but not on the server: without them, 19 GBA games
  // appeared nowhere and could not be brought back.
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
  // No updates and no DLC off the Switch: the status comes down to "where is
  // the game?". Inventing other states would be lying.
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

// A game's status, whatever its platform.
function etatDe(g) {
  return (g.systeme && g.systeme !== 'switch') ? etatSysteme(g) : etatDuJeu(g, nandParChemin());
}

// In the overview, SCONSOLE is empty: console membership is carried by the game
// itself, not by the selected platform.
function consoleLuePour(g) {
  return vueTotale() ? !!CONN.kind : (isSwitch() ? consoleLue() : SCONSOLE.length > 0);
}

// Every platform together. Each game carries the name of its own, without which
// a list of 200 mixed titles would be unreadable.
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
      // summary, year and publisher travel with the game: without them, the
      // "all platforms" view lost what the server had sent.
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

// Rebuilding AND RE-SORTING the whole library on every render costs 16.5 ms on
// 5 000 titles — measured. Since `renderLib()` is called on every keystroke in
// the search, each key exceeded a frame's budget (16 ms) and the typing
// stuttered.
//
// Yet none of that depends on the SEARCH: the unified list only changes when
// the data, the platform or the sort order change. So we keep it, and
// `jeuxFiltres()` only has to filter — which is on the order of a tenth of a
// millisecond.
//
// The signature includes `DONNEES_V`, incremented everywhere the inventory is
// replaced. Forgetting one of those places would show a stale list: that is the
// risk with any cache, and it is why there is only ONE place that increments,
// called from the three assignment sites.
let DONNEES_V = 0;
let _uniCle = null, _uniListe = null;

function inventaireChange() { DONNEES_V++; _uniCle = null; }

function jeuxUnifiesBrut() {
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

function jeuxUnifies() {
  const cle = SYS + '\u0000' + TRI + '\u0000' + SENS + '\u0000' + DONNEES_V;
  if (cle !== _uniCle) { _uniCle = cle; _uniListe = jeuxUnifiesBrut(); }
  return _uniListe;
}

/* ============================================================================
   VARIANTES REGIONALES
   ----------------------------------------------------------------------------
   Ten of this library's thirty-four Switch cards are TWO games: Pokémon FireRed
   and LeafGreen, each in five languages. A third of the grid for two titles.

   Grouping them by their DISPLAYED name is impossible: the German version is
   called "Pokémon Feuerrote Edition", the Italian one "Versione Rosso Fuoco".
   No string comparison brings them together, and it would take a translation
   table per game.

   The FILE name, however, carries the relation:

       Pokémon FireRed Version (German Ver.)
       Pokémon FireRed Version (English Ver.)
       Pokémon FireRed Version (Japanese Ver.)

   So we strip the trailing marker when it holds ONLY language or region names.
   That condition is essential: without it, "Mario Party (2019)" and "Mario
   Party" would merge, which would be wrong.
   ========================================================================== */
const LANGUES_REGIONS = new Set((
  'german english spanish french italian japanese korean chinese dutch ' +
  'portuguese russian polish swedish danish norwegian finnish brazilian ' +
  'deutsch francais italiano espanol japonais nederlands portugues ' +
  'usa europe eur jpn jap japan world us eu jp en fr de es it nl pt ru kr cn ' +
  'multi multi3 multi5 pal ntsc intl international rev').split(' '));
// Decorative words: they accompany the marker without characterising it.
const MOTS_DECOR = new Set(['ver', 'version', 'edition', 'ed', 'v']);
const MARQUEUR_FINAL = /\s*[([]([^)\]]{1,28})[)\]]\s*$/;

// Renvoie [nom de base, un marqueur a-t-il ete retire ?].
function baseSansMarqueur(nom) {
  let base = String(nom || '').trim();
  let trouve = false;
  // A file may carry two: "Game (English Ver.) [EUR]".
  for (let tour = 0; tour < 3; tour++) {
    const m = base.match(MARQUEUR_FINAL);
    if (!m) break;
    const mots = m[1].toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .split(/[\s,+._\-/]+/).filter(Boolean)
      .map(w => w.replace(/\.$/, ''))
      .filter(w => !MOTS_DECOR.has(w));
    // An empty marker ("(Ver.)") or one holding anything other than a language
    // stops the splitting: we do not guess.
    if (!mots.length || !mots.every(w => LANGUES_REGIONS.has(w))) break;
    base = base.slice(0, m.index).trim();
    trouve = true;
  }
  return [base.toLowerCase(), trouve];
}

/* -------------------------------------------------------------- LANGUAGES
   No details source gives a game's languages: neither nlib nor IGDB, in what we
   ask them for. The FILE NAME does carry them — it is the ROM-set convention:

       Zen Pinball 3D (Europe) (En,Fr,De,Es,It) (eShop).3ds
       Pokémon FireRed Version (French Ver.)

   So we only read what is written, and show nothing when nothing is: guessing
   "probably English" would invent a piece of information the user would take
   for verified. */
const CODES_LANGUE = new Set(('en fr de es it ja nl pt sv no da fi ko zh ru pl ' +  // i18n:ok - language codes
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
    // "En,Fr,De,Es,It": the WHOLE group must be made of known codes, otherwise
    // "(US)" or "(v1.0.1)" would pass for languages.
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

// One language: its code, short and unambiguous. Several: "MULTI", because
// lining up five codes on a 158 px cover would make it unreadable — the detail
// goes in the tooltip and in the detail view.
function etiquetteLangues(g) {
  const codes = languesJeu(g);
  if (!codes.length) return null;
  const noms = codes.map(c => NOM_CODE[c] || c.toUpperCase()).join(', ');
  return codes.length === 1
    ? {court: codes[0].toUpperCase(), long: noms}
    : {court: 'MULTI', long: noms};
}


// Which version represents the group: the one in the interface's language when
// it exists, else the English one, else the first to hand. Showing a game's
// Japanese version to a French-reading user would be an arbitrary choice.
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

// Each group's members, as the last displayed list saw them. The versions
// dialog reads them back: it shows exactly what the library holds at the moment
// you open it, filters included.
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
  // A group only exists when several games make it up AND at least one of them
  // really carried a language marker.
  GROUPES = new Map();
  for (const [base, p] of paquets)
    if (p.membres.length > 1 && p.marque) GROUPES.set(base, p.membres);
  if (!GROUPES.size) return liste;

  // A group takes ONE card, always. Expanding the versions in the middle of the
  // grid mixed them with the other games: nothing said where the group began or
  // ended. They now have their own dialog.
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
  // the search covers BOTH names: the file name and the official title
  let l = tous.filter(({g}) => !q || g.name.toLowerCase().includes(q)
                            || nomJeu(g).toLowerCase().includes(q));
  if (FILTER !== 'all') l = l.filter(({e}) => e.etat === FILTER);
  FAV.forEach(k => { if (FAVANCES[k]) l = l.filter(FAVANCES[k][1]); });
  return l;
}



// Everything the selection allows, in both directions: what is missing on the
// console, what is missing on the server, and what can be removed from each
// side.
function deployCibles() {
  // Off the Switch: no NAND and no updates, but the same gestures — send,
  // remove from the console, move to the trash.
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


// ---------------------------------------------------------------- settings
// The description shown under each menu: the user sees the effect of their
// choice without unfolding three walls of text.
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
// The SSO fields only make sense in SSO mode: we hide them otherwise, rather
// than leaving a dozen inert fields on screen.
function majBlocAuth() {
  const sel = $('s-authmode'), bloc = $('blocoidc'), interne = $('blocinterne');
  if (!sel || !bloc) return;
  const mode = sel.value;
  bloc.style.display = mode === 'oidc' ? '' : 'none';
  if (interne) interne.hidden = mode !== 'interne';
  const c = DATA.config || {};
  // A mode announced but unusable protects nothing: saying so plainly beats
  // letting someone believe the access is locked.
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
  chargerNotifs();
}

// -------------------------------------------------------------- API keys
// They are shown once. The store keeps only a digest, which makes a leak of the
// state file harmless — but forbids showing them again. This block's whole
// ergonomics follow from that constraint: the key appears large at creation,
// with a copy button, and the user is warned it will not come back.
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
  // "never" is a fact worth reporting, not an absence to hide: a key created
  // for a trial and never used still opens the API.
  if (!t0) return t('jamais utilisée');
  // Locale tags are not interface text: they are not translated, they are
  // chosen.
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
    actions: [{libelle: t('Copier'), principal: true, faire: () => {
      navigator.clipboard.writeText(r.secret)
        .then(() => toast(t('Clé copiée.'), 'ok'))
        // The clipboard is refused outside a secure context: without this
        // fallback the button would do nothing, without a word. The key stays
        // readable in the dialog's detail, hence selectable by hand.
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
    actions: [{libelle: t('Révoquer'), principal: true, faire: async () => {
      const r = await api('/api/cle-revoquer', {id});
      if (r && r.ok) toast(t('Clé révoquée.'), 'ok');
      chargerCles();
    }}],
  });
}

// ------------------------------------------------------ notifications sortantes
//
// The address is NEVER returned by the server: a Discord webhook is a bearer
// secret, and showing it would put it in the browser history and on any
// screenshot of the settings. We only show the host, which is enough to tell
// which is which.
let NOTIFS = [], NOTIF_EVTS = {};

async function chargerNotifs() {
  const r = await api('/api/notifs', null, true);
  if (!r || r.error) return;
  NOTIFS = r.destinations || [];
  NOTIF_EVTS = r.evenements || {};
  dessinerNotifs();
}

function dessinerNotifs() {
  const boite = $('listenotifs');
  if (!boite) return;
  if (!NOTIFS.length) {
    boite.innerHTML = '<p class="lead" style="margin:0 0 8px">'
      + esc(t('Aucune destination. Romule ne prévient que cet écran.'))
      + '</p>';
    return;
  }
  boite.innerHTML = NOTIFS.map(d =>
    '<div class="compte-ligne">'
    + '<span class="compte-nom" data-i18n-skip>' + esc(d.nom || d.service) + '</span>'
    + '<span class="compte-mail tid" data-i18n-skip>' + esc(d.service) + '</span>'
    + '<span class="mono" data-i18n-skip>' + esc(d.apercu) + '</span>'
    + '<button class="ghost mini" data-act="testerNotif" data-arg="'
    + esc(d.id) + '">' + esc(t('Tester')) + '</button>'
    + '<button class="ghost mini" data-act="supprimerNotif" data-arg="'
    + esc(d.id) + '">' + esc(t('Retirer')) + '</button>'
    + '</div>').join('');
}

async function ajouterNotif() {
  const cn = $('s-notifnom'), cu = $('s-notifurl');
  const url = (cu && cu.value || '').trim();
  if (!url) {
    toast(t('Colle l\'adresse du webhook.'), 'warn');
    if (cu) cu.focus();
    return;
  }
  const r = await api('/api/notif-creer',
                      {nom: (cn && cn.value || '').trim(), url});
  if (!r || r.error) return;
  if (cn) cn.value = '';
  if (cu) cu.value = '';
  NOTIFS = r.destinations || [];
  dessinerNotifs();
  toast(t('Destination ajoutée.'), 'ok');
}

async function supprimerNotif(id) {
  const r = await api('/api/notif-supprimer', {id});
  if (!r || r.error) return;
  NOTIFS = r.destinations || [];
  dessinerNotifs();
  toastAction(t('Destination retirée.'), '', null, 'ok');
}

function _direResultatNotif(r) {
  if (!r) return;
  if (r.ok) toast(t('Envoyé. Regarde ton salon.'), 'ok');
  // The detail carries the HTTP code or the error's name: without it, "failed"
  // does not say whether the address is wrong or the service is down.
  else toast(phrase('Échec : %s', r.detail || r.error || '?'), 'warn');
}

async function testerNotif(id) {
  _direResultatNotif(await api('/api/notif-tester', {id}));
}

async function testerNotifSaisie() {
  const cu = $('s-notifurl');
  const url = (cu && cu.value || '').trim();
  if (!url) { toast(t('Colle l\'adresse du webhook.'), 'warn'); return; }
  _direResultatNotif(await api('/api/notif-tester', {url}));
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
      // We do not offer to remove the last account: nobody could get in any
      // more.
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
    // `?v=`: without it the browser would show the old photo again after a
    // change, the response being cached.
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

// The account routes return their refusals in plain words (password too short,
// email already taken...): we show them as-is rather than letting the generic
// error dialog come up.
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

// Two deliberate steps: the factor is only declared active after a valid code
// has been seen. Otherwise a mis-configured app locks the account.
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

// One dialog for ALL the files to file: opening one per file would be
// unbearable as soon as ten are dropped.
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
    + '<p class="dmsg">' + phrase('%d {fichier|fichiers} portent une extension que ', items.length)
    + 'plusieurs plateformes utilisent. Choisis, ou laisse-les dans le dépôt.</p>'
    + '</div></div>'
    + '<div class="classer">' + items.map(ligne).join('') + '</div>'
    + '<div class="acts"><button class="go" data-di="ok">Ranger</button>'
    + '<button class="ghost" data-di="close">Plus tard</button></div></div>';
  // Reopening cancels a closing already under way: without this, the deferred
  // cleanup in `fermerVoile` would empty the dialog we have just opened.
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
  // Fields tied to a source stay ALWAYS visible: we do not hide a setting the
  // user might go looking for. We merely say it is inactive with the chosen
  // source.
  const prov = $('s-coverprov').value;
  const marquer = (row, actif, quand) => {
    $(row).classList.toggle('inactive', !actif);
    // This text was rendered by `content: attr(data-note)` in CSS: it is then
    // NEVER a text node, so neither the observer nor any tool can see it — and
    // it could not be translated. It becomes a real element, filled through
    // `textContent`.
    const cible = $(row).querySelector('.setlab span');
    let note = cible && cible.querySelector('.setnote');
    if (cible && !note) {
      note = document.createElement('span');
      note.className = 'setnote';
      cible.appendChild(note);
    }
    if (note) {
      note.textContent = actif ? ''
        // `quand` is itself a label: leaving it raw showed "— used only with
        // “URL personnalisée”", half translated.
        : phrase('— utilisée seulement avec « %s »', t(quand));
    }
  };
  marquer('row-sgkey', prov === 'steamgriddb', 'SteamGridDB');
  marquer('row-coverurl', prov === 'custom', 'URL personnalisée');
}
function fillSettings() {
  const c = DATA.config || {};
  // a field may have been removed from the page: we never assume it is there
  const set = (id, v) => {
    const el = $(id);
    if (el && v != null && document.activeElement !== el) el.value = v;
  };
  set('s-oidcissuer', c.oidc_issuer); set('s-oidcclient', c.oidc_client_id);
  set('s-oidcsecret', c.oidc_client_secret); set('s-oidcemails', c.oidc_emails);
  set('s-oidcgroupes', c.oidc_groupes); set('s-oidcadmingroupes', c.oidc_admin_groupes); set('s-oidcredirect', c.oidc_redirect);
  // `aucun` is the setting's VALUE, not its label: the displayed option lives
  // in index.html and goes through the catalogue.
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
  if ($('s-majcheck')) $('s-majcheck').checked = c.maj_check !== false;
  $('s-layout').value = c.push_layout || 'type';
  $('s-local').value = c.local_layout || 'type';
  $('s-verify').value = c.verify_mode || 'size';
  $('s-coverprov').value = c.cover_provider || 'nlib';
  syncSetDesc();
}

// ----------------------------------------------------------------- app
// The profiles come from /api/health: the server alone knows which are shipped,
// and which is active.
function nomEmulateur(cle) {
  const p = ((HEALTH && HEALTH.profils) || []).find(x => x.cle === cle);
  return p ? p.nom : (cle || '');
}

// The footer carries the source offer the AGPL requires. The values come from
// the server: a version hard-coded in the page always ends up lying after an
// upgrade.
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
  // An `<option>` contains text and nothing else: the profile's name cannot be
  // separated there from its "not verified" note. So the sentence is assembled
  // ALREADY translated, otherwise the DOM walk looks for "Eden — not verified"
  // as a single key, which no catalogue will ever hold.
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
    // A non-administrator has no business in the settings: the server would
    // refuse everything they did there. Letting them in by mistake would mean
    // letting them run into 403s.
    if (name === 'settings' && !ROLE.admin) return;
    // We note where the reading was before switching tab: coming back from the
    // settings used to return to the very top of the library, forcing you to
    // find by hand the card you were looking at.
    const actuel = document.querySelector('.panel.active');
    if (actuel) DEFILEMENT[actuel.id] = scrollY;
    const poser = () => {
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
      $('panel-' + name).classList.add('active');
      // The previews' sample cover only exists once the library has been read:
      // on the first visit to the settings, it is finally known.
      if (name === 'settings') majApercuJaquette();
      // Restored after the panel change: before it, the page height is still
      // that of the old tab and the browser clamps the requested position.
      const y = DEFILEMENT['panel-' + name];
      requestAnimationFrame(() => scrollTo({top: y || 0, behavior: 'instant'}));
    };
    // A native cross-fade when the browser can do it. Without it the two
    // panels swap at once; with it, the old one fades while the new one
    // settles. No library: this is a browser API.
    // We skip it when the user has turned motion off, otherwise the transition
    // keeps running although they asked for the opposite.
    const bouge = document.documentElement.dataset.mvt !== 'aucun';
    if (bouge && document.startViewTransition) {
      // Marks the TYPE of transition: opening a detail view uses another one,
      // and the two share the same pseudo-elements.
      document.documentElement.classList.add('vt-onglet');
      const t = document.startViewTransition(poser);
      const fini = () => document.documentElement.classList.remove('vt-onglet');
      t.finished.then(fini, fini);
    } else poser();
  },
  // The console is queried once, at startup: the game list depends on it, and
  // it is no longer behind a tab you would have to open.
  _consoleReady: false,
  async reveilConsole() {
    if (this._consoleReady) return;
    this._consoleReady = true;
    // `detect()` already chains into reading the files and the NAND: doing it
    // again here doubled every call, and every notification.
    await this.detect();
    if (!CONN.kind) return;                 // nothing to read: we stay offline
    this.ecLoad();
  },
  setFilter(f) {
    FILTER = f; PAGE = 0;   // changing filter always returns to the first page
    majChips();
    renderLib();
  },

  // called on every keystroke in the search: the current page no longer applies
  renderLib() { PAGE = 0; renderLib(); },

  // ---- library: per-game actions
  // Searches the DISPLAYED list, not only the Switch library: games from other
  // platforms and those present only on the console do not appear there, so
  // their detail view stayed empty.
  gameByKey(k) {
    const t = jeuxUnifies().find(x => x.g.key === k);
    return t && t.g;
  },
  async openGame(k) {
    const g = this.gameByKey(k); if (!g) return;
    ouvrirDepuisJaquette(k, () => {
      $('modal').innerHTML = openGameHtml(g);
      // Reopening cancels a closing already under way: without this, the
      // deferred cleanup in `fermerVoile` would empty the dialog we just opened.
      $('modal').classList.remove('ferme');
      $('modal').classList.add('open');
      auPremierPlan($('modal'));
    });
    const info = $('gm-info'), desc = $('gm-desc');

    // What we already know, straight away: the detail view must never stay
    // stuck on "loading…" when no remote entry exists.
    const resume = resumeJeu(g);
    if (desc && resume) desc.textContent = resume;
    if (!g.tid) {
      const sys = SYSTEMS.find(x => x.key === (g.systeme || SYS));
      const bits = [sys && sys.name,
                    nb(g.files.length, '{fichier|fichiers}'),
                    ((g.files[0] || {}).ext || '').toUpperCase()].filter(Boolean);
      if (info) info.textContent = bits.join('  ·  ');
      return;
    }
    this.loadBackups(g.tid.toUpperCase());   // the configuration history
    const r = await api('/api/game-meta', {tid: g.tid});
    const m = r.meta;
    if (!m || !info) { if (info) info.textContent = ''; return; }
    const bits = [m.publisher, m.releaseDate ? fmtDate(m.releaseDate) : null,
      m.numberOfPlayers ? m.numberOfPlayers + ' {joueur|joueurs}' : null].filter(Boolean);
    info.textContent = bits.join('  ·  ');
    if (desc && m.description) desc.textContent = m.description;
  },
  closeDialog(e) {
    if (!e || e.target === $('dialog')) fermerVoile($('dialog'));
  },
  closeGame(e) { if (!e || e.target === $('modal')) fermerVoile($('modal')); },
  // Activate ONE game's updates and DLC in Eden, from its detail view. The same
  // treatment in bulk stays available through the selection.
  async activerJeu(k) {
    const g = this.gameByKey(k);
    if (!g) return;
    if (!CONN.kind) return toast('Connecte d\'abord la console.', 'warn');
    const e = etatDuJeu(g, nandParChemin());
    if (!e.aActiver.length) return toast('Rien à activer pour ce jeu.', 'warn');
    const r = await api('/api/deploy', {envoyer: [], activer: e.aActiver.map(f => f.path), configs: []});
    if (!r.error) {
      toast(phrase('Activation de %s {élément|éléments} lancée.', e.aActiver.length), 'ok');
      this.closeGame();
      this.poll();
    }
  },
  // Bring back a game that exists only on the console, from its detail view.
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
    r.error || (toast(phrase('Conversion de %d {fichier|fichiers} lancée.', paths.length), 'ok'), this.poll());
  },
  // Sending depends on the platform: the Switch goes through the
  // GAMES/UPDATE/DLC filing and only accepts decompressed containers; the other
  // consoles receive their ROM as-is. Without that distinction, a 3DS or GBA
  // game was told "no file to send" although it was right there — its extension
  // simply was not a Switch game's.
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
    // No more `confirm()`: it was not translatable — the browser writes it —
    // and it charged the price of a mistake that is not one, since the trash
    // can be restored.
    const r = await api('/api/trash', {paths: [path]});
    if (!r || r.error) return;
    this.closeGame();
    await this.scan();
    toastAction(phrase('%d {fichier|fichiers} à la corbeille.', r.n),
                t('Annuler'), () => this.restore(r.lot), 'ok');
  },

  // ---- systems / other consoles
  // Two close calls share the same promise: the platform list was read twice at
  // startup, once by the launch sequence and once by the detection.
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
  // Switching platform must neither jump, nor reload what has already been
  // seen.
  //
  // The old version emptied `SGAMES`, `SCONSOLE` and `SALL` THEN waited for a
  // network round trip. In between, the grid was empty: the content collapsed,
  // the page scrolled back up, then everything returned. And nothing was kept,
  // so coming back to an already-seen platform downloaded it again.
  //
  // Two changes, and the order matters: we keep the current display until we
  // have something to replace it with, and we remember what we received.
  async setSystem(key) {
    if (SYS === key && CACHE_SYS[key]) return;    // already here, nothing to do
    SYS = key; dsel2.clear(); PAGE = 0;
    localStorage.setItem('systeme', key);

    const garde = CACHE_SYS[key];
    if (garde) { appliquerSysteme(garde); renderLib(); return; }

    // Nothing cached: we announce the loading WITHOUT emptying, so the grid's
    // height does not move — that is what made the page jump.
    R.classe($('lib'), 'charge', true);
    const jeton = ++CHARGE_SYS;
    try {
      const donnees = vueTotale()
        ? {tout: (await api('/api/library-all', {})).systemes || []}
        : isSwitch() ? {switch: true}
                     : await api('/api/system-games', {system: key});
      // An answer that lands after we changed our mind must overwrite nothing:
      // two quick clicks otherwise produced the FIRST platform's inventory
      // under the second one's name.
      if (jeton !== CHARGE_SYS) return;
      CACHE_SYS[key] = donnees;
      appliquerSysteme(donnees);
      renderLib();
    } finally {
      if (jeton === CHARGE_SYS) R.classe($('lib'), 'charge', false);
    }
  },
  // One main action off the Switch too: it sends the console what is missing,
  // and brings back what exists only over there.
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

  // ---- integrity / backups
  // `budgetGo` limits the pass to one slice: what has never been checked first,
  // then the oldest. A full 160 GB verification never gets started in practice;
  // slice by slice, the coverage grows.
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
          esc(i.name) + '</span><span class="mono">' + nb(i.count, '{fichier|fichiers}') + '</span>' +
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
    if (DATA && DATA.moi) { ROLE = DATA.moi; appliquerRole(); }
    render();
    this.loadTrash();
    return this.loadSystems();     // attendue : la sequence de lancement en depend
  },
  async versions(force) { say('Vérification des versions...'); DATA = await api('/api/versions', {force: !!force}); render(); toast('Mises à jour vérifiées.', 'ok'); },
  async doImport() { const r = await api('/api/import', {convert: true}); r.error || (toast('Import lancé.', 'ok'), this.poll()); },
  async reloadImport() { const r = await api('/api/import-list'); renderImport(r.items); toast(phrase('%d {élément|éléments} dans le dépôt.', r.items.length)); },
  copyShop() {
    navigator.clipboard.writeText(DATA.shop_text || '')
      .then(() => toast('Liste copiee.', 'ok')).catch(() => toast('Copie impossible, selectionne le texte.', 'warn'));
  },
  async nandWrite() { const r = await api('/api/nand-write', {}); toast(r.message, 'ok'); },
  // ---- appearance: theme, cover animation, motion
  // These three settings live in the browser and not in the server's config:
  // they describe a SCREEN, not a library. The same library is read in light on
  // a tablet and in dark on the console, and a device preference has no
  // business travelling.
  setTheme(v) { poserApparence('theme', v, ['sombre', 'clair', 'auto']); },
  setCarte(v) { poserApparence('carte', v, ['aucune', '0', '1', '2', '3', '4', '5']); },
  // The setting's three allowed values, not labels.
  setMouvement(v) { poserApparence('mvt', v, ['complet', 'reduit', 'aucun']); },  // i18n:ok

  // ---- interface language
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
    // Translation replaces the text IN the DOM: going back would require
    // remembering every original. Reloading the page starts from the right
    // foot, and the language is already saved server-side.
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
        : phrase('%d {jeu|jeux} reconnus', n)
          + (absents ? phrase(', %d {absent|absents} de leur base', absents) : '')
          + t('. Les badges apparaissent sur les jaquettes.');
    renderLib();
  },
  async erDevices() {
    const r = await api('/api/emuready-devices', {});
    ER_DEVICES = (r.tous || []);
    const sug = r.suggestions || [];
    // the detected console's variants first, then all the rest
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
    if (!nom) {                       // empty field: the model is removed
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
    // the remembered reports were sorted for the old model: we redo the
    // analysis at once, otherwise the user sees other consoles.
    toast('Console : ' + d.nom + '. Recalcul des notes…', 'ok');
    this.erSync(true);
  },
  async erSync(force) {
    if (!ER.actif) return toast('Active d\'abord EmuReady dans les réglages.', 'warn');
    const r = await api('/api/emuready-sync', {force: !!force});
    r.error || (toast('Consultation d\'EmuReady…', 'ok'), this.poll());
  },
  // See before applying: we show the report's actual settings.
  async erPreview(listingId, tid, appareil) {
    say('Lecture de la configuration…');
    const r = await api('/api/emuready-preview', {listing_id: listingId});
    if (r.error) return;
    const lignes = (r.contenu || '').split('\n');
    // we highlight the settings this report actually imposes
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
      message: phrase('Testée sur %s · %s {section|sections}, %s {réglage|réglages} '
                      + '{spécifique|spécifiques}. Le reste suit tes réglages globaux.',
                      appareil, r.sections, r.surcharges),
      detail: (imposes.length ? 'RÉGLAGES IMPOSÉS PAR CE RAPPORT\n' + imposes.join('\n') +
               '\n\n— fichier complet —\n' : '') + (r.contenu || ''),
      fermer: 'Fermer',
      actions: [{libelle: 'Appliquer ces réglages', principal: true,
                 faire: () => this.erApply(listingId, tid)}],
    });
  },

  // History: every write left a restorable backup.
  async loadBackups(tid) {
    const el = $('er-backups');
    if (!el || !tid) return;
    const r = await api('/api/eden-backups', {tid});
    const items = r.items || [];
    if (!items.length) { el.innerHTML = ''; return; }
    el.innerHTML = '<div class="mono" style="margin:10px 0 4px">Revenir en arrière :</div>' +
      items.slice(0, 4).map(b =>
        '<div class="errow"><span class="grow">' + esc(b.quand) + ' · ' +
        (b.vide ? t('aucune configuration')
                : nb(b.sections, '{section|sections}') + ', '
                  + nb(b.surcharges, '{réglage|réglages}')) +
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

  // ---- Eden configuration
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
      if (!v) return;                                   // empty = leave alone
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
          'Appliquer %s {réglage|réglages} %s ?\n\n'
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
    // The NAND state feeds `etatDuJeu()`: it is therefore part of what the
    // unified list reflects.
    NANDST = r.items || []; NANDCONN = !!r.connectee; inventaireChange();
    renderLib();          // the NAND state feeds the unified view
  },




  // ---- console
  // ---- wireless connection
  togglePair() {
    // pairing lives in the settings: we take the user there rather than open
    // a block they would not see from the game list
    this.tab('settings');
    const w = $('pairwrap');
    const ouvre = w.style.display === 'none';
    w.style.display = ouvre ? '' : 'none';
    if (ouvre) { this.wizStep(1); w.scrollIntoView({block: 'center', behavior: 'smooth'}); }
  },
  // Wizard: one visible step at a time, each saying WHERE to act.
  wizStep(n) {
    for (let i = 1; i <= 3; i++) {
      const el = $('wstep' + i);
      if (el) el.classList.toggle('on', i === n);
    }
    const b = $('wizbar');
    if (b) b.style.width = Math.round(n / 3 * 100) + '%';
    if (n === 3) {
      this.wizCheck();
      this.wifiDiscover();               // pre-fills the address if it can be found
      const a = $('pair-addr'); if (a && !a.value) a.focus();
    }
  },
  // Validates as you go: the user sees what is missing before failing.
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

  // ---- open the interface on the console
  async refreshInstall() {
    const r = await api('/api/console-url', {});
    const wrap = $('installwrap');
    // The header's compact button: the label stays short, the explanation
    // moves into a tooltip. Disabled rather than hidden when it is not ready
    // yet, so the user knows the feature exists.
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
    // The upload ceiling comes from the server: freezing it in the browser
    // would mean lying as soon as the host changes it.
    TELEVERSEMENT_MAX = ((HEALTH || {}).checks || {}).televersement_max || 0;
    const vu = localStorage.getItem('onboard-vu') === '1';
    renderChoixEmulateur();
    renderPied();
    majLudotheque();
    if (force || (HEALTH.first_run && !vu)) renderOnboard();
    return HEALTH;
  },
  // From the wizard: take the user where an account is created, rather than
  // describe the path to them.
  allerComptes() {
    this.closeOnboard();
    this.tab('settings');
    voirSectionReglages('sec-acces');
  },

  // The emulator profile dictates every path on the console: changing it from
  // the wizard avoids having to hunt for it in the settings before even having
  // understood what it is for.
  async choisirEmulateur(cle) {
    await this.saveField('emulateur', cle);
    // The Android package name differs between versions: we ask the console
    // which one is actually installed, rather than guess.
    try { await api('/api/emulateur-detecter', {}); } catch (e) { /* no console */ }
    await this.checkHealth(true);
  },

  // ---- assistant de premier demarrage ------------------------------------
  onbPrec() { onbAller(ONB.i - 1); },
  onbSuiv() { onbAller(ONB.i + 1); },
  onbAller(i) { onbAller(i); },

  // Counting games per platform is the only way to know whether the folder
  // given is the right one. A path accepted with nothing inside is a wrong path
  // you only discover an hour later.
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
      // Switch games are not counted by `systems`: they come from the
      // inventory, the only thing able to tell a game from its update.
      const n = x.engine === 'switch' ? (stats.base || 0) : (x.count || 0);
      if (n > 0) { plateformes.push({nom: x.name, n: n}); total += n; }
    });
    plateformes.sort((a, b) => b.n - a.n);
    ONB.resultatScan = {
      total: total, plateformes: plateformes,
      extensions: (sys.extensions || []).length,
    };
    if (total) {
      DATA = lib; GAMES = groupGames(); inventaireChange(); renderLib();
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

  // Saving without checking means letting the user find out in a month that
  // their key was pasted wrong. So we ask for a cover straight away, on a game
  // they have just scanned.
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

  // The wireless connection already has its full wizard in the settings:
  // rebuilding it here in miniature would only mean two of them to maintain.
  // "What the console already holds" is the first question you ask once
  // plugged in, and the only one that avoids re-importing what is already there.
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

  // A cover missing on the first try (an online search is under way) is
  // retried once before giving up: otherwise it never comes back.
  coverRate(img) {
    // A broken image shows the browser's grey box with its alternative text —
    // so during the 2.5 s of the retry, the card displayed a broken rectangle.
    // We hide it at once: `.cover`'s background already acts as an empty
    // sleeve, as it does in the grid.
    img.classList.add('vide');
    if (img.dataset.retry) { img.remove(); return; }
    img.dataset.retry = '1';
    const base = img.src.split('&r=')[0];
    setTimeout(() => { img.src = base + '&r=1'; }, 2500);
  },

  // A cover has just arrived: we take its colour if we do not know it yet, and
  // set it on the card (or on the detail view). The computation happens once
  // per game in the browser's lifetime.
  // The detail view's cover opens full size. We go through the element rather
  // than a hard-coded URL: it is the SAME image, already loaded, so the
  // enlargement is instant.
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
      // Assembled, the sentence was translatable by no catalogue.
      annonce(phrase('Aucune console prête (%s).', d.state || t('non connectée')), 'warn');
    }
  },

  // Reading what the console carries ALWAYS goes through here. Two overlapping
  // calls share the same promise instead of starting the read again: that is
  // what produced "148 file(s)…" three times in a row.
  chargerConsole() {
    if (this._lectureConsole) return this._lectureConsole;
    this._lectureConsole = (async () => {
      try {
        if (DATA.config && DATA.config.device_dir) await this.explore();
        else await this.detectDir();   // no folder known: we look for it
        await this.loadNand();         // the NAND state only means something once connected
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
      majReglagesPlateforme();     // the folder shown comes from the configuration
    }
    return r.config;
  },
  async detectDir() {
    say('Recherche du dossier de jeux...');
    const r = await api('/api/device-detect-dir', {});
    if (!r.dir) return toast('Aucun dossier trouvé. Utilise « changer » pour naviguer.', 'warn');
    const actuel = (DATA.config || {}).device_dir;
    // Never silently replace an already chosen folder: a rough detection has
    // wiped a correct setting before.
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
  // The same browser picks the ROM root, the Switch folder or any platform's:
  // only the TARGET changes.
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
      // an absolute path: it wins over the sub-folder name deduced from the root
      const dirs = Object.assign({}, (DATA.config || {}).system_dirs || {});
      dirs[CIBLE_PARCOURS] = BROWSE_PATH;
      await this.saveField('system_dirs', dirs);
      toast(libelleSysteme(CIBLE_PARCOURS) + ' : ' + BROWSE_PATH, 'ok');
    }
    $('browserwrap').style.display = 'none';
    majReglagesPlateforme();       // the path shown follows immediately
    this.detecterPlateformes();
  },
  setDpath(p) { BROWSE_PATH = p; this.tab('settings'); $('browserwrap').style.display = ''; this.browse(p); },

  // ---- where the games are, on the machine hosting the service
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
      // Deliberately quiet: running into a forbidden folder while browsing is
      // ordinary, and opening an error dialog on every click would be worse
      // than the problem.
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
    // The answer already CARRIES the new folder's inventory: calling
    // `/api/scan` here means walking twice over a tree that can be several
    // terabytes.
    DATA = r;
    render();
    this.loadTrash();
    await this.loadSystems();
    annonce(phrase('Ludothèque : %s — %d {jeu|jeux}.', LUDO.chemin,
                   (r.files || []).length), 'ok');
    if (LUDO.cible === 'onb') {
      // The scan result was about the OLD folder: keeping it would validate
      // the step with a figure that no longer matches anything.
      LUDO.cible = 'set'; LUDO.etat = null; ONB.resultatScan = null;
      renderOnboard();
    }
  },
  async ludoNouveau() {
    if (!LUDO.chemin) return toast(t('Ouvre d\'abord un dossier.'), 'warn');
    const nom = prompt(t('Nom du nouveau dossier :'), 'Romule');
    if (!nom) return;
    // A name, not a path: the input must not be a way to climb the tree. The
    // server would refuse, but there is no point offering it.
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
    DGAMES = r.games || []; buildConset(); inventaireChange();
    renderLib(); this.checkTree();
    annonce(phrase('%d {fichier|fichiers} sur la console, %d {absent|absents} du serveur.',
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

  // ---- selection and main action
  // A click on a card ticks the game if something remains to be done to it,
  // otherwise it opens its detail view: the same gesture never does two things
  // at random.
  // Click = tick. Shift+click = tick the whole range since the last click, as
  // in a file explorer. The detail view opens through "Details".
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
  // Ticking a game must touch ONLY its card. Redrawing the whole list replayed
  // the entry animation of dozens of thumbnails: visually, the page looked
  // reloaded on every click.
  // No more manual DOM updates: renderLib() reconciles, so ticking touches only
  // the card concerned, without rebuilding or re-animating the grid.
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

  // Removing files from the console: a destructive action, so we show exactly
  // what is leaving before asking for confirmation.
  async supprimerConsole() {
    const {supprConsole} = deployCibles();
    if (!supprConsole.length) return toast('Rien à retirer de la console.', 'warn');
    dialogue({
      titre: phrase('Retirer %d {fichier|fichiers} de la console ?', supprConsole.length),
      niveau: 'warn',
      message: 'Ces fichiers seront supprimés de la console. Tes copies sur le serveur ne sont pas touchées.',
      detail: supprConsole.slice(0, 20).map(p => p.split('/').pop()).join('\n') +
              (supprConsole.length > 20
               ? '\n' + phrase('… et %d {autre|autres}', supprConsole.length - 20)
               : ''),
      fermer: 'Annuler',
      actions: [{libelle: 'Retirer', principal: true, faire: async () => {
        const r = await api('/api/device-remove', {paths: supprConsole});
        if (!r.error) { dsel2.clear(); toast('Suppression lancée.', 'ok'); this.poll(); }
      }}],
    });
  },
  // The local trash: nothing is erased, everything stays restorable.
  //
  // No more confirmation dialog. The trash IS the undo: asking "are you sure?"
  // before putting a file in it charges every time the price of a mistake that
  // costs nothing. We act, and the toast offers to go back for eight seconds.
  async corbeilleSelection() {
    const {local} = deployCibles();
    if (!local.length) return toast('Rien à mettre à la corbeille.', 'warn');
    const r = await api('/api/trash', {paths: local});
    if (!r || r.error) return;
    dsel2.clear();
    await this.scan();
    toastAction(phrase('%d {fichier|fichiers} à la corbeille.', r.n),
                t('Annuler'), () => this.restore(r.lot), 'ok');
  },
  // "Tick all" covers the whole filtered result set, not just the visible
  // page: otherwise the gesture lies as soon as there is pagination.
  // A game's versions get their own dialog. It goes through `#dialog` and not
  // `#modal`: opening a version's detail view from the list must be able to
  // sit ON TOP, and Esc must close one then the other.
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

  // ---- filters: counting them, clearing them, saving them
  //
  // Three mechanisms coexist — the search, the state pill, the advanced
  // filters — and nothing said how many were active. You could spend ten
  // minutes wondering why the grid was empty when a filter set the day before
  // was still holding.
  // The release-notes dialog. Two buttons: read the full release, or close.
  // Romule does NOT update itself — it runs in a container or under a package
  // manager, and deciding in the operator's place would be out of line.
  voirMaj() {
    if (!MAJ) return;
    dialogue({
      titre: phrase('Version %s disponible', MAJ.version || '?'),
      niveau: 'ok',
      message: MAJ.titre && MAJ.titre !== MAJ.version ? MAJ.titre : '',
      detail: notesLisibles(MAJ.notes) || t('Aucune note de version publiée.'),
      fermer: t('Plus tard'),
      actions: [{libelle: t('Voir la publication'), principal: true, faire: () => {
        if (MAJ.url) window.open(MAJ.url, '_blank', 'noopener');
      }}],
    });
  },

  effacerFiltres() {
    const champ = $('filter');
    if (champ) champ.value = '';
    FILTER = 'all';
    FAV.clear();
    localStorage.removeItem('fav');
    PAGE = 0;
    renderLib();
  },

  async enregistrerVue() {
    const f = filtresCourants();
    dialogue({
      titre: t('Enregistrer cette vue'),
      niveau: 'info',
      // We SHOW what will be saved: nobody should blindly store a combination
      // they cannot read back afterwards.
      message: resumeFiltres(f),
      champs: [{id: 'nom', libelle: t('Nom de la vue'),
                exemple: t('À convertir sur Switch')}],
      actions: [{libelle: t('Enregistrer'), principal: true,
                 faire: async saisies => {
        const r = await api('/api/vue-creer', {nom: saisies.nom, filtres: f});
        if (!r || r.error) return;
        VUES = r.vues || [];
        dessinerVues();
        toast(t('Vue enregistrée.'), 'ok');
      }}],
    });
  },

  appliquerVue(id) {
    const v = VUES.find(x => x.id === id);
    if (!v) return;
    const f = v.filtres || {};
    const champ = $('filter');
    if (champ) champ.value = f.recherche || '';
    FILTER = f.etat || 'all';
    FAV.clear();
    (f.avances || []).forEach(k => FAV.add(k));
    localStorage.setItem('fav', JSON.stringify([...FAV]));
    PAGE = 0;
    // The platform last: `setSystem` redraws, and doing it earlier would have
    // drawn the grid with the old filters.
    if (f.systeme && f.systeme !== SYS) this.setSystem(f.systeme);
    else renderLib();
  },

  async supprimerVue(id) {
    const r = await api('/api/vue-supprimer', {id});
    if (!r || r.error) return;
    VUES = r.vues || [];
    dessinerVues();
  },
  // A keystroke in the search: we return to the first page, otherwise
  // searching from page 3 shows nothing although there are results.
  chercher() { PAGE = 0; renderLibBientot(); },

  // Folds or unfolds the filter and sort rows, on phones only.
  // The `aria-expanded` attribute carries the state: that is what a screen
  // reader reads, and also what the CSS uses to tint the button — one single
  // source, not an extra class to keep in step.
  basculerFiltres() {
    const b = $('replier');
    const ouvert = document.body.classList.toggle('filtres-ouverts');
    if (b) b.setAttribute('aria-expanded', ouvert ? 'true' : 'false');
  },
  toggleFavPop(e) {
    if (e) e.stopPropagation();
    $('favpop').classList.toggle('on');
  },
  // A single "Refresh" button: read the server AND the console again. Having
  // five different refreshes forced you to guess which one answered what.
  // "Refresh" used to read only the Switch library: on another platform, or in
  // the "all platforms" view, the button looked like it did nothing. It now
  // re-reads what is REALLY on screen.
  async actualiser() {
    oublierCacheSysteme();                        // this is the gesture that says "read again"
    await this.scan();                            // the server's files
    if (CONN.kind) {
      await this.explore();                       // what is already on the console
      await this.loadNand();                      // what is active in Eden
    }
    await this.setSystem(SYS);                    // the displayed list, whichever it is
    renderLib();
    toast('À jour.', 'ok');
  },

  // Refresh the ENTRIES: titles, summaries, covers. This is a network
  // operation, distinct from re-reading the files.
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
  // One main action, whichever way the transfer goes: the tool deduces from
  // the selection what needs doing, and shows it before starting.
  async appliquer() { return isSwitch() ? this.deploy() : this.sendSystem(); },

  async deploy() {
    if (!dsel2.size) return toast('Coche au moins un jeu.', 'warn');
    if (!CONN.kind) return toast('Connecte d\'abord la console.', 'warn');
    const {envoyer, activer, importer} = deployCibles();

    // recommended configurations available for the selected games
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

    // One dialog: everything about to happen, editable before starting.
    const options = [];
    if (importer.length) options.push({id: 'importer', coche: true,
      libelle: 'Copier vers le serveur les jeux qui n\'y sont pas',
      detail: phrase('%d {fichier|fichiers} depuis la console', importer.length)});
    if (envoyer.length) options.push({id: 'fichiers', coche: true,
      libelle: 'Copier les fichiers de jeu',
      detail: nb(envoyer.length, '{fichier|fichiers}') + ' · ' + fmt(poids)});
    if (activer.length) options.push({id: 'activer', coche: true,
      libelle: 'Activer les mises à jour et DLC dans Eden',
      detail: phrase('%s {élément|éléments} — sans ça ils resteraient inactifs',
                     activer.length)});
    if (configs.length) options.push({id: 'config', coche: false,
      libelle: 'Appliquer les réglages recommandés (EmuReady)',
      detail: phrase('%d {jeu|jeux} :', configs.length) + ' '
              + configs.slice(0, 2).map(c => c.jeu + ' (' + c.note + ')').join(', ')
              + (configs.length > 2 ? '…' : '')
              + t(' — remplace leur configuration actuelle')});
    if (!options.length) return toast('Rien à faire sur ces jeux.', 'warn');

    dialogue({
      titre: phrase('Traiter %d {jeu|jeux}', dsel2.size),
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

  // ---- settings
  // Saves a single setting: impossible to wipe the others by mistake.
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
  // The confirmation lives in the table of contents, which is sticky: at the
  // bottom of a 5 000 px page, nobody saw it. At rest it shows nothing — the
  // intro already says everything saves as you go.
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
    // device_dir is deliberately NOT in this body: it is chosen through the
    // console browser (useDir). Including it here once made it possible to wipe
    // it with an empty value on load, before the config had been read.
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
  // Missing entries are downloaded on demand: the display must never wait on
  // the network, and changing language asks for new ones.
  // Plug & play: one read of the console says what it hosts. The user no longer
  // has to know the expected folder names.
  // from the Settings, go and see a platform's games
  // Clicking a platform DETAILS it; a dedicated button is what takes you to the
  // library. Redirecting by default deprived the user of that platform's own
  // settings.
  // A detected platform leads to ITS settings, further up the page. It used to
  // open a second folder editor: the same setting in two places, so two values
  // that could differ on screen.
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
  // Go back to the folder deduced from the ROM root.
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
  // A full analysis: it goes through the task system, so a progress bar and a
  // detailed log — you see WHAT was searched for, and where.
  async analyseGlobale() {
    const r = await api('/api/console-analyse', {});
    if (r.error) return;
    toast('Analyse lancée.', 'ok');
    await this.poll();
    this.detecterPlateformes(true);
  },

  // Declare a platform missing from the shipped table.
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
    renderSysSelect();                 // the counters depend on it
    if (silencieux) return;
    if (r.plateformes && r.plateformes.length)
      annonce(phrase('%s {plateforme|plateformes} {trouvée|trouvées}.', r.plateformes.length), 'ok');
    else annonce('Aucune plateforme trouvée sous ce dossier.', 'warn');
    this.loadSystems();
  },
  // The audit says what protects the installation AND what does not: both
  // matter, so the successful checks are shown too.
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
    toast(n ? phrase('%d {point|points} à regarder.', n) : t('Rien à signaler.'),
          n ? 'warn' : 'ok');
  },

  // Internal account management: the functions live further up, with the rest
  // of the authentication logic.
  // IGDB: we check BEFORE starting an entry fetch, otherwise the failure only
  // shows up in the middle of a long task.
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

  // Maintenance: each panel answers ONE question, and never acts on its own.
  // Seeing is not deciding.
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

  // Some extensions do not name a platform (.iso: PS2, Wii, Xbox…). Rather
  // than let those files sleep in the drop folder, we ask — once, for every
  // file concerned.
  async classerImports(silencieux) {
    const r = await api('/api/import-suggestions', {}, true);
    const items = (r && r.items) || [];
    if (!items.length) {
      if (!silencieux) toast('Rien à classer : tout a trouvé sa plateforme.', 'ok');
      return;
    }
    ouvrirChoixPlateforme(items);
  },

  // Pick in the file chooser: drag and drop does not suit everyone, and on a
  // phone it does not exist.
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

  // Starting over is destructive for the cache: we say so first.
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

  // Jump to a letter: pagination complicates things, because the letter aimed
  // at is not necessarily on the current page. So we change page BEFORE
  // scrolling, otherwise the click led nowhere.
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
      // A brief visual marker: without it, you cannot tell which of the ten
      // visible cards is the one you aimed at.
      R.classe(cible, 'visee', true);
      setTimeout(() => R.classe(cible, 'visee', false), 1400);
      setTimeout(majAlphabet, 420);
    };
    // The clicked letter acknowledges the hit: without that feedback, a click
    // on an already current letter produces no visible sign and reads as a dead
    // button.
    const bouton = [...document.querySelectorAll('#alphabet .alpha')]
      .find(b => b.textContent === lettre);
    if (bouton) {
      bouton.classList.remove('atteinte');
      void bouton.offsetWidth;          // forces the animation to restart
      bouton.classList.add('atteinte');
      setTimeout(() => bouton.classList.remove('atteinte'), 600);
    }
    ALPHA_VISEE = lettre;
    ALPHA_JUSQUA = Date.now() + 1400;   // long enough for the scroll to settle
    majAlphabet();
    if (page !== PAGE) { PAGE = page; renderLib(); requestAnimationFrame(bouger); }
    else bouger();
  },

  ajouterCompte,
  creerCle, revoquerCle,
  ajouterNotif, supprimerNotif, testerNotif, testerNotifSaisie,
  chargerComptes,

  // Picking the platform whose options are being set.
  choisirPlateformeReglages(key) {
    PF_REGLAGES = key;
    localStorage.setItem('pf-reglages', key);
    // The selector must always show the displayed platform: called from
    // elsewhere (a platform card), it stayed on the old one.
    const sel = $('s-plateforme');
    if (sel && sel.value !== key) sel.value = key;
    majReglagesPlateforme();
  },

  // Checks the provider answers BEFORE enabling SSO: locking yourself out with
  // a mistyped address would be the worst outcome.
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

  // ---- trash + log
  // The trash reads first as one sentence. The detail, often long (40 batches
  // here), stays folded until asked for.
  async loadTrash() {
    // `rep` and not `t`: `t()` is the translation function, and shadowing it
    // here raised "t is not a function" as soon as the trash held a batch — the
    // summary then never showed. Invisible as long as the trash stays empty,
    // which is the case in any test library.
    const rep = await api('/api/trash-list');
    const r = rep.resume || {lots: 0, fichiers: 0, octets: 0, plus_vieux: 0};
    const s = $('trashsum');
    if (s) s.innerHTML = r.lots
      ? '<b>' + r.lots + '</b> ' + t('{lot|lots}') + ' &middot; <b>' + r.fichiers
        + '</b> ' + t('{fichier|fichiers}') + ' &middot; <b>' + fmt(r.octets) + '</b> '
        + t('récupérables')
        + (r.plus_vieux ? ' <span class="mono">'
           + phrase('— le plus ancien a %d {jour|jours}', r.plus_vieux) + '</span>' : '')
      : '<span class="mono">Corbeille vide.</span>';
    const sel = $('s-trashdays');
    if (sel && t.jours != null) sel.value = String(t.jours);
    $('trash').innerHTML = t.items.length
      ? '<div class="card">' + t.items.map(i => '<div class="row"><span class="grow">' +
          esc(i.name) + '</span><span class="mono">' + nb(i.count, '{fichier|fichiers}') + ' · ' +
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
        ? phrase('Les lots de plus de %d {jour|jours} seront supprimés définitivement.', jours)
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
    if (ouvert) this.poll();                     // refresh straight away
  },

  // The "+" button has two roles depending on the state: when something is
  // running, it opens the detail of what is running; otherwise it adds games.
  // That is where the user is already looking, since the ring spins there.
  actionFab() {
    if (activite()) this.basculerTaches();
    else this.toggleDrop();
  },
  async restore(nom) {
    const r = await api('/api/restore', {name: nom});
    if (r && r.message) toast(r.message, 'ok');
    this.scan();
  },
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
  // The log opens as a drawer on the right: it no longer covers the add button
  // or the action bar, and closes with a click on the backdrop.
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
      // A task that finishes has almost always moved, converted or deleted
      // files: what we hold in cache is worth nothing any more.
      oublierCacheSysteme();
      const soucis = (j.log || []).filter(e => e.n === 'error');
      const alertes = (j.log || []).filter(e => e.n === 'warn');
      if (soucis.length) {
        dialogue({
          titre: 'Tâche terminée avec des erreurs',
          niveau: 'error',
          message: phrase('%s {erreur|erreurs} et %s {alerte|alertes}. Le reste s\'est bien '
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
      + phrase('— %d {fichier|fichiers} {incomplet|incomplets} {bloqué|bloqués}', r.broken) + '</span>' : '') + '</span>' +
    '<span class="' + (tight ? 'bad' : '') + '">' +
    (r.free != null ? 'libre : ' + fmt(r.free) + (tight ? ' — insuffisant !' : '') : 'espace inconnu') +
    '</span></div>' + body + '</div>';
}

// ------------------------------------------------------------ first-run journey
// Every step is checked server-side (/api/health): we do not tell the user they
// are missing something they have already done.
let HEALTH = null;

/* ============================================================================
   PREMIER DEMARRAGE
   ----------------------------------------------------------------------------
   A journey, not a checklist. The previous version showed seven diagnostics in
   one block: the user read them all, understood none, and had nothing to do
   about them.

   Here, one step at a time, each with a real action and a status: REQUIRED or
   OPTIONAL. Anything specific to a console — emulator, decryption keys, remote
   folders — is absent: that gets set later, once you know what it is about.
   What matters on the first run is where the games are, who is allowed in, and
   what will fill the covers.
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
        // Choosing the folder from here, rather than pointing at an
        // environment variable: on a NAS, that meant opening a terminal and
        // restarting a container in the middle of the wizard.
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
      // `null`: a step that expects no action can be neither required nor
      // optional — calling it "optional" wrongly suggests there would be
      // something to do there.
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

// ------------------------------------------------- install prompt (a2hs)
// Detects the context automatically: installation is offered ONLY if the page
// is open remotely (console, phone) and not already installed.
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

// When driving from the console or the phone, we remind that the library and
// the actions live on the server, not on the device.
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

// Chrome sometimes offers a real installation: we use it if it turns up.
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault(); INSTALL_EVT = e; renderA2HS();
});
window.addEventListener('appinstalled', () => {
  INSTALL_EVT = null; localStorage.setItem('a2hs-off', '1'); renderA2HS();
  toast('Application installée. Retrouve-la sur ton écran d\'accueil.', 'ok');
});

// ------------------------------------------------------------- drag and drop
// The list comes from the server: it depends on the known platforms AND on
// those the user added by hand, with their own extensions. Freezing it here
// would have refused a ROM the tool does know how to file.
let EXTS_ACCEPTEES = ['.nsz', '.xcz', '.nsp', '.xci', '.zip', '.7z', '.rar'];

// The drop overlay and the "Add games" field announce the SAME list as the one
// actually accepted: a list frozen in the HTML lied as soon as the user added a
// platform.
function majZoneDepot() {
  const t = $('dropexts');
  if (!t) return;
  // An alphabetical list (".3ds .bin .cci…") teaches nothing. What the user
  // wants to know is WHICH CONSOLES are recognised.
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

// Progress is computed on the total VOLUME, not the file count: dropping a
// 12 GB game and a 30 MB patch does not make "50 %" halfway through.
function uploadFiles(files) {
  // The drop adds files to the library: the cache is stale before the transfer
  // has even finished.
  oublierCacheSysteme();
  let list = [...files].filter(f => extensionAcceptee(f.name));
  const rejetes = [...files].length - list.length;
  if (!list.length) {
    return toast(t('Aucun fichier reconnu.') + ' ' +
                 phrase('%s formats acceptés — voir « Ajouter des jeux ».',
                        EXTS_ACCEPTEES.length), 'warn');
  }
  if (rejetes) journal(phrase('%d {fichier|fichiers} {ignoré|ignorés} : type non géré.', rejetes), 'warn');

  // The ceiling is checked HERE, before opening a single connection. The
  // server does it too — it is the authority — but it can only answer after the
  // fact: it then cuts the connection mid-reception, and the browser shows only
  // a "network error" that explains nothing.
  const plafond = TELEVERSEMENT_MAX;
  if (plafond) {
    const trop = list.filter(f => f.size > plafond);
    if (trop.length) {
      trop.forEach(f => journal('Trop volumineux : ' + f.name + ' (' + fmt(f.size)
                                + ', maximum ' + fmt(plafond) + ')', 'error'));
      toast(phrase('%d {fichier|fichiers} dépassent %s.', trop.length)
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
    // No estimate before a real throughput has been observed: an ETA based on
    // the first few milliseconds announces anything at all.
    const secs = (ecoule > 2 && fait > 0)
      ? Math.round((octets - fait) / (fait / ecoule)) : null;
    const reste = texteReste(secs);
    ACT_ENVOI = {
      titre: 'Envoi' + (list.length > 1 ? ' ' + (i) + '/' + list.length : ''),
      pct: pct,
      // The button shows the time left AS A NUMBER: it needs the value, not
      // the sentence already formatted for the panel.
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
      toast(phrase('%d {fichier|fichiers} {déposé|déposés}.', list.length), 'ok');
      // Since dropping is now possible anywhere, the user does not necessarily
      // have the panel in sight: we open it on the fresh list, so the next step
      // is where they are looking.
      app.toggleDrop(true);
      app.reloadImport();
      app.classerImports(true);        // if ambiguous extensions remain
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
// One setting changed = we send THAT setting only. Sending the whole form
// risked overwriting the configuration with empty fields.
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
  's-oidcadmingroupes': ['oidc_admin_groupes', 'text'],
  's-majcheck': ['maj_check', 'bool'],
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

// The real height of the header and of the table of contents: they change with
// the width (the tabs wrap) and in landscape, where the header is no longer
// sticky. Freezing them in the CSS would offset the anchors by one bar.
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
   LA CROIX DIRECTIONNELLE

   Sur une console portable de retrogaming — Anbernic, Retroid, AYN — le pouce
   est sur la croix, pas sur l'ecran. Ces appareils emettent des evenements
   CLAVIER standards : il n'y a donc pas besoin de l'API Gamepad, et s'en
   passer evite de dependre d'un materiel qu'on ne peut pas eprouver ici.

   Deux tiers du chemin etaient deja faits, et il vaut la peine de le dire :
   les cartes portent `tabindex="0"` et `role="button"`, elles repondent donc
   deja a Entree (regle posee en phase 4), et `.gcard:focus-visible` dessine
   deja un anneau lisible. Ce qui manquait, c'etait de passer d'une carte a
   l'autre autrement qu'avec la tabulation.

   Le nombre de COLONNES n'est pas une constante : la grille est un
   `auto-fill`, il depend de la largeur et de la densite choisie. On le lit
   donc dans la geometrie — les cartes de la premiere rangee partagent leur
   bord superieur.
   ------------------------------------------------------------------------- */
function cartesGrille() {
  return [...document.querySelectorAll('#lib .gcard')];
}

function colonnesGrille(cartes) {
  if (cartes.length < 2) return 1;
  const haut = Math.round(cartes[0].getBoundingClientRect().top);
  let n = 1;
  while (n < cartes.length
         && Math.round(cartes[n].getBoundingClientRect().top) === haut) n++;
  return n;
}

document.addEventListener('keydown', ev => {
  const DEPLACE = {ArrowLeft: 1, ArrowRight: 1, ArrowUp: 1, ArrowDown: 1,
                   Home: 1, End: 1};
  if (!DEPLACE[ev.key] || ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const ici = document.activeElement;
  if (!ici || !ici.classList || !ici.classList.contains('gcard')) return;
  const cartes = cartesGrille();
  const i = cartes.indexOf(ici);
  if (i < 0) return;
  const col = colonnesGrille(cartes);
  let cible = i;
  if (ev.key === 'ArrowLeft') cible = i - 1;
  else if (ev.key === 'ArrowRight') cible = i + 1;
  else if (ev.key === 'ArrowUp') cible = i - col;
  else if (ev.key === 'ArrowDown') cible = i + col;
  else if (ev.key === 'Home') cible = 0;
  else if (ev.key === 'End') cible = cartes.length - 1;
  // Une fleche qui sort de la grille ne fait rien plutot que de rebondir :
  // sur une console, le rebond se lit comme un bouton qui n'a pas repondu.
  if (cible < 0 || cible >= cartes.length) return;
  ev.preventDefault();
  cartes[cible].focus();
  // `nearest` : on ne recentre pas la page quand la carte visee est deja
  // visible, sinon chaque appui fait sauter la grille sous les yeux.
  cartes[cible].scrollIntoView({block: 'nearest', inline: 'nearest'});
});

// « / » saute a la recherche — le raccourci qu'attend quiconque a deja utilise
// GitHub. Il est ignore quand on est deja en train d'ecrire quelque part,
// sinon taper une barre oblique dans un chemin deplacerait le curseur.
document.addEventListener('keydown', e => {
  if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
  const ou = document.activeElement;
  if (ou && /^(INPUT|TEXTAREA|SELECT)$/.test(ou.tagName)) return;
  if (ou && ou.isContentEditable) return;
  const champ = $('filter');
  if (!champ || !champ.offsetParent) return;
  e.preventDefault();
  app.tab('jeux');
  champ.focus();
  champ.select();
});
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
  'ajouterNotif', 'appliquerVue', 'basculerFiltres', 'chercher', 'creerCle',
  'effacerFiltres', 'supprimerNotif', 'testerNotif', 'testerNotifSaisie',
  'voirMaj',
  'enregistrerVue', 'installApp', 'journalClear', 'journalCopy',
  'supprimerVue',
  'loadSaves',
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
  chargerVues();                   // les vues enregistrees, servies par le serveur
  chargerMaj();                    // y a-t-il une version plus recente ?
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
