"""P-I SD: the Machinedrum's physical-model snare (docs/md.md), from DSP2's P-ISD and its
host scale function. P-IRS (pi_rs.py) is the same model with its own strike, so both are
written here, a flag apart.

The model, a block (32 samples at 44.1 kHz):

- a strike: an excitation table read at a pitch that falls with two envelopes (the pointer
  48 bits, int + fraction, as the 56300 holds it, clamped at the table's end), linearly
  interpolated (SD: with the firmware's half fraction, and the two quirk bits its `asr`
  pulls into the first two weights from the pointer's integer parts);
- three 512-word delay lines (core.delay_base: the slot's 2048 words; the lines at 0, 512,
  1024, scratch arrays from 1536), each read through a one-pole lowpass at its own tap;
- the firmware's noise (a doubling recursion on 24-bit words) through a leaky integrator,
  scaled by an envelope that restarts when the raw noise word exceeds it;
- a junction that writes the three lines back, a highpass-integrator over the lines'
  sum, and eight two-pole modes (frequency x pitch, radius from DEC) summed onto the body.

Words are floats (Q23 / 2^23); the envelopes that are multiplied once a block truncate as
the 56300's do (core.mpy_floor); the pointer's step, Y1 x Y0 >> 20 (46 bits), is exact
(imul_floor); the modes' coefficients are the 56300's integer arithmetic exactly (48-bit
products and sums, `_prod`): in float they were one LSB off, which moved the ringing modes
enough to cost 40 dB (54 dB -> 93+ dB against the reference). State words (S, core.S0..): 15/19 envelopes, 16/17 the pointer (fraction,
int from the table's start), 18 LP1, 20..22 the lines' write positions, 23..25 their taps,
28 the integrator's leak, 29/30/31 the line lowpasses, 32/33 the integrator, 34/35 noise,
36/38 envelopes, 39 the noise integrator (never initialised: 0 as the reference assumes),
41 + 2j / 42 + 2j mode j's accumulator and its last limited output.
"""

from __future__ import annotations

from . import core as K
from .core import inp, s, ss, w, ws
from .gnd import pitch_word, square_shift
from ..perc.dsl import Prog

Q = K.Q23
TOP = K.TOP

# scratch arrays (words from the scratch base: the delay area's word 1536)
SCRW = 1536
E, N, X40, X60, X80, XA0, XC0, COEF = 0, 32, 64, 96, 128, 160, 192, 224
MID = X40 + 16                                     # (the res loop's I0)


def q24(p: Prog, d: int, a: int, k31: int | None = None) -> None:
    """Fd = the 24-bit word in Ra's low bits, signed, as Q23. K31: a register the caller holds -31 in
    (else R12 is loaded). Clobbers R12."""
    p.lsh(d, a, 8)
    if k31 is None:
        p.iconst(12, -31)
        k31 = 12
    p.float_(d, d, k31)


def imul_floor(p: Prog, d: int, a: int, b: int, sh: int) -> None:
    """Rd = floor(Ra Rb / 2^sh), exactly (Ra, Rb integers in 0..2^24, 12 <= sh <= 24): the
    halves' products (12 bits each) are exact in floats. Clobbers R0-R3, R12-R15."""
    p.iconst(12, 4095)
    p.iop(1, a, "AND", 12)
    p.lsh(0, a, -12)
    p.iop(3, b, "AND", 12)
    p.lsh(2, b, -12)
    for r in (0, 1, 2, 3):
        p.iconst(12, 0)
        p.float_(r, r, 12)
    p.fop(13, 0, "*", 3)
    p.fop(14, 1, "*", 2)
    p.trunc(13, 13)
    p.trunc(14, 14)
    p.iop(13, 13, "+", 14)                    # the middle products
    p.fop(14, 1, "*", 3)
    p.trunc(14, 14)
    p.lsh(14, 14, -12)
    p.iop(13, 13, "+", 14)
    p.lsh(13, 13, -(sh - 12))
    p.fop(14, 0, "*", 2)
    p.trunc(14, 14)
    p.lsh(14, 14, 24 - sh)
    p.iop(d, 13, "+", 14)


def _scr(p: Prog, L: K.Layout, r: int, off: int) -> None:
    """Rr = the scratch array word OFF's address. Clobbers R12."""
    p.ld(r, L.C["h"])
    if off:
        p.iconst(12, 4 * off)
        p.iop(r, 12, "+", r)


def _i5(p: Prog, L: K.Layout, off: int = 0) -> None:
    _scr(p, L, 0, off)
    p.seti(5, 0)


def _each(p: Prog, L: K.Layout, body) -> None:
    """for k in 0..31: body() with I5 at scratch word k (arrays by their offsets); the loop
    takes R0 and R12."""
    _i5(p, L)

    def one():
        body()
        p.ldpost(12, 5)
    p.loop0(32, one)


def _line(p: Prog, L: K.Layout, j: int, pos: int, tap: int | None, ri: int, rb: int) -> None:
    """Rri = line j's index (state POS + state TAP, mod 512) in bytes (opt-md, 2026-11-12: x 4),
    Rrb = line j's address; R1 = 4, R3 = 0x7FC (_at's step and mask)."""
    s(p, ri, pos)
    if tap is not None:
        s(p, 12, tap)
        p.iop(ri, 12, "+", ri)
    p.iconst(12, 511)
    p.iop(ri, ri, "AND", 12)
    p.lsh(ri, ri, 2)
    p.ld(rb, L.C["g"])
    if j:
        p.iconst(12, 2048 * j)
        p.iop(rb, 12, "+", rb)
    p.iconst(1, 4)
    p.iconst(3, 0x7FC)


def _at(p: Prog, ri: int, rb: int) -> None:
    """I2 = line word Rri / 4 (Rri a byte index, Rrb its line), and Rri moves on a word (mod 512
    words: R1 = 4, R3 = 0x7FC, _line's). Clobbers R13."""
    p.iop(13, ri, "+", rb)
    p.seti(2, 13)
    p.iop(ri, ri, "+", 1)
    p.iop(ri, ri, "AND", 3)


def _satr(p: Prog, x: int, top: int, bot: int | None) -> None:
    """K.sat with the bounds held in registers (opt-md, 2026-11-12): F<top> = TOP, F<bot> = -1 (None:
    -1 loaded into R12)."""
    p.fop(x, x, "MIN", top)
    if bot is None:
        p.fconst(12, -1.0)
        bot = 12
    p.fop(x, x, "MAX", bot)


def _onepole(p: Prog, L: K.Layout, st: int, coef, src, dst: int, extra=None) -> None:
    """y = sat(a) to DST, a += c x - c y (the firmware's mac pair) from state ST: x the
    array SRC (an int) or line (j, pos, tap). EXTRA(): more in the same loop (R5, R9, R14,
    R15 its own).
    2026-11-14 (opt-md): a in F8, c in F2, so c y rides on the add of c x (the multiplier || ALU form); y
    straight from a through the limiter (no copy first). The same operations, in the same order."""
    coef()                                     # -> F8
    p.fpass(2, 8)                              # c
    s(p, 8, st)                                # a
    line = isinstance(src, tuple)
    if line:
        _line(p, L, src[0], src[1], src[2], 10, 11)
    if extra is None:                          # (opt-md) the limiter's bounds in F14, F15
        p.fconst(14, TOP)
        p.fconst(15, -1.0)
    else:                                      # (EXTRA has R14, R15: the top in F4, free here)
        p.fconst(4, TOP)

    def body():
        if line:
            _at(p, 10, 11)
            p.ldi(6, 0, 2)
        else:
            p.ldi(6, src, 5)
        if extra is None:
            p.fop(7, 8, "MIN", 14)             # y = sat(a)
            p.fop(7, 7, "MAX", 15)
        else:
            p.fop(7, 8, "MIN", 4)
            p.fconst(12, -1.0)
            p.fop(7, 7, "MAX", 12)
        p.sti(dst, 5, 7)
        p.fop(12, 2, "*", 6)                   # c x
        p.par(("*", 13, 2, 7), ("+", 8, 8, 12))   # c y; a + c x
        p.fop(8, 8, "-", 13)                   # - c y
        if extra:
            extra()
    _each(p, L, body)
    K.sat(p, 8)
    ss(p, st, 8)


def _word(p: Prog, d: int) -> None:
    """Rd = Fd (a Q23 word) as its integer. Clobbers R12."""
    p.fconst(12, 2.0 ** 23)
    p.fop(d, d, "*", 12)
    p.trunc(d, d)


def _clamp(p: Prog, d: int) -> None:
    """Rd = Rd through the limiter (24 bits). Clobbers R12."""
    p.iconst(12, 0x7FFFFF)
    p.iop(d, d, "MIN", 12)
    p.iconst(12, -0x800000)
    p.iop(d, d, "MAX", 12)


def _add(p: Prog, h: int, lo: int, h2: int, lo2: int) -> None:
    """(Rh, Rlo) += (Rh2, Rlo2): 48-bit sums as (signed high word, low 24 bits); Rh2 and
    Rlo2 in R8..R11. Clobbers R12, R13."""
    p.iop(lo, lo2, "+", lo)
    p.lsh(13, lo, -24)
    p.iop(h, h2, "+", h)
    p.iop(h, 13, "+", h)
    p.iconst(12, 0xFFFFFF)
    p.iop(lo, lo, "AND", 12)


def _asl(p: Prog, h: int, lo: int) -> None:
    """(Rh, Rlo) <<= 1. Clobbers R12, R13."""
    p.lsh(lo, lo, 1)
    p.lsh(13, lo, -24)
    p.ipass(12, h)
    p.iop(h, 12, "+", h)
    p.iop(h, 13, "+", h)
    p.iconst(12, 0xFFFFFF)
    p.iop(lo, lo, "AND", 12)


def _prod_body(p: Prog) -> None:
    """(R6, R7) = 2 R4 R5 as (floor / 2^24, mod 2^24). perf, 2026-11-11: the fixed-point multiplier: R6 = SSF of
    R4 2^8 and R5 = floor(R4 R5 / 2^23), R7 = the low word of R4 R5, doubled, low 24 bits (was the 12-bit halves
    and a sign fix-up, ~170 instructions)."""
    p.lsh(0, 4, 8)
    p.mul_ssf(6, 0, 5)
    p.mul_ssi(7, 4, 5)
    p.lsh(7, 7, 1)
    p.iconst(12, 0xFFFFFF)
    p.iop(7, 7, "AND", 12)


def _prod(p: Prog) -> None:
    """(R6, R7) = the 56300's product of the words R4, R5 (signed, |x| <= 2^23): 2 R4 R5
    = R6 2^24 + R7, R7 in 0..2^24, exactly. Clobbers R0-R3, R8, R12-R15."""
    p.call("pisd_prod", lambda: _prod_body(p))


class _PI:
    RS = False
    TAB = "PISD_TAB"
    START = 0x18                              # the pointer's start (from the table's)
    CLAMP = 0x483
    PAR = 1                                   # the table's address, odd (the quirk bits)
    GAINK = 30
    LEAK = 0x59999A

    # -- host ---------------------------------------------------------------------------
    @staticmethod
    def _pitch(p: Prog, L: K.Layout) -> None:
        """W1 = (tblP[p & 127] << ((p >> 7) + 10)) - 1000, p = PTCH >> 6."""
        inp(p, 0, 0)
        p.lsh(0, 0, -6)
        pitch_word(p, L, 4, 0, 10)
        p.fconst(12, 1000.0)
        p.fop(4, 4, "-", 12)
        K.mul_k(p, 4, 4, Q)
        ws(p, 1, 4)

    @staticmethod
    def _q(p: Prog, word: int, k: int, sh: int, add: float = 0.0) -> None:
        """W[word] = input k * 2^sh (+ add), a Q23 word."""
        inp(p, 0, k)
        K.to_float(p, 4, 0, sh)
        if add:
            K.add_k(p, 4, 4, add)
        ws(p, word, 4)

    @staticmethod
    def _sq(p: Prog, word: int, k: int) -> None:
        """W[word] = input k ^ 2 >> 5, a Q23 word."""
        inp(p, 0, k)
        square_shift(p, 4, 0, 5)
        K.mul_k(p, 4, 4, Q)
        ws(p, word, 4)

    @staticmethod
    def _tq(p: Prog, L: K.Layout, word: int, k: int, sh: int, add: int, table: str) -> None:
        """W[word] = TABLE[(input k >> sh) + add]."""
        inp(p, 0, k)
        p.lsh(0, 0, -sh)
        p.iconst(12, add)
        p.iop(0, 12, "+", 0)
        K.table_f(p, L, 4, table, 0, 12)
        ws(p, word, 4)

    # -- init, trig ---------------------------------------------------------------------
    @classmethod
    def _init(cls, p: Prog, L: K.Layout) -> None:
        p.fconst(0, 0.0)
        for k in (18, 29, 30, 31, 32, 33):
            ss(p, k, 0)
        K.zero_words(p, 41, 16)                    # (2026-11-20: a loop, perc2b's room)
        p.fconst(0, 0x7FFCB9 * Q)                  # host words 5 and 6, until the next
        ws(p, 5, 0)
        ws(p, 6, 0)
        for k, v in ((20, 0), (21, 0), (22, 0), (23, 0x10B), (24, 0xFF), (25, 0xB5),
                     (34, 0xA), (35, 1)):
            p.iconst(0, v)
            ss(p, k, 0)
        p.fconst(0, cls.LEAK * Q)
        ss(p, 28, 0)

    @classmethod
    def _trig(cls, p: Prog, L: K.Layout) -> None:
        p.iconst(0, 0)
        ss(p, 16, 0)
        p.iconst(0, cls.START)
        ss(p, 17, 0)
        p.fconst(0, TOP)
        for k in (15, 19, 36, 38):
            ss(p, k, 0)

    # -- render -------------------------------------------------------------------------
    @classmethod
    def _render(cls, p: Prog, L: K.Layout) -> None:
        C, rs = L.C, cls.RS
        K.delay_base(p, L, 0)
        p.st(C["g"], 0)
        if L.pi_scr is None:
            p.iconst(12, 4 * SCRW)
            p.iop(0, 12, "+", 0)
        else:                                      # (perf: L1, shared; core.Layout.pi_scr)
            assert 256 <= K.PI_SCR_WORDS
            p.iconst(0, L.pi_scr)
        p.st(C["h"], 0)

        # the strike's envelopes and pitch
        s(p, 4, 19)
        p.fconst(5, 0x7C28F6 * Q)
        K.mpyf_any(p, 6, 4, 5)
        ss(p, 19, 6)
        s(p, 4, 15)
        p.fconst(5, 0x7F7CEE * Q)
        K.mpyf_any(p, 7, 4, 5)
        ss(p, 15, 7)
        p.fconst(11, 2.0 ** 23)
        if rs:
            p.iconst(9, 0x400000)                  # RS: y0 = 0.5 (its sum is not used)
        else:
            w(p, 8, 3)
            p.fop(8, 8, "*", 6)
            w(p, 9, 5)
            p.fop(9, 9, "*", 7)
            p.fop(8, 8, "+", 9)
            K.add_k(p, 8, 8, 0.5)
            K.sat(p, 8)
            p.fop(9, 8, "*", 11)
            p.trunc(9, 9)                          # Y0, a word
        w(p, 10, 1)
        p.fop(10, 10, "*", 11)
        p.trunc(10, 10)                            # Y1, a word
        imul_floor(p, 6, 10, 9, 20)                # the step, 2^-24 units
        imul_floor(p, 7, 10, 9, 22)                # y:$fe
        p.iconst(12, 0x7FFFFF)
        p.iop(7, 7, "MIN", 12)
        q24(p, 7, 7)
        p.st(C["n3"], 7)

        # the pointer: P (R4 int, R5 fraction) .. P + 32 step (stored, clamped)
        s(p, 4, 17)
        s(p, 5, 16)
        p.lsh(9, 6, 5)
        p.ipass(12, 9)
        p.iop(9, 12, "+", 5)                       # frac + 32 step
        p.ipass(12, 6)
        p.iop(10, 12, "+", 9)                      # frac + 33 step
        p.lsh(1, 9, -24)
        p.ipass(12, 4)
        p.iop(1, 12, "+", 1)                       # P + 32 step: int
        p.iconst(12, 0xFFFFFF)
        p.iop(2, 9, "AND", 12)                     # and fraction
        p.iconst(12, cls.CLAMP)
        p.if_(1, "GE", 12, lambda: (p.iconst(1, cls.CLAMP), p.iconst(2, 0)), kind="i")
        ss(p, 17, 1)
        ss(p, 16, 2)
        if not rs:
            # the quirk bits: asr pulls a1's bit 0 (P + 32 step, clamped) and b1's (P +
            # 33 step) into the first two weights' top bit
            p.iconst(12, cls.PAR)
            p.iop(1, 12, "+", 1)
            p.iconst(12, 1)
            p.iop(7, 1, "AND", 12)
            p.lsh(7, 7, 23)
            p.lsh(3, 10, -24)
            p.ipass(12, 4)
            p.iop(3, 12, "+", 3)
            p.iconst(12, cls.PAR)
            p.iop(3, 12, "+", 3)
            p.iconst(12, 1)
            p.iop(8, 3, "AND", 12)
            p.lsh(8, 8, 23)
        else:
            w(p, 7, 3)
            K.mul_k(p, 7, 7, 16.0)                 # RS: 16 HARD

        T = L.T[cls.TAB]

        # (opt-md, 2026-11-14) the table's address in R1, q24's count (RS: the fraction's) in R2, the
        # 24-bit mask in R3, held through the loop
        p.iconst(1, T)
        p.iconst(2, -24 if rs else -31)
        p.iconst(3, 0xFFFFFF)

        def strike():
            p.lsh(12, 4, 2)
            p.iop(13, 12, "+", 1)
            p.seti(1, 13)
            p.ldi(14, 0, 1)
            p.ldi(15, 1, 1)
            if rs:
                p.float_(9, 5, 2)                  # t
                p.fop(15, 15, "-", 14)
                p.fop(15, 15, "*", 9)
                p.fop(15, 15, "+", 14)
                p.fop(15, 15, "+", 15)
                K.sat(p, 15)
                p.fop(15, 15, "*", 7)
                K.sat(p, 15)
                p.sti(X40, 5, 15)
            else:
                p.lsh(9, 5, -1)
                p.iop(9, 9, "OR", 7)               # the weight w (with its quirk bit)
                p.ipass(7, 8)
                p.iconst(8, 0)
                q24(p, 10, 9, 2)                   # w
                p.iconst(12, 0x800001)
                p.iop(11, 12, "+", 9)
                q24(p, 11, 11, 2)                  # w - TOP
                p.fop(11, 11, "*", 14)
                p.fop(10, 10, "*", 15)
                p.fop(11, 11, "-", 10)
                K.sat(p, 11)
                p.sti(E, 5, 11)
            p.ipass(12, 6)
            p.iop(5, 12, "+", 5)
            p.lsh(12, 5, -24)
            p.iop(4, 12, "+", 4)
            p.iop(5, 5, "AND", 3)
        _each(p, L, strike)

        # the block's envelopes, the waveguide's gain, the lowpasses' coefficient
        s(p, 4, 38)
        p.fconst(5, 0x7F5C29 * Q)
        K.mpyf_any(p, 6, 4, 5)
        ss(p, 38, 6)
        s(p, 4, 36)
        w(p, 5, 7)
        K.mpyf_any(p, 7, 5, 4)
        ss(p, 36, 7)
        w(p, 4, 2)
        K.mul_k(p, 4, 4, float(cls.GAINK))
        p.trunc(4, 4)
        K.table_f(p, L, 5, "PI_GAIN_142B49", 4, 12)
        p.st(C["a"], 5)
        K.mul_k(p, 5, 5, 0x5A827A * Q)
        p.st(C["b"], 5)
        K.mul_k(p, 6, 6, (0xD9999A - (1 << 24)) * Q)
        K.add_k(p, 6, 6, (0x400000 if rs else 0x333333) * Q)
        p.st(C["c"], 6)

        if rs:
            _onepole(p, L, 18, lambda: p.fconst(8, 0x7FFCB9 * Q), X40, X60)
        else:
            _onepole(p, L, 18, lambda: w(p, 8, 4), E, X60)
        _onepole(p, L, 29, lambda: p.ld(8, C["c"]), (0, 20, 23), X80)
        _onepole(p, L, 30, lambda: p.ld(8, C["c"]), (1, 21, 24), XA0)

        # the noise
        s(p, 4, 34)
        s(p, 5, 35)
        _i5(p, L, N)

        p.iconst(2, -31)                           # (opt-md, 2026-11-14) q24's count and the mask, held
        p.iconst(3, 0xFFFFFF)

        def noise():
            q24(p, 7, 5, 2)
            p.stpost(5, 7)
            p.ipass(12, 4)
            p.iop(4, 12, "+", 5)
            p.iop(4, 4, "AND", 3)
            p.ipass(12, 5)
            p.iop(6, 12, "+", 4)
            p.iop(6, 6, "AND", 3)
            p.ipass(5, 4)
            q24(p, 7, 5, 2)
            p.stpost(5, 7)
            p.ipass(5, 6)
        p.loop0(16, noise)
        ss(p, 34, 6)
        ss(p, 35, 4)
        p.st(C["d"], 4)

        # the third line's lowpass, and the noise's leaky integrator (in place)
        s(p, 5, 39)

        def integ():
            p.ldi(9, N, 5)
            p.fop(14, 5, "MIN", 4)             # (F4: TOP, _onepole's)
            p.fconst(12, -1.0)
            p.fop(14, 14, "MAX", 12)
            p.sti(N, 5, 14)
            p.fop(5, 5, "+", 9)
            p.fconst(15, (0xD9999A - (1 << 24)) * Q)
            p.fop(15, 15, "*", 14)
            p.fop(5, 5, "+", 15)
        _onepole(p, L, 31, lambda: p.ld(8, C["c"]), (2, 22, 25), XC0, integ)
        K.sat(p, 5)
        ss(p, 39, 5)

        # the noise's level: its envelope restarts when the raw word reaches it
        p.ld(4, C["d"])
        q24(p, 4, 4)
        p.fconst(12, 0.0)
        p.fop(5, 12, "-", 4)
        p.fop(4, 4, "MAX", 5)
        s(p, 5, 36)

        def last():
            _scr(p, L, 7, N + 31)
            p.seti(1, 7)
            p.ldi(6, 0, 1)
        p.if_(4, "GE", 5, lambda: p.fconst(6, TOP), last)
        p.fop(6, 5, "*", 6)
        K.sat(p, 6)
        w(p, 7, 6)
        p.fop(6, 7, "*", 6)
        K.sat(p, 6)
        K.mul_k(p, 8, 6, 0x266666 * Q)
        K.mul_k(p, 9, 6, 0x59999A * Q)
        p.fconst(14, TOP)                          # (opt-md) the limiter's bounds
        p.fconst(15, -1.0)

        def mix():
            p.ldi(5, N, 5)
            if rs:
                p.ldi(4, X40, 5)
                p.fop(6, 8, "*", 5)
            else:
                p.ldi(4, E, 5)
                p.fop(4, 4, "+", 4)
                p.fop(6, 9, "*", 5)
            p.fop(4, 4, "+", 6)
            _satr(p, 4, 14, 15)
            p.sti(X40, 5, 4)
            p.ldi(4, X60, 5)
            p.fop(6, 8, "*", 5)
            p.fop(4, 4, "+", 6)
            _satr(p, 4, 14, 15)
            p.sti(X60, 5, 4)
        _each(p, L, mix)

        # the junction: the lines written back
        p.fconst(8, 0x7EB852 * Q)
        p.ld(9, C["a"])
        p.ld(10, C["b"])
        p.ld(11, C["g"])
        # (opt-md, 2026-11-12) the three lines' write positions (state 20..22) start at 0 together (_init)
        # and move on together, a word a sample: one index R1 for all three, the address worked out once
        # a sample, line j at + 512 j words (R3 = 511: the mask)
        s(p, 1, 20)
        p.iconst(3, 511)
        p.iop(1, 1, "AND", 3)
        p.fconst(2, TOP)                           # (opt-md) the limiter's top

        def put(ri: int, j: int, v: int) -> None:
            p.sti(512 * j, 2, v)

        def junction():
            p.lsh(12, 1, 2)
            p.iop(13, 11, "+", 12)
            p.seti(2, 13)
            p.ldi(4, X60, 5)
            p.ldi(5, X80, 5)
            p.ldi(6, XA0, 5)
            p.ldi(7, XC0, 5)
            p.fop(14, 8, "*", 4)
            p.fop(15, 9, "*", 5)
            p.fop(15, 14, "+", 15)
            _satr(p, 15, 2, None)
            put(3, 2, 15)
            p.fop(4, 10, "*", 7)
            p.fop(6, 10, "*", 6)                   # (once: the second line used the same product again)
            p.fop(15, 14, "+", 6)
            p.fop(15, 15, "+", 4)
            _satr(p, 15, 2, None)
            put(2, 1, 15)
            p.fop(15, 14, "-", 6)
            p.fop(15, 15, "+", 4)
            _satr(p, 15, 2, None)
            put(1, 0, 15)
            p.iconst(12, 1)
            p.iop(1, 12, "+", 1)
            p.iop(1, 1, "AND", 3)
        _each(p, L, junction)
        ss(p, 20, 1)
        ss(p, 21, 1)
        ss(p, 22, 1)

        # the lines' sum, highpassed by a leaky integrator, onto the body (SD) or as the
        # modes' input (RS)
        # (opt-md, 2026-11-14) c in F1, a in F8, the sum in F12: c y rides on the add of the sum (the multiplier
        # || ALU form); each limited value straight into the register its next use reads (no copies). The same
        # operations in the same order.
        s(p, 1, 28)
        s(p, 8, 32)
        s(p, 5, 33)
        p.fpass(6, 8)
        p.fconst(14, TOP)                          # (opt-md) the limiter's bounds
        p.fconst(15, -1.0)

        def hp():
            p.ldi(12, XA0, 5)
            p.ldi(9, XC0, 5)
            p.fop(12, 12, "+", 9)
            p.ldi(9, X80, 5)
            p.fop(12, 12, "+", 9)                  # the lines' sum
            if rs:
                p.sti(X60, 5, 6)
            else:
                p.ldi(9, X40, 5)
                p.fop(9, 9, "+", 6)
                _satr(p, 9, 14, 15)
                p.sti(X40, 5, 9)
            p.fop(6, 8, "MIN", 14)                 # y = sat(a)
            p.fop(6, 6, "MAX", 15)
            p.fop(8, 8, "-", 5)
            p.par(("*", 13, 1, 6), ("+", 8, 8, 12))   # c y; a + the sum
            p.fop(8, 8, "-", 13)
            p.fop(5, 12, "MIN", 14)                # the sum through the limiter
            p.fop(5, 5, "MAX", 15)
        _each(p, L, hp)
        K.sat(p, 8)
        ss(p, 32, 8)
        ss(p, 33, 5)

        # the modes' coefficients, in the 56300's integer arithmetic (a radius or cosine
        # one LSB off moves a ringing mode's pitch and decay audibly over a hit):
        # F = T x (y:$fe for the first four modes, W1 the rest), C = 1 - F^2 + F^4 / 6,
        # R = CURVE[V DEC], c0 = -R^2, c1 = 2 R C - 1, c2 = 2 g (2 R C - 1 - R^2), g the
        # mode's gain (x RING for the last four)
        p.iconst(1, T)
        p.seti(2, 1)
        _i5(p, L, COEF)
        w(p, 4, 8)
        _word(p, 4)
        p.st(C["f"], 4)
        for half in (0, 1):
            if half:
                w(p, 4, 1)
            else:
                p.ld(4, C["n3"])
            _word(p, 4)
            p.st(C["e"], 4)

            def coef(half=half):
                p.ldi(4, 0, 2)
                _word(p, 4)
                p.ld(5, C["e"])
                _prod(p)
                _clamp(p, 6)                       # F
                p.ipass(4, 6)
                p.iconst(12, 0)
                p.iop(5, 12, "-", 6)
                _prod(p)                           # b = -F^2
                p.st(C["b"], 6)
                p.st(C["c"], 7)
                p.ipass(5, 6)
                p.iconst(4, 0x155555)
                _prod(p)
                p.ipass(4, 6)                      # y1 = y0 / 6
                p.ld(5, C["b"])
                _prod(p)                           # y1 y0
                p.ld(9, C["c"])
                p.ld(10, C["b"])
                _add(p, 6, 7, 10, 9)
                p.iconst(12, 0x7FFFFF)
                p.iop(6, 12, "+", 6)
                _clamp(p, 6)
                p.st(C["d"], 6)                    # C
                p.ldi(4, 16, 2)
                _word(p, 4)
                if half:
                    p.ld(5, C["f"])
                    _prod(p)
                    _clamp(p, 6)
                    p.ipass(4, 6)
                p.st(C["a"], 4)                    # g
                p.ldi(7, 8, 2)
                w(p, 10, 2)
                p.fop(7, 7, "*", 10)
                p.fconst(12, 2.0 ** 23)
                p.fop(7, 7, "*", 12)
                p.trunc(7, 7)
                K.table_f(p, L, 4, "PI_CURVE_142949", 7, 12)
                _word(p, 4)
                p.st(C["n2"], 4)                   # R
                p.ld(5, C["d"])
                _prod(p)                           # R C
                if rs:
                    _asl(p, 6, 7)
                    p.iconst(12, -0x800000)
                    p.iop(6, 12, "+", 6)
                else:
                    p.iconst(12, -0x400000)
                    p.iop(6, 12, "+", 6)
                    _asl(p, 6, 7)
                p.ipass(9, 6)
                p.ipass(10, 7)                     # a = 2 R C - 1
                p.ipass(11, 6)
                _clamp(p, 11)
                p.st(C["b"], 11)                   # c1
                p.ld(4, C["n2"])
                p.iconst(12, 0)
                p.iop(5, 12, "-", 4)
                _prod(p)                           # -R^2
                p.st(C["c"], 6)                    # c0
                _add(p, 6, 7, 9, 10)
                _clamp(p, 6)
                p.ipass(5, 6)
                p.ld(4, C["a"])
                _prod(p)
                _asl(p, 6, 7)
                _clamp(p, 6)                       # c2
                for k in ("c", "b"):
                    p.ld(4, C[k])
                    p.iconst(12, -23)
                    p.float_(4, 4, 12)
                    p.stpost(5, 4)
                p.iconst(12, -23)
                p.float_(6, 6, 12)
                p.stpost(5, 6)
                p.ldpost(12, 5)
                p.ldpost(12, 2)
            p.loop(C["n1"], 4, coef)

        # the modes, each summed onto the body (X40)
        _scr(p, L, 1, COEF)
        p.seti(1, 1)
        p.ld(1, C["mdb"])
        p.iconst(12, 4 * (K.S0 + 41))
        p.iop(1, 12, "+", 1)
        p.seti(2, 1)

        # (perf, 2026-11-11) the modes on the multiplier || ALU (the same operations on the same operands as the
        # one-at-a-time form before it, res, I0 at X40 word k + 16: X60 is +16, X40 -16): the limiter's bounds in F10, F11, the three coefficients in
        # F0-F2, 8 cycles a sample (the ALU's 8 operations: two limiter pairs and four adds; the three products
        # ride on three of the adds)
        p.fconst(10, TOP)
        p.fconst(11, -1.0)
        K40, K60 = X40 - MID - 1, X60 - MID - 1

        def mode_mf():
            p.ldpost(1, 1)                         # c1, c2, c3 (and a word the pair of states skips)
            p.ldpost(2, 1)
            p.ldpost(3, 1)
            p.ldpost(6, 1)
            p.ldi(8, 0, 2)                         # a
            p.ldi(4, 1, 2)                         # b
            _scr(p, L, 15, MID)
            p.seti(0, 15)
            p.fop(12, 4, "*", 1)                   # p1 = b c1

            def sample(first: bool):               # a sample's 8 cycles; z of the one before is stored in the first
                p.par(("op", 4, 8, "MIN", 10), *(() if first else (("stk", K40, 0, 9),)))
                p.par(("op", 4, 4, "MAX", 11), ("ld", 6, 0))          # y; I0 on a word
                p.par(("*", 13, 2, 4), ("+", 8, 8, 12), ("ldk", 5, K60, 0))     # p2 = y c2; a + p1; x60
                p.par(("*", 14, 3, 5), ("+", 8, 8, 13))                # p3 = x60 c3; + p2
                p.par(("*", 12, 1, 4), ("+", 8, 8, 14), ("ldk", 15, K40, 0))   # p1 of the next = y c1; + p3; x40
                # (a plain compute is a 32-bit instruction; the loop's last 11 must be 48-bit: a harmless read)
                p.par(("op", 9, 15, "+", 8), ("ldk", 6, 0, 0))      # z = x40 + a
                p.par(("op", 9, 9, "MIN", 10), ("ldk", 6, 0, 0))
                p.par(("op", 9, 9, "MAX", 11), ("ldk", 6, 0, 0))
            sample(True)
            p.loop_hw(31, lambda: sample(False), cnt=7)    # (F12 carries p1: LCNTR from R7)
            p.par(("op", 8, 8, "MIN", 10), ("stk", K40, 0, 9))        # the last z; a's limit
            p.fop(8, 8, "MAX", 11)
            p.sti(0, 2, 8)
            p.sti(1, 2, 4)
            p.ldpost(12, 2)
            p.ldpost(12, 2)

        mode = mode_mf
        p.loop(C["n2"], 8, mode)

        # out
        _i5(p, L, X40)
        p.ld(1, C["mdb"])
        p.iconst(12, 4 * K.OUT0)
        p.iop(1, 12, "+", 1)
        p.seti(2, 1)

        def out():
            p.ldpost(4, 5)
            p.stpost(2, 4)
        p.loop0(32, out)


class PISD(_PI):
    """P-I SD (DSP2's P-ISD). W1 pitch, W2 DEC, W3 HARD, W4 the strike's lowpass (input 7,
    no knob: tblS[0]), W5 TENS, W6 RVOL, W7 RDEC, W8 RING (the higher modes' gain)."""
    NAME, ID = "PI-SD", 65
    PNAMES = ("PTCH", "DEC", "HARD", "RING", "TENS", "RVOL", "RDEC", "-")

    @staticmethod
    def host(p: Prog, L: K.Layout) -> None:
        _PI._pitch(p, L)
        _PI._q(p, 2, 1, -14)                       # DEC << 9
        _PI._q(p, 3, 2, -18)                       # HARD << 5
        if "hostS" in L.T:                         # tblS (the OS's, rom.HOST_TABLES "S")
            _PI._tq(p, L, 4, 7, 6, 0, "hostS")
        else:                                      # pragma: no cover (without it: no lowpass)
            p.fconst(4, TOP)
            ws(p, 4, 4)
        _PI._q(p, 5, 4, -18)                       # TENS << 5
        _PI._sq(p, 6, 5)                           # RVOL^2 >> 5
        _PI._tq(p, L, 7, 6, 7, 228, "hostQ")       # RDEC
        _PI._sq(p, 8, 3)                           # RING^2 >> 5

    @staticmethod
    def init(p: Prog, L: K.Layout) -> None:
        PISD._init(p, L)

    @staticmethod
    def trig(p: Prog, L: K.Layout) -> None:
        PISD._trig(p, L)

    @staticmethod
    def render(p: Prog, L: K.Layout) -> None:
        PISD._render(p, L)


MACHINES = (PISD,)
