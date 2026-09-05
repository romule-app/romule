"""The setup wizard must appear when there is nothing set up.

`first_run` used to mean "the configuration file does not exist". That is not
the same question, and it stopped being true the moment the service began
writing that file before anyone connected: in a container `_first_run_token()`
generates the access token at startup and saves it. One second after
`docker compose up`, the file existed — so the wizard could never appear on the
main installation path.

Nothing failed. There was no error, no log line: the interface simply opened on
an empty library, with no account, no library folder chosen, and nothing said
about either. That is the shape of defect this file exists to make loud.

Nothing here starts a server or a container. `accounts.count` and
`auth.enabled` are substituted, which is what lets the container's case be
checked on a laptop.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["ROMULE_ROOT"] = tempfile.mkdtemp(prefix="romule-premier-")

from romule import accounts, auth, config, server                  # noqa: E402

ok = ko = 0


def t(name, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        ko += 1
        print("  FAIL %s   %s" % (name, detail))


class _Etat:
    """How many accounts, and whether a usable authentication exists."""

    def __init__(self, comptes=0, auth_active=False):
        self.comptes, self.auth_active = comptes, auth_active

    def __enter__(self):
        self._c, self._a = accounts.count, auth.enabled
        accounts.count = lambda: self.comptes
        auth.enabled = lambda cfg=None: self.auth_active
        server.accounts.count = accounts.count
        server.auth.enabled = auth.enabled
        return self

    def __exit__(self, *_):
        accounts.count, auth.enabled = self._c, self._a
        server.accounts.count, server.auth.enabled = self._c, self._a


def test_a_fresh_install_is_a_first_run():
    with _Etat(comptes=0, auth_active=False):
        t("nothing set up means first run", server._first_run() is True)


def test_the_saved_config_does_not_end_the_first_run():
    """The defect itself. The service writes its configuration at startup to
    keep the generated token; that must not be read as "somebody has set this
    up"."""
    config.save_config(config.load_config())
    t("the configuration file now exists", config.CONFIG_FILE.exists())
    with _Etat(comptes=0, auth_active=False):
        t("and it is STILL a first run", server._first_run() is True,
          "the wizard would never appear on the container path")


def test_an_account_ends_it():
    with _Etat(comptes=1, auth_active=True):
        t("one account is enough", server._first_run() is False)


def test_an_sso_ends_it_with_no_local_account():
    """An installation behind an identity provider has no local account and is
    nonetheless set up: asking its user to create one would be wrong."""
    with _Etat(comptes=0, auth_active=True):
        t("a usable SSO ends it", server._first_run() is False)


def test_a_half_configured_authentication_does_not():
    """`auth.enabled()` already refuses to call a half-configured mode active —
    an `interne` mode with no account locks everyone out. The wizard must side
    with that reading, or it would leave the user in front of a service that
    refuses them with no way to fix it."""
    with _Etat(comptes=0, auth_active=False):
        t("a mode that lets nobody in is still a first run",
          server._first_run() is True)


for fn in (test_a_fresh_install_is_a_first_run,
           test_the_saved_config_does_not_end_the_first_run,
           test_an_account_ends_it,
           test_an_sso_ends_it_with_no_local_account,
           test_a_half_configured_authentication_does_not):
    fn()
print("  %d checks OK, %d failure(s)" % (ok, ko))
sys.exit(1 if ko else 0)
