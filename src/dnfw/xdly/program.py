"""XDLY's DSP code, in the DSL (dnfw.perc.dsl Prog): emitted as SHARC assembly (xdly.asm) and run
in Python as its exact model, held bit for bit to dnfw.xdly.ref (which spells out the design and
every operation's order); this module only says where each value lives.

**The slot.** The FX bus calls the stock delay with `CALL 0xb8482c (DB)` at sw 0x1c1c58 and its
two pushes (R4 = its DDR state 0x8005912c, R8 = its parameter struct 0x257934, R12 = the bus's
I/O descriptor 0x257e6c: +4 -> {in L, in R}, +0xc -> {out L, out R}, 32 floats each). The build
changes only that call's target, to wr_xdly (dnfw.waverider.dsp.XDLY_SW); wr_xdly saves every
register it uses, then

- TYPE (the frame's k 40, Delay FX Routing: the low half of DM 0x25cea4) not 0, and no clearing
  pending: restores every register and JUMPs to 0xb8482c, the stock delay entered as the bus
  called it (it returns to the bus, sw 0x1c1c5e, itself).
- TYPE changed to XDLY: starts with its times at once and nothing of its lines read (the fill
  count), so no clearing; to the stock delay: its 4 MB sample area (which XDLY's lines use) is
  cleared, 4096 words a block, the wet silent meanwhile (256 blocks, 171 ms), so neither an old
  stock tail nor XDLY's lines come back.
- TYPE 0: one block of XDLY into out L / R (the wet; the bus adds VOL as for the stock delay).
Both of ours return with the stock C epilogue.

The code in L2 (XDLY_SW), its words in L1 (STATE), its lines in the stock delay's DDR.

**2026-11-10: also the per-track XDLY inserts' engine** (dnfw.inserts.bus), as FDN8's: the bus pass
swaps an instance's words (DYN_WORDS from STATE: its lines' bases `la` / `lb` among them) in, sets MODE
to 1 and enters wr_xdly as a leaf call; MODE 1 runs one block of the instance (a fresh one, `cur` 0,
started first: its times set, nothing of its lines read), restores every register and returns with
JUMP (M14, I12).
"""

from __future__ import annotations

from ..fdn8 import program as FP
from ..perc.dsl import Mem, Prog
from . import design as D
from . import ref as R

STATE = 0x2E6E00                 # the last 512 B of FDN8's L1 block (dnfw.fdn8.program.STATE_BYTES)
STATE_BYTES = 0x200
TYPE_WORD = 0x25CEA4             # the frame image's k 40 (Delay FX Routing), low half
STOCK_DELAY = 0xB8482C

_NAMES = (["la", "lb", "mode", "im", "cur", "clr", "pos", "par", "io", "went", "wp", "fill", "q", "da", "db", "ya", "yb", "fa", "fb",
           "ta", "tb", "md", "g", "c", "x", "ia", "na", "kv", "any"]
          + [f"pr{k}" for k in range(6)]
          + [f"sv{k}" for k in range(16)] + ["svi0", "svi1", "svi2", "svi3", "svi4", "svi12", "sva"]
          + ["kf", "kn", "wl", "wr", "sn", "xb"])      # 2026-11-11: the second page (extras): after the words an instance swaps
C = {n: STATE + 4 * k for k, n in enumerate(_NAMES)}
assert len(C) == len(_NAMES), "a state word named twice"
assert STATE + 4 * len(_NAMES) <= STATE + STATE_BYTES
DYN_WORDS = (C["sv0"] - STATE) // 4               # an instance's words: STATE .. sv0


class _Abs:
    """the words at their own addresses (the sample loop of the send and the instances until 2026-11-14)"""

    @staticmethod
    def ld(p: Prog, r: int, n: str) -> None:
        p.ld(r, C[n])

    @staticmethod
    def st(p: Prog, n: str, r: int) -> None:
        p.st(C[n], r)

    @staticmethod
    def out(p: Prog, k: int, r: int) -> None:
        p.stpost(2 + k, r)


ABS = _Abs()


def state_bytes() -> bytes:
    """the L1 words at power-on: zeros (cur 0: the stock delay) but the lines' bases"""
    import struct
    w = [0] * (STATE_BYTES // 4)
    w[(C["la"] - STATE) // 4] = D.LINE_A
    w[(C["lb"] - STATE) // 4] = D.LINE_B
    return struct.pack(f"<{len(w)}I", *w)


def params(p: Prog) -> None:
    p.ld(4, C["par"])
    p.seti(4, 4)
    for k in range(6):
        p.ldi(0, k, 4)
        p.fconst(1, 0.0)
        p.fop(0, 0, "MAX", 1)
        p.fconst(1, 1.0)
        p.fop(0, 0, "MIN", 1)
        p.st(C[f"pr{k}"], 0)
    p.ld(0, C[f"pr{D.P_TIME}"])
    p.fconst(1, D.LOG2_TSPAN)
    p.fop(0, 0, "*", 1)
    p.fconst(1, D.LOG2_TMIN)
    p.fop(0, 0, "+", 1)
    FP.exp2(p)
    p.st(C["ta"], 0)
    p.ld(0, C[f"pr{D.P_WID}"])
    p.fconst(1, D.WID_TO_KNOB)
    p.fop(0, 0, "*", 1)
    p.fconst(1, 1.0)
    p.fop(0, 0, "MIN", 1)
    p.fconst(1, D.LOG2_TSPAN)
    p.fop(0, 0, "*", 1)
    p.fconst(1, D.LOG2_TMIN)
    p.fop(0, 0, "+", 1)
    FP.exp2(p)
    p.st(C["tb"], 0)
    p.ld(0, C[f"pr{D.P_HPF}"])
    p.fconst(1, D.MOD_GAIN)
    p.fop(0, 0, "*", 1)
    p.st(C["md"], 0)
    p.ld(0, C[f"pr{D.P_FDBK}"])
    p.fconst(1, D.FB_MAX)
    p.fop(0, 0, "*", 1)
    p.st(C["g"], 0)
    p.ld(0, C[f"pr{D.P_LPF}"])
    p.fconst(1, D.LOG2_TONE_SPAN)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, D.W_TONE)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 0)
    p.st(C["c"], 0)
    extras(p)


def extras(p: Prog) -> None:
    """the second page's values (design.EX, ref.Ref.extras) -> kf kn wl wr sn; the instances' (MODE 1) and a send
    before the ColdFire's first word: the constants. Clobbers R0, R12"""
    def defaults():
        p.fconst(0, D.KF)
        p.st(C["kf"], 0)
        p.fconst(0, D.KNEE)
        p.st(C["kn"], 0)
        p.fconst(0, 1.0)
        p.st(C["wl"], 0)
        p.fconst(0, 0.0)
        p.st(C["wr"], 0)
        p.st(C["sn"], 0)

    def real():
        for k, n in enumerate(("kf", "kn", "wl", "wr", "sn")):
            p.ld(0, D.EX + 4 * (k + 1))
            p.st(C[n], 0)

    def received():
        p.ld(0, D.EX)
        p.ifz(0, "EQ", defaults, real)
    p.ld(0, C["im"])
    p.ifz(0, "NE", defaults, received)


def start(p: Prog) -> None:
    p.iconst(0, 0)
    for n in ("fill", "q", "ya", "yb", "fa", "fb"):
        p.st(C[n], 0)
    p.ld(0, C["ta"])
    p.st(C["da"], 0)
    p.ld(0, C["tb"])
    p.st(C["db"], 0)


def knee(p: Prog, a=None) -> None:
    """F0 = knee(F0) (ref.knee); clobbers R1-R6, R12"""
    a = a or ABS
    a.st(p, "kv", 0)
    p.fconst(1, 0.0)
    p.fop(1, 1, "-", 0)
    p.fop(5, 0, "MAX", 1)                        # a

    def over():
        a.ld(p, 1, "kn")
        p.fop(0, 5, "-", 1)
        p.fconst(1, 2.0)
        p.fop(0, 0, "*", 1)
        p.fop(0, 0, "MIN", 1)                    # z
        p.fconst(1, R.LOG2E2)
        p.fop(0, 0, "*", 1)
        FP.exp2(p)
        p.fconst(1, 1.0)
        p.fop(0, 0, "+", 1)
        FP.recip(p)
        p.fconst(1, 2.0)
        p.fop(0, 0, "*", 1)
        p.fconst(1, 1.0)
        p.fop(0, 1, "-", 0)                      # tanh z
        p.fconst(1, 0.5)
        p.fop(0, 0, "*", 1)
        a.ld(p, 1, "kn")
        p.fop(0, 0, "+", 1)
        p.fconst(1, 1.0)
        p.fop(0, 0, "MIN", 1)                    # a
        from ..perc import program as PP         # 2026-11-20 (clip-inner): the loop squashed by 1 dB or more (or held
        p.fconst(1, 1.122)                       # at 1.0): a clip (the send's or the track's: entry, inserts.bus)
        p.fop(1, 0, "*", 1)
        PP.clip_flag(p, 1, "LT", 5, 5)           # (F5 = |x| > kn > 0: a nonzero word)
        a.ld(p, 6, "kv")
        p.fconst(1, 0.0)

        def neg():
            p.fop(0, 1, "-", 0)
        p.if_(6, "LE", 1, neg)

    def under():
        a.ld(p, 0, "kv")
    a.ld(p, 6, "kn")
    p.if_(5, "GT", 6, over, under)


def loop_in(p: Prog, f: str, y: str, xn: str = "x", a=None) -> None:
    """F0 = the line's input (ref.loop_in), F name f updated; the line's input x in C[xn] ('x', 'xb')"""
    a = a or ABS
    a.ld(p, 5, f)
    a.ld(p, 6, y)
    p.fop(2, 6, "-", 5)
    a.ld(p, 3, "c")
    p.fop(2, 2, "*", 3)
    p.fop(5, 5, "+", 2)
    p.fconst(2, 0.0)
    p.fop(2, 2, "-", 5)
    p.fop(2, 5, "MAX", 2)
    p.fconst(3, float(R.FLUSH))
    p.if_(2, "LT", 3, lambda: p.fconst(5, 0.0))
    a.st(p, f, 5)
    a.ld(p, 3, "g")
    p.fop(2, 5, "*", 3)
    a.ld(p, 0, xn)
    p.fop(0, 0, "+", 2)
    knee(p, a=a)


def line_word(p: Prog, base: str, idx: int, a=None) -> None:
    """I4 = the word of the line whose base is the word BASE ('la' / 'lb'), index R{idx} (already
    masked); clobbers R13, R14, R12"""
    a = a or ABS
    p.lsh(14, idx, 2)
    a.ld(p, 12, base)
    p.iop(13, 12, "+", 14)
    p.seti(4, 13)


def moved(p: Prog, d: str, y: str, a=None) -> None:
    """F0 = the time d moved by the other line's last output y (ref.moved)"""
    a = a or ABS
    a.ld(p, 1, y)
    a.ld(p, 2, "md")
    p.fop(0, 1, "*", 2)
    a.ld(p, 1, d)
    p.fop(0, 0, "*", 1)
    p.fop(0, 1, "+", 0)
    p.fconst(1, D.D_LO)
    p.fop(0, 0, "MAX", 1)
    p.fconst(1, D.D_HI)
    p.fop(0, 0, "MIN", 1)


def tap(p: Prog, base: str, a=None) -> None:
    """F0 = the line at BASE read F0 samples back (ref.tap); clobbers R1-R9, R12-R14"""
    a = a or ABS
    p.trunc(5, 0)                                # i
    a.ld(p, 6, "fill")

    def read():
        p.iconst(1, 0)
        p.float_(1, 5, 1)
        p.fop(7, 0, "-", 1)                      # fr
        a.ld(p, 8, "wp")
        p.iop(9, 8, "-", 5)
        p.iconst(12, D.LINE_MASK)
        p.iop(9, 9, "AND", 12)
        line_word(p, base, 9, a=a)
        p.ldi(2, 0, 4)                           # y0
        p.iconst(12, 1)
        p.iop(9, 12, "+", 5)                     # i + 1
        p.fconst(3, 0.0)

        def y1():
            p.iconst(12, 1)
            p.iop(9, 8, "-", 5)
            p.iop(9, 9, "-", 12)
            p.iconst(12, D.LINE_MASK)
            p.iop(9, 9, "AND", 12)
            line_word(p, base, 9, a=a)
            p.ldi(3, 0, 4)
        p.if_(9, "LT", 6, y1, kind="i")
        p.fop(3, 3, "-", 2)
        p.fop(3, 3, "*", 7)
        p.fop(0, 2, "+", 3)

    p.if_(5, "GE", 6, lambda: p.fconst(0, 0.0), read, kind="i")


def sample(p: Prog, a=None) -> None:
    """one sample; I0/I1 in, I2/I3 out; R11 the count (left alone)"""
    a = a or ABS
    p.ldpost(0, 0)
    p.ldpost(1, 1)
    p.fop(2, 0, "-", 1)                          # l - r
    p.fop(0, 0, "+", 1)
    p.fconst(1, 0.5)
    p.fop(0, 0, "*", 1)
    a.st(p, "x", 0)
    a.st(p, "xb", 0)
    a.ld(p, 3, "sn")
    p.fconst(4, 0.0)

    def spread():
        p.fop(2, 2, "*", 1)                      # d = (l - r) / 2
        p.fop(2, 2, "*", 3)                      # x sn
        p.fop(5, 0, "+", 2)
        a.st(p, "x", 5)
        p.fop(5, 0, "-", 2)
        a.st(p, "xb", 5)
    p.if_(3, "NE", 4, spread)
    core(p, a)


def core(p: Prog, a=None) -> None:
    """one sample after its x / xb (ref.Ref.block's loop): the times, the lines' inputs, the writes, the counts, the
    taps, the output"""
    a = a or ABS
    a.ld(p, 4, "kf")                             # 2026-11-21 (fx-fast): the two times' smoothing interleaved (A in R2 R3,
    a.ld(p, 2, "ta")                             # B in R6 R7), so B's loads and A's store ride on computes: the same
    a.ld(p, 3, "da")                             # operations on the same values
    p.fop(2, 2, "-", 3)
    a.ld(p, 6, "tb")
    p.fop(2, 2, "*", 4)
    a.ld(p, 7, "db")
    p.fop(3, 3, "+", 2)
    p.fop(6, 6, "-", 7)
    a.st(p, "da", 3)
    p.fop(6, 6, "*", 4)
    p.fop(7, 7, "+", 6)
    a.st(p, "db", 7)
    loop_in(p, "fa", "ya", a=a)
    a.st(p, "ia", 0)
    loop_in(p, "fb", "yb", "xb", a=a)
    p.fpass(7, 0)                                # ib
    a.ld(p, 8, "wp")
    p.iconst(12, 1)
    p.iop(8, 12, "+", 8)
    p.iconst(12, D.LINE_MASK)
    p.iop(8, 8, "AND", 12)
    a.st(p, "wp", 8)
    a.ld(p, 6, "ia")
    line_word(p, "la", 8, a=a)
    p.sti(0, 4, 6)
    line_word(p, "lb", 8, a=a)
    p.sti(0, 4, 7)
    # q: zeros written in a row on both
    a.ld(p, 0, "q")

    def zero_q():
        p.iconst(0, 0)

    def count_q():
        p.iconst(1, D.LINE)

        def inc():
            p.iconst(12, 1)
            p.iop(0, 12, "+", 0)
        p.if_(0, "LT", 1, inc, kind="i")
    p.fconst(1, 0.0)

    def b_test():
        p.if_(7, "NE", 1, zero_q, count_q)
    p.if_(6, "NE", 1, zero_q, b_test)
    a.st(p, "q", 0)
    a.ld(p, 0, "fill")
    p.iconst(1, D.LINE)

    def inc_fill():
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
    p.if_(0, "LT", 1, inc_fill, kind="i")
    a.st(p, "fill", 0)
    moved(p, "da", "yb", a=a)
    tap(p, "la", a=a)
    a.st(p, "na", 0)
    moved(p, "db", "ya", a=a)
    tap(p, "lb", a=a)
    a.st(p, "yb", 0)
    a.ld(p, 1, "na")
    a.st(p, "ya", 1)
    a.ld(p, 2, "wr")
    p.fconst(3, 0.0)

    def width():
        a.ld(p, 4, "wl")
        p.fop(5, 1, "*", 4)                      # na wl
        p.fop(6, 0, "*", 2)                      # nb wr
        p.fop(5, 5, "+", 6)
        p.fop(6, 0, "*", 4)                      # nb wl
        p.fop(7, 1, "*", 2)                      # na wr
        p.fop(6, 6, "+", 7)
        a.out(p, 0, 5)
        a.out(p, 1, 6)

    def hard():
        a.out(p, 0, 1)
        a.out(p, 1, 0)
    p.if_(2, "NE", 3, width, hard)


def silent_in(p: Prog) -> None:
    """C['any'] = 1 if any input word of the block is not 0.0"""
    io_ptrs(p)
    p.iconst(0, 0)
    p.st(C["any"], 0)

    def one():
        for i in (0, 1):
            p.ldpost(0, i)
            p.fconst(1, 0.0)

            def mark():
                p.iconst(2, 1)
                p.st(C["any"], 2)
            p.if_(0, "NE", 1, mark)
    p.loop_r(11, D.BLOCK, one)


# 2026-11-14 (insfx): the block's x / xb first (into L1 at XX, in pairs), then the sample loop with every word through
# I3 (C[...] - REL_BASE, all in -32..31: a move rides on a compute) and the outputs through I1 / I2: the same operations
# on the same values (test_xdly's A/B); False: the sample loop as it was
STAGED = True
REL_BASE = STATE + 4 * 32
assert all(-32 <= (a - REL_BASE) // 4 < 32 for a in C.values())


class _Rel:
    """the words through I3 at REL_BASE; x / xb from XX through I0 (x then xb, in the order loop_in reads them); the
    outputs through I1 (L) / I2 (R)"""

    @staticmethod
    def ld(p: Prog, r: int, n: str) -> None:
        if n in ("x", "xb"):
            p.ldpost(r, 0)
        else:
            p.ldi(r, (C[n] - REL_BASE) // 4, 3)

    @staticmethod
    def st(p: Prog, n: str, r: int) -> None:
        p.sti((C[n] - REL_BASE) // 4, 3, r)

    @staticmethod
    def out(p: Prog, k: int, r: int) -> None:
        p.stpost(1 + k, r)


REL = _Rel()


def _xx() -> int:
    from ..fdn8 import stages as FS                # FDN8's block buffers: free while XDLY runs
    return FS.bufs()[2]


def _front(p: Prog) -> None:
    """x and xb of the block's 32 samples into XX (x, xb a pair), as sample() works them out (the spread when sn is
    not 0). I0 / I1 in, I3 XX"""
    p.ld(3, C["sn"])
    p.fconst(4, 0.0)
    p.fconst(1, 0.5)

    def plain():
        p.ldpost(0, 0)
        p.ldpost(1, 1)
        p.fop(2, 0, "-", 1)                      # (l - r: left unused, as in sample())
        p.fop(0, 0, "+", 1)
        p.fconst(1, 0.5)
        p.fop(0, 0, "*", 1)
        p.stpost(3, 0)
        p.stpost(3, 0)

    def spread():
        p.ldpost(0, 0)
        p.ldpost(1, 1)
        p.fop(2, 0, "-", 1)
        p.fop(0, 0, "+", 1)
        p.fconst(1, 0.5)
        p.fop(0, 0, "*", 1)
        p.fop(2, 2, "*", 1)
        p.fop(2, 2, "*", 3)
        p.fop(5, 0, "+", 2)
        p.stpost(3, 5)
        p.fop(5, 0, "-", 2)
        p.stpost(3, 5)
    p.if_(3, "NE", 4, lambda: p.loop_r(11, D.BLOCK, spread), lambda: p.loop_r(11, D.BLOCK, plain))


def _staged_block(p: Prog) -> None:
    io_ptrs(p)
    p.geti(13, 2)                                # out L, out R (I2, I3 become XX's and the words')
    p.geti(14, 3)
    p.iconst(15, _xx())
    p.seti(3, 15)
    _front(p)
    p.iconst(15, _xx())
    p.seti(0, 15)
    p.seti(1, 13)
    p.seti(2, 14)
    p.iconst(15, REL_BASE)
    p.seti(3, 15)
    p.loop_r(11, D.BLOCK, lambda: core(p, REL))
    p.ldi(0, -2, 0)                              # x / xb's words as the sample loop leaves them
    p.st(C["x"], 0)
    p.ldi(0, -1, 0)
    p.st(C["xb"], 0)


def xdly_block(p: Prog) -> None:
    p.ld(0, C["q"])
    p.iconst(1, D.LINE)
    p.iconst(2, 1)
    p.st(C["any"], 2)
    p.if_(0, "GE", 1, lambda: silent_in(p), kind="i")
    p.ld(0, C["any"])

    def go():
        if STAGED:
            _staged_block(p)
            return
        io_ptrs(p)
        p.loop_r(11, D.BLOCK, lambda: sample(p))
    p.ifz(0, "NE", go, lambda: silence(p))


def clearing(p: Prog) -> None:
    """CHUNK words of the stock delay's sample area, then the wet silent"""
    p.ld(0, C["pos"])
    p.lsh(2, 0, 2)
    p.iconst(12, D.LINE_A)
    p.iop(2, 12, "+", 2)
    p.seti(4, 2)
    p.fconst(0, 0.0)

    def sixteen():
        for _ in range(16):
            p.stpost(4, 0)
    p.loop_r(11, D.CHUNK // 16, sixteen)
    p.ld(0, C["pos"])
    p.iconst(12, D.CHUNK)
    p.iop(0, 12, "+", 0)
    p.st(C["pos"], 0)
    p.ld(0, C["clr"])
    p.iconst(1, D.CHUNK)
    p.iop(0, 0, "-", 1)
    p.st(C["clr"], 0)
    silence(p)


def switch(p: Prog) -> None:
    """R1 the new type"""
    p.st(C["cur"], 1)
    p.iconst(0, 0)
    p.st(C["pos"], 0)

    def to_xdly():
        p.iconst(0, 0)
        p.st(C["clr"], 0)
        params(p)
        start(p)

    def to_stock():
        p.iconst(0, D.STOCK_WORDS)
        p.st(C["clr"], 0)
    p.ifz(1, "NE", to_xdly, to_stock)


SAVE_I = FP.SAVE_I


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


def ret(p: Prog) -> None:
    restore(p)
    if p.run:
        p.mem.put(C["went"], 2)
        return
    p.e("I12 = DM(M7, I6);")
    p.e("JUMP (M14, I12) (DB);")
    p.e("RFRAME;")
    p.e("NOP;")


def send(p: Prog) -> None:
    """the bus's call (MODE 0): the type asked for (a switch when it changed); the stock delay, when it is
    the type and nothing is to be cleared"""
    p.ld(0, C["sv8"])
    p.st(C["par"], 0)
    p.ld(0, C["sv12"])
    p.st(C["io"], 0)
    p.ld(0, TYPE_WORD)
    p.iconst(12, 0xFFFF)
    p.iop(0, 0, "AND", 12)
    p.iconst(1, 0)
    p.ifz(0, "EQ", lambda: p.iconst(1, 1))      # the type asked for: 1 XDLY
    p.ld(2, C["cur"])
    p.if_(1, "NE", 2, lambda: switch(p), kind="i")

    def go_stock():
        restore(p)
        if p.run:
            p.mem.put(C["went"], 1)
            return
        p.jump_abs("", STOCK_DELAY, "the stock delay, entered as the bus called it")

    def no_clear():
        p.ld(1, C["cur"])
        p.ifz(1, "EQ", go_stock)
    p.ld(0, C["clr"])
    p.ifz(0, "EQ", no_clear)


def instance(p: Prog) -> None:
    """MODE 1: the instance swapped in (dnfw.inserts.bus); a fresh one (cur 0) started (R1 = 1)"""
    p.ld(2, C["cur"])
    p.iconst(1, 1)
    p.if_(2, "NE", 1, lambda: switch(p), kind="i")


def entry(p: Prog) -> None:
    """after save(): the call's own part (send or instance), then one block (clearing, or XDLY), then back
    as the call came (the stock C epilogue to the bus, or JUMP (M14, I12) to the bus pass)"""
    if p.run:
        p.mem.put(C["went"], 0)
    p.ld(0, C["mode"])
    p.st(C["im"], 0)
    p.iconst(1, 0)
    p.st(C["mode"], 1)
    p.ifz(0, "NE", lambda: instance(p), lambda: send(p))
    if p.run and p.mem.get(C["went"]) == 1:     # (the model: the stock delay took the call)
        return
    p.ld(0, C["clr"])

    def ours():
        params(p)
        xdly_block(p)
    p.ifz(0, "NE", lambda: clearing(p), ours)
    p.ld(0, C["im"])
    from ..perc import guard as G, program as PP  # 2026-11-20 (clip-inner): the send's clip: the delay return's bit;
    from ..inserts import bus as BUS               # an instance's (a track's bus insert): the bus pass's track, C['t']
    p.ifz(0, "EQ", lambda: PP.clip_note_track(p, bit=G.CLIPTRK_RET + 0), lambda: PP.clip_note_track(p, BUS.C["t"]))
    p.ld(0, C["im"])

    def to_pass():
        restore(p)
        if not p.run:
            p.e("JUMP (M14, I12);", "back to the bus pass (dnfw.inserts.bus)")
            p.e("NOP;", "(never run: the if's own jump follows, and BRANCH-WIN wants 3 parcels")
            p.e("NOP;", " between two branches, scripts/gate_hwrules.py)")
    p.ifz(0, "NE", to_pass, lambda: ret(p))


def run_instance(mem: Mem) -> Prog:
    """the model of the bus pass's call (MODE 1 set, the instance's words in place)"""
    p = Prog("run", mem=mem)
    save(p)
    entry(p)
    return p


def io_ptrs(p: Prog) -> None:
    p.ld(13, C["io"])
    p.seti(4, 13)
    p.ldi(14, 1, 4)
    p.seti(4, 14)
    p.ldi(15, 0, 4)
    p.seti(0, 15)
    p.ldi(15, 1, 4)
    p.seti(1, 15)
    p.ld(13, C["io"])
    p.seti(4, 13)
    p.ldi(14, 3, 4)
    p.seti(4, 14)
    p.ldi(15, 0, 4)
    p.seti(2, 15)
    p.ldi(15, 1, 4)
    p.seti(3, 15)


def silence(p: Prog) -> None:
    io_ptrs(p)
    p.fconst(0, 0.0)

    def zero():
        p.stpost(2, 0)
        p.stpost(3, 0)
    p.loop_r(11, D.BLOCK, zero)


def program(prefix: str = "xd") -> str:
    p = Prog("emit", prefix=prefix)
    p.raw("// xdly.asm -- XDLY in the stock delay's slot (docs/xdly.md). GENERATED by")
    p.raw("// scripts/gen_xdly_asm.py from dnfw.xdly.program; do not edit by hand.")
    p.raw("")
    p.raw(".SECTION/PM seg_pmco;")
    p.raw("")
    p.raw(".GLOBAL wr_xdly.;")
    p.raw("wr_xdly.:")
    save(p)
    entry(p)
    p.emit_subs()
    p.raw(".wr_xdly..end:")
    p.raw("      .type wr_xdly.,STT_FUNC;")
    # 2026-11-20 (DRUM's room): the R12 loads nothing reads, folded (dnfw.perc.flow)
    from ..perc import flow as _FLOW
    return _FLOW.fold_text(p.text())


def run(mem: Mem, regs: dict[int, int]) -> tuple[str, Prog]:
    """the model: one call with R0..R15 = REGS on MEM -> ('stock' | 'ours', the Prog)"""
    p = Prog("run", mem=mem)
    for k, v in regs.items():
        p.r[k] = v & 0xFFFFFFFF
    save(p)
    entry(p)
    went = mem.get(C["went"])
    return ("stock" if went == 1 else "ours"), p
