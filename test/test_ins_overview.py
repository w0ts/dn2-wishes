"""The inserts overview (FX held; csrc/inserts/ovw.c): the C's letters and names are the model's
(dnfw.inserts.overview), and the model's picture keeps to its layout."""

import pathlib
import re

from dnfw.inserts import design, overview as O

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVW = (ROOT / "csrc/inserts/ovw.c").read_text()
DRAW = (ROOT / "csrc/inserts/ovw_draw.c").read_text()
FONT_H = (ROOT / "csrc/inserts/ovw_font.h").read_text()


def test_font_header_is_the_model():
    chars = re.search(r'OVW_CHARS\[\] = "([^"]*)"', FONT_H).group(1)
    glyphs = [int(w, 16) for w in re.findall(r"0x([0-9a-f]{4})", FONT_H.split("OVW_GLYPH")[-1])]
    assert chars == O.CHARS
    assert glyphs == [O.glyph_bits(c) for c in O.CHARS]


def test_names_are_the_models_and_cover_every_type():
    names = re.search(r"NAME3\[\] = \{(.*?)\};", DRAW, re.S).group(1)
    assert re.findall(r'"([A-Z]*)"', names) == O.NAME3
    assert len(O.NAME3) == len(design.NAMES)
    assert all(len(n) == 3 for n in O.NAME3[1:])
    for name in O.NAME3[1:]:
        assert all(c in O.CHARS for c in name)


def test_every_state_fits_its_cell():
    st = [[(t + j) % 4 for j in range(2)] for t in range(16)]
    ty = [[1 + (2 * t + j) % 13 for j in range(2)] for t in range(16)]
    pic = O.render(st, ty, 5, 63)
    assert len(pic) == 64 and all(len(r) == 128 for r in pic)
    assert all(pic[r][x] for r in range(0, 9) for x in (0, 127))       # the title bar lit
    for t in range(16):
        for j in range(2):
            x, r0 = 16 * (t % 8), 10 + 27 * (t // 8) + 7 + 10 * j
            assert not any(pic[r][x + 15] for r in range(r0, r0 + 9))   # a dark column between cells


def test_blink_only_moves_full_cells():
    st = [[O.FULL, O.RUNS]] + [[O.OFF, O.MIX0]] * 15
    ty = [[8, 1]] + [[0, 4]] * 15
    on, off = O.render(st, ty, 0, -1, True), O.render(st, ty, 0, -1, False)
    moved = {(r, x) for r in range(64) for x in range(128) if on[r][x] != off[r][x]}
    assert moved and all(0 <= x <= 14 and 17 <= r <= 25 for r, x in moved)


def test_the_hold_is_a_second_and_fx_goes_on_release():
    assert re.search(r"#define LONG_TICKS +121u", OVW)              # one second at the unit's 121 ticks
    assert "ovw_key" in (ROOT / "csrc/sampler/rec.c").read_text()
    assert "ovw_poll" in (ROOT / "csrc/waverider/page.c").read_text()
