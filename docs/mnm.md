# The Monomachine's synth machines on the DN2 (v0.26)

> **In this fork:** removed on 2026-11-08 (the User, to make room for PLAITS and the 303; their
> types 6, 7, 14, 15, 16 stayed reserved) and back on 2026-11-11 (the User: the LZMA-stored DSP
> section gave the USB image room), with the same types, levels and costs, after the machines
> already in MACHINE SEL in PERC's machine index (`dnfw.mnm.machines.ALL_MODULES`) and first in
> MACHINE SEL's list. Their tables (from the Monomachine OS, `MNM_OS`) come first in the
> Monomachine table run, PLAITS's after them (`dnfw.mnm.tables`). Each is a builder part
> (`MNM_SID`, `MNM_DPRO_WAVE`, `MNM_DPRO_DDRW`, `MNM_DPRO_DENS`, `MNM_VO6`), on by default.

Owner, 2026-10-25: *"i want to build the digipro, sid, and VO synth machines from the
elektron monomachine. you can erase the cz phase and resonator machines and just add these
alongside the dn2 synth machines as synth engines"* -- each its own entry in MACHINE SEL,
its page drawn as the Monomachine draws it (the owner's six screenshots from its manual).

## Where the algorithms come from

The owner's Monomachine SFX-6/60 OS 1.32B (Elektron's `Elektron_SFX6-60_OS1.32B.syx`; `MNM_OS`, default a local copy at `../mnm132/mnm_os1.32b.syx`,
sha256 `fe13c09f...a1710`). `../mnm132/research/` (outside the repository: Elektron's code)
records its layout: a ColdFire host (VMA 0x200000), two DSP56303s with a kernel each, and
an external image the kernels share (P/X/Y unified above 0x100000) holding every machine's
code and tables. `dnfw.mnm.rom` reads the tables from the owner's file at build time, as
`dnfw.md.rom` reads the Machinedrum's; nothing of Elektron's is in this repository.

The research tools there run each machine's own code in the DSP56300 emulator (from the
Machinedrum work, with DIV, CLB and NORMF added for the Monomachine's kernels) and record its
output (`golden/`, `MNM_GOLDEN`), and an integer model of each machine matches that output
bit for bit (`mnm_models.py`).

## How the Monomachine runs a voice (what the port keeps)

- **Blocks of 16 frames at 44.1 kHz** (2,756.25 a second). Each machine renders its
  oscillator at 4x (DPRO: 64 samples a block) or 12x (SID: 192), then a polyphase IIR
  decimator (five words of state, ten coefficients) brings it to 16.
- **The voice block**: 52 words from the host each update. The eight parameters are the
  knob positions (0..127) << 16 -- enumerated ones too: the DSP compares them with its own
  thresholds. Each machine has three entries: init (the machine was chosen), trig (a note),
  render (every block).
- **Pitch**: a word F, 2048 to the octave, 0..0x5800 (11 octaves); F = note x 2048 / 12 +
  floor(TUNE x 683 / 128), so TUNE spans -2..+2 semitones around 64; 440 Hz at F = 0x2F55
  (note 69, TUNE 64). The kernel turns F into the render's increment A through its 2048-word
  exponential table.

## The machines

| machine | id | parameters | what |
|---|---|---|---|
| DPRO-WAVE | 6 | WAVE WP WPM WPRS SYNC SFRQ --- TUNE | one of 32 single-cycle waves (512 x 12-bit), linear interpolation at 4x through a 512..1023-sample window that WP (swept by WPM) slides into the next wave; hard sync per block to SFRQ or the previous track's pitch |
| SID 6581 | 3 | PW PWAD PWRS WAVE MOD MSRC MFRQ TUNE | two 24-bit phase accumulators at 12x; TRI, SAW, PULS (swept), MIX (the chip's combined waves, a 4096-entry table), NOIS (two linked shift registers, sampled at the phase's wrap); RING, SYNC, R+S |
| VO-6 | 11 | VOC1 VOC2 V-SW VOIC CONS CLEN CVOL TUNE | a band-limited pulse train (32-tap pulses, the kernel's table) and noise (VOIC mixes them) through four formant resonators in series (F1, F2 from VOC1, VOC2; F3, F4 fixed), the same four in parallel on the unvoiced source; an AGC, three internal envelopes (onset, the consonant's transition, the vowel gate), 21 consonants (CONS: their set-ups and renderers, CLEN, CVOL), a fixed output biquad. No oversampling |
| DPRO-DDRW | 32 | WAV1 MIX WAV2 TIME BR1 WID BR2 TUNE | two Digibank waves at 2x, each at its own pitch (WID detunes them up to -/+53 cents, scaled by 1 - abs(2 MIX - 1)), crossfading from the previous wave on a change (TIME), bit-reduced (BR1/BR2: 15 bits at 0 down to 3 at 127), each read at two mip levels crossfaded over the octave's top 1/16; MIX ramped over the block; the kernel's 2:1 allpass decimator |
| DPRO-DENS | 33 | PCH2 PCH3 PCH4 WAVE --- CHRL CHRW TUNE | four oscillators on one Digibank wave at 2x, three at PCH2..4's ratios (-12..+12 semitones and 2/3 3/4 4/5 5/6 6/5 5/4 4/3 3/2; the middle, 1.0, is OFF), band-limited by mip level with a crossfade over each octave's top 1/16 toward a partner sample held in the finer level's low bytes; mixed at 0.633 each (silent at 20 kHz and up, or at the first one's Hz); the 2:1 decimator. CHRL/CHRW are the Monomachine's chorus after the machine (not here) |

**DPRO-BBOX** (24 drum samples, 63,049 words: about 189 KB) does not fit the firmware: the
whole image has about 50 KB to spare under the 2 MiB the USB upgrade takes. **DDRW and DENS** read
the Monomachine's user Digibank (64 waves in its own flash, 2048 words a wave: nine mip
levels, 1024 >> L samples, each word a 16-bit sample << 8 with a crossfade partner's byte),
which is not in the OS file. Here the DSP builds a stand-in once the tables are filled
(`dnfw.mnm.dpro.build`, 8 outputs a block, about 8 s; DENS and DDRW are silent until it is
done): the 32 ROM DigiPRO waves through a 7-tap halfband chain (level 0 the ROM wave
upsampled, each level the last one's halfband, its even samples the next level and all of
them that level's partner), 256 KB of DDR (`core.DIGI_OFF`); wave n reads stack n & 31.
The golden runs load the same words (`dpro.digibank_reference`, the build run in run mode).

## On the DN2

**One machine, MONOMACHINE (2026-11-11).** The User: *"i think one mono machine makes sense. and we
should have uniformity about where we put the sub engine knob. so that it is logical and aligned with
machinedrum"*. The five are the engines of one machine, MONOMACHINE, on type 6 (MACHINE SEL: MONOMACHINE,
its keyboard icon; Monomachine / MNM):

| control | where | what |
|---|---|---|
| ENGN | page 1 H (PERC's eighth record, PD1 0..100) | the engine: SID, WAVE, DDRW, DENS, VO-6, the list popup with a tag beside each (SID CHIP, 32 WAVES, 2 DIGIBANK, 4-OSC CHORD, VOICE), as MACHINEDRUM's TYPE |
| the engine's first seven | page 1 A..G (the records they always had) | as the table above |
| the engine's TUNE | page 2 H (PERC's TYPE record, 0..127: every knob, where PD1 held 101) | as before |

| former machine | its type until 2026-11-11 | now |
|---|---|---|
| SID 6581 | 6 | MONOMACHINE's first engine (type 6) |
| DPRO-WAVE, DPRO-DDRW, DPRO-DENS, VO-6 | 7, 14, 15, 16 | engines 2..5; the types reserved (`RETIRED`), never reused |

- **The pages follow ENGN**, as MACHINEDRUM's follow TYPE: the ColdFire's Monomachine tables have a place
  for each engine (`dnfw.mnm.machines.CF_MONO_PLACES`: the type's own place is SID's, the others after the
  types' places); `mnm_live` (generated, `dnfw.waverider.pages`) picks the place from ENGN's word for the
  page, its list popups, the value readouts (`fmt.c`), FUNC + turn and the record names (`page.c`
  wr_names: one set of names an engine).
- **Changing the engine starts it as choosing it in MACHINE SEL did**: ENGN turned (the setter's
  `smp_quant`) to another engine marks the track; the UI's poll (`rec.c` mono_poll) writes that engine's
  start (`mnm_default`) to its other controls, ENGN as turned. MACHINE SEL to MONOMACHINE starts SID.
- **On the DSP each engine is still its own PERC voice** (its index in PERC's machine index, its level
  `MNM_LEVELS` and cost `MNM_COST`): PERC reads ENGN from the frame (`dnfw.perc.program.mono_engine`, the
  choice the page shows) and adds it to the type's voice, as PERC's TYPE picks a Machinedrum machine; the
  engine's eighth input (TUNE) is read from page 2 H. A new engine plays from the next note (its init), as a
  new TYPE does. Each engine's output is bit-identical to its separate machine's for the same controls
  (perc.live's model, every engine at its start and at random knobs, notes and trigs).

(`dnfw.mnm.machines.TYPES`: a type per voice, MONOMACHINE's five all 6; 6 and 7 were CZ's and RESONATOR's,
14.. follow the sample machines. The ColdFire's type range, names, MACHINE SEL list and group, its pages'
kinds (is_wr: the type - 4) and the DSP's type lookup follow that one table.)

- **The DSP budget.** A Monomachine voice never goes quiet (as on the Monomachine: it plays
  until the next note; the DN2's amp envelope shapes what is heard), and one costs as much
  as two to ten Machinedrum voices: the model's worst case a DN2 block is about 55,000
  instructions (SID), 31,000 (WAVE), 70,000 (DDRW), 63,000 (DENS), 64,000 (VO-6). So each
  block PERC renders them in track order while their cost (`perc.program.MNM_COST`: SID
  60,000, WAVE 34,000, DDRW 78,000, DENS 70,000, VO-6 75,000) fits `MNM_BUDGET` (150,000);
  a track past it is silent that block. Two SIDs, four DPRO Waves, or one DDRW and one
  DENS, at once. The SHARC has about 250,000 cycles a frame free beside the stock engines
  (`docs/sharc-load.md`); the budget is to be raised or lowered from a reading on the
  instrument (`tools/dn2sharc_load.py`).
- **DPRO-WAVE is played an octave up** (`machines.TRANSPOSE`): on the Monomachine, for the
  same pitch, it sounds an octave under SID, DDRW, DENS and VO-6 (their golden runs). So
  each machine's note 60 is 261.6 Hz, as the DN2's own machines' (test_perc_live).
- **Its AMP level** (y:(r6+175), the kernel's amp envelope, which gates the voiced path):
  that of an AMP attack of 0 (0 at the trig, then + 0x400000 a block to full), so its
  pre-delay is 0.
- **The knobs start where WaveTone's records are** when the machine is chosen (as PERC's
  do): the Monomachine's own defaults are not loaded (see FIRMWARE.md).

- **In PERC's voice** (`dnfw.md.voice`): a slot's words, the 44.1 kHz stream and its
  resampler to 48 kHz are the Machinedrum machines'; a Monomachine machine's render is two
  of its blocks (32 samples). The machine type picks the machine (not PERC's TYPE).
- **The DSL** (`dnfw.perc.dsl`, one program for the SHARC code and its model): `dnfw.mnm`
  (`wave.py`, `sid.py`, `dec.py` the shared decimator, a leaf subroutine). The 56300's
  48-bit phases are 32-bit integers here (DPRO: 21 fraction bits), its MACR rounding and
  the limiter's test a clamp.
- **The increments**: on the DSP each machine's `pitch` computes them in float from the
  DN2's pitch; `dnfw.mnm.exact` computes them in the Monomachine's integer arithmetic.

## ANALOG 2's page 3: the glide (2026-11-11)

The User asked for DRONE's mono legato glide on ANALOG 2. Pages 1 and 2 use 16 of WaveTone's 25 saved records, so
page 3 sits on records none of our machines used (`dnfw.perc.machines.P3_RECS`). They keep their stock ranges, so
p-locks, LFO destinations and SAVE/LOAD work as for any record.

| control | record (slot) | range | what |
|---|---|---|---|
| GLID | LEV2 245 (36) | 0..127 | 1 ms .. 1 s as Optimist's TIME_MS index, then up to 5 minutes; 0 OFF (DRONE's) |
| GLTY | TYPE 259 (46) | 0..2 | OFF, RATE (GLID is an octave's time), TIME (GLID is any glide's time) |

- **Old projects play as before.** GLTY OFF is TYPE's stock default (0). No free record with a 0..127 range
  defaults to 0 (LEV2 0x6400, DEC 0x7f00, MAST and FINE 0x4000, measured in the 1.11 and 1.12 tables), so the
  OFF has to be GLTY's. A track whose TYPE word was set by something else before reads RATE or TIME.
- **MACHINE SEL** starts it at GLTY OFF, GLID 54 (Optimist's SLIDE_T, ~50 ms).
- **Legato, as DRONE's** (`dnfw.mnm.a2glide`): a note glides only when its trig comes while the slot's gate is
  still open (no note-off since the last note); a separate note jumps. Only the oscillators glide; KTR keys the
  filter from the note itself, as Optimist's ANALOG 2 does. A note that glides does not restart the phases at
  DRFT 0 (Optimist's LEGATO plays it on the sounding voice).
- **Up to 5 minutes** (the User, 2026-11-11: "drone glide should go to minutes"; DRONE's GLID too):
  `a2glide.ms_of`: the lower three quarters of the knob are Optimist's 10^(4 q) ms (1 ms .. 1 s), the top quarter
  climbs from 1 s to 5 min (~20 % a step). The readout is exact a knob (`units.glid_table`: "40ms", "1.5s", "12s",
  "2.5m"). voice.c's whole-unit step (1/4096 semitone a block, at least one) is not kept: it capped a glide at ~3 s
  a semitone; the step is a float now, so every glide takes its time.
- The DSP reads page 3 only for a machine that has one (`dnfw.perc.program`, words `r0`, `r1`).

## The tables, over the fast link

The DSP image had about 50 KB to spare, so the tables no longer ride in it. The ColdFire
carries them (a CODE chunk at `TABLE_LOAD`, 0x47000000: magic, length, data) and sends them
first over the sample link at power-on (`csrc/sampler/link.c`, K_TABLES), to the pool's
table area (`dnfw.sampler.machines.TABLE_AREA`, 512 KB below the slice area); K_READY then
writes `TABLE_MAGIC` at `TABLE_READY`. The DSP's `table_fill` (`dnfw.md.core`) waits for
that word, then decodes zpack 2,048 words a block, as before. PERC's voices, the Machinedrum
machines' too, stay silent until the fill is whole (about 40 blocks).

What ships: the Machinedrum's host pitch table and zpack, which now also carries the
Monomachine's tables after the sine (`TABLE_LAYOUT["mnm"]`, starting a block). They are
stored compactly, and the fill restores them exactly:
- DPRO-WAVE's ROM words as (hi, lo) pairs (lo = the low 12 bits, signed; hi = the rest),
  which `_mnm_fix` turns back into (hi x 4096 + lo, lo x 4096): the word and its low sample
  << 12, exact in float (`dnfw.mnm.rom.packed_words`);
- SID's combined waveforms (8 bits << 16) as the 8 bits; `sid.py` scales them back.

The shipped tables came to 65 KB (94 KB with the words as they are).

## Checks

`test/test_mnm.py`: every golden case of every machine in run mode, with the increments
exactly the Monomachine's, at 60 dB signal-to-error or better (DPRO-WAVE 63.8..99 dB, SID
94..110 dB so far); each machine's float `pitch` within 1e-4 of the exact increments.

## JUNO (2026-11-12): the Juno-106 voice, machine type 23

Optimist's JUNO engine (fm-106 / KR-106, GPL-3.0-only: THIRD-PARTY.md) as a Monomachine-style machine on PERC's
voice, `dnfw.mnm.juno`; a voice a note, as many as the DSP budget (`perc.program.MNM_COST`) lets start.

- **Page 1:** WAVE (OFF SAW PULS BOTH: the Juno's two buttons), PW (50..95 %), SUB, NOIS | CUT, RES, KEY (key
  tracking around C4), HPF (BOOST FLAT 236 754 Hz).
- **Page 2:** ENV (the VCF envelope's depth, -127..+127 about knob 64: negative inverts it), ATK (1.5 ms .. 3 s),
  DEC, SUS, REL (1.5 ms .. 12 s), PWM (MAN; ENV: the width follows the envelope), RNGE (16' 8' 4'). The envelope
  drives the VCF only; the DN2's AMP page shapes the level, its LFOs move the knobs (PW, CUT: the Juno's LFO).
- **The ladder** is ANALOG 2's OTA core (`dnfw.a2f.models.ladder_core`, one subroutine for both machines, PERC's
  room) on the Juno's own coefficients once every 16 samples: the cutoff DAC routine (CUT, ENV, KEY), its RC slew,
  KR-106's measured cutoff curve pulled to the resonance's peak, the resonance's k. The core's Pade saturation
  stands for fm-106's BA662 table: a drive by RES and a makeup gain fitted on the host against Optimist's voice
  (scratch/juno-engine/cmp). Measured there, sustained, cutoffs 30..100: harmonics within 0.2 dB up to RES 110,
  0.7 dB at RES 120; RES 127's self-oscillation within ~2 dB (a few harmonics up to 6 dB). End to end (this
  program in the model against Optimist's voice with its HPF): levels within 0.5 dB, harmonics within ~2 dB
  (0.6..0.9 rms) over saw, pulse, sub, BOOST and the cuts; at RES 120 the self-oscillating tone ~4 dB weaker.
- **Its tables** (KR-106's cutoff curve, 1,025 points; by RES its k, peak pull, the drive; the sub's and noise's
  levels: 1,793 words) follow PLAITS's in the Monomachine tables (`mnm.tables.juno_values`, `Layout.JU`), read
  once a block or once every 16 samples.
- **Cost** (the model, steady, one voice): ~6,000 instructions a block (a saw), ~8,100 with pulse, sub and noise;
  PERC code +2,988 B (+720 instructions, ANALOG 2's ladder moved into the shared subroutine with it). ANALOG 2 is
  bit-identical (test_juno pins it) and ~1 % slower on its ladders (the shared loop tests the model a second time
  a sample).
- **Known:** BOOST with every source at full (BOTH, SUB, NOIS) reaches the voice stream's +-8 bound; every other
  setting the runner and test_juno try stays under 4.0.
