"""The wishes record on the host (src/dnfw/wishes): the link a stored sound carries, the records carried in a
.dn2pst as `wishes.bin`. The client against the firmware's own C is in test_wishes_c.py (travel)."""

from __future__ import annotations

import io
import json
import struct
import zipfile
import zlib

import pytest

from dnfw.wishes import pst as P
from dnfw.wishes import record as R


def spell(fields: dict[int, bytes]) -> bytes:
    return b"".join(t.to_bytes(2, "big") + len(v).to_bytes(2, "big") + v for t, v in sorted(fields.items()))


def literal_block(data: bytes) -> bytes:
    """one LZ4 block of literals only (a valid block: its one sequence has no match)"""
    n, head = len(data), bytearray()
    if n < 15:
        return bytes([n << 4]) + data
    head.append(0xF0)
    k = n - 15
    while k >= 255:
        head.append(255)
        k -= 255
    head.append(k)
    return bytes(head) + data


def payload(stored: bytes) -> bytes:
    body = struct.pack(">I", 2) + b"\0" + stored
    block = literal_block(body)
    chain = struct.pack(">I", len(block)) + block + b"\0\0\0\0"
    head = (P.PAYLOAD_MAGIC + bytes.fromhex("020005000f") + b"0049"
            + struct.pack(">IIII", 3, 2, 0, len(body)) + bytes([1, 12]))
    return head + chain + struct.pack(">II", zlib.crc32(chain, 0xFFFFFFFF), len(chain)) + P.TRAILER


def preset_file(stored: bytes, name: str = "MY SOUND") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("manifest.json", json.dumps({"Payload": name, "FileType": "Sound"}), zipfile.ZIP_DEFLATED)
        z.writestr(name, payload(stored), zipfile.ZIP_DEFLATED)
    return out.getvalue()


REC = spell({0x10: bytes([0, 67, 0x50, 0]), 0x11: bytes([8, 127, 32, 96, 24, 1, 1, 0])})


def test_xxh32_reference_values():
    assert R.xxh32(b"", 0) == 0x02CC5D05
    assert R.xxh32(b"a", 0) == 0x550D7456
    assert R.xxh32(b"Nobody inspects the spammish repetition", 0) == 0xE2293B2F


def test_a_link_written_reads_back_and_names_its_record():
    stored = R.write_link(bytes(R.STORED), REC)
    link = R.read_link(stored)
    assert link and link.matches(REC) and not link.matches(REC + b"\0\0\0\0")
    changed = set(i for i in range(R.STORED) if stored[i])
    assert changed <= {at + k for at in R.LANE for k in (0, 1)}


def test_a_lane_that_is_not_our_link_is_no_link():
    stored = bytearray(R.write_link(bytes(R.STORED), REC))
    stored[85] ^= 1                                             # the check
    assert R.read_link(bytes(stored)) is None
    assert R.read_link(bytes(R.STORED)) is None


def test_records_must_be_spelled_as_ours():
    assert R.valid(REC) and not R.valid(b"") and not R.valid(REC[:-1]) and not R.valid(bytes(489))
    assert not R.valid(spell({0x11: b"a"}) + spell({0x10: b"b"}))   # tags out of order


def test_the_record_rides_in_wishes_bin_and_the_rest_is_kept():
    raw = preset_file(R.write_link(bytes(R.STORED), REC))
    p = P.Preset(raw)
    assert p.link().matches(REC) and p.record() is None
    out = P.Preset(p.with_records([REC]))
    assert out.record() == REC and out.records() == [REC]
    for name in ("manifest.json", "MY SOUND"):
        assert out.zip.read(name) == p.zip.read(name)
    assert out.zip.namelist() == ["manifest.json", "MY SOUND", "wishes.bin"]
    again = P.Preset(out.with_records([REC]))                  # added twice: still one entry
    assert again.zip.namelist().count("wishes.bin") == 1


def test_a_wishes_bin_whose_record_does_not_match_its_hash_is_refused():
    raw = bytearray(P.encode_records([REC]))
    raw[-1] ^= 1
    with pytest.raises(ValueError):
        P.decode_records(bytes(raw))


def test_a_stock_preset_has_no_link():
    p = P.Preset(preset_file(bytes(R.STORED)))
    assert p.link() is None and p.record() is None


def test_a_payload_with_a_bad_crc_is_refused():
    pl = bytearray(payload(bytes(R.STORED)))
    pl[40] ^= 1
    with pytest.raises(ValueError):
        P.body_of(bytes(pl))
