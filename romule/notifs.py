"""Notifications sortantes : Discord, Slack, Telegram, ntfy, Gotify, webhook.

Romule savait deja prevenir — mais seulement la personne assise devant lui, par
une notification de bureau. Or ce qu'il fait dure : une conversion de trente
fichiers, un transfert de plusieurs gigaoctets. Ce sont precisement les moments
ou l'on n'est PAS devant l'ecran.

Un mot sur la forme choisie. Les outils comparables passent par Apprise, qui
sait parler a quatre-vingts services — et qui est une dependance. Romule n'en a
aucune, et cette regle n'est pas negociable. On implemente donc les cinq
familles qui couvrent l'essentiel des installations auto-hebergees, plus un
webhook generique pour tout le reste, en une centaine de lignes de `urllib`.

Le TYPE est deduit de l'adresse. Demander a l'utilisateur de choisir « Discord »
dans une liste apres avoir colle une URL qui commence par
`https://discord.com/api/webhooks/` serait lui faire ressaisir ce qu'il vient de
donner. Le champ reste modifiable : la deduction propose, elle n'impose pas.

Ce module ne leve jamais et ne bloque jamais. Une notification est un CONFORT :
un service qui echoue parce que Discord est en panne serait pire que le silence.
"""

import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config, console, reseau

# Les evenements notifiables. Le libelle est ce que voit l'utilisateur dans les
# reglages ; la cle est ce qui est range dans la configuration.
EVENEMENTS = {
    "tache_ok": "A task finished",
    "tache_echec": "A task failed",
    "console_liee": "The console connected or disconnected",
    "maj": "An update is available",
    "import": "Files were imported from the drop folder",
}

# Delai court : une notification qui traine retiendrait un fil pour rien.
DELAI = 10
# Au-dela, on renonce. Un service injoignable le reste generalement, et
# reessayer indefiniment transformerait une panne distante en fuite de fils.
ESSAIS = 2

MAX_DESTINATIONS = 10

# Un seul pool, borne : dix destinations qui repondent en dix secondes ne
# doivent pas ouvrir dix fils a chaque evenement.
_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="notif")


# --------------------------------------------------------------- deduction

def deviner(url):
    """Le service que designe cette adresse, ou `webhook` par defaut."""
    u = (url or "").strip().lower()
    hote = urllib.parse.urlparse(u).netloc
    if "discord.com" in hote or "discordapp.com" in hote:
        return "discord"
    if "hooks.slack.com" in hote:
        return "slack"
    if "api.telegram.org" in hote:
        return "telegram"
    # ntfy s'auto-heberge : le domaine ne suffit pas, mais son chemin est
    # toujours un simple sujet, sans segment supplementaire.
    if "ntfy" in hote:
        return "ntfy"
    if "/message" in urllib.parse.urlparse(u).path and "token=" in (
            urllib.parse.urlparse(u).query or ""):
        return "gotify"
    return "webhook"


# --------------------------------------------------------------- redaction

def _corps(service, titre, texte, niveau):
    """Le couple (donnees, en-tetes) attendu par ce service.

    Chaque service a sa forme. Envoyer partout le meme JSON marcherait pour
    aucun d'eux : Discord veut `content`, Slack veut `text`, ntfy veut du texte
    brut avec le titre en en-tete.
    """
    plein = "%s\n%s" % (titre, texte) if texte else titre
    entetes = {"User-Agent": "romule"}
    if service == "discord":
        # Une couleur par gravite : dans un salon ou passent trente messages,
        # c'est ce qui distingue « termine » de « echoue » sans lire.
        couleurs = {"ok": 0x2ECC71, "warn": 0xF1C40F, "error": 0xE74C3C,
                    "info": 0x95A5A6}
        d = {"embeds": [{"title": titre[:256], "description": texte[:4000],
                         "color": couleurs.get(niveau, couleurs["info"])}]}
        return json.dumps(d).encode(), dict(entetes, **{"Content-Type": "application/json"})
    if service == "slack":
        return (json.dumps({"text": plein[:3000]}).encode(),
                dict(entetes, **{"Content-Type": "application/json"}))
    if service == "telegram":
        # Telegram prend ses parametres en formulaire ; `chat_id` est deja dans
        # l'URL fournie par l'utilisateur.
        return (urllib.parse.urlencode({"text": plein[:4000]}).encode(),
                dict(entetes, **{"Content-Type": "application/x-www-form-urlencoded"}))
    if service == "ntfy":
        # Le titre passe en en-tete, et il doit etre en latin-1 : un accent ou
        # un emoji dans un nom de jeu ferait echouer l'envoi entier.
        return (texte.encode() or titre.encode(),
                dict(entetes, **{"Title": _ascii(titre), "Priority":
                                 {"error": "high", "warn": "default"}.get(niveau, "low")}))
    if service == "gotify":
        d = {"title": titre[:100], "message": texte[:2000],
             "priority": {"error": 8, "warn": 5}.get(niveau, 2)}
        return json.dumps(d).encode(), dict(entetes, **{"Content-Type": "application/json"})
    # Webhook generique : tout, en clair, pour que l'autre bout choisisse.
    d = {"service": "romule", "niveau": niveau, "titre": titre,
         "message": texte, "date": int(time.time())}
    return json.dumps(d).encode(), dict(entetes, **{"Content-Type": "application/json"})


def _ascii(texte):
    """Un en-tete HTTP ne porte pas d'accent : `Titre: Pokémon` casse l'envoi."""
    return (texte or "").encode("ascii", "replace").decode("ascii")


# --------------------------------------------------------------- envoi

def _poster(url, donnees, entetes):
    """Rend (True, "") ou (False, raison). Ne leve pas."""
    for essai in range(ESSAIS):
        try:
            req = urllib.request.Request(url, data=donnees, headers=entetes,
                                         method="POST")
            with reseau.ouvrir(req, timeout=DELAI) as r:
                return (200 <= r.status < 300), "HTTP %d" % r.status
        except reseau.SchemaRefuse as exc:
            return False, str(exc)          # inutile de reessayer un `file://`
        except Exception as exc:
            dernier = "%s: %s" % (type(exc).__name__, exc)
            if essai + 1 < ESSAIS:
                time.sleep(1)
    return False, dernier


def destinations(cfg=None):
    """Les destinations enregistrees, assainies."""
    cfg = cfg if cfg is not None else config.load_config()
    propres = []
    for d in (cfg.get("notif_destinations") or [])[:MAX_DESTINATIONS]:
        if not isinstance(d, dict):
            continue
        url = str(d.get("url") or "").strip()
        if not url:
            continue
        evts = [e for e in (d.get("evenements") or []) if e in EVENEMENTS]
        propres.append({
            "id": str(d.get("id") or "")[:32],
            "nom": str(d.get("nom") or "")[:60],
            "url": url,
            "service": d.get("service") if d.get("service") in SERVICES
                       else deviner(url),
            # Une liste vide veut dire TOUS les evenements : c'est ce qu'attend
            # quelqu'un qui colle une adresse sans rien cocher.
            "evenements": evts or list(EVENEMENTS),
            "actif": d.get("actif", True) is not False,
        })
    return propres


SERVICES = ("discord", "slack", "telegram", "ntfy", "gotify", "webhook")


def envoyer(evenement, titre, texte="", niveau="info", cfg=None, attendre=False):
    """Previent les destinations abonnees a cet evenement.

    Rend le nombre de destinations sollicitees. L'envoi est asynchrone par
    defaut : une tache ne doit pas attendre un serveur distant pour se terminer.
    `attendre=True` sert au bouton « Tester » et aux tests, ou l'on veut savoir.
    """
    cibles = [d for d in destinations(cfg)
              if d["actif"] and evenement in d["evenements"]]
    if not cibles:
        return 0
    for cible in cibles:
        donnees, entetes = _corps(cible["service"], titre, texte, niveau)
        if attendre:
            _tenter(cible, donnees, entetes)
        else:
            _POOL.submit(_tenter, cible, donnees, entetes)
    return len(cibles)


def _tenter(cible, donnees, entetes):
    reussi, raison = _poster(cible["url"], donnees, entetes)
    # L'ADRESSE n'est jamais journalisee : un webhook Discord est un secret —
    # qui l'a peut ecrire dans le salon. Le nom donne par l'utilisateur suffit
    # a savoir laquelle a echoue.
    nom = cible["nom"] or cible["service"]
    if reussi:
        console.evenement("Notification envoyee a %s" % nom, "debug", "notifs")
    else:
        console.evenement("Notification vers %s echouee (%s)" % (nom, raison),
                          "warn", "notifs")
    return reussi


def tester(url, service=None):
    """Envoi d'essai vers UNE adresse, sans l'enregistrer. Rend (ok, raison)."""
    service = service if service in SERVICES else deviner(url)
    donnees, entetes = _corps(
        service, "Romule", "Test notification — if you can read this, it works.",
        "ok")
    return _poster(url, donnees, entetes)
