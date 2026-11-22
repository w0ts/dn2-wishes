"""DRUM's CLAP (stage 4) in the DSL: dnfw.engines.drum.ref.Clap, operation for operation (its exp2, log2, e^x and
reciprocals PERC's and dmath's, as the reference computes them, so the burst times are the same samples; the filters'
tangents PERC's sine polynomial; test/test_drum.py holds the two within DSL_TOL_DB).

scratch/drum-engine/drum_v4.py Clap (design.md section 12): noise through saw-shaped bursts (the 808's hand VCA:
instant up, exponential down) into a band-pass; the tail (the 808's reverberation VCA) on its own band-pass, with a
rise and the 808's long faint floor, opening with the last burst; a second clapper (GRP: its own noise, band +4 st and
burst times), always run (a level of 0 when off: one cost); TONE the bands' low- or high-pass share; the soft clip at
g x vm, its level held (KICK's); the output held under 0.99.

A hit (`hit`, the first half after the trig) sets the bands, their levels and both burst trains (times in samples and
levels: CNT, SPRD, HUMN's draws, RAMP); then 16 samples a half (`sample`): a burst starts where its sample comes (one
compare a train), the three bands, the envelopes, the clip.

State words: DRUM's shared ones (kick.py's numbers) stay common; the rest are the other types' words reused (each CLAP
hit sets every word CLAP reads), but P_RNG2 (GRP's generator, seeded at the machine's init and kept from hit to hit as
drum_v4's) and the hats' kept words (89..95), which CLAP never touches.
"""

from __future__ import annotations

from ...mnm import core as C
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
S_ON, S_RNG, S_LAST, S_DK, S_DC2 = KI.S_ON, KI.S_RNG, KI.S_LAST, KI.S_DK, KI.S_DC2

S_EB, S_EG, S_ET, S_EF, S_RISE, S_N, S_TNA, S_TNG, S_PA, S_PG, D_BD = range(5, 16)
D_TD = 17
A_SVF, T_SVF, G_SVF = 21, 26, 31               # the bursts' band, the tail's, GRP's (stmlib Svf words g r h s1 s2)
D_MIX = 36                                     # 3 x (lp, bp, hp) weights: A, T, G (G's x GRP)
D_FD, D_TR, D_TL, D_G, D_COMP = 45, 46, 47, 48, 49
TA, LA, TG, LG = 50, 59, 67, 76                # the trains: 9 times (the last -1), 8 levels each (a level 9 words on)
T_VM, T_FC, T_Q, T_N = 84, 85, 86, 87
P_RNG2 = 88                                    # GRP's generator (kept; drum.init seeds it)
WORDS = 89
_OWN = tuple(range(5, 16)) + (D_TD,) + tuple(range(21, WORDS))
assert LA - TA == LG - TG == 9 and TG == TA + 17 and LG + 8 == T_VM and len(set(_OWN)) == len(_OWN)
assert not set(_OWN) & set(SN.SHARED)

TUNE, DCAY, TONE, CNT, SPRD, TAIL, DRIV = range(7)            # page 1 A..G
SNAP, Q, HUMN, GRP, TLTN, TATK, RAMP, VEL = range(8)          # page 2 (q0..q6, VEL on H: q7)
DK_D = KI.DK_D
END = -1                                       # a train's end (no sample is -1)


def _lcg(p: Prog, d: int) -> None:
    """Fd = the next draw of the generator whose word is in R0 (M.noise's arithmetic). Clobbers R12, R14."""
    p.iconst(14, 1664525)
    p.mul_ssi(0, 0, 14)
    p.iconst(14, 1013904223)
    p.iop(0, 14, "+", 0)
    p.iconst(12, -31)
    p.float_(d, 0, 12)


def _train(p: Prog) -> None:
    """one train (ref.clap_train): R1 bursts, F2 their spacing (samples), F3 0.35 HUMN, F4 0.25 HUMN, F5 the level's
    step, F6 the first level, F7 the first time, R0 the generator's word, I1 at its times: each burst's level
    max(lv (1 + 0.25 HUMN r), 0.05) (9 words on) and time trunc(t + 0.5), t += sp (1 + 0.35 HUMN r), lv += step; then
    the end mark. One copy (a leaf). Clobbers R0, R1, R6-R12, R14, I1, I12."""
    def body():
        def one():
            _lcg(p, 8)
            p.fop(9, 4, "*", 8)
            addk(p, 9, 9, 1.0)
            p.fop(10, 6, "*", 9)
            p.fconst(11, 0.05)
            p.fop(10, 10, "MAX", 11)
            addk(p, 11, 7, 0.5)
            p.trunc(11, 11)
            p.sti(LA - TA, 1, 10)
            p.stpost(1, 11)
            _lcg(p, 8)
            p.fop(9, 3, "*", 8)
            addk(p, 9, 9, 1.0)
            p.fop(9, 2, "*", 9)
            p.fop(7, 7, "+", 9)
            p.fop(6, 6, "+", 5)
        p.loop_r(1, None, one, one=12)
        p.iconst(11, END)
        p.sti(0, 1, 11)
    p.call("dr_ctrain", body)


def _start_train(p: Prog, base: int, s_rng: int, sp_x: float, hum_min: float | None, t0) -> None:
    """a train at word BASE from generator word S_RNG: SPRD's spacing (S_EB) x SP_X, HUMN (S_ET, at least HUM_MIN),
    RAMP (S_EG), the count (T_N); T0() puts the first time in F7 (it may use R0, R12-R15). Then the train's first time
    in S_TNA / S_TNG and its pointer. Clobbers R0-R15, I1, I12."""
    ld(p, 9, S_ET)
    if hum_min is not None:
        p.fconst(12, hum_min)
        p.fop(9, 9, "MAX", 12)
    mulk(p, 3, 9, 0.35)
    mulk(p, 4, 9, 0.25)
    ld(p, 1, T_N)
    ld(p, 10, S_EG)

    def ramp():                                  # RAMP over the train: from 1 - RAMP / 2 by RAMP / (n - 1)
        p.iconst(12, -1)
        p.iop(11, 12, "+", 1)
        p.iconst(12, 0)
        p.float_(11, 11, 12)
        PM.recip(p, 5, 11)
        p.fop(5, 10, "*", 5)
        mulk(p, 6, 10, -0.5)
        addk(p, 6, 6, 1.0)

    def flat():
        p.fconst(5, 0.0)
        p.fconst(6, 1.0)
    p.iconst(12, 1)
    p.if_(1, "GT", 12, ramp, flat, kind="i")
    t0()
    ld(p, 2, S_EB)
    if sp_x != 1.0:
        mulk(p, 2, 2, sp_x)
    ld(p, 1, T_N)
    ld(p, 0, s_rng)
    SN._ptr(p, base)
    _train(p)
    sv(p, s_rng, 0)


def hit(p: Prog, L) -> None:
    """The hit's values (ref.Clap.trig), in the first half after the trig. Clobbers R0-R15, I1, I12, n4."""
    KI.vm(p, L, VEL)
    sv(p, T_VM, 2)
    # the band: 1 kHz x 2^(TUNE + note) x 2^((vm - 1) / 2); Q 0.6 .. 8; the tail's x 2^(2 (TLTN - 0.5)), Q x 0.6;
    # GRP's x 1.26, Q x 0.8
    KI.tune_oct(p, 48.0 / 127.0)
    ld(p, 2, T_VM)
    addk(p, 2, 2, -1.0)
    mulk(p, 2, 2, 0.5)
    p.fop(3, 3, "+", 2)
    M.exp2(p, 4, 3)
    mulk(p, 4, 4, R.CLAP_HZ)
    sv(p, T_FC, 4)
    p.sti(0, 4, 4)                               # (svf_sets' inputs at I4: 2026-11-21, live knobs)
    KI._q(p, L, 2, Q)
    KI._expo(p, 9, 2, *R.CLAP_Q)
    sv(p, T_Q, 9)
    p.sti(1, 4, 9)
    mulk(p, 5, 9, R.CLAP_TAIL_QX)
    p.sti(3, 4, 5)
    mulk(p, 5, 9, R.CLAP_GRP_QX)
    p.sti(5, 4, 5)
    # the tail's trim above Q's centre (ref.CLAP_TQ_*): 2^min(0, -0.71 (Q - 0.5)), kept in D_TL until TAIL's balance
    addk(p, 2, 2, -R.CLAP_TQ_U0)
    mulk(p, 2, 2, -R.CLAP_TQ_K)
    p.fconst(12, 0.0)
    p.fop(2, 2, "MIN", 12)
    M.exp2(p, 3, 2)
    sv(p, D_TL, 3)
    KI._q(p, L, 2, TLTN)
    addk(p, 2, 2, -0.5)
    mulk(p, 2, 2, 2.0)
    M.exp2(p, 3, 2)
    ld(p, 4, T_FC)
    p.fop(3, 4, "*", 3)
    p.sti(2, 4, 3)
    mulk(p, 3, 4, R.CLAP_GRP_RATIO)
    p.sti(4, 4, 3)
    SN.svf_sets(p, L, A_SVF, 3, R.SVF_TOP)
    # the bands' levels held: nb = sqrt(1000 / (q fc)); TONE: hi = max(2 TONE - 1, 0) 0.2, lo = max(1 - 2 TONE, 0) 1.6;
    # each band's weights (lo nb, nb, hi nb), the tail's nb x sqrt(1 / 0.6), GRP's x sqrt(1 / (0.8 x 1.26)) x GRP
    ld(p, 2, T_Q)
    p.fconst(12, R.CLAP_NB_QMIN)                 # q at least 1.25 for the level held (2026-11-21)
    p.fop(2, 2, "MAX", 12)
    ld(p, 3, T_FC)
    p.fconst(12, R.CLAP_NB_FMIN)                 # fc at least 250 Hz for the level held (2026-11-21)
    p.fop(3, 3, "MAX", 12)
    p.fop(2, 2, "*", 3)
    PM.recip(p, 8, 2)
    mulk(p, 8, 8, R.CLAP_HZ)
    M.log2(p)
    mulk(p, 13, 9, 0.5)
    M.exp2(p, 4, 13)                             # nb
    KI._u(p, 2, TONE)
    p.fop(2, 2, "+", 2)
    addk(p, 3, 2, -1.0)
    p.fconst(12, 0.0)
    p.fop(3, 3, "MAX", 12)
    mulk(p, 3, 3, R.CLAP_HI)                     # hi
    p.fconst(12, 1.0)
    p.fop(5, 12, "-", 2)
    p.fconst(12, 0.0)
    p.fop(5, 5, "MAX", 12)
    mulk(p, 5, 5, 2.0 * R.CLAP_LO)               # lo
    KI._q(p, L, 7, GRP)
    # stage 5: TAIL, the balance bursts / tail (ref.balance): the bursts' bands (A, G) x g1 (R11), the tail's level 2 g2
    KI._u(p, 13, TAIL)
    M.balance(p, 11, 14, 13)
    p.fop(14, 14, "+", 14)
    ld(p, 12, D_TL)
    p.fop(14, 14, "*", 12)                       # x the tail's trim above Q 64
    sv(p, D_TL, 14)
    for k, scale in enumerate((None, R.CLAP_NB_T, R.CLAP_NB_G)):
        if scale is None:
            p.fop(6, 4, "*", 11)
        else:
            mulk(p, 6, 4, scale)
            if k == 2:
                p.fop(6, 6, "*", 11)
        p.fop(8, 5, "*", 6)
        p.fpass(9, 6)
        p.fop(10, 3, "*", 6)
        if k == 2:
            p.fop(8, 8, "*", 7)
            p.fop(9, 9, "*", 7)
            p.fop(10, 10, "*", 7)
        for j, r in enumerate((8, 9, 10)):
            sv(p, D_MIX + 3 * k + j, r)
    # the trains: CNT's 1 + (knob x 8) >> 7 bursts, SPRD 3 .. 30 ms apart (samples), HUMN, RAMP (-0.6 .. 0.6); GRP's
    # from 0.3 .. 0.7 SPRD (its generator's draw), SPRD x 1.07 apart, HUMN at least 0.5
    # (the trains: CNT SPRD HUMN RAMP and GRP's draw, the hit's state: at the end, 2026-11-21, live knobs)
    # SNAP: a burst's time constant 15 .. 0.8 ms; DCAY: the tail's T60 50 ms .. 4 s, the floor's x 8.6 (under 6 s);
    # TATK: the tail's rise 0.3 .. 80 ms (TAIL: above)
    KI._q(p, L, 2, SNAP)
    p.fconst(12, 1.0)
    p.fop(2, 12, "-", 2)
    KI._expo(p, 3, 2, R.CLAP_SNAP[0] * FS, R.CLAP_SNAP[1] * FS)
    KI._coef(p, D_BD, 3, -1.0)
    KI._u(p, 2, DCAY)
    KI._expo(p, 3, 2, R.CLAP_T60[0] * FS, R.CLAP_T60[1] * FS)
    sv(p, T_FC, 3)
    KI._coef(p, D_TD, 3, -R.LN_THOUSAND)
    ld(p, 3, T_FC)
    mulk(p, 3, 3, R.CLAP_FLOOR_X)
    p.fconst(12, R.CLAP_FLOOR_MAX * FS)
    p.fop(3, 3, "MIN", 12)
    KI._coef(p, D_FD, 3, -R.LN_THOUSAND)
    KI._q(p, L, 2, TATK)
    KI._expo(p, 3, 2, R.CLAP_TATK[0] * FS, R.CLAP_TATK[1] * FS)
    KI._coef(p, D_TR, 3, -1.0)
    ld(p, 2, D_TR)
    p.fconst(12, 1.0)
    p.fop(2, 12, "-", 2)
    sv(p, D_TR, 2)
    # DRIV: g = 1 + 20 DRIV^2, its level held (KICK's) x the type's level; the clip at g x vm
    KI.drive_level(p, DRIV, 20.0, D_G, D_COMP, R.CLAP_GAIN)
    ld(p, 2, D_G)
    ld(p, 3, T_VM)
    p.fop(2, 2, "*", 3)
    sv(p, D_G, 2)
    # the hit starts: no burst yet, the tail shut; the shared DC out cleared; the declick from the last sample
    def start():
        C.knob(p, 0, CNT)
        p.iconst(1, R.CLAP_N)
        p.mul_ssi(0, 0, 1)
        p.lsh(0, 0, -7)
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
        sv(p, T_N, 0)
        KI._u(p, 2, SPRD)
        KI._expo(p, 3, 2, R.CLAP_SPRD[0] * FS, R.CLAP_SPRD[1] * FS)
        sv(p, S_EB, 3)                               # (the spacing)
        KI._q(p, L, 2, HUMN)
        sv(p, S_ET, 2)                               # (HUMN)
        KI._q(p, L, 2, RAMP)
        addk(p, 2, 2, -0.5)
        mulk(p, 2, 2, 1.2)
        sv(p, S_EG, 2)                               # (RAMP)
        _start_train(p, TA, S_RNG, 1.0, None, lambda: p.fconst(7, 0.0))

        def g_t0():
            ld(p, 0, P_RNG2)
            _lcg(p, 7)
            sv(p, P_RNG2, 0)
            mulk(p, 7, 7, 0.2)
            addk(p, 7, 7, 0.5)
            ld(p, 13, S_EB)
            p.fop(7, 7, "*", 13)
        _start_train(p, TG, P_RNG2, R.CLAP_GRP_SP, 0.5, g_t0)
        for s_t, base, s_p in ((S_TNA, TA, S_PA), (S_TNG, TG, S_PG)):
            SN._ptr(p, base)
            p.geti(0, 1)
            sv(p, s_p, 0)
            ld(p, 0, base)
            sv(p, s_t, 0)
        p.fconst(0, 0.0)
        for k in (S_EB, S_EG, S_ET, S_EF, S_DC2):
            sv(p, k, 0)
        p.iconst(0, 0)
        sv(p, S_RISE, 0)
        sv(p, S_N, 0)
        M.declick_on(p)
    M.on_hit(p, start)


def _fire(p: Prog, s_t: int, s_p: int, s_e: int, tail: bool) -> None:
    """a burst at this sample: its level into S_E, the next time into S_T (the pointer on); the main train's last
    burst opens the tail. Clobbers R2-R5, R12, I1."""
    ld(p, 2, s_p)
    p.seti(1, 2)
    p.ldi(3, LA - TA, 1)
    sv(p, s_e, 3)
    p.ldi(3, 1, 1)
    sv(p, s_t, 3)
    p.iconst(12, 4)
    p.iop(2, 12, "+", 2)
    sv(p, s_p, 2)
    if tail:
        def opens():
            p.iconst(5, 1)
            sv(p, S_RISE, 5)
            p.fconst(5, R.CLAP_FLOOR)
            sv(p, S_EF, 5)
        p.iconst(4, END)
        p.if_(3, "EQ", 4, opens, kind="i")


def _band(p: Prog, k: int) -> None:
    """F13 = band k's (lp, bp, hp) in F11, F10, F9 by its weights. Clobbers R12-R14."""
    ld(p, 12, D_MIX + 3 * k)
    p.fop(13, 12, "*", 11)
    ld(p, 12, D_MIX + 3 * k + 1)
    p.fop(14, 12, "*", 10)
    p.fop(13, 13, "+", 14)
    ld(p, 12, D_MIX + 3 * k + 2)
    p.fop(14, 12, "*", 9)
    p.fop(13, 13, "+", 14)


def sample(p: Prog, L) -> None:
    """One sample at I4 (ref.Clap.sample). Clobbers R0-R15, I1, I12."""
    # the bursts: each train's next time against this sample
    ld(p, 0, S_N)
    ld(p, 1, S_TNA)
    p.if_(0, "EQ", 1, lambda: _fire(p, S_TNA, S_PA, S_EB, True), kind="i")
    ld(p, 1, S_TNG)
    p.if_(0, "EQ", 1, lambda: _fire(p, S_TNG, S_PG, S_EG, False), kind="i")
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    sv(p, S_N, 0)
    # the bursts' band (the VCA before the filter: the 808's order); the burst falls
    M.noise(p, 6, S_RNG)                         # F6 x
    ld(p, 9, S_EB)
    p.fop(8, 6, "*", 9)
    SN._ptr(p, A_SVF)
    PD.svf(p)
    _band(p, 0)
    p.fpass(7, 13)                               # y
    ld(p, 9, S_EB)
    ld(p, 10, D_BD)
    p.fop(9, 9, "*", 10)
    sv(p, S_EB, 9)
    # the tail: rising to 0.98 from the last burst, then falling by DCAY; the floor under it
    ld(p, 0, S_RISE)
    ld(p, 1, S_ET)

    def rise():
        p.fconst(12, 1.0)
        p.fop(2, 12, "-", 1)
        ld(p, 3, D_TR)
        p.fop(2, 2, "*", 3)
        p.fop(1, 1, "+", 2)
        p.fconst(12, 0.98)
        p.if_(1, "GT", 12, lambda: (p.iconst(0, 0), sv(p, S_RISE, 0)))

    def fall():
        ld(p, 2, D_TD)
        p.fop(1, 1, "*", 2)
    p.ifz(0, "NE", rise, fall)
    sv(p, S_ET, 1)
    ld(p, 2, S_EF)
    p.fop(1, 1, "+", 2)
    p.fop(8, 6, "*", 1)
    ld(p, 3, D_TL)
    p.fop(8, 8, "*", 3)
    ld(p, 3, D_FD)
    p.fop(2, 2, "*", 3)
    sv(p, S_EF, 2)
    SN._ptr(p, T_SVF)
    PD.svf(p)
    _band(p, 1)
    p.fop(7, 7, "+", 13)
    # GRP's clapper (its own generator, its bursts; its weights 0 when GRP is 0)
    M.noise(p, 8, P_RNG2)
    ld(p, 9, S_EG)
    p.fop(8, 8, "*", 9)
    SN._ptr(p, G_SVF)
    PD.svf(p)
    _band(p, 2)
    p.fop(7, 7, "+", 13)
    ld(p, 9, S_EG)
    ld(p, 10, D_BD)
    p.fop(9, 9, "*", 10)
    sv(p, S_EG, 9)
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
    K.clamp(p, 4, -R.CLAP_TOP, R.CLAP_TOP)
    sv(p, S_LAST, 4)
    p.stpost(4, 4)
