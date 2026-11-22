# SOPHIE: Sophie's percussion on the DN2 (fork, not released)

A sixth Monomachine-style machine, **Sophie / SOP** in MACHINE SEL (machine type 53 since 2026-11-18; 20 v0.45..v0.58.x, now upstream's FM+ DYN; 17 until v0.45, which gave 17 to upstream's BOUNCE: docs/machine-types.md), after
VO-6. A port of Matt Estela's **Schwung Sophie** (github.com/mestela/schwung-sophie,
`src/dsp/sophie.c`, MIT; THIRD-PARTY.md), the synth Overtone (complex-ping) also carries as its
SOPHIE machine on OS 1.12. Overtone publishes no source for it (its patcher ships byte diffs),
so this port is from Sophie's C; Overtone's README gave the design it shares: the knob names,
the seven models with KICK, no filter of its own (the track's filter does that).

`src/dnfw/engines/sophie/sophie.py`, in the DSL (`dnfw.perc.dsl`): one program for the SHARC code and
its run-mode model, in PERC's voice like the Monomachine machines (`docs/mnm.md`).

## The page

| knob | what | range |
|---|---|---|
| DCAY | Sophie's own amplitude decay (inside the DN2's amp envelope) | 0.03..4 s, exponential |
| COLR | the modulator ratios (deliberately non-integer: the clang zones) | 0..100 % |
| METL | FM depth into the carrier, m1 into m2, the noise | 0..100 % |
| FBK | operator feedback into m1 (Raw) | 0..100 % |
| SWEP | the pitch sweep's depth (on the 28 ms pitch envelope; KICK 75 ms) | -100..+100 % (64: none) |
| CRSH | sample hold (1 + crush² x 31) and 15 - 12 crush bits; off below 0.5 % | 0..100 % |
| MODL | FUSE, STAK, SPLT, SHRD, PIPE, BOOM, KICK | 7 choices |
| TUNE | semitones on the note | -24..+24 (64: in tune) |

KICK is Sophie's pad-1 topology (a tuned sine body, its fold, a quiet FM texture and a click)
with model 0. MACHINE SEL starts it at Sophie's factory snare (pad 3): DCAY 61, COLR 66, METL
97, FBK 23, SWEP 82, CRSH 38, FUSE.

On SOPHIE, H on the AMP page is AMP ON/OFF, OFF by default: the AMP envelope and VOL bypassed (gain 1.0, no release:
DCAY is the hit's length); ON is stock's AMP (2026-11-20, docs/live-select.md "AMP ON/OFF on the drum machines").

## What is left out (against Sophie)

Its per-pad filter, drive, ring delay and level (the DN2's track has filter and overdrive), its
second page (metal decay: the original 135 ms contour; feedback mode: Raw; tail mode: Hit, with
the knobs read every 16 samples instead of latched), velocity, the 1.5 ms steal crossfade.
Sophie's drive stage at 0 remains as the output soft clip, halved: `x / (1 + |x|)`.

## Numbers

44.1 kHz in PERC's stream, as Sophie (no oversampling, no decimator): two 16-sample halves a
DN2 block. Phases in turns; sines from PERC's sine table (256 a turn, linear), exp2 from PERC's
table, divisions by PERC's reciprocal. The amplitude envelope's rate, `e^y` with y tiny, is a
cubic in y (the exp2 table's linear steps would be 2 % off in the decay time).

Cost: at most 7,200 instructions a render half (KICK); the whole voice, its trig block
included, at most 29,979 a DN2 block (`test_perc_live`), so `MNM_COST` 34,000 (SID 60,000). PERC's code grew 4,518 bytes to 143,450, so its L2 span grew 2 KB to 0x23800 and the
sample machines' code moved up 2 KB (SMP_SW 0xbf1c00); still 0x200E9800 at the end, 64 KB
under the non-cacheable window (`test_waverider_dsp`).

## Checks (this fork)

Against `sophie_dn2_ref.c` (Sophie's `render_voice` cut the same way, outside the repo), seven
cases, one per model, 8,320 samples each:

| model | waveform SNR | loudness, worst 1024-sample window | spectral centroid ratio |
|---|---|---|---|
| FUSE | (chaotic) | 0.2 dB | 1.09 |
| STAK | (chaotic) | 0.5 dB | 1.12 |
| SPLT | (chaotic) | 0.3 dB | 1.05 |
| SHRD | (chaotic) | 0.9 dB | 1.01 |
| PIPE | (chaotic) | 0.1 dB | 1.21 |
| BOOM | 27.3 dB | 0.0 dB | 1.01 |
| KICK | 46.6 dB | 0.0 dB | 1.01 |

With metal and feedback high, Sophie's own C is chaotic: a 1e-5 nudge to its feedback state
gives an unrelated waveform (-0.2..-4.9 dB) of the same loudness and colour, so those cases
are held to loudness and brightness, not sample for sample. Each part alone (no feedback)
matches at 81..93 dB.

**Not done**: the project's ship gate (`scripts/ship_gate.py`) needs the owner's bench
(emulators, SHARC runner, snapshots, the Monomachine golden runs): not run, so no build of this
branch is cleared to flash. Unverified on hardware: the sound, the DSP time on the unit, the
page and MACHINE SEL entry.
