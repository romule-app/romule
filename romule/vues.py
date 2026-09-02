"""Vues enregistrees — une combinaison de filtres qu'on retrouve d'un clic.

Trois filtres cohabitent dans la bibliotheque : la recherche, la pastille
d'etat, et les filtres avances. Ils se composent, mais les rejouer demande de
refaire les trois gestes a chaque fois. Une vue les garde ensemble.

Ce qu'une vue retient, et ce qu'elle ne retient pas
---------------------------------------------------
Elle retient ce qui DEFINIT un sous-ensemble de la ludotheque : la plateforme,
la recherche, l'etat, les filtres avances.

Elle ne retient ni le tri, ni la taille des vignettes, ni la pagination. Ce
sont des preferences d'AFFICHAGE : elles valent pour tout ce qu'on regarde, et
les enfermer dans une vue rendrait celle-ci surprenante — on rappellerait
« Jeux a convertir » et l'ordre de la grille changerait sans qu'on l'ait
demande.

Cote serveur, et pas dans le navigateur
----------------------------------------
Le tri et la taille vivent dans `localStorage` : ils sont propres a l'ecran
qu'on a sous les yeux. Une vue est un objet qu'on a construit, qu'on veut
retrouver sur le telephone comme sur le poste, et qui ne doit pas disparaitre
parce qu'on a vide son navigateur.
"""

import json
import os
import secrets
import threading
import time

from . import config

FICHIER = config.fichier_etat("_romule-vues.json", "_romule-vues.json")

# Ce qu'on accepte d'enregistrer. Une liste FERMEE : le navigateur envoie ce
# qu'il veut, et sans cette barriere une version future du client pourrait
# faire grossir le fichier d'etat avec n'importe quoi.
CHAMPS = ("systeme", "recherche", "etat", "avances")

MAX_VUES = 50           # au-dela, c'est une liste, plus un raccourci
_LOCK = threading.RLock()


def _lire():
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "vues": []}
    if not isinstance(d, dict) or not isinstance(d.get("vues"), list):
        return {"version": 1, "vues": []}
    return d


def _ecrire(d):
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FICHIER)


def _propre(filtres):
    """Ne garde que les champs connus, et borne ce qui peut l'etre."""
    f = filtres if isinstance(filtres, dict) else {}
    out = {
        "systeme": str(f.get("systeme") or "all")[:40],
        "recherche": str(f.get("recherche") or "")[:120],
        "etat": str(f.get("etat") or "all")[:40],
        "avances": [str(x)[:40] for x in (f.get("avances") or [])
                    if isinstance(x, str)][:20],
    }
    return out


def liste():
    return _lire()["vues"]


def creer(nom, filtres):
    """Rend la vue creee, ou None si la limite est atteinte."""
    nom = (nom or "").strip()[:60] or "Sans nom"
    with _LOCK:
        d = _lire()
        if len(d["vues"]) >= MAX_VUES:
            return None
        vue = {"id": secrets.token_hex(8), "nom": nom,
               "filtres": _propre(filtres), "cree": int(time.time())}
        d["vues"].append(vue)
        _ecrire(d)
    return vue


def supprimer(vid):
    with _LOCK:
        d = _lire()
        restantes = [v for v in d["vues"] if v["id"] != vid]
        if len(restantes) == len(d["vues"]):
            return False
        d["vues"] = restantes
        _ecrire(d)
    return True
