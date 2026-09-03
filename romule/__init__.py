"""romule — the engine of a self-hosted game library.

Single source of truth: all the business logic lives here, shared by the web
interface (server.py) and the command line (cli.py).

The core knows the Switch in detail (title IDs, NSP/XCI, updates and DLC);
other platforms go through a per-file inventory. The target device and the
emulator are profiles, not code (see profils.py).
"""

__version__ = "0.3.1"

# Romule is distributed under AGPL-3.0-or-later. The licence requires that a
# user reaching the service OVER THE NETWORK be able to obtain its source: that
# is the point of the link in the interface footer, and of what /api/health
# returns.
SOURCE_URL = "https://github.com/romule-app/romule"
LICENCE = "AGPL-3.0-or-later"
