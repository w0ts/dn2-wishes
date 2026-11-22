# DN2 WISHES — CHANGELOG — Digitone II (all builds are based on OS 1.12)

## v0.69.2-fdn8lite2 (22 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.69.2-fdn8lite
- **File:** DN2wishes_v0.69.2-fdn8lite2_76e48431_TEST.syx
- **SHA-256:** 76e48431743345f174f916181a0587e559f92cf5c5b69e506c772bd4364fa1c6
- **Hardware:** Not installed.

**Changes**

  - The insert guard charges a bus FDN8 18,500 a block, its cost measured on the unit (about 17.8-18.4k,
    v0.69.2-fdn8lite's ladder) plus a small margin; it charged 15,200, the emulator's figure. The guard
    admits a bus FDN8 only when that cost still fits before the deadline. The sound is unchanged.

**Known issues**

  - With many bus FDN8 playing, fewer may be admitted at once than on v0.69.2-fdn8lite (not yet measured
    on the unit).

## v0.69.2-fdn8lite (22 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.69.2
- **File:** DN2wishes_v0.69.2-fdn8lite_0cd88167_TEST.syx
- **SHA-256:** 0cd88167c301725269bb13850a6fe14ac34d164817ba7462b64b1e5ea2a4163c
- **Hardware:** Installed on the unit 22 Nov 2026. The FDN8 ladder (INSERT 1 = FDN8 MIX 100 on T1..T8, chords
  waking the stock voices, the system meter's D per rung): D 75.1 % with none playing, 77.8 / 80.4 / 83.1 % with
  1 / 2 / 3, then 84.4 % and 4 insert skips a block from 4 to 8: one playing bus FDN8 costs about 17.8-18.4k cycles a
  block (was about 22-24k), and 4 run at once (was 2-3).

**Changes**

  - The FDN8 INSERT on a track's bus runs HALF, the User's pick from the A/B: the reverb's tank at 24 kHz,
    two input diffusers instead of four, the same eight lines, delay times and decay time. The wet's top is
    about 9 kHz (the first second of the tail a little darker on bright hits).
  - The SEND reverb (TYPE FDN8 / LONG on the Reverb page) is unchanged, bit for bit as v0.69.2.
  - XDLY's code moved to another place in the DSP's memory; it plays as before.

**Known issues**

  - The insert guard still charges a bus FDN8 15,200 (the emulator's figure), under its cost on the unit
    measured above; fixed in v0.69.2-fdn8lite2.
  - The sound at the DN2's levels: no listening check recorded on this file.

## v0.69.2 (22 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.69.1
- **File:** DN2wishes_v0.69.2_bcb44e39_TEST.syx
- **SHA-256:** bcb44e3945cb0cc79bb1e56f73240ca11d10d199cdfb676acc6a23c45de39397
- **Hardware:** Not installed.

**Changes**

  - Our data on the +Drive moves out of the places upstream's firmware uses, and upstream's own
    features go back to upstream's places. The first power-on copies each one once; nothing is lost
    and the old places are only read:
      - the tunings to upstream's tunings place (projects' tunings are now where upstream keeps them);
      - the bank lists B..D back to upstream's places;
      - the wishes record to a bigger table: 92,160 records (was 59,392);
      - SAFE MODE's record and the DSP program's copy to places of ours (at the first boot itself).
  - None of this changes a sound or a page.

**Known issues**

  - The first power-on after flashing does the copies: a few seconds more before the bank lists
    and the tunings are read (not measured on the unit).
  - Checked in the emulator only, not yet on the unit.

## v0.69.1 (22 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.5, moved onto upstream v0.68 (ICONS) and v0.69 (PERFORM)
- **File:** DN2wishes_v0.69.1_440085e4_TEST.syx
- **SHA-256:** 440085e4a4826fb3e11184c9871125922fcdcd0b9823ac2c14987c4c8c39eec5
- **Hardware:** Not installed.

**Changes**

  - From upstream v0.69: PERFORM. Hold [MOD] and press [FX]: eight macros A-H, each moving up to five
    parameters on any tracks by its own depth, added on top of the sound, its LFOs and p-locks. Push a
    knob for MODULATION SETUP; FUNC + YES is PERF MUTE; saved with the project.
  - From upstream v0.68: MACHINE SEL icons. Upstream's machines show the owner's icons, drawn small for our
    two-column MACHINE SEL: MACHINEDRUM, MONOMACHINE, FM+ STAT, PAR and DYN, the six sample machines and
    BOUNCE. Our own machines and the stock machines keep their icons.
  - From upstream v0.68: FLEX takes 12 dB louder. A take of a track at GAIN 0 plays +24 dB over the old
    unity (was +12), a take of MAIN or IN +24 dB (was +12). A track's take is still stored 18 dB lower
    until it plays, so a loud track has 18 dB more room before its take clips than on upstream's
    firmware (on the SHARC runner, the loudest test sound's take peaks 9 dB under the clip).
  - The inserts of every project move to another place on the +Drive, so they no longer sit where
    PERFORM keeps its macros. The first power-on copies them once; old projects keep their inserts.
  - Not taken from upstream v0.69: the DSP limit in MACHINE SEL. VOICE BUDGET stays: it prices every
    note, and knows our machines, the filters, the inserts and PARA.
  - VOICE BUDGET prices the A2 filter types (SVF, LADR, OTA, DIOD, MS20) per filtered voice (they were
    priced about 4 times too low).

**Known issues**

  - A MAIN or IN take saved as a sample plays 24 dB quieter than it did live (as upstream).
  - The FLEX levels are measured on the SHARC runner only, not yet on the unit.
  - PERFORM, the inserts' move and the icons are checked in the emulator only, not yet on the unit.
  - ERASE PROJECT does not clear the macros (as upstream).
  - Turning a macro is not recorded into patterns yet (as upstream).
  - The gate's flexplay check (a FLEX buffer played by a ONESHOT note, both processors) fails its pitch check, as
    the known feature issue it has been since v0.56 (not blocking).

## v0.67.5 (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.4-outs
- **File:** DN2wishes_v0.67.5_06aa7488_TEST.syx
- **SHA-256:** 06aa7488ca79e60ee72cd960d200ad5d570de76776dd689b86acf7cc05ee36ec
- **Hardware:** Installed on the unit. The User's checks (22 Nov 2026): the inserts TAPE, FOLD, HARM and RING, the Machinedrum track effects and ANALOG 2 (DIOD and SVF LP24, DRV high) sound as on v0.67.4-outs, and the DSP load on a heavy pattern is lower: all work.

**Changes**

  - Nothing new to hear or see. The DSP spends less time on the changes below; each gives the same
    output and memory words as before (the model and the SHARC runner).
  - Inserts, 32 slots, worst of 5 knob settings: TAPE -9.7 %, FOLD -22.2 %, RING -24.5 %, HARM -10.5 %.
  - Machinedrum track effects (AM, EQ, HP, LP, all four on, any MD machine): 4,937 -> 2,598
    instructions a voice-block (-47 %).
  - ANALOG 2 at its worst (LP24, WAV2 SIN synced): DIOD 16,849 -> 16,254, SVF 16,625 -> 16,030.
  - EFM-CY at its worst: 20,033 -> 17,378.
  - Room: the DSP program has 5,587 bytes left of the 1 MiB upload.

**Known issues**

  - The costs are the model's figures; the unit's FUNC meter has not measured each one.
  - EFM-CY's change is proved in the model only; no runner step plays EFM-CY itself.
  - sharc:drum fails "every DRUM run sounds" on crash-reverse and crash-random (peak 0.0004 in its
    16 ms window; the DSP is bit-exact to the model). The same since DRUM stage 4 (v0.66.1's source).
  - SAFE MODE's Transfer is not measured on the unit. The MIDI arp is not tested on our unit.

## v0.67.4-outs (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.3
- **File:** DN2wishes_v0.67.4-outs_7ca78321_TEST.syx
- **SHA-256:** 7ca783216d3e598b495fabc8b7b83f2d4aab9a16b67b6b28ade3eb71a895a9a0
- **Hardware:** Installed on the unit. The User's checks (22 Nov 2026): the OUTPUTS overview in Overbridge, USB audio and USB MIDI modes, a track's and the analog output's clip marks, the REC and IN bars while recording: all work.

**Changes**

  - The MIXER overview is replaced by the OUTPUTS overview (FUNC + hold [MOD] 1 s, the same keys). It
    shows only the places where audio can really clip (the fixed-point outputs): 25 bars, each 48 dB
    with its top at that output's own full scale, and a peak tick for the last 3 s. TRK 1-16 (each
    track's Overbridge / USB channel), FX D R C (the send returns' channels), OB L R (Overbridge / USB
    main), OUT L R (the analog outputs and headphones), IN (the input) and REC (the recorder, while it
    records).
  - A dotted bar: that output is not in use (the tracks, returns and OB live in Overbridge mode; in USB
    audio mode only the USB OUT pair; REC only while recording; OUT and IN always).
  - A block above a bar: that output clipped while in use (it stays until the overview has been up
    2 s); its group name turns white on black and the title names it, e.g. "CLIP 5 R OUT".
  - A voice's own clips (engines, inserts, XDLY) are not on this page. The CLIP title label and the
    MIXER pages' "!" are unchanged.
  - DSP: the recorder's level is sent to the ColdFire (our code only; no stock DSP code changed).

**Known issues**

  - One clip mark per pair (a track's L and R, the main's, the analog outputs', the input's): a mark
    cannot say which side.
  - The input's Overbridge channels use the input converter's clip test, not a test of the Overbridge
    words (the same if the input reaches Overbridge at unity: inferred, not measured).
  - As v0.67.3: SAFE MODE's Transfer not measured on the unit; MIDI arp not tested on our unit;
    sharc:drum's crash-reverse / crash-random window fails.

## v0.67.3 (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.2
- **File:** DN2wishes_v0.67.3_b9705c59_TEST.syx
- **SHA-256:** b9705c5911cbaf1afa21cdb5a00b88ce3da36487a4b0c261464440bdc7bc4257
- **Hardware:** Installed on the unit. The User's checks (22 Nov 2026): the MIXER overview, [TEMPO] and [PRESET] held a second, and FM+, VO-6, DPRO-DENS / DDRW, SOPHIE and PLAITS-STRG sounding as on v0.67.2: all work.

**Changes**

  - Engines faster, bit-exact (each engine's output and state words identical over its sweep), in
    instructions a voice-block at their worst: FM+ PAR 19,344 -> 15,888 (-18 %), FM+ STAT 13,498 ->
    11,434, FM+ DYN 13,540 -> 11,476; VO-6 25,518 -> 22,544 (-11.7 %); DPRO-DENS 19,904 -> 19,454,
    DPRO-DDRW 12,136 -> 11,956; SOPHIE KICK 16,057 -> 15,577; PLAITS STRG 19,051 -> 18,827. The
    VOICE BUDGET's cost table is regenerated with them.
  - MIXER overview: FUNC + hold [MOD] 1 s shows all 16 tracks, the 3 send returns and the main L R,
    live (10 times a second, 48 dB); let go: the screen you were on. A tap still opens stock's MIXER,
    on the release.
  - [TEMPO] held 1 s: the big CPU / RAM meter while held (a tap: stock's TEMPO). [PRESET] held 1 s:
    the sample browser for the active track (browse only on a track with no sample machine; a tap:
    stock's). The old FUNC tap-then-hold gesture for the meter is gone: FUNC is stock's again.

**Known issues**

  - SAFE MODE's Transfer is not measured on the unit.
  - The MIDI arp is not tested on our unit; HOLD with the arp on a MIDI track untried.
  - sharc:drum fails on crash-reverse and crash-random (see v0.67.1).

## v0.67.2 (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.1
- **File:** DN2wishes_v0.67.2_623fb5bb_TEST.syx
- **SHA-256:** 623fb5bb8b0459713a746a5275b6b1b1bb19a18526402d6b0e454454b798db6f
- **Hardware:** Not recorded.

**Changes**

  - SAFE MODE: if the firmware stops the DN2 from starting (a crash or freeze
    before the UI has run 30 s), the next start comes up in SAFE MODE: stock OS 1.12's own ColdFire
    code, byte for byte, no DSP program (no sound), an empty project. A fixed firmware can then be
    sent with Elektron Transfer over USB (about 1 min) instead of the Early Start-up Menu over DIN MIDI
    (about 12 min, still the last resort).
  - STOP held alone for 1 s within the first ~3 s after power-on also enters it; a STOP tap does
    nothing special; FUNC + STOP (stock's maintenance combination) does not enter it. The question
    is on stock's own window: LAST START FAILED (or STOP HELD AT START), START SAFE MODE? Y/N. YES:
    SAFE MODE stays. NO: one normal start.
  - Power cycles while starts keep failing come back to SAFE MODE until 2 tries are spent, then a
    normal start. A newly flashed build starts from a fresh record. Nothing is written to the +Drive
    in SAFE MODE.
  - The route probe is taken out (its job is done); routes are 12 bytes, as v0.67.1 A.

**Known issues**

  - SAFE MODE's Transfer is not measured on the unit (the emulator's update chunks pass; the whole
    file and the "UPGRADE OS NOW?" question after the last chunk are not).
  - An earlier v0.67.2 build (7a1031fc) entered SAFE MODE on a single STOP tap. It was withdrawn
    before delivery; this file needs the 1 s hold.
  - The MIDI arp is not tested on our unit; HOLD with the arp on a MIDI track untried.

## v0.67.1-route8 (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.1 (variant B of a CPU A/B)
- **File:** DN2wishes_v0.67.1-route8_c7f8ee21_TEST.syx
- **SHA-256:** c7f8ee218fcb857763c19b8d558d44455e38559582a200315dd6d51286a7c57e
- **Hardware:** Installed on the unit 21 Nov 2026. CPU profile on the unit (the same pattern playing, read only): the route evaluation (mx_probe + mx_eval) 12.59 -> 10.41 % of the CPU (-2.18) against v0.67.1 A, but the whole meter +0.61 % of the CPU, from audio_isr (cause not measured). A ran on the LFO page, B on the compressor page.

**Changes**

  - v0.67.1 with 8-byte routes: a route in 8 bytes instead of 12 (a voice's table 220 bytes, 14
    cache lines instead of 20; 4 more instructions a route). The emulator proves every frame
    byte-identical to the 12-byte build.

**Known issues**

  - The A/B ran on two different pages, so the net result is not settled. v0.67.2 keeps the 12-byte
    routes.
  - Only the route-table feature steps ran on this file; the SHARC steps ran on v0.67.1 A.

## v0.67.1-keys (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.1 without the route probe
- **File:** DN2wishes_v0.67.1-keys_0f8c8533_TEST.syx
- **SHA-256:** 0f8c8533e98523112e4a35d6b391a1037a94353657c515a6ea8cebb5ac94530c
- **Hardware:** Not recorded.

**Changes**

  - The MIXER overview of v0.67.1-mixovw.
  - [TEMPO] held 1 s: the big system meter (DSP, CPU, RAM) while held; a tap still opens the TEMPO
    screen; FUNC + [TEMPO] is still tap tempo. The old "tap FUNC then hold it" gesture shows nothing
    now.
  - [PRESET] held 1 s: the sample browser for the active track; it stays up after the release. On a
    track with no sample machine it only browses (no LOAD TO TRK). A tap is still the PRESET / KIT
    menu; FUNC + [PRESET] is still PERFORM KIT.

**Known issues**

  - Supersedes v0.67.1-mixovw. Its keys are in v0.67.3.
  - The overviews step fails at its VOICE part; the base build fails the same check (not this
    change).

## v0.67.1-mixovw (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.1 without the route probe
- **File:** DN2wishes_v0.67.1-mixovw_81b7e522_TEST.syx
- **SHA-256:** 81b7e522cca54f7a62bf14e4ef3d0a58b85935aa0ff34c50617d679085af76ce
- **Hardware:** Not recorded.

**Changes**

  - MIXER overview: FUNC + hold [MOD] 1 s shows every channel's live level at once (tracks 1-16, the
    send returns D R C, the main L R; bars of 38 px over 48 dB, a peak tick of the last 3 s, a clip
    block above a bar until seen 2 s, CLIP in the title while a clip is recent). 10 updates a second.
    Let go: the screen you were on.
  - A short FUNC + [MOD] still opens or steps stock's MIXER, on the release (stock: on the press).
    Stock's value view while FUNC + [MOD] is held is gone.
  - Measured in the emulator: +0.56 % of the CPU while the overview is up with every bar moving;
    nothing when it is closed.

**Known issues**

  - Superseded by v0.67.1-keys.
  - The overviews step fails at its VOICE part; the base build fails the same check (not this
    change).

## v0.67.1-fdn8dma (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.1 without the route probe (B side of the FDN8 DMA A/B; A is v0.67.1-fdn8off)
- **File:** DN2wishes_v0.67.1-fdn8dma_88835a74_TEST.syx
- **SHA-256:** 88835a7407d64592b6f9211b068f510c483989d199e63edd8f9adcf11c7cafdf
- **Hardware:** Installed on the unit 22 Nov 2026, after A. The DSP load measured on the unit was 2.5 to 3 % of the DSP higher than A's, so the pilot is dropped. PLAITS MDAL (its mode pairs on the DSP's second processing element) played on the chip on this file; its sound is not yet checked by ear.

**Changes**

  - A pilot: FDN8 (the send reverb and the 8 bus FDN8 instances) reads its 8 delay lines' windows from
    L1 instead of DDR. Every block, MDMA0 (a memory-to-memory DMA that stock 1.12 never programs,
    measured with v0.66.2-mdmaprobe) copies the 264 words the lines read in that block from the
    instance's DDR ring to L1. If the copy is not complete when it is read, the block reads the ring
    as before. The output is the same either way.
  - The FDN8 rings are made write-through ranges of the DSP's data cache, so every DSP write to a
    ring reaches DDR before the DMA reads it.

**Known issues**

  - Dropped: slower on the unit, as measured above. The emulator's estimate (about 2 to 2.5 % of the
    DSP saved) could not include the write-through ranges' cost (the emulator has no cache); why the
    unit is slower is not measured.

## v0.67.1-fdn8off (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.67.1 without the route probe (A side of the FDN8 DMA A/B)
- **File:** DN2wishes_v0.67.1-fdn8off_ce8c74b5_TEST.syx
- **SHA-256:** ce8c74b5c6bbb3f2539173e088843fdb38ecfd06e852a4543fbe909573e07b5e
- **Hardware:** Installed on the unit 22 Nov 2026 for the FDN8 DMA A/B (see v0.67.1-fdn8dma).

**Changes**

  - The v0.67.1 source with every build switch off (no route probe): the FDN8 DMA pilot's code is not
    placed. Byte-identical to that source's own build.

**Known issues**

  - None of its own.

## v0.67.1 (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.66.1, moved onto upstream v0.67 (MIDIARP) (variant A of a CPU A/B; B is v0.67.1-route8)
- **File:** DN2wishes_v0.67.1_9cd23a57_TEST.syx
- **SHA-256:** 9cd23a577186d924b9982cf63e7643b46987310180908004c51b4e2f0be80a9e
- **Hardware:** Installed on the unit 21 Nov 2026; CPU profile on the unit for the A/B (see v0.67.1-route8).

**Changes**

  - From upstream v0.67: the ARPEGGIATOR menu opens on a MIDI track. With the arp on, the track's
    notes (keys and sequencer trigs) go through the arp and out over MIDI, one note per arp step, its
    length N.LEN (INF sent as the longest finite length). Arp off: stock MIDI. Synth tracks unchanged.
    (Angel Linares's work.)
  - ANALOG 2 sounds different, by the User's picks: SQR from one BLEP, DRV a one-sided tanh of degree
    4, the WDTH side through a linear SVF at 0.97 of its level, trimmed at low RES (LADR, OTA, DIOD).
    On the full peak grid never louder than before.
  - MOD SETUP rows editable: in the routes popup, VEL MW PB AT BC KEY edit stock's own MOD SETUP
    entries (turn = depth, YES adds or unmutes, NO mutes, NO held or FUNC + NO deletes; NOT IN SETUP
    where stock's list does not offer the knob; /V per voice, /T per track).
  - DIST's onset from the block's own peak, with no fade-in.
  - The FX title icon stays while the page name is up.
  - Matrix: a conversion goes live with its track's table in one step; a copy, carry or clear that
    finds the wishes table locked is queued, never dropped.
  - PARA's costs measured as one voice; the VOICE BUDGET prices a chord's slot by its notes.
  - Faster, the same sound (bit-exact): PERC's constants read from a pool (-6,424 bytes of DSP
    program), the MD / PERC voice resampler, ANALOG 2 / JUNO / the A2 filters, our FX at their worst
    frame (FDN8, the inserts, XDLY, JSEND; the bus FDN8's diffusers moved to L2), and the ColdFire's
    hot paths in assembly.
  - A route probe (this file only): it reads each voice's route table once before the matrix runs, so
    the CPU profile shows what the table's cache-line fills cost. It costs about 767 instructions a
    frame and exists only to measure.

**Known issues**

  - SAFE MODE is not in this file (the User: "leave it for later"); it comes in v0.67.2.
  - The MIDI arp is not tested on our unit (upstream's only); HOLD with the arp on a MIDI track
    untried.
  - sharc:drum (a feature step) fails "every DRUM run sounds" on crash-reverse and crash-random: a
    crash with a slow attack has not swelled yet in the step's 16 ms. The DSP is bit-exact to the
    model; the same on v0.66.1's source.
  - Unit test test_apopt fails: the committed apopt.wasm is not rebuilt byte for byte by any clang
    here. Not firmware.

## v0.66.2-mdmaprobe (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.66.1
- **File:** DN2wishes_v0.66.2-mdmaprobe_e074bd70_TEST.syx
- **SHA-256:** e074bd7023418caee8f2e66ba91554a3b5d3ee457a253518c7c0d9042cd8e919
- **Hardware:** Installed on the unit 21 Nov 2026. Read on the unit (a 6-minute and a more than 1-hour reading): stock 1.12 never programs MDMA0 and MDMA1, so they are free for our use.

**Changes**

  - v0.66.1 plus a read-only probe that shows which DSP DMA channels stock 1.12 uses while the DN2
    plays. Every 16th idle packet on the link to the ColdFire carries the registers of one pair of
    channels (12 pairs: SPORTs, SPIs, link ports, MDMA0-3); the DSP only reads them. Sound
    bit-identical to stock (sharc:stockout passed).
  - Claude reads it through the test channel.

**Known issues**

  - The ColdFire's play positions, DSP load and insert telemetry come 1/16 less often.
  - SPI0 and SPORT5-7 are not probed.

## v0.66.1 (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.65.1 with every feature merged since, moved onto upstream v0.66 (NXT)
- **File:** DN2wishes_v0.66.1_934b798b_TEST.syx
- **SHA-256:** 934b798b9c94bc66e813d888e4c4b7c7d2ce655f8af5a154b8d60654b0f494b6
- **Hardware:** Installed on the unit 21 Nov 2026.

**Changes**

  - From upstream v0.66: a slide lasts until the track's next trig (NXT, SLEN's first choice and
    what a slide trig gets with no SLEN). Slide trigs with no SLEN used to last 1 step: projects with
    plain slide trigs sound different. FM+ DYN: FUNC + turn on 1FRQ and 2FRQ jumps to whole ratios.
    FLEX takes of MAIN and IN are recorded as they come in and played back 12 dB up.
  - FLEX level: a take of a single track now plays at upstream v0.65's level (the User's choice),
    5.86 dB under v0.65.1's.
  - The combined v0.66 file, with everything of v0.65.1 and: ENV2 routes; the MIXER CPU work; the
    ghost-audit fixes; a plain knob push opens the routes popup; CLIP for the engines' own clips; the
    moving line on p-locks; note-start knobs live (SOPHIE DCAY, TB-303 DEC, JUNO RES, DRONE GLID and
    GLTY).
  - No limiter, levels instead: DRONE's and ANALOG 2's output knees are gone; TB-303 -4.5 dB, ANALOG 2
    -4.0, JUNO -3.0, DRONE -2.0; DPRO-DDRW's MIX gain 1.5 (its level made up after the machine).
  - DRUM: balance knobs (KICK CLIK, SNARE / TOM / hats NOIS, CLAP TAIL, cymbal BELL), CURV on KICK, no
    type reaches the soft clip's flat top, and every coefficient knob follows modulation and p-locks
    while a hit rings.
  - AMP ON/OFF on DRUM, MACHINEDRUM, SOPHIE and PLAITS' BD / SD / HH: on stock's AMP page, H is AMP
    ON/OFF, OFF by default (the drum's own decays are the hit). Stored per sound; old sounds read OFF.
  - Insert p-locks and modulation: each track's 14 insert knobs can be p-locked and are matrix
    destinations (all tracks updated 187.5 times a second).
  - INSERT SEL (push A on an INSERT page) with the FX icons; the item's icon in the title bar. The
    icon art is a placeholder.
  - CPU and DSP savings, nothing you hear changes; the VOICE BUDGET reads the right cost for every
    machine (JUNO read a MACHINEDRUM cost, the DRUM types read 0).

**Known issues**

  - Upstream v0.66's own: a MAIN or IN take saved as a sample plays 12 dB quieter than it did live;
    micro timing and trig conditions are not counted for NXT.
  - The first build (dc5839c6) failed the DSP hardware rules (AMP ON/OFF's hook stored a DAG register
    through its own DAG) and was never delivered; fixed in this file.
  - DSP program room: 553 bytes left of the 1 MiB upload. USB upgrade: 75,738 bytes free.
  - v0.65.1's known issues stand.

## v0.65.1 (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.64.1 with ENV2 routes, moved onto upstream v0.65 (BANKS)
- **File:** DN2wishes_v0.65.1_9b89e2b9_TEST.syx
- **SHA-256:** 9b89e2b956855019a9f48fce8bbc5b8797ceeb77f5aa5b668d361248199d87c2
- **Hardware:** Not recorded.

**Changes**

  - From upstream v0.65: PROJECT RAM in four banks A-D (508 slots, then the FLEX buffers). Turn SAMP
    past A127 to go on to B001; FUNC + UP / DOWN in the sample list jumps a bank; SAMP's box and the
    list show the bank letter; LOAD TO PROJECT fills the first empty slot from the track's bank on;
    p-locks, sounds and kits keep the bank. Old projects are bank A.
  - The firmware is packed tighter: the USB upgrade has 85,737 bytes free (v0.64.1: 14,229).
  - FLEX level: ours kept (GAIN 0 plays a track's take at its source's level); upstream's new number
    is not taken.
  - The bank lists are kept at other +Drive sectors and RAM addresses than upstream's, because
    upstream's are ours.

**Known issues**

  - Bank lists made by upstream's v0.65 firmware are not read by Wishes; bank A is the same on both.
  - The recorder records into bank A only (upstream's).
  - None of the features from the other branches is in this file (they are merged next).

## v0.64.3 (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.64.1
- **File:** DN2wishes_v0.64.3_9e190d03_TEST.syx
- **SHA-256:** 9e190d03890d2395df828fbdf435f4aae84a5c4d3512242ede07b04397854895
- **Hardware:** Not recorded.

**Changes**

  - The combined v0.64 file: v0.64.1 plus ENV2 routes, the MIXER CPU work (v0.62.7-mixcpu), the
    ghost-audit fixes (v0.62.7-ghost), the plain knob push, and CLIP for the engines' own clips
    (v0.62.7-clip).
  - The DSP's sample-machine code is 966 bytes smaller (the recorder's ARM start was three copies of
    the same code).

**Known issues**

  - DPRO-DDRW lights CLIP at its defaults.
  - The ghost delay's cause is not found.
  - Feature steps were not run to the end.

## v0.64.1-liveknobs (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.64.1 with ENV2 routes
- **File:** DN2wishes_v0.64.1-liveknobs_9771ba9d_TEST.syx
- **SHA-256:** 9771ba9d1d5651df008708226b67bdeddf0aa15e2a59b8e12f9864fba4739b71
- **Hardware:** Not recorded.

**Changes**

  - Knobs that were read only when a note starts now follow LFOs, routes, p-locks and hand turns
    while the note rings: SOPHIE DCAY, TB-303 DEC, JUNO RES with every wave off, DRONE GLID and
    GLTY. Each voice re-reads them every 10.7 ms. Knobs not moved: bit-identical to v0.64.1.

**Known issues**

  - DRUM's knobs are a separate build that does not fit the DSP upload yet.
  - Not verified on the unit.

## v0.64.1-line-locks (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.64.1 with ENV2 routes
- **File:** DN2wishes_v0.64.1-line-locks_7c1be370_TEST.syx
- **SHA-256:** 7c1be3702a1fa6a315ac6f17847353678b2f6ebdc177e3b02e3648d3c92b1949
- **Hardware:** Not recorded.

**Changes**

  - P-locks show with the moving line: a step with a p-lock draws the line at the locked value while
    the knob and its number stay at the sound's value. Also for parameter slides and sound locks.
  - PER NOTE in the routes popup's header on controls read only when a note starts (TB-303 ACC and
    SLID, DRONE HOLD, DRUM's TYPE, a sample machine's SAMP and BUF, ...).
  - ENV2's MODE, RSET and H are destinations of routes; ENV2's HOLD can be p-locked.

**Known issues**

  - Not verified on the unit.

## v0.64.1 (20 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.6, moved onto upstream v0.63 and v0.64
- **File:** DN2wishes_v0.64.1_4d89996b_TEST.syx
- **SHA-256:** 4d89996b0edb513860dc616c16a590aeb88e2f44c883eb32f158e697ed26a03f
- **Hardware:** Not recorded.

**Changes**

  - From upstream v0.64: keyboard HOLD. PTN + KEYBOARD turns HOLD on or off (the screen says KB HOLD
    ON / OFF while PTN is held). It is stock's sustain pedal on all 16 tracks. Works with trig keys,
    MIDI in, chords, the arp and microtuning.
  - A note held by HOLD (or a MIDI sustain pedal) is never taken by another track's note nor stolen
    by the VOICE BUDGET (ours, same rule as DRONE HOLD).
  - From upstream v0.63: saving a FLEX buffer never normalises; a saved take carries our headroom
    mark so its slot plays at the buffer's level.
  - FLEX level: ours kept (GAIN 0 plays a track's take at its source's level); upstream's +24 dB is
    not taken.

**Known issues**

  - PTN + KEYBOARD no longer switches KEYBOARD mode (upstream's choice).
  - Only the checks that guard against bricking had finished when this file was made.

## v0.62.7-mixcpu (20 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.6
- **File:** DN2wishes_v0.62.7-mixcpu_aacf178c_TEST.syx
- **SHA-256:** aacf178cded438f7965258fdca1291c3e507be50f9312c93ccd2bc6994ea8ef5
- **Hardware:** Not recorded.

**Changes**

  - MIXER pages use less CPU (on the unit: 68 % on a SYN page, 75 % on Internal Mixer 2/5): the
    meters are drawn a column at a time (34,000 -> 5,200 instructions a draw), stock's full redraws
    of the MIXER pages are held to 10 a second, and Overbridge / USB main's peaks are measured by
    the DSP (that was 1.56 % of the CPU in Overbridge mode).

**Known issues**

  - The release check's SHARC test for the Overbridge peak code failed on a status flag (fixed on
    the branch, not in this file).
  - Superseded by v0.64.3.

## v0.62.7-ghost (20 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.6
- **File:** DN2wishes_v0.62.7-ghost_c8ee5265_TEST.syx
- **SHA-256:** c8ee526552b151e5184e08c8bbfd5976571865976a4fbb43d66e0e397f725824
- **Hardware:** Not recorded.

**Changes**

  - The sample link refuses packets aimed below the sample pool (such a packet wrote 124 words where
    stock's reverb and delay and our bus delays live). Nothing you can hear changes.
  - New checks that every DSP memory area is listed, and that output is the same with garbage in the
    delay areas.

**Known issues**

  - The cause of the delay that comes back long after playing is not found; one possible path is
    closed.

## v0.62.7-clip (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.6
- **File:** DN2wishes_v0.62.7-clip_145984a7_TEST.syx
- **SHA-256:** 145984a7b5aa0969f13252294422dbdfe288f5d31485af3da707f805c1a81093
- **Hardware:** Not recorded.

**Changes**

  - Every flat ceiling or protective limiter inside a voice, an insert or the send delay lights CLIP
    and the track's ! on the mixer pages (DRONE and ANALOG 2 knee, PLAITS, DRUM's drive, the
    Machinedrum and Monomachine limiter, PERC, the A2 filter models, the inserts, XDLY). Nothing you
    hear changes: it only reports.

**Known issues**

  - DPRO-DDRW lights CLIP at its defaults (it really sits on its limiter).

## v0.62.6 (20 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.5
- **File:** DN2wishes_v0.62.6_9d72c027_TEST.syx
- **SHA-256:** 9d72c02752a0f75e3b5ba976da761e7fa01ee99bc0574a0d8b766fa79f71416c
- **Hardware:** Not recorded.

**Changes**

  - One file for DRUM, the mixer meters and UP / DOWN pages (v0.62.5-drum, -mixmeter, -mixbang,
    -updown), plus three fixes.
  - DRUM: 55 presets (DRM 01..55) in the repo's presets folder (they need this firmware).
  - Clips count only where they matter: the analog outputs, the input, the recorder while recording;
    Overbridge's main in Overbridge mode; the USB OUT pair in USB audio mode. A track's own
    Overbridge channel never lights CLIP.
  - DSP and CLIP stay unlit while the unit starts (at boot they said !CLIP and !DSP).
  - MACHINE SEL without the divider lines: 24 machines on two screens.

**Known issues**

  - Not heard or seen on the unit: DRUM's sound and levels, the meters with real audio, the DAC fix,
    CLIP on a real clip.

## v0.62.5-plainpush (21 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.4 (before v0.62.6: no DRUM, no UP/DOWN pages)
- **File:** DN2wishes_v0.62.5-plainpush_3e5f8bd2_TEST.syx
- **SHA-256:** 3e5f8bd213707c6a895fa822a0f8760e03cfb33d4539cf0996978d7dd2c08608
- **Hardware:** Not recorded.

**Changes**

  - A plain push on a knob opens the routes popup on every machine's SYN pages, including FM TONE
    and all of ours (they found no parameter before).
  - The pushed knob may wobble: under 4 counts of its own turn while held are ignored; from 4 counts
    it is stock's push + turn.

**Known issues**

  - A project with DRUM tracks will not play them on this file.
  - Not verified on the unit.

## v0.62.5-drum (20 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.5
- **File:** DN2wishes_v0.62.5-drum_821fff7e_TEST.syx
- **SHA-256:** 821fff7eb33c3e01ee32a955a8c0c9bbf8307e43730e2b6f97dca3adab2106d7
- **Hardware:** Not recorded.

**Changes**

  - DRUM stage 3: TOM added (TUNE, DCAY, SWEP, TONE, SNAP, NOIS, DRIV; SWTM, MODE, SHAP, RNGE LOW /
    MID / HI, VEL). KICK: SWHD (sweep hold), SIGH follows the hit's level. SNAR: WCHR (909 band ..
    808 high-pass wires). Hats: TOP, DRFT, the 808's VCA, long OPEN hats wash from DCAY 80.
  - Picking Drum opens the track's AMP fully (also MACHINEDRUM, SOPHIE and PLAITS on BD/SD/HH).

**Known issues**

  - Sound, levels and CPU figures not checked on the unit.
  - DSP upload room: 2,457 bytes left.

## v0.62.5-updown (20 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.5
- **File:** DN2wishes_v0.62.5-updown_a2cd582b_TEST.syx
- **SHA-256:** a2cd582b6ba3a69804855141e8a6a22444cbbfd8006f4f9766ade3321c80d0b8
- **Hardware:** Not recorded.

**Changes**

  - UP and DOWN step pages on our AMP and FX pages as on stock's own pages: AMP ENV1/AMP <-> ENV2,
    FX 1/3 -> 2/3 -> 3/3. On a page 2 they step only among the page 2s.
  - Fix: the inserts' FUNC tap (page 2) is cancelled only by a key, push or turn.

**Known issues**

  - KEYBOARD and REC still close ENV2's page and the INSERT pages.

## v0.62.5-mixbang (20 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.5-mixmeter
- **File:** DN2wishes_v0.62.5-mixbang_7767a145_TEST.syx
- **SHA-256:** 7767a1458970151dada31a8985dd69bb750762a4b07586b60eedeba65be83ab8
- **Hardware:** Not recorded.

**Changes**

  - OUT meter in Overbridge mode: with Overbridge connected stock keeps the internal sound off the
    analog main, so the analog peaks were truly 0; OUT now shows Overbridge's main.
  - The clip latch is a ! in each track's left tick column on the mixer pages.

**Known issues**

  - OUT moving with Overbridge connected is not verified on the unit.

## v0.62.5-mixmeter (20 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.5
- **File:** DN2wishes_v0.62.5-mixmeter_b07394da_TEST.syx
- **SHA-256:** b07394da3d376a2af6f79c4ff38bc9bfadb9fd5e44eaf55bd6dc7b90d471982b
- **Hardware:** Not recorded.

**Changes**

  - Mixer meters (FUNC + MOD): each track's right tick column on Internal Mixer 2/5 and 3/5 is its
    meter (3 dB a row, a 3 s peak tick); meters beside DEL, REV, CHR and OUT on FX Mixer 4/5; IN LR
    on External Mixer 5/5.
  - CLIP in the title bar, lit 3 s after any real clip of an output in use.
  - The analog outputs' overs: stock turned every main-mix sample at or over full scale into about 0
    at the DAC (crackle, not clipping). Now a clean clip. Only those samples change.

**Known issues**

  - Not heard or seen with real audio (the emulator has none).

## v0.62.5 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.4
- **File:** DN2wishes_v0.62.5_dabd3360_TEST.syx
- **SHA-256:** dabd3360e90a3ca4d9a6a7fdc533503afa2129afecf8d663e25235099a160d5a
- **Hardware:** Not recorded.

**Changes**

  - Knob notches: every value with a centre (PAN, BAL, filter ENV, EQ GAIN, LFO SPD/FADE/DEP, TUNE,
    ...) has a virtual notch at its centre: a slow turn stops there, three more small moves go past
    it, a fast turn goes straight through. p-locks too. CC, NRPN, Overbridge, loads and the
    sequencer are never notched.
  - Our popups turn finer when slow and coarser when fast; a depth can always be turned back to
    exactly 0.
  - VOICE held a second: the voice overview. AUTO off on distortions, FUNC + long push resets an
    insert knob.
  - DRONE HOLD: a held voice is never stolen.
  - The screen shows the version as 0.62.5.

## v0.62.4-drum (20 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.4
- **File:** DN2wishes_v0.62.4-drum_58819132_TEST.syx
- **SHA-256:** 58819132676c81343d5e6e291fc69393c783a24863ef258fbe6732608c84bc09
- **Hardware:** Not recorded.

**Changes**

  - New machine DRUM (type 56, MACHINE SEL, below JUNO): one synth drum engine with a TYPE per drum
    (page 1 knob H, p-lockable): KICK, SNAR, CLHH, OPHH, TOM. Each has its own pages and start
    values. CLOSED hats choke OPEN hats of the same track.
  - KICK: TUNE, DCAY, SWEP, SWTM, SNAP, CLKT, DRIV; SHAP, HOLD, SIGH, CLKL, NOIS, VEL. SNAR: TUNE,
    DCAY, TONE, MODE, SNAP, NOIS, DRIV; WIRE, GLID, BUZZ, WTON, WATK, SIZZ, VEL. Hats: TUNE, DCAY,
    TONE, NOIS, COLR, SNAP, DRIV; HPF, Q, LOWB, VEL.

**Known issues**

  - TOM is not in this file (it plays KICK).
  - Stock's AMP envelope still shapes DRUM: open it by hand to hear the engine's decays.
  - Levels are not yet set against a real 808 / 909 kit.

## v0.62.4-dronehold (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.4
- **File:** DN2wishes_v0.62.4-dronehold_b8a264d2_TEST.syx
- **SHA-256:** b8a264d2512fe398780d6cb93a075e671199da7ef88e6ac8c0852b788a3100e5
- **Hardware:** Not recorded.

**Changes**

  - DRONE HOLD: a held DRONE note's voice is never taken by notes on other tracks (a kick used to
    kill the held drone), nor by the VOICE BUDGET's steals. If every voice another track could use
    is held, that note plays no voice.

**Known issues**

  - Not verified on the unit: the drone surviving a kick.
  - The DSP frame guard can still drop a drone voice when a frame has no room.

## v0.62.4 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.2
- **File:** DN2wishes_v0.62.4_e11da0a9_TEST.syx
- **SHA-256:** e11da0a97d5bfbda7ef42bd8af5c33d00ad24fc62f6ba13ccb337bd1487dc87f
- **Hardware:** Not recorded.

**Changes**

  - Everything of v0.62.3 (plain push, DEST jumps, big meter), the magenta VOICE key, and the RAM
    check fix.

**Known issues**

  - The parachord test (a JUNO level check) fails the same way on the main build (not from this
    build).

## v0.62.3 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.2
- **File:** DN2wishes_v0.62.3_9712cb0f_TEST.syx
- **SHA-256:** 9712cb0fe7344ea9df5e8c5107c84b8417e3eafb98db14af9f12e3d338673fc2
- **Hardware:** Not recorded.

**Changes**

  - A plain push of a sound knob (no FUNC), let go, opens the routes popup at the release, if
    nothing else happened while it was held. Stock's push gestures (value peek, push + NO reset,
    push + turn) are untouched. FUNC + push is stock's again everywhere.
  - DEST popup: FUNC + DOWN / UP jump by sections.
  - Big system meter (FUNC tapped, then pressed again and held).

## v0.62.2-voiceovw (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.2
- **File:** DN2wishes_v0.62.2-voiceovw_2c1c10ab_TEST.syx
- **SHA-256:** 2c1c10abfda79e3b6fb253af85a6b73b34f6db5c4eabbe72e67bf651e680b8e1
- **Hardware:** Not recorded.

**Changes**

  - Hold VOICE for a second: a full screen of the 16 tracks, three rows each: the machine, the voice
    mode (PAR = PARA ON, UNI = UNISON, MON = one fixed voice, PLY) and VOICES. A short press is
    stock's VOICE menu.

## v0.62.2-voiceled (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.2
- **File:** DN2wishes_v0.62.2-voiceled_c1eb3fbb_TEST.syx
- **SHA-256:** c1eb3fbbcf9ad03a7893f006f53bce6803c4591ef81484cca6efd5cdf7827cc4
- **Hardware:** Not recorded.

**Changes**

  - On a track whose PARA is ON, the VOICE key lights magenta (stock: teal with UNISON, grey
    otherwise; white with the VOICE menu open).

**Known issues**

  - Not checked on the unit: how the magenta looks.

## v0.62.2-ramcheck (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.2
- **File:** DN2wishes_v0.62.2-ramcheck_351d166a_TEST.syx
- **SHA-256:** 351d166ab22375ceb619a16e950ddc87c2437c68912486b9c4a81d449521e81b
- **Hardware:** Not recorded.

**Changes**

  - The power-on RAM check really runs now. The single check message was sent before the DSP
    listened, was lost, and every power-on said RAM check FAILED with only the first 128 MB loaded.
    Now the ColdFire sends it again every 0.1 s until the DSP answers.
  - Verdicts: passed (all 400 MB load), failed, or not answered; failed and not answered both keep
    the first 128 MB.

## v0.62.2-autooff (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.2 (main without v0.62.3 and v0.62.4)
- **File:** DN2wishes_v0.62.2-autooff_df227d9c_TEST.syx
- **SHA-256:** df227d9c86739b169bb099235313822f98b9200cb1696439ca4063a114cfc0a1
- **Hardware:** Not recorded.

**Changes**

  - AUTO is off whenever a distortion (DIST, FOLD, HARM, FUZZ, TAPE) is picked in an insert's M.SEL.
    Before, a slot remembered each type's AUTO. A saved project keeps its own AUTO.
  - On an INSERT page, FUNC + a knob B..G held 0.6 s resets that knob to its default (M.SEL and MIX
    are left alone). A quick FUNC + push no longer switches FUZZ's or TAPE's page.

## v0.62.2 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.62.1
- **File:** DN2wishes_v0.62.2_3d36aa1b_TEST.syx
- **SHA-256:** 3d36aa1b61569577844e8212fe8bbe630edaffd5468f9e494a70aa17ab5875e9
- **Hardware:** Not recorded.

**Changes**

  - v0.62.1 plus the DEP attenuverter of v0.60.5.

**Known issues**

  - Slides fail by 2 pixels in the emulator test since v0.60.1 (not a sound problem).
  - On the unit the power-on RAM check said FAILED every time (fixed in v0.62.2-ramcheck).

## v0.62.1 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.60.4, moved onto upstream v0.61 and v0.62
- **File:** DN2wishes_v0.62.1_13c04d98_TEST.syx
- **SHA-256:** 13c04d98d585797a5bf45aca7437bce84e73ae255bb512cdc4c6a14b17aed9fe
- **Hardware:** Not recorded.

**Changes**

  - From upstream v0.61: MICROTUNING. KB SETUP's H is TUNE; one tuning per project (12-TET, JUST
    MAJOR, JUST MINOR, PYTHAGOREAN, MEANTONE 1/4, WERCKMEISTER3, KIRNBERGER3, VALLOTTI, ARABIC RAST,
    POOLE ROD12, POOLE12 MIN, and USER 1..8), switched on per track. TUNING page (push H) and EDIT
    page (YES on a USER tuning). Saved with the project. Off unless chosen.
  - From upstream v0.62: the slice editor. Edits play at once, playing a slice selects it, zoom to
    128 frames, FUNC + E / FUNC + H snap to zero crossings; CREATE SLICE GRID FUNC + E jumps
    2/4/8/16/32/64.
  - The tunings' record sits in other +Drive sectors than upstream's, because upstream's are where
    our inserts are saved.
  - Cost: no tuning chosen about 0.03 % of the CPU; all 16 tracks tuned about 1.5 %.

**Known issues**

  - PARA chords take the first note's tuning offset for every note.
  - The DEP attenuverter (v0.60.5) is not in this file.
  - Upstream's own: the same note again on the same voice does not re-select its slice.

## v0.60.6-meterbig (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.60.4
- **File:** DN2wishes_v0.60.6-meterbig_09e11dfe_TEST.syx
- **SHA-256:** 09e11dfe57fe3b7624adfd90c69d56ca57ab128527e4eb5adf135cbecaa8dacf
- **Hardware:** Not recorded.

**Changes**

  - The system meter is bigger and appears only on a click and a half: tap FUNC, then within 0.35 s
    press FUNC again and hold it. A black box under the title bar shows D (DSP), C (ColdFire) and M
    (memory) with a large figure and a 90 px bar (a tick marks the peak of the last 3 s).
  - A plain FUNC hold now shows nothing (the old corner meter is gone). With the meter up, any other
    key, push or turn closes it and works as FUNC + that input.

**Known issues**

  - The DEP attenuverter (v0.60.5) is not in this file.

## v0.60.5 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.60.4
- **File:** DN2wishes_v0.60.5_f7cb1d4a_TEST.syx
- **SHA-256:** f7cb1d4a19032a92b07bbd167e9e3e30563dd19032acd28f5633f0c487a620c0
- **Hardware:** Not recorded.

**Changes**

  - LFO DEP is each LFO's attenuverter: every route of that LFO is heard at its own depth x DEP. DEP
    -64..+63 = -100..+100 % (negative inverts); +63 and above is exactly 100 %. FUNC + long push on
    DEP resets it to 100 %.
  - Old projects: an LFO's old DEP moves into its first route's depth when the sound loads, so a
    project whose DEP was not locked or modulated sounds exactly as before.
  - ENV2's page: G = DEST (pushing it opens the DEST popup for ENV2's routes, 4 at most), H = DEP
    (ENV2's attenuverter, 100 % by default, p-lockable).
  - Costs about 0.84 % of the CPU every frame.

**Known issues**

  - Where DEP was locked or modulated in an old project, that now scales all of the LFO's routes.

## v0.60.4 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.60.3
- **File:** DN2wishes_v0.60.4_3c0ef6a8_TEST.syx
- **SHA-256:** 3c0ef6a824fe4a08ab0e086b9ee9f845866f74c9e522dc380e4ccd3a28985b34
- **Hardware:** On the unit when v0.60.5 was made.

**Changes**

  - The !CPU label: every blink is drawn alone, with no full page redraw (about 1.7 -> 0.1 % of the
    CPU while it is lit).
  - Everything else as v0.60.3.

## v0.60.3 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.60.2-lfohalf
- **File:** DN2wishes_v0.60.3_91c8a9d3_TEST.syx
- **SHA-256:** 91c8a9d390d4ecb2c9b603a210b00dde8e9a7ddc99d212eb38ad5506c6293159
- **Hardware:** Not recorded.

**Changes**

  - Half-rate LFOs on by default, LFO4 off (the User's decision, 19 Nov).
  - PARA: a voice on ANALOG 2 or JUNO with no chord playing costs far less every frame (about 2.8 %
    of the CPU, estimate).
  - The !CPU label: while it blinks, half the full-screen redraws.
  - Routes popup: FUNC + DOWN / UP jump by sections.
  - Oscilloscope: hold [TRIG] for 1 s (stock's trig values show first); it stays until another page
    key, TRK, NO or a [TRIG] tap. [AMP] steps ENV1/AMP -> ENV2 -> ENV1/AMP (2 pages); the scope is
    no longer an AMP page.

**Known issues**

  - The release steps were still running when this file was made.

## v0.60.2-lfohalf (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.60.1
- **File:** DN2wishes_v0.60.2-lfohalf_febf3b68_TEST.syx
- **SHA-256:** febf3b6809c4548cfbccceb64631c9db9a27c722231727f3688f8bc454b92768
- **Hardware:** On the unit when v0.60.3 was made.

**Changes**

  - Everything in v0.60.2, and half-rate LFOs: LFO1-3 of each voice are computed every other frame
    (1.3 ms instead of 0.67 ms), half the voices each frame. Envelopes, the matrix and the smoother
    stay every frame.
  - About 10.5 % of the CPU at rest (emulator counts), about 1.4 % more than v0.60.2.

**Known issues**

  - Any roughness or stepping in fast LFOs was still to be judged by ear.

## v0.60.2 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.60.1
- **File:** DN2wishes_v0.60.2_0a5c88e0_TEST.syx
- **SHA-256:** 0a5c88e047e3cd3c564e97ded46443914218f095b8abdfe7658b44db0d8e9b00
- **Hardware:** Not recorded.

**Changes**

  - LFO4 is off (a project with LFO4 routes still loads; those routes do nothing and LFO4's DEST
    shows ERR, the saved data keeps them).
  - The LFOs and MOD SETUP passes are faster with the same output. About 9 % of the CPU at rest, the
    worst frame (16 note-ons) about 12 % fewer instructions (emulator counts).

**Known issues**

  - The CPU saving was not yet measured on the unit.
  - This file and v0.60.2-lfohalf are twins for comparing by ear.

## v0.60.1-routesjump (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.60.1
- **File:** DN2wishes_v0.60.1-routesjump_514ae10d_TEST.syx
- **SHA-256:** 514ae10d111b6d46f60f3c8fc3e13158d92909739c05321767975f373c500a0d
- **Hardware:** Not recorded.

**Changes**

  - Routes popup: FUNC + DOWN jumps the lit row to the first row of the next section (LFO rows, ENV
    rows, MOD SETUP rows), FUNC + UP to the first row of its own or the previous section. Stops at
    the ends; held, it keeps jumping.

## v0.60.1 (19 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.59.3, moved onto upstream v0.60 (FIXES)
- **File:** DN2wishes_v0.60.1_388264b8_TEST.syx
- **SHA-256:** 388264b8f15bf5269cbeea6a016d1aac24b8746b0d171145d0d3d5e930e57753
- **Hardware:** Not recorded.

**Changes**

  - From upstream v0.60: FM+ STAT and PAR show their frequencies (1FRQ, 2FRQ, 3FRQ) as ratios, FM+
    DYN as x.x and x.xx, as the Monomachine does. GRID's ALLOCATE SLICE: NO now leaves the menu and
    keeps the locks it made. The version on screen is 0.60.
  - ENV2's knobs ATK, HOLD, DEC, SUS, REL can be modulated: FUNC + push opens the routes popup on
    them. ENV2 cannot move its own knobs (its row says NOT ITSELF).
  - The envelope clone's HOLD (AHD mode) holds as long as stock's AMP envelope for every knob 1..126
    (HOLD 64 about 1.8 s); before, any HOLD under 127 held until the note-off.
  - The matrix's work each frame is cheaper (same results).

**Known issues**

  - The other steps were still running when this file was made.

## v0.59.3 (18 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.59.2
- **File:** DN2wishes_v0.59.3_8359bfe9_TEST.syx
- **SHA-256:** 8359bfe995b425ecc94768dcc1336c3a503612613337ae3eaa60d25e6023f75f
- **Hardware:** Not recorded.

**Changes**

  - PARA: a chord's extra notes no longer use up the DSP's shared pool. Before, every chord kept its
    extra notes' slots after it ended, so after about 5 chords chords played only their first note.
    The slots now come back when the chord's voice has gone silent (24 chords in a row, every note
    sounds).

**Known issues**

  - The other steps were still running when this file was made.

## v0.59.2 (18 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.59.1
- **File:** DN2wishes_v0.59.2_fccd9cd3_TEST.syx
- **SHA-256:** fccd9cd33a618694d63badbf592ecefd7893f7ab7ef34d80fe05274c610ea854
- **Hardware:** Not recorded.

**Changes**

  - PARA: chords end when their keys are up (they used to stay live and cost 5-10 % of the CPU);
    lifting one key releases that note; every held note of a chord is kept.
  - Overbridge streaming: its audio copies done straight, about 3 % of the CPU less while streaming.
  - LFO DEST: every way of opening DEST on an LFO page opens our popup. A trig held + D no longer
    sets a DEST p-lock (it edits the routes); existing DEST p-locks still play.
  - Oscilloscope: AUTO is the default gain; gain and time span are remembered after power-off.
  - Moving lines no longer freeze after a restart; ENV1's copy follows LFO routes into the AMP
    envelope.

**Known issues**

  - After about 5 chords the PARA pool could run empty (fixed in v0.59.3).
  - The feature steps were still running when this file was made.

## v0.59.1 (18 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.12, moved onto upstream v0.59 (FMPLUS)
- **File:** DN2wishes_v0.59.1_f724e786_TEST.syx
- **SHA-256:** f724e786ea4ba86d4062c92a4f4a8303a819ebe6718f85cb8600062d199052ad
- **Hardware:** Not recorded.

**Changes**

  - From upstream v0.59: FM+ STAT, FM+ PAR and FM+ DYN (MACHINE SEL, after the Monomachine
    machines); MON on the RECORDER (knob C: hear the input while armed and recording).
  - Our machines have new numbers: JUNO 50, ANALOG 2 51, DRONE 52, SOPHIE 53, TB-303 54, PLAITS 55
    (FM+ uses 18-20).
  - Routes popup and LFO DEST popup: holding NO deletes the route (a tap still mutes). FUNC + long
    push resets the parameter again; push-and-turn held no longer closes the popup.
  - While turning knobs the page is redrawn at most about 25 times a second; the screen no longer
    keeps catching up after you stop (was 0.4-0.9 s). List popups drawn faster.
  - Less CPU: stock's DSP link, send-buffer clear, USB audio out and a reply copy do the same work
    with fewer instructions. About 7.6 % of the CPU less at rest, about 10 % while a computer
    streams USB audio (estimate).

**Known issues**

  - Projects saved with older builds: PLAITS, TB-303 and SOPHIE tracks (old numbers 18-20) now load
    as FM+; DRONE, ANALOG 2 and JUNO tracks (old 21-23) load silent. Re-pick the machine on those
    tracks.
  - During a fast knob turn stock pages update about 9-12 times a second instead of 16-22.
  - ENV2: modulation and its moving line sometimes work, sometimes not.
  - FM+ is checked against its model, not against upstream's 240 recorded cases.

## v0.57.12 (18 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.11
- **File:** DN2wishes_v0.57.12_95dfbda0_TEST.syx
- **SHA-256:** 95dfbda000f448cd9482f515db558be01d3e1b2ae11cb39b840cf8b36b5d3f72
- **Hardware:** Not recorded.

**Changes**

  - ColdFire CPU cuts, every one identical in sound and parameter values: the DSP link receive loop
    rewritten, the audio interrupt's memory copies done as straight copies, slides and stock's
    smoother cheaper, PARA's note hooks written out.
  - Audio interrupt at idle 52,402 -> 48,339 instructions a frame (-7.8 %); the frame where 16
    tracks start a note -18 %. About 3-5 % of the CPU at rest (estimate).

**Known issues**

  - The saving is the emulator's count, not measured on the unit.

## v0.57.11 (18 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.10
- **File:** DN2wishes_v0.57.11_5bdc1318_TEST.syx
- **SHA-256:** 5bdc1318212424558aa64df333de190fd8bb350ade90a2f8b55043c080e36579
- **Hardware:** Not recorded.

**Changes**

  - New LFO DEST popup (push D on an LFO page): this LFO's routes on top with depth and moving bar,
    then the destination list, pool count top right. D turns the lit route's depth (0 removes it),
    YES unmutes or adds, NO mutes, NO held deletes, FUNC + NO deletes all of this LFO's routes.
  - The list is built once at the open (stock rebuilt it 16 times): the open is about 37 % cheaper.
  - Each LFO's first route is stock's DEST and DEP, so stock firmware still plays it; the other
    routes are in our record. Unmodified projects sound exactly as before.

## v0.57.10 (18 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.9
- **File:** DN2wishes_v0.57.10_f4faca86_TEST.syx
- **SHA-256:** f4faca86b58e4d22b998f1c92a86b09d63092f8152f7fb4db86c00ab85452b83
- **Hardware:** Not recorded.

**Changes**

  - Routes popup (FUNC + push on a knob) much cheaper: the moving bars are drawn alone, 15 a second
    (UI cost with the popup up 1.25 M instructions a second, was 3.31 M).
  - Routes popup: YES on an empty row adds a route at +32; FULL shows when all 16 routes are used.
  - Scope: the AUTO label says AUTO whatever gain it picked.
  - FX and AMP keys open page 1 on the press from another page, as stock (140 ms, was 240 ms).

**Known issues**

  - The LFO DEST list (push D on an LFO page) is still stock's and still lights !CPU while it opens.

## v0.57.9 (18 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.8
- **File:** DN2wishes_v0.57.9_71e2169e_TEST.syx
- **SHA-256:** 71e2169e6eb43e59d8a0f37f2c2427bea8d31bf6a3e7018dfef71410f698fc94
- **Hardware:** Not recorded.

**Changes**

  - LFO4's DEST list opens filtered to LFO4's destinations with the highlight on DEST's value; the
    header says MOD4.
  - Modulation matrix about 29 % faster (identical results). Saved routes survive a layout change.
  - Overviews on a long hold of SYN, FLTR, LFO and AMP.

**Known issues**

  - The routes popup and the LFO DEST popup still light !CPU.
  - The AMP and FX page switch is slower than other pages.

## v0.57.8 (18 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.7
- **File:** DN2wishes_v0.57.8_0ecf4027_TEST.syx
- **SHA-256:** 0ecf40277d689d864bc876c8427ad67bb4eeda6c4537ed2ba311029ce42b1b32
- **Hardware:** Not recorded.

**Changes**

  - Oscilloscope: encoder G steps x1/8, x1/4, x1/2, x1 to x16 and AUTO. AUTO picks the largest gain
    that keeps the signal off the top and bottom rows, zooms out at once and back in only after 8
    frames that fit.

**Known issues**

  - LFO4's DEST list: wrong highlight when it opens and no MOD4 header.
  - A push-turn of 2 detents on a DEST also turns its value (stock does the same on LFO1).

## v0.57.7 (17 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.6
- **File:** DN2wishes_v0.57.7_49df7194_TEST.syx
- **SHA-256:** 49df71947794f5c436be592e363de611f754a88bfbde8ad14dd204a0c5d8aef2
- **Hardware:** Not recorded.

**Changes**

  - Less CPU: stock's LFO evaluator runs as one inlined routine, with identical results (modulation
    about 2,700 instructions a frame less; audio interrupt about 2,300 less).
  - Oscilloscope at 15 frames a second (was 25), drawn alone, and skipped while the panel link is
    backed up, so the UI no longer waits behind it.
  - Moving-control lines are updated alone, without a full page redraw, where possible.

**Known issues**

  - The CPU figures are emulator counts, not measured on the unit.
  - LFO4's DEST list: wrong highlight when it opens, no MOD4 header, wrong-DEST risk.

## v0.57.6 (17 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.5
- **File:** DN2wishes_v0.57.6_1a2ebd30_TEST.syx
- **SHA-256:** 1a2ebd3013e5f11003d2ada369be321171ea4441a6d19a10fd42f0cef8b1b27d
- **Hardware:** Not recorded.

**Changes**

  - LFO4's state moved out of the memory that stock 1.12's +Drive file work overwrites. Every LFO4
    build from v0.56.2 to v0.57.5 had its LFO state overwritten when a project was created,
    initialised or loaded (measured: 756,480 writes).
  - The release check now compares every mod's memory against what stock 1.12 writes.

**Known issues**

  - LFO4's DEST list: wrong highlight when it opens, no MOD4 header, wrong-DEST risk.
  - Loading and saving a project with an LFO4 destination set was not driven in the emulator.

## v0.57.5 (17 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.4
- **File:** DN2wishes_v0.57.5_85ddd8e2_TEST.syx
- **SHA-256:** 85ddd8e257fe1dd71a082276680cb13ccef68e981bc2acad225f035555927356
- **Hardware:** Not recorded.

**Changes**

  - Matrix routes popup: routes sorted, mute YES/NO, a long NO deletes, FUNC + NO deletes all, a
    route turned to depth 0 is freed at once.
  - FX and AMP count a press as held from the key's first repeat, as stock's MOD does: a half-second
    hold no longer steps the page on release.

**Known issues**

  - LFO4's DEST list: wrong highlight when it opens, no MOD4 header, wrong-DEST risk.

## v0.57.4 (17 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.3
- **File:** DN2wishes_v0.57.4_9d152ff2_TEST.syx
- **SHA-256:** 9d152ff2710fb216327fe7480bd2d6b39fa2601135a88706ecd0441df0440d22
- **Hardware:** Not recorded.

**Changes**

  - PARA plays the whole chord: the chord's pitches ride in the voice's own frame words, so every
    note sounds on ANALOG 2 and JUNO (before, only the lowest one did).

**Known issues**

  - LFO4's DEST list: wrong highlight when it opens, no MOD4 header, wrong-DEST risk.

## v0.57.3 (17 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.2
- **File:** DN2wishes_v0.57.3_e8ef7481_TEST.syx
- **SHA-256:** e8ef74810f3a519d8c80ff57dfc1febb8690381f0d190c8ee8521e746ca53f5a
- **Hardware:** Not recorded.

**Changes**

  - The ColdFire does the same work every frame, faster: the modulation matrix (all routes every
    frame) and LFO4 always runs and costs the same whether used or not.
  - Stock's parameter smoother and MOD SETUP pass recoded, proven identical to stock.
  - Idle audio interrupt about 54,700 instructions a frame at every use (v0.57.1: 53,103 idle, but
    it grew with use).

**Known issues**

  - PARA ON plays only the lowest note (fixed in v0.57.4).
  - LFO4's DEST list still has the wrong highlight, no MOD4 header, and the wrong-DEST risk.

## v0.57.2 (17 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.1
- **File:** DN2_v0.57.2_3af2e4a2_TEST.syx
- **SHA-256:** 3af2e4a2b727f979a34130b74f7a564654ce6d5e1d437e3accb6cad491d53b39
- **Hardware:** Not recorded.

**Changes**

  - FX on its release, and the inserts overview (from v0.57.1-fxhold).
  - New project and INIT NEW no longer show the !CPU box (stock's file worker counts as idle in the
    meter).
  - Upstream pull request #2's fix keeping OS 1.11 builds working beside 1.12.

**Known issues**

  - PARA ON plays only the lowest note (fixed in v0.57.4).
  - LFO4's DEST list: the highlight is on the wrong row when it opens, the header lacks MOD4, and a
    quick push-turn then YES can store a wrong DEST.
  - Not run on this file: the full release check.

## v0.57.1-fxhold (17 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.57.1
- **File:** DN2_v0.57.1-fxhold_9d8c8f61_TEST.syx
- **SHA-256:** 9d8c8f61e919cbf0c834ec91d11477691d311e5a4998da79d9a58d27e6594204
- **Hardware:** Not recorded.

**Changes**

  - FX and AMP change page when the key is let go, and only if it was let go within a second; a long
    hold never changes the page.
  - While FX or AMP is held, the page shows its values instead of the names, as stock does.
  - FX held for a second: the inserts overview, with every track's two insert slots on one screen
    (title bar INSERTS n/32 and DSP nn %). White box = runs on the DSP, plain name = MIX 0, blinking
    FUL = FDN8 or XDLY with no free instance, dot = OFF.

**Known issues**

  - Not run on this file: the full release check.

## v0.57.1 (17 Nov 2026)

- **Status:** TEST build. Not released: the checks that guard against bricking the unit passed on this file; the full release check was not run.
- **Based on:** v0.56.2b
- **File:** DN2_v0.57.1_a8fbf921_TEST.syx
- **SHA-256:** a8fbf9211c07245cc8507792dd847466e3b75d853098471f0ba8d2361755f0cc
- **Hardware:** Not recorded.

**Changes**

  - From upstream v0.57 (FLEXMUTE): FLEX MUTE SRC mutes its source only while the FLEX track plays
    its take (0.2 s hold after the note), so no more tracks stuck muted.
  - REC 1 and REC 2 are gone from the sample list; F is the bank letter of a FLEX buffer on SAMP.
  - Upstream pull requests #2 (OS 1.12 support), #3 (PERC and Monomachine speed-ups) and #4 (sample
    machines' tables, PERC room) rebased on v0.57.
  - Everything from the unreleased v0.56.3 test: inserts start at MIX 0 and an insert at MIX 0 is
    sent as OFF; CHOR feedback up to 0.97; FDN8 SIZE curve changed; PARA works as one voice (joined
    notes take no slot); the P-I delay lines moved to faster memory (same sound).

**Known issues**

  - The full release check was still open on the FLEX mute test and two other steps.
  - Not run on this file: the other feature steps and the full release check.

## v0.56.2b (16 Nov 2026)

- **Status:** Cleared by the full release check. Not published.
- **Based on:** v0.56.1
- **File:** DN2_v0.56.2b_6ebfb8fb_CLEARED.syx
- **SHA-256:** 6ebfb8fb663384d3d78690e7ccc6ffc88c1d909f03dce95d6f01432ea4108f69
- **Hardware:** Not recorded.

**Changes**

  - LFO4 is on by default.
  - Carries everything of v0.56.1.

**Known issues**

  - Passed the full release check (all steps) on 17 Nov 2026 at 00:58; not yet published.

## v0.56.1 (16 Nov 2026)

- **Status:** Not released. Not cleared by the full test suite (listed below). Flashed by the User at his own risk.
- **Based on:** v0.55, moved onto upstream v0.56 (DDRW)
- **File:** DN2wishes_v0.56.1.syx
- **SHA-256:** starts bc9018e3 (the file is not kept)
- **Hardware:** Installed on the unit 16 Nov 2026.

**Changes**

  - From upstream v0.56 (DDRW): TIME glides between waves (up to about 2 s); BR1 and BR2 are heard
    across the whole knob.
  - Paraphonic ON plays up to 8 notes (was 4).
  - When the chord is full, a new key plays and the oldest held note stops.
  - FLEX: a take recorded from a very loud track no longer clips (the take is stored 18 dB lower and
    brought back up on playback; GAIN 0 still plays it at the source's level).

**Known issues**

  - Not cleared: upstream's FLEX play test (a ONESHOT track playing FLEX buffer B1) fails in the
    emulator.
  - STRETCH plays 1.92 dB under ONESHOT (not found why).

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
    (fixes in v0.54.2). All other tests pass, including upstream's new NAME screen test
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
    test for v0.54.2), flexlevel (a take's level against its source).
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
    emulator measures 4.0 dB under at the track's chain, 4.4 dB under at the amp).
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

  - Test failures: xdly (test emulator), flexlevel (a take's level against its source).
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

  - Test failures: xdly (test emulator), flexlevel, slice (fixed in the test).
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
