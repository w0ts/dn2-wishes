# Remote UI and device tests: dn2tools

Test the Digitone II **on the unit, over USB**: read its numbers (telemetry, counters, trace, state), flip
whitelisted runtime switches for A/B runs without reflashing, record its audio, **see its screen** and
**press its keys**. It needs a *test build* (the firmware below); the shipping builds have none of it.
**Claude never flashes or writes firmware or storage; the User flashes.**

One package (`tools/dn2tools`, Python), one protocol (`docs/remote-ui-protocol.md`), this README.
`docs/device-tests.md` describes the scenarios (functional, peak / wake-up, audio) that run through it.

## The User's ruling (2026-11-11): always in, behind a menu switch

1. **Always in.** The protocol goes into **every** build, not a separate test build. Read-only telemetry
   (TLM), BUILDINFO, STATE and COUNTERS always answer. Screen mirror (SCREEN), key / encoder injection (ARM, KEY)
   and runtime SWITCH writes work only while a new entry in the stock **SYSTEM > USB CONFIG** menu is ON; the SysEx
   arm handshake and the destructive blacklist stay on top of that.
2. **Remembered.** The menu setting is saved with the other USB CONFIG settings and survives a power cycle. Where it
   is stored must be cleared or safely ignored by a stock reflash and by a factory reset (to be measured and stated
   here when built).
3. The integration line (combine / upstream-v048) takes it as a self-contained commit series.
4. (2026-11-11, later) *"menu entry or just always on for now if needed"*: remote control may stay always on (armed
   by the SysEx handshake only) until the USB CONFIG entry is ready; the User checks that entry on the unit (the
   emulator cannot open SETTINGS). *"Yes, reset turns it off"*: a factory reset must turn the setting OFF, so the
   mod's settings sector alone (which a factory reset leaves as it was) is not enough; the setting must be cleared
   by, or tied to something cleared by, a factory reset (to be found).

**Found so far (OS 1.12 image, 2026-11-11), not built:** USB CONFIG is a view of its own (title `USB CFG`, class
name `UsbConfi...`), not a data table: its three choices (OVERBRIDGE, USB MIDI, USB AUDIO/MIDI) are added in code
at `0x4010478e`, `0x401047b6`, `0x401047de`; a fourth entry means patching that view's construction, its
selection handler and its save. **The emulator cannot open SETTINGS** (`docs/ui-map.md` §7: the +Drive is not
modelled, SETTINGS parks on `FACTORY PROJECT >> +DRIVE...`), so such an entry can be verified only on the unit.
The storage that fits "remembered, ignored by stock": the mod's own settings sector `0x6FF000` on the +Drive
(`docs/jump.md` §4: `'DN2S'`, flags bit 0 DIRECT JUMP; this would take bit 1). Stock never reads or writes there
(its store ends below `0x458000`), so a stock reflash ignores it; a factory reset does **not** clear it (it stays
as set for the next mod build).

Until the menu entry exists, the build below is a test build with the gated commands always available (armed
by the handshake only).

### Cost, measured (build `60ffcf64` against the telemetry build `c87ec50e` and night9)

| | section 3 (ColdFire, unpacked) | section 7 (DSP) | packed upgrade image (2 MiB buffer) |
|---|---|---|---|
| telemetry vs night9 | +832 B | +184 B | |
| test channel vs telemetry | +6,584 B | 0 B (identical bytes) | +3,131 B: 2,092,215 of 2,097,152, **4,937 B left** |
| total vs night9 | +7,416 B | +184 B | |

DSP cycles on the frame path: none from the test channel (section 7 is byte-identical to the telemetry build's;
the telemetry build's 18 idle-packet stores are autotest's). ColdFire audio interrupt: one load and test (the
HOLD switch) at each note-on. The rest runs in the MIDI task (commands) and the UI task (the key queue, once a
pass). The upgrade buffer's margin is the binding limit for "every build": 4,937 B with everything in.

## Status (2026-11-11)

| part | state |
|---|---|
| Firmware: BUILDINFO, SWITCH, PEEK, COUNTERS, TRACE, STATE, SCREEN, ARM, KEY (SysEx 33..42, `csrc/devtest`) | built, preflight family passes, emulator-verified (below) |
| Telemetry TLM (32), from the autotest work | built before, emulator-checked |
| `dn2tools`: protocol, client, screen mirror, key driver, simulator, `dn2ui`, `dn2test` | 46 tests on the simulator, no hardware |
| Audio scenarios over USB audio, peak / wake-up scenarios | written and simulator-tested (`docs/device-tests.md`), not run on the unit |
| On the unit | **nothing yet**: waiting for the User to flash the test build |
| CPU profiler PROFILE (43, `csrc/devtest/prof.c`), `dn2test profile` (remoteui-5) | built, preflight family and the emulator (below); not run on the unit |

## Quickstart

1. **The User flashes the test build** (`DN2mod_v0.47-ours-NOBOOT-1.12-combined-remoteui_UNGATED_OS1.12.syx`; UNGATED: it
   passed the preflight family and the emulator, not the full ship gate). Load a **scratch project**: driving the
   UI changes the project in RAM like any key press.
2. USB: `SETTINGS > SYSTEM > USB CONFIG`: *USB AUDIO/MIDI* or *OVERBRIDGE*. The MIDI port reads "Digitone
   Audio+MIDI Elektron Digitone II" or "Digitone OB Elektron Digitone II"; the default `--port "Elektron Digitone II"`
   finds either (the test channel answering over the OB port is not measured yet). The audio scenarios need the audio
   device too.
3. Install (macOS or Linux; Windows best effort), in any venv:

       python3 -m venv .venv
       .venv/bin/pip install "./tools/dn2tools[audio]"      # mido, python-rtmidi, numpy; sounddevice for audio

4. First contact, all read only:

       .venv/bin/dn2test smoke                 # every read command once; clocks; PASS/FAIL
       .venv/bin/dn2test info                  # the build, its capabilities
       .venv/bin/dn2ui snap                    # the screen -> a PNG; prints its path
       .venv/bin/dn2ui mirror                  # the live screen in the terminal (--window, --png-dir DIR)

5. Keys (arms first; the unit disarms itself after 300 s without a command):

       .venv/bin/dn2ui press FUNC+SRC          # FUNC held, SRC tapped: the machine list
       .venv/bin/dn2ui turn A +5 --push        # encoder A, five detents, its push held (a menu's value)
       .venv/bin/dn2ui press NO
       .venv/bin/dn2ui disarm

No unit? Add `--sim` to any command: the simulator answers as the firmware does (a toy UI, not the unit's).

## Commands

`dn2ui` (screen and keys): `snap [FILE]`, `show`, `mirror [--fps 8] [--window] [--png-dir DIR] [--seconds S]`,
`arm`, `disarm`, `status`, `press KEY|CHORD...`, `hold KEY MS`, `turn ENC DELTA [--push]`, `seq STEP...`,
`wait-for FILE.png|--changed`, `run SCENARIO.json`, `keys`.

`dn2test profile` (the CPU profiler, below): `--seconds N --label L --out DIR [--rate 997] [--source auto|timer|audio]
[--stock-dis F | --stock-bin F | --stock-symbols F] [--ours waverider_code.json]`, `--compare A.json B.json`,
`--report RAW.json`, `--status`, `--stop`. Options: `--port NAME`, `--sim`, `--log FILE`
(the event log, default `./dn2ui-events.jsonl`), `--allow-destructive` (see Safety).

`dn2test` (measurements): the scenarios (`--only`, `--dry-run`, `--audio`, `--peak`, `--bench`, `--compare`,
`--peak-compare`; `docs/device-tests.md`), `--peak --switch-ab NAME` (the peak scenarios twice on one build, the
switch at 1 then 0, then compared), and `info`, `switches`, `switch NAME VALUE`, `counters [reset]`, `trace [SINCE]`,
`state`, `peek ADDR [LEN]`, `smoke`.

Every command prints its cost: round trip in ms and SysEx bytes each way (`--quiet` hides it).

Python:

```python
from dn2tools.unit import MidoUnit
from dn2tools.channel import TestChannel
from dn2tools.keys import Keys
from dn2tools import screen

ch = TestChannel(MidoUnit("Elektron Digitone II"))
print(ch.info(), ch.state().machine_types, ch.counters())
screen.write_png(ch.screen(), "now.png")
k = Keys(ch)
k.arm(); k.press("FUNC+SRC"); k.turn("A", +3, push=True); k.press("NO")
k.wait_for_screen(lambda f: screen.pixel(f, 10, 10), timeout=2)
```

Key names: `TRIG SRC (SYN) FLTR AMP FX MOD PRESET SETTINGS TEMPO YES UP NO LEFT DOWN RIGHT TRK FUNC KEYBOARD RECORD
PLAY STOP PAGE PTN SONG T1..T16 PUSHA..PUSHH LEVEL VOICE ARP PLUS STACK MINUS`; encoders `A..H LEVEL`.

### Scenario files

- UI scenario (`dn2ui run`), JSON: `{"name": str, "about": str, "steps": [str, ...]}`. A step is a key or chord
  (`"FUNC+SRC"`), `"turn:A:+5"`, `"push:A:-3"` (turned with its push held), `"hold:PLAY:600"`, `"wait:0.5"`,
  `"snap:NAME"` (a PNG), `"expect:changed"` (the screen must change from the last snap within 2 s, else FAIL).
  Example: `tools/dn2tools/src/dn2tools/data/ui/machine_list.json`.
- The project (which track holds what), the audio thresholds: JSON, `docs/device-tests.md`.

## Safety

- **Disarmed at power-on.** Arming is a handshake: the host asks, the unit answers a nonce, the host sends it back
  with `ARM!` within 10 s; one try per nonce.
- **Auto-disarm** after `ARMTIME` seconds (default 300, a switch: 30..1800) without an ARM or KEY command, and on
  `disarm`. Disarming lets every injected key go and drops the queue.
- **Every key goes up by itself:** a press carries its hold time and the unit lets the key go at that time, so a
  host that dies mid-chord leaves nothing held.
- **Destructive blacklist, in the firmware and in the host:** SETTINGS (the system menu: project manager, OS
  upgrade, format, sample manager) is refused; with FUNC held only the page keys, the arrows, PLAY, STOP, PAGE and
  the encoder pushes may go down (FUNC with YES, NO, PRESET, PTN, SONG, RECORD, ... is refused); FUNC may not go
  down over a held key outside that set. `--allow-destructive` (armed with the destructive flag) lifts both; it is
  **dangerous** (it can save over a project or start an OS update), it is for the person at the unit, and Claude
  never sets it.
- **Not covered:** a confirm dialog reached through the allowed keys is answered by YES like any other (no screen
  text check yet); the blacklist covers the paths into saving, clearing, formatting and updating, not every dialog.
- **Logged:** every injected event in the host's event log (JSON lines) and in the unit's trace (TRACE), with the
  refusals.
- **Writes:** SWITCH writes only the whitelisted words (`csrc/devtest/whitelist.c`, bounded, reset at power-on);
  KEY goes through the panel's own input path. Nothing writes flash, firmware, the +Drive or the samples. The
  tools refuse to encode any other command of this SysEx channel (the sample link's image writes, the library,
  ERASE MOD DATA).

## Switches

Runtime words the firmware reads (`dn2test switches`, `dn2test switch NAME VALUE`, `dn2test --peak --switch-ab NAME`):

| name | | default |
|---|---|---|
| `HOLD` | DRONE's HOLD latch: 0 = every HOLD track plays as HOLD OFF | 1 |
| `LABELS` | the load labels' events (DSP / CPU / RAM): 0 = none lit (forced ones still show) | 1 |
| `ARMTIME` | seconds without a command before key injection disarms (30..1800) | 300 |

The DSP's skip switches (FDN8 `QUIET_GATE`, the A2 quiet skip, the chain skip, the inserts' deadline guard,
`ONE_VOICE`, `CLEAR_SPREAD`) are compile-time in the SHARC code. A runtime word there would put a test on the audio
path, so they stay build switches: their A/B is two builds (`--peak` on each, then `--peak-compare`).

## How it works (measured in the OS 1.12 image; addresses only)

- **Screen.** 128 x 64, 1 bpp, two 1,024-byte buffers behind pointers at `0x402a10c8` (front) and `0x402a10cc`
  (back); `panel_diff` (`0x40131fd2`) sends the just-drawn front's changes to the glass and swaps them, so between
  swaps the back buffer is the frame on the glass (untouched) and the front the one being drawn. Column-major:
  pixel (x, y) is bit `y % 8` of byte `8x + 7 - y/8`. SCREEN copies the glass's buffer whole (the pointer must not
  move and two reads must hash the same),
  then serves it in 8 chunks of 128 bytes; a mirror polls the hash and fetches only changed frames.
- **Keys.** The panel is a separate controller on UART8; vector 154's handler (`0x40001f1a`) calls the
  receive callback `0x4011ffbc` once per byte. A button byte (tag 2) carries a channel's whole 8-bit state and goes
  to `0x4011fc8c(channel, mask)`; an encoder byte (tag 3, a signed delta) to `0x4011ff0c(encoder, delta)`. These
  compare with the channel's last state (`0x445a2e30 + channel`) and post the UI's events through the OS queue.
  The test build calls the same two handlers from the UI task with interrupts masked, with the injected bit set in
  (or cleared from) the channel's real state. Button codes: `channel*8 + bit + 1` for channels 0..5; channel 6
  holds LEVEL, VOICE, ARP, PLUS, STACK, MINUS.
- **Time.** Key timing uses the panel module's tick (`0x466768b0`, bumped by its timer callback `0x4011f8bc`): the
  clock the UI's hold test uses. **It wraps**: the callback takes 4,096 off it past 4,095 (`0x4011f9aa`), about every
  34 s at the unit's 121 ticks a second. The test channel runs on the tick unwrapped (stepped every UI pass).
  `remoteui-1` did not: on the unit a FUNC+SRC sent at tick 4,085 kept FUNC down for about 10 s past the wrap (the
  blacklist then refused a YES "with FUNC held", as it should), and its auto-disarm cannot fire after a wrap;
  `remoteui-2` fixes both. The rate is measured against the audio frames (1,500 a second) and reported by BUILDINFO
  and STATE; `dn2test smoke` prints both.
- **Cost.** Nothing runs in the audio interrupt but one load and test (the HOLD switch, at a note-on). The
  commands run in the MIDI input task; the key queue in the UI task, once a pass.

## Verified, and not

Verified without the unit: the firmware compiles with the build's flags (no scale-8 addressing, no jump tables in
the dispatch); the preflight family (preflight, code fresh, DSP identity, DSP hardware rules, symbols, ColdFire,
Overbridge) passes on the build; the tools' 46 tests on the simulator (protocol golden bytes, the firmware's rules
read from the C, the handshake, auto-disarm, key-up, the blacklist on both sides, the screen readout, the CLIs, a
UI scenario file).

**Emulator (gpufarm, the build's own 800M snapshot, 2026-11-11, build `60ffcf64`):** every command answered
through the stock SysEx router; the SCREEN readout of five screens equals the glass's buffer and the panel's own
captured frame **pixel for pixel** (0 of 8,192 differ, hash checked); the arm handshake armed; a KEY FUNC+SRC opened
*MACHINE SEL > TRACK 1*, NO closed it, encoder A reached the UI (TUN1's label turned into its value; the value read
0.00 after +5 detents, not explained yet); SETTINGS refused at the message (status 4), YES refused while FUNC was
held (traced), every injected key went up at its time; no fault. The emulator's panel tick runs about one tick per
1.1 M instructions, so its key times were given in ticks there (a 4-tick FUNC, a 1-tick tap); on the unit they are
milliseconds at the measured rate.

Not verifiable without the unit: whether a real panel byte interleaves with an injected event (the design masks
interrupts for the call), the real USB SysEx round trip and the mirror's frame rate, the panel tick's rate on the
unit, switch effects on sound, the audio thresholds.

## Measured on the unit (2026-11-11, build `remoteui-1`, sha 60ffcf64)

- **Read path:** every read command answers in 1.3 ms a round trip; a whole screen in 9.4 ms (the hash poll 2 ms);
  the readout is the glass's frame. Panel tick 121 a second (against the audio frames).
- **Keys:** FUNC+SRC opens MACHINE SEL, NO closes it, TRK+T*n* selects track *n*, UP/DOWN/LEFT/RIGHT/YES walk and
  pick in the machine lists (LEFT/RIGHT switch SYN / FLTR). The whole test project of `docs/device-tests.md` was set up
  this way, screen-checked step by step (STATE's machine and insert types confirm it). FUNC+FLTR is the kit SETUP menu.
- **Quirk:** the first FUNC+SRC after a machine change (on any track) does not open the list; a second one does.
- **Encoders: the UI accelerates.** The handler adds the injected count to the encoder's pending turn and the panel's
  timer posts it (clamped to ±30) as one event; the UI turns that into a value change that grows faster than the
  count: one −1 a step changes nothing, two −10 moved PROB by 3 %, two −30 by 30 %. A turn of ≥ 300 counts reaches
  any end (HOLD ON, GLID 10 s). The first turn after a pause, or on a popup list, only shows the parameter. Our
  INSERT page's M.SEL takes the counts about 1:1. Exact values need a closed loop (turn, read the screen, turn).
  The encoder's push makes the handler ignore turns for 39 ticks (a debounce).
- **Bug found and fixed in `remoteui-2`:** the tick wraps at 4,096 (Time, above).
- **Host:** a `dn2ui` call once hung for 2 minutes after its last reply; ports now close with a 2 s limit, and a
  KEY that finds the queue full waits and retries.

### remoteui-2 on the unit (2026-11-11)

- A TRK hold of 800 ms sent 30 ticks before the panel tick's wrap went down at 8,143 and up at 8,239 (unwrapped);
  ARMTIME 30 s auto-disarmed at 30 s across a wrap (traced as a timeout). Both remoteui-1 bugs are fixed.
- **USB audio:** under remoteui-1 the Mac's input "Elektron Digitone II" carried a full-scale ~500 Hz square wave
  even with nothing playing (the unit's own outputs sounded normal, USB CONFIG USB AUDIO/MIDI); after the reflash it
  reads silence at rest and real notes when played. Cause not found; remoteui-1's audio results are void. The
  Overbridge Engine app ran on the Mac throughout (started 2026-11-09 05:16, pid 79683): while the square was there
  and also after the reflash, when the input was clean. A correlation at most, not a cause.
- a_level on remoteui-2: every track sounds except the A2 SVF, OTA, DIODE and MS-20 tracks (-113 .. -72 dBFS; LADDER
  -57). The levels range from -113 to -0.5 dBFS between tracks with the same machine: the machine changes kept each
  track's old sound (FM TONE presets on 1..8, SWARMER SYNTHVAG on 9..16: amp, filter frequency, levels), so these say
  nothing yet about the firmware. Next: an init sound on each track, then the levels again. The click detector
  counts a raw saw's reset as a click (TB-303 33/s, SOPHIE 51/s): it needs tuning before its verdicts count.

### remoteui-3: no load labels while flashing (2026-11-11)

The User: the labels while flashing are "not relevant and scary". `smp_rx` sees every USB SysEx but `F0 7E` (the
router hook); an Elektron SysEx of 128 bytes or more that is not the test channel's (an OS upgrade from Transfer
arrives as a stream of them, the RPC's OsUpgradeWrite; sample and project transfers too) marks the time, and the
labels (DSP, CPU, RAM and the "!") stay off until 2 s after the last one (`smp_bulk_recent`, link.c; meter.c
`icons_live`). Verified in the emulator: the three labels and the "!" forced on, one 200-byte Elektron SysEx through
the router, the next screen shows none (readouts `L0`, `L1`). Not verified: a real OS upgrade (the User sees it on the
next flash; the window cannot be timed in the emulator, whose frame counter stands still). The loadicons branch's "!"
must test `smp_bulk_recent()` too when it is merged.

## The CPU profiler (remoteui-5)

**What the ColdFire spends its time on, on the unit, by scenario.** PROFILE (SysEx 43,
`docs/remote-ui-protocol.md`) samples the interrupted PC about a thousand times a second into a ring in our
own RAM; `dn2test profile` reads it after the run and maps every PC to a function (stock 1.12's from an objdump
of the user's image, ours from the build's `waverider_code.json`). Disarmed at power-on; nothing runs until a
START, and the ring stops when full (65,536 samples: 66 s at 997 a second).

    dn2test profile --seconds 30 --label idle --out prof/ --stock-bin section_3_MAIN_OS.bin --ours waverider_code.json
    dn2test profile --seconds 30 --label dense --out prof/ --stock-symbols prof/stock_symbols.json --ours ...
    dn2test profile --compare prof/idle.json prof/dense.json

The report: **idle %** (samples at the idle task's spin) and busy %, the meter's C label during the run beside
it, the top functions, the split by interrupt mask (task code vs inside an interrupt, by level), the tasks (by
the running TCB, each with its top functions), the samples' lateness, the profiler's own cost and the sample
rate, all measured. `--compare` puts two runs side by side per function: the owner's question (does stock load
the ColdFire the same at idle and at full load?) is answered by comparing an idle run with a dense one; the
headroom for new work is 100 % minus the busy % of the heaviest scenario.

**The build** (UNGATED: the preflight family and the emulator only): `remoteui-5`,
`DN2mod_v0.47-ours-NOBOOT-1.12-combined-remoteui5-profiler_UNGATED_OS1.12.syx`, sha256 `7e8bf07e…`; packed upgrade
image 2,093,831 of 2,097,152 B (**3,321 B left**; remoteui-4 2,092,417 B: the profiler costs 1,414 B packed). Its code in the C
chunk: 2,294 B (`0x46ade1a8..0x46adea9e`, prof.c and prof.S); its RAM (1 MB at `0x47100000`, above the DSP's tables) is not in the image.

### The sampling source (measured in the 1.12 image, 2026-11-11)

Every timer the OS owns is taken: PIT0 the RTOS time slice (vector 205, the switcher re-arms it), PIT1 a
microsecond delay, PIT2 the timer wheel (vector 207), PIT3 the display (vector 208), DTIM1 a sleep (vector 97),
DTIM2 counts an external clock (`0x400cedf4` writes its DTMR = 7), DTIM3 the UI's 30 Hz tick (vector 99).
**DMA timer 0** is the one free interrupt: the OS reads its counter at ten sites (the encoders' time stamps, our
meter) and **never writes any of its registers** (no code names `0xfc070000`..`0xfc070008`; the boot leaves it
counting at the bus clock, 132 MHz, the OS's own 10 s test is 1,319,999,999 ticks); its interrupt source (INTC0
source 32, ICR `0xfc048060`) is never set up and vector 96 (`0x40000180`, VBR `0x40000000`) stays the default
handler `0x40001252`. So the profiler (source **TIMER**, the default) uses only its **reference compare** in free
run: the counter is never stopped or reset (every reader of it is unaffected), each sample sets the next
reference at now + period ± period/16 (a 16-bit LFSR: no lock to the 1,500 Hz audio frames or the 120 Hz wheel),
at **interrupt level 6**, above the audio interrupt's 5. START refuses (status 6, with the reason) unless the
timer is exactly as the boot left it and nothing else uses its interrupt; STOP (or a full ring) masks the source
first, then puts back DTMR0.ORRI, DTRR0, ICR32 and vector 96.

Level 7 would see more but is not safe: it is non-maskable, and the context switch (`0x40000410`) and other
masked code store below SP; a level-7 frame would overwrite those words.

**Bias, TIMER.** Invisible: everything that runs with the mask at 6 or 7: every `move.w #0x2700,%sr` critical
section, and the level-6 / level-7 handlers (vectors 66, 168, 170, 209, 221: the ICR writes in the image). A
sample due inside such a section is taken when it ends, so its time lands on the instruction after the unmask;
the record's `late` measures that delay for every sample (the report's lateness: median, p95, p99, max).
Inside the audio interrupt (level 5) is seen: its share of the samples is the audio interrupt's share of the
CPU, by function.

**Fallback, AUDIO** (`--source audio`, or automatically when the timer is refused): the PC the audio interrupt
interrupted, read from its exception frame (`0x40025e36: link %fp,#-236`: the frame at `%fp + 4`) in the sample
link's hook, every k-th frame (1,500 / k a second). Its bias is large: the audio interrupt's own time (about
half the CPU) and anything at level 5..7 is invisible, and the samples are locked to the audio frames. Disarmed,
it costs the audio interrupt a load and a compare a frame.

**Cost.** The handler measures itself: the DTIM0 ticks from its first instruction to its last, summed (status
`isr ticks`; the report's "the profiler's own handler"), the exception entry and `rte` aside. In the emulator it
is 105 instructions a sample, from the interrupt's delivery to the `rte` (the same for every sample of every run). Each sample writes 12 bytes into the ring (cached DDR at `0x47100100`): about
one cache line allocated per sample. The host polls STATUS and TLM once a second during the run (two round trips,
about 3 ms of the MIDI task a second); those show up in the profile as the MIDI task's functions.

**Idle.** The idle task is TCB `0x4243d900`, prio 1, entry `0x400cedfc` (its TASK_CREATE at `0x400ced30` in 1.12):
after the boot's setup it parks at `0x400cf246: bra.s *` (the CPU never sleeps: no `stop` in the image). The prio-0
task (`0x400ced18`, TCB `0x424398ac`) creates it and parks at its own `bra.s *` (`0x400ced46`); prio 0 never runs.
A sample is **idle** when its PC is `0x400cf246` and its mask is 0.

### The meter's C and the profiler's idle %: what each counts

The meter (`csrc/meter`, the C label, TLM word 6) is **1 - (idle - audio ISR in idle) / elapsed**, in DTIM0 ticks
over half a second: *idle* is the time the idle task held the CPU **parked at its spin**, credited at the context
switch (`mtr_switch` at `0x40000438`: from the switch in to the switch out, only when it switches out from
`0x400cf246`); *audio ISR in idle* is the audio interrupt's time from the link hook (`0x40026098`) to its frame
count (`0x40027b82`) when it interrupted the idle task. So busy = not parked in the idle task, with the audio
interrupt's measured part taken out of idle. **What it counts as idle that is not:** every other interrupt that
lands while the idle task is parked (the timers, UART, USB, the eDMA's vector 170, ... and the profiler's own
handler), and the audio interrupt's entry up to the link hook (its register save and transmit fills).

The profiler's idle % counts **only** samples at the spin with the mask at 0: an interrupt that lands in the idle
task is sampled as that interrupt (busy). So the two should agree to within (a) those interrupts' time inside idle
intervals (the profiler's busy % reads higher by it), (b) the sampling error (±1.6 % at 95 % for 4,000 samples
near 50 %), (c) the profiler's own cost (counted idle by the meter, invisible to the profiler), and (d) the masked
sections' time, which the profiler moves to the instruction after the unmask (busy either way). A difference larger
than that is a finding, not noise. Not measured yet: no run on the unit.

### Verified in the emulator (2026-11-11, build sha 7e8bf07e, source 51e60ea3 + docs)

The emulator models neither DMA timer 0 (its counter reads 0, its mode 0) nor INTC SIMR / CIMR, so the
`dt:profile:*` steps (`scripts/emulib/prof.py`) set DTMR0 to 0x0003 (as the unit's boot leaves it), model SIMR /
CIMR for source 32 only, and raise vector 96 at level 6 at the end of each run slice when the firmware has armed it
(and the CPU's mask is below 6), as the timer would. On the build's snapshot (`ui800M-v014` with this build
installed; the bench container, and the same steps in `scratch/remoteui/farm_ru.sh` for gpufarm):

- START took the timer: vector 96 became `prof_isr`, ICR32 6, the source unmasked, DTMR0 `0x0013` (ORRI set),
  DTRR0 the next due time. STOP put back every one of them (vector `0x40001252`, ICR 0, masked, DTMR0 `0x0003`,
  DTRR0 as found). `faults []` in every run.
- UI alone, 40 slices of 200,000 instructions: 40 interrupts, **40 samples, every PC the one the interrupt was
  raised at**, all in code: 39 at `idle_spin` (`0x400cf246`), 1 in `isr_vec155` (the panel UART's handler).
- With the audio interrupt running on its own (`--isr-frame 75000`: 702 frames, 39,711 instructions each on
  average), 300 slices: 293 interrupts (7 held while the mask was 6 or 7), 293 samples, every PC the raised one,
  masks 0, 1 and 5: **the timer samples inside the audio interrupt** (`fn_400db28e`, `fn_400db340`, the mirror
  apply) and the tasks (`fn_40137a06`, `fn_40134770`, our `smp_status`, `rtos_switch`), 245 at `idle_spin`.
  The shares are the emulator's (samples fall at the harness's slice ends, its time is an instruction count):
  they say nothing about the unit.
- AUDIO source: 133 samples from the audio interrupt's own frames (one a frame, the source asked at 1,500 a
  second), every one at `0x400253ce`, mask 6: the `rte` of the vector-170 callback (`0x40025386`) that forces
  vector 191. In this emulator the forced interrupt is taken before that `rte`; on the hardware a level-5 request
  waits until the level-6 handler's `rte` has lowered the mask, so its frame holds the code vector 170
  interrupted. Called as a function (`isr:3`) the hook records 3 samples (the gate and the ring work; the frame
  there is not an interrupt's).
- `late` is meaningless here (the counter stands still): every sample counts as late.
- **gpufarm** (`scratch/remoteui/farm_ru.sh`, the build's own snapshot: `boot400M` with this build installed, run to
  800M): booted from reset to 800M instructions with no fault; the earlier test channel steps unchanged (seven
  screen readouts equal the glass's buffer pixel for pixel, SETTINGS refused, KEY / ARM / PEEK as before); the
  timer source on the UI alone, 300 slices: 300 samples, every PC the raised one, all at `idle_spin`; with the
  audio interrupt (`--isr-frame 75000`, 702 frames): 294 samples (6 held by the mask), every PC the raised one,
  **259 at mask 0 and 35 at mask 5** (inside the audio interrupt: `fn_400db28e`, `fn_400db340`), 250 at
  `idle_spin`; the audio source 134 samples (as above); 105 instructions a sample; a START while one ran and a
  CLEAR while it ran were refused with status 5; `faults []` in every run.

Not verifiable without the unit: DTMR0's real value (the emulator's reads 0; the boot's setting is read by START
and in every status), the sample rate and lateness, the handler's cost in ticks, the idle % and its agreement
with the meter, the AUDIO source on a running audio interrupt.

## Troubleshooting

- `no MIDI port with 'Digitone II'`: USB CONFIG (above); another program (Overbridge, a DAW) holding the port;
  `--port` with part of the name `mido` lists.
- `no answer to BUILDINFO` / `no test channel`: stock firmware or a build without the test channel: flash the test build.
- `status 3 (not armed)`: `dn2ui arm`; it disarms after ARMTIME s without a command.
- `REFUSED`: the blacklist (Safety).
- The mirror is slow: each frame is 9 round trips; `--fps` lower; the hash poll alone is one.

## Licence and contents

The repository's licence (AGPL-3.0-or-later). No Elektron code or bytes here or in the tools: addresses, offsets,
and cycle counts only; stock firmware images are supplied by the user and never shipped. The key names are the
panel's printed labels.
