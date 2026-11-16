"""Modulation on the ColdFire emulator, OS 1.12 (docs/modulation-more.md): the destination lists,
the LFO cascade, the moving controls' line.

    emu_modulation.py --build BUILD.syx [--before OLD.syx] [--scenario lists,cascade,cost,line] [--json OUT]

lists    the builder 0x4003951e called with the live ParameterSet of track 1, for LFO1 (want
         0x1e00), LFO2 (0xe00), LFO3 (0x600) and MOD SETUP (0x200), track 1 on WaveTone, FM TONE
         and PERC; stock 1.12 beside the build (and --before, the line it replaces). What must hold:
         nothing stock lists is lost; the 13 closed records are added to every list (8 of them FM
         TONE's own); each LFO's list adds the other LFOs' SPD MULT FADE WAVE SPH MODE DEP that
         stock leaves out, never its own controls, never a DEST.

cascade  the frame's LFO path called by hand (the emulator runs no audio interrupt): stock's
         smoother 0x400db28e, then the frame's call of the evaluator (the build's mod_eval, or
         stock's 0x40137a06), voice row 0 holding LFO1 -> LFO2 SPD and LFO2 -> LFO1 SPD at full
         depth, for many frames. What must hold: LFO2's SPD as LFO2 reads it moves on the build (it
         never does on stock), by what LFO1 wrote one frame earlier, exactly; every LFO cell stays
         in 0..0x7fff; the evaluator returns every frame (also with both SPDs and MULTs at their
         tops, at their bottoms, at zero speed).

cost     the evaluator call's instructions, build minus stock, all 16 rows at full depth: typical
         (no LFO aimed at an LFO above it) and worst (every row's LFO1 and LFO2 aimed at LFO3's
         controls); each must stay under its bound.

line     the FLTR page on track 1 (WaveTone): test values written into the heard array of the
         voice the track last played; the cell of FREQ (slot 67) must show a 1 px line in its row
         MV_DY, its length the heard value, none when heard = set (after the 400 ms linger), and
         the UI asks for a redraw by itself when the heard value moves. Before that, with nothing
         modulated, no line on WaveTone's SYN page. The instructions of mv_cell, of a poll and of
         the page's draws are printed, also with every cell of the page modulated (the worst case).

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
TOP = 0x7F00
MV_DY_DEFAULT = 5                   # csrc/modulation/moving.c MV_DY
FAILS: list[str] = []


def check(what, ok, detail=""):
    print(("  ok    " if ok else "  FAIL  ") + what + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        FAILS.append(what)


def idx(v, s):
    return 17 + 101 * v + s


# --- the machine ------------------------------------------------------------------------
def machine(build, snapshot):
    """the snapshot with stock 1.12's MAIN OS, then BUILD's (if any) as the loader leaves it"""
    from emulib.image import differences
    from emulib.machine import Machine
    m = Machine(snapshot)
    stock = open(pathlib.Path(os.environ["DT2_SECTIONS"]) / "section_3_MAIN_OS.bin", "rb").read()
    snap_sec = open(snapshot + ".section_3_MAIN_OS.bin", "rb").read()
    sec3 = None
    m.apply([(va, stock[va - BASE:va - BASE + len(b)]) for va, b in differences(stock, snap_sec)
             if va + len(b) <= BASE + len(stock)])
    if build:
        from dnfw.cli.files import read_image
        from dnfw.firmware.load import load
        from dnfw.mods import platform
        from unicorn import UC_PROT_ALL, UcError
        sec3 = load(read_image(pathlib.Path(build))).container.find(3).unpack()
        m.apply(differences(stock, sec3))
        for va, blob in platform.runtime(sec3):
            m.write(va, blob)
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
    def site(sec):
        for va, blob in platform.runtime(sec):
            if 0x46AC0000 <= va < 0x46AF0000 and blob.count(QRECV_CALL) == 1:
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
            check(f"{name} {lfo}: no DEST listed", not (set(DESTS) & bl))
            if rl is not None:
                extra = sorted(bl - rl - set(OPENED) - set(sum(LFO_CTL.values(), ())))
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
    rows, bad, faults = [], [], 0
    for f in range(frames):
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


def scenario_cascade(a, report, sym):
    n = a.frames
    rep = {}
    for label, build in (("stock", None), ("build", a.build)):
        rows, bad, faults, m = cascade_run(build, a.snapshot, n, 0x5800, 4, sym)
        h2 = [r[1] for r in rows]
        h1 = [r[0] for r in rows]
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
            late = [k for k in range(1, len(rows)) if rows[k][1] != max(0, min(TOP, 0x5800 + rows[k - 1][2]))]
            check("build: what LFO2 hears is what LFO1 wrote one frame earlier", not late, f"{len(late)} frames differ")
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


def eval_cost(build, snapshot, sym, dests, frames=8):
    """instructions of the frame's evaluator call (the build's mod_eval, or stock's 0x40137a06), all
    16 voice rows at full depth with LFO1/2/3 aimed at DESTS; -> the most over FRAMES frames"""
    m = machine(build, snapshot)
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
        worst = max(worst, n)
    return worst


def scenario_cost(a, report, sym):
    """the cascade's cost per audio frame, typical (no LFO aimed at an LFO) and worst (every row's
    LFO1 and LFO2 aimed at LFO3's controls, LFO3 at LFO2's: the most our hooks can do in one frame)"""
    typical = (67, 36 + 0, 72)                  # FREQ, a filter slot, VOL: no LFO's control
    worst = (17, 18, 9)                         # LFO1 -> LFO3 SPD, LFO2 -> LFO3 MULT, LFO3 -> LFO2 SPD
    rep = {}
    for label, dests in (("typical", typical), ("worst", worst)):
        st, bd = eval_cost(None, a.snapshot, sym, dests), eval_cost(a.build, a.snapshot, sym, dests)
        rep[label] = {"stock": st, "build": bd, "ours": bd - st, "per_second_at_1500": (bd - st) * 1500}
        print(f"    evaluator frame, {label}: stock {st}, build {bd}: ours {bd - st} instructions a frame, "
              f"{(bd - st) * 1500:,} a second", flush=True)
        bound = {"typical": 800, "worst": 4500}[label]
        check(f"the cascade's {label} cost is under {bound:,} instructions a frame", 0 <= bd - st < bound,
              f"{bd - st} ({100 * (bd - st) / st:.0f} % of stock's evaluator, {st})")
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
    st = struct.unpack(">I", m.read(STATE + 4 * idx(v, s), 4))[0]
    setv = (st + 0x8000) >> 16
    r = record(m, 36)
    lo, hi = r[2], r[3]
    dy = a.mv_dy

    def line_pixels():
        from emu import panel as P
        buf = bytes(panel.capture.frames[-1]) if panel.capture.frames else None
        if buf is None:
            return None
        lit = P.lit(buf)
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
        check(f"heard {heard:#06x} (set {setv:#06x}): the UI asked for the redraw itself", asks > 0, f"{asks}")
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--before", default=None)
    p.add_argument("--snapshot", default=SNAP)
    p.add_argument("--scenario", default="lists,cascade,line,cost")
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
         "line": lambda: scenario_line(a, report, lay)}[sc]()
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print(("FAIL: " + "; ".join(FAILS[:6])) if FAILS else "PASS: modulation (" + a.scenario + ")")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
