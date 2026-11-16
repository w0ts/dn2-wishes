"""TB303: an acid bass voice, a port of the Open303 engine (Robin Schmidt, MIT) as Schwung 303
configures it (github.com/charlesvestal/schwung-303, GPL-3.0-only: src/dsp/open303/,
plugin.cpp with its Devilfish modifications off, no drive stage; THIRD-PARTY.md), as a
Monomachine-style machine (docs/tb303.md).

One voice per track at 44.1 kHz (PERC's stream), Open303's own rate. Per sample: the pitch's slew
(12 ms), the filter envelope (a decay, two RC smoothers, the accent's), the cutoff, the amp
envelope and its de-clicker; then four oversampled samples (176.4 kHz): the oscillator, a
44.5 Hz high-pass, the TB-303 ladder (with its 150 Hz feedback high-pass) and the 12th-order
elliptic decimation filter; then an all-pass, a high-pass and a sub-sonic notch.

Against Open303:
- The oscillator: Open303 reads band-limited mip-mapped wavetables (2 x 12 x 2048 doubles, built by
  FFT, 394 KB). Here the same two shapes are computed: the saw's two ramps with a poly-BLEP at
  its step (between table points 1023 and 1024), the square as Open303 makes it,
  -tanh(K saw + 4.37) half a cycle on, with a poly-BLEP at its jump; the band-limited levels'
  DC (from 43 Hz on) is taken off as the FFT takes it off. Against the tables: 63..86 dB.
- The elliptic filter as six second-order sections (the same transfer function): its direct
  form, Open303's, does not survive float32 (its poles leave the unit circle).
- A trig is a note on after a note off (the envelopes start again), unless SLID: then the note
  slides (the envelopes go on, the pitch glides). No note off: the DN2's amp envelope gates the
  track; Open303's amp envelope decays (1.23 s) as it does while a note is held.
- ACC: 0 a plain note, above an accented one, the knob its accent (Open303's ACCENT knob and the
  step's accent in one, so a p-lock accents a step). SLID likewise: 0 a trig, above a slide over
  the knob's time (2..360 ms, the Devilfish range). TUNE in semitones (A4 440 Hz); the volume
  -6 dB (Schwung's -12 dB x 2: a plain saw peaks near 0.56, full accent near 2.1).
- exp, exp2, tanh: PERC's exp2 table (and for exp(y) with y small, its cubic series).

Parameters: CUT RES ENV DEC ACC SLID WAVE TUNE.
"""

from __future__ import annotations

import math

from . import core as C
from ..perc.dsl import Prog

NAME, ID = "TB303", 66
PNAMES = ("CUT", "RES", "ENV", "DEC", "ACC", "SLID", "WAVE", "TUNE")
DEFAULTS = (64, 64, 64, 64, 0, 0, 0, 64)

SR = 44100.0
OS = 4
OSR = SR * OS                                    # 176.4 kHz
K_SQ = 69.9841996002273                          # dB2amp(36.9): the square's tanh drive
OFF_SQ = 4.37
EDGE = 1023.5 / 2048.0                           # the saw's step (table points 1023 | 1024)
DC_SAW, DC_SQ = -0.000244140625, -0.06195438585180707   # the prototypes' DC (gone from 43 Hz on)
DC_FROM = 0.5 / 2048.0                           # increment from which the mip level is >= 1
# fixed coefficients (Open303's, at their rates; see dn2mk2-scratch/plaits303/ref303)
HP1 = (0.9992083547409913, -0.9992083547409913, 0.9984167094819826)     # 44.486 Hz @ 176.4k
FBHP = (0.9973357014799811, -0.9973357014799811, 0.994671402959962)     # 150 Hz @ 176.4k
AP = (-0.9980061871566851, 1.0, 0.9980061871566851)                     # 14.008 Hz all-pass
HP2 = (0.9982813535100947, -0.9982813535100947, 0.9965627070201895)     # 24.167 Hz
NOTCH = (0.9973820302482191, -1.994762916660274, 0.9973820302482191, 1.994762916660274,
         -0.9947640604964383)                                           # 7.5164 Hz, 4.7 oct
DECLICK = (0.00019897140604503043, 0.00039794281209006087, 0.00019897140604503043,
           1.9597070338155824, -0.9605029194397625)                     # 200 Hz, Q 0.707
RC1, RC2 = 0.9924699152338644, 0.99848942626933                         # 3 ms, 15 ms
SLEW = 0.9981121395078009                                               # 12 ms (60 ms slide)
AMP_MUL = 1.0 - 1.8435388571380606e-05                                  # 1230 ms amp decay
ACC_DECAY = 200.0                                                       # ms, an accent's
LEVEL = 10.0 ** (-6.0 / 20.0)                    # the volume: -6 dB (Schwung's -12 dB x 2; full accent peaks
                                                 # near 2.1, at 0 dB it reached 4.15)
# the elliptic decimation filter, six sections (b0, b1, b2, a1, a2), y = b0 x + s0 ...
ELLIP_GAIN = 0.9999999986182568
ELLIP = (
    (0.09387200280355566, -0.1312353800952545, 0.09387200280332678, -1.5863116558748012, 0.6428202813864291),
    (0.2418088256503009, -0.3295562860588109, 0.241808825651273, -1.5620957226926269, 0.7161570879353899),
    (0.3850909781305105, -0.48815687914010736, 0.3850909781297761, -1.5310700890181974, 0.8130951661383766),
    (0.3969015240682565, -0.40873882687776086, 0.3969015240683953, -1.5080939966772393, 0.8931582179361303),
    (0.2758217161489087, -0.10244116374782673, 0.2758217161489047, -1.4983265489464017, 0.9475288174963884),
    (0.14286990027143076, 0.19537248746316077, 0.1428699002714311, -1.5032624520096824, 0.9843747400157051),
)
# envModScaler / Offset (Open303's measured mapping)
C0, C1 = 3.138152786059267e+002, 2.394411986817546e+003
OF, OC = 0.048292930943553, 0.294391201442418
SLOF, SLOC, SHIF, SHIC = 3.773996325111173, 0.736965594166206, 4.194548788411135, 0.864344900642434

# state (slot words S0..)
(S_IDLE, S_PH, S_FRQ, S_TGT, S_SLC, S_MENV, S_MC, S_RC1, S_RC2, S_ACC, S_AENV,
 S_DX1, S_DX2, S_DY1, S_DY2, S_H1X, S_H1Y, S_Y1, S_Y2, S_Y3, S_Y4, S_FX1, S_FY1,
 S_APX, S_APY, S_H2X, S_H2Y, S_NX1, S_NX2, S_NY1, S_NY2, S_BASE) = range(32)
S_E = 32                                         # the elliptic sections' 12 words (s0, s1 each)
S_END = S_E + 12
# per half (slot words)
(D_CUT, D_ESC, D_EOF, D_RES, D_BL) = range(S_END, S_END + 5)
# per sample (slot words)
(T_INC, T_RINC, T_B0, T_K, T_G, T_AMP, T_X, T_OSN, T_INCI) = range(S_END + 5, S_END + 14)
# (perf, 2026-11-11) the oversampled samples' ladder outputs, the elliptic decimator's four inputs
T_Y0 = S_END + 14


def _pm():
    from ..perc import machines as PM
    return PM


# perf, 2026-11-11: while a half runs, I0 = the slot's state word 32 (I3 + 4 (S0 + 32)): the machine's state
# words 0..63 are then DM(k - 32, I0), an offset a compute's move can carry (-32..31), where DM(S0 + k, I3) (64..)
# cannot. I0 is not used elsewhere in the voice (PERC saves it). Only the emit-time flag below decides.
_I0 = [False]
S_MID = 32


def _ld(p: Prog, d: int, k: int) -> None:
    if _I0[0]:
        assert -32 <= k - S_MID < 32
        p.ldi(d, k - S_MID, 0)
    else:
        C.st(p, d, k)


def _sv(p: Prog, k: int, s: int) -> None:
    if _I0[0]:
        assert -32 <= k - S_MID < 32
        p.sti(k - S_MID, 0, s)
    else:
        C.sts(p, k, s)


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


def _exp2(p: Prog, L: C.Layout, d: int, x: int) -> None:
    _pm().exp2(p, L.perc, d, x)


# 2^f on 0..1, degree 6 (fitted on Chebyshev points; relative error 2.6e-9)
EXP2_POLY = (0.00021877562525891297, 0.0012387871006721122, 0.009684565724072036,
             0.05548044028510092, 0.2402304964795069, 0.6931469295754649, 1.000000002548704)


def _exp2p(p: Prog, d: int, x: int) -> None:
    """Fd = 2^Fx, precise (float32's own): the exponent's bits and the polynomial on the fraction,
    for the pitch and the cutoff (PERC's table, 2.3e-4, made the resonant filter drift from
    Open303). |x| < 100. d is not x. Clobbers R0, R1, R12."""
    p.trunc(0, x)
    p.iconst(12, 0)
    p.float_(1, 0, 12)
    p.if_(x, "LT", 1, lambda: (p.fconst(12, 1.0), p.fop(1, 1, "-", 12), _dec0(p)))
    p.fop(1, x, "-", 1)                          # the fraction, 0..1
    p.fconst(d, EXP2_POLY[0])
    for c in EXP2_POLY[1:]:
        p.fop(d, d, "*", 1)
        _addk(p, d, d, c)
    p.iconst(12, 127)
    p.iop(0, 12, "+", 0)
    p.lsh(0, 0, 23)                              # R0's bits: 2^n
    p.fop(d, d, "*", 0)


def _dec0(p: Prog) -> None:
    """R0 -= 1 (the floor of a negative non-integer). Clobbers R12."""
    p.iconst(12, -1)
    p.iop(0, 12, "+", 0)


def _recip(p: Prog, d: int, x: int) -> None:
    _pm().recip(p, d, x)


def _exp_small(p: Prog, d: int, y: int) -> None:
    """Fd = e^Fy for |y| small (< 0.06): 1 + y + y^2/2 + y^3/6. d is not y; clobbers R12."""
    _mulk(p, d, y, 1.0 / 6.0)
    _addk(p, d, d, 0.5)
    p.fop(d, d, "*", y)
    _addk(p, d, d, 1.0)
    p.fop(d, d, "*", y)
    _addk(p, d, d, 1.0)


def exact(A: int, F: int, knobs, pre: int = 0) -> dict:
    """no Monomachine increments: TB303 takes its pitch from VW pitch (pitch below)"""
    return {}


def init(p: Prog, L: C.Layout) -> None:
    """Every word 0, idle (silent until the first note, as Open303 before its first)."""
    p.iconst(0, 0)
    for k in range(S_END):
        _sv(p, k, 0)
    p.fconst(0, SLEW)
    _sv(p, S_SLC, 0)
    p.iconst(0, 1)
    _sv(p, S_IDLE, 0)


def pitch(p: Prog, L: C.Layout) -> None:
    """S_BASE = the note's frequency, Hz: 440 x 2^((note - 69 + TUNE) / 12), TUNE -24..+24."""
    C.vw(p, 1, "pitch")
    C.par(p, 2, 7)
    _mulk(p, 2, 2, 48.0)
    _addk(p, 2, 2, -24.0)
    p.fop(1, 1, "+", 2)
    _addk(p, 1, 1, -69.0)
    _mulk(p, 3, 1, 1.0 / 12.0)
    _exp2p(p, 2, 3)
    _mulk(p, 1, 2, 440.0)
    _sv(p, S_BASE, 1)


def trig(p: Prog, L: C.Layout) -> None:
    """A note: Open303's triggerNote (the envelopes start; the first ever note also starts the
    oscillator and the filters from rest), or with SLID its slideToNote (only the pitch, gliding
    over SLID's time, and the accent's state). Its frequency is set by `half` (pitch runs
    after this)."""
    # the accent: ACC above 0 accents the note, by ACC
    _unit(p, 4, 4)
    _sv(p, S_ACC, 4)
    # the filter envelope's decay: an accent's 200 ms, else DEC's 200 x 10^n ms; c = e^y,
    # y = -1 / (ms x 44.1)
    _unit(p, 5, 3)
    _mulk(p, 5, 5, math.log2(10.0))
    _exp2p(p, 6, 5)
    _mulk(p, 5, 6, 200.0)
    p.fconst(12, 0.0)
    p.if_(4, "GT", 12, lambda: p.fconst(5, ACC_DECAY))
    _mulk(p, 5, 5, SR / 1000.0)
    _recip(p, 5, 5)
    p.fconst(12, 0.0)
    p.fop(5, 12, "-", 5)
    _exp_small(p, 6, 5)
    _sv(p, S_MC, 6)
    _unit(p, 7, 5)                               # SLID

    def slide():
        # the slew's coefficient for SLID's time: tau = 0.2 x (2 + 358 n) ms, e^(-1/(tau 44.1))
        _mulk(p, 7, 7, 358.0)
        _addk(p, 7, 7, 2.0)
        _mulk(p, 7, 7, 0.2 * SR / 1000.0)
        _recip(p, 7, 7)
        p.fconst(12, 0.0)
        p.fop(7, 12, "-", 7)
        _exp_small(p, 8, 7)
        _sv(p, S_SLC, 8)
        p.iconst(0, 2)                           # S_IDLE 2: the half sets the target, no jump
        _sv(p, S_IDLE, 0)

    def note():
        _ld(p, 0, S_IDLE)

        def first():                             # the first ever note: everything from rest
            p.iconst(0, 0)
            for k in (S_PH, *range(S_DX1, S_NY2 + 1), *range(S_E, S_END)):
                _sv(p, k, 0)
        p.iconst(1, 1)
        p.if_(0, "EQ", 1, first, kind="i")
        p.fconst(8, SLEW)
        _sv(p, S_SLC, 8)
        # mainEnv: y = 1 / c (its first output 1); the amp envelope at 1
        _ld(p, 6, S_MC)
        _recip(p, 6, 6)
        _sv(p, S_MENV, 6)
        p.fconst(6, 1.0)
        _sv(p, S_AENV, 6)
        p.iconst(0, 3)                           # S_IDLE 3: the half jumps the slew to the note
        _sv(p, S_IDLE, 0)
    p.fconst(12, 0.0)
    _ld(p, 0, S_IDLE)
    p.iconst(1, 1)
    # a slide needs a note before it; the first ever note is a trigger
    p.if_(7, "GT", 12, lambda: p.if_(0, "NE", 1, slide, note, kind="i"), note)


def _params(p: Prog, L: C.Layout) -> None:
    """The half's values from the knobs: the cutoff (314 x (2394/314)^n Hz), envScaler and
    envOffset (Open303's measured mapping), the resonance skewed, the blend; the note."""
    _unit(p, 4, 0)
    r = math.log2(2394.0 / 314.0)
    _mulk(p, 5, 4, r)
    _exp2p(p, 6, 5)
    _mulk(p, 5, 6, 314.0)
    _sv(p, D_CUT, 5)
    # c = log(cutoff / c0) / log(c1 / c0), the cutoff's exponent read back without a log
    _mulk(p, 6, 4, r / math.log2(C1 / C0))
    _addk(p, 6, 6, math.log2(314.0 / C0) / math.log2(C1 / C0))
    _unit(p, 7, 2)                               # e: ENV
    _mulk(p, 8, 7, SLOF)
    _addk(p, 8, 8, SLOC)                         # sLo
    _mulk(p, 9, 7, SHIF)
    _addk(p, 9, 9, SHIC)                         # sHi
    p.fop(9, 9, "-", 8)
    p.fop(9, 9, "*", 6)
    p.fop(9, 9, "+", 8)                          # (1 - c) sLo + c sHi
    _sv(p, D_ESC, 9)
    _mulk(p, 9, 6, OF)
    _addk(p, 9, 9, OC)
    _sv(p, D_EOF, 9)
    # resonance: (1 - e^(-3 n)) / (1 - e^-3)
    _unit(p, 4, 1)
    _mulk(p, 4, 4, -3.0 / math.log(2.0))
    _exp2p(p, 5, 4)
    p.fpass(4, 5)
    p.fconst(12, 1.0)
    p.fop(4, 12, "-", 4)
    _mulk(p, 4, 4, 1.0 / (1.0 - math.exp(-3.0)))
    _sv(p, D_RES, 4)
    _unit(p, 4, 6)
    _sv(p, D_BL, 4)
    # the note: a trigger jumps the slew to it (S_IDLE 3), a slide only sets it (2)
    _ld(p, 4, S_BASE)
    _sv(p, S_TGT, 4)
    _ld(p, 0, S_IDLE)
    p.iconst(1, 3)
    p.if_(0, "EQ", 1, lambda: _sv(p, S_FRQ, 4), kind="i")
    p.iconst(1, 2)
    p.if_(0, "GE", 1, lambda: (p.iconst(0, 0), _sv(p, S_IDLE, 0)), kind="i")


def _control(p: Prog, L: C.Layout) -> None:
    """One sample's control: the slew, the increment, the envelopes, the cutoff and the
    ladder's coefficients, the amplitude."""
    # pitch: y = x + c (y - x); the increment (cycles an oversampled sample) and its inverse
    _ld(p, 4, S_TGT)
    _ld(p, 5, S_FRQ)
    p.fop(5, 5, "-", 4)
    _ld(p, 6, S_SLC)
    p.fop(5, 5, "*", 6)
    p.fop(5, 5, "+", 4)
    _sv(p, S_FRQ, 5)
    _mulk(p, 5, 5, 1.0 / OSR)
    _sv(p, T_INC, 5)
    _mulk(p, 6, 5, 2.0 ** 32)
    p.trunc(6, 6)
    _sv(p, T_INCI, 6)                            # the phase's increment, 32-bit (S_PH: a turn is 2^32)
    _recip(p, 6, 5)
    _sv(p, T_RINC, 6)
    # mainEnv, rc1, rc2 (rc2 fed only with an accent)
    _ld(p, 4, S_MENV)
    _ld(p, 5, S_MC)
    p.fop(4, 4, "*", 5)
    _sv(p, S_MENV, 4)
    _ld(p, 5, S_RC1)                             # y = x + c (y - x)
    p.fop(5, 5, "-", 4)
    _mulk(p, 5, 5, RC1)
    p.fop(5, 5, "+", 4)
    _sv(p, S_RC1, 5)
    _ld(p, 7, S_ACC)
    p.fconst(6, 0.0)
    p.fconst(12, 0.0)
    p.if_(7, "GT", 12, lambda: p.fpass(6, 4))
    _ld(p, 8, S_RC2)
    p.fop(8, 8, "-", 6)
    _mulk(p, 8, 8, RC2)
    p.fop(8, 8, "+", 6)
    _sv(p, S_RC2, 8)
    # cutoff x 2^(envScaler (rc1 - envOffset) + accent rc2), 200..20000 Hz
    _ld(p, 9, D_EOF)
    p.fop(5, 5, "-", 9)
    _ld(p, 9, D_ESC)
    p.fop(5, 5, "*", 9)
    p.fop(8, 8, "*", 7)
    p.fop(5, 5, "+", 8)
    _exp2p(p, 9, 5)
    p.fpass(5, 9)
    _ld(p, 9, D_CUT)
    p.fop(5, 5, "*", 9)
    p.fconst(12, 200.0)
    p.fop(5, 5, "MAX", 12)
    p.fconst(12, 20000.0)
    p.fop(5, 5, "MIN", 12)
    # TB_303's coefficients: fx = cutoff / (fs_os sqrt 2)
    _mulk(p, 5, 5, 1.0 / (OSR * math.sqrt(2.0)))
    _mulk(p, 6, 5, 4.4156345)
    _addk(p, 6, 6, 12.358354)
    p.fop(6, 6, "*", 5)
    _addk(p, 6, 6, 1.0)
    _recip(p, 6, 6)
    _mulk(p, 9, 5, 6.1922189)
    _addk(p, 9, 9, 0.00045522346)
    p.fop(6, 6, "*", 9)
    _sv(p, T_B0, 6)
    _addk(p, 9, 5, 7198.6997)                    # k: Horner
    for c in (-5837.7917, -476.47308, 614.95611, 213.87126, 16.998792):
        p.fop(9, 9, "*", 5)
        _addk(p, 9, 9, c)
    _ld(p, 10, D_RES)
    _mulk(p, 11, 9, 1.0 / 17.0)
    _addk(p, 11, 11, -1.0)
    p.fop(11, 11, "*", 10)
    _addk(p, 11, 11, 1.0)
    p.fconst(12, 1.0)
    p.fop(12, 12, "+", 10)
    p.fop(11, 11, "*", 12)
    _sv(p, T_G, 11)
    p.fop(9, 9, "*", 10)
    _sv(p, T_K, 9)
    # the amplitude: the amp envelope + (0.45 + 4 accent) mainEnv, through the de-clicker
    _ld(p, 5, S_AENV)
    _mulk(p, 6, 5, AMP_MUL)
    _sv(p, S_AENV, 6)
    _mulk(p, 6, 7, 4.0)
    _addk(p, 6, 6, 0.45)
    p.fop(6, 6, "*", 4)
    p.fop(5, 5, "+", 6)
    _biquad(p, 5, DECLICK, S_DX1, S_DX2, S_DY1, S_DY2)
    _mulk(p, 5, 5, LEVEL)
    _sv(p, T_AMP, 5)


def _onepole(p: Prog, x: int, c, sx: int, sy: int) -> None:
    """Fx = b0 x + b1 x1 + a1 y1 (Open303's OnePoleFilter). Clobbers R10, R11, R12."""
    _mulk(p, 10, x, c[0])
    _ld(p, 11, sx)
    _sv(p, sx, x)
    _mulk(p, 11, 11, c[1])
    p.fop(10, 10, "+", 11)
    _ld(p, 11, sy)
    _mulk(p, 11, 11, c[2])
    p.fop(x, 10, "+", 11)
    _sv(p, sy, x)


def _biquad(p: Prog, x: int, c, sx1: int, sx2: int, sy1: int, sy2: int) -> None:
    """Fx = b0 x + b1 x1 + b2 x2 + a1 y1 + a2 y2 (Open303's BiquadFilter: + a). Clobbers
    R10, R11, R12."""
    _ld(p, 11, sx2)
    _mulk(p, 10, 11, c[2])
    _ld(p, 11, sx1)
    _sv(p, sx2, 11)
    _sv(p, sx1, x)
    _mulk(p, 11, 11, c[1])
    p.fop(10, 10, "+", 11)
    _mulk(p, 11, x, c[0])
    p.fop(10, 10, "+", 11)
    _ld(p, 11, sy2)
    _mulk(p, 11, 11, c[4])
    p.fop(10, 10, "+", 11)
    _ld(p, 11, sy1)
    _sv(p, sy2, 11)
    _mulk(p, 11, 11, c[3])
    p.fop(x, 10, "+", 11)
    _sv(p, sy1, x)


SAW_HI = EDGE * 2048.0 / 1023.0                  # the saw just before its step
SAW_LO = 2.0 * EDGE - 2.0                        # and just after


def _saw(p: Prog, d: int, q: int) -> None:
    """Fd = the saw prototype's value at phase Fq (0..1): q 2048 / 1023 before the step, 2 q - 2
    after. Clobbers R12."""
    p.fconst(12, EDGE)

    def before():
        _mulk(p, d, q, 2048.0 / 1023.0)

    def after():
        p.fop(d, q, "+", q)
        _addk(p, d, d, -2.0)
    p.if_(q, "LT", 12, before, after)


def _tanh(p: Prog, L: C.Layout, d: int, x: int) -> None:
    """Fd = tanh(Fx) = 1 - 2 / (e^(2x) + 1), x clamped to +-5.5 (tanh 0.99997). Clobbers R0-R3,
    R12-R15, I1, I12."""
    p.fconst(12, -5.5)
    p.fop(x, x, "MAX", 12)
    p.fconst(12, 5.5)
    p.fop(x, x, "MIN", 12)
    _mulk(p, x, x, 2.0 / math.log(2.0))
    _exp2(p, L, d, x)
    _addk(p, d, d, 1.0)
    _recip(p, d, d)
    _mulk(p, d, d, -2.0)
    _addk(p, d, d, 1.0)


def _blep(p: Prog, d: int, edge: float, h: int) -> None:
    """Fd += the poly-BLEP residual of a step of height Fh at phase EDGE (the phase at T_X,
    the increment T_INC, its inverse T_RINC). Clobbers R0, R1, R7, R8, R12."""
    PM = _pm()
    _ld(p, 7, T_X)
    _addk(p, 7, 7, -edge)
    PM.frac(p, 7)                                # d = (phase - edge) mod 1
    _ld(p, 8, T_INC)

    def past():                                  # crossed this sample: -h (1 - t)^2 / 2
        _ld(p, 8, T_RINC)
        p.fop(7, 7, "*", 8)
        p.fconst(12, 1.0)
        p.fop(7, 12, "-", 7)
        p.fop(7, 7, "*", 7)
        p.fop(7, 7, "*", h)
        _mulk(p, 7, 7, -0.5)
        p.fop(d, d, "+", 7)

    def ahead():                                 # before the next sample: h (1 - t)^2 / 2
        p.fconst(12, 1.0)
        p.fop(7, 12, "-", 7)
        p.if_(7, "LT", 8, lambda: (_ld(p, 8, T_RINC), p.fop(7, 7, "*", 8), p.fconst(12, 1.0),
                                   p.fop(7, 12, "-", 7), p.fop(7, 7, "*", 7), p.fop(7, 7, "*", h),
                                   _mulk(p, 7, 7, 0.5), p.fop(d, d, "+", 7)))
    p.if_(7, "LT", 8, past, ahead)


def _osc(p: Prog, L: C.Layout) -> None:
    """F4 = one oversampled sample of the oscillator: (1 - b) saw + b square / 2, its DC off
    from 43 Hz on, its steps poly-BLEPed; the phase moves on. The phase is a 32-bit integer (a
    turn 2^32: it adds exactly, as Open303's double does near enough; a float32 phase drifts).
    Clobbers R0-R3, R5-R15, I1, I12."""
    _ld(p, 8, S_PH)
    p.iconst(12, -32)
    p.float_(5, 8, 12)                           # signed / 2^32: -0.5..0.5
    p.fconst(12, 0.0)
    p.if_(5, "LT", 12, lambda: (p.fconst(12, 1.0), p.fop(5, 5, "+", 12)))
    _sv(p, T_X, 5)
    _saw(p, 4, 5)
    _ld(p, 9, D_BL)
    p.fconst(12, 1.0)
    p.fop(6, 12, "-", 9)                         # 1 - b
    p.fop(4, 4, "*", 6)
    _ld(p, 12, T_OSN)
    p.fop(4, 4, "+", 12)                         # the DC (T_OSN: control's, per sample)
    p.fconst(12, 0.0)

    def square():
        _ld(p, 5, T_X)
        _addk(p, 5, 5, -0.5)
        _pm().frac(p, 5)
        _saw(p, 6, 5)
        _mulk(p, 6, 6, K_SQ)
        _addk(p, 6, 6, OFF_SQ)
        _tanh(p, L, 7, 6)
        _ld(p, 9, D_BL)
        p.fop(7, 7, "*", 9)
        _mulk(p, 7, 7, -0.5)
        p.fop(4, 4, "+", 7)
        # its jump (from -1 to +1, b / 2 x 2) at EDGE + 1/2
        _blep(p, 4, EDGE - 0.5, 9)
    p.if_(9, "GT", 12, square)
    # the saw's step, -(1 - b) (SAW_HI - SAW_LO), at EDGE
    _ld(p, 9, D_BL)
    p.fconst(12, 1.0)
    p.fop(9, 12, "-", 9)
    _mulk(p, 9, 9, SAW_LO - SAW_HI)
    _blep(p, 4, EDGE, 9)
    _ld(p, 8, S_PH)
    _ld(p, 9, T_INCI)
    p.iop(8, 8, "+", 9)                          # wraps at a turn by itself
    _sv(p, S_PH, 8)


def _ladder(p: Prog, x: int) -> None:
    """Fx = TB_303's ladder on Fx: y0 = x - fbHP(k y4); four coupled stages; 2 g y4.
    Clobbers R5-R12."""
    _ld(p, 5, S_Y4)
    _ld(p, 6, T_K)
    p.fop(5, 5, "*", 6)
    _onepole(p, 5, FBHP, S_FX1, S_FY1)
    p.fop(x, x, "-", 5)                          # y0
    _ld(p, 5, S_Y1)
    _ld(p, 6, S_Y2)
    _ld(p, 7, S_Y3)
    _ld(p, 8, S_Y4)
    _ld(p, 9, T_B0)
    p.fop(10, x, "-", 5)
    p.fop(10, 10, "+", 6)
    p.fop(10, 10, "*", 9)
    p.fop(10, 10, "+", 10)
    p.fop(5, 5, "+", 10)                         # y1 += 2 b0 (y0 - y1 + y2)
    p.fop(10, 6, "+", 6)
    p.fop(10, 5, "-", 10)
    p.fop(10, 10, "+", 7)
    p.fop(10, 10, "*", 9)
    p.fop(6, 6, "+", 10)                         # y2 += b0 (y1 - 2 y2 + y3)
    p.fop(10, 7, "+", 7)
    p.fop(10, 6, "-", 10)
    p.fop(10, 10, "+", 8)
    p.fop(10, 10, "*", 9)
    p.fop(7, 7, "+", 10)                         # y3 += b0 (y2 - 2 y3 + y4)
    p.fop(10, 8, "+", 8)
    p.fop(10, 7, "-", 10)
    p.fop(10, 10, "*", 9)
    p.fop(8, 8, "+", 10)                         # y4 += b0 (y3 - 2 y4)
    _sv(p, S_Y1, 5)
    _sv(p, S_Y2, 6)
    _sv(p, S_Y3, 7)
    _sv(p, S_Y4, 8)
    _ld(p, 9, T_G)
    p.fop(x, 8, "*", 9)
    p.fop(x, x, "+", x)


def _ellip(p: Prog, x: int) -> None:
    """Fx = the elliptic decimation filter on Fx: six sections, transposed direct form II
    (y = b0 x + s0; s0 = b1 x - a1 y + s1; s1 = b2 x - a2 y). Clobbers R5-R12."""
    _mulk(p, x, x, ELLIP_GAIN)
    for k, (b0, b1, b2, a1, a2) in enumerate(ELLIP):
        s0, s1 = S_E + 2 * k, S_E + 2 * k + 1
        _ld(p, 5, s0)
        _mulk(p, 6, x, b0)
        p.fop(6, 6, "+", 5)                      # y
        _ld(p, 7, s1)
        _mulk(p, 8, x, b1)
        p.fop(8, 8, "+", 7)
        _mulk(p, 9, 6, -a1)
        p.fop(8, 8, "+", 9)
        _sv(p, s0, 8)
        _mulk(p, 8, x, b2)
        _mulk(p, 9, 6, -a2)
        p.fop(8, 8, "+", 9)
        _sv(p, s1, 8)
        p.fpass(x, 6)


ELLIP_MF = True                                  # (perf, 2026-11-11) the multifunction schedule; False = one op at a time


def _section_mf(p: Prog, k: int, coef, last: bool) -> None:
    """One elliptic section over the four samples at T_Y0.. (read, and written back as the next section's input; the
    last section keeps only the fourth sample, in F4), a software-pipelined schedule, one multiplier and one ALU
    operation a cycle (II 5, the multiplier's five products a sample): the same operations on the same operands as
    the one-at-a-time form, so bit for bit what it computes. Registers (the multiplier's operands F0-F3 x F4-F7, the
    ALU's F8-F11 x F12-F15): F0 / F3 the sample (alternating), F4 b0, F5 b1, F6 b2, F1 -a1, F2 -a2, F7 y,
    F8 b0 x, F11 b1 x, F10 b2 x, F9 b0 x + s0... (see below), F12 s0, F13 s1, F14 y (-a1), F15 y (-a2)."""
    b0, b1, b2, a1, a2 = coef
    s0, s1 = S_E + 2 * k, S_E + 2 * k + 1
    for reg, c in ((4, b0), (5, b1), (6, b2), (1, -a1), (2, -a2)):
        p.fconst(reg, c)
    _ld(p, 0, T_Y0)                                  # x0
    xr = (0, 3, 0, 3)
    cyc: dict[int, dict] = {}

    def put(c: int, kind: str, v) -> None:
        d = cyc.setdefault(c, {})
        assert kind not in d, (c, kind)
        d[kind] = v
    for j in range(4):
        base, x = 5 * j, xr[j]
        put(base + 0, "mul", (8, x, 4))              # F8 = x b0
        put(base + 1, "mul", (11, x, 5))             # F11 = x b1
        put(base + 1, "alu", ("+", 7, 8, 12))        # y = x b0 + s0
        put(base + 2, "mul", (14, 1, 7))             # F14 = y (-a1)
        put(base + 2, "alu", ("+", 9, 11, 13))       # F9 = x b1 + s1
        put(base + 3, "mul", (15, 2, 7))             # F15 = y (-a2)
        put(base + 3, "alu", ("+", 12, 9, 14))       # s0 = (x b1 + s1) + y (-a1)
        put(base + 4, "mul", (10, x, 6))             # F10 = x b2
        put(base + 5, "alu", ("+", 13, 10, 15))      # s1 = x b2 + y (-a2)
        if not last:
            put(base + 2, "mv", ("stk", T_Y0 + j - S_MID, 0, 7))
        if j < 3:
            put(base + 4, "mv", ("ldk", xr[j + 1], T_Y0 + j + 1 - S_MID, 0))
    put(0, "mv", ("ldk", 12, s0 - S_MID, 0))
    put(1, "mv", ("ldk", 13, s1 - S_MID, 0))
    put(19, "mv", ("stk", s0 - S_MID, 0, 12))        # s0 is final after the ALU op of cycle 18
    for c in sorted(cyc):
        d = cyc[c]
        ops = []
        if "mul" in d and "alu" in d:
            ops += [("*", *d["mul"]), (d["alu"][0], *d["alu"][1:])]
        elif "mul" in d:
            m = d["mul"]
            ops.append(("op", m[0], m[1], "*", m[2]))
        else:
            al = d["alu"]
            ops.append(("op", al[1], al[2], al[0], al[3]))
        if "mv" in d:
            ops.append(d["mv"])
        p.par(*ops)
    _sv(p, s1, 13)
    if last:
        p.fpass(4, 7)


def _ellip4(p: Prog) -> None:
    """F4 = the elliptic decimation filter's output for the fourth of the four ladder outputs (T_Y0..), the
    first three run through it for its states. perf, 2026-11-11: section by section over the four samples
    (a section's five coefficients and two states loaded once, not four times), the same operations in the same
    order on every sample, so bit for bit what _ellip did sample by sample; then (ELLIP_MF) the multiplier and
    the ALU working together (_section_mf). Clobbers R0-R3, R5-R15."""
    if ELLIP_MF:
        p.fconst(12, ELLIP_GAIN)
        _ld(p, 0, T_Y0)
        for j in range(4):                       # x_j G, written back for the first section
            p.par(("op", j, j, "*", 12), *((("ldk", j + 1, T_Y0 + j + 1 - S_MID, 0),) if j < 3 else
                                              (("stk", T_Y0 - S_MID, 0, 0),)))
        for j in (1, 2, 3):
            _sv(p, T_Y0 + j, j)
        for k, coef in enumerate(ELLIP):
            _section_mf(p, k, coef, k == len(ELLIP) - 1)
        return
    xs = (13, 14, 15, 11)
    for j, r in enumerate(xs):
        _ld(p, r, T_Y0 + j)
        _mulk(p, r, r, ELLIP_GAIN)
    for k, (b0, b1, b2, a1, a2) in enumerate(ELLIP):
        s0, s1 = S_E + 2 * k, S_E + 2 * k + 1
        for reg, c in ((0, b0), (1, b1), (2, b2), (3, -a1), (10, -a2)):
            p.fconst(reg, c)
        _ld(p, 5, s0)
        _ld(p, 7, s1)
        for r in xs:
            p.fop(6, r, "*", 0)
            p.fop(6, 6, "+", 5)                  # y = b0 x + s0
            p.fop(8, r, "*", 1)
            p.fop(8, 8, "+", 7)
            p.fop(9, 6, "*", 3)
            p.fop(5, 8, "+", 9)                  # s0 = b1 x - a1 y + s1 (F5's old s0 is used up)
            p.fop(8, r, "*", 2)
            p.fop(9, 6, "*", 10)
            p.fop(7, 8, "+", 9)                  # s1 = b2 x - a2 y
            p.fpass(r, 6)
        _sv(p, s0, 5)
        _sv(p, s1, 7)
    p.fpass(4, 11)


def _sample(p: Prog, L: C.Layout) -> None:
    """One sample at I4."""
    _control(p, L)
    # the DC the band-limited levels drop, from 43 Hz on (as the oscillator reads it)
    _ld(p, 4, T_INC)
    p.fconst(5, 0.0)
    p.fconst(12, DC_FROM)

    def dc():
        _ld(p, 6, D_BL)
        p.fconst(12, 1.0)
        p.fop(7, 12, "-", 6)
        _mulk(p, 7, 7, -DC_SAW)
        _mulk(p, 6, 6, -0.5 * DC_SQ)
        p.fop(5, 7, "+", 6)
    p.if_(4, "GE", 12, dc)
    _sv(p, T_OSN, 5)

    def one(j: int):
        _osc(p, L)
        p.fconst(12, 0.0)
        p.fop(4, 12, "-", 4)                     # Open303 negates the oscillator
        _onepole(p, 4, HP1, S_H1X, S_H1Y)
        _ladder(p, 4)
        _sv(p, T_Y0 + j, 4)
    for j in range(OS):                          # (perf: unrolled; the decimator runs after the four)
        one(j)
    _ellip4(p)                                   # F4 = the last sample's output (the others are dropped)
    _onepole(p, 4, AP, S_APX, S_APY)
    _onepole(p, 4, HP2, S_H2X, S_H2Y)
    _biquad(p, 4, NOTCH, S_NX1, S_NX2, S_NY1, S_NY2)
    _ld(p, 5, T_AMP)
    p.fop(4, 4, "*", 5)
    p.stpost(4, 4)


def half(p: Prog, L: C.Layout) -> None:
    """16 samples at I4; silent until the first note."""
    _ld(p, 0, S_IDLE)
    p.iconst(1, 1)

    def zeros():
        p.fconst(8, 0.0)
        for _ in range(16):
            p.stpost(4, 8)

    def run():
        p.geti(8, 3)
        p.iconst(9, p.ioff(3, 4 * (C.K.S0 + S_MID)))                       # (I3 is biased: shrink)
        p.iop(8, 8, "+", 9)
        p.seti(0, 8, "I0 = the slot's state word 32")
        _I0[0] = True
        try:
            _params(p, L)
            p.loop(L.W["n4"], 16, lambda: _sample(p, L))
        finally:
            _I0[0] = False
    p.if_(0, "EQ", 1, zeros, run, kind="i")
