"""The matrix's routes on the ColdFire emulator, OS 1.12 (csrc/matrix/matrix.c, docs/matrix.md): the gate's check that a
route of ours is heard exactly as stock's own route 1 at the same depth, and what it costs.

    emu_matrix.py --build BUILD.syx --snapshot <ui800M snapshot of this build> [--frames 240] [--json OUT]

The frame's parameter path is called by hand, as scripts/emu_modulation.py calls it (the emulator runs no audio
interrupt): stock's smoother 0x400db28e, then the frame's evaluator call (the build's mod_eval: the cascade's pre-pass,
stock's evaluator 0x40137a06, then the matrix).

exact    two runs of the same machine, every voice row v set up differently (its LFO, wave, speed, a destination
         slot of the sound, a depth, the base the cell starts from; some depths at the clamp):
           stock:  the row's LFO has DEST = that slot and DEP = that depth (stock's route 1);
           ours:   DEST at slot 0 with DEP 0x4000 (adds nothing) and the route in the record of the sound the voice
                   plays (wish_put, then the UI pass mx_poll);
         the slot as heard (OUT) must be the same every frame of every row. Then all three LFOs into one slot (stock:
         three route 1s; ours: three routes listed LFO3, LFO2, LFO1, the order stock adds them, each clamped).
cost     the evaluator call with no route anywhere and with every track's 15 routes set: the same instructions (the
         User's constant cost) within the clamp's branches, and the matrix's own share (mx_eval) under its bound.

Last line PASS or FAIL.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import emu_modulation as MO                                         # noqa: E402 -- its machine and frame recipe

TAG = 0x0010                            # WT_MX_ROUTES (csrc/wishes/wish.h)
VSOUND = 0x800052A8                     # the sound each voice plays
WISH_MAP = (0x47280000, 0x500000)       # the wishes record's RAM and the matrix's tables (dnfw.waverider.pages)
SLOTS, TOP, NONE = 15, 0x7F00, 0x4000
COST_BOUND = 6000                       # the matrix's instructions a frame (16 rows x 15 routes)
FAILS: list[str] = []


def check(what, ok, detail=""):
    print(("  ok    " if ok else "  FAIL  ") + what + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        FAILS.append(what)


def setup(build, snapshot):
    from unicorn import UC_PROT_ALL, UcError
    m = MO.machine(build, snapshot)
    at, n = WISH_MAP
    for page in range(at & ~0xFFFFF, at + n, 0x100000):         # page by page: the snapshot may hold one already
        try:
            m.uc.mem_map(page, 0x100000, UC_PROT_ALL)
        except UcError:
            pass
    frac = m.alloc(len(MO.SET_FRAC))
    m.write(frac, MO.SET_FRAC)
    m.flush()
    m.call(frac)
    return m


def sound(m, t):
    return m.long(MO.KIT) + 52 + 1163 * t


def set_cell(m, v, s, val):
    """the target and the smoother already settled on it (as emu_modulation's cascade sets a row)"""
    MO.w16(m, MO.SRC + 2 * MO.idx(v, s), val)
    m.write(MO.STATE + 4 * MO.idx(v, s), struct.pack(">I", val << 16))
    MO.w16(m, MO.OUT + 2 * MO.idx(v, s), val)


def set_lfo(m, v, lfo, wave, mult, dest, dep):
    for f, val in (("SPD", 0x5800 + 0x300 * v), ("MULT", mult << 8), ("FADE", 0x4000), ("DEST", dest << 8),
                   ("WAVE", wave << 8), ("SPH", 0), ("MODE", 0), ("DEP", dep)):
        set_cell(m, v, MO.slot(lfo, f), val)


def put_routes(m, sym, t, rs):
    val = b"".join(struct.pack(">BBH", src, slot, dep) for src, slot, dep in rs)
    buf = m.alloc(max(len(val), 4))
    m.write(buf, val)
    m.flush()
    r = m.call(sym["wish_put"], sound(m, t), TAG, buf, len(val)) & 0xFFFFFFFF
    return r


def run(m, sym, frames, slots):
    """-> per frame, the heard value of each (row, slot) in SLOTS"""
    rate = m.long(MO.RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    out = []
    for _ in range(frames):
        m.call(MO.SMOOTHER, MO.SRC)
        m.call(sym["mod_eval"], MO.OUT, rate, 1, 1, o1, o2, 0, limit=4_000_000)
        out.append([MO.u16(m, MO.OUT + 2 * MO.idx(v, s)) for v, s in slots])
    return out


def plan_one():
    """row v: (lfo 1..3, wave, mult, slot, depth, base)"""
    depths = [0, 0x1000, 0x3FFF, 0x4000, 0x4001, 0x6000, TOP, 0x2000, 0x5555, 0x7E00, 0x0800, 0x4800, 0x3000,
              0x7000, 0x0100, 0x6FFF]
    bases = [0x3000, 0x7000, 0x0800, 0x4000]
    return [(1 + v % 3, v % 7, 4 + v % 5, 30 + 4 * v, depths[v], bases[v % 4]) for v in range(16)]


def scenario_exact(a, report, sym):
    rep = {}
    plan = plan_one()
    slots = [(v, p[3]) for v, p in enumerate(plan)]
    heard = {}
    for label in ("stock", "ours"):
        m = setup(a.build, a.snapshot)
        for v, (lfo, wave, mult, slot, dep, base) in enumerate(plan):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
            set_cell(m, v, slot, base)
            for k in (1, 2, 3):                                     # every LFO: DEST slot 0, adding nothing
                set_lfo(m, v, k, wave, mult, 0, NONE)
            if label == "stock":
                set_lfo(m, v, lfo, wave, mult, slot, dep)
            else:
                r = put_routes(m, sym, v, [(lfo - 1, slot, dep)])
                check(f"ours: row {v}'s route put in its sound's record", r == 0, f"{r:#x}")
        m.flush()
        m.call(sym["mx_poll"])
        heard[label] = run(m, sym, a.frames, slots)
        if label == "ours":
            rep["compiles"] = m.long(sym["mx_compiles"])
            check("ours: the UI pass laid the tables out", rep["compiles"] >= 1, str(rep["compiles"]))
    diff = [(f, v) for f in range(a.frames) for v in range(16) if heard["stock"][f][v] != heard["ours"][f][v]]
    moved = [v for v in range(16) if plan[v][4] != NONE and len({heard["stock"][f][v] for f in range(a.frames)}) > 1]
    check("one route a row: every frame of every row heard as stock's route 1", not diff,
          f"{len(diff)} differ, first {diff[:3]}" if diff else f"{a.frames} frames x 16 rows")
    check("the LFOs moved the slots (the comparison means something)", len(moved) >= 12, f"{len(moved)} rows moved")
    clamped = sum(1 for f in range(a.frames) for v in range(16) if heard["stock"][f][v] in (0, TOP))
    check("some frames clamped at 0 or 0x7f00", clamped > 0, str(clamped))
    rep["one_route"] = {"frames": a.frames, "rows_moved": len(moved), "clamped": clamped, "differ": len(diff)}

    # all three LFOs into one slot: stock adds LFO3, LFO2, LFO1 in that order, each clamped
    trio = [(30 + 4 * v, [0x7F00, 0x0800, 0x6000][v % 3], [0x1000, 0x7000, 0x5000][v % 2], 0x4000 + 0x400 * (v % 5))
            for v in range(16)]
    heard = {}
    for label in ("stock", "ours"):
        m = setup(a.build, a.snapshot)
        for v, (slot, d1, d2, d3) in enumerate(trio):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
            set_cell(m, v, slot, [0x3000, 0x7000, 0x0800][v % 3])
            deps = {1: d1, 2: d2, 3: d3}
            for k in (1, 2, 3):
                set_lfo(m, v, k, (v + k) % 7, 3 + k, slot if label == "stock" else 0, deps[k] if label == "stock" else NONE)
            if label == "ours":
                put_routes(m, sym, v, [(2, slot, d3), (1, slot, d2), (0, slot, d1)])
        m.flush()
        m.call(sym["mx_poll"])
        heard[label] = run(m, sym, a.frames, [(v, t[0]) for v, t in enumerate(trio)])
    diff = [(f, v) for f in range(a.frames) for v in range(16) if heard["stock"][f][v] != heard["ours"][f][v]]
    check("three routes into one slot: heard as stock's three route 1s", not diff,
          f"{len(diff)} differ, first {diff[:3]}" if diff else f"{a.frames} frames x 16 rows")
    rep["three_routes"] = {"frames": a.frames, "differ": len(diff)}
    report["exact"] = rep


def scenario_cost(a, report, sym):
    rep = {}
    for label in ("none", "full"):
        m = setup(a.build, a.snapshot)
        for v in range(16):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
            for k in (1, 2, 3):
                set_lfo(m, v, k, k, 4, 0, NONE)
            if label == "full":
                r = put_routes(m, sym, v, [(k % 3, 25 + 5 * k, 0x5000 + 0x100 * k) for k in range(SLOTS)])
                check(f"full: track {v}'s 15 routes put", r == 0, f"{r:#x}")
        m.flush()
        m.call(sym["mx_poll"])
        rate = m.long(MO.RATE)
        o1, o2 = m.alloc(256), m.alloc(256)
        worst_eval = worst_mx = 0
        for _ in range(8):
            m.call(MO.SMOOTHER, MO.SRC)
            _, n = m.cost(sym["mod_eval"], MO.OUT, rate, 0xFFFF, 0, o1, o2, 0)
            _, k = m.cost(sym["mx_eval"], MO.OUT)
            worst_eval, worst_mx = max(worst_eval, n), max(worst_mx, k)
        rep[label] = {"mod_eval": worst_eval, "mx_eval": worst_mx}
        print(f"    {label}: the frame's evaluator call {worst_eval} instructions, the matrix's share {worst_mx}",
              flush=True)
    d = abs(rep["full"]["mx_eval"] - rep["none"]["mx_eval"])
    check("constant cost: the matrix's instructions the same with no route and with every route", d <= 16 * SLOTS,
          f"none {rep['none']['mx_eval']}, full {rep['full']['mx_eval']} (the clamp's branches: at most one a route)")
    check(f"the matrix's cost under {COST_BOUND:,} instructions a frame", rep["full"]["mx_eval"] < COST_BOUND,
          f"{rep['full']['mx_eval']} ({rep['full']['mx_eval'] * 1500:,} a second at 1,500 frames)")
    report["cost"] = rep


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", default=MO.SNAP)
    p.add_argument("--scenario", default="exact,cost")
    p.add_argument("--frames", type=int, default=240)
    p.add_argument("--json", default=None)
    a = p.parse_args()
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    report = {}
    for sc in a.scenario.split(","):
        print(f"  --- {sc} ---", flush=True)
        {"exact": lambda: scenario_exact(a, report, sym), "cost": lambda: scenario_cost(a, report, sym)}[sc]()
    report["ok"] = not FAILS
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print(("FAIL: " + "; ".join(FAILS[:6])) if FAILS else "PASS: matrix (" + a.scenario + ")")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
