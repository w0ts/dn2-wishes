"""DRUM's TOM in the DSL: dnfw.engines.drum.ref.Tom, operation for operation (its sines PERC's polynomial, its e^x,
log2 and reciprocals dmath's and PERC's; test/test_drum.py holds the two within DSL_TOL_DB).

Stage 3 (2026-11-20): scratch/drum-engine/drum_v3.py Tom3 (stage 1b's Tom2 re-voiced: the 808's small sweep, the
909's partials 1.5 / 2.75 on their own decays at MODE's low end, SHAP a sine .. the 909's rounded triangle) with
KICK's drive level, its DC out after the drive and the declick, and RNGE (page 2 D: LOW / MID / HI add -6.5 / 0 /
+6.25 semitones to TUNE: ref.RNGE_ST, the choice as the page reads it, ref.rnge_of).

A hit's values are set in the first half after the trig (`hit`, the note is the render's), the skin modes retuned at
the start of every half (`half`: the sweep), then 16 samples a half (`sample`): the swept sine (phase in 0..1), the
triangle and its soft clip by SHAP, the body's decay, two rotors (the skin), the skin noise (a one-pole at 6 f0) and
the stick (its high-passed rest), the soft clip at g x vm with its level held, the DC out after it, the declick.

State words: DRUM's shared ones (kick.py's numbers) stay common; the rest are the other types' words reused (each TOM
hit sets every word TOM reads).
"""

from __future__ import annotations

from ...md import core as MK
from ...perc import machines as PM
from ...perc.dsl import Prog
from ..plaits import plaits_drumkit as PD
from ..plaits import plk as K
from . import dmath as M
from . import kick as KI
from . import ref as R
from . import snare as SN
from .dmath import addk, ld, mulk, sv

FS = R.FS
S_TRIG, S_ON, S_TYPE, S_NOTE, S_RNG = KI.S_TRIG, KI.S_ON, KI.S_TYPE, KI.S_NOTE, KI.S_RNG
S_UP, S_DC2, S_LAST, S_DK = KI.S_UP, KI.S_DC2, KI.S_LAST, KI.S_DK
SHARED = SN.SHARED

S_PH, S_SW, S_AMP, S_NZLP, S_NZ, S_STK = 5, 6, 7, 8, 9, 10
S_RE = (11, 12)                                # the skin modes: rotors (re, im), their coefficients (c, s) a half
S_IM = (13, 14)
S_C = (21, 22)
S_S = (23, 24)
D_R = (25, 26)                                 # each mode's ratio
D_RS = (27, 28)                                # each mode's decay a sample
(D_F0, D_SWAMT, D_SWD, D_AMPD, D_SHAP, D_NZD, D_NZA, D_G, D_COMP, T_VM, T_T60, T_X, T_Y, T_T9) = range(29, 43)
WORDS = 43
_OWN = ((S_PH, S_SW, S_AMP, S_NZLP, S_NZ, S_STK) + S_RE + S_IM + S_C + S_S + D_R + D_RS + tuple(range(D_F0, WORDS)))
assert len(set(_OWN)) == len(_OWN) and not set(_OWN) & set(SHARED) and WORDS <= MK.NS

TUNE, DCAY, SWEP, TONE, SNAP, NOIS, DRIV = range(7)            # page 1 A..G
SWTM, MODE, SHAP, RNGE, VEL = range(5)                         # page 2 (q0..q4)

STK_D = float(R.tau_coef(0.001))
DK_D = KI.DK_D
DC2_A = KI.DC2_A


def _rnge_oct(p: Prog, L, d: int) -> None:
    """Fd = RNGE's semitones / 12: its choice c = (trunc(q 127 + 0.5) x 3) >> 7 (ref.rnge_of), RNGE_ST[c] / 12.
    Clobbers R0, R2, R12."""
    KI._q(p, L, 2, RNGE)
    mulk(p, 2, 2, 127.0)
    addk(p, 2, 2, 0.5)
    p.trunc(2, 2)
    p.iconst(12, 3)
    p.mul_ssi(2, 2, 12)
    p.lsh(2, 2, -7)                              # the choice 0..2
    p.fconst(d, R.RNGE_ST[0] / 12.0)
    p.iconst(0, 1)
    p.if_(2, "EQ", 0, lambda: p.fconst(d, R.RNGE_ST[1] / 12.0), kind="i")
    p.iconst(0, 2)
    p.if_(2, "EQ", 0, lambda: p.fconst(d, R.RNGE_ST[2] / 12.0), kind="i")


def hit(p: Prog, L) -> None:
    """The hit's values (ref.Tom.trig), in the first half after the trig. 2026-11-21 (live knobs): also run with S_TRIG
    0 on the voice's turn (drum.half), the hit's state kept (dmath.on_hit): TUNE RNGE DCAY SWEP SWTM MODE SHAP DRIV
    follow modulation and p-locks while the hit rings; TONE, NOIS, SNAP stay per hit. Clobbers R0-R15, I1, I12."""
    # vm = 1 + VEL (vel - 1)
    KI.vm(p, L, VEL)
    sv(p, T_VM, 2)
    # TUNE (whole semitones, trunc(knob x 48 / 127 + 0.5) - 24) + RNGE + the note: f0 = 110 x 2^(.. / 12) Hz
    KI.tune_oct(p, 48.0 / 127.0)
    sv(p, T_X, 3)
    _rnge_oct(p, L, 4)
    ld(p, 3, T_X)
    p.fop(3, 3, "+", 4)
    M.exp2(p, 4, 3)
    mulk(p, 4, 4, R.TOM_HZ)                      # F4 f0 (Hz)
    sv(p, T_Y, 4)
    mulk(p, 5, 4, 1.0 / FS)
    sv(p, D_F0, 5)
    # the skin noise's one-pole at 6 f0 (under 0.45 FS)
    mulk(p, 2, 4, 6.0)
    p.fconst(12, 0.45 * FS)
    p.fop(2, 2, "MIN", 12)
    KI._onepole(p, D_NZA, 2)
    # SWEP: sw = 3 SWEP^2 x (0.6 + 0.4 vm); SWTM: its time 5 .. 400 ms
    KI._u(p, 2, SWEP)
    p.fop(2, 2, "*", 2)
    mulk(p, 2, 2, 3.0)
    ld(p, 3, T_VM)
    mulk(p, 3, 3, 0.4)
    addk(p, 3, 3, 0.6)
    p.fop(2, 2, "*", 3)
    sv(p, D_SWAMT, 2)
    KI._q(p, L, 2, SWTM)
    KI._expo(p, 3, 2, 0.005 * FS, 0.4 * FS)
    KI._coef(p, D_SWD, 3, -1.0)
    # DCAY: t60 = 0.04 .. 3 s; the body's decay, the skin noise's at 0.3 t60
    KI._u(p, 2, DCAY)
    KI._expo(p, 3, 2, 0.04 * FS, 3.0 * FS)
    sv(p, T_T60, 3)
    KI._coef(p, D_AMPD, 3, -R.LN_THOUSAND)
    ld(p, 3, T_T60)
    mulk(p, 3, 3, 0.3)
    KI._coef(p, D_NZD, 3, -R.LN_THOUSAND)
    # MODE: t9 = max(0, 1 - m / 0.25) toward the 909's partials, mo = max(0, (m - 0.25) / 0.75) the synthetic ..
    # membrane ratios 1.41 + 0.18 mo, 3.0 - 0.86 mo; each mode's T60 t60 / (1.3 r) (1 - t9) + its 909 T60 x t9
    KI._q(p, L, 2, MODE)
    mulk(p, 3, 2, -1.0 / R.TOM_MODE_909)
    addk(p, 3, 3, 1.0)
    p.fconst(12, 0.0)
    p.fop(3, 3, "MAX", 12)
    sv(p, T_T9, 3)                               # t9
    addk(p, 2, 2, -R.TOM_MODE_909)
    mulk(p, 2, 2, 1.0 / (1.0 - R.TOM_MODE_909))
    p.fconst(12, 0.0)
    p.fop(2, 2, "MAX", 12)                       # mo
    for k, (a, b, p9, t9s) in enumerate(((1.41, 0.18, R.TOM_P909[0], R.TOM_T909[0]),
                                         (3.0, -0.86, R.TOM_P909[1], R.TOM_T909[1]))):
        mulk(p, 4, 2, b)
        addk(p, 4, 4, a)                         # old
        p.fconst(12, p9)
        p.fop(5, 12, "-", 4)
        ld(p, 3, T_T9)
        p.fop(5, 5, "*", 3)
        p.fop(4, 4, "+", 5)                      # r
        sv(p, D_R[k], 4)
        sv(p, T_X, 2)
        mulk(p, 4, 4, 1.3)
        PM.recip(p, 5, 4)
        ld(p, 4, T_T60)
        p.fop(5, 4, "*", 5)
        p.fconst(12, 1.0)
        ld(p, 3, T_T9)
        p.fop(6, 12, "-", 3)
        p.fop(5, 5, "*", 6)
        mulk(p, 6, 3, t9s * FS)
        p.fop(5, 5, "+", 6)                      # the mode's T60 (samples)
        KI._coef(p, D_RS[k], 5, -R.LN_THOUSAND)
        ld(p, 2, T_X)
    # SHAP, DRIV (before the hit's state: 2026-11-21, live knobs)
    KI._q(p, L, 2, SHAP)
    sv(p, D_SHAP, 2)
    # DRIV: g = 1 + 20 DRIV^2, its level held (KICK's) x the type's level; the clip sees g x vm
    KI.drive_level(p, DRIV, 20.0, D_G, D_COMP, R.TOM_GAIN)
    ld(p, 2, D_G)
    ld(p, 3, T_VM)
    p.fop(2, 2, "*", 3)
    sv(p, D_G, 2)
    def start():                                 # (the hit's state: levels that decay, the modes at rest)
        # stage 5: NOIS, the balance body / skin noise (ref.balance): the body and the modes x g1 (R6), the noise 0.6 g2
        KI._u(p, 5, NOIS)
        M.balance(p, 6, 7, 5)
        mulk(p, 7, 7, 0.6)
        sv(p, S_NZ, 7)
        sv(p, S_AMP, 6)
        # TONE: the modes' starting levels 0.6 tone, 0.4 tone^2 (x g1)
        KI._u(p, 2, TONE)
        mulk(p, 3, 2, 0.6)
        p.fop(3, 3, "*", 6)
        sv(p, S_RE[0], 3)
        p.fop(3, 2, "*", 2)
        mulk(p, 3, 3, 0.4)
        p.fop(3, 3, "*", 6)
        sv(p, S_RE[1], 3)
        # SNAP: the stick 0.8 SNAP x vm
        KI._u(p, 2, SNAP)
        mulk(p, 2, 2, 0.8)
        ld(p, 3, T_VM)
        p.fop(2, 2, "*", 3)
        sv(p, S_STK, 2)
        # the hit starts: phase 0, the sweep and the body full, the modes and the noise at rest
        p.fconst(0, 0.0)
        for k in (S_PH, S_NZLP) + S_IM:
            sv(p, k, 0)
        p.fconst(0, 1.0)
        sv(p, S_SW, 0)
        M.declick_on(p)                         # the declick from the last sample if a sound was on
    M.on_hit(p, start)


def half(p: Prog, L) -> None:
    """Each half before its samples (ref.Tom.half): fb = f0 (1 + sweep amt x sw); mode k at fb x ratio (under
    0.45), c = cos x rs, s = sin x rs. Clobbers R0-R15, I12."""
    ld(p, 2, D_SWAMT)
    ld(p, 3, S_SW)
    p.fop(2, 2, "*", 3)
    addk(p, 2, 2, 1.0)
    ld(p, 1, D_F0)
    p.fop(4, 1, "*", 2)
    sv(p, T_Y, 4)
    for k in range(2):
        ld(p, 4, T_Y)
        ld(p, 5, D_R[k])
        p.fop(5, 4, "*", 5)
        p.fconst(12, R.MODE_TOP)
        p.fop(5, 5, "MIN", 12)
        sv(p, T_X, 5)
        K.cosp(p, 6, 5)
        ld(p, 7, D_RS[k])
        p.fop(6, 6, "*", 7)
        sv(p, S_C[k], 6)
        ld(p, 5, T_X)
        K.sinp(p, 6, 5)
        ld(p, 7, D_RS[k])
        p.fop(6, 6, "*", 7)
        sv(p, S_S[k], 6)


def sample(p: Prog, L) -> None:
    """One sample at I4 (ref.Tom.sample). Clobbers R0-R15, I1, I12."""
    # the pitch: f0 (1 + sweep amt x sw); sw decays; the phase in 0..1
    ld(p, 2, D_SWAMT)
    ld(p, 3, S_SW)
    p.fop(4, 2, "*", 3)
    addk(p, 4, 4, 1.0)
    ld(p, 1, D_F0)
    p.fop(4, 1, "*", 4)
    ld(p, 2, D_SWD)
    p.fop(3, 3, "*", 2)
    sv(p, S_SW, 3)
    ld(p, 5, S_PH)
    p.fop(5, 5, "+", 4)
    PM.frac(p, 5)
    sv(p, S_PH, 5)
    # the body: sin -> the rounded triangle by SHAP: s + (soft(2 tri) / soft(2) - s) SHAP, tri from frac(ph + 3/4)
    K.sinp(p, 6, 5)
    sv(p, T_X, 6)
    ld(p, 5, S_PH)
    addk(p, 5, 5, 0.75)
    PM.frac(p, 5)
    addk(p, 5, 5, -0.5)
    K.fabs(p, 5, 5)
    mulk(p, 5, 5, 4.0)
    addk(p, 5, 5, -1.0)
    mulk(p, 15, 5, R.TOM_TRI_G)
    PD.soft(p)
    mulk(p, 15, 15, R.TOM_TRI_N)
    ld(p, 6, T_X)
    p.fop(15, 15, "-", 6)
    ld(p, 7, D_SHAP)
    p.fop(15, 15, "*", 7)
    p.fop(6, 6, "+", 15)
    ld(p, 3, S_AMP)
    p.fop(6, 6, "*", 3)                          # body
    ld(p, 2, D_AMPD)
    p.fop(3, 3, "*", 2)
    sv(p, S_AMP, 3)
    # the skin: two rotors, re' = c re - s im, im' = s re + c im, their im's summed
    for k in range(2):
        ld(p, 0, S_C[k])
        ld(p, 1, S_S[k])
        ld(p, 2, S_RE[k])
        ld(p, 3, S_IM[k])
        p.fop(4, 0, "*", 2)
        p.fop(5, 1, "*", 3)
        p.fop(4, 4, "-", 5)
        sv(p, S_RE[k], 4)
        p.fop(5, 1, "*", 2)
        p.fop(8, 0, "*", 3)
        p.fop(5, 5, "+", 8)
        sv(p, S_IM[k], 5)
        if k == 0:
            p.fpass(7, 5)
        else:
            p.fop(7, 7, "+", 5)                  # skin
    p.fop(6, 6, "+", 7)                          # body + skin
    sv(p, T_X, 6)
    # the skin noise (its one-pole x NOIS, falling) and the stick (the rest of the noise x SNAP, falling in 1 ms)
    M.noise(p, 9, S_RNG)
    ld(p, 10, S_NZLP)
    p.fop(11, 9, "-", 10)
    ld(p, 12, D_NZA)
    p.fop(11, 12, "*", 11)
    p.fop(10, 10, "+", 11)
    sv(p, S_NZLP, 10)
    p.fop(9, 9, "-", 10)                         # nz - nz_lp
    ld(p, 11, S_NZ)
    p.fop(10, 10, "*", 11)                       # noise
    ld(p, 12, D_NZD)
    p.fop(11, 11, "*", 12)
    sv(p, S_NZ, 11)
    ld(p, 11, S_STK)
    p.fop(9, 9, "*", 11)                         # stick
    p.fconst(12, STK_D)
    p.fop(11, 11, "*", 12)
    sv(p, S_STK, 11)
    ld(p, 6, T_X)
    p.fop(6, 6, "+", 10)
    p.fop(6, 6, "+", 9)
    # the drive: the soft clip at g x vm, its level held; the DC out after it (5 Hz); the declick
    ld(p, 14, D_G)
    p.fop(15, 6, "*", 14)
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
