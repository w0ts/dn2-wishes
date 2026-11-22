"""The send pages' second page (csrc/fxpage, docs/fxpage.md): the ColdFire's words for the DSP are
dnfw.xdly.design.derive's, bit for bit, for every knob of every parameter; the generated header is fresh; a
project that never touched the page sends exactly the engine's constants."""

from __future__ import annotations

import pathlib
import shutil
import struct
import subprocess
import sys

import pytest

from dnfw.fdn8 import design as FD
from dnfw.xdly import design as XD

ROOT = pathlib.Path(__file__).resolve().parent.parent
HARNESS = r"""
/* cv_fill lives in csrc/waverider/page.c (the firmware's one rectangle fill, 2026-11-17); the page's drawing is
 * never run here, so a stand-in only links it (as test_inserts_c) */
void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on) { (void)cv; (void)x0; (void)y0; (void)x1; (void)y1; (void)on; }

#include <stdio.h>
typedef unsigned int u32;
typedef unsigned char u8;
/* the kit wishes record (csrc/wishes): no kit has a field here */
volatile u32 wish_edits = 0;
int wish_get(u32 item, u32 tag, unsigned char *out, u32 max) { return -1; }
int wish_put(u32 item, u32 tag, const unsigned char *v, u32 vlen) { return 0; }
u32 host_kit = 0x1000;

int smp_overlay_dirty = 0;
int dlt_state = -1, rvt_state = -1;     /* csrc/xdly/ui.c, csrc/fdn8/ui.c: the send pages' TYPE is ours (1) */
u32 ins_edits = 0;
u32 mtr_func_ended = 0;                 /* csrc/meter/meter.c: this FUNC release ended the system meter */
int smp_values_held(void) { return 0; }
/* (2026-11-21, fx-icons) the FX icons' neighbours (csrc/msel/msel.c): no icon, INSERT SEL never up here */
const unsigned char *msel_icon_of(int kind, int type) { (void)kind; (void)type; return 0; }
const unsigned char *msel_fx_icon(int type) { (void)type; return 0; }
int isel_up(void) { return 0; }
void isel_draw(void *c) { (void)c; }
const char *mu_fxp(int page, int place, int k) { return 0; }
extern u8 fxp_v[2][8];
extern void fxp_set_record(const u8 *f);
extern void fxp_defaults(void);
extern void fxp_words(u32 *w);
int main(void)
{
    unsigned v[16];
    fxp_defaults();
    u32 w[12];
    fxp_words(w);
    for (int k = 0; k < 12; k++) printf("%u ", w[k]);
    printf("\n");
    while (scanf("%u %u %u %u %u %u %u", &v[1], &v[2], &v[3], &v[4], &v[8], &v[9], &v[10]) == 7) {
        u8 f[16] = {0};
        for (int k = 1; k <= 4; k++) f[k] = (u8)v[k];
        f[8] = (u8)v[8]; f[9] = (u8)v[9]; f[10] = (u8)v[10];
        fxp_set_record(f);
        fxp_words(w);
        for (int k = 0; k < 12; k++) printf("%u ", w[k]);
        printf("\n");
    }
    return 0;
}
"""


def fbits(x) -> int:
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


def _rec_base() -> str:
    """-D for where our C reads stock's parameter records: the build's own value (dnfw.waverider.cpage passes
    dnfw.waverider.pages.lfo4_moved(); lfo4 moves the table, 2026-11-16 lfo4112)"""
    from dnfw.waverider import pages
    return f"-DREC_BASE={pages.lfo4_moved()['REC_BASE']:#x}u"


@pytest.fixture(scope="module")
def exe(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("fxp")
    (d / "h.c").write_text(HARNESS)
    (d / "pre.h").write_text("extern unsigned int host_kit;\n")
    out = d / "h"
    r = subprocess.run([cc, "-O1", "-w", "-ffp-contract=off", "-Dsection(x)=aligned(4)", _rec_base(), "-DCHR_KIT=host_kit",
                        "-include", str(d / "pre.h"), "-o", str(out), str(d / "h.c"),
                        str(ROOT / "csrc" / "fxpage" / "fxp.c")], capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr[-2000:])
    return out


def run(exe, cases):
    text = "\n".join(" ".join(map(str, c)) for c in cases)
    out = subprocess.run([str(exe)], input=text, capture_output=True, text=True, check=True).stdout.splitlines()
    return [[int(x) for x in ln.split()] for ln in out]


def test_header_is_fresh():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_fxp_derive.py"), "--check"], capture_output=True)
    if r.returncode == 1 and b"numpy" in r.stderr:
        pytest.skip("no numpy for the generator")
    assert r.returncode == 0, "csrc/fxpage/fxp_derive.h is stale: python scripts/gen_fxp_derive.py"


def test_every_knob_is_the_designs_bits(exe):
    cases = []
    for k in range(128):
        cases += [(k, XD.KN_DEF, XD.WD_DEF, XD.IN_DEF), (XD.SL_DEF, k, XD.WD_DEF, XD.IN_DEF),
                  (XD.SL_DEF, XD.KN_DEF, k, XD.IN_DEF), (XD.SL_DEF, XD.KN_DEF, XD.WD_DEF, k),
                  (k, (3 * k) % 128, (5 * k) % 128, (7 * k) % 128)]
    rev = [(k, FD.WD_DEF, FD.FZ_DEF) for k in range(128)] + [(FD.DF_DEF, k, FD.FZ_DEF) for k in range(128)] \
        + [(FD.DF_DEF, FD.WD_DEF, k) for k in range(128)] + [((5 * k) % 128, (3 * k) % 128, (7 * k) % 128) for k in range(128)]
    got = run(exe, [c + rev[i % len(rev)] for i, c in enumerate(cases)] + [(58, 61, 127, 64) + r for r in rev])[1:]
    for i, g in enumerate(got):
        if i < len(cases):
            c, r = cases[i], rev[i % len(rev)]
        else:
            c, r = (58, 61, 127, 64), rev[i - len(cases)]
        assert g[1:6] == [fbits(x) for x in XD.derive(*c)], c
        assert g[7:11] == [fbits(x) for x in FD.derive(*r)], r
        assert g[0] != 0 and g[6] != 0


def test_a_project_that_never_touched_the_page_sends_the_constants(exe):
    first = run(exe, [])[0]
    assert first[1:6] == [fbits(XD.KF), fbits(XD.KNEE), fbits(1.0), fbits(0.0), fbits(0.0)]
    assert first[7:11] == [fbits(1.0), fbits(0.0), fbits(1.0), fbits(0.0)]


TAP = r"""
/* cv_fill lives in csrc/waverider/page.c (the firmware's one rectangle fill, 2026-11-17); the page's drawing is
 * never run here, so a stand-in only links it (as test_inserts_c) */
void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on) { (void)cv; (void)x0; (void)y0; (void)x1; (void)y1; (void)on; }

#include <stdio.h>
typedef unsigned int u32;
typedef unsigned char u8;
int smp_overlay_dirty = 0;
int dlt_state = -1, rvt_state = -1;     /* csrc/xdly/ui.c, csrc/fdn8/ui.c: the send pages' TYPE is ours (1) */
u32 ins_edits = 0;
u32 mtr_func_ended = 0;                 /* csrc/meter/meter.c: this FUNC release ended the system meter */
int smp_values_held(void) { return 0; }
/* (2026-11-21, fx-icons) the FX icons' neighbours (csrc/msel/msel.c): no icon, INSERT SEL never up here */
const unsigned char *msel_icon_of(int kind, int type) { (void)kind; (void)type; return 0; }
const unsigned char *msel_fx_icon(int type) { (void)type; return 0; }
int isel_up(void) { return 0; }
void isel_draw(void *c) { (void)c; }
const char *mu_fxp(int page, int place, int k) { return 0; }
int func_down = 0;
/* the kit wishes record, faked (csrc/wishes): two kits, a field per kit, -1 when it has none */
volatile u32 wish_edits = 0;
u32 host_kit = 0x1000;
static int kit_field[2] = {-1, -1};
int wish_get(u32 item, u32 tag, unsigned char *out, u32 max)
{
    int k = item == 0x2000;
    if (tag != 0x0101 || kit_field[k] < 0 || max < 1) return -1;
    out[0] = (unsigned char)kit_field[k];
    return 1;
}
int wish_put(u32 item, u32 tag, const unsigned char *v, u32 vlen)
{
    int k = item == 0x2000;
    if (tag != 0x0101) return -1;
    kit_field[k] = vlen ? v[0] : -1;
    wish_edits++;
    return 0;
}
int host_key_held(u32 c) { return c == 17 && func_down; }
extern int fxp_up;
extern u8 fxp_v[2][8];
extern void fxp_begin(void);
extern void fxp_seen(int page, int ours);
extern int fxp_pop(u8 *it);
extern void fxp_defaults(void);
extern void fxp_cell(u32 id);
extern void fxp_words(u32 *w);
static int item(int type, int code, int flags, int delta)
{
    u8 it[16] = {0};
    it[0] = (u8)type;
    it[4] = (u8)(code >> 24); it[5] = (u8)(code >> 16); it[6] = (u8)(code >> 8); it[7] = (u8)code;
    it[8] = (u8)delta; it[9] = (u8)(flags >> 16); it[10] = (u8)(flags >> 8); it[11] = (u8)flags;
    return fxp_pop(it);
}
/* a key item: 1 press, 0 release (FUNC's own release carries no bit: flags 0) */
static void key(int code, int down) { if (code == 17) func_down = down; item(0, code, down ? 1 : 0, 0); }
int main(void)
{
    fxp_defaults();
    char c; int a, b;
    while (scanf(" %c", &c) == 1) {
        if (c == 'p') { scanf("%d %d", &a, &b); fxp_begin(); fxp_seen(a, b); }       /* the page stock drew */
        else if (c == 'd') { scanf("%d", &a); key(a, 1); }
        else if (c == 'u') { scanf("%d", &a); key(a, 0); }
        else if (c == 'k') { scanf("%d %d", &a, &b); printf("took=%d ", item(1, a, 0, b)); }
        else if (c == '?') printf("up=%d\n", fxp_up);
        else if (c == 'v') { scanf("%d %d", &a, &b); printf("v=%d\n", fxp_v[a][b]); }
        else if (c == 'c') { scanf("%d", &a); fxp_begin(); fxp_cell((u32)a); }        /* stock drew cell A */
        else if (c == 'w') { u32 w[12]; fxp_words(w); printf("w11=%u\n", w[11]); }
        else if (c == 'K') { scanf("%d", &a); host_kit = a ? 0x2000 : 0x1000; }   /* the playing kit: 0 or 1 */
        else if (c == 'f') { printf("f=%d,%d\n", kit_field[0], kit_field[1]); }
        else if (c == 'M') { scanf("%d", &a); mtr_func_ended = (u32)a; }       /* the meter's word for the next release */
        else if (c == 'S') { scanf("%d %d", &a, &b); dlt_state = a; rvt_state = b; }   /* the TYPEs: ours 1, stock 0 */
        else if (c == 'a') { scanf("%d", &a); printf("took=%d ", item(0, a, 1, 0)); item(0, a, 0x10, 0); }   /* an arrow */
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def tap(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("tap")
    (d / "h.c").write_text(TAP)
    (d / "pre.h").write_text("extern int host_key_held(unsigned int);\nextern unsigned int host_kit;\n")
    out = d / "h"
    r = subprocess.run([cc, "-O1", "-w", "-ffp-contract=off", "-Dsection(x)=aligned(4)", _rec_base(), "-DKEY_HELD=host_key_held",
                        "-DCHR_KIT=host_kit",
                        "-include", str(d / "pre.h"), "-o", str(out), str(d / "h.c"), str(ROOT / "csrc" / "fxpage" / "fxp.c")],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr[-2000:])
    return out


def feed(tap, text):
    r = subprocess.run([str(tap)], input=text, capture_output=True, text=True, check=True)
    return r.stdout.split()


XDLY_PAGE, FDN_PAGE = "p 1 1", "p 2 1"


def test_a_func_tap_switches_the_page(tap):
    assert feed(tap, f"{XDLY_PAGE} d 17 u 17 ? ") == ["up=1"]
    assert feed(tap, f"{XDLY_PAGE} d 17 u 17 {XDLY_PAGE} d 17 u 17 ? ") == ["up=0"]
    assert feed(tap, f"{FDN_PAGE} d 17 u 17 ? ") == ["up=2"]


def test_the_tap_is_cancelled_by_anything_between(tap):
    for between, took in (("d 5 u 5", []), ("d 45 u 45", []), ("d 33 u 33", []), ("k 3 1", ["took=0"]), ("k 7 -1", ["took=0"])):
        assert feed(tap, f"{XDLY_PAGE} d 17 {between} u 17 ? ") == took + ["up=0"], between
    assert feed(tap, f"{XDLY_PAGE} d 17 d 5 u 5 u 17 ? ") == ["up=0"]           # FUNC + FX (the send pages' way in)
    assert feed(tap, f"{XDLY_PAGE} d 17 d 45 u 45 u 17 ? ") == ["up=0"]         # FUNC + a push: the mod popup


def test_the_release_that_ends_the_system_meter_is_no_tap(tap):
    """2026-11-19: FUNC tapped, then held again, shows the system meter (csrc/meter/meter.c); that hold's release ends it
    and is not a tap of its own (mtr_func_ended): the gesture's first tap switches the page once, its release not"""
    assert feed(tap, f"{XDLY_PAGE} d 17 u 17 {XDLY_PAGE} d 17 M 1 u 17 M 0 ? ") == ["up=1"]
    assert feed(tap, f"{XDLY_PAGE} d 17 u 17 {XDLY_PAGE} d 17 u 17 ? ") == ["up=0"]     # (two plain taps: back)


def test_no_page_2_on_a_stock_type_or_off_the_page(tap):
    assert feed(tap, "p 1 0 d 17 u 17 ? ") == ["up=0"]                          # the Delay page, STOCK type
    assert feed(tap, "p 0 0 d 17 u 17 ? ") == ["up=0"]                          # some other page
    # entering by FUNC + FX: FUNC down before the page is drawn, released after: no toggle
    assert feed(tap, f"d 17 d 5 u 5 {XDLY_PAGE} u 17 ? ") == ["up=0"]


def test_page_2_takes_the_knobs_and_leaves_time_to_stock(tap):
    out = feed(tap, f"{XDLY_PAGE} d 17 u 17 {XDLY_PAGE} k 1 3 k 2 5 v 0 1 v 0 2 ")
    assert out == ["took=0", "took=1", "v=63", "v=61"]        # A (TIME) passed on to stock; B SLEW 58 + 5; C untouched
    # FUNC + turn on page 2 jumps to the next of 0, the default, 127 (and is no tap)
    out = feed(tap, f"{XDLY_PAGE} d 17 u 17 {XDLY_PAGE} d 17 k 2 3 u 17 v 0 1 ? ")
    assert out == ["took=1", "v=127", "up=1"]
    out = feed(tap, f"{XDLY_PAGE} d 17 u 17 {XDLY_PAGE} d 17 k 2 -3 u 17 v 0 1 ")
    assert out == ["took=1", "v=0"]                           # down from the default: 0
    # page 1's knobs are stock's alone
    assert feed(tap, f"{XDLY_PAGE} k 2 3 v 0 1 ") == ["took=0", "v=58"]


def test_the_reverb_page_takes_all_eight(tap):
    out = feed(tap, f"{FDN_PAGE} d 17 u 17 {FDN_PAGE} k 1 2 k 2 -2 k 3 4 v 1 0 v 1 1 v 1 2 ")
    assert out == ["took=1", "took=1", "took=1", "v=66", "v=125", "v=4"]


def test_arrows_on_a_page_2_stay_among_the_page_2s(tap):
    """2026-11-20 (the User: "stays within the FUNC / no-FUNC pages: no mixing of groups"): on page 1 UP / DOWN are
    stock's (Delay -> Reverb -> Chorus); on a page 2 they go on to stock (its step) only towards a send page whose TYPE
    has a page 2 (fxp_draw then opens it), else they are taken (no step: never a page 1); FUNC + arrow stock's"""
    UP, DOWN = 11, 14
    d2, r2 = f"{XDLY_PAGE} d 17 u 17 {XDLY_PAGE}", f"{FDN_PAGE} d 17 u 17 {FDN_PAGE}"
    assert feed(tap, f"S 1 1 {XDLY_PAGE} a {DOWN} a {UP} ? ") == ["took=0", "took=0", "up=0"]      # page 1: stock's
    assert feed(tap, f"S 1 1 {d2} a {DOWN} ") == ["took=0"]                 # Delay 2 -> Reverb 2 (FDN8 / LONG)
    assert feed(tap, f"S 1 0 {d2} a {DOWN} ? ") == ["took=1", "up=1"]       # Reverb STOCK: no page 2 there, stays
    assert feed(tap, f"S 1 1 {d2} a {UP} ? ") == ["took=1", "up=1"]         # Delay is the first: stays
    assert feed(tap, f"S 1 1 {r2} a {UP} ") == ["took=0"]                   # Reverb 2 -> Delay 2 (XDLY)
    assert feed(tap, f"S 0 1 {r2} a {UP} ? ") == ["took=1", "up=2"]         # Delay STOCK: stays
    assert feed(tap, f"S 1 1 {r2} a {DOWN} ? ") == ["took=1", "up=2"]       # the Chorus has no page 2: stays
    assert feed(tap, f"S 1 1 {d2} d 17 a {DOWN} u 17 ") == ["took=0"]       # FUNC + DOWN: stock's


def test_link_has_a_word_source_for_every_packet_kind():
    """smp_tdm (csrc/sampler/link.c): every kind of packet it sends (is_cmd, is_ins, is_fxp, is_blank) has its words
    in the word select; one without it sent job data (or NULL + 0..3) as that packet's words (326ff17f's bug)"""
    import re
    src = (ROOT / "csrc" / "sampler" / "link.c").read_text()
    body = src[src.index("void smp_tdm(u32 h)"):]
    body = body[:body.index("smp_tdm_sent++;")]
    kinds = re.findall(r"\bint (is_\w+) = ", body)
    kinds = [k for k in kinds if k != "is_rt"]                  # (a kind of command: is_cmd := is_rt || ..., its words are cw[])
    # 2026-11-21 (cf-asm b2609b7b): the words are written by hooks.S tdm_units from one source picked per packet
    # (`const u32 *src = ...`); a blank packet sends no words (`u32 nn = is_blank ? 0u : ...`)
    sel = re.search(r"const u32 \*src = (.*?);", body, re.S).group(1)
    nn = re.search(r"u32 nn = (.*?);", body, re.S).group(1)
    assert "is_fxp" in kinds and "is_blank" in kinds
    assert re.match(r"\s*is_blank \? 0u? :", nn), f"a blank packet sends words: {nn!r}"
    for k in kinds:
        if k != "is_blank":
            assert k in sel, f"{k}: no word source in {sel!r}"


def test_the_mirror_page_is_not_written_and_nothing_goes_at_power_on():
    import re
    src = (ROOT / "csrc" / "sampler" / "link.c").read_text()
    body = src[src.index("void smp_tdm(u32 h)"):]
    body = body[:body.index("smp_tdm_sent++;")]
    assert "DIR + FXP_OFFSET" not in body                       # the mirror is the checksummed image
    assert "fxp_seen_gen __attribute__((section(\".data\"))) = 0;" in body    # no send at power-on
    assert "fxp_active()" in body


ACTIVE = r"""
/* cv_fill lives in csrc/waverider/page.c (the firmware's one rectangle fill, 2026-11-17); the page's drawing is
 * never run here, so a stand-in only links it (as test_inserts_c) */
void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on) { (void)cv; (void)x0; (void)y0; (void)x1; (void)y1; (void)on; }

#include <stdio.h>
typedef unsigned int u32;
typedef unsigned char u8;
/* the kit wishes record (csrc/wishes): no kit has a field here */
volatile u32 wish_edits = 0;
int wish_get(u32 item, u32 tag, unsigned char *out, u32 max) { return -1; }
int wish_put(u32 item, u32 tag, const unsigned char *v, u32 vlen) { return 0; }
u32 host_kit = 0x1000;

int smp_overlay_dirty = 0;
int dlt_state = -1, rvt_state = -1;     /* csrc/xdly/ui.c, csrc/fdn8/ui.c: the send pages' TYPE is ours (1) */
u32 ins_edits = 0;
u32 mtr_func_ended = 0;                 /* csrc/meter/meter.c: this FUNC release ended the system meter */
int smp_values_held(void) { return 0; }
/* (2026-11-21, fx-icons) the FX icons' neighbours (csrc/msel/msel.c): no icon, INSERT SEL never up here */
const unsigned char *msel_icon_of(int kind, int type) { (void)kind; (void)type; return 0; }
const unsigned char *msel_fx_icon(int type) { (void)type; return 0; }
int isel_up(void) { return 0; }
void isel_draw(void *c) { (void)c; }
const char *mu_fxp(int page, int place, int k) { return 0; }
extern void fxp_defaults(void);
extern void fxp_set_record(const u8 *f);
extern int fxp_active(void);
int main(void)
{
    fxp_defaults();
    printf("%d ", fxp_active());
    u8 f[16] = {0, 58, 61, 127, 64, 0, 0, 0, 64, 127, 0, 0, 0, 0, 0, 0};
    fxp_set_record(f);
    printf("%d ", fxp_active());
    f[2] = 60;
    fxp_set_record(f);
    printf("%d ", fxp_active());
    f[2] = 61; f[10] = 5;
    fxp_set_record(f);
    printf("%d\n", fxp_active());
    return 0;
}
"""


def test_active_means_not_at_the_defaults(tmp_path):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    (tmp_path / "h.c").write_text(ACTIVE)
    (tmp_path / "pre.h").write_text("extern unsigned int host_kit;\n")
    r = subprocess.run([cc, "-O1", "-w", "-Dsection(x)=aligned(4)", _rec_base(), "-DCHR_KIT=host_kit", "-include", str(tmp_path / "pre.h"),
                        "-o", str(tmp_path / "h"), str(tmp_path / "h.c"),
                        str(ROOT / "csrc" / "fxpage" / "fxp.c")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1500:]
    out = subprocess.run([str(tmp_path / "h")], capture_output=True, text=True, check=True).stdout.split()
    assert out == ["0", "0", "1", "1"]


CHORUS_PAGE = "c 105"                                       # stock drew the Chorus page's DPTH cell


def test_the_chorus_page_takes_knob_e_for_its_type(tap):
    """2026-11-12: the Chorus page's TYPE on E (knob 5): right JUNO, left STOCK, in the playing kit's wishes record
    (tag 0x0101; STOCK removes the field); the twelfth word carries it (0 until then); E is stock's (nothing there)
    off the Chorus page, and the other knobs stay stock's on it"""
    assert feed(tap, "w ") == ["w11=0"]
    assert feed(tap, f"{CHORUS_PAGE} k 5 1 f w ") == ["took=1", "f=1,-1", "w11=1"]
    assert feed(tap, f"{CHORUS_PAGE} k 5 1 {CHORUS_PAGE} k 5 -2 f w ") == ["took=1", "took=1", "f=-1,-1", "w11=0"]
    assert feed(tap, f"{CHORUS_PAGE} k 1 3 k 2 -3 k 6 2 f ") == ["took=0", "took=0", "took=0", "f=-1,-1"]
    assert feed(tap, "c 113 k 5 1 f ") == ["took=0", "f=-1,-1"]                # the Delay page: not ours
    assert feed(tap, f"{CHORUS_PAGE} c 0 k 5 1 f ") == ["took=0", "f=-1,-1"]   # the page left


def test_the_chorus_type_follows_the_playing_kit(tap):
    """JUNO set on kit 0; kit 1 plays STOCK (no field); back on kit 0, JUNO again: TYPE is the kit's, not the project's"""
    assert feed(tap, f"{CHORUS_PAGE} k 5 1 w K 1 w K 0 w f ") == ["took=1", "w11=1", "w11=0", "w11=1", "f=1,-1"]
    assert feed(tap, f"K 1 {CHORUS_PAGE} k 5 1 f K 0 w ") == ["took=1", "f=-1,1", "w11=0"]
