"""SUB's knob places are compact (2026-11-11, the User): BAND, TONE, OCT sit on B, C, D, the hidden LEV (stored field 0)
and DRY (field 4) stay where the DSP reads them. csrc/inserts/ins.c compiled for the host (its hardware macros and
stock's widgets stubbed): the page draw, each knob's edit, and the words / record an old project gives."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "csrc" / "inserts" / "ins.c").read_text()
HARNESS = r"""
#include <stdio.h>
#include <string.h>
static void rec_knob(int s, int v);
static void rec_label(int s, const char *t);
static void wg_choice(void *c, int s, const char *t) {}
static void wg_knob(void *c, int s, int v) { rec_knob(s, v); }
static void wg_label(void *c, int s, const char *t) { rec_label(s, t); }
int smp_values_held(void) { return 0; }
const char *mu_ins(int type, int knob, int k) { static char b[32]; sprintf(b, "u%d.%d=%d", type, knob, k); return b; }
void wpop_offer(int a, const char *b, int c, int d, const char *(*e)(int, int), const char *(*f)(int, int), int g) {}
int smp_overlay_dirty; void *wr_screen_obj;
static u8 ui_track;
static int cell_v[8]; static char cell_l[8][32];
static void rec_knob(int s, int v) { cell_v[s] = v; }
static void rec_label(int s, const char *t) { strncpy(cell_l[s], t, 31); }
#include "ins_host.c"
int main(void)
{
    ui_track = 0; ins_defaults();
    /* an old project: SUB in slot (0,0), LEV 11, BAND 22, TONE 33, OCT 44, DRY 55 */
    u8 r[8] = {9, 100, 11, 22, 33, 44, 55, 0};
    ins_set_record(0, 0, r);
    ins_up = 1;
    ins_draw(0);
    for (int s = 1; s <= 6; s++) printf("cell %d %d [%s]\n", s, cell_v[s], cell_l[s]);
    for (int k = 2; k <= 7; k++) {
        turn(k, 1);
        u8 f[8]; ins_record(0, 0, f);
        printf("turn %d %d %d %d %d %d %d\n", k, f[2], f[3], f[4], f[5], f[6], f[7]);
        ins_set_record(0, 0, r);
    }
    u32 w[58]; ins_words(w);
    printf("w %u %u %u %u\n", w[2] & 0x7F, w[2] >> 7 & 0x7F, w[2] >> 14 & 0x7F, w[2] >> 21 & 0x7F);
    u8 f[8]; ins_record(0, 0, f);
    printf("rec %d %d %d %d %d\n", f[2], f[3], f[4], f[5], f[6]);
    ins_up = 2; ins_draw(0);        /* slot 1 is OFF */
    return 0;
}
"""


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("subc")
    src = SRC.replace("(*(volatile u8 *)0x42432A6Cu)", "ui_track")
    src = src.replace('#include "../waverider/widgets.h"', "")
    src = src.replace("#define SET_PIXEL ((void (*)(void *, int, int, int))0x40113E70u)", "#define SET_PIXEL(c, x, y, on) ((void)0)")
    src = src.replace("#define PAGE_DOTS ((void (*)(void *, void *, int, int, int))0x4006598Au)", "#define PAGE_DOTS(a, b, c, d, e) ((void)0)")
    (d / "ins_host.c").write_text(src)
    (d / "h.c").write_text("typedef unsigned int u32; typedef unsigned char u8;\n" + HARNESS)
    exe = d / "h"
    r = subprocess.run([cc, "-O0", "-w", "-Dsection(x)=aligned(4)", "-I", str(d), "-o", str(exe), str(d / "h.c")],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr[-3000:])
    return subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.splitlines()


def test_page_has_no_gap(out):
    cells = [ln for ln in out if ln.startswith("cell")]
    assert cells[0] == "cell 1 22 [BAND]" and cells[1] == "cell 2 33 [TONE]" and cells[2] == "cell 3 44 [OCT]"
    assert cells[3].split()[2:] == ["0", "[]"] or "[" not in cells[3] or cells[3].endswith("[]")


def test_each_knob_edits_its_stored_field(out):
    t = {int(ln.split()[1]): list(map(int, ln.split()[2:])) for ln in out if ln.startswith("turn")}
    assert t[2] == [11, 23, 33, 44, 55, 0]      # B: BAND, field 1
    assert t[3] == [11, 22, 34, 44, 55, 0]      # C: TONE, field 2
    assert t[4] == [11, 22, 33, 45, 55, 0]      # D: OCT, field 3
    assert t[5] == [11, 22, 33, 44, 55, 0] and t[6] == [11, 22, 33, 44, 55, 0] and t[7] == [11, 22, 33, 44, 55, 0]   # no knob there: nothing moves


def test_stored_values_unchanged_for_an_old_project(out):
    assert "w 9 100 11 22" in out and "rec 11 22 33 44 55" in out    # the DSP's words and the saved record by position
