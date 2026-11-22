"""INSERT SEL and the FX icons (2026-11-20, the User: "same code/ui as filter and synth engine"): one table of names and
icons (dnfw.waverider.msel FX_NAMES, FX_ICONS) for INSERT SEL (csrc/msel/msel.c), the INSERT page's M.SEL box
(csrc/inserts/ins.c) and the FX overview (csrc/inserts/ovw_draw.c, dnfw.inserts.overview); the list's order is
M.SEL's (ins.c ORDER)."""

import pathlib
import re

from dnfw.inserts import design, overview as O
from dnfw.waverider import msel as M

ROOT = pathlib.Path(__file__).resolve().parents[1]
INS = (ROOT / "csrc/inserts/ins.c").read_text()
MSEL = (ROOT / "csrc/msel/msel.c").read_text()
DRAW = (ROOT / "csrc/inserts/ovw_draw.c").read_text()


def _c_list(src: str, name: str) -> list[str]:
    return re.findall(r"[\w\"]+", re.search(name + r"\[TYPES\] = \{(.*?)\};", src, re.S).group(1))


def test_every_type_has_a_name_and_an_icon():
    assert sorted(M.FX_NAMES) == list(range(len(design.NAMES)))
    assert sorted(M.FX_ICONS) == list(range(len(design.NAMES)))
    for rows in M.FX_ICONS.values():
        assert len(rows) == 5 and all(len(r) == 7 and set(r) <= {".", "#"} for r in rows)
        assert any("#" in r for r in rows)
    pics = [tuple(r) for r in M.FX_ICONS.values()]
    assert len(set(pics)) == len(pics)                              # no two alike


def test_names_and_order_are_the_insert_pages():
    names = [n.strip('"') for n in _c_list(INS, r"const char \*const NAME")]
    assert names == [M.FX_NAMES[y] for y in range(len(names))]
    order = [int(v) for v in _c_list(INS, r"static const u8 ORDER")]
    assert order == M.fx_rows()
    assert M.fx_rows()[0] == 0                                      # OFF first, then A-Z


def test_header_carries_the_insert_rows():
    h = M.c_header()
    assert f"#define MSEL_IROWS {len(design.NAMES)}" in h
    assert "msel_irows[MSEL_IROWS] = {" + ", ".join(map(str, M.fx_rows())) + "}" in h
    assert "msel_iicon[14][5]" in h and "msel_iname[14]" in h


def test_one_drawing_for_the_three_lists():
    """MACHINE SEL, FILTER SEL and INSERT SEL go through the same sel_draw and cell; the overview and the M.SEL box read
    the icons through msel_fx_icon (no second table)"""
    assert MSEL.count("sel_draw(c, msel_") == 3
    assert "static void cell(" in MSEL and MSEL.count("static void cell(") == 1
    assert "msel_fx_icon(" in INS and "msel_fx_icon(" in DRAW
    assert not re.search(r"\{\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\}", DRAW)   # no icon bytes there


def test_overview_cells_show_icons():
    st = [[O.RUNS, O.MIX0]] + [[O.OFF, O.OFF]] * 15
    ty = [[7, 13]] + [[0, 0]] * 15
    pic = O.render(st, ty, 0, -1)
    x, r0 = 0, 10 + 7
    for r, line in enumerate(M.FX_ICONS[7]):                       # RUNS: a lit box, the icon unlit
        for k, ch in enumerate(line):
            assert pic[r0 + 2 + r][x + 4 + k] == (0 if ch == "#" else 1)
    r1 = r0 + 10
    for r, line in enumerate(M.FX_ICONS[13]):                      # MIX 0: the icon lit
        for k, ch in enumerate(line):
            assert pic[r1 + 2 + r][x + 4 + k] == (1 if ch == "#" else 0)
