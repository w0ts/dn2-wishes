"""The test channel's wire format, pure Python and no I/O (docs/remote-ui-protocol.md is the spec;
this module is its executable form and the golden tests hold the two together).

    request  F0 00 20 3C 7D 01 <pack7: u16 seq, u8 cmd, args> F7
    reply    F0 00 20 3C 7D 01 <pack7: u16 seq, u8 cmd | 0x80, u8 status, data> F7

All numbers big-endian. Commands 1 (HELLO) and 32 (TLM) come from the sample link and the telemetry
build; 33..42 are the test channel (a test build only).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER = bytes([0xF0, 0x00, 0x20, 0x3C, 0x7D, 0x01])

# commands
HELLO = 1
TLM = 32
BUILDINFO = 33
SWITCH = 34
PEEK = 35
COUNTERS = 36
TRACE = 37
STATE = 38
SCREEN = 40
ARM = 41
KEY = 42

NAMES = {HELLO: "HELLO", TLM: "TLM", BUILDINFO: "BUILDINFO", SWITCH: "SWITCH", PEEK: "PEEK", COUNTERS: "COUNTERS",
         TRACE: "TRACE", STATE: "STATE", SCREEN: "SCREEN", ARM: "ARM", KEY: "KEY"}

# The only commands a host built on this package sends. Everything else on this SysEx channel (the
# sample link's WRITE, BEGIN, END, FORGET, LOAD, the library, ERASE MOD DATA ...) can change the unit's
# storage, and is refused before it is encoded (unit.request).
READ_ONLY = frozenset({HELLO, TLM, BUILDINFO, PEEK, COUNTERS, TRACE, STATE, SCREEN})
CONTROL = frozenset({SWITCH, ARM, KEY})          # RAM words the firmware whitelists, the arm handshake, keys
ALLOWED = READ_ONLY | CONTROL

# statuses
OK, ARGS, UNARMED, REFUSED, BUSY, RANGE = 0, 2, 3, 4, 5, 6
STATUS_TEXT = {OK: "ok", 1: "failed", ARGS: "bad arguments or unknown command", UNARMED: "not armed",
               REFUSED: "refused (blacklist or handshake)", BUSY: "busy (queue full)", RANGE: "outside the whitelist"}

# capability bits (BUILDINFO)
CAPS = {"TLM": 0, "BUILDINFO": 1, "SWITCH": 2, "PEEK": 3, "COUNTERS": 4, "TRACE": 5, "STATE": 6, "SCREEN": 7,
        "ARM": 8, "KEY": 9}

# KEY event kinds
PRESS, ENCODER, RELEASE = 1, 2, 3

COUNTER_NAMES = ("commands", "refused", "keys_down", "keys_up", "encoder_events", "arms", "disarms", "auto_disarms",
                 "screen_snapshots", "screen_torn", "switch_writes", "dsp_load_max_pct")
TRACE_KINDS = {1: "ARM", 2: "DISARM", 3: "DOWN", 4: "UP", 5: "ENC", 6: "SWITCH", 7: "REFUSED", 8: "RESET", 9: "TORN"}
REFUSE_WHY = {1: "SETTINGS", 2: "not with FUNC held", 3: "FUNC over a held key"}

SCREEN_W, SCREEN_H, SCREEN_BYTES, CHUNK = 128, 64, 1024, 128


def pack7(data: bytes) -> bytes:
    """8-bit -> 7-bit: a header byte holding the high bits of up to 7 bytes (bit 6 = the first byte)."""
    data = bytes(data)
    out = bytearray()
    for i in range(0, len(data), 7):
        grp = data[i:i + 7]
        hdr = 0
        for k, b in enumerate(grp):
            if b & 0x80:
                hdr |= 1 << (6 - k)
        out.append(hdr)
        out.extend(b & 0x7F for b in grp)
    return bytes(out)


def unpack7(data: bytes) -> bytes:
    """7-bit -> 8-bit (a partial last group is allowed)."""
    data = bytes(data)
    out = bytearray()
    i = 0
    while i < len(data):
        hdr = data[i]
        i += 1
        for k in range(1, 8):
            if i >= len(data):
                break
            out.append(data[i] | ((hdr << k) & 0x80))
            i += 1
    return bytes(out)


def encode(seq: int, cmd: int, args: bytes = b"") -> bytes:
    """a request, F0..F7 (no allow-list here: unit.request is the gate)"""
    return HEADER + pack7(struct.pack(">HB", seq & 0xFFFF, cmd) + bytes(args)) + b"\xF7"


@dataclass(frozen=True)
class Reply:
    seq: int
    cmd: int
    status: int
    data: bytes


def decode(sx: bytes) -> Reply | None:
    """a reply, F0..F7 -> Reply, None if it is not one of ours"""
    sx = bytes(sx)
    if not sx.startswith(HEADER) or not sx.endswith(b"\xF7"):
        return None
    msg = unpack7(sx[len(HEADER):-1])
    if len(msg) < 4:
        return None
    seq, cmd, status = struct.unpack(">HBB", msg[:4])
    return Reply(seq, cmd, status, bytes(msg[4:]))


def reply(seq: int, cmd: int, status: int, data: bytes = b"") -> bytes:
    """a reply as the unit sends it (the simulator's side)"""
    return HEADER + pack7(struct.pack(">HBB", seq & 0xFFFF, cmd | 0x80, status) + bytes(data)) + b"\xF7"


# --- the commands' arguments ------------------------------------------------------------------------

def args_switch_info(k: int) -> bytes:
    return bytes([0, k])


def args_switch_get() -> bytes:
    return bytes([1])


def args_switch_set(k: int, value: int) -> bytes:
    return bytes([2, k]) + struct.pack(">I", value)


def args_peek(address: int, length: int) -> bytes:
    if not 1 <= length <= 128:
        raise ValueError("PEEK reads 1..128 bytes")
    return struct.pack(">IB", address, length)


def args_counters(reset: bool = False) -> bytes:
    return bytes([1 if reset else 0])


def args_trace(since: int) -> bytes:
    return struct.pack(">I", since & 0xFFFFFFFF)


def args_screen(chunk: int, drawing: bool = False, fresh: bool = False) -> bytes:
    """DRAWING: the buffer being drawn instead of the one on the glass"""
    return bytes([(1 if drawing else 0) | (2 if fresh else 0), chunk])


def args_arm_ask() -> bytes:
    return bytes([0])


def args_arm_confirm(nonce: int, destructive: bool = False) -> bytes:
    return bytes([1]) + b"ARM!" + struct.pack(">IB", nonce, 1 if destructive else 0)


def args_disarm() -> bytes:
    return bytes([2])


def args_arm_status() -> bytes:
    return bytes([3])


@dataclass(frozen=True)
class Event:
    """one KEY event: PRESS (code, hold ms), ENCODER (encoder 0..8, signed delta), RELEASE (code); AT ms after arrival"""
    kind: int
    code: int
    at_ms: int = 0
    value: int = 0

    def pack(self) -> bytes:
        return struct.pack(">BBHH", self.kind, self.code, self.at_ms, self.value & 0xFFFF)


def args_key(events: list[Event]) -> bytes:
    if not 1 <= len(events) <= 16:
        raise ValueError("KEY carries 1..16 events")
    return bytes([len(events)]) + b"".join(e.pack() for e in events)


# --- the replies' data --------------------------------------------------------------------------------

@dataclass(frozen=True)
class BuildInfo:
    proto: int
    os: str
    caps: int
    switches: int
    width: int
    height: int
    chunks: int
    label: str
    ticks_per_s: int

    def has(self, name: str) -> bool:
        return bool(self.caps >> CAPS[name] & 1)


def parse_buildinfo(d: bytes) -> BuildInfo:
    if len(d) < 36 or d[:4] != b"DTB1":
        raise ValueError("not a BUILDINFO reply")
    proto, = struct.unpack(">H", d[4:6])
    os = f"{d[6]:x}.{d[7]:02x}"
    caps, = struct.unpack(">I", d[8:12])
    label = d[16:32].split(b"\0")[0].decode("ascii", "replace")
    tps, = struct.unpack(">I", d[32:36])
    return BuildInfo(proto, os, caps, d[12], d[13], d[14], d[15], label, tps)


@dataclass(frozen=True)
class Switch:
    index: int
    name: str
    value: int
    min: int
    max: int
    default: int


def parse_switch_info(d: bytes) -> Switch:
    k = d[0]
    name = d[1:9].split(b"\0")[0].decode("ascii", "replace")
    v, lo, hi, df = struct.unpack(">4I", d[9:25])
    return Switch(k, name, v, lo, hi, df)


def parse_switch_values(d: bytes) -> list[int]:
    return list(struct.unpack(f">{d[0]}I", d[1:1 + 4 * d[0]]))


def parse_counters(d: bytes) -> dict[str, int]:
    n = d[0]
    vals = struct.unpack(f">{n}I", d[1:1 + 4 * n])
    out = {COUNTER_NAMES[k] if k < len(COUNTER_NAMES) else f"c{k}": v for k, v in enumerate(vals)}
    tail = d[1 + 4 * n:]
    out["trace_total"], out["tick"], out["frames"] = struct.unpack(">3I", tail[:12])
    return out


@dataclass(frozen=True)
class TraceEntry:
    tick: int
    kind: str
    a: int
    b: int


def parse_trace(d: bytes) -> tuple[int, int, list[TraceEntry]]:
    """-> (total events so far, the first one's number, entries)"""
    total, first, n = struct.unpack(">IIB", d[:9])
    out = []
    for k in range(n):
        at, ev = struct.unpack(">II", d[9 + 8 * k:17 + 8 * k])
        out.append(TraceEntry(at, TRACE_KINDS.get(ev >> 24, str(ev >> 24)), ev >> 16 & 0xFF, ev & 0xFFFF))
    return total, first, out


@dataclass(frozen=True)
class State:
    frames: int
    tick: int
    ticks_per_s: int
    armed: bool
    destructive: bool
    seconds_left: int
    held: tuple[int, ...]
    pending: int
    panel: tuple[int, ...]
    machine_types: tuple[int, ...]
    inserts: tuple[tuple[int, int], ...]
    fb_front: int
    fb_back: int


def parse_state(d: bytes) -> State:
    frames, tick, tps = struct.unpack(">3I", d[:12])
    armed, flags = d[12], d[13]
    left, = struct.unpack(">H", d[14:16])
    lo, hi = struct.unpack(">II", d[16:24])
    held = tuple([c for c in range(1, 33) if lo >> (c - 1) & 1] + [c for c in range(33, 55) if hi >> (c - 33) & 1])
    pending = d[24]
    panel = tuple(d[25:32])
    types = tuple((b - 256 if b > 127 else b) for b in d[32:48])
    ins = tuple((d[48 + 2 * t], d[49 + 2 * t]) for t in range(16))
    front, back = struct.unpack(">II", d[80:88])
    return State(frames, tick, tps, bool(armed), bool(flags & 1), left, held, pending, panel, types, ins, front, back)


@dataclass(frozen=True)
class ScreenChunk:
    chunk: int
    chunks: int
    tries: int
    whole: bool
    seq: int
    hash: int
    data: bytes


def parse_screen(d: bytes) -> ScreenChunk:
    ch, n, tries, ok = d[0], d[1], d[2], d[3]
    seq, h = struct.unpack(">II", d[4:12])
    return ScreenChunk(ch, n, tries, bool(ok), seq, h, bytes(d[12:12 + CHUNK]) if ch != 0xFF else b"")


@dataclass(frozen=True)
class ArmState:
    armed: bool
    destructive: bool
    timeout_s: int


def parse_arm(d: bytes) -> ArmState:
    to, = struct.unpack(">I", d[2:6])
    return ArmState(bool(d[0]), bool(d[1] & 1), to)


def fnv1a(data: bytes) -> int:
    """the firmware's screen hash"""
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h
