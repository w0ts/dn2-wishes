# VOICE BUDGET: the DSP load budget at note-on

2026-11-12, session opt-host. `csrc/load/load.c` + `hooks.S`, `src/dnfw/load/` (the cost table), checks
`scripts/emu_load_budget.py` (emulator) and `test/test_load_budget.py`.

The User: *"voices are not equal in cost... a big voice uses one voice but blocks the budget of another, and we
keep 16 voices"*. Stock allocates any of its 16 voice slots to any note; our engines cost from ~2k to ~30k cycles a
voice-block, so a kit of heavy engines can ask more of the DSP than a frame holds, and the frame guard then drops
voices late, per frame. This decides at the note instead.

## What it does

All 16 voice slots and every track's stock VOICES setting stay as they are.

- **One budget** (`LOAD_AVAIL`, 298,615 cycles a block: what our voices, inserts and FX get, less our fixed work).
- **What each slot spends now**, added up in the audio interrupt just before stock's allocator picks the note's
  slots (stock's note-on call of `0x4002a6a2`, at `0x400269e6`):
  - a slot last used by a **stock machine**'s track (FM TONE, WAVETONE, FM DRUM, SWARMER): that machine's cost,
    **always**. Measured in the SHARC runner: stock renders such a slot every block, note or not (FM TONE ~15,000 a
    slot, WAVETONE ~9,300, linear over 1..16 slots; a note adds ~6,000 only in its own block);
  - a slot of **one of our machines**: its track's cost while its key is held, or while the DSP still reports it busy
    (its release: the per-slot cost the DSP sends in the idle packet, `smp_tlm_cost`, over 8,000 cycles); else 0;
  - the send FX (FDN8, XDLY, the JUNO chorus) and the bus inserts.
- **If the new note's voices do not fit**, the allocator is made to steal: for that one call its live masks (the shared
  pool, and the track's own slots if it has reserved voices) keep only the held slots, so stock steals by its own
  STEAL mode (CYCLE: the oldest) and the new note retriggers that slot: its cost is freed at once. The hidden free slots
  are put back right after. If one steal is not enough (a heavy voice replacing a light one), the next oldest held
  voices are released with stock's own one-slot note-off (their release tails fade; their cost drops when the DSP rests
  them).
- **Untouched**: a note on a stock machine's track (no check at all), a kit that fits, notes in the same tick (stock
  never steals a slot started in the tick), and the whole thing when the setting is off.
- **The lists** (MACHINEDRUM's TYPE, PLAITS' and SOPHIE's MODL, MONOMACHINE's ENGN, ANALOG 2's FLT2): a choice
  of which fewer than 16 voices fit shows "N VOICES" (or "DSP FULL") in the tag column instead of its description.
  Informational: nothing is capped.
- **The setting**: SETTINGS > PERSONALIZE > VOICE BUDGET, after LIVE SELECT, default ON; the mod's settings
  sector's flag bit 3 turns it off (bit 2 LIVE SELECT, bit 1 REMOTE CONTROL).
- **The frame guard** stays as it is: the run-time safety net (bursts, knob settings the table does not cover).

## The cost table

`scripts/gen_load_table.py` writes `src/dnfw/load/table.json` (generated, committed; `--check` re-measures and
compares), and `dnfw.load.c_header()` turns it into the ColdFire's arrays in `wr_gen.h`. A voice's cost is the dearer
of its steady and its note block from `scripts/dsp_cost.py` (docs/dsp-cost.md), + 530 (its guard and quiet test
outside the voice), x 1.15. Every cost-changing choice is measured on its own: each MACHINEDRUM machine, each PLAITS
and SOPHIE model, each MONOMACHINE engine, each of ANALOG 2's 25 FLT2 filters; the sample machines; the stock machines
(runner). `scripts/dsp_cost_fx.py` adds the A2 filter types and the inserts a voice, the bus inserts and the send FX an
instance. The ColdFire reads each track's machine, choice, filter and inserts from the kit (`load_poll`, once a UI
loop) with the DSP's own formulas for the choices.

## Checked

`scripts/emu_load_budget.py` (inside the bench), the build's ColdFire over a stock 1.12 UI snapshot, stock's own
allocator building every state (reset, notes played tick by tick); digikit does not emulate BITREV, which the
allocator uses, so the check does it at the allocator's twelve BITREV sites. 9 of 9:

| | result |
|---|---|
| the budget fits | the same slots and memory as stock's |
| a stock-only kit (heavy) | stock's result exactly, no check made |
| the setting off, over budget | stock's result exactly |
| full (8 x 35,000 held, a ninth) | the hook steals a held voice (0x0001); stock alone takes a free slot (0x0100); the free slots back in the pool |
| a 50,000 note over 14 x 20,000 | one stolen, the next oldest released (held 14 -> 13) |
| a track with reserved voices | the steal stays in its own slots |
| a chord in one tick | the second note takes another slot |
| the interrupt's stack | the deepest the hook path goes: 116 bytes below the call (stock's allocator alone: 164) |

## Not verified

- On the unit (TODO, unit checks): the sound of a steal, the DSP load with a full kit, a stock-only kit unchanged.
- The tail estimate: the DSP's per-slot cost reaches the ColdFire with the idle packet (some blocks late).
- TRACK steal mode (STEAL = TRACK) ignores the candidate mask (stock's own code): with it, a steal may take a free
  slot, and the guard decides as before.
- REUSE / mono / retrigger reuse the track's own slots: the need is then over-counted (a voice may be stolen early).
- A free slot last used by a stock machine still counts that machine's cost when our note takes it (conservative).
