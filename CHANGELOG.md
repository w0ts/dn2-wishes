# DN2 WISHES — CHANGELOG — Digitone II (all builds are based on OS 1.12)

## NEXT (not built yet)

v0.54.2 moved onto upstream v0.56 (v0.55 FLEXPOOL + v0.56 DDRW), plus the items below, then one
full test run. Goal: the first release. (v0.54.3 is not built: the User moved to the newest
upstream on 16 Nov.)

Checked in the emulator, nothing to fix:

  - Switching XDLY to the stock delay leaves no old echo.

Next build (v0.56.1), as decided by the User 15 Nov:

  - Paraphonic ON plays up to 8 notes (was 4).
  - When the chord is full, a new key plays and the oldest held note stops (today the new key
    is ignored).
  - FLEX: a take recorded from a very loud track no longer clips (the take is stored 18 dB
    lower and brought back up on playback; GAIN 0 still plays it at the source's level).

Open questions:

  - On the unit, track 1 (ANALOG 2) of a new project plays one note at a time; tracks 2 and 8
    play chords. Cause not found yet.

## v0.54.2 (16 Nov 2026)

- **Status:** Not released: testing stopped (moved to v0.56); 78 of 79 steps passed when run one at a time (LFO4 does not apply), the complete run was stopped before its verdict. Do not install.
- **Based on:** v0.54.1
- **File:** DN2wishes_v0.54.2.syx
- **SHA-256:** e357af71f8f09d78b3a417f54645d0522d6a760fb34c4a86b3943250ba48eb64
- **Hardware:** Not yet tested on hardware.

**Changes**

  - FLEX: a take recorded from a track at GAIN 0 plays at its source's level (it was about
    18 dB quieter on the unit).
  - Paraphonic: VOICE menu knob B is PARA OFF / ON (ON plays a chord of up to 4 notes); the
    chord's extra notes skip the sample-rate conversion, so a chord uses less DSP time.
  - The DSP load check uses newly measured costs (every engine slightly higher).

**Known issues**

  - FLEX: a take recorded from a very loud track clips (GAIN 0 with VOL, LEVEL and SUS at 127:
    1.8 % of ONESHOT frames, 7.7 % of WaveTone frames). Fixed in the next build.
  - Tests: the xdly and flexlevel tests now pass. 78 of 79 steps passed when run alone (one did not
    apply); the complete run that clears a build was stopped before its verdict.

## v0.54.1 (15 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.53.13, moved onto upstream v0.54 (NAME)
- **File:** DN2wishes_v0.54.1.syx
- **SHA-256:** aac18059d063cf069ea25a80b763ac6302b57127a8a732fb0c315fc474688aa5
- **Hardware:** Not yet tested on hardware.

**Changes**

  - From upstream v0.54: FILE NAME (after TRIM), RENAME and CREATE FOLDER open the Digitone's own
    NAME screen (35 characters, random name, copy and paste). The recorder's own name page is used
    only if that screen cannot open.
  - Paraphonic chords: the chord's extra notes no longer run their own insert effects. The first
    note's inserts process the whole chord, as before.
  - The DSP load check uses newly measured costs (each insert effect slightly higher).

**Known issues**

  - Test failures: xdly and flexlevel, the same two as in v0.53.13, with the same results
    (fixes in v0.54.2; see NEXT). All other tests pass, including upstream's new NAME screen test
    and the recorder test, both on OS 1.12.

## v0.53.13 (15 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.53.12
- **File:** DN2wishes_v0.53.13.syx
- **SHA-256:** dfc09c4ad6a0769898ad3f6f95d2e7f811ebe8111e130440e561c7f10fceea25
- **Hardware:** Not yet tested on hardware.

**Changes**

  - Paraphonic mode on JUNO: VOICE menu knob B sets PARA to OFF, 2, 3 or 4 notes, as on ANALOG 2.
    A 4-note JUNO chord uses about a third less DSP time than 4 voices.
  - The DSP load check uses newly measured costs (JUNO slightly higher).

**Known issues**

  - Test failures: xdly (its stock delay test is too short to hear the first repeat; fixed in the
    test for v0.54.2), flexlevel (a take's level against its source; see NEXT).
    All other tests pass, including the paraphonic menu test.

## v0.53.12 (15 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.53.11
- **File:** DN2wishes_v0.53.12.syx
- **SHA-256:** 7892a8d15b6c365c562e93eadcfaa3986b9282b5208e424930616a62819aa80b
- **Hardware:** Installed on the unit 15 Nov 2026 (evening). Tested on the unit: paraphonic chords on ANALOG 2 (2-4 notes, a 4-note chord uses 18 % less DSP time), 16 held TB-303 voices (DSP peak 83 %, no voice dropped), ghost-delay test: all pass.

**Changes**

  - Paraphonic mode on ANALOG 2: VOICE menu knob B sets PARA to OFF, 2, 3 or 4 notes.
  - The DSP load check uses newly measured costs for every engine and effect.

**Known issues**

  - Test failures: xdly (test emulator), flexlevel (a take's level against its source: the
    emulator measures 4.0 dB under at the track's chain, 4.4 dB under at the amp; see NEXT).
    All other tests pass, including the new paraphonic menu test.

## v0.53.11 (15 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.53.10
- **File:** DN2wishes_v0.53.11.syx
- **SHA-256:** d452fbc00615a07c9e9c3386d73b36d1ac90aef84f22d0c9868bb82472e54d73
- **Hardware:** Was installed 15 Nov 2026 (afternoon). FLEX takes from a track have sound again, but play back about 15 dB under their source (being investigated).

**Changes**

  - FLEX takes from a track work again: a take recorded from any track now holds that track's
    sound (it was silent in v0.53.9b and v0.53.10).

**Known issues**

  - Test failures: xdly (test emulator), flexlevel (a take's level against its source; see NEXT).
    All other tests pass, including the new track-buffer test and the slice test.

## v0.53.10 (15 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.53.9b
- **File:** DN2wishes_v0.53.10.syx
- **SHA-256:** 64893205968fc503f1a0f19211a1a10e9b78b785b6acc351c0121dfcebdf2596
- **Hardware:** Not yet tested on hardware.

**Changes**

  - VO-6 retriggers like the Monomachine: a new note on a sounding voice starts with a short
    fade from its current level; a voice that has rested starts its next note at once.

**Known issues**

  - Test failures: xdly (test emulator), flexlevel, slice (fixed in the test, see NEXT).
  - Found on hardware in v0.53.9b, not fixed in this build: FLEX takes recorded from a track are
    silent (any track tried); MAIN works.

## v0.53.9b (15 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.53.8c
- **File:** DN2wishes_v0.53.9b.syx
- **SHA-256:** a3856bc1c6f1fea7f852f653f2c6f78d24005f960ebf6b7eaee385a16c03c926
- **Hardware:** Was installed 15 Nov 2026 (morning to afternoon). Ghost-delay test passed on hardware (XDLY and FDN8 switched off while ringing, back on: silence).

**Changes**

  - Stock chorus: no leftover sound when switching the chorus from JUNO back to STOCK.

**Known issues**

  - Test failures: thres, slice, sharc:smp, flexlevel, xdly, VO-6 retrigger (2 tests),
    inserts/ping (1 test; the test was out of date, fixed for the next build).
  - Found on hardware: FLEX takes recorded from a track are silent (any track tried); MAIN works.

## v0.53.9 (15 Nov 2026)

- **Status:** Withdrawn. Do not install.
- **Based on:** v0.53.8c
- **File:** autobuild-rebase/out/v0.53-r9/ours-1.12.syx
- **SHA-256:** b60a734ddffa077572c0b7a9a963f2d2ed4587b4a9a01412a0e5bc351fc083a9
- **Hardware:** Not yet tested on hardware.

**Changes**

  - Stock chorus leftover-sound fix (first attempt).

**Known issues**

  - The fix also erased the stock chorus's own settings. Replaced by v0.53.9b.

## v0.53.8c (15 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.53.7
- **File:** DN2wishes_v0.53.8c.syx
- **SHA-256:** 8e37f0b7b9769cfec37b51940beddb6be3a24a6c3b98181908463532736b020a
- **Hardware:** Not yet tested on hardware.

**Changes**

  - Seven new LFO waveforms.
  - LFO4 added, switched off.
  - Inserts and send effects no longer replay old delay or reverb tails when switched back on
    (the stock chorus is fixed in v0.53.9b).
  - CHOR, WIDE and JUNO inserts use less DSP time, with identical sound.

**Known issues**

  - Test failures: recorder, slice, thres, sharc:smp, VO-6 retrigger (2 tests), inserts/ping (1 test).

## v0.53.7 (14 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.52.5
- **File:** DN2wishes_v0.53.7.syx
- **SHA-256:** 5394163b367afa4c806da0ed77fff2e23fb119032e3f873a7c7ea296d86be38e
- **Hardware:** Not yet tested on hardware.

**Changes**

  - Based on upstream v0.53 (PAGES).
  - FLEX: the SYN page knobs now work.
  - Our machines now respond to note velocity (previously every note played at 100).
  - JUNO is 4 dB quieter, level with WaveTone.
  - The !CPU warning no longer lights while the unit loads or receives an OS update.
  - AMP page 1/3 is titled ENV1/AMP.
  - LIVE SELECT applies after 250 ms instead of 1.24 s.
  - PLAITS, Machinedrum and insert effects use less DSP time, with identical sound.

**Known issues**

  - Test failures: recorder, slice, thres, sharc:smp, VO-6 retrigger (2 tests),
    LFO4 (7 tests), inserts/ping (1 test).

## v0.52.5 (14 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.52.4
- **File:** DN2wishes_v0.52.5.syx
- **SHA-256:** 5d11f700cf436bae78fe0fd3acbc1182a77cf22aa4b8a3d14377d29538b3e92f
- **Hardware:** Was installed 14-15 Nov 2026.

**Changes**

  - Voice allocation keeps DSP headroom free for the safety guard.
  - Notes in their release phase are stolen sooner when voices run out.

**Known issues**

  - Test failures: 16 steps and 26 unit tests (same as v0.52.4).
  - Found on hardware: Machinedrum and Monomachine notes ignore velocity (fixed in v0.53.7).
  - Found on hardware: FLEX SYN page knobs have no effect (fixed in v0.53.7).
  - Found on hardware: JUNO 4-note chords clip the main output.
  - Found on hardware: DRONE plays about 7-12 dB below the rest of the pattern.

## v0.52.4 (13 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.48.14b
- **File:** DN2wishes_v0.52.4.syx
- **SHA-256:** f4b4a247c93a413ece64ad8b65c9da6dc485c1124d683b81b226de4906b22af3
- **Hardware:** Not yet tested on hardware.

**Changes**

  - Based on upstream v0.49 to v0.52 (FLEX replaces BOUNCE).
  - JUNO no longer piles up voices on long releases.
  - TB-303 2x oversampling on.

**Known issues**

  - Test failures: 16 steps and 26 unit tests.

## v0.52.3 (13 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.48.14b
- **File:** DN2wishes_v0.52.3.syx
- **SHA-256:** 65e28be70c0ac449c35045cfa761f5fa255333a046672fda9bc16e9953fc7641
- **Hardware:** Never installed.

**Changes**

  - Superseded by v0.52.4.

## v0.48.14b (13 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.48.14
- **File:** DN2wishes_v0.48.14b.syx
- **SHA-256:** a83f09df17358600b659e384f099f043d49a40c517a34a18df329199a54f411c
- **Hardware:** Installed 13-14 Nov 2026.

**Changes**

  - v0.48.14 with the stock effect memory move switched off.

**Known issues**

  - Found on hardware: JUNO piles up to 12 voices; every other voice glitches (fixed in v0.52.4).

## v0.48.14 (13 Nov 2026)

- **Status:** Withdrawn. Do not install.
- **Based on:** v0.48.13
- **File:** DN2wishes_v0.48.14.syx
- **SHA-256:** aa5dbd2ff76bc61c25f136df11f3b99f00eab92de2ac463c68ce4b7e36a6f0a9
- **Hardware:** Installed 13 Nov 2026: silent.

**Changes**

  - Stock effect memory move.

**Known issues**

  - No sound at all on hardware.

## v0.48.13 (13 Nov 2026)

- **Status:** Withdrawn. Do not install.
- **Based on:** v0.48.12
- **File:** DN2wishes_v0.48.13.syx
- **SHA-256:** bc14136189be297c62673c31cff76dcd9bcd2c59327cce9ad02e4b451063d06b
- **Hardware:** Never installed.

**Changes**

  - Contains the same stock effect memory move as v0.48.14.

**Known issues**

  - Same fault as v0.48.14.

## v0.48.12 (12 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.48.11f
- **File:** DN2wishes_v0.48.12.syx
- **SHA-256:** 78f8580d57af36b54cfd9d9ed3cf260173bd61082cf3645b17bba29f26851ca4
- **Hardware:** Never installed.

**Changes**

  - Superseded by v0.48.14b.

## v0.48.11f (12 Nov 2026)

- **Status:** Not released. The automated test suite reports failures (listed below). Do not install.
- **Based on:** v0.48
- **File:** DN2wishes_v0.48.11f.syx
- **SHA-256:** bfbee9b8bf698f9d407719484f889c14cf9d55cb53643a125ef921d2e08c14dd
- **Hardware:** Installed 12-13 Nov 2026.

**Changes**

  - Superseded by v0.48.14b.
