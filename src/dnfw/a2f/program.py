# SPDX-License-Identifier: AGPL-3.0-or-later
"""The filter machines' DSP pass (a2f.asm), in the DSL: ANALOG 2's filters (dnfw.a2f.models, ported
from Optimist, GPL-3.0-only, firmware/src/engines/analog/a2_models.c and eng_analog2.c) on the voices
whose track's filter type is 7..11 (dnfw.a2f.design: SVF LADR OTA DIOD MS20). Its exact model is the
same calls run in Python (dnfw.a2f.live); dnfw.a2f.ref.Pass spells it out operation by operation.

**Where it runs.** Our per-block chain, after the inserts' pass (inserts.asm JUMPs here instead of to
PING) and before PING (this pass ends with a JUMP to NEXT_SW, PING's wr_ping, which restores the chain's
registers and returns to the stock chain). Every machine has rendered into its voice slot's buffer;
the stock filter is skipped for these types (the unpack maps ColdFire types past 5 to DSP filter 0,
"no filter"), the base-width filter, amp and pan come after. Like PING and the inserts it uses the
registers freely (R0-R15, I0-I4, I12; M6 = 1 and M14 = 1 as the chain leaves them).

**Per voice slot** s (the 16 buffers are slots, not tracks): the track it plays (the s16 map at ROUTE +
2 s; past 15: none), the slot's ColdFire filter type (the frame's 180 + 2 s); 7..11 and built: the
slot's state (16 words at STATE + 64 s; all zero, the last cutoffs "none", when its model or track
changed), the envelope (a trig of the slot starts its attack), then filter 1 and filter 2 in series,
each over the slot's 32 floats in two halves with the model's code (dnfw.a2f.models.half). Any other
type: the slot's model tag is cleared (so it starts afresh when it comes back) and its buffer left.

**The page** (dnfw.waverider.frame.RECORD_FIELDS offsets, floats in the slot's record):
page 1  ATK (+0x1f0) DEC (+0x1f4) FRQ2 (+0x1f8) RES2 (+0x1fc) / FREQ (+0x1cc) RES (+0x1d0)
        MODE (+0x1c8: LP12 LP24 BP HP NOTCH) ENV (+0x204, 0.5 = none, +-6 octaves)
page 2  MOD2 (+0x1ec: 5 choices) . . KEY.T (+0x208) / BASE WDTH BW.RT RSET (stock's, untouched).
A choice from a float x: min(4, trunc(clamp(x, 0, 1) x 5)).

**The cutoffs** in CUT units (0..127, 0.856 semitones each): filter 1 FREQ x 128, filter 2 FRQ2 x 127,
both + KEY.T x (note - 60) semitones (the note cell 0x254b14 + 4 s, as PING reads it) + ENV's depth x
the envelope, clamped to 0..127. Each filter's cutoff moves smoothly: the last block's end, this
block's middle (the envelope after the first half), its end; the SVF's coefficients ramp per sample
between them, the models' are set at each half's end (Optimist's a2_filter / a2m_block, with the
middle from the envelope instead of halfway).

**The envelope**: attack-decay a slot (16 words' 10, 11), stepped twice a block. A trig: attack, from
where it is, a linear rise to 1 over ATK (0.1 ms x 4000^ATK: 0.1 ms .. 400 ms); then the decay, x c a
half (an exponential to -40 dB in DEC: 2 ms x 5000^DEC, 2 ms .. 10 s).
"""

from __future__ import annotations

import math

from ..fdn8 import program as FP
from ..perc import guard as G
from ..perc.dsl import Mem, Prog
from . import design as DS
from . import models as M

ONE_VOICE = False                 # 2026-11-11 (perf, main): every A2 voice is filtered, the ADMIT models admitted against the frame deadline (COST_BY_MODEL); 2026-11-10 it was True (one voice, the newest note's, while a voice cost 17-36 % of a frame: it ran all 16 slots, and its state was in L2). True: one voice a block
# cycles a voice's pass is expected to take, by model (SVF LADR OTA DIOD MS20): the runner's instructions
# + 4 x L2 + 10 x DDR accesses, one voice with the machine's defaults (2026-11-10, HOLD6): 72.6k+, 109.7k+, 115k+, 135k+26k L2, 102k+
COST_BY_MODEL = {"SVF": 8_000, "LADR": 9_500, "OTA": 10_000, "DIOD": 12_000, "MS20": 9_000}
# 2026-11-10 (the User: on HOLD7 the filters do "nothing", warmth only): is the deadline starving them? The runner's
# unit-like clock (silent frame 416k, tail 193k) admits every model, but the unit's tail is unknown. The models that fit
# a frame beside the silent load (silent 64 % + at most 26 %) run without the deadline test; DIOD (36 %) keeps it
ADMIT = {"SVF": 0, "LADR": 0, "OTA": 0, "DIOD": 1, "MS20": 0}
LOAD = 0x200B2400                 # L2: the code (the coordinator's room, to 0x200b5800)
STATE = 0x2DD600                  # L1 (perf, 2026-11-11: was L2 0x200B5800, 4 cycles an access): 16 slots x 64 bytes, then the pass's words, the models', the tables
SLOT_WORDS = 16
SLOT_BYTES = 4 * SLOT_WORDS
Z1, C01, Z2, C02, LVL, STG, TAG, TRK = 0, 4, 5, 9, 10, 11, 12, 13      # a slot's words
NONE = -1.0                       # a last cutoff not yet known

FRAME = 0x25C48C
FTYPE = FRAME + 180               # 16 x s16: the ColdFire filter type (dnfw.waverider.frame.FILTER)
TRIGW = FRAME + 32                # its high half: TRIG_NOTE, bit t (frame offset 34)
RECORDS, RECORD_STRIDE = 0x2554B8, 0x234
NOTES = 0x254B14                  # float semitones, 4 t
BUFFERS = 0x254A60                # 16 pointers: the voice slots' 32 floats
ROUTE = 0x257898                  # 16 x s16: the track each slot plays
TYPE0 = min(DS.TYPES)             # 7: SVF

R_MODE1, R_FREQ, R_RES, R_MODE2 = 0x1C8, 0x1CC, 0x1D0, 0x1EC
R_ATK, R_DEC, R_FRQ2, R_RES2, R_ENV, R_KEY = 0x1F0, 0x1F4, 0x1F8, 0x1FC, 0x204, 0x208

UNITS_PER_SEMI = 127.0 / (12.0 * M.OCT)
ENV_UNITS = 2.0 * 6.0 * 12.0 * UNITS_PER_SEMI      # (ENV - 0.5) x this: +-6 octaves
KEY_MAX = 2.0
ATK_A0 = math.log2(M.N / (1e-4 * M.FS))            # log2 of the step a half at ATK 0 (0.1 ms)
ATK_A1 = math.log2(4000.0)
DEC_K = 4.6 * M.N / (0.002 * M.FS) / math.log(2.0)  # -log2 of the decay a half at DEC 0 (2 ms)
DEC_A1 = math.log2(5000.0)

_NAMES = ["s", "cnt", "tr", "sp", "rec", "lvlA", "lvlB", "kmod", "dmod", "bufb", "fp", "fcnt", "hcnt",
          "g0", "gA", "gB", "cA", "cB", "step", "coef", "ok",
          "f1b", "f1r", "f1m", "f1z", "f2b", "f2r", "f2m", "f2z",
          "ps", "ptr", "pcnt", "first", "pick", "cost", "nfil", "ndry", "quiet"]
SCRATCH = STATE + 16 * SLOT_BYTES
C = {n: SCRATCH + 4 * k for k, n in enumerate(_NAMES)}
MSCRATCH = SCRATCH + 4 * len(_NAMES)
TABLES = MSCRATCH + 4 * M.SCRATCH_WORDS
STATE_SPAN = 0x800


def ctx(models=None) -> M.Ctx:
    return M.Ctx(MSCRATCH, TABLES, DS.BUILT_MODELS if models is None else models)


def state_bytes(models=None) -> bytes:
    """the L2 state's initial contents: zeros, then the models' mix tables"""
    import struct
    X = ctx(models)
    words, _ = M.table_layout(X.models)
    out = bytes(TABLES - STATE) + struct.pack(f"<{len(words)}f", *words)
    assert len(out) <= STATE_SPAN
    return out


# -- helpers ------------------------------------------------------------------------------------
def lshr(p: Prog, d: int, a: int, s: int) -> None:
    """Rd = LSHIFT Ra BY Rs (the form ping.asm uses): left for Rs > 0, logical right below"""
    p.e(f"R{d} = LSHIFT R{a} BY R{s};")
    if p.run:
        n = p.r[s] - (1 << 32) if p.r[s] >> 31 else p.r[s]
        x = p.r[a]
        p.setR(d, (x << n) if n >= 0 else (x >> -n))


def _clamp(p: Prog, r: int, lo: float, hi: float) -> None:
    p.fconst(12, lo)
    p.fop(r, r, "MAX", 12)
    p.fconst(12, hi)
    p.fop(r, r, "MIN", 12)


def _half16(p: Prog, d: int, base: int, idx: str) -> None:
    """Rd = the s16 (zero-extended) at BASE + 2 C[idx]: its word, the high half for an odd index"""
    p.ld(0, C[idx])
    p.lsh(1, 0, -1)
    p.lsh(1, 1, 2)
    p.iconst(12, base)
    p.iop(2, 12, "+", 1)
    p.seti(4, 2)
    p.ldi(d, 0, 4)
    p.iconst(12, 1)
    p.iop(1, 0, "AND", 12)
    p.ifz(1, "NE", lambda: p.lsh(d, d, -16))
    p.iconst(12, 0xFFFF)
    p.iop(d, d, "AND", 12)


def _choice(p: Prog, d: int, k: int) -> None:
    """Rd = min(4, trunc(clamp(DM(k, I4)) x 5))"""
    p.ldi(d, k // 4, 4)
    _clamp(p, d, 0.0, 1.0)
    p.fconst(12, 5.0)
    p.fop(d, d, "*", 12)
    p.trunc(d, d)
    p.iconst(12, 4)
    p.iop(d, d, "MIN", 12)


def _units(p: Prog, d: int, k: int, scale: float) -> None:
    """Fd = clamp(DM(k, I4) x scale, 0, 127)"""
    p.ldi(d, k // 4, 4)
    p.fconst(12, scale)
    p.fop(d, d, "*", 12)
    _clamp(p, d, 0.0, 127.0)


# -- the slot -----------------------------------------------------------------------------------
def _fresh(p: Prog, model_plus1: int) -> None:
    """the slot's words to zero, the last cutoffs to NONE, its tag and track (I2: the slot)"""
    p.ld(0, C["sp"])
    p.seti(3, 0)
    p.iconst(8, 0)
    p.loop_r(11, SLOT_WORDS, lambda: p.stpost(3, 8))
    p.fconst(8, NONE)
    p.sti(C01, 2, 8)
    p.sti(C02, 2, 8)
    p.sti(TAG, 2, model_plus1)
    p.ld(8, C["tr"])
    p.sti(TRK, 2, 8)


def _controls(p: Prog, X: M.Ctx) -> None:
    """the slot's record -> the two filters' words, kmod, dmod, the envelope's step and coef (2026-11-12: the
    records and the note cells are per voice slot, as PERC reads them; they were read at the slot's track)"""
    p.ld(0, C["s"])
    p.lsh(1, 0, 9)                               # record: RECORDS + 0x234 s
    p.lsh(2, 0, 5)
    p.iconst(8, 0)
    p.iop(8, 8, "+", 1)
    p.iop(8, 8, "+", 2)
    p.lsh(2, 0, 4)
    p.iop(8, 8, "+", 2)
    p.lsh(2, 0, 2)
    p.iop(8, 8, "+", 2)
    p.iconst(12, RECORDS)
    p.iop(8, 12, "+", 8)
    p.seti(4, 8)
    _units(p, 5, R_FREQ, 128.0)
    p.st(C["f1b"], 5)
    _units(p, 5, R_RES, 128.0)
    p.st(C["f1r"], 5)
    _choice(p, 5, R_MODE1)
    p.st(C["f1m"], 5)
    _units(p, 5, R_FRQ2, 127.0)
    p.st(C["f2b"], 5)
    _units(p, 5, R_RES2, 127.0)
    p.st(C["f2r"], 5)
    _choice(p, 5, R_MODE2)
    p.st(C["f2m"], 5)
    p.ldi(5, R_ENV // 4, 4)
    p.fconst(12, 0.5)
    p.fop(5, 5, "-", 12)
    p.fconst(12, ENV_UNITS)
    p.fop(5, 5, "*", 12)
    p.st(C["dmod"], 5)                           # (ENV - 0.5) x 6 octaves x 2, in units
    p.ldi(5, R_KEY // 4, 4)
    _clamp(p, 5, 0.0, KEY_MAX)
    p.ld(0, C["s"])                              # the slot's note, validated as PING does it
    p.lsh(1, 0, 2)
    p.iconst(12, NOTES)
    p.iop(1, 12, "+", 1)
    p.seti(1, 1)
    p.ldi(6, 0, 1)
    p.lsh(7, 6, -23)
    p.iconst(12, 0xFF)
    p.iop(7, 7, "AND", 12)

    def zero():
        p.iconst(6, 0)
    p.if_(7, "EQ", 12, zero, lambda: p.ifz(6, "LT", zero), kind="i")
    p.fconst(12, 60.0)
    p.fop(6, 6, "-", 12)
    p.fop(5, 5, "*", 6)
    p.fconst(12, UNITS_PER_SEMI)
    p.fop(5, 5, "*", 12)
    p.st(C["kmod"], 5)                           # KEY.T (note - 60), in units
    p.ldi(0, R_ATK // 4, 4)
    _clamp(p, 0, 0.0, 1.0)
    p.fconst(1, -ATK_A1)
    p.fop(0, 0, "*", 1)
    p.fconst(1, ATK_A0)
    p.fop(0, 1, "+", 0)
    FP.exp2(p)
    p.st(C["step"], 0)                           # the attack's rise a half
    p.ldi(0, R_DEC // 4, 4)
    _clamp(p, 0, 0.0, 1.0)
    p.fconst(1, -DEC_A1)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.fconst(1, -DEC_K)
    p.fop(0, 0, "*", 1)
    FP.exp2(p)
    p.st(C["coef"], 0)                           # the decay's factor a half


def _envelope(p: Prog) -> None:
    """the trig, then the level after each half (lvlA, lvlB); I2: the slot. 2026-11-12: the slot's own trig bit
    (frame +34 is per voice slot); bit `track` made a note on slot 8 restart every T9 voice's envelope (clicks)"""
    p.ld(0, TRIGW)
    p.lsh(0, 0, -16)
    p.ld(2, C["s"])
    p.iconst(1, 1)
    lshr(p, 1, 1, 2)
    p.iop(0, 0, "AND", 1)

    def trig():
        p.iconst(0, 1)
        p.sti(STG, 2, 0)
    p.ifz(0, "NE", trig)
    p.ldi(1, LVL, 2)
    p.ldi(2, STG, 2)
    p.ld(3, C["step"])
    p.ld(4, C["coef"])
    for dst in ("lvlA", "lvlB"):
        def attack():
            p.fop(1, 1, "+", 3)
            p.fconst(12, 1.0)

            def top():
                p.fpass(1, 12)
                p.iconst(2, 0)
            p.if_(1, "GE", 12, top)

        def decay():
            p.fop(1, 1, "*", 4)
        p.ifz(2, "NE", attack, decay)
        p.st(C[dst], 1)
    p.ld(0, C["sp"])
    p.seti(2, 0)
    p.sti(LVL, 2, 1)
    p.sti(STG, 2, 2)


def _cut(p: Prog, d: int, lvl: str) -> None:
    """Fd = clamp(base + kmod + dmod x lvl) (F7: base + kmod)"""
    p.ld(d, C["dmod"])
    p.ld(6, C[lvl])
    p.fop(d, d, "*", 6)
    p.fop(d, 7, "+", d)
    _clamp(p, d, 0.0, 127.0)


def _quiet(p: Prog, X: M.Ctx) -> None:
    """C["quiet"] = the OR of the filter's four state words and the slot buffer's 32 (zero bits): 0 when the
    buffer is all +0.0 and the states are zeros, so the filter's output is the same zeros and its states stay
    zeros (every model's offsets are products and sums of the input and the states). Clobbers R0, R8, R9, R11,
    R12, I3."""
    p.ld(8, X.C["zp"])
    p.seti(3, 8)
    p.iconst(9, 0)

    def word():
        p.ldpost(0, 3)
        p.iop(9, 9, "OR", 0)
    p.loop_r(11, 4, word)
    p.ld(8, C["bufb"])
    p.seti(3, 8)
    p.loop_r(11, 2 * M.N, word)
    p.st(C["quiet"], 9)


def _filter(p: Prog, X: M.Ctx) -> None:
    """one filter (its words at fp) over the slot's buffer"""
    p.ld(8, C["fp"])
    p.seti(1, 8)
    p.ldi(7, 0, 1)
    p.ld(6, C["kmod"])
    p.fop(7, 7, "+", 6)                          # base + kmod
    _cut(p, 5, "lvlA")
    p.st(C["cA"], 5)
    _cut(p, 5, "lvlB")
    p.st(C["cB"], 5)
    p.ld(8, C["fp"])
    p.seti(1, 8)
    p.ldi(0, 1, 1)
    p.st(X.C["res"], 0)
    p.ldi(0, 2, 1)
    p.st(X.C["mode"], 0)
    p.ldi(0, 3, 1)
    p.ld(8, C["sp"])
    p.iop(8, 8, "+", 0)
    p.st(X.C["zp"], 8)
    p.seti(2, 8)
    p.ldi(0, 4, 2)                               # the last cutoff
    p.ld(5, C["cB"])
    p.fconst(12, 0.0)
    p.if_(0, "LT", 12, lambda: p.fpass(0, 5))
    p.st(C["g0"], 0)
    p.sti(4, 2, 5)
    p.iconst(9, 0)                               # the states' guard: NaN or 1e4 on, all four cleared
    p.ld(8, X.C["zp"])
    p.seti(3, 8)

    def look():
        p.ldpost(0, 3)
        p.iconst(12, 0x7FFFFFFF)
        p.iop(0, 0, "AND", 12)
        p.iconst(12, 0x461C4000)
        p.if_(0, "GE", 12, lambda: p.iconst(9, 1), kind="i")
    p.loop_r(11, 4, look)

    def clear():
        p.iconst(0, 0)
        for k in range(4):
            p.sti(k, 2, 0)
    p.ifz(9, "NE", clear)
    if "SVF" in X.models:                        # the SVF ramps from the last block's cutoff
        p.ld(0, X.C["model"])
        p.iconst(1, M.SVF)

        def g0():
            p.ld(15, C["g0"])
            M.g_of(p)
            p.st(C["g0"], 15)
        p.if_(0, "EQ", 1, g0, kind="i")
    for c, g in (("cA", "gA"), ("cB", "gB")):
        p.ld(15, C[c])
        M.g_of(p)
        p.st(C[g], 15)
    p.ld(0, C["bufb"])
    p.st(X.C["buf"], 0)
    p.iconst(0, 2)
    p.st(C["hcnt"], 0)
    _quiet(p, X)

    def half():
        p.ld(0, C["g0"])
        p.st(X.C["gs"], 0)
        p.ld(0, C["gA"])
        p.st(X.C["ge"], 0)
        p.ld(0, C["quiet"])
        p.ifz(0, "NE", lambda: M.half(p, X))     # (perf, 2026-11-11) a silent input and a state of zeros stay zero: nothing to run
        p.ld(0, C["gA"])
        p.st(C["g0"], 0)
        p.ld(0, C["gB"])
        p.st(C["gA"], 0)
        p.ld(8, X.C["buf"])
        p.iconst(9, 4 * M.N)
        p.iop(8, 8, "+", 9)
        p.st(X.C["buf"], 8)
    M.mloop(p, C["hcnt"], half)
    p.ld(8, C["fp"])
    p.iconst(9, 16)
    p.iop(8, 8, "+", 9)
    p.st(C["fp"], 8)


def _admit(p: Prog, run) -> None:
    """RUN() if the pass of the slot (its cost in C["cost"], cycles) is expected to end before the guard's
    INS_DLP (its pass's deadline), or no deadline is known yet (the runner, the model); else INS_SKIPS + 1 and the slot
    left dry. (dnfw.perc.guard.ins_admit with the bound from a word.) Clobbers R8-R10 before RUN."""
    if p.run:
        run()
        return
    go = p.label("a2go")
    done = p.label("a2done")
    p.ld(10, G.INS_DLP)                          # 2026-11-11: this pass's deadline (guard.ins_start)
    p.e("R10 = PASS R10;")
    p.jump("EQ", go)
    p.e("R8 = EMUCLK;")
    p.ld(9, G.MARK0)
    p.e("R8 = R8 - R9;", "into the frame")
    p.ld(9, C["cost"])
    p.e("R8 = R8 + R9;", "and this model's bound")
    p.e("COMP(R8, R10);")
    p.jump("LE", go)
    p.ld(8, G.INS_SKIPS)
    p.iconst(9, 1)
    p.e("R8 = R8 + R9;")
    p.st(G.INS_SKIPS, 8)
    p.jump("", done)
    p.place(go)
    run()
    p.place(done)


def _is_a2(p: Prog, X: M.Ctx, sname: str, trname: str) -> None:
    """R5 = the model + 1 the slot C[sname] plays (0: none), its track in C[trname]"""
    _half16(p, 3, ROUTE, sname)
    p.st(C[trname], 3)
    p.iconst(5, 0)
    p.iconst(12, 15)

    def plays():
        _half16(p, 4, FTYPE, sname)              # 2026-11-12: the slot's own (the frame is per voice slot)
        p.iconst(12, TYPE0)
        p.iop(4, 4, "-", 12)
        for m in X.models:
            i = M.MODELS.index(m)
            p.iconst(6, i)
            p.if_(4, "EQ", 6, lambda i=i: p.iconst(5, i + 1), kind="i")
    p.if_(3, "LE", 12, plays, kind="i")


def _pick(p: Prog, X: M.Ctx) -> None:
    """C["pick"] = the slot + 1 whose filters run this block: the newest note's (a trig of its track this
    block), else the last pick while it still plays a filter machine, else the first such slot; 0: none"""
    p.iconst(0, 0)
    p.st(C["ps"], 0)
    p.st(C["first"], 0)
    p.iconst(0, 16)
    p.st(C["pcnt"], 0)

    def one():
        _is_a2(p, X, "ps", "ptr")

        def yes():
            p.ld(0, C["first"])

            def set_first():
                p.ld(8, C["ps"])
                p.iconst(9, 1)
                p.iop(8, 8, "+", 9)
                p.st(C["first"], 8)
            p.ifz(0, "EQ", set_first)
            p.ld(8, C["ps"])                     # its trig bit (frame +34, bit s: per voice slot)
            p.iconst(9, 16)
            p.iop(8, 8, "+", 9)
            p.iconst(7, 0)
            p.iop(6, 7, "-", 8)
            p.ld(0, TRIGW)
            lshr(p, 0, 0, 6)
            p.iconst(12, 1)
            p.iop(0, 0, "AND", 12)

            def newest():
                p.ld(8, C["ps"])
                p.iconst(9, 1)
                p.iop(8, 8, "+", 9)
                p.st(C["pick"], 8)
            p.ifz(0, "NE", newest)
        p.ifz(5, "NE", yes)
        p.ld(8, C["ps"])
        p.iconst(9, 1)
        p.iop(8, 8, "+", 9)
        p.st(C["ps"], 8)
    M.mloop(p, C["pcnt"], one)
    # the last pick must still play a filter machine
    p.ld(0, C["pick"])

    def check():
        p.iconst(9, 1)
        p.iop(0, 0, "-", 9)
        p.st(C["ps"], 0)
        _is_a2(p, X, "ps", "ptr")
        p.ifz(5, "EQ", lambda: (p.iconst(0, 0), p.st(C["pick"], 0)))
    p.ifz(0, "NE", check)
    p.ld(0, C["pick"])
    p.ifz(0, "EQ", lambda: (p.ld(8, C["first"]), p.st(C["pick"], 8)))


def _slot(p: Prog, X: M.Ctx) -> None:
    p.ld(0, C["s"])
    p.lsh(1, 0, 6)
    p.iconst(12, STATE)
    p.iop(1, 12, "+", 1)
    p.st(C["sp"], 1)
    _half16(p, 3, ROUTE, "s")
    p.st(C["tr"], 3)
    p.iconst(5, 0)                               # the model + 1; 0: none
    p.iconst(12, 15)

    def plays():
        _half16(p, 4, FTYPE, "s")                # 2026-11-12: the slot's own (the frame is per voice slot)
        p.iconst(12, TYPE0)
        p.iop(4, 4, "-", 12)                     # the model
        for m in X.models:
            i = M.MODELS.index(m)
            p.iconst(6, i)
            p.if_(4, "EQ", 6, lambda i=i: p.iconst(5, i + 1), kind="i")
    p.if_(3, "LE", 12, plays, kind="i")
    p.ld(0, C["sp"])
    p.seti(2, 0)

    def off():
        p.iconst(0, 0)
        p.sti(TAG, 2, 0)

    def on():
        p.st(C["ok"], 5)
        p.ldi(6, TAG, 2)
        p.ldi(7, TRK, 2)
        p.ld(8, C["tr"])
        p.iconst(9, 0)
        p.if_(6, "NE", 5, lambda: p.iconst(9, 1), kind="i")
        p.if_(7, "NE", 8, lambda: p.iconst(9, 1), kind="i")
        p.ifz(9, "NE", lambda: _fresh(p, 5))

        def work():
            p.ld(8, C["ok"])
            p.iconst(12, -1)
            p.iop(8, 8, "+", 12)
            p.st(X.C["model"], 8)
            _controls(p, X)
            p.ld(0, C["sp"])
            p.seti(2, 0)
            _envelope(p)
            p.ld(0, C["s"])
            p.lsh(1, 0, 2)
            p.iconst(12, BUFFERS)
            p.iop(1, 12, "+", 1)
            p.seti(1, 1)
            p.ldi(0, 0, 1)
            p.st(C["bufb"], 0)
            p.iconst(0, C["f1b"])
            p.st(C["fp"], 0)
            p.iconst(0, 2)
            p.st(C["fcnt"], 0)
            M.mloop(p, C["fcnt"], lambda: _filter(p, X))
            p.ld(8, C["nfil"])                   # voices filtered, cumulative (the diagnostic page)
            p.iconst(9, 1)
            p.iop(8, 8, "+", 9)
            p.st(C["nfil"], 8)

        def dry():
            p.ld(8, C["ndry"])
            p.iconst(9, 1)
            p.iop(8, 8, "+", 9)
            p.st(C["ndry"], 8)

        def admitted():
            p.ld(8, C["ok"])
            for m in X.models:
                i = M.MODELS.index(m)
                p.iconst(9, i + 1)
                p.if_(8, "EQ", 9, lambda m=m: (p.iconst(10, COST_BY_MODEL[m] if ADMIT[m] else 0), p.st(C["cost"], 10)), kind="i")
            _admit(p, work)
        if ONE_VOICE:
            p.ld(8, C["s"])
            p.iconst(9, 1)
            p.iop(8, 8, "+", 9)
            p.ld(7, C["pick"])
            p.if_(8, "EQ", 7, admitted, dry, kind="i")
        else:
            admitted()
    p.ifz(5, "EQ", off, on)


def body(p: Prog, X: M.Ctx) -> None:
    if not X.models:                             # dnfw.builder: no model, no pass
        return
    p.iconst(0, 0)                               # the filters' state offsets (constant words)
    p.st(C["f1z"], 0)
    p.iconst(0, 4 * Z2)
    p.st(C["f2z"], 0)
    p.iconst(0, 0)
    p.st(C["s"], 0)
    p.iconst(0, 16)
    p.st(C["cnt"], 0)
    G.ins_start(p, 0)                            # 2026-11-10: this pass's time apart (the guard's INS_ACC), out of the stock's tail
    if ONE_VOICE:
        _pick(p, X)
    p.iconst(0, 0)
    p.st(C["s"], 0)
    p.iconst(0, 16)
    p.st(C["cnt"], 0)

    def each():
        _slot(p, X)                              # (a slot's filters run only when picked and expected to end before the frame's deadline)
        p.ld(8, C["s"])
        p.iconst(9, 1)
        p.iop(8, 8, "+", 9)
        p.st(C["s"], 8)
    M.mloop(p, C["cnt"], each)


def program(next_sw: int, models=None, prefix: str = "a2f") -> str:
    """the SHARC source: wr_a2f, then JUMP NEXT_SW (PING's wr_ping)"""
    X = ctx(models)
    p = Prog("emit", prefix=prefix)
    p.raw("// a2f.asm -- ANALOG 2's filters as filter machines (dnfw.a2f). GENERATED from")
    p.raw("// dnfw.a2f.program; do not edit by hand.")
    p.raw("")
    p.raw(".SECTION/PM seg_pmco;")
    p.raw("")
    p.raw(".GLOBAL wr_a2f.;")
    p.raw("wr_a2f.:")
    body(p, X)
    if X.models:
        G.ins_end(p)
    p.jump_abs("", next_sw, "ping.asm's wr_ping (it returns to the stock chain)")
    p.emit_subs()
    p.raw(".wr_a2f..end:")
    p.raw("      .type wr_a2f.,STT_FUNC;")
    return p.text()


def run(mem: Mem, models=None) -> Prog:
    p = Prog("run", mem=mem)
    body(p, ctx(models))
    return p


def sw(load: int = LOAD) -> int:
    return 0xB80000 + (load - 0x20000000) // 2
