"""Controls that move on OUR pages (2026-11-12, docs/modulation-more.md): PERC's Machinedrum page, the
Monomachine machines' pages (SOPHIE, PLAITS, TB-303, DRONE, ANALOG 2, MONOMACHINE) and the sample
machines' pages draw their own knobs, and each one asks csrc/modulation/moving.c for the same line
stock's cells get. What can be read without the emulator; scripts/emu_modulation.py's `ours` scenario
is the behavioural evidence (the rows free, the line drawn, an LFO moving it)."""

from __future__ import annotations

import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOVING = ROOT / "csrc/modulation/moving.c"
MD_PAGE = ROOT / "csrc/waverider/md_page.c"
SMP_PAGE = ROOT / "csrc/sampler/smp_page.c"


def _function(text: str, head: str) -> str:
    body = text[text.index(head):]
    return body[:body.index("\n}\n")]


def _emu():
    spec = importlib.util.spec_from_file_location("emu_modulation", ROOT / "scripts/emu_modulation.py")
    emu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(emu)
    return emu


def test_one_line_drawer_every_page_goes_through():
    mv = MOVING.read_text()
    # (2026-11-20) the one drawer is mv_place: a record's knob (mv_knob) and our own pages' (mv_own_knob, the inserts)
    place = _function(mv, "static void mv_place(void *canvas, int x, int y, int w, u32 id, u32 slot, int lo, int hi, "
                          "int centre)\n{")
    assert mv.count("SET_PIXEL(canvas") == 1 and "SET_PIXEL(canvas" in place
    assert "mv_place(canvas, x, y, w, id, slot, lo, hi," in _function(mv, "void mv_knob(")
    assert "mv_place(canvas, x, y, w, key, slot, 0, 0x7F00, 0);" in _function(mv, "void mv_own_knob(")
    span = _function(mv, "void mv_cell_span(")
    assert "mv_knob(canvas, x0 + MV_DX, y0 + MV_DY, MV_W, id, lo, hi);" in span
    cell = _function(mv, "void mv_cell(")
    assert "mv_cell_span(canvas, x0, y0, id, r[2], r[3]);" in cell     # stock's cells: the record's range
    assert "c->lo = lo;" in place and "c->hi = hi;" in place and "c->w = " in place
    assert "(c->w - 1) / (hi - lo)" in _function(mv, "static int line_at(")   # the poll redraws by the same rule


def test_machinedrum_and_monomachine_cells_ask_for_the_line_before_they_are_lit():
    md = MD_PAGE.read_text()
    perc = _function(md, "int md_page_draw(")
    assert perc.index("wg_knob(c, s, knob(view, id));") < perc.index("mv_cell(c, x0, base, id);") \
        < perc.index("wg_lit(c, s);")                                # inverted with the cell when p-locked
    mnm = _function(md, "int mnm_page_draw(")
    assert mnm.index("wg_knob(c, s, k);") < mnm.index("mv_cell_span(c, wg_x(s), wg_y(s), mnm_rid[j],") \
        < mnm.index("wg_lit(c, s);")
    # the Monomachine knob spans lo..lo + top of the record (mnm_k), so the line does too
    assert "(GET_VALUE(view, mnm_rid[j], &flag) >> 8) - mnm_lo[j]" in _function(md, "static int mnm_k(")
    assert "mnm_lo[j] << 8, (mnm_lo[j] + mnm_top[j]) << 8);" in mnm
    # PERC's knob spans the whole record (knob()), as mv_cell's line does
    assert "int lo = r[2] >> 8, top = (r[3] >> 8) - lo;" in _function(md, "static int knob(")


def test_sample_cells_put_the_line_between_the_widget_and_its_label():
    smp = SMP_PAGE.read_text()
    m = re.search(r"#define MV_LINE\(c, x, y, id\) mv_knob\(\(c\), \(x\) \+ (\d+), \(y\) - (\d+), (\d+), \(id\), "
                  r"RECORD\(id\)\[2\], RECORD\(id\)\[3\]\)", smp)
    assert m, "smp_page.c's MV_LINE"
    dx, dy, w = (int(g) for g in m.groups())
    assert dx + (w - 1) // 2 == 12                    # centred on the widget's centre, x + 12
    cell = _function(smp, "static void cell(")
    assert 'LABEL(c, x + 12, y - 7, "%.4s", label);' in cell     # the label: y - 7 .. y - 3 (5 rows)
    assert -7 + 5 <= -dy < 0                          # the row between the label's top and the widget (from y)
    assert cell.index("MV_LINE(c, x, y, id);") < cell.index("invert(c, x - 1, y - 8, x + 24, y + 19);")
    assert "MV_LINE(c, x, y, ids[i]);" in _function(smp, "void smp_knob_page(")


def test_the_emulator_check_covers_every_page_of_ours_and_the_gate_runs_it():
    emu = _emu()
    names = [n for n, _ in emu.OURS]
    assert names == ["MACHINEDRUM", "SOPHIE", "PLAITS", "TB303", "DRONE", "ANALOG2", "MONOMACHINE", "ONESHOT", "SLICE",
                     "JUNO"]                         # 2026-11-13: + JUNO (the moving lines' ours scenario)
    types = dict(emu.OURS)
    from dnfw.perc import program as PP
    from dnfw.sampler import machines as SM
    assert types["MACHINEDRUM"] == PP.MACHINE_TYPE
    assert types["ONESHOT"] == SM.TYPE_OF["ONESHOT"] and types["SLICE"] == SM.TYPE_OF["SLICE"]
    assert set(emu.LFO_ON) == {"MACHINEDRUM", "MONOMACHINE"}
    src = (ROOT / "scripts/emu_modulation.py").read_text()
    assert 'default="lists,cascade,line,ours,locks,cost"' in src     # the gate's modulation step runs it (+ locks:
                                                                     # 53235ca2, 2026-11-21, emu_modlocks.py)
    assert '"--scenario"' not in (ROOT / "scripts/ship_gate.py").read_text().split('mo_cmd = [')[1].split("\n")[0]


def test_the_checks_can_find_the_drawer():
    for path in ("src/dnfw/waverider/cpage.py", "src/dnfw/waverider/coldfire.py"):
        text = (ROOT / path).read_text()
        assert '"mv_cell_span", "mv_knob"' in text, path
