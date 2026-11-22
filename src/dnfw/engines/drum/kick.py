"""DRUM's KICK in the DSL: dnfw.engines.drum.ref.Kick, operation for operation (its sines PERC's table, its e^x and
log2 dmath's; test/test_drum.py holds the two within DSL_TOL_DB).

A hit's values are set in the first half after the trig (the note is the render's: `pitch` runs before the halves),
then 16 samples a half: the sine body (its sweep, sigh, self phase modulation), the hold and the decay, the click
(the pulse-and-noise through a one-pole, the chirp, or between), the air, the DC out before the drive, the drive's soft
clip with ADAA, its level held, the DC out after it, the retrig's declick.
"""

from __future__ import annotations

import math

from ...mnm import core as C
from ...perc import machines as PM
from ...perc.dsl import Prog
from . import dmath as M
from . import ref as R
from .dmath import addk, clamp, ld, mulk, sv

FS = R.FS
# state words (dnfw.drum.drum owns 0..4: S_TRIG S_ON S_TYPE S_NOTE S_RNG)
S_TRIG, S_ON, S_TYPE, S_NOTE, S_RNG = range(5)
(S_PH, S_SW, S_AMP, S_N, S_CLKLP, S_CLK, S_CHE, S_CHPH, S_NZLP, S_NZ, S_DC, S_UP, S_FUP, S_DC2, S_LAST,
 S_DK) = range(5, 21)
(D_F0, D_SWAMT, D_SWD, D_SIGH, D_HOLD, D_AMPD, D_PM, D_CLKD, D_CHIRP, D_CLKA, D_CHF0, D_CHD, D_NZD, D_NZA, D_G,
 D_COMP) = range(21, 37)
T_U, T_V, T_X, T_Y = range(37, 41)
D_ADAA = 41                                    # 1: the drive's gain is over ADAA_G (ADAA), 0: the plain soft clip
S_SHN, D_SWHD, D_HL = 42, 43, 44               # stage 3: the sweep hold's count and length (int), the hit's level
# stage 5: the click's high-pass, the balance's body gain, CURV's blend, kind, ramp and step, the click kept past the drive
S_CHP, D_G1, D_CVA, D_CVK, S_CVR, D_CVDR, T_CK = range(45, 52)
WORDS = 52

TUNE, DCAY, SWEP, SWTM, CLIK, CLKT, DRIV = range(7)            # page 1 A..G
SHAP, HOLD, SIGH, CLKL, NOIS, VEL, SWHD, CURV = range(8)             # page 2 A..G (q0..q6)

CH_END = R.CHIRP_END_HZ / FS
DK_D = float(R.tau_coef(R.DECLICK_S))
DC_A = float(R.onepole_a(R.DC_PRE_HZ))
CHP_A = float(R.onepole_a(R.CLICK_HP_HZ))
DC2_A = float(R.onepole_a(R.DC_POST_HZ))


def _u(p: Prog, d: int, k: int) -> None:
    """Fd = page-1 knob k as 0..1 (knob / 128 x 128 / 127). Clobbers R12."""
    C.par(p, d, k)
    mulk(p, d, d, 128.0 / 127.0)


def _q(p: Prog, L, d: int, k: int) -> None:
    """Fd = page-2 control k, 0..1"""
    C.page2(p, L, d, k)


def _expo(p: Prog, d: int, x: int, lo: float, hi: float) -> None:
    """Fd = lo (hi / lo)^Fx. d is not x. Clobbers R0, R1, R12-R14, I12."""
    mulk(p, 13, x, math.log2(hi / lo))
    M.exp2(p, d, 13)
    mulk(p, d, d, lo)


COEF_K = {-1.0: "dr_coef1", -R.LN_THOUSAND: "dr_coef60"}


def _coef(p: Prog, s: int, x: int, k: float) -> None:
    """state word S = e^(k / Fx) (Fx > 0, k < 0: a decay's coefficient a sample). One subroutine for each K of COEF_K
    (2026-11-20, CLAP and the cymbals' room: PERC's reciprocal inline, x k, then exp_neg's copy as its tail), the
    same arithmetic. Clobbers R0, R1, R12-R15, I12."""
    if k not in COEF_K:
        PM.recip(p, 14, x)
        mulk(p, 15, 14, k)
        M.exp_neg(p)
        sv(p, s, 14)
        return
    if x != 15:
        p.fpass(15, x)

    def body():
        PM._recip_inline(p, 14, 15, 13)
        mulk(p, 15, 14, k)
        p.tail("dr_exp", lambda: M.exp_neg_body(p))
    p.call(COEF_K[k], body)
    sv(p, s, 14)


def _onepole(p: Prog, s: int, x: int) -> None:
    """state word S = 1 - e^(-2 pi Fx / FS) (Fx a frequency, Hz). Clobbers R0, R1, R12-R15, I12."""
    mulk(p, 15, x, -2.0 * math.pi / FS)
    M.exp_neg(p)
    p.fconst(12, 1.0)
    p.fop(14, 12, "-", 14)
    sv(p, s, 14)


def _vel(p: Prog, L, d: int) -> None:
    """Fd = this slot's note velocity, 0..1 (dnfw.perc.program.vel_latch's word: 127 - vel, latched at the trig).
    Clobbers R9, R11, R12, I1."""
    p.ld(9, L.perc.C["t"])
    p.lsh(12, 9, 2)
    from ...perc import program as PP          # (lazy: program imports the machines)
    p.iconst(11, L.scratch + PP.VEL_OFF)
    p.iop(12, 11, "+", 12)
    p.seti(1, 12)
    p.ldi(9, 0, 1)
    p.iconst(12, 0)
    p.iop(9, 9, "MAX", 12)
    p.iconst(12, 127)
    p.iop(9, 9, "MIN", 12)
    p.iop(9, 12, "-", 9)                         # vel 0..127
    p.iconst(12, 0)
    p.float_(d, 9, 12)
    mulk(p, d, d, 1.0 / 127.0)


def vm(p: Prog, L, k: int) -> None:
    """F2 = vm = 1 + VEL (vel - 1), VEL the page-2 control k: one copy for every type (a leaf; 2026-11-20, the DSP
    upload's room). Clobbers R2, R3, R9, R11, R12, I1, I12."""
    _q(p, L, 3, k)
    vm_f3(p, L)


def vm_f3(p: Prog, L) -> None:
    """F2 = vm = 1 + F3 (vel - 1) (vm's subroutine: F3 the VEL control's value)"""
    def body():
        _vel(p, L, 2)
        addk(p, 2, 2, -1.0)
        p.fop(2, 3, "*", 2)
        addk(p, 2, 2, 1.0)
    p.call("dr_vm", body)


def tune_oct(p: Prog, per: float) -> None:
    """F3 = (st + note - 60) / 12, st = trunc(TUNE's knob x PER + 0.5) - 24 whole semitones (TUNE is page 1 A on every
    type): one copy (a leaf). Clobbers R0-R3, R5, R12, I12."""
    p.fconst(5, per)

    def body():
        C.knob(p, 0, TUNE)
        p.iconst(12, 0)
        p.float_(1, 0, 12)
        p.fop(1, 1, "*", 5)
        addk(p, 1, 1, 0.5)
        p.trunc(1, 1)
        p.iconst(12, 0)
        p.float_(1, 1, 12)
        addk(p, 1, 1, -24.0)
        ld(p, 2, S_NOTE)
        p.fop(1, 1, "+", 2)
        addk(p, 1, 1, -60.0)
        mulk(p, 3, 1, 1.0 / 12.0)
    p.call("dr_tune", body)


def hit(p: Prog, L) -> None:
    """The hit's values (ref.Kick.trig), in the first half after the trig. 2026-11-21 (live knobs): also run with
    S_TRIG 0 on the voice's turn (drum.half), the hit's state kept (dmath.on_hit): every knob but CLIK's click level
    and NOIS (decaying levels) follows modulation and p-locks while the hit rings. Clobbers R0-R15, I1, I12."""
    # vm = 1 + VEL (vel - 1) -> T_X
    vm(p, L, VEL)
    sv(p, T_X, 2)
    # TUNE: whole semitones, trunc(knob x 60 / 127 + 0.5) - 24; f0 = 50 x 2^((st + note - 60) / 12) Hz
    tune_oct(p, 60.0 / 127.0)
    from ..plaits import plk as K
    M.exp2(p, 4, 3)
    mulk(p, 4, 4, R.BASE_HZ)                     # F4 f0 (Hz)
    sv(p, T_Y, 4)
    mulk(p, 5, 4, 1.0 / FS)
    sv(p, D_F0, 5)
    # the sweep: min(f0 (2^(7 SWEP (0.5 + 0.5 vm)) - 1), 12000 - f0) / FS
    _u(p, 5, SWEP)
    mulk(p, 5, 5, 7.0)
    ld(p, 6, T_X)
    mulk(p, 6, 6, 0.5)
    addk(p, 6, 6, 0.5)
    p.fop(5, 5, "*", 6)
    M.exp2(p, 6, 5)
    addk(p, 6, 6, -1.0)
    ld(p, 4, T_Y)
    p.fop(6, 4, "*", 6)
    p.fconst(12, R.SWEEP_TOP_HZ)
    p.fop(7, 12, "-", 4)
    p.fop(6, 6, "MIN", 7)
    mulk(p, 6, 6, 1.0 / FS)
    sv(p, D_SWAMT, 6)
    # its time: e^(-1 / (0.001 x 150^SWTM x FS))
    _u(p, 2, SWTM)
    _expo(p, 3, 2, 0.001 * FS, 0.15 * FS)
    _coef(p, D_SWD, 3, -1.0)
    mulk(p, 3, 3, R.CURV_T)                      # stage 5: CURV's ramp step, 1 / (5 tau FS)
    PM.recip(p, 4, 3)
    sv(p, D_CVDR, 4)
    # SIGH, HOLD (samples), SHAP
    _q(p, L, 2, SIGH)
    mulk(p, 2, 2, 0.25)
    sv(p, D_SIGH, 2)
    _q(p, L, 2, HOLD)
    p.fop(2, 2, "*", 2)
    mulk(p, 2, 2, 0.25 * FS)
    p.trunc(2, 2)
    sv(p, D_HOLD, 2)
    _q(p, L, 2, SHAP)
    mulk(p, 2, 2, 0.45)
    sv(p, D_PM, 2)
    # the decay: e^(-ln 1000 / (t60 FS)), t60 = 0.005 x 1600^DCAY; the air's at 0.3 t60
    _u(p, 2, DCAY)
    _expo(p, 3, 2, 0.005 * FS, 8.0 * FS)
    sv(p, T_Y, 3)
    _coef(p, D_AMPD, 3, -R.LN_THOUSAND)
    ld(p, 3, T_Y)
    mulk(p, 3, 3, 0.3)
    _coef(p, D_NZD, 3, -R.LN_THOUSAND)
    # stage 5: CLIK, the balance: body+noise x ref.balance, the click x its second gain x 1.5 vm
    _u(p, 4, CLIK)
    M.balance(p, 3, 2, 4)
    sv(p, D_G1, 3)
    sv(p, T_CK, 2)                               # (the click's level: the hit's state, _start; T_CK free till then)
    # CURV (page 2 H, q7): its knob trunc(q 127 + 0.5); c = knob - 64: 0 the exponential, < 0 a line, > 0 the concave
    _q(p, L, 2, CURV)
    mulk(p, 2, 2, 127.0)
    addk(p, 2, 2, 0.5)
    p.trunc(0, 2)
    p.iconst(12, -R.CURV_MID)
    p.iop(0, 12, "+", 0)
    p.iconst(1, 0)
    p.iconst(12, 0)
    p.if_(0, "LT", 12, lambda: p.iconst(1, 1), kind="i")
    p.if_(0, "GT", 12, lambda: p.iconst(1, 2), kind="i")
    sv(p, D_CVK, 1)
    p.iconst(12, 0)
    p.float_(2, 0, 12)
    K_fabs(p, 2, 2)
    mulk(p, 2, 2, 1.0 / R.CURV_SPAN)
    sv(p, D_CVA, 2)
    _q(p, L, 2, CLKL)
    _expo(p, 3, 2, 0.0002 * FS, 0.02 * FS)
    sv(p, T_Y, 3)
    _coef(p, D_CLKD, 3, -1.0)
    ld(p, 3, T_Y)
    mulk(p, 3, 3, 0.6)
    p.fconst(12, 0.0004 * FS)
    p.fop(3, 3, "MAX", 12)
    _coef(p, D_CHD, 3, -1.0)
    # CLKT: 0 .. 0.75 the pulse's low-pass 400 Hz .. 16 kHz (held there to CHIRP_AT), from CHIRP_AT the chirp,
    # starting at 1.5 .. 9 kHz
    _u(p, 2, CLKT)
    sv(p, T_Y, 2)
    p.fconst(3, 0.0)
    p.fconst(12, R.CHIRP_AT)
    p.if_(2, "GE", 12, lambda: p.fconst(3, 1.0))
    sv(p, D_CHIRP, 3)
    p.fconst(12, 0.75)
    p.fop(3, 2, "MIN", 12)
    mulk(p, 3, 3, 1.0 / 0.75)
    _expo(p, 4, 3, 400.0, 16000.0)
    _onepole(p, D_CLKA, 4)
    ld(p, 2, T_Y)
    addk(p, 3, 2, -R.CHIRP_AT)
    p.fconst(12, 0.0)
    p.fop(3, 3, "MAX", 12)
    mulk(p, 3, 3, 1.0 / (1.0 - R.CHIRP_AT))
    _expo(p, 4, 3, 1500.0 / FS, 9000.0 / FS)
    sv(p, D_CHF0, 4)
    # the air: NOIS / 2, its low-pass 1500 + 6000 pm / 0.3 Hz
    # (the air's level NOIS / 2: the hit's state, _start)
    ld(p, 2, D_PM)
    mulk(p, 2, 2, 6000.0 / 0.3)
    addk(p, 2, 2, 1500.0)
    _onepole(p, D_NZA, 2)
    # DRIV: g = 1 + 30 DRIV^2; its level g^-0.45 (g <= 10), 10^-0.45 (10 / g)^0.08 above
    drive_level(p, DRIV, 30.0, D_G, D_COMP, R.KICK_GAIN)
    # stage 3: the sigh follows the hit's level, hl = vm g^0.25; the clip sees g x vm (its level held at g's)
    ld(p, 8, D_G)
    M.log2(p)                                    # F9 log2 g
    mulk(p, 13, 9, 0.25)
    M.exp2(p, 4, 13)
    ld(p, 3, T_X)
    p.fop(4, 3, "*", 4)
    sv(p, D_HL, 4)
    ld(p, 2, D_G)
    p.fop(2, 2, "*", 3)
    sv(p, D_G, 2)
    # SWHD: the sweep held trunc(SWHD x 30 ms x FS) samples at its top
    _q(p, L, 2, SWHD)
    mulk(p, 2, 2, R.SWHD_MAX * FS)
    p.trunc(2, 2)
    sv(p, D_SWHD, 2)
    # ADAA above ADAA_G (below it the clip's aliasing is under the 50 Hz body's own: measured -57 dB): its last
    # antiderivative from the last input, which the plain clip keeps too
    p.iconst(0, 0)
    sv(p, D_ADAA, 0)
    ld(p, 2, D_G)
    p.fconst(12, R.ADAA_G)

    def adaa_on():
        p.iconst(0, 1)
        sv(p, D_ADAA, 0)
        ld(p, 15, S_UP)
        M.soft_antider(p, T_U, T_V)
        sv(p, S_FUP, 9)
    p.if_(2, "GT", 12, adaa_on)
    # the hit starts: phase 0, the envelopes full, the declick from the last sample if a sound was on
    M.on_hit(p, lambda: _start(p, L))


def _start(p: Prog, L) -> None:
    """the hit's state (not on a live re-read: dmath.on_hit): the click's level (CLIK's second gain in T_CK) x 1.5
    vm, the air's NOIS / 2, the sweep hold's count, phase 0, the envelopes full, the declick. Clobbers R0-R3, R12."""
    ld(p, 2, T_CK)
    mulk(p, 2, 2, 1.5)
    ld(p, 3, T_X)
    p.fop(2, 2, "*", 3)
    sv(p, S_CLK, 2)
    _q(p, L, 2, NOIS)
    mulk(p, 2, 2, 0.5)
    sv(p, S_NZ, 2)
    p.iconst(0, 0)
    sv(p, S_SHN, 0)
    p.fconst(0, 0.0)
    for k in (S_PH, S_CLKLP, S_CHPH, S_NZLP, S_DC, S_CHP):
        sv(p, k, 0)
    p.fconst(0, 1.0)
    for k in (S_SW, S_AMP, S_CHE, S_CVR):
        sv(p, k, 0)
    p.iconst(0, 0)
    sv(p, S_N, 0)
    M.declick_on(p)


def drive_level(p: Prog, k: int, top: float, s_g: int, s_comp: int, gain: float = 1.0, scale=None) -> None:
    """the drive at page-1 knob K: word S_G = g = 1 + TOP K^2, word S_COMP = its level held (ref.comp) x GAIN.
    SCALE (the hats): SCALE() puts in F2 the gain the level is held at (F2 = g on entry; it may clobber R3, R4, R12).
    Clobbers R0-R4, R8-R14, I12."""
    from ..plaits import plk as K
    _u(p, 2, k)
    p.fop(2, 2, "*", 2)
    mulk(p, 2, 2, top)
    addk(p, 2, 2, 1.0)
    sv(p, s_g, 2)
    if scale is not None:
        scale()
    p.fpass(8, 2)
    M.log2(p)                                    # F9 log2 g
    # the larger of the two laws is the one in force (they meet at g = 10: -0.45 l above -0.45 L10 - 0.08 (l - L10)
    # below it, and under it above): no branch (2026-11-20, the DSP upload's room), each value as before; one copy
    # with exp2's as its tail (2026-11-20, CLAP and the cymbals' room)
    def law():
        mulk(p, 3, 9, -0.45)
        addk(p, 4, 9, -math.log2(10.0))
        mulk(p, 4, 4, -0.08)
        addk(p, 4, 4, -0.45 * math.log2(10.0))
        p.fop(3, 3, "MAX", 4)
        p.fpass(13, 3)
        p.tail("dr_exp2", lambda: K.exp2p(p, 14, 13))
    p.call("dr_law", law)
    p.fpass(4, 14)
    if gain != 1.0:
        mulk(p, 4, 4, gain)
    sv(p, s_comp, 4)


def _sine(p: Prog, L, d: int, x: int) -> None:
    """Fd = sin(2 pi Fx), any Fx: plk.sinp (PLAITS' copy, 1.9e-7 off sin). Clobbers R0, R1, R12-R15, I12."""
    from ..plaits import plk as K
    K.sinp(p, d, x)


def sample(p: Prog, L) -> None:
    """One sample at I4 (ref.Kick.sample). Clobbers R0-R15, I1, I12."""
    # the pitch: f0 (1 - sigh (1 - min(hl amp, 1))) + sweep amt x sw; sw held SWHD samples, then it decays; the
    # phase in 0..1
    ld(p, 3, S_AMP)
    ld(p, 2, D_HL)
    p.fop(3, 2, "*", 3)
    p.fconst(12, 1.0)
    p.fop(3, 3, "MIN", 12)
    p.fop(4, 12, "-", 3)
    ld(p, 2, D_SIGH)
    p.fop(4, 2, "*", 4)
    p.fop(4, 12, "-", 4)
    ld(p, 1, D_F0)
    p.fop(4, 1, "*", 4)
    ld(p, 5, D_SWAMT)
    ld(p, 6, S_SW)
    p.fop(5, 5, "*", 6)
    p.fop(4, 4, "+", 5)
    ld(p, 0, D_CVK)

    def curv():                                  # stage 5: f += amt (a (shape(r) - sw)), shape r or r (2 - r)
        ld(p, 7, S_CVR)
        p.fpass(8, 7)
        p.iconst(12, 2)

        def concave():
            p.fconst(12, 2.0)
            p.fop(8, 12, "-", 7)
            p.fop(8, 7, "*", 8)
        p.if_(0, "EQ", 12, concave, kind="i")
        p.fop(8, 8, "-", 6)
        ld(p, 9, D_CVA)
        p.fop(8, 9, "*", 8)
        ld(p, 5, D_SWAMT)
        p.fop(8, 5, "*", 8)
        p.fop(4, 4, "+", 8)
    p.ifz(0, "NE", curv)
    ld(p, 0, S_SHN)
    ld(p, 1, D_SWHD)

    def sw_held():
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
        sv(p, S_SHN, 0)

    def sw_fall():
        ld(p, 7, D_SWD)
        p.fop(6, 6, "*", 7)
        sv(p, S_SW, 6)
        ld(p, 7, S_CVR)                          # CURV's ramp, max(r - dr, 0)
        ld(p, 8, D_CVDR)
        p.fop(7, 7, "-", 8)
        p.fconst(12, 0.0)
        p.fop(7, 7, "MAX", 12)
        sv(p, S_CVR, 7)
    p.if_(0, "LT", 1, sw_held, sw_fall, kind="i")
    ld(p, 5, S_PH)
    p.fop(5, 5, "+", 4)
    PM.frac(p, 5)
    sv(p, S_PH, 5)
    # the body: sin(ph + pm sin(ph)) x amp
    _sine(p, L, 6, 5)
    ld(p, 7, D_PM)
    p.fop(6, 7, "*", 6)
    ld(p, 5, S_PH)
    p.fop(6, 5, "+", 6)
    _sine(p, L, 7, 6)
    sv(p, T_X, 7)
    ld(p, 3, S_AMP)
    # the hold, then the decay
    ld(p, 0, S_N)
    ld(p, 1, D_HOLD)

    def decay():
        ld(p, 2, D_AMPD)
        p.fop(3, 3, "*", 2)
        sv(p, S_AMP, 3)

    def hold():
        p.ipass(8, 0)
        p.iconst(12, 1)
        p.iop(8, 8, "+", 12)
        sv(p, S_N, 8)
    p.if_(0, "GE", 1, decay, hold, kind="i")
    ld(p, 7, T_X)
    ld(p, 3, S_AMP)
    p.fop(7, 7, "*", 3)                          # body x amp (the amp after this sample's decay, as ref)
    sv(p, T_X, 7)
    # the click: the pulse and noise through its low-pass, or the chirp (CLKT from CHIRP_AT)
    def pulse():
        M.noise(p, 9, S_RNG)
        mulk(p, 9, 9, 0.7)
        addk(p, 9, 9, 1.0)
        ld(p, 10, S_CLKLP)
        p.fop(9, 9, "-", 10)
        ld(p, 11, D_CLKA)
        p.fop(9, 11, "*", 9)
        p.fop(10, 10, "+", 9)
        sv(p, S_CLKLP, 10)
        ld(p, 11, S_CHP)                         # stage 5: high-passed (300 Hz) x 2
        p.fop(9, 10, "-", 11)
        p.fconst(12, CHP_A)
        p.fop(9, 12, "*", 9)
        p.fop(11, 11, "+", 9)
        sv(p, S_CHP, 11)
        p.fop(10, 10, "-", 11)
        mulk(p, 10, 10, R.CLICK_HP_G)
        sv(p, T_Y, 10)

    def chirp():
        ld(p, 4, D_CHF0)
        p.fconst(12, CH_END)
        p.fop(4, 4, "-", 12)
        ld(p, 5, S_CHE)
        p.fop(4, 4, "*", 5)
        p.fop(4, 12, "+", 4)                     # cf
        ld(p, 6, D_CHD)
        p.fop(5, 5, "*", 6)
        sv(p, S_CHE, 5)
        ld(p, 5, S_CHPH)
        p.fop(5, 5, "+", 4)
        PM.frac(p, 5)
        sv(p, S_CHPH, 5)
        _sine(p, L, 6, 5)
        mulk(p, 6, 6, 1.2)
        sv(p, T_Y, 6)
    ld(p, 2, D_CHIRP)
    p.fconst(12, 0.0)
    p.if_(2, "GT", 12, chirp, pulse)
    ld(p, 7, T_Y)
    ld(p, 8, S_CLK)
    p.fop(7, 7, "*", 8)                          # click
    sv(p, T_CK, 7)                               # (added after the drive)
    ld(p, 9, D_CLKD)
    p.fop(8, 8, "*", 9)
    sv(p, S_CLK, 8)
    # the air
    M.noise(p, 9, S_RNG)
    ld(p, 10, S_NZLP)
    p.fop(9, 9, "-", 10)
    ld(p, 11, D_NZA)
    p.fop(9, 11, "*", 9)
    p.fop(10, 10, "+", 9)
    sv(p, S_NZLP, 10)
    ld(p, 11, S_NZ)
    p.fop(10, 10, "*", 11)                       # noise
    ld(p, 9, D_NZD)
    p.fop(11, 11, "*", 9)
    sv(p, S_NZ, 11)
    # x = (body + air) x the balance's g1; the DC out (12 Hz)
    ld(p, 6, T_X)
    p.fop(6, 6, "+", 10)
    ld(p, 7, D_G1)
    p.fop(6, 6, "*", 7)
    ld(p, 5, S_DC)
    p.fop(4, 6, "-", 5)
    p.fconst(12, DC_A)
    p.fop(4, 12, "*", 4)
    p.fop(5, 5, "+", 4)
    sv(p, S_DC, 5)
    p.fop(15, 6, "-", 5)
    # the drive: u = x g; ADAA ((F(u) - F(up)) / (u - up); the midpoint's clip when they meet) or the plain clip
    ld(p, 14, D_G)
    p.fop(15, 15, "*", 14)
    ld(p, 0, D_ADAA)

    def plain():
        sv(p, T_U, 15)
        from ..plaits import plaits_drumkit as PD
        PD.soft(p)                               # F15
        sv(p, T_X, 15)

    def adaa():
        M.soft_antider(p, T_U, T_V)              # F9 F(u), F15 u
        sv(p, T_Y, 9)
        ld(p, 8, S_UP)
        p.fop(10, 15, "-", 8)                    # d
        K_fabs(p, 11, 10)
        p.fconst(12, R.ADAA_EPS)

        def near():
            p.fop(15, 15, "+", 8)
            mulk(p, 15, 15, 0.5)
            from ..plaits import plaits_drumkit as PD
            PD.soft(p)                           # F15
            sv(p, T_X, 15)
        p.if_(11, "LT", 12, near, lambda: _far(p))
        ld(p, 9, T_Y)
        sv(p, S_FUP, 9)
    p.ifz(0, "NE", adaa, plain)
    ld(p, 15, T_U)
    sv(p, S_UP, 15)
    # the level held, the DC out after the drive (5 Hz), the declick
    ld(p, 4, T_X)
    ld(p, 5, D_COMP)
    p.fop(4, 4, "*", 5)
    ld(p, 5, S_DC2)
    p.fop(6, 4, "-", 5)
    p.fconst(12, DC2_A)
    p.fop(6, 12, "*", 6)
    p.fop(5, 5, "+", 6)
    sv(p, S_DC2, 5)
    p.fop(4, 4, "-", 5)
    ld(p, 6, T_CK)                               # stage 5: the click, after the drive
    mulk(p, 6, 6, R.CLICK_POST)
    p.fop(4, 4, "+", 6)
    ld(p, 6, S_DK)
    p.fop(4, 4, "+", 6)
    p.fconst(12, DK_D)
    p.fop(6, 6, "*", 12)
    sv(p, S_DK, 6)
    sv(p, S_LAST, 4)
    p.stpost(4, 4)


def K_fabs(p: Prog, d: int, x: int) -> None:
    from ..plaits import plk as K
    K.fabs(p, d, x)


def _far(p: Prog) -> None:
    """T_X = (F(u) - F(up)) / (u - up): F(u) in T_Y, u in T_U, up in S_UP. Clobbers R8-R15, I12."""
    ld(p, 9, T_Y)
    ld(p, 8, S_FUP)
    p.fop(9, 9, "-", 8)                          # F(u) - F(up)
    ld(p, 15, T_U)
    ld(p, 8, S_UP)
    p.fop(10, 15, "-", 8)                        # d
    p.fconst(12, 0.0)

    def neg():                                   # d < 0: (F(up) - F(u)) / (up - u)
        p.fop(9, 12, "-", 9)
        p.fop(10, 12, "-", 10)
    p.if_(10, "LT", 12, neg)
    PM._recip_inline(p, 14, 10, 13)
    p.fop(9, 9, "*", 14)
    sv(p, T_X, 9)
