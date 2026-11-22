"""The test channel in the simulator: the firmware's commands 33..43 as devtest.c (and prof.c) answer them, the same
statuses, the same arming and blacklist rules, over a toy UI whose screen changes with the keys.

The UI is a MODEL for the tools' tests, not the unit's: a page id drawn as a row of blocks on the top
band, the selected value as a bar, FUNC+SRC opening a "list" page (a framed box), encoder A moving the
value, YES / NO closing the list. Enough to prove that a press reaches the screen, that a turn moves a
value, that the mirror shows what was drawn, and that the safety rules hold, without a unit.

Faults: `no_channel` (a telemetry build: 33..43 answer status 2), `torn` (the first copy of each frame
is torn, the second whole), `no_dtim0` (PROFILE refuses the timer source: DMA timer 0 not running).

PROFILE's samples are a MODEL too: a fixed mix (the idle spin, the audio interrupt, a UI task, our C chunk)
drawn from a seeded generator at the asked rate in the simulator's time, so the host's reports and
comparisons can be tested; the numbers mean nothing about the unit.
"""

from __future__ import annotations

import random
import struct
import zlib
from dataclasses import dataclass, field
from typing import Callable

from . import protocol as P
from .keys import FUNC, FUNC_OK, SETTINGS
from .screen import H, W, from_rows

SWITCHES = [("HOLD", 0, 1, 1), ("LABELS", 0, 1, 1), ("ARMTIME", 30, 1800, 300)]
PAGES = {1: "TRIG", 2: "SRC", 3: "FLTR", 4: "AMP", 5: "FX", 6: "MOD"}
LIST_PAGE = 100
# remoteui-6, the build's identity (devtest.c id_step): the code the simulator 'runs', at the C chunk's address
SIM_CODE_LO, SIM_CODE, SIM_VERSION = 0x46AC0000, bytes(range(256)) * 4, b"0.48"

# PROFILE's model (prof.c): DMA timer 0 at 132 MHz, 1,500 audio frames a second, a 65,536-sample ring
BUS_HZ, CAP = 132_000_000, 65536
IDLE_PC, IDLE_TCB, UI_TCB, MIDI_TCB = 0x400CF246, 0x4243D900, 0x4059E1C0, 0x445E7764
# (pc, sr, tcb, weight): a quiet unit, about as the meter reads it (the audio interrupt about half the CPU)
PROFILE_MIX = ((IDLE_PC, 0x2000, IDLE_TCB, 44), (0x40025F10, 0x2500, IDLE_TCB, 30), (0x40026200, 0x2500, UI_TCB, 18),
               (0x40131FE0, 0x2000, UI_TCB, 4), (0x46A41000, 0x2000, UI_TCB, 2), (0x40121960, 0x2000, MIDI_TCB, 2))


@dataclass
class ChannelSim:
    clock: Callable[[], float]
    faults: frozenset[str] = frozenset()
    sw: list[int] = field(default_factory=lambda: [s[3] for s in SWITCHES])
    armed: bool = False
    glass_inverted: bool = False                                # the glass turns at the UI pass after ARM / DISARM
    remote: bool = True                                         # REMOTE CONTROL in USB CONFIG (usbcfg.c), default ON
    destructive: bool = False
    nonce: int = 0
    nonce_at: float = 0.0
    last_cmd: float = 0.0
    pending: list[tuple[float, int, int, int, int]] = field(default_factory=list)   # due, order, kind, code, value
    order: int = 0
    held: dict[int, float] = field(default_factory=dict)      # code -> release time
    panel: set[int] = field(default_factory=set)              # codes down as the UI sees them
    counters: list[int] = field(default_factory=lambda: [0] * 12)
    trace: list[tuple[int, int]] = field(default_factory=list)
    snap: bytes = b"\0" * 1024
    snap_seq: int = 0
    snap_whole: bool = True
    snap_tries: int = 1
    page: int = 2
    value: int = 64
    list_pos: int = 0
    events: list[str] = field(default_factory=list)            # what the UI received, in order
    prof: dict = field(default_factory=lambda: {"state": 0, "source": 0, "why": 0, "rate": 0, "t0": 0.0, "t1": 0.0,
                                                "samples": [], "starts": 0})
    profile_mix: tuple = PROFILE_MIX
    id_asked_at: float | None = None                           # the first BUILDINFO; the CRC is ready 0.2 s later

    # --- time ---------------------------------------------------------------------------------
    def tick(self) -> int:
        return int(self.clock() * 1000) & 0xFFFFFFFF

    def _trace(self, kind: int, a: int = 0, b: int = 0) -> None:
        self.trace.append((self.tick(), kind << 24 | (a & 0xFF) << 16 | (b & 0xFFFF)))

    def poll(self) -> None:
        """dt_poll: due events, releases, the auto-disarm"""
        now = self.clock()
        if self.armed and now - self.last_cmd >= self.sw[2]:
            self._disarm(1)
        if not self.remote:
            self._disarm(2)
        self.glass_inverted = self.armed
        if not self.armed:
            for c in sorted(self.held):
                self._button(c, False)
            self.held.clear()
            self.pending.clear()
            return
        while True:
            due = sorted(e for e in self.pending if e[0] <= now + 1e-9)
            if not due:
                break
            e = due[0]
            self.pending.remove(e)
            self._play(e[2], e[3], e[4], e[0])
        for c, at in sorted(self.held.items()):
            if at <= now + 1e-9:
                self._button(c, False)
                del self.held[c]
                self.counters[3] += 1
                self._trace(4, c)

    def _refuse(self, code: int) -> int:
        if self.destructive:
            return 0
        if code == SETTINGS:
            return 1
        if FUNC in self.panel and code != FUNC and code not in FUNC_OK:
            return 2
        if code == FUNC and any(c != FUNC and c not in FUNC_OK for c in self.held):
            return 3
        return 0

    def _play(self, kind: int, code: int, value: int, due: float) -> None:
        if kind == P.PRESS:
            why = self._refuse(code)
            if why:
                self.counters[1] += 1
                self._trace(7, code, why)
                return
            if code not in self.held:
                self._button(code, True)
            self.held[code] = due + value / 1000.0
            self.counters[2] += 1
            self._trace(3, code, value)
        elif kind == P.ENCODER:
            d = value - 0x10000 if value & 0x8000 else value
            self._encoder(code, d)
            self.counters[4] += 1
            self._trace(5, code, value)
        elif kind == P.RELEASE and code in self.held:
            self._button(code, False)
            del self.held[code]
            self.counters[3] += 1
            self._trace(4, code)

    def _disarm(self, why: int) -> None:
        if self.armed:
            self.armed = False
            self.destructive = False
            self.counters[7 if why == 1 else 6] += 1
            self._trace(2, why)

    # --- the toy UI ----------------------------------------------------------------------------
    def _button(self, code: int, down: bool) -> None:
        self.events.append(f"{'down' if down else 'up'} {code}")
        if down:
            self.panel.add(code)
        else:
            self.panel.discard(code)
            return
        if FUNC in self.panel and code == 2:
            self.page, self.list_pos = LIST_PAGE, 0
        elif code in PAGES and FUNC not in self.panel:
            self.page = code
        elif self.page == LIST_PAGE and code in (10, 12):
            self.page = 2

    def _encoder(self, enc: int, delta: int) -> None:
        self.events.append(f"enc {enc} {delta:+d}")
        if self.page == LIST_PAGE:
            self.list_pos = max(0, min(7, self.list_pos + delta))
        elif enc == 0:
            self.value = max(0, min(127, self.value + delta))

    def frame(self) -> bytes:
        px = [[False] * W for _ in range(H)]
        for k in range(8):                                      # the page id, in binary, top left
            if self.page >> k & 1:
                for y in range(2, 8):
                    for x in range(4 + 10 * k, 11 + 10 * k):
                        px[y][x] = True
        if self.page == LIST_PAGE:                              # the list: a frame, a highlighted row
            for x in range(20, 108):
                px[14][x] = px[58][x] = True
            for y in range(14, 59):
                px[y][20] = px[y][107] = True
            y0 = 17 + 5 * self.list_pos
            for y in range(y0, y0 + 4):
                for x in range(23, 105):
                    px[y][x] = True
        else:                                                   # the value, a bar
            for y in range(40, 46):
                for x in range(0, self.value):
                    px[y][x] = True
        return from_rows(px)

    # --- the commands ----------------------------------------------------------------------------
    def handle(self, cmd: int, a: bytes) -> tuple[int, bytes]:
        self.poll()
        if "no_channel" in self.faults:
            return P.ARGS, b""
        self.counters[0] += 1
        sub = a[0] if a else 0xFF
        if not self.remote and not P.off_ok(cmd, sub):
            self.counters[1] += 1
            return P.OFF, b""
        if cmd == P.BUILDINFO:
            if self.id_asked_at is None:
                self.id_asked_at = self.clock()
            ready = self.clock() - self.id_asked_at >= 0.2
            crc = zlib.crc32(SIM_CODE) if ready else 0
            return P.OK, (b"DTB1" + struct.pack(">HBBIBBBB", 1, 0x01, 0x12, 0x1FFF, len(SWITCHES), 128, 64, 8)
                          + b"sim".ljust(16, b"\0") + struct.pack(">IB", 1000, self.remote) + SIM_VERSION.ljust(8, b"\0")
                          + struct.pack(">IIIBII", SIM_CODE_LO, len(SIM_CODE), crc, ready, 26_400, 3_300))
        if cmd == P.SWITCH:
            k = a[1] if len(a) > 1 else 0xFF
            if sub == 0 and k < len(SWITCHES):
                n, lo, hi, df = SWITCHES[k]
                return P.OK, bytes([k]) + n.encode().ljust(8, b"\0") + struct.pack(">4I", self.sw[k], lo, hi, df)
            if sub == 1:
                return P.OK, bytes([len(SWITCHES)]) + struct.pack(f">{len(SWITCHES)}I", *self.sw)
            if sub == 2 and k < len(SWITCHES) and len(a) >= 6:
                v = struct.unpack(">I", a[2:6])[0]
                _, lo, hi, _ = SWITCHES[k]
                st = P.OK
                if lo <= v <= hi:
                    self.sw[k] = v
                    self.counters[10] += 1
                    self._trace(6, k, v)
                else:
                    st = P.RANGE
                return st, bytes([k]) + struct.pack(">I", self.sw[k])
            return P.ARGS, b""
        if cmd == P.PEEK:
            if len(a) < 5 or not 1 <= a[4] <= 128:
                return P.ARGS, b""
            addr = struct.unpack(">I", a[:4])[0]
            if not (0x40000000 <= addr and addr + a[4] <= 0x48000000 or 0x80000000 <= addr and addr + a[4] <= 0x80010000
                    or 0x4E6E7100 <= addr and addr + a[4] <= 0x4E6E8100):
                return P.RANGE, b""
            return P.OK, a[:4] + bytes((addr + k) & 0xFF for k in range(a[4]))
        if cmd == P.COUNTERS:
            if sub > 1:
                return P.ARGS, b""
            d = bytes([12]) + struct.pack(">12I", *self.counters) + struct.pack(">3I", len(self.trace), self.tick(), int(self.clock() * 1500))
            if sub == 1:
                self.counters = [0] * 12
                self._trace(8)
            return P.OK, d
        if cmd == P.TRACE:
            since = struct.unpack(">I", a[:4])[0] if len(a) >= 4 else 0
            total = len(self.trace)
            if total - since > 64 or since > total:
                since = max(0, total - 64)
            ent = self.trace[since:since + 16]
            return P.OK, struct.pack(">IIB", total, since, len(ent)) + b"".join(struct.pack(">II", *e) for e in ent)
        if cmd == P.STATE:
            lo = sum(1 << (c - 1) for c in self.held if c <= 32)
            hi = sum(1 << (c - 33) for c in self.held if c > 32)
            left = max(0, int(self.sw[2] - (self.clock() - self.last_cmd))) if self.armed else 0
            panel = [0] * 7
            for c in self.panel:
                ch, bit = ((c - 1) >> 3, (c - 1) & 7) if c <= 48 else (6, (1, 0, 4, 5, 6, 7)[c - 49])
                panel[ch] |= 1 << bit
            return P.OK, (struct.pack(">3IBBHIIB", int(self.clock() * 1500), self.tick(), 1000, self.armed, self.destructive,
                                      left, lo, hi, len(self.pending)) + bytes(panel) + bytes([1] * 16) + bytes(32)
                          + struct.pack(">II", 0x44623BC8, 0x44623FC8) + bytes([self.glass_inverted]))
        if cmd == P.SCREEN:
            if len(a) < 2 or sub > 3 or not (a[1] < 8 or a[1] == 0xFF):
                return P.ARGS, b""
            if sub & 2 or not self.snap_seq:
                self.snap = self.frame()
                self.snap_seq += 1
                self.counters[8] += 1
                self.snap_tries = 2 if "torn" in self.faults else 1
                if "torn" in self.faults:
                    self.counters[9] += 1
            ch = a[1]
            head = bytes([ch, 8, self.snap_tries, 1]) + struct.pack(">II", self.snap_seq, P.fnv1a(self.snap))
            return P.OK, head + (self.snap[128 * ch:128 * ch + 128] if ch < 8 else b"")
        if cmd == P.ARM:
            now = self.clock()
            st, d = P.OK, b""
            if sub == 0:
                self.nonce = (int(now * 1000) * 0x9E3779B1 ^ self.counters[0] * 0x85EBCA6B | 1) & 0xFFFFFFFF
                self.nonce_at = now
                d = struct.pack(">I", self.nonce)
            elif sub == 1:
                ok = (len(a) >= 10 and a[1:5] == b"ARM!" and self.nonce and struct.unpack(">I", a[5:9])[0] == self.nonce
                      and now - self.nonce_at <= 10)
                self.nonce = 0
                if not ok:
                    st = P.REFUSED
                    self.counters[1] += 1
                else:
                    self.destructive = bool(a[9] & 1)
                    self.last_cmd = now
                    if not self.armed:
                        self.armed = True
                        self.counters[5] += 1
                        self._trace(1, int(self.destructive))
            elif sub == 2:
                self._disarm(0)
            elif sub != 3:
                st = P.ARGS
            if sub == 3 and self.armed:
                self.last_cmd = now
            return st, d + bytes([self.armed, self.destructive]) + struct.pack(">I", self.sw[2])
        if cmd == P.KEY:
            return self._keys(a)
        if cmd == P.PROFILE:
            return self._profile(a)
        return P.ARGS, b""

    # --- PROFILE (prof.c) -------------------------------------------------------------------------
    def _prof_fill(self) -> None:
        """the samples the model's timer has taken by now (the ring stops when full)"""
        pr = self.prof
        if pr["state"] != 1:
            return
        now = self.clock()
        want = min(CAP, int((now - pr["t0"]) * pr["rate"]))
        rng = random.Random(pr["starts"] * 7919 + len(pr["samples"]))
        mix = [m for m in self.profile_mix if pr["source"] == P.PROF_TIMER or m[1] >> 8 & 7 < 5]   # AUDIO: no level 5
        weights = [m[3] for m in mix]
        while len(pr["samples"]) < want:
            pc, sr, tcb, _w = rng.choices(mix, weights)[0]
            pr["samples"].append((pc + 2 * rng.randrange(0, 8) * (pc != IDLE_PC), tcb, sr, rng.randrange(0, 200)))
        if len(pr["samples"]) >= CAP:
            pr["state"], pr["t1"] = 2, pr["t0"] + CAP / pr["rate"]

    def _prof_status(self) -> bytes:
        pr = self.prof
        running = pr["state"] == 1
        t_end = self.clock() if running or not pr["starts"] else pr["t1"]
        n = len(pr["samples"])
        period = BUS_HZ // pr["rate"] if pr["rate"] else 0
        dtmr = 0x0003 | (0x10 if running and pr["source"] == P.PROF_TIMER else 0)
        if "no_dtim0" in self.faults:
            dtmr = 0
        words = (n, CAP, period, int(pr["t0"] * BUS_HZ) & 0xFFFFFFFF, int(t_end * BUS_HZ) & 0xFFFFFFFF,
                 int(pr["t0"] * 1500), int(t_end * 1500), n * 140 if pr["source"] == P.PROF_TIMER else 0, n, 0,
                 1200, 0, dtmr << 16 | 2, 0xFFFFFFFF, (6 if running else 0) << 24 | (0 if running else 1) << 16 | pr["starts"],
                 0x46A42000 if running else 0x40001252, 0x47700100)
        return bytes([pr["state"], pr["source"], pr["why"], P.PROF_RECORD]) + struct.pack(">17I", *words)

    def _profile(self, a: bytes) -> tuple[int, bytes]:
        pr = self.prof
        self._prof_fill()
        sub = a[0] if a else 0xFF
        if sub == P.PROF_STATUS:
            return P.OK, self._prof_status()
        if sub == P.PROF_START:
            if len(a) < 6:
                return P.ARGS, self._prof_status()
            if pr["state"] == 1:
                return P.BUSY, self._prof_status()
            src, rate = a[1], struct.unpack(">I", a[2:6])[0]
            if src not in (P.PROF_TIMER, P.PROF_AUDIO):
                pr["why"] = 7
                return P.ARGS, self._prof_status()
            if not 10 <= rate <= (10000 if src == P.PROF_TIMER else 1500):
                pr["why"] = 6
                return P.ARGS, self._prof_status()
            if src == P.PROF_TIMER and "no_dtim0" in self.faults:
                pr["why"] = 1
                return P.RANGE, self._prof_status()
            if src == P.PROF_AUDIO:
                rate = 1500 // (1500 // rate)
            pr.update(state=1, source=src, why=0, rate=rate, t0=self.clock(), t1=0.0, samples=[], starts=pr["starts"] + 1)
            return P.OK, self._prof_status()
        if sub == P.PROF_STOP:
            if pr["state"] == 1:
                pr["state"], pr["t1"] = 3, self.clock()
            return P.OK, self._prof_status()
        if sub == P.PROF_CLEAR:
            if pr["state"] == 1:
                return P.BUSY, self._prof_status()
            pr["samples"], pr["state"] = [], 0
            return P.OK, self._prof_status()
        if sub == P.PROF_READ and len(a) >= 5:
            since = min(struct.unpack(">I", a[1:5])[0], len(pr["samples"]))
            got = pr["samples"][since:since + P.PROF_PER_READ]
            return P.OK, (struct.pack(">IIB", len(pr["samples"]), since, len(got))
                          + b"".join(struct.pack(">IIHH", *g) for g in got))
        return P.ARGS, b""

    def _keys(self, a: bytes) -> tuple[int, bytes]:
        if not self.armed:
            return P.UNARMED, b""
        m = a[0] if a else 0
        if not 1 <= m <= 16 or len(a) < 1 + 6 * m:
            return P.ARGS, b""
        ev = [struct.unpack(">BBHH", a[1 + 6 * j:7 + 6 * j]) for j in range(m)]
        for j, (kind, code, at, val) in enumerate(ev):
            sval = val - 0x10000 if val & 0x8000 else val
            bad = at > 10000 or kind not in (1, 2, 3)
            if kind in (1, 3):
                bad |= not 1 <= code <= 54 or (kind == 1 and not 1 <= val <= 10000)
            if kind == 2:
                bad |= code > 8 or not -30 <= sval <= 30 or sval == 0
            if bad:
                return P.ARGS, bytes([j])
            if kind == 1 and code == SETTINGS and not self.destructive:
                self.counters[1] += 1
                self._trace(7, code, 1)
                return P.REFUSED, bytes([j])
        free = 16 - len(self.pending)
        if free < m:
            return P.BUSY, bytes([free])
        now = self.clock()
        for kind, code, at, val in ev:
            self.pending.append((now + at / 1000.0, self.order, kind, code, val))
            self.order += 1
        self.last_cmd = now
        return P.OK, bytes([m, free - m])
