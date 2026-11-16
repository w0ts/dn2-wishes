"""FDN8's tank stage by stage over the block (2026-11-14, insfx): the same operations on the same values as
dnfw.fdn8.program.sample run sample by sample, only in another order, so the output and every ring word are the
same bit for bit (test/test_fdn8_stages.py holds the two programs to each other).

**Why the order may change.** Sample n of a block reads and writes ring word (p0 - n + off) for each tap's offset
OFF (p0 the block's write index, counting down). Two accesses (sample n, offset a) and (sample m, offset b) meet on
one word only when a - b = n - m, so |a - b| <= 31. Running stage X over all 32 samples before stage Y keeps every
such pair in its sample-by-sample order unless Y's access comes first there: Y at sample m < n with b = a - (n - m),
i.e. Y's offset 1..31 BELOW X's (or X's write feeding back to an earlier read of Y with a - b in 1..31). The
layout (dnfw.fdn8.design.layout) rules both out:

- the pre-delay's write (offset 0) and read (pd, 0..PD_MAX): read >= write, so stage order is sample order;
- a diffuser reads RA + A and writes RA, A >= 79 > 31; the next region starts past the previous one's read
  (RA_k + A_k + 1 = RA_k+1), the pre-delay's read ends at PD_MAX < RA_0;
- a line reads RL + D (D >= L + CM - 0.5 - DEPTH_MAX > 2,900) and RL + D + 1, and is written at RL; its read
  ends at RL + L + 2 CM + 1 < RL_next = RL + L + SP;
- nothing in the ring below offset 0 or past RB_END (< RING_WORDS - 31).

So: the input filters and the pre-delay's writes; the pre-delay's reads with diffuser 0, then diffusers 1..3, x
in L1 between them; each line over the block (its second tap is the word its first tap read a sample before:
u1(n) = u0(n - 1), one read a sample instead of two), its f into L1, the sum s and the output's L / R
accumulated in the order the sample loop adds them; the lines' writes from f, s / 4 and the diffusers' out; the
output gain and width. A tap's run of 32 words is walked by post-modify; where it crosses the ring's start the
stage's loop is split there (a stage's body is one subroutine, called once a segment).

**Where.** The block's buffers in FDN8's own L1 state (after the variant tables, BUF_BYTES), written before they
are read in every block; the bookkeeping in the t0..t7 / f0..f3 words (params()' spills, dead outside it).
"""

from __future__ import annotations

from ..perc.dsl import Prog
from . import design as D
from . import program as P

BLOCK = D.BLOCK
BUF_BYTES = 4 * BLOCK * 10                        # X, S, F0..F7


def lr_bufs() -> tuple[int, int]:
    """(L, R): the lines' output sums (sample n at +4 n), in the free tail of XDLY's L1 words (the last 512 B of
    FDN8's L1 block; XDLY never runs while FDN8 does)"""
    from ..xdly import program as XP
    at = XP.STATE + 4 * len(XP._NAMES)
    assert at + 8 * BLOCK <= XP.STATE + XP.STATE_BYTES, "FDN8's L / R past XDLY's L1 words"
    return at, at + 4 * BLOCK


def bufs() -> tuple[int, int, int]:
    """(X, S, F): the diffusers' x (sample n at X + 4 (31 - n)), the lines' sum s / s4 (S + 4 n), line k's f
    (F + 128 k + 4 n)"""
    at = P.VT2 + 4 * P.NV
    assert at + BUF_BYTES <= P.STATE + P.STATE_BYTES, "FDN8's block buffers past its L1 state"
    return at, at + 4 * BLOCK, at + 8 * BLOCK


def _w(n: str) -> int:
    return P.C[n]


# the drivers' words: a stream's samples before its wrap (w0..w2), what is left (rem), this segment's count (n)
W = {"w0": "t0", "w1": "t1", "w2": "t2", "rem": "t6", "n": "t7"}
IO = {"inl": "f0", "inr": "f1", "outl": "f2", "outr": "f3"}
RING_INC = P.MASK4 + 4                             # what an I register crossing the ring's start gets back


def start(p: Prog, i: int, off, mask: int = 9, base: int = 10, extra: int = 0) -> None:
    """I<i> = the ring word at p0 + OFF (+ EXTRA bytes): OFF words (an int), a state word holding its bytes (a name),
    or None: R14 holds its bytes. R8 p0's bytes, R<mask> / R<base> the ring's. Leaves R13 = its byte offset in the
    ring. Clobbers R13, R14"""
    if isinstance(off, int):
        p.iconst(14, off * 4 + extra)
    else:
        if off is not None:
            p.ld(14, P.C[off] if off in P.C else P.A[off])
        if extra:
            p.iconst(13, extra)
            p.iop(14, 14, "+", 13)
    p.iop(13, 8, "+", 14)
    p.iop(13, 13, "AND", mask)
    p.iop(14, 13, "OR", base)
    p.seti(i, 14)


def until_wrap(p: Prog, word: str | None = None) -> None:
    """R11 = the samples before the stream just started (R13 its byte offset) crosses the ring's start, at most
    the block's; into WORD if given"""
    p.lsh(11, 13, -2)
    p.iconst(14, 1)
    p.iop(11, 11, "+", 14)
    p.iconst(14, BLOCK)
    p.iop(11, 11, "MIN", 14)
    if word:
        p.st(_w(W[word]), 11)


def seg_call(p: Prog, name: str, body) -> None:
    """BODY R11 times (R11 > 0), in the subroutine NAME (one copy, however many calls)"""
    p.call(name, lambda: p.loop_r(11, None, body))


def seg(p: Prog, name: str, body, body2=None) -> None:
    """a segment of R11 samples: BODY2 (two samples a pass) R11 / 2 times when R11 is the whole block, else BODY"""
    if body2 is None:
        seg_call(p, name, body)
        return
    p.iconst(14, BLOCK)

    def whole():
        p.iconst(11, BLOCK // 2)
        seg_call(p, name + "2", body2)
    p.if_(11, "EQ", 14, whole, lambda: seg_call(p, name, body), kind="i")


def run1(p: Prog, name: str, i: int, inc, body, body2=None) -> None:
    """one ring stream (I<i>, started by start(); R13 its offset): BODY over the block, in two calls when the
    stream crosses the ring's start (I<i> then moved up by INC bytes: an int, or a mask word's (value | 3) + 1);
    BODY2 (two samples a pass) when it does not"""
    until_wrap(p, "n")
    seg(p, name, body, body2)
    p.ld(0, _w(W["n"]))
    p.iconst(1, BLOCK)
    p.iop(11, 1, "-", 0)

    def rest():
        _wrap_i(p, i, inc)
        seg_call(p, name, body)
    p.ifz(11, "NE", rest)


def _wrap_i(p: Prog, i: int, inc) -> None:
    p.geti(13, i)
    if isinstance(inc, int):
        p.iconst(14, inc)
    else:                                           # a mask word: MASK4 (0x7fffc) or an L2 ring's 4 x 1024 - 1
        p.ld(14, _w(inc))
        p.iconst(1, 3)
        p.iop(14, 14, "OR", 1)
        p.iconst(1, 1)
        p.iop(14, 14, "+", 1)
    p.iop(13, 13, "+", 14)
    p.seti(i, 13)


def run_n(p: Prog, name: str, streams, body, body2=None) -> None:
    """several ring streams [(I, its words-before-wrap word, INC)]: BODY over the block in segments, each up to the
    next crossing of any stream (at most one each in a block)"""
    p.iconst(0, BLOCK)
    p.st(_w(W["rem"]), 0)

    def segment():
        p.ld(11, _w(W["rem"]))
        for _, wn, _ in streams:
            p.ld(1, _w(W[wn]))
            p.iop(11, 11, "MIN", 1)
        p.st(_w(W["n"]), 11)
        seg(p, name, body, body2)
        for i, wn, inc in streams:
            p.ld(13, _w(W[wn]))
            p.ld(2, _w(W["n"]))
            p.iop(13, 13, "-", 2)

            def wrapped(i=i, inc=inc):
                _wrap_i(p, i, inc)
                p.iconst(13, 1 << 20)               # (never again this block)
            p.ifz(13, "EQ", wrapped)
            p.st(_w(W[wn]), 13)
        p.ld(13, _w(W["rem"]))
        p.ld(2, _w(W["n"]))
        p.iop(13, 13, "-", 2)
        p.st(_w(W["rem"]), 13)
    _repeat(p, segment, 13)


def _repeat(p: Prog, body, reg: int) -> None:
    """do BODY while R<reg> (set by it) is not 0: the test and the jump back, as a loop's"""
    if not p.run:
        top = p.label("seg")
        p.place(top)
        body()
        p.ipass(reg, reg)
        p.jump("NE", top)
        return
    while True:
        p.known.clear()                             # (the top label)
        p._mg = p._mv = None
        body()
        p.ipass(reg, reg)
        p.e("IF NE JUMP 0x0;")                      # (run mode: its one step)
        if p.r[reg] == 0:
            return


# -- the stages ------------------------------------------------------------------------

def io_words(p: Prog) -> None:
    """the I/O pointers (program.io_ptrs) into words"""
    P.io_ptrs(p)
    for i, n in ((0, "inl"), (1, "inr"), (2, "outl"), (3, "outr")):
        p.geti(13, i)
        p.st(_w(IO[n]), 13)


def ring_regs(p: Prog) -> None:
    """R8 p0's bytes (the block's write index, as stored), R9 the ring's mask, R10 its base"""
    p.ld(8, P.C["p4"])
    p.iconst(9, P.MASK4)
    p.ld(10, P.C["ring"])


def _input(p: Prog) -> None:
    """the send's sum x gh, the HPF and LPF one-poles, into the pre-delay (ring offset RB_PD)"""
    p.ld(0, _w(IO["inl"]))
    p.seti(0, 0)
    p.ld(0, _w(IO["inr"]))
    p.seti(1, 0)
    p.ld(4, P.C["gh"])
    p.ld(5, P.C["hs"])
    p.ld(6, P.C["ah"])
    p.ld(7, P.C["ls"])
    p.ld(3, P.C["al"])
    ring_regs(p)
    start(p, 2, D.RB_PD)

    def body():
        p.ldpost(0, 0)
        p.ldpost(1, 1)
        p.fop(0, 0, "+", 1)
        p.fop(0, 0, "*", 4)                         # xin
        p.fop(2, 0, "-", 5)
        p.fop(2, 6, "*", 2)
        p.fop(5, 5, "+", 2)                         # hs
        p.fop(0, 0, "-", 5)
        p.fop(2, 0, "-", 7)
        p.fop(2, 3, "*", 2)
        p.fop(7, 7, "+", 2)                         # ls
        p.stm(2, 7)                                 # the pre-delay
    run1(p, "fd_in", 2, RING_INC, body)
    p.st(P.C["hs"], 5)
    p.st(P.C["ls"], 7)


def _diff_body(p: Prog) -> None:
    """x (I0, down) through diffuser k: b (I1, down) the read, v (I2, down) the write; x out (I3, down). F5 g"""
    p.ldm(1, 1)                                     # b
    p.ldm(0, 0)                                     # x (rides on the product)
    p.fop(2, 5, "*", 1)
    p.fop(2, 0, "+", 2)                             # v
    p.fop(3, 5, "*", 2)
    p.stm(2, 2)                                     # (on the product)
    p.fop(0, 1, "-", 3)
    p.stm(3, 0)


def _diff_pair(p: Prog) -> None:
    """_diff_body for two samples, A then B: the same operations on each, B's moves riding on A's computes"""
    p.ldm(1, 1)                                     # bA
    p.ldm(0, 0)                                     # xA
    p.fop(2, 5, "*", 1)
    p.fop(2, 0, "+", 2)                             # vA
    p.ldm(4, 0)                                     # xB
    p.fop(3, 5, "*", 2)
    p.stm(2, 2)                                     # vA
    p.fop(0, 1, "-", 3)                             # A's x out
    p.ldm(1, 1)                                     # bB
    p.fop(2, 5, "*", 1)
    p.stm(3, 0)
    p.fop(2, 4, "+", 2)                             # vB
    p.fop(3, 5, "*", 2)
    p.stm(2, 2)                                     # vB
    p.fop(0, 1, "-", 3)
    p.stm(3, 0)


def _k_at(p: Prog, d: int, base: int, shift: int = 0) -> None:
    """R<d> = BASE + (k4 << SHIFT), k4 = 4 k the loop's index (word t4). Clobbers R13, R14"""
    p.ld(13, _w("t4"))
    if shift:
        p.lsh(13, 13, shift)
    p.iconst(14, base)
    p.iop(d, 14, "+", 13)


def _k_loop(p: Prog, n: int, body) -> None:
    """BODY for k = 0 .. N - 1 (k4 = 4 k in word t4; the count in word t3)"""
    p.iconst(0, 0)
    p.st(_w("t4"), 0)

    def one():
        body()
        p.ld(13, _w("t4"))
        p.iconst(14, 4)
        p.iop(13, 13, "+", 14)
        p.st(_w("t4"), 13)
    p.loop(_w("t3"), n, one)


def _diffusers(p: Prog) -> None:
    """for k = 0..3: diffuser k over the block, x from the pre-delay's read (k 0) or X, into X"""
    X, _, _ = bufs()

    def one():
        ring_regs(p)
        p.ld(4, P.C["dmask"])
        p.ld(15, P.C["dbase"])
        _k_at(p, 14, P.A["db0"])
        p.seti(4, 14)
        p.ldi(14, 0, 4)
        start(p, 1, None, 4, 15)
        until_wrap(p, "w1")
        _k_at(p, 14, P.A["dw0"])
        p.seti(4, 14)
        p.ldi(14, 0, 4)
        start(p, 2, None, 4, 15)
        until_wrap(p, "w2")
        p.iconst(13, X + 4 * (BLOCK - 1))
        p.seti(3, 13)

        def first():
            start(p, 0, "pd4")
            until_wrap(p, "w0")

        def later():
            p.iconst(13, X + 4 * (BLOCK - 1))
            p.seti(0, 13)
            p.iconst(13, 1 << 20)                   # (L1: never crosses)
            p.st(_w(W["w0"]), 13)
        p.ld(0, _w("t4"))
        p.ifz(0, "EQ", first, later)
        p.ld(13, _w("t4"))                          # g: gdx1 for k 0, 1, gdx2 for 2, 3
        p.lsh(13, 13, -3)
        p.lsh(13, 13, 2)
        p.iconst(14, P.C["gdx1"])
        p.iop(14, 14, "+", 13)
        p.seti(4, 14)
        p.ldi(5, 0, 4)
        run_n(p, "fd_diff", [(0, "w0", RING_INC), (1, "w1", "dmask"), (2, "w2", "dmask")],
              lambda: _diff_body(p), lambda: _diff_pair(p))
    _k_loop(p, 4, one)


# a line's sum into s and its output into L / R, in sample()'s order: line 0 sets s and L (kind l0), 1 adds to s and
# sets R (l1), 2..7 add to s and add to L / R (lp: 4, 5) or take from it (lm: 2, 3, 6, 7); then s x 0.25


def _line_body(p: Prog, kind: str) -> None:
    """one sample of a line: u0 (I0, down), u1 (F6: the word u0 read a sample before), the fraction's allpass (F7 ap,
    F9 eta), the damping (F8 lp, F10 c), the gain (F15 gx); f to I1, s at I2, L / R at I3 (both up). The order of
    the operations on each value is sample()'s; the moves are placed where they ride on a compute"""
    acc = kind not in ("l0", "l1")
    p.ldm(0, 0)                                     # u0
    p.fop(1, 0, "-", 7)
    if kind != "l0":
        p.ldi(3, 0, 2)                              # s (on the subtract)
    p.fop(1, 9, "*", 1)
    if acc:
        p.ldi(4, 0, 3)                              # L / R (on the product)
    p.fop(7, 6, "+", 1)                             # o (the allpass's state too)
    if acc:
        p.fop(4, 4, "+" if kind == "lp" else "-", 7)
        p.stpost(3, 4)                              # (on the next compute)
    else:
        p.stpost(3, 7)
    p.fop(1, 8, "-", 7)
    p.fop(1, 10, "*", 1)
    p.fop(8, 7, "+", 1)                             # lp
    p.fop(2, 8, "*", 15)                            # f
    if kind == "l0":
        p.stpost(1, 2)
        p.fpass(6, 0)                               # u1 of the next sample
        p.stpost(2, 2)                              # s = f
        return
    p.fop(3, 3, "+", 2)
    p.stpost(1, 2)                                  # f (on the add)
    p.fpass(6, 0)                                   # u1 of the next sample
    p.stpost(2, 3)                                  # (on the pass)


def _line_pair(p: Prog, kind: str) -> None:
    """_line_body for two samples, A then B: B's u1 is A's u0 (F0), B's u0 goes to F6 (the next pass's u1), so no
    copy; B's moves ride on A's computes"""
    acc, hs = kind not in ("l0", "l1"), kind != "l0"
    sg = "+" if kind == "lp" else "-"

    def tail():                                     # lp, f, s (and s4), F7 the line's o
        p.fop(1, 8, "-", 7)
        p.fop(1, 10, "*", 1)
        p.fop(8, 7, "+", 1)                         # lp
        p.fop(2, 8, "*", 15)                        # f
        if hs:
            p.fop(3, 3, "+", 2)
            p.stpost(1, 2)
        else:
            p.stpost(1, 2)
    p.ldm(0, 0)                                     # u0A
    p.fop(1, 0, "-", 7)
    if hs:
        p.ldi(3, 0, 2)                              # sA
    p.fop(1, 9, "*", 1)
    if acc:
        p.ldi(4, 0, 3)                              # L / R
    p.fop(7, 6, "+", 1)                             # oA
    if acc:
        p.fop(4, 4, sg, 7)
        p.ldm(6, 0)                                 # u0B
        p.stpost(3, 4)
    else:
        p.ldm(6, 0)                                 # u0B
        p.stpost(3, 7)
    tail()
    p.fop(1, 6, "-", 7)                             # B
    p.stpost(2, 3 if hs else 2)                     # sA
    p.fop(1, 9, "*", 1)
    if hs:
        p.ldi(3, 0, 2)                              # sB
    p.fop(7, 0, "+", 1)                             # oB
    if acc:
        p.ldi(4, 0, 3)
        p.fop(4, 4, sg, 7)
        p.stpost(3, 4)
    else:
        p.stpost(3, 7)
    tail()
    p.stpost(2, 3 if hs else 2)                     # sB


def _lines(p: Prog) -> None:
    """for k = 0..7: line k over the block (kinds: 0 sets s and L, 1 adds to s and sets R, the rest add to s and add
    to (4, 5) or take from (2, 3, 6, 7) L / R); then s x 0.25"""
    _, S, F = bufs()
    L, _ = lr_bufs()

    def off(name):
        return (P.C[name + "0"] - P.C["ro0"]) // 4

    def one():
        ring_regs(p)
        _k_at(p, 14, F, 5)                          # F + 128 k
        p.seti(1, 14)
        p.iconst(14, S)
        p.seti(2, 14)
        p.ld(13, _w("t4"))                          # L (even k) or R
        p.iconst(14, 4)
        p.iop(13, 13, "AND", 14)
        p.lsh(13, 13, 5)
        p.iconst(14, L)
        p.iop(14, 14, "+", 13)
        p.seti(3, 14)
        _k_at(p, 14, P.C["ro0"])
        p.seti(4, 14)
        p.ldi(2, 0, 4)                              # ro
        p.ipass(14, 2)
        start(p, 4, None, extra=4)
        p.ldi(6, 0, 4)                              # u1 of sample 0
        p.ipass(14, 2)
        start(p, 0, None)
        p.ipass(5, 13)                              # (the u0 stream's place, for run1)
        _k_at(p, 14, P.C["ro0"])                    # the line's words (R8..R10 no longer the ring's)
        p.seti(4, 14)
        p.ldi(7, off("ap"), 4)
        p.ldi(8, off("lp"), 4)
        p.ldi(9, off("eta"), 4)
        p.ldi(10, off("c"), 4)
        p.ldi(15, off("gx"), 4)
        p.ipass(13, 5)
        p.ld(2, _w("t4"))                           # the kind: R2 = k4, R3 = k4 & 8 (k 2, 3, 6, 7)
        p.iconst(3, 8)
        p.iop(3, 2, "AND", 3)

        def arm(kind):
            return lambda: run1(p, "fd_" + kind, 0, RING_INC, lambda: _line_body(p, kind),
                                lambda: _line_pair(p, kind))
        p.iconst(1, 4)

        def not0():
            p.if_(2, "EQ", 1, arm("l1"), lambda: p.ifz(3, "NE", arm("lm"), arm("lp")), kind="i")
        p.ifz(2, "EQ", arm("l0"), not0)
        _k_at(p, 14, P.C["ap0"])                    # the line's states back
        p.seti(4, 14)
        p.sti(0, 4, 7)
        p.sti(off("lp") - off("ap"), 4, 8)
    _k_loop(p, 8, one)
    p.iconst(14, S)                                 # s4 = s x 0.25
    p.seti(0, 14)
    p.seti(1, 14)
    p.fconst(5, 0.25)

    def quarter():
        p.ldpost(0, 0)
        p.ldpost(1, 0)
        p.fop(0, 0, "*", 5)
        p.fop(1, 1, "*", 5)
        p.stpost(1, 0)
        p.stpost(1, 1)
    p.loop_r(11, BLOCK // 2, quarter)


def _write2_body(p: Prog) -> None:
    """lines 2j and 2j + 1's writes, one sample: s4 (I1, up), f of line 2j + 1 (I0, up; line 2j's 32 words below),
    the diffusers' out (I2, down); the even line's write to I3 (+ xw), the odd's to I4 (- xw), both down"""
    p.ldpost(1, 1)                                  # s4
    p.ldi(0, -BLOCK, 0)                             # f (even)
    p.fop(3, 1, "-", 0)
    p.ldm(2, 2)                                     # xw
    p.fop(3, 3, "+", 2)
    p.ldpost(4, 0)                                  # f (odd)
    p.fop(5, 1, "-", 4)
    p.stm(3, 3)
    p.fop(5, 5, "-", 2)
    p.stm(4, 5)


def _write2_pair(p: Prog) -> None:
    """_write2_body for two samples, A then B"""
    p.ldpost(1, 1)                                  # s4 A
    p.ldi(0, -BLOCK, 0)                             # f even A
    p.fop(3, 1, "-", 0)
    p.ldm(2, 2)                                     # xw A
    p.fop(3, 3, "+", 2)
    p.ldpost(4, 0)                                  # f odd A
    p.fop(5, 1, "-", 4)
    p.ldpost(1, 1)                                  # s4 B
    p.fop(5, 5, "-", 2)
    p.ldi(0, -BLOCK, 0)                             # f even B
    p.fop(6, 1, "-", 0)
    p.ldm(2, 2)                                     # xw B
    p.fop(6, 6, "+", 2)
    p.stm(3, 3)                                     # A's even write
    p.stm(4, 5)                                     # A's odd write
    p.ldpost(4, 0)                                  # f odd B
    p.fop(7, 1, "-", 4)
    p.stm(3, 6)
    p.fop(7, 7, "-", 2)
    p.stm(4, 7)


def _writes(p: Prog) -> None:
    """for j = 0..3: lines 2j and 2j + 1's writes, s4 - f + the diffusers' out (the even line) and - it (the odd); the
    two lines' rings far apart (a line's region), so their words keep their order whichever line writes first"""
    X, S, F = bufs()

    def one():
        ring_regs(p)
        _k_at(p, 14, F + 4 * BLOCK, 6)              # line 2j + 1's f (F + 128 (2j + 1))
        p.seti(0, 14)
        p.iconst(14, S)
        p.seti(1, 14)
        p.iconst(14, X + 4 * (BLOCK - 1))
        p.seti(2, 14)
        _k_at(p, 14, P.A["rw0"], 1)                 # rw of line 2j, 2j + 1
        p.seti(4, 14)
        p.ldi(2, 1, 4)
        p.ldi(14, 0, 4)
        start(p, 3, None)
        until_wrap(p, "w1")
        p.ipass(14, 2)
        start(p, 4, None)
        until_wrap(p, "w2")
        run_n(p, "fd_w2", [(3, "w1", RING_INC), (4, "w2", RING_INC)], lambda: _write2_body(p),
              lambda: _write2_pair(p))
    _k_loop(p, 4, one)


def _output(p: Prog) -> None:
    """L, R x GOUT, then the width (xwr not 0) or as they are, into out L / R"""
    for i, a in enumerate(lr_bufs()):
        p.iconst(14, a)
        p.seti(i, 14)
    for i, n in ((2, "outl"), (3, "outr")):
        p.ld(14, _w(IO[n]))
        p.seti(i, 14)
    p.fconst(8, D.GOUT)
    p.ld(9, P.C["xwl"])
    p.ld(10, P.C["xwr"])
    p.fconst(7, 0.0)

    def gain():
        p.ldpost(5, 0)
        p.ldpost(6, 1)                              # (rides on the product)
        p.fop(5, 5, "*", 8)
        p.fop(6, 6, "*", 8)

    def width():
        def body():
            gain()
            p.fop(1, 5, "*", 9)
            p.fop(2, 6, "*", 10)
            p.fop(1, 1, "+", 2)
            p.fop(2, 6, "*", 9)
            p.fop(0, 5, "*", 10)
            p.fop(2, 2, "+", 0)
            p.stpost(2, 1)
            p.stpost(3, 2)
        p.loop_r(11, BLOCK, body)

    def hard():
        def body():
            p.ldpost(5, 0)
            p.ldpost(6, 1)
            p.fop(5, 5, "*", 8)                     # (the load of R rides on it)
            p.fop(6, 6, "*", 8)
            p.stpost(2, 5)                          # (on the product)
            p.stpost(3, 6)
        p.loop_r(11, BLOCK, body)
    p.if_(10, "NE", 7, width, hard)


def tank(p: Prog) -> None:
    """the block's samples (program.sample's work), stage by stage; then p moves 32 words on"""
    io_words(p)
    _input(p)
    _diffusers(p)
    _lines(p)
    _writes(p)
    _output(p)
    p.ld(8, P.C["p4"])
    p.iconst(14, 4 * BLOCK)
    p.iop(8, 8, "-", 14)
    p.st(P.C["p4"], 8)
