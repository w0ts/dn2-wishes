"""FDN8's tank stage by stage (dnfw.fdn8.stages, 2026-11-14) against the sample loop it replaces (program.STAGED
False): the same output and the same memory, word for word, block after block, with the ring full of random words
and the write index placed so that every tap's run of 32 words crosses the ring's start at every place in a block
(and the diffusers' L2 ring's start)."""

from __future__ import annotations

import importlib
import pathlib
import random
import struct
import sys

import pytest

from dnfw.fdn8 import design as D
from dnfw.fdn8 import program as P
from dnfw.fdn8 import stages as S

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
T = importlib.import_module("test_fdn8")

SCRATCH = set()
_X, _S, _F = S.bufs()
SCRATCH.update(range(_X, _X + S.BUF_BYTES, 4))
SCRATCH.update(range(S.lr_bufs()[0], S.lr_bufs()[1] + 4 * 32, 4))
SCRATCH.update(P.C[n] for n in [f"t{k}" for k in range(8)] + list(S.IO.values()) + ["xw"] + [f"f{k}" for k in range(8)])


def fbits(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def _block(m, staged: bool, tw, inl, inr, par):
    old = P.STAGED
    P.STAGED = staged
    try:
        return T.call(m, tw, inl, inr, par)
    finally:
        P.STAGED = old


def _same(ma, mb, where: str) -> None:
    keys = (set(ma.w) | set(mb.w)) - SCRATCH
    bad = [k for k in keys if ma.get(k) != mb.get(k)]
    assert not bad, f"{where}: {len(bad)} words differ, first {sorted(hex(k) for k in bad)[:6]}"


def _primed(tw: int, seed: int, p_words: int):
    """two memories, FDN8 (TW 0) or LONG switched to and its clearing skipped: the ring (and the L2 diffuser ring)
    full of the same random floats, the write index at P_WORDS"""
    rnd = random.Random(seed)
    par = [0.3, 0.6, 0.3, 0.5, 0.2, 1.0]
    mems = []
    for _ in range(2):
        m = T.mem0()
        T.call(m, tw, [0.0] * 32, [0.0] * 32, par)      # the switch (its first clearing block)
        m.put(P.C["clr"], 0)
        m.put(P.C["force"], 1)
        mems.append(m)
    words = [fbits(rnd.uniform(-0.3, 0.3)) for _ in range(D.RING_WORDS)]
    l2 = [fbits(rnd.uniform(-0.3, 0.3)) for _ in range(P.DIFF_WORDS)]
    for m in mems:
        for k, w in enumerate(words):
            m.put(P.RING + 4 * k, w)
        for k, w in enumerate(l2):
            m.put(P.DIFF_SEND_L2 + 4 * k, w)
        m.put(P.C["p4"], (4 * p_words) & 0xFFFFFFFF)
    return mems, par


def _run(tw: int, seed: int, p_words: int, blocks: int, par_moves: bool = False) -> None:
    (ma, mb), par = _primed(tw, seed, p_words)
    rnd = random.Random(seed + 1)
    for b in range(blocks):
        inl = [rnd.uniform(-0.5, 0.5) for _ in range(32)]
        inr = [rnd.uniform(-0.5, 0.5) for _ in range(32)]
        if par_moves and b % 3 == 2:
            par = [min(1.0, x + 0.11) for x in par]
        oa = _block(ma, False, tw, inl, inr, par)
        ob = _block(mb, True, tw, inl, inr, par)
        assert oa == ob, f"tw {tw:#x} p {p_words} block {b}: output"
        _same(ma, mb, f"tw {tw:#x} p {p_words} block {b}")


def _offsets(v: int) -> list[int]:
    d = D.variant(v)
    offs = [D.RB_PD, D.RB_PD + D.PD_MAX // 3]
    for k in range(4):
        offs += [d["RA"][k], d["RA"][k] + d["A"][k]]
    for k in range(8):
        offs += [d["RL"][k], d["RL"][k] + d["L"][k] + D.CM]
    return offs


@pytest.mark.parametrize("tw,v", [(0, 1), (0x12340200, 2)])
def test_every_tap_across_the_ring_start(tw, v):
    """for each tap offset, the write index placed so that the tap's run crosses the ring's start at sample 0, 1,
    15, 30, 31 of the first block (and nearby in the next); 3 blocks each"""
    seed = 11
    for off in _offsets(v):
        for j in (0, 1, 15, 30, 31, 33):
            seed += 1
            _run(tw, seed, -off + j, 3)


@pytest.mark.parametrize("tw", [0, 0x12340200])
def test_long_run_moving_knobs(tw):
    """60 blocks from a few places, the knobs moving (the parameters worked out again)"""
    for k, p_words in enumerate((0, 77, 4096 * 7 + 3, -5000)):
        _run(tw, 100 + k, p_words, 60, par_moves=True)


def test_second_page_width():
    """the width branch (WDTH not 127) and DIFF / FREZ off their defaults"""
    for knobs in ((20, 40, 30), (127, 0, 90)):
        (ma, mb), par = _primed(0, 7, 123)
        for m in (ma, mb):
            T.put_ex(m, 1, *knobs)
        rnd = random.Random(8)
        for b in range(20):
            inl = [rnd.uniform(-0.5, 0.5) for _ in range(32)]
            inr = [rnd.uniform(-0.5, 0.5) for _ in range(32)]
            assert _block(ma, False, 0, inl, inr, par) == _block(mb, True, 0, inl, inr, par), (knobs, b)
            _same(ma, mb, f"{knobs} block {b}")


def test_buffers_inside_the_state():
    assert _X >= P.VT2 + 4 * P.NV and _X + S.BUF_BYTES <= P.STATE + P.STATE_BYTES
