"""Modulation on the ColdFire emulator, OS 1.12 (docs/modulation-more.md): the destination lists,
the LFO cascade, the moving controls' line.

    emu_modulation.py --build BUILD.syx [--before OLD.syx] [--scenario lists,cascade,cost,line] [--json OUT]

lists    the builder 0x4003951e called with the live ParameterSet of track 1, for LFO1 (want
         0x1e00), LFO2 (0xe00), LFO3 (0x600) and MOD SETUP (0x200), track 1 on WaveTone, FM TONE
         and PERC; stock 1.12 beside the build (and --before, the line it replaces). What must hold:
         nothing stock lists is lost; the 13 closed records are added to every list (8 of them FM
         TONE's own); each LFO's list adds the other LFOs' SPD MULT FADE WAVE SPH MODE DEP that
         stock leaves out, never its own controls, never a DEST. A build carrying lfo4: LFO1..3's lists
         also offer LFO4's seven controls (ids 321 322 323 325 327 328 329), exactly those, never
         its DEST (324); MOD SETUP's none.

cascade  the frame's LFO path called by hand (the emulator runs no audio interrupt): stock's
         smoother 0x400db28e, then the frame's call of the evaluator (the build's mod_eval, or
         stock's 0x40137a06), voice row 0 holding LFO1 -> LFO2 SPD and LFO2 -> LFO1 SPD at full
         depth, for many frames. What must hold: LFO2's SPD as LFO2 reads it moves on the build (it
         never does on stock), by what LFO1 wrote one frame earlier, exactly; every LFO cell stays
         in 0..0x7fff; the evaluator returns every frame (also with both SPDs and MULTs at their
         tops, at their bottoms, at zero speed).

cost     the evaluator call's instructions, build minus stock, all 16 rows at full depth: typical
         (no LFO aimed at an LFO above it) and worst (every row's LFO1 and LFO2 aimed at LFO3's
         controls); each must stay under its bound. A build carrying lfo4: build minus stock with
         lfo4 alone applied (lfo4's fourth LFO in stock's evaluator is lfo4's share, printed).

line     the FLTR page on track 1 (WaveTone): test values written into the heard array of the
         voice the track last played; the cell of FREQ (slot 67) must show a 1 px line in its row
         MV_DY, its length the heard value, none when heard = set (after the 400 ms linger), and
         the UI updates it by itself when the heard value moves (the line alone, read from the glass's buffer). Before that, with nothing
         modulated, no line on WaveTone's SYN page. The instructions of mv_cell, of a poll and of
         the page's draws are printed, also with every cell of the page modulated (the worst case).

ours     the same line on our own pages (2026-11-12): MACHINEDRUM, SOPHIE, PLAITS, TB-303, DRONE, ANALOG 2,
         MONOMACHINE, ONESHOT, SLICE on track 1, SYN page 1: every knob drawn goes through mv_knob, its
         line's row free (nothing lit across it) before anything is modulated; one knob's heard value
         moved draws exactly moving.c's line in that row, and nothing 400 ms after heard = set again;
         on MACHINEDRUM and MONOMACHINE, LFO1 aimed at that knob, run by the frame's evaluator: the line
         moves by itself, and leaves once LFO1's depth is zero.

locks    (2026-11-20, scripts/emu_modlocks.py) a p-lock played with stock's own builder, applier and undo on a stock
         page (WaveTone's FLTR, FREQ), one of our machines' pages (TB-303) and a sample machine's (ONESHOT): the line
         at the locked value while the knob keeps its own value, gone 400 ms after the step without the lock; a knob
         turned: no line (the smoother's glide). A build before the change: no line on a lock (checked as such).

Last line PASS or FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

SNAP = str(HERE.parent.parent / "digikit/out/snapshots/dn2-1.11/ui800M-v014.snap")
BASE = 0x40000400
BUILDER = 0x4003951E
CTX, STEP_A, STEP_B, STEP_C, PSET = 0x4018AC5A, 0x4003E40E, 0x40046BFE, 0x4003E41A, 0x400312AE
COMMIT = 0x40031880                 # MACHINE SEL's commit(model, track, type, 1, 1)
RECORDS = 0x401F83A4
UI_TRACK, KIT = 0x42432A6C, 0x800052A0
SRC, OUT, STATE, OWNER = 0x80003AF0, 0x800068E4, 0x8000DE60, 0x80005308
FRAMES = 0x4058F8D4
SMOOTHER, EVAL_A = 0x400DB28E, 0x40137A06
RATE = 0x402A132C
SET_FRAC = bytes.fromhex("a93c000000204e75")       # move.l #32,%macsr ; rts
# movea.l 4(%sp),%a0 ; move.l 12(%sp),-(%sp) ; move.l 12(%sp),-(%sp) ; jsr builder ; addq #8 ; rts
TRAMPOLINE = bytes.fromhex("206f00042f2f000c2f2f000c4eb94003951e508f4e75")
WANTS = {"LFO1": 0x1E00, "LFO2": 0x0E00, "LFO3": 0x0600, "MOD SETUP": 0x0200}
MACHINES = {"WAVETONE": 1, "FM TONE": 0, "PERC": 5}
STOCK_MACHINES = ("WAVETONE", "FM TONE")      # PERC (type 5) is ours: stock has no such machine
OPENED = (34, 35, 61, 73, 74, 221, 222, 224, 225, 226, 235, 236, 237)
FM_ONLY = (221, 222, 224, 225, 226, 235, 236, 237)
LFO_CTL = {1: (75, 76, 77, 79, 81, 82, 83), 2: (85, 86, 87, 89, 91, 92, 93), 3: (95, 96, 97, 99, 101, 102, 103)}
DESTS = (78, 88, 98)
# lfo4 (DN2_LFO4, docs/lfo-112-port.md; ship_gate 6m4): its records are ids 321..330 in LFO3's order (SPD MULT FADE
# DEST WAVE SLEW SPH MODE DEP MULT2, dnfw.patch.lfo4records). LFO1..3's lists offer its seven controls by design, as
# they offer each other's (cascade.c lfo_of): never its DEST (324), nor SLEW (326, its slot is SPH's) nor the second MULT (330)
LFO4_CTL = (321, 322, 323, 325, 327, 328, 329)
LFO4_DEST = 324
TOP = 0x7F00
MV_DY_DEFAULT = 5                   # csrc/modulation/moving.c MV_DY
FAILS: list[str] = []


FB_BACK = 0x402A10CC                # the panel's BACK pointer: between presents, the frame on the glass


def glass(m):
    """what the glass shows: BACK (2026-11-17: a moving line is rewritten there alone, with no page draw, so
    the last frame drawn (panel.capture) no longer holds it; csrc/modulation/moving.c mv_lines_only)"""
    return bytes(m.read(m.long(FB_BACK), 1024))


def check(what, ok, detail=""):
    print(("  ok    " if ok else "  FAIL  ") + what + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        FAILS.append(what)


def idx(v, s):
    return 17 + 101 * v + s


# --- the machine ------------------------------------------------------------------------
def machine(build, snapshot, sec3_in=None):
    """the snapshot with stock 1.12's MAIN OS, then BUILD's (if any) as the loader leaves it
    (SEC3_IN: a MAIN OS in place of BUILD's, e.g. stock with lfo4 alone: the cost's reference)"""
    from emulib.image import differences
    from emulib.machine import Machine
    m = Machine(snapshot)
    stock = open(pathlib.Path(os.environ["DT2_SECTIONS"]) / "section_3_MAIN_OS.bin", "rb").read()
    snap_sec = open(snapshot + ".section_3_MAIN_OS.bin", "rb").read()
    sec3 = None
    m.apply([(va, stock[va - BASE:va - BASE + len(b)]) for va, b in differences(stock, snap_sec)
             if va + len(b) <= BASE + len(stock)])
    if build or sec3_in is not None:
        from dnfw.cli.files import read_image
        from dnfw.firmware.load import load
        from dnfw.mods import platform
        from unicorn import UC_PROT_ALL, UcError
        sec3 = sec3_in if sec3_in is not None else load(read_image(pathlib.Path(build))).container.find(3).unpack()
        m.apply(differences(stock, sec3))
        for va, blob in platform.runtime(sec3):
            m.write(va, blob)
        from emulib import attkit
        attkit.store_kit(m)  # (2026-11-21) a converted kit stored back: converted once
        from dnfw.sampler import machines as SMx
        for pg in range(SMx.MIRROR, SMx.MIRROR + 0x500000, 0x100000):
            try:
                m.uc.mem_map(pg, 0x100000, UC_PROT_ALL)
            except UcError:
                pass
        resume_ui(m, snap_sec, sec3)
    m.write(0x46AF8000, bytes(0x800))       # MOD_RAM: as after power-on, unknown -> zero here
    m.flush()
    return m


QRECV_CALL = bytes.fromhex("4eb940001928")       # jsr 0x40001928, the UI queue's receive


def resume_ui(m, snap_sec, sec3):
    """The snapshot's UI task sleeps inside the queue receive that our smp_ui_pop (csrc/sampler)
    calls, so its stack holds a return address into the C chunk AS THE SNAPSHOT'S BUILD LAID IT
    OUT. A build whose chunk is laid out otherwise would return into the middle of an
    instruction (an illegal-instruction fault at the first UI pass, measured 2026-11-11). The
    address is moved to the same call's return in this build: the chunk's one such call."""
    from dnfw.mods import platform
    from dnfw.waverider import pages
    def site(sec):
        for va, blob in platform.runtime(sec):
            if pages.C_LOAD <= va < pages.MDUI_LOAD and blob.count(QRECV_CALL) == 1:   # (v0.48's 0x46ac0000 within)
                return va + blob.find(QRECV_CALL) + len(QRECV_CALL)
        return None
    old, new = site(snap_sec), site(sec3)
    if not old or not new or old == new:
        return
    moved = 0
    for page in range(0x40400000, 0x40800000, 0x10000):
        try:
            blob = m.read(page, 0x10000)
        except Exception:                       # noqa: BLE001
            continue
        want = struct.pack(">I", old)
        i = blob.find(want)
        while i >= 0:
            if i % 2 == 0:
                m.write(page + i, struct.pack(">I", new))
                moved += 1
            i = blob.find(want, i + 1)
    print(f"  the UI task's return into the chunk: {old:#010x} -> {new:#010x} ({moved} place(s))", flush=True)


def guest(m, fn, *args):
    from emu_encoder_trace import guest as g
    return g(m, fn, *args)


def u16(m, va):
    return struct.unpack(">H", m.read(va, 2))[0]


def w16(m, va, v):
    m.write(va, struct.pack(">H", v & 0xFFFF))


def record(m, rid):
    return struct.unpack(">15i", m.read(RECORDS + 60 * rid, 60))


def stored(m, s, t=0):
    """track T's sound's stored value of slot S (sound + 20 + 2 S): what the moving line takes as set (moving.c)"""
    return u16(m, m.long(KIT) + 52 + 1163 * t + 20 + 2 * s)


def rest_on_sound(m, v=0, t=0):
    """voice V's smoother settled on track T's sound and nothing added: its input SRC, STATE and OUT at the stored values
    (2026-11-20: the line's set is the stored value; on a build before, the smoother's state, which this makes the same)"""
    for s in range(1, 101):
        val = stored(m, s, t)
        w16(m, SRC + 2 * idx(v, s), val)
        m.write(STATE + 4 * idx(v, s), struct.pack(">I", val << 16))
        w16(m, OUT + 2 * idx(v, s), val)


def set_machine(m, panel, track, mtype):
    owner = guest(m, CTX)
    guest(m, COMMIT, owner + 0xF4, track, mtype, 1, 1)
    panel.settle(3_000_000)
    kit = m.long(KIT)
    return struct.unpack(">b", m.read(kit + 52 + 1163 * track + 0xDE, 1))[0]


def parameter_set(m):
    b = guest(m, STEP_B, guest(m, STEP_A, guest(m, CTX)))
    return guest(m, PSET, guest(m, STEP_C, guest(m, CTX)), b) & 0xFFFFFFFF


def dest_list(m, tramp, out, pset, want):
    m.write(out, bytes(8))
    guest(m, tramp, out, pset, want)
    vec = m.long(out)
    if not vec:
        return []
    begin, end = m.long(vec), m.long(vec + 4)
    if not begin or end < begin or (end - begin) % 4 or end - begin > 4 * 400:
        return []
    return [m.long(a) for a in range(begin, end, 4)]


# --- lists --------------------------------------------------------------------------------
def lists_of(build, snapshot):
    from emulib.panel import Panel
    m = machine(build, snapshot)
    panel = Panel(m, png_dir="out/modulation")
    m.write(UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    tramp = m.alloc(len(TRAMPOLINE))
    m.write(tramp, TRAMPOLINE)
    m.flush()
    out = m.alloc(8)
    res = {}
    for name, mtype in MACHINES.items():
        got = set_machine(m, panel, 0, mtype)
        if got != mtype:
            res[name] = None
            continue
        pset = parameter_set(m)
        res[name] = {lfo: dest_list(m, tramp, out, pset, want) for lfo, want in WANTS.items()}
    return res


def scenario_lists(a, report):
    lfo4 = lfo4_in(a.build)
    print(f"    lfo4 in the build: {'yes (LFO1..3 offer its seven controls)' if lfo4 else 'no'}", flush=True)
    runs = {"stock": lists_of(None, a.snapshot), "build": lists_of(a.build, a.snapshot)}
    if a.before:
        runs["before"] = lists_of(a.before, a.snapshot)
    table = {}
    for name in MACHINES:
        for lfo in WANTS:
            row = {k: (len(v[name][lfo]) if v.get(name) else None) for k, v in runs.items()}
            table[f"{name} {lfo}"] = row
            print(f"    {name:9} {lfo:9} " + "  ".join(f"{k} {n}" for k, n in row.items()), flush=True)
    report["lists"] = table
    for name in MACHINES:
        s, b = runs["stock"].get(name), runs["build"].get(name)
        ref = runs["before"][name] if a.before and runs["before"].get(name) else s
        if not b or (name in STOCK_MACHINES and not s):
            check(f"{name}: the machine could be set and its lists built", False)
            continue
        for lfo, want in WANTS.items():
            bl = set(b[lfo])
            rl = set(ref[lfo]) if ref else None     # PERC without --before: the build's own rules only
            if rl is not None:
                check(f"{name} {lfo}: the reference list is not empty", len(rl) > 0, f"{len(rl)}")
                lost = sorted(rl - bl)
                check(f"{name} {lfo}: nothing the line before listed is lost", not lost, f"{lost}")
            want_open = set(OPENED) - (set() if name == "FM TONE" else set(FM_ONLY))
            missing = sorted(want_open - bl)
            check(f"{name} {lfo}: the {len(want_open)} closed records this machine has are listed", not missing,
                  f"missing {missing}")
            k = {"LFO1": 1, "LFO2": 2, "LFO3": 3}.get(lfo)
            if k:
                others = set(sum((LFO_CTL[j] for j in LFO_CTL if j != k), ()))
                check(f"{name} {lfo}: every other LFO's controls listed", others <= bl, f"missing {sorted(others - bl)}")
                check(f"{name} {lfo}: none of its own controls", not (set(LFO_CTL[k]) & bl), f"{sorted(set(LFO_CTL[k]) & bl)}")
                if lfo4:
                    check(f"{name} {lfo}: LFO4's seven controls listed (lfo4)", set(LFO4_CTL) <= bl,
                          f"missing {sorted(set(LFO4_CTL) - bl)}")
            check(f"{name} {lfo}: no DEST listed", not (set(DESTS) & bl))
            check(f"{name} {lfo}: no LFO4 DEST listed", LFO4_DEST not in bl)
            if rl is not None:
                # lfo4's controls are expected only where lfo4 offers them: LFO1..3's lists, on a build carrying lfo4
                allowed = set(OPENED) | set(sum(LFO_CTL.values(), ())) | (set(LFO4_CTL) if lfo4 and k else set())
                extra = sorted(bl - rl - allowed)
                check(f"{name} {lfo}: nothing else added", not extra, f"{extra}")


# --- cascade ------------------------------------------------------------------------------
LFO_SLOT = {"SPD": 1, "MULT": 2, "FADE": 3, "DEST": 4, "WAVE": 5, "SPH": 6, "MODE": 7, "DEP": 8}


def slot(lfo, field):
    return 8 * (lfo - 1) + LFO_SLOT[field]


def cascade_run(build, snapshot, frames, spd, mult, sym):
    """-> per frame: (heard LFO1 SPD, heard LFO2 SPD, LFO1's write into the shadow), and bounds"""
    m = machine(build, snapshot)
    frac = m.alloc(len(SET_FRAC))
    m.write(frac, SET_FRAC)
    m.flush()
    m.call(frac)
    v = 0
    setting = {slot(1, "SPD"): spd, slot(1, "MULT"): mult << 8, slot(1, "FADE"): 0x4000, slot(1, "DEST"): slot(2, "SPD") << 8,
               slot(1, "WAVE"): 0, slot(1, "SPH"): 0, slot(1, "MODE"): 0, slot(1, "DEP"): TOP,
               slot(2, "SPD"): spd, slot(2, "MULT"): mult << 8, slot(2, "FADE"): 0x4000, slot(2, "DEST"): slot(1, "SPD") << 8,
               slot(2, "WAVE"): 0, slot(2, "SPH"): 0, slot(2, "MODE"): 0, slot(2, "DEP"): TOP,
               slot(3, "DEST"): 0, slot(3, "DEP"): 0x4000}
    for s, val in setting.items():            # the target, and the smoother already settled on it
        w16(m, SRC + 2 * idx(v, s), val)
        m.write(STATE + 4 * idx(v, s), struct.pack(">I", val << 16))
        w16(m, OUT + 2 * idx(v, s), val)
    rate = m.long(RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    caller = sym.get("mod_eval") if build else EVAL_A
    # what each LFO of row 0 reads as its SPD: d6 after 0x40137b1c's mvs.w 68(%a4),%d6, with
    # the LFO counter (2 LFO3 .. 0 LFO1) at 48(%sp) and the row in %a5
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    read = {}

    def on_spd(uc, ad, sz, us):
        if uc.reg_read(K.UC_M68K_REG_A5) == v:
            sp = uc.reg_read(K.UC_M68K_REG_A7)
            lfo = struct.unpack(">i", bytes(uc.mem_read(sp + 48, 4)))[0]
            read[lfo] = uc.reg_read(K.UC_M68K_REG_D6) & 0xFFFF
    m.uc.hook_add(UC_HOOK_CODE, on_spd, begin=0x40137B20, end=0x40137B20)
    if build and lfo_fast_in(build):            # 2026-11-17: the build runs the evaluator as lfo_fast (hooks.S): the same
        at = lfo_fast_spd(m, sym)               # read there, the frame the same
        m.uc.hook_add(UC_HOOK_CODE, on_spd, begin=at, end=at)
    rows, bad, faults = [], [], 0
    for f in range(frames):
        read.clear()                            # (DN2_LFO_HALFRATE: a frame where row 0's LFOs do not step reads none)
        try:
            m.call(SMOOTHER, SRC)
            m.call(caller, OUT, rate, 1, 1, o1, o2, 0, limit=2_000_000)
        except Exception as e:                  # noqa: BLE001
            faults += 1
            bad.append(f"frame {f}: {e}")
            break
        h1, h2 = read.get(0), read.get(1)       # as LFO1 and LFO2 read their SPD this frame
        shadow = None
        if build:
            row = 0x46AF8000 + 12 + 68 * v
            sh, base = u16(m, row + 4 + 2 * 0), u16(m, row + 36 + 2 * 0)
            shadow = sh - base
        rows.append((h1, h2, shadow))
        for s in range(1, 25):
            x = u16(m, OUT + 2 * idx(v, s))
            if x > 0x7FFF:
                bad.append(f"frame {f} slot {s} = {x:#06x}")
    return rows, bad, faults, m


def halfrate_in() -> bool:
    """this tree's build steps half the voices' LFOs a frame (DN2_LFO_HALFRATE: lh_args in its code map)"""
    d = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())
    return "lh_args" in (d.get("c_text_symbols") or {})


# (2026-11-19, DN2_LFO_HALFRATE on by default, the User's choice, agreed with main) with half-rate LFOs a row's LFOs
# step every second frame (its turn) and read their SPD only then: on the build the reads are taken from the frames
# where row 0 stepped, which must be exactly every second frame, and "LFO2 hears what LFO1 wrote one frame earlier" is
# checked at each of them (LFO1 writes LFO2's SPD every frame, from its last output). Without half-rate: every frame.
def scenario_cascade(a, report, sym):
    n = a.frames
    rep = {}
    half = halfrate_in()
    for label, build in (("stock", None), ("build", a.build)):
        rows, bad, faults, m = cascade_run(build, a.snapshot, n, 0x5800, 4, sym)
        turns = [k for k in range(len(rows)) if rows[k][1] is not None]
        if label == "build" and half:
            check("build (half-rate LFOs): row 0's LFOs step every second frame, no more, no less",
                  len(turns) >= len(rows) // 2 - 1 and all(y - x == 2 for x, y in zip(turns, turns[1:])),
                  f"{len(turns)} of {len(rows)} frames, first {turns[:6]}")
            rep["half_rate_turns"] = len(turns)
        else:
            check(f"{label}: row 0's LFOs step every frame", len(turns) == len(rows), f"{len(turns)} of {len(rows)}")
        h2 = [rows[k][1] for k in turns] or [0]
        h1 = [rows[k][0] for k in turns if rows[k][0] is not None] or [0]
        rep[label] = {"frames": len(rows), "lfo2_spd": [min(h2), max(h2)], "lfo1_spd": [min(h1), max(h1)],
                      "faults": faults}
        print(f"    {label}: {len(rows)} frames, LFO1 SPD heard {min(h1):#06x}..{max(h1):#06x}, "
              f"LFO2 SPD heard {min(h2):#06x}..{max(h2):#06x}", flush=True)
        check(f"{label}: every frame returned, no fault", faults == 0 and len(rows) == n, "; ".join(bad[:2]))
        check(f"{label}: every LFO cell stays in 0..0x7fff", not bad, "; ".join(bad[:3]))
        check(f"{label}: LFO2 -> LFO1 SPD is heard (stock's direction)", max(h1) - min(h1) > 0x400,
              f"{max(h1) - min(h1):#x}")
        if label == "stock":
            check("stock: LFO1 -> LFO2 SPD is never heard (written after LFO2 read it)", max(h2) == min(h2) == 0x5800,
                  f"{min(h2):#06x}..{max(h2):#06x}")
        else:
            check("build: LFO1 -> LFO2 SPD is heard", max(h2) - min(h2) > 0x400, f"{max(h2) - min(h2):#x}")
            late = [k for k in turns if k >= 1 and rows[k][1] != max(0, min(TOP, 0x5800 + rows[k - 1][2]))]
            check("build: what LFO2 hears is what LFO1 wrote one frame earlier" + (" (at each turn)" if half else ""),
                  not late, f"{len(late)} frames differ")
            carried = m.long(0x46AF8000 + 8)
            check("build: the carry ran", carried > 0, f"{carried} cells carried")
            # costs: the pre-pass alone, with and without a carry
            _, c_pre = m.cost(sym["mod_eval_pre"])
            rep["pre_instructions"] = c_pre
            print(f"    mod_eval_pre: {c_pre} instructions (a carried cell, 16 rows)", flush=True)
    for label, spd, mult in (("tops", TOP, 23), ("bottoms", 0, 0), ("zero speed", 0x4000, 0)):
        rows, bad, faults, _ = cascade_run(a.build, a.snapshot, n // 2, spd, mult, sym)
        check(f"build, SPD {spd:#06x} MULT {mult}: every frame returned, cells in range", faults == 0 and not bad
              and len(rows) == n // 2, "; ".join(bad[:2]))
        rep[label] = {"frames": len(rows), "faults": faults}
    report["cascade"] = rep


def lfowaves_edits(build):
    """lfowaves' in-image edits when BUILD carries its chunk (each checked as lfowaves made it), else []"""
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    from dnfw.mods import lfowaves as LW
    from dnfw.mods import platform
    sec3 = load(read_image(pathlib.Path(build))).container.find(3).unpack()
    if not any(va == LW.RUNTIME_VA for va, _ in platform.runtime(sec3)):
        return []
    bad = [e["va"] for e in LW.EDITS if sec3[e["va"] - BASE:e["va"] - BASE + len(e["new"]) // 2].hex() != e["new"]]
    if bad:
        raise SystemExit(f"the build carries lfowaves' chunk but not its edits at {[hex(v) for v in bad]}")
    return LW.EDITS


LFO_FAST_JMP = bytes.fromhex("4ef9")             # 0x40137a06: jmp lfo_fast ; nop (dnfw.waverider.lfofast)
LFO_FAST_SPD = bytes.fromhex("7d6c0044712c0046")  # mvs.w 68(%a4),%d6 ; mvs.b 70(%a4),%d0: the LFO's SPD read


def lfo_fast_in(build):
    """True when BUILD's evaluator A is entered by a jmp into lfo_fast (csrc/modulation/hooks.S)"""
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    sec3 = load(read_image(pathlib.Path(build))).container.find(3).unpack()
    return sec3[EVAL_A - BASE:EVAL_A - BASE + 2] == LFO_FAST_JMP


def lfo_fast_edits(build):
    """lfo_fast's jmp at 0x40137a06 as an edit to put back (eval_cost's WITHOUT), or [] when the build has none"""
    from dnfw.waverider import lfofast
    return [{"va": EVAL_A, "stock": lfofast.EVAL_ENTRY.hex()}] if lfo_fast_in(build) else []


def lfo_fast_spd(m, sym):
    """-> the address in lfo_fast of the instruction after its SPD read (stock's 0x40137b20)"""
    code = bytes(m.read(sym["lfo_fast"], 0x400))
    at = code.find(LFO_FAST_SPD)
    if at < 0 or code.find(LFO_FAST_SPD, at + 1) >= 0:
        raise SystemExit("lfo_fast: its SPD read is not found once")
    return sym["lfo_fast"] + at + 4


def lfo4_in(build):
    """True when BUILD carries lfo4: its CODE chunk at 0x46800000 (as emu_lfo4.py finds it). Its in-image edits are
    not compared byte for byte here: where lfowaves' hook covers one (0x400372e3), the platform writes it into the
    displaced copy instead (dnfw.mods.platform.write)"""
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    from dnfw.mods import platform
    sec3 = load(read_image(pathlib.Path(build))).container.find(3).unpack()
    _, chunks = platform.split(sec3)
    return any(c == platform.area.CODE and platform.area.CodeChunk.unpack(d).load == 0x46800000 for c, d in chunks)


def stock_with_lfo4():
    """stock 1.12's MAIN OS with lfo4 alone applied (dnfw.mods.lfo4.compose, what gen_lfo4_code.py checks byte for
    byte): the evaluator with lfo4's fourth LFO on every voice and nothing of ours"""
    from dnfw.mods import lfo4 as L4
    return L4.compose(open(pathlib.Path(os.environ["DT2_SECTIONS"]) / "section_3_MAIN_OS.bin", "rb").read())


def eval_cost(build, snapshot, sym, dests, frames=8, without=(), sec3_in=None):
    """instructions of the frame's evaluator call (the build's mod_eval, or stock's 0x40137a06), all
    16 voice rows at full depth with LFO1/2/3 aimed at DESTS; -> the most over FRAMES frames.
    WITHOUT: in-image edits put back to stock first (lfowaves', whose share is not the cascade's).
    SEC3_IN (with BUILD None): that MAIN OS, its evaluator called as stock's (stock with lfo4 alone)"""
    m = machine(build, snapshot, sec3_in)
    for e in without:
        m.write(e["va"], bytes.fromhex(e["stock"]))
    m.flush()
    frac = m.alloc(len(SET_FRAC))
    m.write(frac, SET_FRAC)
    m.flush()
    m.call(frac)
    for v in range(16):
        for k, d in zip((1, 2, 3), dests):
            for f, val in (("SPD", 0x5800), ("MULT", 4 << 8), ("FADE", 0x4000), ("DEST", d << 8), ("WAVE", 0),
                           ("SPH", 0), ("MODE", 0), ("DEP", TOP)):
                s = slot(k, f)
                w16(m, SRC + 2 * idx(v, s), val)
                m.write(STATE + 4 * idx(v, s), struct.pack(">I", val << 16))
    rate = m.long(RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    caller = sym["mod_eval"] if build else EVAL_A
    for _ in range(2):                          # warm: the first frame zeroes MOD_RAM (once a power-on)
        m.call(SMOOTHER, SRC)
        m.call(caller, OUT, rate, 0xFFFF, 0, o1, o2, 0)
    worst = 0
    for _ in range(frames):
        m.call(SMOOTHER, SRC)
        _, n = m.cost(caller, OUT, rate, 0xFFFF, 0, o1, o2, 0)
        if build and "mx_eval" in sym:          # the matrix's share (csrc/matrix, its own constant cost and gate
            _, k = m.cost(sym["mx_eval"], OUT)  # step emu_matrix.py): not the cascade's
            n -= k
        worst = max(worst, n)
    return worst


def scenario_cost(a, report, sym):
    """the cascade's cost per audio frame, typical (no LFO aimed at an LFO) and worst (every row's
    LFO1 and LFO2 aimed at LFO3's controls, LFO3 at LFO2's: the most our hooks can do in one frame)"""
    typical = (67, 36 + 0, 72)                  # FREQ, a filter slot, VOL: no LFO's control
    worst = (17, 18, 9)                         # LFO1 -> LFO3 SPD, LFO2 -> LFO3 MULT, LFO3 -> LFO2 SPD
    # 2026-11-14 (r8, the first build with lfowaves on 1.12): lfowaves hooks every LFO's evaluation (two hooks,
    # 18 instructions an LFO at a stock wave), 816 instructions a frame that are not the cascade's. The cascade is
    # measured on the build with lfowaves' edits put back to stock; lfowaves' share is checked on its own.
    lw = lfowaves_edits(a.build)
    # 2026-11-16 (v0.56.2, lfo4 on): lfo4 edits stock's evaluator itself to run a fourth LFO on every voice (its loop
    # 3 -> 4, its state moved to 0x46700000): that share is lfo4's, not the cascade's. On a build carrying lfo4 the
    # cascade is measured against stock with lfo4 alone applied (the same evaluator, nothing of ours); lfo4's share
    # (that reference minus stock) is printed beside it.
    l4 = stock_with_lfo4() if lfo4_in(a.build) else None
    # 2026-11-17: a build whose evaluator is lfo_fast (the same work, fewer instructions; checked against stock's
    # instruction for instruction by lfotest) is measured here with its jmp put back: the cascade's and lfowaves'
    # shares as before, on stock's evaluator; lfo_fast's own saving beside them
    lf = lfo_fast_edits(a.build)
    rep = {}
    for label, dests in (("typical", typical), ("worst", worst)):
        st = eval_cost(None, a.snapshot, sym, dests, sec3_in=l4)
        if l4 is not None:
            s0 = eval_cost(None, a.snapshot, sym, dests)
            rep.setdefault("lfo4", {})[label] = {"stock": s0, "stock_with_lfo4": st, "share": st - s0}
            print(f"    evaluator frame, {label}: stock {s0}, stock with lfo4 alone {st}: lfo4's share {st - s0} "
                  f"instructions a frame (the reference below)", flush=True)
        bd = eval_cost(a.build, a.snapshot, sym, dests, without=lw + lf)
        rep[label] = {"stock": st, "build": bd, "ours": bd - st, "per_second_at_1500": (bd - st) * 1500}
        print(f"    evaluator frame, {label}: {'stock with lfo4' if l4 is not None else 'stock'} {st}, "
              f"build {bd}{' without lfowaves' if lw else ''}: "
              f"ours {bd - st} instructions a frame, {(bd - st) * 1500:,} a second", flush=True)
        # 2026-11-17 (the User: the same work every frame, no skip by use): lfo4's cascade walks all 16 rows x 8 cells
        # every frame (csrc/modulation/cascade.c l4_frame), so its cost no longer depends on how many rows are written:
        # this is the constant-cost rule, not a skip. Bounds = the measured full walk (typical 2,050, worst 5,874 on
        # claude/mx-worst3's build 6e8d0023) plus about 10 %. Then lfo4 always runs its fourth LFO (the User: "Always run,
        # like LFO1-3"): typical 2,658, worst 6,482 measured on 30193cb7.
        bound = {"typical": 2900, "worst": 7100}[label]
        check(f"the cascade's {label} cost is under {bound:,} instructions a frame", 0 <= bd - st < bound,
              f"{bd - st} ({100 * (bd - st) / st:.0f} % of stock's evaluator, {st})")
        if lw:
            full = eval_cost(a.build, a.snapshot, sym, dests, without=lf)
            rep[label]["lfowaves"] = full - bd
            print(f"    evaluator frame, {label}: lfowaves' share {full - bd} instructions a frame "
                  f"(the build with it {full})", flush=True)
            # 2026-11-17: lfo4 always runs its fourth LFO through the same hooks: 64 LFOs (1,088 measured on 30193cb7)
            check(f"lfowaves' {label} share is under 1,200 instructions a frame (64 LFOs at a stock wave)",
                  0 <= full - bd < 1200, f"{full - bd}")
        if lf:
            fast = eval_cost(a.build, a.snapshot, sym, dests)
            ref = full if lw else eval_cost(a.build, a.snapshot, sym, dests, without=lf)
            rep[label]["lfo_fast"] = {"shipped": fast, "stock_evaluator": ref, "saved": ref - fast}
            print(f"    evaluator frame, {label}: lfo_fast {fast}, the build on stock's evaluator {ref}: "
                  f"{ref - fast} instructions a frame fewer", flush=True)
            check(f"lfo_fast: the {label} frame costs fewer instructions than on stock's evaluator", fast < ref,
                  f"{fast} vs {ref}")
    report["cost"] = rep


# --- line ---------------------------------------------------------------------------------
def frame(m, sym):
    """one audio frame's parameter path, by hand (the emulator runs no audio interrupt): stock's
    smoother, the six sources (the build's smp_mod_apply), the LFOs (the build's mod_eval)"""
    from emu_encoder_trace import STACK_TOP  # noqa: F401  (guest's stack)
    frac = m.alloc(len(SET_FRAC))
    m.write(frac, SET_FRAC)
    m.flush()
    guest(m, frac)
    guest(m, SMOOTHER, SRC)
    guest(m, sym["smp_mod_apply"], OUT)
    o1, o2 = m.alloc(256), m.alloc(256)
    guest(m, sym["mod_eval"], OUT, m.long(RATE), 0, 0, o1, o2, 0)


class Counter:
    """instructions from a routine's entry to its return, each time it runs (the UI's own draw)"""

    def __init__(self, m, entry):
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as K
        self.m, self.runs, self.h, self.ret, self.n = m, [], None, None, 0

        def tick(uc, ad, sz, us):
            if ad == self.ret:
                uc.hook_del(self.h)
                self.h = None
                self.runs.append(self.n)
            else:
                self.n += 1

        def enter(uc, ad, sz, us):
            if self.h is None:
                sp = uc.reg_read(K.UC_M68K_REG_A7)
                self.ret = struct.unpack(">I", bytes(uc.mem_read(sp, 4)))[0]
                self.n = 0
                self.h = uc.hook_add(UC_HOOK_CODE, tick)
        m.uc.hook_add(UC_HOOK_CODE, enter, begin=entry, end=entry)


def scenario_line(a, report, sym):
    from emulib.panel import Panel
    from unicorn import UC_HOOK_CODE
    m = machine(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/modulation").with_suffix("")) + "_png")
    m.write(UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check("track 1 is WaveTone", set_machine(m, panel, 0, 1) == 1)
    cells = []

    def on_cell(uc, ad, sz, us):
        sp = m.uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
        cv, x0, y0, rid = struct.unpack(">4I", m.read(sp + 4, 16))
        cells.append((cv, x0 if x0 < 0x80000000 else x0 - (1 << 32), y0 if y0 < 0x80000000 else y0 - (1 << 32), rid))
    h = m.uc.hook_add(UC_HOOK_CODE, on_cell, begin=sym["mv_cell"], end=sym["mv_cell"])
    frame(m, sym)                           # OUT = the smoother's state + the sources, as after any frame
    rest_on_sound(m)                        # ... settled on the sound's values, nothing added
    v, s = 0, 67
    m.write(sym["sl_lastv"], b"\x00")       # track 1 last played voice 1, which plays it
    m.write(OWNER, struct.pack(">I", 0))
    lines0 = m.long(0x46AF8000 + 0x500 + 8)
    panel.tap((0, 1))                       # SYN 1 of WaveTone, TUN1 and TUN2 among its cells
    panel.settle(20_000_000)
    drawn = len(cells)
    check("nothing modulated: no line on the SYN page (TUNE included)", m.long(0x46AF8000 + 0x500 + 8) == lines0
          and drawn > 0, f"{m.long(0x46AF8000 + 0x500 + 8) - lines0} lines over {drawn} cells")
    cells.clear()
    panel.tap((0, 2))                       # FLTR
    panel.settle(20_000_000)
    freq = [c for c in cells if c[3] == 36]
    freq_cells = list(cells)
    check("the FLTR page draws FREQ (record 36) through wr_cell", bool(freq), f"{len(cells)} cells")
    if not freq:
        return
    canvas, x0, y0, _ = freq[-1]
    print(f"    FREQ's cell at ({x0}, {y0}); cells drawn: {sorted(set((c[1], c[2], c[3]) for c in cells))}", flush=True)
    setv = stored(m, s)
    r = record(m, 36)
    lo, hi = r[2], r[3]
    dy = a.mv_dy

    def line_pixels():
        from emu import panel as P
        lit = P.lit(glass(m))
        yp = 63 - (y0 + dy)
        return [x for x in range(x0, x0 + 24) if (x, yp) in lit]

    report["line"] = {"cell": [x0, y0], "set": setv, "range": [lo, hi]}
    shots = {}
    for name, heard in (("half", (lo + hi) // 2), ("top", hi), ("low", lo + (hi - lo) // 10)):
        if heard == setv:
            heard += 0x100
        cells.clear()
        w16(m, OUT + 2 * idx(v, s), heard)
        asks0 = m.long(0x46AF8000 + 0x500 + 16)
        m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 100))
        panel.settle(30_000_000)
        asks = m.long(0x46AF8000 + 0x500 + 16) - asks0
        px = line_pixels()
        want = (heard - lo) * 20 // (hi - lo)
        shots[name] = panel.screen(f"line-{name}")
        check(f"heard {heard:#06x} (set {setv:#06x}): the UI updated the line itself", asks > 0, f"{asks}")
        check(f"heard {heard:#06x}: a line of {want + 1} px in row y0+{dy}", px is not None and len(px) >= want + 1
              and min(px) == x0 + 1 and max(px) == x0 + 1 + want, f"{px}")
    cells.clear()
    w16(m, OUT + 2 * idx(v, s), setv)
    m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 100))
    panel.settle(20_000_000)
    px = line_pixels()
    check("heard = set, inside the linger: the line stays", bool(px), f"{px}")
    m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 700))
    panel.settle(30_000_000)
    px_after = line_pixels()
    shots["none"] = panel.screen("line-none")
    check("heard = set, 400 ms later: no line", px_after is not None and len(px_after) <= 1, f"{px_after}")
    m.uc.hook_del(h)
    # costs, in the UI's own draws: mv_cell per cell, the whole screen, a poll
    cc, cs, cp = Counter(m, sym["mv_cell"]), Counter(m, sym["wr_screen"]), Counter(m, sym["mv_poll"])
    m.flush()                               # (a hook added after a block was translated is not seen)
    w16(m, OUT + 2 * idx(v, s), (lo + hi) // 2)
    m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 100))
    panel.settle(30_000_000)
    with_line = (list(cc.runs), list(cs.runs))
    cc.runs.clear(); cs.runs.clear()
    w16(m, OUT + 2 * idx(v, s), setv)
    m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 700))
    panel.settle(30_000_000)                # the poll asks for the draw that takes the line away
    without = (list(cc.runs), list(cs.runs))
    cost = {"mv_cell_with_line": max(with_line[0]) if with_line[0] else None,
            "mv_cell_without": max(without[0]) if without[0] else None,
            "screen_with_line": with_line[1][-1] if with_line[1] else None,
            "screen_without": without[1][-1] if without[1] else None,
            "poll": max(cp.runs) if cp.runs else None, "polls": len(cp.runs)}
    # the worst case: every sound cell of the page modulated (heard at the top of its range)
    cc.runs.clear(); cs.runs.clear(); cp.runs.clear()
    page_ids = sorted({c[3] for c in freq_cells})
    for rid in page_ids:
        r_ = record(m, rid)
        if 1 <= r_[1] <= 100:
            w16(m, OUT + 2 * idx(v, r_[1]), r_[3] if u16(m, OUT + 2 * idx(v, r_[1])) != r_[3] else r_[2])
    m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 100))
    panel.settle(30_000_000)
    cost["screen_all_modulated"] = cs.runs[-1] if cs.runs else None
    cost["mv_cells_all_modulated"] = sum(cc.runs[-9:]) if cc.runs else None
    cost["poll_all_modulated"] = max(cp.runs) if cp.runs else None
    report["line"].update({"cost": cost, "screens": shots})
    print(f"    instructions: {cost}", flush=True)


# 2026-11-12: our own pages (md_page.c, smp_page.c) draw their knobs themselves and call mv_knob for each
OURS = (("MACHINEDRUM", 5), ("SOPHIE", 53), ("PLAITS", 55), ("TB303", 54), ("DRONE", 52), ("ANALOG2", 51),
        ("MONOMACHINE", 6), ("ONESHOT", 8), ("SLICE", 13), ("JUNO", 50))   # 2026-11-13: + JUNO


LFO_ON = ("MACHINEDRUM", "MONOMACHINE")       # a real LFO, run by the evaluator, on these two


def lfo_moves(m, panel, sym, name, s, x, y, w, row_lit, shots):
    """voice 1's LFO1 aimed at slot S at full depth (LFO2, LFO3 without), the frame's parameter path run 150 frames (0.1 s)
    between screens: the knob's line must move by itself (several lengths), then leave once LFO1's
    depth is back at zero (heard = set again) past the linger"""
    lfo = {slot(1, "SPD"): 0x5800, slot(1, "MULT"): 4 << 8, slot(1, "FADE"): 0x4000, slot(1, "DEST"): s << 8,
           slot(1, "WAVE"): 0, slot(1, "SPH"): 0, slot(1, "MODE"): 0, slot(1, "DEP"): TOP,
           slot(2, "DEP"): 0x4000, slot(3, "DEP"): 0x4000}     # the sound's own LFO2 and LFO3: no depth
    keep = {k: (u16(m, SRC + 2 * idx(0, k)), m.read(STATE + 4 * idx(0, k), 4)) for k in lfo}
    for k, val in lfo.items():
        w16(m, SRC + 2 * idx(0, k), val)
        m.write(STATE + 4 * idx(0, k), struct.pack(">I", val << 16))
    frac = m.alloc(len(SET_FRAC))
    m.write(frac, SET_FRAC)
    m.flush()
    guest(m, frac)
    rate, o1, o2 = m.long(RATE), m.alloc(256), m.alloc(256)

    def run(frames):
        for _ in range(frames):
            guest(m, SMOOTHER, SRC)
            guest(m, sym["mod_eval"], OUT, rate, 1, 1, o1, o2, 0)
        m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + frames))
        panel.settle(30_000_000)

    seen = []
    for k in range(6):
        run(150)
        px = row_lit(x, y, w) or []
        seen.append((min(px), max(px)) if px else None)
        shots[f"{name}-lfo{k}"] = panel.screen(f"{name}-lfo{k}")
    ends = {e for e in seen if e}
    check(f"{name}: LFO1 -> slot {s} at full depth: the line moves by itself", len(ends) >= 3, f"{seen}")
    w16(m, SRC + 2 * idx(0, slot(1, "DEP")), 0x4000)       # DEP's middle: no depth
    m.write(STATE + 4 * idx(0, slot(1, "DEP")), struct.pack(">I", 0x4000 << 16))
    run(150)
    run(700)
    px = row_lit(x, y, w)
    check(f"{name}: LFO1's depth back to zero: no line past the linger", px == [], f"{px}")
    for k, (src, st) in keep.items():
        w16(m, SRC + 2 * idx(0, k), src)
        m.write(STATE + 4 * idx(0, k), st)
    return seen


def ours_machine(m, panel, mtype):
    """track 1 on MTYPE: MACHINE SEL's commit, else the sound's type byte as mnmpages pokes it"""
    if set_machine(m, panel, 0, mtype) == mtype:
        return True
    kit = m.long(KIT)
    m.write(kit + 52 + 0xDE, bytes([mtype]))
    m.flush()
    panel.settle(5_000_000)
    return struct.unpack(">b", m.read(kit + 52 + 0xDE, 1))[0] == mtype


def scenario_ours(a, report, sym):
    """each of our machines' SYN page 1: every knob drawn calls mv_knob with a row that is free (no lit
    pixel across the line's width before anything is modulated, so the line never overdraws the
    page); then the first knob's heard value moved: exactly the line moving.c's rule gives, in that
    row, and no line once heard = set again past the linger"""
    from emulib.panel import Panel
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    m = machine(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/modulation").with_suffix("")) + "_ours_png")
    from emu import panel as P                  # (digikit's, on the path once a Panel exists)
    m.write(UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    knobs = []

    def on_knob(uc, ad, sz, us):
        sp = uc.reg_read(K.UC_M68K_REG_A7)
        vals = struct.unpack(">7i", m.read(sp + 4, 28))
        knobs.append(vals[1:])                  # x, y, w, id, lo, hi
    m.uc.hook_add(UC_HOOK_CODE, on_knob, begin=sym["mv_knob"], end=sym["mv_knob"])
    m.uc.hook_add(UC_HOOK_CODE, lambda uc, ad, sz, us: knobs.clear(),   # the last draw's knobs only
                  begin=sym["mv_begin"], end=sym["mv_begin"])
    m.flush()
    frame(m, sym)
    m.write(sym["sl_lastv"], b"\x00")           # track 1 last played voice 1, which plays it
    m.write(OWNER, struct.pack(">I", 0))
    rep, shots = {}, {}

    def row_lit(x, y, w):
        lit = P.lit(glass(m))
        return [k for k in range(w) if (x + k, 63 - y) in lit]

    for name, mtype in OURS:
        if not ours_machine(m, panel, mtype):
            check(f"{name}: track 1 set to type {mtype}", False)
            continue
        rest_on_sound(m)                        # nothing modulated: heard = set on every slot of voice 1 (the
                                                # snapshot's sound has its own sources), past any linger
        m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 700))
        pages = []
        for tap in range(3):                    # SYN cycles the pages (3 at most): each one once
            knobs.clear()
            panel.tap((0, 1))
            panel.settle(40_000_000)            # past the page title's flash
            drawn = {}
            for x, y, w, rid, lo, hi in knobs:
                drawn[rid] = (x, y, w, lo, hi)
            if drawn and drawn in pages:
                break
            pages.append(drawn)
            twice = sorted({rid for _x, _y, _w, rid, _lo, _hi in knobs
                            if sum(k[3] == rid for k in knobs) > 1})
            check(f"{name}, page {tap + 1} seen: no control drawn in two places", not twice,
                  f"records {twice} ({len(knobs)} places, {len(drawn)} controls)")
            busy = {f"{rid}@({x},{y})": px for rid, (x, y, w, lo, hi) in drawn.items() if (px := row_lit(x, y, w))}
            check(f"{name}, page {tap + 1} seen: every knob's line row is free while nothing is modulated", not busy,
                  f"{busy}")
            shots[f"{name}-p{tap + 1}"] = panel.screen(f"{name}-p{tap + 1}")
        drawn = max(pages, key=len) if pages else {}
        check(f"{name}: its pages call mv_knob for their knobs", sum(map(len, pages)) >= 4,
              f"{[len(p) for p in pages]} knobs")

        def to_page(want_drawn):
            for _ in range(3):
                if dict((r, (x, y, w, lo, hi)) for x, y, w, r, lo, hi in knobs) == want_drawn:
                    return True
                knobs.clear()
                panel.tap((0, 1))
                panel.settle(40_000_000)
            return dict((r, (x, y, w, lo, hi)) for x, y, w, r, lo, hi in knobs) == want_drawn

        def movable(page):
            return [r for r in page if 0 < record(m, r)[1] <= 100 and page[r][4] > page[r][3]]

        def prove(rid, entry, tag):
            """the knob's heard value moved: exactly moving.c's line in its row; none once heard = set past the linger"""
            x, y, w, lo, hi = entry
            s = record(m, rid)[1]
            setv = stored(m, s)
            heard = lo + (hi - lo) * 3 // 4
            if heard == setv:
                heard += 0x100
            w16(m, OUT + 2 * idx(0, s), heard)
            m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 100))
            panel.settle(30_000_000)
            at = (min(max(heard, lo), hi) - lo) * (w - 1) // (hi - lo)
            frm = (w - 1) // 2 if 2 * record(m, rid)[4] == lo + hi else 0
            want = list(range(min(frm, at), max(frm, at) + 1))
            px = row_lit(x, y, w)
            shots[f"{name}-{tag}"] = panel.screen(f"{name}-{tag}")
            check(f"{name}{' ' + tag if tag != 'line' else ''}: record {rid} (slot {s}) heard {heard:#06x} of "
                  f"{lo:#x}..{hi:#x}: the line in row {y}", px == want, f"lit {px}, want {want[0]}..{want[-1]}")
            w16(m, OUT + 2 * idx(0, s), setv)
            m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 700))
            panel.settle(30_000_000)
            m.write(FRAMES, struct.pack(">I", m.long(FRAMES) + 700))
            panel.settle(30_000_000)
            px = row_lit(x, y, w)
            check(f"{name}{' ' + tag if tag != 'line' else ''}: heard = set, 400 ms later: no line", px == [], f"{px}")
            return {"record": rid, "line": [x, y, w], "range": [lo, hi]}

        to_page(drawn)                          # back to the page with the most knobs
        cand = movable(drawn)
        if not cand:
            check(f"{name}: a knob to modulate", False)
            continue
        rep[name] = {"knobs": [len(p) for p in pages], **prove(cand[0], drawn[cand[0]], "line")}
        # 2026-11-13: a sample machine's page 2 bottom row (E, F, G, H's pill): its lines on row 7 (MV_LINE: y 9 - 2)
        bottom = [(p, r) for p in pages for r in movable(p) if p[r][1] == 7]
        if bottom:
            page, rid = bottom[0]
            check(f"{name}: back on the page with the bottom row", to_page(page))
            rep[name]["bottom"] = prove(rid, page[rid], "bottom")
        if name in LFO_ON:                      # the first knob's: LFO1 at full depth on its slot
            to_page(drawn)
            x, y, w, _lo, _hi = drawn[cand[0]]
            rep[name]["lfo"] = lfo_moves(m, panel, sym, name, record(m, cand[0])[1], x, y, w, row_lit, shots)
    report["ours"] = {"pages": rep, "screens": shots}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--before", default=None)
    p.add_argument("--snapshot", default=SNAP)
    p.add_argument("--scenario", default="lists,cascade,line,ours,locks,cost")
    p.add_argument("--frames", type=int, default=3000)
    p.add_argument("--mv-dy", type=int, default=MV_DY_DEFAULT)
    p.add_argument("--json", default=None)
    a = p.parse_args()
    lay = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    report = {}
    for sc in a.scenario.split(","):
        print(f"  --- {sc} ---", flush=True)
        {"lists": lambda: scenario_lists(a, report),
         "cascade": lambda: scenario_cascade(a, report, lay),
         "cost": lambda: scenario_cost(a, report, lay),
         "line": lambda: scenario_line(a, report, lay),
         "ours": lambda: scenario_ours(a, report, lay),
         "locks": lambda: __import__("emu_modlocks").scenario_locks(sys.modules[__name__], a, report, lay)}[sc]()
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print(("FAIL: " + "; ".join(FAILS[:6])) if FAILS else "PASS: modulation (" + a.scenario + ")")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
