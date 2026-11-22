# The preset browser's ENGINE filter

2026-11-12. `csrc/presets/engfilt.c`, `csrc/presets/hooks.S`, `src/dnfw/waverider/engfilt.py`,
`test/test_engine_filter.py`. Built and run in the 1.12 emulator; not on the unit, not gated.

## What the User sees

PRESET > LOAD (or SAVE / MANAGE) > [LEFT] opens stock's SORTING menu. It now has its own **ENGINE** row
between FILTER and SEARCH. The User asked for "a separate engine filter" (the first design put the
engines inside FILTER's list).

- YES on ENGINE opens its own tick list, built the way stock builds FILTER's: `<CLEAR>`, then one row
  per MACHINE SEL engine, in MACHINE SEL's order and with its names. The rows are FM TONE, FM DRUM,
  WAVETONE, SWARMER, MACHINEDRUM, MONOMACHINE, SOPHIE, PLAITS, TB-303, DRONE, ANALOG, ONESHOT, WERP,
  STRETCH, REPITCH, SLICE and GRID, plus BOUNCE when it is listed. MIDI stays in stock's FILTER, as stock
  has it.
- YES on an engine ticks it and moves down, as on a tag. NO leaves, as from FILTER's list.
- Ticked engines are combined with **OR** (a preset has one machine). The engine set is combined with
  **AND** against FILTER (tags, MIDI, NO TAG), the bank and the search.
- ENGINE's `<CLEAR>` clears the engines only, and FILTER's `<CLEAR>` clears the tags only.
- The SORTING row reads `ENGINE *` while an engine is ticked, like `FILTER *`.
- MONOMACHINE is one row, because its five engines share type 6.

## How (stock 1.12, measured)

- **The data is stock's.** The preset library (singleton `*0x44648940`, class vtable `0x40208ea4`) keeps
  2048 entries of 36 bytes at `lib + 3628`: +0 used, +4 version, +8 name[16], +24 tags, **+32 the
  machine**. Stock's indexer (`0x4012e2c0..`) reads one sector of each preset at boot and after each
  save, and stores byte 244 of the stored sound there, sign-extended (4 for MIDI, −1 if unreadable). The
  getter is the library's vtable +28 (`0x4012d1cc`). So the filter adds no +Drive read.
- **The test.** The preset view's rebuild (`0x400ac7xx`) tests each slot in turn: tags, NO TAG, search,
  show-all, bank, then MIDI (`0x400ac9a8`). `eng_test_hook` takes that spot. While engines are ticked it
  first applies `eng_match`; a preset that fails goes where stock's failed test goes (`0x400ac9bc`).
  Every other preset then gets stock's MIDI test as it was.
- **The row and the list.** The SORTING builder (`0x400acc9e`) makes each row as an item:
  `0x401173b8(item, label, action, f3, f4, -1, 8)`, added with `0x40116bee(view+448, item)`. The
  callbacks are std::functions: a heap closure, a manager and an invoker. `eng_sort_hook`
  (`0x400ad194`, after FILTER's row) adds ENGINE with FILTER's managers and our invokers. The list
  (`eng_list`) is built the way FILTER's builder `0x400ab908` builds its own:
  - the menu is cleared (`0x40116d10`);
  - `<CLEAR>` is added with stock's label (`0x400a8566`);
  - each engine row gets a closure {view, row} with the tag rows' manager (`0x400a9950`);
  - the cursor goes to the top (`0x401168b8(menu, 0, 0)`).
- **The constructor** (`0x400ac62c`) clears the engines when it clears stock's filters.

## Measured in the 1.12 emulator (this build's own snapshot, `scratch/be/emu.sh`)

| step | result |
|---|---|
| SORTING | ADD TO PRESET POOL, SEL BANK, SORT, FILTER, **ENGINE**, SEARCH |
| ENGINE | `<CLEAR>`, FM TONE … GRID; ticks drawn as stock's |
| FILTER | stock's again: … FAV, MIDI, NO TAG |
| ENGINE FM DRUM | PUNCHBASS, THE GRAND PIANO, THE CELLO … (the index's type 2; PUNCHBASS loads as FM DRUM) |
| a SOPHIE track (type 20 then, 53 since 2026-11-18) saved to B:172, ENGINE SOPHIE | FRAGILE BEINGS alone |
| + FILTER EVOL | FRAGILE BEINGS (it has EVOL); SORTING shows `FILTER *` and `ENGINE *` |
| + FILTER KICK | stock's NO MATCHES |
| ENGINE FM DRUM + SOPHIE | the FM DRUM presets, then B:172 FRAGILE BEINGS |
| FILTER BASS + ENGINE FM DRUM, SOPHIE, then ENGINE `<CLEAR>` | all BASS presets; `ENGINE` with no `*`, `FILTER *` kept |
| faults | none, every run |

Not verified: on the unit; with the User's own +Drive (DN1-imported presets carry the machine their
conversion gives); the ship gate.
