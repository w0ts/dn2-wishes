"""scripts/emulib/attkit.py (2026-11-21): a snapshot's converted kit stored back as a boot has it, so a harness that
writes the build's runtime over the snapshot converts it once (the DEP attenuverter, csrc/matrix/atten.c).

A fake memory holds what such a snapshot holds (the matrix's state laid out by the build, the kit, the voices, the
smoother); the C conversion's arithmetic (atten.c mxa_convert, an old sound: D = DEP, DEP 100 %; saved by this build:
DEP = C -> A back) is modelled here to show the double conversion this removes."""

from __future__ import annotations

import pathlib
import struct
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from emulib import attkit

MX_RAM, KIT = 0x476F0000, 0x48000000
FULL = 0x7FFE


class Mem:
    def __init__(self):
        self.b: dict[int, int] = {}

    def write(self, va, data):
        for i, x in enumerate(data):
            self.b[va + i] = x

    def read(self, va, n):
        return bytes(self.b.get(va + i, 0) for i in range(n))

    def long(self, va):
        return struct.unpack(">I", self.read(va, 4))[0]


def snd(t):
    return KIT + 52 + 1163 * t


def dep_of(m, t, lfo):
    return struct.unpack(">H", m.read(snd(t) + 20 + 2 * attkit.DEP_SLOT[lfo], 2))[0]


def converted_snapshot(entry=12, lfo_w=30, depths=((0x432B, 0x4021, 0x4240), (0x6000, 0x3000, 0x4000))):
    """the state a build's UI pass leaves: tracks 0, 1 converted (DEP 100 %, nx1 = -2 (D - 0x4000)); track 2 not
    (MX_PASS); voice v plays track v"""
    tab_b = 23 * entry + 36
    nx1 = 23 * entry + 24
    size = 720 + 33 * tab_b + 4 * 16 * lfo_w + 2 * 2 * 16 * 101 + 32
    m = Mem()
    m.write(MX_RAM, struct.pack(">I", 0x4D580000 | size))
    m.write(attkit.KIT_PTR, struct.pack(">I", KIT))
    m.write(MX_RAM + attkit.MX_KIT, struct.pack(">I", KIT))
    for t in range(3):
        m.write(MX_RAM + attkit.MX_SOUND + 4 * t, struct.pack(">I", snd(t)))
        m.write(MX_RAM + attkit.MX_LIVE + 4 * t, struct.pack(">I", t & 1))
        m.write(attkit.VSOUND + 4 * t, struct.pack(">I", snd(t)))
        tab = MX_RAM + 720 + tab_b * (2 * t + (t & 1))
        for lfo in range(3):
            if t < 2:
                m.write(tab + nx1 + 4 * lfo, struct.pack(">i", -2 * (depths[t][lfo] - 0x4000)))
                m.write(snd(t) + 20 + 2 * attkit.DEP_SLOT[lfo], struct.pack(">H", FULL))
            else:
                m.write(tab + nx1 + 4 * lfo, struct.pack(">i", 1))
                m.write(snd(t) + 20 + 2 * attkit.DEP_SLOT[lfo], struct.pack(">H", 0x5000))
    return m


def convert_old(m, t):
    """the build's first UI pass on a sound with no record (the runtime cleared the wishes table): D = its DEP"""
    return [dep_of(m, t, lfo) for lfo in range(3)]


@pytest.mark.parametrize("entry,lfo_w", [(12, 30), (12, 40), (8, 30), (8, 40)])
def test_the_kit_is_stored_back_and_converts_once(entry, lfo_w):
    depths = ((0x432B, 0x4021, 0x4240), (0x6000, 0x3000, 0x4000))
    m = converted_snapshot(entry, lfo_w, depths)
    rep = attkit.store_kit(m, MX_RAM)
    assert rep["sounds"] == 2 and len(rep["deps"]) == 6
    for t in range(2):
        assert convert_old(m, t) == [attkit.compat(d, FULL) for d in depths[t]] == list(depths[t])
        i = 17 + 101 * t + 8
        assert struct.unpack(">H", m.read(attkit.SM_SRC + 2 * i, 2))[0] == depths[t][0]
        assert struct.unpack(">i", m.read(attkit.SM_STATE + 4 * i, 4))[0] == depths[t][0] << 16
        assert struct.unpack(">H", m.read(attkit.SM_OUT + 2 * i, 2))[0] == depths[t][0]
    assert convert_old(m, 2) == [0x5000] * 3                      # not converted: left alone


def test_a_second_call_stores_nothing():
    m = converted_snapshot()
    attkit.store_kit(m, MX_RAM)
    before = dict(m.b)
    assert attkit.store_kit(m, MX_RAM) == {"sounds": 0, "deps": []} and m.b == before


def test_negative_control_without_it_the_kit_converts_twice(monkeypatch):
    """DNFW_ATTKIT=0 (the harnesses before 2026-11-21): the UI pass takes the converted DEP (100 %) as the depth"""
    monkeypatch.setenv("DNFW_ATTKIT", "0")
    m = converted_snapshot()
    rep = attkit.store_kit(m, MX_RAM)
    assert rep["skipped"] == "DNFW_ATTKIT=0" and len(rep["found"]["deps"]) == 6
    assert convert_old(m, 0) == [FULL] * 3 != [0x432B, 0x4021, 0x4240]


def test_no_matrix_state_or_another_kit_is_left_alone():
    m = Mem()
    assert attkit.store_kit(m, MX_RAM) is None                    # a stock snapshot: no magic
    m = converted_snapshot()
    m.write(MX_RAM + attkit.MX_KIT, struct.pack(">I", KIT + 0x10000))
    assert "skipped" in attkit.store_kit(m, MX_RAM) and dep_of(m, 0, 0) == FULL


def test_the_layout_matches_the_c_structs_known_sizes():
    assert attkit.table_layout(0x4D580000 | (720 + 33 * 312 + 4 * 16 * 30 + 4 * 16 * 101 + 32)) == (312, 300)
    assert attkit.table_layout(0x12345678) is None
