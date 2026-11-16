"""The preset browser's ENGINE filter (csrc/presets, dnfw.waverider.engfilt): its own SORTING row after FILTER and its
own tick list (the User: "add a separate engine filter please"), MACHINE SEL's engines, MIDI left to stock's FILTER;
each OS 1.12 site jumps to its hook, which replays exactly the stock instructions the jump replaced and goes on where
stock went; stock's FILTER list is stock's again. Measured in the 1.12 emulator (2026-11-12): SORTING lists ENGINE
between FILTER and SEARCH; FM DRUM ticked lists PUNCHBASS first; a preset saved from a SOPHIE track is the only one
SOPHIE lists; + FILTER EVOL keeps it, + KICK gives NO MATCHES; FM DRUM + SOPHIE lists both; ENGINE's <CLEAR> keeps
FILTER's tags."""

from __future__ import annotations

import json
import pathlib
import re

from dnfw.waverider import coldfire as CF
from dnfw.waverider import engfilt as E
from dnfw.waverider import msel as M

ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE = json.loads((ROOT / "src/dnfw/mods/waverider_code.json").read_text())
HOOKS_S = (ROOT / "csrc/presets/hooks.S").read_text()

# site -> (stock bytes, the hook, jmp or jsr)
SITES = {
    CF.ENG_TEST_SITE: (CF.ENG_TEST_STOCK, "eng_test_hook", "4ef9"),
    CF.ENG_SORT_SITE: (CF.ENG_SORT_STOCK, "eng_sort_hook", "4ef9"),
    CF.ENG_CTOR_SITE: (CF.ENG_CTOR_STOCK, "eng_ctor_hook", "4eb9"),
}
# stock's FILTER list and <CLEAR> are stock's again (the first design's sites)
FILTER_SITES = (0x400ABAD8, 0x400A900E, 0x400A90DE)


def _edit(va: int) -> dict:
    found = [e for e in CODE["edits"] if e["va"] == va]
    assert len(found) == 1, hex(va)
    return found[0]


def _body(label: str) -> list[str]:
    """the hook's instructions, comments and blank lines dropped, up to the next global"""
    m = re.search(rf"^{label}:\n(.*?)(?=^\s+\.globl|\Z)", HOOKS_S, re.M | re.S)
    assert m, label
    return [" ".join(line.split("|")[0].split()) for line in m.group(1).splitlines() if line.split("|")[0].strip()]


def test_each_site_holds_stock_and_enters_its_hook():
    syms = CODE["c_text_symbols"]
    for va, (stock, hook, op) in SITES.items():
        e = _edit(va)
        assert e["stock"] == stock.hex()
        new = op + f"{syms[hook]:08x}" + "4e71" * ((len(stock) - 6) // 2)
        assert e["new"] == new, hex(va)


def test_the_test_hook_tests_the_engines_then_stocks_midi():
    b = _body("eng_test_hook")
    assert b[:2] == ["tst.l eng_mask", "beq.s 3f"]                           # no engine: straight to stock's test
    assert b[b.index("jsr eng_match") + 2:b.index("jsr eng_match") + 5] == ["tst.l %d0", "bne.s 3f", "jmp 0x400AC9BC"]
    assert b[-4:] == ["3: tst.b 1413(%a4)", "beq.s 2f", "jmp 0x400AC9AE", "2: jmp 0x400AC9BA"]   # stock's, as it was


def test_the_replays_go_on_after_the_site():
    sort = _body("eng_sort_hook")
    assert sort[-3:] == ["pea 4", "clr.l -56(%fp)", f"jmp 0x{CF.ENG_SORT_SITE + 8:08X}"]
    assert "jsr eng_sort_row" in sort
    assert _body("eng_ctor_hook") == ["move.b %d1, 1412(%a2)", "move.b %d1, 1413(%a2)", "clr.l eng_mask", "rts"]


def test_stocks_filter_list_is_stocks():
    for e in CODE["edits"]:
        lo, hi = e["va"], e["va"] + len(e["new"]) // 2
        assert not any(lo <= va < hi for va in FILTER_SITES), hex(e["va"])


def test_the_rows_are_machine_sels_engines_without_midi():
    types = E.engine_types()
    assert types == [t for t in M.machine_rows() if t >= 0 and t != E.MIDI]
    assert E.MIDI not in types and len(set(types)) == len(types)
    assert types[:4] == [0, 2, 1, 3]                                          # FM TONE, FM DRUM, WAVETONE, SWARMER
    names = M.machine_names()
    assert [names[t] for t in types[:4]] == ["FM TONE", "FM DRUM", "WAVETONE", "SWARMER"]
    assert all(0 <= t < 32 for t in types)                                    # one mask bit per type
    assert all(len(names[t]) <= E.LABEL_MAX for t in types)


def test_the_row_is_engine():
    assert E.TITLE == "ENGINE"
    c = (ROOT / "csrc/presets/engfilt.c").read_text()
    assert '"ENGINE  "' in c and "t[7] = eng_mask ? '*' : ' ';" in c       # FILTER's "FILTER *" (0x4028c61c +7)


def test_the_header_lists_the_rows():
    h = E.c_header()
    types = E.engine_types()
    assert f"#define ENG_N {len(types)}" in h
    assert "eng_types[ENG_N] = {" + ", ".join(map(str, types)) + "}" in h


def test_the_checks_find_the_state():
    lay = CODE["layout"]
    for name in ("eng_mask", "eng_tests", "eng_lists", "eng_n"):
        assert name in lay
    assert lay["c_data_start"] <= lay["eng_mask"] < lay["c_image_end"]       # written at run time: .data


def test_no_other_edit_touches_the_sites():
    spans = [(va, va + len(stock)) for va, (stock, _h, _o) in SITES.items()]
    for e in CODE["edits"]:
        if e["va"] in SITES:
            continue
        lo, hi = e["va"], e["va"] + len(e["new"]) // 2
        assert all(hi <= a or lo >= b for a, b in spans), hex(e["va"])
