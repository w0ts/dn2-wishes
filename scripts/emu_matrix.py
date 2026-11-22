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
hold     keys held as the unit sends them (Panel.tick_clock: the frame count follows stock's panel tick at the unit's
         rate, a held key's repeats from stock's key task, 24 ticks after the press, then every 8): in the routes popup
         NO tapped or held 0.25 s mutes, NO held 0.7 s deletes at 0.6 s (still up), FUNC + NO held clears every route,
         DOWN held steps with its repeats, a push-and-turn held past the first repeat keeps it up; closed, FUNC + a
         0.7 s push resets the parameter (no popup).
pernote   (2026-11-20, scripts/emu_pernote.py) PER NOTE in the routes popup's header on a control read only at the
          note's start (TB-303 ACC SLID, DRUM's TYPE, ONESHOT's SAMP), never on a live one (CUT)
plainpush the routes popup's PLAIN push (2026-11-19, the User): it opens on the push's release only when nothing else
         happened while the knob was held; stock keeps push + NO (reset), push + turn (big steps), trig + push (the
         lock cleared), a key held before the push (LIVE REC's NO + push), YES or another key during the hold: none opens
         it. FUNC + push is stock's (no popup; FUNC + long push still resets); a long plain push opens at its release.
         Where: SYN 1, FLTR, TRIG 2/2 PTIM open; TRIG 1/2's FILL (a trig record at slot 25) never; a MIDI track's
         FUNC + push turns CHAN on / off (stock's), no popup. Each "no popup" case sits between plain pushes that open
         it (the controls).
popsort  the routes popup's rows sorted at the open (routes on LFO3, ENV1, MW: those three first, then the rest, each
         in the usual order); the lit row edits and deletes its own source; MW's row edits stock's entry (2026-11-21:
         scripts/emu_setuprows.py for the rest); the rows kept while up, sorted anew at the next open. Screenshots popsort_*.png beside the json.
popjump  FUNC + UP / DOWN in the routes popup (2026-11-19): the lit row to the previous / next section (a run of rows of
         one kind as shown: LFOs, envelopes, MOD SETUP's), on five route layouts (sorted and not), each jump from every
         place against the model; the ends stay; plain UP / DOWN one row; no UP / DOWN item reaches stock while up;
         FUNC + NO and FUNC + push while up as before; FUNC + DOWN held jumps on with its repeats. env2jump: the same on
         a popup opened on ENV2's page (ENV1 routed into ENV2 DEC, first).
popglass the routes popup's redraws (2026-11-18, the User: "mod matrix popup => cpu warning"): routes on LFO1 (stock's
         route 1), ENV1 (negative: its bar reaches left over the row's words) and PB (MOD SETUP's list +246); the voice
         live, MW and the playing step moved by hand. After every update (open, scroll, edit, mute, delete, the moving
         bars and LOCKS' step) the glass, modelled from every group sent, is BACK, and a full redraw forced then draws
         exactly that frame; the moving bars took the alone path (mxp_parts). Then the cost: the UI's draw, panel_diff
         and the popup's and moving lines' polls, instructions a second, the popup up with MW moving every frame,
         against the same with the popup closed (popcost; this part also runs on a build before the change).
cost     the evaluator call with no route anywhere and with every track's 23 routes set: the same instructions (the
         User's constant cost) within the clamp's branches, and the matrix's own share (mx_eval) under its bound.

Last line PASS or FAIL.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import pathlib
import re
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import emu_modulation as MO                                         # noqa: E402 -- its machine and frame recipe

TAG, ENV_TAG = 0x0010, 0x0011           # WT_MX_ROUTES, WT_MX_ENV (csrc/wishes/wish.h)
LFO_TAG = 0x0013                        # (2026-11-19) WT_MX_LFO: LFO1-3 {DEP as saved, the first route's depth}
# (2026-11-19) our popups turn by the record's size (csrc/knobs/knob.h): a record of KN_POP_SLOW counts or less moves 1
# unit every KN_POP_DIV counts, a bigger one 1 unit a count. The popup turns here send records of MID counts, 1 unit a
# count, so a depth is still 0x100 x the counts taken (the slow band is scripts/emu_knobnotch.py's)
_KH = (pathlib.Path(__file__).resolve().parent.parent / "csrc/knobs/knob.h").read_text()
MID = int(re.search(r"#define KN_POP_SLOW\s+(\d+)", _KH).group(1)) + 1
# (2026-11-20) a plain push's own knob turned under this many counts while held is a wobble: held back, the popup opens
_WM = re.search(r"#define KN_PUSH_WOBBLE\s+(\d+)", _KH)
WOBBLE = int(_WM.group(1)) if _WM else 4               # (a build before 2026-11-20 has none: the checks then fail on it)
ATT_FULL = 0x7FFE                       # (2026-11-19) DEP, the LFO's attenuverter, at 100 % (+63 and above)
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


def lfo_word(m, sym, v, l):
    """(2026-11-19) voice V's LFO L's source as the record's routes read it: its output x DEP, negated, written by
    lfo_fast at stock's DEP read into our word beside its state (matrix.c mx_kof: LFO_OUT(v) + 40 l - 84 + mx_kof)"""
    from dnfw.waverider import pages
    lv = pages.lfo4_moved()
    return (lv["LFO_LIVE"] + 4 + lv["LFO_STRIDE"] * v + 40 * l - 84 + m.long(sym["mx_kof"])) & 0xFFFFFFFF


def set_out(m, sym, v, l, out):
    """voice V's LFO L's output OUT as mx_eval alone reads it (no lfo_fast): its state and, DEP at 100 %, our word"""
    from dnfw.waverider import pages
    lv = pages.lfo4_moved()
    m.write(lv["LFO_LIVE"] + 4 + lv["LFO_STRIDE"] * v + 40 * l, struct.pack(">i", out))
    m.write(lfo_word(m, sym, v, l), struct.pack(">i", -out if out != -(1 << 31) else (1 << 31) - 1))


def first_routes(m, sym, depths, call=None):
    """(2026-11-19, DEP the attenuverter: csrc/matrix/atten.c) each LFO's first route's own depth on track T, from
    DEPTHS {t: (LFO1, LFO2, LFO3)}: a UI pass converts the kit's sounds (their DEP the attenuverter), then the record's
    WT_MX_LFO holds the depths and the sound's DEPs are 100 %; the caller sets the rows' DEP cells (set_lfo) and runs
    the UI pass again"""
    (call or m.call)(sym["mx_poll"])
    for t, ds in depths.items():
        put_field(m, sym, t, LFO_TAG, b"".join(struct.pack(">HH", ATT_FULL, d) for d in ds), call)
        for l in range(3):
            MO.w16(m, sound(m, t) + 20 + 2 * (8 + 8 * l), ATT_FULL)
    m.flush()


def put_field(m, sym, t, tag, val, call=None):
    """CALL: how wish_put runs: m.call (the default) leaves the CPU's registers as the call left them, which is right
    only while no UI runs on this machine; with the UI running, MO.guest (its registers and PC/SR kept)"""
    buf = m.alloc(max(len(val), 4))
    m.write(buf, val)
    m.flush()
    return (call or m.call)(sym["wish_put"], sound(m, t), tag, buf, len(val)) & 0xFFFFFFFF


def put_routes(m, sym, t, rs, call=None):
    return put_field(m, sym, t, TAG, b"".join(struct.pack(">BBH", src, slot, dep) for src, slot, dep in rs), call)


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
                set_lfo(m, v, k, wave, mult, 0, NONE if label == "stock" else ATT_FULL)   # (ours: DEP 100 %)
            if label == "stock":
                set_lfo(m, v, lfo, wave, mult, slot, dep)
            else:
                r = put_routes(m, sym, v, [(lfo - 1, slot, dep)])
                check(f"ours: row {v}'s route put in its sound's record", r == 0, f"{r:#x}")
        m.flush()
        if label == "ours":                     # (2026-11-19) stock's side: no UI pass, every first route stock's
            m.call(sym["mx_poll"])              # route 1, DEP its depth (MX_PASS)
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
                set_lfo(m, v, k, (v + k) % 7, 3 + k, slot if label == "stock" else 0, deps[k] if label == "stock" else ATT_FULL)
            if label == "ours":
                put_routes(m, sym, v, [(2, slot, d3), (1, slot, d2), (0, slot, d1)])
        m.flush()
        if label == "ours":
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
                set_lfo(m, v, k, k, 4, 0, ATT_FULL)
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
                set_lfo(m, v, k, 0, 4, 0, ATT_FULL)
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


def scenario_env1lfo(a, report, sym):
    """2026-11-18 (scratch/env2-mod.md): a route of the record from LFO1 into the AMP envelope's DEC (slot 83) is heard
    by the amp (the row the DSP is sent) and now by ENV1 too: mx_eval steps the envelopes after the LFO routes. The
    frame's mx_eval (the ColdFire's unrolled routes) on voice v1: LFO1's output held at full scale, DEC 40 in the row,
    the route at full depth (DEC -> 127); ENV1 routed into slot 60 shows its level. Every frame must be the clone's
    model with DEC 127; without the route, DEC 40 (the arithmetic otherwise unchanged)"""
    sys.path.insert(0, str(HERE.parent / "test"))
    import test_matrix_c as T
    from dnfw.waverider import pages
    lv = pages.lfo4_moved()
    knobs, events, frames = T.CASES["ADSR, held then released"]
    frames = min(frames, 200)
    rep = {}
    for label, routes in (("no route", []), ("LFO1 -> DEC", [(0, 83, TOP)])):
        m = setup(a.build, a.snapshot)
        v1, slot, base = 5, 60, 0x2000
        for v in range(16):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
        put_routes(m, sym, v1, routes + [(3, slot, TOP)])
        m.flush()
        m.call(sym["mx_poll"])
        lfo1 = lv["LFO_LIVE"] + 4 + lv["LFO_STRIDE"] * v1                # LFO1's output after its fade (state + 84)
        w40 = m.alloc(4)
        got, dec = [], []
        for f in range(frames):
            ev = events.get(f)
            if ev == "on":
                m.call(sym["hold_len"], v1, v1, 100)
            if ev == "off":
                m.write(w40, bytes(4))
                m.flush()
                m.call(sym["hold_final"], 1 << v1, w40)
            for s_, kn in zip((81, 82, 83, 84, 85, 91, 92), knobs):     # the row as the smoother writes it, every frame
                MO.w16(m, MO.OUT + 2 * MO.idx(v1, s_), kn << 8)
            MO.w16(m, MO.OUT + 2 * MO.idx(v1, slot), base)
            set_out(m, sym, v1, 0, 0x7FFFFFFF)
            m.flush()
            m.call(sym["mx_eval"], MO.OUT, limit=4_000_000)
            got.append(MO.u16(m, MO.OUT + 2 * MO.idx(v1, slot)))
            dec.append(MO.u16(m, MO.OUT + 2 * MO.idx(v1, 83)))
        heard = 127 if routes else knobs[2]
        want_knobs = tuple(heard if i == 2 else k for i, k in enumerate(knobs))
        d1 = (TOP - NONE) * 2
        want = [max(0, min(TOP, base + ((d1 * x) >> 31))) for x in T.model(want_knobs, events, frames)]
        bad = [f for f in range(frames) if got[f] != want[f]]
        check(f"env1lfo {label}: the amp is sent DEC {heard}", all(d >> 8 == heard for d in dec), f"{sorted(set(dec))[:4]}")
        check(f"env1lfo {label}: ENV1 every frame as the clone's model with DEC {heard}", not bad,
              f"{len(bad)} frames differ, first {[(f, got[f], want[f]) for f in bad[:3]]}" if bad else f"{frames} frames")
        rep[label] = {"frames": frames, "differ": len(bad), "dec": sorted(set(dec))}
    report["env1lfo"] = rep


def scenario_para(a, report, sym):
    """ANALOG 2's PARA as one voice (csrc/para/one.c pv_final, called by HOLD's frame hook hold_final as the frame
    calls it; 2026-11-17: the one-slot-a-note rule, para_final, went with PARA one-voice): a PARA chord is one slot,
    its leader; the leader's note-off is kept back (amp +36 and filter +40) while a joined note of its chord holds,
    and goes when none does (here a sequenced joined note, ended by its own gate timer); PARA turned off mid-chord
    lets it go at once; PARA off, and another machine, as stock (the note-off goes out in its own frame).
    DNFW_MATRIX_NEG=pvhold (the negative control): pv_final patched to return its note-offs untouched, as a build
    whose one-voice hold is broken: the chord checks must fail on it"""
    import os
    m = setup(a.build, a.snapshot)
    kit = m.long(MO.KIT)
    owner = 0x80005308
    stop_all, period_at = 0x4058E550, 0x402A132C           # (csrc/para/one.c STOP_ALL, PERIOD)
    held_, used, sound_, timed = 0x02, 0x01, 0x04, 0x08    # one.h PV_HELD, PV_USED, PV_SOUND, PV_TIMED
    entry, places = 16, 10
    chord_size = 8 + places * entry

    def track(t, typ, para):
        snd = kit + 52 + 1163 * t
        m.write(snd + 0xDE, bytes([typ]))
        m.write(snd + 20 + 2 * 37, struct.pack(">H", para << 8))

    track(0, 51, 3)                                     # ANALOG 2, PARA 4
    track(1, 51, 0)                                     # ANALOG 2, PARA OFF
    track(2, 52, 3)                                     # DRONE, the record set (not PARA: another machine)
    own = {0: 15, 1: 0, 2: 0, 3: 0, 4: 15, 5: 1, 6: 1, 7: 2, 8: 2}
    for v in range(16):
        m.write(owner + 4 * v, struct.pack(">I", own.get(v, 15)))
    track(15, 0, 0)
    m.write(stop_all, struct.pack(">I", 0))
    m.write(sym["pv_ch"], bytes(16 * chord_size))
    m.write(sym["pv_cur"], bytes(16))
    m.write(sym["pv_kept"], struct.pack(">I", 0))
    neg = os.environ.get("DNFW_MATRIX_NEG", "") == "pvhold"
    if neg:                                             # move.l 4(%sp),%d0; rts
        m.write(sym["pv_final"], bytes.fromhex("202f00044e75"))
    w40 = m.alloc(4)
    m.flush()
    period = m.long(period_at)

    def chord(s, t, joined_len):
        """slot S the leader of a chord on track T: its own note held, a sequenced joined note held, its gate timer
        JOINED_LEN (born long ago: counted from the next frame)"""
        c = bytearray(chord_size)
        c[0], c[1] = 1, t
        struct.pack_into(">BBBBiII", c, 8, 60, used | held_ | sound_, 0, 0, 0, 0, 0)
        struct.pack_into(">BBBBiII", c, 8 + entry, 64, used | held_ | sound_ | timed, 0, 0, joined_len, 1, 0xFFFF0000)
        m.write(sym["pv_ch"] + chord_size * s, bytes(c))
        m.write(sym["pv_cur"] + t, bytes([s + 1]))
        m.flush()

    def on(*vs):
        for v in vs:
            m.call(sym["hold_len"], v, own[v], 100)

    def off(bits):
        m.write(w40, struct.pack(">I", bits))
        m.flush()
        got = m.call(sym["hold_final"], bits, w40) & 0xFFFF
        return got, struct.unpack(">I", m.read(w40, 4))[0] & 0xFFFF

    kept = lambda: m.long(sym["pv_kept"]) & 0xFFFF                     # noqa: E731
    b = lambda *vs: sum(1 << v for v in vs)                             # noqa: E731
    chord(1, 0, 3 * period)                             # the joined note ends at the third frame
    on(1, 5, 6, 7, 8)
    r1 = off(b(1, 5, 7))                                # one note of each track ends
    check("para: PARA OFF's 5 and DRONE's 7 go at once", r1[0] & b(5, 7) == b(5, 7) and r1[1] & b(5, 7) == b(5, 7),
          f"{r1}")
    check("para: the PARA chord's leader (slot 1): its note-off kept back (+36 and +40) while its joined note holds",
          r1 == (b(5, 7), b(5, 7)) and kept() == b(1), f"{r1} kept {kept():#x}")
    r2 = off(0)
    check("para: a frame with no note-off sends none while the chord holds", r2 == (0, 0) and kept() == b(1),
          f"{r2} kept {kept():#x}")
    r3 = off(b(6, 8))
    check("para: the joined note's gate timer ends: the chord's note-off goes with it; 6 and 8 as stock",
          r3 == (b(1, 6, 8), b(1, 6, 8)) and kept() == 0, f"{r3} kept {kept():#x}")
    r4 = off(0)
    check("para: nothing goes twice, nothing waits after", r4 == (0, 0) and kept() == 0, f"{r4} kept {kept():#x}")
    chord(1, 0, 1000 * period)                          # a chord held long, then PARA turned off
    on(1)
    r5 = off(b(1))
    track(0, 22, 0)
    m.flush()
    r6 = off(0)
    check("para: PARA turned off mid-chord: the kept note-off goes at the next frame",
          r5 == (0, 0) and r6 == (b(1), b(1)) and kept() == 0, f"{r5} then {r6} kept {kept():#x}")
    report["para"] = {"r": [r1, r2, r3, r4, r5, r6], "negative": neg, "period": period}


def popup_rig(a, sym, what):
    """the routes popup's bench (csrc/matrix/routes_pop.c): the machine on its UI, track 1 WaveTone, its FLTR page up and
    FREQ's knob found; -> a namespace of the helpers both popup scenarios use, or None (the failure checked)"""
    import types
    from emulib.panel import ENCODER_PUSH, NO, Panel
    from unicorn import UC_HOOK_CODE
    m = setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/matrix").with_suffix("")) + "_png")
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check(f"{what}: track 1 is WaveTone", MO.set_machine(m, panel, 0, 1) == 1)
    cells = []

    def on_cell(uc, ad, sz, us):
        sp = m.uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
        cv, x0, y0, rid = struct.unpack(">4I", m.read(sp + 4, 16))
        cells.append((x0, y0, rid))
    h = m.uc.hook_add(UC_HOOK_CODE, on_cell, begin=sym["mv_cell"], end=sym["mv_cell"])
    m.flush()                                           # (a code hook sees only blocks translated after it: emulib.machine.flush)
    panel.tap((0, 2))                                   # FLTR
    panel.settle(20_000_000)
    m.uc.hook_del(h)
    freq = [(x, y, rid) for x, y, rid in cells if MO.record(m, rid)[1] == 67]
    check(f"{what}: FREQ (slot 67) is on the FLTR page", bool(freq), str(sorted(set(cells))[:8]))
    if not freq:
        return None
    x, y, rid = freq[-1]
    k = (x - 24 + 13) // 26 + (4 if y < 13 else 0)
    snd = m.long(MO.KIT) + 52
    FUNC = (2, 0)
    buf = m.alloc(128)
    # no route into FREQ to start from (the snapshot's sound may hold some: an LFO's DEST, MOD SETUP's): the rows are
    # sorted at each open (used first), and the walks count from the usual order
    for dest in (MO.record(m, r_)[1] for r_ in (78, 88, 98)):          # LFO1-3 DEST
        if struct.unpack(">H", m.read(snd + 20 + 2 * dest, 2))[0] >> 8 == 67:
            m.write(snd + 20 + 2 * dest, struct.pack(">H", 0))
    mod = bytes(m.read(snd + 230, 96))                  # MOD SETUP: six lists of four {s16 depth, s16 slot}
    m.write(snd + 230, b"".join(b_ if struct.unpack(">hh", b_)[1] != 67 else b"\0\0\0\0"
                                for b_ in (mod[i:i + 4] for i in range(0, 96, 4))))
    m.flush()
    r = types.SimpleNamespace(m=m, panel=panel, k=k, rid=rid, snd=snd)
    r.param = lambda slot: struct.unpack(">H", m.read(snd + 20 + 2 * slot, 2))[0]
    r.visible = lambda: MO.guest(m, sym["mxp_visible"]) & 0xFFFFFFFF   # guest: the running UI's registers kept
    r.detents = lambda: struct.unpack(">i", m.read(sym["mxp_detents"], 4))[0]

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

    def plain_push(frames=100):
        """(2026-11-19, the User) K pushed alone, held FRAMES frames, let go: the popup opens at the release"""
        panel.hold(ENCODER_PUSH[k], 2_000_000)
        m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + frames) & 0xFFFFFFFF))
        m.flush()
        panel.settle(3_000_000)
        panel.let_go(ENCODER_PUSH[k], 5_000_000)
        return frames

    def turn(delta, times):
        """TIMES detents of DELTA on K, as the popup receives them: -> the detents it took (the panel task sums the
        encoder's counts over its timer ticks: each call here sends MID counts (1 unit a count), settled apart)"""
        d0 = r.detents()
        for _ in range(8 * times):                      # until the popup has taken TIMES detents (the panel task
            if abs(r.detents() - d0) >= times:          # takes a turn's first counts from rest, as stock's knob step
                break                                   # does; docs/display-path.md)
            m.pc = panel.panelin.encoder(m.m, panel.profile, k, MID * delta)
            panel.settle(4_000_000)
        panel.settle(10_000_000)
        return r.detents() - d0

    def to_zero(get):
        """the lit row's depth turned back to 0x4000, a count at a time (a record can carry several detents)"""
        for _ in range(80):
            cur = get()
            if cur == 0x4000:
                break
            m.pc = panel.panelin.encoder(m.m, panel.profile, k, -1 if cur > 0x4000 else 1)
            panel.settle(4_000_000)
        return get()

    def record():
        n = MO.guest(m, sym["wish_get"], snd, TAG, buf, 128) & 0xFFFFFFFF
        return bytes(m.read(buf, n)) if n < 128 else b""

    def long_no(frames=1000):
        """NO held FRAMES frames (0.6 s = 900: the lit row's route deleted), let go"""
        panel.hold(NO, 2_000_000)
        m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + frames) & 0xFFFFFFFF))
        m.flush()
        panel.settle(15_000_000)                        # the UI pass (wr_poll) sees NO held that long
        panel.let_go(NO, 5_000_000)

    def func_no():
        """FUNC + NO: every route of ours into the parameter deleted"""
        panel.hold(FUNC, 2_000_000)
        panel.tap(NO)
        panel.let_go(FUNC, 5_000_000)

    def quiet():
        """the word a key left on screen (1 s) gone: the frame count moved past it, the 6 s idle close far off"""
        m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + 1600) & 0xFFFFFFFF))
        m.flush()
        panel.settle(20_000_000)

    r.quiet = quiet
    r.close = lambda: panel.tap(ENCODER_PUSH[k])        # the popup's own knob pushed, no turn: closed, kept
    r.func_push, r.turn, r.to_zero, r.record, r.long_no, r.func_no = func_push, turn, to_zero, record, long_no, func_no
    r.open = plain_push
    r.routes = lambda: [record()[i:i + 4] for i in range(0, len(record()), 4)]
    return r


def env2_rig(a, sym, what, routes=(), rid=64):
    """ENV2's page bench: the machine on its UI, track 1 WaveTone, no LFO DEST, the record's routes ROUTES
    ((src, slot, depth)...), [AMP] twice: ENV2's page, its DEC's knob found; -> a namespace (m, panel, snd, k, open:
    FUNC + a short push on DEC, -> 1 when the popup is up), or None (the failure checked)"""
    import types
    from emulib.panel import ENCODER_PUSH, Panel
    from unicorn import UC_HOOK_CODE
    m = setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/matrix").with_suffix("")) + "_png")
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check(f"{what}: track 1 is WaveTone", MO.set_machine(m, panel, 0, 1) == 1)
    snd = m.long(MO.KIT) + 52
    for dest in (MO.record(m, r_)[1] for r_ in (78, 88, 98)):          # no LFO DEST (a free DEST takes a first route)
        m.write(snd + 20 + 2 * dest, struct.pack(">H", 0))
    put_routes(m, sym, 0, list(routes), lambda fn, *args: MO.guest(m, fn, *args))
    m.flush()
    cells = []

    def on_cell(uc, ad, sz, us):                        # the cells drawn while ENV2's page is up
        if struct.unpack(">I", bytes(uc.mem_read(sym["amp_sub"], 4)))[0] != 1:
            return
        sp = m.uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
        cv, x0, y0, rid = struct.unpack(">4I", m.read(sp + 4, 16))
        cells.append((x0, y0, rid))
    h = m.uc.hook_add(UC_HOOK_CODE, on_cell, begin=sym["mv_cell"], end=sym["mv_cell"])
    m.flush()                                           # (a code hook sees only blocks translated after it: emulib.machine.flush)
    panel.tap((0, 3))                                   # [AMP]: ENV1/AMP
    panel.settle(30_000_000)
    panel.tap((0, 3))                                   # [AMP]: ENV2
    for _ in range(6):
        panel.settle(30_000_000)
        if any(r_ == rid for _x, _y, r_ in cells):
            break
    m.uc.hook_del(h)
    check(f"{what}: ENV2's page up", m.long(sym["amp_sub"]) == 1, f"amp_sub {m.long(sym['amp_sub'])}")
    dec = [(x, y) for x, y, r_ in cells if r_ == rid]
    check(f"{what}: ENV2's knob {rid} drawn", bool(dec), str(sorted(set(cells))))
    if not dec:
        return None
    x, y = dec[-1]
    k = (x - 24 + 13) // 26 + (4 if y < 13 else 0)
    FUNC = (2, 0)

    def open_():                                        # (2026-11-19) a plain push, let go: opened at the release
        panel.hold(ENCODER_PUSH[k], 2_000_000)
        m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + 100) & 0xFFFFFFFF))
        m.flush()
        panel.settle(3_000_000)
        panel.let_go(ENCODER_PUSH[k], 5_000_000)
        return MO.guest(m, sym["mxp_visible"]) & 0xFFFFFFFF
    return types.SimpleNamespace(m=m, panel=panel, snd=snd, k=k, open=open_)


def scenario_env2more(a, report, sym):
    """2026-11-20 (the User: ENV2's MODE, RSET and H routable, 0xE5..0xE7): on ENV2's page a plain push on MODE (record
    73), RSET (74) and H (83, drawn as LFO1's DEP) opens the routes popup on ENV2's own knob, and a turn makes LFO1's
    route into 0xE5, 0xE6, 0xE7 (a route of the record; LFO1's DEST untouched)"""
    out = {}
    for rid, slot, name in ((73, 0xE5, "MODE"), (74, 0xE6, "RSET"), (83, 0xE7, "H")):
        rig = env2_rig(a, sym, f"env2more {name}", rid=rid)
        if rig is None:
            continue
        m, panel, snd, k = rig.m, rig.panel, rig.snd, rig.k
        detents = lambda: struct.unpack(">i", m.read(sym["mxp_detents"], 4))[0]      # noqa: E731
        buf = m.alloc(128)
        up = rig.open()
        check(f"env2more: a plain push on ENV2's {name} opens the popup on it", up == 1 and m.long(sym["mxp_rid"]) == rid,
              f"up {up} why {m.long(sym['mxp_why'])} rid {m.long(sym['mxp_rid'])}")
        if not up:
            continue
        d0 = detents()
        for _ in range(32):
            if abs(detents() - d0) >= 4:
                break
            m.pc = panel.panelin.encoder(m.m, panel.profile, k, MID)
            panel.settle(4_000_000)
        panel.settle(10_000_000)
        n = MO.guest(m, sym["wish_get"], snd, TAG, buf, 128) & 0xFFFFFFFF
        b = bytes(m.read(buf, n)) if n < 128 else b""
        rs = [tuple(struct.unpack(">BBH", b[i:i + 4])) for i in range(0, len(b), 4)]
        dest1 = struct.unpack(">H", m.read(snd + 20 + 2 * MO.record(m, 78)[1], 2))[0]
        check(f"env2more: a turn makes LFO1's route into ENV2's {name} ({slot:#x}), a route of the record; LFO1's DEST "
              "untouched", any(src == 0 and sl == slot and dep > 0x4000 for src, sl, dep in rs) and dest1 == 0,
              f"{rs} DEST {dest1:#x}")
        out[name] = rs
    report["env2more"] = out


def scenario_env2pop(a, report, sym):
    """2026-11-18 (the User: ENV2's ATK HOLD DEC SUS REL as destinations, from the routes popup on ENV2's knobs):
    WaveTone, [AMP] twice: ENV2's page. FUNC + a short push on ENV2's DEC opens the popup on ENV2 DEC (slot 0xE2, never
    stock's DEC 83); a turn makes LFO1's route there, a route of the record (never the first route: LFO1's DEST
    untouched); FUNC + DOWN / UP jump the lit row by sections there too (2026-11-19); the ENV2 row refuses (ENV2 into
    itself); the frame then hears it in ENV2's knob row only (the amp's DEC cell untouched)"""
    from emulib.panel import DOWN, ENCODER_PUSH, UP
    rig = env2_rig(a, sym, "env2pop")
    if rig is None:
        return
    m, panel, snd, k = rig.m, rig.panel, rig.snd, rig.k
    FUNC = (2, 0)
    detents = lambda: struct.unpack(">i", m.read(sym["mxp_detents"], 4))[0]          # noqa: E731
    buf = m.alloc(128)

    def routes():
        n = MO.guest(m, sym["wish_get"], snd, TAG, buf, 128) & 0xFFFFFFFF
        b = bytes(m.read(buf, n)) if n < 128 else b""
        return [tuple(struct.unpack(">BBH", b[i:i + 4])) for i in range(0, len(b), 4)]

    def turn(delta, times):
        d0 = detents()
        for _ in range(8 * times):
            if abs(detents() - d0) >= times:
                break
            m.pc = panel.panelin.encoder(m.m, panel.profile, k, MID * delta)
            panel.settle(4_000_000)
        panel.settle(10_000_000)
    up = rig.open()
    check("env2pop: a plain push on ENV2's DEC opens the popup", up == 1 and m.long(sym["mxp_rid"]) == 64,
          f"up {up} why {m.long(sym['mxp_why'])} rid {m.long(sym['mxp_rid'])}")
    if not up:
        return
    turn(1, 4)
    rs = routes()
    dest1 = struct.unpack(">H", m.read(snd + 20 + 2 * MO.record(m, 78)[1], 2))[0]
    check("env2pop: a turn makes LFO1's route into ENV2's DEC (0xE2), a route of the record; LFO1's DEST untouched",
          any(src == 0 and slot == 0xE2 and dep > 0x4000 for src, slot, dep in rs) and dest1 == 0, f"{rs} DEST {dest1:#x}")
    seq = []                                            # opened with no route: the usual order, LFO1 lit
    for key in (DOWN, DOWN, DOWN, UP, UP, UP):
        func_key(m, panel, key)
        seq.append(m.long(sym["mxp_lit"]) if "mxp_lit" in sym else None)
    check("env2pop: FUNC + DOWN / UP jump by sections on ENV2's page too (LFO1 -> ENV1 -> VEL, stays; ENV1, LFO1, "
          "stays)", seq == [3, 5, 5, 3, 0, 0], f"lit places {seq} (want [3, 5, 5, 3, 0, 0])")
    for _ in range(4):                                  # the lit row down to ENV2 (LFO1 is used: first; then LFO2, LFO3,
        panel.tap(DOWN)                                 # ENV1, ENV2)
        panel.settle(5_000_000)
    before = routes()
    turn(1, 2)
    check("env2pop: the ENV2 row refuses (ENV2 into its own knobs)", routes() == before, f"{before} -> {routes()}")
    panel.tap(ENCODER_PUSH[k])                          # closed, kept
    panel.settle(10_000_000)
    lv = __import__("dnfw.waverider.pages", fromlist=["x"]).lfo4_moved()
    m.call(sym["mx_poll"])
    for v in range(16):
        m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, 0) if v == 0 else sound(m, v)))
    MO.w16(m, MO.OUT + 2 * MO.idx(0, 83), 40 << 8)
    set_out(m, sym, 0, 0, 0x7FFFFFFF)                                               # voice 1's LFO1 at full scale
    m.flush()
    m.call(sym["mx_eval"], MO.OUT, limit=4_000_000)
    hs, ss = m.alloc(4), m.alloc(4)
    m.call(sym["mx_e2_knob"], 0, 2, hs, ss)
    heard, setv = struct.unpack(">i", m.read(hs, 4))[0], struct.unpack(">i", m.read(ss, 4))[0]
    amp = MO.u16(m, MO.OUT + 2 * MO.idx(0, 83))
    check("env2pop: the frame hears it in ENV2's knob row only", heard > setv and amp == 40 << 8,
          f"ENV2 DEC heard {heard:#x} set {setv:#x}, the amp's DEC {amp:#x}")
    report["env2pop"] = {"routes": rs, "heard": heard, "set": setv}


def scenario_popup(a, report, sym):
    """the routes popup through the panel (csrc/matrix/routes_pop.c): WaveTone's FLTR page, FUNC + a short push on
    FREQ's knob opens it; turning makes LFO1's route (stock's route 1: its DEST and DEP), push-and-turn moves to LFO2
    (its own route 1) and to ENV1 (a route of the record); the knob pushed closes, kept; a route turned back to 0 goes
    at once (its row empty) and stays freed after a reopen; NO mutes the lit route, YES unmutes it; a long NO deletes
    the lit route (an empty row: nothing), FUNC + NO every route into FREQ; FUNC + push while up does nothing; FUNC +
    a long push with the popup closed resets FREQ to its record's default. The rows are sorted at each open (the used
    ones first: scenario popsort); the walks below follow that order"""
    from emulib.panel import DOWN, NO, UP, YES
    from unicorn import UC_HOOK_CODE
    rig = popup_rig(a, sym, "popup")
    if rig is None:
        return
    m, panel, k, rid, snd = rig.m, rig.panel, rig.k, rig.rid, rig.snd
    param, visible, detents, func_push, turn, record, routes = (rig.param, rig.visible, rig.detents, rig.func_push,
                                                                rig.turn, rig.record, rig.routes)
    crash = {}

    def on_halt(uc, ad, sz, us):                        # stock's fault dump ends at this halt: the stack, for the cause
        if not crash:
            sp = uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
            words = struct.unpack(">96I", bytes(uc.mem_read(sp, 384)))
            crash["sp"] = sp
            crash["ours"] = [(i, hex(w)) for i, w in enumerate(words) if 0x46A40000 <= w < 0x46AF0000][:12]
            crash["words"] = [hex(w) for w in words[:40]]
    m.uc.hook_add(UC_HOOK_CODE, on_halt, begin=0x4011EDEC, end=0x4011EDEC)
    m.flush()                                           # (a code hook sees only blocks translated after it: emulib.machine.flush)

    def counters():
        return {n: m.long(sym[n]) for n in ("mxp_pushes", "mxp_opens", "mxp_refusals", "mxp_why", "mxp_rid", "mxp_turns", "mxp_keys")}

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
    check("popup: FUNC + a short push is stock's again (2026-11-19, the User): no popup", visible() == 0,
          f"visible {visible()}; {counters()}")
    held = rig.open(300)
    panel.settle(20_000_000)
    print(f"    screens composed: {f0} before the push, {panel.frames()} after it", flush=True)
    check("popup: a plain short push opens it", visible() == 1, f"push held {held} frames; {counters()}")
    if visible() != 1:
        return
    panel.screen("popup_open")
    from emu import panel as EP
    frame = bytes(panel.capture.frames[-1]) if panel.capture.frames else b""
    lit = EP.lit(frame) if frame else set()
    cell = lambda s: (30 + 4 * s, 63 - 5) in lit                                     # noqa: E731 (canvas y 5)
    check("popup: LOCKS shows FREQ's locks on steps 1 and 4, not on step 2", lockrec is not None and cell(0)
          and cell(3) and not cell(1), f"record {lockrec}, steps 1-4 filled: {[cell(s) for s in range(4)]}")
    fbuf = m.alloc(12)

    def first(lfo):
        """(2026-11-19) LFO's first route's own depth: the record's WT_MX_LFO (DEP is the attenuverter, atten.c)"""
        n = MO.guest(m, sym["wish_get"], snd, LFO_TAG, fbuf, 12) & 0xFFFFFFFF
        return struct.unpack(">H", m.read(fbuf + 4 * lfo + 2, 2))[0] if n == 12 else param(8 + 8 * lfo)

    def depth_of(lfo, dest_slot, dep_slot):
        """-> (where, depth): the LFO's route into FREQ, its first route (stock's DEST, 'stock') or the record's"""
        if param(dest_slot) >> 8 == 67:
            return "stock", first(lfo)
        for r in routes():
            if r[0] == lfo and r[1] == 67:
                return "record", r[2] << 8 | r[3]
        return None, 0x4000

    mod = snd + 230                                     # MOD SETUP (stock's; 2026-11-21 edited here too, setup.c,
                                                        # emu_setuprows.py): VEL into FREQ, AT twice
    mod0 = bytes(m.read(mod, 96))
    want = struct.pack(">hh", 0x2000, 67) + mod0[4:64] + struct.pack(">hhhh", -0x400, 67, 0x600, 67) + mod0[72:]
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
    at_now = [struct.unpack(">hh", m.read(mod + 64 + 4 * p_, 4)) for p_ in range(4)]
    check("popup: MOD SETUP's rows show VEL's and AT's routes into FREQ (AT's two summed); (2026-11-21) a turn on AT's "
          "row merges its two into one, turned, our record untouched",
          vel[0] == 0x2000 and vel[1] & 1 and at[0] == 0x200 and at[1] & 9 == 9 and turned > 0
          and at_now[:2] == [(0x200 + 0x100 * turned, 67), (0, 0)] and record() == rec0,
          f"VEL {vel}, AT {at}, turned {turned}, AT now {at_now}")
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
    rig.close()
    check("popup: the knob pushed closes it, the routes kept", visible() == 0 and depth_of(0, 4, 8)[1] == d1
          and depth_of(1, 12, 16)[1] == d2, f"visible {visible()}, {depth_of(0, 4, 8)}, {depth_of(1, 12, 16)}")
    # the unit's case (2026-11-17): a row turned back to 0 still drew its value, tick and count until the close
    rig.open(300)                                      # sorted: LFO1 LFO2 ENV1 ...; LFO1 lit
    panel.settle(20_000_000)
    used0 = m.long(sym["mxp_rows_drawn"])
    d0 = detents()
    rig.to_zero(lambda: depth_of(0, 4, 8)[1])
    back = detents() - d0
    panel.settle(20_000_000)
    drawn = m.long(sym["mxp_rows_drawn"])
    panel.screen("popup_zero")
    check("popup: LFO1 turned back to 0: its route gone at once, its row drawn empty while up",
          visible() == 1 and depth_of(0, 4, 8)[0] is None and used0 & 1 and not drawn & 1 and drawn & 2,
          f"{back} detents back; LFO1 {depth_of(0, 4, 8)}, rows drawn {used0:#x} -> {drawn:#x}")
    rig.close()
    rig.open(300)                                      # reopened: LFO2 ENV1 first, LFO1 among the unused
    order = list(m.read(sym["mxp_order"], 11))
    check("popup: closed and reopened, LFO1's route is freed (not in the pool, not sorted as used)",
          depth_of(0, 4, 8)[0] is None and order[:3] == [1, 3, 0] and depth_of(1, 12, 16)[1] == d2,
          f"order {order}, LFO1 {depth_of(0, 4, 8)}")
    # mute (the User, 2026-11-17: NO mutes, YES unmutes): LFO2 lit (its stock route 1), then ENV1 (the record's)
    where2 = depth_of(1, 12, 16)[0]
    panel.tap(NO)
    mark = [r for r in routes() if r[0] == 0xC1]
    mrec = [r for r in routes() if r[1] == 67 and r[0] == 0x81]
    panel.settle(20_000_000)
    panel.screen("popup_muted")
    # 2026-11-18 (the User: our matrix the only source, DEST and DEP the first route's copy; csrc/matrix/routes.c):
    # LFO2's first route muted keeps DEST and DEP, the record gets its mark (0xC1), the frame hears DEST none; a route
    # of the record (the snapshot's LFO2 DEST in use elsewhere) gets its mute bit in place
    muted = (param(12) >> 8 == 67 and first(1) == d2 and len(mark) == 1) if where2 == "stock" else \
        (len(mrec) == 1 and (mrec[0][2] << 8 | mrec[0][3]) == d2 and not mark)
    check("popup: NO mutes the lit route (LFO2's: the first route's mark, DEST and DEP kept; or the record's mute bit), "
          "still drawn", muted and visible() == 1 and m.long(sym["mxp_rows_drawn"]) & 2,
          f"{where2} -> {record().hex()}, LFO2 DEST {param(12):#06x}")
    panel.tap(YES)
    check("popup: YES unmutes it (the mark gone, DEST and DEP as they were)",
          depth_of(1, 12, 16) == (where2, d2) and not any(r[0] & 0x80 for r in routes()) and visible() == 1,
          f"{depth_of(1, 12, 16)}, {record().hex()}")
    panel.tap(DOWN)                                     # ENV1
    e1 = [r for r in routes() if r[0] == 3 and r[1] == 67]
    panel.tap(NO)
    check("popup: NO on ENV1 sets its mute bit in place, the depth kept",
          bytes([0x83]) + e1[0][1:] in routes() if e1 else False, record().hex())
    rig.close()
    rig.open(300)                                      # a muted route sorts as unused: LFO2, then LFO1 LFO3 ENV1 ...
    order = list(m.read(sym["mxp_order"], 11))
    check("popup: a muted route sorts as unused", order[:5] == [1, 0, 2, 3, 4], f"order {order}")
    for _ in range(3):
        panel.tap(DOWN)                                 # ENV1 (place 3)
    panel.tap(YES)
    check("popup: YES on ENV1 unmutes it", e1 and e1[0] in routes(), record().hex())
    rig.close()
    # deleting (the User, 2026-11-17): a long NO the lit row's, FUNC + NO every route into FREQ. The state set
    # directly: LFO1's stock route 1 into FREQ (DEST 67, DEP 0x4800) with a DEP p-lock on step 2, LFO2's and ENV1's
    # routes in the record
    m.write(snd + 20 + 2 * 4, struct.pack(">H", 67 << 8))
    m.write(snd + 20 + 2 * 8, struct.pack(">H", 0x4800))
    m.write(snd + 20 + 2 * 12, struct.pack(">H", 0))
    rb = m.alloc(16)
    m.write(rb, bytes([1, 67, 0x44, 0x00, 3, 67, 0x3C, 0x00]))
    m.flush()
    MO.guest(m, sym["wish_put"], snd, TAG, rb, 8)
    deplock = None
    if tbl:                                             # a p-lock of LFO1's DEP (slot 8) on step 2
        heads = [m.read(tbl + 258 * i, 1)[0] for i in range(80)]
        deplock = heads.index(0xFF) if 0xFF in heads else None
    if deplock is not None:
        vals = [0xFFFF] * 128
        vals[1] = 0x6000
        m.write(tbl + 258 * deplock, bytes([8, 0]) + b"".join(struct.pack(">H", v) for v in vals))
        m.flush()
    e0 = m.long(sym["mxp_erased"])
    rig.open(300)                                      # LFO1 lit (sorted: LFO1 LFO2 ENV1 LFO3 ...)
    rig.long_no()
    freed = bytes(m.read(tbl + 258 * deplock, 258)) if deplock is not None else b""
    check("popup: a long NO deletes the lit row's route (LFO1's first route: DEST off; its DEP lock kept: DEP is the "
          "attenuverter, 2026-11-19), still up",
          visible() == 1 and m.long(sym["mxp_erased"]) == e0 + 1 and param(4) >> 8 != 67
          and depth_of(1, 12, 16)[0] == "record" and freed[:2] == bytes([8, 0]),
          f"erased {m.long(sym['mxp_erased']) - e0}, LFO1 DEST {param(4):#06x}, lock record {freed[:4].hex()}")
    panel.screen("popup_deleted")
    for _ in range(3):                                  # DOWN three times: LFO3, no route here
        panel.tap(DOWN)
    rig.long_no()
    check("popup: a long NO on an empty row does nothing", m.long(sym["mxp_erased"]) == e0 + 1
          and depth_of(1, 12, 16)[0] == "record" and visible() == 1, f"erased {m.long(sym['mxp_erased']) - e0}")
    rig.func_no()
    panel.screen("popup_all_cleared")
    check("popup: FUNC + NO deletes every route into FREQ (LFO2's, ENV1's), still up",
          m.long(sym["mxp_erased"]) == e0 + 3 and depth_of(1, 12, 16)[0] is None and visible() == 1
          and not any(r[1] == 67 for r in routes()), f"erased {m.long(sym['mxp_erased']) - e0}, {record().hex()}")
    # YES on an empty row (2026-11-18, the User: as the LFO DEST popup): a route at +32, LFO3's route 1 (made free
    # first: route 1 first, as a turn from 0 places it); YES again on it changes nothing; the knob then sets it; a long
    # NO takes it away again
    d3, p3 = MO.record(m, 98)[1], MO.record(m, 103)[1]
    m.write(snd + 20 + 2 * d3, struct.pack(">H", 0))                  # LFO3 DEST off: its route 1 free
    m.flush()
    rig.quiet()                                                       # ALL CLEARED gone (a word lasts a second)
    panel.tap(YES)
    added = depth_of(2, d3, p3)
    panel.screen("popup_added")
    back = bytes(m.read(m.long(0x402A10CC), 1024))                    # the frame YES left (a word would be up a second)
    box = sum(back[8 * x + (y >> 3)] >> (7 - (y & 7)) & 1 for x in range(28, 100) for y in range(24, 39))
    panel.tap(YES)
    again = depth_of(2, d3, p3)
    check("popup: YES on an empty row (LFO3) adds its route at +32 (its free route 1), YES again nothing more",
          added == ("stock", 0x4000 + 32 * 0x100) and again == added and visible() == 1, f"{added}, then {again}")
    check("popup: ... its row drawn with the route, no word box over the rows (the User: no ADDED box)",
          m.long(sym["mxp_rows_drawn"]) >> 2 & 1 == 1 and box < 72 * 15 // 2, f"rows drawn {m.long(sym['mxp_rows_drawn']):#x}, "
          f"{box} of {72 * 15} box pixels lit")
    rig.quiet()
    got = rig.turn(1, 1)
    check(f"popup: ... the knob then sets it ({got} detents: +{32 + got})", got > 0
          and depth_of(2, d3, p3) == ("stock", 0x4000 + (32 + got) * 0x100),
          str(depth_of(2, d3, p3)))
    rig.long_no()
    check("popup: ... and a long NO deletes it", depth_of(2, d3, p3)[0] is None, str(depth_of(2, d3, p3)))
    # FUNC + push begun while up: ignored (no close, no reset; the unit's bounced push, 2026-11-17)
    m.write(snd + 20 + 2 * 67, struct.pack(">H", 0x1234))
    m.flush()
    func_push(1000)
    func_push(300)
    check("popup: FUNC + push (long or short) while up does nothing: still up, FREQ not reset",
          visible() == 1 and param(67) == 0x1234, f"visible {visible()}, FREQ {param(67):#06x}")
    rig.close()
    held = func_push(1000)
    want = MO.record(m, rid)[4]
    check("popup: FUNC + a long push (popup closed) resets FREQ to its default", param(67) == want and visible() == 0,
          f"FREQ {param(67):#06x}, default {want:#06x}, held {held} frames (0.6 s = 900)")
    rec = record()
    report["popup"] = {"knob": k, "rid": rid, "record": rec.hex()}


def scenario_plainpush(a, report, sym):
    """(2026-11-19, the User) the routes popup opens on a PLAIN push's release, only when nothing else happened while
    the knob was held; FUNC + push is stock's again. Keys held in panel ticks (Panel.tick_clock: stock's repeats come).
    Every "no popup" case is checked between plain pushes that open it (the controls: the rig opens it there)."""
    from emulib.panel import ENCODER_PUSH, NO, YES
    rig = popup_rig(a, sym, "plainpush")
    if rig is None:
        return
    m, panel, k, rid, snd = rig.m, rig.panel, rig.k, rig.rid, rig.snd
    param, vis = rig.param, rig.visible
    panel.tick_clock(MO.FRAMES)
    FUNC, TRIG1, SRC, TRIGK = (2, 0), (3, 0), (0, 1), (0, 0)
    push = ENCODER_PUSH[k]
    rep = {}
    default = MO.record(m, rid)[4]

    def shut():
        if vis():
            panel.press_for(push_now[0], 4)             # the same knob pushed and let go: closed, kept
            panel.release_for(push_now[0], 20)
        panel.skip_frames(1600)
        panel.run_ticks(10)
    push_now = [push]

    def plain(ticks=8, p=None):
        """a plain push held TICKS ticks -> (up while held, up after the release)"""
        p = p or push
        push_now[0] = p
        panel.press_for(p, ticks)
        during = vis()
        panel.release_for(p, 30)
        return during, vis()

    def control(what):
        d, u = plain()
        check(f"plainpush: control before {what}: a plain push opens it at its release", (d, u) == (0, 1),
              f"while held {d}, after {u}, why {m.long(sym['mxp_why'])}")
        shut()

    def set_freq(v):
        m.write(snd + 20 + 2 * 67, struct.pack(">H", v))
        m.flush()

    def turn(knob, n):
        for _ in range(n):
            m.pc = panel.panelin.encoder(m.m, panel.profile, knob, 4)
            panel.run_ticks(4)

    # 1. the release, not the press
    d, u = plain(8)
    check("plainpush: a short plain push: nothing on the press, the popup at the release", (d, u) == (0, 1),
          f"while held {d}, after {u}, why {m.long(sym['mxp_why'])}, rid {m.long(sym['mxp_rid'])}")
    shut()
    d, u = plain(242)
    check("plainpush: a 2 s plain push: nothing while held, the popup at the release", (d, u) == (0, 1),
          f"while held {d}, after {u}")
    shut()
    rep["opens"] = True
    # 2. push + NO: stock's reset (on NO's release, the knob held), no popup
    control("push + NO")
    set_freq(0x1234)
    panel.press_for(push, 10)
    panel.press_for(NO, 3)
    panel.release_for(NO, 10)
    panel.release_for(push, 30)
    check("plainpush: push + NO: stock's reset (FREQ to its default), no popup", param(67) == default and vis() == 0,
          f"FREQ {param(67):#06x} (default {default:#06x}), up {vis()}")
    rep["push_no"] = param(67)
    shut()
    # 3. push + turn: stock's big steps, no popup
    control("push + turn")
    set_freq(0x0800)
    v0 = param(67)
    panel.press_for(push, 30)                           # (stock 1.12 drops a turn ~45 ms after the push: ab81db68)
    turn(k, 2)
    panel.release_for(push, 30)
    v1 = param(67)
    up_turn = vis()
    panel.run_ticks(30)
    turn(k, 2)
    panel.run_ticks(30)
    v2 = param(67)
    check("plainpush: push + turn: stock's big steps (more than the same plain detents), no popup",
          up_turn == 0 and vis() == 0 and v2 > v1 and (v1 - v0) > 2 * (v2 - v1),
          f"pushed: {v0:#06x} -> {v1:#06x}; plain: -> {v2:#06x}; up {up_turn}/{vis()}")
    rep["push_turn"] = [v0, v1, v2]
    shut()
    # 3b. (2026-11-20, the User: "if the knob moves (even by one) while pressed, it doesn't work") the pushed knob
    # wobbling: counts summed under WOBBLE either way (single counts, one record, back and forth) are held back: FREQ
    # exactly as before the press, the popup at the release. At WOBBLE counts they all go on to stock at once (its push
    # + turn), no popup: [1] * WOBBLE moves FREQ exactly as one record of WOBBLE counts does
    wob = sym.get("mxp_wobbles")
    passed = panel.watch_items(sym["kn_item"])          # the knob items that went on (after mxp_seen), as stock gets them
    m.flush()

    def wobble(counts):
        set_freq(0x1234)
        w0 = m.long(wob) if wob else 0
        n0 = len(passed)
        panel.press_for(push, 12)                       # (stock 1.12 drops a turn ~45 ms after the push: ab81db68)
        for c in counts:
            m.pc = panel.panelin.encoder(m.m, panel.profile, k, c)
            panel.run_ticks(4)
        panel.run_ticks(8)
        held = param(67)
        panel.release_for(push, 30)
        went = [struct.unpack(">b", bytes([f >> 24]))[0] for t, ty, c, f in passed[n0:] if ty == 1 and c == k + 1]
        return held, param(67), vis(), (m.long(wob) - w0) if wob else None, went

    small = ([1], [-1], [1] * (WOBBLE - 1), [-1] * (WOBBLE - 1), [WOBBLE - 1], [1 - WOBBLE], [2, -2, 1, -1],
             [WOBBLE - 1, 1 - WOBBLE, WOBBLE - 1])
    for counts in small:
        held, after, up, n, went = wobble(counts)
        check(f"plainpush: pushed, its knob turned {counts} counts (under {WOBBLE}): FREQ untouched, no count reaches "
              f"stock, the popup at the release", held == 0x1234 and after == 0x1234 and up == 1
              and n == len(counts) and not went,
              f"FREQ while held {held:#06x}, after {after:#06x}, up {up}, items held back {n}, went on {went}")
        shut()
    # at WOBBLE counts: the crossing item carries every count held back (one item, the sum), no popup. Whether stock
    # then moves FREQ is stock's own (its first turn after a pause only shows the value): reported, not checked
    moved = {}
    for counts in ([1] * WOBBLE, [WOBBLE], [-1] * WOBBLE, [-WOBBLE], [WOBBLE + 4], [2, 2, 3]):
        held, after, up, n, went = wobble(counts)
        moved[str(counts)] = after
        first = next(i for i in range(len(counts)) if abs(sum(counts[:i + 1])) >= WOBBLE)
        check(f"plainpush: pushed, its knob turned {counts} counts (at least {WOBBLE}): every count goes on to stock "
              f"(push + turn), no popup", up == 0 and n == first and sum(went) == sum(counts)
              and went[0] == sum(counts[:first + 1]),
              f"went on {went}, items held back {n}, up {up}, FREQ {after:#06x}")
        shut()
    rep["wobble"] = moved
    # 4. a key held before the push (LIVE REC's NO + push): no popup, nothing changed
    control("NO held first")
    set_freq(0x1234)
    panel.press_for(NO, 10)
    panel.press_for(push, 8)
    panel.release_for(push, 20)
    panel.release_for(NO, 30)
    check("plainpush: NO held, then the push (LIVE REC's gesture): no popup, FREQ unchanged (stock: nothing)",
          vis() == 0 and param(67) == 0x1234, f"up {vis()}, FREQ {param(67):#06x}")
    shut()
    # 5. YES, FUNC during the hold; another knob turned during the hold
    for name, key in (("YES", YES), ("FUNC", FUNC)):
        control(f"{name} during the hold")
        set_freq(0x1234)
        panel.press_for(push, 8)
        panel.press_for(key, 3)
        panel.release_for(key, 5)
        panel.release_for(push, 30)
        check(f"plainpush: {name} pressed while the knob is held: no popup, FREQ unchanged", vis() == 0
              and param(67) == 0x1234, f"up {vis()}, FREQ {param(67):#06x}")
        shut()
    control("another knob turned")
    panel.press_for(push, 30)
    turn((k + 1) % 8, 1)
    panel.release_for(push, 30)
    check("plainpush: another knob turned while the knob is held: no popup", vis() == 0, f"up {vis()}")
    shut()
    # 6. a trig held + push: no popup (stock clears that trig's lock of FREQ: GRID RECORDING; read, not checked)
    control("trig held + push")
    tbl = MO.guest(m, sym["sl_ui_table_now"]) & 0xFFFFFFFF
    lockrec = None
    if tbl:
        heads = [m.read(tbl + 258 * i, 1)[0] for i in range(80)]
        lockrec = heads.index(0xFF) if 0xFF in heads else None
    if lockrec is not None:
        vals = [0xFFFF] * 128
        vals[0] = 0x5000
        m.write(tbl + 258 * lockrec, bytes([67, 0]) + b"".join(struct.pack(">H", v) for v in vals))
        m.flush()
    panel.press_for(TRIG1, 10)
    panel.press_for(push, 8)
    panel.release_for(push, 20)
    panel.release_for(TRIG1, 30)
    lock = struct.unpack(">H", m.read(tbl + 258 * lockrec + 2, 2))[0] if lockrec is not None else None
    check("plainpush: [TRIG 1] held, then the push: no popup", vis() == 0, f"up {vis()}")
    print(f"    trig held + push: FREQ's lock on step 1 {lock if lock is None else hex(lock)} (0x5000 set; 0xffff: "
          f"cleared by stock)", flush=True)
    rep["trig_lock"] = lock
    shut()
    # 6b. (2026-11-20) a trig held + push + one count: stock's lock path as before, nothing held back (a plain push only)
    w0 = m.long(wob) if wob else 0
    panel.press_for(TRIG1, 10)
    panel.press_for(push, 12)
    m.pc = panel.panelin.encoder(m.m, panel.profile, k, 1)
    panel.run_ticks(8)
    panel.release_for(push, 20)
    panel.release_for(TRIG1, 30)
    lock2 = struct.unpack(">H", m.read(tbl + 258 * lockrec + 2, 2))[0] if lockrec is not None else None
    n = (m.long(wob) - w0) if wob else None
    check("plainpush: [TRIG 1] held, push + 1 count: the count goes to stock (nothing held back), no popup",
          vis() == 0 and n == 0, f"up {vis()}, items held back {n}, FREQ's lock on step 1 "
          f"{lock2 if lock2 is None else hex(lock2)}")
    rep["trig_lock_turn"] = lock2
    shut()
    # 7. FUNC + push: stock's (no popup); FUNC + a long push still resets
    control("FUNC + push")
    panel.press_for(FUNC, 10)
    panel.press_for(push, 8)
    panel.release_for(push, 40)
    panel.release_for(FUNC, 40)
    check("plainpush: FUNC + a short push: stock's, no popup", vis() == 0, f"up {vis()}")
    set_freq(0x1234)
    panel.press_for(FUNC, 3)
    panel.press_for(push, 85)
    panel.release_for(push, 3)
    panel.release_for(FUNC, 20)
    check("plainpush: FUNC + a push held 0.7 s: FREQ reset to its default, no popup", param(67) == default
          and vis() == 0, f"FREQ {param(67):#06x} (default {default:#06x}), up {vis()}")
    shut()
    # 8. the pages: SYN 1 (A), TRIG 1/2 (G FILL: never), TRIG 2/2 (G PTIM)
    panel.press_for(SRC, 6)
    panel.release_for(SRC, 60)
    d, u = plain(8, ENCODER_PUSH[0])
    r0 = m.long(sym["mxp_rid"])
    check("plainpush: SYN 1, A: opens", u == 1 and MO.record(m, r0)[0] < 16, f"up {u}, rid {r0}, page "
          f"{MO.record(m, r0)[0] if r0 else None}, why {m.long(sym['mxp_why'])}")
    shut()
    panel.press_for(TRIGK, 6)
    panel.release_for(TRIGK, 60)
    d, u = plain(8, ENCODER_PUSH[6])
    r1, why = m.long(sym["mxp_rid"]), m.long(sym["mxp_why"])
    page = MO.record(m, r1)[0] if r1 else None
    check("plainpush: TRIG 1/2, G (FILL, a trig record): no popup (refused: not a sound parameter)",
          u == 0 and why == 3, f"up {u}, rid {r1} page {page} slot {MO.record(m, r1)[1] if r1 else None}, why {why}")
    shut()
    panel.press_for(FUNC, 10)
    panel.press_for(ENCODER_PUSH[6], 8)
    panel.release_for(ENCODER_PUSH[6], 40)
    panel.release_for(FUNC, 40)
    check("plainpush: TRIG 1/2, FUNC + push G (FILL): no popup", vis() == 0, f"up {vis()}")
    shut()
    panel.press_for(TRIGK, 6)
    panel.release_for(TRIGK, 60)
    d, u = plain(8, ENCODER_PUSH[6])
    r2 = m.long(sym["mxp_rid"])
    check("plainpush: TRIG 2/2, G (PTIM): opens", u == 1, f"up {u}, rid {r2}, why {m.long(sym['mxp_why'])}")
    shut()
    rep["fill"] = {"rid": r1, "page": page, "why": why}
    # 8b. (2026-11-20, the User: "I could not get it to work") SYN 1 of FM TONE (its places never reach the cell widget:
    # pages.py wr_place_tail) and of ANALOG 2 (our pages draw their own knobs: moving.c mv_knob): every knob A..H
    # opens, on eight different sound records. Until then all eight found no parameter (why 1)
    for ty, name in ((51, "ANALOG 2"), (0, "FM TONE")):
        got = MO.set_machine(m, panel, 0, ty)
        panel.run_ticks(60)
        panel.press_for((0, 2), 6)                      # FLTR first: SRC then opens SYN 1, whatever page was up
        panel.release_for((0, 2), 60)
        panel.press_for(SRC, 6)
        panel.release_for(SRC, 60)
        rids, ups = [], []
        for kk in range(8):
            d, u = plain(8, ENCODER_PUSH[kk])
            rids.append(m.long(sym["mxp_rid"]))
            ups.append(u)
            shut()
        pages_ok = all(r and MO.record(m, r)[0] < 16 for r in rids)
        check(f"plainpush: {name} (type {got}) SYN 1: every knob opens, eight sound records", got == ty and all(ups)
              and len(set(rids)) == 8 and pages_ok, f"up {ups}, rids {rids}, why {m.long(sym['mxp_why'])}")
        rep[f"syn1_{ty}"] = rids
        # each knob's record is the one that knob turns: a push + turn of 8 counts moves that record's slot
        bad = []
        for kk, rid_k in enumerate(rids):
            if not rid_k:
                continue                                # (checked above: every knob opens)
            slot = MO.record(m, rid_k)[1]
            ch = []
            for tries in range(4):                      # (stock's first turn after a pause may only show the value; a
                before = bytes(m.read(snd + 20, 202))   # choice at its end moves only one way)
                up_dir = (-16 if struct.unpack(">H", before[2 * slot:2 * slot + 2])[0] >= 0x4000 else 16) * (
                    -1 if tries >= 2 else 1)
                panel.press_for(ENCODER_PUSH[kk], 12)
                m.pc = panel.panelin.encoder(m.m, panel.profile, kk, up_dir)
                panel.run_ticks(8)
                panel.release_for(ENCODER_PUSH[kk], 20)
                shut()
                after = bytes(m.read(snd + 20, 202))
                ch = [i // 2 for i in range(0, 202, 2) if before[i:i + 2] != after[i:i + 2]]
                if ch:
                    break
            if slot not in ch:
                bad.append((kk, rid_k, slot, ch))
        check(f"plainpush: {name} SYN 1: each knob's record is the slot that knob turns", not bad, str(bad))
    # 9. a MIDI track: FUNC + push on CHAN is stock's on / off; a plain push opens nothing
    got = MO.set_machine(m, panel, 0, 4)
    panel.run_ticks(60)
    panel.press_for(TRIGK, 6)
    panel.release_for(TRIGK, 40)
    panel.press_for(SRC, 6)
    panel.release_for(SRC, 60)
    back = lambda: bytes(m.read(m.long(0x402A10CC), 1024))                             # noqa: E731 (the glass)
    g0 = back()
    panel.press_for(FUNC, 10)
    panel.press_for(ENCODER_PUSH[0], 8)
    panel.release_for(ENCODER_PUSH[0], 40)
    panel.release_for(FUNC, 40)
    panel.run_ticks(120)
    g1 = back()
    diff = sum(1 for i in range(1024) if g0[i] != g1[i])
    panel.screen("plainpush_midi_chan")
    # (the knob-push survey, stock 1.12: the X box becomes a value at the push's release and stays; the sound's bytes
    # do not change, the on / off is kept elsewhere; main took the push: the screen went back as it was)
    check("plainpush: MIDI track (type 4), SYN 1 A (CHAN): FUNC + push is stock's on / off (the X box becomes a value "
          "and stays), no popup", got == 4 and diff > 0 and vis() == 0, f"type {got}, glass bytes changed {diff}, "
          f"up {vis()}")
    d, u = plain(8, ENCODER_PUSH[0])
    check("plainpush: MIDI track: a plain push opens nothing", u == 0, f"up {u}, why {m.long(sym['mxp_why'])}")
    rep["midi"] = diff
    report["plainpush"] = rep


def repeats_of(items, code, since):
    """-> the ticks of CODE's repeat items (bit 3 with bit 0) seen from item SINCE on"""
    from emulib.panel import F_REPEAT
    return [t for t, kind, c, f in items[since:] if kind == 0 and c == code and f & F_REPEAT and f & 1]


def scenario_hold(a, report, sym):
    """held keys as the unit sends them (2026-11-18, the User: "holding NO also only mutes"). Stock's key task sends a
    held key's repeats (the first 24 panel ticks after the press, then one every 8: bit 3 beside the press's bit 0);
    the frame count follows the panel tick at the unit's rate (Panel.tick_clock), every key held a number of ticks.
    In the routes popup, LFO1's route into FREQ lit (stock's DEST and DEP) with LFO2's and ENV1's of the record:
    NO tapped mutes; NO held 0.25 s (past the first repeat, short of 0.6 s) mutes; NO held 0.7 s deletes the lit route
    at 0.6 s, still up, nothing more on its release; FUNC + NO held clears every route into FREQ, still up; the knob
    pushed and turned (the lit row moved), held past the first repeat, let go: still up. The popup closed: FUNC + the
    knob pushed 0.7 s resets FREQ to its default, no popup (2026-11-19: opened by a plain push; FUNC + push is stock's). An arrow held steps the lit row with its repeats (stock's
    lists' way). v1 took every repeat for a new press: NO's hold, the push's turn and FUNC + push's hold began again
    every 8 ticks"""
    from emulib.panel import DOWN, ENCODER_PUSH, NO, YES
    rig = popup_rig(a, sym, "hold")
    if rig is None:
        return
    m, panel, k, rid, snd = rig.m, rig.panel, rig.k, rig.rid, rig.snd
    param, visible, routes = rig.param, rig.visible, rig.routes
    FUNC, K_NO, K_DOWN = (2, 0), 12, 14
    panel.tick_clock(MO.FRAMES)
    first, every = panel.repeat_timing()
    items = panel.watch_items(sym["mxp_pop"])
    erased = lambda: m.long(sym["mxp_erased"])                                         # noqa: E731
    muted = lambda: any(r_[0] & 0x80 for r_ in routes())                               # noqa: E731
    into_freq = lambda: param(4) >> 8 == 67 or any(r_[1] == 67 for r_ in routes())    # noqa: E731
    m.write(snd + 20 + 2 * 4, struct.pack(">H", 67 << 8))     # LFO1: DEST FREQ, DEP +8 (stock's route 1)
    m.write(snd + 20 + 2 * 8, struct.pack(">H", 0x4800))
    rb = m.alloc(16)
    m.write(rb, bytes([1, 67, 0x44, 0x00, 3, 67, 0x3C, 0x00]))  # LFO2 +4, ENV1 -4 (the record)
    m.flush()
    MO.guest(m, sym["wish_put"], snd, TAG, rb, 8)

    def func_push(ticks):
        panel.press_for(FUNC, 3)
        panel.press_for(ENCODER_PUSH[k], ticks)
        panel.release_for(ENCODER_PUSH[k], 3)
        panel.release_for(FUNC, 20)

    def word_gone():
        panel.skip_frames(1600)                         # MUTED / DELETED's second on screen
        panel.run_ticks(10)

    func_push(10)
    check("hold: FUNC + a short push (stock's again) opens nothing", visible() == 0, f"visible {visible()}")
    panel.press_for(ENCODER_PUSH[k], 10)                # a plain short push: opened at its release
    panel.release_for(ENCODER_PUSH[k], 20)
    order = list(m.read(sym["mxp_order"], 11))
    check("hold: a plain short push opens the popup, LFO1 lit (sorted first)", visible() == 1 and order[0] == 0,
          f"visible {visible()}, order {order}, repeat timing {first}/{every} ticks")
    if visible() != 1:
        return
    e0 = erased()
    panel.press_for(NO, 3)
    panel.release_for(NO, 20)
    check("hold: NO tapped mutes the lit route", muted() and erased() == e0 and visible() == 1,
          f"{rig.record().hex()}, erased {erased() - e0}")
    panel.press_for(YES, 3)
    panel.release_for(YES, 20)
    word_gone()
    check("hold: YES unmutes it", not muted(), rig.record().hex())
    n0 = len(items)
    panel.press_for(NO, 30)
    panel.release_for(NO, 20)
    reps = repeats_of(items, K_NO, n0)
    check("hold: NO held 0.25 s (its repeats came, short of 0.6 s) mutes, deletes nothing", reps and muted()
          and erased() == e0 and visible() == 1, f"repeats {len(reps)}, erased {erased() - e0}, {rig.record().hex()}")
    panel.press_for(YES, 3)
    panel.release_for(YES, 20)
    word_gone()
    n0 = len(items)
    pressed = panel.ticks()
    panel.press_for(NO, 85)
    held = (erased(), visible())
    panel.release_for(NO, 20)
    reps = repeats_of(items, K_NO, n0)
    steps = [b - a_ for a_, b in zip(reps, reps[1:])]
    check("hold: NO held 0.7 s, its repeats coming every 8 ticks: the lit route deleted at 0.6 s, still up",
          len(reps) >= 5 and held == (e0 + 1, 1) and param(4) >> 8 != 67, f"repeats at {[t - pressed for t in reps]}, "
          f"erased {held[0] - e0} while held, LFO1 DEST {param(4):#06x}")
    check("hold: ... let go: nothing more (no mute, still up)", erased() == e0 + 1 and not muted() and visible() == 1,
          f"erased {erased() - e0}, {rig.record().hex()}")
    report["hold"] = {"repeat_first": first, "repeat_every": every,
                      "no_repeats": [t - pressed for t in reps], "repeat_steps": steps}
    word_gone()
    panel.press_for(FUNC, 3)
    panel.press_for(NO, 85)
    panel.release_for(NO, 3)
    panel.release_for(FUNC, 20)
    check("hold: FUNC + NO held: every route into FREQ deleted (LFO2's, ENV1's), still up",
          erased() == e0 + 3 and not into_freq() and visible() == 1,
          f"erased {erased() - e0}, {rig.record().hex()}, LFO1 DEST {param(4):#06x}")
    word_gone()
    n0 = len(items)
    panel.press_for(DOWN, 60)                            # DOWN held 0.5 s: the lit row steps with the repeats
    panel.release_for(DOWN, 10)
    downs = repeats_of(items, K_DOWN, n0)
    check("hold: DOWN held: its repeats reach the popup (the lit row steps with them, as stock's lists)",
          len(downs) >= 3 and visible() == 1, f"repeats {len(downs)}")
    panel.press_for(ENCODER_PUSH[k], 5)                  # pushed and turned: the lit row moves
    m.pc = panel.panelin.encoder(m.m, panel.profile, k, 4)
    panel.run_ticks(40)                                  # held past the first repeat
    panel.release_for(ENCODER_PUSH[k], 20)
    check("hold: the knob pushed and turned, held past its first repeat, let go: still up", visible() == 1,
          f"visible {visible()}")
    rig.close()
    panel.run_ticks(10)
    m.write(snd + 20 + 2 * 67, struct.pack(">H", 0x1234))
    m.flush()
    func_push(85)
    want = MO.record(m, rid)[4]
    check("hold: popup closed, FUNC + the knob pushed 0.7 s: FREQ reset to its default, no popup",
          param(67) == want and visible() == 0, f"FREQ {param(67):#06x}, default {want:#06x}, visible {visible()}")
    if visible():
        rig.close()


def scenario_popsort(a, report, sym):
    """the routes popup's rows sorted (the User, 2026-11-17: "the used modulation are on top of the list (ordered the
    same way)", MOD SETUP's rows too): routes into FREQ on LFO3 (its stock route 1), ENV1 (the record's) and MW (MOD
    SETUP's list at +262: 2026-11-21, measured on stock's MOD WHEEL page; until then read as PB) -> the rows LFO3 ENV1
    MW, then LFO1 LFO2 ENV2 VEL PB AT BC KEY. Turning the lit row changes that row's source only; (2026-11-21) MW's row
    edits stock's entry (a turn, NO mutes, YES unmutes, the row kept); a depth turned to 0 or a route deleted moves no
    row while the popup is up (ENV1 turned to 0 goes at once, its row empty); the next open sorts anew"""
    from emulib.panel import DOWN, NO, UP, YES
    rig = popup_rig(a, sym, "popsort")
    if rig is None:
        return
    m, panel, snd, param = rig.m, rig.panel, rig.snd, rig.param
    dest3, dep3 = MO.record(m, 98)[1], MO.record(m, 103)[1]          # LFO3 DEST and DEP (stock's records)
    dests = [MO.record(m, r)[1] for r in (78, 88, 98)]
    mod = snd + 230                                     # MOD SETUP: six lists of four {s16 depth, s16 slot}, MW the third
    mod0 = bytes(m.read(mod, 96))
    clean = b"".join(b if struct.unpack(">hh", b)[1] != 67 else b"\0\0\0\0" for b in
                     (mod0[i:i + 4] for i in range(0, 96, 4)))      # no other MOD SETUP route into FREQ
    want_mod = clean[:32] + struct.pack(">hh", 0x0F00, 67) + clean[36:]
    m.write(mod, want_mod)
    for d in dests:                                     # no LFO's route 1 into FREQ but LFO3's
        if param(d) >> 8 == 67:
            m.write(snd + 20 + 2 * d, struct.pack(">H", 0))
    m.write(snd + 20 + 2 * dest3, struct.pack(">H", 67 << 8))
    fb = m.alloc(16)                                    # (2026-11-19) LFO3's first route's depth: the record's
    MO.guest(m, sym["mx_poll"])                         # (the sound converted: DEP the attenuverter)
    n = MO.guest(m, sym["wish_get"], snd, LFO_TAG, fb, 12) & 0xFFFFFFFF
    f = bytearray(m.read(fb, 12)) if n == 12 else bytearray(struct.pack(">6H", *([ATT_FULL, NONE] * 3)))
    f[10:12] = struct.pack(">H", 0x4800)
    m.write(fb, bytes(f))
    m.flush()
    MO.guest(m, sym["wish_put"], snd, LFO_TAG, fb, 12)

    def first3():
        k = MO.guest(m, sym["wish_get"], snd, LFO_TAG, fb, 12) & 0xFFFFFFFF
        return struct.unpack(">H", m.read(fb + 10, 2))[0] if k == 12 else param(dep3)
    rb = m.alloc(16)
    m.write(rb, bytes([3, 67, 0x3C, 0x00]))             # ENV1 into FREQ, -4
    m.flush()
    MO.guest(m, sym["wish_put"], snd, TAG, rb, 4)
    env1 = lambda: next(((r[2] << 8 | r[3]) for r in rig.routes() if r[0] == 3 and r[1] == 67), None)  # noqa: E731
    order = lambda: list(m.read(sym["mxp_order"], 11)) if "mxp_order" in sym else None                  # noqa: E731
    others = lambda: (param(dests[0]), param(dests[1]), [r for r in rig.routes() if r[1] == 67 and r[0] != 3],  # noqa: E731
                      bytes(m.read(mod, 96)))
    rig.open(300)
    check("popsort: a plain short push opens it", rig.visible() == 1)
    if rig.visible() != 1:
        return
    panel.screen("popsort_open")
    if "mxp_order" not in sym:                          # a build without the sorting (the screenshots before it)
        for _ in range(3):                              # ENV1 (unsorted: LFO1 LFO2 LFO3 ENV1): to 0, the unit's case
            panel.tap(DOWN)
        rig.to_zero(env1)
        panel.settle(20_000_000)
        panel.screen("popsort_zero")
        for _ in range(4):                              # PB
            panel.tap(DOWN)
        panel.screen("popsort_setup")
        check("popsort: the build sorts the popup's rows (mxp_order)", False, "no mxp_order: unsorted build")
        panel.tap(NO)
        return
    want = [2, 3, 6, 0, 1, 4, 5, 7, 8, 9, 10]           # LFO3 ENV1 MW | LFO1 LFO2 ENV2 VEL PB AT BC KEY
    o1 = order()
    check("popsort: the used rows first (LFO3 ENV1 MW), then the others, each in the usual order", o1 == want,
          f"{o1} (want {want})")
    base = others()
    got = rig.turn(+1, 2)                               # place 0 lit: LFO3
    check(f"popsort: the first row turned {got}: LFO3's route 1 only", got > 0 and first3() == 0x4800 + 0x100 * got
          and param(dest3) == 67 << 8 and env1() == 0x3C00 and others() == base,
          f"LFO3 DEP {first3():#06x}, ENV1 {env1()}, LFO1/2 DEST {param(dests[0]):#06x}/{param(dests[1]):#06x}")
    d3 = first3()
    panel.tap(DOWN)                                     # place 1: ENV1
    got = rig.turn(-1, 2)
    check(f"popsort: the second row turned {got}: ENV1's route only", got < 0 and env1() == 0x3C00 + 0x100 * got
          and first3() == d3 and others() == base, f"ENV1 {env1()}, LFO3 DEP {first3():#06x}")
    panel.tap(DOWN)                                     # place 2: MW, MOD SETUP's (2026-11-21: edited here)
    e0 = m.long(sym["mxp_erased"])
    panel.screen("popsort_setup")
    hint = (m.long(sym["mxp_setup_hint"]), struct.unpack(">i", m.read(sym["mxp_setup_dep"], 4))[0])
    before = (first3(), env1(), others()[:3])
    turned = rig.turn(+1, 1)
    mw = struct.unpack(">hh", m.read(mod + 32, 4))
    panel.tap(NO)                                       # NO mutes, YES unmutes: the entry kept, the row too
    rig.quiet()
    panel.tap(YES)
    rig.quiet()
    check("popsort: the third row is MW's: its turn edits stock's entry only, NO / YES mute and unmute it, the row kept",
          hint == (7, 0x0F00) and turned > 0 and mw == (0x0F00 + 0x100 * turned, 67)
          and struct.unpack(">hh", m.read(mod + 32, 4)) == mw and (first3(), env1(), others()[:3]) == before
          and m.long(sym["mxp_erased"]) == e0 and rig.visible() == 1 and order() == want,
          f"hint row+1 {hint[0]} depth {hint[1]:#06x} (want 7, 0x0f00), turned {turned}, MW {mw}, "
          f"erased {m.long(sym['mxp_erased']) - e0}")
    panel.tap(UP)                                       # ENV1 back to 0: gone at once, its row empty, the rows kept
    rig.to_zero(lambda: env1() or 0x4000)
    rig.quiet()
    panel.screen("popsort_zero")
    drawn = m.long(sym["mxp_rows_drawn"])
    check("popsort: ENV1 turned to 0 while up: its route gone, its row drawn empty, no row moves",
          order() == want and env1() is None and not drawn & 8 and drawn & 4, f"{order()}, ENV1 {env1()}, "
          f"rows drawn {drawn:#x}")
    panel.tap(UP)                                       # place 0: LFO3, deleted
    rig.long_no()
    panel.screen("popsort_deleted")
    check("popsort: a long NO on the first row deletes LFO3's route 1, the rows kept",
          m.long(sym["mxp_erased"]) == e0 + 1 and param(dest3) >> 8 != 67 and env1() is None
          and order() == want and rig.visible() == 1,
          f"erased {m.long(sym['mxp_erased']) - e0}, LFO3 DEST {param(dest3):#06x}, ENV1 {env1()}, {order()}")
    rig.close()
    rig.open(300)                                       # opened again: sorted anew
    o2 = order()
    panel.screen("popsort_reopen")
    hint2 = m.long(sym["mxp_setup_hint"])
    want2 = [6, 0, 1, 2, 3, 4, 5, 7, 8, 9, 10]
    check("popsort: the next open sorts anew: MW first (lit, MOD SETUP), then the rest in order",
          o2 == want2 and hint2 == 7 and env1() is None, f"{o2} (want {want2}), hint {hint2}, ENV1 {env1()}")
    rig.close()
    m.write(mod, mod0)
    m.flush()
    report["popsort"] = {"order_open": o1, "order_reopen": o2}


# --- FUNC + UP / DOWN: the lit row by sections (2026-11-19, the User) ------------------------------------------------
JUMP_FUNC = (2, 0)
MOD_LIST = (0, 2, 1, 4, 3, 5)           # row VEL MW PB AT BC KEY -> the sound's MOD SETUP list (setup.c mxs_list; 2026-11-21)


def section(r):
    """a row's section: 0 the LFOs (rows 0..2), 1 the envelopes (3, 4), 2 MOD SETUP's (5..10)"""
    return 0 if r < 3 else 1 if r < 5 else 2


def jump_model(order, lit, down):
    """the rows on screen in ORDER (place -> row), LIT the lit place: a section is a run of places whose rows are of
    one kind; FUNC + DOWN -> the next run's first place (the last run: stays), FUNC + UP -> this run's first place, or
    the previous run's when already on it (place 0: stays)"""
    kind = [section(r) for r in order]
    starts = [i for i in range(len(order)) if i == 0 or kind[i] != kind[i - 1]]
    if down:
        after = [i for i in starts if i > lit]
        return after[0] if after else lit
    before = [i for i in starts if i < lit]
    return before[-1] if before else 0


def func_key(m, panel, key):
    """FUNC held, KEY tapped, FUNC let go"""
    panel.hold(JUMP_FUNC, 2_000_000)
    panel.tap(key)
    panel.let_go(JUMP_FUNC, 5_000_000)


def watch_returns(m, entry_va):
    """every call of the routine taking (u8 *item) at ENTRY_VA: -> a list filled as the machine runs, of (type, code,
    flags, d0 it returned) (1: the item is the popup's, dropped; 0: on to stock). The return hook goes on its call
    site once a first call has shown it (arm, after that call)"""
    from unicorn import UC_HOOK_CODE, m68k_const
    seen, pend, sites = [], [], set()

    def on_entry(uc, ad, sz, us):
        sp = uc.reg_read(m68k_const.UC_M68K_REG_A7)
        ret, item = struct.unpack(">II", bytes(uc.mem_read(sp, 8)))
        it = bytes(uc.mem_read(item, 12))
        pend.append((it[0],) + struct.unpack(">II", it[4:12]))
        sites.add(ret)

    def on_ret(uc, ad, sz, us):
        if pend:
            seen.append(pend.pop() + (uc.reg_read(m68k_const.UC_M68K_REG_D0) & 0xFFFFFFFF,))

    def arm():
        for ret in sorted(sites):
            m.uc.hook_add(UC_HOOK_CODE, on_ret, begin=ret, end=ret)
        m.flush()                                       # the call site's translation made again, with the hook
        pend.clear()
        return sorted(sites)
    m.uc.hook_add(UC_HOOK_CODE, on_entry, begin=entry_va, end=entry_va)
    m.flush()
    return seen, arm


def scenario_popjump(a, report, sym):
    """FUNC + UP / FUNC + DOWN in the routes popup (2026-11-19, the User): the lit row jumps to the previous / next
    section, a section being a run of rows of one kind in the rows as shown (LFO1-3, ENV1-2, MOD SETUP's six): FUNC +
    DOWN to the next run's first row, FUNC + UP to this run's first row (the previous run's when on it); at the ends it
    stays. On FREQ, with the routes into it: none (the usual order), LFO2 + ENV1 + PB, LFO3 alone, VEL alone, ENV2 + KEY
    (each sorted at its open: used rows first). Each jump from every place against the model where the sorting splits a
    kind; plain UP / DOWN still one row; every UP / DOWN item (press, repeats, release) taken by the popup while up
    (none reaches stock), FUNC's own items on to stock as before; FUNC + NO still deletes every route, FUNC + push while
    up still ignored; FUNC + DOWN held: its repeats jump on (stock's lists' way), the last run kept"""
    from emulib.panel import DOWN, NO, UP
    rig = popup_rig(a, sym, "popjump")
    if rig is None:
        return
    m, panel, snd, param = rig.m, rig.panel, rig.snd, rig.param
    if "mxp_lit" not in sym:
        check("popjump: the build has the lit row's word (mxp_lit)", False, "no mxp_lit: a build without the jumps")
        return
    lit = lambda: m.long(sym["mxp_lit"])                                               # noqa: E731
    order = lambda: list(m.read(sym["mxp_order"], 11))                                 # noqa: E731
    seen, arm = watch_returns(m, sym["mxp_pop"])
    dests = [MO.record(m, r_)[1] for r_ in (78, 88, 98)]
    deps = [MO.record(m, r_)[1] for r_ in (83, 93, 103)]
    mod = snd + 230
    mod0 = bytes(m.read(mod, 96))                       # popup_rig left no MOD SETUP route into FREQ

    def layout(lfos=(), envs=(), mods=()):
        """the routes into FREQ: LFOS' stock route 1 (DEST, DEP +8), ENVS' of the record (+4), MODS' (rows 5..10) a
        MOD SETUP route (+15) in their list's first place"""
        for l_, d_ in enumerate(dests):
            m.write(snd + 20 + 2 * d_, struct.pack(">H", 67 << 8 if l_ in lfos else 0))
        for l_ in lfos:
            m.write(snd + 20 + 2 * deps[l_], struct.pack(">H", 0x4800))
        b = bytearray(mod0)
        for r_ in mods:
            b[16 * MOD_LIST[r_ - 5]:16 * MOD_LIST[r_ - 5] + 4] = struct.pack(">hh", 0x0F00, 67)
        m.write(mod, bytes(b))
        m.flush()
        put_routes(m, sym, 0, [(r_, 67, 0x4400) for r_ in envs], lambda fn, *args: MO.guest(m, fn, *args))

    def go(place):
        for _ in range(12):
            if lit() == place:
                break
            panel.tap(DOWN if lit() < place else UP)
        return lit()

    def walk(keys):
        out = []
        for key in keys:
            func_key(m, panel, key)
            out.append(lit())
        return out

    def opened(name, want_order):
        rig.open(300)
        o = order()
        check(f"popjump {name}: opened, the rows {want_order}", rig.visible() == 1 and o == want_order and lit() == 0,
              f"visible {rig.visible()}, order {o}, lit {lit()}")
        return rig.visible() == 1 and o == want_order

    def sweep(name, o):
        """from every place, FUNC + DOWN and FUNC + UP against the model"""
        bad = []
        for p_ in range(11):
            for key, down in ((DOWN, True), (UP, False)):
                if go(p_) != p_:
                    bad.append((p_, "go", lit()))
                    continue
                func_key(m, panel, key)
                if lit() != jump_model(o, p_, down):
                    bad.append((p_, "DOWN" if down else "UP", lit(), jump_model(o, p_, down)))
        check(f"popjump {name}: FUNC + DOWN / UP from each of the 11 places as the model", not bad and rig.visible() == 1,
              f"wrong (place, key, got, want): {bad[:6]}")

    D, U = DOWN, UP
    # 1. no route: LFO1 LFO2 LFO3 | ENV1 ENV2 | VEL MW PB AT BC KEY
    layout()
    if not opened("none", list(range(11))):
        return
    arm()                                               # the call site known: the returns from here on
    n0 = len(seen)
    got = walk((D, D, D, U, U, U))
    check("popjump none: FUNC + DOWN LFO1 -> ENV1 -> VEL, stays at the last section; FUNC + UP -> ENV1 -> LFO1, stays",
          got == [3, 5, 5, 3, 0, 0], f"lit {got}")
    panel.tap(DOWN)
    one = lit()
    func_key(m, panel, UP)
    check("popjump none: plain DOWN one row (LFO2); FUNC + UP from inside a section: its first row (LFO1)",
          (one, lit()) == (1, 0), f"DOWN -> {one}, FUNC + UP -> {lit()}")
    go(4)
    func_key(m, panel, UP)
    a4 = lit()
    go(7)
    func_key(m, panel, UP)
    a7 = lit()
    go(10)
    func_key(m, panel, DOWN)
    a10 = lit()
    func_key(m, panel, UP)
    check("popjump none: FUNC + UP from ENV2 -> ENV1, from PB -> VEL; FUNC + DOWN on KEY (the last row) stays, then "
          "FUNC + UP -> VEL", (a4, a7, a10, lit()) == (3, 5, 10, 5), f"{(a4, a7, a10, lit())} (want (3, 5, 10, 5))")
    go(3)
    panel.tap(UP)
    p_up = lit()
    panel.tap(DOWN)
    check("popjump none: plain UP / DOWN still one row (ENV1 -> LFO3 -> ENV1)", (p_up, lit()) == (2, 3),
          f"UP -> {p_up}, DOWN -> {lit()}")
    arrows = [x for x in seen[n0:] if x[0] == 0 and x[1] in (11, 14)]
    funcs = [x for x in seen[n0:] if x[0] == 0 and x[1] == 17]
    check("popjump none: every UP / DOWN item (presses and releases, FUNC held or not) taken by the popup: none on to "
          "stock; FUNC's own items on to stock as before", arrows and all(x[3] == 1 for x in arrows)
          and funcs and all(x[3] == 0 for x in funcs),
          f"{len(arrows)} arrow items, on to stock {[x for x in arrows if x[3] != 1][:4]}; FUNC items {len(funcs)}, "
          f"taken {[x for x in funcs if x[3] != 0][:4]}")
    sweep("none", list(range(11)))
    rig.close()
    # 2. LFO2, ENV1, PB used: LFO2 | ENV1 | PB | LFO1 LFO3 | ENV2 | VEL MW AT BC KEY
    want2 = [1, 3, 7, 0, 2, 4, 5, 6, 8, 9, 10]
    layout(lfos=(1,), envs=(3,), mods=(7,))
    if not opened("LFO2+ENV1+PB", want2):
        return
    got = walk((D, D, D, D, D, D))
    back = walk((U, U, U, U, U, U))
    check("popjump LFO2+ENV1+PB: FUNC + DOWN by the runs as shown (LFO2, ENV1, PB, LFO1, ENV2, VEL, stays), FUNC + UP "
          "back (ENV2, LFO1, PB, ENV1, LFO2, stays)", got == [1, 2, 3, 5, 6, 6] and back == [5, 3, 2, 1, 0, 0],
          f"down {got}, up {back}")
    sweep("LFO2+ENV1+PB", want2)
    e0 = m.long(sym["mxp_erased"])
    rig.func_push(300)
    still = rig.visible()
    func_key(m, panel, NO)
    check("popjump LFO2+ENV1+PB: after the jumps, FUNC + push while up still ignored (up), FUNC + NO still deletes "
          "every route into FREQ (LFO2's, ENV1's; 2026-11-21: PB's MOD SETUP entry too), still up",
          still == 1 and m.long(sym["mxp_erased"]) == e0 + 3
          and param(dests[1]) >> 8 != 67 and not [r_ for r_ in rig.routes() if r_[1] == 67] and rig.visible() == 1,
          f"up after FUNC + push {still}, erased {m.long(sym['mxp_erased']) - e0}, LFO2 DEST {param(dests[1]):#06x}, "
          f"{rig.record().hex()}")
    rig.quiet()
    rig.close()
    # 3. LFO3 alone: LFO3 LFO1 LFO2 (one run) | ENV1 ENV2 | VEL ...
    layout(lfos=(2,))
    if opened("LFO3", [2, 0, 1, 3, 4, 5, 6, 7, 8, 9, 10]):
        got = walk((D, D, U, U))
        check("popjump LFO3: the used LFO3 and the unused LFO1 LFO2 one section (LFO3 -> ENV1 -> VEL; ENV1, LFO3)",
              got == [3, 5, 3, 0], f"lit {got}")
        rig.close()
    # 4. VEL alone: VEL | LFO1 LFO2 LFO3 | ENV1 ENV2 | MW PB AT BC KEY
    layout(mods=(5,))
    want4 = [5, 0, 1, 2, 3, 4, 6, 7, 8, 9, 10]
    if opened("VEL", want4):
        got = walk((D, D, D, D, U, U, U, U))
        check("popjump VEL: VEL -> LFO1 -> ENV1 -> MW, stays; ENV1, LFO1, VEL, stays", got == [1, 4, 6, 6, 4, 1, 0, 0],
              f"lit {got}")
        sweep("VEL", want4)
        rig.close()
    # 5. ENV2 and KEY: ENV2 | KEY | LFO1 LFO2 LFO3 | ENV1 | VEL MW PB AT BC
    layout(envs=(4,), mods=(10,))
    if opened("ENV2+KEY", [4, 10, 0, 1, 2, 3, 5, 6, 7, 8, 9]):
        got = walk((D, D, D, D, D, U, U, U, U, U))
        check("popjump ENV2+KEY: ENV2 -> KEY -> LFO1 -> ENV1 -> VEL, stays; ENV1, LFO1, KEY, ENV2, stays",
              got == [1, 2, 5, 6, 6, 5, 2, 1, 0, 0], f"lit {got}")
        rig.close()
    # 6. FUNC + DOWN held (the unit's key task: repeats 24 ticks after the press, then every 8): jumps on with them
    layout()
    if opened("held", list(range(11))):
        panel.tick_clock(MO.FRAMES)
        items = panel.watch_items(sym["mxp_pop"])
        n0, s0 = len(items), len(seen)
        panel.press_for(JUMP_FUNC, 3)
        panel.press_for(DOWN, 45)                       # the press and two repeats or more
        mid = lit()
        panel.release_for(DOWN, 3)
        panel.release_for(JUMP_FUNC, 20)
        reps = repeats_of(items, 14, n0)
        downs = [x for x in seen[s0:] if x[0] == 0 and x[1] == 14]
        check("popjump held: FUNC + DOWN held: its repeats jump on (LFO1 -> ENV1 -> VEL), the last section kept, every "
              "item taken, still up", len(reps) >= 1 and mid == 5 and lit() == 5 and downs
              and all(x[3] == 1 for x in downs) and rig.visible() == 1,
              f"repeats {len(reps)}, lit while held {mid}, after {lit()}, on to stock "
              f"{[x for x in downs if x[3] != 1][:4]}")
        rig.close()
    m.write(mod, mod0)
    m.flush()
    report["popjump"] = {"ok": True}


def scenario_env2jump(a, report, sym):
    """FUNC + UP / DOWN on a popup opened on ENV2's page (ENV2 DEC, slot 0xE2) with ENV1 routed there: the rows ENV1 |
    LFO1 LFO2 LFO3 | ENV2 | VEL ... KEY, each jump from every place as the model"""
    from emulib.panel import DOWN, UP
    rig = env2_rig(a, sym, "env2jump", routes=[(3, 0xE2, 0x4400)])
    if rig is None:
        return
    m, panel = rig.m, rig.panel
    if "mxp_lit" not in sym:
        check("env2jump: the build has the lit row's word (mxp_lit)", False, "no mxp_lit: a build without the jumps")
        return
    lit = lambda: m.long(sym["mxp_lit"])                                               # noqa: E731
    up = rig.open()
    o = list(m.read(sym["mxp_order"], 11))
    want = [3, 0, 1, 2, 4, 5, 6, 7, 8, 9, 10]
    check("env2jump: a plain push on ENV2's DEC opens it, ENV1 (routed there) first", up == 1 and o == want
          and m.long(sym["mxp_rid"]) == 64, f"up {up}, order {o}, rid {m.long(sym['mxp_rid'])}")
    if up != 1:
        return
    got = []
    for key in (DOWN,) * 4 + (UP,) * 4:
        func_key(m, panel, key)
        got.append(lit())
    check("env2jump: ENV1 -> LFO1 -> ENV2 -> VEL, stays; ENV2, LFO1, ENV1, stays", got == [1, 4, 5, 5, 4, 1, 0, 0],
          f"lit {got}")
    bad = []
    for p_ in range(11):
        for key, down in ((DOWN, True), (UP, False)):
            for _ in range(12):
                if lit() == p_:
                    break
                panel.tap(DOWN if lit() < p_ else UP)
            func_key(m, panel, key)
            if lit() != jump_model(want, p_, down):
                bad.append((p_, "DOWN" if down else "UP", lit(), jump_model(want, p_, down)))
    check("env2jump: FUNC + DOWN / UP from each of the 11 places as the model", not bad and
          MO.guest(m, sym["mxp_visible"]) & 0xFFFFFFFF == 1, f"wrong (place, key, got, want): {bad[:6]}")
    report["env2jump"] = {"order": o}


GROUP_CONT = 0x40131F0C                 # stock's group sender past its first two instructions (emu_line_redraw.py)
PANEL_DIFF = 0x40131FD2
MW_VAL = 0x8000DE40                     # MOD SETUP list 1's source (PB, 2026-11-21; named MW before), a s16 a track
TRACK_CUR = 0x42C5B984                  # each track's playing step (routes_pop.c)
OWNER = 0x80005308


def popglass_rig(a, sym, what):
    """the popup's bench with three routes into FREQ (LFO1's route 1, ENV1 at a negative depth, MW in MOD SETUP), the
    voice live on track 1, the glass modelled from every group sent"""
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    rig = popup_rig(a, sym, what)
    if rig is None:
        return None
    m, snd = rig.m, rig.snd
    dest, dep = MO.record(m, 78)[1], MO.record(m, 83)[1]
    m.write(snd + 20 + 2 * dest, struct.pack(">H", 67 << 8))               # LFO1 DEST FREQ, DEP +24
    m.write(snd + 20 + 2 * dep, struct.pack(">H", 0x4000 + 0x1800))
    # ENV1 -28. The UI runs on this machine (popup_rig): wish_put as a guest call, the UI's registers kept. A plain
    # m.call left the UI's stack pointer on the harness's stack and its other registers as wish_put left them; where
    # the UI then went depended on where it had been stopped (the code's layout), and on some builds it ended with the
    # interrupts masked, so no key reached the popup ("the popup is up" failed, 2026-11-18, claude/cpu-cuts)
    put_routes(m, sym, 0, [(3, 67, 0x4000 - 0x1C00)], call=lambda *x: MO.guest(m, *x))
    m.write(snd + 230 + 16 * 1, struct.pack(">hh", 0x0C00, 67))           # PB +12 (list 1, its first route; its value 0x8000de40)
    m.write(sym["sl_lastv"], b"\x00")                                     # track 1 last played voice 1 ...
    m.write(OWNER, struct.pack(">I", 0))                                  # ... which plays it
    m.flush()
    rig.glass, rig.screen = bytearray(1024), None
    rig.sym = sym

    def on_screen(uc, ad, sz, us):
        rig.screen = struct.unpack(">I", m.read(uc.reg_read(K.UC_M68K_REG_A7) + 4, 4))[0]

    def on_group(uc, ad, sz, us):
        sp = uc.reg_read(K.UC_M68K_REG_A7)
        col, page, ptr = struct.unpack(">3I", m.read(sp + 20, 12))
        for k_, b in enumerate(m.read(ptr, 8)):
            rig.glass[8 * ((col & 0xFF) + k_) + (page & 7)] = b
    m.uc.hook_add(UC_HOOK_CODE, on_screen, begin=sym["wr_screen"], end=sym["wr_screen"])
    m.uc.hook_add(UC_HOOK_CODE, on_group, begin=GROUP_CONT, end=GROUP_CONT)
    m.flush()                                           # (a code hook sees only blocks translated after it: emulib.machine.flush)
    rig.back = lambda: bytes(m.read(m.long(0x402A10CC), 1024))
    rig.png_dir = str(pathlib.Path(a.json or "out/matrix/x").parent)
    rig.panel.settle(10_000_000)
    rig.glass[:] = rig.back()                                             # the glass as last presented
    return rig


MOVE_RUN = 8_000_000                    # a move's run, instructions (at least: the popup's update for it is waited for)
MOVE_CHUNK = 500_000
MOVE_BOUND = 40_000_000
IDENTITY_RUN = 20_000_000              # a forced full redraw's run (at least: until it is presented)
IDENTITY_BOUND = 80_000_000


def move(rig, step, run=MOVE_RUN):
    """MW and the playing step moved, then a poll due (the frame count past the popup's 15/s). (2026-11-20) Run in
    chunks until the popup's poll has taken this move (mxp_parts + mxp_fulls + mxp_same moved; bounded), then on to
    RUN in all; and only once a stock redraw already due is done. With a fixed 8 M run the counts depended on where
    runs ended (main: 7 M gave 2 full redraws, 8 M one; the plain-push build: 8 M two, 9 M one): stock sets the
    screen's dirty byte on its own now and then, and a move whose update met it was drawn full (traced 2026-11-20:
    the dirty byte set at a move's start, right after the previous forced redraw had ended clean). -> whether the
    update came"""
    m, sym = rig.m, rig.sym
    polled = lambda: sum(m.long(sym[n]) for n in ("mxp_parts", "mxp_fulls", "mxp_same"))   # noqa: E731
    quiet = 0                                           # a stock redraw already due: drawn first (below)
    while rig.screen and m.read(rig.screen + 32, 1) != b"\x00" and quiet < MOVE_BOUND:
        quiet += rig.panel.settle(MOVE_CHUNK) or MOVE_CHUNK
    m.write(MW_VAL, struct.pack(">h", [0, 9000, 20000, 32000, 15000, -3000][step % 6]))
    m.write(TRACK_CUR, bytes([(3 * step) % 64]))
    m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + 110) & 0xFFFFFFFF))
    m.flush()
    n0, ran = polled(), 0
    while polled() == n0 and ran < MOVE_BOUND:
        ran += rig.panel.settle(MOVE_CHUNK) or MOVE_CHUNK
    while bytes(rig.glass) != rig.back() and ran < MOVE_BOUND:       # and its groups sent: the glass is BACK again
        ran += rig.panel.settle(MOVE_CHUNK) or MOVE_CHUNK
    if ran < run:
        rig.panel.settle(run - ran)
    return polled() != n0


def identity(rig, tag, shots):
    """the glass is BACK; a full redraw forced now draws exactly it"""
    back = rig.back()
    check(f"popglass {tag}: the glass shows BACK", bytes(rig.glass) == back,
          f"{sum(x != y for x, y in zip(rig.glass, back))} bytes differ")
    if rig.screen is None:
        check(f"popglass {tag}: the screen object seen", False)
        return
    n0 = len(rig.panel.capture.frames)
    rig.m.write(rig.screen + 32, b"\x01")
    ran = 0                                             # (2026-11-20) until that redraw is done: its frame presented
    while ran < IDENTITY_BOUND and (len(rig.panel.capture.frames) == n0 or rig.m.read(rig.screen + 32, 1) != b"\x00"):
        ran += rig.panel.settle(MOVE_CHUNK) or MOVE_CHUNK
    if ran < IDENTITY_RUN:                              # and the screen's dirty byte down: a redraw still due after the
        rig.panel.settle(IDENTITY_RUN - ran)            # run made the next move's update a full one (popglass, step 4)
    drawn = bytes(rig.panel.capture.frames[-1]) if len(rig.panel.capture.frames) > n0 else None
    diff = [i for i in range(1024) if drawn is None or drawn[i] != back[i]]
    if diff or tag in shots:
        rig.panel.panel.write_png(back, str(pathlib.Path(rig.png_dir) / f"popglass_{tag}.png"))
        if drawn and diff:
            rig.panel.panel.write_png(drawn, str(pathlib.Path(rig.png_dir) / f"popglass_{tag}_full.png"))
    check(f"popglass {tag}: a full redraw draws exactly the glass", drawn is not None and not diff,
          "no frame drawn" if drawn is None else f"{len(diff)} bytes, columns {sorted({i // 8 for i in diff})[:8]}")


def scenario_popglass(a, report, sym):
    from emulib.panel import DOWN, NO, UP
    if "mxp_parts" not in sym:
        check("popglass: the build draws the popup's moving layer alone (mxp_parts)", False, "a build before it")
        return
    rig = popglass_rig(a, sym, "popglass")
    if rig is None:
        return
    m, panel = rig.m, rig.panel
    g = lambda n: m.long(sym[n])                                          # noqa: E731
    shots = {"open", "bars3", "scroll", "muted"}
    rig.open(100)
    check("popglass: the popup is up", rig.visible() == 1)
    identity(rig, "open", shots)
    p0, f0 = g("mxp_parts"), g("mxp_fulls")
    late = []
    for step in range(1, 7):                                              # the moving bars and LOCKS' step
        if not move(rig, step):
            late.append(step)
        identity(rig, f"bars{step}", shots)
    check("popglass: the popup took every move", not late, f"no update for steps {late}")
    parts, fulls = g("mxp_parts") - p0, g("mxp_fulls") - f0
    check(f"popglass: the moving bars went alone ({parts} alone, {fulls} full)", parts >= 4 and fulls <= 1)
    rig.turn(1, 1)                                                        # an edit (the lit row's depth)
    identity(rig, "edit", shots)
    move(rig, 7)
    identity(rig, "edit_bars", shots)
    panel.tap(DOWN)                                                       # a scroll: the lit row moves
    panel.tap(DOWN)
    identity(rig, "scroll", shots)
    move(rig, 8)
    identity(rig, "scroll_bars", shots)
    for _ in range(2):                                                    # back to the top: LFO1's row lit
        panel.tap(UP)
    panel.tap(NO)                                                         # mute (the word on screen: drawn whole)
    identity(rig, "mute_word", shots)
    rig.quiet()
    identity(rig, "muted", shots)
    move(rig, 9)
    identity(rig, "muted_bars", shots)
    rig.long_no()                                                         # delete
    rig.quiet()
    identity(rig, "deleted", shots)
    move(rig, 10)
    identity(rig, "deleted_bars", shots)
    report["popglass"] = {"alone": g("mxp_parts"), "fulls": g("mxp_fulls"), "same": g("mxp_same"),
                          "dropped": g("mxp_dropped"), "groups": g("mxp_groups")}


def scenario_popcost(a, report, sym):
    """instructions a second the UI spends drawing (wr_screen), presenting (panel_diff) and polling the popup and the
    moving lines, MW moving every frame: the popup closed (FLTR) and up. Runs on a build before the change too"""
    rig = popglass_rig(a, sym, "popcost")
    if rig is None:
        return
    m, panel = rig.m, rig.panel
    counters = {n: MO.Counter(m, addr) for n, addr in (("screen", sym["wr_screen"]), ("diff", PANEL_DIFF),
                                                         ("mxp_poll", sym["mxp_poll"]), ("mv_poll", sym["mv_poll"]))}
    from emu.pit import INSTR_PER_SEC
    out = {}
    for state in ("closed", "up"):
        if state == "up":
            rig.open(100)
            check("popcost: the popup is up", rig.visible() == 1)
        panel.frame_clock(MO.FRAMES, per_sec=round(1500 * INSTR_PER_SEC / (121 * 1_100_000)))
        panel.settle(30_000_000)
        for c in counters.values():
            c.runs.clear()
        mxp = [n for n in ("mxp_fulls", "mxp_parts", "mxp_same", "mxp_dropped", "mxp_groups") if n in sym]
        m0 = {n: m.long(sym[n]) for n in mxp}
        ticks = 121 * 2                                                   # two seconds of panel ticks
        for t in range(ticks):
            m.write(MW_VAL, struct.pack(">h", int(20000 * math.sin(t / 7.0))))
            m.write(TRACK_CUR, bytes([(t // 15) % 64]))
            m.flush()
            panel.settle(1_100_000)
        res = {n: round(sum(c.runs) / 2) for n, c in counters.items()}
        res["full_draws_a_s"] = len(counters["screen"].runs) / 2
        res["total_a_s"] = sum(v for k_, v in res.items() if k_ in counters)
        res.update({n + "_a_s": (m.long(sym[n]) - m0[n]) / 2 for n in mxp})          # the popup's own redraw counts
        out[state] = res
        check(f"popcost {state}: still up", state == "closed" or rig.visible() == 1)
        panel.clock = None
    out["popup_adds_a_s"] = out["up"]["total_a_s"] - out["closed"]["total_a_s"]
    out["popup_adds_a_frame"] = round(out["popup_adds_a_s"] / 1500)
    print(f"    popcost: {json.dumps(out)}", flush=True)
    report["popcost"] = out


def scenario_env2lock(a, report, sym):
    """ENV2's locks through the panel (csrc/matrix/env2_page.c, csrc/slides): AMP 2/2, a trig held on step 1, knob A
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
    check("env2lock: [AMP] twice is ENV2's page (AMP 2/2)", g("env2_visible") == 1)
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
    from dnfw import slides as SLD
    e2 = struct.unpack(">6H", m.read(lst + SLD.EXT_OFFSET + 16, 12))
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


def scenario_titles(a, report, sym):
    """the AMP pages' titles (the User, 2026-11-13): [AMP] steps ENV1/AMP (stock's page; its own header "AMP" renamed
    by inserts' ins_header) -> ENV2 -> ENV1/AMP (2026-11-19: the scope, WAVEFORM, is no longer an AMP page); each title read back from the title bar, and its lit
    width on screen measured (it must end clear of the screen's right edge)"""
    from emu import panel as EP
    from emulib.panel import Panel
    m = setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/matrix").with_suffix("")) + "_png")
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check("titles: track 1 is WaveTone", MO.set_machine(m, panel, 0, 1) == 1)

    from unicorn import UC_HOOK_CODE

    def title():
        p = MO.guest(m, sym["ins_title_now"]) & 0xFFFFFFFF
        return bytes(m.read(p, 24)).split(b"\0")[0].decode("ascii", "replace") if p else None

    # 2026-11-14 (r5 on the unit showed "Amplitude" on AMP 1/2): reading the message line back (title()) passes even
    # when the bar still draws stock's text, so each title must also be POSTED through stock's message call, SAY
    # 0x4005628C (message, std::string*), the path the bar draws from
    posted = []

    def on_say(uc, ad, sz, us):
        sp = uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
        s = struct.unpack(">I", bytes(uc.mem_read(sp + 8, 4)))[0]
        p = struct.unpack(">I", bytes(uc.mem_read(s, 4)))[0] if 0x40000000 <= s < 0x48000000 else 0
        text = bytes(uc.mem_read(p, 24)).split(b"\0")[0] if 0x40000000 <= p < 0x48000000 else b""
        posted.append(text.decode("ascii", "replace"))
    say_hook = m.uc.hook_add(UC_HOOK_CODE, on_say, begin=0x4005628C, end=0x4005628C)
    m.flush()                                           # (a code hook sees only blocks translated after it: emulib.machine.flush)

    seen = {}
    for want in ("ENV1/AMP", "ENV2", "ENV1/AMP"):
        del posted[:]
        panel.tap((0, 3))                               # [AMP]
        panel.settle(30_000_000)                        # the title's slide over

        def letters_end():
            frame = bytes(panel.capture.frames[-1]) if panel.capture.frames else b""
            lit = EP.lit(frame) if frame else set()
            dark = [x for x in range(20, 128) if any((x, y) not in lit for y in range(2, 8))]
            return max(dark) if dark else None          # the bar is lit, its letters dark: where they end
        # 2026-11-17: since [AMP] acts on its release, the first page's title can still be sliding 30 M after the
        # tap (ENV1/AMP measured at x 123, settled at 57): read where the letters end once they stop moving (two
        # equal readings 5 M apart, at most 120 M more), so the check measures the title, not the slide
        end, ran = letters_end(), 0
        while ran < 120_000_000:
            panel.settle(5_000_000)
            ran += 5_000_000
            now = letters_end()
            if now == end:
                break
            end = now
        name = f"title_{len(seen)}_{want.replace('/', '_')}"
        panel.screen(name)
        seen[name] = (title(), end)
        check(f"titles: [AMP] shows {want!r}", seen[name][0] == want, f"title {seen[name][0]!r}")
        check(f"titles: [AMP] posts {want!r} through stock's message call, last", bool(posted) and posted[-1] == want,
              f"posted {posted!r}")
    m.uc.hook_del(say_hook)
    report["titles"] = seen
    print(f"    titles, where each title's letters end: {seen}", flush=True)
    check("titles: every title's letters end inside the bar, clear of its right end (x < 120)",
          all(e is not None and e < 120 for _, e in seen.values()), str(seen))


def scenario_env2page(a, report, sym):
    """ENV2's page drawn by stock's own AMP page code with ENV2's values (csrc/matrix/env2_page.c; the User, 2026-11-13):
    ENV2's record set to the sound's own AMP envelope, ENV2's page (AMP 2/2) must be stock's AMP page (1/2) pixel for
    pixel below the title bar, but for the page dots; in ADSR and in AHD. Then ENV2's ATK changed: the picture changes"""
    from emu import panel as EP
    from emulib.panel import Panel
    m = setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/matrix").with_suffix("")) + "_png")
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check("env2page: track 1 is WaveTone", MO.set_machine(m, panel, 0, 1) == 1)
    snd = m.long(MO.KIT) + 52
    cell = lambda slot: m.read(snd + 20 + 2 * slot, 1)[0]                          # noqa: E731
    g = lambda fn, *args: MO.guest(m, sym[fn], *args) & 0xFFFFFFFF                    # noqa: E731
    buf = m.alloc(16)

    def put_env(val):                                   # guest: the running UI's registers kept (not Machine.call)
        m.write(buf, val)
        m.flush()
        return MO.guest(m, sym["wish_put"], snd, ENV_TAG, buf, len(val)) & 0xFFFFFFFF

    def screen(name):
        panel.screen(name)
        frame = bytes(panel.capture.frames[-1]) if panel.capture.frames else b""
        return EP.lit(frame) if frame else set()

    def amp_pages():
        """-> the lit pixels of AMP 1/2 and 2/2, ENV2 set to the sound's envelope (ATK HOLD DEC SUS REL MODE RSET)"""
        env = [cell(s) for s in (81, 82, 83, 84, 85, 91, 92)]
        put_env(bytes(env + [0]))
        panel.settle(30_000_000)                        # stock's AMP page, redrawn with the sound's MODE
        one = screen(f"env2page_stock_{env[5]}")
        panel.tap((0, 3))                               # [AMP]: ENV2's
        panel.settle(30_000_000)
        two = screen(f"env2page_env2_{env[5]}")
        panel.tap((0, 3))                               # [AMP]: stock's again (AMP 1/2)
        panel.settle(10_000_000)
        return env, one, two

    panel.tap((0, 3))                                   # [AMP]: stock's AMP page
    panel.settle(10_000_000)
    out = {}
    for mode in (1, 0):                                 # ADSR (the default), then AHD
        m.write(snd + 20 + 2 * 91, bytes([mode, 0]))    # the sound's AMP MODE (stock's draw reads the sound)
        m.flush()
        # 2026-11-17: stock's page draws the MODE when it is entered; it was entered before this write (the last
        # pass's [AMP] taps), and whether a tap still pending redrew it after the write was timing (since [AMP]
        # acts on its release: AHD written, the "stock" capture still ADSR). [AMP] a full turn (ENV2, stock's;
        # 2026-11-19: two pages) so stock's page is entered after the write
        for _ in range(2):
            panel.tap((0, 3))
            panel.settle(30_000_000)
        env, one, two = amp_pages()
        diff = sorted((one ^ two))
        below = [(x, y) for x, y in diff if y >= 12 and x < 122   # not the title bar (ENV1/AMP, ENV2), the page dots,
                 and not (x >= 63 and y >= 36)]                    # nor G and H (2026-11-19: ENV2's DEST and DEP, not
        gh = [(x, y) for x, y in diff if x >= 63 and y >= 36]      # the sound's PAN and VOL)
        box = (min(x for x, _ in below), min(y for _, y in below), max(x for x, _ in below),
               max(y for _, y in below)) if below else None
        out[mode] = {"env": env, "differ": len(below), "box": box, "lit": (len(one), len(two))}
        check(f"env2page: MODE {'ADSR' if mode else 'AHD'}: ENV2's page is stock's AMP page but for the page dots",
              env[5] == mode and len(one) > 200 and not below and g("env2_visible") == 0,
              f"{len(below)} pixels differ, in {box}; lit {len(one)}, {len(two)}")
        check(f"env2page: MODE {'ADSR' if mode else 'AHD'}: G and H are ENV2's DEST and DEP knobs (not PAN, VOL)",
              len(gh) > 20, f"{len(gh)} pixels differ there")
        out[mode]["gh_differ"] = len(gh)
    env = [cell(s) for s in (81, 82, 83, 84, 85, 91, 92)]
    put_env(bytes([(env[0] + 40) % 128] + env[1:] + [0]))
    panel.settle(10_000_000)
    one = screen("env2page_stock_again")
    panel.tap((0, 3))
    panel.settle(30_000_000)
    two = screen("env2page_env2_atk")
    moved = len([(x, y) for x, y in one ^ two if y >= 9])
    check("env2page: ENV2's own ATK changes its knob and shape", moved > 20, f"{moved} pixels differ")
    report["env2page"] = out


def scenario_relay(a, report, sym):
    """2026-11-18 (claude/mx-faster: struct mx_tab's layout changed, so MX_MAGIC did): the matrix's tables in MX_RAM are
    only a cache of the routes in each sound's wishes record (what a project saves). After a flash MX_RAM holds the
    old build's layout; the magic differs, mx_poll lays every track out again from the records. Here: routes put in
    16 sounds' records, the frames heard; then MX_RAM filled with another layout's leftovers (every word 0x55AA55AA,
    the magic included), mx_poll, the same frames: every frame of every row the same, and the tables laid out anew.
    2026-11-18 (main-next 71e2169e, measured): the two runs start from the same state. The first version heard both
    runs on ONE machine, so the second 240 frames were the LFOs' next 240 (their phases ran on): 2,884 differed with
    no garbage written at all, the same count as with it. Now each run is a machine fresh from the snapshot with the
    same routes and the same first mx_poll; only the second has MX_RAM overwritten and mx_poll again. Measured on
    71e2169e: fresh vs fresh 0 differ; fresh vs garbage re-laid 0; garbage NOT re-laid (no second mx_poll) 3,258.
    That last run is kept as the control: it must differ"""
    from dnfw.waverider import pages as PG
    plan = plan_one()
    slots = [(v, p[3]) for v, p in enumerate(plan)]

    def routed(run_name):
        m = setup(a.build, a.snapshot)
        for v, (lfo, wave, mult, slot, dep, base) in enumerate(plan):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
            set_cell(m, v, slot, base)
            for k in (1, 2, 3):
                set_lfo(m, v, k, wave, mult, 0, ATT_FULL)
            r = put_routes(m, sym, v, [(lfo - 1, slot, dep), (2 - (lfo - 1) % 3, slot + 1, 0x6000)])
            check(f"relay ({run_name}): row {v}'s routes put in its sound's record", r == 0, f"{r:#x}")
        m.flush()
        m.call(sym["mx_poll"])
        return m

    before = run(routed("fresh"), sym, a.frames, slots)
    m = routed("re-laid")
    first = m.long(sym["mx_compiles"])
    m.write(PG.MX_RAM, b"\x55\xaa\x55\xaa" * (PG.MX_BYTES // 4))       # another layout's leftovers, magic included
    m.flush()
    m.call(sym["mx_poll"])
    after = run(m, sym, a.frames, slots)
    diff = [(f, v) for f in range(a.frames) for v in range(16) if before[f][v] != after[f][v]]
    moved = [v for v in range(16) if len({before[f][v] for f in range(a.frames)}) > 1]
    check("relay: after MX_RAM held another layout, mx_poll lays it out again (a compile)",
          m.long(sym["mx_compiles"]) > first, f"compiles {first} -> {m.long(sym['mx_compiles'])}")
    check("relay: every frame of every row as before (the routes come back from the records)", not diff,
          f"{len(diff)} differ, first {diff[:3]}" if diff else f"{a.frames} frames x 16 rows")
    check("relay: the routes moved the slots (the comparison means something)", len(moved) >= 12, f"{len(moved)} rows moved")
    m = routed("left")                                  # the control: the leftovers NOT laid out again
    m.write(PG.MX_RAM, b"\x55\xaa\x55\xaa" * (PG.MX_BYTES // 4))
    m.flush()
    left = run(m, sym, a.frames, slots)
    stale = sum(1 for f in range(a.frames) for v in range(16) if before[f][v] != left[f][v])
    check("relay: without mx_poll the leftovers are heard (the comparison sees a stale MX_RAM)", stale > 0,
          f"{stale} differ")
    report["relay"] = {"frames": a.frames, "differ": len(diff), "rows_moved": len(moved), "stale_differ": stale}


# --- (2026-11-19, the User) DEP, the LFO's global attenuverter (csrc/matrix/atten.c, hooks.S lfo_fast) ------------------
SAVER, LOADER = 0x400DD80A, 0x400DD34E  # stock's live -> stored (stored, live) and stored -> live (live, stored)


def sound_dep(m, t, l):
    return MO.u16(m, sound(m, t) + 20 + 2 * (8 + 8 * l))


def field(m, sym, t, call=None):
    buf = m.alloc(16)
    n = (call or m.call)(sym["wish_get"], sound(m, t), LFO_TAG, buf, 12) & 0xFFFFFFFF
    return struct.unpack(">6H", m.read(buf, 12)) if n == 12 else None


def compat(depth, a):
    """atten.c mxa_compat: the DEP a stock unit plays for a first route of DEPTH under the attenuverter A"""
    q = 16384 if a >= 0x7F00 else a - 0x4000
    return max(0, min(0x7FFE, 0x4000 + (((depth - 0x4000) * q) >> 14)))


def scenario_attexact(a, report, sym):
    """an old sound (no record: its DEP the first route's depth) at load, converted by the UI pass (DEP 100 %, the
    depth into the record), is heard as before, bit for bit: every voice row, frame by frame, against the same machine
    left unconverted (no UI pass: the frame's every first route is stock's route 1, DEP its depth). DESTs of every
    kind (25..100 and an LFO's controls), depths from 0 to the top, the half-rate LFOs, the same setup both runs."""
    plan = plan_one()
    heard = {}
    for label in ("before", "converted"):
        gc.collect()
        m = setup(a.build, a.snapshot)
        for v, (lfo, wave, mult, slot, dep, base) in enumerate(plan):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
            set_cell(m, v, slot, base)
            dest = slot if v % 5 else 1 + 8 * (lfo % 3)                 # every fifth row: into another LFO's SPD
            for k in (1, 2, 3):
                d = (dest if k == lfo else 0)
                dp = dep if k == lfo else 0x4000 + 0x400 * k
                set_lfo(m, v, k, wave, mult, d, dp)
                MO.w16(m, sound(m, v) + 20 + 2 * MO.slot(k, "DEST"), d << 8)   # the sound as loaded
                MO.w16(m, sound(m, v) + 20 + 2 * MO.slot(k, "DEP"), dp)
            m.call(sym["wish_drop"], sound(m, v))                       # no record: an old sound
        m.flush()
        if label == "converted":
            m.call(sym["mx_poll"])
            for v in range(16):                                         # the rows as the smoother settles them on
                for k in (1, 2, 3):                                     # the converted sound (DEP 100 %)
                    set_cell(m, v, MO.slot(k, "DEP"), sound_dep(m, v, k - 1))
            m.flush()
        heard[label] = run(m, sym, a.frames, [(v, s) for v in range(16) for s in range(25, 101)])
    conv = [[sound_dep(m, v, l) for l in range(3)] for v in range(16)]
    diff = [f for f in range(a.frames) if heard["before"][f] != heard["converted"][f]]
    moved = len({tuple(x) for x in heard["before"]})
    check("attexact: converted (DEP 100 %, the depths in the record): every row's sound parameters bit for bit as "
          "before, frame by frame", not diff and moved > 10,
          f"{len(diff)} of {a.frames} frames differ (first {diff[:3]}), {moved} distinct frames")
    check("attexact: every converted sound's DEPs at 100 % (0x7ffe)", all(d == 0x7FFE for r in conv for d in r),
          str(conv[:2]))
    report["attexact"] = {"frames": a.frames, "differ": len(diff), "distinct": moved}


def scenario_att(a, report, sym):
    """DEP scales every route of its LFO: LFO1's first route and a route of the record into two slots, DEP set on the
    rows to -64 .. +63 and the top, against the model: route = clamp(cell + mac(-2 (depth - 0x4000), mac(out, M))),
    M = mx_atab[DEP >> 7] (exactly -out from +63 up)"""
    deps = [0x0000, 0x2000, 0x3F00, 0x4000, 0x5100, 0x6000, 0x7E00, 0x7F00, 0x7FFE]
    m = setup(a.build, a.snapshot)
    first_routes(m, sym, {v: (0x7000, NONE, NONE) for v in range(16)})
    for v in range(16):
        m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
        set_cell(m, v, 40, 0x3000)
        set_cell(m, v, 41, 0x3000)
        set_lfo(m, v, 1, v % 7, 4 + v % 3, 40, deps[v % len(deps)])
        for k in (2, 3):
            set_lfo(m, v, k, 0, 4, 0, ATT_FULL)
        put_routes(m, sym, v, [(0, 41, 0x6800)])
    m.flush()
    m.call(sym["mx_poll"])
    atab = struct.unpack(">512i", m.read(sym["mx_atab"], 2048))
    rate = m.long(MO.RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    bad, n = [], 0
    for f in range(min(a.frames, 120)):
        m.call(MO.SMOOTHER, MO.SRC)
        for v in range(16):
            set_cell(m, v, 40, 0x3000)
            set_cell(m, v, 41, 0x3000)
        m.flush()
        m.call(sym["mod_eval"], MO.OUT, rate, 1, 1, o1, o2, 0, limit=4_000_000)
        if f < 2:                                       # (half-rate LFOs: every voice has had its turn from frame 2)
            continue
        for v in range(16):
            dep = deps[v % len(deps)]
            neg = struct.unpack(">i", m.read(lfo_word(m, sym, v, 0), 4))[0]
            out = struct.unpack(">i", m.read(lfo_word(m, sym, v, 0) - m.long(sym["mx_kof"]) + 84, 4))[0]
            want_src = ((out * atab[dep >> 7]) >> 31)
            w40 = max(0, min(TOP, 0x3000 + ((-2 * (0x7000 - NONE) * neg) >> 31)))
            w41 = max(0, min(TOP, 0x3000 + ((-2 * (0x6800 - NONE) * neg) >> 31)))
            got = (MO.u16(m, MO.OUT + 2 * MO.idx(v, 40)), MO.u16(m, MO.OUT + 2 * MO.idx(v, 41)))
            n += 1
            if neg != want_src or got != (w40, w41):
                bad.append((f, v, dep, neg, want_src, got, (w40, w41)))
    check("att: every LFO1 route (the first, the record's) heard at its depth x DEP, the model's, every frame",
          not bad, f"{len(bad)} of {n} differ, first {bad[:2]}")
    report["att"] = {"checked": n, "differ": len(bad)}


def scenario_attsave(a, report, sym):
    """saved for a stock unit: a converted sound's stored DEP is C = its first route's depth x DEP (atten.c mxa_save),
    the field's A the attenuverter; loaded back (stock's loader, our UI pass): DEP the attenuverter again, the depth from
    the record; the stored DEP changed on a stock unit: DEP kept, the first route DEP / A (the User, Q4 a); an old
    sound: its DEP into the record, DEP 100 %"""
    m = setup(a.build, a.snapshot)
    call = m.call
    first_routes(m, sym, {0: (0x6000, 0x5000, NONE)})
    MO.w16(m, sound(m, 0) + 20 + 2 * 8, 0x6000)                       # LFO1's DEP: 50 %
    m.flush()
    call(sym["mx_poll"])
    st = m.alloc(512)
    call(SAVER, st, sound(m, 0))
    stored = bytes(m.read(st, 359))
    got_c = [struct.unpack(">H", stored[28 + 2 * (29 + l):30 + 2 * (29 + l)])[0] for l in range(3)]
    f0 = field(m, sym, 0)
    want_c = [compat(0x6000, 0x6000), compat(0x5000, 0x7FFE), compat(NONE, 0x7FFE)]
    check("attsave: the stored DEPs are C = depth x DEP (a stock unit plays the first routes as heard)",
          got_c == want_c, f"{[hex(x) for x in got_c]} want {[hex(x) for x in want_c]}")
    check("attsave: the field's A the attenuverters at the save", f0 is not None and f0[0] == 0x6000 and f0[2] == 0x7FFE,
          str(f0))
    call(LOADER, sound(m, 1), st)                                     # loaded into track 2: stored form, then the pass
    m.flush()
    dep_loaded = sound_dep(m, 1, 0)
    call(sym["mx_poll"])
    f1 = field(m, sym, 1)
    check("attsave: loaded, the stored DEP is C until the UI pass; then DEP the attenuverter, the depth the record's",
          dep_loaded == want_c[0] and sound_dep(m, 1, 0) == 0x6000 and f1 is not None and f1[1] == 0x6000
          and f1[3] == 0x5000, f"loaded {dep_loaded:#06x}, then {sound_dep(m, 1, 0):#06x}, field {f1}")
    edited = bytearray(stored)
    edited[28 + 2 * 29:30 + 2 * 29] = struct.pack(">H", 0x5800)
    m.write(st, bytes(edited))
    m.flush()
    call(LOADER, sound(m, 2), st)
    m.flush()
    call(sym["mx_poll"])
    f2 = field(m, sym, 2)
    want_d = 0x4000 + (0x1800 * 16384) // 0x2000
    check("attsave: DEP changed on a stock unit: the attenuverter kept, the first route DEP / A (Q4 a)",
          sound_dep(m, 2, 0) == 0x6000 and f2 is not None and f2[1] == want_d, f"DEP {sound_dep(m, 2, 0):#06x}, {f2}")
    call(sym["wish_drop"], sound(m, 3))
    MO.w16(m, sound(m, 3) + 20 + 2 * 8, 0x5555)
    m.flush()
    call(sym["mx_poll"])
    f3 = field(m, sym, 3)
    check("attsave: an old sound: its DEP into the record, DEP 100 %", sound_dep(m, 3, 0) == 0x7FFE and f3 is not None
          and f3[1] == 0x5555, f"DEP {sound_dep(m, 3, 0):#06x}, {f3}")
    report["attsave"] = {"stored": [hex(x) for x in got_c], "loaded": f1, "stock_edit": f2, "old": f3}


def scenario_attpool(a, report, sym):
    """a converted sound (DEP the attenuverter) copied out of the playing kit by stock's memcpy (into the pool, a
    clipboard, a pattern's kit: here a block outside the kit) is stored by the next UI pass (atten.c mxa_moved): its
    DEP = C (a sound lock on it plays its first route as heard: stock's route 1, DEP the depth), the field's A the
    attenuverter, no W_ATT; a copy between the kit's own tracks stays converted"""
    m = setup(a.build, a.snapshot)
    call = m.call
    first_routes(m, sym, {0: (0x6000, NONE, NONE)})
    MO.w16(m, sound(m, 0) + 20 + 2 * 8, 0x6000)                       # LFO1's DEP: 50 %
    m.flush()
    call(sym["mx_poll"])
    out = m.alloc(1200)
    s0 = m.long(sym["mxa_stored"])
    call(sym["wish_memcpy_stub"], out, sound(m, 0), 1163)              # out of the kit
    call(sym["wish_memcpy_stub"], sound(m, 1), sound(m, 0), 1163)      # into the kit's track 2
    m.flush()
    call(sym["mx_poll"])
    buf = m.alloc(16)
    n = call(sym["wish_get"], out, LFO_TAG, buf, 12) & 0xFFFFFFFF
    fo = struct.unpack(">6H", m.read(buf, 12)) if n == 12 else None
    dep_out = MO.u16(m, out + 20 + 2 * 8)
    check("attpool: copied out of the kit, stored by the UI pass: DEP = C, the field's A the attenuverter",
          dep_out == compat(0x6000, 0x6000) and fo is not None and fo[0] == 0x6000 and fo[1] == 0x6000
          and m.long(sym["mxa_stored"]) == s0 + 1, f"DEP {dep_out:#06x}, field {fo}, stored {m.long(sym['mxa_stored']) - s0}")
    check("attpool: the kit's own sound and its copy into track 2 stay converted (DEP the attenuverter)",
          sound_dep(m, 0, 0) == 0x6000 and sound_dep(m, 1, 0) == 0x6000, f"{sound_dep(m, 0, 0):#06x} {sound_dep(m, 1, 0):#06x}")
    call(sym["wish_memcpy_stub"], sound(m, 2), out, 1163)               # back into the kit: converted again
    m.flush()
    call(sym["mx_poll"])
    f2 = field(m, sym, 2)
    check("attpool: copied back into the kit, converted again: DEP the attenuverter, the depth the record's",
          sound_dep(m, 2, 0) == 0x6000 and f2 is not None and f2[1] == 0x6000, f"{sound_dep(m, 2, 0):#06x}, {f2}")
    report["attpool"] = {"dep_out": dep_out, "field": fo}


def scenario_env2att(a, report, sym):
    """ENV2's H (WT_MX_ENV byte 7 = 127 - the knob): 100 % (byte 0) every frame as before (the clone's model), -50 %
    inverted and halved, to the model: cell = clamp(base + mac(-2 (depth - 0x4000), mac(level, M)))"""
    sys.path.insert(0, str(HERE.parent / "test"))
    import test_matrix_c as T
    knobs, events, frames = T.CASES["ADSR, held then released"]
    frames = min(frames, 160)
    lv = T.model(knobs, events, frames)
    rep = {}
    for knob in (127, 32, 64):
        m = setup(a.build, a.snapshot)
        v2, slot, base = 6, 60, 0x3000
        for v in range(16):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
        put_routes(m, sym, v2, [(4, slot, TOP)])
        put_field(m, sym, v2, ENV_TAG, bytes(list(knobs) + [127 - knob]))
        m.flush()
        m.call(sym["mx_poll"])
        M = struct.unpack(">512i", m.read(sym["mx_atab"], 2048))[(knob << 8) >> 7]
        w40 = m.alloc(4)
        got = []
        for f in range(frames):
            ev = events.get(f)
            if ev == "on":
                m.call(sym["hold_len"], v2, v2, 100)
            if ev == "off":
                m.write(w40, struct.pack(">I", 1 << v2))
                m.flush()
                m.call(sym["hold_final"], 1 << v2, w40)
            MO.w16(m, MO.OUT + 2 * MO.idx(v2, slot), base)
            m.flush()
            m.call(sym["mx_eval"], MO.OUT, limit=4_000_000)
            got.append(MO.u16(m, MO.OUT + 2 * MO.idx(v2, slot)))
        want = [max(0, min(TOP, base + ((-2 * (TOP - NONE) * ((x * M) >> 31)) >> 31))) for x in lv]
        bad = [f for f in range(frames) if got[f] != want[f]]
        check(f"env2att: H {knob - 64:+d} every frame as the model", not bad,
              f"{len(bad)} differ, first {[(f, got[f], want[f]) for f in bad[:3]]}")
        rep[str(knob)] = len(bad)
    report["env2att"] = rep



def scenario_attslide(a, report, sym):
    """(2026-11-21) the conversion at a load is heard without a jump or a slide: the same machine run twice, frame by
    frame, (1) never converted (no UI pass: every first route stock's route 1, DEP its depth C), (2) the UI pass run
    after a third of the frames, mid-play, the rows NOT settled by hand (attexact settles them): the conversion's own
    commit (matrix.c mx_poll, atten.c mxa_commit) must. Even rows: old sounds (no record; A = 100 %, D = C): bit for
    bit. Odd rows: saved by this build (the field's A at a knob step, D; the sound's DEP C = mxa_compat(D, A)): within
    the rounding of C (TOL). Before 2026-11-21 the smoother glided each row's DEP from C to A while the first route was
    already D: heard at D x (C .. A) for tens of frames (the negative control: the build before fails here)"""
    TOL = 4
    plan = plan_one()
    at = max(8, a.frames // 3)
    field_a = [0x6000, 0x2000, 0x7000, 0x5000, 0x3800, 0x4800, 0x6800, 0x1000]
    heard = {}
    for label in ("never", "mid-play"):
        gc.collect()
        m = setup(a.build, a.snapshot)
        for v, (lfo, wave, mult, slot, dep, base) in enumerate(plan):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
            set_cell(m, v, slot, base)
            dest = slot if v % 5 else 1 + 8 * (lfo % 3)                 # every fifth row: into another LFO's SPD
            fld = []
            for k in (1, 2, 3):
                d = (dest if k == lfo else 0)
                depth = dep if k == lfo else 0x4000 + 0x400 * k
                A = field_a[(v + k) % len(field_a)]
                dp = depth if v % 2 == 0 else compat(depth, A)          # the stored form: DEP = C
                fld.append((A, depth))
                set_lfo(m, v, k, wave, mult, d, dp)
                MO.w16(m, sound(m, v) + 20 + 2 * MO.slot(k, "DEST"), d << 8)
                MO.w16(m, sound(m, v) + 20 + 2 * MO.slot(k, "DEP"), dp)
            m.call(sym["wish_drop"], sound(m, v))
            if v % 2:
                put_field(m, sym, v, LFO_TAG, b"".join(struct.pack(">HH", A, d) for A, d in fld))
        m.flush()
        rate = m.long(MO.RATE)
        o1, o2 = m.alloc(256), m.alloc(256)
        slots = [(v, s) for v in range(16) for s in range(25, 101)]
        out = []
        for f in range(a.frames):
            if label == "mid-play" and f == at:
                m.call(sym["mx_poll"])                                  # the load's first UI pass, between two frames
                m.flush()
            m.call(MO.SMOOTHER, MO.SRC)
            m.call(sym["mod_eval"], MO.OUT, rate, 1, 1, o1, o2, 0, limit=4_000_000)
            out.append([MO.u16(m, MO.OUT + 2 * MO.idx(v, s)) for v, s in slots])
        heard[label] = out
        if label == "mid-play":
            conv = [[sound_dep(m, v, l) for l in range(3)] for v in range(16)]
            n_conv = m.long(sym["mxa_converted"])
    n = 76
    worst_even, worst_odd, bad_even, bad_odd = 0, 0, [], []
    for f in range(a.frames):
        for i, (x, y) in enumerate(zip(heard["never"][f], heard["mid-play"][f])):
            d, v = abs(x - y), i // n
            if v % 2 == 0:
                worst_even = max(worst_even, d)
                if d:
                    bad_even.append((f, v, 25 + i % n, x, y))
            else:
                worst_odd = max(worst_odd, d)
                if d > TOL:
                    bad_odd.append((f, v, 25 + i % n, x, y))
    moved = len({tuple(x) for x in heard["never"]})
    check(f"attslide: old sounds converted mid-play (frame {at}): every frame of every even row bit for bit as never "
          "converted", not bad_even and moved > 10,
          f"{len(bad_even)} differ, worst {worst_even}, first {bad_even[:3]}; {moved} distinct frames")
    check(f"attslide: sounds saved by this build converted mid-play: every frame of every odd row within {TOL} of "
          "never converted (C's rounding)", not bad_odd, f"{len(bad_odd)} beyond, worst {worst_odd}, first {bad_odd[:3]}")
    check("attslide: every sound converted, DEP the attenuverter (100 % on the old ones, the field's A on the others)",
          n_conv >= 16 and all(conv[v][l] == (0x7FFE if v % 2 == 0 else field_a[(v + l + 1) % len(field_a)])
                               for v in range(16) for l in range(3)), f"{n_conv} converted, {conv[:2]}")
    report["attslide"] = {"frames": a.frames, "at": at, "even_worst": worst_even, "odd_worst": worst_odd,
                          "even_differ": len(bad_even), "odd_beyond": len(bad_odd), "distinct": moved}


def scenario_attsnap(a, report, sym):
    """(2026-11-21) the harness on the build's own snapshot converts the kit once (scripts/emulib/attkit.py): the
    snapshot's kit was converted by the build's UI pass (DEP the attenuverter A, the first routes' depths D in the
    matrix's tables); the runtime written over it, the kit is stored back (DEP = C) and the build's first UI pass gives
    each sound A and D again, as on the unit. DNFW_ATTKIT=0 (the negative control) leaves the kit converted: the pass
    takes A for an old sound's depth (D = 100 %: the 2026-11-20 parachord smear) and this check fails"""
    from emulib import attkit
    m = setup(a.build, a.snapshot)
    rep = attkit.LAST or {}
    deps = rep.get("deps") or (rep.get("found") or {}).get("deps") or []
    if not deps:
        check("attsnap: the snapshot holds no converted kit (not this build's own, or no LFO depth): nothing to check",
              True, str(rep))
        report["attsnap"] = {"report": rep}
        return
    m.call(sym["mx_poll"])
    bad = []
    for t, lfo, A, D, C in deps:
        f = field(m, sym, t)
        got = (sound_dep(m, t, lfo - 1), f[2 * (lfo - 1) + 1] if f else None)
        # heard as before: depth x attenuverter = C. (A sound saved with A < 100 % comes back as an old sound here, A
        # 100 % and D = C: its record is on no +Drive in the emulator; on the unit stock's load reads it back)
        if got[1] is None or compat(got[1], got[0]) != C or (A >= 0x7F00 and got != (A, D)):
            bad.append((t, lfo, got, (A, D)))
    check(f"attsnap: the snapshot's converted kit ({len(deps)} LFOs) converted once by the build's first UI pass: "
          "every first route heard at C as before (old sounds: DEP 100 %, the depth D exactly)", not bad,
          f"{len(bad)} differ, first {[(t, l, tuple(hex(x) for x in g if x is not None), tuple(hex(x) for x in w)) for t, l, g, w in bad[:3]]}"
          + (f" ({rep.get('skipped')})" if rep.get("skipped") else ""))
    report["attsnap"] = {"lfos": len(deps), "differ": len(bad), "skipped": rep.get("skipped")}

def scenario_attcopy(a, report, sym):
    """(2026-11-21) a converted kit sound copied into another track while the wishes table's lock is held (another
    task in the table, or an interrupt's copy) gets its record when the holder lets go (table.c's queue; before, the
    copy was dropped and the UI pass converted the copy a second time: its DEP A taken as an old sound's depth, every
    route of that LFO at A x 100 % instead of D x A); the copy is heard as its source"""
    m = setup(a.build, a.snapshot)
    call = m.call
    first_routes(m, sym, {0: (0x6000, 0x5000, NONE)})
    MO.w16(m, sound(m, 0) + 20 + 2 * 8, 0x3000)                       # LFO1's DEP: -25 %
    m.flush()
    call(sym["mx_poll"])
    f0 = field(m, sym, 0)
    q0, r0 = m.long(sym["wish_queued"]), m.long(sym["wish_reentered"])
    before = field(m, sym, 3)                                         # track 4's own (the snapshot's kit, converted)
    m.write(sym["wish_busy"], b"\x80")                                # the lock held
    m.flush()
    call(sym["wish_memcpy_stub"], sound(m, 3), sound(m, 0), 1163)
    m.flush()
    waiting = field(m, sym, 3)
    call(sym["wish_give"])                                            # the holder lets go
    m.flush()
    busy = m.read(sym["wish_busy"], 1)[0]
    call(sym["mx_poll"])
    f3 = field(m, sym, 3)
    check("attcopy: the copy waits while the lock is held, queued (not dropped)",
          waiting == before and before != f0 and m.long(sym["wish_queued"]) == q0 + 1
          and m.long(sym["wish_reentered"]) == r0,
          f"field {waiting} (before the copy {before}), queued {m.long(sym['wish_queued']) - q0}, dropped {m.long(sym['wish_reentered']) - r0}")
    check("attcopy: done when the holder lets go, the lock free after it", busy == 0 and f3 == f0, f"{f3} vs {f0}")
    check("attcopy: the copy is not converted again (DEP the attenuverter, the first routes' depths its source's)",
          sound_dep(m, 3, 0) == 0x3000 and f3 is not None and f3[1] == 0x6000 and f3[3] == 0x5000,
          f"DEP {sound_dep(m, 3, 0):#06x}, field {f3}")
    report["attcopy"] = {"field": f3, "dep": sound_dep(m, 3, 0)}

# --- 2026-11-20: the inserts locked and modulated (csrc/inserts/ins.c; scratch/mod-live-design.md C) ------------------
INS_DEST, INS_OFFSET = 0xC0, 0xF18      # the knobs' destinations; the packet's place (dnfw.inserts.design.GEN_OFFSET)
TDM_TX = 0x4E6E8100                     # link.c TDM_TX(0): the transmit half smp_tdm(0) writes


def tx_units(m):
    """the link's packet in TDM_TX(0), as the DSP decodes it -> (seq, off, words) or None"""
    from dnfw.sampler import machines as SM
    for base in (TDM_TX, TDM_TX - 0x08000000):          # (the 0x4e... alias, or its 0x46... memory)
        try:
            raw = m.read(base, 0x800)
        except Exception:                               # noqa: BLE001
            continue
        units = []
        for i in range(SM.RX_UNITS):
            x = struct.unpack_from(">I", raw, 4 * (16 * (i >> 3) + 8 + (i & 7)))[0]
            if x >> 16 != SM.TDM_TAG:
                break
            units.append(x & 0xFFFF)
        if len(units) != SM.RX_UNITS or units[0] != SM.RX_MAGIC:
            return None
        if units[255] != (SM.LINK_SEED + sum(units[:255])) & 0xFFFF:
            raise AssertionError("a TDM packet with a bad check")
        off, n = units[2] | units[3] << 16, units[252]
        return units[1], off, [units[4 + 2 * j] | units[5 + 2 * j] << 16 for j in range(n)]
    return None


class Link:
    """smp_tdm(0) a period, its packets decoded and listed: (period, kind, words); kind 'ins', 'cmd', 'tpg', 'lvw', ..."""

    def __init__(self, m, sym):
        from dnfw.sampler import machines as SM
        self.m, self.sym, self.SM = m, sym, SM
        self.period, self.seq, self.log = 0, None, []

    def kind(self, off):
        SM = self.SM
        if 4 * off == INS_OFFSET:
            return "ins"
        if 4 * off == SM.CMD_OFFSET:
            return "cmd"
        if 4 * off == SM.TABLE_READY + 0x100:
            return "tpg"
        if 4 * off == SM.LV_WANT_OFF:
            return "lvw"
        return f"{4 * off:#x}"

    def step(self, call=None):
        (call or self.m.call)(self.sym["smp_tdm"], 0)
        u = tx_units(self.m)
        out = None
        if u and u[0] != self.seq:
            self.seq = u[0]
            out = (self.period, self.kind(u[1]), u[2])
            self.log.append(out)
        self.period += 1
        return out


def ins_load(m, sym, recs, call=None):
    g = call or m.call
    buf = m.alloc(8)
    for i, r in enumerate(recs):
        m.write(buf, bytes(r))
        m.flush()
        g(sym["ins_set_record"], i >> 1, i & 1, buf)
    g(sym["ins_loaded"])


def ins_recs():
    """FUZZ on track 1's INSERT 1 (MIX 100, TONE 40), CHOR on track 2's INSERT 2; the rest OFF"""
    from dnfw.inserts import design as DI
    recs = [[0, 127, 0, 0, 0, 0, 0, 0] for _ in range(DI.RECORDS)]
    recs[0] = [DI.FUZZ, 100, 64, 40, 0, 30, 0, 100]
    recs[3] = [DI.CHOR, 90, 50, 50, 40, 64, 100, 10]
    return recs


def scenario_inslive(a, report, sym):
    """the inserts' round-robin and packet in the ColdFire emulator: frames of mx_eval then smp_tdm(0) (the link's own
    period), its packets decoded as the DSP takes them. No route: every insert packet is ins_words', one every 8 periods,
    the change word still. A route LFO1 -> track 1's INSERT 1 TONE (0xC1): the packed TONE follows the LFO at 187.5 Hz
    (one value every 8 blocks, the one the frame worked out when its group came next), the change word moves only when
    the words differ. Commands and TAPE's PGAIN still go out between them. The costs: ins_period and mx_eval."""
    from dnfw.inserts import design as DI
    rep = {}
    recs = ins_recs()
    for label in ("none", "route"):
        m = setup(a.build, a.snapshot)
        for v in range(16):
            m.write(VSOUND + 4 * v, struct.pack(">I", sound(m, v)))
            for k in (1, 2, 3):
                set_lfo(m, v, k, k, 4, 0, ATT_FULL)
        if label == "route":
            r = put_routes(m, sym, 0, [(0, INS_DEST + 1, TOP)])
            check("inslive: LFO1's route into INSERT 1's TONE put", r == 0, f"{r:#x}")
        m.flush()
        ins_load(m, sym, recs)
        m.call(sym["mx_poll"])
        m.write(sym["sl_lastv"], bytes([0]) + b"\xff" * 15)      # track 1 last played voice 1
        m.flush()
        link = Link(m, sym)
        want = m.alloc(4 * 58)
        m.call(sym["ins_words"], want)
        base = list(struct.unpack(">58I", m.read(want, 4 * 58)))
        expect, rr_seen, costs, mxc = {}, [], [], []
        for f in range(160):
            out = int(0x7FFFFFFF * math.sin(2 * math.pi * f / 50.0))
            set_out(m, sym, 0, 0, out)
            rr = m.long(sym["ins_rr"])
            rr_seen.append(rr)
            _, n = m.cost(sym["mx_eval"], MO.OUT)
            mxc.append(n)
            if rr == 0:                                 # track 1's offset worked out this frame: its value
                x = max(0, min(TOP, (40 << 8) + ((2 * (TOP - NONE) * out) >> 31)))
                expect[f] = x >> 8
            if f == 100 and label == "route":           # other traffic: three commands, TAPE's PGAIN after READY
                m.write(sym["smp_tables"], struct.pack(">i", 2))
                m.write(sym["ins_tpg_gen"], struct.pack(">I", (m.long(sym["ins_tpg_gen"]) + 1) & 0xFFFFFFFF))
                for _ in range(3):
                    m.call(sym["smp_command"], 8, 0, 0, 0, 0)
                m.flush()
            _, c = m.cost(sym["ins_period"]) if f == 159 else (0, 0)
            if c:
                costs.append(c)
            link.step()
        ins = [(p, w) for p, k_, w in link.log if k_ == "ins"]
        gaps = [b[0] - a_[0] for a_, b in zip(ins, ins[1:])]
        rep[label] = {"packets": len(ins), "gaps": sorted(set(gaps)), "kinds": sorted({k_ for _, k_, _ in link.log}),
                      "mx_eval": [min(mxc), max(mxc)]}
        # a command goes first (link.c: each sent CMD_REPEAT = 8 times): a packet due meanwhile waits for it, the next
        # comes back to the fixed phase. A late gap holds at most 8 periods a command logged between, plus one
        late_ok = []
        for (p0, _), (p1, _), g_ in zip(ins, ins[1:], gaps):
            ncmd = sum(1 for p, k_, _ in link.log if p0 < p < p1 and k_ == "cmd")
            late_ok.append(g_ <= 9 or (ncmd and g_ <= 8 + 8 * ncmd + 1))   # (a short one: "back" below)
        back = all(g_ >= 7 or (i and gaps[i - 1] > 9) for i, g_ in enumerate(gaps))   # short only right after a late one
        check(f"inslive {label}: an insert packet every 8 periods (187.5 Hz), only a command may push one on",
              len(ins) >= 18 and all(late_ok) and back and sum(g_ == 8 for g_ in gaps) >= len(gaps) - 4,
              f"{len(ins)} packets, gaps {gaps}")
        chg = [w[0] for _, w in ins]
        moved = [(chg[i + 1] != chg[i]) == (ins[i + 1][1][2:] != ins[i][1][2:]) for i in range(len(ins) - 1)]
        check(f"inslive {label}: the change word moves exactly when the words differ", all(moved),
              f"{sum(not x for x in moved)} packets wrong")
        if label == "none":
            check("inslive none: every packet's words are ins_words' (bit-exact, no route, no lock)",
                  all(w[2:] == base[2:] for _, w in ins[1:]), "")
            check("inslive none: the change word still after the first packet", len(set(chg[1:])) == 1, str(sorted(set(chg))))
        else:
            got = []
            for p, w in ins:
                fs = [f_ for f_ in expect if f_ <= p]
                if fs:
                    got.append((p, DI.unpack(w[2:])[3], expect[max(fs)]))
            bad = [x for x in got if x[1] != x[2]]
            check("inslive route: each packet's TONE is SET + the route as the frame of its group worked it out",
                  got and not bad, f"{len(got)} packets, {len(bad)} differ, first {bad[:3]}")
            vals = [x[1] for x in got]
            # (one value every 8 frames of a 50-frame sine at full depth: clipped at 0 and 127 much of the time)
            check("inslive route: TONE moved with the LFO (the comparison means something)",
                  len(set(vals)) >= 6 and max(vals) - min(vals) >= 100, str(sorted(set(vals))[:12]))
            other = [DI.unpack(w[2:]) for _, w in ins]
            check("inslive route: every other field unchanged", all(o[:3] + o[4:] == DI.unpack(base[2:])[:3]
                  + DI.unpack(base[2:])[4:] for o in other), "")
            kinds = [k_ for p, k_, _ in link.log if p >= 100]
            check("inslive route: commands and TAPE's PGAIN went out between the insert packets",
                  kinds.count("cmd") >= 9 and "tpg" in kinds, str(kinds[:24]))
            rep["route"]["ins_period"] = max(costs) if costs else None
        rep[label]["rr_steps"] = all((rr_seen[i] + 1) % 8 == rr_seen[i + 1] for i in range(len(rr_seen) - 1))
        check(f"inslive {label}: one group a period, every period", rep[label]["rr_steps"])
    m = setup(a.build, a.snapshot)                      # the worst ins_period: a trig changing every group's SET
    ins_load(m, sym, ins_recs())
    for _ in range(9):
        m.call(sym["ins_period"])
    lk = m.alloc(16)
    m.write(lk, struct.pack(">7H", *([0x4020] * 7)))
    m.flush()
    for t in range(16):
        m.call(sym["ins_trig"], t, lk)
    per = lambda n: [m.cost(sym["ins_period"])[1] for _ in range(n)]                  # noqa: E731
    first = per(8)                                      # the blocks after: the trigs' groups packed (at most 3 a block)
    worst = max(first)
    one = max(per(16))                                  # nothing pending: every block's work, the round-robin's group
    m.write(lk, struct.pack(">7H", *([0x4121] * 7)))   # again, other values: the MIX locks already kept
    m.flush()
    trigs = [m.cost(sym["ins_trig"], t, lk)[1] for t in range(16)]
    steady = max(per(8))
    _, trig = m.cost(sym["ins_trig"], 3, 0)
    rep["costs"] = {"ins_period": one, "ins_period_16_trigs": worst, "ins_period_16_trigs_blocks": first,
                    "ins_period_16_trigs_again": steady, "ins_trig_16": sum(trigs), "ins_trig": trig,
                    "mx_eval_none": rep["none"]["mx_eval"], "mx_eval_route": rep["route"]["mx_eval"]}
    print(f"    costs: ins_period {one} a block (most of 16, nothing pending); after 16 tracks' trigs the worst block "
          f"{worst} (the 8 blocks {first}), again with the MIX locks kept {steady}; the 16 ins_trig {sum(trigs)}, "
          f"ins_trig {trig}; mx_eval {rep['none']['mx_eval']} / {rep['route']['mx_eval']}", flush=True)
    check("inslive: mx_eval's cost the same with no route and with an insert route",
          abs(max(rep["route"]["mx_eval"]) - max(rep["none"]["mx_eval"])) <= 16, str(rep["costs"]))
    report["inslive"] = rep


def scenario_inslock(a, report, sym):
    """the inserts' locks and routes popup through the panel: track 1 FUZZ on INSERT 1 (FX twice), a trig held on step 1,
    knob B (DRIV) turned: step 1's lock (kind K1, id 211, INSERT 1's low byte), drawn as a lock; the lock list carries it
    (sl_build); SAVE / LOAD keep it. sl_apply with that list: the packet carrying it is the link's next (its delay
    in periods measured). A plain push on C (TONE) opens the routes popup on 0xC1; a turn makes LFO1's route into it"""
    from emulib.panel import ENCODER_PUSH, Panel
    from dnfw import slides as SLD
    from dnfw.inserts import design as DI
    m = setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/matrix").with_suffix("")) + "_inslock_png")
    key = lambda code: divmod(code - 1, 8)                                            # noqa: E731
    g = lambda fn, *args: MO.guest(m, sym[fn], *args) & 0xFFFFFFFF                    # noqa: E731
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check("inslock: track 1 is WaveTone", MO.set_machine(m, panel, 0, 1) == 1)
    ins_load(m, sym, ins_recs(), lambda fn, *args: MO.guest(m, fn, *args))
    panel.tap(key(19))                                  # RECORD: grid recording
    panel.settle(10_000_000)
    panel.tap(key(25))                                  # a trig on step 1
    panel.settle(10_000_000)
    panel.tap(key(5))                                   # [FX]: FX 1/3
    panel.settle(10_000_000)
    panel.tap(key(5))                                   # [FX]: INSERT 1
    panel.settle(10_000_000)
    check("inslock: [FX] twice is INSERT 1", m.long(sym["ins_up"]) == 1, str(m.long(sym["ins_up"])))
    panel.hold(key(25), 5_000_000)
    panel.settle(10_000_000)
    waited = 15_000_000                                 # stock's held-trig state (slides' held()): turn only once it is up
    while g("sl_ins_held", 0, 0) == 0x10000 and waited < 200_000_000:
        panel.settle(1_000_000)
        waited += 1_000_000
    knob0 = m.read(sym["ins_kv"] + 6, 1)[0]
    print(f"    held after {waited / 1e6:.0f} M instructions (sl_ins_held {g('sl_ins_held', 0, 0):#x}), DRIV {knob0}", flush=True)
    lock, tbl, kind = 0xFFFF, 0, 3 + SLD.E2_KINDS
    for _ in range(12):
        m.pc = panel.panelin.encoder(m.m, panel.profile, 1, 4)
        panel.settle(4_000_000)
        tbl = m.long(sym["sl_ui_table"])
        lock = g("sl_lock_get", tbl, 0, 0, kind) if tbl else 0xFFFF
        if lock != 0xFFFF:
            break
    panel.screen("ins_locked")
    held = g("sl_ins_held", 0, 0)
    panel.let_go(key(25))
    panel.settle(10_000_000)
    check("inslock: a trig held, B turned: step 1's DRIV lock in INSERT 1's byte (above the knob's 64), none in INSERT 2's",
          tbl != 0 and lock != 0xFFFF and 64 < (lock & 0xFF) <= 127 and lock >> 8 == 0xFF and held == lock & 0xFF,
          f"table {tbl:#x}, lock {lock:#06x}, held {held:#x}")
    check("inslock: the knob itself unchanged (DRIV 64: the turn went into the lock)",
          knob0 == 64 and m.read(sym["ins_kv"] + 6, 1)[0] == 64, f"{knob0} -> {m.read(sym['ins_kv'] + 6, 1)[0]}")
    if not tbl or lock == 0xFFFF:
        report["inslock"] = {"lock": lock}
        return
    snd = m.long(MO.KIT) + 52
    lst = m.alloc(1700)
    m.write(lst, bytes(1700))
    m.flush()
    g("sl_build", 0, lst, tbl, snd, 0, 0, 0)
    ext = SLD.EXT_OFFSET
    tail = struct.unpack(">7H", m.read(lst + ext + 32, 14))
    check("inslock: the lock list carries it (sl_build: the tail's insert values)", tail[0] == lock
          and all(x == 0xFFFF for x in tail[1:]), str([hex(x) for x in tail]))
    stored = m.alloc(258 * 80)
    m.write(stored, bytes(258 * 80))
    m.flush()
    g("sl_save", stored, tbl)
    recs = [bytes(m.read(stored + 258 * i, 4)) for i in range(80)]
    check("inslock: SAVE writes it as stored id 211, track 1", sum(1 for r in recs if r[0] == SLD.ID_INS and r[1] == 0) == 1,
          str([r.hex() for r in recs if r[0] >= 200]))
    ram2 = m.alloc(258 * 80)
    m.write(ram2, b"\xff" * (258 * 80))
    m.flush()
    g("sl_load", ram2, stored)
    check("inslock: LOAD brings it back as it was", g("sl_lock_get", ram2, 0, 0, kind) == lock)
    # the delay: sl_apply with the step's list (as the sequencer's note on voice 1), then the link's periods
    m.write(MO.OWNER, struct.pack(">I", 0))
    m.write(VSOUND, struct.pack(">I", snd))
    m.flush()
    link = Link(m, sym)
    call = lambda fn, *args: MO.guest(m, fn, *args)                                   # noqa: E731
    for _ in range(12):
        link.step(call)
    trigs0 = m.long(sym["ins_trigs"])
    call(sym["sl_apply"], 0, lst, MO.SRC)
    lk_now = m.read(sym["ins_lk"], 14)
    delay = None
    for p in range(1, 12):
        out = link.step(call)
        if out and out[1] == "ins" and DI.unpack(out[2][2:])[2] == (lock & 0xFF):
            delay = p
            break
    check("inslock: sl_apply took the trig's lock (ins_trig)", m.long(sym["ins_trigs"]) == trigs0 + 1 and lk_now[0] == lock & 0xFF,
          f"trigs {m.long(sym['ins_trigs']) - trigs0}, ins_lk {lk_now.hex()}")
    check("inslock: the packet carrying the lock is the link's first period after the trig (1 block; the DSP unpacks it "
          "at its next block)", delay == 1, f"delay {delay} periods")
    # the routes popup on INSERT 1's TONE (C), a plain push
    opens0 = m.long(sym["mxp_opens"])
    panel.hold(ENCODER_PUSH[2], 2_000_000)
    m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + 100) & 0xFFFFFFFF))
    m.flush()
    panel.settle(3_000_000)
    panel.let_go(ENCODER_PUSH[2], 5_000_000)
    up = g("mxp_visible")
    panel.screen("ins_popup")
    check("inslock: a plain push on INSERT 1's TONE opens the routes popup", up == 1 and m.long(sym["mxp_opens"]) == opens0 + 1,
          f"up {up} why {m.long(sym['mxp_why'])}")
    if up:
        d0 = struct.unpack(">i", m.read(sym["mxp_detents"], 4))[0]
        for _ in range(32):
            if abs(struct.unpack(">i", m.read(sym["mxp_detents"], 4))[0] - d0) >= 4:
                break
            m.pc = panel.panelin.encoder(m.m, panel.profile, 2, MID)
            panel.settle(4_000_000)
        panel.settle(10_000_000)
        buf = m.alloc(128)
        n = g("wish_get", snd, TAG, buf, 128)
        b = bytes(m.read(buf, n)) if n < 128 else b""
        rs = [tuple(struct.unpack(">BBH", b[i:i + 4])) for i in range(0, len(b), 4)]
        check("inslock: a turn makes LFO1's route into 0xC1 (a route of the record)",
              any(src == 0 and sl == INS_DEST + 1 and dep > NONE for src, sl, dep in rs), str(rs))
        panel.settle(10_000_000)
        m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + 400) & 0xFFFFFFFF))
        m.flush()
        panel.settle(20_000_000)
        rt = g("mx_ins_routes", 0)
        check("inslock: the UI pass laid it out (mx_ins_routes: TONE)", rt == 1 << 1, f"{rt:#x}")
        report["inslock_route"] = rs
    report["inslock"] = {"lock": lock, "tail": list(tail), "delay_periods": delay}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", default=MO.SNAP)
    p.add_argument("--scenario", default="exact,env,env1lfo,env2pop,env2more,popup,plainpush,hold,popsort,popjump,env2jump,popglass,env2lock,titles,env2page,cost,para,relay,attexact,attslide,att,attsave,attpool,attcopy,attsnap,env2att,pernote,inslive,inslock")
    p.add_argument("--frames", type=int, default=240)
    p.add_argument("--json", default=None)
    a = p.parse_args()
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    report = {}
    for sc in a.scenario.split(","):
        print(f"  --- {sc} ---", flush=True)
        {"exact": lambda: scenario_exact(a, report, sym), "env": lambda: scenario_env(a, report, sym),
         "env1lfo": lambda: scenario_env1lfo(a, report, sym),
         "env2pop": lambda: scenario_env2pop(a, report, sym),
         "env2more": lambda: scenario_env2more(a, report, sym),
         "popup": lambda: scenario_popup(a, report, sym),
         "plainpush": lambda: scenario_plainpush(a, report, sym),
         "hold": lambda: scenario_hold(a, report, sym),
         "popsort": lambda: scenario_popsort(a, report, sym),
         "popjump": lambda: scenario_popjump(a, report, sym),
         "env2jump": lambda: scenario_env2jump(a, report, sym),
         "popglass": lambda: scenario_popglass(a, report, sym),
         "popcost": lambda: scenario_popcost(a, report, sym),
         "env2lock": lambda: scenario_env2lock(a, report, sym),
         "titles": lambda: scenario_titles(a, report, sym),
         "env2page": lambda: scenario_env2page(a, report, sym),
         "cost": lambda: scenario_cost(a, report, sym),
         "para": lambda: scenario_para(a, report, sym),
         "relay": lambda: scenario_relay(a, report, sym),
         "attexact": lambda: scenario_attexact(a, report, sym), "att": lambda: scenario_att(a, report, sym),
         "attsave": lambda: scenario_attsave(a, report, sym),
         "attpool": lambda: scenario_attpool(a, report, sym), "env2att": lambda: scenario_env2att(a, report, sym),
         "attslide": lambda: scenario_attslide(a, report, sym), "attcopy": lambda: scenario_attcopy(a, report, sym),
         "attsnap": lambda: scenario_attsnap(a, report, sym),
         "pernote": lambda: __import__("emu_pernote").scenario_pernote(sys.modules[__name__], a, report, sym),
         "inslive": lambda: scenario_inslive(a, report, sym), "inslock": lambda: scenario_inslock(a, report, sym)}[sc]()
    report["ok"] = not FAILS
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print(("FAIL: " + "; ".join(FAILS[:6])) if FAILS else "PASS: matrix (" + a.scenario + ")")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
