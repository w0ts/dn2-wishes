"""The stereo inserts after the pan (CHOR, WIDE, JUNO): their DSP code, in the DSL (dnfw.perc.dsl Prog),
emitted as SHARC assembly (inspost.asm) and run in Python as its exact model, held bit for bit to
dnfw.inserts.postref.

**Where it runs.** The engine calls the FX sends (sw 0x1c1738) with `CJUMP 0x1c1738 (DB)` at sw
0x1c3054, after the voice chain (filter, amp, pan) has left each voice slot's block in stereo
(design.STEREO) and before the sends and the routing read it. The build changes only that call's
target, to wr_inpost (dnfw.waverider.dsp.POST_SW): it saves every register it uses, runs the post
insert of each slot whose track asks for one, in place, restores everything and JUMPs to 0x1c1738,
which then runs as if the engine had called it.
"""

from __future__ import annotations

from ..fdn8 import program as FP
from ..perc import guard as G
from ..perc.dsl import Mem, Prog
from . import design as D
from . import program as PR

STATE = 0x2E3A40                 # L1 (perf, 2026-11-11; was L2 0x200B1000): dnfw.waverider.dsp.POST_STATE_DM
STATE_WORDS = 8                  # per slot: words 0..5 the insert's, 6 the last track, 7 the last M.SEL
STATE_BYTES = D.RECORDS * 4 * STATE_WORDS   # 2026-11-10: per voice slot and insert slot (i = 2 s + j)
WL = STATE + STATE_BYTES         # CHOR's wet, 32 + 32 words
WR = WL + 4 * D.BLOCK
SCRATCH = WR + 4 * D.BLOCK
SAVE_I = (0, 1, 2, 3, 4, 12)
_NAMES = (["t", "cnt", "tr", "sel", "i", "j", "rec", "sa", "rb", "lp", "rp"] + [f"p{k}" for k in range(7)]
          + [f"s{k}" for k in range(6)]
          + ["wg", "dl", "ab", "ct", "nv", "inc", "base", "dep", "fb", "k", "ph0", "v", "a0", "d",
             "step", "gl", "gr", "pos"]
          + [f"sv{k}" for k in range(16)] + [f"svi{i}" for i in SAVE_I] + ["sva", "bk", "bg"])
C = {n: SCRATCH + 4 * k for k, n in enumerate(_NAMES)}
SCRATCH_BYTES = 4 * len(_NAMES)
GW = {n: D.POST_GW_L2 + 4 * k for k, n in enumerate(("aa", "icost", "ist", "rbuf", "dl0", "dl31", "dr0", "dr31"))}
SENDS_SW = 0x1C1738              # the FX sends, the call's stock target
MASK = D.POST_RING - 1
# 2026-11-12 (opt-inserts): a tap's reads in a block lie in one span of its ring that the block does not write
# (the ring is written after the taps; design asserts every read is of an earlier block's samples). When the
# span does not wrap and fits, it is copied once to LINE (L1, transient: nothing in it outlives the tap) and
# the tap reads it there: its inner loop is unchanged, only the ring's base it adds moves. The same words, so
# the same output; 0: every read from the ring (DDR) as before. LINE is the Monomachine render scratch's IN
# (dnfw.waverider.dsp.MNM_RENDER_DM; the arbiter, juno-engine, 2026-11-12: 0x2e5400..0x2e5600 for this pass):
# every Monomachine-style voice rewrites it each render and none keeps state there, and this pass (and the
# JUNO send, jsend, at the same FX-sends call) runs after every voice has rendered. Nothing here may expect
# it to hold anything at the next block.
LINE = 0x2E5400
LINE_WORDS = 48
assert D.POST_RING_STRIDE == (1 << 12) + (1 << 4)       # run(): i << 12 + i << 4


# 2026-11-09: DRONE's BEAT (dnfw.mnm.drone): the side of its two ears, per voice slot, written by the
# machine before the chain (pre-amp) and mixed here after the pan, scaled by what the chain did to the mid
SIDE_L2 = 0x200B1800             # slot t's block at SIDE_L2 + SIDE_STRIDE t (dnfw.waverider.dsp)
SIDE_STRIDE = 0x90               # 36 words: 0..31 the side, 32 sum |mid| pre-amp, 33 flag (1.0), 34 last gain
SIDE_BYTES = 16 * SIDE_STRIDE
assert SIDE_L2 >= STATE + STATE_BYTES + 8 * D.BLOCK + 4 * len(_NAMES)
GAIN_MAX = 4.0                   # the side's gain at most (a mid the chain raised that much)


def _beat_built() -> bool:
    """a machine that writes a side block is built: DRONE (BEAT), ANALOG2 (WDTH, 2026-11-11)"""
    from ..mnm import machines as MM
    return "DRONE" in MM.NAMES or "ANALOG2" in MM.NAMES


def _recip(p: Prog, d: int, x: int) -> None:
    """Fd = 1 / Fx (Fx >= 1e-9 > 0): the integer seed from the float's bits, three Newton steps
    (dnfw.ping.live.recip's). Clobbers R12, R13."""
    p.iconst(12, 0x7EF311C7)
    p.iop(d, 12, "-", x)
    for _ in range(3):
        p.fop(13, x, "*", d)
        p.fconst(12, 2.0)
        p.fop(13, 12, "-", 13)
        p.fop(d, d, "*", 13)


def beat(p: Prog) -> None:
    """slot C['t']: DRONE's side, when it wrote one this block (flag), into the slot's stereo block:
    L += g s, R -= g s, g from the last block's gain to this one's over the block, this one's =
    (sum |L + R| / 2) / (sum |mid| pre-amp), at most GAIN_MAX: the amp envelope, the level, the pan
    and the filter's broadband gain, as the chain gave them to the mid. The flag is cleared; no
    flag: the last gain 0 (BEAT starts from silence)."""
    p.ld(0, C["t"])
    p.lsh(1, 0, 7)
    p.lsh(2, 0, 4)
    p.iconst(12, SIDE_L2)
    p.iop(3, 12, "+", 1)
    p.ipass(12, 3)
    p.iop(3, 12, "+", 2)
    p.seti(4, 3)
    p.ldi(5, 33, 4)
    p.fconst(6, 0.5)

    def on():
        p.fconst(6, 0.0)
        p.sti(33, 4, 6)
        p.ld(0, C["t"])
        p.lsh(1, 0, 8)
        p.iconst(12, D.STEREO)
        p.iop(1, 12, "+", 1)
        p.seti(0, 1)
        p.seti(2, 1)
        p.iconst(12, D.STEREO_R)
        p.iop(1, 12, "+", 1)
        p.seti(1, 1)
        p.seti(3, 1)
        p.fconst(7, 0.0)

        def acc():
            p.ldpost(8, 0)
            p.ldpost(9, 1)
            p.fop(8, 8, "+", 9)
            p.fconst(10, 0.0)
            p.fop(10, 10, "-", 8)
            p.fop(8, 8, "MAX", 10)
            p.fop(7, 7, "+", 8)
        p.loop(C["bk"], D.BLOCK, acc)
        p.fconst(12, 0.5)
        p.fop(7, 7, "*", 12)                     # sum |post mid|
        p.ldi(6, 32, 4)
        p.fconst(12, 1e-9)
        p.fop(6, 6, "MAX", 12)
        _recip(p, 8, 6)
        p.fop(7, 7, "*", 8)
        p.fconst(12, GAIN_MAX)
        p.fop(7, 7, "MIN", 12)                   # g, this block's
        p.ldi(9, 34, 4)                          # the last block's
        p.sti(34, 4, 7)
        p.fop(10, 7, "-", 9)
        p.fconst(12, 1.0 / D.BLOCK)
        p.fop(10, 10, "*", 12)                   # its step a sample
        p.ld(0, C["t"])
        p.lsh(1, 0, 8)
        p.iconst(12, D.STEREO)
        p.iop(1, 12, "+", 1)
        p.seti(0, 1)
        p.seti(2, 1)
        p.iconst(12, D.STEREO_R)
        p.iop(1, 12, "+", 1)
        p.seti(1, 1)
        p.seti(3, 1)
        p.ld(1, C["t"])                          # I4 back at the side's word 0
        p.lsh(2, 1, 7)
        p.lsh(3, 1, 4)
        p.iconst(12, SIDE_L2)
        p.iop(2, 12, "+", 2)
        p.ipass(12, 2)
        p.iop(2, 12, "+", 3)
        p.seti(4, 2)

        def mix():
            p.fop(9, 9, "+", 10)
            p.ldpost(5, 4)
            p.fop(5, 5, "*", 9)
            p.ldpost(6, 0)
            p.fop(6, 6, "+", 5)
            p.stpost(2, 6)
            p.ldpost(6, 1)
            p.fop(6, 6, "-", 5)
            p.stpost(3, 6)
        p.loop(C["bk"], D.BLOCK, mix)

    def off():
        p.fconst(6, 0.0)
        p.sti(34, 4, 6)
    p.if_(5, "GT", 6, on, off)


def state_bytes() -> bytes:
    return bytes(STATE_BYTES + 8 * D.BLOCK + SCRATCH_BYTES)


def save(p: Prog) -> None:
    for k in range(16):
        p.st(C[f"sv{k}"], k)
    for i in SAVE_I:
        p.e(f"DM({C[f'svi{i}']:#x}) = I{i};")
    p.e(f"DM({C['sva']:#x}) = ASTAT;")


def restore(p: Prog) -> None:
    p.e(f"ASTAT = DM({C['sva']:#x});")
    for i in SAVE_I:
        p.e(f"I{i} = DM({C[f'svi{i}']:#x});")
    for k in range(16):
        p.ld(k, C[f"sv{k}"])


def ring_at(p: Prog, idx: int, tmp: int) -> None:
    """I4 = the slot's ring word R{idx} (masked here); clobbers R12 and R{tmp}"""
    p.iconst(12, MASK)
    p.iop(idx, idx, "AND", 12)
    p.lsh(idx, idx, 2)
    p.ld(tmp, C["rb"])
    p.iop(idx, tmp, "+", idx)
    p.seti(4, idx)


def wide(p: Prog) -> None:
    """WIDE (postref.PostRef.wide); p0 MIX, p1 WDTH, p2 TIME, p3 BASS, p4 TONE; s0 wp, s1 lb, s2 lt"""
    p.ld(0, C["p1"])
    p.fconst(1, 2.0)
    p.fop(0, 0, "*", 1)
    p.st(C["wg"], 0)
    p.ld(0, C["p2"])
    p.fconst(1, D.WD_D_SPAN)
    p.fop(0, 0, "*", 1)
    p.fconst(1, D.WD_D_MIN)
    p.fop(0, 0, "+", 1)
    p.trunc(0, 0)
    p.st(C["dl"], 0)
    p.ld(0, C["p3"])
    p.fconst(1, D.LOG2_WB_SPAN)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.W_WB)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 0)
    p.st(C["ab"], 0)
    p.ld(0, C["p4"])
    p.fconst(1, D.LOG2_TONE_SPAN)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.W_TONE)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 0)
    p.st(C["ct"], 0)
    # perf (2026-11-11): two passes over the block. First m, the side times WDTH x 2 into WL, WR (L1 scratch)
    # and m into the ring (post-modified through I4; the write place is a multiple of 32 from a fresh slot
    # on, so only the last word can wrap: its address is R10's). Then the ring read (all writes are in:
    # a read is TIME >= 24 back, the ring holds 1024), the two one-poles and the mix.
    p.ld(9, C["s0"])                             # wp
    if p.run:
        assert p.r[9] % 32 == 0, "WIDE: the write place moves 32 a block from 0"
    p.ld(13, C["rb"])
    p.iconst(12, 1)
    p.iop(8, 12, "+", 9)
    p.iconst(12, MASK)
    p.iop(8, 8, "AND", 12)
    p.lsh(8, 8, 2)
    p.iop(8, 13, "+", 8)
    p.seti(4, 8)                                 # the first word
    p.iconst(12, D.BLOCK)
    p.iop(10, 12, "+", 9)
    p.iconst(12, MASK)
    p.iop(10, 10, "AND", 12)
    p.st(C["s0"], 10)                            # wp + 32
    p.lsh(10, 10, 2)
    p.iop(10, 13, "+", 10)                       # the last word's
    p.iconst(12, 1)
    p.iop(15, 12, "+", 9)
    p.lsh(15, 15, 2)
    p.ld(8, C["dl"])
    p.lsh(8, 8, 2)
    p.iop(15, 15, "-", 8)                        # t = 4 (wp + 1 - TIME): the first read, unmasked
    p.ld(4, C["lp"])
    p.seti(0, 4)
    p.ld(4, C["rp"])
    p.seti(1, 4)
    p.iconst(4, WL)
    p.seti(2, 4)
    p.iconst(4, WR)
    p.seti(3, 4)
    p.fconst(0, 0.5)
    p.ld(1, C["wg"])
    p.ldpost(8, 0)
    p.ldpost(9, 1)

    def first(last: bool = False):
        p.fop(2, 8, "+", 9)
        p.fop(2, 2, "*", 0)                      # m
        if last:
            p.seti(4, 10)
        p.stpost(4, 2)                           # the ring
        p.stpost(2, 2)
        p.fop(3, 8, "-", 9)
        p.fop(3, 3, "*", 0)
        p.ldpost(8, 0)                           # the next sample's l, r
        p.fop(3, 3, "*", 1)                      # the side x WDTH x 2
        p.ldpost(9, 1)
        p.stpost(3, 3)

    def four():
        for _ in range(4):
            first()
    p.loop_r(11, D.BLOCK // 4 - 1, four)
    for k in range(4):
        first(k == 3)
    p.ld(4, C["lp"])
    p.seti(0, 4)
    p.ld(4, C["rp"])
    p.seti(1, 4)
    p.iconst(4, WL)
    p.seti(2, 4)
    p.iconst(4, WR)
    p.seti(3, 4)
    p.ld(0, C["p0"])                             # R0 MIX, R3 ab, R4 ct, R5 WDTH, R6 lb, R7 lt, R10 4,
    p.ld(3, C["ab"])                             # R13 the ring's base, R14 4 MASK, R15 t
    p.ld(4, C["ct"])
    p.ld(5, C["p1"])
    p.ld(6, C["s1"])
    p.ld(7, C["s2"])
    p.iconst(10, 4)
    p.iconst(14, 4 * MASK)

    def second():
        p.iop(8, 15, "AND", 14)
        p.iop(8, 8, "+", 13)
        p.seti(4, 8)
        p.ldi(8, 0, 4)                           # d
        p.iop(15, 15, "+", 10)
        p.fop(9, 8, "-", 6)
        p.fop(9, 9, "*", 3)
        p.fop(6, 6, "+", 9)                      # lb
        p.fop(8, 8, "-", 6)                      # h
        p.fop(8, 8, "-", 7)
        p.fop(8, 8, "*", 4)
        p.fop(7, 7, "+", 8)                      # lt
        p.fop(9, 7, "*", 5)
        p.ldpost(1, 3)                           # the side x WDTH x 2
        p.fop(1, 1, "+", 9)                      # s'
        p.ldpost(2, 2)                           # m
        p.fop(8, 2, "+", 1)                      # lo
        p.fop(9, 2, "-", 1)                      # ro
        p.ldi(12, 0, 0)                          # l
        p.fop(8, 8, "-", 12)
        p.fop(8, 8, "*", 0)
        p.fop(8, 12, "+", 8)
        p.ldi(12, 0, 1)                          # r
        p.stpost(0, 8)
        p.fop(9, 9, "-", 12)
        p.fop(9, 9, "*", 0)
        p.fop(9, 12, "+", 9)
        p.stpost(1, 9)
    p.loop_r(11, D.BLOCK, second)
    p.st(C["s1"], 6)
    p.st(C["s2"], 7)


def chor_params(p: Prog) -> None:
    p.ld(0, C["p4"])
    p.fconst(1, D.CH_VOICES_K)
    p.fop(0, 0, "*", 1)
    p.trunc(0, 0)
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    p.st(C["nv"], 0)
    p.ld(0, C["p2"])
    p.fconst(1, D.LOG2_CR_SPAN)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.CH_RATE_LO * D.PH_PER_HZ)
    p.fop(0, 0, "*", 1)
    p.trunc(0, 0)
    p.st(C["inc"], 0)
    for dst, src, k, add in (("base", "p3", D.CH_DLY_SPAN, D.CH_DLY_MIN), ("dep", "p1", D.CH_DEP_MAX, None),
                             ("fb", "p6", D.CH_FB_MAX, None)):
        p.ld(0, C[src])
        p.fconst(1, k)
        p.fop(0, 0, "*", 1)
        if add is not None:
            p.fconst(1, add)
            p.fop(0, 0, "+", 1)
        p.st(C[dst], 0)
    p.ld(0, C["nv"])
    p.iconst(1, 0)
    p.float_(0, 0, 1)
    FP.recip(p)
    p.fconst(1, 2.0)
    p.fop(0, 0, "*", 1)
    p.st(C["k"], 0)
    p.ld(0, C["s0"])
    p.st(C["ph0"], 0)
    p.ld(12, C["inc"])
    p.iop(0, 12, "+", 0)
    p.st(C["s0"], 0)                             # ph1


def chor_voice(p: Prog) -> None:
    """one voice into the wet (WL, WR); leaves R10 (the voices' count) alone"""
    for ph, dst in (("ph0", "a0"), ("s0", "step")):
        p.ld(0, C["v"])
        p.lsh(0, 0, 30)
        p.ld(12, C[ph])
        p.iop(0, 12, "+", 0)
        FP.sine(p)
        p.ld(1, C["dep"])
        p.fop(0, 0, "*", 1)
        p.ld(1, C["base"])
        p.fop(0, 0, "+", 1)
        p.st(C[dst], 0)
    p.ld(1, C["a0"])
    p.st(C["d"], 1)
    p.ld(0, C["step"])
    p.fop(0, 0, "-", 1)
    p.fconst(1, 1 / D.BLOCK)
    p.fop(0, 0, "*", 1)
    p.st(C["step"], 0)
    p.fconst(5, 0.5)
    p.ld(0, C["v"])
    p.iconst(1, 1)
    p.iop(0, 0, "AND", 1)
    p.ifz(0, "NE", lambda: p.fconst(5, -0.5))
    p.ld(0, C["nv"])
    p.iconst(1, 1)
    p.if_(0, "EQ", 1, lambda: p.fconst(5, 0.0), kind="i")
    p.ld(1, C["p5"])
    p.fop(5, 1, "*", 5)                          # hw
    p.ld(4, C["k"])
    p.fconst(1, 0.5)
    p.fop(2, 1, "+", 5)
    p.fop(2, 2, "*", 4)
    p.st(C["gl"], 2)
    p.fop(2, 1, "-", 5)
    p.fop(2, 2, "*", 4)
    p.st(C["gr"], 2)
    p.ld(7, C["s1"])
    p.iconst(12, 1)
    p.iop(7, 12, "+", 7)
    p.st(C["pos"], 7)
    p.iconst(4, WL)
    p.seti(0, 4)
    p.iconst(4, WR)
    p.seti(1, 4)

    # perf (2026-11-11): the whole inner loop in registers, 4 samples a pass: R0 d, R1 step, R2 gl, R3 gr,
    # R4 0, R5 0xffc, R6 the ring's base, R7 4, R15 pos in bytes; R8, R9, R12, R13, R14 temporaries; I0 / I1 the
    # wet words, I2 the ring read (the compute's memory move may take I0..I3 only)
    p.ld(0, C["d"])
    p.ld(1, C["step"])
    p.ld(2, C["gl"])
    p.ld(3, C["gr"])
    p.iconst(4, 0)
    p.iconst(5, 4 * MASK)
    p.ld(6, C["rb"])
    p.iconst(7, 4)
    p.ld(15, C["pos"])
    p.lsh(15, 15, 2)
    if LINE:
        span(p)                                  # y0, y1 (the span reaches two words further back: copied, unread)

    def one():
        p.fop(0, 0, "+", 1)                      # d
        p.trunc(8, 0)                            # i
        p.lsh(9, 8, 2)
        p.iop(9, 15, "-", 9)                     # t = 4 (pos - i)
        p.iop(13, 9, "AND", 5)
        p.iop(13, 13, "+", 6)
        p.seti(2, 13)
        p.ldi(14, 0, 2)                          # y0
        p.float_(12, 8, 4)
        p.ldi(13, -1, 2)                         # y1: the word before (the ring's mirror at its first)
        p.fop(12, 0, "-", 12)                    # fr
        p.iop(15, 15, "+", 7)                    # pos
        p.fop(13, 13, "-", 14)
        p.fop(13, 13, "*", 12)
        p.fop(13, 14, "+", 13)                   # y
        p.ldi(9, 0, 0)                           # wet l
        p.fop(8, 13, "*", 2)
        p.ldi(14, 0, 1)                          # wet r
        p.fop(9, 9, "+", 8)
        p.stpost(0, 9)
        p.fop(8, 13, "*", 3)
        p.fop(14, 14, "+", 8)
        p.stpost(1, 14)

    def four():
        for _ in range(4):
            one()
    p.loop_r(11, D.BLOCK // 4, four)
    p.ld(0, C["v"])
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    p.st(C["v"], 0)


def chor(p: Prog) -> None:
    """CHOR (postref.PostRef.chor); p0 MIX, p1 DPTH, p2 RATE, p3 DLY, p4 VOIC, p5 WDTH, p6 FDBK;
    s0 the phase, s1 wp"""
    chor_params(p)
    p.ld(8, C["rb"])                             # the word before the ring = its last (the second tap of
    p.iconst(12, 4 * MASK)                       # a read at the ring's first word)
    p.iop(9, 8, "+", 12)
    p.seti(2, 9)
    p.ldi(9, 0, 2)
    p.seti(2, 8)
    p.sti(-1, 2, 9)
    p.iconst(4, WL)
    p.seti(0, 4)
    p.fconst(0, 0.0)

    def zero():                                  # WL, WR are one run of 64 words
        for _ in range(16):
            p.stpost(0, 0)
    p.loop_r(11, 2 * D.BLOCK // 16, zero)
    p.iconst(0, 0)
    p.st(C["v"], 0)
    p.ld(10, C["nv"])
    p.loop_r(10, None, lambda: chor_voice(p))
    p.ld(4, C["lp"])
    p.seti(0, 4)
    p.ld(4, C["rp"])
    p.seti(1, 4)
    p.iconst(4, WL)
    p.seti(2, 4)
    p.iconst(4, WR)
    p.seti(3, 4)

    # perf (2026-11-11): the block's ring writes go through I4 one word on each (the write place is a
    # multiple of 32 from a fresh slot on, +32 a block: only the block's last word can wrap, so its
    # address is set apart, R10), R0 MIX, R1 0.5, R4 FDBK; the next sample's four inputs are loaded in
    # this one's compute instructions
    p.ld(9, C["s1"])                             # wp
    if p.run:
        assert p.r[9] % 32 == 0, "CHOR: the write place moves 32 a block from 0"
    p.ld(13, C["rb"])
    p.iconst(12, 1)
    p.iop(8, 12, "+", 9)
    p.iconst(12, MASK)
    p.iop(8, 8, "AND", 12)
    p.lsh(8, 8, 2)
    p.iop(8, 13, "+", 8)
    p.seti(4, 8)                                 # the first word
    p.iconst(12, D.BLOCK)
    p.iop(10, 12, "+", 9)
    p.iconst(12, MASK)
    p.iop(10, 10, "AND", 12)
    p.st(C["s1"], 10)                            # wp + 32
    p.lsh(10, 10, 2)
    p.iop(10, 13, "+", 10)                       # the last word's
    p.ld(0, C["p0"])
    p.fconst(1, 0.5)
    p.ld(4, C["fb"])
    p.ldi(5, 0, 0)
    p.ldi(6, 0, 1)
    p.ldpost(2, 2)
    p.ldpost(3, 3)

    def sample(last: bool = False):
        p.fop(7, 5, "+", 6)
        p.fop(7, 7, "*", 1)                      # x
        p.fop(8, 2, "+", 3)
        p.fop(8, 8, "*", 1)
        p.fop(8, 8, "*", 4)
        p.fop(7, 7, "+", 8)
        if last:
            p.seti(4, 10)
        p.stpost(4, 7)                           # the ring
        p.fop(8, 2, "-", 5)
        p.ldpost(2, 2)                           # the next sample's wet l, r, l, r
        p.fop(8, 8, "*", 0)
        p.fop(8, 5, "+", 8)
        p.stpost(0, 8)
        p.fop(9, 3, "-", 6)
        p.fop(9, 9, "*", 0)
        p.ldpost(3, 3)
        p.fop(9, 6, "+", 9)
        p.ldi(5, 0, 0)
        p.ldi(6, 1, 1)
        p.stpost(1, 9)

    def four():
        for _ in range(4):
            sample()
    p.loop_r(11, D.BLOCK // 4 - 1, four)
    for k in range(4):
        sample(k == 3)


def _tri(p: Prog, d: int, ph: int) -> None:
    """Fd = the triangle at the phase R{ph}, less its middle (postref.PostRef.tri); clobbers R12"""
    p.lsh(d, ph, -16)
    p.iconst(12, 32768)
    p.iop(d, d, "-", 12)
    p.float0(d, d)
    p.fabs_(d, d)
    p.fconst(12, 16384.0)
    p.fop(d, d, "-", 12)


def juno_params(p: Prog) -> None:
    """MODE's phase step and depth, the block's two taps' starts and steps, MIX's gains (postref.PostRef.juno)"""
    J = D.JN
    p.ld(0, C["p1"])
    p.fconst(1, D.JN_MODE_K)
    p.fop(0, 0, "*", 1)
    p.trunc(0, 0)                                # MODE 0, 1, 2
    p.iconst(2, D.BLOCK * J["inc"][0])
    p.fconst(3, 2 * J["dep"][0])
    for md in (1, 2):
        def pick(md=md):
            p.iconst(2, D.BLOCK * J["inc"][md])
            p.fconst(3, 2 * J["dep"][md])
        p.iconst(1, md)
        p.if_(0, "EQ", 1, pick, kind="i")
    p.st(C["dep"], 3)
    p.ld(8, C["s0"])
    p.iop(9, 8, "+", 2)
    p.st(C["s0"], 9)                             # the phase at the block's end
    _tri(p, 4, 8)
    p.ld(3, C["dep"])
    p.fop(4, 4, "*", 3)
    p.fconst(5, J["base"])
    p.fop(6, 5, "+", 4)
    p.st(C["d"], 6)                              # the left tap's start
    p.fop(7, 5, "-", 4)
    p.st(C["a0"], 7)                             # the right's
    _tri(p, 4, 9)
    p.ld(3, C["dep"])
    p.fop(4, 4, "*", 3)
    p.fop(4, 5, "+", 4)
    p.fop(4, 4, "-", 6)
    p.fconst(12, 1 / D.BLOCK)
    p.fop(4, 4, "*", 12)
    p.st(C["step"], 4)                           # the left's step
    p.fconst(12, 0.0)
    p.fop(4, 12, "-", 4)
    p.st(C["k"], 4)                              # the right's
    p.ld(0, C["p0"])
    p.fconst(1, 1 - D.JN_GD)
    p.fop(1, 0, "*", 1)
    p.fconst(2, 1.0)
    p.fop(2, 2, "-", 1)
    p.st(C["gl"], 2)                             # the dry's gain
    p.fconst(1, D.JN_GW)
    p.fop(1, 0, "*", 1)
    p.st(C["gr"], 1)                             # the taps'


def juno_tap(p: Prog) -> None:
    """one tap over the block (Hermite, postref.PostRef.herm), from C['d'] by C['step'] into the words at C['v'];
    then the right tap's values move into those three. R0 d, R1 step, R2 0.5, R5 0xffc, R6 the ring's base,
    R7 4, R15 4 x the write place; I0 the wet, I2 the ring's read"""
    p.ld(0, C["d"])
    p.ld(1, C["step"])
    p.fconst(2, 0.5)
    p.iconst(5, 4 * MASK)
    p.ld(6, C["rb"])
    p.iconst(7, 4)
    p.ld(15, C["s1"])
    p.iconst(12, 1)
    p.iop(15, 15, "+", 12)
    p.lsh(15, 15, 2)
    p.ld(4, C["v"])
    p.seti(0, 4)
    if LINE:
        span(p)                                  # y0 .. y3: the word read and the three before it

    def one():
        p.fop(0, 0, "+", 1)                      # d
        p.trunc(8, 0)                            # i
        p.lsh(9, 8, 2)
        p.iop(9, 15, "-", 9)
        p.iop(13, 9, "AND", 5)
        p.iop(13, 13, "+", 6)
        p.seti(2, 13)                            # the ring at pos - i
        p.ldi(14, 0, 2)                          # y0 .. y3 (the mirror words before the ring at its first)
        p.ldi(3, -1, 2)
        p.ldi(4, -2, 2)
        p.ldi(10, -3, 2)
        p.float0(9, 8)
        p.fop(9, 0, "-", 9)                      # fr
        p.iop(15, 15, "+", 7)                    # pos
        p.fop(8, 3, "-", 4)                      # t1
        p.fop(10, 10, "-", 14)
        p.fop(10, 10, "*", 2)
        p.fop(13, 8, "*", 2)
        p.fop(13, 13, "+", 8)
        p.fop(10, 10, "+", 13)                   # c3
        p.fop(4, 4, "-", 14)
        p.fop(4, 4, "*", 2)                      # c1
        p.fop(14, 14, "-", 3)
        p.fop(14, 14, "+", 4)
        p.fop(14, 14, "-", 10)                   # c2
        p.fop(13, 10, "*", 9)
        p.fop(13, 13, "+", 14)
        p.fop(13, 13, "*", 9)
        p.fop(13, 13, "+", 4)
        p.fop(13, 13, "*", 9)
        p.fop(13, 13, "+", 3)
        p.stpost(0, 13)

    def two():
        one()
        one()
    p.loop_r(11, D.BLOCK // 2, two)
    for dst, src in (("d", "a0"), ("step", "k")):
        p.ld(0, C[src])
        p.st(C[dst], 0)
    p.iconst(0, WR)
    p.st(C["v"], 0)


SPAN_BACK = 3                    # the words before the one read that a tap reads (JUNO 3; CHOR 1, the span is one longer)


def span(p: Prog) -> None:
    """(one copy: a leaf subroutine) -- see _span"""
    p.call("span", lambda: _span(p, SPAN_BACK))


def _span(p: Prog, back: int) -> None:
    """2026-11-12: before a tap's block (R0 d, R1 step, R6 the ring's base, R15 4 x its first read's pos): the
    words it will read, 4 (pos - i) - 4 BACK .. 4 (pos - i) for pos = first .. first + 31 and i = trunc(d) as d
    moves by step, copied to LINE when they lie inside the ring unwrapped and fit; then R6 = LINE's base for
    them. i is bounded by d's first and last values (the last by a multiply, so one more each side for the
    rounding of the sum). Clobbers R8, R9, R11-R14, I3, I4; leaves R0-R7, R10, R15, I0-I2."""
    p.fop(8, 0, "+", 1)                          # d after the first step
    p.fconst(12, float(D.BLOCK))
    p.fop(9, 1, "*", 12)
    p.fop(9, 0, "+", 9)                          # .. after the last
    p.fop(13, 8, "MIN", 9)
    p.fop(14, 8, "MAX", 9)
    p.trunc(13, 13)
    p.trunc(14, 14)
    p.iconst(12, 1)
    p.iop(14, 14, "+", 12)                       # i at most
    p.iop(13, 13, "-", 12)                       # i at least
    p.lsh(14, 14, 2)
    p.iop(8, 15, "-", 14)
    p.iconst(12, 4 * back)
    p.iop(8, 8, "-", 12)                         # the span's first word (its offset from the ring, bytes)
    p.lsh(13, 13, 2)
    p.iop(9, 15, "-", 13)
    p.iconst(12, 4 * (D.BLOCK - 1))
    p.iop(9, 9, "+", 12)                         # its last word

    def up():                                    # all of it before the ring's first word: the AND puts it a
        p.iconst(12, 4 * D.POST_RING)            # ring's length up, in one run (a span across 0 is two)
        p.iop(8, 8, "+", 12)
        p.iop(9, 9, "+", 12)
    p.ifz(9, "LT", up)
    p.iconst(13, 0)                              # R13 = 1: it lies inside the ring (or its mirror) and fits
    p.iconst(12, -4 * back)

    def inside():
        p.iconst(12, 4 * MASK)

        def below_end():
            p.iop(11, 9, "-", 8)
            p.iconst(12, 4 * (LINE_WORDS - 1))
            p.if_(11, "LE", 12, lambda: p.iconst(13, 1), kind="i")
        p.if_(9, "LE", 12, below_end, kind="i")
    p.if_(8, "GE", 12, inside, kind="i")

    def copy():
        p.iop(11, 8, "+", 6)
        p.seti(3, 11)                            # the ring's span
        p.iop(11, 9, "-", 8)
        p.lsh(11, 11, -2)
        p.iconst(12, 1)
        p.iop(11, 11, "+", 12)                   # its words
        p.iconst(12, LINE)
        p.seti(4, 12)
        p.iop(14, 12, "-", 8)
        p.ipass(6, 14)                           # the base that maps the span's first word to LINE

        def word():
            p.ldpost(14, 3)
            p.stpost(4, 14)
        p.loop_r(11, None, word)
    p.ifz(13, "NE", copy)


def juno_lp(p: Prog) -> None:
    """the two low-passes over WL, WR in place (postref.PostRef.lp): R0 R1 the left's states, R2 R3 the right's,
    R4 a1, R5 a2, R6 g"""
    for k in range(4):
        p.ld(k, C[f"s{2 + k}"])
    p.fconst(4, D.JN["a1"])
    p.fconst(5, D.JN["a2"])
    p.fconst(6, D.JN["g"])
    p.iconst(7, WL)
    p.seti(0, 7)
    p.iconst(7, WR)
    p.seti(1, 7)

    def side(i: int, s0: int, s1: int):
        p.ldi(7, 0, i)
        p.fop(8, 7, "-", s1)                     # v3
        p.fop(9, s0, "*", 4)
        p.fop(10, 8, "*", 5)
        p.fop(9, 9, "+", 10)                     # v1
        p.fop(10, 9, "*", 6)
        p.fop(10, s1, "+", 10)                   # v2
        p.fop(13, 9, "+", 9)
        p.fop(s0, 13, "-", s0)
        p.fop(13, 10, "+", 10)
        p.fop(s1, 13, "-", s1)
        p.stpost(i, 10)

    def both():
        side(0, 0, 1)
        side(1, 2, 3)
    p.loop_r(11, D.BLOCK, both)
    for k in range(4):
        p.st(C[f"s{2 + k}"], k)


def juno(p: Prog) -> None:
    """JUNO (postref.PostRef.juno); p0 MIX, p1 MODE; s0 the triangle's phase, s1 wp, s2 s3 the left low-pass,
    s4 s5 the right's"""
    juno_params(p)
    p.ld(8, C["rb"])                             # the three words before the ring = its last three
    p.iconst(12, 4 * (MASK - 2))
    p.iop(9, 8, "+", 12)
    p.seti(2, 9)
    p.ldi(9, 0, 2)
    p.ldi(10, 1, 2)
    p.ldi(13, 2, 2)
    p.seti(2, 8)
    p.sti(-3, 2, 9)
    p.sti(-2, 2, 10)
    p.sti(-1, 2, 13)
    p.iconst(0, WL)
    p.st(C["v"], 0)
    p.loop(C["bk"], 2, lambda: juno_tap(p))      # the left tap into WL, then the right into WR
    juno_lp(p)
    p.ld(4, C["lp"])
    p.seti(0, 4)
    p.ld(4, C["rp"])
    p.seti(1, 4)
    p.iconst(4, WL)
    p.seti(2, 4)
    p.iconst(4, WR)
    p.seti(3, 4)
    p.ld(9, C["s1"])                             # wp (a multiple of 32: only the block's last write can wrap)
    if p.run:
        assert p.r[9] % 32 == 0, "JUNO: the write place moves 32 a block from 0"
    p.ld(13, C["rb"])
    p.iconst(12, 1)
    p.iop(8, 12, "+", 9)
    p.iconst(12, MASK)
    p.iop(8, 8, "AND", 12)
    p.lsh(8, 8, 2)
    p.iop(8, 13, "+", 8)
    p.seti(4, 8)                                 # the first word
    p.iconst(12, D.BLOCK)
    p.iop(10, 12, "+", 9)
    p.iconst(12, MASK)
    p.iop(10, 10, "AND", 12)
    p.st(C["s1"], 10)                            # wp + 32
    p.lsh(10, 10, 2)
    p.iop(10, 13, "+", 10)                       # the last word's
    p.ld(0, C["gl"])
    p.ld(1, C["gr"])
    p.fconst(2, 0.5)

    def sample(last: bool = False):
        p.ldi(8, 0, 0)                           # l
        p.ldi(9, 0, 1)                           # r
        p.fop(13, 8, "+", 9)
        p.fop(13, 13, "*", 2)
        if last:
            p.seti(4, 10)
        p.stpost(4, 13)                          # the ring
        p.fop(13, 8, "*", 0)
        p.ldpost(14, 2)
        p.fop(14, 14, "*", 1)
        p.fop(13, 13, "+", 14)
        p.stpost(0, 13)
        p.fop(13, 9, "*", 0)
        p.ldpost(14, 3)
        p.fop(14, 14, "*", 1)
        p.fop(13, 13, "+", 14)
        p.stpost(1, 13)
    p.loop_r(11, D.BLOCK - 1, sample)
    sample(True)


def slot(p: Prog) -> None:
    """voice slot C['t']: the track it plays (design.ROUTE), its M.SEL, then CHOR or WIDE"""
    p.ld(0, C["t"])
    p.lsh(1, 0, -1)
    p.lsh(1, 1, 2)
    p.iconst(12, D.ROUTE)
    p.iop(2, 12, "+", 1)
    p.seti(4, 2)
    p.ldi(3, 0, 4)
    p.iconst(12, 1)
    p.iop(1, 0, "AND", 12)
    p.ifz(1, "NE", lambda: p.lsh(3, 3, -16))
    p.iconst(12, 0xFFFF)
    p.iop(3, 3, "AND", 12)
    p.st(C["tr"], 3)
    PR.record(p, C)
    p.iconst(7, 0)
    for typ in D.POST:
        p.ld(5, C["sel"])
        p.iconst(6, typ)
        p.if_(5, "EQ", 6, lambda: p.iconst(7, 1), kind="i")
    p.ifz(7, "NE", lambda: run(p))


def run(p: Prog) -> None:
    p.ld(0, C["i"])
    p.lsh(1, 0, 5)
    p.iconst(12, STATE)
    p.iop(2, 12, "+", 1)
    p.st(C["sa"], 2)
    p.lsh(8, 0, 12)                              # RING_STRIDE (4 KB + 16) a voice slot and insert slot
    p.lsh(9, 0, 4)
    p.iop(8, 8, "+", 9)
    p.iconst(12, D.POST_RING_DDR + 4 * D.POST_MIRROR)   # the words before the ring mirror its last (CHOR: one, JUNO: three)
    p.iop(1, 12, "+", 8)
    p.st(C["rb"], 1)
    p.iconst(12, D.POST_AUX_L2)                  # its aux words (R9 = 16 i)
    p.iop(1, 12, "+", 9)
    p.st(GW["aa"], 1)
    p.ld(0, C["t"])
    p.lsh(1, 0, 8)                               # the voice slot's stereo block
    p.iconst(12, D.STEREO)
    p.iop(1, 12, "+", 1)
    p.st(C["lp"], 1)
    p.iconst(12, D.STEREO_R)
    p.iop(1, 12, "+", 1)
    p.st(C["rp"], 1)
    p.ld(2, C["sa"])
    p.seti(4, 2)
    p.ldi(7, STATE_WORDS - 1, 4)
    p.ldi(6, STATE_WORDS - 2, 4)
    p.ld(5, C["sel"])
    p.ld(8, C["tr"])
    p.iconst(9, 0)
    p.if_(7, "NE", 5, lambda: p.iconst(9, 1), kind="i")
    p.if_(6, "NE", 8, lambda: p.iconst(9, 1), kind="i")

    def fresh():
        p.ld(2, C["sa"])
        p.seti(4, 2)
        p.iconst(9, 0)
        for k in range(STATE_WORDS - 2):
            p.sti(k, 4, 9)
        p.ld(8, C["tr"])
        p.ld(5, C["sel"])
        p.sti(STATE_WORDS - 2, 4, 8)
        p.sti(STATE_WORDS - 1, 4, 5)
        p.ld(2, GW["aa"])
        p.seti(4, 2)
        for k in range(D.AUX_WORDS):
            p.sti(k, 4, 9)
        p.ld(1, C["rb"])
        p.seti(0, 1)
        p.fconst(0, 0.0)

        def sixteen():
            for _ in range(16):
                p.stpost(0, 0)
        p.loop_r(11, D.POST_RING // 16, sixteen)
    p.ifz(9, "NE", fresh)
    p.ld(2, C["sa"])
    p.seti(4, 2)
    for k in range(6):
        p.ldi(8, k, 4)
        p.st(C[f"s{k}"], 8)
    PR.values(p, C)

    def by_type(wide_, juno_, chor_):
        p.ld(5, C["sel"])
        p.iconst(6, D.WIDE)

        def not_wide():
            p.ld(5, C["sel"])
            p.iconst(6, D.JUNO)
            p.if_(5, "EQ", 6, juno_, chor_, kind="i")
        p.if_(5, "EQ", 6, wide_, not_wide, kind="i")

    def cost(typ):
        return lambda: (p.iconst(1, D.COST[typ]), p.st(GW["icost"], 1))
    by_type(cost(D.WIDE), cost(D.JUNO), cost(D.CHOR))
    for side, d0, d31 in (("lp", "dl0", "dl31"), ("rp", "dr0", "dr31")):
        PR.dry_ends(p, C[side], GW[d0], GW[d31])
    G.ins_gate(p, GW["icost"], GW["aa"], GW["ist"], lambda: by_type(lambda: wide(p), lambda: juno(p), lambda: chor(p)))
    for k, (side, d0, d31) in enumerate((("lp", "dl0", "dl31"), ("rp", "dr0", "dr31"))):
        p.ld(0, C[side])
        p.st(GW["rbuf"], 0)
        PR.smooth(p, GW["aa"], GW["ist"], GW["rbuf"], GW[d0], GW[d31], k)
    p.ld(2, C["sa"])
    p.seti(4, 2)
    for k in range(6):
        p.ld(8, C[f"s{k}"])
        p.sti(k, 4, 8)


def body(p: Prog) -> None:
    p.ld(0, D.FLAGS + 4)                         # (perf, 2026-11-10) no POST record: nothing to walk
    p.ifz(0, "NE", lambda: _walk(p))


def _walk(p: Prog) -> None:
    p.iconst(0, 0)
    p.st(C["i"], 0)
    p.iconst(0, D.RECORDS)
    p.st(C["cnt"], 0)
    top = p.label("slot")
    p.place(top)

    def each():
        p.ld(0, C["i"])
        p.lsh(1, 0, -1)
        p.st(C["t"], 1)
        p.iconst(12, 1)
        p.iop(1, 0, "AND", 12)
        p.st(C["j"], 1)
        if _beat_built():                        # 2026-11-10: DRONE's BEAT, once a slot, before its inserts
            p.ld(1, C["j"])
            p.ifz(1, "EQ", lambda: beat(p))
        slot(p)
        p.ld(0, C["i"])
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
        p.st(C["i"], 0)
        p.ld(0, C["cnt"])
        p.iconst(12, 1)
        p.iop(0, 0, "-", 12)
        p.st(C["cnt"], 0)
    if p.run:
        while True:
            each()
            if p.r[0] == 0:
                break
        return
    each()
    p.jump("NE", top)


def program(prefix: str = "ip") -> str:
    p = Prog("emit", prefix=prefix)
    p.raw("// inspost.asm -- the stereo inserts after the pan, CHOR and WIDE (docs/inserts.md). GENERATED")
    p.raw("// by scripts/gen_inserts_asm.py from dnfw.inserts.post; do not edit by hand.")
    p.raw("")
    p.raw(".SECTION/PM seg_pmco;")
    p.raw("")
    p.raw(".GLOBAL wr_inpost.;")
    p.raw("wr_inpost.:")
    save(p)
    G.ins_start(p)
    body(p)
    G.ins_end(p)
    restore(p)
    p.jump_abs("", SENDS_SW, "the FX sends, entered as the engine called them")
    p.emit_subs()
    p.raw(".wr_inpost..end:")
    p.raw("      .type wr_inpost.,STT_FUNC;")
    return p.text()


def model(mem: Mem, regs: dict[int, int] | None = None) -> Prog:
    """the model: one call with R0..R15 = REGS on MEM (the registers come back as they went in)"""
    p = Prog("run", mem=mem)
    for k, v in (regs or {}).items():
        p.r[k] = v & 0xFFFFFFFF
    save(p)
    body(p)
    restore(p)
    return p
