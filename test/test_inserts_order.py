"""Slot order across the passes (2026-11-11, the User: "DSP: always run in slot order"; design.MOVERS): a
slot 1 of CHOR, WIDE, FDN8 or XDLY with a slot 2 of a voice insert (design.BUILT) moves slot 2 to the bus
pass, after slot 1, on the track's L and R. The pre pass leaves it out (its model against dnfw.inserts.ref);
the bus pass runs it (its model against dnfw.inserts.busref), bit for bit; every other pair as before."""

from __future__ import annotations

import random

import numpy as np

from dnfw.inserts import busref as BR
from dnfw.inserts import design as D
from dnfw.inserts import program as P
from dnfw.inserts import ref as R

from . import test_inserts as TI
from . import test_inserts_bus as TB

FUZZ = [D.FUZZ, 127, 90, 70, 20, 40, 0, 100]
DIST = [D.DIST, 127, 127, 127, 127, 127, 127, 0]
TAPE = [D.TAPE, 127, 80, 100, 90, 100, 60, 40]
SUB = [D.SUB, 127, 100, 85, 59, 0, 127, 0]
HARM = [D.HARM, 127, 50, 70, 64, 80, 100, 0]
GATER = [D.GATER, 127, 127, 16, 64, 20, 0, 0]
FOLD = [D.FOLD, 90, 100, 60, 64, 90, 110, 0]
CHOR = [D.CHOR, 127, 64, 64, 64, 64, 64, 0]
WIDE = [D.WIDE, 127, 64, 64, 64, 64, 64, 64]
FDN8 = TB.rec(D.FDN8, 0, 64, 10, 90, 30, 64, 0, 127)
XDLY = TB.rec(D.XDLY, 1, 127, 20, 30, 100, 40, 90)


def rows_at(b: int) -> dict:
    """(track, slot) -> record: every kind of pair"""
    rows = {(0, 0): FDN8, (0, 1): DIST,                      # bus | voice: moved
            (1, 0): XDLY, (1, 1): TAPE,                      # bus | TAPE: moved, its own rings
            (2, 0): CHOR, (2, 1): SUB,                       # post | voice: moved (no bus unit on the track)
            (3, 0): WIDE, (3, 1): GATER,                     # post | GATER: moved (the clock word)
            (4, 0): DIST, (4, 1): HARM,                      # voice | voice: the pre pass, slot order
            (5, 0): FUZZ, (5, 1): TB.rec(D.XDLY, 2, 127, 20, 30, 100, 40, 90),                    # voice | bus: as before
            (6, 0): TB.rec(D.FDN8, 1, 127, 0, 120, 60, 127, 30, 100),
            (6, 1): TB.rec(D.XDLY, 0, 90, 5, 8, 127, 100, 60),   # bus | bus: as before
            (7, 0): [D.OFF, 127, 0, 0, 0, 0, 0, 0], (7, 1): FOLD,  # OFF | voice: the pre pass
            (8, 0): TB.rec(D.FDN8, 2, 127, 64, 64, 64, 64, 64, 64), (8, 1): CHOR}  # bus | post
    if b >= 20:
        rows[(1, 1)] = HARM                                   # the moved type switched: fresh
    if b >= 30:
        rows[(1, 1)] = TAPE                                   # and back: the ring cleared again
        rows[(0, 0)] = [D.OFF, 127, 0, 0, 0, 0, 0, 0]          # slot 1 OFF: DIST back in the pre pass
    return rows


def test_moved_pairs():
    assert D.moved(TB.table(rows_at(0)), 0) and not D.moved(TB.table(rows_at(0)), 4)
    assert [t for t in range(D.TRACKS) if D.moved(TB.table(rows_at(0)), t)] == [0, 1, 2, 3]
    assert D.flags(TB.table({(2, 0): CHOR, (2, 1): SUB})) == [1, 1, 1]      # the bus pass must walk
    assert D.flags(TB.table({(2, 0): CHOR, (2, 1): CHOR})) == [0, 1, 0]


def test_pre_pass_leaves_moved_out():
    """the pre pass's model against the reference: tracks 0..3's slot 2 is not run here, slot 1 neither
    (a post or bus type), so their voices pass untouched while the pair is moved"""
    rnd = random.Random(5)
    m, r = TI.mem0(), R.Ref()
    for b in range(40):
        par = TB.table(rows_at(b))
        bufs = [[rnd.uniform(-0.8, 0.8) for _ in range(32)] for _ in range(16)]
        want = [[np.float32(x) for x in buf] for buf in bufs]
        r.block(par, want)
        got = TI.call(m, par, bufs)
        assert got == [[TI.fbits(x) for x in w] for w in want], f"block {b}"
        for t in (1, 2, 3):
            assert got[t] == [TI.fbits(np.float32(x)) for x in bufs[t]], f"block {b} track {t}"
        dry0 = [TI.fbits(np.float32(x)) for x in bufs[0]]
        assert (got[0] == dry0) == (b < 30), f"block {b}: DIST on track 1 only once slot 1 is OFF"
        assert got[4] != [TI.fbits(np.float32(x)) for x in bufs[4]]


def test_bus_pass_runs_moved_after_slot_1():
    rnd = random.Random(9)
    m, ref = TB.mem0(), BR.BusRef()
    TB.load(m, P.STATE, P.state_bytes())                     # GATER's tables (the pre pass's state)
    regs = {k: rnd.getrandbits(32) for k in range(16)}
    for b in range(40):
        par = TB.table(rows_at(b))
        left = [[rnd.uniform(-2.0, 2.0) for _ in range(32)] for _ in range(16)]
        right = [[x * 0.7 for x in row] for row in left]
        wl = [[np.float32(x) for x in row] for row in left]
        wr = [[np.float32(x) for x in row] for row in right]
        ref.block(par, wl, wr)
        lo, ro, p = TB.call(m, par, left, right, regs)
        assert lo == [[TI.fbits(x) for x in row] for row in wl], f"block {b} left"
        assert ro == [[TI.fbits(x) for x in row] for row in wr], f"block {b} right"
        assert all(p.r[k] == regs[k] for k in range(16)), f"block {b}: registers"
        for t in (4, 7, 9, 15):                              # nothing on the bus: untouched
            assert lo[t] == [TI.fbits(np.float32(x)) for x in left[t]], f"block {b} track {t}"
        for t in (2, 3):                                     # post | voice: only the moved insert here
            assert lo[t] != [TI.fbits(np.float32(x)) for x in left[t]], f"block {b} track {t}"


def test_moved_order_is_slot_order():
    """the bus model with XDLY | DIST on track 1 equals XDLY alone, then DIST (the voice insert's reference)
    on that result x G_IN, x G_OUT back: slot 1 first, bit for bit"""
    from dnfw.inserts import bus as B
    rnd = random.Random(1)
    m, xd, dist = TB.mem0(), BR.BusRef(), R.Ref()
    TB.load(m, P.STATE, P.state_bytes())
    for b in range(12):
        left = [[rnd.uniform(-2.0, 2.0) for _ in range(32)] for _ in range(16)]
        right = [[x * 0.5 for x in row] for row in left]
        wl = [[np.float32(x) for x in row] for row in left]
        wr = [[np.float32(x) for x in row] for row in right]
        xd.block(TB.table({(0, 0): XDLY}), wl, wr)          # slot 1 alone ...
        for k, buf in ((0, wl[0]), (1, wr[0])):              # ... then slot 2 on what it left
            x = [np.float32(s) * np.float32(B.G_IN) for s in buf]
            dist.one(k, 0, bytes(DIST), x)
            buf[:] = [np.float32(s) * np.float32(B.G_OUT) for s in x]
        lo, ro, _ = TB.call(m, TB.table({(0, 0): XDLY, (0, 1): DIST}), left, right, {})
        assert lo[0] == [TI.fbits(x) for x in wl[0]] and ro[0] == [TI.fbits(x) for x in wr[0]], f"block {b}"


def test_layout():
    from dnfw.inserts import bus as B
    assert B.MV_END <= D.BUS_STATE_END
    assert D.MV_RING_DDR + D.MV_INSTANCES * 4 * D.TP_RING <= 0x82600000     # dnfw.mnm.plk.BIG_DDR
