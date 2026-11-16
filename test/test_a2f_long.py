"""The A2 filter machines held for 3 s (4,500 blocks) in the pass's model (dnfw.engines.analog2.filters.live, the program the
SHARC runs bit for bit): every model stays finite and audible to the end (2026-11-10: the User reported the
filters stopping after about a second; the runner's steps only run tens of blocks)."""

from __future__ import annotations

import math
import struct

import pytest

from dnfw.engines.analog2.filters import design as DS
from dnfw.engines.analog2.filters import live as AL
from dnfw.engines.analog2.filters import program as P

BLOCKS = 4500
THRESHOLD = 0.01


def _held(typ: int) -> list[float]:
    img = AL.Image()
    img.route([0] + [0x7FFF] * 15)
    img.ftype(0, typ)
    img.record(0, mode1=0.2, freq=0.5, res=0.5, mode2=0.1, atk=0.0, dec=0.5, frq2=0.5, res2=0.3, env=0.5, key=0.0)
    img.note(0, 60.0)
    peaks, ph = [], 0.0
    for b in range(BLOCKS):
        if b == 0:
            img.trig([0])
        else:
            img.mem.put(P.TRIGW, img.mem.get(P.TRIGW) & 0xFFFF)
        xs = []
        for _ in range(32):
            ph += 2 * math.pi * 220 / 48000.0
            xs.append(0.5 * math.sin(ph) + 0.3 * math.sin(3 * ph))
        img.buffer(0, xs)
        AL.run(img.mem)
        y = img.read_buffer(0)
        assert all(math.isfinite(v) for v in y), f"{DS.TYPES[typ]}: non-finite output in block {b}"
        peaks.append(max(abs(v) for v in y))
    return peaks


@pytest.mark.parametrize("typ", DS.BUILT_TYPES or tuple(DS.TYPES))
def test_filter_held_three_seconds(typ):
    peaks = _held(typ)
    assert max(peaks[-300:]) > THRESHOLD, f"{DS.TYPES[typ]} is silent at the end of 3 s"
