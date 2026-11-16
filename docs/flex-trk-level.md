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
source's level at the init sound. STRETCH's renderer (`render_stretch`) does not apply the mark. Only FLEX tracks
reach the buffers, and FLEX plays through `render()`.

## For upstream

- G17 in their runner (`sharc_dn2_fixups.py`) and the two-marker trkbuf check.
- `TRK_UNITY` x 10^(17.86 / 20) if they want GAIN 0 = source level on a unit at the init sound.

Upstream has no trackbuf.asm, so the 2026-11-15 TRK silence (ours) does not apply to them.
