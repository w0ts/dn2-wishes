# SPDX-License-Identifier: AGPL-3.0-or-later
"""DRONE: a coupled network of four sine generators for drones and ambient, with binaural
beats, ported from Optimist (GPL-3.0-only, firmware/src/engines/drone/eng_drone.c and
drone_mem.h), after Caravel's DRONE by bonszaimusic (GPL-3.0-only, github.com/bonszaimusic/
caravel firmware/src/eng_drone.c), as a Monomachine-style machine (THIRD-PARTY.md).

One network a track at 44.1 kHz (PERC's stream, Optimist's own rate). A note plays four sines;
each one's phase is moved (under a quarter turn) by another's previous sample through a soft
odd cubic (CHAR); the four averaged, a ~14 Hz DC block, a one-pole low-pass (TONE), a soft
knee at 16000/32768. A note transposes the whole network.

Parameters (page 1, knob / 128): SPREAD (ratios 1 : 1 + s/4 : 1 + s/2 : 1 + s), COUPLE (the
phase modulation, 0 .. a quarter turn), TOPO (PAIRS 0<->1 2<->3, CHAIN 0->1->2->3, RING
3->0->1->2->3: knob x 3 picks; a change crossfades over ~23 ms, PAIRS to RING through CHAIN),
CHAR (sine -> 1.5 x - 0.5 x^3), DRIFT (each generator's slow triangle, up to +-6.8 cents,
0.015 .. 0.11 Hz), TONE, BEAT (0 OFF, else Optimist's F_LFOHZ curve rounded as LFO_HZ_X100,
0.05 .. 40 Hz), DTUNE (Optimist's track DETUNE: the generators {-3 -1 1 3} x up to ~6.7 cents).
Page 2 (`core.page2`): q0 GLID (0 off, else dnfw.engines.analog2.a2glide.ms_of(q0): 1 ms .. 1 s as Optimist's TIME_MS
index q0 x 127, then up to 5 minutes, 2026-11-11),
q1 GLTY (index trunc(2 q1): 0 RATE = GLID is the time an octave takes, 1 TIME = GLID is the time
of any glide; default 0.5 = TIME), q2 OCT (2026-11-11, the User: -3..+3 octaves, trunc(7 q2) - 3, default
0.5 = 0, so a project saved before it plays as it did; 12 x OCT semitones are added to the note before the
glide: a trig glides into a new octave as into any note, a turn between trigs moves the pitch at once),
q3..q5 unused, q6 HOLD (index trunc(2 q6), default OFF; the latch
itself is the ColdFire's: csrc/hold/hold.c). The glide is legato (2026-11-10, the User's brief, no new
control): a note glides only when its trig comes while the slot's gate is still open (no note-off since
the last note: a key still down, an overlapping trig, or a HOLD latch); a separate note jumps.

Against Optimist:
- Float32 for its Q15 integers. The controls' ~23 ms followers and the increments' (2^-10 a
  sample) are stepped once a 16-sample half, exactly (r^16), the half using their mean over
  its 16 samples; the drift's triangle and the generators' steps likewise once a half (the
  triangle moves 3e-5 of its range in a half). Phases stay 32-bit integers, as Optimist's.
  Its integer followers (floored d >> 10) lag the exponential a little: after a note change the
  network sits ~4e-4 turn off the reference's phase (47 dB, inaudible).
- The sine: s (1 - s^2) Q(s^2), s = 2 x phase in -1..1, Q of degree 3 (error 1.1e-5, under
  Optimist's own Q15 step 3.1e-5; its 1024-point table 4.7e-6). tanh in the knee: 1 - 2 /
  (2^(2v/ln2) + 1) with tb303's precise exp2 (Optimist: TANH_Q15, 257 points).
- The DC block keeps Optimist's integer offset: its floored dco >> 9 adds half an LSB (2^-16) a
  sample on average, a standing +0.0078 an ear (mid +0.0153, -36 dB) that also tilts the knee;
  emulated (+2^-16 a sample: 55 dB to the reference against 30 dB without); likewise the
  one-pole's floored product (-2^-16 a sample: TONE 0 54 dB against 25) and the drift's
  inc >> 16 (DRIFT 127 63 dB against 41).
- COUPLE's "+ m->shape" and TONE's "+ m->cutoff" are gone (the DN2's LFOs move the knobs).
- Glide as Optimist's voice.c (glide_set / its per-block step, in 1/4096 semitone; since 2026-11-11 not
  truncated, and up to 5 minutes: dnfw.engines.analog2.a2glide): a trig with GLID > 0 glides from the current pitch, except into a fresh network. The
  note's later moves without a trig (VW pitch) pass straight through.
- HOLD: the machine sees no key-up, and the DN2's amp envelope gates the track, so the latch
  itself (a note held past its key-up, the key again letting it go) is NOT done here: it needs
  the DN2's gate path (the coordinator's). What the machine does: HOLD OFF is Optimist's
  note_on (a trig on a silent voice starts the network afresh, a trig on a sounding one goes on
  with it); HOLD ON never restarts it, a trig only retargets the pitch. "Silent" is the
  machine's own state: S_READY 0 (after init), or S_IDLE 1, which any caller may write (e.g.
  PERC when a resting voice wakes); without that the network restarts only after init.
- BEAT: two ears (twice the cost). The mid yl + yr is the machine's output (BEAT OFF 2 yl, the
  scale of Optimist's out += 2 yl a with a = 1); the side yl - yr goes to this slot's side block
  in L2 at SIDE_L2 + SIDE_STRIDE x t (t = PERC's word C["t"], the voice slot): words 0..31 the
  block's side (half h at 16 h), word 32 the block's sum of |mid| (pre-amp), word 33 1.0 (BEAT
  on and written this block); BEAT OFF writes nothing (the coordinator's post-pan pass reads
  word 33, scales the side by |post mid| / |pre mid| and clears the flag). BEAT OFF -> ON
  starts the right ear on the left's state (Optimist copies it every block while OFF).
"""

from __future__ import annotations

import math

from ...mnm import core as C
from ..tb303.tb303 import _exp2p
from ...perc.dsl import Prog

NAME, ID = "DRONE", 67
PNAMES = ("SPRD", "CPL", "TOPO", "CHAR", "DRFT", "TONE", "BEAT", "DTUN")
DEFAULTS = (0, 12, 0, 18, 32, 76, 0, 24)         # Optimist's defaults; DTUNE: STILL AIR's 24
PNAMES2 = ("GLID", "GLTY", "OCT", "---", "---", "---", "HOLD")
DEFAULTS2 = (0.0, 0.5, 0.5, 0.5, 0.0, 1.0, 0.0)  # q0..q6 as 0..1 (PERC's records' defaults)

SIDE_L2 = 0x200B1800                             # the slots' side blocks (the coordinator's)
SIDE_STRIDE = 0x90                               # 36 words a slot
SR = 44100.0
FOL = 1.0 - 2.0 ** -10                           # drone_follow: ~23 ms
R16 = FOL ** 16                                  # a half's follower step
A16 = FOL * (1.0 - R16) / (16.0 * (1.0 - FOL))   # the mean of its 16 values
MAXINC = 0.375                                   # DRONE_MAXINC, turns a sample
BEAT_K = (2 ** 32 + 50 * 44100) // (100 * 44100)   # DRONE_BEAT_K (974)
KNEE = 16000.0 / 32768.0
IV = (0.0, 16384.0, 32768.0, 65536.0)            # SPREAD's ratios - 1, Q16
DT = (-3.0, -1.0, 1.0, 3.0)
PH0, DPH0 = 0x19234567, 0x39123457               # the fresh network's phases
SIN_Q = (-0.06377979419113637, 0.5173279877339564, -2.0245718986613155, 3.141485754684884)

# an ear's words (16 a ear; ear e at 16 e): phases (ints), previous outputs, steps (ints), DC
# block in/out, low-pass, the sample's output
E_PH, E_PREV, E_ST, E_DCI, E_DCO, E_LOW, E_Y = 0, 4, 8, 12, 13, 14, 15
EAR = 16
S_DPH, S_INC, S_CTL = 32, 36, 40                 # drift phases (ints), increments, 5 controls
(S_READY, S_IDLE, S_CUR, S_GST, S_TGT, S_TRG, S_BI) = range(45, 52)
D_FQ, D_T = 52, 56                               # per block: the increments' and controls' targets
(D_CA0, D_CB0, D_C1, D_CA2, D_CB2, D_H, D_H1, D_G1, D_ABS, T_E0, T_E1) = range(61, 72)
K_IV, K_DT, K_DR = 72, 76, 80                    # per generator, set by init (x knob / 128): IV x 128 / 127,
# 2026-11-10: the slot's gate (1 from its note-on until its note-off: frame +36, bit slot) and whether
# this note began legato (the gate still open at its trig)
S_GATE, S_LEG = 84, 85
NOTE_OFF_WORD = 0x25C4B0                         # frame +36 (low half): the note-off / amp gate-off mask, bit slot
S_END = 86                                       # DT x 252 x 128 / 127; and (8 + g) / 8
CPL, TOPO, CHR, DRF, TONE = range(5)


def _ld(p: Prog, d: int, k: int) -> None:
    C.st(p, d, k)


def _sv(p: Prog, k: int, s: int) -> None:
    C.sts(p, k, s)


def _k(p: Prog, d: int, a: int, op: str, x: float) -> None:
    """Fd = Fa op x (a constant in R12)."""
    p.fconst(12, x)
    p.fop(d, a, op, 12)


def exact(A: int, F: int, knobs, pre: int = 0) -> dict:
    """no Monomachine increments: DRONE takes its pitch from VW pitch and OCT (pitch below)"""
    return {}


def init(p: Prog, L: C.Layout) -> None:
    """Every word 0 (the next render installs the network: S_READY 0) but the generators'
    constants."""
    _base(p, L, 0, 0)
    p.seti(5, 0)
    p.iconst(6, 0)
    p.loop(L.W["n5"], S_END, lambda: p.stpost(5, 6))
    for g in range(4):
        for w, x in ((K_IV, IV[g] * 128.0 / 127.0), (K_DT, DT[g] * 252.0 * 128.0 / 127.0),
                     (K_DR, (8.0 + g) / 8.0)):
            p.fconst(0, x)
            _sv(p, w + g, 0)


def _exp2(p: Prog, d: int, x: int) -> None:
    """Fd = 2^Fx, tb303's precise exp2 as one subroutine. Clobbers R0, R1, R12, R14, R15, I12."""
    p.fpass(15, x)
    p.call("drone_exp2", lambda: (_exp2p(p, 14, 15), p.fpass(15, 14)))
    p.fpass(d, 15)


def trig(p: Prog, L: C.Layout) -> None:
    """A note: the pitch is retargeted at the next `pitch` (S_TRG); HOLD OFF restarts a silent
    network (S_IDLE), HOLD ON never does."""
    p.iconst(0, 2)                               # 2026-11-10: acted on at the second `pitch` after the trig (the note's pitch word lags the trig by a call)
    _sv(p, S_TRG, 0)
    _ld(p, 0, S_GATE)                            # 2026-11-10: legato = the gate still open (or latched: HOLD)
    _sv(p, S_LEG, 0)
    p.iconst(0, 1)
    _sv(p, S_GATE, 0)
    C.page2(p, L, 1, 6)
    p.fconst(12, 0.5)
    _ld(p, 0, S_IDLE)
    p.if_(1, "LT", 12, lambda: p.ifz(0, "NE", lambda: (p.iconst(0, 0), _sv(p, S_READY, 0))))
    p.iconst(0, 0)
    _sv(p, S_IDLE, 0)


def _glide_start(p: Prog, L: C.Layout) -> None:
    """S_GST: voice.c glide_set's step (1/4096 semitone a block, as semitones) for GLID's time
    ms = a2glide.ms_of(q0) (2026-11-11: up to 5 minutes): TIME |d| / trunc(ms FS / 1000 / 32), RATE
    ENV_LIN x 3 / 1024, neither truncated (a2glide.step_semis). In: F1 the target,
    F2 GLID (> 0)."""
    from ..analog2 import a2glide as G
    G.curve_x(p, 3, 2)
    _k(p, 3, 3, "*", -math.log2(10.0))
    _exp2(p, 4, 3)                               # 1 / ms
    _k(p, 4, 4, "*", float(1 << 24) * 32.0 * 1000.0 / SR)
    p.trunc(5, 4)                                # ENV_LIN
    C.page2(p, L, 6, 1)

    def time_():
        _target(p, L)                            # (the target again: _exp2p clobbered R1)
        p.iconst(12, 0)
        p.float_(4, 5, 12)
        from ...perc import machines as PM
        PM._recip_inline(p, 6, 4, 7)
        _k(p, 6, 6, "*", float(1 << 24) * (1.0 + 2e-7))
        p.trunc(5, 6)                            # ticks
        p.iconst(12, 0)
        p.float_(4, 5, 12)
        PM._recip_inline(p, 6, 4, 7)             # 1 / ticks
        _ld(p, 3, S_CUR)
        p.fop(3, 1, "-", 3)
        p.fconst(12, 0.0)
        p.fop(4, 12, "-", 3)
        p.fop(3, 3, "MAX", 4)
        _k(p, 3, 3, "*", 4096.0)                 # |d|, units
        p.fop(3, 3, "*", 6)
        _k(p, 3, 3, "*", 1.0 + 2e-7)             # gstep, units

    def rate():
        p.iconst(12, -10)
        p.float_(3, 5, 12)
        _k(p, 3, 3, "*", 3.0)
    p.fconst(12, 0.5)
    p.if_(6, "GE", 12, time_, rate)
    G.step_semis(p)
    _sv(p, S_GST, 3)


def _target(p: Prog, L: C.Layout) -> None:
    """F1 = the note: VW pitch + 12 x OCT (q2: trunc(7 q2) - 3, -3..+3; OCT 0 adds 0.0, so the
    pitch is bit for bit as before). One subroutine. Clobbers R12, R14, I12."""
    def body():
        C.vw(p, 1, "pitch")
        C.page2(p, L, 14, 2)
        _k(p, 14, 14, "*", 7.0)
        p.trunc(14, 14)
        p.iconst(12, 6)
        p.iop(14, 14, "MIN", 12)
        p.iconst(12, -3)
        p.iop(14, 14, "+", 12)
        p.iconst(12, 0)
        p.float_(14, 14, 12)
        _k(p, 14, 14, "*", 12.0)
        p.fop(1, 1, "+", 14)
    p.call("drone_target", body)


def _pitch_glide(p: Prog, L: C.Layout) -> None:
    """S_CUR (semitones) from the note (_target): a trig jumps to it or starts a glide; otherwise
    its moves pass straight through; the glide steps once a block (voice.c)."""
    _target(p, L)
    _ld(p, 0, S_TRG)

    def on_trig():
        p.iconst(0, 0)
        _sv(p, S_TRG, 0)
        C.page2(p, L, 2, 0)
        _ld(p, 0, S_READY)
        p.fconst(12, 0.0)

        def jump():
            _sv(p, S_CUR, 1)
            p.fconst(3, 0.0)
            _sv(p, S_GST, 3)

        def legato_or_all():                     # legato only: the gate still open at the trig
            _ld(p, 0, S_LEG)
            p.ifz(0, "NE", lambda: _glide_start(p, L), jump)
        p.if_(2, "GT", 12, lambda: p.ifz(0, "NE", legato_or_all, jump), jump)

    def follow():                                # CUR += T - last T
        _ld(p, 2, S_TGT)
        p.fop(2, 1, "-", 2)
        _ld(p, 3, S_CUR)
        p.fop(3, 3, "+", 2)
        _sv(p, S_CUR, 3)
    def pending():
        p.iconst(12, 1)
        p.if_(0, "EQ", 12, on_trig, lambda: (p.iconst(0, 1), _sv(p, S_TRG, 0), follow()), kind="i")
    p.ifz(0, "NE", pending, follow)
    _target(p, L)                                # (the glide's set-up clobbers F1)
    _sv(p, S_TGT, 1)
    _ld(p, 2, S_CUR)                             # one step towards T (S_GST 0: there)
    _ld(p, 3, S_GST)
    p.fop(4, 1, "-", 2)
    p.fconst(12, 0.0)
    p.fop(5, 12, "-", 3)
    p.if_(3, "EQ", 12, lambda: p.fpass(2, 1),
          lambda: (p.fop(4, 4, "MIN", 3), p.fop(4, 4, "MAX", 5), p.fop(2, 2, "+", 4)))
    _sv(p, S_CUR, 2)


def _fq(p: Prog, L: C.Layout) -> None:
    """D_FQ: the generators' increments (turns a sample) from S_CUR, SPREAD and DTUNE, with
    Optimist's integer truncations. Clobbers R0-R8, R12, R14, R15, I1, I12."""
    _ld(p, 2, S_CUR)
    _k(p, 2, 2, "+", -69.0)
    _k(p, 3, 2, "*", 1.0 / 12.0)
    _exp2(p, 4, 3)
    _k(p, 4, 4, "*", 440.0 / SR)                 # the key's increment
    C.par(p, 5, 0)                               # spr / 128
    C.par(p, 6, 7)                               # det / 128
    p.iconst(8, 0)
    _base(p, L, 0, 0)
    p.seti(1, 0)

    def gen():                                   # I1: generator g's words
        p.ldi(7, K_IV, 1)
        p.fop(7, 7, "*", 5)
        p.trunc(0, 7)
        p.float_(7, 0, 8)
        _k(p, 7, 7, "*", 2.0 ** -16)
        _k(p, 7, 7, "+", 1.0)
        p.fop(7, 4, "*", 7)
        p.ldi(3, K_DT, 1)
        p.fop(3, 3, "*", 6)
        p.trunc(0, 3)
        p.float_(3, 0, 8)
        _k(p, 3, 3, "*", 2.0 ** -16)
        _k(p, 3, 3, "+", 1.0)
        p.fop(7, 7, "*", 3)
        _k(p, 7, 7, "MIN", MAXINC)
        p.sti(D_FQ, 1, 7)
        p.ldpost(3, 1)
    p.loop(L.W["n5"], 4, gen)


def _targets(p: Prog) -> None:
    """D_T: the controls' targets (drone_targets without the modulations)."""
    C.par(p, 1, 1)
    _sv(p, D_T + CPL, 1)
    C.par(p, 1, 2)                               # TOPO: trunc(3 knob / 128), 0..2
    _k(p, 1, 1, "*", 3.0)
    p.trunc(0, 1)
    p.iconst(12, 2)
    p.iop(0, 0, "MIN", 12)
    p.iconst(12, 0)
    p.float_(1, 0, 12)
    _sv(p, D_T + TOPO, 1)
    for k, w in ((3, CHR), (4, DRF)):
        C.par(p, 1, k)
        _k(p, 1, 1, "*", 128.0 * 258.0 / 32768.0)
        _sv(p, D_T + w, 1)
    C.par(p, 1, 5)
    _sv(p, D_T + TONE, 1)


def _base(p: Prog, L: C.Layout, d: int, off: int) -> None:
    """Rd = the byte address of slot word S0 + off. Clobbers R12."""
    from ...md import core as K
    p.ld(d, L.md.C["mdb"])
    p.iconst(12, 4 * (K.S0 + off))
    p.iop(d, 12, "+", d)


def _install(p: Prog, L: C.Layout) -> None:
    """Optimist's afresh: the network's words 0, the phases apart, the increments and the
    controls at their targets."""
    _base(p, L, 0, 0)
    p.seti(5, 0)
    p.iconst(6, 0)
    p.loop(L.W["n5"], S_INC, lambda: p.stpost(5, 6))
    for g in range(4):
        p.iconst(0, PH0 * g)
        _sv(p, E_PH + g, 0)
        _sv(p, EAR + E_PH + g, 0)
        p.iconst(0, DPH0 * g)
        _sv(p, S_DPH + g, 0)
        _ld(p, 1, D_FQ + g)
        _sv(p, S_INC + g, 1)
    for k in range(5):
        _ld(p, 1, D_T + k)
        _sv(p, S_CTL + k, 1)
    p.iconst(0, 1)
    _sv(p, S_READY, 0)


def _side_base(p: Prog, L: C.Layout, d: int) -> None:
    """Rd = this slot's side block (SIDE_L2 + SIDE_STRIDE t). Clobbers R12-R14."""
    p.ld(13, L.perc.C["t"])
    p.lsh(14, 13, 7)
    p.lsh(13, 13, 4)
    p.iop(d, 13, "+", 14)
    p.iconst(12, SIDE_L2)
    p.iop(d, 12, "+", d)


def _beat(p: Prog, L: C.Layout) -> None:
    """S_BI: BEAT's increment (0 OFF); OFF -> ON copies the left ear to the right; ON: the side
    block's |mid| sum 0 and its flag 1."""
    C.par(p, 1, 6)
    _k(p, 1, 1, "*", 128.0)
    p.iconst(0, 0)
    p.fconst(12, 0.5)

    def on():                                    # round(100 x 0.05 x 800^(knob / 127)) x 974
        _k(p, 2, 1, "*", math.log2(800.0) / 127.0)
        _exp2(p, 3, 2)
        _k(p, 3, 3, "*", 5.0)
        _k(p, 3, 3, "+", 0.5)
        p.trunc(0, 3)
        p.iconst(12, 0)
        p.float_(3, 0, 12)
        _k(p, 3, 3, "*", float(BEAT_K))
        p.trunc(0, 3)
    p.if_(1, "GT", 12, on)
    _ld(p, 1, S_BI)
    _sv(p, S_BI, 0)

    def turned_on():                             # (E_ST too: the half rewrites it)
        _base(p, L, 2, 0)
        p.seti(1, 2)
        _base(p, L, 2, EAR)
        p.seti(5, 2)
        p.loop(L.W["n5"], E_Y, lambda: (p.ldpost(2, 1), p.stpost(5, 2)))
    p.ifz(0, "NE", lambda: (p.ifz(1, "EQ", turned_on), _side_base(p, L, 0), p.seti(5, 0),
                            p.fconst(2, 0.0), p.sti(32, 5, 2), p.fconst(2, 1.0), p.sti(33, 5, 2)))


def _gate_off(p: Prog, L: C.Layout) -> None:
    """S_GATE 0 when this block's frame carries the slot's note-off (+36 bit slot: the DN2's key-up or
    the trig's end; HOLD on the ColdFire keeps it from coming)"""
    from ...perc import program as PP
    p.ld(0, NOTE_OFF_WORD)
    p.iconst(12, 0xFFFF)
    p.iop(0, 0, "AND", 12)
    p.iconst(1, 1)
    p.ld(9, L.perc.C["t"])
    PP._shift_by(p, 1, 9)
    p.iop(0, 0, "AND", 1)
    p.ifz(0, "NE", lambda: (p.iconst(1, 0), _sv(p, S_GATE, 1)))


def pitch(p: Prog, L: C.Layout) -> None:
    """Once a DN2 block (Optimist's render's set-up): the glide, the increments' and controls'
    targets, BEAT, and a fresh network installed."""
    _gate_off(p, L)
    _pitch_glide(p, L)
    _fq(p, L)
    _targets(p)
    _beat(p, L)
    _ld(p, 0, S_READY)
    p.ifz(0, "EQ", lambda: _install(p, L))


def _half_ctl(p: Prog) -> None:
    """The controls' followers a half on; the half's coefficients from their means."""
    for k in range(5):
        _ld(p, 1, S_CTL + k)
        _ld(p, 2, D_T + k)
        p.fop(1, 1, "-", 2)
        _k(p, 3, 1, "*", R16)
        p.fop(3, 3, "+", 2)
        _sv(p, S_CTL + k, 3)
        _k(p, 1, 1, "*", A16)
        p.fop(4 + k, 1, "+", 2)                  # F4..F8: CPL TOPO CHR DRF TONE, the means
    _k(p, 4, 4, "*", 2.0 ** 30)                  # COUPLE: a quarter turn at 1
    p.fconst(12, 1.0)
    p.fop(1, 12, "-", 5)
    p.fconst(12, 0.0)
    p.fop(1, 1, "MAX", 12)                       # k1 = max(1 - t, 0)
    p.fconst(12, 1.0)
    p.fop(2, 5, "MIN", 12)                       # k2 = min(t, 1)
    p.fop(3, 5, "-", 12)
    p.fconst(12, 0.0)
    p.fop(3, 3, "MAX", 12)                       # k3 = max(t - 1, 0)
    _sv(p, D_C1, 4)
    p.fop(1, 1, "*", 4)
    _sv(p, D_CA0, 1)
    _sv(p, D_CA2, 1)
    p.fop(3, 3, "*", 4)
    _sv(p, D_CB0, 3)
    p.fop(2, 2, "*", 4)
    _sv(p, D_CB2, 2)
    _k(p, 6, 6, "*", 0.5)                        # CHAR: y (1 + h - h y^2), h = chr / 2
    _sv(p, D_H, 6)
    _k(p, 6, 6, "+", 1.0)
    _sv(p, D_H1, 6)
    _k(p, 8, 8, "*", 30236.0 / 32768.0)          # TONE's one-pole: (128 + tone x 30236) / 2^15
    _k(p, 8, 8, "+", 128.0 / 32768.0)
    _sv(p, D_G1, 8)


def _half_steps(p: Prog, L: C.Layout) -> None:
    """The increments' followers a half on; each generator's step (its mean increment, the
    drift's triangle) for both ears (-+ BEAT / 2); the drift phases 16 samples on.
    In: F7 DRIFT's mean. Clobbers R0-R3, R7, R9, R10, R12, R13, I1."""
    _ld(p, 0, S_BI)
    p.lsh(9, 0, -1)                              # bi >> 1
    _k(p, 10, 7, "*", 9.0 * 32768.0 / 32.0)
    _k(p, 10, 10, "+", 1461.0)                   # the drift's rate
    _k(p, 7, 7, "*", 1.0 / 256.0)
    _base(p, L, 0, 0)
    p.seti(1, 0)

    def gen():                                   # I1: generator g's words
        p.ldi(1, S_INC, 1)
        p.ldi(2, D_FQ, 1)
        p.fop(1, 1, "-", 2)
        _k(p, 3, 1, "*", R16)
        p.fop(3, 3, "+", 2)
        p.sti(S_INC, 1, 3)
        _k(p, 1, 1, "*", A16)
        p.fop(1, 1, "+", 2)                      # the mean increment
        p.ldi(0, S_DPH, 1)
        p.iconst(12, -32)
        p.float_(2, 0, 12)
        p.fconst(12, 0.0)
        p.fop(3, 12, "-", 2)
        p.fop(2, 2, "MAX", 3)
        _k(p, 2, 2, "*", 4.0)
        _k(p, 2, 2, "+", -1.0)                   # the triangle, -1..1
        p.fop(2, 2, "*", 7)
        _k(p, 3, 1, "*", 65536.0)                # Optimist's inc >> 16 (its whole 2^-16 turns)
        p.trunc(3, 3)
        p.iconst(12, -16)
        p.float_(3, 3, 12)
        p.fop(2, 2, "*", 3)
        p.fop(1, 1, "+", 2)
        p.fconst(12, 0.0)
        p.fop(1, 1, "MAX", 12)
        _k(p, 1, 1, "MIN", MAXINC)
        _k(p, 1, 1, "*", 2.0 ** 32)
        p.trunc(1, 1)
        p.iop(2, 1, "-", 9)
        p.sti(E_ST, 1, 2)
        p.ipass(13, 9)
        p.iop(2, 13, "+", 1)
        p.sti(EAR + E_ST, 1, 2)
        p.ldi(2, K_DR, 1)                        # 16 x trunc(rate (8 + g) / 8)
        p.fop(2, 2, "*", 10)
        p.trunc(2, 2)
        p.lsh(2, 2, 4)
        p.ipass(13, 0)
        p.iop(0, 13, "+", 2)
        p.sti(S_DPH, 1, 0)
        p.ldpost(3, 1)
    p.loop(L.W["n5"], 4, gen)


# the generators' sources: (gen, ((prev index, coefficient word), ...))
SRC = ((0, ((1, D_CA0), (3, D_CB0))), (1, ((0, D_C1),)), (2, ((3, D_CA2), (1, D_CB2))),
       (3, ((2, D_C1),)))


EAR_SCHED = True                                 # (perf, 2026-11-12) _ear_sched; False = _ear_body as before
I0_AT = 75                                       # I0 = the slot's word I0_AT while a half runs (_half_i0)
T_O = 86                                         # the four generators' outputs until they become E_PREV
K_ONE, K_Q0 = 90, 91                             # 1.0 and SIN_Q[0] (_half_i0)


def _half_i0(p: Prog) -> None:
    """I0 = the slot's word I0_AT (D_CA0 .. D_G1 and T_O within its -32..31); K_ONE, K_Q0. Clobbers R8, R9."""
    p.geti(8, 3)
    p.iconst(9, p.ioff(3, 4 * (C.K.S0 + I0_AT)))
    p.iop(8, 8, "+", 9)
    p.seti(0, 8, "I0 = the slot's word I0_AT")
    for k, x in ((K_ONE, 1.0), (K_Q0, SIN_Q[0])):
        p.fconst(8, x)
        p.sti(k - I0_AT, 0, 8)


def _ear_sched(p: Prog) -> None:
    """_ear_body's operations, the same ones on the same operands (so bit for bit its result), scheduled
    (dnfw.mnm.sched): the generators in two register sets, so one's loads and integer steps ride on the other's
    computes; the slot's words through I0 (_half_i0), the sine's first coefficient and 1.0 from slot words too
    (K_ONE, K_Q0), each generator's output in T_O until all four have read the previous ones; its phase step
    moved up (it reads nothing the sine writes). The soft knee as before."""
    from ...mnm.sched import Sched
    s = Sched()
    o = lambda k: k - I0_AT                      # noqa: E731
    s.const(7, 0.0)
    s.const(12, SIN_Q[1])
    s.const(13, SIN_Q[2])
    s.const(14, SIN_Q[3])
    s.raw(lambda q: q.iconst(9, -31), (), (9,))
    for g, srcs in SRC:
        a, b, c, d, ph = (0, 1, 2, 3, 8) if g % 2 == 0 else (4, 5, 6, 10, 11)
        for j, (src, w) in enumerate(srcs):
            x, k = (a, b) if j == 0 else (c, d)
            s.ld(x, E_PREV + src, 1)
            s.ld(k, o(w), 0)
            s.mul(x, x, k)
        if len(srcs) > 1:
            s.add(a, a, c)
        s.raw(lambda q, a=a: q.trunc(a, a), (a,), (a,))
        s.ld(ph, E_PH + g, 1)
        s.raw(lambda q, a=a, ph=ph: q.iop(a, ph, "+", a), (ph, a), (a,))
        s.raw(lambda q, a=a: q.float_(a, a, 9), (a, 9), (a,))     # s = 2 x phase, -1..1
        s.ld(b, E_ST + g, 1)
        s.raw(lambda q, b=b, ph=ph: q.iop(ph, ph, "+", b), (ph, b), (ph,))
        s.st(E_PH + g, 1, ph)
        s.mul(b, a, a)                           # sin(pi s) = s (1 - s^2) Q(s^2)
        s.ld(d, o(K_ONE), 0)
        s.sub(d, d, b)
        s.ld(c, o(K_Q0), 0)
        s.mul(c, c, b)
        s.add(c, c, 12)
        s.mul(c, c, b)
        s.add(c, c, 13)
        s.mul(c, c, b)
        s.add(c, c, 14)
        s.mul(c, c, d)
        s.mul(c, c, a)                           # y
        s.mul(b, c, c)                           # CHAR: y (1 + h - h y^2)
        s.ld(d, o(D_H), 0)
        s.mul(b, b, d)
        s.ld(a, o(D_H1), 0)
        s.sub(a, a, b)
        s.mul(a, c, a)
        s.st(o(T_O + g), 0, a)
        s.add(7, 7, a)
    for g in range(4):
        s.ld(2 + (g & 1), o(T_O + g), 0)
        s.st(E_PREV + g, 1, 2 + (g & 1))
    s.const(12, 0.25)
    s.mul(7, 7, 12)                              # the mean
    s.ld(0, E_DCI, 1)                            # the DC block: x - x1 + y1 (1 - 2^-9)
    s.st(E_DCI, 1, 7)
    s.sub(1, 7, 0)
    s.ld(2, E_DCO, 1)
    s.const(13, 1.0 - 2.0 ** -9)
    s.mul(2, 2, 13)
    s.add(1, 1, 2)
    s.const(14, 2.0 ** -16)
    s.add(1, 1, 14)                              # Optimist's floored dco >> 9: +1/2 LSB a sample
    s.st(E_DCO, 1, 1)
    s.ld(0, E_LOW, 1)                            # TONE's one-pole
    s.sub(1, 1, 0)
    s.ld(2, o(D_G1), 0)
    s.mul(1, 1, 2)
    s.add(0, 0, 1)
    s.const(15, -(2.0 ** -16))
    s.add(0, 0, 15)                              # its floored product: -1/2 LSB a sample
    s.st(E_LOW, 1, 0)
    s.emit(p)
    p.fconst(12, 0.0)                            # soft_knee(x, 16000)
    p.fop(1, 12, "-", 0)
    p.fop(1, 1, "MAX", 0)
    p.fconst(12, KNEE)
    p.if_(1, "GT", 12, lambda: _knee(p))
    p.sti(E_Y, 1, 0)


def _ear_body(p: Prog) -> None:
    """One ear, one sample (drone_ear), the ear's words at I1: E_Y = its output."""
    if EAR_SCHED:
        _ear_sched(p)
        return
    p.fconst(7, 0.0)
    for g, srcs in SRC:
        for j, (s, w) in enumerate(srcs):
            p.ldi(2 * j, E_PREV + s, 1)
            _ld(p, 2 * j + 1, w)
            p.fop(2 * j, 2 * j, "*", 2 * j + 1)
        if len(srcs) > 1:
            p.fop(0, 0, "+", 2)
        p.trunc(0, 0)                            # the phase offset, 2^30 a quarter turn
        p.ldi(13, E_PH + g, 1)
        p.iop(0, 13, "+", 0)
        p.iconst(1, -31)
        p.float_(0, 0, 1)                        # s = 2 x phase, -1..1
        p.fop(2, 0, "*", 0)                      # sin(pi s) = s (1 - s^2) Q(s^2)
        p.fconst(3, 1.0)
        p.fop(3, 3, "-", 2)
        p.fconst(4, SIN_Q[0])
        for c in SIN_Q[1:]:
            p.fop(4, 4, "*", 2)
            _k(p, 4, 4, "+", c)
        p.fop(4, 4, "*", 3)
        p.fop(4, 4, "*", 0)                      # y
        p.fop(2, 4, "*", 4)                      # CHAR: y (1 + h - h y^2)
        _ld(p, 3, D_H)
        p.fop(2, 2, "*", 3)
        _ld(p, 5, D_H1)
        p.fop(5, 5, "-", 2)
        p.fop(8 + g, 4, "*", 5)
        p.fop(7, 7, "+", 8 + g)
        p.ldi(14, E_ST + g, 1)
        p.iop(13, 13, "+", 14)
        p.sti(E_PH + g, 1, 13)
    for g in range(4):
        p.sti(E_PREV + g, 1, 8 + g)
    _k(p, 7, 7, "*", 0.25)                       # the mean
    p.ldi(0, E_DCI, 1)                           # the DC block: x - x1 + y1 (1 - 2^-9)
    p.sti(E_DCI, 1, 7)
    p.fop(1, 7, "-", 0)
    p.ldi(2, E_DCO, 1)
    _k(p, 2, 2, "*", 1.0 - 2.0 ** -9)
    p.fop(1, 1, "+", 2)
    _k(p, 1, 1, "+", 2.0 ** -16)                 # Optimist's floored dco >> 9: +1/2 LSB a sample
    p.sti(E_DCO, 1, 1)
    p.ldi(0, E_LOW, 1)                           # TONE's one-pole
    p.fop(1, 1, "-", 0)
    _ld(p, 2, D_G1)
    p.fop(1, 1, "*", 2)
    p.fop(0, 0, "+", 1)
    _k(p, 0, 0, "+", -(2.0 ** -16))              # its floored product: -1/2 LSB a sample
    p.sti(E_LOW, 1, 0)
    p.fconst(12, 0.0)                            # soft_knee(x, 16000)
    p.fop(1, 12, "-", 0)
    p.fop(1, 1, "MAX", 0)
    p.fconst(12, KNEE)
    p.if_(1, "GT", 12, lambda: _knee(p))
    p.sti(E_Y, 1, 0)


def _knee(p: Prog) -> None:
    """F0 = sign(x) (k + tanh(min(2 (|x| - k), 2)) / 2): F0 x, F1 |x|."""
    from ...perc import machines as PM
    p.fpass(8, 0)
    _k(p, 3, 1, "+", -KNEE)
    p.fop(3, 3, "+", 3)
    _k(p, 3, 3, "MIN", 2.0)
    _k(p, 3, 3, "*", 2.0 / math.log(2.0))
    _exp2p(p, 2, 3)                              # e^(2v)
    _k(p, 2, 2, "+", 1.0)
    PM._recip_inline(p, 4, 2, 5)
    _k(p, 4, 4, "*", -32767.0 / 32768.0)         # tanh x 32767 / 32768, halved, + k
    _k(p, 4, 4, "+", 0.5 * 32767.0 / 32768.0 + KNEE)
    p.fconst(12, 0.0)
    p.fop(0, 12, "-", 4)
    p.if_(8, "GT", 12, lambda: p.fpass(0, 4))


def _ear(p: Prog, word: int) -> None:
    """The ear whose base is in slot word WORD, one sample."""
    _ld(p, 0, word)
    p.seti(1, 0)
    p.call("drone_ear", lambda: _ear_body(p))


def half(p: Prog, L: C.Layout) -> None:
    """16 samples at I4 (and, BEAT on, 16 side samples)."""
    if EAR_SCHED:
        _half_i0(p)
    _half_ctl(p)
    _half_steps(p, L)
    _base(p, L, 0, 0)
    _sv(p, T_E0, 0)
    _base(p, L, 0, EAR)
    _sv(p, T_E1, 0)
    _ld(p, 0, S_BI)

    def mono():
        def one():
            _ear(p, T_E0)
            p.ldi(0, E_Y, 1)
            p.fop(0, 0, "+", 0)
            p.stpost(4, 0)
        p.loop(L.W["n4"], 16, one)

    def beat():
        _side_base(p, L, 0)
        p.ld(1, L.W["half"])
        p.lsh(1, 1, 6)
        p.ipass(12, 1)
        p.iop(0, 12, "+", 0)
        p.seti(5, 0)
        p.fconst(0, 0.0)
        _sv(p, D_ABS, 0)

        def two():
            _ear(p, T_E0)
            p.ldi(0, E_Y, 1)
            p.st(L.W["tmp2"], 0)
            _ear(p, T_E1)
            p.ldi(0, E_Y, 1)
            p.ld(6, L.W["tmp2"])
            p.fop(1, 6, "+", 0)                  # mid
            p.fop(2, 6, "-", 0)                  # side
            p.stpost(4, 1)
            p.stpost(5, 2)
            p.fconst(12, 0.0)
            p.fop(2, 12, "-", 1)
            p.fop(1, 1, "MAX", 2)
            _ld(p, 2, D_ABS)
            p.fop(2, 2, "+", 1)
            _sv(p, D_ABS, 2)
        p.loop(L.W["n4"], 16, two)
        _side_base(p, L, 0)
        p.seti(5, 0)
        p.ldi(1, 32, 5)
        _ld(p, 2, D_ABS)
        p.fop(1, 1, "+", 2)
        p.sti(32, 5, 1)
    p.ifz(0, "EQ", mono, beat)
