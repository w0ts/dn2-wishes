"""The unit as the tools see it: notes and the test channel's SysEx, nothing else.

What may be sent is fixed here, not in the scenarios (never to write to the unit's firmware or
storage): note on / note off, the controllers ALLOWED_CC (sustain, all sound off, all notes off), a
sound parameter's CC only from a CC map the user gives, and SysEx only the commands in
protocol.ALLOWED: the read-only ones (HELLO, TLM, BUILDINFO, PEEK, COUNTERS, TRACE, STATE, SCREEN) and
SWITCH (whitelisted RAM words), ARM and KEY (keys.py, disarmed until armed). No NRPN, no program
change, no other SysEx command: the sample link's writes and the library's commands are refused here.
"""

from __future__ import annotations

import struct
import time
from abc import ABC, abstractmethod

from . import protocol as P
from .frame import Telemetry, decode

HEADER = P.HEADER
CMD_HELLO = P.HELLO
ALLOWED_SYSEX = P.ALLOWED
ALLOWED_CC = frozenset({64, 120, 123})          # sustain, all sound off, all notes off
STATUS_UNKNOWN = P.ARGS


class Refused(Exception):
    """the tools will not send this (it could change the unit)"""


class NoTestChannel(Exception):
    """the firmware on the unit does not answer this command: stock firmware, or a build without it"""


class StatusError(Exception):
    """the unit answered with a non-zero status"""

    def __init__(self, cmd: int, status: int, data: bytes = b""):
        self.cmd, self.status, self.data = cmd, status, data
        super().__init__(f"{P.NAMES.get(cmd, cmd)}: status {status} ({P.STATUS_TEXT.get(status, '?')})")


def request(seq: int, cmd: int, payload: bytes = b"") -> bytes:
    if cmd not in ALLOWED_SYSEX:
        raise Refused(f"SysEx command {cmd} is not one the tools send (allowed: {sorted(ALLOWED_SYSEX)}): "
                      f"it could change the unit's storage")
    return P.encode(seq, cmd, payload)


def parse(sx: bytes) -> dict | None:
    r = P.decode(sx)
    return None if r is None else {"seq": r.seq, "cmd": r.cmd, "status": r.status, "payload": r.data}


def check_note(ch: int, note: int, vel: int = 100) -> None:
    if not (0 <= ch <= 15 and 0 <= note <= 127 and 0 <= vel <= 127):
        raise Refused(f"note ch {ch} note {note} vel {vel} out of range")


class Unit(ABC):
    """notes and SysEx; `wait` is real time on the unit, virtual time on the simulator"""

    @abstractmethod
    def _note(self, on: bool, ch: int, note: int, vel: int) -> None: ...

    @abstractmethod
    def _cc(self, ch: int, cc: int, value: int) -> None: ...

    @abstractmethod
    def _exchange(self, cmd: int, payload: bytes) -> P.Reply | None:
        """one request out (already allowed), its reply in; None: no answer"""

    @abstractmethod
    def wait(self, seconds: float) -> None: ...

    def close(self) -> None:
        pass

    param_cc: frozenset = frozenset()                  # controllers the user allowed in a --cc-map file (none by default)
    last_cost: tuple[float, int, int] = (0.0, 0, 0)    # the last command's round trip (s), bytes out, bytes in

    def clock(self) -> float:
        return time.monotonic()

    def _call(self, cmd: int, payload: bytes = b"", ok: tuple[int, ...] = (P.OK,)) -> bytes:
        if cmd not in ALLOWED_SYSEX:
            raise Refused(f"SysEx command {cmd} is not one the tools send")
        r = self._exchange(cmd, payload)
        if r is None:
            raise NoTestChannel(f"no answer to {P.NAMES.get(cmd, cmd)}: stock firmware (it ignores this SysEx), "
                                f"USB CONFIG not USB MIDI / Overbridge, or another program holds the port")
        if r.status == P.ARGS and cmd in (P.TLM, P.BUILDINFO):
            raise NoTestChannel(f"the firmware does not know {P.NAMES[cmd]} ({cmd}): flash a test build "
                                f"(docs/remote-ui.md, Quickstart)")
        if r.status not in ok:
            raise StatusError(cmd, r.status, r.data)
        return r.data

    def call(self, cmd: int, payload: bytes = b"", ok: tuple[int, ...] = (P.OK,)) -> bytes:
        return self._call(cmd, payload, ok)

    def param(self, ch: int, cc: int, value: int) -> None:
        """a sound parameter's CC, only one the user listed in the CC map (it changes the track's sound in place)"""
        if cc not in self.param_cc:
            raise Refused(f"controller {cc} is not in the user's CC map")
        self._cc(ch, cc, value)

    def note_on(self, ch: int, note: int, vel: int = 100) -> None:
        check_note(ch, note, vel)
        self._note(True, ch, note, vel or 1)

    def note_off(self, ch: int, note: int) -> None:
        check_note(ch, note)
        self._note(False, ch, note, 0)

    def cc(self, ch: int, cc: int, value: int) -> None:
        if cc not in ALLOWED_CC:
            raise Refused(f"controller {cc} could change a sound: only {sorted(ALLOWED_CC)} are sent")
        self._cc(ch, cc, value)

    def all_notes_off(self) -> None:
        for ch in range(16):
            self.cc(ch, 123, 0)

    def hello(self) -> int:
        return struct.unpack(">H", self._call(CMD_HELLO)[:2])[0]

    def tlm(self) -> Telemetry:
        return decode(self._call(P.TLM))


def find_port(names: list[str], want: str) -> str | None:
    """the first port whose name holds WANT (case blind)"""
    hits = [n for n in names if want.lower() in n.lower()]
    return hits[0] if hits else None


class MidoUnit(Unit):
    """the Digitone II (or the simulator's virtual ports) through mido; one SysEx out, SysEx in until it answers"""

    def __init__(self, want: str = "Elektron Digitone II", timeout: float = 1.0, tries: int = 3):
        try:
            import mido                             # the 'mido' and 'python-rtmidi' packages (pyproject dependencies)
        except ImportError as e:
            raise SystemExit("dn2tools needs mido and python-rtmidi: pip install ./tools/dn2tools") from e
        self.mido = mido
        out, inp = find_port(mido.get_output_names(), want), find_port(mido.get_input_names(), want)
        if not out or not inp:
            raise SystemExit(f"no MIDI port with {want!r} in its name: is the Digitone II on and on USB, USB CONFIG "
                             f"USB MIDI or Overbridge? (ports: {', '.join(mido.get_output_names()) or 'none'}; "
                             f"--port picks another)")
        self.out = mido.open_output(out)
        self.inp = mido.open_input(inp)
        self.name = out
        self.seq = 0x500
        self.timeout, self.tries = timeout, tries

    played = False                                  # notes went out: close() sends all-notes-off

    def _note(self, on: bool, ch: int, note: int, vel: int) -> None:
        self.played = True
        self.out.send(self.mido.Message("note_on" if on else "note_off", channel=ch, note=note, velocity=vel))

    def _cc(self, ch: int, cc: int, value: int) -> None:
        self.out.send(self.mido.Message("control_change", channel=ch, control=cc, value=value))

    def _exchange(self, cmd: int, payload: bytes) -> P.Reply | None:
        for _ in range(self.tries):
            self.seq = (self.seq + 1) & 0xFFFF or 1
            msg = request(self.seq, cmd, payload)
            t0 = time.perf_counter()
            self.out.send(self.mido.Message("sysex", data=msg[1:-1]))
            end = time.time() + self.timeout
            while time.time() < end:
                for m in self.inp.iter_pending():
                    if m.type != "sysex":
                        continue
                    raw = bytes([0xF0]) + bytes(m.data) + bytes([0xF7])
                    r = P.decode(raw)
                    if r and r.seq == self.seq and r.cmd == cmd | 0x80:
                        self.last_cost = (time.perf_counter() - t0, len(msg), len(raw))
                        return r
                time.sleep(0.0005)
        return None

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def close(self) -> None:
        """all-notes-off if notes were played; the ports closed in a thread given 2 s (a CoreMIDI close was seen
        to hang for minutes on macOS, 2026-11-11, after every reply had arrived)"""
        import threading

        def shut() -> None:
            try:
                if self.played:
                    self.all_notes_off()
            finally:
                self.inp.close()
                self.out.close()
        t = threading.Thread(target=shut, daemon=True)
        t.start()
        t.join(2.0)
