"""Outgoing notifications: Discord, Slack, Telegram, ntfy, Gotify, webhook.

Romule could already tell you — but only the person sitting in front of it,
with a desktop notification. And what it does takes time: a thirty-file
conversion, a multi-gigabyte transfer. Those are precisely the moments when you
are NOT in front of the screen.

A word on the shape chosen. Comparable tools reach for Apprise, which can talk
to eighty services — and which is a dependency. Romule has none, and that rule
is not negotiable. So the five families that cover most self-hosted setups are
implemented here, plus a generic webhook for everything else, in about a
hundred lines of `urllib`.

The TYPE is worked out from the address. Asking the user to pick "Discord" from
a list after pasting a URL that starts with
`https://discord.com/api/webhooks/` would be making them retype what they just
gave. The field stays editable: the guess proposes, it does not impose.

This module never raises and never blocks. A notification is a CONVENIENCE: a
service that fails because Discord is down would be worse than silence.
"""

import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config, console, reseau

# The notifiable events. The label is what the user sees in the settings; the
# key is what gets stored in the configuration.
EVENEMENTS = {
    "tache_ok": "A task finished",
    "tache_echec": "A task failed",
    "console_liee": "The console connected or disconnected",
    "maj": "An update is available",
    "import": "Files were imported from the drop folder",
}

# Short timeout: a notification that drags would hold a thread for nothing.
DELAI = 10
# Past this, give up. An unreachable service usually stays unreachable, and
# retrying forever would turn a remote outage into a thread leak.
ESSAIS = 2

MAX_DESTINATIONS = 10

# One bounded pool: ten destinations that take ten seconds to answer must not
# open ten threads on every event.
_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="notif")


# --------------------------------------------------------------- guessing

def deviner(url):
    """The service this address points at, or `webhook` by default."""
    u = (url or "").strip().lower()
    hote = urllib.parse.urlparse(u).netloc
    if "discord.com" in hote or "discordapp.com" in hote:
        return "discord"
    if "hooks.slack.com" in hote:
        return "slack"
    if "api.telegram.org" in hote:
        return "telegram"
    # ntfy is self-hosted: the domain alone is not enough, but its path is
    # always a plain topic, with no extra segment.
    if "ntfy" in hote:
        return "ntfy"
    if "/message" in urllib.parse.urlparse(u).path and "token=" in (
            urllib.parse.urlparse(u).query or ""):
        return "gotify"
    return "webhook"


# --------------------------------------------------------------- composing

def _corps(service, titre, texte, niveau):
    """The (body, headers) pair this service expects.

    Each service has its own shape. Sending the same JSON everywhere would work
    for none of them: Discord wants `content`, Slack wants `text`, ntfy wants
    plain text with the title in a header.
    """
    plein = "%s\n%s" % (titre, texte) if texte else titre
    entetes = {"User-Agent": "romule"}
    if service == "discord":
        # A colour per severity: in a channel where thirty messages go by,
        # that is what tells "finished" from "failed" without reading.
        couleurs = {"ok": 0x2ECC71, "warn": 0xF1C40F, "error": 0xE74C3C,
                    "info": 0x95A5A6}
        d = {"embeds": [{"title": titre[:256], "description": texte[:4000],
                         "color": couleurs.get(niveau, couleurs["info"])}]}
        return json.dumps(d).encode(), dict(entetes, **{"Content-Type": "application/json"})
    if service == "slack":
        return (json.dumps({"text": plein[:3000]}).encode(),
                dict(entetes, **{"Content-Type": "application/json"}))
    if service == "telegram":
        # Telegram takes its parameters as a form; `chat_id` is already in the
        # URL the user supplied.
        return (urllib.parse.urlencode({"text": plein[:4000]}).encode(),
                dict(entetes, **{"Content-Type": "application/x-www-form-urlencoded"}))
    if service == "ntfy":
        # The title travels in a header, and must be latin-1: an accent or an
        # emoji in a game name would fail the whole send.
        return (texte.encode() or titre.encode(),
                dict(entetes, **{"Title": _ascii(titre), "Priority":
                                 {"error": "high", "warn": "default"}.get(niveau, "low")}))
    if service == "gotify":
        d = {"title": titre[:100], "message": texte[:2000],
             "priority": {"error": 8, "warn": 5}.get(niveau, 2)}
        return json.dumps(d).encode(), dict(entetes, **{"Content-Type": "application/json"})
    # Generic webhook: everything, in the open, so the far end can choose.
    d = {"service": "romule", "niveau": niveau, "titre": titre,
         "message": texte, "date": int(time.time())}
    return json.dumps(d).encode(), dict(entetes, **{"Content-Type": "application/json"})


def _ascii(texte):
    """An HTTP header carries no accents: `Title: Pokémon` breaks the send."""
    return (texte or "").encode("ascii", "replace").decode("ascii")


# --------------------------------------------------------------- sending

def _poster(url, donnees, entetes):
    """Returns (True, "") or (False, reason). Does not raise."""
    for essai in range(ESSAIS):
        try:
            req = urllib.request.Request(url, data=donnees, headers=entetes,
                                         method="POST")
            with reseau.ouvrir(req, timeout=DELAI) as r:
                return (200 <= r.status < 300), "HTTP %d" % r.status
        except reseau.SchemaRefuse as exc:
            return False, str(exc)          # no point retrying a `file://`
        except Exception as exc:
            dernier = "%s: %s" % (type(exc).__name__, exc)
            if essai + 1 < ESSAIS:
                time.sleep(1)
    return False, dernier


def destinations(cfg=None):
    """The saved destinations, sanitised."""
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
            # An empty list means EVERY event: that is what someone who
            # pastes an address without ticking anything expects.
            "evenements": evts or list(EVENEMENTS),
            "actif": d.get("actif", True) is not False,
        })
    return propres


SERVICES = ("discord", "slack", "telegram", "ntfy", "gotify", "webhook")


def envoyer(evenement, titre, texte="", niveau="info", cfg=None, attendre=False):
    """Tell the destinations subscribed to this event.

    Returns how many destinations were contacted. Sending is asynchronous by
    default: a task must not wait on a remote server to finish. `attendre=True`
    is for the "Test" button and for tests, where we want to know.
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
    # The ADDRESS is never logged: a Discord webhook is a secret — whoever
    # holds it can post in the channel. The name the user gave is enough to
    # know which one failed.
    nom = cible["nom"] or cible["service"]
    if reussi:
        console.evenement("Notification envoyee a %s" % nom, "debug", "notifs")
    else:
        console.evenement("Notification vers %s echouee (%s)" % (nom, raison),
                          "warn", "notifs")
    return reussi


def tester(url, service=None):
    """A trial send to ONE address, without saving it. Returns (ok, reason)."""
    service = service if service in SERVICES else deviner(url)
    donnees, entetes = _corps(
        service, "Romule", "Test notification — if you can read this, it works.",
        "ok")
    return _poster(url, donnees, entetes)
