"""MACHINE SEL in two columns (2026-11-11, the User's design E; csrc/msel/msel.c draws it over stock's view).

The rows are the ones stock's MachineListView builds (row builder 0x4005b2c0), made here from the same
lists: the machine page from coldfire.LIST_NEW with a divider wherever coldfire's group(type) changes (as
0x40059274 rewritten tells stock), the filter page from a2f.coldfire's FLTR list (stock draws no divider
there). The emulator test walks the cursor over every row and holds these tables to stock's count. Each
type has a name (12 characters at most: two 61-pixel columns, the list's own 3 x 5 font) and a 7 x 5 icon.
"""
from __future__ import annotations

# the names (the User's E, 2026-11-11): what each machine is, at most 12 characters
MACHINE_NAMES = {0: "FM TONE", 1: "WAVETONE", 2: "FM DRUM", 3: "SWARMER", 4: "MIDI",
                 5: "PERC MD KIT", 20: "SOPHIE PERC", 18: "PLAITS MACRO", 19: "TB-303 ACID",
                 21: "DRONE SINES", 22: "ANALOG 2 VA",
                 6: "SID 6581", 7: "DPRO-WAVE", 14: "DPRO-DDRW", 15: "DPRO-DENS", 16: "VO-6 VOICE",
                 8: "ONESHOT", 9: "WERP", 10: "STRETCH", 11: "REPITCH", 12: "GRID", 13: "SLICE", 17: "BOUNCE"}
FILTER_NAMES = {0: "MULTI-MODE", 1: "LOWPASS 4", 2: "EQUALIZER", 3: "COMB -", 4: "LEGACY LP/HP", 5: "COMB +",
                7: "A2 SVF", 8: "A2 LADDER", 9: "A2 OTA", 10: "A2 DIODE", 11: "A2 MS-20"}
# the icons, 7 x 5, rows top to bottom (scratch/lists/mock_e.py, the mock-up the User approved)
MACHINE_ICONS = {
    0: [".#.....", "#.#....", "...#...", "....#.#", ".....#."],      # FM TONE: a sine
    1: ["#..#..#", "##.##.#", "#.#.#.#", "#..#..#", "#..#..#"],      # WAVETONE: a saw table
    2: ["#......", "##.....", "#.#....", "#..##..", "#....##"],      # FM DRUM: a decay
    3: ["#.#.#.#", ".#.#.#.", "#.#.#.#", ".#.#.#.", "#.#.#.#"],      # SWARMER: a swarm
    4: [".#####.", "#.#.#.#", "#.....#", "#..#..#", ".#####."],      # MIDI: the DIN socket
    5: [".#####.", "#.....#", "#######", "#.....#", ".#####."],      # PERC: a drum
    20: ["...#...", "..#.#..", ".#...#.", "#.....#", "###.###"],     # SOPHIE: a ping
    18: ["#...#..", ".#.#.#.", "..#...#", ".#.#.#.", "#...#.."],     # PLAITS: a braid
    19: [".#...#.", ".......", "#.....#", ".#...#.", "..###.."],     # TB-303: the acid smiley
    21: ["#######", ".......", "#######", ".......", "#######"],     # DRONE: held tones
    22: ["...#..#", "..##.##", ".#.#.#.", "#..##..", "...#..."],     # ANALOG 2: two saws
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
NAME_MAX = 12
DIVIDER = -1


def _group(t: int) -> int:
    """coldfire's group(type) as rewritten (GROUP_SOURCE): the synths, MIDI, the sample machines, ours"""
    from . import coldfire as C
    if t < 0:
        return 0
    if t <= 3:
        return 1
    if t == 4:
        return 2
    if C.SAMPLER_FIRST <= t <= C.SAMPLER_LAST or t == getattr(C, "BOUNCE_TYPE", 17):
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


def filter_rows() -> list[int]:
    from ..a2f import coldfire as F
    return list(F.LIST_NEW)


def _icon_bytes(rows: list[str]) -> list[int]:
    assert len(rows) == 5 and all(len(r) == 7 for r in rows)
    return [sum(1 << (6 - i) for i, ch in enumerate(r) if ch == "#") for r in rows]


def c_header() -> str:
    mrows, frows = machine_rows(), filter_rows()
    out = ["/* MACHINE SEL in two columns (dnfw.waverider.msel) */",
           f"#define MSEL_MROWS {len(mrows)}", f"#define MSEL_FROWS {len(frows)}",
           "static const signed char msel_mrows[MSEL_MROWS] = {" + ", ".join(map(str, mrows)) + "};",
           "static const signed char msel_frows[MSEL_FROWS] = {" + ", ".join(map(str, frows)) + "};"]
    for kind, names, icons, rows in (("m", MACHINE_NAMES, MACHINE_ICONS, mrows), ("f", FILTER_NAMES, FILTER_ICONS, frows)):
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
