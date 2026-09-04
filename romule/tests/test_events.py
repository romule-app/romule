"""Every event you can tick must be an event something sends.

This file exists because of a question that had no good answer. The settings
offered five events; only two were ever emitted. Someone could tick *the
console connected*, *a version is available* and *the drop folder was filed*,
and Romule would never say a word — no error, no log line, nothing to notice.
A subscription to something nobody publishes is worse than a missing feature:
it looks answered.

`test_notify.py` could not catch it. It checks the SHAPE of what leaves and the
silence when nothing is configured — both true of an event nobody sends. So the
check here is on the other side: the declared list against the emitters.

Nothing in this file opens a socket, so it runs in the unit family, where it is
seen rather than assumed.
"""

import ast
import contextlib
import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE.parent))

from romule import notify                                        # noqa: E402

ok = ko = 0


def t(name, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        ko += 1
        print("  FAIL %s   %s" % (name, detail))


@contextlib.contextmanager
def _sans_reseau():
    """Count what `send` decides to contact, without contacting anything.

    The substitution is undone by the context manager rather than by hand: a
    test that leaves a stub behind poisons every test after it, and the one
    that fails is not the one at fault.
    """
    envoyes = []
    vrai = notify._attempt
    notify._attempt = lambda target, data, headers: envoyes.append(target["id"])
    try:
        yield envoyes
    finally:
        notify._attempt = vrai


def _emitted():
    """Every event name the shipped code can actually send.

    Read from the source rather than by running it: an emitter that only fires
    when a console is plugged in would otherwise count as absent on a machine
    with no console — which is every machine that runs the tests.
    """
    names = set()
    for p in sorted(RACINE.glob("*.py")):
        src = p.read_text(encoding="utf-8")
        names |= set(re.findall(r'notify\.send\(\s*"([a-z_]+)"', src))
        # `jobs.py` passes the name through a variable: the two catch-alls are
        # chosen there by outcome, and the specific ones come from the table.
        if "notify.send(notify.TASK_EVENTS.get(" in src:
            names |= set(notify.TASK_EVENTS.values())
            names |= {"tache_ok", "tache_echec"}
    return names


def test_every_declared_event_has_an_emitter():
    orphelins = sorted(set(notify.EVENTS) - _emitted())
    t("no event is offered that nothing sends", not orphelins, orphelins)


def test_no_emitter_sends_an_undeclared_event():
    """The other direction: something sent but not offered can never be
    subscribed to, so it reaches nobody."""
    inconnus = sorted(_emitted() - set(notify.EVENTS))
    t("nothing is sent that cannot be ticked", not inconnus, inconnus)


def test_the_task_table_names_real_functions():
    """`TASK_EVENTS` is keyed by the label `JobRunner` gives a task, which is a
    Python function's own name. A renamed action would quietly stop producing
    its specific event — and fall back to the catch-all, which looks like it
    still works."""
    src = (RACINE / "actions.py").read_text(encoding="utf-8")
    defs = {n.name for n in ast.parse(src).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    # `scan` is started under that label by the server, not by actions.py.
    absentes = sorted(k for k in notify.TASK_EVENTS if k not in defs and k != "scan")
    t("every task in the table is a function that exists", not absentes, absentes)


def test_a_specific_event_also_satisfies_its_catch_all():
    t("a finished transfer satisfies both",
      notify._names("envoi", "ok") == {"envoi", "tache_ok"},
      notify._names("envoi", "ok"))
    t("a failed transfer satisfies the failure catch-all",
      notify._names("envoi", "error") == {"envoi", "tache_echec"},
      notify._names("envoi", "error"))
    t("an interrupted one counts as a failure",
      "tache_echec" in notify._names("conversion", "warn"))
    # The specific event fires on BOTH outcomes: someone watching for the end of
    # a 12 GB transfer wants to hear about it either way.
    t("the specific event fires whatever the outcome",
      "envoi" in notify._names("envoi", "ok")
      and "envoi" in notify._names("envoi", "error"))


def test_an_event_that_is_not_a_task_stays_alone():
    t("a console connection is not a task",
      notify._names("console_liee", "ok") == {"console_liee"},
      notify._names("console_liee", "ok"))
    t("a new version is not a task",
      notify._names("maj", "info") == {"maj"}, notify._names("maj", "info"))
    t("a catch-all does not expand into specifics",
      notify._names("tache_ok", "ok") == {"tache_ok"})


def test_one_message_per_destination():
    """A destination subscribed to both `envoi` and `tache_ok` must be told
    ONCE about a transfer, not twice."""
    cfg = {"notif_destinations": [
        {"id": "1", "nom": "Salon", "url": "https://hooks.slack.com/x",
         "evenements": ["envoi", "tache_ok"]}]}
    with _sans_reseau() as envoyes:
        n = notify.send("envoi", "T", "", "ok", cfg, wait=True)
    t("a doubly-subscribed destination is contacted once",
      n == 1 and envoyes == ["1"], (n, envoyes))


def test_a_narrow_subscription_stays_narrow():
    cfg = {"notif_destinations": [
        {"id": "1", "url": "https://hooks.slack.com/x", "evenements": ["envoi"]}]}
    with _sans_reseau():
        n_conv = notify.send("conversion", "T", "", "ok", cfg, wait=True)
        n_push = notify.send("envoi", "T", "", "ok", cfg, wait=True)
    t("a conversion does not reach a transfer-only destination", n_conv == 0, n_conv)
    t("a transfer does", n_push == 1, n_push)


def test_every_label_is_a_catalogue_key():
    """The labels are shown as checkbox text, so they go through `t()`. One
    that is not a key displays untranslated — in English inside a French
    interface, which is the defect the whole i18n check exists for."""
    fr = json.loads((RACINE / "locales" / "fr.json").read_text(encoding="utf-8"))
    absents = sorted(v for v in notify.EVENTS.values() if v not in fr)
    t("every event label is in the catalogue", not absents, absents)


for fn in (test_every_declared_event_has_an_emitter,
           test_no_emitter_sends_an_undeclared_event,
           test_the_task_table_names_real_functions,
           test_a_specific_event_also_satisfies_its_catch_all,
           test_an_event_that_is_not_a_task_stays_alone,
           test_one_message_per_destination,
           test_a_narrow_subscription_stays_narrow,
           test_every_label_is_a_catalogue_key):
    fn()
print("  %d checks OK, %d failure(s)" % (ok, ko))
sys.exit(1 if ko else 0)
