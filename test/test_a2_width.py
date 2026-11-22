"""ANALOG2's WDTH (2026-11-11, the User: "a stereo spread of voices", option A): the swarm's copies panned left and
right through the slot's side block (DRONE's BEAT's, mixed after the pan by dnfw.inserts.post.beat). WDTH 0 writes
nothing (old tracks stay mono); on, the mid is the same sum of the oscillators (to float rounding) and the side is
L - R of the copies, filtered as the mid, x 2 WDTH; nothing without copies."""

from __future__ import annotations

import struct

import pytest

from dnfw.md import core as MDK
from dnfw.engines.analog2 import analog2 as A2
from dnfw.mnm import machines as MM
from dnfw.perc import live as PL
from dnfw.perc import machines as PM
from dnfw.perc import program as PP
from dnfw.perc.dsl import bits

TYPE = next(t for t, k in PP.MNM_TYPES.items() if MM.NAMES[k] == "ANALOG2")
SWARM = [127, 64, 34, 0, 0, 0, 0]                        # six copies


def _render(p2, wdth, blocks=6):
    h = PL.Harness()
    h.words[h.L.md.C["fill"]] = MDK.Z_N
    for k, v in enumerate(A2.table_words()):
        h.words[A2.tables_at() + 4 * k] = bits(v)
    h.set_mnm(TYPE, list(A2.DEFAULTS))
    for (_r, slot, lo, top), x in zip(PM.FX_PARAMS, p2):
        h._half(PM.frame_offset(slot), PL.knob_word(x, top, lo))
    h._half(PM.frame_offset(PM.TYPE_REC[1]), PL.knob_word(wdth, 127, 0))
    out = []
    for b in range(blocks):
        out += h.block(note=60.0, trig=b == 0)
    base = A2.SIDE_L2 + A2.SIDE_STRIDE * h.t if hasattr(h, "t") else A2.SIDE_L2
    side = [struct.unpack("<f", struct.pack("<I", h.mem.get(base + 4 * k)))[0] for k in range(34)]
    return out, side


def test_off_writes_no_side():
    _out, side = _render(SWARM, 0)
    assert side[33] == 0.0 and not any(side[:32])


def test_no_copies_no_side():
    _out, side = _render([0, 64, 34, 0, 0, 0, 0], 127)
    assert side[33] == 0.0 and not any(side[:32])


def test_on_keeps_the_mid_and_writes_the_side():
    mid0, _ = _render(SWARM, 0)
    mid1, side = _render(SWARM, 127)
    assert max(abs(a - b) for a, b in zip(mid0, mid1)) < 1e-6
    assert side[33] == 1.0 and side[32] > 0.0 and max(map(abs, side[:32])) > 0.01


def test_side_scales_with_wdth():
    _, full = _render(SWARM, 127)
    _, half = _render(SWARM, 64)
    for a, b in zip(full[:32], half[:32]):
        assert b == pytest.approx(a * 64 / 127, rel=1e-5, abs=1e-9)


def test_one_copy_left_then_right(monkeypatch):
    """one copy: its side's sign alone decides the side's (L - R: + on the left)"""
    one = [20, 64, 34, 0, 0, 0, 0]                       # SWRM 1 (its record spans 0..120: trunc(20 / 120 x 7))
    _, left = _render(one, 127)
    monkeypatch.setattr(A2, "SIDE_OF", (-1,) + A2.SIDE_OF[1:])
    _, right = _render(one, 127)
    assert max(map(abs, left[:32])) > 0.01
    assert right[:32] == [-x for x in left[:32]]
