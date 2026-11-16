"""Stock records' units, a build option (2026-11-11, the User: proper values everywhere, "gate it with a compile
option at first"): DN2_STOCK_UNITS at generation adds dnfw.engines.units STOCK_UNITS to the header and the formatters
in csrc/waverider/md_page.c (stu_*). Without it the header is exactly as before (so the code is), with it each
listed record answers its unit, and the stock formatter it replaces is stock 1.12's own at that record."""

from __future__ import annotations

import os
import pathlib
import shutil
import struct
import subprocess

import pytest

from dnfw.engines import units as MU
from dnfw.waverider import pages as WP

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _header(monkeypatch, on: bool) -> str:
    if on:
        monkeypatch.setenv("DN2_STOCK_UNITS", "1")
    else:
        monkeypatch.delenv("DN2_STOCK_UNITS", raising=False)
    return WP.mnm_c_header()


def test_off_header_has_nothing_of_it(monkeypatch):
    off = _header(monkeypatch, False)
    assert "STU_" not in off and "stu_" not in off
    monkeypatch.setenv("DN2_STOCK_UNITS", "0")
    assert WP.mnm_c_header() == off


def test_on_header_lists_the_records(monkeypatch):
    on = _header(monkeypatch, True)
    off = _header(monkeypatch, False)
    assert f"#define STU_N {len(set(MU.STOCK_UNITS) | set(MU._stock_table_rows()[0]))}" in on
    assert on.startswith(off.split("static const short mnm_curves")[0])     # what comes before is unchanged


def test_stock_formatters_are_stock_112s():
    img = pathlib.Path(os.environ.get("DN2_MAIN_112", ROOT.parent.parent.parent / "scratch/sec112/section_3_MAIN_OS.bin"))
    if not img.exists():
        pytest.skip("no stock 1.12 MAIN OS section")
    b = img.read_bytes()
    for rid, fmt in MU._STOCK_FMT_OF.items():                                # a measured table's records
        assert struct.unpack_from(">15I", b, 0x401F83A4 + 60 * rid - 0x40000400)[13] == fmt, rid
    for rid, (_k, _f, _o, fmt) in MU.STOCK_UNITS.items():
        o = 0x401F83A4 + 60 * rid - 0x40000400
        w = struct.unpack_from(">15I", b, o)
        assert w[13] == fmt, rid
        assert (w[2] >> 8, w[3] >> 8) == (0, 127), rid                       # the knob is the value 0..127


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_the_formatters_answer_units(monkeypatch, tmp_path):
    hdr = _header(monkeypatch, True)
    src = (ROOT / "csrc/waverider/md_page.c").read_text()
    a, b = src.index("static int ucat"), src.index("static int mnm_choice_count")
    keep = [ln for ln in hdr.splitlines() if ln.startswith((
        "#define MNM_N", "#define MNM_J", "enum { MU_", "static const unsigned char mnm_unit", "static const unsigned char ins_unit",
        "static const unsigned char flt_unit", "static const unsigned char fxp_unit", "static const short mnm_curves", "static const unsigned short mnm_glid",
        "#define STU_", "static const unsigned short stu_", "static const unsigned char stu_", "static const unsigned int stu_"))]
    prog = ("#include <stdio.h>\ntypedef unsigned int u32;\n#define DN2_STOCK_UNITS 1\nint wr_track_ours(void){return 0;}\n"
            + "\n".join(keep) + "\n" + src[a:b].replace("__attribute__((section(\".data\")))", "")
            + "\nint main(void){char b[16];for(int w=0;w<STU_N;w++)for(int k=0;k<128;k++){stu_fns[w](k<<8,b);"
              "printf(\"%d %d %s\\n\",stu_ids[w],k,b);}return 0;}\n")
    c = tmp_path / "s.c"
    c.write_text(prog)
    exe = tmp_path / "s"
    subprocess.run(["cc", "-O1", "-w", "-o", str(exe), str(c)], check=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()
    seen = set()
    for ln in out:
        rid, k, txt = ln.split(" ", 2)
        assert 1 <= len(txt) <= 4 and not txt.isdigit(), ln
        seen.add(int(rid))
        if MU.STOCK_UNITS.get(int(rid), ("",))[0] == "pct":
            assert txt == f"{(int(k) * 100 + 63) // 127}%", ln
    assert seen == set(MU.STOCK_UNITS) | set(MU._stock_table_rows()[0])


def test_measured_tables_are_whole():
    for name, q in MU.stock_measured().items():
        assert len(q["values"]) == 128, name
        assert q["unit"] and q["how"] and q["records"], name
        assert all(r in MU._STOCK_FMT_OF for r in q["records"]), name
