"""The test channel's client: every command as a method, typed results (protocol.py), the build's
capabilities checked first so an older build or stock firmware gets a clear message, not a timeout.

    from dn2tools.unit import MidoUnit
    from dn2tools.channel import TestChannel
    ch = TestChannel(MidoUnit("Elektron Digitone II"))
    print(ch.info().label, ch.state().machine_types)
    png = ch.screen()                  # 1,024 bytes, column-major (screen.py decodes them)
"""

from __future__ import annotations

import struct

from . import protocol as P
from .unit import NoTestChannel, StatusError, Unit


class TestChannel:
    """the commands 33..42 over a Unit (the real one through mido, or the simulator)"""

    __test__ = False                             # pytest: not a test class

    def __init__(self, unit: Unit):
        self.unit = unit
        self._info: P.BuildInfo | None = None

    # --- identity -------------------------------------------------------------------------------
    def info(self) -> P.BuildInfo:
        if self._info is None:
            self._info = P.parse_buildinfo(self.unit.call(P.BUILDINFO))
            if self._info.proto != 1:
                raise NoTestChannel(f"test channel protocol {self._info.proto}: this dn2tools speaks 1; update it")
        return self._info

    def require(self, cap: str) -> None:
        if not self.info().has(cap):
            raise NoTestChannel(f"the build on the unit ({self.info().label}) has no {cap}: flash a newer test build")

    # --- switches -------------------------------------------------------------------------------
    def switches(self) -> list[P.Switch]:
        self.require("SWITCH")
        return [P.parse_switch_info(self.unit.call(P.SWITCH, P.args_switch_info(k))) for k in range(self.info().switches)]

    def switch_values(self) -> list[int]:
        self.require("SWITCH")
        return P.parse_switch_values(self.unit.call(P.SWITCH, P.args_switch_get()))

    def set_switch(self, name: str, value: int) -> int:
        """-> the value the unit now holds; ValueError if the name is unknown or the value out of its bounds"""
        sw = {s.name.upper(): s for s in self.switches()}
        s = sw.get(name.upper())
        if s is None:
            raise ValueError(f"no switch {name!r} (the build's: {', '.join(sw) or 'none'})")
        if not s.min <= value <= s.max:
            raise ValueError(f"{s.name} takes {s.min}..{s.max}")
        d = self.unit.call(P.SWITCH, P.args_switch_set(s.index, value))
        return struct.unpack(">I", d[1:5])[0]

    # --- reads ----------------------------------------------------------------------------------
    def peek(self, address: int, length: int) -> bytes:
        self.require("PEEK")
        out = bytearray()
        while len(out) < length:
            n = min(128, length - len(out))
            d = self.unit.call(P.PEEK, P.args_peek(address + len(out), n))
            out += d[4:4 + n]
        return bytes(out)

    def counters(self, reset: bool = False) -> dict[str, int]:
        self.require("COUNTERS")
        return P.parse_counters(self.unit.call(P.COUNTERS, P.args_counters(reset)))

    def trace(self, since: int = 0) -> tuple[int, list[P.TraceEntry]]:
        """-> (the next SINCE, the entries since SINCE: the ring keeps the last 64)"""
        self.require("TRACE")
        out: list[P.TraceEntry] = []
        while True:
            total, first, entries = P.parse_trace(self.unit.call(P.TRACE, P.args_trace(since)))
            out += entries
            since = first + len(entries)
            if not entries or since >= total:
                return since, out

    def state(self) -> P.State:
        self.require("STATE")
        return P.parse_state(self.unit.call(P.STATE))

    # --- the screen -----------------------------------------------------------------------------
    def screen_hash(self, drawing: bool = False) -> tuple[int, bool]:
        """-> (a fresh frame's hash, whether it was whole); the frame stays on the unit for screen_chunks"""
        self.require("SCREEN")
        c = P.parse_screen(self.unit.call(P.SCREEN, P.args_screen(0xFF, drawing, fresh=True)))
        return c.hash, c.whole

    def screen(self, drawing: bool = False, fresh: bool = True) -> bytes:
        """-> the 1,024 bytes of the frame on the glass (or, DRAWING, the one being drawn): copied once, served in 8 chunks"""
        self.require("SCREEN")
        first = P.parse_screen(self.unit.call(P.SCREEN, P.args_screen(0, drawing, fresh)))
        if not first.whole:
            raise StatusError(P.SCREEN, P.OK, b"torn")
        data = bytearray(first.data)
        for k in range(1, first.chunks):
            c = P.parse_screen(self.unit.call(P.SCREEN, P.args_screen(k, drawing, False)))
            if c.seq != first.seq:                  # another reader took a new frame: start again
                return self.screen(drawing, True)
            data += c.data
        if P.fnv1a(bytes(data)) != first.hash:
            raise StatusError(P.SCREEN, P.OK, b"hash")
        return bytes(data)

    # --- arming and keys ------------------------------------------------------------------------
    def arm(self, destructive: bool = False) -> P.ArmState:
        self.require("ARM")
        d = self.unit.call(P.ARM, P.args_arm_ask())
        nonce = struct.unpack(">I", d[:4])[0]
        return P.parse_arm(self.unit.call(P.ARM, P.args_arm_confirm(nonce, destructive)))

    def disarm(self) -> P.ArmState:
        self.require("ARM")
        return P.parse_arm(self.unit.call(P.ARM, P.args_disarm()))

    def arm_status(self) -> P.ArmState:
        """also keeps an armed unit armed (it counts as a command)"""
        self.require("ARM")
        return P.parse_arm(self.unit.call(P.ARM, P.args_arm_status()))

    def send_events(self, events: list[P.Event]) -> int:
        """-> events accepted; StatusError 3 not armed, 4 refused, 5 queue full"""
        self.require("KEY")
        return self.unit.call(P.KEY, P.args_key(events))[0]
