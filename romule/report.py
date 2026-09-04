"""What is wrong with the library, in one place.

The material already existed and nobody could see it. `duplicates.report()` and
`integrity.summary()` each had a route and a panel buried in the settings;
`scan.py` has been flagging orphans, superseded versions and missing updates on
every pass since the beginning, and those flags only showed one card at a time.
Whether the library was in good shape was a question you could only answer by
opening five screens and remembering what each one said.

This assembles, it does not compute. Every number here is read from something
that already knew it — which is why this file is short, and why it must stay
so: the moment it starts deciding what "wrong" means, it becomes a sixth screen
with its own opinion.

Each family carries the ACTION that addresses it, by the name the interface
already uses for that button. A screen that lists problems and leaves you to
find the remedy elsewhere is a screen that gets read once.
"""

from . import duplicates, integrity


def _flagged(files, wanted):
    """The files carrying one of these flags, with the flag's own wording."""
    out = []
    for f in files:
        for name, text in (f.get("flags") or []):
            if name in wanted:
                out.append({"rel": f.get("rel") or f.get("name"), "quoi": text})
                break
    return out


def build(lib, cfg, meta_cache=None, pending=None):
    """The whole report. Never raises: a screen that says nothing is worse than
    a screen that says "this part could not be read"."""
    files = lib.files or []
    familles = []

    def famille(cle, titre, items, action="", detail=""):
        # A family with nothing in it is not shown. A list of "0 problems" is
        # exactly what turns a health screen into wallpaper.
        if items:
            familles.append({"cle": cle, "titre": titre, "nombre": len(items),
                             "action": action, "detail": detail,
                             "exemples": items[:8]})

    famille("incomplets", "Fichiers incomplets",
            _flagged(files, {"broken"}),
            "verify", "Le fichier existe mais son contenu ne tient pas debout.")
    famille("orphelins", "Mises à jour et DLC sans leur jeu",
            _flagged(files, {"orphan"}),
            "", "Le jeu de base manque : ces fichiers sont inutilisables.")
    famille("depassees", "Versions dépassées",
            _flagged(files, {"old", "outdated", "nopatch"}),
            "", "Une version plus récente existe.")
    famille("aconvertir", "À convertir",
            [{"rel": f.get("rel"), "quoi": "NSP/XCI"}
             for f in files if f.get("needs_convert")],
            "convertAll", "Convertir en NSZ libère de la place sans rien perdre.")

    try:
        doubles = duplicates.report(lib, cfg)
    except Exception:
        doubles = {}
    identiques = doubles.get("identiques") or []
    regions = doubles.get("regions") or []
    famille("identiques", "Fichiers en double",
            [{"rel": (x.get("fichiers") or [""])[0], "quoi": "%d copies"
              % len(x.get("fichiers") or [])} for x in identiques],
            "", "Même empreinte, deux emplacements.")
    famille("regions", "Mêmes jeux, plusieurs régions",
            [{"rel": x.get("titre"), "quoi": x.get("plateforme", "")}
             for x in regions],
            "", "Un choix, souvent involontaire.")

    # A game with no entry has no title, no summary and no cover: on the grid it
    # is a file name. That is the most visible defect of all, and the one people
    # least often know how to fix.
    cache = meta_cache or {}
    sans_fiche = [{"rel": f.get("rel"), "quoi": f.get("name")}
                  for f in files
                  if f.get("type") == "BASE" and f.get("tid")
                  and not (cache.get(f["tid"][:13] + "000")
                           or cache.get(f["tid"]))]
    famille("fiches", "Jeux sans fiche", sans_fiche,
            "refreshEntries", "Ni titre officiel, ni résumé, ni jaquette.")

    attente = list(pending or [])
    famille("depot", "En attente dans le dépôt",
            [{"rel": x.get("rel") or x.get("name"), "quoi": x.get("etat", "")}
             for x in attente],
            "doImport", "Déposé mais pas encore rangé.")

    try:
        etat = integrity.summary(files)
    except Exception:
        etat = {}

    return {
        "familles": familles,
        "total": sum(f["nombre"] for f in familles),
        # Coverage is not a family: it is not a problem, it is how much of the
        # library the integrity check has ever looked at. Shown beside the
        # families because "no problem found" means something quite different at
        # 4 % than at 100 %.
        "integrite": {
            "fichiers": etat.get("fichiers", len(files)),
            "couverts": etat.get("couverts", 0),
            "sans_empreinte": etat.get("sans_empreinte", 0),
            "plus_ancienne": etat.get("plus_ancienne"),
        },
        "recuperable": doubles.get("recuperable", 0),
    }
