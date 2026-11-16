"""PLAITS: Mutable Instruments Plaits' engines as a Monomachine-style machine (docs/plaits.md):
WAVESHAPING (WS) here, the others in their own modules (dnfw.mnm.plaits_*). A port of Emilie
Gillet's C++ (github.com/pichenettes/eurorack, plaits/dsp/engine/waveshaping_engine.cc,
dsp/oscillator/oscillator.h; MIT, THIRD-PARTY.md). GRANULAR FORMANT (GRAIN) was here until
2026-11-09 (removed for the inserts' DSP room; its MODL choice is RETIRED and plays WS).

One voice per track at 44.1 kHz (PERC's stream; every frequency is Hz / 44100, so a note
sounds at its pitch), 16-sample halves as Plaits' blocks (its parameter interpolators run
over 16 samples, not 12). Only Plaits' OUT is rendered (the track is mono); its LPG and AUX
are left to the DN2's filter and amp. The oscillators are never reset on a trig: Plaits'
engines run on (a reset per note is what clicked in the Digitakt II ports).

- WS: a band-limited slope oscillator (integrated poly-BLEP), morph = its pulse width; the
  waveshaper (HARM crossfades Plaits' five Tides tables), the wavefolder (TIMB: the fold
  table, Hermite-interpolated), both tamed by the pitch as Plaits does.

Sines are PERC's sine table (256 a turn, linear) where Plaits' is 512; exp2 PERC's table; a
division PERC's reciprocal. The tables (WS's five shapes, the fold) ship in zpack
(dnfw.mnm.tables, Q23).

Parameters: HARM TIMB MORP --- --- FINE TUNE MODL (2026-11-11, the User: the engine on page 1 knob H on every
machine with engines, as MACHINEDRUM's TYPE; MODL and TUNE swapped places, old projects not converted).
"""

from __future__ import annotations

from ...mnm import core as C
from . import plk as K
from . import plaits_va, plaits_fm, plaits_add, plaits_swarm, plaits_noise, plaits_part, plaits_string, plaits_modal, plaits_bd, plaits_sd, plaits_hh
from ...perc import guard as G
from ...perc.dsl import Prog

NAME, ID = "PLAITS", 65
PNAMES = ("HARM", "TIMB", "MORP", "---", "---", "FINE", "TUNE", "MODL")   # FINE 2026-11-09; MODL on H 2026-11-11
TUNE_K, MODL_K = 6, 7                                                      # their places (G, H)
WS, RETIRED = range(2)
# 2026-11-09: Plaits' other engines, each its own module (dnfw.engines.plaits.plk their common ground), after
# WS and the retired choice in MODL's choices
ENGINES = (plaits_va, plaits_fm, plaits_add, plaits_swarm, plaits_noise, plaits_part, plaits_string, plaits_modal, plaits_bd, plaits_sd, plaits_hh)
# 2026-11-09 (the User): GRAN (Plaits' granular formant) removed for the CHOR and WIDE inserts'
# DSP room. Its choice stays, RETIRED (an empty name): MODL keeps its 13 knob slots, so every
# saved knob and p-lock keeps its engine; the retired one plays WS, the page shows it as WS and
# steps past it (pages.MNM_RETIRED, md_page.c / page.c / fmt.c)
MODELS = ("WS", "") + tuple(E.MODEL for E in ENGINES)   # the page shows four characters
N_MODELS = len(MODELS)
# 2026-11-09: Plaits' OUT stage after each of those engines (voice.cc RegisterInstance's out_gain,
# voice.h ChannelPostProcessor): a fixed gain, the result clipped to +-1 (Plaits' Clip16), or, for a
# negative figure, stmlib's Limiter with that pre-gain (its peak follower, x 0.8), then clipped too. The raw engines go
# well past +-1 (PART to 8, MDAL to 3.6). WS stays as it was, without it.
OUT_GAIN = {"VA": 0.8, "FM": 0.6, "ADD": 0.8, "SWRM": -3.0, "NOIS": -1.0, "PART": -2.0, "STRG": -1.0,
            "MDAL": -1.0, "BD": 0.8, "SD": 0.8, "HH": 0.8}
POST = True                                     # False: the raw engines (the references' comparisons)
DEFAULTS = (64, 64, 64, 0, 0, 64, 64, 0)

SR = 44100.0
F_MAX, F_MIN = 0.25, 0.000001                    # plaits::kMaxFrequency, kMinFrequency
HALF = 16

# state (slot words S0..): WS's oscillator and interpolators, then GRAIN's (unused since 2026-11-09,
# kept so the layout and WS stay bit-identical)
(S_WPH, S_WNX, S_WHI, S_WF, S_WPW, S_WSH, S_WGN,
 S_GCP, S_GF0, S_GCS, S_GCB, S_GFP0, S_GFP1, S_GF1A, S_GF1B, S_GNX, S_GDC, S_BASE) = range(18)
# per half (slot words): the interpolators' steps, the DC blocker's g and gi, the model
(D_WFI, D_WPWI, D_WSHI, D_WGNI, D_GF0I, D_GCSI, D_GCBI, D_GF1AI, D_GF1BI, D_GG, D_GGI,
 D_MOD) = range(18, 30)
# per sample scratch (slot words)
(T_UP, T_DN, T_THIS, T_NXT, T_F, T_W, T_OUT, T_RT, T_CS, T_CB, T_CAR, T_INV, T_CS0,
 T_CB0) = range(30, 44)


def _pm():
    from ...perc import machines as PM
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
    its pulse width 0.5; the rest at 0."""
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
    C.par(p, 2, TUNE_K)                          # knob / 128, exactly
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
    _sv(p, K.S_NOTE, 1)                          # the note, for the engines after WS
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


def model_of(knob: int) -> int:
    """MODL's knob -> the model (the page's choice: knob x N >> 7)."""
    return (knob * N_MODELS) >> 7


def knob_value(knob: int) -> int | None:
    """2026-11-12: the smallest value of MODL's record (page 1 H, 0..TOP) whose knob, as the page shows it
    (v / TOP x 127, rounded: dnfw.perc.live.knob_word), is KNOB; None for a knob no value reaches (the record has
    TOP + 1 values for 128 knobs)."""
    from ...perc import machines as PM
    _rid, _slot, _lo, top = PM.PARAMS[MODL_K]
    return next((v for v in range(top + 1) if int(v / top * 127 + 0.5) == knob), None)


def dsp_model(value: int) -> int:
    """the model the DSP plays for MODL's record value VALUE: dnfw.perc.program's param (v x 1/TOP, float32),
    dnfw.md.voice.inputs' knob (trunc(x 127 + 0.5), the page's own rounding; the Monomachine host passes it on
    as knob / 128), then half's choice (knob x N >> 7)"""
    from ...perc import machines as PM
    from ...perc.dsl import f32
    _rid, _slot, _lo, top = PM.PARAMS[MODL_K]
    x = f32(f32(float(value)) * f32(1.0 / top))
    knob = min(max(int(f32(f32(x * 127.0) + 0.5)), 0), 127)
    return (knob * N_MODELS) >> 7


def knob_of(model: int) -> int:
    """the smallest knob that chooses MODEL and that the unit can hold: a value of MODL's record shows it on the
    page and the DSP plays MODEL for that value. 2026-11-12: was the smallest knob of the page's choice alone,
    which for ADD (40) no value reaches (the harness's nearest value plays FM: every check through knob_of measured
    FM twice and never ADD)."""
    return next(k for k in range(128) if model_of(k) == model and (v := knob_value(k)) is not None
                and dsp_model(v) == model)


def half(p: Prog, L: C.Layout) -> None:
    """16 samples at I4: the model MODL chooses (the choice, knob x N >> 7, as the page's). A
    model other than WS starts (its init) when it is chosen; the trigger is this half's. Choice 1
    (GRAN until 2026-11-09, RETIRED) plays WS."""
    C.knob(p, 0, MODL_K)
    p.iconst(1, N_MODELS)
    p.mul_ssi(0, 0, 1)
    p.lsh(0, 0, -7)
    _ld(p, 1, K.S_LAST)

    def change():
        _sv(p, K.S_LAST, 0)
        G.fresh(p, 12)                           # 2026-11-09: a start block for the frame guard
        p.iconst(2, 0)
        _sv(p, K.S_CLR, 2)                       # no clear pending (an engine's init may defer one)
        for k, E in enumerate(ENGINES):
            p.iconst(1, 2 + k)
            p.if_(0, "EQ", 1, lambda E=E: E.init(p, L), kind="i")
            _ld(p, 0, K.S_LAST)
        _limiter_init(p)
    p.if_(0, "NE", 1, change, kind="i")
    # the arms by choice; WS takes choices 0 and RETIRED (<= 1)
    arms = [lambda: _ws_half(p, L)] + [lambda E=E: E.half(p, L) for E in ENGINES]

    def chain(k):
        if k == len(arms) - 1:
            arms[k]()
            return
        if k == 0:
            p.iconst(1, RETIRED)
            p.if_(0, "LE", 1, arms[0], lambda: chain(1), kind="i")
            return
        p.iconst(1, 1 + k)
        p.if_(0, "EQ", 1, arms[k], lambda: chain(k + 1), kind="i")

    def render():
        _ld(p, 0, K.S_LAST)
        chain(0)
        if POST and ENGINES:
            _ld(p, 0, K.S_LAST)
            p.iconst(1, 2)
            p.if_(0, "GE", 1, lambda: _post(p, L), kind="i")
        p.iconst(0, 0)
        _sv(p, K.S_TRIG, 0)

    def clearing():                              # 2026-11-09: a deferred clear (plk.defer_clear):
        K.clear_half(p, L, 5)                    # silent, the trigger kept for the engine's start
        tails = [(2 + k, E) for k, E in enumerate(ENGINES) if hasattr(E, "init_tail")]
        if tails:
            def done():
                for m, E in tails:
                    _ld(p, 0, K.S_LAST)
                    p.iconst(1, m)
                    p.if_(0, "EQ", 1, lambda E=E: E.init_tail(p, L), kind="i")
            _ld(p, 0, K.S_CLR)
            p.ifz(0, "EQ", done)
    _ld(p, 0, K.S_CLR)
    p.ifz(0, "GT", clearing, render)


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
        # 2026-11-10 (poly16): the peak, -gain and the constants in registers through the half,
        # the attack's choice a conditional move on the error's own sign (as COMP(error, 0)):
        # the same operations in the same order
        p.fconst(12, 0.0)
        p.fop(5, 12, "-", 5)
        C.vw(p, 7, "i1")                         # peak
        p.fconst(9, 0.05)
        p.fconst(10, 1.0)
        p.fconst(11, -1.0)
        p.fconst(3, 0.8)

        def one():
            p.ldpost(4, 1)
            p.fop(4, 4, "*", 5)                  # s
            p.fabs_(6, 4)                        # (|s|, as _abs: 0 - s, MAX: the same value)
            p.fconst(8, 0.00002)
            p.fop(6, 6, "-", 7)                  # error
            p.fop_if("GT", 8, 9, "PASS")
            p.fop(6, 8, "*", 6)
            p.fop(7, 7, "+", 6)
            p.if_(7, "GT", 10, lambda: (C.vws(p, "i1", 7), recip(p, 14, 7), p.fop(4, 4, "*", 14), C.vw(p, 7, "i1")))
            p.fop(4, 4, "*", 3)
            p.fop(4, 4, "MAX", 11)
            p.fop(4, 4, "MIN", 10)               # Clip16, as every OUT (the limiter's attack lets a jump through)
            p.sti(-1, 1, 4)
        p.loop_r(2, HALF, one)                   # (recip clobbers R12-R15)
        C.vws(p, "i1", 7)

    def fixed():                                 # the gain, Clip16's +-1
        p.fconst(11, -1.0)
        p.fconst(10, 1.0)

        def four():
            for k in range(4):
                p.ldpost(4, 1)
                p.fop(4, 4, "*", 5)
                p.fop(4, 4, "MAX", 11)
                p.fop(4, 4, "MIN", 10)
                p.sti(-1, 1, 4)
        p.loop_r(15, HALF // 4, four)
    p.if_(5, "LT", 12, limit, fixed)
