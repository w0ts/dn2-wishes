"""FDN8's DSP code, in the DSL (dnfw.perc.dsl): one program, emitted as SHARC assembly
(fdn8.asm) and run in Python as its exact model. Held bit for bit to dnfw.fdn8.ref, which
spells out the design and every operation's order; this module only says where each value
lives and which register holds it.

**The slot.** The FX bus calls the stock reverb with `CJUMP 0xb836bc (DB)` at sw 0x1c1d11 and
its two pushes (R4 = its DDR state 0x80000018, R8 = its parameter struct 0x257918, R12 = the
bus's I/O descriptor 0x257e6c: +4 -> {in L, in R}, +0xc -> {out L, out R}, 32 floats each).
The build changes only that CJUMP's target, to wr_fdn8 (dnfw.waverider.dsp.FDN8_SW): the
pushes still run, so wr_fdn8 is entered exactly as the stock reverb is. It saves every
register it uses (R0-R15, I0-I4, I12, ASTAT), then

- TYPE (the frame's k 48, the low half of DM 0x25ceb4) not 0, and no switch pending: restores
  every register and JUMPs to 0xb836bc. The stock reverb runs as if called directly and
  returns to the bus (sw 0x1c1d18) itself: the stock reverb, unchanged.
- TYPE changed: the type switched to is cleared first (FDN8: its ring; stock: its four sample
  buffers in 0x80000018..), 4096 words a block, the wet silent meanwhile, so an old tail never
  comes back. FDN8 starts with its filters at 0 and its parameters worked out again.
- TYPE 0: one block of FDN8 into out L / R (the wet only; the bus adds VOL as for the stock).
Both of ours return with the stock C epilogue.

Where things are: the code in L2 (FDN8_SW), its state in L1 (STATE), its ring in DDR (RING,
256 KB of float32, zeros at power-on).

**2026-11-10: also the per-track FDN8 inserts' engine** (dnfw.inserts.bus). The bus pass swaps an
instance's words (DYN_WORDS from STATE, and the active variant table ACT) in for the send reverb's,
sets MODE to 1 and enters wr_fdn8 as a leaf call (I12 = its return address - 1). After save(), MODE 1
runs one block of that instance (its ring at the word `ring`, its parameters and I/O where `par` and
`io` point, a fresh instance (`cur` 0) switched to FDN8 first: the ring cleared, the filters at 0),
restores every register and returns with JUMP (M14, I12). MODE 0, the bus's call: as before.
"""

from __future__ import annotations

from ..perc.dsl import Mem, Prog
from . import design as D
from . import ref as R

STATE = 0x2E6400                 # L1 block 1's free tail (dnfw.waverider.dsp: after MNM_RENDER)
STATE_BYTES = 0xA00              # (the last 512 B of the block: XDLY's words)
RING = 0x82400000                # DDR, 256 KB, aligned to its size
TYPE_WORD = 0x25CEB4             # the frame image's k 48 (Reverb FX Routing), low half
STOCK_REVERB = 0xB836BC
STOCK_STATE = R.STOCK_STATE
MASK4 = D.RING_MASK << 2

_NAMES = (["ring", "mode", "im", "cur", "clr", "pos", "force", "p4", "pd4", "xw", "gd1", "gd2", "gh", "ah", "al", "hs", "ls",
           "dq", "io", "par", "went", "qin", "qn", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7"]
          + [f"{n}{k}" for n in ("ph", "ro", "eta", "ap", "lp", "c", "g", "f") for k in range(8)]
          + [f"last{k}" for k in range(6)] + [f"pr{k}" for k in range(6)]
          + [f"sv{k}" for k in range(16)] + ["svi0", "svi1", "svi2", "svi3", "svi4", "svi12", "sva"]
          + ["xsd", "xf", "xwl", "xwr", "gdx1", "gdx2"] + [f"gx{k}" for k in range(8)])   # 2026-11-11: the second page, after the words an instance swaps
C = {n: STATE + 4 * k for k, n in enumerate(_NAMES)}
assert len(C) == len(_NAMES), "a state word named twice"
DYN_WORDS = (C["sv0"] - STATE) // 4               # an instance's words: STATE .. sv0 (then ACT's)
CTAB = STATE + 4 * len(_NAMES)                    # the stock buffers' chunk addresses
N_STOCK_CHUNKS = R.STOCK_WORDS // R.CHUNK
assert all((b - a) % (4 * R.CHUNK) == 0 for a, b in R.STOCK_BUFS)
# the active variant's table (what differs between FDN8 and LONG, design.variant), copied from
# VT1 / VT2 at a switch: a line's read centre and gain length (floats), its damping length, its
# ring offsets (x 4) and the diffusers', the decay factor
_ACT = ([f"lc{k}" for k in range(8)] + [f"ng{k}" for k in range(8)] + [f"sl{k}" for k in range(8)]
        + [f"rl{k}" for k in range(8)] + [f"rw{k}" for k in range(8)] + [f"db{k}" for k in range(4)]
        + [f"dw{k}" for k in range(4)] + ["ktv"])
ACT = CTAB + 4 * N_STOCK_CHUNKS
A = {n: ACT + 4 * k for k, n in enumerate(_ACT)}
NV = len(_ACT)
VT1 = ACT + 4 * NV
VT2 = VT1 + 4 * NV
assert VT2 + 4 * NV <= STATE + STATE_BYTES


def variant_words(v: int) -> list[int]:
    import struct
    d = D.variant(v)

    def fw(x):
        return struct.unpack("<I", struct.pack("<f", float(R.F(x))))[0]
    w = {}
    for k in range(8):
        w[f"lc{k}"] = fw(d["L"][k] + D.CM - 0.5)
        w[f"ng{k}"] = fw(-(d["L"][k] + D.CM))
        w[f"sl{k}"] = fw(d["sl"][k])
        w[f"rl{k}"] = d["RL"][k]
        w[f"rw{k}"] = d["RL"][k] * 4
    for k in range(4):
        w[f"db{k}"] = (d["RA"][k] + d["A"][k]) * 4
        w[f"dw{k}"] = d["RA"][k] * 4
    w["ktv"] = fw(d["ktv"])
    return [w[n] for n in _ACT]


def stock_chunks() -> list[int]:
    out = []
    for a, b in R.STOCK_BUFS:
        out += [STOCK_STATE + x for x in range(a, b, 4 * R.CHUNK)]
    return out


def state_bytes() -> bytes:
    """the L1 state's initial contents: zeros (cur 0: the stock reverb), the LFOs' start
    phases, and the chunk table"""
    import struct
    w = [0] * (STATE_BYTES // 4)
    w[(C["ring"] - STATE) // 4] = RING
    for k in range(8):
        w[(C[f"ph{k}"] - STATE) // 4] = D.LFO_PH0[k]
    for k, a in enumerate(stock_chunks()):
        w[(CTAB - STATE) // 4 + k] = a
    for base, v in ((VT1, 1), (VT2, 2)):
        for k, x in enumerate(variant_words(v)):
            w[(base - STATE) // 4 + k] = x
    return struct.pack(f"<{len(w)}I", *w)


# -- the leaf routines: F0 in, F0 out; they clobber R1-R4 and R12 --------------------------

def _poly(p: Prog, d: int, t: int, c, tmp: int) -> None:
    p.fconst(d, c[-1])
    for k in range(len(c) - 2, -1, -1):
        p.fop(d, d, "*", t)
        p.fconst(tmp, c[k])
        p.fop(d, d, "+", tmp)


def _exp2(p: Prog) -> None:
    p.fconst(1, -100.0)
    p.fop(0, 0, "MAX", 1)
    p.trunc(1, 0)                                # n, toward 0
    p.iconst(2, 0)
    p.float_(2, 1, 2)

    def down():                                  # floor
        p.iconst(3, 1)
        p.iop(1, 1, "-", 3)
        p.fconst(3, 1.0)
        p.fop(2, 2, "-", 3)
    p.if_(2, "GT", 0, down)
    p.fop(2, 0, "-", 2)                          # the fraction
    _poly(p, 0, 2, R.EXP2_C, 3)
    p.iconst(12, 127)
    p.iop(1, 12, "+", 1)
    p.lsh(1, 1, 23)                              # 2^n
    p.fop(0, 0, "*", 1)


def _log2(p: Prog) -> None:
    p.lsh(1, 0, -23)
    p.iconst(12, 127)
    p.iop(1, 1, "-", 12)                         # the exponent
    p.iconst(12, 0x7FFFFF)
    p.iop(2, 0, "AND", 12)
    p.iconst(12, 0x3F800000)
    p.iop(2, 2, "OR", 12)                        # the mantissa, 1 .. 2
    p.fconst(3, 1.0)
    p.fop(2, 2, "-", 3)
    p.iconst(12, 0)
    p.float_(1, 1, 12)
    _poly(p, 0, 2, R.LOG2_C, 3)
    p.fop(0, 1, "+", 0)


def _recip(p: Prog) -> None:
    p.iconst(1, R.RECIP_MAGIC)
    p.iop(1, 1, "-", 0)
    p.fconst(3, 2.0)
    for _ in range(R.NEWTON):
        p.fop(2, 0, "*", 1)
        p.fop(2, 3, "-", 2)
        p.fop(1, 1, "*", 2)
    p.fpass(0, 1)


def _sqrt(p: Prog) -> None:
    p.lsh(1, 0, -1)
    p.iconst(12, R.RSQRT_MAGIC)
    p.iop(1, 12, "-", 1)
    p.fconst(3, 0.5)
    p.fop(2, 0, "*", 3)                          # x / 2
    p.fconst(4, 1.5)
    for _ in range(R.NEWTON):
        p.fop(3, 1, "*", 1)
        p.fop(3, 2, "*", 3)
        p.fop(3, 4, "-", 3)
        p.fop(1, 1, "*", 3)
    p.fop(0, 0, "*", 1)


def _sine(p: Prog) -> None:
    """R0 a phase of 2^32 -> F0 its sine"""
    p.iconst(1, -31)
    p.float_(0, 0, 1)
    p.fconst(1, 0.5)

    def hi():
        p.fconst(2, 1.0)
        p.fop(0, 2, "-", 0)

    def lo():
        p.fconst(1, -0.5)

        def neg():
            p.fconst(2, -1.0)
            p.fop(0, 2, "-", 0)
        p.if_(0, "LT", 1, neg)
    p.if_(0, "GT", 1, hi, lo)
    p.fop(2, 0, "*", 0)
    _poly(p, 1, 2, R.SIN_C, 3)
    p.fop(0, 1, "*", 0)


def exp2(p):
    p.call("exp2", lambda: _exp2(p))


def log2(p):
    p.call("log2", lambda: _log2(p))


def recip(p):
    p.call("recip", lambda: _recip(p))


def sqrt(p):
    p.call("sqrt", lambda: _sqrt(p))


def sine(p):
    p.call("sine", lambda: _sine(p))


# -- the parameters (ref.Ref.params): F5 s, F6 d, F7 y; t0.. spills ------------------------

def params(p: Prog) -> None:
    def clamp(k):
        p.ld(0, C[f"last{k}"])
        p.fconst(1, 0.0)
        p.fop(0, 0, "MAX", 1)
        p.fconst(1, 1.0)
        p.fop(0, 0, "MIN", 1)
        p.st(C[f"pr{k}"], 0)
    for k in range(6):
        clamp(k)
    p.ld(0, C["pr1"])
    p.fconst(1, 127.0)
    p.fop(5, 0, "*", 1)                          # s
    p.ld(0, C["pr2"])
    p.fop(6, 0, "*", 1)                          # d
    p.fconst(1, D.KNEE)
    p.fop(7, 5, "-", 1)
    p.fconst(1, 0.0)
    p.fop(7, 7, "MAX", 1)                        # y
    p.st(C["t0"], 7)
    p.fop(0, 5, "-", 7)                          # sk
    p.fconst(1, 44.0)
    p.fop(2, 1, "*", 0)
    p.fconst(1, 23109.0)
    p.fop(2, 1, "-", 2)
    p.fop(2, 2, "*", 0)
    p.fop(2, 2, "*", 0)
    p.fconst(1, 1 / 65536)
    p.fop(2, 2, "*", 1)                          # t
    p.fconst(1, 135.0)
    p.fop(3, 1, "*", 0)                          # u
    p.fconst(1, 14647.0)
    p.fop(3, 1, "-", 3)
    p.fop(3, 3, "+", 2)
    p.fconst(1, R.K_KT)
    p.fop(3, 3, "*", 1)                          # kt
    p.st(C["t1"], 3)
    p.fconst(1, D.DBL_PER_STEP)
    p.fop(4, 7, "*", 1)                          # e
    p.fconst(1, 126.0)
    p.fop(0, 5, "-", 1)
    p.fconst(1, 0.0)
    p.fop(0, 0, "MAX", 1)
    p.fconst(1, 1.0)
    p.fop(0, 0, "MIN", 1)
    p.fconst(1, D.FRZ)
    p.fop(0, 0, "*", 1)
    p.fop(4, 4, "+", 0)
    p.st(C["t2"], 4)                             # e
    p.fconst(1, 0.0)
    p.fop(0, 1, "-", 4)
    exp2(p)
    p.st(C["t3"], 0)                             # rho
    p.ld(3, C["t1"])
    p.fop(3, 3, "*", 0)
    p.ld(1, A["ktv"])
    p.fop(3, 3, "*", 1)
    p.st(C["t4"], 3)                             # ktr
    for k in range(8):
        p.ld(3, C["t4"])
        p.ld(1, A[f"ng{k}"])
        p.fop(0, 3, "*", 1)
        exp2(p)
        p.st(C[f"g{k}"], 0)
    c0, c1, c2, c3 = D.DAMP_C
    p.fconst(1, c3)
    p.fop(2, 1, "*", 6)
    p.fconst(1, c2)
    p.fop(2, 1, "-", 2)                          # w
    p.fop(3, 6, "*", 6)                          # d^2
    p.fop(2, 2, "*", 3)
    p.fconst(1, 1 / 65536)
    p.fop(2, 2, "*", 1)
    p.fconst(1, c1 / 256)
    p.fop(3, 6, "*", 1)
    p.fconst(1, c0)
    p.fop(3, 1, "-", 3)
    p.fop(3, 3, "-", 2)                          # kq
    p.fconst(1, 1.0)
    p.fop(3, 3, "MAX", 1)
    p.fconst(1, 32767.0)
    p.fop(3, 3, "MIN", 1)
    p.fconst(1, 1 / 32768)
    p.fop(3, 3, "*", 1)
    p.fconst(1, 1.0)
    p.fop(3, 1, "-", 3)                          # a
    p.fconst(1, D.A_MAX)
    p.fop(3, 3, "MIN", 1)
    p.st(C["t5"], 3)
    p.fconst(1, 1.0)
    p.fop(0, 1, "-", 3)
    p.fop(0, 0, "*", 0)
    recip(p)
    p.ld(3, C["t5"])
    p.fop(0, 3, "*", 0)                          # q
    p.fconst(1, D.K22)
    p.fop(0, 0, "*", 1)
    p.fconst(1, 1.0)
    p.fop(0, 0, "+", 1)
    log2(p)
    p.st(C["t6"], 0)                             # v
    p.ld(3, C["t3"])
    p.fconst(1, 1 / D.LREF)
    p.fop(3, 3, "*", 1)
    p.st(C["t7"], 3)                             # rl
    for k in range(8):
        p.ld(3, C["t7"])
        p.ld(1, A[f"sl{k}"])
        p.fop(3, 3, "*", 1)                      # sc
        p.ld(0, C["t6"])
        p.fop(0, 0, "*", 3)
        p.fconst(1, D.T_MAX)
        p.fop(0, 0, "MIN", 1)
        exp2(p)
        p.fconst(1, 1.0)
        p.fop(0, 0, "-", 1)
        p.fconst(1, 1 / D.K48)
        p.fop(5, 0, "*", 1)                      # q
        p.fop(6, 5, "+", 5)                      # 2q
        p.fconst(1, 4.0)
        p.fop(0, 5, "*", 1)
        p.fconst(1, 1.0)
        p.fop(0, 0, "+", 1)
        p.fop(7, 6, "+", 1)                      # 2q + 1
        sqrt(p)
        p.fop(0, 7, "+", 0)
        recip(p)
        p.fop(0, 6, "*", 0)
        p.st(C[f"c{k}"], 0)
    p.ld(7, C["t0"])                             # y
    p.fconst(1, R.DEP_GROW)
    p.fop(0, 7, "*", 1)
    p.fconst(1, D.FEXC48)
    p.fop(0, 0, "+", 1)
    p.ld(2, C["pr3"])
    p.fconst(1, D.MOD_MAX)
    p.fop(2, 2, "*", 1)
    p.fop(0, 0, "*", 2)
    p.st(C["dq"], 0)
    p.ld(0, C["pr0"])
    p.fop(0, 0, "*", 0)
    p.fconst(1, float(D.PD_MAX))
    p.fop(0, 0, "*", 1)
    p.trunc(0, 0)
    p.iconst(1, D.PD_MAX)
    p.iop(0, 0, "MIN", 1)
    p.iconst(12, D.RB_PD)
    p.iop(0, 12, "+", 0)
    p.lsh(0, 0, 2)
    p.st(C["pd4"], 0)
    p.fconst(1, 0.05 / 37)
    p.fop(0, 7, "*", 1)
    p.fconst(1, 0.75)
    p.fop(0, 0, "+", 1)
    p.st(C["gd1"], 0)
    p.fconst(1, 0.075 / 37)
    p.fop(0, 7, "*", 1)
    p.fconst(1, 0.625)
    p.fop(0, 0, "+", 1)
    p.st(C["gd2"], 0)
    p.ld(0, C["t2"])
    p.fconst(1, -0.125)
    p.fop(0, 0, "*", 1)
    exp2(p)
    p.fconst(1, D.GIN * 0.5)
    p.fop(0, 0, "*", 1)
    p.st(C["gh"], 0)
    for k, w, name in ((4, R.W_HPF, "ah"), (5, R.W_LPF, "al")):
        p.ld(0, C[f"pr{k}"])
        p.fconst(1, R.LOG2_100)
        p.fop(0, 0, "*", 1)
        exp2(p)
        p.fconst(1, w)
        p.fop(0, 0, "*", 1)
        exp2(p)
        p.fconst(1, 1.0)
        p.fop(0, 1, "-", 0)
        p.st(C[name], 0)


# -- per block -------------------------------------------------------------------------

def lfo(p: Prog) -> None:
    for k in range(8):
        p.ld(0, C[f"ph{k}"])
        p.iconst(12, D.LFO_INC[k])
        p.iop(0, 12, "+", 0)
        p.st(C[f"ph{k}"], 0)
        sine(p)
        p.ld(1, C["dq"])
        p.fop(0, 1, "*", 0)
        p.ld(1, A[f"lc{k}"])
        p.fop(0, 0, "+", 1)
        p.trunc(5, 0)                            # D
        p.iconst(1, 0)
        p.float_(1, 5, 1)
        p.fop(0, 0, "-", 1)
        p.fconst(1, 0.5)
        p.fop(0, 0, "-", 1)
        p.fop(0, 0, "*", 1)                      # h
        p.fop(2, 0, "*", 0)
        p.fconst(1, 1.0)
        p.fop(3, 1, "-", 0)
        p.fop(3, 3, "+", 2)
        p.fop(3, 0, "*", 3)
        p.fconst(1, 0.0)
        p.fop(3, 1, "-", 3)
        p.st(C[f"eta{k}"], 3)
        p.ld(12, A[f"rl{k}"])
        p.iop(5, 12, "+", 5)
        p.lsh(5, 5, 2)
        p.st(C[f"ro{k}"], 5)


def ring_at(p: Prog, off: int | None = None) -> None:
    """I4 = the ring word at p + off (off4 a constant, or R14 when OFF is None)"""
    if off is not None:
        p.iconst(14, off * 4)
    p.iop(13, 8, "+", 14)
    p.iop(13, 13, "AND", 9)
    p.iop(13, 13, "OR", 10)
    p.seti(4, 13)


def sample(p: Prog) -> None:
    """one sample: R8 4p, R9 the mask, R10 the ring, I0/I1 in, I2/I3 out; R11 the count"""
    p.ldpost(0, 0)
    p.ldpost(1, 1)
    p.fop(0, 0, "+", 1)
    p.ld(1, C["gh"])
    p.fop(0, 0, "*", 1)                          # xin
    p.ld(1, C["hs"])
    p.fop(2, 0, "-", 1)
    p.ld(3, C["ah"])
    p.fop(2, 3, "*", 2)
    p.fop(1, 1, "+", 2)
    p.st(C["hs"], 1)
    p.fop(0, 0, "-", 1)
    p.ld(1, C["ls"])
    p.fop(2, 0, "-", 1)
    p.ld(3, C["al"])
    p.fop(2, 3, "*", 2)
    p.fop(1, 1, "+", 2)
    p.st(C["ls"], 1)
    ring_at(p, D.RB_PD)
    p.sti(0, 4, 1)                               # the pre-delay
    p.ld(14, C["pd4"])
    ring_at(p)
    p.ldi(0, 0, 4)                               # x
    p.ld(5, C["gdx1"])
    p.ld(6, C["gdx2"])
    for k in range(4):
        g = 5 if k < 2 else 6
        p.ld(14, A[f"db{k}"])
        ring_at(p)
        p.ldi(1, 0, 4)                           # b
        p.fop(2, g, "*", 1)
        p.fop(2, 0, "+", 2)                      # v
        p.ld(14, A[f"dw{k}"])
        ring_at(p)
        p.sti(0, 4, 2)
        p.fop(3, g, "*", 2)
        p.fop(0, 1, "-", 3)
    p.st(C["xw"], 0)
    p.iconst(15, 4)
    for k in range(8):
        p.ld(14, C[f"ro{k}"])
        ring_at(p)
        p.ldi(0, 0, 4)                           # u0
        p.iop(14, 14, "+", 15)
        ring_at(p)
        p.ldi(1, 0, 4)                           # u1
        p.ld(2, C[f"ap{k}"])
        p.fop(0, 0, "-", 2)
        p.ld(2, C[f"eta{k}"])
        p.fop(0, 2, "*", 0)
        p.fop(0, 1, "+", 0)                      # o
        p.st(C[f"ap{k}"], 0)
        p.ld(1, C[f"lp{k}"])
        p.fop(1, 1, "-", 0)
        p.ld(2, C[f"c{k}"])
        p.fop(1, 2, "*", 1)
        p.fop(1, 0, "+", 1)
        p.st(C[f"lp{k}"], 1)
        p.ld(2, C[f"gx{k}"])
        p.fop(1, 1, "*", 2)                      # f
        p.st(C[f"f{k}"], 1)
        if k == 0:
            p.fpass(4, 1)
            p.fpass(5, 0)
        else:
            p.fop(4, 4, "+", 1)
            if k == 1:
                p.fpass(6, 0)
            else:
                lr = 5 if k % 2 == 0 else 6
                p.fop(lr, lr, "+" if k in (4, 5) else "-", 0)
    p.fconst(3, 0.25)
    p.fop(4, 4, "*", 3)
    p.ld(7, C["xw"])
    for k in range(8):
        p.ld(1, C[f"f{k}"])
        p.fop(1, 4, "-", 1)
        p.fop(1, 1, "+" if k % 2 == 0 else "-", 7)
        p.ld(14, A[f"rw{k}"])
        ring_at(p)
        p.sti(0, 4, 1)
    p.fconst(3, D.GOUT)
    p.fop(5, 5, "*", 3)
    p.fop(6, 6, "*", 3)
    p.ld(4, C["xwr"])
    p.fconst(7, 0.0)

    def width():
        p.ld(3, C["xwl"])
        p.fop(1, 5, "*", 3)                      # lg wl
        p.fop(2, 6, "*", 4)                      # rg wr
        p.fop(1, 1, "+", 2)
        p.fop(2, 6, "*", 3)                      # rg wl
        p.fop(0, 5, "*", 4)                      # lg wr
        p.fop(2, 2, "+", 0)
        p.stpost(2, 1)
        p.stpost(3, 2)

    def hard():
        p.stpost(2, 5)
        p.stpost(3, 6)
    p.if_(4, "NE", 7, width, hard)
    p.iconst(14, 4)
    p.iop(8, 8, "-", 14)


def io_ptrs(p: Prog) -> None:
    """I0, I1 = in L, R; I2, I3 = out L, R (from the I/O descriptor the bus passed in R12)"""
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


# 2026-11-11 (perf): a block is skipped (its wet written as zeros, nothing else moves: the ring, the LFOs'
# phases and the pointer stand still) once the input has been exactly zero and the wet below 2^-24 (-144 dB) for
# QUIET_BLOCKS blocks in a row. NOT bit-exact to the ungated program once the tail is that small: declared
# sound-neutral (a tail under -144 dB is cut; the LFOs' phases keep moving); False: the old program
QUIET_GATE = True
QUIET_BLOCKS = 4224               # > the ring's length in blocks (RING_WORDS 2^17 / 32 = 4096, 3 s): a delay line holds nothing younger
QUIET_SMALL = 0x33800000          # 2^-24


def _lfo_phases(p: Prog) -> None:
    """a skipped block: only the LFOs' phases move (lfo() does these first; the rest it recomputes from them)"""
    for k in range(8):
        p.ld(0, C[f"ph{k}"])
        p.iconst(12, D.LFO_INC[k])
        p.iop(0, 12, "+", 0)
        p.st(C[f"ph{k}"], 0)


def _quiet_scan_in(p: Prog) -> None:
    """C["qin"] = the OR of the input's 64 words' bits (0: exactly +0.0 throughout). Clobbers R0, R9, R11, I0-I4"""
    io_ptrs(p)
    p.iconst(9, 0)

    def pair():
        p.ldpost(0, 0)
        p.iop(9, 9, "OR", 0)
        p.ldpost(0, 1)
        p.iop(9, 9, "OR", 0)
    p.loop_r(11, D.BLOCK, pair)
    p.st(C["qin"], 9)


def _quiet_after(p: Prog) -> None:
    """after a block run on a silent input: qn + 1 when the wet is below 2^-24 throughout, else 0"""
    def on():
        io_ptrs(p)
        p.iconst(9, 0)
        p.iconst(12, 0x7FFFFFFF)

        def pair():
            p.ldpost(0, 2)
            p.iop(0, 0, "AND", 12)
            p.iop(9, 9, "MAX", 0)
            p.ldpost(0, 3)
            p.iop(0, 0, "AND", 12)
            p.iop(9, 9, "MAX", 0)
        p.loop_r(11, D.BLOCK, pair)
        p.iconst(1, QUIET_SMALL)

        def small():
            p.ld(8, C["qn"])
            p.iconst(10, 1)
            p.iop(8, 8, "+", 10)
            p.st(C["qn"], 8)
        p.if_(9, "LT", 1, small, lambda: (p.iconst(0, 0), p.st(C["qn"], 0)), kind="i")
    p.ld(0, C["qin"])
    p.ifz(0, "EQ", on)


def fdn8_block(p: Prog) -> None:
    if not QUIET_GATE:
        _fdn8_block(p)
        return
    _quiet_scan_in(p)
    p.ld(9, C["qin"])
    p.iconst(3, 0)

    def silent_in():
        p.ld(1, C["qn"])
        p.iconst(2, QUIET_BLOCKS)
        p.if_(1, "GE", 2, lambda: p.iconst(3, 1), kind="i")
    p.ifz(9, "EQ", silent_in, lambda: (p.iconst(0, 0), p.st(C["qn"], 0)))
    p.ifz(3, "NE", lambda: (_lfo_phases(p), silence(p)), lambda: (_fdn8_block(p), _quiet_after(p)))


def extras(p: Prog) -> None:
    """once a block, before the samples: the second page's values (design.EX, ref.Ref.extras) -> xsd xf xwl xwr, and
    the diffusers' gdx1 / gdx2 (g x sd, held to DF_MAX) and the lines' gains gx0..7 (g (1 - f) + f); the instances
    (MODE 1) and a send before the ColdFire's first word use the constants: x 1.0 and + 0.0, exactly today's.
    Clobbers R0-R3, R12"""
    def defaults():
        p.fconst(0, 1.0)
        p.st(C["xsd"], 0)
        p.st(C["xwl"], 0)
        p.fconst(0, 0.0)
        p.st(C["xf"], 0)
        p.st(C["xwr"], 0)

    def real():
        for k, n in enumerate(("xsd", "xf", "xwl", "xwr")):
            p.ld(0, D.EX + 4 * (k + 1))
            p.st(C[n], 0)

    def received():
        p.ld(0, D.EX)
        p.ifz(0, "EQ", defaults, real)
    p.ld(0, C["im"])
    p.ifz(0, "NE", defaults, received)
    p.ld(1, C["xsd"])
    p.fconst(2, D.DF_MAX)
    for src, dst in (("gd1", "gdx1"), ("gd2", "gdx2")):
        p.ld(0, C[src])
        p.fop(0, 0, "*", 1)
        p.fop(0, 0, "MIN", 2)
        p.st(C[dst], 0)
    p.ld(2, C["xf"])
    p.fconst(1, 1.0)
    p.fop(3, 1, "-", 2)                          # 1 - f
    for k in range(8):
        p.ld(0, C[f"g{k}"])
        p.fop(0, 0, "*", 3)
        p.fop(0, 0, "+", 2)
        p.st(C[f"gx{k}"], 0)


def _fdn8_block(p: Prog) -> None:
    # the parameters, when one changed (or after a switch)
    p.ld(3, C["force"])
    p.ld(4, C["par"])
    p.seti(4, 4)
    for k in range(6):
        p.ldi(0, k, 4)
        p.ld(1, C[f"last{k}"])
        p.iop(2, 0, "-", 1)
        p.iop(3, 3, "OR", 2)
        p.st(C[f"last{k}"], 0)
    p.iconst(0, 0)
    p.st(C["force"], 0)
    p.ifz(3, "NE", lambda: params(p))
    lfo(p)
    extras(p)
    io_ptrs(p)
    p.ld(8, C["p4"])
    p.iconst(9, MASK4)
    p.ld(10, C["ring"])
    p.loop_r(11, D.BLOCK, lambda: sample(p))
    p.st(C["p4"], 8)


def silence(p: Prog) -> None:
    io_ptrs(p)
    p.fconst(0, 0.0)

    def zero():
        p.stpost(2, 0)
        p.stpost(3, 0)
    p.loop_r(11, D.BLOCK, zero)


def clearing(p: Prog) -> None:
    """CHUNK words of the type switched to, then the wet silent"""
    p.ld(0, C["pos"])
    p.ld(1, C["cur"])

    def fdn():                                   # the ring, from its start
        p.lsh(2, 0, 2)
        p.ld(12, C["ring"])
        p.iop(2, 12, "+", 2)
        p.seti(4, 2)

    def stock():                                 # the stock buffers: chunk pos / CHUNK's address
        p.lsh(2, 0, -12)                         # (CHUNK is 2^12)
        p.lsh(2, 2, 2)
        p.iconst(12, CTAB)
        p.iop(2, 12, "+", 2)
        p.seti(4, 2)
        p.ldi(2, 0, 4)
        p.seti(4, 2)
    p.ifz(1, "NE", fdn, stock)
    p.fconst(0, 0.0)

    def sixteen():
        for _ in range(16):
            p.stpost(4, 0)
    p.loop_r(11, R.CHUNK // 16, sixteen)
    p.ld(0, C["pos"])
    p.iconst(12, R.CHUNK)
    p.iop(0, 12, "+", 0)
    p.st(C["pos"], 0)
    p.ld(0, C["clr"])
    p.iconst(1, R.CHUNK)
    p.iop(0, 0, "-", 1)
    p.st(C["clr"], 0)
    silence(p)


assert R.CHUNK == 1 << 12


def switch(p: Prog) -> None:
    """R1 the new type"""
    p.st(C["cur"], 1)
    p.iconst(0, 0)
    p.st(C["pos"], 0)

    def to_fdn():
        p.iconst(2, VT1)                         # the variant's table into the active one
        p.iconst(3, 2)
        p.if_(1, "EQ", 3, lambda: p.iconst(2, VT2), kind="i")
        p.seti(4, 2)
        p.iconst(2, ACT)
        p.seti(0, 2)

        def one():
            p.ldpost(2, 4)
            p.stpost(0, 2)
        p.loop_r(11, NV, one)
        p.iconst(0, D.RING_WORDS)
        p.st(C["clr"], 0)
        p.iconst(0, 0)
        for k in range(8):
            p.st(C[f"ap{k}"], 0)
            p.st(C[f"lp{k}"], 0)
        p.st(C["hs"], 0)
        p.st(C["ls"], 0)
        p.iconst(0, 1)
        p.st(C["force"], 0)

    def to_stock():
        p.iconst(0, R.STOCK_WORDS)
        p.st(C["clr"], 0)
    p.ifz(1, "NE", to_fdn, to_stock)


SAVE_I = (0, 1, 2, 3, 4, 12)


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
    """back to the bus as a C function returns (the CJUMP's frame and its pushes)"""
    restore(p)
    if p.run:
        p.mem.put(C["went"], 2)                # (run mode: where it went, for the model)
        return
    p.e("I12 = DM(M7, I6);")
    p.e("JUMP (M14, I12) (DB);")
    p.e("RFRAME;")
    p.e("NOP;")


def send(p: Prog) -> None:
    """the bus's call (MODE 0): R8 and R12 as the bus passed them are in sv8 / sv12; the type asked for
    (a switch when it changed); the stock reverb, when it is the type and nothing is to be cleared"""
    p.ld(0, C["sv8"])
    p.st(C["par"], 0)
    p.ld(0, C["sv12"])
    p.st(C["io"], 0)
    p.ld(0, TYPE_WORD)
    p.iconst(12, 0xFFFF)
    p.iop(0, 0, "AND", 12)
    p.iconst(1, 0)
    p.ifz(0, "EQ", lambda: p.iconst(1, 1))      # the type asked for: 1 FDN8, 2 LONG (0x200)
    p.iconst(2, 0x200)
    p.if_(0, "EQ", 2, lambda: p.iconst(1, 2), kind="i")
    p.ld(2, C["cur"])
    p.if_(1, "NE", 2, lambda: switch(p), kind="i")

    def go_stock():
        restore(p)
        if p.run:
            p.mem.put(C["went"], 1)
            return
        p.jump_abs("", STOCK_REVERB, "the stock reverb, entered as the bus called it")

    def no_clear():
        p.ld(1, C["cur"])
        p.ifz(1, "EQ", go_stock)
    p.ld(0, C["clr"])
    p.ifz(0, "EQ", no_clear)


def instance(p: Prog) -> None:
    """MODE 1: the instance swapped in (dnfw.inserts.bus); a fresh one (cur 0) switched to FDN8 (R1 = 1)"""
    p.ld(2, C["cur"])
    p.iconst(1, 1)
    p.if_(2, "NE", 1, lambda: switch(p), kind="i")


def entry(p: Prog) -> None:
    """after save(): the call's own part (send or instance), then one block (clearing, or FDN8), then back
    as the call came (the stock C epilogue to the bus, or JUMP (M14, I12) to the bus pass)"""
    if p.run:
        p.mem.put(C["went"], 0)
    p.ld(0, C["mode"])
    p.st(C["im"], 0)
    p.iconst(1, 0)
    p.st(C["mode"], 1)
    p.ifz(0, "NE", lambda: instance(p), lambda: send(p))
    if p.run and p.mem.get(C["went"]) == 1:     # (the model: the stock reverb took the call)
        return
    p.ld(0, C["clr"])
    p.ifz(0, "NE", lambda: clearing(p), lambda: fdn8_block(p))
    p.ld(0, C["im"])

    def to_pass():
        restore(p)
        if not p.run:
            p.e("JUMP (M14, I12);", "back to the bus pass (dnfw.inserts.bus)")
            p.e("NOP;", "(never run: the if's own jump follows, and BRANCH-WIN wants 3 parcels")
            p.e("NOP;", " between two branches, scripts/gate_hwrules.py)")
    p.ifz(0, "NE", to_pass, lambda: ret(p))


def program(prefix: str = "fd") -> str:
    p = Prog("emit", prefix=prefix)
    p.raw("// fdn8.asm -- FDN8 in the stock reverb's slot (docs/fdn8.md). GENERATED by")
    p.raw("// scripts/gen_fdn8_asm.py from dnfw.fdn8.program; do not edit by hand.")
    p.raw("")
    p.raw(".SECTION/PM seg_pmco;")
    p.raw("")
    p.raw(".GLOBAL wr_fdn8.;")
    p.raw("wr_fdn8.:")
    save(p)
    entry(p)
    p.emit_subs()
    p.raw(".wr_fdn8..end:")
    p.raw("      .type wr_fdn8.,STT_FUNC;")
    return p.text()


def run(mem: Mem, regs: dict[int, int]) -> tuple[str, Prog]:
    """the model: one call with R0..R15 = REGS on MEM -> ('stock' | 'ours', the Prog)"""
    p = Prog("run", mem=mem)
    for k, v in regs.items():
        p.r[k] = v & 0xFFFFFFFF
    save(p)
    entry(p)
    went = mem.get(C["went"])
    return ("stock" if went == 1 else "ours"), p


def run_instance(mem: Mem) -> Prog:
    """the model of the bus pass's call (MODE 1 set, the instance's words in place)"""
    p = Prog("run", mem=mem)
    save(p)
    entry(p)
    return p
