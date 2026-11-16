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

from ...mnm import core as C
from . import plk as K
from . import plaits_noise as N
from ...md import core as MD
from ...perc import msched as MS
from ...perc.dsl import Prog, f32

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
RNG_A = 1664525                             # plk.rnd01's multiplier


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
    LFO started, its low-pass at 0, its buffer cleared and its write pointer at 0. 2026-11-09:
    the buffer's clear deferred (plk.defer_clear), so a voice's start block is not 8,192 DDR
    stores; 2026-11-11 (plaits16): just in time instead (_jit: each word zeroed before the half
    that first reads it), so the voice sounds from its first half."""
    K.zero_state(p, K.U0, NU_USED)
    p.fconst(0, 0.5)
    K.sv(p, Y0, 0)
    p.fconst(0, LFO_Y1)
    K.sv(p, Y1, 0)
    # 2026-11-11: the write pointer starts at 32 x 17 x slot (a multiple of 32: the LFO's every-32nd
    # update falls where it did, and the buffer is cleared, so the output is the same), so the
    # voices' ring wraps (the half-blocks that run masked) come at different blocks, not all at
    # once after a chord
    K.big_at(p, L, 0)
    p.iconst(12, K.BIG_DDR)
    p.iop(0, 0, "-", 12)
    p.lsh(0, 0, -15)
    p.iconst(12, 17 * 32)
    p.mul_ssi(0, 0, 12)
    p.iconst(12, MASK)
    p.iop(0, 0, "AND", 12)
    K.sv(p, WP, 0)
    p.iconst(0, 0)
    K.sv(p, K.S_AGE, 0)


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
    frequency still to draw; the sum at I1 (moved on). 2026-11-10 (poly16): the voice's random
    generator in R13 through the loop (written back round _fire, which draws from the slot), the
    Svf's tick inline: the same operations in the same order. 2026-11-11: the generator's
    multiplier in R12 and its scale (-31) in R14 through the loop (set by _particle, again after
    _fire), the loop's own one in R9 (the sample starts by writing it); the same values."""
    p.fconst(9, 0.0)                           # s (F11: DENS, loaded before the loop)

    def fires():
        K.ld(p, 7, GAIN)
        p.fop(9, 6, "*", 7)

        def fire():
            K.sv(p, K.S_RNG, 13)
            _fire(p)
            K.ld(p, 13, K.S_RNG)
            K.ld(p, 11, DENS)                  # (_fire clobbers R11)
            p.iconst(12, RNG_A)
            p.iconst(14, -31)
        p.ifz(15, "NE", fire)
    p.if_(6, "LE", 11, fires)
    p.fop(0, 10, "*", 9)
    p.fop(9, 2, "*", 4)                        # N.svf_tick's body
    p.fop(6, 0, "-", 9)
    p.fop(9, 1, "*", 4)
    p.fop(6, 6, "-", 9)
    p.fop(6, 6, "-", 5)
    p.fop(6, 6, "*", 3)                        # hp
    p.fop(9, 1, "*", 6)
    p.fop(7, 9, "+", 4)                        # bp
    p.fop(4, 9, "+", 7)
    p.fop(9, 1, "*", 7)
    p.fop(8, 9, "+", 5)                        # lp
    p.fop(5, 9, "+", 8)
    p.ldi(8, 0, 1)
    p.fop(8, 8, "+", 7)
    p.stpost(1, 8)
    p.mul_ssi(13, 13, 12)                      # the next u: plk.rnd01 (rng's body) on R13
    p.iconst(0, 1013904223)
    p.iop(13, 13, "+", 0)
    p.lsh(0, 13, -1)
    p.float_(6, 0, 14)


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
    K.ld(p, 13, K.S_RNG)
    K.ld(p, 11, DENS)
    p.iconst(12, RNG_A)
    p.iconst(14, -31)
    p.loop(L.W["n4"], K.HALF // 4, lambda: [_particle_sample(p) for _ in range(4)], one=9)
    K.sv(p, K.S_RNG, 13)
    p.ld(0, L.W["inner"])
    p.seti(1, 0)
    p.sti(0, 1, 10)
    for k in range(1, 6):
        p.sti(k, 1, k)
    p.iconst(12, 4 * PW)
    p.iop(0, 12, "+", 0)
    p.st(L.W["inner"], 0)


# 2026-11-10 (poly16): the diffuser stage by stage over the half. Every read is 125 samples or more
# behind the write pointer (the shortest line's tail; AP4's modulated tap 357, DEL's 2,730), so no
# read of a half sees a write of the same half and each stage may run its 16 samples in a row; the
# five fixed-offset stages then walk their three words a sample by post-decrement (I0, I1, I5)
# instead of masking three addresses, as long as no window wraps round the buffer's end (_fast_ok;
# else the half runs as before, sample by sample). AP4 and DEL (their offsets on the LFO) keep the
# masked reads (_stage_sub) sample by sample. Every value with the same operations: bit-exact.
FIXED = ((AP1, KAP, True), (AP2, KAP, True), (AP3, KAP, True), (DAPA, -KAP, True), (DAPB, KAP, True))
IN_ROW, LFO_ROW = 0, 16                        # the render scratch's YB row: the inputs, the LFO
Z_ROW = 32                                     # 17 zeros (_jit, plaits16): a young line's reads in a fast half
MV_FLAG = Z_ROW + 17                           # AP4's, DEL's: every read of this (fast) half unwritten (_jit)


def _fast_ok(p: Prog, d: int) -> None:
    """Rd = 1 if the half's every fixed window stays inside the buffer, else 0. Clobbers R0, R8, R12."""
    K.ld(p, 8, WP)
    p.iconst(12, -1)
    p.iop(8, 12, "+", 8)                       # this half's first write pointer (before its mask)
    p.iconst(d, 1)
    cs = [(b + l - 1, True) for (b, l), _k, _w in FIXED] + [(b, False) for (b, l), _k, _w in FIXED]
    cs += [(AP4[0], False), (DEL[0], False)]
    for c, read in cs:
        p.iconst(12, c)
        p.iop(0, 12, "+", 8)
        p.iconst(12, MASK)
        p.iop(0, 0, "AND", 12)
        p.iconst(12, 15)
        p.if_(0, "LT", 12, lambda: p.iconst(d, 0), kind="i")
        if read:
            p.iconst(12, MASK - 1)
            p.if_(0, "GT", 12, lambda: p.iconst(d, 0), kind="i")


def _ptr(p: Prog, i: int, c: int) -> None:
    """Ii = the buffer's word (wp0 + c) & MASK; R11 wp0, R10 the buffer. Clobbers R0, R12."""
    p.iconst(12, c)
    p.iop(0, 12, "+", 11)
    p.iconst(12, MASK)
    p.iop(0, 0, "AND", 12)
    p.lsh(0, 0, 2)
    p.iop(0, 10, "+", 0)
    p.seti(i, 0)


def _acc_row(p: Prog, L: C.Layout) -> None:
    """I4 = the half's samples (the accumulator), from L.W['wb']."""
    p.ld(0, L.W["wb"])
    p.seti(4, 0)


# 2026-11-14 (plaits16, r52): a fixed stage's 16 samples straight, placed by dnfw.perc.msched into multifunction
# instructions with their loads and stores on them (the loop did one operation an instruction). The same operations
# on the same values: x is worked out twice (XM for the multiply, XA for the add; the same add of the same operands,
# the same bits). Every register is the stage's: R10 (the buffer) and R11 (wp0) are put back after it, R10 from
# W["inner"] (the particles' pointer, free once they are done: _stages saves R10 there). The registers: a search
# over assignments (scratch fixexp2.py), two sets that alternate a sample.
FX_FRAC, FX_K, FX_NK, FX_X1 = "F4", "F7", "F1", "F13"
FX_SETS = ({"x0": "F10", "d": "F2", "d2": "F12", "xm": "F2", "xa": "F15", "t": "F6", "a": "F13", "a2": "F5",
            "a3": "F13", "a4": "F9"},
           {"x0": "F14", "d": "F0", "d2": "F11", "xm": "F3", "xa": "F13", "t": "F15", "a": "F5", "a2": "F6",
            "a3": "F9", "a4": "F3"})


def _fixed_ops() -> list:
    """the 16 samples' operations: I0 x0 (offset -s; x1 the word one on, the sample before's x0), I2 the half's
    samples (offset s), I1 the line's head (offset -s)."""
    ops = [("mov", "ldk", (FX_X1,), (), ("I0", 1))]
    for s in range(K.HALF):
        r, q = FX_SETS[s % 2], FX_SETS[(s - 1) % 2]
        x1 = FX_X1 if s == 0 else q["x0"]
        ops += [("mov", "ldk", (r["x0"],), (), ("I0", -s)),
                ("alu", "-", (r["d"],), (x1, r["x0"]), None),          # x1 - x0
                ("mul", "*", (r["d2"],), (r["d"], FX_FRAC), None),     # x the fraction (0)
                ("alu", "+", (r["xm"],), (r["x0"], r["d2"]), None),    # x (for the multiply)
                ("alu", "+", (r["xa"],), (r["x0"], r["d2"]), None),    # x (for the add)
                ("mul", "*", (r["t"],), (r["xm"], FX_K), None),        # x k
                ("mov", "ldk", (r["a"],), (), ("I2", s)),
                ("alu", "+", (r["a2"],), (r["a"], r["t"]), None),      # acc + x k
                ("mov", "stk", (), (r["a2"],), ("I1", -s)),             # the line's head
                ("mul", "*", (r["a3"],), (r["a2"], FX_NK), None),      # x (0 - k)
                ("alu", "+", (r["a4"],), (r["a3"], r["xa"]), None),    # + x
                ("mov", "stk", (), (r["a4"],), ("I2", s))]
    return ops


def _fixed(p: Prog, L: C.Layout, line, k: float, write: bool) -> None:
    """a fixed-offset stage over the 16 samples (the TAIL read, its fraction 0). R10 the buffer, R11 wp0 (put
    back after: R10 from W["inner"])."""
    assert write, "every fixed stage writes its line (FIXED)"
    b, l = line
    _ptr(p, 0, b + l - 1)                      # x0 at offset -s, x1 (no wrap: _fast_ok) the word one on
    _ptr(p, 1, b)                              # the head
    K.ld(p, 0, K.S_AGE)                        # 2026-11-11 (_jit): every read of the half of a word no write
    p.iconst(12, l - 1)                        # has reached (AGE - 16 <= l - 17): the zero row's words instead

    def zeros():
        p.iconst(0, L.YB + 4 * (Z_ROW + 15))
        p.seti(0, 0)
    p.if_(0, "LE", 12, zeros, kind="i")
    p.ld(0, L.W["wb"])
    p.seti(2, 0)                               # the half's samples
    frac, kk, nk = (int(r[1:]) for r in (FX_FRAC, FX_K, FX_NK))
    p.fconst(frac, 0.0)                        # the fraction
    p.fconst(kk, k)
    p.fconst(nk, 0.0)
    p.fop(nk, nk, "-", kk)                     # -k (0 - k, as _stage_sub)
    MS.emit(p, _fixed_ops())
    p.ld(10, L.W["inner"])
    p.ld(0, L.W["sb"])
    p.ipass(11, 0)


def _moving_masked(p: Prog, L: C.Layout, line, scale_rt: bool, write: bool, mul: float, add: float) -> None:
    """AP4 / DEL over the 16 samples: the offset add + mul x LFO (its row); _stage_sub's operations
    inline (2026-11-10: no call a sample). The offset (F1, its integer part R2, its fraction F6) is
    worked out again only when the LFO's value changes (once a half at most; F15 the last value),
    and x1 (F14) is the sample before's x0: the same word, as the write pointer moves one back a
    sample and the offset stays. The same operations on the same values."""
    base = line[0]
    _acc_row(p, L)
    p.iconst(0, L.YB + 4 * LFO_ROW)
    p.seti(5, 0)
    p.ld(0, L.W["sb"])
    p.ipass(11, 0)                             # wp0
    if scale_rt:
        K.ld(p, 3, RT)
    else:
        p.fconst(3, KAP)
    p.fconst(15, -1.0)                         # no LFO value yet (it is 0..1)

    def at(r):
        p.iconst(12, MASK)
        p.iop(9, r, "AND", 12)
        p.lsh(9, 9, 2)
        p.iop(9, 10, "+", 9)
        p.seti(1, 9)

    def recompute():
        p.fpass(15, 13)
        K.mulk(p, 1, 13, mul)
        K.addk(p, 1, 1, add)                   # the offset
        p.trunc(2, 1)
        p.float0(6, 2)
        p.fop(6, 1, "-", 6)                    # its fraction
        p.iop(8, 11, "+", 2)
        p.iconst(12, base + 1)
        p.iop(8, 12, "+", 8)
        at(8)
        p.ldi(14, 0, 1)                        # x1

    def one():
        p.ldpost(13, 5)                        # the LFO's value
        p.if_(13, "NE", 15, recompute)
        p.iop(8, 11, "+", 2)
        p.iconst(12, base)
        p.iop(8, 12, "+", 8)
        at(8)
        p.ldi(7, 0, 1)                         # x0
        p.fop(9, 14, "-", 7)                   # x1 - x0
        p.fop(9, 9, "*", 6)
        p.fop(5, 7, "+", 9)                    # x
        p.fop(9, 5, "*", 3)
        p.ldi(4, 0, 4)
        p.fop(4, 4, "+", 9)
        if write:
            p.iconst(12, base)
            p.iop(8, 12, "+", 11)
            at(8)
            p.sti(0, 1, 4)
            p.fconst(12, 0.0)
            p.fop(12, 12, "-", 3)
            p.fop(4, 4, "*", 12)
            p.fop(4, 4, "+", 5)
        p.stpost(4, 4)
        p.fpass(14, 7)                         # the next sample's x1
        p.iconst(12, -1)                       # the next sample's write pointer
        p.iop(11, 12, "+", 11)
        p.iconst(12, MASK)
        p.iop(11, 11, "AND", 12)
    p.loop(L.W["n5"], K.HALF, one)


def _moving(p: Prog, L: C.Layout, line, scale_rt: bool, write: bool, mul: float, add: float,
            lo: int, hi: int) -> None:
    """AP4 / DEL over the 16 samples: `_moving_masked`'s arithmetic, but the line's words walked by
    pointers (I0 the read, one word back a sample; I1 the head write likewise) instead of masking
    three addresses a sample, when no word of the half's windows wraps round the buffer's end:
    the head (checked by _fast_ok), and the reads, whose offset is the LFO's: its integer part
    stays in LO..HI (the LFO is 0..1: offset = mul x it + add, the bounds with a margin), so every
    read of the half is inside the range [wp + base + LO - 15, wp + base + HI + 1] (mod the
    buffer) and one test of its two ends tells. Else the half runs masked. 2026-11-11: the same
    operations on the same words, so the same floats."""
    base = line[0]

    def fast():
        _acc_row(p, L)
        p.iconst(0, L.YB + 4 * LFO_ROW)
        p.seti(5, 0)
        p.ld(0, L.W["sb"])                         # wp0: I1 = the head word (base + wp0)
        p.iconst(12, base)
        p.iop(0, 12, "+", 0)
        p.iconst(12, MASK)
        p.iop(0, 0, "AND", 12)
        p.lsh(0, 0, 2)
        p.iop(0, 10, "+", 0)
        p.seti(1, 0)
        p.seti(0, 0)                               # I0 = x0 at offset 0, before the first sample's
        p.iconst(2, 0)                             # recompute moves it to the LFO's
        if scale_rt:
            K.ld(p, 3, RT)
        else:
            p.fconst(3, KAP)
        if write:
            p.fconst(12, 0.0)
            p.fop(12, 12, "-", 3)                  # -k (0 - k, as _stage_sub)
        p.fconst(15, -1.0)                         # no LFO value yet (it is 0..1)

        def stale():                               # 2026-11-11 (plaits16, _jit): every word the half reads is
            p.fconst(5, 0.0)                       # one no write has reached (Plaits': 0), so x = 0 + (0 - 0) frac
            p.fconst(9, 0.0)                       # = +0 and x k = +0 (k > 0): the rest of one()'s operations

            def s1():
                p.ldi(4, 0, 4)
                p.fop(4, 4, "+", 9)
                if write:
                    p.stm(1, 4)
                    p.fop(4, 4, "*", 12)
                    p.fop(4, 4, "+", 5)
                p.stpost(4, 4)
            p.loop_r(2, K.HALF, s1, one=13)        # (F12 is -k)

        def recompute():
            p.fpass(15, 13)
            p.ipass(8, 2)                          # the old integer part (0 before the first)
            K.mulk(p, 1, 13, mul, 9)               # (F12 is -k: the constants through R9)
            K.addk(p, 1, 1, add, 9)                # the offset
            p.trunc(2, 1)
            p.float0(6, 2)
            p.fop(6, 1, "-", 6)                    # its fraction
            p.iop(8, 2, "-", 8)                    # I0 (this sample's x0, at the old offset) moved by
            p.lsh(8, 8, 2)                         # the change, masked round the buffer
            p.geti(9, 0)
            p.iop(8, 8, "+", 9)
            p.iop(8, 8, "-", 10)
            p.iconst(9, 4 * MASK)
            p.iop(8, 8, "AND", 9)
            p.iop(8, 10, "+", 8)
            p.seti(0, 8)
            p.ldi(14, 1, 0)                        # x1

        def one():
            p.ldpost(13, 5)                        # the LFO's value
            p.if_(13, "NE", 15, recompute)
            p.ldm(7, 0)                            # x0
            p.fop(9, 14, "-", 7)                   # x1 - x0
            p.fop(9, 9, "*", 6)
            p.fop(5, 7, "+", 9)                    # x
            p.fop(9, 5, "*", 3)
            p.ldi(4, 0, 4)
            p.fop(4, 4, "+", 9)
            if write:
                p.stm(1, 4)
                p.fop(4, 4, "*", 12)
                p.fop(4, 4, "+", 5)
            p.stpost(4, 4)
            p.fpass(14, 7)                         # the next sample's x1
        p.ld(0, L.YB + 4 * (MV_FLAG + [AP4, DEL].index(line)))
        p.ifz(0, "NE", stale, lambda: p.loop(L.W["n5"], K.HALF // 2, lambda: (one(), one()), one=9))

    p.ld(0, L.W["sb"])
    p.iconst(12, base + lo)
    p.iop(8, 12, "+", 0)
    p.iconst(12, MASK)
    p.iop(8, 8, "AND", 12)
    p.iconst(9, 1)
    p.iconst(12, 15)
    p.if_(8, "LT", 12, lambda: p.iconst(9, 0), kind="i")
    p.iconst(12, MASK - (hi - lo) - 1)
    p.if_(8, "GT", 12, lambda: p.iconst(9, 0), kind="i")
    p.ifz(9, "NE", fast, lambda: _moving_masked(p, L, line, scale_rt, write, mul, add))


def _at(p: Prog, r: int) -> None:
    """I1 = the buffer's word Rr (masked); R10 the buffer. Clobbers R9, R12."""
    p.iconst(12, MASK)
    p.iop(9, r, "AND", 12)
    p.lsh(9, 9, 2)
    p.iop(9, 10, "+", 9)
    p.seti(1, 9)


def _step_wp(p: Prog) -> None:
    """R11 = (R11 - 1) & MASK"""
    p.iconst(12, -1)
    p.iop(11, 12, "+", 11)
    p.iconst(12, MASK)
    p.iop(11, 11, "AND", 12)


def _fixed_masked(p: Prog, L: C.Layout, line, k: float, write: bool) -> None:
    """_fixed's stage with every address masked, a sample at a time: the half's windows wrap round
    the buffer's end (_fast_ok said no). The operations of the old sample-by-sample stage
    (FxEngine Context::Interpolate at a TAIL read, fraction 0, then WriteAllPass), so the same
    floats; 2026-11-11: this stage alone, not the whole chain a sample at a time."""
    b, l = line
    _acc_row(p, L)
    p.ld(0, L.W["sb"])
    p.ipass(11, 0)                             # wp0
    p.fconst(6, 0.0)                           # the fraction
    p.fconst(3, k)

    def one():
        p.iconst(12, b + l - 1)
        p.iop(8, 12, "+", 11)
        _at(p, 8)
        p.ldi(7, 0, 1)                         # x0
        p.iconst(12, 1)
        p.iop(8, 8, "+", 12)
        _at(p, 8)
        p.ldi(9, 0, 1)                         # x1
        p.fop(9, 9, "-", 7)
        p.fop(9, 9, "*", 6)
        p.fop(5, 7, "+", 9)                    # x
        p.fop(9, 5, "*", 3)
        p.ldi(4, 0, 4)
        p.fop(4, 4, "+", 9)
        if write:
            p.iconst(12, b)
            p.iop(8, 12, "+", 11)
            _at(p, 8)
            p.sti(0, 1, 4)
            p.fconst(12, 0.0)
            p.fop(12, 12, "-", 3)
            p.fop(4, 4, "*", 12)
            p.fop(4, 4, "+", 5)
        p.stpost(4, 4)
        _step_wp(p)
    p.loop(L.W["n5"], K.HALF, one)


# 2026-11-14 (plaits16, r52): the fast half's mix straight, placed by dnfw.perc.msched (its moves on its computes):
# I2 the half's samples read, I3 them written (one pointer for both would order every sample's read after the
# sample before's write), I1 DEL's head, I0 the inputs. I3 is the slot's pointer: kept in W["inner"] meanwhile
# (_fixed's saved R10 is done with). The same operations on the same values.
MIX_AMT = "F6"
MIX_SETS = ({"a": "F8", "in": "F12", "a2": "F9", "a3": "F0", "o": "F10"},
            {"a": "F11", "in": "F13", "a2": "F14", "a3": "F1", "o": "F15"},
            {"a": "F4", "in": "F7", "a2": "F2", "a3": "F3", "o": "F5"})


def _mix_ops() -> list:
    ops = []
    for s in range(K.HALF):
        r = MIX_SETS[s % len(MIX_SETS)]
        ops += [("mov", "ldk", (r["a"],), (), ("I2", s)),
                ("mov", "stk", (), (r["a"],), ("I1", -s)),             # c.Write(del, 2.0): DEL's head
                ("mov", "ldk", (r["in"],), (), ("I0", s)),
                ("alu", "+", (r["a2"],), (r["a"], r["a"]), None),      # 2 acc
                ("alu", "-", (r["a3"],), (r["a2"], r["in"]), None),    # - in
                ("mul", "*", (r["o"],), (MIX_AMT, r["a3"]), None),     # x amount
                ("alu", "+", (r["o"],), (r["in"], r["o"]), None),      # in +
                ("mov", "stk", (), (r["o"],), ("I3", s))]
    return ops


def _mix_fast(p: Prog, L: C.Layout) -> None:
    """_mix of a fast half (R10 the buffer, R11 wp0); I4 left past the half's samples, as _mix's loop."""
    _ptr(p, 1, DEL[0])
    K.ld(p, int(MIX_AMT[1:]), AMT)
    b3 = p.ibias.get(3)                         # I3 as the voice set it: biased (program.I3_BIAS)
    p.geti(0, 3)
    p.st(L.W["inner"], 0)
    p.iconst(0, L.YB + 4 * IN_ROW)
    p.seti(0, 0)
    p.ld(0, L.W["wb"])
    p.seti(2, 0)
    p.seti(3, 0)
    MS.emit(p, _mix_ops())
    p.ld(0, L.W["inner"])
    p.seti(3, 0, bias=b3)
    p.ld(0, L.W["wb"])
    p.iconst(12, 4 * K.HALF)
    p.iop(0, 12, "+", 0)
    p.seti(4, 0)


def _mix(p: Prog, L: C.Layout, masked: bool) -> None:
    """c.Write(del, 2.0), the mix: *in_out += amount (2 acc - in)"""
    if not masked:
        _mix_fast(p, L)
        return
    _acc_row(p, L)
    if masked:
        p.ld(0, L.W["sb"])
        p.ipass(11, 0)
    else:
        _ptr(p, 5, DEL[0])
    p.iconst(0, L.YB + 4 * IN_ROW)
    p.seti(0, 0)
    K.ld(p, 6, AMT)

    def mix():
        if masked:
            p.iconst(12, DEL[0])
            p.iop(8, 12, "+", 11)
            _at(p, 8)
        p.ldi(4, 0, 4)
        if masked:
            p.sti(0, 1, 4)
        else:
            p.stm(5, 4)
        p.ldpost(15, 0)
        p.fop(4, 4, "+", 4)
        p.fop(4, 4, "-", 15)
        p.fop(4, 6, "*", 4)
        p.fop(4, 15, "+", 4)
        p.stpost(4, 4)
        if masked:
            _step_wp(p)
    if masked:
        p.loop(L.W["n5"], K.HALF, mix)
    else:
        p.loop_r(2, K.HALF, mix)


def _stages(p: Prog, L: C.Layout, masked: bool) -> None:
    """the diffuser's stages over the half (the rows and WP/sb are set): fast (pointer walks) or,
    for a half whose windows wrap round the buffer's end, masked (2026-11-11: stage by stage as
    well, not the old sample-by-sample chain)."""
    fixed = _fixed_masked if masked else _fixed
    if not masked:
        p.st(L.W["inner"], 10)                 # R10 the buffer, for _fixed to put back (2026-11-14)
    for line, k, w in FIXED[:3]:
        fixed(p, L, line, k, w)
    if masked:
        _moving_masked(p, L, AP4, False, True, 43.0, 400.0)
        _moving_masked(p, L, DEL, True, False, 340.0, 3070.0)
    else:
        _moving(p, L, AP4, False, True, 43.0, 400.0, 396, 446)
        _moving(p, L, DEL, True, False, 340.0, 3070.0, 3040, 3440)
    # c.Lp(lp_decay_, 0.75), sample by sample
    _acc_row(p, L)
    K.ld(p, 6, LP)
    p.fconst(3, 0.75)

    def lp():
        p.ldi(4, 0, 4)
        p.fop(7, 4, "-", 6)
        p.fop(7, 7, "*", 3)
        p.fop(6, 6, "+", 7)
        p.stpost(4, 6)
    p.loop_r(2, K.HALF, lp)
    K.sv(p, LP, 6)
    K.ld(p, 11, WP)
    p.ld(0, L.W["sb"])
    p.ipass(11, 0)
    for line, k, w in FIXED[3:]:
        fixed(p, L, line, k, w)
    _mix(p, L, masked)


# 2026-11-11 (plaits16): the buffer is not cleared at the engine's start (it was, since 2026-11-09 over the start's
# first halves, silent): a read of a word no write has reached since the start must read 0, as Plaits' cleared
# buffer, and each such word is zeroed just before the half that reads it. A line's head writes the word at its
# offset `base` from the write pointer, which moves one word back a sample, so the word read at offset base + j
# in sample s of a half that starts t0 samples after the start (j relative to the half's first write pointer
# wp0) was written j samples earlier; it has not been when j > t0. A half reads, per line, j in [R - 16, R + 1]:
# R = l - 1 for a fixed line (its tail, x1 one on); for AP4 / DEL R is the LFO's integer offset at the half's
# larger LFO value (the LFO moves once in 32 samples, by under 0.3 of a sample, so the half's other offset is
# R or R - 1). Before the stages, while t0 <= the largest R (AGE < YOUNG), the words wp0 + base + j for j in
# [max(t0 + 1, R - 17), R + 1] are zeroed: words no write has reached (the line's own head reaches them later;
# the next line's head writes them only after this line's reads, stage by stage), so a zero there is what
# Plaits' cleared buffer holds. The output is the same as a clear at the start, sample for sample, and the voice
# sounds from its first half; the clear's 8,192 DDR stores are spread over the first 3,456 samples, 17-19 words
# a line a half.
YOUNG = 3456
MOVING = ((AP4, 43.0, 400.0), (DEL, 340.0, 3070.0))   # _moving's lines: their offset = add + mul x the LFO


def _jitz_body(p: Prog) -> None:
    """R1 = R, R2 = the line's base, R9 = t0 + 1, R10 the buffer, R11 wp0: zero the words wp0 + base + j, j in
    [max(t0 + 1, R - 17), R + 1], round the buffer's end; none when R0 is not 0 (a fixed line in a fast half)
    and every read of the half is of such a word (R - 16 >= t0: _fixed reads the zero row then). Clobbers R1-R6,
    R8, R12, I1."""
    p.iconst(12, -17)
    p.iop(3, 12, "+", 1)
    p.iop(3, 3, "MAX", 9)                      # the first j
    p.iop(4, 1, "-", 3)
    p.iconst(12, 2)
    p.iop(4, 12, "+", 4)                       # the words: R + 2 - the first j

    def fixed_fast():
        p.iconst(12, -15)
        p.iop(5, 12, "+", 1)
        p.if_(5, "GE", 9, lambda: p.iconst(4, 0), kind="i")
    p.ifz(0, "NE", fixed_fast)

    def zero():
        p.iop(8, 11, "+", 2)
        p.iop(8, 8, "+", 3)
        p.iconst(12, MASK)
        p.iop(8, 8, "AND", 12)                 # the first word
        p.iconst(12, MASK + 1)
        p.iop(5, 12, "-", 8)
        p.iop(5, 5, "MIN", 4)                  # the words before the buffer's end
        p.iop(4, 4, "-", 5)                    # and after it
        p.lsh(8, 8, 2)
        p.iop(8, 8, "+", 10)
        p.seti(1, 8)
        p.iconst(6, 0)
        p.loop_r(5, None, lambda: p.stpost(1, 6))

        def rest():
            p.seti(1, 10)
            p.loop_r(4, None, lambda: p.stpost(1, 6))
        p.ifz(4, "GT", rest)
    p.ifz(4, "GT", zero)


def _jit(p: Prog, L: C.Layout) -> None:
    """while the voice is young: zero the words this half's stages read that no write has reached (above), or,
    a fixed line in a fast half that reads only such words, write the zero row it reads instead (_fixed). R10
    the buffer, R11 wp0 (kept); the LFO's row written. Clobbers R0-R9, R12, I1, I12."""
    K.ld(p, 0, K.S_AGE)                        # t0

    def young():
        p.iconst(12, K.HALF)
        p.iop(1, 12, "+", 0)
        K.sv(p, K.S_AGE, 1)
        p.iconst(12, 1)
        p.iop(9, 12, "+", 0)
        p.iconst(0, L.YB + 4 * Z_ROW)          # the zero row (the render scratch is anyone's between halves)
        p.seti(1, 0)
        p.iconst(6, 0)
        p.loop_r(5, 17, lambda: p.stpost(1, 6))
        p.ld(0, L.W["tmp2"])                   # _fast_ok's verdict: R0 for the fixed lines

        def lines(group):
            for (b, l), _k, _w in group:
                p.iconst(1, l - 1)
                p.iconst(2, b)
                p.call("plpart_jitz", lambda: _jitz_body(p))
        for group in (FIXED[:3], FIXED[3:]):     # nothing to zero in a group once t0 > R = l - 1 for all its lines
            p.iconst(12, max(l for (_b, l), _k, _w in group))
            p.if_(9, "LE", 12, lambda group=group: lines(group), kind="i")   # (R9 = t0 + 1 <= l)
        p.ld(7, L.YB + 4 * LFO_ROW)
        p.ld(8, L.YB + 4 * (LFO_ROW + K.HALF - 1))
        p.fop(7, 7, "MAX", 8)                  # the half's larger LFO value
        for k, ((b, _l), mul, add) in enumerate(MOVING):
            K.mulk(p, 1, 7, mul)               # _moving's operations: its integer offset there
            K.addk(p, 1, 1, add)
            p.trunc(1, 1)
            p.ld(4, L.W["tmp2"])               # a fast half whose every read (j >= R - 16) is unwritten: no
            p.iconst(12, -16)                  # zeros stored, _moving's stale loop instead (its x is +0)
            p.iop(5, 12, "+", 1)
            p.if_(5, "LT", 9, lambda: p.iconst(4, 0), kind="i")
            p.st(L.YB + 4 * (MV_FLAG + k), 4)
            p.iconst(0, 0)                     # (no zero row for AP4 / DEL)
            p.iconst(2, b)
            p.ifz(4, "EQ", lambda: p.call("plpart_jitz", lambda: _jitz_body(p)))

    def old():
        p.iconst(4, 0)
        for k in range(len(MOVING)):
            p.st(L.YB + 4 * (MV_FLAG + k), 4)
    p.iconst(12, YOUNG)
    p.if_(0, "LT", 12, young, old, kind="i")


def _diffuse_fast(p: Prog, L: C.Layout) -> None:
    """the post filter and the diffuser, stage by stage (see FIXED); L.W["tmp2"] holds _fast_ok's verdict."""
    p.geti(0, 4)
    p.st(L.W["wb"], 0)                          # the half's samples (the accumulator)
    # the post filter and the LFO, sample by sample: the inputs and the LFO's values to rows
    K.ld(p, 1, PG_)
    K.ld(p, 2, PR_)
    K.ld(p, 3, PH_)
    K.ld(p, 4, PS1)
    K.ld(p, 5, PS2)
    p.iconst(0, L.YB + 4 * IN_ROW)
    p.seti(0, 0)
    p.iconst(0, L.YB + 4 * LFO_ROW)
    p.seti(5, 0)
    K.ld(p, 11, WP)
    K.ld(p, 13, Y1)                             # 2026-11-11 (plaits16): the LFO's row value in F13 through the
    K.addk(p, 13, 13, 0.5)                      # loop, worked out again only when the LFO moves (the same add on
                                                # the same Y1); the count in R15, the pointer's step a DEC
    def first():
        p.ldi(0, 0, 4)
        for d, a, op, b in ((9, 2, "*", 4), (6, 0, "-", 9), (9, 1, "*", 4), (6, 6, "-", 9), (6, 6, "-", 5),
                            (6, 6, "*", 3), (9, 1, "*", 6), (7, 9, "+", 4), (4, 9, "+", 7), (9, 1, "*", 7),
                            (8, 9, "+", 5), (5, 9, "+", 8)):
            p.fop(d, a, op, b)                  # N.svf_tick's body, here (no call a sample)
        p.stpost(4, 8)                          # the accumulator starts at the input
        p.stpost(0, 8)
        p.dec(11, 11)
        p.iconst(12, MASK)
        p.iop(11, 11, "AND", 12)
        p.iconst(12, 31)
        p.iop(0, 11, "AND", 12)

        def lfo_next():
            K.ld(p, 6, Y0)
            K.ld(p, 7, Y1)
            K.mulk(p, 8, 6, LFO_IIR)
            p.fop(8, 8, "-", 7)
            K.sv(p, Y0, 8)
            K.sv(p, Y1, 6)
            K.addk(p, 13, 6, 0.5)
        p.ifz(0, "EQ", lfo_next)
        p.stpost(5, 13)
    p.loop_r(15, K.HALF, first)
    K.sv(p, PS1, 4)
    K.sv(p, PS2, 5)
    p.iconst(12, K.HALF - 1)                    # wp0 = the first sample's (15 on from the last's, R11)
    p.iop(0, 12, "+", 11)
    p.iconst(12, MASK)
    p.iop(0, 0, "AND", 12)
    p.st(L.W["sb"], 0)
    K.sv(p, WP, 11)
    p.ipass(11, 0)
    _jit(p, L)
    p.ld(0, L.W["tmp2"])
    p.ifz(0, "NE", lambda: _stages(p, L, False), lambda: _stages(p, L, True))


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
    _fast_ok(p, 9)
    p.st(L.W["tmp2"], 9)
    _diffuse_fast(p, L)
