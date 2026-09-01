/* Une valeur qui entre dans une chaine JavaScript a l'interieur d'un attribut
   de gestionnaire traverse deux analyseurs. `esc()` n'en couvre qu'un.

   Le trou : `esc()` transforme l'apostrophe en `&#39;`, mais l'analyseur HTML
   la restitue AVANT que le moteur JavaScript ne compile le gestionnaire. La
   chaine se referme, et la suite de la valeur devient du code. La cle d'une
   carte etant le CHEMIN du fichier, un nom comme `x',alert(1),'.gba` suffisait
   — et il s'obtient par un simple depot de fichier.

   Trois choses sont verifiees ici :
     1. `jsq()` rend la valeur telle quelle, sans jamais executer l'injection ;
     2. `esc()` seul, lui, l'executait — la faille etait reelle, pas theorique ;
     3. AUCUN gestionnaire en ligne du fichier n'interpole plus sans `jsq()`.

   Le point 3 est le plus utile : il vaut pour les sites d'aujourd'hui comme
   pour celui que quelqu'un ajoutera demain. */
const fs = require('fs'), path = require('path');
const RACINE = path.resolve(__dirname, '..', '..', '..');
const CHEMIN = path.join(RACINE, 'romule', 'static', 'app.js');
const src = fs.readFileSync(CHEMIN, 'utf8');

let ok = 0, ko = 0;
function t(nom, cond, detail) {
  if (cond) { ok++; console.log('      OK   ' + nom); }
  else { ko++; console.log('      ECHEC ' + nom + '   ' + (detail || '')); }
}

// ---- on evalue les definitions REELLES du fichier livre
const lignes = src.split('\n');
const debut = lignes.findIndex(l => l.startsWith('const esc = s =>'));
const fin = lignes.findIndex((l, i) => i > debut && l.includes('u2029/g'));
if (debut < 0 || fin < 0) {
  console.log('      ECHEC definitions de esc/jsq introuvables dans app.js');
  process.exit(1);
}
const [esc, jsq] = new Function(
  lignes.slice(debut, fin + 1).join('\n') + '\nreturn [esc, jsq];')();

// L'analyseur HTML decode les entites d'une valeur d'attribut avant que le
// moteur JavaScript ne lise le gestionnaire. On refait ce decodage.
const decodeHTML = s => s
  .replace(/&#39;/g, "'").replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

console.log('   -- 1. la valeur ressort intacte, et rien ne s\'execute --');
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

console.log('   -- 2. l\'ancien encodage etait bien perce --');
let execute = false;
try {
  new Function('app', 'event', 'alerte',
    decodeHTML("app.cardClick(event,'" + esc("x',alerte(),'.gba") + "')"))(
    {cardClick: () => {}}, {}, () => { execute = true; });
} catch (e) { /* une erreur de syntaxe prouverait deja la sortie de la chaine */ }
t('esc() seul executait le code injecte', execute,
  'si ce controle echoue, le scenario a change et la regle est a revoir');

console.log('   -- 3. le detecteur voit-il ce qu\'il pretend voir ? --');
// Une regle qui annonce un invariant sans qu'on ait verifie qu'elle DETECTE
// quelque chose ne vaut rien. La premiere version de ce test exigeait une
// espace avant le `+` : elle a laissse passer un site ou la ligne etait coupee
// juste apres le litteral, et le `+` ouvrait la ligne suivante. Le detecteur
// est donc mis a l'epreuve avant d'etre applique.
function fautifs(texte) {
  const out = [];
  let m;
  // Une valeur entrant dans une chaine JavaScript d'attribut est precedee du
  // delimiteur `\''` puis d'une concatenation. N'importe quelle blancheur peut
  // entourer le `+`, saut de ligne compris.
  const appel = /\\''\s*\+\s*([A-Za-z_$][\w$]*)\s*\(/g;
  while ((m = appel.exec(texte)) !== null) {
    if (m[1] === 'jsq') continue;
    out.push(texte.slice(0, m.index).split('\n').length + ' : ' + m[1] + '(');
  }
  // Et la forme sans le moindre encodage : `\'' + variable +`
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
  t(nom + (attendu ? ' -> detecte' : ' -> ignore'), vu === attendu,
    'detecte=' + vu);
}

console.log('   -- 4. et le fichier livre le respecte --');
const restants = fautifs(src);
t('tous les sites passent par jsq()', restants.length === 0, restants.join(' | '));
const total = /\\''\s*\+\s*jsq\(/g;
const compte = (src.match(total) || []).length;
console.log('      (' + compte + ' site(s) — 0 est le resultat attendu depuis la'
            + ' phase 4 ; jsq() reste defini comme garde-fou)');

console.log('   -- 4bis. plus aucun gestionnaire en ligne --');
// La phase 4 a supprime les 153 attributs `on*=`. Le detecteur ci-dessus est
// donc devenu vide de sens : il cherche une forme qui n'existe plus. On le
// garde — il redeviendra utile le jour ou quelqu'un reintroduira un
// gestionnaire — mais l'invariant qui protege VRAIMENT le fichier est
// maintenant plus fort : il n'y a pas d'attribut de gestionnaire du tout.
//
// C'est cet invariant qui permet a la politique de securite de refuser
// `'unsafe-inline'`. Le premier `onclick` reintroduit rendrait tous les
// boutons de l'interface inertes, en silence.
function enLigne(texte) {
  const out = [];
  texte.split('\n').forEach((l, i) => {
    // Les lignes de commentaire en citent en exemple : ce sont des mots, pas
    // du code. Le decoupage est grossier a dessein — un commentaire mal
    // detecte ferait un faux positif bruyant, jamais un trou silencieux.
    const nu = l.trim();
    if (nu.startsWith('//') || nu.startsWith('*') || nu.startsWith('/*')) return;
    const m = nu.match(/\son[a-z]+\s*=\s*["']/);
    if (m) out.push((i + 1) + ' :' + m[0]);
  });
  return out;
}
const epreuvesEnLigne = [
  ['un onclick genere -> detecte', "  x = '<b onclick=\"f()\">';", true],
  ['un onchange genere -> detecte', "  x = '<i onchange=\"g()\">';", true],
  ['le meme en commentaire -> ignore', "  // exemple : onclick=\"f()\"", false],
  ['un data-act -> ignore', "  x = '<b data-act=\"f\">';", false],
];
for (const [nom, extrait, attendu] of epreuvesEnLigne)
  t(nom, (enLigne(extrait).length > 0) === attendu);

const html = fs.readFileSync(
  path.join(RACINE, 'romule', 'static', 'index.html'), 'utf8');
t('app.js ne genere aucun gestionnaire en ligne',
  enLigne(src).length === 0, enLigne(src).join(' | '));
t('index.html n\'en porte aucun',
  enLigne(html).length === 0, enLigne(html).join(' | '));

console.log('   -- 4ter. les valeurs entrant dans un data-* sont echappees --');
// La valeur a quitte la chaine JavaScript pour une valeur d'attribut : un
// SEUL analyseur la lit desormais, et `esc()` suffit — a condition qu'il soit
// la. Sans lui, un nom de fichier contenant un guillemet double sortirait de
// l'attribut et pourrait en ouvrir un autre.
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
  ['un data-arg non echappe -> detecte',
   "x = '<b data-arg=\"' + jsq(v) + '\">';", true],
  ['un data-arg nu -> detecte', "x = '<b data-arg=\"' + v + '\">';", true],
  ['un data-arg echappe -> ignore', "x = '<b data-arg=\"' + esc(v) + '\">';", false],
  ['un data-arg2 echappe -> ignore', "x = '<b data-arg2=\"' + esc(v) + '\">';", false],
];
for (const [nom, extrait, attendu] of epreuvesEsc)
  t(nom, (sansEsc(extrait).length > 0) === attendu);
const nonEch = sansEsc(src);
t('toutes les valeurs interpolees passent par esc()',
  nonEch.length === 0, nonEch.join(' | '));
console.log('      (' + (src.match(/data-(?:act|arg\d?)="'\s*\+\s*esc\(/g) || []).length
            + ' valeurs echappees)');

console.log('   -- 5. rien ne masque la fonction de traduction --');
// `t()` traduit. Une variable locale nommee `t` la masque dans toute la
// portee, et l'appel devient « t is not a function » — au premier rendu
// seulement, donc un demarrage casse et rien du tout ensuite. C'est arrive :
// `const t = $('tri')` dans `renderToolbar`, et l'ecran restait vide.
//
// Douze fonctions declarent un `t` local. Aucune ne doit appeler `t(`.
function masquages(texte) {
  const out = [];
  const decl = /\b(?:const|let|var)\s+t\s*=/g;
  let m;
  while ((m = decl.exec(texte)) !== null) {
    // On suit les accolades depuis la declaration : quand la profondeur passe
    // sous zero, on a quitte le bloc ou le masquage s'applique.
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

// Le detecteur est mis a l'epreuve avant d'etre applique, comme le bloc 3.
t('il voit un t() dans une portee ou t est masque',
  masquages("function f(){ const t = x; return t('a'); }").length === 1);
t("il ignore un t() hors de la portee",
  masquages("function f(){ const t = x; }\nfunction g(){ return t('a'); }").length === 0);
t('il ignore une portee sans appel',
  masquages("function f(){ const t = x; return t.value; }").length === 0);

const masques = masquages(src);
t('aucune fonction ne masque t() puis l\'appelle', masques.length === 0,
  'lignes : ' + masques.join(', '));

console.log('      ------------------------------------------------');
console.log('      ' + ok + ' controles OK, ' + ko + ' echec(s)');
process.exit(ko ? 1 : 0);
