"""The stereo inserts after the pan (CHOR, WIDE): their DSP code, in the DSL (dnfw.perc.dsl Prog),
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

STATE = 0x200B1000               # L2, after the code (dnfw.waverider.dsp.POST_STATE_L2)
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
          + [f"sv{k}" for k in range(16)] + [f"svi{i}" for i in SAVE_I] + ["sva"])
C = {n: SCRATCH + 4 * k for k, n in enumerate(_NAMES)}
SCRATCH_BYTES = 4 * len(_NAMES)
SENDS_SW = 0x1C1738              # the FX sends, the call's stock target
MASK = D.POST_RING - 1


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
    p.ld(4, C["lp"])
    p.seti(0, 4)
    p.ld(4, C["rp"])
    p.seti(1, 4)

    def one():
        p.ldi(5, 0, 0)                           # l
        p.ldi(6, 0, 1)                           # r
        p.fop(7, 5, "+", 6)
        p.fconst(1, 0.5)
        p.fop(7, 7, "*", 1)                      # m
        p.fop(8, 5, "-", 6)
        p.fop(8, 8, "*", 1)                      # sd
        p.ld(9, C["s0"])
        p.iconst(12, 1)
        p.iop(9, 9, "+", 12)
        p.iconst(12, MASK)
        p.iop(9, 9, "AND", 12)
        p.st(C["s0"], 9)                         # wp
        p.ipass(10, 9)
        ring_at(p, 10, 12)
        p.sti(0, 4, 7)
        p.ld(10, C["dl"])
        p.iop(10, 9, "-", 10)
        ring_at(p, 10, 12)
        p.ldi(0, 0, 4)                           # d
        p.ld(1, C["s1"])
        p.fop(2, 0, "-", 1)
        p.ld(3, C["ab"])
        p.fop(2, 2, "*", 3)
        p.fop(1, 1, "+", 2)
        p.st(C["s1"], 1)                         # lb
        p.fop(2, 0, "-", 1)                      # h
        p.ld(1, C["s2"])
        p.fop(2, 2, "-", 1)
        p.ld(3, C["ct"])
        p.fop(2, 2, "*", 3)
        p.fop(1, 1, "+", 2)
        p.st(C["s2"], 1)                         # lt
        p.ld(3, C["wg"])
        p.fop(2, 8, "*", 3)
        p.ld(3, C["p1"])
        p.fop(4, 1, "*", 3)
        p.fop(2, 2, "+", 4)                      # s'
        p.fop(3, 7, "+", 2)                      # lo
        p.fop(4, 7, "-", 2)                      # ro
        p.ld(0, C["p0"])
        p.fop(3, 3, "-", 5)
        p.fop(3, 3, "*", 0)
        p.fop(3, 5, "+", 3)
        p.stpost(0, 3)
        p.fop(4, 4, "-", 6)
        p.fop(4, 4, "*", 0)
        p.fop(4, 6, "+", 4)
        p.stpost(1, 4)
    p.loop_r(11, D.BLOCK, one)


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

    def one():
        p.ld(0, C["d"])
        p.ld(1, C["step"])
        p.fop(0, 0, "+", 1)
        p.st(C["d"], 0)
        p.trunc(5, 0)                            # i
        p.iconst(1, 0)
        p.float_(1, 5, 1)
        p.fop(6, 0, "-", 1)                      # fr
        p.ld(7, C["pos"])
        p.iop(8, 7, "-", 5)
        ring_at(p, 8, 12)
        p.ldi(2, 0, 4)                           # y0
        p.iop(8, 7, "-", 5)
        p.iconst(12, 1)
        p.iop(8, 8, "-", 12)
        ring_at(p, 8, 12)
        p.ldi(3, 0, 4)                           # y1
        p.fop(3, 3, "-", 2)
        p.fop(3, 3, "*", 6)
        p.fop(2, 2, "+", 3)                      # y
        p.ldi(3, 0, 0)
        p.ld(1, C["gl"])
        p.fop(4, 2, "*", 1)
        p.fop(3, 3, "+", 4)
        p.stpost(0, 3)
        p.ldi(3, 0, 1)
        p.ld(1, C["gr"])
        p.fop(4, 2, "*", 1)
        p.fop(3, 3, "+", 4)
        p.stpost(1, 3)
        p.iconst(12, 1)
        p.iop(7, 12, "+", 7)
        p.st(C["pos"], 7)
    p.loop_r(11, D.BLOCK, one)
    p.ld(0, C["v"])
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    p.st(C["v"], 0)


def chor(p: Prog) -> None:
    """CHOR (postref.PostRef.chor); p0 MIX, p1 DPTH, p2 RATE, p3 DLY, p4 VOIC, p5 WDTH, p6 FDBK;
    s0 the phase, s1 wp"""
    chor_params(p)
    p.iconst(4, WL)
    p.seti(0, 4)
    p.fconst(0, 0.0)

    def zero():
        p.stpost(0, 0)
        p.stpost(0, 0)
    p.loop_r(11, D.BLOCK, zero)
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

    def one():
        p.ldi(5, 0, 0)                           # l
        p.ldi(6, 0, 1)                           # r
        p.fop(7, 5, "+", 6)
        p.fconst(1, 0.5)
        p.fop(7, 7, "*", 1)                      # x
        p.ldpost(2, 2)                           # wet l
        p.ldpost(3, 3)                           # wet r
        p.fop(4, 2, "+", 3)
        p.fop(4, 4, "*", 1)
        p.ld(0, C["fb"])
        p.fop(4, 4, "*", 0)
        p.fop(7, 7, "+", 4)
        p.ld(9, C["s1"])
        p.iconst(12, 1)
        p.iop(9, 9, "+", 12)
        p.iconst(12, MASK)
        p.iop(9, 9, "AND", 12)
        p.st(C["s1"], 9)
        ring_at(p, 9, 12)
        p.sti(0, 4, 7)
        p.ld(0, C["p0"])
        p.fop(4, 2, "-", 5)
        p.fop(4, 4, "*", 0)
        p.fop(4, 5, "+", 4)
        p.stpost(0, 4)
        p.fop(4, 3, "-", 6)
        p.fop(4, 4, "*", 0)
        p.fop(4, 6, "+", 4)
        p.stpost(1, 4)
    p.loop_r(11, D.BLOCK, one)


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
    p.lsh(1, 0, 12)                              # 4 KB a voice slot and insert slot
    p.iconst(12, D.POST_RING_DDR)
    p.iop(1, 12, "+", 1)
    p.st(C["rb"], 1)
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
    p.ld(5, C["sel"])
    p.iconst(6, D.WIDE)
    p.if_(5, "EQ", 6, lambda: G.ins_admit(p, D.COST[D.WIDE], lambda: wide(p)),
          lambda: G.ins_admit(p, D.COST[D.CHOR], lambda: chor(p)), kind="i")
    p.ld(2, C["sa"])
    p.seti(4, 2)
    for k in range(6):
        p.ld(8, C[f"s{k}"])
        p.sti(k, 4, 8)


def body(p: Prog) -> None:
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
