"""Automatic security audit, with no dependency.

Deux familles de controles, volontairement separees :

  1. **Posture** — how THIS installation is configured: who can get in, with
     what, and what is lying around on disk. By far the most common source of
     real problems on a self-hosted tool, and checkable offline, instantly.

  2. **Python version** — the project's only "dependency". We ask
     endoflife.date whether the series in use still receives security fixes.
     With no network, the check reports "not verified" rather than "fine": an
     audit that lies by omission is worse than no audit.

Each check returns a level: `grave`, `alerte`, `info` or `bon`.
`code_sortie()` returns 2 when a severe check failed, 1 for a warning, 0
otherwise — enough to block a deployment in a pipeline.

Usage :
    python3 -m romule.audit            # readable report
    python3 -m romule.audit --json     # for a pipeline
    python3 -m romule.audit --hors-ligne
"""

import ast
import json
import os
import re
import stat
import sys
import urllib.request
from pathlib import Path

from . import config, reseau

NIVEAUX = {"grave": 3, "alerte": 2, "info": 1, "bon": 0}


def _c(niveau, titre, constat, remede=""):
    return {"niveau": niveau, "titre": titre, "constat": constat, "remede": remede}


# ------------------------------------------------------------------ posture

def _acces(cfg):
    """Who can open the library, and with what."""
    from . import auth, comptes
    out = []
    mode = cfg.get("auth_mode", "aucun")
    actif = auth.actif(cfg)
    ouvert = bool(cfg.get("lan_access")) or config.ENV_LAN

    if mode in ("oidc", "interne") and not actif:
        out.append(_c("grave", "Authentification annoncee mais inactive",
                      "Le mode « %s » est choisi, mais il manque %s : personne "
                      "n'est reellement authentifie." % (
                          mode,
                          "un compte" if mode == "interne"
                          else "l'adresse du fournisseur ou le client ID"),
                      "Termine la configuration, ou repasse en mode « Aucune »."))
    elif not actif and ouvert and not config.TOKEN:
        out.append(_c("grave", "Ludotheque ouverte au reseau sans authentification",
                      "L'acces depuis le reseau local est autorise et aucune "
                      "authentification n'est active : n'importe quel appareil "
                      "du reseau peut tout piloter.",
                      "Active les comptes internes ou le SSO, ou definis "
                      "ROMULE_TOKEN, ou coupe l'acces reseau."))
    elif not actif:
        out.append(_c("info", "Acces local uniquement",
                      "Aucune authentification, mais rien n'est expose : seul "
                      "127.0.0.1 peut se connecter."))
    else:
        out.append(_c("bon", "Authentification active",
                      "Mode « %s ». Elle s'applique aussi depuis cette machine."
                      % mode))

    if mode == "oidc" and actif:
        if not (cfg.get("oidc_emails") or "").strip() \
                and not (cfg.get("oidc_groupes") or "").strip():
            out.append(_c("alerte", "Aucune liste de comptes autorises",
                          "Toute personne que ton fournisseur authentifie peut "
                          "entrer, meme si elle n'a rien a faire ici.",
                          "Renseigne des adresses ou un groupe dans « Comptes "
                          "autorises »."))
        if (cfg.get("oidc_issuer") or "").startswith("http://"):
            out.append(_c("grave", "Fournisseur SSO joint en clair",
                          "L'issuer commence par http:// : les jetons "
                          "circulent sans chiffrement.",
                          "Passe le fournisseur en https://."))

    if mode == "interne" and actif:
        n = comptes.nombre()
        out.append(_c("bon", "Comptes internes",
                      "%d compte(s). Empreintes scrypt (N=2^%d, r=%d, p=%d)."
                      % (n, comptes.SCRYPT_N.bit_length() - 1,
                         comptes.SCRYPT_R, comptes.SCRYPT_P)))
        if ouvert and not _https_probable(cfg):
            out.append(_c("alerte", "Mots de passe transmis en clair",
                          "La ludotheque est jointe en HTTP sur le reseau : le "
                          "mot de passe circule en clair a chaque connexion.",
                          "Place-la derriere un reverse proxy HTTPS "
                          "(Caddy, Traefik, nginx) et renseigne l'adresse "
                          "publique."))
    return out


def _https_probable(cfg):
    """True when the installation appears to be served through an HTTPS proxy."""
    return (cfg.get("oidc_redirect") or "").startswith("https://")


def _secrets(cfg):
    out = []
    s = cfg.get("auth_secret") or ""
    if not s:
        out.append(_c("info", "Cle de signature des sessions",
                      "Pas encore creee : elle le sera a la premiere connexion."))
    elif len(s) < 32:
        out.append(_c("grave", "Cle de signature trop courte",
                      "`auth_secret` fait %d caracteres : une cle courte se "
                      "devine, et permet alors de forger une session valide."
                      % len(s),
                      "Efface `auth_secret` du fichier de configuration : une "
                      "cle solide sera regeneree."))
    else:
        out.append(_c("bon", "Cle de signature des sessions",
                      "%d caracteres aleatoires." % len(s)))

    if config.TOKEN and len(config.TOKEN) < 20:
        out.append(_c("alerte", "ROMULE_TOKEN court",
                      "%d caracteres : cassable par essais repetes."
                      % len(config.TOKEN),
                      "Utilise au moins 24 caracteres aleatoires."))
    return out


def _permissions():
    """The sensitive files must not be readable by everybody."""
    from . import comptes
    out = []
    for chemin, exige in ((config.CONFIG_FILE, 0o077), (comptes.FICHIER, 0o077)):
        if not Path(chemin).exists():
            continue
        m = os.stat(chemin).st_mode
        trop = stat.S_IMODE(m) & exige
        if trop:
            out.append(_c("alerte", "Fichier lisible au-dela du proprietaire",
                          "%s est en %o : il contient des secrets."
                          % (Path(chemin).name, stat.S_IMODE(m)),
                          "chmod 600 %s" % chemin))
        else:
            out.append(_c("bon", "Permissions de %s" % Path(chemin).name,
                          "%o — reserve au proprietaire." % stat.S_IMODE(m)))
    return out


def _code():
    """A few patterns we never want to see reappear in the code.

    This is not a static analyser: it is a guard against the specific mistakes
    this project has already made or could make.
    """
    # These strings are SEARCH PATTERNS, never calls: this module executes
    # nothing of what it quotes. It excludes itself from the sweep below,
    # otherwise it would flag itself on every pass.
    # The third field says WHICH FILES the pattern applies to. Without it,
    # `\bexec\s*\(` — written for Python — caught the `.exec(` of a JavaScript
    # regular expression (`app.js`), and the audit sat on a permanent warning
    # everyone learnt to ignore. A guard you learn to ignore guards nothing.
    PY_SEUL, TOUS = ".py", "*"
    interdits = [
        (r"\bshell\s*=\s*True", "subprocess avec shell=True",
         "Une commande construite par concatenation devient injectable.", PY_SEUL),
        (r"(?<![.\w])\beval\s*\(|(?<![.\w])\bexec\s*\(", "eval() ou exec()",
         "Executer du texte comme du code n'a aucune raison d'etre ici.", TOUS),
        (r"\bpickle\b", "pickle",
         "Deserialiser du pickle revient a executer ce qu'il contient.", PY_SEUL),
        (r"verify\s*=\s*False|_create_unverified_context", "TLS non verifie",
         "Une connexion dont on ne verifie pas le certificat n'en est pas une.", TOUS),
    ]
    out = []
    fichiers = list(config.PKG.glob("*.py")) + list((config.PKG / "static").glob("*.js"))
    for motif, titre, pourquoi, portee in interdits:
        touches = []
        for f in fichiers:
            if f.name == "audit.py":
                continue                      # this file QUOTES the patterns
            if portee != "*" and f.suffix != portee:
                continue
            for n, ligne in enumerate(f.read_text(encoding="utf-8",
                                                  errors="replace").splitlines(), 1):
                if re.search(motif, ligne):
                    touches.append("%s:%d" % (f.name, n))
        if touches:
            out.append(_c("alerte", titre, "%s  (%s)" % (pourquoi, ", ".join(touches[:5])),
                          "Verifie chaque occurrence, ou justifie-la en commentaire."))
    out += _innerhtml()
    if not out:
        out.append(_c("bon", "Motifs dangereux",
                      "Aucun des %d motifs surveilles n'apparait dans le code, "
                      "et aucune donnee n'est injectee en innerHTML sans "
                      "echappement." % len(interdits)))
    return out


# Fields that come from the user or the network and end up on screen.
_SENSIBLES = ("nom", "email", "titre", "name", "message", "error", "resume")


def _sans_esc(expression):
    """Sensitive identifiers concatenated WITHOUT going through esc().

    We first strip everything already inside an `esc(...)`, then look at what
    is left: a plain pattern search would not tell `esc(c.nom)` — safe — from
    `+ c.nom +` — dangerous.
    """
    reste, i = [], 0
    while i < len(expression):
        j = expression.find("esc(", i)
        if j < 0:
            reste.append(expression[i:])
            break
        reste.append(expression[i:j])
        prof, k = 1, j + 4
        while k < len(expression) and prof:
            prof += (expression[k] == "(") - (expression[k] == ")")
            k += 1
        i = k
    texte_restant = "".join(reste)
    return [c for c in _SENSIBLES
            if re.search(r"[+\s]\w+\.%s\b" % c, texte_restant)]


def _innerhtml():
    """Unescaped data assigned to innerHTML is an HTML injection."""
    touches = []
    for f in (config.PKG / "static").glob("*.js"):
        src = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"innerHTML\s*=", src):
            fin = src.find(";", m.end())
            expression = src[m.end():fin if fin > 0 else len(src)]
            ligne = src.count("\n", 0, m.start()) + 1
            for champ in _sans_esc(expression):
                touches.append("%s:%d (%s)" % (f.name, ligne, champ))
    if touches:
        return [_c("alerte", "Donnee injectee en innerHTML sans echappement",
                   "Une valeur controlee par l'utilisateur atterrit dans du "
                   "HTML brut : %s." % ", ".join(sorted(set(touches))[:6]),
                   "Passer par textContent / R.texte, ou echapper avec esc().")]
    return []


def _entetes():
    """Are the security headers still being set by the server?"""
    src = (config.PKG / "server.py").read_text(encoding="utf-8", errors="replace")
    attendus = ("Content-Security-Policy", "X-Content-Type-Options",
                "X-Frame-Options", "Referrer-Policy")
    manque = [e for e in attendus if e not in src]
    if manque:
        return [_c("alerte", "En-tetes de securite manquants",
                   "Absents du serveur : %s." % ", ".join(manque),
                   "Voir _entetes_securite() dans server.py.")]
    return [_c("bon", "En-tetes de securite", "Les %d en-tetes sont poses."
               % len(attendus))]


def _csp():
    """`script-src 'self'` with no tolerance for inline, since phase 4.

    The check reads `server.py`'s SOURCE rather than querying the server: the
    header depends on the request (HSTS is only set over TLS), and an audit run
    offline must still answer. The "inline allowed" branch stays written: it
    would light up again if someone restored the tolerance, which is exactly
    what we want reported."""
    src = (config.PKG / "server.py").read_text(encoding="utf-8", errors="replace")
    if "Content-Security-Policy" not in src:
        return [_c("alerte", "Aucune politique de contenu",
                   "Le serveur ne pose pas de Content-Security-Policy.",
                   "Voir _entetes_securite() dans server.py.")]
    inline = "script-src 'self' 'unsafe-inline'" in src
    externe = "default-src 'self'" in src
    if inline and externe:
        return [_c("info", "Scripts en ligne autorises",
                   "`script-src` accepte l'inline : sans cela, les boutons de "
                   "l'interface cessent de repondre. Le chargement de scripts "
                   "depuis un autre domaine reste interdit.",
                   "Pour durcir : remplacer les attributs onclick par une "
                   "delegation d'evenements, puis retirer 'unsafe-inline'.")]
    if inline:
        return [_c("alerte", "Politique de contenu trop permissive",
                   "L'inline est autorise sans restreindre les origines.",
                   "Ajouter default-src 'self'.")]
    return [_c("bon", "Politique de contenu stricte",
               "Aucun script en ligne autorise.")]


def _csrf():
    src = (config.PKG / "server.py").read_text(encoding="utf-8", errors="replace")
    if "_meme_origine" in src and "def do_POST" in src \
            and src.index("_meme_origine") < src.rindex("_route_post"):
        return [_c("bon", "Protection CSRF",
                   "Tout POST est refuse s'il ne vient pas de cette page.")]
    return [_c("grave", "Protection CSRF absente",
               "Un site tiers pourrait declencher des actions avec la session "
               "de l'utilisateur.",
               "Retablir le controle d'origine dans do_POST.")]


# ---------------------------------------------------------------- dependances

def _python(hors_ligne):
    v = "%d.%d" % sys.version_info[:2]
    detail = "Python %d.%d.%d" % sys.version_info[:3]
    if hors_ligne:
        return [_c("info", "Version de Python", detail + " — non verifiee "
                   "(mode hors ligne).")]
    try:
        req = urllib.request.Request("https://endoflife.date/api/python.json",
                                     headers={"User-Agent": "romule-audit"})
        with reseau.ouvrir(req, timeout=10) as r:
            series = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as exc:
        return [_c("info", "Version de Python",
                   detail + " — verification impossible (%s)." % exc)]
    for s in series:
        if s.get("cycle") != v:
            continue
        fin = s.get("eol")
        if fin is True:
            return [_c("grave", "Python en fin de vie",
                       "La serie %s ne recoit plus de correctifs de securite." % v,
                       "Passe a une serie encore maintenue.")]
        return [_c("bon", "Version de Python",
                   "%s — serie maintenue%s."
                   % (detail, " jusqu'au %s" % fin if isinstance(fin, str) else ""))]
    return [_c("info", "Version de Python",
               detail + " — serie inconnue du referentiel.")]


def _dependances():
    """The project claims zero dependencies: we check it, it is not decreed.

    Parsed with `ast`, not with a regular expression. The regex matched any
    line whose first word was `import` or `from` — including a wrapped comment
    reading "the user thinks the import failed", which reported a dependency
    named `failed`. A guard that cries wolf gets switched off, and then it
    guards nothing.

    Parsing also catches what the regex missed: `import a, b` declares two
    modules, and `import a.b` depends on `a`.
    """
    externes = set()
    connus = {p.stem for p in config.PKG.glob("*.py")} | {"romule"}
    for f in config.PKG.glob("*.py"):
        try:
            arbre = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            # A file that does not parse is a different problem, and the
            # syntax suite is the one that reports it. Here we simply cannot
            # conclude, and we say nothing rather than guess.
            continue
        noms = set()
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                noms |= {a.name.split(".")[0] for a in noeud.names}
            elif isinstance(noeud, ast.ImportFrom):
                # `level > 0` is a relative import — `from . import x` — so by
                # construction it is one of ours.
                if not noeud.level and noeud.module:
                    noms.add(noeud.module.split(".")[0])
        for nom in noms:
            if nom in connus or nom in sys.stdlib_module_names:
                continue
            externes.add(nom)
    if externes:
        return [_c("alerte", "Dependance externe introduite",
                   "Modules hors bibliotheque standard : %s."
                   % ", ".join(sorted(externes)),
                   "Chaque dependance ajoute une surface a auditer et a mettre "
                   "a jour. Retire-la, ou assume-la explicitement.")]
    return [_c("bon", "Aucune dependance externe",
               "Seule la bibliotheque standard est importee : rien a auditer "
               "en amont, rien a mettre a jour en urgence.")]


def _cles_api():
    """API keys are an access path in their own right: they belong in the
    report that says who can get in.

    A key does not expire and reminds nobody of itself. The one created six
    months ago to try out a dashboard still opens the door, and nothing in the
    interface puts it in front of you. This is the one moment it gets read
    again.
    """
    from . import apikeys
    try:
        cles = apikeys.liste()
    except Exception:
        return []
    if not cles:
        return [_c("bon", "Aucune cle d'API",
                   "Aucune cle n'est active : l'API n'est atteignable par "
                   "personne.")]
    jamais = [k for k in cles if not k.get("dernier_usage")]
    detail = "%d cle(s) active(s) : %s." % (
        len(cles), ", ".join(k["nom"] for k in cles[:5]))
    if jamais:
        return [_c("info", "Cles d'API actives",
                   detail + " %d n'a jamais servi." % len(jamais),
                   "Une cle creee pour un essai et jamais utilisee ouvre "
                   "toujours l'API : `romule apikey revoke <id>`.")]
    return [_c("info", "Cles d'API actives", detail,
               "Chaque cle atteint /api/v1/ et rien d'autre. "
               "`romule apikey list` montre leur derniere utilisation.")]


# -------------------------------------------------------------------- rapport

def lancer(cfg=None, hors_ligne=False):
    cfg = cfg or config.load_config()
    controles = []
    for f in (_acces, _secrets):
        controles += f(cfg)
    controles += _permissions() + _entetes() + _csp() + _csrf() + _code()
    controles += _cles_api()
    controles += _dependances() + _python(hors_ligne)
    pire = max((NIVEAUX[c["niveau"]] for c in controles), default=0)
    return {
        "controles": controles,
        "pire": pire,
        "resume": {n: sum(1 for c in controles if c["niveau"] == n)
                   for n in NIVEAUX},
    }


def code_sortie(rapport):
    """2 = severe problem, 1 = warning, 0 = nothing to report."""
    return {3: 2, 2: 1}.get(rapport["pire"], 0)


SYMBOLE = {"grave": "[GRAVE ]", "alerte": "[ALERTE]",
           "info": "[ INFO ]", "bon": "[  OK  ]"}


def texte(rapport):
    lignes = ["Audit de securite — %s" % config.ROOT,
              "Ludotheque — %s" % config.LUDO, ""]
    for c in sorted(rapport["controles"], key=lambda x: -NIVEAUX[x["niveau"]]):
        lignes.append("%s %s" % (SYMBOLE[c["niveau"]], c["titre"]))
        lignes.append("         %s" % c["constat"])
        if c["remede"]:
            lignes.append("         -> %s" % c["remede"])
        lignes.append("")
    r = rapport["resume"]
    lignes.append("%d grave(s), %d alerte(s), %d info, %d conforme(s)."
                  % (r["grave"], r["alerte"], r["info"], r["bon"]))
    return "\n".join(lignes)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    rapport = lancer(hors_ligne="--hors-ligne" in argv)
    if "--json" in argv:
        print(json.dumps(rapport, indent=2, ensure_ascii=False))
    else:
        print(texte(rapport))
    return code_sortie(rapport)


if __name__ == "__main__":
    sys.exit(main())
