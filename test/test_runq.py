"""scripts/runq.py, the shared run queue (2026-11-12): its limits, its key, and a whole job on the
Mac in a throwaway repository: two submits of the same job run it once, a third reuses the result."""

from __future__ import annotations

import importlib
import os
import pathlib
import subprocess
import sys
import time

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


HOSTS_TOML = """
[farm]
host = "testfarm"
bench = "/srv/bench"
load_max = 60
cpus = 50
[farm.window]
days = [0, 1, 2, 3, 4]
start = 8
end = 17
cpus = 32
"""


@pytest.fixture
def runq(tmp_path, monkeypatch):
    hosts = tmp_path / "hosts.toml"                         # never this machine's own settings
    hosts.write_text(HOSTS_TOML)
    monkeypatch.setenv("DN2_HOSTS_FILE", str(hosts))
    for v in ("RUNQ_FARM_HOST", "RUNQ_FARM_BENCH", "RUNQ_FARM_CPUS", "RUNQ_FARM_LOAD"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("RUNQ_DIR", str(tmp_path / "q"))
    monkeypatch.setenv("RUNQ_NO_DISPATCHER", "1")
    monkeypatch.setenv("RUNQ_MAC_CORES", "100000")         # the test must not wait on the Mac's load
    sys.path.insert(0, str(SCRIPTS))
    import hostcfg
    importlib.reload(hostcfg)
    import runq_hosts
    importlib.reload(runq_hosts)
    import runq as R
    R = importlib.reload(R)
    yield R
    sys.path.remove(str(SCRIPTS))


def _job(cpus=1, host="farm", started=0.0):
    return {"cpus": cpus, "host": host, "started": started, "hosts": [host]}


WEEKDAY_NOON = time.mktime((2026, 11, 12, 12, 0, 0, 0, 0, -1))      # a Thursday
SATURDAY = time.mktime((2026, 11, 14, 12, 0, 0, 0, 0, -1))
WEEKDAY_EVENING = time.mktime((2026, 11, 12, 17, 0, 0, 0, 0, -1))


def test_farm_cap_follows_the_settings_window(runq):
    assert runq.H.FARM == "testfarm" and runq.H.FARM_ROOT == "/srv/bench/runq"
    assert runq.H.farm_cpu_max(WEEKDAY_NOON) == 32
    assert runq.H.farm_cpu_max(SATURDAY) == 50
    assert runq.H.farm_cpu_max(WEEKDAY_EVENING) == 50
    assert runq.H.can_start(_job(2), "farm", [], (47.0, 10.0), SATURDAY)
    assert not runq.H.can_start(_job(2), "farm", [], (49.0, 10.0), SATURDAY)        # 51 > 50


def test_farm_counts_cpus_ours_and_ramping(runq):
    now = WEEKDAY_NOON
    assert runq.H.can_start(_job(1), "farm", [], (31.0, 10.0), now)
    assert not runq.H.can_start(_job(2), "farm", [], (31.0, 10.0), now)            # 33 > 32
    # a job started 10 s ago may not show yet: it counts with its CPUs
    ramping = [_job(4, started=now - 10)]
    assert not runq.H.can_start(_job(1), "farm", ramping, (28.0, 10.0), now)
    assert runq.H.can_start(_job(1), "farm", [_job(4, started=now - 600)], (28.0, 10.0), now)
    assert not runq.H.can_start(_job(1), "farm", [], (0.0, 60.0), now)              # the farm's own load
    assert not runq.H.can_start(_job(1), "farm", [], None, now)                     # unreachable: wait


def test_mac_counts_jobs_and_load(runq, monkeypatch):
    # half of the free cores (cores - load1), a job's CPUs within it
    monkeypatch.setattr(runq.H, "MAC_CORES", 16)
    two = [_job(host="mac"), _job(host="mac")]
    assert runq.H.can_start(_job(host="mac"), "mac", two[:1], 3.0, 1000)
    assert not runq.H.can_start(_job(host="mac"), "mac", two, 3.0, 1000)
    assert not runq.H.can_start(_job(host="mac"), "mac", [], 15.0, 1000)     # 1 free core: half is 0.5 < 1
    assert runq.H.can_start(_job(host="mac"), "mac", [], 14.0, 1000)         # 2 free: half is 1
    assert not runq.H.can_start(_job(host="mac"), "mac", [_job(host="mac", started=990)], 13.0, 1000)   # ramping
    # a job that may run on either goes to the farm when the Mac is loaded
    j = {"cpus": 1, "hosts": ["mac", "farm"]}
    assert runq.H.place(j, [], 20.0, (3.0, 10.0), 0) == "farm"
    assert runq.H.place(j, [], 2.0, (3.0, 10.0), 0) == "mac"
    assert runq.H.place({"cpus": 1, "hosts": ["mac"]}, [], 20.0, (3.0, 10.0), 0) is None


def test_mac_jobs_run_at_nice_19_with_capped_threads(runq):
    import pathlib as _p
    src = (_p.Path(__file__).resolve().parents[1] / "scripts" / "runq_hosts.py").read_text()
    assert "nice -n 19 env" in src and "OMP_NUM_THREADS" in src and "VECLIB_MAXIMUM_THREADS" in src


def test_farm_jobs_run_at_nice_19(runq, tmp_path, monkeypatch):
    sent = []

    def fake_ssh(cmd, timeout=60, inp=None):
        sent.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")
    monkeypatch.setattr(runq.H, "ssh", fake_ssh)
    tar = tmp_path / "job.tgz"
    tar.write_bytes(b"")
    for kind in ("runner", "cmd"):
        sent.clear()
        job = {"id": f"t-{kind}", "host": "farm", "tar": str(tar), "kind": kind, "timeout": 60,
               "cmd": ["python", "x.py"], "files": {}, "env": {"A": "1"}}
        runq.H.start(job, tmp_path / "w")
        started = sent[-1]
        assert "( nice -n 19 timeout 60 " in started, started


def test_status_runs(runq, tmp_path, monkeypatch):
    monkeypatch.setattr(runq.H, "farm_usage", lambda: None)
    d = tmp_path / "q"
    d.mkdir(parents=True, exist_ok=True)
    out = runq.status(d)
    assert "Mac load" in out and "farm: unreachable" in out


def test_the_key_follows_tree_command_and_outside_files(runq, tmp_path):
    k = runq.job_key("t1", "runner", ["python", "x.py"], {}, [], {})
    assert k == runq.job_key("t1", "runner", ["python", "x.py"], {}, [], {})
    assert k != runq.job_key("t2", "runner", ["python", "x.py"], {}, [], {})
    assert k != runq.job_key("t1", "runner", ["python", "y.py"], {}, [], {})
    assert k != runq.job_key("t1", "runner", ["python", "x.py"], {"A": "1"}, [], {})
    # an outside file counts by its content, not its path
    a = runq.job_key("t1", "gate", ["g", "/x/B.syx"], {}, [], {"/x/B.syx": "aa"})
    assert a == runq.job_key("t1", "gate", ["g", "/x/B.syx"], {}, [], {"/x/B.syx": "aa"})
    assert a != runq.job_key("t1", "gate", ["g", "/x/B.syx"], {}, [], {"/x/B.syx": "bb"})


def _repo(path: pathlib.Path) -> pathlib.Path:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "a.txt").write_text("one\n")
    (path / ".gitignore").write_text("ignored/\n")
    (path / "ignored").mkdir()
    (path / "ignored" / "big").write_text("not shipped\n")
    return path


def _run_until_done(runq, jid, limit=30.0):
    d = runq.qdir()
    t0 = time.time()
    while time.time() - t0 < limit:
        runq.dispatch_once(d)
        job = runq.load_job(d, jid)
        if job["state"] == "done":
            return job
        time.sleep(0.2)
    raise AssertionError(f"{jid} still {job['state']}")


def test_a_job_runs_once_and_its_result_is_reused(runq, tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    counter = tmp_path / "count"
    cmd = ["--", "sh", "-c", f"echo ran >> {counter}; cat a.txt > out.txt; ls ignored 2>&1 | head -1"]
    sub = ["submit", "--kind", "cmd", "--host", "mac", "--collect", "out.txt"]
    first = runq.main(sub + cmd)
    assert first == 0
    d = runq.qdir()
    jobs = sorted(runq.all_jobs(d), key=lambda j: j["submitted"])
    assert [j["state"] for j in jobs] == ["queued"]
    runq.main(sub + cmd)                                   # the same, while the first waits: joins it
    jobs = sorted(runq.all_jobs(d), key=lambda j: j["submitted"])
    assert jobs[1]["state"] == "joined" and jobs[1]["joined"] == jobs[0]["id"]
    done = _run_until_done(runq, jobs[0]["id"])
    assert done["rc"] == 0 and counter.read_text() == "ran\n"
    assert runq.load_job(d, jobs[1]["id"])["state"] == "done"
    res = pathlib.Path(done["result"])
    assert (res / "files" / "out.txt").read_text() == "one\n"
    assert "No such file" in (res / "log").read_text()     # ignored files are not shipped
    runq.main(sub + cmd)                                   # later: the stored result, nothing runs
    third = max(runq.all_jobs(d), key=lambda j: j["submitted"])
    assert third["state"] == "done" and third["reused"] == done["id"]
    assert counter.read_text() == "ran\n"
    # fetch copies the collected files into a tree
    dst = tmp_path / "into"
    assert runq.fetch(third["id"], dst) == [str(dst / "out.txt")]
    # a changed tree is a new job
    (repo / "a.txt").write_text("two\n")
    runq.main(sub + cmd)
    fourth = max(runq.all_jobs(d), key=lambda j: j["submitted"])
    assert fourth["state"] == "queued" and fourth["key"] != done["key"]
    _run_until_done(runq, fourth["id"])
    assert counter.read_text() == "ran\nran\n"
    assert not any((d / "work").iterdir())                 # the job trees are gone


def test_collect_patterns_cannot_run_anything(runq):
    for bad in ("out/*; rm -rf ~", "$(id)", "../x", "/etc/passwd", "a b"):
        with pytest.raises(ValueError):
            runq.H.check_glob(bad)
    assert runq.H.check_glob("out/waverider/m5_report_*.json") == "out/waverider/m5_report_*.json"


def test_a_failure_runs_again_and_a_lost_lead_ends_its_joiners(runq, tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    counter = tmp_path / "count"
    cmd = ["submit", "--host", "mac", "--", "sh", "-c", f"echo ran >> {counter}; exit 3"]
    runq.main(cmd)
    d = runq.qdir()
    first = runq.all_jobs(d)[0]
    assert _run_until_done(runq, first["id"])["rc"] == 3
    runq.main(cmd)                                         # a failure is not reused: it runs again
    second = max(runq.all_jobs(d), key=lambda j: j["submitted"])
    assert second["state"] == "queued"
    runq.main(cmd)                                         # joins the second
    third = max(runq.all_jobs(d), key=lambda j: j["submitted"])
    assert third["state"] == "joined"
    (d / "jobs" / f"{second['id']}.json").unlink()         # its lead's record is gone
    assert runq.wait(third["id"], poll_s=0)["rc"] == 125


def test_a_mac_job_past_its_timeout_is_stopped(runq, tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    runq.main(["submit", "--host", "mac", "--timeout", "1", "--", "sleep", "60"])
    d = runq.qdir()
    job = runq.all_jobs(d)[0]
    t0 = time.time()
    done = _run_until_done(runq, job["id"], limit=20)
    assert done["rc"] == 124 and time.time() - t0 < 20
