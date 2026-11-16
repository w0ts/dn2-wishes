# SPDX-License-Identifier: AGPL-3.0-or-later
"""ANALOG 2's mono legato glide (page 3: GLID, GLTY), DRONE's (dnfw.engines.drone.drone) on ANALOG 2's own words.

2026-11-11, the User: ANALOG 2 gets DRONE's glide. GLID (r0, record LEV2) is Optimist's TIME_MS index, q x 127:
1 ms .. 10 s, 0 off. GLTY (r1, record TYPE, 0..2) is OFF, RATE (GLID the time an octave takes) or TIME (GLID the
time of any glide). OFF is TYPE's stock default, so a track saved before this page has its glide off.

Legato as DRONE's: a note glides only when its trig comes while the slot's gate is still open (no note-off since
the last note: a key still down or an overlapping trig); a separate note jumps. The glide is Optimist's voice.c
(glide_set and its per-block step, in 1/4096 semitone; not truncated, below). Only the oscillators glide: KTR keys
the filter from the note itself (Optimist's eng_analog2.c: v->pitch16), and VW pitch's moves between trigs pass
straight through. With the glide off, the pitch is VW pitch exactly, every block.

GLID's time (2026-11-11, the User: "drone glide should go to minutes", top 5 minutes; DRONE's too): q 0..0.75 is
Optimist's TIME_MS curve, 10^(4 q) ms (1 ms .. 1 s, unchanged), q 0.75..1 climbs from 1 s to 5 min (`ms_of`).
voice.c's step is a whole number of 1/4096 semitones a block, at least one: that caps a glide at ~3 s a semitone and
makes a 2.5-unit glide 25 % slow. Here the step is not truncated, so a glide of any length takes its time.

A note that glides does not restart the phases (DRFT 0's restart): Optimist's LEGATO plays it on the sounding
voice (voice.c mono_play, retrig 0).
"""

from __future__ import annotations

import math

from ...mnm import core as C
from ..tb303.tb303 import _exp2p
from ...perc.dsl import Prog

SR = 44100.0
NOTE_OFF_WORD = 0x25C4B0                         # frame +36 (low half): the note-off mask, bit slot (drone.py)
GLID, GLTY = 0, 1                                # page 3's controls (core.page3)
OFF, RATE, TIME = range(3)
TOP_MS = 300_000.0                               # GLID's top: 5 minutes (the User, 2026-11-11)
KNEE = 0.75                                      # below it Optimist's 10^(4 q) ms (1 s at the knee)
UPPER = math.log10(TOP_MS / 1000.0) / (1.0 - KNEE)   # log10(ms) a unit of q above the knee


def ms_of(q: float) -> float:
    """GLID's time in ms for q 0..1 (0: off)"""
    if q <= 0.0:
        return 0.0
    return 10.0 ** (4.0 * q) if q <= KNEE else 1000.0 * 10.0 ** (UPPER * (q - KNEE))


def curve_x(p: Prog, d: int, a: int) -> None:
    """Fd = log10(ms_of(Fa)): 4 Fa + (UPPER - 4) max(0, Fa - KNEE). Clobbers R12, R13."""
    _k(p, d, a, "*", 4.0)
    _k(p, 13, a, "-", KNEE)
    p.fconst(12, 0.0)
    p.fop(13, 13, "MAX", 12)
    _k(p, 13, 13, "*", UPPER - 4.0)
    p.fop(d, d, "+", 13)


def step_semis(p: Prog) -> None:
    """F3: a step in 1/4096 semitone (float, >= 0) -> semitones, not truncated (voice.c truncates it to a whole
    unit, at least one). Clobbers R12."""
    _k(p, 3, 3, "*", 2.0 ** -12)


class Words:
    """ANALOG 2's slot words for the glide: CUR the oscillators' pitch (semitones), GST the step (semitones a
    block, 0 none), TGT the last block's VW pitch, TRG the pending trig (2, 1, 0), GATE the slot's gate, LEG
    whether this note began legato."""

    def __init__(self, base: int):
        (self.CUR, self.GST, self.TGT, self.TRG, self.GATE, self.LEG) = range(base, base + 6)
        self.END = base + 6


def _k(p: Prog, d: int, a: int, op: str, x: float) -> None:
    p.fconst(12, x)
    p.fop(d, a, op, 12)


def _glty(p: Prog, L: C.Layout, d: int) -> None:
    """Rd = GLTY's choice: min(2, trunc(3 q)). Clobbers R12."""
    C.page3(p, L, d, GLTY)
    _k(p, d, d, "*", 3.0)
    p.trunc(d, d)
    p.iconst(12, TIME)
    p.iop(d, d, "MIN", 12)


def _on(p: Prog, L: C.Layout, d: int) -> None:
    """Rd = 1 when the glide is on (GLTY not OFF and GLID > 0), else 0. Clobbers R12, R13."""
    _glty(p, L, d)
    C.page3(p, L, 13, GLID)
    p.fconst(12, 0.0)
    p.if_(13, "LE", 12, lambda: p.iconst(d, 0))
    p.iconst(12, 1)
    p.iop(d, d, "MIN", 12)


def trig(p: Prog, L: C.Layout, W: Words) -> None:
    """At a trig: TRG 2 (acted on at the second `pitch` after it: the note's pitch word lags the trig by a call),
    LEG = the gate still open, the gate open. Leaves R0 = 1 when this note glides (legato, the glide on)."""
    p.iconst(0, 2)
    C.sts(p, W.TRG, 0)
    C.st(p, 0, W.GATE)
    C.sts(p, W.LEG, 0)
    p.iconst(1, 1)
    C.sts(p, W.GATE, 1)
    p.ifz(0, "NE", lambda: _on(p, L, 0))


def _exp2(p: Prog, d: int, x: int) -> None:
    """Fd = 2^Fx, tb303's precise exp2 as one subroutine. Clobbers R0, R1, R12, R14, R15, I12."""
    p.fpass(15, x)
    p.call("a2_exp2", lambda: (_exp2p(p, 14, 15), p.fpass(15, 14)))
    p.fpass(d, 15)


def _start(p: Prog, L: C.Layout, W: Words) -> None:
    """GST: voice.c glide_set's step (1/4096 semitone a block, as semitones) for GLID's time ms_of(q):
    TIME |d| / trunc(ms FS / 1000 / 32), RATE ENV_LIN x 3 / 1024, neither truncated (step_semis). In: F2 GLID (> 0)."""
    curve_x(p, 3, 2)
    _k(p, 3, 3, "*", -math.log2(10.0))
    _exp2(p, 4, 3)                               # 1 / ms
    _k(p, 4, 4, "*", float(1 << 24) * 32.0 * 1000.0 / SR)
    p.trunc(5, 4)                                # ENV_LIN
    _glty(p, L, 6)

    def time_():
        C.vw(p, 1, "pitch")                      # the target
        p.iconst(12, 0)
        p.float_(4, 5, 12)
        from ...perc import machines as PM
        PM._recip_inline(p, 6, 4, 7)
        _k(p, 6, 6, "*", float(1 << 24) * (1.0 + 2e-7))
        p.trunc(5, 6)                            # ticks
        p.iconst(12, 0)
        p.float_(4, 5, 12)
        PM._recip_inline(p, 6, 4, 7)             # 1 / ticks
        C.st(p, 3, W.CUR)
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
    p.iconst(12, TIME)
    p.if_(6, "EQ", 12, time_, rate, kind="i")
    step_semis(p)
    C.sts(p, W.GST, 3)


def _gate_off(p: Prog, L: C.Layout, W: Words) -> None:
    """GATE 0 when this block's frame carries the slot's note-off (+36 bit slot: the key-up or the trig's end)"""
    from ...perc import program as PP
    p.ld(0, NOTE_OFF_WORD)
    p.iconst(12, 0xFFFF)
    p.iop(0, 0, "AND", 12)
    p.iconst(1, 1)
    p.ld(9, L.perc.C["t"])
    PP._shift_by(p, 1, 9)
    p.iop(0, 0, "AND", 1)
    p.ifz(0, "NE", lambda: (p.iconst(1, 0), C.sts(p, W.GATE, 1)))


def pitch(p: Prog, L: C.Layout, W: Words) -> None:
    """Once a block, before the increments: CUR (semitones) from VW pitch. A trig jumps to it or starts a glide;
    otherwise its moves pass straight through; the glide steps once a block (voice.c). Clobbers R0-R7, R9,
    R12-R15, I12."""
    _gate_off(p, L, W)
    C.vw(p, 1, "pitch")
    C.st(p, 0, W.TRG)

    def on_trig():
        p.iconst(0, 0)
        C.sts(p, W.TRG, 0)

        def jump():
            C.sts(p, W.CUR, 1)                   # (F1: VW pitch; _on keeps it)
            p.fconst(3, 0.0)
            C.sts(p, W.GST, 3)

        def glide():
            C.page3(p, L, 2, GLID)
            _start(p, L, W)
        C.st(p, 0, W.LEG)
        p.ifz(0, "NE", lambda: (_on(p, L, 0), p.ifz(0, "NE", glide, jump)), jump)

    def follow():                                # CUR += T - last T
        C.st(p, 2, W.TGT)
        p.fop(2, 1, "-", 2)
        C.st(p, 3, W.CUR)
        p.fop(3, 3, "+", 2)
        C.sts(p, W.CUR, 3)

    def pending():
        p.iconst(12, 1)
        p.if_(0, "EQ", 12, on_trig, lambda: (p.iconst(0, 1), C.sts(p, W.TRG, 0), follow()), kind="i")
    p.ifz(0, "NE", pending, follow)
    C.vw(p, 1, "pitch")                          # (the glide's set-up clobbers F1)
    C.sts(p, W.TGT, 1)
    C.st(p, 2, W.CUR)                            # one step towards T (GST 0: there)
    C.st(p, 3, W.GST)
    p.fop(4, 1, "-", 2)
    p.fconst(12, 0.0)
    p.fop(5, 12, "-", 3)
    p.if_(3, "EQ", 12, lambda: p.fpass(2, 1),
          lambda: (p.fop(4, 4, "MIN", 3), p.fop(4, 4, "MAX", 5), p.fop(2, 2, "+", 4)))
    C.sts(p, W.CUR, 2)
