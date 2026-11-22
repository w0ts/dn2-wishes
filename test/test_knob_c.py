"""Knob notches and our popups' slow turns (csrc/knobs/notch.c, docs/knob-notch.md), compiled for the host and driven
through ctypes: a knob item (rec.c smp_ui_pop -> kn_item), then the writes it drives (kn_value), against the rules
of knob.h. The stock paths (the setters' writes, LOCK_SET) are the emulator's check (scripts/emu_knobnotch.py)."""

from __future__ import annotations

import ctypes
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "csrc" / "knobs" / "notch.c"
H = (ROOT / "csrc" / "knobs" / "knob.h").read_text()
K = {m.group(1): int(m.group(2)) for m in re.finditer(r"#define (KN_\w+)\s+(\d+)u?\b", H)}
HOLD, PASS, HOLD_END = K["KN_HOLD"], K["KN_PASS"], K["KN_HOLD_END"]
SLOW, DIV, FAST, MUL = K["KN_POP_SLOW"], K["KN_POP_DIV"], K["KN_POP_FAST"], K["KN_POP_FAST_MUL"]
N = 0x4000


@pytest.fixture(scope="module")
def L(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        pytest.skip("no host C compiler")
    d = tmp_path_factory.mktemp("knob")
    out = d / "libknob.so"
    r = subprocess.run([cc, "-shared", "-fPIC", "-O1", "-std=gnu11", "-Wall", "-Wextra", "-Werror", str(SRC), "-o", str(out)],
                       capture_output=True, text=True)
    if r.returncode:
        pytest.fail(r.stderr)
    lib = ctypes.CDLL(str(out))
    lib.kn_value.restype = ctypes.c_int32
    lib.kn_value.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    lib.kn_units.restype = ctypes.c_int
    lib.kn_whole.restype = ctypes.c_int32
    lib.kn_whole.argtypes = [ctypes.c_int32, ctypes.c_int, ctypes.c_int32]
    lib.kn_centre.restype = ctypes.c_int32
    return lib


class Knob:
    """one knob's items and the value they drive, as stock's step would (VALUE += STEP a count)"""

    def __init__(self, L, code=8, value=N + 0x500, step=0x100, key=83):
        self.L, self.code, self.v, self.step, self.key = L, code, value, step, key
        self.clock = ctypes.c_uint32.in_dll(L, "kn_host_frames")
        self.clock.value += 100_000                     # a fresh knob: any old hold long gone

    def item(self, d, gap=100, write=True):
        self.clock.value += gap
        it = bytes([1, 0, 0, 0, 0, 0, 0, self.code, d & 0xFF, 0, 0, 0])
        self.L.kn_item(ctypes.c_char_p(it))
        if write and d:
            self.v = self.L.kn_value(self.key, self.v, self.v + d * self.step, N)
        return self.v


def test_a_slow_turn_across_lands_on_the_notch_and_holds(L):
    k = Knob(L)
    vals = [k.item(-2) for _ in range(3)]               # 0x4500 -> 0x4300 -> 0x4100 -> (0x3f00) caught
    assert vals == [N + 0x300, N + 0x100, N]
    held = [k.item(-1) for _ in range(HOLD + 1)]        # the hold: HOLD counts more the same way stay on it
    assert held == [N] * HOLD + [N - 0x100]             # then it moves on


def test_a_hold_is_counted_in_counts_whatever_the_records(L):
    k = Knob(L, value=N + 0x100)
    assert k.item(-2) == N
    assert k.item(-(HOLD - 1)) == N and k.item(-1) == N  # HOLD counts in two records: still there
    assert k.item(-2) == N - 0x200


def test_a_turn_back_releases_at_once(L):
    k = Knob(L, value=N + 0x200)
    assert k.item(-3) == N
    assert k.item(+1) == N + 0x100                      # back: free


def test_a_fast_turn_passes(L):
    k = Knob(L, value=N + 0x300)
    assert k.item(-PASS) == N + 0x300 - PASS * 0x100    # a record of PASS counts goes through
    k2 = Knob(L, value=N + 0x300)
    assert k2.item(-(PASS - 1)) == N                    # one count less is caught


def test_from_the_notch_it_moves_at_once(L):
    k = Knob(L, value=N)
    assert k.item(+1) == N + 0x100                      # D2: free from rest


def test_a_pause_ends_the_hold(L):
    k = Knob(L, value=N + 0x100)
    assert k.item(-2) == N
    assert k.item(-1, gap=HOLD_END + 1) == N - 0x100


def test_another_value_under_the_knob_is_not_held(L):
    k = Knob(L, value=N + 0x100)
    assert k.item(-2) == N
    k.key, k.v = 84, N + 0x500                          # another page: another record on this knob
    assert k.item(-1) == N + 0x400


def test_outside_a_knob_item_nothing_changes(L):
    k = Knob(L, value=N + 0x100)
    L.kn_item(ctypes.c_char_p(bytes([2, 0, 0, 0, 0, 0, 0, 10, 1, 0, 0, 0])))   # a key's item (or a MIDI one)
    assert L.kn_value(83, N + 0x100, N - 0x100, N) == N - 0x100


def test_the_popups_slow_turns(L):
    k = Knob(L, code=4)

    def units(d):
        k.item(d, write=False)                          # (the knob item being handled: D's)
        return L.kn_units(d)
    assert [units(1) for _ in range(6)] == [0, 0, 1, 0, 0, 1]               # 1 unit every DIV counts
    assert units(1) == 0 and units(-1) == 0             # a turn back drops the leftover
    assert units(SLOW + 1) == SLOW + 1                  # 1 a count above SLOW
    assert units(-FAST) == -FAST * MUL                  # MUL a count from FAST
    L.kn_item(ctypes.c_char_p(bytes(12)))               # no knob item: the counts as they are
    assert L.kn_units(2) == 2


def test_whole_units_and_the_top(L):
    assert L.kn_whole(0x7FFE, -1, 0x7FFE) == 0x7E00     # the fraction dropped
    assert L.kn_whole(0x7F00, +1, 0x7FFE) == 0x7FFE     # the top end
    assert L.kn_whole(0x40FE, +1, 0x7FFE) == 0x4100
    assert L.kn_whole(0x0000, -1, 0x7FFE) == 0
    assert L.kn_whole(0x7FFE, 0, 0x7FFE) == 0x7FFE      # no unit: as it was


def test_stock_centres(L):
    assert L.kn_centre(71) == N and L.kn_centre(83) == N and L.kn_centre(204) == 0x3F00
    assert L.kn_centre(37) == -1                        # RESO: unipolar
