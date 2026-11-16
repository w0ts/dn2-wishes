"""PLAITS' PART: Mutable Instruments Plaits' particle engine (Emilie Gillet, MIT;
plaits/dsp/engine/particle_engine.cc, dsp/noise/particle.h, dsp/fx/diffuser.h, fx_engine.h).

OUT only: six particles (dust at TIMB's density, each a band-pass at the note spread by HARM
+-48 semitones, its frequency drawn when it fires, MORP's upper half its resonance), summed, the
post low-pass at the note, then the diffuser (MORP's lower half): four all-passes, a modulated
delay with a low-pass in the loop, two more all-passes. A trig fires every particle at once.

The diffuser's 8192-sample buffer is the voice's DDR area (plk.big_at), as floats (Plaits keeps
it as 12-bit fixed point in int16: FxEngine<8192, FORMAT_12_BIT>). The six particles' state
(pre-gain, g, r, h, the two filter states) are slot words, six a particle, walked by I1; the
particles accumulate into the half's output (I4's 16 words), which the post filter and the
diffuser then read and overwrite sample by sample.

The Svf's coefficients and tick, 1 / sqrt and 2^x are plaits_noise's subroutines.
"""

from __future__ import annotations

from . import core as C
from . import plk as K
from . import plaits_noise as N
from ..md import core as MD
from ..perc.dsl import Prog, f32

MODEL = "PART"
NP = 6                                         # kNumParticles
PW = 6                                         # a particle's words: PG, G, R, H, S1, S2
PS1, PS2, WP, LP, Y0, Y1 = (K.U0 + NP * PW + k for k in range(6))
# per half: the particles' parameters; then (after them) the post filter's and diffuser's
T0, T1, T2, T3, T4, T5 = (K.U0 + NP * PW + 6 + k for k in range(6))
DENS, GAIN, FREQ, SPREAD, QV, SQD = T0, T1, T2, T3, T4, T5
PG_, PR_, PH_, AMT, RT = T0, T1, T2, T3, T4
NU_USED = NP * PW + 12                         # 48
BIG_USED = 8192
MASK = 8191
KAP = 0.625


def _lfo_init() -> tuple[float, float]:
    """the diffuser's LFO_1 (CosineOscillator::InitApproximate(0.3 / 48000 x 32)): its IIR
    coefficient and initial y1"""
    f = f32(f32(f32(0.3) / 48000.0) * 32.0)
    sign = 16.0
    f = f32(f - 0.25)
    if f < 0.0:
        f = -f
    elif f > 0.5:
        f = f32(f - 0.5)
    else:
        sign = -16.0
    iir = f32(f32(sign * f) * f32(1.0 - f32(2.0 * f)))
    return iir, f32(iir * 0.25)


LFO_IIR, LFO_Y1 = _lfo_init()
# the delay lines (FxEngine Reserve<126, 180, 269, 444, 1653, 2010, 3411>): base, length
_LINES = []
_b = 0
for _l in (126, 180, 269, 444, 1653, 2010, 3411):
    _LINES.append((_b, _l))
    _b += _l + 1
AP1, AP2, AP3, AP4, DAPA, DAPB, DEL = _LINES


def _r_of_i4(p: Prog, d: int) -> None:
    """Rd = I4 (the form dnfw.mnm.machines._render uses)"""
    p.e(f"R{d} = I4;")
    if p.run:
        p.r[d] = p.i[4]


def init(p: Prog, L: C.Layout) -> None:
    """ParticleEngine::Init + Reset: the particles' pre-gains and filters at 0 (their g, r, h too:
    Plaits' Init sets them, but a particle's filter only ever ticks a 0 input with zero state
    until its first frequency is drawn, which sets them), the post filter at 0, the diffuser's
    LFO started, its low-pass at 0, its buffer cleared and its write pointer at 0."""
    p.iconst(0, 0)
    for k in range(NU_USED):
        K.sv(p, K.U0 + k, 0)
    p.fconst(0, 0.5)
    K.sv(p, Y0, 0)
    p.fconst(0, LFO_Y1)
    K.sv(p, Y1, 0)
    K.big_at(p, L, 0)
    p.seti(1, 0)
    p.iconst(2, 0)
    p.loop_r(3, BIG_USED, lambda: p.stpost(1, 2))


def _params(p: Prog) -> None:
    K.ld(p, 4, K.S_NOTE)
    N.note_freq(p, 5, 4)
    K.sv(p, FREQ, 5)                           # f0
    K.par(p, 6, 1)                             # density = NoteToFrequency(60 + 72 t^2)^2 / 6
    p.fop(6, 6, "*", 6)
    K.mulk(p, 6, 6, 72.0)
    K.addk(p, 6, 6, 60.0)
    N.note_freq(p, 7, 6)
    p.fop(7, 7, "*", 7)
    K.mulk(p, 7, 7, 1.0 / NP)
    K.sv(p, DENS, 7)
    K.recip(p, 8, 7)
    K.sv(p, GAIN, 8)                           # gain = 1 / density
    p.fpass(13, 7)
    N.rsqrt(p)
    p.fop(14, 7, "*", 14)
    K.sv(p, SQD, 14)                           # Sqrt(density)
    K.par(p, 6, 2)                             # q = 0.5 + SemitonesToRatio(max(morph - 0.5, 0) 120)^2
    K.addk(p, 7, 6, -0.5)
    K.mulk(p, 7, 7, 120.0)
    p.fconst(12, 0.0)
    p.fop(7, 7, "MAX", 12)
    N.semis(p, 8, 7)
    p.fop(8, 8, "*", 8)
    K.addk(p, 8, 8, 0.5)
    K.sv(p, QV, 8)
    K.par(p, 6, 0)                             # spread = 48 h^2
    K.mulk(p, 7, 6, 48.0)
    p.fop(7, 7, "*", 6)
    K.sv(p, SPREAD, 7)


def _fire(p: Prog) -> None:
    """The particle's frequency, drawn (the first time it fires in the half): F10 pre-gain,
    F1-F3 its Svf's g r h. Clobbers R0-R3, R6-R8, R11-R14."""
    K.rnd01(p, 6)
    p.fop(6, 6, "+", 6)
    K.addk(p, 6, 6, -1.0)
    K.ld(p, 7, SPREAD)
    p.fop(6, 7, "*", 6)
    N.semis(p, 6, 6)
    K.ld(p, 7, FREQ)
    p.fop(6, 6, "*", 7)
    p.fconst(12, 0.25)
    p.fop(6, 6, "MIN", 12)                     # f
    K.ld(p, 7, QV)
    p.fop(13, 7, "*", 6)
    K.ld(p, 12, SQD)
    p.fop(13, 13, "*", 12)
    N.rsqrt(p)
    K.mulk(p, 10, 14, 0.5)                     # pre_gain = 0.5 / Sqrt(q f Sqrt(density))
    N.tan_dirty(p, 1, 6)
    p.fpass(6, 7)
    N.svf_set(p)
    p.iconst(15, 0)                            # can_randomize_frequency = false


def _particle_sample(p: Prog) -> None:
    """One sample of Particle::Render: u in F6, the Svf in F1-F5, the pre-gain F10, R15 the
    frequency still to draw; the sum at I1 (moved on)."""
    p.fconst(9, 0.0)                           # s
    K.ld(p, 11, DENS)

    def fires():
        K.ld(p, 12, GAIN)
        p.fop(9, 6, "*", 12)
        p.ifz(15, "NE", lambda: _fire(p))
    p.if_(6, "LE", 11, fires)
    p.fop(0, 10, "*", 9)
    N.svf_tick(p)
    p.ldi(8, 0, 1)
    p.fop(8, 8, "+", 7)
    p.stpost(1, 8)
    K.rnd01(p, 6)                              # the next u


def _particle(p: Prog, L: C.Layout) -> None:
    """Particle::Render over the half; L.W['inner'] holds its words' address."""
    K.rnd01(p, 6)                              # u
    K.ld(p, 0, K.S_TRIG)
    p.ifz(0, "NE", lambda: K.ld(p, 6, DENS))
    p.iconst(15, 1)
    p.ld(0, L.W["inner"])
    p.seti(1, 0)
    p.ldi(10, 0, 1)
    for k in range(1, 6):
        p.ldi(k, k, 1)
    _r_of_i4(p, 0)
    p.seti(1, 0)
    p.loop(L.W["n4"], K.HALF, lambda: _particle_sample(p))
    p.ld(0, L.W["inner"])
    p.seti(1, 0)
    p.sti(0, 1, 10)
    for k in range(1, 6):
        p.sti(k, 1, k)
    p.iconst(12, 4 * PW)
    p.iop(0, 12, "+", 0)
    p.st(L.W["inner"], 0)


def _stage_sub(p: Prog) -> None:
    """The diffuser's read (FxEngine Context::Interpolate; a TAIL read is one at length - 1, its
    fraction 0): x = the line at R2 (base) + F1 (offset) from the write pointer R11, the buffer
    at R10; F5 = x, F4 += x F3. Then, R14 not 0, WriteAllPass(-F3): the line's head = F4,
    F4 = F4 (-F3) + x. Clobbers R0, R6-R9, R12, I1, I12."""
    def at(r):                                 # I1 = the buffer's word Rr (masked)
        p.iconst(12, MASK)
        p.iop(9, r, "AND", 12)
        p.lsh(9, 9, 2)
        p.iop(9, 10, "+", 9)
        p.seti(1, 9)

    def body():
        K.ifrac(p, 0, 6, 1)
        p.iop(8, 11, "+", 0)
        p.iop(8, 8, "+", 2)
        at(8)
        p.ldi(7, 0, 1)
        p.iconst(12, 1)
        p.iop(8, 8, "+", 12)
        at(8)
        p.ldi(9, 0, 1)
        p.fop(9, 9, "-", 7)
        p.fop(9, 9, "*", 6)
        p.fop(5, 7, "+", 9)
        p.fop(9, 5, "*", 3)
        p.fop(4, 4, "+", 9)

        def write():
            p.iop(8, 11, "+", 2)
            at(8)
            p.sti(0, 1, 4)
            p.fconst(12, 0.0)
            p.fop(12, 12, "-", 3)
            p.fop(4, 4, "*", 12)
            p.fop(4, 4, "+", 5)
        p.ifz(14, "NE", write)
    p.call("plpart_stage", body)


def _stage(p: Prog, line, off: float | None, scale: float | None, write: bool = True) -> None:
    """a diffuser stage: off None: F1 holds the offset; scale None: F3 holds it"""
    if off is not None:
        p.fconst(1, off)
    p.iconst(2, line[0])
    if scale is not None:
        p.fconst(3, scale)
    p.iconst(14, 1 if write else 0)
    _stage_sub(p)


def _post_diffuse(p: Prog, L: C.Layout) -> None:
    """One sample: the post low-pass on the particles' sum at I4, the diffuser, stored at I4."""
    p.ldi(0, 0, 4)
    K.ld(p, 1, PG_)
    K.ld(p, 2, PR_)
    K.ld(p, 3, PH_)
    K.ld(p, 4, PS1)
    K.ld(p, 5, PS2)
    N.svf_tick(p)
    K.sv(p, PS1, 4)
    K.sv(p, PS2, 5)
    p.fpass(15, 8)                             # the diffuser's input
    # FxEngine::Start: the write pointer back one, LFO_1 on every 32nd
    K.ld(p, 11, WP)
    p.iconst(12, 1)
    p.iop(11, 11, "-", 12)
    p.iconst(12, MASK)
    p.iop(11, 11, "AND", 12)
    K.sv(p, WP, 11)
    p.iconst(12, 31)
    p.iop(0, 11, "AND", 12)

    def lfo_next():
        K.ld(p, 6, Y0)
        K.ld(p, 7, Y1)
        K.mulk(p, 8, 6, LFO_IIR)
        p.fop(8, 8, "-", 7)
        K.sv(p, Y0, 8)
        K.sv(p, Y1, 6)
    p.ifz(0, "EQ", lfo_next)
    K.ld(p, 13, Y1)
    K.addk(p, 13, 13, 0.5)                     # the LFO's value
    p.fpass(4, 15)                             # c.Read(*in_out)
    _stage(p, AP1, AP1[1] - 1.0, KAP)
    _stage(p, AP2, AP2[1] - 1.0, None)
    _stage(p, AP3, AP3[1] - 1.0, None)
    K.mulk(p, 1, 13, 43.0)
    K.addk(p, 1, 1, 400.0)
    _stage(p, AP4, None, None)
    K.mulk(p, 1, 13, 340.0)
    K.addk(p, 1, 1, 3070.0)
    K.ld(p, 3, RT)
    _stage(p, DEL, None, None, write=False)
    K.ld(p, 6, LP)                             # c.Lp(lp_decay_, 0.75)
    p.fop(7, 4, "-", 6)
    K.mulk(p, 7, 7, 0.75)
    p.fop(4, 6, "+", 7)
    K.sv(p, LP, 4)
    _stage(p, DAPA, DAPA[1] - 1.0, -KAP)
    _stage(p, DAPB, DAPB[1] - 1.0, KAP)
    p.iconst(12, DEL[0])                       # c.Write(del, 2.0): wet = 2 acc
    p.iop(8, 11, "+", 12)
    p.iconst(12, MASK)
    p.iop(8, 8, "AND", 12)
    p.lsh(8, 8, 2)
    p.iop(8, 10, "+", 8)
    p.seti(1, 8)
    p.sti(0, 1, 4)
    p.fop(4, 4, "+", 4)
    p.fop(4, 4, "-", 15)                       # *in_out += amount (wet - *in_out)
    K.ld(p, 6, AMT)
    p.fop(4, 6, "*", 4)
    p.fop(4, 15, "+", 4)
    p.stpost(4, 4)


def _post_params(p: Prog) -> None:
    """the post filter's coefficients (f0 clamped to 0.49, q 0.5) and the diffuser's amount and
    rt, into the per-half words the particles are done with"""
    K.ld(p, 6, FREQ)
    p.fconst(12, 0.49)
    p.fop(6, 6, "MIN", 12)
    N.tan_dirty(p, 1, 6)
    p.fconst(6, 0.5)
    N.svf_set(p)
    K.sv(p, PG_, 1)
    K.sv(p, PR_, 2)
    K.sv(p, PH_, 3)
    # diffusion = morph < 0.5 ? (2 |morph - 0.5|)^2 : 0
    K.par(p, 6, 2)
    K.addk(p, 7, 6, -0.5)
    K.fabs(p, 7, 7)
    p.fop(7, 7, "+", 7)
    p.fop(7, 7, "*", 7)
    p.fconst(12, 0.5)
    p.if_(6, "GE", 12, lambda: p.fconst(7, 0.0))
    K.mulk(p, 8, 7, 0.8)
    p.fop(8, 8, "*", 7)
    K.sv(p, AMT, 8)
    K.mulk(p, 8, 7, 0.5)
    K.addk(p, 8, 8, 0.25)
    K.sv(p, RT, 8)


def half(p: Prog, L: C.Layout) -> None:
    _params(p)
    _r_of_i4(p, 0)                             # the sum: the half's output, cleared
    p.seti(1, 0)
    p.iconst(2, 0)
    p.loop_r(3, K.HALF, lambda: p.stpost(1, 2))
    p.ld(0, L.md.C["mdb"])                     # the slot's words: the first particle's
    p.iconst(12, 4 * (MD.S0 + K.U0))
    p.iop(0, 12, "+", 0)
    p.st(L.W["inner"], 0)
    p.loop(L.W["n5"], NP, lambda: _particle(p, L))
    _post_params(p)
    K.big_at(p, L, 10)
    p.loop(L.W["n4"], K.HALF, lambda: _post_diffuse(p, L))
