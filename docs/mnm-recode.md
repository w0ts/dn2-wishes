# The Monomachine machines re-coded (v0.42)

Owner, 2026-11-06: re-code the Monomachine machines from the bit-exact code "for this
firmware": less of the DSP, the same sound. Two parts.

## 1. DDRW's bit reducer made exact (a sound change, toward the Monomachine)

The Monomachine's reducer (P:0x3FA..0x405 of its DSP code) takes the crossfaded sample as a
24-bit word (the accumulator's a1), multiplies it by X49 into the 48-bit product, and keeps a1:
floor(t24 x X49 / 2^23); then X48 times that. v0.26..v0.41 floored a float32 product of the
float sample: at heavy bit reduction (BR around 112) a one-LSB slip flips a whole step (0.044
of full scale at BR 112). v0.42 does it as the Monomachine does, in one fixed-point multiply:
`R = (t24 << 8) * X49 (SSF)` is floor(t24 x X49 / 2^23) (the SHARC multiplier's signed
fractional form: the 64-bit product shifted once, bits 63..32 kept, truncated; PRM p.3-9).

Against the regenerated Monomachine references (bench `GOLDENS-MNM.md`, its own DSP code in an
emulator, 366 cases): v0.41's model failed 3 (DDRW BR1=112 44.6 dB, BR2=112 44.0, mix1 43.0);
v0.42's passes all 366, those three at 115.0, 114.9 and 117.8 dB, `test_mnm.py` unchanged.
That ends the owner's exception of 2026-11-05 (the references are installed and run in the
gate's unit step).

## 2. The machines' hot loops re-coded, the same words bit for bit

The DSL (`dnfw.perc.dsl`) writes one SHARC instruction an operation and kept every loop's
words in L2 scratch: a loop's count, its pointers and constants were loaded (and stored) every
sample. v0.42 holds them in registers in the loops that run most, with the same operations in
the same order, so every output word is the same:

| where | machines | what |
|---|---|---|
| DDRW's wave loop | DDRW | i0, msk, the two wave pointers, the fade, its step, X48, X49, TOP and q23's shift in registers; the count in a register (`Prog.loop_r`) |
| DPRO's interpolator | DDRW, DENS | P, il, g, out in registers, the five taps unrolled |
| DPRO's 2:1 decimator | DDRW, DENS | TOP, -1, the stride in registers; the count in a register |
| the polyphase decimator | SID, WAVE | its inner rounds counted in a register (10 - inner of them, not ten tested ones); TOP held |
| SID's phases, TRI, SAW, PULS, RING | SID | the phases, increments, mask and constants in registers |
| VO-6's series resonator | VO-6 | on the fixed-point multiplier: each 24 x 24 product as hi = floor(p / 2^18) (SSF) and lo = p mod 2^18 (SSI), not four float partial products of 12-bit halves; no MR accumulator (nothing an interrupt could take between instructions) |

**The check** (`scripts/mnm_identity.py`): every machine over the 366 golden cases' notes and
increments plus two variants of each whose knobs change mid-note at random (its own seed per
case; 1,098 runs), each output's words hashed; the re-coded machines against a983674 (the
DDRW fix alone): every run identical. The gate's SHARC runner then holds the DSP to this model
bit for bit (part `mnm`), and `test_mnm.py` the model to the Monomachine.

**Instructions a Monomachine block** (16 frames, run mode, the average over those runs):

| machine | before the re-code (a983674) | v0.42 | |
|---|---|---|---|
| DPRO-WAVE | 8,072 | 6,843 | -15 % |
| SID 6581 | 18,802 | 14,144 | -25 % |
| DPRO-DENS | 17,784 | 14,102 | -21 % |
| DPRO-DDRW | 16,021 | 11,684 | -27 % |
| VO-6 | 20,171 | 16,608 | -18 % |

These are instructions only; the loops' L2 loads and stores of scratch words (the larger
part of each removed one: about ten a sample in DDRW's wave loop) cost more than an
instruction each on the unit. The SHARC runner's cost step (`--steps cost`) and the unit's
load meter (FUNC held on a Monomachine page) are the measures.

The check found one mistake on the way: a VO-6 loop counted in R3, which its body reads (F3,
the ramp's step); `loop_r` catches a body that writes its count, not one that reads it, and the
identity check caught it (86 runs differed); that loop keeps its scratch count.

## New instruction forms

`R = R * R (SSF)` and `R = R * R (SSI)` are the first fixed-point multiplies in our code
(compute type, multiplier opcodes 0x78 and 0x70: 01 y x f 0 0 r, PRM Table). selas encodes
them as `0x0197844e` / `0x0197044e` for `R4 = R4 * R14`: compute field `0x17844e`, cu 01 (the
multiplier), opcode 0x78 / 0x70, Rn 4, Rx 4, Ry 14, as the PRM's compute-field layout (Figure
18-1) and multiplier table give them. digikit's decoder walks them as one confident instruction
each, and the gate's SHARC emulator (`compute_mult.py`: the exact product, doubled for signed
fractional, bits 63..32 or 31..0) runs them; the SHARC runner's `mnm` part holds every Monomachine
voice's output to the model bit for bit. Neither form keeps state between instructions.

## 3. Toward 16 voices (opt-mnm, 2026-11-12), the same words bit for bit

**Not in the v0.52 merge (main's rule b, 2026-11-13).** v0.51 made these engines lighter its own way (an
oversampling switch, OS 1 halving DPRO's and WAVE's work; SID/DDRW/DENS/VO-6 re-coded), and upstream's engine
files won. Everything below was dropped with them: the engines' edits, the decimator (its new form needs F11 set by
the caller and clobbers I0, which upstream's SID and WAVE do not provide for), and the interpolator's L1 copy
(upstream's DPRO build does not fill it). It is kept here as the record of what opt-mnm measured on v0.48.

The five MONOMACHINE engines re-scheduled again, every output word the same (`scripts/mnm_identity.py`
against f649683c: SID 213, WAVE 240, DDRW 198, DENS 183, VO-6 222 runs, 0 differ; the decimator also
over 400 random cases with NaN, denormal and out-of-range words). One voice, steady block, the engine's
own part (`scripts/dsp_cost.py`, opt-host's method: instructions + 4 L2 + 10 DDR; the target for 16
voices with room is about 11,200):

| engine | f649683c | now | what |
|---|---|---|---|
| SID 6581 | 26,025 | 11,177 | decimator: constants held, y1 x1 once a sample, the state's shifts as renaming, products and sums on multifunction instructions; TRI/SAW/PULS fused with the phases (a << 8 wraps as AND M24) |
| DPRO-WAVE | 15,730 | 8,457 | the sample loop in registers; the decimator as SID |
| DPRO-DENS | 18,310 | 8,650 | build loop in registers, the partner not read at crossfade weight 0; DPRO's interpolator taps on multifunction instructions; dec2's allpass stages fused in pairs; the interpolator's table in L1 (below) |
| DPRO-DDRW | 31,199 | 15,991 | one Digibank read a sample when no wave change is pending (old + fade (new - old) is old); mix loop in registers; DPRO as DENS |
| VO-6 | 32,888 | 20,838 | the 24-bit MPY as one SSF (was a 45-instruction subroutine); floor by `IF LT`; ramps held, skipped when the targets hold; the series formants on words |

Where a fast path stands in for the general one (DDRW's steady wave, DENS's weight 0, SID's TRI without
its MAX), the general path's arithmetic gives the same word there: x - x = +0, and +-0 added to a non-zero
word or to +0 leaves it; a limit the value is already within. With NaN in the state (the runner's
garbage step) those paths now give finite words where they gave NaN.

**The interpolator's table in L1.** DDRW and DENS read ~10 words a sample of DPRO's 320-word interpolator
table; it was in L2 (v0.36). build() now also copies it to L1 `dsp.MNM_INTERP_DM` (0x2e1200..0x2e1700, the
memory arbiter's allotment after trackbuf.asm, whose span now ends there), and interp reads it there: DDRW
21,111 -> 15,991, DENS 11,210 -> 8,650 (a 3-PCH chord about -10k).

**What is left is not bit-exact work:** VO-6 (20,838) is mostly the 56300's exact arithmetic (floored
stores, integer series resonators); DDRW (15,991) its two waves' builds, interpolators and the 2:1
decimator. The User chose SIMD (voice pairs) before any approximation. PERC's code grew 470 B
(171,916 of 172,032).

## 4. v0.52's engines re-scheduled, bit-identical to v0.52 (2026-11-13)

(Section 3's work was on the v0.42 engines; v0.52 took v0.51's lighter ones, and this carries it over to them.)

v0.51's lighter engines (SID at 4x, DDRW and DENS read at 1x, VO-6's series formants in float) re-scheduled
without changing a word: `scripts/mnm_identity.py` against v0.52's own code, SID 213, WAVE 240, DDRW 198,
DENS 183, VO-6 222 runs, 0 differ. One voice, steady block, the engine's own part (`scripts/dsp_cost.py`):

| engine | v0.52 | now | what |
|---|---|---|---|
| SID 6581 | 9,367 | 4,245 | the decimator: constants held, y1 x1 once a sample, the state's shifts as renaming, products and sums on multifunction instructions; TRI/SAW/PULS fused with the phases (a << 8 wraps as AND M24) |
| DPRO-WAVE | 15,708 | 8,436 | the sample loop in registers; the decimator as SID's |
| DPRO-DDRW | 18,778 | 9,884 | one Digibank read a sample when no wave change is pending (old + fade (new - old) is old); the mix loop in registers; the interpolator's taps on multifunction instructions; its table in L1 |
| DPRO-DENS | 10,153 | 4,455 | the build loop in registers, the partner not read at crossfade weight 0; the interpolator as DDRW's |
| VO-6 | 30,412 | 17,801 | the 24-bit MPY as one SSF; the floor's LSB down by `IF LT`; ramps held, skipped when the targets hold, floats when the series is float; the resonators' y1/y2 renamed, their input through I0 |

Where a fast path stands in for the general one (DDRW's steady wave, DENS's weight 0, SID's TRI without its
MAX), the general path's arithmetic gives the same word there: x - x = +0, and +-0 added to a non-zero word or to
+0 leaves it; a limit the value is already within. With NaN in the state (the runner's garbage step) those paths,
and VO-6's floor, give finite words where they gave NaN.

**DPRO's interpolator table in L1.** DDRW and DENS read ~10 words a sample of its 320 words; build() also copies
it to L1 `dsp.MNM_INTERP_DM` (0x2e1200..0x2e1700, docs/memory-map.md), where interp reads it.
