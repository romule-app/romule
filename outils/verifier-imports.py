#!/usr/bin/env python3
"""Every module a file uses is a module that file imports.

This tool was written during the rename of the package's modules into English,
and it was written because the rename had already produced exactly the failure
it looks for. `reseau.py` became `net.py`; a multi-line `from . import (...)`
kept the old name while the twenty call sites in the same file moved to the new
one. The file still parsed, `python3 -m romule` still started, and the test
families that would have caught it were the server ones — the ones that cannot
run on a machine whose ephemeral ports are exhausted.

A `NameError` on a route nobody exercised is a defect that ships.

The check is static and reads the AST, not the text: `net.check(...)` is an
attribute access on a `Name`, and the set of those names must be covered by
what the module imports, by its own globals, and by its locals. Anything else
would have to be a builtin, and builtins are known.

It also reports the reverse — a module imported and no longer used — because
that is the other half of the same rename mistake, and because a stale import
is what makes the first half survive review.

And it reads the package's own signatures, so that a call keeping a KEYWORD a
rename has moved is caught the same way. That half was added because the first
half had just missed two of them: `apikeys.liste(avec_revoquees=…)` became
`apikeys.list_all(with_revoked=…)`, and two call sites kept the old name. It
then immediately found two more, in `comptes.py`.

    python3 outils/verifier-imports.py            # the shipped package
    python3 outils/verifier-imports.py --tout     # tools and tests too
    python3 outils/verifier-imports.py --autotest # checks the tool bites

Exits 0 if nothing, 1 otherwise.
"""

import ast
import builtins
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Names that are attribute-accessed but never imported, and legitimately so:
# they are bound by the runtime or by a `for` target the AST walk does not
# model. Each one is here with its reason, never as a blanket exception.
ALLOWED = {
    "self", "cls", "super",
}

_BUILTINS = set(dir(builtins))


def _bound_names(tree):
    """Every name the module binds: imports, assignments, defs, arguments."""
    bound = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                bound.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bound.add(n.id)
        elif isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, ast.alias):
            bound.add((n.asname or n.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            bound.update(n.names)
    return bound


def _module_imports(tree):
    """Only the names bound by an import — the ones a rename moves."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                out.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
    return out


def _attribute_roots(tree):
    """The names on the left of a dot: `net` in `net.check(url)`."""
    return {n.value.id for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}


def _used_names(tree):
    """Every name the module reads, whatever the shape."""
    return {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def inspect_source(source, name="<source>"):
    """Returns (missing, stale) for one file's source."""
    tree = ast.parse(source, filename=name)
    bound = _bound_names(tree) | _BUILTINS | ALLOWED
    missing = sorted(_attribute_roots(tree) - bound)
    imports = _module_imports(tree)
    # `__init__` re-exports on purpose, and a module imported for its side
    # effect has no name to read. Both are normal; neither is a rename mistake.
    stale = sorted(imports - _used_names(tree)) if "__init__" not in name else []
    return missing, stale


GOOD = '''
from . import net

def f(url):
    return net.check(url)
'''

MISSING_IMPORT = '''
from . import reseau

def f(url):
    return net.check(url)
'''

STALE_IMPORT = '''
from . import net, matching

def f(url):
    return net.check(url)
'''

LOCAL = '''
import json

def f(payload):
    parsed = json.loads(payload)
    return parsed.get("x")
'''

# One package module's signature, for the keyword check below.
SIGS = {"totp": {"verify": ({"secret", "entered", "when", "used"}, False)},
        "loose": {"anything": (set(), True)}}

GOOD_KEYWORD = "totp.verify(s, e, used=set())"
STALE_KEYWORD = "totp.verify(s, e, utilises=set())"
KWARGS_KEYWORD = "loose.anything(whatever=1)"
UNKNOWN_MODULE = "json.dumps(indent=2)"


def autotest():
    """A check that never bites protects against nothing."""
    ok = True
    cases = [
        ("a correct import passes", GOOD, [], []),
        ("a renamed module is caught", MISSING_IMPORT, ["net"], ["reseau"]),
        ("an import no longer used is reported", STALE_IMPORT, [], ["matching"]),
        ("a local name is not a missing import", LOCAL, [], []),
    ]
    for name, src, want_missing, want_stale in cases:
        m, i = inspect_source(src, name)
        if m == want_missing and i == want_stale:
            print("  OK    %s" % name)
        else:
            ok = False
            print("  FAIL  %s: missing=%s stale=%s" % (name, m, i))

    # The keyword half. A renamed parameter is the same mistake as a renamed
    # module, and Python reports it just as late.
    kw_cases = [
        ("a keyword the callee accepts passes", GOOD_KEYWORD, 0),
        ("a keyword left over from a rename is caught", STALE_KEYWORD, 1),
        ("a callee taking **kwargs accepts anything", KWARGS_KEYWORD, 0),
        ("a module outside the package is not judged", UNKNOWN_MODULE, 0),
    ]
    for name, src, want in kw_cases:
        found = len(_bad_keywords(ast.parse(src), SIGS))
        if found == want:
            print("  OK    %s" % name)
        else:
            ok = False
            print("  FAIL  %s: found %d, wanted %d" % (name, found, want))
    return 0 if ok else 1


# ---------------------------------------------------------------- keywords
#
# The second half of the same rename mistake. `apikeys.liste(avec_revoquees=…)`
# became `apikeys.list_all(with_revoked=…)`; the module and the function moved,
# two call sites kept the old KEYWORD. Python only complains when the line runs,
# and the lines that ran were in the families this machine cannot start.
#
# So we read the package's own function signatures and check every
# `module.function(keyword=…)` call against them. Only intra-package calls: we
# know nothing about the standard library's signatures, and guessing would
# produce noise instead of findings.


def _signatures(paths):
    """{module: {function: (accepted keywords, takes **kwargs)}}."""
    out = {}
    for p in paths:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=p.name)
        except (OSError, SyntaxError):
            continue
        funcs = {}
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = n.args
                names = {a.arg for a in args.args + args.posonlyargs + args.kwonlyargs}
                funcs[n.name] = (names, args.kwarg is not None)
        out[p.stem] = funcs
    return out


def _bad_keywords(tree, sigs):
    """Calls of the shape `module.function(keyword=…)` the signature refuses."""
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)):
            continue
        known = sigs.get(f.value.id, {}).get(f.attr)
        if not known:
            continue
        accepted, takes_kwargs = known
        if takes_kwargs:
            continue
        for kw in n.keywords:
            if kw.arg and kw.arg not in accepted:
                bad.append((n.lineno, "%s.%s(%s=…)" % (f.value.id, f.attr, kw.arg)))
    return bad


def files_to_read(every):
    yield from sorted((RACINE / "romule").glob("*.py"))
    if every:
        yield from sorted((RACINE / "outils").glob("*.py"))
        yield from sorted((RACINE / "romule" / "tests").rglob("*.py"))
        yield RACINE / "lancer_tests.py"


def main(argv):
    if "--autotest" in argv:
        print("-- self-test of the detector --")
        return autotest()
    faults = 0
    sigs = _signatures(sorted((RACINE / "romule").glob("*.py")))
    for p in files_to_read("--tout" in argv):
        try:
            source = p.read_text(encoding="utf-8")
            missing, stale = inspect_source(source, p.name)
            keywords = _bad_keywords(ast.parse(source, filename=p.name), sigs)
        except (OSError, SyntaxError) as exc:
            print("  SKIP    %-30s %s" % (p.name, exc))
            continue
        rel = p.relative_to(RACINE)
        for m in missing:
            print("  MISSING %-30s uses `%s.` but never imports it" % (rel, m))
            faults += 1
        for i in stale:
            print("  STALE   %-30s imports `%s` and never uses it" % (rel, i))
            faults += 1
        for line, call in keywords:
            print("  KEYWORD %-30s %s:%d does not accept that name"
                  % (rel, call, line))
            faults += 1
    print("   %d import problem(s)." % faults)
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
