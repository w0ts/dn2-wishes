"""The Monomachine machines as PERC's voice runs them (dnfw.md.voice): the four steps every
machine there has (host, init, trig, render), around each machine module's own
(docs/mnm.md).

- host: the eight 14-bit inputs (knob << 7) -> W[1..8], each knob / 128 (the Monomachine's
  parameter word, knob << 16, as a Q23 fraction);
- render: the machine's own pitch (`pitch`, from VW pitch), then two of its 16-frame blocks
  into the stream at OUT0.

Removed (2026-11-08, the User, to make room for PLAITS and the 303): the five machines ported
from the Monomachine's own DSP code, SID 6581, DPRO-WAVE, DPRO-DDRW, DPRO-DENS and VO-6, with
their tables, the Digibank stand-in and the Monomachine kernel's pitch words (F, A, pre) only
they read. Their machine types stay RESERVED (never reused): the DSP's lookup makes a track on
one the MIDI machine's slot (nothing renders it: a stock MIDI track, bit for bit) and its page
is empty.
"""

from __future__ import annotations

from . import core as C
from . import plaits, sophie, tb303
from ..md import core as K
from ..perc.dsl import Prog

MODULES = (sophie, plaits, tb303)        # their types: TYPES below (20, 18, 19)
F_TOP = 0x5800


def _host(p: Prog, L: K.Layout) -> None:
    for k in range(8):
        K.inp(p, 0, k)
        p.lsh(0, 0, -7)
        p.iconst(12, -7)
        p.float_(0, 0, 12)
        K.ws(p, C.P0 + k, 0)


# v0.56 (owner, 2026-11-15: "time in ddrw is not working ... BR1 and BR2 controls are 99%
# inaudible"; docs/ddrw-fix.md). The Monomachine's DDRW model (ddrw.py) and its references are
# untouched: the DN2's host maps its knobs on the way in.
DDRW_BR = (4, 6)                    # BR1, BR2
DDRW_FADE = 6000.0 / (127 * 127)    # TIME 127: the fade over about 6,000 half-renders (2 s)
DDRW_RATE = 0x21D10 / 2.0 ** 23 * 2048.0   # ddrw._half's fade rate a half-render at g = 1, x (TIME + 1)


def _host_ddrw(p: Prog, L: K.Layout) -> None:
    """BR 1..127 -> the table's 64..127 (9 bits down to 3: the whole turn heard; 0 stays clean,
    the Monomachine's 15 bits); TIME -> the glide word g = (TIME + 1) / (RATE (1 + c TIME^2)), so
    the fade lasts 1 + c TIME^2 half-renders (TIME 16: ~30 ms, 64: ~0.5 s, 127: ~2 s), and 0 is
    the model's own instant change. Clobbers R0-R3, R12-R15, I12."""
    from ..perc import machines as PM
    for k in range(8):
        K.inp(p, 0, k)
        p.lsh(0, 0, -7)                         # 0..127
        if k in DDRW_BR:
            p.lsh(1, 0, 6)
            p.iop(1, 1, "-", 0)                 # 63 x
            p.iconst(12, 63)
            p.iop(1, 12, "+", 1)
            p.lsh(1, 1, -7)                     # (63 x + 63) >> 7: 0..63
            p.iconst(12, 64)
            p.iop(1, 12, "+", 1)
            p.ifz(0, "NE", lambda: p.ipass(0, 1))
        p.iconst(12, -7)
        p.float_(0, 0, 12)
        K.ws(p, C.P0 + k, 0)
    W = L.mnm.W
    K.inp(p, 0, 3)
    p.lsh(0, 0, -7)                             # TIME
    p.iconst(12, 0)
    p.float_(1, 0, 12)                          # t
    p.fop(2, 1, "*", 1)
    p.fconst(12, DDRW_FADE)
    p.fop(2, 2, "*", 12)
    p.fconst(12, 1.0)
    p.fop(2, 2, "+", 12)                        # 1 + c t^2
    p.fconst(12, DDRW_RATE)
    p.fop(2, 2, "*", 12)
    PM.recip(p, 3, 2)
    p.fconst(12, 1.0)
    p.fop(1, 1, "+", 12)                        # t + 1
    p.fop(3, 3, "*", 1)                         # g
    p.fconst(12, 0.0)
    p.ifz(0, "EQ", lambda: p.fpass(3, 12))      # TIME 0: the model's own (g unused there)
    p.st(W["gl"], 3)


def _render(M):
    def render(p: Prog, L: K.Layout) -> None:
        mL = L.mnm
        # I4 is the caller's (the slot's output: dnfw.md.voice.advance keeps I3, I4); the
        # halves below walk their own (v0.26 WIP wrote the voice's output over its words)
        p.e("R0 = I4;")
        if p.run:
            p.r[0] = p.i[4]
        p.st(mL.W["i4s"], 0)
        M.pitch(p, mL)
        p.iconst(0, 0)
        p.st(mL.W["half"], 0)

        def one():
            p.ld(1, L.C["mdb"])
            p.iconst(12, 4 * K.OUT0)
            p.iop(1, 12, "+", 1)
            p.ld(2, mL.W["half"])
            p.lsh(2, 2, 6)                      # 16 floats a half
            p.ipass(12, 1)
            p.iop(1, 12, "+", 2)
            p.seti(4, 1)
            M.half(p, mL)
            p.ld(2, mL.W["half"])
            p.ipass(12, 2)
            p.iconst(13, 1)
            p.iop(2, 12, "+", 13)
            p.st(mL.W["half"], 2)
        p.loop(mL.W["tmp"], 2, one)
        p.ld(0, mL.W["i4s"])
        p.seti(4, 0)
    return render


def _adapter(M):
    return type(M.NAME.replace(" ", "").replace("-", ""), (), {
        "NAME": M.NAME, "ID": M.ID, "PNAMES": M.PNAMES, "MNM": M,
        "host": staticmethod(_host_ddrw if M is ddrw else _host),
        "init": staticmethod(lambda p, L, M=M: M.init(p, L.mnm)),
        "trig": staticmethod(lambda p, L, M=M: M.trig(p, L.mnm)),
        "render": staticmethod(_render(M)),
    })


MACHINES = tuple(_adapter(M) for M in MODULES)
NAMES = tuple(M.NAME for M in MACHINES)
DEFAULTS = {M.NAME: M.DEFAULTS for M in MODULES}

# each machine its own machine type (MACHINE SEL entry), in MODULES order. One table for the
# ColdFire (dnfw.waverider.coldfire, pages), the DSP's lookup (dnfw.waverider.dsp) and PERC's
# voice (dnfw.perc.program).
# v0.45 (2026-11-09, the User: keep upstream dn2mk2's numbers): BOUNCE is upstream's type 17, so
# SOPHIE moved 17 -> 20; PLAITS and TB303 keep 18 and 19
TYPE_SLOTS = (20, 18, 19)                 # 20: SOPHIE (docs/sophie.md), 18: PLAITS (docs/plaits.md), 19: TB303 (docs/tb303.md)
TYPES = TYPE_SLOTS[:len(MACHINES)]
# the removed machines' types (2026-11-08): reserved, never reused, so every other machine keeps
# its number and a project's track on one stays on it (silent, its page empty)
RESERVED = {6: "SID 6581", 7: "DPRO-WAVE", 14: "DPRO-DDRW", 15: "DPRO-DENS", 16: "VO-6"}
assert not set(RESERVED) & set(TYPES)
from ..sampler import machines as _smp  # noqa: E402
assert not set(_smp.TYPES) & (set(TYPES) | set(RESERVED)), "a machine type of ours is a sample machine's (v0.44 BOUNCE: 17)"
# MACHINE SEL's names (long, short), as the DN2 lists its own
LIST_NAMES = {"SOPHIE": ("Sophie", "SOP"), "PLAITS": ("Plaits", "PLT"), "TB303": ("TB-303", "303")}
REMOVED_NAMES = ("Removed", "---")       # a reserved type's name (MACHINE SEL never lists it)


class Removed:
    """A reserved type's place in the ColdFire's tables (no DSP code): eight unused controls."""
    NAME, PNAMES, DEFAULTS = "REMOVED", ("---",) * 8, (0,) * 8


# the ColdFire's Monomachine places, one per type 6, 7, 14.. in type order (its page code turns a
# type into this index by arithmetic: dnfw.waverider.pages is_wr): the live machines and the
# reserved types' placeholders
CF_TYPES = tuple(sorted(set(TYPES) | set(RESERVED)))
CF_MACHINES = tuple(MACHINES[TYPES.index(t)] if t in TYPES else Removed for t in CF_TYPES)
CF_LIST_NAMES = tuple(LIST_NAMES[M.NAME] if M is not Removed else REMOVED_NAMES for M in CF_MACHINES)
CF_DEFAULTS = tuple(DEFAULTS.get(M.NAME, Removed.DEFAULTS) for M in CF_MACHINES)
