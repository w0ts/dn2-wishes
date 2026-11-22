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
#ifndef MX_HOST_LFO_W
#define MX_HOST_LFO_W 30u
#endif
typedef signed short s16;
#ifdef DN2_ROUTE8
struct mx_e { s32 cell; s16 h; s16 src; };
#else
struct mx_e { s32 cell, d1, src; };
#endif
struct mx_env { s32 level; u32 hold; u8 stage, on, off, pad; };
struct mx_tab { struct mx_e e[23]; u8 env2[8]; u16 e2w[8]; s32 nx1[3]; };
struct mx_state { u32 magic, edits, kit, compiles, frames, ons, offs, sound[16], live[16]; struct mx_env env[16][2];
                  u8 e2_lock[16][7]; s32 e2_hm[16]; u16 e2_locked;
                  struct mx_tab tab[16][2]; struct mx_tab none; s32 env_out[16 * MX_HOST_LFO_W]; u16 scratch[16 * 101];
                  u16 e2row[16 * 101]; u16 iroute[16]; };
struct mx_state mx_host_state;
/* (2026-11-20) the inserts' side (csrc/inserts/ins.c): each track's SET as cells, the offsets the frame works out, the
 * group packed next; slides' last voice of each track */
u16 ins_cell[17][14] __attribute__((aligned(4)));
s16 ins_moff[16][14];
signed char sl_lastv[16];
u32 host_ins_group;
u32 ins_next_group(void) { return host_ins_group; }
u16 host_e2row(u32 v, u32 k) { return mx_host_state.e2row[101u * v + k]; }
u16 mx_host_rows[34 / 2 + 16 * 101 + 8] __attribute__((aligned(4)));
u32 mx_host_kit, mx_host_vsound[16];
s32 mx_host_lfo[16 * MX_HOST_LFO_W];
u32 host_mx_sound(u32 t) { return mx_host_state.sound[t]; }
u32 host_mx_live(u32 t) { return mx_host_state.live[t]; }
u32 host_mx_compiles(void) { return mx_host_state.compiles; }
u32 host_scratch_sum(void) { u32 s = 0; for (u32 k = 0; k < 16 * 101; k++) s += mx_host_state.scratch[k]; return s; }
void host_mx_reset(void) { memset(&mx_host_state, 0, sizeof mx_host_state); }
void host_mx_stale(void) { memset(&mx_host_state, 0xAB, sizeof mx_host_state); mx_host_state.magic = 0x4D583034u; }
u32 host_mx_magic(void) { return mx_host_state.magic; }
u32 host_mx_size(void) { return sizeof mx_host_state; }
s32 host_env(u32 v, u32 j)      /* ENV1's level (its routes' source), ENV2's (its state: its routes' source is x H, negated) */
{
    return j == 1u ? mx_host_state.env[v][1].level : mx_host_state.env_out[MX_HOST_LFO_W * v + j];
}
s32 host_word(u32 v, u32 j) { return mx_host_state.env_out[MX_HOST_LFO_W * v + j]; }
u32 host_stage(u32 v, u32 j) { return mx_host_state.env[v][j].stage; }
#ifdef DN2_ROUTE8
long host_env_src(u32 j) { return (long)(4u * j); }   /* (DN2_ROUTE8) from the voice's env_out row */
#else
long host_env_src(u32 j) { return (long)((char *)&mx_host_state.env_out[j] - (char *)mx_host_lfo); }
#endif
/* (2026-11-19) DEP the attenuverter: atten.c's conversion (the host: every sound converted when HOST_CONV), and the
 * frame's work at stock's DEP read (hooks.S lfo_fast) for voice V's LFO L: its output OUT x DEP into our word
 * (env_out W_OUT, negated), the first route's word (W_X1) as mx_eval left it */
int host_conv;
int mxa_convert(u32 t, u32 s) { (void)t; (void)s; return host_conv; }
s32 mx_m_of(u32 a);
void host_dep_site(u32 v, u32 l, s32 out, u32 dep)
{
    s32 m = mx_m_of(dep);
    mx_host_state.env_out[MX_HOST_LFO_W * v + 2u + 10u * l] = (s32)(((long long)out * m) >> 31);
}
s32 host_x1(u32 v, u32 l) { return mx_host_state.env_out[MX_HOST_LFO_W * v + 3u + 10u * l]; }
s32 host_first(u32 v, u32 l, s32 cell)   /* lfo_fast's first route on CELL (no clamp), as the frame adds it */
{
    s32 o = mx_host_state.env_out[MX_HOST_LFO_W * v + 2u + 10u * l], d = host_x1(v, l);
    return cell + (s32)(((long long)d * o) >> 31);
}
"""


@pytest.fixture(scope="module", params=[(30, 12), (40, 12), (30, 8), (40, 8)],
                ids=["stock-lfo-stride", "lfo4-stride", "stock-lfo-stride-route8", "lfo4-stride-route8"])
def lib(request, tmp_path_factory):
    """the matrix built four times: the LFO state's stride stock's (120 B a voice, 30 words) and lfo4's (160 B, 40 words;
    DN2_LFO4 moves it, csrc/matrix/matrix.c ENV_W), each with a route in 12 bytes and in 8 (DN2_ROUTE8)"""
    w, eb = request.param
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp(f"matrix{w}-{eb}")
    (d / "host.h").write_text(HOST_H)
    (d / "harness.c").write_text(HARNESS)
    out = d / "libmatrix.so"
    r = subprocess.run([cc, "-shared", "-fPIC", "-O1", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-DWISH_HOST", "-DMX_HOST", f"-DMX_HOST_LFO_W={w}u", *(["-DDN2_ROUTE8=1"] if eb == 8 else []), "-include", str(d / "host.h"), f"-I{WISH_SOURCES[0].parent}",
                        *map(str, WISH_SOURCES), str(MATRIX), str(d / "harness.c"), "-o", str(out)],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr)
    L = ctypes.CDLL(str(out))
    for name in ("mx_lay", "host_mx_sound", "host_mx_live", "host_mx_compiles", "host_scratch_sum", "host_stage",
                 "host_mx_magic", "host_mx_size", "mx_ins_routes"):
        getattr(L, name).restype = ctypes.c_uint32
    L.host_e2row.restype = ctypes.c_uint16
    for name in ("host_env", "host_word", "mx_m_of", "host_x1", "host_first"):
        getattr(L, name).restype = ctypes.c_int32
    L.host_dep_site.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32]
    L.host_first.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32]
    L.host_env_src.restype = ctypes.c_long
    L.mx_eval.argtypes = [ctypes.c_ulong]
    L.W = w
    L.EB = eb
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
    _fields_ = [("e", (ctypes.c_int32 * 3) * SLOTS), ("env2", ctypes.c_uint8 * 8), ("e2w", ctypes.c_uint16 * 8),
                ("nx1", ctypes.c_int32 * 3)]


class E8(ctypes.Structure):
    _fields_ = [("cell", ctypes.c_int32), ("h", ctypes.c_int16), ("src", ctypes.c_int16)]


class Tab8(ctypes.Structure):           # (DN2_ROUTE8) a route in 8 bytes: d1 kept as its half
    _fields_ = [("e", E8 * SLOTS), ("env2", ctypes.c_uint8 * 8), ("e2w", ctypes.c_uint16 * 8),
                ("nx1", ctypes.c_int32 * 3)]


def lay(lib, value: bytes, env: bytes = b"") -> tuple[int, list[tuple[int, int, int]]]:
    """-> the routes laid out, each (cell, d1, src) whichever the build's entry"""
    t = Tab8() if lib.EB == 8 else Tab()
    n = lib.mx_lay(value, len(value), env, len(env), ctypes.byref(t))
    lay.env2 = tuple(t.env2)
    lay.e2w = tuple(t.e2w)
    if lib.EB == 8:
        return n, [(t.e[k].cell, 2 * t.e[k].h, t.e[k].src) for k in range(SLOTS)]
    return n, [tuple(t.e[k]) for k in range(SLOTS)]


def mac(a: int, b: int) -> int:
    return (a * b) >> 31


def lsrc(m, l: int) -> int:
    """(2026-11-19) an LFO route's source: its output x DEP, negated, in env_out's row (W_OUT)"""
    return m.host_env_src(2 + 10 * l)


# --- laying a record out ---------------------------------------------------------------------
def test_lay_one_route_as_stock_route_1(m):
    n, e = lay(m, routes((1, 67, 0x6000)))
    assert n == 1
    assert e[0] == (2 * 67, -(0x6000 - NONE) * 2, lsrc(m, 1))      # LFO2: its output x DEP, the depth negated
    none = e[1]
    assert none[1] == 0 and all(x == none for x in e[1:])           # the rest add 0 into the scratch row


def test_lay_skips_what_is_out_of_range(m):
    n, e = lay(m, routes((5, 67, 0x6000), (0, 24, 0x6000), (0, 101, 0x6000), (0, 25, 0x7FFF), (2, 100, 0)))
    assert n == 2                                                   # sources 0..4, slots 25..100 only
    assert e[0] == (50, -(0x7FFE - NONE) * 2, lsrc(m, 0))           # the depth clamped to DEP's top
    assert e[1] == (200, 2 * NONE, lsrc(m, 2))


def test_lay_a_muted_route_in_its_place_adding_nothing(m):
    """the routes popup's mute (the User, 2026-11-17): MX_MUTED (0x80) in the source byte; laid where it was, its
    cell and source kept (the same cost), d1 0 as at depth 0x4000; the pool's places count it"""
    n, e = lay(m, routes((0x81, 67, 0x6000), (0x83, 40, 0x2000), (0, 50, 0x5000)))
    n0, e0 = lay(m, routes((1, 67, NONE), (3, 40, NONE), (0, 50, 0x5000)))
    assert n == n0 == 3 and e == e0
    assert e[0] == (2 * 67, 0, lsrc(m, 1)) and e[1] == (2 * 50, -(0x5000 - NONE) * 2, lsrc(m, 0))


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
def frame_setup(m, lfo_values, cells, deps=None):
    rows = arr(m, "mx_host_rows", ctypes.c_uint16, 17 + 16 * 101 + 8)
    for v in range(16):
        for s in range(101):
            rows[17 + 101 * v + s] = cells.get((v, s), 0x3000)
    lfo = arr(m, "mx_host_lfo", ctypes.c_int32, 16 * m.W)
    for v in range(16):
        for l in range(3):
            lfo[m.W * v + 10 * l] = lfo_values[(v, l)]
            m.host_dep_site(v, l, lfo_values[(v, l)], deps.get((v, l), 0x7FFE) if deps else 0x7FFE)
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



def test_a_state_left_by_another_layout_is_never_trusted(m):
    """MX_RAM outlives a flash: 'MX04' with another build's layout (garbage tables) must not reach a cell; the
    first UI pass lays it out anew (MX_MAGIC carries the state's size)"""
    lfo = {(v, l): 0x7FFFFFFF for v in range(16) for l in range(3)}
    rows, _ = frame_setup(m, lfo, {})
    m.host_mx_stale()
    m.mx_eval(ctypes.addressof(rows))
    assert all(cell(rows, v, s) == 0x3000 for v in range(16) for s in range(25, 101))
    m.mx_poll()
    assert m.host_mx_magic() == 0x4D580000 | m.host_mx_size()
    m.mx_eval(ctypes.addressof(rows))
    assert all(cell(rows, v, s) == 0x3000 for v in range(16) for s in range(25, 101))

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
            if (stage == "atk" or (stage == "hold" and T["ENV_HOLD"][hold_k] == 0xFFFFFFFF)) if not mode else stage != "rest":
                stage = "fall" if not mode else "rel"
        if stage == "atk":
            if x >= FULL - inc:
                used = 0 if s == FULL else (FULL - x + s - 1) // s
                rest = 32 - used if used < 32 else 0
                sus, r = sus_k * (FULL // 127), T["ENV_DEC_S"][dec]
                x = FULL
                if not mode:
                    h = T["ENV_HOLD"][hold_k]
                    hold, stage = rest, "hold"              # the samples held so far
                    if h != 0xFFFFFFFF and rest > h:
                        x = fall(x, r, rest - h)
                        hold, stage = 0, "fall"
                else:
                    stage = "dec"
                    x = sus + fall(x - sus, r, rest)
            else:
                x += inc
        elif stage == "hold":
            h = T["ENV_HOLD"][hold_k]
            if h == 0xFFFFFFFF or hold + 32 <= h:
                hold = hold + 32 if hold < 0xFFFFFF00 else hold
            else:
                x = fall(x, T["ENV_DEC_S"][dec], 32 if hold >= h else hold + 32 - h)
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
    "AHD, a timed hold (HOLD 4)": ((10, 4, 35, 64, 50, 0, 1), {0: "on"}, 200),
    "AHD, a timed hold (HOLD 16), the note-off inside it": ((0, 16, 35, 64, 50, 0, 1), {0: "on", 40: "off"}, 200),
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


def test_envelope_routes_reach_each_voices_own_cell(m):
    """every voice's ENV1 and ENV2 routes read that voice's own levels, at either LFO stride (2026-11-16: under lfo4's
    160 B the routes of voice v read env_out at 160 v bytes, voice 0's alone right: the gate's matrix step)"""
    knobs = (30, 127, 40, 64, 50, 1, 1)
    base, slot = 0x2000, 60
    for v in range(16):
        put(m, v, routes((3, slot, TOP), (4, slot + 1, TOP)))
        m.wish_put(ctypes.c_uint32(sound(v)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [0]), 8)
    m.mx_poll()
    cells = {(v, s): k << 8 for v in range(16) for s, k in zip((81, 82, 83, 84, 85, 91, 92), knobs)}
    cells.update({(v, s): base for v in range(16) for s in (slot, slot + 1)})
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, cells)
    lv = model(knobs, {0: "on"}, 40)
    for v in range(16):
        m.mx_env_on(v)
    for f in range(40):
        for v in range(16):
            rows[17 + 101 * v + slot] = rows[17 + 101 * v + slot + 1] = base
        m.mx_eval(ctypes.addressof(rows))
        want = max(0, min(TOP, base + (((TOP - NONE) * 2 * lv[f]) >> 31)))
        assert [(cell(rows, v, slot), cell(rows, v, slot + 1)) for v in range(16)] == [(want, want)] * 16, f
    assert want > base


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
    locks = (ctypes.c_uint16 * 8)(10, 0xFFFF, 100, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF)   # ATK 10, SUS 100: the rest the record's
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


# --- 2026-11-18: ENV1 hears the record's LFO routes into the AMP envelope; a restart that keeps MX_RAM -------------
AMP_SLOTS = (81, 82, 83, 84, 85, 91, 92)


def _amp_run(m, record, dec_row, frames=200):
    """ENV1 and ENV2 levels on voice 0 (a note on at 0, off at 120) and the row's DEC as the DSP is sent it; the row
    written anew before every frame, as stock's smoother does. DEC_ROW: DEC in the row before mx_eval (stock's
    evaluator has already added an LFO's first route there)"""
    knobs = (10, 127, 40, 64, 30, 1, 1)
    put(m, 0, routes(*record))
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [0]), 8)
    m.mx_poll()
    cells = {(0, s): k << 8 for s, k in zip(AMP_SLOTS, knobs)}
    rows, _ = frame_setup(m, {(v, l): (0x7FFFFFFF if l == 0 else 0) for v in range(16) for l in range(3)}, cells)
    e1, e2, dec = [], [], []
    for f in range(frames):
        rows[17 + 83] = dec_row
        if f == 0:
            m.mx_env_on(0)
        if f == 120:
            m.mx_env_off(1)
        m.mx_eval(ctypes.addressof(rows))
        e1.append(m.host_env(0, 0))
        e2.append(m.host_env(0, 1))
        dec.append(cell(rows, 0, 83))
    return e1, e2, dec, knobs


def test_env1_hears_an_lfo_route_of_the_record_into_dec_as_the_amp_does(m):
    """the amp is sent the row after every route; ENV1 steps after the LFO routes (0..14), so it reads the same DEC"""
    base1, base2, _, knobs = _amp_run(m, [], 40 << 8)
    m.host_mx_reset()
    e1, e2, dec, _ = _amp_run(m, [(0, 83, TOP)], 40 << 8)          # LFO1 -> DEC at full depth, a route of the record
    assert dec[5] == TOP                                            # the amp: DEC at its top
    assert e2 == base2                                              # ENV2: never a destination
    m.host_mx_reset()
    same, _, _, _ = _amp_run(m, [], TOP)                            # the same DEC put in the row before mx_eval
    assert e1 == same and e1 != base1                               # ENV1 = the clone of what the amp hears


def test_env1_and_the_envelopes_routes_unchanged_without_lfo_routes_into_the_amp(m):
    """the split changes nothing else: an envelope's routes read this frame's levels, and ENV1 reads its own DEC route
    one frame later only through the next frame's row (the clone's known limit)"""
    base1, _, _, _ = _amp_run(m, [], 40 << 8)
    m.host_mx_reset()
    e1, _, dec, _ = _amp_run(m, [(3, 83, TOP)], 40 << 8)            # ENV1 -> DEC: the amp hears it, ENV1 does not
    assert e1 == base1
    assert dec[5] > 40 << 8


def test_a_restart_that_keeps_mx_ram_adds_no_route_before_the_first_pass(m):
    """MX_RAM (magic and all) outlives a restart that keeps the RAM; mx_loaded (code data) is 0 again after a load:
    no route of the last run reaches a cell until this load's first UI pass has laid the tables out again"""
    put(m, 0, routes((0, 67, TOP)))
    m.mx_poll()
    lfo = {(v, l): 0x7FFFFFFF for v in range(16) for l in range(3)}
    rows, _ = frame_setup(m, lfo, {})
    m.mx_eval(ctypes.addressof(rows))
    assert cell(rows, 0, 67) == TOP                                 # laid out and heard
    ctypes.c_uint32.in_dll(m, "mx_loaded").value = 0                # the restart: the code's data loaded again
    rows, _ = frame_setup(m, lfo, {})
    m.mx_eval(ctypes.addressof(rows))
    assert cell(rows, 0, 67) == 0x3000                              # nothing until the first pass
    m.mx_poll()
    rows, _ = frame_setup(m, lfo, {})                               # (the frame's lfo_fast: its words every frame)
    m.mx_eval(ctypes.addressof(rows))
    assert cell(rows, 0, 67) == TOP


# --- 2026-11-18: ENV2's knobs as destinations (0xE0 ATK, 0xE1 HOLD, 0xE2 DEC, 0xE3 SUS, 0xE4 REL) ------------------
E2 = {"ATK": 0xE0, "HOLD": 0xE1, "DEC": 0xE2, "SUS": 0xE3, "REL": 0xE4}


def test_lay_of_env2_destinations(m):
    n, e = lay(m, routes((0, E2["DEC"], TOP), (3, E2["SUS"], TOP), (4, E2["ATK"], TOP), (0, 0xE8, TOP), (1, 0xDF, TOP)))
    assert n == 2                                                   # LFO1 and ENV1 into ENV2: laid; ENV2 into itself,
    assert e[0][0] != 2 * 0xE2 and e[0][1] == -(TOP - NONE) * 2      # 0xE8 and 0xDF: skipped (LFO1: x DEP,
                                                                    # its depth laid negated)
    assert e[15][1] == (TOP - NONE) * 2                             # ENV1's first route


def _e2_run(m, record, frames=200, lfo1=0x7FFFFFFF):
    knobs = (10, 127, 40, 64, 30, 1, 1)
    put(m, 0, routes(*record))
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [0]), 8)
    m.mx_poll()
    cells = {(0, s): k << 8 for s, k in zip(AMP_SLOTS, knobs)}
    rows, _ = frame_setup(m, {(v, l): (lfo1 if l == 0 else 0) for v in range(16) for l in range(3)}, cells)
    e1, e2, amp, dec2 = [], [], [], []
    heard, setv = ctypes.c_int(), ctypes.c_int()
    for f in range(frames):
        if f == 0:
            m.mx_env_on(0)
        if f == 120:
            m.mx_env_off(1)
        m.mx_eval(ctypes.addressof(rows))
        e1.append(m.host_env(0, 0))
        e2.append(m.host_env(0, 1))
        amp.append([cell(rows, 0, s) for s in AMP_SLOTS])
        assert m.mx_e2_knob(0, 2, ctypes.byref(heard), ctypes.byref(setv)) == 1
        dec2.append((heard.value, setv.value))
    return e1, e2, amp, dec2, knobs


def test_an_lfo_route_into_env2s_dec_moves_env2_only(m):
    base1, base2, amp0, _, knobs = _e2_run(m, [])
    m.host_mx_reset()
    e1, e2, amp, dec2, _ = _e2_run(m, [(0, E2["DEC"], TOP)])
    assert e1 == base1 and amp == amp0                              # ENV1 and the amp's cells untouched
    assert all(h == TOP and s == knobs[2] << 8 for h, s in dec2)    # ENV2's DEC heard at the top, set at the record's
    want = model(tuple(127 if i == 2 else k for i, k in enumerate(knobs)), {0: "on", 120: "off"}, 200)
    assert e2 == want and e2 != base2


def test_env1_into_env2s_knob_in_the_same_frame(m):
    """ENV1's routes come after ENV1 steps and before ENV2 does: ENV2's ATK heard = the record's + ENV1's level now"""
    _, _, _, _, knobs = _e2_run(m, [], frames=1)
    m.host_mx_reset()
    put(m, 0, routes((3, E2["ATK"], TOP)))
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [0]), 8)
    m.mx_poll()
    cells = {(0, s): k << 8 for s, k in zip(AMP_SLOTS, knobs)}
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, cells)
    m.mx_env_on(0)
    heard, setv = ctypes.c_int(), ctypes.c_int()
    for f in range(30):
        m.mx_eval(ctypes.addressof(rows))
        m.mx_e2_knob(0, 0, ctypes.byref(heard), ctypes.byref(setv))
        lv = m.host_env(0, 0)
        assert heard.value == max(0, min(TOP, (knobs[0] << 8) + (((TOP - NONE) * 2 * lv) >> 31))), f


def test_env2_destinations_change_nothing_without_such_a_route(m):
    """bit-exact: ENV2's knob row written from the record every frame, read back unchanged"""
    base1, base2, amp0, dec2, knobs = _e2_run(m, [(0, 67, TOP)])
    assert base2 == model(knobs, {0: "on", 120: "off"}, 200)
    assert all(h == s == knobs[2] << 8 for h, s in dec2)


def test_a_hold_moved_during_the_hold_is_heard_at_once(m):
    """(2026-11-18) the clone counts the samples held, against HOLD's length now (as the DSP counts its word 0x2547c4):
    ENV2's HOLD 16 (3,085 samples) moved to 0 by LFO1 at full negative depth after 20 frames: ENV2 falls in that frame"""
    knobs = (0, 16, 35, 64, 50, 0, 1)
    put(m, 0, routes((0, E2["HOLD"], 0)))                             # depth 0: -64, HOLD pulled to 0 at full scale
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [0]), 8)
    m.mx_poll()
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {})
    lfo = arr(m, "mx_host_lfo", ctypes.c_int32, 16 * m.W)
    m.mx_env_on(0)
    out = []
    for f in range(30):
        lfo[0] = 0x7FFFFFFF if f >= 20 else 0
        m.host_dep_site(0, 0, lfo[0], 0x7FFE)                       # lfo_fast's work at DEP's read, 100 %
        m.mx_eval(ctypes.addressof(rows))
        out.append((m.host_stage(0, 1), m.host_env(0, 1)))
    assert all(st == 2 and x == FULL for st, x in out[1:20])         # E_HOLD at full scale, HOLD 16 not over
    assert out[20][0] == 5 and out[20][1] < FULL                      # E_FALL: the whole block fell (HOLD 0: 2 samples)
    assert out == [(st, x) for st, x in out]


# --- (2026-11-19) DEP, the LFO's global attenuverter (atten.c, hooks.S lfo_fast; docs/matrix.md) -------------------
RNG_OUTS = [0, 1, -1, 2, 0x7FFFFFFF, -0x7FFFFFFF, 0x40000000, -0x40000000, 0x12345678, -0x23456789, 0x7FFF0001,
            -0x7FFF8001] + [((k * 2654435761) & 0xFFFFFFFF) - (1 << 31) for k in range(1, 400)]


def test_m_of_the_attenuverter(m):
    assert m.mx_m_of(0x7F00) == m.mx_m_of(0x7FFE) == m.mx_m_of(0xC000) == -(1 << 31)   # +63 and above: 100 %
    assert m.mx_m_of(0x4000) == 0                                                     # 0 %
    assert m.mx_m_of(0x6000) == -(0x2000 << 17) and m.mx_m_of(0x2000) == 0x2000 << 17  # stock's own scale
    assert m.mx_m_of(0) == m.mx_m_of(0x7F) == 16383 << 17                             # -100 % (-16383: in 32 bits)
    assert m.mx_m_of(0x6080) == m.mx_m_of(0x60FF) == -((0x6080 - 0x4000) << 17)        # the table's step: 0x80


@pytest.mark.parametrize("dep", [0x7F00, 0x7FFE, 0x7F80])
def test_at_100_percent_every_route_is_stocks_bit_for_bit(m, dep):
    """the identity: at DEP 100 % the source is exactly -out, the depth laid negated: mac(-d1, -out) = mac(d1, out)"""
    for out in RNG_OUTS:
        m.host_dep_site(0, 0, out, dep)
        neg = m.host_word(0, 2)
        assert neg == -out or (out == -(1 << 31))
        for d in (0, 0x1000, NONE, 0x5555, TOP, 0x7FFE):
            assert mac(-(d - NONE) * 2, neg) == mac((d - NONE) * 2, out)


def test_the_attenuverter_scales_every_route_of_its_lfo(m):
    """DEP 50 % on LFO1 of voice 0: its record route heard at half its depth (to the floor), LFO2's route untouched"""
    lfo = {(v, l): 0x60000000 for v in range(16) for l in range(3)}
    put(m, 0, routes((0, 67, 0x7000), (1, 68, 0x7000)))
    m.mx_poll()
    rows, _ = frame_setup(m, lfo, {}, deps={(0, 0): 0x6000})
    m.mx_eval(ctypes.addressof(rows))
    half = mac(-(0x7000 - NONE) * 2, (0x60000000 * -(0x2000 << 17)) >> 31)
    assert cell(rows, 0, 67) == max(0, min(TOP, 0x3000 + half))
    assert abs(half - mac((0x7000 - NONE) * 2, 0x60000000) // 2) <= 1
    assert cell(rows, 0, 68) == max(0, min(TOP, 0x3000 + mac((0x7000 - NONE) * 2, 0x60000000)))
    rows2, _ = frame_setup(m, lfo, {}, deps={(0, 0): 0x2000})
    m.mx_eval(ctypes.addressof(rows2))
    assert cell(rows2, 0, 67) < 0x3000                              # -50 %: inverted


def test_the_first_routes_words_for_the_frame(m):
    """mx_lay_first: a converted sound's field (LFO1-3 {DEP as saved, depth}) -> -2 x (depth - 0x4000); not
    converted (its record not read, locked): MX_PASS. The frame gives each voice its track's words (W_X1)"""
    f = struct.pack(">6H", 0x7FFE, 0x6000, 0x7FFE, NONE, 0x5000, 0x2000)
    ctypes.c_int.in_dll(m, "host_conv").value = 1
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(0x0013), f, len(f))
    m.mx_poll()
    rows, vs = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {})
    m.mx_eval(ctypes.addressof(rows))
    assert [m.host_x1(0, l) for l in range(3)] == [-2 * 0x2000, 0, -2 * (0x2000 - NONE)]
    vs[0] = sound(0) + 1163 * 20                                    # a sound lock: DEP its first route's depth
    m.mx_eval(ctypes.addressof(rows))
    assert [m.host_x1(0, l) for l in range(3)] == [1] * 3
    ctypes.c_int.in_dll(m, "host_conv").value = 0                   # not converted
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(0x0013), f, len(f) - 2)
    m.mx_poll()
    vs[0] = sound(0)
    m.mx_eval(ctypes.addressof(rows))
    assert [m.host_x1(0, l) for l in range(3)] == [1] * 3


def test_before_the_first_pass_each_first_route_is_stocks(m):
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {})
    m.mx_eval(ctypes.addressof(rows))
    assert all(m.host_x1(v, l) == 1 for v in range(16) for l in range(3))


def test_env2s_h_scales_its_routes(m):
    """ENV2's H (WT_MX_ENV byte 7 = 127 - the knob): 100 % (byte 0) bit for bit as before; the knob 32 (-32: -50 %)
    inverts and halves"""
    for b7, sign in ((0, 1), (127 - 32, -1)):
        m.host_mx_reset()
        m.host_erase()
        m.host_zero()
        ctypes.c_uint32.in_dll(m, "mx_host_kit").value = KIT
        put(m, 0, routes((4, 67, TOP)))
        m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes([0, 127, 64, 127, 50, 1, 1, b7]), 8)
        m.mx_poll()
        rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {(0, 67): 0x4000})
        m.mx_env_on(0)
        for _ in range(4):
            m.mx_eval(ctypes.addressof(rows))
            rows[17 + 67] = 0x4000
        lv, src = m.host_env(0, 1), m.host_word(0, 1)
        assert lv > 0
        if sign > 0:
            assert src == -lv                                       # 100 %: exactly -level, the routes' source
        else:
            assert src == (lv * (32 - 64) * 256 * -131072) >> 31 > 0   # -50 %: inverted, halved



# --- 2026-11-20 (the User): ENV2's MODE, RSET and H as destinations (0xE5..0xE7); HOLD lockable (slides' id 210) ------
E2.update({"MODE": 0xE5, "RSET": 0xE6, "H": 0xE7})


def test_lay_of_mode_rset_h_destinations(m):
    n, e = lay(m, routes((0, E2["MODE"], TOP), (1, E2["RSET"], TOP), (2, E2["H"], TOP), (4, E2["H"], TOP), (0, 0xE8, TOP)),
               bytes([8, 127, 32, 96, 24, 1, 0, 127 - 20]))
    assert n == 3                                                   # LFO1-3 laid; ENV2 into its own H and 0xE8: not
    assert e[0][0] - e[1][0] == e[1][0] - e[2][0] == -2              # three consecutive cells of the knob row
    assert lay.e2w == (8 << 8, 127 << 8, 32 << 8, 96 << 8, 24 << 8, 0x100, 0, 20 << 8)   # MODE 1, RSET 0, H the knob 20


def _route_run(m, knobs, record, events, frames, lfo1=0x7FFFFFFF, when=0, h7=0):
    """ENV2 on voice 0 with RECORD's routes, LFO1 at LFO1 from frame WHEN (0 before) -> [(stage, level, source word)]"""
    put(m, 0, routes(*record))
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [h7]), 8)
    m.mx_poll()
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {})
    lfo = arr(m, "mx_host_lfo", ctypes.c_int32, 16 * m.W)
    out = []
    for f in range(frames):
        lfo[0] = lfo1 if f >= when else 0
        m.host_dep_site(0, 0, lfo[0], 0x7FFE)
        if events.get(f) == "on":
            m.mx_env_on(0)
        if events.get(f) == "off":
            m.mx_env_off(1)
        m.mx_eval(ctypes.addressof(rows))
        out.append((m.host_stage(0, 1), m.host_env(0, 1), m.host_word(0, 1)))
    return out


def test_a_route_into_mode_switches_env2_to_ahd(m):
    """LFO1 at full scale, depth -64 into MODE (ADSR, 0x100): the cell 0, AHD; ENV2 is the model's AHD"""
    knobs, ev = (10, 127, 40, 64, 30, 1, 1), {0: "on", 120: "off"}
    out = _route_run(m, knobs, [(0, E2["MODE"], 0)], ev, 200)
    assert [x for _, x, _ in out] == model(knobs[:5] + (0, 1), ev, 200) != model(knobs, ev, 200)
    heard, setv = ctypes.c_int(), ctypes.c_int()
    assert m.mx_e2_knob(0, 5, ctypes.byref(heard), ctypes.byref(setv)) == 1 and (heard.value, setv.value) == (0, 0x100)


def test_a_route_into_rset_turns_the_restart_off(m):
    knobs, ev = (30, 127, 40, 64, 50, 1, 1), {0: "on", 40: "off", 70: "on"}
    out = _route_run(m, knobs, [(0, E2["RSET"], 0)], ev, 200)
    assert [x for _, x, _ in out] == model(knobs[:6] + (0,), ev, 200) != model(knobs, ev, 200)


def test_a_route_into_h_scales_env2s_source(m):
    """H 100 % (byte 7 0), pulled to the knob 0 (-64) by LFO1: the routes' source = level x mx_m_of(0); the level
    itself unchanged"""
    knobs, ev = (10, 127, 40, 64, 30, 1, 1), {0: "on"}
    base = _route_run(m, knobs, [], ev, 40)
    m.host_mx_reset()
    out = _route_run(m, knobs, [(0, E2["H"], 0)], ev, 40)
    assert [x for _, x, _ in out] == [x for _, x, _ in base]
    m0 = m.mx_m_of(0)
    assert all(w == mac(x, m0) for _, x, w in out) and all(w == -x for _, x, w in base)
    heard, setv = ctypes.c_int(), ctypes.c_int()
    assert m.mx_e2_knob(0, 7, ctypes.byref(heard), ctypes.byref(setv)) == 1 and (heard.value, setv.value) == (0, 0x7F00)


def test_mode_moved_to_ahd_in_the_decay_still_ends_at_the_note_off(m):
    """ADSR in its decay, MODE pulled to AHD at frame 60: the note-off at 100 falls (E_FALL) at DEC's rate to rest,
    not held at SUS until the next note"""
    knobs = (10, 127, 40, 64, 30, 1, 1)
    out = _route_run(m, knobs, [(0, E2["MODE"], 0)], {0: "on", 100: "off"}, 4000, when=60)   # DEC 40: 1.7 s to -60 dB
    assert out[59][0] == 3 and out[100][0] == 5 and out[-1][1] < out[100][1] >> 14   # falling: below -84 dB


def test_mode_rset_h_routes_change_nothing_without_such_a_route(m):
    knobs, ev = (30, 127, 40, 64, 50, 0, 0), {0: "on", 40: "off", 70: "on"}
    out = _route_run(m, knobs, [(0, 67, TOP)], ev, 200)
    assert [x for _, x, _ in out] == model(knobs, ev, 200) and all(w == -x for _, x, w in out)


def test_env2_takes_a_hold_lock(m):
    """slides' 8th kind (stored id 210): HOLD 0 locked on an AHD ENV2 whose record holds 16"""
    knobs, ev = (0, 16, 35, 64, 50, 0, 1), {0: "on"}
    put(m, 0, routes((4, 67, TOP)))
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [0]), 8)
    m.mx_poll()
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {})
    m.mx_env2_locks(0, (ctypes.c_uint16 * 8)(*([0xFFFF] * 7 + [0])))
    m.mx_env_on(0)
    out = []
    for _ in range(60):
        m.mx_eval(ctypes.addressof(rows))
        out.append(m.host_env(0, 1))
    assert out == model((0, 0, 35, 64, 50, 0, 1), ev, 60) != model(knobs, ev, 60)
    heard, setv = ctypes.c_int(), ctypes.c_int()
    assert m.mx_e2_knob(0, 1, ctypes.byref(heard), ctypes.byref(setv)) == 1 and setv.value == 0


def test_an_h_lock_and_a_route_into_h(m):
    """an H lock (the knob 32: -50 %) is the cell the routes add to; at no route its scale is the lock's"""
    knobs = (0, 127, 64, 127, 50, 1, 1)
    put(m, 0, routes((4, 67, TOP)))
    m.wish_put(ctypes.c_uint32(sound(0)), ctypes.c_uint32(ENV_TAG), bytes(list(knobs) + [0]), 8)
    m.mx_poll()
    rows, _ = frame_setup(m, {(v, l): 0 for v in range(16) for l in range(3)}, {})
    m.mx_env2_locks(0, (ctypes.c_uint16 * 8)(*([0xFFFF] * 6 + [32, 0xFFFF])))
    m.mx_env_on(0)
    for _ in range(4):
        m.mx_eval(ctypes.addressof(rows))
    lv = m.host_env(0, 1)
    assert m.host_word(0, 1) == mac(lv, m.mx_m_of(32 << 8))
    heard, setv = ctypes.c_int(), ctypes.c_int()
    m.mx_e2_knob(0, 7, ctypes.byref(heard), ctypes.byref(setv))
    assert heard.value == setv.value == 32 << 8


# --- 2026-11-20: the inserts' knobs as destinations (0xC0 + 7 j + i: slot j's K1..K6, MIX) -----------------------------
INS = 0xC0


def ins_setup(m, cells=None, last=None, group=0):
    c = arr(m, "ins_cell", ctypes.c_uint16, 17 * 14)
    for t in range(16):
        for i in range(14):
            c[14 * t + i] = (cells or {}).get((t, i), (10 + 3 * t + i) << 8)
    for i in range(14):
        c[14 * 16 + i] = 0
    arr(m, "ins_moff", ctypes.c_int16, 16 * 14)[:] = [0] * (16 * 14)
    lv = arr(m, "sl_lastv", ctypes.c_int8, 16)
    lv[:] = [-1] * 16
    for t, v in (last or {}).items():
        lv[t] = v
    ctypes.c_uint32.in_dll(m, "host_ins_group").value = group
    return c


def test_lay_of_insert_destinations(m):
    n, e = lay(m, routes((0, INS, TOP), (3, INS + 13, 0x5000), (4, INS + 6, 0x3000), (0, INS + 14, TOP), (1, 0xBF, TOP)))
    assert n == 3                                                   # LFO1, ENV1, ENV2 into the inserts; 0xCE, 0xBF skipped
    assert e[0][1] == -(TOP - NONE) * 2 and e[15][1] == (0x5000 - NONE) * 2 and e[19][1] == -(0x3000 - NONE) * 2
    assert len({e[0][0], e[15][0], e[19][0]}) == 3                  # three cells of the knob row, none a voice row slot
    assert all(c[0] > 2 * 100 or c[0] < 0 for c in (e[0], e[15], e[19]))


def test_the_frame_adds_routes_on_the_tracks_set_and_works_the_offset_out(m):
    lfo = {(v, l): (0x40000000 if l == 0 else -0x20000000 if l == 1 else 0) for v in range(16) for l in range(3)}
    put(m, 2, routes((0, INS + 1, TOP), (1, INS + 1, 0x5000), (0, INS + 13, 0x2000)))
    m.mx_poll()
    assert m.mx_ins_routes(2) == (1 << 1) | (1 << 13) and m.mx_ins_routes(3) == 0
    c = ins_setup(m, {(2, 1): 0x7000, (2, 13): 0x0400}, last={2: 5, 3: 6}, group=1)
    rows, vs = frame_setup(m, lfo, {})
    vs[5] = sound(2)                                                # voice 5 plays track 3's sound, voice 6 track 4's
    vs[6] = sound(3)
    m.mx_eval(ctypes.addressof(rows))
    x = max(0, min(TOP, 0x7000 + mac(-(TOP - NONE) * 2, -lfo[(5, 0)])))
    x = max(0, min(TOP, x + mac(-(0x5000 - NONE) * 2, -lfo[(5, 1)])))
    assert m.host_e2row(5, 8 + 1) == x                              # SET + the routes, clamped after each, as stock
    y = max(0, min(TOP, 0x0400 + mac(-(0x2000 - NONE) * 2, -lfo[(5, 0)])))
    assert m.host_e2row(5, 8 + 13) == y
    assert [m.host_e2row(6, 8 + i) for i in range(14)] == [c[14 * 3 + i] for i in range(14)]   # no route: SET exactly
    off = arr(m, "ins_moff", ctypes.c_int16, 16 * 14)
    assert off[14 * 2 + 1] == x - 0x7000 and off[14 * 2 + 13] == y - 0x0400
    assert all(off[14 * 2 + i] == 0 for i in range(14) if i not in (1, 13))
    assert all(off[14 * 3 + i] == 0 for i in range(14))
    # the voice leaves the track (another sound): the offsets held, not worked out again
    vs[5] = sound(7)
    m.mx_eval(ctypes.addressof(rows))
    assert off[14 * 2 + 1] == x - 0x7000
    # another group: track 3's offsets not touched
    vs[5] = sound(2)
    off[14 * 2 + 1] = 0
    ctypes.c_uint32.in_dll(m, "host_ins_group").value = 2
    m.mx_eval(ctypes.addressof(rows))
    assert off[14 * 2 + 1] == 0


def test_insert_destinations_change_nothing_else(m):
    """bit-exact: the voice rows and ENV2's knob cells as before with the inserts' cells in the knob row"""
    lfo = {(v, l): 0x7FFFFFFF for v in range(16) for l in range(3)}
    put(m, 0, routes((0, 67, 0x6000), (0, INS, TOP)))
    m.mx_poll()
    ins_setup(m, last={0: 0}, group=0)
    rows, vs = frame_setup(m, lfo, {})
    m.mx_eval(ctypes.addressof(rows))
    assert cell(rows, 0, 67) == max(0, min(TOP, 0x3000 + mac((0x6000 - NONE) * 2, lfo[(0, 0)])))
    assert m.host_scratch_sum() == 0

