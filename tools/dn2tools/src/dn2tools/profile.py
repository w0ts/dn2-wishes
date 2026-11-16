"""The CPU profiler's host side: run PROFILE on the unit, then what the ColdFire spent its time on.

    run(ch, seconds, rate, source)        -> Run (the samples, the firmware's status before/after, the clocks)
    analyse(run, symbols)                 -> dict (idle %, functions %, by IPL, by task, lateness, overhead)
    write(out_dir, label, run, result)    -> the raw run (JSON, CSV) and the report (JSON, markdown)
    compare(a.json, b.json)               -> markdown: per function, A vs B

Measured, not assumed: the elapsed time is the audio frames' (1,500 a second); DMA timer 0's rate is
measured against them (its counter is unwrapped from the status polls, at most `POLL_S` apart: it wraps
every 32.5 s at 132 MHz); the overhead is the firmware's own sum of its handler's time in those ticks.
"Idle" is a sample at the idle task's spin (0x400cf246, bra.s *) with the interrupt mask at 0: what the
meter's C label calls idle too, but the meter counts the interrupts that land in it as idle (docs/remote-ui.md).
"""

from __future__ import annotations

import csv
import json
import pathlib
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

from . import protocol as P
from .symbols import AUDIO_ISR, IDLE_PC, IDLE_TCB, Symbols
from .unit import NoTestChannel, StatusError

FRAMES_PER_S = 1500
POLL_S = 1.0
TOP = 40


@dataclass
class Run:
    label: str
    source: str
    rate_asked: int
    build: str
    started: str
    statuses: list[dict] = field(default_factory=list)        # every status seen, in order (asdict)
    meter_c_pm: list[int] = field(default_factory=list)       # the meter's C figure (TLM word 6), each poll
    samples: list[tuple[int, int, int, int]] = field(default_factory=list)   # pc, tcb, sr, late
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Run":
        r = cls(**{k: d[k] for k in ("label", "source", "rate_asked", "build", "started")})
        r.statuses, r.meter_c_pm, r.notes = d["statuses"], d["meter_c_pm"], d.get("notes", [])
        r.samples = [tuple(s) for s in d["samples"]]
        return r


def _meter(unit) -> int | None:
    try:
        return unit.tlm().c_pm
    except (NoTestChannel, StatusError, ValueError):
        return None


def run(ch, seconds: float, rate: int = 997, source: str = "auto", label: str = "run", log=print) -> Run:
    """PROFILE on the unit (or the simulator): start, poll every POLL_S, stop at SECONDS or a full ring, read"""
    info = ch.info()
    ch.require("PROFILE")
    r = Run(label, source, rate, info.label, time.strftime("%Y-%m-%d %H:%M:%S"))
    st = ch.profile_status()
    if st.state == "running":
        raise SystemExit("a profile already runs on the unit: `dn2test profile --stop` first")
    order = ["timer", "audio"] if source == "auto" else [source]
    for src in order:
        try:
            st = ch.profile_start(rate if src == "timer" else min(rate, FRAMES_PER_S), src)
            r.source = src
            break
        except StatusError as e:
            why = P.PROF_WHY.get(ch.profile_status().why, "?")
            r.notes.append(f"{src} source refused: status {e.status}, {why}")
            log(f"PROFILE {src}: refused ({why})")
    else:
        raise SystemExit("no profiler source could start: " + "; ".join(r.notes))
    r.statuses.append(asdict(st))
    log(f"PROFILE {r.source} at {rate} Hz asked: running for {seconds:g} s (ring {st.capacity} samples)")
    t_end = ch.unit.clock() + seconds
    while t_end - ch.unit.clock() > 1e-3:
        ch.unit.wait(min(POLL_S, max(0.0, t_end - ch.unit.clock())))
        st = ch.profile_status()
        r.statuses.append(asdict(st))
        m = _meter(ch.unit)
        if m is not None:
            r.meter_c_pm.append(m)
        if st.state != "running":
            r.notes.append(f"the ring filled after {st.samples} samples")
            break
    st = ch.profile_stop()
    r.statuses.append(asdict(st))
    r.samples = [(s.pc, s.tcb, s.sr, s.late) for s in ch.profile_read(0, st.samples)]
    log(f"PROFILE stopped: {len(r.samples)} samples read")
    return r


def clocks(r: Run) -> dict:
    """elapsed seconds (audio frames), DMA timer 0 ticks (unwrapped across the polls), rates, overhead"""
    s = r.statuses
    first, last = s[0], s[-1]
    frames = (last["f_now"] - first["f_start"]) & 0xFFFFFFFF
    ticks, prev = 0, first["t_start"]
    for st in s:
        ticks += (st["t_now"] - prev) & 0xFFFFFFFF
        prev = st["t_now"]
    elapsed = frames / FRAMES_PER_S if frames else None
    out = {"frames": frames, "elapsed_s": elapsed, "dtim0_ticks": ticks, "samples": last["samples"],
           "period_ticks": last["period_ticks"], "late_over_period": last["late"], "late_max_ticks": last["late_max"],
           "isr_ticks": last["isr_ticks"], "fires": last["fires"], "dropped": last["dropped"],
           "dtim0_regs": f"DTMR0 {last['dtim0'] >> 16:#06x} DTXMR0 {last['dtim0'] >> 8 & 0xFF:#04x} DTER0 {last['dtim0'] & 0xFF:#04x}",
           "dtrr0": f"{last['dtrr0']:#010x}", "vector96": f"{last['vector96']:#010x}"}
    out["dtim0_hz"] = ticks / elapsed if elapsed else None
    out["rate_hz"] = last["samples"] / elapsed if elapsed else None
    out["overhead_pct"] = 100.0 * last["isr_ticks"] / ticks if ticks and r.source == "timer" else None
    return out


def _ipl_name(ipl: int) -> str:
    return "task (mask 0)" if ipl == 0 else f"mask {ipl} (an interrupt at level {ipl}, or code masking to it)"


def analyse(r: Run, sym: Symbols) -> dict:
    n = len(r.samples)
    if not n:
        return {"samples": 0, "clocks": clocks(r) if r.statuses else {}}
    named = [(sym.lookup(pc), pc, tcb, sr >> 8 & 7, late) for pc, tcb, sr, late in r.samples]
    idle = sum(1 for _nm, pc, _t, ipl, _l in named if pc == IDLE_PC and ipl == 0)
    funcs = Counter(nm[0] for nm, *_ in named)
    origin = Counter(nm[1] for nm, *_ in named)
    ipls = Counter(ipl for _nm, _pc, _t, ipl, _l in named)
    per_ipl: dict[int, Counter] = defaultdict(Counter)
    tasks: Counter = Counter()
    per_task: dict[int, Counter] = defaultdict(Counter)
    for nm, _pc, tcb, ipl, _l in named:
        per_ipl[ipl][nm[0]] += 1
        if ipl == 0:
            tasks[tcb] += 1
            per_task[tcb][nm[0]] += 1
    in_audio = sum(1 for nm, *_ in named if nm[0] == "audio_isr")
    lates = sorted(late for *_x, late in named)
    pct = 100.0 / n
    c = clocks(r)
    us = 1e6 / c["dtim0_hz"] if c.get("dtim0_hz") else 1e6 / 132e6
    meter = [m / 10.0 for m in r.meter_c_pm if m is not None]
    return {
        "label": r.label, "build": r.build, "source": r.source, "started": r.started, "samples": n, "clocks": c,
        "idle_pct": idle * pct, "busy_pct": 100 - idle * pct,
        "meter_c_pct": {"mean": statistics.fmean(meter), "min": min(meter), "max": max(meter)} if meter else None,
        "origin_pct": {k: v * pct for k, v in origin.most_common()},
        "functions_pct": {k: v * pct for k, v in funcs.most_common()},
        "busy_functions_pct": {k: v * 100.0 / max(1, n - idle) for k, v in funcs.most_common() if k != _idle_name(sym)},
        "ipl_pct": {str(k): v * pct for k, v in sorted(ipls.items())},
        "ipl_top": {str(k): {f: v * pct for f, v in cnt.most_common(10)} for k, cnt in sorted(per_ipl.items())},
        "audio_isr_entry_pct": in_audio * pct,
        "tasks_pct": {f"{t:#010x}": v * pct for t, v in tasks.most_common()},
        "task_top": {f"{t:#010x}": {f: v * pct for f, v in per_task[t].most_common(6)} for t, _v in tasks.most_common(12)},
        "late_us": {"median": lates[len(lates) // 2] * us, "p95": lates[int(len(lates) * 0.95)] * us,
                    "p99": lates[min(len(lates) - 1, int(len(lates) * 0.99))] * us, "max": lates[-1] * us,
                    "clamped": sum(1 for x in lates if x >= 0xFFFF)} if r.source == "timer" else None,
        "notes": r.notes,
    }


def _idle_name(sym: Symbols) -> str:
    return sym.lookup(IDLE_PC)[0]


def write(out: str | pathlib.Path, r: Run, res: dict, sym: Symbols) -> tuple[pathlib.Path, pathlib.Path]:
    """-> (report json, report md); the raw run beside them (LABEL.raw.json, LABEL.samples.csv)"""
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{r.label}.raw.json").write_text(json.dumps(r.to_json()))
    with open(out / f"{r.label}.samples.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pc", "tcb", "sr", "ipl", "late_ticks", "function", "origin"])
        for pc, tcb, sr, late in r.samples:
            name, origin = sym.lookup(pc)
            w.writerow([f"{pc:#010x}", f"{tcb:#010x}", f"{sr:#06x}", sr >> 8 & 7, late, name, origin])
    j = out / f"{r.label}.json"
    j.write_text(json.dumps(res, indent=1))
    m = out / f"{r.label}.md"
    m.write_text(markdown(res))
    return j, m


def _f(v, fmt="{:.1f}") -> str:
    return "n/a" if v is None else fmt.format(v)


def markdown(res: dict) -> str:
    if not res.get("samples"):
        return "# CPU profile\n\nno samples\n"
    c = res["clocks"]
    meter = res["meter_c_pct"]
    lines = [
        f"# CPU profile: {res['label']}", "",
        f"build `{res['build']}`, source **{res['source']}**, {res['samples']:,} samples over {_f(c['elapsed_s'], '{:.2f}')} s "
        f"(audio frames), {_f(c['rate_hz'])} samples/s; started {res['started']}", "",
        "| | |", "|---|---|",
        f"| **idle** (the idle task's spin, mask 0) | **{res['idle_pct']:.1f} %** |",
        f"| **busy** (everything else the samples saw) | **{res['busy_pct']:.1f} %** |",
        f"| the meter's C during the run (mean, min..max) | {_f(meter and meter['mean'])} % "
        f"({_f(meter and meter['min'])}..{_f(meter and meter['max'])}) |",
        f"| inside the audio interrupt's own function (0x{AUDIO_ISR:08x}) | {res['audio_isr_entry_pct']:.1f} % |",
        f"| DMA timer 0, measured against the audio frames | {_f(c['dtim0_hz'] and c['dtim0_hz'] / 1e6, '{:.3f}')} MHz |",
        f"| the profiler's own handler (measured, entry and rte aside) | {_f(c['overhead_pct'], '{:.3f}')} % |",
        f"| samples more than a period late / latest | {c['late_over_period']} / {c['late_max_ticks']} ticks |",
        f"| dropped | {c['dropped']} |", "",
    ]
    if res.get("late_us"):
        lu = res["late_us"]
        lines += [f"Lateness (a sample due inside a masked section is taken when it ends): median {lu['median']:.1f} us, "
                  f"p95 {lu['p95']:.1f} us, p99 {lu['p99']:.1f} us, max {lu['max']:.1f} us ({lu['clamped']} clamped).", ""]
    lines += ["## By interrupt mask", "", "| mask | % | top |", "|---|---|---|"]
    for k, v in res["ipl_pct"].items():
        top = ", ".join(f"{f} {p:.1f}" for f, p in list(res["ipl_top"][k].items())[:5])
        lines.append(f"| {_ipl_name(int(k))} | {v:.1f} | {top} |")
    lines += ["", f"## Functions (top {TOP}, % of all samples)", "", "| function | % |", "|---|---|"]
    lines += [f"| {f} | {v:.2f} |" for f, v in list(res["functions_pct"].items())[:TOP]]
    lines += ["", "## Tasks (mask 0 samples, by the running TCB)", "", "| TCB | % | top functions |", "|---|---|---|"]
    for t, v in list(res["tasks_pct"].items())[:12]:
        tag = " (idle, prio 1)" if int(t, 16) == IDLE_TCB else ""
        top = ", ".join(f"{f} {p:.1f}" for f, p in res["task_top"].get(t, {}).items())
        lines.append(f"| {t}{tag} | {v:.1f} | {top} |")
    lines += ["", "By origin: " + ", ".join(f"{k} {v:.1f} %" for k, v in res["origin_pct"].items()), ""]
    if res.get("notes"):
        lines += ["Notes: " + "; ".join(res["notes"]), ""]
    return "\n".join(lines)


def compare(a_path: str, b_path: str, top: int = TOP) -> str:
    """two report JSONs -> markdown: idle, mask levels, and every function in either's top, A vs B"""
    a, b = (json.loads(pathlib.Path(p).read_text()) for p in (a_path, b_path))
    rows = [f"# CPU profile: {a['label']} (A) vs {b['label']} (B)", "",
            "| | A | B | B - A |", "|---|---|---|---|",
            f"| samples | {a['samples']:,} | {b['samples']:,} | |",
            f"| idle % | {a['idle_pct']:.1f} | {b['idle_pct']:.1f} | {b['idle_pct'] - a['idle_pct']:+.1f} |",
            f"| busy % | {a['busy_pct']:.1f} | {b['busy_pct']:.1f} | {b['busy_pct'] - a['busy_pct']:+.1f} |"]
    for k in sorted(set(a["ipl_pct"]) | set(b["ipl_pct"])):
        va, vb = a["ipl_pct"].get(k, 0.0), b["ipl_pct"].get(k, 0.0)
        rows.append(f"| mask {k} % | {va:.1f} | {vb:.1f} | {vb - va:+.1f} |")
    names = list(dict.fromkeys(list(a["functions_pct"])[:top] + list(b["functions_pct"])[:top]))
    diff = sorted(names, key=lambda f: -abs(b["functions_pct"].get(f, 0.0) - a["functions_pct"].get(f, 0.0)))
    rows += ["", "| function | A % | B % | B - A |", "|---|---|---|---|"]
    for f in diff:
        va, vb = a["functions_pct"].get(f, 0.0), b["functions_pct"].get(f, 0.0)
        rows.append(f"| {f} | {va:.2f} | {vb:.2f} | {vb - va:+.2f} |")
    return "\n".join(rows) + "\n"
