# Presets

Digitone II sounds (`.dn2pst`) for the machines this firmware adds, made with this repository's own tools: an INIT
and a set of sounds for each machine of ours, and an INIT for each of the other machines. Download them all as one zip from the
[presets page](https://w0ts.github.io/dn2-wishes/presets.html) (size and sha256 there), or take single files from the
folders below.

<!-- sets: presets_sync.py writes this table -->
| folder | sounds | what |
|---|---|---|
| [`AN2/`](AN2/) | 25 | ANALOG 2 (type 51): an INIT and sounds after Optimist's factory presets |
| [`DRN/`](DRN/) | 10 | DRONE (type 52): an INIT and sounds after Optimist's factory presets |
| [`JUN/`](JUN/) | 8 | JUNO (type 50): the Juno-106 voice, an INIT and sounds after Optimist's JUNO presets |
| [`SPH/`](SPH/) | 15 | SOPHIE (type 53): an INIT and drum sounds after Schwung Sophie's factory kit |
| [`303/`](303/) | 5 | TB-303 (type 54): an INIT and acid sounds after Optimist's ACID presets |
| [`PLT/`](PLT/) | 7 | PLAITS (type 55): an INIT and sounds after Optimist's PLAITS presets |
| [`DRM/`](DRM/) | 55 | DRUM (type 56): KICK, SNARE, CLOSED and OPEN HAT and TOM sounds (TYPE on page 1 H); a name ending +DS, +FZ, +FD or +TP wants the DIST, FUZZ, FOLD or TAPE insert on its track (the project's, not the sound's) |
| [`MD/`](MD/) | 14 | MACHINEDRUM (type 5, PERC): an INIT and drum sounds of the Machinedrum models |
| [`MNM/`](MNM/) | 15 | MONOMACHINE (type 6): an INIT and sounds of each engine (SID, WAVE, DDRW, DENS, VO-6) |
| [`INIT/`](INIT/) | 14 | an INIT sound for each machine that is not ours: Elektron's FM TONE, WAVETONE, FM DRUM, SWARMER; upstream's ONESHOT, WERP, STRETCH, REPITCH, GRID, SLICE, FLEX and FM+ STAT / PAR / DYN |
<!-- /sets -->

## Which firmware they need

Our machines are machine types 50 and up (JUNO 50, ANALOG 2 51, DRONE 52, SOPHIE 53, TB-303 54, PLAITS 55;
`docs/machine-types.md`), plus MACHINEDRUM (5) and MONOMACHINE (6). A sound stores its machine by that number, so
these presets need a Wishes build made since our machines moved to 50..55 (2026-11-18): the release on the
[builder page](https://w0ts.github.io/dn2-wishes/) (v0.62.2 or later). On an older build, or on stock firmware, a
sound of one of our machines loads as another machine or as a silent one. The INIT set's sounds are for machines
that are not ours (Elektron's and upstream's); they are made for this firmware too and tested only on it.

## How to load them

1. Unzip the download.
2. Open **Elektron Transfer** with the Digitone II connected over USB.
3. Send the `.dn2pst` files to a bank of the Digitone II's +Drive presets (a free bank keeps your own sounds apart).
4. On the Digitone II, load one onto a track as any other preset.

Back up your +Drive with Transfer first, as before any change.

## How they are refreshed

The presets are made in a folder outside the repository. `scripts/presets_sync.py FOLDER` checks every file in it
for anything private (only Elektron's own fields, no +Drive slot, no text but the sound's name, the machine one of
the set's types, only INITs of machines that are not ours) and, when all pass, copies the new and changed ones into
their set's folder here and rewrites the table above; one failing file and nothing is copied. A new machine of ours
is one row in its `SETS`. `scripts/presets_sync.py --check` checks this folder (the tests run it).
`scripts/presets_zip.py OUTDIR` makes the download, byte for byte the same from the same files;
`scripts/make_site.sh` runs it for the presets page.
