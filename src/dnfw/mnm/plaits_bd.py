"""Plaits' BASS DRUM (engine/bass_drum_engine.cc): OUT, the 808 model (drums/analog_bass_drum.h)
through the overdrive (fx/overdrive.h). Triggered (sustain false: the DN2 triggers every note),
accent 0.8. HARM: attack and self FM, the drive; TIMB: the tone; MORP: the decay.

The pulse times stay Plaits' in samples (48 kHz's: 9 % longer at 44.1 kHz); f0 is the note's at
44.1 kHz. AUX (the synthetic bass drum) is not rendered, nor its random draws (OUT draws none).
"""

from __future__ import annotations

from . import plaits_drumkit as D
from . import plk as K
from ..perc.dsl import Prog, f32

MODEL = "BD"
(FM_REM, FM_LP, RETRIG, LP_OUT, TONE_LP, PRE, POST, SVF, F0, SCALE, Q, TONE_F, LEAK, AFM, SFM,
 PRE_I, POST_I) = (4, 5, 6, 7, 8, 9, 10, 11, 16, 17, 18, 19, 20, 21, 22, 23, 24)
NU_USED = 25
BIG_USED = 0

PULSE_DECAY = f32(1.0 - f32(1.0 / D.ksr(0.2e-3)))
FILTER_K = f32(1.0 / D.ksr(0.1e-3))
RETRIG_DECAY = f32(1.0 - f32(1.0 / D.ksr(0.05)))
N_PULSE, N_FM = int(D.ksr(1.0e-3)), int(D.ksr(6.0e-3))
HEIGHT = f32(3.0 + f32(7.0 * f32(K.ACCENT)))


def init(p: Prog, L) -> None:
    """Init: every word 0 (the pulses, filters, the overdrive's gains)."""
    D.clear(p, L, NU_USED)


def _params(p: Prog) -> None:
    u = D.u
    K.ld(p, 1, K.S_NOTE)
    D.note_freq(p, 4, 1)                       # F4 f0
    K.sv(p, u(F0), 4)
    K.par(p, 5, 0)                             # harmonics
    K.par(p, 6, 1)                             # tone
    K.par(p, 7, 2)                             # decay
    K.mulk(p, 8, 5, 4.0)
    p.fconst(12, 1.0)
    p.fop(9, 8, "MIN", 12)
    K.sv(p, u(AFM), 9)                         # min(4 h, 1)
    K.addk(p, 8, 8, -1.0)
    K.clamp(p, 8, 0.0, 1.0)
    K.sv(p, u(SFM), 8)                         # max(min(4 h - 1, 1), 0)
    p.fop(8, 5, "+", 5)
    K.addk(p, 8, 8, -1.0)
    p.fconst(12, 0.0)
    p.fop(8, 8, "MAX", 12)
    K.mulk(p, 9, 4, 16.0)
    p.fconst(12, 1.0)
    p.fop(9, 12, "-", 9)
    p.fconst(12, 0.0)
    p.fop(9, 9, "MAX", 12)
    p.fop(8, 8, "*", 9)                        # drive
    # Overdrive::Process(0.5 + 0.5 drive)
    K.mulk(p, 8, 8, 0.5)
    K.addk(p, 8, 8, 0.5)
    p.fop(9, 8, "*", 8)                        # drive_2
    K.mulk(p, 10, 8, 0.5)                      # pre_gain_a
    p.fop(3, 9, "*", 9)
    p.fop(3, 3, "*", 8)
    K.mulk(p, 3, 3, 24.0)                      # pre_gain_b
    p.fop(3, 3, "-", 10)
    p.fop(3, 3, "*", 9)
    p.fop(3, 10, "+", 3)                       # pre_gain
    K.interp_start(p, u(PRE_I), u(PRE), 3)
    p.fconst(12, 2.0)
    p.fop(9, 12, "-", 8)
    p.fop(9, 8, "*", 9)                        # drive_squashed
    K.addk(p, 10, 3, -0.33)
    p.fop(10, 9, "*", 10)
    K.addk(p, 15, 10, 0.33)
    D.soft(p)
    K.recip(p, 15, 15)
    K.interp_start(p, u(POST_I), u(POST), 15)
    # the bass drum's constants
    K.recip(p, 8, 4)
    K.mulk(p, 8, 8, 0.001)
    K.sv(p, u(SCALE), 8)                       # 0.001 / f0
    K.mulk(p, 8, 7, 80.0)
    D.semis(p, 9, 8)
    K.mulk(p, 9, 9, 1500.0)
    K.sv(p, u(Q), 9)
    K.mulk(p, 8, 6, 108.0)
    D.semis(p, 9, 8)
    K.mulk(p, 10, 4, 4.0)
    p.fop(9, 10, "*", 9)
    p.fconst(12, 1.0)
    p.fop(9, 9, "MIN", 12)
    K.sv(p, u(TONE_F), 9)
    K.addk(p, 8, 6, 0.25)
    K.mulk(p, 8, 8, 0.08)
    K.sv(p, u(LEAK), 8)


def _trig(p: Prog) -> None:
    u = D.u
    p.iconst(0, N_PULSE)
    K.sv(p, u(D.P_REM), 0)
    p.iconst(0, N_FM)
    K.sv(p, u(FM_REM), 0)
    p.fconst(0, HEIGHT)
    K.sv(p, u(D.P_H), 0)
    p.fconst(0, 0.0)
    K.sv(p, u(LP_OUT), 0)


def _sample(p: Prog, L) -> None:
    u = D.u
    p.fconst(8, PULSE_DECAY)
    D.pulse(p)                                 # F9
    p.fconst(3, FILTER_K)
    D.one_pole(p, 5, D.P_LP, 9, 3)
    p.fop(6, 9, "-", 5)
    K.mulk(p, 7, 9, 0.044)
    p.fop(15, 6, "+", 7)
    D.diode(p)
    p.fpass(4, 15)                             # F4 pulse
    # the FM pulse, the retrigger pulse
    K.ld(p, 5, u(FM_REM))

    def on():
        p.iconst(12, 1)
        p.iop(5, 5, "-", 12)
        K.sv(p, u(FM_REM), 5)
        p.fconst(6, 1.0)
        p.fconst(7, 0.0)
        p.ifz(5, "EQ", lambda: p.fconst(7, -0.8))

    def off():
        p.fconst(6, 0.0)
        K.ld(p, 7, u(RETRIG))
        K.mulk(p, 7, 7, RETRIG_DECAY)
    p.ifz(5, "NE", on, off)
    K.sv(p, u(RETRIG), 7)                      # F7 retrig
    p.fconst(3, FILTER_K)
    D.one_pole(p, 5, FM_LP, 6, 3)              # F5 fm_pulse_lp
    K.ld(p, 15, u(LP_OUT))
    K.mulk(p, 15, 15, 10.0)
    K.addk(p, 15, 15, -1.0)
    D.diode(p)
    K.addk(p, 15, 15, 0.7)                     # punch
    K.mulk(p, 5, 5, 1.7)
    K.ld(p, 6, u(AFM))
    p.fop(5, 5, "*", 6)
    K.mulk(p, 15, 15, 0.08)
    K.ld(p, 6, u(SFM))
    p.fop(15, 15, "*", 6)
    K.addk(p, 5, 5, 1.0)
    p.fop(5, 5, "+", 15)
    K.ld(p, 6, u(F0))
    p.fop(5, 6, "*", 5)
    K.clamp(p, 5, 0.0, 0.4)                    # F5 f
    D.tan_dirty(p, 8, 5)
    K.ld(p, 9, u(Q))
    p.fop(9, 9, "*", 5)
    K.addk(p, 9, 9, 1.0)
    D.wptr(p, L, SVF)
    D.svfset(p)
    K.mulk(p, 7, 7, 0.2)
    p.fop(8, 4, "-", 7)
    K.ld(p, 7, u(SCALE))
    p.fop(8, 8, "*", 7)
    D.svf(p)                                   # F10 bp, F11 lp
    K.sv(p, u(LP_OUT), 11)
    K.ld(p, 6, u(LEAK))
    p.fop(6, 4, "*", 6)
    p.fop(6, 6, "+", 10)
    K.ld(p, 3, u(TONE_F))
    D.one_pole(p, 7, TONE_LP, 6, 3)            # F7 tone_lp
    K.interp_next(p, 15, u(PRE), u(PRE_I))
    p.fop(15, 15, "*", 7)
    D.soft(p)
    K.interp_next(p, 14, u(POST), u(POST_I))
    p.fop(15, 15, "*", 14)
    p.stpost(4, 15)


def half(p: Prog, L) -> None:
    D.on_trig(p, lambda: _trig(p))
    _params(p)
    p.loop(L.W["n4"], K.HALF, lambda: _sample(p, L))
