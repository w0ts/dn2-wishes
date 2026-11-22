# The system meter (OS 1.12 fork, not released)

**[TEMPO] held a second** (2026-11-21, the User: "on a long press of the METRONOME button and not FUNC
click-and-hold"; the DN2's metronome is METRO on the TEMPO screen; 2026-11-19..21 it was FUNC tapped then pressed
again, "one click and a half"). Stock 1.12 acts on [TEMPO]'s release only (the TEMPO screen), so the release of that
hold is dropped (csrc/inserts/ovw.c); a tap still opens the TEMPO screen, FUNC + [TEMPO] is still tap tempo. While
held, a black box
over the page body (rows 0..53, under the title bar) shows three rows, each named in large letters, with a large figure
and a bar 74 px long filled to it:

    DSP  42  ##############|          (| : the peak tick, the last 3 s's highest, on DSP and CPU)
    CPU  61  ###################|
    RAM   9  ##

It goes when that second press is let go: one full redraw, stock's page back as it was. **A plain FUNC hold shows
nothing**, so FUNC's combos are quiet again. If any other key is pressed, a knob is pushed or an encoder turned while it
is up, the meter goes at once and that input is FUNC + it, exactly as without the meter: nothing is taken, held back or
added (every FUNC item goes on to stock, the first tap's included). A figure not known yet reads `--`: its bar is a
dotted floor and it has no tick.

The gesture (`mtr_key`, csrc/meter/meter.c, called first for every UI item by rec.c `smp_ui_pop`): the first press is a
tap when it is let go within 0.35 s (`TAP_MAX`, 525 frames) with no other key press, push or turn between; the second
press must come within 0.35 s of that release (`TAP_GAP`). A slow double tap, a long first press, or anything between
the two: no meter. Timed by FRAMES (1,500 a second).

**Stock and FUNC double taps (checked before building, 2026-11-19).** Stock 1.12's key task marks a key's second press
within its own window with flag bit 2 (`0x5`, its repeats `0xd`; read in the emulator from the UI queue's items). Its
one reader is the key event's accessor `0x4011637c`, called from five places only: `0x4005a0a2` and `0x4005f3ca` (code
2, SRC), `0x40073068` (code 21, STOP: reached by a STOP double tap in the emulator), `0x4007e766` and `0x4008095e` (code
24, SONG; their switches' jump tables decoded). None for FUNC (code 17), whose cases go elsewhere in both switches. In
the emulator (stock 1.12, `ui1200M`), on TRIG, SYN, FLTR, AMP, FX and MOD: a FUNC tap changes nothing; a fast double tap
with the second press held shows exactly what a plain FUNC hold shows (FLTR's ATK reads DEL while FUNC is down), and
nothing after.

**On the send Delay (XDLY) and Reverb (FDN8, LONG) pages** a FUNC tap switches page 1 <-> 2 (csrc/fxpage): the gesture's
first tap does that too (it reaches everything, as any tap); the release that ends the meter is not taken as a tap
(`mtr_func_ended`), so those pages switch once.

**Drawing.** Rows of 16 px on page boundaries (DSP pages 4-5, CPU 2-3, RAM 0-1): the word (x 1..26; the User,
2026-11-19: "DSP", "CPU", "RAM", not D / C / M) and the figure (right-aligned, x 29..50) at twice the labels' 3 x 5 glyphs
(M 5 wide), the bar at x 53..126 (74 px; 90 with the one-letter names), 8 px high, the tick 12 px. The meter's coming, and every full draw of
stock's while it is up, draws the box whole (`mtr_draw` after everything of ours but the overviews). Every quarter
second (`REDRAW`) `mtr_poll` draws again only the rows whose figure or tick changed, into BACK (the frame on the glass),
and sends only their changed 8-pixel groups through stock's sender (`big_update`, as the load labels' blink and the
moving lines); nothing changed, nothing sent. While it is up nothing of ours is drawn alone under it: page.c `wr_poll`
does not call the moving lines', the scope's, the routes popup's or the DEST popup's polls (any key or turn takes the
meter down before any of them could be needed); the list popup's poll now runs before them, so those four come last
under one test. The title bar stays stock's, with the load labels.

| | what | from |
|---|---|---|
| **DSP** (D) | the DSP's load, percent, the last half second's peak; `--` with no reading for a second | the SHARC's idle packets, unit 18 (`guard.meter`, v0.32), `link.c` `smp_dsp_load()` |
| **CPU** (C) | the ColdFire's load, percent, over the last half second; `--` before the first window | idle time credited at the context switch (the idle task's spin and, since 2026-11-17, stock's prio-2 file worker), less the audio ISR's time inside it (`csrc/meter/hooks.S`, usbprobe's method, `docs/usbprobe.md`) |
| **RAM** (M) | the main buddy heap's used share, percent: 1 - free / total | free: the heap's free lists walked under its own mutex, as digihealth walks it; total: the heap descriptor's `+0x14` in 16-byte units (stock 1.12: `0x200000`, 32 MB = 2^ the top order 21, read in the emulator) (`csrc/meter/meter.c`) |

**Checked (2026-11-19, the 1.12 emulator, build 09e11dfe on its own snapshot).** `meter` (ship_gate): a FUNC hold
alone and a slow double tap (1,000 frames) show nothing and leave the page as it was; tap + hold 300 frames apart shows
the meter; its release brings the page back as it was; FUNC + SRC with it up takes it down at the SRC press and opens
MACHINE SEL exactly as a plain FUNC + SRC. `lineonly` `bigmeter`: also a long first press (900 frames); the meter over
rows 0..53 only (the title bar untouched); every quarter-second update alone (18, 10, 0 and 39 groups: nothing sent
when nothing changed), the glass always what a full redraw draws; lines moving under it change nothing on the glass;
its release leaves the page body exactly as before it; an encoder turn takes it down. Main's build (3c0ef6a8) fails
these.

With the rows named in words (build b09ec5e6 on its own snapshot, 2026-11-19): `meter` and `lineonly` pass, `bigmeter`
also checking columns 0..28 of each row hold exactly DSP, CPU, RAM at twice the glyphs; the updates alone sent 16, 12, 0
and 37 groups.

Costs (emulator instructions, `lineonly` `costs` and one traced pass, WaveTone's SYN page at rest):

| | main 3c0ef6a8 | this build |
|---|---|---|
| UI pass (wr_poll), meter down | 4,656 (one traced pass: 4,667) | 4,650 (4,661) |
| full draw + panel_diff, meter down | 113,359 | 113,361 |
| UI pass, meter up, nothing due | | 4,679 |
| UI pass with a quarter-second update (alone) | | 27,544 / 34,061 / 29,184 |
| full draw + panel_diff with the meter | | 153,414 |

The audio frame's part (`mtr_isr_out`, `mtr_switch`) is the same code as main's. `mtr_key` costs about 10
instructions for each UI item that is not a key or a knob, about 20-30 for a key's. The page keys' latency
(`emu_page_keys.py`) is unchanged to the 0.1 ms.

The heap is walked as the meter comes and then once a second while it is up (every 2 s otherwise, for the RAM
label). The PERC/MnM pages' DSP % in the tempo's place (v0.32) is unchanged.

## Where it hooks (stock 1.12, each byte-checked by `coldfire.compose`)

| site | stock bytes | to |
|---|---|---|
| `0x40000438`, the context switch | `203cffffdfff` (move.l #0xffffdfff,%d0) | `mtr_switch` |
| `0x40027b82`, the audio ISR's frame count before its rte | `52b94058f8d4` (FRAMES, 1.11's +0x1000) | `mtr_isr_out` |
| (no new site) the link's existing ISR hook `0x40026098` | | `smp_tdm_hook` stamps `mtr_t_in` |

**The ISR's start is the link hook, not the ISR's entry.** The ISR's instructions from its
entry `0x40025e36` up to the link hook are Overbridge's audio path, which the build never
touches (v0.41, `scripts/gate_overbridge.py`; a first version hooked `0x40025e3e` and that
gate refused it). So the ISR time subtracted from idle runs from the link hook to the frame
count: the entry, the register save and the transmit fills before the hook count as idle when
they interrupt the idle task, and **C reads low by their share** (unmeasured; usbprobe, which
timed the whole ISR on 1.11, read 58-61 %).

Data: `CUR_TCB` `0x4664bcdc`, idle task (prio 1) TCB `0x4243d900` parked at `0x400cf246`,
DTCN0 `0xfc07000c`, heap control block `0x4029f0dc` (+4 units base, +0xc free-list heads,
+0x10 top order), its mutex `0x445e2e40`, take `0x40001608` / give `0x4000172a`. None is in
the uncached `0x4e…` block stock 1.12 moved by +0x8000. Proof of each address against stock
1.12 and 1.11: dn2mk2-scratch `docs/meter-plan.md`, `bench/map112.py`. The drawing runs from
`wr_screen` and `wr_poll` (`csrc/waverider/page.c`).

**State: in RAM above BSS, not in the code chunk.** The counters and figures live in the
meter's own 256-byte block at `0x46aff000` (`pages.METER_RAM`, between the MD graphics and the
pool's mirror, declared by `dnfw.mods.waverider.ram`), zeroed by the first poll (magic `MTR1`).
A first version kept them in the C chunk's `.data`: the switch hook writes them at every
context switch, and the gate's `engine` step (every CODE chunk must stay the loader's image)
failed on it.

Cost: two new sites and two instructions in the link hook; the C chunk +~1.1 KB; USB image +1,111 B
(11,603 B left under the 2 MiB limit). No DSP code.

**The bars (2026-11-08, the owner on the unit: "make the meter visual").** The bar is the
figure itself; the tick on D and C is its highest value over the last 3 s (`PEAK_HOLD`, kept
in the meter's RAM block). D's figure was already the half second's peak, so its tick holds
that peak longer. Emulator screenshots with C and its peak poked (the emulator has no DSP and
no audio ISR, so D reads `--` and C is not measured there): a stock page, PERC, the
Monomachine VO-6 and a sample page, each with FUNC held and after the release.

## Checked, and not

(Until 2026-11-19 the meter was a corner of the title bar, x 74..127, shown while FUNC was held; the first checks below
are that version's.)

- Emulator (1.12, `ui800M-v014`): the corner on a stock page, PERC, SID and a sample page; with
  FUNC up every page equals the base build's (1cc3084) pixel for pixel, and after the release it
  equals the page before the press; the number formats (D63 C61 H812K, D100 C0 H10M) with the
  values poked (and H1.5M); a run of about 4,000 M instructions with ten FUNC presses: no fault, 0 heap-walk
  faults, the switch hook counting (226,622 switches). `gate_overbridge.py`: 0 of 1,907 Overbridge path instructions touched.
- **Not checkable in the emulator:** the C and D values (it runs no audio ISR and holds DMA
  timer 0; no DSP), so the CPU figure reads `--` there. On the unit, usbprobe read 58-61 % on
  1.11; 1.12 is unmeasured until the owner holds FUNC.
- Gate on 1.12 (meter build c7a11b44 vs base 80d35b4b, 2026-11-08): every step that passes on
  base passes on the meter build, except `engine` (fixed above) and `erase` (flaky: passed on
  rerun). After the fix (fa4bb891): engine, coldfire, overbridge, hooks, meter, code-fresh,
  preflight, erase pass. The SHARC steps failed on both builds for a missing cached init
  snapshot in the fresh trees; the DSP is unchanged.
- Not on hardware yet.

## The load labels (2026-11-10)

The User: "a little shark/cpu/memory icon blinking when we are over dsp/cpu/memory, on the right of the
title bar"; drawn icons were tried and refused ("they dont work... what about CPU / DSP / RAM ?"). So, on
every page (stock's and ours), the title bar's right end shows a word in a black box for
each limit hit, while it is and a second after (`ICON_HOLD`), blinking at 2 Hz; the lit ones packed to
the right, over the tempo, which comes back when they go; one `!` in its own black box at the group's left
while any is lit (something is over its limit). (Until 2026-11-19 a held FUNC's corner covered them; the big meter is
below the title bar and leaves them shown.)

| label | lit when | from |
|---|---|---|
| **DSP** | the DSP's guard left a voice out for time, or passed an insert block through for time; or the DSP's load peak at 99 % (`ICON_DSP_PCT`, off under 97 %; the unit idle reads D 94 %) | voices: the idle packet's unit 17 (`smp_skipped_any`); inserts: **unit 23, new**, the guard's `INS_SKIPS` count (`sampler/program.py`, 3 DSP instructions; `link.c` `smp_ins_skip_at`); load: unit 18 |
| **CPU** | the ColdFire's load over the last half second at 90 % (`ICON_CPU_PM`, off under 85 %) | the meter's C (`cpu_window`, computed every half second, FUNC or not) |
| **RAM** | an FDN8 / XDLY insert found no instance free (FULL), or the main heap 90 % used (`ICON_HEAP_PCT`) | `ins.c` `ins_full_any`; the heap walked every 2 s (`ICON_HEAP_EVERY`) under its own lock |

The PERC / Monomachine pages' "CPU" under LEV (v0.30) is gone: LEV always reads LEV, the title bar's DSP
says it (the User). State: the meter's RAM block, words 25..29 (`MTR_ICON_*`); `MTR_ICON_FORCE`
(`METER_RAM + 0x74`, bits D C M) shows a label steadily, for the emulator's screenshots (no DSP, no audio
ISR, a frame counter standing still there). Not measured: the audio ISR's lateness, a task's deadline.
Not on hardware yet; the thresholds are first guesses.

### Stock's file worker counts as idle (2026-11-17)

The User, v0.57.1 on the User's DN2: "creating / initialising a new project shows an error popup", the project made and
working. Measured on the unit (remote UI, a8fbf921): no stock ERROR anywhere; the box was this meter's "!CPU".
Stock's project work runs in its file worker, the one task at prio 2 (TCB `0x42c6a1d0` on the unit and in the
emulator, made at run time; its +8 is its ready-table slot `0x4664bca4` = `0x4664bc9c + 4 * 2`): a LOAD's read,
its working-copy write for ~15 s after the load bar, INIT NEW's "CLEARING...", SAVE. Prio 2 runs only when every
task above it waits, so its time is time nobody else wanted; counted as load it read C 100 % for ~17 s on a
LOAD (a 24 s profile: 18 % the worker's, 71 % at the audio interrupt's level; idle C 73 %, a separate report)
and lit the label. Now `mtr_switch` opens the idle interval for the worker as for the idle task (all of the
worker's time; only the spin for the idle task), and the audio ISR inside it still counts as load. C is the
load of every task above the worker. Gate: `newproj` (`ship_gate.py` 6n2): CREATE NEW and INIT NEW through the
panel, SUCCESS and no ERROR, no fault, and every switch into the worker opens the interval (on a8fbf921: 94
switches, 0 opened).

### The CPU label while stock loads or upgrades (2026-11-14)

The User: "Disable during firmware upgrade and until loading notification is gone". CPU lit at boot while
"Loading..." showed and while an OS upgrade arrived: stock busy on purpose, not over a limit. While
`mtr_quiet_why()` (`csrc/meter/quiet.c`) says stock is loading or upgrading, the CPU label stays unlit, its
hold and its hysteresis cleared; after, it reads C again only from the second half-second window after
the quiet (`CPU_FRESH`), never from the load stock had meanwhile. DSP, RAM and the meter's C are
unchanged. Pure reads of stock's own state, no hook. Each address traced in stock 1.12's code:

| state | stock 1.12 | quiet while |
|---|---|---|
| loading | the view at `*0x44648980` (weak_ptr, control block `*0x44648984`, +4 its use count; built by `0x40060e72`, 0x228 B, +504 = 0 and +508 = -1 there). That constructor installs the lambda `0x4005e28a` (every tick, capturing the view): not ready, +504 counts up and at 2 posts "Loading..." (`0x402161d7`) through SAY `0x4005628c` on +156; ready, +504 = 0 and +508 = -1 (`0x4005e380`). `0x4005bd70` animates +508 (0..9) while +504 > 2 | the view never built (boot); or held (use count > 0) with +504 not 0 or +508 not -1. A view no one holds is not read |
| loading | the title's message line `*0x446488c8` (built by `0x4018b2a4`, never freed): SAY writes its text (a one-pointer std::string) at +72 and its countdown at +76 | +76 > 0 and the text is "Loading..." |
| upgrade | `MidiRpcDispatcher` (RTTI) at `0x445fb5cc`, static, built at the first RPC message (guard `0x445fb6a8`, `0x40125d64`); +4 its `OsUpgradeState` (RTTI, vtable `0x40208548`, +4 cleared by its constructor `0x40129860`). Its +4 is written 1 (`0x401298be`, OsUpgradeStart), 2 (`0x40129f56`, the first write), 3 (`0x4012a10c`, written to flash), 5 (failed or cancelled, `0x40129f5e` and five more); nothing else | 1, 2 or 3 |

The upgrade state is Transfer's route; the bootloader's OS UPGRADE runs without this OS. An upgrade cut off
without a cancel leaves 1 or 2 until the next boot: CPU unlit until then. The emulator's loading workers
never report ready, so there the CPU label stays unlit after boot (the proof pokes the ready branch's
values). Checked: `test/test_meter_quiet.py` (the reads over a model of that memory); the emulator from
`boot400M` with C poked to 950 permille (unlit while loading and while an upgrade's state is 1..3, lit two
windows after).

### The DSP and CLIP labels while the DN2 starts (2026-11-20)

The User, on the mixer-meter build: "at boot it says !CLIP and !DSP... I suppose it's the boot-up, but can we fix
it?". At power-on the labels see the DSP's first reports (the guard's skips and load while every voice and machine
is set up) and the clip word of our DSP program's first blocks, when stock's buffers (the input's block, the main
mix, the send effects) may not have been written yet: not a clip or an overload of the instrument in use. Which of
these lit them on the unit was not measured (a read of `mix_clip_at`, `smp_skip_at` and `smp_load_peak` right after
a boot would tell). `csrc/meter/startup.c` keeps DSP and CLIP unlit from the load (every boot) until stock's loading
is over (`QUIET_LOADING`) and our DSP program has reported (`smp_dsp_load() >= 0`) without a break for 2 s; every clip
stamped meanwhile is forgotten (the label's 3 s and the MIXER pages' latches), DSP's stamp and hysteresis cleared.
After, nothing changes: a clip or an overload lights them at once. CPU keeps its own quiet (above); RAM unchanged.
The emulator's DSP never reports, so there the start-up never ends by itself: the checks that light the labels set
`mtr_start_done` first (`emu_mixmeter.py`, `emu_line_redraw.py` labels). Checked: `test/test_meter_startup.py`;
`emu_mixmeter.py` (start-up: a clip and a 100 % load unlit and the clip forgotten while the DSP is silent and for 2 s
of its reports; after, DSP and CLIP lit at once, as the forced labels draw them).
