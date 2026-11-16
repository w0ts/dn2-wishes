# The modulation matrix (OS 1.12)

More routes than stock's one per LFO. Decided by the User, 2026-11-11:

- up to **16 LFO routes a track**, shared by LFO1-3; stock's route 1 of each LFO counts, and is filled first;
- ENV1 and ENV2 (phase 3) with four destinations each;
- MOD SETUP keeps stock's four per source;
- a **constant-cost** evaluator: a frame costs the same whatever is routed;
- the popup (phase 4): FUNC + short push opens it on a parameter, FUNC + long push (0.6 s) resets the parameter;
  layout A, a moving bar, a LOCKS strip, "13/16" and FULL.

Phases: 1 the wishes record (`docs/wishes-record.md`), **2 the evaluator (this page)**, 3 the envelopes and their
MOD pages, 4 the popup, 5 presets and Transfer carrying the record.

## Where the routes live

A sound's routes are one field of its wishes record, tag `WT_MX_ROUTES` (0x0010, neither must-understand nor tied to
the machine), four bytes a route:

| byte | |
|---|---|
| 0 | the source: 0 LFO1, 1 LFO2, 2 LFO3 (3 ENV1, 4 ENV2 from phase 3) |
| 1 | the destination: a slot of the voice row, 25..100 (a sound parameter) |
| 2-3 | the depth, big-endian, in stock DEP's units: 0..0x7f00, 0x4000 adds nothing |

At most 15 routes are laid out (16 a track, at least one of them stock's route 1). Anything out of range is
skipped. A route into an LFO's own controls (slots 1..24) is not offered: it would land after that LFO has read
them. Stock's DEST, and the cascade (`docs/modulation-more.md`), still reach them.

## How a route is heard

Stock's evaluator `0x40137a06` walks the 16 voice rows. For each row it runs LFO3, then LFO2, then LFO1, and adds
each LFO's route 1 into its DEST cell (`0x40137d6a`):

    cell = clamp(cell + mac((DEP - 0x4000) x 2, out), 0, 0x7f00)

`out` is the LFO's output after its fade, kept at its state + 84. Row v's LFO l is at `0x44640C1C + 120 v + 40 l`
[measured in the 1.12 bytes]. A row's cells are at B + 34 + 202 v + 2 slot, with B the evaluator's first argument
(the mirror OUT, `0x800068e4`).

The frame's evaluator call (`0x400272d4`) is modulation's `mod_eval` (`csrc/modulation/hooks.S`). It runs the
cascade's pre-pass, then stock's evaluator with the caller's seven arguments, then `mx_eval(B)`
(`csrc/matrix/matrix.c`). That adds each row's routes with stock's own instruction (`mac.l`, then `movclr.l`, under
the frame's fractional MACSR), clamping after each route as stock does. A route at depth D is heard exactly as stock's
route 1 at DEP D. The gate step `matrix` (`scripts/emu_matrix.py`) checks this frame by frame on every row, and with
three routes into one slot listed in stock's order (LFO3, LFO2, LFO1).

**A voice's track** is the kit sound it plays. Stock writes the sound a voice plays at `0x800052a8[v]`
(`0x4002549c`, the same call that copies the sound's parameters into the voice's row; LFO4 keyed on it on 1.11,
measured on the instrument). The frame takes (sound - kit - 52) / 1163, a multiply exact for every whole sound,
and checks the sound against that track's. A voice on any other sound gets no routes.

**Constant cost.** Every row runs all 15 routes every frame. An unused route adds 0 into a scratch row of ours, at
an offset that fits every row, so no route and every route take the same instructions. The clamp's two branches are
the only difference.

## Read in the UI pass, never in the frame

`mx_poll` (from `page.c` `wr_poll`) lays the tables out again when any record changed (`wish_edits`, counted at every
change to an entry: made, copied, cleared, put, read from its cell) or when the kit moved. Each track's routes go into
its spare table, which then becomes the live one; the frame takes it from its next row. The frame never takes the
record's lock and never looks a sound up.

## RAM

`MX_RAM` `0x476F0000`, 16 KB (`dnfw.waverider.pages`, `docs/memory-map.md`): each track's table twice, an empty
table, the scratch row (16 x 101 words).

## Known limits

- A voice playing a sound other than its track's kit sound (a sound lock) hears no routes of ours. Stock's route 1
  still plays.
- The depths are the record's, not modulated: stock's DEP is a cell of the row (LFOs and the six sources can move
  it), a route's depth is fixed.
- A route's slot means what that slot means on the sound's machine. The routes are kept when the machine changes
  (the field is not tied to the machine). What stock does with DEST then is not checked here.
