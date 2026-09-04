"""The public API, version 1 — the one we promise not to break.

Romule serves 97 `/api/...` routes. They are cut for its own browser: they
return what a screen needs, change when that screen changes, and that is fine.
Freezing them would mean forbidding ourselves from evolving the interface.

`/api/v1` is something else: a small surface, chosen for what a dashboard or a
script really wants to know, and STABLE. What Sonarr and Radarr publish is not
their internal surface either, and for the same reason.

La promesse, precisement
------------
Within a major version no route disappears, and no existing field changes name
or type. Fields may APPEAR — so a client must ignore the ones it does not know.
That is all; the rest of the API is not covered by this promise, and says so.

La portee
-----
`dans_la_portee()` -- anglais:ok, quoting a function name -- decides on its own
what an API key may reach, and it compares
the path ALREADY NORMALISED by the server. A key handed to a dashboard must not
be able to delete an account: that is the entire point of the exercise, and it
is what `test_apikeys.py` checks.
"""

import json
import time
import urllib.parse

from . import __version__

PREFIX = "/api/v1/"

# Pagination bounds. 200 is not a round number picked at random: a library of
# 5 000 titles fits in 25 pages, and a page of 200 entries weighs a few hundred
# kilobytes — compressed by the server since version 0.2.0.
LIMITE_DEFAUT = 50
LIMITE_MAX = 200


def in_scope(path):
    """True if an API key is allowed to reach this path.

    The comparison is strict and literal. `/api/v1` alone is not enough:
    without the trailing slash, `/api/v1x/...` would pass too. The server
    already normalises the path before we get here — so `..` and double slashes
    are resolved — but we do not rely on that: a path still containing either
    is refused.
    """
    if not isinstance(path, str) or not path.startswith(PREFIX):
        return False
    if ".." in path or "//" in path:
        return False
    return True


# --------------------------------------------------------------- helpers

def _int(values, key, default, lowest, highest):
    """Two distinct behaviours, and that is deliberate.

    An UNREADABLE value (`page=zero`) falls back to the default: the client got
    the type wrong, nothing can be made of it. An OUT-OF-RANGE value
    (`limit=100000`, `limit=-4`) is clamped: the intent is legible, and
    refusing it would force every client to know the ceiling before asking.
    That is the convention for paginated APIs, and it is written in the
    specification.
    """
    try:
        n = int((values.get(key) or [str(default)])[0])
    except (TypeError, ValueError):
        return default
    return max(lowest, min(highest, n))


def _entry(f):
    """What we publish about a library file.

    The ABSOLUTE path is not part of it. It teaches a client nothing, and it
    reveals the server's directory tree — often including the person's account
    name. The relative path is enough to designate a game, and it is already
    the key used everywhere else.
    """
    return {
        "key": f.get("rel"),
        "name": f.get("name"),
        "folder": f.get("dir"),
        "extension": f.get("ext"),
        "title_id": f.get("tid"),
        "type": f.get("type"),
        "version": f.get("version"),
        "size": f.get("size"),
        "playable": f.get("ext") in ("nsp", "xci"),
        "needs_convert": bool(f.get("needs_convert")),
        "flags": [g[0] for g in (f.get("flags") or [])],
    }


def _page(items, params):
    page = _int(params, "page", 1, 1, 10 ** 6)
    limite = _int(params, "limit", LIMITE_DEFAUT, 1, LIMITE_MAX)
    total = len(items)
    debut = (page - 1) * limite
    return {
        "page": page,
        "limit": limite,
        "total": total,
        "pages": max(1, (total + limite - 1) // limite),
        "items": items[debut:debut + limite],
    }


# ------------------------------------------------------------------ routage

def router(path, params, method, ctx):
    """Return (code, object), or None when the route is unknown.

    `ctx` carries what the server knows how to do, injected rather than
    imported: this module must not depend on `server`, which already depends on
    everything else.
    """
    nom = path[len(PREFIX):]

    if method == "GET":
        if nom == "health":
            return 200, ctx["health"]()
        if nom == "openapi.json":
            return 200, SPEC
        if nom == "system":
            h = ctx["health"]()
            return 200, {
                "version": h.get("version"),
                "licence": h.get("licence"),
                "source": h.get("source"),
                "api": "v1",
                "started_at": ctx["demarrage"],
                "uptime_s": int(time.time() - ctx["demarrage"]),
                "library_ready": not h.get("first_run"),
            }
        if nom == "stats":
            lib = ctx["inventaire"]()
            return 200, lib["stats"]
        if nom == "library":
            lib = ctx["inventaire"]()
            fiches = [_entry(f) for f in lib["files"]]
            genre = (params.get("type") or [""])[0].upper()
            if genre:
                fiches = [f for f in fiches if f["type"] == genre]
            fiches.sort(key=lambda f: (f["name"] or "").lower())
            return 200, _page(fiches, params)
        if nom.startswith("library/"):
            # A game's key IS its relative path: it contains spaces, square
            # brackets, sometimes an apostrophe. So it arrives percent-encoded,
            # and comparing it as-is never finds anything. Only the key is
            # decoded, not the whole path: decoding before routing would let a
            # `%2F` forge a segment.
            key = urllib.parse.unquote(nom[len("library/"):])
            lib = ctx["inventaire"]()
            for f in lib["files"]:
                if f.get("rel") == key:
                    return 200, _entry(f)
            return 404, {"error": "not_found",
                         "message": "No game with that key."}
        if nom == "search":
            q = (params.get("q") or [""])[0].strip().lower()
            if not q:
                return 400, {"error": "missing_parameter",
                             "message": "q is required."}
            lib = ctx["inventaire"]()
            trouves = [_entry(f) for f in lib["files"]
                       if q in (f.get("name") or "").lower()
                       or q in (f.get("tid") or "").lower()]
            return 200, _page(trouves, params)
        if nom == "platforms":
            return 200, {"platforms": ctx["plateformes"]()}
        if nom == "device":
            return 200, ctx["console"]()
        if nom == "job":
            return 200, ctx["job"]()
        if nom == "trash":
            return 200, {"items": ctx["corbeille"]()}

    if method == "POST":
        taches = {"scan": "scan", "convert": "convert", "push": "push"}
        if nom in taches:
            lance, motif = ctx["lancer"](taches[nom])
            if lance:
                return 202, {"started": True, "task": nom}
            # 409 and not 400: the request is valid, it is the server's STATE
            # that prevents it. A client retrying later is right to.
            return 409, {"error": "busy", "message": motif}

    return None


# ------------------------------------------------------------- specification

def _response(desc, example=None):
    contenu = {"application/json": {}}
    if example is not None:
        contenu["application/json"]["example"] = example
    return {"description": desc, "content": contenu}


_PAGINATION = [
    {"name": "page", "in": "query", "required": False,
     "schema": {"type": "integer", "minimum": 1, "default": 1}},
    {"name": "limit", "in": "query", "required": False,
     "schema": {"type": "integer", "minimum": 1, "maximum": LIMITE_MAX,
                "default": LIMITE_DEFAUT}},
]

SPEC = {
    "openapi": "3.1.0",
    "info": {
        "title": "Romule",
        "version": "1",
        "summary": "Read your library, watch a task, start a job.",
        "description": (
            "Stable subset of the Romule HTTP API. Within a major version no "
            "route disappears and no existing field changes name or type; new "
            "fields may appear, so ignore the ones you do not know.\n\n"
            "Romule's other `/api/...` routes exist and are **not** covered by "
            "this promise — they follow the interface and change with it.\n\n"
            "Authenticate with an API key: `X-Api-Key: rml_...`, or "
            "`?apikey=rml_...` where a header is impractical. A key reaches "
            "`/api/v1/` and nothing else."),
        "license": {"name": "AGPL-3.0-or-later"},
    },
    "servers": [{"url": "http://localhost:8787", "description": "Default"}],
    "components": {
        "securitySchemes": {
            "ApiKeyHeader": {"type": "apiKey", "in": "header",
                             "name": "X-Api-Key"},
            "ApiKeyQuery": {"type": "apiKey", "in": "query", "name": "apikey"},
        },
    },
    "security": [{"ApiKeyHeader": []}, {"ApiKeyQuery": []}],
    "paths": {
        "/api/v1/health": {"get": {
            "summary": "Liveness. The only route also used by the container probe.",
            "responses": {"200": _response("The service is up.")}}},
        "/api/v1/openapi.json": {"get": {
            "summary": "This document.",
            "responses": {"200": _response("The OpenAPI specification.")}}},
        "/api/v1/system": {"get": {
            "summary": "Version, licence, source, uptime.",
            "responses": {"200": _response(
                "Service identity.",
                # `__version__` rather than a literal: a specification example
                # announcing a version from two releases ago reads as a stale
                # specification.
                {"version": __version__, "api": "v1", "uptime_s": 8412,
                 "licence": "AGPL-3.0-or-later", "library_ready": True})}}},
        "/api/v1/stats": {"get": {
            "summary": "Counts and total size for the whole library.",
            "responses": {"200": _response(
                "Library statistics.",
                {"total": 412, "base": 180, "update": 150, "dlc": 82,
                 "bytes": 174929203200, "to_convert": 3})}}},
        "/api/v1/library": {"get": {
            "summary": "The inventory, paginated and sorted by name.",
            "description": ("An unreadable `page` or `limit` falls back to the "
                            "default; a value outside the bounds is clamped "
                            "into them."),
            "parameters": _PAGINATION + [
                {"name": "type", "in": "query", "required": False,
                 "schema": {"type": "string",
                            "enum": ["BASE", "UPDATE", "DLC", "INCONNU"]}}],
            "responses": {"200": _response(
                "One page of games.",
                {"page": 1, "limit": 50, "total": 412, "pages": 9,
                 "items": [{"key": "GAMES/Some Game [0100ABC].nsp",
                            "name": "Some Game", "type": "BASE",
                            "size": 4294967296, "playable": True}]})}}},
        "/api/v1/library/{key}": {"get": {
            "summary": "One game, by its key — the path relative to the library.",
            "parameters": [{"name": "key", "in": "path", "required": True,
                            "schema": {"type": "string"}}],
            "responses": {"200": _response("The game."),
                          "404": _response("No game with that key.")}}},
        "/api/v1/search": {"get": {
            "summary": "Search by name or title ID.",
            "parameters": [{"name": "q", "in": "query", "required": True,
                            "schema": {"type": "string"}}] + _PAGINATION,
            "responses": {"200": _response("One page of matches."),
                          "400": _response("q is missing.")}}},
        "/api/v1/platforms": {"get": {
            "summary": "Configured platforms and their local counts.",
            "responses": {"200": _response("Platforms.")}}},
        "/api/v1/device": {"get": {
            "summary": "State of the connected handheld.",
            "responses": {"200": _response("Device state.")}}},
        "/api/v1/job": {"get": {
            "summary": ("The running task, if any. Romule runs one task at a "
                        "time, so there is no task list."),
            "responses": {"200": _response(
                "Current task.",
                {"running": True, "label": "Conversion", "done": 2,
                 "total": 5, "detail": "Some Game.nsz"})}}},
        "/api/v1/trash": {"get": {
            "summary": "What is in the trash and can still be restored.",
            "responses": {"200": _response("Trash contents.")}}},
        "/api/v1/scan": {"post": {
            "summary": "Rescan the library.",
            "responses": {"202": _response("Task started."),
                          "409": _response("Another task is running.")}}},
        "/api/v1/convert": {"post": {
            "summary": "Convert the remaining .nsz/.xcz files.",
            "responses": {"202": _response("Task started."),
                          "409": _response("Another task is running.")}}},
        "/api/v1/push": {"post": {
            "summary": "Send pending games to the handheld.",
            "responses": {"202": _response("Task started."),
                          "409": _response("Another task is running.")}}},
    },
}


def documented_routes():
    """The (method, path) pairs the specification announces."""
    out = set()
    for path, ops in SPEC["paths"].items():
        for method in ops:
            out.add((method.upper(), path))
    return out


if __name__ == "__main__":       # `python3 -m romule.apiv1 > openapi.json`
    print(json.dumps(SPEC, indent=2, ensure_ascii=False))
