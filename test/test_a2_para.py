"""PARA as one voice (dnfw.engines.analog2.para, 2026-11-16, the User: "one bigger voice") in the model (the program
the SHARC runs): the chord on ONE slot, its joined notes in the ColdFire's row (csrc/para/one.c, here written into the
rows, since 2026-11-17 in the voice's own frame words as csrc/para/one.c pv_out writes them), each rendered from a pool block (a shadow) inside the leader's voice.

- A chord is its notes' post-drive halves (oscillators, noise, drive per note), added at full level to the leader's
  after its drive, then the leader's filter and knee: bit for bit against that sum made from today's own pieces (the
  engine with its shared stage taken out on each joined note, run alone at the leader's pitch plus its offset, its
  halves added to an unchanged leader's).
- PARA off, and a chord of one, play as today, bit for bit; no shadow, no role.
- A dropped place fades out over FADE_HALVES halves and its block is freed; a new note on the slot (a new chord)
  frees the old chord's blocks and waits for a new row (the row still showing the old chord is not taken again).
- More places than the pool holds: the rest are left out (LOST), nothing else changes.
- The first block after a DSP load zeroes the rows (DDR keeps an earlier boot's).
"""

from __future__ import annotations

import pathlib

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

ROOT = pathlib.Path(__file__).resolve().parent.parent

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
        h.words[A2.tables_at() + 4 * k] = bits(v)
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


def block(h, slots, notes, on=0, off=0, skip=(), closed=()):
    """one block: notes[u] in slot u's cell, ON / OFF the note-on and note-off masks -> ({u: 32 floats}, roles).
    SKIP: slots the frame guard refuses this block (not run; their buffer stays zero, as the guard's). CLOSED: slots
    whose DN2 AMP (the track chain's, after PERC) has closed: their buffer, which the next block's quiet test reads as
    "the block the chain left", is silence (2026-11-18)"""
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
    out = {u: [h.mem.get(BUFS + 0x100 * u + 4 * k) for k in range(32)] for u in slots}
    for u in closed:
        for k in range(32):
            h.mem.put(BUFS + 0x100 * u + 4 * k, bits(0.0))
    return out, roles


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



def write_row(h, s, places, seq=1, live=True, lead_note=60):
    """slot S's row (one.h): PLACES {k: (offset, sounding, place seq)} (k 0 the leader's own note)"""
    hw = [0] * (2 * PARA.row_words())
    hw[0] = (0x8000 if live else 0) | (seq << 8) | (lead_note & 0x7F)
    for k, (off, sounding, q) in places.items():
        hw[1 + k] = (off & 0xFF) | 0x100 | (PARA.P_SOUND if sounding else 0) | PARA.P_USED | (q << 12)
    t = h.t                                  # (2026-11-17) in the voice's own frame words, as csrc/para/one.c pv_out
    h.t = s
    for i, x in enumerate(hw):
        h._half(PM.frame_offset(PARA.ROW_SLOT + i), x)
    h.t = t


def ready(h):
    """the DSP has run since its load (its first block zeroed the rows, the pool free): the ColdFire's rows come after"""
    h.mem.put(PARA.INIT, 1)
    h.mem.put(PARA.FREE, (1 << PARA.POOL_N) - 1)


CHORD = {0: (0, True, 1), 1: (4, True, 1), 2: (7, True, 1), 3: (11, True, 1)}   # 60: +4 +7 +11
LEAD = 3


def chord_run(engine, blocks, rows=None, para=3, extra=()):
    """slot LEAD on ENGINE, note 60 on at block 0; ROWS {block: places} written before that block's pass ->
    [({u: 32 words}, roles)]"""
    slots = [LEAD, *extra]
    h = setup(slots, para=para, engine=engine)
    ready(h)
    out = []
    for b in range(blocks):
        if rows and b in rows:
            write_row(h, LEAD, rows[b])
        out.append(block(h, slots, {u: 60.0 for u in slots}, on=(1 << LEAD) if b == 0 else 0))
    return h, out


@pytest.mark.parametrize("engine", ENGINES)
def test_a_chord_on_one_slot_is_its_notes_halves_under_the_leaders_filter(engine):
    h, out = chord_run(engine, 24, rows={0: CHORD})
    assert role_of(out[0][1][LEAD]) == PARA.LEADER
    want = reference({LEAD: 60.0, 10: 64.0, 11: 67.0, 12: 71.0}, LEAD, [10, 11, 12], len(out), engine)
    assert [o[LEAD] for o, _r in out] == want
    assert max(abs(flt(w)) for o, _r in out for w in o[LEAD]) > 0.5
    assert h.mem.get(PARA.FREE) == (1 << PARA.POOL_N) - 1 - 0b111 and h.mem.get(PARA.LOST) == 0


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("late", [1, 3])
def test_the_chords_row_after_the_note_on_still_makes_the_chord(engine, late):
    # 2026-11-17 (v0.57.1 on the unit: only the chord's lowest note sounded): the TDM link brought the chord's row a
    # period or more after the leader's note-on frame, so at the note-on the slot's row showed no chord, its chord word
    # was zeroed and it was never looked at again. The row now rides in the voice's own frame (the same frame as the
    # note-on); should it ever come later, the slot stays watched until it does
    h, out = chord_run(engine, late + 8, rows={late: CHORD})
    assert role_of(out[late][1][LEAD]) == PARA.LEADER
    assert h.mem.get(PARA.FREE) == (1 << PARA.POOL_N) - 1 - 0b111 and h.mem.get(PARA.LOST) == 0


def test_the_row_is_read_from_the_voices_own_frame_words():
    # 2026-11-17 (the User: one voice, its pitches with it): the pass copies a looked-at slot's frame words ROW_SLOT..+11
    # into its row; none of our machines reads those frame slots (FM TONE's)
    used = {PM.TYPE_REC[1], PM.VEL_SLOT} | {x[1] for x in PM.PARAMS + PM.FX_PARAMS + PM.P3_RECS}
    assert not used & set(range(PARA.ROW_SLOT, PARA.ROW_SLOT + 2 * PARA.row_words()))
    one = (ROOT / "csrc/para/one.c").read_text()
    assert "#define PV_ROW_SLOT 50u" in one and PARA.ROW_SLOT == 50
    assert "pv_out(OUT);" in (ROOT / "csrc/slides/slide.c").read_text()
    assert "pv_row" not in (ROOT / "csrc/sampler/link.c").read_text()


@pytest.mark.parametrize("engine", ENGINES)
def test_para_off_and_a_chord_of_one_play_as_today(engine):
    _h, on = chord_run(engine, 16, rows={0: {0: (0, True, 1)}})
    _h, off = chord_run(engine, 16, para=0)
    _h, bare = chord_run(engine, 16)
    for (x, rx), (y, ry), (z, _rz) in zip(on, off, bare):
        assert x[LEAD] == y[LEAD] == z[LEAD] and role_of(rx[LEAD]) == 0 and role_of(ry[LEAD]) == 0


@pytest.mark.parametrize("engine", ENGINES)
def test_a_dropped_place_fades_out_and_frees_its_block(engine):
    dropped = dict(CHORD)
    dropped[1] = (4, False, 1)
    h, out = chord_run(engine, 30, rows={0: CHORD, 12: dropped})
    assert h.mem.get(PARA.FREE) == (1 << PARA.POOL_N) - 1 - 0b110        # block 0 (place 1) back
    x = [flt(w) for o, _r in out[8:20] for w in o[LEAD]]
    steady = [flt(w) for o, _r in out[4:12] for w in o[LEAD]]
    jump = max(abs(x[k] - x[k - 1]) for k in range(1, len(x)))
    assert jump <= 1.5 * max(abs(steady[k] - steady[k - 1]) for k in range(1, len(steady)))


@pytest.mark.parametrize("engine", ENGINES)
def test_the_leaders_own_note_dropped_fades_and_the_chord_plays_on(engine):
    own_out = dict(CHORD)
    own_out[0] = (0, False, 1)
    h, out = chord_run(engine, 30, rows={0: CHORD, 12: own_out})
    r = out[-1][1][LEAD]
    assert role_of(r) == PARA.LEADER and (r >> PARA.FADE_SHIFT) & 7 == PARA.FADE_OUT
    assert max(abs(flt(w)) for w in out[-1][0][LEAD]) > 0.05


@pytest.mark.parametrize("engine", ENGINES)
def test_a_new_note_on_the_slot_waits_for_a_new_chord(engine):
    slots = [LEAD]
    h = setup(slots, para=3, engine=engine)
    ready(h)
    write_row(h, LEAD, CHORD)
    for b in range(12):
        block(h, slots, {LEAD: 60.0}, on=(1 << LEAD) if b == 0 else 0)
    o, r = block(h, slots, {LEAD: 62.0}, on=1 << LEAD)                  # a new note: the row still the old chord
    for b in range(10):                                                   # its shadows fade out and go
        o, r = block(h, slots, {LEAD: 62.0})
    assert h.mem.get(PARA.FREE) == (1 << PARA.POOL_N) - 1 and role_of(r[LEAD]) == 0
    write_row(h, LEAD, {0: (0, True, 2), 1: (3, True, 2)}, seq=2)        # the new chord's row
    o, r = block(h, slots, {LEAD: 62.0})
    assert role_of(r[LEAD]) == PARA.LEADER and h.mem.get(PARA.FREE) == (1 << PARA.POOL_N) - 2


@pytest.mark.parametrize("engine", ENGINES)
def test_more_places_than_the_pool_are_left_out(engine):
    slots = [1, 2, 3]
    h = setup(slots, para=3, engine=engine)
    ready(h)
    full = {k: (k, True, 1) for k in range(PARA.PLACES)}
    for s in slots:
        write_row(h, s, full)
    for b in range(6):
        o, r = block(h, slots, {s: 50.0 + s for s in slots}, on=0b1110 if b == 0 else 0)
    assert h.mem.get(PARA.FREE) == 0 and h.mem.get(PARA.LOST) > 0
    # the slots in order: slot 1 takes 9 blocks, slot 2 the other 7, slot 3 none (it plays its own note alone)
    assert [role_of(r[s]) for s in slots] == [PARA.LEADER, PARA.LEADER, 0]
    assert all(abs(flt(w)) < 8.0 for s in slots for w in o[s])


@pytest.mark.parametrize("engine", ENGINES)
def test_chord_after_chord_each_released_to_rest_renders_every_member(engine):
    """2026-11-18 (v0.59.2 on the unit: chords played fewer notes than the keys held; every member joined and held on
    the ColdFire, the slot's DSP cost the same for 1 and 5 notes): 24 chords of 3..6 notes, each on the next of 8
    slots as stock's allocator hands them out, each held, let go (the frame's note-off), its DN2 AMP closed, the voice
    left to rest (MNM_QUIET_BLOCKS of silence: no render at all), then its row ended by the ColdFire (csrc/para/one.c:
    once the DSP reports the slot quiet). Every chord's every joined note has a shadow while held, none is LOST, and
    the pool is whole between chords. Until the fix a shadow's fade moved on only in its leader's render: a resting
    leader never moved it, so its block stayed taken until that slot's next note, and the pool ran dry"""
    slots = list(range(8))
    h = setup(slots, para=3, engine=engine)
    ready(h)
    full = (1 << PARA.POOL_N) - 1
    lost0 = h.mem.get(PARA.LOST)
    notes = {u: 60.0 for u in slots}
    seen = []
    for i in range(24):
        u, n, seq = i % 8, 3 + i % 4, 1 + (i // 8) % 15                 # 3, 4, 5, 6 notes; a new seq on the slot
        rests = h.L.md.mnm.scratch + PP.RESTS_OFF + 4 * u
        write_row(h, u, {k: (2 * k + i % 3, True, seq) for k in range(n)}, seq=seq)
        others = [x for x in slots if x != u]
        for b in range(8):
            block(h, slots, notes, on=(1 << u) if b == 0 else 0, closed=others)
        own = h.mem.get(PARA.OWN + 4 * u)
        block(h, slots, notes, off=1 << u, closed=slots)                  # let go; the AMP closes
        quiet = 0
        while h.mem.get(rests) < PP.MNM_QUIET_BLOCKS + 2 and quiet < 4 * PP.MNM_QUIET_BLOCKS:
            block(h, slots, notes, closed=slots)
            quiet += 1
        write_row(h, u, {}, live=False)                                   # the ColdFire ends the chord: its row zero
        for _ in range(12):
            block(h, slots, notes, closed=slots)
        seen.append((u, n, bin(own).count("1"), h.mem.get(rests), h.mem.get(PARA.FREE)))
    assert all(r >= PP.MNM_QUIET_BLOCKS for *_x, r, _f in seen), f"the voice rests between chords: {seen}"
    assert all(o == n - 1 for _u, n, o, _r, _f in seen), f"every member a shadow (slot, notes, shadows, rests, free): {seen}"
    assert all(f == full for *_x, f in seen) and h.mem.get(PARA.LOST) == lost0, f"the pool whole: {seen}"


def test_the_first_block_zeroes_the_rows():
    h = setup([LEAD], para=3)
    for j in range(16 * PARA.row_words()):
        h.mem.put(PARA.rows() + 4 * j, 0xDEADBEEF)
    block(h, [LEAD], {LEAD: 60.0})
    assert all(h.mem.get(PARA.rows() + 4 * j) == 0 for j in range(16 * PARA.row_words()))
    assert h.mem.get(PARA.FREE) == (1 << PARA.POOL_N) - 1


@pytest.mark.parametrize("name", ["ROLE", "CSEQ", "OWN", "RROLE", "INIT", "FREE", "LOST", "SH_N", "SH_NOTE", "WATCH"])
def test_the_words_fit_the_area(name):
    at = getattr(PARA, name)
    assert PARA.AREA <= at < PARA.AREA + 4 * PARA.WORDS
    assert PARA.WATCH + 4 == PARA.AREA + 4 * PARA.WORDS
