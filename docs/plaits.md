# PLAITS: Plaits engines on the DN2 (fork, not released)

A seventh Monomachine-style machine, **Plaits / PLT** in MACHINE SEL (machine type 18), after
SOPHIE. A port of Mutable Instruments Plaits' engines (two at first, thirteen since 2026-11-09:
see *The other engines*) (Emilie Gillet,
github.com/pichenettes/eurorack `plaits/`, MIT; THIRD-PARTY.md): **WS** (waveshaping) and
**GRAIN** (granular formant). More engines can join MODL later, each one a DSL routine.
**GRAIN was removed on 2026-11-09** (the User: DSP room for the CHOR and WIDE inserts): see
*GRAN removed*; what is written about it below is its history.

`src/dnfw/mnm/plaits.py`, in the DSL (`dnfw.perc.dsl`): one program for the SHARC code and its
run-mode model, in PERC's voice like the Monomachine machines (`docs/mnm.md`).

## The page

| knob | what | range |
|---|---|---|
| HARM | WS: the waveshaper (Plaits' five Tides tables, crossfaded); GRAIN: the second formant's ratio (-24..+24 semitones) and, below the middle, the carrier's bleed | 0..100 % |
| TIMB | WS: the wavefolder's gain; GRAIN: the formant (24..108 semitones) | 0..100 % |
| MORP | WS: the slope oscillator's shape (its pulse width, 0.5..0.95); GRAIN: the carrier's shape | 0..100 % |
| MODL | the engine: WS, then the engines below (2026-11-09), in MODL's order (GRAN's slot retired: plays and shows WS) | one choice each |
| FINE | cents on the note (2026-11-09), shown as +0 at the centre | -64..+63 cents |
| TUNE | whole semitones on the note (2026-11-09; continuous until then), shown as +7, -12 | -24..+24 (+0 at the centre) |

TUNE is (knob x 49 >> 7) - 24 and FINE knob - 64 (the page's value by the same arithmetic, its
signed figure under the knob). At their centres the note is bit for bit what it was. FINE is the
fifth record (BASE's), at 0 in a project saved before it: MACHINE SEL starts it at the centre, but
a PLAITS track saved earlier comes back 64 cents flat until FINE is turned up.

The two other places are empty (`---`). MACHINE SEL starts it at WS, every knob in the middle.

## What is left out (against Plaits)

- Plaits' **AUX** output (WS's triangle-and-fold-2 mix, GRAIN's Z oscillator): the track is mono.
- Plaits' **LPG** and its decay, and the internal envelope: the DN2's track filter and amp do that.
- Trigger, level and FM inputs, the model's accent.
- **No reset on a trig**: Plaits' engines run on through every note, as on the module (the two
  Digitakt II ports reset per note and report a recurring trigger click).

## Numbers

44.1 kHz in PERC's stream; every frequency is Hz / 44100 (so a note sounds at its pitch).
Plaits' parameter interpolators run over a 16-sample half (Plaits: 12). Sines are PERC's sine
table (256 a turn, linear; Plaits' is 512), exp2 PERC's table, divisions PERC's reciprocal.
The tables (WS's five shapes, 5 x 257, and the fold, 516) are rebuilt from Plaits'
`lookup_tables.py` formulas and ship in zpack after VO-6's (`dnfw.mnm.core.PL_TABLES`).

GRAIN's two grainlets share their carrier (the same frequency, shape and bleed in Plaits too, so
the same numbers), which leaves one carrier and two formants a sample.

Cost, the whole voice in a DN2 block (the model's steps, `test_perc_live`'s method, at its
defaults, every knob up and down, random knobs, notes 36..84): **WS 20,316, GRAIN 22,054**, so
`MNM_COST` 25,000 (SOPHIE 34,000, SID 60,000). The machine itself, a 32-sample block: WS about
5,600, GRAIN about 8,000.

Size, on this fork's base without SID, the DPRO machines and VO-6 (28eb110): PERC's code grew
4,142 bytes to 123,128 (27,441 instructions), its L2 span 4 KB to 0x1E400 (SMP_SW 0xbef200).

| | base (28eb110) | + PLAITS | cost | free |
|---|---|---|---|---|
| DSP upload, unpacked | 999,036 | 1,003,180 | +4,144 B | 45,395 B |
| USB image | 2,049,795 | 2,053,431 | +3,636 B | 43,721 B |

(Its tables, 1,801 Q23 words, ride in zpack.)

## Checks (this fork)

`plaits_ref.py` (outside the repo, `dn2mk2-scratch/plaits303/ref/`) is a Python reference of
the original C++ engines and their tables. Held to the original C++ itself (compiled from
pichenettes/eurorack, block 16), with its float32 accumulators: **110..116 dB** on WS and GRAIN,
every window of 8,000 samples.

The run-mode model (the program the SHARC runs, `compare_plaits.py`) against the reference at
44.1 kHz, the same carrier frequency, 8,000 samples a case:

| case | SNR |
|---|---|
| WS, four cases (notes 36..84, folds, shapes) | 115.3..121.6 dB |
| GRAIN, four cases, against the reference with PERC's exp2 | 84.5..87.1 dB |
| GRAIN, against the reference with Plaits' own pitch tables | 49.2..71.2 dB |

GRAIN's lower figure is its formant frequency: PERC's exp2 and Plaits' 1/256-semitone tables
differ by up to 2.3e-4 (0.4 cent), and the formant runs up to a few turns a grain. With the same
exp2 the rest is the sine table's (256 against 512).

In the SHARC runner (`sharc:mnm+frame`, OS 1.12): PLAITS's buffer and state bit-exact to the model
every block (beside the next machine, every knob up, the budget and rest checks). Unit tests: the
base's results. Its page drawn in the 1.12 emulator (a snapshot booted on the build), the big-knob
style: HARM, TIMB, MORP, MODL (WS, GRAN), TUNE.

**Not done**: the project's ship gate needs the owner's bench; no build of this branch is
cleared to flash. Unverified on hardware: the sound, the DSP time on the unit, the page.

## The other engines (2026-11-09)

Each further engine is its own module, `src/dnfw/mnm/plaits_<name>.py` (`MODEL`, `init`, `half`),
listed in `plaits.ENGINES`; MODL's choices are `plaits.MODELS` (the page reads them), the knob
picks one as knob x N >> 7. Their common ground is `src/dnfw/mnm/plk.py`:

- **The model's own words.** The note (`S_NOTE`, TUNE added), the model last rendered (`S_LAST`),
  the trigger (`S_TRIG`), the voice's random generator (`S_RNG`), then 48 union words. A model is
  started (its `init`, Plaits' Init and Reset) when MODL chooses it; WS and GRAIN keep their own
  words and are never restarted, as before.
- **The trigger.** A trig sets S_TRIG: the next half is Plaits' TRIGGER_RISING_EDGE, its trigger
  input patched (never a gate, never unpatched); accent 0.8 (Plaits' with LEVEL unpatched). The
  oscillator engines ignore it.
- **Memory.** Each voice has 32 KB of DDR of its own at 0x82600000 + slot x 32 KB (`plk.BIG_DDR`,
  512 KB for sixteen; nothing ships there, an engine clears what it reads): delay lines, modes,
  the diffuser.
- **Arithmetic.** exp2 from the float's exponent and a polynomial (2e-7, float32's rounding), a
  polynomial sine (1.9e-7), stmlib's random generator (one per voice, seeded 0x21), PERC's
  reciprocal for divisions. The references take the same arithmetic ("matched"); Plaits' own
  SemitonesToRatio reads 1/256-semitone tables, so against those ("faithful") an engine's pitch
  differs by up to 0.4 cent and its phases drift apart: the faithful figures below measure that
  quantisation, not the port.

The references (`dn2mk2-scratch/allplaits/ref/`, outside the repo) are Python ports of the C++,
each held to the C++ itself (compiled from the read-only clone, `-ffp-contract=off`, block 16,
48 kHz, Plaits' own tables) with float32 rounding; the run-mode model (the program the SHARC runs)
against them at 44.1 kHz.

### VA (virtual analog)

Plaits' VIRTUAL ANALOG (`virtual_analog_engine.cc`, VA_VARIANT 2): OUT = a variable saw (MORPH:
its notch's pulse width, its triangle near the middle; detuned from the note by HARMONICS'
interval: unison, fifth, octave, octave + fifth, two octaves, either way) + a square hard-synced
to the note (TIMBRE: its pulse width, from the middle up the sync's interval, its level).
Plaits' primary and auxiliary oscillators only feed AUX: not rendered. One deviation: the synced
square starts at waveshape 1.0 (Plaits ramps it from 0 over its first block): the first 16
samples after VA is chosen differ.

| | |
|---|---|
| reference vs the C++ | 180.5..184.8 dB, six cases (the 9-digit printout's limit) |
| model vs reference, matched | 90.8..144.8 dB, seven cases (notes 24..84, the knobs' ranges) |
| model vs reference, faithful | 12.0..46.6 dB (the sync case lowest: its interval's 0.4 cent moves every reset) |
| cost, a DN2 block | 7,820 steps at worst (entry block 7,375) |
| PERC code | +3,420 B (with the dispatcher's arm) |

### The other ten (agents' ports, integrated and checked here)

MODL's order: WS, GRAN, VA, FM, ADD, SWRM, NOIS, PART, STRG, MDAL, BD, SD, HH (Plaits' own order;
not ported: wavetable, chords, speech). Every engine below renders Plaits' OUT only. "ref vs C++":
the float32 reference against the original C++ at 48 kHz; "matched": the run-mode model against
it at 44.1 kHz with the same arithmetic (the 85 dB target: GRAIN's figure); "faithful": with
Plaits' own pitch / sine tables. Steps: the worst DN2 block (pitch + two halves), the model-entry
block (its init) apart where larger. Code: PERC's growth as the commits added them.

| model | what (Plaits) | ref vs C++ | matched | faithful | steps | code |
|---|---|---|---|---|---|---|
| VA | virtual analog (VA_VARIANT 2) | 180.5 dB | 90.8 dB | 12.0 dB | 7,824 | +3,420 B |
| FM | 2-operator FM, 4x downsampled | 186.7 dB | 106.8 dB | 10.3 dB | 15,184 | +2,452 B (FM + ADD) |
| ADD | additive (harmonic oscillators) | 175.2 dB | 105.3 dB | 62.3 dB | 17,740 (entry 18,093) | |
| SWRM | swarm: 8 grain-enveloped saws, burst on a trig | bit-exact | 152.9 dB | -2.0 dB | 8,476 (entry 8,600) | +1,940 B (with the cost's constant) |
| NOIS | clocked noise through the SVF | bit-exact | 102.3 dB | 3.6 dB | 5,864 | +3,648 B (NOIS + PART) |
| PART | particles, post filter, diffuser | bit-exact | 92.4 dB | 25.7 dB | 19,517 (entry 43,725) | |
| STRG | three inharmonic strings, rotating on a trig | bit-exact | 91.6 dB | 40.0 dB | 25,035 (entry 43,685) | +5,614 B (STRG + MDAL) |
| MDAL | modal resonator and exciters | bit-exact | 70.2 dB | 65.5 dB | 32,280 (entry 32,794) | |
| BD | analog bass drum | bit-exact | 108.1 dB | 73.8 dB | 8,007 | +4,444 B (BD + SD + HH) |
| SD | analog snare drum | bit-exact | 103.4 dB | 85.5 dB | 9,646 (entry 9,821) | |
| HH | hi-hat (square noise, OUT's) | bit-exact | 121.7 dB | 54.3 dB | 6,141 (entry 6,268) | |

("bit-exact": the reference equals the C++'s printed floats in every case.)

- **MDAL's 70.2 dB** (three cases with damping near the top) is below the target: there the modes'
  Q reaches about 4 million and PERC's reciprocal, 1 ulp off a division, moves their phase over a
  long ring. With the DSP's own routines in the reference it is bit-exact (200 dB); it is float32
  sensitivity of Plaits' own high-Q modes, not a porting error.
- **The faithful gaps** are Plaits' 1/256-semitone pitch tables (their quantised frequencies drift
  the phases apart, or, in the random engines SWRM / NOIS, move a grain or a clock edge to another
  block so the sequence differs), ADD's and FM's 1,024-point sine table, STRG's interpolated
  lut_svf_shift (computed here) and PART's 12-bit diffuser (floats here). Each agent's NOTES.md
  measures them piece by piece.
- **Deviations** (each module's docstring has its own): 44.1 kHz with Plaits' per-sample time
  constants kept (decays, pulse lengths, LFOs ~9 % longer); the sub-oscillators, organ
  harmonics, sines and second noises that only feed AUX left out (their random draws still taken,
  so the sequence is Plaits'); STRG's f0 delay 14 blocks (5.1 ms); the never-struck string's
  1/0 as 1/1e-30.
- **The OUT stage.** Plaits never sends an engine's raw OUT to its jack: `voice.cc` gives each a
  gain, a fixed one (VA, ADD, the drums 0.8; FM 0.6) or a negative one, stmlib's Limiter with that
  pre-gain (SWRM 3, NOIS 1, PART 2, STRG 1, MDAL 1: a peak follower, x 0.8), and the DAC's 16 bits
  clip at +-1. The raw engines go well past it (PART to 8.0 on a trig right after it is chosen,
  MDAL to 3.6), so `plaits._post` does the same after each of these engines (its limiter's peak in
  the slot's word 250, reset when the engine changes); WS and GRAIN stay as before, without it.
  Held to stmlib's Limiter and Clip16 in float32 (`post_check.py`): 144..200 dB. The engines'
  comparisons above are of the raw engines (`plaits.POST` off).
- **Memory**: SWRM 88 DDR words a voice, ADD 96, MDAL 192, STRG 3,984, PART 8,192 (the diffuser).
- **Cost in PERC's budget** (the whole voice in a DN2 block, `test_perc_live`'s harness: the steps
  above plus the voice's own ~14,700): WS 20,295, GRAN 22,077, VA 21,586, FM 29,216, ADD 32,682,
  SWRM 22,885, NOIS 20,484, PART 58,357, STRG 58,409, MDAL 47,418, BD 21,822, SD 24,451, HH 20,649
  (PART's and STRG's worst is their entry block, clearing their DDR). With the OUT stage (below):
  WS 20,305, GRAN 22,087, VA 22,014, FM 29,644, ADD 33,110, SWRM 23,818, NOIS 21,396, PART 59,333,
  STRG 59,325, MDAL 48,604, BD 22,250, SD 24,879, HH 21,077. `MNM_COST["PLAITS"]` 60,000;
  sixteen voices at it, 960,000, stay under MNM_BUDGET, so one figure serves every engine.

Size, the commits on this branch (base: sophie-v043-os112-all, de642a3, build 149feeca):

| | base | + framework + VA | + FM, ADD | + NOIS, PART | + BD, SD, HH | + STRG, MDAL | + SWRM (final) |
|---|---|---|---|---|---|---|---|
| PERC code | 128,290 | 131,794 | 134,246 | 137,894 | 142,338 | 147,952 | 149,892 |
| DSP upload free | 33,079 | 29,575 | 27,123 | 23,475 | 19,031 | 13,419 | 11,479 |
| USB image free | 38,570 | 37,257 | 35,944 | 34,429 | 32,611 | 30,086 | 29,278 |

Then the OUT stage and the cost at 60,000 (the final build, d8f5c3c9): PERC code 150,412 B (span
0x24C00), DSP upload 10,959 B free, USB image 29,076 B free.

PERC's L2 span grew to 0x24C00; the sample machines' code moved below it (0x200b6000, after FDN8's
code) so it could.

**Checks of the final build**: the SHARC runner (`sharc:mnm+frame`) holds every model's track
(triggered at blocks 1 and 4, off-centre knobs) and a track walking MODL through every model to the
model, bit for bit, every block; WS and GRAIN are bit-identical to the build before.

## GRAN removed (2026-11-09)

The User removed GRAIN (granular formant) to make DSP room for the CHOR and WIDE inserts. The
other twelve engines are untouched.

- **MODL keeps its 13 knob slots.** GRAN's slot (choice 1, knob 10..19) is *retired*: an empty
  name in `plaits.MODELS`. The DSP plays WS there (`half`'s first arm takes choices <= 1); the page
  shows it as WS and a turn steps past it (`pages.MNM_RETIRED`, used by md_page.c, page.c and
  fmt.c's `mnm_quant`; a jump that lands on it goes to WS). So every saved knob and p-lock keeps its
  engine: VA is still 20..29, HH still 119..127, and an old GRAN p-lock now plays WS.
- **Size** (base sophie-v043-os112-b4 8e14c9a, build 03f28370): PERC code 150,454 -> 148,496 B;
  DSP upload 2,607 -> 4,567 B free (**1,960 B freed**); USB image 26,147 -> 26,753 B free
  (**606 B freed**).
- **Unchanged engines.** The run-mode model's output, hashed for every MODL slot at both ends of its
  knob range and four knob sets (`same_all.py`), is identical to b4's for WS and VA..HH; the retired
  slot hashes as WS. Each half is 4 steps cheaper (one compare fewer in the dispatcher).
  `MNM_COST["PLAITS"]` stays 60,000 (PART / STRG set it).
- GRAIN's state words (slot words 7..16) and per-half words are kept, unused, so WS's layout is
  bit-identical.

## A voice's start (2026-11-09)

The User: PLAITS played by key and locked to one voice, but sequenced with voice rotation it
stayed silent and LEV read `CPU` (the frame guard leaving voices out for time). As Optimist's
`perf(notestart)` did for its Plaits, the start of a voice is made light:

- **PART's and STRG's DDR clear is deferred** (`plk.defer_clear` / `clear_half`): their init no
  longer clears 8,192 / 3,984 DDR words in the voice's start block; each half then clears 1,024
  of them (top down) and is silent, the note's trigger kept, until none are left (PART four
  blocks, 2.7 ms; STRG two, 1.3 ms; then STRG's `init_tail`). Only when the engine starts on a
  voice (a voice changing machine, or MODL); a voice already on it plays its next note at once.
  `S_CLR` is slot word 7 (GRAIN's, free).
  2026-11-11 (plaits16, declared: not bit-exact in time against the deferred clear): **PART clears just in
  time** (`plaits_part._jit`): it sounds from its first half, its output word for word that of a clear at the
  start; each diffuser word is zeroed right before the first half that reads it, or, a half reading only words
  no write has reached, the stage reads a zero row (fixed lines) or runs its x = +0 loop (AP4, DEL) instead.
  `S_AGE` (slot word 8, GRAIN's) counts its samples until 3,456. **STRG's chunk is 800 words a half**: its
  3,984 in 5 halves, rendering from the sixth (main's 512: from the ninth). docs/dsp-perf.md has the numbers.
- **The guard keeps a start block's cost out of its expectation** (`guard.FRESH`, set by PLAITS'
  change of engine, which a voice changing machine to PLAITS also makes): the next block is
  expected at FLOOR, then at what it measures, so one heavy start cannot get the note's next
  blocks refused twice and the note stolen.
- **A PLAITS note's first two blocks are expected at a fixed bound** (`program.MNM_START`, its
  MNM_COST 60,000; per slot at `BOUNDS_OFF` each block, `guard.START_BLOCKS`), not at 1.5 x the
  slot's stored cost, which on a rotated voice is another note's or a start block's.
- **A refusal in a PLAITS note's trig block is no strike**: it is tried again the next block; only
  the refusals after it count towards the steal (two in a note).
- All three are PLAITS' only: for every other slot the bound is 0 and FRESH never set, so SOPHIE,
  TB303, PERC and the sample machines decide exactly as before (the runner's `rotate` and
  `stress` guard traces compared, below).
- Old voices: Plaits has no LPG here (OUT goes to the DN2's filter and amp); after a note-off and
  the amp's release a voice rests 64 quiet blocks later and costs nothing (runner step `rests`:
  PLAITS from block 65, as SOPHIE).

Runner (memory-cost clock, `scripts/sharc_waverider_m5.py --steps notestart,rests,rotate`): a
voice changing machine to PLAITS, its start block, our time above the silent block (cycles):

| engine | start before | start after | steady |
|---|---|---|---|
| WS | 59,548 | 59,573 | 15,892 |
| VA | 64,717 | 64,742 | 18,538 |
| FM | 73,208 | 73,233 | 29,058 |
| ADD | 95,293 | 95,318 | 48,870 |
| SWRM | 65,534 | 65,559 | 18,104 |
| NOIS | 58,001 | 58,026 | 11,633 |
| PART | 190,748 | 74,604 | 41,414 |
| STRG | 176,277 | 74,392 | 70,542 |
| MDAL | 147,586 | 147,611 | 99,755 |
| BD | 60,761 | 60,786 | 15,098 |
| SD | 67,045 | 67,070 | 20,116 |
| (SOPHIE) | 69,959 | 69,963 | 26,671 |
| (TB303) | 117,552 | 117,556 | 71,166 |

The run-mode model renders every engine but PART and STRG bit for bit as before (those two start
four / two blocks later). **Not measured: the unit.** On the memory-cost clock even the old build
admits every rotated PLAITS note (WS at 0.17 of the frame); what the unit measures differently is
not known, so whether this is enough is the User's test on the instrument.

## Sixteen voices (2026-11-10, branch sophie-v043-os112-poly16)

The User: "each instrument must be able to play 16 voices". Measured on the unit (b5diag2, 2026-11-09):
the guard's limit about 355,000 cycles a frame, the rest of the DN2 about 43,000, so at most ~19,500
cycles a voice; b6's PLAITS voices cost 20,000 .. 48,000. Every change below keeps the engines' output
**bit for bit** as b6's (so every reference figure above still holds): `golden.py` (outside the repo,
`dn2mk2-scratch/poly16/`) hashes the full voice (frame, engine, resampler, output guard) for every MODL
slot x 5 knob sets x a note / trig script with an engine switch: 65 / 65 identical to b6. The
reorderings were also run 600 blocks (PART), and the shared routines held to the old ones on random
inputs (`sin_eq.py` 25,530 sines, `ages_eq.py`, `guard_eq.py` 400 blocks with inf / NaN).

What was done (the commits on this branch):
- **The voices' slots in L1** (`dsp.MD_STATE_DM` 0x2e7000, 16 x 1 KB; L2 until now): every voice of ours
  reads and writes its slot all through its block. The startup's DM cache is 16 KB (0x2ec000..,
  docs/waverider-dsp-silence.md), so REGION may reach 0x2eb000. Zeros at power-on: a fill block.
- **mnm_ages a loop over the slots** (it was unrolled 16 times): 8.1 KB of the DSP upload back, the room
  the faster kernels take.
- **DDR out of the engines' loops**: MDAL's mode states / amplitudes, ADD's interpolators / amplitudes,
  STRG's string states, SWRM's voices 0..4 now live in the slot's free host words (W[9..63]: the
  Monomachine host writes W[1..8] only) and the union's free tail; per-half coefficients and rows in
  the render scratch's rows SID left free (XB, YB, L1); FM's FIR copied to L1 once a half. MDAL runs
  mode by mode (a mode's state in registers through the half), PART's diffuser stage by stage (every
  read is 125+ samples behind its write, so a stage may run its 16 samples in a row; its fixed stages
  walk the buffer by post-decrement).
- **Instructions**: the sine without branches (TRUNC + `IF LT`, the fold by MIN / MAX), inline where
  hot (FM, ADD); the OUT stage, the output guard (a sum of x x 0 for the non-finite test), STRG's
  excitation, PART's particles with their state in registers; a voice's reset clears 8 words a pass.
- DSL (`dnfw.perc.dsl`): `par` (one compute with one memory move), `fop_lt` / `fop_if` (a conditional
  compute on the last ALU result's flags), `fabs_`, `float0`, `geti`, `ldm` / `stm` (M7's -1), and a
  load / store folded into the adjacent independent compute automatically. Two traps found by the gate's
  decode step (selmap against digikit), both now refused by the DSL: a compute's move through I4 / I5
  (`compute, R = DM(I4, M6)`, `compute, R = DM(k, I5)`: selmap reads 4 bytes, the compute gone), so
  only I0..I3 (`dsl.PAR_I`); and multifunction computes (selmap reads selas's `Fm = Fx * Fy, Fa = ...`
  as `Fm = MRF + Fx * Fy`, digikit as a float multiply). selas also encodes illegal multifunction
  register sets without a word.

Cost, a steady block (the model's instructions with every jump and call counted, + 0.9 x (4 L2 + 10
DDR), the runner's memory-cost clock; the worst of 5 knob sets over blocks 8..19, trigs included):

| engine | b6 | poly16 | | engine | b6 | poly16 |
|---|---|---|---|---|---|---|
| WS | 16,951 | 10,807 | | PART | 41,367 | 25,659 |
| VA | 25,364 | 12,321 | | STRG | 70,808 | 23,481 |
| FM | 30,700 | 17,148 | | MDAL | 102,575 | 21,075 |
| ADD | 50,937 | 14,921 | | BD | 18,548 | 11,511 |
| SWRM | 22,927 | 13,899 | | SD | 23,738 | 12,814 |
| NOIS | 15,559 | 9,907 | | HH | 17,447 | 9,303 |

The runner's poly16 step's own case (the PLAITS defaults, a held note, `perblock.py`): a steady block
WS 10,541, VA 9,775, FM 16,997, ADD 14,871, SWRM 12,190, NOIS 9,139, PART 21,394 (25,259 in a half
whose diffuser window wraps the buffer: the old per-sample path), STRG 21,705, MDAL 19,265, BD 11,383,
SD 12,567, HH 8,810; a fresh voice's first block (its reset) 23,656 on every engine.
(b6's WS voice measured about 20,000 cycles on the unit against 16,951 here.) The worst block (an
engine's start with its reset, PART's / STRG's deferred clear) 30,500 .. 45,000.

The guard (PLAITS slots only; every other machine decides as before):
- `program.MNM_START["PLAITS"]` 30,000 (was 60,000): sixteen notes started together are each
  expected at it for their first two blocks.
- `guard.PLAITS_FLOOR` 20,000 (was 30,000), and a measured slot expected at 1.25 x its last cost
  (`PLAITS_SLACK_SHIFT`; was 1.5 x).
- A slot without a measured cost (its engine's start, FRESH, or a voice never rendered yet) expected
  at its start bound, not FLOOR's 60,000: a voice refused during PART's / STRG's start never got a
  cost, stayed at 60,000 and was refused until stolen.
Provisional until the unit's costs are measured.

The runner's poly16 step (16 PLAITS voices triggered together and held, the memory clock; build
38b8cbe5, the branch's last): WS VA FM ADD SWRM NOIS MDAL BD SD HH every voice sounding, no guard
skip after the start (the heaviest: MDAL 21,816, FM 18,204 a voice); PART and STRG 13..14 of 16 (their
frame is full there: 20,000 .. 26,800 a voice with their DDR charged at 9 cycles an access, the
runner's estimate; the unit's DM cache serves DDR, so the unit decides). The same build: the decode
step (selmap and digikit, every instruction), DSP identity, the hardware rules, guard / rotate /
stress / TDM / the Monomachine machines bit-exact (44 PASS), boot from reset (800 M instructions). Runner step `poly16` (`scripts/sharc_waverider_m5.py --steps poly16`): sixteen PLAITS
voices at once on each engine, the memory clock.
