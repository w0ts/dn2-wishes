# SPDX-License-Identifier: AGPL-3.0-or-later
"""ANALOG2: two band-limited oscillators, a swarm of copies of the first, hard sync, noise, drive
and ANALOG 2's filters (SVF, LADR, OTA, DIOD, MS20 x LP12 LP24 BP HP NOTCH), ported from Optimist
(GPL-3.0-only, firmware/src/engines/analog/eng_analog.c, eng_analog2.c and a2_models.c), as a
Monomachine-style machine (THIRD-PARTY.md). The filters are dnfw.engines.analog2.filters.models, the filter machines'.

One voice a track at 44.1 kHz (PERC's stream, Optimist's own rate), Optimist's 32-sample block as
the DN2's (its control in `pitch`, once a block; two 16-sample halves). A half: the swarm's copies
of osc 1, osc 1, osc 2 (free, or hard-synced to osc 1), noise, drive, the filter, x 2 (Optimist's
soft knee at 16000/32768 is gone since 2026-11-21: no limiter). Levels as Optimist's "half scale": 1.0 is its 32768, so one oscillator at MIX 0
plays +-1.0 out (the square +-0.5, Optimist's).

Parameters (page 1, knob / 128): WAVE (SAW SQR TRI SIN PWM: knob x 5 >> 7), DTN (osc 2's detune,
cents, Optimist's det_inc), MIX (osc 1 -> osc 2), NOIS, CUT, RES, DRV, KTR (Optimist's KTR, the
cutoff + KTR (note - 60) / 256 CUT units). Page 2 (`core.page2`, q0..q6 as 0..1; a choice is
min(n - 1, trunc(q n))): q0 SWRM (0..6 copies, 0 off), q1 SEMI (-24..+24 st, osc 2's interval),
q2 SDTN (the copies' spread, q x 127), q3 SYNC (ON for q >= 0.5), q4 WAV2 (=1 SAW SQR TRI SIN
PWM; 0 osc 1's), q5 DRFT (round(q x 127): Optimist's DRFT, 0 restarts the phases on a trig),
q6 FLT2 (model x 5 + mode, 25 choices: SVF LP12 .. MS20 NOTCH; 0 SVF LP12, ANALOG's), q7 WDTH (2026-11-11, TYPE's
record: the copies' stereo width, 0 mono).
Page 3 (2026-11-11, `core.page3`): r0 GLID, r1 GLTY (OFF RATE TIME), DRONE's mono legato glide on the
oscillators (dnfw.engines.analog2.a2glide); OFF is its record's stock default, so older tracks play as before.

Against Optimist:
- Float32 for its Q15 integers; the phases and the increments stay 32-bit integers (a phase
  kept + 2^31, so FLOAT of it is the phase - 1/2). The increments: 2^((note - 69) / 12) x 440 Hz
  in float32 (Optimist's pitch_inc table to +-1 unit at the usual notes); DTN as det_inc (whole
  1/16 semitones, the rest fine_inc's truncated factor), DRFT's walk (super_drift) in integers
  as Optimist's, the noise (xorshift32) bit for bit.
- The poly-BLEPs as osc_saw's, in float (t = phase / increment); the square is two saws, so PWM
  is the square: its width came from ENV / LFO -> SHP, which the machine does not have (the DN2's
  LFOs move knobs). The sine: u (1 - u^2) Q(u^2), Q of degree 4 (3e-7; Optimist's 1024-point
  table). tanh in the drive: x P(x^2) on 0..2, degree 4 (never above the degree-8 curve on 0..2, within 1.08e-3 under it; rising; 2026-11-21, the
  User's pick for speed: degree 8 before, 4.5e-6; Optimist's TANH_Q15 interpolated, 6e-6), clamped at 2 as softclip.
- Hard sync as a2_sync, sample by sample: a look-ahead puts the restart's pre-correction on the
  sample before the wrap (the C's segments do it on b[i - 1] or at the block's end), the restart
  and its post-correction on the next. A trig that restarts the phases restarts osc 2 there too
  (the C finds osc 1's wrap at sample 0).
- The filters are the a2f port's (dnfw.engines.analog2.filters.models: float, its own approximations; ref.py lists
  them): the SVF ramps its coefficients from the last half's cutoff, the models are set at each
  half's end (a2_filter, a2m_block). The model's states are cleared when FLT changes model.
- No ENV2, no m->shape / m->cutoff / OSC2 / SDTN modulation (the DN2's LFOs and envelopes move
  the knobs); with SYNC, SEMI moves osc 2 (the sync interval). No FLT B.
- The swarm's CPU cap is a constant (MAX_COPIES; Optimist's voices_busy cap has no DN2 source).
- A trig: with DRFT 0 the phases restart (osc 1 and the spread at 0, osc 2 a quarter turn on),
  free otherwise; the filter's states and last cutoff go on (Optimist's retrigger keeps them).

WDTH (2026-11-11, the User: "a stereo spread of voices"): with copies and WDTH > 0, the copies go left (+1 -2 +3,
SIDE_OF) and right (-1 +2 -3), osc 1 and 2 in the middle. The mid is the same sum as with WDTH 0 (to float rounding:
the copies are summed right, then left); the side L - R of the copies runs through a linear SVF (2026-11-21, the
User's pick for speed, _side12: one stage, two for LP24, the mode's SVF mix, this half's cutoff, RES's damping, the SVF's knees, the
level of the chosen model's passband; its states S_Z2, S_Z2 + 1; before, a second copy of the chosen filter), x 2 WDTH (the output's 2 x; DRV not on the side), into the slot's side block (DRONE's BEAT's,
dnfw.inserts.post.beat: added after the pan as L += g s, R -= g s, g the chain's gain on the mid). WDTH 0 or no copies
writes nothing: output bit-identical to before. Cost (model steps a block, 6 copies, sync, DRV): +2.7k (SVF) .. +4.8k
(MS20); on the runner's memory clock +4.0k .. +6.2k cycles.

The filters' words and mix tables (`ctx`): the words in the render scratch's XB (SID's phases,
free since 2026-11-08), the tables (`table_words`, not zeros) read from the A2 filter pass's own copy in L1
(`tables_at`: dnfw.engines.analog2.filters.program.TABLES, the same floats; 2026-11-21, DSP room: the second copy
the upload carried at TABLES_OFF in the Monomachine's L2 scratch is gone, -436 B of section 7).
"""

from __future__ import annotations

from . import a2glide as G
from . import para as PARA
from ...mnm import core as C
from ..drone.drone import SIDE_L2, SIDE_STRIDE, _side_base
from ..tb303.tb303 import _exp2p
from .filters import models as M
from ...perc.dsl import Prog

NAME, ID = "ANALOG2", 68
PNAMES = ("WAVE", "DTN", "MIX", "NOIS", "CUT", "RES", "DRV", "KTR")
DEFAULTS = (0, 10, 64, 0, 90, 30, 0, 64)         # Optimist's ANALOG defaults
PNAMES2 = ("SWRM", "SEMI", "SDTN", "SYNC", "WAV2", "DRFT", "FLT2", "WDTH")
# page 2's start as knobs 0..127 (dnfw.waverider.pages mnm_default: perc.live.knob_word; q ~ knob / 127):
# Optimist's SWRM 0, SEMI 0, SDTN 34, SYNC OFF, WAV2 =1, DRFT 0, FLT SVF LP12; WDTH 0 (2026-11-11: mono, as before)
DEFAULTS2 = (0, 64, 34, 0, 0, 0, 0, 0)
# 2026-11-11: page 3, the glide (dnfw.engines.analog2.a2glide). MACHINE SEL starts it OFF, GLID at Optimist's SLIDE_T (TIME_MS
# index 54, ~50 ms), so RATE or TIME glides at once
PNAMES3 = ("GLID", "GLTY")
DEFAULTS3 = (54, 0)
# 2026-11-11 (the User: spread next to the swarm count; the filter type, FLT2 (ANALOG 2's own filter, not the
# DN2's), beside CUT and RES; osc 2's SEMI beside WAV2): where each control is drawn, page by page, knobs A..H.
# Display only: a control keeps its record wherever it is drawn (dnfw.waverider.pages mnm_order), so old tracks
# keep their values. None: an empty knob
LAYOUT = (("WAVE", "DTN", "MIX", "NOIS", "FLT2", "CUT", "RES", "KTR"),
          ("SWRM", "SDTN", "DRFT", "SYNC", "WAV2", "SEMI", "DRV", "WDTH"),
          ("GLID", "GLTY"))
WAVES = ("SAW", "SQR", "TRI", "SIN", "PWM")
WAVES2 = ("=1",) + WAVES
FLTS = tuple(f"{m} {md}" for m in M.MODELS for md in M.MODES)

MAX_COPIES = 6                                   # the swarm's cap (a constant: no voices_busy here)
# the filter models emitted (the SVF always); a FLT choice of a model left out plays the SVF in its
# mode (Optimist's "a model not built: the SVF")
FILTER_MODELS = M.MODELS
TABLES_OFF = 0x3200                              # (until 2026-11-21) the mix tables in the Monomachine L2 scratch:
                                                 # +0x3200..+0x33A8 there is free now (tables_at)
SR = 44100.0
INC_K = 440.0 / SR * 2.0 ** 32                   # the increment of A4
COPY_PH = (0x2B7E1516, 0x9E3779B9, 0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A)
COPY_AT = (1, -1, 2, -2, 3, -3)
GC = 80 * 258                                    # A2_SWARM_GC: the copies' level, Q15
SDTN_K = 60 * 2367 * 16 / (127 * 3 * 1000)      # dinc's factor a SDTN unit
TOP15 = 32767.0 / 32768.0                        # softclip's and the sine's top
NONE = -1.0                                      # no last cutoff (a fresh voice)
HALF = 0x80000000
# sin(pi u) / (u (1 - u^2)) in u^2 (fitted, 3e-7), with the sine's sign and TOP15 folded in
SIN_Q = tuple(-c * TOP15 for c in (3.14159230309089, -2.0260895597297144, 0.5237673445980027,
                                   -0.07439094157966462, 0.005918106135584834))
assert SIN_Q == M.A2_SIN_Q                        # (the two-sample kernel reads its copy in the filters' KC table)
# tanh(x) / x in x^2 on 0..2, TOP15 folded in: one-sided, never above the degree-8 curve before it (TANH_P8, A's
# sound) anywhere on 0..2 (a linear program: n <= o (1 - 1e-5), float32 rounding of both curves included, least max(o - n) = 1.08e-3), so the drive is never
# louder than before at any input (no digital clipping, the User 2026-11-21); slope 0.9944 at 0 (-0.05 dB), rising
TANH_P8 = (0.9999987523471627, -0.3332349530378557, 0.1325101073321532, -0.05139980898798015, 0.01773782644437922,
           -0.004831303440849461, 0.0009141036195898637, -0.0001032153224941374, 5.152369914034383e-06)
TANH_P = tuple(c * TOP15 for c in (0.994438468571122, -0.3077078377445752, 0.08908856172526249,
                                   -0.01588368865468038, 0.0012091530231845907))
assert TANH_P == M.A2_TANH_P                      # (the drive's two-sample loop reads its copy in the filters' KC table)
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
# 2026-11-11, WDTH (the User: "a stereo spread of voices", option A): the copies' sides (K_S + k, k 1..6: +1 left,
# -1 right), the side's filter states, D_WID 2 x WDTH while the side is on (copies and WDTH > 0; else 0), D_SEL the
# job pass's side (0 every job)
SIDE_OF = (1, -1, -1, 1, 1, -1)                  # copy k's side: left the copies at +1 -2 +3, right -1 +2 -3
K_S = GW.END
S_Z2 = K_S + 7
D_WID, D_SEL = S_Z2 + 4, S_Z2 + 5
A_END = S_Z2 + 6
assert A_END <= C.K.NS


def tables_at(L: C.Layout | None = None) -> int:
    """where the mix tables are: the A2 filter pass's own L1 copy (filters.program.TABLES, loaded with its state:
    dnfw.waverider.dsp._a2f_state_span), the same floats (checked). 2026-11-21 (DSP room): read there, not from a
    second copy in the Monomachine's L2 scratch (L1 is also the quicker read). L: unused, the address is the DSP's."""
    from .filters import program as FP
    assert FP.ctx().models == M.Ctx(0, 0, FILTER_MODELS).models, "the pass's tables must be ANALOG 2's"
    return FP.TABLES


def ctx(L: C.Layout) -> M.Ctx:
    """the filters' words (render scratch XB) and mix tables (tables_at: the A2 filter pass's L1 copy)"""
    return M.Ctx(L.XB, tables_at(L), FILTER_MODELS)


def table_words() -> list[float]:
    """the mix tables' floats, as the DSP holds them at tables_at()"""
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
    p.loop(L.W["n5"], A_END, lambda: p.stpost(2, 1))
    for k in range(1, 7):
        p.iconst(0, COPY_AT[k - 1])
        _sv(p, K_A + k, 0)
        p.iconst(0, SIDE_OF[k - 1])
        _sv(p, K_S + k, 0)
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
    """Rx = xorshift32(Rx) (13, 17, 5). Clobbers R13 (R14 no more: 2026-11-21, the native XOR)."""
    for n in (13, -17, 5):
        p.lsh(13, x, n)
        p.xor1(x, x, 13)


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
            _sv(p, S_Z2 + k, 0)
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
    _width(p, L)


def _width(p: Prog, L: C.Layout) -> None:
    """D_WID = 2 x WDTH (q7) with copies, else 0; on: the side block's |mid| sum 0 and its flag 1 (DRONE's BEAT's
    block: the coordinator's post-pan pass mixes the side in, dnfw.inserts.post.beat)"""
    C.page2(p, L, 0, 7)
    _k(p, 0, 0, "*", 2.0)
    p.fconst(3, 0.0)
    p.fconst(2, 0.0)
    _ld(p, 1, D_NC)

    def on():
        p.fpass(3, 0)
        _side_base(p, L, 0)
        p.seti(5, 0)
        p.fconst(2, 0.0)
        p.sti(32, 5, 2)
        p.fconst(2, 1.0)
        p.sti(33, 5, 2)
    PARA.shadow_render(p, 4)                     # 2026-11-16: a PARA shadow (a chord's joined note) has no side:
    p.ifz(4, "NE", lambda: p.iconst(1, 0))       # the side block is its leader slot's (the chord's spread its own)
    p.ifz(1, "NE", lambda: p.if_(0, "GT", 2, on))
    _sv(p, D_WID, 3)


SIDE_TMP = 176                                   # 2026-11-21 (perf): the half's side, built and filtered in the render
                                                 # scratch's YB row 176..191 (L1, anyone's between halves); _side_out
                                                 # writes it to the slot's side block (L2) once, x 2 WDTH


def _side_tmp(p: Prog, L: C.Layout, d: int) -> None:
    """Rd = the half's side in L1 (SIDE_TMP)"""
    p.iconst(d, L.YB + 4 * SIDE_TMP)


def _side_at(p: Prog, L: C.Layout, i: int) -> None:
    """Ii = this half's 16 words of the slot's side block. Clobbers R0, R1, R12-R14."""
    _side_base(p, L, 0)
    p.ld(1, L.W["half"])
    p.lsh(1, 1, 6)
    p.ipass(12, 1)
    p.iop(0, 12, "+", 0)
    p.seti(i, 0)


# the Monomachine scratch words the halves use (dnfw.mnm.core SC_WORDS: the removed machines')
WN = {"bv": "bv", "i3": "x0", "jobs": "n4", "job": "inner", "ri1": "minc", "if2": "inc", "n0": "x1",
      "hn": "fd", "g2": "g", "jall": "u", "passes": "osc", "pass": "j"}


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
    p.ld(0, L.W[WN["bv"]])
    p.seti(0, 0)
    p.fconst(3, 1.0)

    def blep_setup():                            # (2026-11-21: only the saw's and the square's: TRI and SIN read
        p.float_(15, 9, 10)                      # neither F6 nor F7)
        p.fconst(12, 0.5)
        p.fop(7, 12, "-", 15)                    # thr = 1/2 - increment
        M.recip(p)
        p.fpass(6, 15)                           # 1 / increment
        p.fconst(2, 0.5)

    def acc(v: int) -> None:
        p.ldi(13, 0, 0)
        p.fop(v, v, "*", 5)
        p.fop(13, 13, "+", v)
        p.stpost(0, 13)

    def saw():
        blep_setup()

        def one():
            p.float_(0, 8, 10)
            p.iop(8, 8, "+", 9)
            _saw(p, 1, 0, 14, 7, 6, 2, 3)
            acc(1)
        p.loop_r(11, M.N, one)

    def sqr():
        """(2026-11-21, the User's pick for speed) the square as sgn(x) (1 - b): the two saws' BLEPs are one BLEP of the doubled phase z
        (both edges sit at z's wrap, at the same t), its sign the sign of x"""
        blep_setup()
        p.fop(7, 7, "+", 7)
        p.fop(7, 7, "-", 2)                      # thr = 1/2 - 2 increments
        p.fop(6, 6, "*", 2)                      # 1 / (2 increments)
        _k(p, 5, 5, "*", 0.5)
        p.iop(4, 9, "+", 9)                      # the doubled phase's increment
        p.iconst(15, HALF)
        p.iop(15, 15, "+", 8)
        p.iop(15, 15, "+", 8)                    # z = 2 phase (+ 2^31)

        def one():
            p.float_(0, 15, 10)
            p.iop(15, 15, "+", 4)
            M.fabs(p, 1, 0)
            p.fpass(13, 5)                       # (2026-11-21, filt-opt) 1.0 x g is g (g = F5, itself a product: a
                                                 # finite or canonical word), so no BLEP: g with no multiply
            p.ldi(14, 0, 0)                      # (rides on the pass)

            def blep():
                p.fop(1, 2, "-", 1)
                p.fop(1, 1, "*", 6)
                p.fop(1, 3, "-", 1)
                p.fop(1, 1, "*", 1)
                p.fop(13, 3, "-", 1)
                p.fop(13, 13, "*", 5)
            p.if_(1, "GT", 7, blep)
            p.ifz(8, "LT", lambda: p.fop(14, 14, "-", 13), lambda: p.fop(14, 14, "+", 13))
            p.iop(8, 8, "+", 9)
            p.stpost(0, 14)
        p.loop_r(11, M.N, one)
        p.iconst(4, 1)

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
        if SIN2:
            return _sin2(p, L)
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


SIN2 = True                                      # (perf, 2026-11-21) the sine kernel two samples at a time (_sin2)


def _sin2(p: Prog, L: C.Layout) -> None:
    """the sine kernel's 16 samples as 8 pairs: each sample's operations as _kernel's sin (_sin, acc), on its own
    registers, in the same order (bit for bit); the two samples' chains side by side, so a multiply of one rides
    with an add of the other (multifunction, dnfw.perc.mf's proven forms; dnfw.mnm.sched). Q's coefficients and 1.0
    from the filters' KC table through I1. In: R8 the phase, R9 the increment, F5 g, I0 at b."""
    from ...mnm.sched import Sched
    kc = M._kc
    X = ctx(L)
    p.iconst(12, X.T["kc"][0])
    p.seti(1, 12)
    p.ipass(14, 9)                               # the increment
    p.iconst(15, -32)
    p.ldi(6, kc("k1"), 1)                        # 1.0
    p.ipass(10, 8)                               # the phase (an integer add's first operand: R8..R15)

    def pair():
        s = Sched()
        for u in (2, 3):                         # f = FLOAT the phase; the phase moves on
            s.raw(lambda q, u=u: q.float_(u, 10, 15), (10, 15), (u,))
            s.raw(lambda q: q.iop(10, 10, "+", 14), (10, 14), (10,))
        lanes = ((0, 2, 4, 9, 12), (1, 3, 7, 8, 13))    # d, u, t, m, b (R10 the phase, R11 the count)
        for d, u, t, m, b in lanes:
            s.add(u, u, u)                       # u = 2 f
            s.mul(t, u, u)                       # t = u^2
        for d, u, t, m, b in lanes:
            s.ld(b, kc("sq4"), 1)
            s.mul(m, b, t)                       # q4 t (the PASS of q4, then its multiply)
        for k in (3, 2, 1, 0):
            for d, u, t, m, b in lanes:
                s.ld(b, kc(f"sq{k}"), 1)
                s.add(d, m, b)                   # + q_k
                if k:
                    s.mul(m, d, t)               # x t
        for d, u, t, m, b in lanes:
            s.sub(t, 6, t)                       # 1 - t
            s.mul(t, t, u)                       # (1 - t) u
            s.mul(d, d, t)
            s.mul(m, d, 5)                       # x g (acc)
        for lane, (d, u, t, m, b) in enumerate(lanes):
            s.ld(b, lane, 0)
            s.add(b, b, m)                       # b + g w
        s.emit(p)
        p.stpost(0, 12)
        p.stpost(0, 13)
    p.loop_r(11, M.N // 2, pair)
    p.iconst(4, 3)                               # (R4 the wave again: the kernel keeps it)


def _jobs(p: Prog, L: C.Layout) -> None:
    """the copies, osc 1, osc 2 when free: one kernel each. With the side on (D_WID), three passes: the right
    copies (b = R; side = -R), the left (b = R + L; side = b + 2 side = L - R), then the oscillators"""
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
    p.st(W[WN["jall"]], 0)
    p.iconst(2, 1)
    _ld(p, 1, D_WID)
    p.fconst(12, 0.0)
    p.if_(1, "NE", 12, lambda: p.iconst(2, 3))
    p.st(W[WN["passes"]], 2)
    p.iconst(0, 0)
    p.st(W[WN["pass"]], 0)

    def one_pass():
        p.ld(0, W[WN["pass"]])
        p.ld(1, W[WN["jall"]])
        _ld(p, 2, D_NC)
        p.iconst(3, 0)                           # the first job
        p.iconst(4, 0)                           # the side
        _ld(p, 5, D_WID)
        p.fconst(12, 0.0)

        def stereo():
            p.iconst(12, 2)
            p.if_(0, "LT", 12, lambda: (p.ipass(1, 2), p.iconst(4, -1),
                                        p.ifz(0, "NE", lambda: p.iconst(4, 1))),
                  lambda: (p.ipass(3, 2), p.ipass(12, 1), p.iop(1, 12, "-", 2)), kind="i")
        p.if_(5, "NE", 12, stereo)
        p.st(W[WN["jobs"]], 1)
        p.st(W[WN["job"]], 3)
        _sv(p, D_SEL, 4)
        M.mloop(p, W[WN["jobs"]], lambda: _job(p, L))
        p.ld(0, W[WN["pass"]])
        _ld(p, 5, D_WID)
        p.fconst(12, 0.0)

        def side():
            p.ld(2, W[WN["bv"]])
            p.ipass(3, 0)
            _side_tmp(p, L, 1)
            p.seti(1, 1)                         # (I1: its moves ride on the computes)
            p.seti(0, 2)

            def neg():
                p.ldpost(1, 0)
                p.fop(1, 13, "-", 1)
                p.stpost(1, 1)

            def lr():
                p.ldpost(1, 0)
                p.ldi(2, 0, 1)
                p.fop(2, 2, "+", 2)
                p.fop(2, 2, "+", 1)
                p.stpost(1, 2)
            def second():
                p.iconst(12, 1)
                p.if_(3, "EQ", 12, lambda: p.loop_r(11, M.N, lr), kind="i")
            p.ifz(3, "EQ", lambda: (p.fconst(13, 0.0), p.loop_r(11, M.N, neg)), second)
        p.if_(5, "NE", 12, side)
        p.ld(8, W[WN["pass"]])
        p.iconst(12, 1)
        p.iop(8, 8, "+", 12)
        p.st(W[WN["pass"]], 8)
    M.mloop(p, W[WN["passes"]], one_pass)


def _job(p: Prog, L: C.Layout) -> None:
    """one job (W job): a copy (D_SEL 0, or the copy on D_SEL's side; another is skipped), osc 1, osc 2"""
    W = L.W
    p.ld(6, W[WN["job"]])
    _ld(p, 7, D_NC)

    def copy():                                  # copy k = job + 1: osc 1 + a spr + c
        _ri(p, 0, "I3")
        p.iconst(12, p.ioff(3, 4 * (C.K.S0 + K_A + 1)))
        p.iop(0, 12, "+", 0)
        p.lsh(1, 6, 2)
        p.ipass(12, 0)
        p.iop(0, 12, "+", 1)
        p.seti(2, 0)
        p.ldi(10, K_S - K_A, 2)                  # its side (2026-11-21: tested first, a copy of the other side
        _ld(p, 11, D_SEL)                        # skipped before its words are read)
        p.iconst(6, 1)
        p.ifz(11, "NE", lambda: p.if_(10, "NE", 11, lambda: p.iconst(6, 0), kind="i"))

        def words():
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
        p.ifz(6, "NE", words)

    def osc1():
        _ld(p, 8, S_Q0)
        _ld(p, 9, D_INC1)
        _ld(p, 5, D_G1)
        _ld(p, 4, D_W1)
        p.iconst(6, 1)

    def osc2():
        _ld(p, 8, S_Q1)
        _ld(p, 9, D_INC2)
        _ld(p, 5, D_G2)
        _ld(p, 4, D_W2)
        p.iconst(6, 1)
    p.if_(6, "LT", 7, copy, lambda: p.if_(6, "EQ", 7, osc1, osc2, kind="i"), kind="i")
    p.ifz(6, "NE", lambda: _kernel(p, L))
    p.ld(8, W[WN["job"]])
    p.iconst(12, 1)
    p.iop(8, 8, "+", 12)
    p.st(W[WN["job"]], 8)


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
        p.iconst(14, -16384)                     # (2026-11-21: once, not every sample; xor1 leaves R14 alone)

        def one():
            _noise_step(p, 8)
            p.lsh(13, 8, -17)
            p.iop(13, 14, "+", 13)
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

        if DRV2:
            p.iconst(12, ctx(L).T["kc"][0])     # (2026-11-21, filt-opt) its constants from the filters' KC table
            p.seti(1, 12)
            p.loop_r(11, M.N // 2, lambda: _drive2(p))
            return

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


DRV2 = True                                      # (perf, 2026-11-12) _drive2; False = sample by sample, a2tp called


def _drive2(p: Prog) -> None:
    """two of _drive's samples (b at I0, I0 two words on): its operations on the same values (so bit for bit),
    a2tp's polynomial inlined and the two run side by side (dnfw.mnm.sched): each coefficient loaded once for
    both, one's multiply with the other's add in one instruction. F5 drive, F6 dw kept; R11 the loop's.
    (2026-11-21, filt-opt) the constants read from the filters' KC table through I1 (each load a move that rides on a
    compute, not a constant load of its own) and the two samples stored by post-modify (I0 two words on, no pointer
    arithmetic): the same values, the same words"""
    from ...mnm.sched import Sched
    kc = M._kc
    s = Sched()
    for x, y, s2, am, aa in ((1, 10, 4, 0, 8), (2, 13, 7, 3, 9)):
        s.ld(x, x - 1, 0)
        s.mul(y, x, 5)
        s.ld(12, kc("k2"), 1)
        s.fop(y, y, "MIN", 12)
        s.ld(12, kc("km2"), 1)
        s.fop(y, y, "MAX", 12)
        s.mul(s2, y, y)
    n = len(TANH_P) - 1
    s.ld(0, kc(f"tp{n}"), 1)
    s.ld(3, kc(f"tp{n}"), 1)
    for k in range(n - 1, -1, -1):
        s.mul(8, 0, 4)
        s.mul(9, 3, 7)
        s.ld(12, kc(f"tp{k}"), 1)
        s.add(0, 8, 12)
        s.add(3, 9, 12)
    for x, y, a, t in ((1, 10, 0, 15), (2, 13, 3, 14)):
        s.mul(t, y, a)                           # tanh's curve
        s.ld(12, kc("khalf"), 1)
        s.mul(t, t, 12)
        s.sub(t, t, x)
        s.mul(t, t, 6)
        s.add(x, x, t)
    s.emit(p)
    p.stpost(0, 1)
    p.stpost(0, 2)


def _filter(p: Prog, L: C.Layout) -> None:
    """the filter (dnfw.engines.analog2.filters.models) in place over b: its words from the block's, the states at
    S_Z (cleared past 1e4 or NaN, as a2m_block); I3 kept round it (the models clobber it). (The WDTH side: _side12.)"""
    X = ctx(L)
    W = L.W
    z = S_Z
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
    p.iconst(12, p.ioff(3, 4 * (C.K.S0 + z)))
    p.iop(0, 12, "+", 0)
    p.st(X.C["zp"], 0)
    p.iconst(9, 0)
    for k in range(4):
        _ld(p, 0, z + k)
        p.iconst(12, 0x7FFFFFFF)
        p.iop(0, 0, "AND", 12)
        p.iconst(12, 0x461C4000)                 # 1e4
        p.if_(0, "GE", 12, lambda: p.iconst(9, 1), kind="i")

    def clear():
        p.iconst(0, 0)
        for k in range(4):
            _sv(p, z + k, 0)
    p.ifz(9, "NE", clear)
    M.half(p, X)
    p.ld(0, W[WN["i3"]])
    p.seti(3, 0, bias=b3)                        # the models point I3 at their own tables: the voice's biased one back


SIDE12_KNEE = True                               # the knees on the side's states (the User's ask; on the peak grid they never
                                                 # engage, and they cost 512 a block: False drops them)
SIDE12_DBP = (0.15, 0.95)                        # DIOD BP's side level at RES 0 and 127 (linear between)
SIDE12_KMIN = 0.1                                # the side's least damping: bounded at RES 127
# LADR, OTA, DIOD at low RES: the side's level x min(1, LOW0 + LOWK RES) (1 from RES 25). Their filters are not the
# side's SVF, so the side's phase against the mid differs; at RES 0 .. 15 that alone put B's stereo peak up to
# +0.6 dB above A's (DIOD LP24 RES 5) though the side was not louder. The trims a CUT sweep needed (peak grid,
# 2026-11-21): LADR 0.835 / 0.975 / 0.995 at RES 0 / 5 / 10, OTA 0.83 / 0.96 / 1, DIOD 0.91 / 0.88 / 0.905 / 0.97
# at RES 0 / 5 / 10 / 15, 1 from RES 20; this line stays under all of them
SIDE12_LOW0, SIDE12_LOWK = 0.80, 0.008
# every model: the side at 0.97 of the level above (-0.26 dB). On the full peak grid (every model x mode x RES x DRV,
# 2026-11-21) B's stereo peak still rose above A's by up to +0.035 dB (MS20 LP24), +0.005 (SVF): the side's filter runs
# on the half's end cutoff, the model's on its ramp. The trims needed were 0.99 at the least; B's peak is convex in the
# side's level and at level 0 is the mid's (never above A's), so any level under the needed trim keeps B under A
SIDE12_LEVEL = 0.97
# LADR, OTA, DIOD's LP24 DC gain against RES / 100 (0..1), degree 4, fitted on ref.py's models
# (RES 0..100 by 5; within 0.21, 0.04, 0.44 dB); SVF and MS20 pass DC at 1
SIDE12_DC = ((0.99007, -2.99361, 5.73099, -5.59232, 2.08664),
             (0.99593, -1.40077, 2.58044, -2.46765, 0.91043),
             (0.95682, -2.08525, 8.17025, -9.73937, 4.07121))


def _side_knee(p: Prog, r: int, lim: float) -> None:
    """Fr past +-lim (|Fr| in F15, lim in F12): lim + lim tanh((|Fr| - lim) / lim), its sign kept, as the SVF stage's
    knee (filters.models _svf_stage over); squashed by 1 dB or more lights the voice's clip. Clobbers F10, F12-F15."""
    p.fpass(10, 15)
    p.fop(15, 15, "-", 12)
    if lim != 1.0:
        p.fconst(12, 1.0 / lim)
        p.fop(15, 15, "*", 12)
    p.fconst(12, 2.0)
    p.fop(15, 15, "MIN", 12)
    M.tanh(p)
    if lim != 1.0:
        p.fop(15, 15, "+", 15)
    p.fconst(12, lim)
    p.fop(15, 12, "+", 15)
    p.fconst(12, 1.122)
    p.fop(12, 15, "*", 12)
    M._clip(p, 12, "LT", 10)
    p.fconst(12, 0.0)
    p.if_(r, "LT", 12, lambda: p.fop(r, 12, "-", 15), lambda: p.fpass(r, 15))


def _side12(p: Prog, L: C.Layout) -> None:
    """the WDTH side through one linear SVF stage (12 dB, any model; LP24 two), the mode's SVF mix, at this
    half's end cutoff (no ramp), RES's damping (not under SIDE12_KMIN), the SVF stage's knees on its states, the chosen
    model's passband level at RES (SIDE12_DC; LADR, OTA, DIOD trimmed at low RES, SIDE12_LOW0); LP24 adds the SVF's second stage (K2ND, 24 dB, as the SVF's own LP24):
    its states S_Z2 .. S_Z2 + 3"""
    X = ctx(L)
    W = L.W
    for src, w in ((D_GA, "ge"), (D_RES, "res"), (D_MODE, "mode")):
        _ld(p, 0, src)
        p.st(X.C[w], 0)
    p.iconst(9, 0)
    for k in range(4):
        _ld(p, 0, S_Z2 + k)
        p.iconst(12, 0x7FFFFFFF)
        p.iop(0, 0, "AND", 12)
        p.iconst(12, 0x461C4000)                 # 1e4 (or NaN): cleared, as _filter
        p.if_(0, "GE", 12, lambda: p.iconst(9, 1), kind="i")
    p.ifz(9, "NE", lambda: (p.iconst(0, 0), [_sv(p, S_Z2 + k, 0) for k in range(4)]))
    _ld(p, 1, S_Z2)
    _ld(p, 2, S_Z2 + 1)
    p.st(X.C["t1"], 1)
    p.st(X.C["t2"], 2)
    _ld(p, 0, D_RES)                             # the model's LP passband (DC) gain at RES, so the side keeps its level
    _k(p, 0, 0, "MIN", 100.0)                    # (past 100 the models self-oscillate: held at 100's)
    _k(p, 0, 0, "*", 0.01)
    _ld(p, 1, D_MODEL)
    p.fconst(2, SIDE12_LEVEL)                    # SVF, MS20: 1 (x SIDE12_LEVEL)

    def horner(c):
        p.fconst(2, c[-1])
        for ck in c[-2::-1]:
            p.fop(2, 2, "*", 0)
            _k(p, 2, 2, "+", ck)
    for mi, c in ((M.LADR, SIDE12_DC[0]), (M.OTA, SIDE12_DC[1]), (M.DIOD, SIDE12_DC[2])):
        c = tuple(SIDE12_LEVEL * ck for ck in c)
        p.iconst(12, mi)
        p.if_(1, "EQ", 12, lambda c=c: horner(c), kind="i")

    def diod_bp():                               # DIOD's BP is far quieter than the SVF's (grid: +15 dB at RES 0, +2.4 at
        _ld(p, 0, D_RES)                         # 127 with the LP gain): its own level, SIDE12_DBP at RES 0 .. 127
        _k(p, 0, 0, "MIN", 127.0)
        _k(p, 0, 0, "*", SIDE12_LEVEL * (SIDE12_DBP[1] - SIDE12_DBP[0]) / 127.0)
        _k(p, 2, 0, "+", SIDE12_LEVEL * SIDE12_DBP[0])
    _ld(p, 3, D_MODE)
    p.iconst(12, 2)
    p.if_(3, "EQ", 12, lambda: (p.iconst(12, M.DIOD), p.if_(1, "EQ", 12, diod_bp, kind="i")), kind="i")

    def low():                                   # LADR, OTA, DIOD: x min(1, LOW0 + LOWK RES) (SIDE12_LOW0)
        _ld(p, 0, D_RES)
        _k(p, 0, 0, "*", SIDE12_LOWK)
        _k(p, 0, 0, "+", SIDE12_LOW0)
        _k(p, 0, 0, "MIN", 1.0)
        p.fop(2, 2, "*", 0)
    p.iconst(12, M.SVF)
    p.if_(1, "NE", 12, lambda: (p.iconst(12, M.MS20), p.if_(1, "NE", 12, low, kind="i")), kind="i")
    p.st(X.C["t0"], 2)
    b3 = p.ibias.get(3)
    _ri(p, 0, "I3")
    p.st(W[WN["i3"]], 0)
    M.svf_k(p, X, 9)
    p.fconst(12, SIDE12_KMIN)
    p.fop(9, 9, "MAX", 12)
    M._svf_coef(p, X, "ge", 9)                   # F15 a1, F14 a2, F13 a3
    p.fpass(3, 15)
    p.fpass(4, 14)
    p.fpass(5, 13)
    M._rowi(p, X, "svf")
    p.ldi(6, 0, 3)                               # cx
    p.ldi(7, 1, 3)
    p.fop(7, 7, "*", 9)
    p.ldi(10, 2, 3)
    p.fop(7, 7, "+", 10)                         # cb = cbk k + cb1
    p.ldi(8, 3, 3)                               # cl
    p.ld(10, X.C["t0"])
    for r in (6, 7, 8):
        p.fop(r, r, "*", 10)                     # the mix x the model's DC gain
    p.ld(1, X.C["t1"])
    p.ld(2, X.C["t2"])
    _side_tmp(p, L, 0)
    p.seti(0, 0)
    p.fconst(9, 1.0)                             # (the band state's knee bound, _side_one)

    p.loop_r(11, M.N, lambda: _side_one(p, True))
    p.ld(0, W[WN["i3"]])
    p.seti(3, 0, bias=b3)
    _sv(p, S_Z2, 1)
    _sv(p, S_Z2 + 1, 2)
    _ld(p, 0, D_MODE)

    def lp24():                                  # LP24: the SVF's second stage (K2ND, Q 0.707, low-pass), as its own
        p.fconst(9, M.K2ND)
        M._svf_coef(p, X, "ge", 9)
        p.fpass(3, 15)
        p.fpass(4, 14)
        p.fpass(5, 13)
        _ld(p, 1, S_Z2 + 2)
        _ld(p, 2, S_Z2 + 3)
        _side_tmp(p, L, 0)
        p.seti(0, 0)
        p.fconst(9, 1.0)
        p.loop_r(11, M.N, lambda: _side_one(p, False))
        _sv(p, S_Z2 + 2, 1)
        _sv(p, S_Z2 + 3, 2)
    p.iconst(12, 1)
    p.if_(0, "EQ", 12, lp24, kind="i")


def _side_one(p: Prog, mix: bool) -> None:
    """one side sample (I0): the linear SVF (F1 ic1, F2 ic2, F3-F5 a1-a3), out = cx x + cb v1 + cl v2 (F6-F8) when MIX,
    else the low-pass v2; then the SVF stage's knees on the states (band to 1, low-pass to 2; F9 holds 1.0).
    (perf, 2026-11-21, filt-opt) the temporaries' registers chosen so two multiplies pair with adds (multifunction,
    dnfw.mnm.sched): the same operations on the same values, in the same order for each value"""
    from ...mnm.sched import Sched
    s = Sched()
    s.ld(0, 0, 0)
    s.sub(15, 0, 2)                              # v3 = x - ic2
    s.mul(10, 3, 1)
    s.mul(12, 4, 15)
    s.add(13, 10, 12)                            # v1
    s.mul(14, 4, 1)
    s.mul(10, 5, 15)
    s.add(14, 14, 10)
    s.add(14, 2, 14)                             # v2
    s.add(15, 13, 13)
    s.sub(1, 15, 1)
    s.add(15, 14, 14)
    s.sub(2, 15, 2)
    if mix:
        s.mul(12, 6, 0)
        s.mul(13, 7, 13)
        s.add(10, 12, 13)
        s.mul(15, 8, 14)
        s.add(10, 10, 15)                        # cx x + cb v1 + cl v2
        s.emit(p)
        p.stpost(0, 10)
    else:
        s.emit(p)
        p.stpost(0, 14)
    if not SIDE12_KNEE:
        return
    M.fabs(p, 15, 1)
    p.if_(15, "GT", 9, lambda: (p.fconst(12, 1.0), _side_knee(p, 1, 1.0)))   # (the knee reads its bound in F12)
    M.fabs(p, 15, 2)
    p.fconst(12, 2.0)
    p.if_(15, "GT", 12, lambda: _side_knee(p, 2, 2.0))


def _out(p: Prog, L: C.Layout) -> None:
    """b = 2 b (a2_out, before the amplitude). 2026-11-21 (the User: "just make it quieter! not a limiter"): Optimist's
    soft knee (16000/32768, a protection for its Q15 output) is gone; ANALOG 2's level (perc.program LEVEL_DB) keeps
    its loudest setting clear of the outputs' full scale"""
    p.ld(0, L.W[WN["bv"]])
    p.seti(0, 0)

    def one():
        p.ldi(1, 0, 0)
        p.fop(1, 1, "+", 1)
        p.stpost(0, 1)
    p.loop_r(11, M.N, one)


def _side_out(p: Prog, L: C.Layout) -> None:
    """the side x 2 WDTH (b's 2 x; WDTH's own), the block's |b| sum into the side block's word 32"""
    _side_at(p, L, 5)
    _side_tmp(p, L, 0)
    p.seti(1, 0)
    _ld(p, 6, D_WID)
    p.ld(0, L.W[WN["bv"]])
    p.seti(0, 0)
    p.fconst(7, 0.0)

    def one():
        p.ldpost(1, 0)
        M.fabs(p, 2, 1)
        p.fop(7, 7, "+", 2)
        p.ldpost(3, 1)
        p.fop(3, 3, "*", 6)
        p.stpost(5, 3)
    p.loop_r(11, M.N, one)
    _side_base(p, L, 0)
    p.seti(5, 0)
    p.ldi(1, 32, 5)
    p.fop(1, 1, "+", 7)
    p.sti(32, 5, 1)


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
    X = ctx(L)
    p.iconst(0, 0)
    p.st(X.C["cv"], 0)                           # (2026-11-21) the coefficient words: not this half's yet

    def side_filter():
        _ld(p, 0, D_WID)
        p.fconst(12, 0.0)

        p.if_(0, "NE", 12, lambda: _side12(p, L))
    PARA.stage(p, L, side_filter)
    _noise(p, L)
    _drive(p, L)

    def rest():
        _filter(p, L)
        _out(p, L)
        _ld(p, 0, D_WID)
        p.fconst(12, 0.0)
        p.if_(0, "NE", 12, lambda: _side_out(p, L))
    PARA.stage(p, L, rest, bv_word=L.W[WN["bv"]])
