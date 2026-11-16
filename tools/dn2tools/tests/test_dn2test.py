"""The on-device test harness against its simulator (dn2tools, docs/device-tests.md): every scenario passes on a
healthy simulated unit and fails on the fault meant for it; the frame codec round-trips; the harness refuses
anything that is not a note or the read-only telemetry request."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from dn2tools import frame  # noqa: E402
from dn2tools.ctx import Params  # noqa: E402
from dn2tools.project import Project  # noqa: E402
from dn2tools.runner import run  # noqa: E402
from dn2tools.sim import DirectUnit  # noqa: E402
from dn2tools.unit import ALLOWED_CC, Refused, request  # noqa: E402

PROJECT = Project.load(SRC / "dn2tools" / "data" / "project.json")
PARAMS = Params(hold_s=2.0)


def _run(faults=(), only=None):
    unit = DirectUnit(PROJECT, faults)
    return {r.name: r for r in run(unit, PROJECT, PARAMS, only, log=lambda *_: None)}


def test_healthy_unit_passes_every_scenario():
    results = _run()
    bad = {n: [c for c in r.checks if not c.ok] for n, r in results.items() if r.status != "PASS"}
    assert not bad, bad
    assert set(results) >= {"link", "idle", "wiring", "a2_svf", "a2_ms20", "hold", "glide", "inserts", "stress"}


@pytest.mark.parametrize("fault,scenarios", [
    ("a2_dies", ("a2_svf", "a2_diod")),
    ("hold_dead", ("hold",)),
    ("labels_idle", ("idle",)),
    ("ins_skips", ("inserts",)),
    ("voices_stale", ("wiring",)),
    ("overload", ("stress", "a2_ladr")),
])
def test_each_fault_is_caught(fault, scenarios):
    results = _run((fault,))
    for name in scenarios:
        assert results[name].status == "FAIL", (fault, name, results[name].checks[:3])


def test_frame_roundtrip():
    unit = DirectUnit(PROJECT)
    unit.note_on(0, 60)
    unit.wait(1.0)
    t = unit.tlm()
    assert frame.decode(frame.encode(t)) == t
    assert t.build == 0x00470001 and t.voices == 1 and t.frames == 1500


def test_decode_refuses_a_wrong_frame():
    with pytest.raises(ValueError):
        frame.decode(b"\0" * 128)
    with pytest.raises(ValueError):
        frame.decode(b"\0" * 8)


def test_only_notes_and_the_read_only_requests_are_sent():
    unit = DirectUnit(PROJECT)
    for cmd in (2, 6, 7, 8, 9, 25, 28, 30, 31):           # WRITE LOAD FORGET BEGIN END SCAN ERASE ...
        with pytest.raises(Refused):
            request(1, cmd)
    for cc in (1, 7, 74, 99, 100, 6, 38):                 # sound, NRPN and RPN controllers
        with pytest.raises(Refused):
            unit.cc(0, cc, 64)
    for cc in ALLOWED_CC:
        unit.cc(0, cc, 0)
    with pytest.raises(Refused):
        unit.note_on(16, 60)
    with pytest.raises(Refused):
        unit.note_on(0, 128)


def test_project_rejects_nonsense():
    with pytest.raises(ValueError):
        Project.from_dict({"tracks": {"17": {"machine": "X"}}})
    with pytest.raises(ValueError):
        Project.from_dict({"tracks": {"1": {"machine": "ANALOG2", "filter": "NOPE"}}})


def test_the_driver_over_virtual_midi_ports():
    """the real mido path (ports, SysEx framing, polling) against the simulator on CoreMIDI / ALSA virtual ports"""
    mido = pytest.importorskip("mido")
    try:
        probe = mido.open_output("dn2test-probe", virtual=True)
        probe.close()
    except Exception as e:                                # noqa: BLE001 - no virtual ports here (CI, Windows)
        pytest.skip(f"no virtual MIDI ports: {e}")
    server = subprocess.Popen([sys.executable, "-m", "dn2tools.cli.dn2test", "--serve-fake", "--port", "DN2 Fake T"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              env={**__import__("os").environ, "PYTHONPATH": str(SRC)})
    try:
        assert "fake unit on virtual" in server.stdout.readline()
        from dn2tools.unit import MidoUnit
        unit = MidoUnit("DN2 Fake T")
        try:
            assert unit.hello() == 7
            unit.note_on(0, 60)
            unit.wait(0.3)
            assert unit.tlm().voices == 1
        finally:
            unit.close()
    finally:
        server.terminate()
        server.wait(5)


def test_bench_dry_run_and_compare(tmp_path):
    from dn2tools import bench
    unit = DirectUnit(PROJECT)
    rows = bench.run_bench(unit, PROJECT, PARAMS, "t", log=lambda *_: None)
    idle = next(r for r in rows if r.item == "idle")
    assert 420_000 < idle.d_mean < 430_000                      # the simulator's 64 % idle floor
    one, sixteen = (next(r for r in rows if r.item == f"T1 ANALOG2 SVF x{n}") for n in (1, 16))
    assert one.d_mean > idle.d_mean and sixteen.d_mean > one.d_mean
    csv_a, md_a = bench.write(rows, tmp_path, 0x00470001, "a", {"PLAITS:WS": (360_000.0, 537_000.0)})
    csv_b, _ = bench.write(rows, tmp_path, 0x00470002, "b", {})
    assert "0x00470001" in md_a.read_text().splitlines()[0]
    assert "+0.0 %" in bench.compare(str(csv_a), str(csv_b))
    ratios = [ln for ln in csv_a.read_text().splitlines() if "PLAITS:WS" in ln]
    assert ratios and ratios[0].split(",")[-1]                  # a runner row gives a unit / runner ratio


def test_runner_table_rows_are_read():
    from dn2tools import bench
    table = pathlib.Path.home() / "GitHub/dn2mk2-scratch/combined/budget-table.md"
    if not table.exists():
        pytest.skip("no budget table")
    est = bench.load_runner(table)
    assert est["TB303"][0] == 387_093.0 and est["TB303"][1] == 897_334.0


def test_peak_run_and_on_off_compare(tmp_path):
    from dn2tools import peak
    unit = DirectUnit(PROJECT)
    ps = peak.run_peaks(unit, PROJECT, PARAMS, seconds=8.0, log=lambda *_: None)
    names = [p.scenario for p in ps]
    assert "busy 16 voices" in names and "wake all tracks" in names and any(n.startswith("random notes") for n in names)
    assert all(p.max >= p.p99 >= 0 and p.max >= p.mean for p in ps)
    on, _ = peak.write(ps, tmp_path, 0x00470001, "on")
    worse = [peak.Peak(p.scenario, p.n, p.mean, p.p99, p.max + 20_000, p.first_max, p.steady_mean, p.skipped_max, p.ins_skips, p.a2_dry) for p in ps]
    bad, _ = peak.write(worse, tmp_path, 0x00470001, "worse")
    assert "ON WORSE" not in peak.compare(str(on), str(on))
    assert "ON WORSE" in peak.compare(str(bad), str(on))


# -- audio -------------------------------------------------------------------------------------

def _audio(faults=(), only=None, tmp=None, cc_map=None):
    pytest.importorskip("numpy")
    from dn2tools import audio_scenarios as AS
    from dn2tools.audio_sim import SimRecorder
    unit = DirectUnit(PROJECT, faults)
    res = AS.run_audio(unit, PROJECT, PARAMS, SimRecorder(unit), AS.Thresholds(), tmp, cc_map, only, log=lambda *_: None)
    return {r.name: r for r in res}


def test_audio_analysis_on_synthetic_signals():
    np = pytest.importorskip("numpy")
    from dn2tools import audio_analysis as A
    fs = A.FS
    t = np.arange(fs * 2) / fs
    x = 0.3 * np.sin(2 * np.pi * 440 * t)
    assert A.clicks(x)["n"] == 0 and not A.dropouts(x)
    y = x.copy()
    y[::32 * 50] += 0.6
    c = A.clicks(y)
    assert c["n"] > 30 and c["periodic"]
    z = x.copy()
    z[30000:30100] = 0
    assert A.dropouts(z) == [(30000, 100)]
    g = np.where(t < 0.5, 261.6, np.where(t < 0.9, 261.6 * (392 / 261.6) ** ((t - 0.5) / 0.4), 392.0))
    tt, ff = A.pitch_track(np.sin(2 * np.pi * np.cumsum(g) / fs))
    assert 0.25 < A.transition_time(tt, ff, 261.6, 392.0) < 0.45
    d = np.sin(2 * np.pi * 300 * t) * np.exp(-t / 0.3)
    assert abs(A.decay_time(d, 0.1) - 1.38) < 0.05
    b = np.zeros(fs * 2)
    b[:2400] = 0.5 * np.sin(2 * np.pi * 500 * t[:2400])
    b[12000:14400] = 0.25 * np.sin(2 * np.pi * 500 * t[:2400])
    assert A.echo_delays(b)[0] == pytest.approx(250.0, abs=10)
    n = np.random.RandomState(1).randn(fs * 2)
    assert A.spectral_diff_db(n, np.convolve(n, np.ones(16) / 16, "same")) > 6 > A.spectral_diff_db(n, 0.3 * n)


def test_audio_scenarios_pass_on_a_healthy_simulator(tmp_path):
    results = _audio(tmp=tmp_path)
    bad = {n: [c for c in r.checks if not c.ok][:2] for n, r in results.items() if r.status in ("FAIL", "ERROR")}
    assert not bad, bad
    assert results["a_page2"].status == "SKIP"                     # no CC map: nothing parameter-like is sent
    assert list(tmp_path.glob("a_level-*.wav"))


@pytest.mark.parametrize("fault,scenario", [
    ("audio_clicks", "a_clicks"), ("audio_silent", "a_level"), ("filter_dead", "a_filters"),
    ("glide_dead", "a_glide"), ("delay_dead", "a_inserts"), ("hold_dead", "a_hold")])
def test_each_audio_fault_is_caught(fault, scenario, tmp_path):
    assert _audio((fault,), [scenario], tmp_path)[scenario].status == "FAIL"


def test_parameter_cc_needs_the_users_map():
    unit = DirectUnit(PROJECT)
    with pytest.raises(Refused):
        unit.param(0, 74, 64)
    unit.param_cc = frozenset({74})
    unit.param(0, 74, 64)
    with pytest.raises(Refused):
        unit.param(0, 75, 64)


def test_idle_slots_cost_but_do_not_sound():
    """every slot's voice code runs every block (the unit, 2026-11-11): at idle all 16 slots have a cost and none counts
    as sounding; a held note's slot does (word 23 counts the slots over SOUNDING_CYCLES, not the slots with a cost)"""
    unit = DirectUnit(PROJECT, ())
    unit.wait(0.2)
    idle = unit.tlm()
    assert all(c >= frame.IDLE_SLOT_CYCLES - 16 for c in idle.slot_cost) and idle.voices == 0
    unit.note_on(0, 60)
    unit.wait(0.2)
    held = unit.tlm()
    assert held.voices == 1 and max(held.slot_cost) > frame.SOUNDING_CYCLES
    unit.note_off(0, 60)
    unit.wait(1.0)
    assert unit.tlm().voices == 0
