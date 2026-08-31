"""Navigation dans les dossiers de la machine qui heberge le service.

Pourquoi ce module existe : jusqu'ici le dossier des jeux ne pouvait etre
designe que par une variable d'environnement. Sur un NAS, cela veut dire
ouvrir un terminal, editer un fichier compose et redemarrer un conteneur —
pour une information que l'interface est le seul endroit naturel ou saisir.

Un navigateur de fichiers dans un service reseau est une primitive sensible :
il revele l'arborescence de la machine. Trois choses le tiennent.

1. Il est reserve a l'administrateur (`RESERVE_ADMIN` dans server.py).
2. Il ne liste que des DOSSIERS. Le contenu des fichiers, leurs noms meme, ne
   sortent pas d'ici — seul un comptage des jeux reconnus est renvoye, parce
   que c'est ce qui permet a l'utilisateur de reconnaitre sa ludotheque.
3. `ROMULE_BASES` permet de confiner la navigation a une liste de dossiers.

Ce dernier point demande une explication, parce que le defaut peut surprendre :
`ROMULE_BASES` n'est PAS posee par defaut. C'est le choix que font Jellyfin,
Sonarr ou qBittorrent, et il n'est pas un relachement — c'est la reconnaissance
de qui tient reellement la frontiere :

  * en conteneur, le processus ne voit que ce qui est monte. Le `volumes:` du
    fichier compose EST la liste blanche, et elle est appliquee par le noyau
    plutot que par du code applicatif ;
  * en natif, la frontiere est le compte Unix qui fait tourner le service.

Une liste blanche applicative par-dessus donnerait surtout l'illusion d'une
protection. `ROMULE_BASES` reste disponible pour qui installe en natif sous un
compte large et veut se restreindre malgre tout.
"""

import os
from pathlib import Path

from . import config, systems

# `BASES` et le controle d'appartenance vivent dans `config` : la meme regle
# doit valoir pour ce qu'on PARCOURT et pour ce qu'on CHOISIT.
BASES = config.BASES
autorise = config.dans_les_bases

# Plafonds du comptage. Un dossier peut contenir un million de fichiers, et
# l'utilisateur attend une reponse pendant que la fenetre est ouverte.
PROFONDEUR = 3
PLAFOND = 20000


def _extensions(cfg=None):
    """Toutes les extensions reconnues, Switch et plateformes retro.

    `cfg` est passe par l'appelant quand il l'a deja : sans lui,
    `systems.liste()` relit le fichier de configuration a chaque clic dans la
    fenetre de navigation.
    """
    exts = set(config.EXTS)
    for s in systems.liste(cfg):
        exts.update(e.lower() for e in s.get("exts", []))
    return exts


def compter_jeux(dossier, exts=None, cfg=None):
    """Nombre de fichiers reconnus sous ce dossier, borne en profondeur.

    Borne, et pas exact : ce chiffre sert a repondre « oui, c'est bien ma
    ludotheque », pas a inventorier. Le rendre exact couterait une traversee
    complete a chaque clic dans la fenetre.
    """
    exts = exts if exts is not None else _extensions(cfg)
    vus = 0
    trouves = 0
    piles = [(Path(dossier), 0)]
    while piles:
        d, prof = piles.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    vus += 1
                    if vus > PLAFOND:
                        return trouves
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if prof < PROFONDEUR and e.name not in config.IGNORE_DIRS:
                                piles.append((Path(e.path), prof + 1))
                        elif os.path.splitext(e.name)[1].lower() in exts:
                            trouves += 1
                    except OSError:
                        continue
        except (OSError, ValueError):
            continue
    return trouves


def lister(chemin="", cfg=None):
    """Sous-dossiers d'un chemin. Renvoie un dict, ou {"error": ...}."""
    brut = str(chemin or "").strip()
    # Point de depart : la ludotheque courante. Mais elle peut se trouver HORS
    # des bases declarees — c'est meme le cas normal d'un conteneur qui range
    # ses donnees dans un volume et borne la navigation au montage des jeux.
    # Sans ce repli, ouvrir la fenetre repondait « chemin hors des dossiers
    # autorises » a quelqu'un qui n'avait encore rien demande.
    depart = config.LUDO
    if not config.dans_les_bases(depart) and config.BASES:
        depart = config.BASES[0]
    cible = Path(brut).expanduser() if brut else depart
    try:
        cible = cible.resolve()
    except OSError as exc:
        return {"error": "chemin illisible : %s" % exc}
    if not autorise(cible):
        # Volontairement avare : confirmer l'existence d'un chemin hors des
        # bases serait deja repondre a la question qu'on refuse.
        return {"error": "chemin hors des dossiers autorises"}
    if not cible.is_dir():
        return {"error": "ce dossier n'existe pas"}

    dossiers = []
    try:
        with os.scandir(cible) as it:
            for e in it:
                try:
                    if not e.is_dir():          # suit les liens : un lien vers
                        continue                # un dossier reste un dossier
                except OSError:
                    continue
                p = Path(e.path)
                if not autorise(p):
                    continue
                dossiers.append({
                    "nom": e.name,
                    "chemin": str(p),
                    "cache": e.name.startswith("."),
                    "lisible": os.access(p, os.R_OK | os.X_OK),
                })
    except PermissionError:
        return {"error": "lecture refusee sur ce dossier"}
    except OSError as exc:
        return {"error": "lecture impossible : %s" % exc}
    dossiers.sort(key=lambda d: d["nom"].lower())

    parent = cible.parent
    return {
        "chemin": str(cible),
        # Pas de parent hors des bases : la fenetre ne doit pas proposer un
        # bouton qui repondra « refuse ».
        "parent": str(parent) if parent != cible and autorise(parent) else "",
        "dossiers": dossiers,
        "ecrivable": os.access(cible, os.W_OK),
        "jeux": compter_jeux(cible, cfg=cfg),
        "douteux": config.racine_douteuse(cible),
        "raccourcis": raccourcis(),
    }


def raccourcis():
    """Points de depart proposes dans la fenetre."""
    vus = set()
    out = []
    for libelle, p in (("Ludothèque actuelle", config.LUDO),
                       ("Données du service", config.ROOT),
                       ("Dossier personnel", Path.home()),
                       ("Racine", Path(Path.cwd().anchor or "/"))):
        try:
            p = Path(p).resolve()
        except OSError:
            continue
        if str(p) in vus or not p.is_dir() or not autorise(p):
            continue
        vus.add(str(p))
        out.append({"nom": libelle, "chemin": str(p)})
    # Les bases declarees sont, par definition, les endroits ou aller.
    for b in BASES:
        if str(b) not in vus and b.is_dir():
            vus.add(str(b))
            out.append({"nom": b.name or str(b), "chemin": str(b)})
    return out
