"""The LFO4 mod: it applies to stock 1.12 (2026-11-14, docs/lfo-112-port.md; it was 1.11's), refuses what it cannot
sit on, and reproduces the image that was gated.

`scripts/gen_lfo4_code.py` packages `build_lfo4_browser.RELEASE`, the build
the release `.syx` came from, so what is asserted here is **byte equality with
`lfo4-fast`** (`python scripts/build_lfo4_browser.py --name lfo4-fast`).

`lfo4-fast` is `lfo4-everyvoice4` -- the release twin of the code that passed
tests 10 and 11 on the instrument (`docs/lfo4-build-plan.md`) -- with an idle
LFO4 costing the frame nothing and the `memcpy` / `memset` test moved into the
stubs, after the owner's save-while-playing stutter was bisected to lfo4
(2026-09-27).
"""

import pathlib
import struct

import pytest

from dnfw.mods import ModError, lfo4
from dnfw.patch import paramtable

ROOT = pathlib.Path(__file__).resolve().parent.parent
STOCK_112 = ROOT / "00_Resources/00_Firmware/Digitone_II_OS1.12_dist.zip"
GATED = ROOT / "out/lfo4-fast/section_3_MAIN_OS.bin"     # (1.11's gated build: none on 1.12 yet, so it skips)
BASE = lfo4.BASE


@pytest.fixture(scope="module")
def dn2():
    if not STOCK_112.exists():
        pytest.skip("Digitone II 1.12 is not in 00_Resources")
    from dnfw.cli.files import read_image
    from dnfw.firmware.load import load
    return load(read_image(STOCK_112))


@pytest.fixture(scope="module")
def stock(dn2):
    return dn2.container.find(lfo4.SECTION).unpack()


@pytest.fixture(scope="module")
def applied(stock):
    return lfo4.compose(stock)


def test_is_the_image_that_was_gated(applied):
    if not GATED.exists():
        pytest.skip("out/lfo4-fast is not built")
    assert applied == GATED.read_bytes()


def test_changes_nothing_outside_its_extents(stock, applied):
    allowed = [(e.start, e.end) for e in lfo4.extents()]
    stray = [i for i in range(len(stock))
             if stock[i] != applied[i] and not any(lo <= i < hi for lo, hi in allowed)]
    assert stray == []
    assert len(applied) == allowed[-1][1]


def test_ships_no_stock_table():
    """The relocated table's place in the packaged blob is blank."""
    blob = bytes.fromhex(lfo4.SPEC["blob"])
    at = lfo4.SPEC["table_offset"]
    assert not any(blob[at:at + paramtable.RECORD * lfo4.SPEC["table_records"]])


def test_refuses_an_image_that_already_grew(stock):
    with pytest.raises(ModError, match="appended"):
        lfo4.compose(stock + bytes(16))


def test_refuses_a_changed_edit_site(stock):
    e = lfo4._edits()[0]
    bad = bytearray(stock)
    bad[e["va"] - BASE] ^= 0xFF
    with pytest.raises(ModError, match="not stock"):
        lfo4.compose(bytes(bad))


def test_carries_a_table_edit_made_before_it(stock):
    """An edit made in the stock table before lfo4 (on 1.11: moddest's thirteen masks, fxmod's Chorus records, mods
    our 1.12 build does not have) is in lfo4's relocated copy -- why lfo4 is applied last (dnfw.mods.SHIPPED)."""
    edited = bytearray(stock)
    table = paramtable.TABLE - BASE
    picks = (78, 95, 244, 319)                              # four records' flags (+44), anywhere in the table
    for rid in picks:
        at = table + paramtable.RECORD * rid + 44
        struct.pack_into(">I", edited, at, struct.unpack_from(">I", edited, at)[0] ^ 0x00A50000)
    out = lfo4.compose(bytes(edited))
    moved = lfo4.SPEC["area_va"] - BASE + lfo4.SPEC["table_offset"]
    for rid in picks:
        at = table + paramtable.RECORD * rid + 44
        assert out[moved + at - table:moved + at - table + 4] == bytes(edited[at:at + 4]), rid
