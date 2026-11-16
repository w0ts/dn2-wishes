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

_NAMES = (["cur", "clr", "pos", "par", "io", "went", "wp", "fill", "q", "da", "db", "ya", "yb", "fa", "fb",
           "ta", "tb", "md", "g", "c", "x", "ia", "na", "kv", "any"]
          + [f"pr{k}" for k in range(6)]
          + [f"sv{k}" for k in range(16)] + ["svi0", "svi1", "svi2", "svi3", "svi4", "svi12", "sva"])
C = {n: STATE + 4 * k for k, n in enumerate(_NAMES)}
assert len(C) == len(_NAMES), "a state word named twice"
assert STATE + 4 * len(_NAMES) <= STATE + STATE_BYTES


def state_bytes() -> bytes:
    """the L1 words at power-on: zeros (cur 0: the stock delay)"""
    return bytes(STATE_BYTES)


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


def start(p: Prog) -> None:
    p.iconst(0, 0)
    for n in ("fill", "q", "ya", "yb", "fa", "fb"):
        p.st(C[n], 0)
    p.ld(0, C["ta"])
    p.st(C["da"], 0)
    p.ld(0, C["tb"])
    p.st(C["db"], 0)


def knee(p: Prog) -> None:
    """F0 = knee(F0) (ref.knee); clobbers R1-R6, R12"""
    p.st(C["kv"], 0)
    p.fconst(1, 0.0)
    p.fop(1, 1, "-", 0)
    p.fop(5, 0, "MAX", 1)                        # a

    def over():
        p.fconst(1, D.KNEE)
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
        p.fconst(1, D.KNEE)
        p.fop(0, 0, "+", 1)
        p.fconst(1, 1.0)
        p.fop(0, 0, "MIN", 1)                    # a
        p.ld(6, C["kv"])
        p.fconst(1, 0.0)

        def neg():
            p.fop(0, 1, "-", 0)
        p.if_(6, "LE", 1, neg)

    def under():
        p.ld(0, C["kv"])
    p.fconst(6, D.KNEE)
    p.if_(5, "GT", 6, over, under)


def loop_in(p: Prog, f: str, y: str) -> None:
    """F0 = the line's input (ref.loop_in), F name f updated; x in C['x']"""
    p.ld(5, C[f])
    p.ld(6, C[y])
    p.fop(2, 6, "-", 5)
    p.ld(3, C["c"])
    p.fop(2, 2, "*", 3)
    p.fop(5, 5, "+", 2)
    p.fconst(2, 0.0)
    p.fop(2, 2, "-", 5)
    p.fop(2, 5, "MAX", 2)
    p.fconst(3, float(R.FLUSH))
    p.if_(2, "LT", 3, lambda: p.fconst(5, 0.0))
    p.st(C[f], 5)
    p.ld(3, C["g"])
    p.fop(2, 5, "*", 3)
    p.ld(0, C["x"])
    p.fop(0, 0, "+", 2)
    knee(p)


def line_word(p: Prog, base: int, idx: int) -> None:
    """I4 = the word of the line at BASE, index R{idx} (already masked); clobbers R13, R14, R12"""
    p.lsh(14, idx, 2)
    p.iconst(12, base)
    p.iop(13, 12, "+", 14)
    p.seti(4, 13)


def moved(p: Prog, d: str, y: str) -> None:
    """F0 = the time d moved by the other line's last output y (ref.moved)"""
    p.ld(1, C[y])
    p.ld(2, C["md"])
    p.fop(0, 1, "*", 2)
    p.ld(1, C[d])
    p.fop(0, 0, "*", 1)
    p.fop(0, 1, "+", 0)
    p.fconst(1, D.D_LO)
    p.fop(0, 0, "MAX", 1)
    p.fconst(1, D.D_HI)
    p.fop(0, 0, "MIN", 1)


def tap(p: Prog, base: int) -> None:
    """F0 = the line at BASE read F0 samples back (ref.tap); clobbers R1-R9, R12-R14"""
    p.trunc(5, 0)                                # i
    p.ld(6, C["fill"])

    def read():
        p.iconst(1, 0)
        p.float_(1, 5, 1)
        p.fop(7, 0, "-", 1)                      # fr
        p.ld(8, C["wp"])
        p.iop(9, 8, "-", 5)
        p.iconst(12, D.LINE_MASK)
        p.iop(9, 9, "AND", 12)
        line_word(p, base, 9)
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
            line_word(p, base, 9)
            p.ldi(3, 0, 4)
        p.if_(9, "LT", 6, y1, kind="i")
        p.fop(3, 3, "-", 2)
        p.fop(3, 3, "*", 7)
        p.fop(0, 2, "+", 3)

    p.if_(5, "GE", 6, lambda: p.fconst(0, 0.0), read, kind="i")


def sample(p: Prog) -> None:
    """one sample; I0/I1 in, I2/I3 out; R11 the count (left alone)"""
    p.ldpost(0, 0)
    p.ldpost(1, 1)
    p.fop(0, 0, "+", 1)
    p.fconst(1, 0.5)
    p.fop(0, 0, "*", 1)
    p.st(C["x"], 0)
    p.fconst(4, D.KF)
    for t, d in (("ta", "da"), ("tb", "db")):
        p.ld(2, C[t])
        p.ld(3, C[d])
        p.fop(2, 2, "-", 3)
        p.fop(2, 2, "*", 4)
        p.fop(3, 3, "+", 2)
        p.st(C[d], 3)
    loop_in(p, "fa", "ya")
    p.st(C["ia"], 0)
    loop_in(p, "fb", "yb")
    p.fpass(7, 0)                                # ib
    p.ld(8, C["wp"])
    p.iconst(12, 1)
    p.iop(8, 12, "+", 8)
    p.iconst(12, D.LINE_MASK)
    p.iop(8, 8, "AND", 12)
    p.st(C["wp"], 8)
    p.ld(6, C["ia"])
    line_word(p, D.LINE_A, 8)
    p.sti(0, 4, 6)
    line_word(p, D.LINE_B, 8)
    p.sti(0, 4, 7)
    # q: zeros written in a row on both
    p.ld(0, C["q"])

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
    p.st(C["q"], 0)
    p.ld(0, C["fill"])
    p.iconst(1, D.LINE)

    def inc_fill():
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
    p.if_(0, "LT", 1, inc_fill, kind="i")
    p.st(C["fill"], 0)
    moved(p, "da", "yb")
    tap(p, D.LINE_A)
    p.st(C["na"], 0)
    moved(p, "db", "ya")
    tap(p, D.LINE_B)
    p.st(C["yb"], 0)
    p.ld(1, C["na"])
    p.st(C["ya"], 1)
    p.stpost(2, 1)
    p.stpost(3, 0)


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


def xdly_block(p: Prog) -> None:
    p.ld(0, C["q"])
    p.iconst(1, D.LINE)
    p.iconst(2, 1)
    p.st(C["any"], 2)
    p.if_(0, "GE", 1, lambda: silent_in(p), kind="i")
    p.ld(0, C["any"])

    def go():
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


def body(p: Prog) -> None:
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
    p.ld(0, C["clr"])

    def go_stock():
        restore(p)
        if p.run:
            p.mem.put(C["went"], 1)
            return
        p.jump_abs("", STOCK_DELAY, "the stock delay, entered as the bus called it")

    def run_one():
        p.ld(1, C["cur"])

        def ours():
            params(p)
            xdly_block(p)
            ret(p)
        p.ifz(1, "EQ", go_stock, ours)

    def clear():
        clearing(p)
        ret(p)
    p.ifz(0, "NE", clear, run_one)


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
    body(p)
    p.emit_subs()
    p.raw(".wr_xdly..end:")
    p.raw("      .type wr_xdly.,STT_FUNC;")
    return p.text()


def run(mem: Mem, regs: dict[int, int]) -> tuple[str, Prog]:
    """the model: one call with R0..R15 = REGS on MEM -> ('stock' | 'ours', the Prog)"""
    p = Prog("run", mem=mem)
    for k, v in regs.items():
        p.r[k] = v & 0xFFFFFFFF
    save(p)
    body(p)
    went = mem.get(C["went"])
    return ("stock" if went == 1 else "ours"), p
