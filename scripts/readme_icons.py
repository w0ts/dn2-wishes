#!/usr/bin/env python3
"""Render the README's icons to docs/img/icons/*.png: the firmware's 7 x 5 one-bit icons
(dnfw.waverider.msel MACHINE_ICONS, OUR_ICONS, FILTER_ICONS) and the approved FX insert icons
(not yet in the firmware), on a transparent background, 6x, nearest neighbour: NAME.png dark pixels (light pages), NAME-dark.png light
pixels (dark pages; the README picks one with <picture>).
PNG written with zlib + struct (no PIL).  Run: PYTHONPATH=src python3 scripts/readme_icons.py"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

from dnfw.waverider import msel

SCALE, PAD = 6, 1                       # a pixel is 6 x 6; one pixel of margin round the 7 x 5
INK = {"": (20, 24, 30, 255), "-dark": (236, 236, 232, 255)}
CLEAR = (0, 0, 0, 0)
STOCK = {0, 1, 2, 3, 4}                    # Elektron's own machines: not in the README
OUT = Path(__file__).resolve().parent.parent / "docs" / "img" / "icons"

# the FX icons the User approved (2026-11-20); not in the firmware yet
FX_ICONS = {
    "CHOR": [".#...#.", "#.#.#.#", "...#...", ".#...#.", "#.#.#.#"],
    "DIST": ["...###.", "..##...", ".#####.", "...##..", ".###..."],
    "FDN8": ["...#..#", ".#..#.#", "#.#.#.#", ".#..#.#", "...#..#"],
    "FOLD": ["..#.#..", ".#.#.#.", ".#...#.", "#.....#", "#.....#"],
    "FUZZ": ["#.#.#..", "#####..", "....#..", "....###", "....#.#"],
    "GATR": ["##.#.##", "##.#.##", "##.#.##", "##.#.##", "##.#.##"],
    "HARM": ["#######", ".......", "###.###", ".......", "#.#.#.#"],
    "JUNO": ["#.#####", "#..#.#.", "#..#.#.", "#..#.#.", "#.#####"],
    "RING": [".#####.", "#.#.#.#", "#..#..#", "#.#.#.#", ".#####."],
    "SUB": ["#.#.#.#", ".#.#.#.", ".......", ".#####.", "#.....#"],
    "TAPE": ["###.###", "#.#.#.#", "###.###", ".#...#.", "..###.."],
    "WIDE": ["...#...", ".#.#.#.", "#..#..#", ".#.#.#.", "...#..."],
    "XDLY": ["#......", "#......", "#.#....", "#.#.#..", "#.#.#.#"],
}


def png(rows: list[str], ink: tuple) -> bytes:
    w, h = (7 + 2 * PAD) * SCALE, (5 + 2 * PAD) * SCALE
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        py = y // SCALE - PAD
        for x in range(w):
            px = x // SCALE - PAD
            lit = 0 <= py < 5 and 0 <= px < 7 and rows[py][px] == "#"
            raw += bytes(ink if lit else CLEAR)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def slug(name: str) -> str:
    return name.lower().replace(" -", " minus").replace(" ", "-").replace("/", "-").replace("+", "plus").replace("--", "-")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for t, rows in msel.MACHINE_ICONS.items():
        if t in STOCK:
            continue
        jobs["machine-" + slug(msel.MACHINE_NAMES[t])] = rows
    for key, rows in msel.OUR_ICONS.items():
        jobs["machine-" + slug(msel.OUR_NAMES[key])] = rows
    for t, rows in msel.FILTER_ICONS.items():
        jobs["filter-" + slug(msel.FILTER_NAMES[t])] = rows
    for name, rows in FX_ICONS.items():
        jobs["fx-" + slug(name)] = rows
    for name, rows in jobs.items():
        for suffix, ink in INK.items():
            (OUT / f"{name}{suffix}.png").write_bytes(png(rows, ink))
    print(len(jobs), "icons (light and dark) in", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
