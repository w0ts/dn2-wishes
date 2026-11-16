"""PLAITS' ADD: Mutable Instruments Plaits' ADDITIVE engine's OUT (plaits/dsp/engine/additive_engine.cc,
oscillator/harmonic_oscillator.h; MIT, Emilie Gillet).

24 integer harmonics: UpdateAmplitudes (TIMBRE the centroid, MORPH the slope, HARMONICS the
bumps; each amplitude one-pole smoothed, then the sum normalised), then two banks of 12 by
HarmonicOscillator's recurrence (current = 2 sin(phase) current - previous), each harmonic's
amplitude interpolated over the half and tamed towards Nyquist. Plaits' two oscillators share
their phase and frequency (the same Init, the same f0: they stay equal), so one phase drives both.
The organ harmonics (oscillator 2) only feed AUX: left out. Sines by plk.sinp (Plaits: lut_sine).

DDR (big_at): harmonic i's interpolator at 2i (value, step), its smoothed amplitude at 48 + 2i.
"""

from __future__ import annotations

from . import core as C
from . import plk as K
from ..perc.dsl import Prog

MODEL = "ADD"
NU_USED = 4
BIG_USED = 96
N_H = 24
A_OFF = 48                                       # the amplitudes' offset from the interpolators

PHASE, FREQ, IFREQ, BASE = (K.U0 + k for k in range(NU_USED))


def init(p: Prog, L: C.Layout) -> None:
    """Init + Reset: the phase, the frequency, the amplitudes and their interpolators at 0."""
    p.iconst(0, 0)
    for k in (PHASE, FREQ):
        K.sv(p, k, 0)
    K.big_at(p, L, 1)
    p.seti(1, 1)

    def clear():
        p.iconst(1, 0)
        p.stpost(1, 1)
    p.loop_r(8, BIG_USED, clear)


def _skip2(p: Prog) -> None:
    """I1 += 2 words"""
    p.ldpost(15, 1)
    p.ldpost(15, 1)


def _update(p: Prog) -> None:
    """UpdateAmplitudes(centroid F2 -> center, slope F3, bumps F4) over the 24 harmonics, I1 at
    the first: F5 = the sum. Clobbers R0, R1, R6-R15, I12."""
    p.fconst(5, 0.001)
    p.fconst(6, 0.0)                              # i

    def one():
        p.fop(7, 6, "-", 2)
        K.fabs(p, 7, 7)
        p.fop(7, 7, "*", 3)                       # order
        p.fconst(12, 1.0)
        p.fop(9, 12, "-", 7)
        K.fabs(p, 10, 9)
        p.fop(9, 9, "+", 10)
        p.fop(9, 9, "*", 9)                       # gain
        p.fop(15, 7, "*", 4)
        K.addk(p, 15, 15, 0.25)
        K.sinp(p, 15, 15)
        K.addk(p, 15, 15, 1.0)
        p.fop(9, 9, "*", 15)
        p.fop(9, 9, "*", 9)
        p.fop(9, 9, "*", 9)
        p.ldi(10, A_OFF, 1)
        p.fop(9, 9, "-", 10)
        K.mulk(p, 9, 9, 0.001)
        p.fop(10, 10, "+", 9)
        p.sti(A_OFF, 1, 10)
        p.fop(5, 5, "+", 10)
        K.addk(p, 6, 6, 1.0)
        _skip2(p)
    p.loop_r(8, N_H, one)


def _params(p: Prog, L: C.Layout) -> None:
    K.big_at(p, L, 1)
    K.sv(p, BASE, 1)
    p.seti(1, 1)
    K.par(p, 4, 0)                                # raw_bumps
    K.par(p, 2, 1)                                # centroid
    K.par(p, 3, 2)                                # morph
    K.mulk(p, 5, 4, 0.6)
    p.fconst(12, 1.0)
    p.fop(5, 12, "-", 5)
    p.fop(5, 5, "*", 3)                           # raw_slope
    K.mulk(p, 3, 5, 1.99)
    p.fop(3, 3, "*", 5)
    p.fop(3, 3, "*", 5)
    K.addk(p, 3, 3, 0.01)                         # slope
    K.mulk(p, 5, 4, 16.0)
    p.fop(4, 5, "*", 4)                           # bumps
    # margin = (1 / slope - 1) / (1 + bumps); center = centroid (23 + margin) - margin / 2
    K.recip(p, 6, 3)
    K.addk(p, 6, 6, -1.0)
    K.addk(p, 7, 4, 1.0)
    K.div(p, 5, 6, 7)
    K.addk(p, 6, 5, float(N_H - 1))
    p.fop(6, 2, "*", 6)
    K.mulk(p, 5, 5, 0.5)
    p.fop(2, 6, "-", 5)
    _update(p)
    K.recip(p, 5, 5)                              # 1 / sum
    # the oscillators: f = min(f0, 0.5); harmonic k's amplitude target A_k (1 - 2 min(k f, 0.5))
    K.ld(p, 6, K.S_NOTE)
    K.note_freq(p, 7, 6)
    p.fconst(12, 0.5)
    p.fop(2, 7, "MIN", 12)
    K.interp_start(p, IFREQ, FREQ, 2)
    K.ld(p, 1, BASE)
    p.seti(1, 1)
    p.fconst(6, 1.0)                              # k

    def one():
        p.fop(7, 2, "*", 6)
        p.fconst(12, 0.5)
        p.fop(7, 7, "MIN", 12)
        p.fop(7, 7, "+", 7)
        p.fconst(12, 1.0)
        p.fop(7, 12, "-", 7)
        p.ldi(9, A_OFF, 1)
        p.fop(9, 9, "*", 5)
        p.sti(A_OFF, 1, 9)
        p.fop(9, 9, "*", 7)
        p.ldi(10, 0, 1)
        p.fop(9, 9, "-", 10)
        K.mulk(p, 9, 9, 1.0 / K.HALF)
        p.sti(1, 1, 9)
        K.addk(p, 6, 6, 1.0)
        _skip2(p)
    p.loop_r(8, N_H, one)


def _bank(p: Prog) -> None:
    """12 harmonics: F5 += amplitude Next() x current; current = F2 current - previous (F4
    current, F3 previous), I1 walking the interpolators. Clobbers R6-R9, R12."""
    def body():
        def one():
            p.ldpost(6, 1)
            p.ldpost(7, 1)
            p.fop(6, 6, "+", 7)
            p.sti(-2, 1, 6)
            p.fop(9, 6, "*", 4)
            p.fop(5, 5, "+", 9)
            p.fop(9, 2, "*", 4)
            p.fop(9, 9, "-", 3)
            p.fpass(3, 4)
            p.fpass(4, 9)
        p.loop_r(8, 12, one)
    p.call("pladd_bank", body)


def _sample(p: Prog) -> None:
    K.interp_next(p, 6, FREQ, IFREQ)
    K.ld(p, 11, PHASE)
    p.fop(11, 11, "+", 6)
    p.fconst(12, 1.0)
    p.if_(11, "GE", 12, lambda: p.fop(11, 11, "-", 12))
    K.sv(p, PHASE, 11)
    K.sinp(p, 2, 11)
    p.fop(2, 2, "+", 2)                           # two_x
    K.ld(p, 1, BASE)
    p.seti(1, 1)
    p.fconst(3, 1.0)
    K.mulk(p, 4, 2, 0.5)
    p.fconst(5, 0.0)
    _bank(p)                                      # harmonics 1..12
    p.fpass(10, 5)
    K.mulk(p, 15, 11, 12.0)
    K.addk(p, 15, 15, 0.25)
    K.sinp(p, 3, 15)
    K.mulk(p, 15, 11, 13.0)
    K.sinp(p, 4, 15)
    p.fconst(5, 0.0)
    _bank(p)                                      # 13..24
    p.fop(10, 10, "+", 5)
    p.stpost(4, 10)


def half(p: Prog, L: C.Layout) -> None:
    """AdditiveEngine::Render(16 samples) at I4 (OUT)."""
    _params(p, L)
    p.loop(L.W["n4"], K.HALF, lambda: _sample(p))
