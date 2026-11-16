"""The inserts' DSP code, in the DSL (dnfw.perc.dsl Prog): emitted as SHARC assembly (inserts.asm)
and run in Python as its exact model, held bit for bit to dnfw.inserts.ref.

**Where it runs.** Our per-block chain before the stock voice chain: the block counter, PERC, the
sample machines (smp.asm), which JUMPs here (dnfw.waverider.dsp.INS_SW) instead of to PING; this
pass ends with a JUMP to PING (dnfw.waverider.dsp.PING_SW), which restores the registers the chain
saved and returns to the stock chain. So every machine has rendered into its track buffer, and the
filter, amp and pan are still to come. Like PING it uses the registers freely.

2026-11-10, two slots a track: first, when the ColdFire's change word (design.GEN) moved, the 56
packed words (design.PACK) are unpacked into TABLE (32 records x 8 words: type | instance << 4, MIX,
K1..K6), which this pass, the post pass and the bus pass read. Then for each voice slot s and insert
slot j (i = 2 s + j, slot 1 before slot 2): the track s plays, its record 2 tr + j; when that is a built
type, its state (8 words at STATE + 32 i, zeros when the type or the track changed), the insert run over
the voice's buffer in place. OFF (and a type this pass does not run) costs a load and a compare.

2026-11-11 (the User: "DSP: always run in slot order", docs/inserts.md "Slot order across the stages"): a
slot 2 under a slot 1 of design.MOVERS is left out here (skip_moved); the bus pass runs it on the track's
L and R after slot 1. The insert itself (one) is a callable at design.INS_ONE_SW, after the entry's JUMP,
so both passes run the same code.

SUB, DIST, GATER, RING (types 9..12, either slot): ported from Optimist (GPL-3.0-only, the User's own),
firmware/src/fx/insfx/insfx.c, fx.c, insfx/gater.c (dnfw.inserts.ref, docs/inserts.md). DIST shares
FUZZ's loop (fz_loop, emitted once). Each is a builder part (design.PART): left out, it is not emitted
and plays as OFF.
"""

from __future__ import annotations

import struct

from ..fdn8 import program as FP
from ..perc import guard as G
from ..perc.dsl import Mem, Prog
from . import design as D

STATE = 0x2E3000                 # L1 (perf, 2026-11-11; was L2 0x200AF400): 32 x 32 bytes of state (dnfw.waverider.dsp.INS_STATE_DM)
STATE_BYTES = D.RECORDS * 4 * D.STATE_WORDS
SCRATCH = STATE + STATE_BYTES    # the pass's own words
TABLE = D.TABLE                  # the unpacked records (design.TABLE), and the last change word seen
_NAMES = ["t", "i", "j", "rec", "w1", "sa", "buf", "gn"] + [f"p{k}" for k in range(7)] + [f"s{k}" for k in range(8)] + [
    "g", "c", "b", "y0", "k", "thr", "cnt",
    "gd", "step", "lvl", "d", "rb", "sel", "tr",
    # SUB DIST GATER RING (ports3, 2026-11-09): FUZZ's loop's values (DIST shares it), GATER's block values
    "pa", "rel", "a1", "lv", "kl", "fz", "inv", "inc", "sl", "nsl", "pat", "nx", "b1", "h0", "h1",
    "ret",                       # one's return address - 1 (2026-11-11: the bus pass calls it too)
    "aa", "au", "at",            # AUTO (design.AUTO_L2): the aux words' address, on (1.0) / off, PGAIN's gain T
    "icost", "ist", "d0", "d31",  # the gate (2026-11-12): this type's bound, its status, the dry's first and last
    "qa", "zin", "ap0", "ap1",   # quiet (2026-11-12): the mark's address, the input's OR, AUTO's powers before
    "tpg"]                       # TAPE's PGAIN (2026-11-13), the gain
C = {n: SCRATCH + 4 * k for k, n in enumerate(_NAMES)}
assert len(C) == len(_NAMES)
SCRATCH_BYTES = 4 * len(_NAMES)
# GATER's tables after the words: RATE's 1 / ticks (float32), the 16 patterns (loaded with the state)
RATE_TAB = SCRATCH + SCRATCH_BYTES
PAT_TAB = RATE_TAB + 4 * len(D.GT_RATE)
COST_TAB = PAT_TAB + 4 * len(D.GT_PAT)            # 2026-11-12: each type's guard bound (design.COST, 0 for the others)
TP_TAB = COST_TAB + 4 * len(D.NAMES)               # 2026-11-14 (insfx): TAPE's stage 2 reads these through I2
TP_CONST = (D.LCG_A, D.LCG_C, (-31) & 0xFFFFFFFF, 4)   # the LCG's multiplier and increment, its scale, a word's bytes
FZ_TAB = TP_TAB + 4 * len(TP_CONST)               # 2026-11-14 (insfx): the held loops' constants, read through I2
_K_NAMES = ("nin", "in", "zero", "one", "gk", "m1", "half", "x15", "dcr", "quarter", "fdoff", "four", "two31",
            "three", "hmdrv", "sbdn", "sbup", "sbthr", "two")
FZ_CONST = (-D.IN_MAX, D.IN_MAX, 0.0, 1.0, D.FZ_GATE_K, -1.0, 0.5, 1.5, D.FZ_DC_R, 0.25, 0.25 + D.FD_OFFSET, 4.0,
            2.0 ** 31, 3.0, D.HM_DRIVE, D.SB_DN, D.SB_UP, D.SB_THR, 2.0)
assert len(_K_NAMES) == len(FZ_CONST)
GT_CONST = (D.GT_PAIR - 1, 14)                     # GATER's integers, after FZ_CONST (the same I2; the table is full)
TABLE_WORDS = ([struct.unpack("<I", struct.pack("<f", 1.0 / d))[0] for d in D.GT_RATE] + list(D.GT_PAT)
               + [D.COST.get(t, 0) for t in range(len(D.NAMES))] + list(TP_CONST)
               + [struct.unpack("<I", struct.pack("<f", x))[0] for x in FZ_CONST] + list(GT_CONST))
assert FZ_TAB + 4 * (len(FZ_CONST) + len(GT_CONST)) <= TABLE


def state_bytes() -> bytes:
    """the state and the pass's words (zeros), GATER's tables, then the unpacked records, the last
    change word and the skip flags (zeros)"""
    head = bytes(RATE_TAB - STATE) + struct.pack(f"<{len(TABLE_WORDS)}I", *TABLE_WORDS)
    return head + bytes(D.FLAGS + 4 * D.FLAG_WORDS - STATE - len(head))


def auto_pre(p: Prog) -> None:
    """AUTO's gain this block (ref.Ref.auto_gain) in F10: 1.0 off (C['au'] 0), else C['at'] x sqrt(Pin / Pout) of the
    powers at C['aa']; F8, F9 = 0, the block's sums of squares (auto_sample). One copy, a leaf (its 1/x and sqrt
    inline: the inserts' L2 span). Clobbers R0-R5, R12, I4, I12"""
    p.call("ins_auto_pre", lambda: _auto_pre(p))


def _auto_pre(p: Prog) -> None:
    p.ld(2, C["aa"])
    p.seti(4, 2)
    p.ldi(5, 0, 4)                               # Pin
    p.ldi(0, 1, 4)                               # Pout
    p.fconst(1, D.AUTO_FLOOR)
    p.fop(5, 5, "MAX", 1)
    p.fop(0, 0, "MAX", 1)
    FP._recip(p)
    p.fop(0, 0, "*", 5)
    p.fconst(1, D.AUTO_R_MIN)
    p.fop(0, 0, "MAX", 1)
    p.fconst(1, D.AUTO_R_MAX)
    p.fop(0, 0, "MIN", 1)
    FP._sqrt(p)
    p.ld(1, C["at"])
    p.fop(10, 0, "*", 1)
    p.ld(1, C["au"])
    p.ifz(1, "EQ", lambda: p.fconst(10, 1.0), kind="f")
    p.fconst(8, 0.0)
    p.fconst(9, 0.0)


def auto_sample(p: Prog, x: int, o: int) -> None:
    """the dry F{x} and the wet F{o} into the sums (F8, F9), then the wet x AUTO's gain (F10). Clobbers F4"""
    p.fop(4, x, "*", x)
    p.fop(8, 8, "+", 4)
    p.fop(4, o, "*", o)
    p.fop(9, 9, "+", 4)
    p.fop(o, o, "*", 10)


def auto_post(p: Prog) -> None:
    """the block's sums into AUTO's powers at C['aa'] (ref.Ref.auto_end), on or off. One copy, a leaf. Clobbers
    R1-R3, R12, I4, I12"""
    p.call("ins_auto_post", lambda: _auto_post(p))


def _auto_post(p: Prog) -> None:
    p.ld(2, C["aa"])
    p.seti(4, 2)
    for k, acc in ((0, 8), (1, 9)):
        p.fconst(1, 1 / 32)
        p.fop(acc, acc, "*", 1)
        p.ldi(2, k, 4)
        p.fop(3, acc, "-", 2)
        p.fconst(1, D.AUTO_A)
        p.fop(3, 3, "*", 1)
        p.fop(2, 2, "+", 3)
        p.sti(k, 4, 2)


def auto_set(p: Prog, t: float | None) -> None:
    """C['au'] = 1.0 when the type's knob G (p6) is on, C['at'] = p5 x T (None: no AUTO, FUZZ). Clobbers R0, R1"""
    p.fconst(0, 0.0)
    if t is None:
        p.st(C["au"], 0)
        return
    p.st(C["au"], 0)
    p.ld(0, C["p6"])
    p.fconst(1, D.AUTO_ON)
    p.if_(0, "GT", 1, lambda: (p.fconst(0, 1.0), p.st(C["au"], 0)))
    p.ld(0, C["p5"])
    if t != 1.0:
        p.fconst(1, t)
        p.fop(0, 0, "*", 1)
    p.st(C["at"], 0)


def fuzz(p: Prog) -> None:
    """FUZZ's block values (ref.Ref.fuzz); fz_loop runs it. Values p0 MIX, p1..p6"""
    p.ld(0, C["p1"])
    p.fconst(1, D.FZ_DRIVE_OCT)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.st(C["g"], 0)
    p.ld(0, C["p4"])
    p.fconst(1, D.FZ_PRE_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["k"], 0)
    p.ld(0, C["p5"])
    p.fconst(1, D.FZ_GATE_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["thr"], 0)
    p.fconst(0, D.FZ_PRE_A)
    p.st(C["pa"], 0)
    p.fconst(0, D.FZ_ENV_REL)
    p.st(C["rel"], 0)
    p.fconst(0, 1.0)
    p.st(C["a1"], 0)
    p.st(C["fz"], 0)
    p.ld(0, C["p6"])
    p.st(C["lv"], 0)
    p.st(C["at"], 0)                             # AUTO's T: PGAIN (2026-11-13)
    p.fconst(0, 0.0)
    p.st(C["kl"], 0)
    p.st(C["au"], 0)
    p.ld(2, C["rec"])                            # AUTO: field 0's bit 4 (design.FZ_AUTO_BIT)
    p.seti(4, 2)
    p.ldi(1, 0, 4)
    p.iconst(12, D.FZ_AUTO_BIT)
    p.iop(1, 1, "AND", 12)
    p.ifz(1, "NE", lambda: (p.fconst(0, 1.0), p.st(C["au"], 0)))


def dist(p: Prog) -> None:
    """DIST's block values (ref.Ref.dist): the drive over the peak (s1), the low band (s0) dry"""
    p.ld(0, C["p1"])
    p.fconst(1, D.DS_DRIVE_OCT)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.DS_DRIVE_LO)
    p.fop(0, 0, "*", 1)
    p.st(C["gd"], 0)
    p.ld(0, C["s1"])
    p.fconst(1, D.DS_FLOOR)
    p.fop(0, 0, "MAX", 1)
    p.st(C["lvl"], 0)                            # the peak
    FP.recip(p)
    p.ld(1, C["gd"])
    p.fop(0, 1, "*", 0)
    p.st(C["g"], 0)
    p.ld(0, C["gd"])
    p.fconst(1, 1.0)
    p.fop(0, 0, "MIN", 1)
    p.fconst(1, 1.5)
    p.fop(0, 0, "*", 1)
    FP.recip(p)                                  # the make-up
    p.ld(1, C["p5"])
    p.fconst(2, D.DS_LEV_MAX)
    p.fop(1, 1, "*", 2)
    p.ld(2, C["lvl"])
    p.fop(1, 1, "*", 2)
    p.fop(1, 1, "*", 0)
    p.st(C["lv"], 1)
    pole_c(p, "p4", D.W_DL, D.LOG2_DL_SPAN)
    p.st(C["pa"], 0)
    p.fconst(0, 1.0)
    p.st(C["k"], 0)
    p.st(C["kl"], 0)
    p.st(C["fz"], 0)
    p.fconst(0, 0.0)
    p.st(C["thr"], 0)
    p.st(C["a1"], 0)
    p.fconst(0, D.DS_REL)
    p.st(C["rel"], 0)
    auto_set(p, D.DS_LEV_MAX)


def fz_loop(p: Prog) -> None:
    """FUZZ's and DIST's loop over the buffer at C['buf'] (ref.Ref.fz_loop): TONE p2, BIAS p3; state
    s0 lp, s1 env, s2 gg, s3 dx, s4 dy, s5 tl"""
    tone_c(p, "p2")
    p.st(C["c"], 0)
    p.ld(0, C["p3"])
    p.fconst(1, D.FZ_BIAS_MAX)
    p.fop(0, 0, "*", 1)                          # b
    p.st(C["b"], 0)
    p.fop(2, 0, "*", 0)
    p.fop(2, 2, "*", 0)
    p.fconst(1, 0.5)
    p.fop(2, 2, "*", 1)
    p.fconst(1, 1.5)
    p.fop(3, 0, "*", 1)
    p.fop(2, 3, "-", 2)
    p.st(C["y0"], 2)
    auto_pre(p)
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)
    if FZ_STAGED:
        _fz_held(p)
        return

    def one():
        p.ldpost(0, 0)                           # x
        p.fconst(1, -D.IN_MAX)
        p.fop(0, 0, "MAX", 1)
        p.fconst(1, D.IN_MAX)
        p.fop(0, 0, "MIN", 1)
        p.ld(2, C["s0"])                         # lp
        p.fop(3, 0, "-", 2)
        p.ld(1, C["pa"])
        p.fop(3, 3, "*", 1)
        p.fop(2, 2, "+", 3)
        p.st(C["s0"], 2)
        p.fop(3, 0, "-", 2)
        p.ld(1, C["k"])
        p.fop(3, 3, "*", 1)
        p.ld(1, C["a1"])
        p.fop(5, 0, "*", 1)
        p.fop(5, 5, "+", 3)                      # xe
        p.fconst(1, 0.0)
        p.fop(1, 1, "-", 0)
        p.fop(6, 0, "MAX", 1)                    # a
        p.ld(2, C["s1"])
        p.ld(1, C["rel"])
        p.fop(2, 2, "*", 1)
        p.fop(2, 6, "MAX", 2)                    # env
        p.st(C["s1"], 2)
        p.fconst(6, 1.0)                         # tg
        p.ld(3, C["thr"])
        p.fconst(1, 0.0)

        def gated():
            p.if_(2, "LE", 3, lambda: p.fconst(6, 0.0))
        p.if_(3, "GT", 1, gated)
        p.ld(2, C["s2"])
        p.fop(6, 6, "-", 2)
        p.fconst(1, D.FZ_GATE_K)
        p.fop(6, 6, "*", 1)
        p.fop(2, 2, "+", 6)
        p.st(C["s2"], 2)                         # gg
        p.ld(1, C["g"])
        p.fop(5, 5, "*", 1)
        p.ld(1, C["b"])
        p.fop(5, 5, "+", 1)
        p.fconst(1, -1.0)
        p.fop(5, 5, "MAX", 1)
        p.fconst(1, 1.0)
        p.fop(5, 5, "MIN", 1)                    # v
        p.fop(6, 5, "*", 5)
        p.fop(6, 6, "*", 5)
        p.fconst(1, 0.5)
        p.fop(6, 6, "*", 1)
        p.fconst(1, 1.5)
        p.fop(5, 5, "*", 1)
        p.fop(5, 5, "-", 6)
        p.ld(1, C["y0"])
        p.fop(5, 5, "-", 1)                      # y
        p.ld(2, C["s3"])
        p.fop(6, 5, "-", 2)
        p.ld(2, C["s4"])
        p.fconst(1, D.FZ_DC_R)
        p.fop(2, 2, "*", 1)
        p.fop(6, 6, "+", 2)                      # d
        p.st(C["s3"], 5)
        p.st(C["s4"], 6)
        p.ld(2, C["s5"])
        p.fop(3, 6, "-", 2)
        p.ld(1, C["c"])
        p.fop(3, 3, "*", 1)
        p.fop(2, 2, "+", 3)
        p.st(C["s5"], 2)                         # tl
        p.ld(1, C["lv"])
        p.fop(3, 2, "*", 1)
        p.ld(1, C["s2"])
        p.fop(3, 3, "*", 1)
        p.ld(2, C["s0"])
        p.ld(1, C["kl"])
        p.fop(2, 2, "*", 1)
        p.fop(3, 3, "+", 2)                      # (DIST: the low band back, dry)
        auto_sample(p, 0, 3)
        p.fop(3, 3, "-", 0)
        p.ld(1, C["p0"])
        p.fop(3, 3, "*", 1)
        p.fop(3, 0, "+", 3)
        p.stpost(1, 3)
    p.loop_r(11, D.BLOCK, one)
    auto_post(p)


# 2026-11-14 (insfx): fz_loop's samples with the state in registers, the constants through I2 (FZ_TAB) and the block's
# values through I3, each move placed to ride on a compute: the same operations on the same values (test_inserts'
# A/B); False: the loop as it was
FZ_STAGED = True
_FZ_I3 = "g"


def _fz_k(name: str) -> int:
    return (C[name] - C[_FZ_I3]) // 4


_FZ = {name: k for k, name in enumerate(_K_NAMES)}


def _kc(p: Prog, d: int, name: str) -> None:
    """F<d> = FZ_CONST's NAME through I2 (FZ_TAB)"""
    p.ldi(d, _FZ[name], 2)


def _kw(p: Prog, d: int, name: str) -> None:
    """R<d> = the word C[NAME] through I3 (C[_FZ_I3])"""
    p.ldi(d, _fz_k(name), 3)


def _held(p: Prog, regs, sample, auto: bool = True) -> None:
    """the held loops' frame: I2 FZ_TAB, I3 C[_FZ_I3], the state words s<k> in registers (REGS: (reg, k)), SAMPLE 32
    times, the state back, AUTO's sums (auto_post) when AUTO. I0 / I1 the buffer (set by the caller)"""
    p.iconst(4, FZ_TAB)
    p.seti(2, 4)
    p.iconst(4, C[_FZ_I3])
    p.seti(3, 4)
    for r, k in regs:
        p.ld(r, C[f"s{k}"])
    p.loop_r(11, D.BLOCK, sample, one=11)
    for r, k in regs:
        p.st(C[f"s{k}"], r)
    if auto:
        auto_post(p)


def _held_in(p: Prog, x: int = 7) -> None:
    """F<x> = x, the input held to +-IN_MAX (clamp_in's); its word C['k'] is the caller's to store"""
    p.ldpost(x, 0)
    _kc(p, 1, "nin")
    p.fop(x, x, "MAX", 1)
    _kc(p, 1, "in")
    p.fop(x, x, "MIN", 1)


def _held_dc_tone(p: Prog, y: int) -> None:
    """dc_tone_out's, held: F13 dx, F15 dy, F14 tl; the tone's coefficient C['c']. Clobbers F1 F3 F6"""
    p.fop(6, y, "-", 13)
    _kc(p, 1, "dcr")
    p.fop(15, 15, "*", 1)
    _kw(p, 1, "c")
    p.fop(15, 6, "+", 15)                        # d
    p.fpass(13, y)
    p.fop(3, 15, "-", 14)
    p.fop(3, 3, "*", 1)
    p.fop(14, 14, "+", 3)                        # tl


def _held_out(p: Prog) -> None:
    """F3 the wet, F7 x: AUTO's sums and gain (auto_sample's), the mix, out through I1"""
    p.fop(4, 7, "*", 7)
    p.fop(8, 8, "+", 4)
    _kw(p, 1, "p0")
    p.fop(4, 3, "*", 3)
    p.fop(9, 9, "+", 4)
    p.fop(3, 3, "*", 10)
    p.fop(3, 3, "-", 7)
    p.fop(3, 3, "*", 1)
    p.fop(3, 7, "+", 3)
    p.stpost(1, 3)


def _fold_sample(p: Prog) -> None:
    """FOLD's one(), held: F7 x, F13 dx (s0), F15 dy (s1), F14 tl (s2); the sine's R1-R3 R12 left to it"""
    _held_in(p)
    _kw(p, 1, "g")
    p.fop(5, 7, "*", 1)
    _kw(p, 1, "b")
    p.fop(5, 5, "+", 1)                          # v
    _kc(p, 1, "quarter")
    p.fop(5, 5, "*", 1)
    _kc(p, 1, "fdoff")
    p.fop(5, 5, "+", 1)                          # u
    p.sti(_fz_k("k"), 3, 7)                      # (x's word, on the next compute)
    p.trunc(6, 5)
    p.float0(1, 6)
    _kc(p, 2, "half")
    p.fop(5, 5, "-", 1)                          # fr
    p.sti(_fz_k("y0"), 3, 5)
    p.fop(6, 5, "-", 2)
    _kc(p, 1, "zero")
    p.fop(1, 1, "-", 6)
    _kc(p, 2, "four")
    p.fop(6, 6, "MAX", 1)
    _kc(p, 1, "one")
    p.fop(6, 6, "*", 2)
    _kc(p, 2, "two31")
    p.fop(6, 6, "-", 1)                          # tri
    p.sti(_fz_k("thr"), 3, 6)
    p.fop(0, 5, "*", 2)
    p.trunc(0, 0)
    p.lsh(0, 0, 1)
    p.iconst(1, 1 << 30)
    p.iop(0, 0, "-", 1)                          # ph
    FP.sine(p)
    p.fop(0, 0, "-", 6)
    _kw(p, 1, "p3")
    p.fop(0, 0, "*", 1)
    p.fop(5, 6, "+", 0)                          # y
    _held_dc_tone(p, 5)
    _kw(p, 1, "p5")
    p.fop(3, 14, "*", 1)
    _held_out(p)


def _ring_sample(p: Prog) -> None:
    """RING's one(), held: F7 x, R8 the phase, R9 its step; the sine's R1-R3 R12 left to it"""
    _held_in(p)
    p.sti(_fz_k("k"), 3, 7)                      # (on the next compute)
    p.ipass(0, 8)
    FP.sine(p)
    p.iop(8, 8, "+", 9)
    _kw(p, 1, "g")
    p.fop(0, 0, "*", 1)
    _kc(p, 1, "m1")
    p.fop(0, 0, "MAX", 1)
    _kc(p, 1, "one")
    p.fop(0, 0, "MIN", 1)
    p.fop(2, 1, "-", 0)
    _kw(p, 1, "p3")
    p.fop(2, 2, "*", 1)
    p.fop(0, 0, "+", 2)                          # the carrier
    p.fop(3, 7, "*", 0)
    _kw(p, 1, "p4")
    p.fop(3, 3, "*", 1)
    _kw(p, 1, "p0")
    p.fop(3, 3, "-", 7)
    p.fop(3, 3, "*", 1)
    p.fop(3, 7, "+", 3)
    p.stpost(1, 3)


def _sub_sample(p: Prog) -> None:
    """SUB's one(), held: F0 x, F12 lp (s0), F13 e (s1), F14 l1 (s2); ff, trig, ff2 (s3 s4 s5) through I3"""
    def w(d, n):
        _kw(p, d, n)

    def ws(n, r):
        p.sti(_fz_k(n), 3, r)

    def fire():
        w(7, "s3")
        p.fconst(1, 1.0)
        p.fop(7, 1, "-", 7)
        ws("s3", 7)
        ws("s4", 1)

        def second():
            w(7, "s5")
            p.fconst(1, 1.0)
            p.fop(7, 1, "-", 7)
            ws("s5", 7)
        p.fconst(1, 0.5)
        p.if_(7, "GT", 1, second)

    def rearm():
        p.fconst(1, 0.0)
        p.fop(1, 1, "-", 5)

        def armed():
            p.fconst(1, 0.0)
            ws("s4", 1)
        p.if_(12, "LT", 1, armed)
    _held_in(p, 0)
    w(1, "g")
    p.fop(3, 0, "-", 12)
    ws("k", 0)
    p.fop(3, 3, "*", 1)
    _kc(p, 1, "zero")
    p.fop(12, 12, "+", 3)                        # lp
    p.fop(1, 1, "-", 12)
    _kc(p, 6, "sbdn")
    p.fop(3, 12, "MAX", 1)                       # |lp|
    p.fop(5, 3, "-", 13)
    _kc(p, 1, "sbup")
    p.if_(3, "GT", 13, lambda: p.fpass(6, 1))
    p.fop(5, 5, "*", 6)
    _kc(p, 1, "sbthr")
    p.fop(13, 13, "+", 5)                        # e
    w(6, "s4")
    p.fop(5, 13, "*", 1)                         # th
    p.ifz(6, "EQ", lambda: p.if_(12, "GT", 5, fire), rearm, kind="f")
    w(6, "s3")
    w(7, "s5")
    p.fop(7, 7, "-", 6)
    w(1, "b")
    p.fop(7, 7, "*", 1)
    _kc(p, 1, "two")
    p.fop(7, 6, "+", 7)
    p.fop(7, 7, "*", 1)
    _kc(p, 1, "one")
    p.fop(7, 7, "-", 1)
    w(1, "c")
    p.fop(7, 13, "*", 7)                         # the square at e
    p.fop(7, 7, "-", 14)
    p.fop(7, 7, "*", 1)
    w(1, "p5")
    p.fop(14, 14, "+", 7)                        # rounded
    p.fop(3, 0, "*", 1)
    w(1, "p1")
    p.fop(2, 14, "*", 1)
    w(1, "p0")
    p.fop(3, 3, "+", 2)
    p.fop(3, 3, "-", 0)
    p.fop(3, 3, "*", 1)
    p.fop(3, 0, "+", 3)
    p.stpost(1, 3)


_GT = {name: len(FZ_CONST) + k for k, name in enumerate(("pairm1", "k14"))}


def _gater_sample(p: Prog) -> None:
    """GATER's one(), its block values through I3 and its constants through I2: F0 x, R8 the phase, R9 its step, F5
    the closure, R13 the pattern, R14 its open bits (as one() keeps them)"""
    def g(d, name):
        p.ldi(d, _GT[name], 2)
    _held_in(p, 0)
    g(12, "pairm1")
    p.sti(_fz_k("k"), 3, 0)                      # (on the next compute)
    p.iop(1, 8, "AND", 12)                       # q
    g(12, "k14")
    p.lsh(2, 8, -28)
    p.iop(2, 2, "AND", 12)                       # k
    _kw(p, 3, "b1")

    def first():
        _kw(p, 6, "h0")
        p.ipass(7, 3)

    def second():
        p.iconst(12, 1)
        p.iop(2, 12, "+", 2)
        _kw(p, 6, "h1")
        p.iconst(7, D.GT_PAIR)
    p.if_(1, "LT", 3, first, second, kind="i")
    p.iconst(3, 1)
    p.float_(3, 3, 2)
    p.trunc(3, 3)                                # 1 << k
    p.iop(4, 14, "AND", 3)
    p.ifz(4, "EQ", lambda: p.ipass(6, 7))        # the next step closed: open to this one's end
    _kw(p, 4, "p1")
    p.iop(10, 13, "AND", 3)
    p.ifz(10, "NE", lambda: p.if_(1, "LT", 6, lambda: p.fconst(4, 0.0), kind="i"))
    _kw(p, 1, "sl")
    p.fop(4, 4, "-", 5)
    p.fop(4, 4, "MIN", 1)
    _kw(p, 1, "nsl")
    p.fop(4, 4, "MAX", 1)
    _kc(p, 1, "one")
    p.fop(5, 5, "+", 4)                          # the closure
    p.fop(1, 1, "-", 5)
    _kw(p, 2, "p0")
    p.fop(1, 0, "*", 1)
    p.fop(1, 1, "-", 0)
    p.fop(1, 1, "*", 2)
    p.fop(1, 0, "+", 1)
    p.stpost(1, 1)
    p.iop(8, 8, "+", 9)


def _harm_sample(p: Prog) -> None:
    """HARM's one(), held: F7 x, F12 lp (s0), F13 dx (s1), F15 dy (s2), F14 tl (s3)"""
    _held_in(p)
    _kw(p, 1, "g")
    p.fop(3, 7, "-", 12)
    p.sti(_fz_k("k"), 3, 7)
    p.fop(3, 3, "*", 1)
    _kc(p, 1, "hmdrv")
    p.fop(12, 12, "+", 3)                        # lp
    p.fop(5, 7, "-", 12)
    _kc(p, 2, "m1")
    p.fop(5, 5, "*", 1)
    _kc(p, 1, "one")
    p.fop(5, 5, "MAX", 2)
    _kc(p, 2, "four")
    p.fop(5, 5, "MIN", 1)                        # bnd
    _kc(p, 1, "three")
    p.fop(6, 5, "*", 5)                          # e
    p.fop(4, 6, "*", 5)
    p.fop(4, 4, "*", 2)
    p.fop(3, 5, "*", 1)
    _kw(p, 1, "p3")
    p.fop(4, 4, "-", 3)                          # o
    p.fop(6, 6, "-", 4)
    p.fop(6, 6, "*", 1)
    p.fop(5, 4, "+", 6)                          # h
    _held_dc_tone(p, 5)
    _kw(p, 1, "b")
    p.fop(3, 14, "*", 1)
    _kw(p, 1, "p5")
    p.fop(3, 7, "+", 3)
    p.fop(3, 3, "*", 1)
    _held_out(p)


def _fz_held(p: Prog) -> None:
    """fz_loop's loop: F7 lp (s0), F12 env (s1), F13 gg (s2), F14 dx (s3), F15 dy (s4); tl (s5) through I3; F8 F9 F10
    AUTO's (auto_pre's); I0 / I1 the buffer"""
    p.iconst(4, FZ_TAB)
    p.seti(2, 4)
    p.iconst(4, C[_FZ_I3])
    p.seti(3, 4)
    for r, k in ((7, 0), (12, 1), (13, 2), (14, 3), (15, 4)):
        p.ld(r, C[f"s{k}"])
    p.loop_r(11, D.BLOCK, lambda: _fz_sample(p), one=11)
    for r, k in ((7, 0), (12, 1), (13, 2), (14, 3), (15, 4)):
        p.st(C[f"s{k}"], r)
    auto_post(p)


def _fz_sample(p: Prog) -> None:
    def c(d, name):
        p.ldi(d, _FZ[name], 2)

    def w(d, name):
        p.ldi(d, _fz_k(name), 3)
    p.ldpost(0, 0)                               # x
    c(1, "nin")
    p.fop(0, 0, "MAX", 1)
    c(1, "in")
    p.fop(0, 0, "MIN", 1)
    w(1, "pa")
    p.fop(3, 0, "-", 7)
    p.fop(3, 3, "*", 1)
    w(1, "k")
    p.fop(7, 7, "+", 3)                          # lp
    w(2, "a1")
    p.fop(3, 0, "-", 7)
    c(6, "zero")
    p.fop(3, 3, "*", 1)
    w(1, "rel")
    p.fop(5, 0, "*", 2)
    p.fop(5, 5, "+", 3)                          # xe
    p.fop(2, 6, "-", 0)
    w(3, "thr")
    p.fop(6, 0, "MAX", 2)                        # a
    p.fop(12, 12, "*", 1)
    c(1, "zero")
    p.fop(12, 6, "MAX", 12)                      # env
    c(6, "one")                                  # tg

    def gated():
        p.if_(12, "LE", 3, lambda: p.fconst(6, 0.0))
    p.if_(3, "GT", 1, gated)
    p.fop(6, 6, "-", 13)
    c(1, "gk")
    p.fop(6, 6, "*", 1)
    w(1, "g")
    p.fop(13, 13, "+", 6)                        # gg
    w(2, "b")
    p.fop(5, 5, "*", 1)
    c(1, "m1")
    p.fop(5, 5, "+", 2)
    c(2, "one")
    p.fop(5, 5, "MAX", 1)
    c(1, "half")
    p.fop(5, 5, "MIN", 2)                        # v
    c(2, "x15")
    p.fop(6, 5, "*", 5)
    p.fop(6, 6, "*", 5)
    p.fop(6, 6, "*", 1)
    w(1, "y0")
    p.fop(5, 5, "*", 2)
    c(2, "dcr")
    p.fop(5, 5, "-", 6)
    p.fop(5, 5, "-", 1)                          # y
    p.fop(6, 5, "-", 14)
    p.fop(15, 15, "*", 2)
    w(2, "s5")                                   # tl
    p.fop(15, 6, "+", 15)                        # d (dy)
    p.fpass(14, 5)                               # dx
    w(1, "c")
    p.fop(3, 15, "-", 2)
    p.fop(3, 3, "*", 1)
    w(1, "lv")
    p.fop(2, 2, "+", 3)
    p.sti(_fz_k("s5"), 3, 2)                     # (rides on the next compute)
    p.fop(3, 2, "*", 1)
    p.fop(3, 3, "*", 13)
    w(1, "kl")
    p.fop(2, 7, "*", 1)
    p.fop(3, 3, "+", 2)                          # (DIST: the low band back, dry)
    p.fop(4, 0, "*", 0)                          # auto_sample's, inline
    p.fop(8, 8, "+", 4)
    w(1, "p0")
    p.fop(4, 3, "*", 3)
    p.fop(9, 9, "+", 4)
    p.fop(3, 3, "*", 10)
    p.fop(3, 3, "-", 0)
    p.fop(3, 3, "*", 1)
    p.fop(3, 0, "+", 3)
    p.stpost(1, 3)


def tape(p: Prog) -> None:
    """TAPE over the buffer at C['buf'] (ref.Ref.tape); state s0 lp, s1 s2 phases, s3 d1, s4 seed, s5 wp"""
    p.ld(0, C["p1"])
    p.fconst(1, D.TP_DRIVE_OCT)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.st(C["gd"], 0)
    p.ld(0, C["p2"])
    p.fconst(1, D.TP_WOW_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["g"], 0)                              # wd
    p.ld(0, C["p4"])
    p.fconst(1, D.TP_FLUT_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["b"], 0)                              # fd
    p.ld(0, C["p3"])
    p.fconst(1, D.LOG2_WRAT_SPAN)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.TP_WRAT_LO * D.PH_PER_HZ)
    p.fop(0, 0, "*", 1)
    p.trunc(0, 0)                                # inc
    p.ld(8, C["s1"])
    p.iop(8, 8, "+", 0)
    p.st(C["s1"], 8)                             # phw
    p.ld(8, C["s2"])
    p.iconst(9, D.TP_FLUT_INC)
    p.iop(8, 8, "+", 9)
    p.st(C["s2"], 8)                             # phf
    p.ld(0, C["s1"])
    FP.sine(p)
    p.ld(1, C["g"])
    p.fop(0, 0, "*", 1)
    p.st(C["y0"], 0)
    p.ld(0, C["s2"])
    FP.sine(p)
    p.ld(1, C["b"])
    p.fop(0, 0, "*", 1)
    p.ld(1, C["y0"])
    p.fop(0, 1, "+", 0)
    p.fconst(1, D.TP_D0)
    p.fop(0, 0, "+", 1)                          # d1
    p.ld(2, C["s3"])                             # d0
    p.fconst(3, 0.0)
    p.if_(2, "EQ", 3, lambda: p.fpass(2, 0))
    p.st(C["d"], 2)
    p.st(C["s3"], 0)
    p.fop(0, 0, "-", 2)
    p.fconst(1, 1 / D.BLOCK)
    p.fop(0, 0, "*", 1)
    p.st(C["step"], 0)
    p.ld(0, C["p5"])
    p.fconst(1, -3.0)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.W_AGE)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 0)
    p.st(C["c"], 0)
    p.ld(0, C["p6"])
    p.fop(0, 0, "*", 0)
    p.fconst(1, D.TP_HISS_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["lvl"], 0)                            # (the ring: C['rb'], the caller's)
    if TAPE_STAGED:
        _tape_staged(p)
        return
    tape_pgain(p)
    auto_pre(p)                                  # AUTO's sums and gain in F13, F14, F15 here (the loop uses R4, R8, R9)
    p.fpass(13, 8)
    p.fpass(14, 9)
    p.fpass(15, 10)
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)

    def ring_at(idx):                            # I4 = the ring's word R{idx} (masked here)
        p.iconst(12, D.TP_RING - 1)
        p.iop(idx, idx, "AND", 12)
        p.lsh(idx, idx, 2)
        p.ld(12, C["rb"])
        p.iop(idx, 12, "+", idx)
        p.seti(4, idx)

    def one():
        p.ldpost(0, 0)
        p.fconst(1, -D.IN_MAX)
        p.fop(0, 0, "MAX", 1)
        p.fconst(1, D.IN_MAX)
        p.fop(0, 0, "MIN", 1)
        p.st(C["k"], 0)                          # x
        p.ld(1, C["gd"])
        p.fop(5, 0, "*", 1)
        p.fconst(1, -D.TP_SAT_MAX)
        p.fop(5, 5, "MAX", 1)
        p.fconst(1, D.TP_SAT_MAX)
        p.fop(5, 5, "MIN", 1)                    # xs
        p.fop(6, 5, "*", 5)                      # t2
        p.fconst(1, 27.0)
        p.fop(7, 6, "+", 1)
        p.fop(7, 7, "*", 5)                      # num
        p.fconst(1, 9.0)
        p.fop(0, 6, "*", 1)
        p.fconst(1, 27.0)
        p.fop(0, 0, "+", 1)                      # den
        FP.recip(p)
        p.fop(7, 7, "*", 0)                      # y
        p.ld(8, C["s5"])
        p.iconst(12, 1)
        p.iop(8, 12, "+", 8)
        p.iconst(12, D.TP_RING - 1)
        p.iop(8, 8, "AND", 12)
        p.st(C["s5"], 8)                         # wp
        p.ipass(9, 8)
        ring_at(9)
        p.sti(0, 4, 7)
        p.ld(0, C["d"])
        p.ld(1, C["step"])
        p.fop(0, 0, "+", 1)
        p.st(C["d"], 0)
        p.trunc(5, 0)                            # i
        p.iconst(1, 0)
        p.float_(1, 5, 1)
        p.fop(6, 0, "-", 1)                      # fr
        p.ld(8, C["s5"])
        p.iop(9, 8, "-", 5)
        ring_at(9)
        p.ldi(2, 0, 4)                           # y0
        p.ld(8, C["s5"])
        p.iop(9, 8, "-", 5)
        p.iconst(12, 1)
        p.iop(9, 9, "-", 12)
        ring_at(9)
        p.ldi(3, 0, 4)                           # y1
        p.fop(3, 3, "-", 2)
        p.fop(3, 3, "*", 6)
        p.fop(2, 2, "+", 3)                      # r
        p.ld(1, C["s0"])
        p.fop(3, 2, "-", 1)
        p.ld(4, C["c"])
        p.fop(3, 3, "*", 4)
        p.fop(1, 1, "+", 3)
        p.st(C["s0"], 1)                         # lp
        p.ld(8, C["s4"])
        p.iconst(9, D.LCG_A)
        p.mul_ssi(8, 8, 9)
        p.iconst(9, D.LCG_C)
        p.iop(8, 8, "+", 9)
        p.st(C["s4"], 8)                         # seed
        p.iconst(9, -31)
        p.float_(2, 8, 9)
        p.ld(3, C["lvl"])
        p.fop(2, 2, "*", 3)                      # n
        p.fop(2, 1, "+", 2)                      # o = lp + n
        p.ld(3, C["tpg"])
        p.fop(2, 2, "*", 3)                      # x PGAIN
        p.ld(0, C["k"])
        p.fop(3, 0, "*", 0)                      # AUTO's sums, its gain (auto_sample's, in F13-F15)
        p.fop(13, 13, "+", 3)
        p.fop(3, 2, "*", 2)
        p.fop(14, 14, "+", 3)
        p.fop(2, 2, "*", 15)
        p.fop(2, 2, "-", 0)
        p.ld(3, C["p0"])
        p.fop(2, 2, "*", 3)
        p.fop(2, 0, "+", 2)
        p.stpost(1, 2)
    p.loop_r(11, D.BLOCK, one)
    p.fpass(8, 13)
    p.fpass(9, 14)
    auto_post(p)


# 2026-11-14 (insfx): TAPE's samples in two stages (_tape_staged), the same operations on the same values as the sample
# loop, bit for bit (test_inserts' A/B); False: the sample loop
TAPE_STAGED = True
# the stage-2 loop's values ride on its computes as DM(k, I3) (I3 = C['lv'], 2026-11-14: c lvl p0 tpg in reach) and
# DM(k, I2) (I2 = TP_TAB)
_TP_I3 = "lv"


def _tp_k(name: str) -> int:
    return (C[name] - C[_TP_I3]) // 4


def _tape_staged(p: Prog) -> None:
    """stage 1, over the block: x held to +-IN_MAX (back into the buffer: stage 2's dry), the Pade tanh, into the ring
    (wp + 1 .. wp + 32, split where it wraps); stage 2: the delay's read (at least 44 samples back: never a word stage 1
    just wrote), the age one-pole, the hiss, PGAIN, AUTO, the mix. The state's words s0 s4 s5 and C['d'] are left as
    the sample loop leaves them; C['k'] (the last x there) and C['thr'] (here the first segment's count) are the
    block's scratch"""
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)
    p.ld(0, C["s5"])                             # the first write place, wp + 1
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    p.iconst(12, D.TP_RING - 1)
    p.iop(0, 0, "AND", 12)
    p.lsh(2, 0, 2)
    p.ld(12, C["rb"])
    p.iop(2, 12, "+", 2)
    p.seti(2, 2)
    p.iconst(12, D.TP_RING)
    p.iop(11, 12, "-", 0)                        # the words before the ring's end
    p.iconst(12, D.BLOCK)
    p.iop(11, 11, "MIN", 12)
    p.st(C["thr"], 11)                           # (the walk counts in C["cnt"])
    for r, v in ((4, -D.IN_MAX), (5, D.IN_MAX), (7, -D.TP_SAT_MAX), (8, D.TP_SAT_MAX), (9, 27.0), (10, 9.0),
                 (13, 2.0)):
        p.fconst(r, v)
    p.ld(6, C["gd"])
    p.iconst(14, FP.R.RECIP_MAGIC)

    def sat():
        p.call("tp_sat", lambda: p.loop_r(11, None, lambda: _tape_sat(p), one=11))
    sat()
    p.ld(0, C["thr"])
    p.iconst(12, D.BLOCK)
    p.iop(11, 12, "-", 0)

    def wrapped():
        p.ld(2, C["rb"])
        p.seti(2, 2)
        sat()
    p.ifz(11, "NE", wrapped)
    tape_pgain(p)
    auto_pre(p)                                  # (its sums and gain stay in F8, F9, F10)
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)
    p.iconst(4, TP_TAB)
    p.seti(2, 4)
    p.iconst(4, C[_TP_I3])
    p.seti(3, 4)
    p.ld(5, C["d"])
    p.ld(6, C["step"])
    p.ld(7, C["s0"])
    p.ld(13, C["s4"])
    p.ld(14, C["s5"])
    p.lsh(14, 14, 2)
    p.ld(15, C["rb"])
    p.iconst(12, 4 * (D.TP_RING - 1))
    p.loop_r(11, D.BLOCK, lambda: _tape_read(p), one=11)
    p.st(C["d"], 5)
    p.st(C["s0"], 7)
    p.st(C["s4"], 13)
    p.lsh(14, 14, -2)
    p.iconst(12, D.TP_RING - 1)
    p.iop(14, 14, "AND", 12)
    p.st(C["s5"], 14)
    auto_post(p)


def _tape_sat(p: Prog) -> None:
    """stage 1, one sample: F4 / F5 -+IN_MAX, F6 gd, F7 / F8 -+SAT_MAX, F9 27, F10 9, F13 2, R14 recip's magic; x back to
    the buffer (I1), y into the ring (I2)"""
    p.ldpost(0, 0)
    p.fop(0, 0, "MAX", 4)
    p.fop(0, 0, "MIN", 5)                        # x
    p.stpost(1, 0)
    p.fop(1, 0, "*", 6)
    p.fop(1, 1, "MAX", 7)
    p.fop(1, 1, "MIN", 8)                        # xs
    p.fop(0, 1, "*", 1)                          # t2
    p.fop(2, 0, "+", 9)
    p.fop(2, 2, "*", 1)                          # num
    p.fop(1, 0, "*", 10)
    p.fop(1, 1, "+", 9)                          # den
    p.iop(0, 14, "-", 1)                         # 1 / den: the bit guess, then Newton (fdn8.program._recip)
    for _ in range(FP.R.NEWTON):
        p.fop(3, 1, "*", 0)
        p.fop(3, 13, "-", 3)
        p.fop(0, 0, "*", 3)
    p.fop(2, 2, "*", 0)                          # y
    p.stpost(2, 2)


def _tape_read(p: Prog) -> None:
    """stage 2, one sample: F5 d, F6 step, F7 lp, R13 seed, R14 4 wp (unmasked), R15 the ring, R12 its byte mask; I3 at
    C['lv'] (c lvl p0 tpg), I2 at TP_TAB; F8 F9 the sums, F10 AUTO's gain (auto_pre's); the dry x at I0, the out to I1"""
    p.fop(5, 5, "+", 6)                          # d
    p.trunc(0, 5)                                # i
    p.float0(1, 0)
    p.fop(1, 5, "-", 1)                          # fr
    p.lsh(0, 0, 2)
    p.ldi(4, 3, 2)                    # 4
    p.iop(14, 14, "+", 4)                        # wp
    p.iop(2, 14, "-", 0)
    p.iop(3, 2, "AND", 12)
    p.iop(3, 3, "OR", 15)
    p.seti(4, 3)
    p.iop(2, 2, "-", 4)
    p.ldi(3, 0, 4)                               # y0
    p.iop(2, 2, "AND", 12)
    p.iop(2, 2, "OR", 15)
    p.seti(4, 2)
    p.ldi(2, 0, 4)                               # y1
    p.fop(2, 2, "-", 3)
    p.fop(2, 2, "*", 1)
    p.fop(3, 3, "+", 2)                          # r
    p.ldi(4, _tp_k("c"), 3)
    p.fop(3, 3, "-", 7)
    p.fop(3, 3, "*", 4)
    p.ldi(4, 0, 2)                      # the LCG's multiplier
    p.fop(7, 7, "+", 3)                          # lp
    p.mul_ssi(13, 13, 4)
    p.ldi(4, 1, 2)
    p.iop(13, 13, "+", 4)                        # seed
    p.ldi(4, 2, 2)
    p.float_(2, 13, 4)
    p.ldi(4, _tp_k("lvl"), 3)
    p.fop(2, 2, "*", 4)                          # n
    p.ldi(4, _tp_k("tpg"), 3)                    # PGAIN's gain
    p.fop(2, 7, "+", 2)                          # o
    p.ldpost(0, 0)                               # x
    p.fop(2, 2, "*", 4)
    p.fop(3, 0, "*", 0)
    p.fop(8, 8, "+", 3)
    p.fop(3, 2, "*", 2)
    p.ldi(4, _tp_k("p0"), 3)
    p.fop(9, 9, "+", 3)
    p.fop(2, 2, "*", 10)
    p.fop(2, 2, "-", 0)
    p.fop(2, 2, "*", 4)
    p.fop(2, 0, "+", 2)
    p.stpost(1, 2)


def tape_pgain(p: Prog) -> None:
    """TAPE's PGAIN and AUTO (2026-11-13; ref.Ref.tape): C['tpg'] = 2^(dB / 6.02) of its record's byte at
    design.TP_PG_DDR (7-bit two's complement; 0: exactly 1.0), C['at'] the same (AUTO's T), C['au'] field 0's bit 4.
    Clobbers R0-R3, R12, I4"""
    p.ld(2, C["rec"])
    p.iconst(12, (-TABLE) & 0xFFFFFFFF)
    p.iop(1, 12, "+", 2)
    p.lsh(1, 1, -5)                              # the record i
    p.lsh(3, 1, -2)
    p.lsh(3, 3, 2)
    p.iconst(12, D.TP_PG_DDR)
    p.iop(3, 12, "+", 3)
    p.seti(4, 3)
    p.ldi(0, 0, 4)                               # its word
    p.iconst(12, 2)
    p.iop(2, 1, "AND", 12)
    p.ifz(2, "NE", lambda: p.lsh(0, 0, -16))
    p.iconst(12, 1)
    p.iop(2, 1, "AND", 12)
    p.ifz(2, "NE", lambda: p.lsh(0, 0, -8))
    p.iconst(12, 0x7F)
    p.iop(0, 0, "AND", 12)                       # the byte
    p.fconst(1, 1.0)
    p.st(C["tpg"], 1)

    def gain():
        p.iconst(12, 64)
        p.if_(0, "GE", 12, lambda: (p.iconst(12, -128), p.iop(0, 12, "+", 0)), kind="i")
        p.iconst(1, 0)
        p.float_(0, 0, 1)
        p.fconst(1, D.TP_PG_DB)
        p.fop(0, 0, "*", 1)
        FP.exp2(p)
        p.st(C["tpg"], 0)
    p.ifz(0, "NE", gain)
    p.ld(0, C["tpg"])
    p.st(C["at"], 0)
    p.fconst(0, 0.0)
    p.st(C["au"], 0)
    p.ld(2, C["rec"])
    p.seti(4, 2)
    p.ldi(1, 0, 4)
    p.iconst(12, D.FZ_AUTO_BIT)
    p.iop(1, 1, "AND", 12)
    p.ifz(1, "NE", lambda: (p.fconst(0, 1.0), p.st(C["au"], 0)))


def pole_c(p: Prog, src: str, w: float, l2: float) -> None:
    """F0 = a one-pole's coefficient at f_lo x span^C[src] (ref.Ref.pole_c)"""
    p.ld(0, C[src])
    p.fconst(1, l2)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, w)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 0)


def tone_c(p: Prog, src: str) -> None:
    """F0 = a one-pole's coefficient at 300 Hz x 40^C[src] (ref.Ref.tone_c)"""
    pole_c(p, src, D.W_TONE, D.LOG2_TONE_SPAN)


def clamp_in(p: Prog) -> None:
    p.ldpost(0, 0)
    p.fconst(1, -D.IN_MAX)
    p.fop(0, 0, "MAX", 1)
    p.fconst(1, D.IN_MAX)
    p.fop(0, 0, "MIN", 1)
    p.st(C["k"], 0)                              # x


def dc_tone_out(p: Prog, y: int, sx: str, sy: str, st: str) -> None:
    """the DC blocker on F{y} (state sx, sy), the tone one-pole (st, coefficient C['c']); leaves F2 = tl"""
    p.ld(2, C[sx])
    p.fop(6, y, "-", 2)
    p.ld(2, C[sy])
    p.fconst(1, D.FZ_DC_R)
    p.fop(2, 2, "*", 1)
    p.fop(6, 6, "+", 2)                          # d
    p.st(C[sx], y)
    p.st(C[sy], 6)
    p.ld(2, C[st])
    p.fop(3, 6, "-", 2)
    p.ld(1, C["c"])
    p.fop(3, 3, "*", 1)
    p.fop(2, 2, "+", 3)
    p.st(C[st], 2)


def fold(p: Prog) -> None:
    """FOLD (ref.Ref.fold); values p0 MIX, p1 AMNT, p2 SYMM, p3 SHPE, p4 TONE, p5 LEV; s0 dx s1 dy s2 tl"""
    p.ld(0, C["p1"])
    p.fconst(1, D.FD_GAIN_OCT)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.st(C["g"], 0)
    p.ld(0, C["p2"])
    p.fconst(1, 0.5)
    p.fop(0, 0, "-", 1)
    p.fconst(1, 2 * D.FD_BIAS_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["b"], 0)
    tone_c(p, "p4")
    p.st(C["c"], 0)
    auto_set(p, 1.0)
    auto_pre(p)
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)

    if FZ_STAGED:
        _held(p, ((13, 0), (15, 1), (14, 2)), lambda: _fold_sample(p))
        return

    def one():
        clamp_in(p)
        p.ld(1, C["g"])
        p.fop(5, 0, "*", 1)
        p.ld(1, C["b"])
        p.fop(5, 5, "+", 1)                      # v
        p.fconst(1, 0.25)
        p.fop(5, 5, "*", 1)
        p.fconst(1, 0.25 + D.FD_OFFSET)
        p.fop(5, 5, "+", 1)                      # u
        p.trunc(6, 5)
        p.iconst(1, 0)
        p.float_(1, 6, 1)
        p.fop(5, 5, "-", 1)                      # fr
        p.st(C["y0"], 5)
        p.fconst(1, 0.5)
        p.fop(6, 5, "-", 1)
        p.fconst(1, 0.0)
        p.fop(1, 1, "-", 6)
        p.fop(6, 6, "MAX", 1)
        p.fconst(1, 4.0)
        p.fop(6, 6, "*", 1)
        p.fconst(1, 1.0)
        p.fop(6, 6, "-", 1)                      # tri
        p.st(C["thr"], 6)
        p.fconst(1, 2.0 ** 31)
        p.fop(0, 5, "*", 1)
        p.trunc(0, 0)
        p.lsh(0, 0, 1)
        p.iconst(1, 1 << 30)
        p.iop(0, 0, "-", 1)                      # ph
        FP.sine(p)
        p.ld(6, C["thr"])
        p.fop(0, 0, "-", 6)
        p.ld(1, C["p3"])
        p.fop(0, 0, "*", 1)
        p.fop(5, 6, "+", 0)                      # y
        dc_tone_out(p, 5, "s0", "s1", "s2")
        p.ld(1, C["p5"])
        p.fop(3, 2, "*", 1)
        p.ld(0, C["k"])
        auto_sample(p, 0, 3)
        p.fop(3, 3, "-", 0)
        p.ld(1, C["p0"])
        p.fop(3, 3, "*", 1)
        p.fop(3, 0, "+", 3)
        p.stpost(1, 3)
    p.loop_r(11, D.BLOCK, one)
    auto_post(p)


def harm(p: Prog) -> None:
    """HARM (ref.Ref.harm); p1 AMNT, p2 FREQ, p3 EVEN, p4 TONE, p5 LEV; s0 lp s1 dx s2 dy s3 tl"""
    p.ld(0, C["p2"])
    p.fconst(1, D.LOG2_HM_SPAN)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.W_HM)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 0)
    p.st(C["g"], 0)                              # a
    tone_c(p, "p4")
    p.st(C["c"], 0)
    p.ld(0, C["p1"])
    p.fconst(1, D.HM_AMNT_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["b"], 0)                              # k
    auto_set(p, 1.0)
    auto_pre(p)
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)

    if FZ_STAGED:
        _held(p, ((12, 0), (13, 1), (15, 2), (14, 3)), lambda: _harm_sample(p))
        return

    def one():
        clamp_in(p)
        p.ld(2, C["s0"])
        p.fop(3, 0, "-", 2)
        p.ld(1, C["g"])
        p.fop(3, 3, "*", 1)
        p.fop(2, 2, "+", 3)
        p.st(C["s0"], 2)                         # lp
        p.fop(5, 0, "-", 2)
        p.fconst(1, D.HM_DRIVE)
        p.fop(5, 5, "*", 1)
        p.fconst(1, -1.0)
        p.fop(5, 5, "MAX", 1)
        p.fconst(1, 1.0)
        p.fop(5, 5, "MIN", 1)                    # bnd
        p.fop(6, 5, "*", 5)                      # e
        p.fop(7, 6, "*", 5)
        p.fconst(1, 4.0)
        p.fop(7, 7, "*", 1)
        p.fconst(1, 3.0)
        p.fop(3, 5, "*", 1)
        p.fop(7, 7, "-", 3)                      # o
        p.fop(6, 6, "-", 7)
        p.ld(1, C["p3"])
        p.fop(6, 6, "*", 1)
        p.fop(5, 7, "+", 6)                      # h
        dc_tone_out(p, 5, "s1", "s2", "s3")
        p.ld(1, C["b"])
        p.fop(3, 2, "*", 1)
        p.ld(0, C["k"])
        p.fop(3, 0, "+", 3)
        p.ld(1, C["p5"])
        p.fop(3, 3, "*", 1)
        auto_sample(p, 0, 3)
        p.fop(3, 3, "-", 0)
        p.ld(1, C["p0"])
        p.fop(3, 3, "*", 1)
        p.fop(3, 0, "+", 3)
        p.stpost(1, 3)
    p.loop_r(11, D.BLOCK, one)
    auto_post(p)


def sub(p: Prog) -> None:
    """SUB (ref.Ref.sub); p1 LEV, p2 BAND, p3 TONE, p4 OCT, p5 DRY; s0 lp, s1 e, s2 l1, s3 ff, s4 trig, s5 ff2"""
    pole_c(p, "p2", D.W_SB, D.LOG2_SB_SPAN)
    p.st(C["g"], 0)
    pole_c(p, "p3", D.W_ST, D.LOG2_ST_SPAN)
    p.st(C["c"], 0)
    p.ld(0, C["p4"])
    p.fconst(1, 0.5)
    p.fconst(2, 0.0)
    p.if_(0, "GE", 1, lambda: p.fconst(2, 1.0))
    p.st(C["b"], 2)                              # two octaves down
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)

    if FZ_STAGED:
        _held(p, ((12, 0), (13, 1), (14, 2)), lambda: _sub_sample(p), auto=False)
        return

    def fire():                                  # a rising crossing: the flip-flop turns, the trigger fires
        p.ld(7, C["s3"])
        p.fconst(1, 1.0)
        p.fop(7, 1, "-", 7)
        p.st(C["s3"], 7)
        p.st(C["s4"], 1)

        def second():
            p.ld(7, C["s5"])
            p.fconst(1, 1.0)
            p.fop(7, 1, "-", 7)
            p.st(C["s5"], 7)
        p.fconst(1, 0.5)
        p.if_(7, "GT", 1, second)

    def rearm():
        p.fconst(1, 0.0)
        p.fop(1, 1, "-", 5)

        def armed():
            p.fconst(1, 0.0)
            p.st(C["s4"], 1)
        p.if_(2, "LT", 1, armed)

    def one():
        clamp_in(p)
        p.ld(2, C["s0"])
        p.fop(3, 0, "-", 2)
        p.ld(1, C["g"])
        p.fop(3, 3, "*", 1)
        p.fop(2, 2, "+", 3)
        p.st(C["s0"], 2)                         # lp
        p.fconst(1, 0.0)
        p.fop(1, 1, "-", 2)
        p.fop(3, 2, "MAX", 1)                    # |lp|
        p.ld(4, C["s1"])
        p.fop(5, 3, "-", 4)
        p.fconst(6, D.SB_DN)
        p.if_(3, "GT", 4, lambda: p.fconst(6, D.SB_UP))
        p.fop(5, 5, "*", 6)
        p.fop(4, 4, "+", 5)
        p.st(C["s1"], 4)                         # e
        p.fconst(1, D.SB_THR)
        p.fop(5, 4, "*", 1)                      # th
        p.ld(6, C["s4"])
        p.ifz(6, "EQ", lambda: p.if_(2, "GT", 5, fire), rearm, kind="f")
        p.ld(6, C["s3"])
        p.ld(7, C["s5"])
        p.fop(7, 7, "-", 6)
        p.ld(1, C["b"])
        p.fop(7, 7, "*", 1)
        p.fop(7, 6, "+", 7)
        p.fconst(1, 2.0)
        p.fop(7, 7, "*", 1)
        p.fconst(1, 1.0)
        p.fop(7, 7, "-", 1)
        p.fop(7, 4, "*", 7)                      # the square at e
        p.ld(2, C["s2"])
        p.fop(7, 7, "-", 2)
        p.ld(1, C["c"])
        p.fop(7, 7, "*", 1)
        p.fop(2, 2, "+", 7)
        p.st(C["s2"], 2)                         # rounded
        p.ld(1, C["p5"])
        p.fop(3, 0, "*", 1)
        p.ld(1, C["p1"])
        p.fop(2, 2, "*", 1)
        p.fop(3, 3, "+", 2)
        p.fop(3, 3, "-", 0)
        p.ld(1, C["p0"])
        p.fop(3, 3, "*", 1)
        p.fop(3, 0, "+", 3)
        p.stpost(1, 3)
    p.loop_r(11, D.BLOCK, one)


def ring(p: Prog) -> None:
    """RING (ref.Ref.ring_mod); p1 FREQ, p2 SHPE, p3 AM, p4 LEV; s0 the phase"""
    p.ld(0, C["p1"])
    p.fconst(1, D.LOG2_RG_SPAN)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.RG_LO * D.RG_PH_PER_HZ)
    p.fop(0, 0, "*", 1)
    p.trunc(0, 0)
    p.st(C["inc"], 0)
    p.ld(0, C["p2"])
    p.fconst(1, D.RG_SHAPE_MAX)
    p.fop(0, 0, "*", 1)
    p.fconst(1, 1.0)
    p.fop(0, 0, "+", 1)
    p.st(C["g"], 0)
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)
    p.ld(9, C["inc"])
    if FZ_STAGED:
        _held(p, ((8, 0),), lambda: _ring_sample(p), auto=False)
        return
    p.ld(8, C["s0"])

    def one():
        clamp_in(p)
        p.ipass(0, 8)
        FP.sine(p)
        p.iop(8, 8, "+", 9)
        p.ld(1, C["g"])
        p.fop(0, 0, "*", 1)
        p.fconst(1, -1.0)
        p.fop(0, 0, "MAX", 1)
        p.fconst(1, 1.0)
        p.fop(0, 0, "MIN", 1)
        p.fop(2, 1, "-", 0)
        p.ld(1, C["p3"])
        p.fop(2, 2, "*", 1)
        p.fop(0, 0, "+", 2)                      # the carrier
        p.ld(5, C["k"])
        p.fop(3, 5, "*", 0)
        p.ld(1, C["p4"])
        p.fop(3, 3, "*", 1)
        p.fop(3, 3, "-", 5)
        p.ld(1, C["p0"])
        p.fop(3, 3, "*", 1)
        p.fop(3, 5, "+", 3)
        p.stpost(1, 3)
    p.loop_r(11, D.BLOCK, one)
    p.st(C["s0"], 8)


def gater(p: Prog) -> None:
    """GATER (ref.Ref.gater); p1 DPTH, p2 PATN, p3 RATE, p4 SHPE, p5 SWNG; s0 the phase (Q28 a step),
    s1 the closure, s2 the clock word last seen (design.CLK)"""
    p.ld(0, D.TEMPO)
    p.iconst(12, 0xFFFF)
    p.iop(0, 0, "AND", 12)
    p.ifz(0, "EQ", lambda: p.iconst(0, 120 * 120))
    p.iconst(1, 0)
    p.float_(0, 0, 1)
    p.fconst(1, D.TICKS_PER_BPM120)
    p.fop(0, 0, "*", 1)                          # ticks a block
    p.ld(1, C["p3"])
    p.fconst(2, float(len(D.GT_RATE)))
    p.fop(1, 1, "*", 2)
    p.trunc(1, 1)
    p.iconst(2, len(D.GT_RATE) - 1)
    p.iop(1, 1, "MIN", 2)
    p.lsh(1, 1, 2)
    p.iconst(12, RATE_TAB)
    p.iop(2, 12, "+", 1)
    p.seti(4, 2)
    p.ldi(1, 0, 4)
    p.st(C["inv"], 1)                            # 1 / the step's ticks
    p.fop(0, 0, "*", 1)
    p.fconst(1, 2.0 ** 23)
    p.fop(0, 0, "*", 1)
    p.trunc(0, 0)
    p.st(C["inc"], 0)                            # a sample's step, Q28
    p.iconst(1, -27)
    p.float_(2, 0, 1)
    p.st(C["sl"], 2)
    p.ld(0, C["p4"])
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 0)
    p.fconst(1, D.GT_SHAPE_OCT)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.ld(1, C["sl"])
    p.fop(0, 1, "*", 0)
    p.fconst(1, D.GT_SMIN)
    p.fop(0, 0, "MAX", 1)
    p.fconst(1, D.GT_SMAX)
    p.fop(0, 0, "MIN", 1)
    p.st(C["sl"], 0)
    p.fconst(1, 0.0)
    p.fop(1, 1, "-", 0)
    p.st(C["nsl"], 1)
    p.ld(0, C["p2"])
    p.fconst(1, 16.0)
    p.fop(0, 0, "*", 1)
    p.trunc(0, 0)
    p.iconst(1, 15)
    p.iop(0, 0, "MIN", 1)
    p.lsh(0, 0, 2)
    p.iconst(12, PAT_TAB)
    p.iop(2, 12, "+", 0)
    p.seti(4, 2)
    p.ldi(13, 0, 4)                              # the pattern
    p.lsh(1, 13, -1)
    p.lsh(2, 13, 15)
    p.iop(1, 1, "OR", 2)
    p.iconst(12, 0xFFFF)
    p.iop(14, 1, "AND", 12)                      # bit k: step k + 1 is open
    p.ld(0, C["p5"])
    p.fconst(1, D.GT_SWING_MAX)
    p.fop(0, 0, "*", 1)
    p.fconst(1, 1.0)
    p.fop(0, 0, "+", 1)
    p.fconst(1, float(D.GT_STEP))
    p.fop(0, 0, "*", 1)
    p.trunc(0, 0)
    p.st(C["b1"], 0)                             # a pair's first step (the swing)
    p.lsh(1, 0, -1)
    p.st(C["h0"], 1)
    p.iconst(12, D.GT_STEP)
    p.iop(1, 12, "+", 1)
    p.st(C["h1"], 1)
    p.ld(8, C["s0"])

    def snap():                                  # the clock word: the sequencer's place, to the phase
        p.iconst(12, 0xFFF)
        p.iop(1, 0, "AND", 12)
        p.iconst(2, 0)
        p.float_(1, 1, 2)
        p.ld(2, C["inv"])
        p.fop(1, 1, "*", 2)
        p.trunc(3, 1)
        p.iconst(4, 0)
        p.float_(4, 3, 4)
        p.fop(1, 1, "-", 4)
        p.fconst(4, float(D.GT_STEP))
        p.fop(1, 1, "*", 4)
        p.trunc(1, 1)
        p.lsh(12, 3, 28)
        p.iop(3, 12, "+", 1)                     # the target
        p.fconst(4, D.GT_TOL_TICKS * float(D.GT_STEP))
        p.fop(2, 2, "*", 4)
        p.trunc(2, 2)                            # the tolerance
        p.iop(4, 8, "-", 3)
        p.iconst(5, 0)
        p.iop(6, 5, "-", 2)

        def take():
            p.ipass(8, 3)
        p.if_(4, "GT", 2, take, lambda: p.if_(4, "LT", 6, take, kind="i"), kind="i")

    def seen():
        p.st(C["s2"], 0)
        p.ifz(0, "LT", snap)
    p.ld(0, D.CLK)
    p.ld(1, C["s2"])
    p.if_(0, "NE", 1, seen, kind="i")
    p.ld(5, C["s1"])
    p.ld(9, C["inc"])
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)
    if FZ_STAGED:
        p.iconst(4, FZ_TAB)
        p.seti(2, 4)
        p.iconst(4, C[_FZ_I3])
        p.seti(3, 4)
        p.loop_r(11, D.BLOCK, lambda: _gater_sample(p), one=11)
        p.st(C["s0"], 8)
        p.st(C["s1"], 5)
        return

    def one():
        clamp_in(p)
        p.iconst(12, D.GT_PAIR - 1)
        p.iop(1, 8, "AND", 12)                   # q
        p.lsh(2, 8, -28)
        p.iconst(12, 14)
        p.iop(2, 2, "AND", 12)                   # k
        p.ld(3, C["b1"])

        def first():
            p.ld(6, C["h0"])
            p.ipass(7, 3)

        def second():
            p.iconst(12, 1)
            p.iop(2, 12, "+", 2)
            p.ld(6, C["h1"])
            p.iconst(7, D.GT_PAIR)
        p.if_(1, "LT", 3, first, second, kind="i")
        p.iconst(3, 1)
        p.float_(3, 3, 2)
        p.trunc(3, 3)                            # 1 << k
        p.iop(4, 14, "AND", 3)
        p.ifz(4, "EQ", lambda: p.ipass(6, 7))    # the next step closed: open to this one's end
        p.ld(4, C["p1"])
        p.iop(10, 13, "AND", 3)
        p.ifz(10, "NE", lambda: p.if_(1, "LT", 6, lambda: p.fconst(4, 0.0), kind="i"))
        p.fop(4, 4, "-", 5)
        p.ld(1, C["sl"])
        p.fop(4, 4, "MIN", 1)
        p.ld(1, C["nsl"])
        p.fop(4, 4, "MAX", 1)
        p.fop(5, 5, "+", 4)                      # the closure
        p.fconst(1, 1.0)
        p.fop(1, 1, "-", 5)
        p.fop(1, 0, "*", 1)
        p.fop(1, 1, "-", 0)
        p.ld(2, C["p0"])
        p.fop(1, 1, "*", 2)
        p.fop(1, 0, "+", 1)
        p.stpost(1, 1)
        p.iop(8, 8, "+", 9)
    p.loop_r(11, D.BLOCK, one)
    p.st(C["s0"], 8)
    p.st(C["s1"], 5)


def track(p: Prog) -> None:
    """voice slot C['t']: the track it plays (design.ROUTE), that track's bytes, then its insert"""
    p.ld(0, C["t"])
    p.lsh(1, 0, -1)
    p.lsh(1, 1, 2)
    p.iconst(12, D.ROUTE)
    p.iop(2, 12, "+", 1)
    p.seti(4, 2)
    p.ldi(3, 0, 4)                               # the slot pair's word: even slot low half, odd high
    p.iconst(12, 1)
    p.iop(1, 0, "AND", 12)
    p.ifz(1, "NE", lambda: p.lsh(3, 3, -16))
    p.iconst(12, 0xFFFF)
    p.iop(3, 3, "AND", 12)
    p.st(C["tr"], 3)
    record(p, C)
    skip_moved(p)

    def run():                                   # its state at STATE + 32 i, its ring, the voice's buffer
        p.ld(0, C["i"])
        p.lsh(1, 0, 5)
        p.iconst(12, STATE)
        p.iop(2, 12, "+", 1)
        p.st(C["sa"], 2)
        if D.TAPE in D.BUILT:
            p.lsh(1, 0, 11)                      # 2 KB a voice slot and insert slot
            p.iconst(12, D.TP_RING_DDR)
            p.iop(1, 12, "+", 1)
            p.st(C["rb"], 1)
        p.ld(0, C["t"])
        p.lsh(1, 0, 2)
        p.iconst(12, D.BUFFERS)
        p.iop(2, 12, "+", 1)
        p.seti(4, 2)
        p.ldi(3, 0, 4)
        p.st(C["buf"], 3)
        call_one(p, lambda: p.jump("", ONE))
    _is_built(p, run)


ONE = "wr_in_one"                                # one's label (design.INS_ONE_SW)


def call_one(p: Prog, go) -> None:
    """one(): run mode runs it here; emit mode puts the return address - 1 in C['ret'] and GO() jumps to
    it (one calls the leaf subroutines, so it cannot be one itself). Clobbers what one does"""
    if p.run:
        one(p)
        return
    ret = p.label("oret")
    p.ret_addr(12, ret)
    p.st(C["ret"], 12)
    go()
    p.place(ret)


def in_types(p: Prog, d: int, s: int, w: int, types) -> None:
    """Rd nonzero when Rs (a type, 0..15) is one of TYPES: bit min(Rs, 15) of their mask. Clobbers Rw, R12"""
    assert max(types) < 15
    p.iconst(12, 15)
    p.iop(w, s, "MIN", 12)
    p.iconst(d, 1)
    p.float_(d, d, w)
    p.trunc(d, d)
    p.iconst(12, sum(1 << t for t in types))
    p.iop(d, d, "AND", 12)


def skip_moved(p: Prog) -> None:
    """2026-11-11 (the User: "always run in slot order"): a slot 2 (C['j'] 1) whose slot 1 is of
    design.MOVERS is left out here (C['sel'] = 0): the bus pass runs it after slot 1 (dnfw.inserts.bus).
    Clobbers R0, R2, R3, R5-R7, R12, I4"""
    def check():
        p.ld(2, C["rec"])
        p.iconst(12, 4 * D.FIELDS)
        p.iop(2, 2, "-", 12)                     # slot 1's record
        p.seti(4, 2)
        p.ldi(3, 0, 4)
        p.iconst(12, (1 << D.TYPE_BITS) - 1)
        p.iop(3, 3, "AND", 12)
        in_types(p, 7, 3, 6, D.MOVERS)

        def leave():
            p.iconst(5, 0)
            p.st(C["sel"], 5)
        p.ifz(7, "NE", leave)
    p.ld(0, C["j"])
    p.ld(5, C["sel"])
    p.ifz(0, "NE", lambda: p.ifz(5, "NE", check))     # (C['rec'] is the record's only when it plays)


def _or_buf(p: Prog) -> None:
    """R3 = the OR of the 32 words at C['buf'] (0: all +0.0), R4 their AND (R3 = R4 = 0x80000000: all -0.0). Clobbers
    R1, R2, R11, I0"""
    p.ld(2, C["buf"])
    p.seti(0, 2)
    p.iconst(3, 0)
    p.iconst(4, -1)

    def one():
        p.ldpost(1, 0)
        p.iop(3, 3, "OR", 1)
        p.iop(4, 4, "AND", 1)
    p.loop_r(11, D.BLOCK, one)


def _zero_class(p: Prog) -> None:
    """R3 = the input's zero class from _or_buf's R3, R4: 0 all +0.0, 0x80000000 all -0.0, 1 anything else (not
    quiet). Clobbers R12"""
    p.iconst(12, 0x80000000)

    def neg():
        p.iconst(3, 1)
        p.if_(4, "EQ", 12, lambda: p.iconst(3, 0x80000000), kind="i")
    p.ifz(3, "NE", lambda: p.if_(3, "EQ", 12, neg, lambda: p.iconst(3, 1), kind="i"))


def quiet(p: Prog, gated) -> None:
    """2026-11-12 (main; opt-host's measure: a per-voice insert runs on every slot its track owns, sounding or not):
    GATED() (the insert, its gate and smoothing) unless the input is all +0.0 or all -0.0 and the instance's quiet
    mark (C['qa']) is the change word + 1 with that sign in bit 31: then its last run had the same input and left
    all +0.0 output, its state and AUTO words as they were, under the same records, so running it again would give
    the same: the skip writes the +0.0s, bit-identical. (The runner's silent slots hold -0.0s, not +0.0s.) Clobbers
    R0-R4, R11, R12, I0, I4 (and GATED's)"""
    _or_buf(p)
    _zero_class(p)
    p.st(C["zin"], 3)
    p.ld(0, TABLE + 4 * D.RECORDS * D.FIELDS)    # the change word + 1, the sign in bit 31
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    p.iop(0, 0, "OR", 3)
    p.ld(2, C["qa"])
    p.seti(4, 2)
    p.ldi(1, 0, 4)
    p.iconst(2, 0)                               # 1: skip

    def marked():
        p.if_(1, "EQ", 0, lambda: p.iconst(2, 1), kind="i")
    p.iconst(12, 1)
    p.if_(3, "NE", 12, marked, kind="i")

    def skip():                                  # what the run gave: +0.0s
        p.ld(2, C["buf"])
        p.seti(0, 2)
        p.iconst(1, 0)
        p.loop_r(11, D.BLOCK, lambda: p.stpost(0, 1))
    p.ifz(2, "EQ", gated, skip)


def quiet_mark(p: Prog) -> None:
    """after a run: the quiet mark = the change word + 1, the input's sign in bit 31, when the input was all +0.0 or all
    -0.0 (C['zin'] 0 or 0x80000000), the gate ran it (status 0), the output is all +0.0, and the state words
    (C['s0'..'s5'] against the stored) and AUTO's powers are as they were; else 0. Clobbers R0-R4, R8, R9, R11, R12, I0,
    I4"""
    p.iconst(8, 0)                               # the mark

    def check():
        _or_buf(p)
        p.iconst(9, 1)                           # all as they were

        def same():
            for stored, kept, n in (("sa", "s0", D.STATE_WORDS - 2), ("aa", "ap0", 2)):
                p.ld(2, C[stored])
                p.seti(4, 2)
                p.iconst(2, C[kept])
                p.seti(0, 2)

                def one():
                    p.ldpost(0, 4)
                    p.ldpost(1, 0)
                    p.if_(0, "NE", 1, lambda: p.iconst(9, 0), kind="i")
                p.loop_r(11, n, one)

            def mark():
                p.ld(8, TABLE + 4 * D.RECORDS * D.FIELDS)
                p.iconst(12, 1)
                p.iop(8, 8, "+", 12)
                p.ld(0, C["zin"])
                p.iop(8, 8, "OR", 0)
            p.ifz(9, "NE", mark)
        p.ifz(3, "EQ", same)
    p.ld(0, C["zin"])                            # 0 or 0x80000000, and status 0
    p.iconst(12, 0x7FFFFFFF)
    p.iop(0, 0, "AND", 12)
    p.ld(1, C["ist"])
    p.iop(0, 0, "OR", 1)
    p.ifz(0, "EQ", check)
    p.ld(2, C["qa"])
    p.seti(4, 2)
    p.sti(0, 4, 8)


def auto_addr(p: Prog) -> None:
    """C['aa'] = the aux words (design.AUX_WORDS) for the state at R2 (C['sa']): the pre pass's (L1, STATE + 32 i) at
    AUTO_L2 + 16 i, a moved slot 2's (L2, MV_STATE + 32 k) at AUTO_MV_L2 + 16 ((MV_STATE / 32 + k) mod 32); C['qa']
    its quiet mark, QUIET_L2 + 4 i (+ 4 RECORDS for a moved one). Keeps R2"""
    p.lsh(1, 2, -5)
    p.iconst(12, D.RECORDS - 1)
    p.iop(1, 1, "AND", 12)
    p.lsh(1, 1, 4)
    p.iconst(12, D.AUTO_L2)
    p.iconst(3, 0x20000000)                      # L2 and above: a moved slot 2's state (bus.MV_STATE)
    p.if_(2, "GE", 3, lambda: p.iconst(12, D.AUTO_MV_L2), kind="i")
    p.iop(8, 12, "+", 1)
    p.st(C["aa"], 8)
    p.lsh(1, 1, -2)                              # the quiet mark (design.QUIET_L2): 4 i, the moved ones after
    p.iconst(12, D.QUIET_L2)
    p.if_(2, "GE", 3, lambda: p.iconst(12, D.QUIET_L2 + 4 * D.RECORDS), kind="i")
    p.iop(1, 12, "+", 1)
    p.st(C["qa"], 1)


def dry_ends(p: Prog, buf_at: int | None = None, d0_at: int | None = None, d31_at: int | None = None) -> None:
    """the first and last samples of the buffer (address at BUF_AT) before the insert, to D0_AT and D31_AT (smooth's;
    the pre pass's words by default). Clobbers R0-R2, I0"""
    p.ld(2, C["buf"] if buf_at is None else buf_at)
    p.seti(0, 2)
    p.ldi(0, 0, 0)
    p.st(C["d0"] if d0_at is None else d0_at, 0)
    p.ldi(1, D.BLOCK - 1, 0)
    p.st(C["d31"] if d31_at is None else d31_at, 1)


def smooth(p: Prog, aa_at: int | None = None, ist_at: int | None = None, buf_at: int | None = None,
           d0_at: int | None = None, d31_at: int | None = None, diff: int = 3) -> None:
    """2026-11-12 (perc.guard.ins_gate): no step where an instance goes out or comes back. Its aux word DIFF holds
    the last block's wet - dry at its last sample; the block it goes out (status 2), the dry gets that difference,
    fading to 0 over the block; the block it comes back (1), the wet gets dry - wet at its first sample, fading
    likewise. Every block it runs (0, 1), word DIFF = its last wet - the dry's; out (2, 3), 0. The buffer's address
    is at BUF_AT, the status at IST_AT, the dry's ends at D0_AT, D31_AT, the aux words' address at AA_AT (the pre
    pass's words by default; ramp reads the buffer's address at BUF_AT too). Clobbers R0-R3, R11, R12, I0, I1, I4"""
    aa_at = C["aa"] if aa_at is None else aa_at
    buf_at = C["buf"] if buf_at is None else buf_at
    p.ld(2, aa_at)
    p.seti(4, 2)
    p.ld(3, C["ist"] if ist_at is None else ist_at)
    p.iconst(1, 2)

    def left_out():
        def went():
            p.ldi(0, diff, 4)
            ramp(p, buf_at)
        p.iconst(1, 2)
        p.if_(3, "EQ", 1, went, kind="i")
        p.fconst(0, 0.0)
        p.ld(2, aa_at)
        p.seti(4, 2)
        p.sti(diff, 4, 0)

    def ran():
        def back():
            p.ld(2, buf_at)
            p.seti(0, 2)
            p.ldi(1, 0, 0)
            p.ld(0, C["d0"] if d0_at is None else d0_at)
            p.fop(0, 0, "-", 1)
            ramp(p, buf_at)
        p.iconst(1, 1)
        p.if_(3, "EQ", 1, back, kind="i")
        p.ld(2, buf_at)
        p.seti(0, 2)
        p.ldi(0, D.BLOCK - 1, 0)
        p.ld(1, C["d31"] if d31_at is None else d31_at)
        p.fop(0, 0, "-", 1)
        p.ld(2, aa_at)
        p.seti(4, 2)
        p.sti(diff, 4, 0)
    p.if_(3, "GE", 1, left_out, ran, kind="i")


def ramp(p: Prog, buf_at: int) -> None:
    """the buffer at the address at BUF_AT + F0 x (31 - j) / 32, j = 0..31 (one copy a program, a leaf: every call
    in a program passes the same BUF_AT). Clobbers R0-R3, R11, R12, I0, I1, I12"""
    p.call("ins_ramp", lambda: _ramp(p, buf_at))


def _ramp(p: Prog, buf_at: int) -> None:
    p.fconst(1, 1.0 / D.BLOCK)
    p.fop(1, 0, "*", 1)                          # the step
    p.ld(2, buf_at)
    p.seti(0, 2)
    p.seti(1, 2)

    def one():
        p.fop(0, 0, "-", 1)
        p.ldpost(2, 0)
        p.fop(2, 2, "+", 0)
        p.stpost(1, 2)
    p.loop_r(11, D.BLOCK, one)


def one(p: Prog) -> None:
    """one insert: the record at C['rec'] (type C['sel'], a BUILT one, played by track C['tr']) over the 32
    floats at C['buf'], in place; its state the 8 words at C['sa'] (zeros when the type or the track changed
    since it last ran there), TAPE's ring at C['rb']. The pre pass runs it for each voice slot's insert; the
    bus pass for a moved slot 2 on the track's L and R (2026-11-11)"""
    p.ld(2, C["sa"])
    auto_addr(p)
    p.seti(4, 2)
    p.ldi(7, D.STATE_WORDS - 1, 4)               # the last M.SEL
    p.ldi(6, D.STATE_WORDS - 2, 4)               # the last track
    p.ld(5, C["sel"])
    p.ld(8, C["tr"])

    def fresh():
        p.ld(2, C["sa"])
        p.seti(4, 2)
        p.iconst(9, 0)
        for k in range(D.STATE_WORDS - 2):
            p.sti(k, 4, 9)
        p.ld(8, C["tr"])
        p.ld(5, C["sel"])
        p.sti(D.STATE_WORDS - 2, 4, 8)
        p.sti(D.STATE_WORDS - 1, 4, 5)
        p.ld(2, C["aa"])                         # the aux words too (AUTO's powers, the gate's), and the quiet mark
        p.seti(4, 2)
        for k in range(D.AUX_WORDS):
            p.sti(k, 4, 9)
        p.ld(2, C["qa"])
        p.seti(4, 2)
        p.sti(0, 4, 9)

        def fresh_ring():                        # TAPE starts from a silent ring
            p.ld(1, C["rb"])
            p.seti(1, 1)
            p.fconst(0, 0.0)

            def eight():                         # (2026-11-14: 8 a pass, not 16: code room for TAPE's stages)
                for _ in range(8):
                    p.stpost(1, 0)
            p.loop_r(11, D.TP_RING // 8, eight)
        if D.TAPE in D.BUILT:                    # dnfw.builder: no ring without TAPE
            p.iconst(6, D.TAPE)
            p.if_(5, "EQ", 6, fresh_ring, kind="i")
    p.iconst(9, 0)

    def differs():
        p.iconst(9, 1)
    p.if_(7, "NE", 5, differs, kind="i")
    p.if_(6, "NE", 8, differs, kind="i")
    p.ifz(9, "NE", fresh)
    p.ld(2, C["sa"])
    p.seti(4, 2)
    for k in range(D.STATE_WORDS):
        p.ldi(8, k, 4)
        p.st(C[f"s{k}"], 8)
    values(p, C)
    fzd = D.FUZZ in D.BUILT or D.DIST in D.BUILT

    def run():
        if fzd:                                  # FUZZ and DIST set it: their shared loop, emitted once, runs after
            p.iconst(0, 0)
            p.st(C["fz"], 0)
        _by_type(p, [(typ, fn) for typ, fn in ((D.FUZZ, fuzz), (D.TAPE, tape), (D.FOLD, fold), (D.HARM, harm),
                                               (D.SUB, sub), (D.DIST, dist), (D.GATER, gater), (D.RING, ring))
                     if typ in D.BUILT])         # dnfw.builder: only the inserts this build runs
        if fzd:
            p.ld(0, C["fz"])
            p.ifz(0, "NE", lambda: fz_loop(p))

    def gated():
        dry_ends(p)
        p.ld(1, C["sel"])                        # the type's bound (COST_TAB)
        p.lsh(1, 1, 2)
        p.iconst(12, COST_TAB)
        p.iop(1, 12, "+", 1)
        p.seti(4, 1)
        p.ldi(1, 0, 4)
        p.st(C["icost"], 1)
        p.ld(2, C["aa"])                         # AUTO's powers as they were (quiet_mark)
        p.seti(4, 2)
        for k in range(2):
            p.ldi(1, k, 4)
            p.st(C[f"ap{k}"], 1)
        G.ins_gate(p, C["icost"], C["aa"], C["ist"], run, typ_at=C["sel"])
        smooth(p)
        quiet_mark(p)
    quiet(p, gated)
    p.ld(2, C["sa"])
    p.seti(4, 2)
    for k in range(D.STATE_WORDS - 2):
        p.ld(8, C[f"s{k}"])
        p.sti(k, 4, 8)


def _is_built(p: Prog, run) -> None:
    """RUN once when M.SEL (C['sel']) is a type this build runs (design.BUILT): bit min(sel, 15) of
    the built types' mask (1 << n as FLOAT 1 BY n, TRUNC)"""
    assert max(D.BUILT) < 15
    p.ld(5, C["sel"])
    p.iconst(6, 15)
    p.iop(5, 5, "MIN", 6)
    p.iconst(7, 1)
    p.float_(7, 7, 5)
    p.trunc(7, 7)
    p.iconst(12, sum(1 << t for t in D.BUILT))
    p.iop(7, 7, "AND", 12)
    p.ifz(7, "NE", run)


def _by_type(p: Prog, table) -> None:
    """the insert of C['sel'] from TABLE [(type, fn)]"""
    def pick(rest):
        if not rest:
            return
        typ, fn = rest[0]
        p.ld(5, C["sel"])
        p.iconst(6, typ)
        p.if_(5, "EQ", 6, lambda: fn(p), lambda: pick(rest[1:]), kind="i")
    pick(table)


def record(p: Prog, C: dict) -> None:
    """C['tr'] (the track voice slot C['t'] plays, past 15 none) and C['j'] (the insert slot) -> C['rec']
    the record's address in TABLE, C['sel'] its type (0 when the slot plays no track). Clobbers R0-R5, R12"""
    p.iconst(5, 0)
    p.ld(3, C["tr"])
    p.iconst(12, 15)

    def plays():
        p.ld(0, C["tr"])
        p.lsh(1, 0, 6)                           # 2 records x 32 bytes a track
        p.ld(0, C["j"])
        p.lsh(0, 0, 5)
        p.ipass(12, 1)
        p.iop(1, 12, "+", 0)
        p.iconst(12, TABLE)
        p.iop(2, 12, "+", 1)
        p.st(C["rec"], 2)
        p.seti(4, 2)
        p.ldi(3, 0, 4)
        p.iconst(12, (1 << D.TYPE_BITS) - 1)
        p.iop(5, 3, "AND", 12)                   # the type
    p.if_(3, "LE", 12, plays, kind="i")
    p.st(C["sel"], 5)


def values(p: Prog, C: dict) -> None:
    """MIX, K1..K6 of the record at C['rec'] -> C['p0'] .. C['p6'], each / 127. Clobbers R2, R8, R9, R12, I4"""
    p.ld(2, C["rec"])
    p.seti(4, 2)
    for k in range(7):
        p.ldi(8, k + 1, 4)
        p.iconst(9, 0)
        p.float_(8, 8, 9)
        p.fconst(9, 1 / 127)
        p.fop(8, 8, "*", 9)
        p.st(C[f"p{k}"], 8)


def unpack(p: Prog, C: dict) -> None:
    """when the change word moved: the packed words into TABLE (design.unpack). Clobbers R0-R3, R12, I0, I4"""
    def go():
        p.st(TABLE + 4 * D.RECORDS * D.FIELDS, 0)
        p.iconst(1, D.PACK)
        p.seti(4, 1)
        p.iconst(1, TABLE)
        p.seti(0, 1)

        def group():
            p.iconst(3, 0)                       # X: the words' top nibbles

            def word():
                p.ldpost(0, 4)
                for sh in (0, 7, 14, 21):
                    p.lsh(1, 0, -sh) if sh else p.ipass(1, 0)
                    p.iconst(12, 0x7F)
                    p.iop(1, 1, "AND", 12)
                    p.stpost(0, 1)
                p.lsh(3, 3, -4)
                p.lsh(1, 0, -28)
                p.lsh(1, 1, 24)
                p.iop(3, 3, "OR", 1)
            p.loop_r(11, 7, word, one=2)
            for sh in (0, 7, 14, 21):
                p.lsh(1, 3, -sh) if sh else p.ipass(1, 3)
                p.iconst(12, 0x7F)
                p.iop(1, 1, "AND", 12)
                p.stpost(0, 1)
        p.loop(C["gn"], D.RECORDS * D.FIELDS // 32, group)
        set_flags(p)
    p.ld(0, D.GEN)
    p.ld(1, TABLE + 4 * D.RECORDS * D.FIELDS)
    p.if_(0, "NE", 1, go, kind="i")


def set_flags(p: Prog) -> None:
    """D.FLAGS from the records just unpacked (design.flags), 2026-11-10 (perf); 2026-11-11: the bus
    pass's flag for a moved slot 2 too (design.moved). Clobbers R0-R8, R11, R12, I4"""
    p.iconst(1, TABLE)
    p.seti(4, 1)
    for r in (2, 3, 5, 6, 7):                    # R2 the last record's type, R3 1 on a slot 2
        p.iconst(r, 0)

    def rec():
        p.ldi(0, 0, 4)
        p.iconst(12, (1 << D.TYPE_BITS) - 1)
        p.iop(0, 0, "AND", 12)
        for r, group in ((5, D.BUILT), (6, D.POST), (7, D.BUS)):
            for typ in group:
                p.iconst(12, typ)
                p.if_(0, "EQ", 12, lambda r=r: p.iconst(r, 1), kind="i")

        def slot2():
            in_types(p, 4, 0, 8, D.BUILT)

            def built():
                in_types(p, 4, 2, 8, D.MOVERS)
                p.ifz(4, "NE", lambda: p.iconst(7, 1))
            p.ifz(4, "NE", built)
        p.ifz(3, "NE", slot2)
        p.ipass(2, 0)
        p.iconst(12, 1)
        p.iop(3, 12, "-", 3)
        p.geti(1, 4)
        p.iconst(12, 4 * D.FIELDS)
        p.iop(1, 12, "+", 1)
        p.seti(4, 1)
    p.loop_r(11, D.RECORDS, rec, one=12)
    for k, r in enumerate((5, 6, 7)):
        p.st(D.FLAGS + 4 * k, r)


def body(p: Prog) -> None:
    G.ins_start(p, 1)
    unpack(p, C)
    p.ld(0, D.FLAGS)                             # (perf) no BUILT record: nothing to walk
    p.ifz(0, "NE", lambda: _walk(p))


def _walk(p: Prog) -> None:
    p.iconst(0, 0)
    p.st(C["i"], 0)

    def each():
        p.ld(0, C["i"])
        p.lsh(1, 0, -1)
        p.st(C["t"], 1)
        p.iconst(12, 1)
        p.iop(1, 0, "AND", 12)
        p.st(C["j"], 1)
        track(p)
        p.ld(0, C["i"])
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
        p.st(C["i"], 0)
    _tracks(p, each, D.RECORDS)


def _tracks(p: Prog, each, n: int = D.TRACKS) -> None:
    """EACH n times (the caller counts; a scratch word counts down)"""
    p.iconst(0, n)
    p.st(C["cnt"], 0)
    top = p.label("trk")
    p.place(top)
    if p.run:
        while True:
            each()
            p.ld(0, C["cnt"])
            p.iconst(12, 1)
            p.iop(0, 0, "-", 12)
            p.st(C["cnt"], 0)
            if p.r[0] == 0:
                break
        return
    each()
    p.ld(0, C["cnt"])
    p.iconst(12, 1)
    p.iop(0, 0, "-", 12)
    p.st(C["cnt"], 0)
    p.jump("NE", top)


def program(next_sw: int, prefix: str = "in") -> str:
    p = Prog("emit", prefix=prefix)
    p.raw("// inserts.asm -- the per-track inserts (docs/inserts.md). GENERATED by")
    p.raw("// scripts/gen_inserts_asm.py from dnfw.inserts.program; do not edit by hand.")
    p.raw("")
    p.raw(".SECTION/PM seg_pmco;")
    p.raw("")
    p.raw(".GLOBAL wr_ins.;")
    p.raw("wr_ins.:")
    main = "wr_in_main"
    p.jump("", main)                             # (48 bits: one is at INS_SW + 3, design.INS_ONE_SW)
    p.place(ONE)                                 # 2026-11-11: one insert, a callable for the bus pass too
    one(p)
    p.ld(12, C["ret"])
    p.e("I12 = R12;")
    p.e("JUMP (M14, I12);", "back to the caller (the walk here, or dnfw.inserts.bus)")
    p.place(main)
    body(p)
    G.ins_end(p)
    p.jump_abs("", next_sw, "ping.asm's wr_ping (it returns to the stock chain)")
    p.emit_subs()
    p.raw(".wr_ins..end:")
    p.raw("      .type wr_ins.,STT_FUNC;")
    return p.text()


def run(mem: Mem) -> Prog:
    p = Prog("run", mem=mem)
    for k, w in enumerate(TABLE_WORDS):          # (on the DSP: state_bytes, loaded with the code)
        mem.put(RATE_TAB + 4 * k, w)
    body(p)
    return p
