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
    # REC_BASE: where our C reads stock's records, as the build passes it (cpage: pages.lfo4_moved(); since
    # 2026-11-16 lfo4112). Only stu_poll's STU_FMT reads it, which this program never calls
    prog = ("#include <stdio.h>\ntypedef unsigned int u32;\n#define DN2_STOCK_UNITS 1\nint wr_track_ours(void){return 0;}\n"
            + f"#define REC_BASE {WP.lfo4_moved()['REC_BASE']:#x}u\n"
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


def _fine_prog(hdr: str, smp: str) -> str:
    """fmt.c's smp_fine and md_page.c's stu_stock_of compiled natively, the records and value types in arrays: record
    36 (FREQ) holds our Hz formatter, as stu_poll leaves it with the option on"""
    fmt = (ROOT / "csrc/sampler/fmt.c").read_text()
    a = fmt.index("#define POS_RANGE")
    b = fmt.index("\n}\n", fmt.index("void smp_fine(int kind)\n{")) + 3
    body = fmt[a:b].replace("__attribute__((section(\".data\")))", "")
    # the record and the value-type accessors, as fmt.c spells them (REC_BASE since 2026-11-16 lfo4112): each must be
    # found, or the program would read the real addresses
    for old, new in (("((int *)(REC_BASE + 60u * (id)))", "(rec_w[id])"),
                     ("((u32 *)(0x4243425Cu + 68u * (id) + 4u))", "(entry_type[id])")):
        assert body.count(old) == 1, old
        body = body.replace(old, new)
    md = (ROOT / "csrc/waverider/md_page.c").read_text()
    stu = md[md.index("void *stu_stock_of(int id)"):]
    stu = stu[:stu.index("\n}\n") + 3]
    keep = [ln for ln in hdr.splitlines() if ln.startswith(("#define STU_N ", "static const unsigned short stu_ids",
                                                            "static const unsigned int stu_stock"))]
    defs = [ln for ln in smp.splitlines() if ln.startswith(("#define SMP_KIND0", "#define SMP_STRT_ID", "#define SMP_LEN_ID",
                                                            "#define SMP_LOOP_ID", "#define SMP_STRETCH_KIND",
                                                            "#define SMP_REPITCH_KIND", "#define SMP_BOUNCE_KIND"))]
    return ("#include <stdio.h>\n#include <stdint.h>\ntypedef unsigned int u32;\ntypedef unsigned short u16;\n"
            "#define DN2_STOCK_UNITS 1\n" + "\n".join(keep + defs) + "\n"
            "static int rec_w[512][15];\nstatic u32 entry_type[512][4];\nstatic void *rec_fmt[512];\n"
            "#define RECORD_FMT(id) (rec_fmt[id])\n" + stu + body +
            "\nstatic void ours_hz(int v, char *b) { (void)v; b[0] = 0; }\n"
            "static void strt_own(int v, char *b) { (void)v; b[0] = 0; }\n"
            "int main(void) {\n"
            "    void *stock36 = stu_stock_of(36);\n"
            "    rec_fmt[36] = (void *)ours_hz;             /* stu_poll: ours on FREQ */\n"
            "    rec_fmt[SMP_STRT_ID] = rec_fmt[SMP_LEN_ID] = rec_fmt[SMP_LOOP_ID] = (void *)strt_own;\n"
            "    smp_fine(SMP_KIND0);                       /* ONESHOT: all three fine */\n"
            "    printf(\"%d %d %d\\n\", rec_fmt[SMP_STRT_ID] == stock36, rec_fmt[SMP_LEN_ID] == stock36,"
            " rec_fmt[SMP_LOOP_ID] == stock36);\n"
            "    smp_fine(-1);                              /* a machine without them: their own back */\n"
            "    printf(\"%d %d %d\\n\", rec_fmt[SMP_STRT_ID] == (void *)strt_own, rec_fmt[SMP_LEN_ID] == (void *)strt_own,"
            " rec_fmt[SMP_LOOP_ID] == (void *)strt_own);\n"
            "    return 0;\n}\n")


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_fine_positions_take_stocks_two_decimal_text_not_our_hz(monkeypatch, tmp_path):
    """main's bug (2026-11-14): with the option on, smp_fine gave STRT/LEN/LOOP record 36's formatter, which stu_poll
    has made our Hz text, and handed their own back only while 36 still held what it gave. They take stock's own
    two-decimal formatter (stock 1.12's at record 36, the units table's), and get their own back when the machine
    has no fine positions"""
    assert MU.STOCK_UNITS[36][3] == 0x400E305A                               # stock 1.12's two-decimal one
    prog = _fine_prog(_header(monkeypatch, True), WP.smp_c_header())
    c = tmp_path / "f.c"
    c.write_text(prog)
    exe = tmp_path / "f"
    subprocess.run(["cc", "-O1", "-w", "-o", str(exe), str(c)], check=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.split("\n")
    assert out[0] == "1 1 1", "ONESHOT's STRT/LEN/LOOP: stock's two-decimal formatter, not our Hz"
    assert out[1] == "1 1 1", "their own formatters back on a machine without fine positions"
