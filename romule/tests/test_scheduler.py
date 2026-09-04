"""The scheduler, on an injected clock — never on the real hour.

A test that reads the wall clock passes at 14:00 and fails at 03:00, and the
failure looks like a bug in the code rather than in the test. So `Scheduler`
takes its time source as an argument, and every moment here is a number this
file chose.

What is checked is as much what fires as what does NOT: a preset that says
never, a task already running, and a schedule that survives a restart. A
scheduler nobody has seen decline to fire is a scheduler that will fire twice.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from romule import scheduler                                     # noqa: E402

ok = ko = 0


def t(name, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        ko += 1
        print("  FAIL %s   %s" % (name, detail))


class Fake:
    """A configuration, a clock and a runner, all under the test's control."""

    def __init__(self, schedule=None, state=None, busy=False, now=1_700_000_000):
        self.cfg = {"schedule": schedule or {}, "schedule_state": state or {}}
        self.busy = busy
        self.now = now
        self.started = []
        self.logged = []

    def read(self):
        return self.cfg

    def save_state(self, state):
        self.cfg["schedule_state"] = state

    def start(self, name):
        if self.busy:
            return False
        self.started.append(name)
        return True

    def clock(self):
        return self.now

    def make(self):
        return scheduler.Scheduler(self.read, self.save_state, self.start,
                                   self.logged.append, self.clock)


def test_presets_are_read():
    t("an unknown preset falls back to never",
      scheduler.preset_of("whatever")[0] == scheduler.NEVER)
    t("nightly carries its hour", scheduler.preset_of("nightly:03") == ("nightly", 3))
    t("an unreadable hour falls back to 3",
      scheduler.preset_of("nightly:zz") == ("nightly", 3))
    t("an hour out of range wraps", scheduler.preset_of("nightly:26") == ("nightly", 2))
    t("hourly is read", scheduler.preset_of("hourly")[0] == "hourly")


def test_due():
    now = 1_700_000_000
    t("never is never due", not scheduler.due("never", 0, now))
    t("startup is not due on a tick", not scheduler.due("startup", 0, now))
    t("a periodic task never run is due at once", scheduler.due("hourly", 0, now))
    t("hourly is not due after 59 minutes",
      not scheduler.due("hourly", now - 59 * 60, now))
    t("hourly is due after an hour", scheduler.due("hourly", now - 3600, now))
    t("six-hourly waits its six hours",
      not scheduler.due("6h", now - 5 * 3600, now)
      and scheduler.due("6h", now - 6 * 3600, now))


def test_nightly_fires_once_a_night():
    # Three in the morning, local time, whatever the machine's zone: the moment
    # is built from the clock the code itself uses.
    hour = 3
    now = time.mktime((2026, 5, 4, hour, 30, 0, 0, 0, -1))
    last_night = scheduler._last_nightly(now, hour)
    t("a nightly task not yet run tonight is due",
      scheduler.due("nightly:03", last_night - 60, now))
    t("a nightly task already run tonight is not due again",
      not scheduler.due("nightly:03", last_night + 60, now))
    before = time.mktime((2026, 5, 4, hour - 1, 30, 0, 0, 0, -1))
    t("it is not due before its hour",
      not scheduler.due("nightly:03", last_night - DAY_AGO, before))


DAY_AGO = 23 * 3600


def test_a_pass_starts_and_records():
    f = Fake(schedule={"scan": "hourly"})
    started = f.make().tick()
    t("a due task is started", started == ["scan"], started)
    t("the run is recorded", f.cfg["schedule_state"].get("scan") == f.now,
      f.cfg["schedule_state"])
    # A second pass at the same instant must NOT run it again: that is the
    # whole point of persisting the last run.
    t("it does not fire twice in the same minute", f.make().tick() == [])


def test_a_running_task_is_skipped_not_queued():
    f = Fake(schedule={"scan": "hourly"}, busy=True)
    started = f.make().tick()
    t("nothing is started while a task runs", started == [], started)
    t("the skip is said out loud",
      any("skipped" in m for m in f.logged), f.logged)
    # And the due time is NOT remembered as run: the next pass, once free, must
    # still do it. A skipped night that also counts as done is a night lost.
    t("the skipped task stays due", not f.cfg["schedule_state"].get("scan"))
    f.busy = False
    t("it runs on the next free pass", f.make().tick() == ["scan"])


def test_the_schedule_survives_a_restart():
    f = Fake(schedule={"scan": "hourly"})
    f.make().tick()
    state = dict(f.cfg["schedule_state"])
    # A restart: a brand-new scheduler, the same persisted state, one second
    # later. Without persistence this fires again — and a container that
    # restarts often would run its nightly task all day.
    g = Fake(schedule={"scan": "hourly"}, state=state, now=f.now + 1)
    t("a restart does not re-fire a task just run", g.make().tick() == [])


def test_startup_is_its_own_pass():
    f = Fake(schedule={"scan": "startup", "import": "hourly"})
    t("a tick ignores the startup preset", f.make().tick() == ["import"])
    g = Fake(schedule={"scan": "startup", "import": "hourly"})
    t("the startup pass runs only the startup tasks",
      g.make().run_startup() == ["scan"])


def test_nothing_irreversible_is_schedulable():
    """The list is short on purpose. An unattended action must be one whose
    result can still be looked at in the morning."""
    for name in ("purge", "trash", "journal", "revoke", "clear", "delete"):
        t("`%s` is not schedulable" % name,
          not any(name in k for k in scheduler.TASKS), sorted(scheduler.TASKS))


def test_only_known_values_are_stored():
    kept = scheduler.clean({"scan": "hourly", "unknown_task": "hourly",
                            "import": "whatever", "convert": "nightly:7"})
    t("an unknown task is dropped", "unknown_task" not in kept, kept)
    t("an unknown preset is dropped", "import" not in kept, kept)
    t("a known preset is kept", kept.get("scan") == "hourly", kept)
    t("nightly keeps its hour, normalised", kept.get("convert") == "nightly:07", kept)


for fn in (test_presets_are_read, test_due, test_nightly_fires_once_a_night,
           test_a_pass_starts_and_records,
           test_a_running_task_is_skipped_not_queued,
           test_the_schedule_survives_a_restart, test_startup_is_its_own_pass,
           test_nothing_irreversible_is_schedulable,
           test_only_known_values_are_stored):
    fn()
print("  %d checks OK, %d failure(s)" % (ok, ko))
sys.exit(1 if ko else 0)
