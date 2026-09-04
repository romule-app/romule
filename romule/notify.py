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

from . import config, console, net

# The notifiable events. The label is what the user sees in the settings; the
# key is what gets STORED in each destination, so a key never changes name —
# renaming one would silently unsubscribe everybody who had ticked it.
#
# Two kinds, and the distinction is the whole design:
#
#   * the two CATCH-ALLS, `tache_ok` and `tache_echec`, which say "any task,
#     this outcome". Someone who wants to hear about everything ticks one box,
#     not seven;
#   * the SPECIFIC ones, which fire for one kind of work whatever its outcome.
#     Someone who only cares that a 12 GB transfer is over does not want to be
#     told about every cover refresh.
#
# An occurrence satisfies a specific event AND its catch-all, and a destination
# receives ONE message however many of its ticked boxes match. See `_names()`.
# The LABELS are French because they are catalogue keys, like every other
# sentence the interface shows: `fr.json` maps each to itself and `en.json`
# translates it. That is the i18n mechanism, not a style — and until these
# events had checkboxes, nothing displayed them, so nothing noticed they were
# English and therefore untranslatable.
EVENTS = {
    "tache_ok": "Une tâche s'est terminée",
    "tache_echec": "Une tâche a échoué",
    "envoi": "Un envoi vers la console s'est terminé",
    "conversion": "Une conversion s'est terminée",
    "import": "Le dépôt a été rangé",
    "fiches": "Les fiches ont été rafraîchies",
    "verification": "Une vérification d'intégrité s'est terminée",
    "console_liee": "La console s'est connectée ou déconnectée",
    "maj": "Une version plus récente existe",
}

# Which task produces which specific event. The key is the label `JobRunner`
# gives a task, which is the Python function's own name — the same coupling
# `test_ui_injection.js` guards for the interface's task names.
TASK_EVENTS = {
    "push_files": "envoi",
    "push_system": "envoi",
    "deploy_games": "envoi",
    "import_from_device": "envoi",
    "convert_files": "conversion",
    "import_files": "import",
    "import_system_files": "import",
    "sync_meta": "fiches",
    "verify_library": "verification",
}

# A specific event also satisfies its catch-all, by outcome.
CATCH_ALL = {"ok": "tache_ok", "error": "tache_echec", "warn": "tache_echec"}


def _names(event, level="info"):
    """Every event name this occurrence satisfies.

    A successful push satisfies `envoi` and `tache_ok`; a failed one satisfies
    `envoi` and `tache_echec`. The specific event fires on BOTH outcomes,
    because someone watching for the end of a transfer wants to hear about it
    either way — the level says which.
    """
    out = {event}
    if event in ("tache_ok", "tache_echec"):
        return out
    catch = CATCH_ALL.get(level)
    if catch and event in TASK_EVENTS.values():
        out.add(catch)
    return out

# Short timeout: a notification that drags would hold a thread for nothing.
TIMEOUT = 10
# Past this, give up. An unreachable service usually stays unreachable, and
# retrying forever would turn a remote outage into a thread leak.
ATTEMPTS = 2

MAX_DESTINATIONS = 10

# One bounded pool: ten destinations that take ten seconds to answer must not
# open ten threads on every event.
_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="notif")


# --------------------------------------------------------------- guessing

def guess(url):
    """The service this address points at, or `webhook` by default."""
    u = (url or "").strip().lower()
    host = urllib.parse.urlparse(u).netloc
    if "discord.com" in host or "discordapp.com" in host:
        return "discord"
    if "hooks.slack.com" in host:
        return "slack"
    if "api.telegram.org" in host:
        return "telegram"
    # ntfy is self-hosted: the domain alone is not enough, but its path is
    # always a plain topic, with no extra segment.
    if "ntfy" in host:
        return "ntfy"
    if "/message" in urllib.parse.urlparse(u).path and "token=" in (
            urllib.parse.urlparse(u).query or ""):
        return "gotify"
    return "webhook"


# --------------------------------------------------------------- composing

def _body(service, title, text, level):
    """The (body, headers) pair this service expects.

    Each service has its own shape. Sending the same JSON everywhere would work
    for none of them: Discord wants `content`, Slack wants `text`, ntfy wants
    plain text with the title in a header.
    """
    full = "%s\n%s" % (title, text) if text else title
    headers = {"User-Agent": "romule"}
    if service == "discord":
        # A colour per severity: in a channel where thirty messages go by,
        # that is what tells "finished" from "failed" without reading.
        colours = {"ok": 0x2ECC71, "warn": 0xF1C40F, "error": 0xE74C3C,
                    "info": 0x95A5A6}
        d = {"embeds": [{"title": title[:256], "description": text[:4000],
                         "color": colours.get(level, colours["info"])}]}
        return json.dumps(d).encode(), dict(headers, **{"Content-Type": "application/json"})
    if service == "slack":
        return (json.dumps({"text": full[:3000]}).encode(),
                dict(headers, **{"Content-Type": "application/json"}))
    if service == "telegram":
        # Telegram takes its parameters as a form; `chat_id` is already in the
        # URL the user supplied.
        return (urllib.parse.urlencode({"text": full[:4000]}).encode(),
                dict(headers, **{"Content-Type": "application/x-www-form-urlencoded"}))
    if service == "ntfy":
        # The title travels in a header, and must be latin-1: an accent or an
        # emoji in a game name would fail the whole send.
        return (text.encode() or title.encode(),
                dict(headers, **{"Title": _ascii(title), "Priority":
                                 {"error": "high", "warn": "default"}.get(level, "low")}))
    if service == "gotify":
        d = {"title": title[:100], "message": text[:2000],
             "priority": {"error": 8, "warn": 5}.get(level, 2)}
        return json.dumps(d).encode(), dict(headers, **{"Content-Type": "application/json"})
    # Generic webhook: everything, in the open, so the far end can choose.
    d = {"service": "romule", "level": level, "title": title,
         "message": text, "date": int(time.time())}
    return json.dumps(d).encode(), dict(headers, **{"Content-Type": "application/json"})


def _ascii(text):
    """An HTTP header carries no accents: `Title: Pokémon` breaks the send."""
    return (text or "").encode("ascii", "replace").decode("ascii")


# --------------------------------------------------------------- sending

def _post(url, data, headers):
    """Returns (True, "") or (False, reason). Does not raise."""
    for attempt in range(ATTEMPTS):
        try:
            req = urllib.request.Request(url, data=data, headers=headers,
                                         method="POST")
            with net.open_url(req, timeout=TIMEOUT) as r:
                return (200 <= r.status < 300), "HTTP %d" % r.status
        except net.SchemeRefused as exc:
            return False, str(exc)          # no point retrying a `file://`
        except Exception as exc:
            last = "%s: %s" % (type(exc).__name__, exc)
            if attempt + 1 < ATTEMPTS:
                time.sleep(1)
    return False, last


def destinations(cfg=None):
    """The saved destinations, sanitised."""
    cfg = cfg if cfg is not None else config.load_config()
    clean = []
    for d in (cfg.get("notif_destinations") or [])[:MAX_DESTINATIONS]:
        if not isinstance(d, dict):
            continue
        url = str(d.get("url") or "").strip()
        if not url:
            continue
        kept_events = [e for e in (d.get("evenements") or []) if e in EVENTS]
        # The keys below are DATA: they are already in `notif_destinations` on
        # every installation, and the interface reads them by name. Only the
        # identifiers around them are English.
        clean.append({
            "id": str(d.get("id") or "")[:32],
            "nom": str(d.get("nom") or "")[:60],
            "url": url,
            "service": d.get("service") if d.get("service") in SERVICES
                       else guess(url),
            # An empty list means EVERY event: that is what someone who
            # pastes an address without ticking anything expects.
            "evenements": kept_events or list(EVENTS),
            "actif": d.get("actif", True) is not False,
        })
    return clean


SERVICES = ("discord", "slack", "telegram", "ntfy", "gotify", "webhook")


def send(event, title, text="", level="info", cfg=None, wait=False):
    """Tell the destinations subscribed to this event.

    Returns how many destinations were contacted. Sending is asynchronous by
    default: a task must not wait on a remote server to finish. `wait=True`
    is for the "Test" button and for tests, where we want to know.
    """
    # ONE message per destination, however many of its ticked boxes match: a
    # destination subscribed to both `envoi` and `tache_ok` must not be told
    # twice about the same transfer.
    satisfait = _names(event, level)
    targets = [d for d in destinations(cfg)
               if d["actif"] and satisfait & set(d["evenements"])]
    if not targets:
        return 0
    for target in targets:
        data, headers = _body(target["service"], title, text, level)
        if wait:
            _attempt(target, data, headers)
        else:
            _POOL.submit(_attempt, target, data, headers)
    return len(targets)


def _attempt(target, data, headers):
    sent, reason = _post(target["url"], data, headers)
    # The ADDRESS is never logged: a Discord webhook is a secret — whoever
    # holds it can post in the channel. The name the user gave is enough to
    # know which one failed.
    name = target["nom"] or target["service"]
    if sent:
        console.event("Notification envoyee a %s" % name, "debug", "notify")
    else:
        console.event("Notification vers %s echouee (%s)" % (name, reason),
                      "warn", "notify")
    return sent


def probe(url, service=None):
    """A trial send to ONE address, without saving it. Returns (ok, reason)."""
    service = service if service in SERVICES else guess(url)
    data, headers = _body(
        service, "Romule", "Test notification — if you can read this, it works.",
        "ok")
    return _post(url, data, headers)
