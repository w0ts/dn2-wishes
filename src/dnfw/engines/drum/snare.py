"""DRUM's SNARE in the DSL: dnfw.engines.drum.ref.Snare, operation for operation (its sines PERC's polynomial, its
e^x, log2 and reciprocals dmath's and PERC's; test/test_drum.py holds the two within DSL_TOL_DB).

A hit's values are set in the first half after the trig (`hit`, the note is the render's), the modes retuned at the
start of every half (`half`: the tension glide), then 16 samples a half (`sample`): four decaying sines (rotors), the
stick (a 0.3 ms pulse and high-passed noise), the wires (noise rattled by the body's phase, the clap bursts or a rise,
the wire band and the sizzle band (stmlib's SVF), a 350 Hz high-pass), the soft clip with its level held, the DC out
after it, the retrig's declick.

State words: DRUM's shared ones (S_TRIG .. S_RNG, S_UP, S_DC2, S_LAST, S_DK: kick.py's numbers) stay common, so a
retrig across types declicks; the rest are KICK's type-specific words reused (every hit sets each word its type
reads) and words above KICK's.
"""

from __future__ import annotations

import math

from ...md import core as MK
from ...mnm import core as C
from ...perc import machines as PM
from ...perc.dsl import Prog
from ..plaits import plaits_drumkit as PD
from ..plaits import plk as K
from . import dmath as M
from . import kick as KI
from . import ref as R
from .dmath import addk, clamp, ld, mulk, sv

FS = R.FS
S_TRIG, S_ON, S_TYPE, S_NOTE, S_RNG = KI.S_TRIG, KI.S_ON, KI.S_TYPE, KI.S_NOTE, KI.S_RNG
S_UP, S_DC2, S_LAST, S_DK = KI.S_UP, KI.S_DC2, KI.S_LAST, KI.S_DK
SHARED = (S_TRIG, S_ON, S_TYPE, S_NOTE, S_RNG, S_UP, S_DC2, S_LAST, S_DK)

S_RE = (5, 6, 7, 8)                            # the modes: rotors (re, im), their coefficients (c, s) a half
S_IM = (9, 10, 11, 12)
S_GL, S_STK, S_STKLP = 13, 14, 15
D_SZ = 17                                      # (KICK's S_FUP)
W_SVF, Z_SVF = 21, 26                          # stmlib Svf words g r h s1 s2: the wire band, the sizzle band
S_C = (31, 32, 33, 34)
S_S = (35, 36, 37, 38)
D_RS = (39, 40, 41, 42)                        # each mode's decay a sample
D_R = (43, 44, 45, 46)                         # each mode's ratio
(D_F, D_FB, D_GLIDE, S_BPH, D_OMB, D_B2, S_N, D_WSTART, S_BC, D_BD, S_BENV, D_WLVL, S_WDEC, S_WATT, D_WDD, D_WAD,
 S_WHP, D_G, D_COMP, T_X, T_ENV, T_WN, T_W, T_VM, T_T60) = range(47, 72)
D_BPG, D_HPG, D_WHEND, D_VT, D_VLO, D_VTN = range(72, 78)     # stage 3: WCHR's
WORDS = 78
_OWN = (S_RE + S_IM + (S_GL, S_STK, S_STKLP, D_SZ) + tuple(range(W_SVF, Z_SVF + 5)) + S_C + S_S + D_RS + D_R
        + tuple(range(D_F, WORDS)))
assert len(set(_OWN)) == len(_OWN) and not set(_OWN) & set(SHARED) and WORDS <= MK.NS

TUNE, DCAY, TONE, MODE, SNAP, NOIS, DRIV = range(7)            # page 1 A..G
WIRE, GLID, BUZZ, WTON, WATK, SIZZ, VEL, WCHR = range(8)       # page 2 (q0..q6; WCHR q7: PERC's TYPE record)

GL_D = float(R.tau_coef(R.GLIDE_TAU))
STK_D = float(R.tau_coef(R.STICK_TAU))
STK_A = float(R.onepole_a(R.STICK_HP_HZ))
B_D = float(R.tau_coef(R.BURST_TAU))
WHP_A = float(R.onepole_a(R.WIRE_HP_HZ))
DK_D = KI.DK_D
DC2_A = KI.DC2_A


def _ptr(p: Prog, k: int, t: int = 13) -> None:
    """I1 = state word k's address. Clobbers Rt, R12."""
    p.iconst(t, p.ioff(3, 4 * (MK.S0 + k)))
    p.geti(12, 3)
    p.iop(t, 12, "+", t)
    p.seti(1, t)


def svf_sets(p: Prog, L, base: int, n: int, top: float | None = None) -> None:
    """The N stmlib Svfs at words BASE, BASE + 5, ..: each set from the frequency (Hz) and the resonance its caller
    left at I4 + 2 k, I4 + 2 k + 1 (2026-11-21, live knobs: the half's output words, free until its samples; they
    were the Svf's s1 and s2, its state) (g = tan(pi fc / FS) as sin / cos, r, h); its state 0 in a hit only
    (dmath.on_hit: a live re-read keeps the filter ringing): _svf_set's arithmetic in a loop (2026-11-20, the DSP
    upload's room). TOP: the frequency held under it. Clobbers R0-R15, I1, I12, n4."""
    _ptr(p, base)

    def one():
        p.ldpost(4, 4)                           # fc
        if top is not None:
            p.fconst(12, top)
            p.fop(4, 4, "MIN", 12)
        mulk(p, 5, 4, 0.5 / FS)                  # pi fc / FS = 2 pi x
        K.sinp(p, 6, 5)
        K.cosp(p, 7, 5)
        PM.recip(p, 8, 7)
        p.fop(8, 6, "*", 8)                      # g
        p.ldpost(9, 4)                           # Q
        PD.svfset(p)

        def zero():
            p.iconst(0, 0)
            p.sti(3, 1, 0)
            p.sti(4, 1, 0)
        M.on_hit(p, zero)
        p.geti(13, 1)
        p.iconst(12, 4 * 5)
        p.iop(13, 12, "+", 13)
        p.seti(1, 13)
    p.loop(L.W["n4"], n, one)
    p.geti(13, 4)                                # I4 back at the half's first word
    p.iconst(12, -4 * 2 * n)
    p.iop(13, 12, "+", 13)
    p.seti(4, 13)


def hit(p: Prog, L) -> None:
    """The hit's values (ref.Snare.trig), in the first half after the trig. 2026-11-21 (live knobs): also run with
    S_TRIG 0 on the voice's turn (drum.half), the hit's state kept (dmath.on_hit): TUNE DCAY MODE WIRE GLID NOIS's
    wires BUZZ SIZZ WTON DRIV WCHR follow modulation and p-locks while the hit rings, the filters not reset; TONE,
    SNAP, WATK and NOIS's body level stay per hit. Clobbers R0-R15, I1, I12."""
    # vm = 1 + VEL (vel - 1)
    KI.vm(p, L, VEL)
    sv(p, T_VM, 2)
    # TUNE: whole semitones, trunc(knob x 48 / 127 + 0.5) - 24; f = 180 x 2^((st + note - 60) / 12) / FS
    KI.tune_oct(p, 48.0 / 127.0)
    M.exp2(p, 4, 3)
    mulk(p, 4, 4, R.SNARE_HZ)
    mulk(p, 4, 4, 1.0 / FS)
    sv(p, D_F, 4)
    # MODE: the ratios, analog .. membrane
    KI._u(p, 2, MODE)
    for k, (a, b) in enumerate(zip(R.ANALOG, R.MEMBRANE)):
        mulk(p, 3, 2, b - a)
        addk(p, 3, 3, a)
        sv(p, D_R[k], 3)
    # DCAY: t60 = 0.03 .. 2 s; the k-th mode decays in t60 / ratio: e^(-ln 1000 ratio / (t60 FS))
    KI._u(p, 2, DCAY)
    KI._expo(p, 3, 2, 0.03 * FS, 2.0 * FS)
    sv(p, T_T60, 3)
    PM.recip(p, 4, 3)
    sv(p, T_X, 4)
    # (a loop, I1 walking D_RS: 2026-11-20, the DSP upload's room; D_R is D_RS + 4)
    _ptr(p, D_RS[0])

    def decay():
        ld(p, 4, T_X)
        p.ldi(5, D_R[0] - D_RS[0], 1)
        p.fop(15, 4, "*", 5)
        mulk(p, 15, 15, -R.LN_THOUSAND)
        M.exp_neg(p)
        p.stpost(1, 14)
    p.loop(L.W["n4"], 4, decay)
    # the wires' decay: clamp(t60 x 0.25 .. 6 (WIRE), 0.03, 3 s)
    KI._q(p, L, 2, WIRE)
    KI._expo(p, 4, 2, 0.25, 6.0)
    ld(p, 3, T_T60)
    p.fop(4, 3, "*", 4)
    clamp(p, 4, 0.03 * FS, 3.0 * FS)
    KI._coef(p, D_WDD, 4, -R.LN_THOUSAND)
    # stage 5: NOIS, the balance body / wires (ref.balance): the modes x g1 (R6), the wires' level NOIS_MAX x g2
    KI._u(p, 5, NOIS)
    M.balance(p, 6, 7, 5)
    mulk(p, 7, 7, R.NOIS_MAX)
    sv(p, D_WLVL, 7)
    sv(p, T_W, 6)                                # (g1, for the hit's state below; T_W free till the samples)
    # GLID: 0 .. 12 % x (0.6 + 0.4 vm)
    KI._q(p, L, 2, GLID)
    mulk(p, 2, 2, R.GLIDE_MAX)
    ld(p, 3, T_VM)
    mulk(p, 3, 3, 0.4)
    addk(p, 3, 3, 0.6)
    p.fop(2, 2, "*", 3)
    sv(p, D_GLIDE, 2)
    # BUZZ: the rattle (1 - BUZZ, 2 BUZZ); SIZZ: the second band's level (NOIS: above)
    KI._q(p, L, 2, BUZZ)
    p.fconst(12, 1.0)
    p.fop(3, 12, "-", 2)
    sv(p, D_OMB, 3)
    p.fop(3, 2, "+", 2)
    sv(p, D_B2, 3)
    KI._q(p, L, 2, SIZZ)
    mulk(p, 2, 2, 0.8)
    sv(p, D_SZ, 2)
    # the hit's state (2026-11-21, live knobs: not on a re-read, dmath.on_hit): the modes' starting levels (TONE, NOIS's
    # body level g1 in T_W), at rest; the stick's level (SNAP); WATK's wires' start and bursts; the declick
    def start():
        ld(p, 6, T_W)
        # TONE: the modes' starting levels 1, 0.2 + 0.8 t, 0.8 t^2, 0.7 max(0, (TONE - 0.75) / 0.25);
        # t = min(TONE / 0.75, 1)
        KI._u(p, 2, TONE)
        mulk(p, 3, 2, 1.0 / 0.75)
        p.fconst(12, 1.0)
        p.fop(3, 3, "MIN", 12)
        mulk(p, 4, 3, 0.8)
        addk(p, 4, 4, 0.2)
        p.fop(4, 4, "*", 6)
        sv(p, S_RE[1], 4)
        p.fop(4, 3, "*", 3)
        mulk(p, 4, 4, 0.8)
        p.fop(4, 4, "*", 6)
        sv(p, S_RE[2], 4)
        addk(p, 4, 2, -0.75)
        mulk(p, 4, 4, 0.7 / 0.25)
        p.fconst(12, 0.0)
        p.fop(4, 4, "MAX", 12)
        p.fop(4, 4, "*", 6)
        sv(p, S_RE[3], 4)
        sv(p, S_RE[0], 6)
        p.fconst(0, 0.0)
        for k in S_IM + (S_STKLP, S_BPH, S_BENV, S_WHP):
            sv(p, k, 0)
        p.fconst(0, 1.0)
        for k in (S_GL, S_WDEC, S_WATT):
            sv(p, k, 0)
        p.iconst(0, 0)
        for k in (S_N, S_BC):
            sv(p, k, 0)
        # SNAP: the stick, 0 .. 1.6 x (0.5 + 0.5 vm)
        KI._u(p, 2, SNAP)
        mulk(p, 2, 2, R.STICK_MAX)
        ld(p, 3, T_VM)
        mulk(p, 3, 3, 0.5)
        addk(p, 3, 3, 0.5)
        p.fop(2, 2, "*", 3)
        sv(p, S_STK, 2)
        # WATK: the wires' rise 0.3 .. 8 ms (to the split); above it 1 .. 4 clap bursts 6 .. 10 ms apart, then the
        # wires
        KI._q(p, L, 2, WATK)
        sv(p, T_X, 2)
        p.fconst(12, R.WATK_SPLIT)
        p.fop(3, 2, "MIN", 12)
        mulk(p, 3, 3, 1.0 / R.WATK_SPLIT)
        KI._expo(p, 4, 3, 0.0003 * FS, 0.008 * FS)
        KI._coef(p, D_WAD, 4, -1.0)
        p.iconst(0, 0)
        sv(p, D_WSTART, 0)
        sv(p, D_BD, 0)
        ld(p, 2, T_X)
        p.fconst(12, R.WATK_SPLIT)

        def bursts():
            addk(p, 3, 2, -R.WATK_SPLIT)
            mulk(p, 3, 3, 1.0 / (1.0 - R.WATK_SPLIT))   # c
            mulk(p, 4, 3, 3.0)
            addk(p, 4, 4, 0.5)
            p.trunc(4, 4)
            p.iconst(12, 1)
            p.iop(4, 12, "+", 4)                     # nb = 1 + trunc(3 c + 0.5)
            mulk(p, 5, 3, 0.004)
            addk(p, 5, 5, 0.006)
            mulk(p, 5, 5, FS)
            p.trunc(5, 5)                            # D, whole samples
            sv(p, D_BD, 5)
            p.mul_ssi(4, 4, 5)
            sv(p, D_WSTART, 4)
        p.if_(2, "GT", 12, bursts)
        M.declick_on(p)                         # the declick from the last sample if a sound was on
    M.on_hit(p, start)
    # WTON: the wire band at 1.5 .. 9 kHz x 2^(vm - 1), Q 0.9; the sizzle's at min(2.2 x, 14 kHz), Q 1.2
    ld(p, 2, T_VM)
    addk(p, 2, 2, -1.0)
    M.exp2(p, 3, 2)
    KI._q(p, L, 2, WTON)
    KI._expo(p, 4, 2, 1500.0, 9000.0)
    p.fop(4, 4, "*", 3)
    p.sti(0, 4, 4)                               # (svf_sets' inputs at I4)
    mulk(p, 4, 4, R.SIZZ_RATIO)
    p.fconst(12, R.SIZZ_TOP_HZ)
    p.fop(4, 4, "MIN", 12)
    p.sti(2, 4, 4)
    p.fconst(4, R.WIRE_Q)
    p.sti(1, 4, 4)
    p.fconst(4, R.SIZZ_Q)
    p.sti(3, 4, 4)
    assert Z_SVF == W_SVF + 5
    svf_sets(p, L, W_SVF, 2)
    # DRIV: g = 1 + 20 DRIV^2, its level held (KICK's), the type's level; stage 3: the clip sees g x vm
    KI.drive_level(p, DRIV, 20.0, D_G, D_COMP, R.SNARE_GAIN)
    ld(p, 2, D_G)
    ld(p, 3, T_VM)
    p.fop(2, 2, "*", 3)
    sv(p, D_G, 2)
    wchr(p, L)


def wchr(p: Prog, L) -> None:
    """Stage 3 (ref.Snare.wchr): WCHR's knob k (q7 read back, trunc(q 127 + 0.5)); d = max(64 - k, 0) / 64 (the 909's
    end), w = max(k - 64, 0) / 63 (the 808's); the band's share 1 - w, the high-pass's 0.3 - 0.3 d + 0.7 w; the wire
    hold trunc(d 24 ms FS) after the wires' start; the threshold 2e-4 d, its floor (0, or none at d = 0) and
    1 / (1 - threshold). Clobbers R0-R6, R12-R15, I12."""
    KI._q(p, L, 2, WCHR)
    mulk(p, 2, 2, 127.0)
    addk(p, 2, 2, 0.5)
    p.trunc(2, 2)                                # k
    p.iconst(12, R.WCHR_MID)
    p.iop(3, 12, "-", 2)
    p.iconst(12, 0)
    p.iop(3, 3, "MAX", 12)
    p.float0(3, 3)
    mulk(p, 3, 3, 1.0 / R.WCHR_MID)              # d
    p.iconst(12, -R.WCHR_MID)
    p.iop(4, 12, "+", 2)
    p.iconst(12, 0)
    p.iop(4, 4, "MAX", 12)
    p.float0(4, 4)
    mulk(p, 4, 4, 1.0 / (127 - R.WCHR_MID))      # w
    p.fconst(12, 1.0)
    p.fop(5, 12, "-", 4)
    sv(p, D_BPG, 5)
    mulk(p, 5, 3, 0.3)
    p.fconst(12, 0.3)
    p.fop(5, 12, "-", 5)
    mulk(p, 6, 4, 0.7)
    p.fop(5, 5, "+", 6)
    sv(p, D_HPG, 5)
    mulk(p, 8, 3, R.WIRE_HOLD_MAX * FS)
    p.trunc(8, 8)
    ld(p, 9, D_WSTART)
    p.iop(8, 8, "+", 9)
    sv(p, D_WHEND, 8)
    mulk(p, 5, 3, R.WIRE_VT)
    sv(p, D_VT, 5)

    def thr():                                   # d > 0: the floor 0, 1 / (1 - threshold)
        p.fconst(12, 1.0)
        p.fop(6, 12, "-", 5)
        PM.recip(p, 6, 6)
        sv(p, D_VTN, 6)
        p.fconst(6, 0.0)
        sv(p, D_VLO, 6)

    def none():
        p.fconst(6, 1.0)
        sv(p, D_VTN, 6)
        p.fconst(6, R.WIRE_FLOOR)
        sv(p, D_VLO, 6)
    p.fconst(12, 0.0)
    p.if_(3, "GT", 12, thr, none)


def half(p: Prog, L) -> None:
    """Each half before its samples (ref.Snare.half): fb = f (1 + glide x gl); mode k at fb x ratio (under 0.45),
    c = rs cos, s = rs sin. Clobbers R0-R15, I1, I12, the counter word n4."""
    ld(p, 2, D_GLIDE)
    ld(p, 3, S_GL)
    p.fop(2, 2, "*", 3)
    addk(p, 2, 2, 1.0)
    ld(p, 1, D_F)
    p.fop(4, 1, "*", 2)
    sv(p, D_FB, 4)
    # the four modes in a loop, I1 walking S_S (2026-11-20, the DSP upload's room): S_C is S_S - 4, D_RS + 4, D_R + 8
    assert S_C[0] == S_S[0] - 4 and D_RS[0] == S_S[0] + 4 and D_R[0] == S_S[0] + 8
    _ptr(p, S_S[0])

    def mode():
        ld(p, 4, D_FB)
        p.ldi(5, 8, 1)
        p.fop(5, 4, "*", 5)
        p.fconst(12, R.MODE_TOP)
        p.fop(5, 5, "MIN", 12)
        sv(p, T_X, 5)
        K.cosp(p, 6, 5)
        p.ldi(7, 4, 1)
        p.fop(6, 6, "*", 7)
        p.sti(-4, 1, 6)
        ld(p, 5, T_X)
        K.sinp(p, 6, 5)
        p.ldi(7, 4, 1)
        p.fop(6, 6, "*", 7)
        p.stpost(1, 6)
    p.loop(L.W["n4"], 4, mode)


def sample(p: Prog, L) -> None:
    """One sample at I4 (ref.Snare.sample). Clobbers R0-R15, I1, I12."""
    ld(p, 2, S_GL)
    p.fconst(12, GL_D)
    p.fop(2, 2, "*", 12)
    sv(p, S_GL, 2)
    # the body: four rotors, re' = c re - s im, im' = s re + c im, their im's summed
    for k in range(4):
        ld(p, 0, S_C[k])
        ld(p, 1, S_S[k])
        ld(p, 2, S_RE[k])
        ld(p, 3, S_IM[k])
        p.fop(4, 0, "*", 2)
        p.fop(5, 1, "*", 3)
        p.fop(4, 4, "-", 5)
        sv(p, S_RE[k], 4)
        p.fop(5, 1, "*", 2)
        p.fop(6, 0, "*", 3)
        p.fop(5, 5, "+", 6)
        sv(p, S_IM[k], 5)
        if k == 0:
            p.fpass(7, 5)
        else:
            p.fop(7, 7, "+", 5)
    mulk(p, 7, 7, 0.8)
    # the stick: the noise less its 1800 Hz one-pole, the pulse for its first 13 samples, x its 1.5 ms decay
    M.noise(p, 9, S_RNG)
    ld(p, 10, S_STKLP)
    p.fop(11, 9, "-", 10)
    p.fconst(12, STK_A)
    p.fop(11, 12, "*", 11)
    p.fop(10, 10, "+", 11)
    sv(p, S_STKLP, 10)
    p.fop(9, 9, "-", 10)
    ld(p, 0, S_N)
    p.iconst(1, R.PULSE_N)
    p.if_(0, "LT", 1, lambda: addk(p, 9, 9, R.PULSE), kind="i")
    ld(p, 10, S_STK)
    p.fop(9, 9, "*", 10)
    p.fconst(12, STK_D)
    p.fop(10, 10, "*", 12)
    sv(p, S_STK, 10)
    p.fop(7, 7, "+", 9)
    sv(p, T_X, 7)                                # body x 0.8 + stick
    # the rattle: 1 - BUZZ + 2 BUZZ max(tri(the body's phase), 0)
    ld(p, 2, S_BPH)
    ld(p, 3, D_FB)
    p.fop(2, 2, "+", 3)
    PM.frac(p, 2)
    sv(p, S_BPH, 2)
    addk(p, 2, 2, -0.5)
    K.fabs(p, 3, 2)
    mulk(p, 3, 3, 4.0)
    addk(p, 3, 3, -1.0)
    p.fconst(12, 0.0)
    p.fop(3, 3, "MAX", 12)
    ld(p, 4, D_B2)
    p.fop(3, 4, "*", 3)
    ld(p, 4, D_OMB)
    p.fop(3, 4, "+", 3)                          # F3 rattle
    # the envelope: the bursts (a countdown of D samples while n < the wires' start), then the wires' rise and decay
    ld(p, 0, S_N)
    ld(p, 1, D_WSTART)

    def bursts():
        ld(p, 2, S_BC)

        def fire():
            p.fconst(4, 1.0)
            sv(p, S_BENV, 4)
            ld(p, 2, D_BD)
        p.ifz(2, "EQ", fire)
        p.dec(2, 2)
        sv(p, S_BC, 2)
    p.if_(0, "LT", 1, bursts, kind="i")
    ld(p, 4, S_BENV)
    ld(p, 5, D_WLVL)
    p.fop(6, 4, "*", 5)
    p.fconst(12, B_D)
    p.fop(4, 4, "*", 12)
    sv(p, S_BENV, 4)
    ld(p, 0, S_N)
    ld(p, 1, D_WSTART)

    def wires():
        ld(p, 7, S_WDEC)
        ld(p, 8, S_WATT)
        p.fop(9, 7, "-", 8)
        ld(p, 10, D_VT)                          # stage 3: the threshold close, max(e - vt, floor) / (1 - vt)
        p.fop(9, 9, "-", 10)
        ld(p, 10, D_VLO)
        p.fop(9, 9, "MAX", 10)
        ld(p, 10, D_VTN)
        p.fop(9, 9, "*", 10)
        p.fop(9, 9, "*", 5)
        p.fop(6, 6, "+", 9)
        ld(p, 1, D_WHEND)                        # the wire hold: the decay from the hold's end

        def fall():
            ld(p, 10, D_WDD)
            p.fop(7, 7, "*", 10)
            sv(p, S_WDEC, 7)
        p.if_(0, "GE", 1, fall, kind="i")
        ld(p, 10, D_WAD)
        p.fop(8, 8, "*", 10)
        sv(p, S_WATT, 8)
    p.if_(0, "GE", 1, wires, kind="i")
    sv(p, T_ENV, 6)
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    sv(p, S_N, 0)
    # the wires: noise x rattle through the wire band (bp + 0.3 hp) and the sizzle band (x SIZZ), a 350 Hz high-pass
    M.noise(p, 8, S_RNG)
    p.fop(8, 8, "*", 3)
    sv(p, T_WN, 8)
    _ptr(p, W_SVF)
    PD.svf(p)                                    # F9 hp, F10 bp
    ld(p, 11, D_HPG)                             # stage 3: bp x (1 - w) + hp x (0.3 - 0.3 d + 0.7 w) (WCHR)
    p.fop(9, 9, "*", 11)
    ld(p, 11, D_BPG)
    p.fop(10, 10, "*", 11)
    p.fop(10, 10, "+", 9)
    sv(p, T_W, 10)
    _ptr(p, Z_SVF)
    ld(p, 8, T_WN)
    PD.svf(p)
    ld(p, 9, D_SZ)
    p.fop(10, 9, "*", 10)
    ld(p, 11, T_W)
    p.fop(10, 11, "+", 10)
    ld(p, 11, S_WHP)
    p.fop(9, 10, "-", 11)
    p.fconst(12, WHP_A)
    p.fop(9, 12, "*", 9)
    p.fop(11, 11, "+", 9)
    sv(p, S_WHP, 11)
    p.fop(10, 10, "-", 11)
    ld(p, 9, T_ENV)
    p.fop(10, 10, "*", 9)                        # wires
    ld(p, 9, T_X)
    p.fop(15, 9, "+", 10)
    # the drive: the soft clip at gain g, its level held; the DC out after it (5 Hz); the declick
    ld(p, 14, D_G)
    p.fop(15, 15, "*", 14)
    sv(p, S_UP, 15)
    PD.soft(p)
    ld(p, 4, D_COMP)
    p.fop(4, 15, "*", 4)
    ld(p, 5, S_DC2)
    p.fop(6, 4, "-", 5)
    p.fconst(12, DC2_A)
    p.fop(6, 12, "*", 6)
    p.fop(5, 5, "+", 6)
    sv(p, S_DC2, 5)
    p.fop(4, 4, "-", 5)
    ld(p, 6, S_DK)
    p.fop(4, 4, "+", 6)
    p.fconst(12, DK_D)
    p.fop(6, 6, "*", 12)
    sv(p, S_DK, 6)
    sv(p, S_LAST, 4)
    p.stpost(4, 4)
