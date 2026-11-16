"""The analog drums' common ground (plaits_bd, plaits_sd, plaits_hh): Plaits' stmlib::Svf (set_f_q,
Process), its tangent approximations, SoftClip, the bass drum's Diode, the 808 trigger pulse the
bass and snare drums share, and the random generator's skip (the AUX voices' draws, which Plaits'
OUT shares one stmlib::Random with). From Emilie Gillet's C++ (github.com/pichenettes/eurorack,
stmlib/dsp/filter.h, dsp.h, plaits/dsp/drums/*.h; MIT, THIRD-PARTY.md).

Every filter is five union words [g, r, h, s1, s2] reached through I1 (`wptr`), so one copy of its
code serves all eight filters of the three engines. The subroutines are leaves: a reciprocal
inside one is the inline Newton (dnfw.perc.machines._recip_inline).
"""

from __future__ import annotations

import math

from . import plk as K
from ..md import core as MK
from ..perc.dsl import Prog, f32
from ..perc.machines import _recip_inline

# the trigger pulse's words, the same in BD and SD (pldk_pulse reads them)
P_REM, P_PULSE, P_H, P_LP = range(4)
PI_F = f32(math.pi)


def u(k: int) -> int:
    return K.U0 + k


def ksr(c: float) -> float:
    """c x kSampleRate as Plaits' float32 (its times in samples stay Plaits' at 44.1 kHz)."""
    return f32(f32(c) * 48000.0)


def wbase(p: Prog, L, d: int, k: int) -> None:
    """Rd = the address of union word k. Clobbers R12."""
    p.ld(d, L.md.C["mdb"])                     # the slot's address (I3)
    p.iconst(12, 4 * (MK.S0 + K.U0 + k))
    p.iop(d, 12, "+", d)


def wptr(p: Prog, L, k: int, d: int = 13) -> None:
    """I1 = union word k. Clobbers Rd, R12."""
    wbase(p, L, d, k)
    p.seti(1, d)


def clear(p: Prog, L, n: int) -> None:
    """Union words 0 .. n-1 = 0 (the engine's Init: every state Plaits sets is 0). Clobbers R0-R2,
    R12, R13, I1."""
    wptr(p, L, 0)
    p.iconst(1, 0)
    p.loop_r(2, n, lambda: p.stpost(1, 1))


def _exp2(p: Prog, d: int) -> None:
    """Fd = 2^F15 (plk.exp2p, one copy). Clobbers R0, R1, R12, R14, I12."""
    p.call("pldk_exp2", lambda: K.exp2p(p, 14, 15))
    if d != 14:
        p.fpass(d, 14)


def semis(p: Prog, d: int, x: int) -> None:
    """Fd = SemitonesToRatio(Fx) as plk.semis. Clobbers R0, R1, R12, R14, R15, I12."""
    K.mulk(p, 15, x, 1.0 / 12.0)
    _exp2(p, d)


def note_freq(p: Prog, d: int, x: int) -> None:
    """Fd = NoteToFrequency(Fx) as plk.note_freq. Clobbers R0, R1, R12, R14, R15, I12."""
    K.addk(p, 15, x, -69.0)
    K.mulk(p, 15, 15, 1.0 / 12.0)
    _exp2(p, 14)
    K.mulk(p, d, 14, K.A0)


def on_trig(p: Prog, body) -> None:
    """body() when this half is Plaits' TRIGGER_RISING_EDGE. Clobbers R0."""
    K.ld(p, 0, K.S_TRIG)
    p.ifz(0, "NE", body)


# -- stmlib::Svf -----------------------------------------------------------------------------------
def svf(p: Prog) -> None:
    """Svf::Process at I1 on F8: F9 hp, F10 bp, F11 lp. Clobbers R8-R14, I12."""
    def body():
        p.ldi(13, 0, 1)                        # g
        p.ldi(14, 1, 1)                        # r
        p.ldi(10, 3, 1)                        # s1
        p.fop(14, 14, "*", 10)
        p.fop(9, 8, "-", 14)
        p.fop(14, 13, "*", 10)
        p.fop(9, 9, "-", 14)
        p.ldi(11, 4, 1)                        # s2
        p.fop(9, 9, "-", 11)
        p.ldi(14, 2, 1)                        # h
        p.fop(9, 9, "*", 14)                   # hp
        p.fop(14, 13, "*", 9)
        p.fop(10, 14, "+", 10)                 # bp = g hp + s1
        p.fop(14, 14, "+", 10)
        p.sti(3, 1, 14)                        # s1 = g hp + bp
        p.fop(14, 13, "*", 10)
        p.fop(11, 14, "+", 11)                 # lp = g bp + s2
        p.fop(14, 14, "+", 11)
        p.sti(4, 1, 14)                        # s2 = g bp + lp
    p.call("pldk_svf", body)


def svfset(p: Prog) -> None:
    """Svf::set_f_q at I1 from g = F8 (the tangent) and the resonance F9: r = 1 / F9,
    h = 1 / (1 + r g + g g). Clobbers R10-R14, I12."""
    def body():
        p.sti(0, 1, 8)
        _recip_inline(p, 10, 9, 13)
        p.sti(1, 1, 10)
        p.fop(11, 10, "*", 8)
        K.addk(p, 11, 11, 1.0)
        p.fop(14, 8, "*", 8)
        p.fop(11, 11, "+", 14)
        _recip_inline(p, 10, 11, 13)
        p.sti(2, 1, 10)
    p.call("pldk_svfset", body)


def _pik(c: float, n: int) -> float:
    """c * M_PI * .. (n times), as the C's double expression"""
    x = f32(c)
    for _ in range(n):
        x *= math.pi
    return f32(x)


def tan_dirty(p: Prog, d: int, f: int) -> None:
    """Fd = OnePole::tan<FREQUENCY_DIRTY>(Ff) = f (pi + a f f). Clobbers R12."""
    K.mulk(p, d, f, _pik(3.736e-01, 3))
    p.fop(d, d, "*", f)
    K.addk(p, d, d, PI_F)
    p.fop(d, f, "*", d)


TAN_FAST = (_pik(1.823e-01, 5), _pik(3.260e-01, 3))
TAN_ACC = (_pik(9.5168091e-03, 11), _pik(2.900525e-03, 9), _pik(5.33740603e-02, 7),
           _pik(1.333923995e-01, 5), _pik(3.333314036e-01, 3))


def tan_poly(p: Prog, d: int, f: int, t: int, coefs) -> None:
    """Fd = f (pi + f2 (a + f2 (b + ..))) (FREQUENCY_FAST / ACCURATE; coefs highest first).
    Clobbers Rt, R12. d, f, t distinct."""
    p.fop(t, f, "*", f)                        # f2
    p.fconst(d, coefs[0])
    for c in coefs[1:] + (PI_F,):
        p.fop(d, t, "*", d)
        K.addk(p, d, d, c)
    p.fop(d, f, "*", d)


# -- shapers -----------------------------------------------------------------------------------
def soft(p: Prog) -> None:
    """F15 = SoftClip(F15) = SoftLimit(clamp(x, -3, 3)) (SoftLimit(+-3) is +-1, exactly).
    Clobbers R11-R14, I12."""
    def body():
        K.clamp(p, 15, -3.0, 3.0)
        p.fop(14, 15, "*", 15)
        K.addk(p, 13, 14, 27.0)
        p.fop(13, 15, "*", 13)                 # x (27 + x x)
        K.mulk(p, 14, 15, 9.0)
        p.fop(14, 14, "*", 15)
        K.addk(p, 14, 14, 27.0)                # 27 + 9 x x
        _recip_inline(p, 15, 14, 11)
        p.fop(15, 13, "*", 15)
    p.call("pldk_soft", body)


def diode(p: Prog) -> None:
    """F15 = AnalogBassDrum::Diode(F15): x >= 0 ? x : 0.7 (2x) / (1 + |2x|). Clobbers R11-R14,
    I12."""
    def body():
        def neg():
            p.fop(15, 15, "+", 15)
            K.fabs(p, 14, 15)
            K.addk(p, 14, 14, 1.0)
            K.mulk(p, 13, 15, 0.7)
            _recip_inline(p, 15, 14, 11)
            p.fop(15, 13, "*", 15)
        p.ifz(15, "LT", neg, kind="f")
    p.call("pldk_diode", body)


def pulse(p: Prog) -> None:
    """The 808 trigger pulse (Q39/Q40, Q45/Q46): F9 = pulse, the decay a sample in F8.
    Clobbers R9, R10, R12, I12."""
    def body():
        K.ld(p, 9, u(P_REM))

        def on():
            p.iconst(12, 1)
            p.iop(9, 9, "-", 12)
            K.sv(p, u(P_REM), 9)
            K.ld(p, 10, u(P_H))
            p.ifz(9, "EQ", lambda: K.addk(p, 10, 10, -1.0))
            p.fpass(9, 10)

        def off():
            K.ld(p, 9, u(P_PULSE))
            p.fop(9, 9, "*", 8)
        p.ifz(9, "NE", on, off)
        K.sv(p, u(P_PULSE), 9)
    p.call("pldk_pulse", body)


def one_pole(p: Prog, d: int, k: int, x: int, c: int) -> None:
    """ONE_POLE(word k, Fx, Fc): Fd = word k += c (x - word k). Clobbers R12."""
    K.ld(p, d, u(k))
    p.fop(12, x, "-", d)
    p.fop(12, c, "*", 12)
    p.fop(d, d, "+", 12)
    K.sv(p, u(k), d)


# -- the random generator ------------------------------------------------------------------------
def lcg_jump(n: int) -> tuple[int, int]:
    """(A, C): n GetWord()s at once, x -> A x + C (mod 2^32)."""
    a, c = 1, 0
    for _ in range(n):
        a, c = (a * 1664525) & 0xFFFFFFFF, (c * 1664525 + 1013904223) & 0xFFFFFFFF
    return a, c


def rng_skip(p: Prog, n: int) -> None:
    """The voice's generator n draws on (the AUX voice's, Plaits' shared stmlib::Random).
    Clobbers R13, R14."""
    a, c = lcg_jump(n)
    K.ld(p, 13, K.S_RNG)
    p.iconst(14, a)
    p.mul_ssi(13, 13, 14)
    p.iconst(14, c)
    p.iop(13, 13, "+", 14)
    K.sv(p, K.S_RNG, 13)
