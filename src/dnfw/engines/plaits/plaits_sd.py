"""Plaits' SNARE DRUM (engine/snare_drum_engine.cc): OUT, the 808 model (drums/analog_snare_drum.h):
five shell modes (band-pass Svfs rung by the trigger pulse) through SoftClip, plus band-passed noise.
Triggered (sustain false), accent 0.8. HARM: snappy; TIMB: the tone (the modes' gains); MORP: the
decay.

The pulse times and the noise envelope's decay stay Plaits' in samples (9 % longer at 44.1 kHz).
AUX (the synthetic snare) is not rendered, but it draws 16 randoms a block from Plaits' one
stmlib::Random after OUT's 16: the voice's generator skips them (rng_skip), so OUT's noise is the
C++'s draw for draw.
"""

from __future__ import annotations

from . import plaits_drumkit as D
from . import plk as K
from ...perc.dsl import Prog, f32

MODEL = "SD"
NENV, NED, LEAK, SNAPPY, MODES, NOISE = 4, 5, 6, 7, 10, 40     # MODES: 5 x [g r h s1 s2 gain]
NU_USED = 45
BIG_USED = 0

PULSE_DECAY = f32(1.0 - f32(1.0 / D.ksr(0.1e-3)))
N_PULSE = int(D.ksr(1.0e-3))
HEIGHT = f32(3.0 + f32(7.0 * f32(K.ACCENT)))
RATIOS = (1.00, 2.00, 3.18, 4.16, 5.62)


def init(p: Prog, L) -> None:
    D.clear(p, L, NU_USED)


def _gain(i: int) -> int:
    return D.u(MODES + 6 * i + 5)


def _fq(p: Prog) -> None:
    """I1 = the filter at R6, R6 on to the next; F8 = tan_fast(f), F9 = 1 + f qk with
    f = min(f0 F4 x ratio F8, 0.499), qk in F9. Clobbers R10-R12, I12."""
    def body():
        p.seti(1, 6)
        p.iconst(12, 24)
        p.iop(6, 12, "+", 6)
        p.fop(10, 4, "*", 8)
        p.fconst(12, 0.499)
        p.fop(10, 10, "MIN", 12)
        p.fop(9, 10, "*", 9)
        K.addk(p, 9, 9, 1.0)
        D.tan_poly(p, 8, 10, 11, D.TAN_FAST)
    p.call("plsd_fq", body)


def _params(p: Prog, L) -> None:
    u = D.u
    K.ld(p, 1, K.S_NOTE)
    D.note_freq(p, 4, 1)                       # F4 f0
    K.par(p, 7, 0)                             # snappy
    K.par(p, 5, 1)                             # tone
    K.par(p, 6, 2)                             # decay
    K.addk(p, 8, 6, -1.0)
    p.fop(8, 6, "*", 8)
    K.addk(p, 8, 8, 1.0)
    p.fop(8, 6, "*", 8)                        # decay_xt
    K.mulk(p, 8, 8, 84.0)
    D.semis(p, 2, 8)
    K.mulk(p, 2, 2, 2000.0)                    # F2 q
    K.mulk(p, 3, 2, 0.25)                      # F3 q / 4
    K.mulk(p, 8, 7, 10.0)
    K.addk(p, 8, 8, 50.0)
    p.fop(8, 6, "*", 8)
    p.fconst(12, 0.0)
    p.fop(8, 12, "-", 8)
    D.semis(p, 9, 8)
    K.mulk(p, 9, 9, 0.0017)
    p.fconst(12, 1.0)
    p.fop(9, 12, "-", 9)
    K.sv(p, u(NED), 9)                         # noise_envelope_decay
    p.fconst(12, 2.0)
    p.fop(8, 12, "-", 7)
    p.fop(8, 7, "*", 8)
    K.mulk(p, 8, 8, 0.1)
    K.sv(p, u(LEAK), 8)                        # exciter_leak
    K.mulk(p, 7, 7, 1.1)
    K.addk(p, 7, 7, -0.05)
    K.clamp(p, 7, 0.0, 1.0)
    K.sv(p, u(SNAPPY), 7)
    # the six filters: the modes at f0 x ratio, Q q (mode 0) or q / 4, the noise's at 16 f0
    D.wbase(p, L, 6, MODES)
    for i, r in enumerate(RATIOS + (16.0,)):
        p.fconst(8, r)
        if i == 0:
            p.fpass(9, 2)
        elif i < 5:
            p.fpass(9, 3)
        else:
            p.fconst(9, 1.5)
        _fq(p)
        D.svfset(p)
    # the modes' gains
    p.fconst(12, f32(0.666667))

    def s808():
        K.mulk(p, 5, 5, 1.5)
        p.fconst(12, 1.0)
        p.fop(8, 12, "-", 5)
        p.fop(8, 8, "*", 8)
        K.mulk(p, 8, 8, 4.5)
        K.addk(p, 8, 8, 1.5)
        K.sv(p, _gain(0), 8)
        p.fop(8, 5, "+", 5)
        K.addk(p, 8, 8, 0.15)
        K.sv(p, _gain(1), 8)
        p.fconst(8, 0.0)
        for i in (2, 3, 4):
            K.sv(p, _gain(i), 8)

    def extra():
        K.addk(p, 5, 5, -0.666667)
        K.mulk(p, 5, 5, 3.0)
        K.mulk(p, 8, 5, 0.5)
        p.fconst(12, 1.5)
        p.fop(8, 12, "-", 8)
        K.sv(p, _gain(0), 8)
        K.mulk(p, 8, 5, 0.7)
        p.fconst(12, 2.15)
        p.fop(8, 12, "-", 8)
        K.sv(p, _gain(1), 8)
        for i in (2, 3, 4):
            K.sv(p, _gain(i), 5)
            if i < 4:
                p.fop(5, 5, "*", 5)
    p.if_(5, "LT", 12, s808, extra)


def _trig(p: Prog) -> None:
    u = D.u
    p.iconst(0, N_PULSE)
    K.sv(p, u(D.P_REM), 0)
    p.fconst(0, HEIGHT)
    K.sv(p, u(D.P_H), 0)
    p.fconst(0, 2.0)
    K.sv(p, u(NENV), 0)


def _mode(p: Prog) -> None:
    """One mode: shell F7 += gain (bp(exc F4) + exc leak F3); the filter at R6, R6 on."""
    p.seti(1, 6)
    p.fpass(8, 4)
    D.svf(p)
    p.fop(11, 4, "*", 3)
    p.fop(10, 10, "+", 11)
    p.ldi(11, 5, 1)
    p.fop(10, 11, "*", 10)
    p.fop(7, 7, "+", 10)
    p.fpass(4, 5)
    p.iconst(12, 24)
    p.iop(6, 12, "+", 6)


def _sample(p: Prog, L) -> None:
    u = D.u
    p.fconst(8, PULSE_DECAY)
    D.pulse(p)                                 # F9 pulse
    p.fconst(3, 0.75)
    D.one_pole(p, 5, D.P_LP, 9, 3)
    p.fop(4, 9, "-", 5)
    K.mulk(p, 6, 9, 0.006)
    p.fop(4, 4, "+", 6)                        # F4 mode 0's excitation
    K.mulk(p, 5, 9, 0.026)                     # F5 the others'
    K.ld(p, 3, u(LEAK))
    p.fconst(7, 0.0)
    D.wbase(p, L, 6, MODES)
    p.loop_r(2, 5, lambda: _mode(p))
    p.fpass(15, 7)
    D.soft(p)
    p.fpass(7, 15)                             # F7 shell
    K.rnd01(p, 8)
    p.fop(8, 8, "+", 8)
    K.addk(p, 8, 8, -1.0)
    p.fconst(12, 0.0)
    p.fop(8, 8, "MAX", 12)
    K.ld(p, 9, u(NENV))
    K.ld(p, 10, u(NED))
    p.fop(9, 9, "*", 10)
    K.sv(p, u(NENV), 9)
    K.ld(p, 10, u(SNAPPY))
    p.fop(9, 9, "*", 10)
    p.fop(9, 9, "+", 9)
    p.fop(8, 8, "*", 9)
    p.seti(1, 6)                               # the noise filter
    D.svf(p)
    K.ld(p, 11, u(SNAPPY))
    p.fconst(12, 1.0)
    p.fop(11, 12, "-", 11)
    p.fop(11, 7, "*", 11)
    p.fop(15, 10, "+", 11)
    p.stpost(4, 15)


def half(p: Prog, L) -> None:
    D.on_trig(p, lambda: _trig(p))
    _params(p, L)
    p.loop(L.W["n4"], K.HALF, lambda: _sample(p, L))
    D.rng_skip(p, K.HALF)                      # AUX's draws
