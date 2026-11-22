"""ANALOG2 (machine 51; 22 until 2026-11-18) held for 3 s (4,500 blocks) in the model (the program the SHARC runs bit for bit):
finite and audible to the end, at the defaults and on each of its 25 filter choices at three notes
(2026-11-10: the User: ANALOG 2 works badly on the unit; the runner's steps run tens of blocks)."""

from __future__ import annotations

import math

import pytest

from dnfw.md import core as MDK
from dnfw.engines.analog2 import analog2 as A2
from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.perc import machines as PM
from dnfw.perc import program as PP
from dnfw.perc.dsl import bits

TYPE = next(t for t, k in PP.MNM_TYPES.items() if MM.NAMES[k] == "ANALOG2")


def _held(blocks, note=60.0, flt=0):
    h = PL.Harness()
    h.words[h.L.md.C["fill"]] = MDK.Z_N
    for k, v in enumerate(A2.table_words()):             # the coordinator loads the filters' mix tables
        h.words[A2.tables_at() + 4 * k] = bits(v)
    h.set_mnm(TYPE, list(A2.DEFAULTS))
    p2 = list(A2.DEFAULTS2)
    p2[6] = flt
    for (_r, slot, lo, top), x in zip(PM.FX_PARAMS, p2):
        h._half(PM.frame_offset(slot), PL.knob_word(x, top, lo))
    peaks = []
    for b in range(blocks):
        out = h.block(note=note, trig=b == 0)
        assert all(math.isfinite(x) for x in out), f"non-finite in block {b}"
        peaks.append(max(abs(x) for x in out))
    return peaks


def test_three_seconds_at_the_defaults():
    peaks = _held(4500)
    assert max(peaks[-300:]) > 0.05


@pytest.mark.parametrize("flt", range(0, 125, 5))
@pytest.mark.parametrize("note", (36.0, 60.0, 84.0))
def test_every_filter_choice_sounds_at_the_end(flt, note):
    peaks = _held(300, note, flt)
    assert max(peaks[-60:]) > 0.01
