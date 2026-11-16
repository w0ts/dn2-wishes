"""Performance on the unit (docs/device-tests.md, "Benchmarks"): real cycles per frame, to replace the runner's
estimates. The telemetry's D is the DSP's load in permille over a half second (0.1 % = 667 cycles of the
666,667 a frame), so `D x 666.667` is the cycles the DSP used in a frame; it is the half second's PEAK, so a
"mean" here is the mean of peaks (an upper bound of the mean) and "max" the peak. The slot costs (frame_cost) are the
voices' own passes. Each item is held >= 3 s after a 1 s settle."""

from __future__ import annotations

import csv
import pathlib
import re
import statistics
import time
from dataclasses import dataclass

from .ctx import SIXTEEN, Ctx, Params, Result
from .frame import FRAME_CYCLES
from .project import Project, Track
from .unit import Unit

NOTES = (60, 64, 67, 71, 72, 76, 79, 83, 48, 52, 55, 59, 36, 40, 43, 47)         # distinct, up to 16
SETTLE_S = 1.0
COLUMNS = ("build", "label", "item", "key", "voices", "d_mean_cycles", "d_max_cycles", "delta_mean", "delta_max",
           "slots_mean", "c_mean_pct", "c_max_pct", "skipped_max", "ins_skips", "a2_dry", "runner_cycles", "ratio")


@dataclass(frozen=True)
class Row:
    item: str
    key: str
    voices: int
    d_mean: float
    d_max: float
    slots_mean: float
    c_mean: float
    c_max: float
    skipped_max: int
    ins_skips: int
    a2_dry: int


def load_runner(path: str | pathlib.Path | None) -> dict[str, tuple[float, float]]:
    """the budget table's synth rows: name -> (1 voice mean, 16 voices mean) in cycles (a frame total, idle included)"""
    if not path or not pathlib.Path(path).exists():
        return {}
    out = {}
    for ln in pathlib.Path(path).read_text().splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.fullmatch(r"[\d,]+", cells[1]) and re.fullmatch(r"[\d,]+", cells[3]):
            out[cells[0]] = (float(cells[1].replace(",", "")), float(cells[3].replace(",", "")))
    return out


def _measure(ctx: Ctx, item: str, key: str, voices: int, seconds: float) -> Row:
    rs = [s for t, s in ((ctx.t, x) for x in ctx.run(SETTLE_S + seconds))][int(SETTLE_S / ctx.params.every_s):]
    pm = [r.d_pm for r in rs if r.d_pm is not None] or [0]
    first, last = rs[0], rs[-1]
    return Row(item, key, voices, statistics.fmean(pm) * FRAME_CYCLES / 1000.0, max(pm) * FRAME_CYCLES / 1000.0,
               statistics.fmean(r.frame_cost for r in rs), statistics.fmean(r.c_pct or 0 for r in rs),
               max(r.c_pct or 0 for r in rs), max(r.skipped_voices for r in rs),
               last.ins_skips - first.ins_skips, (last.a2_dry - first.a2_dry) & 0xFFFF)


def _items(project: Project):
    """(item, [(track, notes)...]) in order; every held on its own channel"""
    yield "idle", "", []
    for tr in project.tracks:
        if tr.hold:
            continue
        for n in (1, 4, 8, 16):
            yield f"{tr.label} x{n}", tr.key or "", [(tr, NOTES[:n] if n < 16 else SIXTEEN)]
    ins = [t for t in project.tracks if t.insert]
    for tr in project.tracks:
        if tr.filter:
            yield f"A2 {tr.filter} 1v", "", [(tr, NOTES[:1])]
        if tr.insert:
            yield f"insert {tr.insert} 1v", "", [(tr, NOTES[:1])]
            yield f"insert {tr.insert} 4v", "", [(tr, NOTES[:4])]
    kinds = {}
    for tr in ins:
        kinds.setdefault(tr.insert, tr)
    ks = sorted(kinds)
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            yield f"inserts {a}+{b} 1v each", "", [(kinds[a], NOTES[:1]), (kinds[b], NOTES[:1])]


def run_bench(unit: Unit, project: Project, params: Params, label: str, seconds: float = 3.0, log=print) -> list[Row]:
    rows = []
    res = Result("bench", "benchmarks")
    ctx = Ctx(unit, project, params, res)
    unit.all_notes_off()
    ctx.wait(1.0)
    for item, key, plays in _items(project):
        try:
            for tr, notes in plays:
                ctx.play(tr, notes, 90)
            row = _measure(ctx, item, key, sum(len(n) for _, n in plays), seconds)
        finally:
            for tr, notes in plays:
                ctx.release(tr, notes)
            unit.all_notes_off()
            ctx.wait(2.0)
        rows.append(row)
        log(f"  {item:36s} D mean {row.d_mean:9,.0f}  max {row.d_max:9,.0f} cycles  skipped {row.skipped_max}")
    return rows


def write(rows: list[Row], out_dir, build: int, label: str, runner: dict) -> tuple[pathlib.Path, pathlib.Path]:
    d = pathlib.Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = next((r for r in rows if r.item == "idle"), None)
    table = []
    for r in rows:
        dm, dx = (r.d_mean - base.d_mean, r.d_max - base.d_max) if base else (0.0, 0.0)
        table.append((r, dm, dx, None))
    csv_path, md_path = d / f"bench-{label}-{stamp}.csv", d / f"bench-{label}-{stamp}.md"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r, dm, dx, _ in table:
            rc = runner.get(r.key, ("", ""))
            runner_cycles = rc[0] if r.voices == 1 else (rc[1] if r.voices == 16 else "")
            ratio = f"{r.d_mean / runner_cycles:.3f}" if runner_cycles else ""
            w.writerow([f"{build:#010x}", label, r.item, r.key, r.voices, f"{r.d_mean:.0f}", f"{r.d_max:.0f}", f"{dm:.0f}", f"{dx:.0f}",
                        f"{r.slots_mean:.0f}", f"{r.c_mean:.1f}", f"{r.c_max:.1f}", r.skipped_max, r.ins_skips, r.a2_dry,
                        runner_cycles, ratio])
    md = [f"# Benchmark {label}: build {build:#010x}", "", f"{time.strftime('%Y-%m-%d %H:%M:%S')}; one frame = {FRAME_CYCLES:,} cycles; "
          "D is the half second's peak, 0.1 % = 667 cycles.", "",
          "| item | voices | D mean | D max | over idle (mean) | % of frame | slots mean | C max % | skipped | runner | ratio |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r, dm, dx, _ in table:
        rc = runner.get(r.key, ("", ""))
        rcy = rc[0] if r.voices == 1 else (rc[1] if r.voices == 16 else "")
        md.append(f"| {r.item} | {r.voices} | {r.d_mean:,.0f} | {r.d_max:,.0f} | {dm:,.0f} | {100 * r.d_mean / FRAME_CYCLES:.1f} | "
                  f"{r.slots_mean:,.0f} | {r.c_max:.0f} | {r.skipped_max} | {rcy if rcy == '' else f'{rcy:,.0f}'} | "
                  f"{'' if rcy == '' else f'{r.d_mean / rcy:.2f}'} |")
    md_path.write_text("\n".join(md) + "\n")
    return csv_path, md_path


def compare(a: str, b: str) -> str:
    """two bench CSVs (flash A, run, flash B, run): per item the change in cycles over the idle floor and in total"""
    def load(p):
        with open(p, newline="") as f:
            rows = list(csv.DictReader(f))
        return rows[0]["build"] if rows else "?", {r["item"]: r for r in rows}
    ba, ra = load(a)
    bb, rb = load(b)
    out = [f"# Compare {ba} (A) -> {bb} (B)", "",
           "| item | A total | B total | change | A over idle | B over idle | change |", "|---|---:|---:|---:|---:|---:|---:|"]
    for item in ra:
        if item not in rb:
            continue
        ta, tb = float(ra[item]["d_mean_cycles"]), float(rb[item]["d_mean_cycles"])
        da, db = float(ra[item]["delta_mean"]), float(rb[item]["delta_mean"])
        pct = lambda x, y: f"{100 * (y - x) / x:+.1f} %" if x else ""      # noqa: E731
        out.append(f"| {item} | {ta:,.0f} | {tb:,.0f} | {pct(ta, tb)} | {da:,.0f} | {db:,.0f} | {pct(da, db)} |")
    return "\n".join(out) + "\n"
