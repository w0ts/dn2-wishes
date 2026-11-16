"""LFO4's values in the wishes record (csrc/wishes/lfo4.c, DN2_LFO4; docs/lfo-112-port.md 4.1, the User: "Into the
wishes record"), compiled for the host with table.c, tlv.c and store.c, lfo4's own table (csrc/lfo4/ext.c) stood in
for by a small one here with its four entry points: save puts LFO4's values in the record as a field (none at the
defaults), a sound loaded with no link (a stock one, or one saved by upstream's 1.11 lfo4) has LFO4 at its defaults,
and a linked one gets its values once its record is in RAM."""

from __future__ import annotations

import ctypes
import pathlib
import shutil
import struct
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "csrc" / "wishes"
SOURCES = [SRC / "table.c", SRC / "tlv.c", SRC / "store.c", SRC / "lfo4.c"]
WT_LFO4 = 0x0012
DEFAULTS = [0x4000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x4000]   # any: the stand-in's own

HOST_H = r"""
#define DN2_LFO4 1
extern int host_blk_read(unsigned s, unsigned n, void *p);
extern int host_blk_write(unsigned s, unsigned n, const void *p);
extern unsigned host_ready, host_sectors, host_frames;
#define WISH_BLK_READ(s, n, p) host_blk_read(s, n, p)
#define WISH_BLK_WRITE(s, n, p) host_blk_write(s, n, p)
#define WISH_BLK_READY host_ready
#define WISH_BLK_SECTORS host_sectors
#define WISH_FRAMES host_frames
extern unsigned short *host_ext_find(unsigned key);
extern void host_ext_set(unsigned key, unsigned param, unsigned value);
extern void host_ext_drop(unsigned key);
extern unsigned short host_ext_default[8];
#define LFO4_EXT_FIND ((unsigned long)host_ext_find)
#define LFO4_EXT_SET ((unsigned long)host_ext_set)
#define LFO4_EXT_DROP ((unsigned long)host_ext_drop)
#define LFO4_EXT_DEFAULT ((unsigned long)host_ext_default)
"""

HARNESS = r"""
#include <string.h>
#include "wish.h"
u8 wish_host_area[WISH_O_END] __attribute__((aligned(16)));
int smp_er_lock = 0;
volatile u32 ins_wr_head = 0;
unsigned host_ready = 1, host_sectors = 0x800000, host_frames = 0;
u32 host_shift_moves = 0;
int host_blk_read(unsigned s, unsigned n, void *p) { (void)s; memset(p, 0, n); return 0; }
int host_blk_write(unsigned s, unsigned n, const void *p) { (void)s; (void)n; (void)p; return 0; }
/* lfo4's table, stood in for: 16 keys, eight values each, and the defaults */
unsigned short host_ext_default[8] = {0x4000, 0, 0, 0, 0, 0, 0, 0x4000};
unsigned host_keys[16];
unsigned short host_vals[16][8];
unsigned host_sets = 0, host_drops = 0;
unsigned short *host_ext_find(unsigned key)
{
    for (int k = 0; k < 16; k++) if (host_keys[k] == key && key) return host_vals[k];
    return 0;
}
void host_ext_set(unsigned key, unsigned param, unsigned value)
{
    unsigned short *v = host_ext_find(key);
    for (int k = 0; !v && k < 16; k++)
        if (!host_keys[k]) { host_keys[k] = key; memcpy(host_vals[k], host_ext_default, 16); v = host_vals[k]; }
    if (v) v[param] = (unsigned short)value;
    host_sets++;
}
void host_ext_drop(unsigned key)
{
    for (int k = 0; k < 16; k++) if (host_keys[k] == key) host_keys[k] = 0;
    host_drops++;
}
void host_reset(void)
{
    memset(host_keys, 0, sizeof host_keys);
    host_sets = host_drops = 0;
    wish_ready = 0;
    wish_busy = 0;
    wish_init();
}
"""


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("wishes_lfo4")
    (d / "host.h").write_text(HOST_H)
    (d / "harness.c").write_text(HARNESS)
    out = d / "libwl4.so"
    r = subprocess.run([cc, "-shared", "-fPIC", "-O1", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-Wno-int-to-pointer-cast", "-DWISH_HOST", "-include", str(d / "host.h"), f"-I{SRC}",
                        *map(str, SOURCES), str(d / "harness.c"), "-o", str(out)], capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr)
    L = ctypes.CDLL(str(out))
    L.wish_find.restype = ctypes.c_void_p
    L.host_ext_find.restype = ctypes.POINTER(ctypes.c_uint16)
    return L


@pytest.fixture()
def w(lib):
    lib.host_reset()
    return lib


def u32(lib, name):
    return ctypes.c_uint32.in_dll(lib, name).value


def lfo4_values(lib, key):
    p = lib.host_ext_find(ctypes.c_uint(key))
    return [p[k] for k in range(8)] if p else None


def set_lfo4(lib, key, values):
    for k, v in enumerate(values):
        lib.host_ext_set(ctypes.c_uint(key), ctypes.c_uint(k), ctypes.c_uint(v))


def field(lib, key):
    """-> the record's WT_LFO4 value (16 bytes) or None"""
    b = ctypes.create_string_buffer(64)
    n = lib.wish_get(ctypes.c_uint32(key), ctypes.c_uint32(WT_LFO4), b, 64)
    return b.raw[:n] if n >= 0 else None


def test_save_puts_lfo4_in_the_record_and_links_the_sound(w):
    live, stored = 0x42100000, ctypes.create_string_buffer(359)
    vals = [0x5800, 0x0300, 0x1000, 0x0700, 0x0900, 0x2000, 0x0100, 0x7F00]
    set_lfo4(w, live, vals)
    w.wish_save(stored, ctypes.c_uint32(live))
    assert field(w, live) == b"".join(struct.pack(">H", v) for v in vals)
    assert stored.raw[36] == 0x57 and u32(w, "wish_links_out") == 1     # 'W': the lane is the link
    assert u32(w, "wish_lfo4_out") == 1


def test_lfo4_at_its_defaults_makes_no_field_and_no_record(w):
    live, stored = 0x42100000, ctypes.create_string_buffer(359)
    w.wish_save(stored, ctypes.c_uint32(live))
    assert not w.wish_find(ctypes.c_uint32(live)) and stored.raw[36] != 0x57


def test_back_at_the_defaults_drops_the_field(w):
    live, stored = 0x42100000, ctypes.create_string_buffer(359)
    set_lfo4(w, live, [0x5800] + [0] * 6 + [0x4000])
    w.wish_save(stored, ctypes.c_uint32(live))
    w.host_ext_drop(ctypes.c_uint(live))
    w.wish_save(stored, ctypes.c_uint32(live))
    assert field(w, live) is None


def test_a_sound_loaded_with_no_link_has_lfo4_at_its_defaults(w):
    """a stock sound, or one saved by upstream's 1.11 lfo4 (its LFO4 values in the lane, not a link)"""
    live = 0x42100000
    set_lfo4(w, live, [0x5800] + [0] * 7)
    lane = bytearray(359)
    for k, i in enumerate(range(36, 52, 2)):                        # 1.11 lfo4's values at ids 4..32
        struct.pack_into(">H", lane, i, 0x1234 + k)
    w.wish_load(ctypes.c_uint32(live), bytes(lane))
    assert lfo4_values(w, live) is None and u32(w, "wish_lfo4_reset") == 1


def test_a_linked_sound_gets_its_values_once_its_record_is_in_ram(w):
    src, dst, stored = 0x42100000, 0x42200000, ctypes.create_string_buffer(359)
    vals = [0x6000, 0x0400, 0, 0x0800, 0x0A00, 0x3000, 0x0200, 0x6000]
    set_lfo4(w, src, vals)
    w.wish_save(stored, ctypes.c_uint32(src))                       # the record in RAM and in the hash cache
    w.wish_load(ctypes.c_uint32(dst), stored.raw)
    assert lfo4_values(w, dst) is None                              # not before the poll
    w.wish_lfo4_poll()
    assert lfo4_values(w, dst) == vals and u32(w, "wish_lfo4_in") == 1
    w.wish_lfo4_poll()
    assert u32(w, "wish_lfo4_in") == 1                              # once
