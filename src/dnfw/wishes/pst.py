"""Wishes records in Digitone II preset files (.dn2pst): the sound's link read, the records carried as a third ZIP
entry, `wishes.bin` (docs/wishes-record.md "Travel").

Elektron Transfer sends only the payload `manifest.json` names, so a preset sent to another unit arrives with its
link and without its record. Our tools put the record beside it, and `scripts/wish_pst.py send` gives it to the unit
over our SysEx channel (link.c PUT); the sound finds it by its hash.

The file is a ZIP of `manifest.json` and the payload (the combine session's reader, scratch/presets-work/dn2pst.py,
measured on 820 presets): a 31-byte header, one LZ4 block of the 364-byte body (a 5-byte prefix, then the 359-byte
stored sound), a CRC-32 and a trailer. Adding `wishes.bin` keeps the other two entries byte for byte.

`wishes.bin`: 'WSH1', u16 count, then per record u32 h0, u32 h1, u16 length, the record (big-endian).
"""

from __future__ import annotations

import io
import json
import struct
import time
import zipfile
import zlib

from . import record as R

ENTRY = "wishes.bin"
MAGIC = b"WSH1"
PAYLOAD_MAGIC = bytes.fromhex("ac11d303")
TRAILER = bytes.fromhex("aaa1daaa")
PREFIX = 5                                      # the body's prefix before the stored sound


def lz4_block(src: bytes, n: int) -> bytes:
    """-> N bytes from one LZ4 block"""
    i, out = 0, bytearray()
    while i < len(src):
        t = src[i]
        i += 1
        k = t >> 4
        if k == 15:
            while True:
                b = src[i]
                i += 1
                k += b
                if b != 255:
                    break
        out += src[i:i + k]
        i += k
        if i >= len(src):
            break
        off = src[i] | src[i + 1] << 8
        i += 2
        m = (t & 15) + 4
        if (t & 15) == 15:
            while True:
                b = src[i]
                i += 1
                m += b
                if b != 255:
                    break
        if not 0 < off <= len(out):
            raise ValueError("LZ4: an offset outside the output")
        for _ in range(m):
            out.append(out[-off])
    if len(out) != n:
        raise ValueError(f"LZ4 block gave {len(out)} bytes, not {n}")
    return bytes(out)


def body_of(payload: bytes) -> bytes:
    """-> the payload's body (prefix + stored sound), its CRC checked"""
    if payload[:4] != PAYLOAD_MAGIC:
        raise ValueError("not a sound payload")
    n = struct.unpack_from(">I", payload, 25)[0]
    L = struct.unpack_from(">I", payload, 31)[0]
    chain = payload[31:35 + L + 4]
    crc, tl = struct.unpack_from(">II", payload, 35 + L + 4)
    if payload[35 + L:39 + L] != b"\0\0\0\0" or tl != L + 8 or payload[-4:] != TRAILER:
        raise ValueError("bad block chain or trailer")
    if zlib.crc32(chain, 0xFFFFFFFF) != crc:
        raise ValueError("payload CRC mismatch")
    return lz4_block(payload[35:35 + L], n)


def encode_records(recs: list[bytes]) -> bytes:
    out = bytearray(MAGIC + struct.pack(">H", len(recs)))
    for rec in recs:
        if not R.valid(rec):
            raise ValueError("not a record of ours")
        h0, h1 = R.hash_of(rec)
        out += struct.pack(">IIH", h0, h1, len(rec)) + rec
    return bytes(out)


def decode_records(raw: bytes) -> list[bytes]:
    """-> the records in a wishes.bin, each checked against its hash"""
    if raw[:4] != MAGIC:
        raise ValueError(f"{ENTRY}: not 'WSH1'")
    (count,), at, recs = struct.unpack_from(">H", raw, 4), 6, []
    for _ in range(count):
        h0, h1, n = struct.unpack_from(">IIH", raw, at)
        rec = raw[at + 10:at + 10 + n]
        if len(rec) != n or R.hash_of(rec) != (h0, h1) or not R.valid(rec):
            raise ValueError(f"{ENTRY}: a record does not match its hash")
        recs.append(rec)
        at += 10 + n
    return recs


class Preset:
    """a .dn2pst read: its ZIP entries kept as they are"""

    def __init__(self, raw: bytes):
        self.zip = zipfile.ZipFile(io.BytesIO(raw))
        self.manifest = json.loads(self.zip.read("manifest.json"))
        self.payload_name = self.manifest["Payload"]
        self.stored = body_of(self.zip.read(self.payload_name))[PREFIX:]

    def link(self) -> R.Link | None:
        return R.read_link(self.stored)

    def records(self) -> list[bytes]:
        return decode_records(self.zip.read(ENTRY)) if ENTRY in self.zip.namelist() else []

    def record(self) -> bytes | None:
        """-> the record the sound's link names, when the file carries it"""
        link = self.link()
        return next((r for r in self.records() if link and link.matches(r)), None)

    def with_records(self, recs: list[bytes]) -> bytes:
        """-> the file again with RECS as its wishes.bin (the other entries copied as they are)"""
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for info in self.zip.infolist():
                if info.filename != ENTRY:
                    z.writestr(info, self.zip.read(info.filename), compress_type=info.compress_type)
            if recs:
                info = zipfile.ZipInfo(ENTRY, time.localtime()[:6])
                z.writestr(info, encode_records(recs), compress_type=zipfile.ZIP_DEFLATED)
        return out.getvalue()
