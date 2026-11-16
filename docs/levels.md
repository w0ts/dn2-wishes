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
| SOPHIE | hit | peak -21.1 | 0 ² | -21.1 |
| TB-303 | hit | peak -22.7 | +4.0 | -18.7 ¹ |
| PLAITS MDAL | hit | peak -19.5 | +2.2 | -17.3 |
| PLAITS SD | hit | peak -19.9 | 0 ² | -19.9 |
| PLAITS HH | hit | peak -21.3 | 0 ² | -21.3 |
| PLAITS BD | hit | peak -27.0 | 0 ² | -27.0 |
| PLAITS STRG | hit | peak -27.0 | +8.4 | -18.6 ¹ |
| SID 6581, PLAITS FM, ADD, VA, NOIS, DRONE, VO-6 | held | RMS -24.7 .. -28.4 | 0 | in band |
| PLAITS PART | hit | peak -17.9 | 0 | in band |
| JUNO ³ | held | RMS -25.3 (peak -18.0); on the unit +4.1 over WaveTone | -4.0 | RMS -29.3; on the unit level with WaveTone |

¹ In its band, short of the middle: at the middle the engine's loudest setting (every knob 127, the runner's `tops`
run) went past the runner's 4.0 bound on a track buffer (TB-303 4.29, DPRO-DENS 4.42 at +5.4 / +6.6 dB; PLAITS STRG 4.52 at +9.7 dB, its start when the runner's MODL walk turns to it); at these it
stays near 3.6.

² **The User, 2026-11-12, on r11f** (SOPHIE "very loud"): "bring it back how it was, apply the correction only to the
melodic synths". The drums and percussion (SOPHIE, PLAITS BD, SD, HH) are at their levels from before this work, bit
for bit; the melodic synths (ANALOG 2, TB-303, PLAITS WS, SWRM, MDAL, STRG, DPRO-WAVE, DDRW, DENS) keep their
corrections; the Machinedrum is as it was.

³ JUNO (type 23, 2026-11-12), measured after this table on r11f (v0.48 round 11) as the others: RMS -25.3 dB, 1.1 dB
over WaveTone's -26.4, so inside the band and left bit for bit (no LEVEL_DB entry); its machine tap peaks at 1.12
(WaveTone 1.00, ANALOG 2 0.92).
**2026-11-14, on the unit (r5; the User: "Juno level: good"):** the same track (T13) at both machines' defaults, JUNO
against stock WaveTone: 6 single notes -16.4 dB RMS against -20.5 (+4.1), 4 four-note chords -10.5 against -14.4
(+3.9), and JUNO's chords clipped alone (peak 1.000, WaveTone's 0.526). The unit decides over the runner (whose +1.1 the
unit's +4.1 does not match, not explained yet): JUNO gets -4.0 dB (`LEVEL_DB`), level with WaveTone there, its chords'
peak ~0.63. In the SHARC runner (16 blocks, note 60, defaults; and a 4-note chord) it is a pure scale of JUNO's output:
its PERC output words are the old ones times 10^(-4/20) to float rounding (RMS -4.00000 dB, error <= 5.5e-8 of the
peak), every other Monomachine engine and WaveTone bit for bit at PERC's output and at the amp stage's input. PERC's code
gains one branch (JUNO's level 0.8833 for MD_LEVEL's 1.4), +24 B. After stock's filter (the amp stage's input) JUNO
moves -3.89 dB: that filter is stock's, bit for bit, fed a quieter signal.

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
