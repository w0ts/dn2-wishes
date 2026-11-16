# The preset browser's ENGINE filter

2026-11-12. `csrc/presets/engfilt.c`, `csrc/presets/hooks.S`, `src/dnfw/waverider/engfilt.py`,
`test/test_engine_filter.py`. Built and run in the 1.12 emulator; not on the unit, not gated.

## What the User sees

PRESET > LOAD (or SAVE / MANAGE) > [LEFT] > FILTER is stock's tick list: `<CLEAR>`, the 32 tags, MIDI,
NO TAG. Between the tags and MIDI it now has one row per MACHINE SEL engine, in MACHINE SEL's order and
with its names: FM TONE, FM DRUM, WAVETONE, SWARMER, MACHINEDRUM, MONOMACHINE, SOPHIE, PLAITS, TB-303,
DRONE, ANALOG, ONESHOT, WERP, STRETCH, REPITCH, SLICE, GRID (and BOUNCE when listed). YES ticks a row
and moves down, as on a tag.

- Engines combine with **OR** among themselves (a preset has one machine). Stock's MIDI row joins that
  set when ticked.
- The engine set combines with **AND** with the tags, the bank (SEL BANK), the search and SHOW ALL SLOTS,
  as stock's filters combine with each other.
- `<CLEAR>` clears the engines too. FILTER's `*` in the SORTING menu shows while an engine is ticked.
- The set lasts as stock's own filters do: the view's constructor clears both.

MONOMACHINE is one row: its five engines share type 6 and the preset stores the type, not ENGN.

## How (stock 1.12, measured)

- **The data is stock's.** The preset library (singleton `*0x44648940`, class vtable `0x40208ea4`) keeps
  2048 36-byte entries at `lib + 3628`: +0 used, +4 the stored version, +8 name[16], +24 tags, **+32 the
  machine**. Its indexer (`0x4012e2c0..`) reads one sector of each preset at boot and after each save,
  and stores the stored sound's byte 244 sign-extended (4 for a MIDI preset, −1 if unreadable). The
  getter is the library's vtable +28 (`0x4012d1cc`). So the filter adds no +Drive read.
- **The list.** The preset view's rebuild (`0x400ac7xx`) tests, per slot: tags `(tags & mask) == mask`,
  NO TAG, search, show-all, bank, then MIDI (`0x400ac9a8`: `tst.b 1413(%a4)`). `eng_test_hook` replaces
  that MIDI test. With no engine ticked it is stock's test. With engines ticked it is
  `eng_match(lib, slot, view)`.
- **The rows.** The FILTER list's builder makes each tag row from three `std::function`s. Each holds an
  8-byte closure `{view, row}` on the heap, manager `0x400a9950`, and its invoker: label, toggle, tick.
  It then calls the item ctor `0x401173b8(item, f1, f2, f3, f4, -1, 8)` and appends with
  `0x40116bee(view+448, item)`. `eng_rows_hook` (at `0x400abad8`, after the 32 tags) makes ours the same
  way, with stock's manager and our invokers.
- **Other sites:** `<CLEAR>` `0x400a900e`, FILTER's label `0x400a90de`, and the view's constructor
  `0x400ac62c`.

## Measured in the 1.12 emulator (this build's own snapshot, `scratch/be/emu.sh`)

| step | result |
|---|---|
| FILTER list | engine rows after FAV, before MIDI; ticks drawn as stock's |
| FM DRUM ticked | PUNCHBASS, THE GRAND PIANO, THE CELLO, PIXELATED… (index type 2). PUNCHBASS loaded onto track 1: `sound+0xDE` = 2, MACHINE SEL on FM DRUM |
| a SOPHIE track (type 20) saved to B:172 | stock's indexer stores 20; SOPHIE ticked lists FRAGILE BEINGS alone (LOAD and SAVE views) |
| SOPHIE + EVOL | FRAGILE BEINGS (it has EVOL) |
| SOPHIE + EVOL + KICK | stock's NO MATCHES |
| FM DRUM + SOPHIE | the FM DRUM presets, then B:172 FRAGILE BEINGS; B:170/171 (other machines) left out |
| `<CLEAR>` | mask 0, the full list, FILTER without `*` |
| faults | none, every run |

Not verified: on the unit; with the User's own +Drive (DN1-imported presets carry the machine their
conversion gives); the ship gate.
