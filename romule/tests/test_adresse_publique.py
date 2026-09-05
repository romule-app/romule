"""The address Romule tells people to open must be one they can open.

This exists because of what a container install showed FIRST. `_lan_ip()`
opens a socket and reads its own end: on a laptop that is the LAN address, in a
container it is the bridge address — `172.18.0.2`. Correct for the container,
unreachable from the host under Docker Desktop or Colima, and unreachable from
the console, which was being asked to open it.

The address appeared in three places, and all three were wrong at once: the
first-start banner carrying the token, the settings screen, and the button that
pushes the address to the console's browser.

Nothing here opens a socket or needs a container: `config.in_container()` is
substituted, which is what lets the defect be caught on a laptop — the machine
where it cannot happen, and therefore where nobody would have looked.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ["ROMULE_ROOT"] = tempfile.mkdtemp(prefix="romule-adresse-")

from romule import config, server                                  # noqa: E402

ok = ko = 0


def t(name, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        ko += 1
        print("  FAIL %s   %s" % (name, detail))


class _Contexte:
    """A container, or not, and a declared address, or not."""

    def __init__(self, conteneur=False, declaree=None):
        self.conteneur, self.declaree = conteneur, declaree

    def __enter__(self):
        self._vrai = config.in_container
        config.in_container = lambda: self.conteneur
        self._avant = os.environ.get("ROMULE_PUBLIC_HOST")
        if self.declaree is None:
            os.environ.pop("ROMULE_PUBLIC_HOST", None)
        else:
            os.environ["ROMULE_PUBLIC_HOST"] = self.declaree
        return self

    def __exit__(self, *_):
        config.in_container = self._vrai
        if self._avant is None:
            os.environ.pop("ROMULE_PUBLIC_HOST", None)
        else:
            os.environ["ROMULE_PUBLIC_HOST"] = self._avant


def test_a_container_does_not_invent_an_address():
    with _Contexte(conteneur=True):
        t("a container offers no address rather than the bridge one",
          server._lan_ip() is None, server._lan_ip())
        t("and it says why", "ROMULE_PUBLIC_HOST" in server._no_address_reason(),
          server._no_address_reason())
        # The reason is READ by somebody: blaming the Wi-Fi of a container whose
        # network works sends them to look in the wrong place.
        t("the reason does not blame the network",
          "wifi" not in server._no_address_reason().lower()
          and "connexion" not in server._no_address_reason().lower(),
          server._no_address_reason())


def test_a_declared_address_is_used_as_it_is():
    with _Contexte(conteneur=True, declaree="192.168.1.20"):
        t("the declared address wins", server._lan_ip() == "192.168.1.20",
          server._lan_ip())
        t("and gets the service port",
          server._public_url(server._lan_ip())
          == "http://192.168.1.20:%d" % config.PORT,
          server._public_url(server._lan_ip()))


def test_a_declared_port_is_kept():
    """The published port is not always the internal one: `9000:8787` is an
    ordinary mapping, and appending 8787 to it would give an address that does
    not answer — the very defect this file is about, one layer further out."""
    with _Contexte(conteneur=True, declaree="nas.local:9000"):
        t("a declared port is not overwritten",
          server._public_url(server._lan_ip()) == "http://nas.local:9000",
          server._public_url(server._lan_ip()))
    with _Contexte(conteneur=True, declaree="http://nas.local/"):
        t("a scheme and a trailing slash are tolerated",
          server._public_url(server._lan_ip())
          == "http://nas.local:%d" % config.PORT,
          server._public_url(server._lan_ip()))


def test_outside_a_container_nothing_changes():
    with _Contexte(conteneur=False):
        ip = server._lan_ip()
        # The machine running the tests may have no network at all; what must
        # not happen is a bridge address being passed off as a LAN one.
        t("a real machine still answers with an address or with nothing",
          ip is None or ip.count(".") == 3 or ":" in ip, ip)
        if ip:
            t("and it is built into a usable address",
              server._public_url(ip).startswith("http://"), server._public_url(ip))
        else:
            t("and it is built into a usable address", True)


def test_no_address_means_no_url_at_all():
    """A missing address must not become `http://None:8787`, which is what
    string formatting gives when nobody looks."""
    t("nothing in, nothing out", server._public_url(None) is None,
      server._public_url(None))
    t("an empty string too", server._public_url("") is None, server._public_url(""))


for fn in (test_a_container_does_not_invent_an_address,
           test_a_declared_address_is_used_as_it_is,
           test_a_declared_port_is_kept,
           test_outside_a_container_nothing_changes,
           test_no_address_means_no_url_at_all):
    fn()
print("  %d checks OK, %d failure(s)" % (ok, ko))
sys.exit(1 if ko else 0)
