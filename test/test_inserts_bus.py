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
    # 2026-11-12: a fresh FDN8 instance's first blocks clear its ring (4,096 DDR writes a block); its guard
    # bound (design.COST) must cover that block on the shared scale with 20 % to spare
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
    assert m.n[2] >= 4096                                    # it is a clearing block
    assert abs(clearing - D.FDN8_MEASURED["clearing"]) <= 0.02 * clearing
    assert D.COST[D.FDN8] >= 1.2 * clearing
