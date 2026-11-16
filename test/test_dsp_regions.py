"""dsp.check_regions (2026-11-12): every L1 / L2 / DDR area of ours, loaded or not, at its real extent, disjoint; a
container's sub-areas inside it and disjoint. section7() refuses a build that breaks it. The case that made it: PERC's
tan table given L1 0x2e4080, inside the bus FDN8 stores (inserts.bus.FD_L1), which spans()' padding hid."""

from __future__ import annotations

import inspect

import pytest

from dnfw.inserts import bus as ins_bus
from dnfw.inserts import design as ins_d
from dnfw.mnm import plk
from dnfw.waverider import dsp


def test_this_tree_passes():
    dsp.check_regions()


def test_section7_runs_it():
    assert "check_regions()" in inspect.getsource(dsp.section7)


def test_the_regions_name_the_run_time_areas():
    names = " ".join(w for w, *_r in dsp.regions())
    for part in ("FD_L1", "relatch", "render scratch", "shipped", "pool", "MV_RING", "BIG_DDR", "VEL_OFF"):
        assert part in names, part


def _with_span(monkeypatch, what, at, n):
    raw = dsp._raw_spans
    monkeypatch.setattr(dsp, "_raw_spans", lambda: sorted(raw() + [(what, at, bytes(n))], key=lambda s: s[1]))


def test_the_tan_table_in_the_bus_fdn8_stores_fails(monkeypatch):
    _with_span(monkeypatch, "PERC's tan table, its L1 copy", 0x2E4080, 2056)
    with pytest.raises(dsp.DspError, match="FD_L1"):
        dsp.check_regions()


def test_a_span_over_the_relatch_words_fails(monkeypatch):
    _with_span(monkeypatch, "a table", 0x2E0180, 64)
    with pytest.raises(dsp.DspError, match="relatch"):
        dsp.check_regions()


def test_a_ddr_span_over_plaits_buffers_fails(monkeypatch):
    ddr = dsp.ddr_spans
    monkeypatch.setattr(dsp, "ddr_spans", lambda: ddr() + [("a ring", plk.BIG_DDR + 0x1000, bytes(16))])
    with pytest.raises(dsp.DspError, match="BIG_DDR"):
        dsp.check_regions()


def test_a_scratch_word_over_another_fails(monkeypatch):
    from dnfw.perc import program as PP
    monkeypatch.setattr(PP, "VEL_OFF", PP.BOUNDS_OFF)
    with pytest.raises(dsp.DspError, match="in Monomachine scratch"):
        dsp.check_regions()


def test_the_fdn8_stores_fit_before_the_render_scratch():
    assert ins_bus.FD_L1 + ins_d.FDN8_INSTANCES * ins_bus.FD_L1_BYTES <= dsp.MNM_RENDER_DM
