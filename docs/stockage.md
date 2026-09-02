# Storage: why there is no database

Romule keeps its state in JSON files and derives the library from the
filesystem on demand. That is a deliberate choice, and it gets questioned
often enough — usually as *"shouldn't this be in SQLite?"* — that the answer
belongs in writing, with the measurements that produced it.

## The short answer

**A database would not have fixed what was actually slow.** The cost was never
reading data. It was rebuilding `pathlib.Path` objects, thousands of times per
page, to throw them away immediately.

## What was measured

A synthetic library of **20 000 titles / 39 525 files**, on a warm cache —
that is, the case a database is supposed to help. `/api/scan` is the request
every page load pays.

| | Before | After | |
|---|---|---|---|
| `/api/scan`, warm | 1 759 ms | **1 170 ms** | −33 % |
| Startup (import + first inventory) | 949 ms | **457 ms** | −52 % |

The profile before the change, on the 1 887 ms spent inside the scan:

| What | Time | Share |
|---|---|---|
| `Path.relative_to` | 744 ms | 39 % |
| `sorted()` over `Path` objects | 362 ms | 19 % — 504 724 comparisons |
| `stat` | 138 ms | called **twice** per file |
| JSON serialisation | — | did not appear in the top 18 |

That last line is the whole argument. If serialising the answer does not even
register, the bottleneck is not storage, and no storage engine can move it.

## What the fix was

Strings and `os.walk` instead of `pathlib` in the one loop that runs per file,
per request:

- `os.walk` prunes ignored folders in place, instead of descending into
  `_corbeille/` and rejecting each file afterwards;
- sorting is on `os.path.normcase(path)`, which reproduces `sorted(rglob("*"))`
  exactly — `PurePath.__lt__` compares that same normalised string;
- `os.scandir` (inside `os.walk`) already knows the file type, so the second
  `stat` is gone;
- `splitext` is computed once and carried, not recomputed;
- `titleid.pretty_name` no longer builds a `Path` to read `.stem`.

The rewrite was verified by replaying the **old loop verbatim** against the same
library and comparing every field of every entry: 4 433 files, zero
differences, including the cases the synthetic library does not produce on its
own — a file at the root, an ignored folder, accents, uppercase extensions,
deep nesting. A performance rewrite that silently changes its output is the
exact failure this project keeps finding.

## Where SQLite would still not help

The inventory is **derived, not stored**. Romule's source of truth is your
folder of games — you can drop a file in with Finder, and the next scan sees
it. A database would have to be reconciled against the filesystem anyway, on
every request, which means doing the walk *and* querying the database.

The rest of the state is small and rarely written:

| File | Typical size | Written |
|---|---|---|
| `_romule-config.json` | ~1 KiB | when a setting changes |
| `_romule-comptes.json` | ~400 B | when an account changes |
| `_romule-cles.json` | ~1 KiB | when a key is created or revoked |
| `_covers/` | one file per game | when artwork is fetched |

Whole-file rewrite is O(n) per write, which matters at ten thousand rows and
does not at ten. Atomic replacement (`os.replace`) already gives crash safety —
the property a database is usually brought in for.

## Where it *would* help, honestly

Three cases, none of which Romule is in today:

1. **Concurrent writers.** One process, one lock per file. A second Romule
   pointed at the same folder would corrupt state — but so would two of most
   self-hosted tools.
2. **Queries that are not "give me everything".** Everything currently ends up
   in the browser, which filters in memory in under 16 ms. Server-side search
   over hundreds of thousands of titles would want an index.
3. **History.** Romule keeps no timeline — no "when was this imported", no
   per-game event log. Adding one would want a table, not a JSON file that
   grows forever.

If any of those arrive, the conclusion changes. Until then, adding a database
would mean a schema, migrations, and a second source of truth to keep in step
with the filesystem — in exchange for a bottleneck that turned out to be
somewhere else entirely.

!!! note "The zero-dependency rule is not the reason"
    `sqlite3` ships with Python; using it would break no rule. The reason is
    that it would not have helped, and the measurement says so.

## Reproducing this

```sh
python3 outils/mesurer-perf.py --titres 20000
```

The thresholds are in the tool, and CI warns when one is crossed. If you make
this faster, that is the number to move.
