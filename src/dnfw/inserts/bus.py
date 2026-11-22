"""The bus inserts (FDN8, XDLY) per track: their DSP pass, in the DSL (dnfw.perc.dsl Prog), emitted as
SHARC assembly (insbus.asm) and run in Python as its exact model, held bit for bit to
dnfw.inserts.busref (2026-11-10, the User: FDN8 and XDLY as inserts, two slots a track).

**Where it runs.** The engine (sw 0x1c2712) renders the voices (0x1c8ef1), calls the FX sends (0x1c1738:
wr_inpost first), then the routing 0x1c1f1e: it sums each voice slot's stereo block into its track's block
(design.BUS_BLOCKS + 0x100 t, L then R at + 0x80, the voices x 14.125; its loop ends at sw 0x1c1fec), then
sums the tracks' blocks into the main bus (0x25bb68, from sw 0x1c2038), adds the send FX's returns and runs
the master chain; the output stage (0x1c244d, called at sw 0x1c307b) then sends each track's block to
Overbridge. The build replaces the routing's first instruction after its per-track loop (sw 0x1c1fef,
`R2 = DM(0x257980)`, dnfw.waverider.dsp.ROUTE_SITE_SW) with `JUMP wr_inbus`: it saves every register it
uses, runs the bus inserts of each track in place on its block (slot 1 before slot 2), restores everything,
does the instruction it replaced and JUMPs back to sw 0x1c1ff2. So a bus insert is on the main mix (and
through the master chain, as the track is) and on Overbridge's track outputs; the FX sends took their taps
before (docs/inserts.md "On the track's bus"). Unlike the voice inserts it runs once a track, whatever the
voices: a tail outlives its notes.

**2026-11-11, the User: "xdelay and fdn8 still dont work as insert".** Until then the pass ran at the output
stage's call (sw 0x1c307b), after the routing had summed the main bus from the dry blocks: the unit's
Overbridge stream of the track carried the insert (remoteui's SPI records), the main mix did not. The
runner's mainmix step (scripts/sharc_mainmix_step.py) holds the main bus to the blocks after this pass.

**The engines are the send FX's own code** (dnfw.fdn8.program, dnfw.xdly.program): an instance's words
(DYN_WORDS, and FDN8's active variant table) live here, are swapped in for the send FX's (saved first,
put back at the end), MODE set to 1, and wr_fdn8 / wr_xdly entered as a leaf call. Each instance has its
own DDR (design.FDN8_RING_DDR, XDLY_LINES_DDR); the ColdFire gives a slot an instance (field 0's high
bits) and keeps it while the slot keeps the type; an instance whose slot or type changed (OWNER) starts
fresh. Input: the track's block x G_IN; MIX blends the wet x G_OUT in: x' = x + (wet - x) MIX.

**A moved slot 2** (2026-11-11, design.MOVERS: slot 1 CHOR, WIDE, FDN8 or XDLY, slot 2 a voice insert): the
pre pass left it out; here, right after slot 1, the pre pass's own insert code (program.one, called at
design.INS_ONE_SW) runs it on the track's block x G_IN, L and R each with its own state (MV_STATE), then
x G_OUT back (moved). The bus pass's flag is set for such a pair too (program.set_flags).
"""

from __future__ import annotations

from ..fdn8 import program as FP
from ..perc import guard as G
from ..perc.dsl import Mem, Prog
from ..xdly import program as XP
from . import design as D
from . import program as PR

# the FDN8 engine finds an instance's L2 diffuser ring from its DDR ring (fdn8.program.diff_ring, 2026-11-21)
assert (FP.BUS0_RING, FP.BUS_RING_STRIDE, FP.BUS_INSTANCES) == (D.FDN8_RING_DDR, D.FDN8_RING_STRIDE, D.FDN8_INSTANCES)

STATE = D.BUS_STATE                               # L2, after the code (dnfw.waverider.dsp.INSBUS_STATE_L2)
FD_WORDS = FP.DYN_WORDS                           # an FDN8 instance: its words (2026-11-22: HALF's table VT3 is in ACT
                                                  # while instances run, put there once a pass: no table an instance)
XD_WORDS = XP.DYN_WORDS
FD_STRIDE, XD_STRIDE = 1024, 256                  # bytes a store (powers of two: the instance's by a shift)
assert 4 * FD_WORDS <= FD_STRIDE and 4 * XD_WORDS <= XD_STRIDE
# the head, loaded at power-on (zeros but the descriptor): OWNER 0 = no slot yet, so each instance's first
# run starts it fresh (its words zeroed then set); the stores themselves are not loaded
OWNER = STATE                                     # per instance (FDN8's, then XDLY's): 1 + record | type << 8
# 2026-11-14 (delay leaks; the User: "i heard some delay, long after"): OWNER changes only when the instance runs,
# so a slot whose FDN8 / XDLY went away (another type, OFF) and came back with the same instance (the ColdFire
# gives the lowest free one: the same) resumed its frozen lines and replayed the old tail. Now each pass counts
# itself (PASSN, down) and each instance keeps the pass that last claimed it (LAST): a claim after a pass without one
# clears OWNER, so the instance starts fresh, as the design says ("an instance whose slot or type changed")
LAST = OWNER + 4 * (D.FDN8_INSTANCES + D.XDLY_INSTANCES)
PASSN = LAST + 4 * (D.FDN8_INSTANCES + D.XDLY_INSTANCES)
HEAD_END = PASSN + 4
# 2026-11-12 (opt-inserts): a unit's scratch in L1, not L2 (the engine reads and writes it every sample: ~340 L2
# accesses a unit), in the Monomachine render scratch's IN after the post pass's taps line (inserts.post.LINE): the
# arbiter's transient 0x2e54c0..0x2e5700. The voices rewrite it every block, so every unit writes its descriptor
# (unit_io) before the engine reads it, as the power-on head (state_bytes) held it until then.
UNIT_L1 = 0x2E54C0
DESC = UNIT_L1                                    # the I/O descriptor the engines read:
INP = DESC + 16                                   # +4 -> {in L, in R}, +0xc -> {out L, out R}
OUTP = INP + 8
XL = OUTP + 8                                     # the input (the track x G_IN), the wet
XR = XL + 4 * D.BLOCK
WL = XR + 4 * D.BLOCK
WR = WL + 4 * D.BLOCK
PARF = WR + 4 * D.BLOCK                           # the instance's 6 parameters, floats (the struct the FX read)
UNIT_L1_END = PARF + 4 * 6
assert UNIT_L1_END <= 0x2E5700
# 2026-11-12 (opt-inserts, lever 4): the pass's own words (C) and the send FX's words set aside while instances
# run (FD_SEND, XD_SEND) in L1, not L2: the arbiter's transient 0x2e5700..0x2e5b00 (the render's XB and YB, dead
# after the voices). Each is written in the pass before it is read, and nothing is kept across blocks.
WORDS_L1, WORDS_L1_LIMIT = 0x2E5700, 0x2E5B00
SAVE_I = (0, 1, 2, 3, 4, 12)
_NAMES = (["i", "t", "j", "rec", "sel", "inst", "fds", "xds", "own", "lp", "rp", "mix", "cnt", "bnd", "aa", "ist", "unit"]
          + [f"sv{k}" for k in range(16)] + [f"svi{i}" for i in SAVE_I] + ["sva"])
C = {n: WORDS_L1 + 4 * k for k, n in enumerate(_NAMES)}
FD_SEND = WORDS_L1 + 4 * len(_NAMES)              # the send FX's words, while instances run
XD_SEND = FD_SEND + 4 * (FP.DYN_WORDS + FP.NV)    # (the send FDN8's words and its active table)
WORDS_L1_END = XD_SEND + 4 * XD_WORDS
assert WORDS_L1_END <= WORDS_L1_LIMIT
XD_L2 = (HEAD_END + XD_STRIDE - 1) // XD_STRIDE * XD_STRIDE   # (where the XDLY stores were, in L2: kept, so nothing
END = XD_L2 + D.XDLY_INSTANCES * XD_STRIDE                     # after them moves)
# 2026-11-13 (lever 5; the arbiter: L1 F2 0x2e1750..0x2e1980): the XDLY instances' stores in L1 (every block copies
# an instance's 35 words in and out: 2 L2 accesses a word), packed at their words' size; zeros at power-on (dsp)
XD_STORE, XD_L1_STRIDE = 0x2E1750, 4 * XD_WORDS
assert XD_STORE + D.XDLY_INSTANCES * XD_L1_STRIDE <= 0x2E1980
# perf (2026-11-11): the FDN8 instances' stores in L1 (every block copies an instance's words in and out: 2
# L2 accesses a word), in the 5 KB free after the post pass's state (post.py ends at 0x2e4044; MNM_RENDER_DM
# starts at 0x2e5400), 156 words an instance, no gaps
FD_L1 = 0x2E4050
FD_L1_BYTES = 4 * FD_WORDS
FD_STORE = FD_L1
assert FD_L1 >= 0x2E4044 and FD_L1 + D.FDN8_INSTANCES * FD_L1_BYTES <= FP.BUF_L1 <= 0x2E5400   # (FDN8's block
assert FD_L1 == 0x2E4050                                                       # buffers after the stores, 2026-11-22)
assert END <= D.BUS_STATE_END, f"the bus pass's state runs past its room: {END:#x}"
# 2026-11-11 (design.MOVERS): a moved slot 2's state, 8 words for each of the track's L (2 t) and R (2 t + 1),
# as the pre pass's (program.one: the last type and track in its last two words, zeros at power-on)
MV_STATE = END
MV_END = MV_STATE + 4 * D.STATE_WORDS * D.MV_INSTANCES
assert MV_END <= D.BUS_STATE_END, f"the moved inserts' state runs past the bus pass's room: {MV_END:#x}"
assert MV_END <= D.AUTO_L2, "AUTO's words (design.AUTO_L2) after the moved inserts' state"
assert MV_STATE >= 0x20000000 > PR.STATE and D.MV_INSTANCES == D.RECORDS   # program.auto_addr's test and its mod 32
# (MV_INSTANCES == RECORDS: PR.forget_all walks 32)
# the guard's bound for a moved insert: the dearest BUILT type, twice (L and R; the unit's cost unmeasured)
MV_COST = 2 * max(D.COST[t] for t in D.BUILT)
SITE_SW = 0x1C1FEF                                # the routing, after its per-track loop: JUMP wr_inbus here
DISPLACED = "R2 = DM(0x257980);"                  # .. in place of this (stock's, 48 bits), done on the way back
RESUME_SW = 0x1C1FF2                              # the routing's next instruction: the main bus is summed after
G_IN = 1 / 14.125                                 # the routing's gain on a voice (docs/link-research.md §7)
G_OUT = 14.125
assert G_IN == __import__("dnfw.fdn8.lite", fromlist=["G_IN"]).G_IN


def state_bytes() -> bytes:
    """the head's words at power-on: OWNER, LAST and PASSN zeros"""
    import struct
    return struct.pack(f"<{(HEAD_END - STATE) // 4}I", *[0] * ((HEAD_END - STATE) // 4))


UNIT_IO = ((DESC, 0), (DESC + 4, INP), (DESC + 8, 0), (DESC + 12, OUTP), (INP, XL), (INP + 4, XR), (OUTP, WL),
           (OUTP + 4, WR))


def unit_io(p: Prog) -> None:
    """the I/O descriptor and its two pairs, in the unit's L1 scratch. Clobbers R0"""
    for at, v in UNIT_IO:
        p.iconst(0, v)
        p.st(at, 0)


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


def copy(p: Prog, dst: int | str, src: int | str, n: int) -> None:
    """N words from SRC to DST (an address, or a scratch word's name holding one). Clobbers R0, R11, R12, I0, I1,
    I12"""
    for i, a in ((0, src), (1, dst)):
        if isinstance(a, str):
            p.ld(0, C[a])
        else:
            p.iconst(0, a)
        p.seti(i, 0)

    def one():
        p.ldpost(0, 0)
        p.stpost(1, 0)

    def eight():                                 # perf (2026-11-11): 8 words a pass (the loop's 3 instructions shared)
        for _ in range(8):
            one()
    if n >= 8:                                   # (2026-11-14, code room: the 8-word loop once, a leaf subroutine;
        p.iconst(11, n // 8)                     # it was inline at each of the 13 copies)
        p.call("copy8", lambda: p.loop_r(11, None, eight))
    for _ in range(n % 8):
        one()


def store_area(p: Prog, name: str, base: int, stride: int) -> None:
    """C[name] = BASE + C['inst'] x STRIDE. Clobbers R0, R12"""
    p.ld(0, C["inst"])
    if stride & (stride - 1):
        p.iconst(12, stride)
        p.mul_ssi(0, 0, 12)
    else:
        p.lsh(0, 0, stride.bit_length() - 1)
    p.iconst(12, base)
    p.iop(0, 12, "+", 0)
    p.st(C[name], 0)


def zero(p: Prog, at: int, n: int) -> None:
    """N words from AT zeroed. Clobbers R0, R11, R12, I0"""
    p.iconst(0, at)
    p.seti(0, 0)
    p.iconst(0, 0)
    p.loop_r(11, n, lambda: p.stpost(0, 0))


def block_ptrs(p: Prog) -> None:
    """C['lp'], C['rp']: track C['t']'s block, L and R. Clobbers R0, R1, R12"""
    p.ld(0, C["t"])
    p.lsh(1, 0, 8)
    p.iconst(12, D.BUS_BLOCKS)
    p.iop(1, 12, "+", 1)
    p.st(C["lp"], 1)
    p.iconst(12, D.BUS_R)
    p.iop(1, 12, "+", 1)
    p.st(C["rp"], 1)


def take_input(p: Prog) -> None:
    """XL, XR = the track's block x G_IN"""
    for src, dst in (("lp", XL), ("rp", XR)):
        p.ld(0, C[src])
        p.seti(0, 0)
        p.iconst(0, dst)
        p.seti(1, 0)
        p.fconst(2, G_IN)

        def one():
            p.ldpost(0, 0)
            p.fop(0, 0, "*", 2)
            p.stpost(1, 0)
        p.loop_r(11, D.BLOCK, one)


def blend(p: Prog) -> None:
    """the track's block: x + (wet G_OUT - x) MIX g. 2026-11-12 (the guard's hold, guard.ins_gate; opt-host's ins_fade):
    g = 1 (MIX x 1.0, exact: the sound as before), or by the gate's status a ramp: 1 (back) 1/32 .. 1, 4 (refused,
    run once more) 31/32 .. 0, the block's end dry"""
    p.fconst(8, 1.0)
    p.fconst(7, 0.0)
    p.ld(13, C["ist"])
    p.iconst(12, 1)
    p.if_(13, "EQ", 12, lambda: (p.fconst(8, 1.0 / D.BLOCK), p.fconst(7, 1.0 / D.BLOCK)), kind="i")
    p.iconst(12, 4)
    p.if_(13, "EQ", 12, lambda: (p.fconst(8, 1.0 - 1.0 / D.BLOCK), p.fconst(7, -1.0 / D.BLOCK)), kind="i")
    def chan(src, wet, lean):
        p.ld(0, C[src])
        p.seti(0, 0)
        p.seti(1, 0)
        p.iconst(0, wet)
        p.seti(2, 0)
        p.fconst(4, G_OUT)
        p.ld(5, C["mix"])
        p.fpass(6, 8)
        if lean:
            p.fop(3, 5, "*", 6)                  # MIX g, g 1.0 throughout: the same bits each sample

        def one():
            p.ldpost(0, 0)                       # x
            p.ldpost(1, 2)                       # wet
            p.fop(1, 1, "*", 4)
            p.fop(1, 1, "-", 0)
            if not lean:
                p.fop(3, 5, "*", 6)              # MIX g
                p.fop(6, 6, "+", 7)
            p.fop(1, 1, "*", 3)
            p.fop(0, 0, "+", 1)
            p.stpost(1, 0)
        p.loop_r(11, D.BLOCK, one)

    def both(lean):
        for src, wet in (("lp", WL), ("rp", WR)):
            chan(src, wet, lean)
    p.ifz(7, "EQ", lambda: both(True), lambda: both(False), kind="f")   # 2026-11-22: no fade (step 0): lean


def params(p: Prog, scales) -> None:
    """PARF[k] = the record's field (2 + SCALES[k][0]) x SCALES[k][1] (a field None: 0.0); C['mix'] = MIX / 127"""
    p.ld(2, C["rec"])
    p.seti(4, 2)
    for k, (f, sc) in enumerate(scales):
        if f is None:
            p.fconst(8, 0.0)
        else:
            p.ldi(8, 2 + f, 4)
            p.iconst(9, 0)
            p.float_(8, 8, 9)
            p.fconst(9, sc)
            p.fop(8, 8, "*", 9)
        p.st(PARF + 4 * k, 8)
    p.ldi(8, 1, 4)
    p.iconst(9, 0)
    p.float_(8, 8, 9)
    p.fconst(9, 1 / 127)
    p.fop(8, 8, "*", 9)
    p.st(C["mix"], 8)


# FDN8: K1 PRE, K2 SIZE, K3 DAMP, K4 MOD, K5 HPF, K6 LPF -> the stock reverb's struct (PRE DEC FREQ GAIN HPF LPF)
FDN8_PAR = [(k, 1 / 127) for k in range(6)]
# XDLY: K1 TIME 1, K2 TIME 2, K3 FDBK, K4 MOD, K5 TONE -> the stock delay's struct (TIME/127, X, WID/128,
# FDBK/128, HPF/127, LPF/127)
XDLY_PAR = [(0, 1 / 127), (None, 0.0), (1, 1 / 128), (2, 1 / 128), (3, 1 / 127), (4, 1 / 127)]


def owner(p: Prog, slot: int, fresh) -> None:
    """OWNER[SLOT + inst] = 1 + record | type << 8; when it differs, FRESH() (the instance starts as a
    new engine: its swapped-in words set anew). Clobbers R0-R3, R8, R12, I4 before FRESH"""
    def changed():
        p.sti(0, 4, 1)
        fresh()
    owner_differs(p, slot, changed)


def owner_differs(p: Prog, slot: int, then) -> None:
    """THEN() when OWNER[SLOT + inst] is not 1 + record | type << 8 (R1 that word, I4 at OWNER[SLOT + inst]).
    Clobbers R0-R3, R8, R12, I4"""
    p.ld(0, C["inst"])
    p.lsh(0, 0, 2)
    p.iconst(12, OWNER + 4 * slot)
    p.iop(0, 12, "+", 0)
    p.seti(4, 0)
    p.ld(8, C["i"])
    p.iconst(12, 1)
    p.iop(1, 8, "+", 12)
    p.ld(2, C["sel"])
    p.lsh(2, 2, 8)
    p.iop(1, 1, "OR", 2)
    p.ldi(3, 0, 4)
    p.if_(1, "NE", 3, then, kind="i")


def claim(p: Prog) -> None:
    """the record claims its unit's instance (C['aa'], its aux words: design.BUS_AUX_L2 + 16 (first + inst)):
    OWNER 0 when the last pass did not claim it (it went away and came back: it starts fresh), or while the guard
    holds it out (its out count, aux word 2, not 0: it comes back fresh, 2026-11-14 "start fresh"), then LAST = this
    pass. Run whether the guard then runs the unit or holds it. Clobbers R0-R3, R12, I4"""
    assert 4 * D.AUX_WORDS == 16 and D.BUS_AUX_L2 % 4 == 0
    p.ld(0, C["aa"])
    p.seti(4, 0)
    p.ldi(3, 2, 4)                               # the out count (perc.guard.ins_gate)
    p.lsh(0, 0, -2)
    p.iconst(12, LAST - D.BUS_AUX_L2 // 4)
    p.iop(0, 12, "+", 0)
    p.seti(4, 0)
    p.ld(1, PASSN)
    p.ldi(2, 0, 4)
    p.sti(0, 4, 1)
    p.dec(2, 2)                                  # (PASSN counts down: the pass before is this one + 1)

    def gone():
        p.iconst(0, 0)
        p.sti(-(LAST - OWNER) // 4, 4, 0)
    p.if_(2, "NE", 1, lambda: p.iconst(3, 1), kind="i")
    p.ifz(3, "NE", gone)


def enter(p: Prog, sw: int, model) -> None:
    """the engine's MODE 1 call: a leaf call to SW (I12 = the return address - 1)"""
    if p.run:
        model(p.mem)
        return
    ret = p.label("eret")
    p.known.clear()
    p.lines.append("      R12 = 0x0;".ljust(40) + f"// return address - 1: {ret}. - 1")
    p.e("I12 = R12;")
    p.jump_abs("", sw, "the engine, MODE 1 (it returns with JUMP (M14, I12))")
    p.place(ret)


def unit_fdn8(p: Prog) -> None:
    def run():
        p.ld(0, C["fds"])

        def keep_send():
            copy(p, FD_SEND, FP.STATE, FP.DYN_WORDS)
            copy(p, FD_SEND + 4 * FP.DYN_WORDS, FP.ACT, FP.NV)
            copy(p, FP.ACT, FP.VT3, FP.NV)       # 2026-11-22: every instance runs HALF (fdn8.lite)
            p.iconst(0, 1)
            p.st(C["fds"], 0)
        p.ifz(0, "EQ", keep_send)
        store_area(p, "own", FD_STORE, FD_L1_BYTES)
        copy(p, FP.STATE, "own", FP.DYN_WORDS)

        def fresh():                             # a new engine: zeros, its ring, the LFOs' start phases
            zero(p, FP.STATE, FP.DYN_WORDS)
            p.ld(0, C["inst"])
            p.lsh(0, 0, D.FDN8_RING_STRIDE.bit_length() - 1)
            p.iconst(12, D.FDN8_RING_DDR)
            p.iop(0, 12, "+", 0)
            p.st(FP.C["ring"], 0)
            for k in range(8):
                p.iconst(0, FP.D.LFO_PH0[k])
                p.st(FP.C[f"ph{k}"], 0)
        owner(p, 0, fresh)
        params(p, FDN8_PAR)
        for name, v in (("par", PARF), ("io", DESC), ("mode", 1)):
            p.iconst(0, v)
            p.st(FP.C[name], 0)
        for k, src in enumerate(("lp", "rp")):  # 2026-11-22: HALF reads the track's block itself (x G_IN in its
            p.ld(0, C[src])                      # decimator, fdn8.stages._decimate): no copy
            p.st(INP + 4 * k, 0)
        enter(p, D.FDN8_SW, FP.run_instance)
        for k, buf in enumerate((XL, XR)):       # (the descriptor as unit_io left it, for XDLY)
            p.iconst(0, buf)
            p.st(INP + 4 * k, 0)
        copy(p, "own", FP.STATE, FP.DYN_WORDS)
    run()                                        # (slot gates it and blends once for both units)


def fdn8_bound(p: Prog) -> None:
    """C['bnd'] = the guard's bound for this block of the instance (2026-11-12, main: the skips 1,579 -> 40,041 a
    minute on the unit with 64,000 on every block): design.FDN8_COST_CLEAR when it will clear its ring (its
    stored clr nonzero, or a new owner: fresh, then cleared), else COST[FDN8]. Clobbers R0-R3, R8, R12, I4"""
    store_area(p, "own", FD_STORE, FD_L1_BYTES)
    p.ld(2, C["own"])
    p.seti(4, 2)
    p.ldi(0, (FP.C["clr"] - FP.STATE) // 4, 4)
    p.iconst(1, D.COST[D.FDN8])
    p.ifz(0, "NE", lambda: p.iconst(1, D.FDN8_COST_CLEAR))
    p.st(C["bnd"], 1)
    owner_differs(p, 0, lambda: (p.iconst(1, D.FDN8_COST_CLEAR), p.st(C["bnd"], 1)))


def unit_xdly(p: Prog) -> None:
    def run():
        p.ld(0, C["xds"])

        def keep_send():
            copy(p, XD_SEND, XP.STATE, XP.DYN_WORDS)
            p.iconst(0, 1)
            p.st(C["xds"], 0)
        p.ifz(0, "EQ", keep_send)
        store_area(p, "own", XD_STORE, XD_L1_STRIDE)
        copy(p, XP.STATE, "own", XP.DYN_WORDS)

        def fresh():                             # a new engine: zeros, its two lines
            zero(p, XP.STATE, XP.DYN_WORDS)
            p.ld(0, C["inst"])
            p.lsh(0, 0, D.XDLY_LINES_STRIDE.bit_length() - 1)
            p.iconst(12, D.XDLY_LINES_DDR)
            p.iop(0, 12, "+", 0)
            p.st(XP.C["la"], 0)
            p.iconst(12, D.XDLY_LINES_STRIDE // 2)
            p.iop(0, 12, "+", 0)
            p.st(XP.C["lb"], 0)
        owner(p, D.FDN8_INSTANCES, fresh)
        params(p, XDLY_PAR)
        for name, v in (("par", PARF), ("io", DESC), ("mode", 1)):
            p.iconst(0, v)
            p.st(XP.C[name], 0)
        take_input(p)
        enter(p, D.XDLY_SW, XP.run_instance)
        copy(p, "own", XP.STATE, XP.DYN_WORDS)
    run()                                        # (slot gates it and blends once for both units)


def slot(p: Prog) -> None:
    """record i (= 2 t + j): its type and instance; FDN8 or XDLY with an instance in range: its unit"""
    p.ld(0, C["i"])
    p.lsh(1, 0, 5)
    p.iconst(12, PR.TABLE)
    p.iop(2, 12, "+", 1)
    p.st(C["rec"], 2)
    p.seti(4, 2)
    p.ldi(3, 0, 4)
    p.iconst(12, (1 << D.TYPE_BITS) - 1)
    p.iop(5, 3, "AND", 12)
    p.st(C["sel"], 5)
    p.lsh(3, 3, -D.TYPE_BITS)
    p.st(C["inst"], 3)

    p.iconst(0, 0)
    p.st(C["unit"], 0)

    def unit(k: int, first: int) -> None:       # C['unit'] = K and its aux words (design.BUS_AUX_L2)
        p.iconst(0, k)
        p.st(C["unit"], 0)
        p.ld(0, C["inst"])
        p.lsh(0, 0, 4)
        p.iconst(12, D.BUS_AUX_L2 + 4 * D.AUX_WORDS * first)
        p.iop(1, 12, "+", 0)
        p.st(C["aa"], 1)

    def fdn8():
        p.ld(3, C["inst"])
        p.iconst(12, D.FDN8_INSTANCES)
        p.if_(3, "LT", 12, lambda: unit(1, 0), kind="i")

    def xdly():
        p.ld(3, C["inst"])
        p.iconst(12, D.XDLY_INSTANCES)
        p.if_(3, "LT", 12, lambda: (p.iconst(1, D.COST[D.XDLY]), p.st(C["bnd"], 1), unit(2, D.FDN8_INSTANCES)),
              kind="i")
    p.ld(5, C["sel"])
    p.iconst(6, D.FDN8)
    p.iconst(7, D.XDLY)
    p.if_(5, "EQ", 6, fdn8, lambda: (p.ld(5, C["sel"]), p.iconst(7, D.XDLY),
                                     p.if_(5, "EQ", 7, xdly, kind="i")), kind="i")

    def run():                                   # the unit, then the blend (once for both)
        p.ld(0, C["unit"])
        p.iconst(1, 1)
        p.if_(0, "EQ", 1, lambda: unit_fdn8(p), lambda: unit_xdly(p), kind="i")
        blend(p)

    def gated():                                 # 2026-11-12: the guard's hold (guard.ins_gate), faded in blend
        claim(p)                                 # (2026-11-14) before FDN8's bound: a claim may make it fresh
        p.ld(0, C["unit"])
        p.iconst(1, 1)
        p.if_(0, "EQ", 1, lambda: fdn8_bound(p), kind="i")
        block_ptrs(p)
        G.ins_gate(p, C["bnd"], C["aa"], C["ist"], run, grace=True, typ_at=C["sel"])
    p.ld(0, C["unit"])
    p.ifz(0, "NE", gated)
    p.ld(0, C["i"])
    p.iconst(12, 1)
    p.iop(0, 0, "AND", 12)
    p.ifz(0, "NE", lambda: moved(p))


def moved(p: Prog) -> None:
    """2026-11-11 (the User: "always run in slot order"): record C['rec'], a slot 2 of a BUILT type under a
    slot 1 of design.MOVERS (the pre pass left it out, program.skip_moved): the pre pass's one insert
    (program.one, called at design.INS_ONE_SW) on the track's block x G_IN, L then R, each with its own state
    (MV_STATE) and TAPE ring (design.MV_RING_DDR), then x G_OUT back. MIX is the insert's own (its p0)"""
    def run():
        block_ptrs(p)
        take_input(p)
        for side, buf in ((0, XL), (1, XR)):
            p.ld(0, C["t"])
            p.lsh(0, 0, 1)
            if side:
                p.iconst(12, 1)
                p.iop(0, 12, "+", 0)             # k = 2 t + side
            p.lsh(1, 0, 5)
            p.iconst(12, MV_STATE)
            p.iop(1, 12, "+", 1)
            p.st(PR.C["sa"], 1)
            if D.TAPE in D.BUILT:
                p.lsh(1, 0, 11)
                p.iconst(12, D.MV_RING_DDR)
                p.iop(1, 12, "+", 1)
                p.st(PR.C["rb"], 1)
            p.iconst(1, buf)
            p.st(PR.C["buf"], 1)
            for name in ("t", "sel", "rec"):
                p.ld(1, C[name])
                p.st(PR.C["tr" if name == "t" else name], 1)
            PR.call_one(p, lambda: p.jump_abs("", D.INS_ONE_SW, "the pre pass's one insert (program.one)"))
        for src, x in (("lp", XL), ("rp", XR)):
            p.iconst(0, x)
            p.seti(0, 0)
            p.ld(0, C[src])
            p.seti(1, 0)
            p.fconst(2, G_OUT)

            def one():
                p.ldpost(0, 0)
                p.fop(0, 0, "*", 2)
                p.stpost(1, 0)
            p.loop_r(11, D.BLOCK, one)

    def forget():                                # (2026-11-14) not moved here: the track's two engines forget
        p.ld(0, C["t"])                          # their last M.SEL, so a later move starts from silence
        p.lsh(1, 0, 6)
        p.iconst(12, MV_STATE + 4 * (D.STATE_WORDS - 1))
        p.iop(2, 12, "+", 1)
        p.seti(4, 2)
        p.iconst(0, 0)
        p.sti(0, 4, 0)
        p.sti(D.STATE_WORDS, 4, 0)

    def built():
        p.ld(2, C["rec"])
        p.iconst(12, 4 * D.FIELDS)
        p.iop(2, 2, "-", 12)                     # slot 1's record
        p.seti(4, 2)
        p.ldi(3, 0, 4)
        p.iconst(12, (1 << D.TYPE_BITS) - 1)
        p.iop(3, 3, "AND", 12)
        PR.in_types(p, 4, 3, 8, D.MOVERS)
        p.ifz(4, "NE", lambda: G.ins_admit(p, MV_COST, run, typ_at=C["sel"]), forget)   # (the moved slot's type)
    p.ld(3, C["sel"])
    PR.in_types(p, 4, 3, 8, D.BUILT)
    p.ifz(4, "NE", built, forget)


def body(p: Prog) -> None:
    p.ld(0, PASSN)                               # (2026-11-14) this pass's number (claim), counting down
    p.dec(0, 0)
    p.st(PASSN, 0)
    p.ld(0, D.FLAGS + 8)                         # (perf, 2026-11-10) no BUS record: nothing to walk (2026-11-14:
    p.ifz(0, "NE", lambda: _walk(p),            # every moved engine forgets its last M.SEL)
          lambda: PR.forget_all(p, MV_STATE + 4 * (D.STATE_WORDS - 1)))


def _walk(p: Prog) -> None:
    unit_io(p)                                   # once a pass: the engines only read it, nothing else here writes it
    p.iconst(0, 0)
    p.st(C["fds"], 0)
    p.st(C["xds"], 0)
    p.st(C["i"], 0)

    def each():
        p.ld(0, C["i"])
        p.lsh(1, 0, -1)
        p.st(C["t"], 1)
        slot(p)
        p.ld(0, C["i"])
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
        p.st(C["i"], 0)
    PR._tracks(p, each, D.RECORDS)
    p.ld(0, C["fds"])

    def back_fd():
        copy(p, FP.STATE, FD_SEND, FP.DYN_WORDS)
        copy(p, FP.ACT, FD_SEND + 4 * FP.DYN_WORDS, FP.NV)
    p.ifz(0, "NE", back_fd)
    p.ld(0, C["xds"])
    p.ifz(0, "NE", lambda: copy(p, XP.STATE, XD_SEND, XP.DYN_WORDS))


def program(prefix: str = "ib") -> str:
    p = Prog("emit", prefix=prefix)
    p.raw("// insbus.asm -- the bus inserts FDN8 and XDLY per track (docs/inserts.md). GENERATED")
    p.raw("// by scripts/gen_inserts_asm.py from dnfw.inserts.bus; do not edit by hand.")
    p.raw("")
    p.raw(".SECTION/PM seg_pmco;")
    p.raw("")
    p.raw(".GLOBAL wr_inbus.;")
    p.raw("wr_inbus.:")
    save(p)
    G.ins_start(p, 3)
    body(p)
    G.ins_end(p, last=True)                      # 2026-11-11: its end time too (the guard's REST_OUT)
    restore(p)
    p.e(DISPLACED, "the routing's instruction the JUMP took the place of")
    p.jump_abs("", RESUME_SW, "back into the routing: it sums the tracks' blocks into the main bus next")
    p.emit_subs()
    p.raw(".wr_inbus..end:")
    p.raw("      .type wr_inbus.,STT_FUNC;")
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
