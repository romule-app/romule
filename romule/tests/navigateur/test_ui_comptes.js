/* Renders app.js in a minimal DOM and checks the "accounts" section draws and
   answers, without a browser. */
const fs = require('fs'), vm = require('vm'), path = require('path');
// The static files' paths are relative to the project's root.
process.chdir(path.resolve(__dirname, '..', '..', '..'));

const html = fs.readFileSync('romule/static/index.html', 'utf8');
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
// a very rough parse: collects the classes and data-* of the template's tags
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
  // The translation observes DOM additions: without this class, app.js does not
  // load at all in the fake DOM.
  // app.js listens for `resize`/`scroll` at the global level: without these
  // functions the module does not load at all in the fake DOM.
  addEventListener: () => {},
  removeEventListener: () => {},
  ResizeObserver: function () { this.observe = () => {}; this.disconnect = () => {}; },
  MutationObserver: function (fn) {
    this.observe = () => {};
    this.disconnect = () => {};
    this.takeRecords = () => [];
  },
  NodeFilter: {SHOW_TEXT: 4},
  // A real browser exposes `matchMedia` globally, not only on `window`: the
  // automatic theme queries it to know whether the system is in light mode.
  // Without it, the test would exercise the fallback instead of the real path.
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
vm.runInContext(fs.readFileSync('romule/static/reactive.js', 'utf8'), ctx);
ctx.R = ctx.window.R;
// `const app = ...` stays within the script's scope: we expose it for the test.
const SUFFIXE = "\n;globalThis.__t = {app, updateAuthBlock, config: c => { DATA.config = c; }};";
vm.runInContext(fs.readFileSync('romule/static/app.js', 'utf8') + SUFFIXE, ctx);

let ok = 0, ko = 0;
const t = (n, c, d) => c ? (ok++, console.log('      OK   ' + n))
                         : (ko++, console.log('      FAIL  ' + n + '  ' + (d ?? '')));

(async () => {
  t('app.addAccount is exposed', typeof ctx.__t.app.addAccount === 'function');
  t('app.loadAccounts is exposed', typeof ctx.__t.app.loadAccounts === 'function');

  await ctx.__t.app.loadAccounts();
  t('/api/comptes is called', appels.includes('/api/comptes'));

  const carte = ids.get('moncompte');
  t('the "my account" card is filled', /moncompte/.test(carte.innerHTML), carte.innerHTML.slice(0, 60));
  const av = carte.querySelector('avatar');
  t('the photo is set on the avatar', /\/photo\/aaa\?v=/.test(av.style.backgroundImage || ''),
    av.style.backgroundImage);
  // photo, nom, mot de passe, double authentification, deconnexion
  t('5 actions offered', (carte.innerHTML.match(/data-a=/g) || []).length === 5,
    (carte.innerHTML.match(/data-a=/g) || []).length);
  t('two-factor authentication is offered', /data-a="totp"/.test(carte.innerHTML));

  const boite = ids.get('listecomptes');
  t('2 people listed', boite.children.length === 2, boite.children.length);

  // switching the mode selector
  const sel = ids.get('s-authmode');
  sel.value = 'interne';
  ctx.__t.config({auth_mode: 'interne'});
  ctx.__t.updateAuthBlock();
  t('the internal block is shown', ids.get('blocinterne').hidden === false);
  t('the SSO block is hidden', ids.get('blocoidc').style.display === 'none');
  sel.value = 'oidc';
  ctx.__t.updateAuthBlock();
  t('back to SSO', ids.get('blocinterne').hidden === true
    && ids.get('blocoidc').style.display === '');

  console.log('   ------------------------------------------------');
  console.log('   ' + ok + ' checks OK, ' + ko + ' failure(s)');
  process.exit(ko ? 1 : 0);
})();
