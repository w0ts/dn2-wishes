"""The send FX pages' values in units (2026-11-11, the User: no bare 0..127): while the Reverb page's TYPE is
FDN8 / LONG and the Delay page's XDLY, their knobs' value texts are the FDN8 / XDLY inserts' (csrc/fdn8/ui.c
rvu, csrc/xdly/ui.c dlu -> md_page.c mu_ins, dnfw.mnm.units INS_UNITS): the same engines read the same knob
scales, so each record must sit on the insert knob that drives the same engine parameter. The sample machines'
LEV reads the gain LEV / LEV_UNITY in percent (csrc/sampler/fmt.c f_lev)."""

from __future__ import annotations

import pathlib
import re

from dnfw.inserts import bus as IB
from dnfw.mnm import units as MU
from dnfw.sampler import machines as SM
from dnfw.xdly import design as XD
from dnfw.fdn8 import design as FD

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _ids(path: str, name: str) -> list[int]:
    m = re.search(name + r"\[\w*\] = \{([0-9, ]+)\}", (ROOT / path).read_text())
    assert m, name
    return [int(x) for x in m.group(1).split(",")]


def test_reverb_records_on_fdn8_knobs():
    # the reverb's struct (fdn8.ref: +0 PRE .. +0x14 LPF) is records 123..128 in order; the insert's K1..K6 the same
    assert _ids("csrc/fdn8/ui.c", "rvu_ids") == [123, 124, 125, 126, 127, 128]
    assert IB.FDN8_PAR == [(k, 1 / 127) for k in range(6)]
    assert set(MU.INS_UNITS["FDN8"]) == set(range(6))


def test_delay_records_on_xdly_knobs():
    # the insert feeds the stock struct (TIME, X, WID, FDBK, HPF, LPF) from K1, -, K2, K3, K4, K5: the records
    # 113 115 116 117 118 are knobs 0..4 in that order
    assert _ids("csrc/xdly/ui.c", "dlt_ids") == [113, 115, 116, 117, 118]
    knobs = [k for k, _s in IB.XDLY_PAR if k is not None]
    assert knobs == [0, 1, 2, 3, 4]
    assert set(MU.INS_UNITS["XDLY"]) == set(range(5))


def test_xdly_times_are_the_design_range():
    kind, fn, _off = MU.INS_UNITS["XDLY"][0]
    assert kind == "ms" and MU.INS_UNITS["XDLY"][1][1] is fn
    fs = 48000.0
    assert abs(fn(0) - XD.T_MIN / fs * 1000.0) < 1e-9
    assert abs(fn(127) - XD.T_MAX / fs * 1000.0) < 1e-6


def test_fdn8_filters_are_the_design_range():
    assert abs(MU.INS_UNITS["FDN8"][4][1](0) - FD.HPF_LO) < 1e-9
    assert abs(MU.INS_UNITS["FDN8"][4][1](127) - FD.HPF_LO * FD.FILT_SPAN) < 1e-6
    assert abs(MU.INS_UNITS["FDN8"][5][1](127) - FD.LPF_LO * FD.FILT_SPAN) < 1e-6


def test_sample_lev_reads_its_gain():
    f = (ROOT / "csrc/sampler/fmt.c").read_text()
    assert "SMP_LEV_REC};" in f and "f_mtune, f_lev};" in f
    assert "coarse(v, SMP_LEV_REC) * 100 / SMP_LEV_UNITY" in f
    assert SM.LEV_UNITY == 100 and SM.LEV_REC == 241
    assert all(any(r == SM.LEV_REC for r, _s, _l in page) for page in SM.PAGES.values())


def _stock_fmts(path: str, name: str) -> list[int]:
    m = re.search(name + r"\[\w*\] = \{([0-9A-Fa-fxu, ]+)\}", (ROOT / path).read_text())
    assert m, name
    return [int(x.strip().rstrip("u"), 16) for x in m.group(1).split(",")]


def test_stock_formatters_are_stock_112s():
    """the STOCK texts go to stock's formatters at fixed addresses: they must be what stock 1.12's records hold
    (record id x 60 + 0x34 from 0x401F83A4; MAIN OS loads at 0x40000400)"""
    import os
    import struct
    import pytest
    img = pathlib.Path(os.environ.get("DN2_MAIN_112", ROOT.parent.parent.parent / "scratch/sec112/section_3_MAIN_OS.bin"))
    if not img.exists():
        pytest.skip("no stock 1.12 MAIN OS section")
    b = img.read_bytes()

    def fmt(rid: int) -> int:
        return struct.unpack_from(">I", b, 0x401F83A4 + 60 * rid + 0x34 - 0x40000400)[0]
    assert _stock_fmts("csrc/fdn8/ui.c", "rvu_stock") == [fmt(r) for r in _ids("csrc/fdn8/ui.c", "rvu_ids")]
    assert _stock_fmts("csrc/xdly/ui.c", "dlu_stock") == [fmt(r) for r in _ids("csrc/xdly/ui.c", "dlt_ids")]
