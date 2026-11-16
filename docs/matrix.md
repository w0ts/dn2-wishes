# The modulation matrix (OS 1.12)

More routes than stock's one per LFO. Decided by the User, 2026-11-11:

- up to **16 LFO routes a track**, shared by LFO1-3; stock's route 1 of each LFO counts, and is filled first;
- ENV1 and ENV2 (phase 3) with four destinations each. 2026-11-12, the User: ENV1 **is** stock's AMP envelope (still on
  the amp, now also routable); ENV2 is "just a clone of env1", routed only;
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
| 0 | the source: 0 LFO1, 1 LFO2, 2 LFO3, 3 ENV1, 4 ENV2 |
| 1 | the destination: a slot of the voice row, 25..100 (a sound parameter) |
| 2-3 | the depth, big-endian, in stock DEP's units: 0..0x7ffe (DEP's own range), 0x4000 adds nothing |

At most 15 LFO routes are laid out (16 a track, at least one of them stock's route 1) and four for each envelope.
Anything out of range is skipped. A route into an LFO's own controls (slots 1..24) is not offered: it would land after that LFO has read
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

## The envelopes (phase 3)

Stock's AMP envelope runs on the SHARC (section 7), and the ColdFire cannot read it. ENV1 and ENV2 are a **ColdFire
clone** of it (the User's choice A), one pair a voice, stepped once a frame in `mx_eval` (one DSP block, 32
samples) before the routes. The amp's own envelope is untouched; nothing is sent to the DSP.

- **ENV1** takes its knobs from the voice row's own AMP cells every frame: ATK 81, HOLD 82, DEC 83, SUS 84,
  REL 85, MODE 91, RSET 92. Those are what the DSP is sent, so LFO modulation and p-locks of the AMP page reach
  ENV1 as they reach the amp.
- **ENV2** takes the same seven from the sound's wishes record (`WT_MX_ENV` 0x0011: ATK HOLD DEC SUS REL MODE
  RSET, a byte kept 0). With no field it uses stock's own defaults (records 62..66, 73, 74: ATK 8, HOLD 127, DEC 32,
  SUS 96, REL 24, ADSR, RSET on).
- **ENV2's locks** (the User: "Yes, p-lockable", all six): with grid recording on and a trig held, a knob on ENV2's
  page sets that step's lock on every held step, as stock's own knobs do; the page shows the held trig's values, a
  lock drawn as stock draws one. The locks are records of the pattern's lock pool of ours, kinds 3..8 of slides'
  (`csrc/slides`, table-driven since): stored ids 203..208 (ATK DEC SUS REL MODE RSET; `docs/lock-id-table.md`),
  RAM heads 0x53..0x58. They are kept, cleared, copied and pasted (page and trig) with slides' own; the lock list's
  tail carries the step's six values (`sl_build`), and at the trig (`sl_apply`) they become that voice's ENV2 knobs
  until its next trig, over the record's. A full pool refuses a lock, as stock does. Stock firmware drops them on
  LOAD and keeps everything else (as slides).
- **Note-on and note-off** come from DRONE HOLD's hooks, which every note passes through: `hold_len` (a note that
  plays, not one HOLD drops) and `hold_final` (the frame's composed amp note-off word, `+36`).

**Measured in Elektron's own DSP code** (the SHARC runner; the level is the DSP's word `0x2547c8`, found by searching
its memory for the amp's measured gain; `csrc/matrix/amp_env.json`, `scripts/gen_matrix_env.py` ->
`csrc/matrix/env_table.h`):

| stage | law | measured |
|---|---|---|
| attack | linear, a length in samples | all 128 knobs: the level after n blocks is s (32 n + 0.5) from a reset, to 6e-7; s = 1/33, 1/48, 1/67, 1/90 for knobs 5..8; knobs 0..4 end inside the first block |
| decay | geometric toward SUS, a ratio a block | all 128 knobs, the same ratio over 3 blocks to 3e-7; knob 127 does not fall; DEC 40 gives the 1,742 ms (60 dB) of `docs/stock-units.md` |
| release | geometric toward 0 | all 128 knobs: the same table as the decay's, to the last bit of the DSP's float |
| MODE 1 (ADSR, the default) | attack, decay to SUS, at the note-off a release from the level reached | |
| MODE 0 (AHD) | attack, HOLD, then a decay to 0 at DEC's rate; SUS and REL unused | a note-off in the attack starts the decay; HOLD 127 (the default) lasts until the note-off; HOLD 0 none; a timed hold is not ended by a note-off |
| RSET | 1: a note-on restarts from 0; 0: the attack goes on from the level reached | |

Knobs 8 and 9 give the same values in every table, as do 12 and 13, and 17 and 18: the DSP steps its own curve.
Its memory holds no table of these (L1, L2 and DDR searched), so the clone's tables are the measurements.

**Checked:** the C against the model on the host (`test/test_matrix_c.py`, every case), the target's C against the
model in the ColdFire emulator through HOLD's own hooks (gate step `matrix`, its `env` scenario), and the model
against stock's own envelope in the SHARC runner, block by block (`scripts/sharc_matrix_env.py`, gate step
`envclone`).

## The AMP pages

[AMP] on stock's AMP page now steps AMP 1/3 (stock's) -> 2/3 (ENV2) -> 3/3 (the scope) -> 1/3. Each page's place is
one constant in `csrc/waverider/amp_pages.h` (the User: the scope "might move elsewhere"). ENV2's page
(`csrc/matrix/env2_page.c`) lays out the envelope as stock's AMP page does: A ATK, B DEC, C SUS, D REL, E RSET,
F MODE (ADSR / AHD). HOLD is not on stock's 1.12 page either. The destinations are set from the knob popup (phase 4).

## The routes popup (phase 4)

`csrc/matrix/routes_pop.c`, the owner's layout A (`scratch/modulation/dest-knob.md` §1, §7 and its mock-ups):

- **FUNC + push** on a sound page: the press is ours. Let go within 0.4 s (600 frames): the popup opens on that
  knob's parameter. Still held at 0.6 s: the parameter is reset to its record's default (stock's own `setValue`,
  as a knob writes it). The knob's parameter is the one stock's cell routine drew in that place (`page.c`
  `wr_cell` -> `mxp_cell`; the left panel's LEV is not a place).
- **The screen:** a slim header with the parameter's name, then a row a source: LFO1-3 (their icon is their WAVE),
  ENV1, ENV2. A row at depth 0 is an empty line; a route shows its depth (DEP's units, -64..+63) and the moving bar
  (the outline the reach, a tick the depth, the solid bar the offset the source applies now on the voice the track
  last played). The lit row shows its count: the LFOs' shared pool "n/16", an envelope's "n/4", FULL.
- **Editing:** turning the knob sets the lit row's depth live; push-and-turn (or UP/DOWN) moves the lit row. Turned
  from 0, an LFO's row takes its stock route 1 when that is free (DEST and DEP, so a stock unit plays it), else a
  route of the record; a route left at 0 goes when the popup closes.
- **Closing:** the same knob pushed, YES, FUNC + push, another knob turned, any key that leaves, a track change, a
  stock question, 6 s untouched: kept. NO: every change undone.
- **Refused** (the push stays stock's): a trig held, a stock question, a page of ours up, a MIDI track, a parameter
  that is not a sound parameter of the voice row (slots 25..100).

- **LOCKS** (the bottom line): this parameter's p-locks on the track's pattern (the pool's record of its slot and
  track): the 16 steps of the page playing, a filled cell a locked step and the playing step underlined, then a tick
  a page, tall when that page holds a lock, the page playing underlined.

Next in this phase: MOD SETUP's rows (VEL MW PB AT BC KEY, stock's four routes a source).

## Read in the UI pass, never in the frame

`mx_poll` (from `page.c` `wr_poll`) lays the tables out again when any record changed (`wish_edits`, counted at every
change to an entry: made, copied, cleared, put, read from its cell) or when the kit moved. Each track's routes go into
its spare table, which then becomes the live one; the frame takes it from its next row. The frame never takes the
record's lock and never looks a sound up.

## RAM

`MX_RAM` `0x476F0000`, 16 KB (`dnfw.waverider.pages`, `docs/memory-map.md`): each track's table twice, an empty
table, the scratch row (16 x 101 words).

## Known limits

- ENV1 and ENV2 step once a frame (32 samples): where a stage ends inside a block, the clone is one block behind
  the DSP for that block. They also hear a note one frame before the DSP does.
- HOLD 1..126 in AHD mode is not measured: the clone holds until the note-off, as at 127. On 1.12 HOLD is not on the
  AMP page; its default is 127.

- A voice playing a sound other than its track's kit sound (a sound lock) hears no routes of ours. Stock's route 1
  still plays.
- The depths are the record's, not modulated: stock's DEP is a cell of the row (LFOs and the six sources can move
  it), a route's depth is fixed.
- A route's slot means what that slot means on the sound's machine. The routes are kept when the machine changes
  (the field is not tied to the machine). What stock does with DEST then is not checked here.
