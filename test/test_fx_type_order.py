"""The Reverb / Delay page's TYPE lists STOCK first (2026-11-11, the User): the knob walks STOCK, FDN8, LONG
(delay: STOCK, XDLY) while the stored values keep their meaning (reverb 0 FDN8, 1 STOCK, 2 LONG; delay
0 XDLY, 1 STOCK): csrc/fdn8/ui.c rvt_step, csrc/xdly/ui.c dlt_step, compiled for the host."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HARNESS = r"""
#include <stdio.h>
void wpop_offer(int a, const char *b, int c, int d, const char *(*e)(int, int), const char *(*f)(int, int), int g) {}
int wpop_slot_of(int x, int y) { return 0; }
const char *mu_ins(int type, int knob, int k) { return 0; }
void fxp_seen(int page, int ours) {}
extern int rvt_step(int old0, int d);
extern int dlt_step(int old0, int d);
int main(void)
{
    for (int old = 0; old <= 3; old++)
        for (int d = -1; d <= 1; d += 2)
            printf("r %d %d %d\n", old, d, rvt_step(old << 8 | 0x40, d) >> 8);
    for (int old = 0; old <= 1; old++)
        for (int d = -1; d <= 1; d += 2)
            printf("d %d %d %d\n", old, d, dlt_step(old << 8, d) >> 8);
    return 0;
}
"""


def _rec_base() -> str:
    """-D for where our C reads stock's parameter records: the build's own value (dnfw.waverider.cpage passes
    dnfw.waverider.pages.lfo4_moved(); lfo4 moves the table, 2026-11-16 lfo4112)"""
    from dnfw.waverider import pages
    return f"-DREC_BASE={pages.lfo4_moved()['REC_BASE']:#x}u"


@pytest.fixture(scope="module")
def table(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("fxt")
    (d / "h.c").write_text(HARNESS)
    out = d / "h"
    r = subprocess.run([cc, "-O1", "-w", "-Dsection(x)=aligned(4)", _rec_base(), "-o", str(out), str(d / "h.c"),
                        str(ROOT / "csrc" / "fdn8" / "ui.c"), str(ROOT / "csrc" / "xdly" / "ui.c")],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr[-2000:])
    rows = subprocess.run([str(out)], capture_output=True, text=True, check=True).stdout.splitlines()
    return {(k, int(a), int(b)): int(c) for k, a, b, c in (ln.split() for ln in rows)}


STOCK, FDN8, LONG = 1, 0, 2          # the stored values (kits, frame, DSP)


def test_reverb_knob_walks_stock_fdn8_long(table):
    assert table["r", STOCK, 1] == FDN8 and table["r", FDN8, 1] == LONG and table["r", LONG, 1] == LONG
    assert table["r", LONG, -1] == FDN8 and table["r", FDN8, -1] == STOCK and table["r", STOCK, -1] == STOCK


def test_reverb_stale_value_counts_as_stock(table):
    assert table["r", 3, -1] == STOCK and table["r", 3, 1] == FDN8


def test_delay_knob_walks_stock_xdly(table):
    XDLY = 0
    assert table["d", STOCK, 1] == XDLY and table["d", XDLY, 1] == XDLY
    assert table["d", XDLY, -1] == STOCK and table["d", STOCK, -1] == STOCK


def test_every_old_value_keeps_its_type():
    """the lists in the files: position 0 is STOCK, and the stored values were not renumbered"""
    f = (ROOT / "csrc" / "fdn8" / "ui.c").read_text()
    x = (ROOT / "csrc" / "xdly" / "ui.c").read_text()
    assert '{"STOCK", "FDN8", "LONG"}' in f and '{"STOCK", "XDLY"}' in x
    assert 'rvt_pos[rvt_seen], rvt_pop_name' in f and '1 - dlt_seen, dlt_pop_name' in x      # the popup's cursor: list position
    assert 't == 1 ? "STOCK" : t == 2 ? "LONG" : "FDN8"' in f                     # the value text, unchanged
    assert '((v >> 8) & 0xFF) ? "STOCK" : "XDLY"' in x


QUANT = r"""
#include <stdio.h>
typedef unsigned int u32;
typedef unsigned char u8;
void wpop_offer(int a, const char *b, int c, int d, const char *(*e)(int, int), const char *(*f)(int, int), int g) {}
int wpop_slot_of(int x, int y) { return 0; }
void fxp_seen(int page, int ours) {}
const char *mu_ins(int type, int knob, int k) { return 0; }
extern int rvt_step(int old0, int d);
extern int dlt_step(int old0, int d);
int smp_knob_d, smp_pop_knob;
u32 smp_knob_seq, smp_key_seq, frames_now, smp_knob_at;
%s
int main(void)
{
    int id, old, d, knob, kseq, keyseq;
    unsigned age;
    while (scanf("%%d %%d %%d %%d %%d %%d %%u", &id, &old, &value_in, &d, &knob, &kseq, &age) == 7) {
        u16 w = (u16)(old << 8);
        smp_knob_d = d; smp_pop_knob = knob; smp_knob_seq = kseq %% 100; smp_key_seq = (kseq / 100) * 10;
        frames_now = 100000; smp_knob_at = frames_now - age;
        printf("%%d\n", fx_type_quant((u8 *)&w, 0, value_in << 8, id));
    }
    return 0;
}
"""


def _quant_exe(tmp_path):
    import re
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    src = (ROOT / "csrc" / "sampler" / "fmt.c").read_text()
    a = src.index("int fx_type_quant(")
    fn = src[a:src.index("\n}\n", a) + 3].replace("*(volatile u32 *)0x4058F8D4u", "frames_now")
    fn = fn.replace("*(volatile u16 *)", "*(u16 *)")
    prog = QUANT % fn
    prog = prog.replace("int id, old, d, knob", "int value_in, id, old, d, knob").replace("typedef unsigned char u8;", "typedef unsigned char u8; typedef unsigned short u16;")
    (tmp_path / "q.c").write_text(prog)
    out = tmp_path / "q"
    r = subprocess.run([cc, "-O1", "-w", "-Dsection(x)=aligned(4)", _rec_base(), "-o", str(out), str(tmp_path / "q.c"), str(ROOT / "csrc" / "fdn8" / "ui.c"),
                        str(ROOT / "csrc" / "xdly" / "ui.c")], capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr[-2000:])
    return out


def _quant(exe, cases):
    text = "\n".join(" ".join(map(str, c)) for c in cases)
    return [int(x) >> 8 for x in subprocess.run([str(exe)], input=text, capture_output=True, text=True, check=True).stdout.split()]


def test_the_knob_gate_is_not_a_100_ms_window(tmp_path):
    """fx_type_quant: (id, stored now, the value stock writes, knob delta, last knob 1..8, knob seq, age in frames).
    A turn of G is honoured up to 2 s after its item (the UI loop can run late on the unit: stock's raw order then
    showed through, 0 = FDN8 / XDLY at the knob's left end); not once a key was pressed (seq order), not for another
    knob, not when nothing was turned."""
    exe = _quant_exe(tmp_path)
    # reverb, STOCK stored 1, turned fully left: stock writes 0 (FDN8): we keep STOCK, at 10 ms and at 1.5 s
    assert _quant(exe, [(131, 1, 0, -30, 7, 5, 15), (131, 1, 0, -30, 7, 5, 2250)]) == [1, 1]
    # delay, STOCK, turned left: stays STOCK; right: XDLY
    assert _quant(exe, [(122, 1, 0, -30, 7, 5, 1500), (122, 1, 0, 30, 7, 5, 1500)]) == [1, 0]
    # past 2 s, another knob, no turn at all: stock's value goes through
    assert _quant(exe, [(131, 1, 0, -30, 7, 5, 3500), (131, 1, 0, -30, 3, 5, 15), (131, 1, 0, 0, 7, 5, 15),
                        (131, 1, 0, -30, 7, 0, 15), (131, 1, 0, -30, 7, 105, 15)]) == [0, 0, 0, 0, 0]   # (105: a key after the turn)
    # a sweep left to right: STOCK, FDN8, LONG (stored 1, 0, 2)
    assert _quant(exe, [(131, 1, 0, 30, 7, 5, 15), (131, 0, 2, 30, 7, 5, 15), (131, 2, 2, 30, 7, 5, 15),
                        (131, 2, 0, -30, 7, 5, 15), (131, 0, 1, -30, 7, 5, 15), (131, 1, 0, -30, 7, 5, 15)]) == [0, 2, 2, 0, 1, 1]
    # another record is never touched
    assert _quant(exe, [(124, 1, 0, -30, 7, 5, 15)]) == [0]
