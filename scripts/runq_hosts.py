"""The run queue's hosts (scripts/runq.py, docs/runq.md): the User's limits, the tree's snapshot,
and starting, watching, stopping and collecting a job on the Mac or on gpufarm."""

from __future__ import annotations

import glob
import hashlib
import io
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import tarfile
import time

FARM = os.environ.get("RUNQ_FARM_HOST", "gpufarm")
FARM_HOME = os.environ.get("RUNQ_FARM_HOME", "/home/mots")
FARM_BENCH = FARM_HOME + "/dn2mk2-bench"
FARM_ROOT = FARM_BENCH + "/runq"                 # the job trees, and seed/ (the runner's engine snapshot)
# the User's rule (2026-11-12): ours, all together, of gpufarm's 64 cores: 32 on weekdays 08:00-17:00 (local),
# 50 otherwise. RUNQ_FARM_CPUS sets one cap at all times
FARM_CPU_OFFICE, FARM_CPU_OFF_HOURS = 32.0, 50.0
FARM_CPU_FIXED = os.environ.get("RUNQ_FARM_CPUS")
FARM_LOAD_MAX = float(os.environ.get("RUNQ_FARM_LOAD", "60"))     # of its 64 cores: the colleagues' room
MAC_JOBS_MAX = int(os.environ.get("RUNQ_MAC_JOBS", "2"))
# the User's rule (2026-11-13, ~/.claude/rules/common/check-system-before-running.md: the Mac is in use, always): a Mac
# job starts only when its CPUs fit in half of the free cores (cores - load1, all our jobs' and everyone's work counted
# in the load), runs at nice 19, and its numeric libraries get no more threads than its CPUs
MAC_CORES = int(os.environ.get("RUNQ_MAC_CORES", str(os.cpu_count() or 8)))
MAC_THREAD_VARS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                   "NUMBA_NUM_THREADS")
RAMP_S = 90                                      # a job just started may not show its CPU yet
FILES_DIR = "_runq_files"                        # where files named outside the tree land in its copy

# kind -> (hosts it may run on, CPUs it takes, timeout in s). Measured on gpufarm 2026-11-12: a
# runner step or a gate part is one python process at 100 % of one core; a regeneration likewise.
KINDS = {
    "runner": (("farm",), 1, 7200),              # scripts/sharc_waverider_m5.py: digikit is on gpufarm
    "regen": (("farm",), 1, 1800),               # gen_*_asm + gen_waverider_sharc --assemble: selas is there
    "gate": (("farm",), 1, 7200),                # ship_gate.py --only STEP
    "emu": (("mac",), 2, 7200),                  # the ColdFire emulator (Docker on the Mac)
    "cmd": (("mac", "farm"), 1, 7200),           # anything else
}
PLACEHOLDERS = {
    "farm": {"{STOCK111}": FARM_BENCH + "/data112/stock112dist/Digitone_II_OS1.11.syx",
             "{STOCK112}": FARM_BENCH + "/data112/os112dl/Digitone_II_OS1.12.syx",
             "{DIGIKIT}": "/mnt/d/01_Code/Z_Personal/digikit-wt-sharcemu"},
    "mac": {},
}
GLOB_OK = re.compile(r"^[A-Za-z0-9_.*?\-/\[\]]+$")


class HostError(RuntimeError):
    """the host could not be reached or did not do what was asked: try again later"""


# -- the tree ------------------------------------------------------------------------------------

def check_glob(g: str) -> str:
    """a --collect pattern: relative, inside the tree, plain characters (it is expanded by a shell
    on gpufarm, so nothing it could run)"""
    if not GLOB_OK.match(g) or g.startswith("/") or ".." in g.split("/"):
        raise ValueError(f"runq: --collect {g!r}: a relative pattern of letters, digits, _ . - / * ? [ ]")
    return g


def tree_files(top: pathlib.Path) -> list[str]:
    """the tree's files as git sees them: tracked, and untracked but not ignored"""
    out = subprocess.run(["git", "-C", str(top), "ls-files", "-co", "--exclude-standard", "-z"],
                         capture_output=True, check=True).stdout.decode()
    return sorted(p for p in set(out.split("\0")) if p and (top / p).is_file() and not (top / p).is_symlink())


def outside_files(cmd: list[str], top: pathlib.Path) -> dict[str, str]:
    """absolute paths in the arguments (whole, or after an '=') naming a file outside the tree ->
    their sha256: shipped with the job and keyed by content"""
    out = {}
    for a in cmd:
        for cand in {a, a.split("=", 1)[-1]}:
            if not os.path.isabs(cand) or not os.path.isfile(cand):
                continue
            try:
                pathlib.Path(cand).resolve().relative_to(top.resolve())
            except ValueError:
                out[cand] = hashlib.sha256(pathlib.Path(cand).read_bytes()).hexdigest()
    return out


def shipped_name(path: str, sha: str) -> str:
    return f"{FILES_DIR}/{sha[:12]}-{os.path.basename(path)}"


def snapshot(trees: pathlib.Path, top: pathlib.Path, files: list[str],
             outside: dict[str, str]) -> tuple[str, pathlib.Path]:
    """-> (the tree's hash, its tar). Each file is read once: what is hashed is what is packed, so
    an edit during the submit cannot give a tar other content than its name says."""
    tmp = trees / f"part-{os.getpid()}-{os.urandom(3).hex()}.tar.gz"
    h = hashlib.sha256()
    with tarfile.open(tmp, "w:gz", compresslevel=3) as t:
        for p in files:
            full = top / p
            data = full.read_bytes()
            mode = 0o755 if os.access(full, os.X_OK) else 0o644
            h.update(f"{p}\0{mode:o}\0{hashlib.sha256(data).hexdigest()}\n".encode())
            info = tarfile.TarInfo(p)
            info.size, info.mode, info.mtime = len(data), mode, 0
            t.addfile(info, io.BytesIO(data))
        for a, sha in sorted(outside.items()):
            data = pathlib.Path(a).read_bytes()
            info = tarfile.TarInfo(shipped_name(a, sha))
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            t.addfile(info, io.BytesIO(data))
    th = h.hexdigest()
    name = th[:24] + ("-" + hashlib.sha256("".join(sorted(outside.values())).encode()).hexdigest()[:8]
                      if outside else "")
    tar = trees / f"{name}.tar.gz"
    if tar.exists():
        tmp.unlink()
    else:
        tmp.replace(tar)
    return th, tar


# -- the limits ----------------------------------------------------------------------------------

def ssh(cmd: str, timeout: int = 60, inp: bytes | None = None) -> subprocess.CompletedProcess:
    """CMD on gpufarm; HostError when ssh itself fails (rc 255) or times out"""
    try:
        r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", FARM, cmd],
                           input=inp, capture_output=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError) as e:
        raise HostError(f"gpufarm: {e}") from e
    if r.returncode == 255:
        raise HostError(f"gpufarm: {r.stderr.decode(errors='replace')[-200:]}")
    return r


FARM_PROBE = r"""python3 - <<'EOF'
import os, time
uid = os.getuid()
def ticks():
    t = 0
    for p in os.listdir('/proc'):
        if not p.isdigit():
            continue
        try:
            if os.stat('/proc/' + p).st_uid != uid:
                continue
            f = open('/proc/%s/stat' % p).read().rsplit(')', 1)[1].split()
            t += int(f[11]) + int(f[12])
        except (OSError, IndexError, ValueError):
            pass
    return t
a = ticks(); time.sleep(1.0); b = ticks()
print((b - a) / os.sysconf('SC_CLK_TCK'), open('/proc/loadavg').read().split()[0])
EOF"""


def farm_usage() -> tuple[float, float] | None:
    """(the CPUs all our processes on gpufarm use now, queued or not; its load1), or None"""
    try:
        ours, load = ssh(FARM_PROBE, timeout=40).stdout.decode().split()
        return float(ours), float(load)
    except (HostError, ValueError):
        return None


def mac_load() -> float:
    return os.getloadavg()[0]


def farm_cpu_max(now: float) -> float:
    """our CPU cap on gpufarm at NOW (epoch seconds, the Mac's local time)"""
    if FARM_CPU_FIXED is not None:
        return float(FARM_CPU_FIXED)
    t = time.localtime(now)
    return FARM_CPU_OFFICE if t.tm_wday < 5 and 8 <= t.tm_hour < 17 else FARM_CPU_OFF_HOURS


def can_start(job: dict, host: str, running: list[dict], usage, now: float) -> bool:
    """the User's limits for starting JOB on HOST, given the queue's RUNNING jobs and the host's
    USAGE (farm: (our CPUs, load1) or None; mac: load1). Pure, for the tests."""
    if host == "mac":
        mine = [j for j in running if j["host"] == "mac"]
        ramping = sum(j["cpus"] for j in mine if now - j.get("started", 0) < RAMP_S)
        return len(mine) < MAC_JOBS_MAX and ramping + job["cpus"] <= (MAC_CORES - usage) / 2
    if usage is None:
        return False
    ours, load = usage
    ramping = sum(j["cpus"] for j in running if j["host"] == "farm" and now - j.get("started", 0) < RAMP_S)
    return ours + ramping + job["cpus"] <= farm_cpu_max(now) and load + job["cpus"] <= FARM_LOAD_MAX


def place(job: dict, running: list[dict], mac_usage: float, farm, now: float) -> str | None:
    """the host to start JOB on now (the Mac first where it may run there), or None to wait"""
    for host in job["hosts"]:
        if can_start(job, host, running, mac_usage if host == "mac" else farm, now):
            return host
    return None


# -- a job's life --------------------------------------------------------------------------------

def _shell(job: dict, host: str) -> str:
    out = []
    for a in job["cmd"]:
        for path, sha in job["files"].items():
            a = a.replace(path, shipped_name(path, sha))
        for k, v in PLACEHOLDERS[host].items():
            a = a.replace(k, v)
        out.append(shlex.quote(a))
    return " ".join(out)


def _env(job: dict) -> str:
    return " ".join(shlex.quote(f"{k}={v}") for k, v in sorted(job["env"].items()))


def start(job: dict, work: pathlib.Path) -> dict:
    """start JOB detached on job['host']: it writes runq.log, and runq.rc when it ends. -> where"""
    attempt = job.get("attempt", 0)
    tail = "; echo $? > runq.rc.tmp; mv runq.rc.tmp runq.rc"
    if job["host"] == "mac":
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        with tarfile.open(job["tar"]) as t:
            t.extractall(work, filter="data")
        caps = " ".join(f"{v}={job['cpus']}" for v in MAC_THREAD_VARS)
        sh = f"( nice -n 19 env {caps} {_env(job)} {_shell(job, 'mac')} ) > runq.log 2>&1{tail}"
        p = subprocess.Popen(["/bin/sh", "-c", sh], cwd=work, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"where": str(work), "pgid": p.pid}
    root = f"{FARM_ROOT}/work/{job['id']}-{attempt}"
    r = ssh(f"rm -rf {root} && mkdir -p {root} && tar -xzf - -C {root}", timeout=900,
            inp=pathlib.Path(job["tar"]).read_bytes())
    if r.returncode:
        raise HostError(f"gpufarm: unpacking failed: {r.stderr.decode(errors='replace')[-200:]}")
    seed = (f"mkdir -p out/waverider && cp -n {FARM_ROOT}/seed/m2_init_* out/waverider/ 2>/dev/null; "
            if job["kind"] == "runner" else "")
    run = f"timeout {int(job['timeout'])} " + ("" if job["kind"] == "cmd" else f"{FARM_BENCH}/bench_ns112.sh . ")
    # 2026-11-14 (main): nice 19 on gpufarm too, as on the Mac (17-19 jobs at a time ran at nice 0 until now)
    sh = f"cd {root} && {seed}( nice -n 19 {run}env {_env(job)} {_shell(job, 'farm')} ) > runq.log 2>&1{tail}"
    r = ssh(f"nohup sh -c {shlex.quote(sh)} > /dev/null 2>&1 < /dev/null &", timeout=60)
    if r.returncode:
        raise HostError(f"gpufarm: start failed: {r.stderr.decode(errors='replace')[-200:]}")
    return {"where": root}


def poll(job: dict, now: float) -> int | str | None:
    """the job's rc when it has ended; 'gone' when its tree has vanished; else None. A Mac job past
    its timeout is stopped (its process group) and ends with 124, as `timeout` does on gpufarm."""
    if job["host"] == "mac":
        f = pathlib.Path(job["where"]) / "runq.rc"
        if f.exists():
            txt = f.read_text().strip()
            return int(txt) if txt.lstrip("-").isdigit() else 1
        if not pathlib.Path(job["where"]).exists():
            return "gone"
        if now - job["started"] > job["timeout"]:
            try:
                os.killpg(job["pgid"], signal.SIGTERM)
            except (ProcessLookupError, PermissionError, KeyError):
                pass
            return 124
        return None
    r = ssh(f"cat {job['where']}/runq.rc 2>/dev/null || test -d {job['where']} || echo gone", timeout=40)
    txt = r.stdout.decode().strip()
    if txt == "gone":
        return "gone"
    return int(txt) if txt.lstrip("-").isdigit() else None


def collect(job: dict, into: pathlib.Path) -> None:
    """the job's log (into/log) and the files its --collect patterns match (into/files/...); raises
    HostError if gpufarm did not hand them over (so nothing half is kept)"""
    (into / "files").mkdir(parents=True, exist_ok=True)
    if job["host"] == "mac":
        work = pathlib.Path(job["where"])
        shutil.copy(work / "runq.log", into / "log")
        for g in job["collect"]:
            for f in glob.glob(str(work / g), recursive=True):
                if not os.path.isfile(f):
                    continue
                dst = into / "files" / os.path.relpath(f, work)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dst)
        return
    pats = " ".join(check_glob(g) for g in job["collect"])
    pack = f"tar -czf - runq.log $(for f in {pats}; do [ -f \"$f\" ] && printf '%s\\n' \"$f\"; done)"
    r = ssh(f"cd {job['where']} && bash -O globstar -O nullglob -c {shlex.quote(pack)}", timeout=900)
    if r.returncode or not r.stdout:
        raise HostError(f"gpufarm: collecting failed: {r.stderr.decode(errors='replace')[-200:]}")
    with tarfile.open(fileobj=io.BytesIO(r.stdout), mode="r:gz") as t:
        t.extractall(into / "files", filter="data")
    (into / "files" / "runq.log").replace(into / "log")


def remove(job: dict) -> None:
    """the job's tree, once its result is kept"""
    if job["host"] == "mac":
        shutil.rmtree(job["where"], ignore_errors=True)
    else:
        ssh(f"rm -rf {job['where']}", timeout=300)

