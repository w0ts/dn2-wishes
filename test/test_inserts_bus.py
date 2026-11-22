"""The bus inserts FDN8 and XDLY per track (docs/inserts.md "On the track's bus"): the DSL program's
model against dnfw.inserts.busref, bit for bit, two slots a track, instances moving between slots; the
send FX's own words back as they were; tracks with no bus insert untouched; every register back."""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.fdn8 import program as FP
from dnfw.inserts import bus as B
from dnfw.inserts import busref as R
from dnfw.inserts import design as D
from dnfw.perc.dsl import Mem
from dnfw.xdly import program as XP


def fbits(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def load(m: Mem, at: int, blob: bytes) -> None:
    for k in range(0, len(blob), 4):
        m.put(at + k, struct.unpack_from("<I", blob, k)[0])


def mem0() -> Mem:
    m = Mem()
    load(m, FP.STATE, FP.state_bytes())
    load(m, XP.STATE, XP.state_bytes())
    load(m, B.STATE, B.state_bytes())
    return m


def rec(typ: int, inst: int, mix: int, *k: int) -> list[int]:
    return [typ | inst << D.TYPE_BITS, mix] + list(k) + [0] * (6 - len(k))


def table(rows: dict) -> bytes:
    """ROWS: (track, slot) -> record"""
    b = bytearray(8 * D.RECORDS)
    for (t, j), v in rows.items():
        b[8 * (2 * t + j):8 * (2 * t + j) + 8] = bytes(v)
    return bytes(b)


def call(m: Mem, par: bytes, left, right, regs):
    for k, v in enumerate(par):
        m.put(D.TABLE + 4 * k, v)
    for k, v in enumerate(D.flags(par)):                    # the pre pass's flags (perf, 2026-11-10)
        m.put(D.FLAGS + 4 * k, v)
    for t in range(D.TRACKS):
        for j in range(D.BLOCK):
            m.put(D.BUS_BLOCKS + 0x100 * t + 4 * j, fbits(left[t][j]))
            m.put(D.BUS_BLOCKS + 0x100 * t + D.BUS_R + 4 * j, fbits(right[t][j]))
    p = B.model(m, regs)
    lo = [[m.get(D.BUS_BLOCKS + 0x100 * t + 4 * j) for j in range(D.BLOCK)] for t in range(D.TRACKS)]
    ro = [[m.get(D.BUS_BLOCKS + 0x100 * t + D.BUS_R + 4 * j) for j in range(D.BLOCK)] for t in range(D.TRACKS)]
    return lo, ro, p


def send_words(m: Mem) -> list[int]:
    return ([m.get(FP.STATE + 4 * k) for k in range(FP.DYN_WORDS)]
            + [m.get(FP.ACT + 4 * k) for k in range(FP.NV)]
            + [m.get(XP.STATE + 4 * k) for k in range(XP.DYN_WORDS)])


def rows_at(b: int) -> dict:
    rows = {(0, 0): rec(D.FDN8, 0, 64, 10, 90, 30, 64, 0, 127),       # track 1: FDN8, half wet
            (1, 1): rec(D.XDLY, 1, 127, 20, 30, 100, 40, 90),          # track 2 slot 2: XDLY, wet only
            (2, 0): rec(D.FDN8, 1, 127, 0, 120, 60, 127, 30, 100),     # track 3: FDN8 then XDLY
            (2, 1): rec(D.XDLY, 0, 90, 5, 8, 127, 100, 60),
            (4, 0): rec(D.FUZZ, 0, 127, 127, 127, 127, 127, 127),      # a voice insert: not here
            (5, 1): rec(D.FDN8, 9, 127, 64, 64, 64, 64, 64, 64)}       # FULL (no instance 9): passes
    if b >= 45:
        rows[(0, 0)] = rec(D.FDN8, 0, 64, 10, 126, 90, 0, 0, 127)     # knobs moved (SIZE near freeze)
    if b >= 50:
        del rows[(2, 1)]                                               # XDLY 0 freed ...
        rows[(6, 0)] = rec(D.XDLY, 0, 127, 40, 40, 60, 0, 127)         # ... given to track 7: fresh
    return rows


def test_model_is_the_reference():
    rnd = random.Random(7)
    m, ref = mem0(), R.BusRef()
    regs = {k: rnd.getrandbits(32) for k in range(16)}
    send0 = send_words(m)
    for b in range(70):
        par = table(rows_at(b))
        loud = 0.0 if 60 <= b < 64 else 2.0
        left = [[rnd.uniform(-loud, loud) for _ in range(32)] for _ in range(16)]
        right = [[x * 0.7 for x in row] for row in left]
        wl = [[np.float32(x) for x in row] for row in left]
        wr = [[np.float32(x) for x in row] for row in right]
        ref.block(par, wl, wr)
        lo, ro, p = call(m, par, left, right, regs)
        assert lo == [[fbits(x) for x in row] for row in wl], f"block {b} left"
        assert ro == [[fbits(x) for x in row] for row in wr], f"block {b} right"
        assert all(p.r[k] == regs[k] for k in range(16)), f"block {b}: registers"
        assert send_words(m) == send0, f"block {b}: the send FX's words"
        for t in (3, 4, 5, 7, 15):                       # no bus insert (or FULL): untouched
            assert lo[t] == [fbits(np.float32(x)) for x in left[t]], f"block {b} track {t}"
    # the reverbs and delays did something once their rings were clear: their own DDR holds the sound
    assert lo[0] != [fbits(np.float32(x)) for x in left[0]]
    assert lo[1] != [fbits(np.float32(x)) for x in left[1]]
    ring0 = sum(1 for k in range(0, 4 * 40000, 4 * 7) if m.get(D.FDN8_RING_DDR + k))
    ring1 = sum(1 for k in range(0, 4 * 40000, 4 * 7) if m.get(D.FDN8_RING_DDR + D.FDN8_RING_STRIDE + k))
    line1 = sum(1 for k in range(0, 4 * 2400, 4) if m.get(D.XDLY_LINES_DDR + D.XDLY_LINES_STRIDE + k))
    assert ring0 > 100 and ring1 > 100 and line1 > 1000, (ring0, ring1, line1)
    assert not any(m.get(FP.RING + 4 * k) for k in range(0, 40000, 7))     # the send reverb's ring: untouched


def test_an_insert_that_went_away_and_came_back_starts_fresh():
    # 2026-11-14 (the User: "i heard some delay, long after"): a slot's FDN8 / XDLY switched to OFF or another type
    # and back gets the same instance again (the ColdFire gives the lowest free one); it used to resume its frozen
    # lines and replay the old tail. Now silent input after the return gives exact zeros. Track 1's away blocks with
    # no bus record at all (the pass does not walk), track 2's with another bus insert on (it walks, no claim)
    rnd = random.Random(5)
    m, ref = mem0(), R.BusRef()
    on = {(0, 0): rec(D.XDLY, 0, 127, 20, 30, 100, 0, 90), (1, 0): rec(D.FDN8, 0, 127, 10, 90, 30, 64, 0, 127)}
    played = [False, False]
    for b in range(260):
        if b < 160:
            rows = dict(on)
        elif b < 170:
            rows = {}                                              # all off: no walk
        elif b < 180:
            rows = {(0, 0): rec(D.DIST, 0, 127, 64), (3, 0): rec(D.XDLY, 1, 127, 64, 64, 64)}   # walk, no claim
        else:
            rows = dict(on)
        par = table(rows)
        loud = 1.0 if b < 160 else 0.0
        left = [[rnd.uniform(-loud, loud) for _ in range(32)] for _ in range(16)]
        right = [list(row) for row in left]
        wl = [[np.float32(x) for x in row] for row in left]
        wr = [[np.float32(x) for x in row] for row in right]
        ref.block(par, wl, wr)
        lo, ro, _ = call(m, par, left, right, {})
        assert lo == [[fbits(x) for x in row] for row in wl], f"block {b} left"
        assert ro == [[fbits(x) for x in row] for row in wr], f"block {b} right"
        if b < 170:                                                # (FDN8's wet: from block 126, its ring cleared)
            played = [played[0] or any(lo[0]), played[1] or any(lo[1])]
        if b == 179:
            assert played == [True, True], "both played (their tails through the away blocks too)"
        if b >= 180:
            assert not any(lo[0] + ro[0] + lo[1] + ro[1]), f"block {b}: an old tail came back"


def test_the_units_l1_scratch_holds_nothing_across_blocks():
    # 2026-11-12: a unit's scratch and the pass's own words are the Monomachine render scratch, which the voices
    # rewrite every block: with it full of garbage before every call, every block is still the reference's
    rnd = random.Random(11)
    m, ref = mem0(), R.BusRef()
    regs = {k: rnd.getrandbits(32) for k in range(16)}
    for b in range(56):
        for a in [*range(B.UNIT_L1, B.UNIT_L1_END, 4), *range(B.WORDS_L1, B.WORDS_L1_END, 4)]:
            m.put(a, rnd.getrandbits(32))
        par = table(rows_at(b))
        left = [[rnd.uniform(-1.0, 1.0) for _ in range(32)] for _ in range(16)]
        right = [[x * 0.5 for x in row] for row in left]
        wl = [[np.float32(x) for x in row] for row in left]
        wr = [[np.float32(x) for x in row] for row in right]
        ref.block(par, wl, wr)
        lo, ro, _ = call(m, par, left, right, regs)
        assert lo == [[fbits(x) for x in row] for row in wl], f"block {b} left"
        assert ro == [[fbits(x) for x in row] for row in wr], f"block {b} right"


def test_all_off_leaves_every_block():
    rnd = random.Random(2)
    m = mem0()
    left = [[rnd.uniform(-1, 1) for _ in range(32)] for _ in range(16)]
    right = [[rnd.uniform(-1, 1) for _ in range(32)] for _ in range(16)]
    lo, ro, _ = call(m, bytes(8 * D.RECORDS), left, right, {})
    assert lo == [[fbits(np.float32(x)) for x in r] for r in left]
    assert ro == [[fbits(np.float32(x)) for x in r] for r in right]


def test_layout():
    assert B.END <= D.BUS_STATE_END
    assert D.FDN8_RING_STRIDE >= 4 * FP.D.RING_WORDS and D.FDN8_RING_DDR % D.FDN8_RING_STRIDE == 0
    assert D.XDLY_LINES_STRIDE == 2 * 4 * XP.D.LINE


class _CountMem(Mem):
    """Mem counting accesses by region: L1, L2 (0x2000_0000..), DDR (0x8000_0000..)"""

    def __init__(self, base: Mem):
        super().__init__()
        self.w = dict(base.w)
        self.n = [0, 0, 0]

    def _count(self, a):
        a &= 0xFFFFFFFF
        self.n[2 if a >= 0x80000000 else 1 if 0x20000000 <= a < 0x20200000 else 0] += 1

    def get(self, a):
        self._count(a)
        return super().get(a)

    def put(self, a, v):
        self._count(a)
        super().put(a, v)


def test_the_guard_bound_covers_a_clearing_fdn8():
    # 2026-11-12: a fresh FDN8 instance's first blocks clear its ring (4,096 DDR writes a block; 1,264 since 2026-11-21,
    # its window only); its guard bound (design.COST) must cover that block on the shared scale with 20 % to spare
    from dnfw.fdn8 import ref as FR
    import dnfw.perc.dsl as DSL
    progs = []
    init = DSL.Prog.__init__

    def hook(self, *a, **k):
        init(self, *a, **k)
        progs.append(self)
    DSL.Prog.__init__ = hook
    try:
        noise = [[0.1 * ((t * 7 + j * 3) % 11 - 5) for j in range(D.BLOCK)] for t in range(D.TRACKS)]
        costs = []
        for rows in ({}, {(0, 0): rec(D.FDN8, 0, 64, 10, 90, 30, 64, 0, 127)}):
            m = _CountMem(mem0())
            progs.clear()
            call(m, table(rows), noise, noise, {r: 0 for r in range(16)})
            steps = sum(x.steps for x in progs)
            costs.append(steps + 4 * m.n[1] + 10 * m.n[2])
    finally:
        DSL.Prog.__init__ = init
    clearing = costs[1] - costs[0]
    assert m.n[2] >= FR.WIN[3]                               # a clearing block (HALF's window, fdn8.ref.WINDOW_CLEAR)
    assert abs(clearing - D.FDN8_MEASURED["clearing"]) <= 0.02 * clearing
    assert D.FDN8_COST_CLEAR >= 1.2 * clearing


def test_the_guard_bound_covers_a_steady_fdn8():
    # 2026-11-14 (the staged tank): the dearer instance's steady block (1, its diffusers in DDR), as the clearing test
    # measures, is FDN8_MEASURED's; the bound is 1.2 x the dearest steady block seen over every place of the ring
    # (2026-11-21: every bus instance's diffusers are in L2 now, instance 1 costs what instance 0 does)
    import dnfw.perc.dsl as DSL
    progs = []
    init = DSL.Prog.__init__

    def hook(self, *a, **k):
        init(self, *a, **k)
        progs.append(self)
    DSL.Prog.__init__ = hook
    try:
        noise = [[0.1 * ((t * 7 + j * 3) % 11 - 5) for j in range(D.BLOCK)] for t in range(D.TRACKS)]
        costs = []
        for rows in ({}, {(0, 0): rec(D.FDN8, 1, 64, 10, 90, 30, 64, 0, 127)}):
            m = _CountMem(mem0())
            for _ in range(41):
                m.n = [0, 0, 0]
                progs.clear()
                call(m, table(rows), noise, noise, {r: 0 for r in range(16)})
            costs.append(sum(x.steps for x in progs) + 4 * m.n[1] + 10 * m.n[2])
    finally:
        DSL.Prog.__init__ = init
    steady = costs[1] - costs[0]
    assert abs(steady - D.FDN8_MEASURED["steady"]) <= 0.02 * steady
    assert D.COST[D.FDN8] >= 1.2 * D.FDN8_STEADY_MAX >= 1.2 * steady


def test_the_fdn8_bound_is_the_clearing_one_only_while_it_clears():
    # 2026-11-12 (the unit's skips with 64,000 on every block): the bus pass charges a block the clearing bound
    # while the instance clears its ring (a new owner, then 32 blocks), the steady one after
    noise = [[0.1 * ((t * 7 + j * 3) % 11 - 5) for j in range(D.BLOCK)] for t in range(D.TRACKS)]
    m = mem0()
    rows = {(0, 0): rec(D.FDN8, 0, 64, 10, 90, 30, 64, 0, 127)}
    bounds = []
    for b in range(40):
        call(m, table(rows), noise, noise, {r: 0 for r in range(16)})
        bounds.append(m.get(B.C["bnd"]))
    assert bounds[:32] == [D.FDN8_COST_CLEAR] * 32 and bounds[33:] == [D.COST[D.FDN8]] * 7, bounds
    rows = {(0, 0): rec(D.FDN8, 0, 64, 10, 90, 30, 64, 0, 127), (1, 0): rec(D.FDN8, 0, 64, 10, 90, 30, 64, 0, 127)}
    call(m, table({(1, 0): rows[(1, 0)]}), noise, noise, {r: 0 for r in range(16)})
    assert m.get(B.C["bnd"]) == D.FDN8_COST_CLEAR                 # the instance to another track: a new owner


def test_a_refused_bus_insert_fades_out_stays_out_and_fades_back():
    # 2026-11-12 (perc.guard.ins_gate with grace, bus.blend's MIX x g; opt-host's ins_fade): an XDLY refused within
    # P/16 past the deadline runs once more, fading to the dry over that block; it stays out INS_HOLD blocks (the
    # track's block untouched) and comes back fading in. Refused past the grace, it is out at once
    import math
    from dnfw.perc import guard as G
    rows = {(0, 0): rec(D.XDLY, 0, 127, 20, 30, 100, 40, 90)}

    def fval(w):
        return np.float32(struct.unpack("<f", struct.pack("<I", w & 0xFFFFFFFF))[0])

    def play(clk_at):
        m, out = mem0(), []
        m.put(G.INS_DLP, 100_000)
        m.put(G.PERIOD, 666_667)
        for b in range(100):
            m.put(G.INS_TESTCLK, clk_at.get(b, 0))
            ph = [2 * math.pi * 220 * (32 * b + j) / D.FS for j in range(32)]
            left = [[0.0] * 32 for _ in range(16)]
            left[0] = [0.3 * math.sin(x) for x in ph]
            lo, ro, _ = call(m, table(rows), left, left, {r: 0 for r in range(16)})
            out.append(([fval(w) for w in lo[0]], [np.float32(x) for x in left[0]]))
        return m, out
    m, got = play({20: 90_000})                  # 110,000 > 100,000, within 100,000 + 41,666: faded
    _, always = play({})
    back = 20 + G.INS_HOLD
    assert got[:20] == always[:20]
    assert got[20][0] != got[20][1] and got[20][0][31] == got[20][1][31]   # it ran, and ends on the dry
    for b in range(21, back):
        assert got[b][0] == got[b][1], b          # out: the track's block as it came
    assert got[back][0] != got[back][1]           # back
    assert abs(float(got[back][0][0] - got[back][1][0])) < 0.1 * abs(float(always[back][0][0] - always[back][1][0])) + 1e-6
    assert m.get(G.INS_SKIPS) == back - 20
    m2, hard = play({20: 200_000})               # past the grace: out at once
    assert hard[20][0] == hard[20][1] and m2.get(G.INS_SKIPS) == back - 20


def test_a_held_out_bus_insert_comes_back_from_silence():
    # 2026-11-14 (the User: "start fresh"): an XDLY refused at block 20 and held out INS_HOLD blocks comes back as a
    # new engine (its lines unread), not resuming the lines it froze with: silent input after, exact zeros
    from dnfw.perc import guard as G
    rows = {(0, 0): rec(D.XDLY, 0, 127, 20, 30, 100, 0, 90)}
    rnd = random.Random(4)
    m = mem0()
    m.put(G.INS_DLP, 100_000)
    m.put(G.PERIOD, 666_667)
    back = 20 + G.INS_HOLD
    for b in range(back + 20):
        m.put(G.INS_TESTCLK, 200_000 if b == 20 else 0)
        loud = 1.0 if b < 20 else 0.0
        left = [[0.0] * 32 for _ in range(16)]
        left[0] = [rnd.uniform(-loud, loud) for _ in range(32)]
        lo, ro, _ = call(m, table(rows), left, [list(x) for x in left], {})
        if b == 19:
            assert any(lo[0]), "it played"
        if b >= back:
            assert not any(lo[0] + ro[0]), (b, "the frozen lines came back")
    assert m.get(G.INS_SKIPS) == G.INS_HOLD
