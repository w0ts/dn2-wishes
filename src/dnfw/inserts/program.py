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
    "pa", "rel", "a1", "lv", "kl", "fz", "inv", "inc", "sl", "nsl", "pat", "nx", "b1", "h0", "h1"]
C = {n: SCRATCH + 4 * k for k, n in enumerate(_NAMES)}
assert len(C) == len(_NAMES)
SCRATCH_BYTES = 4 * len(_NAMES)
# GATER's tables after the words: RATE's 1 / ticks (float32), the 16 patterns (loaded with the state)
RATE_TAB = SCRATCH + SCRATCH_BYTES
PAT_TAB = RATE_TAB + 4 * len(D.GT_RATE)
TABLE_WORDS = [struct.unpack("<I", struct.pack("<f", 1.0 / d))[0] for d in D.GT_RATE] + list(D.GT_PAT)
assert PAT_TAB + 4 * len(D.GT_PAT) <= TABLE


def state_bytes() -> bytes:
    """the state and the pass's words (zeros), GATER's tables, then the unpacked records, the last
    change word and the skip flags (zeros)"""
    head = bytes(RATE_TAB - STATE) + struct.pack(f"<{len(TABLE_WORDS)}I", *TABLE_WORDS)
    return head + bytes(D.FLAGS + 4 * D.FLAG_WORDS - STATE - len(head))


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
    p.fconst(0, 0.0)
    p.st(C["kl"], 0)


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
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)

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
        p.fop(3, 3, "-", 0)
        p.ld(1, C["p0"])
        p.fop(3, 3, "*", 1)
        p.fop(3, 0, "+", 3)
        p.stpost(1, 3)
    p.loop_r(11, D.BLOCK, one)


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
    p.st(C["lvl"], 0)
    p.ld(0, C["i"])
    p.lsh(1, 0, 11)                              # 2 KB a voice slot and insert slot
    p.iconst(12, D.TP_RING_DDR)
    p.iop(1, 12, "+", 1)
    p.st(C["rb"], 1)
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
        p.ld(0, C["k"])
        p.fop(2, 2, "-", 0)
        p.ld(3, C["p0"])
        p.fop(2, 2, "*", 3)
        p.fop(2, 0, "+", 2)
        p.stpost(1, 2)
    p.loop_r(11, D.BLOCK, one)


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
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)

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
        p.fop(3, 3, "-", 0)
        p.ld(1, C["p0"])
        p.fop(3, 3, "*", 1)
        p.fop(3, 0, "+", 3)
        p.stpost(1, 3)
    p.loop_r(11, D.BLOCK, one)


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
    p.ld(4, C["buf"])
    p.seti(0, 4)
    p.seti(1, 4)

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
        p.fop(3, 3, "-", 0)
        p.ld(1, C["p0"])
        p.fop(3, 3, "*", 1)
        p.fop(3, 0, "+", 3)
        p.stpost(1, 3)
    p.loop_r(11, D.BLOCK, one)


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
    p.ld(8, C["s0"])
    p.ld(9, C["inc"])

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

    def run():
        p.ld(0, C["i"])
        p.lsh(1, 0, 5)
        p.iconst(12, STATE)
        p.iop(2, 12, "+", 1)
        p.st(C["sa"], 2)
        p.seti(4, 2)
        p.ldi(7, D.STATE_WORDS - 1, 4)           # the last M.SEL
        p.ldi(6, D.STATE_WORDS - 2, 4)           # the last track
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

            def fresh_ring():                    # TAPE starts from a silent ring
                p.ld(0, C["i"])
                p.lsh(1, 0, 11)
                p.iconst(12, D.TP_RING_DDR)
                p.iop(1, 12, "+", 1)
                p.seti(1, 1)
                p.fconst(0, 0.0)

                def sixteen():
                    for _ in range(16):
                        p.stpost(1, 0)
                p.loop_r(11, D.TP_RING // 16, sixteen)
            if D.TAPE in D.BUILT:                # dnfw.builder: no ring without TAPE
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
        p.ld(0, C["t"])
        p.lsh(1, 0, 2)
        p.iconst(12, D.BUFFERS)
        p.iop(2, 12, "+", 1)
        p.seti(4, 2)
        p.ldi(3, 0, 4)
        p.st(C["buf"], 3)
        fzd = D.FUZZ in D.BUILT or D.DIST in D.BUILT
        if fzd:                                  # FUZZ and DIST (when the guard admits them) set it:
            p.iconst(0, 0)                       # their shared loop, emitted once, runs after
            p.st(C["fz"], 0)
        _by_type(p, [(typ, (lambda fn, typ: lambda p: G.ins_admit(p, D.COST[typ], lambda: fn(p)))(fn, typ))
                     for typ, fn in ((D.FUZZ, fuzz), (D.TAPE, tape), (D.FOLD, fold), (D.HARM, harm),
                                     (D.SUB, sub), (D.DIST, dist), (D.GATER, gater), (D.RING, ring))
                     if typ in D.BUILT])         # dnfw.builder: only the inserts this build runs
        if fzd:
            p.ld(0, C["fz"])
            p.ifz(0, "NE", lambda: fz_loop(p))
        p.ld(2, C["sa"])
        p.seti(4, 2)
        for k in range(D.STATE_WORDS - 2):
            p.ld(8, C[f"s{k}"])
            p.sti(k, 4, 8)
    _is_built(p, run)


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
    """D.FLAGS from the records just unpacked (design.flags), 2026-11-10 (perf). Clobbers R0, R1,
    R5-R7, R11, R12, I4"""
    p.iconst(1, TABLE)
    p.seti(4, 1)
    for r in (5, 6, 7):
        p.iconst(r, 0)

    def rec():
        p.ldi(0, 0, 4)
        p.iconst(12, (1 << D.TYPE_BITS) - 1)
        p.iop(0, 0, "AND", 12)
        for r, group in ((5, D.BUILT), (6, D.POST), (7, D.BUS)):
            for typ in group:
                p.iconst(12, typ)
                p.if_(0, "EQ", 12, lambda r=r: p.iconst(r, 1), kind="i")
        p.geti(1, 4)
        p.iconst(12, 4 * D.FIELDS)
        p.iop(1, 12, "+", 1)
        p.seti(4, 1)
    p.loop_r(11, D.RECORDS, rec, one=12)
    for k, r in enumerate((5, 6, 7)):
        p.st(D.FLAGS + 4 * k, r)


def body(p: Prog) -> None:
    G.ins_start(p)
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
