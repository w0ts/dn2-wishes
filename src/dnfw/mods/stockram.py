"""No chunk of ours lies in RAM stock OS 1.12 writes (2026-11-16).

`ramcheck` assumed the RAM above BSS belongs to no one. On 1.12 that is false: stock's uncached
buffers moved up 0x8000, and its +Drive bounce buffer (0x4e6f9300, 64 KiB, the uncached alias of
0x466f9300..0x46709300) is written whenever a read's destination is not 16-aligned or its length
not whole sectors (the read routine 0x4012c87a, disassembled). The boot-screen stamp sat at
0x46708000, under it, and crashed the unit at every power-on (combined build 7f7e7d6c, EXCEPTION,
Line-F, PC 0x46708000; the same on 2026-11-08).

Two sources of the RAM stock writes:

- `BOUNCE`: the bounce buffer's whole reach, from the read routine itself (a call is at most 64 KiB;
  the DMA writes whole sectors from 0x4e6f9300), whatever the emulator happened to read;
- `stock112_writes.json`: the 256-byte blocks stock 1.12 wrote between writemap.LO and HI in the
  emulator (scripts/stock_ram_map.py: boot from reset, blank and with a project, and stock UI walks),
  through 0x46..., the uncached alias and the emulator's DMA.

`clashes(extents)` -> every (chunk, range) that overlaps either. The gate's `rammap` step and
test/test_stock_ram_112.py hold the build's chunks (waverider.ram(), bootscreen.ram()) to it.
"""

from __future__ import annotations

import json
import pathlib

ALIAS = 0x08000000
BOUNCE = (0x4E6F9300 - ALIAS, 0x4E6F9300 - ALIAS + 0x10000)      # 0x466f9300..0x46709300
MAP = pathlib.Path(__file__).with_name("stock112_writes.json")
# the gate's boot step makes one stock read through the bounce buffer at power-on (scripts/emu_boot_check.py,
# bounce_read): SECTOR, a whole 64 KiB call, into an unaligned BUF that neither stock nor we use
PROBE_READ = (0x100000, 0x10000, 0x46A10004)


def measured() -> list[tuple[int, int]]:
    """The measured ranges [lo, hi) stock 1.12 writes, from MAP."""
    data = json.loads(MAP.read_text())
    return [(int(a, 16), int(b, 16)) for a, b in data["ranges"]]


def stock_ranges() -> list[tuple[int, int, str]]:
    return [(*BOUNCE, "stock 1.12's +Drive bounce buffer (0x4e6f9300, 64 KiB)")] + [
        (a, b, "written by stock 1.12 in the emulator (stock112_writes.json)") for a, b in measured()]


def clashes(extents) -> list[str]:
    """extents: objects with .start, .length and a str() -> 'chunk overlaps range (what)' lines."""
    out = []
    ranges = stock_ranges()
    for e in extents:
        lo, hi = e.start, e.start + e.length
        for a, b, what in ranges:
            if lo < b and a < hi:
                out.append(f"{e} [{lo:#010x}..{hi:#010x}) overlaps {a:#010x}..{b:#010x}: {what}")
    return out


def ours(env=None):
    """Every RAM extent the build in this tree places or uses: every shipped mod's ram() (dnfw.mods.shipped:
    waverider, lfowaves, lfo4 with DN2_LFO4) and the boot-screen stamp's. 2026-11-17: this was waverider's and
    bootscreen's alone, so lfo4's LFO state arrays (0x46700000.., inside the bounce buffer) were never checked."""
    import importlib                                            # noqa: PLC0415
    from . import RAM, bootscreen, platform, shipped            # noqa: PLC0415
    out, seen = [], set()
    every = [e for mid in shipped(env) for e in importlib.import_module(f"{__package__}.{mid}").ram()]
    for e in every + bootscreen.ram() + platform.ram():          # and the loader's own data window
        if e.section == RAM and (e.start, e.length) not in seen:
            seen.add((e.start, e.length))
            out.append(e)
    return out
