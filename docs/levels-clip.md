# How hot each machine runs against each output's clip point (2026-11-21)

The User: "are our engines designed too hot?" Measured in the SHARC runner on main 845e9777 (`scripts/levels_clip.py`,
run on the farm), nothing changed in any engine or trim. Tags: **[M]** measured, **[I]** inferred.

## Short answer

- **Stock clips its own Overbridge channel too.** WaveTone's default sound on a track at the kit's level (LEVEL 100,
  AMP VOL 110): one note peaks 1.3 dB under the track's own Overbridge clip point, a 4-note chord **10.8 dB over it**
  (460 saturated words) [M]. At LEVEL 127 / AMP VOL 127 one WaveTone note is **+5.4 dB** over, a chord **+17.4 dB**,
  and the chord also goes over Overbridge main (+8.2) and the analog outputs (+5.1) [I, see below].
- **Ours are not hotter than stock WaveTone; none is louder.** Our loudest single notes sit level with WaveTone
  (DPRO-WAVE and DPRO-DENS -1.0/-1.1 against WaveTone's -1.3 at the kit level); the rest are 1 to 7 dB under it
  (PLAITS BD 14 dB under). Our 4-note chords reach +6.4 at most (DRONE), against WaveTone's +10.8. At the kit level no
  single note of ours clips any output [M for the track channel].
- **Swarmer is the quiet stock machine** (-10.2 a note, -8.0 a chord); FM TONE and FM DRUM do not render in the runner
  (known gap, docs/levels.md), so there is no stock FM reference.
- The track's own Overbridge channel runs 9.3 dB hotter than the track's share of Overbridge main (x3.2768 in the
  routing, by stock's design), so it is the first output to clip, for stock and ours alike. Overbridge main clips
  3.1 dB before the analog outputs. Only full chords at high settings reach the main outputs.

## Method

Track 0, one machine at its default sound, note C4 (or a chord C4 E4 G4 C5 on four voice slots, all routed to track 0),
note on at block 1, 80 blocks (53 ms), one runner call a block. Three settings: **L100V100** (LEVEL 100, AMP VOL 100),
**KIT** (LEVEL 100, AMP VOL 110: the init sound's own), **MAX** (LEVEL 127, AMP VOL 127, VEL 127). Our engines read
velocity word 0 as full level, so in L100V100 and KIT they play at full velocity; a stock trig at VEL 100 plays them a
further 2.1 dB quieter (docs/levels.md).

Columns, dB against each output's own clip point (0 = clip):

| column | how | tag |
|---|---|---|
| track OB (A) | voice block peak x 66.1 (x14.125 routing, x3.2768, x1/0.7): the track's own Overbridge channel with the frame's source flag on A. Checked against the TX words themselves: WaveTone 0.0108 x 66.1 = 0.715, the word read 0.7151; "sat N" = saturated TX words counted | **M** |
| track OB (B) | track buffer after the amp x 11.627 x 1/0.7 (the raw channel, before LEVEL and VOL, so it does not move with them) | I (factor from link-research, not read here) |
| OB main | main bus x 1.127 x 1/0.7 | I |
| DAC | main bus x 1.127 | I |
| PERC out / port limit | PERC's output peak against its level (MD_LEVEL 1.4, the engine's MNM level, PLAITS by model) | M peak; the limit is an assumption |

The runner leaves Overbridge main (TX slots 0/1) and the main mix buffer empty, so the two main columns use the bus ->
mix ratio the runner's `levels` step measured at small signals (0.159 / 0.141); the master compressor sits in that
path, so at the hot rows they are an upper estimate [I].

## The track's own Overbridge channel (A), dB against its clip point [M]

| machine | L100V100 note / chord | KIT note / chord | MAX note / chord |
|---|---|---|---|
| **stock WaveTone** | -2.9 / **+9.1** | -1.3 / **+10.8** | **+5.4** / **+17.4** |
| stock Swarmer | -11.9 / -9.7 | -10.2 / -8.0 | -3.6 / -1.3 |
| stock FM TONE, FM DRUM | silent in the runner | | |
| DPRO-WAVE | -2.7 / +4.4 | -1.1 / +6.1 | +5.6 / +12.7 |
| DPRO-DENS | -2.7 / +2.6 | -1.0 / +4.3 | +5.6 / +10.9 |
| VO-6 | -3.7 / +4.3 | -2.0 / +6.0 | +4.6 / +12.6 |
| DRONE | -6.4 / +4.8 | -4.7 / +6.4 | +1.9 / +13.1 |
| SID 6581 | -7.2 / +4.3 | -5.5 / +5.9 | +1.1 / +12.6 |
| SOPHIE | -8.5 / +1.1 | -6.8 / +2.8 | -0.2 / +9.4 |
| ANALOG2 | -7.9 / -0.5 | -6.3 / +1.2 | +0.4 / +7.9 |
| TB303 | -8.1 / -1.4 | -6.5 / +0.2 | +0.2 / +6.9 |
| JUNO | -9.7 / -2.4 | -8.0 / -0.7 | -1.4 / +5.9 |
| PLAITS VA / WS / FM / MDAL / STRG / BD | -7.7 / -8.9 / -8.7 / -7.5 / -8.7 / -17.4 | -6.0 / -7.2 / -7.0 / -5.8 / -7.1 / -15.8 | +0.6 / -0.6 / -0.4 / +0.8 / -0.4 / -9.1 |
| MD PI-BD / PI-SD / TRX-BD / TRX-SD / EFM-BD / EFM-SD | -3.7 / -3.9 / -4.4 / -5.3 / -8.3 / -7.7 | -2.1 / -2.3 / -2.7 / -3.6 / -6.6 / -6.0 | +4.6 / +4.4 / +3.9 / +3.0 / +0.0 / +0.6 |
| SMP ONESHOT (the runner's sample; its own peak against full scale not checked [O]) | -8.1 | -6.4 | +0.2 |

Against the 2026-11-20 run (rr/levels-max, v0.62.5, 60 blocks): every row it shares agrees to 0.1 dB (WaveTone
+5.4 / +17.4 at MAX, +9.1 chord at L100V100; JUNO -1.4, ANALOG2 +0.4, SOPHIE -0.2, TB303 +0.2, DRONE +1.9, SID +1.1,
DPRO-WAVE / DENS +5.6 at MAX) except VO-6 at MAX, +4.6 here against +3.0 then (not explained; 80 blocks here, 60 then).

## Inside the fixed-point ports

- **Machinedrum ports** (56300 model, `src/dnfw/md/core.py`: the `sat` limiter clamps to [-1, 1 - 2^-23]): PERC's
  output peaks at the port's full scale x MD_LEVEL on TRX-BD (-0.0 dB), PI-BD (+0.2) and PI-SD (+0.1) at their default
  sounds [M peak]; that they ride the limiter there is inferred from the exact match [I]. TRX-SD -1.2, EFM-SD -3.2,
  EFM-BD -4.0. This is the Machinedrum's own sound, not a DN2 clip.
- **Monomachine ports** (VO-6, DPRO, SID: `limi` in `src/dnfw/mnm/vo6.py`): 14.6 to 20.9 dB under their level value at
  PERC's output. Their native output scale is not word / 2^23 x level (their levels are 5.4 to 18.4), so whether they
  saturate inside is not shown by this measurement [O].
- Float engines (DRONE +3.7, PLAITS) have no fixed-point stage; the column is only their level ratio.

## The raw channel (B)

If the Overbridge track channels are taken from B (frame word +0xa7a = 0), every machine's default sound is over
regardless of LEVEL and AMP VOL: stock WaveTone +8.6, ours +1.8 (JUNO) to +8.8 (DPRO) [I: factor 11.627 x 1/0.7 from
link-research, not read back]. Which source the unit uses was not checked here.

## Full tables

All three settings, every column (from `scripts/levels_clip.py`, results in the farm's rr/levels-clip/out):


**L100V100**

| machine | notes | voice block peak | track OB (A) | track OB (B) | OB main | DAC | PERC out / port limit | NaN |
|---|---|---|---|---|---|---|---|---|
| ANALOG2 | 1 | -44.3 | **-7.9** | +3.6 | -17.2 | -20.3 | -0.5 |  |
| ANALOG2 | 4 | -36.9 | **-0.5** | +3.6 | -9.7 | -12.8 | -0.3 |  |
| DPRO-DENS | 1 | -39.1 | **-2.7** | +8.8 | -12.0 | -15.1 | -6.1 |  |
| DPRO-DENS | 4 | -33.8 | **+2.6** sat 14 | +8.8 | -6.6 | -9.7 | -6.1 |  |
| DPRO-WAVE | 1 | -39.1 | **-2.7** | +8.8 | -12.0 | -15.1 | -20.9 |  |
| DPRO-WAVE | 4 | -32.0 | **+4.4** sat 64 | +8.8 | -4.9 | -8.0 | -20.9 |  |
| DRONE | 1 | -42.8 | **-6.4** | +5.1 | -15.7 | -18.8 | +3.7 |  |
| DRONE | 4 | -31.6 | **+4.8** sat 410 | +5.1 | -4.5 | -7.6 | +3.7 |  |
| JUNO | 1 | -46.1 | **-9.7** | +1.8 | -19.0 | -22.0 | -1.9 |  |
| JUNO | 4 | -38.8 | **-2.4** | +1.8 | -11.6 | -14.7 | -1.9 |  |
| MD EFM-BD | 1 | -44.7 | **-8.3** | +3.2 | -17.5 | -20.6 | -4.0 |  |
| MD EFM-SD | 1 | -44.1 | **-7.7** | +3.8 | -16.9 | -20.0 | -3.2 |  |
| MD PI-BD | 1 | -40.1 | **-3.7** | +7.8 | -13.0 | -16.1 | +0.2 |  |
| MD PI-SD | 1 | -40.4 | **-3.9** | +7.5 | -13.2 | -16.3 | +0.1 |  |
| MD TRX-BD | 1 | -40.8 | **-4.4** | +7.1 | -13.7 | -16.8 | -0.0 |  |
| MD TRX-SD | 1 | -41.7 | **-5.3** | +6.2 | -14.6 | -17.7 | -1.2 |  |
| PLAITS BD | 1 | -53.9 | **-17.4** | -6.0 | -26.7 | -29.8 | -9.9 |  |
| PLAITS FM | 1 | -45.1 | **-8.7** | +2.8 | -17.9 | -21.0 | -4.4 |  |
| PLAITS MDAL | 1 | -43.9 | **-7.5** | +4.0 | -16.7 | -19.8 | +0.2 |  |
| PLAITS STRG | 1 | -45.2 | **-8.7** | +2.7 | -18.0 | -21.1 | -12.8 |  |
| PLAITS VA | 1 | -44.1 | **-7.7** | +3.8 | -17.0 | -20.1 | -2.8 |  |
| PLAITS WS | 1 | -45.3 | **-8.9** | +2.6 | -18.2 | -21.3 | -1.8 |  |
| SID 6581 | 1 | -43.6 | **-7.2** | +4.3 | -16.5 | -19.6 | -14.6 |  |
| SID 6581 | 4 | -32.1 | **+4.3** sat 236 | +4.3 | -5.0 | -8.1 | -14.6 |  |
| SMP ONESHOT | 1 | -44.5 | **-8.1** | +3.4 | -17.3 | -20.4 |  |  |
| SOPHIE | 1 | -44.9 | **-8.5** | +3.0 | -17.7 | -20.8 | -5.0 |  |
| SOPHIE | 4 | -35.3 | **+1.1** sat 10 | +3.0 | -8.2 | -11.3 | -5.0 |  |
| TB303 | 1 | -44.5 | **-8.1** | +3.4 | -17.4 | -20.5 | -7.9 |  |
| TB303 | 4 | -37.8 | **-1.4** | +3.4 | -10.7 | -13.8 | -7.3 |  |
| VO-6 | 1 | -40.1 | **-3.7** | +7.8 | -12.9 | -16.0 | -19.4 |  |
| VO-6 | 4 | -32.1 | **+4.3** sat 362 | +7.8 | -4.9 | -8.0 | -19.4 |  |
| stock FM DRUM | 1 | silent | | | | | | 0 |
| stock FM TONE | 1 | silent | | | | | | 0 |
| stock FM TONE | 4 | silent | | | | | | 0 |
| stock SWARMER | 1 | -48.3 | **-11.9** | -0.4 | -21.1 | -24.2 |  |  |
| stock SWARMER | 4 | -46.1 | **-9.7** | -0.4 | -18.9 | -22.0 |  |  |
| stock WAVETONE | 1 | -39.3 | **-2.9** | +8.6 | -12.2 | -15.3 |  |  |
| stock WAVETONE | 4 | -27.3 | **+9.1** sat 460 | +8.6 | -0.1 | -3.2 |  |  |

**KIT**

| machine | notes | voice block peak | track OB (A) | track OB (B) | OB main | DAC | PERC out / port limit | NaN |
|---|---|---|---|---|---|---|---|---|
| ANALOG2 | 1 | -42.7 | **-6.3** | +3.6 | -15.5 | -18.6 | -0.5 |  |
| ANALOG2 | 4 | -35.2 | **+1.2** sat 122 | +3.6 | -8.1 | -11.2 | -0.3 |  |
| DPRO-DENS | 1 | -37.4 | **-1.0** | +8.8 | -10.3 | -13.4 | -6.1 |  |
| DPRO-DENS | 4 | -32.1 | **+4.3** sat 58 | +8.8 | -5.0 | -8.1 | -6.1 |  |
| DPRO-WAVE | 1 | -37.5 | **-1.1** | +8.8 | -10.3 | -13.4 | -20.9 |  |
| DPRO-WAVE | 4 | -30.3 | **+6.1** sat 170 | +8.8 | -3.2 | -6.3 | -20.9 |  |
| DRONE | 1 | -41.2 | **-4.7** | +5.1 | -14.0 | -17.1 | +3.7 |  |
| DRONE | 4 | -30.0 | **+6.4** sat 672 | +5.1 | -2.8 | -5.9 | +3.7 |  |
| JUNO | 1 | -44.4 | **-8.0** | +1.8 | -17.3 | -20.4 | -1.9 |  |
| JUNO | 4 | -37.1 | **-0.7** | +1.8 | -10.0 | -13.1 | -1.9 |  |
| MD EFM-BD | 1 | -43.0 | **-6.6** | +3.2 | -15.9 | -19.0 | -4.0 |  |
| MD EFM-SD | 1 | -42.4 | **-6.0** | +3.8 | -15.3 | -18.4 | -3.2 |  |
| MD PI-BD | 1 | -38.5 | **-2.1** | +7.8 | -11.3 | -14.4 | +0.2 |  |
| MD PI-SD | 1 | -38.7 | **-2.3** | +7.5 | -11.6 | -14.7 | +0.1 |  |
| MD TRX-BD | 1 | -39.2 | **-2.7** | +7.1 | -12.0 | -15.1 | -0.0 |  |
| MD TRX-SD | 1 | -40.0 | **-3.6** | +6.2 | -12.9 | -16.0 | -1.2 |  |
| PLAITS BD | 1 | -52.2 | **-15.8** | -6.0 | -25.1 | -28.2 | -9.9 |  |
| PLAITS FM | 1 | -43.4 | **-7.0** | +2.8 | -16.3 | -19.4 | -4.4 |  |
| PLAITS MDAL | 1 | -42.2 | **-5.8** | +4.0 | -15.1 | -18.2 | +0.2 |  |
| PLAITS STRG | 1 | -43.5 | **-7.1** | +2.7 | -16.4 | -19.5 | -12.8 |  |
| PLAITS VA | 1 | -42.5 | **-6.0** | +3.8 | -15.3 | -18.4 | -2.8 |  |
| PLAITS WS | 1 | -43.7 | **-7.2** | +2.6 | -16.5 | -19.6 | -1.8 |  |
| SID 6581 | 1 | -41.9 | **-5.5** | +4.3 | -14.8 | -17.9 | -14.6 |  |
| SID 6581 | 4 | -30.5 | **+5.9** sat 454 | +4.3 | -3.3 | -6.4 | -14.6 |  |
| SMP ONESHOT | 1 | -42.8 | **-6.4** | +3.4 | -15.7 | -18.8 |  |  |
| SOPHIE | 1 | -43.2 | **-6.8** | +3.0 | -16.1 | -19.2 | -5.0 |  |
| SOPHIE | 4 | -33.7 | **+2.8** sat 54 | +3.0 | -6.5 | -9.6 | -5.0 |  |
| TB303 | 1 | -42.9 | **-6.5** | +3.4 | -15.7 | -18.8 | -7.9 |  |
| TB303 | 4 | -36.2 | **+0.2** sat 4 | +3.4 | -9.0 | -12.1 | -7.3 |  |
| VO-6 | 1 | -38.4 | **-2.0** | +7.8 | -11.3 | -14.4 | -19.4 |  |
| VO-6 | 4 | -30.4 | **+6.0** sat 590 | +7.8 | -3.3 | -6.4 | -19.4 |  |
| stock FM DRUM | 1 | silent | | | | | | 0 |
| stock FM TONE | 1 | silent | | | | | | 0 |
| stock FM TONE | 4 | silent | | | | | | 0 |
| stock SWARMER | 1 | -46.6 | **-10.2** | -0.4 | -19.5 | -22.6 |  |  |
| stock SWARMER | 4 | -44.4 | **-8.0** | -0.4 | -17.3 | -20.4 |  |  |
| stock WAVETONE | 1 | -37.7 | **-1.3** | +8.6 | -10.5 | -13.6 |  |  |
| stock WAVETONE | 4 | -25.6 | **+10.8** sat 460 | +8.6 | +1.5 | -1.6 |  |  |

**MAX**

| machine | notes | voice block peak | track OB (A) | track OB (B) | OB main | DAC | PERC out / port limit | NaN |
|---|---|---|---|---|---|---|---|---|
| ANALOG2 | 1 | -36.0 | **+0.4** sat 120 | +3.6 | -8.9 | -12.0 | -0.5 |  |
| ANALOG2 | 4 | -28.6 | **+7.9** sat 1502 | +3.6 | -1.4 | -4.5 | -0.3 |  |
| DPRO-DENS | 1 | -30.8 | **+5.6** sat 278 | +8.8 | -3.7 | -6.8 | -6.1 |  |
| DPRO-DENS | 4 | -25.5 | **+10.9** sat 932 | +8.8 | +1.7 | -1.4 | -6.1 |  |
| DPRO-WAVE | 1 | -30.8 | **+5.6** sat 426 | +8.8 | -3.7 | -6.8 | -20.9 |  |
| DPRO-WAVE | 4 | -23.7 | **+12.7** sat 1528 | +8.8 | +3.4 | +0.3 | -20.9 |  |
| DRONE | 1 | -34.5 | **+1.9** sat 1246 | +5.1 | -7.4 | -10.5 | +3.7 |  |
| DRONE | 4 | -23.3 | **+13.1** sat 2328 | +5.1 | +3.8 | +0.7 | +3.7 |  |
| JUNO | 1 | -37.8 | **-1.4** | +1.8 | -10.6 | -13.7 | -1.9 |  |
| JUNO | 4 | -30.5 | **+5.9** sat 682 | +1.8 | -3.3 | -6.4 | -1.9 |  |
| MD EFM-BD | 1 | -36.4 | **+0.0** sat 6 | +3.2 | -9.2 | -12.3 | -4.0 |  |
| MD EFM-SD | 1 | -35.8 | **+0.6** sat 2 | +3.8 | -8.6 | -11.7 | -3.2 |  |
| MD PI-BD | 1 | -31.8 | **+4.6** sat 1202 | +7.8 | -4.7 | -7.8 | +0.2 |  |
| MD PI-SD | 1 | -32.1 | **+4.4** sat 368 | +7.5 | -4.9 | -8.0 | +0.1 |  |
| MD TRX-BD | 1 | -32.5 | **+3.9** sat 268 | +7.1 | -5.4 | -8.5 | -0.0 |  |
| MD TRX-SD | 1 | -33.4 | **+3.0** sat 18 | +6.2 | -6.3 | -9.4 | -1.2 |  |
| PLAITS BD | 1 | -45.6 | **-9.1** | -6.0 | -18.4 | -21.5 | -9.9 |  |
| PLAITS FM | 1 | -36.8 | **-0.4** | +2.8 | -9.6 | -12.7 | -4.4 |  |
| PLAITS MDAL | 1 | -35.6 | **+0.8** sat 38 | +4.0 | -8.4 | -11.5 | +0.2 |  |
| PLAITS STRG | 1 | -36.8 | **-0.4** | +2.7 | -9.7 | -12.8 | -12.8 |  |
| PLAITS VA | 1 | -35.8 | **+0.6** sat 16 | +3.8 | -8.7 | -11.8 | -2.8 |  |
| PLAITS WS | 1 | -37.0 | **-0.6** | +2.6 | -9.9 | -13.0 | -1.8 |  |
| SID 6581 | 1 | -35.3 | **+1.1** sat 540 | +4.3 | -8.2 | -11.2 | -14.6 |  |
| SID 6581 | 4 | -23.8 | **+12.6** sat 1918 | +4.3 | +3.3 | +0.2 | -14.6 |  |
| SMP ONESHOT | 1 | -36.2 | **+0.2** sat 50 | +3.4 | -9.0 | -12.1 |  |  |
| SOPHIE | 1 | -36.6 | **-0.2** | +3.0 | -9.4 | -12.5 | -5.0 |  |
| SOPHIE | 4 | -27.0 | **+9.4** sat 822 | +3.0 | +0.1 | -3.0 | -5.0 |  |
| TB303 | 1 | -36.2 | **+0.2** sat 8 | +3.4 | -9.1 | -12.2 | -7.9 |  |
| TB303 | 4 | -29.5 | **+6.9** sat 340 | +3.4 | -2.4 | -5.5 | -7.3 |  |
| VO-6 | 1 | -31.8 | **+4.6** sat 416 | +7.8 | -4.6 | -7.7 | -19.4 |  |
| VO-6 | 4 | -23.8 | **+12.6** sat 1910 | +7.8 | +3.4 | +0.3 | -19.4 |  |
| stock FM DRUM | 1 | silent | | | | | | 0 |
| stock FM TONE | 1 | silent | | | | | | 0 |
| stock FM TONE | 4 | silent | | | | | | 0 |
| stock SWARMER | 1 | -40.0 | **-3.6** | -0.4 | -12.8 | -15.9 |  |  |
| stock SWARMER | 4 | -37.8 | **-1.3** | -0.4 | -10.6 | -13.7 |  |  |
| stock WAVETONE | 1 | -31.0 | **+5.4** sat 306 | +8.6 | -3.9 | -7.0 |  |  |
| stock WAVETONE | 4 | -19.0 | **+17.4** sat 768 | +8.6 | +8.2 | +5.1 |  |  |
