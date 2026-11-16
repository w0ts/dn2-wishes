"""The load labels' event stamps (csrc/meter/stamp.h, meter.c icons_live and mtr_tlm).

A label is lit while its last event is younger than ICON_HOLD. The stamp is f | 1 (never 0, 0 meaning
none); its age used to be f - stamp, which on an even frame is f - (f + 1): 0xFFFFFFFF, so a label whose
event held on (C over 90 %, say) went dark on every poll that fell on an even frame. stamp.h takes the
age from f | 1. The helpers are compiled for the host and driven as icons_live drives them; the last test
holds meter.c to them (it fails on the code before the fix)."""

from __future__ import annotations

import ctypes
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
METER = ROOT / "csrc" / "meter"
ICON_HOLD = 1500                                    # meter.c: frames, a second after the last event
WINDOW = 750                                        # meter.c: a half second

HARNESS = r"""
#include "stamp.h"
unsigned int t_stamp(unsigned int f) { return mtr_stamp(f); }
unsigned int t_age(unsigned int at, unsigned int f) { return mtr_age(at, f); }
"""


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    assert cc, "no host C compiler"
    d = tmp_path_factory.mktemp("stamp")
    (d / "harness.c").write_text(HARNESS)
    so = d / "stamp.so"
    subprocess.run([cc, "-O1", "-Wall", "-Werror", "-shared", "-fPIC", "-I", str(METER), str(d / "harness.c"),
                    "-o", str(so)], check=True, capture_output=True, text=True)
    lib = ctypes.CDLL(str(so))
    for fn in (lib.t_stamp, lib.t_age):
        fn.restype = ctypes.c_uint
    lib.t_stamp.argtypes = [ctypes.c_uint]
    lib.t_age.argtypes = [ctypes.c_uint, ctypes.c_uint]
    return lib


FRAMES = [0, 1, 2, 3, 750, 751, 1500, 0x7FFFFFFE, 0x7FFFFFFF, 0xFFFFFFFE, 0xFFFFFFFF]


@pytest.mark.parametrize("f", FRAMES)
def test_a_stamp_is_never_none(lib, f):
    assert lib.t_stamp(f) != 0


@pytest.mark.parametrize("f", FRAMES)
def test_an_event_is_age_zero_on_its_own_frame_even_or_odd(lib, f):
    assert lib.t_age(lib.t_stamp(f), f) == 0


@pytest.mark.parametrize("f", FRAMES)
def test_the_age_counts_the_frames_since_within_one(lib, f):
    """an even frame's stamp is a frame ahead, an odd one's seen from an even frame a frame behind"""
    at = lib.t_stamp(f)
    for k in (1, 2, 3, 374, 375, ICON_HOLD - 2, ICON_HOLD - 1, ICON_HOLD, ICON_HOLD + 1):
        age = lib.t_age(at, (f + k) & 0xFFFFFFFF)
        assert k - 1 <= age <= k + 1, (f, k, age)


def lit(lib, at, f):
    """icons_live's hold, as meter.c tests it"""
    return at != 0 and lib.t_age(at, f) < ICON_HOLD


@pytest.mark.parametrize("start", [0, 1, 750, 751])
def test_an_event_that_holds_keeps_its_label_lit_at_every_poll(lib, start):
    """the event stamped again at each poll (a window apart), its label tested the same poll"""
    at = 0
    for n in range(40):
        f = start + WINDOW * n
        at = lib.t_stamp(f)
        assert lit(lib, at, f), (start, n, f)


@pytest.mark.parametrize("start", [0, 1])
def test_an_event_gone_keeps_its_label_a_second_then_not(lib, start):
    at = lib.t_stamp(start)
    assert lit(lib, at, start + ICON_HOLD - 2)
    assert not lit(lib, at, start + ICON_HOLD + 1)


def test_the_old_age_wrapped_on_an_even_frame():
    """what this replaces: f - (f | 1) on an even frame"""
    f = 1500
    assert (f - (f | 1)) & 0xFFFFFFFF == 0xFFFFFFFF


def body(src, name):
    m = re.search(r"\n[a-z][^\n]*\b" + name + r"\([^)]*\)[^\n]*\n\{(.*?)\n\}", src, re.S)
    assert m, name
    return m.group(1)


def test_meter_c_takes_every_label_stamp_and_age_from_stamp_h():
    src = (METER / "meter.c").read_text()
    assert '#include "stamp.h"' in src
    live, tlm = body(src, "icons_live"), body(src, "mtr_tlm")
    assert "mtr_stamp(f)" in live and "f | 1u" not in live
    assert "mtr_age(at, f) < ICON_HOLD" in live
    assert not re.search(r"\bf\s*-\s*at\b", live)
    assert "mtr_age(MTR[MTR_ICON_AT_D + k], f)" in tlm
    assert not re.search(r"\bf\s*-\s*MTR\[MTR_ICON_AT", tlm)
