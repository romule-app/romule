"""Journal des acces, ecrit sur disque.

Le journal de l'interface vit en memoire : un redemarrage efface la trace des
tentatives de connexion. Or c'est precisement ce qu'on veut relire apres coup,
quand on se demande si quelqu'un a essaye d'entrer.

Format : une ligne JSON par evenement (JSONL), en 0600, avec rotation par
taille. Rien d'autre n'est conserve — ni mot de passe, ni cookie, ni jeton :
un journal qui contient des secrets devient lui-meme un secret a proteger.
"""

import json
import os
import time

from . import config

FICHIER = config.fichier_etat("_romule-acces.log", "_switch-acces.log")
TAILLE_MAX = 1 << 20            # 1 Mio, puis rotation
ARCHIVES = 3


def _tourner():
    try:
        if FICHIER.exists() and FICHIER.stat().st_size > TAILLE_MAX:
            for i in range(ARCHIVES - 1, 0, -1):
                vieux = FICHIER.with_suffix(".log.%d" % i)
                if vieux.exists():
                    vieux.replace(FICHIER.with_suffix(".log.%d" % (i + 1)))
            FICHIER.replace(FICHIER.with_suffix(".log.1"))
    except OSError:
        pass


def noter(evenement, ip="", email="", detail=""):
    """Enregistre un evenement d'acces. Ne leve jamais : un journal qui casse
    l'authentification serait pire que pas de journal."""
    try:
        _tourner()
        ligne = json.dumps({
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "e": evenement,               # connexion | refus | deconnexion | compte
            "ip": str(ip or "")[:45],
            "email": str(email or "")[:120],
            "detail": str(detail or "")[:200],
        }, ensure_ascii=False)
        neuf = not FICHIER.exists()
        with FICHIER.open("a", encoding="utf-8") as f:
            f.write(ligne + "\n")
        if neuf:
            os.chmod(FICHIER, 0o600)
    except Exception:
        pass


def dernieres(n=200):
    """Les n derniers evenements, du plus recent au plus ancien."""
    try:
        lignes = FICHIER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for l in reversed(lignes[-n:]):
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def resume():
    """De quoi repondre a « est-ce que quelqu'un a essaye d'entrer ? »."""
    ev = dernieres(500)
    refus = [e for e in ev if e.get("e") == "refus"]
    return {
        "evenements": len(ev),
        "refus": len(refus),
        "derniers_refus": refus[:5],
        "derniere_connexion": next((e for e in ev if e.get("e") == "connexion"), None),
    }
