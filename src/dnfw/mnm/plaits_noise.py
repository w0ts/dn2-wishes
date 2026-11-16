"""PLAITS' NOISE: Mutable Instruments Plaits' filtered noise engine (Emilie Gillet, MIT;
plaits/dsp/engine/noise_engine.cc, dsp/noise/clocked_noise.h, stmlib dsp/filter.h Svf).

OUT only: the clocked noise (TIMB the clock, -24..128 semitones: the trigger is patched; a trig
syncs it) through the state-variable filter at the note (MORP its resonance, 0.5 x 2^(10 morph),
HARM crossfading LP -> BP -> HP), its input gain 1 / sqrt((0.5 + q) 40 f0). The second clocked
noise and the two band-passes feed Plaits' AUX only and are not rendered; the second noise's
16 random numbers a block are still taken from the generator (rng_skip), so the sequence is
Plaits'.

The state-variable filter (its coefficients and its tick) and 1 / sqrt are subroutines PART
(plaits_part) calls too.
"""

from __future__ import annotations

import math
import struct

from . import core as C
from . import plk as K
from ..perc.dsl import Prog
from ..perc.machines import _recip_inline

MODEL = "NOIS"
(PH, SMP, NXT, CF, F0, Q, MD, S1, S2,              # the clocked noise, the interpolators, the Svf
 CFI, F0I, QI, MDI) = (K.U0 + k for k in range(13))  # per half: the interpolators' steps
NU_USED = 13
BIG_USED = 0


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _pi_pow(c: float, n: int) -> float:
    """the C's `c##f * M_PI * ..` (n factors, double, left to right) as the float it is"""
    v = _f32(c)
    for _ in range(n):
        v *= math.pi
    return _f32(v)


PI_F = _f32(math.pi)
TAN_ACC = (_pi_pow(3.333314036e-01, 3), _pi_pow(1.333923995e-01, 5), _pi_pow(5.33740603e-02, 7),
           _pi_pow(2.900525e-03, 9), _pi_pow(9.5168091e-03, 11))     # OnePole::tan ACCURATE
TAN_DIRTY = _pi_pow(3.736e-01, 3)

# stmlib::Random 16 draws at once: x -> A16 x + C16 (mod 2^32)
_A, _C = 1664525, 1013904223
A16, C16 = 1, 0
for _ in range(16):
    A16, C16 = (A16 * _A) & 0xFFFFFFFF, (C16 * _A + _C) & 0xFFFFFFFF


# -- shared subroutines (PART calls them too) ----------------------------------------------------
def svf_set(p: Prog) -> None:
    """Svf::set_f_q's rest: F2 = r = 1 / F6 (the resonance), F3 = h = 1 / (1 + r g + g g), g in F1.
    Clobbers R7, R8, R12, I12."""
    def body():
        _recip_inline(p, 2, 6, 7)
        p.fop(7, 2, "*", 1)
        K.addk(p, 7, 7, 1.0)
        p.fop(8, 1, "*", 1)
        p.fop(7, 7, "+", 8)
        _recip_inline(p, 3, 7, 8)
    p.call("plnoise_svfset", body)


def svf_tick(p: Prog) -> None:
    """Svf::Process: in F0, g r h in F1-F3, the state s1 s2 in F4 F5 (updated) -> F6 hp, F7 bp,
    F8 lp. Clobbers R9, R12, I12."""
    def body():
        p.fop(9, 2, "*", 4)
        p.fop(6, 0, "-", 9)
        p.fop(9, 1, "*", 4)
        p.fop(6, 6, "-", 9)
        p.fop(6, 6, "-", 5)
        p.fop(6, 6, "*", 3)                    # hp
        p.fop(9, 1, "*", 6)
        p.fop(7, 9, "+", 4)                    # bp
        p.fop(4, 9, "+", 7)
        p.fop(9, 1, "*", 7)
        p.fop(8, 9, "+", 5)                    # lp
        p.fop(5, 9, "+", 8)
    p.call("plnoise_svf", body)


def rsqrt(p: Prog) -> None:
    """F14 = 1 / sqrt(F13) (F13 > 0): the seed 0x5f3759df - bits / 2, two Newton steps.
    Clobbers R11-R13, I12."""
    def body():
        p.iconst(12, 0x5F3759DF)
        p.lsh(14, 13, -1)
        p.iop(14, 12, "-", 14)
        K.mulk(p, 13, 13, 0.5)                 # x / 2
        p.fconst(11, 1.5)
        for _ in range(2):
            p.fop(12, 14, "*", 14)
            p.fop(12, 12, "*", 13)
            p.fop(12, 11, "-", 12)
            p.fop(14, 14, "*", 12)
    p.call("plnoise_rsqrt", body)


def exp2(p: Prog, d: int, x: int) -> None:
    """Fd = 2^Fx as plk.exp2p, a subroutine (NOISE and PART take it at several places). Clobbers
    R0-R3, R12, I12."""
    if x != 2:
        p.fpass(2, x)
    p.call("plnoise_exp2", lambda: K.exp2p(p, 3, 2))
    if d != 3:
        p.fpass(d, 3)


def semis(p: Prog, d: int, x: int) -> None:
    """Fd = 2^(Fx / 12) (plk.semis). Clobbers R0-R3, R12, I12."""
    K.mulk(p, 2, x, 1.0 / 12.0)
    exp2(p, d, 2)


def note_freq(p: Prog, d: int, x: int) -> None:
    """Fd = A0 x 2^((Fx - 69) / 12) (plk.note_freq). Clobbers R0-R3, R12, I12."""
    K.addk(p, 2, x, -69.0)
    K.mulk(p, 2, 2, 1.0 / 12.0)
    exp2(p, d, 2)
    K.mulk(p, d, d, K.A0)


def tan_dirty(p: Prog, d: int, f: int) -> None:
    """Fd = OnePole::tan<FREQUENCY_DIRTY>(Ff) = f (pi + a f f). d is not f. Clobbers R12."""
    K.mulk(p, d, f, TAN_DIRTY)
    p.fop(d, d, "*", f)
    K.addk(p, d, d, PI_F)
    p.fop(d, f, "*", d)


# -- the engine ----------------------------------------------------------------------------------
def init(p: Prog, L: C.Layout) -> None:
    """NoiseEngine::Init: the clocked noise at phase 0 (its frequency 0.001), the filter's state
    and the interpolators at 0."""
    K.zero_state(p, K.U0, NU_USED)
    p.fconst(0, 0.001)
    K.sv(p, CF, 0)


def _params(p: Prog) -> None:
    K.ld(p, 4, K.S_NOTE)
    note_freq(p, 5, 4)                       # f0
    K.interp_start(p, F0I, F0, 5)
    K.par(p, 6, 1)                             # the clock: timbre x 152 - 24 (patched)
    K.mulk(p, 6, 6, 152.0)
    K.addk(p, 6, 6, -24.0)
    note_freq(p, 7, 6)
    K.clamp(p, 7, 0.0, 1.0)
    K.interp_start(p, CFI, CF, 7)
    K.par(p, 6, 2)                             # q = 0.5 x SemitonesToRatio(morph x 120)
    K.mulk(p, 6, 6, 120.0)
    semis(p, 7, 6)
    K.mulk(p, 7, 7, 0.5)
    K.interp_start(p, QI, Q, 7)
    K.par(p, 6, 0)                             # the mode: harmonics
    K.interp_start(p, MDI, MD, 6)
    K.ld(p, 0, K.S_TRIG)

    def sync():
        p.fconst(0, 1.0)
        K.sv(p, PH, 0)
    p.ifz(0, "NE", sync)


def _clocked(p: Prog) -> None:
    """One sample of ClockedNoise::Render -> F10."""
    K.interp_next(p, 4, CF, CFI)               # frequency
    K.rnd01(p, 5)
    p.fop(5, 5, "+", 5)
    K.addk(p, 5, 5, -1.0)                      # raw
    K.addk(p, 6, 4, -0.25)
    K.mulk(p, 6, 6, 4.0)
    K.clamp(p, 6, 0.0, 1.0)                    # raw_amount
    K.ld(p, 7, PH)
    p.fop(7, 7, "+", 4)
    K.ld(p, 8, NXT)                            # this
    p.fconst(9, 0.0)                           # next
    K.ld(p, 10, SMP)
    p.fconst(11, 1.0)

    def wrap():
        p.fop(7, 7, "-", 11)
        _recip_inline(p, 0, 4, 1)
        p.fop(0, 7, "*", 0)                    # t = phase / frequency
        p.fop(1, 5, "-", 10)                   # the discontinuity
        K.mulk(p, 2, 0, 0.5)
        p.fop(2, 2, "*", 0)
        p.fop(2, 1, "*", 2)
        p.fop(8, 8, "+", 2)
        p.fop(2, 11, "-", 0)
        K.mulk(p, 3, 2, -0.5)
        p.fop(3, 3, "*", 2)
        p.fop(3, 1, "*", 3)
        p.fop(9, 9, "+", 3)
        p.fpass(10, 5)
        K.sv(p, SMP, 10)
    p.if_(7, "GE", 11, wrap)
    K.sv(p, PH, 7)
    p.fop(9, 9, "+", 10)
    K.sv(p, NXT, 9)
    p.fop(5, 5, "-", 8)
    p.fop(5, 6, "*", 5)
    p.fop(10, 8, "+", 5)


def _filter(p: Prog) -> None:
    """One sample of the LP-BP-HP Svf on F10 -> stored at I4."""
    K.interp_next(p, 15, F0, F0I)
    K.interp_next(p, 6, Q, QI)
    K.addk(p, 13, 6, 0.5)
    K.mulk(p, 13, 13, 40.0)
    p.fop(13, 13, "*", 15)
    rsqrt(p)                                   # the gain
    p.fop(0, 10, "*", 14)
    # g = OnePole::tan<FREQUENCY_ACCURATE>(f0)
    a, b, c, d, e = TAN_ACC
    p.fop(2, 15, "*", 15)
    p.fconst(3, e)
    for k in (d, c, b, a):
        p.fop(3, 2, "*", 3)
        K.addk(p, 3, 3, k)
    p.fop(3, 2, "*", 3)
    K.addk(p, 3, 3, PI_F)
    p.fop(1, 15, "*", 3)
    svf_set(p)
    K.ld(p, 4, S1)
    K.ld(p, 5, S2)
    svf_tick(p)
    K.sv(p, S1, 4)
    K.sv(p, S2, 5)
    # ProcessMultimodeLPtoHP's gains
    K.interp_next(p, 9, MD, MDI)
    K.mulk(p, 10, 9, -2.0)
    K.addk(p, 10, 10, 1.0)                     # 1 - 2 mode
    p.fconst(12, 0.0)
    p.fop(11, 10, "MIN", 12)                   # hp
    p.fop(13, 10, "MAX", 12)                   # lp
    K.addk(p, 14, 9, -0.5)
    K.fabs(p, 14, 14)
    p.fop(14, 14, "+", 14)
    p.fconst(12, 1.0)
    p.fop(14, 12, "-", 14)                     # bp
    p.fop(6, 11, "*", 6)
    p.fop(7, 14, "*", 7)
    p.fop(6, 6, "+", 7)
    p.fop(8, 13, "*", 8)
    p.fop(6, 6, "+", 8)
    p.stpost(4, 6)


def rng_skip16(p: Prog) -> None:
    """the voice's stmlib::Random 16 draws on (the second clocked noise's). Clobbers R13, R14."""
    K.ld(p, 13, K.S_RNG)
    p.iconst(14, A16)
    p.mul_ssi(13, 13, 14)
    p.iconst(14, C16)
    p.iop(13, 13, "+", 14)
    K.sv(p, K.S_RNG, 13)


def half(p: Prog, L: C.Layout) -> None:
    _params(p)

    def one():
        _clocked(p)
        _filter(p)
    p.loop(L.W["n4"], K.HALF, one)
    rng_skip16(p)
