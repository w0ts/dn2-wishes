"""One run queue for every dn2-wishes session (2026-11-12, the User: "mutualise runs"; docs/runq.md).

Sessions hand their heavy jobs (SHARC runner steps, regenerations, gate steps, emulator runs)
to this queue instead of starting them themselves. A job is the caller's tree as it is now
(snapshotted at submit), a kind and a command. The same tree, kind and command run once: a
second submitter joins the job that is queued or running, and a later one gets its stored
result (a passing one: a failure runs again). One dispatcher starts jobs on the Mac or on
gpufarm within the User's limits (scripts/runq_hosts.py): on gpufarm at most 32 CPUs of ours
at any time, all our processes counted, and its load watched; on the Mac at most two jobs,
and none while its load is high.

    runq.py submit [--kind K] [--host H] [--cpus N] [--prio P] [--env K=V] [--collect GLOB]
                   [--timeout S] [--fresh] [--wait] -- CMD ...   -> the job's id
    runq.py wait ID         block until done; exits with the job's rc; prints the result dir
    runq.py result ID       the job's record (JSON)
    runq.py log ID          its log (also while it runs)
    runq.py fetch ID [DIR]  copy its collected files into DIR (default: the current tree)
    runq.py status          queue, running, recent results, CPU and load on both hosts
    runq.py gc [--days N]   remove old results, unused snapshots, finished work trees

In a command, {STOCK111}, {STOCK112} and {DIGIKIT} are the host's own paths; an absolute path
outside the tree (whole, or after '=') is shipped with the job. State lives in the main
checkout's scratch/runq/ (git-ignored), shared by every worktree; RUNQ_DIR overrides it.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runq_hosts as H                          # noqa: E402

IDLE_EXIT_S = 600                                # the dispatcher leaves after this long with nothing to do
TICK_S = 15
MAX_ERRORS = 20                                  # a job whose host keeps failing ends (rc 125) after this many
LIVE = ("queued", "starting", "running", "joined")


# -- where things live ---------------------------------------------------------------------------

def qdir() -> pathlib.Path:
    """the shared queue directory: RUNQ_DIR, else scratch/runq in the main checkout of the
    repository this script belongs to (its git common directory's parent)"""
    env = os.environ.get("RUNQ_DIR")
    if env:
        d = pathlib.Path(env)
    else:
        here = pathlib.Path(__file__).resolve().parent
        common = subprocess.run(["git", "-C", str(here), "rev-parse", "--git-common-dir"],
                                capture_output=True, text=True, check=True).stdout.strip()
        d = (here / common).resolve().parent / "scratch" / "runq"
    for sub in ("jobs", "trees", "results", "work"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


class Lock:
    """the queue's lock (fcntl), held only for quick bookkeeping, never across a host's work"""

    def __init__(self, d: pathlib.Path):
        self.f = open(d / "lock", "a+")

    def __enter__(self):
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def _write_json(path: pathlib.Path, obj) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(3).hex()}")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(path)


def load_job(d: pathlib.Path, jid: str) -> dict:
    return json.loads((d / "jobs" / f"{jid}.json").read_text())


def save_job(d: pathlib.Path, job: dict) -> None:
    _write_json(d / "jobs" / f"{job['id']}.json", job)


def all_jobs(d: pathlib.Path) -> list[dict]:
    out = []
    for f in (d / "jobs").glob("*.json"):
        try:
            out.append(json.loads(f.read_text()))
        except (ValueError, OSError):
            continue
    return out


def job_key(tree: str, kind: str, cmd: list[str], env: dict, collect: list[str],
            files: dict[str, str]) -> str:
    """the dedup key: the same tree content, kind, command (shipped files by their content),
    environment and collected outputs run once"""
    norm = []
    for a in cmd:
        for path, sha in files.items():
            a = a.replace(path, f"@file:{sha}")
        norm.append(a)
    blob = json.dumps([tree, kind, norm, sorted(env.items()), sorted(collect)], separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def _stored(d: pathlib.Path, key: str) -> dict | None:
    """the stored result for KEY, if it passed (a failure or a timeout runs again)"""
    f = d / "results" / key / "meta.json"
    try:
        meta = json.loads(f.read_text())
    except (OSError, ValueError):
        return None
    return meta if meta.get("rc") == 0 else None


# -- submit, wait --------------------------------------------------------------------------------

def submit(a) -> str:
    d = qdir()
    top = pathlib.Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                                      text=True, check=True).stdout.strip())
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        raise SystemExit("runq: no command")
    hosts, cpus, timeout = H.KINDS[a.kind]
    if a.host:
        if a.host not in hosts and a.kind != "cmd":
            raise SystemExit(f"runq: kind {a.kind} runs on {'/'.join(hosts)} only")
        hosts = (a.host,)
    env = dict(e.split("=", 1) for e in a.env)
    collect = [H.check_glob(g) for g in a.collect]
    outside = H.outside_files(cmd, top)
    th, tar = H.snapshot(d / "trees", top, H.tree_files(top), outside)
    key = job_key(th, a.kind, cmd, env, collect, outside)
    jid = time.strftime("%Y%m%d-%H%M%S") + "-" + key[:6] + "-" + os.urandom(2).hex()
    job = {"id": jid, "key": key, "kind": a.kind, "cmd": cmd, "env": env, "collect": collect,
           "files": outside, "tree": th, "tar": str(tar), "hosts": list(hosts), "cpus": a.cpus or cpus,
           "timeout": a.timeout or timeout, "prio": a.prio, "submitted": time.time(),
           "by": a.by or os.environ.get("RUNQ_BY", top.name), "state": "queued"}
    with Lock(d):
        meta = None if a.fresh else _stored(d, key)
        live = [j for j in all_jobs(d) if j["key"] == key and j["state"] in ("queued", "starting", "running")]
        if meta:
            job.update(state="done", rc=0, result=str(d / "results" / key), reused=meta["id"], ended=time.time())
        elif live and not a.fresh:
            job.update(joined=live[0]["id"], state="joined")
        save_job(d, job)
    if job["state"] in ("queued", "joined"):
        ensure_dispatcher(d)
    how = {"done": f"reused {job.get('reused')}", "joined": f"joined {job.get('joined')}",
           "queued": "queued"}[job["state"]]
    print(f"{jid}  {how}", file=sys.stderr)
    return jid


def _settle_joined(d: pathlib.Path, job: dict) -> dict:
    """a joined job takes its lead's end (or ends with 125 if the lead's record is gone)"""
    try:
        lead = load_job(d, job["joined"])
    except (OSError, ValueError):
        job.update(state="done", rc=125, note=f"its lead {job['joined']} is gone", ended=time.time())
        save_job(d, job)
        return job
    if lead["state"] == "done":
        job.update(state="done", rc=lead.get("rc", 125), result=lead.get("result"),
                   note=lead.get("note", ""), ended=lead.get("ended", time.time()))
        save_job(d, job)
    return job


def wait(jid: str, poll_s: float = 5.0) -> dict:
    d = qdir()
    while True:
        job = load_job(d, jid)
        if job["state"] == "joined":
            with Lock(d):
                job = _settle_joined(d, load_job(d, jid))
        if job["state"] == "done":
            return job
        ensure_dispatcher(d)
        time.sleep(poll_s)


# -- the dispatcher ------------------------------------------------------------------------------

def _end(d: pathlib.Path, job: dict, rc: int, result: str | None, note: str = "") -> None:
    job.update(state="done", rc=rc, result=result, ended=time.time())
    if note:
        job["note"] = note
    with Lock(d):
        save_job(d, job)
        for w in all_jobs(d):
            if w.get("joined") == job["id"] and w["state"] == "joined":
                _settle_joined(d, w)


def _finish(d: pathlib.Path, job: dict, rc: int) -> None:
    """keep the log, rc and collected files under results/KEY (whole, or not at all), then
    remove the job's tree"""
    res = d / "results" / job["key"]
    tmp = d / "results" / f".{job['key']}.{job['id']}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        H.collect(job, tmp)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    meta = {k: job[k] for k in ("key", "kind", "cmd", "env", "collect", "tree", "host", "started", "by")}
    meta.update(rc=rc, ended=time.time(), id=job["id"])
    _write_json(tmp / "meta.json", meta)
    old = d / "results" / f".{job['key']}.old.{job['id']}"
    if res.exists():
        res.replace(old)
    tmp.replace(res)
    shutil.rmtree(old, ignore_errors=True)
    try:
        H.remove(job)
    except H.HostError:
        pass                                        # gc removes it later
    _end(d, job, rc, str(res))


def _tend(d: pathlib.Path, job: dict, now: float) -> None:
    """one running job: has it ended?"""
    try:
        rc = H.poll(job, now)
        if rc is None:
            return
        if rc == "gone":
            _end(d, job, 125, None, "its tree vanished before it ended")
            return
        _finish(d, job, rc)
    except Exception as e:                          # a host's trouble must not stop the queue
        job["errors"] = job.get("errors", 0) + 1
        job["note"] = f"{type(e).__name__}: {e}"[:300]
        if job["errors"] >= MAX_ERRORS:
            _end(d, job, 125, None, "gave up: " + job["note"])
        else:
            with Lock(d):
                save_job(d, job)


def dispatch_once(d: pathlib.Path) -> bool:
    """one pass: finish ended jobs, start what the limits allow. -> whether anything is left"""
    now = time.time()
    for j in [j for j in all_jobs(d) if j["state"] == "running"]:
        _tend(d, j, now)                            # only the dispatcher changes running jobs
    queued = sorted((j for j in all_jobs(d) if j["state"] == "queued"),
                    key=lambda j: (-j["prio"], j["submitted"]))
    farm = H.farm_usage() if any("farm" in j["hosts"] for j in queued) else None
    for j in queued:
        with Lock(d):                               # claim it: a host and a start time
            try:
                j = load_job(d, j["id"])
            except (OSError, ValueError):
                continue
            running = [r for r in all_jobs(d) if r["state"] in ("starting", "running")]
            host = H.place(j, running, H.mac_load(), farm, time.time()) if j["state"] == "queued" else None
            if host is None:
                continue
            j.update(state="starting", host=host, started=time.time())
            save_job(d, j)
        try:
            j.update(H.start(j, d / "work" / j["id"]))
            j["state"] = "running"
            if host == "farm" and farm is not None:
                farm = (farm[0], farm[1] + j["cpus"])
        except Exception as e:                      # back in the queue; a later attempt starts afresh
            j.update(state="queued", attempt=j.get("attempt", 0) + 1, errors=j.get("errors", 0) + 1,
                     note=f"start on {host} failed: {e}"[:300])
            j.pop("host", None)
            if j["errors"] >= MAX_ERRORS:
                j.update(state="done", rc=125, result=None, ended=time.time())
        with Lock(d):
            save_job(d, j)
    return any(j["state"] in LIVE for j in all_jobs(d))


def dispatcher(d: pathlib.Path) -> None:
    lockf = open(d / "dispatcher.lock", "a+")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return                                      # one is running already
    pid = d / "dispatcher.pid"
    pid.write_text(str(os.getpid()))
    idle_since = time.time()
    try:
        while True:
            try:
                busy = dispatch_once(d)
            except Exception as e:                  # logged; the next pass tries again
                print(time.strftime("%H:%M:%S"), "dispatch:", type(e).__name__, e, flush=True)
                busy = True
            if busy:
                idle_since = time.time()
            elif time.time() - idle_since > IDLE_EXIT_S:
                break
            time.sleep(TICK_S)
    finally:
        pid.unlink(missing_ok=True)
        fcntl.flock(lockf, fcntl.LOCK_UN)
        lockf.close()
    # a job submitted while this one was leaving found the lock held: see to it
    if any(j["state"] in ("queued", "joined") for j in all_jobs(d)):
        ensure_dispatcher(d)


def ensure_dispatcher(d: pathlib.Path) -> None:
    if os.environ.get("RUNQ_NO_DISPATCHER"):         # the tests drive dispatch_once themselves
        return
    lockf = open(d / "dispatcher.lock", "a+")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return                                      # held: a dispatcher is alive
    fcntl.flock(lockf, fcntl.LOCK_UN)
    lockf.close()
    subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve()), "_dispatch"],
                     stdin=subprocess.DEVNULL, stdout=open(d / "dispatcher.log", "a"),
                     stderr=subprocess.STDOUT, start_new_session=True, env={**os.environ, "RUNQ_DIR": str(d)})


# -- status, gc, fetch ---------------------------------------------------------------------------

def status(d: pathlib.Path) -> str:
    jobs = sorted(all_jobs(d), key=lambda j: j["submitted"])
    now = time.time()
    lines = [f"Mac load {H.mac_load():.1f} of {H.MAC_CORES} cores (a job starts when its threads fit half the free cores, "
             f"<= {H.MAC_JOBS_MAX} jobs)"]
    fu = H.farm_usage()
    lines.append("gpufarm: unreachable" if fu is None else
                 f"gpufarm: our CPUs {fu[0]:.1f} of {H.farm_cpu_max(time.time()):g}, load {fu[1]:.1f} (starts at <= {H.FARM_LOAD_MAX:g})")
    lines.append(f"dispatcher: {'running' if (d / 'dispatcher.pid').exists() else 'idle'}")
    for sel in ("running", "starting", "queued", "joined"):
        js = [j for j in jobs if j["state"] == sel]
        if js:
            lines.append(f"{sel}:")
            for j in js:
                age = now - j.get("started", j["submitted"])
                where = f"-> {j['joined']}" if sel == "joined" else j.get("host", "/".join(j["hosts"]))
                lines.append(f"  {j['id']}  {j['kind']:6s} {where}  {j['cpus']:g} cpu  {age / 60:5.1f} min  "
                             f"{j['by']}  {' '.join(j['cmd'])[:60]}  {j.get('note', '')[:80]}")
    done = [j for j in jobs if j["state"] == "done"][-12:]
    if done:
        lines.append("recent:")
        for j in done:
            how = "reused" if j.get("reused") else "joined" if j.get("joined") else "ran"
            lines.append(f"  {j['id']}  {j['kind']:6s} rc {j.get('rc')}  {how}  {j['by']}  "
                         f"{' '.join(j['cmd'])[:60]}  {j.get('note', '')[:60]}")
    return "\n".join(lines)


def gc(d: pathlib.Path, days: float) -> list[str]:
    """results and records older than DAYS, snapshots no live job needs (older than a day), and
    work trees here and on gpufarm that belong to no live job"""
    now, gone = time.time(), []
    with Lock(d):
        jobs = all_jobs(d)
        live = {j["id"] for j in jobs if j["state"] in LIVE}
        tars = {j.get("tar") for j in jobs if j["id"] in live}
        for r in (d / "results").iterdir():
            if r.is_dir() and now - r.stat().st_mtime > days * 86400:
                shutil.rmtree(r, ignore_errors=True)
                gone.append(str(r))
        for t in (d / "trees").iterdir():
            if str(t) not in tars and now - t.stat().st_mtime > 86400:
                t.unlink()
                gone.append(str(t))
        for j in jobs:
            if j["id"] not in live and now - j.get("ended", j["submitted"]) > days * 86400:
                (d / "jobs" / f"{j['id']}.json").unlink(missing_ok=True)
                gone.append(j["id"])
        for w in (d / "work").iterdir():
            if w.name not in live:
                shutil.rmtree(w, ignore_errors=True)
                gone.append(str(w))
    try:
        r = H.ssh(f"cd {H.FARM_ROOT}/work 2>/dev/null && for x in *; do [ -e \"$x\" ] || continue; "
                  f"case \"$x\" in {'|'.join(k + '-*' for k in live) or '-'}) ;; "
                  f"*) rm -rf \"$x\" && echo \"gpufarm:$x\";; esac; done", timeout=300)
        gone += r.stdout.decode().split()
    except H.HostError:
        pass
    return gone


def fetch(jid: str, into: pathlib.Path) -> list[str]:
    d = qdir()
    job = load_job(d, jid)
    if job["state"] == "joined":
        job = _settle_joined(d, job)
    if not job.get("result"):
        raise SystemExit(f"runq: {jid} has no result ({job['state']}{', ' + job['note'] if job.get('note') else ''})")
    src = pathlib.Path(job["result"]) / "files"
    out = []
    for f in sorted(src.rglob("*")):
        if f.is_file():
            dst = into / f.relative_to(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, dst)
            out.append(str(dst))
    return out


def _log(jid: str) -> str:
    d = qdir()
    job = load_job(d, jid)
    lead = load_job(d, job["joined"]) if job.get("joined") else job
    res = job.get("result") or lead.get("result")
    if res:
        return (pathlib.Path(res) / "log").read_text(errors="replace")
    if lead.get("host") == "mac" and lead.get("where"):
        return (pathlib.Path(lead["where"]) / "runq.log").read_text(errors="replace")
    if lead.get("host") == "farm" and lead.get("where"):
        return H.ssh(f"tail -c 20000 {lead['where']}/runq.log", timeout=40).stdout.decode(errors="replace")
    return f"({lead['state']}{': ' + lead['note'] if lead.get('note') else ''})\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="op", required=True)
    s = sub.add_parser("submit")
    s.add_argument("--kind", default="cmd", choices=sorted(H.KINDS))
    s.add_argument("--host", choices=("mac", "farm"))
    s.add_argument("--cpus", type=float)
    s.add_argument("--prio", type=int, default=0, help="higher first; the integrator's gate: 10")
    s.add_argument("--env", action="append", default=[], metavar="K=V")
    s.add_argument("--collect", action="append", default=[], metavar="GLOB",
                   help="files to keep from the job's tree (relative; ** allowed)")
    s.add_argument("--timeout", type=int)
    s.add_argument("--by", help="who submits (default RUNQ_BY or the tree's folder name)")
    s.add_argument("--fresh", action="store_true", help="run again although a result is stored")
    s.add_argument("--wait", action="store_true")
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    for name in ("wait", "result", "log"):
        sub.add_parser(name).add_argument("id")
    f = sub.add_parser("fetch")
    f.add_argument("id")
    f.add_argument("dir", nargs="?", default=".")
    sub.add_parser("status")
    g = sub.add_parser("gc")
    g.add_argument("--days", type=float, default=7.0)
    sub.add_parser("_dispatch")
    a = p.parse_args(argv)
    if a.op in ("submit", "wait"):
        jid = submit(a) if a.op == "submit" else a.id
        if a.op == "submit":
            print(jid)
            if not a.wait:
                return 0
        job = wait(jid)
        print(job.get("result") or f"no result: {job.get('note', '')}")
        return int(job.get("rc", 125))
    if a.op == "result":
        print(json.dumps(load_job(qdir(), a.id), indent=1))
    elif a.op == "log":
        sys.stdout.write(_log(a.id))
    elif a.op == "fetch":
        for x in fetch(a.id, pathlib.Path(a.dir)):
            print(x)
    elif a.op == "status":
        print(status(qdir()))
    elif a.op == "gc":
        for x in gc(qdir(), a.days):
            print("removed", x)
    elif a.op == "_dispatch":
        dispatcher(qdir())
    return 0


if __name__ == "__main__":
    sys.exit(main())
