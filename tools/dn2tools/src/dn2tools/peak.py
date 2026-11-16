"""Peak and transient cost on the unit (docs/device-tests.md, "Peaks and wake-ups"): what the idle skips
(FDN8 quiet gate, A2 quiet skip, chain skip, empty-pass exits) cost when the project is busy, and the spike when a
skipped part wakes. Steady state is `bench.py`'s; here the polls are every 0.1 s and the max and the 99th percentile
of the readings are the figures.

What the telemetry can see: D is the DSP's load of one frame in permille, held as the PEAK of the last half second
(link.c). Polling faster than that loses no frame's peak: the max over the polls is the worst frame of the window.
The percentile is over polls (a peak-of-half-second each), not over frames: it is an upper bound. D is clamped to
1000 (one frame): a frame over 100 % (the model's 745k wake-up block) reads 1000 and shows in `skipped` and INS_SKIPS,
not as a number. 0.1 % = 667 cycles. The skip switches are build switches, not run-time ones: an A/B is two builds
(flash A, `--peak --label A`; flash B, `--peak --label B`; `--peak-compare`)."""

from __future__ import annotations

import csv
import math
import pathlib
import random
import statistics
import time
from dataclasses import dataclass

from .ctx import Ctx, Params, Result
from .frame import FRAME_CYCLES
from .project import Project
from .unit import Unit

POLL_S = 0.1
QUIET_WAIT_S = 6.0                 # longer than FDN8's 4,224 blocks (2.8 s) and the A2 quiet skip
COLUMNS = ("build", "label", "scenario", "n", "mean", "p99", "max", "first_max", "steady_mean", "spike_ratio",
           "skipped_max", "ins_skips", "a2_dry")
NOTES = (60, 64, 67, 71, 72, 76, 79, 83, 48, 52, 55, 59, 36, 40, 43, 47)


@dataclass(frozen=True)
class Peak:
    scenario: str
    n: int
    mean: float
    p99: float
    max: float
    first_max: float
    steady_mean: float
    skipped_max: int
    ins_skips: int
    a2_dry: int

    @property
    def spike_ratio(self) -> float:
        return self.first_max / self.steady_mean if self.steady_mean else 0.0


def _cycles(pm) -> float:
    return (pm or 0) * FRAME_CYCLES / 1000.0


def _percentile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def _summary(name: str, rs, first_s: float = 1.0) -> Peak:
    d = [_cycles(r.d_pm) for r in rs]
    k = max(1, int(first_s / POLL_S))
    tail = d[-max(1, int(1.0 / POLL_S)):]
    return Peak(name, len(d), statistics.fmean(d), _percentile(d, 0.99), max(d), max(d[:k]), statistics.fmean(tail),
                max(r.skipped_voices for r in rs), rs[-1].ins_skips - rs[0].ins_skips, (rs[-1].a2_dry - rs[0].a2_dry) & 0xFFFF)


def run_peaks(unit: Unit, project: Project, params: Params, seconds: float = 60.0, seed: int = 1, log=print) -> list[Peak]:
    fast = Params(**{**params.__dict__, "every_s": POLL_S})
    ctx = Ctx(unit, project, fast, Result("peak", "peaks"))
    rng = random.Random(seed)
    tracks = [t for t in project.tracks if not t.hold]
    out: list[Peak] = []

    def done(p: Peak) -> None:
        out.append(p)
        log(f"  {p.scenario:34s} mean {p.mean:9,.0f}  p99 {p.p99:9,.0f}  max {p.max:9,.0f}  spike x{p.spike_ratio:.2f}  skipped {p.skipped_max}")

    def quiet(s: float = QUIET_WAIT_S) -> None:
        unit.all_notes_off()
        ctx.wait(s)

    def voices_over(tr_list, total=16):
        """(track, notes) so that `total` voices sound over the tracks"""
        per, extra = divmod(total, len(tr_list))
        return [(tr, NOTES[:per + (1 if k < extra else 0)]) for k, tr in enumerate(tr_list)]

    quiet(2.0)
    # (1) a busy project: 16 voices over every track, inserts and sends as the project has them
    plays = voices_over(tracks)
    for tr, notes in plays:
        ctx.play(tr, notes, 90)
    done(_summary("busy 16 voices", ctx.run(10.0)))
    for tr, notes in plays:
        ctx.release(tr, notes)
    quiet()
    # (2a) all tracks wake at once from silence
    for tr in tracks:
        ctx.play(tr, NOTES[:1], 90)
    done(_summary("wake all tracks", ctx.run(4.0)))
    quiet()
    # (2b) a gated FX / a quiet A2 filter wakes: silent past the gate, then one note
    for tr in tracks:
        if not (tr.insert or tr.filter):
            continue
        label = f"wake {tr.insert or tr.filter} (T{tr.number})"
        ctx.play(tr, NOTES[:1], 90)
        ctx.run(1.5)
        ctx.release(tr, NOTES[:1])
        quiet()
        ctx.play(tr, NOTES[:1], 90)
        done(_summary(label, ctx.run(3.0)))
        quiet(2.0)
    # (3) the worst frame in a long run: notes start at random
    end, held = ctx.t + seconds, []
    readings = []
    while ctx.t < end:
        for tr, n, until in list(held):
            if until <= ctx.t:
                ctx.release(tr, (n,))
                held.remove((tr, n, until))
        if rng.random() < 0.35 and len(held) < 16:
            tr, n = rng.choice(tracks), rng.choice(NOTES)
            if not any(h[0] is tr and h[1] == n for h in held):
                ctx.play(tr, (n,), rng.randint(40, 127))
                held.append((tr, n, ctx.t + rng.uniform(0.2, 1.5)))
        ctx.wait(POLL_S)
        readings.append(ctx.sample())
    done(_summary(f"random notes {seconds:.0f} s", readings, 0.0))
    quiet(2.0)
    return out


def write(peaks: list[Peak], out_dir, build: int, label: str) -> tuple[pathlib.Path, pathlib.Path]:
    d = pathlib.Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    c, m = d / f"peak-{label}-{stamp}.csv", d / f"peak-{label}-{stamp}.md"
    with c.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for p in peaks:
            w.writerow([f"{build:#010x}", label, p.scenario, p.n, f"{p.mean:.0f}", f"{p.p99:.0f}", f"{p.max:.0f}", f"{p.first_max:.0f}",
                        f"{p.steady_mean:.0f}", f"{p.spike_ratio:.3f}", p.skipped_max, p.ins_skips, p.a2_dry])
    md = [f"# Peaks {label}: build {build:#010x}", "", f"{time.strftime('%Y-%m-%d %H:%M:%S')}; cycles of a {FRAME_CYCLES:,} frame; D is clamped at one frame.", "",
          "| scenario | polls | mean | p99 | max | max % | first second max | steady | spike x | skipped | INS_SKIPS |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    md += [f"| {p.scenario} | {p.n} | {p.mean:,.0f} | {p.p99:,.0f} | {p.max:,.0f} | {100 * p.max / FRAME_CYCLES:.1f} | {p.first_max:,.0f} | "
           f"{p.steady_mean:,.0f} | {p.spike_ratio:.2f} | {p.skipped_max} | {p.ins_skips} |" for p in peaks]
    m.write_text("\n".join(md) + "\n")
    return c, m


def compare(on: str, off: str, tolerance: float = 2 * FRAME_CYCLES / 1000.0) -> str:
    """skips ON build vs skips OFF build: mean, p99, max per scenario, and a verdict. ON is worse when its max exceeds
    OFF's by more than the tolerance (default two steps of D, 1,333 cycles: the check overhead the skips may cost)"""
    def load(p):
        with open(p, newline="") as f:
            rows = list(csv.DictReader(f))
        return (rows[0]["build"] if rows else "?"), {r["scenario"]: r for r in rows}
    bn, a = load(on)
    bf, b = load(off)
    out = [f"# Skips ON {bn} vs OFF {bf}", "", f"worse = ON's max or p99 over OFF's by more than {tolerance:,.0f} cycles", "",
           "| scenario | mean ON | mean OFF | p99 ON | p99 OFF | max ON | max OFF | max diff | spike ON | spike OFF | verdict |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for s in a:
        if s not in b:
            continue
        x, y = a[s], b[s]
        dmax, dp99 = float(x["max"]) - float(y["max"]), float(x["p99"]) - float(y["p99"])
        worse = dmax > tolerance or dp99 > tolerance
        out.append(f"| {s} | {float(x['mean']):,.0f} | {float(y['mean']):,.0f} | {float(x['p99']):,.0f} | {float(y['p99']):,.0f} | "
                   f"{float(x['max']):,.0f} | {float(y['max']):,.0f} | {dmax:+,.0f} | {x['spike_ratio']} | {y['spike_ratio']} | {'**ON WORSE**' if worse else 'ok'} |")
    return "\n".join(out) + "\n"
