# DRUM: one synth drum machine, its type on page 1 H (machine type 56)

The User (2026-11-19): *"one engine for kick, snare, hh, closed hh etc."*, a wide palette on one page per type that
sounds great; the research, the design and the stage-1 / 1b renders are in `scratch/drum-engine/` (design.md,
measurements.md, the WAVs). This is the firmware.

**Stage 2a (2026-11-20): KICK, end to end. Stage 2b: SNARE. Stage 2c: CLOSED and OPEN HAT (CLOSED chokes OPEN on its
track). Stage 3: TOM, and the re-voicing of the study's stage 3 (scratch/drum-engine/drum_v3.py) with the TR-808's
kit levels (below, "Stage 3"). Stage 4: CLAP, RIDE and CRASH (below, "Stage 4").** TYPE lists KICK, CLAP, SNAR, CRSH,
CLHH, OPHH, RIDE, TOM; each type has its own page (the table of hosts, below). RIM, COWBELL later.

`src/dnfw/engines/drum/`: `drum.py` (the machine: its pages, TYPE, init / trig / pitch / half), `kick.py` (KICK in the
DSL), `snare.py` (SNARE), `hats.py` (CLOSED and OPEN HAT, the choke), `dmath.py` (e^x, log2, the LCG, the soft clip's antiderivative), `ref.py` (the reference: numpy float32,
the arithmetic written plainly).

## KICK's pages

| page | knob | range | what |
|---|---|---|---|
| 1 A | TUNE | -24 .. +36 semitones about 50 Hz (whole semitones), plus the note | the body's pitch |
| 1 B | DCAY | 5 ms .. 8 s (to -60 dB), exponential | the body's decay |
| 1 C | SWEP | 0 .. 7 octaves (start under 12 kHz) | the pitch jump at the attack |
| 1 D | SWTM | 1 .. 150 ms, exponential | how fast it falls |
| 1 E | CLIK | a balance, -64 .. +63 (C at the centre): left the body+noise only, C both at 100 %, right the click only (stage 5) | the click against the body |
| 1 F | CLKT | 0 .. 0.75: the pulse-and-noise click's low-pass 400 Hz .. 16 kHz; from 0.8 (knob 102): a chirp from 1.5 .. 9 kHz down to 250 Hz | the click's colour (Click Colour): pulse and noise up to 101, the chirp from 102 |
| 1 G | DRIV | soft clip, gain 1 .. 31 (+30 dB), level held | the 909 shaper, the 808 boom |
| 1 H | TYPE | KICK CLAP SNAR CRSH CLHH OPHH RIDE TOM (stage 4) | the type (a list popup with tags) |
| 2 A | SHAP | 0 .. 0.45 turns of self phase modulation | the body's wave, sine .. brighter |
| 2 B | HOLD | 0 .. 250 ms | full level before the decay |
| 2 C | SIGH | 0 .. 25 % | the 808's slow pitch fall with the decay |
| 2 D | CLKL | 0.2 .. 20 ms | the click's length |
| 2 E | NOIS | 0 .. 0.5 | low-passed air under the body |
| 2 F | VEL | 0 .. 1 | how much a soft hit loses (sweep depth, click; stage 3: the clip and the sigh too); the level by velocity is PERC's, every machine's |
| 2 G | SWHD | 0 .. 30 ms (stage 3) | the sweep held at its top before it falls (the 909's 16 ms: knob 68) |
| 2 H | CURV | -100 % .. +99 % (stage 5): 0 the exponential fall, left blends in a straight line over 5 sweep times, right the concave r (2 - r) (holds, then drops) | the sweep's shape (808 / 909-like curves) |

Hard distortion, folding and post-EQ are the inserts' (DIST, FUZZ, FOLD, ...) and the track filter's (the User,
2026-11-19).

## Numbers

44.1 kHz in PERC's stream, 16-sample halves; a hit's values set in the first half after its trig (after `pitch`, so
the note is the hit's). Phases in turns, kept in 0..1 every sample. Sines: `plk.sinp` (PLAITS' copy); e^x: its series
above -0.125, `plk.exp2p` below; log2: the exponent and a degree-8 polynomial on the mantissa (no reciprocal); the
LCG: Plaits'. The drive: SoftClip at gain g, by ADAA (first-order antiderivative anti-aliasing:
F(u) = v^2 / 18 + 4/3 ln(3 + v^2) + max(|u| - 3, 0), v = clamp(u, +-3)) when g > 10, the plain clip below (its
aliasing under the body's own there: -57 dB measured at 50 and 400 Hz); a 12 Hz DC out before the drive, 5 Hz
after it (the User's 2026-11-20 choice: a driven, short corner's offset 10.4 % -> 0.14 %); a retrig fades the cut
sound out in 1 ms.

**The model against the reference** (test/test_drum.py, the voice's own 44.1 kHz stream before PERC's resampler):
-80.9 dB (a held body at drive 100) .. -125.6 dB under the peak, at the start, a tick, an 808, a chirp click, full
chirp and drive; declared tolerance -60 dB.

**Cost** (scripts/dsp_cost.py, the model, a voice-block; engine = the machine's own code): KICK at its start steady
8,866 (engine 6,750), its dearest setting (`DRUM-KICK-WORST`: every knob 127, CLKT at the chirp, full drive with
ADAA) steady 12,067 (engine 9,951), trig block 13,041. Under the 13,100 a voice-block 16 voices with room need
(docs/dsp-cost.md). `MNM_COST` 28,000.

**Level** (dnfw.perc.program LEVEL_DB): -3.0 dB: KICK at its start, the voice's first 300 ms, RMS -8.7 dB at
MD_LEVEL against TRX-BD's -12.7 and EFM-BD's -11.2; the engine's worst corner peaks under 1.0.

**Room**: perc2b (the machines' init bodies) 5,964 of 6,144 B with DRUM's init as a loop: the other types' inits must
share it (one init for the machine, not one a type).

## SNARE's pages (stage 2b, 2026-11-20)

| page | knob | range | what |
|---|---|---|---|
| 1 A | TUNE | -24 .. +24 semitones about 180 Hz (whole semitones: trunc(knob x 48 / 127 + 0.5) - 24), plus the note | the head's pitch |
| 1 B | DCAY | 30 ms .. 2 s (to -60 dB), exponential | the body's decay; the k-th mode decays in it / its ratio; the wires follow it |
| 1 C | TONE | t = min(TONE / 0.75, 1): the modes' levels 1, 0.2 + 0.8 t, 0.8 t^2; from 0.75 (knob 96) a 4th mode up to 0.7 | brightness, richness |
| 1 D | MODE | the four modes' ratios, analog (1, 2, 3.18, 4.16) .. membrane (1, 1.59, 2.14, 2.295), a linear morph | 808/909 tone body .. acoustic head |
| 1 E | SNAP | 0 .. 1.6 x (0.5 + 0.5 vm): a 0.3 ms pulse and noise through an 1800 Hz high-pass, falling in 1.5 ms | the stick (RIM / CLICKY at the top) |
| 1 F | NOIS | a balance (stage 5): body / wires (Body/Wires), the wires' 100 % = 1.4 | the wires ("snappy") against the heads |
| 1 G | DRIV | soft clip, gain 1 .. 21 (1 + 20 DRIV^2), level held (KICK's) | grit (909) |
| 1 H | TYPE | | |
| 2 A | WIRE | the body's decay x 0.25 .. 6, held in 30 ms .. 3 s | the wires' decay against the body's |
| 2 B | GLID | 0 .. 12 % x (0.6 + 0.4 vm), falling in 25 ms | the head's tension glide (modes retuned every 16 samples) |
| 2 C | BUZZ | 0 .. 1: noise x (1 - BUZZ + 2 BUZZ max(tri(the body's phase), 0)) | the wires rattled by the head, once a cycle |
| 2 D | WTON | 1.5 .. 9 kHz x 2^(vm - 1) (a soft hit darker), Q 0.9: band-pass + 0.3 of its high-pass | the wires' band |
| 2 E | WATK | to 0.7 (knob 88): the wires' rise 0.3 .. 8 ms; above: 1 .. 4 clap bursts (2.8 ms each) 6 .. 10 ms apart, then the wires | acoustic delay .. trap clap-snare |
| 2 F | SIZZ | 0 .. 0.8: a second band at min(2.2 x WTON, 14 kHz), Q 1.2 | the sizzle |
| 2 G | VEL | 0 .. 1: vm = 1 + VEL (vel - 1) | how much a soft hit loses (stick, glide, wire brightness; stage 3: the clip) |
| 2 H | WCHR | stage 3: 64 the wires as before; 0..64 the 909's band (no high-pass share), a wire hold up to 24 ms, a threshold close (env - 2e-4 d); 64..127 the band into a 2-pole high-pass at WTON (the 808's) | the wires' circuit, 909 .. 808 |

Stage 1b's Snare2 (scratch/drum-engine/drum_v2.py) with the User's 2026-11-20 choices: **RING is gone** (the body's
T60 is DCAY's alone), the SVFs are stmlib's (Plaits'), the clap bursts fall on whole samples (D = trunc(spacing x
FS)), all four modes and both wire bands always run (a level of 0 when off: one cost), KICK's DC out after the drive
(5 Hz) and its 1 ms declick. Its start: stage 1b's RICH (TUNE 64 DCAY 57 TONE 100 MODE 90 SNAP 48 NOIS 76 DRIV 25;
WIRE 61 GLID 55 BUZZ 60 WTON 70 WATK 22 SIZZ 45 VEL 64). The A/B against stage 1b at its spectrum points:
`scratch/drum-engine/wav/fw_snare_vs_stage1b.wav` (first 250 ms RMS within 0.4 dB at every point).

One voice: `drum.half` runs the type latched at the trig (S_TYPE). SNARE reuses KICK's type-specific state words (each
hit sets every word its type reads) and words 42..71; the shared words (S_TRIG .. S_RNG, S_UP, S_DC2, S_LAST, S_DK) stay
common, so a KICK cut by a SNARE (or back) declicks. Each SNARE hit zeroes its filters and sets its modes.

**The model against the reference** (test/test_drum.py): -100.6 (909) .. -133.5 dB (808) under the peak at the start
(RICH), 808, 909, acoustic, loose, the trap clap-snare, rim / clicky and the worst corner (every knob 127: -104.5).
The reference takes the DSP's sine polynomial (ref.sinp, PERC's, 1.9e-7 off sin) for the modes' coefficients: a
rotor turns its coefficients' last bits into phase sample after sample, and at full drive (slope x7 at zero) numpy's
sin would put the model at -44 dB under the peak in 40 ms (no glide), a frequency 3e-8 of FS apart.

**Cost** (dsp_cost.py, the model): SNARE is branch-free but for the stick's first 13 samples and the bursts'
countdown, so its start and its dearest (`DRUM-SNAR-WORST`: every knob 127, WATK 88) cost the same: steady 10,623
(engine 8,502), trig block 11,725. The runner (sharc_cost.py, its host ~1,000 above the unit's, docs/dsp-cost.md):
SNARE steady 11,621 (engine 8,503) at its start and its dearest, trig block 12,736; KICK 9,877 / 13,078 (dearest),
trig 14,057: SNARE ~10,600 a voice-block steady on the unit, under the 13,100 16 voices with room need. The type's
dispatch costs KICK 13 on the model (8,879 / 12,080 steady, trig 13,058). `MNM_COST` stays 28,000 (KICK's trig block
is the dearest).

**Level**: inside the engine, 0.75 (-2.5 dB, ref.SNARE_GAIN) on the drive's held level; the machine's -3.0 dB as
KICK's. SNARE at its start, the voice's first 300 ms (dnfw.perc.live, the level included): RMS -18.4 dB against TRX-SD's
-17.6 and EFM-SD's -20.1 (KICK -11.0 against TRX-BD's -12.3 and EFM-BD's -10.8 by the same measure); 244 random and
hand corners peak at 0.754 at most (the engine's output).

## The hats' pages (stage 2c, 2026-11-20): CLHH and OPHH

| page | knob | range | what |
|---|---|---|---|
| 1 A | TUNE | -24 .. +24 semitones on the 808's six (205.3, 304.4, 369.6, 522.7, 540, 800 Hz; trunc(knob x 48 / 127 + 0.5) - 24), plus the note | the metal's pitch |
| 1 B | DCAY | CLOSED 8 ms .. 0.6 s, OPEN 80 ms .. 4 s (to -60 dB), exponential | the VCA |
| 1 C | TONE | the band-pass at 7.1 kHz x 2^((TONE - 0.5) 3) (2.5 .. 20 kHz, held under 0.45 FS), a soft hit darker: x 2^((vm - 1) / 2) | the 808's high band |
| 1 D | NOIS | a balance (stage 5): metal / noise (Metal/Noise), both x 0.748 (the old start's metal share) | metal .. noise (909-like at the right) |
| 1 E | COLR | to 0.7 (knob 89): the ratios bent r^(0.6 .. 1.4) (the 808's set at 0.35, knob 44); above: the ring-modulated pairs (sq1 sq2, sq3 sq4, sq5 sq6) fade in | 808 .. inharmonic .. dense, cymbal-like |
| 1 F | SNAP | 0 .. 2 x (0.5 + 0.5 vm), falling in 2 ms: the VCA x (1 + strike) | the strike |
| 1 G | DRIV | soft clip at gain 1 + 20 DRIV^2 on the band x 2, its level held (KICK's comp), before the high-pass | the swing VCA's bite |
| 1 H | TYPE | | |
| 2 A | HPF | the high-pass (stmlib SVF, Q 0.75) at the band x 0.4 .. 1.4, exponential | thin at the top |
| 2 B | Q | the band's Q 0.8 .. 8, exponential | its resonance |
| 2 C | LOWB | 0 .. 2 x the 808's low band (3.44 kHz x the TONE ratio, Q 1.5: a band-pass of the metal and noise), added after the high-pass | the acoustic "chick" |
| 2 D | VEL | 0 .. 1: vm = 1 + VEL (vel - 1) | how much a soft hit loses (strike, brightness; stage 3: the knee's start) |
| 2 E | TOP | stage 3: 0 .. 1: a first-difference pre-emphasis x 1.5 TOP and the band toward its high-pass | the top octave (the 808's 17.8 kHz at 42) |
| 2 F | DRFT | stage 3: 0 .. 2 x the 808's: a jitter draw a square a half (+-0.52 % a cycle's worth at 64), a leaky drift walk every 256 samples | living metal; 0 static |

Stage 1b's Hat2 / OpenHat2 (scratch/drum-engine/drum_v2.py) with the User's 2026-11-20 choices: **plain squares** (no
anti-aliasing) at the 808's 47.98 % duty, stmlib's SVF (Plaits') in place of the TPT one, the hits' phases at stage 1b's
0.13 i turns. The squares' phases are 32-bit integers (a turn = 2^32, offset half a turn: they wrap by themselves, and a
square is one signed compare and one conditional subtract of the sign bit from +1.0's word); their increments are held
under 0.45 of FS (a note far up); the reference counts the same edges because it computes the increments with PERC's
exp2 polynomial (ref.exp2p, a copy test/test_drum.py holds equal). Every part runs every sample (the ring, the low band:
a level of 0 when off): one cost. **No DC blocker**: the band-pass, the high-pass and the low band pass no DC; a hat hit
zeroes the shared one (S_DC2) so a KICK or SNARE after it starts clean. The 1 ms declick on a retrig, across types too.
The starts (drum.PLACES, asserted equal to ref.Hat's): stage 1b's (v1's 808: TUNE 64 DCAY 58 / 55 (OPEN) TONE 64 NOIS 32
COLR 44 SNAP 44 DRIV 32; HPF 64 Q 44 LOWB 0 VEL 64).

**The choke** (the User): a CLOSED hit writes PERC's block clock (`perc.program.CLOCK_OFF`, one added at PERC's entry
every block) into its track's choke word; an OPEN hit keeps the word (S_SEEN), its address and the clock (S_HIT); every
half an OPEN voice looks, and when the word has moved, or it was the OPEN's own block at its hit (a CLOSED hit earlier in
that block) and that block is over, its envelope's coefficient becomes the choke's (a 3 ms time constant: -8.7 dB at 3 ms, -20 dB at 7 ms, -60 dB at 21 ms; stage 1b's). The words: 16, one a
track, at the Monomachine L2 scratch + 0x33C0 (`perc.program.CHOKE_OFF`, 0x200A73C0..0x200A7400, between ANALOG 2's mix
tables and VEL_OFF; in `dsp.py`'s area checks and docs/memory-map.md), zeros at load; the slot's track from the stock's
slot map (ROUTE 0x257898, the frame's 0xa5a + 2 s), masked to 0..15. PERC renders the newest voice first, so a CLOSED
hit chokes its track's older OPEN voices in its own trig block. On one voice a CLOSED trig on an OPEN hit simply takes
the voice (the declick). **A CLOSED and an OPEN hit on one track in the same block** (the User, 2026-11-20: the OPEN is
ALWAYS choked, whatever the slots' render order; until then the lower slot rendered first, keys being age x 16 + slot,
and an OPEN on the higher slot was never choked): from the next block in both orders, the two the same to the bit (an
OPEN rendered first sees the word move in the next block; rendered second, it saw the word at its own block and waits
for the block to end). `ref.choke_block` holds the rule; every other case is as before, bit for bit (the two-slot
choke's numbers unchanged). Cost: OPEN's look each half +4 instructions when the word has not moved; PERC's entry +5 a
block (the clock); the hats' code +68 B.

**Level, no corner over 1.0.** Stage 1b's stacking (the strike x the low band x the band's resonance into the clip x
the high-pass's overshoot) reached 6.3 here at gain 1. The level is held: the hit's gain x 1 / ((1 + SNAP)
(1 + 1.5 LOWB) (1 + 0.5 ring)) (on the clip's level and LOWB's), and the clip's level (comp) at g x max(Q / Q0, 1) (Q0:
the start's 1.78, so Q above it drives the clip as DRIV does); the type's level 0.72 (ref.HAT_GAIN, both types); then
the output held under 0.99 (two operations a sample) for the noise's rare peaks beyond that: 15,000 random hits (knobs at
their ends or anywhere, notes 0..127, velocities, the noise anywhere in its sequence) touched it 7 times (0.05 %); without
it 400 random hits and 192 stacking corners peak at 0.857 (test_hat_reference_corners_under_one). The machine's
-3.0 dB as the others'. The starts, the voice's first 300 ms (dnfw.perc.live, the level included): CLHH RMS -33.0 dB
(peak -6.7) against TRX-CH's -29.6 (peak -12.2), OPHH -25.3 (peak -6.1) against TRX-OH's -24.8 (peak -11.9); EFM-HH
-19.4 (peak +2.9). The hold costs the dense settings level: against stage 1b, first 250 ms RMS -2.5 .. -5.4 dB at the
plain points, -10.1 .. -11.5 dB at ACOUSTIC-LIKE / WASHY (`scratch/drum-engine/wav/fw_hats_vs_stage1b.wav`).

**The model against the reference** (test/test_drum.py): -111.9 (the worst corners) .. -123.4 dB under the peak, at
CLOSED's start, a tick, thin, 909-like, acoustic-like (ring, low band), the worst; OPEN's start, washy, the worst; the
two-slot choke (OPEN -122.1, CLOSED -123.0 dB) and an OPEN cut by a CLOSED on one voice (-126.1 dB).

**Cost** (dsp_cost.py, the model): the hats are branch-free (one cost at every setting): CLHH steady 8,707 (engine
6,586), trig block 10,164; OPHH 8,727 / 10,180 (the choke's look each half: +20). The runner (sharc_cost.py, its host
~1,000 above the unit's): CLHH 9,737 steady (engine 6,619), trig 11,194; OPHH 9,757 / 11,210: the hats ~8,700 a
voice-block steady on the unit, under the 13,100 16 voices with room need. With the hats (the shared code below) KICK
is 8,889 / 12,090 (dearest) steady, trig 13,124 on the model (runner 9,887 / 13,088, trig 14,122), SNARE 10,667 steady,
trig 11,854 (runner 11,665 / 12,865: its loops, +44). `MNM_COST` stays 28,000 (KICK's dearest trig 13,124 + ~14,700).

**Room: the DSP upload is full.** With the hats as first written the DSP upload (section 7 unpacked) came to 1,051,308 B
against the uploader's 1,048,575 (`dnfw.codec.lzma7`, docs/dsp-room.md): the build refused (build.sh still said
BUILD_END 0: its `mods apply` prints the refusal and writes nothing). Bit-exact cuts in DRUM's own code made it fit: one
exp2 for every hit (`dmath.exp2`, a leaf: ~21 inline copies were ~170 B each), the hits' velocity and TUNE in one copy
each (`kick.vm`, `kick.tune_oct`), SNARE's four modes and their decays in loops, every Svf of SNARE and the hats set in
one loop (`snare.svf_sets`), the drive's level without a branch, the hats' metal weights set at the hit. Then: section 7
1,048,308 of 1,048,575 B (267 B left); perc 175,086 B (+506 over SNARE's build). **Room found, bit-exact (2026-11-20,
docs/dsp-room.md "DRUM's room")**: the R12 loads nothing reads folded by the control flow (`dnfw.perc.flow`: 903 sites,
-3,654 B in PERC and the other DSL objects) and PERC's DDR exp2 no longer loaded (-2,068 B): section 7 **1,042,682 B,
5,893 B left**; perc 172,192 B (7,520 B left of PERC_L2_SPAN's 179,712), perc2a 17,868 of 19,456, perc2b 5,964 of
6,144 B (180 B left, DRUM's one init unchanged). KICK, SNARE and the hats as first written cost 4,028, 3,806 and 3,506 B
of perc: TOM fits.

## The gate

- `test/test_drum.py` (in the unit step): the registry, each type's model against the reference, random corners
  finite and bounded (SNARE's and the hats' under 1.0; the hats' reference without its output hold too), the
  reference's sine and exp2 copies equal to PERC's, the hats' choke (two slots, one track, against the reference; a
  control on two tracks), the same-block choke (both hits in one block, the OPEN on slot 0 or slot 1: the two orders
  the same to the bit, choked from the next block against the reference, a control on two tracks) and a CLOSED trig on
  an OPEN hit on one voice.
- `sharc:drum` (scripts/sharc_drum_step.py, the SHARC runner): KICK at its start, a tick, an 808, a techno chirp, a
  held driven body, the worst corner, two random corners; SNARE at its start, an 808, loose, the trap clap-snare, a
  rim, the worst corner, two random corners; CLOSED at its start, a tick, a 909, an acoustic one (ring, low band), the
  worst, a random corner; OPEN at its start, washy, the worst, a random corner; a retrig, a KICK cut by a SNARE, an
  OPEN cut by a CLOSED and back (one voice), a soft hit of KICK, SNARE and CLOSED; the choke: slot 0 OPEN, slot 1
  CLOSED on one track (the frame's slot map), and the control on two tracks; the same-block choke (2026-11-20: both
  hits in block 2, the OPEN on slot 0 and on slot 1, each with a two-track control); every run bit-exact to the model,
  sounding, finite and under 4.0; the retrigs the same until them; the soft hits quieter; slot 0's OPEN the same on
  either track until the CLOSED hit, then choked (RMS 10..20 blocks on under a tenth of the unchoked); the same-block
  OPEN the same in both orders and choked after the hits' block. Stage 3 (2026-11-20): KICK 909 re-voiced (SWHD) and 808
  BOOM; SNARE 808 (WCHR 127) and 909 (WCHR 0) re-voiced, the worst at WCHR 0; CLOSED 808 re-voiced (TOP), DRFT 0, the
  worst with TOP and DRFT; OPEN 808 re-voiced, OPEN long (DCAY 110: the exponential tail); TOM at its start, RNGE HI, the
  808 LO, the 909 MID, the conga, the worst, a random corner, a soft hit, a KICK cut by a TOM: 56 runs, 5,978 s on build
  821fff7e, every check PASS, every run bit-exact. Before: 39 runs, ~4,240 s on the farm (scripts/gate_times.json;
  2026-11-20 on build 8d92c3c0: every check PASS, every run bit-exact). 2026-11-20 with the hats: every run bit-exact (24 voice-blocks a
  run, 48 for the two-slot ones); the choked OPEN's RMS 10..20 blocks after the CLOSED hit 0.0148 against 0.160
  (-20.7 dB); instructions a block (the whole program): KICK 161,644, SNARE 163,209, CLHH 161,532, OPHH 161,543.
- `sharc:mnm-mb` runs DRUM at its start beside the next machine, bit-exact (step mnm's machine unit).

## A page per type: the table of hosts (2026-11-20)

The ColdFire reads DRUM's tables at the TYPE's place, as MONOMACHINE's at ENGN's: the mechanism is a table of hosts
(`dnfw.mnm.machines.HOSTS`; `wr_gen.h` `mnm_host_*`: each host's place, its SEL control J (page 1 H on both), its
places in its SEL's order, its thresholds on the SEL record's value). `mnm_live`, the names (`wr_extra_*`), the list
popup's load tag, the load check, fmt.c's quantiser and SEL-change detection, rec.c `mono_poll` (a SEL turned: that
place's start) and the overview all read it. Each type is a place (`drum.PLACES`: "DRUM KICK" .. "DRUM TOM") with its
own names, choices (TOM's RNGE: LOW MID HI), units (`dnfw.engines.units`) and start values; MACHINE SEL to DRUM
starts KICK. DRUM's thresholds give the type its DSP voice reads for every record value (asserted at generation,
`pages.host_dsp_choice`; test/test_drum_hosts.py). MONOMACHINE's tables are byte for byte as before (the same test's
GOLDEN). The gate's `mnmdefaults` step checks MACHINE SEL to DRUM (KICK's start) and TYPE turned to SNAR (SNARE's).

## Next: TOM

- On the DSP DRUM stays one voice, TYPE dispatched in `half` (each type a module beside kick.py), so the machine's
  cost is its dearest type's.
- **Room**: the DSP upload has 5,893 B left (above; 2026-11-20); perc's span 7,520 B; perc2b 180 B left (DRUM's one
  init, its loop over 72 words; no init a type).
- TOM: RANGE on page 2 (LOW / MID / HI detents), TUNE fine-tunes.

## Stage 3 (2026-11-20): TOM, the re-voicing, the TR-808's levels

The study's stage 3 (`scratch/drum-engine/drum_v3.py`, design.md 10 / 11, README "Stage 3") ported as it has it,
the reference first (`ref.py`), then the DSL. Against drum_v3 at the named points (`scratch/drum-engine/fw2_check.py`,
the WAVs `wav/fw2_<type>_vs_v3.wav`, the firmware's new type levels divided out): KICK and SNARE bit-identical at every
point (808 LONG, 808 BOOM, 909 and TECHNO re-voiced, TICK, HARD; RICH, 808 and 909 re-voiced, WCHR 0 / 127, the trap
clap-snare); the hats -93 .. -132 dB (the reference's float32 arithmetic for DRFT's draws) but OPEN past DCAY 80 (the
exponential tail, below: TRASHY -34 dB, WASHY -11 dB, on purpose); TOM -16 .. -29 dB: its DC out after the drive (5 Hz,
as KICK's and SNARE's: the study's TOM had none; without it -87 dB) and PERC's sine polynomial for the study's
256-point table (without both, -93 .. -109 dB).

**KICK.** The sigh follows the hit's level: f0 (1 - SIGH (1 - min(hl amp, 1))), hl = vm g^0.25 (g = DRIV's gain): at
DRIV 0 and full velocity as before; an accent or drive holds the pitch up longer, a soft hit glides less. SWHD (page 2
G): the sweep held 0..30 ms at its top. The clip sees g x vm, its level held at g's (a soft hit cleaner and about vm
quieter, never over a full one). The 909 point re-voiced: SWEP 21, SWTM 65, DCAY 82, HOLD 51 (40 ms), SWHD 68 (16 ms);
TECHNO: HOLD 44.

**SNARE.** WCHR on page 2 H, PERC's TYPE record (0..127), which PERC already read for every Monomachine machine with a
second page (`perc.program` fx_params: q7, MONOMACHINE's TUNE there): read back as its knob k = trunc(q 127 + 0.5),
d = max(64 - k, 0) / 64, w = max(k - 64, 0) / 63; the band's share 1 - w, the high-pass's 0.3 - 0.3 d + 0.7 w; the
wires held trunc(d 24 ms) samples after they start, then their decay through max(e - 2e-4 d, floor) / (1 - 2e-4 d)
(floor -1e30 at d = 0: the wires bit for bit as before at 64). The clip at g x vm. Re-voiced: 808 (MODE 18 = x1.94,
TONE 40, DCAY 69, NOIS 38, SNAP 40, DRIV 5, WCHR 127, WTON 11, WIRE 75, no glide, buzz, sizzle), 909 (TUNE 75, DCAY
56, TONE 40, MODE 127, SNAP 45, NOIS 100, DRIV 10, WCHR 0, WTON 44, WIRE 94, GLID 48).

**HATS.** The swing VCA's diode knee: g = knee(e) / knee(4), knee 0 under 0.59, (e - 0.59)^2 / 2.4 over a 1.2 knee,
e - 1.19 above (branch-free: o = max(e - V, 0), k = min(o, W), k^2 / 2W + (o - k)); e starts at 4 (0.6 + 0.4 vm).
CLOSED: e falls with tau 0.43 x DCAY's T60 (the -40 dB point where DCAY put it): it holds, then stops. OPEN: e rises
in 6 ms, stays for 0.234 T60, then falls in a straight line over 0.546 T60. **The User's choice: an exponential tail at
long DCAY.** The crossover: up to DCAY 80 (T60 0.94 s) the line alone; from 80 the exponential's share xt rises
linearly to all of it at DCAY 100 (T60 1.75 s) and above. The exponential tail starts from the same rise and hold and
falls 60 dB in 0.649 T60 (the -40 dB point kept at 2/3 T60); the VCA is (1 - xt) the line's + xt the tail's. The
choke: both fall in 3 ms, out of the hold. The VCA before the high-pass (the 808's order: the high-pass rings out
after the gate); the low band x LOWB x the VCA. TOP (page 2 E): x + 1.5 TOP (x - x1) into the band, the band toward its
own high-pass by TOP. DRFT (page 2 F): each half a draw a square, the increment trunc(inc0 ((1 + drift) + jit r)), jit =
0.0052 dr / sqrt(16 a) (dr = DRFT x 127 / 64, a the square's frequency / FS: the phase noise of a +-0.52 % draw a
cycle), and every 16 halves the drift's walk (drift + 2.5e-4 dr r) x 0.98; its own generator (seeded 0x21 ^ 0x5A5A at
the machine's init) and the walk in words no other type touches (kept from hit to hit, as drum_v3's), so the noise's
sequence is as before; the reference does the same float32 arithmetic (its log2 and exp2 the DSP's), so the edges agree
to the bit (test/test_drum.py). DRFT's start is 64 (the 808's amount); TOP's 0. Re-voiced: CH 808 (DCAY 75, TOP 42), OH
808 (DCAY 66, TONE 56, TOP 10).

**TOM** (`tom.py`, `ref.Tom`). Page 1: TUNE DCAY SWEP TONE SNAP NOIS DRIV; page 2: SWTM MODE SHAP RNGE VEL.

| page | knob | range | what |
|---|---|---|---|
| 1 A | TUNE | -24 .. +24 whole semitones about 110 Hz, plus RNGE, plus the note | the pitch (start +4: 138.6 Hz) |
| 1 B | DCAY | 40 ms .. 3 s (to -60 dB), exponential | the body; the skin noise in 0.3 of it |
| 1 C | SWEP | 0 .. 3 x (square law: 3 SWEP^2) x (0.6 + 0.4 vm) | the pitch drop (the 808's +8.2 % at 21) |
| 1 D | TONE | 0.6 TONE, 0.4 TONE^2 | the two skin modes' levels |
| 1 E | SNAP | 0 .. 0.8 x vm, falling in 1 ms | the stick (the noise above its one-pole) |
| 1 F | NOIS | a balance (stage 5): body / skin noise (Body/Noise); the noise's 100 % = 0.6, a one-pole at 6 f0 | the skin noise against the body |
| 1 G | DRIV | soft clip at gain (1 + 20 DRIV^2) x vm, level held (KICK's) | |
| 1 H | TYPE | | |
| 2 A | SWTM | 5 .. 400 ms, exponential | the sweep's time (the 808's 45 ms at 64) |
| 2 B | MODE | 0 .. 0.25: toward the 909's partials 1.5 / 2.75 on their own 66 / 42 ms T60s; 0.25 .. 1: 1.41 / 3.0 .. 1.59 / 2.14 (synthetic .. membrane), each mode's T60 the body's / (1.3 ratio) | the skin |
| 2 C | SHAP | 0 .. 1: the sine .. the 909's rounded triangle (soft(2 tri) / soft(2)) | the body's wave, the fundamental the strongest |
| 2 D | RNGE | LOW MID HI (a choice, three detents: the page's quantiser, as JUNO's RNGE): -6.5 / 0 / +6.25 semitones | the 808's LT / MT / HT apart |
| 2 E | VEL | 0 .. 1 | how much a soft hit loses (sweep, stick, the clip) |

RNGE's choice: the DSP reads q3 back as its knob (trunc(q 127 + 0.5)) and takes (knob x 3) >> 7, the page's own
reading: test/test_drum_hosts.py holds the two equal for every value the record can hold. TOM's start is the study's
re-voiced 808 MID (TUNE 74, DCAY 69, SWEP 21, TONE 0, SNAP 10, NOIS 15, DRIV 0; SWTM 64, MODE 127, SHAP 0, RNGE MID, VEL
64). The study's 808 LO / HI (TUNE 56 / 90, DCAY 77 / 67), 909 LO / MID / HI (SWEP 25, SWTM 87, MODE 0, TONE 115, SHAP
127, SNAP 80, DRIV 30, NOIS 0) and the 808 CONGA (TUNE 108, SWEP 13, DCAY 54, NOIS 0) are all reachable.

**Levels** (the User): the TR-808's MIX-OUT balance from its Service Notes (`scratch/drum-engine/levels_v3.md`), peak
to peak of each type's 808 point against KICK's 808 LONG, measured on this reference: SNARE -4.9 dB (`SNARE_GAIN`
0.75 -> 0.4945), TOM -4.0 (the 808 LO / MID / HI's mean: `TOM_GAIN` 0.6327), CL.HH -7.9 (`HAT_GAIN` 0.72 -> 0.3857), OP.HH
-8.1 (0.72 -> 0.4619). KICK's level stays the machine's (`LEVEL_DB["DRUM"]`, -3.0 dB). CLAP -2.0, RIM -4.9, COWBELL
-6.6 for later.

**Cost** (dsp_cost.py, the model; a voice-block): KICK 9,119 steady at its start, 12,348 at its dearest (trig 13,475);
SNARE 11,051 at its start (12,287 trig), 10,955 at WCHR 0's dearest; CLHH 10,387 (trig 12,549), OPHH 10,395 (12,592):
the hats are branch-free (one cost at every setting; +1,680 for the knee, TOP, the tail and DRFT's draws); TOM 8,997
(trig 9,843) at every setting. All under 13,100. `MNM_COST` 28,200 (KICK's dearest trig + ~14,700). The runner
(sharc_cost.py on the build's tree, its host ~1,000 above the unit's): KICK 10,021 steady / 13,218 at its dearest (trig
14,308), SNARE 12,001 (trig 13,216), CLHH 11,385 (13,485), OPHH 11,379 (13,513), TOM 9,923 (10,744); TRX-BD 4,862,
PLAITS-BD 11,523 beside them.

**AMP** (2026-11-20, the User; docs/live-select.md "AMP ON/OFF on the drum machines"): on DRUM, H on stock's AMP page
is AMP ON/OFF, OFF by default: the voice bypasses stock's AMP envelope and VOL in the DSP (gain exactly 1.0: DRUM's own
decays are the hit, the 808 boom's 8 s and the open hat's 4 s included; a note-off cuts nothing), every TYPE alike. ON
is stock's AMP and VOL. (Replaces the first approach, the AMP records set open at a pick.) Note for the levels: OFF
also leaves out VOL, which the first approach kept (stock's default VOL 110 is (110/128)^2 = 0.74, -2.6 dB): a DRUM
track with AMP OFF plays 2.6 dB louder than the same sound did with the AMP open at VOL 110.

**Room** (the build, 2026-11-20): section 7 1,046,118 of 1,048,575 B unpacked (**2,457 B left**; stage 3 +3,436); perc
175,618 B (4,094 left of PERC_L2_SPAN), perc2a 17,868, perc2b 5,972 of 6,144 (172 left: DRUM's one init +8, the
jitter generator's seed).

## Presets (2026-11-20)

55 sounds for DRUM, made on build 821fff7e (v0.62.5-drum TEST): the bank of the study (`scratch/drum-engine/design.md`
section 7) re-voiced as its sections 10 / 11 and the stage-3 points above. Numbered in one series, KICK first:
files `DRM 01 CLICK.dn2pst` .. `DRM 55 TOM CONGA.dn2pst` (the User's Bank B folder; published in `presets/DRM/`, branch
claude/drm-presets). Stored names (<= 15 characters, the payload's and the manifest's the same): `DRM` and the point
for KICK, `DRM SD`, `DRM CH`, `DRM OH`, `DRM TOM` for the others. **Inserts are the project's, not the sound's**: a
preset that wants one names it, `+DS` DIST, `+FZ` FUZZ, `+FD` FOLD, `+TP` TAPE, and the list in
`scratch/drum-engine/README.md` gives its knobs (MIX 127).

| type | presets |
|---|---|
| KICK (01..12) | CLICK, TICK, 808 LONG, 808 BOOM, 909, TECHNO, SUB, ACOUSTIC, DUB, HARD, HARDSTYL+DS, GABBER +FZ |
| SNARE (13..22) | SD RIMCLICK, SD 808, SD 909, SD TIGHT, SD ACOUSTIC, SD LOOSE, SD RICH, SD TRAPCLAP, SD 909 +DS, SD LOFI +TP |
| CLOSED HAT (23..32) | CH TICK, CH THIN, CH 808, CH 909, CH ACOUSTIC, CH PEDAL, CH SHAKER, CH DARK, CH METAL, CH 808 +FZ |
| OPEN HAT (33..42) | OH 808, OH 909, OH ACOUSTIC, OH SHORT, OH DARK, OH BRIGHT, OH WASHY, OH RIDE-ISH, OH TRASHY, OH FOLD +FD |
| TOM (43..55) | TOM 808 LO / MID / HI and TOM 909 LO / MID / HI (RNGE's detents LOW 20, MID 64, HI 105), TOM LO / MID / HI +FZ (the 909 toms), TOM RACK, TOM FLOOR, TOM ELECTRO, TOM CONGA |

**How they are made** (`scratch/drum-engine/`: `presets_drm.py` the bank, `make_presets_drm.py`, `emu_drum_presets.py`
on the farm). The build on its own UI snapshot (the setup of the gate's first `drumamp` step): for each TYPE the track's sound put back to
a new project's, MACHINE SEL's commit to DRUM, TYPE turned through stock's setter (the firmware writes the type's start),
stock's SAVE. Each preset is its type's firmware-made record with only these changed: the record version (+4: 2, as
the DN2 and Transfer write files), the tags (+8), the name (+12..27) and the words of the type's own knobs (page 1
A..G, page 2's used records), each the record value whose shown knob is the one asked (`perc.live.knob_word`; every
knob in the bank is one its record holds: PERC's 0..120 and 0..100 records skip some, e.g. KICK's 909 DCAY 82 is
written as the 81 the page shows). TYPE and the AMP stay the firmware's: **the stored sound carries DRUM's open AMP**
(drum-amp's values: DEL 0, ATK 0, HOLD 127, DEC INF, SUS 127, REL INF, ADSR, RSET on), so it plays open wherever it
is loaded (loading never changes AMP).

**What is checked.** Every written file decoded back: the payload's CRC, the stored name = the payload's, machine 56,
record version 2, +Drive slot 0, TYPE read as its type on the page and on the DSP, every knob as intended, the AMP open,
the tags in the record = the manifest's, no other byte than those above differing from the firmware's record; names
checked free in the folder first, written with exclusive create. On the emulator: the 55 records loaded one after
another into one track through stock's LOAD (version 3, the in-RAM one) with the UI running: each DRUM, its TYPE and
every knob word the record's (a type change between loads does not start the type), the AMP open, and stock's SAVE
gives the record back byte for byte (55 of 55). `presets_sync.py` (privacy, ZIP, manifest, set): clean. Rendered
through `ref.py` (and the named insert's reference): `scratch/drum-engine/wav/presets_<type>.wav`. Not checked:
the unit itself (nobody has listened; the 2 -> 3 version upgrade on import is the unit's, as for every Bank B preset).

### The bank for stage 5 (2026-11-21, the User's OKs of 2026-11-20)

84 sounds (Bank B and `presets/DRM`), every name carrying its kind's code (BD SD CH OH TOM CP RD CR; `presets_sync.py`
refuses a DRM file or stored name without one) and its kind's stock tag (BD KICK, SD SNARE, CH / OH HI-HAT, TOM and CP
PERCUSSION: the DN2's list has no TOM or CLAP tag, RD / CR CYMBAL; `test_the_drm_presets_keep_their_types`):

| type | presets |
|---|---|
| KICK (01..12) | BD CLICK, BD TICK, BD 808 LONG, BD 808 BOOM, BD 909, BD TECHNO, BD SUB, BD ACOUSTIC, BD DUB, BD HARD, BD HSTYL+DS, BD GABB +FZ |
| SNARE, CLOSED, OPEN, TOM (13..55) | as above |
| CLAP (56..65) | CP 808, CP 909, CP TIGHT, CP SNAP, CP GROUP, CP ROOM, CP FLAM, CP TRAP, CP DARK, CP LOFI +TP |
| RIDE (66..74) | RD 808, RD PING, RD BELL, RD JAZZ, RD SIZZLE, RD WASH, RD BRIGHT, RD 909-ISH, RD TRASH |
| CRASH (75..84) | CR CRASH, CR SHORT, CR LONG, CR SPLASH, CR CHINA, CR DARK, CR BRIGHT, CR REVERSE, CR 909-ISH, CR GONG-ISH |

**Converted in place** (`scratch/drum-engine/convert5.py`): each file is its old record with only the balance knobs'
words changed, as the code's own starts were converted: KICK CLIK, SNARE and TOM NOIS, CLAP TAIL at 64 v / 127 (the left
half: the first part at 100 %, the second at its old level); RIDE and CRASH BELL at 127 - 63 v / 127; the hats' and the
cymbals' NOIS by their metal / noise ratio; KICK CURV 64 (the old records held 0 there, a straight line); the kicks'
names. 56..84 come from `presets/out4` (made on the stage-4 build, before the balance knobs), converted the same way.
The AMP words are the old ones (the AMP fully open); with AMP ON/OFF the sounds play OFF unless set ON.
**Checked:** every file decoded back (CRC, names, machine 56, TYPE, every knob, the tags; no other byte than those
words); all 84 loaded through stock's LOAD on the emulator (stage-4 build: the record handling is the same), each DRUM,
its TYPE and every knob word the record's, stock's SAVE byte for byte: 84 of 84; rendered old file on the stage-4
reference against the new file on this one (`convert5_check.py`): SNARE, TOM and CLAP the same sound to -41 dB or better
apart from KIT_TRIM's -3.1 dB; the hats and cymbals keep their metal / noise ratio (level within 1.6 dB of the trim);
the kicks differ by the click's redesign. Nobody has listened.

## Stage 4 (2026-11-20): CLAP, RIDE, CRASH

The study's stage 4 (`scratch/drum-engine/drum_v4.py`, design.md section 12, README "Stage 4") in the firmware, with the
User's choices: RIDE and CRASH two TYPE entries sharing ONE code (`cymbal.py`, as CLOSED and OPEN share `hats.py`), the
cymbal on the hats' metal as shared subroutines (`hats.metal`, `hats.drft`, `hats.colr`, `hats.inc_f2`; one hit for both,
`cymbal.metal_hit`), exponential envelopes as rendered, SWEL's body band gliding up (retuned every half), the levels as
rendered, CLAP's output held under 0.99. GRP's clapper, the bell and the rivets always run (a level of 0 when off): one
cost at every setting. `clap.py` (CLAP), `cymbal.py` (RIDE, CRASH); the references `ref.Clap`, `ref.Cymbal` (`Ride`,
`Crash`).

**TYPE's eight types** in eight equal spans, (knob x 8) >> 7, in the order KICK CLAP SNAR CRSH CLHH OPHH RIDE TOM: every
value a project or a preset made with five types holds reads as its type (on PERC's 0..100 TYPE record, MACHINE SEL's
and a TYPE change's start words 9, 30, 50, 70, 90 and stock's setter's own values 9, 30, 50, 70, 91 land in KICK's,
SNAR's, CLHH's, OPHH's and TOM's spans of eight); the new three take the spans no old choice lands in. The 55 DRM presets
(`presets/DRM`) read as their type (test/test_drum_hosts.py, both). A value no page wrote (a hand-set MIDI CC, say) between
the old choices can read as a neighbouring new type.

### CLAP's pages

| page | knob | range | what |
|---|---|---|---|
| 1 A | TUNE | +-24 whole semitones about 1 kHz, plus the note | the band (the 808 at -2: 891 Hz) |
| 1 B | DCAY | the tail's T60 50 ms .. 4 s (the floor's x 8.6, under 6 s), exponential | |
| 1 C | TONE | below 64 the bands' low-pass share (x 0.8 x 2), above it their high-pass share (x 0.2) | warm .. bright |
| 1 D | CNT | 1 .. 8 bursts (a choice: (knob x 8) >> 7) | the tail opens with the last |
| 1 E | SPRD | the bursts 3 .. 30 ms apart, exponential | 808 9.4, 909 12 |
| 1 F | TAIL | a balance (stage 5): bursts / tail (Burst/Tail); the tail's 100 % = 2 x the bursts | the tail against the bursts |
| 1 G | DRIV | soft clip at (1 + 20 DRIV^2) x vm, level held (KICK's) | |
| 2 A | SNAP | a burst's tau 15 .. 0.8 ms | the saw (808 4.5 ms) |
| 2 B | Q | 0.6 .. 8 (the tail's x 0.6, GRP's x 0.8) | the bands' Q, their levels held (sqrt(1000 / (q fc))) |
| 2 C | HUMN | the bursts' times +-35 % of SPRD, levels +-25 % (two draws a burst from the noise) | |
| 2 D | GRP | a second clapper's level: its own generator, band +4 st, bursts SPRD x 1.07 apart from 0.3 .. 0.7 SPRD | |
| 2 E | TLTN | the tail's band x 0.5 .. 2 | |
| 2 F | TATK | the tail's rise 0.3 .. 80 ms | the 808's 3 ms; a room's bloom |
| 2 G | RAMP | -0.6 .. +0.6 over the train | the 909's rising bursts |
| 2 H | VEL | 0 .. 1 (PERC's TYPE record, q7) | velocity into the clip and the band |

### RIDE's and CRASH's page (one; their starts apart)

| page | knob | range | what |
|---|---|---|---|
| 1 A | TUNE | +-24 whole semitones on the SET (the bell x clamp(tr, 1/4, 4)), plus the note | |
| 1 B | DCAY | the body's T60 0.15 .. 12 s; the bell's x 1.3 | |
| 1 C | TONE | the body band 7.15 kHz x 2^(3 (TONE - 0.5)), a soft hit darker | |
| 1 D | BELL | a balance (stage 5): bell / wash (Bell/Wash); the bell 4 g^1.5 x the pair 2.94 / 3.27 kHz (Q 75 / 32), weights 1.4 / 75, 1 / 32 | ping, bell |
| 1 E | COLR | the hats' (ratios bent to 0.7, ring pairs above) | |
| 1 F | HIT | the top's T60 20 ms .. 3 s (the metal's first difference under a 12 kHz one-pole, x 0.7) | the stick's wash |
| 1 G | DRIV | soft clip at (1 + 20 DRIV^2) x vm, level held | |
| 2 A | SET | 808 WIDE CLST LOW (a choice, four detents: (knob x 4) >> 7) | the six squares' tuning, each with its bell ratio (1, 0.82, 1.12, 0.62) |
| 2 B | SWEL | the body from SWEL x 2 octaves down, gliding up (tau 50 .. 400 ms, retuned every half), its level from 1 - SWEL in up to 120 ms | the crash's bloom |
| 2 C | ATK | 0 none; 5 ms .. 2 s: a 60 dB swell, all three bands held, then their decays | REVERSE |
| 2 D | SNAP | 0 .. 3 x (0.5 + 0.5 vm), tau 1.5 ms | the stick on the body and the top |
| 2 E | NOIS | a balance (stage 5): metal / noise (Metal/Noise), x the kind's start share (RIDE 0.906, CRASH 0.685); level held against the noise | |
| 2 F | DRFT | the hats' (64 the 808's jitter) | |
| 2 G | RIVT | 0 .. 0.3 RIVT^2: noise clicks (|noise| > 0.94) high-passed 2.5 kHz on the bell's envelope | rivets |
| 2 H | VEL | 0 .. 1 (q7) | the clip, the strike, the brightness |

Starts: CLAP the 808 point (TUNE 58 DCAY 48 TONE 52 CNT 56 SPRD 63 TAIL 79 DRIV 5; SNAP 52 Q 37 TLTN 64 TATK 52 RAMP
64); RIDE 808-ish (DCAY 76 TONE 64 BELL 48 COLR 44 HIT 90 DRIV 10; SET 808, SWEL 12, SNAP 50, NOIS 12, DRFT 64); CRASH
(DCAY 86 TONE 74 BELL 12 COLR 100 HIT 84 DRIV 16; SET WIDE, SWEL 72, SNAP 64, NOIS 40, DRFT 80).

**The references against drum_v4** (`ref.Clap`, `ref.Cymbal`: drum_v4's loops in float32, every value set with the
DSP's exp2, log2, reciprocal and e^x, so the burst times, the squares' edges and the long decays are the DSP's; drum_v4
ran its loops in float64 with the squares' increments from float64 powers): see "How far from drum_v4" below.

**The model against the reference** (test/test_drum.py, 90 blocks): CLAP -98.6 (every knob 127) .. -128.7 dB under the
peak at its start, 909, tight, one burst, big group, room, wide flam, trap, dark; RIDE -95.0 .. -125.3 dB (start, ping,
bell, dark jazz on LOW, sizzle with rivets, wash on WIDE, trash on CLUSTER, every knob 127), CRASH -98.1 .. -125.5 dB
(start, long, splash, china, reverse with ATK, gong on LOW, every knob 127); soft hits; random corners finite and under
1.0; SET's and CNT's DSP readings the page's choice for every record value.

**Levels** (the User, levels_v3.md's method: Vpp re KICK 808 LONG on the reference): CLAP's 808 point (its start) -2.00
dB (`ref.CLAP_GAIN` 1.1366), RIDE's and CRASH's starts -6.60 dB (`ref.CYM_GAIN` 1.6426 / 1.3697, on the held level
against the stick, the bell, the ring and the noise); test/test_drum.py holds them within 0.1 dB.

**Cost** (dsp_cost.py, the model, a voice-block): CLAP 8,163 steady at every setting (trig 9,921, 10,157 at its dearest);
RIDE and CRASH 11,325 steady at every setting (trig 13,752); with the shared metal the hats are 10,519 / 10,527 steady
(+132: the metal's call a sample), KICK 9,127 / 12,356 at its dearest, SNARE 11,047, TOM 8,993: all under 13,100.
`MNM_COST` DRUM 28,600 (the cymbals' trig 13,753 + ~14,700). The runner: below.

**Room.** CLAP and the cymbals as first written did not fit (perc 180,864 B against its 179,712 B span; section 7
~1,600 B over even after docs/dsp-room.md "CLAP and the cymbals' room"); cut, bit-exact for every other machine and type (the model before and
after: 260 cases, every output word): the hats' and the cymbal's hit one copy (`cymbal.metal_hit`), `kick._coef` and
`drive_level`'s law one subroutine each with exp_neg's and exp2's copies as their tails (`Prog.tail`), exp_neg's
power branch into exp2's copy, the host lookups (`md_pitch0/1`, `trx_hathost`), the Monomachine half loop two
instructions shorter, DRUM's subroutines in the host bodies' span. The build: section 7 1,048,266 of 1,048,575 B
(**309 B left**); perc 177,740 B (1,972 left of PERC_L2_SPAN), perc2a 18,640 (816 left), perc2b 4,254 (1,890 left).

## Stage 5 (2026-11-20): the balance knobs, the click, CURV, no digital clipping

**The balance knobs (the User).** One knob sets two parts: at its centre (knob 64, shown C) both at 100 %, left the
first part only, right the second only, linear (`ref.balance`: min(1, (1 - b) 127/63), min(1, b 127/64), b = knob /
127); shown -64 .. +63 (the readout kind `bal`). KICK CLIK (body+noise / click, in SNAP's place), SNARE NOIS (body /
wires; SNAP stays the stick), TOM NOIS (body / skin noise), CLAP TAIL (bursts / tail), RIDE and CRASH BELL (bell /
wash), the hats' NOIS and the cymbals' page-2 NOIS (metal / noise). Each second part's 100 % is its old maximum, so an
old value v reads the same at knob 64 v / 127 (the left half); BELL's old value maps to the right half (127 - 63 v /
127); the old metal/noise crossfades map by their ratio. The starts are converted: SNARE NOIS 38, TOM 8, CLAP TAIL 40,
the hats 22, RIDE BELL 103, CRASH 121, RIDE NOIS 7, CRASH NOIS 29.

**The click (why it "did nothing").** It was a ~1 ms DC-ish pulse added before the soft clip at the moment the body's
own sweep is loudest: SNAP 0 -> 127 moved the first 20 ms by at most 0.7 dB. Now the pulse click is high-passed at
300 Hz (x 2) and added after the drive; its 100 % is 0.4 of the body's peak (the most that keeps the worst case under
full scale, below).

**No digital clipping (the User).** No type's output reaches full scale at any knob setting, the drive at its cleanest
or at its top (the drive saturates by design, its level held; no clamp in KICK). Every type's level x KIT_TRIM (0.70,
-3.1 dB), so the kit's balance (the 808 MIX-OUT levels) holds; the cymbals' level after the soft clip at most 0.9
(CYM_COMP_MAX). Worst peaks (random survey, then hill-climbed over every knob and the note): KICK 0.874, SNARE 0.37,
CLHH 0.42, OPHH 0.61, TOM 0.44, CLAP 0.80, RIDE 0.90, CRASH 0.67 (CRASH and RIDE before the fix below). Measured on
the reference over random and corner settings (scratch/drum-engine/click/peaks.py, the hats', CLAP's and the cymbals'
output holds lifted): see the test `test_no_type_reaches_full_scale` for each type's worst setting and its peak.

**No setting reaches the soft clip's flat top at DRIV 0 (2026-11-21).** Two corners did (`scratch/drum-engine/click/
softin.py`, the clip's largest input, hill-climbed over every knob and the note; the curve is flat from 3): CLAP with
TAIL at 64 and up and a high Q (2.40 at Q 64, 2.72 at Q 96, 2.99 at Q 127: a narrow tail band's noise), and the
cymbals (RIDE 5.1, CRASH 3.9: their level held against the stick, the bell, the ring and the noise was applied after
the clip, so the clip saw the raw sum; and the top band, the metal's first difference, grows with the pitch). Now:
CLAP's tail level x 2^(-0.71 (Q - 0.5)) above Q's centre (0.78 at Q 127; Q 0 .. 64 unchanged), and its bands' level
hold sqrt(1000 / (q fc)) taken with fc at least 250 Hz and q at least 1.25 (the hill-climb found the clip's input at 11
at a low TUNE and a low note, and 4.0 at a low Q with TONE's low-pass share, which does not narrow with Q; the start's
891 Hz and q 1.276 untouched) and the low-pass share 0.6 (was 0.8: a TONE under 64 is up to 2.5 dB lower in its
low-pass part), CLAP_GAIN re-set (1.1676 x KIT_TRIM) so the start stays 2.0 dB under KICK 808 LONG: the worst input 2.54; RIDE and CRASH take their level held INTO the clip (x 1 / h with g x vm; the same level below
the knee) and held against the pitch above an octave up (x 2^(-0.3 (x - 1)), x = TUNE + the note in octaves; every
start at notes up to 72 unchanged), `CYM_COMP_MAX` gone, `CYM_GAIN` re-set so the starts stay 6.6 dB under KICK 808
LONG (RIDE 1.5420, CRASH 1.0901, x KIT_TRIM). The drive (DRIV) still saturates by design. Random survey of the output
after the fix: CLAP 0.80, RIDE 0.63, CRASH 0.41; the listed worst cases all under 0.95.
