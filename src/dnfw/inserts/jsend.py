"""The chorus SEND's TYPE JUNO (2026-11-12, the User): Optimist's Juno-106 chorus in the stock chorus's slot on the
FX bus, in the DSL (dnfw.perc.dsl Prog), emitted as SHARC assembly (jsend.asm) and run in Python as its exact model,
held bit for bit to dnfw.inserts.postref.JsendRef.

**The slot.** The FX bus calls the stock chorus with `CALL 0xb84d5c (DB)` at sw 0x1c1be1 and its two pushes (R4 = its
DDR state 0x80459388, R8 = its parameter struct 0x257950, R12 = the bus's I/O descriptor 0x257e6c: +4 -> {in L, in R},
+0xc -> {out L, out R}, 32 floats each; measured in the runner), as it calls the delay at 0x1c1c58 (dnfw.xdly). The
build changes only that call's target, to wr_jsend (dnfw.waverider.dsp.JSEND_SW); wr_jsend saves every register it
uses, then

- TYPE (the send pages' words, design.JS_TYPE: 0 until the ColdFire sends one) not JUNO: forgets its own state (the
  next JUNO starts from zeros), restores every register and JUMPs to 0xb84d5c, the stock chorus entered as the bus
  called it (it returns to the bus itself);
- TYPE JUNO: one block of postref's JUNO (dnfw.inserts.post.juno, the very code the inserts run) on the send: in L / R
  copied to out L / R, then the chorus in place there; MIX the chorus page's DPTH, MODE its SPD (the frame image's
  kit slots 25 and 26, as the page's knobs hold them: 8.8, knob x 256), and returns with the stock C epilogue.

Its scratch is the post pass's (dnfw.inserts.post.C, WL, WR in L1): the FX bus runs after that pass has ended
(the pass JUMPs on to the sends, 0x1c1738, which call the bus). Its own words (the six state words, the last TYPE
it ran) and its ring are in DDR (design.JS_STATE, JS_RING). The stock chorus's own state is never touched, so back
on STOCK it carries on from where it was.
"""

from __future__ import annotations

from ..perc.dsl import Mem, Prog
from . import design as D
from . import post as P

C = P.C
CHORUS_SW = 0xB84D5C                 # the stock chorus, as the bus calls it
WORDS = 8                            # the state words: s0..s5, the last TYPE run (word 6)


def _knob(p: Prog, word: int, high: bool, dst: str) -> None:
    """C[dst] = the frame image's half word (8.8, knob x 256) x design.JS_KNOB_K: the knob / 127"""
    p.ld(0, word)
    if high:
        p.lsh(0, 0, -16)
    p.iconst(12, 0xFFFF)
    p.iop(0, 0, "AND", 12)
    p.float0(0, 0)
    p.fconst(1, D.JS_KNOB_K)
    p.fop(0, 0, "*", 1)
    p.st(C[dst], 0)


def _state_at(p: Prog) -> None:
    p.iconst(2, D.JS_STATE)
    p.seti(4, 2)


def fresh(p: Prog) -> None:
    """a start: the state words and the ring zeros, the last TYPE JUNO"""
    _state_at(p)
    p.iconst(9, 0)
    for k in range(6):
        p.sti(k, 4, 9)
    p.iconst(9, D.JS_JUNO)
    p.sti(6, 4, 9)
    p.iconst(1, D.JS_RING)
    p.seti(0, 1)
    p.fconst(0, 0.0)

    def sixteen():
        for _ in range(16):
            p.stpost(0, 0)
    p.loop_r(11, D.POST_RING // 16, sixteen)


def block(p: Prog) -> None:
    """one block of JUNO on the send (in -> out, then post.juno in place on out)"""
    _state_at(p)
    p.ldi(0, 6, 4)
    p.iconst(1, D.JS_JUNO)
    p.if_(0, "NE", 1, lambda: fresh(p), kind="i")
    _state_at(p)
    for k in range(6):
        p.ldi(8, k, 4)
        p.st(C[f"s{k}"], 8)
    p.ld(13, C["sv12"])                          # the bus's I/O descriptor
    p.seti(4, 13)
    p.ldi(14, 1, 4)
    p.seti(4, 14)
    p.ldi(15, 0, 4)
    p.seti(0, 15)
    p.ldi(15, 1, 4)
    p.seti(1, 15)                                # I0, I1: in L, in R
    p.ld(13, C["sv12"])
    p.seti(4, 13)
    p.ldi(14, 3, 4)
    p.seti(4, 14)
    p.ldi(15, 0, 4)
    p.st(C["lp"], 15)
    p.seti(2, 15)
    p.ldi(15, 1, 4)
    p.st(C["rp"], 15)
    p.seti(3, 15)                                # I2, I3: out L, out R

    def copy():
        p.ldpost(8, 0)
        p.stpost(2, 8)
        p.ldpost(9, 1)
        p.stpost(3, 9)
    p.loop_r(11, D.BLOCK, copy)
    p.iconst(0, D.JS_RING)
    p.st(C["rb"], 0)
    _knob(p, D.JS_DPTH_WORD, True, "p0")         # MIX: DPTH
    _knob(p, D.JS_SPD_WORD, False, "p1")         # MODE: SPD
    P.juno(p)
    _state_at(p)
    for k in range(6):
        p.ld(8, C[f"s{k}"])
        p.sti(k, 4, 8)


def ret(p: Prog) -> None:
    P.restore(p)
    if p.run:
        p.went = "ours"
        return
    p.e("I12 = DM(M7, I6);")
    p.e("JUMP (M14, I12) (DB);")
    p.e("RFRAME;")
    p.e("NOP;")


def entry(p: Prog) -> None:
    """after save(): TYPE; the stock chorus (and our state forgotten), or one block of JUNO"""
    p.ld(0, D.JS_TYPE)
    p.iconst(1, D.JS_JUNO)

    def go_stock():
        _state_at(p)
        p.iconst(9, 0)
        p.sti(6, 4, 9)                           # the next JUNO starts fresh
        P.restore(p)
        if p.run:
            p.went = "stock"
            return
        p.jump_abs("", CHORUS_SW, "the stock chorus, entered as the bus called it")

    p.if_(0, "NE", 1, go_stock, kind="i")
    if p.run and p.went == "stock":             # (the model: the stock chorus took the call)
        return
    block(p)
    ret(p)


def program(prefix: str = "js") -> str:
    p = Prog("emit", prefix=prefix)
    p.raw("// jsend.asm -- JUNO in the stock chorus's slot on the FX bus (docs/inserts.md \"The chorus send\"). GENERATED")
    p.raw("// by scripts/gen_inserts_asm.py from dnfw.inserts.jsend; do not edit by hand.")
    p.raw("")
    p.raw(".SECTION/PM seg_pmco;")
    p.raw("")
    p.raw(".GLOBAL wr_jsend.;")
    p.raw("wr_jsend.:")
    P.save(p)
    entry(p)
    p.emit_subs()
    p.raw(".wr_jsend..end:")
    p.raw("      .type wr_jsend.,STT_FUNC;")
    return p.text()


def model(mem: Mem, regs: dict[int, int]) -> tuple[str, Prog]:
    """the model: one call with R0..R15 = REGS on MEM -> ('stock' | 'ours', the Prog)"""
    p = Prog("run", mem=mem)
    for k, v in regs.items():
        p.r[k] = v & 0xFFFFFFFF
    p.went = ""
    P.save(p)
    entry(p)
    return p.went, p
