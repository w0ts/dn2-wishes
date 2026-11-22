"""The fast link's packet window (dnfw.sampler.program.tdm_rx), run in the DSL's run mode on a packet in the TDM
receive page (2026-11-20, the ghost audit, docs/memory-map.md "The DSP's write windows"): a packet whose word
offset is negative (its high half >= 0x8000) wrote its words below the pool, where stock's and our delay lines
lie. Now it writes nothing; the offsets the ColdFire sends still write where they did."""

from __future__ import annotations

import pytest

from dnfw.perc.dsl import Mem, Prog
from dnfw.sampler import live as SL
from dnfw.sampler import machines as SM
from dnfw.sampler import program as SP
from dnfw.waverider import dsp

POOL = dsp.SMP_POOL_DDR
MARK = 0x5EED0000


def packet_units(off: int, words: list[int]) -> list[int]:
    """the 256 units as link.c's smp_tdm sends them"""
    u = [SM.RX_MAGIC, 7, off & 0xFFFF, (off >> 16) & 0xFFFF]
    for k in range(SM.RX_WORDS):
        w = words[k] if k < len(words) else 0
        u += [w & 0xFFFF, (w >> 16) & 0xFFFF]
    u += [len(words), 0, 0]
    u.append((SM.LINK_SEED + sum(u)) & 0xFFFF)
    assert len(u) == SM.RX_UNITS
    return u


def run(off: int, n: int = 8) -> dict[int, int]:
    """-> the words the packet wrote in DDR"""
    mem = Mem()
    mem.put(SM.TDM_PAGE, 0)
    page = SM.TDM_RX + 32
    for i, v in enumerate(packet_units(off, [MARK + k for k in range(n)])):
        mem.put(page + 64 * (i >> 3) + 4 * (i & 7), SM.TDM_TAG << 16 | v)
    p = Prog("run", mem=mem)
    SP.tdm_rx(p, SL.layout())
    return {a: v for a, v in mem.w.items() if a >= 0x80000000 and (v & 0xFFFF0000) == MARK}


def test_a_packet_inside_the_pool_is_written():
    off = SM.DATA_OFFSET // 4 + 100
    got = run(off)
    assert got == {POOL + 4 * (off + k): MARK + k for k in range(8)}


def test_a_packet_at_the_pools_top_is_written():
    off = SM.POOL_WORDS - 8
    assert len(run(off)) == 8


@pytest.mark.parametrize("off", [-1, -8, 0x80000000, 0xFF000000, 0xFFC00000, 0xFFFF0000])
def test_a_negative_offset_writes_nothing(off):
    """0xFF000000 words below the pool is stock's reverb / delay (0x80000000..), 0xFFC00000 the bus XDLY lines"""
    assert run(off & 0xFFFFFFFF) == {}


def test_past_the_pools_top_writes_nothing():
    assert run(SM.POOL_WORDS - 4) == {}
