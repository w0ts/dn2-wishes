"""(perf, 2026-11-12) TB303's sample, scheduled: the same operations on the same operands as dnfw.mnm.tb303's
_sample runs them one at a time (bit for bit its output), packed by dnfw.mnm.vsched into multifunction
instructions with a memory move each, the constants read from a table in L1 (KTAB) by those moves, the branches
that can be conditional computes made so.

A sample is four straight-line regions and the branches between them:
  R0  the slew and (only when the frequency changed) the increments: plain code, as before;
  A   the envelopes, the cutoff and the ladder's coefficients, the amplitude, and the four oversampled
      oscillator samples' saw parts (the phase, the saw, its blend and DC);
  S   (WAVE above 0) the square: its drive, the tanh at its clamps as conditional constants, the rare middle
      through _tanh as before, then its term and its BLEP into each sample;
  B   the saw's BLEP, the negation, the 44.5 Hz high-pass, the ladder, the decimator and the output chain.
The ladder's and the filters' states go through their slot words between oversampled samples (a move each, no
registers held), so every region starts and ends with nothing in a register.
"""

from __future__ import annotations

from . import core as C
from . import tb303 as T
from .vsched import VS, KTab
from ..perc.dsl import Prog, bits, f32

# the slot's words past I0's reach (64..95), at I2 (= the slot's word SLOT_HI, offsets -32..-1)
SLOT_HI = 96
T_X = 64                                         # the four oversampled phases (floats)
T_V = 68                                         # the square's four drives
T_T = 72                                         # their tanh
T_I3 = 76                                        # I3 kept across the loop
# the constants' table: 128 words in L1 at KTAB_AT (a placeholder for the model: the integrator places it,
# dnfw.waverider.dsp, and fills it from ktab_words), I1 at its word 32 and I3 at its word 96
KTAB_AT = 0x2E6100                               # = dnfw.waverider.dsp.TB303_KTAB_DM (the arbiter's claim, 2026-11-12)
KTAB_N = 128
WINDOWS = {1: 32, 3: 96}
_KT: dict = {}
DBL_MUL = True                                   # x + x as x * 2.0 (exact, the same bits) where the multiplier is freer
SPLIT_B = True                                   # region B in two (the ladder part; the decimator and output chain)
WINDOW = 96                                      # the scheduler's window (ops)


def _collect(L: C.Layout) -> KTab:
    """the table: every constant the half asks for (emit mode runs every branch), the most asked for first"""
    import collections

    class Count(KTab):
        def __init__(self):
            super().__init__({})
            self.n: collections.Counter = collections.Counter()

        def at(self, w):
            self.n[w] += 1
            return None
    kt = Count()
    _KT["collect"] = kt
    try:
        q = Prog("emit")
        q.i[3] = 0
        T.half(q, L)
    finally:
        del _KT["collect"]
    out = KTab(WINDOWS)
    for w, _n in kt.n.most_common(KTAB_N):
        out.at(w)
    assert len(out.words) <= KTAB_N
    out.frozen = True
    out.asked = len(kt.n)
    return out


def ktab(L: C.Layout) -> KTab:
    if "collect" in _KT:
        return _KT["collect"]
    key = L.perc.T["exp2"]                       # the table is the same for every layout with the same exp2 table
    if key not in _KT:
        _KT[key] = _collect(L)
    return _KT[key]


def ktab_words(L: C.Layout) -> list[int]:
    """the table's words, for whoever fills it (the model: dnfw.perc.live's harness callers)"""
    return list(ktab(L).words)


# -- the lone instructions -------------------------------------------------------------------
def _trunc(p, d, a):
    p.trunc(d, a)


def _float0(p, d, a):
    p.float0(d, a)


def _float_by(p, d, a, s):
    p.float_(d, a, s)


def _lsh23(p, d, a):
    p.lsh(d, a, 23)


def _iadd(p, d, a, b):
    p.iop(d, a, "+", b)


def _stpost4(p, a):
    p.stpost(4, a)


I8 = {0: list(range(8, 16))}                     # an integer add's first operand (G5)


class Gen:
    """the operations of one region"""

    def __init__(self, p: Prog, L: C.Layout):
        self.p, self.L = p, L
        self.s = VS(p, ktab=ktab(L), window=WINDOW)
        self.held: dict[int, int] = {}

    def k(self, x: float) -> int:
        return self.s.k(x)

    def kh(self, x: float) -> int:
        """a constant held in a register for its uses within the scope (one load)"""
        w = bits(f32(x))
        if w not in self.held:
            self.held[w] = self.s.k(x)
        return self.held[w]

    def hold(self, *xs: float) -> None:
        """constants held across every scope of the region"""
        self.region_held = {bits(f32(x)) for x in xs}
        for x in xs:
            self.kh(x)

    def scope(self) -> None:
        keep = getattr(self, "region_held", set())
        self.held = {w: v for w, v in self.held.items() if w in keep}

    def ki(self, n: int) -> int:
        return self.s.ki(n)

    def ld(self, w: int) -> int:
        return self.s.ld(0, w - T.S_MID) if w < 64 else self.s.ld(2, w - SLOT_HI)

    def st(self, w: int, v: int) -> None:
        if w < 64:
            self.s.st(0, w - T.S_MID, v)
        else:
            self.s.st(2, w - SLOT_HI, v)

    def f(self, op, a, b):
        return self.s.f(op, a, b)

    def mul(self, a, b):
        return self.s.f("*", a, b)

    def add(self, a, b):
        return self.s.f("+", a, b)

    def sub(self, a, b):
        return self.s.f("-", a, b)

    def mulk(self, a, x):
        return self.s.f("*", a, self.kh(x))

    def addk(self, a, x):
        return self.s.f("+", a, self.kh(x))

    def dbl(self, a):
        """a + a (as x * 2.0 when DBL_MUL: the same bits)"""
        return self.mulk(a, 2.0) if DBL_MUL else self.add(a, a)

    def emit(self, key: str | None = None) -> dict:
        self.s.emit(key)
        return self.s.stats

    # -- pieces ------------------------------------------------------------------------------
    def exp2p(self, x: int) -> int:
        """2^x as tb303._exp2p: the exponent's bits and the polynomial on the fraction"""
        s = self.s
        r0 = s.raw(_trunc, [x])
        f1 = s.raw(_float0, [r0])
        one = self.ki(1)
        s.flag("-", x, f1)
        r0 = s.iff("LT", r0, r0, "-", one, kind="i")             # the floor of a negative non-integer
        f1 = s.raw(_float0, [r0])
        fr = self.sub(x, f1)
        d = self.kh(T.EXP2_POLY[0])
        for c in T.EXP2_POLY[1:]:
            d = self.mul(d, fr)
            d = self.addk(d, c)
        r0 = s.raw(_iadd, [self.ki(127), r0], wishes=I8)
        r0 = s.raw(_lsh23, [r0])
        return self.mul(d, r0)

    def recip(self, x: int) -> int:
        """1 / x as dnfw.perc.machines._recip_inline"""
        d = self.s.raw(lambda p, d, a, b: p.iop(d, a, "-", b), [self.ki(0x7EF311C7), x])
        for _ in range(3):
            t = self.mul(x, d)
            t = self.sub(self.kh(2.0), t)
            d = self.mul(d, t)
        return d

    def onepole(self, x: int, c, sx: int, sy: int) -> int:
        """tb303._onepole on its slot words"""
        t10 = self.mulk(x, c[0])
        x1 = self.ld(sx)
        self.st(sx, x)
        t11 = self.mulk(x1, c[1])
        t10 = self.add(t10, t11)
        y1 = self.ld(sy)
        t11 = self.mulk(y1, c[2])
        y = self.add(t10, t11)
        self.st(sy, y)
        return y

    def biquad(self, x: int, c, sx1: int, sx2: int, sy1: int, sy2: int) -> int:
        x2 = self.ld(sx2)
        t10 = self.mulk(x2, c[2])
        x1 = self.ld(sx1)
        self.st(sx2, x1)
        self.st(sx1, x)
        t11 = self.mulk(x1, c[1])
        t10 = self.add(t10, t11)
        t11 = self.mulk(x, c[0])
        t10 = self.add(t10, t11)
        y2 = self.ld(sy2)
        t11 = self.mulk(y2, c[4])
        t10 = self.add(t10, t11)
        y1 = self.ld(sy1)
        self.st(sy2, y1)
        t11 = self.mulk(y1, c[3])
        y = self.add(t10, t11)
        self.st(sy1, y)
        return y

    def frac1(self, d: int) -> int:
        """x - floor(x) for -1 < x < 1, as machines.frac computes it there: x - (-1.0) when x is negative,
        else x (its x - 0.0)"""
        s = self.s
        m1 = self.kh(-1.0)
        s.flag("-", d, self.kh(0.0))
        return s.iff("LT", d, d, "-", m1)

    def saw(self, q: int) -> int:
        """tb303._saw: q 2048/1023 before the step, 2 q - 2 after"""
        s = self.s
        before = self.mulk(q, 2048.0 / 1023.0)
        after = self.add(q, q)
        after = self.addk(after, -2.0)
        s.flag("-", q, self.kh(T.EDGE))
        return s.iff("GE", before, after, "PASS")

    def blep(self, f4: int, x: int, edge: float, h: int, inc: int, rinc: int) -> int:
        """tb303._blep: the residual of a step of height H at EDGE added to F4 (the phase X). BRANCH_BLEP: the
        two residuals (a step crossed this sample, or before the next: once a cycle each) in blocks out of line
        behind conditional jumps; else as conditional computes, both worked out every time."""
        s = self.s
        d = self.addk(x, -edge)
        if edge > 0:                             # d in (-1, 1)
            d = self.frac1(d)
        else:                                    # d in [0, 1 + small): its x - 1.0 once past 1
            one = self.kh(1.0)
            s.flag("-", d, one)
            d = s.iff("GE", d, d, "-", one)
        if BRANCH_BLEP:
            kt = ktab(self.L)
            w = self.sub(self.kh(1.0), d)
            s.flag("-", d, inc)
            f4 = s.branch("LT", f4, (d, rinc, h), _residual(kt, -0.5))
            s.flag("-", w, inc)
            return s.branch("LT", f4, (w, rinc, h), _residual(kt, 0.5))
        t = self.mul(d, rinc)
        u = self.sub(self.kh(1.0), t)
        u = self.mul(u, u)
        u = self.mul(u, h)
        rp = self.mulk(u, -0.5)
        s.flag("-", d, inc)
        f4 = s.iff("LT", f4, f4, "+", rp)
        w = self.sub(self.kh(1.0), d)
        t = self.mul(w, rinc)
        u = self.sub(self.kh(1.0), t)
        u = self.mul(u, u)
        u = self.mul(u, h)
        ra = self.mulk(u, 0.5)
        s.flag("-", w, inc)
        return s.iff("LT", f4, f4, "+", ra)


BRANCH_BLEP = True


def _kload(kt: KTab, p: Prog, d: int, x: float) -> None:
    """Fd = the constant X, from the table where it has a word"""
    at = kt.at(bits(f32(x)))
    if at is None:
        p.fconst(d, x)
    else:
        p.ldi(d, at[1], at[0])


def _residual(kt: KTab, half: float):
    """the block: F4 += (1 - d rinc)^2 h (HALF), tb303._blep's past (-0.5) or ahead (0.5) branch's operations"""
    def body(p: Prog, regs, temps) -> None:
        f4, d, rinc, h = regs
        t, c = temps
        p.fop(t, d, "*", rinc)
        _kload(kt, p, c, 1.0)
        p.fop(t, c, "-", t)
        p.fop(t, t, "*", t)
        p.fop(t, t, "*", h)
        _kload(kt, p, c, half)
        p.fop(t, t, "*", c)
        p.fop(f4, f4, "+", t)
    return body


def region_a(p: Prog, L: C.Layout) -> dict:
    """the envelopes, the cutoff, the coefficients and the amplitude (tb303._control from mainEnv on), the
    oscillator's DC, and the four phases with their saw parts (tb303._osc up to the square)"""
    g = Gen(p, L)
    s, k, ld, st = g.s, g.kh, g.ld, g.st
    g.hold(0.0, 1.0)
    # mainEnv, rc1, rc2 (rc2 fed only with an accent)
    menv = g.mul(ld(T.S_MENV), ld(T.S_MC))
    st(T.S_MENV, menv)
    rc1 = ld(T.S_RC1)
    t = g.sub(rc1, menv)
    t = g.mulk(t, T.RC1)
    rc1 = g.add(t, menv)
    st(T.S_RC1, rc1)
    acc = ld(T.S_ACC)
    z = g.k(0.0)
    s.flag("-", acc, k(0.0))
    x6 = s.iff("GT", z, menv, "PASS")
    rc2 = ld(T.S_RC2)
    t = g.sub(rc2, x6)
    t = g.mulk(t, T.RC2)
    rc2 = g.add(t, x6)
    st(T.S_RC2, rc2)
    # cutoff x 2^(envScaler (rc1 - envOffset) + accent rc2), 200..20000 Hz
    u = g.sub(rc1, ld(T.D_EOF))
    u = g.mul(u, ld(T.D_ESC))
    w = g.mul(rc2, acc)
    u = g.add(u, w)
    e = g.exp2p(u)
    c = g.mul(e, ld(T.D_CUT))
    c = g.f("MAX", c, k(200.0))
    c = g.f("MIN", c, k(20000.0))
    fx = g.mulk(c, 1.0 / (T.OSR * 2.0 ** 0.5))
    g6 = g.mulk(fx, 4.4156345)
    g6 = g.addk(g6, 12.358354)
    g6 = g.mul(g6, fx)
    g6 = g.addk(g6, 1.0)
    g6 = g.recip(g6)
    g.scope()
    g9 = g.mulk(fx, 6.1922189)
    g9 = g.addk(g9, 0.00045522346)
    st(T.T_B0, g.mul(g6, g9))
    kk = g.addk(fx, 7198.6997)
    for cc in (-5837.7917, -476.47308, 614.95611, 213.87126, 16.998792):
        kk = g.mul(kk, fx)
        kk = g.addk(kk, cc)
    res = ld(T.D_RES)
    g11 = g.mulk(kk, 1.0 / 17.0)
    g11 = g.addk(g11, -1.0)
    g11 = g.mul(g11, res)
    g11 = g.addk(g11, 1.0)
    t12 = g.add(k(1.0), res)
    st(T.T_G, g.mul(g11, t12))
    st(T.T_K, g.mul(kk, res))
    # the amplitude: the amp envelope + (0.45 + 4 accent) mainEnv, through the de-clicker
    g.scope()
    aenv = ld(T.S_AENV)
    st(T.S_AENV, g.mulk(aenv, T.AMP_MUL))
    a6 = g.mulk(acc, 4.0)
    a6 = g.addk(a6, 0.45)
    a6 = g.mul(a6, menv)
    a5 = g.add(aenv, a6)
    a5 = g.biquad(a5, T.DECLICK, T.S_DX1, T.S_DX2, T.S_DY1, T.S_DY2)
    st(T.T_AMP, g.mulk(a5, T.LEVEL))
    # the DC the band-limited levels drop, from 43 Hz on
    inc = ld(T.T_INC)
    bl = ld(T.D_BL)
    omb = g.sub(k(1.0), bl)
    f7 = g.mulk(omb, -T.DC_SAW)
    f6 = g.mulk(bl, -0.5 * T.DC_SQ)
    osn = g.add(f7, f6)
    z = g.k(0.0)
    s.flag("-", inc, k(T.DC_FROM))
    osn = s.iff("LT", osn, z, "PASS")
    st(T.T_OSN, osn)
    # the four phases and their saw parts (their constants held over the four)
    g.hold(0.0, 1.0, 2048.0 / 1023.0, -2.0, T.EDGE)
    ph = ld(T.S_PH)
    inci = ld(T.T_INCI)
    m32 = g.ki(-32)
    for j in range(T.OS):
        g.scope()
        x = s.raw(_float_by, [ph, m32])
        one = k(1.0)
        s.flag("-", x, k(0.0))
        x = s.iff("LT", x, x, "+", one)
        st(T_X + j, x)
        sw = g.saw(x)
        f4 = g.mul(sw, omb)
        f4 = g.add(f4, osn)
        st(T.T_Y0 + j, f4)
        ph = s.raw(_iadd, [ph, inci], wishes=I8)
    st(T.S_PH, ph)
    return g.emit("A")


def region_s1(p: Prog, L: C.Layout) -> dict:
    """the square's drive for the four samples (T_V) and its tanh at the clamps (T_T; the middle: square_mid)"""
    g = Gen(p, L)
    s, k, ld, st = g.s, g.kh, g.ld, g.st
    lo, hi = T._tanh_ends(L)
    g.hold(0.0, -1.0, 2048.0 / 1023.0, -2.0, T.EDGE, 5.5)
    for j in range(T.OS):
        g.scope()
        x2 = g.addk(ld(T_X + j), -0.5)
        x2 = g.frac1(x2)
        v = g.mulk(g.saw(x2), T.K_SQ)
        v = g.addk(v, T.OFF_SQ)
        st(T_V + j, v)
        th, tl = g.k(hi), k(lo)
        s.flag("-", v, k(5.5))
        t = s.iff("LT", th, tl, "PASS")
        st(T_T + j, t)
    return g.emit("S1")


def square_mid(p: Prog, L: C.Layout) -> None:
    """the drives between the clamps (about 8 % of a cycle each) through _tanh, as before (its exp2 lookup
    clobbers I1: set again)"""
    for j in range(T.OS):
        p.ldi(6, T_V + j - SLOT_HI, 2)
        p.fconst(12, 5.5)

        def inside(j=j):
            p.fconst(12, -5.5)

            def exact(j=j):
                T._tanh(p, L, 7, 6)
                p.sti(T_T + j - SLOT_HI, 2, 7)
                p.iconst(8, KTAB_AT + 4 * WINDOWS[1])
                p.seti(1, 8, "I1 = the constants again")
            p.if_(6, "GT", 12, exact)
        p.if_(6, "LT", 12, inside)


def region_s2(p: Prog, L: C.Layout) -> dict:
    """the square's term and its BLEP into each sample"""
    g = Gen(p, L)
    ld, st = g.ld, g.st
    g.hold(1.0, 0.5, -0.5)
    for j in range(T.OS):
        g.scope()
        inc, rinc = ld(T.T_INC), ld(T.T_RINC)
        bl = ld(T.D_BL)
        t = g.mul(ld(T_T + j), bl)
        t = g.mulk(t, -0.5)
        f4 = g.add(ld(T.T_Y0 + j), t)
        f4 = g.blep(f4, ld(T_X + j), T.EDGE - 0.5, bl, inc, rinc)
        st(T.T_Y0 + j, f4)
    return g.emit("S2")


def region_b(p: Prog, L: C.Layout) -> dict:
    """the saw's BLEP, the negation, the high-pass, the ladder (tb303._ladder), the decimator (tb303._ellip's
    operations, section by section over the four samples as _ellip4) and the output chain. In program order
    the BLEP and high-pass of sample j + 1 come before the ladder of sample j (the scheduler's window then
    overlaps them); every state goes through its slot word (a move) between the four."""
    g = Gen(p, L)
    s, k, ld, st = g.s, g.kh, g.ld, g.st
    g.hold(1.0, 0.0)

    def pre(j: int) -> int:
        g.scope()
        inc, rinc = ld(T.T_INC), ld(T.T_RINC)
        omb = g.sub(k(1.0), ld(T.D_BL))
        h = g.mulk(omb, T.SAW_LO - T.SAW_HI)
        f4 = g.blep(ld(T.T_Y0 + j), ld(T_X + j), T.EDGE, h, inc, rinc)
        f4 = g.sub(k(0.0), f4)                   # Open303 negates the oscillator
        return g.onepole(f4, T.HP1, T.S_H1X, T.S_H1Y)

    def ladder(f4: int) -> int:
        """the states through their slot words each time (no register held across the four); a state read
        twice where it is both a multiplier's and the ALU's operand (y + y as y x 2.0: the same bits), so each
        copy sits in its unit's register class"""
        g.scope()
        y4m = ld(T.S_Y4)
        # y0 = x - fbHP(k y4)
        f5 = g.mul(y4m, ld(T.T_K))
        f5 = g.onepole(f5, T.FBHP, T.S_FX1, T.S_FY1)
        y0 = g.sub(f4, f5)
        b0 = ld(T.T_B0)
        y1, y2, y3, y4 = ld(T.S_Y1), ld(T.S_Y2), ld(T.S_Y3), ld(T.S_Y4)
        y2m, y3m = ld(T.S_Y2), ld(T.S_Y3)
        t = g.sub(y0, y1)
        t = g.add(t, y2)
        t = g.mul(t, b0)
        t = g.dbl(t)
        y1 = g.add(y1, t)                        # y1 += 2 b0 (y0 - y1 + y2)
        t = g.dbl(y2m)
        t = g.sub(y1, t)
        t = g.add(t, y3)
        t = g.mul(t, b0)
        y2 = g.add(y2, t)                        # y2 += b0 (y1 - 2 y2 + y3)
        t = g.dbl(y3m)
        t = g.sub(y2, t)
        t = g.add(t, y4)
        t = g.mul(t, b0)
        y3 = g.add(y3, t)                        # y3 += b0 (y2 - 2 y3 + y4)
        t = g.dbl(y4m)
        t = g.sub(y3, t)
        t = g.mul(t, b0)
        y4 = g.add(y4, t)                        # y4 += b0 (y3 - 2 y4)
        st(T.S_Y1, y1)
        st(T.S_Y2, y2)
        st(T.S_Y3, y3)
        st(T.S_Y4, y4)
        out = g.mul(y4, ld(T.T_G))
        return g.dbl(out)
    f = [pre(0), pre(1)]
    st(T.T_Y0, ladder(f[0]))
    f.append(pre(2))
    st(T.T_Y0 + 1, ladder(f[1]))
    f.append(pre(3))
    st(T.T_Y0 + 2, ladder(f[2]))
    st(T.T_Y0 + 3, ladder(f[3]))
    if SPLIT_B:
        g.emit("B1")
        g = Gen(p, L)
        s, k, ld, st = g.s, g.kh, g.ld, g.st
    # the decimator: six sections, each over the four samples, its coefficients held, the samples through their
    # words between sections
    g.scope()
    gain = k(T.ELLIP_GAIN)
    for j in range(T.OS):
        st(T.T_Y0 + j, g.mul(ld(T.T_Y0 + j), gain))
    for n, (b0, b1, b2, a1, a2) in enumerate(T.ELLIP):
        g.scope()
        s0w, s1w = T.S_E + 2 * n, T.S_E + 2 * n + 1
        s0, s1 = ld(s0w), ld(s1w)
        kb0, kb1, kb2, ma1, ma2 = k(b0), k(b1), k(b2), k(-a1), k(-a2)
        for j in range(T.OS):
            x = ld(T.T_Y0 + j)
            y = g.add(g.mul(x, kb0), s0)
            t9 = g.add(g.mul(x, kb1), s1)
            t14 = g.mul(ma1, y)
            s0 = g.add(t9, t14)
            t15 = g.mul(ma2, y)
            s1 = g.add(g.mul(x, kb2), t15)
            if n < len(T.ELLIP) - 1 or j == T.OS - 1:
                st(T.T_Y0 + j, y)
        st(s0w, s0)
        st(s1w, s1)
    g.scope()
    y = ld(T.T_Y0 + 3)
    y = g.onepole(y, T.AP, T.S_APX, T.S_APY)
    y = g.onepole(y, T.HP2, T.S_H2X, T.S_H2Y)
    y = g.biquad(y, T.NOTCH, T.S_NX1, T.S_NX2, T.S_NY1, T.S_NY2)
    y = g.mul(y, ld(T.T_AMP))
    s.raw(_stpost4, [y], write=False)
    return g.emit("B2")


def sample(p: Prog, L: C.Layout) -> None:
    """One sample at I4 (I0 the slot's word 32, I2 its word SLOT_HI, I1 and I3 the constants)."""
    T._slew(p)
    region_a(p, L)
    p.ldi(9, T.D_BL - T.S_MID, 0)
    p.fconst(12, 0.0)

    def square():
        region_s1(p, L)
        square_mid(p, L)
        region_s2(p, L)
    p.if_(9, "GT", 12, square)
    region_b(p, L)


def half_run(p: Prog, L: C.Layout) -> None:
    """the half's loop, with its index registers set (I0 by tb303.half)"""
    p.geti(8, 0)
    p.iconst(12, 4 * (SLOT_HI - T.S_MID))
    p.iop(8, 8, "+", 12)
    p.seti(2, 8, "I2 = the slot's word SLOT_HI")
    b3 = p.ibias.get(3)
    p.geti(8, 3)
    p.sti(T_I3 - SLOT_HI, 2, 8)
    p.iconst(8, KTAB_AT + 4 * WINDOWS[1])
    p.seti(1, 8, "I1 = the constants")
    p.iconst(8, KTAB_AT + 4 * WINDOWS[3])
    p.seti(3, 8, "I3 = the constants' second window")
    p.loop(L.W["n4"], 16, lambda: sample(p, L))
    if not p.run and VS.DEFERRED:                # the BLEPs' blocks, out of the loop's way
        past = p.label("blocks")
        p.jump("", past)
        VS.flush(p)
        p.place(past)
    p.ldi(8, T_I3 - SLOT_HI, 2)
    p.seti(3, 8, "I3 = the slot again", bias=b3)
