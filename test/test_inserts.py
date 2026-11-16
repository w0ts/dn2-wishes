"""Per-track inserts (docs/inserts.md): the DSL program's model against the reference, bit for bit,
tracks with no insert untouched. The SHARC runner's inserts step holds the assembled code to the
same reference."""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.inserts import design as D
from dnfw.inserts import program as P
from dnfw.inserts import ref as R
from dnfw.perc.dsl import Mem

BUF = 0x83F00000                     # the test's track buffers (DDR, used by nothing)


def fbits(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def fval(w) -> np.float32:
    return np.float32(struct.unpack("<f", struct.pack("<I", w & 0xFFFFFFFF))[0])


def mem0() -> Mem:
    m = Mem()
    for t in range(D.TRACKS):
        m.put(D.BUFFERS + 4 * t, BUF + 0x80 * t)
    return m


_GEN = [0]


def send(m: Mem, par: bytes) -> None:
    """the ColdFire's send (ins.c ins_words): the records packed after a moved change word, only when
    they differ from the last sent (as the link sends on a change)"""
    words = D.pack(par, 0)[2:]
    if [m.get(D.PACK + 4 * k) for k in range(D.PACK_WORDS)] != words or m.get(D.GEN) == 0:
        _GEN[0] += 1
        for k, w in enumerate(D.pack(par, _GEN[0])):
            m.put(D.GEN + 4 * k, w)


def call(m: Mem, par: bytes, bufs, route=None) -> list[list[int]]:
    rt = list(range(16)) if route is None else route
    for k in range(8):
        m.put(D.ROUTE + 4 * k, (rt[2 * k] & 0xFFFF) | (rt[2 * k + 1] & 0xFFFF) << 16)
    send(m, par)
    for t in range(D.TRACKS):
        for j in range(D.BLOCK):
            m.put(BUF + 0x80 * t + 4 * j, fbits(bufs[t][j]))
    P.run(m)
    return [[m.get(BUF + 0x80 * t + 4 * j) for j in range(D.BLOCK)] for t in range(D.TRACKS)]


def par_of(rows: dict, rows2: dict | None = None) -> bytes:
    """ROWS: track -> slot 1's record; ROWS2: track -> slot 2's"""
    b = bytearray(8 * D.RECORDS)
    for j, rr in enumerate((rows, rows2 or {})):
        for t, v in rr.items():
            b[8 * (2 * t + j):8 * (2 * t + j) + 8] = bytes(v)
    return bytes(b)


def script(blocks=120, seed=3):
    rnd = random.Random(seed)
    out = []
    rows = {2: [D.FUZZ, 127, 90, 70, 20, 40, 0, 100], 5: [D.FUZZ, 64, 127, 127, 127, 0, 30, 127],
            9: [D.OFF, 127, 127, 0, 0, 0, 0, 127], 11: [D.WIDE, 127, 64, 64, 64, 64, 64, 64],
            7: [D.TAPE, 127, 80, 100, 90, 100, 60, 40], 13: [D.TAPE, 90, 20, 0, 127, 0, 127, 127],
            3: [D.FOLD, 127, 90, 40, 0, 100, 100, 0], 4: [D.FOLD, 100, 127, 127, 127, 60, 127, 0],
            6: [D.HARM, 127, 100, 60, 64, 90, 110, 0], 8: [D.CHOR, 127, 64, 64, 64, 64, 64, 64]}
    for b in range(blocks):
        if b == 40:
            rows[2] = [D.FUZZ, 100, 30, 10, 127, 127, 60, 80]   # knobs moved, the gate on
        if b == 60:
            rows[5] = [D.OFF] + rows[5][1:]                    # off ...
        if b == 70:
            rows[5] = [D.FUZZ] + rows[5][1:]                   # ... and on again: from zeros
        if b == 50:
            rows[7] = [D.TAPE, 127, 127, 127, 0, 127, 0, 0]       # TAPE's knobs moved
        if b == 80:
            rows[13] = [D.FUZZ] + rows[13][1:]                 # TAPE -> FUZZ -> TAPE: its ring cleared
        if b == 85:
            rows[13] = [D.TAPE] + rows[13][1:]
        if b == 45:
            rows[3] = [D.FOLD, 127, 30, 100, 64, 30, 90, 0]         # FOLD half triangle, half sine
            rows[6] = [D.HARM, 64, 127, 127, 0, 127, 127, 0]          # HARM odd only, open
        if b == 90:
            rows[2] = [D.FUZZ, 0, 127, 127, 127, 127, 127, 127]  # MIX 0: dry (the input clamped)
        loud = 6.0 if 20 <= b < 24 else 0.8
        bufs = [[rnd.uniform(-loud, loud) * (0.0 if 100 <= b < 110 else 1.0) for _ in range(32)]
                for _ in range(D.TRACKS)]
        out.append((par_of(rows), bufs))
    return out


def test_model_is_the_reference():
    m, r = mem0(), R.Ref()
    changed = 0
    for b, (par, bufs) in enumerate(script()):
        want = [[np.float32(x) for x in buf] for buf in bufs]
        r.block(par, want)
        got = call(m, par, bufs)
        assert got == [[fbits(x) for x in w] for w in want], f"block {b}"
        for t in (0, 9, 11, 8):                 # no insert, OFF, types not built: untouched
            assert got[t] == [fbits(np.float32(x)) for x in bufs[t]], f"block {b} track {t}"
        changed += sum(1 for t in (2, 3, 4, 5, 6, 7, 13) for j in range(32) if got[t][j] != fbits(np.float32(bufs[t][j])))
    assert changed > 3000


def test_all_off_leaves_every_buffer():
    m = mem0()
    rnd = random.Random(1)
    bufs = [[rnd.uniform(-1, 1) for _ in range(32)] for _ in range(D.TRACKS)]
    got = call(m, bytes(8 * D.RECORDS), bufs)
    assert got == [[fbits(np.float32(x)) for x in b] for b in bufs]


def test_each_voice_gets_the_insert_of_the_track_it_plays():
    """tracks 1, 2, 5, 16 (0, 1, 4, 15) each with its own insert; the voice slots playing them
    rotate every few blocks (the allocator), two slots play track 2 at once (polyphony), some play
    nothing (0xffff); every slot's output is the reference's, a slot's state never carries another
    track's (it starts again when its track changes)"""
    rnd = random.Random(9)
    rows = {0: [D.FUZZ, 127, 100, 70, 30, 40, 0, 110], 1: [D.TAPE, 127, 90, 110, 100, 110, 80, 60],
            4: [D.FOLD, 127, 100, 70, 64, 90, 110, 0], 15: [D.HARM, 127, 127, 50, 64, 100, 110, 0]}
    par = par_of(rows)
    m, r = mem0(), R.Ref()
    slots_seen = set()
    for b in range(90):
        k = b // 7
        route = [0xFFFF] * 16
        for j, tr in enumerate((0, 1, 4, 15, 1)):        # (track 2 on two voices)
            route[(3 * k + 5 * j) % 16] = tr
        bufs = [[rnd.uniform(-0.8, 0.8) for _ in range(32)] for _ in range(16)]
        want = [[np.float32(x) for x in buf] for buf in bufs]
        r.block(par, want, route)
        got = call(m, par, bufs, route)
        assert got == [[fbits(x) for x in w] for w in want], f"block {b}"
        for s_ in range(16):
            if route[s_] == 0xFFFF:                       # a voice playing nothing: untouched
                assert got[s_] == [fbits(np.float32(x)) for x in bufs[s_]]
            else:
                slots_seen.add(s_)
    assert len(slots_seen) >= 12                         # the tracks moved over most slots


def test_pack_round_trip():
    rnd = random.Random(4)
    v = [rnd.randrange(128) for _ in range(D.RECORDS * D.FIELDS)]
    w = D.pack(v, 77)
    assert len(w) == 2 + D.PACK_WORDS and w[0] == 77
    assert D.unpack(w[2:]) == v


def test_unpack_model_is_design_unpack():
    """the DSP's unpack (run in the model) gives design.unpack's table, and only on a change"""
    rnd = random.Random(5)
    m = mem0()
    v = [rnd.randrange(128) for _ in range(D.RECORDS * D.FIELDS)]
    for k, w in enumerate(D.pack(v, 9)):
        m.put(D.GEN + 4 * k, w)
    P.run(m)
    assert [m.get(D.TABLE + 4 * k) for k in range(D.RECORDS * D.FIELDS)] == v
    m.put(D.PACK, 0x7F)                          # no change word moved: the table stays
    P.run(m)
    assert [m.get(D.TABLE + 4 * k) for k in range(D.RECORDS * D.FIELDS)] == v


def test_two_slots_run_in_order():
    """slot 1 then slot 2 on the same voice (FUZZ into FOLD; TAPE into HARM), slot 2 alone (slot 1 OFF),
    slot 2 switched while slot 1 keeps its state; every block as the reference"""
    rnd = random.Random(11)
    rows = {0: [D.FUZZ, 127, 90, 70, 20, 40, 0, 100], 3: [D.TAPE, 100, 80, 100, 90, 100, 60, 40],
            6: [D.OFF, 127, 0, 0, 0, 0, 0, 0]}
    rows2 = {0: [D.FOLD, 90, 100, 60, 64, 90, 110, 0], 3: [D.HARM, 127, 100, 60, 64, 90, 110, 0],
             6: [D.FUZZ, 127, 127, 127, 0, 0, 0, 127], 9: [D.CHOR, 127, 64, 64, 64, 64, 64, 64]}
    m, r = mem0(), R.Ref()
    for b in range(60):
        if b == 30:
            rows2[0] = [D.TAPE, 127, 64, 64, 64, 64, 64, 64]
        par = par_of(rows, rows2)
        bufs = [[rnd.uniform(-0.8, 0.8) for _ in range(32)] for _ in range(16)]
        want = [[np.float32(x) for x in buf] for buf in bufs]
        r.block(par, want)
        got = call(m, par, bufs)
        assert got == [[fbits(x) for x in w] for w in want], f"block {b}"
        assert got[9] == [fbits(np.float32(x)) for x in bufs[9]]
        assert got[6] != [fbits(np.float32(x)) for x in bufs[6]]
