"""The matrix's C (csrc/matrix/matrix.c, docs/matrix.md), compiled for the host with the wishes record's C and driven
through ctypes: a record's routes laid out for the frame, the UI pass's re-layout (only when a record changed or the
kit moved), and the frame's arithmetic against a model.

The host has no EMAC: its mac is (a x b) >> 31, the fractional product the frame's MACSR gives. That the target's
instruction gives exactly what stock's route 1 gives is the emulator's check (scripts/emu_matrix.py)."""

from __future__ import annotations

import ctypes
import pathlib
import shutil
import struct
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_wishes_c import HARNESS as WISH_HARNESS, HOST_H, SOURCES as WISH_SOURCES   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MATRIX = ROOT / "csrc" / "matrix" / "matrix.c"
TAG = 0x0010                            # WT_MX_ROUTES
SLOTS, TOP, NONE = 15, 0x7F00, 0x4000
KIT = 0x10000                           # a kit's address as the host test plays it (never dereferenced)

HARNESS = WISH_HARNESS + r"""
#include <stddef.h>
typedef signed short s16;
struct mx_e { s32 cell, d1; u32 src; };
struct mx_tab { struct mx_e e[15]; };
struct mx_state { u32 magic, edits, kit, compiles, frames, sound[16], live[16];
                  struct mx_tab tab[16][2]; struct mx_tab none; u16 scratch[16 * 101]; };
struct mx_state mx_host_state;
u16 mx_host_rows[34 / 2 + 16 * 101 + 8] __attribute__((aligned(4)));
u32 mx_host_kit, mx_host_vsound[16];
s32 mx_host_lfo[16 * 30];
u32 host_mx_sound(u32 t) { return mx_host_state.sound[t]; }
u32 host_mx_live(u32 t) { return mx_host_state.live[t]; }
u32 host_mx_compiles(void) { return mx_host_state.compiles; }
u32 host_scratch_sum(void) { u32 s = 0; for (u32 k = 0; k < 16 * 101; k++) s += mx_host_state.scratch[k]; return s; }
void host_mx_reset(void) { memset(&mx_host_state, 0, sizeof mx_host_state); }
"""


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("matrix")
    (d / "host.h").write_text(HOST_H)
    (d / "harness.c").write_text(HARNESS)
    out = d / "libmatrix.so"
    r = subprocess.run([cc, "-shared", "-fPIC", "-O1", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-DWISH_HOST", "-DMX_HOST", "-include", str(d / "host.h"), f"-I{WISH_SOURCES[0].parent}",
                        *map(str, WISH_SOURCES), str(MATRIX), str(d / "harness.c"), "-o", str(out)],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr)
    L = ctypes.CDLL(str(out))
    for name in ("mx_lay", "host_mx_sound", "host_mx_live", "host_mx_compiles", "host_scratch_sum"):
        getattr(L, name).restype = ctypes.c_uint32
    L.mx_eval.argtypes = [ctypes.c_ulong]
    return L


@pytest.fixture()
def m(lib):
    lib.host_erase()
    lib.host_reboot()
    lib.host_zero()
    lib.host_mx_reset()
    ctypes.c_uint32.in_dll(lib, "mx_host_kit").value = KIT
    return lib


def sound(t: int) -> int:
    return KIT + 52 + 1163 * t


def routes(*r: tuple[int, int, int]) -> bytes:
    return b"".join(struct.pack(">BBH", src, slot, dep) for src, slot, dep in r)


def put(lib, t: int, value: bytes) -> int:
    return lib.wish_put(ctypes.c_uint32(sound(t)), ctypes.c_uint32(TAG), value, len(value))


def arr(lib, name, ctype, n):
    return (ctype * n).in_dll(lib, name)


class Tab(ctypes.Structure):
    _fields_ = [("e", (ctypes.c_int32 * 3) * SLOTS)]


def lay(lib, value: bytes) -> tuple[int, list[tuple[int, int, int]]]:
    t = Tab()
    n = lib.mx_lay(value, len(value), ctypes.byref(t))
    return n, [tuple(t.e[k]) for k in range(SLOTS)]


def mac(a: int, b: int) -> int:
    return (a * b) >> 31


# --- laying a record out ---------------------------------------------------------------------
def test_lay_one_route_as_stock_route_1(m):
    n, e = lay(m, routes((1, 67, 0x6000)))
    assert n == 1
    assert e[0] == (2 * 67, (0x6000 - NONE) * 2, 40)               # LFO2: its output 40 bytes after LFO1's
    none = e[1]
    assert none[1] == 0 and all(x == none for x in e[1:])           # the rest add 0 into the scratch row


def test_lay_skips_what_is_out_of_range(m):
    n, e = lay(m, routes((3, 67, 0x6000), (0, 24, 0x6000), (0, 101, 0x6000), (0, 25, 0x7FFF), (2, 100, 0)))
    assert n == 2                                                   # ENV sources are phase 3's, slots 25..100 only
    assert e[0] == (50, (TOP - NONE) * 2, 0)                        # the depth clamped to stock's top
    assert e[1] == (200, -2 * NONE, 80)


def test_lay_takes_at_most_fifteen(m):
    n, e = lay(m, routes(*[(k % 3, 25 + k, 0x5000) for k in range(20)]))
    assert n == SLOTS
    assert [x[0] for x in e] == [2 * (25 + k) for k in range(SLOTS)]


def test_lay_of_nothing(m):
    n, e = lay(m, b"")
    assert n == 0 and all(x[1] == 0 for x in e)
    n, e = lay(m, b"\x00\x43")                                      # a broken tail is ignored
    assert n == 0


# --- the UI pass ----------------------------------------------------------------------------
def test_poll_lays_out_each_track_from_its_sound(m):
    assert put(m, 3, routes((0, 67, 0x7000))) == 0
    m.mx_poll()
    assert m.host_mx_compiles() == 1
    assert [m.host_mx_sound(t) for t in range(16)] == [sound(t) for t in range(16)]
    live = m.host_mx_live(3)
    m.mx_poll()                                                     # nothing changed: nothing laid out again
    assert m.host_mx_compiles() == 1 and m.host_mx_live(3) == live
    assert put(m, 3, routes((0, 67, 0x2000))) == 0                  # an edit: laid out into the spare table
    m.mx_poll()
    assert m.host_mx_compiles() == 2 and m.host_mx_live(3) == live ^ 1


def test_poll_follows_the_kit(m):
    m.mx_poll()
    ctypes.c_uint32.in_dll(m, "mx_host_kit").value = KIT + 0x8000
    m.mx_poll()
    assert m.host_mx_compiles() == 2 and m.host_mx_sound(0) == KIT + 0x8000 + 52


def test_poll_without_a_kit_does_nothing(m):
    ctypes.c_uint32.in_dll(m, "mx_host_kit").value = 0
    m.mx_poll()
    assert m.host_mx_compiles() == 0


# --- the frame ------------------------------------------------------------------------------
def frame_setup(m, lfo_values, cells):
    rows = arr(m, "mx_host_rows", ctypes.c_uint16, 17 + 16 * 101 + 8)
    for v in range(16):
        for s in range(101):
            rows[17 + 101 * v + s] = cells.get((v, s), 0x3000)
    lfo = arr(m, "mx_host_lfo", ctypes.c_int32, 16 * 30)
    for v in range(16):
        for l in range(3):
            lfo[30 * v + 10 * l] = lfo_values[(v, l)]
    vs = arr(m, "mx_host_vsound", ctypes.c_uint32, 16)
    for v in range(16):
        vs[v] = sound(v)
    return rows, vs


def cell(rows, v, s):
    return rows[17 + 101 * v + s]


def test_frame_adds_each_route_as_the_model(m):
    lfo = {(v, l): (0x7FFFFFFF if l == 0 else -0x40000000 if l == 1 else 0x12345678) for v in range(16) for l in range(3)}
    put(m, 0, routes((0, 67, 0x6000)))
    put(m, 1, routes((1, 67, TOP), (2, 30, 0x1000), (0, 30, 0x5555)))
    m.mx_poll()
    rows, vs = frame_setup(m, lfo, {(1, 30): 0x7E00})
    before = [cell(rows, v, s) for v in range(16) for s in range(101)]
    m.mx_eval(ctypes.addressof(rows))
    want0 = max(0, min(TOP, 0x3000 + mac((0x6000 - NONE) * 2, lfo[(0, 0)])))
    assert cell(rows, 0, 67) == want0
    w67 = max(0, min(TOP, 0x3000 + mac((TOP - NONE) * 2, lfo[(1, 1)])))
    assert cell(rows, 1, 67) == w67
    w30 = max(0, min(TOP, 0x7E00 + mac((0x1000 - NONE) * 2, lfo[(1, 2)])))
    w30 = max(0, min(TOP, w30 + mac((0x5555 - NONE) * 2, lfo[(1, 0)])))   # clamped after each route, as stock
    assert cell(rows, 1, 30) == w30
    after = [cell(rows, v, s) for v in range(16) for s in range(101)]
    changed = {(k // 101, k % 101) for k in range(len(after)) if after[k] != before[k]}
    assert changed <= {(0, 67), (1, 67), (1, 30)}
    assert m.host_scratch_sum() == 0                                # the unused routes added 0


def test_frame_voice_on_another_sound_gets_nothing(m):
    lfo = {(v, l): 0x7FFFFFFF for v in range(16) for l in range(3)}
    put(m, 2, routes((0, 67, TOP)))
    m.mx_poll()
    rows, vs = frame_setup(m, lfo, {})
    for other in (sound(2) + 1163 * 20, sound(2) + 1, sound(0) - 1163, 0):  # the pool's, inside a sound, below the kit
        vs[2] = other
        m.mx_eval(ctypes.addressof(rows))
        assert cell(rows, 2, 67) == 0x3000
    vs[2] = sound(2)                                                # its track's sound again: heard
    m.mx_eval(ctypes.addressof(rows))
    assert cell(rows, 2, 67) == TOP


def test_frame_finds_the_track_from_the_sound(m):
    lfo = {(v, l): 0x7FFFFFFF for v in range(16) for l in range(3)}
    for t in range(16):
        put(m, t, routes((0, 25 + t, TOP)))
    m.mx_poll()
    rows, vs = frame_setup(m, lfo, {})
    for v in range(16):
        vs[v] = sound(15 - v)                                       # voice v plays track 15 - v
    m.mx_eval(ctypes.addressof(rows))
    for v in range(16):
        assert [s for s in range(25, 41) if cell(rows, v, s) != 0x3000] == [25 + 15 - v]


def test_frame_before_the_first_pass_does_nothing(m):
    lfo = {(v, l): 0x7FFFFFFF for v in range(16) for l in range(3)}
    rows, _ = frame_setup(m, lfo, {})
    m.mx_eval(ctypes.addressof(rows))
    assert all(cell(rows, v, 67) == 0x3000 for v in range(16))
