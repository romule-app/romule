"""Une sortie reseau ne doit pas pouvoir lire un fichier local.

`urllib.request.urlopen` n'ouvre pas que du HTTP : il accepte `file://`,
`ftp://`, et tout ce que les gestionnaires installes savent traiter. Trois
adresses utilisees par Romule viennent de la configuration — la source des
jaquettes, les miroirs de titledb, l'emetteur OIDC — et rien ne verifiait leur
schema. Un `file:///etc/passwd` dans le champ des jaquettes faisait donc lire
un fichier local au serveur, qui le renvoyait comme une image.

Ce test tient les deux moities de la propriete : ce qui doit passer passe, et
ce qui doit etre refuse l'est — y compris sous les formes qui contournent une
comparaison naive.
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
    # `file:` est le cas qui compte : c'est celui qui transforme le service en
    # lecteur de fichiers. Les autres sont refuses par la meme regle.
    for u in ("file:///etc/passwd", "FILE:///etc/passwd", "ftp://h/f",
              "gopher://h/", "data:text/plain,bonjour", "/etc/passwd",
              "etc/passwd", "", None):
        try:
            reseau.verifier(u)
            t("refuse %r" % u, False, "accepte a tort")
        except reseau.SchemaRefuse:
            t("refuse %r" % u, True)


def test_ouvrir_verifie_aussi_les_Request():
    """Le controle doit porter sur l'URL portee par la requete, pas sur l'objet."""
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
    """Le garde ne vaut que si personne ne le contourne.

    Un controle centralise se perime des qu'un appel direct reapparait ailleurs.
    On le verifie sur le source, pas sur l'intention.
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
