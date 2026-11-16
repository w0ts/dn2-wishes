"""The wishes record's C (csrc/wishes, docs/wishes-record.md), compiled for the host and driven through ctypes:
the table against a model under every way a sound moves, the record's spelling and hash, the link in the stored
sound's lane, and the +Drive cells over a fake +Drive (a power cut, a torn cell, ERASE's lock, a full queue).

What only the firmware can show (the four hooks at stock's routines, the cells on a real eMMC) is the emulator's and
the unit's; test_wishes.py checks the target build and its stubs' bytes."""

from __future__ import annotations

import ctypes
import pathlib
import random
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "csrc" / "wishes"
SOURCES = [SRC / "table.c", SRC / "tlv.c", SRC / "store.c"]

CELL0, CELLS = 0x6F0800, 59392
SOUND = 1163
W_DIRTY, W_DISK, W_WANT, W_MISSING, W_LOCKED = 1, 2, 4, 8, 16
LANE = {4: 36, 8: 44, 12: 52, 16: 60, 20: 68, 24: 76, 28: 84}     # lane id -> stored byte

HOST_H = r"""
extern int host_blk_read(unsigned s, unsigned n, void *p);
extern int host_blk_write(unsigned s, unsigned n, const void *p);
extern unsigned host_ready, host_sectors, host_frames;
#define WISH_BLK_READ(s, n, p) host_blk_read(s, n, p)
#define WISH_BLK_WRITE(s, n, p) host_blk_write(s, n, p)
#define WISH_BLK_READY host_ready
#define WISH_BLK_SECTORS host_sectors
#define WISH_FRAMES host_frames
"""

HARNESS = r"""
#include <string.h>
#include "wish.h"
u8 wish_host_area[WISH_O_END] __attribute__((aligned(16)));
int smp_er_lock = 0;
volatile u32 ins_wr_head = 0;
unsigned host_ready = 1, host_sectors = 0x800000, host_frames = 0;
unsigned host_reads = 0, host_writes = 0, host_fail = 0;
static u8 disk[59392u * 512u];
int host_blk_read(unsigned s, unsigned n, void *p)
{
    if (host_fail) return -1;
    host_reads++;
    if (n != 512u || s < 0x6F0800u || s >= 0x6F0800u + 59392u) { memset(p, 0, n); return 0; }
    memcpy(p, disk + 512u * (s - 0x6F0800u), 512u);
    return 0;
}
int host_blk_write(unsigned s, unsigned n, const void *p)
{
    if (host_fail) return -1;
    host_writes++;
    if (n != 512u || s < 0x6F0800u || s >= 0x6F0800u + 59392u) return -2;
    memcpy(disk + 512u * (s - 0x6F0800u), p, 512u);
    return 0;
}
u8 *host_disk(void) { return disk; }
void host_reboot(void)              /* RAM is lost; the +Drive stays */
{
    wish_ready = 0;
    wish_pend_head = wish_pend_tail = 0;
    wish_busy = 0;
    wish_wants = 0;
    wish_init();
}
void host_erase(void) { memset(disk, 0, sizeof disk); }
void host_zero(void)                /* every counter, between tests */
{
    wish_reentered = wish_full = 0;
    wish_loads = wish_links_in = wish_saves = wish_links_out = wish_copies = wish_carries = wish_clears = 0;
    wish_cells_written = wish_cells_found = wish_cells_read = wish_resolved = wish_missing = 0;
    wish_pend_lost = wish_io_fails = 0;
    host_reads = host_writes = 0;
    ins_wr_head = 0;
}
"""


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("wishes")
    (d / "host.h").write_text(HOST_H)
    (d / "harness.c").write_text(HARNESS)
    out = d / "libwishes.so"
    r = subprocess.run([cc, "-shared", "-fPIC", "-O1", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-DWISH_HOST", "-include", str(d / "host.h"), f"-I{SRC}",
                        *map(str, SOURCES), str(d / "harness.c"), "-o", str(out)],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr)
    L = ctypes.CDLL(str(out))
    L.wish_find.restype = ctypes.c_void_p
    L.wish_add.restype = ctypes.c_void_p
    L.host_disk.restype = ctypes.POINTER(ctypes.c_uint8)
    for name in ("wish_xxh32",):
        getattr(L, name).restype = ctypes.c_uint32
    return L


@pytest.fixture()
def w(lib):
    lib.host_erase()
    lib.host_reboot()
    lib.host_zero()
    for name in ("smp_er_lock", "host_fail"):
        ctypes.c_int.in_dll(lib, name).value = 0
    for name in ("wish_put_wait", "wish_got_state"):
        ctypes.c_uint32.in_dll(lib, name).value = 0
    ctypes.c_uint.in_dll(lib, "host_frames").value = 0
    return lib


def u32(lib, name):
    return ctypes.c_uint32.in_dll(lib, name).value


def entry(lib, sound):
    """-> (h0, h1, len, flags, rec) or None"""
    p = lib.wish_find(ctypes.c_uint32(sound))
    if not p:
        return None
    b = ctypes.string_at(p, 12 + 488)
    import struct
    h0, h1, n, flags = struct.unpack_from("<IIHB", b)
    return h0, h1, n, flags, b[12:12 + n]


def put(lib, sound, tag, value: bytes) -> int:
    return lib.wish_put(ctypes.c_uint32(sound), ctypes.c_uint32(tag), value, len(value))


def get(lib, sound, tag):
    out = ctypes.create_string_buffer(488)
    n = lib.wish_get(ctypes.c_uint32(sound), ctypes.c_uint32(tag), out, 488)
    return None if n < 0 else out.raw[:n]


def save(lib, sound, stored: bytearray | None = None) -> bytearray:
    stored = stored if stored is not None else bytearray(359)
    buf = (ctypes.c_uint8 * 359).from_buffer(stored)
    lib.wish_save(buf, ctypes.c_uint32(sound))
    return stored


def load(lib, sound, stored: bytearray) -> None:
    buf = (ctypes.c_uint8 * 359).from_buffer(stored)
    lib.wish_load(ctypes.c_uint32(sound), buf)


def settle(lib, passes=64):
    f = ctypes.c_uint.in_dll(lib, "host_frames")
    for _ in range(passes):
        f.value += 800
        lib.wish_poll()


# -- the hash ------------------------------------------------------------------------------------------------

def xxh32(data: bytes, seed: int) -> int:
    P1, P2, P3, P4, P5 = 2654435761, 2246822519, 3266489917, 668265263, 374761393
    M = 0xFFFFFFFF

    def rotl(x, r):
        return ((x << r) | (x >> (32 - r))) & M

    def rnd(v, lane):
        return rotl((v + lane * P2) & M, 13) * P1 & M
    n, i = len(data), 0
    if n >= 16:
        v = [(seed + P1 + P2) & M, (seed + P2) & M, seed, (seed - P1) & M]
        while i + 16 <= n:
            for k in range(4):
                v[k] = rnd(v[k], int.from_bytes(data[i + 4 * k:i + 4 * k + 4], "little"))
            i += 16
        h = (rotl(v[0], 1) + rotl(v[1], 7) + rotl(v[2], 12) + rotl(v[3], 18)) & M
    else:
        h = (seed + P5) & M
    h = (h + n) & M
    while i + 4 <= n:
        h = rotl((h + int.from_bytes(data[i:i + 4], "little") * P3) & M, 17) * P4 & M
        i += 4
    while i < n:
        h = rotl((h + data[i] * P5) & M, 11) * P1 & M
        i += 1
    h ^= h >> 15
    h = h * P2 & M
    h ^= h >> 13
    h = h * P3 & M
    return h ^ (h >> 16)


def link_bytes(rec: bytes) -> dict[int, int]:
    """-> stored byte -> value: the link csrc/wishes/table.c writes for REC (scripts/emu_wishes.py uses it too)"""
    h0, h1 = xxh32(rec, 0x57495348), xxh32(rec, 0x4E324D58)
    seed = 0x5701 ^ h0 ^ (((h1 << 7) | (h1 >> 25)) & 0xFFFFFFFF) ^ (len(rec) << 16)
    x = xxh32(b"", seed & 0xFFFFFFFF)
    words = {36: 0x5701, 44: h0 >> 16, 52: h0 & 0xFFFF, 60: h1 >> 16, 68: h1 & 0xFFFF, 76: len(rec),
             84: (x ^ (x >> 16)) & 0xFFFF}
    return {at + k: (v >> (8 - 8 * k)) & 0xFF for at, v in words.items() for k in (0, 1)}


def cell_bytes(rec: bytes) -> bytes:
    """-> the cell csrc/wishes/store.c writes for REC"""
    h0, h1 = xxh32(rec, 0x57495348), xxh32(rec, 0x4E324D58)
    c = bytearray(512)
    c[:8] = b"DN2W\x01\x01" + len(rec).to_bytes(2, "big")
    c[8:16] = h0.to_bytes(4, "big") + h1.to_bytes(4, "big")
    c[20:20 + len(rec)] = rec
    a, b = 1, 0
    for x in c[:508]:
        a += x
        b += a
    c[508:] = ((((b << 16) ^ a) & 0xFFFFFFFF) ^ 0x57495348).to_bytes(4, "big")
    return bytes(c)


def test_xxh32_known_values(lib):
    assert lib.wish_xxh32(b"", 0, 0) == 0x02CC5D05            # the published empty-input value
    assert xxh32(b"", 0) == 0x02CC5D05
    assert lib.wish_xxh32(b"a", 1, 0) == xxh32(b"a", 0) == 0x550D7456


def test_xxh32_matches_the_reference_at_every_length_and_alignment(lib):
    rnd = random.Random(1)
    for n in range(0, 140):
        for off in range(4):
            data = bytes(rnd.randrange(256) for _ in range(n + off))
            seed = rnd.randrange(1 << 32)
            buf = ctypes.create_string_buffer(data, len(data))
            got = lib.wish_xxh32(ctypes.byref(buf, off), n, ctypes.c_uint32(seed))
            assert got == xxh32(data[off:], seed), (n, off)


# -- the record's spelling -----------------------------------------------------------------------------------

def spell(fields: dict[int, bytes]) -> bytes:
    return b"".join(t.to_bytes(2, "big") + len(v).to_bytes(2, "big") + v for t, v in sorted(fields.items()))


def test_fields_are_spelled_one_way_whatever_the_order_of_edits(w):
    rnd = random.Random(2)
    model: dict[int, bytes] = {}
    for _ in range(600):
        tag = rnd.choice([1, 2, 3, 0x10, 0x4005, 0x7FFF, 0x0100])
        v = bytes(rnd.randrange(256) for _ in range(rnd.choice([0, 0, 1, 2, 5, 16, 40])))
        before = entry(w, 0x1000)
        r = put(w, 0x1000, tag, v)
        new = dict(model)
        if v:
            new[tag] = v
        else:
            new.pop(tag, None)
        if len(spell(new)) > 488:
            assert r == -4
            # nothing changed but the dirty mark
            assert entry(w, 0x1000)[4] == (before[4] if before else b"")
            continue
        assert r == 0
        model = new
        e = entry(w, 0x1000)
        assert e is not None and e[4] == spell(model)
        assert w.wish_tlv_valid(e[4], len(e[4])) == 1
        for t in (1, 2, 3, 0x10, 0x4005, 0x7FFF, 0x0100):
            assert get(w, 0x1000, t) == model.get(t)


def test_a_record_that_does_not_fit_is_refused_whole(w):
    assert put(w, 0x2000, 5, bytes(484)) == 0                  # 4 + 484 = 488: full
    assert put(w, 0x2000, 6, b"x") == -4
    assert put(w, 0x2000, 5, bytes(485)) == -4
    assert get(w, 0x2000, 5) == bytes(484)


def test_invalid_spellings_are_refused(w):
    good = spell({1: b"ab", 2: b""})
    assert w.wish_tlv_valid(good, len(good)) == 1
    for bad in (spell({2: b"a"}) + spell({1: b"b"}),         # out of order
                spell({1: b"a"}) + spell({1: b"b"}),         # repeated
                good[:-1] + b"\x00\x05",                       # runs past the end
                good + b"\x00"):                               # a partial header
        assert w.wish_tlv_valid(bad, len(bad)) == 0


def test_fields_tied_to_the_machine_are_dropped_and_the_rest_kept(w):
    rec = bytearray(spell({0x0001: b"keep", 0x4002: b"drop", 0x8003: b"must", 0xC004: b"both"}))
    rec += bytes(488 - len(rec))
    buf = (ctypes.c_uint8 * 488).from_buffer(rec)
    n = w.wish_tlv_drop_machine(buf, len(spell({0x0001: b"keep", 0x4002: b"drop", 0x8003: b"must", 0xC004: b"both"})))
    assert bytes(rec[:n]) == spell({0x0001: b"keep", 0x8003: b"must"})


# -- the link in the stored sound -----------------------------------------------------------------------------

def link_of(stored: bytes):
    h0, h1, n = ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint32()
    return h0, h1, n


def read_link(lib, stored: bytes):
    h0, h1, n = ctypes.c_uint32(), ctypes.c_uint32(), ctypes.c_uint32()
    buf = (ctypes.c_uint8 * 359).from_buffer_copy(stored)
    ok = lib.wish_link_read(buf, ctypes.byref(h0), ctypes.byref(h1), ctypes.byref(n))
    return (h0.value, h1.value, n.value) if ok else None


def test_the_link_lives_in_the_lane_and_nowhere_else(w):
    rnd = random.Random(3)
    for _ in range(200):
        stored = bytearray(rnd.randrange(256) for _ in range(359))
        before = bytes(stored)
        h0, h1, n = rnd.randrange(1 << 32), rnd.randrange(1 << 32), rnd.randrange(1, 489)
        w.wish_link_write((ctypes.c_uint8 * 359).from_buffer(stored), ctypes.c_uint32(h0), ctypes.c_uint32(h1), n)
        lane = {b for at in LANE.values() for b in (at, at + 1)}
        assert all(stored[k] == before[k] for k in range(359) if k not in lane)
        assert stored[36] == 0x57 and stored[37] == 1
        assert stored[92] == before[92] and stored[93] == before[93]      # id 32: a stock unit's sink, left alone
        assert read_link(w, stored) == (h0, h1, n)


def test_a_lane_that_is_not_our_link_is_no_link(w):
    rnd = random.Random(4)
    assert read_link(w, bytes(359)) is None                    # every stock-saved sound
    stored = bytearray(359)
    w.wish_link_write((ctypes.c_uint8 * 359).from_buffer(stored), 1, 2, 30)
    for at in [b for a in LANE.values() for b in (a, a + 1)]:   # any one byte changed: refused
        for flip in (1, 0x80):
            bad = bytearray(stored)
            bad[at] ^= flip
            assert read_link(w, bad) is None, (at, flip)
    # Overtone 1.2 writes its words at 36, 44, .. 92 (docs/overtone-map.md 1b): random words are never a link
    hits = 0
    for _ in range(20000):
        other = bytearray(359)
        for a in list(LANE.values()) + [92]:
            other[a], other[a + 1] = rnd.randrange(256), rnd.randrange(256)
        other[36] = 0x57 if rnd.random() < 0.5 else other[36]
        other[37] = 1 if rnd.random() < 0.5 else other[37]
        hits += read_link(w, other) is not None
    assert hits == 0


# -- the table under every way a sound moves -------------------------------------------------------------------

def test_copies_carries_and_clears_against_a_model(w):
    rnd = random.Random(5)
    base = 0x41000000
    slots = [base + SOUND * k for k in range(40)]
    model: dict[int, bytes] = {}
    for step in range(3000):
        op = rnd.random()
        if op < 0.3:
            s = rnd.choice(slots)
            v = bytes([step & 255, step >> 8 & 255])
            assert put(w, s, 1, v) == 0
            model[s] = v
        elif op < 0.5:
            d, s = rnd.sample(slots, 2)
            w.wish_on_memcpy(d, s, SOUND)
            if s in model:
                model[d] = model[s]
            else:
                model.pop(d, None)
        elif op < 0.7:
            k = rnd.randrange(1, 6)
            a, b = rnd.randrange(0, 40 - k + 1), rnd.randrange(0, 40 - k + 1)
            if abs(a - b) < k:
                continue                    # memcpy of overlapping blocks is not a thing stock does
            src, dst = slots[a], slots[b]
            w.wish_on_memcpy(dst, src, SOUND * k)
            moved = {dst + (s - src): v for s, v in model.items() if src <= s < src + SOUND * k}
            model = {s: v for s, v in model.items() if not dst <= s < dst + SOUND * k}
            model.update(moved)
        elif op < 0.8:
            k = rnd.randrange(1, 4)
            a = rnd.randrange(0, 40 - k + 1)
            w.wish_on_memset(slots[a], 0, SOUND * k)
            model = {s: v for s, v in model.items() if not slots[a] <= s < slots[a] + SOUND * k}
        elif op < 0.9:
            s = rnd.choice(slots)
            w.wish_drop(s)
            model.pop(s, None)
        else:                               # an unrelated copy that ends inside a sound changes nothing
            s = rnd.choice(slots)
            w.wish_on_memcpy(s + 20, 0x50000000, SOUND)
        for s in slots:
            assert get(w, s, 1) == model.get(s), (step, hex(s))
        assert u32(w, "wish_n") == len(model)
    assert u32(w, "wish_full") == 0


def test_a_block_holding_hundreds_of_records_carries_every_one(w):
    base = 0x43000000
    for k in range(300):
        assert put(w, base + SOUND * k, 1, k.to_bytes(2, "big")) == 0
    w.wish_on_memcpy(base + 0x1000000, base, SOUND * 300)
    assert all(get(w, base + 0x1000000 + SOUND * k, 1) == k.to_bytes(2, "big") for k in range(300))
    assert u32(w, "wish_full") == 0 and u32(w, "wish_n") == 600


def test_a_copy_inside_one_block_moves_overlapping_sounds_whole(w):
    base = 0x42000000
    for k in range(4):
        assert put(w, base + SOUND * k, 1, bytes([k + 1])) == 0
    w.wish_on_memcpy(base + SOUND, base, SOUND * 3)     # an overlapping move by one sound (a memmove)
    assert [get(w, base + SOUND * k, 1) for k in range(4)] == [b"\x01", b"\x01", b"\x02", b"\x03"]


def test_the_table_full_is_counted_and_nothing_is_corrupted(w):
    for k in range(8192):
        assert put(w, 0x10000 + 4 * k, 1, b"x") == 0
    assert put(w, 0x9000000, 1, b"y") == -1
    assert u32(w, "wish_full") >= 1
    assert get(w, 0x10000, 1) == b"x" and get(w, 0x10000 + 4 * 8191, 1) == b"x"
    w.wish_on_memset(0x10000, 0, 4 * 8192)
    assert u32(w, "wish_n") == 0
    assert put(w, 0x9000000, 1, b"y") == 0


def test_a_mutator_that_finds_the_lock_taken_does_nothing_and_counts(w):
    put(w, 0x3000, 1, b"a")
    ctypes.c_uint8.in_dll(w, "wish_busy").value = 0x80
    w.wish_on_memcpy(0x3000 + SOUND, 0x3000, SOUND)
    ctypes.c_uint8.in_dll(w, "wish_busy").value = 0
    assert get(w, 0x3000 + SOUND, 1) is None and u32(w, "wish_reentered") >= 1


# -- load, save, the +Drive -----------------------------------------------------------------------------------

def test_a_stock_saved_sound_loads_with_no_record(w):
    put(w, 0x5000, 1, b"old")
    load(w, 0x5000, bytearray(359))             # a stock save left the lane at zeros
    assert entry(w, 0x5000) is None


def test_the_reference_spellings_are_the_cs(w):
    for fields in ({7: b"routes"}, {1: b"", 0x8001: bytes(range(200)), 3: b"x"}):
        sound = 0x6800 + len(fields)
        for t, v in fields.items():
            put(w, sound, t, v)
        stored = save(w, sound)
        rec = entry(w, sound)[4]
        assert rec == spell({t: v for t, v in fields.items() if v})
        assert all(stored[k] == v for k, v in link_bytes(rec).items())
        settle(w)
        h0 = read_link(w, stored)[0]
        disk = w.host_disk()
        assert bytes(disk[512 * (h0 % CELLS):512 * (h0 % CELLS) + 512]) == cell_bytes(rec)


def test_save_links_and_the_cell_reaches_the_drive_after_settling(w):
    put(w, 0x6000, 7, b"routes")
    stored = save(w, 0x6000)
    h0, h1, n = read_link(w, stored)
    assert n == len(spell({7: b"routes"}))
    e = entry(w, 0x6000)
    assert (e[0], e[1]) == (h0, h1) and e[3] & W_DISK and not e[3] & W_DIRTY
    assert (h0, h1) == (xxh32(e[4], 0x57495348), xxh32(e[4], 0x4E324D58))
    w.wish_poll()
    assert u32(w, "wish_cells_written") == 0                    # not before SETTLE
    settle(w)
    assert u32(w, "wish_cells_written") == 1
    disk = w.host_disk()
    cell = bytes(disk[512 * (h0 % CELLS):512 * (h0 % CELLS) + 512])
    assert cell[:4] == b"DN2W" and cell[20:20 + n] == e[4]


def test_a_project_write_flushes_at_once(w):
    put(w, 0x6100, 7, b"x")
    save(w, 0x6100)
    w.wish_poll()                                               # notes the slot head
    ctypes.c_uint32.in_dll(w, "ins_wr_head").value += 1
    w.wish_poll()
    assert u32(w, "wish_cells_written") == 1


def test_power_off_and_on_the_record_comes_back_from_its_link(w):
    put(w, 0x7000, 3, b"lfo1->freq")
    stored = save(w, 0x7000)
    settle(w)
    w.host_reboot()
    load(w, 0x7123, stored)
    e = entry(w, 0x7123)
    assert e[3] & W_WANT and get(w, 0x7123, 3) is None            # plays stock until read
    assert put(w, 0x7123, 3, b"no") == -2                         # and cannot be edited before
    settle(w, 2)
    assert get(w, 0x7123, 3) == b"lfo1->freq" and u32(w, "wish_resolved") == 1
    assert entry(w, 0x7123)[3] == W_DISK


def test_a_second_load_of_a_known_record_needs_no_read(w):
    put(w, 0x7200, 3, b"r")
    stored = save(w, 0x7200)
    reads = u32(w, "host_reads")
    load(w, 0x8000, stored)
    assert get(w, 0x8000, 3) == b"r" and u32(w, "host_reads") == reads


def test_the_same_record_twice_is_one_cell(w):
    for s in (0x9000, 0x9100):
        put(w, s, 3, b"same")
        save(w, s)
    settle(w)
    assert u32(w, "wish_cells_written") == 1


def test_power_cut_before_the_cell_keeps_the_link_and_plays_stock(w):
    put(w, 0xA000, 3, b"lost")
    stored = save(w, 0xA000)
    w.host_reboot()                                             # before SETTLE: the cell never written
    load(w, 0xA000, stored)
    settle(w, 2)
    e = entry(w, 0xA000)
    assert e[3] & W_MISSING and get(w, 0xA000, 3) is None and u32(w, "wish_missing") == 1
    resaved = save(w, 0xA000)                                  # the link stays: the record may arrive later
    assert read_link(w, resaved) == read_link(w, stored)
    settle(w)
    assert u32(w, "wish_cells_written") == 0


def test_a_torn_cell_reads_as_empty_and_is_written_over(w):
    put(w, 0xB000, 3, b"torn")
    stored = save(w, 0xB000)
    h0 = read_link(w, stored)[0]
    disk = w.host_disk()
    at = 512 * (h0 % CELLS)
    for k, b in enumerate(b"DN2W\x01\x01\x00\x08"):             # half a cell: a header, no check
        disk[at + k] = b
    settle(w)
    assert u32(w, "wish_cells_written") == 1
    w.host_reboot()
    load(w, 0xB000, stored)
    settle(w, 2)
    assert get(w, 0xB000, 3) == b"torn"


def test_records_that_share_a_home_cell_both_come_back(w):
    rnd = random.Random(6)
    stored = []
    for k in range(300):
        put(w, 0xC000 + k, 3, bytes([k & 255, k >> 8, rnd.randrange(256)]))
        stored.append(save(w, 0xC000 + k))
    # crowd one stretch: every cell around the first record's home cell already taken by a foreign cell
    h0 = read_link(w, stored[0])[0]
    disk = w.host_disk()
    for i in range(5):
        at = 512 * ((h0 + i) % CELLS)
        foreign = bytearray(512)
        foreign[:8] = b"DN2W\x01\x01\x00\x00"
        foreign[8:16] = (i + 77).to_bytes(4, "big") * 2
        a, b = 1, 0
        for x in foreign[:508]:
            a += x
            b += a
        foreign[508:] = (((b << 16 ^ a) & 0xFFFFFFFF) ^ 0x57495348).to_bytes(4, "big")
        for k, x in enumerate(foreign):
            disk[at + k] = x
    settle(w, 200)
    assert u32(w, "wish_cells_written") == 300
    w.host_reboot()
    for k, st in enumerate(stored):
        load(w, 0xD000 + k, st)
    settle(w, 200)
    assert all(get(w, 0xD000 + k, 3) is not None for k in range(300))


def test_erase_mod_data_stops_every_write(w):
    put(w, 0xE000, 3, b"e")
    save(w, 0xE000)
    ctypes.c_int.in_dll(w, "smp_er_lock").value = 1
    settle(w)
    assert u32(w, "host_writes") == 0


def test_a_failing_drive_keeps_the_cell_queued(w):
    put(w, 0xE100, 3, b"f")
    save(w, 0xE100)
    ctypes.c_int.in_dll(w, "host_fail").value = 1
    settle(w, 4)
    assert u32(w, "wish_cells_written") == 0 and u32(w, "wish_io_fails") > 0
    ctypes.c_int.in_dll(w, "host_fail").value = 0
    settle(w)
    assert u32(w, "wish_cells_written") == 1


def test_a_full_queue_counts_what_it_could_not_keep(w):
    ctypes.c_uint.in_dll(w, "host_ready").value = 0             # the +Drive not up: nothing drains
    try:
        for k in range(514):
            put(w, 0xF000 + k, 3, k.to_bytes(2, "big"))
            save(w, 0xF000 + k)
        assert u32(w, "wish_pend_lost") == 2
        assert sum(1 for k in range(514) if entry(w, 0xF000 + k)[3] & W_DISK) == 512
    finally:
        ctypes.c_uint.in_dll(w, "host_ready").value = 1
    settle(w, 400)                                              # ... and queued again once there is room
    assert u32(w, "wish_cells_written") == 514
    assert all(entry(w, 0xF000 + k)[3] & W_DISK for k in range(514))


def test_a_field_this_build_must_understand_and_does_not_locks_the_record(w):
    put(w, 0x11000, 0x8001, b"future")                           # as a later build would have written it
    stored = save(w, 0x11000)
    settle(w)
    w.host_reboot()
    load(w, 0x11000, stored)
    settle(w, 2)
    assert entry(w, 0x11000)[3] & W_LOCKED
    assert put(w, 0x11000, 1, b"edit") == -3
    assert read_link(w, save(w, 0x11000)) == read_link(w, stored)    # carried and saved unchanged


def test_an_unknown_field_survives_an_edit_by_this_build(w):
    put(w, 0x12000, 0x0123, b"later feature")
    stored = save(w, 0x12000)
    settle(w)
    w.host_reboot()
    load(w, 0x12000, stored)
    settle(w, 2)
    assert put(w, 0x12000, 1, b"mine") == 0
    assert get(w, 0x12000, 0x0123) == b"later feature"
    assert read_link(w, save(w, 0x12000)) != read_link(w, stored)


def test_removing_the_last_field_removes_the_link(w):
    put(w, 0x13000, 1, b"a")
    save(w, 0x13000)
    put(w, 0x13000, 1, b"")
    stored = save(w, 0x13000)
    assert read_link(w, stored) is None and entry(w, 0x13000) is None


# -- travel: PUT and GET over our SysEx channel (link.c 12, 13) ------------------------------------------------

def rx(lib, cmd: int, args: bytes) -> tuple[int, bytes]:
    """-> (status, reply data): wish_rx as link.c's smp_rx calls it (the request: seq, cmd, arguments)"""
    rq = b"\x12\x34" + bytes([cmd]) + args
    rp = ctypes.create_string_buffer(160)
    st = ctypes.cast(ctypes.byref(rp, 3), ctypes.POINTER(ctypes.c_uint8))
    r = lib.wish_rx(cmd, rq, len(rq), rp, 4, st)
    return rp.raw[3], rp.raw[4:r]


def get_all(lib, h0: int, h1: int) -> tuple[int, bytes]:
    """-> (status, record): GET chunk by chunk from offset 0"""
    out, off = b"", 0
    while True:
        st, d = rx(lib, 13, h0.to_bytes(4, "big") + h1.to_bytes(4, "big") + off.to_bytes(2, "big"))
        if st:
            return st, out
        n = int.from_bytes(d[:2], "big")
        assert int.from_bytes(d[2:4], "big") == off
        out += d[4:]
        off += len(d) - 4
        if off >= n:
            return 0, out


def test_a_record_put_reaches_the_sound_waiting_for_it_and_its_cell(w):
    rec = spell({0x10: bytes(range(200)), 0x11: b"\x08\x7f\x20\x60\x18\x01\x01\x00"})
    put(w, 0xC000, 0x10, bytes(range(200)))
    put(w, 0xC000, 0x11, b"\x08\x7f\x20\x60\x18\x01\x01\x00")
    stored = save(w, 0xC000)                                   # another unit's preset: its link, no cell here
    w.host_erase()
    w.host_reboot()
    load(w, 0xC000, stored)
    settle(w, 2)
    assert entry(w, 0xC000)[3] & W_MISSING
    st, d = rx(w, 12, len(rec).to_bytes(2, "big") + rec)
    assert st == 0 and d == xxh32(rec, 0x57495348).to_bytes(4, "big") + xxh32(rec, 0x4E324D58).to_bytes(4, "big")
    assert rx(w, 12, len(rec).to_bytes(2, "big") + rec)[0] == 5       # one at a time, until the UI loop files it
    settle(w)
    assert get(w, 0xC000, 0x10) == bytes(range(200)) and entry(w, 0xC000)[3] == W_DISK
    assert u32(w, "wish_cells_written") == 1 and u32(w, "wish_put_wait") == 0
    w.host_reboot()                                            # and it stays: the cell is on the +Drive
    load(w, 0xC100, stored)
    settle(w, 2)
    assert get(w, 0xC100, 0x10) == bytes(range(200))


def test_a_put_that_is_not_a_record_is_refused(w):
    for bad in (b"", b"\x00\x05abc", (489).to_bytes(2, "big") + bytes(489), b"\x00\x03\x00\x10\x00"):
        assert rx(w, 12, bad)[0] == 1
    rec = spell({0x20: b"x", 0x10: b"y"})[::-1]                  # tags out of order: no record of ours
    assert rx(w, 12, len(rec).to_bytes(2, "big") + rec)[0] == 1 and u32(w, "wish_put_wait") == 0


def test_get_answers_from_ram_in_chunks(w):
    put(w, 0xD000, 0x10, bytes(range(256)) + bytes(200))
    stored = save(w, 0xD000)
    h0, h1, n = read_link(w, stored)
    st, rec = get_all(w, h0, h1)
    assert st == 0 and rec == entry(w, 0xD000)[4] and len(rec) == n and u32(w, "host_reads") == 0


def test_get_reads_the_cell_when_no_sound_holds_it(w):
    put(w, 0xE000, 0x10, b"from the drive")
    stored = save(w, 0xE000)
    settle(w)
    w.host_reboot()                                            # RAM lost, the cell kept
    h0, h1, _ = read_link(w, stored)
    assert get_all(w, h0, h1)[0] == 5                          # asked: the UI loop reads it
    settle(w, 1)
    st, rec = get_all(w, h0, h1)
    assert st == 0 and rec == spell({0x10: b"from the drive"})


def test_get_of_a_record_this_drive_has_not_says_so(w):
    assert get_all(w, 0x1234, 0x5678)[0] == 5
    settle(w, 1)
    assert get_all(w, 0x1234, 0x5678)[0] == 3


def test_the_hosts_link_and_hash_are_the_firmwares(w):
    from dnfw.wishes import record as R
    for fields in ({0x10: b"routes"}, {0x10: bytes(300), 0x11: bytes(range(8))}):
        rec = spell(fields)
        s = 0xF000
        for t, v in fields.items():
            put(w, s, t, v)
        stored = bytes(save(w, s))
        assert R.write_link(bytes(359), rec) == stored and R.read_link(stored).matches(rec)
        w.wish_drop(ctypes.c_uint32(s))


def test_the_hosts_client_puts_and_gets_through_the_channels_framing(w):
    """dnfw.wishes.travel's Unit over the SysEx bytes, wish_rx answering as link.c's smp_rx frames it"""
    from dnfw.wishes import record as R
    from dnfw.wishes import travel as T

    def exchange(msg: bytes) -> bytes:
        rq = T.unpack7(msg[6:-1])
        rp = ctypes.create_string_buffer(160)
        rp.raw = rq[:2] + bytes([rq[2] | 0x80, 0]) + bytes(156)
        st = ctypes.cast(ctypes.byref(rp, 3), ctypes.POINTER(ctypes.c_uint8))
        r = w.wish_rx(rq[2], rq, len(rq), rp, 4, st)
        return T.HEADER + T.pack7(rp.raw[:r]) + b"\xF7"

    unit = T.Unit(exchange, wait=lambda s: settle(w, 1))
    rec = spell({0x10: bytes(range(250)), 0x11: bytes(8)})
    assert unit.put(rec) == R.hash_of(rec)
    settle(w)
    w.host_reboot()                                            # only the cell left: GET reads it
    link = R.Link(*R.hash_of(rec), len(rec))
    assert unit.get(link) == rec
    assert unit.get(R.Link(1, 2, 10)) is None
