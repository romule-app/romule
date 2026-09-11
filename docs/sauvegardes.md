# Backups

A game can be downloaded again. Two hundred hours of progress cannot, and
neither can the account file or the covers you spent an evening fixing by hand.

Romule used to do a third of this job, in three places, and none of them said
where the copy landed: the configuration went into `_sauvegardes/`, the
console's game saves into `_saves/`, and the library sat in one folder. All
three wrote to **the same disk as the thing they protected**, which is the one
failure a backup exists for.

**Settings → Backups** is that job, done in one place.

## The four questions

Everything is chosen in one dialog, in the order you ask yourself the
questions.

### What

| Source | Where it is read | Note |
|---|---|---|
| Game saves | the console, over adb | Skipped, with a line in the journal, when no console answers |
| Games | the library | |
| Updates | the library | |
| DLC | the library | |
| Covers and entries | the data folder | Small, and slow to rebuild |
| Configuration and accounts | the data folder | Includes the history `backup.py` already kept |

Each row shows what it weighs before you tick it. Game saves are the exception
and say so: their size is only known while the console is being read.

### From which console

Only asked when game saves are part of the batch. It selects the driven
console — the same setting as **Settings → Your console → My consoles** — and
says whether it is connected, because that decides whether its saves make it
into the batch at all.

### Where

Romule offers what it finds rather than a field to type into:

- **a plugged-in disk** — anything mounted under `/Volumes`, `/media`,
  `/run/media` or `/mnt`. This is the destination that survives the failure;
- **a synced folder** — Dropbox, Google Drive, OneDrive, Nextcloud, pCloud,
  Syncthing. Romule writes files into the folder their own client already
  watches; that client carries them away. **No account, no token and no
  network call from Romule** — which is also why it keeps working when a
  provider changes its API;
- **the service's own data folder**, offered last and labelled *Same machine*.
  A copy beats no copy, and it is still the one that goes down with the disk.

Anything else is reachable through **Choose another folder…**, which browses
the host and can create folders as it goes.

!!! warning "Bounded by `ROMULE_BASES`"
    A destination outside the declared folders is refused, and not created.
    The reasoning is the same as for the folder picker: in a container the
    mounts are the allow-list and the kernel enforces it. See
    [Roles and access](roles.md).

### How often

The same five presets as every other scheduled task — never, at startup,
hourly, every six hours, nightly at a chosen hour. The setting is shared with
**Settings → Maintenance → Schedule**: one setting, two places to reach it.

## What a run does

1. resolves the chosen sources into a list of files, with their total size;
2. **refuses if the destination has not got the room** — before copying
   anything. Finding out at 94 % is finding out too late, and it leaves a half
   batch that looks like a whole one. If old batches are in the way, rotation
   runs early to make room, and says so;
3. copies, with progress and an ETA computed from the measured rate. The task
   can be paused and cancelled like any other;
4. writes `manifeste.json` into the batch;
5. rotates: oldest first, down to the number of batches asked for.

Every step goes into the journal. An unattended copy that says nothing is a
copy nobody checks.

## What a batch looks like

```
/Volumes/Sauvegardes/
  romule-2026-09-11_031500/
    manifeste.json
    sauvegardes/storage_emulated_0_Android_data_…/
    jeux/Zelda/Zelda.nsp
    config/_romule-config.json
```

`manifeste.json` says what the batch holds, when it was taken, from which
library, and whether it finished:

```json
{
  "outil": "romule",
  "date": "2026-09-11 03:15:00",
  "sources": ["sauvegardes", "jeux"],
  "fichiers": 1284,
  "octets": 41203847168,
  "complet": true,
  "ludotheque": "/library"
}
```

Plain folders and plain files: **a batch is restored by copying it back**, with
or without Romule. That is the point of a backup, and it is why nothing here is
an archive format.

## Rotation, and what it will not delete

Rotation deletes. So it only ever looks at folders that carry **both** our name
prefix and our manifest — a folder of holiday photos sitting beside the batches
is not a candidate, and neither is a folder that merely happens to be named
like one.

An **interrupted** batch goes before a complete one: keeping half a copy in
place of a whole one is the one way rotation could make things worse.

Two backups in the same second get a suffix rather than one overwriting the
other. An existing batch is a backup, and Romule does not write over a backup.

## What this is not

It is **not** a sync, and not a versioned archive. Each batch is a full copy of
what you ticked. Backing up a whole library every night will fill any disk you
point it at — which is what `backup_keep` is for, and why the default only
carries game saves.
