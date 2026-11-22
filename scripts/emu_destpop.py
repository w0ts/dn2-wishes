"""The DEST popup (csrc/matrix/dest_pop.c, routes.c; docs/matrix.md "The DEST popup") on the ColdFire emulator, OS 1.12:
an LFO's routes, the first route in stock's DEST and DEP, the others in the record (the User, 2026-11-18: our matrix the
only live source of LFO routes, stock's DEST and DEP the compatibility copy of each LFO's first route).

    emu_destpop.py --build BUILD.syx --snapshot <ui800M snapshot of this build> [--scenario ...] [--json OUT]

open     track 1 WaveTone, [MOD]: LFO1's page; D's push opens the popup (not stock's DEST list: its view and its
         list builder never run); its rows are this LFO's routes first (the first route and the record's, in the list's
         order), then the rest; the list's entries are the ones stock lists for LFO1 (the builder called by hand), in
         stock's order, each once. The open's instructions are counted (the UI's, from the push to the first frame).
edit     the routes set directly (LFO1: DEST FREQ +8, the record's LFO1 -> RES -16 and a muted one), then through the
         keys: D turned sets the lit route's depth (the first route: DEP); YES on an unused row adds it at +32 (DEST in
         use: a route of the record); NO mutes the first route (the record's mark, DEST and DEP kept) and YES unmutes it;
         a long NO deletes the first route (its DEP p-lock freed) and the LFO's next route of the record moves into
         DEST and DEP; FUNC + NO deletes every route of LFO1; D turned to 0 removes a route at once.
ctrl     LFO2's first route into an LFO1 control (slot 1..8): drawn as a route; NO says CAN'T MUTE; a second route into an
         LFO control is refused (LFO CTRL: 1 ROUTE), a route into a sound parameter goes to the record.
pool     16 routes in use (three DESTs, the record's 13): an unused row refuses (FULL).
lfo4     (lfo4 builds) LFO4's page: its DEST alone; with DEST free a turn sets it (lfo4's table), with DEST in use another
         row is refused (LFO4: 1 ROUTE), NO says CAN'T MUTE.
paths    every gesture that opened stock's DEST list on an LFO page (LFO1's, LFO4's): a turn, a fast turn, a push, a
         push-and-turn, FUNC + turn, a trig held + turn, a trig held + push: ours opens, never stock's list (its view
         0x4010660c), and nothing moves; FUNC + push, short or held 0.7 s (2026-11-19, the User: stock's again):
         stock's list, not ours, nothing moved (FUNC + long push never resets a DEST).
jump     (2026-11-19, the User) FUNC + DOWN / FUNC + UP in the DEST popup: the lit row by sections, as the routes
         popup's: this LFO's routes on top, then each of stock's categories (its page id, 0x400dbe4c) in the list's
         order. From the first and second place of every section, each key against the model; plain UP / DOWN one
         row; every UP / DOWN item taken while up (none reaches stock); FUNC + DOWN held jumps on with its repeats.
valid    stock's value check of a record (every LFO page draw checks each knob's value; for a DEST it built the whole
         list) taken over for LFO1-3's DEST: for every slot, on three machines, the answer is stock's, no list built.
frame    the frame's parameter path called by hand (the smoother, MOD SETUP, the evaluator call): a muted first route (the record's
         mark) is heard exactly as DEST 0 on every row, every frame, while the other LFOs' first routes and the record's
         routes play as before; the mark removed, it is heard exactly as stock's route 1 again. Voices of another track
         are not muted (mx_pre: each voice its own track's marks).
hold     held keys as the unit sends them (Panel.tick_clock: stock's key task sends a held key's repeats, 24 panel ticks
         after the press, then every 8; the frame count follows the tick at the unit's rate): D held 0.25 s at the open,
         let go: still up; NO tapped mutes, NO held 0.25 s mutes, NO held 0.7 s deletes the lit route at 0.6 s, still
         up, nothing more on its release; FUNC + NO held deletes every route of LFO1 (LFO3's kept); D pushed and turned,
         held past its first repeat, let go: still up; DOWN held steps with its repeats.
nolfo4   (builds without lfo4, DN2_LFO4 off: the default since 2026-11-19) a sound saved by an lfo4 build: LFO1-3's DEST
         on LFO4's controls (101, 104, 108) and its record's LFO4 field (WT_LFO4, 0x0012): the LFO pages draw, the popup
         opens, turns and closes, stock's fault dump never runs; the frame path (the smoother, MOD SETUP, the
         evaluator) on 16 voices with every LFO's DEST past 100 writes every row exactly as DEST none (slot 0 aside:
         DEST none writes there; the DEST cells hold their own values), and the record keeps its LFO4 field.
edges    a muted first route's edge cases (the frame with MOD SETUP): (a) MOD SETUP into LFO1's DEST while muted, depths
         +0x0400, +0x2000, +0x7fff, -0x2000: LFO1 adds nothing (as at depth 0); (b) the sound's DEST moved from outside: the new destination plays, back: muted again; (c) a
         sound-locked voice: not muted by its track's mark.

Screenshots *_png/ beside the json. Last line PASS or FAIL.
"""

from __future__ import annotations

import argparse
import gc
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import emu_matrix as MX                                             # noqa: E402 -- its machine and frame recipe
import emu_modulation as MO                                         # noqa: E402

TAG = 0x0010                            # WT_MX_ROUTES
MUTED, FIRST = 0x80, 0x40               # matrix.c MX_MUTED, MX_FIRST
NONE = 0x4000
DEST = {0: 4, 1: 12, 2: 20}             # LFO1-3 DEST and DEP slots
DEP = {0: 8, 1: 16, 2: 24}
DEST_REC, DEP_REC = (78, 88, 98, 324), (83, 93, 103, 329)
CTOR, BUILDER = 0x4010660C, 0x4003951E  # stock's DEST list view, its list builder
FUNC = (2, 0)
KNOB_D = 3
FAILS = MX.FAILS
check = MX.check


def rig(a, sym, what, lfo=0):
    """the machine on its UI, track 1 WaveTone, LFO(0..3)'s page up -> a namespace of helpers"""
    import types
    from emulib.panel import MOD, Panel
    m = MX.setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/destpop").with_suffix("")) + f"_{what}_png")
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check(f"{what}: track 1 is WaveTone", MO.set_machine(m, panel, 0, 1) == 1)
    for _ in range(lfo + 1):
        panel.tap(MOD)
        panel.settle(20_000_000)
    snd = m.long(MO.KIT) + 52
    buf = m.alloc(256)
    r = types.SimpleNamespace(m=m, panel=panel, snd=snd, sym=sym)
    r.param = lambda slot: struct.unpack(">H", m.read(snd + 20 + 2 * slot, 2))[0]

    def set_param(slot, val):
        m.write(snd + 20 + 2 * slot, struct.pack(">H", val))
        m.flush()
    r.set_param = set_param

    def first(l):
        """(2026-11-19) LFO L's first route's own depth: the record's WT_MX_LFO (DEP is the attenuverter, atten.c)"""
        n = MO.guest(m, sym["wish_get"], snd, MX.LFO_TAG, buf, 12) & 0xFFFFFFFF
        return struct.unpack(">H", m.read(buf + 4 * l + 2, 2))[0] if n == 12 else r.param(DEP[l])
    r.first = first

    def set_first(l, val):
        """LFO L's first route's depth VAL in the record (the sound converted by the UI pass first)"""
        MO.guest(m, sym["mx_poll"])
        n = MO.guest(m, sym["wish_get"], snd, MX.LFO_TAG, buf, 12) & 0xFFFFFFFF
        f = bytearray(m.read(buf, 12)) if n == 12 else bytearray(struct.pack(">6H", *([MX.ATT_FULL, NONE] * 3)))
        f[4 * l + 2:4 * l + 4] = struct.pack(">H", val)
        m.write(buf, bytes(f))
        m.flush()
        MO.guest(m, sym["wish_put"], snd, MX.LFO_TAG, buf, 12)
    r.set_first = set_first

    def record():
        n = MO.guest(m, sym["wish_get"], snd, TAG, buf, 256) & 0xFFFFFFFF
        return bytes(m.read(buf, n)) if n < 256 else b""
    r.record = record
    r.routes = lambda: [tuple(record()[i:i + 4]) for i in range(0, len(record()), 4)]

    def put(rs):
        val = b"".join(struct.pack(">BBH", s, sl, d) for s, sl, d in rs)
        m.write(buf, val or b"\0")
        m.flush()
        return MO.guest(m, sym["wish_put"], snd, TAG, buf, len(val)) & 0xFFFFFFFF
    r.put = put

    def state():
        up, lf, track, lit, last, n, nroutes = struct.unpack(">iiIIIII", m.read(sym["ldp_p"], 28))
        return types.SimpleNamespace(up=up, lfo=lf, track=track, lit=lit, n=n, nroutes=nroutes)
    r.state = state
    r.rows = lambda: list(struct.unpack(f">{state().n}H", m.read(sym["ldp_rows"], 2 * state().n)))
    r.slot = lambda rid: MO.record(m, rid)[1]
    r.count = lambda name: m.long(sym[name])
    r.detents = lambda: struct.unpack(">i", m.read(sym["ldp_detents"], 4))[0]

    def open_():
        from emulib.panel import ENCODER_PUSH
        panel.tap(ENCODER_PUSH[KNOB_D])                 # D pushed: stock 1.12 makes its DEST list at the press
        panel.settle(20_000_000)
        return state().up == 1
    r.open = open_

    def turn(delta, times=1):
        """TIMES counts of DELTA on D (records of MX.MID counts: 1 unit a count), each settled apart -> the popup's turns taken"""
        d0 = r.detents()
        for _ in range(8 * times):                      # the panel task takes a turn's first counts from rest
            if abs(r.detents() - d0) >= times:          # (emu_matrix's popup rig)
                break
            m.pc = panel.panelin.encoder(m.m, panel.profile, KNOB_D, MX.MID * delta)
            panel.settle(4_000_000)
        panel.settle(10_000_000)
        return r.detents() - d0
    r.turn = turn

    def frames_on(n):
        m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + n) & 0xFFFFFFFF))
        m.flush()

    def long_no():
        from emulib.panel import NO
        panel.hold(NO, 2_000_000)
        frames_on(1000)
        panel.settle(15_000_000)
        panel.let_go(NO, 5_000_000)
    r.long_no = long_no

    def func_no():
        from emulib.panel import NO
        panel.hold(FUNC, 2_000_000)
        panel.tap(NO)
        panel.let_go(FUNC, 5_000_000)
    r.func_no = func_no

    def quiet():
        frames_on(1600)
        panel.settle(20_000_000)
    r.quiet = quiet

    def to_row(rid):
        """UP/DOWN until the lit row is RID's -> found"""
        from emulib.panel import DOWN, UP
        rows = r.rows()
        if rid not in rows:
            return False
        want = rows.index(rid)
        for _ in range(140):
            lit = state().lit
            if lit == want:
                return True
            panel.tap(DOWN if lit < want else UP, after=3_000_000)
        return state().lit == want
    r.to_row = to_row
    r.close = lambda: panel.tap(__import__("emulib.panel", fromlist=["ENCODER_PUSH"]).ENCODER_PUSH[KNOB_D])
    return r


def stock_list(r, want):
    """the entries stock's builder lists for WANT on track 1 (called by hand on its live ParameterSet: emu_modulation's
    recipe), in its order"""
    m = r.m
    tramp = m.alloc(len(MO.TRAMPOLINE))
    m.write(tramp, MO.TRAMPOLINE)
    out = m.alloc(8)
    m.flush()
    return MO.dest_list(m, tramp, out, MO.parameter_set(m), want)


def scenario_probe(a, report, sym):
    """(not in the gate's list) what the UI does around D's push on LFO1's page: stock's list builder's callers, the
    items the popup is handed"""
    from emulib.panel import ENCODER_PUSH
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as K
    r = rig(a, sym, "probe")
    m, panel = r.m, r.panel
    hits, items = [], []

    def chain(uc):
        fp = uc.reg_read(K.UC_M68K_REG_A6) & 0xFFFFFFFF
        out = [hex(struct.unpack(">I", bytes(uc.mem_read(uc.reg_read(K.UC_M68K_REG_A7), 4)))[0])]
        for _ in range(6):
            if not (0x40000000 <= fp < 0x50000000):
                break
            nxt, ra = struct.unpack(">II", bytes(uc.mem_read(fp, 8)))
            out.append(hex(ra))
            fp = nxt
        return out

    def on_builder(uc, ad, sz, us):
        hits.append(("builder", chain(uc)))

    def on_pop(uc, ad, sz, us):
        sp = uc.reg_read(K.UC_M68K_REG_A7)
        it = struct.unpack(">I", bytes(uc.mem_read(sp + 4, 4)))[0]
        b = bytes(uc.mem_read(it, 12))
        items.append((b[0], int.from_bytes(b[4:8], "big"), b[8:12].hex(), r.state().up))
    m.uc.hook_add(UC_HOOK_CODE, lambda *_: hits.append(("ctor",)), begin=CTOR, end=CTOR)
    m.uc.hook_add(UC_HOOK_CODE, on_builder, begin=BUILDER, end=BUILDER)
    m.uc.hook_add(UC_HOOK_CODE, on_pop, begin=sym["ldp_pop"], end=sym["ldp_pop"])

    def on_valid(uc, ad, sz, us):
        sp = uc.reg_read(K.UC_M68K_REG_A7)
        w = struct.unpack(">5I", bytes(uc.mem_read(sp, 20)))
        hits.append(("valid", hex(w[0]), w[2], hex(w[3]), chain(uc)))
    m.uc.hook_add(UC_HOOK_CODE, on_valid, begin=0x40036692, end=0x40036692)
    m.flush()
    push = ENCODER_PUSH[KNOB_D]
    log = []
    panel.hold(push, 5_000_000)
    log.append(("pressed", len(hits), r.state().up))
    panel.settle(20_000_000)
    log.append(("held", len(hits), r.state().up))
    panel.let_go(push, 20_000_000)
    log.append(("let go", len(hits), r.state().up))
    for _ in range(2):
        m.pc = panel.panelin.encoder(m.m, panel.profile, KNOB_D, 4)
        panel.settle(6_000_000)
    log.append(("turned twice", len(hits), r.state().up, r.count("ldp_turns")))
    panel.screen("probe")
    for x in log:
        print("   ", x, flush=True)
    for h in hits[:24]:
        print("    hit", h, flush=True)
    for it in items[:30]:
        print("    item", it, flush=True)
    report["probe"] = {"log": log, "hits": hits[:20], "items": items[:40]}


def scenario_valid(a, report, sym):
    """stock's value check of a record, taken over for an LFO's DEST (dest_pop.c ldp_valid): for LFO1-3's DEST and every
    slot 0..127 (each value's high byte), on WaveTone, FM TONE and PERC, the answer is stock's: the value's entry is in
    the list stock's builder makes for that LFO (called by hand, its live ParameterSet); and no list is built"""
    from unicorn import UC_HOOK_CODE
    from emulib.panel import Panel
    m = MX.setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/destpop").with_suffix("")) + "_valid_png")
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    tramp = m.alloc(len(MO.TRAMPOLINE))
    m.write(tramp, MO.TRAMPOLINE)
    out = m.alloc(8)
    m.flush()
    rep, bad = {}, []
    for name, mtype in MO.MACHINES.items():
        if MO.set_machine(m, panel, 0, mtype) != mtype:
            check(f"valid: track 1 on {name}", False)
            continue
        pset = MO.parameter_set(m)
        lookup = struct.unpack(">I", m.read(m.long(pset) + 80, 4))[0]
        n = 0
        for lfo, (rid, want) in enumerate(((78, 0x1E00), (88, 0x0E00), (98, 0x0600))):
            listed = set(MO.dest_list(m, tramp, out, pset, want))
            builds = []
            h = m.uc.hook_add(UC_HOOK_CODE, lambda *_: builds.append(1), begin=BUILDER, end=BUILDER)
            m.flush()
            for slot in range(128):
                e = MO.guest(m, lookup, pset, slot) & 0xFFFFFFFF
                stock = int(bool(e) and e in listed)
                ours = MO.guest(m, sym["ldp_valid"], pset, rid, slot << 8) & 0xFF
                n += stock
                if ours != stock:
                    bad.append((name, lfo + 1, slot, stock, ours))
            m.uc.hook_del(h)
            m.flush()
            check(f"valid: {name} LFO{lfo + 1} DEST: no list built for 128 values", not builds, f"{len(builds)} built")
        rep[name] = n
    check("valid: every LFO1-3 DEST value's answer is stock's (its entry in stock's list)", not bad,
          f"{len(bad)} differ, first {bad[:4]}" if bad else f"valid values {rep}")
    report["valid"] = {"valid": rep, "differ": len(bad)}


TRIG1 = (3, 0)                          # [TRIG 1] (code 25)
PATHS = ("turn", "spin", "push", "pushturn", "functurn", "funcpush", "funclong", "trigturn", "trigpush")


def open_path(r, path):
    """D's gesture PATH on the LFO page up: a turn (one detent), a spin (a fast turn: several detents in one item), a
    push, a push-and-turn, FUNC + turn, FUNC + push, a trig held + turn, a trig held + push"""
    from emulib.panel import ENCODER_PUSH
    m, panel = r.m, r.panel
    enc = lambda n: setattr(m, "pc", panel.panelin.encoder(m.m, panel.profile, KNOB_D, n))   # noqa: E731
    held = {"functurn": FUNC, "funcpush": FUNC, "funclong": FUNC, "trigturn": TRIG1, "trigpush": TRIG1}.get(path)
    if held:
        panel.hold(held, 3_000_000)
    if path in ("turn", "functurn", "trigturn"):
        for _ in range(8):
            enc(4)
            panel.settle(4_000_000)
            if r.state().up or r.made:
                break
    elif path == "spin":
        enc(24)
        panel.settle(6_000_000)
    elif path in ("push", "funcpush", "trigpush"):
        panel.tap(ENCODER_PUSH[KNOB_D], after=6_000_000)
    elif path == "funclong":                            # (2026-11-19) FUNC + D held 0.7 s: never our reset of DEST
        panel.hold(ENCODER_PUSH[KNOB_D], 2_000_000)
        m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + 1050) & 0xFFFFFFFF))
        m.flush()
        panel.settle(15_000_000)                        # the UI pass (wr_poll) sees the push held that long
        panel.let_go(ENCODER_PUSH[KNOB_D], 3_000_000)
    elif path == "pushturn":
        panel.push_and_turn(KNOB_D, +1, times=1)
    if held:
        panel.let_go(held, 3_000_000)
    panel.settle(20_000_000)


def scenario_paths(a, report, sym):
    """every way stock opened its DEST list on an LFO page opens ours (the User, 2026-11-18: "the destination for mod
    page is still the elektron one ... i just want ours"): LFO1's page and LFO4's, each gesture in PATHS on a machine
    fresh from the snapshot: our popup up, stock's DEST list view (0x4010660c) never made; the first turn that opens
    it moves no depth (as stock's lists: the twist only opens)"""
    from unicorn import UC_HOOK_CODE
    rep = {}
    from dnfw.mods import shipped
    for lfo in (0, 3) if "lfo4" in shipped() else (0,):  # (LFO4's page only with lfo4, DN2_LFO4: off by default)
        for path in PATHS:
            gc.collect()
            r = rig(a, sym, f"paths_l{lfo + 1}_{path}", lfo=lfo)
            m = r.m
            r.made = []
            m.uc.hook_add(UC_HOOK_CODE, lambda *_: r.made.append(1), begin=CTOR, end=CTOR)
            m.flush()
            before = (r.param(DEST[lfo]), r.first(lfo)) if lfo < 3 else None
            rec0 = r.record()
            open_path(r, path)
            s = r.state()
            r.panel.screen("opened")
            moved = lfo < 3 and (r.param(DEST[lfo]), r.first(lfo)) != before or r.record() != rec0
            rep[f"LFO{lfo + 1} {path}"] = {"ours": bool(s.up and s.lfo == lfo), "stock_list": len(r.made),
                                           "moved": bool(moved)}
            stocks = path in ("funcpush", "funclong")   # (2026-11-19, the User: FUNC + push stock's again: on
            if not stocks:                              # stock 1.12 it opens its DEST list, knob-push survey)
                check(f"paths: LFO{lfo + 1}'s page, {path}: our DEST popup, never stock's list, nothing moved",
                      s.up == 1 and s.lfo == lfo and not r.made and not moved,
                      f"ours up {s.up} (lfo {s.lfo}), stock's list made {len(r.made)}x, moved {moved}")
            else:
                check(f"paths: LFO{lfo + 1}'s page, {path}: stock's DEST list, not ours, nothing moved (no reset)",
                      s.up == 0 and (r.made or lfo == 3) and not moved,
                      f"ours up {s.up}, stock's list made {len(r.made)}x, moved {moved}")
    report["paths"] = rep


CATEGORY = 0x400DBE4C                   # an entry's page id (stock's comparator's; dest_pop.c CATEGORY)


def scenario_jump(a, report, sym):
    from emulib.panel import DOWN, UP
    r = rig(a, sym, "jump")
    m, panel = r.m, r.panel
    r.set_param(DEST[0], 67 << 8)                       # LFO1: DEST FREQ (the first route), the record's LFO1 -> RES
    r.set_first(0, 0x4800)
    r.put([(0, 68, 0x3000)])
    seen, arm = MX.watch_returns(m, sym["ldp_pop"])
    if not r.open():
        check("jump: the DEST popup opened", False)
        return
    st = r.state()
    rows = r.rows()
    cat = [MO.guest(m, CATEGORY, e) & 0xFFFFFFFF for e in rows]
    starts = [i for i in range(st.n) if i == 0 or i == st.nroutes or (i > st.nroutes and cat[i] != cat[i - 1])]
    check("jump: opened with LFO1's two routes on top, then stock's categories", st.nroutes == 2 and len(starts) >= 4,
          f"routes {st.nroutes}, rows {st.n}, sections at {starts}")
    if st.n < 3:
        return
    lit = lambda: r.state().lit                                                        # noqa: E731

    def model(p_, down):
        if down:
            after = [i for i in starts if i > p_]
            return after[0] if after else p_
        before = [i for i in starts if i < p_]
        return before[-1] if before else 0

    def go(p_):
        for _ in range(st.n + 4):
            if lit() == p_:
                break
            panel.tap(DOWN if lit() < p_ else UP, after=3_000_000)
        return lit() == p_
    arm()
    s0 = len(seen)
    walk_d = []
    for _ in range(len(starts) + 1):
        MX.func_key(m, panel, DOWN)
        walk_d.append(lit())
    walk_u = []
    for _ in range(len(starts) + 1):
        MX.func_key(m, panel, UP)
        walk_u.append(lit())
    check("jump: FUNC + DOWN from the top visits every section's first row, then stays; FUNC + UP back to 0, stays",
          walk_d == starts[1:] + [starts[-1]] * 2 and walk_u == starts[-2::-1] + [0, 0],
          f"down {walk_d}, up {walk_u}, sections {starts}")
    bad = []
    places = sorted({q for s_ in starts for q in (s_, s_ + 1) if q < st.n} | {st.n - 1})
    for p_ in places:
        for key, down in ((DOWN, True), (UP, False)):
            if not go(p_):
                bad.append((p_, "reach", lit()))
                continue
            MX.func_key(m, panel, key)
            if lit() != model(p_, down):
                bad.append((p_, "DOWN" if down else "UP", lit(), model(p_, down)))
    check(f"jump: FUNC + DOWN / UP from the first two places of each section ({len(places)} places) as the model",
          not bad and r.state().up == 1, f"wrong (place, key, got, want): {bad[:6]}")
    go(1)
    panel.tap(DOWN, after=3_000_000)
    one_d = lit()
    panel.tap(UP, after=3_000_000)
    one_u = lit()
    check("jump: plain DOWN / UP still one row", (one_d, one_u) == (2, 1), f"{one_d}, {one_u}")
    arrows = [x for x in seen[s0:] if x[0] == 0 and x[1] in (11, 14)]
    check("jump: every UP / DOWN item (presses, releases) taken by the popup while up, none on to stock",
          arrows and all(x[3] == 1 for x in arrows), f"{len(arrows)} items, on to stock "
          f"{[x for x in arrows if x[3] != 1][:4]}")
    go(0)
    panel.tick_clock(MO.FRAMES)
    items = panel.watch_items(sym["ldp_pop"])
    n0 = len(items)
    panel.press_for(FUNC, 3)
    panel.press_for(DOWN, 45)                           # the press and two repeats or more
    mid = lit()
    panel.release_for(DOWN, 3)
    panel.release_for(FUNC, 20)
    reps = [t for t, kind, c, f in items[n0:] if kind == 0 and c == 14 and f & 0x08 and f & 1]
    want = starts[min(1 + len(reps), len(starts) - 1)]
    check("jump: FUNC + DOWN held: its repeats jump on by sections, still up", reps and mid == want
          and r.state().up == 1, f"repeats {len(reps)}, lit {mid} (want {want}), sections {starts}")
    report["jump"] = {"sections": starts, "rows": st.n, "routes": st.nroutes}


def scenario_open(a, report, sym):
    from unicorn import UC_HOOK_CODE
    r = rig(a, sym, "open")
    m = r.m
    freq, res = 67, 68
    want = list(dict.fromkeys(e for e in stock_list(r, 0x1E00) if e != 19))   # stock's, "None" left out, once each
    rid_of = {r.slot(e): e for e in want}
    r.set_param(DEST[0], freq << 8)
    r.set_first(0, 0x4800)
    r.put([(0, res, 0x3000), (MUTED | 0, 70, 0x5000), (1, 72, 0x4400)])
    hits = {"ctor": 0, "builder": 0}
    h1 = m.uc.hook_add(UC_HOOK_CODE, lambda *_: hits.__setitem__("ctor", hits["ctor"] + 1), begin=CTOR, end=CTOR)
    h2 = m.uc.hook_add(UC_HOOK_CODE, lambda *_: hits.__setitem__("builder", hits["builder"] + 1), begin=BUILDER,
                       end=BUILDER)
    count = {"n": 0}

    def on_any(uc, ad, sz, us):
        count["n"] += 1
    h3 = m.uc.hook_add(UC_HOOK_CODE, on_any)
    m.flush()
    b0 = r.count("ldp_built")
    opened = r.open()
    m.uc.hook_del(h3)
    m.uc.hook_del(h1)
    m.uc.hook_del(h2)
    m.flush()
    r.panel.screen("open")
    s = r.state()
    check("open: D's push on LFO1's page opens the DEST popup", opened and s.lfo == 0 and s.track == 0,
          f"up {s.up}, lfo {s.lfo}, opens {r.count('ldp_opens')}, refusals {r.count('ldp_refusals')}")
    check("open: stock's DEST list is never made (its view, its builder)", hits == {"ctor": 0, "builder": 0}
          and r.count("ldp_built") == b0 + 1, f"{hits}, our list built {r.count('ldp_built') - b0}x")
    rows = r.rows()
    own = [e for e in want if (e < 321 and 1 <= r.slot(e) <= 8) or e in DEST_REC]   # (lfo4's records: its own table)
    routes = [rid_of[freq], rid_of[res], rid_of[70]]
    routes_in_order = [e for e in rows[:s.nroutes]]
    check("open: the rows are LFO1's three routes (the first, the record's, the muted one) first, in the list's order",
          s.nroutes == 3 and sorted(routes_in_order) == sorted(routes)
          and routes_in_order == [e for e in want if e in routes], f"rows {rows[:6]}, routes {routes}")
    rest = [e for e in want if e not in routes and e not in own]
    check("open: then the rest, stock's LFO1 entries in stock's order, once each (its own controls, DESTs, None left out)",
          rows[s.nroutes:] == rest, f"{len(rows) - s.nroutes} rows, stock {len(rest)}; ours only "
          f"{[(e, r.slot(e)) for e in rows if e not in want][:6]}, stock only {[e for e in rest if e not in rows][:6]}, "
          f"twice {[e for e in set(rows) if rows.count(e) > 1][:6]}")
    report["open"] = {"instructions": count["n"], "rows": len(rows), "routes": s.nroutes, "stock_entries": len(want)}
    print(f"    the open: {count['n']:,} instructions (the push-and-turn, the popup's list, its first frame)", flush=True)
    got = r.turn(+1)
    r.close()
    check("open: D pushed alone closes it, the routes kept", r.state().up == 0 and got > 0
          and r.first(0) == 0x4800 + 0x100 * got, f"up {r.state().up}, {got} detents, DEP {r.first(0):#06x}")


def scenario_edit(a, report, sym):
    from emulib.panel import DOWN, NO, YES
    r = rig(a, sym, "edit")
    m = r.m
    freq, res, drive = 67, 68, 70
    r.set_param(DEST[0], freq << 8)
    r.set_first(0, 0x4800)
    r.put([(0, res, 0x3000), (2, 72, 0x5000)])
    tbl = MO.guest(m, sym["sl_ui_table_now"]) & 0xFFFFFFFF  # a p-lock of LFO1's DEP (slot 8) on step 2
    deplock = None
    if tbl:
        heads = [m.read(tbl + 258 * i, 1)[0] for i in range(80)]
        deplock = heads.index(0xFF) if 0xFF in heads else None
    if deplock is not None:
        vals = [0xFFFF] * 128
        vals[1] = 0x6000
        m.write(tbl + 258 * deplock, bytes([8, 0]) + b"".join(struct.pack(">H", v) for v in vals))
        m.flush()
    check("edit: opened", r.open())
    rid_of = {r.slot(e): e for e in r.rows()}
    r.to_row(rid_of[freq])
    lit = r.rows()[r.state().lit]
    got = r.turn(+1, 2)
    dep1 = 0x4800 + 0x100 * got
    check("edit: D turned on the first route sets DEP, DEST kept", lit == rid_of[freq] and got >= 2
          and r.first(0) == dep1 and r.param(DEST[0]) == freq << 8,
          f"lit {lit}, {got} turns, DEP {r.first(0):#06x}")
    r.panel.tap(NO)
    rec = r.routes()
    mark = [x for x in rec if x[0] == (MUTED | FIRST | 0)]
    r.quiet()
    r.panel.screen("first_muted")
    check("edit: NO mutes the first route: the record's mark, DEST and DEP kept", len(mark) == 1
          and mark[0][1] == freq and r.param(DEST[0]) == freq << 8 and r.first(0) == dep1, f"{rec}")
    MO.guest(m, sym["mx_poll"])
    dm = [struct.unpack(">I", m.read(sym["mx_dmask"] + 64 * l, 4))[0] for l in range(3)]
    check("edit: the frame sees it (mx_dmask: track 1's LFO1 mask 0, LFO2's and LFO3's all ones)",
          dm == [0, 0xFFFFFFFF, 0xFFFFFFFF], str([hex(x) for x in dm]))
    r.panel.tap(YES)
    check("edit: YES unmutes it (the mark gone)", not [x for x in r.routes() if x[0] & FIRST], f"{r.routes()}")
    r.panel.tap(NO)
    r.panel.tap(YES)
    # an unused row: YES adds a route at +32; DEST in use, so a route of the record
    r.to_row(rid_of[drive])
    n0 = len(r.routes())
    said = m.read(sym["ldp_p"] + 44, 8)                 # the word on screen and its end (P.say, P.say_at)
    r.panel.tap(YES)
    check("edit: YES on an unused row adds it at +32, a route of the record (DEST in use), no word shown",
          (0, drive, 0x6000) in [(x[0], x[1], x[2] << 8 | x[3]) for x in r.routes()] and len(r.routes()) == n0 + 1
          and m.read(sym["ldp_p"] + 44, 8) == said, f"{r.routes()}")
    r.quiet()                                           # (UNMUTED, the YES before, gone)
    r.panel.screen("added")
    got = r.turn(-1, 1)
    check("edit: D turned on it: its depth", (0, drive, 0x6000 + 0x100 * got) in
          [(x[0], x[1], x[2] << 8 | x[3]) for x in r.routes()] and got < 0, f"{got}, {r.routes()}")
    r.panel.tap(NO)
    check("edit: NO mutes a route of the record (its MUTED bit, in place)", (MUTED | 0, drive) in
          [(x[0], x[1]) for x in r.routes()], f"{r.routes()}")
    r.quiet()
    r.panel.screen("routes")
    # a long NO on the first route: DEST and its depth take LFO1's next route of the record (RES -16); DEP's lock kept
    # (2026-11-19, the User: DEP is the attenuverter, its p-locks the LFO's)
    r.to_row(rid_of[freq])
    r.panel.tap(NO)                                     # muted first: the mark goes with it
    e0 = r.count("ldp_erased")
    r.long_no()
    freed = bytes(m.read(tbl + 258 * deplock, 258)) if deplock is not None else b""
    rec = r.routes()
    check("edit: a long NO deletes the first route; LFO1's next route of the record moves into DEST and DEP",
          r.count("ldp_erased") == e0 + 1 and r.param(DEST[0]) == res << 8 and r.first(0) == 0x3000
          and (0, res) not in [(x[0], x[1]) for x in rec] and not [x for x in rec if x[0] & FIRST]
          and (deplock is None or freed[:2] == bytes([8, 0])), f"DEST {r.param(DEST[0]):#06x} DEP {r.first(0):#06x}, {rec}, "
                                      f"lock {freed[:4].hex()}")
    r.quiet()
    r.panel.screen("deleted")
    # D turned to 0 on the new first route: it goes, and the muted DRIVE route moves into DEST, muted (the mark)
    r.to_row(rid_of[res])
    for _ in range(80):
        if r.param(DEST[0]) >> 8 != res:
            break
        r.turn(-1 if r.first(0) > NONE else 1)
    rec = r.routes()
    check("edit: turned to 0, the first route goes at once; the muted route of the record takes DEST, muted",
          r.param(DEST[0]) >> 8 == drive and (MUTED | FIRST | 0, drive) in [(x[0], x[1]) for x in rec]
          and not [x for x in rec if x[0] == MUTED | 0], f"DEST {r.param(DEST[0]):#06x}, {rec}")
    r.func_no()
    rec = r.routes()
    check("edit: FUNC + NO deletes every route of LFO1 (DEST 0, the record's, the mark); LFO3's kept",
          r.param(DEST[0]) == 0 and [x for x in rec if (x[0] & 3) == 0 and x[0] & 0x3C == 0 or x[0] & FIRST] == []
          and (2, 72) in [(x[0], x[1]) for x in rec], f"DEST {r.param(DEST[0]):#06x}, {rec}")
    r.quiet()
    r.panel.screen("all_cleared")
    # with DEST free, a new route is the first: DEST and DEP
    r.to_row(rid_of[freq])
    r.panel.tap(YES)
    check("edit: with DEST free, YES makes the first route: DEST and DEP (+32)",
          r.param(DEST[0]) == freq << 8 and r.first(0) == 0x6000, f"{r.param(DEST[0]):#06x} {r.first(0):#06x}")
    r.close()
    report["edit"] = {"record": r.record().hex(), "dest": r.param(DEST[0]), "dep": r.first(0)}


def scenario_hold(a, report, sym):
    """held keys with their repeats, as the unit sends them (2026-11-18, the User: "holding NO also only mutes", the
    routes popup's; this popup had the same v1 code: emu_matrix's scenario hold)"""
    from emulib.panel import DOWN, ENCODER_PUSH, NO, YES
    r = rig(a, sym, "hold")
    m, panel = r.m, r.panel
    K_NO, K_DOWN = 12, 14
    freq, res = 67, 68
    panel.tick_clock(MO.FRAMES)
    first, every = panel.repeat_timing()
    items = panel.watch_items(sym["ldp_pop"])
    erased = lambda: r.count("ldp_erased")                                            # noqa: E731
    muted = lambda: any(x[0] & MUTED for x in r.routes())                             # noqa: E731
    r.set_param(DEST[0], freq << 8)
    r.set_first(0, 0x4800)
    r.put([(0, res, 0x3000), (2, 72, 0x5000)])

    def word_gone():
        panel.skip_frames(1600)
        panel.run_ticks(10)

    panel.press_for(ENCODER_PUSH[KNOB_D], 30)           # D held 0.25 s at the open (past its first repeat)
    panel.release_for(ENCODER_PUSH[KNOB_D], 20)
    check("hold: D held 0.25 s opens the DEST popup, still up after its release", r.state().up == 1,
          f"up {r.state().up}, opens {r.count('ldp_opens')}, repeat timing {first}/{every} ticks")
    if r.state().up != 1:                               # (v1: closed; opened by a tap for the rest of the checks)
        panel.press_for(ENCODER_PUSH[KNOB_D], 3)
        panel.release_for(ENCODER_PUSH[KNOB_D], 20)
    if r.state().up != 1:
        return
    e0 = erased()
    panel.press_for(NO, 3)
    panel.release_for(NO, 20)
    check("hold: NO tapped mutes the lit route", muted() and erased() == e0, f"{r.routes()}")
    panel.press_for(YES, 3)
    panel.release_for(YES, 20)
    word_gone()
    check("hold: YES unmutes it", not muted(), f"{r.routes()}")
    n0 = len(items)
    panel.press_for(NO, 30)
    panel.release_for(NO, 20)
    reps = MX.repeats_of(items, K_NO, n0)
    check("hold: NO held 0.25 s (its repeats came, short of 0.6 s) mutes, deletes nothing", reps and muted()
          and erased() == e0 and r.state().up == 1, f"repeats {len(reps)}, erased {erased() - e0}, {r.routes()}")
    panel.press_for(YES, 3)
    panel.release_for(YES, 20)
    word_gone()
    n0 = len(items)
    pressed = panel.ticks()
    panel.press_for(NO, 85)
    held = (erased(), r.state().up)
    panel.release_for(NO, 20)
    reps = MX.repeats_of(items, K_NO, n0)
    check("hold: NO held 0.7 s, its repeats coming every 8 ticks: the lit route deleted at 0.6 s, still up",
          len(reps) >= 5 and held == (e0 + 1, 1), f"repeats at {[t - pressed for t in reps]}, "
          f"erased {held[0] - e0} while held")
    check("hold: ... let go: nothing more (no mute, still up)", erased() == e0 + 1 and not muted()
          and r.state().up == 1, f"erased {erased() - e0}, {r.routes()}")
    report["hold"] = {"repeat_first": first, "repeat_every": every, "no_repeats": [t - pressed for t in reps]}
    word_gone()
    panel.press_for(FUNC, 3)
    panel.press_for(NO, 85)
    panel.release_for(NO, 3)
    panel.release_for(FUNC, 20)
    rec = r.routes()
    check("hold: FUNC + NO held: every route of LFO1 deleted (DEST 0, the record's), LFO3's kept, still up",
          r.param(DEST[0]) == 0 and not [x for x in rec if (x[0] & 0x3F) == 0] and (2, 72) in [(x[0], x[1]) for x in rec]
          and r.state().up == 1, f"DEST {r.param(DEST[0]):#06x}, {rec}")
    word_gone()
    n0 = len(items)
    panel.press_for(DOWN, 60)
    panel.release_for(DOWN, 10)
    downs = MX.repeats_of(items, K_DOWN, n0)
    check("hold: DOWN held: its repeats reach the popup (the lit row steps with them)", len(downs) >= 3
          and r.state().up == 1 and r.state().lit > 0, f"repeats {len(downs)}, lit {r.state().lit}")
    panel.press_for(ENCODER_PUSH[KNOB_D], 5)             # pushed and turned: the lit row moves
    m.pc = panel.panelin.encoder(m.m, panel.profile, KNOB_D, 4)
    panel.run_ticks(40)                                  # held past the first repeat
    panel.release_for(ENCODER_PUSH[KNOB_D], 20)
    check("hold: D pushed and turned, held past its first repeat, let go: still up", r.state().up == 1,
          f"up {r.state().up}")
    if r.state().up:
        r.close()


def scenario_ctrl(a, report, sym):
    from emulib.panel import NO, YES
    r = rig(a, sym, "ctrl", lfo=1)
    r.set_param(DEST[1], 1 << 8)                        # LFO2 -> LFO1 SPD (slot 1)
    r.set_first(1, 0x5000)
    r.put([])
    check("ctrl: LFO2's popup opened", r.open() and r.state().lfo == 1)
    rid_of = {r.slot(e): e for e in r.rows()}
    rows = r.rows()
    check("ctrl: LFO2 -> LFO1 SPD is its route row", r.state().nroutes == 1 and rows[0] == rid_of[1], f"{rows[:3]}")
    r.panel.tap(NO)
    check("ctrl: NO on a route into an LFO's control: CAN'T MUTE (nothing changes)",
          r.routes() == [] and r.param(DEST[1]) == 1 << 8, f"{r.routes()}")
    r.quiet()
    other = rid_of[2]                                   # LFO1 MULT: another LFO control
    r.to_row(other)
    r.panel.tap(YES)
    check("ctrl: a second route into an LFO's control is refused (LFO CTRL: 1 ROUTE)", r.routes() == []
          and r.param(DEST[1]) == 1 << 8, f"{r.routes()}")
    r.panel.screen("ctrl_refused")
    r.quiet()
    r.to_row(rid_of[67])
    r.panel.tap(YES)
    check("ctrl: a route into a sound parameter goes to the record", (1, 67) in [(x[0], x[1]) for x in r.routes()],
          f"{r.routes()}")
    r.close()


def scenario_pool(a, report, sym):
    from emulib.panel import YES
    r = rig(a, sym, "pool")
    for k in range(3):
        r.set_param(DEST[k], (40 + k) << 8)
        r.set_first(k, 0x5000)
    r.put([(k % 3, 45 + k, 0x4800) for k in range(13)])
    check("pool: opened with 16 routes in use", r.open())
    rid_of = {r.slot(e): e for e in r.rows()}
    r.to_row(rid_of[67])
    n0 = r.record()
    r.panel.tap(YES)
    r.turn(+1)
    check("pool: a 17th route is refused (FULL), by YES and by a turn", r.record() == n0, f"{len(r.record()) // 4}")
    r.panel.screen("full")
    r.close()


def scenario_lfo4(a, report, sym):
    from emulib.panel import NO, YES
    r = rig(a, sym, "lfo4", lfo=3)
    if not r.open():
        check("lfo4: LFO4's page opens the popup", False, f"refusals {r.count('ldp_refusals')}")
        return
    s = r.state()
    rows = r.rows()
    check("lfo4: the popup is LFO4's; its rows hold no LFO4 control", s.lfo == 3
          and all(not 101 <= r.slot(e) <= 108 for e in rows), f"lfo {s.lfo}, rows {rows[:8]}")
    had = s.nroutes
    r.to_row(rows[had] if had < len(rows) else rows[0])
    r.panel.tap(YES)
    r.close()
    r.open()
    s = r.state()
    check("lfo4: YES on an unused row sets LFO4's DEST when it was free: one route", s.nroutes == 1,
          f"routes {had} -> {s.nroutes}")
    rows = r.rows()
    first = rows[0]
    r.to_row(rows[1])
    r.panel.tap(YES)
    r.quiet()
    r.panel.screen("lfo4_refused")
    r.close()
    r.open()
    check("lfo4: a second route is refused (LFO4: 1 ROUTE)", r.state().nroutes == 1 and r.rows()[0] == first,
          f"{r.state().nroutes}")
    r.panel.tap(NO)
    check("lfo4: NO on its route: CAN'T MUTE (no record written)", not [x for x in r.routes() if x[0] & FIRST],
          f"{r.routes()}")
    r.quiet()
    r.panel.screen("lfo4_cant_mute")
    r.close()


MODS = 0x400DB390                       # stock's MOD SETUP pass (mods_fast in the build): after the smoother, before the LFOs


def run_rows(m, sym, frames, plock=None):
    """the frame's parameter path as stock's frame calls it: the smoother, MOD SETUP, the evaluator call (mod_eval)
    -> per frame the 16 voice rows' 101 cells; PLOCK(f) may change the targets before a frame"""
    rate = m.long(MO.RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    out = []
    for f in range(frames):
        if plock:
            plock(f)
            m.flush()
        m.call(MO.SMOOTHER, MO.SRC)
        m.call(MODS, MO.OUT)
        m.call(sym["mod_eval"], MO.OUT, rate, 1, 1, o1, o2, 0, limit=4_000_000)
        out.append(bytes(m.read(MO.OUT + 34, 202 * 16)))
    return out


def sound_dest(m, t, lfo, slot):
    """the sound's own stored DEST of LFO (1..3): the first route the record's mark is compared with (mx_poll)"""
    MO.w16(m, MX.sound(m, t) + 20 + 2 * MO.slot(lfo, "DEST"), slot << 8)


def run_slots(m, sym, frames, slots):
    """run_rows' frames (the smoother, MOD SETUP, the evaluator call) -> per frame the heard value of each (row, slot)"""
    rows = run_rows(m, sym, frames)
    return [[struct.unpack(">H", r[202 * v + 2 * s:202 * v + 2 * s + 2])[0] for v, s in slots] for r in rows]


def set_lfo_f(firsts, m, v, k, wave, mult, dest, dep, t=None, kit=True):
    """(2026-11-19, DEP the attenuverter) MX.set_lfo with its first route's DEPTH kept for the record (FIRSTS
    {track: [LFO1, LFO2, LFO3]}, MX.first_routes) and the row's DEP at 100 %; a voice off its kit sound (a sound lock:
    stock's route 1, DEP its depth) keeps DEP as the depth"""
    t = v if t is None else t
    MX.set_lfo(m, v, k, wave, mult, dest, MX.ATT_FULL if kit else dep)
    if kit:
        firsts.setdefault(t, [NONE] * 3)[k - 1] = dep if dest else firsts.get(t, [NONE] * 3)[k - 1]


def edge_machine(a, sym, dest, dep, mark, vel=None, vsound=None):
    """16 voices on tracks 1-16 (each its kit sound unless VSOUND[v] says otherwise), LFO1 -> DEST at DEP on every row,
    a mark on every track when MARK (the slot it names), VEL (depth) into LFO1's DEST through MOD SETUP's VEL list"""
    gc.collect()                                        # (the machines before this one let go: each holds the snapshot)
    m = MX.setup(a.build, a.snapshot)
    firsts = {}
    for v in range(16):
        snd = vsound(m, v) if vsound else MX.sound(m, v)
        m.write(MX.VSOUND + 4 * v, struct.pack(">I", snd))
        m.write(MO.OWNER + 4 * v, struct.pack(">I", v))
        for s in (40, 50, 60, 70):
            MX.set_cell(m, v, s, 0x3000 + 0x400 * (v % 4))
        kit = snd == MX.sound(m, v)
        for k in (1, 2, 3):
            set_lfo_f(firsts, m, v, k, (v + k) % 7, 4 + v % 3, 0, NONE, kit=kit)
        set_lfo_f(firsts, m, v, 1, v % 7, 4 + v % 3, dest, dep, kit=kit)
        sound_dest(m, v, 1, dest)
        desc = MO.SRC + 3468 + 153 * v + 8                  # MOD SETUP's lists in the voice's descriptor (VEL first)
        m.write(desc, struct.pack(">hh", vel, 4) if vel else bytes(4))
        if mark is not None:
            MX.put_routes(m, sym, v, [(MUTED | FIRST | 0, mark, dep)])
    m.write(0x8000DD40, struct.pack(">16I", *([0x7F000000] * 16)) if vel else bytes(64))
    m.flush()
    MX.first_routes(m, sym, firsts)
    m.call(sym["mx_poll"])
    return m


def strip0(rows):
    """the rows' sound parameters (slots 25..100): what is heard; slot 0 is DEST none's own cell, and the LFOs' own
    cells (their DEP among them) differ between the runs by construction"""
    return b"".join(rows[202 * v + 50:202 * v + 202] for v in range(16))


def scenario_edges(a, report, sym):
    """the muted first route's edge cases: (a) MOD SETUP routed into LFO1's DEST while that first route is muted, at four
    depths (up a little, a lot, the most, down): the LFO adds nothing anywhere (as at DEP 0); (b) DEST changed from outside (CC, Overbridge, the plugin: the sound's DEST
    written) while muted: the mark belongs to the route it muted, the new destination plays (as with no mark), and DEST
    put back is muted again; (c) a voice of the track playing another sound (a sound lock): not muted (the mark is the
    track's sound's), heard as with no mark"""
    frames = min(a.frames, 120)
    rep = {}
    # (a) does stock's MOD SETUP list offer an LFO's DEST? then the frames
    r = rig(a, sym, "edges")
    listed = [e for e in stock_list(r, 0x0200) if e in (78, 88, 98)]
    rep["modsetup_lists_dest"] = listed
    # (the User, 2026-11-18: fixed, the mask applied after MOD SETUP; stock's list offers no LFO DEST, a sound made
    # elsewhere can hold one)
    rep["modsetup_into_dest"] = {}
    for vel in (0x0400, 0x2000, 0x7FFF, -0x2000):       # MOD SETUP's depth: DEST moved a little .. a lot, and down
        mq = edge_machine(a, sym, 50, NONE, None, vel=vel)
        quiet = [strip0(x) for x in run_rows(mq, sym, frames)]
        dest_heard = MO.u16(mq, MO.OUT + 2 * MO.idx(0, 4))
        muted = [strip0(x) for x in run_rows(edge_machine(a, sym, 50, 0x7000, 50, vel=vel), sym, frames)]
        plain = [strip0(x) for x in run_rows(edge_machine(a, sym, 50, 0x7000, None, vel=vel), sym, frames)]
        moved = sum(1 for f in range(frames) if plain[f] != quiet[f])
        diff = [f for f in range(frames) if muted[f] != quiet[f]]
        rep["modsetup_into_dest"][f"{vel:+#06x}"] = {"dest_heard": dest_heard, "muted_differs": len(diff)}
        check(f"edges (a): MOD SETUP (depth {vel:+#06x}, DEST heard unmuted {dest_heard:#06x}) into LFO1's DEST, "
              "the first route muted: every row as with LFO1 at depth 0", not diff and moved > 0,
              f"{len(diff)} of {frames} frames differ; unmuted differs in {moved}")
    # (b) the sound's DEST moved from outside (to 60) while the mark names 50: heard as with no mark; back to 50: muted
    def track_dest(m, slot):
        for t in range(16):
            MO.w16(m, MX.sound(m, t) + 20 + 2 * 4, slot << 8)    # the sound's LFO1 DEST, as CC or Overbridge write it
        for v in range(16):
            MO.w16(m, MO.SRC + 2 * MO.idx(v, 4), slot << 8)      # and the voices' (a new note would copy it)
        m.flush()
        MO.guest(m, sym["mx_poll"])                               # the UI pass

    mb = edge_machine(a, sym, 50, 0x7000, 50)
    track_dest(mb, 60)
    moved_m = run_rows(mb, sym, frames)
    mn = edge_machine(a, sym, 50, 0x7000, None)
    track_dest(mn, 60)
    moved_n = run_rows(mn, sym, frames)
    d1 = [f for f in range(frames) if moved_m[f] != moved_n[f]]
    check("edges (b): DEST moved from outside while muted: the new destination plays (as with no mark)", not d1,
          f"{len(d1)} frames differ")
    track_dest(mb, 50)
    back = [strip0(x) for x in run_rows(mb, sym, frames)]
    q2 = edge_machine(a, sym, 50, NONE, None)
    quiet2 = [strip0(x) for x in run_rows(q2, sym, frames)]
    d2 = [f for f in range(frames) if back[f] != quiet2[f]]
    check("edges (b): DEST put back to the muted route's: muted again (as at depth 0)", not d2, f"{len(d2)} frames differ")
    # (c) sound locks: voices 0-7 play another sound (the pattern's sound pool stand-in: a sound outside the kit)
    other = lambda m, v: (MX.sound(m, v) if v >= 8 else MX.sound(m, 15) + 1163 * 2)   # noqa: E731
    def lock_rows(mark):
        m = edge_machine(a, sym, 50, 0x7000, mark, vsound=other)
        return run_rows(m, sym, frames)
    lk_m, lk_n, lk_q = lock_rows(50), lock_rows(None), run_rows(edge_machine(a, sym, 50, NONE, None, vsound=other),
                                                                   sym, frames)
    row = lambda b, v: b[202 * v + 50:202 * (v + 1)]                # noqa: E731 -- (slots 25..100, as strip0)
    dl = [(f, v) for f in range(frames) for v in range(8) if row(lk_m[f], v) != row(lk_n[f], v)]
    dk = [(f, v) for f in range(frames) for v in range(8, 16) if row(lk_m[f], v) != row(lk_q[f], v)]
    check("edges (c): a sound-locked voice is not muted by its track's mark (as with no mark)", not dl,
          f"{len(dl)} differ, first {dl[:3]}")
    check("edges (c): the track's own sound's voices are muted", not dk, f"{len(dk)} differ, first {dk[:3]}")
    report["edges"] = rep


def scenario_frame(a, report, sym):
    """a muted first route heard as DEST 0; unmuted, as stock's route 1; another track's voices untouched"""
    plan = MX.plan_one()
    slots = [(v, p[3]) for v, p in enumerate(plan)]
    heard = {}
    for label in ("dest0", "muted", "stock", "unmuted"):
        gc.collect()
        m = MX.setup(a.build, a.snapshot)
        firsts = {}
        for v, (lfo, wave, mult, slot, dep, base) in enumerate(plan):
            m.write(MX.VSOUND + 4 * v, struct.pack(">I", MX.sound(m, v)))
            m.write(MO.OWNER + 4 * v, struct.pack(">I", v))
            MX.set_cell(m, v, slot, base)
            for k in (1, 2, 3):
                set_lfo_f(firsts, m, v, k, wave, mult, 0, NONE)
            other = lfo % 3 + 1                             # another LFO's first route, into the same slot
            set_lfo_f(firsts, m, v, other, (wave + 1) % 7, mult + 1, slot, 0x5400)
            if label != "dest0":
                set_lfo_f(firsts, m, v, lfo, wave, mult, slot, dep)
                sound_dest(m, v, lfo, slot)
            set_lfo_f(firsts, m, v, other, (wave + 1) % 7, mult + 1, slot, 0x5400)
            rs = [(lfo - 1 + 1) % 3, slot, 0x3800]          # a route of the record into the same slot
            marks = [(MUTED | FIRST | (lfo - 1), slot, dep)] if label == "muted" else []
            MX.put_routes(m, sym, v, [tuple(rs)] + marks)
        m.flush()
        MX.first_routes(m, sym, firsts)
        m.call(sym["mx_poll"])
        heard[label] = run_slots(m, sym, a.frames, slots)
    diff_m = [(f, v) for f in range(a.frames) for v in range(16) if heard["dest0"][f][v] != heard["muted"][f][v]]
    diff_u = [(f, v) for f in range(a.frames) for v in range(16) if heard["stock"][f][v] != heard["unmuted"][f][v]]
    moved = [v for v in range(16) if len({heard["stock"][f][v] for f in range(a.frames)}
                                         ^ {heard["dest0"][f][v] for f in range(a.frames)}) > 0]
    check("frame: a muted first route is heard as DEST 0 (the other LFO's and the record's routes as before)",
          not diff_m, f"{len(diff_m)} differ, first {diff_m[:3]}" if diff_m else f"{a.frames} frames x 16 rows")
    check("frame: with no mark, the first route is heard as stock's route 1", not diff_u,
          f"{len(diff_u)} differ, first {diff_u[:3]}" if diff_u else f"{a.frames} frames x 16 rows")
    check("frame: the first routes moved the slots (the comparison means something)", len(moved) >= 12,
          f"{len(moved)} rows")
    # a mark on track 1's LFO2 mutes the rows of voices on track 1 only: voices 1-2 on track 1, the rest on track 2,
    # every row's LFO2 into slot 50: track 1's rows heard as DEST none, track 2's as stock's route 1
    heard = {}
    for label in ("mark", "none"):
        gc.collect()
        m = MX.setup(a.build, a.snapshot)
        firsts = {}
        for v in range(16):
            t = 0 if v < 2 else 1
            m.write(MX.VSOUND + 4 * v, struct.pack(">I", MX.sound(m, t)))
            m.write(MO.OWNER + 4 * v, struct.pack(">I", t))
            MX.set_cell(m, v, 50, 0x3000)
            for k in (1, 2, 3):
                set_lfo_f(firsts, m, v, k, v % 7, 4, 0, NONE, t=t)
            set_lfo_f(firsts, m, v, 2, v % 7, 4, 50 if label == "mark" or v >= 2 else 0, 0x6000, t=t)
            sound_dest(m, t, 2, 50 if label == "mark" or t == 1 else 0)
        if label == "mark":
            MX.put_routes(m, sym, 0, [(MUTED | FIRST | 1, 50, 0x6000)])
        m.flush()
        MX.first_routes(m, sym, firsts)
        m.call(sym["mx_poll"])
        heard[label] = run_slots(m, sym, a.frames, [(v, 50) for v in range(16)])
    diff = [(f, v) for f in range(a.frames) for v in range(16) if heard["mark"][f][v] != heard["none"][f][v]]
    check("frame: the mark mutes only the voices of its track (voices 1-2: as DEST none; 3-16: stock's route 1)",
          not diff, f"{len(diff)} differ, first {diff[:3]}" if diff else f"{a.frames} frames x 16 rows")
    report["frame"] = {"frames": a.frames, "muted_differ": len(diff_m), "unmuted_differ": len(diff_u)}


def scenario_nolfo4(a, report, sym):
    from unicorn import UC_HOOK_CODE
    from emulib.panel import MOD
    from dnfw.mods import shipped
    if "lfo4" in shipped():
        check("nolfo4: a build without lfo4 (DN2_LFO4 off)", False, "this tree ships lfo4")
        return
    r = rig(a, sym, "nolfo4")
    m = r.m
    halts = {"n": 0}
    m.uc.hook_add(UC_HOOK_CODE, lambda *_: halts.__setitem__("n", halts["n"] + 1), begin=0x4011EDEC, end=0x4011EDEC)
    m.flush()
    for lfo, slot in ((0, 101), (1, 104), (2, 108)):    # as an lfo4 build saves a route into LFO4's controls
        r.set_param(DEST[lfo], slot << 8)
        r.set_first(lfo, 0x6000)
    l4 = struct.pack(">8H", 0x6000, 4 << 8, 0x4000, 40 << 8, 7 << 8, 0, 0, 0x5000)
    buf = m.alloc(64)
    m.write(buf, l4)
    m.flush()
    put = MO.guest(m, sym["wish_put"], r.snd, 0x0012, buf, len(l4)) & 0xFFFFFFFF
    shots = []
    for k in range(3):                                  # LFO1, LFO2, LFO3's pages drawn with DEST past 100
        r.quiet()
        r.panel.screen(f"nolfo4_lfo{k + 1}")
        shots.append(k)
        r.panel.tap(MOD)
        r.panel.settle(20_000_000)
    for _ in range(4):                                  # back round to LFO1's page (the MOD key cycles the pages)
        if r.state().up:
            break
        r.panel.tap(MOD)
        r.panel.settle(20_000_000)
        try:
            opened = r.open()
        except Exception:                               # noqa: BLE001
            opened = False
        if opened:
            break
    opened = r.state().up == 1
    turned = r.turn(+1) if opened else 0
    if opened:
        r.close()
        r.panel.settle(20_000_000)
    r.panel.screen("nolfo4_after")
    got = MO.guest(m, sym["wish_get"], r.snd, 0x0012, buf, 64) & 0xFFFFFFFF
    kept = bytes(m.read(buf, 16)) if got == 16 else b""
    check("nolfo4: the LFO pages draw and the popup opens and closes with DEST on LFO4's controls, no fault",
          halts["n"] == 0 and opened, f"fault dumps {halts['n']}, opened {opened}, turned {turned}, wish_put {put:#x}")
    check("nolfo4: the record keeps its LFO4 field (an lfo4 build reads it back)", kept == l4,
          f"wish_get {got:#x}, {kept.hex()}")
    heard = {}
    for label, dest in (("past100", (101, 104, 108)), ("none", (0, 0, 0))):
        gc.collect()
        m2 = MX.setup(a.build, a.snapshot)
        for v in range(16):
            m2.write(MX.VSOUND + 4 * v, struct.pack(">I", MX.sound(m2, v)))
            m2.write(MO.OWNER + 4 * v, struct.pack(">I", v))
            for k in (1, 2, 3):
                MX.set_lfo(m2, v, k, (v + k) % 7, 4 + v % 3, dest[k - 1], 0x6000 + 0x400 * k)
                sound_dest(m2, v, k, dest[k - 1])
        m2.flush()
        m2.call(sym["mx_poll"])
        heard[label] = run_rows(m2, sym, 48)
    skip = set(DEST.values())                           # (the DEST cells themselves: their own values)
    diff = [(f, v, s_) for f in range(48) for v in range(16) for s_ in range(1, 101) if s_ not in skip
            and heard["past100"][f][202 * v + 2 * s_:202 * v + 2 * s_ + 2] != heard["none"][f][202 * v + 2 * s_:202 * v + 2 * s_ + 2]]
    check("nolfo4: the frame with every LFO's DEST past 100 writes the rows as DEST none (slot 0 and the DEST cells "
          "aside)", not diff, f"{len(diff)} cells differ, first {diff[:4]}" if diff else "48 frames x 16 rows x 97 slots")
    report["nolfo4"] = {"faults": halts["n"], "opened": opened, "record_kept": kept == l4, "cells_differ": len(diff)}


def scenario_env2(a, report, sym):
    """(2026-11-19, the User) ENV2's page: G opens our DEST popup for ENV2's routes (source 4, the record's, its own
    four), H is ENV2's attenuverter (WT_MX_ENV byte 7 = 127 - the knob); stock's PAN and VOL not turned from it"""
    from emulib.panel import NO, YES
    r = rig(a, sym, "env2", lfo=-1)
    m, panel = r.m, r.panel
    for _ in range(2):                                  # [AMP]: stock's AMP page, then ENV2's
        panel.tap((0, 3))
        panel.settle(30_000_000)
    env2_up = MO.guest(m, sym["env2_visible"]) & 0xFF
    check("env2: ENV2's page up", env2_up == 1, f"env2_visible {env2_up}")
    pan0, vol0 = r.param(89), r.param(90)
    eb = m.alloc(16)

    def h_byte():
        n = MO.guest(m, sym["wish_get"], r.snd, MX.ENV_TAG, eb, 8) & 0xFFFFFFFF
        return m.read(eb + 7, 1)[0] if n == 8 else 0
    h0 = h_byte()
    for _ in range(8):                                  # H turned down: the attenuverter
        m.pc = panel.panelin.encoder(m.m, panel.profile, 7, -4)
        panel.settle(4_000_000)
    panel.settle(10_000_000)
    h1 = h_byte()
    check("env2: H turns ENV2's attenuverter (byte 7 up = the knob down), not the sound's VOL",
          h1 > h0 and r.param(90) == vol0, f"byte 7 {h0} -> {h1}, VOL {vol0:#06x} -> {r.param(90):#06x}")
    m.pc = panel.panelin.encoder(m.m, panel.profile, 6, 4)   # G turned: ENV2's DEST popup (the twist only opens)
    panel.settle(20_000_000)
    st = r.state()
    check("env2: G opens the DEST popup for ENV2 (source 4), PAN untouched", st.up == 1 and st.lfo == 4
          and r.param(89) == pan0, f"up {st.up} source {st.lfo}, PAN {pan0:#06x} -> {r.param(89):#06x}")
    if st.up != 1:
        return
    panel.screen("env2_dest")
    rows = r.rows()
    check("env2: its list holds only sound parameters (slots 25..100)", rows and all(25 <= r.slot(e) <= 100 for e in rows),
          f"{len(rows)} rows")
    n0 = len(r.routes())
    panel.tap(YES)
    rs = r.routes()
    check("env2: YES on an empty row adds an ENV2 route of the record at +32", len(rs) == n0 + 1
          and any(x[0] == 4 and x[2] << 8 | x[3] == 0x6000 for x in rs), f"{rs}")
    panel.tap(NO)
    check("env2: NO mutes it (MUTED in its source byte)", any(x[0] == 0x84 for x in r.routes()), f"{r.routes()}")
    for k in range(3):                                  # three more: the fourth fills ENV2's own four
        r.to_row(rows[k + 1])
        panel.tap(YES)
    n4 = len([x for x in r.routes() if x[0] & 0x7F == 4])
    r.to_row(rows[5])
    panel.tap(YES)
    check("env2: ENV2's four at most (FULL)", n4 == 4 and len([x for x in r.routes() if x[0] & 0x7F == 4]) == 4,
          f"{n4}, {r.routes()}")
    r.func_no()
    check("env2: FUNC + NO deletes ENV2's routes", not [x for x in r.routes() if x[0] & 0x7F == 4], f"{r.routes()}")
    report["env2"] = {"h": [h0, h1], "routes": len(rs)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--frames", type=int, default=240)
    p.add_argument("--scenario", default="", help="default: valid,paths,open,edit,jump,hold,ctrl,pool,frame,edges, then "
                   "lfo4 (DN2_LFO4 on) or nolfo4 (off, 2026-11-19: off by default)")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    if not a.scenario:
        from dnfw.mods import shipped
        a.scenario = "valid,paths,open,edit,jump,hold,ctrl,pool,frame,edges,env2," + ("lfo4" if "lfo4" in shipped() else "nolfo4")
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    report: dict = {}
    run = {"open": scenario_open, "edit": scenario_edit, "hold": scenario_hold, "ctrl": scenario_ctrl,
           "pool": scenario_pool, "lfo4": scenario_lfo4, "frame": scenario_frame, "probe": scenario_probe, "valid": scenario_valid,
           "edges": scenario_edges, "paths": scenario_paths, "jump": scenario_jump, "nolfo4": scenario_nolfo4, "env2": scenario_env2}
    for name in a.scenario.split(","):
        print(f"== {name}", flush=True)
        try:
            run[name](a, report, sym)
        except Exception as e:                          # noqa: BLE001 -- a scenario that broke is a failure
            import traceback
            traceback.print_exc()
            check(f"{name}: ran to its end", False, repr(e)[:300])
    report["fails"] = FAILS
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print("PASS" if not FAILS else f"FAIL: {len(FAILS)} checks: " + "; ".join(FAILS)[:600], flush=True)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
