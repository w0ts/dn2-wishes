"""FDN8 (docs/fdn8.md): the DSL program's model against the reference, bit for bit, and the
design's numbers. The SHARC runner's fdn8 step holds the assembled code to the same reference."""

from __future__ import annotations

import random
import struct

import numpy as np

from dnfw.fdn8 import design as D
from dnfw.fdn8 import program as P
from dnfw.fdn8 import ref as R
from dnfw.perc.dsl import Mem

PAR, IO = 0x257918, 0x257E6C
BUF = 0x83F00000
INL, INR, OUTL, OUTR, PAIRI, PAIRO = (BUF + k * 0x100 for k in range(6))


def fbits(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def mem0() -> Mem:
    m = Mem()
    st = P.state_bytes()
    for k in range(0, len(st), 4):
        m.put(P.STATE + k, struct.unpack_from("<I", st, k)[0])
    for a, v in ((IO, 32), (IO + 4, PAIRI), (IO + 12, PAIRO), (PAIRI, INL), (PAIRI + 4, INR),
                 (PAIRO, OUTL), (PAIRO + 4, OUTR)):
        m.put(a, v)
    return m


def call(m: Mem, type_word: int, inl, inr, par):
    m.put(P.TYPE_WORD, type_word)
    for k in range(32):
        m.put(INL + 4 * k, fbits(inl[k]))
        m.put(INR + 4 * k, fbits(inr[k]))
        m.put(OUTL + 4 * k, 0x7FC00001)             # a marker: every word must be written
        m.put(OUTR + 4 * k, 0x7FC00001)
    for k, x in enumerate(par):
        m.put(PAR + 4 * k, fbits(x))
    m.put(P.C["went"], 0)
    went, _ = P.run(m, {4: P.STOCK_STATE, 8: PAR, 12: IO})
    if went == "stock":
        return "stock"
    return ([m.get(OUTL + 4 * k) for k in range(32)], [m.get(OUTR + 4 * k) for k in range(32)])


def as_bits(out):
    if isinstance(out, str):
        return out
    return ([fbits(x) for x in out[0]], [fbits(x) for x in out[1]])


def script(seed=1, blocks=260):
    """(type word, in L, in R, params) per block: stock, a switch to FDN8 (its clearing),
    noise bursts and an impulse, the knobs moving, a switch back"""
    rnd = random.Random(seed)
    par = [0.1, 0.6, 0.3, 0.5, 0.0, 1.0]
    out = []
    for b in range(blocks):
        tw = 0x100 if b < 3 or b >= blocks - 4 else 0
        if 40 <= b < 46:                                # (after the 32 clearing blocks)
            inl = [rnd.uniform(-0.5, 0.5) for _ in range(32)]
            inr = [rnd.uniform(-0.5, 0.5) for _ in range(32)]
        else:
            inl = [1.0 if (b == 50 and j == 3) else 0.0 for j in range(32)]
            inr = list(inl)
        if b in (135, 140, 141, 142):                   # a knob turned (the ColdFire smooths it)
            par = [min(1.0, x + 0.07 * (k + 1) / 6) for k, x in enumerate(par)]
        if b == 200:
            par = [0.0, 1.0, 0.0, 1.0, 1.0, 0.0]    # the ends: SIZE 127 (the freeze), PRE 0
        out.append((tw, inl, inr, [np.float32(x) for x in par]))
    return out


def test_design_numbers():
    assert D.primes48() == (D.L48, D.A48)
    assert D.RB_END <= D.RING_WORDS
    assert P.CTAB + 4 * P.N_STOCK_CHUNKS <= P.STATE + P.STATE_BYTES
    assert len(P.stock_chunks()) == R.STOCK_WORDS // R.CHUNK


def test_model_is_the_reference():
    m, r = mem0(), R.Ref()
    loud = 0
    for b, (tw, inl, inr, par) in enumerate(script()):
        got = call(m, tw, inl, inr, par)            # words as the DSP stored them
        want = as_bits(r.block(tw, inl, inr, par))
        assert got == want, f"block {b}"
        if not isinstance(want, str):
            loud += sum(1 for w in want[0] + want[1] if w & 0x7FFFFFFF)
    assert loud > 3000                              # the tail is heard, not a run of zeros
    # and the ring, word for word
    ring = [m.get(P.RING + 4 * k) for k in range(D.RING_WORDS)]
    assert ring == [fbits(x) for x in r.ring]


def test_long_is_the_reference():
    """LONG (TYPE 2): from stock, from FDN8 (a switch between the two clears the ring and starts
    again), its tail heard, the ring word for word"""
    m, r = mem0(), R.Ref()
    rnd = random.Random(5)
    par = [np.float32(x) for x in (0.05, 0.75, 0.4, 0.5, 0.0, 1.0)]
    heard = 0
    for b in range(340):                            # (LONG's shortest line is 185 blocks)
        tw = 0x100 if b < 2 else 0 if b < 50 else 0x12340200      # stock, FDN8, LONG (k 49 high: not ours)
        noisy = 40 <= b < 44 or 90 <= b < 96
        inl = [rnd.uniform(-0.5, 0.5) if noisy else 0.0 for _ in range(32)]
        inr = [rnd.uniform(-0.5, 0.5) if noisy else 0.0 for _ in range(32)]
        got = call(m, tw, inl, inr, par)
        want = as_bits(r.block(tw, inl, inr, par))
        assert got == want, f"block {b}"
        if b >= 90 and not isinstance(want, str):
            heard += sum(1 for w in want[0] + want[1] if w & 0x7FFFFFFF)
    assert r.cur == 2 and heard > 3000
    ring = [m.get(P.RING + 4 * k) for k in range(D.RING_WORDS)]
    assert ring == [fbits(x) for x in r.ring]


def test_approximations():
    for x in (-99.5, -20.25, -3.0, -0.001, 0.0, 0.5, 3.75, 6.999):
        assert abs(float(R.exp2(np.float32(x))) / 2 ** x - 1) < 1e-6
    for y in (1.0, 1.5, 2.0, 37.0, 128.0):
        assert abs(float(R.log2(np.float32(y))) - np.log2(y)) < 1e-6
    for x in (1e-3, 0.37, 1.0, 5.5, 3000.0):
        assert abs(float(R.recip(np.float32(x))) * x - 1) < 1e-6
    for x in (1.0, 2.0, 9.0, 1000.0):
        assert abs(float(R.sqrt(np.float32(x))) / np.sqrt(x) - 1) < 1e-6
    for ph in (0, 1 << 30, 1 << 31, 3 << 30, 0x12345678):
        assert abs(float(R.sine(ph)) - np.sin(2 * np.pi * ph / 2 ** 32)) < 1e-6
