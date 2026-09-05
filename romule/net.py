"""Outbound network: one way through, and one check.

`urllib.request.urlopen` does not only open HTTP. It accepts `file://`,
`ftp://` and whatever the installed handlers know how to process. And three of
the addresses Romule uses come from its CONFIGURATION:

    cover_url      where cover art comes from
    versions_urls  the titledb mirrors
    oidc_issuer    the identity provider

A `file:///etc/passwd` in the cover-art field therefore made the server read a
local file and hand it back as an image. Setting those fields requires
administrator rights, which limits the reach — but an administrator has no
business being able to turn the service into a file reader through a settings
field, and an installation with authentication switched off has no distinct
administrator in the first place.

The check lives here, on the one path every outbound call goes through, rather
than repeated in nine places where one would eventually be forgotten.
"""

import urllib.error
import urllib.parse
import urllib.request

SCHEMES = ("http", "https")


class SchemeRefused(ValueError):
    """An address whose scheme is not allowed."""


def check(url):
    """Return the URL if it is acceptable, raise `SchemeRefused` otherwise."""
    scheme = urllib.parse.urlparse(str(url or "")).scheme.lower()
    if scheme not in SCHEMES:
        raise SchemeRefused(
            # The sentence stays in French: it is handed to the interface as
            # the reason a destination was refused, and shown as it arrives.
            # The identifiers around it are English; the phrase people read is
            # not an identifier.
            "schema refuse : %r (seuls %s sont acceptes)"
            % (scheme or "aucun", " et ".join(SCHEMES)))
    return url


def open_url(target, timeout=30):
    """`urlopen`, but http(s) only.

    Accepts a string or a `Request`, like `urlopen`, so it can stand in for
    existing calls without rewriting them.
    """
    url = target.full_url if isinstance(target, urllib.request.Request) else target
    check(url)
    # This is THE only `urlopen` in the shipped code, and the scheme was checked
    # two lines above. The suppression markers carry their reason: tools cannot
    # see that check, and a marker without a motive gets copied everywhere else.
    # The reason is written ABOVE, never after the marker: bandit reads whatever
    # follows it as a list of rule identifiers, and a sentence there becomes a
    # string of fake test names. (This comment avoids spelling the marker out
    # for the same reason.)
    return urllib.request.urlopen(target, timeout=timeout)  # nosec B310  # noqa: S310
