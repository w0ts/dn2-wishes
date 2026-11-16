"""PLAITS: two of Mutable Instruments Plaits' engines, WAVESHAPING (WS) and GRANULAR FORMANT
(GRAIN), as a Monomachine-style machine (docs/plaits.md). A port of Emilie Gillet's C++
(github.com/pichenettes/eurorack, plaits/dsp/engine/waveshaping_engine.cc, grain_engine.cc,
dsp/oscillator/oscillator.h, grainlet_oscillator.h; MIT, THIRD-PARTY.md).

One voice per track at 44.1 kHz (PERC's stream; every frequency is Hz / 44100, so a note
sounds at its pitch), 16-sample halves as Plaits' blocks (its parameter interpolators run
over 16 samples, not 12). Only Plaits' OUT is rendered (the track is mono); its LPG and AUX
are left to the DN2's filter and amp. The oscillators are never reset on a trig: Plaits'
engines run on (a reset per note is what clicked in the Digitakt II ports).

- WS: a band-limited slope oscillator (integrated poly-BLEP), morph = its pulse width; the
  waveshaper (HARM crossfades Plaits' five Tides tables), the wavefolder (TIMB: the fold
  table, Hermite-interpolated), both tamed by the pitch as Plaits does.
- GRAIN: two grainlet oscillators on the note's carrier (their carrier phase, shape and bleed
  are the same, so they share them), formants at TIMB (24..108 semitones) and TIMB x HARM's
  ratio, poly-BLEP at the carrier's reset, then the DC blocker.

Sines are PERC's sine table (256 a turn, linear) where Plaits' is 512; exp2 PERC's table; a
division PERC's reciprocal. The tables (WS's five shapes, the fold) ship in zpack
(dnfw.mnm.tables, Q23).

Parameters: HARM TIMB MORP --- --- --- MODL TUNE.
"""

from __future__ import annotations

import math

from . import core as C
from . import plk as K
from . import plaits_va, plaits_fm, plaits_add, plaits_swarm, plaits_noise, plaits_part, plaits_string, plaits_modal, plaits_bd, plaits_sd, plaits_hh
from ..perc.dsl import Prog

NAME, ID = "PLAITS", 65
PNAMES = ("HARM", "TIMB", "MORP", "---", "---", "FINE", "MODL", "TUNE")   # FINE 2026-11-09
WS, GRAIN = range(2)
# 2026-11-09: Plaits' other engines, each its own module (dnfw.mnm.plk their common ground), after
# WS and GRAIN in MODL's choices
ENGINES = (plaits_va, plaits_fm, plaits_add, plaits_swarm, plaits_noise, plaits_part, plaits_string, plaits_modal, plaits_bd, plaits_sd, plaits_hh)
MODELS = ("WS", "GRAN") + tuple(E.MODEL for E in ENGINES)   # the page shows four characters
N_MODELS = len(MODELS)
# 2026-11-09: Plaits' OUT stage after each of those engines (voice.cc RegisterInstance's out_gain,
# voice.h ChannelPostProcessor): a fixed gain, the result clipped to +-1 (Plaits' Clip16), or, for a
# negative figure, stmlib's Limiter with that pre-gain (its peak follower, x 0.8), then clipped too. The raw engines go
# well past +-1 (PART to 8, MDAL to 3.6). WS and GRAIN stay as they were, without it.
OUT_GAIN = {"VA": 0.8, "FM": 0.6, "ADD": 0.8, "SWRM": -3.0, "NOIS": -1.0, "PART": -2.0, "STRG": -1.0,
            "MDAL": -1.0, "BD": 0.8, "SD": 0.8, "HH": 0.8}
POST = True                                     # False: the raw engines (the references' comparisons)
DEFAULTS = (64, 64, 64, 0, 0, 64, 0, 64)

SR = 44100.0
F_MAX, F_MIN = 0.25, 0.000001                    # plaits::kMaxFrequency, kMinFrequency
HALF = 16

# state (slot words S0..): WS's oscillator and interpolators, GRAIN's
(S_WPH, S_WNX, S_WHI, S_WF, S_WPW, S_WSH, S_WGN,
 S_GCP, S_GF0, S_GCS, S_GCB, S_GFP0, S_GFP1, S_GF1A, S_GF1B, S_GNX, S_GDC, S_BASE) = range(18)
# per half (slot words): the interpolators' steps, the DC blocker's g and gi, the model
(D_WFI, D_WPWI, D_WSHI, D_WGNI, D_GF0I, D_GCSI, D_GCBI, D_GF1AI, D_GF1BI, D_GG, D_GGI,
 D_MOD) = range(18, 30)
# per sample scratch (slot words)
(T_UP, T_DN, T_THIS, T_NXT, T_F, T_W, T_OUT, T_RT, T_CS, T_CB, T_CAR, T_INV, T_CS0,
 T_CB0) = range(30, 44)


def _pm():
    from ..perc import machines as PM
    return PM


def _ld(p: Prog, d: int, k: int) -> None:
    C.st(p, d, k)


def _sv(p: Prog, k: int, s: int) -> None:
    C.sts(p, k, s)


def _mulk(p: Prog, d: int, a: int, x: float, t: int = 12) -> None:
    p.fconst(t, x)
    p.fop(d, a, "*", t)


def _addk(p: Prog, d: int, a: int, x: float, t: int = 12) -> None:
    p.fconst(t, x)
    p.fop(d, a, "+", t)


def _clamp(p: Prog, x: int, lo: float, hi: float) -> None:
    p.fconst(12, lo)
    p.fop(x, x, "MAX", 12)
    p.fconst(12, hi)
    p.fop(x, x, "MIN", 12)


def _unit(p: Prog, d: int, k: int) -> None:
    """Fd = parameter k as 0..1 (knob / 127)."""
    C.par(p, d, k)
    _mulk(p, d, d, 128.0 / 127.0)


def _abs(p: Prog, d: int, x: int) -> None:
    p.fconst(12, 0.0)
    p.fop(12, 12, "-", x)
    p.fop(d, x, "MAX", 12)


def sinw(p: Prog, L: C.Layout, d: int, x: int) -> None:
    """Fd = sin(2 pi Fx), any Fx. Clobbers R0-R3, R12, R15, I1, I12."""
    _pm().sin_(p, L.perc, d, x, wrap=True)


def recip(p: Prog, d: int, x: int) -> None:
    """Fd = 1 / Fx. Clobbers R12-R15, I12."""
    _pm().recip(p, d, x)


def _ifrac(p: Prog, i: int, f: int, x: int) -> None:
    """Ri = (int) Fx (towards zero, as C's cast), Ff = Fx - Ri. Clobbers R12."""
    p.trunc(i, x)
    p.iconst(12, 0)
    p.float_(f, i, 12)
    p.fop(f, x, "-", f)


def _interp(p: Prog, d: int, s: int, inc: int) -> None:
    """Fd = state S += step INC (ParameterInterpolator.Next). Clobbers R11."""
    _ld(p, d, s)
    _ld(p, 11, inc)
    p.fop(d, d, "+", 11)
    _sv(p, s, d)


def _step(p: Prog, inc: int, s: int, x: int) -> None:
    """step INC = (Fx - state S) / 16 (a new interpolator over the half). Clobbers R11."""
    _ld(p, 11, s)
    p.fop(11, x, "-", 11)
    _mulk(p, 11, 11, 1.0 / HALF)
    _sv(p, inc, 11)


def exact(A: int, F: int, knobs, pre: int = 0) -> dict:
    """no Monomachine increments: PLAITS takes its pitch from VW pitch (pitch below)"""
    return {}


def init(p: Prog, L: C.Layout) -> None:
    """Every engine as Plaits' Init: the slope oscillator at phase 0.5, its frequency 0.001,
    its pulse width 0.5; the grainlets and the DC blocker at 0."""
    p.iconst(0, 0)
    for k in range(S_BASE + 1):
        _sv(p, k, 0)
    p.fconst(0, 0.5)
    _sv(p, S_WPH, 0)
    _sv(p, S_WPW, 0)
    p.fconst(0, 0.001)
    _sv(p, S_WF, 0)
    p.iconst(0, 1)
    _sv(p, S_WHI, 0)
    # 2026-11-09: the other engines' common words: no model rendered yet (their init runs when
    # one is first chosen), no trigger, the random generator at stmlib's seed
    p.iconst(0, -1)
    _sv(p, K.S_LAST, 0)
    p.iconst(0, 0)
    _sv(p, K.S_TRIG, 0)
    p.iconst(0, K.RNG_SEED)
    _sv(p, K.S_RNG, 0)
    _limiter_init(p)


def trig(p: Prog, L: C.Layout) -> None:
    """S_TRIG: the next half is Plaits' TRIGGER_RISING_EDGE (the engines that take a trigger:
    the drums, the physical models, PART). The oscillators are never reset (no click)."""
    p.iconst(0, 1)
    _sv(p, K.S_TRIG, 0)


def pitch(p: Prog, L: C.Layout) -> None:
    """S_BASE = the note's frequency a sample: 440 x 2^((note - 69 + TUNE + FINE) / 12) / 44100.
    2026-11-09 (the User): TUNE in whole semitones, (knob x 49 >> 7) - 24, -24..+24, 0 at 64 (until
    then knob / 128 x 48 - 24, continuous); FINE knob - 64 cents (-64..+63, 0 at 64). The page shows
    both by the same arithmetic (pages.MNM_CHOICES, md_page.c MW_SIGNED). At 64 / 64 the sum is 0.0,
    so the note is the one it was."""
    C.vw(p, 1, "pitch")
    C.par(p, 2, 7)                               # knob / 128, exactly
    _mulk(p, 2, 2, 49.0)
    p.trunc(2, 2)                                # (knob x 49) >> 7 (exact in float32)
    p.iconst(12, -24)
    p.iop(2, 12, "+", 2)
    p.iconst(12, 0)
    p.float_(2, 2, 12)                           # TUNE, semitones
    C.par(p, 3, 5)
    _mulk(p, 3, 3, 128.0)
    _addk(p, 3, 3, -64.0)
    _mulk(p, 3, 3, 0.01)                         # FINE, cents
    p.fop(2, 2, "+", 3)
    p.fop(1, 1, "+", 2)
    _sv(p, K.S_NOTE, 1)                          # the note, for the engines after GRAIN
    _addk(p, 1, 1, -69.0)
    _mulk(p, 1, 1, 1.0 / 12.0)
    _pm().exp2(p, L.perc, 1, 1)
    _mulk(p, 1, 1, 440.0 / SR)
    _sv(p, S_BASE, 1)


# -- WS ----------------------------------------------------------------------------------------
def _tame(p: Prog, d: int, f0: int, h: int, order: float) -> None:
    """Fd = Tame(f0, harmonics, order): clamp(1 - (f0 h - 0.5/order) / (0.5 - 0.5/order))^3.
    Clobbers R12."""
    max_f = 0.5 / order
    p.fop(d, f0, "*", h)
    _addk(p, d, d, -max_f)
    _mulk(p, d, d, -1.0 / (0.5 - max_f))
    _addk(p, d, d, 1.0)
    _clamp(p, d, 0.0, 1.0)
    p.fop(12, d, "*", d)
    p.fop(d, d, "*", 12)


def _ws_params(p: Prog, L: C.Layout) -> None:
    _ld(p, 4, S_BASE)                            # f0 (NoteToFrequency), unclamped
    _unit(p, 5, 0)                               # harmonics
    _unit(p, 6, 1)                               # timbre
    _unit(p, 7, 2)                               # morph
    # the oscillator: frequency clamped, pulse width morph x 0.45 + 0.5 clamped to it
    p.fpass(8, 4)
    _clamp(p, 8, F_MIN, F_MAX)
    _step(p, D_WFI, S_WF, 8)
    _mulk(p, 9, 7, 0.45)
    _addk(p, 9, 9, 0.5)
    p.fop(10, 8, "+", 8)                         # 2 f
    p.fop(9, 9, "MAX", 10)
    p.fconst(12, 1.0)
    p.fop(10, 12, "-", 10)                       # 1 - 2 f
    p.fop(9, 9, "MIN", 10)
    _step(p, D_WPWI, S_WPW, 9)
    # slope = 3 + |morph - 0.5| x 5; shape_amount = |harmonics - 0.5| x 2
    _addk(p, 9, 7, -0.5)
    _abs(p, 9, 9)
    _mulk(p, 9, 9, 5.0)
    _addk(p, 9, 9, 3.0)
    _addk(p, 10, 5, -0.5)                        # harmonics - 0.5
    _tame(p, 8, 4, 9, 16.0)                      # shape_amount_attenuation
    _abs(p, 7, 10)
    p.fop(7, 7, "+", 7)                          # shape_amount
    p.fop(7, 7, "*", 8)
    _mulk(p, 7, 7, 5.0)
    _addk(p, 7, 7, 3.0)
    p.fop(7, 7, "*", 9)
    _tame(p, 3, 4, 7, 12.0)                      # wavefolder_gain_attenuation
    p.fop(10, 10, "*", 8)
    _addk(p, 10, 10, 0.5)
    _step(p, D_WSHI, S_WSH, 10)
    p.fop(6, 6, "*", 3)
    _mulk(p, 6, 6, 0.46)
    _addk(p, 6, 6, 0.03)
    _step(p, D_WGNI, S_WGN, 6)


def _iblep_sub(p: Prog) -> None:
    """F10 = ThisIntegratedBlepSample(F8) x F9, F11 = NextIntegratedBlepSample(F8) x F9
    (stmlib polyblep.h). Clobbers R13, R14."""
    def nib(d, t):                               # 0.1875 - t/2 + 1.5 (t/2)^2 - (t/2)^4
        _mulk(p, 13, t, 0.5, t=14)
        p.fop(14, 13, "*", 13)                   # t2
        p.fop(d, 14, "*", 14)                    # t4
        p.fconst(12, 1.5)
        p.fop(14, 14, "*", 12)
        p.fop(14, 14, "-", d)
        p.fop(14, 14, "-", 13)
        _addk(p, d, 14, 0.1875)

    def body():
        nib(11, 8)
        p.fop(11, 11, "*", 9)
        p.fconst(12, 1.0)
        p.fop(13, 12, "-", 8)
        p.fpass(10, 13)
        nib(10, 10)
        p.fop(10, 10, "*", 9)
    p.call("pl_iblep", body)


def _ws_edge(p: Prog, sign: float) -> None:
    """this -= / += ThisIntegratedBlep(t) d, next likewise: t in F8, d in F9."""
    _iblep_sub(p)
    _ld(p, 4, T_THIS)
    _ld(p, 5, T_NXT)
    p.fop(4, 4, "+" if sign > 0 else "-", 10)
    p.fop(5, 5, "+" if sign > 0 else "-", 11)
    _sv(p, T_THIS, 4)
    _sv(p, T_NXT, 5)


def _ws_disc(p: Prog, x: int) -> None:
    """F8 = Fx / f (the edge's time), F9 = (up + down) f. Clobbers R12-R15, R8, R9, I12."""
    _ld(p, 15, T_F)
    recip(p, 15, 15)
    p.fop(8, x, "*", 15)
    _ld(p, 9, T_UP)
    _ld(p, 13, T_DN)
    p.fop(9, 9, "+", 13)
    _ld(p, 13, T_F)
    p.fop(9, 9, "*", 13)


def _ws_osc(p: Prog) -> None:
    """One sample of Oscillator::Render<OSCILLATOR_SHAPE_SLOPE> -> T_OUT."""
    _interp(p, 4, S_WF, D_WFI)
    _sv(p, T_F, 4)
    _interp(p, 5, S_WPW, D_WPWI)
    _sv(p, T_W, 5)
    _ld(p, 6, S_WPH)
    p.fop(6, 6, "+", 4)
    _sv(p, S_WPH, 6)
    recip(p, 7, 5)
    _sv(p, T_UP, 7)
    p.fconst(12, 1.0)
    p.fop(7, 12, "-", 5)
    recip(p, 7, 7)
    _sv(p, T_DN, 7)
    _ld(p, 0, S_WNX)
    _sv(p, T_THIS, 0)
    p.fconst(0, 0.0)
    _sv(p, T_NXT, 0)
    # high_ ^ (phase < pw): the falling edge
    _ld(p, 6, S_WPH)
    _ld(p, 5, T_W)
    p.iconst(1, 0)
    p.if_(6, "LT", 5, lambda: p.iconst(1, 1))
    _ld(p, 0, S_WHI)

    def fall():
        _sv(p, S_WHI, 1)
        _ld(p, 6, S_WPH)
        _ld(p, 5, T_W)
        p.fop(6, 6, "-", 5)
        _ws_disc(p, 6)
        _ws_edge(p, -1.0)
    p.if_(0, "NE", 1, fall, kind="i")
    # the wrap: the rising edge
    _ld(p, 6, S_WPH)
    p.fconst(12, 1.0)

    def wrap():
        p.fop(6, 6, "-", 12)
        _sv(p, S_WPH, 6)
        _ws_disc(p, 6)
        _ws_edge(p, 1.0)
        p.iconst(0, 1)
        _sv(p, S_WHI, 0)
    p.if_(6, "GE", 12, wrap)
    # next += high ? phase up : 1 - (phase - pw) down
    _ld(p, 6, S_WPH)
    _ld(p, 0, S_WHI)

    def up():
        _ld(p, 7, T_UP)
        p.fop(7, 6, "*", 7)

    def down():
        _ld(p, 5, T_W)
        p.fop(7, 6, "-", 5)
        _ld(p, 5, T_DN)
        p.fop(7, 7, "*", 5)
        p.fconst(12, 1.0)
        p.fop(7, 12, "-", 7)
    p.ifz(0, "NE", up, down)
    _ld(p, 5, T_NXT)
    p.fop(5, 5, "+", 7)
    _sv(p, S_WNX, 5)
    _ld(p, 4, T_THIS)
    p.fop(4, 4, "+", 4)
    _addk(p, 4, 4, -1.0)
    _sv(p, T_OUT, 4)


def _ws_shape(p: Prog, L: C.Layout) -> None:
    """The waveshaper and the wavefolder on T_OUT -> stored at I4."""
    _interp(p, 4, S_WSH, D_WSHI)
    _mulk(p, 4, 4, 3.9999)
    _ifrac(p, 5, 6, 4)                           # R5 shape's table, F6 its fraction
    _ld(p, 7, T_OUT)
    _mulk(p, 7, 7, 127.0)
    _addk(p, 7, 7, 128.0)
    _ifrac(p, 8, 9, 7)                           # R8 the index, F9 its fraction
    p.iconst(12, 255)
    p.iop(8, 8, "AND", 12)
    # the row: tables + 4 (257 shape + index)
    p.iconst(12, 257)
    p.mul_ssi(5, 5, 12)
    p.ipass(12, 5)
    p.iop(5, 12, "+", 8)
    p.lsh(5, 5, 2)
    p.iconst(12, L.PL["ws"])
    p.iop(5, 12, "+", 5)
    p.seti(1, 5)

    def lerp(d, k):                              # Fd = row[k] + (row[k+1] - row[k]) frac
        p.ldi(2, k, 1)
        p.ldi(3, k + 1, 1)
        p.fop(3, 3, "-", 2)
        p.fop(3, 3, "*", 9)
        p.fop(d, 2, "+", 3)
    lerp(10, 0)
    lerp(11, 257)
    p.fop(11, 11, "-", 10)
    p.fop(11, 11, "*", 6)
    p.fop(10, 10, "+", 11)                       # mix
    _interp(p, 4, S_WGN, D_WGNI)
    p.fop(10, 10, "*", 4)
    _addk(p, 10, 10, 0.5)                        # index
    # InterpolateHermite(lut_fold + 1, index, 512)
    _mulk(p, 10, 10, 512.0)
    _ifrac(p, 8, 9, 10)
    p.lsh(8, 8, 2)
    p.iconst(12, L.PL["fold"])
    p.iop(8, 12, "+", 8)
    p.seti(1, 8)
    p.ldi(4, 0, 1)                               # xm1
    p.ldi(5, 1, 1)                               # x0
    p.ldi(6, 2, 1)                               # x1
    p.ldi(7, 3, 1)                               # x2
    p.fop(10, 6, "-", 4)
    _mulk(p, 10, 10, 0.5)                        # c
    p.fop(11, 5, "-", 6)                         # v
    p.fop(4, 10, "+", 11)                        # w
    p.fop(7, 7, "-", 5)
    _mulk(p, 7, 7, 0.5)
    p.fop(7, 7, "+", 11)
    p.fop(7, 7, "+", 4)                          # a
    p.fop(4, 4, "+", 7)                          # b_neg
    p.fop(7, 7, "*", 9)
    p.fop(7, 7, "-", 4)
    p.fop(7, 7, "*", 9)
    p.fop(7, 7, "+", 10)
    p.fop(7, 7, "*", 9)
    p.fop(7, 7, "+", 5)
    p.stpost(4, 7)


def _ws_half(p: Prog, L: C.Layout) -> None:
    _ws_params(p, L)

    def one():
        _ws_osc(p)
        _ws_shape(p, L)
    p.loop(L.W["n4"], HALF, one)


# -- GRAIN -------------------------------------------------------------------------------------
def _grain_params(p: Prog, L: C.Layout) -> None:
    PM = _pm()
    _ld(p, 4, S_BASE)                            # f0, unclamped
    _unit(p, 5, 0)                               # harmonics
    _unit(p, 6, 1)                               # timbre
    _unit(p, 7, 2)                               # morph
    # carrier_shape = 0.33 + (morph - 0.33) max(1 - 24 f0, 0)
    _mulk(p, 8, 4, -24.0)
    _addk(p, 8, 8, 1.0)
    p.fconst(12, 0.0)
    p.fop(8, 8, "MAX", 12)
    _addk(p, 7, 7, -0.33)
    p.fop(7, 7, "*", 8)
    _addk(p, 7, 7, 0.33)
    _step(p, D_GCSI, S_GCS, 7)
    # carrier_bleed = 1 - 2 harm below 0.5, else 0; fixed = b (2 - b)
    p.fop(8, 5, "+", 5)
    p.fconst(12, 1.0)
    p.fop(8, 12, "-", 8)
    p.fconst(12, 0.0)
    p.fop(8, 8, "MAX", 12)
    p.fconst(12, 2.0)
    p.fop(9, 12, "-", 8)
    p.fop(8, 8, "*", 9)
    _step(p, D_GCBI, S_GCB, 8)
    # the carrier, clamped below kMaxFrequency / 2
    p.fpass(8, 4)
    p.fconst(12, F_MAX * 0.5)
    p.fop(8, 8, "MIN", 12)
    _step(p, D_GF0I, S_GF0, 8)
    # f1 = NoteToFrequency(24 + 84 timbre); ratio = 2^((-24 + 48 harm) / 12)
    _mulk(p, 6, 6, 84.0 / 12.0)
    _addk(p, 6, 6, (24.0 - 69.0) / 12.0)
    PM.exp2(p, L.perc, 6, 6)
    _mulk(p, 6, 6, 440.0 / SR)
    _mulk(p, 5, 5, 4.0)
    _addk(p, 5, 5, -2.0)
    PM.exp2(p, L.perc, 5, 5)
    p.fop(5, 5, "*", 6)
    p.fconst(12, F_MAX)
    p.fop(6, 6, "MIN", 12)
    _step(p, D_GF1AI, S_GF1A, 6)
    p.fop(5, 5, "MIN", 12)
    _step(p, D_GF1BI, S_GF1B, 5)
    # the DC blocker at 0.3 f0 (FREQUENCY_DIRTY): g = f (pi + a f^2), gi = 1 / (1 + g)
    _mulk(p, 4, 4, 0.3)
    p.fop(5, 4, "*", 4)
    _mulk(p, 5, 5, 3.736e-01 * math.pi ** 3)
    _addk(p, 5, 5, math.pi)
    p.fop(5, 5, "*", 4)
    _sv(p, D_GG, 5)
    _addk(p, 5, 5, 1.0)
    recip(p, 5, 5)
    _sv(p, D_GGI, 5)


def _carrier_sub(p: Prog) -> None:
    """F15 = the grainlet carrier's shaped phase (Carrier before its sine) for phase F8,
    shape F9 (GrainletOscillator::Carrier). Clobbers R0, R1, R8-R10, R13, R14."""
    def body():
        _mulk(p, 9, 9, 3.0, t=13)
        p.trunc(0, 9)
        p.iconst(13, 0)
        p.float_(10, 0, 13)
        p.fop(9, 9, "-", 10)                     # shape_fractional
        p.fconst(13, 1.0)
        p.fop(10, 13, "-", 9)                    # t
        p.fop(14, 10, "*", 10)
        p.fop(14, 14, "*", 10)                   # t^3
        p.iconst(1, 0)

        def s0():
            _mulk(p, 14, 14, 15.0, t=13)
            _addk(p, 14, 14, 1.0, t=13)
            p.fop(8, 8, "*", 14)
            p.fconst(13, 1.0)
            p.fop(8, 8, "MIN", 13)
            _addk(p, 15, 8, 0.75, t=13)

        def s1():
            _mulk(p, 14, 14, 0.499, t=13)
            _addk(p, 14, 14, 0.001, t=13)        # breakpoint

            def before():
                _pm()._recip_inline(p, 10, 14, 13)
                p.fop(8, 8, "*", 10)
                _mulk(p, 15, 8, 0.5, t=13)

            def after():
                p.fop(8, 8, "-", 14)
                p.fconst(13, 1.0)
                p.fop(14, 13, "-", 14)
                p.fpass(9, 14)
                _pm()._recip_inline(p, 10, 9, 13)
                p.fop(8, 8, "*", 10)
                _mulk(p, 8, 8, 0.5, t=13)
                _addk(p, 15, 8, 0.5, t=13)
            p.if_(8, "LT", 14, before, after)
            _addk(p, 15, 15, 0.75, t=13)

        def s2():
            p.fop(14, 9, "*", 9)
            p.fop(14, 14, "*", 9)                # shape_fractional^3
            _mulk(p, 14, 14, 14.5, t=13)
            _addk(p, 14, 14, 0.5, t=13)
            p.fop(8, 8, "*", 14)
            _addk(p, 15, 8, 0.25, t=13)
            p.fconst(13, 0.75)
            p.fop(15, 15, "MIN", 13)
        p.if_(0, "EQ", 1, s0, lambda: (p.iconst(1, 1), p.if_(0, "EQ", 1, s1, s2, kind="i")), kind="i")
    p.call("pl_carrier", body)


def _carrier(p: Prog, L: C.Layout, d: int, ph: int, sh: int) -> None:
    """Fd = Carrier(Fph, Fsh) = (sin(2 pi shaped) + 1) / 4. Clobbers R0-R3, R8-R10, R12-R15,
    I1, I12."""
    if ph != 8:
        p.fpass(8, ph)
    if sh != 9:
        p.fpass(9, sh)
    _carrier_sub(p)
    sinw(p, L, d, 15)
    _addk(p, d, d, 1.0)
    _mulk(p, d, d, 0.25)


def _blep(p: Prog, dd: int) -> None:
    """this += d ThisBlep(rt), next += d NextBlep(rt): d in Fdd, rt at T_RT. Clobbers R4-R6."""
    _ld(p, 4, T_RT)
    p.fop(5, 4, "*", 4)
    _mulk(p, 5, 5, 0.5)
    p.fop(5, 5, "*", dd)
    _ld(p, 6, T_THIS)
    p.fop(6, 6, "+", 5)
    _sv(p, T_THIS, 6)
    p.fconst(12, 1.0)
    p.fop(4, 12, "-", 4)
    p.fop(5, 4, "*", 4)
    _mulk(p, 5, 5, -0.5)
    p.fop(5, 5, "*", dd)
    _ld(p, 6, T_NXT)
    p.fop(6, 6, "+", 5)
    _sv(p, T_NXT, 6)


def _formant(p: Prog, L: C.Layout, d: int, fp: int, f1: int, k: float | None) -> None:
    """Fd = sin(fp + k f1) + bleed at T_CB (k None: sin(fp) + bleed). Clobbers as sinw, R4."""
    _ld(p, 4, fp)
    if k is not None:
        _ld(p, 5, f1)
        _ld(p, 6, T_RT)
        p.fconst(12, 1.0)
        p.fop(6, 12, "-", 6)
        p.fop(5, 5, "*", 6)
        p.fop(4, 4, "+", 5)
    sinw(p, L, d, 4)
    _ld(p, 4, T_CB)
    p.fop(d, d, "+", 4)


def _grain_reset(p: Prog, L: C.Layout) -> None:
    """The carrier's reset: rt = phase / f0; the two grainlets before (at 1 - rt) and after,
    their step through the poly-BLEP; the formants restart at rt f1."""
    _ld(p, 4, S_GCP)
    _ld(p, 5, T_F)
    recip(p, 5, 5)
    p.fop(4, 4, "*", 5)
    _sv(p, T_RT, 4)
    # before: shape and bleed at 1 - rt (subsample from the values before this sample's step)
    p.fconst(12, 1.0)
    p.fop(5, 12, "-", 4)
    _ld(p, 6, D_GCSI)
    p.fop(6, 6, "*", 5)
    _ld(p, 7, T_CS0)
    p.fop(6, 6, "+", 7)
    _ld(p, 7, D_GCBI)
    p.fop(7, 7, "*", 5)
    _ld(p, 8, T_CB0)
    p.fop(7, 7, "+", 8)
    _sv(p, T_CB, 7)
    p.fpass(9, 6)
    p.fconst(8, 1.0)
    _carrier(p, L, 10, 8, 9)
    _sv(p, T_CAR, 10)
    _ld(p, 7, T_CB)
    _addk(p, 7, 7, 1.0)
    recip(p, 7, 7)
    _sv(p, T_INV, 7)
    _formant_before(p, L)
    # after: Grainlet(0, 0, shape(1), bleed(1)) twice = 2 Carrier(0, s1) b1 / (1 + b1)
    _ld(p, 9, T_CS)
    p.fconst(8, 0.0)
    _carrier(p, L, 10, 8, 9)
    _ld(p, 7, D_GCBI)
    _ld(p, 8, T_CB0)
    p.fop(7, 7, "+", 8)                          # b1
    p.fop(10, 10, "*", 7)
    _addk(p, 7, 7, 1.0)
    recip(p, 7, 7)
    p.fop(10, 10, "*", 7)
    p.fop(10, 10, "+", 10)
    _ld(p, 11, T_OUT)                            # before (both)
    p.fop(10, 10, "-", 11)                       # the discontinuity
    _blep(p, 10)
    # the formants restart
    _ld(p, 4, T_RT)
    _ld(p, 5, S_GF1A)
    p.fop(5, 5, "*", 4)
    _sv(p, S_GFP0, 5)
    _ld(p, 5, S_GF1B)
    p.fop(5, 5, "*", 4)
    _sv(p, S_GFP1, 5)


def _formant_before(p: Prog, L: C.Layout) -> None:
    """T_OUT = the two grainlets before the reset: Carrier(1, s) (sin(fp + (1 - rt) f1) +
    b) / (1 + b), summed."""
    _formant(p, L, 10, S_GFP0, S_GF1A, 1.0)
    _sv(p, T_OUT, 10)
    _formant(p, L, 10, S_GFP1, S_GF1B, 1.0)
    _ld(p, 11, T_OUT)
    p.fop(10, 10, "+", 11)
    _ld(p, 11, T_CAR)
    p.fop(10, 10, "*", 11)
    _ld(p, 11, T_INV)
    p.fop(10, 10, "*", 11)
    _sv(p, T_OUT, 10)


def _grain_sample(p: Prog, L: C.Layout) -> None:
    """One sample of both grainlets, summed, through the DC blocker, stored at I4."""
    _ld(p, 0, S_GCS)
    _sv(p, T_CS0, 0)
    _ld(p, 0, S_GCB)
    _sv(p, T_CB0, 0)
    _interp(p, 4, S_GF0, D_GF0I)
    _sv(p, T_F, 4)
    _interp(p, 5, S_GF1A, D_GF1AI)
    _interp(p, 5, S_GF1B, D_GF1BI)
    # the shape's and bleed's Next (the reset's subsamples read T_CS0, T_CB0)
    _ld(p, 5, T_CS0)
    _ld(p, 11, D_GCSI)
    p.fop(5, 5, "+", 11)
    _sv(p, T_CS, 5)
    _ld(p, 5, S_GNX)
    _sv(p, T_THIS, 5)
    p.fconst(0, 0.0)
    _sv(p, T_NXT, 0)
    _ld(p, 6, S_GCP)
    p.fop(6, 6, "+", 4)
    _sv(p, S_GCP, 6)
    p.fconst(12, 1.0)

    def reset():
        p.fop(6, 6, "-", 12)
        _sv(p, S_GCP, 6)
        _grain_reset(p, L)

    def run():
        for fp, f1 in ((S_GFP0, S_GF1A), (S_GFP1, S_GF1B)):
            _ld(p, 7, fp)
            _ld(p, 8, f1)
            p.fop(7, 7, "+", 8)
            _pm().wrap1(p, 7)
            _sv(p, fp, 7)
    p.if_(6, "GE", 12, reset, run)
    # the shape's and bleed's Next, then the grainlets at this sample
    _interp(p, 9, S_GCS, D_GCSI)
    _interp(p, 7, S_GCB, D_GCBI)
    _sv(p, T_CB, 7)
    _addk(p, 7, 7, 1.0)
    recip(p, 7, 7)
    _sv(p, T_INV, 7)
    _ld(p, 8, S_GCP)
    _carrier(p, L, 10, 8, 9)
    _sv(p, T_CAR, 10)
    _formant(p, L, 10, S_GFP0, S_GF1A, None)
    _sv(p, T_OUT, 10)
    _formant(p, L, 10, S_GFP1, S_GF1B, None)
    _ld(p, 11, T_OUT)
    p.fop(10, 10, "+", 11)
    _ld(p, 11, T_CAR)
    p.fop(10, 10, "*", 11)
    _ld(p, 11, T_INV)
    p.fop(10, 10, "*", 11)
    _ld(p, 11, T_NXT)
    p.fop(10, 10, "+", 11)
    _sv(p, S_GNX, 10)
    # the DC blocker: lp = (g x + s) gi; s = g (x - lp) + lp; out x - lp
    _ld(p, 4, T_THIS)
    _ld(p, 5, D_GG)
    p.fop(6, 5, "*", 4)
    _ld(p, 7, S_GDC)
    p.fop(6, 6, "+", 7)
    _ld(p, 7, D_GGI)
    p.fop(6, 6, "*", 7)                          # lp
    p.fop(7, 4, "-", 6)                          # x - lp: the output
    p.fop(8, 5, "*", 7)
    p.fop(8, 8, "+", 6)
    _sv(p, S_GDC, 8)
    p.stpost(4, 7)


def _grain_half(p: Prog, L: C.Layout) -> None:
    _grain_params(p, L)
    p.loop(L.W["n4"], HALF, lambda: _grain_sample(p, L))


def model_of(knob: int) -> int:
    """MODL's knob -> the model (the page's choice: knob x N >> 7)."""
    return (knob * N_MODELS) >> 7


def knob_of(model: int) -> int:
    """the smallest knob that chooses MODEL"""
    return next(k for k in range(128) if model_of(k) == model)


def half(p: Prog, L: C.Layout) -> None:
    """16 samples at I4: the model MODL chooses (the choice, knob x N >> 7, as the page's). A
    model other than WS and GRAIN starts (its init) when it is chosen; the trigger is this half's."""
    C.knob(p, 0, 6)
    p.iconst(1, N_MODELS)
    p.mul_ssi(0, 0, 1)
    p.lsh(0, 0, -7)
    _ld(p, 1, K.S_LAST)

    def change():
        _sv(p, K.S_LAST, 0)
        for k, E in enumerate(ENGINES):
            p.iconst(1, 2 + k)
            p.if_(0, "EQ", 1, lambda E=E: E.init(p, L), kind="i")
            _ld(p, 0, K.S_LAST)
        _limiter_init(p)
    p.if_(0, "NE", 1, change, kind="i")
    _ld(p, 0, K.S_LAST)
    arms = [lambda: _ws_half(p, L), lambda: _grain_half(p, L)] + [lambda E=E: E.half(p, L) for E in ENGINES]

    def chain(k):
        if k == len(arms) - 1:
            arms[k]()
            return
        p.iconst(1, k)
        p.if_(0, "EQ", 1, arms[k], lambda: chain(k + 1), kind="i")
    chain(0)
    if POST and ENGINES:
        _ld(p, 0, K.S_LAST)
        p.iconst(1, 2)
        p.if_(0, "GE", 1, lambda: _post(p, L), kind="i")
    p.iconst(0, 0)
    _sv(p, K.S_TRIG, 0)


def _limiter_init(p: Prog) -> None:
    """the OUT stage's limiter as Plaits' Init / Reset (a change of engine): its peak 0.5.
    Clobbers R0."""
    p.fconst(0, 0.5)
    C.vws(p, "i1", 0)


def _post(p: Prog, L: C.Layout) -> None:
    """Plaits' OUT stage on the half just rendered (the 16 words before I4), the model's out_gain.
    Clobbers R0-R15, I1."""
    p.e("R0 = I4;")
    if p.run:
        p.r[0] = p.i[4]
    p.iconst(12, -4 * HALF)
    p.iop(0, 12, "+", 0)
    p.seti(1, 0)
    _ld(p, 0, K.S_LAST)
    p.fconst(5, 0.8)
    for k, E in enumerate(ENGINES):
        p.iconst(1, 2 + k)
        p.if_(0, "EQ", 1, lambda g=OUT_GAIN[E.MODEL]: p.fconst(5, g), kind="i")
    p.fconst(12, 0.0)

    def limit():                                 # stmlib Limiter::Process(-gain)
        p.fconst(12, 0.0)
        p.fop(5, 12, "-", 5)

        def one():
            p.ldi(4, 0, 1)
            p.fop(4, 4, "*", 5)                  # s
            _abs(p, 6, 4)
            C.vw(p, 7, "i1")                     # peak
            p.fop(6, 6, "-", 7)                  # error
            p.fconst(8, 0.00002)
            p.fconst(12, 0.0)
            p.if_(6, "GT", 12, lambda: p.fconst(8, 0.05))
            p.fop(6, 8, "*", 6)
            p.fop(7, 7, "+", 6)
            C.vws(p, "i1", 7)
            p.fconst(12, 1.0)
            p.if_(7, "GT", 12, lambda: (recip(p, 7, 7), p.fop(4, 4, "*", 7)))
            _mulk(p, 4, 4, 0.8)
            _clamp(p, 4, -1.0, 1.0)              # Clip16, as every OUT (the limiter's attack lets a jump through)
            p.stpost(1, 4)
        p.loop(L.W["n4"], HALF, one)

    def fixed():                                 # the gain, Clip16's +-1
        def one():
            p.ldi(4, 0, 1)
            p.fop(4, 4, "*", 5)
            _clamp(p, 4, -1.0, 1.0)
            p.stpost(1, 4)
        p.loop(L.W["n4"], HALF, one)
    p.if_(5, "LT", 12, limit, fixed)
