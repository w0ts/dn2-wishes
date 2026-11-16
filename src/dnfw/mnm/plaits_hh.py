"""Plaits' HI-HAT (engine/hi_hat_engine.cc): OUT, hi_hat_1_ = HiHat<SquareNoise, SwingVCA, resonance,
one-stage envelope> (drums/hi_hat.h): six square oscillators (808 metallic noise) through a
resonant band-pass, mixed with clocked noise, the swing VCA, a high-pass. Triggered (sustain
false), accent 0.8. HARM: noisiness; TIMB: the tone (the filters' cutoff); MORP: the decay.

The cutoff is 150 Hz x 2^(tone x 6) at 44.1 kHz (Plaits' 150 / kSampleRate is a frequency); the
envelope's decay a sample stays Plaits'. AUX (hi_hat_2_) is not rendered, but its noise clock is
OUT's (the same f0 and noisiness, both from 0), so it draws as many randoms as OUT, after OUT's, a
block: the voice's generator skips them (COUNT), and OUT's noise is the C++'s draw for draw.
"""

from __future__ import annotations

from . import plaits_drumkit as D
from . import plk as K
from ..perc.dsl import Prog, f32

MODEL = "HH"
ENV, NCLK, NSAMP, BPF, HPF, EDEC, NOISY, NOISE_F, COUNT = 12, 13, 14, 15, 20, 25, 26, 27, 28
NU_USED = 29                                   # words 0..11: the oscillators' (increment, phase)
BIG_USED = 0

RATIOS = (1.0, 1.304, 1.466, 1.787, 1.932, 2.536)
GAIN_ACCENT = f32(0.3 + f32(f32(0.7) * f32(K.ACCENT)))


def init(p: Prog, L) -> None:
    D.clear(p, L, NU_USED)


def _params(p: Prog, L) -> None:
    u = D.u
    K.ld(p, 1, K.S_NOTE)
    D.note_freq(p, 4, 1)                       # F4 f0
    K.par(p, 5, 0)                             # noisiness
    K.par(p, 6, 1)                             # tone
    K.par(p, 7, 2)                             # decay
    K.mulk(p, 8, 7, 84.0)
    p.fconst(12, 0.0)
    p.fop(8, 12, "-", 8)
    D.semis(p, 9, 8)
    K.mulk(p, 9, 9, 0.003)
    p.fconst(12, 1.0)
    p.fop(9, 12, "-", 9)
    K.sv(p, u(EDEC), 9)                        # envelope_decay

    def trig():
        p.fconst(12, 1.0)
        p.fop(8, 12, "-", 7)
        K.mulk(p, 8, 8, 0.5)
        K.addk(p, 8, 8, 1.5)
        K.mulk(p, 8, 8, GAIN_ACCENT)
        K.sv(p, u(ENV), 8)
    D.on_trig(p, trig)
    # SquareNoise(2 f0): the increments
    p.fop(8, 4, "+", 4)
    for i, r in enumerate(RATIOS):
        p.fconst(9, r)
        p.fop(9, 8, "*", 9)
        p.fconst(12, 0.499)
        p.fop(9, 9, "MIN", 12)
        K.mulk(p, 9, 9, 4294967296.0)
        p.trunc(10, 9)
        K.sv(p, u(2 * i), 10)
    # the band-pass and the high-pass at the cutoff
    K.mulk(p, 8, 6, 72.0)
    D.semis(p, 9, 8)
    K.mulk(p, 9, 9, f32(150.0 / K.SR))
    K.clamp(p, 9, 0.0, f32(16000.0 / K.SR))
    D.tan_poly(p, 8, 9, 10, D.TAN_ACC)         # F8 g
    K.mulk(p, 9, 6, 3.0)
    K.addk(p, 9, 9, 3.0)
    D.wptr(p, L, BPF)
    D.svfset(p)
    p.fconst(9, 0.5)
    D.wptr(p, L, HPF)
    D.svfset(p)
    # the clocked noise
    p.fop(5, 5, "*", 5)
    K.sv(p, u(NOISY), 5)
    p.fconst(12, 1.0)
    p.fop(9, 12, "-", 5)
    K.mulk(p, 9, 9, 16.0)
    K.addk(p, 9, 9, 16.0)
    p.fop(9, 4, "*", 9)
    K.clamp(p, 9, 0.0, 0.5)
    K.sv(p, u(NOISE_F), 9)
    p.iconst(0, 0)
    K.sv(p, u(COUNT), 0)


def _osc(p: Prog) -> None:
    """One oscillator at I1 (increment, phase): phase += increment, R10 += its top bit."""
    p.ldpost(9, 1)
    p.ldi(8, 0, 1)
    p.iop(8, 8, "+", 9)
    p.stpost(1, 8)
    p.lsh(9, 8, -31)
    p.iop(10, 10, "+", 9)


def _sample(p: Prog, L) -> None:
    u = D.u
    D.wptr(p, L, 0)
    p.iconst(10, 0)
    p.loop_r(3, len(RATIOS), lambda: _osc(p))
    p.iconst(12, 0)
    p.float_(8, 10, 12)
    K.mulk(p, 8, 8, 0.33)
    K.addk(p, 8, 8, -1.0)
    D.wptr(p, L, BPF)
    D.svf(p)
    p.fpass(4, 10)                             # F4 the band-passed metallic noise
    K.ld(p, 5, u(NCLK))
    K.ld(p, 6, u(NOISE_F))
    p.fop(5, 5, "+", 6)
    p.fconst(12, 1.0)

    def draw():
        p.fop(5, 5, "-", 12)
        K.rnd01(p, 6)
        K.addk(p, 6, 6, -0.5)
        K.sv(p, u(NSAMP), 6)
        K.ld(p, 7, u(COUNT))
        p.iconst(12, 1)
        p.iop(7, 12, "+", 7)
        K.sv(p, u(COUNT), 7)
    p.if_(5, "GE", 12, draw)
    K.sv(p, u(NCLK), 5)
    K.ld(p, 6, u(NSAMP))
    p.fop(6, 6, "-", 4)
    K.ld(p, 7, u(NOISY))
    p.fop(6, 7, "*", 6)
    p.fop(4, 4, "+", 6)
    # the envelope, SwingVCA
    K.ld(p, 5, u(ENV))
    K.ld(p, 6, u(EDEC))
    p.fop(5, 5, "*", 6)
    K.sv(p, u(ENV), 5)
    p.fconst(12, 0.0)
    p.if_(4, "GT", 12, lambda: K.mulk(p, 4, 4, 4.0), lambda: K.mulk(p, 4, 4, 0.1))
    K.fabs(p, 6, 4)
    K.addk(p, 6, 6, 1.0)
    K.recip(p, 6, 6)
    p.fop(4, 4, "*", 6)
    K.addk(p, 4, 4, 0.1)
    p.fop(8, 4, "*", 5)
    D.wptr(p, L, HPF)
    D.svf(p)
    p.stpost(4, 9)


def half(p: Prog, L) -> None:
    _params(p, L)
    p.loop(L.W["n4"], K.HALF, lambda: _sample(p, L))
    K.ld(p, 5, D.u(COUNT))                     # AUX's draws
    p.ifz(5, "GT", lambda: p.loop_r(5, None, lambda: K.rng(p, 13)))
