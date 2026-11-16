"""PLAITS' STRG: Mutable Instruments Plaits' STRING engine (MIT, Emilie Gillet:
plaits/dsp/engine/string_engine.cc, physical_modelling/string_voice.cc, string.cc, delay_line.h;
stmlib filter.h, dsp.h, parameter_interpolator.h, random.h). OUT only.

Three strings (kNumStrings), the trigger moving to the next one (the one left keeps ringing at the
f0 Plaits' f0 delay line held 14 blocks earlier). Each string: on its trigger a burst of 1 / f0
samples of white noise (the voice's stmlib::Random) through an SVF low-pass (FREQUENCY_DIRTY,
Q 0.5), into a Karplus-Strong loop: the 1024-word delay line read by Hermite interpolation (the
curved bridge, HARM below 0.24), or linearly and through a 256-word allpass (the dispersion, HARM
above 0.26, with the delay jittered by filtered noise), clamped to +-20, a DC blocker (20 Hz) and
the damping SVF (FREQUENCY_FAST, its delay compensated by 1 - atan(2^(-cutoff/12)) / pi:
Plaits' lut_svf_shift, here computed), and the linear upsampler under 43 Hz.

Memory: the voice's DDR area (plk.big_at), per string REC words: the delay line (1024 words + 3
mirrored, so a Hermite read never wraps), the stretch line (256), the string's state (STW words);
then the excitation of the string being rendered (16), the output accumulator (16), the f0 delay
line (16). Parameters: HARM structure, TIMB brightness (squared), MORP damping.
"""

from __future__ import annotations

import math

from . import plk as K
from ..perc.dsl import Prog, f32
from ..perc import machines as PM

MODEL = "STRG"
N_STR = 3
LINE, STRETCH = 1024, 256
O_LINE, O_STR, O_ST = 0, 1028, 1284              # a string's record (words)
REC = 1312
O_TEMP, O_ACC, O_F0L = N_STR * REC, N_STR * REC + 16, N_STR * REC + 32
BIG_USED = N_STR * REC + 48
# a string's state words (at its record + O_ST)
(EG, EH, ES1, ES2, REM, DG, DH, DS1, DS2, DCX, DCY, DLY, DISP, BRG, O0, O1, SRC, WP, WP2,
 F0) = range(20)
STW = 20
# the slot's union words
(U_BIG, U_ACT, U_FWP, U_BR, U_DA, U_NL, U_STR, U_K, U_SRCR, U_INC, U_NA, U_NF, U_BC, U_APG,
 U_SP, U_SPK, U_SC, U_DISP, U_LB, U_D, U_S, U_AP, U_MAIN, U_OK, U_STA) = (K.U0 + k for k in range(25))
NU_USED = 25

ACC_K = float(f32(f32(0.25) * f32(K.ACCENT)))   # 0.25f * accent
SR = K.SR
DC_POLE = f32(1.0 - f32(20.0 / SR))              # DCBlocker's pole: 1 - 20 / kSampleRate
K160 = f32(160.0 / SR)
PI = math.pi


def _kpi(c, n):
    v = float(f32(c))
    for _ in range(n):
        v *= PI
    return f32(v)


PI_F = f32(PI)
DIRTY_A = _kpi(3.736e-01, 3)
FAST_A, FAST_B = _kpi(3.260e-01, 3), _kpi(1.823e-01, 5)
# atan(y) on 0 <= y <= 0.5 as y (c1 + c3 y^2 + .. + c9 y^8): least squares, float32 (8.2e-8 off)
ATAN_POLY = (0.9999999403953552, -0.33331498503685, 0.19935134053230286, -0.13493411242961884,
             0.06989286839962006)


# -- helpers ---------------------------------------------------------------------------------
def exp2(p: Prog, d: int, x: int) -> None:
    """Fd = 2^Fx (plk.exp2p as a subroutine, shared by the physical models). Clobbers R0, R1,
    R12-R15, I12."""
    p.fpass(14, x)
    p.call("plphy_exp2", lambda: K.exp2p(p, 15, 14))
    if d != 15:
        p.fpass(d, 15)


def recip(p: Prog, d: int, x: int) -> None:
    """Fd = 1 / Fx. Clobbers R12-R15, I12."""
    PM.recip(p, d, x)


def svf_coefs(p: Prog, g: int, kg: int) -> None:
    """state[kg] = Fg, state[kg + 1] = 1 / (1 + 2 g + g g) (an Svf at Q 0.5: r = 2). Clobbers
    R12-R15, I12, R10, R11."""
    p.sti(kg, 1, g)
    p.fop(10, g, "+", g)
    K.addk(p, 10, 10, 1.0)
    p.fop(11, g, "*", g)
    p.fop(10, 10, "+", 11)
    recip(p, 10, 10)
    p.sti(kg + 1, 1, 10)


def svf_lp(p: Prog, d: int, x: int, kg: int) -> None:
    """Fd = Svf::Process<LOW_PASS>(Fx), its g, h, s1, s2 at state[kg..]: R2, R3, R5-R7, R10, R11
    clobbered (d may be x; x not in those)."""
    p.ldi(10, kg, 1)                             # g
    p.ldi(2, kg + 2, 1)                          # s1
    p.ldi(3, kg + 3, 1)                          # s2
    p.fop(5, 2, "+", 2)                          # r s1
    p.fop(5, x, "-", 5)
    p.fop(6, 10, "*", 2)
    p.fop(5, 5, "-", 6)
    p.fop(5, 5, "-", 3)
    p.ldi(11, kg + 1, 1)                         # h
    p.fop(5, 5, "*", 11)                         # hp
    p.fop(5, 10, "*", 5)                         # g hp
    p.fop(6, 5, "+", 2)                          # bp
    p.fop(5, 5, "+", 6)
    p.sti(kg + 2, 1, 5)                          # s1
    p.fop(7, 10, "*", 6)                         # g bp
    p.fop(d, 7, "+", 3)                          # lp
    p.fop(5, 7, "+", d)
    p.sti(kg + 3, 1, 5)                          # s2


def shared_at(p: Prog, d: int, off: int) -> None:
    """Rd = the address of the shared word OFF. Clobbers R8, R12."""
    K.ld(p, 8, U_BIG)
    p.iconst(12, 4 * off)
    p.iop(d, 12, "+", 8)


def _temp_start(p: Prog) -> None:
    """U_K = the address of the excitation's first word (the accumulator's is 16 on)."""
    shared_at(p, 0, O_TEMP)
    K.sv(p, U_K, 0)


def _temp(p: Prog) -> None:
    """I1 = U_K: this sample's excitation word (+ 16: its accumulator word)."""
    K.ld(p, 8, U_K)
    p.seti(1, 8)


def rec_at(p: Prog, d: int, i: int) -> None:
    """Rd = string Ri's state words' address (Ri 0..2). Clobbers R8, R12, Ri."""
    p.iconst(12, 4 * REC)
    p.mul_ssi(i, i, 12)
    K.ld(p, 8, U_BIG)
    p.iop(i, 8, "+", i)
    p.iconst(12, 4 * O_ST)
    p.iop(d, 12, "+", i)


def _home(p: Prog) -> None:
    """I1 = the string's state words again (after a delay line's or a shared word's access).
    Clobbers R8."""
    K.ld(p, 8, U_STA)
    p.seti(1, 8)


def inc_word(p: Prog, k: int, mask: int | None = None, by: int = 1) -> None:
    """slot word k += by (& mask). Clobbers R0, R12."""
    K.ld(p, 0, k)
    p.iconst(12, by)
    p.iop(0, 12, "+", 0)
    if mask is not None:
        p.iconst(12, mask)
        p.iop(0, 0, "AND", 12)
    K.sv(p, k, 0)


# -- init --------------------------------------------------------------------------------------
def init(p: Prog, L) -> None:
    """StringEngine::Init + Reset: the lines and states cleared, f0_ 0.01, delay_ 100, the active
    string the last, the f0 line empty."""
    K.big_at(p, L, 4)
    K.sv(p, U_BIG, 4)
    p.iconst(5, 0)

    def clear():
        p.seti(1, 4)
        p.sti(0, 1, 5)
        p.iconst(12, 4)
        p.iop(4, 12, "+", 4)
    p.loop_r(6, BIG_USED, clear)
    for i in range(N_STR):
        p.iconst(0, i)
        rec_at(p, 4, 0)
        p.seti(1, 4)
        p.fconst(0, 100.0)
        p.sti(DLY, 1, 0)
        p.fconst(0, 0.01)
        p.sti(F0, 1, 0)
    p.iconst(0, N_STR - 1)
    K.sv(p, U_ACT, 0)
    p.iconst(0, 0)
    K.sv(p, U_FWP, 0)


# -- the engine, a half --------------------------------------------------------------------------
def _globals(p: Prog) -> None:
    """brightness (timbre^2) and damping with the accent, the non-linearity."""
    K.par(p, 4, 1)
    p.fop(4, 4, "*", 4)
    K.par(p, 5, 2)
    for r, u in ((4, U_BR), (5, U_DA)):          # x += 0.25 accent (1 - x)
        p.fconst(12, 1.0)
        p.fop(6, 12, "-", r)
        K.mulk(p, 6, 6, ACC_K)
        p.fop(r, r, "+", 6)
        K.sv(p, u, r)
    K.par(p, 4, 0)                               # structure
    p.fconst(5, 0.0)
    p.fconst(6, 0.24)

    def lo():
        p.fop(5, 4, "-", 6)
        K.mulk(p, 5, 5, 4.166)
    p.if_(4, "LT", 6, lo)
    p.fconst(6, 0.26)

    def hi():
        p.fop(5, 4, "-", 6)
        K.mulk(p, 5, 5, 1.35135)
    p.if_(4, "GT", 6, hi)
    K.sv(p, U_NL, 5)


def _f0s(p: Prog) -> None:
    """f0 = NoteToFrequency(note); on the trigger the active string takes the f0 line's 14th and
    the next string is active; the active string's f0 = f0; the f0 line takes f0."""
    K.ld(p, 4, K.S_NOTE)
    K.addk(p, 4, 4, -69.0)
    K.mulk(p, 4, 4, 1.0 / 12.0)
    exp2(p, 5, 4)
    K.mulk(p, 5, 5, K.A0)
    K.sv(p, U_D, 5)
    K.ld(p, 0, K.S_TRIG)

    def trig():
        K.ld(p, 1, U_FWP)
        p.iconst(12, 14)
        p.iop(1, 12, "+", 1)
        p.iconst(12, 15)
        p.iop(1, 1, "AND", 12)
        p.lsh(1, 1, 2)
        shared_at(p, 2, O_F0L)
        p.ipass(8, 2)
        p.iop(1, 8, "+", 1)
        p.seti(1, 1)
        p.ldi(3, 0, 1)                           # f0_line.Read(14)
        K.ld(p, 0, U_ACT)
        rec_at(p, 4, 0)
        p.seti(1, 4)
        p.sti(F0, 1, 3)
        K.ld(p, 0, U_ACT)
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
        p.iconst(1, N_STR)
        p.if_(0, "EQ", 1, lambda: p.iconst(0, 0), kind="i")
        K.sv(p, U_ACT, 0)
    p.ifz(0, "NE", trig)
    K.ld(p, 0, U_ACT)
    rec_at(p, 4, 0)
    p.seti(1, 4)
    K.ld(p, 5, U_D)
    p.sti(F0, 1, 5)
    K.ld(p, 1, U_FWP)
    p.lsh(1, 1, 2)
    shared_at(p, 2, O_F0L)
    p.ipass(8, 2)
    p.iop(1, 8, "+", 1)
    p.seti(1, 1)
    p.sti(0, 1, 5)                               # f0_line.Write(f0)
    inc_word(p, U_FWP, 15, -1)


def _excite_trig(p: Prog) -> None:
    """StringVoice on its trigger: the filter at 4 f0 x 2^((b (2 - b) - 0.5) 72 / 12), the noise's
    length 1 / f0."""
    p.ldi(4, F0, 1)
    K.ld(p, 6, U_BR)
    p.fconst(12, 2.0)
    p.fop(7, 12, "-", 6)
    p.fop(7, 6, "*", 7)
    K.addk(p, 7, 7, -0.5)
    K.mulk(p, 7, 7, 72.0)
    K.mulk(p, 7, 7, 1.0 / 12.0)
    exp2(p, 7, 7)
    K.mulk(p, 5, 4, 4.0)
    p.fop(7, 5, "*", 7)
    p.fconst(12, 0.499)
    p.fop(7, 7, "MIN", 12)                       # cutoff
    K.mulk(p, 9, 7, DIRTY_A)                     # tan DIRTY: f (pi + a f f)
    p.fop(9, 9, "*", 7)
    K.addk(p, 9, 9, PI_F)
    p.fop(9, 7, "*", 9)
    svf_coefs(p, 9, EG)
    p.ldi(4, F0, 1)
    recip(p, 4, 4)
    p.trunc(4, 4)
    p.sti(REM, 1, 4)


def _excite(p: Prog, L) -> None:
    """16 samples of the excitation into the shared temp: noise while REM, through the SVF."""
    _temp_start(p)

    def one():
        p.fconst(9, 0.0)
        p.ldi(0, REM, 1)

        def noise():
            K.rnd01(p, 9)
            p.fop(9, 9, "+", 9)
            K.addk(p, 9, 9, -1.0)
            p.ldi(0, REM, 1)
            p.iconst(12, 1)
            p.iop(0, 0, "-", 12)
            p.sti(REM, 1, 0)
        p.ifz(0, "GT", noise)
        svf_lp(p, 9, 9, EG)
        _temp(p)
        p.sti(0, 1, 9)
        _home(p)
        inc_word(p, U_K, by=4)
    p.loop(L.W["inner"], K.HALF, one)


def _string_params(p: Prog) -> None:
    """String::ProcessInternal's block: the delay, the upsampler's ratio, the damping filter and
    its compensation, the non-linearities' amounts."""
    p.ldi(4, F0, 1)
    p.fconst(12, 1e-30)
    p.fop(5, 4, "MAX", 12)                       # f0 0 (a string never struck): delay 1020
    recip(p, 5, 5)
    K.clamp(p, 5, 4.0, LINE - 4.0)
    K.sv(p, U_D, 5)                              # delay
    p.fop(6, 5, "*", 4)                          # src_ratio
    p.fconst(12, 0.9999)

    def unity():
        p.fconst(6, 1.0)
        p.sti(SRC, 1, 6)
    p.if_(6, "GE", 12, unity)
    K.sv(p, U_SRCR, 6)
    # damping_cutoff, damping_f
    K.ld(p, 6, U_DA)
    p.fop(7, 6, "*", 6)
    K.mulk(p, 7, 7, 60.0)
    K.addk(p, 7, 7, 12.0)
    K.ld(p, 8, U_BR)
    K.mulk(p, 9, 8, 24.0)
    p.fop(7, 7, "+", 9)
    p.fconst(12, 84.0)
    p.fop(7, 7, "MIN", 12)                       # cut
    K.mulk(p, 9, 7, 1.0 / 12.0)
    exp2(p, 9, 9)
    p.ldi(4, F0, 1)
    p.fop(9, 4, "*", 9)
    p.fconst(12, 0.499)
    p.fop(9, 9, "MIN", 12)                       # damp_f
    p.fconst(12, 0.95)

    def infinite():
        K.addk(p, 10, 6, -0.95)
        K.mulk(p, 10, 10, 20.0)                  # to_infinite
        for r, top in ((8, 1.0), (9, 0.4999), (7, 128.0)):
            p.fconst(12, top)
            p.fop(11, 12, "-", r)
            p.fop(11, 10, "*", 11)
            p.fop(r, r, "+", 11)
    p.if_(6, "GE", 12, infinite)
    K.sv(p, U_S, 8)                              # brightness (crossfaded)
    K.sv(p, U_MAIN, 7)                           # cut
    # tan FAST: f (pi + f2 (a + b f2))
    p.fop(10, 9, "*", 9)
    K.mulk(p, 11, 10, FAST_B)
    K.addk(p, 11, 11, FAST_A)
    p.fop(11, 10, "*", 11)
    K.addk(p, 11, 11, PI_F)
    p.fop(9, 9, "*", 11)
    svf_coefs(p, 9, DG)
    # compensation 1 - atan(2^(-cut / 12)) / pi; the delay's interpolator
    K.ld(p, 7, U_MAIN)
    K.mulk(p, 7, 7, -1.0 / 12.0)
    exp2(p, 7, 7)                                # y
    p.fop(8, 7, "*", 7)
    p.fconst(9, ATAN_POLY[-1])
    for c in reversed(ATAN_POLY[:-1]):
        p.fop(9, 9, "*", 8)
        K.addk(p, 9, 9, c)
    p.fop(9, 9, "*", 7)
    K.mulk(p, 9, 9, 1.0 / PI)
    p.fconst(12, 1.0)
    p.fop(9, 12, "-", 9)
    K.ld(p, 5, U_D)
    p.fop(9, 5, "*", 9)
    p.ldi(10, DLY, 1)
    p.fop(9, 9, "-", 10)
    K.mulk(p, 9, 9, 1.0 / K.HALF)
    K.sv(p, U_INC, 9)
    # stretch, noise, bridge, allpass gain (on |non_linearity|)
    K.ld(p, 4, U_NL)
    p.iconst(0, 0)
    p.fconst(12, 0.0)
    p.if_(4, "GT", 12, lambda: p.iconst(0, 1))
    K.sv(p, U_DISP, 0)
    K.fabs(p, 4, 4)
    p.fconst(12, 2.0)
    p.fop(6, 12, "-", 4)
    p.fop(6, 4, "*", 6)
    K.mulk(p, 6, 6, 0.225)
    K.sv(p, U_SP, 6)
    K.mulk(p, 6, 6, 0.308)
    p.fconst(12, 0.408)
    p.fop(6, 12, "-", 6)
    K.sv(p, U_SPK, 6)
    K.mulk(p, 6, 5, K160)
    K.clamp(p, 6, 1.0, 2.1)
    K.sv(p, U_SC, 6)
    p.fconst(6, 0.0)
    p.fconst(12, 0.75)

    def nas():
        p.fop(6, 4, "-", 12)
        K.mulk(p, 6, 6, 4.0)
    p.if_(4, "GT", 12, nas)
    p.fop(6, 6, "*", 6)
    K.mulk(p, 6, 6, 0.1)
    K.sv(p, U_NA, 6)
    K.ld(p, 8, U_S)
    K.mulk(p, 6, 8, 0.94)
    p.fop(6, 6, "*", 8)
    K.addk(p, 6, 6, 0.06)
    K.sv(p, U_NF, 6)
    p.fop(6, 4, "*", 4)
    K.mulk(p, 6, 6, 0.01)
    K.sv(p, U_BC, 6)
    K.addk(p, 6, 4, 0.15)
    recip(p, 6, 6)
    K.mulk(p, 7, 4, -0.618)
    p.fop(6, 7, "*", 6)
    K.sv(p, U_APG, 6)


def _line_at(p: Prog, d: int, idx: int, mask: int, off: int) -> None:
    """Id = the string's line word (Ridx & MASK) + OFF (words from its record). Clobbers R8, R12,
    Ridx."""
    p.iconst(12, mask)
    p.iop(idx, idx, "AND", 12)
    p.lsh(idx, idx, 2)
    K.ld(p, 8, U_LB)
    p.iop(idx, 8, "+", idx)
    if off:
        p.iconst(12, 4 * off)
        p.iop(idx, 12, "+", idx)
    p.seti(d, idx)


def _string_sample(p: Prog) -> None:
    """One sample of the string (when the upsampler's phase wraps) -> O0, O1."""
    p.fconst(12, 1.0)
    p.fop(4, 4, "-", 12)
    p.sti(SRC, 1, 4)
    p.ldi(5, DLY, 1)
    K.ld(p, 6, U_INC)
    p.fop(5, 5, "+", 6)
    p.sti(DLY, 1, 5)                             # delay_modulation.Next()
    K.sv(p, U_D, 5)
    p.iconst(0, 0)
    K.sv(p, U_OK, 0)
    K.ld(p, 0, U_DISP)

    def disp():
        K.rnd01(p, 6)
        K.addk(p, 6, 6, -0.5)
        p.ldi(7, DISP, 1)
        p.fop(6, 6, "-", 7)
        K.ld(p, 8, U_NF)
        p.fop(6, 8, "*", 6)
        p.fop(7, 7, "+", 6)
        p.sti(DISP, 1, 7)
        K.ld(p, 8, U_NA)
        p.fop(7, 7, "*", 8)
        K.addk(p, 7, 7, 1.0)
        K.ld(p, 5, U_D)
        p.fop(5, 5, "*", 7)
        K.sv(p, U_D, 5)
        K.ld(p, 6, U_SP)
        p.fop(6, 5, "*", 6)                      # ap_delay
        K.sv(p, U_AP, 6)
        K.ld(p, 7, U_SPK)
        p.fop(7, 6, "*", 7)
        K.ld(p, 8, U_SC)
        p.fop(7, 7, "*", 8)
        p.fop(7, 5, "-", 7)                      # main_delay
        K.sv(p, U_MAIN, 7)
        p.fconst(12, 4.0)

        def ok():
            p.iconst(0, 1)
            K.sv(p, U_OK, 0)
        p.if_(6, "GE", 12, lambda: p.if_(7, "GE", 12, ok))

    def bridge():
        p.ldi(6, BRG, 1)
        K.ld(p, 7, U_BC)
        p.fop(6, 6, "*", 7)
        p.fconst(12, 1.0)
        p.fop(6, 12, "-", 6)
        p.fop(5, 5, "*", 6)
        K.sv(p, U_D, 5)
    p.ifz(0, "NE", disp, bridge)
    K.ld(p, 0, U_OK)

    def stretched():
        K.ld(p, 4, U_MAIN)                       # string_.Read(main): linear
        K.ifrac(p, 0, 5, 4)
        p.ldi(1, WP, 1)
        p.ipass(8, 1)
        p.iop(0, 8, "+", 0)
        p.ldi(3, WP2, 1)
        _line_at(p, 1, 0, LINE - 1, O_LINE)
        p.ldi(6, 0, 1)
        p.ldi(7, 1, 1)
        p.fop(7, 7, "-", 6)
        p.fop(7, 7, "*", 5)
        p.fop(9, 6, "+", 7)                      # s
        K.ld(p, 4, U_AP)                         # stretch_.Allpass(s, (size_t) ap, gain)
        p.trunc(0, 4)
        p.ipass(8, 3)
        p.iop(0, 8, "+", 0)
        _line_at(p, 1, 0, STRETCH - 1, O_STR)
        p.ldi(6, 0, 1)                           # read
        K.ld(p, 10, U_APG)
        p.fop(7, 10, "*", 6)
        p.fop(7, 9, "+", 7)                      # write
        p.ipass(0, 3)
        _line_at(p, 1, 0, STRETCH - 1, O_STR)
        p.sti(0, 1, 7)
        p.fop(7, 7, "*", 10)
        p.fop(9, 6, "-", 7)
        _home(p)
        p.iconst(12, -1)
        p.iop(3, 12, "+", 3)
        p.iconst(12, STRETCH - 1)
        p.iop(3, 3, "AND", 12)
        p.sti(WP2, 1, 3)

    def hermite():
        K.ld(p, 4, U_D)
        K.ifrac(p, 0, 5, 4)
        p.ldi(1, WP, 1)
        p.ipass(8, 1)
        p.iop(0, 8, "+", 0)
        p.iconst(12, -1)
        p.iop(0, 12, "+", 0)
        _line_at(p, 1, 0, LINE - 1, O_LINE)      # xm1 .. x2: the mirror covers the wrap
        p.ldi(6, 0, 1)                           # xm1
        p.ldi(7, 1, 1)                           # x0
        p.ldi(9, 2, 1)                           # x1
        p.ldi(10, 3, 1)                          # x2
        _home(p)
        p.fop(11, 9, "-", 6)
        K.mulk(p, 11, 11, 0.5)                   # c
        p.fop(6, 7, "-", 9)                      # v
        p.fop(9, 11, "+", 6)                     # w
        p.fop(10, 10, "-", 7)
        K.mulk(p, 10, 10, 0.5)
        p.fop(6, 9, "+", 6)
        p.fop(10, 6, "+", 10)                    # a
        p.fop(9, 9, "+", 10)                     # b_neg
        p.fop(10, 10, "*", 5)
        p.fop(10, 10, "-", 9)
        p.fop(10, 10, "*", 5)
        p.fop(10, 10, "+", 11)
        p.fop(10, 10, "*", 5)
        p.fop(9, 10, "+", 7)                     # s
    p.ifz(0, "NE", stretched, hermite)
    _home(p)
    K.ld(p, 0, U_DISP)

    def curve():                                 # curved_bridge_ = (|v| + v) sign, v = |s| - 0.025
        K.fabs(p, 6, 9)
        K.addk(p, 6, 6, -0.025)
        K.fabs(p, 7, 6)
        p.fop(6, 7, "+", 6)
        p.fconst(7, -1.5)
        p.fconst(12, 0.0)
        p.if_(9, "GT", 12, lambda: p.fconst(7, 1.0))
        p.fop(6, 6, "*", 7)
        p.sti(BRG, 1, 6)
    p.ifz(0, "EQ", curve)
    # + the excitation, clamp, the DC blocker, the damping filter, the line
    _temp(p)
    p.ldi(6, 0, 1)
    _home(p)
    p.fop(9, 9, "+", 6)
    K.clamp(p, 9, -20.0, 20.0)
    p.ldi(6, DCX, 1)
    p.sti(DCX, 1, 9)
    p.ldi(7, DCY, 1)
    K.mulk(p, 7, 7, DC_POLE)
    p.fop(7, 7, "+", 9)
    p.fop(7, 7, "-", 6)
    p.sti(DCY, 1, 7)
    svf_lp(p, 9, 7, DG)
    p.ldi(0, WP, 1)
    p.ipass(4, 0)
    _line_at(p, 1, 0, LINE - 1, O_LINE)
    p.sti(0, 1, 9)
    p.iconst(1, 3)

    def mirror():
        p.ipass(0, 4)
        _line_at(p, 1, 0, LINE - 1, O_LINE + LINE)
        p.sti(0, 1, 9)
    p.if_(4, "LT", 1, mirror, kind="i")
    _home(p)
    p.iconst(12, -1)
    p.iop(4, 12, "+", 4)
    p.iconst(12, LINE - 1)
    p.iop(4, 4, "AND", 12)
    p.sti(WP, 1, 4)
    p.ldi(0, O0, 1)
    p.sti(O1, 1, 0)
    p.sti(O0, 1, 9)


def _string(p: Prog, L) -> None:
    """16 samples of the string, added to the accumulator."""
    _temp_start(p)

    def one():
        p.ldi(4, SRC, 1)
        K.ld(p, 5, U_SRCR)
        p.fop(4, 4, "+", 5)
        p.fconst(12, 1.0)
        p.if_(4, "GT", 12, lambda: _string_sample(p), lambda: p.sti(SRC, 1, 4))
        p.ldi(5, O1, 1)                          # Crossfade(out1, out0, src_phase)
        p.ldi(6, O0, 1)
        p.fop(6, 6, "-", 5)
        p.ldi(7, SRC, 1)
        p.fop(6, 6, "*", 7)
        p.fop(6, 5, "+", 6)
        _temp(p)
        p.ldi(7, 16, 1)
        p.fop(7, 7, "+", 6)
        p.sti(16, 1, 7)
        _home(p)
        inc_word(p, U_K, by=4)
    p.loop(L.W["inner"], K.HALF, one)


def _voice(p: Prog, L) -> None:
    """StringVoice::Render for string U_STR."""
    K.ld(p, 0, U_STR)
    rec_at(p, 4, 0)
    p.seti(1, 4)
    K.sv(p, U_STA, 4)
    p.iconst(12, -4 * O_ST)
    p.iop(4, 12, "+", 4)
    K.sv(p, U_LB, 4)                             # the record (its line)
    K.ld(p, 0, K.S_TRIG)

    def trig():
        K.ld(p, 0, U_STR)
        K.ld(p, 1, U_ACT)
        p.if_(0, "EQ", 1, lambda: _excite_trig(p), kind="i")
    p.ifz(0, "NE", trig)
    _excite(p, L)
    _string_params(p)
    _string(p, L)


def half(p: Prog, L) -> None:
    """StringEngine::Render, 16 samples at I4."""
    K.big_at(p, L, 4)
    K.sv(p, U_BIG, 4)
    _globals(p)
    _f0s(p)
    p.iconst(0, 0)
    K.sv(p, U_STR, 0)

    def each():
        _voice(p, L)
        inc_word(p, U_STR)
    p.loop(L.W["n5"], N_STR, each)
    _temp_start(p)

    def out():
        _temp(p)
        p.ldi(5, 16, 1)
        p.stpost(4, 5)
        p.iconst(5, 0)
        p.sti(16, 1, 5)
        inc_word(p, U_K, by=4)
    p.loop(L.W["n4"], K.HALF, out)
