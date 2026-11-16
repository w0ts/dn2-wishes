"""SOPHIE: percussive metal, pipes and kicks, a port of Matt Estela's Schwung Sophie
(github.com/mestela/schwung-sophie, src/dsp/sophie.c, MIT; THIRD-PARTY.md) to a Monomachine-style
machine slot (docs/sophie.md).

One voice per track, at 44.1 kHz as Sophie runs (no oversampling, no decimator): a carrier,
three modulators, a pitch envelope, a metal envelope, an amplitude envelope (its own DCAY,
inside the DN2's amp envelope), operator feedback and per-hit noise; then the crusher and the
soft clip. Sophie's per-pad filter, drive, ring delay, level and its second page (metal decay,
feedback mode, tail mode) are left to the DN2's track (filter, overdrive) or out: this is
Sophie's Raw feedback, Hit tail and its original metal contour (metal decay 0).

Phases are kept in turns (0..1) where Sophie keeps radians; a modulation of r radians is
r / 2 pi turns. Sines are the PERC sine table (256 a turn, linear), exp2 PERC's table, and a
division is PERC's reciprocal (dnfw.perc.machines).

MODL (seven choices): FUSE, STAK, SPLT, SHRD, PIPE, BOOM (Sophie's models 0..5), KICK (Sophie's
pad-1 kick topology with model 0). State: S0.. below; per-half values from the knobs after them.
Parameters: DCAY COLR METL FBK SWEP CRSH TUNE MODL (2026-11-11, the User: the engine on page 1 knob H on every
machine with engines, as MACHINEDRUM's TYPE; MODL and TUNE swapped places, old projects not converted).
"""

from __future__ import annotations

import math

from . import core as C
from ..perc.dsl import Prog

NAME, ID = "SOPHIE", 64
PNAMES = ("DCAY", "COLR", "METL", "FBK", "SWEP", "CRSH", "TUNE", "MODL")
TUNE_K, MODL_K = 6, 7                                                      # their places (G, H)
MODELS = ("FUSE", "STAK", "SPLT", "SHRD", "PIPE", "BOOM", "KICK")
FUSE, STAK, SPLT, SHRD, PIPE, BOOM, KICK = range(7)
# Sophie's factory snare-ish start: decay 0.24 s, color 52, metal 76, feedback 18, sweep 28,
# crush 30 (pad 3), FUSE, in tune
DEFAULTS = (61, 66, 97, 23, 82, 38, 64, 9)   # MODL 9: the middle of FUSE's knobs, where fmt.c's quantiser stores the
                                             # first engine (mnm_rep); 0 was stored as 7 on record 240 (2026-11-11)

SR = 44100.0
TAU = 2.0 * math.pi
DEC_LO, DEC_HI = 0.03, 4.0                       # DCAY's range (s), exponential
AMP_END = 0.00012                                # the amplitude envelope's end
PMUL = math.exp(-1.0 / (0.028 * SR))             # the pitch envelope (the kick's 0.075 s)
PMUL_KICK = math.exp(-1.0 / (0.075 * SR))
MMUL = math.exp(-1.0 / (0.135 * SR))             # the metal envelope (Sophie's 135 ms)
SEED = 0x534F5048

# state (slot words S0..): phases (turns), envelopes, feedback and noise, crusher, on
(S_CAR, S_M1, S_M2, S_M3, S_AMP, S_PEN, S_MEN, S_ATK, S_AMUL, S_FBZ, S_NZ, S_RNG, S_CH, S_CC,
 S_ON, S_BASE) = range(16)
# per half, from the knobs (slot words, after the state)
(D_COL, D_MET, D_FBK, D_M25, D_SWP, D_R1, D_R2, D_R3, D_IX0, D_IX1, D_MOD, D_RDIV, D_LEV,
 D_ILEV, D_PMUL, D_NZK) = range(16, 32)
# per sample scratch (slot words)
(T_B, T_IDX, T_M1, T_M2, T_M3, T_OUT, T_INC, T_CNT) = range(32, 40)


def _pm():
    from ..perc import machines as PM
    return PM


def _ld(p: Prog, d: int, k: int) -> None:
    C.st(p, d, k)


def _sv(p: Prog, k: int, s: int) -> None:
    C.sts(p, k, s)


def _k(p: Prog, d: int, x: float) -> None:
    p.fconst(d, x)


def _mulk(p: Prog, d: int, a: int, x: float, t: int = 12) -> None:
    p.fconst(t, x)
    p.fop(d, a, "*", t)


def _addk(p: Prog, d: int, a: int, x: float, t: int = 12) -> None:
    p.fconst(t, x)
    p.fop(d, a, "+", t)


def _unit(p: Prog, d: int, k: int) -> None:
    """Fd = parameter k as 0..1 (knob / 127)."""
    C.par(p, d, k)
    _mulk(p, d, d, 128.0 / 127.0)


def sinw(p: Prog, L: C.Layout, d: int, x: int) -> None:
    """Fd = sin(2 pi Fx), any Fx. Clobbers R0-R3, R12, R15, I1, I12."""
    _pm().sin_(p, L.perc, d, x, wrap=True)


def frac(p: Prog, x: int) -> None:
    """Fx = x - floor(x). Clobbers R0, R1, R12."""
    _pm().frac(p, x)


def softclip(p: Prog, d: int, x: int) -> None:
    """Fd = x / (1 + |x|). Clobbers R4, R5, R12-R15, I12; d, x not R4/R5/R15."""
    p.fconst(4, 0.0)
    p.fop(4, 4, "-", x)
    p.fop(4, 4, "MAX", x)                        # |x|
    _addk(p, 15, 4, 1.0)                         # (perf, 2026-11-12: in and out through F15, no copies)
    p.fpass(5, x)
    _pm().recip(p, 15, 15)
    p.fop(d, 5, "*", 15)


def noise(p: Prog, d: int) -> None:
    """Fd = the voice's xorshift32 as Sophie's noise_bipolar (24 bits, -1..1).
    Clobbers R0, R1, R12."""
    _ld(p, 0, S_RNG)
    p.lsh(1, 0, 13)
    p.xor(0, 0, 1, 12)
    p.lsh(1, 0, -17)
    p.xor(0, 0, 1, 12)
    p.lsh(1, 0, 5)
    p.xor(0, 0, 1, 12)
    _sv(p, S_RNG, 0)
    p.iconst(12, 0xFFFFFF)
    p.iop(0, 0, "AND", 12)
    p.iconst(12, 0)
    p.float_(d, 0, 12)
    _mulk(p, d, d, 2.0 / 16777215.0)
    _addk(p, d, d, -1.0)


def exact(A: int, F: int, knobs, pre: int = 0) -> dict:
    """no Monomachine increments: SOPHIE takes its pitch from VW pitch (pitch below)"""
    return {}


def init(p: Prog, L: C.Layout) -> None:
    p.iconst(0, 0)
    for k in range(S_BASE + 1):
        _sv(p, k, 0)
    p.iconst(0, SEED)
    _sv(p, S_RNG, 0)


def trig(p: Prog, L: C.Layout) -> None:
    """A hit: the phases restart (two modulators a little apart), the envelopes at full, the
    amplitude envelope's rate from DCAY (Sophie's Hit mode: fixed for the hit)."""
    p.fconst(0, 0.0)
    for k in (S_CAR, S_M1, S_ATK, S_FBZ, S_NZ, S_CH):
        _sv(p, k, 0)
    p.iconst(0, 0)
    _sv(p, S_CC, 0)
    p.fconst(0, 1.0)
    for k in (S_AMP, S_PEN, S_MEN):
        _sv(p, k, 0)
    noise(p, 2)
    _mulk(p, 2, 2, 0.12 / TAU)
    _sv(p, S_M2, 2)
    noise(p, 2)
    _mulk(p, 2, 2, 0.08 / TAU)
    _sv(p, S_M3, 2)
    # decay = 0.03 x 2^(DCAY log2(4 / 0.03)) s; the envelope falls to AMP_END in that time:
    # amul = 2^(log2(AMP_END) / (decay x SR)) = e^y, y = ln(AMP_END) / (decay x SR), small
    _unit(p, 4, 0)
    _mulk(p, 4, 4, math.log2(DEC_HI / DEC_LO))
    _pm().exp2(p, L.perc, 4, 4)
    _mulk(p, 4, 4, DEC_LO * SR)
    _pm().recip(p, 4, 4)
    _mulk(p, 4, 4, math.log(AMP_END))           # y, -0.007..0
    p.fpass(5, 4)
    _mulk(p, 6, 4, 1.0 / 6.0)
    _addk(p, 6, 6, 0.5)
    p.fop(6, 6, "*", 5)
    _addk(p, 6, 6, 1.0)
    p.fop(6, 6, "*", 5)
    _addk(p, 6, 6, 1.0)                          # 1 + y + y^2/2 + y^3/6
    _sv(p, S_AMUL, 6)
    p.iconst(0, 1)
    _sv(p, S_ON, 0)


def pitch(p: Prog, L: C.Layout) -> None:
    """S_BASE = the note's frequency in turns a sample: 440 x 2^((note - 69 + TUNE) / 12),
    TUNE -24..+24 semitones (64 in tune), 20..10000 Hz as Sophie."""
    C.vw(p, 1, "pitch")
    C.par(p, 2, TUNE_K)
    _mulk(p, 2, 2, 48.0)
    _addk(p, 2, 2, -24.0)                        # TUNE: knob x 48 / 128 - 24
    p.fop(1, 1, "+", 2)
    _addk(p, 1, 1, -69.0)
    _mulk(p, 1, 1, 1.0 / 12.0)
    _pm().exp2(p, L.perc, 1, 1)
    _mulk(p, 1, 1, 440.0)
    _k(p, 12, 20.0)
    p.fop(1, 1, "MAX", 12)
    _k(p, 12, 10000.0)
    p.fop(1, 1, "MIN", 12)
    _mulk(p, 1, 1, 1.0 / SR)
    _sv(p, S_BASE, 1)


def _params(p: Prog, L: C.Layout) -> None:
    """The per-half values from the knobs (Sophie's Live tail without its slew)."""
    PM = _pm()
    _unit(p, 4, 1)                               # color
    _sv(p, D_COL, 4)
    _unit(p, 5, 2)                               # metal
    _sv(p, D_MET, 5)
    _unit(p, 6, 3)                               # feedback
    _mulk(p, 7, 5, 10.0)
    _addk(p, 7, 7, 2.0)
    p.fop(6, 6, "*", 7)
    _mulk(p, 6, 6, 1.0 / TAU)                    # feedback x (2 + 10 metal), in turns
    _sv(p, D_FBK, 6)
    _mulk(p, 6, 5, 2.5 / TAU)                    # m1's depth into m2 (turns)
    _sv(p, D_M25, 6)
    p.fop(6, 5, "*", 5)                          # metal^2: index = metal^2 (8 + 18 b) rad
    _mulk(p, 7, 6, 8.0 / TAU)
    _sv(p, D_IX0, 7)
    _mulk(p, 7, 6, 18.0 / TAU)
    _sv(p, D_IX1, 7)
    # MODL: the choice (knob x 7) >> 7, as the page's (fmt.c mnm_ch)
    C.knob(p, 0, MODL_K)
    p.lsh(1, 0, 3)
    p.iop(0, 1, "-", 0)                          # knob x 7
    p.lsh(0, 0, -7)
    _sv(p, D_MOD, 0)
    # the sweep's range and the pitch envelope by topology (the kick's own)
    C.par(p, 7, 4)
    _mulk(p, 7, 7, 2.0)
    _addk(p, 7, 7, -1.0)                         # SWEP: -1..1
    p.iconst(1, KICK)

    def kick():
        _mulk(p, 8, 7, 2.5)
        p.fconst(9, PMUL_KICK)

    def other():
        _mulk(p, 8, 7, 4.5)
        p.fconst(9, PMUL)
    p.if_(0, "EQ", 1, kick, other, kind="i")
    _sv(p, D_SWP, 8)
    _sv(p, D_PMUL, 9)
    # the ratios (deliberately non-integer: COLR moves through the clang zones)
    p.fop(8, 4, "*", 4)
    _mulk(p, 8, 8, 7.6)
    _addk(p, 8, 8, 0.47)                         # r1
    p.iconst(1, PIPE)
    p.if_(0, "EQ", 1, lambda: (_mulk(p, 8, 4, 6.0), _addk(p, 8, 8, 1.31)), kind="i")
    p.iconst(1, BOOM)
    p.if_(0, "EQ", 1, lambda: (_mulk(p, 8, 4, 4.2), _addk(p, 8, 8, 0.60)), kind="i")
    _sv(p, D_R1, 8)
    _mulk(p, 8, 4, 11.17)
    _addk(p, 8, 8, 1.31)
    _sv(p, D_R2, 8)
    p.fconst(8, 1.0)
    p.fop(8, 8, "-", 4)
    _mulk(p, 8, 8, 15.73)
    _addk(p, 8, 8, 2.07)
    _sv(p, D_R3, 8)
    # SHRD's noise smoothing (0.02 + 0.35 color), the kick's 0.32
    _mulk(p, 8, 4, 0.35)
    _addk(p, 8, 8, 0.02)
    p.iconst(1, KICK)
    p.if_(0, "EQ", 1, lambda: p.fconst(8, 0.32), kind="i")
    _sv(p, D_NZK, 8)
    # CRSH: off below 0.005; else hold every 1 + crush^2 x 31 samples, 15 - 12 crush bits
    _unit(p, 4, 5)
    p.iconst(0, 0)
    _sv(p, D_RDIV, 0)
    _k(p, 12, 0.005)

    def crush():
        p.fop(5, 4, "*", 4)
        _mulk(p, 5, 5, 31.0)
        p.trunc(5, 5)
        p.iconst(12, 1)
        p.iop(5, 12, "+", 5)
        _sv(p, D_RDIV, 5)
        p.fpass(6, 4)
        _mulk(p, 4, 4, -12.0)
        _addk(p, 4, 4, 15.0)
        PM.exp2(p, L.perc, 4, 4)
        _sv(p, D_LEV, 4)
        _mulk(p, 6, 6, 12.0)
        _addk(p, 6, 6, -15.0)
        PM.exp2(p, L.perc, 6, 6)
        _sv(p, D_ILEV, 6)
    p.if_(4, "GE", 12, crush)


def _envelopes(p: Prog) -> None:
    """amp, pitch and metal envelopes, the attack ramp; S_ON 0 once the amp is done."""
    _ld(p, 4, S_AMP)
    _ld(p, 5, S_AMUL)
    p.fop(4, 4, "*", 5)
    _sv(p, S_AMP, 4)
    _ld(p, 5, S_PEN)
    _ld(p, 6, D_PMUL)
    p.fop(5, 5, "*", 6)
    _sv(p, S_PEN, 5)
    _ld(p, 6, S_MEN)
    _mulk(p, 6, 6, MMUL)
    _k(p, 12, 0.000001)
    p.if_(6, "LT", 12, lambda: p.fconst(6, 0.0))
    _sv(p, S_MEN, 6)
    _ld(p, 7, S_ATK)
    p.fconst(8, 1.0)
    p.fop(8, 8, "-", 7)
    _mulk(p, 8, 8, 0.085)
    p.fop(7, 7, "+", 8)
    _sv(p, S_ATK, 7)
    _k(p, 12, AMP_END)
    p.if_(4, "LT", 12, lambda: (p.iconst(0, 0), _sv(p, S_ON, 0)))


def _advance(p: Prog, L: C.Layout) -> None:
    """The swept frequency, then the four phases (turns, wrapped)."""
    _ld(p, 4, D_SWP)
    _ld(p, 5, S_PEN)
    p.fop(15, 4, "*", 5)
    _pm().exp2(p, L.perc, 15, 15)
    _ld(p, 5, S_BASE)
    p.fop(4, 15, "*", 5)
    _k(p, 12, 18.0 / SR)
    p.fop(4, 4, "MAX", 12)
    _k(p, 12, 18000.0 / SR)
    p.fop(4, 4, "MIN", 12)
    _sv(p, T_INC, 4)
    for ph, r in ((S_CAR, None), (S_M1, D_R1), (S_M2, D_R2), (S_M3, D_R3)):
        if r is None:
            p.fpass(6, 4)
        else:
            _ld(p, 6, r)
            p.fop(6, 6, "*", 4)
        _ld(p, 7, ph)
        p.fop(7, 7, "+", 6)
        frac(p, 7)
        _sv(p, ph, 7)


def _mods(p: Prog, L: C.Layout) -> None:
    """m1 (with the operator feedback), m2 (m1 into it), m3; b and the index."""
    _ld(p, 4, S_FBZ)
    _ld(p, 5, D_FBK)
    p.fop(4, 4, "*", 5)
    _ld(p, 5, S_M1)
    p.fop(15, 4, "+", 5)                         # (perf, 2026-11-12: the sines in and out through F15)
    sinw(p, L, 15, 15)
    _sv(p, T_M1, 15)
    _ld(p, 5, D_M25)
    p.fop(4, 15, "*", 5)
    _ld(p, 5, S_M2)
    p.fop(15, 4, "+", 5)
    sinw(p, L, 15, 15)
    _sv(p, T_M2, 15)
    def m3():
        _ld(p, 15, S_M3)
        sinw(p, L, 15, 15)
        _sv(p, T_M3, 15)
    # (perf, 2026-11-12) m3 is read by STAK and SPLT alone (this sample's T_M3): the others skip its sine (S_M3 still
    # moves on in _advance, so a model changed mid-note finds the same phase)
    _ld(p, 0, D_MOD)
    p.iconst(1, STAK)
    p.if_(0, "EQ", 1, m3, lambda: (p.iconst(1, SPLT), p.if_(0, "EQ", 1, m3, kind="i")), kind="i")
    # b: the metal envelope for PIPE and BOOM (Sophie's shaped models), else the pitch one
    _ld(p, 4, S_PEN)
    _ld(p, 0, D_MOD)
    p.iconst(1, PIPE)
    p.if_(0, "GE", 1, lambda: _ld(p, 4, S_MEN), kind="i")
    p.iconst(1, KICK)
    p.if_(0, "EQ", 1, lambda: _ld(p, 4, S_PEN), kind="i")
    _sv(p, T_B, 4)
    _ld(p, 5, D_IX1)
    p.fop(5, 5, "*", 4)
    _ld(p, 6, D_IX0)
    p.fop(5, 5, "+", 6)
    _sv(p, T_IDX, 5)


def _op(p: Prog, L: C.Layout, d: int, car_mul: float, idx_mul: float, m: int | None) -> None:
    """Fd = sin(car x CAR_MUL + index x IDX_MUL x m) (turns). Clobbers R0-R3, R6, R7, R12,
    R15, I1, I12."""
    if m is None and car_mul == 1.0:             # (perf, 2026-11-12: the argument made in F15, no copy in)
        _ld(p, 15, S_CAR)
    else:
        _ld(p, 6, S_CAR)
        if car_mul != 1.0:
            _mulk(p, 6 if m is not None else 15, 6, car_mul)
    if m is not None:
        _ld(p, 7, T_IDX)
        if idx_mul != 1.0:
            _mulk(p, 7, 7, idx_mul)
        _ld(p, 0, m)
        p.fop(7, 7, "*", 0)
        p.fop(15, 6, "+", 7)
    sinw(p, L, d, 15)


def _fuse(p: Prog, L: C.Layout) -> None:
    _ld(p, 8, T_M2)
    _mulk(p, 8, 8, 0.72)
    _ld(p, 9, T_M1)
    _mulk(p, 9, 9, 0.28)
    p.fop(8, 8, "+", 9)
    _ld(p, 9, T_IDX)
    p.fop(8, 8, "*", 9)
    _ld(p, 9, S_CAR)
    p.fop(15, 8, "+", 9)
    sinw(p, L, 15, 15)
    _sv(p, T_OUT, 15)


def _stak(p: Prog, L: C.Layout) -> None:
    _op(p, L, 8, 1.0, 0.62, T_M1)
    _op(p, L, 9, 0.501, 0.35, T_M2)
    _mulk(p, 9, 9, 0.55)
    p.fop(8, 8, "+", 9)
    _op(p, L, 9, 1.997, 0.22, T_M3)
    _mulk(p, 9, 9, 0.32)
    p.fop(8, 8, "+", 9)
    _mulk(p, 8, 8, 0.56)
    _sv(p, T_OUT, 8)


def _splt(p: Prog, L: C.Layout) -> None:
    _op(p, L, 8, 1.0, 1.0, T_M1)
    _mulk(p, 8, 8, 0.62)
    _op(p, L, 9, 1.003, -0.71, T_M2)
    _mulk(p, 9, 9, 0.38)
    p.fop(8, 8, "+", 9)
    _ld(p, 9, T_M3)
    _mulk(p, 9, 9, 0.18)
    p.fop(8, 8, "+", 9)
    _sv(p, T_OUT, 8)


def _noise_z(p: Prog, d: int) -> None:
    """Fd = the smoothed noise: nz += (noise - nz) x D_NZK. Clobbers R0, R1, R6, R12."""
    noise(p, 6)
    _ld(p, d, S_NZ)
    p.fop(6, 6, "-", d)
    _ld(p, 0, D_NZK)
    p.fop(6, 6, "*", 0)
    p.fop(d, d, "+", 6)
    _sv(p, S_NZ, d)


def _shrd(p: Prog, L: C.Layout) -> None:
    _ld(p, 6, S_CAR)
    _mulk(p, 6, 6, 32.0)
    p.trunc(6, 6)                                # car >= 0: floor
    p.iconst(12, 0)
    p.float_(6, 6, 12)
    _mulk(p, 6, 6, 1.0 / 32.0)                   # the 32-step stair
    _ld(p, 7, T_IDX)
    _mulk(p, 7, 7, 0.55)
    _ld(p, 0, T_M1)
    p.fop(7, 7, "*", 0)
    p.fop(15, 6, "+", 7)
    sinw(p, L, 8, 15)
    _ld(p, 9, D_MET)
    _mulk(p, 10, 9, -0.25)
    _addk(p, 10, 10, 0.85)
    p.fop(8, 8, "*", 10)
    _noise_z(p, 10)
    p.fop(10, 10, "*", 9)
    _mulk(p, 10, 10, 0.42)
    p.fop(8, 8, "+", 10)
    _sv(p, T_OUT, 8)


def _pipe(p: Prog, L: C.Layout) -> None:
    _op(p, L, 8, 1.0, 1.0, T_M1)                 # body
    _ld(p, 9, D_MET)
    _mulk(p, 9, 9, 0.5)
    _ld(p, 10, T_B)
    _mulk(p, 10, 10, 0.125)
    p.fop(9, 9, "+", 10)
    _addk(p, 9, 9, 0.3125)                       # the ring mix
    _ld(p, 10, T_M1)
    _addk(p, 10, 10, -1.0)
    p.fop(10, 10, "*", 9)
    _addk(p, 10, 10, 1.0)                        # (1 - mix) + m1 mix
    p.fop(8, 8, "*", 10)
    _mulk(p, 8, 8, 1.25)
    _sv(p, T_OUT, 8)


def _boom(p: Prog, L: C.Layout) -> None:
    _op(p, L, 8, 1.0, 1.0, None)                 # body
    _op(p, L, 9, 1.0, 1.0, T_M1)                 # edge
    _ld(p, 10, D_MET)
    _ld(p, 11, T_B)
    p.fop(10, 10, "*", 11)
    _mulk(p, 10, 10, 0.5)
    _addk(p, 10, 10, 0.0625)                     # the edge's mix
    p.fop(9, 9, "-", 8)
    p.fop(9, 9, "*", 10)
    p.fop(8, 8, "+", 9)
    _sv(p, T_OUT, 8)


def _kick(p: Prog, L: C.Layout) -> None:
    """Sophie's pad-1 kick: a tuned sine body, its fold, a quiet FM texture and a click."""
    _op(p, L, 8, 1.0, 1.0, None)                 # body
    _ld(p, 10, D_COL)
    _mulk(p, 9, 10, 2.2)
    _addk(p, 9, 9, 1.0)
    p.fop(9, 9, "*", 8)
    _mulk(p, 15, 9, 1.0 / TAU)
    sinw(p, L, 9, 15)                            # folded = sin(body (1 + 2.2 color))
    _ld(p, 10, D_COL)
    _mulk(p, 11, 10, -0.08)
    _addk(p, 11, 11, 0.86)
    p.fop(8, 8, "*", 11)
    _mulk(p, 11, 10, 0.08)
    _addk(p, 11, 11, 0.14)
    p.fop(9, 9, "*", 11)
    p.fop(8, 8, "+", 9)
    _sv(p, T_OUT, 8)
    # texture = sin(car + m2 (0.18 + 1.35 feedback)) x metal x 0.18
    _unit(p, 9, 3)
    _mulk(p, 9, 9, 1.35 / TAU)
    _addk(p, 9, 9, 0.18 / TAU)
    _ld(p, 0, T_M2)
    p.fop(9, 9, "*", 0)
    _ld(p, 6, S_CAR)
    p.fop(15, 9, "+", 6)
    sinw(p, L, 9, 15)
    _ld(p, 10, D_MET)
    p.fop(9, 9, "*", 10)
    _mulk(p, 9, 9, 0.18)
    _ld(p, 8, T_OUT)
    p.fop(8, 8, "+", 9)
    # click = nz x pitch env x (0.012 + 0.035 metal)
    _noise_z(p, 9)
    _ld(p, 0, S_PEN)
    p.fop(9, 9, "*", 0)
    _ld(p, 10, D_MET)
    _mulk(p, 10, 10, 0.035)
    _addk(p, 10, 10, 0.012)
    p.fop(9, 9, "*", 10)
    p.fop(8, 8, "+", 9)
    _sv(p, T_OUT, 8)


BODIES = ((FUSE, _fuse), (STAK, _stak), (SPLT, _splt), (SHRD, _shrd), (PIPE, _pipe),
          (BOOM, _boom), (KICK, _kick))


def _model(p: Prog, L: C.Layout) -> None:
    """T_OUT = the model's output (D_MOD), a chain of tests."""
    if MODEL_TREE:
        _ld(p, 0, D_MOD)
        _tree(p, L, list(BODIES))
        return

    def chain(k: int) -> None:
        mod, body = BODIES[k]
        if k == len(BODIES) - 1:
            body(p, L)
            return
        _ld(p, 0, D_MOD)
        p.iconst(1, mod)
        p.if_(0, "EQ", 1, lambda: body(p, L), lambda: chain(k + 1), kind="i")
    chain(0)


MODEL_TREE = True                                # (perf, 2026-11-12) _tree; False = the chain of tests


def _tree(p: Prog, L: C.Layout, arms) -> None:
    """the body of the model in R0 (D_MOD) among ARMS (model, body) sorted by model: halves by a test on the
    middle, at most three tests for seven (the chain made KICK, the last, pass six); a model outside them plays
    the last arm, as the chain does. The bodies leave R0 alone until they start, so R0 is loaded once."""
    if len(arms) == 1:
        arms[0][1](p, L)
        return
    mid = len(arms) // 2
    p.iconst(1, arms[mid][0])
    p.if_(0, "LT", 1, lambda: _tree(p, L, arms[:mid]), lambda: _tree(p, L, arms[mid:]), kind="i")


def _crush(p: Prog) -> None:
    """F8 = the crushed F8: held every D_RDIV samples, rounded to D_LEV levels."""
    _ld(p, 0, S_CC)
    _ld(p, 1, D_RDIV)
    p.ifz(0, "LE", lambda: (_sv(p, S_CH, 8), _sv(p, S_CC, 1)))
    _ld(p, 8, S_CH)
    _ld(p, 0, S_CC)
    p.iconst(12, -1)
    p.iop(0, 12, "+", 0)
    _sv(p, S_CC, 0)
    _ld(p, 9, D_LEV)
    p.fop(8, 8, "*", 9)
    _addk(p, 8, 8, 0.5)
    p.fpass(9, 8)
    frac(p, 9)
    p.fop(8, 8, "-", 9)                          # floor(x lev + 0.5)
    _ld(p, 9, D_ILEV)
    p.fop(8, 8, "*", 9)


def _sample(p: Prog, L: C.Layout) -> None:
    """One sample at I4 (Sophie's render_voice, as the docstring at the top cuts it)."""
    _envelopes(p)

    def silent():
        p.fconst(8, 0.0)
        p.stpost(4, 8)

    def sound():
        _advance(p, L)
        _mods(p, L)
        _model(p, L)
        _ld(p, 8, T_OUT)
        _mulk(p, 9, 8, 1.4)
        softclip(p, 9, 9)
        _sv(p, S_FBZ, 9)                         # the operator feedback (Raw)
        _ld(p, 8, T_OUT)
        _ld(p, 9, S_AMP)
        p.fop(8, 8, "*", 9)
        _ld(p, 9, S_ATK)
        p.fop(8, 8, "*", 9)
        _ld(p, 0, D_RDIV)
        p.ifz(0, "GT", lambda: _crush(p))
        softclip(p, 8, 8)                        # Sophie's drive stage at 0, halved
        p.stpost(4, 8)
    _ld(p, 0, S_ON)
    p.ifz(0, "EQ", silent, sound)


def half(p: Prog, L: C.Layout) -> None:
    """16 samples at I4."""
    _params(p, L)
    _ld(p, 0, S_ON)

    def zeros():
        p.fconst(8, 0.0)
        for _ in range(16):
            p.stpost(4, 8)

    def run():
        p.loop(L.W["n4"], 16, lambda: _sample(p, L))
    p.ifz(0, "EQ", zeros, run)
