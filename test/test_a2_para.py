"""ANALOG 2's PARA (dnfw.engines.analog2.para) in the model (the program the SHARC runs): several voice slots in one
memory, run as the DSP runs them each block (mnm_ages, the PARA pass, each slot newest first).

- A chord is its members' post-drive halves (oscillators, noise, drive per note: the User's "per note, before the
  sum"), added at full level to the leader's after its drive, one member at a time in slot order, then the leader's
  filter and knee: bit for bit against that sum made from today's own pieces (the engine with its filter and knee
  taken out on the members, their halves added to an unchanged leader's).
- Members and dropped notes play exact silence; PARA off, and a chord of one, play as today, bit for bit.
- A member the frame guard refused this block is left out of the leader's sum (its words are an earlier pass).
- The chords' rules: a note joins its track's chord while one of the chord's notes is held, else starts one; the
  oldest N play (N the PARA value + 1), the rest are dropped; a chord releasing keeps its leader while a new chord
  starts on the track; a leader's slot taken by another note hands the chord to its oldest member.
"""

from __future__ import annotations

import pytest

from dnfw.engines.analog2 import analog2 as A2
from dnfw.engines.analog2 import para as PARA
from dnfw.engines.juno import juno as J
from dnfw.md import core as MDK
from dnfw.md import voice as MDV
from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.perc import machines as PM
from dnfw.perc import program as PP
from dnfw.perc.dsl import Prog, bits, flt

# the engines PARA plays (para.ENGINES), each with its per-note step (the last before the shared stage) and its shared
# stage's steps (taken out on a member in the reference): ANALOG 2 drive | filter, out; JUNO DCO | ladder, post
ENGINE = {"ANALOG2": (A2, "_drive", ("_filter", "_out")), "JUNO": (J, "_osc", ("_ladder", "_post"))}
ENGINES = tuple(ENGINE)
assert ENGINES == PARA.ENGINES


def _type(engine):
    return next(t for t, k in PP.MNM_TYPES.items() if MM.NAMES[k] == engine)
BUFS = 0x00310000                       # slot u's 48 kHz buffer at BUFS + 0x100 u (the harness memory)
CHORD4 = {0: 60.0, 1: 64.0, 2: 67.0, 3: 71.0}


def _route(h, u, track):
    a = MDV.ROUTE + 4 * (u >> 1)
    w = h.mem.get(a)
    h.mem.put(a, (w & 0xFFFF) | (track << 16) if u & 1 else (w & 0xFFFF0000) | track)


def setup(slots, para, knobs=None, page2=None, track=0, engine="ANALOG2"):
    h = PL.Harness()
    h.words[h.L.md.C["fill"]] = MDK.Z_N
    for k, v in enumerate(A2.table_words()):
        h.words[h.L.md.mnm.scratch + A2.TABLES_OFF + 4 * k] = bits(v)
    for u in slots:
        h.t = u
        mod = ENGINE[engine][0]
        h.set_mnm(_type(engine), list(knobs or mod.DEFAULTS))
        for (_r, slot, lo, top), x in zip(PM.FX_PARAMS, page2 or mod.DEFAULTS2):
            h._half(PM.frame_offset(slot), PL.knob_word(x, top, lo))
        h._half(PM.frame_offset(PARA.PARA_REC[1]), para << 8)
        _route(h, u, track)
    h.t = 0
    return h


def block(h, slots, notes, on=0, off=0, skip=()):
    """one block: notes[u] in slot u's cell, ON / OFF the note-on and note-off masks -> ({u: 32 floats}, roles).
    SKIP: slots the frame guard refuses this block (not run; their buffer stays zero, as the guard's)"""
    L = h.L
    for u in slots:
        h.mem.put(PP.NOTE_CELLS + 4 * u, bits(notes[u]))
        h.mem.put(PP.BUFFERS + 4 * u, BUFS + 0x100 * u)
        if u in skip:                    # the guard zeroes a refused voice's buffer; any other keeps its last
            for k in range(32):          # block (a voice writes its whole block): the quiet test reads it, as on the DSP
                h.mem.put(BUFS + 0x100 * u + 4 * k, bits(0.0))
    h.mem.put(PP.TRIG_WORD, (h.mem.get(PP.TRIG_WORD) & 0xFFFF) | (on << 16))
    w = h.mem.get(PM.FRAME + PARA.NOTE_OFF)
    h.mem.put(PM.FRAME + PARA.NOTE_OFF, (w & 0xFFFF0000) | off)
    h.mem.put(L.C["mcost"], 0)
    p = Prog("run", mem=h.mem)
    p.spill = L.md.C["ash"]
    PP.mnm_ages(p, L)
    PP.para_prepass(p, L)
    for u in [h.mem.get(L.md.mnm.scratch + PP.ORDER_OFF + 4 * k) for k in range(16)]:
        if u in slots and u not in skip:
            PP.run_voice(L, None, u, mem=h.mem)
    roles = {u: h.mem.get(PARA.ROLE + 4 * u) for u in slots}
    return {u: [h.mem.get(BUFS + 0x100 * u + 4 * k) for k in range(32)] for u in slots}, roles


def role_of(r):
    return r >> PARA.ROLE_SHIFT


def reference(notes, lead, members, blocks, engine="ANALOG2"):
    """the chord from today's pieces: each member's engine with its shared stage taken out, its per-note halves
    (after its per-note step) captured in order; the leader's engine, unchanged but for that step, adding them one
    member at a time"""
    mod, per_note, shared = ENGINE[engine]
    orig = {n: getattr(mod, n) for n in (per_note,) + shared}
    cap, ptr = 0x00F00000, 0x00EFFFFC
    caps_at = {u: 0x00F10000 + 0x1000 * k for k, u in enumerate(members)}

    def harness():
        return setup([0], 0, engine=engine)

    def copy_out(p, L):
        orig[per_note](p, L)
        p.ld(8, L.W[A2.WN["bv"]])
        p.seti(0, 8)
        p.ld(8, ptr)
        p.seti(1, 8)
        p.loop_r(11, A2.M.N, lambda: (p.ldpost(1, 0), p.stpost(1, 1)))
        p.geti(8, 1)
        p.st(ptr, 8)

    def add_in(p, L):
        orig[per_note](p, L)
        for u in members:
            p.ld(8, L.W[A2.WN["bv"]])
            p.seti(0, 8)
            p.ld(8, caps_at[u] - 4)
            p.seti(1, 8)

            def one():
                p.ldi(1, 0, 0)
                p.ldpost(2, 1)
                p.fop(1, 1, "+", 2)
                p.stpost(0, 1)
            p.loop_r(11, A2.M.N, one)
            p.geti(8, 1)
            p.st(caps_at[u] - 4, 8)

    def patch(per, nothing):
        setattr(mod, per_note, per)
        for n in shared:
            setattr(mod, n, (lambda p, L, *a, **k: None) if nothing else orig[n])
    hs = {u: harness() for u in [lead] + members}
    out = []
    try:
        for b in range(blocks):
            for u in members:
                patch(copy_out, True)
                hs[u].mem.put(ptr, cap)
                hs[u].block(note=notes[u], trig=b == 0)
                n = (hs[u].mem.get(ptr) - cap) // 4
                hs[lead].mem.put(caps_at[u] - 4, caps_at[u])
                for k in range(n):
                    hs[lead].mem.put(caps_at[u] + 4 * k, hs[u].mem.get(cap + 4 * k))
            patch(add_in, False)
            out.append([bits(x) for x in hs[lead].block(note=notes[lead], trig=b == 0)])
    finally:
        for n, f in orig.items():
            setattr(mod, n, f)
    return out


@pytest.mark.parametrize("engine", ENGINES)
def test_a_chord_is_its_members_post_drive_halves_under_the_leaders_filter(engine):
    slots = [0, 1, 2, 3]
    h = setup(slots, para=3, engine=engine)
    outs = [block(h, slots, CHORD4, on=0xF if b == 0 else 0) for b in range(24)]
    assert {u: role_of(r) for u, r in outs[0][1].items()} == {0: PARA.MEMBER, 1: PARA.MEMBER, 2: PARA.MEMBER,
                                                               3: PARA.LEADER}
    assert outs[0][1][3] & 0xFFFF == 0b0111
    for o, _r in outs:
        assert all(o[u] == [0] * 32 for u in (0, 1, 2))                   # members: exact zeros
    want = reference(CHORD4, 3, [0, 1, 2], len(outs), engine)
    assert [o[3] for o, _r in outs] == want
    assert max(abs(flt(w)) for o, _r in outs for w in o[3]) > 0.5


@pytest.mark.parametrize("engine", ENGINES)
def test_para_off_and_a_chord_of_one_play_as_today(engine):
    slots = [0, 1, 2]
    notes = {0: 48.0, 1: 55.0, 2: 62.0}
    off = setup(slots, para=0, engine=engine)
    alone = {u: setup(slots, para=0, engine=engine) for u in slots}
    for b in range(16):
        o, roles = block(off, slots, notes, on=0b111 if b == 0 else 0)
        assert not any(roles.values())
        for u in slots:                                                     # each slot as if it played alone
            a, _ = block(alone[u], slots, notes, on=(1 << u) if b == 0 else 0)
            assert o[u] == a[u]
    one_on, one_off = setup([2], para=3, engine=engine), setup([2], para=0, engine=engine)
    for b in range(16):
        x, r = block(one_on, [2], notes, on=0b100 if b == 0 else 0)
        y, _ = block(one_off, [2], notes, on=0b100 if b == 0 else 0)
        assert x == y and r[2] == 0                                         # a chord of one: no role, today's


@pytest.mark.parametrize("engine", ENGINES)
def test_the_oldest_n_play_and_the_rest_are_dropped(engine):
    slots = [0, 1, 2]
    notes = {0: 48.0, 1: 55.0, 2: 62.0}
    h = setup(slots, para=1, engine=engine)                                                # 2 pitches
    outs = [block(h, slots, notes, on=0b111 if b == 0 else 0) for b in range(16)]
    r = outs[0][1]
    assert role_of(r[2]) == PARA.LEADER and r[2] & 0xFFFF == 0b010          # the highest leads, the next joins
    assert role_of(r[1]) == PARA.MEMBER and role_of(r[0]) == PARA.DROPPED
    assert all(o[0] == [0] * 32 and o[1] == [0] * 32 for o, _r in outs)
    assert [o[2] for o, _r in outs] == reference(notes, 2, [1], len(outs), engine)


@pytest.mark.parametrize("engine", ENGINES)
def test_a_releasing_chord_keeps_its_leader_while_a_new_one_starts(engine):
    slots = [0, 1, 2]
    notes = {0: 48.0, 1: 55.0, 2: 62.0}
    h = setup(slots, para=3, engine=engine)
    for b in range(6):
        _o, r = block(h, slots, notes, on=0b011 if b == 0 else 0)
    assert role_of(r[1]) == PARA.LEADER and r[1] & 0xFFFF == 0b001
    _o, r = block(h, slots, notes, off=0b011)                              # both released
    o, r = block(h, slots, notes, on=0b100)                                # a new note: a new chord
    assert role_of(r[1]) == PARA.LEADER and r[1] & 0xFFFF == 0b001         # the old one releases on
    assert r[2] == 0                                                        # the new one, a chord of one
    assert h.mem.get(PARA.CUR) == 3                                         # track 0's chord: slot 2 + 1
    o, r = block(h, slots, notes, on=0b001)                                # slot 0 taken by a new note: it joins
    assert r[1] == 0 and role_of(r[2]) == PARA.LEADER and r[2] & 0xFFFF == 0b001


@pytest.mark.parametrize("engine", ENGINES)
def test_a_taken_leader_hands_its_chord_to_its_oldest_member(engine):
    slots = [0, 1, 2]
    notes = {0: 48.0, 1: 55.0, 2: 62.0}
    h = setup(slots, para=3, engine=engine)
    for b in range(4):
        _o, r = block(h, slots, notes, on=0b111 if b == 0 else 0)
    assert role_of(r[2]) == PARA.LEADER and r[2] & 0xFFFF == 0b011
    _route(h, 2, 5)                                                         # slot 2's next note: another track
    _o, r = block(h, slots, notes, on=0b100)
    assert role_of(r[1]) == PARA.LEADER and r[1] & 0xFFFF == 0b001         # slot 1 (the older key) leads on
    assert role_of(r[0]) == PARA.MEMBER and r[2] == 0
    assert h.mem.get(PARA.CUR) == 2 and h.mem.get(PARA.CUR + 4 * 5) == 3


@pytest.mark.parametrize("engine", ENGINES)
def test_a_member_the_guard_refused_is_left_out_of_its_chord(engine):
    """the frame guard refuses a member (or it rests): its stream words hold an earlier pass, so the leader must not
    add them. The leader's block is the same whatever those words hold, and differs from the whole chord's"""
    slots = [0, 1, 2, 3]
    runs = {k: setup(slots, para=3, engine=engine) for k in ("whole", "stale", "junk")}
    for b in range(6):
        for h in runs.values():
            o, r = block(h, slots, CHORD4, on=0xF if b == 0 else 0)
    assert all(r[u] & PARA.RENDERED for u in (0, 1, 2)) and not r[3] & PARA.RENDERED
    junk = runs["junk"]
    for k in range(256):                                                    # member 1's words: junk
        junk.mem.put(junk.L.md.state + 1024 + 4 * k, bits(1000.0))
    whole, _ = block(runs["whole"], slots, CHORD4)
    stale, rs = block(runs["stale"], slots, CHORD4, skip=(1,))
    bad, rj = block(junk, slots, CHORD4, skip=(1,))
    assert not rs[1] & PARA.RENDERED and rs[0] & PARA.RENDERED and rs[2] & PARA.RENDERED
    assert stale[3] == bad[3]                                               # nothing of member 1's words added
    assert stale[3] != whole[3]                                             # (and member 1 was in the chord)
    assert stale[1] == [0] * 32 and max(abs(flt(w)) for w in stale[3]) > 0.01


@pytest.mark.parametrize("engine", ENGINES)
def test_a_held_chord_keeps_its_members_past_the_quiet_test(engine):
    """a member writes silence to its own buffer; mnm_ages' quiet test (QUIET_BLOCKS of silence, no note: rest) must
    not rest it while its chord sounds: it takes its leader's count"""
    slots = [0, 1, 2, 3]
    h = setup(slots, para=3, engine=engine)
    n = PP.MNM_QUIET_BLOCKS + 16
    outs = [block(h, slots, CHORD4, on=0xF if b == 0 else 0) for b in range(n)]
    last, roles = outs[-1]
    assert all(roles[u] & PARA.RENDERED for u in (0, 1, 2))
    assert all(h.mem.get(h.L.md.mnm.scratch + PP.RESTS_OFF + 4 * u) < PP.MNM_QUIET_BLOCKS for u in slots)
    assert max(abs(flt(w)) for w in last[3]) > 0.1


@pytest.mark.parametrize("name", ["HELD", "CUR", "MEM", "ROLE"])
def test_the_words_fit_the_area(name):
    at = getattr(PARA, name)
    assert PARA.AREA <= at < PARA.AREA + 4 * PARA.WORDS
    assert PARA.ROLE + 64 == PARA.AREA + 4 * PARA.WORDS
