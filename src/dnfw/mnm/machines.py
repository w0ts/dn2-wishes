"""The Monomachine machines as PERC's voice runs them (dnfw.md.voice): the four steps every
machine there has (host, init, trig, render), around each machine module's own
(docs/mnm.md).

- host: the eight 14-bit inputs (knob << 7) -> W[1..8], each knob / 128 (the Monomachine's
  parameter word, knob << 16, as a Q23 fraction);
- render: the machine's own pitch (`pitch`, from VW pitch), then two of its 16-frame blocks
  into the stream at OUT0.

The five machines ported from the Monomachine's own DSP code (SID 6581, DPRO-WAVE, DPRO-DDRW,
DPRO-DENS, VO-6; types 6, 7, 14, 15, 16) were removed on 2026-11-08 to make room for PLAITS and
the 303, and came back on 2026-11-11 (the User: LZMA gave the USB image room). They render after
the Monomachine kernel's pitch words (`_pitch`, theirs only):

F = note x 2048 / 12 + TUNE x 683 / 128 (TUNE 64: in tune), 0..0x5800; A = 2^(F / 2048) x
0x1D22A / 2^14 (the kernel's exp table and scaling, in float); pre, the previous slot's F
(PRCH, MSRC). Their tables come from the User's Monomachine OS (dnfw.mnm.tables, dnfw.mnm.rom).
"""

from __future__ import annotations

from . import core as C
from . import analog2, ddrw, dens, drone, plaits, sid, sophie, tb303, vo6, wave
from ..md import core as K
from ..perc.dsl import Prog
from ..builder import selection as _sel

# in the order of PERC's machine index (dnfw.perc.program MNM_TYPES): the Monomachine's own five
# after the others (2026-11-11), so every machine already here keeps its index
ALL_MODULES = (sophie, plaits, tb303, drone, analog2, sid, wave, ddrw, dens, vo6)
# their types: ALL_TYPE_SLOTS below (20, 18, 19, 21, 22, 6, 7, 14, 15, 16)
# the builder (docs/builder.md): a machine left out of this build is emitted nowhere and its type
# is RESERVED below
PART = {"SOPHIE": "MNM_SOPHIE", "PLAITS": "MNM_PLAITS", "TB303": "MNM_TB303", "DRONE": "MNM_DRONE",
        "ANALOG2": "MNM_ANALOG2",
        "SID 6581": "MNM_SID", "DPRO-WAVE": "MNM_DPRO_WAVE", "DPRO-DDRW": "MNM_DPRO_DDRW",
        "DPRO-DENS": "MNM_DPRO_DENS", "VO-6": "MNM_VO6"}
MODULES = tuple(M for M in ALL_MODULES if _sel.on(PART[M.NAME]))
# the Monomachine's own machines (the kernel's pitch words F, A, pre: `_pitch`)
MNM_OS_NAMES = ("SID 6581", "DPRO-WAVE", "DPRO-DDRW", "DPRO-DENS", "VO-6")
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


# v0.26: semitones added to the DN2's note, so each machine's note 60 is 261.6 Hz as the
# DN2's own: on the Monomachine, for the same pitch, DPRO-WAVE sounds an octave under SID,
# DDRW, DENS and VO-6
TRANSPOSE = {"DPRO-WAVE": 12}


def _pitch(p: Prog, L: K.Layout, transpose: int = 0) -> None:
    """VW F, A and pre from VW pitch and TUNE (the Monomachine kernel's, for its own machines:
    28eb110's parent, unchanged). Clobbers R0-R3, R12-R15, I1, I12."""
    from ..perc import machines as PM
    C.vw(p, 1, "pitch")
    if transpose:
        p.fconst(12, float(transpose))
        p.fop(1, 1, "+", 12)
    p.fconst(12, 2048.0 / 12.0)
    p.fop(1, 1, "*", 12)
    C.knob(p, 2, 7)
    p.iconst(12, 0)
    p.float_(2, 2, 12)
    p.fconst(12, 683.0 / 128.0)
    p.fop(2, 2, "*", 12)
    p.trunc(2, 2)
    p.iconst(12, 0)
    p.float_(2, 2, 12)
    p.fop(1, 1, "+", 2)
    p.fconst(12, 0.0)
    p.fop(1, 1, "MAX", 12)
    p.fconst(12, float(F_TOP))
    p.fop(1, 1, "MIN", 12)
    p.trunc(1, 1)
    C.vws(p, "F", 1)
    p.iconst(12, 0)
    p.float_(1, 1, 12)
    p.fconst(12, 1.0 / 2048.0)
    p.fop(1, 1, "*", 12)
    PM.exp2(p, L.mnm.perc, 1, 1)
    p.fconst(12, 0x1D22A / 2.0 ** 14)
    p.fop(1, 1, "*", 12)
    C.vws(p, "A", 1)
    # the previous slot's F (slot 15's for slot 0): PRCH, MSRC
    p.ld(1, L.C["mdb"])
    p.iconst(12, -K.MD_STRIDE)
    p.iop(1, 12, "+", 1)
    p.iconst(12, L.state)
    p.if_(1, "LT", 12, lambda: (p.iconst(12, 16 * K.MD_STRIDE), p.iop(1, 12, "+", 1)), kind="i")
    p.seti(1, 1)
    p.ldi(2, C.VW["F"], 1)
    C.vws(p, "pre", 2)


def _render(M):
    def render(p: Prog, L: K.Layout) -> None:
        mL = L.mnm
        # I4 is the caller's (the slot's output: dnfw.md.voice.advance keeps I3, I4); the
        # halves below walk their own (v0.26 WIP wrote the voice's output over its words)
        p.e("R0 = I4;")
        if p.run:
            p.r[0] = p.i[4]
        p.st(mL.W["i4s"], 0)
        if M.NAME in MNM_OS_NAMES:              # the Monomachine's own machines read F, A, pre
            _pitch(p, L, TRANSPOSE.get(M.NAME, 0))
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


def _pad8(t, fill):
    """page 2's eight places (the eighth, PERC's TYPE record, unused by a Monomachine machine)"""
    return tuple(t) + (fill,) * (8 - len(t))


def _knobs(d):
    """page 2's starts as knobs 0..127 (a module may give them as 0..1)"""
    return tuple(int(round(x * 127)) if isinstance(x, float) else int(x) for x in d)


def _adapter(M):
    return type(M.NAME.replace(" ", "").replace("-", ""), (), {
        "NAME": M.NAME, "ID": M.ID, "PNAMES": M.PNAMES, "MNM": M,
        # 2026-11-09: a second page (PERC's page-2 records; dnfw.waverider.pages.MNM_PAGE2)
        **({"PNAMES2": _pad8(M.PNAMES2, "---"), "DEFAULTS2": _pad8(_knobs(M.DEFAULTS2), 0)}
           if hasattr(M, "PNAMES2") else {}),
        # 2026-11-11: a third page (dnfw.perc.machines.P3_RECS; dnfw.waverider.pages.MNM_PAGE3)
        **({"PNAMES3": _pad8(M.PNAMES3, "---"), "DEFAULTS3": _pad8(_knobs(M.DEFAULTS3), 0)}
           if hasattr(M, "PNAMES3") else {}),
        "host": staticmethod(_host_ddrw if M is ddrw else _host),
        "init": staticmethod(lambda p, L, M=M: M.init(p, L.mnm)),
        "trig": staticmethod(lambda p, L, M=M: M.trig(p, L.mnm)),
        "render": staticmethod(_render(M)),
    })


MACHINES = tuple(_adapter(M) for M in MODULES)
NAMES = tuple(M.NAME for M in MACHINES)
DEFAULTS = {M.NAME: M.DEFAULTS for M in MODULES}

# each voice's machine type (MACHINE SEL entry), in MODULES order. One table for the ColdFire
# (dnfw.waverider.coldfire, pages), the DSP's lookup (dnfw.waverider.dsp) and PERC's voice
# (dnfw.perc.program).
# v0.45 (2026-11-09, the User: keep upstream dn2mk2's numbers): BOUNCE is upstream's type 17, so
# SOPHIE moved 17 -> 20; PLAITS and TB303 keep 18 and 19.
# 2026-11-11 (the User: "i think one mono machine makes sense. and we should have uniformity about where we put
# the sub engine knob. so that it is logical and aligned with machinedrum"): the Monomachine's five ports are ONE
# machine, MONOMACHINE, on type 6 (SID's); its engine (SID 6581, DPRO-WAVE, DPRO-DDRW, DPRO-DENS, VO-6) is chosen
# by page 1 knob H (ENGN, the list popup with tags, as MACHINEDRUM's TYPE), the engine's first seven controls on
# A..G, its eighth (TUNE) on page 2 H (MACHINEDRUM's eighth's place). On the DSP each engine stays its own PERC
# voice (its index here), chosen by ENGN as PERC's TYPE chooses a Machinedrum machine (dnfw.perc.program). Types 7,
# 14, 15, 16 (the four engines' own until then) are reserved, never reused (RETIRED).
MONO_NAME = "MONOMACHINE"
MONO_TYPE = 6
MONO_ENGN = "ENGN"                       # the engine's control
MONO_ENGINE_K = 7                        # its place: page 1 H (PERC's eighth record, PD1: 0..100)
MONO_TUNE_J = 15                         # the engine's eighth (TUNE): page 2 H (PERC's TYPE record, 0..127)
ALL_TYPE_SLOTS = (20, 18, 19, 21, 22, 6, 6, 6, 6, 6)   # 20: SOPHIE (docs/sophie.md), 18: PLAITS, 19: TB303,
                                                       # 2026-11-10: 21 DRONE, 22 ANALOG2; 6: MONOMACHINE's five
# the four engines' former types (2026-11-11): a project's track on one stays there, silent, its page empty
RETIRED = {7: "DPRO-WAVE", 14: "DPRO-DDRW", 15: "DPRO-DENS", 16: "VO-6"}
TYPE_SLOTS = tuple(t for M, t in zip(ALL_MODULES, ALL_TYPE_SLOTS) if M in MODULES)   # each voice's type
TYPES = TYPE_SLOTS[:len(MACHINES)]       # per voice (NAMES' order): MONOMACHINE's engines all MONO_TYPE
MACHINE_TYPES = tuple(dict.fromkeys(TYPES))   # each machine type once
# MONOMACHINE's engines in this build (ENGN's choices, in this order): consecutive voices from MONO_FIRST
MONO_ENGINES = tuple(n for n in MNM_OS_NAMES if n in NAMES)
MONO_FIRST = NAMES.index(MONO_ENGINES[0]) if MONO_ENGINES else -1
assert all(NAMES.index(n) == MONO_FIRST + e for e, n in enumerate(MONO_ENGINES))
assert all((t == MONO_TYPE) == (n in MNM_OS_NAMES) for t, n in zip(TYPES, NAMES))
# ENGN's choices by name (4 characters: the page's choice box) and their tags (the list popup's, 11 at most)
MONO_CHOICES = {"SID 6581": "SID", "DPRO-WAVE": "WAVE", "DPRO-DDRW": "DDRW", "DPRO-DENS": "DENS", "VO-6": "VO-6"}
MONO_TAGS = {"SID 6581": "SID CHIP", "DPRO-WAVE": "32 WAVES", "DPRO-DDRW": "WAVE XFADE",
             "DPRO-DENS": "4-OSC CHORD", "VO-6": "FORMANTS"}


def mono_engine_of_knob(knob: int) -> int:
    """ENGN's knob (0..127) -> the engine, as the page reads a choice: (knob x n) >> 7"""
    return (knob * len(MONO_ENGINES)) >> 7


def mono_knob(e: int) -> int:
    """the knob in the middle of engine E's span (where MACHINE SEL and an engine change put ENGN)"""
    n = len(MONO_ENGINES)
    k = ((2 * e + 1) * 128) // (2 * n)
    assert mono_engine_of_knob(k) == e
    return k


# MACHINE SEL's order (dnfw.waverider.coldfire LIST_NEW): MONOMACHINE first (as the five were before their
# removal, SOPHIE after them), then the others in TYPES' order
LIST_TYPES = ((MONO_TYPE,) if MONO_ENGINES else ()) + tuple(t for t in MACHINE_TYPES if t != MONO_TYPE)
# the machines this build leaves out (dnfw.builder): their types are reserved, never reused, so
# every other machine keeps its number and a project's track on one stays on it (silent, its
# page empty). None in the full build; MONOMACHINE's four retired types always.
LEFT_OUT = {t: (MONO_NAME if t == MONO_TYPE else M.NAME)
            for M, t in zip(ALL_MODULES, ALL_TYPE_SLOTS) if t not in TYPES}
RESERVED = {**LEFT_OUT, **RETIRED}
assert not set(RESERVED) & set(TYPES)
assert all(TYPES.count(t) == 1 for t in MACHINE_TYPES if t != MONO_TYPE), "two machines of ours on one type"
from ..sampler import machines as _smp  # noqa: E402
assert not set(_smp.TYPES) & (set(TYPES) | set(RESERVED)), "a machine type of ours is a sample machine's (v0.44 BOUNCE: 17)"
# MACHINE SEL's names (long, short), as the DN2 lists its own
LIST_NAMES = {"SOPHIE": ("Sophie", "SOP"), "PLAITS": ("Plaits", "PLT"), "TB303": ("TB-303", "303"),
              "DRONE": ("Drone", "DRN"), "ANALOG2": ("Analog 2", "AN2"),
              MONO_NAME: ("Monomachine", "MNM")}
REMOVED_NAMES = ("Removed", "---")       # a reserved type's name (MACHINE SEL never lists it)


class Removed:
    """A reserved type's place in the ColdFire's tables (no DSP code): eight unused controls."""
    NAME, PNAMES, DEFAULTS = "REMOVED", ("---",) * 8, (0,) * 8


def _mono_place(name: str):
    """MONOMACHINE on engine NAME as the ColdFire's tables hold a machine: the engine's controls (its NAME: its
    choices, widgets, units and long names are the engine's), ENGN on page 1 H, the engine's TUNE on page 2 H"""
    V = MACHINES[NAMES.index(name)]
    e = MONO_ENGINES.index(name)
    d = DEFAULTS[name]
    assert V.PNAMES[7] == "TUNE", name
    return type("Mono" + V.__name__, (), {
        "NAME": name, "HOST": MONO_NAME, "ENGINE": e, "ID": V.ID, "MNM": V.MNM,
        "PNAMES": tuple(V.PNAMES[:7]) + (MONO_ENGN,),
        "PNAMES2": ("---",) * 7 + (V.PNAMES[7],),
        "DEFAULTS": tuple(d[:7]) + (mono_knob(e),),
        "DEFAULTS2": (0,) * 7 + (d[7],),
    })


MONO_PLACES = tuple(_mono_place(n) for n in MONO_ENGINES)

# the ColdFire's Monomachine places, one per type 6, 7, 14.. in type order (its page code turns a
# type into this index by arithmetic: dnfw.waverider.pages is_wr): the live machines and the
# reserved types' placeholders; MONOMACHINE's is its first engine's
CF_TYPES = tuple(sorted(set(TYPES) | set(RESERVED)))
CF_MACHINES = tuple(MONO_PLACES[0] if t == MONO_TYPE else MACHINES[TYPES.index(t)] if t in TYPES else Removed
                    for t in CF_TYPES)
CF_LIST_NAMES = tuple(LIST_NAMES[getattr(M, "HOST", M.NAME)] if M is not Removed else REMOVED_NAMES
                      for M in CF_MACHINES)
CF_DEFAULTS = tuple(M.DEFAULTS if hasattr(M, "HOST") else DEFAULTS.get(M.NAME, Removed.DEFAULTS)
                    for M in CF_MACHINES)
# 2026-11-11: MONOMACHINE's other engines' places, after the types' (no kind reaches them: the page code picks one
# by ENGN, dnfw.waverider.pages MNM_MONO); CF_ALL every place, the page code's tables
CF_EXTRA = MONO_PLACES[1:]
CF_ALL = CF_MACHINES + CF_EXTRA
CF_ALL_LIST_NAMES = CF_LIST_NAMES + tuple(LIST_NAMES[MONO_NAME] for _ in CF_EXTRA)
CF_ALL_DEFAULTS = CF_DEFAULTS + tuple(M.DEFAULTS for M in CF_EXTRA)
# each engine's place, in ENGN's order (none without MONOMACHINE in this build)
CF_MONO = CF_TYPES.index(MONO_TYPE) if MONO_ENGINES else -1
CF_MONO_PLACES = ((CF_MONO,) + tuple(range(len(CF_MACHINES), len(CF_ALL)))) if MONO_ENGINES else ()
