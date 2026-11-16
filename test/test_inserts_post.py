"""The stereo inserts after the pan (docs/inserts.md "After the pan"): the DSL program's model
against dnfw.inserts.postref, bit for bit, with voices moving between tracks; slots whose track asks
for no post insert untouched; every register back as it came. The SHARC runner's inspost step holds
the assembled code to the same reference."""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.inserts import design as D
from dnfw.inserts import post as P
from dnfw.inserts import postref as R
from dnfw.perc.dsl import Mem


def fbits(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def expand(par: bytes, par2: bytes | None = None) -> bytes:
    """slot 1's 16 records (and slot 2's) -> the 32 records (track t's slot j at 8 (2 t + j))"""
    out = bytearray(8 * D.RECORDS)
    for j, src in enumerate((par, par2 or bytes(128))):
        for t in range(D.TRACKS):
            out[8 * (2 * t + j):8 * (2 * t + j) + 8] = src[8 * t:8 * t + 8]
    return bytes(out)


def call(m: Mem, par: bytes, left, right, route, regs=None, par2=None):
    for k, v in enumerate(expand(par, par2)):              # the pre pass's unpacked table
        m.put(D.TABLE + 4 * k, v)
    for k, v in enumerate(D.flags(expand(par, par2))):     # and its flags (perf, 2026-11-10)
        m.put(D.FLAGS + 4 * k, v)
    for k in range(8):
        m.put(D.ROUTE + 4 * k, (route[2 * k] & 0xFFFF) | (route[2 * k + 1] & 0xFFFF) << 16)
    for s in range(D.TRACKS):
        for j in range(D.BLOCK):
            m.put(D.STEREO + D.STEREO_STRIDE * s + 4 * j, fbits(left[s][j]))
            m.put(D.STEREO + D.STEREO_STRIDE * s + D.STEREO_R + 4 * j, fbits(right[s][j]))
    p = P.model(m, regs)
    lo = [[m.get(D.STEREO + D.STEREO_STRIDE * s + 4 * j) for j in range(D.BLOCK)] for s in range(D.TRACKS)]
    ro = [[m.get(D.STEREO + D.STEREO_STRIDE * s + D.STEREO_R + 4 * j) for j in range(D.BLOCK)]
          for s in range(D.TRACKS)]
    return lo, ro, p


def rows_at(b):
    rows = bytearray(128)
    rows[0:8] = bytes([D.WIDE, 127, 100, 60, 40, 80, 0, 0])                 # track 1
    rows[8:16] = bytes([D.CHOR, 90, 80, 50, 60, 127, 100, 60])               # track 2: four voices
    rows[32:40] = bytes([D.CHOR, 127, 127, 127, 0, 0, 0, 127])               # track 5: one voice
    rows[120:128] = bytes([D.WIDE, 64, 0, 127, 127, 0, 0, 0])                # track 16
    rows[24:32] = bytes([D.FUZZ, 127, 127, 127, 127, 127, 127, 127])         # a pre insert: not here
    if b >= 40:
        rows[8:16] = bytes([D.CHOR, 127, 30, 127, 20, 40, 0, 127])            # knobs moved: two voices
    if b >= 60:
        rows[0:8] = bytes([D.CHOR, 127, 60, 60, 60, 127, 64, 90])             # track 1: WIDE -> CHOR
    return bytes(rows)


def route_at(b):
    rt = [0xFFFF] * 16
    for j, tr in enumerate((0, 1, 4, 15, 1, 3)):
        rt[(b // 7 + j) % 6] = tr
    return rt


def test_model_is_the_reference_with_voices_moving():
    rnd = random.Random(5)
    m, ref = Mem(), R.PostRef()
    regs = {k: rnd.getrandbits(32) for k in range(16)}
    changed = 0
    for b in range(90):
        par, route = rows_at(b), route_at(b)
        left = [[rnd.uniform(-0.3, 0.3) for _ in range(32)] for _ in range(16)]
        right = [[x * 0.6 + rnd.uniform(-0.05, 0.05) for x in row] for row in left]
        wl = [[np.float32(x) for x in row] for row in left]
        wr = [[np.float32(x) for x in row] for row in right]
        ref.block(expand(par), wl, wr, route)
        lo, ro, p = call(m, par, left, right, route, regs)
        assert lo == [[fbits(x) for x in row] for row in wl], f"block {b} left"
        assert ro == [[fbits(x) for x in row] for row in wr], f"block {b} right"
        assert all(p.r[k] == regs[k] for k in range(16)), f"block {b}: registers"
        for s in range(16):
            tr = route[s]
            if tr > 15 or par[8 * tr] not in D.POST:
                assert lo[s] == [fbits(np.float32(x)) for x in left[s]], f"block {b} slot {s} touched"
                assert ro[s] == [fbits(np.float32(x)) for x in right[s]], f"block {b} slot {s} touched"
        changed += sum(1 for s in range(16) for j in range(32) if lo[s][j] != fbits(np.float32(left[s][j])))
    assert changed > 3000


def test_all_off_leaves_every_slot():
    rnd = random.Random(2)
    m = Mem()
    left = [[rnd.uniform(-1, 1) for _ in range(32)] for _ in range(16)]
    right = [[rnd.uniform(-1, 1) for _ in range(32)] for _ in range(16)]
    lo, ro, _ = call(m, bytes(128), left, right, list(range(16)))
    assert lo == [[fbits(np.float32(x)) for x in r] for r in left]
    assert ro == [[fbits(np.float32(x)) for x in r] for r in right]


def test_wide_at_noon_with_no_delay_keeps_the_side_and_chor_alone_is_centred():
    """WDTH 64/127 (x ~1 side), TIME / BASS / TONE 0: the side kept, the delayed mid added at half"""
    m, ref = Mem(), R.PostRef()
    par = bytearray(128)
    par[0:8] = bytes([D.CHOR, 127, 0, 0, 0, 0, 127, 0])                      # one voice, WDTH max
    left = [[0.25] * 32 for _ in range(16)]
    right = [[0.25] * 32 for _ in range(16)]
    for _ in range(4):
        lo, ro, _ = call(m, bytes(par), left, right, list(range(16)))
    assert lo[0] == ro[0]                                                    # alone: centred


def test_two_slots_wide_into_chor():
    """track 1: WIDE in slot 1, CHOR in slot 2 (both on its voices, in that order); track 3: CHOR in slot 2
    alone; track 5: a pre insert in slot 1, WIDE in slot 2: every block as the reference"""
    rnd = random.Random(8)
    m, ref = Mem(), R.PostRef()
    p1, p2 = bytearray(128), bytearray(128)
    p1[0:8] = bytes([D.WIDE, 127, 100, 60, 40, 80, 0, 0])
    p2[0:8] = bytes([D.CHOR, 127, 60, 60, 60, 127, 64, 90])
    p2[16:24] = bytes([D.CHOR, 90, 80, 50, 60, 127, 100, 60])
    p1[32:40] = bytes([D.FUZZ, 127, 127, 127, 127, 127, 127, 127])
    p2[32:40] = bytes([D.WIDE, 64, 0, 127, 127, 0, 0, 0])
    route = [0, 2, 4, 0] + [0xFFFF] * 12
    for b in range(40):
        left = [[rnd.uniform(-0.3, 0.3) for _ in range(32)] for _ in range(16)]
        right = [[x * 0.5 for x in row] for row in left]
        wl = [[np.float32(x) for x in row] for row in left]
        wr = [[np.float32(x) for x in row] for row in right]
        ref.block(expand(bytes(p1), bytes(p2)), wl, wr, route)
        lo, ro, _ = call(m, bytes(p1), left, right, route, par2=bytes(p2))
        assert lo == [[fbits(x) for x in row] for row in wl], f"block {b} left"
        assert ro == [[fbits(x) for x in row] for row in wr], f"block {b} right"


def test_juno_model_is_the_reference_modes_and_slots():
    """JUNO (2026-11-12) on tracks 1 and 3, MODE I+II -> I -> II, MIX moved, track 3 CHOR -> JUNO, slot 2 behind a
    WIDE: every block as the reference, bit for bit"""
    rnd = random.Random(13)
    m, ref = Mem(), R.PostRef()
    route = [0, 2, 0, 4] + [0xFFFF] * 12
    for b in range(70):
        p1, p2 = bytearray(128), bytearray(128)
        p1[0:8] = bytes([D.JUNO, 127, 110 if b < 25 else 0 if b < 50 else 64, 0, 0, 0, 0, 0])
        p1[16:24] = bytes([D.CHOR, 90, 80, 50, 60, 127, 100, 60] if b < 30 else [D.JUNO, 40, 64, 0, 0, 0, 0, 0])
        p1[32:40] = bytes([D.WIDE, 127, 100, 60, 40, 80, 0, 0])
        p2[32:40] = bytes([D.JUNO, 127, 20, 0, 0, 0, 0, 0])
        left = [[rnd.uniform(-0.5, 0.5) for _ in range(32)] for _ in range(16)]
        right = [[x * 0.4 + rnd.uniform(-0.1, 0.1) for x in row] for row in left]
        wl = [[np.float32(x) for x in row] for row in left]
        wr = [[np.float32(x) for x in row] for row in right]
        ref.block(expand(bytes(p1), bytes(p2)), wl, wr, route)
        lo, ro, _ = call(m, bytes(p1), left, right, route, par2=bytes(p2))
        assert lo == [[fbits(x) for x in row] for row in wl], f"block {b} left"
        assert ro == [[fbits(x) for x in row] for row in wr], f"block {b} right"


def test_juno_reference_is_optimists_juno_chorus():
    """the reference at Optimist's own rate (design.juno_consts(44100): its very integers) against its juno_cho.h
    rendered on the host (scripts/gen_juno_golden.py): within -65 dB of the output, every case (the rest is its
    Q15 arithmetic and the triangle moved linearly across a block); L and R apart (the taps in antiphase)"""
    g, gold = _golden()
    x = (g.golden_input() / 32768.0).astype(np.float32)
    c44 = D.juno_consts(44100)
    for mode, mix in g.CASES:
        want = gold[f"m{mode}_x{mix}"] / 32768.0
        ref = R.PostRef()
        L, Rr = x.copy(), x.copy()
        p = [np.float32(mix) * np.float32(1 / 127), np.float32(43 * mode + 20) * np.float32(1 / 127)] + [np.float32(0)] * 5
        for b in range(len(x) // 32):
            ref.juno(0, p, L[32 * b:32 * b + 32], Rr[32 * b:32 * b + 32], c44)
        err = np.stack([L, Rr], 1) - want
        db = 20 * np.log10(err.std() / want.std())
        assert db < -65, (mode, mix, db)
        assert (want[:, 0] - want[:, 1]).std() > 0.01, (mode, mix)


def test_juno_at_48k_keeps_optimists_times_and_rates():
    """the 48 kHz constants hold Optimist's times and rates: the taps' centre 155 / 44.1 kHz (3.51 ms), the depths
    47 / 37.5 / 5 samples at 44.1 kHz, the triangle 0.514 / 0.843 / 7.86 Hz, the low-pass's corner"""
    import math
    c = D.JN
    assert abs((1 + c["base"]) / 48000 - 155 / 44100) < 1e-9
    for k, dep in enumerate((47.0, 37.5, 5.0)):
        assert abs(c["dep"][k] * 32768 / 48000 - dep / 44100) < 1e-9
        assert abs(c["inc"][k] * 48000 / 2 ** 32 - D.JN_INC0[k] * 44100 / 2 ** 32) < 1e-4
    fc = lambda g, fs: math.atan(g) * fs / math.pi                                   # noqa: E731
    assert abs(fc(c["g"], 48000) - fc(D.JN_LP0[0] / 32768, 44100)) < 1e-6
    assert abs(c["a2"] - c["g"] * c["a1"]) < 1e-12


def _golden():
    import importlib.util
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("gen_juno_golden", root / "scripts" / "gen_juno_golden.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g, np.load(root / "test" / "data" / "juno_cho_golden.npz")


def test_the_taps_line_is_the_arbiters_transient_l1():
    # 2026-11-12: JUNO's and CHOR's taps read a block's span from LINE, the start of the Monomachine render
    # scratch's IN (the arbiter's 512 B, dead during the post pass)
    from dnfw.waverider import dsp
    assert P.LINE == dsp.MNM_RENDER_DM == 0x2E5400
    assert 4 * P.LINE_WORDS <= 0x200


def test_a_refused_juno_stays_out_and_switches_without_a_step():
    # 2026-11-12 (the User: "juno in any insert => bad"; perc.guard.ins_gate, program.smooth in the post pass): a refused
    # JUNO stays out until it fits INS_HOLD blocks in a row, the dry while out, and the block it goes out or comes back
    # carries no step on either side (a tenth of the step it was)
    import math
    from dnfw.perc import guard as G
    route = [0] + [0xFFFF] * 15

    def play(deadline: bool):
        m, out = Mem(), []
        if deadline:
            m.put(G.INS_DLP, 100_000)
        for b in range(110):
            m.put(G.INS_TESTCLK, 99_000 if b == 20 else 0)
            p1 = bytearray(128)
            p1[0:8] = bytes([D.JUNO, 127, 110, 0, 0, 0, 0, 0])
            ph = [2 * math.pi * 220 * (32 * b + j) / D.FS for j in range(32)]
            left = [[0.0] * 32 for _ in range(16)]
            right = [[0.0] * 32 for _ in range(16)]
            left[0] = [0.3 * math.sin(x) for x in ph]
            right[0] = [0.2 * math.sin(x) for x in ph]
            lo, ro, _ = call(m, bytes(p1), left, right, route)
            out.append(([fv(w) for w in lo[0]], [fv(w) for w in ro[0]], left[0], right[0]))
        return m, out

    def fv(w):
        return np.float32(struct.unpack("<f", struct.pack("<I", w & 0xFFFFFFFF))[0])
    m, got = play(True)
    _, want = play(False)
    back = 20 + G.INS_HOLD
    assert m.get(G.INS_SKIPS) == G.INS_HOLD
    assert got[:20] == want[:20]
    for b in range(21, back):
        assert got[b][0] == [np.float32(x) for x in got[b][2]] and got[b][1] == [np.float32(x) for x in got[b][3]], b
    for b in (20, back):
        for side in (0, 1):
            first = np.float32(got[b][side + 2][0]) if b == 20 else want[b][side][0]
            raw = abs(float(first - got[b - 1][side][31]))
            jump = abs(float(got[b][side][0] - got[b - 1][side][31]))
            assert raw > 0.02 and jump < 0.1 * raw, (b, side, jump, raw)


def _fv(w):
    return np.float32(struct.unpack("<f", struct.pack("<I", w & 0xFFFFFFFF))[0])


def test_a_post_insert_that_did_not_run_starts_from_silence():
    # 2026-11-14 (the User: "Fix all, start fresh"): a voice slot's CHOR / WIDE / JUNO that stopped running (the slot
    # went to another track, or the M.SEL to OFF, every post insert OFF so the pass did not walk) and runs again
    # starts from silence: with silent input after it comes back, exact zeros (it used to replay its frozen ring,
    # peak 1.39, 131 ms). Model = reference bit for bit throughout
    for typ, knobs in ((D.CHOR, [127, 90, 80, 50, 60, 127, 100]), (D.WIDE, [127, 127, 127, 127, 127, 0, 0]),
                       (D.JUNO, [127, 127, 0, 0, 0, 0, 0])):
        rnd = random.Random(typ)
        m, ref = Mem(), R.PostRef()
        for b in range(180):
            rows = bytearray(128)
            rows[0:8] = bytes([typ] + knobs)                       # track 1's insert
            rows[40:48] = bytes([D.WIDE, 64, 0, 127, 127, 0, 0, 0])  # track 6 (keeps the pass walking)
            route = [0xFFFF] * 16
            route[3] = 5
            if not 40 <= b < 50:
                route[0] = 0                                        # voice slot 0 plays track 1 ...
            else:
                route[0] = 2                                        # ... track 3 (no insert), then back
            if 100 <= b < 110:
                rows[0:8] = bytes(8)                                # track 1's M.SEL OFF, then back
            if 160 <= b < 170:
                rows = bytearray(128)                               # every post insert OFF: no walk, then back
            loud = 1.0 if b < 40 or 55 <= b < 100 or 115 <= b < 160 else 0.0   # it plays before each time away
            left = [[rnd.uniform(-loud, loud) for _ in range(32)] for _ in range(16)]
            right = [[x * 0.6 for x in row] for row in left]
            wl = [np.array(row, np.float32) for row in left]
            wr = [np.array(row, np.float32) for row in right]
            ref.block(expand(bytes(rows)), wl, wr, route)
            lo, ro, _ = call(m, bytes(rows), left, right, route)
            assert lo == [[fbits(x) for x in row] for row in wl], (typ, b, "left")
            assert ro == [[fbits(x) for x in row] for row in wr], (typ, b, "right")
            if b in (39, 99, 159):
                assert any(lo[0]), (typ, b, "it played")
            if 50 <= b < 55 or 110 <= b < 115 or 170 <= b < 175:      # back, silent input: from silence
                assert not any(lo[0] + ro[0]), (typ, b, "an old ring came back")


def test_a_held_out_post_insert_comes_back_from_silence():
    # 2026-11-14: the guard's hold (ins_gate): a CHOR refused at block 20 stays out INS_HOLD blocks; when it comes
    # back it starts from silence (its state and ring zeros), not from its ring of block 19
    from dnfw.perc import guard as G
    route = [0] + [0xFFFF] * 15
    rnd = random.Random(3)
    m = Mem()
    m.put(G.INS_DLP, 100_000)
    back = 20 + G.INS_HOLD
    for b in range(back + 30):
        m.put(G.INS_TESTCLK, 99_000 if b == 20 else 0)
        p1 = bytearray(128)
        p1[0:8] = bytes([D.CHOR, 127, 90, 80, 50, 60, 127, 100])
        loud = 1.0 if b < 20 else 0.0
        left = [[rnd.uniform(-loud, loud) for _ in range(32)] for _ in range(16)]
        right = [list(row) for row in left]
        lo, ro, _ = call(m, bytes(p1), left, right, route)
        if b == 19:
            assert any(lo[0]), "it played"
        if b >= back:
            assert not any(lo[0] + ro[0]), (b, "the ring of block 19 came back")
    assert m.get(G.INS_SKIPS) == G.INS_HOLD
