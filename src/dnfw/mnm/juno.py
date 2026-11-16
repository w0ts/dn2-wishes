# SPDX-License-Identifier: GPL-3.0-only
"""JUNO: the Juno-106 voice of Optimist's JUNO engine (firmware/src/engines/juno: eng_juno.c, juno_dsp.h), itself
fm-106 by PatttF (GPL-3.0-only) after Ultramaster KR-106 (GPL-3.0), as a Monomachine-style machine on PERC's
voice (THIRD-PARTY.md). A model of the Roland Juno-106; not affiliated with or endorsed by Roland.

One voice a track at 44.1 kHz, a DN2 block of 32 samples as two halves of 16. A half: the DCO (one phase: saw,
pulse 50..95 %, a sub square an octave down, noise through a 5.3 kHz low-pass; poly-BLEP edges as ANALOG2's
osc_saw), the ladder, the part's 1.6 Hz coupling and the HPF (BOOST, FLAT,
236 Hz, 754 Hz). Levels as Optimist's: 1.0 is its Q15 32768.

The ladder (2026-11-12, the User's choice: PERC's room): ANALOG2's OTA core (dnfw.a2f.models.ladder_core, one
subroutine for both machines) on Juno's own coefficients, once every 16 samples, as Optimist's voice sets them:
the cutoff DAC value a block (the uPD7811 routine juno_dac: CUT, the ENV's depth and polarity, KEY around C4), its
RC slew taken to the half's middle, KR-106's measured cutoff curve (G1Q) pulled to the resonance's peak
(PEAK_PULL), the resonance's k (RES_K, faded above code 3,500). The core's saturation is the Pade tanh where
fm-106 has the BA662 table; the drive D(RES) and the makeup GAIN were fitted on the host against Optimist's own
voice (scratch/juno-engine/cmp: harmonics within 0.2 dB to RES 110, 0.7 at 120; RES 127's self-oscillation within
~2 dB). D rides on the core's words: H D, k / D, G4 D (u = x - (k / D) tanh(D (G4 t + S))).

Parameters (page 1, knob / 128): WAVE (OFF SAW PULSE BOTH: the Juno's two buttons), PW (the width, 50..95 % over
knob 0..105), SUB, NOIS, CUT, RES, KEY, HPF (BOOST FLAT 236 754). Page 2 (`core.page2`, q0..q6): q0 ENV (the VCF
envelope's depth, -127..+127 about the middle: negative inverts it), q1 ATK (1.5 ms .. 3 s), q2 DEC, q3 SUS,
q4 REL (1.5 ms .. 12 s; the Juno's ADSR, for the VCF: the DN2's AMP page shapes the level), q5 PWM (MAN; ENV:
the width follows the envelope), q6 RNGE (16' 8' 4').

Against Optimist: float for its Q15 integers; the pulse as two band-limited saws (its mean removed by the coupling
capacitor, as the Juno's), the sub as two at half the rate (Optimist softens the sub's edge by the saw's BLEP);
no coupling capacitor after the DCO (every source here is without DC: the pulse is two saws), the two near-DC
couplings after the ladder (1.6 Hz and the HPF's 0.35 Hz) as one, 1.6 Hz; the envelope once a
block (the Juno's CPU ran it every 4 ms); no VCA curve (the DN2's AMP envelope); its ENV and LFO are the track's
own in Optimist, here the page-2 envelope and the DN2's LFOs on the knobs.
"""

from __future__ import annotations

import math

from . import analog2 as A2
from . import core as C
from .tables import T_D, T_G1Q, T_ID8, T_K8, T_NZ4, T_PULL2, T_SUB
from .tb303 import _exp2p
from ..a2f import models as M
from ..perc.dsl import Prog

NAME, ID = "JUNO", 69
PNAMES = ("WAVE", "PW", "SUB", "NOIS", "CUT", "RES", "KEY", "HPF")
DEFAULTS = (32, 0, 0, 0, 127, 0, 0, 48)          # Optimist's JUNO INIT: SAW, PW 0, CUT 127, HPF FLAT
PNAMES2 = ("ENV", "ATK", "DEC", "SUS", "REL", "PWM", "RNGE")
DEFAULTS2 = (64, 0, 50, 100, 30, 0, 64)          # ENV 0 (knob 64: q0 60/120), DEC ~0.3 s, SUS full, REL ~70 ms, MAN, 8'
WAVES = ("OFF", "SAW", "PULSE", "BOTH")
HPFS = ("BOOST", "FLAT", "236", "754")
PWMS = ("MAN", "ENV")
RANGES = ("16'", "8'", "4'")

GAIN = 10.0 ** (1.3 / 20.0)                      # the makeup the fit found (the core's LP24 against fm-106's x 8.59)
SAW_G = 19660.0 / 32768.0                        # the saw's level (Optimist: x 19660 >> 15)
PW_K = 18407003.0 / 2.0 ** 32                    # the width a PW step (eff = 1/2 - pw PW_K, pw 0..105)
NOISE_LP = 9300.0 / 32768.0                      # the noise's 5.3 kHz low-pass
CPL_A = 3800.0 / 2.0 ** 24                       # the ladder's (fm106_dc_block, 1.59 Hz)
SLEW_MID = 23150.0 / 32768.0                     # the cutoff CV's RC slew to the half's middle, (1 - 1393/32768)^8
SLEW_END = 16353.0 / 32768.0                     # and to its end, ^16
FADE_AT, FADE_W = 3500.0, 595.0                  # no resonance at Nyquist (juno_coef)
# the envelope (a block: 32 samples at 44.1 kHz): ATK's step 2^(A0 - q A1), DEC's and REL's x 2^(E0 - q E1)
# (env -> target + (env - target)(1 - x), about 40 dB in the time), 1.5 ms .. 3 s / 12 s
_BL = 32.0 / 44.1                                # ms a block
A0, A1 = math.log2(_BL / 1.5), math.log2(3000.0 / 1.5)
E0, E1 = math.log2(_BL * math.log(100.0) / 1.5), math.log2(12000.0 / 1.5)
# the HPF (fm106: juno_boost, juno_hpf_cut): BOOST's two shelves, the cuts' one-pole g
HB = (70704.0 / 2 ** 24, 27019.0 / 32768.0, 86019.0 / 2 ** 24, 2979.0 / 32768.0, 77000.0 / 32768.0)
HCUT = (277423.0 / 2 ** 24, 856006.0 / 2 ** 24)
NIL = -1.0                                       # S_SLEW: not started

# state (slot words S0..)
(S_PH, S_SPH, S_NS, S_NLP, S_FREE, S_SLEW, S_ENV, S_STG, S_GATE, S_CPL, S_B1, S_B2, S_HP) = range(13)
S_Z = 13                                         # the ladder's 4 states (the core's zp)
S_END = 17
# per block (pitch -> the halves)
(D_INC, D_INC2, D_THR, D_RI, D_THR2, D_RI2, D_GSAW, D_GPUL, D_GSUB, D_GNZ, D_W, D_DAC, D_K, D_D, D_ID, D_PULL,
 D_HPF) = range(S_END, S_END + 17)
D_END = S_END + 17
assert D_END <= C.K.NS
ATTACK, DECAY, RELEASE = range(3)
NOTE_OFF_WORD = 0x25C4B0                         # frame +36 (low half): the note-off mask, bit slot (drone.py)


def _ld(p: Prog, d: int, k: int) -> None:
    C.st(p, d, k)


def _sv(p: Prog, k: int, s: int) -> None:
    C.sts(p, k, s)


def _k(p: Prog, d: int, a: int, op: str, x: float) -> None:
    """Fd = Fa op x (x in R12)."""
    p.fconst(12, x)
    p.fop(d, a, op, 12)


def _tab(p: Prog, L: C.Layout, d: int, base: int, i: int) -> None:
    """Fd = JUNO's table word BASE + Ri (an integer). Clobbers R12, I1."""
    p.iconst(12, L.JU + 4 * base)
    p.lsh(i, i, 2)
    p.iop(12, 12, "+", i)
    p.seti(1, 12)
    p.ldi(d, 0, 1)


def exact(A: int, F: int, knobs, pre: int = 0) -> dict:
    """no Monomachine increments: JUNO takes its pitch from VW pitch (pitch below)"""
    return {}


def init(p: Prog, L: C.Layout) -> None:
    """Every word 0 but the noise's seed and 'no slew yet'; the envelope released at 0."""
    A2._ri(p, 0, "I3")
    p.iconst(12, p.ioff(3, 4 * C.K.S0))
    p.iop(0, 12, "+", 0)
    p.seti(2, 0)
    p.iconst(1, 0)
    p.loop(L.W["n5"], D_END, lambda: p.stpost(2, 1))
    p.iconst(0, 0x1234567)
    _sv(p, S_NS, 0)
    p.fconst(0, NIL)
    _sv(p, S_SLEW, 0)
    p.iconst(0, RELEASE)
    _sv(p, S_STG, 0)


def trig(p: Prog, L: C.Layout) -> None:
    """A note: the gate opens and the envelope attacks from where it is (the Juno's); the phases and the ladder go
    on. With every wave off and RES past 80 a still ladder is set ringing (fm-106's pure resonance patch)."""
    p.iconst(0, 1)
    _sv(p, S_GATE, 0)
    p.iconst(0, ATTACK)
    _sv(p, S_STG, 0)
    C.knob(p, 0, 0)
    p.lsh(0, 0, -5)                              # WAVE's choice (0: OFF)
    C.knob(p, 1, 2)
    p.iop(0, 0, "OR", 1)
    C.knob(p, 1, 3)
    p.iop(0, 0, "OR", 1)
    C.knob(p, 1, 5)
    p.iconst(12, 80)

    def ring():
        _ld(p, 1, S_Z)
        _ld(p, 2, S_Z + 1)
        p.fop(1, 1, "+", 2)
        p.fconst(12, 0.0)
        p.if_(1, "EQ", 12, lambda: (p.fconst(2, 0.01), _sv(p, S_Z, 2)))
    p.ifz(0, "EQ", lambda: p.if_(1, "GT", 12, ring, kind="i"))


def _gate_off(p: Prog, L: C.Layout) -> None:
    """S_GATE 0 when this block's frame carries the slot's note-off (frame +36, bit slot), as DRONE's"""
    from ..perc import program as PP
    p.ld(0, NOTE_OFF_WORD)
    p.iconst(12, 0xFFFF)
    p.iop(0, 0, "AND", 12)
    p.iconst(1, 1)
    p.ld(9, L.perc.C["t"])
    PP._shift_by(p, 1, 9)
    p.iop(0, 0, "AND", 1)
    p.ifz(0, "NE", lambda: (p.iconst(1, 0), _sv(p, S_GATE, 1)))


def _env(p: Prog, L: C.Layout) -> None:
    """The VCF envelope a block: F4 = its level 0..1 after the step. Clobbers R0-R3, R12-R15."""
    _ld(p, 0, S_GATE)
    _ld(p, 1, S_STG)
    p.iconst(12, RELEASE)
    p.ifz(0, "EQ", lambda: (p.ipass(1, 12), _sv(p, S_STG, 1)))
    # the stage's rate: 2^(c0 - q c1), q its control (ATK, DEC or REL)
    def sel(k: int, c0: float, c1: float):
        C.page2(p, L, 2, k)
        p.fconst(13, c0)
        p.fconst(14, c1)

    def not_attack():
        p.iconst(12, DECAY)
        p.if_(1, "EQ", 12, lambda: sel(2, E0, E1), lambda: sel(4, E0, E1), kind="i")
    p.iconst(12, ATTACK)
    p.if_(1, "EQ", 12, lambda: sel(1, A0, A1), not_attack, kind="i")
    p.fop(2, 2, "*", 14)
    p.fop(15, 13, "-", 2)
    _exp2p(p, 3, 15)                             # F3: the rate (clobbers R0, R1, R12)
    _ld(p, 1, S_STG)
    _ld(p, 4, S_ENV)
    p.fconst(12, 1.0)
    p.fop(3, 3, "MIN", 12)

    def attack():
        p.fop(4, 4, "+", 3)
        p.fconst(12, 1.0)
        p.if_(4, "GE", 12, lambda: (p.fpass(4, 12), p.iconst(0, DECAY), _sv(p, S_STG, 0)))

    def toward(target):
        p.fop(2, 4, "-", target)
        p.fop(2, 2, "*", 3)
        p.fop(4, 4, "-", 2)

    def decay():
        C.page2(p, L, 5, 3)                      # SUS
        toward(5)

    def release():
        p.fconst(5, 0.0)
        toward(5)
    A2._dispatch(p, 1, (attack, decay, release))
    _sv(p, S_ENV, 4)


def _dac(p: Prog, L: C.Layout) -> None:
    """D_DAC: the cutoff DAC value (juno_dac, 0..16383) from CUT, the envelope F4 at ENV's depth, KEY around C4.
    Keeps F4. Clobbers R0-R3, R12."""
    C.par(p, 0, 4)
    _k(p, 0, 0, "*", 128.0 * 128.0)              # CUT << 7
    C.page2(p, L, 1, 0)
    _k(p, 1, 1, "*", 2.0)
    _k(p, 1, 1, "-", 1.0)
    _k(p, 1, 1, "*", 127.0 * 2.0 * 16383.0 / 256.0)   # ENV's depth (x 2, the Juno's 254) on env14 >> 8
    p.fop(1, 1, "*", 4)
    p.fop(0, 0, "+", 1)
    C.vw(p, 2, "pitch")
    _k(p, 2, 2, "-", 60.0)
    C.par(p, 3, 6)
    _k(p, 3, 3, "*", 128.0 * 2.0 * 96.0 / 256.0)      # KEY x 2 on (note - C4) in 1/96 semitone >> 8
    p.fop(2, 2, "*", 3)
    p.fop(0, 0, "+", 2)
    _k(p, 0, 0, "MAX", 0.0)
    _k(p, 0, 0, "MIN", 16383.0)
    _sv(p, D_DAC, 0)


def _choice(p: Prog, d: int, a: int, n: int) -> None:
    A2._choice(p, d, a, n)


def _dco(p: Prog, L: C.Layout) -> None:
    """D_INC, D_INC2, D_THR, D_RI, D_THR2, D_RI2 (RNGE), the gains (WAVE, SUB, NOIS) and D_W (PW, PWM). F4: the
    envelope. Clobbers R0-R3, R5-R15."""
    C.page2(p, L, 0, 6)
    _choice(p, 1, 0, 3)
    p.iconst(12, 0)
    p.float_(1, 1, 12)
    _k(p, 1, 1, "*", 12.0)
    C.vw(p, 15, "pitch")
    p.fop(15, 15, "+", 1)
    _k(p, 15, 15, "+", -12.0 - 69.0)
    p.fpass(5, 4)
    A2._inc(p)                                   # R15: the increment (clobbers R0, R1, R12-R14)
    p.fpass(4, 5)
    _sv(p, D_INC, 15)
    p.lsh(0, 15, -1)
    _sv(p, D_INC2, 0)
    p.iconst(12, -32)
    p.float_(15, 15, 12)
    for f, thr, ri in ((1.0, D_THR, D_RI), (0.5, D_THR2, D_RI2)):
        _k(p, 1, 15, "*", f)
        p.fconst(12, 0.5)
        p.fop(2, 12, "-", 1)
        _sv(p, thr, 2)
        p.fpass(5, 15)
        p.fpass(15, 1)
        M.recip(p)
        _sv(p, ri, 15)
        p.fpass(15, 5)
    C.par(p, 0, 0)
    _choice(p, 1, 0, 4)
    p.iconst(12, 1)
    p.iop(2, 1, "AND", 12)
    p.iconst(12, 0)
    p.float_(2, 2, 12)
    _k(p, 2, 2, "*", SAW_G)
    _sv(p, D_GSAW, 2)
    p.lsh(1, 1, -1)
    p.iconst(12, 0)
    p.float_(1, 1, 12)
    _k(p, 1, 1, "*", 0.5)
    _sv(p, D_GPUL, 1)
    for k, base, scale, w in ((2, T_SUB, 1.0, D_GSUB), (3, T_NZ4, 4.0, D_GNZ)):
        C.knob(p, 1, k)
        _tab(p, L, 2, base, 1)
        p.ifz(1, "EQ", lambda: p.fconst(2, 0.0))
        if scale != 1.0:
            _k(p, 2, 2, "*", scale)
        _sv(p, w, 2)
    C.par(p, 0, 1)
    _k(p, 0, 0, "*", 128.0)                      # PW
    C.page2(p, L, 1, 5)
    _k(p, 1, 1, "-", 0.5)
    p.fconst(12, 0.0)
    p.if_(1, "GE", 12, lambda: p.fop(0, 0, "*", 4))   # PWM ENV: the width follows the envelope
    _k(p, 0, 0, "MIN", 105.0)
    _k(p, 0, 0, "*", PW_K)
    p.fconst(12, 0.5)
    p.fop(0, 12, "-", 0)
    _sv(p, D_W, 0)                               # the pulse's second saw's offset (the threshold, a phase)


def _res(p: Prog, L: C.Layout) -> None:
    """D_K, D_D, D_ID, D_PULL from RES; D_HPF from HPF. Clobbers R0-R2, R12, I1."""
    for base, w, scale in ((T_K8, D_K, 8.0), (T_D, D_D, 1.0), (T_ID8, D_ID, 8.0), (T_PULL2, D_PULL, 2.0)):
        C.knob(p, 1, 5)
        _tab(p, L, 0, base, 1)
        if scale != 1.0:
            _k(p, 0, 0, "*", scale)
        _sv(p, w, 0)
    C.par(p, 0, 7)
    _choice(p, 1, 0, 4)
    _sv(p, D_HPF, 1)


def pitch(p: Prog, L: C.Layout) -> None:
    """The block's control: the gate, the envelope, the cutoff DAC value, the DCO's increments and gains, the
    resonance's words."""
    _gate_off(p, L)
    _env(p, L)
    _dac(p, L)
    _dco(p, L)
    _res(p, L)


# -- a half ------------------------------------------------------------------------------------
def _osc(p: Prog, L: C.Layout) -> None:
    """16 samples of the DCO at I0 (the half's b): R8 the phase (+ 2^31), R9 the increment, F7 the BLEP's
    threshold, F6 1 / the increment (as ANALOG2's _kernel), F2 1/2, F3 1, R10 -32. Clobbers every register but
    I3."""
    _ld(p, 8, S_PH)
    _ld(p, 9, D_INC)
    _ld(p, 7, D_THR)
    _ld(p, 6, D_RI)
    p.fconst(2, 0.5)
    p.fconst(3, 1.0)
    p.iconst(10, -32)

    def wrap(r):                                 # Fr into -1/2..1/2
        p.fconst(12, -0.5)
        p.if_(r, "LT", 12, lambda: p.fop(r, r, "+", 3))

    def pulse():                                 # (saw(f) - saw(f - w)) / 2: the pulse, its mean 0
        _ld(p, 4, D_W)
        p.fop(4, 0, "-", 4)
        wrap(4)
        A2._saw(p, 12, 4, 14, 7, 6, 2, 3)
        p.fop(12, 1, "-", 12)
        p.fop(12, 12, "*", 13)
        p.fop(15, 15, "+", 12)

    def sub():                                   # a square at half the phase: two saws there
        _ld(p, 4, S_SPH)
        p.float_(5, 4, 10)
        _ld(p, 12, D_INC2)
        p.iop(4, 12, "+", 4)
        _sv(p, S_SPH, 4)
        _ld(p, 13, D_THR2)
        _ld(p, 12, D_RI2)
        A2._saw(p, 4, 5, 14, 13, 12, 2, 3)
        p.fop(0, 5, "-", 2)
        wrap(0)
        _ld(p, 12, D_RI2)                        # (wrap took R12)
        A2._saw(p, 1, 0, 14, 13, 12, 2, 3)
        p.fop(4, 4, "-", 1)
        _ld(p, 13, D_GSUB)
        p.fop(4, 4, "*", 13)
        p.fop(15, 15, "+", 4)

    def noise():                                 # xorshift32, its 5.3 kHz low-pass
        _ld(p, 4, S_NS)
        for n in (13, -17, 5):
            p.lsh(5, 4, n)
            p.xor(4, 4, 5, 12)
        _sv(p, S_NS, 4)
        p.iconst(12, -31)
        p.float_(4, 4, 12)
        _ld(p, 5, S_NLP)
        p.fop(4, 4, "-", 5)
        _k(p, 4, 4, "*", NOISE_LP)
        p.fop(5, 5, "+", 4)
        _sv(p, S_NLP, 5)
        _ld(p, 13, D_GNZ)
        p.fop(5, 5, "*", 13)
        p.fop(15, 15, "+", 5)

    def one():
        p.float_(0, 8, 10)                       # f, the phase - 1/2
        p.iop(8, 8, "+", 9)
        A2._saw(p, 1, 0, 14, 7, 6, 2, 3)
        _ld(p, 13, D_GSAW)
        p.fop(15, 1, "*", 13)
        _ld(p, 13, D_GPUL)
        p.ifz(13, "NE", pulse, kind="f")
        _ld(p, 13, D_GSUB)
        p.ifz(13, "NE", sub, kind="f")
        _ld(p, 13, D_GNZ)
        p.ifz(13, "NE", noise, kind="f")
        p.stpost(0, 15)
    p.loop_r(11, M.N, one)
    _sv(p, S_PH, 8)


def _ladder(p: Prog, L: C.Layout) -> None:
    """The ladder's words once a half (juno_coef at the slewed CV) and the core over the half's b (I3 kept)."""
    X = A2.ctx(L)
    _ld(p, 0, D_DAC)
    _ld(p, 1, S_SLEW)
    p.fconst(12, 0.0)
    p.if_(1, "LT", 12, lambda: p.fpass(1, 0))
    p.fop(1, 1, "-", 0)
    _k(p, 2, 1, "*", SLEW_MID)
    p.fop(2, 2, "+", 0)                          # the CV the half's coefficients take
    _k(p, 1, 1, "*", SLEW_END)
    p.fop(1, 1, "+", 0)
    _sv(p, S_SLEW, 1)
    _k(p, 2, 2, "*", 0.25)
    _k(p, 2, 2, "MAX", 0.0)
    _k(p, 2, 2, "MIN", 4095.0)                   # the cutoff table's code
    _k(p, 3, 2, "*", 0.25)
    p.trunc(4, 3)
    p.iconst(12, 1023)
    p.iop(4, 4, "MIN", 12)
    p.iconst(12, 0)
    p.float_(5, 4, 12)
    p.fop(3, 3, "-", 5)                          # the fraction between its points
    p.iconst(12, L.JU + 4 * T_G1Q)
    p.lsh(4, 4, 2)
    p.iop(12, 12, "+", 4)
    p.seti(1, 12)
    p.ldi(5, 0, 1)
    p.ldi(6, 1, 1)
    p.fop(6, 6, "-", 5)
    p.fop(6, 6, "*", 3)
    p.fop(5, 5, "+", 6)
    _ld(p, 6, D_PULL)
    p.fop(5, 5, "*", 6)
    _k(p, 5, 5, "MIN", 32767.0 / 32768.0)        # G
    p.fconst(12, 4095.0)
    p.fop(3, 12, "-", 2)
    _k(p, 3, 3, "*", 1.0 / FADE_W)
    _k(p, 3, 3, "MIN", 1.0)                      # the fade (1 below code 3,500)
    _ld(p, 7, D_K)
    p.fop(7, 7, "*", 3)                          # k
    _ld(p, 8, D_D)
    p.fop(9, 5, "*", 5)
    p.fop(9, 9, "*", 9)                          # G^4
    p.fop(15, 7, "*", 9)
    p.fconst(12, 1.0)
    p.fop(15, 12, "+", 15)
    M.recip(p)
    M._st(p, X, "inv", 15)
    _k(p, 10, 7, "*", 0.5)
    p.fconst(12, 1.0)
    p.fop(10, 12, "+", 10)
    M._st(p, X, "cin", 10)                       # 1 + k / 2
    M._st(p, X, "G", 5)
    p.fop(10, 12, "-", 5)
    p.fop(10, 10, "*", 8)
    M._st(p, X, "H", 10)                         # D (1 - G)
    _ld(p, 10, D_ID)
    p.fop(10, 10, "*", 7)
    M._st(p, X, "k", 10)                         # k / D
    p.fop(9, 9, "*", 8)
    M._st(p, X, "G4", 9)                         # D G^4
    p.iconst(0, 1)
    M._st(p, X, "ota", 0)
    p.iconst(0, 1)                               # LP24 (the core's output row)
    M._st(p, X, "mode", 0)
    p.ld(0, L.W[A2.WN["bv"]])
    M._st(p, X, "buf", 0)
    b3 = p.ibias.get(3)
    A2._ri(p, 0, "I3")
    p.st(L.W[A2.WN["i3"]], 0)
    p.iconst(12, p.ioff(3, 4 * (C.K.S0 + S_Z)))
    p.iop(0, 12, "+", 0)
    M._st(p, X, "zp", 0)
    M.ladder_core(p, X)
    p.ld(0, L.W[A2.WN["i3"]])
    p.seti(3, 0, bias=b3)


def _post(p: Prog, L: C.Layout) -> None:
    """b x GAIN, the 1.6 Hz coupling, the HPF (juno_hpf by HPF), in place."""
    p.ld(0, L.W[A2.WN["bv"]])
    p.seti(0, 0)
    _ld(p, 8, S_CPL)
    p.fconst(7, GAIN)
    p.fconst(6, CPL_A)

    def head():                                  # F1 = b x GAIN less the coupling's
        p.ldi(1, 0, 0)
        p.fop(1, 1, "*", 7)
        p.fop(2, 1, "-", 8)
        p.fop(2, 2, "*", 6)
        p.fop(8, 8, "+", 2)
        p.fop(1, 1, "-", 8)

    def boost():
        _ld(p, 9, S_B1)
        _ld(p, 10, S_B2)

        def one():
            head()
            for st, a, b, y, x in ((9, HB[0], HB[1], 3, 1), (10, HB[2], HB[3], 4, 3)):
                p.fop(2, x, "-", st)
                _k(p, 2, 2, "*", a)
                p.fop(5, st, "+", 2)             # the low-pass
                p.fop(st, 5, "+", 2)
                p.fop(y, x, "-", 5)
                _k(p, y, y, "*", b)
                p.fop(y, y, "+", 5)
            _k(p, 4, 4, "*", HB[4])
            p.fop(1, 1, "+", 4)
            p.stpost(0, 1)
        p.loop_r(11, M.N, one)
        _sv(p, S_B1, 9)
        _sv(p, S_B2, 10)

    def flat():
        def one():
            head()
            p.stpost(0, 1)
        p.loop_r(11, M.N, one)

    def cut(g):
        def run():
            _ld(p, 9, S_HP)
            p.fconst(5, g)

            def one():
                head()
                p.fop(2, 1, "-", 9)
                p.fop(2, 2, "*", 5)
                p.fop(3, 9, "+", 2)
                p.fop(9, 3, "+", 2)
                p.fop(1, 1, "-", 3)
                p.stpost(0, 1)
            p.loop_r(11, M.N, one)
            _sv(p, S_HP, 9)
        return run
    _ld(p, 4, D_HPF)
    A2._dispatch(p, 4, (boost, flat, cut(HCUT[0]), cut(HCUT[1])))
    _sv(p, S_CPL, 8)


def half(p: Prog, L: C.Layout) -> None:
    """16 samples at I4 (I3 and I4 kept)."""
    W = L.W
    A2._ri(p, 0, "I4")
    p.st(W[A2.WN["bv"]], 0)
    p.seti(0, 0)
    _osc(p, L)
    _ladder(p, L)
    _post(p, L)
