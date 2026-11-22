"""The page keys' overviews (2026-11-17, the User: "lets try them all, we can revert what we dont like"): a page key held
a second shows every track at once (csrc/inserts/ovw.c the keys, ovw_draw.c the picture). The model of each screen,
pixel for pixel; scripts/emu_overviews.py compares the emulator's screens with `render`.

One layout for all five (FX's inserts overview, dnfw.inserts.overview, came first): screen 128 x 64, row 0 the top.
The title bar rows 0..8 lit, its left text at x 2 and its right text ending at x 125, both unlit. Tracks 1-8 then
9-16: a numbers row (the active track's number lit) and each track's two rows below it, a cell 15 px wide (x .. x+14)
every 16 px, 9 rows tall:

    DOT     one dot (nothing there: OFF, no engine, no route)
    PLAIN   the text, lit, centred
    LIT     a lit box, the text unlit inside
    FRAME   an outline box, the text lit inside
    BLINK   FRAME drawn every other half second (the inserts' FULL)
    MARKS   four 2 x 5 marks at x+2, x+5, x+8, x+11, filled for a bit set (LFO1-4 with a DEST), a dot when clear
    COUNT   (a, m): a > 0 a lit box x .. x+8 with a centred in it; m > 0 the digit min(m, 9) lit at x+11; both 0 a DOT
    ICON    (2026-11-20) the FX type's 7 x 5 icon (dnfw.waverider.msel FX_ICONS) lit at x+4, r+2
    ICON_LIT a lit box, the icon unlit in it

The overviews (what each cell row holds):
    INS  (FX)   slot 1, slot 2: dnfw.inserts.overview's states
    SYN  (SYN)  the machine (LIT; FRAME when the track is muted), its engine (PLAIN; DOT none)
    FLT  (FLTR) FLT1, the filter machine (LIT), FLT2 (PLAIN): ANALOG 2's own FLT2 on an ANALOG 2 track, else a DOT
                (the DN2's FLTR 2 page is the base-width filter, no type; the User 2026-11-18: "a dot")
    LFO  (MOD)  MARKS for LFO1-4, COUNT of the track's routes (a in use, m muted)
    AMP  (AMP)  the voices sounding ("3V"; DOT none), the track's DSP share ("12%"; LIT on the busiest; DOT none)

The VOICE key's (2026-11-19, `voice_render`) has the same title bar and numbers, then THREE rows a track, 7 px apart
(rb + 6, + 13, + 20; text at + 1; a LIT or FRAME box 7 rows tall, x .. x+14; a DOT at x+7, + 3): the machine (PLAIN,
as SYN's names it; MID on a MIDI track), the mode (PAR LIT: ANALOG 2 or JUNO with PARA ON; UNI FRAME: UNISON on; MON
PLAIN: one fixed voice; PLY PLAIN; a DOT on a MIDI track), the VOICES the VOICE menu shows (DYN, or the fixed count;
a DOT on a MIDI track). The title: VOICE SETUP, and the DYN pool (the menu's "(n)": 16 less the fixed voices).
"""

from __future__ import annotations

from .inserts import overview as INS

W, H = 128, 64
DOT, PLAIN, LIT, FRAME, BLINK, MARKS, COUNT, BLANK, ICON, ICON_LIT = range(10)   # ICON*: an FX type's icon (INS)
CHARS = INS.CHARS                               # ovw_font.h's characters (the inserts' and the overviews' names)
FRAME_CYCLES = 666_667                          # the DSP's frame (dnfw.load: 666,667 cycles a block)

# the filter machines by the byte at sound+0xDF (dnfw.waverider.msel FILTER_NAMES), 3 letters (short3)
FILTER3 = {0: "MLT", 1: "LP4", 2: "EQ", 3: "CB-", 4: "LEG", 5: "CB+",
           7: "SVF", 8: "LAD", 9: "OTA", 10: "DIO", 11: "M20"}
# the machines by the byte at sound+0xDE that have no engine of their own, 3 letters (our Monomachine-style
# machines and PERC are named by page.c wr_ovw_names from MACHINE SEL's short names and their engine's choice)
MACHINE4 = {0: "FMT", 1: "WAV", 2: "FMD", 3: "SWR", 4: "MID",
            8: "ONE", 9: "WRP", 10: "STR", 11: "RPT", 12: "GRD", 13: "SLC", 17: "FLX"}


def short3(s: str) -> str:
    """a cell's text, 3 letters at most (ovw_draw.c short3): 4 letters fill the 16 px pitch and run into the next cell.
    A longer name loses its first vowel after the first letter, else (two digits at its end) its second letter, else
    its last: STRG STR, SL12 S12, FUSE FSE, SWRM SWR"""
    if len(s) <= 3:
        return s
    vowels = [i for i in range(1, len(s)) if s[i] in "AEIOU"]
    drop = vowels[0] if vowels else 1 if s[-2:].isdigit() else len(s) - 1
    return (s[:drop] + s[drop + 1:])[:3]


def glyph_bits(ch: str) -> int:
    return INS.glyph_bits(ch)


def width(s: str) -> int:
    return 4 * len(s) - 1


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


def _cell(c, x, r0, cell, blink_on):
    kind, val = cell
    if isinstance(val, str):
        val = short3(val)
    if kind == DOT:
        c[r0 + 4][x + 7] = 1
    elif kind == PLAIN:
        _text(c, x + (15 - width(val)) // 2, r0 + 2, val)
    elif kind == LIT:
        _box(c, x, r0, x + 14, r0 + 8)
        _text(c, x + (15 - width(val)) // 2, r0 + 2, val, 0)
    elif kind in (FRAME, BLINK):
        if kind == FRAME or blink_on:
            _frame(c, x, r0, x + 14, r0 + 8)
            _text(c, x + (15 - width(val)) // 2, r0 + 2, val)
    elif kind in (ICON, ICON_LIT):
        if kind == ICON_LIT:
            _box(c, x, r0, x + 14, r0 + 8)
        INS.icon(c, x + 4, r0 + 2, val, 1 if kind == ICON else 0)
    elif kind == MARKS:
        for k in range(4):
            mx = x + 2 + 3 * k
            if val >> k & 1:
                _box(c, mx, r0 + 2, mx + 1, r0 + 6)
            else:
                c[r0 + 4][mx] = 1
    elif kind == COUNT:
        a, m = val
        if a > 0:
            s = str(min(a, 99))
            _box(c, x, r0, x + 8, r0 + 8)
            _text(c, x + (9 - width(s)) // 2, r0 + 2, s, 0)
        if m > 0:
            _text(c, x + 11, r0 + 2, str(min(m, 9)))
        if a <= 0 and m <= 0:
            c[r0 + 4][x + 7] = 1


def _head(left: str, right: str, track: int):
    """the title bar's two texts and the track numbers (the active one lit): every overview's"""
    c = [[0] * W for _ in range(H)]
    _box(c, 0, 0, W - 1, 8)
    _text(c, 2, 2, left, 0)
    _text(c, 126 - width(right), 2, right, 0)
    for t in range(16):
        x, rb = 16 * (t % 8), 10 + 27 * (t // 8)
        s = str(t + 1)
        tx = x + (15 - width(s)) // 2
        if t == track:
            _box(c, x + 1, rb - 1, x + 14, rb + 5)
            _text(c, tx, rb, s, 0)
        else:
            _text(c, tx, rb, s)
    return c


def render(left: str, right: str, cells, track: int, blink_on: bool = True):
    """cells[t][j] = (kind, value) for the 16 tracks' two rows -> rows of 0/1"""
    c = _head(left, right, track)
    for t in range(16):
        for j in range(2):
            _cell(c, 16 * (t % 8), 10 + 27 * (t // 8) + 7 + 10 * j, cells[t][j], blink_on)
    return c


def _cell7(c, x, r, cell):
    """a VOICE overview cell, 7 rows from R (ovw_draw.c cell7): DOT, PLAIN, LIT or FRAME"""
    kind, val = cell
    val = short3(val)
    tx = x + (15 - width(val)) // 2
    if kind == DOT:
        c[r + 3][x + 7] = 1
    elif kind == LIT:
        _box(c, x, r, x + 14, r + 6)
        _text(c, tx, r + 1, val, 0)
    else:
        if kind == FRAME:
            _frame(c, x, r, x + 14, r + 6)
        _text(c, tx, r + 1, val)


def voice_render(left: str, right: str, cells, track: int):
    """cells[t] = three (kind, value): the machine, the mode, the VOICES -> rows of 0/1"""
    c = _head(left, right, track)
    for t in range(16):
        for j in range(3):
            _cell7(c, 16 * (t % 8), 10 + 27 * (t // 8) + 6 + 7 * j, cells[t][j])
    return c


# -- the OUTPUTS overview (2026-11-21, FUNC + [MOD] held a second; it replaced that day's MIXER overview) -----------
# The User: "I want to see what clips. So only what is not float, by definition"; "We have many more track with
# overbridge" (scratch/outputs-ovw-mock2.png). csrc/inserts/ovw_draw.c mix_view, csrc/meter/mixer.c mix_ovw_get.
MIX_TOP, MIX_PX, MIX_DB = 15, 38, 48.0
MIX_LV_ONE = 16384                              # csrc/meter/mixer.c LV_ONE: full scale in the DSP's peak units
OUT_CH = 25                                     # 0..15 tracks, 16..18 returns, 19, 20 OB / USB main, 21, 22 the analog
                                                # outputs, 23 the input, 24 the recorder
OUT_X = [1 + 4 * t for t in range(16)] + [67, 72, 77, 84, 89, 96, 101, 108, 119]
OUT_UNIT = list(range(19)) + [22, 23, 19, 20, 21, 24]      # mixer.c OV_UNIT: each bar's levels-packet unit
OUT_BIT = list(range(19)) + [19, 19, 20, 20, 21, 22]       # mixer.c OV_BIT: its clip bit
OUT_NAMES = [str(t + 1) for t in range(16)] + ["D", "R", "C", "OB", "OB", "OUT", "OUT", "IN", "REC"]
OUT_ROW54 = ((1, "1"), (29, "8"), (57, "16"), (67, "D"), (72, "R"), (77, "C"), (84, "L"), (89, "R"), (96, "L"),
             (101, "R"), (107, "IN"), (116, "REC"))


def mix_thresholds() -> list[int]:
    """csrc/meter/mixer.c OTH: a peak at the k-th or more lights k pixels (the top one full scale)"""
    return [round(MIX_LV_ONE * 10 ** (-(MIX_PX - k) * MIX_DB / MIX_PX / 20)) for k in range(1, MIX_PX + 1)]


def mix_px(peak: int) -> int:
    return sum(1 for t in mix_thresholds() if peak >= t)


def out_group(ch: int) -> int:
    """0 TRK, 1 FX, 2 OB, 3 OUT, 4 IN, 5 REC"""
    return 0 if ch < 16 else 1 if ch < 19 else 2 if ch < 21 else 3 if ch < 23 else ch - 19


def outs_title(mark, usb: bool) -> str:
    """the title's right side: CLIP and the marked outputs' names (a pair's once), "+" past 20 characters"""
    if not any(mark):
        return ""
    t = "CLIP"
    for ch in range(OUT_CH):
        if not mark[ch] or (ch in (20, 22) and mark[ch - 1]):
            continue
        m = ("USB" if usb else "OB") if ch in (19, 20) else OUT_NAMES[ch]
        if len(t) + 1 + len(m) > 20:
            t += " +"
            break
        t += " " + m
    return t


def outs_render(lit, hold, mark, live, usb: bool = False):
    """the 25 bars: pixels lit, the peak tick, the clip mark, the output in use -> rows of 0/1 (ovw_draw.c mix_view)"""
    c = [[0] * W for _ in range(H)]
    _box(c, 0, 0, W - 1, 8)
    _text(c, 2, 2, "OUTPUTS", 0)
    bot = MIX_TOP + MIX_PX - 1
    for ch in range(OUT_CH):
        x, w, n, h = OUT_X[ch], 3 if ch < 16 else 4, lit[ch], hold[ch]
        if live[ch]:
            _box(c, x, bot, x + w - 1, bot)
            if n > 0:
                _box(c, x, bot - n + 1, x + w - 1, bot)
            if h > n:
                _box(c, x, bot - h + 1, x + w - 1, bot - h + 1)
        else:
            for r in range(MIX_TOP + 1, bot + 1, 3):
                c[r][x + w // 2] = 1
        if mark[ch]:
            _box(c, x, 10, x + w - 1, 13)
    for x, t in OUT_ROW54:
        _text(c, x, 54, t)
    groups = [("TRK", 25), ("FX", 70), ("USB", 83) if usb else ("OB", 85), ("OUT", 95)]
    gm = [any(mark[ch] for ch in range(OUT_CH) if out_group(ch) == g) for g in range(4)]
    for g, (t, x) in enumerate(groups):
        if gm[g]:
            _box(c, x - 1, 58, x + width(t), 63)
        _text(c, x, 59, t, 0 if gm[g] else 1)
    t = outs_title(mark, usb)
    if t:
        _text(c, 126 - width(t), 2, t, 0)
    return c


# -- each overview's cells from its data ---------------------------------------------------------------------------

def ins_cells(states, types):
    """the inserts overview (FX) in this module's terms: the same picture as dnfw.inserts.overview.render"""
    out = []
    for t in range(16):
        row = []
        for j in range(2):
            st = states[t][j]
            row.append((DOT, "") if st == INS.OFF else (BLINK, "FUL") if st == INS.FULL
                       else (ICON_LIT, types[t][j]) if st == INS.RUNS else (ICON, types[t][j]))
        out.append(row)
    n = sum(1 for t in range(16) for j in range(2) if states[t][j] == INS.RUNS)
    return f"INSERTS {n}/32", out


def syn_cells(names, muted):
    """names[t] = (machine, engine) ("" none), muted[t] -> (left, right, cells)"""
    cells = []
    for t in range(16):
        m, e = names[t]
        top = (DOT, "") if not m else (FRAME if muted[t] else LIT, m)
        cells.append([top, (PLAIN, e) if e else (DOT, "")])
    return "MACHINES", f"MUTED {sum(1 for t in range(16) if muted[t])}", cells


def flt_cells(flt):
    """flt[t] = (FLT1, FLT2) names, ("", "") on a track with no filter (MIDI)"""
    cells = [[(LIT, a) if a else (DOT, ""), (PLAIN, b) if b else (DOT, "")] for a, b in flt]
    return "FILTERS", "", cells


def lfo_cells(marks, active, muted, pool):
    """marks[t] bits 0..3 (LFO1-4 with a DEST), active[t] / muted[t] the track's routes, pool: LFO routes used"""
    cells = [[(MARKS, marks[t]), (COUNT, (active[t], muted[t]))] for t in range(16)]
    return f"LFO POOL {pool}/256", f"MUTED {sum(muted)}", cells


def pct(cycles: int) -> int:
    """a track's DSP share in percent of the frame: rounded, at least 1 when it costs anything (ovw_draw.c pct)"""
    if cycles <= 0:
        return 0
    return max(1, (cycles * 100 + FRAME_CYCLES // 2) // FRAME_CYCLES)


def amp_cells(voices, cycles, cpu, dsp):
    """voices[t] sounding, cycles[t] the track's DSP cycles, cpu / dsp the meter's C and D in percent (-1 none)"""
    busiest = max(range(16), key=lambda t: (cycles[t], -t)) if max(cycles) > 0 else -1
    cells = []
    for t in range(16):
        v = (PLAIN, f"{min(voices[t], 16)}V") if voices[t] > 0 else (DOT, "")
        p = pct(cycles[t])
        d = (DOT, "") if p == 0 else (LIT if t == busiest else PLAIN, f"{min(p, 999)}%")
        cells.append([v, d])
    c = f"C {min(cpu, 999)}%" if cpu >= 0 else "C --"
    d = f"D {min(dsp, 999)}%" if dsp >= 0 else "D --"
    return f"VOICES {min(sum(voices), 99)}/16", f"{c} {d}", cells


MIDI_TYPE = 4


def voice_mode(mtype: int, para_on: bool, unison: bool, voices: int) -> str:
    """a track's mode as the VOICE overview names it ("" on a MIDI track or with no machine): PARA wins over UNISON
    (UNISON is ignored on a PARA track, csrc/para/led.c), one fixed voice is MON"""
    if mtype < 0 or mtype == MIDI_TYPE:
        return ""
    return "PAR" if para_on else "UNI" if unison else "MON" if voices == 1 else "PLY"


def voice_cells(names, mtypes, para_on, unison, voices, pool):
    """names[t] the machine (SYN's, "" none), mtypes[t] sound+0xDE, para_on[t], unison[t], voices[t] (VOICES: <= 0 DYN,
    else fixed), pool the DYN pool -> (left, right, cells)"""
    cells = []
    for t in range(16):
        mode = voice_mode(mtypes[t], para_on[t], unison[t], voices[t])
        top = (PLAIN, names[t]) if names[t] else (DOT, "")
        if not mode:
            cells.append([top, (DOT, ""), (DOT, "")])
            continue
        mid = (LIT if mode == "PAR" else FRAME if mode == "UNI" else PLAIN, mode)
        cells.append([top, mid, (PLAIN, "DYN" if voices[t] <= 0 else str(min(voices[t], 16)))])
    return "VOICE SETUP", f"DYN {max(0, min(pool, 16))}", cells
