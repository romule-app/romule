"""Y a-t-il une version plus recente, et qu'apporte-t-elle ?

Un outil auto-heberge qu'on installe une fois et qu'on oublie finit par tourner
pendant des mois sur une version qui a recu des correctifs de securite. Rien
dans l'interface ne le disait.

Trois choses valent d'etre expliquees, parce qu'aucune ne va de soi.

**On interroge une seule fois par jour, et jamais au demarrage.** GitHub limite
les requetes anonymes a soixante par heure et par adresse : plusieurs
instances derriere la meme adresse publique se les partagent. Le resultat est
donc garde sur disque, avec l'heure de sa lecture.

**Le reseau ne doit jamais faire attendre l'interface.** La verification est
paresseuse : la route rend ce qu'elle sait, et ne va sur le reseau que si le
cache est perime. Une panne de GitHub rend « je ne sais pas », pas une erreur.

**Cela se coupe.** Certains hebergent precisement pour ne parler a personne.
Le reglage `maj_check` existe, il est documente, et l'audit dit ce qu'il fait.
"""

import json
import re
import time

from . import config, reseau
from . import __version__

# Version publiee : `v0.2.0` ou `0.2.0`, suivie eventuellement d'un suffixe.
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")

SOURCE = "https://api.github.com/repos/romule-app/romule/releases/latest"
CACHE = config.fichier_etat("_romule-maj.json", "_romule-maj.json")
DUREE = 24 * 3600
# Au-dela, la note de version est tronquee : elle s'affiche dans une fenetre,
# pas dans un navigateur de documentation.
MAX_NOTES = 4000


def _triplet(v):
    m = _VERSION.match(str(v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def plus_recente(publiee, courante=None):
    """`publiee` est-elle strictement posterieure a `courante` ?

    Compare des NOMBRES, pas des chaines : « 0.10.0 » est posterieure a
    « 0.9.0 », ce qu'une comparaison lexicale rend faux. Une version qu'on ne
    sait pas lire ne declenche rien — mieux vaut se taire que crier a tort.
    """
    a, b = _triplet(publiee), _triplet(courante or __version__)
    return bool(a and b and a > b)


def _lire_cache():
    try:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire_cache(d):
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    except OSError:
        pass                      # un disque plein ne doit pas casser l'interface


def _demander():
    """Interroge GitHub. Rend un dictionnaire, ou leve."""
    req = reseau.urllib.request.Request(
        SOURCE, headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "romule"})
    with reseau.ouvrir(req, timeout=8) as r:
        d = json.loads(r.read().decode("utf-8"))
    # Le `v` du tag est retire : l'interface ecrit deja « Version %s
    # disponible », et « Version v0.3.0 disponible » fait doublon. La
    # comparaison, elle, ne s'en soucie pas — `_triplet` ignore le prefixe.
    return {"version": str(d.get("tag_name") or "").lstrip("vV"),
            "titre": str(d.get("name") or ""),
            "notes": str(d.get("body") or "")[:MAX_NOTES],
            "url": str(d.get("html_url") or ""),
            "publiee": str(d.get("published_at") or "")}


def etat(cfg=None, forcer=False):
    """Ce qu'on sait de la derniere version. Ne leve jamais.

    Rend toujours les memes cles, pour que l'interface n'ait pas a distinguer
    « pas encore verifie » de « erreur » : dans les deux cas `disponible` est
    faux et il n'y a rien a montrer.
    """
    cfg = cfg or config.load_config()
    reponse = {"courante": __version__, "disponible": False, "version": "",
               "titre": "", "notes": "", "url": "", "verifie": 0,
               "actif": bool(cfg.get("maj_check", True))}
    if not reponse["actif"]:
        return reponse

    cache = _lire_cache()
    frais = (time.time() - float(cache.get("verifie") or 0)) < DUREE
    if forcer or not frais:
        try:
            cache = _demander()
            cache["verifie"] = int(time.time())
            _ecrire_cache(cache)
        except Exception:
            # Reseau coupe, GitHub indisponible, quota atteint : on garde ce
            # qu'on avait. Une verification ratee n'est pas un evenement.
            if not cache:
                return reponse

    reponse.update({k: cache.get(k, reponse[k])
                    for k in ("version", "titre", "notes", "url")})
    reponse["verifie"] = int(cache.get("verifie") or 0)
    reponse["disponible"] = plus_recente(cache.get("version"))
    return reponse
