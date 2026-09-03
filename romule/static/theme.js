/* Loaded at the top of the page and BLOCKING, by design: the theme must be set
   before the first render. This code used to be an inline <script>; it moves out
   so the security policy can refuse `'unsafe-inline'`, which a single inline
   script was enough to prevent. */
/* The theme is set BEFORE the first render. Reading it from app.js, loaded at
   the end of the page, would show the interface in dark then switch to light
   before the user's eyes on every opening.
   These three settings stay local to the device: the same user often wants light
   on the tablet and dark on the handheld. */
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
