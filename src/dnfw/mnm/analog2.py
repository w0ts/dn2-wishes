# SPDX-License-Identifier: AGPL-3.0-or-later
"""ANALOG2: two band-limited oscillators, a swarm of copies of the first, hard sync, noise, drive
and ANALOG 2's filters (SVF, LADR, OTA, DIOD, MS20 x LP12 LP24 BP HP NOTCH), ported from Optimist
(GPL-3.0-only, firmware/src/engines/analog/eng_analog.c, eng_analog2.c and a2_models.c), as a
Monomachine-style machine (THIRD-PARTY.md). The filters are dnfw.a2f.models, the filter machines'.

One voice a track at 44.1 kHz (PERC's stream, Optimist's own rate), Optimist's 32-sample block as
the DN2's (its control in `pitch`, once a block; two 16-sample halves). A half: the swarm's copies
of osc 1, osc 1, osc 2 (free, or hard-synced to osc 1), noise, drive, the filter, the soft knee
(16000/32768) x 2. Levels as Optimist's "half scale": 1.0 is its 32768, so one oscillator at MIX 0
plays +-1.0 out (the square +-0.5, Optimist's).

Parameters (page 1, knob / 128): WAVE (SAW SQR TRI SIN PWM: knob x 5 >> 7), DTN (osc 2's detune,
cents, Optimist's det_inc), MIX (osc 1 -> osc 2), NOIS, CUT, RES, DRV, KTR (Optimist's KTR, the
cutoff + KTR (note - 60) / 256 CUT units). Page 2 (`core.page2`, q0..q6 as 0..1; a choice is
min(n - 1, trunc(q n))): q0 SWRM (0..6 copies, 0 off), q1 SEMI (-24..+24 st, osc 2's interval),
q2 SDTN (the copies' spread, q x 127), q3 SYNC (ON for q >= 0.5), q4 WAV2 (=1 SAW SQR TRI SIN
PWM; 0 osc 1's), q5 DRFT (round(q x 127): Optimist's DRFT, 0 restarts the phases on a trig),
q6 FLT (model x 5 + mode, 25 choices: SVF LP12 .. MS20 NOTCH; 0 SVF LP12, ANALOG's).
Page 3 (2026-11-11, `core.page3`): r0 GLID, r1 GLTY (OFF RATE TIME), DRONE's mono legato glide on the
oscillators (dnfw.mnm.a2glide); OFF is its record's stock default, so older tracks play as before.

Against Optimist:
- Float32 for its Q15 integers; the phases and the increments stay 32-bit integers (a phase
  kept + 2^31, so FLOAT of it is the phase - 1/2). The increments: 2^((note - 69) / 12) x 440 Hz
  in float32 (Optimist's pitch_inc table to +-1 unit at the usual notes); DTN as det_inc (whole
  1/16 semitones, the rest fine_inc's truncated factor), DRFT's walk (super_drift) in integers
  as Optimist's, the noise (xorshift32) bit for bit.
- The poly-BLEPs as osc_saw's, in float (t = phase / increment); the square is two saws, so PWM
  is the square: its width came from ENV / LFO -> SHP, which the machine does not have (the DN2's
  LFOs move knobs). The sine: u (1 - u^2) Q(u^2), Q of degree 4 (3e-7; Optimist's 1024-point
  table). tanh in the drive and the knee: x P(x^2) on 0..2, degree 8 (4.5e-6; Optimist's
  TANH_Q15 interpolated, 6e-6), clamped at 2 as softclip.
- Hard sync as a2_sync, sample by sample: a look-ahead puts the restart's pre-correction on the
  sample before the wrap (the C's segments do it on b[i - 1] or at the block's end), the restart
  and its post-correction on the next. A trig that restarts the phases restarts osc 2 there too
  (the C finds osc 1's wrap at sample 0).
- The filters are the a2f port's (dnfw.a2f.models: float, its own approximations; ref.py lists
  them): the SVF ramps its coefficients from the last half's cutoff, the models are set at each
  half's end (a2_filter, a2m_block). The model's states are cleared when FLT changes model.
- No ENV2, no m->shape / m->cutoff / OSC2 / SDTN modulation (the DN2's LFOs and envelopes move
  the knobs); with SYNC, SEMI moves osc 2 (the sync interval). No FLT B.
- The swarm's CPU cap is a constant (MAX_COPIES; Optimist's voices_busy cap has no DN2 source).
- A trig: with DRFT 0 the phases restart (osc 1 and the spread at 0, osc 2 a quarter turn on),
  free otherwise; the filter's states and last cutoff go on (Optimist's retrigger keeps them).

The filters' words and mix tables (`ctx`): the words in the render scratch's XB (SID's phases,
free since 2026-11-08), the tables (`table_words`, not zeros) at TABLES_OFF in the Monomachine's
L2 scratch, which the coordinator loads.
"""

from __future__ import annotations

from . import a2glide as G
from . import core as C
from .tb303 import _exp2p
from ..a2f import models as M
from ..perc.dsl import Prog

NAME, ID = "ANALOG2", 68
PNAMES = ("WAVE", "DTN", "MIX", "NOIS", "CUT", "RES", "DRV", "KTR")
DEFAULTS = (0, 10, 64, 0, 90, 30, 0, 64)         # Optimist's ANALOG defaults
PNAMES2 = ("SWRM", "SEMI", "SDTN", "SYNC", "WAV2", "DRFT", "FLT")
# page 2's start as knobs 0..127 (dnfw.waverider.pages mnm_default: perc.live.knob_word; q ~ knob / 127):
# Optimist's SWRM 0, SEMI 0, SDTN 34, SYNC OFF, WAV2 =1, DRFT 0, FLT SVF LP12
DEFAULTS2 = (0, 64, 34, 0, 0, 0, 0)
# 2026-11-11: page 3, the glide (dnfw.mnm.a2glide). MACHINE SEL starts it OFF, GLID at Optimist's SLIDE_T (TIME_MS
# index 54, ~50 ms), so RATE or TIME glides at once
PNAMES3 = ("GLID", "GLTY")
DEFAULTS3 = (54, 0)
WAVES = ("SAW", "SQR", "TRI", "SIN", "PWM")
WAVES2 = ("=1",) + WAVES
FLTS = tuple(f"{m} {md}" for m in M.MODELS for md in M.MODES)

MAX_COPIES = 6                                   # the swarm's cap (a constant: no voices_busy here)
# the filter models emitted (the SVF always); a FLT choice of a model left out plays the SVF in its
# mode (Optimist's "a model not built: the SVF")
FILTER_MODELS = M.MODELS
TABLES_OFF = 0x3200                              # the mix tables in the Monomachine L2 scratch
SR = 44100.0
INC_K = 440.0 / SR * 2.0 ** 32                   # the increment of A4
COPY_PH = (0x2B7E1516, 0x9E3779B9, 0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A)
COPY_AT = (1, -1, 2, -2, 3, -3)
GC = 80 * 258                                    # A2_SWARM_GC: the copies' level, Q15
SDTN_K = 60 * 2367 * 16 / (127 * 3 * 1000)      # dinc's factor a SDTN unit
KNEE = 16000.0 / 32768.0
TOP15 = 32767.0 / 32768.0                        # softclip's and the sine's top
NONE = -1.0                                      # no last cutoff (a fresh voice)
HALF = 0x80000000
# sin(pi u) / (u (1 - u^2)) in u^2 (fitted, 3e-7), with the sine's sign and TOP15 folded in
SIN_Q = tuple(-c * TOP15 for c in (3.14159230309089, -2.0260895597297144, 0.5237673445980027,
                                   -0.07439094157966462, 0.005918106135584834))
# tanh(x) / x in x^2 on 0..2 (fitted, 4.5e-6), TOP15 folded in
TANH_P = tuple(c * TOP15 for c in (0.9999987523471627, -0.3332349530378557, 0.1325101073321532,
                                   -0.05139980898798015, 0.01773782644437922, -0.004831303440849461,
                                   0.0009141036195898637, -0.0001032153224941374, 5.152369914034383e-06))
N0 = (-1.0, -0.5, -1.0, 0.0)                     # a wave at phase 0 (SAW SQR TRI SIN)
HN = (-2.0, -1.0, 0.0, 0.0)                      # its own BLEP's view of a restart (a2_sync's hn)

# state (slot words S0..)
(S_Q0, S_Q1, S_SPR, S_NST, S_DRF, S_LC, S_MDL, S_SP, S_ST, S_FW, S_POST, S_V) = range(12)
S_Z = 12                                         # the filter's 4 states
K_A, K_C = 16, 23                                # the copies' steps and phases (osc 1 at 0), 7 each
S_END = 30
# per block (pitch -> the halves)
(D_INC1, D_INC2, D_DINC, D_NC, D_W1, D_W2, D_G1, D_GC, D_G2, D_SYNC, D_NZ, D_DRV, D_DW,
 D_GS, D_GA, D_GB, D_RES, D_MODE, D_MODEL, D_RI1, D_IF2, D_N0, D_HN, D_RI2, D_TH2) = range(S_END, S_END + 25)
D_END = S_END + 25
GW = G.Words(D_END)                              # the glide's words (2026-11-11), up to GW.END
assert GW.END <= C.K.NS


def ctx(L: C.Layout) -> M.Ctx:
    """the filters' words (render scratch XB) and mix tables (L2 scratch + TABLES_OFF)"""
    return M.Ctx(L.XB, L.scratch + TABLES_OFF, FILTER_MODELS)


def table_words() -> list[float]:
    """the mix tables' floats, as the DSP must hold them at TABLES_OFF"""
    return M.table_layout(FILTER_MODELS)[0]


def _ld(p: Prog, d: int, k: int) -> None:
    C.st(p, d, k)


def _sv(p: Prog, k: int, s: int) -> None:
    C.sts(p, k, s)


def _k(p: Prog, d: int, a: int, op: str, x: float) -> None:
    """Fd = Fa op x (x in R12)."""
    p.fconst(12, x)
    p.fop(d, a, op, 12)


def _ri(p: Prog, d: int, src: str) -> None:
    """Rd = I3 or I4 (an I register's value)."""
    p.e(f"R{d} = {src};")
    if p.run:
        p.r[d] = p.i[int(src[1])]


def _choice(p: Prog, d: int, a: int, n: int) -> None:
    """Rd = min(n - 1, trunc(Fa n)), Fa >= 0. Clobbers R12."""
    _k(p, d, a, "*", float(n))
    p.trunc(d, d)
    p.iconst(12, n - 1)
    p.iop(d, d, "MIN", 12)


def _fint(p: Prog, d: int, a: int) -> None:
    """Fd = the integer Ra as a float. Clobbers R12."""
    p.iconst(12, 0)
    p.float_(d, a, 12)


def exact(A: int, F: int, knobs, pre: int = 0) -> dict:
    """no Monomachine increments: ANALOG2 takes its pitch from VW pitch (pitch below)"""
    return {}


def init(p: Prog, L: C.Layout) -> None:
    """Every word 0 but the copies' constants, the noise's seed and 'no last cutoff'."""
    _ri(p, 0, "I3")
    p.iconst(12, p.ioff(3, 4 * (C.K.S0)))
    p.iop(0, 12, "+", 0)
    p.seti(2, 0)
    p.iconst(1, 0)
    p.loop(L.W["n5"], GW.END, lambda: p.stpost(2, 1))
    for k in range(1, 7):
        p.iconst(0, COPY_AT[k - 1])
        _sv(p, K_A + k, 0)
        p.iconst(0, COPY_PH[k - 1])
        _sv(p, K_C + k, 0)
    p.iconst(0, HALF)
    _sv(p, S_Q0, 0)
    _sv(p, S_Q1, 0)
    p.iconst(0, 0x1234567)
    _sv(p, S_NST, 0)
    p.fconst(0, NONE)
    _sv(p, S_LC, 0)


def _drift_amount(p: Prog, L: C.Layout, d: int) -> None:
    """Rd = DRFT, round(q5 x 127). Clobbers R12."""
    C.page2(p, L, d, 5)
    _k(p, d, d, "*", 127.0)
    _k(p, d, d, "+", 0.5)
    p.trunc(d, d)


def trig(p: Prog, L: C.Layout) -> None:
    """A note: DRFT 0 restarts the phases (osc 2 a quarter turn on; with SYNC, osc 1's wrap at the
    first sample restarts it), unless the note glides (a2glide: legato, as Optimist's LEGATO); otherwise
    nothing."""
    G.trig(p, L, GW)
    p.ipass(2, 0)                                # 1: this note glides
    _drift_amount(p, L, 0)
    p.ifz(2, "NE", lambda: p.iconst(0, 1))       # (DRFT's 0 test below then fails)

    def restart():
        p.iconst(0, HALF)
        _sv(p, S_Q0, 0)
        p.iconst(0, HALF + 0x40000000)
        _sv(p, S_Q1, 0)
        p.iconst(0, 0)
        _sv(p, S_SPR, 0)
    p.ifz(0, "EQ", restart)


def _inc(p: Prog) -> None:
    """R15 = the increment of F15 semitones from A4 (float32: 2^(x / 12) x INC_K, truncated), the
    note clamped to 0..127 15/16 (det_inc's clamp of pitch16 to 0..2047). Clobbers R0, R1, R12-R14,
    I12."""
    def body():
        _k(p, 15, 15, "MAX", -69.0)
        _k(p, 15, 15, "MIN", 2047.0 / 16.0 - 69.0)
        _k(p, 13, 15, "*", 1.0 / 12.0)
        _exp2p(p, 14, 13)
        _k(p, 14, 14, "*", INC_K)
        p.trunc(15, 14)
    p.call("a2inc", body)


def _noise_step(p: Prog, x: int) -> None:
    """Rx = xorshift32(Rx) (13, 17, 5). Clobbers R13, R14."""
    for n in (13, -17, 5):
        p.lsh(13, x, n)
        p.xor(x, x, 13, 14)


def _drift(p: Prog) -> None:
    """R6 = super_drift's return (1/4096 units) for DRFT R5 > 0; S_DRF, S_NST move on. Clobbers
    R0-R4, R6, R8, R12-R14."""
    _ld(p, 8, S_NST)
    _noise_step(p, 8)
    _sv(p, S_NST, 8)
    p.lsh(0, 8, -24)
    p.iconst(12, -128)
    p.iop(0, 12, "+", 0)
    p.mul_ssi(0, 0, 5)                           # (n - 128) drift
    p.iconst(12, 7)
    p.ifz(0, "LT", lambda: p.iop(0, 12, "+", 0))
    p.ash(0, 0, -3)                              # / 8, toward zero
    _ld(p, 8, S_DRF)
    p.iop(8, 8, "+", 0)
    p.ash(1, 8, -7)
    p.iop(8, 8, "-", 1)                          # d -= d >> 7
    _fint(p, 2, 5)
    _k(p, 2, 2, "*", 30.0 * 256.0 / 127.0)
    _k(p, 2, 2, "+", 1e-3)
    p.trunc(2, 2)                                # lim
    p.iop(8, 8, "MIN", 2)
    p.iconst(12, 0)
    p.iop(3, 12, "-", 2)
    p.iop(8, 8, "MAX", 3)
    _sv(p, S_DRF, 8)
    p.ash(4, 8, -8)
    p.iconst(12, 2367)
    p.mul_ssi(4, 4, 12)
    _fint(p, 6, 4)
    _k(p, 6, 6, "*", 1e-3)
    p.trunc(6, 6)                                # (d >> 8) 2367 / 1000, toward zero


def _fine(p: Prog, d: int, a: int, f: int, sub: bool = False) -> None:
    """Rd = Ra +- (Ra >> 12) Rf (fine_inc). Clobbers R12."""
    p.lsh(12, a, -12)
    p.mul_ssi(12, 12, f)
    if sub:
        p.iop(d, a, "-", 12)
    else:
        p.iop(d, 12, "+", a)


def _gains(p: Prog, L: C.Layout) -> None:
    """D_G1, D_G2, D_GC, D_NC, D_NZ, D_DRV, D_DW from MIX, SWRM, NOIS, DRV."""
    C.par(p, 1, 2)
    _k(p, 1, 1, "*", 128.0 * 258.0)              # m2 = MIX x 258 (Q15)
    _k(p, 2, 1, "*", 1.0 / 65536.0)
    _sv(p, D_G2, 2)                              # (m2 >> 1) / 32768
    p.fconst(3, 16384.0)
    p.fconst(12, 0.0)

    def g1():
        p.fconst(3, 32767.0)
        p.fop(3, 3, "-", 1)
        _k(p, 3, 3, "*", 0.5)
        p.trunc(3, 3)
        _fint(p, 3, 3)
    p.if_(1, "GT", 12, g1)                       # F3: g1 (Q15 units)
    C.page2(p, L, 4, 0)
    _choice(p, 4, 4, 7)
    p.iconst(12, MAX_COPIES)
    p.iop(4, 4, "MIN", 12)
    _sv(p, D_NC, 4)

    def swarm():
        _fint(p, 5, 4)
        _k(p, 5, 5, "*", GC / 32.0)
        _k(p, 15, 5, "+", 1024.0)
        M.recip(p)
        _k(p, 15, 15, "*", 32767.0 * 1024.0)
        p.trunc(5, 15)
        _fint(p, 5, 5)                           # cg
        _k(p, 6, 5, "*", GC / 32768.0)
        p.trunc(6, 6)
        _fint(p, 6, 6)
        p.fop(6, 6, "*", 3)
        _k(p, 6, 6, "*", 2.0 / 32768.0)
        p.trunc(6, 6)
        _fint(p, 6, 6)
        _k(p, 6, 6, "*", 1.0 / 32768.0)
        _sv(p, D_GC, 6)                          # gc
        p.fop(3, 3, "*", 5)
        _k(p, 3, 3, "*", 1.0 / 32768.0)
        p.trunc(3, 3)
        _fint(p, 3, 3)                           # g1 cg
    p.ifz(4, "NE", swarm)
    _k(p, 3, 3, "*", 1.0 / 32768.0)
    _sv(p, D_G1, 3)
    C.par(p, 1, 3)
    _k(p, 1, 1, "*", 128.0 * 100.0 / 32768.0)
    _sv(p, D_NZ, 1)
    C.par(p, 1, 6)
    _k(p, 2, 1, "*", 128.0 * 768.0 / 16384.0)
    _k(p, 2, 2, "+", 2.0)
    _sv(p, D_DRV, 2)                             # drive / 16384
    _k(p, 2, 1, "*", 128.0 * 258.0 / 32768.0)
    _sv(p, D_DW, 2)


def _waves(p: Prog, L: C.Layout) -> None:
    """D_W1, D_W2 (0..3: PWM plays the square), D_SYNC, D_N0, D_HN."""
    C.par(p, 0, 0)
    _choice(p, 1, 0, 5)
    C.page2(p, L, 0, 4)
    _choice(p, 2, 0, 6)
    p.iconst(12, -1)
    p.iop(2, 12, "+", 2)
    p.ifz(2, "LT", lambda: p.ipass(2, 1))        # =1: osc 1's
    for r in (1, 2):
        p.iconst(12, 4)
        p.if_(r, "EQ", 12, lambda r=r: p.iconst(r, 1), kind="i")
    _sv(p, D_W1, 1)
    _sv(p, D_W2, 2)
    p.fconst(3, N0[0])
    p.fconst(4, HN[0])
    for w in (1, 2, 3):
        p.iconst(12, w)
        p.if_(2, "EQ", 12, lambda w=w: (p.fconst(3, N0[w]), p.fconst(4, HN[w])), kind="i")
    _sv(p, D_N0, 3)
    _sv(p, D_HN, 4)
    C.page2(p, L, 0, 3)
    p.iconst(1, 0)
    _k(p, 0, 0, "-", 0.5)
    p.fconst(12, 0.0)
    p.if_(0, "GE", 12, lambda: p.iconst(1, 1))   # q >= 0.5: a two-way choice's ON (the page's rule)
    _sv(p, D_SYNC, 1)


def _filter_ctl(p: Prog, L: C.Layout) -> None:
    """D_GS, D_GA, D_GB (g at the last block's cutoff, halfway, this one's), D_RES, D_MODE,
    D_MODEL; a model change clears the states."""
    C.par(p, 0, 4)
    _k(p, 0, 0, "*", 128.0)
    C.vw(p, 1, "pitch")
    _k(p, 1, 1, "+", -60.0)
    C.par(p, 2, 7)
    p.fop(1, 1, "*", 2)
    _k(p, 1, 1, "*", 128.0 / 256.0)
    p.fop(0, 0, "+", 1)
    _k(p, 0, 0, "MAX", 0.0)
    _k(p, 0, 0, "MIN", 127.0)                    # cut
    _ld(p, 1, S_LC)
    p.fconst(12, 0.0)
    p.if_(1, "LT", 12, lambda: p.fpass(1, 0))    # c0
    _sv(p, S_LC, 0)
    p.fop(2, 1, "+", 0)
    _k(p, 2, 2, "*", 0.5)                        # halfway
    for c, w in ((1, D_GS), (2, D_GA), (0, D_GB)):
        p.fpass(15, c)
        M.g_of(p)
        _sv(p, w, 15)
    C.par(p, 0, 5)
    _k(p, 0, 0, "*", 128.0)
    _sv(p, D_RES, 0)
    C.page2(p, L, 0, 6)
    _choice(p, 1, 0, 25)
    _k(p, 0, 0, "*", 5.0)
    p.trunc(2, 0)
    p.iconst(12, 4)
    p.iop(2, 2, "MIN", 12)                       # the model
    p.lsh(12, 2, 2)
    p.iop(3, 12, "+", 2)                         # 5 x the model
    p.iop(1, 1, "-", 3)                          # the mode
    for k, m in enumerate(M.MODELS):
        if m not in FILTER_MODELS:
            p.iconst(12, k)
            p.if_(2, "EQ", 12, lambda: p.iconst(2, M.SVF), kind="i")
    _sv(p, D_MODE, 1)
    _sv(p, D_MODEL, 2)
    p.iconst(12, 1)
    p.iop(2, 12, "+", 2)
    _ld(p, 3, S_MDL)

    def change():
        _sv(p, S_MDL, 2)
        p.fconst(0, 0.0)
        for k in range(4):
            _sv(p, S_Z + k, 0)
    p.if_(2, "NE", 3, change, kind="i")


def pitch(p: Prog, L: C.Layout) -> None:
    """The block's control: the increments (DTN, SEMI, DRFT), the swarm's spread, the gains,
    the waves, the filter's cutoffs and choice."""
    G.pitch(p, L, GW)                            # 2026-11-11: the glide's pitch, GW.CUR
    _waves(p, L)
    _gains(p, L)
    _filter_ctl(p, L)
    _ld(p, 15, GW.CUR)
    _k(p, 15, 15, "+", -69.0)
    _inc(p)
    _sv(p, D_INC1, 15)
    _sv(p, D_INC2, 15)
    C.par(p, 4, 1)
    _k(p, 4, 4, "*", 128.0)                      # det, cents
    C.page2(p, L, 5, 1)
    _choice(p, 5, 5, 49)
    p.iconst(12, -24)
    p.iop(5, 12, "+", 5)
    _fint(p, 5, 5)                               # semi
    p.fconst(12, 0.0)

    def det():
        _k(p, 6, 4, "*", 0.16)
        _k(p, 6, 6, "+", 1e-3)
        p.trunc(6, 6)
        _fint(p, 6, 6)                           # d16
        _k(p, 7, 6, "*", -100.0)
        _k(p, 8, 4, "*", 16.0)
        p.fop(7, 8, "+", 7)                      # rem
        _k(p, 7, 7, "*", 2367.0 / 16000.0)
        _k(p, 7, 7, "+", 2e-5)
        p.trunc(9, 7)                            # its fine factor
        _k(p, 6, 6, "*", 1.0 / 16.0)
        p.fop(6, 6, "+", 5)
        _ld(p, 15, GW.CUR)
        p.fop(15, 15, "+", 6)
        _k(p, 15, 15, "+", -69.0)
        _inc(p)
        _fine(p, 15, 15, 9)
        _sv(p, D_INC2, 15)
    p.if_(4, "NE", 12, det, lambda: p.if_(5, "NE", 12, det))
    _drift_amount(p, L, 5)

    def drift():
        _drift(p)
        _ld(p, 8, D_INC1)
        _fine(p, 8, 8, 6)
        _sv(p, D_INC1, 8)
        _ld(p, 8, D_INC2)
        _fine(p, 8, 8, 6, sub=True)
        _sv(p, D_INC2, 8)
    p.ifz(5, "NE", drift)
    # the copies' spread a sample, and the reciprocals the halves use
    p.iconst(0, 0)
    _ld(p, 1, D_NC)

    def spread():
        C.page2(p, L, 2, 2)
        _k(p, 2, 2, "*", 127.0 * SDTN_K)
        p.trunc(2, 2)
        _ld(p, 3, D_INC1)
        p.lsh(3, 3, -16)
        p.mul_ssi(0, 3, 2)
    p.ifz(1, "NE", spread)
    _sv(p, D_DINC, 0)
    p.iconst(12, -32)
    for src, ri, extra in ((D_INC1, D_RI1, None), (D_INC2, D_RI2, D_IF2)):
        _ld(p, 0, src)
        p.iconst(12, -32)
        p.float_(15, 0, 12)
        if extra is not None:
            _sv(p, extra, 15)
            p.fconst(12, 0.5)
            p.fop(1, 12, "-", 15)
            _sv(p, D_TH2, 1)
        M.recip(p)
        _sv(p, ri, 15)


# the Monomachine scratch words the halves use (dnfw.mnm.core SC_WORDS: the removed machines')
WN = {"bv": "bv", "i3": "x0", "jobs": "n4", "job": "inner", "ri1": "minc", "if2": "inc", "n0": "x1",
      "hn": "fd", "g2": "g"}


# -- the oscillators ---------------------------------------------------------------------------
def _saw(p: Prog, dst: int, f: int, t: int, thr: int, rinc: int, half: int | None, one: int | None) -> None:
    """Fdst = osc_saw at the phase Ff (- 1/2): 2 f, less its poly-BLEP when |f| > thr. Clobbers Ft
    (and R12 when half / one are None)."""
    p.fop(dst, f, "+", f)
    M.fabs(p, t, f)

    def blep():
        if half is None:
            p.fconst(12, 0.5)
        p.fop(t, 12 if half is None else half, "-", t)
        p.fop(t, t, "*", rinc)
        if one is None:
            p.fconst(12, 1.0)
        p.fop(t, 12 if one is None else one, "-", t)
        p.fop(t, t, "*", t)
        p.ifz(f, "LT", lambda: p.fop(dst, dst, "+", t), lambda: p.fop(dst, dst, "-", t), kind="f")
    p.if_(t, "GT", thr, blep)


def _sin(p: Prog, dst: int, f: int, t: int, q=None, one: int | None = None) -> None:
    """Fdst = osc_sine at the phase Ff (- 1/2); Q's coefficients from the registers q (low order
    first) and 1.0 from Fone when given, else loaded. Clobbers Ff, Ft, R12."""
    p.fop(f, f, "+", f)                          # u = 2 f
    p.fop(t, f, "*", f)
    if q is None:
        p.fconst(dst, SIN_Q[-1])
    else:
        p.fpass(dst, q[-1])
    for k in range(len(SIN_Q) - 2, -1, -1):
        p.fop(dst, dst, "*", t)
        if q is None:
            _k(p, dst, dst, "+", SIN_Q[k])
        else:
            p.fop(dst, dst, "+", q[k])
    if one is None:
        p.fconst(12, 1.0)
    p.fop(t, 12 if one is None else one, "-", t)
    p.fop(t, t, "*", f)
    p.fop(dst, dst, "*", t)


def _wave_leaf(p: Prog) -> None:
    """F2 = wave R4 (0..3) at the phase F0 (- 1/2), BLEP'd past F7 with F6 = 1 / increment (F7
    >= 1/2: none). Keeps R4-R11, R15. Clobbers F0, F1, F3, F13, F14, R12, I12."""
    def body():
        def saw():
            _saw(p, 2, 0, 1, 7, 6, None, None)

        def sqr():
            saw()
            p.fconst(12, 0.5)
            p.ifz(0, "LT", lambda: p.fop(3, 0, "+", 12), lambda: p.fop(3, 0, "-", 12), kind="f")
            _saw(p, 14, 3, 1, 7, 6, None, None)
            p.fop(2, 2, "-", 14)
            _k(p, 2, 2, "*", 0.5)

        def tri():
            M.fabs(p, 1, 0)
            _k(p, 1, 1, "*", 4.0)
            p.fconst(12, 1.0)
            p.fop(2, 12, "-", 1)

        def sin():
            _sin(p, 2, 0, 1)
        _dispatch(p, 4, (saw, sqr, tri, sin))
    p.call("a2wv", body)


def _dispatch(p: Prog, r: int, arms) -> None:
    """arms[Rr] (the last for any other value). Clobbers R12."""
    if len(arms) == 1:
        arms[0]()
        return
    p.iconst(12, 0)
    p.if_(r, "EQ", 12, arms[0], lambda: _dispatch_from(p, r, arms, 1), kind="i")


def _dispatch_from(p: Prog, r: int, arms, k: int) -> None:
    if k == len(arms) - 1:
        arms[k]()
        return
    p.iconst(12, k)
    p.if_(r, "EQ", 12, arms[k], lambda: _dispatch_from(p, r, arms, k + 1), kind="i")


def _kernel(p: Prog, L: C.Layout) -> None:
    """b[0..15] += g x wave(phase): R8 the phase (+ 2^31), R9 the increment, F5 g, R4 the wave
    (0..3); b at W bv. Clobbers every register but R4, I0 (walks b), I12."""
    p.iconst(10, -32)
    p.float_(15, 9, 10)
    p.fconst(12, 0.5)
    p.fop(7, 12, "-", 15)                        # thr = 1/2 - increment
    M.recip(p)
    p.fpass(6, 15)                               # 1 / increment
    p.ld(0, L.W[WN["bv"]])
    p.seti(0, 0)
    p.fconst(3, 1.0)
    p.fconst(2, 0.5)

    def acc(v: int) -> None:
        p.ldi(13, 0, 0)
        p.fop(v, v, "*", 5)
        p.fop(13, 13, "+", v)
        p.stpost(0, 13)

    def saw():
        def one():
            p.float_(0, 8, 10)
            p.iop(8, 8, "+", 9)
            _saw(p, 1, 0, 14, 7, 6, 2, 3)
            acc(1)
        p.loop_r(11, M.N, one)

    def sqr():
        _k(p, 5, 5, "*", 0.5)
        p.iconst(15, HALF)

        def one():
            p.float_(0, 8, 10)
            p.iop(4, 8, "+", 15)
            p.float_(4, 4, 10)
            p.iop(8, 8, "+", 9)
            _saw(p, 1, 0, 14, 7, 6, 2, 3)
            _saw(p, 13, 4, 14, 7, 6, 2, 3)
            p.fop(1, 1, "-", 13)
            acc(1)
        p.loop_r(11, M.N, one)
        p.iconst(4, 1)                           # (R4 the wave again)

    def tri():
        p.fconst(2, 4.0)

        def one():
            p.float_(0, 8, 10)
            p.iop(8, 8, "+", 9)
            M.fabs(p, 1, 0)
            p.fop(1, 1, "*", 2)
            p.fop(1, 3, "-", 1)
            acc(1)
        p.loop_r(11, M.N, one)

    def sin():
        q = (2, 4, 6, 7, 15)
        for r, c in zip(q, SIN_Q):
            p.fconst(r, c)

        def one():
            p.float_(0, 8, 10)
            p.iop(8, 8, "+", 9)
            _sin(p, 1, 0, 14, q, 3)
            acc(1)
        p.loop_r(11, M.N, one)
    _dispatch(p, 4, (saw, sqr, tri, sin))


def _jobs(p: Prog, L: C.Layout) -> None:
    """the copies, osc 1, osc 2 when free: one kernel each"""
    W = L.W
    _ld(p, 0, D_NC)
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)                         # copies + osc 1
    _ld(p, 1, D_G2)
    _ld(p, 2, D_SYNC)
    p.fconst(12, 0.0)

    def osc2():
        p.ifz(2, "EQ", lambda: (p.iconst(12, 1), p.iop(0, 12, "+", 0)))
    p.if_(1, "NE", 12, osc2)
    p.st(W[WN["jobs"]], 0)
    p.iconst(0, 0)
    p.st(W[WN["job"]], 0)

    def job():
        p.ld(6, W[WN["job"]])
        _ld(p, 7, D_NC)

        def copy():                              # copy k = job + 1: osc 1 + a spr + c
            _ri(p, 0, "I3")
            p.iconst(12, p.ioff(3, 4 * (C.K.S0 + K_A + 1)))
            p.iop(0, 12, "+", 0)
            p.lsh(1, 6, 2)
            p.ipass(12, 0)
            p.iop(0, 12, "+", 1)
            p.seti(2, 0)
            p.ldi(1, 0, 2)                       # a
            p.ldi(2, K_C - K_A, 2)               # c
            _ld(p, 3, S_SPR)
            p.mul_ssi(3, 3, 1)
            _ld(p, 8, S_Q0)
            p.iop(8, 8, "+", 3)
            p.iop(8, 8, "+", 2)
            _ld(p, 3, D_DINC)
            p.mul_ssi(3, 3, 1)
            _ld(p, 9, D_INC1)
            p.iop(9, 9, "+", 3)
            _ld(p, 5, D_GC)
            _ld(p, 4, D_W1)

        def osc1():
            _ld(p, 8, S_Q0)
            _ld(p, 9, D_INC1)
            _ld(p, 5, D_G1)
            _ld(p, 4, D_W1)

        def osc2():
            _ld(p, 8, S_Q1)
            _ld(p, 9, D_INC2)
            _ld(p, 5, D_G2)
            _ld(p, 4, D_W2)
        p.if_(6, "LT", 7, copy, lambda: p.if_(6, "EQ", 7, osc1, osc2, kind="i"), kind="i")
        _kernel(p, L)
        p.ld(8, W[WN["job"]])
        p.iconst(12, 1)
        p.iop(8, 8, "+", 12)
        p.st(W[WN["job"]], 8)
    M.mloop(p, W[WN["jobs"]], job)


def _sync(p: Prog, L: C.Layout) -> None:
    """osc 2 hard-synced to osc 1 (a2_sync), sample by sample: S_SP a restart pending at this
    sample (S_ST its t, S_FW osc 2's phase then); the look-ahead finds osc 1's wrap before the
    next sample and pre-corrects this one."""
    W = L.W
    _ld(p, 8, S_Q0)
    _ld(p, 9, D_INC1)
    _ld(p, 10, S_Q1)
    _ld(p, 5, D_INC2)
    _ld(p, 4, D_W2)
    _ld(p, 6, D_RI2)
    _ld(p, 7, D_TH2)
    p.iconst(12, HALF)
    p.iop(15, 12, "+", 9)                        # osc 1 wrapped: its phase (+ 2^31) below this
    for w in (D_RI1, D_IF2, D_N0, D_HN, D_G2):   # (the loop's constants, as scratch words)
        _ld(p, 0, w)
        p.st(W[WN[_SW[w]]], 0)
    p.ld(0, W[WN["bv"]])
    p.seti(0, 0)

    def naive(f: int) -> None:
        """F2 = the wave at Ff without its BLEP. Keeps F7 (via its word)."""
        p.fpass(0, f)
        p.fconst(7, 1.0)
        _wave_leaf(p)
        _ld(p, 7, D_TH2)

    def jump(fw: int) -> None:
        """F2 = h = the wave at 0 - at Ffw"""
        naive(fw)
        p.ld(1, W[WN["n0"]])
        p.fop(2, 1, "-", 2)

    def caught() -> None:
        """osc 1 wrapped before this sample (R8 its phase + 2^31, R0 osc 2's): S_ST = t (of an
        increment), F3 = S_FW = osc 2's phase at the wrap, S_SP = 1. Clobbers R0, F1, F3, F13, R12."""
        p.iconst(12, -32)
        p.float_(3, 0, 12)
        p.iconst(12, HALF)
        p.iop(0, 12, "+", 8)
        p.iconst(12, -32)
        p.float_(1, 0, 12)
        p.ld(13, W[WN["ri1"]])
        p.fop(1, 1, "*", 13)                     # t
        _sv(p, S_ST, 1)
        p.ld(13, W[WN["if2"]])
        p.fop(13, 13, "*", 1)
        p.fop(3, 3, "-", 13)
        p.fconst(12, -0.5)
        p.if_(3, "LT", 12, lambda: _k(p, 3, 3, "+", 1.0))
        _sv(p, S_FW, 3)
        p.iconst(0, 1)
        _sv(p, S_SP, 0)

    # the half's first sample: osc 1 wrapped just before it (a2_sync's test at sample 0, with this
    # block's increment: a trig's restart, a fresh voice, a wrap the last half looked ahead to)
    p.iconst(0, 0)
    _sv(p, S_SP, 0)
    p.if_(8, "LT", 15, lambda: (p.ipass(0, 10), caught()), kind="i")

    def one():
        _ld(p, 0, S_SP)

        def restart():
            _ld(p, 1, S_FW)
            jump(1)
            p.ld(1, W[WN["hn"]])
            p.fop(2, 2, "-", 1)
            _ld(p, 1, S_ST)
            p.fconst(12, 1.0)
            p.fop(3, 12, "-", 1)
            p.fop(3, 3, "*", 3)
            p.fop(2, 2, "*", 3)
            _k(p, 2, 2, "*", -0.5)
            _sv(p, S_POST, 2)                    # -(h - hn) (1 - t)^2 / 2
            p.ld(3, W[WN["if2"]])
            p.fop(1, 1, "*", 3)
            _k(p, 1, 1, "*", 2.0 ** 32)
            p.trunc(10, 1)
            p.iconst(12, HALF)
            p.iop(10, 12, "+", 10)               # osc 2 at t increments
            p.iconst(0, 2)
            _sv(p, S_SP, 0)
        p.ifz(0, "NE", restart)
        p.iconst(12, -32)
        p.float_(0, 10, 12)
        _wave_leaf(p)
        _ld(p, 0, S_SP)

        def post():
            _ld(p, 1, S_POST)
            p.fop(2, 2, "+", 1)
            p.iconst(0, 0)
            _sv(p, S_SP, 0)
        p.iconst(12, 2)
        p.if_(0, "EQ", 12, post, kind="i")
        p.iop(8, 8, "+", 9)                      # osc 1's next sample

        def wraps():                             # osc 1 wraps before the next sample
            _sv(p, S_V, 2)
            p.iop(0, 10, "+", 5)
            caught()
            jump(3)
            _ld(p, 1, S_ST)
            p.fop(1, 1, "*", 1)
            p.fop(2, 2, "*", 1)
            _k(p, 2, 2, "*", 0.5)                # h t^2 / 2 on this sample
            _ld(p, 1, S_V)
            p.fop(2, 2, "+", 1)
        p.if_(8, "LT", 15, wraps, kind="i")
        p.ld(1, W[WN["g2"]])
        p.fop(2, 2, "*", 1)
        p.ldi(1, 0, 0)
        p.fop(1, 1, "+", 2)
        p.stpost(0, 1)
        p.iop(10, 10, "+", 5)
    p.loop_r(11, M.N, one)
    _sv(p, S_Q1, 10)


_SW = {D_RI1: "ri1", D_IF2: "if2", D_N0: "n0", D_HN: "hn", D_G2: "g2"}




def _tanh(p: Prog) -> None:
    """F15 = softclip's curve / 32768: tanh(clamp(x, -2, 2)) x 32767/32768 (an odd polynomial).
    Clobbers F12-F14, I12."""
    def body():
        _k(p, 15, 15, "MIN", 2.0)
        _k(p, 15, 15, "MAX", -2.0)
        p.fop(14, 15, "*", 15)
        p.fconst(13, TANH_P[-1])
        for c in TANH_P[-2::-1]:
            p.fop(13, 13, "*", 14)
            _k(p, 13, 13, "+", c)
        p.fop(15, 15, "*", 13)
    p.call("a2tp", body)


def _noise(p: Prog, L: C.Layout) -> None:
    """b += NOIS's noise (a2_noise: xorshift32, (n >> 17) - 16384)"""
    _ld(p, 5, D_NZ)
    p.fconst(12, 0.0)

    def run():
        _ld(p, 8, S_NST)
        p.iconst(10, -15)
        p.ld(0, L.W[WN["bv"]])
        p.seti(0, 0)

        def one():
            _noise_step(p, 8)
            p.lsh(13, 8, -17)
            p.iconst(12, -16384)
            p.iop(13, 12, "+", 13)
            p.float_(1, 13, 10)
            p.fop(1, 1, "*", 5)
            p.ldi(2, 0, 0)
            p.fop(2, 2, "+", 1)
            p.stpost(0, 2)
        p.loop_r(11, M.N, one)
        _sv(p, S_NST, 8)
    p.if_(5, "NE", 12, run)


def _drive(p: Prog, L: C.Layout) -> None:
    """DRV: b + dw (softclip(b drive) / 2 - b) (a2_drive)"""
    _ld(p, 6, D_DW)
    p.fconst(12, 0.0)

    def run():
        _ld(p, 5, D_DRV)
        p.ld(0, L.W[WN["bv"]])
        p.seti(0, 0)

        def one():
            p.ldi(1, 0, 0)
            p.fop(15, 1, "*", 5)
            _tanh(p)
            _k(p, 15, 15, "*", 0.5)
            p.fop(15, 15, "-", 1)
            p.fop(15, 15, "*", 6)
            p.fop(1, 1, "+", 15)
            p.stpost(0, 1)
        p.loop_r(11, M.N, one)
    p.if_(6, "NE", 12, run)


def _filter(p: Prog, L: C.Layout) -> None:
    """the filter (dnfw.a2f.models) in place over b: its words from the block's, the states at
    S_Z (cleared past 1e4 or NaN, as a2m_block); I3 kept round it (the models clobber it)"""
    X = ctx(L)
    W = L.W
    for src, w in ((D_GS, "gs"), (D_GA, "ge"), (D_RES, "res"), (D_MODE, "mode"), (D_MODEL, "model")):
        _ld(p, 0, src)
        p.st(X.C[w], 0)
    _ld(p, 0, D_GA)                              # the next half ramps on from here
    _sv(p, D_GS, 0)
    _ld(p, 0, D_GB)
    _sv(p, D_GA, 0)
    p.ld(0, W[WN["bv"]])
    p.st(X.C["buf"], 0)
    b3 = p.ibias.get(3)                          # the voice's I3 bias (shrink), put back with it below
    _ri(p, 0, "I3")
    p.st(W[WN["i3"]], 0)
    p.iconst(12, p.ioff(3, 4 * (C.K.S0 + S_Z)))
    p.iop(0, 12, "+", 0)
    p.st(X.C["zp"], 0)
    p.iconst(9, 0)
    for k in range(4):
        _ld(p, 0, S_Z + k)
        p.iconst(12, 0x7FFFFFFF)
        p.iop(0, 0, "AND", 12)
        p.iconst(12, 0x461C4000)                 # 1e4
        p.if_(0, "GE", 12, lambda: p.iconst(9, 1), kind="i")

    def clear():
        p.iconst(0, 0)
        for k in range(4):
            _sv(p, S_Z + k, 0)
    p.ifz(9, "NE", clear)
    M.half(p, X)
    p.ld(0, W[WN["i3"]])
    p.seti(3, 0, bias=b3)                        # the models point I3 at their own tables: the voice's biased one back


def _out(p: Prog, L: C.Layout) -> None:
    """b = 2 x soft_knee(b, 16000) (a2_out, before the amplitude)"""
    p.ld(0, L.W[WN["bv"]])
    p.seti(0, 0)
    p.fconst(5, KNEE)

    def one():
        p.ldi(1, 0, 0)
        M.fabs(p, 2, 1)

        def knee():
            p.fop(15, 2, "-", 5)
            p.fop(15, 15, "+", 15)
            _tanh(p)
            _k(p, 15, 15, "*", 0.5)
            p.fop(2, 5, "+", 15)
            p.ifz(1, "LT", lambda: (p.fconst(12, 0.0), p.fop(1, 12, "-", 2)), lambda: p.fpass(1, 2), kind="f")
        p.if_(2, "GT", 5, knee)
        p.fop(1, 1, "+", 1)
        p.stpost(0, 1)
    p.loop_r(11, M.N, one)


def half(p: Prog, L: C.Layout) -> None:
    """16 samples at I4 (I3 and I4 kept)."""
    W = L.W
    _ri(p, 0, "I4")
    p.st(W[WN["bv"]], 0)
    p.seti(0, 0)
    p.fconst(1, 0.0)
    p.loop_r(11, M.N, lambda: p.stpost(0, 1))
    _jobs(p, L)
    # osc 2 synced, or its phase moved on (a restart pending only while synced)
    _ld(p, 0, D_G2)
    _ld(p, 1, D_SYNC)
    p.fconst(12, 0.0)

    def free():
        _ld(p, 8, S_Q1)
        _ld(p, 9, D_INC2)
        p.lsh(9, 9, 4)
        p.iop(8, 8, "+", 9)
        _sv(p, S_Q1, 8)
        p.iconst(0, 0)
        _sv(p, S_SP, 0)
    p.if_(0, "NE", 12, lambda: p.ifz(1, "NE", lambda: _sync(p, L), free), free)
    for ph, inc in ((S_Q0, D_INC1), (S_SPR, D_DINC)):
        _ld(p, 8, ph)
        _ld(p, 9, inc)
        p.lsh(9, 9, 4)
        p.iop(8, 8, "+", 9)
        _sv(p, ph, 8)
    _noise(p, L)
    _drive(p, L)
    _filter(p, L)
    _out(p, L)
