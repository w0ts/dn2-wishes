"""PLAITS' SWARM (Mutable Instruments Plaits' swarm engine; MIT, Emilie Gillet:
plaits/dsp/engine/swarm_engine.{h,cc}): eight voices, each a GrainEnvelope steering an
AdditiveSawOscillator (its poly-BLEP sawtooth), summed. OUT only: the voices' FastSineOscillators
write Plaits' AUX, which the DN2 does not render, so they are left out.

The trigger is patched (the DN2 triggers every note), so the envelopes run in burst mode: a
trigger (S_TRIG) starts a burst (phase 0.5, rate x16, then slowing by 0.8..1.0 at each grain).
One stmlib::Random for the voice (plk.rng, S_RNG), consumed in Plaits' order.

Memory: the voices' state in the voice's DDR area (11 words a voice); the union holds the half's
parameters and the 16-sample accumulator. Code: the per-voice block work runs once a voice in a
loop over the voices; the per-sample sawtooth is one loop body run 16 times (emitted once).
"""

from __future__ import annotations

from . import core as C
from . import plk as K
from ..md import core as MK
from ..perc.dsl import Prog

MODEL = "SWRM"
NV = 8                                         # kNumSwarmVoices
HALF = K.HALF

# union words
ACC = 0                                        # U0 .. U15: the half's output, summed over voices
W_SR, W_DEN, W_SPR, W_F0, W_VB, W_RANK, W_GT = (K.U0 + 16 + k for k in range(7))
NU_USED = 23

# a voice's words in DDR (stride V_N): GrainEnvelope, then AdditiveSawOscillator
V_FROM, V_INT, V_PH, V_FM, V_AMP, V_PREV, V_FC, V_SPH, V_SNX, V_SF, V_SG = range(11)
V_N = 11
V_INIT = (0.0, 1.0, 1.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.01, 0.0)
BIG_USED = NV * V_N
# 2026-11-10 (poly16): voices 0..4's words in the slot's free host words W[9..63] (L1), 5..7's still
# in DDR (no room for them): their DDR accesses 5/8 fewer, the same arithmetic
from ..md import core as _MDK
L1_W, L1_NV = 9, 5
assert L1_W + L1_NV * V_N <= _MDK.NW


def _first(p: Prog) -> None:
    """R0 = voice 0's words (the slot's W[9]). Clobbers R12."""
    p.geti(0, 3)
    p.iconst(12, p.ioff(3, 4 * L1_W))
    p.iop(0, 12, "+", 0)


def _acc_at(p: Prog, L: C.Layout) -> None:
    """I1 = the accumulator's first word (union word ACC). Clobbers R0, R12."""
    p.ld(0, L.md.C["mdb"])
    p.iconst(12, 4 * (MK.S0 + K.U0 + ACC))
    p.iop(0, 12, "+", 0)
    p.seti(1, 0)


def _vb(p: Prog) -> None:
    """I1 = this voice's DDR words. Clobbers R0."""
    K.ld(p, 0, W_VB)
    p.seti(1, 0)


def init(p: Prog, L: C.Layout) -> None:
    """SwarmEngine::Init + Reset: every voice's GrainEnvelope and saw at Init; the sum at 0."""
    def voice():
        for v in V_INIT:
            p.fconst(0, v)
            p.stpost(1, 0)
    _first(p)
    p.seti(1, 0)
    p.loop_r(10, L1_NV, voice)
    K.big_at(p, L, 0)
    p.seti(1, 0)
    p.loop_r(10, NV - L1_NV, voice)
    _acc_at(p, L)
    p.fconst(0, 0.0)
    p.loop_r(10, HALF, lambda: p.stpost(1, 0))


def _saw_body(p: Prog) -> None:
    """One sample of AdditiveSawOscillator::Render, added to the sum at I1 (I1 moves on).
    R4 phase, R5 next_sample, R6/R7 frequency and its step, R8/R9 gain and its step.
    Clobbers R0-R3, R12, R13."""
    p.fop(6, 6, "+", 7)
    p.fop(8, 8, "+", 9)
    p.fpass(3, 5)                              # this
    p.fconst(2, 0.0)                           # next
    p.fop(4, 4, "+", 6)
    p.fconst(13, 1.0)

    def wrap():
        p.fop(4, 4, "-", 13)
        K._pm()._recip_inline(p, 0, 6, 1)
        p.fop(0, 4, "*", 0)                    # t = phase / frequency
        p.fconst(12, 0.5)
        p.fop(1, 12, "*", 0)
        p.fop(1, 1, "*", 0)
        p.fop(3, 3, "-", 1)                    # this -= ThisBlepSample(t)
        p.fop(1, 13, "-", 0)
        p.fop(2, 12, "*", 1)
        p.fop(2, 2, "*", 1)                    # next -= NextBlepSample(t)
    p.if_(4, "GE", 13, wrap)
    p.fop(5, 2, "+", 4)
    p.fop(3, 3, "+", 3)
    p.fop(3, 3, "-", 13)
    p.fop(3, 3, "*", 8)
    p.ldi(1, 0, 1)
    p.fop(1, 1, "+", 3)
    p.stpost(1, 1)


def _step(p: Prog) -> None:
    """GrainEnvelope::Step(density, burst_mode = true, start_burst = S_TRIG)."""
    p.ldi(4, V_PH, 1)
    p.ldi(5, V_FM, 1)
    p.iconst(6, 0)

    def burst():
        p.fconst(4, 0.5)
        p.fconst(5, 16.0)
        p.iconst(6, 1)

    def run():
        K.ld(p, 7, W_DEN)
        p.fop(7, 7, "*", 5)
        p.fop(4, 4, "+", 7)
        p.fconst(12, 1.0)

        def wrap():
            K.ifrac(p, 0, 1, 4)
            p.fpass(4, 1)
            p.iconst(6, 1)
        p.if_(4, "GE", 12, wrap)
    K.ld(p, 0, K.S_TRIG)
    p.ifz(0, "NE", burst, run)
    p.sti(V_PH, 1, 4)
    p.sti(V_FM, 1, 5)

    def randomize():
        p.ldi(7, V_FROM, 1)
        p.ldi(8, V_INT, 1)
        p.fop(7, 7, "+", 8)
        p.sti(V_FROM, 1, 7)
        K.rnd01(p, 8)
        p.fop(8, 8, "-", 7)
        p.sti(V_INT, 1, 8)
        K.rnd01(p, 8)
        K.mulk(p, 8, 8, 0.2)
        K.addk(p, 8, 8, 0.8)
        p.ldi(5, V_FM, 1)
        p.fop(5, 5, "*", 8)
        p.sti(V_FM, 1, 5)
    p.ifz(6, "NE", randomize)


def _amplitude(p: Prog) -> None:
    """W_GT = GrainEnvelope::amplitude(size_ratio) / kNumSwarmVoices."""
    K.ld(p, 7, W_SR)
    p.fconst(8, 1.0)                           # target
    p.iconst(9, 0)

    def grain():
        p.iconst(9, 1)
        p.ldi(4, V_PH, 1)
        K.addk(p, 4, 4, -0.5)
        p.fop(4, 4, "*", 7)
        K.clamp(p, 4, -1.0, 1.0)
        K.mulk(p, 4, 4, 0.5)
        K.addk(p, 4, 4, 1.25)
        K.sinp(p, 8, 4)
        K.addk(p, 8, 8, 1.0)
        K.mulk(p, 8, 8, 0.5)
    p.fconst(12, 1.0)
    p.if_(7, "GE", 12, grain)
    p.ldi(5, V_PREV, 1)
    p.iconst(10, 0)
    p.fconst(12, 1.0)
    p.if_(5, "GE", 12, lambda: p.iconst(10, 1))
    p.ldi(6, V_FC, 1)
    p.if_(9, "NE", 10, lambda: p.fconst(6, 0.5), kind="i")
    K.mulk(p, 6, 6, 0.95)
    p.sti(V_FC, 1, 6)
    p.sti(V_PREV, 1, 7)
    p.ldi(4, V_AMP, 1)
    p.fconst(12, 0.5)
    p.fop(6, 12, "-", 6)
    p.fop(5, 8, "-", 4)
    p.fop(5, 6, "*", 5)
    p.fop(4, 4, "+", 5)
    p.sti(V_AMP, 1, 4)
    K.mulk(p, 4, 4, 1.0 / NV)
    K.sv(p, W_GT, 4)


def _frequency(p: Prog) -> None:
    """F8 = the saw's frequency: f0 x SemitonesToRatio(48 expo spread rank) x (1 + linear),
    at most kMaxFrequency."""
    p.ldi(4, V_FROM, 1)
    K.ld(p, 7, W_SR)
    p.fconst(12, 1.0)

    def glide():
        p.ldi(5, V_INT, 1)
        p.ldi(6, V_PH, 1)
        p.fop(5, 5, "*", 6)
        p.fop(4, 4, "+", 5)
        p.fop(4, 4, "+", 4)
        K.addk(p, 4, 4, -1.0)
    p.if_(7, "LT", 12, glide)
    K.mulk(p, 4, 4, 48.0)
    K.ld(p, 5, W_SPR)
    p.fop(4, 4, "*", 5)
    K.ld(p, 6, W_RANK)
    p.fop(4, 4, "*", 6)
    K.semis(p, 8, 4)
    K.ld(p, 3, W_F0)
    p.fop(8, 3, "*", 8)
    K.ld(p, 6, W_RANK)
    K.addk(p, 4, 6, 0.01)
    p.fop(4, 6, "*", 4)
    K.ld(p, 5, W_SPR)
    p.fop(4, 4, "*", 5)
    K.mulk(p, 4, 4, 0.25)
    K.addk(p, 4, 4, 1.0)
    p.fop(8, 8, "*", 4)
    p.fconst(12, K.F_MAX)
    p.fop(8, 8, "MIN", 12)


def _voice(p: Prog, L: C.Layout) -> None:
    """SwarmVoice::Render for the voice the loop counter names (n5: 8 .. 1 is voice 0 .. 7)."""
    _vb(p)
    p.ld(0, L.W["n5"])
    p.iconst(12, NV - 3)
    p.iop(0, 12, "-", 0)                       # i - 3
    p.iconst(12, 0)
    p.float_(0, 0, 12)
    K.mulk(p, 0, 0, 1.0 / 3.0)                 # rank = (i - 3) / 3 (Plaits' n is (8 - 1) / 2 = 3)
    K.sv(p, W_RANK, 0)
    _step(p)
    _amplitude(p)
    _frequency(p)
    # the saw's interpolators over the half
    p.ldi(6, V_SF, 1)
    p.fop(7, 8, "-", 6)
    K.mulk(p, 7, 7, 1.0 / HALF)
    p.ldi(8, V_SG, 1)
    K.ld(p, 9, W_GT)
    p.fop(9, 9, "-", 8)
    K.mulk(p, 9, 9, 1.0 / HALF)
    p.ldi(4, V_SPH, 1)
    p.ldi(5, V_SNX, 1)
    _acc_at(p, L)
    p.loop_r(10, HALF, lambda: _saw_body(p))
    _vb(p)
    p.sti(V_SPH, 1, 4)
    p.sti(V_SNX, 1, 5)
    p.sti(V_SF, 1, 6)
    p.sti(V_SG, 1, 8)
    # the next voice: size_ratio x 0.97, its words
    K.ld(p, 0, W_SR)
    K.mulk(p, 0, 0, 0.97)
    K.sv(p, W_SR, 0)
    K.ld(p, 0, W_VB)
    p.iconst(12, 4 * V_N)
    p.iop(0, 12, "+", 0)
    p.ld(1, L.W["n5"])
    p.iconst(12, NV - L1_NV + 1)                 # voice L1_NV - 1 just done: the next in DDR
    p.if_(1, "EQ", 12, lambda: K.big_at(p, L, 0), kind="i")
    K.sv(p, W_VB, 0)


def half(p: Prog, L: C.Layout) -> None:
    """SwarmEngine::Render(16 samples) -> I4."""
    K.ld(p, 3, K.S_NOTE)
    K.note_freq(p, 4, 3)
    K.sv(p, W_F0, 4)
    K.par(p, 3, 1)
    K.mulk(p, 3, 3, 120.0)
    K.note_freq(p, 4, 3)
    K.mulk(p, 4, 4, 0.025)
    K.mulk(p, 4, 4, float(HALF))               # density (control_rate 16)
    K.sv(p, W_DEN, 4)
    K.par(p, 3, 0)
    p.fop(4, 3, "*", 3)
    p.fop(4, 4, "*", 3)                        # spread = harmonics^3
    K.sv(p, W_SPR, 4)
    K.par(p, 3, 2)
    p.fconst(12, 1.0)
    p.fop(3, 12, "-", 3)
    K.mulk(p, 3, 3, 84.0)
    K.semis(p, 4, 3)
    K.mulk(p, 4, 4, 0.25)                      # size_ratio
    K.sv(p, W_SR, 4)
    _first(p)
    K.sv(p, W_VB, 0)
    p.loop(L.W["n5"], NV, lambda: _voice(p, L))
    _acc_at(p, L)
    p.fconst(2, 0.0)

    def out():
        p.ldi(0, 0, 1)
        p.stpost(4, 0)
        p.stpost(1, 2)
    p.loop_r(10, HALF, out)
