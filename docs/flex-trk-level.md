# FLEX takes of a track: their level (2026-11-15)

A note for upstream (dn2mk2-firmware): it affects every build since v0.50, theirs included.

## What the unit showed

v0.53.11, the init sound on a track, ONESHOT looping, note 60 at VEL 127. FLEX REC on another track records it
(SRC TRK, GAIN 0), and the take plays back on the source's own track, through the same filter and amp.

| measured on | take against its source (RMS, amp out) |
|---|---|
| the unit (main out, 1 to 3.5 s into the note) | **-17.86 dB** (VEL 100: -19.85 dB) |
| the SHARC runner before the fix (step 3f) | -4.42 dB |
| the SHARC runner, fixed (below), in the amp's sustain | -16.0 dB |

v0.50's notes promise "a take of a track ... at the track's level as it sounds": GAIN 0 should give 0 dB.
That was measured on the runner only, and the runner was wrong.

## Cause: the runner, not the firmware

The output stage (`0x1c244d`) clears the 16 per-track buffers (`0x259f68 + 0x100 k`, FLEX's TRK sources and
Overbridge's raw track channels) at the start of every block, then adds each voice slot's block x 11.627 into its
track's buffer. The clear stores M12 = 0 in SIMD (Types 15b, 3a and 3b). On the chip, a SIMD store of a register
that has no PEy complement writes the same register at the companion address too. The runner wrote only PEx's
word, so every odd word of every buffer kept the sum of all the blocks it had ever received.

Measured on stock and on our build alike (a WaveTone note): TRK1 rose 0.065, 0.20, 0.36 ... 1.01 RMS over nine
blocks while the slot's block stayed at 0.029; after the clear, every odd word was still non-zero.

A FLEX take recorded that sum, and `TRK_UNITY` (0.1696 / 0.0725 = 2.339, `dnfw.sampler.machines`) was calibrated on
it. The fix is runner fix G17 in `scripts/sharc_dn2_fixups.py`: G12's rule extended to every memory form.
Runner step 4k (trkbuf) now writes two blocks' markers and requires only the last one in the buffers. It fails
without G17 and passes with it.

## What a take carries

The per-track buffer is the track after its whole chain: velocity, VOL, filter, amp envelope, LEVEL. Played back
on the same track, the take goes through that chain once more. So the take-to-source ratio is that chain's gain
times a constant, and GAIN 0 = source level holds for one setting only. Measured:

- on the unit, VEL 127 to VEL 100 lowers the source 2.1 dB and the take 4.2 dB;
- on the fixed runner, the init sound's amp sustain (SUS 96, 0.756) lowers the ratio by 2.0 dB against the
  attack.

The owner's ruling: keep upstream's design (record after the chain), and make its promise true at the init sound.

## The calibration

`TRK_UNITY = 0.1696 / 0.0725 x 10^(17.86 / 20)` = 18.28 (+25.2 dB), from the unit's measurement. The runner, fixed,
reads +1.86 dB at GAIN 0 with it (sustain, step 3f's source with amp DEC 0). The 1.9 dB between runner and unit is
written into step 3f as measured. Its cause is **not measured**: the unit's main-out RMS of a pulsing sample over
seconds against the runner's amp out over 8 ms, or something after the amp.

Step 3f on the fixed runner: the new value gives +1.77 dB (pass), the old value -16.09 dB (fail).

## Headroom

With the new value, a hot source fills the 16-bit take. Measured on the fixed runner (VOL 127, track LEVEL 127,
SUS 127, the sample at LEV 127):

| source | GAIN 0 | GAIN +38 |
|---|---|---|
| ONESHOT | take peak 1.0, 1.8 % of frames at the recorder's clamp | 85.6 % at the clamp |
| WaveTone | take peak 1.0, 7.7 % at the clamp | 60.0 % at the clamp |

Playback peaks stay under 1.8 at the voice and 0.16 at the amp out. GAIN +38 clips any normal source by construction.

### v0.54.3: the take keeps 18 dB of room

The owner chose to fix this. A FLEX take of a track (GAIN set, SRC TRK) is now stored at 1/8 of its level and
played 8 times louder (`TAKE_HEAD`), so GAIN 0 still plays at the source's level:

- **The mark.** Bit 17 of the buffer half's steps word, or of a slot entry's format word, marks the take. A voice
  keeps it in its `sla` word as bit 30 and multiplies its LEV by 8 once a block (`render()`).
- **The meter and THRES** still read the peak at the full level.
- **Saved takes.** A take saved to a pool slot is normalised and written as plain int16, so it plays as stored,
  with no mark.

Measured on the fixed runner, step 3f:

| check | v0.54.2 (no headroom) | v0.54.3 |
|---|---|---|
| hot source, GAIN 0: frames at the clamp | peak 1.0, FAIL | peak 0.17, none, PASS |
| hot take: 18.0 dB over the same take at GAIN -18 | +17.99 | +18.01, PASS |
| saved (plain int16) entry: 18.06 dB under the marked take | 0 dB, FAIL | -18.06, PASS |

A hot track's take plays louder than its source, because its VOL, SUS, LEVEL and LEV count once more. GAIN 0 is the
source's level at the init sound.

### v0.56.1: STRETCH applies the mark too

Since upstream v0.55 (FLEXPOOL), every sample machine can play the FLEX buffers, so a take can reach STRETCH, which
renders through `render_stretch()`. That renderer now multiplies LEV by `TAKE_HEAD` for a marked take, as `render()`
does. It needs no make-up gain: its two-tap reads sum to 1.

Measured on the runner, step 3f (the GAIN 0 take, out of the amp, against its source):

| playback | v0.54.3 | v0.56.1 |
|---|---|---|
| ONESHOT, marked take | +1.77 dB | +1.77 dB |
| ONESHOT, saved (unmarked) | -16.29 dB | -16.29 dB |
| STRETCH, marked take | -18.20 dB (mark ignored) | -0.14 dB |
| STRETCH, saved (unmarked) | -18.20 dB | -18.20 dB |

STRETCH plays this take 1.92 dB under ONESHOT whether it is marked or not. That is STRETCH's own level against
ONESHOT's, not the mark, so step 3f compares the mark's part: STRETCH against ONESHOT, marked and saved, within 0.1 dB.
Its cause, measured 2026-11-16 (the runner, v0.56.1, step 3f's GAIN 0 take on ONESHOT and on STRETCH, track 0's
voice before the stock chain):

- STRETCH plays the 768-frame take bit-exact: every frame is the take's x 8.00 (correlation 1.0000, 18.06 dB =
  `TAKE_HEAD`); a least-squares kernel puts 8.001 on lag 0 and nothing elsewhere.
- ONESHOT plays it through the DT2's reader (`render()`: the 6-tap, 256-phase interpolator at 96 kHz and the 2:1
  decimator, Elektron's coefficients). Fitted kernel (x 8, lag -4..4): -0.17 -1.30 5.44 5.34 -0.99 -0.39 0.09 -0.04
  0.01, unity at DC, about 1.5 frames early. Against STRETCH: 0-1 kHz -0.01 dB, 1-4 kHz +0.48, 4-10 kHz +1.43,
  10-24 kHz +1.83 dB: a treble lift.
- So the 1.92 dB is 1.48 dB of that lift on this bright source (frames 416-768, inside the take) plus 0.44 dB from the
  window running 32 frames past the take's end (frames 768-800), where STRETCH (no LOOP) stops and ONESHOT loops
  (PLAY 80, LOOP 20). The amp output reads the same (1.91 / 1.48).

Not a STRETCH level fault and not the mark: STRETCH reads exact frames, ONESHOT's reader is not flat.

## For upstream

- G17 in their runner (`sharc_dn2_fixups.py`) and the two-marker trkbuf check.
- `TRK_UNITY` x 10^(17.86 / 20) if they want GAIN 0 = source level on a unit at the init sound.

Upstream has no trackbuf.asm, so the 2026-11-15 TRK silence (ours) does not apply to them.

## v0.65.1: upstream's level taken (the User, 2026-11-21)

`TRK_UNITY` is now upstream v0.65's: 2.339 x 10^(`TRK_HW_DB` 12 / 20) = 9.31, 5.86 dB under our init-sound unity
(18.28). Measured on the runner (step flexlevel, build 9b89e2b9 at 18.28; minus 5.86 dB for 9.31; the runner reads
1.86 dB over the unit):

| sound | at 18.28 (runner / unit) | at 9.31 (runner / unit) |
|---|---|---|
| init sound | +1.77 / -0.09 dB | -4.09 / -5.95 dB |
| every level at 127 (VOL, SUS, LEVEL, LEV) | +8.60 / +6.74 dB | +2.74 / +0.88 dB |

flexlevel now expects the init sound at `RUNNER_TO_UNIT_DB + TRK_INIT_UNIT_DB` (-4.0 dB) and the all-127 sound at
`RUNNER_TO_UNIT_DB` (the source's level on the unit), each within its tolerance.

**TODO (not measured yet, investigate later):** a take's level against its source depends on the sound, about 7 dB
between the init sound and every level at 127. That suggests the track's LEVEL / VOL (and SUS, LEV) count differently
when the take is recorded and when it is played back: the take carries its track's chain once more (section 3
above), so a hot track's take comes out hotter. Measure on the unit which stages count twice before changing the
level again.

## v0.68.1: upstream's v0.68 level taken (the User, 2026-11-22)

Upstream v0.68 (its owner, on v0.67 itself, pattern volume 100, compressor off: a track's take 12 dB short, MAIN and
IN as well) set `TRK_HW_DB` 24 and `MAIN_PLAY_DB` 24. Both taken: `TRK_UNITY` = 2.339 x 10^(24 / 20) = 37.08, 6.14 dB
over our init-sound unity (18.28); a MAIN / IN take plays x 15.85 (was x 3.98).

Measured on the runner (step flexlevel on build v0.69.1 440085e4, 2026-11-22; the unit's column is the runner's
minus `RUNNER_TO_UNIT_DB` 1.86, derived, not measured on a unit):

| sound | at 37.08 runner (measured) | unit (derived) | the take's peak (stored x 1/8) |
|---|---|---|---|
| init sound | +7.92 dB | +6.06 dB | 0.189 of full scale |
| every level at 127 (VOL, SUS, LEVEL, LEV) | +14.74 dB | +12.88 dB | 0.350 of full scale, 0 frames at the clamp |

flexlevel's expectations follow the constants: the init sound at `RUNNER_TO_UNIT_DB + TRK_INIT_UNIT_DB` (+8.00 dB),
the all-127 sound at `RUNNER_TO_UNIT_DB + TRK_HW_DB - LOUD_UNITY_HW_DB` (+13.86 dB; `LOUD_UNITY_HW_DB` 12 is upstream
v0.65's calibration of that sound, NiKo). So on our runner model a GAIN 0 take is no longer at its source's level for
either sound; upstream's owner hears it at the source's level on his unit. The two disagree by the TODO above.

Upstream's known issues against ours:

- **A loud take may clip at GAIN 0** (upstream: the gain is applied before the recorder's int16 clamp). Ours stores a
  track's take x 1/8 (`TAKE_HEAD`, v0.54.3), so ours has 18 dB more room before that clamp than upstream's. At
  18.28 the hot source (VOL, SUS, LEVEL, LEV 127) recorded unclipped; at 37.08 that margin is 6.14 dB smaller.
  Measured at 37.08 (runner): the hot source records unclipped at GAIN 0, its take peaking at 0.350 of full scale
  as stored, 9.1 dB under the clamp. Without the 1/8 (upstream's way) the same take would peak at 2.8: clipped. On
  the unit a source hotter than the runner's hot one (other machines, drive, FX before the bucket) could still reach
  the clamp at GAIN 0; not measured.
- **A MAIN or IN take saved as a sample plays 24 dB quieter** than it played live: the same here. The saved entry
  is plain int16 without the MAIN mark (bit 15). A saved take of a **track** keeps its TAKE_HEAD mark (bit 17,
  v0.64.1), so it plays at the live take's level.
- The runner's G17 (TRK buckets cleared) and `RUNNER_TO_UNIT_DB` (+1.86) are unchanged: the level change is one
  constant in the recorder (x TRK_UNITY) and one in the voice (x MAIN_PLAY_DB); smp.asm differs from v0.67.5's in
  those four constants only.
