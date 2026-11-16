# Automated tests on the device (2026-11-11)

The emulator and the SHARC runner pass things the real unit fails (HOLD, glide, ANALOG2, the A2 filters, the load
labels lit below 70 % load): the model differs from the unit, and the User can only report by ear. This harness
makes the unit the test bench: **Claude drives the Digitone II over USB MIDI (notes only), reads its state back
through a read-only telemetry frame, and asserts.**

Nothing here writes to the unit. What the harness may send is fixed in `tools/dn2tools/src/dn2tools/unit.py`, not in the
scenarios, and `tools/dn2tools/tests` checks it:

| sent | allowed |
|---|---|
| note on / note off, channels 1..16 | yes |
| CC 64 (sustain), 120 (all sound off), 123 (all notes off) | yes |
| SysEx 1 HELLO (the link's version), SysEx 32 TLM (the frame) | yes, both read only |
| any other SysEx command (WRITE, LOAD, BEGIN, SCAN, ERASE ...), any other CC, NRPN, RPN, program change | refused in code (`Refused`) |

Flashing is the User's. The harness never flashes, never sends firmware, project or sample data.

## The parts

1. **Telemetry** (firmware): SysEx 32 `TLM`, in the sample link's SysEx (`csrc/sampler/link.c`), answered by the
   ColdFire from RAM words it already has. The telemetry **test build** carries it; the morning candidate does not.
2. **Driver** (`dn2test`, package `tools/dn2tools`, docs/remote-ui.md): finds the unit's MIDI ports, plays, polls, asserts,
   writes `report-*.md` and `results-*.json`.
3. **Simulator** (`tools/dn2tools/src/dn2tools/sim.py`): a fake unit, so the scenarios and their assertions are tested before the
   unit is connected (`--dry-run`, `--serve-fake`, `tools/dn2tools/tests`).

## The telemetry frame

Request: `F0 00 20 3C 7D 01 <pack7: u16 seq, u8 32> F7`. Reply: the usual `seq, 32 | 0x80, status 0` and 32
big-endian words (128 bytes). The ColdFire fills it with **reads only**: the meter's RAM block, the HOLD counters,
the insert counters and the DSP's idle packet as the sample link already stores it. `tools/dn2tools/src/dn2tools/frame.py` is the
format's definition (decode and encode).

| word | content | source |
|---|---|---|
| 0 | `TLM1` | |
| 1 | build id `0x0047 << 16 \| frame format` (0x00470001) | `TLM_BUILD`, link.c |
| 2, 3 | audio frames since power-on (1,500 a second); sample-link periods | `FRAMES`, `periods` (`smp_periods`) |
| 4 | **D** DSP load now, permille (the last half second's peak; none: 0xFFFFFFFF) | `smp_load_peak`, DSP unit 18 (a half-second peak, not an instant) |
| 5 | D peak over 3 s, percent | meter.c `dpk` |
| 6, 7 | **C** ColdFire load now (permille), peak over 3 s (percent) | meter.c `mtr_cpu`, `cpk` |
| 8, 9, 10 | **H** heap used (bytes), heap total, heap walk faults | meter.c |
| 11 | label bits: lit now (bit 0 D, 1 C, 2 M) \| hysteresis << 8 \| forced << 16 | meter.c `MTR_ICON_*` |
| 12..14 | frames since each label's last event (D, C, M); none: 0xFFFFFFFF | meter.c `MTR_ICON_AT_*` |
| 15 | voices skipped for time (bit v) \| insert-full << 16 | `smp_skipped`, `ins_full_any` |
| 16, 17 | INS_SKIPS (insert blocks passed through for time); periods since the last | DSP unit 23 |
| 18, 19, 20 | HOLD: `hold_count` (latches made), `hold_drops` (same-key drops), `hold_seq` (voices latched, bit v) | `csrc/hold/hold.c` |
| 21 | A2 filter pass: voices filtered \| voices left dry << 16 (16 bits each, cumulative) | DSP unit 40, 41 (`a2f` `nfil`, `ndry`) |
| 22 | the 16 slots' cost summed, cycles (one frame is 666,667) | DSP units 24..39 |
| 23 | slots rendering (cost not 0) | |
| 24..31 | each slot's last cost / 16, two to a word (slot 0 high) | DSP units 24..39 (guard `COST_PERC`, `COST_SMP`, the larger) |

**The DSP side (the only DSP change).** The idle packet's units 24..41 were zeros; the DSP now stores into them
(`src/dnfw/sampler/program.py`, after unit 23): 16 slot costs, then the A2 pass's two counters. It reads guard words
the DSP already keeps and writes only the packet buffer. 18 stores and a 16-step loop, once per idle packet.
Nothing reads those units but the frame.

**What is a "voice".** The unit has 16 voice slots (a track's notes play on any of them). The frame reports a slot
as rendering when its last cost is not 0. Whether the guard's cost word clears when a note ends is **not yet
measured on the unit**: the `idle` and `wiring` scenarios check it (a voice that never clears fails "the voice ends"),
and if they fail only there, read the voice counts as "since idle".

**D, C and the labels.** The load-label panel design with the six trigger bits S K D C H R (voice skip, insert skip,
DSP load, ColdFire load, heap, RAM) is not in this carrier: the carrier has three labels (DSP, CPU, RAM) with
the triggers listed in `csrc/meter/meter.c`. The frame reports those three bits, their hysteresis state, the age of
each last event, and every figure a trigger reads (skip mask, INS_SKIPS and its age, insert full, D, C, heap), so
the harness can say **why** a label is lit (`labels_explained`: a label lit with no cause in the last 2.5 s fails).

## What the User prepares (the harness cannot)

Machine, filter, insert and HOLD are not reachable through MIDI without writing sound or pattern data (the
Digitone II's CC/NRPN set changes the sound's parameters in place, and a program change loads a project). The
harness sends none of them. **The User sets up one project once** and keeps it for the tests. The default in
`tools/dn2tools/src/dn2tools/data/project.json` (edit the file, or pass `--project`); the number is the track, the MIDI channel is the
track's number unless the file says `"channel"`:

| track | machine | set on the unit |
|---|---|---|
| 1..5 | ANALOG2 | FLTR page filter: 1 SVF, 2 LADR, 3 OTA, 4 DIOD, 5 MS20 (the A2 filter machines 7..11); a sustaining sound (no short envelope) |
| 6 | DRONE | HOLD ON |
| 7 | DRONE | HOLD off, GLID long |
| 8 | ANALOG2 | insert XDLY engaged on the track |
| 9 | ANALOG2 | insert FDN8 engaged on the track |
| 10, 11, 12 | PLAITS, TB303, SOPHIE | (stress only) |

Also: every track's MIDI **input channel** equals its number (SETTINGS > MIDI CONFIG > PORT CONFIG > TRACK
CHANNELS: the DT2's default), USB CONFIG set to **USB MIDI or Overbridge** (the sample link's port), the sequencer
**stopped** and nothing else playing, no Elektron Transfer or other program holding the MIDI port, volume as you like
(the notes sound; turn it down). A track's polyphony must allow 4 voices (16 for the stress scenario): the
stress scenario plays 16 notes on a track in turn. Save the project under its own name; the harness never loads or
saves one.

## Running it

```
dn2test                 # everything, on the unit
dn2test --only idle,hold,a2_svf
dn2test --list
dn2test --dry-run [--fault a2_dies]
```

(`mido` is in that venv only; `python3` on the Mac has none. The tests under pytest use the dn2mk2 `.venv`.)
The port is found by name (`--port "Digitone II"`, a substring; the Mac lists it as "Digitone MIDI Elektron
Digitone II"). Output: `device-test-report/report-<time>.md` (what to read) and `results-<time>.json` (every check,
every number and the readings' time series). Exit status 1 when a scenario fails. About five minutes.

## The scenarios

| name | does | asserts |
|---|---|---|
| `link` | HELLO, two frames 0.5 s apart | sample link >= 7; the build is the 0.47 telemetry frame; audio frames count at 1,500/s; heap walked, no fault |
| `idle` | nothing playing, 2 s | D <= 95 %, C <= 85 %, no label lit, no voice skipped, no INS_SKIPS growth, no voice rendering, labels explained |
| `wiring` | one note on each project track | the note makes a slot render (so the channel is right); it ends after the release |
| `a2_svf` .. `a2_ms20` | each A2 filter's track: one note held 3 s, then four stacked 3 s | still rendering at 3 s; filtered counter grows over the last seconds (the unit's "died after 1 s"); not mostly dry; 4 voices rendering; INS_SKIPS growth <= cap; D < 100 %; no voice skipped; voices end after the release |
| `hold` | track with HOLD: note on/off, same key again, another key, another again, the same key to let go | `hold_count` +1 and one voice latched and still sounding after the key is up; same key: `hold_drops` +1 and none latched; another key takes the latch over (one latched); the last one released |
| `glide` | track with GLID long: legato overlap, then separate notes | at most two voices, D < 100 %, voices end (the pitch glide itself is audio, below) |
| `inserts` | tracks with XDLY / FDN8: 1 and 4 voices, 3 s each | INS_SKIPS growth <= cap (0), insert not full, D < 100 %, sounding |
| `stress` | each non-HOLD track: 16 notes held 3 s | D peak < 100 %, the unit still answers and its clock runs, all voices end; **records** D, C, voices rendering, voices skipped, insert blocks passed through per machine |

Every scenario ends with `labels_explained`: a label lit with no cause in the last 2.5 s of readings fails (the
labels lit below 70 % load). `--hold SECONDS`, `--ins-skip-cap N` change the hold time and the allowed INS_SKIPS
growth. The first run on the unit settles two guesses (marked in the report as failed checks): the idle D of an older
build was 94 %, so `idle_d_max` is 95; and whether a slot's cost clears (above).

## The dry run

`--dry-run` plays the same scenarios against `tools/dn2tools/src/dn2tools/sim.py`, a model of the unit in virtual time
(seconds, not minutes). It is a model: costs from the runner's budget table, loads rounded. `--fault NAME` switches
on a known failure to prove the assertion catches it: `a2_dies` (filters stop after 1 s), `hold_dead`, `labels_idle`,
`ins_skips`, `voices_stale`, `overload`. `--serve-fake` serves the simulator on mido virtual ports ("DN2 Fake",
wall-clock time) and `--port "DN2 Fake"` runs the real driver path (ports, SysEx framing, polling) against it.
`pytest tools/dn2tools` runs the lot: a healthy simulator passes every scenario, each fault fails the scenario
meant for it, the codec round-trips, nothing but notes and the two read-only SysEx commands can be sent, and the driver
works over the virtual ports.

## Benchmarks: real cycles on the unit

`dn2test --bench --label NAME --out DIR` measures what the runner only estimated. The telemetry's D is
the DSP's load over a half second in permille (0.1 % = 667 cycles of the 666,667 a frame), so **D x 666.667 is the
cycles a frame used on the unit, idle floor included**. It is the half second's peak: a "mean" is the mean of peaks
(an upper bound), "max" the peak over the hold. A cycle-exact per-frame counter would need a DSP change (the idle
packet carries only the meter's permille); 667 cycles is under 0.2 % of a heavy item, so it was not added. The
slots' own costs (`slots mean`) are the guard's per-voice words, rounded to 16 cycles.

Each item is held after a 1 s settle for 3 s (`--hold` sets it), the notes released, 2 s of silence before the next:

| item | what |
|---|---|
| `idle` | the silent frame with the project as it is. Run it twice, as the User sets the unit: all 16 tracks MIDI, then all machines selected but silent; use `--label` to tell them apart |
| `T<n> <machine> x1/4/8/16` | each non-HOLD track: 1, 4, 8, 16 voices held, D mean / max, over idle, slots, C, skipped voices |
| `A2 <filter> 1v` | each A2 filter track, one voice |
| `insert XDLY / FDN8 / CHOR 1v, 4v` | each insert track alone |
| `inserts A+B 1v each` | two different inserts at once |

Outputs: `bench-<label>-<time>.csv` (columns: build, label, item, key, voices, d_mean_cycles, d_max_cycles,
delta_mean, delta_max, slots_mean, c_mean_pct, c_max_pct, skipped_max, ins_skips, a2_dry, runner_cycles, ratio) and
a markdown table with the build id in the header. **Calibration:** `--runner budget-table.md` (default
`~/GitHub/dn2mk2-scratch/combined/budget-table.md`) is read for the synth rows (1 voice mean, 16 voices mean, frame totals);
a track whose project entry has `"key": "PLAITS:WS"` (the table's row name) gets `runner_cycles` and `ratio` =
unit / runner for 1 and 16 voices. Items without a key (inserts, filters) have no runner row in that table: the
ratio column stays empty for them (the table lists passes alone, not per-insert frames).

**Before / after:** flash A, `--bench --label A`; flash B, `--bench --label B`; then
`--compare bench/bench-A-*.csv bench/bench-B-*.csv` prints per item the total and the over-idle cycles of both and the
change in percent. The same project and the same unit state (sequencer stopped, nothing else) for both runs.
Run each twice to see the run-to-run spread before trusting a small gain.

## Peaks and wake-ups (the idle skips under load)

`dn2test --peak --label NAME --out DIR [--peak-seconds 60] [--seed N]` measures the worst frames, not the
steady state (the question: do the idle skips cost something when the project is busy, or when a skipped part wakes?).
Polls every 0.1 s; per scenario the mean, the 99th percentile and the max of D in cycles, the max of the first second,
the last second's mean, and `spike x` = first-second max / steady.

| scenario | does |
|---|---|
| `busy 16 voices` | 16 voices spread over every non-HOLD track (inserts and sends as the project has them), 10 s |
| `wake all tracks` | silence, then one note on every track at once (the model's 745k first block) |
| `wake <insert / filter> (T<n>)` | each insert and A2 filter track: a note, release, 6 s of silence (past FDN8's 4,224 blocks and the A2 quiet skip), the note again; the second start is measured |
| `random notes 60 s` | notes start at random tracks and times (seeded), the worst frame of the run |

What the telemetry can and cannot see: D is one frame's load held as the peak of the last half second, so polling every
0.1 s loses no frame's peak, and the max over a window is the worst frame in it (to 667 cycles). The percentile is over
polls, so it is an upper bound of the frames' own. D is clamped to one frame: a wake-up block over 100 % reads
1,000 and shows in `skipped` and INS_SKIPS, not as a number; if that matters, a DSP-side per-frame max counter with reset
(unclamped cycles) is the addition, and it needs a DSP change and a new build. **The skip switches are build
switches, not run-time ones**: the A/B is two builds, skips ON and skips OFF (flash, `--peak --label on`; flash, `--peak
--label off`), then `--peak-compare on.csv off.csv`, which prints mean, p99 and max of both per scenario and marks
**ON WORSE** where ON's max or p99 exceeds OFF's by more than two steps of D (1,333 cycles, the check overhead the
skips may cost). The OFF build does not exist yet: it is the same tree with the switches off (the FDN8 `QUIET_GATE`,
the A2 quiet skip, the chain skip, the empty-pass exits), built the same way and flashed by the User.

## Audio (the unit's USB audio, analysed on the Mac)

With the unit in USB audio mode the driver captures its main output (sounddevice, 48 kHz stereo; the input is found by
name, `--audio-device Digitone`) while the scenarios play, and analyses it with numpy only (`tools/dn2tools/src/dn2tools/audio_analysis.py`).
The MIDI port then is "Digitone Audio+MIDI Elektron Digitone II" (the default `--port "Digitone II"` matches it).

```
dn2test --audio [--only a_level,a_hold] [--out DIR]
dn2test --dry-run --audio          # the simulator's rendering, no unit
```

**Safety.** Sound plays on the User's unit and monitors: every note is at velocity 40 (`tools/dn2tools/src/dn2tools/data/audio_thresholds.json`), each
scenario is announced on the console before it plays, `--only` picks scenarios, `--dry-run` plays nothing. The first thing
the run does is read the build id from the telemetry; if it does not answer, the run stops and says to ask the User which
build is on the unit (`--allow-unknown-build` goes on anyway; the audio scenarios do not need the telemetry). MIDI is notes
and the three channel controllers only; the one SysEx is the read-only telemetry request. **Parameter CCs are never sent
unless the User gives a `--cc-map` file** (`{"cutoff": 74, "resonance": 75, "page2": [{"track": 8, "cc": 80, "low": 0,
"high": 127}]}`: controllers he has checked in the Digitone II manual; they change the track's sound in place, so use a test
project). Without it the resonance sweep and `a_page2` are skipped, not faked.

Each capture is saved as `DIR/wav/<scenario>-<n>-<tag>.wav`. Thresholds are in `tools/dn2tools/src/dn2tools/data/audio_thresholds.json` (unknown keys are an
error); the project may name a **reference track** (`"reference": true`): the same kind of sound with no filter and no
insert, the dry side of the filter and insert comparisons (the default project's track 13).

| scenario | does | asserts |
|---|---|---|
| `a_level` | every track, one note at its defaults (HOLD tracks let go by the same key) | level over -60 dBFS (not silent: ANALOG2, DRONE, all), no clipping, no clicks, no dropouts |
| `a_clicks` | each track a four-voice chord for 4 s, then every track at once for 6 s | clicks (second difference over its local RMS, 8x and 0.02 absolute), none once a 32-sample block (1,500 Hz: >50 % of clicks at one block phase), runs of zeros inside sound (dropouts), click rate |
| `a_filters` | each A2 filter track and the reference: one held note, spectra | each filter's spectrum differs from the dry reference by >= 6 dB in some band (levels matched: turning it down does not count); the filters differ from each other; with a CC map: the resonance raises the spectral peak >= 6 dB |
| `a_hold` | HOLD track: note on, off at 0.4 s, listen; the same key again | still within 6 dB of its level 1.4 s after the key went up; 30 dB down 2.5 s after the same key |
| `a_glide` | glide track: C4 then G4 overlapping, then separately | legato: the autocorrelation pitch track takes 0.08..3 s for 10 %..90 % of the way C4 to G4; separate notes: <= 0.05 s |
| `a_inserts` | each insert track and the reference: a 0.1 s note, 3 s of listening | XDLY: echoes (autocorrelation peaks of the level envelope, delays reported); FDN8: tail to -40 dB over the dry one by 0.3 s (0.5 s with no reference); wet differs from dry by >= 3 dB |
| `a_page2` | with a CC map: each listed control low and high | the spectrum changes >= 3 dB |

The analysis is tested on synthetic signals (`tools/dn2tools/tests`); the simulator renders the notes it was played (saws, a
filter weighting the harmonics, echoes, a tail, a glide) so every scenario passes on a healthy simulation and the faults
`audio_clicks audio_silent filter_dead glide_dead delay_dead hold_dead` each fail the scenario meant for them. A model of the
sound, not of the unit: the first run on the unit may need threshold changes (pitch tracking on a rich waveform can read an octave
off; the click detector is tuned on synthetic clicks). What the audio cannot say: whether a sound is good, only whether it is
there, clean, filtered, held, gliding, echoing.

## What cannot be tested this way

- **Audio quality by telemetry alone.** Whether a filter sounds right, whether an insert changes the sound, whether the glide's pitch
  runs, whether a voice crackles: the telemetry sees loads, counts and states, not the signal. The audio scenarios above do
  measure these over USB audio. What follows was the plan before they existed.
- **Crackle needs a recording.** An audio loopback through the Mac could add a click detector: record the unit's main
  (or a track) output on an audio interface at 48 kHz while a scenario plays, then find clicks (a sample-to-sample
  step far above the signal's own slope, or energy in a 10..20 kHz band for a few samples) and pitch (zero crossings
  or an autocorrelation per 50 ms, for the glide). It needs: an audio interface with an input on the Mac (a
  line cable from the unit's main out, or the unit's USB audio if Overbridge is on), `sounddevice` (or `ffmpeg`
  with avfoundation) in a venv, and the scenario to start the recording before the notes; the unit's cable level
  must not clip. The harness has the hook (`Ctx.run` samples while the notes play); the recorder is not written.
  Nothing in this repository records audio yet. `scripts/audio_probe.py`, `scripts/audio_sync.py` are earlier
  attempts in the repository and may be the place to start.
- **The project's setup** (machines, filters, inserts, HOLD): by hand (above).
- **HOLD OFF releasing all voices**, the pattern sequencer's HOLD (short trigs): by hand; MIDI notes only test the
  played-key latch.
- **A scenario's reading of a voice** is the guard's cost word: a voice the DSP renders but whose cost is 0 reads as
  not rendering.

## Known quirks of the first telemetry build

- A label's "frames since the last event" (words 12..14) and INS_SKIPS's age (word 17) can read 0xFFFFFFFF ("never",
  `None`) for one frame when the request lands in the same frame as the event (the stamp is stored `| 1`, one count ahead
  of the clock). Harmless; read it as "just now" if the value was a number a poll earlier.
- `nfil` / `ndry` are 16 bits and count per block: 16 voices wrap them in under 3 s. The scenarios that use them hold at
  most four voices; take differences with `delta16`.

## Hand-over (2026-11-11, to the remote UI session, the single owner of this work)

Branch `claude/autotest-device-c6da3b`. Everything is committed; nothing is pushed or published.

**Exists and works (simulator / emulator only):**
- Telemetry firmware: SysEx 32 TLM, DSP idle packet units 24..41. Build
  `~/GitHub/dn2mk2-scratch/DN2mod_v0.47-ours-NOBOOT-1.12-combined-telemetry_UNGATED_OS1.12.syx`, sha256 `c87ec50e3bfb8d25093ae8215ac7fda9fff5f048cf4cfb4e29e91f8fead00a2c`
  (source 9019f236, regenerated files d7a2d62b). Build recipe: `~/GitHub/dn2mk2-scratch/autotest/build_tree.sh NAME COMMIT`
  (needs a commit hash from this repo, not the main checkout's HEAD). Emulator check: `scripts/check_tlm_replies.py` on the replies of
  `emu_waverider_menu.py`'s `sysex:` step (`~/GitHub/dn2mk2-scratch/autotest/farm_tlm.sh` ran it on the farm).
- Driver `tools/dn2test.py` + `tools/dn2test/`: function scenarios, `--bench` / `--compare`, `--peak` / `--peak-compare`, `--audio`, `--dry-run`,
  `--serve-fake`. 23 pytest tests (`tools/dn2tools/tests`, the project `.venv` has pytest and numpy).
- The audio-analysis scenarios and the peak / wake-up scenarios are NOT queued: they are written and tested (sections above).

**Verified:** preflight family on the telemetry build; boot from reset 800M, fault None; the emulator answers HELLO and TLM; the simulator passes every
scenario and each fault fails its scenario; the driver over real mido virtual ports.
**Not verified:** anything on the unit. Open: does a slot's cost word clear when a note ends (voice counts); MIDI channel = track number;
idle D; audio thresholds (pitch tracking octave errors, click detector tuning); no skips-OFF build exists for `--peak-compare`; the telemetry's
D is clamped to one frame (an unclamped per-frame max needs a DSP change); a label age can read "never" for one frame.

**Still to do (the usable-by-others requirement, from main):** no hard-coded paths or user names (`tools/dn2test.py` defaults `--runner` to
`~/GitHub/dn2mk2-scratch/...`; the docs name the optimist venv), a documented venv recipe (mido, python-rtmidi, numpy, sounddevice) and a
requirements file, scenarios in a documented file format (today they are Python functions; thresholds are already JSON), a clear message on firmware without
the telemetry channel (status 2 already gives one; make it a typed error), a versioned protocol spec, `pip`-free CI run of the simulator tests, a quickstart.
`tools/dn2tools/src/dn2tools/unit.py` imports `pack7` from `tools/dn2probe.py`: copy it into the package to make it self-contained.

**Done by the remote UI session (2026-11-11):** all of the above. The driver is the `dn2tools` package
(`pip install ./tools/dn2tools`, console commands `dn2test` and `dn2ui`; `tools/dn2test.py` stays as a shim), no
hard-coded paths, `pack7` in `protocol.py`, typed errors (`NoTestChannel`, `StatusError`), a versioned protocol spec
(`docs/remote-ui-protocol.md`), UI scenario files in JSON, a quickstart (`docs/remote-ui.md`). The skips-OFF
comparison now has a one-build form for the runtime switches (`--peak --switch-ab HOLD`); the DSP's skip switches stay
build switches (two builds).

