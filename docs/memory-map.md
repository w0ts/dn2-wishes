# The MAIN OS memory map

Where the code, its constants, and its runtime state live in the ColdFire V4e
address space, reconstructed from the startup routine and the cross-references.
A visual explorer of this is an Artifact with a version selector (link in the
project notes); this is the written record.

**Two builds are mapped: 1.11 (the target — what the device runs) and 1.10E
(kept for comparison).** Every address moves on a relink, so nothing is shared
between them: each column below was measured from its own image. Never carry an
address from one release to another — the parameter table alone moved ~90 KB.

## The image versus runtime RAM — the distinction that matters

The MAIN OS section is loaded at `0x40000400` and holds **code, read-only data,
and the initializers for RAM** — it is not where the running firmware keeps its
mutable state. The startup code makes this explicit: it copies a region of the
image to external SDRAM and clears BSS there before entering `main`.

**There are two runtime data regions, not one.** An earlier version of this
document said "runtime data lives at `0x80000000`, not in the image". That is
true of the initialized `.data` — about 64 KB — and wrong about everything else.
`0x4000053e` calls the copy routine and *then* the BSS clear, and the BSS clear
covers **~100 MB immediately after the image**, in the same `0x40000000` SDRAM
space:

```
400004ba:  moveal #0x402fc000,%a0    ; BSS start  (1.10E: 0x402e2000)
400004c0:  movel  #0x466b74d0,%d1    ; BSS end    (1.10E: 0x464f47d0)
400004c6:  subl   %a0,%d1 ; asrl #4,%d1
400004d2:  moveml %d4-%d7,%a0@       ; zero 16 B at a time, d4-d7 cleared
```

| Build | BSS start | BSS end | Size |
|---|---|---|---|
| 1.10E | `0x402e2000` | `0x464f47d0` | 102,836,176 B |
| 1.11 | `0x402fc000` | `0x466b74d0` | 104,576,208 B |

BSS starts at exactly the address this map calls the ".data initializer block 1"
— not a contradiction, but an ordering: the copy routine consumes that image tail
into `0x80000000` first, and the clear routine then recycles it as the first
bytes of BSS. A second, independent reason those trailing bytes are not free cave
space.

**The top of SDRAM is `0x48000000`, and 25.3 MB above BSS is unclaimed.**
Measured 2026-09-12, answering the gating question in `docs/ideas-backlog.md`
§6. The C runtime's first instruction sets the stack pointer:

```
400004f2:  moveal #0x48000000,%sp     ; before the .data copy and BSS clear
```

Stacks descend on ColdFire, so that pins the top of usable RAM: SDRAM spans
`0x40000000`–`0x48000000`, **128 MB**. BSS ends at `0x466b74d0`, leaving
**26,512,176 bytes (25.3 MB)** between the two.

That window is genuinely unclaimed, by three independent measurements:

| Evidence | Result |
|---|---|
| Immediates naming an address in `[BSS start, top of RAM)` | **7,043** — BSS is densely named |
| The highest of them | `0x466b7420`, `0x466b7456`, `0x466b748c` — **within 68 bytes of the BSS end** |
| Immediates naming anything **above** the BSS end | **none** |

The four values the scan returns above `0x466b74d0` are not addresses:
`0x466b74d0` itself is the clear loop's own bound, `0x474e5543` is the ASCII
`"GNUC"`, and `0x47efffff` (twice) is a float constant. Statics climb to within
68 bytes of the BSS end and then stop dead — which is what a linker-computed
`_end` looks like, and means **the heap is a static arena inside BSS, not a
region above it.** That is also why BSS is 100 MB: it is globals *plus* the
pool.

So the window's only occupant is the stack, descending from `0x48000000`. Its
depth is unmeasured. **The safe end of the window is therefore the bottom** —
just above `0x466b74d0`, where the stack would have to descend 25 MB to reach
it — not the top, which is where the stack already is.

**Use the BSS span as a validity filter.** An absolute long decoded out of the
image is only plausibly a data reference if it lands inside it. Scanning 1.11 for
`lea`/`pea` of absolutes above the image end yields apparent targets at
`0x4e541300` and `0x5a2967c1`; both fall outside BSS and are opcode bytes
masquerading as addresses. The `0x42c6xxxx` and `0x4464xxxx` clusters fall
inside, and `docs/parameter-set-tables.md` identifies what they hold.

## 1.11 — the build target (build 40059, MAIN OS 3,192,192 B)

The startup routine at `0x4000045c` runs **two** copy loops, where 1.10E ran
one, and clears twice as much BSS:

```
0x4000045c  lea 0x402fc000,%a2 ; lea 0x80000000,%a1   ; copy .data block 1
            movel %a2@+,%a1@ ... cmpal #0x40304000    ; until 0x40304000
            clrl %a0@+ ... cmpal #0x80008000          ; clear BSS to 0x80008000
0x40000486  lea 0x40304000,%a2 ; lea 0x80008000,%a1   ; copy .data block 2
            movel %a2@+,%a1@ ... cmpal #0x4030b980    ; until section end
            clrl %a0@+ ... cmpal #0x80010000          ; clear BSS to 0x80010000
```

| Range | What | Notes |
|---|---|---|
| `0x40000400`–`~0x40000600` | reset vector + C runtime bring-up | writes `0xfc080000` (memory controller); two copy loops |
| `~0x40000600`–`~0x401d0000` | **program code** (~1.95 MB) | grew ~104 KB over 1.10E, pushing everything below it later |
| `~0x401d0000`–`~0x40287000` | **read-only data**: parameter tables, vtables, RTTI, strings | the DN2 parameter table is **`0x401f7fc4`** |
| `~0x40287000`–`0x402fc000` | packed data records + **unreferenced padding runs** | the only free space: 41 runs ≥256 B, **~29 KB**, largest ~1 KB (`dnfw cave scan`) |
| `0x402fc000`–`0x40304000` | **.data/BSS initializer block 1** | copied to `0x80000000` — **not free space** |
| `0x40304000`–`0x4030b980` | **.data/BSS initializer block 2** | copied to `0x80008000` — **not free space** |
| `0x4030b980` | end of the loaded MAIN OS section | exactly where copy loop 2 stops |
| `0x402fc000`–`0x466b74d0` | **main BSS, ~100 MB** | cleared at `0x400004b2`; recycles the initializer tail. Holds the `ParameterSet` slot tables at `0x42c6xxxx` (`docs/parameter-set-tables.md`) |
| `0x80000000`–`0x80010000` | **fast SRAM**: the copied `.data` + its own small BSS | cleared to `0x80010000` — double 1.10E. **Section 4 (the *updater*, not DSP) loads at `0x80000400`**; this is not the main heap |
| inside the per-track object (`~+0x4f2e0`) | **engine modulation state** | measured on 1.10E; **re-anchor pending on 1.11** |
| ELE3 dest `0x02010000` | **bootstrap** (recovery receiver) | 1.10E used `0x02000000` |
| ELE3 section id **8** | **new in 1.11** — 103,416 → 159,948 B, dest 0 | ships with Outbox-8 support; see below |
| `0xfc000000`–`0xfc0fffff` | **ColdFire peripherals** (MBAR) | startup writes `0xfc080000` |

**The parameter table, verified.** `0x401f7fc4` is the origin whose record+0 is
a short-name pointer: `record[id] = 0x401f7fc4 + id*60`, and indexing it returns
`SPD MULT FADE DEST WAVE SLEW SPH MODE DEP MULT` at ids 75–84 (LFO1) and again
at 95–104 (LFO3), exactly as 1.10E's `0x401e29d0` does. An earlier note recorded
`0x401f7fc8`; that was **four bytes into this origin** — the same field-offset
confusion `docs/parameter-table-consumer.md` records for 1.10E. Use `0x401f7fc4`.

**Function-level RE is not yet re-anchored on 1.11.** The page renderer, the
`is_lfo_param_modulatable` 3-LFO gate, the LFO-speed handler and the bootstrap
functions were all located on 1.10E. Their 1.11 addresses are unknown and must
be re-found, not extrapolated.

## 1.10E — kept for comparison (build 40050, MAIN OS 3,085,696 B)

One copy loop: `lea 0x402e2000,%a2; lea 0x80000000,%a1; copy…; clrl (BSS)`.

| Range | What | Notes |
|---|---|---|
| `~0x40000600`–`~0x401bxxxx` | program code (~1.9 MB) | Gate-F cleared |
| `~0x401bae00`–`~0x40260000` | read-only data | parameter table `0x401e29d0`; `LfoPageView` vtable `0x401ecf7c` |
| `~0x4026e000`–`0x402e2000` | padding runs | `LFO4` label written at `0x4026eff6` |
| `0x402e2000`–`0x40300000` | .data/BSS initializer | copied to `0x80000000` |
| `0x402f1980` | end of the loaded section | |
| `0x402e2000`–`0x464f47d0` | **main BSS, ~98 MB** | cleared at `0x400004b2`; sound slot table at `0x42aa6914` |
| `0x80000000`–`~0x8001e000` | fast SRAM (`.data` + small BSS) | cleared to `0x80008000` |
| `0x800003fc` | bootstrap runtime address | ELE3 dest `0x02000000` |

Located on 1.10E: `parameter_page_renderer` `0x40016f38`,
`is_lfo_param_modulatable` `0x400de34e` (hardcodes group ∈ {26,27,28}),
LFO-speed handler `0x40035f32`, `recovery_receive_loop` `0x80003e5a`,
`verify_and_flash_container` `0x80003c9c`.

## What the map settles

**Code caves are scarce, and the obvious space is a trap.** The trailing zeros
before the section end read as free but are the **.data/BSS initializer**,
copied to SDRAM at boot — overwriting them changes the program's initial RAM
state. The only safe space is the **unreferenced padding inside the constants
region**: ~29 KB on 1.11 in runs of ~1 KB. `dnfw cave scan` finds them per
image; `docs/code-caves.md` is the mechanism for using them.

**A new container section is not a route to more code space.** 1.11 added
section id 8 for the Outbox, which shows Elektron growing the *container* — but
a section with `dest 0` is loaded **data**, not code at a virtual address, and
the behavior that uses it lives in the recompiled MAIN OS. We cannot recompile
MAIN OS, so new behavior must be spliced into section 3 with code caves. Adding
or deleting container sections changes flash and file size, **not** the virtual
address space a fourth LFO needs. See `docs/ideas-backlog.md` for the variant of
this idea that *does* pay off (repurposing dead code inside section 3).

**The engine's state is in SDRAM, so the generator is too.** A parameter's live,
modulated value is read from `~+0x4f2e0` inside the per-track engine object in
SDRAM. Nothing in the image holds it. The LFO generator writes it on the
real-time modulation tick — the write-side code that remains the make-or-break
for a fourth LFO, and the reason it cannot be found by reading the image's data.

## Method note

The address-reference histogram over the raw image is **noisy** — scanning every
2-byte offset catches ColdFire opcode bytes (`0x4e`, `0x2f`, `0x48`…) as false
"addresses". The reliable sources are the **startup routine** (which names the
copy and clear boundaries outright) and **targeted cross-reference counts** for a
specific address, not a blind histogram. The parameter table was re-found on
1.11 the reliable way: locate the `SPD` string, find the pointer to it, and
subtract `id*60`.

## Where each mod lives — measured 2026-09-17

`scripts/memory_map.py` diffs every current build against stock 1.11 and
attributes each changed run to a cave, an in-place edit, the appended area, or
(from the build scripts' constants) RAM above BSS. Output
`out/memory-map/map.json`; published as a visual map for the owner.

| | |
|---|---|
| zero runs ≥32 B in `0x4026e000`–`0x402e2000` | 217 runs, 33,125 B |
| **clean** runs (pass the stride and reference checks) | **70 runs, 7,065 B**; only three are large: `0x402cf52c`, `0x402d0664`, `0x402dfa1c`, 896 B each |
| RAM above BSS (`0x466b74d0`–`0x48000000`) | 25.3 MB, mods use 49 KB — 26 KB of it step 4b's relocated parameter table |

**RAM above BSS from `0x47000000`, 1.12 (2026-11-11).** Every claim up here has its row; a new one takes a range
between them, adds its row and an `assert` against its neighbours in `dnfw.waverider.pages`. Measured free map:
`scratch/memory/free-memory-2026-11-11.md` (stack depth from `0x48000000` read small, not bounded).

| Range | Owner | What |
|---|---|---|
| `0x47000000` .. `0x4700d110` | `dnfw.mods.waverider._tables` | the DSP's tables, sent at power-on by the sample link (53,520 B) |
| `0x47100000` .. `0x47200000` | remoteui, `csrc/devtest/prof.c` (`pages.PROF_RAM`, `PROF_BYTES`) | the CPU profiler's state and sample ring (1 MB) |
| `0x47200000` .. `0x47280000` | (free) | 512 KB kept clear between the profiler and the wishes record |
| `0x47280000` .. `0x476E4200` | the wishes record, `csrc/wishes` (`pages.WISH_RAM`, `docs/wishes-record.md`) | index, free stack, hash cache, queue, carry scratch, 8,192 entries of 512 B (4,604,416 B) |
| `0x476F0000` .. `0x476F8000` | the matrix, `csrc/matrix` (`pages.MX_RAM`, `docs/matrix.md`) | each track's routes and envelope times laid out twice for the audio frame, the voices' envelopes, the scratch row (32 KB) |
| `0x47800000` | (bound) | the claims above stay under it; the stack descends from `0x48000000` |

| mod | caves | in-place edits | appended | RAM |
|---|---|---|---|---|
| `lfo4-tick6a` | 210 B at `0x402dfa1c` | 137 B, 33 sites | — | 12,288 B at `0x46700000` |
| `lfo-waveshapes8` | 668 B `0x402cf52c` + 746 B `0x402d0664` | 83 B, 26 sites | — | 8,192 B NOI state + 336 B glyph tiles |
| `lfo-wavetable4` | 676 B + 560 B, same two caves | 80 B, 25 sites | — | glyph tile |
| `arp-on-midi2` | — | 4 B, 1 site | — | — |
| `bootscreen-bang` | 200 B at `0x402dfa1c` | 15 B, 2 sites | 2,092 B | 2,056 B at `0x46710000` |
| `c-hello` (LFO4 step 0) | loader 132 B at `0x4028da70` (cave `0x4028da6e`, 138 B) | 16 B, 2 sites (startup calls, `memcpy` entry) | 164 B `CODE` chunk | 156 B at `0x46800000` -- **LFO4's code region** |
| `lfo4-ext` (LFO4 step 1) | the same loader, 132 B at `0x4028da70` | 24 B, 3 sites (startup calls, `memcpy` and `memset` entries) | 1,564 B `CODE` chunk | 7,732 B at `0x46800000` — 1,548 B of code, then the 5,120-byte table and its counters |
| `lfo4-bridge` (step 3) | 376 B: the loader plus 246 B of engine stubs at `0x402dfa1c` | 174 B, 38 sites | 2,304 B `CODE` chunk | at `0x46800000` |
| `lfo4-slots` (step 4a) | the same 376 B | 180 B, 39 sites | 2,304 B | at `0x46800000` |
| `lfo4-table` (step 4b, part 1) | the same 376 B | **457 B, 148 sites** — 109 of them the relocated table's 56 bases and 53 bounds | 22,140 B in **two** `CODE` chunks | 26,464 B: 6,656 B at `0x46800000` (the C, the extension table, the per-track rows) and 19,808 B at `0x46900000` (the 330 parameter records and the `LFO4` label) |
| `lfo4-page` (step 4b, part 2) | the same 376 B | 469 B, 150 sites | 22,484 B | the same, plus the page record and its name in BSS |
| `lfo4-value` (steps 4c-4e) | the same 376 B | 493 B, 153 sites | 22,836 B | the same again — the read divert, the companion divert and the fourth waveform block are six, ten and eight bytes plus stubs |
| `waverider-m0` (2026-09-26) | as `build_lfo4_tlm --persist` | as `build_lfo4_tlm --persist` | 40,848 B: the C chunk grows 4,164 -> 20,972 B, of which 16,384 B is the baked wavetable (`const`, `wr_table` at `0x468011e4`) | the C chunk (image + 7,016 B BSS) ends at `0x46806d54`, **1,020,588 B** below the relocated parameter table at `0x46900000` |
| `intro-tunnel` | — | 2 B, 2 sites | — | — |
| `intro-stamp` | 184 B at `0x402dfa1c` | 8 B, 1 site | — | — |

**Conflicts today:** the two LFO waveform builds share both caves and every hook;
`lfo4-tick6a`, `bootscreen-bang` and `intro-stamp` share `0x402dfa1c`. **Clean
caves are the scarce resource; the appended area (proven by `intro-bang`) and
RAM above BSS are not.** The mix-and-match registry (backlog §11) must allocate
caves and RAM, not just check hooks.


## The DN2 mod's RAM above BSS, OS 1.12 — 2026-11-12

The RAM the waverider build's loader fills, read from a NOBOOT 1.12 build (`platform.runtime`,
build `4f848d9a`), plus the RAM it uses without carrying bytes for it (`dnfw.mods.waverider.ram()`
declares all of them). 1.12's BSS ends at `0x466b84d0`.

| Range | Size | What | Constant |
|---|---|---|---|
| `0x4670c000`..`0x4670d1e4` | 4,580 B | the pages assembly | `pages.LOAD` |
| `0x4670f000`..`0x4670fba0` | 1,352 B | the A2 filters' ColdFire tables | `a2f.coldfire` |
| `0x46710000`..`0x46710054` | 84 B | the platform runtime's header | `pages.C_END` |
| `0x469f0000`..`0x46a40000` | — | **emulator harnesses only** (most of them; older ones use `0x467cf000`/`0x467d0000`): their call stack (down from `0x46a00000`/`0x46a20000`) and scratch, never in a build | `emulib.machine.SCRATCH_END` |
| `0x46a40000`..`0x46af0000` | 720,896 B span | **the C page renderer** (`csrc/waverider` and what it links), 195,108 B on 2026-11-12 | `pages.C_LOAD`, `pages.C_SPAN` |
| `0x46af0000`..`0x46af1aac` | 6,828 B | the Machinedrum's screen graphics | `pages.MDUI_LOAD` |
| `0x46af8000`..`0x46af8800` | 2 KB | modulation's state | `pages.MOD_RAM` |
| `0x46aff000`..`0x46aff100` | 256 B | the system meter's state | `pages.METER_RAM` |
| `0x46b00000`..`0x47000000` | 5 MB | the sample link's mirror of the pool | `sampler.machines.MIRROR` |
| `0x47000000`..`0x47013428` | 78,888 B (up to 512 KB) | the DSP's tables | `sampler.machines.TABLE_LOAD` |
| `0x47100000`.. | 1 MB | the CPU profiler, while PROFILE runs | `pages.PROF_RAM` |

**The renderer moved down on 2026-11-12** (the User's ruling): from `0x46ac0000` with a
0x30000 span (v0.29..v0.40 0x20000), where it had 1.5 KB left, to `0x46a40000` with 0xB0000,
up to the MD graphics. The harnesses' scratch had grown into the new range (emu_fxdest at
`0x46a40000`, emu_slides and emu_bouncegone allocating from `0x46a30000`); it now stays below
`SCRATCH_END`, which `Machine.alloc` enforces and a test ties to `pages.C_LOAD`.


## The +Drive (eMMC) — whose sectors are whose (2026-11-01)

Not RAM, but the same question: who may write where. The stock store reads and writes
nothing above 2,224 MiB (`docs/drive-storage-research.md`); everything of ours is above it,
each region checked against its bounds before the stock block driver (`0x4012c59a` read,
`0x4012c780` write) is called.

| sectors (512 B) | owner | what |
|---|---|---|
| below `0x458000` | stock | projects, sounds, samples: never written by the mod |
| `0x600000` | the sample link (`csrc/sampler/link.c`) | the pool image's header (`DN2Q`) |
| `0x600001` .. `0x6C8000` | the sample link | the pool image (400 MB, `POOL_BYTES`) |
| `0x6D0000`, `0x6D0001` | the per-project sample pools (`csrc/sampler/pools.c`, `docs/project-pools.md`) | the superblock (`DN2J`), two copies: owner, generation, a switch's intent |
| `0x6D0100` .. `0x6E02FF` | the per-project sample pools | 129 lists (128 projects + the legacy list) x 2 copies x 256 sectors (`DN2K` header, sums, directory page, meta block, slice area) |
| `0x6E0400` .. `0x6E0501` | the inserts (`csrc/inserts/store.c`, `docs/inserts.md`) | 129 records x 2 copies (`DN2I`) |
| `0x6E8000` .. `0x6E8800` | the DSP program's copy (`csrc/waverider/lzma7cache.c`, `docs/lzma7.md`) | header (`DN7C`, written last), then the program decoded from section 7 (up to 1 MiB) |
| `0x6F0000` .. `0x6F0700` | the +Drive library's extension (`csrc/sampler/lib.c` `LIB_X_AT`) | entries 2,048..16,383 |
| `0x6F0800` .. `0x6FEFFF` | the wishes record (`csrc/wishes/store.c`, `docs/wishes-record.md`) | 59,392 cells of one sector (`DN2W`), each a sound's record filed under its hash; written once |
| `0x6FF000` | DIRECT JUMP (`csrc/jump/jump.c`, `docs/jump.md`) | the mod's settings sector (`DN2S`, version, flags, check); bit 0: DIRECT JUMP, bit 1: REMOTE CONTROL OFF (`csrc/devtest/usbcfg.c`), bit 2: LIVE SELECT OFF (`csrc/msel/live.c`), bit 3: VOICE BUDGET OFF (`csrc/load/load.c` SET_BUDGET_OFF, 2026-11-12); bits 2.. carried through by jump.c's writes |
| `0x700000` .. the device's end | the +Drive library (`csrc/sampler/lib.c`) | superblock (`DN2L`), index, folders, then the samples' frames |

Free between them: `0x6C8001..0x6CFFFF`, `0x6D0002..0x6D00FF`, `0x6E0300..0x6E03FF`, `0x6E0502..0x6E7FFF`,
`0x6E8801..0x6EFFFF`, `0x6F0701..0x6F07FF` (the folders 64..127 at `0x6FF800..0x6FF804`). A new region takes a range
from there and adds its row here and a `_Static_assert` against its neighbours in its C.

**v0.39, ERASE MOD DATA** (`csrc/sampler/erase.c`, `docs/erase-mod-data.md`) TRIMs exactly the four
mod rows above (the pool image `0x600000..0x6C8000`, the lists' whole range `0x6D0000..0x6E02FF`, the
settings sector, the library to the device's end) and nothing below `0x600000`. A new region must be
added to its job table and `er_inside`, or it survives an erase.

## The DSP (SHARC): where its map lives, and recent claims

Not the ColdFire's RAM, but the same rule: one owner per range. The DSP's map is
`src/dnfw/waverider/dsp.py` (every L1, L2 and DDR span ours, checked against the stock stream by
`test_waverider_dsp`); a new span is added there, not here. Claims made on 2026-11-12 (opt-samples,
the sample reader, `docs/dsp-cost.md`):

| range | what | constant |
|---|---|---|
| L2 `0x200a0000..0x200a1800` | the DT2 reader's 256 x 6 interpolator rows (the Machinedrum slots' room, unused since 2026-11-10; `0x200a1800..0x200a4000` still free) | `SMP_TABLES_L2` |
| L1 `0x2e0080..0x2e0094` | the reader's decimator coefficients and LEV make-up gain | `SMP_DTAB_DM` |
| L1 `0x2df7f4..0x2df7fc` | the recorder's GAIN index and factor (v0.50; at 0x2e0080 until the v0.52 merge): the sample machines' scratch words `rgain`, `rgfac` | `sampler.machines.REC_GAIN` |
| L1 `0x2ddff0..0x2ddffc` | the guard's later insert words (INS_DLP, INS_BUSEND, REST_OUT; v0.52 merge: v0.49's words filled the block at 0x2de000), after PERC's scratch (to 0x2ddfe8) | `perc.guard.INS_LO` |
| L1 `0x2e0098..0x2e0100` | the taps' line: its switch, its tag, then 24 words (to `sampler.program.RELATCH`) | `SMP_LINE_DM` |
| DDR `0x81218000..0x81219824` | freed (the reader's coefficients until 2026-11-12) | `SMP_TABLES_DDR` |

## DSP optimisation claims 2026-11-12 (SHARC L1 / L2)

Arbiter: juno-engine (for main, 2026-11-12). One row per claim, built on `dnfw.waverider.dsp`'s real layout (spans,
run-time areas) and the stock boot stream (DN2 1.11 = 1.12 section 7, sha256 336e340a...). A claim is a range nobody
else takes; the owner adds it to `dsp.py` (a span or a constant) in its own commit, and a span check there.

**What is where (measured from the boot stream and `dsp.spans()` / `l2_spans()`, byte addresses):**

| region | stock | ours | free |
|---|---|---|---|
| L1 block 0, `0x240000..0x270000` | loaded to `0x26F000` | the frame lookup only | `0x26F000..0x270000` (4 KB, untested) |
| L1 block 1, `0x2C0000..0x2F0000` | loaded to `0x2DD52C`; DM cache `0x2EC000..` | REGION `0x2DD600..0x2EB000`, packed | holes F1 F2 F3 below (padding today); `0x2EB000..0x2EC000` kept as the cache's safety gap |
| L1 block 2, `0x300000..0x320000` | nothing loaded; PM cache `0x31C000..` (startup decode, docs/waverider-dsp-silence.md) | nothing | `0x300000..0x31C000` (112 KB): only `0x30B000..0x30C0A0` ever ran on the unit (ONESHOT 2026-09); the runner has no cache model |
| L1 block 3, `0x380000..0x3A0000` | loaded to `0x39BFFC`; I-cache `0x39C000..` | nothing | none |
| L2 `0x20000000..0x20100000` | image to `0x2008823C`; non-cacheable window `0x200FA000..0x200FDFFF` | `0x200A4000..0x200EA000` (spans, PERC after the move) | `0x2009823C..0x200A4000` inside dsp.py's floor (image + 64 KB); `0x20088400..0x2009823C` below that floor (complex-ping's mods ran there on units); `0x200EA000..0x200FA000` the User's 64 KB margin above PERC; small gaps between spans (3.5 KB at `0x200A9200`, 3.2 KB at `0x200BD050`, 2.7 KB at `0x200AF542`, 2 KB at `0x200B5800`, 1.5 KB at `0x200B1210`) |

PERC's tan table stays in DDR (opt-synths ed672287: read once per SVF coefficient set; L2 would save ~25-35 a voice).
The checks: `test/test_dsp_claims.py` holds these claims as data (every claim disjoint, every L1 / L2 address constant of
`dnfw` inside its owner's claim, every span starting in a claim that takes spans).

Holes inside REGION (a padded span's zeros; real sizes from `dsp.objects()` and the state constants):
F1 `0x2E0640..0x2E1000` (2,496 B: after ping.asm's 182 B and its 128 B tail), F2 `0x2E1200..0x2E1C00` (2,560 B: after
trackbuf.asm's 342 B), ~~F3~~ `0x2E4080..0x2E5400` is **not free**: the bus FDN8 instances' stores live there at run time
(`inserts.bus.FD_L1` `0x2E4050..0x2E53D0`, 8 x 624 B, since day1). Corrected 2026-11-12: the first scan grepped for
addresses inside each hole and missed an area starting 48 B below it; now every module-level L1 constant of `dnfw` is
listed (`scratch/juno-engine/l1consts.py`) and F1, F2 re-checked against them (RELATCH ends `0x2E0200`, ping's code
`0x2E05B6`, trackbuf's `0x2E1156`).

| range | bytes | owner | what | measured gain (per block) | status |
|---|---|---|---|---|---|
| L2 `0x200A0000..0x200A1800` | 6,144 | opt-samples | (their claim) | (theirs) | taken |
| L1 `0x2E0080..0x2E0100` | 128 | opt-samples | (their claim) | (theirs) | taken |
| L1 F2 `0x2E1200..0x2E1700` | 1,280 | DPRO speed (v0.52) | DPRO's interp table (`dsp.MNM_INTERP_DM`; trackbuf's span cut to `0x2E1200`) | measured on v0.52's engines (dsp_cost.py, engine): DPRO-DDRW -2,560 a voice (12,444 -> 9,884), DPRO-DENS -1,280 (5,735 -> 4,455) | used (re-allotted 2026-11-13) |
| L1 F2 `0x2E1700..0x2E1750` | 80 | opt-host | the inserts' refusal telemetry (round 13): per-type skip counts (`guard.INS_TSKIP`, 16 words) and each insert pass's least room (`guard.INS_ROOM`, 4 words); a span (`dsp.INS_TSKIP_DM`) | (telemetry, not a saving) | used (claude/instel; the arbiter allotted 0x2E1700..0x2E1980, the rest given back) |
| L1 F1 `0x2E0640..0x2E0E44` | 2,052 | opt-synths | PERC's exp2 table | SOPHIE -2.2..3.9k a voice (with tan), MD too | allotted |
| L1 `0x2E4050..0x2E53D0` | 4,992 | inserts (bus) | the bus FDN8 instances' stores (`inserts.bus.FD_L1`), live across blocks | (perf 2026-11-11) | used |
| L1 `0x2E5400..0x2E5600` (MNM render IN) | 512, transient | opt-inserts | the post-insert pass's per-voice copy of the JUNO/CHOR ring span; only during the pass (IN is per-render scratch, dead after the voices) | bit-identical | allotted |
| L1 `0x25D980..0x25DD84` (stock's) | 0 new | opt-synths (reads) | stock's own L1 sine S1, now SOPHIE's / AMD's sine (rounding only: 26 of 257 words 1 ulp; never written in the runner) | SHFT.sin's 1,288 B L1 copy not needed | used (457f79a4, after 12:00) |
| L2 `0x20098400..0x2009B400` | 12,288 | opt-stock | the send FX' hot state: the stock chorus's state at `0x20098400..0x20099744` (4,932 B, `dsp.CHORUS_DM`, `_check_l2`); the rest reserved for the delay's control words (~600 B) and the reverb's hot words | -69k (L2); block 2 another ~-21k | used in part (L2, the User 2026-11-12); L1 block 2: **pending unit test** when the User is back |
| L2 `0x200A1800..0x200A2800` | 4,096 | juno-chorus | jsend.asm, the chorus send's JUNO (1,976 B code, sw `0xBD0C00`) | (a feature, not a saving) | allotted (3b3b1aae / 6e982a5c) |
| L2 `0x2009B400..0x200A0000` | 19,456 | perc-layout | PERC's event-only code: host bodies (18,074) + trx_coefs / md_idiv (754) | PERC's span -24.3 KB with 2b (0 instructions changed) | used: perc2a 18,828 B (628 B spare); dsp.py pairwise L2 overlap check (round 11) |
| L2 `0x200A2800..0x200A4000` | 6,144 | perc-layout | 2b: init bodies (4,788) + vo6_bqx (648) | (with 2a) | used: perc2b 5,480 B (664 B spare) |
| L2 `0x200A6FC0..0x200A7000` (MNM scratch +0x2FC0) | 64 | opt-host | the budget sums (`perc.program.CUM_OFF`, 16 words) | (the host cut, bf2639fd) | used |
| L2 `0x200A7400..0x200A7440` (MNM scratch +0x3400) | 64 | clicks | `VEL_OFF`: per-slot velocity (16 words; plus frame slot 62 of our voices, types 5..31) | - | allotted (claude/velocity) |
| L2 `0x200A4000..0x200A6550` (MNM scratch +0x0000) | 9,552 | lever 5 (opt-inserts) | the FDN8 diffusers of the send and of bus 0 (`fdn8.program.DIFF_SEND_L2`, `DIFF_BUS0_L2`; 0x200A4000..0x200A6000 used, to 0x200A6550 allotted): **persistent** delay state | (lever 5) | used (r5; its own claim in test_dsp_claims.py since 2026-11-14) |
| L2 `0x200A9200..0x200A9C88` | 2,696 | opt-md | PI-RS's strike table (`PIRS_TAB`), copied once from the decoded tables when they become whole (`md.core.tables_in_l2`, `dsp.PIRS_TAB_L2`) | PI-RS -624 a voice (with the curve) | used (main as arbiter, 2026-11-14; claude/md16-r5) |
| L2 `0x200B5800..0x200B6000` | 2,048 | opt-md | the P-I modes' curve table (`PI_CURVE_142949`; `dsp.PI_CURVE_L2`), copied the same way: the gap between a2f.asm's span and smp.asm's (ANALOG 2's filter state left it for L1, 2026-11-11) | PI-SD/RS/BD/MT/ML a little each block | used (main as arbiter, 2026-11-14; claude/md16-r5) |
| L2 128 KB, place open | 131,072 | opt-md | DSP2's sine table (no exact smaller form: no symmetry) | EFM-CY -2.5k a voice, FM / TRX | **decision**: no 128 KB contiguous anywhere today; see below |

Left free: F1 `0x2E0E44..0x2E1000` (444 B), F2 `0x2E1750..0x2E1C00` (1,200 B), F3: none (FDN8 stores),
L2 `0x2009B400..0x200A0000` (19,456 B) and `0x200A2800..0x200A4000` (6,144 B), both taken by perc-layout: with them,
nothing is left inside dsp.py's L2 floor but the small gaps between spans.

The Monomachine L2 scratch (`0x200A4000..0x200A8000`, one span): `+0x0000..+0x2FC0` unused since v0.43 (the render scratch
went to L1), then **lever 5's FDN8 diffusers at `+0x0000..+0x2550`** (persistent; a 2026-11-14 note here still said
"unused" and opt-md's P-I tables nearly landed on them); free `+0x2550..+0x2FC0` (2,672 B, main allots it); `+0x2FC0` opt-host's sums; `+0x3000..+0x31C4` the voices'
bookkeeping (keys, costs, rests, strikes, bounds, SLOT_N); `+0x3200..+0x33A8` ANALOG 2's mix tables (106 words);
`+0x3400..+0x3440` clicks' VEL_OFF; free `+0x33A8..+0x3400` and `+0x3440..+0x4000`.

DDR (no fast-memory cost; listed so nobody lands on another): juno-chorus `0x82550000..0x82551050` (the send's state +
a 1,024-float ring with 3 mirror words, zeros at power-on), right after the moved TAPE's rings (`0x82540000..0x82550000`);
the post rings `0x82510000 + 32 x 4,112 B` end at `0x82530200`; PLAITS' `0x82600000..`. The word `0x84000EFC` (the
fxpage block's 12th word, link.c FXP_OFFSET `0xED0` + 44): the chorus TYPE, juno-chorus.

**Open, for main / the User:** (1) opt-md's 128 KB table has no contiguous place: below the floor `0x20088400..0x200A0000`
is 96 KB; it reaches 128 KB (`0x20088400..0x200A8400`) only with dsp.py's floor lowered (complex-ping's mods used it on
units; a runtime scan of stock should come first) AND opt-samples' 6 KB and the Monomachine scratch, DPRO tables and main
tap (`0x200A4000..0x200A9200`, 20.5 KB) moved elsewhere (e.g. into `0x200EA000..`, the User's margin above PERC). (2) L1 block 2 (112 KB, 1-cycle) would
serve opt-stock's -115k and opt-md's table best, but only 4 KB of it has run on the unit and the runner cannot see
the PM cache: it needs a hardware check by the User before anyone's state goes there.
