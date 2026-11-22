"""Every safety gate, on the exact .syx you will flash. Nothing is cleared without it.

    DT2_SECTIONS=/path/to/stock-1.12-sections \\
    python scripts/ship_gate.py Digitone_II_OS1.12.syx build.syx \\
        [--venv ../digikit/.venv/bin/python] [--digikit-sharc ../digikit-wt-sharcemu] \\
        [--only STEP[,STEP...]] [--list]

**The owner's rule (2026-10-11): every check, on every build, every time. No
exceptions, no "it's only a small change".** This script is that rule as code, so it
does not depend on anyone remembering it. It runs, in order, and stops at the first
failure:

1. **preflight** (`dnfw.safety`): stock input is OS 1.11 byte for byte; bootstrap,
   updater, metadata and Outbox untouched; signature valid; DSP program within the
   uploader's real limit.
2. **DSP identity**: if section 7 changed, it must be *exactly*
   `dnfw.waverider.dsp.section7(stock)` -- the image the SHARC gate runs. Otherwise the
   SHARC gate would be testing a different program from the one being flashed.
3. **SHARC runner** (`sharc_waverider_m5.py`, if section 7 changed): PERC and every
   filter and machine of ours bit-exact to its model, and types 0-4 bit-identical to stock.
4. **ColdFire instruction set** (`check_coldfire.py`): every `CODE` chunk the loader
   runs has no scale-8 addressing; and every hit in MAIN OS against stock lies past
   stock's end *and* outside every `CODE` chunk (i.e. in data that never executes).
5. **boot from reset** (`emu_boot_check.py`): boots and draws its UI, no fault (v0.37: and the
   start-up animation's first frame is s!Rwa²'s).
5c. **repacked sections** (v0.65, `emu_depack_check.py`, docs/packer.md): the instrument's own
   aPLib depacker (the bootstrap's, run in the emulator) gives back exactly our bytes for every
   compressed section the build changed; one flipped byte does not.
5b. **start-up animation** (v0.37, `emu_aniz_check.py`): from the snapshot before the intro,
   with the build's hook and appended area installed, every frame (v0.39: 38, his own), each his, in
   order, to the intro's last frame.
6. **engine + LOAD/SAVE** (`emu_boot_engine.py`): the evaluator runs clean under the
   real loader; CODE chunks intact; machine types survive a SAVE/LOAD round trip.
6b. **sample link** (v0.16, `emu_waverider_menu.py`'s `link16`): on the ColdFire, the
   +Drive's pool image loads into a Python DSP over the fast link (one packet lost and
   resent), commands included; with nothing getting through, the loader stops; a
   recording comes back over TDM and is written to a Python +Drive. Every byte checked,
   and every period the frame's routing words (0xa5a..) are stock's (v0.20). v0.38 (`live`):
   22 samples added live and 3 recordings, one after another, each into the first empty
   slot past the power-on count; each must play by the DSP's own rule (`slot_plays`: the
   magic, the count, the entry), its frames the image's; a recording while it records.
6p. **per-project pools** (v0.38, `emu_waverider_menu.py`'s `link16` `pools`, scripts/emu_pools.py):
   the OS's LOAD, NEW and SAVE AS through the build's detours; each project its own slots, the
   legacy pool for old ones; power cuts after every sector; the DSP never another project's sample.
6e. **ERASE MOD DATA** (v0.39, `emu_erase.py`, docs/erase-mod-data.md): through the real keys
   (+DRIVE, RIGHT, two questions; NO at either erases nothing) and link command 28, on a Python
   +Drive logging every command: TRIM only in the mod's four regions, covering them exactly,
   headers first; stock areas and gaps byte-identical; everything reads erased; no write
   after the first TRIM; a bad card and a TRIM error fail at their sector; a power-on after
   cuts at seven points boots with an empty pool, and after the whole erase as a fresh install.
6d2. **stock NAME screen** (v0.54, `emu_waverider_menu.py`, docs/name-screen.md): after TRIM's YES the
   DN2's own NameView is up, opened once and drawn; its NO goes on to ASSIGN without a name. The negative
   control clears the main view pointer: our own naming screen stands in (the fallback). The recorder
   flow (6d) spells a name with the stock screen's own keys and its YES names the recording.
6w. **the wishes record** (2026-11-11, `emu_wishes.py`, docs/wishes-record.md): stock's own SAVE, LOAD,
   memcpy and memset through the four hooks, on a Python +Drive at the driver: every byte outside the link's
   lane as stock saves it, the link and the cell as the host reference spells them, a record copied, carried,
   dropped, written once 0.5 s on, read back from a cell; nothing written under ERASE's lock; no fault.
6w2. **the wishes record on every item** (2026-11-12, `emu_wishes_items.py`, docs/wishes-record.md "Every item
   type"): stock's kit, pattern, song and project-settings SAVE and LOAD through their hooks: every stored byte
   outside the link as stock saves it, the link as the host reference spells it, the record loaded into another
   item and dropped by a stock-saved one, the live bytes the same with or without the link, copy and clear carry
   and drop it, its cell written with its item type; a pattern's link moves when its lock record is taken.
6x. **the matrix** (2026-11-12, `emu_matrix.py`, docs/matrix.md): the frame's parameter path called by hand,
   stock's route 1 on every voice row against the same route in the row's sound's record: the heard slot the same
   every frame (one route a row; then three into one slot, clamped in stock's order); the matrix's instructions the
   same with no route and with every route, under its bound; ENV1 (the row's AMP cells) and ENV2 (the record) through
   HOLD's own note hooks, each routed cell every frame as the clone's model; the routes popup through the panel
   (a plain push opens it at its release, never with a key or turn in between, FUNC + push stock's; turns make routes, push-and-turn moves the row, YES keeps, a route at 0 goes, NO undoes,
   FUNC + long push resets the parameter; LOCKS shows the parameter's own locks; MOD SETUP's rows read only;
   FUNC + long push inside deletes a route, its DEP lock freed, NO brings them back); the AMP pages' titles
   (ENV1/AMP, ENV2, WAVEFORM, read from the title bar, clear of the right edge); ENV2's page drawn by stock's AMP
   page code (with ENV2 set to the sound's envelope, stock's page pixel for pixel, ADSR and AHD); ENV2's
   locks through the panel (grid recording, a trig held, an ENV2 knob turned: the step's lock; the lock list's tail;
   SAVE as id 203.., LOAD back).
6y. **the envelope clone** (2026-11-12, `sharc_matrix_env.py --quick`): the model ENV1/ENV2 run against stock's own AMP
   envelope in Elektron's DSP code (the SHARC runner), block by block: ADSR and AHD, a note-off in the attack, RSET
   off, the fastest knobs.
6m. **MACHINE SEL in two columns** (`emu_waverider_menu.py`, csrc/msel/msel.c): after every key the cell drawn
   selected is the row stock's own reader puts under the cursor, over every machine row and every filter row;
   FUNC + SYN switches the page and leaves it up; YES commits the type drawn selected; NO closes it.
6m2. **LIVE SELECT** (`emu_waverider_menu.py`, csrc/msel/msel.c, docs/live-select.md): a moved cursor commits
   nothing until it has rested, then the machine under it; NO puts the machine and the whole sound back byte for
   byte and closes; YES keeps the previewed machine; with the setting off, MACHINE SEL is stock's.
6m3. **LFO waveforms** (`emu_lfowaves.py`, `dnfw.mods.lfowaves`, docs/lfo-112-port.md): against the same build with
   lfowaves taken out, LFO1 on each wave through the frame's evaluator: stock's seven unchanged, each new one moving
   its destination with its own shape; the cascade carries an LFO into another's WAVE past 6; the WAVE formatter
   names the new waves and the LFO page draws every wave differently, stock's as before.
6m4. **LFO4** (`emu_lfo4.py`, `dnfw.mods.lfo4` with `DN2_LFO4`, docs/lfo-112-port.md): LFO4 sweeps its destination
   and not at depth zero; LFO4 into LFO1's SPD and LFO1 into LFO4's SPD each change the other's output (the
   cascade both ways); LFO1..3's lists offer LFO4's seven controls, never its DEST; stock's own SAVE and LOAD carry
   LFO4's values through the wishes record, and a sound saved at LFO4's defaults loads them so; on the build's own
   snapshot, [MOD] walks four pages with LFO4's the fourth, each of its knobs moves its own LFO4 value and nothing
   else, LFO1..3's knobs leave LFO4 alone, and a value in lfo4's table is drawn.
6n2. **a new project** (2026-11-17, `emu_waverider_menu.py --switch-watch`, docs/meter.md): LOAD PROJECT's CREATE
   NEW and MANAGE PROJECTS' INIT NEW through the panel: stock's popup says SUCCESS, never ERROR; INIT NEW writes
   the slot; no fault; every switch into stock's prio-2 file worker opens the meter's idle interval, so stock's
   own project work cannot light "!CPU" (the User's v0.57.1 report, measured on the User's DN2).
6s. **DIRECT JUMP** (`emu_jump.py` run on the coupled emulator by `emu_jump_coupled.py`, docs/jump.md): the sequencer ticked through stock's own ISR;
   off is stock's state every tick; on, every track goes on from its own step (Elektron's rule); a cue
   that is not the PTN view's stays stock's; the setting persists in its sector; rapid fire (83 cues). Every run
   on the coupled emulator: the UI and the audio ISR every period (the stock control too).
6q. **UI fuzz** (v0.33, `emu_fuzz_ui.py`): the sample pages driven at random, two seeds.
   v0.34 (docs/timing-model.md): with the audio interrupt firing on its own at its real
   cadence through the real vectors, preempting the mod's UI code; a CPU exception, the
   interrupt no longer delivered, or audio frames overrunning their budget fail a seed.
6s. **parameter slides** (`emu_slides.py`, the build and stock 1.11): a slide's ramp exact per
   frame and landing on the locks; SLIDE off and every lock table identical to stock's.
7. **unit tests** (`pytest -m "not slow"` on the safety, mod, PERC and filter tests; v0.38: on
   both cores, pytest-xdist `-n 2 --dist load`, the same tests and the same pass line).

The SHARC runner's parts (v0.34): decode/map/voice/guard, stress (K = 3 and the memory-cost
clock), garbage, **wipe** (the output guard really resets a poisoned voice and records it),
smp, link/rec/pvmix/tdm, stock (ping until v0.44), mnm/frame.

Only if all pass does it write `BUILD.gate.json` beside the build (the build's
sha256, each gate's result, the date) and print `CLEARED TO FLASH`. Anything else
prints `DO NOT FLASH` and exits non-zero. A build changed after its gate needs a new
gate: the record names the sha256 it cleared.

It takes about an hour, mostly the two ColdFire emulator runs. Run it unattended.

**v0.25 (the owner's go-ahead, 2026-10-25): the SHARC runner runs beside the ColdFire
steps, and a long step's pass is reused only when nothing it read has changed**
(`scripts/gate_cache.py`): every file its processes opened, the directories they listed,
the native libraries and programs they ran, and this script's own inputs, each hashed
(sha256) when it passed. One differing byte, or a file gone, and the step runs again. The
record says which steps were reused and from which pass.

**v0.38 (owner, 2026-11-01): faster, with nothing less checked.** The numbers above name the
steps; they run in this order (`--list`): preflight, ColdFire code current, the build is this
tree's, DSP identity, DSP hardware rules, the C symbols in the layout, the ColdFire instruction
set, then the unit tests (both cores), then the SHARC runner starts beside the ColdFire emulator
steps, which run quickest first and the hour-long dead link last. The SHARC runner's parts run
quickest first too, and a part that fails stops the gate when the ColdFire step under way ends,
not an hour later. Every check is the same one, on the same inputs: the order is all that moved.

**2026-11-16 (the User: "the checks should be running the riskest first, always").** After the
static steps (preflight, `rammap`, ... the ColdFire instruction set), the brick-risk emulator steps
(BRICK_EMU: boot from reset, the power-on with our machines, engine + SAVE/LOAD, the UI fuzz) run
before the unit tests, then the rest as above.

`--only STEP[,STEP...]` runs just those steps on the build (a SHARC runner step's name, e.g.
`chords`, names its part). Each step's pass goes into the same reuse cache, traced exactly as in
a full run (the setup, which makes every step's commands, runs whole either way, so a step's
commands and this script's own inputs are the same). It never prints the clearance and never
writes the build's `.gate.json`: only a full run clears a build.

The workflow: when a change touches a step's inputs, run that step alone with `--only` first,
until it passes. Then run the full gate, and make no edit to a test or a script while it runs:
the full run reuses the standalone passes only while nothing they read has changed.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PYCACHE = ROOT / "out" / "ship_gate_pycache"
# The slice step's y1, YES on a SLICE page with no sample on SAMP: the box NO SAMPLE ON SAMP over the page, as the v0.59
# merge build drew it (ce8e92c9, sha256 fccd9cd3..., its own snapshot, 2026-11-18; the same file as 62dc9b91's y1 and as
# a6fa7ff6's first draw after YES, measured 2026-11-20). The slice step wants y1 equal to it pixel for pixel.
SLICE_NOTE_REF = ROOT / "test" / "data" / "slice_no_sample_v059.png"
if __name__ == "__main__":
    # 2026-11-17 (v0.56.3's full run): the gate's own process and its untraced steps (preflight .. overbridge)
    # write their byte-code here, never into the tree. Their __pycache__ folders in src/ and scripts/ changed the
    # listings that the traced steps' records hold (src/dnfw/params), and every SHARC part, the coupled steps and
    # the unit tests ran again in the full run although nothing they read had changed. Traced steps keep their own
    # (run(): PYTHONPYCACHEPREFIX inside the trace folder)
    sys.pycache_prefix = str(PYCACHE)
    os.environ["PYTHONPYCACHEPREFIX"] = str(PYCACHE)
sys.path.insert(0, str(ROOT / "src"))

from dnfw import safety                                    # noqa: E402
from dnfw.cli.files import read_image                      # noqa: E402
from dnfw.firmware.load import load                        # noqa: E402
from dnfw.mods import platform                             # noqa: E402
from dnfw.patch import area                                # noqa: E402
from dnfw.waverider import dsp                             # noqa: E402

sys.path.insert(0, str(HERE))
import gate_cache                                          # noqa: E402

MAIN_BASE = 0x40000400


def has_bootscreen(sec3: bytes) -> bool:
    """this MAIN OS section's intro jumps to the boot screen's stamp (dnfw.mods.bootscreen.apply's JMP), i.e. the build
    carries the start-up animation; a NOBOOT build keeps stock's intro"""
    from dnfw.mods import bootscreen as BS      # noqa: PLC0415
    o = BS.SPEC["intro_va"] - BS.BASE
    return sec3[o:o + 2] == b"\x4e\xf9" and int.from_bytes(sec3[o + 2:o + 6], "big") == BS.SPEC["stamp"]
# CODE chunks that hold only data, reached through a pointer and never jumped to.
# Each is listed by name, on purpose: a chunk is assumed to execute unless it is here.
DATA_ONLY: dict[int, str] = {       # (Waverider's wave-display bytes were one, until v0.11)
    # the Monomachine build: the tables csrc/sampler/link.c sends the DSP at power-on (read
    # as bytes from TABLE_LOAD, never called; dnfw.mods.waverider._tables)
    0x47000000: "the DSP's tables, sent at power-on by the sample link (data, never called)",
}


def code_ranges() -> dict[int, list[tuple[int, int]]]:
    """CODE chunks whose code and data the build itself has recorded: {load: [(start,
    end)]}, the ranges that execute. Waverider's page chunk is assembly (is_wr up to its
    label table) and then C (C_LOAD up to __text_end); between and after them are its
    descriptors, strings, rodata and data, which a scan would misread as instructions
    (W2: a descriptor's two pointers read as `and.l %d0,%a4@(70,%d4:w:8)`). Any other
    CODE chunk is checked whole."""
    lay = json.loads((ROOT / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    out = {lay["is_wr"]: [(lay["is_wr"], lay["labels"])],
           lay["c_load"]: [(lay["c_load"], lay["c_text_end"])]}      # v0.13: a chunk of its own
    if "mchunk_code_end" in lay:  # the machines chunk: the shims, then strings and tables
        out[lay["slot_shim"]] = [(lay["slot_shim"], lay["name_long_5"])]
    # 2026-11-14 (r8): lfowaves' chunk is names, wavetables, the glyph and its relocated pointer tables, then its
    # code; the tables read as 68020 modes (`03b4 4678` = bclr ..(78,%d4:w:8)). Its build records the code's range.
    lw = json.loads((ROOT / "src/dnfw/mods/lfowaves_code.json").read_text())
    if "code" in lw:
        out[lw["runtime_va"]] = [tuple(lw["code"])]
    # 2026-11-21 (the User: "Scan only the kernel's code"): SAFE MODE's chunk is the compiled kernel (head, code and
    # its constants, safemode_code.json) and then the unpatch table dnfw.mods.safemode appends (stock 1.12's bytes,
    # data the kernel copies, never executed). Only the kernel's own bytes are scanned; the table is reported as
    # appended data (sm_table_note), and a scale-8 instruction planted in the kernel must still fail (sm_control).
    lo, hi = safemode_code()
    out[lo] = [(lo, hi)]
    return out


def safemode_code() -> tuple[int, int]:
    """SAFE MODE's kernel code range: its load .. load + the compiled kernel's length (safemode_code.json)"""
    sm = json.loads((ROOT / "src/dnfw/mods/safemode_code.json").read_text())
    return sm["load"], sm["load"] + len(bytes.fromhex(sm["code"]))


SM_PLANT = bytes.fromhex("23810e00")       # movel %d1,%a1@(0,%d0:l:8): the scale-8 store that faulted lfo4-bridge


def sm_control(image: bytes, va: int, work: pathlib.Path, logs) -> tuple[bool, str]:
    """the negative control for SAFE MODE's range: the scanned kernel bytes with SM_PLANT written at the kernel's init
    (a function entry, so the disassembly is in step there) must FAIL check_coldfire, the hit at the planted address"""
    sm = json.loads((ROOT / "src/dnfw/mods/safemode_code.json").read_text())
    lo, hi = safemode_code()
    at = sm["init"]
    if not (va == lo and lo <= at and at + len(SM_PLANT) <= hi):
        return False, f"init {at:#x} not inside the kernel's range {lo:#x}..{hi:#x}"
    planted = bytearray(image[:hi - lo])
    planted[at - lo:at - lo + len(SM_PLANT)] = SM_PLANT
    f = work / f"code_{lo:08x}_control.bin"
    f.write_bytes(bytes(planted))
    rc, out = run(f"coldfire_{lo:08x}_control", [sys.executable, "scripts/check_coldfire.py", f, "--base", hex(lo)],
                  logs)
    hits = [int(h, 16) for h in HIT.findall(out)]
    ok = rc == 1 and at in hits
    return ok, (f"a scale-8 store planted at the kernel's init {at:#x} is caught" if ok
                else f"the planted instruction at {at:#x} was NOT caught (rc {rc}, hits {[hex(h) for h in hits]})")
# v0.40 (owner, 2026-11-05): the one build the missing Monomachine golden runs may be excepted
# for -- its DSP image (section 7) and the MnM code and test as they were at v0.39 (dbbe804).
# Any change to these ends the exception: the golden runs must exist again.
MNM_EXC_SEC7 = "1864d691b2f91bc8006580ab4a07701b1b7644be67fb1f5663429aabc7496ed0"
MNM_EXC_TREES = {"src/dnfw/mnm": "c27c4179af8142a94794fcafac097b5b99edd267",
                 "test/test_mnm.py": "cbe70e82073139d8f21ba0bb58972a927ef74016"}
# without the golden runs test_mnm collects only its 8 tests that need none (they skip as a
# module); its 366 golden cases are not collected at all (measured on v0.39's tree, 2026-11-05)
MNM_EXC_REST = 8
# dn2-wishes (the User, 2026-11-11, "Skip it, report it"): upstream's Monomachine golden runs are not available to
# the fork (not on the Mac nor the farm), and the exception above covers only v0.39's DSP image. Without them the unit
# step runs every other test and reports the golden cases as not checked, instead of refusing every v0.48 build.
NO_MNM_GOLDEN = -1
# the machines test_mnm holds to golden runs (dnfw.mnm.bench.GOLDEN_NAMES; test_mnm asserts the two agree): with the
# folder there but one's file missing (v0.59's FM+, never made for the fork), its golden cases are not collected and
# the unit step names it as not checked (the same ruling)
MNM_GOLDEN_NAMES = ("WAVE", "SID", "DENS", "DDRW", "VO6", "FMSTAT", "FMPAR", "FMDYN")
TESTS = ["test/test_safety.py", "test/test_mods_list.py", "test/test_mods_platform.py",
         "test/test_waverider_mod.py", "test/test_waverider_dsp.py",
         "test/test_ram_112.py",                            # 1.12: every RAM chunk above stock's uncached buffers
         "test/test_stock_ram_112.py",                      # 1.12: no chunk of ours where stock writes (stockram)
         "test/test_waverider_pages.py",                    # v0.45: test_ping_coldfire/_live dropped with PING
         "test/test_shft_live.py", "test/test_mnm.py",
         "test/test_md_source_identity.py",                  # 2026-11-13: every MD machine as v0.52's source renders it
         "test/test_gran_live.py", "test/test_sharc_sources_in_repo.py", "test/test_perc_live.py", "test/test_sampler.py",
         "test/test_sources.py", "test/test_md_ui.py", "test/test_patcher.py",
         "test/test_md.py", "test/test_md_table_mem.py",    # the Machinedrum machines against its own output; their tables per layout
         "test/test_sampler_relatch.py", "test/test_pools.py",
         "test/test_gate_cache_foreign.py",                 # v0.48: the cache's cross-worktree guard and its control
         "test/test_gate_cache_scratch.py",                 # 2026-11-16: a step's own temporary folder, its controls
         "test/test_slides.py",
         "test/test_lfowaves_112.py",                       # lfowaves on 1.12, SHIPPED, the DN2_LFO4 option
         "test/test_wishes_lfo4.py",                        # LFO4's stored values in the wishes record (host)
         "test/test_modulation.py",                           # 2026-11-11: the lists, the cascade, the moving controls
         "test/test_moving_ours.py",                          # 2026-11-12: the moving controls on our own pages
         "test/test_line_redraw.py",                          # 2026-11-17: the moving lines updated alone
         "test/test_scope_alone.py",                          # 2026-11-17: the scope's frames alone, never queued
         "test/test_libtree.py", "test/test_web_tool.py",   # v0.40: nested folders (the model, the page's levels)
         "test/test_fdn8.py",                                 # FDN8: its DSP program against the reference
         "test/test_drum.py",                                 # 2026-11-20: DRUM: its model against its reference
         "test/test_perc_flow.py",                            # 2026-11-20: the R12 folds (dnfw.perc.flow): dead only
         "test/test_xdly.py",                                 # XDLY: the same
         "test/test_inserts.py",                              # the inserts: the same
         "test/test_inserts_post.py",                         # the post inserts (CHOR, WIDE): the same
         "test/test_inserts_bus.py",                          # the bus inserts (FDN8, XDLY per track): the same
         "test/test_inserts_c.py",                            # the ColdFire's packed values against design.pack
         "test/test_wishes.py", "test/test_wishes_c.py", "test/test_wishes_items_c.py", "test/test_wishes_pst.py", "test/test_matrix_c.py",      # the wishes record: its stubs, its C on the host
         "test/test_meter_quiet.py", "test/test_meter_stamp.py", "test/test_meter_startup.py",
         "test/test_ins_overview.py", "test/test_overviews.py",                         # 2026-11-17: the inserts overview's letters, names, layout                         # the CPU label quiet while stock loads or upgrades
         # 2026-11-17 (triage af55cb18/23a5f018): tests that ran outside the gate, passing again; js_platform stays out
         # (it needs node, which the farm does not have: there it would only skip)
         "test/test_lzma7.py", "test/test_lzma7cache.py", "test/test_fxpage.py", "test/test_fx_type_order.py",
         "test/test_stock_units.py", "test/test_juno.py", "test/test_a2_glide.py", "test/test_lfo4_sites.py",
         "test/test_mods_matrix.py", "test/test_telemetry.py", "test/test_mods_ramcheck.py",
         "test/test_ramguard.py",                            # the RAM guard's no_dma rows (fd850113)
         "test/test_apopt.py", "test/test_banks.py"]        # v0.65: the optimal packer; banks B..D on the DSP's model
HIT = re.compile(r"^\s+([0-9a-f]{8}):", re.M)
# stock's MachineListView (csrc/msel/msel.c): its class, the cursor's row (dividers counted), the page (0 the
# machines, 1 the filters), and the reader of the type under its cursor (stock's YES reads it)
MSEL_VT, MSEL_CURSOR, MSEL_PAGE, MSEL_ROW_TYPE = 0x401DFDE8, 420, 424, 0x4005B162
MSEL_ROWS = 6                                       # msel.c ROWS: a column's cells; two columns a screen

# v0.38 (owner, 2026-11-01): the steps by name, for --only and --list, in the order a full run
# takes them. The quick ones, and those new code most often fails, first, so a failure shows
# in minutes; the SHARC runner (gate_sharc.parts(), names "sharc:...") starts after the unit
# tests, on its own core beside the ColdFire emulator steps, and a part that fails stops the
# gate at the next step's end. What each step checks is unchanged, and the steps that are
# never reused (preflight to the ColdFire instruction set) stay so.
FIRST = (("preflight", "preflight (never reused)"),
         ("rammap", "our RAM clear of what stock 1.12 writes (never reused)"),   # 2026-11-16: a brick risk
         ("code-fresh", "ColdFire code current (never reused)"),
         ("rebuild", "the build is this tree's (never reused)"),
         ("dsp-identity", "DSP identity (never reused)"),
         ("hwrules", "DSP hardware rules (never reused)"),
         ("symbols", "every C-keyed check has its symbol in the layout (never reused)"),
         ("coldfire", "ColdFire instruction set, each code chunk and MAIN OS (never reused)"),
         ("overbridge", "Overbridge's code untouched (never reused)"),
         ("safeboot-table", "SAFE MODE: its unpatch table gives stock 1.12, the kernel first (never reused)"),   # 2026-11-21
         ("linkfast", "stock's link and USB passes with less work: the same bytes as stock's (never reused)"),
         ("unit", "unit tests, both cores (pytest-xdist)"))
# the ColdFire emulator steps. 2026-11-16 (the User: "the checks should be running the riskest first,
# always"): first the brick risks (BRICK_EMU: a build that cannot power on, that faults with our machines on
# its tracks, that corrupts what it saves, that faults under the UI), before the unit tests; then the rest,
# quickest first (v0.37's timings), the hour-long dead link last
BRICK_EMU = ("boot", "safeboot", "machines", "engine", "fuzz", "paravoice", "dronehold")
EMU = (("boot", "boot from reset"),
       ("safeboot", "SAFE MODE from reset: the record, the SAFE boot as stock 1.12, hostile input, the reset cap; the question (ColdFire)"),
       ("machines", "every machine through MACHINE SEL's own list; a power-on with ours on the tracks (ColdFire)"),
       ("engine", "engine + LOAD/SAVE"),
       ("fuzz", "UI fuzz, two seeds, the audio interrupt at its real rate (ColdFire)"),
       ("paravoice", "PARA as one voice: joined notes take no slot, every note-off route, the chord's slot kept (ColdFire)"),
       ("dronehold", "DRONE HOLD: a latched voice never taken by another note, the no-slot path (ColdFire)"),
       ("meter", "DSP load meter (ColdFire)"),
       ("insovw", "FX on its release, the inserts overview held a second (ColdFire)"),
       ("overviews", "SYN, FLTR, MOD, AMP, VOICE held a second: their overviews; taps, value views and the VOICE menu as stock (ColdFire)"),
       ("updown", "UP / DOWN page through AMP's and FX's pages as stock's own pages; stock's pages unchanged (ColdFire)"),
       ("newproj", "new project (ColdFire)"),
       ("keepsamp", "SAMP kept across sample machines (ColdFire)"),
       ("functurn", "FUNC + turn (ColdFire)"),
       ("flexpool", "FLEX buffers in every sample machine's SAMP (ColdFire)"),
       ("aniz", "start-up animation, every frame"),
       ("depack", "the instrument's own depacker on every repacked section"),
       ("recorder", "recorder screen (ColdFire)"),
       ("mnmpages", "Monomachine pages and detents (ColdFire)"),
       ("playdet", "PLAY two detents a choice (ColdFire)"),
       ("question", "stock questions and held keys (ColdFire)"),
       ("mnmdefaults", "Monomachine start values (ColdFire)"),
       ("alloc", "GRID allocate slice locks (ColdFire)"),
       ("multisel", "multi-select delete (ColdFire)"),
       ("unused", "SELECT UNUSED (ColdFire)"),
       ("hooks", "overlays let go (ColdFire)"),
       ("recflow", "recorder flow (ColdFire)"),
       ("stockname", "stock NAME screen: NO, and its fallback (ColdFire)"),
       ("slice", "SLICE menus and SLICES keys (ColdFire)"),
       ("samplist", "sample list, browser, playhead (ColdFire)"),
       ("colsw", "MACHINE SEL columns, SYN held (ColdFire)"),
       ("msel", "MACHINE SEL in two columns (ColdFire)"),
       ("insel", "INSERT SEL, the FX icons in M.SEL's box and the title bar (ColdFire)"),
       ("livesel", "LIVE SELECT (ColdFire)"),
       ("drumamp", "AMP ON/OFF on the drum machines: H on the AMP page, the field, the DSP's mask (ColdFire)"),
       ("drive", "+DRIVE browser (ColdFire)"),
       ("drivenav", "+DRIVE keys and long names (ColdFire)"),
       ("jump", "DIRECT JUMP (ColdFire)"),
       ("slides", "parameter slides (ColdFire)"),
       ("flexcore", "FLEX on the ColdFire: recorder trigs, ARM, the panel, an older BOUNCE track's trigs (ColdFire)"),
       ("rectext", "RECORDER text inside its places, every state and R.LEN value (ColdFire)"),
       ("kbrec", "KEYBOARD kept through grid recording (ColdFire)"),
       ("kbhold", "KEYBOARD HOLD: PTN + KEYBOARD, held notes, chords, release (ColdFire)"),
       ("midiarp", "the arp on MIDI tracks (ColdFire)"),
       ("tune", "microtuning: KB SETUP's TUNE, the TUNING page, the frame's retune (ColdFire)"),
       ("tunerec", "microtuning: each project's tuning record (ColdFire)"),
       ("perform", "PERFORM: [MOD] + [FX], the macros, MODULATION SETUP, PERF MUTE (ColdFire)"),
       ("performrec", "PERFORM: the offsets and each project's macros record (ColdFire)"),
       ("insmove", "the inserts' records moved off upstream's sectors, old projects converted (ColdFire)"),
       ("drivemove", "our +Drive data out of upstream's places: tunings, bank lists, wishes, SAFE, DSP copy (ColdFire)"),
       ("slicefine", "SLICE editor: live edits, zero-crossing snap, deep zoom, a played slice picked (ColdFire)"),
       ("thres", "THRES on both processors (coupled)"),
       ("stocknote", "a stock note through both processors (coupled)"),
       ("ournote", "our machines' notes through both processors (coupled)"),
       ("parachord", "a PARA chord through both processors: one slot, every note heard (coupled)"),
       ("paralive", "PARA chords played live: every note joins and is held to its own key-up, a chord ends after its tail (ColdFire)"),
       ("flex", "FLEX: a recorder trig's take played by a note, on both processors (coupled)"),
       ("flexplay", "FLEX buffers played by a ONESHOT track, on both processors (coupled)"),
       ("mute", "FLEX MUTE SRC: the SRC track out of the mix, still recorded, on both processors (coupled)"),
       ("fineswap", "STRT/LEN/LOOP fine records swapped in and out (ColdFire)"),
       ("fineknob", "STRT's knob against stock's fine FREQ (ColdFire)"),
       ("modulation", "modulation: the destination lists, the LFO cascade, the moving controls (ColdFire)"),
       ("lineonly", "moving lines updated alone: the glass always as a full redraw (ColdFire)"),
       ("scope", "the oscilloscope: its frames as v1 drew them, alone, never queued behind the panel UART; every gain x1/8..x16, AUTO below x1 on full scale and never on an edge row (ColdFire)"),
       ("mixmeter", "the MIXER pages' meters over stock's pixels, alone updates, latches and the CLIP label (ColdFire)"),
       ("longkeys", "[TEMPO] held a second: the system meter; [PRESET] held a second: the sample browser (browse only on a track with no sample machine); their taps and FUNC combos as stock (ColdFire)"),
       ("mixovw", "the OUTPUTS overview: FUNC + [MOD] held a second, every fixed-point output and its clip marks, live; a tap still opens stock's MIXER; let go, the screen of before (ColdFire)"),
       ("mixcpu", "the MIXER pages' CPU: stock's redraws held to 10 a second (a key or knob at once), a full draw's meters, what they add on each page, under their ceilings (ColdFire)"),
       ("lfowaves", "LFO waveforms: the seven new waves modulating and drawn (ColdFire)"),
       ("lfo4", "LFO4: modulating, the cascade both ways, its lists, its stored values, its page (ColdFire)"),
       ("link16", "sample link (ColdFire)"),
       ("banks", "PROJECT RAM banks B..D: loaded, played, edited, LOAD TO PROJECT, controls (ColdFire)"),
       ("pools", "per-project pools (ColdFire)"),
       ("erase", "ERASE MOD DATA (ColdFire)"),
       ("wishes", "the wishes record through stock's SAVE, LOAD, memcpy, memset (ColdFire)"),
       ("wishitems", "the wishes record on kits, patterns, songs and the project settings (ColdFire)"),
       ("matrix", "the matrix's routes heard as stock's route 1, at a constant cost (ColdFire)"),
       ("destpop", "the DEST popup: an LFO's routes, first route in DEST/DEP, mute and delete; stock's DEST check unchanged (ColdFire)"),
       ("setuprows", "the routes popup's MOD SETUP rows: stock's entries edited through stock's objects, mute heard as 0 (ColdFire)"),
       ("knobnotch", "knob notches on bipolar values (CC, NRPN, Overbridge exact; unipolar as stock), our popups' slow turns (ColdFire)"),
       ("paravmenu", "PARA on the VOICE menu's B: stock's places as stock's, B OFF / ON on ANALOG 2 and JUNO (ColdFire)"),
       ("voiceled", "PARA on the VOICE key's LED: magenta on a PARA ON track, stock's teal/backlight/white elsewhere, refreshed on a change (ColdFire)"),
       ("envclone", "ENV1/ENV2's clone against stock's own AMP envelope (SHARC runner)"),
       ("ampdsp", "AMP ON/OFF: OFF unity bit for bit, ON and every other slot stock's (SHARC runner)"),
       ("link16-dead", "sample link, dead link (ColdFire)"))
EMU_ID = {n: i for i, n in EMU}
# 2026-11-16 (the User: "for me if a feature break, it is not reason to not flash. we should not flash what can
# brick"): feature steps. A failure of one is recorded in the build's .gate.json as a known issue and printed; it
# does not block CLEARED TO FLASH. Every other step blocks, the RAM guard and `rammap` included. Only steps whose
# failure cannot harm the unit (a feature that misbehaves, no fault, no corruption) belong here. A RAM-guard
# or wild-read failure inside one still blocks.
# (slides was one from 2026-11-19 to 11-20, until its check-timing fix and the half-rate declaration: the User,
# "slides then passes and leaves the feature list")
FEATURE_STEPS = ("flexplay",)
assert all(f in dict(EMU) for f in FEATURE_STEPS) and not set(FEATURE_STEPS) & set(BRICK_EMU)


def sharc_ids() -> dict[str, list[str]]:
    """{'sharc:a+b': [a, b]} for each part of the SHARC runner (gate_sharc.parts())"""
    import gate_sharc                           # noqa: PLC0415
    return {"sharc:" + "+".join(p): p for p in gate_sharc.parts()}


def all_ids() -> list[tuple[str, str]]:
    return ([x for x in FIRST if x[0] != "unit"] + [(i, n) for i, n in EMU if i in BRICK_EMU]
            + [x for x in FIRST if x[0] == "unit"] + [(i, n) for i, n in EMU if i not in BRICK_EMU]
            + [(i, "SHARC runner: " + ",".join(p)) for i, p in sharc_ids().items()])


def step_rows() -> list[dict]:
    """--list (2026-11-16): each step's id, name, whether a pass can be reused, and its expected time, limit and
    memory peak (scripts/gate_times.json, measured on the farm; a step not in it: its "default"). Read for --list
    only: no step's verdict reads it, so it is in no reuse record"""
    times = json.loads((HERE / "gate_times.json").read_text())
    rows = []
    for i, n in all_ids():
        t = times["steps"].get(i, times["default"])
        expect = int(t["expect_s"])
        rows.append({"id": i, "name": n, "reused": not n.endswith("(never reused)"), "expect_s": expect,
                     "limit_s": int(t.get("limit_s", max(times["limit_min_s"], times["limit_factor"] * expect))),
                     "mem_gb": float(t["mem_gb"])})
    return rows


def resolve_only(spec: str) -> set[str]:
    """--only's list -> step ids. A SHARC runner step's own name (e.g. chords) names its part;
    'sharc' every part. Unknown names are an error."""
    ids = {i for i, _ in all_ids()}
    parts = sharc_ids()
    out = set()
    for x in (s.strip() for s in spec.split(",")):
        if not x:
            continue
        if x in ids:
            out.add(x)
        elif x == "sharc":
            out |= set(parts)
        elif any(x in p for p in parts.values()):
            out |= {i for i, p in parts.items() if x in p}
        elif "sharc:" + x in parts:
            out.add("sharc:" + x)
        elif x == "mnm":                        # 2026-11-16: the runner's mnm, in its parts (mnm-...)
            out |= {i for i, p in parts.items() if any(s.startswith("mnm-") for s in p)}
        else:
            raise SystemExit(f"--only: no step {x!r} (python scripts/ship_gate.py --list)")
    return out


def _frozen(fn):
    """FN with its free variables bound to their values now. A deferred ColdFire step's body
    runs after the rest of the setup, which reuses names (js, g, kit, ...); frozen, it reads
    exactly what it read when it ran in place (v0.37 and before)."""
    if not getattr(fn, "__closure__", None):
        return fn
    import types                                # noqa: PLC0415
    cells = []
    for c in fn.__closure__:
        try:
            cells.append(types.CellType(c.cell_contents))
        except ValueError:                      # not bound yet: left as it is
            cells.append(c)
    new = types.FunctionType(fn.__code__, fn.__globals__, fn.__name__, fn.__defaults__, tuple(cells))
    new.__kwdefaults__ = fn.__kwdefaults__
    return new


def repo_modules() -> set[str]:
    return {str(pathlib.Path(m.__file__).resolve()) for m in list(sys.modules.values())
            if getattr(m, "__file__", None) and pathlib.Path(m.__file__).resolve().is_relative_to(ROOT)}


class Stop(Exception):
    pass


LOWTRAP: dict[int, list[str]] = {}         # v0.46: wild reads seen, per thread (emulib/lowtrap.py)
LIVE: list[subprocess.Popen] = []            # steps running (the SHARC runner beside the rest)
RAMGUARD: dict[str, str] = {}                # 2026-11-16: {"rows": the build's RAM chunks (JSON), or "error"}
# 2026-11-16: the boot step's power-on read through stock 1.12's +Drive bounce buffer (a whole 64 KiB call,
# its destination unaligned, in RAM nothing of ours or stock's uses: dnfw.mods.stockram)
from dnfw.mods.stockram import PROBE_READ as _PROBE_READ   # noqa: E402
BOUNCE_SECTOR, BOUNCE_BYTES, BOUNCE_BUF = _PROBE_READ
NOT_EMULATOR = {"code fresh", "rebuild", "hwrules", "mfcheck", "coldfire_main", "pytest", "overbridge", "overbridge_control",
                "linkfast"}   # steps that run no ColdFire
SCRATCH: dict[str, str] = {}                 # 2026-11-16: a step's trace folder -> its own temporary folder (run())


def run(name, cmd, log_dir, env=None, cwd=ROOT, trace=None):
    """Run CMD, log its output to LOG_DIR/NAME.log, -> (rc, output). TRACE: a directory for
    the step's trace (gate_cache: what it read)."""
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    t = time.time()
    env = {**os.environ, **(env or {})}
    if name not in NOT_EMULATOR:                # 2026-11-16: every emulator step runs under the RAM guard
        if RAMGUARD.get("error"):               # (emulib/ramguard.py); one that cannot is a failed step
            out = f"CODEGUARD FAIL: the RAM guard cannot run: {RAMGUARD['error']}"
            print(f"  {out}", flush=True)
            LOWTRAP.setdefault(threading.get_ident(), []).append(f"{name}: {out}")
            return 99, out
        env.setdefault("DNFW_DDR_ALIAS", "1")   # 0x4e... is 0x46..., as on the instrument (emulib/quickboot.py)
        if RAMGUARD.get("rows"):
            env["DNFW_RAMGUARD"] = RAMGUARD["rows"]
            env["DNFW_RAMGUARD_LOG"] = str(log_dir / "ramguard.jsonl")
            if trace is None:                   # the guard is installed by the tracer's sitecustomize
                env["PYTHONPATH"] = os.pathsep.join([str(HERE / "gate_trace")]
                                                    + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    if trace is not None:
        trace.mkdir(parents=True, exist_ok=True)
        env["DNFW_GATE_TRACE"] = str(trace)
        env["PYTHONPATH"] = os.pathsep.join([str(HERE / "gate_trace")]
                                            + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        # 2026-11-16 (gate speed): the step's Python compiles every module from its source into a byte-code
        # folder of the step's own (inside TRACE, which the tracer leaves out), and reads no .pyc from the tree or
        # the interpreter: what ran is the sources (traced) under the interpreter (traced), never a .pyc that a
        # copy of the tree may hold or lack (gate_cache.PYCACHE)
        env["PYTHONPYCACHEPREFIX"] = str(trace / gate_cache.PYCACHE)
        # ... and its temporary files in a folder of its own, made empty for this step (a short path, under the
        # usual temporary folder; removed when the step ends). gate_cache.inputs leaves it out of the record when
        # every program the step ran is accounted for (then the step made all that is in it); else it stays in
        # (2026-11-16: pytest's numbered folders under a shared TMPDIR were inputs, and differed between a tree's
        # copy and the tree, so the unit tests were never reused)
        scratch = SCRATCH.setdefault(str(trace), tempfile.mkdtemp(prefix="gs-"))
        env["TMPDIR"] = env["DNFW_GATE_SCRATCH"] = scratch
    proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    LIVE.append(proc)
    out, _ = proc.communicate()
    LIVE.remove(proc)
    (log_dir / f"{name}.log").write_text(out)
    trap = [ln for ln in out.splitlines() if ln.startswith(("LOWTRAP FAIL", "CODEGUARD FAIL"))]
    if trap:                                    # v0.46: a wild read fails the step it ran in (remoteui-6: and
        LOWTRAP.setdefault(threading.get_ident(), []).append(f"{name}: {trap[0][:600]}")   # a code write)
    print(f"    rc {proc.returncode}, {round(time.time() - t)} s, log {log_dir / (name + '.log')}",
          flush=True)
    return proc.returncode, out


def own_inputs(own=None) -> dict[str, str]:
    """What this script's verdicts read: itself, the cache and tracer, and every module of
    the repository it has imported (the build's layout among them). OWN (v0.28): a step
    whose verdict reads only those files (and its own traced run): the cache, the tracer
    and OWN."""
    files = {HERE / "gate_cache.py", HERE / "gate_trace" / "sitecustomize.py"}
    if own is not None:
        files |= {pathlib.Path(f).resolve() for f in own}
    else:
        files |= {HERE / "ship_gate.py", ROOT / "src/dnfw/mods/waverider_code.json",
                  ROOT / "src/dnfw/waverider/sharc_code.json"}
        for m in list(sys.modules.values()):
            f = getattr(m, "__file__", None)
            if f and pathlib.Path(f).resolve().is_relative_to(ROOT):
                files.add(pathlib.Path(f).resolve())
    out = {}
    for f in sorted(files):
        if f.is_file():
            out[str(f)] = "f:" + hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def _mnm_rep(lo: int, top: int, n: int, c: int) -> int:
    """csrc/sampler/fmt.c mnm_rep: a Monomachine control's coarse value in the middle of its
    choice C of N (the knob k's choice is k x N >> 7)"""
    ks = [k for k in range(128) if (k * n) >> 7 == c] or [0]
    return lo + ((ks[0] + ks[-1]) // 2 * 2 * top + 127) // 254


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stock", type=pathlib.Path, nargs="?", help="Elektron's Digitone_II_OS1.12.syx")
    p.add_argument("build", type=pathlib.Path, nargs="?", help="the exact .syx that will be flashed")
    p.add_argument("--venv", default=str(ROOT.parent / "digikit/.venv/bin/python"),
                   help="python with digikit's emulator deps (unicorn)")
    # 2026-11-12 (owner: "Yes, with a cross-check"; docs/gate-speed.md D, C): the pure-Python SHARC
    # emulator's steps (the SHARC runner, the coupled THRES and FLEX) run under PyPy, 3-4x faster,
    # same checks. Its venv holds the same patched libunicorn. scripts/gate_crosscheck.py reruns
    # them under CPython and compares every report. "" (or no such file) runs them under CPython.
    p.add_argument("--pypy", default=str(ROOT.parent / "pypy-venv/bin/python"),
                   help="PyPy with numpy and the patched unicorn, for the SHARC emulator's steps")
    p.add_argument("--digikit-sharc", default=os.environ.get(
        "DNFW_DIGIKIT_SHARC", str(ROOT.parent / "digikit-wt-sharcemu")))
    p.add_argument("--only", metavar="STEP[,STEP...]",
                   help="run just these steps (--list), each recorded in the reuse cache as a full run "
                        "would; never a gate pass, never the build's .gate.json")
    p.add_argument("--list", action="store_true", help="print the steps' names, in the full run's order")
    p.add_argument("--json", action="store_true", help="with --list: as JSON (scripts/gate_parallel.py reads it)")
    a = p.parse_args()
    a.sharc_py = a.pypy if a.pypy and os.path.isfile(a.pypy) else sys.executable
    a.coupled_py = a.pypy if a.pypy and os.path.isfile(a.pypy) else a.venv

    if a.list:
        rows = step_rows()
        if a.json:
            print(json.dumps(rows))
            return 0
        print("  the full run's order          expected   limit   peak  (the farm; scripts/gate_times.json)")
        for r in rows:
            print(f"  {r['id']:28s} {r['expect_s']:6d} s {r['limit_s']:6d} s {r['mem_gb']:4.1f} GB  {r['name']}")
        par = sorted((r for r in rows if r["reused"]), key=lambda r: -r["expect_s"])
        print("\n  scripts/gate_parallel.py's order (each step alone, longest first; then ONE full run, which reuses "
              "them):\n  " + ", ".join(f"{r['id']} {r['expect_s']}" for r in par))
        print("\n  (a SHARC runner step's own name, e.g. chords, names its part; 'sharc' names them all, 'mnm' its "
              "parts)")
        return 0
    if a.stock is None or a.build is None:
        p.error("the stock .syx and the build are required")
    only = resolve_only(a.only) if a.only is not None else None
    if only is not None and not only:
        p.error("--only names no step")

    def wanted(sid):
        return only is None or sid in only

    if "DT2_SECTIONS" not in os.environ:
        print("DT2_SECTIONS must point at stock 1.11's extracted sections.\n\nDO NOT FLASH.")
        return 2

    build_bytes = read_image(a.build)
    sha = hashlib.sha256(a.build.read_bytes()).hexdigest()
    work = pathlib.Path(tempfile.mkdtemp(prefix="ship_gate_", dir=ROOT / "out"
                                         if (ROOT / "out").is_dir() else None))
    logs = work / "logs"
    logs.mkdir()
    # 2026-11-16 (the combined build 7f7e7d6c, EXCEPTION at every boot): every chunk this tree's build
    # places in RAM, for the RAM guard in every emulator step (emulib/ramguard.py)
    try:
        sys.path.insert(0, str(HERE))
        from emulib import ramguard as _rg      # noqa: PLC0415
        _rows = _rg.build_rows(load(build_bytes).container.find(3).unpack())   # with the image's own chunks
        _rg.chunks_file(_rows, work / "ramguard.json")
        RAMGUARD["rows"] = str(work / "ramguard.json")
        print("  RAM guard: " + ", ".join(f"{r['load']:#010x}+{len(r['code']) // 2:,} B" for r in _rows), flush=True)
    except Exception as e:                      # noqa: BLE001 -- an unguarded emulator step is a failed one
        RAMGUARD["error"] = f"{type(e).__name__}: {e}"
    print(f"ship gate: {a.build.name}\n  sha256 {sha}\n  work {work}\n"
          + (f"  ONLY: {', '.join(sorted(only))} (a partial run: never a gate pass)\n" if only is not None else ""),
          flush=True)
    results: dict[str, str] = {}

    known: dict[str, str] = {}                 # FEATURE_STEPS that failed: recorded, printed, not blocking

    def gate(name, ok, detail, feature=False):
        if not ok and feature and not any(t in detail for t in ("CODEGUARD FAIL", "LOWTRAP FAIL", "the RAM guard")):
            results[name] = "KNOWN ISSUE (a feature step: does not block): " + detail
            known[name] = detail
            print(f"[KNOWN ISSUE] {name}: {detail}\n  (a feature step, FEATURE_STEPS: recorded, does not block)\n",
                  flush=True)
            return
        results[name] = ("PASS: " if ok else "FAIL: ") + detail
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}\n", flush=True)
        if not ok:
            raise Stop(name)

    reused: dict[str, str] = {}
    setup_mods: set[str] = set()                # the repository's modules once the setup is done

    def cached(name, cmds, body, own=None):
        """A long step: reused if a pass with these commands read nothing that has changed
        since (gate_cache); else BODY(trace) -> (ok, detail), and a pass is kept. OWN: the
        files the step's verdict reads (v0.28, the SHARC runner's: gate_sharc.py), else
        all of this script's own inputs."""
        key = [gate_cache.norm_cmd(c, work) for c in cmds]
        rec = gate_cache.lookup(ROOT, name, key, work)
        if rec:
            reused[name] = rec["date"]
            print(f"  (reused: the pass of {rec['date']}, build {rec['build'][:12]}; its "
                  f"{len(rec['inputs'])} inputs are byte-identical now)", flush=True)
            return True, rec["detail"] + " [reused: no input changed]"
        tdir = work / "traces" / "".join(c if c.isalnum() else "_" for c in name)
        LOWTRAP.pop(threading.get_ident(), None)
        ok, detail = body(tdir)
        wild = LOWTRAP.pop(threading.get_ident(), None)
        if wild:                                # v0.46: whatever the step found, a wild read fails it
            ok, detail = False, ("a read below 0x40000000 by our code (the v0.44 freeze's kind), or a write into "
                                 "the C chunk's code or rodata (emulib/codeguard.py), or a change by anyone but "
                                 "our loader to a chunk the build placed in RAM (emulib/ramguard.py): "
                                 + "; ".join(wild))
        if ok:
            # v0.38: this script's own inputs are the same in a full run and an --only run: the
            # whole setup runs in both, and nothing after it may import a module of ours
            late = repo_modules() - setup_mods
            if own is None and late:
                return False, (f"ship_gate imported {sorted(late)} after its setup: its own inputs would "
                               "differ between a full and an --only run; import it in the setup")
            ins = gate_cache.inputs(tdir, work, logs)
            ins.update(own_inputs(own))
            gate_cache.store(ROOT, name, key, ins, detail, sha)
        shutil.rmtree(tdir / gate_cache.PYCACHE, ignore_errors=True)   # the step's own byte-code and temporary
        shutil.rmtree(SCRATCH.pop(str(tdir), ""), ignore_errors=True)  # files (run()), after its inputs are hashed
        return ok, detail

    plan: dict[str, tuple] = {}                 # the ColdFire emulator steps, run in EMU's order

    def later(sid, gname, cname, cmds, body):
        assert EMU_ID.get(gname) == sid, (sid, gname)
        plan[sid] = (gname, cname, cmds, _frozen(body))

    sharc = None
    sharc_box: list = []                        # (ok, detail) of each SHARC part as it ends
    sharc_want: list = []

    def sharc_failed():
        """a SHARC part has failed: stop now, not after the ColdFire steps"""
        bad = [d for ok, d in list(sharc_box) if not ok]
        if bad:
            gate("SHARC runner", False, bad[0])

    try:
        # setup: everything below runs in a full run and in an --only run alike (the build
        # read, its sections written, every step's commands made), so a step's commands and
        # this script's own inputs are the same in both
        stock = load(read_image(a.stock))
        built = load(build_bytes)
        sec3 = built.container.find(3).unpack()
        stock3 = stock.container.find(3).unpack()
        stock7 = stock.container.find(7).unpack()
        sec7 = built.container.find(7).unpack()
        bdir = work / "build"
        bdir.mkdir()
        (bdir / "section_3_MAIN_OS.bin").write_bytes(sec3)
        (work / "stock_section_3_MAIN_OS.bin").write_bytes(stock3)
        dsp_changed = sec7 != stock7
        want7 = dsp.section7(stock7) if dsp_changed else None
        import gate_sharc                       # noqa: PLC0415
        import gate_playhead                    # noqa: PLC0415 (samplist's playhead verdict; its control runs it too)
        import slides_stock                     # noqa: PLC0415 (slides' stock comparison, 2026-11-20)
        from dnfw.mods import waverider as W    # noqa: PLC0415
        lay = W.SPEC.get("layout", {})

        # 1. preflight
        if wanted("preflight"):
            ok, text = safety.report(safety.preflight(stock, build_bytes))
            (logs / "preflight.log").write_text(text)
            gate("preflight", ok, "bootstrap/updater/meta/Outbox untouched, signature, DSP size"
                 if ok else text[-600:])
        # v0.33: the ColdFire code the build carries is what csrc/ compiles to now (v0.33's
        # first builds carried a waverider_code.json older than three C fixes, and the gate's
        # emulator steps tested the old code; scripts/gen_waverider_code.py --check)
        # 2026-11-16 (7f7e7d6c: EXCEPTION at every power-on, the stamp at 0x46708000 under stock 1.12's
        # +Drive bounce buffer): every chunk this build places, and every RAM area it uses, clear of the RAM
        # stock 1.12 writes (dnfw.mods.stockram: the bounce buffer's reach and the measured map). A chunk
        # counts when its bytes are in this build's MAIN OS (a NOBOOT build has no stamp).
        if wanted("rammap"):
            from dnfw.mods import Extent as _Ext, RAM as _RAM_SEC, stockram   # noqa: PLC0415
            _ext = []                           # what the loader places: every CODE chunk in this image's area
            if len(sec3) > platform.STOCK_LENGTH:
                _blob = sec3[platform.STOCK_LENGTH:]
                _total, _count = struct.unpack_from(">II", _blob, 4)
                for _i in range(_count):
                    _off, _n = struct.unpack_from(">II", _blob, 16 + 12 * _i)
                    if _blob[12 + 12 * _i:16 + 12 * _i] == area.CODE:
                        _c = area.CodeChunk.unpack(_blob[_off:_off + _n])
                        _ext.append(_Ext(_RAM_SEC, _c.load, len(_c.image) + _c.bss,
                                         f"the image's code chunk at {_c.load:#010x} ({len(_c.image):,} B + {_c.bss:,} B BSS)"))
            _rows = json.loads((work / "ramguard.json").read_text()) if RAMGUARD.get("rows") else []
            _content = {(r["load"], len(r["code"]) // 2) for r in _rows}
            _ext += [e for e in stockram.ours() if (e.start, e.length) not in _content]   # its run-time areas
            _bad = stockram.clashes(_ext)
            gate("our RAM clear of what stock 1.12 writes", not _bad,
                 "; ".join(_bad)[:900] if _bad else
                 f"{len(_ext)} chunks (the image's area) and run-time areas (this tree's), none in the "
                 f"{len(stockram.stock_ranges())} ranges stock 1.12 writes (the bounce buffer, the measured map)")

        if wanted("code-fresh"):
            rc_c, out_c = run("code fresh", [sys.executable, "scripts/gen_waverider_code.py", "--check"], logs,
                              env={"PYTHONPATH": str(ROOT / "src")})
            gate("ColdFire code current", rc_c == 0, out_c.strip()[-400:])
            rc_k, out_k = run("code fresh (SAFE MODE)", [sys.executable, "scripts/gen_safemode_code.py", "--check"], logs,
                              env={"PYTHONPATH": str(ROOT / "src")})   # 2026-11-21: the kernel chunk is the sources'
            gate("SAFE MODE's kernel code current", rc_k == 0, out_k.strip()[-400:])
        # and the file under test is what this tree builds, byte for byte (so every step below
        # tests these sources, not an older build of them)
        if wanted("rebuild"):
            rb = work / "rebuilt.syx"
            # 2026-11-14 (main: the 1.12 gate's blind spots): every 1.12 build is NOBOOT (scripts/noboot.py: stock's
            # intro, no stamp), so an image without the boot screen is rebuilt the NOBOOT way; still byte for byte
            from dnfw.mods import SHIPPED            # noqa: PLC0415  (waverider, lfowaves: the patcher's own list)
            from dnfw.mods import waverider as Wr   # noqa: PLC0415
            nb = hasattr(Wr, "_boot") and not has_bootscreen(sec3)
            pre = f"import sys; sys.path.insert(0, {str(HERE)!r}); import noboot; noboot.install(); " if nb else ""
            mods_ = [x for mid in SHIPPED for x in ("--mod", mid)]
            rc_b, out_b = run("rebuild", [sys.executable, "-c", pre + "from dnfw.cli.main import main; main()", "mods",
                                          "apply", a.stock, *mods_, "-o", rb], logs,
                              env={"PYTHONPATH": str(ROOT / "src")})
            same_b = rc_b == 0 and rb.exists() and read_image(rb) == build_bytes
            how = "dnfw mods apply (NOBOOT, scripts/noboot.py)" if nb else "dnfw mods apply"
            gate("the build is this tree's", same_b, f"{how} here gives the same file, byte for byte"
                 if same_b else (f"it differs from {how}: rebuild it from this tree" if rc_b == 0 else out_b[-400:]))

        # 2 + 3. the DSP program
        if dsp_changed:
            if wanted("dsp-identity"):
                same = sec7 == want7
                gate("DSP identity", same, "section 7 is exactly dsp.section7(stock), the image "
                     "the SHARC gate runs" if same else "section 7 is not what the SHARC gate "
                     "tests; its result would not apply to this file")
            # v0.32: the hardware rules no emulator sees (complex-ping's hwrules.py, from a
            # checkout of his digitone-2-modding-skill beside this repository): our code and
            # round each patch, against the stock image's own
            if wanted("hwrules"):
                skill = ROOT.parent / "digitone-2-modding-skill"
                rc, out = run("hwrules", [sys.executable, "scripts/gate_hwrules.py", a.stock, a.build, skill], logs,
                              env={"PYTHONPATH": "src"})
                gate("DSP hardware rules", rc == 0 and "PASS:" in out, out.strip().splitlines()[-1] if out.strip() else
                     "gate_hwrules.py printed nothing")
                # 2026-11-21 (docs/selas-encoding.md, "the corpus"): every multifunction word of ours is the
                # instruction its generator meant, in the build's own bytes, read by digikit and by selmap
                rc, out = run("mfcheck", [sys.executable, "scripts/gate_mf.py", a.build, a.digikit_sharc], logs,
                              env={"PYTHONPATH": "src"})
                gate("DSP multifunction words", rc == 0 and "PASS:" in out,
                     out.strip().splitlines()[-1] if out.strip() else "gate_mf.py printed nothing")
            # v0.25: beside the ColdFire steps (its own core); v0.38: started after the unit
            # tests, its verdict looked at after each ColdFire step and taken at the end
            # v0.28: the step is scripts/gate_sharc.py's; its reuse record holds what the
            # runner read and that file, not this script or the ColdFire's artefacts
            sharc_want[:] = [p for sid, p in sharc_ids().items() if wanted(sid)]

            def sharc_thread():
                # v0.28: in parts (gate_sharc.parts: together the runner's default steps), each
                # cached on its own; the verdict is every part's
                try:
                    for steps in sharc_want:
                        cmd = gate_sharc.command(a.stock, a.digikit_sharc, steps, "part_" + "_".join(steps),
                                                 python=a.sharc_py)

                        def body(tdir, cmd=cmd, steps=steps):
                            rc, out = run(f"sharc_m5_{'_'.join(steps)}", cmd, logs, trace=tdir)
                            return gate_sharc.verdict(rc, out)
                        ok, detail = cached(f"SHARC runner: {','.join(steps)}", [cmd], body, own=gate_sharc.OWN)
                        sharc_box.append((ok, f"{','.join(steps)}: {detail}"))
                        print(f"  (SHARC runner, {','.join(steps)}: {'PASS' if ok else 'FAIL'})", flush=True)
                        if not ok:
                            break
                except Exception as e:          # noqa: BLE001
                    sharc_box.append((False, f"the runner did not run: {e}"))
        else:
            results["DSP identity"] = results["SHARC runner"] = "n/a: section 7 is stock"
            if only is not None and any(s.startswith("sharc:") or s in ("dsp-identity", "hwrules") for s in only):
                print("  (section 7 is stock: the DSP steps do not apply)", flush=True)

        # v0.30: a check keyed on a C symbol must not be skipped because the symbol never
        # reached the layout (6k was, once: smp_machine_commit was linked but not listed)
        # (v0.38: before the emulator steps; it reads only the C and the layout)
        if wanted("symbols"):
            csrc_text = "".join(f.read_text() for f in (ROOT / "csrc").rglob("*.c"))
            for sym, what in (("smp_question_up", "stock questions and held keys (ColdFire)"),
                              ("smp_machine_commit", "SAMP kept across sample machines (ColdFire)"),
                              ("smp_knob_at", "FUNC + turn (ColdFire)"),
                              ("smp_pl_on", "per-project pools (ColdFire)"),
                              ("msel_draw", "MACHINE SEL in two columns (ColdFire)"),
                              ("ls_commits", "LIVE SELECT (ColdFire)"),
                              ("as_mask", "AMP ON/OFF on the drum machines: H on the AMP page, the field, the DSP's mask (ColdFire)"),
                              ("jmp_on", "DIRECT JUMP (ColdFire)"),
                              ("tn_retune", "microtuning: KB SETUP's TUNE, the TUNING page, the frame's retune (ColdFire)"),
                              ("tn_poll", "microtuning: each project's tuning record (ColdFire)"),
                              ("slc_live_sends", "SLICE editor: live edits, zero-crossing snap, deep zoom, a played slice picked (ColdFire)")):
                if re.search(rf"\b{sym}\b", csrc_text) and sym not in lay:
                    gate(what, False, f"{sym} is in the C but not in the layout: the check cannot run")
            results["symbols"] = "PASS: every C-keyed check has its symbol in the layout"
            print("[PASS] symbols: every C-keyed check has its symbol in the layout\n", flush=True)

        # 4. ColdFire instruction set
        # (va, offset of its image in sec3, length) for every CODE chunk, from the
        # area's own directory -- the same table the loader reads.
        code_chunks = []
        if len(sec3) > platform.STOCK_LENGTH:
            blob = sec3[platform.STOCK_LENGTH:]
            total, count = struct.unpack_from(">II", blob, 4)
            for i in range(count):
                cid = blob[12 + 12 * i:16 + 12 * i]
                off, n = struct.unpack_from(">II", blob, 16 + 12 * i)
                if cid != area.CODE:
                    continue
                chunk = area.CodeChunk.unpack(blob[off:off + n])
                code_chunks.append((chunk.load, platform.STOCK_LENGTH + off + 16,
                                    len(chunk.image), chunk.image))
        for va, at, n, image in (code_chunks if wanted("coldfire") else []):
            if va in DATA_ONLY:
                results[f"ColdFire: chunk {va:#x}"] = f"n/a: {DATA_ONLY[va]}"
                print(f"[n/a ] ColdFire: chunk {va:#x}: {DATA_ONLY[va]}\n", flush=True)
                continue
            spans = code_ranges().get(va, [(va, va + len(image))])
            for lo, hi in spans:
                if not (va <= lo < hi <= va + len(image)):
                    gate(f"ColdFire: chunk {va:#x}", False,
                         f"recorded code range {lo:#x}..{hi:#x} is outside the chunk")
                f = work / f"code_{lo:08x}.bin"
                f.write_bytes(image[lo - va:hi - va])
                rc, out = run(f"coldfire_{lo:08x}", [sys.executable, "scripts/check_coldfire.py",
                                                     f, "--base", hex(lo)], logs)
                gate(f"ColdFire: code {lo:#x}..{hi:#x}", rc == 0, "no scale-8 addressing"
                     if rc == 0 else out[-800:])
            if va == safemode_code()[0]:
                end = va + len(image)
                note = (f"SAFE MODE's unpatch table {safemode_code()[1]:#x}..{end:#x}: appended data that never "
                        f"executes (stock 1.12's bytes the kernel copies)")
                results[f"ColdFire: chunk {va:#x} table"] = f"n/a: {note}"
                print(f"[n/a ] ColdFire: {note}\n", flush=True)
                ok, detail = sm_control(image, va, work, logs)
                gate("ColdFire: SAFE MODE control (a scale-8 store planted in the kernel fails the scan)", ok, detail)
        # each executed range, at its place in MAIN OS's appended area (where the chunk's
        # image sits before the loader copies it): file offset + (start - load)
        if wanted("coldfire"):
            executed = [(at + lo - va, hi - lo) for va, at, n, image in code_chunks if va not in DATA_ONLY
                        for lo, hi in code_ranges().get(va, [(va, va + n)])]
            rc, out = run("coldfire_main", [sys.executable, "scripts/check_coldfire.py",
                                            bdir / "section_3_MAIN_OS.bin", "--base", hex(MAIN_BASE),
                                            "--against", work / "stock_section_3_MAIN_OS.bin"], logs)
            if rc == 2:
                gate("ColdFire: MAIN OS", False, "no objdump: unchecked is not passing")
            hits = [int(h, 16) for h in HIT.findall(out)] if rc else []
            stock_end = MAIN_BASE + len(stock3)
            bad = [h for h in hits if h < stock_end or any(
                MAIN_BASE + at <= h < MAIN_BASE + at + n for at, n in executed)]
            gate("ColdFire: MAIN OS", not bad,
                 f"{len(hits)} hit(s), all in appended data that never executes" if not bad
                 else f"{len(bad)} in executed code, first at {bad[0]:#x}")

        # 4b. v0.41 (docs/ROADMAP.md 1b, docs/overbridge.md): no byte the build changes lies in an
        # instruction Overbridge's audio path can run (scripts/gate_overbridge.py: from the mode-6
        # packet builder, the USB input to TX, the USB writer, the mode getter, and the audio
        # interrupt up to the link's hook, followed through every branch and call); and the
        # detector's negative control, rooted at a site the build patches, must find it
        # 2026-11-21 (docs/safe-mode.md): SAFE MODE runs stock 1.12: the kernel is the area's first CODE chunk, its
        # code the sources', and its unpatch table applied to this MAIN OS gives stock 1.12 byte for byte except the
        # two runs the loader is running in; every override site stock under it (scripts/safeboot_table.py)
        if wanted("safeboot-table"):
            rc_sb, out_sb = run("safeboot-table", [a.venv, "-u", "scripts/safeboot_table.py", a.stock, a.build], logs)
            last_sb = out_sb.strip().splitlines()[-1] if out_sb.strip() else ""
            gate("SAFE MODE's table gives stock 1.12", rc_sb == 0 and last_sb.endswith("checks pass"),
                 last_sb if rc_sb == 0 else out_sb[-800:])

        if wanted("overbridge"):
            ob_args = [sys.executable, "scripts/gate_overbridge.py", work / "stock_section_3_MAIN_OS.bin",
                       bdir / "section_3_MAIN_OS.bin"]
            rc_o, out_o = run("overbridge", [*ob_args, "--json", work / "overbridge.json"], logs)
            rc_c, out_c = run("overbridge_control", [*ob_args, "--control", "0x400DB1F6"], logs)
            last = out_o.strip().splitlines()[-1] if out_o.strip() else ""
            good = rc_o == 0 and rc_c == 0 and last.startswith("PASS")
            gate("Overbridge's code untouched", good,
                 last[6:] + " (its negative control found the patched applier)" if good
                 else (out_o[-500:] + " | control: " + out_c[-200:]))

        # 4c. 2026-11-18 (the User: "allow if bit identical yes and add a flag to switch back if needed"): every
        # stocklink site the build edits (csrc/stocklink, DN2_STOCK_LINK_FAST; the only edits the overbridge step
        # allows in Overbridge's path) against the same build with it put back to stock's bytes, under Unicorn:
        # random frames, every USB mode incl. Overbridge's, mode switches, re-installs, every byte and peripheral
        # write, with negative controls (scripts/check_stocklink.py gate). A build without them passes as is.
        if wanted("linkfast"):
            rc_l, out_l = run("linkfast", [a.venv, "-u", "scripts/check_stocklink.py", "gate",
                                           work / "stock_section_3_MAIN_OS.bin", bdir / "section_3_MAIN_OS.bin",
                                           ROOT / "src/dnfw/mods/waverider_code.json"], logs)
            last = out_l.strip().splitlines()[-1] if out_l.strip() else ""
            gate("stock's link passes, the same bytes", rc_l == 0 and last.startswith("PASS"),
                 last[6:] if rc_l == 0 and last.startswith("PASS") else out_l[-800:])

        # 5. boot from reset
        boot_cmd = [a.venv, "-u", "scripts/emu_boot_check.py", bdir / "section_3_MAIN_OS.bin"]
        # v0.37: the build plays the start-up animation (dnfw.bootanim): every frame the stamp
        # shows during the boot, checked bit for bit against his (s!Rwa²'s), all of them shown
        from dnfw.mods import waverider as Wb   # noqa: PLC0415
        # 2026-11-13 (main: the 1.12 gate's blind spots): only when THIS image carries the boot screen, i.e. its intro
        # jumps to the stamp (dnfw.mods.bootscreen.SPEC, this layer's addresses). A NOBOOT build (every 1.12 build:
        # stock's intro, no stamp) has no animation to check: from reset it is held to the boot alone, as stock is
        anim = hasattr(Wb, "_boot") and has_bootscreen(sec3)
        noboot = hasattr(Wb, "_boot") and not anim
        if anim:
            boot_cmd.append("--aniz")

        def boot_body(tdir):
            # 2026-11-16 (7f7e7d6c): from reset with the uncached alias as the same memory, and one stock
            # +Drive read of 64 KiB into an unaligned buffer at power-on (emu_boot_check.bounce_read), from a
            # card whose sectors there read 0xff (erased flash: a Line-F word wherever it lands)
            card = work / "bounce_card.img"
            if not card.exists():
                with open(card, "wb") as f:
                    f.seek(BOUNCE_SECTOR * 512)
                    f.write(b"\xff" * BOUNCE_BYTES)
            rc, out = run("boot_check", boot_cmd, logs, env={"DNFW_CODEGUARD": "1", "DNFW_CARD_IMAGE": str(card),   # remoteui-6
                                                             "DNFW_BOOT_BOUNCE": f"{BOUNCE_SECTOR:#x}:{BOUNCE_BYTES:#x}:{BOUNCE_BUF:#x}"},
                          trace=tdir)
            good = rc == 0 and "booted and drew its UI" in out
            if anim:
                good = good and ", 0 not his" in out
            return good, ("booted and drew its UI, no fault" + ("; the start-up animation's first frame, "
                          "his" if anim else "; a NOBOOT image (stock's intro): no animation" if noboot else "")
                          if good else out[-800:])
        later("boot", "boot from reset", "boot from reset", [boot_cmd], boot_body)

        # 5a. 2026-11-21 (docs/safe-mode.md): SAFE MODE from reset (scripts/emu_safeboot.py): a, the normal boot's record;
        # b, a pending record -> the SAFE mark and a reset, then the SAFE boot: MAIN OS stock 1.12 after the loader, no
        # other init, no DSP program, no +Drive write, the UI; f (in b), the empty project: no working-project read, no
        # MRAM write; e, hostile marks and records; n, the NORMAL-ONCE and STOP marks; t, the mark lost: the cap. Then the
        # question (O2) on stock 1.12's UI snapshot (scripts/emu_safemode_question.py: from reset the UI loop is never
        # reached): it opens by itself, YES stays, NO leaves the NORMAL-ONCE mark and resets. The STOP entry on the build
        # installed over that snapshot (scripts/emu_safemode_stop.py): STOP alone held 1 s enters; a STOP tap, a hold under 1 s, FUNC + STOP and no key do not (2026-11-21).
        # The update RPC in SAFE MODE's state (scripts/emu_safemode_rpc.py, part c): Ping, SoftwareVersion,
        # OsUpgradeStart and four OsUpgradeWrite chunks through the USB MIDI receive path, each accepted
        # (The step's title stays as it is: it is also the EMU entry's, and the two must match.)
        sb_cmd = [a.venv, "-u", "scripts/emu_safeboot.py", a.stock, a.build, "--parts", "a,b,e,n,t,m"]
        sq_cmd = [a.venv, "-u", "scripts/emu_safemode_question.py", a.build, "--png-dir", work / "safemode-question"]
        ss_cmd = [a.venv, "-u", "scripts/emu_safemode_stop.py", a.build]
        sr_cmd = [a.venv, "-u", "scripts/emu_safemode_rpc.py", a.build, "--chunks", "4", "--sender-returns"]
        sq_env = {"DT2_MAIN_IMG": str(pathlib.Path(os.environ["DT2_SECTIONS"]) / "section_3_MAIN_OS.bin"),
                  "DNFW_EMU_FLAGS": '{"weakptr": false}'}

        def safeboot_body(tdir):
            rc, out = run("safeboot", sb_cmd, logs, trace=tdir)
            good = rc == 0 and out.strip().splitlines()[-1].startswith("PASS")
            if not good:
                return False, out[-800:]
            for name, cmd in (("safeboot-question", sq_cmd), ("safeboot-stop", ss_cmd), ("safeboot-rpc", sr_cmd)):
                rc, out = run(name, cmd, logs, env=sq_env, trace=tdir)
                if not (rc == 0 and out.strip().splitlines()[-1].startswith("PASS")):
                    return False, f"{name}: " + out[-800:]
            return True, ("the record at boot; SAFE MODE as stock 1.12 after the loader, nothing of ours run, no DSP "
                          "program, no +Drive write, an empty project; hostile input normal; two resets at most; the "
                          "question opens, YES stays, NO restarts normally; STOP alone enters; the update RPC answers")
        later("safeboot", "SAFE MODE from reset: the record, the SAFE boot as stock 1.12, hostile input, the reset cap; "
              "the question (ColdFire)", "safeboot", [sb_cmd, sq_cmd, ss_cmd, sr_cmd, sorted(sq_env.items())],
              safeboot_body)

        # 5b. v0.37: the start-up animation, every frame. From reset the intro stops after its
        # first frame under the emulator (stock too), so from the snapshot taken just before
        # it, with this build's intro hook and appended area installed as its loader would:
        # every frame (v0.39: s!Rwa²'s own 38), each bit for bit his, in order, to the intro's last frame
        if anim:
            from dnfw import bootanim as BA      # noqa: PLC0415
            n_anim = len(BA.DURATIONS_MS)
            aniz_cmd = [a.venv, "-u", "scripts/emu_aniz_check.py", a.build]

            def aniz_body(tdir):
                rc, out = run("aniz_check", aniz_cmd, logs, trace=tdir)
                good = (rc == 0 and "in order: PASS" in out and f"{n_anim} of {n_anim} distinct, 0 not his" in out
                        and ", 0 wrong; the label" in out and f"over frame(s) [{n_anim - 1}]" in out)
                return good, (f"all {n_anim} frames, each his, in order, to the intro's end; the panel showed "
                              f"each, the version label over the last only" if good else out[-800:])
            later("aniz", "start-up animation, every frame", "start-up animation", [aniz_cmd], aniz_body)
        elif noboot:                             # (the step stays in the list: it says why nothing ran)
            later("aniz", "start-up animation, every frame", "start-up animation", [],
                  lambda tdir: (True, "a NOBOOT image: its intro is stock's (no jump to the stamp), no animation to check"))

        # 5c. v0.65 (docs/packer.md): the sections the build changes are packed by the optimal
        # parse (codec.aplibopt); the instrument's own aPLib depacker (the bootstrap's 0x80000432,
        # from stock's untouched section 2, run in digikit's Unicorn machine) must give back
        # exactly what ours does for each, and a stream with one byte flipped must not
        depack_cmd = [a.venv, "-u", "scripts/emu_depack_check.py", a.stock, a.build]

        def depack_body(tdir):
            rc, out = run("depack_check", depack_cmd, logs, trace=tdir)
            good = rc == 0 and out.strip().endswith("DEPACK PASS") and "does not give its content back" in out
            secs = [ln.split(":")[0] for ln in out.splitlines() if "identical to ours" in ln]
            return good, (f"{', '.join(secs)}: the instrument's depacker gives exactly our bytes; a flipped "
                          "byte does not" if good else out[-800:])
        later("depack", "the instrument's own depacker on every repacked section", "repacked sections",
              [depack_cmd], depack_body)

        # 6. engine + LOAD/SAVE
        # PERC (5), the Monomachine's (6, 7, v0.26: 14..) and the sample machines (8..13,
        # v0.13; 13 SLICE, v0.19) are kept by LOAD; the first type past ours still loads as
        # FM Tone
        from dnfw.waverider import coldfire as _cf
        last = _cf.TYPES_LAST
        mtypes = sorted({5, 6, 7, 8, 12, 13, *range(14, last + 1), last + 1})
        types = ["--machine-type", "3"] + ([x for t in mtypes for x in ("--machine-type", str(t))]
                                           + ["--machine-max", str(last)]
                                           if dsp_changed else [])
        # v0.27: SHFT (7) and GRAN (8) removed: 7 and 8 load as Multi-Mode now; v0.45: PING (6)
        # removed too, so the LOAD bound is stock again and every type above 5 loads as Multi-Mode.
        # 2026-11-11: the A2 filter machines (dnfw.engines.analog2.filters, 2026-11-10) raise the bound again on purpose
        # (a2f.coldfire LOAD_BOUND: -1..the last built type kept): each built type must come back as
        # itself, the first type past them as Multi-Mode; 6 (PING's, not built) is inside the bound
        # and LOAD turns it into Multi-Mode (a2f.coldfire flt_load, the User's choice)
        from dnfw.engines.analog2.filters import coldfire as _fc
        fmax = _fc.NEW_FILTERS[-1] if _fc.NEW_FILTERS else 5
        ftypes = sorted({6, 7, 8, *_fc.NEW_FILTERS, fmax + 1})
        types += ["--filter-type", "2"] + ([x for t in ftypes for x in ("--filter-type", str(t))]
                                           + ["--filter-max", str(fmax)]
                                           + [x for t in range(6, fmax) if t not in _fc.NEW_FILTERS
                                              for x in ("--filter-reset", str(t))]
                                           if dsp_changed else [])
        if "fx_get" in W.SPEC.get("layout", {}):   # v0.51: FLEX REC's settings in the sound, through SAVE/LOAD
            types += ["--fx-roundtrip"]
        eng_cmd = [a.venv, "-u", "scripts/emu_boot_engine.py", "--build", bdir, "--frames", "8", *types]

        def eng_body(tdir):
            rc, out = run("boot_engine", eng_cmd, logs, trace=tdir)
            clean = rc == 0 and "ran clean" in out and "FAIL" not in out and "corrupt" not in out
            return clean, ("evaluator clean, CODE intact, machine and filter types round-trip"
                           if clean else out[-800:])
        later("engine", "engine + LOAD/SAVE", "engine + LOAD/SAVE", [eng_cmd], eng_body)

        # 6b. the sample link on the ColdFire (v0.16): the +Drive's image loaded over the
        # fast link with a packet lost (resent), the loader stopping when nothing gets
        # through (v0.20: the frame's words are never written), and a recording read back
        # and saved -- each against a Python DSP and +Drive
        # (scripts/emu_waverider_menu.py's link16 step)
        from dnfw.mods import waverider as W        # noqa: PLC0415
        lay = W.SPEC.get("layout", {})
        snap = ROOT.parent / "digikit/out/snapshots/dn2-1.11/ui800M-v014.snap"
        EMU_ENV = {"DT2_MAIN_IMG": str(pathlib.Path(os.environ["DT2_SECTIONS"]) / "section_3_MAIN_OS.bin"),
                   "DNFW_EMU_FLAGS": '{"weakptr": false}',
                   "DNFW_LOWTRAP": "1",   # v0.46: every emulator step traps wild reads (emulib/lowtrap.py)
                   "DNFW_CODEGUARD": "1"}   # remoteui-6: ... and writes into the C chunk's code (emulib/codeguard.py)
        if "smp_tdm_sent" in lay:
            syms = work / "link16_syms.json"
            syms.write_text(json.dumps({k: v for k, v in lay.items() if k.startswith("smp_")}))
            # (2026-11-19: late, late_lowram: a DSP that comes up 1,500 periods after the ColdFire, as on the unit)
            scen = (("save", "fast", "dead", "high", "lowram", "late", "late_lowram") if "smp_ram" in lay
                    else ("save", "fast", "dead"))
            if "smp_slices_set" in lay:
                scen += ("slices",)             # v0.23: the slice editor's reading and saving
            if "smp_lib_state" in lay:
                scen += ("lib",)                # v0.31: the +Drive's library, bounded to its region
            if "smp_heads" in lay:
                scen += ("live",)               # v0.38: 22 live adds and 3 recordings, each must play
                scen += ("bulk",)               # LOAD TO PROJECT of 40 at once: all queued, loaded, played
                scen += ("pvlat",)              # +DRIVE preview: periods to playback, short/long/second, bytes exact
            if "smp_lib_fpar" in lay:
                scen += ("nest",)               # v0.40: folders inside folders over the link, power cuts
            if "smp_rs_done" in lay:
                scen += ("recstore",)           # v0.46: a recording into +DRIVE > RECORDED: exact, power cuts, no room
            if "smp_saved" in lay:
                scen += ("norm",)              # v0.41: takes normalised to full scale (last: it leaves takes in the pool)
            # v0.31: "dead" (every packet lost: the RAM check's four seconds, then seven tries
            # three seconds apart before the loader stops) takes about an hour in the emulator
            # on its own, so it is a step of its own, cached on its own: the gate's run fits
            # the two-hour limit, and a run cut off there keeps whichever step passed
            dead = [sc for sc in scen if sc == "dead"]
            scen = tuple(sc for sc in scen if sc != "dead")
            steps = ",".join(f"link16:{syms}:{sc}" for sc in scen)
            l16_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT,
                       "--build", bdir, "--snapshot", snap, "--steps", steps,
                       "--png-dir", work / "link16"]
            if dead:
                ld_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT,
                          "--build", bdir, "--snapshot", snap, "--steps", f"link16:{syms}:dead",
                          "--png-dir", work / "link16dead"]

                def ld_body(tdir):
                    rc, out = run("link16 dead", ld_cmd, logs, env=EMU_ENV, trace=tdir)
                    oks = re.findall(r"link16 dead: .*\"ok\": (true|false)", out)
                    good = rc == 0 and oks == ["true"]
                    return good, ("dead (nothing gets through): the RAM check gives up after four seconds, "
                                  "the loader tries each chunk seven times and stops, nothing reaches the "
                                  "DSP's routing" if good else out[-800:])
                later("link16-dead", "sample link, dead link (ColdFire)", "sample link, dead link (ColdFire)", [ld_cmd, sorted(EMU_ENV.items())], ld_body)

            def l16_body(tdir):
                rc, out = run("link16", l16_cmd, logs, env=EMU_ENV, trace=tdir)
                oks = re.findall(r"link16 (save|fast|dead|high|lowram|late|late_lowram|slices|lib|live|bulk|pvlat|nest|recstore|norm): .*\"ok\": (true|false)", out)
                good = rc == 0 and len(oks) == len(scen) and all(v == "true" for _, v in oks)
                return good, ("save, fast (a lost packet resent); every byte loaded and saved; the frame's routing words stock's in "
                              "every period; v0.22: the RAM check first, past 128 MB loaded only when it "
                              "passes (high, lowram)"
                              + ("; the RAM check sent once the DSP runs, sent again when lost, its verdict after a "
                                 "DSP 1,500 periods late (late, late_lowram)" if "late" in scen else "")
                              + "; v0.31: the kit's samples first; the +Drive's library written, read back, "
                              "a hole reused, every write inside its region, a small device refused (lib); v0.38: 22 samples "
                              "added live and 3 recordings, one after another, each plays on the DSP by its own rule "
                              "(the count covers it), a recording while it records too (live)"
                              + ("; LOAD TO PROJECT of 40 at once: every one queued, loaded and played (bulk)" if "bulk" in scen else "")
                              + ("; v0.40: folders inside folders: an old flat library read as it was, a path's "
                                 "levels made once, look-alikes apart, six deep at most, DROP refused with a folder "
                                 "inside, one sector a change, a power cut after every sector of making and of a "
                                 "DELETE leaves a sound tree, a v0.39 reads every name (nest)" if "nest" in scen else "")
                              + ("; v0.46: a recording into +DRIVE > RECORDED: its trimmed frames exact, in RECORDED under "
                                 "its name, the slot marked as that sample, a power cut after any pass leaves no entry or "
                                 "all of it, a slot changed mid-copy stops it, no room writes nothing (recstore)"
                                 if "recstore" in scen else "")
                              + ("; v0.41: takes at 4,000, 32,000 and 10 (-70 dBFS) normalised to full scale, every frame "
                                 "exact, none clipped; an all-zero take stays zero (norm)" if "norm" in scen else "")
                              if good else out[-800:])
            later("link16", "sample link (ColdFire)", "sample link (ColdFire)", [l16_cmd, sorted(EMU_ENV.items())], l16_body)

            # 6p. v0.38: per-project sample pools (csrc/sampler/pools.c, docs/project-pools.md;
            # scripts/emu_pools.py): the OS's own LOAD, NEW and SAVE AS through the build's
            # detours; each project its own slots, the legacy pool for old projects, the lists
            # across a power cycle, corrupted lists and changed frames falling back safely, a
            # power cut after every sector of a change and of a switch, every write inside its
            # region, the image one v0.37 reads; the DSP's directory checked every period:
            # never another project's sample, never one half sent
            if "smp_pl_on" in lay:
                pl_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT,
                          "--build", bdir, "--snapshot", snap, "--steps", f"link16:{syms}:pools",
                          "--png-dir", work / "pools"]

                def pl_body(tdir):
                    rc, out = run("pools", pl_cmd, logs, env=EMU_ENV, trace=tdir)
                    res = work / "pools" / "link16_pools.json"
                    why, good = out[-800:], False
                    if rc == 0 and res.exists():
                        r = json.loads(res.read_text())
                        facts = r.get("facts", {})
                        good = bool(r.get("ok")) and len(facts) >= 16 and all(facts.values())
                        why = json.dumps({k: v for k, v in facts.items() if not v})[:800] or out[-800:]
                    return good, ("per-project pools: LOAD / NEW / SAVE AS through the OS's own code, each project "
                                  "its own slots, old projects today's pool, lists kept across a power cycle, a corrupted "
                                  "list its previous copy, changed frames silent, a power cut after every sector safe, "
                                  "every write in its region, the DSP never another project's sample" if good else why)
                later("pools", "per-project pools (ColdFire)", "per-project pools (ColdFire)",
                      [pl_cmd, sorted(EMU_ENV.items())], pl_body)

            # 6q. v0.65 (docs/banks.md; scripts/emu_banks.py): banks B..D's pages loaded with the image
            # and played by the DSP's own rule; the list's rows through the banks; an edit and a
            # LOAD TO PROJECT into bank B on the +Drive, the DSP and the header; a power cycle.
            # Controls: the header's word for B wrong (B empty), an old recording where the pages go
            # (banks off, nothing written or sent there)
            if "smp_bank_live" in lay:
                bk_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT,
                          "--build", bdir, "--snapshot", snap, "--steps", f"link16:{syms}:banks",
                          "--png-dir", work / "banks"]

                def bk_body(tdir):
                    rc, out = run("banks", bk_cmd, logs, env=EMU_ENV, trace=tdir)
                    res = work / "banks" / "link16_banks.json"
                    why, good = out[-800:], False
                    if rc == 0 and res.exists():
                        r = json.loads(res.read_text())
                        facts = r.get("facts", {})
                        good = bool(r.get("ok")) and len(facts) == 10 and all(facts.values())
                        why = json.dumps({k: v for k, v in facts.items() if not v})[:800] or out[-800:]
                    return good, ("banks B..D: B005 plays from B's page, A005 does not, C and D empty; rows "
                                  "A127 > B001; an edit and a LOAD TO PROJECT into bank B on the +Drive, the DSP "
                                  "and the header; a power cycle; controls: a wrong header word (B empty), a "
                                  "recording where the pages go (off, nothing written)" if good else why)
                later("banks", "PROJECT RAM banks B..D: loaded, played, edited, LOAD TO PROJECT, controls (ColdFire)",
                      "PROJECT RAM banks (ColdFire)", [bk_cmd, sorted(EMU_ENV.items())], bk_body)

            # 6e. v0.39: ERASE MOD DATA (csrc/sampler/erase.c, docs/erase-mod-data.md;
            # scripts/emu_erase.py): the key path (+DRIVE, RIGHT, two questions; NO at either and
            # LEFT erase nothing), link command 28 (a wrong word refused), on a Python +Drive that
            # logs every eMMC command: TRIM only inside the four regions, covering each exactly,
            # headers first, never a write from the first TRIM on; the stock store, the factory
            # buffer and the gaps byte-identical; every region's sector read back erased (0x00
            # and 0xFF cards); a card that keeps a sector and a TRIM error fail at their sector;
            # a power-on after a cut at seven points boots with the pool empty, writing only in
            # its regions, and after the whole erase exactly as on a +Drive never written
            if "smp_er_state" in lay:
                er_js = work / "erase.json"
                er_cmd = [a.venv, "-u", "scripts/emu_erase.py", "--build", bdir, "--snapshot", snap,
                          "--scenario", "all", "--json", er_js, "--png-dir", work / "erase"]

                def er_body(tdir):
                    rc, out = run("erase", er_cmd, logs, env=EMU_ENV, trace=tdir)
                    why, good = out[-800:], False
                    if rc == 0 and er_js.exists():
                        r = json.loads(er_js.read_text())
                        checks = r.get("checks", {})
                        good = bool(r.get("ok")) and len(checks) >= 35 and all(c["ok"] for c in checks.values())
                        why = json.dumps({k: c for k, c in checks.items() if not c["ok"]})[:800] or out[-800:]
                        if good:
                            c = r["commands"]
                            why = (f"ERASE MOD DATA: NO at each question and LEFT erase nothing; three YES: "
                                   f"{c['trims']} TRIM calls (CMD35/36/38), only in the mod's regions (the inserts' records with them, 2026-11-11) and "
                                   f"covering them exactly, headers first, no write after the first; stock areas "
                                   f"and gaps byte-identical, every region erased and verified ({r['reads']} reads); "
                                   f"link 28 likewise (0xFF card); a kept sector and a TRIM error fail at their "
                                   f"sector; {len(r['boot'])} power-ons after cuts boot empty, the whole erase as a "
                                   f"fresh install; {len(checks)} checks")
                    return good, why
                later("erase", "ERASE MOD DATA (ColdFire)", "ERASE MOD DATA (ColdFire)",
                      [er_cmd, sorted(EMU_ENV.items())], er_body)

        # 6w. 2026-11-11: the wishes record (csrc/wishes, docs/wishes-record.md; scripts/emu_wishes.py)
        if "wish_load_stub" in lay:
            wi_js = work / "wishes.json"
            wi_cmd = [a.venv, "-u", "scripts/emu_wishes.py", "--build", bdir, "--snapshot", snap, "--json", wi_js]

            def wi_body(tdir):
                rc, out = run("wishes", wi_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and wi_js.exists():
                    r = json.loads(wi_js.read_text())
                    checks = r.get("checks", {})
                    good = bool(r.get("ok")) and len(checks) >= 20 and all(c["ok"] for c in checks.values())
                    why = json.dumps({k: c for k, c in checks.items() if not c["ok"]})[:800] or out[-800:]
                    if good:
                        why = (f"stock's SAVE/LOAD/memcpy/memset through the hooks: lane-only difference, link and "
                               f"cell as the host reference, copy/carry/drop, a cell written and one read; "
                               f"{len(checks)} checks; cost {r.get('cost')}")[:800]
                return good, why
            later("wishes", "the wishes record through stock's SAVE, LOAD, memcpy, memset (ColdFire)",
                  "the wishes record through stock's SAVE, LOAD, memcpy, memset (ColdFire)",
                  [wi_cmd, sorted(EMU_ENV.items())], wi_body)

        # 6w2. 2026-11-12: the wishes record on kits, patterns, songs and the project settings (csrc/wishes/item.c,
        # items.S; scripts/emu_wishes_items.py)
        if "wish_item" in lay:                  # (its stubs are in c_text_symbols, not the layout: 2026-11-12)
            wt_js = work / "wishitems.json"
            wt_cmd = [a.venv, "-u", "scripts/emu_wishes_items.py", "--build", bdir, "--snapshot", snap, "--json", wt_js]

            def wt_body(tdir):
                rc, out = run("wishitems", wt_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and wt_js.exists():
                    r = json.loads(wt_js.read_text())
                    checks = r.get("checks", {})
                    good = bool(r.get("ok")) and len(checks) >= 40 and all(c["ok"] for c in checks.values())
                    why = json.dumps({k: c for k, c in checks.items() if not c["ok"]})[:800] or out[-800:]
                    if good:
                        why = (f"kit, pattern, song, project settings: stock's SAVE/LOAD through the hooks, link-only "
                               f"difference, link and cell as the host reference, copy/clear carry and drop; "
                               f"{len(checks)} checks")[:800]
                return good, why
            later("wishitems", "the wishes record on kits, patterns, songs and the project settings (ColdFire)",
                  "the wishes record on kits, patterns, songs and the project settings (ColdFire)",
                  [wt_cmd, sorted(EMU_ENV.items())], wt_body)

        # 6x. 2026-11-12: the matrix's routes (csrc/matrix, docs/matrix.md; scripts/emu_matrix.py): every voice row's
        # route of ours heard frame by frame as stock's route 1 at the same depth (one a row, then three into one
        # slot), and the frame's cost the same with no route and with every route, under its bound
        if "mx_eval" in lay:
            mx_js = work / "matrix.json"
            mx_cmd = [a.venv, "-u", "scripts/emu_matrix.py", "--build", a.build, "--snapshot", snap, "--json", mx_js]

            def mx_body(tdir):
                rc, out = run("matrix", mx_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                r = json.loads(mx_js.read_text()) if mx_js.exists() else {}
                return True, (f"{last[6:]}: every row's route heard as stock's route 1 every frame "
                              f"({r.get('exact', {}).get('one_route')}), three into one slot too; cost "
                              f"{r.get('cost')}")[:800]
            later("matrix", "the matrix's routes heard as stock's route 1, at a constant cost (ColdFire)",
                  "the matrix's routes heard as stock's route 1, at a constant cost (ColdFire)",
                  [mx_cmd, sorted(EMU_ENV.items())], mx_body)

        # 2026-11-18: the DEST popup (csrc/matrix/dest_pop.c, routes.c; scripts/emu_destpop.py): stock's DEST value check
        # answered as stock's for every slot with no list built; D's push opens the popup, never stock's list; an LFO's
        # routes edited, muted, deleted (the first route in DEST and DEP, the next one taking its place); LFO controls
        # and LFO4 one route; the pool's 16; a muted first route heard as DEST none, on its track's voices only
        if "ldp_valid" in lay:
            dp_js = work / "destpop.json"
            dp_cmd = [a.venv, "-u", "scripts/emu_destpop.py", "--build", a.build, "--snapshot", snap, "--json", dp_js]

            def dp_body(tdir):
                rc, out = run("destpop", dp_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                r = json.loads(dp_js.read_text()) if dp_js.exists() else {}
                return True, (f"DEST check as stock's ({r.get('valid')}); the popup opened, edited, muted, deleted; "
                              f"a muted first route heard as DEST none ({r.get('frame')}); open {r.get('open')}")[:800]
            later("destpop", "the DEST popup: an LFO's routes, first route in DEST/DEP, mute and delete; stock's DEST check "
                  "unchanged (ColdFire)", "the DEST popup: an LFO's routes, first route in DEST/DEP, mute and delete; "
                  "stock's DEST check unchanged (ColdFire)", [dp_cmd, sorted(EMU_ENV.items())], dp_body)

        # 2026-11-21: the routes popup's MOD SETUP rows (csrc/matrix/setup.c, setup.S; scripts/emu_setuprows.py): stock's
        # entries edited through stock's own MOD SETUP objects (a turn, YES at +32 in the first free place, FULL at 4, a
        # long NO frees the place, two entries merged, FUNC + NO), NOT IN SETUP as stock's list, a muted entry heard as
        # that entry at depth 0 with the sound unchanged (both of stock's copies into the voices)
        if "mxs_copy" in lay:
            sr_js = work / "setuprows.json"
            sr_cmd = [a.venv, "-u", "scripts/emu_setuprows.py", "--build", a.build, "--snapshot", snap, "--json", sr_js]

            def sr_body(tdir):
                rc, out = run("setuprows", sr_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                return True, "MOD SETUP's rows edited through stock's objects; NOT IN SETUP as stock's list; a muted entry heard as depth 0"
            later("setuprows", "the routes popup's MOD SETUP rows: stock's entries edited through stock's objects, mute heard as 0 "
                  "(ColdFire)", "the routes popup's MOD SETUP rows: stock's entries edited through stock's objects, mute heard "
                  "as 0 (ColdFire)", [sr_cmd, sorted(EMU_ENV.items())], sr_body)

        # 2026-11-19: PARA on the VOICE key's LED (csrc/para/led.c, docs/leds.md; scripts/emu_voiceled.py):
        # stock's compose on the build's own snapshot, the panel UART's bytes recorded: WaveTone and ANALOG 2 PARA OFF as
        # stock's (against stock's bytes put back at the site), PARA ON magenta (2, 91) `b9 07 5b`, the VOICE menu's
        # white kept, VOICE claimed above left alone, the refresh through the UI loop on a PARA, machine or track change
        if "pu_led_marks" in lay:
            vl_js = work / "voiceled.json"
            vl_cmd = [a.venv, "-u", "scripts/emu_voiceled.py", "--build", a.build, "--snapshot", snap,
                      "--json", vl_js, "--png-dir", work / "voiceled"]

            def vl_body(tdir):
                rc, out = run("voiceled", vl_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                r = json.loads(vl_js.read_text()) if vl_js.exists() else {}
                return True, (f"stock's VOICE LED on stock's tracks, magenta on PARA ON ({r.get('on')}), the VOICE "
                              f"menu's white, refreshes {r.get('marks')}")[:800]
            later("voiceled", "PARA on the VOICE key's LED: magenta on a PARA ON track, stock's teal/backlight/white "
                  "elsewhere, refreshed on a change (ColdFire)", "PARA on the VOICE key's LED: magenta on a PARA ON "
                  "track, stock's teal/backlight/white elsewhere, refreshed on a change (ColdFire)",
                  [vl_cmd, sorted(EMU_ENV.items())], vl_body)

        # 2026-11-19: knob notches (csrc/knobs, scripts/emu_knobnotch.py, docs/knob-notch.md): a knob-driven write of a
        # bipolar value (stock's sound and kit setters, p-locks, our popups, ENV2's H) that crosses its 0 lands on it and
        # is held KN_HOLD counts; fast turns pass; CC, NRPN and Overbridge writes (no knob item, or another task) exact;
        # unipolar values exactly as stock writes them; the popups' slow turns 1 unit every KN_POP_DIV counts
        if "kn_value" in lay:
            kn_js = work / "knobnotch.json"
            kn_cmd = [a.venv, "-u", "scripts/emu_knobnotch.py", "--build", a.build, "--snapshot", snap, "--json", kn_js]

            def kn_body(tdir):
                rc, out = run("knobnotch", kn_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                r = json.loads(kn_js.read_text()) if kn_js.exists() else {}
                return True, (f"notches caught, held and passed as knob.h says ({r.get('constants')}); CC/NRPN/Overbridge "
                              f"writes exact ({r.get('outside')}); unipolar as stock ({r.get('unipolar')})")[:800]
            later("knobnotch", "knob notches on bipolar values (CC, NRPN, Overbridge exact; unipolar as stock), our popups' "
                  "slow turns (ColdFire)", "knob notches on bipolar values (CC, NRPN, Overbridge exact; unipolar as "
                  "stock), our popups' slow turns (ColdFire)", [kn_cmd, sorted(EMU_ENV.items())], kn_body)

        # 2026-11-15: ANALOG 2's PARA on the VOICE menu's knob B (csrc/para, docs/paraphonic.md;
        # scripts/emu_para_vmenu.py): on a stock machine's track the menu as stock's after turns of B and C; on an
        # ANALOG 2 track only B's label row differs (PARA OFF), and B steps PARA 2 3 4 (capped) and back to OFF
        if "vm_sets" in lay:
            pv_js = work / "para_vmenu.json"
            pv_cmd = [a.venv, "-u", "scripts/emu_para_vmenu.py", "--build", a.build, "--snapshot", snap,
                      "--json", pv_js, "--png-dir", work / "para_vmenu"]

            def pv_body(tdir):
                rc, out = run("paravmenu", pv_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                r = json.loads(pv_js.read_text()) if pv_js.exists() else {}
                return True, (f"stock's places untouched, B right {r.get('right')}, left {r.get('left')}, "
                              f"vm_sets {r.get('vm_sets')}")[:800]
            later("paravmenu", "PARA on the VOICE menu's B: stock's places as stock's, B OFF / ON on ANALOG 2 and JUNO (ColdFire)",
                  "PARA on the VOICE menu's B: stock's places as stock's, B OFF / ON on ANALOG 2 and JUNO (ColdFire)",
                  [pv_cmd, sorted(EMU_ENV.items())], pv_body)

            # 2026-11-12: ENV1/ENV2 (the User: ENV1 is stock's AMP envelope, ENV2 its clone): the clone's model against
            # stock's own envelope in Elektron's DSP code, block by block (scripts/sharc_matrix_env.py --quick); the
            # target's C against the model is the matrix step's env scenario
            ec_js = work / "envclone.json"
            ec_cmd = [a.venv, "-u", "scripts/sharc_matrix_env.py", "--image", a.stock, "--digikit", a.digikit_sharc,
                      "--quick", "--json", ec_js]

            def ec_body(tdir):
                rc, out = run("envclone", ec_cmd, logs, env={"PYTHONPATH": str(ROOT / "src")}, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                return True, last[6:][:800]
            later("envclone", "ENV1/ENV2's clone against stock's own AMP envelope (SHARC runner)",
                  "ENV1/ENV2's clone against stock's own AMP envelope (SHARC runner)",
                  [ec_cmd, sorted(EMU_ENV.items())], ec_body)

            # 2026-11-20 (the User): AMP ON/OFF's bypass in Elektron's DSP code (scripts/sharc_ampsw_step.py, the
            # tree's DSP image, which dsp-identity ties to the build): a drum slot OFF leaves VOL's loop bit for bit as
            # it reached the AMP stage; ON, the other slots and a word without the magic as stock's (stockout's
            # declaration, scripts/sharc_stockout_step.py)
            ad_js = work / "ampdsp.json"
            ad_cmd = [a.venv, "-u", "scripts/sharc_ampsw_step.py", "--image", a.stock, "--digikit", a.digikit_sharc,
                      "--json", ad_js]

            def ad_body(tdir):
                rc, out = run("ampdsp", ad_cmd, logs, env={"PYTHONPATH": str(ROOT / "src")}, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                return True, last[6:][:800]
            later("ampdsp", "AMP ON/OFF: OFF unity bit for bit, ON and every other slot stock's (SHARC runner)",
                  "AMP ON/OFF in Elektron's DSP code (SHARC runner)", [ad_cmd, sorted(EMU_ENV.items())], ad_body)

        # 6c. the RECORDER screen (v0.22): FUNC+VOICE opens it over any page, its knobs
        # change the recorder and never the track's sound, NO closes it, and the UI keeps
        # drawing throughout (scripts/emu_waverider_menu.py, keys and knob as the panel)
        if "rec_overlay" in lay:
            ov, src = hex(lay["rec_overlay"]), hex(lay["rec_src"])
            # v0.59: then C (MON) on and off, each time the next command's channel word read
            mon, sch = hex(lay["rec_mon"]), hex(lay["rec_sent_chan"])
            # (2026-11-13, the 1.12 gate's blind spots: 1.12 redraws later in the emulator; the stock page came back
            # 60..300 M instructions after NO on clean 1.12, so the waits are longer: the checks are the same)
            # The first screen is taken once the first frame is composed, at most 40 M after the
            # resume (it was a fixed 25 M, which the first frame reached within 0.5 M on some builds)
            steps = (f"firstframe:40,png:p0,mem:{ov}:4,press:17,wait:3,tap:49,wait:3,release:17,"
                     f"wait:60,mem:{ov}:4,png:a1,spin:0:3,wait:15,mem:{src}:4,spin:0:9,wait:15,mem:{src}:4,png:a2,"
                     f"spin:2:3,wait:15,mem:{mon}:4,mem:{sch}:4,png:m1,spin:2:-3,wait:15,mem:{mon}:4,mem:{sch}:4,no,"
                     f"wait:300,mem:{ov}:4,png:a3,wait:15,png:a4")
            js = work / "recorder.json"
            rec_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT,
                                       "--build", bdir, "--snapshot", snap, "--steps", steps,
                                       "--png-dir", work / "recorder", "--json", js]

            def rec_body(tdir):
                rc, out = run("recorder", rec_cmd, logs, env=EMU_ENV, trace=tdir)
                why = out[-800:]
                good = False
                if rc == 0 and js.exists():
                    r = json.loads(js.read_text())
                    ff = r.get("first_frame_at")
                    if ff is None:
                        return False, "no frame composed within 40 M instructions of the resume"
                    m = r["memory"]
                    seen = [int(m[k], 16) for k in (ov, f"{ov}@1", f"{ov}@8")]
                    srcs = [int(m[k], 16) for k in (src, f"{src}@3")]     # v0.41: 3 detents, then 9 more
                    mons = [int(m[k], 16) for k in (mon, f"{mon}@6")]      # v0.59: C on, then off
                    chans = [int(m[k], 16) >> 30 & 1 for k in (sch, f"{sch}@7")]   # MON's bit in the next command
                    shots = [pathlib.Path(r["screens"][n]).read_bytes() for n in ("p0", "a2", "a4", "m1")]
                    good = (seen == [0, 1, 0] and srcs == [0, 3] and mons == [1, 0] and chans == [1, 0]
                            and not r["setter_writes"] and r["screen_frames"] > 0
                            and shots[1] != shots[0] and shots[1] != shots[2] and shots[3] != shots[1])
                    why = (f"overlay {seen}, src {srcs}, MON {mons}, its bit sent {chans}, setter writes "
                           f"{len(r['setter_writes'])}, frames {r['screen_frames']}, first frame at {ff / 1e6:.0f} M")
                return good, ("FUNC+VOICE opens it, knob A moves SRC four detents a choice (3: none, 12: three; v0.41) with no write to the sound, "
                 "C turns MON on and off, the next command carrying it (v0.59), NO closes it, "
                 f"the screen drawn throughout (first frame at {ff / 1e6:.0f} M)"
                              if good else why)
            later("recorder", "recorder screen (ColdFire)", "recorder screen (ColdFire)", [rec_cmd, sorted(EMU_ENV.items())], rec_body)

        # 6d. after a recording (v0.22; v0.25 as the DT2's): SAVING/NORMALIZING (phase 4) on to
        # TRIM once saved; TRIM's ends move (E, H); FUNC + YES plays the preview while held
        # (a command each way, FUNC's release seen); YES on to FILE NAME (spelt by knob and
        # arrows; FUNC + YES inserts, FUNC + NO deletes), YES on to ASSIGN, a [TRIG] key
        # makes track 3 ONESHOT playing the slot (stock's MACHINE SEL commit and setValue)
        # v0.40: the preview's playhead (the owner: it never moved): held, the frame counter
        # moved on 150 twice (6,400 audio frames, as the audio interrupt would count them), the column drawn moves right each time and the
        # screen with it; let go, none (trim_head_x -1, the screen changed again)
        if "rec_phase" in lay and "rec_pv_on" in lay:
            g = {k: hex(lay.get(k, 0)) for k in ("rec_overlay", "rec_phase", "trim_slot", "trim_n", "trim_s",
                                                  "trim_e", "nm_text", "rec_pv_on", "smp_func_held", "smp_cmds",
                                                  "smp_saved", "trim_head_x", "sn_opens", "sn_results")}
            kit = 0x4210D08C                    # the snapshot's live kit ([0x800052a0])
            snd = hex(kit + 52 + 1163 * 2)      # track 3's sound
            steps = (f"wait:3,mem:0x800052a0:4,mem:{snd}:256,poke:{g['trim_slot']}:00000004,"
                     f"poke:{g['trim_n']}:00017700,poke:{g['trim_s']}:00000000,poke:{g['trim_e']}:00017700,"
                     f"poke:{g['smp_saved']}:00000000,poke:{g['rec_overlay']}:00000001,"
                     f"poke:{g['rec_phase']}:00000004,wait:10,mem:{g['rec_phase']}:4,"
                     f"poke:{g['smp_saved']}:00000001,wait:10,mem:{g['rec_phase']}:4,png:t1,spin:4:5,wait:5,"
                     f"mem:{g['trim_s']}:4,spin:7:-3,wait:5,mem:{g['trim_e']}:4,png:t2,spin:5:2,wait:5,png:tz,"
                     f"mem:{g['smp_cmds']}:4,"
                     f"press:17,wait:2,press:10,wait:3,mem:{g['rec_pv_on']}:4,mem:{g['smp_cmds']}:4,"
                     f"mem:{g['trim_head_x']}:4,png:p0,addl:0x4058f8d4:150,wait:10,mem:{g['trim_head_x']}:4,png:p1,"
                     f"addl:0x4058f8d4:150,wait:10,mem:{g['trim_head_x']}:4,png:p2,"
                     f"release:10,wait:3,release:17,wait:3,mem:{g['rec_pv_on']}:4,mem:{g['smp_func_held']}:4,"
                     f"mem:{g['smp_cmds']}:4,mem:{g['trim_head_x']}:4,png:pr,yes,wait:10,mem:{g['rec_phase']}:4,png:n0,"
                     # v0.54: FILE NAME is the DN2's own NAME screen (NameView, docs/name-screen.md),
                     # spelt with its own keys: UP gives A, RIGHT, UP twice gives B
                     f"mem:{g['sn_opens']}:4,up,wait:5,right,wait:5,up,wait:5,up,wait:5,"
                     f"png:n1,yes,wait:10,mem:{g['rec_phase']}:4,mem:{g['sn_results']}:4,mem:{g['nm_text']}:8,png:a1,tap:27,"
                     f"wait:20,mem:{g['rec_phase']}:4,mem:{snd}:256,png:r1,mem:{lay['trim_zoom']:#x}:4")
            js = work / "recflow.json"
            flow_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT,
                                            "--build", bdir, "--snapshot", snap, "--steps", steps,
                                            "--png-dir", work / "recflow", "--json", js]

            # the harness keys a repeated read of an address by its place among all reads
            # (emu_waverider_menu.py's mem:): the n-th read of VA, worked out from the steps
            reads = [st.split(":")[1] for st in steps.split(",") if st.startswith("mem:")]

            def nth(va, n):
                k = [i for i, x in enumerate(reads) if x == va][n]
                return va if not n else f"{va}@{k}"

            def flow_body(tdir):
                rc, out = run("recorder flow", flow_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and js.exists():
                    r = json.loads(js.read_text())
                    m = r["memory"]
                    ph, cm, pv = g["rec_phase"], g["smp_cmds"], g["rec_pv_on"]
                    phases = [int(m[nth(ph, k)], 16) for k in range(5)]
                    cmds = [int(m[nth(cm, k)], 16) for k in range(3)]
                    before, after = bytes.fromhex(m[snd]), bytes.fromhex(m[nth(snd, 1)])
                    s0, e0 = int(m[g["trim_s"]], 16), int(m[g["trim_e"]], 16)
                    name = bytes.fromhex(m[g["nm_text"]])[:4]
                    nshot = {k: pathlib.Path(r["screens"][k]).read_bytes() for k in ("pr", "n0", "n1")}
                    hx = g["trim_head_x"]
                    heads = [struct.unpack(">i", bytes.fromhex(m[nth(hx, k)]))[0] for k in range(4)] \
                        if "trim_head_x" in lay else None
                    shot = {k: pathlib.Path(r["screens"][k]).read_bytes() for k in ("p0", "p1", "p2", "pr")}
                    facts = {"kit": m["0x800052a0"] == f"{kit:08x}",
                             "phases (v0.54: FILE NAME is the stock NAME screen, phase 5)": phases == [4, 1, 5, 3, 0],
                             "trim": 0 < s0 < e0 < 0x17700,
                             "preview": int(m[pv], 16) == 1 and int(m[nth(pv, 1)], 16) == 0
                             and cmds[1] == cmds[0] + 1 and cmds[2] == cmds[1] + 1
                             and int(m[g["smp_func_held"]], 16) == 0,
                             "v0.40: the preview's playhead moves with it (held: drawn, further on each "
                             "time, the screen changing) and is gone once let go":
                             heads is not None and 4 <= heads[0] < heads[1] < heads[2] <= 123 and heads[3] == -1
                             and shot["p0"] != shot["p1"] != shot["p2"] != shot["pr"],
                             "v0.54: YES on TRIM opens the stock NAME screen (once), drawn, and its keys spell "
                             "the name (UP, RIGHT, UP UP: AB); its YES names the recording and goes on to ASSIGN":
                             int(m[g["sn_opens"]], 16) == 1 and int(m[g["sn_results"]], 16) == 1
                             and name == b"AB\0\0" and nshot["n0"] != nshot["pr"] and nshot["n1"] != nshot["n0"],
                             "oneshot": before[0xDE] != 8 and after[0xDE] == 8,
                             "samp": after[0x6A] == 5,
                             "frames": r["screen_frames"] > 0,
                             "v0.33: F zooms TRIM (drawn)": int(m[f"{lay['trim_zoom']:#x}"], 16) >= 1
                             and pathlib.Path(r["screens"]["tz"]).read_bytes() != pathlib.Path(r["screens"]["t2"]).read_bytes()}
                    good = all(facts.values())
                    why = str(facts) + f" phases {phases} cmds {cmds} name {name} heads {heads}"
                return good, ("SAVING on to TRIM; TRIM's ends move; FUNC + YES previews while held, its playhead "
                              f"moving (columns {heads[:3]}), gone at release; YES on to "
                              "FILE NAME, the stock NAME screen (spelt AB with its keys), YES on to ASSIGN, "
                              "a [TRIG] key makes track 3 ONESHOT on the slot" if good else why)
            later("recflow", "recorder flow (ColdFire)", "recorder flow (ColdFire)", [flow_cmd, sorted(EMU_ENV.items())], flow_body)

        # 6d2. v0.54: the stock NAME screen (docs/name-screen.md). After TRIM's YES the DN2's
        # own NameView is up (phase 5, opened once, drawn); its NO closes it without a name:
        # the recording keeps the one it has and goes on to ASSIGN (phase 3, no result). The
        # negative control: the same keys with the main screen's view pointer (SN_MAIN_VIEW)
        # cleared, which leaves our own naming screen in use (phase 2, nothing opened): the
        # fallback, and proof the facts above see the stock screen and not ours.
        if "sn_opens" in lay and "rec_phase" in lay:
            g2 = {k: hex(lay[k]) for k in ("rec_overlay", "rec_phase", "trim_slot", "trim_n", "trim_s",
                                           "trim_e", "smp_saved", "sn_opens", "sn_results")}
            pre = (f"wait:3,poke:{g2['trim_slot']}:00000004,poke:{g2['trim_n']}:00017700,"
                   f"poke:{g2['trim_s']}:00000000,poke:{g2['trim_e']}:00017700,poke:{g2['smp_saved']}:00000000,"
                   f"poke:{g2['rec_overlay']}:00000001,poke:{g2['rec_phase']}:00000004,wait:10,"
                   f"poke:{g2['smp_saved']}:00000001,wait:10,png:t0,")
            tail = (f"yes,wait:10,mem:{g2['rec_phase']}:4,mem:{g2['sn_opens']}:4,png:s0,no,wait:10,"
                    f"mem:{g2['rec_phase']}:4,mem:{g2['sn_results']}:4,png:s1")
            sn_runs = {}
            for kind, extra in (("stock", ""), ("control", "poke:0x44648980:00000000,")):
                js_ = work / f"stockname_{kind}.json"
                sn_runs[kind] = (js_, [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT,
                                       "--build", bdir, "--snapshot", snap, "--steps", pre + extra + tail,
                                       "--png-dir", work / f"stockname_{kind}", "--json", js_])

            def sn_body(tdir):
                seen = {}
                for kind, (js_, cmd) in sn_runs.items():
                    rc, out = run(f"stock name {kind}", cmd, logs, env=EMU_ENV, trace=tdir)
                    if rc != 0 or not js_.exists():
                        return False, f"{kind}: " + out[-600:]
                    r = json.loads(js_.read_text())
                    m = r["memory"]
                    ph = g2["rec_phase"]
                    seen[kind] = {"phase_up": int(m[ph], 16), "opens": int(m[g2["sn_opens"]], 16),
                                  "phase_after": int(m[f"{ph}@2"], 16), "results": int(m[g2["sn_results"]], 16),
                                  "drawn": pathlib.Path(r["screens"]["s0"]).read_bytes()
                                  != pathlib.Path(r["screens"]["t0"]).read_bytes(),
                                  "faults": [f for f in r.get("fault_reports", [])]}
                st, ct = seen["stock"], seen["control"]
                facts = {"YES on TRIM: the stock NAME screen up (phase 5), opened once, drawn":
                         st["phase_up"] == 5 and st["opens"] == 1 and st["drawn"],
                         "its NO: closed without a name, on to ASSIGN (phase 3), no result":
                         st["phase_after"] == 3 and st["results"] == 0,
                         "no fault report": not st["faults"] and not ct["faults"],
                         "negative control (no main screen view): our own naming screen (phase 2), "
                         "nothing opened; its NO on to ASSIGN too":
                         ct["phase_up"] == 2 and ct["opens"] == 0 and ct["phase_after"] == 3}
                good = all(facts.values())
                return good, ("the stock NAME screen opens on TRIM's YES and its NO leaves the name, "
                              "on to ASSIGN; with no main view our own screen stands in (control)"
                              if good else f"{facts} {json.dumps({k: {x: y for x, y in v.items() if x != 'faults'} for k, v in seen.items()})}")
            later("stockname", "stock NAME screen: NO, and its fallback (ColdFire)",
                  "stock NAME screen: NO, and its fallback (ColdFire)",
                  [c for _j, c in sn_runs.values()] + [sorted(EMU_ENV.items())], sn_body)

        # 6e. v0.23, SLICE: its menus drawn over the page (the menu, the grid dialog, the
        # editor with a slice table), the editor's keys and knobs moving the picked slice;
        # and in KEYBOARD mode on a SLICE track (SLCE NOTE) each key plays its own note's slice,
        # as the DT2 (v0.48; v0.26..v0.47 ranked the keys' notes): trig 9 C, 10 D, 2 C#
        if "slc_state" in lay:
            import struct as _st                # noqa: PLC0415
            g = {k: hex(lay[k]) for k in ("slc_state", "slc_nfr", "slc_ns", "slc_cur", "slc_sl", "wr_draws")}
            from dnfw.sampler import machines as SMx    # noqa: PLC0415
            hires = hex(SMx.MIRROR + 0x78000)
            pat = bytes((k * 37) % 200 for k in range(1024)).hex()
            tb = _st.pack(">9I", 0, 30000, 0, 36000, 70000, 40000, 72000, 140000, 72000).hex()
            kit = 0x4210D08C
            pk = ",".join(f"poke:{kit + 52 + 1163 * t + 0xDE:#x}:0d,poke:{kit + 52 + 1163 * t + 108:#x}:0000"
                          for t in range(16))
            # v0.42: the menus poked over the SLICE track's page itself (slice.c closes a menu whose
            # page the screen does not draw: NiKo's GRID report), not over the snapshot's page
            steps = (f"wait:2,{pk},tap:2,wait:10,png:p0,poke:{g['slc_state']}:00000001,wait:6,png:m,"
                     f"poke:{g['slc_state']}:00000002,wait:6,png:g,"
                     f"poke:{hires}:{pat},poke:{g['slc_nfr']}:00023280,poke:{g['slc_ns']}:00000003,"
                     f"poke:{g['slc_cur']}:00000000,poke:{g['slc_sl']}:{tb},poke:{g['slc_state']}:00000004,"
                     f"wait:6,png:e1,right,wait:5,spin:4:6,wait:5,png:e2,mem:{g['slc_cur']}:4,"
                     f"mem:{g['slc_sl']}:36,"
                     # v0.26: FUNC + RIGHT splits the picked slice in two, FUNC + LEFT removes it
                     f"press:17,wait:2,right,wait:3,release:17,wait:3,mem:{g['slc_ns']}:4,mem:{g['slc_sl']}:48,"
                     f"press:17,wait:2,left,wait:3,release:17,wait:3,mem:{g['slc_ns']}:4,"
                     # v0.27: FUNC held, E moves the start at its normal step (FUNC + YES's preview between moves)
                     f"mem:{g['slc_cur']}:4,mem:{g['slc_sl']}:36,press:17,wait:2,spin:4:3,wait:5,release:17,wait:3,"
                     f"mem:{g['slc_sl']}:36,"
                     f"no,wait:6,mem:{g['slc_state']}:4,"
                     # v0.33: YES on the SLICE track's page answers (the menu, or NO SAMPLE ON
                     # SAMP) after MACHINE SEL (FUNC + SRC, NO: its keys' releases never reach the
                     # mod, so SRC stayed "held" and every YES went to stock: the owner's dead
                     # SLICE/GRID menus, reproduced) and a FUNC combo on the page (FUNC + LEFT)
                     f"{pk},tap:2,wait:10,func-src,wait:20,no,wait:10,png:y0,press:17,wait:2,left,wait:3,release:17,wait:6,mark:{g['wr_draws']}:4,press:10,until-shown:{g['wr_draws']}:10,png:y1,release:10,wait:6,"
                     f"no,wait:6,tap:18,wait:6,press:33,wait:6,release:33,wait:6,press:34,wait:6,release:34,wait:6,"
                     f"press:26,wait:6,release:26,wait:6")
            js = work / "slice.json"
            slc_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT,
                                          "--build", bdir, "--snapshot", snap, "--steps", steps,
                                          "--regs-at", "0x400576ca", "--frame-clock",
                                          "--png-dir", work / "slice", "--json", js]
            # 2026-11-15: --frame-clock (FRAMES moves as the UI runs; the menu emulator runs no audio ISR, so
            # it stood at 0). Without it the editor's COULD NOT SAVE (the poked editor's slot is slice.c's -1)
            # stayed up for good, and YES's answer here, NO SAMPLE ON SAMP (the SAMP slot is empty on our
            # snapshots), was drawn only by chance (page.c redraws a note only once FRAMES has moved). y1 is
            # taken while YES is held, inside the answer's 1.5 s: `yes` (a 2 M tap, a 10 M settle) outlasted it.
            # 2026-11-20: y1 is taken once the first screen draw after YES's press has gone to the panel (until-shown
            # on wr_draws: a frame sent with the draw counter moved; 0.25 M steps, at most 10 M), not at a fixed
            # +4 M. The UI draws on its own pass cycle (about every 4.25 M here) and the note is up for about
            # 3.75 M, so a fixed sample saw it only by the cycle's phase, which
            # moves with every build's code: from 736e511a (LFO4 off by default) the first draw after the press came
            # at +4.25 M and y1 at +4.0 M saw the page unchanged, though the box was drawn as before (measured: the
            # draw after the press brings it in every build; shifting the press by 0.5 M brought it back in time).
            # The fact now also wants that draw, and the box pixel for pixel as v0.59 drew it (SLICE_NOTE_REF).

            # v0.40 (a user: "sometimes EDIT SLICE POINTS or CREATE SLICE GRID returns CANNOT
            # READ IT"): the menus opened again and again, TR.DET OFF and ON, after CLEAR SLICE
            # GRID and not, while other link work is in flight (the loader, TRIM's read of another
            # slot, LOAD TO PROJECT, a preview, refused chunk reads, a take saving and
            # normalising into the slot, a project switch): each must reach the editor with the
            # slot's waveform and its grid kept; and the editor's LINKED points (the DT2's, knob
            # A): START moves the previous END, END the next START, bounded; UNLINKED as before
            # (emu_waverider_menu.py's link16 scenario slicebusy, the +Drive and DSP played)
            busy_cmd = None
            if "slc_linked" in lay:
                bsyms = work / "slicebusy_syms.json"
                bsyms.write_text(json.dumps({k: v for k, v in lay.items() if k.startswith(("smp_", "slc_")) or k == "wr_draws"}))
                busy_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT,
                            "--build", bdir, "--snapshot", snap, "--steps", f"link16:{bsyms}:slicebusy",
                            "--png-dir", work / "slicebusy"]

            def slc_note_is_ref(png):
                """The screen at PNG is the reference's, pixel for pixel (lit or not, as the glass shows it)."""
                import numpy as np                      # noqa: PLC0415
                from PIL import Image                   # noqa: PLC0415

                def lit(f):
                    return np.array(Image.open(f).convert("L")) > 128
                a_, b_ = lit(png), lit(SLICE_NOTE_REF)
                return a_.shape == b_.shape and bool((a_ == b_).all())

            def slc_body(tdir):
                rc, out = run("slice menus", slc_cmd, logs, env=EMU_ENV, trace=tdir)
                busy_ok, busy_why = True, ""
                if busy_cmd:
                    brc, bout = run("slice busy", busy_cmd, logs, env=EMU_ENV, trace=tdir)
                    busy_ok = brc == 0 and re.findall(r"link16 slicebusy: .*\"ok\": (true|false)", bout) == ["true"]
                    busy_why = "" if busy_ok else " slicebusy: " + bout[-1500:]
                why, good = out[-800:] + busy_why, False
                if rc == 0 and js.exists():
                    r = json.loads(js.read_text())
                    m = r["memory"]
                    shots = {n: pathlib.Path(r["screens"][n]).read_bytes() for n in ("p0", "m", "g", "e1", "e2", "y0", "y1")}
                    table = list(_st.unpack(">9I", bytes.fromhex(m[g["slc_sl"]])))
                    notes = [int(x["D4"], 16) for x in r["regs_at"].get("0x400576ca", [])]
                    split = list(_st.unpack(">12I", bytes.fromhex(m[f"{g['slc_sl']}@3"])))
                    facts = {"drawn": len({shots[n] for n in ("p0", "m", "g", "e1", "e2")}) >= 4,
                             "v0.33: YES after FUNC + LEFT answers on a SLICE page": shots["y0"] != shots["y1"]
                             and [u[3] for u in r.get("until", []) if u[:2] == ["shown", g["wr_draws"]]] == [True]
                             and slc_note_is_ref(r["screens"]["y1"]),
                             "picked": int(m[g["slc_cur"]], 16) == 1,
                             "start moved": table[3] > 36000 and table[:3] == [0, 30000, 0],
                             # slice 2 (start s, end 70000) split at its middle: s..mid, mid..70000
                             "split": int(m[g["slc_ns"]], 16) == 4 and split[3] == table[3]
                             and split[6] == split[3] + (70000 - split[3]) // 2 == split[4]
                             and split[7] == 70000
                             and split[9:12] == [72000, 140000, 72000],   # slice 3, as it was
                             "removed": int(m[f"{g['slc_ns']}@4"], 16) == 3,
                             "FUNC + E: the normal step": (lambda c, a, b: b[3 * c] - a[3 * c] >= 3 * (0x23280 // 128))(
                                 int(m[f"{g['slc_cur']}@5"], 16),
                                 _st.unpack(">9I", bytes.fromhex(m[f"{g['slc_sl']}@6"])),
                                 _st.unpack(">9I", bytes.fromhex(m[f"{g['slc_sl']}@7"]))),
                             "closed": int(m[g["slc_state"]], 16) == 0,
                             # v0.48 (the owner: the DT2's stock behaviour): each key its own
                             # note, the DSP the slice (note - C1) wrapped. The notes are
                             # stock's: the same snapshot, keys (trig 9, 10, 2) and call site
                             # on stock OS 1.11 give 60, 63, 75 (its project's KEYBOARD is a
                             # scale, not chromatic; measured 2026-11-10)
                             "slice notes": notes == [60, 63, 75]}
                    good = all(facts.values()) and busy_ok
                    why = str(facts) + f" notes {notes}" + busy_why
                return good, ("menu, grid dialog and editor drawn; RIGHT picks slice 2, E moves its start, NO "
                 "closes; FUNC + RIGHT splits slice 2, FUNC + LEFT removes it; FUNC + E moves at the normal step; KEYBOARD on a SLICE track: each key its own note, stock's (trig 9, 10, 2: 60, 63, 75, as stock OS 1.11 gives), the slice that note's, as the DT2's"
                              + ("; v0.40: EDIT SLICE POINTS and CREATE SLICE GRID (TR.DET OFF, ON, after CLEAR) reach the "
                                 "editor every time while the loader, TRIM's read, LOAD TO PROJECT, a preview, refused reads, "
                                 "a take saving and normalising, a project switch are in flight; LINKED START/END move the "
                                 "neighbour, bounded; UNLINKED as before" if busy_cmd else "")
                              if good else why)
            later("slice", "SLICE menus and SLICES keys (ColdFire)", "SLICE menus and SLICES keys (ColdFire)",
                  [slc_cmd, busy_cmd, sorted(EMU_ENV.items()), hashlib.sha256(SLICE_NOTE_REF.read_bytes()).hexdigest()],
                  slc_body)

        # 6g. v0.25, GRID's ALLOCATE SLICE (YES on a GRID track's page): trigs placed on steps
        # 1, 3, 5 in GRID RECORDING; CREATE LINEAR LOCKS locks slices 1, 2, 3 on them (the
        # stock's own lock calls, read back through its GET); RANDOM twice, then NO exits with
        # RANDOM's locks kept (v0.60, impbox: as the DT2; NO used to put the linear ones back)
        if "slc_alloc_n" in lay:
            from dnfw.sampler import machines as SMx    # noqa: PLC0415
            sid = SMx.SLICE_REC
            kit = 0x4210D08C
            get = ",".join(f"call:0x40037c52:0:{sid}:{k},wait:2" for k in (0, 2, 4))
            steps = (f"wait:3,poke:{kit + 52 + 0xDE:#x}:0c,wait:4,tap:2,wait:6,tap:19,wait:6,tap:25,wait:4,"
                     f"tap:27,wait:4,tap:29,wait:4,tap:19,wait:6,yes,wait:6,png:m,yes,wait:6,"
                     f"mem:{lay['slc_alloc_n']:#x}:4,{get},yes,wait:6,down,wait:3,yes,wait:6,yes,wait:6,{get},"
                     f"no,wait:6,mem:{lay['slc_state']:#x}:4,{get}")
            # v0.42 (NiKo, v0.40): CREATE RANDOM LOCKS stays open after its YES; another track
            # (TRACK + [TRIG 2]) must close it, YES there must not open it again, and back on the
            # GRID track YES opens it, a page key (tap 5) closes it, YES there not again
            letgo = "slc_letgo" in lay
            if letgo:
                st_, lg_ = f"{lay['slc_state']:#x}", f"{lay['slc_letgo']:#x}"
                steps += (f",yes,wait:6,down,wait:3,yes,wait:6,mem:{st_}:4,"
                          f"press:16,wait:2,press:26,wait:3,release:26,wait:2,release:16,wait:10,"
                          f"mem:0x42432a6c:1,mem:{st_}:4,mem:{lg_}:4,png:t2,yes,wait:8,mem:{st_}:4,png:t2y,no,wait:6,yes,wait:8,mem:{st_}:4,no,wait:6,"
                          f"press:16,wait:2,press:25,wait:3,release:25,wait:2,release:16,wait:10,"
                          f"yes,wait:6,mem:{st_}:4,tap:5,wait:10,mem:{st_}:4,yes,wait:8,mem:{st_}:4,png:p5y,"
                          f"no,wait:4,tap:2,wait:8")
            js = work / "alloc.json"
            al_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", steps, "--png-dir", work / "alloc", "--json", js]

            def al_body(tdir):
                rc, out = run("grid allocate", al_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and js.exists():
                    r = json.loads(js.read_text())
                    m = r["memory"]
                    d0 = [c["d0"] for c in r["direct_calls"]]
                    sts = [int(v, 16) for k, v in m.items() if k.split("@")[0] == hex(lay["slc_state"])]
                    facts = {"three trigs locked": int(m[hex(lay["slc_alloc_n"])], 16) == 3,
                             "linear: slices 1, 2, 3": d0[:3] == [512, 1024, 1536],
                             "closed": sts[:1] == [0],
                             # v0.60 (impbox): NO exits and keeps RANDOM's locks, as the DT2 does
                             "RANDOM changed the locks": d0[3:6] != [512, 1024, 1536],
                             "RANDOM's locks are slices": all(v % 512 == 0 and 512 <= v <= 63 * 512 for v in d0[3:6]),
                             "NO keeps RANDOM's locks": len(d0) >= 9 and d0[6:9] == d0[3:6]}
                    if letgo:
                        trk = [int(v, 16) for k, v in m.items() if k.split("@")[0] == "0x42432a6c"]
                        lgv = [int(v, 16) for k, v in m.items() if k.split("@")[0] == hex(lay["slc_letgo"])]
                        facts.update({"RANDOM stays open after YES": sts[1:2] == [5],
                                      "on track 2": trk == [1],
                                      "another track closes it": sts[2:3] == [0] and lgv[:1] >= [1],
                                      "YES on track 2 opens nothing": sts[3:4] == [0],
                                      "YES again on track 2 opens nothing": sts[4:5] == [0],
                                      "back: YES opens it": sts[5:6] == [5],
                                      "a page key closes it": sts[6:7] == [0],
                                      "YES off the page opens nothing": sts[7:8] == [0]})
                    good = all(facts.values())
                    why = str(facts) + f" {d0} states {sts}"
                return good, ("GRID's ALLOCATE SLICE: LINEAR locks slices 1..3 on three placed trigs; RANDOM "
                              "changes them and NO exits keeping them" + ("; v0.42: open RANDOM lets go on another track and on another "
                              "page, and YES there opens nothing" if letgo else "") if good else why)
            later("alloc", "GRID allocate slice locks (ColdFire)", "GRID allocate slice locks (ColdFire)", [al_cmd, sorted(EMU_ENV.items())], al_body)

        # 6f. v0.25: the sample pages' playhead (the DSP's positions, poked as the link would
        # leave them), the DT2-style sample list (it opens on SAMP's change; DOWN moves SAMP,
        # NO puts it back and closes it), the folder browser (FUNC + YES: a folder entered, a
        # sample picked sets SAMP and closes both), and modulation on SAMP moved through the
        # loaded slots (smp_mod_apply, called on the parameter mirror)
        if "smp_mod_apply" in lay:
            from dnfw.sampler import machines as SMx    # noqa: PLC0415
            M = SMx.MIRROR
            kit = 0x4210D08C
            snd0 = kit + 52
            samp0 = snd0 + 0x6A

            def samp_all(v):                    # (2026-11-14: and a redraw asked, as a load of the value asks one: 1.12
                # redraws a poked value only when asked, so the list's NO put back a slot it had not seen drawn)
                return [f"poke:{kit + 52 + 1163 * t + 0x6A:#x}:{v:02x}00" for t in range(16)] + [
                    f"poke:{lay['smp_overlay_dirty']:#x}:00000001"]
            d = bytearray(0x1000)
            struct.pack_into("<II", d, 0, 0x31504D53, 4)
            for k, (fr, nm) in enumerate([(48000, "KICK"), (96000, "SHS_HAU"), (0, ""), (24000, "SNARE")]):
                if fr:
                    struct.pack_into("<IIfI", d, 8 + 16 * k, 0x84001000 + 0x40000 * k, fr, 1.0, 1)
                d[0x808 + 8 * k:0x808 + 8 * k + len(nm)] = nm.encode()
            ov = bytes((40 + (j * 7) % 150) for j in range(100))
            fb, sb = SMx.META_FOLDER_BYTES, SMx.META_SLOT_BYTES
            mt = bytearray(SMx.META_BYTES)
            struct.pack_into("<III", mt, 0, SMx.META_MAGIC, 1, 2)
            mt[12:22] = b"drum_loops"
            mt[12 + fb:12 + fb + 5] = b"loops"
            for k in range(128):
                mt[12 + SMx.META_FOLDERS * fb + sb * k] = 0xFF
            for k, f, nm in ((0, 0, "kick"), (1, 1, "shs_haunt_tape_56_drum_lo"), (3, 0xFF, "snare")):
                r0 = 12 + SMx.META_FOLDERS * fb + sb * k
                mt[r0] = f
                mt[r0 + 4:r0 + 4 + len(nm)] = nm.encode()
            cell = 0x800068E4 + 34 + 86
            mem = lambda va, n=4: f"mem:{va:#x}:{n}"          # noqa: E731
            st = ["wait:2"] + [f"poke:{kit + 52 + 1163 * t + 0xDE:#x}:08" for t in range(16)] + samp_all(2)
            st += [f"poke:{M:#x}:{d[:0xC10].hex()}"] + [f"poke:{M + 0x1000 + 100 * k:#x}:{ov.hex()}" for k in (0, 1, 3)]
            st += [f"poke:{M + 0x80000:#x}:{mt.hex()}", f"poke:{lay['smp_dir_ok']:#x}:00000001",
                   f"poke:{lay['smp_meta_ok']:#x}:00000001"]
            base = list(st)                     # (the pool as loaded: 6i starts from it too)
            st += ["wait:6", "tap:2", "wait:6", "png:p2", f"poke:{lay['smp_periods']:#x}:00000000",
                   f"poke:{lay['smp_pos_at']:#x}:00000000", f"poke:{lay['smp_pos']:#x}:" + "8000" * 16,
                   "wait:12", "png:ph1", f"poke:{lay['smp_pos']:#x}:" + "C000" * 16, "wait:36", "png:ph2"]
            # v0.40 (owner: "the slice machine's on-screen indicators are a little slow to catch
            # up"): the DSP's packets through smp_pos_in, two voices on the page's track (the
            # snapshot's table gives every voice to track 1, the active one): a note at 0x2000,
            # then a second at 0xA000 while the first still sounds -- the playhead is the NEWER
            # note's (v0.30..v0.39: the lower position's, the older note's until it ended);
            # then the first voice retriggered at 0xE000: that one. Each moved column is drawn by the
            # next UI pass after 40 frames (the emulator's frame counter moves only by addl);
            # a playhead that stays in its column asks for no redraw
            # (2026-11-16, v0.56.2: "the next UI pass" is one pass of the redraw routine, `pass:`, not a wait:3.
            # Measured on v0.56.1 and v0.56.2 alike: the loop wakes about every 4.4 M here and draws at every
            # wake (stock asks it), so wait:3 held a pass or none by its phase alone -- v0.56.1 passed by it, and
            # lfo4's code moved the phase ~1 M -- and "a still one not redrawn" was never measured by the draw
            # count. The playhead's own part is its redraw ask, smp_wants_redraw(), read after each packet: asked
            # when the column moved, not when it stayed; and a moved one is drawn by the next pass)
            ph_sym = W.SPEC.get("c_text_symbols", {})
            ph_new = "smp_pos_in" in lay       # (and smp_wants_redraw beside it: a build without it fails here)
            ph_cmd, phjs = None, work / "playhead.json"
            if ph_new:                          # (a run of its own: the list's steps below are timed)
                F_ = "0x4058f8d4"
                pkt = 0x46A23000                 # (above the harness's call stack: SENTINEL + 0x2C00)
                per = f"{lay['smp_periods']:#x}"

                def packet(n, v0, v1):
                    return [f"poke:{per}:{n:08x}", f"poke:{pkt:#x}:{v0:04x}{v1:04x}" + "ffff" * 14,
                            f"call:{lay['smp_pos_in']:#x}:{pkt:#x}", f"addl:{F_}:40",
                            f"call:{ph_sym['smp_wants_redraw']:#x}", mem(lay["wr_draws"]), "pass:30"]
                ps = base + ["wait:6", "tap:2", "wait:6", "png:v0", "mem:0x42432a6c:1"]
                for n, v0, v1, nm in ((100, 0x2000, 0xFFFF, "v1"), (101, 0x2100, 0xA000, "v2"),
                                      (102, 0x2108, 0xA008, "v3"), (103, 0xE000, 0xA010, "v4")):
                    ps += packet(n, v0, v1) + [f"call:{lay['smp_playhead']:#x}:0", f"png:{nm}", mem(lay["wr_draws"])]
                ph_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                          "--snapshot", snap, "--steps", ",".join(ps), "--png-dir", work / "playhead", "--json", phjs]
            st += ["tap:2", "wait:6"]
            # v0.27: SAMP set without a turn (TRACK + PLAY's clear, a load) leaves the list
            # closed; a turn of SAMP (encoder D) opens it
            # (the emulator's encoders do not move a stock page's value, so a turn is the stock
            # setter's own call of smp_quant on SAMP's slot, then the value it writes)
            def turn(v):                        # (and a redraw asked for, as the turn's own would)
                return [f"call:{lay['smp_quant']:#x}:sound0:{SMx.RECORDS[SMx.SAMP_REC][0]}:{v << 8:#x}",
                        f"poke:{samp0:#x}:{v:02x}00", f"poke:{lay['smp_overlay_dirty']:#x}:00000001"]
            st += samp_all(3) + [f"poke:{lay['smp_overlay_dirty']:#x}:00000001", "wait:10", "png:l0",
                                 mem(lay["smp_lst_open"])]      # (redrawn: the change is seen, and opens nothing)
            st += samp_all(2) + ["wait:10"] + turn(4) + ["wait:10", "png:l1", mem(lay["smp_lst_open"]), "down",
                                 "wait:8", "png:l2", mem(samp0, 2), "no", "wait:8", "png:l3", mem(samp0, 2),
                                 mem(lay["smp_lst_open"])]
            st += samp_all(2) + ["wait:10"] + turn(3) + ["wait:10", "png:l4", "press:17", "wait:2", "yes", "wait:2", "release:17",
                                 "wait:8", "yes", "wait:6", "png:b1", mem(lay["smp_fb_open"]), "yes", "wait:8", "png:b2",
                                 mem(lay["smp_fb_folder"]), "down", "wait:2", "yes", "wait:8", "png:b3t",
                                 mem(samp0, 2), mem(lay["smp_fb_open"]),
                                 "right", "wait:6", "yes", "wait:8", "png:b3",
                                 mem(samp0, 2), mem(lay["smp_fb_open"]), mem(lay["smp_lst_open"])]
            # (v0.33: YES on a sample in PROJECT RAM ticks it, as the DT2's; RIGHT, LOAD TRK assigns)
            # (v0.31: FUNC + YES opens on the two stores, the cursor on PROJECT RAM: YES enters it)
            # the SAMPLE ACTION menu: into "loops", RIGHT on its sample, DELETE, asked, YES
            st += samp_all(3) + ["wait:10"] + turn(2) + ["wait:10", "press:17", "wait:2", "yes", "wait:2", "release:17", "wait:8",
                                 "yes", "wait:6", "down", "wait:4", "yes", "wait:6", "right", "wait:6", "png:m1", "down", "wait:3",
                                 "down", "wait:3", "yes", "wait:6", "png:m2", "yes", "wait:8", "png:m3",
                                 mem(M + 8 + 16 + 4, 4)]
            # (v0.30: the reach scaled by depth over the loaded samples, held at the ends. The
            # DELETE above emptied slot 1, so two are loaded: slots 0 and 3. SAMP 1 (slot 0):
            # +43 one sample on (SAMP 4), +125 to the last and no further (SAMP 4), +1 none
            # (SAMP 1). v0.29's first form set SAMP 2, the slot just deleted, and counted three)
            # (v0.40: the reference is the voice's target cell, the sound's value or the trig's
            # lock: SAMP 1 there as the sound's, as stock's sync puts it)
            st += [f"poke:0x800052a8:{snd0:08x}", f"poke:{samp0:#x}:0100", f"poke:{cell - 0x800068E4 + 0x80003AF0:#x}:0100",
                   f"onpc:0x400db390:{cell:#x}:2c00",
                   f"call:{lay['smp_mod_apply']:#x}:0x800068e4", mem(cell, 2),
                   f"onpc:0x400db390:{cell:#x}:7e00", f"call:{lay['smp_mod_apply']:#x}:0x800068e4", mem(cell, 2),
                   f"onpc:0x400db390:{cell:#x}:0200", f"call:{lay['smp_mod_apply']:#x}:0x800068e4", mem(cell, 2)]
            # (v0.45: smp_mod_apply sets SAMP to the target first -- a slot never glides -- and
            # then runs the stock apply, which adds the modulation: the modulated value goes in
            # where that apply adds it, on its entry, not before the call)
            js = work / "samplist.json"
            sl_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", ",".join(st), "--png-dir", work / "samplist", "--json", js]

            def sl_body(tdir):
                rc, out = run("sample list", sl_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and js.exists():
                    r = json.loads(js.read_text())
                    m = r["memory"]
                    shots = {n: pathlib.Path(r["screens"][n]).read_bytes() for n in ("p2", "ph1", "ph2", "l1", "b1", "b2")}
                    lo, fo, ff = (hex(lay[k]) for k in ("smp_lst_open", "smp_fb_open", "smp_fb_folder"))
                    sp, ce = hex(samp0), hex(cell)
                    o = 0
                    facts = {"playhead drawn and moving": len({shots["p2"], shots["ph1"], shots["ph2"]}) == 3,
                             "v0.27: SAMP set without a turn leaves the list closed": int(m[lo], 16) == 0,
                             "list opens on a turn": int(m[f"{lo}@{1 + o}"], 16) == 1,
                             "DOWN moves SAMP": m[sp] == "0500",
                             "NO puts it back and closes": m[f"{sp}@{3 + o}"] == "0200" and int(m[f"{lo}@{4 + o}"], 16) == 0,
                             "browser opens, a folder entered": int(m[fo], 16) == 1 and int(m[ff], 16) == 0
                             and shots["b1"] != shots["b2"],
                             "v0.33: YES on a sample ticks it: SAMP kept, the browser up":
                             m[f"{sp}@{7 + o}"] == "0300" and int(m[f"{fo}@{8 + o}"], 16) == 1,
                             "RIGHT, LOAD TRK: SAMP, both closed": m[f"{sp}@{9 + o}"] == "0100" and int(m[f"{fo}@{10 + o}"], 16) == 0
                             and int(m[f"{lo}@{11 + o}"], 16) == 0,
                             "DELETE in the SAMPLE ACTION menu empties the slot": m[hex(M + 28)] == "00000000"
                             and len({pathlib.Path(r["screens"][n]).read_bytes() for n in ("m1", "m2", "m3")}) == 3,
                             "modulated SAMP through the loaded slots, by depth, held at the last":
                             [m[ce], m[f"{ce}@{14 + o}"], m[f"{ce}@{15 + o}"]] == ["0400", "0400", "0100"]}
                    if ph_new:
                        prc, pout = run("playhead", ph_cmd, logs, env=EMU_ENV, trace=tdir)
                        pr = json.loads(phjs.read_text()) if prc == 0 and phjs.exists() else {"memory": {}, "screens": {}}
                        newest, drawn, why_ph = gate_playhead.playhead_fact(
                            pr, lay["smp_playhead"], ph_sym["smp_wants_redraw"], lay["wr_draws"])
                        facts["v0.40: the newest note's playhead (0x2000, then 0xA000 over 0x2100, 0xA008, the first voice again at 0xE000)"] = newest
                        facts["v0.40: a moved playhead drawn at the next pass, a still one not redrawn"] = drawn
                    else:
                        why_ph = ""
                    good = all(facts.values())
                    why = str(facts) + why_ph
                return good, ("the playhead drawn where the DSP says"
                              + ("; v0.40: the newest note's, drawn at the next pass when its column moves, no redraw when it does not"
                                 if ph_new else "") + "; SAMP set without a turn opens nothing, a turn opens the list, DOWN moves it, NO "
                              "puts it back; FUNC + YES's browser enters a folder, YES ticks a sample and RIGHT, LOAD TRK assigns it; "
                              "its SAMPLE ACTION menu deletes; modulation on SAMP steps through the loaded slots" if good else why)
            later("samplist", "sample list, browser, playhead (ColdFire)", "sample list, browser, playhead (ColdFire)", [sl_cmd, ph_cmd, sorted(EMU_ENV.items())], sl_body)

            # 6i. v0.29: multi-select in the browser (a user's report: no way to delete all the
            # samples sent in). At the top, FUNC + YES marks every sample of "drum_loops"
            # (kick); RIGHT on "loops" opens its menu, SELECT ALL marks its sample; RIGHT,
            # DELETE: "DELETE 2?", YES: slots 0 and 1 emptied, the snare (no folder) kept; the
            # marks cleared, the browser still up, and the two emptied folders no longer shown
            if "smp_fb_mark_count" in lay:
                fbc, fbm = lay["smp_fb_count"], lay["smp_fb_mark_count"]
                lead = ["wait:6", "tap:2", "wait:6", f"poke:{lay['smp_periods']:#x}:00000000",     # (as 6f: the
                        f"poke:{lay['smp_pos_at']:#x}:00000000", "wait:12", "tap:2", "wait:6"]      # clock set)
                ms = base + lead + samp_all(3) + [f"poke:{lay['smp_overlay_dirty']:#x}:00000001", "wait:10"] + turn(2) + [
                    "wait:10", "press:17", "wait:2", "yes", "wait:2", "release:17", "wait:8", "yes", "wait:6",
                    f"call:{fbc:#x}",
                    "press:17", "wait:2", "yes", "wait:2", "release:17", "wait:6", "png:s1", f"call:{fbm:#x}",
                    "down", "wait:4", "right", "wait:6", "png:s2", "yes", "wait:6", f"call:{fbm:#x}",
                    "right", "wait:6", "down", "wait:3", "png:s3", "yes", "wait:6", "png:s4", "yes", "wait:10",
                    "png:s5", mem(M + 8), mem(M + 24), mem(M + 56), f"call:{fbm:#x}", mem(lay["smp_fb_open"]),
                    f"call:{fbc:#x}"]
                mjs = work / "multisel.json"
                ms_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                          "--snapshot", snap, "--steps", ",".join(ms), "--png-dir", work / "multisel", "--json", mjs]

                def ms_body(tdir):
                    rc, out = run("multi-select", ms_cmd, logs, env=EMU_ENV, trace=tdir)
                    why, good = out[-800:], False
                    if rc == 0 and mjs.exists():
                        r = json.loads(mjs.read_text())
                        m, calls = r["memory"], [c.get("d0") for c in r.get("direct_calls", [])]
                        shots = [pathlib.Path(r["screens"][n]).read_bytes() for n in ("s1", "s2", "s3", "s4", "s5")]
                        d0 = [int(str(x), 0) if x is not None else None for x in calls][1:]   # (the first: the turn's smp_quant)
                        facts = {"the top: three items (two folders, INCOMING)": d0[:1] == [3],
                                 "FUNC + YES on a folder marks its sample": d0[1:2] == [1],
                                 "SELECT ALL on the second folder: two marked": d0[2:3] == [2],
                                 "DELETE 2: slots 0 and 1 emptied, the snare kept": m[hex(M + 8)] == "00000000"
                                 and m[hex(M + 24)] == "00000000" and m[hex(M + 56)] != "00000000",
                                 "the marks cleared, the browser up, only INCOMING left":
                                 d0[3:5] == [0, 1] and int(m[hex(lay["smp_fb_open"])], 16) == 1,
                                 "each step drawn": len(set(shots)) == 5}
                        good = all(facts.values())
                        why = f"{facts} d0={d0}"
                    return good, ("FUNC + YES marks a folder's samples; SELECT ALL a folder's; DELETE takes the "
                                  "marked ones (DELETE 2?), keeps the rest, clears the marks, hides emptied folders"
                                  if good else why)
                later("multisel", "multi-select delete (ColdFire)", "multi-select delete (ColdFire)", [ms_cmd, sorted(EMU_ENV.items())], ms_body)

            # 6i2. v0.45: SELECT UNUSED (the DT2's 13.6.6; Wolljamin). Slots 0..7 loaded. Used: pattern
            # 0's kit, track 0 (ONESHOT) on SAMP 2 (slot 1); pattern 5's kit, track 3 on SAMP 4
            # (slot 3); a SAMP p-lock in pattern 5's table, track 3, step 0, on SAMP 7 (slot 6).
            # A decoy: pattern 7's track 0 is an FM machine whose slot-43 byte is 8 (slot 7):
            # not a sample machine, so not a use. Every other kit's types poked to 0 (FM).
            # SELECT UNUSED marks {0, 2, 4, 5, 7} (5); UNLOAD empties exactly those
            if "smp_fb_mark_unused" in lay:
                P0, PSTR, KSTR = 0x4121998C, 122478, 23921
                d2 = bytearray(d[:0xC10])
                for k in range(8):
                    struct.pack_into("<IIfI", d2, 8 + 16 * k, 0x84001000 + 0x40000 * k, 24000, 1.0, 1)
                us = list(base) + [f"poke:{M:#x}:{d2.hex()}"]
                for n in range(128):
                    for t in range(16):
                        if n == 0 or (n, t) == (5, 3):
                            continue
                        us.append(f"poke:{kit + KSTR * n + 52 + 1163 * t + 0xDE:#x}:00")
                us += [f"poke:{kit + 52 + 1163 * t + 0x6A:#x}:0000" for t in range(1, 16)]
                us += [f"poke:{kit + 52 + 0x6A:#x}:0200",
                       f"poke:{kit + KSTR * 5 + 52 + 1163 * 3 + 0xDE:#x}:08",
                       f"poke:{kit + KSTR * 5 + 52 + 1163 * 3 + 0x6A:#x}:0400",
                       f"poke:{kit + KSTR * 7 + 52 + 0xDE:#x}:00",
                       f"poke:{kit + KSTR * 7 + 52 + 0x6A:#x}:0800"]
                for n in range(128):                    # every pattern's SAMP index: no lock
                    tb = P0 + PSTR * n + 97872
                    us.append(f"poke:{tb + 20640:#x}:" + "ff" * (101 * 16))
                tb5 = P0 + PSTR * 5 + 97872
                us += [f"poke:{tb5 + 258 * 79:#x}:2b03" + "0700" + "ffff" * 127,
                       f"poke:{tb5 + 20640 + 101 * 3 + 43:#x}:4f",
                       "wait:4", f"call:{lay['smp_fb_mark_unused']:#x}"]
                us += [f"call:{lay['smp_fb_marked']:#x}:{k}" for k in range(8)]
                us += [f"call:{lay['smp_fb_delete']:#x}:0:0xffffffff", "wait:4"] + [mem(M + 8 + 16 * k + 4) for k in range(8)]
                ujs, usf = work / "unused.json", work / "unused.steps"
                usf.write_text(",".join(us))
                us_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                          "--snapshot", snap, "--steps", f"@{usf}", "--png-dir", work / "unused", "--json", ujs]

                def us_body(tdir):
                    rc, out = run("select unused", us_cmd, logs, env=EMU_ENV, trace=tdir)
                    why, good = out[-800:], False
                    if rc == 0 and ujs.exists():
                        r = json.loads(ujs.read_text())
                        m = r["memory"]
                        d0 = [int(str(c.get("d0")), 0) if c.get("d0") is not None else None
                              for c in r.get("direct_calls", [])]
                        fr = [int(m[hex(M + 8 + 16 * k + 4)], 16) for k in range(8)]
                        facts = {"five unused marked": d0[:1] == [5],
                                 "the marks are 0, 2, 4, 5, 7": [x & 1 for x in d0[1:9]] == [1, 0, 1, 0, 1, 1, 0, 1],
                                 "UNLOAD empties them, keeps 1, 3, 6 (a kit's SAMP, another pattern's kit, "
                                 "another pattern's SAMP lock; an FM track's byte ignored)":
                                 [x != 0 for x in fr] == [False, True, False, True, False, False, True, False]}
                        good = all(facts.values())
                        why = f"{facts} d0={d0} frames={fr}"
                    return good, ("SELECT UNUSED marks the loaded slots no pattern's kit or SAMP lock uses (5 of 8: a "
                                  "kit's SAMP, another pattern's kit, a lock in another pattern, an FM track's byte "
                                  "ignored); UNLOAD empties exactly those" if good else why)
                later("unused", "SELECT UNUSED (ColdFire)", "SELECT UNUSED (ColdFire)", [us_cmd, sorted(EMU_ENV.items())], us_body)

            # 6l. v0.31: the browser's two stores and the +Drive's library. A library of three
            # samples (two in INCOMING, one in DRUMS) put in its RAM as lib.c reads it at
            # power-on; FUNC + YES opens on the two stores, UP to +DRIVE, YES: its folders
            # (2); YES into the first (2 samples); YES ticks one (1 selected); RIGHT, LOAD TO
            # PROJ (the first action), YES: queued (pending); NO: back to +DRIVE's folders;
            # NO: back to the two stores; NO: closed
            if "smp_fb_store" in lay and "smp_lp_queued" in lay:
                import zlib as _z                # noqa: F401
                LRAM = SMx.MIRROR + 0x100000
                LDATA = 0x700000 + 1 + 256 + 4

                def adl(b, s=1):
                    a_, b_ = s & 0xFFFF, s >> 16
                    for x in b:
                        a_ = (a_ + x) % 65521
                        b_ = (b_ + a_) % 65521
                    return b_ << 16 | a_

                def lent(start, frames, folder, name):
                    e = bytearray(64)
                    struct.pack_into("<III", e, 0, start, frames, 0x3F800000)
                    e[12], e[13] = 1, folder
                    struct.pack_into("<I", e, 20, (frames * 2 + 511) // 512)
                    e[24:24 + len(name)] = name.encode()
                    struct.pack_into("<I", e, 60, adl(bytes(e[:60])) ^ 0x4C494245)
                    return bytes(e)
                idx = lent(LDATA, 1000, 0, "inc one") + lent(LDATA + 4, 1000, 0, "inc two") + lent(LDATA + 8, 500, 2, "drum one")
                fold = b"INCOMING".ljust(32, b"\0") + b"RECORDED".ljust(32, b"\0") + b"DRUMS".ljust(32, b"\0")
                lsteps = [f"poke:{LRAM + 0x200:#x}:{idx.hex()}", f"poke:{LRAM + 0x200 + 2048 * 64:#x}:{fold.hex()}",
                          f"poke:{lay['smp_lib_state']:#x}:00000002", f"call:{lay['smp_lib_refresh']:#x}"]
                fbs, pend = lay["smp_fb_store"], lay["smp_lib_pending"]
                ds = base + lead + lsteps + samp_all(3) + [f"poke:{lay['smp_overlay_dirty']:#x}:00000001", "wait:10"] + turn(2) + [
                    "wait:10", "press:17", "wait:2", "yes", "wait:2", "release:17", "wait:8", "png:d0", mem(fbs),
                    "up", "wait:4", "yes", "wait:6", "png:d1", mem(fbs), f"call:{fbc:#x}",
                    "yes", "wait:6", "png:d2", f"call:{fbc:#x}", "yes", "wait:6", "png:d3", f"call:{fbm:#x}",
                    # v0.33: FUNC + YES on a sample previews it (+DRIVE's: asked of the loader).
                    # Auto preview: in +DRIVE it is a toggle, so let go it plays on; FUNC + YES
                    # again stops it
                    "press:17", "wait:2", "press:10", "wait:6", mem(lay["smp_pv_state"]),
                    "release:10", "wait:2", "release:17", "wait:4", mem(lay["smp_pv_state"])]
                ds += ([mem(lay["smp_fb_auto"]), "png:auto_on", "press:17", "wait:2", "press:10", "wait:4", "release:10", "wait:2",
                        "release:17", "wait:4", mem(lay["smp_pv_state"]), mem(lay["smp_fb_auto"]), "png:auto_off"]
                       if "smp_fb_auto" in lay else [])
                ds += [f"call:{fbm:#x}",
                    "right", "wait:6", "png:d4", "yes", "wait:6", mem(lay["smp_lp_queued"]),
                    "no", "wait:6", mem(lay["smp_fb_folder"]), mem(fbs), "no", "wait:6", mem(fbs),
                    "no", "wait:6", mem(lay["smp_fb_open"]),
                    # v0.33: MOVE SELECTED, then MOVE HERE (the DT2's 13.6.5): open again (on
                    # +DRIVE now), INCOMING, tick "inc one", RIGHT, MOVE SELECT (the fourth),
                    # NO up to the folders, DOWN twice to DRUMS, RIGHT, MOVE HERE (the third): DRUMS
                    # then holds two
                    "press:17", "wait:2", "yes", "wait:2", "release:17", "wait:8", "yes", "wait:6", "yes", "wait:6",
                    "yes", "wait:4", "right", "wait:4", "down", "wait:2", "down", "wait:2", "down", "wait:2", "yes", "wait:4",
                    "no", "wait:6", "down", "wait:4", "down", "wait:4", "right", "wait:4", "png:mv", "down", "wait:2", "down", "wait:2",
                    "yes", "wait:6", "yes", "wait:6", f"call:{fbc:#x}", "png:mv2"]
                djs = work / "drive.json"
                d_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                         "--snapshot", snap, "--steps", ",".join(ds), "--png-dir", work / "drive", "--json", djs]
                # v0.40: folders inside folders (takton: a pack's nested folders flattened into
                # many top-level "TRANCE STARTER PAC"s): a three-level library with look-alike
                # names at different levels and an old import's flat folder, driven through
                # every level (scripts/emu_drive_nest.py: its facts; v0.39's code fails them)
                nest = "smp_fb_titletext" in lay
                njs_ = work / "drive_nest.json"
                dn_cmd = [a.venv, "-u", "scripts/emu_drive_nest.py", "--build", bdir, "--snapshot", snap,
                          "--json", njs_, "--png-dir", work / "drive_nest"]

                def d_body(tdir):
                    rc, out = run("+drive browser", d_cmd, logs, env=EMU_ENV, trace=tdir)
                    why, good = out[-800:], False
                    if rc == 0 and djs.exists():
                        r = json.loads(djs.read_text())
                        m = r["memory"]
                        d0 = [int(str(c.get("d0")), 0) for c in r.get("direct_calls", [])][2:]   # (the refresh's, the turn's)
                        sh = [pathlib.Path(r["screens"][n]).read_bytes() for n in ("d0", "d1", "d2", "d3", "d4")]
                        S = hex(fbs)
                        ash = 3 if "smp_fb_auto" in lay else 0    # auto preview: three more reads before
                        facts = {"opens on the two stores": int(m[S], 16) == 0xFFFFFFFF,
                                 "UP, YES: +DRIVE, its three folders (v0.33: RECORDED shows, named, though empty)":
                                 int(m[f"{S}@1"], 16) == 1 and d0[0:1] == [3],
                                 "YES: INCOMING's two samples": d0[1:2] == [2],
                                 "YES ticks one": d0[2:3] == [1],
                                 ("auto preview: FUNC + YES turns it on (it plays, let go too, AUTO in the title), again off (it stops, AUTO gone)"
                                  if "smp_fb_auto" in lay else "v0.33: FUNC + YES held previews it; let go, it stops"):
                                 int(m[hex(lay["smp_pv_state"])], 16) in (1, 2, 3)
                                 and (int(m[f"{hex(lay['smp_pv_state'])}@3"], 16) in (1, 2, 3)
                                      and int(m[hex(lay["smp_fb_auto"])], 16) == 1
                                      and int(m[f"{hex(lay['smp_pv_state'])}@5"], 16) == 0
                                      and int(m[f"{hex(lay['smp_fb_auto'])}@6"], 16) == 0
                                      and pathlib.Path(r["screens"]["auto_on"]).read_bytes()
                                      != pathlib.Path(r["screens"]["auto_off"]).read_bytes()
                                      if "smp_fb_auto" in lay else int(m[f"{hex(lay['smp_pv_state'])}@3"], 16) == 0),
                                 "the preview ticks nothing (still one)": d0[3:4] == [1],
                                 "v0.33: MOVE SELECTED, MOVE HERE: DRUMS holds two": d0[4:5] == [2],
                                 "LOAD TO PROJ queues it": int(m[hex(lay["smp_lp_queued"])], 16) == 1,
                                 "NO: +DRIVE's folders": int(m[hex(lay["smp_fb_folder"])], 16) == 0xFFFFFFFF
                                 and int(m[f"{S}@{6 + ash}"], 16) == 1,
                                 "NO: the two stores": int(m[f"{S}@{7 + ash}"], 16) == 0xFFFFFFFF,
                                 "NO: closed": int(m[hex(lay["smp_fb_open"])], 16) == 0,
                                 "each step drawn": len(set(sh)) == 5}
                        good = all(facts.values())
                        why = f"{facts} d0={d0} mem={m}"
                    if good and nest:
                        rc, out = run("+drive nested folders", dn_cmd, logs, env=EMU_ENV, trace=tdir)
                        r = json.loads(njs_.read_text()) if njs_.exists() else {}
                        good = rc == 0 and bool(r.get("ok")) and len(r.get("facts", {})) >= 24
                        why = (json.dumps({k: v for k, v in r.get("facts", {}).items() if not v})[:900]
                               + " " + json.dumps(r.get("seen", {}))[:600]) if r else out[-800:]
                    return good, ("the two stores, +DRIVE's folders and samples, a tick, LOAD TO PROJECT "
                                  "queued, NO back up a level each time and closed at the top"
                                  + ("; v0.40: folders inside folders, three levels (look-alike names, an old "
                                     "flat folder): each level's folders then samples, the path in the title, "
                                     "preview, LOAD TO PROJECT, NO up onto the folder left, MOVE, a folder's "
                                     "FUNC + YES all it holds, SELECT ALL a list's own, CREATE FOLDER inside, "
                                     "DELETE of a folder with folders inside, the rest untouched" if nest else "")
                                  if good else why)
                later("drive", "+DRIVE browser (ColdFire)", "+DRIVE browser (ColdFire)",
                      [d_cmd] + ([dn_cmd] if nest else []) + [sorted(EMU_ENV.items())], d_body)

                # 6l2. v0.39 (the owner, v0.38): +DRIVE's keys as Elektron's lists, and long names
                # as the DT2's. A folder of 17: "SHORT ONE.WAV", then 16 hi-hats whose names are
                # one but for their last two characters (his "AT HIHAT": six rows of "AT BIRDHOUSE
                # HI-HA"). Held DOWN steps on by itself, in the list and in the action menu;
                # FUNC + DOWN a page; a knob turned pushed in a page a detent, unpushed one; D
                # pushed leaves +DRIVE up (stock took it); NO still goes up. An unselected long
                # name is head...tail; the selected one scrolls from its start to its end; moved
                # off, it is head...tail again and the new one starts from its start
                if "smp_fb_rowtext" in lay and "smp_mq_off" in lay:
                    hh = [f"AT BIRDHOUSE HI-HAT CLOSED VEL {k:02d}" for k in range(16)]
                    # v0.41: a user's v0.38 INCOMING folder (his video: hands off, the cursor going
                    # between the top two rows by itself)
                    pab = ["LC_FTR_100_FX_IMPACT_01.WAV", "LC_FTR_100_FX_RISE_01.WAV", "LC_FTR_BASS_A#_02.WAV",
                           "LC_FTR_BASS_G.WAV", "LC_FTR_PERC_01.WAV", "LC_FTR_PERC_07_01.WAV"]
                    nidx = lent(LDATA, 1000, 2, "SHORT ONE.WAV") + b"".join(
                        lent(LDATA + 4 + 4 * k, 1000 + k, 2, nm) for k, nm in enumerate(hh)) + b"".join(
                        lent(LDATA + 4 + 64 + 4 * k, 1000 + k, 0, nm) for k, nm in enumerate(pab))
                    nfold = b"INCOMING".ljust(32, b"\0") + b"RECORDED".ljust(32, b"\0") + b"AT HIHAT".ljust(32, b"\0")
                    TICK = 0x4058F8D4
                    rt, mq, cur, mcur = lay["smp_fb_rowtext"], lay["smp_mq_off"], lay["smp_fb_cur"], lay["smp_fb_mcur"]
                    snap_ = [mem(rt, 144), mem(mq), mem(cur), mem(TICK)]
                    ns = base + lead + [f"poke:{LRAM + 0x200:#x}:{nidx.hex()}", f"poke:{LRAM + 0x200 + 2048 * 64:#x}:{nfold.hex()}",
                                        f"poke:{lay['smp_lib_state']:#x}:00000002", f"call:{lay['smp_lib_refresh']:#x}"]
                    ns += samp_all(3) + [f"poke:{lay['smp_overlay_dirty']:#x}:00000001", "wait:10"] + turn(2) + [
                        "wait:10", "press:17", "wait:2", "yes", "wait:2", "release:17", "wait:8", "up", "wait:4", "yes", "wait:6",
                        f"poke:{lay['smp_fb_folder']:#x}:00000002", f"poke:{cur:#x}:00000000",
                        f"poke:{lay['smp_overlay_dirty']:#x}:00000001", "wait:6", "png:n0"] + snap_      # 0: the folder
                    # (the emulator's clock, the 1.5 kHz ticks at 0x4058f8d4, does not run: it is set
                    # as time would move it: the repeat's 0.4 s then 0.08 s steps, the marquee's 1 s
                    # rest and 0.2 s a character). 2026-11-14 (the 1.12 gate's blind spots): each clock step
                    # waits 20 M, about four UI passes. Idle, the UI loop passes once in about 4.5 M instructions
                    # on 1.11 and 1.12 alike (jmp_poll entries over 100 M, clean v0.53), so 2 M held a pass or
                    # none by the snapshot's phase: 1.11's per-build snapshot held one, 1.12's none (one repeat seen)
                    def clock(t):
                        return [f"poke:{TICK:#x}:{t:08x}", "wait:20"]
                    ns += clock(100) + ["press:14", "wait:2"] + clock(700) + clock(850) + clock(1000) + snap_   # 1: held DOWN
                    ns += ["release:14", "wait:2"] + clock(1300) + snap_ + clock(1600) + snap_                  # 2, 3: let go
                    # 4-19: the marquee of the row it stopped on (selected at tick 1000)
                    MQT = (1100, 1900, 2600, 2900, 3200, 4100, 5000, 6200, 7400, 7700, 8200, 8700, 8850, 9000, 9500, 10900)
                    for t in MQT:
                        ns += clock(t) + snap_
                    ns += ["down", "wait:3"] + snap_                                                               # 20: moved off
                    ns += ["press:17", "wait:2", "down", "wait:2", "release:17", "wait:3"] + snap_                  # 21: FUNC + DOWN
                    ns += [f"poke:{cur:#x}:00000000", "wait:3", "turn:3:1", "wait:3"] + snap_                     # 22: pushed, two detents
                    ns += ["press:44", "wait:3", "release:44", "wait:4", mem(lay["smp_fb_open"]), mem(lay["smp_fb_store"]),
                           mem(lay["smp_fb_folder"]), "png:n1"]
                    ns += ["right", "wait:4"] + clock(20000) + ["press:14", "wait:4"] + clock(20700) + clock(20850) + clock(21000) + [
                           "release:14", "wait:3", mem(mcur), mem(lay["smp_fb_menu"]),
                           "png:n2", "no", "wait:4", "no", "wait:4", mem(lay["smp_fb_folder"]), mem(lay["smp_fb_open"])]
                    # v0.41: in INCOMING with the cursor on its first row, encoder A jittering (+1, -1,
                    # ... with no key, as a worn encoder resting between detents reports): the cursor
                    # moves once at most and stays; then turned by hand, three detents on and three
                    # back: a row a detent, the turn back losing one
                    jit0 = sum(1 for x in ns if x == mem(cur))
                    jrt = sum(1 for x in ns if x == mem(rt, 144))
                    ns += [f"poke:{lay['smp_fb_folder']:#x}:00000000", f"poke:{cur:#x}:00000000",
                           f"poke:{lay['smp_overlay_dirty']:#x}:00000001", "wait:6", mem(rt, 144), mem(cur), "png:n3"]
                    for _ in range(6):
                        ns += ["spin:0:1", mem(cur), "spin:0:-1", mem(cur)]
                    ns += ["png:n4"]
                    ns += ["spin:5:1", mem(cur), "spin:5:1", mem(cur), "spin:5:1", mem(cur),
                           "spin:5:-1", mem(cur), "spin:5:-1", mem(cur), "spin:5:-1", mem(cur)]
                    # auto preview (FUNC + YES in +DRIVE toggles it): in AT HIHAT, on: the sample under
                    # the cursor plays at once; ten DOWNs with the clock still start nothing; 100 ticks
                    # (66 ms) later still nothing; 300 (200 ms) later exactly one; again for one more
                    # DOWN; FUNC + YES again: off and silent; on again, then NO up and closed: off.
                    # The link: no retries, the loader idle at the end
                    auto = "smp_fb_auto" in lay
                    if auto:
                        A, AS, PV = lay["smp_fb_auto"], lay["smp_fb_auto_starts"], lay["smp_pv_state"]
                        RT_, LS_ = lay["smp_retries"], lay["smp_lstate"]
                        ar = [mem(A), mem(AS), mem(PV), mem(cur), mem(RT_), mem(LS_)]
                        fy = ["press:17", "wait:2", "press:10", "wait:2", "release:10", "wait:2", "release:17", "wait:4"]
                        ns += [f"poke:{lay['smp_fb_folder']:#x}:00000002", f"poke:{cur:#x}:00000001",
                               f"poke:{lay['smp_overlay_dirty']:#x}:00000001", "wait:4"] + clock(30000) + ar      # a0
                        ns += fy + ["wait:4"] + ar                                                         # a1: on
                        for _ in range(10):
                            ns += ["down", "wait:2"]
                        ns += ar                                                                         # a2: scrolled
                        ns += clock(30100) + ["wait:2"] + ar                                           # a3: 66 ms
                        ns += clock(30300) + ["wait:2"] + ar                                           # a4: 200 ms
                        ns += ["down", "wait:2"] + clock(30400) + ["wait:2"] + ar                   # a5: 66 ms
                        ns += clock(30700) + ["wait:2"] + ar                                           # a6: 200 ms
                        ns += fy + ar                                                                    # a7: off
                        ns += fy + ["no", "wait:4", "no", "wait:4", "no", "wait:4"] + ar          # a8: on, closed
                        ns += [mem(lay["smp_fb_open"])]
                    njs = work / "drivenav.json"
                    n_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                             "--snapshot", snap, "--steps", ",".join(ns), "--png-dir", work / "drivenav", "--json", njs]

                    def n_body(tdir):
                        rc, out = run("+drive keys, names", n_cmd, logs, env=EMU_ENV, trace=tdir)
                        why, good = out[-800:], False
                        if rc == 0 and njs.exists():
                            m = json.loads(njs.read_text())["memory"]

                            def at(va, i):          # the I-th read of VA
                                ks = [k for k in m if k == hex(va) or k.startswith(hex(va) + "@")]
                                return m[ks[i]] if i < len(ks) else None

                            def i32(va, i):
                                v = at(va, i)
                                return None if v is None else int.from_bytes(bytes.fromhex(v), "big", signed=True)

                            def rows(i):
                                v = at(rt, i)
                                b = bytes.fromhex(v) if v else bytes(144)
                                return [b[24 * r:24 * r + 24].split(b"\0")[0].decode("ascii", "replace") for r in range(6)]
                            ticks = [i32(TICK, i) for i in range(23)]
                            curs = [i32(cur, i) for i in range(23)]
                            offs = [i32(mq, i) for i in range(23)]
                            r0 = rows(0)

                            W = 21                         # (smp_page.c's FB_W)

                            def ht(nm):                    # head...tail: ten, "...", eight
                                return nm[:10] + "..." + nm[-8:]
                            sel = curs[3]                  # the hi-hat held DOWN stopped on: hh[sel - 1]
                            mq_rows = [rows(i) for i in range(3, 20)]          # (0: let go; 1..16: the marquee)
                            name = hh[sel - 1] if sel and 1 <= sel <= 16 else ""
                            seen = {r for rs in mq_rows for r in rs}
                            top = max(0, min(sel - 2, 17 - 6)) if sel else 0
                            after = rows(20)
                            ntop = max(0, min(curs[20] - 2, 17 - 6)) if curs[20] is not None else 0
                            end = len(name) - W
                            # (selected at tick 1000: a second's rest (1500 ticks), a character each 300 to
                            # its end, a second's rest, then from the start again)

                            def mq_want(t):
                                u = (t - 1000) % (3000 + 300 * end)
                                return 0 if u < 1500 else min(end, (u - 1500) // 300)
                            want = [mq_want(t) for t in MQT]
                            facts = {
                                "a short name whole, its .WAV dropped": r0[0] == "SHORT ONE",
                                "an unselected long name head...tail (\"AT BIRDHOU...D VEL 00\")": r0[1] == ht(hh[0]) and r0[2] == ht(hh[1]),
                                "held DOWN steps on by itself (a press and three repeats)": curs[1] == 4,
                                "let go, it stops": curs[2] == curs[3] == curs[1],
                                "the selected long name starts from its start": bool(name) and mq_rows[1][sel - top] == name[:W],
                                "it scrolls on to its end, a character each 0.2 s, and starts again": offs[4:20] == want
                                and end == 12 and max(want) == end and want[-1] > 0 and 0 in want[want.index(end):]
                                and any(r == name[-W:] for r in mq_rows[1 + want.index(end)]),
                                "only the selected row scrolls": all(r == ht(hh[top + j - 1]) for rs in mq_rows
                                                                     for j, r in enumerate(rs) if top + j != sel and top + j >= 1)
                                and all(rs[sel - top] == name[o:o + W] for rs, o in zip(mq_rows[1:], want)),
                                "DOWN: the next": curs[20] == sel + 1,
                                "moved off: head...tail again": after[sel - ntop] == ht(hh[sel - 1]),
                                "the new one from its start": after[curs[20] - ntop] == hh[curs[20] - 1][:W] and offs[20] == 0,
                                "FUNC + DOWN: a page": curs[21] == min(curs[20] + 6, 16),
                                "a knob pushed in: a page a detent (two)": curs[22] == 12,
                                "D pushed: +DRIVE still up, in its folder": int(m[hex(lay["smp_fb_open"])], 16) == 1
                                and int(m[hex(lay["smp_fb_store"])], 16) == 1 and int(m[hex(lay["smp_fb_folder"])], 16) == 2,
                                "held DOWN in the action menu steps on": i32(mcur, 0) == 4 and int(at(lay["smp_fb_menu"], 0), 16) == 1,
                                "NO: out of the menu, then up a level": i32(lay["smp_fb_folder"], 1) == -1 and i32(lay["smp_fb_open"], 1) == 1}
                            jc = [i32(cur, jit0 + k) for k in range(1 + 12 + 6)]
                            jr = rows(jrt)
                            jit = jc[1:13]
                            facts.update({
                                "INCOMING: the user's six LC_FTR_ samples, the cursor on the first":
                                    jc[0] == 0 and jr[0].startswith("LC_FTR_100") and jr[1].startswith("LC_FTR_100"),
                                "an encoder jittering +1/-1, no key: the cursor moves once at most, then stays (v0.41)":
                                    None not in jit and max(jit) <= 1 and len(set(jit[1:])) == 1,
                                "turned by hand: a row a detent; turned back, the first detent back lost (v0.41)":
                                    None not in jc[13:] and jc[13:16] == [jit[-1] + 1, jit[-1] + 2, jit[-1] + 3]
                                    and jc[16:19] == [jit[-1] + 3, jit[-1] + 2, jit[-1] + 1]})
                            if auto:
                                a_ = [i32(A, i) for i in range(9)]
                                s_ = [i32(AS, i) for i in range(9)]
                                p_ = [i32(PV, i) for i in range(9)]
                                r_ = [i32(RT_, i) for i in range(9)]
                                l_ = [i32(LS_, i) for i in range(9)]
                                facts.update({
                                    "auto preview: FUNC + YES turns it on, the sample under the cursor plays at once":
                                        a_[0] == 0 and a_[1] == 1 and s_[1] == s_[0] + 1 and p_[1] in (1, 2, 3),
                                    "auto preview: ten DOWNs with no time passing start nothing": s_[2] == s_[1],
                                    "auto preview: 66 ms after the last move still nothing": s_[3] == s_[1],
                                    "auto preview: 200 ms after it, exactly one, playing": s_[4] == s_[1] + 1 and p_[4] in (1, 2, 3),
                                    "auto preview: one more DOWN: nothing at 66 ms, one at 200 ms": s_[5] == s_[4] and s_[6] == s_[4] + 1,
                                    "auto preview: FUNC + YES again: off, silent": a_[7] == 0 and p_[7] == 0 and s_[7] == s_[6],
                                    "auto preview: on, then the browser closed: off": a_[8] == 0
                                        and int(at(lay["smp_fb_open"], 2) or "1", 16) == 0,
                                    "auto preview: the link stays healthy (no retries, the loader idle)":
                                        None not in r_ and r_[8] == r_[0] and l_[8] in (0, 4)})
                            good = all(bool(v) for v in facts.values())
                            why = f"{ {k: v for k, v in facts.items() if not v} } cur={curs} jitter={jc} jrows={jr} off={offs} ticks={ticks} rows0={r0} rows3={rows(3)} rows20={after}"
                        return good, ("held arrows repeat in the list and the action menu, FUNC + DOWN a page, a pushed "
                                      "knob a page a detent, D pushed keeps +DRIVE, NO goes up; long names head...tail, "
                                      "the selected one scrolls to its end and back, moved off it is head...tail again; an encoder jittering +1/-1 moves the cursor once at most (v0.41)"
                                      if good else why[:1500])
                    later("drivenav", "+DRIVE keys and long names (ColdFire)", "+DRIVE keys and long names (ColdFire)",
                          [n_cmd, sorted(EMU_ENV.items())], n_body)

        # 6h. v0.28: the Monomachine machines' pages drawn as the Monomachine's (each machine its
        # own screen, none the stock grid), and their choices' detents (SOPHIE's MODL since the
        # DPRO machines went, 2026-11-08; DPRO-WAVE's WPRS before: four detents a choice, through
        # smp_quant as the stock setter calls it)
        if "smp_quant" in lay:
            from dnfw.mnm import machines as MMx    # noqa: PLC0415
            from dnfw.perc import machines as PMx   # noqa: PLC0415
            kit = 0x4210D08C
            snd0 = kit + 52
            from dnfw.perc import live as PLx      # noqa: PLC0415
            # (2026-11-14, the 1.12 gate's blind spots: 20 M before the stock page's picture, about four UI passes:
            # 2 M held none on 1.12's snapshot, so no frame was composed; and a redraw asked after each poke, as
            # a type chosen in MACHINE SEL asks one: 1.12 redrew only on a change of page)
            st = ["wait:20", "png:stock"]
            for k, ty in enumerate(MMx.TYPES):       # 2026-11-11: MONOMACHINE on each engine (ENGN, page 1 H)
                st += [f"poke:{snd0 + 0xDE:#x}:{ty:02x}"]
                if MMx.NAMES[k] in MMx.MONO_ENGINES:
                    e = MMx.MONO_ENGINES.index(MMx.NAMES[k])
                    w = PLx.knob_word(MMx.mono_knob(e), PMx.PARAMS[7][3], PMx.PARAMS[7][2])
                    st += [f"poke:{snd0 + 0x14 + 2 * PMx.PARAMS[7][1]:#x}:{w:04x}"]
                st += [f"poke:{lay['smp_overlay_dirty']:#x}:00000001", "wait:20", f"png:m{k}"]
            wslot = PMx.PARAMS[7][1]             # SOPHIE's MODL: the eighth place (H, 2026-11-11)
            st += [f"poke:{snd0 + 0xDE:#x}:{MMx.TYPES[MMx.NAMES.index('SOPHIE')]:02x}",
                   f"poke:{snd0 + 0x14 + 2 * wslot:#x}:0000", "wait:4"]
            st += [f"call:{lay['smp_quant']:#x}:sound0:{wslot}:0x100"] * 4
            # v0.60 (zuzsw, Thos Grol on v0.59): the page each Monomachine type gets from the
            # stock page(type, 0) (1.11's 0x400c24ee upstream; 1.12's 0x400c2652 here, wr_page): its own
            # descriptor. v0.59's arithmetic gave FM+ STAT PAR's, PAR DYN's and DYN one past the table (the
            # sample machines' first: its knobs on ONESHOT's records, named "unused"). Ours: every type of
            # the Monomachine's places (CF_TYPES: FM+ 18..20, ours 50..55, the reserved ones), each its place's
            # descriptor, mnm_descriptors + 44 ASM_IX (the reserved types share one place, 2026-11-18)
            from dnfw.waverider import pages as WPx    # noqa: PLC0415
            from dnfw.waverider import coldfire as WCx  # noqa: PLC0415
            mdesc = lay["descriptors"] + 44 * len(WPx.PAGES)
            mp_types = tuple(MMx.CF_TYPES)
            mp_want = [mdesc + 44 * WPx.ASM_IX[WPx.MNM_KINDS.index(ty - 4)] for ty in mp_types]
            for ty in mp_types:
                st += [f"poke:{snd0 + 0xDE:#x}:{ty:02x}", "wait:4", f"call:{WCx.PAGE_SITE - 4:#x}:{ty}:0"]
            js = work / "mnmpages.json"
            mp_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", ",".join(st), "--png-dir", work / "mnmpages", "--json", js]

            def mp_body(tdir):
                rc, out = run("mnm pages", mp_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and js.exists():
                    r = json.loads(js.read_text())
                    shots = {n: pathlib.Path(r["screens"][n]).read_bytes() for n in r["screens"]}
                    pages = [shots[f"m{k}"] for k in range(len(MMx.TYPES))]
                    d0 = [c["d0"] for c in r["direct_calls"]]
                    lo, top = PMx.PARAMS[7][2], PMx.PARAMS[7][3]
                    n = len(MMx.MACHINES[MMx.NAMES.index("SOPHIE")].MNM.MODELS)
                    on = _mnm_rep(lo, top, n, 1) << 8
                    facts = {"each machine its own page, none the stock grid":
                             len(set(pages)) == len(pages) and shots["stock"] not in pages,
                             "MODL: three detents keep FUSE, the fourth gives STAK": d0[:4] == [0, 0, 0, on],
                             "each Monomachine type its own page record (FM+ and ours included; the reserved "
                             "types their shared place, v0.60)": d0[4:] == mp_want}
                    good = all(facts.values())
                    why = str(facts) + f" d0 {d0} want {mp_want}"
                return good, ("the Monomachine pages drawn, each its own; a choice control four detents a "
                              "choice; each type's page record its own (v0.60)" if good else why)
            later("mnmpages", "Monomachine pages and detents (ColdFire)", "Monomachine pages and detents (ColdFire)", [mp_cmd, sorted(EMU_ENV.items())], mp_body)

            # 6h2. v0.53 (owner: PLAY's four choices took too much turning): PLAY two detents a
            # choice, through smp_quant as the stock setter calls it (sound, slot 41, the value, its
            # record 254): an ONESHOT sound on FWD, one detent keeps FWD, the second gives FFWD loop
            # (32); MODE, a four-choice control too, keeps four (two detents: nothing)
            from dnfw.sampler import machines as SMq    # noqa: PLC0415
            pslot = SMq.RECORDS[SMq.PLAY_REC][0]
            mrec = SMq.MODE_REC
            mslot = SMq.RECORDS[mrec][0]
            pst = ["wait:2", f"poke:{snd0 + 0xDE:#x}:{SMq.TYPE_OF['ONESHOT']:02x}",
                   f"poke:{snd0 + 0x14 + 2 * pslot:#x}:0000", "wait:4"]
            pst += [f"call:{lay['smp_quant']:#x}:sound0:{pslot}:0x100:{SMq.PLAY_REC}"] * 2
            pst += [f"poke:{snd0 + 0xDE:#x}:{SMq.TYPE_OF['WERP']:02x}",
                    f"poke:{snd0 + 0x14 + 2 * mslot:#x}:0000", "wait:4"]
            pst += [f"call:{lay['smp_quant']:#x}:sound0:{mslot}:0x100:{mrec}"] * 2
            pjs = work / "playdet.json"
            pd_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", ",".join(pst), "--png-dir", work / "playdet", "--json", pjs]

            def pd_body(tdir):
                rc, out = run("play detents", pd_cmd, logs, env=EMU_ENV, trace=tdir)
                if rc != 0 or not pjs.exists():
                    return False, out[-800:]
                d0 = [c["d0"] for c in json.loads(pjs.read_text())["direct_calls"]]
                good = d0 == [0, 32 << 8, 0, 0]
                return good, ("PLAY: one detent keeps FWD, the second moves on (two a choice); MODE keeps four"
                              if good else f"d0 {d0}, want [0, {32 << 8}, 0, 0]")
            later("playdet", "PLAY two detents a choice (ColdFire)", "PLAY two detents a choice (ColdFire)",
                  [pd_cmd, sorted(EMU_ENV.items())], pd_body)

        # 6j. v0.30: a stock question's keys are stock's (a user's report: on a sample track, the
        # OS update's "UPGRADE OS NOW?" answered by our page; v0.29's save question), and a YES
        # with another key held (TRIG + YES) is stock's. On a GRID track's page: TRIG 1 held,
        # YES: no menu. FUNC + SETTINGS's SAVE ALL question (d0 forced at 0x4005f5c6: the
        # emulator's project was never saved, so stock offers the slot list instead) is seen
        # up (smp_question_up 1); its YES is the question's (it closes, no menu); back on the
        # page, YES opens the menu, NO closes it
        if "smp_question_up" in lay:
            kit = 0x4210D08C
            Q, H, S = lay["smp_question_up"], lay["smp_held_lo"], lay["slc_state"]
            # (2026-11-14, the 1.12 gate: stock's popups waited for by state, not time, whatever the snapshot's project
            # and card show: the project's per-slot write protection cleared (stock's own project, 0x4018e0a8; 1.12's
            # per-build snapshot holds the factory PRESETS, slot 0 protected, so the save said WRITE PROTECTED), a
            # further question (OVERWRITE '...'? when the card holds the project) answered YES, and each view
            # waited for: SAVING (0x4020734c) and the message after it (0x40207294, ERROR without a card)
            QV, PV, MV, PROJ = 0x4020671C, 0x4020734C, 0x40207294, 0x4018E0A8
            qs = (f"wait:3,poke-ret:{PROJ:#x}:0x1de79:00,poke:{kit + 52 + 0xDE:#x}:0c,wait:4,tap:2,wait:6,call:{Q:#x},"
                  f"press:25,wait:2,yes,"
                  f"wait:4,mem:{H:#x}:4,release:25,wait:6,mem:{S:#x}:4,mem:{H:#x}:4,press:17,wait:2,tap:8,"
                  f"wait:2,release:17,wait:20,png:q,call:{Q:#x},yes,wait:30,mem:{S:#x}:4,call:{Q:#x},"
                  f"yes-while:{QV:#x}:5,until-class:{MV:#x}:1:300,until-class:{MV:#x}:0:300,tap:2,"
                  f"wait:6,yes,wait:6,png:m,mem:{S:#x}:4,no,wait:6,mem:{S:#x}:4,"
                  # v0.41 (the owner, v0.40: "YES opens the slice menu, sometimes" while saving):
                  # FUNC + SETTINGS, YES, and a YES while SAVING is drawn (its view 0x4020734c at
                  # the list's end), then one on the message after it (0x40207294): both stock's,
                  # no menu; smp_question_up sees both up; the message's YES takes it down
                  f"press:17,wait:2,tap:8,wait:2,release:17,wait:20,yes,wait:3,yes-while:{QV:#x}:5,"
                  f"until-class:{PV:#x}:1:50,png:s,call:{Q:#x},yes,wait:3,"
                  f"mem:{S:#x}:4,until-class:{MV:#x}:1:300,png:e,call:{Q:#x},yes,wait:6,mem:{S:#x}:4,call:{Q:#x},"
                  f"until-class:{MV:#x}:0:300,call:{Q:#x},"
                  # 2026-11-14 (main): a slot write-protected (every slot's bit set): WRITE PROTECTED, the message a
                  # unit on the factory project shows. Measured in the emulator (1.12): YES does not take it down and
                  # opens no menu; it goes down by itself (about 210 M instructions)
                  f"poke-ret:{PROJ:#x}:0x1de79:{'ff' * 16},press:17,wait:2,tap:8,wait:2,release:17,wait:20,yes,"
                  f"until-class:{MV:#x}:1:100,png:w,call:{Q:#x},yes,wait:6,mem:{S:#x}:4,call:{Q:#x},"
                  f"until-class:{MV:#x}:0:300,call:{Q:#x}")
            qjs = work / "question.json"
            q_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--set-d0-at", "0x4005f5c6:0", "--steps", qs,
                     "--png-dir", work / "question", "--json", qjs]

            def q_body(tdir):
                rc, out = run("stock question", q_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and qjs.exists():
                    r = json.loads(qjs.read_text())
                    m = r["memory"]
                    d0 = [c["d0"] for c in r["direct_calls"]]
                    shots = {n: pathlib.Path(r["screens"][n]).read_bytes() for n in ("q", "m")}
                    d0 = d0 + [None] * (10 - len(d0))
                    facts = {"TRIG 1 held: seen held": m[hex(H)] == "02000000",
                             "TRIG 1 + YES: stock's, no menu": int(m[hex(S)], 16) == 0,
                             "let go: nothing held": m[f"{hex(H)}@2"] == "00000000",
                             # v0.41: after the question's YES the save's message is up (ERROR here:
                             # the emulator has no card), and it is a stock popup too, so the
                             # third probe reads 1 (0 on v0.30..v0.40, which saw only the question)
                             "the question seen up; then the save's message": d0[:3] == [0, 1, 1],
                             "its YES the question's: no menu": int(m[f"{hex(S)}@3"], 16) == 0,
                             "then YES on the page opens the menu, NO closes it":
                             int(m[f"{hex(S)}@4"], 16) != 0 and int(m[f"{hex(S)}@5"], 16) == 0,
                             "the question drawn": shots["q"] != shots["m"],
                             # v0.41
                             "SAVING seen up: YES on it is stock's, no menu": d0[3] == 1 and int(m[f"{hex(S)}@6"], 16) == 0,
                             # 2026-11-14 (main): upstream's snapshot has no card, so the message is ERROR, which
                             # its YES takes down. A unit has a card: the save is done and the message is DONE,
                             # which takes no key and goes by itself. Either way its YES opens no menu; a message
                             # its YES takes down is held to ERROR's form, one it does not must go by itself
                             "the message after it seen up: its YES opens no menu; it goes (ERROR: by that YES, "
                             "DONE: by itself)":
                             d0[4] == 1 and int(m[f"{hex(S)}@7"], 16) == 0 and (d0[5] == 0 or d0[6] == 0),
                             "WRITE PROTECTED seen up: its YES opens no menu; it goes by itself":
                             d0[7] == 1 and int(m[f"{hex(S)}@8"], 16) == 0 and d0[9] == 0}
                    good = all(facts.values())
                    why = f"{facts} d0={d0} mem={m}"
                return good, ("a stock question's YES is the question's; TRIG + YES is stock's; the page's "
                              "own YES still opens its menu; SAVING's and its message's keys are stock's, WRITE PROTECTED's too" if good else why)
            later("question", "stock questions and held keys (ColdFire)", "stock questions and held keys (ColdFire)", [q_cmd, sorted(EMU_ENV.items())], q_body)

        # 6k. v0.30: MACHINE SEL from one sample machine to another keeps SAMP (owner: the stock
        # commit resets the sound to the new machine's defaults, SAMP to OFF). Track 1 on
        # ONESHOT with SAMP 5; MACHINE SEL, DOWN, YES: the next sample machine, SAMP still 5
        if "smp_machine_commit" in lay:
            kit = 0x4210D08C
            sa, ty = kit + 52 + 20 + 2 * 43, kit + 52 + 0xDE
            ks = (f"wait:3,poke:{ty:#x}:08,poke:{sa:#x}:0500,wait:4,tap:2,wait:6,func-src,wait:20,down,wait:4,"
                  f"yes,wait:20,types,mem:{sa:#x}:2")
            kjs = work / "keepsamp.json"
            k_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--steps", ks, "--png-dir", work / "keepsamp", "--json", kjs]

            def k_body(tdir):
                rc, out = run("keep SAMP", k_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and kjs.exists():
                    r = json.loads(kjs.read_text())
                    m = r["memory"]
                    types = m.get("types@0") or [None]
                    facts = {"the next sample machine chosen": types[0] == 9,
                             "SAMP kept": m.get(hex(sa)) == "0500"}
                    good = all(facts.values())
                    why = f"{facts} types={types} mem={m}"
                return good, ("MACHINE SEL from ONESHOT to the next sample machine keeps SAMP" if good else why)
            later("keepsamp", "SAMP kept across sample machines (ColdFire)", "SAMP kept across sample machines (ColdFire)", [k_cmd, sorted(EMU_ENV.items())], k_body)

        # 6m. v0.32: FUNC + turn on our machines' controls (a tester's list; the owner: a control
        # that jumps with FUNC goes on jumping to its next value, one that does not stays put).
        # Stock's jump kept where it is right (PERC's first control, by octaves); a control of
        # choices steps one choice a click the way the knob turned; any other control of ours
        # stays where it was; nothing changes without FUNC, with a stale knob, or on a stock
        # machine. (The emulator's encoders do not move a stock page's value: the setter's own
        # call of smp_quant is made, the knob's last turn poked and its time copied from the UI
        # clock by the stock memcpy.)
        if "smp_knob_at" in lay:
            from dnfw.mnm import machines as MMf      # noqa: PLC0415
            from dnfw.perc import machines as PMf     # noqa: PLC0415
            from dnfw.sampler import machines as SMf  # noqa: PLC0415
            kit = 0x4210D08C
            snd0 = kit + 52
            clock, memcpy = 0x4058F8D4, 0x40134770
            ptch, other = PMf.PARAMS[0][1], PMf.PARAMS[2][1]
            # SOPHIE's MODL (seven choices) since DPRO-WAVE (its WPRS) went, 2026-11-08
            wprs, wlo, wtop = PMf.PARAMS[7][1], PMf.PARAMS[7][2], PMf.PARAMS[7][3]   # MODL on H (2026-11-11)
            n_modl = len(MMf.MACHINES[MMf.NAMES.index("SOPHIE")].MNM.MODELS)
            w_on = _mnm_rep(wlo, wtop, n_modl, 1)
            w_off = _mnm_rep(wlo, wtop, n_modl, 0)
            dwave = MMf.TYPES[MMf.NAMES.index("SOPHIE")]
            n_eng = len(MMf.MONO_ENGINES)                # 2026-11-11: MONOMACHINE's ENGN (page 1 H)
            e_0, e_1 = _mnm_rep(wlo, wtop, n_eng, 0), _mnm_rep(wlo, wtop, n_eng, 1)
            q = next(r for r in SMf.QUANT if r[1] == SMf.PLAY_REC and "ONESHOT" in r[0])
            play = SMf.RECORDS[SMf.PLAY_REC][0]
            p_from, p_to = q[3][0], q[3][1]

            rid = {sl: r for r, sl, _lo, _t in PMf.PARAMS}
            rid[play] = SMf.PLAY_REC
            lfo_rec, lfo_slot = 94, 60                # v0.33: an LFO record (stock's, LFO3's first)

            def fcase(ty, slot, old, held, knob, fresh, value):
                s = [f"poke:{snd0 + 0xDE:#x}:{ty:02x}", f"poke:{snd0 + 20 + 2 * slot:#x}:{old:04x}",
                     f"poke:{lay['smp_func_held']:#x}:{held:08x}",
                     f"poke:{lay['smp_knob_d']:#x}:{knob & 0xFFFFFFFF:08x}"]
                s += [f"call:{memcpy:#x}:{lay['smp_knob_at']:#x}:{clock:#x}:4"] if fresh else \
                     [f"poke:{lay['smp_knob_at']:#x}:80000000"]   # (half the clock away: stale)
                r = lfo_rec if slot == lfo_slot else rid[slot]       # (the setter passes the record: v0.33 reads it)
                return s + [f"call:{lay['smp_quant']:#x}:sound0:{slot}:{value:#x}:{r}"]
            cases = [("PERC's first control: stock's octave jump kept", (5, ptch, 0x4000, 1, 1, True, 0x4C00), 0x4C00),
                     ("PERC, another control: it stays put", (5, other, 0x2000, 1, 1, True, 0x7F00), 0x2000),
                     ("SOPHIE's MODL, right: the next choice in one click", (dwave, wprs, w_off << 8, 1, 1, True, 0x0000), w_on << 8),
                     ("SOPHIE's MODL, left: back in one click", (dwave, wprs, w_on << 8, 1, -1, True, 0x7F00), w_off << 8),
                     ("ONESHOT's PLAY, right: the next mode in one click", (8, play, p_from << 8, 1, 1, True, 0x0000), p_to << 8),
                     ("MONOMACHINE's ENGN, right: the next engine in one click",
                      (MMf.MONO_TYPE, wprs, e_0 << 8, 1, 1, True, 0x0000), e_1 << 8),
                     ("MONOMACHINE's ENGN, left: back in one click",
                      (MMf.MONO_TYPE, wprs, e_1 << 8, 1, -1, True, 0x7F00), e_0 << 8),
                     ("no FUNC: as it is", (5, other, 0x2000, 0, 1, True, 0x2100), 0x2100),
                     ("a stale knob: as it is", (5, other, 0x2000, 1, 1, False, 0x2100), 0x2100),
                     ("a stock machine: as it is", (1, other, 0x2000, 1, 1, True, 0x2100), 0x2100),
                     ("v0.33: an LFO control on PERC: stock's FUNC jump kept", (5, lfo_slot, 0x2000, 1, 1, True, 0x4000), 0x4000),
                     ("v0.33: an LFO control on a Monomachine track: stock's", (dwave, lfo_slot, 0x2000, 1, 1, True, 0x4000), 0x4000),
                     ("v0.33: an LFO control on ONESHOT: stock's", (8, lfo_slot, 0x2000, 1, 1, True, 0x4000), 0x4000)]
            # v0.66 (owner: FM+ DYN's FRQs "jump when func is held"): FUNC + turn on 1FRQ (x.x, 2 k/128)
            # and 2FRQ (x.xx, 4 (k/128)^2) goes to the next whole ratio the knob's way (knob 0, 64, 127;
            # 0, 64, 91, 111, 127), written as the record value nearest that knob (fmt.c mnm_val_for);
            # without FUNC both stay continuous
            dyn = MMf.TYPES[MMf.NAMES.index("FM+DYN")]

            def kn(j, v):
                lo, top = PMf.PARAMS[j][2], PMf.PARAMS[j][3]
                v = min(max(v - lo, 0), top)
                return (v * 254 + top) // (2 * top)

            def val_for(j, k_, t_, d_):
                lo, top = PMf.PARAMS[j][2], PMf.PARAMS[j][3]
                best, bd = -1, 1000
                for v in range(top + 1):
                    kv = (v * 254 + top) // (2 * top)
                    if (kv <= k_) if d_ > 0 else (kv >= k_):
                        continue
                    dd = abs(kv - t_)
                    if dd < bd or (dd == bd and d_ > 0):
                        bd, best = dd, v
                return lo + best

            def at_knob(j, k_):                       # a record value whose knob is K_
                lo, top = PMf.PARAMS[j][2], PMf.PARAMS[j][3]
                return next(lo + v for v in range(top + 1) if (v * 254 + top) // (2 * top) == k_)
            for j, nm, start, d_, tgt in ((0, "1FRQ", 30, 1, 64), (0, "1FRQ", 64, 1, 127), (0, "1FRQ", 30, -1, 0),
                                          (4, "2FRQ", 64, 1, 91), (4, "2FRQ", 91, 1, 111), (4, "2FRQ", 100, -1, 91),
                                          (4, "2FRQ", 127, 1, None)):
                old_v = at_knob(j, start)
                want = (old_v << 8) if tgt is None else (val_for(j, kn(j, old_v), tgt, d_) << 8)
                cases.append((f"v0.66: FM+ DYN {nm} at knob {start}, FUNC + turn {'right' if d_ > 0 else 'left'}: "
                              + ("stays at the end" if tgt is None else f"knob {tgt}"),
                              (dyn, PMf.PARAMS[j][1], old_v << 8, 1, d_, True, ((old_v + d_) & 0xFF) << 8), want))
            o1 = at_knob(0, 30)
            cases.append(("v0.66: FM+ DYN 1FRQ without FUNC: continuous, as it is",
                          (dyn, PMf.PARAMS[0][1], o1 << 8, 0, 1, True, (o1 + 1) << 8), (o1 + 1) << 8))
            fs = ["wait:3"]
            for _n, args, _w in cases:
                fs += fcase(*args)
            fs += [f"poke:{lay['smp_func_held']:#x}:00000000", f"poke:{snd0 + 0xDE:#x}:01", "wait:4"]
            fjs = work / "functurn.json"
            f_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--steps", ",".join(fs), "--png-dir", work / "functurn", "--json", fjs]

            def f_body(tdir):
                rc, out = run("FUNC + turn", f_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and fjs.exists():
                    calls = [c for c in json.loads(fjs.read_text())["direct_calls"]
                             if int(str(c.get("fn", "0")), 0) == lay["smp_quant"]]
                    got = [c["d0"] & 0xFFFF for c in calls]
                    facts = {n: (g == w) for (n, _a, w), g in zip(cases, got)}
                    good = len(got) == len(cases) and all(facts.values())
                    why = f"{facts} got={[hex(g) for g in got]}"
                return good, ("FUNC + turn: PERC's first control keeps stock's octave jumps; other controls of ours "
                              "stay put; choices step one a click either way (WPRS, PLAY); no change without FUNC, "
                              "with a stale knob, or on a stock machine" if good else why)
            later("functurn", "FUNC + turn (ColdFire)", "FUNC + turn (ColdFire)", [f_cmd, sorted(EMU_ENV.items())], f_body)

        # 6m2. v0.55 (owner: "add the recorded buffers (1-8) to the end of the project RAM list"):
        # SAMP on a sample machine goes on past 127 to the eight FLEX buffers (their codes,
        # BUF_SAMP0 + 2 b). The knob (the setter's own call of smp_quant, the knob's last turn
        # poked fresh): 127 -> B1, B1 -> B2, B1 -> 127, B8 held, 5 -> 6 and 122 -> 123 as before, a
        # stale knob as before. Knob D at 127 turned right by the panel's encoder (the stock knob
        # stops at the record's 127: smp_ui_pop takes it on): B1, the list up on it, naming the
        # buffer; DOWN B2, UP B1, UP 127 (smp_set_samp's write past the record, through smp_quant)
        if "rt_buf_code" in lay:
            from dnfw.sampler import machines as SMp   # noqa: PLC0415
            kit = 0x4210D08C
            snd0 = kit + 52
            samp0 = snd0 + 20 + 2 * 43
            clock, memcpy = 0x4058F8D4, 0x40134770
            srec = SMp.SAMP_REC
            b1, b2, b8 = SMp.BUF_SAMP0, SMp.BUF_SAMP0 + 2, SMp.BUF_SAMP0 + 14

            def pcase(ty, old, knob, fresh, value):
                q = [f"poke:{snd0 + 0xDE:#x}:{ty:02x}", f"poke:{samp0:#x}:{old:04x}",
                     f"poke:{lay['smp_knob_d']:#x}:{knob & 0xFFFFFFFF:08x}"]
                q += [f"call:{memcpy:#x}:{lay['smp_knob_at']:#x}:{clock:#x}:4"] if fresh else \
                     [f"poke:{lay['smp_knob_at']:#x}:80000000"]
                return q + [f"call:{lay['smp_quant']:#x}:sound0:43:{value:#x}:{srec}"]
            pcases = [("127, a detent right: B1", (8, 0x7F00, 1, True, 0x8000), b1 << 8),
                      ("B1, right: B2", (8, b1 << 8, 1, True, (b1 + 1) << 8), b2 << 8),
                      ("B1, left: 127", (8, b1 << 8, -1, True, (b1 - 1) << 8), 0x7F00),
                      ("B8, right: held", (8, b8 << 8, 1, True, (b8 + 1) << 8), b8 << 8),
                      ("STRETCH 127, right: B1", (10, 0x7F00, 1, True, 0x8000), b1 << 8),
                      ("5, right: 6 (as before)", (8, 0x0500, 1, True, 0x0600), 0x0600),
                      ("122, right: 123 (as before)", (8, 0x7A00, 1, True, 0x7B00), 0x7B00),
                      ("a stale knob: as it is", (8, 0x7F00, 1, False, 0x7F00), 0x7F00)]
            ps = ["wait:3"] + [f"poke:{kit + 52 + 1163 * t + 0xDE:#x}:08" for t in range(16)]
            for _n, args, _w in pcases:
                ps += pcase(*args)
            # the list and the pages, buffer 1 holding a take (its bytes poked), the others empty
            # (rt_on follows the pool's directory: smp_dir_ok set first, then the take's bytes)
            ps += [f"poke:{lay['smp_dir_ok']:#x}:00000001", "wait:4", f"poke:{lay['rt_play']:#x}:" + "00" * 8,
                   f"poke:{lay['rt_rbytes']:#x}:00001000" + "00000000" * 15,
                   f"poke:{snd0 + 0xDE:#x}:08", f"poke:{samp0:#x}:7f00", f"poke:{lay['smp_knob_at']:#x}:80000000",
                   "wait:6", "tap:2", "wait:10", "spin:3:1", "wait:10", "png:list_b1",
                   f"mem:{samp0:#x}:2", f"mem:{lay['smp_lst_open']:#x}:4",
                   "down", "wait:8", "png:list_b2", f"mem:{samp0:#x}:2",
                   "up", "wait:8", f"mem:{samp0:#x}:2", "up", "wait:8", f"mem:{samp0:#x}:2",
                   "no", "wait:8", f"poke:{lay['smp_samp_turned']:#x}:80000000",   # (no turn: the list stays shut)
                   f"poke:{samp0:#x}:{b1:02x}00", f"poke:{lay['smp_overlay_dirty']:#x}:00000001",
                   "wait:10", "png:page1_b1", "tap:2", "wait:10", "png:page2_b1",
                   f"poke:{samp0:#x}:{b2:02x}00", f"poke:{lay['smp_overlay_dirty']:#x}:00000001", "wait:10",
                   "png:page2_b2", f"mem:{lay['rt_on']:#x}:4", f"mem:{lay['rt_rbytes']:#x}:4",
                   f"poke:{snd0 + 0xDE:#x}:01", "wait:4"]
            pjs = work / "flexpool.json"
            p_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--steps", ",".join(ps), "--png-dir", work / "flexpool", "--json", pjs]

            def p_body(tdir):
                rc, out = run("FLEX buffers in the list", p_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and pjs.exists():
                    r = json.loads(pjs.read_text())
                    calls = [c for c in r["direct_calls"] if int(str(c.get("fn", "0")), 0) == lay["smp_quant"]]
                    got = [c["d0"] & 0xFFFF for c in calls]
                    facts = {n: (g == w) for (n, _a, w), g in zip(pcases, got)}
                    m = r["memory"]
                    lo, sp = hex(lay["smp_lst_open"]), hex(samp0)
                    sh = {n: pathlib.Path(r["screens"][n]).read_bytes() if n in r["screens"] else b""
                          for n in ("list_b1", "list_b2", "page1_b1", "page2_b1", "page2_b2")}
                    facts["knob D at 127, a detent right (the panel's encoder): B1, the list up on it"] = \
                        m.get(sp) == f"{b1:02x}00" and int(m.get(lo, "0"), 16) == 1
                    facts["DOWN: B2, UP: B1, UP: 127"] = [m.get(f"{sp}@2"), m.get(f"{sp}@3"), m.get(f"{sp}@4")] == \
                        [f"{b2:02x}00", f"{b1:02x}00", "7f00"]
                    facts["each view drawn, B1 and B2 told apart (FLEX BUF 1 holding its take, FLEX EMPTY 2)"] = \
                        all(sh.values()) and len(set(sh.values())) == 5 and \
                        m.get(hex(lay["rt_on"])) == "00000001" and m.get(hex(lay["rt_rbytes"])) == "00001000"
                    good = len(got) == len(pcases) and all(facts.values())
                    why = f"{facts} got={[hex(g) for g in got]} mem={m}"
                return good, ("SAMP past 127 to the FLEX buffers B1..B8 by the knob and in the list, as before "
                              "below; a stale knob as before; the list and both pages name the buffer" if good else why)
            later("flexpool", "FLEX buffers in every sample machine's SAMP (ColdFire)",
                  "FLEX buffers in every sample machine's SAMP (ColdFire)", [p_cmd, sorted(EMU_ENV.items())], p_body)

        # 6n. v0.32: the DSP load meter. smp_dsp_load gives the last half second's peak (the
        # idle packets' unit 18, permille) in percent, rounded, and -1 when none came in the last
        # second; v0.32..v0.43 a PERC page with FUNC held drew it in the tempo's place, v0.44 the
        # system meter draws it (D, with C and H) in the title bar's corner on every page
        # 2026-11-19 (the User: "could the cpu/dsp/memory meters be bigger, and only come on double click + hold (or one
        # click and a half) on the FUNC button?"): the meter is up only while FUNC, tapped and pressed again within
        # 0.35 s, is held, over the page body. The emulator's frame clock stands still: each press is timed by FRAMES
        # poked (FUNC's items are read at once). On SYN (stock's FUNC hold changes nothing there, measured on 1.12):
        # FUNC held alone and a slow double tap (1,000 frames) draw nothing; tap + hold 300 frames apart draws the
        # meter, and its release the page as before; FUNC + SRC with it up is a plain FUNC + SRC (MACHINE SEL) and the
        # meter is gone at the SRC press
        if "smp_dsp_load" in lay:
            fr = lambda v: f"poke:0x4058f8d4:{v:08x}"                     # noqa: E731  FRAMES
            mb = lay.get("mtr_big", lay["smp_func_held"])                 # (a build without it fails "the build has")
            rd = f"mem:{mb:#x}:4"

            def gesture(t, gap):                                          # the old one (FUNC tap + hold): nothing now
                return [fr(t), "press:17", "release:17", fr(t + gap), "press:17", "wait:30"]
            tk = lambda v: f"poke:0x466768b0:{v:08x}"                     # noqa: E731  the panel tick (ovw.c's clock)
            # 2026-11-21 (the User: "on a long press of the METRONOME button and not FUNC click-and-hold"): [TEMPO]
            # (code 9) held a second (the panel tick moved past ovw.c's 121), the meter; its release dropped (no TEMPO
            # screen); FUNC's gesture shows nothing now
            ms = ["wait:3", "tap:2", "wait:150",
                  f"poke:{lay['smp_load_peak']:#x}:00000274",                  # 628 permille
                  # (the emulator runs no audio periods: the clock and the packet's time are set)
                  f"poke:{lay['smp_periods']:#x}:00001000", f"poke:{lay['smp_load_seen']:#x}:00000fff",
                  f"call:{lay['smp_dsp_load']:#x}",
                  "tap:2", "wait:150", "png:base",
                  fr(0x100000), "press:17", "wait:30", "png:hold", rd, "release:17", "wait:20",       # FUNC held alone
                  *gesture(0x110000, 1000), "png:slow", rd, "release:17", "wait:20",                 # a slow double tap
                  *gesture(0x120000, 300), "png:old", rd, "release:17", "wait:20",                   # the old tap + hold
                  tk(0x100), "press:9", "wait:5", tk(0x190), "wait:30", "png:big", rd,             # [TEMPO] held 1.2 s
                  "release:9", "wait:30", "png:after", rd,
                  f"poke:{lay['smp_load_seen']:#x}:00000000",
                  f"call:{lay['smp_dsp_load']:#x}", "wait:4"]
            mjs = work / "meter.json"
            m_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--steps", ",".join(ms), "--png-dir", work / "meter", "--json", mjs]

            def m_body(tdir):
                rc, out = run("load meter", m_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and mjs.exists():
                    r = json.loads(mjs.read_text())
                    d0 = [c["d0"] for c in r["direct_calls"] if int(str(c["fn"]), 0) == lay["smp_dsp_load"]]
                    shots = {k: pathlib.Path(v).read_bytes() for k, v in r["screens"].items()}
                    ups = [int(v, 16) for k, v in r.get("memory", {}).items() if k.split("@")[0] == f"{mb:#x}"]
                    facts = {"628 permille reads 63 %": d0[:1] == [63],
                             "none in the last second reads -1": d0[1:2] == [-1],
                             "the build has the big meter (mtr_big)": "mtr_big" in lay,
                             "FUNC held alone: no meter, the page as it was": ups[0:1] == [0]
                             and shots.get("hold") == shots.get("base"),
                             "a slow double tap (1,000 frames): no meter": ups[1:2] == [0]
                             and shots.get("slow") == shots.get("base"),
                             "FUNC tapped then held (the old gesture): no meter now": ups[2:3] == [0]
                             and shots.get("old") == shots.get("base"),
                             "[TEMPO] held a second: the meter over the page": ups[3:4] == [1]
                             and shots.get("big") != shots.get("base"),
                             "let go: the page as before it (the release dropped: no TEMPO screen)":
                             ups[4:5] == [0] and shots.get("after") == shots.get("base")}
                    good = len(d0) == 2 and all(facts.values())
                    why = f"{facts} d0={d0} mtr_big={ups}"
                return good, ("the DSP load meter: the half second's peak in percent, none when the DSP is "
                              "silent; the system meter on [TEMPO] held a second (not FUNC's old gesture), gone "
                              "at its release with no TEMPO screen" if good else why)
            later("meter", "DSP load meter (ColdFire)", "DSP load meter (ColdFire)", [m_cmd, sorted(EMU_ENV.items())], m_body)

        # 6n2. 2026-11-17 (the User): FX acts on its release; held a second, every track's two insert slots on one screen
        # (csrc/inserts/ovw.c). scripts/emu_ins_overview.py: the tap on the release, stock's value view while held,
        # all 32 slots against dnfw.inserts.overview pixel for pixel, a FULL XDLY, another key closing it, FUNC + FX
        # stock's, no fault
        if "ovw_up" in lay:
            ow = work / "insovw"
            o_cmd = [a.venv, "-u", "scripts/emu_ins_overview.py", "--venv", a.venv, "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--work", ow]

            def o_body(tdir):
                rc, out = run("inserts overview", o_cmd, logs, env=EMU_ENV, trace=tdir)
                good = rc == 0 and "OVERVIEW OK" in out
                return good, ("FX on its release; held a second, the overview, every slot as the model; another key "
                              "closes it; FUNC + FX stock's; a distortion picked with AUTO OFF, FUNC + long push G "
                              "resets AUTO to OFF (2026-11-19)" if good else out[-900:])
            later("insovw", "FX on its release, the inserts overview held a second (ColdFire)",
                  "FX on its release, the inserts overview held a second (ColdFire)", [o_cmd, sorted(EMU_ENV.items())], o_body)

        # 6n3. 2026-11-17 (the User: "lets try them all, we can revert what we dont like"): SYN, FLTR, MOD and AMP held a
        # second show their overviews (csrc/inserts/ovw.c, ovw_draw.c). scripts/emu_overviews.py: each key's tap steps on
        # its release and a 0.5 s hold shows stock's values with no step (stock's behaviour, untouched), held 1.3 s the
        # overview pixel for pixel dnfw.overviews with the data read back from RAM, closed on the release with no step,
        # another key closing it, the redraws alone over the glass, no fault. 2026-11-19: VOICE's too
        # (scripts/emu_voice_overview.py, run by emu_overviews.py)
        if "ovw_alone" in lay:
            vw = work / "overviews"
            v_cmd = [a.venv, "-u", "scripts/emu_overviews.py", "--venv", a.venv, "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--work", vw]

            def v_body(tdir):
                rc, out = run("page key overviews", v_cmd, logs, env=EMU_ENV, trace=tdir)
                good = rc == 0 and "OVERVIEWS OK" in out
                return good, ("SYN, FLTR, MOD, AMP, VOICE: taps, value views and the VOICE menu as stock; held a second, "
                              "each overview as the model; closed on the release, no step" if good else out[-900:])
            v_what = ("SYN, FLTR, MOD, AMP, VOICE held a second: their overviews; taps, value views and the VOICE menu as "
                      "stock (ColdFire)")
            later("overviews", v_what, v_what, [v_cmd, sorted(EMU_ENV.items())], v_body)

        # 6n3b. 2026-11-20 (the User: "UP/DOWN should page through the pages of AMP and FX ... like any other pages"):
        # csrc/scope/scope.c amp_arrow, csrc/inserts/ins.c fx_arrow. scripts/emu_updown_pages.py: on every page key's
        # pages (TRIG SYN FLTR MOD AMP FX and FUNC + FX's send pages) DOWN steps to the last page and stays, UP back to
        # page 1 and stays, a held DOWN's repeats step, FUNC + DOWN steps nothing, a trig held / KEYBOARD on / grid
        # recording step as without (stock 1.12's rule on its own pages, measured); on AMP and FX each step leaves the
        # glass the page key leaves; a routes popup up takes the arrows
        if "amp_sub" in lay and "ins_up" in lay:
            ud_work = work / "updown"
            ud_cmd = [a.venv, "-u", "scripts/emu_updown_pages.py", "--build", a.build, "--snapshot", snap,
                      "--work", ud_work]

            def ud_body(tdir):
                rc, out = run("updown pages", ud_cmd, logs, env=EMU_ENV, trace=tdir)
                good = rc == 0 and "UPDOWN OK" in out
                return good, ("UP / DOWN step AMP's and FX's pages as stock steps its own (stop at the ends, repeats, "
                              "not with FUNC; a trig held, KEYBOARD, grid recording alike), each step the page key's "
                              "glass; stock's pages and the send pages unchanged; a popup of ours keeps the arrows"
                              if good else "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:])
            ud_what = "UP / DOWN page through AMP's and FX's pages as stock's own pages; stock's pages unchanged (ColdFire)"
            later("updown", ud_what, ud_what, [ud_cmd, sorted(EMU_ENV.items())], ud_body)

        # 6n2. 2026-11-17 (the User, v0.57.1 on the User's DN2: "creating / initialising a new project shows an error popup").
        # Measured on the unit: no stock ERROR; the box was our meter's "!CPU" label. Stock's project work (a LOAD,
        # the working-copy write after it, INIT NEW, SAVE) runs in its file worker, the one prio-2 task, which runs
        # only when every other task waits; the meter counted it as load (csrc/meter/hooks.S). Through the panel:
        # SETTINGS > PROJECT > LOAD PROJECT > CREATE NEW, then MANAGE PROJECTS > slot 002 > INIT NEW. Fails on any
        # ERROR from stock's SUCCESS/ERROR popup (0x4009ea1c, its result in d2 at 0x4009ea2c), on a fault, when INIT
        # NEW writes nothing, and when a switch into the worker does not open the meter's idle interval (MTR_I_ON)
        # or the worker never ran (the emulator models no DMA timer, so the meter's figure itself cannot be read)
        if "mtr_switch" in lay:
            ns = ("wait:3,tap:8,wait:20,yes,wait:20,yes,wait:30,down,wait:6,yes,wait:150,png:created,"
                  "no,wait:10,no,wait:10,no,wait:10,tap:8,wait:20,yes,wait:20,down,down,yes,wait:30,down,wait:6,yes,"
                  "wait:20,right,wait:20,png:menu,yes,wait:150,png:inited")
            njs = work / "newproj.json"
            n_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--steps", ns, "--switch-watch", "--regs-at", "0x4009ea2c",
                     "--regs-at", "0x4012ca74", "--regs-last", "400", "--png-dir", work / "newproj", "--json", njs]

            def n_body(tdir):
                rc, out = run("new project", n_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and njs.exists():
                    r = json.loads(njs.read_text())
                    results = [int(x["D2"], 16) for x in r["regs_at"].get("0x4009ea2c", [])]
                    writes = len(r["regs_at"].get("0x4012ca74", []))
                    sw = r["switch_watch"]
                    shots = {k: pathlib.Path(v).read_bytes() for k, v in r["screens"].items()}
                    facts = {"CREATE NEW: stock's popup once, SUCCESS (result 0)": results == [0],
                             "INIT NEW writes the slot (more than 100 +Drive writes in all)": writes > 100,
                             "INIT NEW changes the list": shots.get("menu") != shots.get("inited"),
                             "no fault": not r["faults"],
                             "the file worker (prio 2) ran": sw["into_worker"] > 0,
                             "every switch into it opened the meter's idle interval": sw["opened"] == sw["into_worker"]}
                    good = all(facts.values())
                    why = f"{facts} results={results} writes={writes} switch_watch={sw}"
                return good, ("a new project through LOAD's CREATE NEW and MANAGE's INIT NEW: SUCCESS, no ERROR, no "
                              "fault; stock's file worker counted as idle by the meter (no !CPU from its work)"
                              if good else why)
            later("newproj", "new project (ColdFire)", "new project (ColdFire)", [n_cmd, sorted(EMU_ENV.items())], n_body)

        # 6o. v0.33: MACHINE SEL to a Monomachine machine gives it its own start (dnfw.mnm's
        # DEFAULTS: SID on PULS, PW at the middle), not the shared records' defaults. A real
        # MACHINE SEL first (6k's: ONESHOT to the next sample machine; its commit's arguments
        # kept), then the commit called again for track 1 to SOPHIE (SID until 2026-11-08): its
        # eight records' words
        if "smp_machine_commit" in lay:
            from dnfw.mnm import machines as MMo     # noqa: PLC0415
            from dnfw.perc import machines as PMo    # noqa: PLC0415
            from dnfw.perc import live as PLo        # noqa: PLC0415
            kit = 0x4210D08C
            snd0 = kit + 52
            sa, ty = snd0 + 20 + 2 * 43, snd0 + 0xDE
            sid = MMo.TYPES[MMo.NAMES.index("SOPHIE")]
            cm = lay["smp_machine_commit"]
            want = [PLo.knob_word(x, top, lo) for (_r, _s, lo, top), x in zip(PMo.PARAMS, MMo.DEFAULTS["SOPHIE"])]
            os_ = (f"wait:3,poke:{ty:#x}:08,poke:{sa:#x}:0500,wait:4,tap:2,wait:6,func-src,wait:20,down,wait:4,"
                   f"yes,wait:20,call:{cm:#x}:arg1@{cm:#x}:0:{sid}:arg4@{cm:#x}:arg5@{cm:#x},wait:10,types,"
                   + ",".join(f"mem:{snd0 + 20 + 2 * sl:#x}:2" for _r, sl, _lo, _t in PMo.PARAMS))
            # 2026-11-11: MONOMACHINE's own start (its first engine's, ENGN on it), and an engine change's: ENGN
            # turned by the setter (smp_quant, then its value written as the setter writes it) to the third engine
            # gives that engine's start, ENGN as turned (rec.c mono_poll, from the UI's poll)
            from dnfw.perc import program as PPo     # noqa: PLC0415
            mono_slots = [sl for _r, sl, _lo, _t in PMo.PARAMS] + [PPo.MONO_TUNE_REC[1]]
            e_slot, e_rid = PMo.PARAMS[7][1], PMo.PARAMS[7][0]
            e2 = MMo.MONO_ENGINES[2]
            e2_word = _mnm_rep(PMo.PARAMS[7][2], PMo.PARAMS[7][3], len(MMo.MONO_ENGINES), 2) << 8
            mono_want = [PLo.mnm_slot_words(MMo.NAMES.index(n), MMo.DEFAULTS[n])
                         for n in (MMo.MONO_ENGINES[0], e2)]
            mono_want[1][e_slot] = e2_word
            mono_want = [[w[sl] for sl in mono_slots] for w in mono_want]
            mono_m = ",".join(f"mem:{snd0 + 20 + 2 * sl:#x}:2" for sl in mono_slots)
            from dnfw.waverider import pages as WPo  # noqa: PLC0415
            mono_first = MMo.CF_ALL[MMo.CF_MONO]
            mono_recs = [next(r for r in WPo.MNM_RECS if r[1] == sl) for sl in mono_slots]

            def mono_view(i, w):
                """slot i's word as the page reads it on the first engine: a choice's index, else the word"""
                _r, _sl, lo, top = mono_recs[i]
                n = WPo._choices(mono_first).get(WPo.mnm_pnames(mono_first)[WPo.MNM_RECS.index(mono_recs[i])], 0)
                if not n:
                    return ("w", w)
                v = min(max((w >> 8) - lo, 0), top)
                k = (v * 254 + top) // (2 * top)
                if n == "pch":
                    return ("c", WPo._pch_names()[0][k])
                n = n if isinstance(n, int) else len(n)
                return ("c", (k * n) >> 7)
            os_ += (f",call:{cm:#x}:arg1@{cm:#x}:0:{MMo.MONO_TYPE}:arg4@{cm:#x}:arg5@{cm:#x},wait:10,types,{mono_m},"
                    f"call:{lay['smp_quant']:#x}:sound0:{e_slot}:{e2_word:#x}:{e_rid},"
                    f"poke:{snd0 + 20 + 2 * e_slot:#x}:{e2_word:04x},wait:10,{mono_m}")
            # 2026-11-20 (the table of hosts): DRUM the same by TYPE: MACHINE SEL to DRUM starts KICK's place (both
            # pages), TYPE turned to SNAR (the setter, then its word written) starts SNARE's place, TYPE as turned
            drum_h = MMo.HOST_BY_NAME.get("DRUM")
            drum_slots = [sl for _r, sl, _lo, _t in WPo.MNM_RECS[:16]]
            drum_m = ",".join(f"mem:{snd0 + 20 + 2 * sl:#x}:2" for sl in drum_slots)
            if drum_h is not None:
                d_places = [MMo.CF_ALL[i] for i in MMo.CF_HOST_PLACES["DRUM"]]
                d_lo, d_top = WPo.MNM_RECS[drum_h.J][2:4]
                d1_word = _mnm_rep(d_lo, d_top, len(d_places), 1) << 8
                drum_want = [WPo.mnm_default_words(P.DEFAULTS, P)[:16] for P in d_places[:2]]
                drum_want[1][drum_h.J] = d1_word
                os_ += (f",call:{cm:#x}:arg1@{cm:#x}:0:{drum_h.TYPE}:arg4@{cm:#x}:arg5@{cm:#x},wait:10,types,{drum_m},"
                        f"call:{lay['smp_quant']:#x}:sound0:{e_slot}:{d1_word:#x}:{e_rid},"
                        f"poke:{snd0 + 20 + 2 * e_slot:#x}:{d1_word:04x},wait:10,{drum_m}")

            def drum_view(j, w):
                """control j's word on DRUM KICK's page: a choice's index, else the word"""
                P = MMo.CF_ALL[MMo.CF_HOST_PLACES["DRUM"][0]]
                _r, _sl, lo, top = WPo.MNM_RECS[j]
                n = WPo._choices(P).get(WPo.mnm_pnames(P)[j], 0)
                if not n:
                    return ("w", w)
                v = min(max((w >> 8) - lo, 0), top)
                return ("c", ((v * 254 + top) // (2 * top) * (n if isinstance(n, int) else len(n))) >> 7)
            ojs = work / "mnmdefaults.json"
            o_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--args-at", hex(cm), "--steps", os_, "--png-dir", work / "mnmdefaults",
                     "--json", ojs]

            def o_body(tdir):
                rc, out = run("mnm defaults", o_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and ojs.exists():
                    m = json.loads(ojs.read_text())["memory"]
                    types = m.get("types@0") or [None]
                    got = [int(m.get(f"{snd0 + 20 + 2 * sl:#x}", "0") or "0", 16) for _r, sl, _lo, _t in PMo.PARAMS]
                    facts = {"track 1 is SOPHIE": types[0] == sid, "its eight controls at SOPHIE's own start": got == want}
                    # 2026-11-11: after SOPHIE's (types, eight reads), MONOMACHINE's commit (types, nine reads) and its
                    # engine change (nine reads), in the order read
                    vals = list(m.values())
                    k0 = 1 + len(PMo.PARAMS)
                    types1 = vals[k0] if len(vals) > k0 and isinstance(vals[k0], list) else [None]
                    nine = len(mono_slots)
                    mono_got = [[int(str(v or "0"), 16) for v in vals[k0 + 1 + nine * i:k0 + 1 + nine * (i + 1)]]
                                for i in (0, 1)]
                    facts["track 1 is MONOMACHINE"] = types1[0] == MMo.MONO_TYPE
                    # (MACHINE SEL writes through the setter, whose smp_quant snaps a choice to the middle of its span:
                    # a choice control is held to its choice, as the page reads it; every other word exactly)
                    facts["MONOMACHINE starts on its first engine, at that engine's start (TUNE on page 2 H)"] = \
                        [mono_view(j, w) for j, w in enumerate(mono_got[0])] == \
                        [mono_view(j, w) for j, w in enumerate(mono_want[0])]
                    facts[f"ENGN turned to {e2}: {e2}'s start, ENGN as turned"] = mono_got[1] == mono_want[1]
                    if drum_h is not None:              # 2026-11-20: DRUM's commit (types, 16 reads), TYPE turned (16)
                        k1 = k0 + 1 + 2 * nine
                        types2 = vals[k1] if len(vals) > k1 and isinstance(vals[k1], list) else [None]
                        sixteen = len(drum_slots)
                        drum_got = [[int(str(v or "0"), 16) for v in vals[k1 + 1 + sixteen * i:k1 + 1 + sixteen * (i + 1)]]
                                    for i in (0, 1)]
                        facts["track 1 is DRUM"] = types2[0] == drum_h.TYPE
                        facts["DRUM starts on KICK, at KICK's start (both pages)"] = \
                            [drum_view(j, w) for j, w in enumerate(drum_got[0])] == \
                            [drum_view(j, w) for j, w in enumerate(drum_want[0])]
                        facts["TYPE turned to SNAR: SNARE's start (both pages), TYPE as turned"] = \
                            drum_got[1] == drum_want[1]
                        why_d = (f" drum got={[[hex(g) for g in r] for r in drum_got]}"
                                 f" want={[[hex(w) for w in r] for r in drum_want]} types={types2}")
                    else:
                        why_d = ""
                    good = all(facts.values())
                    why = (f"{facts} got={[hex(g) for g in got]} want={[hex(w) for w in want]} types={types}"
                           f" mono got={[[hex(g) for g in r] for r in mono_got]}"
                           f" want={[[hex(w) for w in r] for r in mono_want]} types={types1}" + why_d)
                return good, ("MACHINE SEL to SOPHIE: its eight controls at its own start (the factory snare); to "
                              "MONOMACHINE: its first engine's; ENGN turned: the new engine's start"
                              + ("; to DRUM: KICK's; TYPE turned: SNARE's start" if drum_h is not None else "")
                              if good else why)
            later("mnmdefaults", "Monomachine start values (ColdFire)", "Monomachine start values (ColdFire)", [o_cmd, sorted(EMU_ENV.items())], o_body)

        # 6p. v0.33: our overlays let go when the page under them goes (docs/freeze-hunt.md).
        # The sample list opened on track 1 (a SAMP turn), then TRK + [TRIG 2] to track 2, a
        # stock machine: the next UP is not the list's (it closes); then MACHINE SEL in and
        # out (FUNC + SRC, NO), and YES on a SLICE track's page still answers (its menu, or
        # NO SAMPLE ON SAMP)
        if "smp_lst_open" in lay and "smp_held_lo" in lay:
            from dnfw.sampler import machines as SMp    # noqa: PLC0415
            kit = 0x4210D08C
            snd0, snd1 = kit + 52, kit + 52 + 1163
            srec = SMp.RECORDS[SMp.SAMP_REC][0]
            lo_ = lay["smp_lst_open"]
            hs = [f"wait:3,poke:{snd0 + 0xDE:#x}:08,poke:{snd1 + 0xDE:#x}:00,poke:{snd0 + 0x6A:#x}:0200",
                  "wait:4,tap:2,wait:8",
                  f"call:{lay['smp_quant']:#x}:sound0:{srec}:{3 << 8:#x}:{SMp.SAMP_REC}",
                  f"poke:{snd0 + 0x6A:#x}:0300,poke:{lay['smp_overlay_dirty']:#x}:00000001,wait:10,png:h0,mem:{lo_:#x}:4",
                  "press:16,wait:2,press:26,wait:3,release:26,wait:2,release:16,wait:10,mem:0x42432a6c:1",
                  f"up,wait:6,mem:{lo_:#x}:4,png:h1",
                  "press:16,wait:2,press:25,wait:3,release:25,wait:2,release:16,wait:10",
                  f"poke:{snd0 + 0xDE:#x}:0d,poke:{snd0 + 0x6A:#x}:0000,wait:4,tap:2,wait:8",
                  "func-src,wait:20,no,wait:10,png:h2,yes,wait:8,png:h3"]
            hjs = work / "hooks.json"
            h_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--steps", ",".join(hs), "--png-dir", work / "hooks", "--json", hjs]

            def h_body(tdir):
                rc, out = run("hooks let go", h_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and hjs.exists():
                    r = json.loads(hjs.read_text())
                    m = r["memory"]
                    sh = {n: pathlib.Path(r["screens"][n]).read_bytes() for n in ("h2", "h3")}
                    facts = {"the list opens on track 1": int(m[hex(lo_)], 16) == 1,
                             "TRK + [TRIG 2]: track 2": int(m["0x42432a6c"], 16) == 1,
                             "UP there: the list closed, not taking it": int(m[f"{hex(lo_)}@2"], 16) == 0,
                             "after MACHINE SEL in and out, YES on a SLICE page answers": sh["h2"] != sh["h3"]}
                    good = all(facts.values())
                    why = f"{facts} mem={m}"
                return good, ("the sample list lets go when another track is active; YES on a SLICE page "
                              "answers after MACHINE SEL" if good else why)
            later("hooks", "overlays let go (ColdFire)", "overlays let go (ColdFire)", [h_cmd, sorted(EMU_ENV.items())], h_body)

        # 6r. v0.35: MACHINE SEL's columns (flupperich6l, v0.33: with a machine low in our long
        # SRC list chosen, RIGHT showed an empty FLTR column: stock's LEFT / RIGHT keeps the
        # list's top row, and stock's lists never scroll). Track 1 on WaveTone: MACHINE SEL,
        # nine DOWNs to GRID, YES, RIGHT: the FLTR column drawn with MULTI-MODE marked on its
        # first row; LEFT: GRID under the cursor again; RIGHT once more: the same column
        if "colsw" in lay:
            kit = 0x4210D08C
            ty = kit + 52 + 0xDE
            # (2026-11-14, the 1.12 gate: down to GRID's row as stock reads it, not nine rows: 1.11's gate snapshot
            # holds v0.14's MACHINE SEL rows, a 1.12 per-build one this build's (LIST_NEW), GRID further down)
            # (2026-11-14, ours: MACHINE SEL in two columns draws over stock's single column, so its page and the row
            # under its cursor are read from stock's own view; LIVE SELECT, on by default, closes it on YES (its "YES
            # keeps it and closes"), so this step turns LIVE SELECT off first, through set_flag_put as the PERSONALIZE
            # row does, and MACHINE SEL stays up after YES as stock's does: the v0.35 case it tests)
            ms = "msel_draw" in lay
            msr = (f",view:{MSEL_VT:#x}:{MSEL_PAGE}:4,view:{MSEL_VT:#x}:{MSEL_CURSOR}:4,"
                   f"call:{MSEL_ROW_TYPE:#x}:view@{MSEL_VT:#x}") if ms else ""
            live_off = f"call:{lay['set_flag_put']:#x}:4:1," if "ls_commits" in lay else ""
            rs = (f"wait:3,{live_off}poke:{ty:#x}:01,wait:4,tap:2,wait:6,func-src,wait:20,down-to:12,wait:3,"
                  + f"png:r0,yes,wait:20,right,wait:20,png:r1{msr},left,wait:20,png:r2{msr},right,wait:20,png:r3,types,"
                  # (2026-11-14: 300 M after NO and after SYN's release: stock shows the page's title a while after
                  # a key, then the pattern's name; both pictures are taken once the title has settled)
                  + "no,wait:300,png:v0,press:2,wait:30,png:v1,release:2,wait:300,png:v2")   # v0.35: SYN held (O14)
            rjs = work / "colsw.json"
            r_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                     "--snapshot", snap, "--steps", rs, "--png-dir", work / "colsw", "--json", rjs]

            def r_body(tdir):
                rc, out = run("machine sel columns", r_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and rjs.exists():
                    import numpy as np                     # noqa: PLC0415
                    from PIL import Image                  # noqa: PLC0415
                    r = json.loads(rjs.read_text())

                    def lit(name, y0, y1, x0=76, x1=116):   # the list column, in screen pixels
                        im = np.array(Image.open(r["screens"][name]).convert("L")) > 128
                        k = im.shape[1] // 128
                        return float(im[y0 * k:y1 * k, x0 * k:x1 * k].mean())
                    types = r["memory"].get(next((k_ for k_ in r["memory"] if k_.startswith("types@")), ""), [None])
                    if ms:                                  # MACHINE SEL in two columns: stock's view's own state
                        from dnfw.waverider import msel as _ms   # noqa: PLC0415
                        vals = [int(v, 16) if v else None for k_, v in r["memory"].items() if k_.startswith("0x")]
                        rows_ = [c_["d0"] for c_ in r["direct_calls"] if c_["fn"] == f"{MSEL_ROW_TYPE:#x}"]
                        got = dict(zip(("page r1", "cursor r1", "page r2", "cursor r2"), vals))
                        cols = {"RIGHT: MACHINE SEL still up, the filter page, its first row under the cursor":
                                got.get("page r1") == 1 and got.get("cursor r1") == 0
                                and rows_[:1] == [_ms.filter_rows()[0]],
                                "... and its two columns drawn": lit("r1", 8, 60, 2, 124) > 0.1,
                                "LEFT: the machine page, GRID under the cursor (stock's reader and the drawn rows)":
                                got.get("page r2") == 0 and rows_[1:2] == [12]
                                and _ms.machine_rows()[got.get("cursor r2") or 0] == 12}
                    else:
                        cols = {"RIGHT: the FLTR column's first row marked": lit("r1", 8, 16) > 0.3,
                                "... and its list drawn": lit("r1", 8, 60) > 0.1,
                                "LEFT: the SRC column's bottom row (GRID) marked": lit("r2", 52, 60) > 0.3}
                    facts = {"track 1 is GRID": types[0] == 12, **cols,
                             "RIGHT again: the same FLTR column": pathlib.Path(r["screens"]["r3"]).read_bytes()
                             == pathlib.Path(r["screens"]["r1"]).read_bytes(),
                             # O14: SYN held long on GRID's page shows its values, let go shows its labels
                             "SYN held: the page changes": pathlib.Path(r["screens"]["v1"]).read_bytes()
                             != pathlib.Path(r["screens"]["v0"]).read_bytes(),
                             "SYN let go: the page as before": pathlib.Path(r["screens"]["v2"]).read_bytes()
                             == pathlib.Path(r["screens"]["v0"]).read_bytes()}
                    good = all(facts.values())
                    why = (f"{facts} types={types} mem={ {k_: v for k_, v in r['memory'].items() if k_.startswith('0x')} } "
                           f"calls={r.get('direct_calls')}" if ms else
                           f"{facts} types={types} lit={lit('r1', 8, 16):.3f}/{lit('r1', 8, 60):.3f}/{lit('r2', 52, 60):.3f}")
                return good, ("MACHINE SEL: RIGHT from GRID shows the FLTR column from its top, LEFT returns "
                              "to GRID; SYN held shows the page's values" if good else why)
            later("colsw", "MACHINE SEL columns, SYN held (ColdFire)", "MACHINE SEL columns, SYN held (ColdFire)", [r_cmd, sorted(EMU_ENV.items())], r_body)

        # 6m. MACHINE SEL in two columns (csrc/msel/msel.c; upstream's step, its state read from stock's own view: this
        # series' msel.c keeps none). Track 1 on WaveTone, MACHINE SEL opened. After every key the row stock's own
        # reader (0x4005b162(view)) puts under the cursor is the row drawn selected (the view's cursor +420 into
        # dnfw.waverider.msel's rows, what msel_draw draws): DOWN through every row of the machine page and UP back
        # through all of them (every listed type seen), FUNC + SYN to the filter page (stock's RIGHT: still up, page 1)
        # and DOWN through its rows, FUNC + SYN back (page 0); the selected cell inverted, both columns drawn, each
        # page's dot; YES commits the type drawn selected (stock's commit, unchanged); NO closes it.
        if "msel_draw" in lay:
            from dnfw.waverider import msel as _ms      # noqa: PLC0415
            kit = 0x4210D08C
            ty = kit + 52 + 0xDE
            m_rows, f_rows = _ms.machine_rows(), _ms.filter_rows()
            mreads: list[str] = []
            mcalls: list[str] = []

            def mrd(label, off):                        # OFF in MACHINE SEL's view ("" while it is not up)
                mreads.append(label)
                return f"view:{MSEL_VT:#x}:{off}:4"

            def both(label):                            # the view's cursor, and stock's row under it
                mcalls.append(label)
                return f"{mrd(label, MSEL_CURSOR)},call:{MSEL_ROW_TYPE:#x}:view@{MSEL_VT:#x}"
            ms = [f"wait:3,poke:{ty:#x}:01,wait:4,tap:2,wait:6,func-src,wait:20,png:m0",
                  mrd("shown open", 0), mrd("page open", MSEL_PAGE), both("open")]
            ms += [f"down,wait:8,{both(f'down {i}')},png:d{i}" for i in range(len(m_rows))]
            ms += ["png:m1"]
            ms += [f"up,wait:8,{both(f'up {i}')}" for i in range(len(m_rows))]
            ms += ["func-src,wait:20,png:f0", mrd("shown filters", 0), mrd("page filters", MSEL_PAGE),
                   both("filters")]
            ms += [f"down,wait:8,{both(f'filter down {i}')}" for i in range(len(f_rows))]
            ms += ["func-src,wait:20,png:b0", mrd("shown back", 0), mrd("page back", MSEL_PAGE), both("back")]
            ms += ["down,wait:8", both("pick"), "yes,wait:20,types", "no,wait:20", mrd("shown no", 0)]
            mjs = work / "msel.json"
            ms_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", ",".join(ms), "--png-dir", work / "msel", "--json", mjs]

            def ms_body(tdir):
                rc, out = run("machine sel two columns", ms_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and mjs.exists():
                    import numpy as np                     # noqa: PLC0415
                    from PIL import Image                  # noqa: PLC0415
                    r = json.loads(mjs.read_text())

                    def signed(h):
                        if not h:
                            return None
                        v = int(h, 16)
                        return v - (1 << 32) if v & 0x80000000 else v
                    got = dict(zip(mreads, (signed(v) for k_, v in r["memory"].items() if k_.startswith("0x"))))
                    stock_rows = dict(zip(mcalls, (c["d0"] for c in r["direct_calls"])))
                    filt = {k_ for k_ in mcalls if k_ == "filters" or k_.startswith("filter down ")}

                    def drawn_of(k_):                       # the row msel_draw draws selected: rows[cursor]
                        rows, at = (f_rows if k_ in filt else m_rows), got.get(k_)
                        return rows[at] if at is not None and 0 <= at < len(rows) else None
                    drawn = {k_: drawn_of(k_) for k_ in mcalls}
                    differ = {k_: (drawn[k_], stock_rows.get(k_)) for k_ in mcalls if drawn[k_] != stock_rows.get(k_)}
                    walked = {drawn[k_] for k_ in mcalls if k_ == "open" or k_.startswith(("down ", "up "))}
                    fwalked = {drawn[k_] for k_ in filt}
                    types = r["memory"].get(next((k_ for k_ in r["memory"] if k_.startswith("types@")), ""), [None])

                    def lit(name, x0, y0, x1, y1):          # screen pixels, y from the top, both ends in
                        im = np.array(Image.open(r["screens"][name]).convert("L")) > 128
                        k = im.shape[1] // 128
                        return float(im[y0 * k:(y1 + 1) * k, x0 * k:(x1 + 1) * k].mean())

                    def selected(name, at):                 # the cell of stock's row AT on its screen of twelve
                        # (2026-11-20, the User: "remove the lines --------------": the dividers take no cell)
                        c = _ms.shown_index(m_rows, at or 0) % (2 * MSEL_ROWS)
                        x, y = 2 + (c // MSEL_ROWS) * 61, 12 + 8 * (c % MSEL_ROWS)
                        return lit(name, x, y - 1, x + 56, y + 4)
                    n_shown = len([t for t in m_rows if t != _ms.DIVIDER])

                    def no_lines(name):                     # every cell drawn holds a machine's icon (rows other
                        ok_ = []                            # than a divider's middle one), none only a line
                        for c in range(2 * MSEL_ROWS):
                            x, y = 2 + (c // MSEL_ROWS) * 61, 12 + 8 * (c % MSEL_ROWS)
                            line = lit(name, x + 12, y + 2, x + 56, y + 2) > 0.9
                            icon = max(lit(name, x + 1, y + r_, x + 7, y + r_) for r_ in (0, 1, 3, 4)) > 0
                            ok_.append(not line or icon)
                        return all(ok_)
                    unlit = {f"down {i}": round(selected(f"d{i}", got.get(f"down {i}")), 2) for i in range(len(m_rows))
                             if selected(f"d{i}", got.get(f"down {i}")) <= 0.5}
                    facts = {"MACHINE SEL up, the machine page": got.get("shown open") is not None
                             and got.get("page open") == 0,
                             "every row drawn selected is stock's cursor row": not differ,
                             "the machine page's walk saw every listed type": walked == set(m_rows) - {_ms.DIVIDER},
                             "the selected cell inverted": selected("m0", got.get("open")) > 0.5,
                             # the cell stock's cursor is on drawn inverted after every DOWN (FLEX and MIDI included:
                             # their dividers are stock's)
                             "every DOWN: the cursor's cell drawn inverted": not unlit,
                             # (the v0.59 merge: 27 rows, so the last page, m1, holds three: its right column is
                             # empty by design; both columns on the first page, the left on the last, the right too
                             # when the last page reaches it)
                             "both columns drawn": lit("m0", 1, 10, 60, 60) > 0.03 and lit("m0", 63, 10, 122, 60) > 0.03
                             and lit("m1", 1, 10, 60, 60) > 0.03
                             and ((n_shown % (2 * MSEL_ROWS) or 2 * MSEL_ROWS) <= MSEL_ROWS
                                  or lit("m1", 63, 10, 122, 60) > 0.03),
                             # 2026-11-20 (the User: "remove the lines --------------"): no divider line drawn
                             "no divider line, every cell a machine": no_lines("m0") and no_lines("m1"),
                             "the machine page's dot": lit("m0", 124, 52, 127, 55) > 0.9,
                             "FUNC + SYN: the filter page, still up": got.get("shown filters") is not None
                             and got.get("page filters") == 1,
                             "the filter page's dot": lit("f0", 124, 58, 127, 61) > 0.9,
                             "the filter page's walk saw every listed filter": fwalked == set(f_rows),
                             "FUNC + SYN again: the machine page": got.get("shown back") is not None
                             and got.get("page back") == 0,
                             "YES commits the type drawn selected": types[0] == drawn["pick"],
                             "NO closes it": got.get("shown no") is None}
                    good = all(facts.values())
                    why = (f"{ {k_: v for k_, v in facts.items() if not v} } differ={differ} unlit={unlit} got={got} "
                           f"types={types}")
                return good, (f"MACHINE SEL in two columns: {len(m_rows)} machine rows (dividers taking no cell) and "
                              f"{len(f_rows)} filter rows, "
                              "the row drawn selected stock's cursor row after every key; FUNC + SYN switches the "
                              "page; YES commits the row drawn selected; NO closes it" if good else why)
            later("msel", "MACHINE SEL in two columns (ColdFire)", "MACHINE SEL in two columns (ColdFire)",
                  [ms_cmd, sorted(EMU_ENV.items())], ms_body)

        # 6m1. INSERT SEL (2026-11-20, the User: "same code/ui as filter and synth engine"; csrc/msel/msel.c isel_*, the
        # FX icons' one table dnfw.waverider.msel FX_ICONS). Track 1, FX twice: INSERT 1, its M.SEL box with OFF's icon.
        # A pushed: INSERT SEL up on OFF's row, every cell of the screen drawn with its icon (the cursor's inverted);
        # DOWN through the rows to screen 2 and to the end, where it stays; UP back to FDN8; YES: FDN8 picked, closed,
        # M.SEL's box with FDN8's icon. FUNC + turn A opens it again on FDN8's row; RIGHT: INSERT 2 (the page under it
        # too) on its own OFF; LEFT back; DOWN twice, a rest, NO: closed, slot 1 FDN8 again (LIVE SELECT's revert, or
        # nothing picked when it is off)
        if "isel_open" in lay:
            from dnfw.waverider import msel as _ms      # noqa: PLC0415
            irows = _ms.fx_rows()
            ireads: list[str] = []

            def ird(label, sym, n=4):
                ireads.append(label)
                return f"mem:{lay[sym]:#x}:{n}"

            def st(label):                              # INSERT SEL up, its row, its slot; the page's slot; the types
                return [ird(f"{label} open", "isel_open"), ird(f"{label} at", "isel_at"),
                        ird(f"{label} slot", "isel_slot"), ird(f"{label} up", "ins_up"), ird(f"{label} sel", "ins_sel", 2)]
            n_end = len(irows) - 1
            kit = 0x4210D08C                            # (the snapshot's kit, as the msel step's)
            # (each page's name slides in first: the icon comes once it is in, 20 M and more here)
            iss = ["wait:3", "tap:2", "wait:30", "png:t_syn", f"mem:{kit + 52 + 0xDE:#x}:2", "tap:3", "wait:30",
                   "png:t_flt", "tap:4", "wait:30", "png:t_amp",
                   "tap:5", "wait:10", "tap:5", "wait:30", "png:page_off", *st("page"),
                   "tap:41", "wait:12", "png:i_open", *st("open")]
            iss += ["down", "wait:6"] * 3 + [*st("down3")]
            iss += ["down", "wait:6"] * 9 + ["wait:6", "png:i_s2", *st("down12")]
            iss += ["down", "wait:6"] * 3 + [*st("end")]
            iss += ["up", "wait:6"] * (n_end - 3) + [*st("up")]
            iss += ["yes", "wait:30", "png:page_fdn8", *st("yes")]
            iss += ["press:17", "spin:0:1", "wait:6", "release:17", "wait:12", "png:i_func", *st("func")]
            iss += ["right", "wait:12", "png:i_right", *st("right"), "left", "wait:12", *st("left")]
            iss += ["down", "wait:6", "down", "wait:150", *st("rest"), "no", "wait:12", *st("no")]
            ijs = work / "insel.json"
            is_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", ",".join(iss), "--png-dir", work / "insel", "--json", ijs,
                      "--cost", f"{lay['ins_title_icon']:#x}"]

            def is_body(tdir):
                rc, out = run("insert sel", is_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and ijs.exists():
                    import numpy as np                     # noqa: PLC0415
                    from PIL import Image                  # noqa: PLC0415
                    r = json.loads(ijs.read_text())
                    vals = [v for k_, v in r["memory"].items() if k_.startswith("0x")]
                    snd = vals[0] if vals else "0000"                   # track 1's machine and filter
                    mach, flt = int(snd[0:2], 16), int(snd[2:4], 16)
                    got = dict(zip(ireads, vals[1:]))
                    costs = r.get("cost", {}).get(f"{lay['ins_title_icon']:#010x}", [])

                    def num(label):
                        v = got.get(label)
                        return int(v, 16) if v else None

                    def sel(label):                         # slot 1's and slot 2's types on track 1
                        v = got.get(f"{label} sel") or ""
                        return (int(v[0:2], 16), int(v[2:4], 16)) if len(v) >= 4 else None

                    def screen(name):
                        im = np.array(Image.open(r["screens"][name]).convert("L")) > 128
                        k = im.shape[1] // 128
                        return im[k // 2::k, k // 2::k]

                    def icon_at(name, x, y, t, lit, table=None):   # the icon of type T at (x, y) from the top
                        s = screen(name)
                        return all(bool(s[y + r_, x + i]) == (lit if ch == "#" else not lit)
                                   for r_, row in enumerate((table or _ms.FX_ICONS)[t]) for i, ch in enumerate(row))

                    def bar_icon(name, rows):                # the title bar's icon: x 119, row 2, unlit on lit
                        s = screen(name)
                        return all(bool(s[2 + r_, 119 + i]) == (ch != "#") for r_, row in enumerate(rows)
                                   for i, ch in enumerate(row)) and all(s[1, 118:127]) and all(s[7, 118:127])

                    def cells(name, first, at):              # every cell of the screen holding row FIRST..: its icon
                        ok_ = []
                        for c in range(min(12, len(irows) - first)):
                            x, y = 2 + (c // 6) * 61, 12 + 8 * (c % 6)
                            ok_.append(icon_at(name, x + 1, y, irows[first + c], first + c != at))
                        return all(ok_)
                    fdn8, off = 7, 0
                    m_icons = _ms.machine_icons()
                    facts = {"the title bar: the SYN page's name with the machine's icon":
                             mach in m_icons and bar_icon("t_syn", m_icons[mach]),
                             "the title bar: the FLTR page's name with the filter's icon":
                             flt in _ms.FILTER_ICONS and bar_icon("t_flt", _ms.FILTER_ICONS[flt]),
                             "the title bar: AMP's name, no icon": not bar_icon("t_amp", m_icons.get(mach, ["#"] * 5)),
                             "the title bar: INSERT 1's name with its insert's icon": bar_icon("page_off", _ms.FX_ICONS[0]),
                             # (2026-11-20, the User is tight on CPU) a draw with no page name up: a few
                             # instructions; one with the icon: the page's view found, nine column words; the
                             # first draw of another item makes its columns once (measured 38, 233..276, 759..864)
                             "the title bar's icon: at most 60 instructions a draw without it, 1,000 with it":
                             bool(costs) and min(costs) <= 60 and max(costs) <= 1000,
"FX twice: INSERT 1, M.SEL's box with OFF's icon": num("page up") == 1
                             and num("page open") == 0 and icon_at("page_off", 30, 16, off, True),
                             "A pushed: INSERT SEL up, on OFF's row, INSERT 1": num("open open") == 1
                             and num("open at") == 0 and num("open slot") == 0,
                             "screen 1: twelve cells, each its type's icon (the cursor's inverted)":
                             cells("i_open", 0, 0),
                             "DOWN x3: FDN8's row": num("down3 at") == 3,
                             "DOWN to screen 2: its cells and icons": num("down12 at") == 12 and cells("i_s2", 12, 12),
                             "the end: DOWN stays": num("end at") == n_end,
                             "UP back to FDN8": num("up at") == 3,
                             "YES: FDN8 picked, closed, M.SEL's box with FDN8's icon": num("yes open") == 0
                             and (sel("yes") or (None,))[0] == fdn8 and num("yes up") == 1
                             and icon_at("page_fdn8", 30, 16, fdn8, True),
                             "FUNC + turn A: up again on FDN8's row": num("func open") == 1 and num("func at") == 3,
                             "RIGHT: INSERT 2, the page under it too, its own OFF": num("right slot") == 1
                             and num("right up") == 2 and num("right at") == 0 and num("right open") == 1,
                             "LEFT: INSERT 1 again, on FDN8": num("left slot") == 0 and num("left up") == 1
                             and num("left at") == 3,
                             "NO: closed, slot 1 FDN8 as when it opened": num("no open") == 0
                             and (sel("no") or (None,))[0] == fdn8 and num("rest at") == 5}
                    good = all(facts.values())
                    why = f"{ {k_: v for k_, v in facts.items() if not v} } got={got} costs={sorted(set(costs))}"
                return good, (f"INSERT SEL on MACHINE SEL's page: {len(irows)} types with their icons over two "
                              "screens, UP/DOWN stop at the ends, LEFT/RIGHT the slots, YES picks, NO puts back; "
                              "M.SEL's box shows the type's icon; the title bar's icon on SYN, FLTR, INSERT "
                              f"({len(costs)} draws, {min(costs)}..{max(costs)} instructions each)" if good else why)
            later("insel", "INSERT SEL, the FX icons in M.SEL's box and the title bar (ColdFire)",
                  "INSERT SEL, the FX icons in M.SEL's box and the title bar (ColdFire)", [is_cmd, sorted(EMU_ENV.items())], is_body)

        # 6m2. LIVE SELECT (csrc/msel/msel.c, live.c; docs/live-select.md; upstream's step, MACHINE SEL's view found by
        # its class): track 1 on WaveTone, MACHINE SEL opened, the setting on (the default). DOWN moves the cursor:
        # before it has rested nothing is committed (the tick read around it); the tick moved on past the rest: the
        # cursor's machine is on the track; NO puts WaveTone back and the whole sound byte for byte as it was at the
        # opening, and closes. Reopened, DOWN, rested, YES: the cursor's machine kept, closed, nothing reverted. The
        # setting turned off through set_flag_put (what the PERSONALIZE row calls): a resting cursor commits nothing
        # and NO reverts nothing (stock's MACHINE SEL).
        if "ls_commits" in lay:
            kit = 0x4210D08C
            snd0 = kit + 52
            ty = snd0 + 0xDE
            tick = 0x466768B0                            # the panel task's tick (msel.c TICK, read modulo 4096)
            rest, sound_len, live_off = (250 * 120 + 500) // 1000, 1163, 4   # msel.c REST (30: REST_MS, TICK_HZ 120), SOUND_LEN; live.c SET_LIVE_OFF
            lreads: list[str] = []
            lcalls: list[str] = []

            def lrd(label, va, n=4):
                lreads.append(label)
                return f"mem:{va:#x}:{n}"

            def lshown(label):                           # MACHINE SEL's view's class word ("" while it is not up)
                lreads.append(label)
                return f"view:{MSEL_VT:#x}:0:4"

            def lcall(label, text):
                lcalls.append(label)
                return text

            def cursor(label):                           # stock's own type under the cursor
                return lcall(label, f"call:{MSEL_ROW_TYPE:#x}:view@{MSEL_VT:#x}")
            later_rest = f"addl:{tick:#x}:{rest + 50},wait:10"
            ls_ = [f"wait:3,poke:{ty:#x}:01,wait:4,tap:2,wait:6,func-src,wait:20",
                   lrd("open sound", snd0, sound_len), lrd("commits open", lay["ls_commits"]),
                   lrd("tick before", tick)]
            ls_ += ["down,wait:8", lrd("tick after", tick), lrd("commits unrested", lay["ls_commits"])]
            ls_ += [later_rest, lrd("commits rested", lay["ls_commits"]), cursor("cursor rested"), "types",
                    lrd("previewed sound", snd0, sound_len)]
            ls_ += ["no,wait:20", "types", lrd("sound after no", snd0, sound_len), lrd("reverts no", lay["ls_reverts"]),
                    lshown("shown no")]
            ls_ += ["func-src,wait:20,down,wait:8", later_rest, cursor("cursor yes"), "yes,wait:20", "types",
                    lshown("shown yes"), lrd("reverts yes", lay["ls_reverts"]), lrd("commits yes", lay["ls_commits"])]
            ls_ += [lcall("off", f"call:{lay['set_flag_put']:#x}:{live_off}:1"), lrd("bits off", lay["set_bits"]),
                    "func-src,wait:20,down,wait:8", later_rest, "types", lrd("commits off", lay["ls_commits"]),
                    "no,wait:20", "types", lrd("reverts off", lay["ls_reverts"])]
            ljs = work / "livesel.json"
            ls_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", ",".join(ls_), "--png-dir", work / "livesel", "--json", ljs]

            def ls_body(tdir):
                rc, out = run("live select", ls_cmd, logs, env=EMU_ENV, trace=tdir)
                why, good = out[-800:], False
                if rc == 0 and ljs.exists():
                    r = json.loads(ljs.read_text())
                    got = dict(zip(lreads, (v for k_, v in r["memory"].items() if k_.startswith("0x"))))
                    num = {k_: int(v, 16) for k_, v in got.items() if 0 < len(v) <= 8}
                    calls = dict(zip(lcalls, (c["d0"] for c in r["direct_calls"])))
                    types = [v for k_, v in r["memory"].items() if k_.startswith("types@")]
                    t1 = [t[0] for t in types] + [None] * 5   # track 1: rested, NO, YES, off rested, off NO
                    waited = (num.get("tick after", 0) - num.get("tick before", 0)) & 0xFFF
                    c0 = num.get("commits open")
                    facts = {f"the cursor moved, not rested ({waited} ticks < {rest}): nothing committed":
                             waited < rest and num.get("commits unrested") == c0,
                             "rested: the cursor's machine on the track, one commit":
                             t1[0] == calls.get("cursor rested") and t1[0] != 1
                             and num.get("commits rested") == (c0 or 0) + 1,
                             "the preview changed the sound": got.get("previewed sound") != got.get("open sound"),
                             "NO: WaveTone back": t1[1] == 1,
                             "NO: the whole sound as it was at the opening, byte for byte":
                             got.get("sound after no") == got.get("open sound"),
                             "NO: one revert, MACHINE SEL closed": num.get("reverts no") == 1
                             and got.get("shown no") == "",
                             "YES: the cursor's machine kept, closed, nothing reverted":
                             t1[2] == calls.get("cursor yes") and t1[2] != 1 and got.get("shown yes") == ""
                             and num.get("reverts yes") == 1,
                             "off: the sector's flag set": bool(num.get("bits off", 0) & live_off),
                             "off: a resting cursor commits nothing": t1[3] == t1[2]
                             and num.get("commits off") == num.get("commits yes"),
                             "off: NO reverts nothing": t1[4] == t1[2] and num.get("reverts off") == 1}
                    good = all(facts.values())
                    differ = (sum(x != y for x, y in zip(bytes.fromhex(got.get("sound after no", "")),
                                                         bytes.fromhex(got.get("open sound", ""))))
                              if "sound after no" in got and "open sound" in got else None)
                    why = (f"{ {k_: v for k_, v in facts.items() if not v} } types={t1[:5]} calls={calls} "
                           f"num={num} sound bytes differing after NO={differ}")
                return good, ("LIVE SELECT: a moved cursor commits only once rested; NO puts the machine and the "
                              "whole sound back byte for byte; YES keeps the previewed machine; off, MACHINE SEL "
                              "is stock's" if good else why)
            later("livesel", "LIVE SELECT (ColdFire)", "LIVE SELECT (ColdFire)", [ls_cmd, sorted(EMU_ENV.items())], ls_body)

        # 2026-11-20 (the User): AMP ON/OFF for the drum machines (csrc/msel/ampsw.c, docs/live-select.md "AMP ON/OFF"):
        # scripts/emu_amp_switch.py from the build's snapshot: picks never touch AMP or VOL, the DSP's mask bit exactly
        # on a drum with AMP OFF (PLAITS by MODL), H on stock's AMP page (drawn, turned, pushed) and VOL as stock on
        # WaveTone, stock's SAVE / LOAD carrying the field. Keyed on smp_machine_commit (main's too), so a build
        # without the code runs it and fails
        if "smp_machine_commit" in lay:
            da_js = work / "drumamp.json"
            da_cmd = [a.venv, "-u", "scripts/emu_amp_switch.py", "--build", a.build, "--snapshot", snap, "--json", da_js]

            def da_body(tdir):
                rc, out = run("AMP ON-OFF", da_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if l.startswith("FAIL"))[-900:] or out[-900:]
                return True, last[:800]
            later("drumamp", "AMP ON/OFF on the drum machines: H on the AMP page, the field, the DSP's mask (ColdFire)",
                  "AMP ON/OFF on the drum machines (ColdFire)", [da_cmd, sorted(EMU_ENV.items())], da_body)

        # 6s. v0.45 (v0.44's BOUNCE froze the unit on MACHINE SEL's YES, and at every power-on of
        # a project holding a BOUNCE track: pages.py wr_label indexed past the Monomachine's label
        # tables and walked absolute 0x000000EE, zero RAM in the emulator, nothing on the unit).
        # Not from ui800M-v014, whose MACHINE SEL rows are v0.14's: boot400M with this build
        # installed (its own rows), the kit given every one of our types at the UI's first draw
        # (the newest on the active track) and booted on; then each track of ours drawn (FLTR,
        # SYN) and every row of LIST_NEW picked through MACHINE SEL's own list. A read below
        # 0x40000000 by code that is not stock's fails, as does EXCEPTION (scripts/emu_machine_boot.py,
        # scripts/emu_machine_sweep.py)
        from dnfw.waverider import coldfire as _cfm     # noqa: PLC0415
        mb_types = sorted(_cfm.NEW_TYPES, reverse=True)
        mb_snap, mb_js, ms_js = work / "machines-boot.snap", work / "machines-boot.json", work / "machines.json"
        stock_sec = work / "stock_section_3_MAIN_OS.bin"
        mb_cmd = [a.venv, "-u", "scripts/emu_machine_boot.py", "--build", bdir, "--stock", stock_sec,
                  "--snapshot", ROOT.parent / "digikit/out/snapshots/dn2-1.11/boot400M.snap",
                  "--types", ",".join(map(str, mb_types)), "--out", mb_snap, "--json", mb_js]
        ms_cmd = [a.venv, "-u", "scripts/emu_machine_sweep.py", "--snapshot", mb_snap, "--stock", stock_sec,
                  "--mod-types", ",".join(map(str, mb_types)), "--list", ",".join(map(str, _cfm.LIST_NEW)),
                  "--png-dir", work / "machines", "--json", ms_js]
        MB_ENV = {**EMU_ENV, "DT2_SYX": str(pathlib.Path(a.stock).resolve())}

        def mb_body(tdir):
            rc, out = run("machines: power-on", mb_cmd, logs, env=MB_ENV, trace=tdir)
            if rc != 0 or "machine boot: PASS" not in out:
                return False, out[-800:]
            rc, out = run("machines: MACHINE SEL", ms_cmd, logs, env=MB_ENV, trace=tdir)
            good = rc == 0 and "machine sweep: PASS" in out
            return good, (f"a power-on with types {mb_types} on the tracks, each track of ours drawn, and all "
                          f"{len(_cfm.LIST_NEW)} rows of MACHINE SEL's own list picked: no read below 0x40000000 "
                          "by our code, no EXCEPTION" if good else out[-800:])
        later("machines", "every machine through MACHINE SEL's own list; a power-on with ours on the tracks (ColdFire)",
              "every machine, MACHINE SEL's own list (ColdFire)", [mb_cmd, ms_cmd, sorted(MB_ENV.items())], mb_body)

        # 6q. v0.33: the sample pages driven at random (scripts/emu_fuzz_ui.py: SAMP turns,
        # the list, the browser and its menu, page and [TRIG] keys, MACHINE SEL, the machine
        # changed under the page): two seeds, each must finish, fault nothing in our code and
        # answer the last probe. v0.34 (docs/timing-model.md): the audio interrupt fires on
        # its own at its real cadence throughout (digikit's SSI0/eDMA event source, through
        # the real vectors), preempting the mod's UI code as on the unit; a CPU exception,
        # the interrupt no longer delivered, or audio frames overrunning fail the seed. It
        # needs the section the snapshot was booted with beside it (its own build's edits
        # are put back to stock first)
        # v0.38 (blskk's crash): first a fixed arp scenario (a SLICE track at NOTE, the arp on,
        # KEYBOARD's CHORD MEMORY with 12-note chords, keys held while the sequencer ticks, the
        # RECORDER and ARP pages up); the seeds also turn the arp, KEYBOARD and the sequencer; every
        # run fails on a free() of a stack address (emu_waverider_menu.py's stack_frees)
        if "smp_lst_open" in lay:
            snap_sec = pathlib.Path(str(snap) + ".section_3_MAIN_OS.bin")
            fz_cmd = [sys.executable, "scripts/emu_fuzz_ui.py", bdir, "3,7", "--steps", "24",
                      "--venv", a.venv, "--snapshot", snap, "--json", work / "fuzz.json",
                      "--isr-frame", "75000"]

            def fz_body(tdir):
                if not snap_sec.exists():
                    return False, f"missing {snap_sec} (the snapshot's own MAIN OS section): the real-rate interrupt needs it"
                rc, out = run("ui fuzz", fz_cmd, logs, env={**EMU_ENV, "PYTHONPATH": str(ROOT / "src")}, trace=tdir)
                return rc == 0, (out.strip().splitlines()[-1] if rc == 0 else out[-800:])
            later("fuzz", "UI fuzz, two seeds, the audio interrupt at its real rate (ColdFire)", "UI fuzz, two seeds, real-rate ISR (ColdFire)", [fz_cmd, sorted(EMU_ENV.items())], fz_body)

        # 2026-11-16 (PARA as one voice, csrc/para/one.c, docs/paraphonic-onevoice.md; the User: every note-off route a
        # scenario, the chord's slot kept the riskiest): the audio ISR's note-on and key-up allocator calls through
        # their hooks on stock 1.12's own allocator (scripts/emu_para_onevoice.py, emu_load_budget's install): a
        # joining note leaves stock's state byte for byte; key-up, gate timer, no-key net, stop-all, PARA off end it;
        # the chord's slot is never taken while held; the stack within 256 bytes of stock's
        if "pv_ch" in lay:
            pvo_js = work / "para_onevoice.json"
            pvo_cmd = [a.venv, "-u", "scripts/emu_para_onevoice.py", "--snapshot", snap, "--json", pvo_js]

            def pvo_body(tdir):
                rc, out = run("paravoice", pvo_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                r = json.loads(pvo_js.read_text()) if pvo_js.exists() else {}
                return True, f"{last}; stack {r.get('stack')}"[:800]
            later("paravoice", "PARA as one voice: joined notes take no slot, every note-off route, the chord's slot "
                  "kept (ColdFire)", "PARA as one voice (ColdFire)", [pvo_cmd, sorted(EMU_ENV.items())], pvo_body)

        # 2026-11-19 (the User, v0.62.4: "one kick kills the drone held voice"; csrc/hold/hold.c hold_locked): DRONE
        # HOLD's latched slot, released in stock's state at its key-up, was a free slot to stock's allocator. The
        # note-on's allocator call through its hook on stock 1.12's own allocator (scripts/emu_drone_hold.py, the
        # paravoice rig): another track's note never takes a latch (one kick, sixteen, a full pool, the VOICE
        # BUDGET's steal and releases); all candidates latched: no slot (the ISR's no-slot path); the drone's own
        # track and HOLD OFF as stock; no latch: the hook = stock byte for byte
        if "hold_locked" in lay:
            dh_js = work / "drone_hold.json"
            dh_cmd = [a.venv, "-u", "scripts/emu_drone_hold.py", "--snapshot", snap, "--json", dh_js]

            def dh_body(tdir):
                rc, out = run("dronehold", dh_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                r = json.loads(dh_js.read_text()) if dh_js.exists() else {}
                return True, f"{last}; stack {r.get('stack')}"[:800]
            later("dronehold", "DRONE HOLD: a latched voice never taken by another note, the no-slot path (ColdFire)",
                  "DRONE HOLD latches (ColdFire)", [dh_cmd, sorted(EMU_ENV.items())], dh_body)

        # 6s. DIRECT JUMP (csrc/jump, docs/jump.md; scripts/emu_jump.py): the sequencer ticked
        # through stock's own ISR, a pattern cued with PTN + TRIG. Off: every tick's sequencer
        # state is stock's (same digest as the stock image's run). On (PTN + YES): the switch
        # within one step of the cue, and from the step after it every track goes on from its
        # own step in the playing pattern, wrapped by its new length (Elektron's rule; per
        # pattern, per track with lengths 5, 7, 3, and after a 12-step pattern's loop and a
        # half into a 16-step one); with equal lengths from PLAY, where stock plays that pattern
        # from PLAY. On, a cue through the sequencer's own cue routine (program changes,
        # chains, songs): stock's. The setting written to its sector, read back at power-on, NO turns
        # it off. v0.40 (owner: "works ~70% of the time", not when rapid-fired): 83 cues one after
        # another at every phase after the previous switch, pairs before one switch, PTN held
        # across two: each at the first step boundary, from where the pattern was (v0.39's code
        # fails 29). No fault anywhere
        if "jmp_on" in lay:
            jdir = work / "jump"
            jdir.mkdir(exist_ok=True)
            jruns = [("off", "pp", True), ("off", "pp", False), ("pc", "pp", False), ("on", "pp", False),
                     ("ref", "pp", True), ("on", "pt", False), ("ref", "pt", True), ("on", "odd", False),
                     ("persist", "pp", False), ("rapid", "pp", False)]
            # 2026-11-14 (the 1.12 gate's blind spots): both runs from one snapshot that booted
            # stock (ui1200M, no section beside it), the build installed over it. 1.12's per-build
            # ui800M booted THIS build: its UI state calls into the build's C chunk, so reverted to
            # stock (--stock) it faulted at once (stock's fault reporter, from 0x46acee58)
            jsnap = snap.parent / "ui1200M.snap"
            if not jsnap.exists() or pathlib.Path(f"{jsnap}.section_3_MAIN_OS.bin").exists():
                jsnap = snap
            # 2026-11-14 (the 1.12 gate's blind spots): every run on the coupled emulator (scripts/emu_jump_coupled.py:
            # emu_jump's own run(), checks and digest, the UI and the audio ISR every period; --stock the coupled
            # emulator on the stock image). emu_jump alone never runs the audio ISR: on 1.12 the sequencer's node pool
            # ran dry at entry 256; with the ISR run inside it, the work A04's switch (rapid) and, from v0.53, A01's
            # loop (odd) start waited on a TDM side it does not have, and no key reached stock's cue after it
            jcmds = [[a.venv, "-u", "scripts/emu_jump_coupled.py", "--build", a.build, "--stock-image", a.stock,
                      "--snapshot", jsnap, "--scenario", sc, "--variant", var, "--png-dir", jdir / f"screens_{sc}_{var}",
                      "--json", jdir / f"{sc}_{var}_{'stock' if st else 'build'}.json"]
                     + (["--stock"] if st else []) for sc, var, st in jruns]

            def jump_body(tdir):
                res = {}
                for (sc, var, st), cmd in zip(jruns, jcmds):
                    rc, out = run(f"jump {sc} {var} {'stock' if st else 'build'}", cmd, logs, env=EMU_ENV, trace=tdir)
                    got = re.findall(r"^emu_jump \w+: (\{.*\})$", out, re.M)
                    if not got:
                        return False, f"{sc}/{var}: no result (rc {rc}): {out[-600:]}"
                    res[(sc, var, st)] = json.loads(got[-1])
                    if rc != 0 or res[(sc, var, st)].get("faults"):
                        return False, f"{sc}/{var}: rc {rc}, faults {res[(sc, var, st)].get('faults')}"
                stock_off = res[("off", "pp", True)]["trace_digest"]
                why = []
                if res[("off", "pp", False)]["trace_digest"] != stock_off:
                    why.append("off: the sequencer's state differs from stock's")
                pc = res[("pc", "pp", False)]
                if pc["trace_digest"] != stock_off or pc["jmp"]["jmp_count"] != 0:
                    why.append("a cue not from the PTN view jumped")
                for var in ("pp", "pt", "odd"):
                    on, ref = res[("on", var, False)], res.get(("ref", var, True))
                    if on.get("on") != 1 or not on.get("sector_after_yes", "").startswith("444e3253"):
                        why.append(f"{var}: PTN + YES did not turn it on and write it")
                    sw = on.get("switch_global")
                    if sw is None or on["switch_after_cue_ticks"] > 6 or on["jmp"]["jmp_count"] != 1:
                        why.append(f"{var}: no switch within a step of the cue ({on.get('switch_after_cue_ticks')} ticks)")
                        continue
                    if not on.get("rule_ok"):
                        why.append(f"{var}: after the jump, steps {on.get('rule_bad')} do not go on from the playing pattern's")
                    if ref is not None:
                        after = [g for g in on["steps"] if int(g) > sw]
                        bad = [g for g in after if on["steps"][g] != ref["steps"].get(g)]
                        if bad or len(after) < 20:
                            why.append(f"{var}: after the jump, steps {bad[:4]} are not where stock plays that pattern")
                if not res[("persist", "pp", False)].get("ok"):
                    why.append("the setting did not persist (or wrote outside its sector)")
                rp = res[("rapid", "pp", False)]
                if not rp.get("ok"):
                    why.append(f"rapid fire: {rp.get('n_bad')} of {rp.get('cues')} cues not switched at the next "
                               f"boundary from where the pattern was, e.g. {rp.get('bad', [])[:2]}")
                on = res[("on", "pp", False)]
                return not why, ("; ".join(why) if why else
                                 f"off and a program-change cue: stock's state every tick; on: switched "
                                 f"{on['switch_after_cue_ticks']} tick(s) after the cue, start step {on['jmp']['jmp_last']}; "
                                 "every track goes on from its own step, wrapped by its new length (per pattern; per "
                                 "track, lengths 5, 7, 3; after a 12-step pattern's loop and a half, start "
                                 f"{res[('on', 'odd', False)]['jmp']['jmp_last']}), and from PLAY where stock plays it; "
                                 "the setting written, read back at power-on, turned off; v0.40: rapid fire, "
                                 f"{res[('rapid', 'pp', False)].get('cues')} cues at every phase after a switch "
                                 "(pairs, PTN held across two), each at the next boundary")
            later("jump", "DIRECT JUMP (ColdFire)", "DIRECT JUMP (ColdFire)", [*jcmds, sorted(EMU_ENV.items())], jump_body)

        # 6s. parameter slides (docs/slides.md, scripts/emu_slides.py): on the ColdFire, a trig's
        # locks applied as the frame ISR's note block applies them, then the real frame ISR every
        # frame: with SLIDE on, FILTER FREQ and FM TONE's FDBK ramp to the trig's locks over SLEN,
        # exact per frame, and land on them; a knob, a tempo change, a trigless lock, a retrig,
        # a new sound, a trig with no p-lock; the lock table's SAVE/LOAD and step clear. With
        # SLIDE off, and for every lock table, the same as stock 1.11 byte for byte: every frame's
        # smoother state and output arrays (the emulator's own EMAC, and the instrument's
        # arithmetic), what SAVE stores and LOAD restores, and stock skipping our records.
        # v0.40: copy and paste through the panel (track copy/clear/paste, trig copy/paste) carry
        # SLD/SLEN exactly as the track's stock lock beside them (both fail on v0.39's code)
        # v0.40 review (scripts/emu_slides_paths.py): every hooked paste site driven and counted --
        # shift right/left, track paste and its UNDO, page copy/paste and its UNDO, page autocopy
        # on lengthening -- each against the whole lock table; slot 80 (shift and autocopy treat
        # our records as stock's): the same routines with and without our records make the same
        # writes outside them, from the same memory, and never touch the sound; a track and a trig
        # paste on a nearly full lock table keep every stock lock (939cbc42 dropped two)
        # v0.40 (a user's report): a trig with a stock p-lock on a sample machine's SAMP (ONESHOT)
        # and on SLICE's SLCE, through stock's builder and applier and the real frame ISR (with
        # smp_mod_apply): the frame's word, played through the DSP's model, is exactly the locked
        # sample / slice, with the track's value on two others; unlocked trigs the track's (v0.39:
        # the lock was a scaled offset from the track's value)
        if "sl_smooth" in lay:
            # 2026-11-14 (the 1.12 gate's blind spots): both runs from a snapshot that booted stock (ui1200M, no
            # section beside it) when there is one, as the jump step: 1.12's per-build snapshot booted THIS build,
            # and reverted to stock (--stock) its UI composed no frame (no TRIG page 2 to compare)
            ssnap = snap.parent / "ui1200M.snap"
            if not ssnap.exists() or pathlib.Path(f"{ssnap}.section_3_MAIN_OS.bin").exists():
                ssnap = snap
            sl_cmds = [[a.venv, "-u", "scripts/emu_slides.py", "--build", bdir, "--snapshot", ssnap,
                        "--json", work / f"slides-{k}.json",
                        *(["--stock"] if k == "stock" else ["--png-dir", work / "slides-png"])]
                       for k in ("build", "stock")]

            def sl_body(tdir):
                outs = []
                for k, cmd in zip(("build", "stock"), sl_cmds):
                    rc, out = run(f"slides {k}", cmd, logs, env=EMU_ENV, trace=tdir)
                    if rc != 0 or "PASS" not in out.strip().splitlines()[-1]:
                        return False, f"{k}: " + out[-800:]
                    outs.append(json.loads((work / f"slides-{k}.json").read_text()))
                b, s = outs
                same = [k for k in ("plain_stored_sha", "plain_loaded_sha",
                                    "ours_loaded_rest_sha") if b.get(k) != s.get(k)]
                if same or not s.get("stock_skips_ours"):
                    return False, f"differs from stock: {same or 'stock did not skip ids 200/201'}"
                # 2026-11-20 (the User): SLIDE off, every frame's STATE and OUT as stock's, word for word, but for the
                # one declared difference: half-rate LFOs' cells off their voice's turn (scripts/slides_stock.py). A
                # build without half-rate is compared exactly. A negative control: a STATE word, a word no LFO
                # writes, and an LFO cell on its voice's turn, each changed in stock's own frames, must fail
                held = {}
                for k in ("off_shas_emac", "off_shas"):
                    turns = b.get(f"{k}_turns")
                    if b.get(k) == s.get(k) and turns is None:
                        continue                        # no half-rate: equal, word for word
                    if not b.get(f"{k}_frames") or not s.get(f"{k}_frames"):
                        return False, f"differs from stock: {k} (no frames to compare)"
                    bad, summary = slides_stock.compare(b[f"{k}_frames"], s[f"{k}_frames"], turns)
                    if bad:
                        return False, f"differs from stock: {k}, {len(bad)} words not declared, e.g. {bad[:3]}"
                    if turns is not None:
                        wrong = slides_stock.negative_control(s[f"{k}_frames"], turns)
                        if wrong:
                            return False, f"the stock comparison's negative control ({k}): {wrong}"
                        held[k] = summary
                # v0.40: TRIG page 2, our two places (x 21..71, the bottom 25 rows) aside, is
                # stock 1.11's page pixel for pixel
                fb, fs = b.get("trig2_frame"), s.get("trig2_frame")
                if not fb or not fs:
                    return False, "TRIG page 2: no frame from the build or stock"
                fb, fs = bytes.fromhex(fb), bytes.fromhex(fs)

                def lit(buf):
                    return {(x, y) for x in range(128) for y in range(64)
                            if (buf[(7 - (y // 8)) + 8 * x] >> (y % 8)) & 1}
                ours = lambda p: 21 <= p[0] <= 71 and p[1] >= 39          # noqa: E731
                diff = {p for p in lit(fb) ^ lit(fs) if not ours(p)}
                if diff:
                    return False, f"TRIG page 2 differs from stock's outside SLD/SLEN: {len(diff)} pixels, e.g. {sorted(diff)[:4]}"
                return True, (f"SLIDE on: FREQ and FDBK ramp over {b['expected_ramp_frames']} frames "
                              f"(1 step at {b['tempo_word_after_isr'] / 120:g} BPM), exact, landing on the "
                              f"locks; {len(b['checks'])} checks; SLIDE off: {len(b['off_shas'])} frames' "
                              f"arrays and the lock table's SAVE/LOAD identical to stock 1.11"
                              + (f" (but the declared half-rate LFO cells off their voice's turn, {held}; the negative "
                                 f"control failing as it must)" if held else "") + "; the TRIG page's SLD/SLEN "
                              f"set through the panel, the held trig staying on after release; v0.40: track copy, "
                              f"clear and paste carry them exactly as the stock locks, trig copy/paste too, no "
                              f"SLD/SLEN value in a stock lock; v0.40 review: shift, page paste and both "
                              f"UNDOs, autocopy driven (site hits {b.get('paths_hits')}), slot 80 harmless, "
                              f"a paste on a full table keeps every stock lock; v0.40: a SAMP and a SLCE p-lock play their own sample and "
                              f"slice whatever the track's (SAMP 10 and slice 7 over SAMP 2/5, slice 2/5); "
                              f"v0.40: SLD drawn as stock's RTRG and SLEN as "
                              f"stock's LEN pixel for pixel (off/on, unlocked/locked), the page otherwise "
                              f"stock's")
            later("slides", "parameter slides (ColdFire)", "parameter slides (ColdFire)",
                  [*sl_cmds, sorted(EMU_ENV.items())], sl_body)

        # v0.49 FLEX (docs/flex-design.md), on BOUNCE's type 17: replaces v0.48's bouncegone and keeps
        # its other checks (SAMP never glides, the RECORDER's CHAN knob and FILE NAME keys, the
        # Monomachine's TUNE). Always run: not keyed to a symbol, so it can never drop out unseen
        fc_js = work / "flexcore.json"
        fc_cmd = [a.venv, "-u", "scripts/emu_flexcore.py", "--build", bdir, "--snapshot", snap,
                  "--json", fc_js, "--png-dir", work / "flexcore"]

        def fc_body(tdir):
            rc, out = run("flex core", fc_cmd, logs, env=EMU_ENV, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0 or not last.startswith("PASS"):
                return False, out[-900:]
            return True, (f"{last[6:]}: recorder trigs and a slide through SAVE/LOAD byte for byte; the buffers on "
                          f"with a directory, a manual recording kept clear of a buffer's plan; over two passes "
                          f"the trig fires each pass and the one-shot once (then spent), each a take sent to the "
                          f"DSP, the voice on buffer 1; ARM OFF fires nothing; the LED site ours; record 244 BUF "
                          f"on FLEX only; FUNC + VOICE opens FLEX REC, its LEDs the trigs; SAMP never glides; "
                          f"CHAN, FILE NAME; the Monomachine's TUNE")
        later("flexcore", "FLEX on the ColdFire: recorder trigs, ARM, the panel, an older BOUNCE track's trigs (ColdFire)",
              "FLEX on the ColdFire: recorder trigs, ARM, the panel, an older BOUNCE track's trigs (ColdFire)",
              [fc_cmd, sorted(EMU_ENV.items())], fc_body)

        # v0.48 (owner, 2026-11-09): no text outside its place, every value of a control at one
        # place and size: the RECORDER in every state of its centre box and R.LEN through its values
        rx_js = work / "rectext.json"
        rx_cmd = [a.venv, "-u", "scripts/emu_rectext.py", "--build", bdir, "--snapshot", snap,
                  "--json", rx_js, "--png-dir", work / "rectext"]

        def rx_body(tdir):
            rc, out = run("recorder text", rx_cmd, logs, env=EMU_ENV, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0 or not last.startswith("PASS"):
                return False, out[-900:]
            return True, (f"{last[6:]}: every centre-box message of the RECORDER inside its box (no "
                          f"pixel in the gutters, the border untouched), R.LEN's MAX and step counts on "
                          f"one line inside their column")
        later("rectext", "RECORDER text inside its places, every state and R.LEN value (ColdFire)",
              "RECORDER text inside its places, every state and R.LEN value (ColdFire)",
              [rx_cmd, sorted(EMU_ENV.items())], rx_body)

        # v0.48 (owner, 2026-11-09: "chromatic view is gone after REC grid mode ... i wish it
        # [persisted], across all tracks and machine types"). KEYBOARD's state is the long at
        # 0x42432a99 in this snapshot (the keyboard object's +56: 0x40047088 toggles it,
        # 0x4004702e sets it; found with --access). KEYBOARD on; RECORD (grid recording on):
        # off, as stock; RECORD again (off): on again (stock left it off); to track 2 (made an
        # ONESHOT) with TRK + [TRIG 3]: still on; RECORD twice there: on; KEYBOARD off; RECORD
        # twice: still off (nothing given back that was not taken)
        from dnfw.sampler import machines as SMk        # noqa: PLC0415
        KB = "mem:0x42432a99:4"
        kb_steps = ["wait:6", KB, "tap:18", "wait:8", KB, "tap:19", "wait:8", KB, "tap:19", "wait:8", KB,
                    f"poke:{0x4210D08C + 52 + 1163 * 2 + 0xDE:#x}:{SMk.TYPE_OF['ONESHOT']:02x}",
                    "press:16", "wait:2", "tap:27", "wait:2", "release:16", "wait:8", KB,
                    "tap:19", "wait:8", KB, "tap:19", "wait:8", KB,
                    "tap:18", "wait:8", KB, "tap:19", "wait:8", KB, "tap:19", "wait:8", KB, "png:end"]
        kb_js = work / "kbrec.json"
        kb_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                  "--snapshot", snap, "--steps", ",".join(kb_steps), "--png-dir", work / "kbrec", "--json", kb_js]
        KB_WANT = [0, 1, 0, 1, 1, 0, 1, 0, 0, 0]

        def kb_body(tdir):
            rc, out = run("keyboard rec", kb_cmd, logs, env=EMU_ENV, trace=tdir)
            if rc != 0 or not kb_js.exists():
                return False, out[-900:]
            got = [int(v, 16) for v in json.loads(kb_js.read_text())["memory"].values()]
            if got != KB_WANT:
                return False, f"KEYBOARD's word {got}, wanted {KB_WANT}"
            return True, ("KEYBOARD on; RECORD (grid recording): off as stock; RECORD again: on again; on "
                          "another track, an ONESHOT: still on, and through RECORD twice; KEYBOARD off: "
                          "RECORD twice leaves it off")
        later("kbrec", "KEYBOARD kept through grid recording (ColdFire)",
              "KEYBOARD kept through grid recording (ColdFire)", [kb_cmd, sorted(EMU_ENV.items())], kb_body)

        # v0.64 KEYBOARD HOLD (docs/kbhold.md; csrc/sampler/rec.c smp_ui_pop, jump.c): PTN held +
        # KEYBOARD turns HOLD on and off: stock's own sustain (MIDI CC 64's 0x4012702a) on all 16
        # tracks. The screens first (after the harness's own ISR entry, frame:, the panel's
        # picture stops following the UI: measured): KB HOLD ON / OFF on the PTN view's line
        # (10 waits after the tap: measured), the PTN view up while PTN is held and closed at its
        # release (left open, the next [TRIG] picked a pattern: measured), KEYBOARD left on,
        # DIRECT JUMP's setting untouched. Then the ISR's frame (bytes 0x22..0x25: the trig and
        # release masks): [TRIG 1] held BEFORE HOLD comes on, let go after: no release (a note
        # already playing is latched); [TRIG 5] played and let go: held too; MIDI in: a note-off
        # on channel 1 (track 1's), through stock's MIDI note-off entry 0x40121d8e, is kept in
        # track 1's sustain list; HOLD off: both voices released, every sustain off, every list
        # empty. Negative controls: HOLD off, a MIDI note-off is not kept and [TRIG 1] let go is
        # released at once
        if "kh_on" in lay:
            HL = {n: lay[n] for n in ("kh_on", "kh_close", "jmp_on", "wr_screen_obj")}
            SUS, LISTS, MSG = 0x445FF6E0, 0x445FF6F0, 0x46A08000
            hw = f"walk:{HL['wr_screen_obj']:#x}"
            combo = ["press:23", "wait:10", "tap:18", "wait:10", "release:23", "wait:10"]
            midi = [f"poke:{MSG:#x}:803c40", f"call:0x40121d8e:{MSG:#x}", f"mem:{LISTS:#x}:8"]
            state = [f"mem:{HL['kh_on']:#x}:4", f"mem:{SUS:#x}:16"]
            hs = ["wait:6", "tap:18", "wait:6", f"mem:{HL['jmp_on']:#x}:4", "png:before",
                  "press:23", "wait:10", hw, "tap:18", "wait:10", "png:holdon", "release:23", "wait:10", hw,
                  "press:23", "wait:10", hw, "tap:18", "wait:10", "png:holdoff", "release:23", "wait:10", hw,
                  "press:25", "wait:4", "frame:p1", *combo, *state,
                  "release:25", "wait:4", "frame:r1",
                  "press:29", "wait:4", "frame:p5", "release:29", "wait:4", "frame:r5", *midi,
                  *combo, "frame:off", *state, f"mem:{LISTS:#x}:128", *midi,
                  "press:25", "wait:4", "frame:q1", "release:25", "wait:4", "frame:qr1",
                  f"mem:{HL['kh_close']:#x}:4", f"mem:{HL['jmp_on']:#x}:4", "mem:0x42432a99:4"]
            kh_js = work / "kbhold.json"
            kh_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", ",".join(hs), "--png-dir", work / "kbhold", "--json", kh_js]

            def kh_body(tdir):
                rc, out = run("keyboard hold", kh_cmd, logs, env=EMU_ENV, trace=tdir)
                if rc != 0 or not kh_js.exists():
                    return False, out[-900:]
                r = json.loads(kh_js.read_text())
                mem = list(r["memory"].items())
                walks = [v for k, v in mem if k.startswith("walk")]
                v = [bytes.fromhex(x) for k, x in mem if not k.startswith("walk")]
                if len(v) != 11:
                    return False, f"{len(v)} memory reads, wanted 11"
                u = lambda b: int.from_bytes(b, "big")                  # noqa: E731
                fr = {}
                for f in ("p1", "r1", "p5", "r5", "off", "q1", "qr1"):
                    b = pathlib.Path(r["frames"][f]["file"]).read_bytes()
                    fr[f] = struct.unpack(">2H", b[0x22:0x26])            # (trig, release)
                shots = {n: pathlib.Path(r["screens"][n]).read_bytes() if n in r["screens"] else b""
                         for n in ("before", "holdon", "holdoff")}
                ptn = "40200cd4"                                   # the PTN view's class on 1.12 (jump.c PTN_VIEW_VT)
                t1, t5, tq = fr["p1"][0], fr["p5"][0], fr["q1"][0]
                facts = {
                    "PTN + KEYBOARD: the PTN view up while PTN is held, closed at its release, both times":
                        len(walks) == 4 and ptn in walks[0] and ptn not in walks[1] and ptn in walks[2]
                        and ptn not in walks[3],
                    "KB HOLD ON / OFF on the PTN view's line (each screen its own)":
                        all(shots.values()) and len(set(shots.values())) == 3,
                    "HOLD on: stock's sustain on all 16 tracks": u(v[1]) == 1 and v[2] == b"\x01" * 16,
                    "a note already held when HOLD came on is latched when let go":
                        t1 and fr["p1"][1] == 0 and fr["r1"] == (0, 0),
                    "a note played while HOLD is on is held too": t5 and t5 != t1 and fr["r5"] == (0, 0),
                    "MIDI in: a note-off on track 1's channel is kept in its sustain list": u(v[3][:4]) != 0,
                    "HOLD off: every held voice released, every sustain off, every list empty":
                        fr["off"] == (0, t1 | t5) and u(v[4]) == 0 and v[5] == bytes(16) and v[6] == bytes(128),
                    "negative control: HOLD off, a MIDI note-off is not kept": u(v[7][:4]) == 0,
                    "negative control: HOLD off, a key let go is released at once":
                        tq and fr["q1"][1] == 0 and fr["qr1"] == (0, tq),
                    "KEYBOARD left on; DIRECT JUMP's setting untouched; nothing pending":
                        u(v[10]) == 1 and v[9] == v[0] and u(v[8]) == 0,
                }
                good = all(facts.values())
                return good, ("PTN + KEYBOARD turns stock's sustain on and off on every track (KEYBOARD and DIRECT "
                              "JUMP untouched, the PTN view closed, the message shown); a note already held is "
                              "latched, a new one held, a MIDI note-off kept; HOLD off releases all; off, keys and "
                              "MIDI release as stock's" if good else
                              json.dumps({k: x for k, x in facts.items() if not x}) + f" frames={fr} "
                              f"mem={[x.hex()[:40] for x in v]} walks={walks}")
            later("kbhold", "KEYBOARD HOLD: PTN + KEYBOARD, held notes, chords, release (ColdFire)",
                  "KEYBOARD HOLD: PTN + KEYBOARD, held notes, chords, release (ColdFire)",
                  [kh_cmd, sorted(EMU_ENV.items())], kh_body)

        # v0.67: the arpeggiator on MIDI tracks (the midiarp mod from upstream, Angel Linares's
        # dn2_firmware_explore: tested on his unit 2026-09-17 as arp-midi-play4; docs/midiarp.md). Three runs, KEYBOARD on, [TRIG 1] held then let go, a frame
        # after each: track 1 MIDI (the kit's synth/MIDI mask, kit + 0x5cda, bit 0) with the arp on (its
        # sound's MODE, + 0x15f, UP): the key goes the synth road (the voice starter 0x4013801c, never the
        # MIDI sender 0x4012bb90), through the key gate; the ISR's voice trigger reaches the hook that
        # turns the note into a MIDI record (0x402d0c1c), and the engine's voice trigger (0x400db688) is
        # never called for it. (The ISR still sets the voice slot's note-on bit after the hook, stock code
        # past it, measured here: on upstream's unit a MIDI track's slot made no sound, heard 2026-09-17 with
        # arp-midi-diag, which also called the stock trigger; docs/midiarp.md.)
        # Negative controls: the same MIDI track, arp off: the MIDI sender, as stock, never the starter;
        # a synth track (arp off): the starter and a voice in the frame, as stock
        if "kh_on" in lay:
            from dnfw.mods import midiarp as MAg      # noqa: PLC0415
            kit_ = 0x4210D08C                         # (1.12 addresses here: port_os112, the v0.67.1 merge)
            ma_mask, ma_mode = kit_ + 0x5CDA, kit_ + 52 + 0x15F
            ma_cnt = {"starter": 0x4013801C, "sender": 0x4012BB90, "keygate": 0x402D0BD4,
                      "seqgate": 0x402D0BA4, "trighook": 0x402D0C1C, "vtrig": 0x400DB688}
            ma_runs = {}
            for nm, mask, mode in (("midi_arp", "0001", "01"), ("midi_off", "0001", "00"), ("synth_arp", "0000", "00")):
                js_ = work / f"midiarp_{nm}.json"
                st_ = ["wait:6", f"mem:{ma_mask:#x}:2", f"poke:{ma_mask:#x}:{mask}", f"poke:{ma_mode:#x}:{mode}", "sync",
                       "tap:18", "wait:6", "press:25", "wait:4", "frame:p", "wait:2", "frame:p2",
                       "release:25", "wait:4", "frame:r", f"mem:{ma_mask:#x}:2", f"mem:{ma_mode:#x}:1"]
                cmd_ = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                        "--snapshot", snap, "--steps", ",".join(st_), "--json", js_]
                for va in ma_cnt.values():
                    cmd_ += ["--count", hex(va)]
                ma_runs[nm] = (cmd_, js_)

            def ma_body(tdir):
                res = {}
                for nm, (cmd_, js_) in ma_runs.items():
                    rc, out = run(f"midiarp {nm}", cmd_, logs, env=EMU_ENV, trace=tdir)
                    if rc != 0 or not js_.exists():
                        return False, f"{nm}: " + out[-700:]
                    r = json.loads(js_.read_text())
                    c = {k: r["counts"].get(f"{va:#010x}", 0) for k, va in ma_cnt.items()}
                    fr = {}
                    for f in ("p", "p2", "r"):
                        b = pathlib.Path(r["frames"][f]["file"]).read_bytes()
                        fr[f] = struct.unpack(">2H", b[0x22:0x26])
                    mem = [bytes.fromhex(x) for x in r["memory"].values()]
                    res[nm] = {"counts": c, "frames": fr, "mem": [m.hex() for m in mem]}
                A, B, C = res["midi_arp"], res["midi_off"], res["synth_arp"]
                trig = lambda x: x["frames"]["p"][0] | x["frames"]["p2"][0]     # noqa: E731
                facts = {
                    "the build carries midiarp's edits (its cave's N.LEN lookup included)": bool(MAg.SPEC["edits"]),
                    "the pokes took: track 1 MIDI (mask bit 0) and its arp MODE as set, every run":
                        all(int(x["mem"][1], 16) & 1 == (nm != "synth_arp") for nm, x in res.items())
                        and A["mem"][2] == "01" and B["mem"][2] == "00",
                    "MIDI track, arp on: the key down and up go the synth road (the voice starter), through the "
                    "key gate, never the MIDI sender":
                        A["counts"]["starter"] >= 2 and A["counts"]["sender"] == 0 and A["counts"]["keygate"] >= 2,
                    "MIDI track, arp on: the ISR's voice trigger reaches the MIDI-record hook, and the engine's "
                    "voice trigger is never called for it":
                        A["counts"]["trighook"] >= 1 and A["counts"]["vtrig"] == 0,
                    "negative control, MIDI track with the arp off: the MIDI sender, as stock, never the starter":
                        B["counts"]["sender"] >= 2 and B["counts"]["starter"] == 0,
                    "negative control, a synth track (arp off): the voice starter and a voice, as stock":
                        C["counts"]["starter"] >= 2 and C["counts"]["sender"] == 0 and trig(C) != 0
                        and C["counts"]["vtrig"] >= 1 and C["counts"]["trighook"] >= 1,
                }
                good = all(facts.values())
                return good, ("the arp on a MIDI track: menu-free routing checked on the key forks (synth road with "
                              "the arp on, MIDI sender with it off), the ISR's voice trigger turned into a MIDI record "
                              "with no voice; a synth track as stock" if good else
                              json.dumps({k: x for k, x in facts.items() if not x}) + " " + json.dumps(res)[:1500])
            later("midiarp", "the arp on MIDI tracks (ColdFire)", "the arp on MIDI tracks (ColdFire)",
                  [cmd_ for cmd_, _ in ma_runs.values()] + [sorted(EMU_ENV.items())], ma_body)

        # v0.61: microtuning (csrc/sampler/tune.c, docs/microtuning.md). The frame: tn_retune on 16
        # voices (voice 15 of no track), POOLE ROD12 at ROOT D with every track tuned but track 4:
        # each tuned voice its pitch class's offset, track 4's and voice 15's NOTE words as they
        # were (the negative controls), and 12-TET on every track: nothing moved. The UI: KB SETUP
        # (FUNC + KEYBOARD) draws TUNE in its empty H slot; H turned tunes this track (JUST MAJOR,
        # then JUST MINOR), pushed opens TUNING; A, B, C, D there; YES on a factory tuning stays,
        # on USER 8 opens EDIT, whose B moves the note's cents; NO, NO closes; FUNC + YES copies
        # FROM in. And on the main page (KB SETUP closed) H and its push are stock's: nothing of
        # ours moves (the negative control)
        if "tn_retune" in lay:
            from dnfw.waverider import tunings as TUg     # noqa: PLC0415
            L = {n: lay[n] for n in ("tn_retune", "tn_set", "tn_mask", "tn_cur", "tn_root", "tn_ui", "tn_user", "tn_opens")}
            scratch, vt_va = 0x46A08000, 0x80005308
            vtrack = "".join(f"{v if v < 15 else 0xFF:08x}" for v in range(16))
            words = [((60 + v) << 8) | 0x10 for v in range(16)]
            nw = "0000" + "".join(f"{w:04x}" for w in words)
            M = lambda n, k=4: f"mem:{L[n]:#x}:{k}"                       # noqa: E731
            ts = ["wait:3", f"poke:{vt_va:#x}:{vtrack}"]
            from dnfw.sampler import machines as SMt     # noqa: PLC0415
            ty5 = 0x4210D08C + 52 + 1163 * 5 + 0xDE      # track 6's machine (the snapshot's kit; 1.12: 0x4210D08C)
            for tun, mask in ((9, 0xFFFF & ~(1 << 3)), (0, 0xFFFF)):
                ts += [f"call:{L['tn_set']:#x}:{tun}:2:{mask}", f"poke:{scratch:#x}:{nw}",
                       f"call:{L['tn_retune']:#x}:{scratch:#x}", f"mem:{scratch:#x}:34"]
            # track 6 made a SLICE track: its voice never retuned (the note picks the slice)
            ts += [f"mem:{ty5:#x}:1", f"poke:{ty5:#x}:{SMt.TYPE_OF['SLICE']:02x}",
                   f"call:{L['tn_set']:#x}:9:2:{0xFFFF & ~(1 << 3)}", f"poke:{scratch:#x}:{nw}",
                   f"call:{L['tn_retune']:#x}:{scratch:#x}", f"mem:{scratch:#x}:34"]
            ts += [f"call:{L['tn_set']:#x}:0:0:0"]
            # the negative control first: the main page, H turned and pushed
            ts += ["spin:7:4", "wait:3", "tap:48", "wait:3", M("tn_mask"), M("tn_ui"), "png:main_h"]
            # dn2-wishes (2026-11-19): 30 M instructions (about 225 ms of the panel's clock, 1.1 M a tick, 121 ticks a
            # second), not 6 M (about 45 ms), before KB SETUP's first H turn: stock 1.12 sends no knob item for an
            # encoder turned that soon after the same encoder's push (the push of H on the main page above; measured on
            # stock 1.12's own snapshot: the turn reaches the encoder routine 0x4011FF0C, no item reaches the UI queue)
            ts += ["press:17", "tap:18", "release:17", "wait:30", "png:kb0",
                   "spin:7:2", "wait:3", M("tn_mask"), M("tn_cur"), "png:kb1",
                   "spin:7:2", "wait:3", M("tn_cur"),
                   "tap:48", "wait:3", M("tn_ui"), "png:tuning",
                   "spin:1:3", "wait:2", "spin:3:2", "wait:2", M("tn_root"), M("tn_mask"),
                   "tap:10", "wait:2", M("tn_ui"),
                   "spin:0:30", "wait:2", M("tn_cur"), "tap:10", "wait:2", M("tn_ui"), "png:edit",
                   "spin:1:4", "wait:2", M("tn_user", 192),
                   "spin:3:9", "wait:2", "press:17", "tap:10", "release:17", "wait:2", M("tn_user", 192), "png:edit2",
                   "tap:12", "wait:2", M("tn_ui"), "tap:12", "wait:3", M("tn_ui"), "png:closed"]
            tu_js = work / "tune.json"
            tu_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", ",".join(ts), "--png-dir", work / "tune", "--json", tu_js]

            def tu_body(tdir):
                rc, out = run("microtuning", tu_cmd, logs, env=EMU_ENV, trace=tdir)
                if rc != 0 or not tu_js.exists():
                    return False, out[-900:]
                r = json.loads(tu_js.read_text())
                mem = r["memory"]

                def seq(addr):
                    a_ = hex(addr)
                    ks = sorted((k for k in mem if k == a_ or k.startswith(a_ + "@")),
                                key=lambda k: int(k.split("@")[1]) if "@" in k else -1)
                    return [bytes.fromhex(mem[k]) for k in ks]
                frames = [list(struct.unpack(">17H", b))[1:] for b in seq(scratch)]
                i32s = {n: [struct.unpack(">i", b)[0] for b in seq(L[n])] for n in ("tn_mask", "tn_cur", "tn_root", "tn_ui")}
                users = [list(struct.unpack(">96h", b)) for b in seq(L["tn_user"])]
                pr = TUg.tenths(TUg.FACTORY[9][2])

                def want(skip):
                    o = []
                    for v, w in enumerate(words):
                        pc = ((w >> 8) - 2) % 12
                        n = pr[pc] * 256
                        f = (n + 500) // 1000 if n >= 0 else -((-n + 500) // 1000)
                        o.append(w if v == 15 or v in skip else max(0, min(0x7FFF, w + f)))
                    return o
                shots = {n: pathlib.Path(r["screens"][n]).read_bytes() if n in r["screens"] else b""
                         for n in ("main_h", "kb0", "kb1", "tuning", "edit", "edit2", "closed")}
                mk, cu, ui = i32s["tn_mask"], i32s["tn_cur"], i32s["tn_ui"]
                u8 = TUg.USER_SLOTS - 1                # USER 8
                facts = {
                    "POOLE ROD12 at ROOT D: each tuned voice its offset; track 4's and voice 15's as they were":
                        len(frames) == 3 and frames[0] == want({3}) and frames[0] != words,
                    "12-TET on every track: no NOTE word moved": len(frames) == 3 and frames[1] == words,
                    "a SLICE track's voice never retuned; the others as before":
                        len(frames) == 3 and frames[2] == [w if v == 5 else x for v, (w, x) in enumerate(zip(words, want({3})))]
                        and frames[2] != frames[0],
                    "the main page: H turned and pushed, nothing of ours moved (stock's)":
                        mk[:1] == [0] and ui[:1] == [0],
                    "KB SETUP: H tunes this track (JUST MAJOR, then JUST MINOR)":
                        mk[1:2] == [1] and cu[:2] == [1, 2],
                    "H pushed: TUNING; B ROOT D#, D ALL on": ui[1:2] == [1] and i32s["tn_root"] == [3] and mk[2:3] == [0xFFFF],
                    "YES on a factory tuning: TUNING stays; on USER 8: EDIT":
                        ui[2:4] == [1, 2] and cu[2:3] == [TUg.USER_SLOTS + len(TUg.FACTORY) - 1],
                    "EDIT: B moves the note's cents by whole cents; FUNC + YES copies FROM (POOLE ROD12) in":
                        len(users) == 2 and users[0][12 * u8] == 40
                        and users[1][12 * u8:12 * u8 + 12] == TUg.tenths(TUg.FACTORY[9][2]),
                    "NO back to TUNING, NO closes": ui[4:6] == [1, 0],
                    "the screens drawn, each its own": all(shots.values()) and len(set(shots.values())) == len(shots),
                }
                good = all(facts.values())
                return good, ("tn_retune tunes only tuned tracks' voices by their pitch class; KB SETUP's H and the "
                              "TUNING / EDIT pages work; H elsewhere is stock's" if good else
                              json.dumps({k: v for k, v in facts.items() if not v}) + f" frames={frames} i32={i32s} "
                              f"users={[u[84:96] for u in users]}")
            later("tune", "microtuning: KB SETUP's TUNE, the TUNING page, the frame's retune (ColdFire)",
                  "microtuning: KB SETUP's TUNE, the TUNING page, the frame's retune (ColdFire)",
                  [tu_cmd, sorted(EMU_ENV.items())], tu_body)

        # v0.61: each project's tuning record (scripts/emu_tune.py: power-on, a change written
        # after two seconds into its own sectors, LOAD / NEW / a power cycle, a corrupted copy, both
        # corrupted, another project's record refused, ERASE's lock, every write in its region)
        if "tn_poll" in lay:
            tr_syms = work / "tune_syms.json"
            tr_syms.write_text(json.dumps({k: v for k, v in lay.items() if k.startswith(("smp_", "tn_", "dm_"))}))
            tr_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", f"link16:{tr_syms}:tune", "--png-dir", work / "tunerec"]

            def tr_body(tdir):
                rc, out = run("tuning record", tr_cmd, logs, env=EMU_ENV, trace=tdir)
                res = work / "tunerec" / "link16_tune.json"
                if rc != 0 or not res.exists():
                    return False, out[-900:]
                r = json.loads(res.read_text())
                facts = r.get("facts", {})
                good = bool(r.get("ok")) and len(facts) >= 9 and all(facts.values())
                return good, ("each project's tuning: written after two seconds into its own sectors, read on "
                              "LOAD and at power-on, reset by NEW, a corrupted copy falls back, another project's "
                              "refused, nothing written under ERASE's lock, every write in its region" if good else
                              json.dumps({k: v for k, v in facts.items() if not v})[:800] + f" writes={r.get('writes')}")
            later("tunerec", "microtuning: each project's tuning record (ColdFire)",
                  "microtuning: each project's tuning record (ColdFire)", [tr_cmd, sorted(EMU_ENV.items())], tr_body)

        # v0.69: PERFORM (csrc/sampler/perf.c, docs/perform.md). The UI: [FX] alone is stock's (the FX
        # page; nothing of ours opens); [MOD] held + [FX]: PERFORM; A pushed: MODULATION SETUP for
        # macro A; F takes target 1 to track 1 (its first LFO destination), G to the next, A sets its
        # depth (+30); NO back to PERFORM, where A turned moves macro A; FUNC + YES twice: PERF MUTE on
        # and off; FUNC + A pushed: macro A back to 0; [MOD] + [FX] again: closed. Every screen drawn,
        # each its own
        if "pf_poll" in lay:
            L = {n: lay[n] for n in ("pf", "pf_ui", "pf_sel", "pf_mute", "pf_opens")}
            M = lambda n, k=4: f"mem:{L[n]:#x}:{k}"                       # noqa: E731
            ps = ["wait:6", "tap:5", "wait:20", M("pf_ui"), "png:fx_alone",
                  "press:6", "wait:10", "tap:5", "wait:20", "release:6", "wait:10", M("pf_ui"), "png:perform",
                  "tap:41", "wait:20", M("pf_ui"), M("pf_sel"), "png:setup0",
                  "spin:5:2", "wait:10", M("pf", 26), "spin:6:2", "wait:10", M("pf", 26),
                  "spin:0:30", "wait:10", M("pf", 26), "png:setup1",
                  "tap:12", "wait:10", M("pf_ui"), "spin:0:20", "wait:10", M("pf", 26), "png:turned",
                  "press:17", "tap:10", "release:17", "wait:10", M("pf_mute"), "png:muted",
                  "press:17", "tap:10", "release:17", "wait:10", M("pf_mute"),
                  "press:17", "tap:41", "release:17", "wait:10", M("pf", 26),
                  "press:6", "wait:10", "tap:5", "wait:20", "release:6", "wait:10", M("pf_ui"), "png:closed"]
            pf_js = work / "perform.json"
            pf_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", ",".join(ps), "--png-dir", work / "perform", "--json", pf_js]

            def pf_body(tdir):
                rc, out = run("PERFORM", pf_cmd, logs, env=EMU_ENV, trace=tdir)
                if rc != 0 or not pf_js.exists():
                    return False, out[-900:]
                r = json.loads(pf_js.read_text())
                mem = r["memory"]

                def seq(addr):
                    a_ = hex(addr)
                    ks = sorted((k for k in mem if k == a_ or k.startswith(a_ + "@")),
                                key=lambda k: int(k.split("@")[1]) if "@" in k else -1)
                    return [bytes.fromhex(mem[k]) for k in ks]
                ui = [struct.unpack(">i", b)[0] for b in seq(L["pf_ui"])]
                sel = [struct.unpack(">i", b)[0] for b in seq(L["pf_sel"])]
                mute = [struct.unpack(">i", b)[0] for b in seq(L["pf_mute"])]
                A = [(b[11], b[12], struct.unpack(">b", b[13:14])[0], struct.unpack(">b", b[10:11])[0]) for b in seq(L["pf"])]
                shots = {n: pathlib.Path(r["screens"][n]).read_bytes() if n in r["screens"] else b""
                         for n in ("perform", "setup0", "setup1", "turned", "muted", "closed")}
                facts = {
                    "[FX] alone: stock's (nothing of ours opens)": ui[:1] == [0],
                    "[MOD] held + [FX]: PERFORM": ui[1:2] == [1],
                    "A pushed: MODULATION SETUP for macro A": ui[2:3] == [2] and sel[:1] == [0],
                    "F: target 1 on track 1 (a destination); G: the next; A: its depth +30":
                        len(A) >= 3 and A[0][0] == 0 and A[1][0] == 0 and A[1][1] != A[0][1] and A[2][2] == 30,
                    "NO: PERFORM; A turned: macro A's value": ui[3:4] == [1] and len(A) >= 4 and A[3][3] > 0,
                    "FUNC + YES: PERF MUTE on, again off": mute == [1, 0],
                    "FUNC + A pushed: macro A back to 0": len(A) >= 5 and A[4][3] == 0 and A[4][:3] == A[3][:3],
                    "[MOD] + [FX] again: closed": ui[-1:] == [0] and len(ui) == 5,
                    "the screens drawn, each its own": all(shots.values()) and len(set(shots.values())) == len(shots),
                }
                good = all(facts.values())
                return good, ("[MOD] + [FX] opens PERFORM and closes it, [FX] alone is stock's; MODULATION SETUP sets a "
                              "target's track, destination and depth; the macros turn, PERF MUTE and FUNC + push work" if good
                              else json.dumps({k: v for k, v in facts.items() if not v}) + f" ui={ui} sel={sel} mute={mute} A={A}")
            later("perform", "PERFORM: [MOD] + [FX], the macros, MODULATION SETUP, PERF MUTE (ColdFire)",
                  "PERFORM: [MOD] + [FX], the macros, MODULATION SETUP, PERF MUTE (ColdFire)",
                  [pf_cmd, sorted(EMU_ENV.items())], pf_body)

        # v0.69: PERFORM's offsets and each project's macros record (scripts/emu_perform.py: the offset
        # on the mirror, no piling up, two macros adding, bipolar, PERF MUTE, clamped, the sound untouched;
        # power-on, a change written after two seconds into its own sectors, LOAD / NEW / a power cycle,
        # corrupted copies, another project's record refused, ERASE's lock, every write in its region)
        if "pf_poll" in lay:
            pr_syms = work / "perform_syms.json"
            pr_syms.write_text(json.dumps({k: v for k, v in lay.items() if k.startswith(("smp_", "pf"))}))
            pr_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", f"link16:{pr_syms}:perform", "--png-dir", work / "performrec"]

            def pr_body(tdir):
                rc, out = run("PERFORM record", pr_cmd, logs, env=EMU_ENV, trace=tdir)
                res = work / "performrec" / "link16_perform.json"
                if rc != 0 or not res.exists():
                    return False, out[-900:]
                r = json.loads(res.read_text())
                facts = r.get("facts", {})
                good = bool(r.get("ok")) and len(facts) >= 9 and all(facts.values())
                return good, ("the macros' offsets land on the mirror exactly and come off again; each project's "
                              "macros written after two seconds into their own sectors, read on LOAD and at power-on, "
                              "reset by NEW, a corrupted copy falls back, nothing written under ERASE's lock, every "
                              "write in its region" if good else
                              json.dumps({k: v for k, v in facts.items() if not v})[:800]
                              + f" offsets={r.get('offsets')} writes={r.get('writes')}")
            later("performrec", "PERFORM: the offsets and each project's macros record (ColdFire)",
                  "PERFORM: the offsets and each project's macros record (ColdFire)",
                  [pr_cmd, sorted(EMU_ENV.items())], pr_body)

        # 2026-11-22 (v0.69.1, the User: "move our stuff"): the inserts' records from 0x6E0400.. (upstream's
        # tunings and PERFORM) to 0x5FF000.., moved once at power-on with a mark (csrc/inserts/store.c
        # move_once; scripts/emu_ins_move.py): v0.67.5's records copied byte for byte, a project loads its
        # inserts, PERFORM empty over the old working copy, no second move, an erase brings nothing back
        if "ins_st_moved" in lay:
            im_syms = work / "insmove_syms.json"
            im_syms.write_text(json.dumps(lay))
            im_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", f"link16:{im_syms}:insmove", "--png-dir", work / "insmove"]

            def im_body(tdir):
                rc, out = run("insmove", im_cmd, logs, env=EMU_ENV, trace=tdir)
                res = work / "insmove" / "link16_insmove.json"
                if rc != 0 or not res.exists():
                    return False, f"the harness did not finish (rc {rc})"
                r = json.loads(res.read_text())
                bad = [k for k, v in r.get("facts", {}).items() if not v]
                return (bool(r.get("ok")) and not bad), (f"{len(r.get('facts', {}))} facts" if not bad else
                                                        f"failed: {bad} notes={r.get('notes')}")
            later("insmove", "the inserts' records moved off upstream's sectors, old projects converted (ColdFire)",
                  "the inserts' records moved off upstream's sectors, old projects converted (ColdFire)",
                  [im_cmd, sorted(EMU_ENV.items())], im_body)

        # v0.69.2 (the User: "our +Drive data lives where upstream names nothing"): csrc/sampler/dmove.c moves our
        # tunings (to upstream's 0x6E0400), the bank lists (back to upstream's 0x6E0600 / 0x6F0800), the wishes record
        # (to 0x5D8000, 92,160 cells, filed again) and, when their boot-time moves could not, SAFE MODE's record and
        # the DSP copy; once, the old places only read (scripts/emu_drive_move.py)
        if "dm_run" in lay:
            dv_syms = work / "drivemove_syms.json"
            dv_syms.write_text(json.dumps(lay))
            dv_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", f"link16:{dv_syms}:drivemove", "--png-dir", work / "drivemove"]

            def dv_body(tdir):
                rc, out = run("drivemove", dv_cmd, logs, env=EMU_ENV, trace=tdir)
                res = work / "drivemove" / "link16_drivemove.json"
                if rc != 0 or not res.exists():
                    return False, f"the harness did not finish (rc {rc}) " + out[-600:]
                r = json.loads(res.read_text())
                bad = [k for k, v in r.get("facts", {}).items() if not v]
                return (bool(r.get("ok")) and not bad and len(r.get("facts", {})) >= 9), (
                    f"{len(r.get('facts', {}))} facts" if not bad else f"failed: {bad} notes={r.get('notes')}")
            later("drivemove", "our +Drive data out of upstream's places: tunings, bank lists, wishes, SAFE, DSP copy (ColdFire)",
                  "our +Drive data out of upstream's places: tunings, bank lists, wishes, SAFE, DSP copy (ColdFire)",
                  [dv_cmd, sorted(EMU_ENV.items())], dv_body)

        # (v0.69's guardrail step is not ours: the guardrail is left out, VOICE BUDGET prices the notes;
        # docs/guardrail-vs-voice-budget.md, the User 2026-11-22)

        # v0.62: the slice editor's requests (impbox; scripts/emu_slicefine.py, the +Drive and the
        # DSP played by Python): an edit goes to the DSP and the +Drive 0.2 s after the knobs rest
        # (not while they move); FUNC + END lands on a zero crossing, the linked start with it
        # (END alone: no snap); ZOOM to a view of 128..255 frames, the view's own frames read and
        # drawn as the sample's lowest and highest per column (zoom 0: none read); a note on the
        # editor's track picks its slice (another track's, or SLCE fixed: nothing); NO keeps it all
        if "slc_live_sends" in lay:
            sf_syms = work / "slicefine_syms.json"
            sf_syms.write_text(json.dumps({k: v for k, v in lay.items() if k.startswith(("smp_", "slc_", "wr_"))}))
            sf_cmd = [a.venv, "-u", "scripts/emu_waverider_menu.py", "--root", ROOT, "--build", bdir,
                      "--snapshot", snap, "--steps", f"link16:{sf_syms}:slicefine", "--png-dir", work / "slicefine"]

            def sf_body(tdir):
                rc, out = run("slice editor", sf_cmd, logs, env=EMU_ENV, trace=tdir)
                res = work / "slicefine" / "link16_slicefine.json"
                if rc != 0 or not res.exists():
                    return False, out[-900:]
                r = json.loads(res.read_text())
                facts = r.get("facts", {})
                good = bool(r.get("ok")) and len(facts) >= 6 and all(facts.values())
                return good, ("the slice editor: live edits 0.2 s after the knobs rest, FUNC + END on a zero "
                              "crossing, the view's own frames at deep zoom, a played slice picked, all kept" if good else
                              json.dumps({k: v for k, v in facts.items() if not v})[:600] + f" {r.get('detail')}"[:300])
            later("slicefine", "SLICE editor: live edits, zero-crossing snap, deep zoom, a played slice picked (ColdFire)",
                  "SLICE editor: live edits, zero-crossing snap, deep zoom, a played slice picked (ColdFire)",
                  [sf_cmd, sorted(EMU_ENV.items())], sf_body)

        # v0.48 (Error Kit): THRES on the coupled emulator (emu_coupled.py: the ColdFire and the
        # DSP together, block by block): a -34 dB tone on IN; THRES 30 (tick -45 dB) starts the
        # take on the ARM; THRES 110 holds it back, and turned to 30 while armed it starts
        th_js = work / "thres.json"
        th_cmd = [a.coupled_py, "-u", "scripts/emu_coupled_thres.py", "--build", a.build, "--stock", a.stock,
                  "--snapshot", snap, "--json", th_js]

        def th_body(tdir):
            rc, out = run("thres coupled", th_cmd, logs, env=EMU_ENV, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0 or not last.startswith("PASS"):
                return False, out[-900:]
            return True, (f"{last[6:]}: on the ColdFire and the DSP together, a -34 dB tone on IN: THRES 30 (its "
                          f"tick at -45 dB) starts the take on the ARM; THRES 110 holds it back, and turned to 30 "
                          f"while armed, it starts without a new ARM")
        later("thres", "THRES on both processors (coupled)", "THRES on both processors (coupled)",
              [th_cmd, sorted(EMU_ENV.items())], th_body)

        # 2026-11-13 (round 14 played nothing on the unit; no step played a note through both processors): a held
        # KEYBOARD note on stock track 2 (type 0), the ColdFire and the DSP together (emu_coupled_stocknote.py, the
        # stock smoother modelled); its voice must sound. Must pass on ours whatever clean does (report.MUST_PASS)
        sn_js = work / "stocknote.json"
        sn_cmd = [a.coupled_py, "-u", "scripts/emu_coupled_stocknote.py", "--build", a.build, "--stock", a.stock,
                  "--snapshot", snap, "--json", sn_js]

        def sn_body(tdir):
            rc, out = run("stock note coupled", sn_cmd, logs, env=EMU_ENV, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0 or not last.startswith("PASS"):
                return False, out[-900:]
            return True, "a held note on stock track 2 sounds through the ColdFire and the DSP together"
        later("stocknote", "a stock note through both processors (coupled)",
              "a stock note through both processors (coupled)", [sn_cmd, sorted(EMU_ENV.items())], sn_body)

        # 2026-11-14 (the GATE GAP of 2026-11-13: our machines never sounded from a real ColdFire frame): the same for
        # DRONE and JUNO, each put on track 3 by MACHINE SEL's commit and played in its own run (voice slot 0), and
        # DRONE once more after 15 short stock notes on track 2, so its note lands on voice slot 15 (the runner's
        # G12-G14 and the warm snapshot built under them: every slot sounds as slot 0, docs/coupled-emulator.md).
        # Track 3's filter is the Multimode: the stock Equalizer gives NaN in the harness whatever the machine. Must
        # pass on ours
        on_runs = [(name, [a.coupled_py, "-u", "scripts/emu_coupled_stocknote.py", "--build", a.build, "--stock",
                           a.stock, "--snapshot", snap, "--tracks", "", "--ours", spec, *extra,
                           "--json", work / f"ournote_{name}.json"])
                   for name, spec, extra in (("drone", "2:52", ()), ("juno", "2:50", ()),
                                             ("drone15", "2:52", ("--advance", "15", "--expect-slot", "15")))]

        def on_body(tdir):
            for name, cmd in on_runs:
                rc, out = run(f"our note coupled ({name})", cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, f"{name}: " + out[-900:]
            return True, ("a held note on DRONE and on JUNO (track 3, each its own run), and on DRONE on voice slot 15, "
                          "sounds through both processors")
        later("ournote", "our machines' notes through both processors (coupled)",
              "our machines' notes through both processors (coupled)",
              [[c for _n, c in on_runs], sorted(EMU_ENV.items())], on_body)

        # 2026-11-17 (v0.57.1 on the unit, a8fbf921: a PARA chord took one slot but only its lowest note sounded; the
        # ColdFire check and the runner's rows came before the note-on, the TDM link's come after): a 3-note PARA chord
        # on JUNO and on ANALOG 2 (track 3) through both processors: one slot, its row as the link wrote it, every
        # note's fundamental in the leader's render (emu_coupled_para.py)
        pc_runs = [(name, [a.coupled_py, "-u", "scripts/emu_coupled_para.py", "--build", a.build, "--stock", a.stock,
                           "--snapshot", snap, "--engine", str(ty), "--json", work / f"parachord_{name}.json"])
                   for name, ty in (("juno", 50), ("analog2", 51))]

        def pc_body(tdir):
            for name, cmd in pc_runs:
                rc, out = run(f"para chord coupled ({name})", cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, f"{name}: " + out[-900:]
            return True, ("a 3-note PARA chord on JUNO and on ANALOG 2 plays on one voice slot through both "
                          "processors, every note heard in its render")
        later("parachord", "a PARA chord through both processors: one slot, every note heard (coupled)",
              "a PARA chord through both processors: one slot, every note heard (coupled)",
              [[c for _n, c in pc_runs], sorted(EMU_ENV.items())], pc_body)

        # 2026-11-18 (v0.59.1 on the unit: chords never ended, joined notes ended a frame after they joined, no key-up
        # released a member): PARA chords of 3, 4, 6 and 8 notes played on the KEYBOARD 0, 1, 5 and 20 ms apart through
        # the ColdFire's own UI, ISR and allocator: one start and N - 1 joins, every note held to its own key-up, the
        # chord's note-off when the last key is up, the chord kept for the DSP's release tail and ended once the DSP
        # reports its slot quiet (scripts/emu_coupled_paralive.py)
        pl_js = work / "paralive.json"
        pl_cmd = [a.coupled_py, "-u", "scripts/emu_coupled_paralive.py", "--build", a.build, "--stock", a.stock,
                  "--snapshot", snap, "--json", pl_js]

        def pl_body(tdir):
            rc, out = run("paralive", pl_cmd, logs, env=EMU_ENV, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0 or not last.startswith("PASS"):
                return False, "\n".join(ln for ln in out.splitlines() if "FAIL" in ln)[-900:] or out[-900:]
            return True, next((ln for ln in out.splitlines() if "checks pass" in ln), last).strip()
        later("paralive", "PARA chords played live: every note joins and is held to its own key-up, a chord ends after "
              "its tail (ColdFire)", "PARA chords played live (ColdFire)", [pl_cmd, sorted(EMU_ENV.items())], pl_body)

        # v0.49 FLEX on the coupled emulator (emu_coupled.py: the ColdFire and the DSP together): a
        # one-shot recorder trig on step 1 placed with [TRIG 1] on FLEX REC, PLAY, the DSP's take into
        # buffer 1 (the input to the sample), the one-shot spent, then a FLEX note playing the take
        # (its render read after the voices, correlated with the take)
        fx_js = work / "flex.json"
        fx_cmd = [a.coupled_py, "-u", "scripts/emu_coupled_flex.py", "--build", a.build, "--stock", a.stock,
                  "--snapshot", snap, "--json", fx_js]

        def fx_body(tdir):
            rc, out = run("flex coupled", fx_cmd, logs, env=EMU_ENV, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0 or not last.startswith("PASS"):
                return False, out[-900:]
            return True, ("on the ColdFire and the DSP together: [TRIG 1] on FLEX REC places a one-shot on step "
                          "1; the step fires it, the DSP records R.LEN into buffer 1 (the input, sample for "
                          "sample), the one-shot is spent; a FLEX note plays the take (the voice's render "
                          "correlates with it)")
        later("flex", "FLEX: a recorder trig's take played by a note, on both processors (coupled)",
              "FLEX: a recorder trig's take played by a note, on both processors (coupled)",
              [fx_cmd, sorted(EMU_ENV.items())], fx_body)

        # v0.55 (owner: the FLEX buffers in every sample machine): the take recorded as in flex,
        # then a ONESHOT track on SAMP B1 plays it (emu_coupled_flex.py --pool, links P0..P3)
        if "rt_buf_code" in lay:
            fp_js = work / "flexplay.json"
            fp_cmd = [a.coupled_py, "-u", "scripts/emu_coupled_flex.py", "--build", a.build, "--stock", a.stock,
                      "--snapshot", snap, "--pool", "--json", fp_js]

            def fp_body(tdir):
                rc, out = run("flexplay coupled", fp_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, out[-900:]
                return True, ("on the ColdFire and the DSP together: a take recorded into buffer 1; a ONESHOT "
                              "track on SAMP B1: its voice sent buffer 1's playing half (SAMP 129), the DSP "
                              "renders it, the render is the take at the note's pitch; v0.57: MUTE SRC holds "
                              "its SRC muted only while the FLEX track plays the take (M1..M3)")
            later("flexplay", "FLEX buffers played by a ONESHOT track, on both processors (coupled)",
                  "FLEX buffers played by a ONESHOT track, on both processors (coupled)",
                  [fp_cmd, sorted(EMU_ENV.items())], fp_body)

        # v0.52 FLEX MUTE SRC (owner, option B): knob H on REC SETUP turns it ON; a note on the SRC
        # track: its voices' frame LEVEL and FX sends 0 (the DSP's LEVEL too), the other voices' as
        # unmuted, its block after the chain (the TRK source) as loud; OFF gives them back
        if "ms_frame" in lay:
            mu_js = work / "mute.json"
            mu_cmd = [a.coupled_py, "-u", "scripts/emu_coupled_mute.py", "--build", a.build, "--stock", a.stock,
                      "--snapshot", snap, "--json", mu_js]

            def mu_body(tdir):
                rc, out = run("mute coupled", mu_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, out[-900:]
                return True, ("on the ColdFire and the DSP together: knob H on FLEX REC SETUP turns MUTE ON; the "
                              "SRC track's voices get LEVEL and FX sends 0 in the frame and the DSP, the other "
                              "voices' LEVEL unchanged, its block after the chain (the TRK source) as loud; OFF "
                              "gives LEVEL and the sends back; v0.57: none of it without a take, or while the "
                              "FLEX track is not playing (1b..1e)")
            later("mute", "FLEX MUTE SRC: the SRC track out of the mix, still recorded, on both processors (coupled)",
                  "FLEX MUTE SRC: the SRC track out of the mix, still recorded, on both processors (coupled)",
                  [mu_cmd, sorted(EMU_ENV.items())], mu_body)

        # v0.48 (impbox, the owner: "exact dt2"): STRT, LEN, LOOP's fine records (fmt.c
        # smp_fine), on the ColdFire emulator: swapped in on ONESHOT/STRETCH/REPITCH/BOUNCE,
        # every byte back on WaveTone, none on GRID/SLICE/WERP, a fresh machine's LEN 120.00
        fs_js = work / "fineswap.json"
        fs_cmd = [a.venv, "-u", "scripts/emu_fine_swap.py", "--build", a.build, "--snapshot", snap, "--json", fs_js]

        def fs_body(tdir):
            rc, out = run("fine swap", fs_cmd, logs, env=EMU_ENV, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0:
                return False, "\n".join(l for l in out.splitlines() if l.startswith("FAIL"))[-900:] or out[-900:]
            return True, (f"{last}: STRT/LEN/LOOP carry FREQ's fine words while ONESHOT (all three), STRETCH, "
                          f"REPITCH, BOUNCE (STRT, LEN) is the active track; every byte of the records and "
                          f"runtime entries back on WaveTone; none on GRID, SLICE, WERP; a fine STRT kept "
                          f"through track changes; a fresh machine's LEN at 120.00")
        later("fineswap", "STRT/LEN/LOOP fine records swapped in and out (ColdFire)",
              "STRT/LEN/LOOP fine records swapped in and out (ColdFire)", [fs_cmd, sorted(EMU_ENV.items())], fs_body)

        # ... and STRT's knob: every knob step with the inputs of one of stock FREQ's makes
        # the same change (emu_fine_knob.py over emu_encoder_trace.py)
        fk_js = work / "fineknob.json"
        fk_cmd = [a.venv, "-u", "scripts/emu_fine_knob.py", "--build", a.build, "--snapshot", snap, "--json", fk_js]

        def fk_body(tdir):
            rc, out = run("fine knob", fk_cmd, logs, env=EMU_ENV, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0 or not last.startswith("PASS"):
                return False, out[-900:]
            return True, last[6:]
        later("fineknob", "STRT's knob against stock's fine FREQ (ColdFire)",
              "STRT's knob against stock's fine FREQ (ColdFire)", [fk_cmd, sorted(EMU_ENV.items())], fk_body)

        # 2026-11-11 (owner: "Open 13 closed controls, Moving controls, Feedback is okay for lfo";
        # docs/modulation-more.md, scripts/emu_modulation.py): the destination builder called for
        # LFO1-3 and MOD SETUP on WaveTone, FM TONE and PERC against stock's lists; the frame's LFO
        # path called by hand with LFO1 <-> LFO2 SPD at full depth (heard one frame late, bounded,
        # also at the speeds' extremes), and its cost against its bounds; the FLTR page's FREQ cell
        # drawing its heard-value line
        mo_js = work / "modulation.json"
        mo_cmd = [a.venv, "-u", "scripts/emu_modulation.py", "--build", a.build, "--snapshot", snap, "--json", mo_js]

        def mo_body(tdir):
            rc, out = run("modulation", mo_cmd, logs, env=EMU_ENV, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0 or not last.startswith("PASS"):
                return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
            return True, (f"{last[6:]}: every stock list kept, the 13 closed records and the other LFOs' "
                          f"controls added (never an LFO's own, never DEST); LFO1 -> LFO2 SPD heard one frame "
                          f"late, every cell in range, the cost under its bounds; the heard-value line drawn, "
                          f"redrawn and let go")
        later("modulation", "modulation: the destination lists, the LFO cascade, the moving controls (ColdFire)",
              "modulation: the destination lists, the LFO cascade, the moving controls (ColdFire)",
              [mo_cmd, sorted(EMU_ENV.items())], mo_body)

        # 6m2b. 2026-11-17 (the User: "why do we redraw the whole screen? we could redraw only the knob/line?"): a
        # moving line rewritten alone in BACK and its groups sent (csrc/modulation/moving.c mv_lines_only).
        # scripts/emu_line_redraw.py: the glass modelled from every group sent; after every step (MONOMACHINE's,
        # MACHINEDRUM's, ONESHOT's and WaveTone's pages, page changes, the meter, the routes popup and the inserts
        # overview over moving lines, the test channel's inverted glass) the glass is BACK and a full redraw then
        # draws exactly BACK; the cells left clean move alone; the cost against the full path
        if "mv_end" in lay:
            lo_work = work / "lineonly"
            lo_cmd = [a.venv, "-u", "scripts/emu_line_redraw.py", "--build", a.build, "--snapshot", snap,
                      "--work", lo_work]

            def lo_body(tdir):
                rc, out = run("lines alone", lo_cmd, logs, env=EMU_ENV, trace=tdir)
                good = rc == 0 and "LINES OK" in out
                return good, ("every step: the glass as a full redraw would draw it (pages, page changes, the meter, "
                              "the routes popup, the inserts overview, the inverted glass); the clean cells' lines "
                              "moved alone" if good else "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:]
                              or out[-900:])
            later("lineonly", "moving lines updated alone: the glass always as a full redraw (ColdFire)",
                  "moving lines updated alone: the glass always as a full redraw (ColdFire)",
                  [lo_cmd, sorted(EMU_ENV.items())], lo_body)

        # 6m2c. 2026-11-17 (the User: "oscilloscope is creating cpu issues", "the ui [is] lagging behind"): the scope's
        # frames drawn alone (BACK copied, the scope drawn over it, stock's panel_diff), word-wise, and only when the
        # panel UART's ring is all but empty (csrc/scope/scope.c). scripts/emu_scope.py --proof: the UART at the unit's
        # 156,250 baud; every frame drawn alone has the strip v1's SET_PIXEL drawing gives for the same ring, pixel for
        # pixel, and a full redraw then draws exactly the glass
        # 2026-11-21 (gate gaps): every write of the scope's own code in its place (scripts/scope_area.py: scope_draw's
        # canvas pixels in x 18..127, rows 0..53; elsewhere only its C chunk and its stack), a stub's stray writes seen
        # (control); after the page out and in, a track change and back, the title's message runs out and a full redraw
        # draws the glass (a title left standing seen: control)
        if "scope_alone" in lay:
            sc_work = work / "scope"
            sc_cmd = [a.venv, "-u", "scripts/emu_scope.py", "--build", a.build, "--snapshot", snap, "--work", sc_work,
                      "--feed", "noise", "--proof"]

            def sc_body(tdir):
                rc, out = run("scope", sc_cmd, logs, env=EMU_ENV, trace=tdir)
                good = rc == 0 and "SCOPE OK" in out
                return good, ("every scope frame drawn alone as v1 drew it, a full redraw the same as the glass, the UART "
                              "at the unit's rate; every gain reached and drawn as the model, AUTO below x1 on full scale "
                              "with no edge-row pixel, back up to x16 when quiet; every write of its code in its place "
                              "(a stray write seen); the title back after every page and track change"
                              if good else "\n".join(l for l in out.splitlines() if "proof" in l or "area" in l
                                                     or "autozoom" in l or "FAIL" in l)[-900:] or out[-900:])
            later("scope", "the oscilloscope: its frames as v1 drew them, alone, never queued behind the panel UART; every gain x1/8..x16, AUTO below x1 on full scale and never on an edge row (ColdFire)",
                  "the oscilloscope: its frames as v1 drew them, alone, never queued behind the panel UART; every gain x1/8..x16, AUTO below x1 on full scale and never on an edge row (ColdFire)",
                  [sc_cmd, sorted(EMU_ENV.items())], sc_body)

        # 6m2d. 2026-11-20 (the User: the alert and the mixer pages' meters; scratch/mixer-overview.md): the meters on
        # Internal Mixer 2/5, 3/5, FX Mixer 4/5, External Mixer 5/5 exactly as the model draws them over stock's page
        # (every other pixel stock's), alone updates the glass a full redraw draws, nothing over Compressor 1/5, a SYN
        # page or the TEMPO screen, the latches' and the CLIP label's timing, the outputs in use
        if "mix_poll" in lay:
            mm_work = work / "mixmeter"
            mm_cmd = [a.venv, "-u", "scripts/emu_mixmeter.py", "--build", a.build, "--snapshot", snap, "--work", mm_work]

            def mm_body(tdir):
                rc, out = run("mixmeter", mm_cmd, logs, env=EMU_ENV, trace=tdir)
                good = rc == 0 and "MIXMETER OK" in out
                return good, ("the meters on 2/5..5/5 as the model over stock's pixels, every other pixel stock's; "
                              "updates alone the glass a full redraw draws; latches and the CLIP label on time; "
                              "the outputs in use" if good else
                              "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:])
            later("mixmeter", "the MIXER pages' meters over stock's pixels, alone updates, latches and the CLIP label (ColdFire)",
                  "the MIXER pages' meters over stock's pixels, alone updates, latches and the CLIP label (ColdFire)",
                  [mm_cmd, sorted(EMU_ENV.items())], mm_body)

        # 6m2d2. 2026-11-21 (the User: "a MIXER OVERVIEW ... a LONG PRESS of FUNC + MOD", "all channels, return and main"):
        # csrc/inserts/ovw.c (FUNC + [MOD]'s press held back, the tap played on an early release), ovw_draw.c mix_view,
        # csrc/meter/mixer.c (the levels 10 a second). scripts/emu_mix_overview.py: a tap opens and steps stock's MIXER;
        # held a second the overview, pixel for pixel dnfw.overviews.outs_render with the levels and marks read back
        # (2026-11-21: the OUTPUTS overview in its place, every fixed-point output; Overbridge, USB audio, recording);
        # let go, the screen of before (over the MIXER: the MIXER page as before); another key: no overview; the cost
        # under 1 % of the CPU with every bar moving; stock 1.12 as the negative control
        if "mix_ovw_takes" in lay:
            mo_work = work / "mixovw"
            mo_cmd = [a.venv, "-u", "scripts/emu_mix_overview.py", "--build", a.build, "--snapshot", snap,
                      "--work", mo_work]

            def mo_body(tdir):
                rc, out = run("mixovw", mo_cmd, logs, env=EMU_ENV, trace=tdir)
                good = rc == 0 and "MIXER OVERVIEW OK" in out
                return good, ("FUNC + [MOD]: a tap stock's MIXER; held a second the overview as the model; let go, the "
                              "screen of before; the cost under 1 % of the CPU" if good else
                              "\n".join(l for l in out.splitlines() if "BAD" in l or "cost" in l)[-900:] or out[-900:])
            mo_what = ("the OUTPUTS overview: FUNC + [MOD] held a second, every fixed-point output and its clip marks, "
                       "live; a tap still opens stock's MIXER; let go, the screen of before (ColdFire)")   # (the trace
            # folder is named after it: a longer one passes the file system's 255 bytes)
            later("mixovw", mo_what, mo_what, [mo_cmd, sorted(EMU_ENV.items())], mo_body)

        # 6m2d3. 2026-11-21 (the User: the CPU/RAM overview "on a long press of the METRONOME button and not FUNC
        # click-and-hold"; "SAMPLE BROWSER on a long press of PRESET"): csrc/inserts/ovw.c. scripts/emu_long_keys.py:
        # [TEMPO] and [PRESET] taps, half-second holds, FUNC + each pixel for pixel stock 1.12's; held a second the meter
        # (gone at the release, no TEMPO screen) and the browser (LOAD TRK on a sample track, browse only otherwise; up
        # after the release, no PRESET menu); stock 1.12 as the negative control
        if "ovw_tempo_opens" in lay:
            lk_work = work / "longkeys"
            lk_cmd = [a.venv, "-u", "scripts/emu_long_keys.py", "--build", a.build, "--snapshot", snap,
                      "--work", lk_work]

            def lk_body(tdir):
                rc, out = run("longkeys", lk_cmd, logs, env=EMU_ENV, trace=tdir)
                good = rc == 0 and "LONG KEYS OK" in out
                return good, ("[TEMPO] and [PRESET]: taps and FUNC combos as stock; held a second the meter and the "
                              "browser" if good else
                              "\n".join(l for l in out.splitlines() if "BAD" in l)[-900:] or out[-900:])
            lk_what = ("[TEMPO] held a second: the system meter; [PRESET] held a second: the sample browser (browse only "
                       "on a track with no sample machine); their taps and FUNC combos as stock (ColdFire)")
            later("longkeys", lk_what, lk_what, [lk_cmd, sorted(EMU_ENV.items())], lk_body)

        # 6m2e. 2026-11-20 (the User on the unit: "cpu is 94%", "we need to optimise mixer pages"): stock redraws the
        # MIXER pages in full 30 times a second and our meters with every draw; the User: "10 per sec is fine" (held in
        # mixer.c mix_dirty, a key or knob drawn at once); the meters' cost on each page with every meter moving (on
        # against off, the panel UART at the unit's rate) and a full draw's meters under scripts/emu_mixcpu.py's LIMITS,
        # so it cannot grow back unseen
        if "mix_poll" in lay:
            mc_work = work / "mixcpu"
            mc_cmd = [a.venv, "-u", "scripts/emu_mixcpu.py", "--build", a.build, "--snapshot", snap, "--work", mc_work,
                      "--check"]

            def mc_body(tdir):
                rc, out = run("mixcpu", mc_cmd, logs, env=EMU_ENV, trace=tdir)
                good = rc == 0 and "MIXCPU OK" in out
                return good, ("stock's MIXER redraws at 10 a second, a knob drawn at once; the meters' CPU on 2/5..5/5 under its ceilings"
                              if good else "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:])
            later("mixcpu", "the MIXER pages' CPU: stock's redraws held to 10 a second (a key or knob at once), a full draw's meters, what they add on each page, under their ceilings (ColdFire)",
                  "the MIXER pages' CPU: stock's redraws held to 10 a second (a key or knob at once), a full draw's meters, what they add on each page, under their ceilings (ColdFire)",
                  [mc_cmd, sorted(EMU_ENV.items())], mc_body)

        # 6m3. lfowaves (2026-11-14, the User: "Port both"; docs/lfo-112-port.md): when the shipped build carries it
        from dnfw.mods import SHIPPED as SHIPPED_MODS   # noqa: PLC0415  (the patcher's list)
        if "lfowaves" in SHIPPED_MODS:
            lw_js = work / "lfowaves.json"
            lw_cmd = [a.venv, "-u", "scripts/emu_lfowaves.py", "--build", a.build, "--snapshot", snap, "--json", lw_js]

            def lw_body(tdir):
                rc, out = run("lfowaves", lw_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                return True, ("stock's seven waves unchanged; STEP PULS NOIS TRAP WTB1 WTB2 WTB3 each moving its "
                              "destination with its own shape, reachable through the cascade, named and drawn")
            later("lfowaves", "LFO waveforms: the seven new waves modulating and drawn (ColdFire)",
                  "LFO waveforms: the seven new waves modulating and drawn (ColdFire)",
                  [lw_cmd, sorted(EMU_ENV.items())], lw_body)

        # 6m4. lfo4 (2026-11-14, the User: "Port both", "Into the wishes record", "Include"; docs/lfo-112-port.md):
        # when the shipped build carries it (DN2_LFO4)
        if "lfo4" in SHIPPED_MODS:
            l4_js = work / "lfo4.json"
            l4_cmd = [a.venv, "-u", "scripts/emu_lfo4.py", "--build", a.build, "--snapshot", snap, "--json", l4_js,
                      "--scenario", "modulating,cascade,into4,lists,stored,page,line"]     # page: snap booted on the build

            def l4_body(tdir):
                rc, out = run("lfo4", l4_cmd, logs, env=EMU_ENV, trace=tdir)
                last = out.strip().splitlines()[-1] if out.strip() else ""
                if rc != 0 or not last.startswith("PASS"):
                    return False, "\n".join(l for l in out.splitlines() if "FAIL" in l)[-900:] or out[-900:]
                return True, ("LFO4 modulates (not at depth zero); LFO4 into LFO1 and LFO1 into LFO4 heard; LFO1..3's "
                              "lists offer LFO4's seven controls; stock's SAVE and LOAD carry LFO4 in the wishes record; "
                              "[MOD]'s fourth page is LFO4's, each knob moves its own value")
            later("lfo4", "LFO4: modulating, the cascade both ways, its lists, its stored values, its page (ColdFire)",
                  "LFO4: modulating, the cascade both ways, its lists, its stored values, its page (ColdFire)",
                  [l4_cmd, sorted(EMU_ENV.items())], l4_body)

        # the setup is done: from here on, nothing may import a module of ours (cached())
        setup_mods |= repo_modules()

        # 7. unit tests (v0.38: first of the long steps, on both cores: pytest-xdist, test by
        # test (--dist load: test_mnm.py alone is over half the time, so file by file one core
        # would wait on it). No test of TESTS shares a file with another (test_safety's
        # out/safety/waverider.syx is one test's own); module fixtures and lru_caches are built
        # in each worker. Before the SHARC runner starts, so they have both cores)
        tests = [t for t in TESTS if (ROOT / t).exists()]
        py_cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "not slow",
                  "-n", "2", "--dist", "load", *tests]

        def py_body(tdir):
            import importlib.util               # noqa: PLC0415
            if importlib.util.find_spec("xdist") is None:
                return False, ("pytest-xdist is not installed for this python (pip install "
                               "--break-system-packages pytest-xdist): unchecked is not passing")
            # v0.40 (owner, 2026-11-05): the Monomachine golden runs were lost with the old
            # workspace. The owner approved ONE exception, for this DSP image only: if they are
            # missing, test_mnm's cases may go unrun when the build's section 7 and the MnM code
            # and its test are byte-identical to v0.39's (source dbbe804), which passed against
            # the real golden runs. Every other skip still counts: exactly test_mnm's cases plus
            # the one skip every run has had (EFM-SD's eighth knob) may be skipped, no more
            exc = mnm_exception()
            if isinstance(exc, str):
                return False, exc
            rc, out = run("pytest", py_cmd, logs, env={"PYTHONPATH": "src"}, trace=tdir)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            # "586 passed, 1 skipped in 512.3s (0:08:32)": the counts, as serial pytest prints them
            ok = rc == 0 and re.search(r"\b\d+ passed\b", last) is not None
            missing = [] if exc is not None else mnm_golden_missing()
            if ok and missing:                  # the folder is here, some machines' golden runs are not (v0.59: FM+)
                last += (f" [MNM golden: not checked for {', '.join(missing)} ({len(missing)} of "
                         f"{len(MNM_GOLDEN_NAMES)} machines: no golden runs). dn2-wishes, the User 2026-11-11: upstream's "
                         "Monomachine golden runs are not available to the fork, so those machines' golden cases are not "
                         "collected; every other test counts as before]")
            if ok and exc == NO_MNM_GOLDEN:
                last += (" [MNM golden: not checked (no MNM golden). dn2-wishes, the User 2026-11-11: upstream's "
                         "Monomachine golden runs are not available to the fork, so test_mnm's golden cases are not "
                         "collected; every other test counts as before]")
            elif ok and exc is not None:
                m = re.search(r"\b(\d+) skipped\b", last)
                skipped = int(m.group(1)) if m else 0
                if skipped != exc + 1 or exc != MNM_EXC_REST:
                    return False, (f"{last} -- under the MnM exception test_mnm must collect exactly "
                                   f"{MNM_EXC_REST} tests (it collected {exc}) and exactly "
                                   f"{MNM_EXC_REST + 1} may be skipped (those and EFM-SD's eighth knob), "
                                   f"not {skipped}")
                last += (f" [owner exception 2026-11-05: the Monomachine golden runs are missing, so "
                         f"test_mnm's 366 golden cases are not collected and its {exc} other tests "
                         f"skip; section 7, src/dnfw/mnm and test_mnm.py byte-identical to v0.39's "
                         f"(dbbe804), which passed them all]")
            return ok, last

        def mnm_golden_missing():
            """test_mnm's machines (dnfw.mnm.bench.GOLDEN_NAMES) whose golden runs are missing"""
            golden = pathlib.Path(os.environ.get("MNM_GOLDEN",
                                                 str(ROOT.parent / "mnm132" / "research" / "golden")))
            return [n for n in MNM_GOLDEN_NAMES if not (golden / f"{n}.json").is_file()]

        def mnm_exception():
            """None: the golden runs are there, nothing excepted. An int: the exception applies,
            that many test_mnm cases go unrun. A str: why it does not apply (a failure)."""
            golden = pathlib.Path(os.environ.get("MNM_GOLDEN",
                                                 str(ROOT.parent / "mnm132" / "research" / "golden")))
            if golden.is_dir():
                return None
            if hashlib.sha256(sec7).hexdigest() != MNM_EXC_SEC7:
                return NO_MNM_GOLDEN                # dn2-wishes (the User, 2026-11-11): not checked, reported
            for path, want in MNM_EXC_TREES.items():
                got = subprocess.run(["git", "rev-parse", f"HEAD:{path}"], cwd=ROOT,
                                     capture_output=True, text=True).stdout.strip()
                dirty = subprocess.run(["git", "status", "--porcelain", "--", path], cwd=ROOT,
                                       capture_output=True, text=True).stdout.strip()
                if got != want or dirty:
                    return (f"the Monomachine golden runs are missing and {path} differs from "
                            f"v0.39's: the owner's exception (2026-11-05) does not cover it")
            r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                                "-p", "no:cacheprovider", "test/test_mnm.py"], cwd=ROOT,
                               capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src"})
            m = re.search(r"\b(\d+) tests? collected\b", r.stdout)
            if r.returncode != 0 or not m:
                return "the MnM exception could not count test_mnm's cases: unchecked is not passing"
            return int(m.group(1))
        ran = set()
        for sid, _gname in EMU:                 # 2026-11-16: the brick risks first, before the unit tests
            if sid in BRICK_EMU and sid in plan and wanted(sid):
                gname, cname, cmds, body = plan[sid]
                gate(gname, *cached(cname, cmds, body))
                ran.add(sid)

        if wanted("unit"):
            gate("unit tests", *cached("unit tests", [py_cmd], py_body))

        # the SHARC runner (v0.25: beside the ColdFire steps, on its own core)
        if dsp_changed and sharc_want:
            sharc = threading.Thread(target=sharc_thread, daemon=True)
            sharc.start()

        # 5, 5b, 6, 6b..6r. the ColdFire emulator steps, quickest first (EMU); after each, a
        # SHARC part that has failed stops the gate
        for sid, _gname in EMU:
            if sid in plan and wanted(sid) and sid not in ran:
                gname, cname, cmds, body = plan[sid]
                sharc_failed()
                gate(gname, *cached(cname, cmds, body), feature=sid in FEATURE_STEPS)
                ran.add(sid)
                sharc_failed()

        if sharc is not None:
            print("  (waiting for the SHARC runner)", flush=True)
            sharc.join()
            if only is None:
                good = len(sharc_box) == len(gate_sharc.parts()) and all(ok for ok, _ in sharc_box)
                gate("SHARC runner", good, "; ".join(d for _, d in sharc_box) if sharc_box
                     else "the runner did not finish")
            else:
                for k, steps in enumerate(sharc_want):
                    ok, d = sharc_box[k] if k < len(sharc_box) else (False, "did not run: an earlier part failed")
                    gate(f"SHARC runner: {','.join(steps)}", ok, d)
                    ran.add("sharc:" + "+".join(steps))

    except Stop as s:
        for proc in list(LIVE):                 # the SHARC runner, if it is still going
            proc.kill()
        print(f"\nGATE FAILED at: {s}\n\n  DO NOT FLASH {a.build.name}.\n  Logs: {logs}")
        return 1

    if only is not None:
        # v0.38: --only: the steps asked for, each recorded in the reuse cache as a full run
        # would record it. Never a gate pass: no record beside the build, no clearance
        ran |= {sid for sid, _ in FIRST if sid in only and sid not in ("dsp-identity", "hwrules")}
        ran |= {sid for sid in ("dsp-identity", "hwrules") if sid in only and dsp_changed}
        missing = sorted(only - ran)
        print(f"ONLY {', '.join(sorted(only))}: " + ("each asked-for step passed" if not missing else
              f"passed, but {', '.join(missing)} did not apply to this build (not run)")
              + "".join(f"\n  KNOWN ISSUE (feature step, not blocking): {k}: {v[:300]}" for k, v in known.items())
              + f"\n  logs: {logs}\n\n  A PARTIAL RUN, NOT A GATE: do not flash on it. Only a full run of "
              f"ship_gate.py on {a.build.name} can clear it.")
        return 0 if not missing else 3

    record = {"build": a.build.name, "sha256": sha, "stock": a.stock.name,
              "date": datetime.datetime.now().isoformat(timespec="seconds"),
              "gates": results, "logs": str(logs),
              "known_issues": known,          # FEATURE_STEPS that failed: not blocking (the User, 2026-11-16)
              "feature_steps": list(FEATURE_STEPS),
              "interpreters": {"SHARC runner": a.sharc_py, "coupled (THRES, FLEX)": a.coupled_py,
                               "ColdFire steps": a.venv},
              "reused": {k: f"the pass of {v}: every file it read is byte-identical" for k, v in reused.items()}}
    out = a.build.with_name(a.build.name + ".gate.json")
    out.write_text(json.dumps(record, indent=2))
    if known:
        print("KNOWN ISSUES (feature steps, not blocking; in the record):\n"
              + "".join(f"  {k}: {v[:400]}\n" for k, v in known.items()))
    print(f"ALL {'BLOCKING ' if known else ''}GATES PASS on sha256 {sha[:16]}…\n  record: {out}\n\n"
          f"  CLEARED TO FLASH: {a.build.name}\n  (only this exact file; any change needs a new gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
