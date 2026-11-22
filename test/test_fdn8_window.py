"""2026-11-21 (fx-fast): FDN8 / LONG clear only the ring's window a fresh engine reads before it writes (ref.WINDOW_CLEAR).
The output must be the whole-ring clear's bit for bit: the DSL program's model, its ring poisoned with NaNs outside
what it clears, against the reference that clears the whole ring (WINDOW_CLEAR False), through switches stock ->
FDN8 -> LONG -> FDN8 -> stock -> LONG at write places that wrap the window round the ring's end."""

from __future__ import annotations

import importlib
import pathlib
import random
import sys

import numpy as np

from dnfw.fdn8 import design as D
from dnfw.fdn8 import program as P
from dnfw.fdn8 import ref as R

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
T = importlib.import_module("test_fdn8")
as_bits, call, mem0 = T.as_bits, T.call, T.mem0

POISON = 0x7FC0DEAD                                  # a NaN: one read of it reaches the output


def _poison_ring(m) -> None:
    for k in range(D.RING_WORDS):
        m.put(P.RING + 4 * k, POISON)


def _old_block(r: R.Ref, tw, inl, inr, par):
    R.WINDOW_CLEAR = False
    try:
        return as_bits(r.block(tw, inl, inr, par))
    finally:
        R.WINDOW_CLEAR = True


def _plan():
    """(type word, blocks): each switch starts a fresh engine where the last left the write place"""
    return ((0x100, 2), (0, 140), (0x12340200, 300), (0, 120), (0x100, 3), (0x12340200, 260), (0, 90))


def test_window_clear_output_is_the_whole_ring_clears():
    assert R.WINDOW_CLEAR
    m, old, new = mem0(), R.Ref(), R.Ref()
    _poison_ring(m)
    rnd = random.Random(21)
    par = [np.float32(x) for x in (0.1, 0.9, 0.3, 1.0, 0.0, 1.0)]
    heard, b, wrapped = 0, 0, 0
    for tw, n in _plan():
        for k in range(n):
            noisy = 34 <= k < 40 or 70 <= k < 74
            inl = [rnd.uniform(-0.5, 0.5) if noisy else 0.0 for _ in range(32)]
            inr = [rnd.uniform(-0.5, 0.5) if noisy else 0.0 for _ in range(32)]
            if k == 0 and tw != 0x100:
                p0 = (m.get(P.C["p4"]) >> 2) & D.RING_MASK
                end = D.RB_ENDL if tw == 0x12340200 else D.RB_END
                wrapped += (p0 & ~15) + end > D.RING_WORDS
            got = call(m, tw, inl, inr, par)
            want = _old_block(old, tw, inl, inr, par)
            assert got == want, f"block {b} (type word {tw:#x}, its block {k})"
            assert as_bits(new.block(tw, inl, inr, par)) == want, f"the new reference, block {b}"
            if not isinstance(want, str):
                heard += sum(1 for w in want[0] + want[1] if w & 0x7FFFFFFF)
            b += 1
    assert heard > 5000 and wrapped >= 2


def test_window_ring_is_the_new_reference_word_for_word():
    """where the window clear and the reference agree on every ring word (stale words included)"""
    m, r = mem0(), R.Ref()
    rnd = random.Random(4)
    par = [np.float32(x) for x in (0.05, 0.75, 0.4, 0.5, 0.0, 1.0)]
    for tw, n in ((0x100, 2), (0, 80), (0x12340200, 120)):
        for k in range(n):
            noisy = 40 <= k < 46
            inl = [rnd.uniform(-0.5, 0.5) if noisy else 0.0 for _ in range(32)]
            inr = [rnd.uniform(-0.5, 0.5) if noisy else 0.0 for _ in range(32)]
            assert call(m, tw, inl, inr, par) == as_bits(r.block(tw, inl, inr, par))
    ring = P.ring_view(m.get, P.RING, m.get(P.C["p4"]), None)
    assert ring == [int(x) for x in r.ring.view(np.uint32)]


def test_window_bounds():
    for t, end in ((1, D.RB_END), (2, D.RB_ENDL)):
        assert R.WIN[t] % 16 == 0 and R.CLEAR_BLOCKS * R.WIN[t] >= end + 15
        assert R.WIN[t] < R.CHUNK
