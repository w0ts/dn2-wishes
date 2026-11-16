"""PLAITS' FM: Mutable Instruments Plaits' 2-operator FM engine's OUT (plaits/dsp/engine/fm_engine.cc,
oscillator/sine_oscillator.h SinePM, downsampler/4x_downsampler.h; MIT, Emilie Gillet).

At 4x oversampling: the modulator at the note + HARMONICS' quantized ratio (lut_fm_frequency_
quantizer), its phase feedback (MORPH below 0.5) or self phase-modulation (above), the carrier
phase-modulated by it (TIMBRE^2 x 2, tamed for high modulator notes), through Plaits' 4x FIR
downsampler. uint32 phases as Plaits'; SinePM is sin(2 pi (phase / 2^32 + pm)) by plk.sinp (Plaits:
512-point lut_sine, pm in 2^-26 steps). The sub-oscillator feeds only AUX: left out.

The table (TABLE, 137 words, Layout.PL["fm"]): the quantizer / 64 (130 points), then the FIR as
f0 f1 f2 f3 f2 f1 f0 (fir[j] at j, fir[3 - j] at j + 3, read through I1 as the 4 sub-samples go).
"""

from __future__ import annotations

import math

from . import core as C
from . import plk as K
from ..perc.dsl import Prog

MODEL = "FM"
NU_USED = 12
BIG_USED = 0

# slot words: the phases (uint32), the interpolators' values and steps, the one-pole, the FIR head
(CPH, MPH, PCF, PMF, PAM, PFB, PREV, CFIR, ICF, IMF, IAM, IFB) = (K.U0 + k for k in range(NU_USED))

FMQ_SCALE = 64.0
FMQ_N = 130
TABLE_WORDS = FMQ_N + 7
U32 = 4294967296.0


def table() -> list[float]:
    """The table's values (Q23 when shipped, dnfw.mnm.tables): lookup_tables.py's
    fm_frequency_quantizer / 64, then the 4x downsampler's FIR, f0 f1 f2 f3 f2 f1 f0."""
    r = [0.5, 0.5 * 2 ** (16 / 1200.0), math.sqrt(2) / 2, math.pi / 4, 1.0, 2 ** (16 / 1200.0),
         math.sqrt(2), math.pi / 2, 7.0 / 4, 2, 2 * 2 ** (16 / 1200.0), 9.0 / 4, 11.0 / 4,
         2 * math.sqrt(2), 3, math.pi, math.sqrt(3) * 2, 4, math.sqrt(2) * 3, math.pi * 3 / 2, 5,
         math.sqrt(2) * 4, 8]
    scale = []
    for x in r:
        scale += [12 * math.log2(x)] * 3
    while len(scale) < 128:
        d = [b - a for a, b in zip(scale, scale[1:])]
        gap = d.index(max(d))
        scale = scale[:gap + 1] + [(scale[gap] + scale[gap + 1]) / 2] + scale[gap + 1:]
    scale += [scale[-1], scale[-1]]
    fir = (0.02442415, 0.09297315, 0.16712938, 0.21547332)
    return [x / FMQ_SCALE for x in scale] + [fir[k] for k in (0, 1, 2, 3, 2, 1, 0)]


def _tab(L: C.Layout) -> int:
    """the table's address: Layout.PL["fm"] once dnfw.mnm.tables carries it (the integration);
    until then where it would follow the fold (for measuring the code only)"""
    return L.PL["fm"] if "fm" in L.PL else L.PL["fold"] + 4 * 516


def init(p: Prog, L: C.Layout) -> None:
    """FMEngine::Init: phases, amount, feedback, the one-pole and the FIR at 0; the frequencies at
    a0 (55 Hz)."""
    p.iconst(0, 0)
    for k in (CPH, MPH, PAM, PFB, PREV, CFIR):
        K.sv(p, k, 0)
    p.fconst(0, 55.0 / K.SR)
    K.sv(p, PCF, 0)
    K.sv(p, PMF, 0)


def _u32_body(p: Prog) -> None:
    K.mulk(p, 15, 15, U32, t=13)
    p.fconst(14, U32 / 2)
    p.if_(15, "GE", 14, lambda: p.fop(15, 15, "-", 13))
    p.trunc(15, 15)


def _u32(p: Prog, inline: bool = False) -> None:
    """R15 = static_cast<uint32_t>(2^32 F15), F15 in 0 .. 1 (exact). Clobbers R12-R14, I12.
    INLINE (2026-11-10): the body here, not a call (the sub-sample's)."""
    if inline:
        _u32_body(p)
    else:
        p.call("plfm_u32", lambda: _u32_body(p))


def _params(p: Prog, L: C.Layout) -> None:
    K.ld(p, 4, K.S_NOTE)
    K.addk(p, 4, 4, -24.0)                        # note (4x oversampling)
    K.par(p, 5, 0)
    K.mulk(p, 5, 5, 128.0)
    K.ifrac(p, 6, 7, 5)
    p.lsh(6, 6, 2)
    p.iconst(12, _tab(L))
    p.iop(6, 12, "+", 6)
    p.seti(1, 6)
    p.ldi(8, 0, 1)
    p.ldi(9, 1, 1)
    p.fop(9, 9, "-", 8)
    p.fop(9, 9, "*", 7)
    p.fop(8, 8, "+", 9)
    K.mulk(p, 8, 8, FMQ_SCALE)                    # ratio (semitones)
    p.fop(8, 4, "+", 8)                           # modulator_note
    K.note_freq(p, 9, 8)
    K.clamp(p, 9, 0.0, 0.5)
    K.interp_start(p, IMF, PMF, 9)
    K.addk(p, 10, 8, -72.0)                       # hf_taming
    K.mulk(p, 10, 10, 0.025)
    p.fconst(12, 1.0)
    p.fop(10, 12, "-", 10)
    K.clamp(p, 10, 0.0, 1.0)
    p.fop(10, 10, "*", 10)
    K.par(p, 5, 1)
    p.fop(6, 5, "+", 5)
    p.fop(6, 6, "*", 5)
    p.fop(6, 6, "*", 10)
    K.interp_start(p, IAM, PAM, 6)
    K.note_freq(p, 9, 4)
    K.interp_start(p, ICF, PCF, 9)
    K.par(p, 5, 2)
    p.fop(5, 5, "+", 5)
    K.addk(p, 5, 5, -1.0)
    K.interp_start(p, IFB, PFB, 5)


def _sub(p: Prog) -> None:
    """One 4x sub-sample: F2 amount, R4 carrier increment, F5 modulator frequency, F6 phase
    feedback, F7 modulator self-PM; F3 += carrier fir[3 - j] (I1 at j), F11 += carrier fir[j]."""
    K.ld(p, 9, PREV)
    p.fop(10, 9, "*", 6)
    K.addk(p, 10, 10, 1.0)
    p.fop(15, 10, "*", 5)
    _u32(p, inline=True)
    K.ld(p, 9, MPH)
    p.iop(9, 15, "+", 9)
    K.sv(p, MPH, 9)
    K.ld(p, 10, PREV)
    p.fop(10, 10, "*", 7)
    p.iconst(12, -32)
    p.float_(15, 9, 12)
    p.fop(15, 15, "+", 10)
    K.sinp_body(p)                                # modulator (2026-11-10: inline, not a call)
    p.fop(10, 2, "*", 15)
    K.ld(p, 9, CPH)
    p.iop(9, 9, "+", 4)
    K.sv(p, CPH, 9)
    p.iconst(12, -32)
    p.float_(15, 9, 12)
    p.fop(15, 15, "+", 10)
    K.sinp_body(p)                                # carrier (inline)
    K.ld(p, 9, PREV)
    p.fop(10, 15, "-", 9)
    K.mulk(p, 10, 10, 0.05)
    p.fop(9, 9, "+", 10)
    K.sv(p, PREV, 9)
    p.ldi(10, 3, 1)
    p.fop(10, 15, "*", 10)
    p.fop(3, 3, "+", 10)
    p.ldpost(10, 1)
    p.fop(10, 15, "*", 10)
    p.fop(11, 11, "+", 10)


def _sample(p: Prog, L: C.Layout) -> None:
    K.interp_next(p, 2, PAM, IAM)
    K.interp_next(p, 3, PFB, IFB)
    p.fconst(12, 0.0)
    p.fop(6, 3, "MIN", 12)
    p.fop(7, 3, "MAX", 12)
    K.mulk(p, 9, 6, 0.5)
    p.fop(6, 9, "*", 6)                           # phase_feedback
    K.mulk(p, 9, 7, 0.25)
    p.fop(7, 9, "*", 7)                           # modulator_fb
    K.interp_next(p, 15, PCF, ICF)
    _u32(p)
    p.ipass(4, 15)                                # carrier_increment
    K.interp_next(p, 5, PMF, IMF)
    K.ld(p, 3, CFIR)                              # the downsampler's head
    p.fconst(11, 0.0)                             # its tail
    p.iconst(9, L.YB)                             # the FIR (2026-11-10: its L1 copy, half's start)
    p.seti(1, 9)
    p.loop_r(8, 4, lambda: _sub(p))
    p.stpost(4, 3)
    K.sv(p, CFIR, 11)


def half(p: Prog, L: C.Layout) -> None:
    """FMEngine::Render(16 samples) at I4."""
    _params(p, L)
    p.iconst(9, _tab(L) + 4 * FMQ_N)              # 2026-11-10 (poly16): the FIR's 7 words to L1 (the
    p.seti(1, 9)                                  # render scratch's YB row) once a half: read 8 times
    p.iconst(9, L.YB)                             # a sample, they were 256 DDR reads a block
    p.seti(5, 9)
    for k in range(7):
        p.ldpost(9, 1)
        p.stpost(5, 9)
    p.loop(L.W["n4"], K.HALF, lambda: _sample(p, L))
