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
