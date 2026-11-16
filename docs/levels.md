# Our engines' levels against the stock synths (2026-11-12)

The User: "compare the engine levels, they should match approx, don't boost out of the blue".

## Method

As v0.22 measured `MD_LEVEL` (docs/md.md): the SHARC runner, track 0 on the init sound, note 60 triggered at block 1,
the **amp stage's input** (after the stock filter at the init sound, before the amp): peak and RMS over 341 blocks
(227 ms), each engine at its defaults, no velocity. Stock reference: WaveTone (peak -15.8 dB, RMS -26.4) and FM TONE
(-18.7, -33.4). **Runner gap:** FM DRUM and Swarmer do not render in the SHARC runner (their machine output is 0
on track 0 and on track 1, set as the runner's own stock step sets them; the engine-init snapshot is WaveTone's), so
they are not in the reference; not chased (main, 2026-11-12).

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
| DPRO-DENS | held | RMS -33.0 | +4.7 | -28.3 ¹ |
| PLAITS SWRM | held | RMS -28.9 | +2.5 | -26.4 |
| SOPHIE | hit | peak -21.1 | +3.8 | -17.3 |
| TB-303 | hit | peak -22.7 | +4.0 | -18.7 ¹ |
| PLAITS MDAL | hit | peak -19.5 | +2.2 | -17.3 |
| PLAITS SD | hit | peak -19.9 | +2.6 | -17.3 |
| PLAITS HH | hit | peak -21.3 | +4.0 | -17.3 |
| PLAITS BD | hit | peak -27.0 | +9.7 | -17.3 |
| PLAITS STRG | hit | peak -27.0 | +8.4 | -18.6 ¹ |
| SID 6581, PLAITS FM, ADD, VA, NOIS, DRONE, VO-6 | held | RMS -24.7 .. -28.4 | 0 | in band |
| PLAITS PART | hit | peak -17.9 | 0 | in band |

¹ In its band, short of the middle: at the middle the engine's loudest setting (every knob 127, the runner's `tops`
run) went past the runner's 4.0 bound on a track buffer (TB-303 4.29, DPRO-DENS 4.42 at +5.4 / +6.6 dB; PLAITS STRG 4.52 at +9.7 dB, its start when the runner's MODL walk turns to it); at these it
stays near 3.6.

## The Machinedrum machines (all 34, peak at the amp stage, 53 ms; 2026-11-12)

The hit band is -17.3 +-2 dB. In it: EFM-HH -18.7, TRX-XC -18.6, TRX-XT -18.4, PI-SD -18.4, GND-NS -18.1, TRX-SD -18.0, TRX-BD -17.9, PI-MT -17.9, PI-BD -17.3.
Below it: TRX-MA -29.5, TRX-CH -28.5, TRX-OH -28.5, TRX-CY -28.3, TRX-CL -27.5, GND-SN -26.2, TRX-RS -26.0, PI-RC -26.0, TRX-CB -25.3, TRX-CP -25.2, TRX-S2 -24.6, PI-CC -24.6, PI-MA -23.8, EFM-CY -23.2, PI-HH -23.2, EFM-XT -22.3, PI-ML -21.7, EFM-CB -21.1, TRX-B2 -20.9, EFM-SD -20.6, EFM-BD -20.0, EFM-RS -19.8, GND-IM -19.8, EFM-CP -19.7, PI-RS -19.6.
The Machinedrum's own kit balance (hats and cymbals ~10 dB under the kicks); they all share `MD_LEVEL` (v0.22).
The User (2026-11-12): "leave MD as is" (a hi-hat need not be as loud: "it is not a melodic synth"). A per-category
comparison against the User's own drum samples is kept in the session notes (md-levels-by-category.md).

## Where

`dnfw.perc.program`: `LEVEL_DB` (on top of `MNM_LEVELS` / `MD_LEVEL`, per Monomachine machine and MONOMACHINE
engine), `PLAITS_LEVEL_DB` (by model: `plaits_level`, the model as the engine chooses it from MODL, once a block).
Nothing a sample. `test/test_engine_levels.py` holds the measured table and each engine in its band at the levels it
has now. With velocity (claude/velocity) a trig at the stock default VEL 100 plays our engines a further -2.1 dB.
