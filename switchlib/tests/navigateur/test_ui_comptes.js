/* Rend app.js dans un DOM minimal et verifie que la section « comptes »
   se dessine et repond, sans navigateur. */
const fs = require('fs'), vm = require('vm'), path = require('path');
// Les chemins des fichiers statiques sont relatifs a la racine du projet.
process.chdir(path.resolve(__dirname, '..', '..', '..'));

const html = fs.readFileSync('switchlib/static/index.html', 'utf8');
const ids = new Map();
function faux(tag) {
  const el = {
    tagName: tag, children: [], dataset: {}, style: {}, classList: new Set(),
    _txt: '', _html: '', attrs: {}, hidden: false,
    get textContent() { return this._txt; },
    set textContent(v) { this._txt = String(v); },
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); this.children = analyser(v); },
    appendChild(c) { this.children.push(c); return c; },
    insertBefore(c) { if (!this.children.includes(c)) this.children.push(c); return c; },
    remove() {},
    get firstChild() { return this.children[0] || null; },
    get nextSibling() { return null; },
    querySelector(s) { return this.querySelectorAll(s)[0] || null; },
    querySelectorAll(s) {
      const cible = s.replace(/^[.\[]|[\]]$/g, '').split('=')[0];
      return this.children.filter(c =>
        c.classList.has(cible) || c.tagName === cible || (cible in c.dataset));
    },
    addEventListener() {}, focus() {}, click() {},
    setAttribute(k, v) { this.attrs[k] = v; },
  };
  el.classList.add = (...n) => n.forEach(x => el.classList.add_(x));
  el.classList.add_ = x => Set.prototype.add.call(el.classList, x);
  el.classList.contains = x => Set.prototype.has.call(el.classList, x);
  el.classList.remove = (...n) => n.forEach(x => Set.prototype.delete.call(el.classList, x));
  el.classList.toggle = (x, v) => v ? el.classList.add_(x) : el.classList.delete(x);
  Object.defineProperty(el, 'className', {
    set(v) { String(v).split(/\s+/).forEach(x => x && el.classList.add_(x)); },
    get() { return [...el.classList].join(' '); },
  });
  return el;
}
// analyse tres sommaire : recupere classes et data-* des balises du gabarit
function analyser(h) {
  const out = [];
  for (const m of h.matchAll(/<(\w+)([^>]*)>/g)) {
    const el = faux(m[1]);
    const cls = /class="([^"]*)"/.exec(m[2]);
    if (cls) el.className = cls[1];
    for (const d of m[2].matchAll(/data-([\w-]+)="([^"]*)"/g)) el.dataset[d[1]] = d[2];
    out.push(el);
  }
  return out;
}
for (const m of html.matchAll(/\bid="([\w-]+)"/g)) ids.set(m[1], faux('div'));
for (const [k, el] of ids) el.dataset.id = k;

const appels = [];
const ctx = {
  console,
  // La traduction observe les ajouts au DOM : sans cette classe, app.js ne
  // se charge pas du tout dans le faux DOM.
  // app.js ecoute `resize`/`scroll` au niveau global : sans ces fonctions le
  // module ne se charge pas du tout dans le faux DOM.
  addEventListener: () => {},
  removeEventListener: () => {},
  ResizeObserver: function () { this.observe = () => {}; this.disconnect = () => {}; },
  MutationObserver: function (fn) {
    this.observe = () => {};
    this.disconnect = () => {};
    this.takeRecords = () => [];
  },
  NodeFilter: {SHOW_TEXT: 4},
  // Un vrai navigateur expose `matchMedia` en global, pas seulement sur
  // `window` : le theme automatique l'interroge pour savoir si le systeme
  // est en clair. Sans lui, le test exercerait le repli au lieu du vrai
  // chemin.
  matchMedia: () => ({matches: false, addEventListener() {}, addListener() {}}),
  document: {
    getElementById: id => ids.get(id) || null,
    querySelector: () => null, querySelectorAll: () => [],
    createElement: faux, addEventListener() {}, body: faux('body'),
    documentElement: faux('html'),
  },
  window: {addEventListener() {}, navigator: {standalone: false},
           matchMedia: () => ({matches: false, addEventListener() {}, addListener() {}}),
           location: {href: '/', search: ''}},
  location: {href: '/', search: '', reload() {}},
  navigator: {clipboard: {writeText: () => Promise.resolve()}, language: 'fr'},
  localStorage: {getItem: () => null, setItem() {}, removeItem() {}},
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval,
  Date, Math, JSON, Promise,
  fetch: (url, o) => {
    appels.push(String(url).split('?')[0]);
    const vide = {files: [], stats: {}, config: {auth_mode: 'aucun'}, meta: {},
                  nand: [], pending: [], shop: [], items: [], systems: [],
                  langues: [], log: [], running: false, systemes: []};
    const par = {
      '/api/comptes': {comptes: [
        {id: 'aaa', email: 'dino@exemple.fr', nom: 'Dino', photo: true},
        {id: 'bbb', email: 'ami@exemple.fr', nom: 'Ami', photo: false}],
        moi: 'aaa', mdp_min: 12},
    };
    const rep = Object.assign({}, vide, par[String(url).split('?')[0]] || {});
    return Promise.resolve({json: () => Promise.resolve(rep), ok: true, status: 200});
  },
};
ctx.window.R = null; ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('switchlib/static/reactive.js', 'utf8'), ctx);
ctx.R = ctx.window.R;
// `const app = ...` reste dans la portee du script : on l'expose pour le test.
const SUFFIXE = "\n;globalThis.__t = {app, majBlocAuth, config: c => { DATA.config = c; }};";
vm.runInContext(fs.readFileSync('switchlib/static/app.js', 'utf8') + SUFFIXE, ctx);

let ok = 0, ko = 0;
const t = (n, c, d) => c ? (ok++, console.log('      OK   ' + n))
                         : (ko++, console.log('      ECHEC ' + n + '  ' + (d ?? '')));

(async () => {
  t('app.ajouterCompte exposee', typeof ctx.__t.app.ajouterCompte === 'function');
  t('app.chargerComptes exposee', typeof ctx.__t.app.chargerComptes === 'function');

  await ctx.__t.app.chargerComptes();
  t('/api/comptes appelee', appels.includes('/api/comptes'));

  const carte = ids.get('moncompte');
  t('carte « mon compte » remplie', /moncompte/.test(carte.innerHTML), carte.innerHTML.slice(0, 60));
  const av = carte.querySelector('avatar');
  t('photo posee sur l\'avatar', /\/photo\/aaa\?v=/.test(av.style.backgroundImage || ''),
    av.style.backgroundImage);
  // photo, nom, mot de passe, double authentification, deconnexion
  t('5 actions proposees', (carte.innerHTML.match(/data-a=/g) || []).length === 5,
    (carte.innerHTML.match(/data-a=/g) || []).length);
  t('la double authentification est proposee', /data-a="totp"/.test(carte.innerHTML));

  const boite = ids.get('listecomptes');
  t('2 personnes listees', boite.children.length === 2, boite.children.length);

  // bascule du selecteur de mode
  const sel = ids.get('s-authmode');
  sel.value = 'interne';
  ctx.__t.config({auth_mode: 'interne'});
  ctx.__t.majBlocAuth();
  t('bloc interne affiche', ids.get('blocinterne').hidden === false);
  t('bloc SSO masque', ids.get('blocoidc').style.display === 'none');
  sel.value = 'oidc';
  ctx.__t.majBlocAuth();
  t('retour au SSO', ids.get('blocinterne').hidden === true
    && ids.get('blocoidc').style.display === '');

  console.log('   ------------------------------------------------');
  console.log('   ' + ok + ' controles OK, ' + ko + ' echec(s)');
  process.exit(ko ? 1 : 0);
})();
