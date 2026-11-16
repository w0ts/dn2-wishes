# The system meter (OS 1.12 fork, not released)

Hold **FUNC** on any page: the title bar's right end (a white box, x 74..127, rows 54..63)
shows three columns, each a figure over a bar 16 px wide filled to it:

    D42     C61     M9
    ######| ######:|  #       (| : the peak tick, the last 3 s's highest, on D and C)

A figure not known yet reads `--`: its bar is a dotted floor and it has no tick.

| | what | from |
|---|---|---|
| **D** | the DSP's load, percent, the last half second's peak; `--` with no reading for a second | the SHARC's idle packets, unit 18 (`guard.meter`, v0.32), `link.c` `smp_dsp_load()` |
| **C** | the ColdFire's load, percent, over the last half second; `--` before the first window | idle time credited at the context switch, less the audio ISR's time inside it (`csrc/meter/hooks.S`, usbprobe's method, `docs/usbprobe.md`) |
| **M** | the main buddy heap's used share, percent: 1 - free / total | free: the heap's free lists walked under its own mutex, as digihealth walks it; total: the heap descriptor's `+0x14` in 16-byte units (stock 1.12: `0x200000`, 32 MB = 2^ the top order 21, read in the emulator) (`csrc/meter/meter.c`) |

Let go of FUNC and stock's screen comes back as it was (one redraw at the release). While
FUNC is held the corner is redrawn 4 times a second. The heap is walked at the press and then
once a second; nothing is walked or drawn while FUNC is up. The PERC/MnM pages' DSP % in the
tempo's place (v0.32) is unchanged.

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
every page (stock's and ours) while FUNC is up, the title bar's right end shows a word in a black box for
each limit hit, while it is and a second after (`ICON_HOLD`), blinking at 2 Hz; the lit ones packed to
the right, over the tempo, which comes back when they go. FUNC held: the meter's corner covers them.

| label | lit when | from |
|---|---|---|
| **DSP** | the DSP's guard left a voice out for time, or passed an insert block through for time; or the DSP's load peak at 99 % (`ICON_DSP_PCT`, off under 97 %; the unit idle reads D 94 %) | voices: the idle packet's unit 17 (`smp_skipped_any`); inserts: **unit 23, new**, the guard's `INS_SKIPS` count (`sampler/program.py`, 3 DSP instructions; `link.c` `smp_ins_skip_at`); load: unit 18 |
| **CPU** | the ColdFire's load over the last half second at 90 % (`ICON_CPU_PM`, off under 85 %) | the meter's C (`cpu_window`, computed every half second, FUNC or not) |
| **RAM** | an FDN8 / XDLY insert found no instance free (FULL), or the main heap 90 % used (`ICON_HEAP_PCT`) | `ins.c` `ins_full_any`; the heap walked every 2 s (`ICON_HEAP_EVERY`) with FUNC up too, under its own lock |

The PERC / Monomachine pages' "CPU" under LEV (v0.30) is gone: LEV always reads LEV, the title bar's DSP
says it (the User). State: the meter's RAM block, words 25..29 (`MTR_ICON_*`); `MTR_ICON_FORCE`
(`METER_RAM + 0x74`, bits D C M) shows a label steadily, for the emulator's screenshots (no DSP, no audio
ISR, a frame counter standing still there). Not measured: the audio ISR's lateness, a task's deadline.
Not on hardware yet; the thresholds are first guesses.
