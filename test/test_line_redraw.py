"""The moving controls' lines updated alone (csrc/modulation/moving.c mv_lines_only, 2026-11-17): the facts the C and
its emulator check (scripts/emu_line_redraw.py) must agree on. The behaviour (the glass always as a full redraw) is the
gate's lineonly step."""

import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
MV = (ROOT / "csrc/modulation/moving.c").read_text()
PAGE = (ROOT / "csrc/waverider/page.c").read_text()


def _emu():
    spec = importlib.util.spec_from_file_location("emu_line_redraw", ROOT / "scripts/emu_line_redraw.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _function(text, head):
    i = text.index(head)
    return text[i:text.index("\n}\n", i)]


def test_the_checks_read_the_state_where_the_c_asserts_it():
    emu = _emu()
    size = int(re.search(r"sizeof\(struct mv_cell\) == (\d+)", MV).group(1))
    drawn = int(re.search(r"offsetof\(struct mv_cell, drawn\) == (\d+)", MV).group(1))
    clean = int(re.search(r"offsetof\(struct mv_cell, clean\) == (\d+)", MV).group(1))
    parts = int(re.search(r"offsetof\(struct mv_state, parts\) == (\d+)", MV).group(1))
    back = int(re.search(r"offsetof\(struct mv_state, back\) == (\d+)", MV).group(1))
    assert (emu.CELL, emu.C_DRAWN, emu.C_CLEAN, emu.O_PARTS, emu.O_BACK) == (size, drawn, clean, parts, back)
    assert emu.O_CELLS + emu.NCELL * emu.CELL == emu.O_PARTS                  # parts follows the cells
    assert emu.MV_MAGIC == int(re.search(r"#define MV_MAGIC (0x[0-9A-F]+)u", MV).group(1), 16)
    assert re.search(r"#define NCELL\s+16\b", MV)


def test_the_lines_go_through_stocks_own_sender_into_back_only():
    assert "#define FB_BACK   (*(u8 *volatile *)0x402A10CCu)" in MV
    assert "0x40131F04u" in MV and "0x40131EECu" in MV                      # stock's group sender, the 0xB8 show
    assert "FB_FRONT" not in MV and "0x402A10C8" not in MV                  # never the buffer being drawn
    alone = _function(MV, "static void mv_lines_only(")
    assert "GLASS_GROUP(col, page, bytes);" in alone and alone.count("GLASS_SHOW();") == 1
    poll = _function(MV, "void mv_poll(")
    # BACK as the frame drawn, no redraw due, or one held back while a knob turns (2026-11-18: page.c wr_redraw_held)
    assert "FB_BACK == MV->back && (!IS_DIRTY(screen) || wr_redraw_held())" in poll
    assert "alone &= c->clean;" in poll and "SET_DIRTY(screen);" in poll    # any cell not clean: the full redraw
    assert "#define IS_DIRTY  ((u8 (*)(void *))0x4011D5D4u)" in MV         # move.b: only %d0's low byte


def test_every_full_draw_ends_by_judging_the_cells():
    screen = PAGE[PAGE.index("void wr_screen("):PAGE.index("int wr_poll(")]
    assert screen.count("mv_end(canvas, drew);") == 2                       # the NAME screen's early return, the end
    assert screen.index("int drew = (IS_DIRTY(screen) & 0xFF) != 0;") < screen.index("SCREEN_DRAW(screen, canvas);")
    tail = screen[screen.rindex("mtr_draw(canvas);"):]
    assert tail.index("ovw_draw(canvas)") < tail.index("mv_end(canvas, drew);")   # after everything of ours
    early = screen[screen.index("if (sn_up()) {"):]
    assert early.index("mv_end(canvas, drew);") < early.index("return;")


def test_the_gate_runs_it():
    gate = (ROOT / "scripts/ship_gate.py").read_text()
    assert '("lineonly", "moving lines updated alone: the glass always as a full redraw (ColdFire)")' in gate
    assert '"scripts/emu_line_redraw.py"' in gate and '"test/test_line_redraw.py"' in gate
    assert gate.index('("modulation", ') < gate.index('("lineonly", ')
