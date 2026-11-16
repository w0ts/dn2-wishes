"""DRONE's HOLD latch (csrc/hold/hold.c) reads the track's HOLD value out of the live sound: the same layout
page.c and rec.c read (sound at [0x800052a0] + 52 + 1163 t, its 16-bit values from +20, the machine type
value 101 at +0xDE). 2026-11-10: hold.c had the values at +48, so it read another parameter's byte and the
latch never knew HOLD (the User: HOLD does nothing on the unit)."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _define(text: str, name: str) -> int:
    m = re.search(rf"#define {name}\s+(0x[0-9A-Fa-f]+|\d+)u?", text)
    assert m, name
    return int(m.group(1), 0)


def test_hold_reads_the_values_where_the_page_does():
    hold = (ROOT / "csrc/hold/hold.c").read_text()
    page = (ROOT / "csrc/waverider/page.c").read_text()
    assert _define(hold, "SOUND_BASE") == 52 and "52u + 1163u * t + 0x14u" in page
    assert _define(hold, "SOUND_STRIDE") == 1163
    assert _define(hold, "SOUND_PARAMS") == 0x14
    assert _define(hold, "SOUND_TYPE") == 0xDE == 0x14 + 2 * 101
