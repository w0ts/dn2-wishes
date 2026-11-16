"""Pressing the unit's keys and turning its encoders, remotely (a test build, armed first).

    from dn2tools.keys import Keys
    k = Keys(TestChannel(MidoUnit()))
    k.arm()                                     # the handshake; the unit disarms itself after ARMTIME s of silence
    k.press("FUNC+SRC")                         # FUNC held, SRC tapped, FUNC let go
    k.turn("A", +5)                             # encoder A five detents
    k.turn("A", -3, push=True)                  # with its push held (how a value moves in a menu)
    k.hold("PLAY", 600)
    k.wait_for_screen(lambda f: ..., timeout=2)
    k.disarm()

Every event is scheduled by the unit itself: a press carries its hold time and the unit lets the key go
at that time, so a host that dies mid-chord leaves no key down (the unit also lets every key go when
it disarms). Every event is appended to the event log (JSON lines).

Safety, checked here AND in the firmware (devtest.c refuse()):
  * SETTINGS is refused: the system menu holds the project manager, OS upgrade, format and the sample
    manager.
  * With FUNC held, only the page keys (TRIG SRC FLTR AMP FX MOD), the arrows, PLAY, STOP, PAGE and the
    encoder pushes may go down: FUNC with YES, NO, PRESET, PTN, SONG, RECORD, ... (the saving and
    clearing chords) is refused, and so is FUNC while such a key is held.
  * `allow_destructive=True` (dn2ui --allow-destructive) lifts both, for the person at the unit who
    knows what the next keys do. It is dangerous: it can save over a project or start an OS update.
Driving the UI changes the project in RAM like any key press: use a scratch project.
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Callable

from . import protocol as P
from .channel import TestChannel
from .unit import StatusError

CODES: dict[str, int] = {
    "TRIG": 1, "SRC": 2, "FLTR": 3, "AMP": 4, "FX": 5, "MOD": 6, "PRESET": 7, "SETTINGS": 8,
    "TEMPO": 9, "YES": 10, "UP": 11, "NO": 12, "LEFT": 13, "DOWN": 14, "RIGHT": 15, "TRK": 16,
    "FUNC": 17, "KEYBOARD": 18, "RECORD": 19, "PLAY": 20, "STOP": 21, "PAGE": 22, "PTN": 23, "SONG": 24,
    **{f"T{k}": 24 + k for k in range(1, 17)},
    **{f"PUSH{c}": 41 + i for i, c in enumerate("ABCDEFGH")},
    "LEVEL": 49, "VOICE": 50, "ARP": 51, "PLUS": 52, "STACK": 53, "MINUS": 54,
}
ALIASES = {"SYN": "SRC", "FILTER": "FLTR", "REC": "RECORD", "PATTERN": "PTN", "TRACK": "TRK", "SHIFT": "FUNC",
           **{f"TRIG{k}": f"T{k}" for k in range(1, 17)}}
NAMES = {v: k for k, v in CODES.items()}
ENCODERS = {**{c: i for i, c in enumerate("ABCDEFGH")}, "LEVEL": 8}

SETTINGS = CODES["SETTINGS"]
FUNC = CODES["FUNC"]
FUNC_OK = frozenset({1, 2, 3, 4, 5, 6, 11, 13, 14, 15, 20, 21, 22, *range(41, 49)})   # = devtest.c func_ok

TAP_MS = 80             # a tap: well inside the UI's hold threshold
GAP_MS = 60             # between a modifier going down and the next key
ENC_STEP = 30           # the firmware flushes at most +-30 detents at once
ENC_GAP_MS = 25


class Blocked(Exception):
    """the key or chord is on the destructive blacklist"""


def code_of(name: str) -> int:
    n = name.strip().upper().replace(" ", "")
    n = ALIASES.get(n, n)
    if n not in CODES:
        raise ValueError(f"no key {name!r} (keys: {', '.join(CODES)})")
    return CODES[n]


def encoder_of(name: str | int) -> int:
    if isinstance(name, int):
        if not 0 <= name <= 8:
            raise ValueError("encoders are 0..8 (A..H, LEVEL)")
        return name
    n = name.strip().upper()
    if n not in ENCODERS:
        raise ValueError(f"no encoder {name!r} (A..H, LEVEL)")
    return ENCODERS[n]


def check(down_before: frozenset[int], code: int, allow_destructive: bool = False) -> str | None:
    """-> why CODE may not go down while DOWN_BEFORE are held, or None (devtest.c refuse(), the same rules)"""
    if allow_destructive:
        return None
    if code == SETTINGS:
        return "SETTINGS (the system menu: project manager, OS upgrade, format) is refused"
    if FUNC in down_before and code != FUNC and code not in FUNC_OK:
        return f"FUNC+{NAMES.get(code, code)} is refused (saving / clearing chords)"
    if code == FUNC:
        bad = sorted(c for c in down_before if c != FUNC and c not in FUNC_OK)
        if bad:
            return f"FUNC over a held {NAMES.get(bad[0], bad[0])} is refused"
    return None


def chord_events(combo: str, tap_ms: int = TAP_MS, allow_destructive: bool = False) -> tuple[list[P.Event], int]:
    """'FUNC+SRC' -> (events, how long they take in ms): the modifiers go down GAP_MS apart and stay down
    until the last key has been tapped and let go"""
    codes = [code_of(k) for k in combo.split("+") if k.strip()]
    if not codes:
        raise ValueError("an empty chord")
    held: set[int] = set()
    for c in codes:
        why = check(frozenset(held), c, allow_destructive)
        if why:
            raise Blocked(why)
        held.add(c)
    mods, last = codes[:-1], codes[-1]
    t_last = GAP_MS * len(mods)
    total = t_last + tap_ms + (GAP_MS if mods else 0)
    events = [P.Event(P.PRESS, c, GAP_MS * i, total - GAP_MS * i) for i, c in enumerate(mods)]
    events.append(P.Event(P.PRESS, last, t_last, tap_ms))
    return events, total


def turn_events(encoder: int, delta: int, push: bool = False, start_ms: int = 0) -> tuple[list[P.Event], int]:
    if delta == 0:
        return [], 0
    steps, left = [], delta
    while left:
        s = max(-ENC_STEP, min(ENC_STEP, left))
        steps.append(s)
        left -= s
    t0 = start_ms + (GAP_MS if push else 0)
    events = [P.Event(P.ENCODER, encoder, t0 + ENC_GAP_MS * i, s) for i, s in enumerate(steps)]
    end = t0 + ENC_GAP_MS * len(steps)
    if push:
        hold = end + GAP_MS - start_ms
        events.insert(0, P.Event(P.PRESS, 41 + encoder if encoder < 8 else 49, start_ms, hold))
        end = start_ms + hold
    return events, end - start_ms


class Keys:
    def __init__(self, channel: TestChannel, allow_destructive: bool = False,
                 log: str | pathlib.Path | None = "dn2ui-events.jsonl", gap_s: float = 0.03):
        self.ch = channel
        self.allow_destructive = allow_destructive
        self.log = pathlib.Path(log) if log else None
        self.gap_s = gap_s
        self._last = 0.0

    def _record(self, what: str, **kw) -> None:
        if self.log is None:
            return
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "what": what, **kw}) + "\n")

    def _send(self, events: list[P.Event], what: str, total_ms: int, wait: bool = True) -> None:
        if not events:
            return
        dt = time.monotonic() - self._last
        if dt < self.gap_s:                                    # the host's rate limit
            self.ch.unit.wait(self.gap_s - dt)
        for i in range(0, len(events), 16):
            chunk = events[i:i + 16]
            base = chunk[0].at_ms
            chunk = [P.Event(e.kind, e.code, e.at_ms - base, e.value) for e in chunk]   # relative to this message
            for _ in range(200):                                # the unit queues 16: wait for room
                try:
                    self.ch.send_events(chunk)
                    break
                except StatusError as e:
                    if e.status != P.BUSY:
                        raise
                    self.ch.unit.wait(0.05)
            else:
                raise StatusError(P.KEY, P.BUSY)
        self._last = time.monotonic()
        self._record(what, events=[[e.kind, e.code, e.at_ms, e.value] for e in events],
                     allow_destructive=self.allow_destructive)
        if wait:
            self.ch.unit.wait(total_ms / 1000.0 + 0.02)

    def arm(self) -> P.ArmState:
        s = self.ch.arm(self.allow_destructive)
        self._record("arm", destructive=s.destructive, timeout_s=s.timeout_s)
        return s

    def disarm(self) -> P.ArmState:
        s = self.ch.disarm()
        self._record("disarm")
        return s

    def press(self, combo: str, tap_ms: int = TAP_MS, wait: bool = True) -> None:
        events, total = chord_events(combo, tap_ms, self.allow_destructive)
        self._send(events, f"press {combo}", total, wait)

    def hold(self, key: str, ms: int, wait: bool = True) -> None:
        events, total = chord_events(key, ms, self.allow_destructive)
        self._send(events, f"hold {key} {ms}", total, wait)

    def turn(self, encoder: str | int, delta: int, push: bool = False, wait: bool = True) -> None:
        events, total = turn_events(encoder_of(encoder), delta, push)
        self._send(events, f"turn {encoder} {delta:+d}{' push' if push else ''}", total, wait)

    def sequence(self, steps: list[str], pause_s: float = 0.25, out_dir: str | pathlib.Path = ".") -> list[str]:
        """steps: 'FUNC+SRC', 'turn:A:+5', 'push:A:-3', 'hold:PLAY:600', 'wait:0.5', 'snap:NAME' (a PNG in OUT_DIR),
        'expect:changed' (the screen differs from the last snap, else AssertionError). -> the PNGs written"""
        from .screen import write_png
        shots: list[str] = []
        last = None
        for s in steps:
            kind, _, rest = s.partition(":")
            if kind == "wait":
                self.ch.unit.wait(float(rest))
                continue
            if kind == "snap":
                last = self.ch.screen()
                shots.append(str(write_png(last, pathlib.Path(out_dir) / f"{rest or len(shots)}.png")))
                continue
            if kind == "expect":
                if rest != "changed" or last is None:
                    raise ValueError("expect:changed follows a snap")
                if self.wait_for_screen(lambda f: f != last, timeout=2.0) is None:
                    raise AssertionError(f"the screen did not change (step {len(shots)})")
                continue
            if kind in ("turn", "push"):
                enc, d = rest.split(":")
                self.turn(enc, int(d), push=kind == "push")
            elif kind == "hold":
                key, ms = rest.split(":")
                self.hold(key, int(ms))
            else:
                self.press(s)
            self.ch.unit.wait(pause_s)
        return shots

    def wait_for_screen(self, want: Callable[[bytes], bool] | bytes, timeout: float = 3.0,
                        poll_s: float = 0.1, tolerance: int = 0) -> bytes | None:
        """-> the first frame that WANT accepts (a predicate, or a frame within TOLERANCE pixels), None at the timeout"""
        from .screen import differ
        test = want if callable(want) else (lambda f: differ(f, want) <= tolerance)
        end = self.ch.unit.clock() + timeout
        last = None
        while True:
            h, whole = self.ch.screen_hash()
            if whole and h != last:
                last = h
                frame = self.ch.screen(fresh=False)
                if test(frame):
                    return frame
            if self.ch.unit.clock() >= end:
                return None
            self.ch.unit.wait(poll_s)
