"""2026-11-15 (main: "inserts running on members' silent slots can cost more than PARA saves"): a PARA chord's MEMBER
and DROPPED slots (dnfw.engines.analog2.para ROLE) play their track's voice inserts as OFF, in the pre pass
(dnfw.inserts.program) and the post pass (dnfw.inserts.post): the models against the references with those slots
taken off their track (route past 15: not run, and from silence when they run again), bit for bit; the leader's
output is the reference's with every slot on its track (unchanged); the passes' instructions drop. The SHARC
runner's step para holds the assembled code to the same."""

from __future__ import annotations

import random

from dnfw.engines.analog2 import para as PARA
from dnfw.inserts import design as D
from dnfw.inserts import postref as PR
from dnfw.inserts import ref as R
from dnfw.perc.dsl import Mem

from . import test_inserts as TI
from . import test_inserts_post as TP

TRACK = 2
CHORD = (0, 1, 2, 3)                             # slots on TRACK: 3 leads, 0 and 1 members, 2 dropped
LEADER_SLOT = 3


def role_words(b: int) -> list[int]:
    """the ROLE words at block B: the chord from block 4 to 40, then slot 1 leaves it (plays alone), the chord ends at
    60 (every slot plays as itself again)"""
    words = [0] * 16
    if 4 <= b < 60:
        members = (0, 1) if b < 40 else (0,)
        words[LEADER_SLOT] = PARA.LEADER << PARA.ROLE_SHIFT | sum(1 << m for m in members)
        for m in members:
            words[m] = PARA.MEMBER << PARA.ROLE_SHIFT | LEADER_SLOT << PARA.LEAD_SHIFT | PARA.RENDERED
        words[2] = PARA.DROPPED << PARA.ROLE_SHIFT | LEADER_SLOT << PARA.LEAD_SHIFT
    return words


def put_roles(m: Mem, words: list[int]) -> None:
    for u, w in enumerate(words):
        m.put(PARA.ROLE + 4 * u, w)


def route() -> list[int]:
    rt = [0xFFFF] * 16
    for s in CHORD + (4,):                       # slot 4: the same track, no role (a voice of its own)
        rt[s] = TRACK
    rt[5] = 7
    return rt


def masked(rt: list[int], words: list[int]) -> list[int]:
    """the route with MEMBER and DROPPED slots off their track: the reference plays them as no insert"""
    return [0xFFFF if (words[s] >> PARA.ROLE_SHIFT) & 3 in (PARA.MEMBER, PARA.DROPPED) else rt[s] for s in range(16)]


def noise(rnd: random.Random) -> list[list[float]]:
    """every slot sounds (a member's real buffer is silence; any input shows its insert did not run)"""
    return [[rnd.uniform(-0.8, 0.8) for _ in range(D.BLOCK)] for _ in range(D.TRACKS)]


def test_pre_inserts_skip_a_chords_members_and_dropped_slots():
    rnd = random.Random(5)
    par = TI.par_of({TRACK: [D.FUZZ, 127, 90, 70, 20, 40, 0, 100], 7: [D.FOLD, 127, 90, 40, 0, 100, 100, 0]},
                    {TRACK: [D.TAPE, 127, 80, 100, 90, 100, 60, 40]})
    m, ref, whole = TI.mem0(), R.Ref(), R.Ref()
    rt = route()
    for b in range(80):
        words = role_words(b)
        put_roles(m, words)
        bufs = noise(rnd)
        want = [list(map(TI.fval, map(TI.fbits, row))) for row in bufs]
        full = [list(row) for row in want]
        ref.block(par, want, masked(rt, words))
        whole.block(par, full, rt)
        got = TI.call(m, par, bufs, rt)
        assert got == [[TI.fbits(x) for x in row] for row in want], b
        assert got[LEADER_SLOT] == [TI.fbits(x) for x in full[LEADER_SLOT]], b      # the leader's: unchanged
        for s in range(16):
            if masked(rt, words)[s] != rt[s]:
                assert got[s] == [TI.fbits(TI.fval(TI.fbits(x))) for x in bufs[s]], (b, s)   # untouched
    assert ref.last[2 * 1] != (0, 0)             # slot 1 ran again after leaving the chord (from silence)


def test_pre_pass_costs_less_with_a_chord():
    """the same blocks with and without the chord's ROLE words: the pass's model instructions drop by the members' and
    the dropped slot's inserts"""
    par = TI.par_of({TRACK: [D.FUZZ, 127, 90, 70, 20, 40, 0, 100]})
    rt = route()
    cost = {}
    for name, words in (("voices", [0] * 16), ("chord", role_words(10))):
        rnd = random.Random(9)
        m = TI.mem0()
        put_roles(m, words)
        n = 0
        for _ in range(8):
            bufs = noise(rnd)
            for k in range(8):
                m.put(D.ROUTE + 4 * k, (rt[2 * k] & 0xFFFF) | (rt[2 * k + 1] & 0xFFFF) << 16)
            TI.send(m, par)
            for t in range(D.TRACKS):
                for j in range(D.BLOCK):
                    m.put(TI.BUF + 0x80 * t + 4 * j, TI.fbits(bufs[t][j]))
            n += TI.P.run(m).steps
        cost[name] = n // 8
    one = (cost["voices"] - cost["chord"]) / 3
    assert cost["chord"] < cost["voices"] and one > 1000, cost


def test_post_inserts_skip_a_chords_members_and_dropped_slots():
    rnd = random.Random(11)
    rows = bytearray(128)
    rows[8 * TRACK:8 * TRACK + 8] = bytes([D.CHOR, 90, 80, 50, 60, 127, 100, 60])
    rows[8 * 7:8 * 7 + 8] = bytes([D.WIDE, 127, 100, 60, 40, 80, 0, 0])
    par = bytes(rows)
    m, ref, whole = Mem(), PR.PostRef(), PR.PostRef()
    rt = route()
    for b in range(80):
        words = role_words(b)
        put_roles(m, words)
        left, right = noise(rnd), noise(rnd)
        lw = [list(map(TI.fval, map(TI.fbits, row))) for row in left]
        rw = [list(map(TI.fval, map(TI.fbits, row))) for row in right]
        lf, rf = [list(r) for r in lw], [list(r) for r in rw]
        ref.block(TP.expand(par), lw, rw, masked(rt, words))
        whole.block(TP.expand(par), lf, rf, rt)
        lo, ro, _p = TP.call(m, par, left, right, rt)
        assert lo == [[TI.fbits(x) for x in row] for row in lw], b
        assert ro == [[TI.fbits(x) for x in row] for row in rw], b
        assert lo[LEADER_SLOT] == [TI.fbits(x) for x in lf[LEADER_SLOT]], b
        assert ro[LEADER_SLOT] == [TI.fbits(x) for x in rf[LEADER_SLOT]], b


def test_a_slot_with_no_role_or_leading_is_unchanged():
    """the ROLE word's role bits 0 (no chord) and LEADER run the insert; only MEMBER and DROPPED do not"""
    assert PARA.MEMBER & 1 and PARA.DROPPED & 1
    assert not PARA.LEADER & 1
