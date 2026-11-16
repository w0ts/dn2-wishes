"""The preset browser's ENGINE filter (2026-11-12; csrc/presets: engfilt.c, hooks.S; docs/engine-filter.md).

Its own row in stock's SORTING menu (PRESET > LOAD / SAVE / MANAGE > [LEFT]), ENGINE, after FILTER: its own tick
list, as FILTER's for the tags (the User: "add a separate engine filter please"), one row per MACHINE SEL engine
after <CLEAR>. Stock's preset index already holds each preset's machine (entry +32: the stored sound's byte 244, MIDI
4), so the filter needs no extra +Drive reads. The engines are MACHINE SEL's, in its order and with its names
(dnfw.waverider.msel), MIDI left out: stock's FILTER keeps its own MIDI row.
"""
from __future__ import annotations

from . import msel as _msel

MIDI = 4                     # stock's MIDI row (view +1413) is that machine's
LABEL_MAX = 12               # "  " + name in the list's column (msel.NAME_MAX)
# measured in stock 1.12 (scratch study, the emulator): the preset browser's view and its index
V_TAGS, V_NOTAG, V_MIDI, V_MENU = 1408, 1412, 1413, 448
TITLE = "ENGINE"             # the SORTING row, FILTER's " *" after it while an engine is ticked
LIB_MACHINE = 28             # the preset library's vtable: machine(slot) -> entry +32 (0x4012d1cc), -1 if none


def engine_types() -> list[int]:
    """the engine rows' machine types, MACHINE SEL's order, no dividers, no MIDI"""
    return [t for t in _msel.machine_rows() if t >= 0 and t != MIDI]


def c_header() -> str:
    types = engine_types()
    names = _msel.machine_names()
    assert len(types) <= 32 and max(types) < 32, "the engine set is one 32-bit mask by type"
    assert all(len(names[t]) <= LABEL_MAX for t in types)
    return ("/* the preset browser's ENGINE filter (dnfw.waverider.engfilt) */\n"
            f"#define ENG_N {len(types)}\n"
            "static const unsigned char eng_types[ENG_N] = {" + ", ".join(map(str, types)) + "};\n")
