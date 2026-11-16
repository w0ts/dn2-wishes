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
TAG, ENV_TAG = 0x0010, 0x0011             # WT_MX_ROUTES, WT_MX_ENV
LFO, SLOTS, TOP, NONE = 15, 23, 0x7F00, 0x4000
FULL = 0x7FFFFFFF
KIT = 0x10000                           # a kit's address as the host test plays it (never dereferenced)

HARNESS = WISH_HARNESS + r"""
#include <stddef.h>
typedef signed short s16;
struct mx_e { s32 cell, d1, src; };
struct mx_env { s32 level; u32 hold; u8 stage, on, off, pad; };
struct mx_tab { struct mx_e e[23]; u8 env2[8]; };
struct mx_state { u32 magic, edits, kit, compiles, frames, ons, offs, sound[16], live[16]; struct mx_env env[16][2];
                  u8 e2_lock[16][7]; u16 e2_locked;
                  struct mx_tab tab[16][2]; struct mx_tab none; s32 env_out[16 * 30]; u16 scratch[16 * 101]; };
struct mx_state mx_host_state;
u16 mx_host_rows[34 / 2 + 16 * 101 + 8] __attribute__((aligned(4)));
u32 mx_host_kit, mx_host_vsound[16];
s32 mx_host_lfo[16 * 30];
u32 host_mx_sound(u32 t) { return mx_host_state.sound[t]; }
u32 host_mx_live(u32 t) { return mx_host_state.live[t]; }
u32 host_mx_compiles(void) { return mx_host_state.compiles; }
u32 host_scratch_sum(void) { u32 s = 0; for (u32 k = 0; k < 16 * 101; k++) s += mx_host_state.scratch[k]; return s; }
void host_mx_reset(void) { memset(&mx_host_state, 0, sizeof mx_host_state); }
s32 host_env(u32 v, u32 j) { return mx_host_state.env_out[30u * v + j]; }
u32 host_stage(u32 v, u32 j) { return mx_host_state.env[v][j].stage; }
long host_env_src(u32 j) { return (long)((char *)&mx_host_state.env_out[j] - (char *)mx_host_lfo); }
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
    for name in ("mx_lay", "host_mx_sound", "host_mx_live", "host_mx_compiles", "host_scratch_sum", "host_stage"):
        getattr(L, name).restype = ctypes.c_uint32
    L.host_env.restype = ctypes.c_int32
    L.host_env_src.restype = ctypes.c_long
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
    _fields_ = [("e", (ctypes.c_int32 * 3) * SLOTS), ("env2", ctypes.c_uint8 * 8)]


def lay(lib, value: bytes, env: bytes = b"") -> tuple[int, list[tuple[int, int, int]]]:
    t = Tab()
    n = lib.mx_lay(value, len(value), env, len(env), ctypes.byref(t))
    lay.env2 = tuple(t.env2)
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
    n, e = lay(m, routes((5, 67, 0x6000), (0, 24, 0x6000), (0, 101, 0x6000), (0, 25, 0x7FFF), (2, 100, 0)))
    assert n == 2                                                   # sources 0..4, slots 25..100 only
    assert e[0] == (50, (0x7FFE - NONE) * 2, 0)                     # the depth clamped to DEP's top
    assert e[1] == (200, -2 * NONE, 80)


def test_lay_takes_at_most_fifteen_lfo_routes(m):
    n, e = lay(m, routes(*[(k % 3, 25 + k, 0x5000) for k in range(20)]))
    assert n == LFO
    assert [x[0] for x in e[:LFO]] == [2 * (25 + k) for k in range(LFO)]
    assert all(x[1] == 0 for x in e[LFO:])                          # the envelopes' slots stay unused


def test_lay_puts_each_envelopes_routes_in_its_own_four(m):
    rs = [(3, 30 + k, 0x7000) for k in range(6)] + [(4, 40 + k, 0x1000) for k in range(3)] + [(0, 50, 0x5000)]
    n, e = lay(m, routes(*rs))
    assert n == 4 + 3 + 1                                           # ENV1's fifth and sixth left out
    assert e[0][0] == 100
    assert [x[0] for x in e[LFO:LFO + 4]] == [60, 62, 64, 66]
    assert [x[0] for x in e[LFO + 4:LFO + 7]] == [80, 82, 84] and e[LFO + 7][1] == 0
    assert e[LFO][2] == m.host_env_src(0) and e[LFO + 4][2] == m.host_env_src(1)


def test_lay_of_env2s_knobs(m):
    lay(m, b"", bytes([0, 64, 127, 10, 99, 0, 1, 0]))
    assert lay.env2 == (0, 64, 127, 10, 99, 0, 1, 0)
    lay(m, b"", bytes([200, 127, 0, 0, 0, 7, 9, 0]))                # out of range clamped, MODE and RSET to 0 / 1
    assert lay.env2 == (127, 127, 0, 0, 0, 1, 1, 0)
    lay(m, b"", b"")                                                # no field: stock's AMP defaults
    assert lay.env2 == (8, 127, 32, 96, 24, 1, 1, 0)


def test_the_committed_time_table_is_the_generators():
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_matrix_env.py"), "--check"]).returncode == 0


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


# --- the envelopes: the clone of stock's AMP envelope ---------------------------------------------
def tables():
    sys.path.insert(0, str(ROOT / "scripts"))
    import gen_matrix_env as G
    return G.table()


def model(knobs, events, frames):
    """the clone (csrc/matrix env_step) in Python: KNOBS (ATK HOLD DEC SUS REL MODE RSET), EVENTS {frame: "on"/"off"}"""
    T = tables()
    atk, hold_k, dec, sus_k, rel, mode, rset = knobs
    x, stage, hold, out = 0, "rest", 0, []
    s = T["ENV_ATK_S"][atk]
    inc = FULL if s >= FULL // 32 else s << 5

    def fall(d, r, n):
        for _ in range(n):
            d = (d * r) >> 31
        return d
    for f in range(frames):
        ev = events.get(f)
        if ev == "on":
            if rset:
                x = s >> 1
            stage = "atk"
        if ev == "off":
            if (stage == "atk" or (stage == "hold" and hold == 0xFFFFFFFF)) if not mode else stage != "rest":
                stage = "fall" if not mode else "rel"
        if stage == "atk":
            if x >= FULL - inc:
                used = 0 if s == FULL else (FULL - x + s - 1) // s
                rest = 32 - used if used < 32 else 0
                sus, r = sus_k * (FULL // 127), T["ENV_DEC_S"][dec]
                x = FULL
                if not mode:
                    hold = T["ENV_HOLD"][hold_k]
                    stage = "hold"
                    if hold != 0xFFFFFFFF:
                        if hold >= rest:
                            hold -= rest
                        else:
                            x = fall(x, r, rest - hold)
                            hold, stage = 0, "fall"
                else:
                    stage = "dec"
                    x = sus + fall(x - sus, r, rest)
            else:
                x += inc
        elif stage == "hold":
            if hold != 0xFFFFFFFF:
                if hold >= 32:
                    hold -= 32
                else:
                    x = fall(x, T["ENV_DEC_S"][dec], 32 - hold)
                    hold, stage = 0, "fall"
        elif stage == "dec":
            sus = sus_k * (FULL // 127)
            x = sus + (((x - sus) * T["ENV_DEC"][dec]) >> 31)
        elif stage in ("rel", "fall"):
            x = (x * T["ENV_REL" if stage == "rel" else "ENV_DEC"][rel if stage == "rel" else dec]) >> 31
            if x < 0x100:
                x, stage = 0, "rest"
        out.append(x)
    return out


def env2_run(m, knobs, events, frames):
    put(m, 0, routes((4, 67, TOP)))
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [0]), 8)
    m.mx_poll()
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {})
    out = []
    for f in range(frames):
        if events.get(f) == "on":
            m.mx_env_on(0)
        if events.get(f) == "off":
            m.mx_env_off(1)
        m.mx_eval(ctypes.addressof(rows))
        out.append(m.host_env(0, 1))
    return out


CASES = {
    "ADSR, held then released": ((30, 127, 40, 64, 50, 1, 1), {0: "on", 150: "off"}, 400),
    "ADSR, released in the attack": ((40, 127, 30, 64, 20, 1, 1), {0: "on", 40: "off"}, 200),
    "AHD, held until the note-off": ((20, 127, 30, 64, 50, 0, 1), {0: "on", 120: "off"}, 300),
    "AHD, released in the attack": ((40, 127, 30, 64, 50, 0, 1), {0: "on", 40: "off"}, 200),
    "AHD, no hold": ((10, 0, 35, 64, 50, 0, 1), {0: "on"}, 200),
    "RSET off: a note-on goes on from the level": ((30, 127, 40, 64, 50, 1, 0), {0: "on", 40: "off", 70: "on"}, 200),
    "RSET on: a note-on restarts": ((30, 127, 40, 64, 50, 1, 1), {0: "on", 40: "off", 70: "on"}, 200),
    "the fastest knobs": ((0, 127, 1, 0, 1, 1, 1), {0: "on", 3: "off"}, 20),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_env2_is_the_model(m, case):
    knobs, events, frames = CASES[case]
    assert env2_run(m, knobs, events, frames) == model(knobs, events, frames)


def test_env1_reads_the_rows_amp_cells(m):
    m.mx_poll()
    knobs = (30, 127, 40, 64, 50, 1, 1)
    cells = {(0, s): k << 8 for s, k in zip((81, 82, 83, 84, 85, 91, 92), knobs)}
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, cells)
    out = []
    for f in range(300):
        if f == 0:
            m.mx_env_on(0)
        if f == 200:
            m.mx_env_off(1)
        m.mx_eval(ctypes.addressof(rows))
        out.append(m.host_env(0, 0))
    assert out == model(knobs, {0: "on", 200: "off"}, 300)


def test_envelope_note_on_and_off_reach_only_their_voice(m):
    m.mx_poll()
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {})
    m.mx_env_on(3)
    for _ in range(5):
        m.mx_eval(ctypes.addressof(rows))
    assert m.host_env(3, 0) > 0 and m.host_env(3, 1) > 0 and m.host_env(2, 0) == 0
    m.mx_env_off(1 << 2)                                            # a voice at rest stays at rest
    m.mx_eval(ctypes.addressof(rows))
    assert m.host_stage(2, 0) == 0 and m.host_env(2, 0) == 0


def test_env2_takes_a_trigs_locks_until_the_next_trig(m):
    knobs = (30, 127, 40, 64, 50, 1, 1)
    put(m, 0, routes((4, 67, TOP)))
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [0]), 8)
    m.mx_poll()
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {})
    locks = (ctypes.c_uint16 * 6)(10, 0xFFFF, 100, 0xFFFF, 0xFFFF, 0xFFFF)     # ATK 10, SUS 100: the rest the record's
    m.mx_env2_locks(0, locks)
    m.mx_env_on(0)
    out = []
    for _ in range(60):
        m.mx_eval(ctypes.addressof(rows))
        out.append(m.host_env(0, 1))
    locked = (10, 127, 40, 100, 50, 1, 1)
    assert out == model(locked, {0: "on"}, 60)
    m.mx_env2_locks(0, None)                                        # the next trig, no lock: the record's knobs again
    m.mx_env_on(0)
    out = []
    for _ in range(60):
        m.mx_eval(ctypes.addressof(rows))
        out.append(m.host_env(0, 1))
    assert out == model(knobs, {0: "on"}, 60)
