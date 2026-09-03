"""An outbound call must not be able to read a local file.

`urllib.request.urlopen` does not only open HTTP: it accepts `file://`, `ftp://`,
and whatever the installed handlers know how to process. Three of the addresses
Romule uses come from the configuration — the cover source, the titledb mirrors,
the OIDC issuer — and nothing checked their scheme. A `file:///etc/passwd` in the
cover field therefore made the server read a local file and hand it back as an
image.

This test holds both halves of the property: what must pass passes, and what must
be refused is — including in the shapes that bypass a naive comparison.
"""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from romule import reseau                                       # noqa: E402

ok = ko = 0


def t(nom, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % nom)
    else:
        ko += 1
        print("  ECHEC %s   %s" % (nom, detail))


def test_accepte_http():
    for u in ("http://exemple.fr/a", "https://exemple.fr/a",
              "HTTPS://EXEMPLE.FR/A", "https://exemple.fr:8443/a?b=c"):
        try:
            reseau.verifier(u)
            t("accepte %s" % u, True)
        except reseau.SchemaRefuse as exc:
            t("accepte %s" % u, False, exc)


def test_refuse_le_reste():
    # `file:` is the case that matters: it is the one that turns the service
    # into a file reader. The others are refused by the same rule.
    for u in ("file:///etc/passwd", "FILE:///etc/passwd", "ftp://h/f",
              "gopher://h/", "data:text/plain,bonjour", "/etc/passwd",
              "etc/passwd", "", None):
        try:
            reseau.verifier(u)
            t("refuse %r" % u, False, "accepte a tort")
        except reseau.SchemaRefuse:
            t("refuse %r" % u, True)


def test_ouvrir_verifie_aussi_les_Request():
    """The check must be on the URL the request carries, not on the object."""
    req = urllib.request.Request("file:///etc/passwd",
                                 headers={"User-Agent": "romule"})
    try:
        reseau.ouvrir(req)
        t("une Request en file:// est refusee", False, "ouverte a tort")
    except reseau.SchemaRefuse:
        t("une Request en file:// est refusee", True)
    except Exception as exc:
        t("une Request en file:// est refusee", False, "autre erreur : %r" % exc)


def test_aucune_sortie_directe_dans_le_code_livre():
    """The guard is only worth something if nobody bypasses it.

    A centralised check goes stale as soon as a direct call reappears elsewhere.
    We verify it on the source, not on the intention.
    """
    racine = Path(__file__).resolve().parent.parent
    fautifs = []
    for f in sorted(racine.glob("*.py")):
        if f.name == "reseau.py":
            continue
        for n, ligne in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "urlopen(" in ligne and not ligne.lstrip().startswith("#"):
                fautifs.append("%s:%d" % (f.name, n))
    t("aucun urlopen direct hors de reseau.py", not fautifs, fautifs)


for fn in (test_accepte_http, test_refuse_le_reste,
           test_ouvrir_verifie_aussi_les_Request,
           test_aucune_sortie_directe_dans_le_code_livre):
    fn()
print("  %d controles OK, %d echec(s)" % (ok, ko))
sys.exit(1 if ko else 0)
