# Knob notches and slow turns (2026-11-19)

The User: "make the knobs less reactive when I turn them slower, to make very slow movement more precise. Sometimes
it is very hard to reach zero, or maybe we lack 'virtual' notches on our knobs (for instance in our modulation
matrix)." Decided (stage 1, `scratch/knob-precision.md`): a virtual notch at the zero of every bipolar value, ours and
stock's; p-locks notched too; nothing shown but the exact 0; stock's own acceleration and rest guard left as they are;
our popups turn finer when slow. Code: `csrc/knobs/` (knob.h holds every constant), hooks in `rec.c`, `fmt.c`, the
two ParameterSet vtables, `routes_pop.c`, `dest_pop.c`, `env2_page.c`. Gate: `knobnotch` (`scripts/emu_knobnotch.py`),
host test `test/test_knob_c.py`.

## Counts, not detents

The encoders have no physical detents (the User). The panel sends **counts**: the panel task sums each encoder's
counts and sends them every 4 ticks of the 60 Hz timer wheel (about 15 records a second, each clamped to ±30). All
the rules below are in counts per record, so a record's size is the turning speed (counts per 1/15 s). Stock's
integer knobs move one step every 3 counts (the knob step `0x4011364e`, divisor 3), so a "small move" is 3 counts.
How much rotation a count is depends on the panel's controller and cannot be measured in the emulator; the User can
set the feel by the constants after trying it.

## The notch

A knob-driven write that crosses a bipolar value's centre, or lands on it, from elsewhere is written as the centre:

| constant | value | meaning |
|---|---|---|
| `KN_HOLD` | 9 counts | once caught, the next 9 counts turned the same way keep it there (3 small moves); the 10th moves on |
| `KN_PASS` | 12 counts | a record of 12 counts or more (180 counts a second) passes the notch: a fast sweep goes through |
| `KN_HOLD_END` | 2,250 frames | a pause of 1.5 s ends a hold |

- A turn back releases at once. Another value under the knob (another page, row or record) has no hold.
- Starting at the centre moves at once (no hold from rest).
- **Knob-driven** means: written while the UI loop handles a knob's item (`rec.c smp_ui_pop` -> `kn_item`; cleared
  when the loop waits for its next item) and by the UI loop's own task (the running TCB `0x4664bcdc` is the one that
  took the item). CC, NRPN, Overbridge, loads, the sequencer and our own code never are, so they are never notched.
- Where: stock's sound values (the setter's write, `fmt.c smp_quant`), kit values (the kit setter's write,
  `fx_type_quant`: delay WID, SCF, ext-in BAL / LPAN / RPAN), p-locks (the sound and kit ParameterSets' LOCK_SET,
  vtable slots `0x401dbc50` and `0x401dbcd8` -> `kn_lock_snd` / `kn_lock_kit`: the old value is the step's lock, or
  the base when it has none), the routes and DEST popups' depths (their 0 deletes the route, as before), ENV2's H.
- The values (stock 1.12's bipolar formatters, `kn_centre`): at 64 (0x4000) chord NOT2..4, EQ GAIN, filter ENV, BAL,
  PAN, LFO1-3 SPD, FADE and DEP (the attenuverter), delay WID, ext-in BAL, LPAN, RPAN, SCF, FM MIX, COFF / AOFF /
  B1OF / B2OF, the FM macro offsets 227..234, TUNE (238, 242, 263, 293), retrig VFAD; HARM at 63; MIDI PB at 32.00;
  WAVETONE OFS1 / OFS2 at 50.00; the euclid rotations at 127. On our machines (records 238..260 mean their own
  controls) only the sample machines' TUNE, at its record's centre. The attenuverters' ±100 % are their travel ends
  (DEP +63..+63.99 and 0; ENV2 H 127 and 0), always exact; they get no notch (the User, D3).

## Our popups' turns

The routes popup, the DEST popup and ENV2's 0..127 knobs take raw counts. Before 2026-11-19 a count was a unit at
every speed, and a depth that had touched the top (0x7FFE) kept its fraction for good, so it never reached exactly 0
again and could not be deleted by turning. Now (`kn_units`, `kn_whole`):

| constant | value | meaning |
|---|---|---|
| `KN_POP_SLOW`, `KN_POP_DIV` | 4, 3 | a record of at most 4 counts moves 1 unit every 3 counts (the leftover kept 2 s, dropped on a turn back) |
| (between) | | 1 unit a count, as before |
| `KN_POP_FAST`, `KN_POP_FAST_MUL` | 12, 2 | a record of 12 counts or more moves 2 units a count |

Depths are kept on whole units (the first turn drops a fraction); the top end stays 0x7FFE (100 %).

## Cost

Per UI item: a type test. Per knob-driven write: a table lookup and a few compares. Nothing per frame, nothing on the
DSP. RAM: 8 x 32 bytes of knob state and nine counters, in our image's .data.
