"""L'API publique, par HTTP, de bout en bout.

`test_apikeys.py` verifie le magasin de cles et la fonction de portee. Ici on
verifie ce qui compte pour quelqu'un qui branche un tableau de bord : les
routes repondent, la pagination tient, et **une cle ne peut pas sortir de
`/api/v1/`**.

Ce dernier point est teste depuis l'exterieur, avec de vraies requetes, parce
qu'une portee correcte en theorie et contournee par le routage reel serait
exactement le genre de faille qu'on croit avoir ferme.

Une propriete du dispositif merite d'etre dite, parce qu'elle n'est pas
evidente et que c'est elle qui rend ces controles possibles depuis 127.0.0.1 :
**presenter une cle ne DONNE pas des droits, cela choisit un regime.**

Le serveur ecoute en local, donc `_local()` accorderait tout a n'importe quelle
requete venue de la meme machine. Mais des qu'une requete porte `X-Api-Key`,
c'est la branche des cles qui decide — et elle est portee a `/api/v1/`. Une cle
ne peut donc pas servir a elargir un acces : au mieux elle le restreint.

C'est deliberé. Un client qui presente une cle annonce qu'il est un programme,
pas un navigateur ; lui accorder au passage tout ce qu'un navigateur local
obtiendrait ferait de la cle une porte derobee au lieu d'un laissez-passer.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE_PROJET = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, RACINE_PROJET)


def libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return str(s.getsockname()[1])


RACINE = str(Path(tempfile.mkdtemp(prefix="ludo-api-")).resolve())
jeux = Path(RACINE) / "GAMES"
jeux.mkdir(parents=True)
for i in range(7):
    (jeux / ("Jeu numero %02d [0100%012x][v0].nsp" % (i, i))).write_bytes(b"\0" * 64)

PORT = libre()
BASE = "http://127.0.0.1:" + PORT
srv = subprocess.Popen(
    [sys.executable, "-m", "romule", "serve"], cwd=RACINE_PROJET,
    env=dict(os.environ, ROMULE_ROOT=RACINE, ROMULE_WEB_PORT=PORT,
             ROMULE_NO_BROWSER="1", ROMULE_ADB="/inexistant"),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(120):
    try:
        urllib.request.urlopen(BASE + "/api/health", timeout=2)
        break
    except Exception:
        time.sleep(0.5)

# La cle est creee dans le magasin du serveur : meme racine, donc meme fichier.
os.environ["ROMULE_ROOT"] = RACINE
from romule import apikeys, apiv1                  # noqa: E402
apikeys.FICHIER = Path(RACINE) / "_romule-cles.json"
_, CLE = apikeys.creer("essai")
_, CLE_MORTE = apikeys.creer("revoquee")
apikeys.revoquer([k for k in apikeys.liste(True)
                  if k["nom"] == "revoquee"][0]["id"])

ok = fail = 0


def t(nom, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  ok   %s" % nom)
    else:
        fail += 1
        print("  ECHEC %s   %s" % (nom, detail))


def demander(chemin, cle=CLE, methode="GET", entete=True):
    """Rend (code, objet). Ne leve pas : un 403 est une reponse, pas une panne."""
    url = BASE + chemin
    entetes = {}
    if cle and entete:
        entetes["X-Api-Key"] = cle
    elif cle:
        url += ("&" if "?" in url else "?") + "apikey=" + cle
    req = urllib.request.Request(url, headers=entetes, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        corps = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(corps)
        except ValueError:
            return e.code, {"_brut": corps[:120]}


def test_les_routes_repondent():
    for chemin in ("/api/v1/health", "/api/v1/system", "/api/v1/stats",
                   "/api/v1/library", "/api/v1/platforms", "/api/v1/device",
                   "/api/v1/job", "/api/v1/trash", "/api/v1/openapi.json"):
        code, corps = demander(chemin)
        t("%s repond 200" % chemin, code == 200, "%s %s" % (code, corps))


def test_contenu():
    _, sys_ = demander("/api/v1/system")
    t("system annonce la version d'API", sys_.get("api") == "v1", sys_)
    t("system porte la licence", "AGPL" in (sys_.get("licence") or ""), sys_)
    _, st = demander("/api/v1/stats")
    t("stats compte les sept jeux", st.get("total") == 7, st.get("total"))
    _, lib = demander("/api/v1/library")
    t("library pagine", lib.get("total") == 7 and lib.get("page") == 1, lib)
    t("library rend des fiches", len(lib.get("items") or []) == 7)
    prem = (lib.get("items") or [{}])[0]
    t("une fiche porte une cle", bool(prem.get("key")), prem)
    # Le chemin absolu revele l'arborescence du serveur, donc souvent le nom de
    # compte de la personne. Il ne doit pas sortir.
    t("aucune fiche ne publie de chemin absolu",
      not any(str(v).startswith("/") for v in prem.values()), prem)
    t("aucune fiche ne contient la racine du serveur",
      RACINE not in json.dumps(lib), RACINE)


def test_pagination():
    _, p = demander("/api/v1/library?page=1&limit=3")
    t("limit est respecte", len(p["items"]) == 3, len(p["items"]))
    t("le nombre de pages est calcule", p["pages"] == 3, p["pages"])
    _, p3 = demander("/api/v1/library?page=3&limit=3")
    t("la derniere page contient le reste", len(p3["items"]) == 1, p3["items"])
    _, vide = demander("/api/v1/library?page=99&limit=3")
    t("une page hors bornes est vide, pas une erreur", vide["items"] == [])
    _, abusif = demander("/api/v1/library?limit=100000")
    t("limit est plafonne", abusif["limit"] == apiv1.LIMITE_MAX, abusif["limit"])
    # Deux comportements distincts, et c'est voulu : illisible -> defaut,
    # hors bornes -> ramene dans les bornes. La specification le dit.
    _, illisible = demander("/api/v1/library?page=zero&limit=nimporte")
    t("une pagination illisible retombe sur le defaut",
      illisible["page"] == 1 and illisible["limit"] == apiv1.LIMITE_DEFAUT,
      illisible)
    _, negatif = demander("/api/v1/library?limit=-4")
    t("une limite negative est ramenee a 1", negatif["limit"] == 1,
      negatif["limit"])


def test_recherche_et_fiche():
    code, r = demander("/api/v1/search?q=numero%2003")
    t("la recherche trouve", code == 200 and r["total"] == 1, r)
    code, _ = demander("/api/v1/search")
    t("une recherche sans q est un 400", code == 400, code)
    _, lib = demander("/api/v1/library")
    cle = lib["items"][0]["key"]
    code, fiche = demander("/api/v1/library/" + urllib.parse.quote(cle))
    t("une fiche se recupere par sa cle", code == 200 and fiche["key"] == cle,
      "%s %s" % (code, fiche))
    code, _ = demander("/api/v1/library/inexistant.nsp")
    t("une cle inconnue est un 404", code == 404, code)


def test_route_inconnue():
    code, corps = demander("/api/v1/inexistante")
    t("une route inconnue est un 404 qui oriente",
      code == 404 and "openapi" in json.dumps(corps), corps)


def test_la_specification_correspond_au_code():
    """Une documentation qui derive du code est pire qu'absente.

    On interroge chaque route decrite et on verifie qu'elle existe. L'inverse —
    une route servie mais non decrite — est verifie par la liste explicite
    ci-dessous, qui doit etre tenue a jour de pair avec `router()`.
    """
    servies = {("GET", "/api/v1/" + n) for n in (
        "health", "openapi.json", "system", "stats", "library", "search",
        "platforms", "device", "job", "trash")}
    servies.add(("GET", "/api/v1/library/{key}"))
    servies |= {("POST", "/api/v1/" + n) for n in ("scan", "convert", "push")}
    decrites = apiv1.routes_decrites()
    t("toute route servie est decrite", not (servies - decrites),
      sorted(servies - decrites))
    t("toute route decrite est servie", not (decrites - servies),
      sorted(decrites - servies))
    _, spec = demander("/api/v1/openapi.json")
    t("la specification est servie telle quelle",
      spec.get("openapi", "").startswith("3."), spec.get("openapi"))
    t("elle declare l'authentification par cle",
      "ApiKeyHeader" in json.dumps(spec.get("components", {})))


def test_la_cle_ne_sort_pas_de_sa_portee():
    """Le controle central. Une cle valide ne doit atteindre QUE `/api/v1/`."""
    interdits = ["/api/comptes", "/api/config", "/api/scan", "/api/health",
                 "/api/compte-supprimer", "/", "/app.js", "/api/trash-list",
                 "/api/v1", "/api/v1x/library"]
    for chemin in interdits:
        code, _ = demander(chemin)
        t("cle refusee sur %s" % chemin, code in (401, 403), code)


def test_cle_invalide_et_revoquee():
    for nom, cle in (("inconnue", "rml_pasunevraiecle"),
                     ("revoquee", CLE_MORTE),
                     ("vide", "x")):
        code, _ = demander("/api/v1/system", cle=cle)
        t("cle %s refusee" % nom, code in (401, 403), code)


def test_cle_en_parametre():
    code, _ = demander("/api/v1/system", entete=False)
    t("la cle passe aussi en parametre d'URL", code == 200, code)


def test_post_sans_origin():
    """Un client en ligne de commande n'envoie pas d'`Origin`. Le controle
    anti-CSRF ne doit pas le confondre avec un site tiers : c'est la cle
    elle-meme qui joue ce role, puisqu'un navigateur ne l'attache jamais seul."""
    code, corps = demander("/api/v1/scan", methode="POST")
    t("POST /scan est accepte sans Origin", code in (202, 409),
      "%s %s" % (code, corps))
    # La tache lancee occupe le serveur : la seconde doit recevoir 409, et non
    # une erreur qui laisserait croire a une requete mal formee.
    code2, corps2 = demander("/api/v1/scan", methode="POST")
    t("une seconde tache recoit 409, pas 400",
      code2 in (202, 409), "%s %s" % (code2, corps2))


def _local(chemin, corps=None):
    """Sans cle : on est en 127.0.0.1, donc dans le regime local — celui de
    l'interface. C'est par la que passent les trois routes de gestion."""
    donnees = json.dumps(corps or {}).encode() if corps is not None else None
    req = urllib.request.Request(
        BASE + chemin, data=donnees,
        headers={"Content-Type": "application/json"} if donnees else {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {}


def test_gestion_par_l_interface():
    """Les trois routes que le bloc « Cles d'API » des Reglages utilise.

    Elles sont INTERNES : l'interface est un navigateur avec une session, elle
    ne peut pas passer par `/api/v1` qui exige justement une cle. Elles ne sont
    donc pas figees — mais elles doivent marcher, et le seul moyen de le savoir
    est de les appeler.
    """
    code, avant = _local("/api/cles")
    t("l'interface peut lister les cles", code == 200 and "cles" in avant, code)
    n0 = len(avant["cles"])

    code, cree = _local("/api/cle-creer", {"nom": "depuis l'interface"})
    t("l'interface peut creer une cle", code == 200 and cree.get("secret"), cree)
    secret = cree.get("secret", "")
    t("la cle creee porte le marqueur", secret.startswith("rml_"), secret[:8])
    t("la fiche rendue ne contient pas d'empreinte",
      "empreinte" not in json.dumps(cree.get("cle", {})), cree.get("cle"))

    # Elle doit fonctionner tout de suite : une cle creee et inutilisable
    # serait le pire des deux mondes.
    code, _ = demander("/api/v1/system", cle=secret)
    t("la cle creee par l'interface fonctionne aussitot", code == 200, code)

    code, apres = _local("/api/cles")
    t("elle apparait dans la liste", len(apres["cles"]) == n0 + 1,
      "%d -> %d" % (n0, len(apres["cles"])))

    cid = cree["cle"]["id"]
    code, r = _local("/api/cle-revoquer", {"id": cid})
    t("l'interface peut revoquer", code == 200 and r.get("ok"), r)
    code, _ = demander("/api/v1/system", cle=secret)
    t("la cle revoquee ne fonctionne plus", code in (401, 403), code)
    code, r = _local("/api/cle-revoquer", {"id": "inexistante"})
    t("revoquer une cle inconnue rend ok=false, pas une erreur",
      code == 200 and r.get("ok") is False, r)


try:
    for fn in (test_les_routes_repondent, test_contenu, test_pagination,
               test_recherche_et_fiche, test_route_inconnue,
               test_la_specification_correspond_au_code,
               test_la_cle_ne_sort_pas_de_sa_portee,
               test_cle_invalide_et_revoquee, test_cle_en_parametre,
               test_post_sans_origin, test_gestion_par_l_interface):
        fn()
finally:
    srv.terminate()
print("  %d controles OK, %d echec(s)" % (ok, fail))
sys.exit(1 if fail else 0)
