"""Clear a build in about an hour: every ship_gate step alone, in parallel, then ONE full run (2026-11-16).

    gate_parallel.py TREE STOCK BUILD --run-dir DIR [--jobs 8] [--max-jobs 20] [--reserve-gb 16]
                     [--wrap 'BENCH {tree}'] [--venv PY] [--steps a,b,...]

1. Each step that the gate can reuse (ship_gate.py --list --json: "reused") runs alone (`ship_gate.py --only STEP`)
   in its own copy of TREE, longest first (each step's expected time, measured), at most JOBS at once, each under
   its limit (a step that runs past it is killed and fails). A step starts only while the machine has room for it:
   the memory available, less what our running steps may still grow to (each step's measured peak), must hold the
   step's own peak and RESERVE more. JOBS can be changed while it runs: `echo N > DIR/jobs`.
2. If every step passed, each copy's reuse records (out/gate_cache) are merged into TREE's: every record kept once,
   newest last, gate_cache.KEEP a step. Nothing is judged here.
3. ONE full `ship_gate.py` run on TREE. It reuses a step's pass only when every input the step read re-hashes
   identical (gate_cache.lookup), runs every step it cannot reuse, and runs the never-reused steps itself. Only that
   run can print CLEARED TO FLASH, as always.

The copies must run at TREE's own path for their records to name TREE's files: --wrap names a command that runs
ship_gate with the copy mounted where TREE is (the farm: $BENCH/bench_ns112.sh {tree}, a mount namespace).
Without --wrap the copies' records name the copies' paths, and the full run cannot reuse them (it runs every step).

Results: DIR/results.tsv (step, rc, seconds, peak GB), DIR/logs/<step>.log, DIR/logs/FULL.log, DIR/summary.json;
DIR/kept/<step>/ each step's own ship_gate logs and SHARC runner reports; DIR/records/<step>/ its reuse records.
A failed step's copy stays in DIR/copies.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gate_cache  # noqa: E402

GB = 1 << 30


def mem_available() -> int | None:
    """MemAvailable in bytes (Linux), None elsewhere (no memory check: JOBS alone limits)"""
    try:
        for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def proc_table() -> tuple[dict[int, list[int]], dict[int, int]]:
    """every process's children and resident memory (bytes), from /proc (empty where there is none)"""
    kids: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    for d in pathlib.Path("/proc").glob("[0-9]*"):
        try:
            stat = (d / "stat").read_text()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
            kids.setdefault(ppid, []).append(int(d.name))
            for line in (d / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    rss[int(d.name)] = int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            continue
    return kids, rss


def tree_rss(pid: int, kids: dict[int, list[int]], rss: dict[int, int]) -> int:
    """the resident memory of PID and all its descendants, bytes"""
    total, todo = 0, [pid]
    while todo:
        p = todo.pop()
        total += rss.get(p, 0)
        todo += kids.get(p, [])
    return total


class Job:
    def __init__(self, step: dict):
        self.step = step
        self.proc: subprocess.Popen | None = None
        self.start = 0.0
        self.peak = 0
        self.rc: int | None = None
        self.copy: pathlib.Path | None = None
        self.killed = False


def list_steps(args, env) -> list[dict]:
    cmd = wrap(args, args.tree) + [args.python, "scripts/ship_gate.py", "--list", "--json"]
    out = subprocess.run(cmd, cwd=args.tree, env={**env, "PYTHONDONTWRITEBYTECODE": "1"},
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"ship_gate.py --list --json failed:\n{out.stdout[-2000:]}{out.stderr[-2000:]}")
    return json.loads(out.stdout[out.stdout.index("["):])


def wrap(args, tree: pathlib.Path) -> list[str]:
    return [w.replace("{tree}", str(tree)) for w in shlex.split(args.wrap)] if args.wrap else []


def gate_cmd(args, tree: pathlib.Path, only: str | None) -> list[str]:
    cmd = wrap(args, tree) + [args.python, "scripts/ship_gate.py", str(args.stock), str(args.build)]
    if args.venv:
        cmd += ["--venv", args.venv]
    return cmd + (["--only", only] if only else [])


def jobs_limit(run_dir: pathlib.Path, default: int, ceiling: int) -> int:
    try:
        return max(1, min(int((run_dir / "jobs").read_text().strip()), ceiling))
    except (OSError, ValueError):
        return min(default, ceiling)


def copy_tree(src: pathlib.Path, dst: pathlib.Path) -> None:
    dst.mkdir(parents=True)
    ignore = shutil.ignore_patterns("ship_gate_*")          # older gate runs' work folders (out/ship_gate_*)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir() and not item.is_symlink():
            shutil.copytree(item, target, symlinks=True, ignore=ignore, copy_function=shutil.copy2)
        else:
            shutil.copy2(item, target, follow_symlinks=False)


def merge_records(copies: list[pathlib.Path], dst: pathlib.Path) -> int:
    """every copy's out/gate_cache/*.json into DST: each record once (cmds, inputs, build), by date, the last KEEP"""
    merged: dict[str, list] = {}
    for c in copies + [dst]:
        for f in sorted(c.glob("*.json")) if c.is_dir() else ():
            merged.setdefault(f.name, []).extend(json.loads(f.read_text()))
    dst.mkdir(parents=True, exist_ok=True)
    for name, recs in merged.items():
        seen, out = set(), []
        for r in sorted(recs, key=lambda r: r.get("date", "")):
            key = json.dumps([r.get("cmds"), r.get("inputs"), r.get("build")], sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append(r)
        (dst / name).write_text(json.dumps(out[-gate_cache.KEEP:], indent=1))
    return len(merged)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tree", type=pathlib.Path)
    p.add_argument("stock", type=pathlib.Path)
    p.add_argument("build", type=pathlib.Path)
    p.add_argument("--run-dir", type=pathlib.Path, required=True)
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--max-jobs", type=int, default=20, help="the ceiling, whatever DIR/jobs says")
    p.add_argument("--reserve-gb", type=float, default=16.0, help="memory left free beyond our steps' peaks")
    p.add_argument("--wrap", default="", help="command prefix that runs ship_gate with {tree} at TREE's path")
    p.add_argument("--python", default="python")
    p.add_argument("--venv", default="")
    p.add_argument("--steps", default="", help="only these steps in phase 1 (default: every reusable step)")
    p.add_argument("--no-full", action="store_true", help="stop after the merge (never a clearance)")
    args = p.parse_args()
    args.tree, args.run_dir = args.tree.resolve(), args.run_dir.resolve()
    args.stock, args.build = args.stock.resolve(), args.build.resolve()
    run_dir = args.run_dir
    for d in ("logs", "copies", "tmp"):
        (run_dir / d).mkdir(parents=True, exist_ok=True)
    (run_dir / "jobs").write_text(f"{args.jobs}\n")
    (args.tree / "out").mkdir(exist_ok=True)        # before the copies: the tree's listing is an input of some steps
    env = dict(os.environ)
    t0 = time.time()

    def say(msg: str) -> None:
        line = f"[gate_parallel {time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(run_dir / "gate_parallel.log", "a") as f:
            f.write(line + "\n")

    steps = [s for s in list_steps(args, env) if s["reused"]]
    if args.steps:
        want = set(args.steps.split(","))
        steps = [s for s in steps if s["id"] in want]
    steps.sort(key=lambda s: -s["expect_s"])                # longest first
    say(f"{len(steps)} steps, longest first: " + ", ".join(f"{s['id']} ~{s['expect_s']}s" for s in steps))

    pending, running, done = list(steps), [], []
    lock = threading.Lock()
    results = run_dir / "results.tsv"
    results.write_text("")

    def finish(job: Job) -> None:
        secs = round(time.time() - job.start)
        with lock, open(results, "a") as f:
            f.write(f"{job.step['id']}\t{job.rc}\t{secs}\t{job.peak / GB:.1f}\n")
        say(f"end {job.step['id']}: rc {job.rc}, {secs} s (expected {job.step['expect_s']}), peak {job.peak / GB:.1f} GB")

    def room_for(step: dict) -> bool:
        avail = mem_available()
        if avail is None:
            return True
        growth = sum(max(0, int(j.step["mem_gb"] * GB) - j.peak) for j in running)
        return avail - growth >= (step["mem_gb"] + args.reserve_gb) * GB

    while pending or running:
        table = proc_table() if running else ({}, {})
        for job in list(running):
            if job.proc.poll() is None:
                job.peak = max(job.peak, tree_rss(job.proc.pid, *table))
                if time.time() - job.start > job.step["limit_s"] and not job.killed:
                    say(f"{job.step['id']} past its limit of {job.step['limit_s']} s: killed (a failed step)")
                    job.killed = True
                    try:
                        os.killpg(job.proc.pid, signal.SIGKILL)
                    except OSError:
                        job.proc.kill()
                continue
            job.rc = job.proc.returncode
            running.remove(job)
            done.append(job)
            finish(job)
            recs = run_dir / "records" / job.copy.name           # the step's reuse records, kept for the merge
            shutil.rmtree(recs, ignore_errors=True)
            if (job.copy / "out" / "gate_cache").is_dir():
                shutil.copytree(job.copy / "out" / "gate_cache", recs)
            keep = run_dir / "kept" / job.copy.name              # the step's own logs and the runner's reports
            shutil.rmtree(keep, ignore_errors=True)
            for w in (job.copy / "out").glob("ship_gate_*/logs"):
                shutil.copytree(w, keep / "logs", dirs_exist_ok=True)
            for r in (job.copy / "out" / "waverider").glob("m5_report_*.json"):
                keep.mkdir(parents=True, exist_ok=True)
                shutil.copy2(r, keep / r.name)
            if job.rc in (0, 3):
                shutil.rmtree(job.copy, ignore_errors=True)
                shutil.rmtree(run_dir / "tmp" / job.copy.name, ignore_errors=True)
        limit = jobs_limit(run_dir, args.jobs, args.max_jobs)
        while pending and len(running) < limit:
            # the longest step that has room now (a big one waiting for memory does not hold up the rest)
            step = next((s for s in pending if room_for(s)), None)
            if step is None:
                break
            pending.remove(step)
            job = Job(step)
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in step["id"])
            job.copy = run_dir / "copies" / safe
            shutil.rmtree(job.copy, ignore_errors=True)
            copy_tree(args.tree, job.copy)
            tmp = run_dir / "tmp" / safe
            tmp.mkdir(parents=True, exist_ok=True)
            log = open(run_dir / "logs" / f"{safe}.log", "w")
            job.proc = subprocess.Popen(["nice", "-n", "19", *gate_cmd(args, job.copy, step["id"])], cwd=job.copy,
                                        env={**env, "BENCH_TMP": str(tmp), "TMPDIR": str(tmp)},
                                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            job.start = time.time()
            running.append(job)
            say(f"start {step['id']} ({len(running)} running, limit {limit})")
        time.sleep(5)

    bad = [j for j in done if j.rc not in (0, 3)]
    wall1 = round(time.time() - t0)
    summary = {"steps_wall_s": wall1, "steps": {j.step["id"]: {"rc": j.rc, "peak_gb": round(j.peak / GB, 1)}
                                                for j in done}}
    if bad:
        say(f"steps failed: {', '.join(j.step['id'] for j in bad)} -- no full run (copies kept: {run_dir / 'copies'})")
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
        return 1
    n = merge_records(sorted((run_dir / "records").glob("*")), args.tree / "out" / "gate_cache")
    say(f"merged {n} record files into {args.tree / 'out' / 'gate_cache'}")
    if args.no_full:
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
        return 0
    say("the full run")
    t1 = time.time()
    tmp = run_dir / "tmp" / "FULL"
    tmp.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "logs" / "FULL.log", "w") as log:
        rc = subprocess.run(["nice", "-n", "19", *gate_cmd(args, args.tree, None)], cwd=args.tree,
                            env={**env, "BENCH_TMP": str(tmp), "TMPDIR": str(tmp)},
                            stdout=log, stderr=subprocess.STDOUT).returncode
    summary.update(full_rc=rc, full_wall_s=round(time.time() - t1), wall_s=round(time.time() - t0))
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    say(f"full run rc {rc}, {summary['full_wall_s']} s; total {summary['wall_s']} s")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
