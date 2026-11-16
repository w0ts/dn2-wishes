# More modulation: 13 controls opened, LFOs on the LFOs above them, controls that move (OS 1.12)

The owner, 2026-11-11, on the study `scratch/modulation/study.md`: *"Open 13 closed controls, Moving
controls, Feedback is okay for lfo."* Three ColdFire changes, no DSP change. Grades: **[E]** measured
in the emulator (`scripts/emu_modulation.py`, gate step `modulation`), **[S]** read in the 1.12
bytes, **[O]** not verified on the unit.

## 1. The 13 closed controls

PTIM, PORT, the amp envelope's DEL, MODE and RSET, and FM TONE's ATRG, ARST, BTRG, BRST, PHRT, KSA,
KSB1, KSB2 (records 34, 35, 61, 73, 74, 221, 222, 224, 225, 226, 235, 236, 237) carry mask 0 on stock
1.12. `wr_lfo_mask` (`csrc/waverider/page.c`) answers `0x1e00` for them, the mask of an ordinary
parameter; the record table itself is not edited.

**Why the lookup is enough [S].** Every destination list is made by the builder `0x4003951e`
(10 callers: the seven cascades and step routines at `0x4003981c`..`0x40039e36`, the MOD thunks
`0x400c2a52`, the DEST list view `0x401067e2`, MOD SETUP `0x40107d9c`), and the builder asks the mask
through the one `lea` our build points at the hook (`0x40039570`). The three other callers of
`get_param_mod_mask` (`0x40039910`, `0x40039b32`, `0x40039d54`) and the direct record reads
(`0x400397be`, `0x40039ac8`, `0x40039cea`, `0x40039ee8`, `0x400672f2`, `0x400674e6`, `0x400679da`)
read only the DEST records' bits 16..18 (which LFO is asking). The evaluator never reads a mask:
on 1.11 the same 13, opened in the table, listed and modulated on the unit (docs/modulation-mask.md,
2026-09-12). That they modulate on 1.12 is **[O]**; MODE, RSET, PORT, ATRG and the like are switches,
so modulating them toggles.

## 2. LFOs on the LFOs above them

Stock's rule is a rank: an LFO may modulate only the LFOs below it. Now **each LFO's list holds the
other two LFOs' SPD MULT FADE WAVE SPH MODE DEP** (never DEST, never the SLEW record, never its own
controls). MOD SETUP's list was already all of them. MIDI tracks keep stock's lists: their LFOs run in
evaluator B (`0x401376bc`, its own mirror), which this does not touch.

- **The list** (`csrc/modulation/hooks.S` `mod_mask_hook`, `cascade.c` `mod_lfo_mask`): the builder
  calls its lookup with the record on the stack and its own `want` at `60(%sp)` there (0x1e00 LFO1,
  0xe00 LFO2, 0x600 LFO3, 0x200 MOD SETUP), so the hook knows which LFO asks.
- **Self-modulation:** no list offers it. A sound made elsewhere that holds one plays as on stock (the
  write lands after the LFO read, and the next frame's smoother overwrites it).

### How a loop is evaluated [S, E]

Per audio frame (1,500 a second): smoother `0x400db28e` (every cell of `OUT` 0x800068e4 rewritten from
its target), six sources `0x400db390`, then the evaluator `0x40137a06`, which walks the 16 voice rows
and in each **LFO3, LFO2, LFO1** (`moveq #2` at `0x40137a64`, `subq.l #1,48(%sp)` at `0x40137dc2`).
Each LFO reads its controls from its row of `OUT` and adds into its DEST cell
(`0x40137d6a`..`0x40137db0`: read, add, clamp 0..0x7f00, store).

- Higher -> lower (stock): heard in the same frame.
- Lower -> higher: on stock **never heard** (written after the higher LFO read it; the next frame's
  smoother overwrites it). Measured [E]: LFO1 -> LFO2 SPD at full depth, LFO2 read 0x5800 in all
  600 frames.
- Ours: that write goes to a shadow cell (`mod_wb` at `0x40137d7a`, `mod_wb_cell`), started from the
  mirror's value that frame; at the next frame's start, before the evaluator, what the lower LFOs
  added is added into `OUT` (`mod_eval` at `0x400272d4`, `mod_eval_pre`), clamped like every LFO write.
  **One frame late (0.67 ms), exactly** [E]: over 600 frames LFO2's SPD as read equals
  clamp(set + what LFO1 wrote the frame before) in every frame, and ranged 0x2bc6..0x6ba2.

### Bounded [S, E]

- Every value an LFO reads is a clamped cell: 0..0x7f00 from the evaluator and our carry, 0..0x7fff
  from the six-source kernel (`0x400db340`: `satsl`).
- Nothing accumulates: the shadow restarts from the mirror every frame, and the smoother rewrites
  every cell from its target every frame. What does carry over frames is each LFO's phase and fade:
  - the phase step is `2(SPD - 0x4000) x rate >> (11 - MULT')` (`0x40137b24`..`0x40137b7c`), MULT
    clamped to 0..23 first (`0x40137b2c`..`0x40137b3a`), so |step| <= 0x8000 x 14,400 = 4.7e8 < 2^31:
    no overflow at any speed; the phase is a 32-bit word that wraps, as any oscillator's. The lowest
    speed is SPD 0x4000: step 0, the LFO stands (no division anywhere);
  - the fade level is saturated to 0..0x3fffffff (`0x40137ca0`..`0x40137cb6`).
- WAVE is clamped to 0..6 (`0x40137b56`..`0x40137b66`; wave 6's null function pointer is never
  called, `0x40137cc6`).
- The evaluator and its helpers have no division (no `divs`/`divu` in `0x40137a06`..`0x40137e06`, nor
  in the wave and fade routines). It is integer and fractional EMAC only: no float, no NaN, no denormal.
- The SHARC never sees an LFO's controls: slots 1..24 stay on the ColdFire. What it gets is the DEST
  cells, clamped to 0..0x7f00 exactly as a stock LFO's.
- Measured [E]: LFO1 <-> LFO2 SPD at full depth, 600 frames, and with both SPD and MULT at their tops
  (0x7f00, 23), at their bottoms (0, 0) and at zero speed (0x4000): no fault, every frame returned,
  every LFO cell in range.

### Cost, in the audio interrupt [E]

The work per frame is bounded and has no idle-to-busy step beyond that bound: at most 48 short
checks (one per LFO per voice row), at most 32 shadow writes (LFO1 and LFO2 of each of the 16 rows)
and at most 32 carried cells. Measured as the whole evaluator call, build minus stock, all 16 rows at
full depth (`emu_modulation.py` scenario `cost`):

| case | ours a frame | a second (1,500 frames) | against stock's evaluator (8,592 a frame) |
|---|---|---|---|
| typical: no LFO aimed at an LFO above it | 450 instructions | 675,000 | +5 % |
| worst: every row's LFO1 and LFO2 aimed at LFO3's controls, LFO3 at LFO2's | 4,002 instructions | 6.0 M | +47 % |

The worst case's 4,002 split: our write hook 1,024, the shadow writes 1,760, the carry 928, and the
evaluator's own wave and fade routines about 290 more (they follow the modulated values). An
instruction count, not a time: the ColdFire's instructions a second on the unit are not measured
here; the FUNC meter's C (docs/meter.md) on the unit is the check [O].

## 3. Controls that move (Optimist's second bar)

Every stock parameter cell is drawn as before, its number the value set. In the cell's row
`y0 + 5` (free in all 225 stock cells measured: SYN, FLTR, AMP, FX and MOD pages of the four stock
machines [E]), a 1 px line from `x0 + 1`, 21 px, shows the **heard** value: from the left, or from the
centre for a parameter whose default is mid-range. Shown while heard != set, kept 400 ms after.

- **Heard** = `OUT` and **set** = the smoother's own state `STATE` 0x8000de60 rounded (`OUT` before
  the sources are added), at the voice row the UI track last played (`sl_lastv`, csrc/slides) while
  `OWNER` (0x80005308) says it still plays that track. The rows are voices [S]: the six-source apply
  takes each row's track from `OWNER`, the evaluator walks the same 16 rows. A knob's glide and our
  parameter slides move `STATE` and `OUT` together, so they draw nothing.
- A cell is a sound slot only when stock's slot -> record map (`0x400dc18e`, with our machines' hook)
  gives the cell's record back for its slot; the global FX pages, MIDI tracks and the track level get
  no line.
- **Redraws:** `mv_poll` (from `wr_poll`) looks at the last draw's cells at most 100 times a second and
  asks stock `setDirty` (`0x4011d5de`) only when a line would be drawn elsewhere (moved a pixel,
  appeared, left), at most 25 times a second.
- **TUNE:** not skipped. With nothing modulated, after a frame of the parameter path, no line was
  drawn on WaveTone's SYN page (TUN1, TUN2 included) [E]: the mirror holds TUNE as set. Whether a
  modulated TUNE's line reads well on the unit is [O].
- **Not shown:** what the DSP modulates itself (envelopes, key tracking inside the DSP, our DSP
  machines' internal modulation), and our own pages (PERC, the Monomachine and sample pages draw
  their own controls, not stock cells).

### Cost, in the UI task [E, FLTR page]

| case | redraws | ours | the redraws we ask for |
|---|---|---|---|
| typical: nothing on the page modulated | none asked | a poll at most 100 a second, 115..167 instructions; `mv_cell` 226 a cell in stock's own draws | 0 |
| one line moving | 25 a second | `mv_cell` 348 for the moving cell | 25 x the page draw (65,800 instructions on FLTR 1) |
| worst: every cell modulated and moving | 25 a second | `mv_cell` x 9 = 3,802 a draw, 95,000 a second | 25 x 67,948 = 1.7 M instructions a second |

The redraw rate is capped at 25 a second, the rate stock itself redraws at while a knob turns (about
26, measured on the unit on 1.11, display.md); one page draw was about 1.4 ms there, so the cap is
about 3.5 % of the ColdFire while any line moves [D], and 0 when none does. The cap is the bound:
more modulated cells do not raise the redraw rate, only the 2,148 instructions our lines add to each
draw (67,948 against 65,800). The state is 1,104 + 284 B in a RAM block of its own, `MOD_RAM`
0x46af8000 (2 KB, above BSS like the meter's).

## Not verified on the unit

Everything above is from the emulator or the bytes. On the unit: that the 13 modulate on 1.12; that
LFO1 -> LFO3 SPD is heard; the ColdFire load (FUNC meter's C) with a line moving at 25 Hz; how the
line reads on the glass.
