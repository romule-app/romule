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

console.log('   -- 3. aucun gestionnaire en ligne n\'interpole sans jsq() --');
// Toute valeur inseree dans une chaine JavaScript d'attribut est precedee du
// delimiteur `\'' +`. Ce qui suit doit etre `jsq(`, sans exception.
const motif = /\\'' \+\s*([A-Za-z_$][\w$]*)\s*\(/g;
const fautifs = [];
let m;
while ((m = motif.exec(src)) !== null) {
  if (m[1] === 'jsq') continue;
  fautifs.push(src.slice(0, m.index).split('\n').length + ' : ' + m[1] + '(');
}
// Et la forme sans aucun appel : `\'' + variable +`
const nu = /\\'' \+\s*([A-Za-z_$][\w$.]*)\s*\+/g;
while ((m = nu.exec(src)) !== null) {
  fautifs.push(src.slice(0, m.index).split('\n').length + ' : ' + m[1] + ' (aucun encodage)');
}
t('tous les sites passent par jsq()', fautifs.length === 0, fautifs.join(' | '));

const total = /\\'' \+\s*jsq\(/g;
console.log('      (' + (src.match(total) || []).length + ' sites proteges)');

console.log('      ------------------------------------------------');
console.log('      ' + ok + ' controles OK, ' + ko + ' echec(s)');
process.exit(ko ? 1 : 0);
