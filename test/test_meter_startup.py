"""The DSP and CLIP labels while the DN2 starts (csrc/meter/startup.c; 2026-11-20, the User: "at boot it says !CLIP
and !DSP... can we fix it?"): compiled for the host and driven through ctypes, the DSP's load (link.c smp_dsp_load)
and the clips' forgetting (mixer.c mix_clip_forget) as stubs. What meter.c does with the answer (the labels unlit,
DSP's stamp and hysteresis cleared) is the emulator's check (scripts/emu_mixmeter.py, startup)."""

from __future__ import annotations

import ctypes
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STARTUP = ROOT / "csrc" / "meter" / "startup.c"
LOADING, UPGRADE = 1, 2
SETTLE = 3000                              # startup.c START_SETTLE: frames, 2 s

STUBS = r"""
int host_load = -1;
unsigned int host_forgets = 0;
int smp_dsp_load(void) { return host_load; }
void mix_clip_forget(void) { host_forgets++; }
"""


@pytest.fixture()
def lib(tmp_path):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    assert cc, "no host C compiler"
    (tmp_path / "stubs.c").write_text(STUBS)
    so = tmp_path / "startup.so"
    subprocess.run([cc, "-O1", "-Wall", "-Werror", "-shared", "-fPIC", "-DSTART_HOST", "-I", str(STARTUP.parent),
                    str(STARTUP), str(tmp_path / "stubs.c"), "-o", str(so)], check=True, capture_output=True, text=True)
    lib = ctypes.CDLL(str(so))
    lib.mtr_starting.argtypes = [ctypes.c_uint, ctypes.c_uint]
    return lib


def word(lib, name):
    return ctypes.c_uint.in_dll(lib, name)


def set_load(lib, v):
    ctypes.c_int.in_dll(lib, "host_load").value = v


def test_quiet_from_the_load_while_the_dsp_is_silent(lib):
    for f in range(1, 20_001, 500):
        assert lib.mtr_starting(f, 0) == 1
    assert word(lib, "mtr_start_done").value == 0
    assert word(lib, "host_forgets").value == 40          # every poll of the start-up forgets the clips


def test_over_after_two_seconds_of_reports_with_loading_over(lib):
    set_load(lib, 40)
    assert lib.mtr_starting(1001, 0) == 1                  # the first report: the settle starts
    assert lib.mtr_starting(1001 + SETTLE - 2, 0) == 1
    assert lib.mtr_starting(1001 + SETTLE, 0) == 0         # 2 s: over, and the clips forgotten once more
    n = word(lib, "host_forgets").value
    assert word(lib, "mtr_start_done").value == 1
    for f in (5000, 9000, 50_000):                         # then never again: the labels as before
        set_load(lib, -1 if f == 9000 else 100)
        assert lib.mtr_starting(f, LOADING if f == 50_000 else 0) == 0
    assert word(lib, "host_forgets").value == n


def test_loading_or_a_break_in_the_reports_starts_the_settle_again(lib):
    set_load(lib, 40)
    lib.mtr_starting(101, 0)
    assert lib.mtr_starting(101 + 2000, LOADING) == 1      # stock's "Loading..." up again: from the top
    assert word(lib, "mtr_start_at").value == 0
    lib.mtr_starting(3001, 0)
    set_load(lib, -1)                                      # a second without a report: from the top
    assert lib.mtr_starting(3001 + 2000, 0) == 1
    set_load(lib, 40)
    lib.mtr_starting(5001 + 1, 0)
    assert lib.mtr_starting(5001 + SETTLE - 2, 0) == 1     # 2 s from the new start, not from the first
    assert lib.mtr_starting(5003 + SETTLE, 0) == 0


def test_an_upgrade_alone_does_not_hold_it(lib):
    set_load(lib, 40)
    lib.mtr_starting(101, UPGRADE)
    assert lib.mtr_starting(101 + SETTLE, UPGRADE) == 0    # (the labels there are smp_bulk_recent's, meter.c)


def test_meter_c_holds_dsp_and_clip_to_it():
    src = (ROOT / "csrc" / "meter" / "meter.c").read_text()
    body = src[src.index("static u32 icons_live(u32 f)"):]
    body = body[:body.index("\n}\n")]
    assert "int starting = mtr_starting(f, MTR[MTR_QUIET]);" in body
    assert "MTR[MTR_ICON_AT_D] = 0;" in body and "MTR[MTR_ICON_HYS] &= ~1u;" in body
    assert "!starting && smp_skipped_any()" in body
    assert "!starting && over(1u, smp_dsp_load()" in body
    assert "!starting && mix_clip_recent(f)" in body
    assert body.index("mtr_starting(") < body.index("smp_bulk_recent()")
