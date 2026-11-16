# Our engines' levels against the stock synths (2026-11-12)

The User: "compare the engine levels, they should match approx, don't boost out of the blue".

## Method

As v0.22 measured `MD_LEVEL` (docs/md.md): the SHARC runner, track 0 on the init sound, note 60 triggered at block 1,
the **amp stage's input** (after the stock filter at the init sound, before the amp): peak and RMS over 341 blocks
(227 ms), each engine at its defaults, no velocity. Stock reference: WaveTone (peak -15.8 dB, RMS -26.4) and FM TONE
(-18.7, -33.4); FM DRUM and Swarmer do not render in the runner (their machine output is 0 on any track), so they are
not in it.

Two yardsticks, because a decaying hit and a held tone with the same peak differ 10 dB and more in RMS:

- a **held** synth: its RMS within +-2 dB of WaveTone's (-26.4 dB);
- a **hit** (drums, plucks: SOPHIE, TB-303, PLAITS's percussive and resonator models): its peak within +-2 dB of the
  stock synths' mean peak (-17.3 dB).

An engine already in its band keeps its level (bit for bit); one outside moves to the middle of its band.

## Before and after (dB at the amp stage)

| engine | kind | measured | change | after |
|---|---|---|---|---|
| ANALOG 2 | held | RMS -23.2 | -3.2 | -26.4 |
| PLAITS WS | held | RMS -23.6 | -2.8 | -26.4 |
| DPRO-WAVE | held | RMS -30.5 | +4.1 | -26.4 |
| DPRO-DDRW | held | RMS -29.3 | +2.9 | -26.4 |
| DPRO-DENS | held | RMS -33.0 | +6.6 | -26.4 |
| PLAITS SWRM | held | RMS -28.9 | +2.5 | -26.4 |
| SOPHIE | hit | peak -21.1 | +3.8 | -17.3 |
| TB-303 | hit | peak -22.7 | +5.4 | -17.3 |
| PLAITS MDAL | hit | peak -19.5 | +2.2 | -17.3 |
| PLAITS SD | hit | peak -19.9 | +2.6 | -17.3 |
| PLAITS HH | hit | peak -21.3 | +4.0 | -17.3 |
| PLAITS BD | hit | peak -27.0 | +9.7 | -17.3 |
| PLAITS STRG | hit | peak -27.0 | +9.7 | -17.3 |
| SID 6581, PLAITS FM, ADD, VA, NOIS, DRONE, VO-6 | held | RMS -24.7 .. -28.4 | 0 | in band |
| PLAITS PART | hit | peak -17.9 | 0 | in band |

The Machinedrum machines share one level (`MD_LEVEL`, v0.22): TRX-BD, TRX-SD and PI-BD sit in the hit band; PI-HH
(-23.2) and EFM-SD (-20.6) below it. Not changed: a per-machine level would be new host code, and the other 29 are
not measured.

## Where

`dnfw.perc.program`: `LEVEL_DB` (on top of `MNM_LEVELS` / `MD_LEVEL`, per Monomachine machine and MONOMACHINE
engine), `PLAITS_LEVEL_DB` (by model: `plaits_level`, the model as the engine chooses it from MODL, once a block).
Nothing a sample. `test/test_engine_levels.py` holds the measured table and each engine in its band at the levels it
has now. With velocity (claude/velocity) a trig at the stock default VEL 100 plays our engines a further -2.1 dB.
