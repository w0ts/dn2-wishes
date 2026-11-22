"""DRUM's arithmetic in the DSL (dnfw.perc.dsl): state words, constants, e^x for x <= 0, log2, the LCG, and the
drive's soft clip with first-order antiderivative anti-aliasing (ADAA). Leaf subroutines (`p.call`), one copy each.

Every helper names the registers it clobbers. R12 is the DSL's scratch (mulk / addk / clamp use it).
"""

from __future__ import annotations

import math

from ...mnm import core as C
from ...perc import machines as PM
from ...perc.dsl import Prog
from ..plaits import plk as K

LOG2E = 1.0 / math.log(2.0)
LN2 = math.log(2.0)
SERIES_TOP = -0.125                          # e^x by its series above this, by exp2p below
# log2 on the mantissa m in 1..2 as a polynomial in t = m - 1, degree 8 (Chebyshev fit, float32 coefficients,
# highest first; 1.7e-7 off log2 evaluated in float32): no reciprocal
LOG2_POLY = (-0.008874696679413319, 0.05027750879526138, -0.13453425467014313, 0.2392316609621048,
             -0.34599602222442627, 0.4783235490322113, -0.7211146354675293, 1.4426867961883545,
             4.886357629629856e-08)


def ld(p: Prog, d: int, k: int) -> None:
    """Rd = state word k (0..95)"""
    C.st(p, d, k)


def sv(p: Prog, k: int, s: int) -> None:
    C.sts(p, k, s)


mulk, addk, clamp = K.mulk, K.addk, K.clamp


def on_hit(p: Prog, fn) -> None:
    """2026-11-21 (live knobs): FN only in a hit (S_TRIG, word 0, set), not when drum.half runs the same hit code
    with S_TRIG 0 on the voice's turn (the hit's values re-read: what FN sets is the hit's state, kept). Clobbers R0
    before FN."""
    ld(p, 0, 0)
    p.ifz(0, "NE", fn)


def balance_inline(p: Prog, d1: int, d2: int, x: int) -> None:
    """a balance knob's gains (ref.balance): Fd1 = min(1, (1 - Fx) 127/63), Fd2 = min(1, Fx 127/64). d1, d2, x
    distinct, not R12. Clobbers R12."""
    from . import ref as R
    p.fconst(12, 1.0)
    p.fop(d1, 12, "-", x)
    mulk(p, d1, d1, R.BAL_L)
    p.fconst(12, 1.0)
    p.fop(d1, d1, "MIN", 12)
    mulk(p, d2, x, R.BAL_R)
    p.fconst(12, 1.0)
    p.fop(d2, d2, "MIN", 12)


def balance(p: Prog, d1: int, d2: int, x: int) -> None:
    """balance_inline as one copy (2026-11-21, DSP room): F13 in, F14 / F15 out, moved to Fd1 / Fd2. d1, d2, x
    distinct, not R12. Clobbers R12-R15, I12 (and Fx kept unless it is R14 or R15)."""
    if x != 13:
        p.fpass(13, x)
    p.call("dr_bal", lambda: balance_inline(p, 14, 15, 13))
    if d1 != 14:
        p.fpass(d1, 14)
    if d2 != 15:
        p.fpass(d2, 15)


def declick_on(p: Prog) -> None:
    """the hit's last act on every type (2026-11-21, DSP room: one copy): the declick from the last sample if a
    sound was on (S_DK = S_LAST), then the sound on. Clobbers R0, R1, R12, I12."""
    from . import kick as KI

    def body():
        ld(p, 0, KI.S_ON)
        p.ifz(0, "NE", lambda: (ld(p, 1, KI.S_LAST), sv(p, KI.S_DK, 1)))
        p.iconst(0, 1)
        sv(p, KI.S_ON, 0)
    if p.in_sub:
        p.tail("dr_dkon", body)
    else:
        p.call("dr_dkon", body)


def exp_neg(p: Prog) -> None:
    """F14 = e^F15 for F15 <= 0: 1 + x (1 + x (1/2 + x (1/6 + x / 24))) above SERIES_TOP (|error| < 2.6e-7
    there: the decays' coefficients near 1 keep their last bits), 2^(x log2 e) by plk.exp2p below.
    Clobbers R0, R1, R12, R13, I12."""
    p.call("dr_exp", lambda: exp_neg_body(p))


def exp_neg_body(p: Prog) -> None:
    """exp_neg's subroutine (2026-11-20: kick._coef's tail-jumps to it too)"""
    def series():
        p.fconst(14, 1.0 / 24.0)
        p.fop(14, 14, "*", 15)
        addk(p, 14, 14, 1.0 / 6.0)
        p.fop(14, 14, "*", 15)
        addk(p, 14, 14, 0.5)
        p.fop(14, 14, "*", 15)
        addk(p, 14, 14, 1.0)
        p.fop(14, 14, "*", 15)
        addk(p, 14, 14, 1.0)

    def power():                             # (2026-11-20: exp2's one copy, its return this one's)
        mulk(p, 13, 15, LOG2E)
        p.tail("dr_exp2", lambda: K.exp2p(p, 14, 13))
    p.fconst(13, SERIES_TOP)
    p.if_(15, "GT", 13, series, power)


def exp2(p: Prog, d: int, x: int) -> None:
    """Fd = 2^Fx: plk.exp2p, one copy (a leaf subroutine; 2026-11-20, the DSP upload's room: each inline copy of the
    hits' was ~170 B of PERC). d is not x. Clobbers R0, R1, R12-R14, I12 (Fx kept unless x is 13)."""
    if x != 13:
        p.fpass(13, x)
    p.call("dr_exp2", lambda: K.exp2p(p, 14, 13))
    if d != 14:
        p.fpass(d, 14)


def log2_inline(p: Prog) -> None:
    """F9 = log2(F8), F8 > 0 and finite: the exponent, and LOG2_POLY on the mantissa. Inline (a subroutine's
    body may use it). Clobbers R8-R12."""
    p.lsh(10, 8, -23)
    p.iconst(12, -127)
    p.iop(10, 12, "+", 10)                       # e
    p.iconst(12, 0)
    p.float_(10, 10, 12)
    p.iconst(12, 0x7FFFFF)
    p.iop(11, 8, "AND", 12)
    p.iconst(12, 0x3F800000)
    p.iop(11, 11, "OR", 12)                      # m, 1..2
    addk(p, 11, 11, -1.0)                        # t
    p.fconst(9, LOG2_POLY[0])
    for c in LOG2_POLY[1:]:
        p.fop(9, 9, "*", 11)
        addk(p, 9, 9, c)
    p.fop(9, 9, "+", 10)


def log2(p: Prog) -> None:
    """F9 = log2(F8) (log2_inline, one copy). Clobbers R8-R12, I12."""
    p.call("dr_log2", lambda: log2_inline(p))


def noise(p: Prog, d: int, s_rng: int) -> None:
    """Fd = Plaits' LCG, a signed sample: int32(word) / 2^31 (state word S_RNG). Clobbers R12-R14."""
    ld(p, 13, s_rng)
    p.iconst(14, 1664525)
    p.mul_ssi(13, 13, 14)
    p.iconst(14, 1013904223)
    p.iop(13, 13, "+", 14)
    sv(p, s_rng, 13)
    p.iconst(12, -31)
    p.float_(d, 13, 12)


SOFT_F3 = 0.5 + 4.0 / 3.0 * math.log(12.0)
SOFT_F0 = 4.0 / 3.0 * math.log(3.0)           # the antiderivative at 0 (a voice's first ADAA state)


def soft_antider(p: Prog, t_u: int, t_v: int) -> None:
    """F9 = SoftClip's antiderivative at F15: v^2 / 18 + 4/3 ln(3 + v^2) + max(|u| - 3, 0), v = clamp(u, -3, 3).
    State words T_U, T_V hold u and v^2 / 18 across log2. Clobbers R8-R15 (F15 = u again at the end), I12."""
    def body():
        sv(p, t_u, 15)
        p.fpass(8, 15)
        clamp(p, 8, -3.0, 3.0)
        p.fop(8, 8, "*", 8)                      # v^2
        mulk(p, 9, 8, 1.0 / 18.0)
        sv(p, t_v, 9)
        addk(p, 8, 8, 3.0)
        log2_inline(p)                           # F9 = log2(3 + v^2)
        mulk(p, 9, 9, 4.0 / 3.0 * LN2)
        ld(p, 14, t_v)
        p.fop(9, 14, "+", 9)
        ld(p, 15, t_u)
        K.fabs(p, 13, 15)
        addk(p, 13, 13, -3.0)
        p.fconst(12, 0.0)
        p.fop(13, 13, "MAX", 12)
        p.fop(9, 9, "+", 13)
        from ...perc import program as PP        # 2026-11-20 (clip-inner): |u| past 3, where the curve is flat: the
        PP.clip_flag(p, 13, "GT", 12, 13)        # voice's clip (a drive's hard clip; F13 = |u| - 3 > 0, nonzero)
    p.call("dr_softF", body)
