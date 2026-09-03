"""Decoding Switch title IDs — THE single source of truth.

Nintendo convention (16 hex digits, 64 bits), 13th nibble = index 12:
  BASE   : 13th nibble even, last three = 000
  UPDATE : base | 0x800            -> last three = 800
  DLC    : base + 0x1000 + index   -> 13th nibble odd (even base + 1)

Since bases always have an even 13th nibble, stepping up to a DLC (+1) never
carries past that nibble for any realistic DLC count (< 4096), so the
heuristic is stable.
"""

import os
import re

TID_RE = re.compile(r"01[0-9A-Fa-f]{14}")
VER_RE = re.compile(r"\[v(\d+)\]")


def is_valid(tid):
    return bool(tid) and len(tid) == 16 and all(c in "0123456789abcdef" for c in tid.lower())


def from_name(name):
    """Extract the title ID from a file name, or None."""
    m = TID_RE.search(name)
    return m.group(0).lower() if m else None


def version_from_name(name):
    """Extract the version number from [vN], or None."""
    m = VER_RE.search(name)
    return int(m.group(1)) if m else None


def pretty_name(name):
    """Readable name: cut from the title-ID bracket onwards.

    `os.path.splitext` rather than `Path(name).stem`: this runs once per file
    in the library, on every render. Across 39 525 files, building a `Path`
    object to read one attribute and throw it away cost 137 ms — for a string
    split the standard library does without allocating.
    """
    stem = os.path.splitext(name)[0]
    return re.sub(r"\s*\[0100.*", "", stem).strip() or stem


def _nibble(tid):
    return int(tid[12], 16)


def tid_type(tid):
    t = tid.lower()
    n = _nibble(t)
    if n % 2 == 0:
        if t[13:16] == "000":
            return "BASE"
        if t[13:16] == "800":
            return "UPDATE"
    return "DLC"


def tid_base(tid):
    """Title ID of the base game an update or a DLC belongs to."""
    t = tid.lower()
    n = _nibble(t)
    if n % 2 == 1:
        n -= 1
    return "%s%x000" % (t[:12], n)


def tid_patch(tid):
    """Title ID of a base game's patch (update)."""
    t = tid.lower()
    return "%s%s800" % (t[:12], t[12])


def dlc_prefix(base_tid):
    """Prefix (13 hex digits) shared by every DLC of a base game."""
    t = base_tid.lower()
    return "%s%x" % (t[:12], _nibble(t) + 1)


def revision(version):
    """Nintendo version -> readable revision number (v0, rev 3...)."""
    if version and version > 0:
        return "rev %d" % (version // 65536)
    return "v0"
