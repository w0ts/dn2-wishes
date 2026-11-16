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
env      ENV1 (the clone of stock's AMP envelope, from the voice row's AMP cells) and ENV2 (from the record), through
         HOLD's own note hooks (csrc/hold hold_len, hold_final: the paths the frame takes), each routed into a cell:
         the cell every frame as test_matrix_c.model's level gives it (ADSR, AHD, RSET off). The model against
         stock's own envelope is scripts/sharc_matrix_env.py's (the gate's envclone step).
cost     the evaluator call with no route anywhere and with every track's 23 routes set: the same instructions (the
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

TAG, ENV_TAG = 0x0010, 0x0011           # WT_MX_ROUTES, WT_MX_ENV (csrc/wishes/wish.h)
VSOUND = 0x800052A8                     # the sound each voice plays
WISH_MAP = (0x47280000, 0x500000)       # the wishes record's RAM and the matrix's tables (dnfw.waverider.pages)
LFO, SLOTS, TOP, NONE = 15, 23, 0x7F00, 0x4000
FULL, REST = 0x7FFFFFFF, 0x100
COST_BOUND = 10000                      # the matrix's instructions a frame (16 rows: 2 envelopes, 23 routes; 9,466 measured)
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


def put_field(m, sym, t, tag, val):
    buf = m.alloc(max(len(val), 4))
    m.write(buf, val)
    m.flush()
    return m.call(sym["wish_put"], sound(m, t), tag, buf, len(val)) & 0xFFFFFFFF


def put_routes(m, sym, t, rs):
    return put_field(m, sym, t, TAG, b"".join(struct.pack(">BBH", src, slot, dep) for src, slot, dep in rs))


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
                r = put_routes(m, sym, v, [(k % 3, 25 + 3 * k, 0x5000 + 0x100 * k) for k in range(LFO)]
                               + [(3 + k // 4, 70 + k, 0x3000 + 0x200 * k) for k in range(8)])
                check(f"full: track {v}'s 23 routes put", r == 0, f"{r:#x}")
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


def scenario_env(a, report, sym):
    """ENV1 (the row's AMP cells) and ENV2 (the record) through HOLD's own note hooks, each routed at full depth into a
    cell: the cell every frame as test_matrix_c.model's level gives it (the clone's arithmetic; scripts/sharc_matrix_env.py
    holds that model to stock's AMP envelope in the SHARC runner)"""
    sys.path.insert(0, str(HERE.parent / "test"))
    import test_matrix_c as T
    rep = {}
    cases = ["ADSR, held then released", "AHD, held until the note-off", "RSET off: a note-on goes on from the level"]
    for name in cases:
        knobs, events, frames = T.CASES[name]
        frames = min(frames, 200)
        m = setup(a.build, a.snapshot)
        v1, v2, slot, base = 5, 6, 60, 0x2000
        for v in range(16):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
            for k in (1, 2, 3):
                set_lfo(m, v, k, 0, 4, 0, NONE)
        for s, kn in zip((81, 82, 83, 84, 85, 91, 92), knobs):      # ENV1: voice v1's own AMP cells
            set_cell(m, v1, s, kn << 8)
        set_cell(m, v1, slot, base)
        set_cell(m, v2, slot, base)
        put_routes(m, sym, v1, [(3, slot, TOP)])
        put_routes(m, sym, v2, [(4, slot, TOP)])
        put_field(m, sym, v2, ENV_TAG, bytes(list(knobs) + [0]))
        m.flush()
        m.call(sym["mx_poll"])
        rate = m.long(MO.RATE)
        o1, o2 = m.alloc(256), m.alloc(256)
        w40 = m.alloc(4)
        got = {v1: [], v2: []}
        for f in range(frames):
            ev = events.get(f)
            if ev == "on":                                          # the frame's note-on, as hold_note_hook calls it
                for v in (v1, v2):
                    m.call(sym["hold_len"], v, v, 100)
            if ev == "off":                                         # the frame's note-off word
                m.write(w40, bytes(4))
                m.flush()
                m.call(sym["hold_final"], (1 << v1) | (1 << v2), w40)
            m.call(MO.SMOOTHER, MO.SRC)
            m.call(sym["mod_eval"], MO.OUT, rate, 1, 1, o1, o2, 0, limit=4_000_000)
            for v in (v1, v2):
                got[v].append(MO.u16(m, MO.OUT + 2 * MO.idx(v, slot)))
        d1 = (TOP - NONE) * 2
        want = [max(0, min(TOP, base + ((d1 * x) >> 31))) for x in T.model(knobs, events, frames)]
        for v, label in ((v1, "ENV1 (the row's AMP cells)"), (v2, "ENV2 (the record)")):
            bad = [f for f in range(frames) if got[v][f] != want[f]]
            check(f"{name}: {label} routed, every frame as the clone's model", not bad,
                  f"{len(bad)} frames differ, first {[(f, got[v][f], want[f]) for f in bad[:3]]}" if bad
                  else f"{frames} frames, {min(got[v]):#06x}..{max(got[v]):#06x}")
        rep[name] = {"frames": frames, "env1_differ": sum(1 for f in range(frames) if got[v1][f] != want[f]),
                     "env2_differ": sum(1 for f in range(frames) if got[v2][f] != want[f])}
    report["env"] = rep


def scenario_popup(a, report, sym):
    """the routes popup through the panel (csrc/matrix/routes_pop.c): WaveTone's FLTR page, FUNC + a short push on
    FREQ's knob opens it; turning makes LFO1's route (stock's route 1: its DEST and DEP), push-and-turn moves to LFO2
    (its own route 1) and to ENV1 (a route of the record); YES keeps them; a route turned back to 0 goes at the close;
    NO undoes; FUNC + a long push resets FREQ to its record's default"""
    from emulib.panel import DOWN, ENCODER_PUSH, NO, UP, YES, Panel
    from unicorn import UC_HOOK_CODE
    m = setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/matrix").with_suffix("")) + "_png")
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check("popup: track 1 is WaveTone", MO.set_machine(m, panel, 0, 1) == 1)
    cells = []

    def on_cell(uc, ad, sz, us):
        sp = m.uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
        cv, x0, y0, rid = struct.unpack(">4I", m.read(sp + 4, 16))
        cells.append((x0, y0, rid))
    h = m.uc.hook_add(UC_HOOK_CODE, on_cell, begin=sym["mv_cell"], end=sym["mv_cell"])
    panel.tap((0, 2))                                   # FLTR
    panel.settle(20_000_000)
    m.uc.hook_del(h)
    freq = [(x, y, rid) for x, y, rid in cells if MO.record(m, rid)[1] == 67]
    check("popup: FREQ (slot 67) is on the FLTR page", bool(freq), str(sorted(set(cells))[:8]))
    if not freq:
        return
    x, y, rid = freq[-1]
    k = (x - 24 + 13) // 26 + (4 if y < 13 else 0)
    snd = m.long(MO.KIT) + 52
    param = lambda slot: struct.unpack(">H", m.read(snd + 20 + 2 * slot, 2))[0]        # noqa: E731
    visible = lambda: MO.guest(m, sym["mxp_visible"]) & 0xFFFFFFFF   # noqa: E731 -- guest: the running UI's registers kept
    FUNC = (2, 0)
    crash = {}

    def on_halt(uc, ad, sz, us):                        # stock's fault dump ends at this halt: the stack, for the cause
        if not crash:
            sp = uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
            words = struct.unpack(">96I", bytes(uc.mem_read(sp, 384)))
            crash["sp"] = sp
            crash["ours"] = [(i, hex(w)) for i, w in enumerate(words) if 0x46A40000 <= w < 0x46AF0000][:12]
            crash["words"] = [hex(w) for w in words[:40]]
    m.uc.hook_add(UC_HOOK_CODE, on_halt, begin=0x4011EDEC, end=0x4011EDEC)

    def func_push(frames):
        """FUNC held, K's push held FRAMES frames (the emulator runs no audio interrupt: its frame count is moved
        by hand, as the time the push is held), let go"""
        panel.hold(FUNC, 2_000_000)
        panel.hold(ENCODER_PUSH[k], 2_000_000)
        m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + frames) & 0xFFFFFFFF))
        m.flush()
        panel.settle(3_000_000 if frames < 600 else 15_000_000)   # the UI pass (wr_poll) sees the push held that long
        panel.let_go(ENCODER_PUSH[k], 2_000_000)
        panel.let_go(FUNC, 5_000_000)
        return frames

    def counters():
        return {n: m.long(sym[n]) for n in ("mxp_pushes", "mxp_opens", "mxp_refusals", "mxp_why", "mxp_rid", "mxp_turns", "mxp_keys")}

    def detents():
        return struct.unpack(">i", m.read(sym["mxp_detents"], 4))[0]

    def turn(delta, times):
        """TIMES detents of DELTA on K, as the popup receives them: -> the detents it took (the panel task sums the
        encoder's counts over its timer ticks: each call here sends 4 counts, one detent's worth, settled apart)"""
        d0 = detents()
        for _ in range(8 * times):                      # until the popup has taken TIMES detents (the panel task
            if abs(detents() - d0) >= times:            # takes a turn's first counts from rest, as stock's knob step
                break                                   # does; docs/display-path.md)
            m.pc = panel.panelin.encoder(m.m, panel.profile, k, 4 * delta)
            panel.settle(4_000_000)
        panel.settle(10_000_000)
        return detents() - d0

    tbl = MO.guest(m, sym["sl_ui_table_now"]) & 0xFFFFFFFF  # two stock locks of FREQ on step 1 and 4, for LOCKS
    lockrec = None
    if tbl:
        heads = [m.read(tbl + 258 * i, 1)[0] for i in range(80)]
        lockrec = heads.index(0xFF) if 0xFF in heads else None
    if lockrec is not None:
        vals = [0xFFFF] * 128
        vals[0], vals[3] = 0x5000, 0x3000
        m.write(tbl + 258 * lockrec, bytes([67, 0]) + b"".join(struct.pack(">H", v)
                                                               for v in vals))
        m.flush()
    f0 = panel.frames()
    held = func_push(300)
    panel.settle(20_000_000)
    print(f"    screens composed: {f0} before the push, {panel.frames()} after it", flush=True)
    check("popup: FUNC + a short push opens it", visible() == 1, f"push held {held} frames (0.4 s = 600); {counters()}")
    if visible() != 1:
        return
    panel.screen("popup_open")
    from emu import panel as EP
    frame = bytes(panel.capture.frames[-1]) if panel.capture.frames else b""
    lit = EP.lit(frame) if frame else set()
    cell = lambda s: (30 + 4 * s, 63 - 5) in lit                                     # noqa: E731 (canvas y 5)
    check("popup: LOCKS shows FREQ's locks on steps 1 and 4, not on step 2", lockrec is not None and cell(0)
          and cell(3) and not cell(1), f"record {lockrec}, steps 1-4 filled: {[cell(s) for s in range(4)]}")
    buf = m.alloc(128)

    def record():
        n = MO.guest(m, sym["wish_get"], snd, TAG, buf, 128) & 0xFFFFFFFF
        return bytes(m.read(buf, n)) if n < 128 else b""
    def routes():
        rec = record()
        return [rec[i:i + 4] for i in range(0, len(rec), 4)]

    def depth_of(lfo, dest_slot, dep_slot):
        """-> (where, depth): the LFO's route into FREQ, stock's route 1 ('stock') or the record's ('record')"""
        if param(dest_slot) >> 8 == 67:
            return "stock", param(dep_slot)
        for r in routes():
            if r[0] == lfo and r[1] == 67:
                return "record", r[2] << 8 | r[3]
        return None, 0x4000

    mod = snd + 230                                     # MOD SETUP (stock's, read only): VEL into FREQ, AT twice
    mod0 = bytes(m.read(mod, 96))
    want = struct.pack(">hh", 0x2000, 67) + mod0[4:64] + struct.pack(">hhhh", -0x400, 67, 0x300, 67) + mod0[72:]
    m.write(mod, want)
    m.flush()
    rec0 = record()
    for _ in range(5):
        panel.tap(DOWN)
    vel = (struct.unpack(">i", m.read(sym["mxp_setup_dep"], 4))[0], m.long(sym["mxp_setup_rows"]))
    for _ in range(3):
        panel.tap(DOWN)
    at = (struct.unpack(">i", m.read(sym["mxp_setup_dep"], 4))[0], m.long(sym["mxp_setup_rows"]))
    panel.screen("popup_setup")
    turned = turn(+1, 1)
    check("popup: MOD SETUP's rows show VEL's and AT's routes into FREQ (AT's two summed), read only",
          vel[0] == 0x2000 and vel[1] & 1 and at[0] == -0x100 and at[1] & 9 == 9 and turned > 0
          and bytes(m.read(mod, 96)) == want and record() == rec0,
          f"VEL {vel}, AT {at}, turned {turned}")
    m.write(mod, mod0)
    m.flush()
    for _ in range(8):
        panel.tap(UP)
    got1 = turn(+1, 2)                                  # the lit row: LFO1
    where1, d1 = depth_of(0, 4, 8)
    check(f"popup: LFO1 turned {got1} detents: a route into FREQ at that depth (route 1 first if free)",
          got1 > 0 and d1 == 0x4000 + 0x100 * got1 and (where1 == "stock" or param(4) >> 8 not in (0, 67)),
          f"{where1} {d1:#06x}, LFO1 DEST {param(4):#06x}")
    panel.push_and_turn(k, +1, times=1)                 # LFO2
    got2 = turn(+1, 2)
    where2, d2 = depth_of(1, 12, 16)
    check(f"popup: push-and-turn to LFO2, {got2} detents: its route", got2 > 0 and d2 == 0x4000 + 0x100 * got2,
          f"{where2} {d2:#06x}")
    panel.push_and_turn(k, +1, times=2)                 # ENV1
    got3 = turn(-1, 2)
    want3 = 0x4000 + 0x100 * got3
    panel.screen("popup_routes")
    check(f"popup: ENV1, {got3} detents: a route of the record", got3 < 0
          and bytes([3, 67, want3 >> 8, want3 & 0xFF]) in routes(), record().hex())
    panel.tap(YES)
    check("popup: YES closes it, the routes kept", visible() == 0 and depth_of(0, 4, 8)[1] == d1
          and depth_of(1, 12, 16)[1] == d2, f"visible {visible()}, {depth_of(0, 4, 8)}, {depth_of(1, 12, 16)}")
    func_push(300)                                      # LFO1 lit again: back to 0, gone at the close
    back = 0
    for _ in range(80):                                 # a count at a time, so it stops on 0 (a record can carry
        cur = depth_of(0, 4, 8)[1]                      # several detents)
        if cur == 0x4000:
            break
        d0 = detents()
        m.pc = panel.panelin.encoder(m.m, panel.profile, k, -1 if cur > 0x4000 else 1)
        panel.settle(4_000_000)
        back += detents() - d0
    panel.tap(YES)
    check("popup: a route turned back to 0 goes at the close", depth_of(0, 4, 8)[0] is None
          and depth_of(1, 12, 16)[1] == d2, f"{back} detents back; LFO1 {depth_of(0, 4, 8)}, LFO2 {depth_of(1, 12, 16)}")
    before = (record(), param(4), param(8), param(12), param(16))
    func_push(300)
    panel.push_and_turn(k, +1, times=1)
    turn(+1, 3)
    panel.tap(NO)
    after = (record(), param(4), param(8), param(12), param(16))
    check("popup: NO undoes every change", after == before and visible() == 0, f"{after} vs {before}")
    m.write(snd + 20 + 2 * 67, struct.pack(">H", 0x1234))
    m.flush()
    held = func_push(1000)
    want = MO.record(m, rid)[4]
    check("popup: FUNC + a long push resets FREQ to its default", param(67) == want and visible() == 0,
          f"FREQ {param(67):#06x}, default {want:#06x}, held {held} frames (0.6 s = 900)")
    rec = record()
    report["popup"] = {"knob": k, "rid": rid, "record": rec.hex()}


def scenario_env2lock(a, report, sym):
    """ENV2's locks through the panel (csrc/matrix/env2_page.c, csrc/slides): AMP 2/3, a trig held on step 1, knob A
    (ATK) turned: the step's ENV2 ATK lock (a record of ours, kind 3); the lock list's tail carries it (sl_build); SAVE
    writes it as stored id 203, LOAD brings it back as it was"""
    from emulib.panel import Panel
    m = setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/matrix").with_suffix("")) + "_png")
    key = lambda code: divmod(code - 1, 8)                                            # noqa: E731
    g = lambda fn, *args: MO.guest(m, sym[fn], *args) & 0xFFFFFFFF                    # noqa: E731
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check("env2lock: track 1 is WaveTone", MO.set_machine(m, panel, 0, 1) == 1)
    panel.tap(key(19))                                  # RECORD: grid recording (a held trig locks, as stock's)
    panel.settle(10_000_000)
    panel.tap(key(25))                                  # a trig on step 1
    panel.settle(10_000_000)
    panel.tap((0, 3))                                   # [AMP]: stock's page
    panel.settle(10_000_000)
    panel.tap((0, 3))                                   # [AMP] again: ENV2's
    panel.settle(10_000_000)
    check("env2lock: [AMP] twice is ENV2's page (AMP 2/3)", g("env2_visible") == 1)
    panel.hold(key(25), 5_000_000)                      # step 1 held
    panel.settle(10_000_000)
    lock = 0xFFFF
    for _ in range(12):                                 # knob A until the lock is there (the panel task sums counts)
        m.pc = panel.panelin.encoder(m.m, panel.profile, 0, 4)
        panel.settle(4_000_000)
        tbl = m.long(sym["sl_ui_table"])
        lock = g("sl_lock_get", tbl, 0, 0, 3) if tbl else 0xFFFF
        if lock != 0xFFFF:
            break
    panel.screen("env2_locked")
    snd0 = m.long(MO.KIT) + 52
    eb = m.alloc(16)
    n = g("wish_get", snd0, ENV_TAG, eb, 8)
    print(f"    held: ENV2 page up {g('env2_visible')}, slides' held lock {g('sl_e2_held', 0):#x}, ENV2 record "
          f"{bytes(m.read(eb, 8)).hex() if n == 8 else None}, popup turns {m.long(sym['mxp_turns'])}", flush=True)
    panel.let_go(key(25))
    panel.settle(10_000_000)
    tbl = m.long(sym["sl_ui_table"])
    check("env2lock: a trig held, A turned: step 1's ENV2 ATK lock (above the sound's 8)", tbl != 0 and 8 < lock <= 127,
          f"table {tbl:#x}, lock {lock:#06x}")
    if not tbl or lock == 0xFFFF:
        return
    snd = m.long(MO.KIT) + 52
    lst = m.alloc(1700)
    m.write(lst, bytes(1700))
    m.flush()
    g("sl_build", 0, lst, tbl, snd, 0, 0, 0)
    e2 = struct.unpack(">6H", m.read(lst + 1600 + 16, 12))
    check("env2lock: the lock list carries it (sl_build: the tail's ENV2 values)", e2[0] == lock
          and all(x == 0xFFFF for x in e2[1:]), str([hex(x) for x in e2]))
    stored = m.alloc(258 * 80)
    m.write(stored, bytes(258 * 80))
    m.flush()
    g("sl_save", stored, tbl)
    recs = [bytes(m.read(stored + 258 * i, 4)) for i in range(80)]
    ours = [r for r in recs if r[0] == 203 and r[1] == 0]
    check("env2lock: SAVE writes it as stored id 203, track 1", len(ours) == 1, str([r.hex() for r in recs if r[0] >= 200]))
    ram2 = m.alloc(258 * 80)
    m.write(ram2, b"\xff" * (258 * 80))
    m.flush()
    g("sl_load", ram2, stored)
    back = g("sl_lock_get", ram2, 0, 0, 3)
    check("env2lock: LOAD brings it back as it was", back == lock, f"{back:#06x}")
    report["env2lock"] = {"lock": lock, "tail": list(e2)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", default=MO.SNAP)
    p.add_argument("--scenario", default="exact,env,popup,env2lock,cost")
    p.add_argument("--frames", type=int, default=240)
    p.add_argument("--json", default=None)
    a = p.parse_args()
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    report = {}
    for sc in a.scenario.split(","):
        print(f"  --- {sc} ---", flush=True)
        {"exact": lambda: scenario_exact(a, report, sym), "env": lambda: scenario_env(a, report, sym),
         "popup": lambda: scenario_popup(a, report, sym),
         "env2lock": lambda: scenario_env2lock(a, report, sym),
         "cost": lambda: scenario_cost(a, report, sym)}[sc]()
    report["ok"] = not FAILS
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print(("FAIL: " + "; ".join(FAILS[:6])) if FAILS else "PASS: matrix (" + a.scenario + ")")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
