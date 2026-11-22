# The coupled emulator: what is faithful, what is approximate (v0.48 audit)

`scripts/emu_coupled.py` runs the modified ColdFire image (digikit's ColdFire emulator, the
stock 1.11 snapshot with the build installed) and the modified SHARC image (digikit's SHARC
runner, `sharc_waverider_m5.py`) together, one audio period at a time. This page says, for
each place where the two meet or where time is involved, what the harness does and how
close that is to the unit. A result from it is evidence of category **1** (the actual modified
ColdFire and SHARC code together) only for what the table below calls faithful; anything that
leans on an approximation is said so in the result.

## The resume: the kit stored, as at boot (2026-11-20)

`Coupled` writes the build's runtime (code, `.data`, zeroed BSS) over the snapshot, so our code starts as at
boot. The build's own snapshot was made by this build, whose UI pass already converted the playing kit for the DEP
attenuverter (`csrc/matrix/atten.c`: an old sound's DEP moved into its LFOs' first routes' depths, DEP set to 100 %).
Left so, the next UI pass converted it again with the depth = 100 %, and every LFO of the snapshot's project played at
full depth (measured: `parachord`'s PARA OFF voices smeared in pitch from v0.62.2 to v0.62.5, the first builds with
the attenuverter run through it; the NOTE words identical to v0.62.1's). A unit never has this state: at boot stock
loads the kit stored (DEP = C). On the build's own snapshot (its section 3 image is the build's), `Coupled._store_kit`
stores each converted kit sound back as the saver does (DEP = `mxa_compat(D, A)`, D from the snapshot's matrix
tables, `MX_RAM`), in the sound, its voices' rows and the smoother, before the first period; `kit_stored` reports it
(`emu_coupled_para.py` prints track 3's). Measured on v0.62.2's own snapshot: track 1's DEPs 0x432B, 0x4021, 0x4240 and
track 3's 0x4350, 0x4016, 0x44B3 at the resume, those of the build before the attenuverter, and one conversion.

(2026-11-21) The ColdFire-only harnesses that write the runtime over a snapshot had the same double conversion; they
now call `scripts/emulib/attkit.py` `store_kit` right after the runtime (the same store-back; the tables' layout from
the matrix state's magic, so it also reads a snapshot made with DN2_ROUTE8 or DN2_LFO4; idempotent; `DNFW_ATTKIT=0`
is the negative control). Gate `matrix`, `attsnap`: on the build's own snapshot (48 converted LFOs) the first UI pass
converts once; with `DNFW_ATTKIT=0` 41 of them come back at full depth. `Coupled._store_kit` stays until the
combined branch holds `emulib/mxlayout.py`; then it calls `attkit` too.

## One period

A period is one DSP block: 32 frames at 48 kHz, 1,500 a second. In each:

1. the ColdFire's UI runs a slice of `UI_SLICE` (1 M) instructions, its PIT/DMA timers on
   digikit's instruction clock;
2. the sequencer's timer ISR (`0x400D987A`, vector 121) is entered as many times as the
   tempo gives (below);
3. the ColdFire's audio ISR (`0x40025E36`) runs to its `rte` (`0x40027BC6`);
4. the frame it built (`0x80005E60`, 2,688 bytes, big-endian) is byte-swapped into the DSP's
   `unpack_call`;
5. the newest ColdFire transmit half with a new sequence number is copied into the DSP's
   receive page (the page the DSP's dispatch is on), the IN samples (`input`) poked into its
   input buffer;
6. the DSP's block runs (8 M instructions at most; it must return to the unpack's return);
7. the DSP's status (its reply page tail) is written to the ColdFire's reply tail
   (`0x80005E40`), and its transmit slots 14..15 to both halves of the ColdFire's receive page.

## Audit

| what | the harness | the unit | verdict |
|---|---|---|---|
| **Audio ISR cadence** | once per period, at the period's boundary (entered by a call with the registers and PC/SR kept, left at its own `rte`) | an interrupt every 0.67 ms, landing anywhere in the UI's code | **faithful in count and order** (one ISR per DSP block; the frame counter `0x4058E8D4` +1 each). **Approximate in placement**: the ISR never lands in the middle of UI code here, so a race between the two (a half-written value the ISR reads) is not exercised. `emu_waverider_menu.py --isr-frame` and the gate's fuzz step cover preemption on the ColdFire alone |
| **UI time against audio time** | **fast** (the default): 1 M UI instructions a period, the timers at digikit's 18.72 M a second; measured (v0.48, 150 periods, 0.1 s of audio): the 60 Hz tick 540 times where the unit gives 6, **90 x** too fast. **faithful** (`set_timing("faithful")`): a frame is the audio ISR's measured cost / 0.56, the UI gets the rest of it, stopped exactly at its end by a frame clock among digikit's deadline sources, the ISR's own time counted, every timer on that clock | the OS's 60 Hz timer wheel and the 1.5 kHz audio interrupt on one clock; the ISR 56 % of the ColdFire with the sequencer stopped, 60.5 % busy in all (USB probe, `docs/coldfire-tasks.md`) | **fast: approximate** (fine for functional checks; anything depending on UI time against audio time is not faithful). **faithful: measured faithful** on the ColdFire alone (dsp=False, 1,500 periods = 1 s of audio): the 60 Hz tick **59** (60 wanted), PIT0 **50** (50), DTIM3 **30** (30), FRAMES 1,500, no faults; the UI's idle share **80 %** against the unit's 90 % (the emulator's UI a little busier: the fast stepper counts blocks x 3.87, not cycles). Cost: 0.09 s a period without the DSP, about 11 s with it (the DSP's block dominates either way); UI flows need about 80 x more periods, so tests use fast for setup and faithful for the part whose timing matters |
| **Sequencer clock** | the timer ISR entered `24 x BPM / 15 / 1500` times a period (the frame's word 108 is BPM x 120; 24 entries a sixteenth, measured in `emu_jump.py`), the fraction carried over | a DMA timer interrupt at that rate, exactly | **faithful in rate** (no drift: the remainder is carried), **approximate in phase**: an entry lands at a period boundary, up to one period (0.67 ms) late, always just before that period's audio ISR. Step order and the steps themselves are the firmware's |
| **ColdFire -> DSP packets** | the newest transmit half with a new sequence number, once a period | the TDM DMA sends both halves in turn, every frame | **faithful when the ColdFire writes at most one new packet a period** (the link's ISR fills one transmit half an ISR; the harness counts `delivered`, so a test can compare it with the ColdFire's own count). If both halves changed within a period the older would be skipped here: a loss the unit would not have. No bit errors, no reordering are modelled |
| **DSP -> ColdFire status and replies** | the status words and slots 14..15 copied after the DSP's block; the ColdFire reads them in the next period | the SPI reply ring and TDM slots, refreshed each frame | **faithful in content, one period of latency**; the unit's own latency is of the same order (the reply of block n is read during block n + 1) but its exact phase is not modelled |
| **Buffer and directory sync** | none forced: the ColdFire's mirror of the pool (`SM.MIRROR`) and the DSP's directory (`SMP_POOL_DDR`) are each written only by their own code and the link | the same | **faithful**, except the setup shortcuts the tests take (below) |
| **The DSP's RAM check (CMD_PROBE)** | finished the moment it starts with the whole-part verdict (`pres` 1), instead of its ~1,000 blocks | the real check | **a shortcut** (`_shortcut_probe`). Everything after it is the two sides' own; `probe()` itself is held to its model by the SHARC runner's link part. A test can turn it off (`shortcut_probe = False`) at the cost of hours |
| **The DSP's time budget** | a block always completes (8 M instruction cap); instructions counted, not cycles | a block must finish in its frame; memory stalls dominate (`docs/timing-model.md`) | **not modelled**: an overrun on the unit is not one here. The meter and the guard's own tests cover load |
| **Inputs** | `input(block)` poked into the DSP's input buffer at its dispatch, as the per-block driver converts them | the codec's samples by DMA | **faithful at the DSP's input buffer**; the codec, its gain and its latency are not modelled |
| **Voice slots** (2026-11-14) | the DSP starts from the SHARC runner's warm snapshot | every slot's per-slot chain set up at power-on | **every slot faithful since `INIT_REV` `_g14d`** (sharc_dn2_fixups G12-G14 and the warm snapshot `m2_init_<sha>_g14d.snap` built under them): a stock note on slots 0..15 bit-identical to slot 0's (`scripts/sharc_slots.py`). Before, only voice slot 0 sounded, stock or ours (r5, one run: track 2's stock note on slot 0, peak 0.0213; then track 4's on slot 1, 0.0000), and every coupled or full-frame run of our machines was silent, their notes on slots 1 and up. The causes, measured in the runner: the engine init's per-track loop scattered the tracks' state (a MODIFY with no width selector scaled x 4: G13), so only slot 0's chain was set up (the DC blocker's coefficients 0 on the others); the dispatch's SIMD byte forms latch the odd slots' note triggers with PEy, which the runner did not do (G12); a long-word access's modify scaled x 8 where the firmware counts normal words (G14), so slot t read slot 2t's gain smoother. ournote still plays one machine a run, so its note is on slot 0 as the gate first proved it |
| **Snapshot** | `--snapshot .../ui800M-v014.snap`, resolved through `SNAPDIR`: the build's own UI snapshot (`emu_install_snapshot.py`, as `worktrees/up-pr0/make_snap.sh` makes it) | | **required**: with another build's snapshot the panel keys do nothing (r5 on the default `snap112b`: KEYBOARD stays off, no voice) |
| **The stock Equalizer filter** (2026-11-14) | the filter type the frame names, set up from the warm state | | **not faithful**: a track on the Equalizer (ColdFire filter 2) reads NaN after the chain from its first block, whatever the machine (a stock machine too; the same JUNO frame on the Multimode: finite, PERC's own output bit-exact to its model). Not measured on the unit; assumed the harness's (the Equalizer is a stock filter). Track 4 of the snapshot's kit, JUNO put on by MACHINE SEL's commit, is on it (the kit's or the commit's choice: not checked); the gate's ournote uses track 3 (Multimode) |
| **`dsp_clock()` and our voices' audio** (2026-11-14, r5) | the DSP given a clock (the budget proof's calibration) | | **faithful once calibrated with `Coupled.clock_calibrate()`** (7151c998). Calibrating by hand ran frames before EXTRA was set, and the guard held their stock tail (~373k cycles) at its peak, easing it by 1/4096 a frame: the limit came to ~210k, our entry sits ~165k after MARK0, the 45k left are under the guard's 60k FLOOR, so every voice of ours was refused (and an MNM voice refused is stolen until its next note): -84 dB, skips 1. `clock_calibrate` sets EXTRA, runs two calibrated frames (a block reads the frame before it), then clears TAIL and REST_OUT: JUNO held on slot 0 at idle D 0.69 gives tail 259k, limit 324k, 0 skips, 7.9k cycles a block, and it sounds; DRONE (the User's T6) -29.1 dB peak, 0 skips. A run calibrated the old way (`emu_coupled_budget.py` until it moves) measured its counters, but our voices there were most likely refused: its audio is not the unit's |
| **PLAY** (2026-11-14, r5) | the panel's PLAY key with trigs placed by RECORD + [TRIG 1] | | **the sequencer does not start** (`0x42C5B918` stays 0, no voice): `emu_coupled_seqnote.py --with` plays a second track by a second KEYBOARD note instead |

### The setup shortcuts each coupled test takes

- `emu_coupled_thres.py`: the track's machine byte poked to ONESHOT; the pool's mirror
  emptied; `smp_dir_ok` set; the RECORDER opened by calling `rec_combo`; THRES, SRC, R.STRT
  set by writing their variables. The ARM is a real encoder turn.
- `emu_coupled_recplay.py` (v0.48): the machine through `smp_machine_commit` (the UI's
  commit path, called from the harness); the pool's mirror emptied; `smp_dir_ok` set; the
  RECORDER through FUNC + VOICE when the panel names those keys (else `rec_combo`, recorded in
  its report); SRC and R.LEN written; YES, TRIM/NAME/ASSIGN, STRT's turn, KEYBOARD and the
  note are panel keys and encoders.

### What a coupled result can and cannot claim

It can claim that the ColdFire's code and the DSP's code, as built, carry a command, a
recording, a selection and a render between them correctly in the order the period gives.
It cannot claim anything about the unit's timing margins (an ISR landing mid-update, a
packet lost to a busy period, a DSP block overrunning), the codec, or the panel hardware.
Those stay category 3 until measured on the unit.
