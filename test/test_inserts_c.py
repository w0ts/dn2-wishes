"""The ColdFire side of the inserts' values (csrc/inserts/ins.c), compiled for the host: its packed words
(ins_words) are dnfw.inserts.design.pack's of the same records, bit for bit, and its instances are given
out as the DSP's pass expects (each FDN8 / XDLY slot its own, a slot past the last FULL: sent as OFF)."""

from __future__ import annotations

import pathlib
import random
import shutil
import subprocess

import pytest

from dnfw.inserts import design as D

ROOT = pathlib.Path(__file__).resolve().parent.parent
HARNESS = r"""
#include <stdio.h>
typedef unsigned int u32;
typedef unsigned char u8;
void *wr_screen_obj = 0;
int smp_overlay_dirty = 0;
const char *mu_ins(int type, int knob, int k) { return 0; }      /* the page's draw (ins_draw) is not run here */
int smp_values_held(void) { return 0; }
void wpop_offer(int slot, const char *label, int n, int cur, const char *(*name)(int, int), const char *(*tag)(int, int), int arg) {}
extern void ins_set_record(int t, int j, const u8 *f);
extern void ins_loaded(void);
extern void ins_words(u32 *w);
extern void ins_record(int t, int j, u8 *f);
int main(void)
{
    unsigned v;
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < 2; j++) {
            u8 f[8];
            for (int k = 0; k < 8; k++) {
                if (scanf("%u", &v) != 1)
                    return 2;
                f[k] = (u8)v;
            }
            ins_set_record(t, j, f);
        }
    ins_loaded();
    u32 w[58];
    ins_words(w);
    for (int k = 0; k < 58; k++)
        printf("%u\n", w[k]);
    for (int t = 0; t < 16; t++)
        for (int j = 0; j < 2; j++) {
            u8 f[8];
            ins_record(t, j, f);
            for (int k = 0; k < 8; k++)
                printf("%u\n", f[k]);
        }
    return 0;
}
"""


@pytest.fixture(scope="module")
def exe(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("insc")
    (d / "h.c").write_text(HARNESS)
    out = d / "insc"
    r = subprocess.run([cc, "-O1", "-w", "-Dsection(x)=aligned(4)", "-o", str(out), str(d / "h.c"),
                        str(ROOT / "csrc" / "inserts" / "ins.c")], capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr[-2000:])
    return out


def run(exe, recs: list[list[int]]):
    text = "\n".join(str(x) for r in recs for x in r)
    r = subprocess.run([str(exe)], input=text, capture_output=True, text=True, check=True)
    v = [int(x) for x in r.stdout.split()]
    return v[:58], [v[58 + 8 * i:58 + 8 * i + 8] for i in range(D.RECORDS)]


def expected(recs):
    """what the DSP must get: the record's type with its instance (FDN8 / XDLY: given out in record
    order, the lowest free; none left: the record OFF), MIX, the knobs"""
    used = {D.FDN8: 0, D.XDLY: 0}
    n = {D.FDN8: D.FDN8_INSTANCES, D.XDLY: D.XDLY_INSTANCES}
    out = []
    for r in recs:
        y = r[0] if r[0] < len(D.NAMES) else 0
        f0 = y
        if y in n:
            if used[y] < n[y]:
                f0 = y | used[y] << D.TYPE_BITS
                used[y] += 1
            else:
                f0 = 0
        knobs = [x & 0x7F for x in r[2:8]]
        out += [f0, r[1] & 0x7F] + knobs
    return out


def test_words_are_design_pack(exe):
    rnd = random.Random(3)
    for _ in range(5):
        recs = [[rnd.choice(range(len(D.NAMES)))] + [rnd.randrange(128) for _ in range(7)]
                for _ in range(D.RECORDS)]
        w, back = run(exe, recs)
        assert w[2:] == D.pack(expected(recs), 0)[2:]
        assert w[1] == 0
        assert back == [[r[0]] + r[1:] for r in recs]          # the record as saved: type, MIX, knobs (an old SUB's DRY kept)


def test_instances_full_after_the_last(exe):
    recs = [[D.FDN8, 100, 1, 2, 3, 4, 5, 6] for _ in range(D.RECORDS)]
    w, _ = run(exe, recs)
    table = D.unpack(w[2:])
    sent = [table[8 * i] for i in range(D.RECORDS)]
    assert sent[:D.FDN8_INSTANCES] == [D.FDN8 | k << D.TYPE_BITS for k in range(D.FDN8_INSTANCES)]
    assert sent[D.FDN8_INSTANCES:] == [0] * (D.RECORDS - D.FDN8_INSTANCES)   # FULL: OFF to the DSP


def test_unknown_type_is_off(exe):
    recs = [[len(D.NAMES), 100, 1, 2, 3, 4, 5, 6]] + [[0] * 8 for _ in range(D.RECORDS - 1)]   # (13 until JUNO)
    w, back = run(exe, recs)
    assert D.unpack(w[2:])[0] == 0 and back[0][0] == 0


def test_knobs_off_the_page_are_still_saved_and_sent(exe):
    """2026-11-11: SUB's LEV and DRY, HARM's and RING's LEV are no knobs now; an old project's values play as before"""
    recs = [[D.SUB, 90, 10, 20, 30, 40, 99, 6], [D.HARM, 80, 1, 2, 3, 4, 77, 6], [D.RING, 70, 1, 2, 3, 66, 5, 6]]
    recs += [[0] * 8 for _ in range(D.RECORDS - 3)]
    w, back = run(exe, recs)
    assert D.unpack(w[2:])[:24] == [D.SUB, 90, 10, 20, 30, 40, 99, 6, D.HARM, 80, 1, 2, 3, 4, 77, 6, D.RING, 70, 1, 2, 3, 66, 5, 6]
    assert back[:3] == recs[:3]


def test_new_sub_starts_without_the_dry():
    src = (ROOT / "csrc" / "inserts" / "ins.c").read_text()
    assert "{100, 85, 59, 0, SUB_DRY, 0}" in src and "#define SUB_DRY   0 " in src
    assert '{"BAND", "TONE", "OCT", "", "", ""}' in src      # compact: place k is stored field k + 1 (test_ins_sub_compact.py)
