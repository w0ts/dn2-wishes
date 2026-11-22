"""DRUM's RIDE and CRASH (one code, stage 4) in the DSL: dnfw.engines.drum.ref.Cymbal, operation for operation (its
squares' increments, its e^x, exp2, log2 and reciprocals PERC's and dmath's, as the reference computes them; the
filters' tangents PERC's sine polynomial; test/test_drum.py holds the two within DSL_TOL_DB).

scratch/drum-engine/drum_v4.py Cymbal (design.md section 12) with the User's choices: two TYPE entries sharing this
code (their starts on their pages, their levels here), the hats' metal (hats.metal, hats.drft, hats.colr, hats.inc_f2:
one copy of each), the exponential envelopes as rendered, SWEL's body band gliding up (retuned every half), the bell,
the rivets and GRP-like parts always run (a level of 0 when off: one cost at every setting).

A hit's values are set in the first half after the trig (`hit`); each half DRFT and the body's glide (`half`); then 16
samples a half (`sample`): the metal and the noise (hats.metal), the bell pair (stmlib's SVF, Q 75 / 32), the body
band, the top (the metal's first difference under a one-pole), the rivets, the three envelopes or ATK's swell, the stick,
the soft clip at g x vm with its level held, the declick, the output held under 0.99.

State words: the hats' metal words (their phases, increments, jitter, drift, mix, S_HN) are the hats' own numbers (the
shared subroutines read them); the rest are the hats' other words reused (each cymbal hit sets every word it reads).
"""

from __future__ import annotations

import math

from ...perc import machines as PM
from ...perc.dsl import Prog
from ..plaits import plaits_drumkit as PD
from ..plaits import plk as K
from . import dmath as M
from . import hats as HA
from . import kick as KI
from . import ref as R
from . import snare as SN
from .dmath import addk, ld, mulk, sv

FS = R.FS
S_ON, S_TYPE, S_LAST, S_DK, S_DC2 = KI.S_ON, KI.S_TYPE, KI.S_LAST, KI.S_DK, KI.S_DC2
S_HN, D_RING, D_MIX, T_X, T_TR, D_KA, D_KB = HA.S_HN, HA.D_RING, HA.D_MIX, HA.T_X, HA.T_TR, HA.D_KA, HA.D_KB
S_PH = HA.S_PH

S_E1, S_E2, S_E3, D_D1, D_D2 = 11, 13, 14, 15, 17
A_SVF, B_SVF, C_SVF = 21, 26, 31               # the bell pair, the body (stmlib Svf words g r h s1 s2)
# (at the hit: the SET's octaves, its ratio; 2026-11-21, live knobs: no longer the Svfs' words, which a live re-read
# keeps: the octaves in the squares' int increments, which each half sets again from D_INC0, the ratio in word 84)
T_LG, T_BR = HA.D_INC[0], 84
(D_D3, S_TL1, S_TL2) = 36, 37, 38
(S_RL, D_WA, D_WB, D_RIVT, S_SWX) = 42, 43, 44, 45, 46
D_WG = 41                                      # stage 5: BELL's second gain, the wash's (body and top)
D_SWD, D_FB, S_SWA, D_SWAD, D_ATKN = 82, 51, 52, 53, 54
D_ATKM, S_RA, S_SNAP, D_G, D_COMP, T_T60 = 57, 58, 59, 60, 61, 62
T_VM, T_TRB = HA.T_VM, 83                      # (the hats' vm word; T_TRB: the hit's tr, then BELL's level)
_OWN = ((S_E1, S_E2, S_E3, D_D1, D_D2) + tuple(range(A_SVF, C_SVF + 5)) + (D_D3, S_TL1, S_TL2, S_RL, D_WA, D_WB,
        D_RIVT, S_SWX, D_SWD, D_FB, S_SWA, D_SWAD, D_ATKN, D_ATKM, S_RA, S_SNAP, D_G, D_COMP, T_T60, T_TRB, D_WG, T_BR))
_HATS = (S_HN, T_VM, D_RING, D_MIX, T_X, HA.T_Y, T_TR, D_KA, D_KB, HA.D_DSTEP) + S_PH + HA.D_INC + HA.D_INC0 + HA.D_JIT \
    + HA.P_DRIFT + (HA.P_JRNG,)
assert len(set(_OWN)) == len(_OWN) and not set(_OWN) & set(_HATS) and not set(_OWN) & set(SN.SHARED)
WORDS = 85

TUNE, DCAY, TONE, BELL, COLR, HIT, DRIV = range(7)            # page 1 A..G
SET, SWEL, ATK, SNAP, NOIS, DRFT, RIVT, VEL = range(8)        # page 2 (q0..q6, VEL on H: q7)
assert (HA.COLR, HA.DRFT) == (COLR, DRFT)

TOP_A = float(R.onepole_a(R.CYM_TOP_HZ))
RV_A = float(R.onepole_a(R.RIVT_HZ))
SNAP_D = float(R.tau_coef(R.CYM_SNAP_TAU))
DK_D = KI.DK_D


def _set_of(p: Prog, L) -> None:
    """R2 = the SET (page 2 A, four detents: (knob x 4) >> 7, knob = trunc(q 127 + 0.5)). Clobbers R12."""
    KI._q(p, L, 2, SET)
    mulk(p, 2, 2, 127.0)
    addk(p, 2, 2, 0.5)
    p.trunc(2, 2)
    p.iconst(12, 4)
    p.mul_ssi(2, 2, 12)
    p.lsh(2, 2, -7)                              # 0..3


def _set(p: Prog, L) -> None:
    """the set R2 (0..3; the hats' is set 0, the 808's six): its squares' octaves over the first into T_LG.., its first
    square / 205.3 Hz in F6, its bell ratio into T_BR. Clobbers R0, R6, R12."""
    assert R.CYM_LOG2[0] == R.HAT_LOG2 and R.CYM_R0[0] == 1.0

    def put(s: int):
        def body():
            for i in range(1, 6):
                p.fconst(0, R.CYM_LOG2[s][i])
                sv(p, T_LG + i, 0)
            p.fconst(0, R.CYM_BELL_R[s])
            sv(p, T_BR, 0)
            p.fconst(6, R.CYM_R0[s])
        return body

    def rest():
        p.iconst(0, 2)
        p.if_(2, "EQ", 0, put(2), put(3), kind="i")
    p.iconst(0, 1)
    p.if_(2, "LT", 0, put(0), lambda: p.if_(2, "EQ", 0, put(1), rest, kind="i"), kind="i")
    p.fconst(0, 0.0)
    sv(p, T_LG, 0)
    assert all(R.CYM_LOG2[s][0] == 0.0 for s in range(4))


def metal_hit(p: Prog, L) -> None:
    """A hat's or a cymbal's hit (stage 4: one copy of what both set, ref.Hat.trig / ref.Cymbal.trig): vm (VEL: the hats'
    page 2 D, the cymbal's H), the pitch, the SET (the hats' the 808's six), COLR, the squares' increments and phases,
    NOIS's mix (the hats' page 1 D, the cymbal's page 2 E); then the type's own (hats.hit_rest, hit_rest); then DRFT
    (hats.drft_hit), the shared DC out cleared, the declick from the last sample. Clobbers R0-R15, I1, I12, n4."""
    def is_hat(then, else_):
        ld(p, 0, S_TYPE)
        p.iconst(1, HA.CLHH)
        p.iop(0, 0, "-", 1)
        p.lsh(0, 0, -1)                          # (type - CLHH) >> 1, logical: 0 for CLHH and OPHH alone
        p.ifz(0, "EQ", then, else_)
    is_hat(lambda: KI._q(p, L, 3, HA.VEL), lambda: KI._q(p, L, 3, VEL))
    KI.vm_f3(p, L)
    sv(p, T_VM, 2)
    KI.tune_oct(p, 48.0 / 127.0)
    M.exp2(p, 4, 3)
    sv(p, T_TRB, 4)                              # tr
    is_hat(lambda: p.iconst(2, 0), lambda: _set_of(p, L))
    _set(p, L)
    ld(p, 4, T_TRB)
    p.fop(4, 4, "*", 6)
    sv(p, T_TR, 4)                               # tr x the SET's first / 205.3 Hz (the hats': x 1.0, tr itself)
    HA.colr(p)
    # the squares: increments f1 (f / f1)^warp tr / FS (held under 0.45: hats.inc_f2) from the SET's octaves; the
    # phases at stage 1b's 0.13 i
    SN._ptr(p, T_LG)

    def one():
        p.ldpost(2, 1)
        HA.inc_f2(p)
        p.sti(HA.D_INC0[0] - T_LG - 1, 1, 4)
        p.trunc(4, 4)
        p.sti(HA.D_INC[0] - T_LG - 1, 1, 4)
    p.loop(L.W["n4"], 6, one)
    # (the squares' phases at stage 1b's 0.13 i: the hit's state, at the end)
    # NOIS: metal against noise; KA = (1 - ring) m / 6, KB = ring m / 3. Stage 5: a balance metal / noise (ref.balance:
    # m = g1, the noise g2), on the hats (page 1 D) x HAT_BAL_K, on the cymbals (page 2 E) x the kind's CYM_BAL_K
    def hat_mix():
        KI._u(p, 6, HA.NOIS)
        M.balance(p, 3, 2, 6)
        mulk(p, 3, 3, R.HAT_BAL_K)
        mulk(p, 2, 2, R.HAT_BAL_K)

    def cym_mix():                               # (stage 5: the same balance, x the kind's CYM_BAL_K)
        from . import drum as DR                 # (lazy: drum imports this module)
        KI._q(p, L, 6, NOIS)
        M.balance(p, 3, 2, 6)
        ld(p, 0, S_TYPE)
        p.iconst(1, DR.RIDE)
        p.if_(0, "EQ", 1, lambda: p.fconst(12, R.CYM_BAL_K["RIDE"]), lambda: p.fconst(12, R.CYM_BAL_K["CRASH"]),
              kind="i")
        p.fop(3, 3, "*", 12)
        p.fop(2, 2, "*", 12)
    is_hat(hat_mix, cym_mix)
    sv(p, D_MIX, 2)
    sv(p, HA.D_OMM, 3)
    p.fconst(12, 1.0)
    ld(p, 4, D_RING)
    p.fop(5, 12, "-", 4)
    p.fop(5, 5, "*", 3)
    mulk(p, 5, 5, 1.0 / 6.0)
    sv(p, D_KA, 5)
    p.fop(5, 4, "*", 3)
    mulk(p, 5, 5, 1.0 / 3.0)
    sv(p, D_KB, 5)
    is_hat(lambda: HA.hit_rest(p, L), lambda: hit_rest(p, L))
    HA.drft_hit(p, L)
    # the shared DC out after the drive starts again for the next KICK / SNARE; the declick from the last sample
    def start():                                 # the hit's state (not on a live re-read: dmath.on_hit)
        for i in range(6):
            p.iconst(0, R.HAT_PH0[i] & 0xFFFFFFFF)
            sv(p, S_PH[i], 0)
        p.fconst(0, 0.0)
        sv(p, S_DC2, 0)
        M.declick_on(p)
    M.on_hit(p, start)


def hit_rest(p: Prog, L) -> None:
    """The cymbal's own hit values (ref.Cymbal.trig) after metal_hit's. Clobbers R0-R15, I1, I12."""
    # the body at 7.15 kHz x 2^(3 (TONE - 0.5) + (vm - 1) / 2) (under 0.45 FS); the bell pair x clamp(tr, 1/4, 4) x
    # the SET's ratio
    KI._u(p, 2, TONE)
    addk(p, 2, 2, -0.5)
    mulk(p, 2, 2, 3.0)
    ld(p, 3, T_VM)
    addk(p, 3, 3, -1.0)
    mulk(p, 3, 3, 0.5)
    p.fop(3, 2, "+", 3)
    M.exp2(p, 4, 3)
    mulk(p, 4, 4, R.CYM_BODY_HZ)
    p.fconst(12, R.SVF_TOP)
    p.fop(4, 4, "MIN", 12)
    sv(p, D_FB, 4)
    ld(p, 2, T_TRB)
    K.clamp(p, 2, 0.25, 4.0)
    ld(p, 3, T_BR)
    p.fop(2, 2, "*", 3)
    for k, base in enumerate((A_SVF, B_SVF)):
        mulk(p, 3, 2, R.BELL_HZ[k])
        p.sti(2 * k, 4, 3)                       # (svf_sets' inputs at I4)
        p.fconst(3, R.BELL_Q[k])
        p.sti(2 * k + 1, 4, 3)
    # SWEL (page 2 B): the body from SWEL x 2 octaves down, gliding up (swx falls by sw_d each half), its level from
    # 1 - SWEL rising in 0.12 SWEL s
    def swel():                              # (per hit: the swell's start and its times)
        KI._q(p, L, 2, SWEL)
        sv(p, S_SWA, 2)
        p.fop(3, 2, "+", 2)
        sv(p, S_SWX, 3)
        KI._expo(p, 3, 2, R.SWEL_TAU[0] * FS / R.HALF, R.SWEL_TAU[1] * FS / R.HALF)
        KI._coef(p, D_SWD, 3, -1.0)
        ld(p, 2, S_SWA)
        mulk(p, 3, 2, R.SWEL_AMP * FS)
        p.fconst(12, 1e-4 * FS)
        p.fop(3, 3, "MAX", 12)
        KI._coef(p, D_SWAD, 3, -1.0)
    M.on_hit(p, swel)
    ld(p, 2, S_SWX)
    mulk(p, 2, 2, -1.0)
    M.exp2(p, 4, 2)
    ld(p, 3, D_FB)
    p.fop(4, 3, "*", 4)
    p.sti(4, 4, 4)
    p.fconst(4, R.CYM_BODY_Q)
    p.sti(5, 4, 4)
    SN.svf_sets(p, L, A_SVF, 3, R.SVF_TOP)
    # BELL (page 1 D, stage 5): a balance bell / wash (ref.balance): the bell 4 g1^1.5 (g1 x sqrt(max(g1, 2^-20))), the
    # pair's weights 1.4 / 75 and 1 / 32; the wash (body and top) x g2
    KI._u(p, 4, BELL)
    M.balance(p, 2, 3, 4)
    sv(p, D_WG, 3)
    p.fconst(12, R.BELL_FLOOR)
    p.fop(8, 2, "MAX", 12)
    M.log2(p)
    mulk(p, 13, 9, 0.5)
    M.exp2(p, 4, 13)
    mulk(p, 3, 2, 4.0)
    p.fop(3, 3, "*", 4)
    sv(p, T_TRB, 3)                              # bl
    mulk(p, 4, 3, R.BELL_W[0] / R.BELL_Q[0])
    sv(p, D_WA, 4)
    mulk(p, 4, 3, R.BELL_W[1] / R.BELL_Q[1])
    sv(p, D_WB, 4)
    # RIVT (page 2 G): 0.3 RIVT^2
    KI._q(p, L, 2, RIVT)
    p.fop(2, 2, "*", 2)
    mulk(p, 2, 2, R.RIVT_MAX)
    sv(p, D_RIVT, 2)
    # DCAY: the body's T60 0.15 .. 12 s, the bell's x 1.3; HIT: the top's 20 ms .. 3 s
    KI._u(p, 2, DCAY)
    KI._expo(p, 3, 2, R.CYM_T60[0] * FS, R.CYM_T60[1] * FS)
    sv(p, T_T60, 3)
    mulk(p, 3, 3, R.BELL_TX)
    KI._coef(p, D_D1, 3, -R.LN_THOUSAND)
    ld(p, 3, T_T60)
    KI._coef(p, D_D2, 3, -R.LN_THOUSAND)
    KI._u(p, 2, HIT)
    KI._expo(p, 3, 2, R.CYM_HIT_T60[0] * FS, R.CYM_HIT_T60[1] * FS)
    KI._coef(p, D_D3, 3, -R.LN_THOUSAND)
    # SNAP (page 2 D): the stick 3 SNAP x (0.5 + 0.5 vm)
    KI._q(p, L, 2, SNAP)
    mulk(p, 2, 2, R.CYM_SNAP_MAX)
    ld(p, 3, T_VM)
    mulk(p, 3, 3, 0.5)
    addk(p, 3, 3, 0.5)
    p.fop(2, 2, "*", 3)
    sv(p, T_T60, 2)                              # (the level held below reads it: S_SNAP decays)
    # DRIV: g = 1 + 20 DRIV^2, the clip at g x vm; its level held (KICK's) x the type's level x 1 / ((1 + SNAP / 2)
    # (1 + BELL's / 4) (1 + ring / 2) (1 + NOIS))
    KI.drive_level(p, DRIV, 20.0, D_G, D_COMP)
    ld(p, 0, S_TYPE)
    from . import drum as DR                     # (lazy: drum imports this module)
    p.iconst(1, DR.RIDE)
    p.if_(0, "EQ", 1, lambda: p.fconst(4, R.CYM_GAIN["RIDE"]), lambda: p.fconst(4, R.CYM_GAIN["CRASH"]), kind="i")
    ld(p, 3, D_COMP)
    p.fop(4, 3, "*", 4)
    sv(p, D_COMP, 4)
    # the level held against the pitch above an octave up (ref.CYM_TH_*): R6 = 2^(0.3 max(x - 1, 0)), x TUNE + note
    KI.tune_oct(p, 48.0 / 127.0)
    addk(p, 3, 3, -R.CYM_TH_X0)
    p.fconst(12, 0.0)
    p.fop(3, 3, "MAX", 12)
    mulk(p, 3, 3, R.CYM_TH_A)
    M.exp2(p, 6, 3)
    ld(p, 2, T_T60)
    mulk(p, 2, 2, 0.5)
    addk(p, 2, 2, 1.0)
    ld(p, 3, T_TRB)
    mulk(p, 3, 3, 0.25)
    addk(p, 3, 3, 1.0)
    p.fop(2, 2, "*", 3)
    ld(p, 3, D_RING)
    mulk(p, 3, 3, 0.5)
    addk(p, 3, 3, 1.0)
    p.fop(2, 2, "*", 3)
    ld(p, 3, D_MIX)
    addk(p, 3, 3, 1.0)
    p.fop(2, 2, "*", 3)
    p.fop(2, 2, "*", 6)                          # x the pitch's
    PM.recip(p, 5, 2)
    ld(p, 2, D_G)
    ld(p, 3, T_VM)
    p.fop(2, 2, "*", 3)
    p.fop(2, 2, "*", 5)                          # the level held into the clip (2026-11-21: no flat top at DRIV 0)
    sv(p, D_G, 2)
    # the hit's state (2026-11-21, live knobs: not on a re-read, dmath.on_hit): SNAP's stick level (T_T60); ATK (page
    # 2 C): 0 none, else a 60 dB swell over 5 ms .. 2 s (trunc samples), x 1000^(1 / n) a sample from 1e-3; the
    # envelopes full; the top, the rivets at rest (DRFT, the declick: metal_hit)
    def start():
        ld(p, 2, T_T60)
        sv(p, S_SNAP, 2)
        KI._q(p, L, 2, ATK)

        def swell():
            KI._expo(p, 3, 2, R.CYM_ATK[0] * FS, R.CYM_ATK[1] * FS)
            p.trunc(4, 3)
            sv(p, D_ATKN, 4)
            p.iconst(12, 0)
            p.float_(5, 4, 12)
            PM.recip(p, 6, 5)
            mulk(p, 13, 6, math.log2(1000.0))
            M.exp2(p, 7, 13)
            sv(p, D_ATKM, 7)
            p.fconst(0, 1e-3)
            sv(p, S_RA, 0)

        def none():
            p.iconst(0, 0)
            sv(p, D_ATKN, 0)
            p.fconst(0, 1.0)
            sv(p, D_ATKM, 0)
            sv(p, S_RA, 0)
        p.fconst(12, 0.0)
        p.if_(2, "GT", 12, swell, none)
        p.fconst(0, 1.0)
        for k in (S_E1, S_E2, S_E3):
            sv(p, k, 0)
        p.fconst(0, 0.0)
        for k in (S_TL1, S_TL2, S_RL):
            sv(p, k, 0)
        p.iconst(0, 0)
        sv(p, S_HN, 0)
    M.on_hit(p, start)


def half(p: Prog, L) -> None:
    """Each half before its samples (ref.Cymbal.half): DRFT (hats.drft), then the body's glide: swx x sw_d, the body
    at fb 2^-swx (under 0.45 FS), its g, r, h set and its state kept. Clobbers R0-R15, I1, I12, n4."""
    HA.drft(p, L)
    ld(p, 2, S_SWX)
    ld(p, 3, D_SWD)
    p.fop(2, 2, "*", 3)
    sv(p, S_SWX, 2)
    mulk(p, 2, 2, -1.0)
    M.exp2(p, 4, 2)
    ld(p, 3, D_FB)
    p.fop(4, 3, "*", 4)
    p.fconst(12, R.SVF_TOP)
    p.fop(4, 4, "MIN", 12)
    mulk(p, 5, 4, 0.5 / FS)                      # pi fc / FS = 2 pi x
    K.sinp(p, 6, 5)
    K.cosp(p, 7, 5)
    PM.recip(p, 8, 7)
    p.fop(8, 6, "*", 8)                          # g
    p.fconst(9, R.CYM_BODY_Q)
    SN._ptr(p, C_SVF)
    PD.svfset(p)


def sample(p: Prog, L) -> None:
    """One sample at I4 (ref.Cymbal.sample). Clobbers R0-R15, I1, I12."""
    HA.metal(p)                                  # F8 x, F9 the noise's sample
    p.fpass(6, 8)
    p.fpass(5, 9)
    # the bell pair (bp x their weights), the body (bp x r)
    SN._ptr(p, A_SVF)
    PD.svf(p)
    ld(p, 12, D_WA)
    p.fop(7, 10, "*", 12)
    p.fpass(8, 6)
    SN._ptr(p, B_SVF)
    PD.svf(p)
    ld(p, 12, D_WB)
    p.fop(10, 10, "*", 12)
    p.fop(7, 7, "+", 10)                         # bell
    p.fpass(8, 6)
    SN._ptr(p, C_SVF)
    PD.svf(p)
    p.ldi(12, 1, 1)
    p.fop(4, 10, "*", 12)                        # body
    # the top: tl2 += ((x - tl1) - tl2) ta, tl1 = x
    ld(p, 0, S_TL1)
    ld(p, 1, S_TL2)
    p.fop(2, 6, "-", 0)
    p.fop(2, 2, "-", 1)
    mulk(p, 2, 2, TOP_A)
    p.fop(1, 1, "+", 2)
    sv(p, S_TL2, 1)
    sv(p, S_TL1, 6)
    # the rivets: c = the noise where |noise| > 0.94, else 0; rl += (c - rl) rva; c - rl
    K.fabs(p, 2, 5)
    p.fconst(12, R.RIVT_TH)
    p.if_(2, "GT", 12, lambda: p.fpass(3, 5), lambda: p.fconst(3, 0.0))
    ld(p, 0, S_RL)
    p.fop(2, 3, "-", 0)
    mulk(p, 2, 2, RV_A)
    p.fop(0, 0, "+", 2)
    sv(p, S_RL, 0)
    p.fop(3, 3, "-", 0)
    # the envelopes: ATK's swell (all three held) until its end, then the bell's, the body's, the top's decays
    ld(p, 0, S_HN)
    ld(p, 2, D_ATKN)

    def swell():
        ld(p, 9, S_RA)
        ld(p, 12, D_ATKM)
        p.fop(9, 9, "*", 12)
        p.fconst(12, 1.0)
        p.fop(9, 9, "MIN", 12)
        sv(p, S_RA, 9)
        p.fpass(10, 9)
        p.fpass(11, 9)

    def decay():
        for r, s, d in ((9, S_E1, D_D1), (10, S_E2, D_D2), (11, S_E3, D_D3)):
            ld(p, r, s)
            ld(p, 12, d)
            p.fop(r, r, "*", 12)
            sv(p, s, r)
    p.if_(0, "LT", 2, swell, decay, kind="i")
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    sv(p, S_HN, 0)
    # the stick (k = 1 + snap, then it falls), the body's swell (1 - swa, swa falling)
    ld(p, 2, S_SNAP)
    addk(p, 8, 2, 1.0)
    ld(p, 12, D_WG)                              # the wash's gain (BELL's balance)
    p.fop(8, 8, "*", 12)
    p.fconst(12, SNAP_D)
    p.fop(2, 2, "*", 12)
    sv(p, S_SNAP, 2)
    ld(p, 2, S_SWA)
    ld(p, 12, D_SWAD)
    p.fop(2, 2, "*", 12)
    sv(p, S_SWA, 2)
    p.fconst(12, 1.0)
    p.fop(2, 12, "-", 2)
    # y = bell a1 + body a2 (1 - swa) k + top 0.7 a3 k + (c - rl) RIVT a1
    p.fop(7, 7, "*", 9)
    p.fop(4, 4, "*", 10)
    p.fop(4, 4, "*", 2)
    p.fop(4, 4, "*", 8)
    p.fop(7, 7, "+", 4)
    mulk(p, 1, 1, R.CYM_TOP_LVL)
    p.fop(1, 1, "*", 11)
    p.fop(1, 1, "*", 8)
    p.fop(7, 7, "+", 1)
    ld(p, 12, D_RIVT)
    p.fop(3, 3, "*", 12)
    p.fop(3, 3, "*", 9)
    p.fop(7, 7, "+", 3)
    # the soft clip at g x vm, its level held; the declick; the output held under 0.99
    ld(p, 14, D_G)
    p.fop(15, 7, "*", 14)
    PD.soft(p)
    ld(p, 4, D_COMP)
    p.fop(4, 15, "*", 4)
    ld(p, 6, S_DK)
    p.fop(4, 4, "+", 6)
    p.fconst(12, DK_D)
    p.fop(6, 6, "*", 12)
    sv(p, S_DK, 6)
    K.clamp(p, 4, -R.CYM_TOP, R.CYM_TOP)
    sv(p, S_LAST, 4)
    p.stpost(4, 4)
