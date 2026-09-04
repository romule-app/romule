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
    _ev: {}, offsetWidth: 54, offsetHeight: 54,
    getAttribute(k) { return this.attrs[k]; },
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
    addEventListener(ev, fn) { (this._ev[ev] = this._ev[ev] || []).push(fn); },
    declencher(ev, e) { (this._ev[ev] || []).forEach(f => f(e)); },
    focus() {}, click() {},
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
const ENVOIS = [];
const ctx = {
  console,
  document: {
    getElementById: id => ids.get(id) || null,
    querySelector: () => null, querySelectorAll: () => [],
    createElement: faux, addEventListener() {}, body: faux('body'),
    documentElement: faux('html'),
  },
  requestAnimationFrame: f => f(),
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
  XMLHttpRequest: function () {
    this.upload = {}; this.open = () => {}; this.setRequestHeader = () => {};
    this.send = () => { ENVOIS.push(this); };
  },
  window: {_ev: {},
           addEventListener(ev, fn) { (this._ev[ev] = this._ev[ev] || []).push(fn); },
           declencher(ev, e) { (this._ev[ev] || []).forEach(f => f(e)); },
           navigator: {standalone: false},
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
const SUFFIXE = "\n;globalThis.__t = {app, updateAuthBlock, renderTask, uploadFiles, majFab, config: c => { DATA.config = c; }};";
vm.runInContext(fs.readFileSync('romule/static/app.js', 'utf8') + SUFFIXE, ctx);


let ok = 0, ko = 0;
const t = (n, c, d) => c ? (ok++, console.log('      OK   ' + n))
                         : (ko++, console.log('      FAIL  ' + n + '  ' + (d ?? '')));
const fab = ids.get('fab'), jauge = ids.get('fabjauge');

(async () => {
  console.log('   -- 1. at rest --');
  ctx.__t.renderTask({running: false, log: []});
  t('button not marked as working', !fab.classList.contains('working'));
  t('no title displayed', ids.get('fabtitre').textContent === '');

  console.log('   -- 2. a task with a known total --');
  ctx.__t.renderTask({running: true, label: 'convert_files', done: 3, total: 12,
                       detail: 'jeu.nsz', log: []});
  t('button marked as working', fab.classList.contains('working'));
  t('the task name is translated', ids.get('fabtitre').textContent === 'Conversion',
    ids.get('fabtitre').textContent);
  t('counter on the button', /3\/12/.test(ids.get('fabreste').textContent),
    ids.get('fabreste').textContent);
  t('gauge at 25 %', jauge.style.strokeDasharray === '25 100', jauge.style.strokeDasharray);
  t('not in indeterminate mode', !fab.classList.contains('seeking'));
  t('the ring is measured on the outline', ids.get('fabring').getAttribute('viewBox') === '0 0 54 54',
    ids.get('fabring').getAttribute('viewBox'));

  console.log('   -- 3. unknown total --');
  ctx.__t.renderTask({running: true, label: 'verify_library', done: 5, total: 0, log: []});
  t('indeterminate mode', fab.classList.contains('seeking'));
  t('a short segment turning', jauge.style.strokeDasharray === '18 82', jauge.style.strokeDasharray);
  t('the name is translated', ids.get('fabtitre').textContent === 'Vérification');

  console.log('   -- 4. a task the table does not know --');
  ctx.__t.renderTask({running: true, label: 'tache_jamais_vue', done: 1, total: 2, log: []});
  t('a readable fallback', ids.get('fabtitre').textContent === 'Tâche en cours',
    ids.get('fabtitre').textContent);

  console.log('   -- 5. end of task --');
  ctx.__t.renderTask({running: false, log: []});
  t('the indicator is cleared', !fab.classList.contains('working')
    && ids.get('fabtitre').textContent === '');

  console.log('   -- 6. uploading files --');
  ctx.__t.uploadFiles([{name: 'gros.nsp', size: 9000}, {name: 'petit.nsp', size: 1000},
                       {name: 'notice.txt', size: 10}]);
  t('only the handled types are sent', ENVOIS.length === 1, ENVOIS.length);
  t('the indicator is active during the upload', fab.classList.contains('working'));
  t('the title shows the progress', /Envoi 1\/2/.test(ids.get('fabtitre').textContent),
    ids.get('fabtitre').textContent);
  // 50 % of the FIRST file = 4500 / 10000 bytes in total, so 45 %
  ENVOIS[0].upload.onprogress({lengthComputable: true, loaded: 4500, total: 9000});
  t('progress computed on the volume', jauge.style.strokeDasharray === '45 100',
    jauge.style.strokeDasharray);

  console.log('   -- 7. the upload comes before the server task --');
  ctx.__t.renderTask({running: true, label: 'sync_meta', done: 1, total: 4, log: []});
  t('the upload is what stays displayed', /Envoi/.test(ids.get('fabtitre').textContent),
    ids.get('fabtitre').textContent);

  console.log('   -- 8. the drop overlay --');
  const overlay = ids.get('dropzone');
  const evt = (types) => ({dataTransfer: {types, files: []}, preventDefault() {}});
  ctx.window.declencher('dragenter', evt(['Files']));
  t('overlay shown while dragging files', overlay.classList.contains('on'));
  ctx.window.declencher('dragenter', evt(['Files']));   // hovering a child
  ctx.window.declencher('dragleave', evt(['Files']));
  t('no flicker when moving from one element to another', overlay.classList.contains('on'));
  ctx.window.declencher('dragleave', evt(['Files']));
  t('overlay removed on leaving', !overlay.classList.contains('on'));
  ctx.window.declencher('dragenter', evt(['text/plain']));
  t('dragging text opens nothing', !overlay.classList.contains('on'));

  console.log('   ------------------------------------------------');
  console.log('   ' + ok + ' checks OK, ' + ko + ' failure(s)');
  process.exit(ko ? 1 : 0);
})();
