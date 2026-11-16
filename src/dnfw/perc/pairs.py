"""SIMD voice pairs (2026-11-12; the User: "the most useful use case is clearly the voices of one track"): when a
voice of a pairable machine renders, a later voice of the same machine whose block needs nothing new (its partner) is
rendered with it, so the two can run as one SIMD pair (PEx the first, PEy the partner: docs/dsp-simd.md); at its own
turn the partner skips its stream move and its render (done) and the rest of its block runs as always.

Build option DN2_PAIRS (machine names, comma separated, e.g. "TB303"): without it nothing here is emitted and the
program is the one before. Each voice's output and state are the same with pairs on and off: the partner's render is
the one its own turn would run (nothing it reads can change before then: `_clean`), only earlier.

The partner (`_clean`): its slot plays the same machine; it has no trig (the frame's bit, the slot's waiting trig),
no dirty words, no machine change; its frame words and note cell are those of its last render (the snapshot, SNAP),
so its block's host would not change a word the render reads; its stream asks for a block (pos >= START); it is not
resting (quiet, the rest counter); it is later in this block's ORDER (not yet run) and not already a partner; and on
the DSP, the time left holds its expected cost. At its turn the guard admits it (its render is done and paid for).

Memory (L1 F4, 0x2E2500..0x2E3000: the arbiter's claim): STAMP, a word the program moves on each block, and the
other words of the search; SNAP, SNAP_STRIDE words a slot.
Slot word PRE_W (255, free after dnfw.mnm.core's VW): STAMP when the slot's render was done ahead this block.

Step A (this module's first state): the pair is rendered as the two voices' renders one after the other (scalar),
which proves the host's part bit for bit with no engine change; an engine's SIMD pair render replaces it (RENDER2).
"""

from __future__ import annotations

import os

from ..md import core as K
from . import machines as M

NAMES = tuple(x for x in os.environ.get("DN2_PAIRS", "").replace(" ", "").split(",") if x)
PRE_W = 255
assert PRE_W >= K.MD_WORDS - 1 and PRE_W < K.MD_WORDS
WORDS_OFF = 0x2E2500                            # L1 F4 (the arbiter juno-engine, 2026-11-12: 0x2E2500..0x2E3000, the
                                                # stock track buffers' padding): our words, then SNAP
(STAMP, PART, J, AM, SAVE_I4, SAVE_MDB, U, LC, AT, PASSW, OWNW, RENDERW, LC2) = (WORDS_OFF + 4 * k for k in range(13))
T0 = WORDS_OFF + 0x38                           # EMUCLK as the partner's move and render began
DBG = WORDS_OFF + 0x34                          # DN2_PAIRS_DEBUG: how far the partner checks got (max, this block)
DEBUG = os.environ.get("DN2_PAIRS_DEBUG", "") not in ("", "0")
SNAP_OFF = WORDS_OFF + 0x40                     # SNAP_STRIDE words a slot
SNAP_STRIDE = 16
SHIFT = SNAP_OFF + 16 * SNAP_STRIDE * 4         # 16 words: cycles to move between the slots' measured costs (shift)
BYTES = SHIFT + 16 * 4 - WORDS_OFF              # (of the arbiter's F4, 0x2E2500..0x2E3000)
assert WORDS_OFF + BYTES <= 0x2E3000
# the frame's 16-bit records the host reads for a voice (perc.program.voice): the words that cover them
_SLOTS = sorted({M.TYPE_REC[1]} | {s for _r, s, _l, _t in M.PARAMS} | {s for _r, s, _l, _t in M.FX_PARAMS}
                | {s for _r, s, _l, _t in M.P3_RECS})
SPAN_LO = M.frame_offset(_SLOTS[0])
SPAN_HI = M.frame_offset(_SLOTS[-1]) + 2
SPAN_W = (SPAN_HI - SPAN_LO + 2 + 3) // 4 + 1    # words from the aligned start, for either alignment of 146 t
SNAP_W = SPAN_W + 2                              # and the header's type word, the note cell
assert SNAP_W <= 16
RENDER2: dict[int, object] = {}                 # machine index -> its SIMD pair render (step B)


def enabled() -> bool:
    return bool(NAMES)


def machines() -> list[int]:
    """the voice machine indices (dnfw.md.voice.ALL) of the pairable machines"""
    from ..md import voice as MDV
    return [k for k, Mx in enumerate(MDV.ALL) if Mx.NAME in NAMES]


# -- the code ----------------------------------------------------------------------------------------------

def _w(L, off: int) -> int:
    """the address of our word OFF (an absolute L1 address since the arbiter's F4)"""
    return off


def tick(p, L) -> None:
    """after the slot loop: the next block's stamp. A block's mark is STAMP + 1 (_mark): never 0 (a cleared slot's
    PRE_W) until STAMP wraps, and the same from PERC's entry on (the model starts there)"""
    if not enabled():
        return
    p.ld(0, _w(L, STAMP))
    p.iconst(12, 1)
    p.iop(0, 12, "+", 0)
    p.st(_w(L, STAMP), 0)


def _mark(p, L, d: int) -> None:
    """Rd = this block's mark (STAMP + 1). Clobbers R12."""
    p.ld(d, _w(L, STAMP))
    p.iconst(12, 1)
    p.iop(d, 12, "+", d)


def unskip(p, L, mskip: int) -> None:
    """a voice whose render was done ahead is not left out by the Monomachine budget (its state moved on)"""
    if not enabled():
        return
    p.ldi(0, PRE_W, 3)
    _mark(p, L, 1)
    p.if_(0, "EQ", 1, lambda: (p.iconst(0, 0), p.st(mskip, 0)), kind="i")


def admit(p, L, t_word: int, ok: str) -> None:
    """the guard: jump to OK if this slot's render was done ahead this block (its cost is paid). Clobbers R11-R13,
    I1."""
    if not enabled():
        return
    p.ld(12, t_word)
    p.lsh(12, 12, 10)
    p.iconst(13, L.state + 4 * PRE_W)
    p.iop(12, 13, "+", 12)
    p.seti(1, 12)
    p.ldi(13, 0, 1)
    _mark(p, L, 11)
    p.e("COMP(R13, R11);")
    p.jump("EQ", ok)


def skip_move(p, L, move) -> None:
    """advance's stream move, unless this slot's was done ahead this block"""
    if not enabled():
        move()
        return
    p.ldi(0, PRE_W, 3)
    _mark(p, L, 1)
    p.if_(0, "NE", 1, move, kind="i")


def _slot(p, L, word: int, i: int = 1) -> None:
    """Ii = the slot (unbiased) whose index is in WORD. Clobbers R9, R12, R13."""
    p.ld(9, word)
    p.lsh(12, 9, 10)
    p.iconst(13, L.state)
    p.iop(12, 13, "+", 12)
    p.seti(i, 12)


def _ptrs(p, L, word: int) -> None:
    """for the slot in WORD: I1 = its frame words (from the word holding its first record read), I2 = its
    snapshot, R4 its header's type word, R5 its note cell. Clobbers R0, R9, R10, R12, R13."""
    from . import program as P
    p.ld(9, word)
    P.t146(p, 10, 9)
    p.iconst(12, M.FRAME + SPAN_LO)
    p.iop(0, 12, "+", 10)
    p.iconst(12, -4)
    p.iop(0, 0, "AND", 12)
    p.seti(1, 0)
    p.lsh(0, 9, 1)
    p.iconst(12, M.FRAME + 148)
    p.iop(4, 12, "+", 0)
    p.iconst(12, -4)
    p.iop(4, 4, "AND", 12)
    p.lsh(0, 9, 2)
    p.iconst(12, P.NOTE_CELLS)
    p.iop(5, 12, "+", 0)
    p.lsh(0, 9, 6)
    assert SNAP_STRIDE == 16
    p.iconst(12, _w(L, SNAP_OFF))
    p.iop(0, 12, "+", 0)
    p.seti(2, 0)


def _save(p, L, word: int) -> None:
    """the slot's snapshot: its frame words and note cell now"""
    _ptrs(p, L, word)
    for _ in range(SPAN_W):
        p.ldpost(6, 1)
        p.stpost(2, 6)
    for r in (4, 5):
        p.seti(1, r)
        p.ldi(6, 0, 1)
        p.stpost(2, 6)


def _same(p, L, word: int) -> None:
    """R7 = 0 if the slot's frame words and note cell are its snapshot's. Clobbers R0, R4-R13, I1, I2."""
    _ptrs(p, L, word)
    p.iconst(7, 0)
    for _ in range(SPAN_W):
        p.ldpost(6, 1)
        p.ldpost(8, 2)
        p.iop(6, 6, "-", 8)
        p.iop(7, 7, "OR", 6)
    for r in (4, 5):
        p.seti(1, r)
        p.ldi(6, 0, 1)
        p.ldpost(8, 2)
        p.iop(6, 6, "-", 8)
        p.iop(7, 7, "OR", 6)


def _find(p, L) -> None:
    """PART = the first slot after this one in ORDER that can render with it (_clean), else -1"""
    from . import program as P
    from . import guard as G
    from ..md import voice as MDV
    p.iconst(0, -1)
    p.st(_w(L, PART), 0)
    p.iconst(0, 0)
    p.st(_w(L, J), 0)

    def chain(checks, k=0):
        if DEBUG:
            p.ld(0, DBG)
            p.iconst(12, k + 1)
            p.iop(0, 0, "MAX", 12)
            p.st(DBG, 0)
        if k == len(checks):
            p.ld(0, _w(L, U))
            p.st(_w(L, PART), 0)
            return
        checks[k](lambda: chain(checks, k + 1))

    def same_machine(then):
        _slot(p, L, _w(L, U))
        p.ldi(0, K.VW["mach"], 1)
        p.ld(1, _w(L, AM))
        p.if_(0, "EQ", 1, then, kind="i")

    def not_self(then):                          # (ORDER is a permutation on the DSP; the model's may not be)
        p.ld(0, _w(L, U))
        p.ld(1, _w(L, AT))
        p.if_(0, "NE", 1, then, kind="i")

    def not_ahead(then):
        p.ldi(0, PRE_W, 1)
        _mark(p, L, 1)
        p.if_(0, "NE", 1, then, kind="i")

    def flags(then):                             # (I1: the slot still)
        def dirty():
            p.ldi(0, K.VW["dirty"], 1)

            def quiet():
                p.ldi(0, K.VW["quiet"], 1)
                p.iconst(12, MDV.QUIET_BLOCKS)

                def due():
                    p.ldi(0, K.VW["pos"], 1)
                    p.fconst(12, MDV.START)
                    p.if_(0, "GE", 12, then)
                p.if_(0, "LT", 12, due, kind="i")
            p.ifz(0, "EQ", quiet)
        p.ldi(0, K.VW["trg"], 1)
        p.ifz(0, "EQ", dirty)

    def no_trig(then):
        p.ld(0, P.TRIG_WORD)
        p.lsh(0, 0, -16)
        p.iconst(1, 1)
        p.ld(9, _w(L, U))
        P._shift_by(p, 1, 9)
        p.iop(0, 0, "AND", 1)
        p.ifz(0, "EQ", then)

    def not_resting(then):
        p.ld(9, _w(L, U))
        p.lsh(12, 9, 2)
        p.iconst(13, L.mnm.scratch + P.RESTS_OFF)
        p.iop(12, 13, "+", 12)
        p.seti(1, 12)
        p.ldi(0, 0, 1)
        p.iconst(12, P.MNM_QUIET_BLOCKS)
        p.if_(0, "LT", 12, then, kind="i")

    def unchanged(then):
        _same(p, L, _w(L, U))
        p.ifz(7, "EQ", then)

    def in_time(then):                           # (the DSP: the model has no clock)
        if p.run:
            then()
            return
        p.e("R8 = EMUCLK;")
        p.ld(9, G.MARK0)
        p.e("R8 = R8 - R9;")
        for w in (_w(L, U), _w(L, AT)):          # its expected cost and this voice's, as the guard reckons them
            p.ld(9, w)
            p.lsh(9, 9, 2)
            p.iconst(10, G.COST_PERC)
            p.iop(9, 10, "+", 9)
            p.seti(1, 9)
            p.ldi(9, 0, 1)
            p.lsh(10, 9, -1)
            p.iop(9, 9, "+", 10)
            p.iconst(10, G.FLOOR)
            p.iop(9, 9, "MAX", 10)                 # as the guard expects it: 1.5 x, at least FLOOR
            p.iop(8, 8, "+", 9)
        p.ld(10, G.LIMIT_PERC)                   # (v0.52 merge: PERC's limit after v0.49's sample share)
        p.if_(8, "LE", 10, then, kind="i")

    checks = [not_self, same_machine, not_ahead, flags, no_trig, not_resting, unchanged, in_time]

    def body():
        p.ld(0, _w(L, J))
        p.ld(1, L.mnm.scratch + P.PERC_I)
        p.ld(2, _w(L, PART))

        def later():
            def none_yet():
                p.ld(0, _w(L, J))
                p.lsh(12, 0, 2)
                p.iconst(13, P.ORDER)
                p.iop(12, 13, "+", 12)
                p.seti(1, 12)
                p.ldi(0, 0, 1)
                p.st(_w(L, U), 0)
                chain(checks)
            p.ifz(2, "LT", none_yet)
        p.if_(0, "GT", 1, later, kind="i")
        p.ld(0, _w(L, J))
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
        p.st(_w(L, J), 0)
    p.loop(_w(L, LC), 16, body)


def _to(p, L, word: int) -> None:
    """the voice's slot words (C['mdb'], I3 with its bias) at the slot in WORD (an index) or at the address in
    WORD (SAVE_MDB)"""
    from . import program as P
    if word == _w(L, SAVE_MDB):
        p.ld(12, word)
    else:
        p.ld(9, word)
        p.lsh(12, 9, 10)
        p.iconst(13, L.state)
        p.iop(12, 13, "+", 12)
    p.st(L.C["mdb"], 12)
    p.iconst(13, 4 * P.I3_BIAS)
    p.iop(12, 13, "+", 12)
    p.seti(3, 12, bias=P.I3_BIAS)


def render(p, L, each) -> None:
    """dnfw.md.voice's render (EACH: the dispatch, emitted once here): this voice's, unless done ahead this
    block; for a pairable machine with a partner (_find), the partner's first (its stream moved on, its PRE_W
    set), then this voice's (step A: one after the other, the same dispatch; RENDER2 later)"""
    if not enabled():
        each()
        return
    from ..md import voice as MDV
    p.iconst(0, -1)
    p.st(_w(L, PART), 0)
    p.iconst(0, 0)
    p.st(_w(L, OWNW), 0)

    def own():
        p.iconst(0, 1)
        p.st(_w(L, OWNW), 0)
        K.vw(p, 0, "mach")
        p.st(_w(L, AM), 0)
        p.iconst(2, 0)
        for k in machines():
            p.iconst(12, k)
            p.if_(0, "EQ", 12, lambda: p.iconst(2, 1), kind="i")

        def pairable():
            p.ld(0, L.C["mdb"])
            p.iconst(12, -L.state)
            p.iop(0, 12, "+", 0)
            p.lsh(0, 0, -10)
            p.st(_w(L, AT), 0)
            _save(p, L, _w(L, AT))
            _find(p, L)
        p.ifz(2, "NE", pairable)
    p.ldi(0, PRE_W, 3)
    _mark(p, L, 1)
    p.if_(0, "NE", 1, own, kind="i")

    def first():                                 # the partner's render, if any
        p.iconst(0, 0)
        p.st(_w(L, RENDERW), 0)

        def partner():
            if not p.run:
                p.e("R8 = EMUCLK;")
                p.st(T0, 8)
            p.geti(0, 4)
            p.st(_w(L, SAVE_I4), 0)
            p.ld(0, L.C["mdb"])
            p.st(_w(L, SAVE_MDB), 0)
            _to(p, L, _w(L, PART))
            MDV._move(p, L)
            p.iconst(0, 1)
            p.st(_w(L, RENDERW), 0)
        p.ld(0, _w(L, OWNW))
        p.ld(1, _w(L, PART))
        p.ifz(0, "NE", lambda: p.ifz(1, "GE", partner))

    def second():                                # this voice's
        p.ld(0, _w(L, OWNW))
        p.st(_w(L, RENDERW), 0)

        def back():
            if not p.run:                        # the partner's move and render: off this voice's cost, onto its
                p.e("R8 = EMUCLK;")
                p.ld(9, T0)
                p.e("R8 = R8 - R9;")
                for w, op in ((AT, "-"), (PART, "+")):
                    p.ld(9, w)
                    p.lsh(9, 9, 2)
                    p.iconst(10, SHIFT)
                    p.iop(9, 10, "+", 9)
                    p.seti(1, 9)
                    p.ldi(10, 0, 1)
                    p.e(f"R10 = R10 {op} R8;")
                    p.sti(0, 1, 10)
            _mark(p, L, 1)
            p.sti(PRE_W, 3, 1)
            _to(p, L, _w(L, SAVE_MDB))
            p.ld(0, _w(L, SAVE_I4))
            p.seti(4, 0)
        p.ld(1, _w(L, PART))
        p.ifz(0, "NE", lambda: p.ifz(1, "GE", back))

    p.iconst(0, 0)
    p.st(_w(L, PASSW), 0)

    def pass_():
        p.ld(0, _w(L, PASSW))
        p.ifz(0, "EQ", first, second)
        p.ld(0, _w(L, PASSW))
        p.iconst(12, 1)
        p.iop(0, 12, "+", 0)
        p.st(_w(L, PASSW), 0)
        p.ld(0, _w(L, RENDERW))
        p.ifz(0, "NE", each)
    p.loop(_w(L, LC2), 2, pass_)


def shift(p, t_word: int) -> None:
    """the guard, as it stores a voice's measured cost (R8): R8 += the slot's SHIFT (a pair's partner render moved
    from the voice that ran it to the partner), and SHIFT cleared, so each slot's cost word is its own voice's.
    Clobbers R9, R10, I1."""
    if not enabled():
        return
    p.ld(9, t_word)
    p.lsh(9, 9, 2)
    p.iconst(10, SHIFT)
    p.iop(9, 10, "+", 9)
    p.seti(1, 9)
    p.ldi(9, 0, 1)
    p.iop(8, 8, "+", 9)
    p.iconst(9, 0)
    p.sti(0, 1, 9)
