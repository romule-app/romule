"""Ce que Romule ecrit dans le TERMINAL, et rien d'autre.

Le journal du navigateur et celui du terminal repondent a deux questions
differentes. Le premier dit a un utilisateur ce que sa ludotheque est en train
de faire ; le second sert a comprendre pourquoi un service ne demarre pas, sur
une machine ou personne ne peut ouvrir de navigateur — un conteneur, un NAS,
une session ssh. Jusqu'ici, seul le premier existait : `JobRunner.log()`
ecrivait dans un fichier et dans un tampon memoire, jamais sur la sortie
standard. `docker logs romule` ne montrait donc presque rien.

Le style se choisit par `ROMULE_LOG`, et le defaut ne change rien a ce qui
existait :

    quiet     les erreurs seules
    normal    le bandeau, les faits de demarrage, avertissements et erreurs
    verbose   + chaque evenement de tache, horodate et etiquete
    debug     + le module, le fil d'execution, et la duree depuis le demarrage
    json      une ligne JSON par evenement, pour un collecteur

`json` n'est pas un caprice : `docker logs | jq` est la facon dont on lit un
service qu'on n'administre pas a la main, et une ligne coloree y devient une
suite d'echappements ANSI.

La couleur suit `NO_COLOR` (la convention, https://no-color.org) et s'eteint
d'elle-meme hors d'un terminal : une redirection vers un fichier ne doit pas
le remplir de sequences d'echappement.
"""

import json as _json
import os
import sys
import threading
import time

# Ordre de gravite croissante. `debug` est le plus bas : il n'apparait qu'aux
# styles qui le demandent.
NIVEAUX = ("debug", "info", "ok", "warn", "error")
_RANG = {n: i for i, n in enumerate(NIVEAUX)}

STYLES = ("quiet", "normal", "verbose", "debug", "json")

# Seuil de gravite affiche, par style.
#
# `verbose` s'arrete a `info` et NON a `debug`, ce qui n'est pas un detail :
# l'interface interroge `/api/job` en boucle tant qu'une tache tourne, et les
# requetes sont journalisees en `debug`. Un `verbose` qui les montrerait noierait
# les evenements de tache sous des dizaines de lignes par seconde — c'est-a-dire
# rendrait illisible exactement ce qu'on est venu lire.
_SEUIL = {"quiet": _RANG["error"], "normal": _RANG["warn"],
          "verbose": _RANG["info"], "debug": _RANG["debug"],
          "json": _RANG["debug"]}

_C = {"debug": "\033[90m", "info": "\033[0m", "ok": "\033[32m",
      "warn": "\033[33m", "error": "\033[31m",
      "gras": "\033[1m", "or": "\033[38;5;214m", "gris": "\033[90m",
      "fin": "\033[0m"}

DEBUT = time.monotonic()
_VERROU = threading.Lock()


def _style_demande():
    v = (os.environ.get("ROMULE_LOG") or os.environ.get("SWITCH_LOG") or "").strip().lower()
    if v in STYLES:
        return v
    # Un alias evident vaut mieux qu'un refus : « ROMULE_LOG=trace » veut
    # visiblement dire « le plus bavard possible ».
    return {"trace": "debug", "silencieux": "quiet", "bavard": "verbose",
            "": "normal"}.get(v, "normal")


STYLE = _style_demande()


def _couleur_possible():
    if os.environ.get("NO_COLOR") is not None:
        return False
    if STYLE == "json":
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


COULEUR = _couleur_possible()


def relire():
    """Relit l'environnement. Sert aux tests, qui posent la variable apres coup."""
    global STYLE, COULEUR
    STYLE = _style_demande()
    COULEUR = _couleur_possible()
    return STYLE


def _c(texte, quoi):
    return "%s%s%s" % (_C[quoi], texte, _C["fin"]) if COULEUR else texte


def montre(niveau):
    """Ce niveau doit-il apparaitre au style courant ?"""
    return _RANG.get(niveau, _RANG["info"]) >= _SEUIL.get(STYLE, _SEUIL["normal"])


# `ROMULE` en lettres formees de blocs. Un service qui demarre doit se nommer :
# dans un journal ou dix conteneurs ecrivent, c'est le seul repere qui separe
# deux demarrages.
_BANNIERE = r"""
  ██████   ██████  ███    ███ ██    ██ ██      ███████
  ██   ██ ██    ██ ████  ████ ██    ██ ██      ██
  ██████  ██    ██ ██ ████ ██ ██    ██ ██      █████
  ██   ██ ██    ██ ██  ██  ██ ██    ██ ██      ██
  ██   ██  ██████  ██      ██  ██████  ███████ ███████
"""


def banniere(faits):
    """Le bandeau de demarrage : le nom, puis les faits, alignes.

    `faits` est une liste de couples (libelle, valeur). Une valeur vide n'est
    pas affichee : une ligne « Console : » suivie de rien apprend moins que son
    absence.
    """
    if STYLE == "json":
        evenement("demarrage", **{k.lower().replace(" ", "_"): v
                                  for k, v in faits if v})
        return
    if STYLE == "quiet":
        return
    sys.stdout.write(_c(_BANNIERE, "or"))
    large = max((len(k) for k, v in faits if v), default=0)
    for cle, valeur in faits:
        if not valeur:
            continue
        sys.stdout.write("  %s %s\n" % (_c((cle + " ").ljust(large + 1) + ":", "gris"),
                                        valeur))
    sys.stdout.write("\n")
    sys.stdout.flush()


def evenement(message, niveau="info", module="", **champs):
    """Une ligne de journal sur la sortie standard.

    Ne leve jamais : un service ne doit pas mourir parce qu'il n'a pas pu se
    plaindre. Une sortie fermee — un `docker logs` interrompu, un tube casse —
    est le cas normal, pas une panne.
    """
    if not montre(niveau):
        return
    try:
        with _VERROU:
            if STYLE == "json":
                d = {"t": time.strftime("%FT%T"), "niveau": niveau,
                     "message": str(message)}
                if module:
                    d["module"] = module
                d.update(champs)
                sys.stdout.write(_json.dumps(d, ensure_ascii=False) + "\n")
            else:
                sys.stdout.write(_ligne(message, niveau, module, champs))
            sys.stdout.flush()
    except (OSError, ValueError):
        pass


_ETIQUETTE = {"debug": "DEBUG", "info": "INFO ", "ok": "OK   ",
              "warn": "WARN ", "error": "ERROR"}


def _ligne(message, niveau, module, champs):
    bouts = [_c(time.strftime("%H:%M:%S"), "gris"),
             _c(_ETIQUETTE.get(niveau, "INFO "), niveau)]
    if STYLE == "debug":
        # Qui a parle, depuis quel fil, et a quelle seconde de vie du service.
        # Les trois repondent a des questions differentes : « quel module »,
        # « quelle tache concurrente », « avant ou apres le scan ».
        bouts.append(_c("%7.2fs" % (time.monotonic() - DEBUT), "gris"))
        bouts.append(_c("%-14s" % (module or "-")[:14], "gris"))
        bouts.append(_c("%-12s" % threading.current_thread().name[:12], "gris"))
    ligne = " ".join(bouts) + " " + str(message)
    if champs and STYLE == "debug":
        ligne += _c("  " + " ".join("%s=%s" % kv for kv in sorted(champs.items())),
                    "gris")
    return ligne + "\n"


def dit(message, niveau="info", module=""):
    """Un fait de DEMARRAGE : montre quel que soit le style, sauf en `quiet`.

    Distinct d'`evenement()`, qui obeit au seuil de gravite. « Ludotheque :
    /library » n'est ni un avertissement ni une erreur, et doit pourtant
    apparaitre en `normal` — c'est meme la premiere chose qu'on lit quand on
    cherche pourquoi le service ne trouve pas les jeux.
    """
    if STYLE == "quiet" and niveau != "error":
        return
    if STYLE == "json":
        evenement(message, niveau, module)
        return
    try:
        with _VERROU:
            sys.stdout.write(_ligne(message, niveau, module, {}))
            sys.stdout.flush()
    except (OSError, ValueError):
        pass
