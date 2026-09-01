/* Charge en tete de page et de facon BLOQUANTE, a dessein : le theme doit
   etre pose avant le premier rendu. Ce code etait un <script> en ligne ;
   il en sort pour que la politique de securite puisse refuser
   `'unsafe-inline'`, ce qu'un seul script en ligne suffisait a empecher. */
/* Le theme est pose AVANT le premier rendu. Le lire depuis app.js, charge en
   fin de page, ferait apparaitre l'interface en sombre puis basculer en clair
   sous les yeux de l'utilisateur a chaque ouverture.
   Ces trois reglages restent locaux a l'appareil : le meme utilisateur veut
   souvent du clair sur la tablette et du sombre sur la console. */
(function () {
  var d = document.documentElement, mag = null;
  try { mag = localStorage; } catch (e) { mag = null; }   /* navigation privee */
  function lu(cle, defaut, permis) {
    var v = mag && mag.getItem(cle);
    return permis.indexOf(v) >= 0 ? v : defaut;
  }
  d.dataset.theme = lu('theme', 'sombre', ['sombre', 'clair', 'auto']);
  d.dataset.carte = lu('carte', '1', ['aucune', '0', '1', '2', '3', '4', '5']);
  d.dataset.mvt   = lu('mvt', 'complet', ['complet', 'reduit', 'aucun']);
})();
