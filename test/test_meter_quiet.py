"""The CPU label's quiet (csrc/meter/quiet.c, docs/meter.md): compiled for the host and driven through ctypes over a
model of the stock 1.12 memory it reads (the loading view at *0x44648980, the title's message line at *0x446488c8,
the RPC dispatcher's OsUpgradeState at *0x445fb5d0). What meter.c does with the answer (the label unlit, its hold and
hysteresis cleared, C read again only from a fresh window) is the emulator's check; the addresses are traced in stock
1.12's code (docs/meter.md)."""

from __future__ import annotations

import ctypes
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUIET = ROOT / "csrc" / "meter" / "quiet.c"

LOADING, UPGRADE = 1, 2
VIEW_P, MSG_P, UPG_P = 0x44648980, 0x446488C8, 0x445FB5D0
CB_P = VIEW_P + 4                          # the view's weak_ptr: its control block (+4: the use count)
BASE, SIZE = 0x445F0000, 0x00140000        # the model's window: the three pointers and the objects below
VIEW, MSG, STATE, TEXT = 0x44690000, 0x446A0000, 0x446B0000, 0x446C0000
CB = 0x446D0000

HARNESS = r"""
#include <string.h>
typedef unsigned int u32;
static unsigned char mem[0x00140000];
u32 host_rd32(u32 a)
{
    if (a < 0x445F0000u || a + 4u > 0x445F0000u + sizeof mem)
        return 0;
    const unsigned char *p = mem + (a - 0x445F0000u);
    return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
}
void host_clear(void) { memset(mem, 0, sizeof mem); }
void host_wr8(u32 a, unsigned v) { mem[a - 0x445F0000u] = (unsigned char)v; }
"""


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    assert cc, "no host C compiler"
    d = tmp_path_factory.mktemp("quiet")
    (d / "harness.c").write_text(HARNESS)
    (d / "proto.h").write_text("unsigned int host_rd32(unsigned int a);\n")
    so = d / "quiet.so"
    subprocess.run([cc, "-O1", "-Wall", "-Werror", "-shared", "-fPIC", "-DQUIET_RD32(a)=host_rd32(a)",
                    "-include", str(d / "proto.h"), "-I", str(QUIET.parent), str(QUIET), str(d / "harness.c"),
                    "-o", str(so)], check=True, capture_output=True, text=True)
    lib = ctypes.CDLL(str(so))
    lib.mtr_quiet_why.restype = ctypes.c_uint
    lib.host_rd32.restype = ctypes.c_uint
    lib.host_rd32.argtypes = [ctypes.c_uint]
    lib.host_wr8.argtypes = [ctypes.c_uint, ctypes.c_uint]
    return lib


class Mem:
    def __init__(self, lib):
        self.lib = lib
        lib.host_clear()

    def w32(self, a, v):
        for k in range(4):
            self.lib.host_wr8(a + k, (v >> (24 - 8 * k)) & 0xFF)

    def text(self, a, s):
        for k, b in enumerate(s.encode() + b"\0"):
            self.lib.host_wr8(a + k, b)

    def idle(self):
        """stock booted and ready: the view built (no polls pending, no mark), the message line showing nothing"""
        self.w32(VIEW_P, VIEW)
        self.w32(CB_P, CB)
        self.w32(CB + 4, 1)
        self.w32(VIEW + 504, 0)
        self.w32(VIEW + 508, 0xFFFFFFFF)
        self.w32(MSG_P, MSG)
        self.w32(MSG + 72, TEXT)
        self.text(TEXT, "FX")
        self.w32(MSG + 76, 0)
        return self


def why(lib):
    return lib.mtr_quiet_why()


def test_the_model_reads_big_endian(lib):
    m = Mem(lib)
    m.w32(VIEW_P, 0x12345678)
    assert lib.host_rd32(VIEW_P) == 0x12345678


def test_from_reset_until_the_view_is_built_it_is_the_boot(lib):
    Mem(lib)                                    # BSS as reset leaves it
    assert why(lib) == LOADING
    m = Mem(lib)
    m.w32(CB_P, 0x446D0002)                     # not a word address: not a control block
    assert why(lib) == LOADING
    m = Mem(lib).idle()
    m.w32(VIEW_P, 0x44690002)                   # held, but not a word address: not a view
    assert why(lib) == LOADING


@pytest.mark.parametrize("uses", [0, 0xFFFFFFFF])
def test_a_view_no_one_holds_is_not_read(lib, uses):
    m = Mem(lib).idle()
    m.w32(VIEW + 504, 7)                        # what its freed memory may hold now
    m.w32(VIEW + 508, 3)
    m.w32(CB + 4, uses)
    assert why(lib) == 0


def test_stock_ready_is_not_quiet(lib):
    Mem(lib).idle()
    assert why(lib) == 0


@pytest.mark.parametrize("polls,mark", [(1, -1), (2, -1), (3, 0), (40, 9), (0, 5)])
def test_polls_not_ready_or_the_loading_mark_is_loading(lib, polls, mark):
    m = Mem(lib).idle()
    m.w32(VIEW + 504, polls)
    m.w32(VIEW + 508, mark & 0xFFFFFFFF)
    assert why(lib) == LOADING


@pytest.mark.parametrize("text,count,quiet", [
    ("Loading...", 120, LOADING), ("Loading...", 1, LOADING),
    ("Loading...", 0, 0), ("Loading...", -1, 0),          # its countdown run out: gone
    ("Loading", 120, 0), ("Loading...!", 120, 0), ("FX (1/3)", 120, 0), ("", 120, 0)])
def test_the_message_line_showing_loading(lib, text, count, quiet):
    m = Mem(lib).idle()
    m.text(TEXT, text)
    m.w32(MSG + 76, count & 0xFFFFFFFF)
    assert why(lib) == quiet


@pytest.mark.parametrize("off", [1, 2, 3])
def test_the_text_at_any_byte_address(lib, off):
    m = Mem(lib).idle()
    m.w32(MSG + 72, TEXT + off)
    m.text(TEXT + off, "Loading...")
    m.w32(MSG + 76, 30)
    assert why(lib) == LOADING


def test_a_message_line_not_built_or_its_text_not_in_ram(lib):
    m = Mem(lib).idle()
    m.w32(MSG_P, 0)
    assert why(lib) == 0
    m.w32(MSG_P, MSG)
    m.w32(MSG + 72, 0)                          # no text
    m.w32(MSG + 76, 30)
    assert why(lib) == 0


@pytest.mark.parametrize("state,quiet", [(0, 0), (1, UPGRADE), (2, UPGRADE), (3, UPGRADE), (4, 0), (5, 0),
                                         (0xFFFFFFFF, 0)])
def test_the_os_upgrade_state(lib, state, quiet):
    m = Mem(lib).idle()
    m.w32(UPG_P, STATE)
    m.w32(STATE + 4, state)
    assert why(lib) == quiet


def test_no_rpc_dispatcher_yet_is_no_upgrade(lib):
    m = Mem(lib).idle()
    m.w32(UPG_P, 0)                             # the static not built: no RPC message since reset
    m.w32(STATE + 4, 2)
    assert why(lib) == 0
    m.w32(UPG_P, STATE + 2)                     # not a word address
    assert why(lib) == 0


def test_both_at_once(lib):
    m = Mem(lib).idle()
    m.w32(UPG_P, STATE)
    m.w32(STATE + 4, 3)
    m.w32(VIEW + 504, 2)
    assert why(lib) == LOADING | UPGRADE
