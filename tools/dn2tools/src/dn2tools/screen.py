"""The unit's screen: 128 x 64 pixels, 1 bit each, 1,024 bytes column-major (eight bytes a column, the
top band last): pixel (x, y) is bit y % 8 of byte 8 x + 7 - y // 8. The same layout the project's
emulator captures and tools/dn2screen.py use. PNGs are written with the standard library (zlib), so
no imaging package is needed.
"""

from __future__ import annotations

import pathlib
import struct
import zlib

W, H, SIZE = 128, 64, 1024


def pixel(buf: bytes, x: int, y: int) -> bool:
    return bool(buf[8 * x + 7 - y // 8] >> (y % 8) & 1)


def rows(buf: bytes) -> list[list[bool]]:
    """-> rows[y][x], y down from the top of the glass"""
    if len(buf) != SIZE:
        raise ValueError(f"a frame is {SIZE} bytes, not {len(buf)}")
    return [[pixel(buf, x, y) for x in range(W)] for y in range(H)]


def from_rows(px: list[list[bool]]) -> bytes:
    """the inverse of rows (the simulator draws this way)"""
    out = bytearray(SIZE)
    for y in range(H):
        for x in range(W):
            if px[y][x]:
                out[8 * x + 7 - y // 8] |= 1 << (y % 8)
    return bytes(out)


def png(buf: bytes, scale: int = 4) -> bytes:
    """-> a grey PNG of the frame, each pixel SCALE x SCALE (lit white on black, as the glass)"""
    px = rows(buf)
    raw = bytearray()
    for y in range(H):
        line = bytes(255 if px[y][x] else 0 for x in range(W) for _ in range(scale))
        for _ in range(scale):
            raw += b"\0" + line

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    head = struct.pack(">IIBBBBB", W * scale, H * scale, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def write_png(buf: bytes, path: str | pathlib.Path, scale: int = 4) -> pathlib.Path:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(png(buf, scale))
    return p


def text(buf: bytes) -> str:
    """-> the frame as text, two pixel rows a line (half blocks), for a terminal"""
    px = rows(buf)
    chars = {(False, False): " ", (True, False): "▀", (False, True): "▄", (True, True): "█"}
    return "\n".join("".join(chars[(px[y][x], px[y + 1][x])] for x in range(W)) for y in range(0, H, 2))


def differ(a: bytes, b: bytes) -> int:
    """-> how many pixels differ between two frames"""
    return sum(bin(x ^ y).count("1") for x, y in zip(a, b))
