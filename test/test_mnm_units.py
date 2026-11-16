"""The Monomachine-style machines' value readout (csrc/waverider/md_page.c mnm_unit_text, tables from
dnfw.mnm.units): 2026-11-10, the User: no parameter of ours may show a bare 0..127. Every control of DRONE and
ANALOG 2 that is not an empty place, a named choice or the semitone widget has a unit; the C formatter,
compiled natively on the generated tables, fits the cell's four characters for every knob and ends in a
unit mark."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

from dnfw.mnm import machines as MM
from dnfw.waverider import pages as WP

ROOT = pathlib.Path(__file__).resolve().parent.parent
MINE = ("DRONE", "ANALOG2")


def _rows():
    for mi, M in enumerate(MM.CF_MACHINES):
        if M.NAME in MINE:
            yield mi, M


def test_every_control_has_a_unit_or_a_name():
    kinds, _at, _cv = WP._mnm_units.tables(MM.CF_MACHINES, WP.mnm_pnames)
    for mi, M in _rows():
        for j, name in enumerate(WP.mnm_pnames(M)):
            if name == "---":
                continue
            choice = (M.NAME, name) in WP.MNM_WIDGET or name in WP.MNM_CHOICES.get(M.NAME, {})
            assert choice or kinds[mi][j] & 127, f"{M.NAME} {name} would show a bare 0..127"


@pytest.mark.skipif(shutil.which("cc") is None, reason="no C compiler")
def test_the_formatter_fits_four_characters(tmp_path):
    src = (ROOT / "csrc/waverider/md_page.c").read_text()
    a, b = src.index("static int ucat"), src.index("static int mnm_choice_count")
    hdr = WP.mnm_c_header()
    keep = [ln for ln in hdr.splitlines()
            if ln.startswith(("#define MNM_N", "#define MNM_J", "enum { MU_", "static const unsigned char mnm_unit", "static const unsigned char ins_unit", "static const unsigned char flt_unit", "static const short mnm_curves"))]
    prog = ("#include <stdio.h>\n#define MNM_J 16\n" + "\n".join(ln for ln in keep if not ln.startswith("#define MNM_J"))
            + "\n" + src[a:b].replace("__attribute__((section(\".data\")))", "")
            + "\nint main(void){for(int mi=0;mi<MNM_N;mi++)for(int j=0;j<16;j++)for(int k=0;k<128;k++){"
              "const char*t=mnm_unit_text(mi,j,k);if(t)printf(\"%d %d %d %s\\n\",mi,j,k,t);}"
              "for(int w=0;w<9;w++)for(int k=0;k<128;k++){const char*t=mu_flt(w,k);if(t)printf(\"f%d 0 %d %s\\n\",w,k,t);}"
              "for(int ty=0;ty<13;ty++)for(int kn=0;kn<8;kn++)for(int k=0;k<128;k++){"
              "const char*t=mu_ins(ty,kn,k);if(t)printf(\"i%d %d %d %s\\n\",ty,kn,k,t);}return 0;}\n")
    c = tmp_path / "u.c"
    c.write_text(prog)
    exe = tmp_path / "u"
    subprocess.run(["cc", "-O1", "-o", str(exe), str(c)], check=True)
    out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()
    assert out
    seen = set()
    ins_seen = set()
    for ln in out:
        mi, j, k, txt = ln.split(" ", 3)
        assert 1 <= len(txt) <= 4, (ln,)
        assert not txt.isdigit(), f"bare number: {ln}"
        if mi.startswith("f"):
            continue
        if mi.startswith("i"):
            ins_seen.add((int(mi[1:]), int(j)))
        else:
            seen.add((int(mi), int(j)))
    for ty in range(1, 13):                         # every insert type: its knobs and the MIX have a unit
        from dnfw.inserts import design as ID
        from dnfw.mnm import units as MU
        for kn in MU.INS_UNITS[MU.INS_TYPES[ty]]:
            assert (ty, kn) in ins_seen, (ID.NAMES[ty], kn)
        assert (ty, 7) in ins_seen
    for mi, M in _rows():
        kinds, _a, _c = WP._mnm_units.tables(MM.CF_MACHINES, WP.mnm_pnames)
        for j, name in enumerate(WP.mnm_pnames(M)):
            if kinds[mi][j] & 127:
                assert (mi, j) in seen
