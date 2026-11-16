"""The test channel's wire format, pure Python and no I/O (docs/remote-ui-protocol.md is the spec;
this module is its executable form and the golden tests hold the two together).

    request  F0 00 20 3C 7D 01 <pack7: u16 seq, u8 cmd, args> F7
    reply    F0 00 20 3C 7D 01 <pack7: u16 seq, u8 cmd | 0x80, u8 status, data> F7

All numbers big-endian. Commands 1 (HELLO) and 32 (TLM) come from the sample link and the telemetry
build; 33..43 are the test channel (a test build only; 43 PROFILE since remoteui-5).
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
PROFILE = 43

NAMES = {HELLO: "HELLO", TLM: "TLM", BUILDINFO: "BUILDINFO", SWITCH: "SWITCH", PEEK: "PEEK", COUNTERS: "COUNTERS",
         TRACE: "TRACE", STATE: "STATE", SCREEN: "SCREEN", ARM: "ARM", KEY: "KEY", PROFILE: "PROFILE"}

# The only commands a host built on this package sends. Everything else on this SysEx channel (the
# sample link's WRITE, BEGIN, END, FORGET, LOAD, the library, ERASE MOD DATA ...) can change the unit's
# storage, and is refused before it is encoded (unit.request).
READ_ONLY = frozenset({HELLO, TLM, BUILDINFO, PEEK, COUNTERS, TRACE, STATE, SCREEN})
CONTROL = frozenset({SWITCH, ARM, KEY, PROFILE})  # RAM words the firmware whitelists, the arm handshake, keys,
                                                  # the profiler (its own RAM and DMA timer 0's compare)
ALLOWED = READ_ONLY | CONTROL

# statuses
OK, ARGS, UNARMED, REFUSED, BUSY, RANGE, OFF = 0, 2, 3, 4, 5, 6, 7
STATUS_TEXT = {OK: "ok", 1: "failed", ARGS: "bad arguments or unknown command", UNARMED: "not armed",
               REFUSED: "refused (blacklist or handshake)", BUSY: "busy (queue full)", RANGE: "outside the whitelist",
               OFF: "REMOTE CONTROL is OFF on the unit (SETTINGS > SYSTEM > USB CONFIG)"}


def off_ok(cmd: int, sub: int) -> bool:
    """what still answers while REMOTE CONTROL is OFF (csrc/devtest/devtest.c off_ok): the reads that show nothing
    of the screen or memory, and ARM's disarm and status"""
    return cmd in (BUILDINFO, COUNTERS, TRACE, STATE) or (cmd == SWITCH and sub <= 1) or (cmd == ARM and sub in (2, 3))

# capability bits (BUILDINFO)
CAPS = {"TLM": 0, "BUILDINFO": 1, "SWITCH": 2, "PEEK": 3, "COUNTERS": 4, "TRACE": 5, "STATE": 6, "SCREEN": 7,
        "ARM": 8, "KEY": 9, "PROFILE": 10, "INVERT": 11, "USBCFG": 12}

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
    remote: bool | None = None       # REMOTE CONTROL in USB CONFIG (the USBCFG capability); None: a build before it
    identity: BuildId | None = None             # remoteui-6 and later; None from an older build

    def has(self, name: str) -> bool:
        return bool(self.caps >> CAPS[name] & 1)


@dataclass(frozen=True)
class BuildId:
    """remoteui-6: the build's identity (csrc/devtest/devtest.c id_step): the mod's VERSION, and a CRC-32 (zlib's)
    of the C chunk's code and rodata, [code_lo, code_lo + code_len), computed by the unit after the first
    BUILDINFO asks; `crc` is meaningful only once `ready`. `ticks`: DMA timer 0 ticks the CRC took so far
    (132 MHz measured, preemption included), `slice_max` the longest of its slices."""
    mod_version: str
    code_lo: int
    code_len: int
    crc: int
    ready: bool
    ticks: int
    slice_max: int


def parse_buildinfo(d: bytes) -> BuildInfo:
    if len(d) < 36 or d[:4] != b"DTB1":
        raise ValueError("not a BUILDINFO reply")
    proto, = struct.unpack(">H", d[4:6])
    os = f"{d[6]:x}.{d[7]:02x}"
    caps, = struct.unpack(">I", d[8:12])
    label = d[16:32].split(b"\0")[0].decode("ascii", "replace")
    tps, = struct.unpack(">I", d[32:36])
    remote = bool(d[36]) if len(d) > 36 else None
    ident = None
    if len(d) >= 66:                            # remoteui-6: the identity after the remote byte
        lo, n, crc = struct.unpack(">III", d[45:57])
        ticks, smax = struct.unpack(">II", d[58:66])
        ident = BuildId(d[37:45].split(b"\0")[0].decode("ascii", "replace"), lo, n, crc, bool(d[57]), ticks, smax)
    return BuildInfo(proto, os, caps, d[12], d[13], d[14], d[15], label, tps, remote, ident)


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
    glass_inverted: bool = False     # the glass shows the frames inverted (armed); SCREEN still reads them upright


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
    inverted = len(d) > 88 and bool(d[88])          # byte 88 since the INVERT capability (older builds: absent)
    return State(frames, tick, tps, bool(armed), bool(flags & 1), left, held, pending, panel, types, ins, front, back,
                 inverted)


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


# --- PROFILE (43): the CPU profiler (csrc/devtest/prof.c) -------------------------------------------------

PROF_STATUS, PROF_START, PROF_STOP, PROF_CLEAR, PROF_READ = 0, 1, 2, 3, 4
PROF_TIMER, PROF_AUDIO = 1, 2                     # the sources
PROF_STATES = {0: "off", 1: "running", 2: "full", 3: "stopped"}
PROF_SOURCES = {0: "none", 1: "timer", 2: "audio"}
PROF_WHY = {0: "", 1: "DMA timer 0 is not running from the bus clock", 2: "DMA timer 0 restarts at its reference (FRR)",
            3: "DMA timer 0's reference interrupt or DMA is in use", 4: "its interrupt source is set up or unmasked",
            5: "vector 96 is not the stock default", 6: "rate out of range (timer 10..10000, audio 10..1500)",
            7: "unknown source"}
PROF_RECORD = 12                                  # u32 pc, u32 tcb, u16 sr, u16 late
PROF_PER_READ = 12                                # records a READ returns at most (9 + 144 bytes)


def args_profile_status() -> bytes:
    return bytes([PROF_STATUS])


def args_profile_start(source: int, rate_hz: int) -> bytes:
    return bytes([PROF_START, source]) + struct.pack(">I", rate_hz)


def args_profile_stop() -> bytes:
    return bytes([PROF_STOP])


def args_profile_clear() -> bytes:
    return bytes([PROF_CLEAR])


def args_profile_read(since: int) -> bytes:
    return bytes([PROF_READ]) + struct.pack(">I", since & 0xFFFFFFFF)


@dataclass(frozen=True)
class ProfileStatus:
    state: str
    source: str
    why: int
    record_bytes: int
    samples: int
    capacity: int
    period_ticks: int
    t_start: int                                  # DMA timer 0 (132 MHz, wraps every 32.5 s)
    t_now: int                                    # now while running, else at the stop
    f_start: int                                  # audio frames
    f_now: int
    isr_ticks: int                                # the timer handler's own time, summed
    fires: int
    late: int                                     # samples taken more than a period late
    late_max: int
    dropped: int
    dtim0: int                                    # DTMR0 << 16 | DTXMR0 << 8 | DTER0
    dtrr0: int
    intc: int                                     # ICR32 << 24 | IMRH bit 0 << 16 | starts
    vector96: int
    ring: int

    @property
    def why_text(self) -> str:
        return PROF_WHY.get(self.why, str(self.why))


def parse_profile_status(d: bytes) -> ProfileStatus:
    if len(d) < 72:
        raise ValueError("not a PROFILE status")
    w = struct.unpack(">17I", d[4:72])
    return ProfileStatus(PROF_STATES.get(d[0], str(d[0])), PROF_SOURCES.get(d[1], str(d[1])), d[2], d[3], *w)


@dataclass(frozen=True)
class Sample:
    pc: int
    tcb: int
    sr: int
    late: int                                     # DMA timer 0 ticks the sample came after it was due (65535: or more)

    @property
    def ipl(self) -> int:
        return self.sr >> 8 & 7


def parse_profile_read(d: bytes) -> tuple[int, int, list[Sample]]:
    """-> (samples recorded so far, the first one's index, samples)"""
    total, first, n = struct.unpack(">IIB", d[:9])
    out = [Sample(*struct.unpack(">IIHH", d[9 + PROF_RECORD * k:9 + PROF_RECORD * (k + 1)])) for k in range(n)]
    return total, first, out


def fnv1a(data: bytes) -> int:
    """the firmware's screen hash"""
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h
