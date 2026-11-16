"""The glass inverted while the test channel is armed (csrc/devtest/devtest.c dt_glass, dt_present; glass.S):
the two OS 1.12 entries jmp to the C, and glass.S replays exactly the stock instructions each jmp replaced
before going on where it was (2026-11-11, the User: "this way i known when you operate it")."""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE = json.loads((ROOT / "src/dnfw/mods/waverider_code.json").read_text())
GLASS_S = (ROOT / "csrc/devtest/glass.S").read_text()

# site -> (stock bytes, the C entry, the replay in glass.S)
SITES = {
    0x40131F04: ("4feffff048d7041c", "dt_glass", "dt_glass_stock"),        # the 8-byte group sender
    0x40131FD2: ("4fefffd848d71c7c", "dt_present", "dt_diff_stock"),       # panel_diff
}


def _edit(va: int) -> dict:
    found = [e for e in CODE["edits"] if e["va"] == va]
    assert len(found) == 1, hex(va)
    return found[0]


def test_each_entry_jumps_to_its_c():
    syms = CODE["c_text_symbols"]
    for va, (stock, entry, _replay) in SITES.items():
        e = _edit(va)
        assert e["stock"] == stock
        assert e["new"] == "4ef9" + f"{syms[entry]:08x}" + "4e71"     # jmp entry.l ; nop


def test_the_replays_are_the_stock_instructions_and_go_on_after_the_jmp():
    replays = {
        "dt_glass_stock": ["lea     -16(%sp), %sp", "movem.l %d2-%d4/%a2, (%sp)"],    # 4fef fff0 ; 48d7 041c
        "dt_diff_stock": ["lea     -40(%sp), %sp", "movem.l %d2-%d6/%a2-%a4, (%sp)"],  # 4fef ffd8 ; 48d7 1c7c
    }
    for va, (_stock, _entry, replay) in SITES.items():
        m = re.search(rf"^{replay}:\n((?:\s+.+\n)+?)\s+jmp\s+(0x[0-9A-F]+)", GLASS_S, re.M)
        assert m, replay
        body = [" ".join(line.split("|")[0].split()) for line in m.group(1).splitlines() if line.strip()]
        assert body == [" ".join(s.split()) for s in replays[replay]]
        assert int(m.group(2), 16) == va + 8


def test_no_other_edit_touches_the_glass_routines():
    for e in CODE["edits"]:
        lo, hi = e["va"], e["va"] + len(e["new"]) // 2
        if e["va"] in SITES:
            continue
        assert hi <= 0x40131EEC or lo >= 0x401320E8, hex(e["va"])        # 0x40131eec..panel_diff's clear
