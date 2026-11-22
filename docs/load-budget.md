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

**One cost a place (2026-11-21).** `load_mnm` has one cost for each place of `dnfw.mnm.machines.CF_ALL` (55 today:
the types' places, then MONOMACHINE's engines 2-5 and DRUM's types). Until then the table was last generated on
2026-11-16 with 15 places; the places were renumbered and added since, and VOICE BUDGET read `load_mnm` past its end
for JUNO, DRONE, TB303, DRUM and MONOMACHINE's engines 2-5 (JUNO read MACHINEDRUM's machine 22: 4,531 for a voice
the table now prices at 8,623). Now `c_header()` refuses a table whose places are not the firmware's, `wr_gen.h`
refuses to compile when `LOAD_MNM_N` is not `MNM_N`, `load.c mnm_cost()` gives a place outside the table the dearest
place's cost, and `test_load_budget.py` checks every place has its cost. A DRUM type costs the dearer of its start
and its dearest setting. PARA's rows: below (2026-11-21).

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

## 2026-11-13: release tails and the DSP's room (the unit, r14b)

The unit (T12 JUNO, AMP REL 90, the A2 Diode filter at RES 95; 16 short notes, each released before the next): 12 voices
sounding at ~10,700 cycles each (~15,000 in a note's block), our frame 32k -> 138k, D 71 -> 87 %, the guard skipping
voices and inserts from the 11th note; the budget never stole. Measured from the telemetry, D rises about 1 % per
6,700 cycles of ours, so 100 % is the whole 667k frame: this kit's stock alone took ~66 % of it. Three faults:

- **Only held voices were stolen.** Every note had been released, so "nothing held to steal" let each note take a free
  slot. Now the candidates are the voices still sounding: released ones the DSP still reports busy (per-slot cost over
  `LOAD_TAIL`) first, else held ones. Stock's allocator picks among them by its own STEAL mode.
- **A fixed room.** `LOAD_AVAIL` (310,000 less our fixed work) assumed stock leaves ~310k; this kit left far less. Now,
  while the DSP reports it (idle packet unit 61: the bus insert pass's room before its deadline, every block; link.c
  `smp_room_now`, fresh within 150 periods), a note fits when 1.5 x its cost + 6,000 fits in that room, less the bus
  inserts still to run and what notes took since that packet (`load_pend`). `LOAD_AVAIL` remains the fallback.
- **Table costs.** JUNO's table cost (8,815 at the default knobs, + its filter) against ~10,700 measured. A voice now
  costs the larger of its table cost and its track's voices as the DSP measured them (`load_meas`, eased 1/64 a UI loop,
  reset when the track's machine or variant changes), and a sounding slot the larger of that and its own last cost.

Checked: `scripts/emu_load_budget.py` 13 of 13 (9: released tails and little room: the note steals a tail where stock
alone takes a free slot; 10: plenty of room: stock's result; 11: no room reported: as before; 12: a measured cost over
the table decides). Not checked: the coupled emulator run of the unit's 16 notes (it needs a time model: the coupled
harness has no DSP clock, so no deadline and no room), and the unit.

**2026-11-15, ANALOG 2's PARA** (docs/paraphonic.md, main for the User). A chord plays on its leader; each member
renders its oscillators, noise and drive. The track's measured voices (`load_meas`) are its leader's, so before this
every note of a PARA track and every slot of its chord was priced at a leader's cost. Now `para_join_cost`: a note
joining a held chord (hold.c `para_live`) costs `LOAD_PARA_MEMBER + LOAD_PARA_ADD` (6,095 + 1,087,
`scripts/para_cost.py`), one past the chord's N `LOAD_PARA_DROPPED` (610), one with none held the track's voice; a
PARA track's sounding slot is priced at its own DSP measure (at least a member's); the release loop skips a PARA
chord's voices (HOLD keeps their note-off back while the chord is held). Checked: `scripts/emu_load_budget.py` 18 of
18 (13: a joining note fits as a member where PARA OFF steals; 14: dropped; 15: a new chord; 16: the releases skip
the chord's voices, PARA OFF takes them).


**2026-11-13, the coupled proof** (`scripts/emu_coupled_budget.py`: both processors, the DSP given a clock by
`emu_coupled.dsp_clock`, idle D calibrated to the unit's 0.69; T12's sound, 16 short notes): guard voice skips and
insert-block skips, r3 (no fix) 14 / 368 with no steal; budgetfix 7 / 39 with 11 tails stolen; with the guard's FLOOR
kept free (`room_asked`) 1 / 1 with 14 stolen. Stock-only notes: no check, the same slots and load as without the fix.
The last skip came from a JUNO tail (~8,500) dipping under `LOAD_TAIL` (8,000): now 2,000 (idle slots 1,100..1,500,
releases 2,300 and up).

**2026-11-16, PARA as one voice** (`docs/paraphonic-onevoice.md`): a note joining a held PARA chord takes no slot and
never reaches `load_pre` (`csrc/para/one.c` pv_pre returns first); the chord's slot costs what the DSP measures of it
(its shadows render inside its voice), so the budget sees a chord's notes through the leader's measured cost, a few
blocks late. The join pricing above (`para_join_cost`) is left for the corner where a PARA note reaches the allocator
while an older chord of its track still holds notes.

**2026-11-19, DRONE HOLD's latches** (the User, v0.62.4: "one kick kills the drone held voice", a sparse project).
HOLD (csrc/hold/hold.c) keeps a DRONE voice gated by taking its bit out of the frame's note-off words, but stock's
own voice state is released at the key-up: to stock's allocator the latched slot was a free slot, and it gives a note
the free candidate released longest ago (0x4002aa6e), so once the other slots had been used, the next note on any
track took the drone's slot. Now, for each note-on, `pv_pre` hides the slots latched by other tracks from the live
masks for that call (hold.c `hold_locked`, as a held PARA chord's slot); a note whose candidates are all latched gets
no slot (the ISR's no-slot path, as a muted track's note: `hold_nosl` counts them); the budget's steal (`load_pre`:
held and tails) and its further releases (`load_post`) never pick a latch. The drone's own track still sees its own
latch (DRONE's rules: another key plays and lets the others go). With no latch every path is the one before.
Checked: `scripts/emu_drone_hold.py` (gate step `dronehold`), 13 of 13 on the fix, 6 of 13 on 398e0d04 (the kick,
sixteen kicks, a full pool, all candidates latched, both budget paths fail there). The DSP's frame guard is unchanged:
it refuses a voice only when the frame has no room left, whatever its machine.

**2026-11-21, PARA's costs as one voice.** `scripts/para_cost.py` still measured the two-voice design (N slots,
members and a leader): with one-voice PARA its ON runs had no roles and matched PARA OFF block for block, so the table
kept the 2026-11-16 member rows (ANALOG 2 member 4,817 / add 1,086, JUNO 3,581 / 720), and `slot_cost` priced a whole
chord's slot as one member. Now `para_cost.py` measures the chord's one slot (`test/test_a2_para.py`'s harness: the
row in the voice's frame words, the shadows in the L2 pool) with 1..8 notes against PARA OFF, the voice and the PARA
pass together, the dearer of the note blocks (every note joining at once: the pass zeroes their pool blocks) and the
steady mean; ANALOG 2 at its defaults and at its dearest FLT2 (OL12), JUNO at its defaults (dsp_cost's method,
without the 530 a slot):

| notes on the slot | 0 (OFF) | 1 | 2 | 4 | 8 |
|---|---|---|---|---|---|
| ANALOG 2 (defaults) | 6,483 | 8,047 | 15,089 | 26,545 | 50,056 |
| ANALOG 2 (OL12) | 8,155 | 9,719 | 16,761 | 28,217 | 51,113 |
| JUNO | 7,203 | 8,767 | 14,212 | 22,478 | 39,028 |

A joined note costs ~5,700..7,000 (ANALOG 2) and ~4,100..5,400 (JUNO) in its join block, the first the dearest (the
shadow loop's start). The table (x 1.15): `para` / `para_juno` = `base` (PARA ON's one note less OFF: the pass watching
the slot, 1,799 both) and `add[N]` (a chord of N less a chord of one, the dearest setting's: ANALOG 2 8,098 / 21,273 /
48,310 for 2 / 4 / 8, JUNO 6,262 / 15,768 / 34,800); a chord's slot is priced `load_voice + LOAD_PARA_BASE +
load_para_add[N]`. The generator stops if a chord of 2 or more does not lead its shadows (`ParaNotEngaged`).

`load.c`: `slot_cost` prices a PARA track's slot by its chord's sounding notes (`para_notes`: `pv_ch[v]`'s PV_SOUND
places, one at least), so the joined notes, which never pass `load_pre`, count at the next note-on on any track,
not only through the DSP's measure a few blocks later; a PARA note that reaches `load_pre` starts a chord and costs
one note (`para_chord(t, 1)`; `para_join_cost` and the member costs are gone). The track's table voice is used, not
`load_meas` (for a PARA track that is its chords' measure); the slot's own DSP measure still wins when dearer.
`emu_load_budget.py` 18 of 18 (13: 1 / 4 / 8 notes priced voice + BASE + ADD[N]; 14: a note that fits beside a
chord of 1 steals beside a chord of 4; 15: a PARA note reaching the budget costs one note; 16: releases skip PARA's
voices; 17: JUNO's own costs). Not covered: a joined note itself is never refused or made room for by the budget (it
takes no slot); the frame guard remains the net for it.
