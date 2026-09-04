"""Running a single background task, with a log and progress.

One task at a time (conversion, import, transfer). The interface polls
`snapshot()` in a loop to show the log and the progress bar.
"""

import os
import shutil
import subprocess
import threading
from datetime import datetime

from . import console

# Log: we write on every event (a message lost in a crash is worth nothing),
# and rotate the file by size — standard practice, better than a periodic
# flush.
MAX_BYTES = 2 * 1024 * 1024
KEEP = 3
LEVELS = ("debug", "info", "ok", "warn", "error")


def _rotate(path):
    try:
        if os.path.getsize(path) < MAX_BYTES:
            return
    except OSError:
        return
    for i in range(KEEP - 1, 0, -1):
        vieux, neuf = "%s.%d" % (path, i), "%s.%d" % (path, i + 1)
        if os.path.exists(vieux):
            os.replace(vieux, neuf)
    try:
        os.replace(path, "%s.1" % path)
    except OSError:
        pass


def _guess_level(text):
    """Infer the severity of a message that does not state one."""
    t = text.lower()
    if any(m in t for m in ("erreur", "echec", "impossible", "invalide", "corrompu",
                            "introuvable", "[erreur]")):
        return "error"
    if any(m in t for m in ("ignore", "attention", "aucun", "non connect", "interrompu",
                            "deja present", "exclu")):
        return "warn"
    if any(m in t for m in ("ok ", "termine", "installe", "range", "applique",
                            "enregistre", "recu")):
        return "ok"
    return "info"


def desktop_notify(message, title="Romule"):
    """The macOS end-of-task notification (ignored elsewhere).

    Named apart from the `notify` MODULE on purpose. While they shared a name,
    the `from . import notify` twenty lines below made `notify` a local for the
    whole of `wrap()`, and this call — which comes before it — raised
    `UnboundLocalError` inside the thread that finishes every task. Nothing
    caught it: the `except` sits after the line that failed.
    """
    if not shutil.which("osascript"):
        return
    safe = message.replace('"', "'")[:200]
    try:
        subprocess.run(["osascript", "-e",
                        'display notification "%s" with title "%s"' % (safe, title)],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


class JobRunner:
    def __init__(self, logfile=None):
        self._lock = threading.Lock()
        self._resume = threading.Event()
        self._resume.set()
        self.running = False
        self.paused = False
        self.cancelled = False
        self.label = ""
        self.log_lines = []
        self.done = 0
        self.total = 0
        self.detail = ""       # rate / ETA / free-form info shown in the dock
        self.logfile = logfile
        self.notify_end = True
        # Name shown in `ROMULE_LOG=debug` beside every line. It follows the
        # running task: "which module wrote this" is the first question you ask
        # in front of a chatty log.
        self.module = "job"

    def log(self, line, level=None):
        """Log an event. The level is inferred when not given."""
        level = level if level in LEVELS else _guess_level(str(line))
        entree = {"t": datetime.now().strftime("%H:%M:%S"),
                  "date": datetime.now().strftime("%F"),
                  "n": level, "m": str(line)}
        with self._lock:
            self.log_lines.append(entree)
            del self.log_lines[:-800]
        # The TERMINAL, on top of the file and the in-memory buffer. Without
        # it `docker logs romule` showed only the startup banner: everything
        # that happened afterwards existed for a browser only — that is, for
        # nobody on a server administered over ssh.
        console.event(entree["m"], level, self.module)
        if self.logfile:
            try:
                _rotate(self.logfile)
                with open(self.logfile, "a", encoding="utf-8") as fh:
                    fh.write("%s %s %-5s %s\n" % (entree["date"], entree["t"],
                                                  level.upper(), entree["m"]))
            except OSError:
                pass

    def clear(self):
        with self._lock:
            self.log_lines = []

    def set_total(self, n):
        with self._lock:
            self.total = n
            self.done = 0

    def tick(self):
        with self._lock:
            self.done += 1

    def set_detail(self, text):
        with self._lock:
            self.detail = text

    # ------------------------------------------------------------ pause / arret

    def pause(self):
        with self._lock:
            self.paused = True
        self._resume.clear()

    def resume(self):
        with self._lock:
            self.paused = False
        self._resume.set()

    def cancel(self):
        with self._lock:
            self.cancelled = True
        self._resume.set()          # release a paused task so it can exit

    def checkpoint(self):
        """Call between items: blocks while paused, returns False if cancelled."""
        self._resume.wait()
        with self._lock:
            return not self.cancelled

    def snapshot(self):
        with self._lock:
            return {
                "running": self.running,
                "paused": self.paused,
                "label": self.label,
                "log": list(self.log_lines),
                "done": self.done,
                "total": self.total,
                "detail": self.detail,
            }

    def start(self, label, fn, *args):
        """Run fn(*args) in the background. False if a task is already running."""
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.label = label
            self.log_lines = []
            self.done = 0
            self.total = 0
            self.detail = ""
            self.paused = False
            self.cancelled = False
        self._resume.set()

        def wrap():
            err = None
            try:
                fn(*args)
            except Exception as exc:  # a crashing task must not freeze the interface
                err = str(exc)
                self.log("Erreur : %s" % exc)
            finally:
                with self._lock:
                    self.running = False
                    done, total, cancelled = self.done, self.total, self.cancelled
                if err:
                    resume, evt, level = "failed: %s" % err, "tache_echec", "error"
                elif cancelled:
                    resume, evt, level = ("interrupted at %d/%d" % (done, total),
                                           "tache_echec", "warn")
                else:
                    resume, evt, level = ("finished (%d/%d)" % (done, total),
                                           "tache_ok", "ok")
                if self.notify_end:
                    desktop_notify("%s : %s" % (label, resume))
                # A thirty-file conversion takes half an hour: exactly the
                # moment when you are NOT in front of the screen. The desktop
                # notification only serves someone who already is.
                #
                # Imported HERE and not at the top: `notifs` imports `config`,
                # which reads the disk at import time. A cycle between the two
                # would fail startup rather than one notification.
                try:
                    from . import notify
                    # The SPECIFIC event when we know what ran, the catch-all
                    # otherwise. `notify.send` expands one into the other, so a
                    # destination that only wants to hear about transfers is not
                    # told about every cover refresh — and one that wants
                    # everything still ticks a single box.
                    notify.send(notify.TASK_EVENTS.get(label, evt),
                                "Romule — %s" % label, resume, level)
                except Exception as exc:      # never fatal: this is a convenience
                    console.event("Notification impossible : %s" % exc,
                                      "warn", "notifs")

        threading.Thread(target=wrap, daemon=True).start()
        return True
