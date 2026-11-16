"""Automated tests on the Digitone II: notes in, the read-only telemetry frame back, assertions (docs/device-tests.md).

    dn2test                                     the unit, all scenarios
    dn2test --only idle,hold,a2_svf             some of them
    dn2test --project my_project.json --out reports/
    dn2test --dry-run [--fault a2_dies]         against the simulator (no unit; seconds)
    dn2test --serve-fake [--fault hold_dead]    the simulator on virtual MIDI ports "DN2 Fake"
    dn2test --port "DN2 Fake"                   the driver against those ports
    dn2test --list
    dn2test --audio [--only a_level,a_hold] [--cc-map map.json]   audio analysis over USB audio (plays sound at low velocity)
    dn2test --peak --label skipsON --out peak/  peaks and wake-ups; then --peak-compare ON.csv OFF.csv
    dn2test --peak --switch-ab HOLD             the same, run twice on one build: switch HOLD at 1 then at 0
    dn2test --bench --label night9 --out bench/ cycles per frame per machine / FX (CSV + md); then --compare A.csv B.csv
    dn2test info | switches | counters | trace | state | peek ADDR [LEN] | smoke | switch NAME VALUE
    dn2test profile --seconds 20 --label idle --out prof/ [--stock-dis F] [--ours J]   the CPU profiler (PROFILE)
    dn2test profile --compare prof/idle.json prof/busy.json                              per function, A vs B

Sends notes, all-notes-off, and the test channel's requests. Nothing that could change the unit's storage.
"""

from __future__ import annotations

import argparse
import pathlib
import time
from importlib import resources

from .. import audio_scenarios, bench, peak, report
from ..ctx import Params
from ..project import Project
from ..runner import run
from ..scenarios import registry
from ..sim import DirectUnit, serve
from ..unit import MidoUnit, NoTestChannel, StatusError
from . import inspect_cmds

DATA = resources.files("dn2tools") / "data"

FAULTS = ("a2_dies", "hold_dead", "labels_idle", "ins_skips", "voices_stale", "overload",
          "audio_clicks", "audio_silent", "filter_dead", "glide_dead", "delay_dead", "no_channel", "torn")


def run_audio_cli(a, project, unit, params, target) -> int:
    import json
    from ..audio_sim import SimRecorder
    try:
        build = f"{unit.tlm().build:#010x}"
    except (NoTestChannel, StatusError, ValueError, OSError) as e:
        build = None
        print(f"the telemetry did not answer ({e}): the firmware on the unit is not identified.")
        if not a.allow_unknown_build:
            print("Ask the User which build is on the unit, then run again with --allow-unknown-build.")
            unit.close()
            return 2
    print(f"build: {build or 'unknown (allowed)'}; audio scenarios play sound on the unit at low velocity; "
          f"each is announced before it starts", flush=True)
    thr = audio_scenarios.Thresholds.load(a.thresholds)
    cc_map = json.loads(pathlib.Path(a.cc_map).read_text()) if a.cc_map else {}
    if cc_map:
        unit.param_cc = frozenset(v for k, v in cc_map.items() if isinstance(v, int)) | frozenset(e["cc"] for e in cc_map.get("page2", []))
    rec = SimRecorder(unit) if a.dry_run else None
    out = pathlib.Path(a.out)
    try:
        if rec is None:
            from ..audio import DeviceRecorder
            rec = DeviceRecorder(unit, a.audio_device)
        results = audio_scenarios.run_audio(unit, project, params, rec, thr, out / "wav", cc_map, [s for s in a.only.split(",") if s])
    finally:
        unit.close()
    meta = {"project": project.name, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "target": target, "build": build or "unknown",
            "tracks": [t.label for t in project.tracks], "thresholds": thr.__dict__}
    j, m = report.write(out, results, meta)
    bad = [r for r in results if r.status in ("FAIL", "ERROR")]
    print(f"report: {m}\njson:   {j}\n{'ALL PASS' if not bad else str(len(bad)) + ' scenario(s) FAILED: ' + ', '.join(r.name for r in bad)}")
    return 1 if bad else 0


def run_peak_cli(a, project, unit, params) -> int:
    """--peak; with --switch-ab NAME the A/B on one build: NAME at 1 (label-on), then at 0 (label-off), then compared"""
    from ..channel import TestChannel
    try:
        build = unit.tlm().build
        if not a.switch_ab:
            peaks = peak.run_peaks(unit, project, params, a.peak_seconds, a.seed)
            c, m = peak.write(peaks, a.out, build, a.label)
            print(f"csv: {c}\nmd:  {m}")
            return 0
        ch = TestChannel(unit)
        before = {s.name: s.value for s in ch.switches()}
        csvs = []
        try:
            for v, tag in ((1, "on"), (0, "off")):
                print(f"switch {a.switch_ab} = {ch.set_switch(a.switch_ab, v)}", flush=True)
                peaks = peak.run_peaks(unit, project, params, a.peak_seconds, a.seed)
                c, m = peak.write(peaks, a.out, build, f"{a.label}-{a.switch_ab}-{tag}")
                csvs.append(c)
                print(f"csv: {c}\nmd:  {m}")
        finally:
            name = a.switch_ab.upper()
            if name in before:
                ch.set_switch(name, before[name])       # left as it was found
        print(peak.compare(*csvs))
        return 0
    finally:
        unit.close()


def main(argv=None) -> int:
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["profile"]:                      # remoteui-5: the CPU profiler (profile_cli.py)
        from . import profile_cli
        return profile_cli.main(args[1:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="Elektron Digitone II", help="MIDI port name (a part of it); default matches both USB modes: AUDIO+MIDI and OVERBRIDGE")
    ap.add_argument("--project", default=str(DATA / "project.json"), help="the project description (JSON, docs/device-tests.md)")
    ap.add_argument("--only", default="", help="comma separated scenario names")
    ap.add_argument("--out", default="device-test-report")
    ap.add_argument("--dry-run", "--sim", dest="dry_run", action="store_true", help="the simulator, in process, in virtual time")
    ap.add_argument("--quiet", action="store_true", help="no per-command cost lines")
    ap.add_argument("--serve-fake", action="store_true", help="serve the simulator on virtual MIDI ports")
    ap.add_argument("--fault", action="append", default=[], choices=FAULTS, help="simulator fault (repeatable)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--bench", action="store_true", help="performance: cycles per frame per machine / FX (CSV + markdown)")
    ap.add_argument("--label", default="build", help="--bench: a name for the build under test (in the file names)")
    ap.add_argument("--runner", default=None, help="--bench: the runner's budget table (markdown), for the calibration columns")
    ap.add_argument("--audio", action="store_true", help="audio analysis over USB audio: clicks, filters, HOLD, glide, inserts, levels")
    ap.add_argument("--thresholds", default=str(DATA / "audio_thresholds.json"), help="--audio: pass/fail thresholds (JSON)")
    ap.add_argument("--cc-map", default=None, help="--audio: a JSON of sound-parameter controllers the User allows (cutoff, resonance, page2)")
    ap.add_argument("--audio-device", default="Digitone", help="--audio: part of the USB audio input's name")
    ap.add_argument("--allow-unknown-build", action="store_true", help="--audio: go on when the telemetry does not answer (the firmware is not identified)")
    ap.add_argument("--peak", action="store_true", help="peak and wake-up cost: busy, wake all, wake FX/filter, random notes")
    ap.add_argument("--peak-seconds", type=float, default=60.0, help="--peak: the random-notes run's length")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--peak-compare", nargs=2, metavar=("ON.csv", "OFF.csv"), help="two peak CSVs: skips ON vs OFF, ON worse flagged")
    ap.add_argument("--compare", nargs=2, metavar=("A.csv", "B.csv"), help="two bench CSVs: the change per item")
    ap.add_argument("--hold", type=float, default=3.0, help="seconds a filter / insert / stress note is held")
    ap.add_argument("--ins-skip-cap", type=int, default=0, help="insert blocks passed through for time a scenario may add")
    ap.add_argument("--switch-ab", default=None, metavar="NAME", help="--peak: run twice on one build, the runtime switch NAME at 1 then at 0")
    ap.add_argument("command", nargs="*", help="info, switches, switch NAME VALUE, counters [reset], trace, state, peek ADDR [LEN], smoke")
    a = ap.parse_args(args)
    if a.command:
        return inspect_cmds.main(a)
    if a.peak_compare:
        print(peak.compare(*a.peak_compare))
        return 0
    if a.compare:
        print(bench.compare(*a.compare))
        return 0
    project = Project.load(a.project)
    if a.list:
        for name, title, fn in registry(project):
            print(f"{name:12s} {'' if fn else '(no track) '}{title}")
        return 0
    if a.serve_fake:
        serve(project, "DN2 Fake" if a.port == "Elektron Digitone II" else a.port, a.fault)
        return 0
    params = Params(hold_s=a.hold, ins_skip_cap=a.ins_skip_cap)
    unit = DirectUnit(project, a.fault) if a.dry_run else MidoUnit(a.port)
    target = f"simulator{' with ' + ','.join(a.fault) if a.fault else ''}" if a.dry_run else getattr(unit, "name", a.port)
    print(f"{project.name}: {len(project.tracks)} tracks on {target}")
    if a.audio:
        return run_audio_cli(a, project, unit, params, target)
    if a.peak:
        return run_peak_cli(a, project, unit, params)
    if a.bench:
        try:
            build = unit.tlm().build
            rows = bench.run_bench(unit, project, params, a.label)
        finally:
            unit.close()
        c, m = bench.write(rows, a.out, build, a.label, bench.load_runner(a.runner) if a.runner else {})
        print(f"csv: {c}\nmd:  {m}")
        return 0
    try:
        build = unit.tlm().build
        results = run(unit, project, params, [s for s in a.only.split(",") if s])
    finally:
        unit.close()
    meta = {"project": project.name, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "target": target,
            "build": f"{build:#010x}", "tracks": [t.label for t in project.tracks]}
    j, m = report.write(a.out, results, meta)
    bad = [r for r in results if r.status in ("FAIL", "ERROR")]
    print(f"report: {m}\njson:   {j}\n{'ALL PASS' if not bad else str(len(bad)) + ' scenario(s) FAILED: ' + ', '.join(r.name for r in bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
