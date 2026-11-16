"""The send FX pages' values in units (2026-11-11, the User: no bare 0..127): while the Reverb page's TYPE is
FDN8 / LONG and the Delay page's XDLY, their knobs' value texts are the FDN8 / XDLY inserts' (csrc/fdn8/ui.c
rvu, csrc/xdly/ui.c dlu -> md_page.c mu_ins, dnfw.engines.units INS_UNITS): the same engines read the same knob
scales, so each record must sit on the insert knob that drives the same engine parameter. The sample machines'
LEV reads the gain LEV / LEV_UNITY in percent (csrc/sampler/fmt.c f_lev)."""

from __future__ import annotations

import pathlib
import re

from dnfw.inserts import bus as IB
from dnfw.engines import units as MU
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


def _md_units_prog(tmp_path, main: str) -> list[str]:
    import shutil
    import subprocess
    from dnfw.waverider import pages as WP
    if shutil.which("cc") is None:
        import pytest
        pytest.skip("no C compiler")
    src = (ROOT / "csrc/waverider/md_page.c").read_text()
    a, b = src.index("static int ucat"), src.index("static int mnm_choice_count")
    keep = [ln for ln in WP.mnm_c_header().splitlines() if ln.startswith((
        "#define MNM_N", "#define MNM_J", "enum { MU_", "static const unsigned char mnm_unit", "static const unsigned char ins_unit",
        "static const unsigned char flt_unit", "static const unsigned char fxp_unit", "static const short mnm_curves",
        "static const unsigned short mnm_glid"))]
    c = tmp_path / "u.c"
    c.write_text("#include <stdio.h>\n" + "\n".join(keep) + "\n" + src[a:b].replace("__attribute__((section(\".data\")))", "")
                 + "\nint main(void){" + main + "return 0;}\n")
    subprocess.run(["cc", "-O1", "-w", "-o", str(tmp_path / "u"), str(c)], check=True)
    return subprocess.run([str(tmp_path / "u")], check=True, capture_output=True, text=True).stdout.splitlines()


def test_page2_places_have_units(tmp_path):
    """the send pages' page 2 (2026-11-13): every labelled place but the Delay's TIME (stock's cell) reads a unit"""
    out = _md_units_prog(tmp_path, "for(int p=0;p<2;p++)for(int i=0;i<8;i++)for(int k=0;k<128;k++){"
                                   "const char*t=mu_fxp(p,i,k);if(t)printf(\"%d %d %d %s\\n\",p,i,k,t);}")
    got = {}
    for ln in out:
        p, i, k, t = ln.split(" ", 3)
        assert 1 <= len(t) <= 4 and not t.isdigit(), ln
        got[(int(p), int(i), int(k))] = t
    params = (ROOT / "csrc/fxpage/fxp_params.h").read_text()
    labels = {0: re.findall(r'\{"(\w*)", \d+\}', params.split("fxp_reverb")[0]),
              1: re.findall(r'\{"(\w*)", \d+\}', params.split("fxp_reverb")[1])}
    for p, row in labels.items():
        for i, lab in enumerate(row):
            if lab and not (p == 0 and i == 0):
                assert (p, i, 64) in got, (p, lab)
    assert got[(0, 1, 0)] == "1ms" and got[(0, 1, 127)] == "1.0s"            # SLEW 1 ms .. 1 s
    assert got[(0, 2, 0)] == "-10" and got[(0, 2, 64)] == "-4dB" and got[(0, 2, 127)] == "0dB"   # KNEE 0.3 .. 0.95 (-10 and under: no dB, four characters)
    assert got[(0, 4, 64)] == "+0%" and got[(0, 4, 0)] == "-99%"             # INPT signed
    assert got[(1, 0, 64)] == "100%" and got[(1, 0, 127)] == "198%"          # DIFF x k / 64
    assert "page == PAGE_DELAY || page == PAGE_REVERB" in (ROOT / "csrc/fxpage/fxp.c").read_text()   # not JUNO's MIX


def test_thres_reads_the_armed_level(tmp_path):
    """the recorder's THRES (csrc/sampler/rec_dt2.c thres_db) within 0.5 dB of the level rec.c thr_word arms at"""
    import math
    rec = (ROOT / "csrc/sampler/rec.c").read_text()
    frac = [int(x) for x in re.search(r"thr_frac\[12\] = \{[^}]*?\n\s*([\d, ]+)\}", rec).group(1).split(",")]
    floor = int(re.search(r"#define REC_THR_FLOOR (\d+)u", rec).group(1))
    dt2 = (ROOT / "csrc/sampler/rec_dt2.c").read_text()
    body = dt2[dt2.index("static int thres_db"):dt2.index("/* the RECORDER (DT2 SamplerView")]
    import shutil
    import subprocess
    if shutil.which("cc") is None:
        import pytest
        pytest.skip("no C compiler")
    (tmp_path / "t.c").write_text("#include <stdio.h>\n" + body + "int main(void){for(int t=0;t<=120;t++)printf(\"%d\\n\",thres_db(t));return 0;}\n")
    subprocess.run(["cc", "-O1", "-o", str(tmp_path / "t"), str(tmp_path / "t.c")], check=True)
    got = [int(x) for x in subprocess.run([str(tmp_path / "t")], check=True, capture_output=True, text=True).stdout.split()]
    for t in range(121):
        v = floor if t == 0 else max(64, (32767 >> ((120 - t) // 12)) * frac[(120 - t) % 12] >> 16)
        assert abs(got[t] - 20 * math.log10(v / 32767)) <= 0.5, (t, got[t])
    assert "%ddB" in dt2
