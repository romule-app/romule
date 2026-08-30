"""Audit de securite automatique, sans dependance.

Deux familles de controles, volontairement separees :

  1. **Posture** — la facon dont CETTE installation est configuree : qui peut
     entrer, avec quoi, et ce qui traine sur le disque. C'est la source de
     loin la plus frequente de problemes reels sur un outil auto-heberge,
     et c'est verifiable hors ligne, instantanement.

  2. **Version de Python** — la seule « dependance » du projet. On interroge
     endoflife.date pour savoir si la serie utilisee recoit encore des
     correctifs de securite. Sans reseau, le controle est signale « non
     verifie » plutot que « bon » : un audit qui ment par omission est pire
     que pas d'audit.

Chaque controle rend un niveau : `grave`, `alerte`, `info` ou `bon`.
`code_sortie()` renvoie 2 si un controle grave a echoue, 1 pour une alerte,
0 sinon — de quoi bloquer un deploiement dans un pipeline.

Usage :
    python3 -m switchlib.audit            # rapport lisible
    python3 -m switchlib.audit --json     # pour un pipeline
    python3 -m switchlib.audit --hors-ligne
"""

import json
import os
import re
import stat
import sys
import urllib.request
from pathlib import Path

from . import config

NIVEAUX = {"grave": 3, "alerte": 2, "info": 1, "bon": 0}


def _c(niveau, titre, constat, remede=""):
    return {"niveau": niveau, "titre": titre, "constat": constat, "remede": remede}


# ------------------------------------------------------------------ posture

def _acces(cfg):
    """Qui peut ouvrir la ludotheque, et avec quoi."""
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
                      "SWITCH_TOKEN, ou coupe l'acces reseau."))
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
    """Vrai si l'installation semble servie via un proxy HTTPS."""
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
        out.append(_c("alerte", "SWITCH_TOKEN court",
                      "%d caracteres : cassable par essais repetes."
                      % len(config.TOKEN),
                      "Utilise au moins 24 caracteres aleatoires."))
    return out


def _permissions():
    """Les fichiers sensibles ne doivent pas etre lisibles par tout le monde."""
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
    """Quelques motifs qu'on ne veut jamais voir reapparaitre dans le code.

    Ce n'est pas un analyseur statique : c'est un garde-fou sur les erreurs
    precises que ce projet a deja rencontrees ou pourrait commettre.
    """
    # Ces chaines sont des MOTIFS DE RECHERCHE, jamais des appels : ce module
    # n'execute rien de ce qu'il cite. Il s'exclut lui-meme du balayage plus
    # bas, sinon il se signalerait a chaque passage.
    # Le troisieme champ dit A QUELS FICHIERS le motif s'applique. Sans lui,
    # `\bexec\s*\(` — ecrit pour Python — capturait `.exec(` d'une expression
    # reguliere JavaScript (`app.js`), et l'audit restait bloque sur une alerte
    # permanente qu'on finissait par ignorer. Un garde-fou qu'on apprend a
    # ignorer ne garde plus rien.
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
                continue                      # ce fichier CITE les motifs
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


# Champs qui viennent de l'utilisateur ou du reseau, et qui finissent a l'ecran.
_SENSIBLES = ("nom", "email", "titre", "name", "message", "error", "resume")


def _sans_esc(expression):
    """Identifiants sensibles concatenes SANS passer par esc().

    On retire d'abord tout ce qui est deja dans un `esc(...)`, puis on cherche
    ce qui reste : une simple recherche de motif ne distinguerait pas
    `esc(c.nom)` — sur : de `+ c.nom +` — dangereux.
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
    """Une donnee non echappee posee en innerHTML, c'est une injection HTML."""
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
    """Les en-tetes de securite sont-ils toujours poses par le serveur ?"""
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
    """L'interface repose sur des attributs `onclick`, y compris generes a la
    volee : `script-src` doit donc tolerer l'inline. C'est un affaiblissement
    reel, et il ne doit pas se perdre dans les fichiers."""
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
                                     headers={"User-Agent": "switchlib-audit"})
        with urllib.request.urlopen(req, timeout=10) as r:
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
    """Le projet revendique zero dependance : on le verifie, ca ne se decrete pas."""
    externes = set()
    connus = {p.stem for p in config.PKG.glob("*.py")} | {"switchlib"}
    for f in config.PKG.glob("*.py"):
        for ligne in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*(?:from|import)\s+([a-zA-Z_][\w]*)", ligne)
            if not m:
                continue
            nom = m.group(1)
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


# -------------------------------------------------------------------- rapport

def lancer(cfg=None, hors_ligne=False):
    cfg = cfg or config.load_config()
    controles = []
    for f in (_acces, _secrets):
        controles += f(cfg)
    controles += _permissions() + _entetes() + _csp() + _csrf() + _code()
    controles += _dependances() + _python(hors_ligne)
    pire = max((NIVEAUX[c["niveau"]] for c in controles), default=0)
    return {
        "controles": controles,
        "pire": pire,
        "resume": {n: sum(1 for c in controles if c["niveau"] == n)
                   for n in NIVEAUX},
    }


def code_sortie(rapport):
    """2 = probleme grave, 1 = alerte, 0 = rien a signaler."""
    return {3: 2, 2: 1}.get(rapport["pire"], 0)


SYMBOLE = {"grave": "[GRAVE ]", "alerte": "[ALERTE]",
           "info": "[ INFO ]", "bon": "[  OK  ]"}


def texte(rapport):
    lignes = ["Audit de securite — %s" % config.ROOT, ""]
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
