"""The inserts overview (FX held 1 s; csrc/inserts/ovw.c): the model of its screen, pixel for pixel.

The ColdFire draws the same picture (ovw.c ovw_draw); test/test_ins_overview.py holds the two parts that must agree
(the letters, the names) and scripts/emu_ins_overview.py compares the emulator's screen with `render`.

Screen 128 x 64, row 0 the top. Title bar rows 0..8 lit, "INSERTS n/32" (the slots the DSP runs) at x 2 and
"DSP nn%" ("DSP --" with no reading) ending at x 125, both unlit on it. Tracks 1-8 then 9-16: a numbers row (the
active track's number lit) and each track's two slots below, a cell 16 px wide:
    a slot the DSP runs     a lit box x .. x+14, 9 rows, its icon unlit inside (x+4, row+2; 2026-11-20, the User)
    MIX 0 (sent as OFF)     the icon, lit
    FULL (no FDN8/XDLY)     an outline box and "FUL", blinking (drawn every other half second)
    OFF                     one dot
"""

from __future__ import annotations

import json
import pathlib

FONT = json.loads((pathlib.Path(__file__).resolve().parents[1] / "font3x5.json").read_text())["glyphs"]
CHARS = " %+-./0123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ"     # the overviews' names too (dnfw.overviews)
# by type number (dnfw.inserts.design NAMES; csrc/inserts/ins.c NAME): OFF FUZZ TAPE FOLD CHOR WIDE HARM FDN8 XDLY
# SUB DIST GATR RING JUNO
NAME3 = ["", "FUZ", "TAP", "FLD", "CHO", "WID", "HRM", "FDN", "XDL", "SUB", "DST", "GAT", "RNG", "JUN"]
OFF, MIX0, RUNS, FULL = 0, 1, 2, 3              # ovw.c ins_slot_state
W, H = 128, 64


def glyph_bits(ch: str) -> int:
    g = FONT[ch]
    v = 0
    for r in range(5):
        for k in range(3):
            v = v << 1 | (g[r][k] == "1")
    return v


def _text(c, x, y, s, on=1):
    for ch in s:
        bits = glyph_bits(ch if ch in CHARS else " ")
        for r in range(5):
            for k in range(3):
                if bits >> (14 - 3 * r - k) & 1 and 0 <= x + k < W and 0 <= y + r < H:
                    c[y + r][x + k] = on
        x += 4


def _box(c, x0, y0, x1, y1, on=1):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            c[y][x] = on


def _frame(c, x0, y0, x1, y1):
    for x in range(x0, x1 + 1):
        c[y0][x] = c[y1][x] = 1
    for y in range(y0, y1 + 1):
        c[y][x0] = c[y][x1] = 1


def icon(c, x, y, type_, on=1):
    """the FX type's 7 x 5 icon (dnfw.waverider.msel FX_ICONS, the one table; ovw_draw.c C_ICON), top left at X, Y"""
    from ..waverider.msel import FX_ICONS
    for r, line in enumerate(FX_ICONS.get(type_, ["......."] * 5)):
        for k, ch in enumerate(line):
            if ch == "#" and 0 <= x + k < W and 0 <= y + r < H:
                c[y + r][x + k] = on


def render(states, types, track, dsp, blink_on=True):
    """states[t][j] (OFF MIX0 RUNS FULL), types[t][j] (type numbers), track 0..15, dsp percent or -1 -> rows of 0/1"""
    c = [[0] * W for _ in range(H)]
    _box(c, 0, 0, W - 1, 8)
    n = sum(1 for t in range(16) for j in range(2) if states[t][j] == RUNS)
    _text(c, 2, 2, f"INSERTS {n}/32", 0)
    d = f"DSP {dsp}%" if dsp >= 0 else "DSP --"
    _text(c, 126 - (4 * len(d) - 1), 2, d, 0)
    for half in range(2):
        yb = 10 + 27 * half
        for i in range(8):
            t = 8 * half + i
            x = 16 * i
            s = str(t + 1)
            tx = x + (15 - (4 * len(s) - 1)) // 2
            if t == track:
                _box(c, x + 1, yb - 1, x + 14, yb + 5)
                _text(c, tx, yb, s, 0)
            else:
                _text(c, tx, yb, s)
            for j in range(2):
                y0 = yb + 7 + 10 * j
                st = states[t][j]
                if st == OFF:
                    c[y0 + 4][x + 7] = 1
                elif st == FULL:
                    if blink_on:
                        _frame(c, x, y0, x + 14, y0 + 8)
                        _text(c, x + 2, y0 + 2, "FUL")
                elif st == RUNS:
                    _box(c, x, y0, x + 14, y0 + 8)
                    icon(c, x + 4, y0 + 2, types[t][j], 0)
                else:
                    icon(c, x + 4, y0 + 2, types[t][j])
    return c
