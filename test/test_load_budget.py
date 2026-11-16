"""VOICE BUDGET (csrc/load, docs/load-budget.md): the note-on hook, the generated cost table, the setting.

The behaviour is held by the emulator check (scripts/emu_load_budget.py, stock's own allocator); these hold the
pieces it relies on."""

from __future__ import annotations

import json
import pathlib
import re

from dnfw import load as LD
from dnfw.waverider import coldfire as CF

ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE = json.loads((ROOT / "src/dnfw/mods/waverider_code.json").read_text())
HOOKS = (ROOT / "csrc/load/hooks.S").read_text()
LOAD_C = (ROOT / "csrc/load/load.c").read_text()
LIVE_C = (ROOT / "csrc/msel/live.c").read_text()


def _body(label: str) -> list[str]:
    m = re.search(rf"^{label}:\n(.*?)(?=^\s+\.globl|\Z)", HOOKS, re.M | re.S)
    assert m, label
    return [" ".join(line.split("|")[0].split()) for line in m.group(1).splitlines() if line.split("|")[0].strip()]


def test_the_note_on_hook_replaces_only_the_allocators_call():
    found = [e for e in CODE["edits"] if e["va"] == CF.LOAD_ALLOC_SITE]
    assert len(found) == 1
    e = found[0]
    assert e["stock"] == CF.LOAD_ALLOC_STOCK.hex() == "4eb94002a6a2"
    assert e["new"] == "4eb9" + f"{CODE['c_text_symbols']['load_alloc_hook']:08x}"


def test_the_stub_calls_stocks_allocator_and_keeps_its_two_masks():
    b = _body("load_alloc_hook")
    assert b[:4] == ["pea 4(%sp)", "jsr load_pre", "addq.l #4, %sp", "move.l (%sp)+, load_ret"]
    assert "jsr 0x4002A6A2" in b
    assert b.index("lea -8(%sp), %sp") < b.index("movem.l %d0-%d1, (%sp)") < b.index("jsr load_post")
    assert b[-4:] == ["movem.l (%sp), %d0-%d1", "addq.l #8, %sp", "move.l load_ret, -(%sp)", "rts"]


def test_stock_tracks_and_the_setting_leave_stocks_allocation_alone():
    pre = re.search(r"void load_pre\(.*?\n}\n", LOAD_C, re.S).group(0)
    assert "if (load_off || a[2] != 1u || a[0] > 15u)" in pre          # off, a note-off, no track: nothing
    assert "if (!one)" in pre                                          # a stock machine's or MIDI's note: nothing
    assert pre.index("if (sum + one * (u32)n <= LOAD_AVAIL)") < pre.index("LIVE_POOL &= held;")


def test_the_setting_is_a_personalize_row_default_on():
    assert "#define SET_BUDGET_OFF 8u" in LOAD_C                       # bit 3 (bit 2 LIVE SELECT, bit 1 REMOTE CONTROL)
    assert "return !set_flag(SET_BUDGET_OFF);" in LOAD_C
    assert "load_row(view);" in LIVE_C                                 # after LIVE SELECT's row
    assert _body("load_box")[-2:] == ["jsr load_on", "jmp 0x400979DE"]


def test_the_table_is_generated_and_fits_the_coldfires_words():
    t = LD.load()
    h = LD.c_header(t)
    assert f"#define LOAD_AVAIL {LD.OURS - LD.FIXED}u" in h
    for k in ("md", "mnm", "plaits", "sophie", "a2flt", "mono"):
        assert t[k] and all(0 < v < 65536 for v in t[k] if v), k
    assert len(t["md"]) == 34 and len(t["plaits"]) == 13 and len(t["sophie"]) == 7 and len(t["a2flt"]) == 25
    assert t["send"]["FDN8"] > t["send"]["XDLY"] > 0
