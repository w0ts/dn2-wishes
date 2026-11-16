"""A fake Digitone II for the dry run: the telemetry frame the real unit would send, for the notes it is played.

It is a MODEL, not the unit: the numbers (costs, loads) are rounded from the runner's budget table
(docs/dsp-cost.md) and the User's reports, so that every scenario's assertion can pass AND fail here.
Faults (`faults=`) switch a known failure on, to prove an assertion catches it:

    a2_dies        the A2 filters stop filtering one second after a note starts (the 2026-11 report)
    hold_dead      HOLD never latches
    labels_idle    the DSP label is lit at idle with the DSP at 60 %
    ins_skips      an engaged insert is passed through for time all the time
    voices_stale   a voice's cost never clears after its note ends
    overload       every voice costs six times as much and the DSP guard does not stop them (the DSP over its frame)

Served over mido virtual ports with `dn2test --serve-fake` (wall-clock time), or
in-process through DirectUnit (virtual time: `wait` advances the model, so a dry run takes seconds).
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Callable

from .frame import CMD_TLM, FRAME_CYCLES, FRAMES_PER_S, Telemetry, encode
from .project import Project
from . import protocol as P
from .sim_channel import ChannelSim
from .unit import CMD_HELLO, HEADER, Unit

BUILD = 0x00470001
IDLE_COST = 426_667                              # the silent frame, 64 %
MACHINE_COST = {"ANALOG2": 14_000, "DRONE": 12_000, "PLAITS": 22_000, "TB303": 18_000, "SOPHIE": 15_000}
FILTER_COST = {"SVF": 6_000, "LADR": 7_500, "OTA": 8_000, "DIOD": 10_000, "MS20": 7_000}
INSERT_COST = {"XDLY": 20_000, "FDN8": 45_000, "CHOR": 30_000}
RELEASE_S = 0.3
STEP_S = 0.02
HEAP_TOTAL = 32 << 20


@dataclass
class Voice:
    track: int                    # index into project.tracks
    note: int
    started: float
    released: float | None = None
    latched: bool = False
    skipped: bool = False
    vel: int = 100
    at: float = 0.0                       # exact start, clock time
    rel_at: float | None = None           # exact release, clock time
    legato_from: int | None = None        # the note it glides from (a glide track, a note still held)


@dataclass
class UnitSim:
    project: Project
    clock: Callable[[], float]
    faults: frozenset[str] = frozenset()
    t: float = 0.0
    voices: list[Voice] = field(default_factory=list)
    frames: float = 0.0
    a2_filtered: float = 0.0
    a2_dry: float = 0.0
    ins_skips: float = 0.0
    ins_skip_at: float | None = None
    hold_count: int = 0
    hold_drops: int = 0
    skip_at: float | None = None
    label_at: dict = field(default_factory=dict)
    d_hist: list = field(default_factory=list)
    c_hist: list = field(default_factory=list)
    last_cost: tuple = (0,) * 16
    last_pm: int = 640
    steps: int = 0
    log: list = field(default_factory=list)       # every voice ever started (the audio simulator renders from it)

    def __post_init__(self) -> None:
        self.t0 = self.clock()
        self.t = self.t0
        self.channel = ChannelSim(self.clock, self.faults)

    # -- time -----------------------------------------------------------------------------
    def _track_of(self, ch: int):
        for k, tr in enumerate(self.project.tracks):
            if tr.channel == ch:
                return k, tr
        return None, None

    def _advance(self) -> None:
        target = int((self.clock() - self.t0) / STEP_S + 1e-9)       # whole steps: no float drift in the counters
        while self.steps < target:
            self.steps += 1
            self.t = self.t0 + self.steps * STEP_S
            self._step()

    def _factor(self) -> float:
        return 6.0 if "overload" in self.faults else 1.0

    def _step(self) -> None:
        t = self.t
        self.frames += STEP_S * FRAMES_PER_S
        self.voices = [v for v in self.voices
                       if v.latched or v.released is None or t - v.released < RELEASE_S
                       or ("voices_stale" in self.faults)]
        live = self.voices[:16]
        cost, total = [0] * 16, float(IDLE_COST)
        inserts_on, a2_on = {self.project.tracks[v.track].insert for v in live} - {None}, 0
        total += sum(INSERT_COST[i] for i in inserts_on)     # an engaged insert runs whether or not its voice is kept
        for slot, v in enumerate(live):
            v.skipped = False
            tr = self.project.tracks[v.track]
            c = (MACHINE_COST.get(tr.machine, 15_000) + (FILTER_COST[tr.filter] if tr.filter else 0)) * self._factor()
            if total + c > 0.95 * FRAME_CYCLES and "overload" not in self.faults:   # the DSP guard leaves the voice out for time (a failed guard: overload)
                v.skipped = True
                self.skip_at = t
                continue
            total += c
            cost[slot] = int(c)
            if tr.filter and not ("a2_dies" in self.faults and t - v.started > 1.0):
                a2_on += 1
            elif tr.filter:
                self.a2_dry += STEP_S * FRAMES_PER_S
        blocks = STEP_S * FRAMES_PER_S
        self.a2_filtered += a2_on * blocks
        if inserts_on and (total > 0.9 * FRAME_CYCLES or "ins_skips" in self.faults):
            self.ins_skips += blocks
            self.ins_skip_at = t
        self.last_cost = tuple(cost)
        pm = min(1000, int(1000 * total / FRAME_CYCLES))
        if "labels_idle" in self.faults:
            pm = 600
            self.label_at["D"] = t
        self.last_pm = pm
        self.d_hist = [(a, b) for a, b in self.d_hist if t - a < 3.0] + [(t, pm)]
        self.c_hist = [(a, b) for a, b in self.c_hist if t - a < 3.0] + [(t, 300 + 4 * len(live))]
        if pm >= 990 or (self.skip_at is not None and t - self.skip_at < 0.5):
            self.label_at["D"] = t
        if self.c_hist[-1][1] >= 900:
            self.label_at["C"] = t

    # -- the unit's inputs ----------------------------------------------------------------
    def note(self, on: bool, ch: int, note: int, vel: int = 100) -> None:
        self._advance()
        k, tr = self._track_of(ch)
        if tr is None:
            return
        if on:
            if tr.hold and "hold_dead" not in self.faults:
                same = [v for v in self.voices if v.latched and v.track == k and v.note == note]
                if same:                                 # the same key again lets the latch go (hold.c)
                    for v in same:
                        v.latched, v.released, v.rel_at = False, self.t, self.clock()
                    self.hold_drops += 1
                    return
                for v in self.voices:                    # another key on the track takes the latch over
                    if v.latched and v.track == k:
                        v.latched, v.released, v.rel_at = False, self.t, self.clock()
                self.hold_count += 1
                self._start(Voice(k, note, self.t, latched=True, vel=vel, at=self.clock()))
            else:
                v = Voice(k, note, self.t, vel=vel, at=self.clock())
                if tr.glide:                                         # mono and legato: a note still held glides to the new one
                    held = [o for o in self.voices if o.track == k and o.released is None and not o.latched]
                    if held:
                        v.legato_from = held[-1].note
                        for o in held:
                            o.released, o.rel_at = self.t, self.clock()
                self._start(v)
        else:
            for v in self.voices:
                if v.track == k and v.note == note and v.released is None and not v.latched:
                    v.released, v.rel_at = self.t, self.clock()

    def cc(self, ch: int, cc: int) -> None:
        """all notes off / all sound off on a channel: its track's voices are released (a HOLD latch stays, as on the unit)"""
        self._advance()
        k, _ = self._track_of(ch)
        for v in self.voices:
            if cc in (120, 123) and v.track == k and v.released is None and not v.latched:
                v.released, v.rel_at = self.t, self.clock()

    def _start(self, v: Voice) -> None:
        self.voices.append(v)
        self.log.append(v)
        if len(self.voices) > 16:                        # 16 voices: the oldest is stolen
            self.voices.pop(0)

    # -- the telemetry --------------------------------------------------------------------
    def snapshot(self) -> Telemetry:
        self._advance()
        t = self.t
        d_peak = max((b for _, b in self.d_hist), default=self.last_pm)
        c_peak = max((b for _, b in self.c_hist), default=300)
        lit, ages = 0, []
        for k, name in enumerate("DCM"):
            at = self.label_at.get(name)
            ages.append(None if at is None else int((t - at) * FRAMES_PER_S))
            if at is not None and t - at < 1.0:
                lit |= 1 << k
        hold_seq = 0
        for slot, v in enumerate(self.voices[:16]):
            if v.latched:
                hold_seq |= 1 << slot
        sk = sum(1 << s for s, v in enumerate(self.voices[:16]) if v.skipped)
        cost = self.last_cost
        return Telemetry(
            build=BUILD, frames=int(self.frames), periods=int(self.frames), d_pm=self.last_pm,
            d_peak_pct=(d_peak + 5) // 10, c_pm=300 + 4 * len(self.voices), c_peak_pct=(c_peak + 5) // 10,
            heap_used=int(0.4 * HEAP_TOTAL), heap_total=HEAP_TOTAL, heap_faults=0,
            labels_lit=lit, labels_hys=lit, labels_force=0, label_age=tuple(ages),
            skip_mask=sk, ins_full=False, ins_skips=int(self.ins_skips) & 0xFFFFFFFF,
            ins_skip_age=None if self.ins_skip_at is None else int((t - self.ins_skip_at) * FRAMES_PER_S),
            hold_count=self.hold_count, hold_drops=self.hold_drops, hold_seq=hold_seq,
            a2_filtered=int(self.a2_filtered) & 0xFFFF, a2_dry=int(self.a2_dry) & 0xFFFF,
            frame_cost=sum(cost), voices=sum(1 for c in cost if c), slot_cost=tuple((c // 16) * 16 for c in cost))

    def handle_sysex(self, sx: bytes) -> bytes | None:
        """one request in, the reply out (None: not ours); HELLO, TLM, and the test channel (sim_channel.py)"""
        sx = bytes(sx)
        if not sx.startswith(HEADER) or not sx.endswith(b"\xF7"):
            return None
        msg = P.unpack7(sx[len(HEADER):-1])
        if len(msg) < 3:
            return None
        seq, cmd = struct.unpack(">HB", msg[:3])
        args = msg[3:]
        if cmd == CMD_HELLO:
            status, body = 0, struct.pack(">HII", 7, 0, 0)
        elif cmd == CMD_TLM:
            status, body = 0, encode(self.snapshot())
        elif 33 <= cmd <= 43 and cmd != 39:
            status, body = self.channel.handle(cmd, args)
        else:
            status, body = 2, b""
        return P.reply(seq, cmd, status, body)

    def poll(self) -> None:
        """the firmware's UI pass (dt_poll): due key events, releases"""
        self.channel.poll()


class DirectUnit(Unit):
    """the simulator in-process; `wait` advances its virtual clock; the SysEx goes through the real codec"""

    def __init__(self, project: Project, faults=()):
        self.now = 0.0
        self.sim = UnitSim(project, lambda: self.now, frozenset(faults))
        self.seq = 0x700

    def _note(self, on: bool, ch: int, note: int, vel: int) -> None:
        self.sim.note(on, ch, note, vel)

    def clock(self) -> float:
        return self.now

    def _cc(self, ch: int, cc: int, value: int) -> None:
        self.sim.cc(ch, cc)

    def _exchange(self, cmd: int, payload: bytes) -> P.Reply | None:
        self.seq += 1
        raw = self.sim.handle_sysex(P.encode(self.seq, cmd, payload))
        return None if raw is None else P.decode(raw)

    def wait(self, seconds: float) -> None:
        """virtual time, in UI passes of 5 ms (the key events fall due on the way)"""
        end = self.now + seconds
        while self.now < end - 1e-12:
            self.now = min(end, self.now + 0.005)
            self.sim.poll()


def serve(project: Project, name: str, faults=(), seconds: float | None = None) -> None:
    """the simulator on mido virtual ports called NAME (wall-clock time), until interrupted"""
    import mido
    sim = UnitSim(project, time.monotonic, frozenset(faults))
    inp, out = mido.open_input(name, virtual=True), mido.open_output(name, virtual=True)
    print(f"fake unit on virtual MIDI ports {name!r} (faults: {sorted(faults) or 'none'}); Ctrl-C to stop", flush=True)
    end = None if seconds is None else time.monotonic() + seconds
    try:
        while end is None or time.monotonic() < end:
            sim.poll()
            for m in inp.iter_pending():
                if m.type in ("note_on", "note_off"):
                    sim.note(m.type == "note_on" and m.velocity > 0, m.channel, m.note, m.velocity)
                elif m.type == "control_change":
                    sim.cc(m.channel, m.control)
                elif m.type == "sysex":
                    r = sim.handle_sysex(bytes([0xF0]) + bytes(m.data) + bytes([0xF7]))
                    if r:
                        out.send(mido.Message("sysex", data=r[1:-1]))
            time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    finally:
        inp.close()
        out.close()
