"""The wishes record on the host: its hash and the link a stored sound carries (csrc/wishes, docs/wishes-record.md).

A record is fields (tag u16, length u16, value), tags strictly ascending. Its hash is two xxHash32 of the record,
seeds 'WISH' and 'N2MX'. The link is seven big-endian words in the stored sound's lane, ids 4..28 = stored bytes
36, 44, .. 84: 'W' and the link's version, h0 (two words), h1 (two words), the record's length, a 16-bit check.
"""

from __future__ import annotations

from dataclasses import dataclass

SEED0, SEED1 = (int.from_bytes(t, "big") for t in (b"WISH", b"N2MX"))   # as csrc/wishes/tlv.c's TAG4s
MAX = 488                                       # a record's bytes: what one +Drive cell holds
STORED = 359                                    # a stored sound
LANE = (36, 44, 52, 60, 68, 76, 84)             # the link's words: head, h0 hi, h0 lo, h1 hi, h1 lo, length, check
HEAD = 0x5701                                   # 'W', link version 1

_M = 0xFFFFFFFF
_P1, _P2, _P3, _P4, _P5 = 2654435761, 2246822519, 3266489917, 668265263, 374761393


def _rotl(x: int, r: int) -> int:
    return ((x << r) | (x >> (32 - r))) & _M


def xxh32(data: bytes, seed: int) -> int:
    """xxHash32, as csrc/wishes/tlv.c wish_xxh32"""
    n, i = len(data), 0
    if n >= 16:
        v = [(seed + _P1 + _P2) & _M, (seed + _P2) & _M, seed & _M, (seed - _P1) & _M]
        while i + 16 <= n:
            for k in range(4):
                lane = int.from_bytes(data[i + 4 * k:i + 4 * k + 4], "little")
                v[k] = _rotl((v[k] + lane * _P2) & _M, 13) * _P1 & _M
            i += 16
        h = (_rotl(v[0], 1) + _rotl(v[1], 7) + _rotl(v[2], 12) + _rotl(v[3], 18)) & _M
    else:
        h = (seed + _P5) & _M
    h = (h + n) & _M
    while i + 4 <= n:
        h = _rotl((h + int.from_bytes(data[i:i + 4], "little") * _P3) & _M, 17) * _P4 & _M
        i += 4
    while i < n:
        h = _rotl((h + data[i] * _P5) & _M, 11) * _P1 & _M
        i += 1
    h ^= h >> 15
    h = h * _P2 & _M
    h ^= h >> 13
    h = h * _P3 & _M
    return h ^ (h >> 16)


def hash_of(rec: bytes) -> tuple[int, int]:
    return xxh32(rec, SEED0), xxh32(rec, SEED1)


def valid(rec: bytes) -> bool:
    """-> True when REC is spelled as a record of ours (csrc/wishes/tlv.c wish_tlv_valid)"""
    if not 0 < len(rec) <= MAX:
        return False
    i, last = 0, -1
    while i < len(rec):
        if i + 4 > len(rec):
            return False
        tag, n = int.from_bytes(rec[i:i + 2], "big"), int.from_bytes(rec[i + 2:i + 4], "big")
        if tag <= last or i + 4 + n > len(rec):
            return False
        last, i = tag, i + 4 + n
    return True


@dataclass(frozen=True)
class Link:
    h0: int
    h1: int
    length: int

    def matches(self, rec: bytes) -> bool:
        return len(rec) == self.length and hash_of(rec) == (self.h0, self.h1)


def _check(h0: int, h1: int, length: int) -> int:
    x = xxh32(b"", (HEAD ^ h0 ^ _rotl(h1, 7) ^ (length << 16)) & _M)
    return (x ^ (x >> 16)) & 0xFFFF


def read_link(stored: bytes) -> Link | None:
    """-> the link in a stored sound's lane, or None (no link of ours: a stock sound, another firmware's words)"""
    if len(stored) < STORED:
        return None
    w = [int.from_bytes(stored[at:at + 2], "big") for at in LANE]
    if w[0] != HEAD:
        return None
    link = Link(w[1] << 16 | w[2], w[3] << 16 | w[4], w[5])
    if not 0 < link.length <= MAX or w[6] != _check(link.h0, link.h1, link.length):
        return None
    return link


def write_link(stored: bytes, rec: bytes) -> bytes:
    """-> STORED with the link to REC in its lane (what the firmware's saver writes)"""
    h0, h1 = hash_of(rec)
    out = bytearray(stored)
    for at, v in zip(LANE, (HEAD, h0 >> 16, h0 & 0xFFFF, h1 >> 16, h1 & 0xFFFF, len(rec), _check(h0, h1, len(rec)))):
        out[at:at + 2] = v.to_bytes(2, "big")
    return bytes(out)
