"""PLAITS' engines' common ground (dnfw.mnm.plaits; docs/plaits.md): the slot words they share,
their memory in DDR, and the arithmetic they are written with. A leaf module: the engine modules
(plaits_*.py) import it, dnfw.mnm.plaits imports them.

The slot's state words (dnfw.md.core S0, 96 of them): WS's at 0..43 (GRAIN's, removed 2026-11-09, unused) (dnfw.mnm.plaits),
then the words every engine reads (the note, the model last rendered, the trigger, the random
generator), then the UNION: each other engine's own words, from U0. An engine's words are its own
only while it is the model: on a change of model the new one's `init` runs (Plaits' Reset; its
engines keep no state across a change worth a second copy here).

Each voice (slot) also has BIG_STRIDE bytes of DDR at BIG_DDR + slot x BIG_STRIDE (`big`): the
delay lines, the resonators' modes, the diffuser. Nothing ships there; an engine clears what it
reads in its `init`.

Arithmetic, as Plaits' float32 C (stmlib dsp.h, units.h, utils/random.h):
- `exp2p`: 2^x from the float's exponent bits and a polynomial on the fraction (2.1e-7 relative, float32's rounding:
  Plaits' SemitonesToRatio reads 1/256-semitone tables, so the reference takes exact powers and
  the difference is Plaits' quantisation, not ours);
- `sinp`: sin(2 pi x) by an odd polynomial on the quarter turn (1.9e-7 for x in 0..1: Plaits' lut_sine, 1024
  points linear, is 4.7e-6 off);
- `rng`: stmlib::Random, one per voice (seeded 0x21 as stmlib's): state x 1664525 + 1013904223;
  `rnd01` its GetFloat (the word / 2^32; here (word >> 1) / 2^31, the same float but for ties).
"""

from __future__ import annotations

import math

from . import core as C
from ..md import core as K
from ..perc.dsl import Prog

SR = 44100.0
HALF = 16                                      # a half: Plaits' block (its interpolators' length)
F_MAX, F_MIN = 0.25, 0.000001                  # plaits::kMaxFrequency, kMinFrequency
A0 = 440.0 / SR                                # a note's frequency: A0 x 2^((note - 69) / 12)

S_BASE = 17                                    # dnfw.mnm.plaits: WS's f0 (PERC's exp2)
S_NOTE, S_LAST, S_TRIG, S_RNG = 44, 45, 46, 47
U0 = 48                                        # the engines' own words: U0 .. K.NS - 1
NU = K.NS - U0                                 # 48

BIG_DDR, BIG_STRIDE = 0x82600000, 0x8000       # 32 KB a voice (8192 words), 16 voices: 512 KB
BIG_WORDS = BIG_STRIDE // 4
# 2026-11-09 (the User: PLAITS silent sequenced with voice rotation, CPU; Optimist's
# perf(notestart)): an engine whose init would clear thousands of DDR words (PART 8,192, STRG
# 3,984) defers it: its init sets S_CLR to the words to clear (a multiple of CLR_CHUNK), and
# each half then clears CLR_CHUNK of them, from the top down, and renders silence (the trigger
# kept) until none are left; then the engine's `init_tail`, if it has one, and its halves. A
# voice's start block costs an engine half, not 8,192 DDR stores. S_CLR is GRAIN's first state
# word (free since GRAIN went); dnfw.mnm.plaits clears it at init and on a change of engine.
S_CLR = 7
# 2026-11-11 (plaits16): PART's age, the samples rendered since its init while its diffuser still reads words no
# write has reached (plaits_part._jit); GRAIN's second state word, free since GRAIN went
S_AGE = 8
# 2026-11-11 (declared, not bit-exact in time): CLEAR_SPREAD halves the chunk, so the note start's
# silent clear takes twice the halves (PART 8 -> 16 halves = 4 -> 8 blocks, STRG 4 -> 8 halves) and a
# block costs ~half as much: sixteen voices started at once no longer exceed the frame guard's limit in
# their start blocks (poly16 step). A note sounds PART 4 blocks / STRG 2 blocks (a block is 32 samples:
# 0.73 ms at 44.1 kHz, so 2.9 / 1.5 ms) later; after that the output is the same sample for sample.
# 2026-11-11 (plaits16; declared, not bit-exact in time): PART no longer defers (plaits_part._jit), so the
# chunk is STRG's alone: 800 words a half, its 3,984 in 5 halves (2.5 blocks; it renders from the sixth half,
# 512's ninth), a clear half's ~8.1k (10 cycles a word on the runner's clock) plus a voice's ~1.9k still under a
# sounding half's ~9.6k, so sixteen voices started at once fit the frame guard while they clear (poly16 step).
CLEAR_SPREAD = True
CLR_CHUNK = 800 if CLEAR_SPREAD else 1024      # words a half (a multiple of 8)


def defer_clear(p: Prog, words: int) -> None:
    """an engine's init: clear WORDS of this voice's DDR words over the next halves (rounded up
    to CLR_CHUNK). Clobbers R0."""
    n = -(-words // CLR_CHUNK) * CLR_CHUNK
    assert 0 < n <= BIG_WORDS
    p.iconst(0, n)
    sv(p, S_CLR, 0)


def clear_half(p: Prog, L: C.Layout, out: int) -> None:
    """one half while S_CLR > 0: CLR_CHUNK of the voice's DDR words cleared (the top ones left),
    S_CLR less CLR_CHUNK; HALF zeros stored at I4 (OUT: a free register). Clobbers R0-R3, R8,
    R12, I1."""
    ld(p, 1, S_CLR)
    p.iconst(12, -CLR_CHUNK)
    p.iop(1, 12, "+", 1)
    sv(p, S_CLR, 1)                            # the words left after this half: the first to clear
    big_at(p, L, 0)
    p.lsh(8, 1, 2)
    p.iop(0, 8, "+", 0)
    p.seti(1, 0)
    p.iconst(2, 0)
    p.loop_r(3, CLR_CHUNK // 8, lambda: [p.stpost(1, 2) for _ in range(8)])   # 2026-11-10: 8 a pass
    p.iconst(out, 0)
    for _ in range(HALF):
        p.stpost(4, out)
ACCENT = 0.8                                   # Plaits' accent with LEVEL unpatched (voice.cc)


def _pm():
    from ..perc import machines as PM
    return PM


# -- slot words ----------------------------------------------------------------------------------
def ld(p: Prog, d: int, k: int) -> None:
    """Rd = state word k (0..95)."""
    C.st(p, d, k)


def sv(p: Prog, k: int, s: int) -> None:
    """state word k = Rs."""
    C.sts(p, k, s)


def zero_state(p: Prog, k0: int, n: int) -> None:
    """state words k0 .. k0 + n - 1 = 0 by a loop (2026-11-12, plaits-opt: an engine's init, where n stores in a
    row cost PERC's code room and nothing in time matters). Leaves R0 = 0; clobbers R8, R12, I1."""
    p.iconst(8, p.ioff(3, 4 * (K.S0 + k0)))
    p.geti(12, 3)
    p.iop(8, 12, "+", 8)
    p.seti(1, 8)
    p.iconst(0, 0)
    p.loop_r(12, n, lambda: p.stpost(1, 0))


def big_at(p: Prog, L: C.Layout, d: int) -> None:
    """Rd = this voice's DDR words. Clobbers R12."""
    p.ld(d, L.md.C["mdb"])
    p.iconst(12, -L.md.state)
    p.iop(d, 12, "+", d)                       # slot x 1 KB
    p.lsh(d, d, 5)                             # x 32 KB
    p.iconst(12, BIG_DDR)
    p.iop(d, 12, "+", d)


def par(p: Prog, d: int, k: int) -> None:
    """Fd = parameter k as 0..1 (knob / 127), as Plaits' 0..1 knob. Clobbers R12."""
    C.par(p, d, k)
    mulk(p, d, d, 128.0 / 127.0)


# -- float arithmetic ----------------------------------------------------------------------------
def mulk(p: Prog, d: int, a: int, x: float, t: int = 12) -> None:
    p.fconst(t, x)
    p.fop(d, a, "*", t)


def addk(p: Prog, d: int, a: int, x: float, t: int = 12) -> None:
    p.fconst(t, x)
    p.fop(d, a, "+", t)


def clamp(p: Prog, x: int, lo: float, hi: float) -> None:
    """CONSTRAIN(x, lo, hi). Clobbers R12."""
    p.fconst(12, lo)
    p.fop(x, x, "MAX", 12)
    p.fconst(12, hi)
    p.fop(x, x, "MIN", 12)


def fabs(p: Prog, d: int, x: int) -> None:
    """Fd = |Fx|. Clobbers R12."""
    p.fconst(12, 0.0)
    p.fop(12, 12, "-", x)
    p.fop(d, x, "MAX", 12)


def recip(p: Prog, d: int, x: int) -> None:
    """Fd = 1 / Fx (Fx > 0; PERC's three Newton steps). Clobbers R12-R15, I12."""
    _pm().recip(p, d, x)


def div(p: Prog, d: int, a: int, b: int) -> None:
    """Fd = Fa / Fb (Fb > 0), as Fa x recip(Fb). d is not a. Clobbers R12-R15, I12."""
    recip(p, d, b)
    p.fop(d, a, "*", d)


def ifrac(p: Prog, i: int, f: int, x: int) -> None:
    """Ri = (int) Fx (towards zero, C's cast), Ff = Fx - Ri. Clobbers R12."""
    p.trunc(i, x)
    p.iconst(12, 0)
    p.float_(f, i, 12)
    p.fop(f, x, "-", f)


def floor_frac(p: Prog, i: int, f: int, x: int) -> None:
    """Ri = floor(Fx), Ff = Fx - Ri (0..1). Clobbers R12."""
    p.trunc(i, x)
    p.iconst(12, 0)
    p.float_(f, i, 12)

    def neg():
        p.fconst(12, 1.0)
        p.fop(f, f, "-", 12)
        p.iconst(12, -1)
        p.iop(i, 12, "+", i)
    p.if_(x, "LT", f, neg)
    p.fop(f, x, "-", f)


def interp_next(p: Prog, d: int, s: int, inc: int) -> None:
    """Fd = state word S += word INC (ParameterInterpolator::Next). Clobbers R11."""
    ld(p, d, s)
    ld(p, 11, inc)
    p.fop(d, d, "+", 11)
    sv(p, s, d)


def interp_start(p: Prog, inc: int, s: int, x: int) -> None:
    """word INC = (Fx - state word S) / HALF (a ParameterInterpolator over the half). Clobbers R11,
    R12."""
    ld(p, 11, s)
    p.fop(11, x, "-", 11)
    mulk(p, 11, 11, 1.0 / HALF)
    sv(p, inc, 11)


# -- exp2, sine ----------------------------------------------------------------------------------
def _poly_exp2() -> tuple[float, ...]:
    """2^f on 0..1, degree 6 (dnfw.mnm.tb303.EXP2_POLY's), Horner's order (highest first)."""
    from .tb303 import EXP2_POLY
    return tuple(EXP2_POLY)


def exp2p(p: Prog, d: int, x: int) -> None:
    """Fd = 2^Fx, precise (|x| < 100). d is not x. Clobbers R0, R1, R12."""
    poly = _poly_exp2()
    floor_frac(p, 0, 1, x)
    p.fconst(d, poly[0])
    for c in poly[1:]:
        p.fop(d, d, "*", 1)
        addk(p, d, d, c)
    p.iconst(12, 127)
    p.iop(0, 12, "+", 0)
    p.lsh(0, 0, 23)                            # R0's bits: 2^floor
    p.fop(d, d, "*", 0)


def semis(p: Prog, d: int, x: int) -> None:
    """Fd = SemitonesToRatio(Fx) = 2^(x / 12), precise. d is not x; Fx kept. Clobbers R0, R1, R12,
    and R2."""
    mulk(p, 2, x, 1.0 / 12.0)
    exp2p(p, d, 2)


def note_freq(p: Prog, d: int, x: int) -> None:
    """Fd = NoteToFrequency(Fx) = A0 x 2^((x - 69) / 12) (a sample's fraction at 44.1 kHz).
    The note clamped to -119..136 (Plaits' -128..127 after its - 9). d is not x. Clobbers R0-R2,
    R12."""
    p.fpass(2, x)
    clamp(p, 2, -119.0, 136.0)
    addk(p, 2, 2, -69.0)
    mulk(p, 2, 2, 1.0 / 12.0)
    exp2p(p, d, 2)
    mulk(p, d, d, A0)


# sin(2 pi r) on |r| <= 1/4 as r (c1 + c3 r^2 + .. + c9 r^8): least squares at 2,000 Chebyshev
# nodes, the coefficients float32 (1.9e-7 off sin, evaluated in float32 as the DSP does)
SIN_POLY = (6.283185005187988, -41.34165573120117, 81.60099792480469, -76.5496597290039,
            39.53581237792969)


def sinp_body(p: Prog) -> None:
    """F15 = sin(2 pi F15), any F15. Clobbers R0, R1, R12-R14.

    2026-11-10 (poly16): without branches, the same values bit for bit: x + 0.5's floor by TRUNC
    and a conditional + 1 (x + 0.5 - its TRUNC is exact, so + 1 and - (TRUNC - 1) round alike);
    the quarter-turn fold as MAX(MIN(r, 0.5 - r), -0.5 - r) (each picked value computed as
    before; the others cannot cross 0.25 by rounding). 28 instructions, not 33..37 and two
    branches."""
    p.fconst(12, 0.5)
    p.fconst(14, 1.0)
    p.fop(13, 15, "+", 12)
    p.trunc(0, 13)
    p.float0(1, 0)
    p.fop(1, 13, "-", 1)
    p.fop_lt(1, 1, "+", 14)                    # x + 0.5 - floor(x + 0.5)
    p.fop(15, 1, "-", 12)                      # r = x - round(x): -1/2 .. 1/2
    p.fconst(1, -0.5)
    p.fop(13, 12, "-", 15)
    p.fop(14, 15, "MIN", 13)
    p.fop(13, 1, "-", 15)
    p.fop(15, 14, "MAX", 13)                   # |r| <= 1/4
    p.fop(13, 15, "*", 15)                     # r^2
    p.fconst(14, SIN_POLY[-1])
    for c in reversed(SIN_POLY[:-1]):
        p.fop(14, 14, "*", 13)
        addk(p, 14, 14, c)
    p.fop(15, 14, "*", 15)


def sinp(p: Prog, d: int, x: int) -> None:
    """Fd = sin(2 pi Fx), any Fx (a subroutine). Clobbers R0, R1, R12-R15, I12."""
    p.fpass(15, x)
    p.call("pl_sinp", lambda: sinp_body(p))
    if d != 15:
        p.fpass(d, 15)


def sinp_inline(p: Prog, d: int, x: int) -> None:
    """sinp's body here, not a call (2026-11-10: a hot loop's; no I12). Clobbers R0, R1, R12-R15."""
    if x != 15:
        p.fpass(15, x)
    sinp_body(p)
    if d != 15:
        p.fpass(d, 15)


def cosp(p: Prog, d: int, x: int) -> None:
    """Fd = cos(2 pi Fx) = sin(2 pi (Fx + 1/4)). Clobbers R0, R1, R12-R15, I12."""
    addk(p, 15, x, 0.25, t=12)
    p.call("pl_sinp", lambda: sinp_body(p))
    if d != 15:
        p.fpass(d, 15)


# -- the random generator ------------------------------------------------------------------------
RNG_SEED = 0x21


def rng(p: Prog, d: int) -> None:
    """Rd = stmlib::Random::GetWord() (this voice's). Clobbers R12-R14."""
    def body():
        ld(p, 13, S_RNG)
        p.iconst(14, 1664525)
        p.mul_ssi(13, 13, 14)
        p.iconst(14, 1013904223)
        p.iop(13, 13, "+", 14)
        sv(p, S_RNG, 13)
    p.call("pl_rng", body)
    if d != 13:
        p.ipass(d, 13)


def rnd01(p: Prog, d: int) -> None:
    """Fd = Random::GetFloat(), 0..1: (word >> 1) x 2^-31. Clobbers R12-R14."""
    rng(p, 13)
    p.lsh(13, 13, -1)
    p.iconst(12, -31)
    p.float_(d, 13, 12)


def rnd01_inline(p: Prog, d: int) -> None:
    """rnd01 with rng's body here, not a call (2026-11-10: a hot loop's; the same operations).
    Clobbers R12-R14."""
    ld(p, 13, S_RNG)
    p.iconst(14, 1664525)
    p.mul_ssi(13, 13, 14)
    p.iconst(14, 1013904223)
    p.iop(13, 13, "+", 14)
    sv(p, S_RNG, 13)
    p.lsh(13, 13, -1)
    p.iconst(12, -31)
    p.float_(d, 13, 12)


def rnd_sample(p: Prog, d: int) -> None:
    """Fd = Random::GetSample() / 32768 (the word's top 16 bits, signed). Clobbers R12-R14."""
    rng(p, 13)
    p.ash(13, 13, -16)
    p.iconst(12, -15)
    p.float_(d, 13, 12)


# -- the reference's side: the same arithmetic in Python (float32 where the DSP is) -------------
def ref_sinp(x: float) -> float:
    """sinp as the DSP computes it, float32 step by step (for the references' 'matched' mode)."""
    from ..perc.dsl import f32
    r = f32(f32(x + 0.5) - math.floor(f32(x + 0.5)))
    r = f32(r - 0.5)
    if r > 0.25:
        r = f32(0.5 - r)
    if r < -0.25:
        r = f32(-0.5 - r)
    r2 = f32(r * r)
    acc = f32(SIN_POLY[-1])
    for c in reversed(SIN_POLY[:-1]):
        acc = f32(f32(acc * r2) + f32(c))
    return f32(acc * r)
