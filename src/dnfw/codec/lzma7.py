"""Section 7 (the DSP program) as LZMA: the stream our SHARC uploader decodes (docs/lzma7.md).

    'DN7Z' | u32 unpacked length | u8 LZMA props ((pb * 5 + lp) * 9 + lc) | 3 zero bytes |
    u32 CRC-32 (IEEE) of the unpacked bytes | raw LZMA1 stream          (all big-endian)

`csrc/waverider/lzma7.c` (`dn_depack7`) decodes it on the ColdFire in place of stock's aPLib
call, and refuses anything whose length or CRC does not match (the uploader then leaves the DSP
in reset and MAIN OS goes on). The same rules are checked here, so a stream this module accepts
is one the instrument accepts.

Measured on v0.48's section 7 (scratch/room/smaller-image.md): 982,562 B -> 520,680 B of
stream, against 669,696 B of aPLib; lc 0, lp 1, pb 1 is the smallest of six settings tried.
"""

from __future__ import annotations

import lzma
import struct
import zlib

MAGIC = b"DN7Z"
HEAD = 16
MAX = 0xFFFFF                     # the uploader's 1 MiB buffer after its 0x03 byte
LC, LP, PB = 0, 1, 1
LC_LP_MAX = 3                     # the decoder's probability table (csrc/waverider/lzma7.c)


class Lzma7Error(ValueError):
    pass


def _filters(lc: int, lp: int, pb: int) -> list[dict]:
    return [{"id": lzma.FILTER_LZMA1, "preset": 9 | lzma.PRESET_EXTREME, "dict_size": 1 << 22,
             "lc": lc, "lp": lp, "pb": pb}]


def is_lzma7(stream: bytes) -> bool:
    return stream[:4] == MAGIC


def pack(content: bytes) -> bytes:
    """-> header + raw LZMA1 stream for CONTENT."""
    if not 0 < len(content) <= MAX:
        raise Lzma7Error(f"{len(content):,} B: the uploader takes 1..{MAX:,}")
    body = lzma.compress(content, format=lzma.FORMAT_RAW, filters=_filters(LC, LP, PB))
    props = (PB * 5 + LP) * 9 + LC
    head = MAGIC + struct.pack(">IB3xI", len(content), props, zlib.crc32(content))
    out = head + body
    if unpack(out) != content:
        raise Lzma7Error("the packed stream does not decode back to its content")
    return out


def unpack(stream: bytes) -> bytes:
    """The content of an lzma7 stream, under the decoder's own rules."""
    if len(stream) < HEAD or not is_lzma7(stream):
        raise Lzma7Error("not an lzma7 stream")
    length, props, pad0, pad1, pad2, crc = struct.unpack(">IBBBBI", stream[4:HEAD])
    lc, lp, pb = props % 9, (props // 9) % 5, props // 45
    if not 0 < length <= MAX:
        raise Lzma7Error(f"length {length:,} outside 1..{MAX:,}")
    if props >= 225 or lc + lp > LC_LP_MAX or pad0 or pad1 or pad2:
        raise Lzma7Error(f"props 0x{props:02x} or padding out of range")
    try:
        d = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=_filters(lc, lp, pb))
        out = d.decompress(stream[HEAD:], max_length=length)
    except lzma.LZMAError as exc:
        raise Lzma7Error(f"LZMA: {exc}") from exc
    if len(out) != length or zlib.crc32(out) != crc:
        raise Lzma7Error("length or CRC-32 does not match the header")
    return out
