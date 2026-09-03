"""An outbound call must not be able to read a local file.

`urllib.request.urlopen` does not only open HTTP: it accepts `file://`, `ftp://`,
and whatever the installed handlers know how to process. Three of the addresses
Romule uses come from the configuration — the cover source, the titledb mirrors,
the OIDC issuer — and nothing checked their scheme. A `file:///etc/passwd` in the
cover field therefore made the server read a local file and hand it back as an
image.

This test holds both halves of the property: what must pass passes, and what must
be refused is — including in the shapes that bypass a naive comparison.
"""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from romule import net                                          # noqa: E402

ok = ko = 0


def t(name, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        ko += 1
        print("  FAIL %s   %s" % (name, detail))


def test_accepts_http():
    for u in ("http://exemple.fr/a", "https://exemple.fr/a",
              "HTTPS://EXEMPLE.FR/A", "https://exemple.fr:8443/a?b=c"):
        try:
            net.check(u)
            t("accepts %s" % u, True)
        except net.SchemeRefused as exc:
            t("accepts %s" % u, False, exc)


def test_refuses_the_rest():
    # `file:` is the case that matters: it is the one that turns the service
    # into a file reader. The others are refused by the same rule.
    for u in ("file:///etc/passwd", "FILE:///etc/passwd", "ftp://h/f",
              "gopher://h/", "data:text/plain,bonjour", "/etc/passwd",
              "etc/passwd", "", None):
        try:
            net.check(u)
            t("refuses %r" % u, False, "wrongly accepted")
        except net.SchemeRefused:
            t("refuses %r" % u, True)


def test_open_url_also_checks_Request_objects():
    """The check must be on the URL the request carries, not on the object."""
    req = urllib.request.Request("file:///etc/passwd",
                                 headers={"User-Agent": "romule"})
    try:
        net.open_url(req)
        t("a file:// Request is refused", False, "wrongly opened")
    except net.SchemeRefused:
        t("a file:// Request is refused", True)
    except Exception as exc:
        t("a file:// Request is refused", False, "another error: %r" % exc)


def test_no_direct_call_in_the_shipped_code():
    """The guard is only worth something if nobody bypasses it.

    A centralised check goes stale as soon as a direct call reappears elsewhere.
    We verify it on the source, not on the intention.
    """
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for f in sorted(root.glob("*.py")):
        if f.name == "net.py":
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "urlopen(" in line and not line.lstrip().startswith("#"):
                offenders.append("%s:%d" % (f.name, n))
    t("no direct urlopen outside net.py", not offenders, offenders)


for fn in (test_accepts_http, test_refuses_the_rest,
           test_open_url_also_checks_Request_objects,
           test_no_direct_call_in_the_shipped_code):
    fn()
print("  %d checks OK, %d failure(s)" % (ok, ko))
sys.exit(1 if ko else 0)
