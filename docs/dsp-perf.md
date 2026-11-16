# DSP speed: the 2026-11-10 hot-spot pass (branch sophie-v047-os112-perf)

Base: `sophie-v047-os112-poly16` 6e726aac (v0.47 + two inserts + DT2 recorder + PLAITS poly16).
Every change is bit-exact: each PERC machine's output over a script of trigs, notes and two knob sets
is the same, word for word, as the base's (49 of 49 machines: MD, SOPHIE, TB303, the 13 PLAITS
engines), also with the shared L1 scratch below filled with garbage before every block.

## How it was measured

The DSL's run mode, as poly16's prof2.py: instructions (jumps and calls counted, folded memory moves
not), plus 0.9 x (4 x L2 + 10 x DDR accesses): the SHARC runner's memory clock. One voice, steady
blocks; the frame is 666,667 cycles, the guard's limit about 355,000, the stock ~43,000. It is an
estimate: the unit's meter is the measure (b6 WS: est 16,951, unit ~20,000).
Scripts (perf session scratch, `~/GitHub/dn2mk2-scratch/perf/`): profvoice.py (per machine, per
call site), proffx.py (FDN8, XDLY, inserts), golden_all.py / poison.py (the bit-exact check),
eqtest.py (old and new helpers, register for register, 20,000 random, edge and tie cases each).

## What changed

1. **The 56300's products on the SHARC's fixed-point multiplier** (md/efm.py, md/trx2.py, md/core.py).
   The Machinedrum machines did every 24 x 24-bit product as four float products of 12-bit halves,
   22-36 instructions each. One `SSF` (floor(x y / 2^31) of the exact 64-bit product) on operands
   shifted up as far as they stay 32-bit words gives floor(A B / 2^k) directly; `SSI` gives the low
   word (round-half-even, the flags, the filters' carry). Both forms run on the unit since v0.42
   (PLAITS). xfloor 22 -> 6-7, xprod 27-34 -> 8-9, xround 35 -> 16 (12 from an integer), mpy_floor
   36 -> 10, wmul 26-33 -> 3-8 (now inline: shorter than the call), the TRX filters' terms: the
   coefficients kept as integers (c 2, c) instead of float halves, each term SSF + SSI, the sum's
   floor from the floors' sum and the low words' carry.
2. **The P-I block scratch in L1** (md/pi_sd.py, md/pi_bd.py, perc/machines.py, md/core.py
   `pi_scr`). PI-SD / PI-RS / PI-BD / PI-MT kept their per-block arrays (strike, noise, the modes'
   sums and coefficients) in the slot's DDR delay area: 2,112 of PI-SD's 2,410 DDR accesses a block.
   They now use the Monomachine render scratch's XB, YB rows (L1, 384 words): every voice renders
   alone, and no machine reads those rows before writing them in its block (rowfirst.py, every
   MnM machine and PLAITS engine; pifirst.py, the P-I machines; poison.py holds it).
3. **PI-SD / PI-RS: the limiter's bounds in F13, F14** through the eight modes (no constant loads).
4. **The insert passes skip their 32-record walk when no record is theirs** (inserts/program.py,
   post.py, bus.py, design.FLAGS). The pre pass's unpack (only when the records change) sets three
   flags after the table: any FUZZ/TAPE/FOLD/HARM, any CHOR/WIDE, any FDN8/XDLY. With every insert
   OFF the three passes cost ~9,900 a block; now ~350. A harness that writes TABLE directly writes
   design.flags(...) at FLAGS too (the tests and the runner's inserts / inspost / insbus steps do).

## Hot spots, before -> after (est per block, one voice; bytes of the DSP upload)

| component | before | after | change |
|---|---|---|---|
| PI-SD, PI-RS | 41,616 / 40,996 | 22,618 / 22,268 | -46 % |
| TRX-S2 | 23,972 | 13,357 | -44 % |
| TRX-CP | 19,488 | 11,180 | -43 % |
| EFM-BD | 13,823 | 8,733 | -37 % |
| TRX-CY, TRX-MA | 27,159 / 19,344 | 17,320 / 12,343 | -36 % |
| EFM-CP, EFM-CY, EFM-XT, EFM-CB | 15,871 / 29,717 / 15,312 / 19,651 | 10,299 / 19,373 / 10,222 / 13,279 | -32..-35 % |
| TRX-CB, TRX-CH, TRX-OH | 12,438 / 17,569 / 17,353 | 8,439 / 12,904 / 12,865 | -26..-32 % |
| EFM-SD, EFM-RS, EFM-HH | 14,726 / 17,666 / 13,901 | 11,300 / 13,462 / 10,474 | -23..-25 % |
| PI-BD, PI-MT | 24,633 / 27,961 | 18,764 / 21,684 | -22..-24 % |
| PI-RC, PI-CC, PI-HH | ~21,000 | ~20,500 | -3 % |
| TRX-BD/B2/SD/XT/RS/CL/XC, GND, PI-ML, PI-MA | 2,800-20,400 | same | 0..-2 % |
| SOPHIE, TB303, the 13 PLAITS engines | 8,557-44,597 | same | 0 % (not touched: poly16's) |
| insert passes, every record OFF | ~9,900 a frame | ~350 a frame | -96 % |
| FUZZ / TAPE / FOLD / HARM (one on, the pre pass) | 9,943 / 11,788 / 9,801 / 8,812 | about the same | the walk still runs |
| FDN8 / XDLY (one instance) | 24,715 / 9,149 | same | not touched |
| the voice's own work (frame, resampler, guard, out) | ~2,600 a voice | same | resampler 1,120 of it |
| DSP upload (unpacked) | 1,039,872 (8,703 free) | 1,034,940 (13,635 free) | -4,932 B |
| perc / inserts / inspost / insbus objects | 145,592 / 4,124 / 3,098 / 2,690 B | 140,446 / 4,348 / 3,112 / 2,704 B | -5,146 / +224 / +14 / +14 |

## Left (measured, not done)

- **TB303** (35-45k, the dearest voice): half its multiplies load an immediate constant first
  (31 in the elliptic decimator, 4x oversampled); its state loads (I3 + 64..) cannot fold into a
  compute (offsets past +-32): the shrink branch's I3 bias fixes that part for every machine.
- **FDN8** (24.7k an instance): 34 ring taps a sample, each add / AND / OR / I4 = (136 of ~430
  instructions a sample) and 1,220 DDR accesses (its rings: 512 KB, DDR by need). The DAG's
  circular buffers would remove the address arithmetic; this code has never set B/L registers on
  the unit (MODE1 / CBUFEN risk), so not without a unit test.
- **The resampler** (1,120 a voice): scalar, near its floor; multifunction (multiply || add) is
  refused while selmap and digikit decode it differently.
- **EFM**: the remaining halves in state (mfb, mod, mdec, rdec, Ph, mfrq, f2) could be integers too
  (~5 instructions a product); TRX `_clamp` and the P-I `sat` elsewhere could hold their bounds in
  registers.
- **PLAITS / SOPHIE**: per-sample reciprocals (soft clip, WS) and table interpolation; poly16's.

## Verified (take-over session, 2026-11-10; tree = commits f7b045b2..5f4cb9ef on 6e726aac)

What "memory words differ" in the perf scratch's `g_final_cmp.txt` means: golden_all.py hashes two
things, `ho` (the 32 output floats of every block, 56 blocks) and `h` (`ho` plus every memory word the
voice left behind). Only `h` differs, because the scratch moved (P-I block scratch to L1) and the
internals changed (integer coefficients); `ho` is identical for 49 of 49. Re-run by the take-over
session against a clean `git archive` of the base (6e726aac), not the old session's files.

| check | result |
|---|---|
| golden_all.py, base vs this tree, output hash per machine (trigs, 6 notes, 2 knob sets, 56 blocks) | 49/49 identical |
| poison.py (L1 scratch filled with NaN patterns and random words before every block) | 49/49 identical to the base |
| SHARC runner, PERC (step 3, 3g garbage, 3w wipe, 3k chords, 3s stress): DSP bit-exact to the Python model, 34 MD machines sound, guard | PASS |
| SHARC runner, inserts (3i), inspost (3j), insbus (3k): bit-exact to ref/postref/busref, OFF = pass-through with the engine's registers back | PASS |
| gate preflight, code-fresh, rebuild (byte for byte), dsp-identity, hwrules, symbols, coldfire, overbridge on a build of this tree | PASS |
| pytest test_inserts*.py, test_md.py, test_perc_live.py (base and tree) | same result: see the note |
| SHARC runner step 3b: `v0.18: ONESHOT plays KICK from the pool` | FAIL, **identical on the unmodified base** (6e726aac, same step run there): not from this change; smp.asm is untouched |
| gate `boot` (boot from reset) on a build of this tree | FAIL: the intro is never reached within 700M instructions (0 stamp calls, 0 animation frames); **identical on a build of the unmodified base**. Not verified; a ColdFire-side issue the DSP change does not touch (code-fresh PASS) |

Notes: (1) running those six test files together in one pytest-xdist run gives 22 failures in
test_perc_live.py on the base **and** on this tree, the same 22 (an order dependence between test files);
test_perc_live.py alone: 51 passed, 1 skipped on both. (2) The remaining SHARC steps in the same run
(decode, map, link, rec, mainrec, recwhole, pvmix, fdn8, xdly, tdm, stock 0-4/4b, frame) passed apart from
the smp item above.

## All 49 machines, before -> after (est cycles per block, one voice, steady; peak = the worst block)

| machine | before | after | change | peak block before -> after |
|---|---|---|---|---|
| TRX-BD | 4,731 | 4,685 | -1.0 % | 25,034 -> 25,001 |
| TRX-B2 | 6,604 | 6,543 | -0.9 % | 28,791 -> 28,726 |
| TRX-SD | 7,596 | 7,471 | -1.6 % | 29,970 -> 29,844 |
| TRX-XT | 4,137 | 4,112 | -0.6 % | 24,614 -> 24,614 |
| TRX-CP | 19,488 | 11,180 | -42.6 % | 43,831 -> 34,812 |
| TRX-RS | 7,589 | 7,530 | -0.8 % | 29,677 -> 29,615 |
| TRX-CB | 12,438 | 8,439 | -32.2 % | 26,617 -> 25,657 |
| TRX-CH | 17,569 | 12,904 | -26.6 % | 41,085 -> 36,197 |
| TRX-OH | 17,353 | 12,865 | -25.9 % | 41,117 -> 36,229 |
| TRX-CY | 27,159 | 17,320 | -36.2 % | 53,119 -> 42,305 |
| TRX-MA | 19,344 | 12,343 | -36.2 % | 43,265 -> 35,729 |
| TRX-CL | 6,120 | 6,061 | -1.0 % | 28,060 -> 27,998 |
| TRX-XC | 4,082 | 4,057 | -0.6 % | 24,611 -> 24,611 |
| TRX-S2 | 23,972 | 13,357 | -44.3 % | 29,858 -> 27,178 |
| EFM-BD | 13,823 | 8,733 | -36.8 % | 36,504 -> 31,096 |
| EFM-SD | 14,726 | 11,300 | -23.3 % | 37,480 -> 33,839 |
| EFM-XT | 15,312 | 10,222 | -33.2 % | 38,081 -> 32,673 |
| EFM-CP | 15,871 | 10,299 | -35.1 % | 38,701 -> 32,781 |
| EFM-RS | 17,666 | 13,462 | -23.8 % | 40,618 -> 36,152 |
| EFM-CB | 19,651 | 13,279 | -32.4 % | 42,716 -> 35,946 |
| EFM-HH | 13,901 | 10,474 | -24.7 % | 36,600 -> 32,959 |
| EFM-CY | 29,717 | 19,373 | -34.8 % | 53,508 -> 42,518 |
| GND-SN | 3,589 | 3,559 | -0.8 % | 25,469 -> 25,437 |
| GND-NS | 3,164 | 3,164 | +0.0 % | 24,919 -> 24,919 |
| GND-IM | 2,848 | 2,848 | +0.0 % | 24,697 -> 24,697 |
| PI-BD | 24,633 | 18,764 | -23.8 % | 47,915 -> 41,679 |
| PI-SD | 41,616 | 22,618 | -45.7 % | 66,007 -> 45,819 |
| PI-MT | 27,961 | 21,684 | -22.4 % | 51,483 -> 44,813 |
| PI-ML | 20,405 | 20,405 | +0.0 % | 43,536 -> 43,536 |
| PI-MA | 11,402 | 11,402 | +0.0 % | 34,020 -> 34,020 |
| PI-RS | 40,996 | 22,268 | -45.7 % | 65,311 -> 45,411 |
| PI-RC | 21,141 | 20,480 | -3.1 % | 46,036 -> 45,739 |
| PI-CC | 21,230 | 20,570 | -3.1 % | 47,755 -> 47,053 |
| PI-HH | 19,509 | 18,846 | -3.4 % | 45,653 -> 44,949 |
| SOPHIE | 18,338 | 18,338 | +0.0 % | 39,672 -> 39,672 |
| PLT-WS | 10,146 | 10,146 | +0.0 % | 32,441 -> 32,441 |
| PLT- | 10,161 | 10,161 | +0.0 % | 32,444 -> 32,444 |
| PLT-VA | 9,454 | 9,454 | +0.0 % | 31,698 -> 31,698 |
| PLT-FM | 16,211 | 16,211 | +0.0 % | 38,942 -> 38,942 |
| PLT-ADD | 14,180 | 14,180 | +0.0 % | 37,022 -> 37,022 |
| PLT-SWRM | 11,712 | 11,712 | +0.0 % | 35,085 -> 35,085 |
| PLT-NOIS | 9,042 | 9,042 | +0.0 % | 31,090 -> 31,090 |
| PLT-PART | 21,318 | 21,318 | +0.0 % | 45,411 -> 45,411 |
| PLT-STRG | 18,946 | 18,946 | +0.0 % | 45,369 -> 45,369 |
| PLT-MDAL | 19,836 | 19,836 | +0.0 % | 42,870 -> 42,870 |
| PLT-BD | 10,683 | 10,683 | +0.0 % | 32,408 -> 32,408 |
| PLT-SD | 12,015 | 12,015 | +0.0 % | 34,810 -> 34,810 |
| PLT-HH | 8,557 | 8,557 | +0.0 % | 30,885 -> 30,885 |
| TB303 | 44,597 | 44,597 | +0.0 % | 63,129 -> 63,129 |

Insert costs re-measured (proffx.py, the pre pass alone, every record OFF): 4,119 -> 21; FUZZ 9,943 -> 9,949,
TAPE 11,788 -> 11,794, FOLD 9,801 -> 9,807, HARM 8,812 -> 8,817 (+6, the flag test); FDN8 24,715 and XDLY
9,149 unchanged.

## Next hot spots (planned, none started; ranked by the worst-case budget table)

Source: `~/GitHub/dn2mk2-scratch/combined/budget-table.md` (SHARC runner, gpufarm, combined build WITHOUT this
branch's changes, cycles on the runner clock, frame 666,667). Its worst case (16 x PI-SD + DIOD + CHOR/TAPE +
FDN8/XDLY) is 1,987k = 298 %: 16 voices 710k, A2 filter 241k, inserts 685k, idle floor 352k. This branch took
from it: PI-SD/PI-RS ~-46 % per voice (DDR 2.1k -> 0.26k a block), the idle CHOR/WIDE and bus passes (13k + 12k
idle in that table) down to ~0.4k, MD machines -23..-45 %. Left, in order of cycles to win:

| # | item | worst case now | what | est after |
|---|---|---:|---|---:|
| 1 | A2 filter pass (DIOD/OTA/LADR/MS20/SVF) | 157-242k flat | constants into registers, unroll per sample, 8 SIMD pairs, skip empty slots; bit-exact to its model | 110-210k |
| 2 | CHOR post insert, 16 voices x 2 slots | 330k (562k max knobs) | state in registers, delay lines to L1, L/R as SIMD, or one CHOR per track bus | 180-275k |
| 3 | TB303 x16 | 546k above idle (34.9k instr a voice) | SSF fixed point as for the MD, hoist the 31 immediate multiplies, two voices per SIMD op | 350-430k |
| 4 | FDN8 / XDLY idle and bus costs | FDN8 send 42k idle, bus 33k an instance (x8) | zero-input / dead-tail flag (skips the DDR ring reads at idle), circular buffers (hardware test needed first) | -40k idle, -20 % |
| 5 | pre inserts TAPE/DIST/FUZZ/FOLD, 16 voices x 2 | 222-253k | the one-record walk (~half of FUZZ's 9.9k), constants in registers | -30 % |
| 6 | PLAITS PART/STRG/MDAL (poly16's) | 350-385k above idle | PART/STRG DDR-bound (zero-fill stores, L2 rings), MDAL fp-bound (SIMD) | -20..-40 % |
| 7 | PI-SD/PI-RS/PI-MT remainder | 17.9k instr + 0.26k DDR a block | state halves to integers (efm-style), PI-RC/CC/HH still 0.9k DDR | -10..-15 % |
| 8 | per-voice overhead (resampler 1.1k x16) | 42k | multifunction blocked on selmap/digikit decode | small |

Not ours to cut: the stock tail (352k idle floor, 53 % of the frame: stock per-track chain 103k, stock sends/mixer
85k) except by patching stock code (skip empty slots), which needs a per-slot exactness proof. With that floor
no per-voice optimisation alone reaches 16 x any synth x two inserts: a stated ceiling or skip logic is needed too.

## 2026-11-11 additions (same branch; shas in order)

| commit | what | est cycles a block, before -> after | proof |
|---|---|---|---|
| `321852fa` | pre and post insert passes' state, scratch and records in L1 (0x2e3000..0x2e4044; were L2) | FUZZ 9,949 -> 5,089, TAPE 11,794 -> 6,988, FOLD 9,807 -> 5,419, HARM 8,817 -> 4,541; CHOR one voice 17,007 -> 9,303, four 59,113 -> 33,168 | bit-exact (addresses only): runner inserts/inspost/insbus PASS, tests, preflight set 13/13 |
| `ec700812` | FDN8 quiet gate (declared; `fdn8.program.QUIET_GATE`): input exactly +0.0 and wet < 2^-24 for 4,224 blocks (> the 4,096-block ring) => skip, wet zeros, only the LFO phases move | idle FDN8 13.7k instr + 1,220 DDR (est 24.7k) -> 376 instr; active blocks +375 instr | model A/B 5,600 blocks, woken reverb output identical word for word; runner fdn8 PASS with 3 checks on the assembled skip path; xdly, insbus PASS |

The first FDN8 gate (output small for 4 blocks, LFO phases frozen) was wrong twice: the ring holds a delay-line
tail the output does not show (predelay), and frozen phases made the woken reverb differ from the ungated one by
1.4x the signal. Both rules in the commit fix that. A real decayed tail below -144 dB is cut (declared).

A2 filters are on branch `sophie-v047-os112-a2fperf` (see docs/a2f-perf.md there): state in L1 (`c81690f4`), ONE_VOICE off and
silent-slot skip (`5fc821f5`).

| `7ab83407` | PI-RC / PI-CC / PI-HH: the slot's XB block (DSP2's X memory) in L1 during render, the first 64 words (8..37 are state between blocks) copied in and out | PI-RC 21,141 -> 16,176, PI-CC 21,230 -> 16,244, PI-HH 19,509 -> 14,779 (-23..-24 %) | output identical to base (golden, and under poison); runner voice/guard/garbage/wipe PASS; preflight set 13/13. A first attempt differed from block 1: `excite` had one direct address into XB; found by bisecting the render stages with the redirect on one stage at a time |
| `15f957ea` | TB303's elliptic decimator run section by section over the four oversampled samples (coefficients and states loaded once for four samples) | TB303 44,597 -> 39,176 (-12.2 %) | output identical to base (golden, poison); runner voice/garbage/wipe/chords PASS; preflight set 13/13; perc.asm +3.5 KB |

Remaining repeated DDR accesses per block after these (ddrhot.py, words touched more than once): PLT-PART 195 (~1.8k est),
SOPHIE 168 (1.5k), PI-RC/CC/HH ~100 (0.9k), PLT-STRG 94, PLT-SWRM 90, PLT-WS 61: no machine has a big repeated set left; what is
left in DDR is state and tables touched once a block.

### How the PI-RC lead was found (for the next machine)
520 of PI-RC's 1,029 DDR accesses a block were 38 words (slot XB words 0..37, each touched 14 times). ddrhot.py lists, per
machine, the words touched more than once and whether the first access in a block is a write (scratch) or a read (state);
pircfirst.py does it per word. Words read first are state between blocks (copy them in and out); words written first can
live in the shared L1 rows (poison.py proves it: the rows are filled with garbage before every block). Every address into
the block must go through the one accessor: bisecting the stages with the redirect on one stage at a time (PIRC_STAGE) found
the stray direct address. The scripts are in `~/GitHub/dn2mk2-scratch/perf/`.

## Final state of the branch (2026-11-11 morning)

Commits, in order, on `sophie-v047-os112-perf` (base 6e726aac): f7b045b2 MD fixed-point products, a0dd1d17 P-I scratch in L1,
9f692b8c insert-pass walk skip, 5f4cb9ef regenerate, 321852fa pre/post insert state in L1, ec700812 FDN8 quiet gate (declared),
7ab83407 PI-RC/CC/HH XB in L1, 15f957ea TB303 decimator section-major, 77cd8ab4 PI-ML/PI-MA xmul on SSF/SSI, 594933ca PI-SD/PI-RS
_prod on SSF/SSI, c754ebad PI-BD/PI-MT accumulators on SSF/SSI. Every one: output identical to the base for all 49 machines
(golden hash; and under poison), except the FDN8 gate (declared; identical across a wake from a never-used ring). The final
tree: 49/49 identical to the base, 49/49 under poison.

Proof pattern per commit: golden_all.py / poison.py (scratch perf/), the old and new helper compared on thousands of random and
extreme inputs, the runner's voice/guard/garbage/wipe (and chords, inserts, fdn8 steps where touched), then the preflight steps
(preflight, code-fresh, rebuild, dsp-identity, hwrules, symbols, coldfire, overbridge) on a build of the tree. A full 23-step runner
pass of the head through ec700812: 231 PASS, 1 FAIL (sharc 3b ONESHOT/KICK, also failing on the unmodified base). Not run on any:
the full ship_gate and the boot step (which fails identically on the base here). No build from this branch is cleared to flash.

All 49 machines, base -> now (est cycles a block, one voice, steady):

| machine | base | now | change |
|---|---|---|---|
| TRX-BD | 4,731 | 4,685 | -1.0 % |
| TRX-B2 | 6,604 | 6,543 | -0.9 % |
| TRX-SD | 7,596 | 7,471 | -1.6 % |
| TRX-XT | 4,137 | 4,112 | -0.6 % |
| TRX-CP | 19,488 | 11,180 | -42.6 % |
| TRX-RS | 7,589 | 7,530 | -0.8 % |
| TRX-CB | 12,438 | 8,439 | -32.2 % |
| TRX-CH | 17,569 | 12,904 | -26.6 % |
| TRX-OH | 17,353 | 12,865 | -25.9 % |
| TRX-CY | 27,159 | 17,320 | -36.2 % |
| TRX-MA | 19,344 | 12,343 | -36.2 % |
| TRX-CL | 6,120 | 6,061 | -1.0 % |
| TRX-XC | 4,082 | 4,057 | -0.6 % |
| TRX-S2 | 23,972 | 13,357 | -44.3 % |
| EFM-BD | 13,823 | 8,733 | -36.8 % |
| EFM-SD | 14,726 | 11,300 | -23.3 % |
| EFM-XT | 15,312 | 10,222 | -33.2 % |
| EFM-CP | 15,871 | 10,299 | -35.1 % |
| EFM-RS | 17,666 | 13,462 | -23.8 % |
| EFM-CB | 19,651 | 13,279 | -32.4 % |
| EFM-HH | 13,901 | 10,474 | -24.7 % |
| EFM-CY | 29,717 | 19,373 | -34.8 % |
| GND-SN | 3,589 | 3,559 | -0.8 % |
| GND-NS | 3,164 | 3,164 | +0.0 % |
| GND-IM | 2,848 | 2,848 | +0.0 % |
| PI-BD | 24,633 | 16,547 | -32.8 % |
| PI-SD | 41,616 | 20,374 | -51.0 % |
| PI-MT | 27,961 | 18,382 | -34.3 % |
| PI-ML | 20,405 | 17,213 | -15.6 % |
| PI-MA | 11,402 | 7,427 | -34.9 % |
| PI-RS | 40,996 | 20,024 | -51.2 % |
| PI-RC | 21,141 | 16,176 | -23.5 % |
| PI-CC | 21,230 | 16,244 | -23.5 % |
| PI-HH | 19,509 | 14,779 | -24.2 % |
| SOPHIE | 18,338 | 18,338 | +0.0 % |
| PLT-WS | 10,146 | 10,146 | +0.0 % |
| PLT- | 10,161 | 10,161 | +0.0 % |
| PLT-VA | 9,454 | 9,454 | +0.0 % |
| PLT-FM | 16,211 | 16,211 | +0.0 % |
| PLT-ADD | 14,180 | 14,180 | +0.0 % |
| PLT-SWRM | 11,712 | 11,712 | +0.0 % |
| PLT-NOIS | 9,042 | 9,042 | +0.0 % |
| PLT-PART | 21,318 | 21,318 | +0.0 % |
| PLT-STRG | 18,946 | 18,946 | +0.0 % |
| PLT-MDAL | 19,836 | 19,836 | +0.0 % |
| PLT-BD | 10,683 | 10,683 | +0.0 % |
| PLT-SD | 12,015 | 12,015 | +0.0 % |
| PLT-HH | 8,557 | 8,557 | +0.0 % |
| TB303 | 44,597 | 39,176 | -12.2 % |

## 2026-11-11 (session budget-table): the post inserts (CHOR, WIDE) and the bus pass

Branch `claude/speed-chor-fc81b2`, from 81113ac3. Every change here is bit-exact (output word for word as the
unmodified pass: `postref` / `busref`, the pass models' tests, and the same tests with garbage in every word the
pass must not assume zero: scratch, wet buffers, the rings, the FDN8 stores). Cost = the DSL's run-mode steps
(merged moves not counted; jumps counted) + 0.9 x (4 L2 + 10 DDR), 16 voice slots, one insert slot, steady
(scratch: `pc.py` post pass, `pb.py` bus pass; the old tree is `git archive 81113ac3`).

| change | before -> after (est cycles a block) |
|---|---|
| CHOR voice loop and mix loop in registers: the delay, step, gains, ring base, mask and position stay in R0..R15, 4 samples a pass, the wet l / r and the neighbours' moves ride on the computes, the ring written through I4 post-modified (the write place is a multiple of 32 from a fresh slot, so only the block's last word wraps, its address set apart) | 1 voice 63,509 -> 42,485, 4 voices 165,877 -> 110,005 |
| CHOR: a mirror word before each 4 KB ring (stride 4,104 B: the mirror, the ring, 4 spare), refreshed from the ring's last word at the start of each block; a read's second tap is `DM(-1, I2)`, no second address | 4 voices 110,005 -> 102,245 (17 instructions a sample-voice, was 58) |
| CHOR: the wet buffers zeroed 16 words a pass | 4 voices 102,245 -> 101,349 |
| WIDE in two passes (mid, side x WDTH x 2, the ring write; then the read and the two one-poles) | 16 slots 46,293 -> 33,237 |
| FDN8 bus instances' stores (8 x 156 words) in L1 0x2e4050..0x2e53d0 (the 5 KB free after the post pass's state), the swap copies 8 words a pass | one FDN8 bus instance 32,350 -> 30,671 (L2 stores freed: 8 KB of the bus pass's L2 state) |

CHOR with 4 voices (the dearest knob setting) and 16 slots: 165.9k -> 101.3k (-39 %), both insert slots 332k -> 203k.
What is left of it: 17 instructions a sample-voice (2,048 of them: 35k), 2 DDR reads a sample-voice (41k est, the rings
are 128 KB, no room in L1 / L2), the mix loop 7.3k, per-slot set-up (records, exp2, sines) about 12k.
Tried on paper and dropped: reading y1 from the previous sample's y0 (needs a branch, nets ~4 cycles a sample), a 40-word
window of the ring copied into L1 per voice-block (DDR 2.0 -> 1.25 a sample but the copy costs about what it saves),
caching the derived knob values per record (CHOR 1.6k, WIDE 4.8k a block).

The empty passes' idle tax (all records OFF), measured on this tree: post 48 steps, bus 164 (its L2 save area), pre 21
(flags from 9f692b8c): the ~25k of the budget table's "idle taxes" were gone before this session.
## 2026-11-11 speed-pitb session (branch claude/speed-pitb-4777c4, on 81113ac3)

Task: cut the heaviest Machinedrum and TB303 voices. Finding first: **PI-SD / PI-RS are no longer DDR-bound** (about 261 DDR
accesses a block, 15.9k instructions): the plan "shorten delay lines / burst reads" has nothing left to win. The levers that
remained are in the instruction stream, and all of them are bit-exact address-mode or loop-shape changes, no arithmetic touched.

| commit | what | est a block (golden basis), before -> after |
|---|---|---|
| `33c87b15` | TB303: while a half runs, I0 = slot state word 32, so its state words are `DM(k - 32, I0)`: offsets a compute's move can carry (-32..31); `DM(S0 + k, I3)` (k >= 64) never folded | TB303 39,176 -> 36,705 (-6.3 %) |
| `e82eeac3` | `Prog.loop0`: the loop count in R0 instead of a scratch word (leaves R0 = 0, R12 = 1 like `loop`; emit mode refuses a body, or a subroutine it calls, that mentions R0; run mode refuses a body that changes it). 25 loops converted, 12 keep `loop` | PI-SD 20,374 -> 19,303, PI-BD 16,547 -> 15,690, PI-MT 18,382 -> 17,525, PI-ML 17,213 -> 16,573, PI-RC/CC/HH -3 %, TRX/EFM -0.5..-1.4 % |
| `c5411afd` | PI-SD / PI-RS mode loop: I0 at X40[k] + 16 words (X60 at +16, X40 at -16; the step is a folded post-modify) | PI-SD 19,303 -> 18,595, PI-RS 18,953 -> 18,245 (total vs 81113ac3: -8.7 / -8.9 %) |
| `7ba0930a` | EFM operator `pair()`: I0 = the pair's state words centred (span <= 64 words), no rebase of I1 after the table read | EFM-BD 8,733 -> 8,372, SD 11,300 -> 11,089, XT 10,222 -> 9,860, CP 10,299 -> 9,937, RS 13,462 -> 13,041, CB 13,279 -> 12,737, HH 10,474 -> 10,203 |
| `39e369a7` | EFM-CY: the four operators unrolled; state via I0 (slot word S0 + 16), host words via I3 offsets; no C['b'] operator base, no loop | EFM-CY 19,373 -> 16,964 (-12.4 %) |

`e077c029`, `c5c22f8d`, `f1d05df7` regenerate perc.asm / perc.json / sharc_code.json (the DSP upload now 1,036,182+ of 1,048,575
bytes unpacked; EFM-CY's unrolling is about +0.5 KB). Regenerate rather than merge them.

Proof per change: golden_all.py output hash (56 blocks per machine) identical to a `git archive` of 81113ac3 for every machine the
change touches (all 49 after loop0), and identical again under poison.py; emit mode assembles the whole program (the loop0
R0 check); preflight family (preflight, code-fresh, rebuild, dsp-identity, hwrules, symbols, coldfire, overbridge) PASS on a
`mods apply --mod waverider` build of head `f1d05df7`. Runner voice / guard / stress / chords / garbage / wipe: see the result line at
the end of this section. Not run: the full ship_gate, boot step. No build here is cleared to flash.

### What is left, and why it stops here
- Multifunction (multiply || add) and hardware loops would be the big instruction savers (PI res body: 3 products + 3 adds + 2
  saturations a sample, 32 x 8 samples); both stay refused while selmap / digikit decode them differently (docs/SAFETY.md, hwrules).
- I0 is the only free PAR_I index register (I1 table reads, I2 voice state / ring, I3 slot). Loops that touch three or more
  32-word scratch arrays (PI-SD mix, junction, hp: X40..XC0) cannot fold their offsets: the window is -32..31 words.
  Re-laying the scratch (arrays interleaved by 4) would, with a stride-4 modify register; not done.
- TB303: `_ellip4` is 25 % of it and near its floor (30 constant loads per sample could ride on memory-folded loads, ~2 %); the
  oversampled osc / ladder are serial recurrences, so SIMD over voices is not available (one voice per call).
- PI-SD ring `put` / `_at` (3k est): byte offsets instead of word indices (-1 instruction per access), `+2048 j` as the store's own
  offset (-2 per put): about 1-2 % together; not done.
- `K.sat` is 4 instructions (two constant loads) wherever bounds cannot sit in registers (PI junction: no free register).
- TRX-CY / PI-MT: loop0 only; their bodies are already post-modify / SSF tight.

### Note: what blocks multifunction instructions and hardware loops (2026-11-11, read from the repo; nothing built or run for this)

**Multifunction (`Fm = Fx * Fy, Fa = Fx + Fy`, Type 1a, 48-bit).** `dsl.Prog.par` can already model and emit it (multiplier operands
F0-F3 x F4-F7, ALU F8-F15, one DM move); it is switched off by an assert (`multifunction computes are refused`). Why, per the
comments and docs/plaits.md: (a) **selas** (the assembler/encoder) "does NOT check these: it encodes garbage" for illegal
register groups, and its encoding of the legal form is read two ways: (b) the gate's decode step **selmap** reads selas's
`Fm = Fx * Fy, Fa = ...` as `Fm = MRF + Fx * Fy, ...` (a fixed-point multiply-accumulate), **digikit** (which the SHARC runner's
emulator uses, and which matched the firmware in every disagreement so far, docs/for-digikit-sharc-runner-dn2.md section 4) reads a
float multiply. The gate requires every executed pc to decode alike in both, so one disagreement stops the instruction. Nothing
shows that the silicon, the runner's emulator or the byte-guard refuses it: the refusal is the verification decode.
The compute-plus-move forms (type 3a / 4a) are in use already, limited to I0..I3 for the same reason (selmap reads
`compute, R = DM(I4, M6)` as 4 bytes).

**Hardware loops.** The firmware itself uses `LCNTR = ureg, DO ... UNTIL LCE` (type 12a_ureg); digikit's emulator runs it. It does
**not** execute the standalone `DO ... UNTIL LCE` with the count already in LCNTR (type 13a: "unsupported form 13a"). The rest is
policy, not a missing opcode: `scripts/gate_hwrules.py` (complex-ping's hwrules.py) fails any loop violating the PRM's rules (last
11 instructions of a loop must be 48-bit legacy encodings, no `IF NOT LCE` in them, no CALL in the last 5, nested loops must not
share an end address) because "each silenced or crashed someone's unit once". Our loops are software (`loop`, `loop0`, `loop_r`) to
stay out of that.

**Smallest change that would allow them** (not started; waiting for a go):
1. Multifunction: emit Type 1a as raw opcode words from our own encoder (not selas), restricted to the legal operand groups; make
   selmap's reading agree (fix or special-case its Type 1a decode to the PRM's: the multiply is float unless the MRF/SSF bits say
   otherwise), or accept digikit alone for this form with a recorded reason. Verify each distinct encoding by (i) round-trip decode in
   digikit and selmap, (ii) executing it in the runner's emulator against the reference interpretation (`Prog.par` run mode) on random
   and edge inputs (NaN, denormals, +-0, all register groups), (iii) one check on the unit if the User agrees (the silicon is not
   known to differ, but no unit has run one of ours). PRM p.4-53 gives the flag semantics.
2. Hardware loops: emit only `LCNTR = ureg, DO` (12a_ureg, the firmware's form), pad so the last 11 instructions are 48-bit forms
   (our compute-plus-move forms are 48-bit already; a loop shorter than 11 must be all 48-bit), keep CALLs and `IF NOT LCE` out of
   the tail; hwrules stays the gate. Emulator: nothing new for 12a_ureg.

**Effort and gain (estimates, not measured).** Encoder + tests + gate agreement: about 2 days for multifunction (the risky part is
selmap/digikit agreement and the unit check), 1 day for hardware loops on top of the existing loop0 shape. Gain from the instruction
mix: PI-SD's `res` body (3 products + 3 adds + 2 saturations a sample, 256 samples a block) 14 -> about 9 instructions, plus 3
loop instructions an iteration gone (505 iterations a block, about 1.5k): PI-SD / PI-RS -20..-25 %; TB303: the decimator and ladder
are chains of multiply-add pairs, -20..-25 % of 28k; CHOR / PLAITS MDAL (55 % fp compute): -10..-20 %; EFM / TRX (SSF products
beside adds): -10 %. Registers are the limit (multiplier inputs F0-F7, ALU F8-F15 in a pair), so rescheduling by hand is needed, not
a rewrite of the DSL's one-op emitters; the DSL would need a pairing pass for adjacent independent mul / add.
## PLAITS PART / STRG (2026-11-11, branch claude/speed-plaits-00ec7a, on sophie-v047-os112-perf 81113ac3)

Task: 16 voices of PART / STRG on one DSP (the poly16 step: `DNFW_POLY16_ONLY=PART,STRG`, runner
clock). Commits, in order (each `rr:` line regenerates perc.asm/json and sharc_code.json for the one
before):

| commit | what | est a block (golden basis) | proof |
|---|---|---|---|
| `a4ce77ea` | PART: the particle loop x4 with the rng's multiplier and scale held in R12/R14 (reloaded after a fire), the loop's `one` in R9; the five fixed all-pass stages two samples a pass with x0/x1 swapping registers (no copy); AP4 / DEL walked by pointers (I0 read, I1 head; I0 moved by the integer part's change when the LFO moves) when the half's read window (guard: integer part 396..446 / 3040..3440, measured 399.98..443.02 / 3069.9..3410.1 over 10^6 LFO updates) and head do not wrap, else the old masked loop | PART 21,318 -> 19,254 (-9.7 %) | golden 13/13 (output and every memory word), poison 13/13, PART 900 blocks x morph 0/40/100 per-block output and DDR hash identical to the base |
| `03f4f886` | STRG: the stretch line's base worked out once a string (U_SB) | STRG 18,946 -> 18,774 (-0.9 %) | output identical (golden, poison, 700 blocks); only the new word U_SB differs in memory |
| `5f584784` | PART: a half whose diffuser windows wrap round the 8192-word ring runs stage by stage masked (`_fixed_masked`, masked mix, `_moving_masked`) instead of the whole chain a sample at a time (old wrap half +5 k, now +3.3 k; the old chain and `_stage_sub` are gone) | PART 19,221 (steady unchanged) | as above, plus `_fast_ok` forced to 0 for 300 blocks (all masked): output and DDR hash identical |
| `9eae60d1` | PART: the diffuser's write pointer starts at 32 x 17 x slot (a multiple of 32, so the LFO's every-32nd update falls where it did; the ring is cleared), so the voices' ring wraps come at different blocks | same | slots 5 and 13 x morph 0/40, 900 blocks: output word for word identical to the base (the ring's memory words are rotated); golden/poison slot 0 identical |

What the golden hashes do and do not see: at the default MORP the diffuser's amount is 0, so the
output hash `ho` does not depend on the diffuser at all; the memory-word hash `h` does (and caught a
clobbered register in the first AP4 version). Always run `h`, and morph 0/40/100 for 900+ blocks (the
ring wraps once in 256 blocks; the DEL line's 3,410-sample delay is 106 blocks).

### Where it stands (poly16 step, 16 voices, notes C2 .. D#3, all triggered in block 1)

| | base (81113ac3) | now (`9eae60d1`) | + CLR_CHUNK 512 (`CLEAR_SPREAD`, default ON, declared) |
|---|---|---|---|
| PART voices sounding at the end | 13 (skips 28 by block 19) | 14 (skips 11, all in the clear blocks 1-5, none after block 6) | 15, 16 in one block (skips 4) |
| PART per-voice steady max / mean (cycles) | 23.2k / 19.9k | 21.0k / 17.6k | 21.0k / 16.6k |
| STRG voices sounding at the end | 14 (skips 25) | 14 (skips 25) | 14 (skips 6) |
| STRG per-voice steady max / mean | 22.97k / 20.35k | 22.67k / 20.08k | 22.67k / 18.9k |

So: **16 voices are not reached on either engine, and no run of the poly16 step passes** (the step also
needs every voice sounding from block 4, which the deferred clear makes impossible for PART: it is silent
until block 6; STRG until block 4).

* **PART** is within reach. What is left is the note's start: the deferred clear (`plk.defer_clear`,
  8,192 DDR stores, CLR_CHUNK 1,024 a half) makes blocks 1-5 cost 24.9k a voice (silent, only the clear:
  ~9.2k a half), 16 voices at once exceed the guard's limit and two or three are refused for good.
  Measured (farm): CLR_CHUNK 512 gives 14.3k blocks over 8 blocks, 15 voices (16 in one block). **Declared
  change, `plk.CLEAR_SPREAD` (default True; False = 1,024): a PART note starts 4 blocks later (2.9 ms), a
  STRG note 2 blocks later (1.5 ms); a block is 32 samples = 0.73 ms.** Output is not identical to the base in
  time (PART/STRG golden `ho` differs; the other 11 engines identical); after the start the engine renders
  the same, and the stale data is never audible: a voice area pre-filled with random floats gives the same
  output as a clean one over 200 blocks with retriggers (PART/STRG x morph 0/40, `dirty.py`). Committed on
  Wed 11 Nov at the Main session's request. The exact alternative (not done) is a just-in-time clear:
  every line is read at its tail first (offset l - 1 below the write pointer, the moving taps at 400..443 /
  3070..3410), so only ~7 x 17 words a half need zeros ahead of the read sweep (DEL's band 341 words wide),
  instead of all 8,192 up front; it would also remove the silent start.
* **STRG** is not: 22.67k a voice vs the ~20.7k the step needs (-9 %); this pass found -1.7 %. Its cost
  is a per-string-sample ~190 instructions (stretched path: four masked line addresses of 6 instructions
  each, a 17-instruction SVF, the DC blocker, three-way phase bookkeeping) and 5 DDR accesses (2.5k of the
  est). Ideas measured or reasoned, not done: (1) the slot's union words sit at I3 offsets 111..135, past
  the +-32 a compute can fold, so every `K.ld/K.sv` of them is a lone instruction (a free I3 bias would fold
  them: measured with the folding forced in the model: STRG -250, PART -66, i.e. small); (2) a silent-string
  skip (strings 1 and 2 of a voice triggered once never sound) would cut the step's STRG cost by about
  half but must replay the RNG and phase state exactly and does nothing for a voice whose three strings ring:
  not done, it would pass the test without lowering the real worst case; (3) byte-scaled WP (-4 a sample).
* **MDAL / FM / ADD** not touched: MDAL's cost is the 12 modes x 56 sample-steps of fp (672 x 12 instr a
  block); only SIMD pairs of modes would cut it, a restructure.

Code size: perc.asm 31,691 -> 32,469 instructions (+4.7 KB; the masked stages are the bulk of the last
+0.3 k): DSP upload 1,041,010 of 1,048,575 (7,565 B free; it was 13,635 at the start of the perf branch).

Traps found: `K.mulk/K.addk` clobber F12 by default (their constant register), so a loop that keeps a value
in F12 must pass `t=`; `loop()`'s `one` register is clobbered every pass (pass a register the body writes
first); the I-registers I6/I7 are not saved by PERC (`SAVE_REGS`), do not use them; only I0..I3 fold a
memory move into a compute; `L.W["tmp"]` is the half-pair loop's counter in `machines._render`, `tmp2` is
free; the python models run natively on the Mac with `MD_OS_BIN/MNM_OS/DT2_*` from `bench/run112.sh`
(perf scripts: `~/GitHub/dn2mk2-scratch/perf/`, profvoice.py per call site).
