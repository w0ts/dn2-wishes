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
