"""What Romule writes to the TERMINAL, and nothing else.

The browser log and the terminal log answer two different questions. The first
tells a user what their library is doing right now; the second is how you work
out why a service will not start, on a machine where nobody can open a browser
— a container, a NAS, an ssh session. Until now only the first existed:
`JobRunner.log()` wrote to a file and to an in-memory buffer, never to standard
output. `docker logs romule` therefore showed almost nothing.

The style is chosen with `ROMULE_LOG`, and the default changes nothing about
what existed before:

    quiet     errors only
    normal    the banner, the startup facts, warnings and errors
    verbose   + every task event, timestamped and tagged
    debug     + the module, the thread, and seconds since startup
    json      one JSON line per event, for a log collector

`json` is not a whim: `docker logs | jq` is how you read a service you do not
administer by hand, and a coloured line there becomes a string of ANSI escapes.

Colour follows `NO_COLOR` (the convention, https://no-color.org) and switches
itself off outside a terminal: redirecting to a file must not fill it with
escape sequences.
"""

import json as _json
import os
import sys
import threading
import time

# Increasing order of severity. `debug` is the lowest: it only shows for the
# styles that ask for it.
LEVELS = ("debug", "info", "ok", "warn", "error")
_RANK = {n: i for i, n in enumerate(LEVELS)}

STYLES = ("quiet", "normal", "verbose", "debug", "json")

# Severity threshold shown, per style.
#
# `verbose` stops at `info` and NOT at `debug`, which is not a detail: the
# interface polls `/api/job` in a loop while a task runs, and requests are
# logged at `debug`. A `verbose` that showed them would bury the task events
# under dozens of lines a second — that is, make unreadable exactly what you
# opened it to read.
_THRESHOLD = {"quiet": _RANK["error"], "normal": _RANK["warn"],
          "verbose": _RANK["info"], "debug": _RANK["debug"],
          "json": _RANK["debug"]}

_C = {"debug": "\033[90m", "info": "\033[0m", "ok": "\033[32m",
      "warn": "\033[33m", "error": "\033[31m",
      "bold": "\033[1m", "gold": "\033[38;5;214m", "grey": "\033[90m",
      "reset": "\033[0m"}

START = time.monotonic()
_LOCK = threading.Lock()


def _requested_style():
    v = (os.environ.get("ROMULE_LOG") or os.environ.get("SWITCH_LOG") or "").strip().lower()
    if v in STYLES:
        return v
    # An obvious alias beats a refusal: `ROMULE_LOG=trace` clearly means
    # "as loud as you can".
    return {"trace": "debug", "silencieux": "quiet", "bavard": "verbose",
            "": "normal"}.get(v, "normal")


STYLE = _requested_style()


def _colour_possible():
    if os.environ.get("NO_COLOR") is not None:
        return False
    if STYLE == "json":
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


COLOUR = _colour_possible()


def reload_env():
    """Re-read the environment. For tests, which set the variable afterwards."""
    global STYLE, COLOUR
    STYLE = _requested_style()
    COLOUR = _colour_possible()
    return STYLE


def _c(text, what):
    return "%s%s%s" % (_C[what], text, _C["reset"]) if COLOUR else text


def shows(level):
    """Should this level show at the current style?"""
    return _RANK.get(level, _RANK["info"]) >= _THRESHOLD.get(STYLE, _THRESHOLD["normal"])


# `ROMULE` in block letters. A service starting up should name itself: in a
# log where ten containers write, this is the only marker that separates one
# startup from the next.
_BANNER = r"""
  ██████   ██████  ███    ███ ██    ██ ██      ███████
  ██   ██ ██    ██ ████  ████ ██    ██ ██      ██
  ██████  ██    ██ ██ ████ ██ ██    ██ ██      █████
  ██   ██ ██    ██ ██  ██  ██ ██    ██ ██      ██
  ██   ██  ██████  ██      ██  ██████  ███████ ███████
"""


def banner(facts):
    """The startup banner: the name, then the facts, aligned.

    `facts` is a list of (label, value) pairs. An empty value is not shown: a
    line reading "Console:" followed by nothing teaches less than its absence.
    """
    if STYLE == "json":
        event("demarrage", **{k.lower().replace(" ", "_"): v
                                  for k, v in facts if v})
        return
    if STYLE == "quiet":
        return
    sys.stdout.write(_c(_BANNER, "gold"))
    width = max((len(k) for k, v in facts if v), default=0)
    for key, value in facts:
        if not value:
            continue
        sys.stdout.write("  %s %s\n" % (_c((key + " ").ljust(width + 1) + ":", "grey"),
                                        value))
    sys.stdout.write("\n")
    sys.stdout.flush()


def event(message, level="info", module="", **fields):
    """One log line on standard output.

    Never raises: a service must not die because it could not complain. A
    closed output — an interrupted `docker logs`, a broken pipe — is the normal
    case, not a fault.
    """
    if not shows(level):
        return
    try:
        with _LOCK:
            if STYLE == "json":
                d = {"t": time.strftime("%FT%T"), "level": level,
                     "message": str(message)}
                if module:
                    d["module"] = module
                d.update(fields)
                sys.stdout.write(_json.dumps(d, ensure_ascii=False) + "\n")
            else:
                sys.stdout.write(_line(message, level, module, fields))
            sys.stdout.flush()
    except (OSError, ValueError):
        pass


_LABEL = {"debug": "DEBUG", "info": "INFO ", "ok": "OK   ",
              "warn": "WARN ", "error": "ERROR"}


def _line(message, level, module, fields):
    parts = [_c(time.strftime("%H:%M:%S"), "grey"),
             _c(_LABEL.get(level, "INFO "), level)]
    if STYLE == "debug":
        # Who spoke, from which thread, and at what second of the service's
        # life. The three answer different questions: "which module", "which
        # concurrent task", "before or after the scan".
        parts.append(_c("%7.2fs" % (time.monotonic() - START), "grey"))
        parts.append(_c("%-14s" % (module or "-")[:14], "grey"))
        parts.append(_c("%-12s" % threading.current_thread().name[:12], "grey"))
    line = " ".join(parts) + " " + str(message)
    if fields and STYLE == "debug":
        line += _c("  " + " ".join("%s=%s" % kv for kv in sorted(fields.items())),
                    "grey")
    return line + "\n"


def say(message, level="info", module=""):
    """A STARTUP fact: shown whatever the style, except in `quiet`.

    Distinct from `event()`, which obeys the severity threshold. "Library:
    /library" is neither a warning nor an error, yet it must appear in
    `normal` — it is in fact the first thing you read when working out why the
    service cannot find your games.
    """
    if STYLE == "quiet" and level != "error":
        return
    if STYLE == "json":
        event(message, level, module)
        return
    try:
        with _LOCK:
            sys.stdout.write(_line(message, level, module, {}))
            sys.stdout.flush()
    except (OSError, ValueError):
        pass
