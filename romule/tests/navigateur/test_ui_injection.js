/* A value that enters a JavaScript string inside a handler attribute goes
   through two parsers. `esc()` covers only one of them.

   The hole: `esc()` turns the apostrophe into `&#39;`, but the HTML parser
   restores it BEFORE the JavaScript engine compiles the handler. The string
   closes, and the rest of the value becomes code. Since a card's key is the
   file's PATH, a name like `x',alert(1),'.gba` was enough — and it is obtained
   by simply dropping a file.

   Three things are checked here:
     1. `jsq()` renders the value as it stands, never executing the injection;
     2. `esc()` alone did execute it — the hole was real, not theoretical;
     3. NO inline handler in the file interpolates without `jsq()` any more.

   Point 3 is the most useful: it holds for today's call sites as much as for the
   one someone adds tomorrow. */
const fs = require('fs'), path = require('path');
const RACINE = path.resolve(__dirname, '..', '..', '..');
const CHEMIN = path.join(RACINE, 'romule', 'static', 'app.js');
const src = fs.readFileSync(CHEMIN, 'utf8');

let ok = 0, ko = 0;
function t(nom, cond, detail) {
  if (cond) { ok++; console.log('      OK   ' + nom); }
  else { ko++; console.log('      FAIL  ' + nom + '   ' + (detail || '')); }
}

// ---- we evaluate the REAL definitions from the shipped file
const lignes = src.split('\n');
const debut = lignes.findIndex(l => l.startsWith('const esc = s =>'));
const fin = lignes.findIndex((l, i) => i > debut && l.includes('u2029/g'));
if (debut < 0 || fin < 0) {
  console.log('      FAIL  esc/jsq definitions not found in app.js');
  process.exit(1);
}
const [esc, jsq] = new Function(
  lignes.slice(debut, fin + 1).join('\n') + '\nreturn [esc, jsq];')();

// The HTML parser decodes an attribute value's entities before the JavaScript
// engine reads the handler. We redo that decoding.
const decodeHTML = s => s
  .replace(/&#39;/g, "'").replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

console.log('   -- 1. the value comes back intact, and nothing runs --');
const cas = [
  "x',alert(1),'.gba",
  "');alerte();//",
  'normal.gba',
  'guillemet"double.gba',
  'anti\\slash.gba',
  '<script>x<\/script>.gba',
  'deja&#39;encode.gba',
  'retour\nligne.gba',
  'back`tick${1}.gba',
  "/chemin/avec'apostrophe/jeu.nsp",
  ' separateur.gba',
];
for (const v of cas) {
  let recu = null, injecte = false;
  const source = decodeHTML("app.cardClick(event,'" + jsq(v) + "')");
  try {
    new Function('app', 'event', 'alerte', source)(
      {cardClick: (e, k) => { recu = k; }}, {}, () => { injecte = true; });
  } catch (e) { recu = 'ERREUR: ' + e.message; }
  t(JSON.stringify(v), recu === v && !injecte,
    'recu ' + JSON.stringify(recu) + (injecte ? ' ET code injecte execute' : ''));
}

console.log('   -- 2. the old encoding really was pierced --');
let execute = false;
try {
  new Function('app', 'event', 'alerte',
    decodeHTML("app.cardClick(event,'" + esc("x',alerte(),'.gba") + "')"))(
    {cardClick: () => {}}, {}, () => { execute = true; });
} catch (e) { /* a syntax error would already prove the string was escaped */ }
t('esc() alone ran the injected code', execute,
  'si ce controle echoue, le scenario a change et la regle est a revoir');

console.log('   -- 3. does the detector see what it claims to see? --');
// A rule that announces an invariant without anyone having checked that it
// DETECTS something is worth nothing. This test's first version required a space
// before the `+`: it let through a call site where the line was broken right
// after the literal, with the `+` opening the next one. So the detector is put
// to the test before being applied.
function fautifs(texte) {
  const out = [];
  let m;
  // A value entering an attribute's JavaScript string is preceded by the `\''`
  // delimiter then by a concatenation. Any whitespace can surround the `+`, a
  // line break included.
  const appel = /\\''\s*\+\s*([A-Za-z_$][\w$]*)\s*\(/g;
  while ((m = appel.exec(texte)) !== null) {
    if (m[1] === 'jsq') continue;
    out.push(texte.slice(0, m.index).split('\n').length + ' : ' + m[1] + '(');
  }
  // And the form with no encoding at all: `\'' + variable +`
  const nu = /\\''\s*\+\s*([A-Za-z_$][\w$.]*)\s*\+/g;
  while ((m = nu.exec(texte)) !== null) {
    out.push(texte.slice(0, m.index).split('\n').length + ' : ' + m[1] +
             ' (aucun encodage)');
  }
  return out;
}

const epreuves = [
  ["meme ligne, non protege",
   "'<b onclick=\"f(\\'' + esc(v) + '\\')\">'", true],
  ["ligne coupee AVANT le +, non protege",
   "'<b onclick=\"f(\\''\n  + esc(v) + '\\')\">'", true],
  ["ligne coupee APRES le +, non protege",
   "'<b onclick=\"f(\\'' +\n  esc(v) + '\\')\">'", true],
  ["aucun encodage du tout",
   "'<b onclick=\"f(\\'' + v + '\\')\">'", true],
  ["deuxieme argument non protege",
   "'<b onclick=\"f(\\'' + jsq(a) + '\\',\\'' + esc(b) + '\\')\">'", true],
  ["meme ligne, protege",
   "'<b onclick=\"f(\\'' + jsq(v) + '\\')\">'", false],
  ["ligne coupee, protege",
   "'<b onclick=\"f(\\''\n  + jsq(v) + '\\')\">'", false],
  ["hors gestionnaire, sans rapport",
   "const s = 'a' + esc(v) + 'b';", false],
];
for (const [nom, extrait, attendu] of epreuves) {
  const vu = fautifs(extrait).length > 0;
  t(nom + (attendu ? ' -> detected' : ' -> ignored'), vu === attendu,
    'detecte=' + vu);
}

console.log('   -- 4. and the shipped file honours it --');
const restants = fautifs(src);
t('every call site goes through jsq()', restants.length === 0, restants.join(' | '));
const total = /\\''\s*\+\s*jsq\(/g;
const compte = (src.match(total) || []).length;
console.log('      (' + compte + ' call site(s) — 0 is the expected result since'
            + ' phase 4 ; jsq() reste defini comme garde-fou)');

console.log('   -- 4bis. no inline handler left --');
// Phase 4 removed the 153 `on*=` attributes. So the detector above has become
// meaningless: it looks for a shape that no longer exists. We keep it — it will
// become useful again the day someone reintroduces a handler — but the invariant
// that REALLY protects the file is now stronger: there is no handler attribute
// at all.
//
// That invariant is what lets the security policy refuse `'unsafe-inline'`. The
// first `onclick` reintroduced would make every button in the interface inert,
// in silence.
function enLigne(texte) {
  const out = [];
  texte.split('\n').forEach((l, i) => {
    // Comment lines quote some as examples: those are words, not code. The
    // splitting is deliberately crude — a badly detected comment makes a noisy
    // false positive, never a silent hole.
    const nu = l.trim();
    if (nu.startsWith('//') || nu.startsWith('*') || nu.startsWith('/*')) return;
    const m = nu.match(/\son[a-z]+\s*=\s*["']/);
    if (m) out.push((i + 1) + ' :' + m[0]);
  });
  return out;
}
const epreuvesEnLigne = [
  ['a generated onclick -> detected', "  x = '<b onclick=\"f()\">';", true],
  ['a generated onchange -> detected', "  x = '<i onchange=\"g()\">';", true],
  ['the same in a comment -> ignored', "  // example: onclick=\"f()\"", false],
  ['a data-act -> ignored', "  x = '<b data-act=\"f\">';", false],
];
for (const [nom, extrait, attendu] of epreuvesEnLigne)
  t(nom, (enLigne(extrait).length > 0) === attendu);

const html = fs.readFileSync(
  path.join(RACINE, 'romule', 'static', 'index.html'), 'utf8');
t('app.js generates no inline handler',
  enLigne(src).length === 0, enLigne(src).join(' | '));
t('index.html carries none either',
  enLigne(html).length === 0, enLigne(html).join(' | '));

console.log('   -- 4ter. the values entering a data-* are escaped --');
// The value has left the JavaScript string for an attribute value: ONE parser
// now reads it, and `esc()` is enough — provided it is there. Without it, a file
// name holding a double quote would escape the attribute and could open
// another.
function sansEsc(texte) {
  const out = [];
  let m;
  const re = /data-(?:act|arg\d?)="'\s*\+\s*([A-Za-z_$][\w$]*)\s*\(/g;
  while ((m = re.exec(texte)) !== null)
    if (m[1] !== 'esc')
      out.push(texte.slice(0, m.index).split('\n').length + ' : ' + m[1] + '(');
  const nu = /data-(?:act|arg\d?)="'\s*\+\s*([A-Za-z_$][\w$.]*)\s*\+/g;
  while ((m = nu.exec(texte)) !== null)
    out.push(texte.slice(0, m.index).split('\n').length + ' : ' + m[1] +
             ' (aucun encodage)');
  return out;
}
const epreuvesEsc = [
  ['an unescaped data-arg -> detected',
   "x = '<b data-arg=\"' + jsq(v) + '\">';", true],
  ['a bare data-arg -> detected', "x = '<b data-arg=\"' + v + '\">';", true],
  ['an escaped data-arg -> ignored', "x = '<b data-arg=\"' + esc(v) + '\">';", false],
  ['an escaped data-arg2 -> ignored', "x = '<b data-arg2=\"' + esc(v) + '\">';", false],
];
for (const [nom, extrait, attendu] of epreuvesEsc)
  t(nom, (sansEsc(extrait).length > 0) === attendu);
const nonEch = sansEsc(src);
t('every interpolated value goes through esc()',
  nonEch.length === 0, nonEch.join(' | '));
console.log('      (' + (src.match(/data-(?:act|arg\d?)="'\s*\+\s*esc\(/g) || []).length
            + ' valeurs echappees)');

console.log('   -- 5. nothing shadows the translation function --');
// `t()` translates. A local variable named `t` shadows it throughout the scope,
// and the call becomes "t is not a function" — on the first render only, so a
// broken startup and nothing at all afterwards. It happened: `const t = $('tri')`
// in `renderToolbar`, and the screen stayed empty.
//
// Twelve functions declare a local `t`. None of them may call `t(`.
function masquages(texte) {
  const out = [];
  const decl = /\b(?:const|let|var)\s+t\s*=/g;
  let m;
  while ((m = decl.exec(texte)) !== null) {
    // We follow the braces from the declaration: when the depth goes below
    // zero, we have left the block where the shadowing applies.
    let prof = 0;
    for (let i = m.index; i < texte.length; i++) {
      const c = texte[i];
      if (c === '{') prof++;
      else if (c === '}') { if (prof === 0) break; prof--; }
      else if (c === 't' && /[^\w$.]/.test(texte[i - 1] || ' ')
               && texte.slice(i).match(/^t\s*\(/)) {
        out.push(texte.slice(0, i).split('\n').length);
        break;
      }
    }
  }
  return out;
}

// The detector is put to the test before being applied, as in block 3.
t('it sees a t() in a scope where t is shadowed',
  masquages("function f(){ const t = x; return t('a'); }").length === 1);
t("it ignores a t() outside the scope",
  masquages("function f(){ const t = x; }\nfunction g(){ return t('a'); }").length === 0);
t('it ignores a scope with no call',
  masquages("function f(){ const t = x; return t.value; }").length === 0);

const masques = masquages(src);
t('no function shadows t() then calls it', masques.length === 0,
  'lines: ' + masques.join(', '));

console.log('   -- 6. the task labels match on the client and the server --');
// This file is called "injection" and it has become the guardian of app.js's
// SOURCE INVARIANTS: no inline handler, `esc()` on interpolated values, no
// shadowing of `t()`. Here is one more.
//
// `TACHES_FICHES` holds Python FUNCTION names: `JobRunner.start()` sets
// `fn.__name__` as the label, and the client compares that string to know
// whether an entry search is running. Nothing links the two files. Renaming
// `actions.sync_meta` would break the "Recherche des infos…" banner -- anglais:ok,
// a quoted interface string -- in silence,
// and in BOTH directions: either it would never show again, or it would never
// clear.
const blocTaches = (src.match(/const TACHES_FICHES = \[([^\]]*)\]/) || [])[1];
t('app.js declares TACHES_FICHES', !!blocTaches, 'not found');
const attendus = blocTaches
  ? [...blocTaches.matchAll(/'([^']+)'/g)].map(m => m[1]) : [];

const serveur = fs.readFileSync(path.join(RACINE, 'romule', 'server.py'), 'utf8');
const route = serveur.match(
  /"\/api\/meta-sync":\s*\n\s*self\._job\(actions\.(\w+)/);
const appele = route ? route[1] : null;
t('the /api/meta-sync route does start a task', !!appele,
  'pattern not found in server.py');
t("the server's label appears in the client's list",
  !!appele && attendus.includes(appele),
  'serveur=' + appele + '  client=' + JSON.stringify(attendus));

// And the function must exist, otherwise the match proves nothing.
const actions = fs.readFileSync(path.join(RACINE, 'romule', 'actions.py'), 'utf8');
t('the function exists in actions.py',
  !!appele && new RegExp('^def ' + appele + '\\(', 'm').test(actions), appele);

console.log('   -- 7. setSystem does not empty before it can refill --');
// The "jump" when switching platform came from there: the old version emptied
// `SGAMES`, `SCONSOLE` and `SALL` THEN waited for the network. In between, the
// grid was empty, the page scrolled up, then everything came back.
//
// This check lives HERE, on the source, and not in a browser test — three
// versions of the runtime measurement (height per frame, number of cards, with
// emulated latency then a forced delay) stayed GREEN on the broken code. A check
// nobody has ever seen fail proves nothing. The rule, on the other hand, is
// clear and readable: no assignment of an empty list before the first `await`.
function videAvantAttente(texte) {
  const d = texte.indexOf('async setSystem(key)');
  if (d < 0) return ['setSystem introuvable'];
  const attente = texte.indexOf('await', d);
  if (attente < 0) return ['no await in setSystem'];
  const tete = texte.slice(d, attente);
  const out = [];
  for (const nom of ['SGAMES', 'SCONSOLE', 'SCONSOLE_PATHS', 'SALL']) {
    const re = new RegExp('\\b' + nom + '\\s*=\\s*\\[\\s*\\]');
    if (re.test(tete)) out.push(nom);
  }
  return out;
}
const epreuvesVide = [
  ['a list emptied before the await -> detected',
   "async setSystem(key){ SGAMES = []; const r = await api(); }", true],
  ['emptied AFTER the await -> ignored',
   "async setSystem(key){ const r = await api(); SGAMES = []; }", false],
  ['no assignment -> ignored',
   "async setSystem(key){ const r = await api(); appliquer(r); }", false],
];
for (const [nom, extrait, attendu] of epreuvesVide)
  t(nom, (videAvantAttente(extrait).length > 0) === attendu);
const vides = videAvantAttente(src);
t('setSystem empties no list before its first await',
  vides.length === 0, vides.join(', '));

console.log('   -- 8. the dialog buttons carry the right callback --');
// `dialogue()` calls `actions[i].faire(champs)`. Writing `action:` instead of
// `faire:` produces a button that shows, is clicked, and DOES NOTHING — with no
// error, no trace. Three call sites were in that state, among them the "Copier"
// of an API key, which cannot be shown again afterwards.
//
// `test_gestes.py` could not see it: the button IS reachable, it does have a
// handler. It is what the handler calls that does not exist.
function rappelsFautifs(texte) {
  const out = [];
  // An action object is recognised by `libelle:`; we look at what follows it
  // until the end of the object.
  const re = /libelle:\s*[^,]+,([^}]*)\}/g;
  let m;
  while ((m = re.exec(texte)) !== null)
    if (/\baction\s*:/.test(m[1]) && !/\bfaire\s*:/.test(m[1]))
      out.push(texte.slice(0, m.index).split('\n').length);
  return out;
}
const epreuvesRappel = [
  ['action: instead of faire: -> detected',
   "actions: [{libelle: 'X', principal: true, action: () => f()}]", true],
  ['faire: -> ignored',
   "actions: [{libelle: 'X', principal: true, faire: () => f()}]", false],
  ['a label with no callback -> ignored', "actions: [{libelle: 'X'}]", false],
];
for (const [nom, extrait, attendu] of epreuvesRappel)
  t(nom, (rappelsFautifs(extrait).length > 0) === attendu);
const fautifsRappel = rappelsFautifs(src);
t('no dialog button uses `action:`',
  fautifsRappel.length === 0, 'lignes : ' + fautifsRappel.join(', '));

console.log('      ------------------------------------------------');
console.log('      ' + ok + ' checks OK, ' + ko + ' failure(s)');
process.exit(ko ? 1 : 0);
