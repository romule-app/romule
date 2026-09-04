"""Doing something while nobody is watching.

Everything Romule does was manual or triggered by the API. That is a reasonable
default for a tool you sit in front of; it is the wrong one for a service that
runs on a NAS for months. The notifications added in 0.3.0 only mean something
if something happens while you sleep — otherwise they announce the tasks you
started yourself, one second after you started them.

Presets, not cron
-----------------
A drop-down: never, at startup, hourly, every six hours, nightly at a chosen
hour. No cron parser to write, no field where a misplaced star silently means
"every minute of every hour". The five answers cover what a game library needs,
and each one is a phrase rather than a syntax.

Nothing is queued
-----------------
A daemon thread wakes every minute. If a task is already running, the due time
is SKIPPED and said so in the log — it is not stacked for later. That is the
same semantics as the API's 409: Romule does one thing at a time, and says so.
A queue would turn a slow night into a morning where four tasks run at once on
a machine chosen for being quiet.

The last run is persisted
-------------------------
In `schedule_state`, beside the schedule itself. Without it, a restart makes
every "nightly" due again — and a container that restarts on a health check
would run the nightly task all day.

Nothing irreversible is schedulable
-----------------------------------
Emptying the trash, clearing the log, revoking a key: absent from `TASKS`, and
that is not an oversight. An unattended action must be one whose result you can
still look at in the morning.
"""

import threading
import time

# The schedulable tasks: the name stored in the configuration, and the label
# shown in the interface. Each one is REVERSIBLE — it reads, files, converts or
# copies, and nothing it does cannot be looked at afterwards.
TASKS = {
    "scan": "Read the library",
    "import": "File the drop folder",
    "convert": "Convert to NSZ",
    "push": "Send to the console",
    "meta": "Refresh the game entries",
}

# The presets. `nightly` carries its hour, because an hour without its preset is
# a setting that means nothing on its own.
NEVER = "never"
STARTUP = "startup"
HOURLY = "hourly"
SIX_HOURLY = "6h"
NIGHTLY = "nightly"          # stored as `nightly:HH`

HOUR = 3600
DAY = 24 * HOUR

# How often the thread wakes. A minute is far finer than any preset needs, and
# it keeps the arithmetic honest: an hourly task fires within a minute of its
# hour rather than whenever the loop happens to come round.
TICK = 60


def preset_of(value):
    """The preset name and its hour, from a stored value.

    `nightly:03` -> ("nightly", 3). Anything unreadable is `never`: a schedule
    nobody can parse must do nothing, never something at an arbitrary time.
    """
    text = str(value or NEVER).strip().lower()
    if not text.startswith(NIGHTLY):
        return (text if text in (NEVER, STARTUP, HOURLY, SIX_HOURLY) else NEVER), 0
    _, _, hour = text.partition(":")
    try:
        h = int(hour)
    except ValueError:
        h = 3
    return NIGHTLY, h % 24


def _last_nightly(now, hour):
    """The most recent moment the clock passed `hour`:00, at or before `now`."""
    local = time.localtime(now)
    today = time.mktime((local.tm_year, local.tm_mon, local.tm_mday,
                         hour, 0, 0, 0, 0, -1))
    return today if today <= now else today - DAY


def due(value, last, now):
    """Is this task due?

    `last` is when it last RAN, zero if never. A task that has never run under
    a periodic preset is due at once: someone who has just chosen "hourly"
    expects it to happen, not to wait an hour to find out whether it works.
    """
    preset, hour = preset_of(value)
    if preset in (NEVER, STARTUP):
        return False                       # startup is handled by `run_startup`
    if not last:
        return True
    if preset == HOURLY:
        return now - last >= HOUR
    if preset == SIX_HOURLY:
        return now - last >= 6 * HOUR
    return last < _last_nightly(now, hour) <= now


class Scheduler:
    """The loop, with everything it depends on injected.

    `read` returns the configuration, `save_state` persists the last-run table,
    `start` launches a task and returns False when one is already running, and
    `clock` is the time source. Injected rather than imported, so the tests can
    make a night pass in a microsecond and never depend on the real hour.
    """

    def __init__(self, read, save_state, start, log=lambda m: None,
                 clock=time.time):
        self.read = read
        self.save_state = save_state
        self.start = start
        self.log = log
        self.clock = clock
        self._stop = threading.Event()
        self._thread = None

    # ------------------------------------------------------------ one pass

    def tick(self):
        """One pass. Returns the tasks it started, in order."""
        cfg = self.read() or {}
        schedule = cfg.get("schedule") or {}
        state = dict(cfg.get("schedule_state") or {})
        now = self.clock()
        started = []
        for name in sorted(TASKS):
            if not due(schedule.get(name), float(state.get(name) or 0), now):
                continue
            if self.start(name):
                state[name] = now
                started.append(name)
            else:
                # Skipped, not queued. Saying so matters: without this line the
                # only trace of a missed night is a `schedule_state` that did
                # not move, which nobody reads.
                self.log("Scheduled task skipped, another is running: %s" % name)
        if started:
            self.save_state(state)
        return started

    def run_startup(self):
        """The `startup` preset, played once when the service comes up."""
        cfg = self.read() or {}
        schedule = cfg.get("schedule") or {}
        state = dict(cfg.get("schedule_state") or {})
        started = []
        for name in sorted(TASKS):
            if preset_of(schedule.get(name))[0] != STARTUP:
                continue
            if self.start(name):
                state[name] = self.clock()
                started.append(name)
            else:
                self.log("Startup task skipped, another is running: %s" % name)
        if started:
            self.save_state(state)
        return started

    # ------------------------------------------------------------ the loop

    def start_thread(self):
        """Wake every minute, forever. Never raises: a scheduler that dies on
        one bad pass takes every later pass with it, and says nothing."""
        if self._thread is not None:
            return self._thread

        def loop():
            while not self._stop.wait(TICK):
                try:
                    self.tick()
                except Exception as exc:
                    self.log("Scheduler error: %s" % exc)

        self._thread = threading.Thread(target=loop, name="scheduler",
                                        daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        self._stop.set()


def clean(schedule):
    """Keep only what the interface may store: known tasks, known presets."""
    out = {}
    for name, value in (schedule or {}).items():
        if name not in TASKS:
            continue
        preset, hour = preset_of(value)
        if preset == NEVER:
            continue                       # the default: nothing to store
        out[name] = "%s:%02d" % (NIGHTLY, hour) if preset == NIGHTLY else preset
    return out
