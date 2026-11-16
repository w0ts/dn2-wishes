"""PLAITS' VA: Plaits' VIRTUAL ANALOG engine's OUT (engine/virtual_analog_engine.cc, VA_VARIANT 2,
the shipped one; oscillator/variable_shape_oscillator.h, variable_saw_oscillator.h; MIT,
THIRD-PARTY.md). docs/plaits.md.

OUT = a variable saw (MORPH: its notch / pulse width and its triangle; detuned from the note by
HARMONICS' interval) + a square hard-synced to the note (TIMBRE: its pulse width, the sync's
interval above the note, its level). Plaits' primary_ and auxiliary_ oscillators only feed AUX
(the track is mono): not rendered.

One deviation: the synced square is Plaits' VariableShapeOscillator at waveshape 1.0, its only
value here; Plaits starts its waveshape_ at 0 and ramps it to 1 over the first block, this one
starts at 1 (the first 16 samples after VA is chosen differ). So its triangle terms are always 0
and are left out.

Each band-limited edge (the square's rise, fall and sync reset, the saw's notch and wrap) goes
through one subroutine (`_edge`): a poly-BLEP step times F3 and an integrated poly-BLEP times F9
(stmlib polyblep.h) added to this sample and the next.
"""

from __future__ import annotations

from . import core as C
from . import plk as K
from ..perc.dsl import Prog

MODEL = "VA"
DEPTH = 0.2                                    # kVariableSawNotchDepth
INTERVALS = (0.0, 7.01, 12.01, 19.01, 24.01)

# union words: the sync square, the variable saw, the gains, then per-sample scratch
(MP, SP, SNX, SPPW, SHI, SMF, SSF, SPW, DMF, DSF, DPW,
 PH, VNX, VPPW, VHI, VF, VPW, VWS, DVF, DVPW, DVWS,
 GSQ, GSW, DGSQ, DGSW,
 T_THIS, T_NX, T_SQ, T_RT, T_RES, T_TR, T_BRK, T_PW, T_SF, T_UP, T_DN, T_F, T_TRI, T_NA,
 T_TS) = range(K.U0, K.U0 + 40)
NU_USED = 40
BIG_USED = 0


def _ld(p, d, k):
    K.ld(p, d, k)


def _sv(p, k, s):
    K.sv(p, k, s)


def init(p: Prog, L: C.Layout) -> None:
    """Both oscillators as Plaits' Init (the square's waveshape at 1.0, see above), the gains at 0."""
    p.fconst(0, 0.0)
    for k in (MP, SP, SNX, SHI, SMF, PH, VNX, VHI, VWS, GSQ, GSW):
        _sv(p, k, 0)
    p.fconst(0, 0.5)
    for k in (SPPW, SPW, VPPW, VPW):
        _sv(p, k, 0)
    p.fconst(0, 0.01)
    _sv(p, SSF, 0)
    _sv(p, VF, 0)


# -- the edges -----------------------------------------------------------------------------------
def _nib(p: Prog, d: int, t: int) -> None:
    """Fd = NextIntegratedBlepSample(Ft): (0.1875 - t/2 + 1.5 (t/2)^2) - (t/2)^4. Clobbers R12-R15."""
    p.fconst(12, 0.5)
    p.fop(13, t, "*", 12)                      # t1
    p.fop(14, 13, "*", 13)                     # t2
    p.fop(15, 14, "*", 14)                     # t4
    p.fconst(12, 0.1875)
    p.fop(d, 12, "-", 13)
    p.fconst(12, 1.5)
    p.fop(14, 14, "*", 12)
    p.fop(d, d, "+", 14)
    p.fop(d, d, "-", 15)


def _edge_body(p: Prog) -> None:
    """this += F3 ThisBlep(t) - F9 ThisIntegratedBlep(t), next += F3 NextBlep(t) - F9
    NextIntegratedBlep(t), t in F8 (T_THIS, T_NX). Clobbers R4-R7, R10-R15."""
    p.fop(10, 8, "*", 8)
    p.fconst(12, 0.5)
    p.fop(10, 10, "*", 12)                     # ThisBlep
    p.fconst(12, 1.0)
    p.fop(11, 12, "-", 8)                      # 1 - t
    p.fop(7, 11, "*", 11)
    p.fconst(12, -0.5)
    p.fop(7, 7, "*", 12)                       # NextBlep
    _ld(p, 4, T_THIS)
    _ld(p, 5, T_NX)
    p.fop(10, 3, "*", 10)
    p.fop(4, 4, "+", 10)
    p.fop(7, 3, "*", 7)
    p.fop(5, 5, "+", 7)
    _nib(p, 6, 11)                             # ThisIntegratedBlep(t) = Next..(1 - t)
    p.fop(6, 9, "*", 6)
    p.fop(4, 4, "-", 6)
    _nib(p, 6, 8)
    p.fop(6, 9, "*", 6)
    p.fop(5, 5, "-", 6)
    _sv(p, T_THIS, 4)
    _sv(p, T_NX, 5)


def _edge(p: Prog) -> None:
    p.call("plva_edge", lambda: _edge_body(p))


def _edge_k(p: Prog, notch: float, ts: float = 0.0) -> None:
    """an edge of constant height (the square's): F3 = notch, F9 = ts, t in F8."""
    p.fconst(3, notch)
    p.fconst(9, ts)
    _edge(p)


# -- the synced square ---------------------------------------------------------------------------
def _sq_sample(p: Prog) -> None:
    """VariableShapeOscillator::Render<true, false> at waveshape 1 -> T_SQ."""
    _ld(p, 4, SNX)
    _sv(p, T_THIS, 4)
    p.fconst(0, 0.0)
    _sv(p, T_NX, 0)
    K.interp_next(p, 5, SMF, DMF)              # the master's frequency
    K.interp_next(p, 6, SSF, DSF)
    _sv(p, T_SF, 6)
    K.interp_next(p, 7, SPW, DPW)
    _sv(p, T_PW, 7)
    p.iconst(0, 0)
    _sv(p, T_RES, 0)
    _sv(p, T_TR, 0)
    _ld(p, 4, MP)
    p.fop(4, 4, "+", 5)
    _sv(p, MP, 4)
    p.fconst(12, 1.0)

    def reset():
        p.fconst(12, 1.0)
        p.fop(4, 4, "-", 12)
        _sv(p, MP, 4)
        K.recip(p, 9, 5)
        p.fop(9, 4, "*", 9)                    # reset_time
        _sv(p, T_RT, 9)
        _ld(p, 10, SP)
        p.fconst(12, 1.0)
        p.fop(11, 12, "-", 9)
        _ld(p, 6, T_SF)
        p.fop(11, 11, "*", 6)
        p.fop(10, 10, "+", 11)                 # the slave's phase at the reset
        p.iconst(0, 1)
        _sv(p, T_RES, 0)
        p.fconst(12, 1.0)

        def over():
            p.fop(10, 10, "-", 12)
            p.iconst(0, 1)
            _sv(p, T_TR, 0)
        p.if_(10, "GE", 12, over)
        _ld(p, 0, SHI)
        _ld(p, 7, T_PW)

        def low():
            def cross():
                p.iconst(0, 1)
                _sv(p, T_TR, 0)
            p.if_(10, "GE", 7, cross)
        p.ifz(0, "EQ", low)
        _ld(p, 8, T_RT)
        p.if_(10, "GE", 7, lambda: _edge_k(p, -1.0))     # the naive value (1 once high) stepped away
    p.if_(4, "GE", 12, reset)
    _ld(p, 6, SP)
    _ld(p, 5, T_SF)
    p.fop(6, 6, "+", 5)
    _sv(p, SP, 6)
    # the transitions (one pass: the loop's second always breaks, the slave's phase < f <= pw / 2)
    _ld(p, 0, T_TR)
    _ld(p, 1, T_RES)
    p.iconst(12, 1)
    p.iop(1, 12, "-", 1)
    p.iop(0, 0, "OR", 1)

    def transitions():
        p.iconst(0, 0)
        _sv(p, T_BRK, 0)
        _ld(p, 0, SHI)

        def low():
            _ld(p, 6, SP)
            _ld(p, 7, T_PW)

            def rise():
                _ld(p, 9, SPPW)
                p.fop(9, 9, "-", 7)
                _ld(p, 5, T_SF)
                p.fop(9, 9, "+", 5)
                K.recip(p, 9, 9)
                _ld(p, 6, SP)
                _ld(p, 7, T_PW)
                p.fop(8, 6, "-", 7)
                p.fop(8, 8, "*", 9)
                _edge_k(p, 1.0)
                p.iconst(0, 1)
                _sv(p, SHI, 0)

            def brk():
                p.iconst(0, 1)
                _sv(p, T_BRK, 0)
            p.if_(6, "GE", 7, rise, brk)
        p.ifz(0, "EQ", low)
        _ld(p, 0, SHI)
        _ld(p, 1, T_BRK)
        p.iconst(12, 1)
        p.iop(1, 12, "-", 1)
        p.iop(0, 0, "AND", 1)

        def high():
            _ld(p, 6, SP)
            p.fconst(12, 1.0)

            def fall():
                p.fconst(12, 1.0)
                p.fop(6, 6, "-", 12)
                _sv(p, SP, 6)
                _ld(p, 5, T_SF)
                K.recip(p, 9, 5)
                _ld(p, 6, SP)
                p.fop(8, 6, "*", 9)
                _edge_k(p, -1.0)
                p.iconst(0, 0)
                _sv(p, SHI, 0)
            p.if_(6, "GE", 12, fall)
        p.ifz(0, "NE", high)
    p.ifz(0, "NE", transitions)
    _ld(p, 0, T_RES)

    def after_reset():
        _ld(p, 9, T_RT)
        _ld(p, 5, T_SF)
        p.fop(9, 9, "*", 5)
        _sv(p, SP, 9)
        p.iconst(0, 0)
        _sv(p, SHI, 0)
    p.ifz(0, "NE", after_reset)
    _ld(p, 5, T_NX)
    _ld(p, 6, SP)
    _ld(p, 7, T_PW)
    p.if_(6, "GE", 7, lambda: (p.fconst(12, 1.0), p.fop(5, 5, "+", 12)))
    _sv(p, SNX, 5)
    _sv(p, SPPW, 7)
    _ld(p, 4, T_THIS)
    p.fop(4, 4, "+", 4)
    K.addk(p, 4, 4, -1.0)
    _sv(p, T_SQ, 4)


# -- the variable saw ----------------------------------------------------------------------------
def _saw_ts(p: Prog) -> None:
    """F9 = (up + down) f x triangle (the integrated step)."""
    _ld(p, 9, T_UP)
    _ld(p, 5, T_DN)
    p.fop(9, 9, "+", 5)
    _ld(p, 5, T_F)
    p.fop(9, 9, "*", 5)
    _ld(p, 5, T_TRI)
    p.fop(9, 9, "*", 5)


def _saw_sample(p: Prog) -> None:
    """VariableSawOscillator::Render, one sample -> F4."""
    _ld(p, 4, VNX)
    _sv(p, T_THIS, 4)
    p.fconst(0, 0.0)
    _sv(p, T_NX, 0)
    K.interp_next(p, 5, VF, DVF)
    _sv(p, T_F, 5)
    K.interp_next(p, 6, VPW, DVPW)
    _sv(p, T_PW, 6)
    K.interp_next(p, 7, VWS, DVWS)
    _sv(p, T_TRI, 7)
    p.fconst(12, 1.0)
    p.fop(7, 12, "-", 7)
    _sv(p, T_NA, 7)
    K.recip(p, 8, 6)
    _sv(p, T_UP, 8)
    _ld(p, 6, T_PW)
    p.fconst(12, 1.0)
    p.fop(6, 12, "-", 6)
    K.recip(p, 8, 6)
    _sv(p, T_DN, 8)
    _ld(p, 4, PH)
    _ld(p, 5, T_F)
    p.fop(4, 4, "+", 5)
    _sv(p, PH, 4)
    _ld(p, 6, T_PW)
    p.iconst(1, 0)
    p.if_(4, "GE", 6, lambda: p.iconst(1, 1))
    _ld(p, 0, VHI)
    p.iconst(12, 1)
    p.iop(0, 12, "-", 0)
    p.iop(1, 1, "AND", 0)

    def notch():                               # the rise past pw
        _ld(p, 9, VPPW)
        _ld(p, 6, T_PW)
        p.fop(9, 9, "-", 6)
        _ld(p, 5, T_F)
        p.fop(9, 9, "+", 5)
        K.recip(p, 9, 9)
        _ld(p, 4, PH)
        _ld(p, 6, T_PW)
        p.fop(8, 4, "-", 6)
        p.fop(8, 8, "*", 9)                    # t
        p.fconst(12, 1.0 + DEPTH)
        p.fop(3, 12, "-", 6)
        _ld(p, 5, T_NA)
        p.fop(3, 3, "*", 5)                    # the notch
        _sv(p, T_TS, 8)
        _saw_ts(p)
        _ld(p, 8, T_TS)
        _edge(p)
        p.iconst(0, 1)
        _sv(p, VHI, 0)

    def wrap():
        _ld(p, 4, PH)
        p.fconst(12, 1.0)

        def down():
            p.fconst(12, 1.0)
            p.fop(4, 4, "-", 12)
            _sv(p, PH, 4)
            _ld(p, 5, T_F)
            K.recip(p, 8, 5)
            _ld(p, 4, PH)
            p.fop(8, 4, "*", 8)                # t
            _ld(p, 5, T_NA)
            p.fconst(12, -(1.0 + DEPTH))
            p.fop(3, 12, "*", 5)               # - notch (exact: the sign)
            _sv(p, T_TS, 8)
            _saw_ts(p)
            p.fconst(12, 0.0)
            p.fop(9, 12, "-", 9)               # - ts
            _ld(p, 8, T_TS)
            _edge(p)
            p.iconst(0, 0)
            _sv(p, VHI, 0)
        p.if_(4, "GE", 12, down)
    p.ifz(1, "NE", notch, wrap)
    # the naive sample
    _ld(p, 4, PH)
    _ld(p, 6, T_PW)

    def lo():
        p.fpass(5, 4)                          # the notch saw
        _ld(p, 7, T_UP)
        p.fop(7, 4, "*", 7)                    # the triangle

    def hi():
        p.fconst(5, 1.0 + DEPTH)
        p.fop(7, 4, "-", 6)
        _ld(p, 8, T_DN)
        p.fop(7, 7, "*", 8)
        p.fconst(12, 1.0)
        p.fop(7, 12, "-", 7)
    p.if_(4, "LT", 6, lo, hi)
    _ld(p, 8, T_NA)
    p.fop(5, 5, "*", 8)
    _ld(p, 8, T_TRI)
    p.fop(7, 7, "*", 8)
    p.fop(5, 5, "+", 7)
    _ld(p, 4, T_NX)
    p.fop(4, 4, "+", 5)
    _sv(p, VNX, 4)
    _sv(p, VPPW, 6)
    _ld(p, 4, T_THIS)
    p.fop(4, 4, "+", 4)
    K.addk(p, 4, 4, -1.0)
    K.mulk(p, 4, 4, 1.0 / (1.0 + DEPTH))


# -- the parameters ------------------------------------------------------------------------------
def _interval(p: Prog, d: int, i: int, off: int) -> None:
    """Fd = INTERVALS[Ri + off] (Ri 0..3). Clobbers R12."""
    p.fconst(d, INTERVALS[off])
    for k in range(1, 4):
        p.iconst(12, k)
        p.if_(i, "GE", 12, lambda k=k: p.fconst(d, INTERVALS[k + off]), kind="i")


def _squash(p: Prog, x: int) -> None:
    """Fx = x^2 (3 - 2x). Clobbers R12, R13."""
    p.fop(13, x, "*", x)
    p.fop(12, x, "+", x)
    p.fconst(x, 3.0)
    p.fop(12, x, "-", 12)
    p.fop(x, 13, "*", 12)


def _detuning(p: Prog) -> None:
    """F4 = ComputeDetuning(harmonics) (semitones). Clobbers R0-R3, R5-R7, R12, R13."""
    K.par(p, 4, 0)
    K.mulk(p, 4, 4, 2.05)
    K.addk(p, 4, 4, -1.025)
    K.clamp(p, 4, -1.0, 1.0)
    p.fconst(5, 1.0)
    p.fconst(12, 0.0)
    p.if_(4, "LT", 12, lambda: p.fconst(5, -1.0))
    p.fop(4, 4, "*", 5)
    K.mulk(p, 4, 4, 3.9999)
    K.ifrac(p, 0, 6, 4)
    _interval(p, 2, 0, 0)
    _interval(p, 3, 0, 1)
    p.fop(3, 3, "-", 2)
    _squash(p, 6)
    _squash(p, 6)
    p.fop(3, 3, "*", 6)
    p.fop(2, 2, "+", 3)
    p.fop(4, 2, "*", 5)


def _osc_targets(p: Prog, f: int, pw: int, words) -> None:
    """an oscillator's Render() head: f = min(f, 0.25), pw 0.5 at 0.25 else clamped to
    [2f, 1 - 2f], then the interpolators (state, step) for f and pw. Clobbers R11, R12."""
    (sf, df), (spw, dpw) = words
    p.fconst(12, 0.25)
    p.fop(f, f, "MIN", 12)

    def top():
        p.fconst(pw, 0.5)

    def lim():
        p.fop(11, f, "+", f)
        p.fop(pw, pw, "MAX", 11)
        p.fconst(12, 1.0)
        p.fop(11, 12, "-", 11)
        p.fop(pw, pw, "MIN", 11)
    p.if_(f, "GE", 12, top, lim)
    K.interp_start(p, df, sf, f)
    K.interp_start(p, dpw, spw, pw)


def _params(p: Prog) -> None:
    _detuning(p)                                # F4 = the auxiliary's detuning
    _ld(p, 1, K.S_NOTE)
    p.fop(4, 1, "+", 4)
    K.note_freq(p, 8, 4)                        # the auxiliary's (the saw's) frequency
    _sv(p, T_F, 8)
    K.par(p, 6, 1)                              # timbre
    p.fconst(9, 0.0)
    p.fconst(12, 0.5)

    def ratio():
        p.fconst(12, 0.5)
        p.fop(9, 6, "-", 12)
        p.fop(9, 9, "*", 9)
        K.mulk(p, 9, 9, 4.0)
        K.mulk(p, 9, 9, 48.0)
    p.if_(6, "GE", 12, ratio)
    _ld(p, 4, K.S_NOTE)
    p.fop(4, 4, "+", 9)
    K.note_freq(p, 8, 4)                        # the square's (synced) frequency
    K.par(p, 6, 1)
    K.mulk(p, 9, 6, 1.3)
    K.addk(p, 9, 9, -0.15)
    K.clamp(p, 9, 0.005, 0.5)                   # the square's pw
    _osc_targets(p, 8, 9, ((SSF, DSF), (SPW, DPW)))
    # the master: the note's frequency, clamped to 0.25 too
    _ld(p, 4, K.S_NOTE)
    K.note_freq(p, 8, 4)
    p.fconst(12, 0.25)
    p.fop(8, 8, "MIN", 12)
    K.interp_start(p, DMF, SMF, 8)
    # the saw
    K.par(p, 7, 2)                              # morph
    p.fconst(12, 0.5)

    def lo():
        K.addk(p, 9, 7, 0.5)

    def hi():
        K.addk(p, 9, 7, -0.5)
        p.fop(9, 9, "+", 9)
        p.fconst(12, 1.0)
        p.fop(9, 12, "-", 9)
    p.if_(7, "LT", 12, lo, hi)
    K.mulk(p, 9, 9, 1.1)
    K.clamp(p, 9, 0.005, 1.0)
    _ld(p, 8, T_F)
    _osc_targets(p, 8, 9, ((VF, DVF), (VPW, DVPW)))
    K.par(p, 7, 2)
    K.mulk(p, 9, 7, 21.0)
    p.fconst(12, 10.0)
    p.fop(9, 12, "-", 9)
    K.clamp(p, 9, 0.0, 1.0)
    K.interp_start(p, DVWS, VWS, 9)
    # the gains: square min(8 timbre, 1), saw clamp(8 (1 - morph), 0.02, 1), normalised
    K.par(p, 6, 1)
    K.mulk(p, 6, 6, 8.0)
    p.fconst(12, 1.0)
    p.fop(6, 6, "MIN", 12)
    K.par(p, 7, 2)
    p.fconst(12, 1.0)
    p.fop(7, 12, "-", 7)
    K.mulk(p, 7, 7, 8.0)
    K.clamp(p, 7, 0.02, 1.0)
    p.fop(8, 6, "MAX", 7)
    _sv(p, T_TS, 7)
    K.recip(p, 9, 8)                            # norm
    K.par(p, 6, 1)
    K.mulk(p, 6, 6, 8.0)
    p.fconst(12, 1.0)
    p.fop(6, 6, "MIN", 12)
    K.mulk(p, 6, 6, 0.3)
    p.fop(6, 6, "*", 9)
    K.interp_start(p, DGSQ, GSQ, 6)
    _ld(p, 7, T_TS)
    K.mulk(p, 7, 7, 0.5)
    p.fop(7, 7, "*", 9)
    K.interp_start(p, DGSW, GSW, 7)


def half(p: Prog, L: C.Layout) -> None:
    _params(p)

    def one():
        _sq_sample(p)
        _saw_sample(p)
        K.interp_next(p, 5, GSW, DGSW)
        p.fop(4, 4, "*", 5)
        K.interp_next(p, 5, GSQ, DGSQ)
        _ld(p, 6, T_SQ)
        p.fop(5, 5, "*", 6)
        p.fop(4, 4, "+", 5)
        p.stpost(4, 4)
    p.loop(L.W["n4"], K.HALF, one)
