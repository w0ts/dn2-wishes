"""Modulation (docs/modulation-more.md, owner 2026-11-11: "Open 13 closed controls, Moving controls,
Feedback is okay for lfo"): what can be read without the emulator. scripts/emu_modulation.py is
the behavioural evidence (the lists the builder makes, the cascade heard, the line drawn)."""

from __future__ import annotations

import pathlib
import re
import struct

from dnfw.mods import moddest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "csrc/waverider/page.c"

# the 13 records stock 1.12 ships with mask 0: record id -> (group, slot), read from the 1.12
# record table (0x401f83a4 + 60 id: +0 group, +4 slot, +0x24 mask 0) on 2026-11-11
CLOSED_112 = {34: (14, 93), 35: (14, 94), 61: (11, 80), 73: (11, 91), 74: (11, 92),
              221: (0, 44), 222: (0, 45), 224: (0, 47), 225: (0, 48), 226: (0, 33),
              235: (0, 62), 236: (0, 63), 237: (0, 64)}


def _opened() -> list[int]:
    m = re.search(r"wr_opened\[\] = \{([^}]*)\}", PAGE.read_text())
    assert m, "page.c's wr_opened"
    return [int(x) for x in m.group(1).split(",")]


def test_the_opened_records_are_the_thirteen_closed_ones():
    assert sorted(_opened()) == sorted(CLOSED_112)


def test_they_are_moddests_thirteen_measured_on_the_unit():
    # moddest (1.11, on the unit 2026-09-12: all 13 listed and modulated) names them by (group, slot)
    assert {gs for gs in CLOSED_112.values()} == {(g, s) for g, s, _ in moddest.TARGETS}


def test_they_open_with_an_ordinary_parameters_mask():
    assert re.search(r"#define WR_OPEN_MASK 0x1E00u", PAGE.read_text())
    assert moddest.OPEN == 0x1E00


# --- LFOs on the LFOs above them (csrc/modulation/cascade.c, hooks.S) ----------------------------
def _spec():
    from dnfw.mods import waverider
    return waverider.SPEC


def _edit(va):
    return next(e for e in _spec()["edits"] if e["va"] == va)


def _chunk(va: int, n: int) -> bytes:
    c = _spec()["c_chunk"]
    code = bytes.fromhex(c["code"])
    assert c["load"] <= va and va + n <= c["load"] + len(code), f"{va:#x} is not in the C chunk"
    return code[va - c["load"]:va - c["load"] + n]


def _halfrate_args() -> bytes:
    """DN2_LFO_HALFRATE (2026-11-19): mod_eval hands the evaluator's argument copies to lh_args first (pea (%sp) ;
    jsr lh_args ; addq.l #4,%sp); without it, nothing"""
    from dnfw.waverider import pages
    if not pages.lfo_halfrate_on():
        return b""
    return (bytes.fromhex("48574eb9") + struct.pack(">I", _spec()["c_text_symbols"]["lh_args"]) + bytes.fromhex("588f"))


def test_the_frames_evaluator_call_goes_through_the_pre_pass_into_stocks_then_the_matrix():
    from dnfw.waverider import coldfire as CF
    e = _edit(CF.MOD_EVAL_SITE)
    assert bytes.fromhex(e["stock"]) == CF.MOD_EVAL_STOCK == bytes.fromhex("4eb940137a06")
    new = bytes.fromhex(e["new"])
    lay = _spec()["layout"]
    assert new == bytes.fromhex("4eb9") + struct.pack(">I", lay["mod_eval"])
    want = (bytes.fromhex("4eb9") + struct.pack(">I", lay["mod_eval_pre"])
            + bytes.fromhex("4fefffe4")                                # lea -28(%sp),%sp
            + bytes.fromhex("2eaf0020")                                # move.l 32(%sp),(%sp): the first argument again
            + b"".join(bytes.fromhex("2f6f") + struct.pack(">HH", 32 + 4 * k, 4 * k) for k in range(1, 7))
            + _halfrate_args()                                         # (DN2_LFO_HALFRATE: lh_args on the copies)
            + bytes.fromhex("4eb940137a06")                            # stock's evaluator, the seven arguments in place
            + bytes.fromhex("4eb9") + struct.pack(">I", lay["mx_eval"])   # then the matrix (csrc/matrix), B still first
            + bytes.fromhex("4eb9") + struct.pack(">I", lay["smp_lfo_fix"])   # v0.65.1: each sample voice's SAMP keeps its bank
            + bytes.fromhex("4fef001c4e75"))                           # lea 28(%sp),%sp ; rts
    assert _chunk(lay["mod_eval"], len(want)) == want


# hooks.S mod_wb with DN2_LFO4 (2026-11-14, docs/lfo-112-port.md 4.4): DEST 101..108 (LFO4's controls) go to
# mod_wb_cell, past 108 to stock's write, 100 or under on as before. 14 bytes after the first instruction:
LFO4_WB = bytes.fromhex("7264"        # moveq #100,%d1
                        "b287"        # cmp.l %d7,%d1
                        "6408"        # bcc.s 2f: 100 or under, as without lfo4 (+8 = offset 18, the 9..24 test)
                        "726c"        # moveq #108,%d1
                        "b287"        # cmp.l %d7,%d1
                        "6538"        # bcs.s 1f: past 108, stock's write (+0x38 = offset 72, the replayed pair)
                        "6018")       # bra.s 3f: 101..108, mod_wb_cell (+0x18 = offset 42, its argument pushes)


def _lfo4_in_spec() -> bool:
    """the generated waverider spec carries DN2_LFO4's side: the evaluator's DEST bound raised to 108"""
    from dnfw.waverider import coldfire as CF
    hit = [e for e in _spec()["edits"] if e["va"] == CF.EVAL_DEST_BOUND]
    assert len(hit) <= 1
    return bool(hit) and bytes.fromhex(hit[0]["new"]) == bytes.fromhex("726c")


def test_the_evaluators_write_keeps_its_two_instructions():
    from dnfw.waverider import coldfire as CF
    e = _edit(CF.MOD_WB_SITE)
    assert bytes.fromhex(e["stock"]) == CF.MOD_WB_STOCK == bytes.fromhex("206f0034736c0052")
    lay = _spec()["layout"]
    assert bytes.fromhex(e["new"]) == bytes.fromhex("4eb9") + struct.pack(">I", lay["mod_wb"]) + bytes.fromhex("4e71")
    stub = _chunk(lay["mod_wb"], 80)
    # 2026-11-17: the DEST's kind from a table (csrc/modulation/hooks.S): past 127 stock's write, else one read
    assert stub[:8] == bytes.fromhex("0c870000007f6200")[:7] + stub[7:8]   # cmpi.l #127,%d7 ; bhi.s past the table
    assert stub[8:10] == bytes.fromhex("41f9")                              # lea mod_wb_kind,%a0
    assert stub[14:18] == bytes.fromhex("12307800")                         # move.b (%a0,%d7.l),%d1
    assert stub[18:22] == bytes.fromhex("206f0038")                         # movea.l 56(%sp),%a0: stock's 52(%sp)
    assert bytes.fromhex("736c00524e75") in stub                            # mvs.w 82(%a4),%d1 ; rts: replayed
    assert bytes.fromhex("4eb9") + struct.pack(">I", lay["mod_wb_cell"]) in stub


def test_the_dest_kinds_are_the_old_tests():
    """the table gives every DEST 0..127 the path the five compares gave it: 9..24 an LFO's control (-1), 101..108
    LFO4's (1, DN2_LFO4), every other one stock's write (0)"""
    lay = _spec()["layout"]
    stub = _chunk(lay["mod_wb"], 16)
    table = _chunk(struct.unpack(">I", stub[10:14])[0], 128)
    lfo4 = _lfo4_in_spec()
    want = [(-1 if 9 <= d <= 24 else 1 if lfo4 and 101 <= d <= 108 else 0) & 0xFF for d in range(128)]
    assert list(table) == want


def test_the_cascade_state_lives_in_its_own_ram_block():
    from dnfw.mods import waverider
    from dnfw.waverider import pages as PG
    assert PG.MDUI_LOAD + 0x8000 <= PG.MOD_RAM and PG.MOD_RAM + PG.MOD_BYTES <= PG.METER_RAM
    assert PG.MOD_CASCADE_BYTES < PG.MOD_BYTES
    assert any(x.start == PG.MOD_RAM and x.length == PG.MOD_BYTES for x in waverider.ram())


def _lfo_of(rec: int) -> int:
    """cascade.c lfo_of, as written there"""
    if rec < 75 or rec > 104:
        return 0
    k, f = divmod(rec - 75, 10)
    return 0 if f in (3, 5) else k + 1


def test_lfo_of_names_the_seven_controls_of_each_lfo_never_dest_or_slew():
    text = (ROOT / "csrc/modulation/cascade.c").read_text()
    assert "if (f == 3u || f == 5u)" in text and "(rec - 75u) / 10u" in text
    for k, ids in {1: (75, 76, 77, 79, 81, 82, 83, 84), 2: (85, 86, 87, 89, 91, 92, 93, 94),
                   3: (95, 96, 97, 99, 101, 102, 103, 104)}.items():
        assert all(_lfo_of(i) == k for i in ids)
    assert [_lfo_of(i) for i in (78, 88, 98, 80, 90, 100, 74, 105)] == [0] * 8


# --- controls that move (csrc/modulation/moving.c) ---------------------------------------------
def _define(text: str, name: str) -> int:
    m = re.search(rf"#define {name}\s+(0x[0-9A-Fa-f]+|\d+)u?", text)
    assert m, name
    return int(m.group(1), 0)


def test_the_line_row_is_the_one_the_emulator_found_free_and_checks():
    import importlib.util
    mv = (ROOT / "csrc/modulation/moving.c").read_text()
    spec = importlib.util.spec_from_file_location("emu_modulation", ROOT / "scripts/emu_modulation.py")
    emu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(emu)
    assert _define(mv, "MV_DY") == emu.MV_DY_DEFAULT == 5
    assert _define(mv, "MV_W") == 21 and _define(mv, "MV_DX") == 1   # inside a 26 px column (x0 24, 50, 76, 102)
    assert _define(mv, "LINGER") == 600 and _define(mv, "REDRAW") == 60   # 400 ms; 25 a second at 1,500 frames


def test_the_page_draw_keeps_the_cells_and_the_poll_asks_for_redraws():
    page = PAGE.read_text()
    screen = page[page.index("void wr_screen("):page.index("int wr_poll(")]
    assert screen.index("mv_begin();") < screen.index("SCREEN_DRAW(screen, canvas);")
    poll = page[page.index("int wr_poll("):page.index("return (int)mix_dirty(dirty);")]   # (2026-11-18: the turns' hold before it; 2026-11-20: the MIXER's held redraws last)
    assert "mv_poll(screen);" in poll
    cell = page[page.index("void wr_cell("):]
    cell = cell[:cell.index("\n}\n")]
    assert cell.rstrip().endswith("mv_cell(canvas, x0, y0, id);                /* moving controls: the heard value's line (csrc/modulation) */")


def test_heard_and_set_are_read_where_the_frame_writes_them():
    mv = (ROOT / "csrc/modulation/moving.c").read_text()
    slides = (ROOT / "csrc/slides/slide.c").read_text()
    for name, va in (("OUT", "0x800068E4u"), ("STATE", "0x8000DE60u"), ("OWNER", "0x80005308u")):
        assert re.search(rf"#define {name}\s+\(\(volatile u(16|32) \*\){va}\)", mv), name
        assert va in slides                                   # the same arrays slides moves
    assert "17u + 101u * (u32)(v) + (u32)(s)" in mv and "17u + 101u * (u32)(v) + (u32)(s)" in slides


def test_dn2_lfo_halfrate_is_on_unless_turned_off(monkeypatch):
    # 2026-11-19 (the User ran the half-rate build on the DN2 and kept it): on by default, DN2_LFO_HALFRATE=0 turns it off
    from dnfw.waverider import pages
    monkeypatch.delenv("DN2_LFO_HALFRATE", raising=False)
    assert pages.lfo_halfrate_on()
    monkeypatch.setenv("DN2_LFO_HALFRATE", "0")
    assert not pages.lfo_halfrate_on()
    cpage = (ROOT / "src/dnfw/waverider/cpage.py").read_text()
    assert 'if PG.lfo_halfrate_on():\n            defines["DN2_LFO_HALFRATE"] = 1' in cpage
