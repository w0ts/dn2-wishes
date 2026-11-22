"""Knob notches and our popups' slow turns (csrc/knobs, docs/knob-notch.md; the User, 2026-11-19) on the ColdFire
emulator, OS 1.12. The constants are read from csrc/knobs/knob.h, so a retune needs no edit here.

    emu_knobnotch.py --build BUILD.syx --snapshot <ui800M snapshot of this build> [--scenario ...] [--json OUT]

The panel sends counts (the encoders have no detents); each feed below is one record of D counts, settled apart so the
panel task sends it alone (about 15 records a second on the unit).

sound     AMP's PAN (record 71, stock's integer knob): a slow turn down from +6 lands exactly on C (0x4000), the next
          KN_HOLD counts the same way keep it there, then it moves on; a turn back from the notch moves at once; a
          record of KN_PASS counts goes through, one of KN_PASS - 1 is caught (the threshold's edges).
fine      LFO1's DEP (record 83, the attenuverter: stock's fine knob, 1/256 a count, accelerating): from a value off
          the 4/256 grid (0x4003) a slow turn lands on exactly 0x4000; from the top (0x7FFE, 100 %) a medium turn down
          lands on exactly 0x4000 (the value could not be reached before: the fraction stayed).
plock     GRID RECORDING, [TRIG] 1 held, PAN turned down across C: the p-lock written lands on 0x4000 (kn_lock_snd,
          the sound ParameterSet's LOCK_SET), held, then moves on.
outside   writes that come from no knob (a CC, NRPN or Overbridge parameter write reaches the same setters and
          LOCK_SET; the emulator has no MIDI or USB input, so the setters are called by hand, as such a path calls
          them): with no knob item handled the value is written exactly as sent (setter, kit setter, LOCK_SET); with
          a knob item handled by another task (the running task's TCB not the UI loop's) exactly as sent too; the
          positive control, the same call while the UI loop's knob item is handled, is notched.
unipolar  AMP's ATK (record 62, unipolar): a turn at every speed: every value written is the one stock's step
          computed (the setter hook's input), no catch, no hold.
routes    the routes popup (a plain push on FLTR's FREQ, since plain-push): a slow turn moves 1 unit every KN_POP_DIV counts; a route
          turned down to 0 is deleted there and held; a route at the top end (0x7FFE) turned down reaches exactly 0
          and is deleted.
dest      the DEST popup (LFO1's D): a route added at +32 turned down reaches exactly 0 and is deleted.
env2      ENV2's page, H (its attenuverter, from 127 = +100 %): turned down it lands on exactly 64 (0 %), held.

Last line PASS or FAIL.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import emu_matrix as MX                                             # noqa: E402 -- its machine and popup rig
import emu_modulation as MO                                         # noqa: E402

KH = (HERE.parent / "csrc/knobs/knob.h").read_text()
K = {m.group(1): int(m.group(2)) for m in re.finditer(r"#define (KN_\w+)\s+(\d+)u?\b", KH)}
HOLD, PASS, POP_SLOW, POP_DIV, POP_FAST, POP_MUL = (K["KN_HOLD"], K["KN_PASS"], K["KN_POP_SLOW"], K["KN_POP_DIV"],
                                                    K["KN_POP_FAST"], K["KN_POP_FAST_MUL"])
N = 0x4000
CUR_TCB = 0x4664BCDC
SETTER, KIT_SETTER, LOCK_SET_SND = 0x40037B74, 0x40037D86, 0x40037CB6
AMP, FX_KEY, LFO_KEY, RECORD_KEY, TRIG1, FUNC = (0, 3), (0, 4), (0, 5), (2, 2), (3, 0), (2, 0)
KNOB_G, KNOB_H, KNOB_A = 6, 7, 0
GAP = 4_000_000                         # instructions between records: each feed is a record of its own
FAILS = MX.FAILS
check = MX.check


def rig(a, sym, what):
    """the machine on its UI, track 1 WaveTone; feeds and reads -> a namespace"""
    import types
    from emulib.panel import Panel
    m = MX.setup(a.build, a.snapshot)
    panel = Panel(m, png_dir=str(pathlib.Path(a.json or "out/knobnotch").with_suffix("")) + f"_{what}_png")
    m.write(MO.UI_TRACK, b"\x00")
    panel.settle(3_000_000)
    check(f"{what}: track 1 is WaveTone", MO.set_machine(m, panel, 0, 1) == 1)
    snd = m.long(MO.KIT) + 52
    r = types.SimpleNamespace(m=m, panel=panel, snd=snd, sym=sym, this={})
    r.word = lambda slot: struct.unpack(">H", m.read(snd + 20 + 2 * slot, 2))[0]
    r.n = lambda name: m.long(sym[name])

    def put(slot, val):
        m.write(snd + 20 + 2 * slot, struct.pack(">H", val))
        m.flush()
    r.put = put

    def feed(k, d, gap=GAP):
        m.pc = panel.panelin.encoder(m.m, panel.profile, k, d)
        panel.settle(gap)
    r.feed = feed

    def pause():
        """a pause past every hold and leftover (the frame count moved by hand: no audio interrupt here)"""
        m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + 4000) & 0xFFFFFFFF))
        m.flush()
        panel.settle(20_000_000)
    r.pause = pause
    from unicorn import UC_HOOK_CODE

    def on_set(uc, ad, sz, us):                         # the setters' and LOCK_SET's `this` (for the outside calls)
        sp = uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
        r.this.setdefault(ad, struct.unpack(">I", bytes(uc.mem_read(sp + 4, 4)))[0])
    for ad in (SETTER, KIT_SETTER, LOCK_SET_SND):
        m.uc.hook_add(UC_HOOK_CODE, on_set, begin=ad, end=ad)
    m.flush()                                           # (a code hook sees only blocks translated after it)
    return r


def approach(r, k, slot, d, stop, most=60):
    """records of D counts on K until the value of SLOT is at or past STOP -> the values after each record"""
    vals = []
    for _ in range(most):
        r.feed(k, d)
        vals.append(r.word(slot))
        if (d < 0 and vals[-1] <= stop) or (d > 0 and vals[-1] >= stop):
            break
    return vals


def rest_hook(r):
    """-> a switch: while armed, the next knob step (0x4011364e) starts with its encoder's rest counter at 0 (+16 of
    its 20-byte state; emu_encoder_trace.py --rest 0), so that record is not taken by stock's guard"""
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as UK
    sw = {"arm": 0}

    def on_step(uc, ad, sz, us):
        if not sw["arm"]:
            return
        sp = uc.reg_read(UK.UC_M68K_REG_A7)
        obj, enc = struct.unpack(">2I", bytes(uc.mem_read(sp + 4, 8)))
        st = obj + 32 + 20 * enc if enc <= 9 else obj + 232
        uc.mem_write(st + 16, struct.pack(">i", 0))
        sw["arm"] = 0
    r.m.uc.hook_add(UC_HOOK_CODE, on_step, begin=0x4011364E, end=0x4011364E)
    r.m.flush()
    return sw


def scenario_sound(a, report, sym):
    r = rig(a, sym, "sound")
    r.panel.tap(AMP)
    r.panel.settle(20_000_000)
    slot = MO.record(r.m, 71)[1]
    r.put(slot, N + 0x600)
    c0 = r.n("kn_catches")
    vals = approach(r, KNOB_G, slot, -2, N)
    check("sound: PAN turned down slowly (2 counts a record) from +6 lands exactly on C, caught once",
          vals and vals[-1] == N and r.n("kn_catches") == c0 + 1 and all(x >= N for x in vals),
          f"{[hex(v) for v in vals]}, catches {r.n('kn_catches') - c0}")
    held = []
    for _ in range(HOLD):
        r.feed(KNOB_G, -1)
        held.append(r.word(slot))
    moved = approach(r, KNOB_G, slot, -1, N - 0x100, most=6)
    check(f"sound: the next {HOLD} counts the same way stay on C, then it moves on",
          held == [N] * HOLD and moved and moved[-1] == N - 0x100, f"held {[hex(v) for v in held]}, then "
          f"{[hex(v) for v in moved]}")
    r.pause()
    back = approach(r, KNOB_G, slot, +2, N, most=10)    # back up to C: caught again
    rel0 = r.n("kn_releases")
    away = approach(r, KNOB_G, slot, -2, N - 0x100, most=4)
    check("sound: caught again from below, a turn back moves off it at once (released)",
          back and back[-1] == N and away and away[-1] == N - 0x100 and r.n("kn_releases") > rel0,
          f"up {[hex(v) for v in back]}, back {[hex(v) for v in away]}")
    edge = {}
    rest = rest_hook(r)
    for d in (-PASS, -(PASS - 1)):                      # the threshold: a record of PASS counts passes, PASS - 1 caught
        r.pause()
        r.put(slot, N + 0x900)
        approach(r, KNOB_G, slot, -2, N + 0x300, most=24)  # awake, close: no catch yet
        start, p0 = r.word(slot), r.n("kn_passes")
        rest["arm"] = 1                                 # stock's rest guard emptied for this record (it may swallow a
        r.feed(KNOB_G, d)                               # record after a pause: the knob step's own, not ours)
        edge[d] = (start, r.word(slot), r.n("kn_passes") - p0, struct.unpack(">i", r.m.read(sym["kn_d"], 4))[0])
    (s1, v1, p1, d1), (s2, v2, p2, d2) = edge[-PASS], edge[-(PASS - 1)]
    check(f"sound: a record of {PASS} counts passes C, one of {PASS - 1} is caught on it",
          v1 < N and p1 == 1 and v2 == N and p2 == 0 and s1 > N and s2 > N,
          f"{PASS}: {s1:#06x} -> {v1:#06x} (record {d1}); {PASS - 1}: {s2:#06x} -> {v2:#06x} (record {d2})")
    report["sound"] = {"down": vals, "held": held, "edge": {str(k): v for k, v in edge.items()}}


def scenario_fine(a, report, sym):
    r = rig(a, sym, "fine")
    r.panel.tap(LFO_KEY)
    r.panel.settle(20_000_000)
    slot = MO.record(r.m, 83)[1]
    r.put(slot, N + 3)                                  # off stock's 4/256 grid
    r.pause()
    c0 = r.n("kn_catches")
    vals = approach(r, KNOB_H, slot, -2, N)
    check("fine: DEP (the attenuverter) from 0x4003, turned down slowly: exactly 0x4000",
          vals and vals[-1] == N and r.n("kn_catches") == c0 + 1, f"{[hex(v) for v in vals]}")
    r.pause()
    r.put(slot, 0x7FFE)                                 # 100 %, as an imported sound's
    r.pause()
    vals2 = approach(r, KNOB_H, slot, -8, N, most=200)
    check("fine: DEP from the top (0x7FFE, 100 %) turned down (8 counts a record): exactly 0x4000",
          vals2 and vals2[-1] == N, f"{len(vals2)} records, last {[hex(v) for v in vals2[-4:]]}")
    report["fine"] = {"slow": vals, "top": len(vals2)}


def scenario_plock(a, report, sym):
    from unicorn import UC_HOOK_CODE
    r = rig(a, sym, "plock")
    m, panel = r.m, r.panel
    panel.tap(AMP)
    panel.settle(20_000_000)
    slot = MO.record(m, 71)[1]
    r.put(slot, N + 0x400)
    locks = []

    def on_lock(uc, ad, sz, us):
        sp = uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
        this, rid, val, step = struct.unpack(">4I", bytes(uc.mem_read(sp + 4, 16)))
        locks.append((rid, val, step))
    m.uc.hook_add(UC_HOOK_CODE, on_lock, begin=LOCK_SET_SND, end=LOCK_SET_SND)
    m.flush()
    panel.tap(RECORD_KEY)                               # GRID RECORDING
    panel.settle(10_000_000)
    panel.hold(TRIG1, 5_000_000)
    for _ in range(16):                                 # the lock made, then turned up away from C (free from it)
        r.feed(KNOB_G, +2)
    up = [v for rid, v, s in locks if rid == 71]
    n0, l0, c0 = len(up), r.n("kn_locks"), r.n("kn_catches")
    for _ in range(30):                                 # down across C
        r.feed(KNOB_G, -2)
        if r.n("kn_catches") > c0:
            break
    pan = [v for rid, v, s in locks if rid == 71][n0:]
    for _ in range(HOLD + 6):
        r.feed(KNOB_G, -1)
    pan2 = [v for rid, v, s in locks if rid == 71][n0:]
    panel.let_go(TRIG1, 5_000_000)
    panel.tap(RECORD_KEY)
    check("plock: a knob-driven p-lock of PAN turned down across C lands exactly on 0x4000 (kn_lock_snd), the base "
          "untouched", up and up[-1] > N and pan and pan[-1] == N and all(v >= N for v in pan) and r.n("kn_locks") > l0
          and r.word(slot) == N + 0x400, f"up {[hex(v) for v in up[-3:]]}, down {[hex(v) for v in pan]}, "
          f"base {r.word(slot):#06x}")
    after = pan2[len(pan):]
    check(f"plock: held there {HOLD} counts, then it moves on", after and after[-1] < N
          and all(v == N for v in after[:2]), f"{[hex(v) for v in after]}")
    report["plock"] = {"locks": pan2}


def scenario_outside(a, report, sym):
    r = rig(a, sym, "outside")
    m, panel = r.m, r.panel
    panel.tap(AMP)
    panel.settle(20_000_000)
    slot = MO.record(m, 71)[1]
    r.put(slot, N + 0x300)
    approach(r, KNOB_G, slot, -2, N + 0x100, most=12)   # a knob turn first: its `this`, the knob item's TCB
    panel.hold(FUNC, 2_000_000)                         # FUNC + FX: the send FX pages (kit values): a knob turned there
    panel.tap(FX_KEY)
    panel.let_go(FUNC, 10_000_000)
    for kk in range(8):                                 # (records of 2: past stock's rest guard, and back)
        for d in (2, 2, 2, -2, -2, -2):
            r.feed(kk, d)
    panel.tap(AMP)
    panel.settle(20_000_000)
    this = r.this.get(SETTER)
    check("outside: the sound setter's object seen", bool(this), f"{r.this}")
    if not this:
        return
    r.pause()

    def setter_call(v):
        r.put(slot, N + 0x100)
        MO.guest(m, SETTER, this, 71, v, 0, 1, 0)
        return r.word(slot)
    seen0 = r.n("kn_seen")
    idle = setter_call(N - 0x100)
    check("outside: the setter called with no knob item handled (as a CC, NRPN or Overbridge write): exactly as sent",
          idle == N - 0x100 and r.n("kn_seen") == seen0 and r.n("kn_cur") == 0,
          f"{idle:#06x}, kn_cur {r.n('kn_cur')}")
    tcb = m.long(CUR_TCB)
    m.write(sym["kn_cur"], struct.pack(">I", KNOB_G + 1))
    m.write(sym["kn_d"], struct.pack(">i", -2))
    m.write(sym["kn_tcb"], struct.pack(">I", (tcb ^ 0x10) & 0xFFFFFFFF))
    m.flush()
    other = setter_call(N - 0x100)
    m.write(sym["kn_tcb"], struct.pack(">I", tcb))
    m.flush()
    ctrl = setter_call(N - 0x100)                       # the positive control: the UI loop's own knob item
    m.write(sym["kn_cur"], struct.pack(">I", 0))
    m.flush()
    check("outside: a write by another task while a knob item is handled: exactly as sent; the UI loop's: notched",
          other == N - 0x100 and ctrl == N, f"other task {other:#06x}, the loop's {ctrl:#06x}")
    kit = r.this.get(KIT_SETTER)
    check("outside: the kit setter's object seen (a send FX page's knob turned first)", bool(kit), f"{r.this}")
    if kit:                                             # the kit setter (delay WID, record 115), with no knob item
        kslot = MO.record(m, 115)[1]
        inner = m.long(kit + 16)                        # its values: self + 16's vtable + 40, as the setter reads them
        base = MO.guest(m, m.long(m.long(inner) + 40), inner) & 0xFFFFFFFF
        m.write(base + 2 * kslot, struct.pack(">H", N + 0x100))
        m.flush()
        MO.guest(m, KIT_SETTER, kit, 115, N - 0x100, 0, 1, 0)
        kv = struct.unpack(">H", m.read(base + 2 * kslot, 2))[0]
        check("outside: the kit setter (delay WID) with no knob item: exactly as sent", kv == N - 0x100, f"{kv:#06x}")
    seen = []
    from unicorn import UC_HOOK_CODE

    def on_lock(uc, ad, sz, us):
        sp = uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_A7)
        seen.append(struct.unpack(">4I", bytes(uc.mem_read(sp + 4, 16)))[2])
    m.uc.hook_add(UC_HOOK_CODE, on_lock, begin=LOCK_SET_SND, end=LOCK_SET_SND)
    m.flush()
    MO.guest(m, sym["kn_lock_snd"], this, 71, N - 0x100, 0)
    check("outside: LOCK_SET (through kn_lock_snd) with no knob item: the lock exactly as sent",
          seen and seen[-1] == N - 0x100, f"{[hex(v) for v in seen]}")
    report["outside"] = {"idle": idle, "other": other, "ctrl": ctrl}


def scenario_unipolar(a, report, sym):
    from unicorn import UC_HOOK_CODE
    r = rig(a, sym, "unipolar")
    m, panel = r.m, r.panel
    panel.tap(AMP)
    panel.settle(20_000_000)
    slot = MO.record(m, 62)[1]                          # ATK
    r.put(slot, 0x4000)
    ins = []

    def on_hook(uc, ad, sz, us):                        # smp_quant_hook: d3 is what stock's step and setter computed
        ins.append((uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_D4),
                    uc.reg_read(__import__("unicorn").m68k_const.UC_M68K_REG_D3) & 0xFFFF))
    m.uc.hook_add(UC_HOOK_CODE, on_hook, begin=sym["smp_quant_hook"], end=sym["smp_quant_hook"])
    m.flush()
    c0, h0 = r.n("kn_catches"), r.n("kn_held")
    bad = []
    for d, n in ((-1, 12), (-2, 10), (+5, 6), (+12, 3), (-20, 3), (+30, 2), (-3, 8)):
        for _ in range(n):
            before = len(ins)
            r.feed(KNOB_A, d)
            got = [v for rid, v in ins[before:] if rid == 62]
            if got and r.word(slot) != got[-1]:
                bad.append((d, hex(got[-1]), hex(r.word(slot))))
    n62 = len([1 for rid, v in ins if rid == 62])
    check("unipolar: ATK turned at every speed: every value written is stock's own, no catch, no hold",
          not bad and n62 > 10 and r.n("kn_catches") == c0 and r.n("kn_held") == h0,
          f"{n62} writes, differing {bad[:5]}")
    report["unipolar"] = {"writes": n62}


def units_model(ds):
    """kn_units on records DS (one knob, no pause) -> total units"""
    rem, tot = 0, 0
    for d in ds:
        a = abs(d)
        if a >= POP_FAST:
            rem, tot = 0, tot + d * POP_MUL
            continue
        if a > POP_SLOW:
            rem, tot = 0, tot + d
            continue
        if (rem > 0 > d) or (rem < 0 < d):
            rem = 0
        rem += d
        u = int(rem / POP_DIV)
        rem -= u * POP_DIV
        tot += u
    return tot


def scenario_routes(a, report, sym):
    from emulib.panel import UP
    pr = MX.popup_rig(a, sym, "routes")
    if pr is None:
        return
    m, panel, k = pr.m, pr.panel, pr.k
    pr.open(300)                                        # (2026-11-19, plain-push: a plain push opens it, at its
    panel.settle(20_000_000)                            # release; FUNC + push is stock's)
    check("routes: a plain push on FREQ opens the routes popup", pr.visible() == 1)
    if pr.visible() != 1:
        return
    for _ in range(8):
        panel.tap(UP)                                   # LFO1 lit (first)
    fbuf = m.alloc(12)

    def lfo1():
        if pr.param(4) >> 8 == 67:
            n = MO.guest(m, sym["wish_get"], pr.snd, MX.LFO_TAG, fbuf, 12) & 0xFFFFFFFF
            return struct.unpack(">H", m.read(fbuf + 2, 2))[0] if n == 12 else pr.param(8)
        for x in pr.routes():
            if x[0] == 0 and x[1] == 67:
                return x[2] << 8 | x[3]
        return None

    def feed(d):
        m.pc = panel.panelin.encoder(m.m, panel.profile, k, d)
        panel.settle(GAP)
    for _ in range(6):                                  # slow: 1 a count records -> 1 unit every POP_DIV counts
        feed(+1)
    slow = lfo1()
    check(f"routes: 6 counts turned slowly (1 a record) make LFO1's route at +{6 // POP_DIV}",
          slow == N + 0x100 * units_model([1] * 6), f"{slow and hex(slow)}")
    for _ in range(4):                                  # medium (5 a record): 1 unit a count, up to +22
        feed(+5)
    mid = lfo1()
    check("routes: 4 records of 5 counts: 1 unit a count", mid == N + 0x100 * units_model([1] * 6 + [5] * 4),
          f"{mid and hex(mid)}")
    c0 = m.long(sym["kn_catches"])
    down = []
    for _ in range(12):
        feed(-5)
        down.append(lfo1())
        if down[-1] is None:
            break
    check("routes: turned down across 0: the route deleted there (its row empty), caught",
          down and down[-1] is None and m.long(sym["kn_catches"]) == c0 + 1, f"{[d and hex(d) for d in down]}")
    held = []
    for _ in range(HOLD):
        feed(-1)
        held.append(lfo1())
    after = []
    for _ in range(6):
        feed(-1)
        after.append(lfo1())
    check(f"routes: the next {HOLD} counts keep it at 0 (no route made), then it goes on below 0",
          held == [None] * HOLD and after[-1] is not None and after[-1] < N, f"{held}, then {after}")
    pr.quiet()
    for _ in range(6):                                  # up to the top end, fast (2 units a count)
        feed(+POP_FAST)
    top = lfo1()
    pr.quiet()
    pr.m.write(MO.FRAMES, struct.pack(">I", (m.long(MO.FRAMES) + 4000) & 0xFFFFFFFF))
    m.flush()
    down2 = []
    for _ in range(40):
        feed(-5)
        down2.append(lfo1())
        if down2[-1] is None:
            break
    check("routes: from the top end (0x7FFE) turned down: exactly 0, the route deleted",
          top == 0x7FFE and down2 and down2[-1] is None and all(d is None or d & 0xFF == 0 for d in down2),
          f"top {top and hex(top)}, {[d and hex(d) for d in down2[-4:]]}")
    report["routes"] = {"slow": slow, "mid": mid, "down": down, "top": top}


def scenario_dest(a, report, sym):
    from emulib.panel import YES
    import emu_destpop as DP
    r = DP.rig(a, sym, "dest")
    if not r.open():
        check("dest: D opens the DEST popup", False)
        return
    rows = r.rows()
    free = [e for e in rows if not any(x[1] == r.slot(e) for x in r.routes())]
    r.to_row(free[3] if len(free) > 3 else rows[-1])
    r.panel.tap(YES)
    e = r.rows()[r.state().lit]
    sl = r.slot(e)

    def dep():
        for x in r.routes():
            if x[0] & 0x7F == 0 and x[1] == sl:
                return x[2] << 8 | x[3]
        return None
    d0 = dep()
    vals = []
    for _ in range(20):
        r.m.pc = r.panel.panelin.encoder(r.m.m, r.panel.profile, DP.KNOB_D, -5)
        r.panel.settle(GAP)
        vals.append(dep())
        if vals[-1] is None:
            break
    check("dest: a route added at +32, turned down (5 counts a record): exactly 0 on the way, then deleted",
          d0 == 0x6000 and vals and vals[-1] is None and all(v is None or v & 0xFF == 0 for v in vals),
          f"{d0 and hex(d0)} -> {[v and hex(v) for v in vals]}")
    report["dest"] = {"vals": vals}


def scenario_env2(a, report, sym):
    import emu_destpop as DP
    r = DP.rig(a, sym, "env2", lfo=-1)
    m, panel = r.m, r.panel
    for _ in range(2):
        panel.tap(AMP)
        panel.settle(30_000_000)
    check("env2: ENV2's page up", MO.guest(m, sym["env2_visible"]) & 0xFF == 1)
    eb = m.alloc(16)

    def knob():
        n = MO.guest(m, sym["wish_get"], r.snd, MX.ENV_TAG, eb, 8) & 0xFFFFFFFF
        return 127 - (m.read(eb + 7, 1)[0] if n == 8 else 0)
    k0 = knob()
    vals = []
    for _ in range(40):
        m.pc = panel.panelin.encoder(m.m, panel.profile, KNOB_H, -5)
        panel.settle(GAP)
        vals.append(knob())
        if vals[-1] <= 64:
            break
    held = []
    for _ in range(HOLD):
        m.pc = panel.panelin.encoder(m.m, panel.profile, KNOB_H, -1)
        panel.settle(GAP)
        held.append(knob())
    check("env2: H (the attenuverter) from 127 (+100 %) turned down lands on exactly 64 (0 %), held there",
          k0 == 127 and vals and vals[-1] == 64 and held == [64] * HOLD, f"{vals}, held {held}")
    report["env2"] = {"vals": vals, "held": held}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--scenario", default="sound,fine,plock,outside,unipolar,routes,dest,env2")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    sym = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    report: dict = {"constants": K}
    run = {"sound": scenario_sound, "fine": scenario_fine, "plock": scenario_plock, "outside": scenario_outside,
           "unipolar": scenario_unipolar, "routes": scenario_routes, "dest": scenario_dest, "env2": scenario_env2}
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
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1, default=str))
    print("PASS" if not FAILS else f"FAIL: {len(FAILS)} checks: " + "; ".join(FAILS)[:600], flush=True)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
