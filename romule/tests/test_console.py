"""The terminal log: what comes out, and above all what does not.

A logging style is judged on BOTH its edges. That it shows what it is asked for
is the easy half; that it keeps quiet about the rest is what makes a log
readable. Every check here verifies both.
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

ICI = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("ROMULE_ROOT", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(ICI)))

ok = fail = 0


def t(nom, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("      OK   %s" % nom)
    else:
        fail += 1
        print("      ECHEC %s  %s" % (nom, detail))


def sortie(style, faire, no_color="1"):
    """What `faire()` writes to standard output, under this style."""
    from romule import console
    avant = dict(os.environ)
    os.environ["ROMULE_LOG"] = style
    if no_color is None:
        os.environ.pop("NO_COLOR", None)
    else:
        os.environ["NO_COLOR"] = no_color
    console.relire()
    tampon = io.StringIO()
    try:
        with redirect_stdout(tampon):
            faire(console)
    finally:
        os.environ.clear()
        os.environ.update(avant)
        console.relire()
    return tampon.getvalue()


def main():
    from romule import console

    tout = lambda c: [c.evenement(n, n) for n in console.NIVEAUX]  # noqa: E731

    # --- the thresholds, in both directions -----------------------------
    s = sortie("quiet", tout)
    t("quiet ne montre que les erreurs",
      "error" in s and "warn" not in s and "info" not in s, repr(s))

    s = sortie("normal", tout)
    t("normal montre warn et error", "warn" in s and "error" in s, repr(s))
    t("normal tait info et debug",
      "info" not in s and "debug" not in s, repr(s))

    s = sortie("verbose", tout)
    t("verbose montre info", "info" in s, repr(s))
    # The point that matters: the interface polls /api/job in a loop and those
    # requests are logged at `debug`. A verbose level that showed them would
    # drown what you came to read.
    t("verbose tait DEBUG — sinon les requetes noient les taches",
      "debug" not in s, repr(s))

    s = sortie("debug", tout)
    t("debug montre tout", all(n in s for n in console.NIVEAUX), repr(s))

    # --- the debug style carries what it takes to place a line -----------
    s = sortie("debug", lambda c: c.evenement("essai", "info", "moncar"))
    t("debug nomme le module", "moncar" in s, repr(s))
    import re as _re
    # "12.34s": the service's age since it started. Written as it stood, the
    # check passed on any string holding an "s".
    t("debug donne l'age du service",
      bool(_re.search(r"\d+\.\d\ds", s)), repr(s))
    t("debug nomme le fil d'execution",
      "MainThread" in s, repr(s))
    s2 = sortie("verbose", lambda c: c.evenement("essai", "info", "moncar"))
    t("verbose ne porte PAS le module", "moncar" not in s2, repr(s2))

    # --- json ------------------------------------------------------------
    s = sortie("json", lambda c: c.evenement("un message", "warn", "mod", n=3))
    try:
        d = json.loads(s.strip())
    except ValueError:
        d = {}
    t("json rend une ligne analysable", bool(d), repr(s))
    t("json porte niveau, message, module et champs",
      d.get("niveau") == "warn" and d.get("message") == "un message"
      and d.get("module") == "mod" and d.get("n") == 3, d)
    t("json n'ecrit aucune couleur", "\033" not in s, repr(s))

    # --- the banner -------------------------------------------------------
    faits = [("Version", "0.3.0"), ("Vide", ""), ("Ludotheque", "/jeux")]
    s = sortie("normal", lambda c: c.banniere(faits))
    t("le bandeau nomme le service", "ROMULE" in s or "██" in s, repr(s[:80]))
    t("le bandeau montre les faits renseignes",
      "0.3.0" in s and "/jeux" in s, repr(s))
    # A "Console:" line followed by nothing teaches less than its absence.
    t("le bandeau tait les faits vides", "Vide" not in s, repr(s))
    t("quiet n'affiche aucun bandeau", sortie("quiet", lambda c: c.banniere(faits)) == "")
    s = sortie("json", lambda c: c.banniere(faits))
    t("en json le bandeau devient un evenement",
      json.loads(s.strip()).get("message") == "demarrage", repr(s))

    # --- la couleur --------------------------------------------------------
    s = sortie("normal", lambda c: c.evenement("x", "error"), no_color="1")
    t("NO_COLOR eteint la couleur", "\033" not in s, repr(s))
    # Outside a terminal, colour would fill a file with escape sequences.
    # `redirect_stdout` into a StringIO is precisely that case.
    s = sortie("normal", lambda c: c.evenement("x", "error"), no_color=None)
    t("hors terminal, pas de couleur non plus", "\033" not in s, repr(s))

    # --- never kill the service --------------------------------------------
    avant = dict(os.environ)
    os.environ["ROMULE_LOG"] = "debug"
    console.relire()
    vrai = sys.stdout
    try:
        ferme = io.StringIO()
        ferme.close()
        sys.stdout = ferme
        console.evenement("dans le vide", "error")
        console.dit("dans le vide", "error")
        sys.stdout = vrai
        t("une sortie fermee ne tue pas le service", True)
    except Exception as exc:
        sys.stdout = vrai
        t("une sortie fermee ne tue pas le service", False, exc)
    finally:
        sys.stdout = vrai
        os.environ.clear()
        os.environ.update(avant)
        console.relire()

    # --- valeur inconnue ----------------------------------------------------
    t("un style inconnu retombe sur normal",
      sortie("nimportequoi", lambda c: None) == "" and console.STYLE in console.STYLES)
    s = sortie("trace", tout)
    t("`trace` est compris comme debug", "debug" in s, repr(s))

    print("   ------------------------------------------------")
    print("   %d controles OK, %d echec(s)" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
