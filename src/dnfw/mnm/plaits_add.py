"""PLAITS' ADD: Mutable Instruments Plaits' ADDITIVE engine's OUT (plaits/dsp/engine/additive_engine.cc,
oscillator/harmonic_oscillator.h; MIT, Emilie Gillet).

24 integer harmonics: UpdateAmplitudes (TIMBRE the centroid, MORPH the slope, HARMONICS the
bumps; each amplitude one-pole smoothed, then the sum normalised), then two banks of 12 by
HarmonicOscillator's recurrence (current = 2 sin(phase) current - previous), each harmonic's
amplitude interpolated over the half and tamed towards Nyquist. Plaits' two oscillators share
their phase and frequency (the same Init, the same f0: they stay equal), so one phase drives both.
The organ harmonics (oscillator 2) only feed AUX: left out. Sines by plk.sinp (Plaits: lut_sine).

Memory (2026-11-10, poly16: DDR until then): harmonic i's interpolator value in the slot's host
word W[16 + i] and its smoothed amplitude in W[40 + i] (the Monomachine's host writes W[1..8]
only; L1 since the slots moved there), its step for the half in the render scratch's row (L1).
The same arithmetic in the same order: the output is bit for bit as before.
"""

from __future__ import annotations

from . import core as C
from . import plk as K
from ..perc.dsl import Prog

MODEL = "ADD"
NU_USED = 4
BIG_USED = 0
N_H = 24
from ..md import core as _MDK
V_W, A_W = 16, 40                                # slot words (I3): the values W[16..39], the amplitudes W[40..63]
assert A_W + N_H <= _MDK.NW

PHASE, FREQ, IFREQ, BASE = (K.U0 + k for k in range(NU_USED))


def init(p: Prog, L: C.Layout) -> None:
    """Init + Reset: the phase, the frequency, the amplitudes and their interpolators at 0."""
    p.iconst(0, 0)
    for k in (PHASE, FREQ):
        K.sv(p, k, 0)
    _ptr(p, 1, V_W)

    def clear():
        p.iconst(1, 0)
        p.stpost(1, 1)
    p.loop_r(8, 2 * N_H, clear)


def _ptr(p: Prog, i: int, w: int) -> None:
    """Ii = this slot's host word W[w] (I3 + 4 w). Clobbers R0, R12."""
    p.geti(0, 3)
    p.iconst(12, p.ioff(3, 4 * w))
    p.iop(0, 12, "+", 0)
    p.seti(i, 0)


def _steps(p: Prog, L, i: int) -> None:
    """Ii = the steps' row (the render scratch, L1). Clobbers R0."""
    p.iconst(0, L.XB)
    p.seti(i, 0)


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
        K.sinp_inline(p, 15, 15)
        K.addk(p, 15, 15, 1.0)
        p.fop(9, 9, "*", 15)
        p.fop(9, 9, "*", 9)
        p.fop(9, 9, "*", 9)
        p.ldi(10, 0, 1)
        p.fop(9, 9, "-", 10)
        K.mulk(p, 9, 9, 0.001)
        p.fop(10, 10, "+", 9)
        p.stpost(1, 10)
        p.fop(5, 5, "+", 10)
        K.addk(p, 6, 6, 1.0)
    p.loop_r(8, N_H, one)


def _params(p: Prog, L: C.Layout) -> None:
    _ptr(p, 1, A_W)
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
    _ptr(p, 1, A_W)
    _ptr(p, 5, V_W)
    _steps(p, L, 0)
    p.fconst(6, 1.0)                              # k

    def one():
        p.fop(7, 2, "*", 6)
        p.fconst(12, 0.5)
        p.fop(7, 7, "MIN", 12)
        p.fop(7, 7, "+", 7)
        p.fconst(12, 1.0)
        p.fop(7, 12, "-", 7)
        p.ldi(9, 0, 1)
        p.fop(9, 9, "*", 5)
        p.stpost(1, 9)
        p.fop(9, 9, "*", 7)
        p.ldpost(10, 5)
        p.fop(9, 9, "-", 10)
        K.mulk(p, 9, 9, 1.0 / K.HALF)
        p.stpost(0, 9)
        K.addk(p, 6, 6, 1.0)
    p.loop_r(8, N_H, one)


def _bank(p: Prog) -> None:
    """12 harmonics: F5 += amplitude Next() x current; current = F2 current - previous (F4
    current, F3 previous), I5 walking the values, I0 the steps. Clobbers R6-R9. 2026-11-10: the
    12 unrolled (current / previous / next rotating through F4, F3, F9), each harmonic's two loads
    riding on the one before's arithmetic: 5 instructions a harmonic, the same operations."""
    def body():
        p.ldpost(6, 2)
        p.ldpost(7, 0)
        cur, prev, nxt = 4, 3, 9
        for h in range(12):
            last = h == 11
            p.fop(6, 6, "+", 7)                               # value += step
            p.par(("op", 8, 6, "*", cur), ("stk", -1, 2, 6))  # its product; the value kept
            p.par(("op", 5, 5, "+", 8), *(() if last else (("ld", 6, 2),)))
            p.par(("op", nxt, 2, "*", cur), *(() if last else (("ld", 7, 0),)))
            p.fop(nxt, nxt, "-", prev)
            cur, prev, nxt = nxt, cur, prev
    p.call("pladd_bank", body)


def _sample(p: Prog, L) -> None:
    K.interp_next(p, 6, FREQ, IFREQ)
    K.ld(p, 11, PHASE)
    p.fop(11, 11, "+", 6)
    p.fconst(12, 1.0)
    p.if_(11, "GE", 12, lambda: p.fop(11, 11, "-", 12))
    K.sv(p, PHASE, 11)
    K.sinp_inline(p, 2, 11)
    p.fop(2, 2, "+", 2)                           # two_x
    _ptr(p, 2, V_W)                               # (I2: a compute's move goes through I0..I3)
    _steps(p, L, 0)
    p.fconst(3, 1.0)
    K.mulk(p, 4, 2, 0.5)
    p.fconst(5, 0.0)
    _bank(p)                                      # harmonics 1..12
    p.fpass(10, 5)
    K.mulk(p, 15, 11, 12.0)
    K.addk(p, 15, 15, 0.25)
    K.sinp_inline(p, 3, 15)
    K.mulk(p, 15, 11, 13.0)
    K.sinp_inline(p, 4, 15)
    p.fconst(5, 0.0)
    _bank(p)                                      # 13..24
    p.fop(10, 10, "+", 5)
    p.stpost(4, 10)


def half(p: Prog, L: C.Layout) -> None:
    """AdditiveEngine::Render(16 samples) at I4 (OUT)."""
    _params(p, L)
    p.loop(L.W["n4"], K.HALF, lambda: _sample(p, L))
