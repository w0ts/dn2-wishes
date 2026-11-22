"""The matrix's state (csrc/matrix/matrix.c struct mx_state) as a build lays it out, from its magic (2026-11-21).

MX_MAGIC is 'MX' << 16 | sizeof(struct mx_state). The size depends on two build switches: DN2_ROUTE8 (a route 8 bytes
in place of 12) and DN2_LFO4 (env_out's rows 40 words in place of 30). Each pair gives a different size, so the magic
says which layout a run's MX_RAM holds; the harnesses read offsets from here instead of hard-coding them.

    from emulib import mxlayout
    L = mxlayout.of_magic(m.long(MX_RAM))      # -> Layout, or ValueError for a size no build makes
    tab = MX_RAM + L.tab + L.tab_b * (2 * t + live)
"""

from __future__ import annotations

from typing import NamedTuple

SLOTS = 23
HEAD = 720                          # magic .. e2_locked, padded: tab[16][2] starts here (both switches)
ROW_B = 2 * 16 * 101                # scratch, e2row: 16 rows of 101 cells


class Layout(NamedTuple):
    entry: int                      # a route's bytes: 12, or 8 (DN2_ROUTE8)
    lfo_w: int                      # env_out's words a voice: 30, or 40 (DN2_LFO4)
    tab_b: int                      # struct mx_tab's bytes
    env2: int                       # its ENV2 knobs (7 bytes), then mute1
    e2w: int                        # its ENV2 knob cells (8 u16)
    nx1: int                        # its first routes' words (3 s32)
    tab: int                        # offsets in struct mx_state
    none: int
    env_out: int
    scratch: int
    e2row: int
    iroute: int
    size: int


def layout(entry: int, lfo_w: int) -> Layout:
    tab_b = SLOTS * entry + 8 + 16 + 12
    none = HEAD + 32 * tab_b
    env_out = none + tab_b
    scratch = env_out + 4 * 16 * lfo_w
    e2row = scratch + ROW_B
    iroute = e2row + ROW_B
    return Layout(entry, lfo_w, tab_b, SLOTS * entry, SLOTS * entry + 8, SLOTS * entry + 24, HEAD, none, env_out,
                  scratch, e2row, iroute, iroute + 32)


ALL = {lay.size: lay for lay in (layout(e, w) for e in (12, 8) for w in (30, 40))}
assert len(ALL) == 4, "every switch pair a different size"
assert layout(12, 30).env_out == 0x2B08 and layout(12, 30).nx1 == 300, "the 12-byte layout as before"


def of_size(size: int) -> Layout:
    if size not in ALL:
        raise ValueError(f"struct mx_state of {size} bytes: no layout of this tree's (known: {sorted(ALL)})")
    return ALL[size]


def of_magic(magic: int) -> Layout:
    if magic >> 16 != 0x4D58:
        raise ValueError(f"no matrix state (magic {magic:#010x})")
    return of_size(magic & 0xFFFF)
