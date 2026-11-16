"""remoteui-6: which build is on the unit. BUILDINFO carries a CRC-32 (zlib's) of the C chunk's code and rodata
as the unit holds it in RAM (protocol.BuildId); this computes the same CRC from a file:

- a firmware `.syx` (or the `.zip` around one): its MAIN OS section's CODE chunks, as the loader places them
  (dnfw.mods.platform.runtime); needs this repository's `dnfw` importable (its `src` on PYTHONPATH);
- a `waverider_code.json` (src/dnfw/mods/): the C chunk it records, no dnfw needed.

The unit names the range (code_lo, code_len), so nothing here assumes where the chunk is."""

from __future__ import annotations

import json
import pathlib
import zlib

from .protocol import BuildId


def crc_of(pieces: list[tuple[int, bytes]], lo: int, n: int) -> int | None:
    """the CRC of [LO, LO + N) from PIECES [(address, bytes)]; None if no single piece holds the whole range"""
    for at, data in pieces:
        if at <= lo and lo + n <= at + len(data):
            return zlib.crc32(data[lo - at:lo - at + n]) & 0xFFFFFFFF
    return None


def pieces_of(path: pathlib.Path) -> list[tuple[int, bytes]]:
    """[(address, bytes)] a file puts in RAM: a waverider_code.json's C chunk, or a firmware file's CODE chunks"""
    if path.suffix.lower() == ".json":
        c = json.loads(path.read_text())["c_chunk"]
        return [(c["load"], bytes.fromhex(c["code"]))]
    try:
        from dnfw.cli.files import read_image
        from dnfw.firmware.load import load
        from dnfw.mods import platform
    except ImportError as e:
        raise SystemExit(f"--file {path.name}: reading a firmware file needs dnfw (this repository's src on "
                         f"PYTHONPATH): {e}. Or give the build's src/dnfw/mods/waverider_code.json") from None
    return platform.runtime(load(read_image(path)).container.find(3).unpack())


def match(ident: BuildId, path: pathlib.Path) -> tuple[bool, str]:
    """-> (the unit runs this file's code, a line saying so)"""
    crc = crc_of(pieces_of(path), ident.code_lo, ident.code_len)
    rng = f"{ident.code_lo:#010x} +{ident.code_len:,} B"
    if crc is None:
        return False, f"NO MATCH: {path.name} has no code at {rng} (not a build with this chunk)"
    if crc == ident.crc:
        return True, f"MATCH: the unit runs {path.name}'s ColdFire code (CRC-32 {crc:08x} over {rng})"
    return False, f"NO MATCH: the unit's CRC-32 {ident.crc:08x}, {path.name}'s {crc:08x} (over {rng})"
