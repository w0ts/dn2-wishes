"""What a scenario works with: the unit, the project, a clock of its own and the readings it took."""

from __future__ import annotations

from dataclasses import dataclass, field

from .frame import Telemetry
from .project import Project, Track
from .unit import Unit

CHORD = (60, 64, 67, 71)                          # four voices
SIXTEEN = tuple(range(36, 52))                    # sixteen voices


@dataclass(frozen=True)
class Params:
    hold_s: float = 3.0              # how long a filter / insert / stress note is held
    every_s: float = 0.2             # the poll interval
    ins_skip_cap: int = 0            # insert blocks passed through for time a scenario may add
    idle_d_max: float = 95.0         # the DSP's load at idle, percent (the labels come on at 99)
    idle_c_max: float = 85.0         # the ColdFire's, percent (they come on at 90)
    d_limit: float = 100.0           # the DSP's load a scenario must stay under, percent


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Result:
    name: str
    title: str
    checks: list[Check] = field(default_factory=list)
    numbers: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    skipped: str | None = None
    error: str | None = None
    series: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and all(c.ok for c in self.checks)

    @property
    def status(self) -> str:
        if self.error:
            return "ERROR"
        if self.skipped:
            return "SKIP"
        return "PASS" if self.ok else "FAIL"


def delta16(a: int, b: int) -> int:
    """a 16-bit counter's growth from A to B"""
    return (b - a) & 0xFFFF


class Ctx:
    def __init__(self, unit: Unit, project: Project, params: Params, result: Result):
        self.unit, self.project, self.params, self.result = unit, project, params, result
        self.t = 0.0
        self.samples: list[tuple[float, Telemetry]] = []

    # -- time and readings ----------------------------------------------------------------
    def wait(self, seconds: float) -> None:
        self.unit.wait(seconds)
        self.t += seconds

    def sample(self) -> Telemetry:
        s = self.unit.tlm()
        self.samples.append((self.t, s))
        self.result.series.append({"t": round(self.t, 2), "D": s.d_pct, "Dpk": s.d_peak_pct, "C": s.c_pct,
                                   "voices": s.voices, "cost%": round(s.cost_pct, 1), "skip": s.skip_mask,
                                   "insk": s.ins_skips, "nfil": s.a2_filtered, "ndry": s.a2_dry,
                                   "hold": s.hold_count, "latched": s.latched, "lit": "".join(s.lit)})
        return s

    def run(self, seconds: float) -> list[Telemetry]:
        """poll for SECONDS, every `every_s`; the readings (the first at once)"""
        out, end = [self.sample()], self.t + seconds
        while self.t < end - 1e-9:
            self.wait(min(self.params.every_s, end - self.t))
            out.append(self.sample())
        return out

    # -- notes ------------------------------------------------------------------------------
    def play(self, track: Track, notes, vel: int = 100) -> None:
        for n in notes:
            self.unit.note_on(track.channel, n, vel)

    def release(self, track: Track, notes) -> None:
        for n in notes:
            self.unit.note_off(track.channel, n)

    def silence(self, wait: float = 1.0) -> None:
        self.unit.all_notes_off()
        self.wait(wait)

    # -- results ----------------------------------------------------------------------------
    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.result.checks.append(Check(name, bool(ok), detail))
        return bool(ok)

    def number(self, key: str, value) -> None:
        self.result.numbers[key] = value

    def note(self, text: str) -> None:
        self.result.notes.append(text)
