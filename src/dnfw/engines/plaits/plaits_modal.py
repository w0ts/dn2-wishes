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
from ...perc.dsl import Prog, f32
from ...perc import msched as MS

MODEL = "MDAL"
N_MODES, BATCH, MW = 24, 4, 8
(MG, MRG, MH, MA, MS1, MS2, MAMP) = range(7)
BIG_USED = 0
from ...md import core as _MDK
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


def _tan_fast(p: Prog, d: int, f: int, kt: K.KTab | None = None) -> None:
    """Fd = OnePole::tan<FAST>(Ff). Clobbers R11, R12; d is not f. KT: the constants from that pool."""
    k = kt or K
    p.fop(11, f, "*", f)
    k.mulk(p, d, 11, FAST_B)
    k.addk(p, d, d, FAST_A)
    p.fop(d, 11, "*", d)
    k.addk(p, d, d, PI_F)
    p.fop(d, f, "*", d)


def _recip_k(p: Prog, d: int, x: int, kt: K.KTab) -> None:
    """Fd = 1 / Fx as dnfw.perc.machines.recip (the seed 0x7ef311c7 - bits, three Newton steps: the same
    operations), inline and its constants from the pool (2026-11-14: the coefficients' loop's two a mode were
    subroutine calls). Clobbers R12-R14."""
    kt.ld(p, 12, ("i", 0x7EF311C7))
    p.iop(14, 12, "-", x)
    for _ in range(3):
        p.fop(13, x, "*", 14)
        kt.ld(p, 12, 2.0)
        p.fop(13, 12, "-", 13)
        p.fop(14, 14, "*", 13)
    p.fpass(d, 14)


def _h(p: Prog, d: int, r: int, g: int, kt: K.KTab | None = None) -> None:
    """Fd = 1 / (1 + r g + g g). Clobbers R11-R15, I12."""
    p.fop(d, r, "*", g)
    (kt or K).addk(p, d, d, 1.0)
    p.fop(11, g, "*", g)
    p.fop(d, d, "+", 11)
    if kt:
        _recip_k(p, d, d, kt)
    else:
        recip(p, d, d)


def _soften(p: Prog, s: int, kt: K.KTab | None = None) -> None:
    """Fs *= Fs < 0 ? 0.93 : 0.98. Clobbers R11, R12."""
    kc = (lambda d, v: kt.ld(p, d, v)) if kt else (lambda d, v: p.fconst(d, v))
    kc(11, 0.98)
    kc(12, 0.0)
    p.if_(s, "LT", 12, lambda: kc(11, 0.93))
    p.fop(s, s, "*", 11)


def init(p: Prog, L) -> None:
    """ModalEngine::Init + Reset: harmonics_lp_ 0, the filters' states 0, the 24 amplitudes."""
    p.iconst(0, 0)
    for u in (U_HLP, U_ES1, U_ES2):
        K.sv(p, u, 0)
    p.geti(4, 3)
    p.iconst(12, p.ioff(3, 4 * S1_W))
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
    p.iconst(12, p.ioff(3, 4 * (S1_W + AMP_OFF)))
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
    # 2026-11-14 (plaits16, r52): the 24 modes' constants from a pool in the render scratch (XB row KT_ROW, after the
    # excitation's and the outputs' rows) through I2: each load rides on the compute before it. The same values.
    kt = K.KTab(L.XB + 4 * KT_ROW, 2, KT_VALUES)
    kt.write(p)

    def coefs():
        p.fop(4, 1, "*", 2)
        kt.ld(p, 12, 0.499)
        p.fop(4, 4, "MIN", 12)                   # mode_frequency
        _tan_fast(p, 5, 4, kt)
        p.sti(2 * MG, 1, 5)
        p.fop(6, 4, "*", 8)
        kt.addk(p, 6, 6, 1.0)
        _recip_k(p, 6, 6, kt)                    # r = 1 / (1 + f q)
        _h(p, 7, 6, 5, kt)
        p.sti(2 * MH, 1, 7)
        p.fop(6, 6, "+", 5)
        p.sti(2 * MRG, 1, 6)
        p.fop(4, 4, "+", 4)
        kt.ld(p, 12, 1.0)
        p.fop(4, 12, "-", 4)                     # 1 - 2 f
        p.ldpost(5, 5)
        p.fop(5, 5, "*", 4)
        p.sti(2 * MA, 1, 5)
        p.fop(2, 2, "+", 3)                      # stretch += stiffness; stiffness *= k
        _soften(p, 3, kt)
        p.fop(1, 1, "+", 10)                     # harmonic += f0
        p.fop(8, 8, "*", 9)                      # q *= q_loss
        # the next mode's coefficients: a pair's two modes interleave (2026-11-12, simd: PEy reads the word after
        # PEx's), so one word on after an even mode, the next pair's first word after an odd one
        p.geti(0, 1)
        p.iconst(12, 4)
        p.iop(13, 0, "AND", 12)                  # 4 after an odd mode (YB 8-byte aligned), else 0
        p.lsh(5, 13, 4)
        p.lsh(6, 13, 1)
        p.iop(13, 5, "-", 6)                     # 56 or 0
        p.iop(0, 13, "+", 0)
        p.iop(0, 12, "+", 0)                     # + 4
        p.seti(1, 0)
    assert L.YB % 8 == 0
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
# went); then the modes, each mode's states and coefficients in registers through the 16 samples.
# 2026-11-12 (simd): two modes at once, mode m on PEx and m + 1 on PEy (Prog.simd): their states are
# neighbours in the slot already, their coefficients interleave (coefs), the excitation's row holds each
# sample twice (one for each PE) and each mode writes its 16 outputs into its own column of the O rows.
# Each batch of 4 modes is then summed in Plaits' order, ((((0 + o0) + o1) + o2) + o3), and added into
# the half's samples at I4: every value the same operation on the same operands, bit for bit as before.
X_ROW = 0                                        # L.XB + 4 x: the excitation's 16 samples, each twice
KT_ROW = 128                                     # 2026-11-14: the coefficients' constants (plk.KTab)
KT_VALUES = (0.499, FAST_B, FAST_A, PI_F, 1.0, 0.98, 0.0, 0.93, ("i", 0x7EF311C7), 2.0)
O_ROW = 32                                       # the batch's outputs: [2 x sample + lane] a pair, 2 pairs


def _render(p: Prog, L) -> None:
    xr, orow = L.XB + 4 * X_ROW, L.XB + 4 * O_ROW
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
        p.stpost(1, 11)                                # (twice: PEx's and PEy's)
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
    p.iconst(12, p.ioff(3, 4 * S1_W))
    p.iop(0, 12, "+", 0)
    p.seti(0, 0)                                 # I0: the modes' S1 in the slot (S2 S2_OFF on)

    def pair():
        p.ld(9, L.W["bs"])                       # this pair's coefficients
        p.seti(5, 9)
        p.iconst(12, L.YB)                       # its column of the O rows: the batch's first pair or second
        p.iop(13, 9, "-", 12)
        p.iconst(12, 4 * 2 * MW)
        p.iop(13, 13, "AND", 12)
        p.lsh(13, 13, 1)
        p.iconst(12, orow)
        p.iop(13, 12, "+", 13)
        p.seti(2, 13)
        p.iconst(12, 4 * 2 * MW)
        p.iop(9, 12, "+", 9)
        p.st(L.W["bs"], 9)
        p.iconst(13, xr)
        p.seti(1, 13)
        p.simd(lambda: _pair_simd(p))
        p.geti(13, 0)                            # the next pair's states
        p.iconst(12, 8)
        p.iop(13, 12, "+", 13)
        p.seti(0, 13)

    def batch():
        p.loop(L.W["inner"], BATCH // 2, pair)
        _batch_sum(p, orow)
    p.loop(L.W["n4"], N_MODES // BATCH, batch)
    p.geti(0, 4)                                 # I4 past the half, as before
    p.iconst(12, 4 * K.HALF)
    p.iop(0, 12, "+", 0)
    p.seti(4, 0)


def _pair_simd(p: Prog) -> None:
    """Modes m (PEx) and m + 1 (PEy) through the half (in SIMD): I5 their coefficients, I0 their S1, I1 the
    excitation's row, I2 their column of the O rows. The 16 samples' operations as plaits-opt's (2026-11-12),
    placed by dnfw.perc.msched into multifunction instructions with the loads and stores on them; the batch's
    sum is no longer among them (_batch_sum). Registers: F0 g, F1 gain, F2 rg, F3 h (the multiplier's groups),
    F7 s1, F12 s2, F14 t, F8 x / u, F4 u2 / hp, F9 g hp, F15 bp / o, F6 bp (a second add of the same operands,
    for the multiplies), F10 gb, F13 lp."""
    p.ldi(0, 2 * MG, 5)
    p.ldi(2, 2 * MRG, 5)
    p.ldi(3, 2 * MH, 5)
    p.ldi(1, 2 * MA, 5)
    p.ldi(7, 0, 0)                               # s1
    p.ldi(12, S2_OFF, 0)                         # s2
    p.fop(14, 2, "*", 7)                         # t = rg s1
    ops = []
    for k in range(K.HALF):
        ops += [("mov", "ldk", ("F8",), (), ("I1", 2 * k)),              # x
                ("alu", "-", ("F8",), ("F8", "F14"), None),            # u = x - t
                ("alu", "-", ("F4",), ("F8", "F12"), None),            # - s2
                ("mul", "*", ("F4",), ("F3", "F4"), None),             # hp
                ("mul", "*", ("F9",), ("F0", "F4"), None),             # g hp
                ("alu", "+", ("F15",), ("F9", "F7"), None),            # bp
                ("alu", "+", ("F6",), ("F9", "F7"), None),             # bp (for the multiplies)
                ("alu", "+", ("F7",), ("F9", "F15"), None),            # s1
                ("mul", "*", ("F15",), ("F1", "F6"), None),            # o = gain bp
                ("mul", "*", ("F10",), ("F0", "F6"), None),            # gb = g bp
                ("mov", "stk", (), ("F15",), ("I2", 2 * k)),             # o out
                ("alu", "+", ("F13",), ("F10", "F12"), None),          # lp = gb + s2
                ("alu", "+", ("F12",), ("F10", "F13"), None),          # s2
                ("mul", "*", ("F14",), ("F2", "F7"), None)]            # the next t = rg s1
    MS.emit(p, ops)
    p.sti(S2_OFF, 0, 12)
    p.sti(0, 0, 7)


def _batch_sum(p: Prog, orow: int) -> None:
    """The half's samples at I4 += the batch's 4 modes' outputs, summed in Plaits' order (the batch's sum from
    0, then each mode's, then into the sample). I1 the O rows (biased 32 words: offsets -32..31), I2 the
    samples; F15 0. Samples alternate between two sets of registers so one's moves ride on the other's adds."""
    p.iconst(13, orow + 4 * 32)
    p.seti(1, 13)
    p.geti(13, 4)
    p.seti(2, 13)
    p.fconst(15, 0.0)
    ops = []
    for s in range(K.HALF):
        b = 4 * (s % 2)
        o = [f"F{b + j}" for j in range(4)]
        acc, out = f"F{8 + 2 * (s % 2)}", f"F{9 + 2 * (s % 2)}"
        ops += [("mov", "ldk", (o[0],), (), ("I1", 2 * s - 32)),
                ("mov", "ldk", (o[1],), (), ("I1", 2 * s - 31)),
                ("mov", "ldk", (o[2],), (), ("I1", 2 * s)),
                ("mov", "ldk", (o[3],), (), ("I1", 2 * s + 1)),
                ("mov", "ldk", (out,), (), ("I2", s)),
                ("alu", "+", (acc,), ("F15", o[0]), None),
                ("alu", "+", (acc,), (acc, o[1]), None),
                ("alu", "+", (acc,), (acc, o[2]), None),
                ("alu", "+", (acc,), (acc, o[3]), None),
                ("alu", "+", (out,), (out, acc), None),
                ("mov", "stk", (), (out,), ("I2", s))]
    MS.emit(p, ops)


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
