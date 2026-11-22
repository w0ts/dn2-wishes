"""The inserts' live values (csrc/inserts/ins.c, 2026-11-20; scratch/mod-live-design.md C): p-locks and the matrix's slow
modulation of each track's 14 knobs. ins.c compiled for the host and driven through ctypes:

- the round-robin: one group of 4 records packed a block (ins_period), every group every 8 blocks, a packet due once
  every 8 blocks after the last group; its change word moves only when the words differ from the last packet's;
- bit-exact: with no lock and no route the packet's words are ins_words' (dnfw.inserts.design.pack's), every packet;
- a trig's locks (ins_trig: a byte a slot, INSERT 1 low, INSERT 2 high) take the knobs' place until the next trig, pack
  their group at once and make the packet due in the same block;
- the routes' offsets (ins_moff, the matrix's) add to SET on the knobs the slot's type routes (ROUTE_OK), clamped;
- MIX 0 = OFF only when no MIX route or lock keeps the slot running (ins_keep);
- TAPE's PGAIN has its own change word (ins_tpg_gen): a knob turned elsewhere does not move it."""

from __future__ import annotations

import ctypes
import pathlib
import shutil
import subprocess

import pytest

from dnfw.inserts import design as D

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "csrc" / "inserts" / "ins.c"
HARNESS = r"""
typedef unsigned int u32;
typedef unsigned char u8;
unsigned char host_track = 0;
unsigned int host_frames = 0;
void cv_fill(void *cv, int x0, int y0, int x1, int y1, int on) { (void)cv; (void)x0; (void)y0; (void)x1; (void)y1; (void)on; }
void *wr_screen_obj = 0;
int smp_overlay_dirty = 0;
const char *mu_ins(int type, int knob, int k) { (void)type; (void)knob; (void)k; return 0; }
int smp_values_held(void) { return 0; }
/* (2026-11-21, fx-icons) the FX icons' neighbours (csrc/msel/msel.c): no icon, INSERT SEL never up here */
const unsigned char *msel_icon_of(int kind, int type) { (void)kind; (void)type; return 0; }
const unsigned char *msel_fx_icon(int type) { (void)type; return 0; }
int isel_up(void) { return 0; }
void isel_draw(void *c) { (void)c; }
int ovw_fx_held(void) { return 0; }
unsigned int ovw_pass = 0;
void wpop_offer_mv(int slot, const char *label, int n, int cur, const char *(*name)(int, int), const char *(*tag)(int, int),
                   int arg, void (*move)(int, int)) { (void)slot; (void)label; (void)n; (void)cur; (void)name; (void)tag;
                   (void)arg; (void)move; }
const char *const amp_title1 = "ENV1/AMP";
unsigned int sl_ins_held(unsigned int k, unsigned int j) { (void)k; (void)j; return 0x10000u; }
int sl_ins_set(unsigned int k, unsigned int j, unsigned int v) { (void)k; (void)j; (void)v; return 0; }
unsigned int host_routes[16];
unsigned int mx_ins_routes(unsigned int t) { return host_routes[t & 15]; }
unsigned char host_pool[258 * 80];
int host_pool_on = 0;
unsigned char *sl_ui_pool(void) { return host_pool_on ? host_pool : 0; }
const unsigned char *sl_ins_record(const unsigned char *tb, unsigned int t, unsigned int k)
{
    for (int i = 0; i < 80; i++)
        if (tb[258 * i] == 0x5B + k && tb[258 * i + 1] == (0x20 | t))
            return tb + 258 * i;
    return 0;
}
void mv_own_knob(void *c, int x, int y, int w, unsigned int key, unsigned int slot) { (void)c; (void)x; (void)y; (void)w;
                 (void)key; (void)slot; }
"""


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("inslive")
    src = SRC.read_text()
    line = "#define UI_TRACK  (*(volatile u8 *)0x42432A6Cu)"
    assert line in src
    (d / "ins_host.c").write_text(src.replace(line, "extern unsigned char host_track;\nextern unsigned int host_frames;\n#define UI_TRACK host_track"))
    (d / "h.c").write_text(HARNESS)
    out = d / "libinslive.so"
    r = subprocess.run([cc, "-shared", "-fPIC", "-O1", "-w", "-Dsection(x)=aligned(4)", "-DINS_FRAMES=host_frames",
                        "-I", str(ROOT / "csrc" / "inserts"), "-o", str(out), str(d / "h.c"), str(d / "ins_host.c")],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr[-3000:])
    L = ctypes.CDLL(str(out))
    L.ins_take.restype = ctypes.POINTER(ctypes.c_uint32)
    return L


def u32(L, name):
    return ctypes.c_uint32.in_dll(L, name)


def arr(L, name, ctype, n):
    return (ctype * n).in_dll(L, name)


def load(L, recs):
    arr(L, "host_routes", ctypes.c_uint32, 16)[:] = [0] * 16
    ctypes.c_int.in_dll(L, "host_pool_on").value = 0
    for i, r in enumerate(recs):
        L.ins_set_record(i >> 1, i & 1, (ctypes.c_uint8 * 8)(*r))
    L.ins_loaded()
    arr(L, "ins_moff", ctypes.c_int16, 16 * 14)[:] = [0] * (16 * 14)


def words(L):
    w = (ctypes.c_uint32 * 58)()
    L.ins_words(w)
    return list(w)


def block(L):
    """one DSP block as link.c runs it: ins_period, then the packet taken if due -> its 58 words, or None"""
    L.ins_period()
    if ctypes.c_int.in_dll(L, "ins_due").value:
        p = L.ins_take()
        return [p[k] for k in range(58)]
    return None


def recs_plain():
    """records every test starts from: FUZZ, CHOR, FDN8, TAPE, ... at MIX 100, knobs spread"""
    types = [D.FUZZ, D.CHOR, D.FDN8, D.TAPE, D.DIST, D.WIDE, D.XDLY, D.SUB]
    return [[types[i % len(types)], 100] + [(7 * i + 11 * k) % 128 for k in range(6)] for i in range(D.RECORDS)]


def test_round_robin_one_packet_every_8_blocks_after_the_last_group(lib):
    load(lib, recs_plain())
    for _ in range(16):                                         # settle: the headers, every group packed once
        block(lib)
    sent = [block(lib) is not None for _ in range(64)]
    assert sum(sent) == 8
    first = sent.index(True)
    assert all(s == ((k - first) % 8 == 0) for k, s in enumerate(sent))


def test_bit_exact_without_locks_or_routes(lib):
    """the DSP sees the same words as ins_words (dnfw.inserts.design.pack's) in every packet"""
    import random
    rnd = random.Random(7)
    for _ in range(4):
        recs = [[rnd.choice(range(len(D.NAMES)))] + [rnd.choice((0, 0x80, rnd.randrange(256)))]
                + [rnd.randrange(128) for _ in range(6)] for _ in range(D.RECORDS)]
        load(lib, recs)
        want = words(lib)
        pk = [p for p in (block(lib) for _ in range(40)) if p]
        assert len(pk) >= 4
        for p in pk[1:]:
            assert p[2:] == want[2:] and p[1] == 0


def test_change_word_moves_only_when_the_words_differ(lib):
    load(lib, recs_plain())
    pk = [p for p in (block(lib) for _ in range(48)) if p]
    chg = [p[0] for p in pk]
    assert len(set(chg[1:])) == 1                               # nothing changed: the same change word every packet
    host_track = ctypes.c_ubyte.in_dll(lib, "host_track")
    host_track.value = 3
    ctypes.c_int.in_dll(lib, "ins_up").value = 1
    lib.ins_pop((ctypes.c_uint8 * 12)(1, 0, 0, 0, 0, 0, 0, 2, 5, 0, 0, 0))   # knob B (K1) of track 4's INSERT 1, +5
    pk2 = [p for p in (block(lib) for _ in range(24)) if p]
    assert pk2[0][0] == chg[-1] + 1 and all(p[0] == pk2[0][0] for p in pk2)
    t = D.unpack(pk2[0][2:])
    assert t[8 * 6 + 2] == (recs_plain()[6][2] + 5)            # record 6 (track 4, slot 1): K1 + 5


def lk_words(slot1=None, slot2=None):
    """a trig's 7 lock words (K1..K6, MIX): dicts {kind: value} for INSERT 1 (low byte) and INSERT 2 (high byte)"""
    out = []
    for k in range(7):
        a = (slot1 or {}).get(k, 0xFF)
        b = (slot2 or {}).get(k, 0xFF)
        out.append(a | b << 8)
    return (ctypes.c_uint16 * 7)(*out)


def test_a_trig_lock_is_sent_in_the_next_block_and_held_until_the_next_trig(lib):
    recs = recs_plain()
    load(lib, recs)
    for _ in range(20):
        block(lib)
    before = u32(lib, "ins_chg").value
    lib.ins_trig(5, lk_words({0: 99, 6: 33}, {3: 7}))          # track 6: INSERT 1 K1 99, MIX 33; INSERT 2 K4 7
    p = block(lib)
    assert p is not None, "the trig's group packed and sent in the same block"
    assert p[0] == before + 1
    t = D.unpack(p[2:])
    r1, r2 = 10, 11                                             # track 6's records
    assert t[8 * r1 + 2] == 99 and t[8 * r1 + 1] == 33 and t[8 * r2 + 5] == 7
    assert t[8 * r1 + 3:8 * r1 + 8] == recs[r1][3:8] and t[8 * r2 + 1] == 100
    for _ in range(16):                                         # held until the next trig
        q = block(lib)
        if q:
            assert D.unpack(q[2:])[8 * r1 + 2] == 99
    lib.ins_trig(5, None)                                       # a trig with no lock: the knobs again
    q = block(lib)
    assert q is not None and D.unpack(q[2:])[8 * r1 + 2] == recs[r1][2] and D.unpack(q[2:])[8 * r1 + 1] == 100
    urg = u32(lib, "ins_urgents").value
    lib.ins_trig(5, None)
    lib.ins_period()
    assert u32(lib, "ins_urgents").value == urg


def test_sixteen_trigs_packed_over_four_blocks_at_most_three_groups_a_block(lib):
    """(2026-11-21, the worst frame) 16 tracks' trigs in one block: the round-robin's group and at most 2 urgent ones
    a block, so all 8 groups in 4 blocks; each block's packet sent; the last one carries every track's lock"""
    recs = recs_plain()
    load(lib, recs)
    for _ in range(20):
        block(lib)
    urg = u32(lib, "ins_urgents").value
    for t in range(16):
        lib.ins_trig(t, lk_words({0: 90 + t}))
    sent, counts = [], []
    for _ in range(4):
        u0 = u32(lib, "ins_urgents").value
        p = block(lib)
        counts.append(u32(lib, "ins_urgents").value - u0)
        sent.append(p)
    assert all(c <= 3 for c in counts) and u32(lib, "ins_urgents").value - urg == 8, counts
    assert all(p is not None for p in sent)
    t = D.unpack(sent[-1][2:])
    assert all(t[8 * (2 * k) + 2] == 90 + k for k in range(16))
    assert not any(arr(lib, "ins_urgent", ctypes.c_uint8, 8))


def test_route_offsets_on_the_knobs_the_type_routes(lib):
    recs = recs_plain()
    recs[0] = [D.CHOR, 100, 50, 50, 40, 64, 100, 10]           # track 1 slot 1: CHOR (DPTH DLY VOIC not routed)
    recs[1] = [D.FUZZ, 60, 64, 90, 0, 30, 0, 100]
    load(lib, recs)
    for _ in range(16):
        block(lib)
    off = arr(lib, "ins_moff", ctypes.c_int16, 16 * 14)
    for i in range(14):
        off[i] = 0x1080                                         # +16.5 steps on every knob of track 1
    off[7 + 6] = -0x7F00                                        # INSERT 2's MIX down to 0 (clamped)
    pk = [p for p in (block(lib) for _ in range(16)) if p]
    t = D.unpack(pk[-1][2:])
    c = t[0:8]
    assert c[0] == D.CHOR and c[1] == 116                       # MIX 100 + 16 (floor of +16.5 on a whole cell)
    assert c[2] == 50 and c[4] == 40 and c[5] == 64             # DPTH DLY VOIC: not routed (14a)
    assert c[3] == 66 and c[6] == 116 and c[7] == 26            # RATE WDTH FDBK
    f = t[8:16]
    assert f[1] == 0                                            # a modulated 0: dry, not OFF (type kept)
    assert f[0] == D.FUZZ and f[2] == 80 and f[7] == 116


def test_mix_0_is_off_unless_a_mix_route_or_lock_keeps_it(lib):
    recs = recs_plain()
    recs[4] = [D.FUZZ, 0, 1, 2, 3, 4, 5, 6]                     # track 3 slot 1 at MIX 0: OFF (all zero)
    load(lib, recs)
    pk = [p for p in (block(lib) for _ in range(16)) if p]
    assert D.unpack(pk[-1][2:])[32:40] == [0] * 8
    lib.ins_trig(2, lk_words({6: 80}))                          # a MIX lock: kept running from now on
    for _ in range(2):
        block(lib)
    pk = [p for p in (block(lib) for _ in range(16)) if p]
    assert D.unpack(pk[-1][2:])[32:40] == [D.FUZZ, 80, 1, 2, 3, 4, 5, 6]
    lib.ins_trig(2, None)                                       # the next trig, no lock: MIX 0, dry, still running
    pk = [p for p in (block(lib) for _ in range(16)) if p]
    assert D.unpack(pk[-1][2:])[32:40] == [D.FUZZ, 0, 1, 2, 3, 4, 5, 6]
    # the UI pass's scan: no MIX lock in the pattern, no route: OFF again
    u = ctypes.c_uint32.in_dll(lib, "host_frames")
    u.value += 1000
    lib.ins_ui_poll()
    pk = [p for p in (block(lib) for _ in range(16)) if p]
    assert D.unpack(pk[-1][2:])[32:40] == [0] * 8
    # a MIX route keeps it
    arr(lib, "host_routes", ctypes.c_uint32, 16)[2] = 1 << 6
    u.value += 1000
    lib.ins_ui_poll()
    pk = [p for p in (block(lib) for _ in range(16)) if p]
    assert D.unpack(pk[-1][2:])[32:40] == [D.FUZZ, 0, 1, 2, 3, 4, 5, 6]
    # a MIX lock on some step of the pattern keeps it (INSERT 1's byte: the low one)
    arr(lib, "host_routes", ctypes.c_uint32, 16)[2] = 0
    pool = arr(lib, "host_pool", ctypes.c_uint8, 258 * 80)
    pool[:] = [0xFF] * (258 * 80)
    pool[0], pool[1] = 0x5B + 6, 0x20 | 2
    import struct
    step = struct.pack("=H", 0xFF00 | 90)                       # the host's own order, as the ColdFire reads its u16
    pool[2 + 2 * 9], pool[3 + 2 * 9] = step[0], step[1]
    ctypes.c_int.in_dll(lib, "host_pool_on").value = 1
    u.value += 1000
    lib.ins_ui_poll()
    pk = [p for p in (block(lib) for _ in range(16)) if p]
    assert D.unpack(pk[-1][2:])[32:40] == [D.FUZZ, 0, 1, 2, 3, 4, 5, 6]


def test_tape_pgain_has_its_own_change_word(lib):
    recs = recs_plain()
    load(lib, recs)
    for _ in range(16):
        block(lib)
    g = u32(lib, "ins_tpg_gen").value
    ctypes.c_ubyte.in_dll(lib, "host_track").value = 0
    ctypes.c_int.in_dll(lib, "ins_up").value = 1
    lib.ins_pop((ctypes.c_uint8 * 12)(1, 0, 0, 0, 0, 0, 0, 3, 2, 0, 0, 0))   # FUZZ's TONE (C) on track 1: no TAPE change
    for _ in range(8):
        block(lib)
    assert u32(lib, "ins_tpg_gen").value == g
    ctypes.c_ubyte.in_dll(lib, "host_track").value = 1                       # track 2 slot 2 is TAPE (record 3)
    ctypes.c_int.in_dll(lib, "ins_up").value = 2
    lib.ins_pop((ctypes.c_uint8 * 12)(1, 0, 0, 0, 0, 0, 0, 6, 3, 0, 0, 0))   # TAPE's PGAIN (F) +3 dB
    for _ in range(8):                                          # (2026-11-21) made when track 2's group is packed next
        block(lib)
    assert u32(lib, "ins_tpg_gen").value == g + 1
    w = arr(lib, "ins_tpg_w", ctypes.c_uint32, 8)
    assert (w[0] >> 24) & 0x7F == 3                             # record 3: byte 3 of word 0, +3 dB


def test_constant_work_one_group_a_block(lib):
    """the same groups packed in the same blocks with or without offsets (no idle skip): ins_rr steps every block"""
    load(lib, recs_plain())
    seen = []
    for _ in range(24):
        seen.append(u32(lib, "ins_rr").value)
        block(lib)
    assert seen == [(seen[0] + k) % 8 for k in range(24)]
