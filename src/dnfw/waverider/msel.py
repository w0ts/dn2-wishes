"""MACHINE SEL in two columns (2026-11-11, the User's design E; csrc/msel/msel.c draws it over stock's view).

The rows are the ones stock's MachineListView builds (row builder 0x4005b2c0), made here from the same
lists: the machine page from coldfire.LIST_NEW with a divider wherever coldfire's group(type) changes (as
0x40059274 rewritten tells stock), the filter page from a2f.coldfire's FLTR list (stock draws no divider
there). The emulator test walks the cursor over every row and holds these tables to stock's count. Each
type has a name (12 characters at most: two 61-pixel columns, the list's own 3 x 5 font) and a 7 x 5 icon.
"""
from __future__ import annotations

# the names, at most 12 characters (the User, 2026-11-11, mock-up E4: each of ours by what it is, "ANALOG everywhere";
# "drone and tb303 are not monomachine!"; one MONOMACHINE entry, its engine chosen inside it, as MACHINEDRUM's: since
# 2026-11-11 the five Monomachine ports are that one machine on type 6, OUR_NAMES below; 7, 14, 15, 16 are reserved,
# never listed). Elektron's machines and the sample machines keep stock's names. PERC is the Machinedrum's machines
# (its own type 5)
MACHINE_NAMES = {0: "FM TONE", 1: "WAVETONE", 2: "FM DRUM", 3: "SWARMER", 4: "MIDI",
                 5: "MACHINEDRUM",
                 6: "SID 6581", 7: "DPRO-WAVE", 14: "DPRO-DDRW", 15: "DPRO-DENS", 16: "VO-6 VOICE",
                 8: "ONESHOT", 9: "WERP", 10: "STRETCH", 11: "REPITCH", 12: "GRID", 13: "SLICE", 17: "BOUNCE"}
# our other Monomachine-style machines by their module's NAME (dnfw.mnm.machines), whatever type they get: SOPHIE is
# Schwung Sophie, PLAITS Mutable's Plaits, TB303 Open303, DRONE and ANALOG2 Optimist's; MONOMACHINE the five ports
# as one machine (2026-11-11, dnfw.mnm.machines MONO_NAME, on type 6: _ours)
OUR_NAMES = {"SOPHIE": "SOPHIE", "PLAITS": "PLAITS", "TB303": "TB-303", "DRONE": "DRONE", "ANALOG2": "ANALOG",
             "JUNO": "JUNO", "MONOMACHINE": "MONOMACHINE", "DRUM": "DRUM",
             "FM+STAT": "FM+ STAT", "FM+PAR": "FM+ PAR", "FM+DYN": "FM+ DYN"}     # v0.59 (upstream's FM+, types 18..20)
FILTER_NAMES = {0: "MULTI-MODE", 1: "LOWPASS 4", 2: "EQUALIZER", 3: "COMB -", 4: "LEGACY LP/HP", 5: "COMB +",
                7: "ANALOG SVF", 8: "ANALOG LADR", 9: "ANALOG OTA", 10: "ANALOG DIODE", 11: "ANALOG MS-20"}
# the icons, 7 x 5, rows top to bottom (scratch/lists/mock_e.py, the mock-up the User approved)
MACHINE_ICONS = {
    0: [".#.....", "#.#....", "...#...", "....#.#", ".....#."],      # FM TONE: a sine
    1: ["#..#..#", "##.##.#", "#.#.#.#", "#..#..#", "#..#..#"],      # WAVETONE: a saw table
    2: ["#......", "##.....", "#.#....", "#..##..", "#....##"],      # FM DRUM: a decay
    3: ["#.#.#.#", ".#.#.#.", "#.#.#.#", ".#.#.#.", "#.#.#.#"],      # SWARMER: a swarm
    4: [".#####.", "#.#.#.#", "#.....#", "#..#..#", ".#####."],      # MIDI: the DIN socket
    5: [".#####.", "#.....#", "#######", "#.....#", ".#####."],      # PERC: a drum
    6: ["#.#.#.#", "#######", "#.....#", "#######", "#.#.#.#"],      # SID 6581: the chip, its pins
    7: ["###.###", "#.#.#..", "#.#.#..", "#.#.#..", "#.###.."],      # DPRO-WAVE: a pulse
    14: ["....##.", "...#.#.", "..#.#..", ".#.#...", "##....."],     # DPRO-DDRW: a pencil's stroke
    15: ["##.#.##", ".##.##.", "##.#.##", ".##.##.", "##.#.##"],     # DPRO-DENS: dense
    16: ["..###..", "..###..", "..###..", "#.###.#", ".#####."],     # VO-6: a microphone
    8: ["#......", "##.....", "###....", "##.....", "#......"],      # ONESHOT: play once
    9: ["#...#..", ".#.#.#.", "..#...#", "...#...", "....#.."],      # WERP: a warp
    10: ["..#.#..", ".#...#.", "#######", ".#...#.", "..#.#.."],     # STRETCH: <->
    11: ["...#...", "..###..", ".#.#.#.", "...#...", "...#..."],     # REPITCH: pitch up
    12: ["#######", "#..#..#", "#######", "#..#..#", "#######"],     # GRID: a grid
    13: ["#.#.#.#", "#.#.#.#", "#.#.#.#", "#.#.#.#", "#.#.#.#"],     # SLICE: cuts
    17: ["#.....#", ".#...#.", "..#.#..", ".#...#.", "#.....#"],     # BOUNCE (when listed)
}
OUR_ICONS = {
    "SOPHIE": ["...#...", "..#.#..", ".#...#.", "#.....#", "###.###"],      # a ping
    "PLAITS": ["#...#..", ".#.#.#.", "..#...#", ".#.#.#.", "#...#.."],      # a braid
    "TB303": [".#...#.", ".......", "#.....#", ".#...#.", "..###.."],       # the acid smiley
    "DRONE": ["#######", ".......", "#######", ".......", "#######"],       # held tones
    "ANALOG2": ["...#..#", "..##.##", ".#.#.#.", "#..##..", "...#..."],     # two saws
    "JUNO": ["#.##.##", "#.##.##", "#######", "#.#.#.#", "#######"],        # the Juno's keys
    "MONOMACHINE": ["#######", "#.#.#.#", "#.#.#.#", "#.....#", "#######"],  # a keyboard
    "DRUM": ["..###..", ".#...#.", "#.#.#.#", ".#...#.", "..###.."],        # a drum seen from above, two sticks
    # v0.59 FM+: sines, one over the other (STAT: two operators), side by side (PAR: three), a sine over a decay (DYN)
    "FM+STAT": [".#.....", "#.#.#.#", "....#..", ".#.....", "#.#.#.#"],
    "FM+PAR": ["#..#..#", "#..#..#", ".......", "#######", "...#..."],
    "FM+DYN": [".#.....", "#.#.#.#", "....#..", "#......", ".######"],
}


def _ours() -> dict[int, str]:
    """type -> our module's NAME, for those of this build's Monomachine-style machines OUR_NAMES names"""
    from ..mnm import machines as MM
    out = {t: M.NAME for M, t in zip(MM.ALL_MODULES, MM.ALL_TYPE_SLOTS) if M.NAME in OUR_NAMES}
    if MM.MONO_ENGINES:                          # 2026-11-11: the five ports are one machine (dnfw.mnm.machines)
        out[MM.MONO_TYPE] = MM.MONO_NAME
    return out


def machine_names() -> dict[int, str]:
    return {**MACHINE_NAMES, **{t: OUR_NAMES[n] for t, n in _ours().items()}}


# v0.68.1 (the User, 2026-11-22: upstream v0.68's MACHINE SEL icons, "A"): upstream's machines take the owner's icon
# sheet (dnfw.msicons, drawn there at up to 34 x 22 for stock's left pane, which our two columns cover) brought down to
# our 7 x 5 cells; the types are msicons.TYPE_ICON's. Ours (JUNO .. PLAITS, DRUM) and the stock machines keep theirs;
# MONOMACHINE (type 6: our one machine for the five Monomachine ports, upstream's SID) takes the owner's SID icon
# (the User, 2026-11-22)
OWNER_ICONS = {
    "PERC": ["......#", ".....#.", ".#####.", "#.....#", "#######"],      # a stick on a drum
    "WAVE": [".##....", "#..#...", "#######", "...#..#", "....##."],      # a sine over its axis
    "DDRW": [".#.....", "#.#..#.", "...##.#", ".#....#", "#.#...."],      # strokes drawn by hand
    "DENS": ["#.#..#.", "###.#..", "####..#", "#####.#", "#######"],      # dense at the left, dots to the right
    "VO-6": [".###...", "#...###", ".###...", "#...###", ".###..."],      # voices, one over the other
    "STAT": ["#.##.#.", ".#..#.#", "##.#..#", "..#.##.", "#.#..##"],      # static
    "PAR": ["...#...", "..###..", ".#.#.#.", "#..#..#", "...#..."],       # operators fanning out
    "DYN": [".#...#.", "#.#.#.#", "#..#..#", "#.#.#.#", ".#...#."],       # a loop through itself
    "SID": ["#.#.#.#", "#######", "#.###.#", "#######", "#.#.#.#"],       # the chip, its pins, its die
    "DT2": [".#.....", "###....", "#######", "###....", ".#....."],       # the sample machines' sign
    "FLEX": ["..#####", "..#...#", "#####.#", "#...###", "#####.."],      # takes, one behind the other
}
OWNER_KEEP: set[int] = set()                     # types upstream draws whose cell keeps ours (none)


def owner_icons() -> dict[int, list[str]]:
    """type -> the owner's 7 x 5 icon, for upstream's machines (dnfw.msicons.TYPE_ICON) but OWNER_KEEP"""
    from .. import msicons
    return {t: OWNER_ICONS[n] for t, n in msicons.TYPE_ICON.items() if t not in OWNER_KEEP}


def machine_icons() -> dict[int, list[str]]:
    return {**MACHINE_ICONS, **{t: OUR_ICONS[n] for t, n in _ours().items()}, **owner_icons()}


FILTER_ICONS = {
    0: ["##....#", "..#..#.", "...##..", "..#..#.", "##....#"],      # MULTI-MODE
    1: ["####...", "....#..", ".....#.", "......#", "......#"],      # LOWPASS 4
    4: ["###....", "...#...", "....#..", ".....#.", "......#"],      # LEGACY LP/HP
    3: ["#.#.#.#", "#.#.#.#", "#.#.#.#", ".#.#.#.", ".#.#.#."],      # COMB -
    5: [".#.#.#.", ".#.#.#.", "#.#.#.#", "#.#.#.#", "#.#.#.#"],      # COMB +
    2: ["...#...", "..#.#..", "##...##", ".......", "......."],      # EQUALIZER
    7: ["..#....", ".#.#...", "#...##.", "......#", "......#"],      # A2 SVF
    8: ["###....", "#..#...", "#...#..", "#....#.", "#.....#"],      # A2 LADDER
    9: ["####...", "....#..", ".....#.", "......#", "......."],      # A2 OTA
    10: ["...#...", "..##...", "#####..", "..##...", "...#..."],     # A2 DIODE
    11: ["..#....", ".#.#...", "#...#..", ".....#.", "......#"],     # A2 MS-20
}
# INSERT SEL (2026-11-20, the User: "same code/ui as filter and synth engine"): the per-track inserts' types by type
# number (dnfw.inserts.design; the names csrc/inserts/ins.c NAME shows on the page's M.SEL), listed OFF first, then
# A-Z (ins.c ORDER), each with its icon. ONE table for the icons: INSERT SEL, the INSERT page's M.SEL box and the
# FX overview (csrc/inserts/ovw_draw.c, dnfw.inserts.overview) all draw these (msel.c msel_fx_icon). The drawings
# follow the machine icons' rule (scratch/fxicons/icons_v2.py: gear -> its look, a word -> the word, else the scope)
# and wait for the User's OK: a redraw is a change of this table alone.
FX_NAMES = {0: "OFF", 1: "FUZZ", 2: "TAPE", 3: "FOLD", 4: "CHOR", 5: "WIDE", 6: "HARM", 7: "FDN8", 8: "XDLY",
            9: "SUB", 10: "DIST", 11: "GATR", 12: "RING", 13: "JUNO"}
FX_ICONS = {
    0: ["..###..", ".#..##.", ".#.#.#.", ".##..#.", "..###.."],     # OFF: the "none" sign (the User, 2026-11-20)
    4: [".#...#.", "#.#.#.#", "...#...", ".#...#.", "#.#.#.#"],     # CHOR: one wave twice, the second a step behind
    10: ["...###.", "..##...", ".#####.", "...##..", ".###..."],    # DIST: the overdrive pedal's lightning bolt
    7: ["...#..#", ".#..#.#", "#.#.#.#", ".#..#.#", "...#..#"],     # FDN8: ripples spreading in a room
    3: ["..#.#..", ".#.#.#.", ".#...#.", "#.....#", "#.....#"],     # FOLD: a wave, its top folded back down
    1: ["#.#.#..", "#####..", "....#..", "....###", "....#.#"],     # FUZZ: a square with hairs on it
    11: ["##.#.##", "##.#.##", "##.#.##", "##.#.##", "##.#.##"],    # GATR: the sound chopped: on, off, on
    6: ["#######", ".......", "###.###", ".......", "#.#.#.#"],     # HARM: the string whole, halves, quarters
    13: ["#.#####", "#..#.#.", "#..#.#.", "#..#.#.", "#.#####"],    # JUNO: the Juno-106's CHORUS I and II
    12: [".#####.", "#.#.#.#", "#..#..#", "#.#.#.#", ".#####."],    # RING: the ring modulator's sign, x in a circle
    9: ["#.#.#.#", ".#.#.#.", ".......", ".#####.", "#.....#"],     # SUB: a note and its octave below
    2: ["###.###", "#.#.#.#", "###.###", ".#...#.", "..###.."],     # TAPE: two reels, the tape under them
    5: ["...#...", ".#.#.#.", "#..#..#", ".#.#.#.", "...#..."],     # WIDE: from the middle out, both ways
    8: ["#......", "#......", "#.#....", "#.#.#..", "#.#.#.#"],     # XDLY: repeats, each quieter
}
NAME_MAX = 12
DIVIDER = -1


def _group(t: int) -> int:
    """coldfire's group(type) as rewritten (GROUP_SOURCE): the synths, MIDI, the sample machines
    SAMPLER_FIRST..SAMPLER_LAST, ours. FLEX (17) is not a sample machine there, so stock's list has a divider
    on each side of it (GRID | FLEX | MIDI): the rows drawn must be stock's, row for row, or the page
    highlights the wrong cell from FLEX on (2026-11-14, the gate's msel step on r6)"""
    from . import coldfire as C
    if t < 0:
        return 0
    if t <= 3:
        return 1
    if t == 4:
        return 2
    if C.SAMPLER_FIRST <= t <= C.SAMPLER_LAST:
        return C.SAMPLER_GROUP
    return C.SAMPLE_GROUP


def machine_rows() -> list[int]:
    from . import coldfire as C
    rows, last = [], None
    for t in C.LIST_NEW:
        g = _group(t)
        if last is not None and g != last:
            rows.append(DIVIDER)
        rows.append(t)
        last = g
    return rows


def shown_index(rows: list[int], at: int) -> int:
    """the cell (counted over the whole list) msel.c draws stock's row AT in: the dividers take none (2026-11-20, the
    User: "remove the lines --------------")"""
    return sum(1 for t in rows[:at] if t != DIVIDER)


def filter_rows() -> list[int]:
    from ..engines.analog2.filters import coldfire as F
    return list(F.LIST_NEW)


def fx_rows() -> list[int]:
    """INSERT SEL's rows: OFF, then the types A-Z by name (csrc/inserts/ins.c ORDER)"""
    return [0] + sorted((y for y in FX_NAMES if y), key=lambda y: FX_NAMES[y])


def _icon_bytes(rows: list[str]) -> list[int]:
    assert len(rows) == 5 and all(len(r) == 7 for r in rows)
    return [sum(1 << (6 - i) for i, ch in enumerate(r) if ch == "#") for r in rows]


def c_header() -> str:
    mrows, frows, irows = machine_rows(), filter_rows(), fx_rows()
    out = ["/* MACHINE SEL in two columns (dnfw.waverider.msel) */",
           f"#define MSEL_MROWS {len(mrows)}", f"#define MSEL_FROWS {len(frows)}", f"#define MSEL_IROWS {len(irows)}",
           "static const signed char msel_mrows[MSEL_MROWS] = {" + ", ".join(map(str, mrows)) + "};",
           "static const signed char msel_frows[MSEL_FROWS] = {" + ", ".join(map(str, frows)) + "};",
           "static const signed char msel_irows[MSEL_IROWS] = {" + ", ".join(map(str, irows)) + "};"]
    for kind, names, icons, rows in (("m", machine_names(), machine_icons(), mrows), ("f", FILTER_NAMES, FILTER_ICONS, frows),
                                     ("i", FX_NAMES, FX_ICONS, irows)):
        top = max(t for t in rows if t >= 0) + 1
        for t in rows:
            if t >= 0:
                assert t in names and t in icons, (kind, t)
                assert len(names[t]) <= NAME_MAX, names[t]
        out.append(f"static const char *const msel_{kind}name[{top}] = {{"
                   + ", ".join(f'"{names[t]}"' if t in names else "0" for t in range(top)) + "};")
        out.append(f"static const unsigned char msel_{kind}icon[{top}][5] = {{"
                   + ", ".join("{" + ", ".join(str(b) for b in _icon_bytes(icons[t])) + "}" if t in icons else "{0}"
                               for t in range(top)) + "};")
    return "\n".join(out) + "\n"
