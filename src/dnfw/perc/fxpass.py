"""(perf, 2026-11-21, filt-opt) The Machinedrum's track effects (perc.program.fx) as one pass per effect over the
block: AM, then the EQ, the high pass, the low pass, each a loop of its own with its words in registers.

Bit for bit the per-sample chain it replaces: every effect is a filter on its own input sequence, so running AM over
the 32 samples, then the EQ over AM's output, and so on gives every sample the same operations on the same values
as AM, EQ, HP, LP sample by sample. Each pass does the operations of machines.sin_ / svf_tick in the same order (an
operand order may differ only in a multiply or an add, which are the same IEEE operation either way); the states go
back to their words after the pass (their last values, as the chain left them), C fxy holds the block's last sample
and I4 ends past the block, C count at 0, as before. Which effects run is chosen once a block, as before (each its control); at
the worst case (all four on) nothing is skipped.

The SVF passes are scheduled (dnfw.mnm.sched) with registers chosen so the multiplies and adds pair in the
multifunction form (F0-F3 x F4-F7 with F8-F11 +- F12-F15; dnfw.perc.mf.verify's proven forms).
"""

from __future__ import annotations

from . import machines as M
from .dsl import Prog

CNT = 11                                         # the passes' loop count (no data in R11)


def _buf(p: Prog, L: M.Layout) -> None:
    p.ld(0, L.C["buf"])
    p.seti(0, 0)


def am(p: Prog, L: M.Layout) -> None:
    """y = x (1 - amd (0.5 - 0.5 sin(2 pi ph))), ph += amdt a sample (wrapped by frac), machines.sin_'s table read"""
    C = L.C
    p.ld(4, C["amdt"])
    p.ld(5, C["amd"])
    M.v(p, 6, "amph")
    p.fconst(7, 256.0)
    p.iconst(8, 0)                               # +0.0 (interp's MAX against R12 = 0)
    p.fconst(9, 256.0 - 0.001)
    p.fconst(10, 0.5)
    p.fconst(13, 1.0)
    p.iconst(14, L.sin)
    _buf(p, L)

    def one():
        p.fop(6, 6, "+", 4)
        p.trunc(0, 6)                            # frac
        p.float0(1, 0)
        p.if_(6, "LT", 1, lambda: p.fop(1, 1, "-", 13))
        p.fop(6, 6, "-", 1)
        p.fop(15, 6, "*", 7)                     # interp: x 256, in 0 .. 256 - 0.001
        p.fop(15, 15, "MAX", 8)
        p.fop(15, 15, "MIN", 9)
        p.trunc(0, 15)
        p.float0(1, 0)
        p.lsh(0, 0, 2)
        p.iop(0, 14, "+", 0)
        p.seti(1, 0)
        p.ldi(2, 0, 1)
        p.fop(1, 15, "-", 1)
        p.ldi(3, 1, 1)
        p.fop(3, 3, "-", 2)
        p.fop(3, 1, "*", 3)
        p.fop(15, 2, "+", 3)                     # sin
        p.fop(15, 15, "*", 10)
        p.fop(15, 10, "-", 15)                   # 0.5 - 0.5 sin
        p.fop(15, 5, "*", 15)
        p.fop(15, 13, "-", 15)
        p.ldi(12, 0, 0)
        p.fop(12, 12, "*", 15)
        p.stpost(0, 12)
    p.loop_r(CNT, 32, one, one=CNT)          # (DEC: no register but the count)
    M.vs(p, "amph", 6)


def _svf(p: Prog, L: M.Layout, which: int, kind: str) -> None:
    """svf_tick(f{which}) over the block: KIND "eq" (y = x + eqm v1), "hp" (y = x - k v1 - v2), "lp" (y = v2).
    Registers: ic1 F0, v3 F1, v1 F2, a1-a3 F4-F6, eqm / k F7, x F8, ic2 F12 (the multifunction groups)"""
    from ..mnm.sched import Sched
    C = L.C
    pre, a, b = f"s{which}", f"f{which}a", f"f{which}b"
    _buf(p, L)
    M.v(p, 0, a)
    M.v(p, 12, b)
    M.c(p, L, 4, f"{pre}a1")
    M.c(p, L, 5, f"{pre}a2")
    M.c(p, L, 6, f"{pre}a3")
    if kind == "eq":
        p.ld(7, C["eqm"])
    elif kind == "hp":
        M.c(p, L, 7, f"{pre}k")

    def one():
        s = Sched()
        s.ld(8, 0, 0)                            # x
        s.sub(1, 8, 12)                          # v3 = x - ic2
        s.mul(9, 0, 5)                           # a2 ic1
        s.add(9, 9, 12)                          # ic2 + a2 ic1
        s.mul(10, 0, 4)                          # a1 ic1
        s.mul(13, 1, 5)                          # a2 v3
        s.add(2, 10, 13)                         # v1
        s.mul(15, 1, 6)                          # a3 v3
        s.add(14, 9, 15)                         # v2 (low pass)
        s.add(3, 2, 2)
        s.sub(0, 3, 0)                           # ic1 = 2 v1 - ic1
        s.add(10, 14, 14)
        s.sub(12, 10, 12)                        # ic2 = 2 v2 - ic2
        if kind == "eq":
            s.mul(13, 2, 7)                      # eqm v1
            s.add(9, 8, 13)
            y = 9
        elif kind == "hp":
            s.mul(13, 2, 7)                      # k v1
            s.sub(9, 8, 13)
            s.sub(9, 9, 14)                      # x - k v1 - v2
            y = 9
        else:
            y = 14
        s.emit(p)
        p.stpost(0, y)
    p.loop_r(CNT, 32, one, one=CNT)          # (DEC: no register but the count)
    M.vs(p, a, 0)
    M.vs(p, b, 12)


def run(p: Prog, L: M.Layout) -> None:
    """the passes, each when its flag (C fxam, fxeq, fxhp, fxlp) is set; then C fxy and I4 as the chain left them"""
    C = L.C
    for flag, body in (("fxam", lambda: am(p, L)), ("fxeq", lambda: _svf(p, L, 3, "eq")),
                       ("fxhp", lambda: _svf(p, L, 4, "hp")), ("fxlp", lambda: _svf(p, L, 5, "lp"))):
        p.ld(5, C[flag])
        p.ifz(5, "NE", body)
    p.ld(0, C["buf"])
    p.iconst(12, 4 * 32)
    p.iop(0, 12, "+", 0)
    p.seti(4, 0)
    p.ldi(0, -1, 4)
    p.st(C["fxy"], 0)
    p.iconst(0, 0)
    p.st(C["count"], 0)                          # the chain's loop count word ended at 0: every word as before
