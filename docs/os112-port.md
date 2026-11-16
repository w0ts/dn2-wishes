# Port to stock Digitone II OS 1.12: scope and map

Measured 2026-11-07 from Elektron's `Digitone_II_OS1.12_dist.zip` (`Digitone_II_OS1.12.syx`,
sha256 `7e5b8a73…2ceb35`) against stock 1.11 and against v0.42 LEAN (rebuilt byte for byte,
sha256 `8a8be7ac…`). Everything below is measured unless marked otherwise. Nothing was run on
an instrument, and no build from this work is gated (see the end).

Reproduce it: `python scripts/port_os112.py STOCK_1.11 STOCK_1.12` (a dry run; prints the map,
the BSS check and the per-file classification).

## 1. What changed between 1.11 and 1.12

| Section | 1.11 → 1.12 |
|---|---|
| 2 bootstrap | **identical** (sha256 `038aa5d1…`) |
| 3 MAIN OS | 3,192,192 → 3,196,288 B (+4,096). A relink: long regions each moved by one constant, plus a few rewritten functions |
| 4 updater | **identical** |
| 5 meta | the build stamp |
| 7 DSP boot stream | **identical** (sha256 `336e340a…`): the SHARC side, our machines included, needs nothing |
| 8 (id 8) | **identical** |

So the port is the ColdFire side only, as `docs/ROADMAP.md` expected.

### MAIN OS code map (1.11 address → 1.12 = address + delta)

From unique 12-byte anchors grown over equal bytes (`scripts/port_os112.py`, `Map`).
Regions of at least 1 KB:

| 1.11 range | delta | |
|---|---|---|
| `0x40000400..0x4008cc56` | 0 | start-up, UI, sequencer core, setter, lock pool |
| `0x4008cc56..0x4008e246` | — | **changed**: new or rewritten code, not read (1.12's feature is routing the main outputs through Outbox 8; that this is it is a guess) |
| `0x4008e246..0x400f2e53` | +0x164 | sound load/save, parameter sets, pattern change |
| `0x400f3017..0x400fbf56` | +0x1ca / +0x1cc | |
| `0x400fbf56..0x401013d2` | +0x25c, +0x138 (pieces) | **partly rewritten**; the PTN view's handlers live here |
| `0x401013d2..0x401b67fe` | +0x2e0 | drawing, memcpy/memset, menus |
| `0x401b6c68..0x401cfbcc` | +0x41a | |
| `0x401d03ec..0x40200caa` | +0x410 | vtables, rodata |
| `0x4020109c..0x4021ed46` | +0x4b8 | rodata, names |
| `0x4021edfe..0x40237fdf` | +0x53f | |
| `0x40237fdf..0x402faff7` | +0x540 | late code; the platform cave `0x4028da70` → `0x4028dfb0` |
| end of MAIN OS | +0x1000 | `0x4030b980` → `0x4030c980` (our appended area starts here) |

This agrees with every 1.11↔1.12 pair in `docs/overtone-map.md` §2 (e.g. `0x400dccc0` →
`0x400dce24`, `0x402008cc` → `0x40200cdc`, `0x4018a97a` → `0x4018ac5a`).

### RAM

- **BSS moves +0x1000, whole.** The start-up code says so: 1.11 clears `0x402fc000..0x466b74d0`,
  1.12 `0x402fd000..0x466b84d0`; the stack top `0x4664acdc` → `0x4664bcdc`. Checked operand by
  operand: every absolute-long BSS operand in aligned 1.11 code reappears +0x1000 in 1.12
  (0 exceptions). So the layout inside BSS is unchanged, only shifted.
- **Fast SRAM `0x80000000..0x80010000`: unchanged** (no aligned operand into it differs).
- **Our own RAM is still clear.** The lowest address the shipping build uses is
  `0x46700000` (lfo4's state; then `0x46708000`, `0x4670c000`, `0x46710000` runtime, `0x46ac0000`,
  `0x46af0000`, `0x46b00000` mirror). 1.12's BSS ends at `0x466b84d0`, 300 KB below.

## 2. The mod's sites, classified

### 2a. What v0.42 writes into stock MAIN OS

v0.42 changes stock MAIN OS in **86 runs, 626 bytes**; the rest is the 226 KB appended area.
The 86 edit runs, the boot animation's intro hook, the platform's start-up calls and loader
cave, and the 60 guards (149 checks in all):

| class | count | meaning |
|---|---|---|
| shift | 60 | the stock bytes and 16 bytes either side are identical at address + delta |
| shift + relocated | 87 | identical except absolute operands, each of which translates by the map |
| context differs | 2 | the stock bytes match; a neighbour differs (below) |
| changed | **0** | |

Deltas of the edit sites: 0 (73), +0x164 (65), +0x2e0 (6), +0x1cc (2), +0x410 (2), +0x540 (1).

The two context differences, read by hand:
- `0x40026098` (TDM_SITE, the SSI ISR after its transmit fill; delta 0): the instruction two
  before it is `addi.l #0x4e6e0100,%d1` in 1.11 and `#0x4e6e8100` in 1.12. Our 8 bytes match.
  Read 2026-11-07 (objdump, both images): it is stock's own `memset((d1 << 11) + const, 0x800)`
  at `0x40026080..0x40026096`, a buffer address the compiler folded into one constant, run
  before our site and never read by our hook. The hook replaces and replays only
  `move.l %fp,%d2 ; addi.l #-72,%d2` at `0x40026098`, identical in 1.12; the calls around it
  translate (`0x40133ebc` → `0x4013419c`, `0x4012a4e6` → `0x4012a7c6`, BSS `0x4058e880` →
  `0x4058f880`). Nothing for the port to do. (Why the folded constant moved +0x8000 rather
  than +0x1000 was not worked out; it is stock 1.12's own arithmetic.)
- `0x402008cc` (JUMP_KEY_SLOT, a vtable entry; → `0x40200cdc`): neighbouring entries point
  into the partly rewritten `0x400fb..0x40101` stretch, so they move by other deltas. The
  entry itself still holds the stock handler (`0x400fa6be` → `0x400fa88a`, as Overtone has it).

### 2b. Stock addresses the sources name

`scripts/port_os112.py` reads every `0x4XXXXXXX` literal in the files the shipping build
compiles (the composers `waverider/coldfire.py`, `ping/coldfire.py`, `waverider/pages.py`,
`slides.py`, the platform/bootscreen generators, `csrc/include/dn2_111.h`, and the C/asm under
`csrc/{waverider,sampler,jump,slides,runtime}`), plus addresses inside stock-bytes hex strings.

| class | literals | |
|---|---|---|
| code, unchanged (delta 0, verified) | 309 + 9 in hex | nothing to do |
| code, moved (verified) | 372 + 22 in hex | rewritten to the 1.12 address |
| BSS | 116 + 14 in hex | rewritten +0x1000 |
| our RAM, peripherals, other | 27 | unchanged |
| tags that fall in the BSS range | 8 | `'DNFW'`, `'CODE'`, and the +Drive formats `'DN2J'`, `'DN2K'`, `'DN2L'`, `'DN2P'`, `'DN2Q'`, `'DN2S'`: left alone (changing a storage tag would orphan saved data) |
| on lines naming a version (history) | 4 | left alone; one is code (`AREA_VA`), edited by hand |
| **refused** (no proof) | **0** | |

"Verified" means 12 bytes at the 1.12 address are the same code as at the 1.11 address
(equal, or differing only in operands that themselves translate). A delta comes only from an
aligned run of at least 64 bytes: a shorter run can be an accidental match (`0x401ac2de`, a
vtable entry, sat in a run of +0x56; its region is +0x2e0).

The BSS literals were checked one by one as well: of the 28 distinct BSS addresses, stock
names 27 directly, each exactly as often in 1.12 at +0x1000 as in 1.11. The 28th is below.

**A mistake caught on the way (2026-11-07).** The first rewrite matched `0x…` only up to a
word boundary, so the 148 C literals with a suffix (`0x42431a6cu`) were silently left at 1.11.
The first cross-check missed it too: it looked only at bytes that differed between the 1.11
and 1.12 code, so an address that should have moved and did not was invisible. Both fixed:
the pattern takes `u`/`l` suffixes, the script now writes all or nothing, and the cross-check
is the operand audit in §5, which looks at every absolute operand in our code.

What the classification cannot see:
- **Data addresses the code computes** (a base plus an offset in Python or C). They move with
  their base; a table that moved as a block keeps its offsets, and every base here is in a
  verified region. The regeneration's stock-bytes checks catch a wrong placement of an edit,
  **not** a wrong data address our C reads or writes.
- **BSS addresses** are not checked by any stock-bytes test. They rest on the measured
  whole-BSS shift above. An emulator run on 1.12 is the test for them.
- **`ACTIVE_TRACK` (`0x42431a6c`, the UI's active track; `waverider/pages.py`,
  `csrc/sampler/slice.c`) is not a global.** It is field +8 of a heap object reached through
  `ProjectSettings`+16 (`docs/ideas-backlog.md`, LFO waveshapes v5). Stock never names it; the
  shipping 1.11 build reads it at a fixed address and works on the instrument, so the heap
  arena's allocations are evidently repeatable there. Ported +0x1000, it is right only if 1.12
  allocates the same objects in the same order before it. **Unmeasured; the highest-risk
  address in the port.** Measure it in the emulator on 1.12 (TRK + TRIG n, watch the byte), or
  better, read it through `ProjectSettings` instead of a fixed address.
- The 2a context difference in the audio ISR (read since: not ours, see 2a).

## 3. What the port is

1. `scripts/port_os112.py STOCK_1.11 STOCK_1.12 --write`: rewrites the literals (2b). It
   refuses to write if a single literal is unproven.
2. By hand: `AREA_VA` / `DNFW_AREA` (end of MAIN OS, `0x4030c980`), `stock_length`
   (3,196,288), the generators' `STOCK` path (1.12 zip), the "Digitone II 1.11" texts in
   errors and JSON `os` fields, the patcher's version check (`tools/patcher/dn2patch.py`).
3. Regenerate `waverider_code.json`, `platform_code.json`, `bootscreen_code.json` against stock
   1.12 (`scripts/gen_*_code.py`; m68k GCC 13.3 in docker, ~10 s). Their stock-bytes checks
   prove every edit's placement.
4. `dnfw mods apply` on stock 1.12.
5. The gate (owner's bench; not available to this work): `ship_gate.py` and its emulator
   steps are built on 1.11 (snapshots, stock 1.11 references, preflight's stock comparison).
   They must be rebuilt for 1.12 before any 1.12 build can be cleared. **This is the
   largest remaining piece and needs the owner's bench.**

Not in the shipping build and not ported: the standalone mods (`lfo4`, `arpplocks`,
`arpmodes`, `midiarp`, `fxmod`, `lfowaves`, `usbprobe`) and their committed JSON, the
emulator scripts `scripts/emu_*.py`, the one-off `scripts/build_*.py`. Their stock checks
refuse 1.12, so they fail safely.

## 4. Effort (estimate, not measured)

| piece | estimate |
|---|---|
| steps 1–4 (sources, regeneration, a 1.12 build) | hours, mostly mechanical: the map covers every site |
| emulator on 1.12: boot, the gate's UI and engine steps, BSS-dependent features (DIRECT JUMP, slides, sampler link, MACHINE SEL) | days: new snapshots, every 1.11 reference in the harness |
| hardware test by the owner | after the gate clears it |

Merging: the rewrite is a script, so it should be re-run after the 1.11 work in flight
(SOPHIE, DSP-side) lands, instead of carrying a 700-line diff of address edits across
branches.

## 5. Status (2026-11-07): steps 1–4 done on branch `claude/os112-port-201bc1`

- Step 1: `port_os112.py --write` rewrote the literals in 27 files; 0 refused.
- Step 2 by hand: `area.AREA_VA` → `0x4030c980`; the generators read
  `Digitone_II_OS1.12_dist.zip`; `os` fields and refusal texts say 1.12; the preflight
  (`dnfw.safety`) now requires stock 1.12 (version 1.12, build 0062, the stored-payload hash
  of every section; 1.11's hashes kept beside them). `gen_platform_code.py`'s comparison with
  lfo4's instrument-proven loader now moves two addresses first: the loader's cave
  (`0x4028da70` → `0x4028dfb0`) and the end of MAIN OS (`0x4030b980` → `0x4030c980`); the
  1.12 loader is that loader with exactly those two words changed.
- Step 3: `waverider_code.json` (86 edits, 60 guards: every stock-bytes check passed on 1.12
  and the edits replay to the compose output), `platform_code.json`, `bootscreen_code.json`
  and their `site/js/mods/*.js` regenerated against stock 1.12.
- Step 4: the web patcher's `build()` on stock 1.12 writes a build (2,641,056 B, sha256
  `fa9abfbc…7dc4`): mods apply, preflight all ok, integrity and signature 21/21.

Cross-checked independently of the generators:
- section 7 of that build equals v0.42's;
- every edit's 1.12 address is the map's translation of its 1.11 one;
- **operand audit**: every instruction in our code (the four chunks, the boot stamp, the
  loader, the edits) disassembled with objdump, each absolute operand into stock code or BSS
  tested for being a stale 1.11 address. Control: the committed 1.11 code against 1.12 shows
  161 stale operands. The ported code shows 26 flags, all explained: 25 are the ported
  `ACTIVE_TRACK` (`0x42432a6c`, which happens to equal another 1.11 variable's address) and 1
  is the ported message-view vtable (`0x40207294`, `0x40206ddc` + 0x4b8, checked by hand).

Python unit tests (the repo's `test/`, run on this Mac; `test_md.py` and `test_perc_live.py`
excluded: they fail before the port too, for want of the Machinedrum reference here):
- `test_slides.py`, `test_waverider_mod.py`, `test_safety.py` now read stock 1.12 (their
  own 1.11 addresses ported with `port_os112.py --only`): **40 passed**.
- Against the pre-port tree, the port adds failures only in tests of the **standalone 1.11
  mods** stacked on the platform (`test_lfo4_mod`, `test_fxmod_mod`, `test_mods_matrix`,
  `test_mods_platform`, `test_js_platform`, `test_js_lfo4`, `test_js_arpmodes`,
  `test_mods_ramcheck`): those mods are not ported, and the platform they share is now 1.12's.
  Porting them (or retiring them) is its own piece of work.
- The operand audit and the alignment above were run with scratch tools
  (`~/GitHub/dn2mk2-scratch/os112/tools/`, not committed); `port_os112.py` carries the map,
  the BSS check and the literal classification.

Not done:
- **The gate.** `scripts/ship_gate.py`, its emulator steps and their snapshots are 1.11's;
  no 1.12 build can be cleared until they are rebuilt (the owner's bench: the emulator,
  digikit, is not on this Mac). Until then every 1.12 build is **UNGATED and must not be
  flashed** (`CLAUDE.md`).
- `ACTIVE_TRACK` on 1.12 (§2b).
- `docs/` addresses, `dn2_111.h`'s file name, the standalone mods, `scripts/emu_*`.
- The USB-upgrade and SHARC-upload limits in `dnfw.safety` were measured on 1.11 at BSS /
  code addresses that the map moves; the limits themselves rest on the unchanged layout
  (inferred from the whole-BSS shift, not re-measured on 1.12).
