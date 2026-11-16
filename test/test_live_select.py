"""LIVE SELECT (csrc/msel/msel.c, live.c, live.S; docs/live-select.md): MACHINE SEL and the FUNC + G filter list
commit the type under a resting cursor, YES keeps it, NO puts the type and the whole sound back; its setting is a row
of SETTINGS > PERSONALIZE, kept in the mod's settings sector as a flag that turns it off (default on)."""

from __future__ import annotations

import json
import pathlib
import re

from dnfw.waverider import coldfire as CF

ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE = json.loads((ROOT / "src/dnfw/mods/waverider_code.json").read_text())
LIVE_S = (ROOT / "csrc/msel/live.S").read_text()
LIVE_C = (ROOT / "csrc/msel/live.c").read_text()
MSEL_C = (ROOT / "csrc/msel/msel.c").read_text()
JUMP_C = (ROOT / "csrc/jump/jump.c").read_text()


def _edit(va: int) -> dict:
    found = [e for e in CODE["edits"] if e["va"] == va]
    assert len(found) == 1, hex(va)
    return found[0]


def _body(label: str) -> list[str]:
    m = re.search(rf"^{label}:\n(.*?)(?=^\s+\.globl|\Z)", LIVE_S, re.M | re.S)
    assert m, label
    return [" ".join(line.split("|")[0].split()) for line in m.group(1).splitlines() if line.split("|")[0].strip()]


def test_the_personalize_row_hook():
    e = _edit(CF.LIVE_MENU_SITE)
    assert e["stock"] == CF.LIVE_MENU_STOCK.hex()
    assert e["new"] == "4ef9" + f"{CODE['c_text_symbols']['live_menu_hook']:08x}"
    # stock's epilogue, replayed whole after the row (movem.l 24(%sp) ; lea 128(%sp) ; rts)
    assert _body("live_menu_hook")[-3:] == ["movem.l 24(%sp), %d2-%d6/%a2-%a6", "lea 128(%sp), %sp", "rts"]


def test_the_box_is_stocks_with_our_value():
    b = _body("live_box")
    assert b[:6] == ["lea -12(%sp), %sp", "movem.l %d2-%d4, (%sp)", "move.l 24(%sp), %d2", "move.l 32(%sp), %d4",
                     "move.l 28(%sp), %d3", "addi.l #11, %d3"]                # 0x400979be's first instructions
    assert b[-2:] == ["jsr live_on", "jmp 0x400979DE"]                       # where stock's getter returns


def test_default_on_and_the_sector_keeps_other_flags():
    assert "return !set_flag(SET_LIVE_OFF);" in LIVE_C                       # a flag that turns it OFF
    assert "#define SET_LIVE_OFF 4u" in LIVE_C                              # bit 2: bit 1 is REMOTE CONTROL's
    assert "#define SET_OWN (SET_JUMP | SET_REMOTE_OFF)" in JUMP_C
    assert JUMP_C.count("set_bits = sector[2] & ~SET_OWN;") == 2               # read (FACTORY RESET or not): kept
    assert ("sector[2] = (set_bits & ~SET_OWN) | (jmp_on ? SET_JUMP : 0) | (set_remote ? 0 : SET_REMOTE_OFF);"
            in JUMP_C)                                                         # written back with jump's and remote's


def test_no_restores_the_whole_sound_after_the_types():
    m = re.search(r"static void ls_revert\(.*?\n}\n", MSEL_C, re.S)
    body = m.group(0)
    assert body.index("MACHINE_COMMIT(model, ls_track, ls_type, 1, 1)") < body.index("ls_copy(ls_at, ls_sound)")
    assert body.index("FILTER_COMMIT(model, ls_track, ls_filter, 1, 1)") < body.index("ls_copy(ls_at, ls_sound)")
    assert "#define SOUND_LEN   1163" in MSEL_C and "#define REST        150" in MSEL_C


def test_the_checks_find_the_state():
    lay = CODE["layout"]
    for name in ("ls_commits", "ls_reverts", "live_rows", "set_bits"):
        assert name in lay
