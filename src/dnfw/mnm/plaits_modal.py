"""PLAITS' MDAL: Mutable Instruments Plaits' MODAL engine (MIT, Emilie Gillet:
plaits/dsp/engine/modal_engine.cc, physical_modelling/modal_voice.cc, resonator.cc/.h; stmlib
filter.h, cosine_oscillator.h). OUT only.

HARM (smoothed by a one-pole, 0.01 a block) sets the partials' stiffness (Plaits' lut_stiffness,
here its formula at the same 65 points: interpolated as the table), TIMB the brightness, MORP the
damping. On a trigger an impulse (its size from the excitation's cutoff) through the excitation's
low-pass SVF (Q 1.5) into 24 band-pass SVF modes (FREQUENCY_FAST), their amplitudes from Plaits'
approximate cosine oscillator at 0.015, summed in Plaits' batches of 4.

Memory (2026-11-10, poly16; the voice's DDR until then): each mode's two states and amplitude in the
slot (L1): S1 at W[9 + m], S2 at W[33 + m], the amplitude at slot word 131 + m (the union's free
tail); its coefficients for the half (g, r + g, h, gain) in the render scratch's YB row (L1, MW
words a mode). The same arithmetic: the output is bit for bit as before.
"""

from __future__ import annotations

import math

from . import plk as K
from .plaits_string import (FAST_A, FAST_B, PI_F, ACC_K, exp2, recip)
from ..perc.dsl import Prog, f32

MODEL = "MDAL"
N_MODES, BATCH, MW = 24, 4, 8
(MG, MRG, MH, MA, MS1, MS2, MAMP) = range(7)
BIG_USED = 0
from ..md import core as _MDK
S1_W = 9                                         # slot words: S1 at S1_W + m, S2 24 on, the amplitude 122 on
S2_OFF, AMP_OFF = 24, 122
assert S1_W + S2_OFF + N_MODES <= _MDK.NW
(U_BIG, U_HLP, U_EG, U_ERG, U_EH, U_ES1, U_ES2, U_IMP, U_F0, U_BR, U_DA, U_ST, U_SF, U_HM, U_Q,
 U_QL, U_SA, U_SB, U_I) = (K.U0 + k for k in range(19))
NU_USED = 19

R_EXC = f32(1.0 / 1.5)                           # 1 / q (q 1.5)
IMP_K = f32(f32(0.12) + f32(f32(0.08) * f32(K.ACCENT)))    # 0.12f + 0.08f * accent
LOG2_10 = math.log2(10.0)


def _amps():
    """CosineOscillator::InitApproximate(0.015): its coefficient and first y1."""
    f = f32(f32(0.015) - 0.25)
    sign = 16.0
    if f < 0:
        f = -f
    elif f > 0.5:
        f = f32(f - 0.5)
    else:
        sign = -16.0
    c = f32(f32(sign * f) * f32(1.0 - f32(2.0 * f)))
    return c, f32(c * 0.25)


AMP_C, AMP_Y1 = _amps()


def _tan_fast(p: Prog, d: int, f: int) -> None:
    """Fd = OnePole::tan<FAST>(Ff). Clobbers R11, R12; d is not f."""
    p.fop(11, f, "*", f)
    K.mulk(p, d, 11, FAST_B)
    K.addk(p, d, d, FAST_A)
    p.fop(d, 11, "*", d)
    K.addk(p, d, d, PI_F)
    p.fop(d, f, "*", d)


def _h(p: Prog, d: int, r: int, g: int) -> None:
    """Fd = 1 / (1 + r g + g g). Clobbers R11-R15, I12."""
    p.fop(d, r, "*", g)
    K.addk(p, d, d, 1.0)
    p.fop(11, g, "*", g)
    p.fop(d, d, "+", 11)
    recip(p, d, d)


def _soften(p: Prog, s: int) -> None:
    """Fs *= Fs < 0 ? 0.93 : 0.98. Clobbers R11, R12."""
    p.fconst(11, 0.98)
    p.fconst(12, 0.0)
    p.if_(s, "LT", 12, lambda: p.fconst(11, 0.93))
    p.fop(s, s, "*", 11)


def init(p: Prog, L) -> None:
    """ModalEngine::Init + Reset: harmonics_lp_ 0, the filters' states 0, the 24 amplitudes."""
    p.iconst(0, 0)
    for u in (U_HLP, U_ES1, U_ES2):
        K.sv(p, u, 0)
    p.geti(4, 3)
    p.iconst(12, 4 * S1_W)
    p.iop(4, 12, "+", 4)                         # the first mode's S1 in the slot
    p.iconst(5, 0)
    p.fconst(6, AMP_Y1)                          # y1
    p.fconst(7, 0.5)                             # y0

    def mode():
        p.seti(1, 4)
        p.sti(0, 1, 5)
        p.sti(S2_OFF, 1, 5)
        K.mulk(p, 8, 7, AMP_C)
        p.fop(8, 8, "-", 6)                      # c y0 - y1
        p.fpass(6, 7)
        K.addk(p, 9, 7, 0.5)
        K.mulk(p, 9, 9, 0.25)
        p.sti(AMP_OFF, 1, 9)
        p.fpass(7, 8)
        p.iconst(12, 4)
        p.iop(4, 12, "+", 4)
    p.loop_r(10, N_MODES, mode)


def _stiff_point(p: Prog) -> None:
    """F5 = lookup_tables.py's stiffness at structure U_I / 64."""
    K.ld(p, 0, U_I)
    p.iconst(12, -6)
    p.float_(4, 0, 12)                           # g
    p.fconst(5, 2.0)
    p.iconst(1, 63)

    def below():
        p.iconst(1, 58)

        def tip():                               # 1.5 - cos(pi ((g - 0.9) / 0.1)^2) / 2
            K.addk(p, 4, 4, -0.9)
            K.mulk(p, 4, 4, 10.0)
            p.fop(4, 4, "*", 4)
            K.mulk(p, 4, 4, 0.5)
            K.cosp(p, 5, 4)
            K.mulk(p, 5, 5, -0.5)
            K.addk(p, 5, 5, 1.5)

        def mid():
            p.iconst(1, 20)

            def exp():                           # 0.01 x 10^((g - 0.3) / 0.6 x 2.005) - 0.01
                K.addk(p, 4, 4, -0.3)
                K.mulk(p, 4, 4, 2.005 / 0.6 * LOG2_10)
                exp2(p, 5, 4)
                K.mulk(p, 5, 5, 0.01)
                K.addk(p, 5, 5, -0.01)

            def low():                           # 0 from 0.25, else (g - 0.25) / 4
                K.addk(p, 5, 4, -0.25)
                K.mulk(p, 5, 5, 0.25)
                p.fconst(12, 0.0)
                p.fop(5, 5, "MIN", 12)
            p.if_(0, "GE", 1, exp, low, kind="i")
        p.if_(0, "GE", 1, tip, mid, kind="i")
    p.if_(0, "LT", 1, below, kind="i")


def half(p: Prog, L) -> None:
    """ModalEngine::Render, 16 samples at I4."""
    p.iconst(4, L.YB)                            # the coefficients' row (L1)
    K.sv(p, U_BIG, 4)
    # harmonics_lp_ += 0.01 (harmonics - harmonics_lp_); brightness, damping with the accent
    K.par(p, 4, 0)
    K.ld(p, 5, U_HLP)
    p.fop(4, 4, "-", 5)
    K.mulk(p, 4, 4, 0.01)
    p.fop(5, 5, "+", 4)
    K.sv(p, U_HLP, 5)
    for k, u in ((1, U_BR), (2, U_DA)):
        K.par(p, 4, k)
        p.fconst(12, 1.0)
        p.fop(6, 12, "-", 4)
        K.mulk(p, 6, 6, ACC_K)
        p.fop(4, 4, "+", 6)
        K.sv(p, u, 4)
    K.ld(p, 4, K.S_NOTE)
    K.addk(p, 4, 4, -69.0)
    K.mulk(p, 4, 4, 1.0 / 12.0)
    exp2(p, 5, 4)
    K.mulk(p, 5, 5, K.A0)
    K.sv(p, U_F0, 5)
    # the excitation: cutoff = min(2 f0 2^((b (2 - b) - 0.5) 60 / 12), 0.499), Q 1.5
    K.ld(p, 6, U_BR)
    p.fconst(12, 2.0)
    p.fop(7, 12, "-", 6)
    p.fop(7, 6, "*", 7)
    K.addk(p, 7, 7, -0.5)
    K.mulk(p, 7, 7, 60.0)
    K.mulk(p, 7, 7, 1.0 / 12.0)
    exp2(p, 7, 7)
    p.fop(6, 5, "+", 5)
    p.fop(7, 6, "*", 7)
    p.fconst(12, 0.499)
    p.fop(7, 7, "MIN", 12)                       # cutoff
    _tan_fast(p, 8, 7)
    K.sv(p, U_EG, 8)
    p.fconst(9, R_EXC)
    _h(p, 10, 9, 8)
    K.sv(p, U_EH, 10)
    p.fop(9, 9, "+", 8)
    K.sv(p, U_ERG, 9)
    p.fconst(0, 0.0)
    K.sv(p, U_IMP, 0)
    K.ld(p, 0, K.S_TRIG)

    def trig():                                  # (0.12 + 0.08 accent)(1 - d / 2) 2^(c c 24 / 12) / c
        p.fop(8, 7, "*", 7)
        K.mulk(p, 8, 8, 24.0)
        K.mulk(p, 8, 8, 1.0 / 12.0)
        exp2(p, 8, 8)
        K.ld(p, 6, U_DA)
        K.mulk(p, 6, 6, 0.5)
        p.fconst(12, 1.0)
        p.fop(6, 12, "-", 6)
        K.mulk(p, 6, 6, IMP_K)
        p.fop(8, 6, "*", 8)
        recip(p, 7, 7)
        p.fop(8, 8, "*", 7)
        K.sv(p, U_IMP, 8)
    p.ifz(0, "NE", trig)
    # the stiffness: Interpolate(lut_stiffness, structure, 64), the table's two points computed
    K.ld(p, 4, U_HLP)
    K.mulk(p, 4, 4, 64.0)
    K.ifrac(p, 0, 5, 4)
    K.sv(p, U_I, 0)
    K.sv(p, U_SF, 5)

    def point():                                 # U_SA, U_SB = the points at i, i + 1
        _stiff_point(p)
        K.ld(p, 6, U_SB)
        K.sv(p, U_SA, 6)
        K.sv(p, U_SB, 5)
        K.ld(p, 0, U_I)
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
        K.sv(p, U_I, 0)
    p.loop(L.W["n5"], 2, point)
    K.ld(p, 5, U_SB)
    K.ld(p, 4, U_SA)
    p.fop(5, 5, "-", 4)
    K.ld(p, 6, U_SF)
    p.fop(5, 5, "*", 6)
    p.fop(5, 4, "+", 5)
    K.sv(p, U_ST, 5)                             # stiffness
    # f0 *= 1 / NthHarmonicCompensation(3): 1 + s + s k(s)
    p.fpass(6, 5)
    K.addk(p, 7, 6, 1.0)
    _soften(p, 6)
    p.fop(7, 7, "+", 6)
    recip(p, 7, 7)
    K.ld(p, 5, U_F0)
    p.fop(5, 5, "*", 7)
    K.sv(p, U_F0, 5)
    K.sv(p, U_HM, 5)                             # harmonic
    p.fconst(0, 1.0)
    K.sv(p, U_SF, 0)                             # stretch_factor
    # q = 500 2^(d 79.7 / 12)^2; brightness's loss
    K.ld(p, 6, U_DA)
    K.mulk(p, 7, 6, 79.7)
    K.mulk(p, 7, 7, 1.0 / 12.0)
    exp2(p, 7, 7)
    K.mulk(p, 8, 7, 500.0)
    p.fop(8, 8, "*", 7)
    K.sv(p, U_Q, 8)
    K.ld(p, 4, U_BR)
    for r in (None, 6):
        if r is None:
            K.ld(p, 9, U_HLP)
        else:
            p.fpass(9, 6)
        K.mulk(p, 9, 9, 0.3)
        p.fconst(12, 1.0)
        p.fop(9, 12, "-", 9)
        p.fop(4, 4, "*", 9)
    p.fconst(12, 2.0)
    p.fop(9, 12, "-", 4)
    p.fop(9, 4, "*", 9)
    K.mulk(p, 9, 9, 0.85)
    K.addk(p, 9, 9, 0.15)
    K.sv(p, U_QL, 9)
    # the modes' coefficients
    K.ld(p, 4, U_BIG)
    p.seti(1, 4)
    p.geti(4, 3)
    p.iconst(12, 4 * (S1_W + AMP_OFF))
    p.iop(4, 12, "+", 4)
    p.seti(5, 4)                                 # the amplitudes (slot), walked by I5

    # 2026-11-10 (poly16): the running words in registers through the 24 modes (F1 harmonic, F2
    # stretch, F3 stiffness, F8 q, F9 q's loss, F10 f0; recip, _h, _tan_fast and _soften clobber
    # none of them), written back after: the same operations in the same order
    K.ld(p, 1, U_HM)
    K.ld(p, 2, U_SF)
    K.ld(p, 3, U_ST)
    K.ld(p, 8, U_Q)
    K.ld(p, 9, U_QL)
    K.ld(p, 10, U_F0)

    def coefs():
        p.fop(4, 1, "*", 2)
        p.fconst(12, 0.499)
        p.fop(4, 4, "MIN", 12)                   # mode_frequency
        _tan_fast(p, 5, 4)
        p.sti(MG, 1, 5)
        p.fop(6, 4, "*", 8)
        K.addk(p, 6, 6, 1.0)
        recip(p, 6, 6)                           # r = 1 / (1 + f q)
        _h(p, 7, 6, 5)
        p.sti(MH, 1, 7)
        p.fop(6, 6, "+", 5)
        p.sti(MRG, 1, 6)
        p.fop(4, 4, "+", 4)
        p.fconst(12, 1.0)
        p.fop(4, 12, "-", 4)                     # 1 - 2 f
        p.ldpost(5, 5)
        p.fop(5, 5, "*", 4)
        p.sti(MA, 1, 5)
        p.fop(2, 2, "+", 3)                      # stretch += stiffness; stiffness *= k
        _soften(p, 3)
        p.fop(1, 1, "+", 10)                     # harmonic += f0
        p.fop(8, 8, "*", 9)                      # q *= q_loss
        p.geti(0, 1)                             # the next mode's coefficients
        p.iconst(12, 4 * MW)
        p.iop(0, 12, "+", 0)
        p.seti(1, 0)
    p.loop(L.W["n5"], N_MODES, coefs)
    K.sv(p, U_HM, 1)
    K.sv(p, U_SF, 2)
    K.sv(p, U_ST, 3)
    K.sv(p, U_Q, 8)
    p.geti(0, 1)
    K.sv(p, U_BIG, 0)
    _render(p, L)


# 2026-11-10 (poly16, the User: 16 voices on every engine): the half mode by mode, not sample by
# sample. The excitation's 16 samples first (a row in L1, L.XB: SID's phases' room, free since SID
# went); then each batch of 4 modes, each mode's states and coefficients in registers through the
# 16 samples (3 DDR words read and 2 written a mode a half, not 7 a sample), its gain x bp added into
# the batch's row (L1), each batch then added into the half's samples at I4: every sample's sums in
# Plaits' order, so the output is the same, bit for bit.
X_ROW = 0                                        # L.XB + 4 x: the excitation's 16 samples
B_ROW = 16                                       # the batch's 16 sums


def _render(p: Prog, L) -> None:
    xr, br = L.XB + 4 * X_ROW, L.XB + 4 * B_ROW
    # the excitation's low-pass (ResonatorSvf<1>), 16 samples into the X row; the impulse once
    K.ld(p, 2, U_ES1)
    K.ld(p, 3, U_ES2)
    K.ld(p, 4, U_EG)
    K.ld(p, 5, U_ERG)
    K.ld(p, 6, U_EH)
    K.ld(p, 1, U_IMP)
    p.fconst(0, 0.0)
    K.sv(p, U_IMP, 0)
    p.iconst(9, xr)
    p.seti(1, 9)

    def exc():
        _res_svf(p, 1, 2, 3, 4, 5, 6)
        p.par(("op", 1, 0, "+", 0), ("st", 1, 11))    # the input after the impulse: 0 (F0's 0 + 0)
    p.loop_r(15, K.HALF, exc)
    K.sv(p, U_ES1, 2)
    K.sv(p, U_ES2, 3)
    # the half's samples at I4: 0
    p.fconst(0, 0.0)
    for k in range(K.HALF):
        p.sti(k, 4, 0)
    p.iconst(9, L.YB)
    K.sv(p, U_BIG, 9)                            # (as the sample loop left it)
    p.st(L.W["bs"], 9)                          # the modes' coefficients' pointer (2026-11-10)
    p.geti(0, 3)
    p.iconst(12, 4 * S1_W)
    p.iop(0, 12, "+", 0)
    p.seti(0, 0)                                 # I0: the modes' S1 in the slot (S2 S2_OFF on)

    def batch():
        p.iconst(0, br)
        p.seti(5, 0)
        p.fconst(0, 0.0)
        for k in range(K.HALF):
            p.stpost(5, 0)

        def mode():
            # 2026-11-10 (poly16): the loads and the store on computes, the 16 samples unrolled
            # (every F register taken): 12 instructions a sample, not 12+3. (Multifunction pairs
            # were tried: selmap reads selas's float multiply as MRF + x y: dsl.par refuses them.)
            # F0 g, F1 rg, F2 h, F3 gain, F5 s1, F12 s2; F4 bp, F6 t, F8 gb, F9 the batch's sum,
            # F10 lp, F11 u / hp, F13 o, F14 x, F15 g hp. The same operations in the same order.
            p.ld(9, L.W["bs"])                  # this mode's coefficients
            p.seti(1, 9)
            p.ldi(0, MG, 1)
            p.ldi(1, MRG, 1)
            p.ldi(2, MH, 1)
            p.ldi(3, MA, 1)
            p.iconst(12, 4 * MW)
            p.iop(9, 12, "+", 9)
            p.st(L.W["bs"], 9)
            p.ldi(5, 0, 0)                       # s1
            p.ldi(12, S2_OFF, 0)                 # s2
            p.iconst(13, xr)
            p.seti(1, 13)
            p.iconst(13, br)
            p.seti(2, 13)                        # (I2: a compute's move goes through I0..I3)
            p.ldpost(14, 1)                      # x
            p.fop(6, 1, "*", 5)                  # t = rg s1
            for k in range(K.HALF):
                p.fop(11, 14, "-", 6)            # u = x - t
                p.fop(11, 11, "-", 12)           # - s2
                p.par(("op", 11, 11, "*", 2), ("ldk", 9, 0, 2))   # hp; the batch's sum
                p.fop(15, 0, "*", 11)            # g hp
                p.fop(4, 15, "+", 5)             # bp
                p.fop(13, 3, "*", 4)             # o = gain bp
                p.fop(5, 15, "+", 4)             # s1
                p.fop(8, 0, "*", 4)              # gb = g bp
                p.fop(9, 9, "+", 13)             # B += o
                p.fop(6, 1, "*", 5)              # the next t = rg s1
                p.par(("op", 10, 8, "+", 12), ("ld", 14, 1))     # lp = gb + s2; the next x
                p.par(("op", 12, 8, "+", 10), ("st", 2, 9))       # s2; B out
            p.sti(S2_OFF, 0, 12)
            p.stpost(0, 5)                       # the next mode's
        p.loop(L.W["inner"], BATCH, mode)
        p.iconst(0, br)
        p.seti(5, 0)
        p.geti(0, 4)
        p.seti(1, 0)

        def add4():                              # out += the batch's sum
            for k in range(4):
                p.ldpost(1, 5)
                p.ldi(0, 0, 1)
                p.fop(0, 0, "+", 1)
                p.stpost(1, 0)
        p.loop_r(15, K.HALF // 4, add4)
    p.loop(L.W["n4"], N_MODES // BATCH, batch)
    p.geti(0, 4)                                 # I4 past the half, as before
    p.iconst(12, 4 * K.HALF)
    p.iop(0, 12, "+", 0)
    p.seti(4, 0)


def _res_svf(p: Prog, x: int, s1: int, s2: int, g: int, rg: int, h: int) -> None:
    """ResonatorSvf's step on Fx: F7 = bp, F8 = lp, Fs1 / Fs2 the new states. Clobbers R7,
    R8, R11."""
    p.fop(11, rg, "*", s1)
    p.fop(11, x, "-", 11)
    p.fop(11, 11, "-", s2)
    p.fop(11, 11, "*", h)                        # hp
    p.fop(11, g, "*", 11)                        # g hp
    p.fop(7, 11, "+", s1)                        # bp
    p.fop(s1, 11, "+", 7)
    p.fop(8, g, "*", 7)                          # g bp
    p.fop(11, 8, "+", s2)                        # lp
    p.fop(s2, 8, "+", 11)
    p.fpass(8, 11)
