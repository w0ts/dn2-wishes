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


def test_auto_level_model_is_the_reference_and_holds_the_level():
    # 2026-11-12 (AUTO, design.AUTO_TYPES): DIST, FOLD, HARM with knob G on follow the dry's power times PGAIN's
    # gain; off (G 0) they are the inserts as before. The model is the reference, word for word, on and off,
    # through drive moves and a switch to on; at a steady drive the wet's level is the dry's x T within 1.5 dB
    import math
    rows = {0: [D.DIST, 127, 20, 90, 20, 64, 64, 127], 1: [D.DIST, 127, 20, 90, 20, 64, 64, 0],
            2: [D.FOLD, 127, 30, 64, 0, 100, 100, 127], 3: [D.FOLD, 127, 30, 64, 0, 100, 100, 0],
            4: [D.HARM, 127, 50, 70, 64, 80, 100, 127], 5: [D.HARM, 127, 50, 70, 64, 80, 100, 64]}
    m, r = mem0(), R.Ref()
    level = {}
    for b in range(260):
        if b == 100:                             # every drive to full
            for t in rows:
                rows[t] = rows[t][:2] + [127] + rows[t][3:]
        if b == 130:
            rows[1] = rows[1][:7] + [127]        # DIST switched to on
        ph = [2 * math.pi * 110 * (32 * b + j) / D.FS for j in range(32)]
        bufs = [[0.25 * math.sin(x) for x in ph] for _ in range(D.TRACKS)]
        par = par_of(rows)
        want = [[np.float32(x) for x in buf] for buf in bufs]
        r.block(par, want)
        got = call(m, par, bufs)
        assert got == [[fbits(x) for x in w] for w in want], f"block {b}"
        if 60 <= b < 100 or 220 <= b < 260:     # mean squares over 40 blocks (~10 cycles of 110 Hz)
            for t in rows:
                acc = level.setdefault(t, [0.0, 0.0])
                acc[b >= 220] += sum(float(x) ** 2 for x in want[t]) / (40 * 32)
    level = {t: [math.sqrt(a) / (0.25 / math.sqrt(2)) for a in v] for t, v in level.items()}
    t_of = {0: 64 / 127 * D.DS_LEV_MAX, 2: 100 / 127, 4: 100 / 127, 5: 100 / 127}
    for t in (0, 2, 4, 5):
        for lv in level[t]:
            assert abs(20 * math.log10(lv / t_of[t])) < 1.5, (t, level[t])
    assert abs(20 * math.log10(level[1][1] / t_of[0])) < 1.5      # on after the switch
    assert abs(20 * math.log10(level[3][1] / level[3][0])) > 3      # FOLD off: louder at full drive


def test_a_refused_insert_stays_out_and_switches_without_a_step():
    # 2026-11-12 (perc.guard.ins_gate, program.smooth; the unit's skips toggled inserts every block, a click each): a
    # refused instance stays out until it fits INS_HOLD blocks in a row, and the block it goes out or comes back
    # carries no step: the output's first sample is within a small fraction of the wet-dry step of the last
    import math
    from dnfw.perc import guard as G
    rows = {2: [D.FUZZ, 127, 100, 90, 0, 30, 0, 100]}
    unfit = {20, 21, 30}                         # refused at 20 and 21 (and at 30: the count starts again)

    def play(deadline: bool):
        m, out = mem0(), []
        if deadline:
            m.put(G.INS_DLP, 100_000)
        for b in range(140):
            m.put(G.INS_TESTCLK, 99_000 if b in unfit else 0)
            ph = [2 * math.pi * 220 * (32 * b + j) / D.FS for j in range(32)]
            bufs = [[0.3 * math.sin(x) for x in ph] for _ in range(D.TRACKS)]
            out.append([fval(w) for w in call(m, par_of(rows), bufs)[2]])
        return m, out
    m, got = play(True)
    _, want = play(False)
    back = 30 + G.INS_HOLD                       # fits from 31: back at 30 + 64
    assert m.get(G.INS_SKIPS) == back - 20
    assert got[:20] == want[:20]
    for b in range(21, back):                    # out: the dry
        ph = [2 * math.pi * 220 * (32 * b + j) / D.FS for j in range(32)]
        assert got[b] == [np.float32(0.3 * math.sin(x)) for x in ph], b
    for b in (20, back):                         # where it goes out and comes back: a tenth of the step it was
        dry0 = np.float32(0.3 * math.sin(2 * math.pi * 220 * 32 * b / D.FS))
        raw = abs(float((dry0 if b == 20 else want[b][0]) - got[b - 1][31]))
        jump = abs(float(got[b][0] - got[b - 1][31]))
        assert raw > 0.2 and jump < 0.1 * raw, (b, jump, raw)


def test_silent_slots_skip_their_insert_bit_identically():
    # 2026-11-12 (opt-host's measure on A09: T9 owns slots 2..15, so its DIST ran 14 times a block, sounding or not):
    # a slot whose input is all zeros and whose insert last left zeros and its state at rest skips it. Every block is
    # still the reference's, word for word; once the silent slots are at rest (DIST's gate smoothing reaches its
    # fixed point ~250 blocks into silence) the pass runs far fewer steps
    import math
    route = [0, 1] + [9] * 14
    rows = {9: [D.DIST, 127, 90, 90, 20, 64, 64, 0], 1: [D.FOLD, 127, 80, 64, 0, 100, 100, 0]}
    m, r = mem0(), R.Ref()
    steps = []
    for b in range(420):
        ph = [2 * math.pi * 110 * (32 * b + j) / D.FS for j in range(32)]
        bufs = [[-0.0 if t >= 8 else 0.0] * 32 for t in range(D.TRACKS)]   # silent slots hold -0.0s or +0.0s (the
        bufs[2] = [0.4 * math.sin(x) for x in ph]                     # runner's: -0.0s); one T9 voice sounds
        if 30 <= b < 60:
            bufs[5] = [0.2 * math.sin(3 * x) for x in ph]            # a second one, then it stops (a tail)
        want = [[np.float32(x) for x in buf] for buf in bufs]
        r.block(par_of(rows), want, route)
        for k in range(8):
            m.put(D.ROUTE + 4 * k, (route[2 * k] & 0xFFFF) | (route[2 * k + 1] & 0xFFFF) << 16)
        send(m, par_of(rows))
        for t in range(D.TRACKS):
            for j in range(D.BLOCK):
                m.put(BUF + 0x80 * t + 4 * j, fbits(bufs[t][j]))
        p = P.run(m)
        steps.append(p.steps)
        got = [[m.get(BUF + 0x80 * t + 4 * j) for j in range(D.BLOCK)] for t in range(D.TRACKS)]
        assert got == [[fbits(x) for x in w] for w in want], f"block {b}"
    assert max(steps[400:]) < 0.5 * min(steps[1:20]), (steps[1:20], steps[400:])
    assert all(m.get(D.QUIET_L2 + 4 * (2 * s)) for s in (3, 4, 8, 9, 15)), "silent slots, +0.0 and -0.0, marked"


def test_fuzz_auto_rides_in_field_0_and_holds_the_level():
    # 2026-11-13 (the User: AUTO on G for every distortion): FUZZ's AUTO is field 0's bit 4 (design.FZ_AUTO_BIT; FUZZ has
    # no instance); T is its PGAIN. The model is the reference, on and off; on, the wet's level is the dry's x PGAIN
    import math
    on, off = D.FUZZ | D.FZ_AUTO_BIT, D.FUZZ
    rows = {0: [on, 127, 20, 90, 0, 30, 0, 100], 1: [off, 127, 20, 90, 0, 30, 0, 100]}
    m, r = mem0(), R.Ref()
    acc = {0: [0.0, 0.0], 1: [0.0, 0.0]}
    for b in range(260):
        if b == 100:
            for t in rows:
                rows[t] = rows[t][:2] + [127] + rows[t][3:]          # DRIV to full
        ph = [2 * math.pi * 110 * (32 * b + j) / D.FS for j in range(32)]
        bufs = [[0.25 * math.sin(x) for x in ph] for _ in range(D.TRACKS)]
        par = par_of(rows)
        want = [[np.float32(x) for x in buf] for buf in bufs]
        r.block(par, want)
        got = call(m, par, bufs)
        assert got == [[fbits(x) for x in w] for w in want], f"block {b}"
        if 60 <= b < 100 or 220 <= b < 260:
            for t in (0, 1):
                acc[t][b >= 220] += sum(float(x) ** 2 for x in want[t]) / (40 * 32)
    lv = {t: [math.sqrt(a) / (0.25 / math.sqrt(2)) for a in v] for t, v in acc.items()}
    for x in lv[0]:
        assert abs(20 * math.log10(x / (100 / 127))) < 1.5, lv
    assert 20 * math.log10(lv[1][1]) > 6                          # off: much louder at full drive


def test_tape_pgain_and_auto():
    # 2026-11-13 (the User: PGAIN on F and AUTO on G on TAPE too): PGAIN a byte a record at design.TP_PG_DDR (7-bit two's
    # complement dB, 0 x 1.0), AUTO field 0's bit 4. The model is the reference, word for word; -6 dB is half the wet's
    # level (MIX 127); AUTO holds the wet at the dry's level x PGAIN
    import math
    pg = {0: (-6) & 0x7F, 1: 0, 2: (-6) & 0x7F}
    rows = {0: [D.TAPE, 127, 90, 0, 0, 0, 0, 0], 1: [D.TAPE, 127, 90, 0, 0, 0, 0, 0],
            2: [D.TAPE | D.FZ_AUTO_BIT, 127, 90, 0, 0, 0, 0, 0]}
    m, r = mem0(), R.Ref()
    words = [0] * D.TP_PG_WORDS
    for t, b in pg.items():
        i = 2 * t                                 # slot 1's record
        words[i // 4] |= b << (8 * (i % 4))
        r.tpg[i] = b
    for k, w in enumerate(words):
        m.put(D.TP_PG_DDR + 4 * k, w)
    acc = {t: 0.0 for t in pg}
    for b in range(200):
        ph = [2 * math.pi * 110 * (32 * b + j) / D.FS for j in range(32)]
        bufs = [[0.25 * math.sin(x) for x in ph] for _ in range(D.TRACKS)]
        par = par_of(rows)
        want = [[np.float32(x) for x in buf] for buf in bufs]
        r.block(par, want)
        got = call(m, par, bufs)
        assert got == [[fbits(x) for x in w] for w in want], f"block {b}"
        if b >= 160:
            for t in pg:
                acc[t] += sum(float(x) ** 2 for x in want[t])
    db = {t: 10 * math.log10(acc[t] / acc[1]) for t in pg}
    assert abs(db[0] + 6) < 0.3, db                        # -6 dB
    dry = 40 * 32 * 0.25 ** 2 / 2
    assert abs(10 * math.log10(acc[2] / dry) + 6) < 1.5, (db, acc[2] / dry)   # AUTO: the dry's level, -6 dB


TAPE_REC = [D.TAPE, 127, 100, 90, 64, 30, 0, 0]          # (no hiss: silence in, silence out when fresh)


def test_a_pre_insert_that_did_not_run_starts_from_silence():
    # 2026-11-14 (the User: "Fix all, start fresh"): a voice slot's TAPE that stopped running (the slot played
    # another track, its M.SEL went OFF, no BUILT record so no walk) and runs again starts from silence (its ring
    # and state zeros): silent input after the return, exact zeros. Model = reference bit for bit throughout
    rnd = random.Random(8)
    m, ref = mem0(), R.Ref()
    for b in range(180):
        rows = {0: TAPE_REC, 5: [D.FUZZ, 127, 64, 64, 64, 64, 64, 64]}     # track 6 keeps the pass walking
        route = [0xFFFF] * 16
        route[3] = 5
        route[0] = 2 if 40 <= b < 50 else 0                 # voice slot 0: track 1, track 3 (none), track 1
        if 100 <= b < 110:
            rows[0] = [0] * 8                               # track 1's M.SEL OFF, then back
        if 160 <= b < 170:
            rows = {}                                       # nothing BUILT: no walk, then back
        loud = 1.0 if b < 40 or 55 <= b < 100 or 115 <= b < 160 else 0.0
        bufs = [[rnd.uniform(-loud, loud) for _ in range(32)] for _ in range(16)]
        want = [np.array(row, np.float32) for row in bufs]
        par = par_of(rows)
        ref.block(par, want, route)
        got = call(m, par, bufs, route)
        assert got == [[fbits(x) for x in row] for row in want], b
        if b in (39, 99, 159):
            assert got[0] != [fbits(np.float32(x)) for x in bufs[0]], (b, "it played")
        if 50 <= b < 55 or 110 <= b < 115 or 170 <= b < 175:
            assert not any(got[0]), (b, "an old ring came back")


def test_a_held_out_pre_insert_comes_back_from_silence():
    # 2026-11-14: a TAPE refused at block 20 stays out INS_HOLD blocks; it comes back from silence, not from its
    # state and ring of block 19
    from dnfw.perc import guard as G
    rnd = random.Random(9)
    m = mem0()
    m.put(G.INS_DLP, 100_000)
    back = 20 + G.INS_HOLD
    for b in range(back + 20):
        m.put(G.INS_TESTCLK, 99_000 if b == 20 else 0)
        loud = 1.0 if b < 20 else 0.0
        bufs = [[rnd.uniform(-loud, loud) for _ in range(32)] for _ in range(16)]
        got = call(m, par_of({0: TAPE_REC}), bufs)
        if b >= back:
            assert not any(got[0]), (b, "the state of block 19 came back")
    assert m.get(G.INS_SKIPS) == G.INS_HOLD
