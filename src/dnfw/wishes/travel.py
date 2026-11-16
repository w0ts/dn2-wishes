"""Records to and from the unit over our SysEx channel (csrc/sampler/link.c smp_rx; csrc/wishes/store.c wish_rx).

    request  F0 00 20 3C 7D 01 <pack7( u16 seq, u8 cmd, args... )> F7
    reply    F0 00 20 3C 7D 01 <pack7( u16 seq, u8 cmd | 0x80, u8 status, data... )> F7

PUT (12): u16 length, the record -> h0, h1. GET (13): h0, h1, u16 offset -> u16 length, u16 offset, up to 128 bytes.
Statuses: 0 ok, 1 bad arguments, 3 not here (GET) or not now (PUT before the table is up), 5 ask again (a PUT not
filed yet, a cell being read). USB only; stock firmware does not answer.
"""

from __future__ import annotations

import struct
import time
from typing import Callable, Protocol

from . import record as R

HEADER = bytes([0xF0, 0x00, 0x20, 0x3C, 0x7D, 0x01])
PUT, GET = 12, 13
OK, BAD, NOT_HERE, AGAIN = 0, 1, 3, 5


def pack7(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), 7):
        grp = data[i:i + 7]
        out.append(sum(1 << (6 - k) for k, b in enumerate(grp) if b & 0x80))
        out.extend(b & 0x7F for b in grp)
    return bytes(out)


def unpack7(data: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(data):
        hdr = data[i]
        i += 1
        for k in range(1, 8):
            if i >= len(data):
                break
            out.append(data[i] | ((hdr << k) & 0x80))
            i += 1
    return bytes(out)


def request(seq: int, cmd: int, args: bytes) -> bytes:
    return HEADER + pack7(struct.pack(">HB", seq, cmd) + args) + b"\xF7"


def reply(raw: bytes) -> tuple[int, int, int, bytes] | None:
    """-> (seq, cmd, status, data) of one of our replies, or None"""
    if raw[:6] != HEADER or raw[-1:] != b"\xF7":
        return None
    d = unpack7(raw[6:-1])
    if len(d) < 4 or not d[2] & 0x80:
        return None
    return int.from_bytes(d[:2], "big"), d[2] & 0x7F, d[3], d[4:]


class Exchange(Protocol):
    def __call__(self, msg: bytes) -> bytes | None: ...   # one request out, its reply (or None: no answer)


class Unit:
    """PUT and GET over EXCHANGE (the unit through mido, or the host-compiled C in the tests)"""

    def __init__(self, exchange: Exchange, wait: Callable[[float], None] = time.sleep, tries: int = 200):
        self.exchange, self.wait, self.tries, self.seq = exchange, wait, tries, 0x700

    def _call(self, cmd: int, args: bytes) -> tuple[int, bytes]:
        self.seq = (self.seq + 1) & 0xFFFF or 1
        raw = self.exchange(request(self.seq, cmd, args))
        r = reply(raw) if raw else None
        if r is None or r[0] != self.seq or r[1] != cmd:
            raise TimeoutError("no answer: is the unit on USB, with a build of ours (stock firmware does not answer)?")
        return r[2], r[3]

    def _again(self, cmd: int, args: bytes) -> tuple[int, bytes]:
        for _ in range(self.tries):
            st, d = self._call(cmd, args)
            if st != AGAIN:
                return st, d
            self.wait(0.05)                     # the UI loop files it or reads its cell (a pass or two)
        raise TimeoutError("the unit kept saying 'ask again'")

    def put(self, rec: bytes) -> tuple[int, int]:
        """-> the hash the unit filed REC under (it checks the same as ours)"""
        if not R.valid(rec):
            raise ValueError("not a record of ours")
        st, d = self._again(PUT, struct.pack(">H", len(rec)) + rec)
        if st != OK or len(d) != 8:
            raise RuntimeError(f"PUT refused (status {st})")
        got = struct.unpack(">II", d)
        if got != R.hash_of(rec):
            raise RuntimeError("the unit filed it under another hash")
        return got

    def get(self, link: R.Link) -> bytes | None:
        """-> the record LINK names, or None when no sound and no cell of the unit holds it"""
        out = b""
        while True:
            st, d = self._again(GET, struct.pack(">IIH", link.h0, link.h1, len(out)))
            if st == NOT_HERE:
                return None
            if st != OK or len(d) < 4:
                raise RuntimeError(f"GET refused (status {st})")
            n = int.from_bytes(d[:2], "big")
            out += d[4:]
            if len(out) >= n:
                break
        if not link.matches(out):
            raise RuntimeError("the record does not match its link")
        return out


def mido_exchange(want: str = "Elektron Digitone II", timeout: float = 1.0) -> Exchange:
    """-> an Exchange over the first MIDI ports whose names hold WANT (the 'mido' and 'python-rtmidi' packages)"""
    import mido
    pick = lambda names: next((n for n in names if want.lower() in n.lower()), None)   # noqa: E731
    out_name, in_name = pick(mido.get_output_names()), pick(mido.get_input_names())
    if not out_name or not in_name:
        raise SystemExit(f"no MIDI port with {want!r} in its name (is the Digitone II on USB?)")
    out, inp = mido.open_output(out_name), mido.open_input(in_name)

    def exchange(msg: bytes) -> bytes | None:
        seq = unpack7(msg[6:-1])[:2]
        out.send(mido.Message("sysex", data=msg[1:-1]))
        end = time.time() + timeout
        while time.time() < end:
            for m in inp.iter_pending():
                raw = bytes([0xF0, *m.data, 0xF7]) if m.type == "sysex" else b""
                r = reply(raw) if raw else None
                if r and r[0] == int.from_bytes(seq, "big"):
                    return raw
            time.sleep(0.001)
        return None
    return exchange
