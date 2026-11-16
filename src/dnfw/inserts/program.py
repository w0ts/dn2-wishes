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
"""

from __future__ import annotations

from ..fdn8 import program as FP
from ..perc import guard as G
from ..perc.dsl import Mem, Prog
from . import design as D

STATE = 0x200AF400               # L2: 32 x 32 bytes of state, after the code (dnfw.waverider.dsp)
STATE_BYTES = D.RECORDS * 4 * D.STATE_WORDS
SCRATCH = STATE + STATE_BYTES    # the pass's own words
TABLE = D.TABLE                  # the unpacked records (design.TABLE), and the last change word seen
_NAMES = ["t", "i", "j", "rec", "w1", "sa", "buf", "gn"] + [f"p{k}" for k in range(7)] + [f"s{k}" for k in range(8)] + [
    "g", "c", "b", "y0", "k", "thr", "cnt",
    "gd", "step", "lvl", "d", "rb", "sel", "tr"]
C = {n: SCRATCH + 4 * k for k, n in enumerate(_NAMES)}
assert len(C) == len(_NAMES)
SCRATCH_BYTES = 4 * len(_NAMES)


assert SCRATCH + SCRATCH_BYTES <= TABLE


def state_bytes() -> bytes:
    """the state, the pass's words, then the unpacked records and the last change word: zeros"""
    return bytes(TABLE + D.TABLE_BYTES - STATE)


def fuzz(p: Prog) -> None:
    """FUZZ over the buffer at C['buf'] (ref.Ref.fuzz); values p0 MIX, p1..p6, state s0..s5"""
    p.ld(0, C["p1"])
    p.fconst(1, D.FZ_DRIVE_OCT)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.st(C["g"], 0)
    p.ld(0, C["p2"])
    p.fconst(1, D.LOG2_TONE_SPAN)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.W_TONE)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 0)
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
    p.ld(0, C["p4"])
    p.fconst(1, D.FZ_PRE_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["k"], 0)
    p.ld(0, C["p5"])
    p.fconst(1, D.FZ_GATE_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["thr"], 0)
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
        p.fconst(1, D.FZ_PRE_A)
        p.fop(3, 3, "*", 1)
        p.fop(2, 2, "+", 3)
        p.st(C["s0"], 2)
        p.fop(3, 0, "-", 2)
        p.ld(1, C["k"])
        p.fop(3, 3, "*", 1)
        p.fop(5, 0, "+", 3)                      # xe
        p.fconst(1, 0.0)
        p.fop(1, 1, "-", 0)
        p.fop(6, 0, "MAX", 1)                    # a
        p.ld(2, C["s1"])
        p.fconst(1, D.FZ_ENV_REL)
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
        p.ld(1, C["p6"])
        p.fop(3, 2, "*", 1)
        p.ld(1, C["s2"])
        p.fop(3, 3, "*", 1)
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


def tone_c(p: Prog, src: str) -> None:
    """F0 = a one-pole's coefficient at 300 Hz x 40^C[src] (ref.Ref.tone_c)"""
    p.ld(0, C[src])
    p.fconst(1, D.LOG2_TONE_SPAN)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.W_TONE)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 0)


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
        _by_type(p, [(typ, (lambda fn, typ: lambda p: G.ins_admit(p, D.COST[typ], lambda: fn(p)))(fn, typ))
                     for typ, fn in ((D.FUZZ, fuzz), (D.TAPE, tape), (D.FOLD, fold), (D.HARM, harm))])
        p.ld(2, C["sa"])
        p.seti(4, 2)
        for k in range(D.STATE_WORDS - 2):
            p.ld(8, C[f"s{k}"])
            p.sti(k, 4, 8)
    _is_built(p, run)


def _is_built(p: Prog, run) -> None:
    """RUN once when M.SEL (C['sel']) is a type this build runs (design.BUILT): a flag first"""
    p.iconst(7, 0)
    for typ in D.BUILT:
        p.ld(5, C["sel"])
        p.iconst(6, typ)
        p.if_(5, "EQ", 6, lambda: p.iconst(7, 1), kind="i")
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
    p.ld(0, D.GEN)
    p.ld(1, TABLE + 4 * D.RECORDS * D.FIELDS)
    p.if_(0, "NE", 1, go, kind="i")


def body(p: Prog) -> None:
    G.ins_start(p)
    unpack(p, C)
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
    body(p)
    return p
