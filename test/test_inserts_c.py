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
/* cv_fill lives in csrc/waverider/page.c (the firmware's one rectangle fill, 2026-11-17); the page's drawing is
 * never run here, so a stand-in only links it */
void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on) { (void)cv; (void)x0; (void)y0; (void)x1; (void)y1; (void)on; }

#include <stdio.h>
typedef unsigned int u32;
typedef unsigned char u8;
void *wr_screen_obj = 0;
int smp_overlay_dirty = 0;
const char *mu_ins(int type, int knob, int k) { return 0; }      /* the page's draw (ins_draw) is not run here */
int smp_values_held(void) { return 0; }
/* (2026-11-21, fx-icons) the FX icons' neighbours (csrc/msel/msel.c): no icon, INSERT SEL never up here */
const unsigned char *msel_icon_of(int kind, int type) { (void)kind; (void)type; return 0; }
const unsigned char *msel_fx_icon(int type) { (void)type; return 0; }
int isel_up(void) { return 0; }
void isel_draw(void *c) { (void)c; }
int ovw_fx_held(void) { return 0; }                                 /* csrc/inserts/ovw.c (the FX key held) */
unsigned int ovw_pass = 0;
void wpop_offer(int slot, const char *label, int n, int cur, const char *(*name)(int, int), const char *(*tag)(int, int), int arg) {}
void wpop_offer_mv(int slot, const char *label, int n, int cur, const char *(*name)(int, int), const char *(*tag)(int, int), int arg,
                   void (*move)(int, int)) {}   /* (v0.52: the popup's move form; the draw is not run here) */
const char *const amp_title1 = "ENV1/AMP";    /* csrc/scope/scope.c's (matrix's AMP titles; ins_header names it) */
/* (2026-11-20) the live values' neighbours: no trig held, no lock pool, no route, no line */
unsigned int sl_ins_held(unsigned int k, unsigned int j) { (void)k; (void)j; return 0x10000u; }
int sl_ins_set(unsigned int k, unsigned int j, unsigned int v) { (void)k; (void)j; (void)v; return 0; }
unsigned int mx_ins_routes(unsigned int t) { (void)t; return 0; }
unsigned char *sl_ui_pool(void) { return 0; }
const unsigned char *sl_ins_record(const unsigned char *tb, unsigned int t, unsigned int k) { (void)tb; (void)t; (void)k; return 0; }
void mv_own_knob(void *c, int x, int y, int w, unsigned int key, unsigned int slot) { (void)c; (void)x; (void)y; (void)w; (void)key; (void)slot; }
extern void ins_set_record(int t, int j, const u8 *f);
extern void ins_loaded(void);
extern void ins_words(u32 *w);
extern void ins_record(int t, int j, u8 *f);
extern void ins_tpg_words(u32 *w);
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
    u32 g[8];
    ins_tpg_words(g);
    for (int k = 0; k < 8; k++)
        printf("%u\n", g[k]);
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


def run_full(exe, recs: list[list[int]]) -> list[int]:
    """every number the harness prints: the 58 words, the 32 records as saved, the 8 TAPE PGAIN words"""
    text = "\n".join(str(x) for r in recs for x in r)
    r = subprocess.run([str(exe)], input=text, capture_output=True, text=True, check=True)
    return [int(x) for x in r.stdout.split()]


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
    f0s = []
    for r in recs:
        y = r[0] if r[0] < len(D.NAMES) else 0
        f0 = y
        if y in n:
            if used[y] < n[y]:
                f0 = y | used[y] << D.TYPE_BITS
                used[y] += 1
            else:
                f0 = 0
        if y in (D.FUZZ, D.TAPE) and r[1] & 0x80:              # FUZZ's or TAPE's AUTO: saved in MIX's bit 7, sent in field 0's bit 4
            f0 |= D.FZ_AUTO_BIT
        f0s.append(f0)
    off = mix_off(recs, f0s)
    out = []
    for r, f0, o in zip(recs, f0s, off):
        knobs = [x & 0x7F for x in r[2:8]]
        out += [0] * 8 if o else [f0, r[1] & 0x7F] + knobs
    return out


def mix_off(recs, f0s):
    """2026-11-16 (the User): a record the DSP would run (not OFF, not FULL) at MIX 0 is sent as an OFF slot's record at MIX 0,
    all eight fields 0 (its instance kept on the ColdFire), but for slot 1 a MOVER while slot 2 sends a voice insert"""
    off = [f0 & 0xF != 0 and r[1] & 0x7F == 0 for r, f0 in zip(recs, f0s)]
    for i in range(0, len(recs), 2):
        if off[i] and f0s[i] & 0xF in D.MOVERS and f0s[i + 1] & 0xF in D.BUILT and not off[i + 1]:
            off[i] = False
    return off


def test_words_are_design_pack(exe):
    rnd = random.Random(3)
    for _ in range(5):
        recs = [[rnd.choice(range(len(D.NAMES)))] + [rnd.choice((0, 0x80, rnd.randrange(256)))]
                + [rnd.randrange(128) for _ in range(6)] for _ in range(D.RECORDS)]   # MIX 0 often (2026-11-16)
        w, back = run(exe, recs)
        assert w[2:] == D.pack(expected(recs), 0)[2:]
        assert w[1] == 0
        assert back == [[r[0], r[1] if r[0] in (D.FUZZ, D.TAPE) else r[1] & 0x7F] + r[2:]
                        for r in recs]                         # the record as saved: type, MIX (bit 7 FUZZ's / TAPE's AUTO), knobs
                                                               # (an old SUB's DRY kept)


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


def test_fuzz_auto_is_saved_in_mix_bit_7_and_sent_in_field_0_bit_4(exe):
    """2026-11-13 (the User: AUTO on G for FUZZ, GATE to page 2): an old project's FUZZ (bit 7 clear) loads with AUTO off,
    as before; one saved with AUTO on comes back with it and sends field 0 = FUZZ | bit 4; GATE (field 4) unchanged"""
    recs = [[D.FUZZ, 100, 10, 20, 30, 40, 55, 66], [D.FUZZ, 0x80 | 90, 1, 2, 3, 4, 77, 88], [D.DIST, 0x80 | 70, 1, 2, 3, 4, 5, 6]]
    recs += [[0] * 8 for _ in range(D.RECORDS - 3)]
    w, back = run(exe, recs)
    got = D.unpack(w[2:])
    assert got[0:8] == [D.FUZZ, 100, 10, 20, 30, 40, 55, 66]
    assert got[8:16] == [D.FUZZ | D.FZ_AUTO_BIT, 90, 1, 2, 3, 4, 77, 88]
    assert got[16:24] == [D.DIST, 70, 1, 2, 3, 4, 5, 6]                      # bit 7 means nothing to DIST: dropped
    assert back[0] == recs[0] and back[1] == recs[1] and back[2] == [D.DIST, 70, 1, 2, 3, 4, 5, 6]


def test_fuzz_has_pgain_and_auto_on_page_1_and_gate_on_page_2():
    src = (ROOT / "csrc" / "inserts" / "ins.c").read_text()
    assert '{"DRIV", "TONE", "BIAS", "PRE", "PGAIN", AUTO_LABEL},' in src
    assert '[T_FUZZ] = {"GATE", "", "", "", "", ""},' in src
    assert "return pg ? (k == 0 ? 4 : -1) : (k < 4 ? k : k == 4 ? 5 : X_AUTO);" in src


def test_tape_pgain_is_saved_in_the_knobs_bit_7_and_sent_by_record(exe):
    """2026-11-13 (the User: PGAIN on F, AUTO on G on TAPE; AGE HISS on page 2): an old project's TAPE (no bit 7s) loads with
    PGAIN 0 dB and AUTO off, as before; PGAIN -6 dB is saved as 6-bit two's complement in K1..K6's bit 7 and sent, a byte a
    record, to design.TP_PG_DDR's words; AUTO as FUZZ's (MIX bit 7, field 0 bit 4)"""
    s = (-6) & 0x3F
    tape6 = [D.TAPE, 0x80 | 100] + [10 * (k + 1) | ((s >> k) & 1) << 7 for k in range(6)]
    recs = [[D.TAPE, 100, 10, 20, 30, 40, 50, 60], [0] * 8, [0] * 8, tape6]
    recs += [[0] * 8 for _ in range(D.RECORDS - 4)]
    text = "\n".join(str(x) for r in recs for x in r)
    r = subprocess.run([str(exe)], input=text, capture_output=True, text=True, check=True)
    v = [int(x) for x in r.stdout.split()]
    w, back, tpg = v[:58], [v[58 + 8 * i:58 + 8 * i + 8] for i in range(D.RECORDS)], v[58 + 8 * D.RECORDS:]
    got = D.unpack(w[2:])
    assert got[0:8] == [D.TAPE, 100, 10, 20, 30, 40, 50, 60]
    assert got[24:32] == [D.TAPE | D.FZ_AUTO_BIT, 100, 10, 20, 30, 40, 50, 60]
    assert back[0] == recs[0] and back[3] == tape6
    assert len(tpg) == D.TP_PG_WORDS and tpg[0] == ((-6) & 0x7F) << 24 and not any(tpg[1:])   # record 3: word 0 byte 3


def test_tape_pages_and_pgain_place():
    src = (ROOT / "csrc" / "inserts" / "ins.c").read_text()
    assert '{"DRIV", "WOW", "WRAT", "FLUT", "PGAIN", AUTO_LABEL},' in src
    assert '[T_TAPE] = {"AGE", "HISS", "", "", "", ""},' in src
    link = (ROOT / "csrc" / "sampler" / "link.c").read_text()
    assert "#define TPG_OFFSET (TABLE_READY + 0x100u)" in link and "smp_tables == 2" in link
    from dnfw.sampler import machines as SM
    assert D.TP_PG_DDR == D.POOL_DDR + SM.TABLE_READY + 0x100 and 4 * D.TP_PG_WORDS == 0x20   # the arbiter's 32 B


def test_mix_0_is_sent_off_and_keeps_its_instance(exe):
    """2026-11-16 (the User: an insert at no effect should cost nothing): a slot at MIX 0 gives the dry on the DSP (x + (wet -
    x) x 0) yet ran its type in full; the ColdFire sends it OFF. An FDN8 / XDLY keeps its instance (no FULL elsewhere), and
    its MIX and knobs are still sent and saved"""
    recs = [[D.FDN8, 0, 1, 2, 3, 4, 5, 6], [D.FDN8, 9, 1, 2, 3, 4, 5, 6], [D.FUZZ, 0x80, 1, 2, 3, 4, 5, 6],
            [D.TAPE, 0, 7, 7, 7, 7, 7, 7]] + [[0] * 8 for _ in range(D.RECORDS - 4)]
    w, back = run(exe, recs)
    table = D.unpack(w[2:])
    sent = [table[8 * i] for i in range(4)]
    assert sent == [0, D.FDN8 | 1 << D.TYPE_BITS, 0, 0]      # slot 0's FDN8 holds instance 0: slot 1's is 1
    for i in (0, 2, 3):                                       # exactly an OFF slot's record at MIX 0
        assert table[8 * i:8 * i + 8] == [0] * 8
    assert table[8 * 1 + 1] == 9
    assert back[:4] == [r[:] for r in recs[:4]]               # saved as turned


def test_mix_0_tape_sends_no_pgain_byte(exe):
    """an OFF slot's TAPE PGAIN byte is 0: a TAPE at MIX 0 sends 0 too, at MIX 1 its PGAIN"""
    for mix, want in ((0, 0), (1, 5)):
        recs = [[D.TAPE, mix] + [(5 >> k & 1) << 7 for k in range(6)]] + [[0] * 8 for _ in range(D.RECORDS - 1)]
        out = run_full(exe, recs)
        assert out[-8] & 0x7F == want


def test_mix_0_mover_in_slot_1_stays_while_slot_2_is_moved(exe):
    """slot 1 CHOR at MIX 0 with a voice insert in slot 2: slot 1 is still sent, so slot 2 stays on the bus after it
    (design.moved); with slot 2 at MIX 0 too, both go OFF"""
    for slot2_mix, want in ((50, [D.CHOR, D.DIST]), (0, [0, 0])):
        recs = [[D.CHOR, 0, 1, 2, 3, 4, 5, 6], [D.DIST, slot2_mix, 1, 2, 3, 4, 5, 6]] + \
            [[0] * 8 for _ in range(D.RECORDS - 2)]
        w, _ = run(exe, recs)
        table = D.unpack(w[2:])
        assert [table[0], table[8]] == want
        assert D.moved(table, 0) == (slot2_mix != 0)


TURN_HARNESS = r"""
/* cv_fill lives in csrc/waverider/page.c (the firmware's one rectangle fill, 2026-11-17); the page's drawing is
 * never run here, so a stand-in only links it */
void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on) { (void)cv; (void)x0; (void)y0; (void)x1; (void)y1; (void)on; }

#include <stdio.h>
typedef unsigned int u32;
typedef unsigned char u8;
unsigned char host_track = 0;
void *wr_screen_obj = 0;
int smp_overlay_dirty = 0;
const char *mu_ins(int type, int knob, int k) { return 0; }
int smp_values_held(void) { return 0; }
/* (2026-11-21, fx-icons) the FX icons' neighbours (csrc/msel/msel.c): no icon, INSERT SEL never up here */
const unsigned char *msel_icon_of(int kind, int type) { (void)kind; (void)type; return 0; }
const unsigned char *msel_fx_icon(int type) { (void)type; return 0; }
int isel_up(void) { return 0; }
void isel_draw(void *c) { (void)c; }
int ovw_fx_held(void) { return 0; }                                 /* csrc/inserts/ovw.c (the FX key held) */
unsigned int ovw_pass = 0;
void wpop_offer(int slot, const char *label, int n, int cur, const char *(*name)(int, int), const char *(*tag)(int, int), int arg) {}
void wpop_offer_mv(int slot, const char *label, int n, int cur, const char *(*name)(int, int), const char *(*tag)(int, int), int arg,
                   void (*move)(int, int)) {}
const char *const amp_title1 = "ENV1/AMP";
/* (2026-11-20) the live values' neighbours: no trig held, no lock pool, no route, no line */
unsigned int sl_ins_held(unsigned int k, unsigned int j) { (void)k; (void)j; return 0x10000u; }
int sl_ins_set(unsigned int k, unsigned int j, unsigned int v) { (void)k; (void)j; (void)v; return 0; }
unsigned int mx_ins_routes(unsigned int t) { (void)t; return 0; }
unsigned char *sl_ui_pool(void) { return 0; }
const unsigned char *sl_ins_record(const unsigned char *tb, unsigned int t, unsigned int k) { (void)tb; (void)t; (void)k; return 0; }
void mv_own_knob(void *c, int x, int y, int w, unsigned int key, unsigned int slot) { (void)c; (void)x; (void)y; (void)w; (void)key; (void)slot; }
extern int ins_up;
extern int ins_pop(u8 *it);
extern void ins_record(int t, int j, u8 *f);
extern void ins_set_record(int t, int j, const u8 *f);
extern void ins_loaded(void);
static void knob(int code, int delta)          /* an encoder turn as rec.c gives it (IT_KNOB, code, delta at +8) */
{
    u8 it[12] = {1, 0, 0, 0, 0, 0, 0, (u8)code, (u8)(signed char)delta, 0, 0, 0};
    ins_pop(it);
}
static void show(void)
{
    u8 f[8];
    ins_record(3, 0, f);
    printf("%u %u\n", f[0], f[1]);
}
int main(void)
{
    u8 rec[8] = {1, 90, 1, 2, 3, 4, 5, 6};      /* a loaded project: track 4's slot 1 FUZZ at MIX 90 */
    ins_set_record(3, 0, rec);
    ins_loaded();
    host_track = 3;
    ins_up = 1;
    show();                                     /* loaded: MIX 90 kept */
    knob(8, -5); show();                        /* MIX turned: 85 */
    knob(1, 12); show();                        /* M.SEL to the next type: MIX 0 */
    knob(8, 7); show();                         /* MIX up: 7 */
    knob(1, 1); show();                         /* M.SEL moved within the same type's band: MIX kept */
    return 0;
}
"""


def test_a_type_picked_starts_at_mix_0_a_loaded_one_keeps_its_mix(tmp_path):
    """2026-11-16 (the User, A): every M.SEL pick of another type sets MIX 0 (no effect, sent OFF, no DSP); a project's
    saved MIX is kept; MIX turns from there. ins.c is compiled for the host with UI_TRACK on a host variable"""
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    src = (ROOT / "csrc" / "inserts" / "ins.c").read_text()
    line = "#define UI_TRACK  (*(volatile u8 *)0x42432A6Cu)"
    assert line in src
    (tmp_path / "ins_host.c").write_text(src.replace(line, "extern unsigned char host_track;\n#define UI_TRACK host_track"))
    (tmp_path / "h.c").write_text(TURN_HARNESS)
    out = tmp_path / "turn"
    r = subprocess.run([cc, "-O1", "-w", "-Dsection(x)=aligned(4)", "-I", str(ROOT / "csrc" / "inserts"), "-o", str(out),
                        str(tmp_path / "h.c"), str(tmp_path / "ins_host.c")], capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr[-2000:])
    rows = [tuple(int(x) for x in ln.split()) for ln in subprocess.run([str(out)], capture_output=True, text=True,
                                                                        check=True).stdout.splitlines()]
    assert rows[0] == (D.FUZZ, 90) and rows[1] == (D.FUZZ, 85)
    assert rows[2][0] != D.FUZZ and rows[2][1] == 0
    assert rows[3] == (rows[2][0], 7)
    assert rows[4] == rows[3]


AUTO_HARNESS = r"""
void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on) { (void)cv; (void)x0; (void)y0; (void)x1; (void)y1; (void)on; }

#include <stdio.h>
typedef unsigned int u32;
typedef unsigned char u8;
unsigned char host_track = 0;
void *wr_screen_obj = 0;
int smp_overlay_dirty = 0;
const char *mu_ins(int type, int knob, int k) { return 0; }
int smp_values_held(void) { return 0; }
/* (2026-11-21, fx-icons) the FX icons' neighbours (csrc/msel/msel.c): no icon, INSERT SEL never up here */
const unsigned char *msel_icon_of(int kind, int type) { (void)kind; (void)type; return 0; }
const unsigned char *msel_fx_icon(int type) { (void)type; return 0; }
int isel_up(void) { return 0; }
void isel_draw(void *c) { (void)c; }
int ovw_fx_held(void) { return 0; }
unsigned int ovw_pass = 0;
void wpop_offer_mv(int slot, const char *label, int n, int cur, const char *(*name)(int, int), const char *(*tag)(int, int), int arg,
                   void (*move)(int, int)) {}
const char *const amp_title1 = "ENV1/AMP";
/* (2026-11-20) the live values' neighbours: no trig held, no lock pool, no route, no line */
unsigned int sl_ins_held(unsigned int k, unsigned int j) { (void)k; (void)j; return 0x10000u; }
int sl_ins_set(unsigned int k, unsigned int j, unsigned int v) { (void)k; (void)j; (void)v; return 0; }
unsigned int mx_ins_routes(unsigned int t) { (void)t; return 0; }
unsigned char *sl_ui_pool(void) { return 0; }
const unsigned char *sl_ins_record(const unsigned char *tb, unsigned int t, unsigned int k) { (void)tb; (void)t; (void)k; return 0; }
void mv_own_knob(void *c, int x, int y, int w, unsigned int key, unsigned int slot) { (void)c; (void)x; (void)y; (void)w; (void)key; (void)slot; }
extern int ins_up;
extern u8 ins_selv[16][2];
extern int ins_pop(u8 *it);
extern void ins_record(int t, int j, u8 *f);
extern void ins_set_record(int t, int j, const u8 *f);
extern void ins_loaded(void);
extern void ins_defaults(void);
extern void ins_words(u32 *w);
extern int ins_knob_reset(int k);
extern void ins_func_push(void);
static void item(int kind, int code, int b8, int flags)
{
    u8 it[12] = {(u8)kind, 0, 0, 0, 0, 0, 0, (u8)code, (u8)b8, 0, 0, (u8)flags};
    ins_pop(it);
}
/* commands on stdin, one a line: d (a NEW project), u N (ins_up), t T (the track), m V (M.SEL turned to V), k CODE D
 * (knob CODE turned D), f / F (FUNC pressed / let go), s (ins_func_push), x K (ins_knob_reset(K): printed),
 * l T J F0..F7 (a project's record loaded), r (the slot's record as saved: printed), w (the 58 words: printed) */
int main(void)
{
    char c;
    while (scanf(" %c", &c) == 1) {
        int a, b, j = (ins_up - 1) & 1;
        if (c == 'd') ins_defaults();
        else if (c == 'u' && scanf("%d", &a) == 1) ins_up = a;
        else if (c == 't' && scanf("%d", &a) == 1) host_track = (u8)a;
        else if (c == 'm' && scanf("%d", &a) == 1) item(1, 1, a - ins_selv[host_track][j], 0);
        else if (c == 'k' && scanf("%d %d", &a, &b) == 2) item(1, a, b, 0);
        else if (c == 'f') item(0, 17, 0, 1);
        else if (c == 'F') item(0, 17, 0, 0x10);
        else if (c == 's') ins_func_push();
        else if (c == 'x' && scanf("%d", &a) == 1) printf("x %d\n", ins_knob_reset(a));
        else if (c == 'l') {
            unsigned v[10];
            u8 f[8];
            for (int k = 0; k < 10; k++)
                if (scanf("%u", &v[k]) != 1)
                    return 2;
            for (int k = 0; k < 8; k++)
                f[k] = (u8)v[2 + k];
            ins_set_record((int)v[0], (int)v[1], f);
            ins_loaded();
        } else if (c == 'r') {
            u8 f[8];
            ins_record(host_track, j, f);
            printf("r %u %u %u %u %u %u %u %u\n", f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7]);
        } else if (c == 'w') {
            u32 w[58];
            ins_words(w);
            printf("w");
            for (int k = 0; k < 58; k++)
                printf(" %u", w[k]);
            printf("\n");
        } else
            return 3;
    }
    return 0;
}
"""
DISTORTIONS = (D.DIST, D.FOLD, D.HARM, D.FUZZ, D.TAPE)


@pytest.fixture(scope="module")
def auto_exe(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("insauto")
    src = (ROOT / "csrc" / "inserts" / "ins.c").read_text()
    line = "#define UI_TRACK  (*(volatile u8 *)0x42432A6Cu)"
    assert line in src
    (d / "ins_host.c").write_text(src.replace(line, "extern unsigned char host_track;\n#define UI_TRACK host_track"))
    (d / "h.c").write_text(AUTO_HARNESS)
    out = d / "auto"
    r = subprocess.run([cc, "-O1", "-w", "-Dsection(x)=aligned(4)", "-I", str(ROOT / "csrc" / "inserts"), "-o", str(out),
                        str(d / "h.c"), str(d / "ins_host.c")], capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr[-2000:])
    return out


def band_middle(y: int) -> int:
    """M.SEL's value in the middle of type Y's band (ins.c POS: the display order)"""
    import re
    src = (ROOT / "csrc" / "inserts" / "ins.c").read_text()
    pos = [int(x) for x in re.search(r"static const u8 POS\[TYPES\] = \{([^}]*)\}", src).group(1).split(",")]
    return (pos[y] * 128 + 64) // len(pos)


def auto_of(rec: list[int]) -> bool:
    """a saved record's AUTO: FUZZ's and TAPE's MIX bit 7, DIST's FOLD's HARM's K6 (field 5) above 63"""
    return bool(rec[1] & 0x80) if rec[0] in (D.FUZZ, D.TAPE) else rec[7] > 63


def drive(exe, cmds: list[str]) -> list[list[int]]:
    r = subprocess.run([str(exe)], input="\n".join(cmds) + "\n", capture_output=True, text=True)
    assert r.returncode == 0, (r.returncode, r.stderr)
    return [[int(x) for x in ln.split()[1:]] for ln in r.stdout.splitlines()]


def test_a_distortion_picked_starts_with_auto_off(auto_exe):
    """2026-11-19 (the User: "auto gain should be off by default on our disto FXs"): every M.SEL pick of DIST, FOLD, HARM,
    FUZZ or TAPE gives AUTO OFF, also on a slot that held that type with AUTO ON before (a slot keeps every type's knobs:
    the ON came back on the pick), and TAPE picked after a FUZZ with AUTO ON (the two share one AUTO a slot)"""
    pre = ["d", "t 3", "u 1"]
    fresh = drive(auto_exe, pre + [x for y in DISTORTIONS for x in (f"m {band_middle(y)}", "r")])
    assert [r[0] for r in fresh] == list(DISTORTIONS)
    assert [auto_of(r) for r in fresh] == [False] * 5, fresh
    on_each = [x for y in DISTORTIONS for x in (f"m {band_middle(y)}", "k 7 1", "r")]
    again = [x for y in DISTORTIONS for x in ("m 0", f"m {band_middle(y)}", "r")]
    rows = drive(auto_exe, pre + on_each + again)
    assert [auto_of(r) for r in rows[:5]] == [True] * 5, rows[:5]        # AUTO turned ON on each (knob G right)
    assert [r[0] for r in rows[5:]] == list(DISTORTIONS)
    assert [auto_of(r) for r in rows[5:]] == [False] * 5, rows[5:]      # picked again: OFF
    fz_tp = drive(auto_exe, pre + [f"m {band_middle(D.FUZZ)}", "k 7 1", "r", f"m {band_middle(D.TAPE)}", "r"])
    assert auto_of(fz_tp[0]) and fz_tp[1][0] == D.TAPE and not auto_of(fz_tp[1])
    for y in DISTORTIONS:                                                 # M.SEL moved inside the type's band: no pick
        within = drive(auto_exe, pre + [f"m {band_middle(y)}", "k 7 1", f"m {band_middle(y) + 1}", "r"])
        assert within[0][0] == y and auto_of(within[0])


def test_a_saved_auto_on_stays_on_after_a_reload(auto_exe):
    """a project's AUTO ON loads ON, is sent ON and saved back ON (no conversion), and stays ON while other knobs turn"""
    recs = {D.DIST: [D.DIST, 90, 1, 2, 3, 4, 5, 127], D.FOLD: [D.FOLD, 90, 1, 2, 3, 4, 5, 127],
            D.HARM: [D.HARM, 90, 1, 2, 3, 4, 5, 127], D.FUZZ: [D.FUZZ, 0x80 | 90, 1, 2, 3, 4, 5, 6],
            D.TAPE: [D.TAPE, 0x80 | 90, 1, 2, 3, 4, 5, 6]}
    for y, rec in recs.items():
        rows = drive(auto_exe, ["t 5", "u 2", "l 5 1 " + " ".join(map(str, rec)), "r", "w", "k 8 -3", "k 3 2", "r"])
        assert rows[0] == rec and auto_of(rows[0])
        table = D.unpack(rows[1][2:])
        sent = table[8 * 11:8 * 11 + 8]                                    # record 2 t + j = 11
        assert (sent[0] & D.FZ_AUTO_BIT) if y in (D.FUZZ, D.TAPE) else sent[7] == 127
        assert auto_of(rows[2]) and rows[2][1] & 0x7F == 87


def test_func_long_push_resets_auto_to_off(auto_exe):
    """FUNC + long push on an INSERT page's knob (csrc/matrix/routes_pop.c mxp_poll -> ins_knob_reset): the place back to its
    default, AUTO (G, encoder 6) to OFF on every distortion; DRIV (B) to the type's DEFAULT; M.SEL (A) and MIX (H) untouched;
    no INSERT page up: not ours (0)"""
    for y in DISTORTIONS:
        rows = drive(auto_exe, ["d", "t 2", "u 1", f"m {band_middle(y)}", "k 8 50", "k 7 1", "k 2 9", "r", "x 6", "r",
                                "x 1", "r", "x 0", "x 7", "r", "u 0", "x 6"])
        on, x6, after, x1, drv, x0, x7, last, x_off = rows
        assert auto_of(on) and x6 == [1] and not auto_of(after), (y, rows)
        assert after[1] & 0x7F == on[1] & 0x7F and after[2:7] == on[2:7]   # nothing else moved (MIX, K1..K5)
        assert x1 == [1] and drv[2] == on[2] - 9                          # DRIV back to its default (turned +9 from it)
        assert x0 == [0] and x7 == [0] and last == drv and last[1] & 0x7F == 50
        assert x_off == [0]


def test_func_push_on_a_two_page_insert_does_not_switch_pages(auto_exe):
    """FUNC + push is the routes popup's (mxp_pop takes the push before ins_pop sees it): FUNC's release must not then
    count as a FUNC tap and switch FUZZ's or TAPE's page (the reset above would land on page 2); a plain FUNC tap still
    switches. Seen through knob B: page 1 DRIV (field 0), page 2 FUZZ's GATE / TAPE's AGE (field 4)"""
    for y in (D.FUZZ, D.TAPE):
        rows = drive(auto_exe, ["d", "t 1", "u 1", f"m {band_middle(y)}", "r", "f", "s", "F", "k 2 5", "r",
                                "f", "F", "k 2 5", "r"])
        start, pushed, tapped = rows
        assert pushed[2] == start[2] + 5 and pushed[6] == start[6]        # still page 1: DRIV moved
        assert tapped[2] == pushed[2] and tapped[6] == pushed[6] + 5      # a FUNC tap: page 2
