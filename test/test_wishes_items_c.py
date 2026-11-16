"""The wishes record on kits and patterns (csrc/wishes/item.c, docs/wishes-record.md "Every item type"), compiled
for the host with the rest of csrc/wishes and driven through ctypes: where each item's link lives in its stored
object, that nothing else in the stored bytes changes, that a load brings the record back, that a copy or a clear
of the live object carries or drops it (the same stubs as sounds), and that the cell on the +Drive says what it
holds. The hooks at stock's kit and pattern loader and saver are the emulator's (scripts/emu_wishes_items.py)."""

from __future__ import annotations

import ctypes
import random
import shutil
import subprocess

import pytest

from .test_wishes_c import HARNESS, HOST_H, SRC, settle, xxh32

SOURCES = [SRC / "table.c", SRC / "tlv.c", SRC / "store.c", SRC / "item.c"]
WI_KIT, WI_PATTERN = 2, 3
KIT0, KIT_BYTES, KIT_STORED, KIT_LANE = 0x4210D08C, 23921, 10752, 10416
PAT0, PAT_BYTES, PAT_STORED, LOCKS, RECS, REC = 0x4121998C, 122478, 89088, 68148, 80, 258
SOUND = 1163
TAG = 0x0100                                   # a kit-level field (any tag: item.c is tag-blind)
CELL0, CELLS = 0x6F0800, 59392


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("wishitems")
    (d / "host.h").write_text(HOST_H)
    (d / "harness.c").write_text(HARNESS)
    out = d / "libwishitems.so"
    r = subprocess.run([cc, "-shared", "-fPIC", "-O1", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-DWISH_HOST", "-include", str(d / "host.h"), f"-I{SRC}",
                        *map(str, SOURCES), str(d / "harness.c"), "-o", str(out)],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr)
    L = ctypes.CDLL(str(out))
    L.wish_find.restype = ctypes.c_void_p
    L.wish_item.restype = ctypes.c_uint32
    L.host_disk.restype = ctypes.POINTER(ctypes.c_uint8)
    return L


@pytest.fixture()
def w(lib):
    lib.host_erase()
    lib.host_reboot()
    lib.host_zero()
    for name in ("wish_item_loads", "wish_item_saves", "wish_item_nolane"):
        ctypes.c_uint32.in_dll(lib, name).value = 0
    ctypes.c_uint32.in_dll(lib, "wish_item_dropped").value = 0xFFFFFFFF
    ctypes.c_uint.in_dll(lib, "host_frames").value = 0
    return lib


def u32(lib, name):
    return ctypes.c_uint32.in_dll(lib, name).value


def put(lib, live, tag, value: bytes) -> int:
    return lib.wish_put(ctypes.c_uint32(live), ctypes.c_uint32(tag), value, len(value))


def get(lib, live, tag):
    out = ctypes.create_string_buffer(488)
    n = lib.wish_get(ctypes.c_uint32(live), ctypes.c_uint32(tag), out, 488)
    return None if n < 0 else out.raw[:n]


def call(fn, a, b, buf: bytearray, stored_first: bool):
    cbuf = (ctypes.c_uint8 * len(buf)).from_buffer(buf)
    if stored_first:
        fn(cbuf, ctypes.c_uint32(b))
    else:
        fn(ctypes.c_uint32(a), cbuf)


def link(rec: bytes) -> bytes:
    """-> the 14 contiguous bytes item.c writes for REC (the sound link's words, in a row)"""
    h0, h1 = xxh32(rec, 0x57495348), xxh32(rec, 0x4E324D58)
    seed = 0x5701 ^ h0 ^ (((h1 << 7) | (h1 >> 25)) & 0xFFFFFFFF) ^ (len(rec) << 16)
    x = xxh32(b"", seed & 0xFFFFFFFF)
    return (b"\x57\x01" + h0.to_bytes(4, "big") + h1.to_bytes(4, "big") + len(rec).to_bytes(2, "big")
            + ((x ^ (x >> 16)) & 0xFFFF).to_bytes(2, "big"))


def record(tag, value: bytes) -> bytes:
    return tag.to_bytes(2, "big") + len(value).to_bytes(2, "big") + value


def noisy(n: int, seed: int) -> bytearray:
    return bytearray(random.Random(seed).randbytes(n))


# -- the kit ---------------------------------------------------------------------------------------------------

def kit_save(lib, live, stored):
    call(lib.wish_kit_save, 0, live, stored, True)


def kit_load(lib, live, stored):
    call(lib.wish_kit_load, live, 0, stored, False)


def test_the_kits_and_patterns_live_where_stock_keeps_them(w):
    assert w.wish_item(WI_KIT, 0) == KIT0
    assert w.wish_item(WI_KIT, 128) == KIT0 + 128 * KIT_BYTES          # the 129th: KitActive's array
    assert w.wish_item(WI_KIT, 129) == 0
    assert w.wish_item(WI_PATTERN, 127) == PAT0 + 127 * PAT_BYTES
    assert w.wish_item(WI_PATTERN, 128) == 0
    assert w.wish_item(1, 0) == 0                                       # a sound is named by its own address


def test_a_kit_link_lies_past_the_terminator_and_nothing_else_changes(w):
    kit = w.wish_item(WI_KIT, 3)
    assert put(w, kit, TAG, b"\x01") == 0
    stored = noisy(KIT_STORED, 1)
    before = bytes(stored)
    kit_save(w, kit, stored)
    lane = slice(KIT_LANE, KIT_LANE + 14)
    assert bytes(stored[lane]) == link(record(TAG, b"\x01"))
    assert stored[:KIT_LANE] == before[:KIT_LANE] and stored[KIT_LANE + 14:] == before[KIT_LANE + 14:]


def test_a_kit_with_no_record_saves_zeros_there(w):
    stored = noisy(KIT_STORED, 2)
    kit_save(w, w.wish_item(WI_KIT, 0), stored)
    assert stored[KIT_LANE:KIT_LANE + 14] == bytes(14)


def test_a_kit_load_brings_the_record_and_a_stock_kit_drops_it(w):
    a, b = w.wish_item(WI_KIT, 0), w.wish_item(WI_KIT, 128)
    put(w, a, TAG, b"JUNO")
    stored = bytearray(KIT_STORED)
    kit_save(w, a, stored)
    kit_load(w, b, stored)
    assert get(w, b, TAG) == b"JUNO"
    kit_load(w, b, bytearray(KIT_STORED))                               # stock's zeros: no record
    assert get(w, b, TAG) is None and not w.wish_find(ctypes.c_uint32(b))


def test_a_kit_record_survives_a_power_cycle_through_its_cell(w):
    a = w.wish_item(WI_KIT, 5)
    put(w, a, TAG, b"\x02")
    stored = bytearray(KIT_STORED)
    kit_save(w, a, stored)
    settle(w)
    assert u32(w, "wish_cells_written") == 1
    disk = w.host_disk()
    h0 = xxh32(record(TAG, b"\x02"), 0x57495348)
    cell = bytes(disk[512 * (h0 % CELLS) + k] for k in range(512))
    assert cell[:4] == b"DN2W" and cell[5] == WI_KIT                    # the cell says it holds a kit's record
    w.host_reboot()
    kit_load(w, a, stored)
    assert get(w, a, TAG) is None                                       # waiting for its cell
    settle(w)
    assert get(w, a, TAG) == b"\x02"


def test_a_kit_copy_carries_its_record_and_its_sounds_and_a_clear_drops_them(w):
    a, b = w.wish_item(WI_KIT, 1), w.wish_item(WI_KIT, 128)
    put(w, a, TAG, b"\x01")
    snd = a + 52 + 1163 * 7                                             # its track 8 sound
    put(w, snd, 0x0010, b"route")
    w.wish_on_memcpy(ctypes.c_uint32(b), ctypes.c_uint32(a), ctypes.c_uint32(KIT_BYTES))
    assert get(w, b, TAG) == b"\x01" and get(w, b + 52 + 1163 * 7, 0x0010) == b"route"
    w.wish_on_memset(ctypes.c_uint32(b), 0, ctypes.c_uint32(KIT_BYTES))
    assert get(w, b, TAG) is None and get(w, b + 52 + 1163 * 7, 0x0010) is None
    assert get(w, a, TAG) == b"\x01"


def test_a_copy_of_one_sound_inside_a_kit_leaves_the_kits_record(w):
    a = w.wish_item(WI_KIT, 2)
    put(w, a, TAG, b"\x01")
    w.wish_on_memcpy(ctypes.c_uint32(a + 52), ctypes.c_uint32(a + 52 + SOUND), ctypes.c_uint32(SOUND))
    w.wish_on_memset(ctypes.c_uint32(a + 52), 0, ctypes.c_uint32(SOUND))
    assert get(w, a, TAG) == b"\x01"


# -- the pattern -----------------------------------------------------------------------------------------------

def pat_save(lib, live, stored):
    call(lib.wish_pattern_save, 0, live, stored, True)


def pat_load(lib, live, stored):
    call(lib.wish_pattern_load, live, 0, stored, False)


def pool(used: set[int], seed: int) -> bytearray:
    """a stored pattern whose lock records USED hold locks, the others stock's unused (FF FF, a body never written)"""
    stored = noisy(PAT_STORED, seed)
    for i in range(RECS):
        at = LOCKS + REC * i
        if i in used:
            stored[at:at + 2] = bytes([5, i % 16])
        else:
            stored[at:at + 2] = b"\xff\xff"
    return stored


def test_a_pattern_link_goes_into_the_last_unused_lock_record(w):
    p = w.wish_item(WI_PATTERN, 9)
    put(w, p, TAG, b"pat")
    stored = pool({0, 1, 2, 79}, 3)
    before = bytes(stored)
    pat_save(w, p, stored)
    at = LOCKS + REC * 78 + 2
    assert bytes(stored[at:at + 14]) == link(record(TAG, b"pat"))
    for i in range(RECS):                                               # only unused bodies' first 14 B touched
        r = LOCKS + REC * i
        if i in (0, 1, 2, 79):
            assert stored[r:r + REC] == before[r:r + REC]
        elif i != 78:
            assert stored[r + 2:r + 16] == bytes(14) and stored[r + 16:r + REC] == before[r + 16:r + REC]
    assert stored[:LOCKS] == before[:LOCKS] and stored[LOCKS + REC * RECS:] == before[LOCKS + REC * RECS:]


def test_a_pattern_load_finds_the_link_and_an_old_link_elsewhere_is_gone(w):
    p, q = w.wish_item(WI_PATTERN, 0), w.wish_item(WI_PATTERN, 1)
    put(w, p, TAG, b"one")
    stored = pool({79}, 4)
    pat_save(w, p, stored)                                              # in record 78
    put(w, p, TAG, b"two")
    stored[LOCKS + REC * 78:LOCKS + REC * 78 + 2] = bytes([7, 3])       # 78 now holds a lock
    pat_save(w, p, stored)                                              # in record 77; 78's body is the lock's
    stored[LOCKS + REC * 78 + 2:LOCKS + REC * 78 + REC] = noisy(REC - 2, 5)
    pat_load(w, q, stored)
    assert get(w, q, TAG) == b"two"


def full_pool(steps: dict[int, int], seed: int, head=lambda i: bytes([5, i % 16])) -> bytearray:
    """every lock record in use; record i locks STEPS.get(i, 128) steps (the rest FF FF)"""
    stored = pool(set(range(RECS)), seed)
    for i in range(RECS):
        at = LOCKS + REC * i
        n = steps.get(i, 128)
        stored[at:at + 2] = head(i)
        stored[at + 2:at + REC] = b"\x10\x00" * n + b"\xff\xff" * (128 - n)
    return stored


def test_with_every_lock_record_used_the_one_with_fewest_steps_gives_way(w):
    p, q = w.wish_item(WI_PATTERN, 4), w.wish_item(WI_PATTERN, 5)
    put(w, p, TAG, b"full")
    stored = full_pool({7: 3, 40: 2, 41: 9}, 6)
    before = bytes(stored)
    pat_save(w, p, stored)
    at = LOCKS + REC * 40
    assert stored[at:at + 2] == b"\xff\xff" and bytes(stored[at + 2:at + 16]) == link(record(TAG, b"full"))
    diff = [k for k in range(PAT_STORED) if stored[k] != before[k]]
    assert all(at <= k < at + 16 for k in diff)                      # nothing else changed
    assert u32(w, "wish_item_nolane") == 1
    assert u32(w, "wish_item_dropped") == 2 << 16 | (40 % 16) << 8 | 5  # 2 steps, track 8, id 5
    pat_load(w, q, stored)
    assert get(w, q, TAG) == b"full"


def test_on_a_tie_the_last_of_the_fewest_gives_way(w):
    p = w.wish_item(WI_PATTERN, 6)
    put(w, p, TAG, b"tie")
    stored = full_pool({3: 1, 50: 1, 60: 4}, 7)
    pat_save(w, p, stored)
    assert stored[LOCKS + REC * 50:LOCKS + REC * 50 + 2] == b"\xff\xff"
    assert stored[LOCKS + REC * 3] == 5


def test_a_pattern_with_no_record_keeps_all_80_locks(w):
    stored = full_pool({9: 1}, 8)
    before = bytes(stored)
    pat_save(w, w.wish_item(WI_PATTERN, 7), stored)
    assert bytes(stored) == before and u32(w, "wish_item_nolane") == 0


def test_slides_records_never_give_way_and_with_no_stock_lock_the_record_stays_in_ram(w):
    p, q = w.wish_item(WI_PATTERN, 8), w.wish_item(WI_PATTERN, 9)
    put(w, p, TAG, b"ram")
    stored = full_pool({2: 1}, 9, head=lambda i: bytes([200 + i % 3, i % 16]))   # SLD / SLEN / REC
    before = bytes(stored)
    pat_save(w, p, stored)
    assert bytes(stored) == before and u32(w, "wish_item_nolane") == 1
    assert get(w, p, TAG) == b"ram"
    pat_load(w, q, stored)
    assert get(w, q, TAG) is None


def test_a_pattern_copy_and_clear(w):
    p, q = w.wish_item(WI_PATTERN, 10), w.wish_item(WI_PATTERN, 11)
    put(w, p, TAG, b"x")
    w.wish_on_memcpy(ctypes.c_uint32(q), ctypes.c_uint32(p), ctypes.c_uint32(PAT_BYTES))
    assert get(w, q, TAG) == b"x"
    w.wish_on_memset(ctypes.c_uint32(p), 0, ctypes.c_uint32(PAT_BYTES))
    assert get(w, p, TAG) is None and get(w, q, TAG) == b"x"


def test_unused_records_bodies_that_are_noise_are_no_link(w):
    q = w.wish_item(WI_PATTERN, 2)
    hits = 0
    for seed in range(200):
        pat_load(w, q, pool(set(), 1000 + seed))
        hits += get(w, q, TAG) is not None or bool(w.wish_find(ctypes.c_uint32(q)))
    assert hits == 0


# -- the song and the project's settings: the link in the tail stock zeroes ------------------------------------

WI_SONG, WI_PROJECT = 4, 5
SONG0, SONG_BYTES, SONG_STORED, SONG_LANE = 0x423FE67D, 3694, 3072, 2900
PS, PS_STORED, PS_LANE = 0x42432A61, 1024, 544


def test_songs_and_the_project_settings_live_where_stock_keeps_them(w):
    assert w.wish_item(WI_SONG, 0) == SONG0 and w.wish_item(WI_SONG, 16) == SONG0 + 16 * SONG_BYTES
    assert w.wish_item(WI_SONG, 17) == 0
    assert w.wish_item(WI_PROJECT, 0) == PS and w.wish_item(WI_PROJECT, 1) == 0


@pytest.mark.parametrize("kind,index,n,lane,save,load", [
    (WI_SONG, 3, SONG_STORED, SONG_LANE, "wish_song_save", "wish_song_load"),
    (WI_PROJECT, 0, PS_STORED, PS_LANE, "wish_settings_save", "wish_settings_load")])
def test_a_song_or_the_settings_round_trip_with_only_the_link_written(w, kind, index, n, lane, save, load):
    live = w.wish_item(kind, index)
    stored0 = noisy(n, kind)
    call(getattr(w, save), 0, live, stored0, True)
    assert stored0[lane:lane + 14] == bytes(14)
    put(w, live, TAG, b"tail")
    stored1 = noisy(n, kind)
    before = bytes(stored1)
    call(getattr(w, save), 0, live, stored1, True)
    assert bytes(stored1[lane:lane + 14]) == link(record(TAG, b"tail"))
    assert stored1[:lane] == before[:lane] and stored1[lane + 14:] == before[lane + 14:]
    other = live + 1 if kind == WI_PROJECT else w.wish_item(kind, 0)
    call(getattr(w, load), other, 0, stored1, False)
    assert get(w, other, TAG) == b"tail"
    call(getattr(w, load), other, 0, stored0, False)
    assert get(w, other, TAG) is None
