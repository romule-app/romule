"""Cles d'API — des jetons nommes, revocables un par un.

Romule avait deja `ROMULE_TOKEN` : UN secret, tous les droits, qu'on ne peut ni
nommer ni revoquer sans le changer pour tout le monde. Il reste, parce qu'il
resout un autre probleme — ouvrir l'interface a un navigateur sans compte.

Une cle d'API resout celui-ci : donner a un tableau de bord, a un script de
sauvegarde ou a une tache planifiee un acces qu'on peut retirer a lui seul, et
dont on voit la derniere utilisation.

Trois choix qui ne vont pas de soi
----------------------------------

**Le prefixe `rml_` n'est pas decoratif.** Il rend une cle reconnaissable dans
un journal, un fichier de configuration ou un depot public. C'est ce qui permet
a un lecteur — humain ou automate — de dire « ceci est un secret » sans
connaitre Romule. GitHub et Stripe le font pour cette raison.

**SHA-256, et surtout pas `comptes.hacher()`.** Le projet hache les mots de
passe en scrypt N=2^17, soit environ 128 Mio de memoire par calcul. C'est voulu,
et c'est juste : un mot de passe est choisi par un humain, donc devinable, et il
faut rendre chaque essai couteux.

Une cle d'API n'est pas cela. C'est un secret ALEATOIRE de 256 bits : il n'y a
rien a deviner, et aucun cout de calcul n'ajoute de securite. En revanche une
cle est presentee a CHAQUE requete — un tableau de bord qui sonde toutes les
trente secondes ferait alors, a lui seul, 128 Mio d'allocation par sonde. Le
durcissement se retournerait en moyen de mettre le serveur a genoux.

**La recherche se fait par prefixe.** Comparer la cle presentee a toutes les
empreintes enregistrees couterait un parcours complet a chaque requete. Les
douze premiers caracteres identifient la cle ; l'empreinte, comparee en temps
constant, decide.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

from . import config

FICHIER = config.fichier_etat("_romule-cles.json", "_romule-cles.json")

# `rml_` + 43 caracteres base64url (32 octets). Le prefixe affiche couvre le
# marqueur et les huit premiers caracteres du secret : assez pour reconnaitre
# une cle dans une liste, trop peu pour la reconstruire.
MARQUEUR = "rml_"
_TAILLE = 32
_PREFIXE = 12

_LOCK = threading.RLock()


# ------------------------------------------------------------------ stockage

def _lire():
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "cles": []}
    if not isinstance(d, dict) or not isinstance(d.get("cles"), list):
        return {"version": 1, "cles": []}
    return d


def _ecrire(d):
    """Ecriture atomique en 0600, comme le fichier des comptes : une empreinte
    ne doit etre lisible que par le compte systeme qui fait tourner Romule."""
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FICHIER)


def _empreinte(cle):
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()


# -------------------------------------------------------------------- lecture

def _public(k):
    """Ce qu'on peut montrer. L'empreinte n'en fait pas partie : elle ne permet
    pas de retrouver la cle, mais elle permettrait de la VERIFIER hors ligne,
    donc de tester une liste de candidats sans passer par le serveur."""
    return {"id": k["id"], "nom": k["nom"], "prefixe": k["prefixe"],
            "cree": k["cree"], "dernier_usage": k.get("dernier_usage"),
            "revoquee": bool(k.get("revoquee"))}


def liste(avec_revoquees=False):
    cles = _lire()["cles"]
    return [_public(k) for k in cles
            if avec_revoquees or not k.get("revoquee")]


def nombre():
    return len([k for k in _lire()["cles"] if not k.get("revoquee")])


# -------------------------------------------------------------------- ecriture

def creer(nom):
    """Rend (fiche_publique, cle_en_clair).

    La cle en clair n'est rendue QU'ICI : elle n'est stockee nulle part, et
    l'appelant est le seul a pouvoir la montrer. C'est ce qui rend une fuite du
    fichier d'etat inoffensive pour les cles elles-memes.
    """
    nom = (nom or "").strip()[:60] or "sans nom"
    cle = MARQUEUR + secrets.token_urlsafe(_TAILLE)
    with _LOCK:
        d = _lire()
        fiche = {"id": secrets.token_hex(8),
                 "nom": nom,
                 "prefixe": cle[:_PREFIXE],
                 "empreinte": _empreinte(cle),
                 "cree": int(time.time()),
                 "dernier_usage": None,
                 "revoquee": False}
        d["cles"].append(fiche)
        _ecrire(d)
    return _public(fiche), cle


def revoquer(cid):
    """Revoque au lieu de supprimer : le nom et la date de derniere utilisation
    restent lisibles. « Cette cle a-t-elle servi apres que je l'ai retiree ? »
    est une question qu'on se pose apres coup, pas avant."""
    with _LOCK:
        d = _lire()
        for k in d["cles"]:
            if k["id"] == cid and not k.get("revoquee"):
                k["revoquee"] = True
                k["revoquee_le"] = int(time.time())
                _ecrire(d)
                return True
    return False


def renommer(cid, nom):
    nom = (nom or "").strip()[:60]
    if not nom:
        return False
    with _LOCK:
        d = _lire()
        for k in d["cles"]:
            if k["id"] == cid:
                k["nom"] = nom
                _ecrire(d)
                return True
    return False


# ---------------------------------------------------------------- verification

def verifier(presentee):
    """Rend la fiche publique si la cle est valide, sinon None.

    La date de derniere utilisation n'est ecrite qu'une fois par minute : sans
    cela, une sonde de tableau de bord reecrirait le fichier a chaque appel.
    """
    if not presentee or not isinstance(presentee, str):
        return None
    presentee = presentee.strip()
    if not presentee.startswith(MARQUEUR):
        return None
    prefixe = presentee[:_PREFIXE]
    emp = _empreinte(presentee)
    with _LOCK:
        d = _lire()
        for k in d["cles"]:
            if k.get("revoquee") or k.get("prefixe") != prefixe:
                continue
            # Temps constant : une comparaison ordinaire s'arrete au premier
            # caractere different, et le TEMPS de reponse dit alors combien de
            # caracteres etaient justes.
            if not hmac.compare_digest(k.get("empreinte", ""), emp):
                continue
            maintenant = int(time.time())
            if maintenant - (k.get("dernier_usage") or 0) >= 60:
                k["dernier_usage"] = maintenant
                try:
                    _ecrire(d)
                except OSError:
                    pass          # un disque plein ne doit pas fermer l'API
            return _public(k)
    return None
