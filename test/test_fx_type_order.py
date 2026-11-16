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


@pytest.fixture(scope="module")
def table(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("fxt")
    (d / "h.c").write_text(HARNESS)
    out = d / "h"
    r = subprocess.run([cc, "-O1", "-w", "-Dsection(x)=aligned(4)", "-o", str(out), str(d / "h.c"),
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
