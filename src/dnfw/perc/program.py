"""PERC's whole DSP program: the type-5 loop (in Waverider's former place), one voice a
slot, the machines (dnfw.perc.machines), written once for both backends (dnfw.perc.dsl).

`voice(p, L, t)` is one slot's block -- what run mode executes as the model, and what the
SHARC runner holds the assembled code to. `program(L, ...)` adds the loop around it: the
register save the per-track chain expects (PING's tail restores it), the 16 slots, and the
jump on to RESONATOR's entry.
"""

from __future__ import annotations

import math

from . import machines as M
from .dsl import Prog
from ..md import voice as MDV
from ..md import core as MDK

MD_LEVEL = 1.4                            # the Machinedrum's full scale on a DN2 track: v0.22 +6 dB (0.7 in v0.17..v0.21),
                                          # its default hits as loud as WaveTone's and FM Tone's default notes

SAVE = 0x2DDE00                          # the save area PING's tail restores from
I3_BIAS = 96                                 # 2026-11-10 (shrink): words; see voice()
SAVE_REGS = [f"R{k}" for k in range(16)] + ["I0", "I1", "I2", "I3", "I4", "I5", "I12",
                                            "M0", "M1", "M2", "M3", "M4"]
NOTE_CELLS = 0x254B14
TRIG_WORD = 0x25C4AC
BUFFERS = 0x254A60
RECORDS, RECORD_STRIDE = 0x2554B8, 0x234
MACHINE_TYPE = 5
# v0.26: the Monomachine's synth machines (docs/mnm.md), each its own machine type, in PERC's
# voice: type -> index in dnfw.mnm.machines.MACHINES
from ..mnm import machines as _mnm_types   # noqa: E402
MNM_TYPES: dict[int, int] = {}            # 6, 7 (CZ's and RESONATOR's until v0.25), 14..
for _k, _t in enumerate(_mnm_types.TYPES):   # 2026-11-11: MONOMACHINE's type -> its first engine's voice; ENGN
    MNM_TYPES.setdefault(_t, _k)             # (page 1 H) adds the engine (mono_engine)
# 2026-11-11: MONOMACHINE's engine, from page 1 H's record (PERC's eighth, M.PARAMS[7]) as the page reads the choice:
# knob = (v 254 + top) / (2 top), engine = (knob n) >> 7 (md_page.c mnm_k, mnm_choice_of): the least v of each
# engine past the first
MONO_ENGN_REC = M.PARAMS[_mnm_types.MONO_ENGINE_K]


def _mono_thresholds() -> tuple[int, ...]:
    _rid, _slot, lo, top = MONO_ENGN_REC
    assert lo == 0                               # mono_engine compares the word >> 8 itself
    n = len(_mnm_types.MONO_ENGINES)
    e_of = [(((v * 254 + top) // (2 * top)) * n) >> 7 for v in range(top + 1)]
    return tuple(e_of.index(e) for e in range(1, n))


MONO_THRESHOLDS = _mono_thresholds() if _mnm_types.MONO_ENGINES else ()
# the engine's TUNE: page 2 H, PERC's TYPE record (0..127), read into p7 (the engine's eighth) for MONOMACHINE
MONO_TUNE_REC = M.TYPE_REC + (0, 127)
MNM_LEVEL = 0.25                         # a Monomachine machine's full scale on a DN2 track
# v0.27: each machine's own level, by name (owner: MNM-1 was quiet); a machine without one plays
# at MD_LEVEL (SOPHIE). 0.25 put SID's default sound at a peak of 0.046 on its track's buffer, DPRO
# Wave's 0.022, DDRW's 0.26, DENS's 0.13, VO-6's 0.015, where the Machinedrum machines peak at
# 1.0..1.4 (the model, 2026-10-27); each now peaks about 1.0 at its defaults. SID, the DPRO
# machines and VO-6 went on 2026-11-08 and came back on 2026-11-11 with their levels (28eb110's
# parent); a level is emitted only for a machine in this build.
MNM_LEVELS: dict[str, float] = {"DRONE": 0.7,   # 2026-11-09: DRONE peaks 1.5..1.8 at gain 1 (half MD_LEVEL; by ear later)
                                "SID 6581": 5.4, "DPRO-WAVE": 11.5, "DPRO-DDRW": 0.95, "DPRO-DENS": 2.0,
                                "VO-6": 16.5}
# v0.26: the DSP's room for the Monomachine voices. They never go quiet (as on the
# Monomachine, a voice plays until the next note), and one costs as much as two to ten of
# the Machinedrum's, so each block they are rendered in track order while their cost (the
# instructions a DN2 block takes, measured in the model at the most each can take,
# test_perc_live) fits MNM_BUDGET; a track past it plays silence that block. About half of
# what the SHARC has free beside the stock engines (docs/sharc-load.md: ~250,000 cycles).
MNM_COST = {"SOPHIE": 34_000,   # SOPHIE: 29,979 measured (test_perc_live, the trig block)
            "PLAITS": 60_000,   # PLAITS: the whole voice in a DN2 block (test_perc_live's harness), the heaviest
                                # engine's: STRG 58,409 (its entry block, its init clearing its DDR), PART
                                # 58,357, MDAL 47,418, ADD 32,682, FM 29,216, the others 20,295 (WS)..24,451
                                # (SD). 2026-11-09: one figure for every engine (sixteen voices at it, 960,000,
                                # stay under MNM_BUDGET, so a cost per engine would change nothing)
            "TB303": 70_000,    # TB303: 63,577 measured (WAVE square; saw 52,140), the voice in a DN2 block
            "DRONE": 36_000,    # DRONE: 17,251 + the voice ~14,700 with BEAT (two ears); ~24k without
            "JUNO": 27_000,     # JUNO (2026-11-12): worst steps 11,501 (BOTH+SUB+NOIS, BOOST, its note block) + ~14,700; runner cost step: 3,991 a voice-block (defaults)
            "ANALOG2": 32_000,  # ANALOG2: 16,168 (6 copies, sync, DIOD LP24, note 127) + ~14,700; 2026-11-11 WDTH on: 21,034 (MS20 LP24, DRV) steps    # DRONE: 17,251 + the voice ~14,700 with BEAT (two ears); ~24k without
            # the Monomachine's five (28eb110's parent; back 2026-11-11)
            "SID 6581": 60_000, "DPRO-WAVE": 34_000, "DPRO-DDRW": 78_000, "DPRO-DENS": 70_000,
            "VO-6": 75_000}
# v0.36: no longer the limit (the owner and misterairplane: two voices at most on a Monomachine
# track). 150,000 fitted 2 SID / VO-6 / DENS and 1 DDRW whatever the DSP's real time; it came
# before the frame guard (v0.27), which measures the frame and leaves out (v0.36: steals) the
# oldest voices that do not fit. Kept as a ceiling far above what sixteen voices can reach.
MNM_BUDGET = 1_000_000
# v0.29: which Monomachine voices get the budget: the newest first (the owner, 2026-10-28:
# with the DN2's dynamic voice allocation each note lands on a new voice; the older ones,
# which never go quiet, kept the budget in slot order, so most new notes were silent --
# CZ's v0.10 bug again, docs/cz.md). At PERC's entry every slot gets a key, its age in
# blocks (0 the block it is triggered) times 16 plus the slot, or NONE for a slot not on a
# Monomachine machine; a voice plays if the costs of the voices with smaller keys, and its
# own, fit the budget. In the Monomachine scratch's free tail (dnfw.mnm.core uses < 4 KB).
MNM_KEYS_OFF, MNM_COSTS_OFF = 0x3000, 0x3040
# v0.29: and every voice of ours (PERC, the Monomachine's, the sample machines') is rendered
# newest first: the owner's PERC test (TRX-CY, dynamic allocation) heard voices 1-8 and
# then silence -- the ringing older voices took the frame in slot order and the guard
# skipped every newer one. ORDER: the slots by key, the newest first (the ones not ours
# last); PERC's loop and the sample machines' loop walk it (their own index words).
ORDER_OFF, RANK_U, RANK_N, PERC_I, SMP_I = 0x3080, 0x30C0, 0x30C4, 0x30C8, 0x30CC
# v0.29: a Monomachine voice rests once its sound has died away after the AMP envelope (the
# owner: two Monomachine tracks sounding, a third stayed silent -- the budget held by voices
# whose notes had ended long before). At PERC's entry a type-5 track's buffer still holds
# its last block as the chain left it, after AMP (measured in the runner); QUIET_BLOCKS
# blocks under QUIET_LEVEL there, no note, and the voice rests: no cost, silent, until its
# next note. QUIET counts each slot's blocks at RESTS_OFF.
RESTS_OFF = 0x3100
# v0.36: the frame guard's strikes against each slot since its note: a voice left out a second
# time in one note is stolen (rests until its next note); once is a one-block gap (a note's
# first blocks cost the most: DDRW's chord lost three of its four voices to the attack alone)
STRIKES_OFF = 0x3140
# 2026-11-09 (the User: PLAITS silent sequenced with voice rotation, CPU; choice B): a machine's
# fixed start bound, the guard's expectation for a note's first blocks (dnfw.perc.guard
# START_BLOCKS) in place of the slot's stored cost; per slot at BOUNDS_OFF each block (mnm_ages),
# 0 for a slot not on such a machine (the guard decides as before). PLAITS only: its MNM_COST.
BOUNDS_OFF = 0x3180
SLOT_N = 0x31C0                            # 2026-11-10 (poly16): mnm_ages' loop over the slots, its counter
# 2026-11-12 (opt-host): each slot's budget sum, the costs of the slots with smaller keys and its own (mnm_ages, in a
# block with a Monomachine slot), so a voice's budget reads one word, not sixteen keys and their costs. In the L2
# scratch below the keys: nothing has used 0..0x3000 since the render scratch went to L1 (v0.43)
CUM_OFF = 0x2FC0
assert CUM_OFF + 4 * 16 <= MNM_KEYS_OFF
# 2026-11-12 (velocity, the User: "like Sophie, and our other synths too"): each slot's attenuation 1 - vel/127,
# latched at its trig (vel_latch), applied at the output guard; 0 (full level) until a velocity arrives. After
# ANALOG 2's mix tables (dnfw.mnm.analog2.TABLES_OFF, 106 words)
VEL_OFF = 0x3400
# 2026-11-10 (poly16, the User: 16 PLAITS voices on every engine): 30,000, not MNM_COST's 60,000: a
# note's start costs about a steady block now (the heaviest engine's ~25,000 on the memory clock),
# and sixteen notes started together must fit the frame at it (16 x 60,000 cannot: only six
# started a block and the rest were refused). A fresh voice's start (its reset) is FRESH-handled.
MNM_START = {"PLAITS": 30_000}
assert MNM_START["PLAITS"] <= MNM_COST["PLAITS"]
STEAL_STRIKES = 2
# 2026-11-12 (opt-host): mnm_ages' type tests, a bit a type: ours (PERC, the Monomachine machines, the sample
# machines), and the Monomachine machines
from ..sampler import machines as _smx_types   # noqa: E402
OURS_TYPES = (*MNM_TYPES, MACHINE_TYPE, *_smx_types.TYPES)
assert all(0 <= t < 32 for t in OURS_TYPES)
OURS_MASK = sum(1 << t for t in set(OURS_TYPES))
MNM_MASK = sum(1 << t for t in MNM_TYPES)
VOICE_MASK = MNM_MASK | 1 << MACHINE_TYPE      # PERC's loop: the slots its voice plays
MNM_QUIET_LEVEL = 2.0 ** -16                # -96 dB: an AMP envelope's tail and a filter's are under it
MNM_QUIET_BLOCKS = 64                      # 43 ms
MNM_SCRATCH = 0x200A4000                   # dsp.MNM_SCRATCH_L2 (v0.32: L2; test_waverider_dsp holds them equal)
ORDER = MNM_SCRATCH + ORDER_OFF
MNM_AGE_TOP = (1 << 26) - 1
MNM_NONE = 0x7FFFFFF0
SEED = 0x2545F491
OFF_LEVEL = 0.0002


def t146(p: Prog, d: int, t: int) -> None:
    """Rd = 146 Rt. Clobbers R12, R13."""
    p.lsh(12, t, 7)
    p.lsh(13, t, 4)
    p.iop(12, 12, "+", 13)
    p.lsh(13, t, 1)
    p.iop(d, 12, "+", 13)


def half(p: Prog, d: int, off: int, k146: int) -> None:
    """Rd = the frame copy's 16-bit word at offset OFF for this slot (Rk146 = 146 t).
    Clobbers R0, R1, R12, I1."""
    p.iconst(12, M.FRAME + off)
    p.iop(0, 12, "+", k146)
    p.iconst(12, 2)
    p.iop(1, 0, "AND", 12)
    p.iconst(12, -4)
    p.iop(0, 0, "AND", 12)
    p.seti(1, 0)
    p.ldi(d, 0, 1)
    p.ifz(1, "NE", lambda: p.lsh(d, d, -16))
    p.iconst(12, 0xFFFF)
    p.iop(d, d, "AND", 12)


# 2026-11-12 (opt-host): a voice's frame records read through two pointers set once a voice (frame_regs), not
# by half()'s address arithmetic each record: the same 16-bit halves, the same bytes. FRAME_BIAS (words) puts the
# records' offsets (frame_offset: 168 + 2 slot, slots 25..47) in -32..31: 4-byte loads that ride on computes
FRAME_BIAS = 52
assert M.FRAME % 4 == 0


def frame_regs(p: Prog) -> None:
    """For frame_byte, the slot in R9 and 146 t in R10: I1 = the slot's frame halves' word-aligned base (FRAME +
    146 t, less 2 for an odd slot), I0 = that + 4 for an odd slot (both + 4 FRAME_BIAS, biased); R13, R14 the
    shifts that bring a record's high byte down for a record at an offset = 0, = 2 (mod 4): a half at an address
    = 2 (mod 4) is a word's upper one (half()); R11 = 0xFF, R15 = 0. Clobbers R0, R1, R12."""
    p.iconst(12, M.FRAME + 4 * FRAME_BIAS)
    p.iop(0, 12, "+", 10)
    p.iconst(12, -4)
    p.iop(0, 0, "AND", 12)
    p.seti(1, 0, "the slot's frame words (+ FRAME_BIAS)", bias=FRAME_BIAS)
    p.iconst(12, 1)
    p.iop(1, 9, "AND", 12)                    # t & 1
    p.lsh(12, 1, 2)
    p.iop(0, 12, "+", 0)
    p.seti(0, 0, "the same, a word on for an odd slot", bias=FRAME_BIAS)
    p.lsh(12, 1, 4)                           # 16 (t & 1)
    p.iconst(13, -8)
    p.iop(13, 13, "-", 12)                    # offset = 0 (mod 4): even slot the lower half (-8), odd the upper (-24)
    p.iconst(14, -24)
    p.iop(14, 12, "+", 14)                    # = 2: even slot the upper half (-24), odd the lower (-8)
    p.iconst(11, 0xFF)
    p.iconst(15, 0)


def frame_byte(p: Prog, d: int, slot: int) -> None:
    """Rd = frame record SLOT's high byte for this slot (half() >> 8), after frame_regs (whose registers it
    keeps)."""
    off = M.frame_offset(slot)
    if off & 2:
        p.ldi(d, (off - 2) // 4, 0)
    else:
        p.ldi(d, off // 4, 1)
    MDK._shift_r(p, d, d, 14 if off & 2 else 13)
    p.iop(d, d, "AND", 11)


def raw_type(p: Prog, d: int) -> None:
    """Rd = this slot's machine type as the ColdFire sent it: the frame's header word at
    148 + 2 t (v0.13). The record's copy (+0x1b4) is the lookup's answer, which is 5 for
    PERC and for every sample machine (types 8..12 borrow PERC's engine slot, the one
    path through the stock code the runner and the instrument have proven), so the frame
    word tells them apart. Needs C['t'] in R9; clobbers R0, R1, R10, R12, I1."""
    p.iop(10, 9, "+", 9)
    half(p, d, 148, 10)


def mono_engine(p: Prog, d: int, s: int, k146: int) -> None:
    """2026-11-11: Rd = MONOMACHINE's engine 0..n-1 (ENGN, page 1 H) for the slot whose 146 t is in Rk146, the choice
    the page shows (MONO_THRESHOLDS). Rs the record's value (word >> 8). Clobbers R0, R1, R12, I1."""
    _rid, slot, _lo, _top = MONO_ENGN_REC
    half(p, s, M.frame_offset(slot), k146)
    p.lsh(s, s, -8)
    p.iconst(d, 0)
    for v in MONO_THRESHOLDS:
        p.iconst(12, v)
        p.if_(s, "GE", 12, lambda: (p.iconst(12, 1), p.iop(d, 12, "+", d)), kind="i")


def mnm_ages(p: Prog, L: M.Layout) -> None:
    """v0.29: every slot's key and Monomachine cost for this block (MNM_KEYS_OFF), and the
    slots in key order (ORDER_OFF), and (2026-11-12) the budget sums (CUM_OFF). Clobbers R0-R15, I0-I2."""
    from ..mnm import machines as MNM
    keys = L.md.mnm.scratch + MNM_KEYS_OFF
    costs = L.md.mnm.scratch + MNM_COSTS_OFF
    p.ld(3, TRIG_WORD)
    p.lsh(3, 3, -16)                           # the slots' note triggers (bit 0: this slot's, shifted on)
    # 2026-11-10 (poly16): one pass of a loop a slot (until then the 16 slots unrolled: about 1,900
    # instructions, 10 KB of the DSP upload); the same operations in the same order, slot u in the
    # word U_WORD, I5 at the scratch + 4 u (the per-slot words), R3 the triggers shifted to it
    # 2026-11-12 (opt-host): slot u in I0 (it was the L2 word U_WORD, read four times a slot), the count in R15
    # (it was the L2 word SLOT_N); both words left after the loop as it left them (16, 0)
    U_WORD = L.md.mnm.scratch + RANK_U         # (free until the ordering below starts it at 0)
    p.iconst(0, 0)
    p.seti(0, 0)
    p.seti(2, 0)
    p.iconst(0, L.md.mnm.scratch)
    p.seti(5, 0)

    def slot():
        p.geti(10, 0)
        p.iop(10, 10, "+", 10)                 # 2 u
        half(p, 2, 148, 10)                    # the slot's machine type, as raw_type
        p.iconst(4, 0)
        p.iconst(14, 0)                        # R14: ours (PERC, Monomachine, a sample machine): nonzero
        # 2026-11-12 (opt-host): which types are ours, and Monomachine machines, by one bit each of two masks
        # (a type under 32), the costs' compares only for a Monomachine machine: the same R4 and R14 (as a
        # flag) as the compare for each type
        p.iconst(12, 32)

        def small():                           # (its 1 << type: a count under 32)
            p.iconst(13, 1)
            MDK._shift_r(p, 13, 13, 2)
            p.iconst(12, OURS_MASK)
            p.iop(14, 13, "AND", 12)
            p.iconst(12, MNM_MASK)
            p.iop(12, 13, "AND", 12)

            def mnm_cost():
                p.iconst(12, 1)
                p.seti(2, 12)                  # I2: a Monomachine slot this block (for the budget sums)
                for typ, k in MNM_TYPES.items():
                    p.iconst(12, typ)
                    p.if_(2, "EQ", 12, lambda c=MNM_COST[MNM.NAMES[k]]: p.iconst(4, c), kind="i")
            p.ifz(12, "NE", mnm_cost)
        p.if_(2, "LT", 12, small, kind="i")
        if MONO_THRESHOLDS:                    # 2026-11-11: MONOMACHINE's cost is its engine's

            def mono_cost():
                p.geti(8, 0)
                t146(p, 11, 8)
                mono_engine(p, 6, 7, 11)
                for e, name in enumerate(MNM.MONO_ENGINES[1:], start=1):
                    p.iconst(12, e)
                    p.if_(6, "EQ", 12, lambda c=MNM_COST[name]: p.iconst(4, c), kind="i")
                # ... or the engine the voice still plays (ENGN turned, no note yet), whichever costs more
                p.geti(8, 0)
                p.lsh(12, 8, 10)
                p.iconst(11, L.md.state + 4 * MDK.VW["mach"])
                p.iop(12, 11, "+", 12)
                p.seti(1, 12)
                p.ldi(6, 0, 1)
                for e, name in enumerate(MNM.MONO_ENGINES):
                    def more(c=MNM_COST[name]):
                        p.iconst(12, c)
                        p.if_(4, "LT", 12, lambda: p.iconst(4, c), kind="i")
                    p.iconst(12, MDV.N + MNM.MONO_FIRST + e)
                    p.if_(6, "EQ", 12, more, kind="i")
            p.iconst(12, MNM.MONO_TYPE)
            p.if_(2, "EQ", 12, mono_cost, kind="i")
        p.sti(MNM_COSTS_OFF // 4, 5, 4)
        p.iconst(4, 0)                         # 2026-11-09: the slot's start bound (MNM_START)
        for typ, k in MNM_TYPES.items():
            if MNM.NAMES[k] in MNM_START:
                p.iconst(12, typ)
                p.if_(2, "EQ", 12, lambda c=MNM_START[MNM.NAMES[k]]: p.iconst(4, c), kind="i")
        p.sti(BOUNDS_OFF // 4, 5, 4)

        def mnm():
            p.iconst(12, 1)
            p.iop(12, 3, "AND", 12)

            def struck():
                p.iconst(0, 0)
                p.sti(RESTS_OFF // 4, 5, 0)
                p.sti(STRIKES_OFF // 4, 5, 0)  # v0.36: a new note, no strikes

            def listen():                      # the block the chain left in its buffer
                p.geti(0, 5)
                p.iconst(12, BUFFERS - L.md.mnm.scratch)
                p.iop(0, 12, "+", 0)           # BUFFERS + 4 u
                p.seti(4, 0)
                p.ldi(0, 0, 4)
                p.seti(1, 0)                   # (2026-11-12: I1, not I4: a load rides on a compute)
                p.fconst(7, 0.0)
                MDV.peak32(p, 1, counter=5)
                p.ldi(0, RESTS_OFF // 4, 5)
                p.fconst(12, MNM_QUIET_LEVEL)
                p.if_(7, "LT", 12, lambda: (p.iconst(12, 1), p.iop(0, 12, "+", 0)), lambda: p.iconst(0, 0))
                p.sti(RESTS_OFF // 4, 5, 0)
            p.ifz(12, "NE", struck, listen)
            p.ldi(0, RESTS_OFF // 4, 5)
            p.iconst(12, MNM_QUIET_BLOCKS)
            p.if_(0, "GE", 12, lambda: (p.iconst(4, 0), p.sti(MNM_COSTS_OFF // 4, 5, 4)), kind="i")   # resting: free
            p.ldi(13, MNM_KEYS_OFF // 4, 5)
            p.lsh(13, 13, -4)                  # its age last block
            p.iconst(12, MNM_AGE_TOP)
            p.if_(13, "LT", 12, lambda: (p.iconst(12, 1), p.iop(13, 13, "+", 12)), kind="i")
            p.iconst(12, 1)
            p.iop(12, 3, "AND", 12)
            p.ifz(12, "NE", lambda: p.iconst(13, 0))    # a note this block: the newest
            p.lsh(13, 13, 4)
            p.geti(12, 0)
            p.iop(13, 13, "OR", 12)
            p.sti(MNM_KEYS_OFF // 4, 5, 13)

        def none():
            p.iconst(12, MNM_NONE)
            p.geti(5, 0)
            p.iop(5, 12, "+", 5)               # MNM_NONE | u (its low four bits are 0)
            p.sti(MNM_KEYS_OFF // 4, 5, 5)
        p.ifz(14, "NE", mnm, none)
        p.lsh(3, 3, -1)                        # the next slot's trigger to bit 0
        p.geti(12, 0)
        p.iconst(13, 1)
        p.iop(12, 12, "+", 13)
        p.seti(0, 12)
        p.geti(0, 5)
        p.iconst(12, 4)
        p.iop(0, 12, "+", 0)
        p.seti(5, 0)
    p.loop_r(15, 16, slot)
    p.iconst(0, 16)
    p.st(U_WORD, 0)
    p.iconst(0, 0)
    p.st(L.md.mnm.scratch + SLOT_N, 0)
    # the slots in key order: slot u goes to place (how many keys are smaller). 2026-11-12 (opt-host): six slots'
    # keys at a time held in R0..R5, each pass over the sixteen keys (one L2 read each) counting for all six at
    # once (a compare and a conditional add): the same places, 48 key reads a block instead of 256; ORDER
    # written place by place as before (its words the same), RANK_U left at 16 by the loop above (as the old
    # count left it), RANK_N at 0 (as its loop left it)
    order = L.md.mnm.scratch + ORDER_OFF
    p.iconst(0, 0)
    p.st(L.md.mnm.scratch + RANK_N, 0)
    counts = (8, 9, 10, 11, 13, 15)            # (integer adds take R8..R15 first; R12 is loop_r's, R14 its count)
    for lo in range(0, 16, len(counts)):
        us = list(range(lo, min(lo + len(counts), 16)))
        for j, u in enumerate(us):
            p.ld(j, keys + 4 * u)              # slot u's key in Rj
        for j in range(len(us)):
            p.iconst(counts[j], 0)
        p.iconst(7, 1)
        p.iconst(12, keys)
        p.seti(1, 12)

        def each_v(n=len(us)):
            p.ldpost(6, 1)                     # key v
            for j in range(n):
                p.comp_iop_if(6, j, "LT", counts[j], counts[j], "+", 7)
        p.loop_r(14, 16, each_v)
        p.iconst(14, order)
        for j, u in enumerate(us):
            p.lsh(12, counts[j], 2)
            p.iop(12, 14, "+", 12)
            p.seti(1, 12)
            p.iconst(7, u)
            p.sti(0, 1, 7)                     # ORDER[place] = u
    # 2026-11-12 (opt-host): the budget sums (CUM_OFF), in a block with a Monomachine slot: the costs in key order,
    # summed (the same integers budget() added up, in another order)
    p.geti(12, 2)

    def sums():
        p.iconst(8, 0)
        p.iconst(11, costs)
        p.iconst(12, order)
        p.seti(1, 12)

        def one():
            p.ldpost(9, 1)                     # the next slot in key order
            p.lsh(10, 9, 2)
            p.iop(10, 11, "+", 10)
            p.seti(0, 10)
            p.ldi(10, 0, 0)
            p.iop(8, 8, "+", 10)
            p.sti((CUM_OFF - MNM_COSTS_OFF) // 4, 0, 8)
        p.loop_r(14, 16, one)
    p.ifz(12, "NE", sums)


def order_slot(p: Prog, idx: int) -> None:
    """v0.29: C['t'] (the caller's) = ORDER[the index word IDX]; R9 = it. Clobbers R0, R12, I1."""
    p.ld(0, idx)
    p.lsh(12, 0, 2)
    p.iconst(9, ORDER)
    p.iop(12, 9, "+", 12)
    p.seti(1, 12)
    p.ldi(9, 0, 1)


def voice(p: Prog, L: M.Layout, t: int | None = None) -> None:
    """One slot's block. In run mode T is the slot (also stored at C['t']); in emit mode
    the slot is read from C['t']."""
    C = L.C
    if p.run:
        p.iconst(9, t)
        p.st(C["t"], 9)
    # v0.26: which Monomachine machine (index + 1), 0 for PERC, from the frame's type word
    p.ld(9, C["t"], "t")
    raw_type(p, 2)
    p.iconst(0, 0)
    for typ, k in MNM_TYPES.items():
        p.iconst(12, typ)
        p.if_(2, "EQ", 12, lambda k=k: p.iconst(0, k + 1), kind="i")
    p.st(C["mnm"], 0)
    if MONO_THRESHOLDS:
        # 2026-11-11: MONOMACHINE: its engine (ENGN, page 1 H) picks the engine's voice, as PERC's TYPE picks a
        # Machinedrum machine: everything after (its level, cost, voice, a new note's init) is that engine's own
        def mono():
            p.ld(9, C["t"])
            t146(p, 10, 9)
            mono_engine(p, 6, 7, 10)
            p.ld(0, C["mnm"])
            p.ipass(12, 6)
            p.iop(0, 12, "+", 0)
            p.st(C["mnm"], 0)
        p.iconst(12, _mnm_types.MONO_TYPE)
        p.if_(2, "EQ", 12, mono, kind="i")
    p.ld(9, C["t"], "t")
    p.lsh(12, 9, 7)
    p.iconst(11, L.state)
    p.iop(12, 11, "+", 12)
    p.seti(2, 12, "this slot's state")
    p.st(C["sbase"], 12)
    # the trigger
    p.ld(0, TRIG_WORD)
    p.lsh(0, 0, -16)
    p.iconst(1, 1)
    p.ld(9, C["t"])
    _shift_by(p, 1, 9)
    p.iop(0, 0, "AND", 1)
    p.st(C["trig"], 0)
    vel_latch(p, L)
    # TYPE and the eight parameters from the frame
    p.ld(9, C["t"])
    t146(p, 10, 9)
    frame_regs(p)
    frame_byte(p, 4, M.TYPE_REC[1])
    p.iconst(12, 127)
    p.iop(4, 4, "MIN", 12)
    p.iconst(12, 0)
    p.float_(4, 4, 12)
    p.fconst(12, MDV.N / 128.0)               # 0..127 over the machines (v0.17)
    p.fop(4, 4, "*", 12)
    p.trunc(4, 4)
    p.ld(5, C["mnm"])                         # v0.26: a Monomachine machine's type picks it
    p.ifz(5, "NE", lambda: (p.iconst(12, MDV.N - 1), p.iop(4, 12, "+", 5)))
    p.st(C["type"], 4)
    def param(k, slot, lo, top, word=None):
        frame_byte(p, 4, slot)
        if lo:                                 # (+ 0 left out: the same word)
            p.iconst(12, -lo)
            p.iop(4, 12, "+", 4)
        p.iop(4, 4, "MAX", 15)                 # (R15 = 0: frame_regs)
        p.iconst(12, top)
        p.iop(4, 4, "MIN", 12)
        p.iconst(12, 0)
        p.float_(5, 4, 12)
        p.fconst(12, 1.0 / top)
        p.fop(5, 5, "*", 12)
        p.st(C[word or (f"p{k}" if k < 8 else f"q{k - 8}" if k < 15 else f"r{k - 15}")], 5)
    for k, (_rid, slot, lo, top) in enumerate(M.PARAMS):
        param(k, slot, lo, top)
    if MONO_THRESHOLDS:
        # 2026-11-11: MONOMACHINE's engine reads its eighth (TUNE) where it always did (p7), from page 2 H: page 1 H
        # is ENGN
        first = _mnm_types.MONO_FIRST + 1
        last = _mnm_types.MONO_FIRST + len(_mnm_types.MONO_ENGINES)
        p.ld(5, C["mnm"])
        p.iconst(6, 0)
        p.iconst(12, first)
        p.if_(5, "GE", 12, lambda: (p.iconst(12, last), p.if_(5, "LE", 12, lambda: p.iconst(6, 1), kind="i")),
              kind="i")
        _rid, slot, lo, top = MONO_TUNE_REC
        p.ifz(6, "NE", lambda: param(7, slot, lo, top))

    def fx_params():                          # 2026-11-10 (poly16): only PERC's voices read them (fx)
        for k, (_rid, slot, lo, top) in enumerate(M.FX_PARAMS, start=len(M.PARAMS)):
            param(k, slot, lo, top)
        param(0, M.TYPE_REC[1], 0, 127, "q7")   # 2026-11-11: page 2's eighth, TYPE's record (ANALOG 2's WDTH)
    # 2026-11-11 (the merge, found by the runner's DRONE glide check): the page-2 words (q0..q6) feed PERC's own
    # machines AND the Monomachine machines that have a second page (DRONE's GLID/GLTY/HOLD, ANALOG2's
    # SWRM SEMI SDTN SYNC WAV2 DRFT FLT): the poly16 skip for every Monomachine machine left them 0
    from ..mnm import machines as _MNMM
    page2 = [k + 1 for k, _m in enumerate(_MNMM.MACHINES) if hasattr(_m, "PNAMES2")]
    p.ld(5, C["mnm"])
    p.iconst(6, 0)
    p.ifz(5, "EQ", lambda: p.iconst(6, 1))
    for idx in page2:
        p.iconst(12, idx)
        p.if_(5, "EQ", 12, lambda: p.iconst(6, 1), kind="i")
    p.ifz(6, "NE", fx_params)
    # 2026-11-11: page 3's words (r0, r1: ANALOG 2's GLID, GLTY), for the Monomachine machines that have one
    page3 = [k + 1 for k, _m in enumerate(_MNMM.MACHINES) if hasattr(_m, "PNAMES3")]
    if page3:
        p.ld(5, C["mnm"])
        p.iconst(6, 0)
        for idx in page3:
            p.iconst(12, idx)
            p.if_(5, "EQ", 12, lambda: p.iconst(6, 1), kind="i")
        p.ifz(6, "NE", lambda: [param(8 + 7 + k, slot, lo, top)
                                for k, (_rid, slot, lo, top) in enumerate(M.P3_RECS[:M.P3_READ])])
    # the Machinedrum machine (v0.17, docs/md.md): its slot's words at I3
    p.ld(9, C["t"])
    p.lsh(12, 9, 10)
    p.iconst(11, L.md.state)
    p.iop(12, 11, "+", 12)
    p.st(L.md.C["mdb"], 12)
    # 2026-11-10 (shrink): I3 = the slot + I3_BIAS words, so the state words S0.. (most of
    # the slot's moves) take a 6-bit offset (4-byte instructions instead of 6)
    p.iconst(11, 4 * I3_BIAS)
    p.iop(12, 11, "+", 12)
    p.seti(3, 12, "this slot's Machinedrum words + I3_BIAS", bias=I3_BIAS)
    # the slot's buffer
    p.ld(9, C["t"])
    p.lsh(12, 9, 2)
    p.iconst(11, BUFFERS)
    p.iop(12, 11, "+", 12)
    p.seti(1, 12)
    p.ldi(0, 0, 1)
    p.seti(4, 0, "the slot's buffer")
    p.st(C["buf"], 0)
    # a slot that has just become PERC starts clean, playing nothing until its first note
    M.v(p, 0, "on")

    def fresh():
        MDV.reset(p, L.md)
        p.iconst(0, 1)
        M.vs(p, "on", 0)
    p.ifz(0, "EQ", fresh)
    # the level, and for a Monomachine machine the note (float semitones, as RESONATOR reads it)
    p.fconst(0, MD_LEVEL)
    p.st(C["lev"], 0)
    p.ld(0, C["mnm"])

    def mnm_note():
        from ..mnm import core as MNC
        for name, lev in ((n, v) for n, v in MNM_LEVELS.items() if n in _mnm_types.NAMES):   # v0.27: the machine's own level (2026-11-09: only those built)
            p.iconst(12, _mnm_types.NAMES.index(name) + 1)
            p.if_(0, "EQ", 12, lambda lev=lev: (p.fconst(1, lev), p.st(C["lev"], 1)), kind="i")
        p.ld(9, C["t"])
        p.lsh(12, 9, 2)
        p.iconst(11, NOTE_CELLS)
        p.iop(12, 11, "+", 12)
        p.seti(1, 12)
        p.ldi(8, 0, 1)
        p.lsh(12, 8, -23)
        p.iconst(13, 0xFF)
        p.iop(12, 12, "AND", 13)
        p.if_(12, "EQ", 13, lambda: p.iconst(8, 0), kind="i")    # NaN, infinite: 0
        p.ifz(8, "LT", lambda: p.iconst(8, 0))                    # negative: 0
        MNC.vws(p, "pitch", 8)
    p.ifz(0, "NE", mnm_note)
    # v0.26: a Monomachine voice only while the block's Monomachine cost fits MNM_BUDGET
    p.iconst(0, 0)
    p.st(C["mskip"], 0)
    p.ld(0, C["mnm"])

    def budget():
        # v0.29: the newer voices' costs first (mnm_ages), then this one's
        keys = L.md.mnm.scratch + MNM_KEYS_OFF
        p.ld(8, C["t"])
        p.lsh(12, 8, 2)
        p.iconst(11, keys)
        p.iop(12, 11, "+", 12)
        p.seti(1, 12)
        p.ldi(8, (CUM_OFF - MNM_KEYS_OFF) // 4, 1)    # 2026-11-12: their costs and its own, summed by mnm_ages
        p.ldi(5, (RESTS_OFF - MNM_KEYS_OFF) // 4, 1)    # v0.29: resting (its sound died away)
        p.iconst(12, MNM_QUIET_BLOCKS)
        p.if_(5, "GE", 12, lambda: p.iconst(8, MNM_BUDGET + 1), kind="i")
        p.iconst(12, MNM_BUDGET)
        p.if_(8, "GT", 12, lambda: (p.iconst(0, 1), p.st(C["mskip"], 0)),
              lambda: p.st(C["mcost"], 8), kind="i")
    p.ifz(0, "NE", budget)

    def md_rest():
        # v0.31: a Machinedrum voice rests too once its sound has died away after the AMP
        # (depaffect: eight PERC tracks with dynamic allocation stopped all audio; each note
        # takes another voice, and the old ones went on costing a full render each block)
        p.ld(8, C["t"])
        p.lsh(12, 8, 2)
        p.iconst(11, L.md.mnm.scratch + RESTS_OFF)
        p.iop(12, 11, "+", 12)
        p.seti(1, 12)
        p.ldi(5, 0, 1)
        p.iconst(12, MNM_QUIET_BLOCKS)
        p.if_(5, "GE", 12, lambda: (p.iconst(0, 1), p.st(C["mskip"], 0)), kind="i")
    p.ld(0, C["mnm"])
    p.ifz(0, "EQ", md_rest)

    def mono_level():
        # 2026-11-11: an engine plays at its own level: ENGN turned with no note, the voice plays the old engine on
        # until the next note (as a new TYPE), at that engine's level (the runner: DENS at VO-6's 16.5 went past 4.0)
        # (a MONOMACHINE track only: C['mnm'] one of its engines)
        def by_mach():
            MDK.vw(p, 0, "mach")
            for e, name in enumerate(_mnm_types.MONO_ENGINES):
                p.iconst(12, MDV.N + _mnm_types.MONO_FIRST + e)
                p.if_(0, "EQ", 12, lambda lev=MNM_LEVELS[name]: (p.fconst(1, lev), p.st(C["lev"], 1)), kind="i")
        p.ld(5, C["mnm"])
        p.iconst(12, _mnm_types.MONO_FIRST + 1)
        p.if_(5, "GE", 12, lambda: (p.iconst(12, _mnm_types.MONO_FIRST + len(_mnm_types.MONO_ENGINES)),
                                    p.if_(5, "LE", 12, by_mach, kind="i")), kind="i")

    def render():
        p.ld(2, C["trig"])
        p.ld(5, C["type"])
        MDV.block(p, L.md, [C[f"p{k}"] for k in range(8)], 2, 5, level_word=C["lev"],
                  after_advance=mono_level if MONO_THRESHOLDS else None)

    def silence():                            # past the budget: this block is silent
        p.ld(0, C["buf"])
        p.seti(4, 0)
        p.fconst(1, 0.0)
        p.loop(C["tmp"], 32, lambda: p.stpost(4, 1))
    p.ld(0, C["mskip"])
    p.ifz(0, "NE", silence, render)
    p.ld(12, C["sbase"])
    p.seti(2, 12, "this slot's state, again")
    p.ld(0, C["mnm"])
    p.ifz(0, "EQ", lambda: fx(p, L))          # the Machinedrum's track effects: PERC's only
    out_guard(p, L)


OUT_LIMIT = 8.0                                # v0.33: our voices' samples, at most (+- 18 dBFS)


def _vel_word(p: Prog, L: M.Layout) -> None:
    """I1 = this slot's attenuation word (VEL_OFF + 4 t). Clobbers R9, R11, R12."""
    p.ld(9, L.C["t"])
    p.lsh(12, 9, 2)
    p.iconst(11, L.md.mnm.scratch + VEL_OFF)
    p.iop(12, 11, "+", 12)
    p.seti(1, 12)


def vel_latch(p: Prog, L: M.Layout) -> None:
    """2026-11-12: at the slot's trig, its note's velocity (frame slot M.VEL_SLOT, vel x 256; 0: none sent, full level)
    as the attenuation (127 - vel) / 127, so 127 and none are exactly 0 (the voice bit for bit as before). Clobbers
    R0, R1, R4, R9..R12, I1."""
    C = L.C

    def latch():
        p.ld(9, C["t"])
        t146(p, 10, 9)
        half(p, 4, M.frame_offset(M.VEL_SLOT), 10)
        p.lsh(4, 4, -8)
        p.iconst(12, 127)
        p.ifz(4, "EQ", lambda: p.iconst(4, 127))
        p.iop(4, 4, "MIN", 12)
        p.iop(4, 12, "-", 4)                       # 127 - vel
        p.iconst(12, 0)
        p.float_(4, 4, 12)
        p.fconst(12, 1.0 / 127.0)
        p.fop(4, 4, "*", 12)
        _vel_word(p, L)
        p.sti(0, 1, 4)
    p.ld(0, C["trig"])
    p.ifz(0, "NE", latch)


def out_guard(p: Prog, L: M.Layout) -> None:
    """v0.33 (Moog, CAT: a PERC track burst into white noise, then all audio went silent until
    a restart -- the signature of a voice blowing up: a resonant filter or a feedback state
    running away to infinity, then NaN, which the stock chain carries into the delay and
    reverb, where it stays). Every sample of the block our voice wrote is held to
    +-OUT_LIMIT; and if one is not finite (infinite or NaN: its exponent all ones), the whole
    block is zeroed and the voice's state cleared (its 'on' word with it: the next block starts
    it fresh, as a new machine), so nothing non-finite ever leaves our code. 2026-11-12: each sample first scaled
    by the slot's velocity (vel_latch; F6 = 1 - its attenuation). Uses R0-R2, R5, R6, R9-R14, I1, I2, I4 and fxy
    (a flag, free after the effects)."""
    C = L.C
    _vel_word(p, L)                            # 2026-11-12: x vel/127 = 1 - the slot's attenuation (vel_latch)
    p.ldi(6, 0, 1)
    p.fconst(12, 1.0)
    p.fop(6, 12, "-", 6)
    p.iconst(0, 0)
    p.st(C["fxy"], 0)
    p.ld(0, C["buf"])
    p.seti(1, 0, "the slot's buffer, the guard")
    # 2026-11-10 (poly16): the non-finite test as a sum of x x 0 (0 for every finite x, NaN from
    # an infinite or NaN one, and a NaN stays), tested once after the block; the limits in
    # registers: the same block written, the same verdict, 5 instructions a sample, not 10
    p.fconst(14, OUT_LIMIT)
    p.fconst(13, -OUT_LIMIT)
    p.fconst(11, 0.0)                          # x 0
    p.fconst(10, 0.0)                          # the sum

    def four():
        # 2026-11-12 (opt-host): each sample's operations as before (x 0, MIN, the sum, MAX, the store), the
        # samples in turn in R0 and R2 through I1, so the next sample's load and each store but the pass's
        # last ride on a compute: 20 instructions the four samples, not 24
        def sample(x: int, y: int | None, first: bool) -> None:
            p.fop(x, x, "*", 6)                # 2026-11-12: x vel/127 (the NaN test below sees the scaled sample)
            p.fop(1, x, "*", 11)               # (takes in the store before it, if any)
            if y is not None and first:
                p.ldi(y, 1, 1)                 # the next sample (I1 still at this one)
            p.fop(x, x, "MIN", 14)
            if y is not None and not first:
                p.ldi(y, 1, 1)                 # the next sample (I1 at the one before it)
            p.fop(10, 10, "+", 1)
            p.fop(x, x, "MAX", 13)
            p.stpost(1, x)
        p.ldi(0, 0, 1)
        sample(0, 2, True)
        sample(2, 0, False)
        sample(0, 2, False)
        sample(2, None, False)
    p.loop_r(5, 8, four)
    p.ipass(12, 10)
    p.lsh(12, 12, -23)
    p.iconst(13, 0xFF)
    p.iop(12, 12, "AND", 13)
    p.if_(12, "EQ", 13, lambda: (p.iconst(13, 1), p.st(C["fxy"], 13)), kind="i")

    def blown():
        # v0.34: the record first (docs/timing-model.md; the owner's O13: P-I machines silent
        # on the same voices every time). Which slot and machine, and the first non-finite
        # word in the voice's P-I delay lines; none: the poison was in the voice's own state
        # (the filters', zeroed here), its input, or the effects
        from . import guard as G
        p.comment("v0.34: the guard's record: count, slot | type << 8, the mask")
        p.ld(1, G.BLOWN_COUNT)
        p.iconst(12, 1)
        p.iop(1, 12, "+", 1)
        p.st(G.BLOWN_COUNT, 1)
        p.ld(1, C["type"])
        p.lsh(1, 1, 8)
        p.ld(12, C["t"])
        p.iop(1, 1, "OR", 12)
        p.st(G.BLOWN_INFO, 1)
        p.iconst(1, 1)
        p.ld(12, C["t"])
        _shift_by(p, 1, 12)                   # 1 << t
        p.ld(12, G.BLOWN_MASK)
        p.iop(1, 1, "OR", 12)
        p.st(G.BLOWN_MASK, 1)
        p.iconst(1, G.WHERE_NONE)
        p.st(G.BLOWN_WHERE, 1)
        p.iconst(1, 0)
        p.st(C["fxy"], 1, "the scan's index")

        def scan(n: int, tag: int):
            """I5 walks N words; the first non-finite one's index | TAG and bits are kept"""
            def word():
                p.ldpost(1, 5)
                p.lsh(12, 1, -23)
                p.iconst(13, 0xFF)
                p.iop(12, 12, "AND", 13)

                def first():
                    p.ld(13, G.BLOWN_WHERE)
                    p.iconst(12, G.WHERE_NONE)

                    def keep():
                        p.st(G.BLOWN_WORD, 1)
                        p.ld(13, C["fxy"])
                        p.iconst(12, tag)
                        p.iop(13, 13, "OR", 12)
                        p.st(G.BLOWN_WHERE, 13)
                    p.if_(13, "EQ", 12, keep, kind="i")
                p.if_(12, "EQ", 13, first, kind="i")
                p.ld(13, C["fxy"])
                p.iconst(12, 1)
                p.iop(13, 12, "+", 13)
                p.st(C["fxy"], 13)
            p.loop(C["tmp"], n, word)
        # (the delay lines only: the voice's stream holds the tainted output itself, and
        # its machine words hold integers, -1 among them, whose bits are the core's NaN)
        MDK.delay_base(p, L.md, 1)
        p.seti(5, 1, "the P-I delay lines")
        scan(MDK.PI_DELAY_WORDS, G.WHERE_DELAY)
        # then the wipe: the block silent and the voice's state zeroed, so the next block
        # starts it fresh (reset: its words and delay lines cleared). v0.33 stored R0 here,
        # which loop() uses as its counter: the state got 32, 31 .. 1 instead of zeros, its
        # 'on' word with them, so the voice never reset and stayed silent until a power-on
        p.ld(0, C["buf"])
        p.seti(4, 0)
        p.fconst(1, 0.0)
        p.loop(C["tmp"], 32, lambda: p.stpost(4, 1))
        p.ld(12, C["sbase"])
        p.seti(2, 12, "this slot's state, cleared")
        p.iconst(1, 0)
        p.loop(C["tmp"], 32, lambda: p.stpost(2, 1))
    p.ld(0, C["fxy"])
    p.ifz(0, "NE", blown)


def fx(p: Prog, L: M.Layout) -> None:
    """The Machinedrum's track effects on the block the machine just wrote (rv_perc.c
    perc_render): amplitude modulation, a one-band peaking EQ, a high pass and a low pass
    (the band filter). Each runs only when its control turns it on; at the records'
    defaults none does and the block is left as it is. Linear, so run after the machine's
    trim rather than before it."""
    C = L.C
    one = 12

    def q(d, k):
        p.ld(d, C[f"q{k}"])

    # AM: depth, and the phase step a sample (0.1 Hz .. 2.3 kHz)
    q(4, 0)
    p.st(C["amd"], 4)
    p.iconst(5, 0)
    p.st(C["fxam"], 5)
    p.fconst(6, 0.0)

    def am_on():
        p.iconst(5, 1)
        p.st(C["fxam"], 5)
        q(8, 1)                               # 2026-11-12 (opt-host): the step only when AM is on (only the
        p.fconst(one, 14.5)                   # AM pass reads amdt): the same word then
        p.fop(8, 8, "*", one)
        M.exp2(p, L, 8, 8)
        p.fconst(one, 0.1 * M.DT)
        p.fop(8, 8, "*", one)
        p.st(C["amdt"], 8)
    p.if_(4, "GT", 6, am_on)
    # EQ: gain in dB, (EQG - 0.5) x 36: +-18, 0 at the record's default
    q(4, 3)
    p.fconst(one, 0.5)
    p.fop(4, 4, "-", one)
    p.fconst(one, 36.0)
    p.fop(4, 4, "*", one)
    p.st(C["tmp"], 4)
    p.iconst(5, 0)
    p.st(C["fxeq"], 5)

    def eq_on():
        p.iconst(5, 1)
        p.st(C["fxeq"], 5)
        p.ld(4, C["tmp"])
        p.fconst(one, 0.1661)
        p.fop(4, 4, "*", one)
        M.exp2(p, L, 9, 4)
        p.fconst(one, 1.0)
        p.fop(9, 9, "-", one)
        p.st(C["eqm"], 9)                   # 2^(eqg 0.1661) - 1
        q(8, 2)
        p.fconst(one, 8.9)
        p.fop(8, 8, "*", one)
        M.exp2(p, L, 8, 8)
        p.fconst(one, 40.0)
        p.fop(8, 8, "*", one)                # 40 .. 19 kHz
        M.svf_set(p, L, 3, 8, qc=1.2)
        p.ld(9, C["eqm"])
        p.ld(10, C["s3k"])
        p.fop(9, 9, "*", 10)
        p.st(C["eqm"], 9)                   # eq.k (2^(eqg 0.1661) - 1)
    p.fconst(one, 0.2)
    p.if_(4, "GT", one, eq_on, lambda: (p.fconst(one, -0.2), p.if_(4, "LT", one, eq_on)))
    # the band filter: base FLTF, width FLTW, q 0.5 + FLTQ^2 x 12 / 16129 (0..127 each)
    q(4, 4)
    p.fconst(one, 127.0)
    p.fop(4, 4, "*", one)
    p.st(C["y"], 4)                          # e13
    q(5, 5)
    p.fop(5, 5, "*", one)
    p.st(C["ns"], 5)                         # e14
    q(6, 6)
    p.fop(6, 6, "*", one)
    p.fop(6, 6, "*", 6)
    p.fconst(one, 12.0 / 16129.0)
    p.fop(6, 6, "*", one)
    p.fconst(one, 0.5)
    p.fop(6, 6, "+", one)
    p.st(C["tmp2"], 6)                       # fq
    p.iconst(7, 0)
    p.st(C["fxhp"], 7)
    p.st(C["fxlp"], 7)

    def hp_on():
        p.iconst(7, 1)
        p.st(C["fxhp"], 7)
        p.ld(8, C["y"])
        p.fconst(one, 10.0 / 127.0)
        p.fop(8, 8, "*", one)
        M.exp2(p, L, 8, 8)
        p.fconst(one, 20.0)
        p.fop(8, 8, "*", one)
        p.ld(6, C["tmp2"])
        M.svf_set(p, L, 4, 8, q=6)
    p.ld(4, C["y"])
    p.fconst(one, 0.5)
    p.if_(4, "GE", one, hp_on)

    def lp_on():
        p.iconst(7, 1)
        p.st(C["fxlp"], 7)
        p.ld(8, C["y"])
        p.ld(5, C["ns"])
        p.fop(8, 8, "+", 5)
        p.fconst(one, 127.0)
        p.fop(8, 8, "MIN", one)
        p.fconst(9, 0.0)
        p.fop(8, 8, "MAX", 9)
        p.fconst(one, 10.0 / 127.0)
        p.fop(8, 8, "*", one)
        M.exp2(p, L, 8, 8)
        p.fconst(one, 20.0)
        p.fop(8, 8, "*", one)
        p.ld(6, C["tmp2"])
        M.svf_set(p, L, 5, 8, q=6)
    p.ld(5, C["ns"])
    p.fconst(one, 126.5)
    p.if_(5, "LE", one, lp_on)
    # anything on? then once more through the block
    p.ld(0, C["fxam"])
    p.ld(1, C["fxeq"])
    p.iop(0, 0, "OR", 1)
    p.ld(1, C["fxhp"])
    p.iop(0, 0, "OR", 1)
    p.ld(1, C["fxlp"])
    p.iop(0, 0, "OR", 1)

    def run():
        p.ld(0, C["buf"])
        p.seti(4, 0, "the slot's buffer, again")

        def sample():
            p.ldi(0, 0, 4)
            p.st(C["fxy"], 0)

            def am():
                M.v(p, 13, "amph")
                p.ld(12, C["amdt"])
                p.fop(13, 13, "+", 12)
                M.frac(p, 13)
                M.vs(p, "amph", 13)
                M.sin_(p, L, 9, 13)
                p.fconst(12, 0.5)
                p.fop(9, 9, "*", 12)
                p.fop(9, 12, "-", 9)            # 0.5 - 0.5 sin
                p.ld(10, C["amd"])
                p.fop(9, 10, "*", 9)
                p.fconst(12, 1.0)
                p.fop(9, 12, "-", 9)
                p.ld(0, C["fxy"])
                p.fop(0, 0, "*", 9)
                p.st(C["fxy"], 0)
            p.ld(5, C["fxam"])
            p.ifz(5, "NE", am)

            def eq():
                p.ld(0, C["fxy"])
                M.svf_tick(p, L, 3)
                p.ld(12, C["eqm"])
                p.fop(2, 2, "*", 12)
                p.ld(0, C["fxy"])
                p.fop(0, 0, "+", 2)
                p.st(C["fxy"], 0)
            p.ld(5, C["fxeq"])
            p.ifz(5, "NE", eq)

            def hp():
                p.ld(0, C["fxy"])
                M.svf_tick(p, L, 4, hp=True)
                p.st(C["fxy"], 3)
            p.ld(5, C["fxhp"])
            p.ifz(5, "NE", hp)

            def lp():
                p.ld(0, C["fxy"])
                M.svf_tick(p, L, 5)
                p.st(C["fxy"], 1)
            p.ld(5, C["fxlp"])
            p.ifz(5, "NE", lp)
            p.ld(0, C["fxy"])
            p.stpost(4, 0)
        M.samples(p, L, sample)
    p.ifz(0, "NE", run)


def _shift_by(p: Prog, d: int, s: int) -> None:
    """Rd = LSHIFT Rd BY Rs."""
    p.e(f"R{d} = LSHIFT R{d} BY R{s};")
    if p.run:
        n = p.r[s] & 0xFF
        assert n < 32
        p.setR(d, p.r[d] << n)


# 2026-11-12 (perc-layout): the subroutines only events run (measured: VO-6's trig, the TRX coefficients on a knob
# change, the integer divide of P-I's and TRX-MA's knob scaling) go beside the steps that call them (dnfw.md.voice
# STEP_SPAN)
SUB_SPAN = {"trx_coefs": "perc2a", "md_idiv": "perc2a", "vo6_bqx": "perc2b"}


def program(L: M.Layout, rings_sw: int, prefix: str = "pk") -> str:
    """perc.asm: entered by the block counter's JUMP (in machine5_live's former place)."""
    return program_spans(L, rings_sw, prefix)["perc"]


def program_spans(L: M.Layout, rings_sw: int, prefix: str = "pk") -> dict[str, str]:
    """2026-11-12 (perc-layout): every span's text: "perc" (perc.asm) and the other L2 spans (perc2a.asm,
    perc2b.asm), which hold code only events run; one program, its jumps between spans 48-bit absolute."""
    p = _emit(L, rings_sw, prefix)
    out = {"perc": p.text()}
    for name, text in sorted(p.span_texts().items()):
        out[name] = (f"// {name}.asm -- PERC's code that only events run (a knob change, a note), in its own L2\n"
                     "// span (dnfw.waverider.dsp). GENERATED by scripts/gen_perc_asm.py with perc.asm; do not\n"
                     "// edit by hand.\n\n.SECTION/PM seg_pmco;\n\n" + text)
    return out


def _emit(L: M.Layout, rings_sw: int, prefix: str) -> Prog:
    p = Prog("emit", prefix=prefix)
    p.spill = L.md.C["ash"]
    p.raw("// perc.asm -- PERC, machine type 5 (docs/perc.md): the owner's Ravel PERC machines")
    p.raw("// (TRX, EFM, GND) on the DN2's DSP. GENERATED by scripts/gen_perc_asm.py from")
    p.raw("// dnfw.perc (one program for this text and its model); do not edit by hand.")
    p.raw("")
    p.raw(".SECTION/PM seg_pmco;")
    p.raw("")
    p.raw(".GLOBAL wr_perc.;")
    p.raw("wr_perc.:")
    for k, r in enumerate(SAVE_REGS):
        p.e(f"DM({SAVE + 4 * k:#x}) = {r};")
    from ..md import core as MDK
    MDK.table_fill(p, L.md)                    # the Machinedrum's sine and tables, 1024 words a block until whole (v0.24: zpack)
    if {"DPRO-DDRW", "DPRO-DENS"} & set(_mnm_types.NAMES):
        from ..mnm import dpro as MNP
        MNP.build(p, L.md.mnm)                 # v0.26: then DENS's and DDRW's Digibank stand-in, 8 words a block
    p.iconst(0, 0)
    p.st(L.C["mcost"], 0)                      # v0.26: no Monomachine voice rendered yet this block
    mnm_ages(p, L)                             # v0.29: the newest Monomachine voices first
    from . import guard as G
    G.entry(p)                                 # v0.27: the frame's length and the time our voices have
    from ..sampler import machines as SMx2
    from ..sampler.program import V as SV
    from ..waverider import dsp as DSPx
    G.perc_limit(p, [SMx2.TYPE_OF[n] for n in SMx2.ENGINED], DSPx.SMP_STATE_DM, DSPx.SMP_STATE_STRIDE,
                 SV["on"], TRIG_WORD, lambda p, d, k: half(p, d, 148, k))   # v0.49: the samples' time first
    p.iconst(0, 0)
    p.st(L.md.mnm.scratch + PERC_I, 0)
    top = p.label("slot")
    nxt = p.label("next")
    p.place(top)
    order_slot(p, L.md.mnm.scratch + PERC_I)   # v0.29: the newest first
    p.st(L.C["t"], 9)
    # 2026-11-12 (opt-host): no record pointer (I4 = 0x2554b8 + 0x234 t was set here and read by nothing: the
    # voice sets I4 to its buffer before any use), and PERC or a Monomachine machine (v0.26: PERC's voice too)
    # by one bit of VOICE_MASK, not a compare a type
    raw_type(p, 2)
    p.iconst(0, 0)
    p.iconst(12, 32)
    p.if_(2, "LT", 12, lambda: (p.iconst(13, 1), MDK._shift_r(p, 13, 13, 2), p.iconst(12, VOICE_MASK),
                                p.iop(0, 13, "AND", 12)), kind="i")
    p.ipass(0, 0)
    other = p.label("other")
    p.jump("EQ", other)
    p.ld(0, L.md.C["fill"])                   # v0.26: silent until the tables (sent by the
    p.iconst(12, MDK.Z_N)                     # ColdFire at power-on) are decoded
    p.e("COMP(R0, R12);")
    p.jump("LT", other)
    G.around(p, L.C["t"], G.COST_PERC, BUFFERS, lambda: voice(p, L),   # v0.27: if it fits in the frame
             rests=L.md.mnm.scratch + RESTS_OFF, rest_blocks=MNM_QUIET_BLOCKS,   # v0.36: else, the second
             strikes=L.md.mnm.scratch + STRIKES_OFF, steal_at=STEAL_STRIKES,       # time in a note, stolen
             limit=G.LIMIT_PERC,                                                    # v0.49: after the samples' share
             keys=L.md.mnm.scratch + MNM_KEYS_OFF)     # 2026-11-09: PLAITS' start bound, its trig block no strike
    p.jump("", nxt)
    # not PERC: its voice is silenced, so a track that comes back to PERC starts clean
    # (v0.12: v0.11 resumed what it had left ringing)
    p.place(other)
    p.ld(9, L.C["t"])
    p.lsh(12, 9, 7)
    p.iconst(11, L.state)
    p.iop(12, 11, "+", 12)
    p.seti(2, 12)
    p.iconst(0, 0)
    M.vs(p, "on", 0)
    p.place(nxt)
    p.ld(0, L.md.mnm.scratch + PERC_I)
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    p.st(L.md.mnm.scratch + PERC_I, 0)
    p.iconst(12, 16)
    p.e("COMP(R0, R12);")
    p.jump("LT", top)
    p.e(f"JUMP {rings_sw:#x};", "smp.asm's wr_smp, then PING (which restores)")
    p.emit_subs(SUB_SPAN)
    p.raw(".wr_perc..end:")
    p.raw("      .type wr_perc.,STT_FUNC;")
    return p


def run_voice(L: M.Layout, read, t: int, mem=None):
    """The model: one slot's block, on memory READ (and MEM's earlier writes, carried
    across blocks). -> (Prog, its memory)."""
    from .dsl import Mem
    mem = mem or Mem(read)
    p = Prog("run", mem=mem)
    p.spill = L.md.C["ash"]
    voice(p, L, t)
    return p, mem
