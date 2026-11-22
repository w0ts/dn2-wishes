# The run queue: one place for every session's heavy runs (2026-11-12)

About fifteen sessions used to start their own builds, regenerations, SHARC runner and emulator
runs, often the same ones, on the Mac and on the farm; the Mac reached a load of 70. The User:
"mutualise runs". `scripts/runq.py` is the one queue they all use instead.

## Use

    python3 scripts/runq.py submit --kind runner --env DNFW_COST_ONLY=smp \
        --collect 'out/waverider/m5_report_*.json' --wait -- \
        python scripts/sharc_waverider_m5.py --image {STOCK112} --digikit {DIGIKIT} --steps cost

prints the job's id, waits, and prints its result directory (its `log`, `meta.json` and the
collected files under `files/`). Without `--wait`: `runq.py wait ID` (exits with the job's rc),
`runq.py log ID` (also while it runs), `runq.py fetch ID [DIR]` (the collected files into DIR,
default the current tree: regenerated asm, reports), `runq.py result ID`, `runq.py status`,
`runq.py gc`.

- Run it from the tree to test: the job runs on that tree as it is at submit (tracked files, and
  untracked ones git does not ignore), so editing afterwards changes nothing.
- `{STOCK111}`, `{STOCK112}` and `{DIGIKIT}` are the host's own paths (the farm's are in this
  machine's settings, below). An
  absolute path outside the tree (a build's `.syx`), whole or after `=`, is shipped with the job and
  counts in its key by content.
- `--collect` takes relative patterns of letters, digits, `_ . - / * ? [ ]` only (`**` for any depth):
  the farm expands them in a shell, so nothing else is accepted.
- The code is `scripts/runq.py` (the queue, the commands) and `scripts/runq_hosts.py` (the limits,
  the snapshot, a job's life on each host); `test/test_runq.py` runs whole jobs on the Mac.
- **This machine's settings** (the farm's ssh host, its bench directory, the `{NAME}` paths and the CPU
  caps) are kept out of the repository, in `~/.config/dn2-wishes/hosts.toml` (or the file
  `DN2_HOSTS_FILE` names), read by `scripts/hostcfg.py`; `docs/hosts.example.toml` shows every key.
  Without the file, neutral defaults apply (ssh host `farm`, a small CPU cap).
- `--env K=V` for environment the command needs; the Mac's jobs get no `env.sh` of their own.
- `--prio 10` for the integrator's gate (higher runs first; otherwise first come, first served).
- `--fresh` runs it again although a result is stored.

| kind | where | CPUs | timeout |
|---|---|---|---|
| `runner` (sharc_waverider_m5.py) | farm (digikit) | 1 | 2 h |
| `regen` (gen_*_asm, gen_waverider_sharc --assemble) | farm (selas) | 1 | 30 min |
| `gate` (ship_gate.py --only STEP) | farm | 1 | 2 h |
| `emu` (the ColdFire emulator) | Mac | 2 | 2 h |
| `cmd` (anything else) | Mac or farm (`--host`) | 1 (`--cpus`) | 2 h |

The CPUs are what one such job takes, measured on the farm (one python process at 100 % of a core);
a job that fans out says so with `--cpus N`. Emulator jobs stay on the Mac: the farm's emulator
setup has not been shown to match the Mac's (main, 2026-11-12: they may go there once it is).

## What it does

- **Once per input.** A job's key is the sha256 of its tree's content (each file's path, mode and
  sha256), its kind, its command (a shipped file by its content), its environment and what it
  collects. A submit whose key is queued or running joins that job; one whose key has a stored
  **passing** result (rc 0) gets it at once (`reused` in its record). A failure is kept to read but
  runs again on the next submit (it may have been the host's, not the code's). The tree is hashed
  from the very bytes that are packed, so the snapshot is exactly what its key says.
- **Robust.** A job's log, rc and collected files are kept whole or not at all: if the farm does not
  hand them over, the dispatcher tries again next pass and keeps the remote tree until it has them.
  A host's trouble (ssh down, a failed start) never stops the queue: the job goes back in the queue
  (a start afresh) or, after 20 failures, ends with rc 125 and a note. A Mac job past its timeout
  is stopped (its process group) and ends with 124, as `timeout` does on the farm. A joined job ends
  with its lead, or with 125 if the lead's record is gone. The queue's lock is held only for
  bookkeeping, never across ssh.
- **Within the limits**, checked before every start by one dispatcher (the first submit
  starts it; it leaves after ten idle minutes):
  - the farm: at most the settings' **`cpus`** of ours (or the `[farm.window]` cap on its weekdays and
    hours, the Mac's local time): every process of our ssh user there is counted (queued or not:
    other runs too), measured over a second from /proc, plus the CPUs of any queue job started in
    the last 90 s (not visible yet); and the farm's load1 plus the job stays under **`load_max`**,
    the room left for its other users.
  - Mac (it is in use, always): at most **two** queue jobs, and a job starts only when its CPUs, with those of our jobs started in the
    last 90 s, fit in **half of the free cores** (cores - `uptime`'s load1); it runs at **nice 19** with
    OMP / MKL / OpenBLAS / vecLib / Numba threads capped to its CPUs. A job that may run on either host goes to
    the farm when the Mac is loaded, else it waits.
  - (`RUNQ_FARM_HOST`, `RUNQ_FARM_BENCH`, `RUNQ_FARM_CPUS`, `RUNQ_FARM_LOAD`, `RUNQ_MAC_JOBS`, `RUNQ_MAC_CORES` change them.)
- **One place.** Everything is under the main checkout's `scratch/runq/` (git-ignored): `jobs/`
  (a record a job), `trees/` (the snapshots, one per tree content), `results/KEY/`, `work/` (the
  Mac's running jobs), `dispatcher.log`. On the farm a job runs in `BENCH/runq/work/ID`
  under `bench_ns112.sh`; its tree is removed when it ends. The runner's engine snapshot
  (`out/waverider/m2_init_*`, 18 min to build) is seeded from `BENCH/runq/seed/` (BENCH: the settings' `bench`).
- **Cleanup.** `runq.py gc [--days 7]` removes older results and records, snapshots no live job
  needs, and work trees here and on the farm that belong to no live job.

## Next (phase 2)

Reuse across trees: record a passing job's traced inputs, as `scripts/gate_cache.py` does for the
gate's steps (`scripts/gate_trace/sitecustomize.py`, the job's tree as `@WORK`), so a different
tree whose traced inputs are unchanged reuses the pass too.
