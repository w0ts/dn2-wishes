"""The CPU profiler (PROFILE, 43): its wire format, the firmware's numbers read from csrc/devtest/prof.c (so
the host and the C cannot drift), the simulator's runs (timer, the audio fallback, a full ring), the
symbolizer on a synthetic objdump and a build's code JSON, the report and the A/B comparison, the CLI."""

from __future__ import annotations

import json
import pathlib
import re

from dn2tools import profile as PR
from dn2tools import protocol as P
from dn2tools import sim_channel as SC
from dn2tools import symbols as S
from dn2tools.channel import TestChannel
from dn2tools.project import Project
from dn2tools.sim import DirectUnit

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"     # pyproject: pytest's pythonpath is src
REPO = pathlib.Path(__file__).resolve().parents[3]

PROJECT = Project.load(SRC / "dn2tools" / "data" / "project.json")
PROF_C = (REPO / "csrc" / "devtest" / "prof.c").read_text()


def chan(faults=()):
    return TestChannel(DirectUnit(PROJECT, faults))


def quiet(*_a):
    pass


# --- the wire format and the firmware's numbers ---------------------------------------------------------

def test_profile_golden_bytes():
    assert P.PROFILE == 43 and P.PROFILE in P.ALLOWED and P.CAPS["PROFILE"] == 10
    assert P.args_profile_start(P.PROF_TIMER, 997).hex() == "0101000003e5"
    assert P.args_profile_read(0x01020304).hex() == "0401020304"
    assert P.encode(5, P.PROFILE, P.args_profile_status()).hex() == "f000203c7d01" + "00" + "00052b00" + "f7"


def test_the_firmware_agrees_with_the_host():
    """prof.c's record, ring, read size, sub-commands and refusal reasons are the host's"""
    rec = int(re.search(r"#define REC_WORDS (\d+)u", PROF_C).group(1))
    assert rec * 4 == P.PROF_RECORD
    assert int(re.search(r"#define CAP (\d+)u", PROF_C).group(1)) == SC.CAP
    assert "> 12u ? 12u" in PROF_C and P.PROF_PER_READ == 12
    assert "const u32 w[17]" in PROF_C                          # the status's 17 words
    whys = re.search(r"enum \{ (WHY_NONE[^}]*)\}", PROF_C).group(1).replace(" ", "").split(",")
    assert len(whys) == len(P.PROF_WHY)
    assert re.search(r"enum \{ S_OFF, S_RUN, S_FULL, S_STOPPED \}", PROF_C)
    assert [P.PROF_STATES[k] for k in range(4)] == ["off", "running", "full", "stopped"]
    assert "0 STATUS, 1 START u8 source u32 rate, 2 STOP" in PROF_C and "3 CLEAR, 4 READ u32 from" in PROF_C
    assert "#define BUS_HZ 132000000u" in PROF_C and SC.BUS_HZ == 132_000_000


def test_the_dispatch_and_the_audio_gate_are_wired():
    link = (REPO / "csrc" / "sampler" / "link.c").read_text()
    assert "cmd >= 33 && cmd <= 43 && cmd != 39" in link
    dt = (REPO / "csrc" / "devtest" / "devtest.c").read_text()
    assert "#define CAP_PROFILE  (1u << 10)" in dt and "cmd == 43" in dt
    hooks = (REPO / "csrc" / "sampler" / "hooks.S").read_text()
    gate = int(re.search(r"W_AUDIO_GATE == (\d+)", PROF_C).group(1))
    assert f"PROF_RAM + {4 * gate}" in hooks
    magic = int(re.search(r"#define AUDIO_GATE (0x[0-9A-Fa-f]+)u", PROF_C).group(1), 16)
    assert f"#{magic:#010x}" in hooks.lower()


def test_the_timer_is_one_stock_leaves_alone():
    """the addresses prof.c writes, as measured in the 1.12 image (docs/remote-ui.md)"""
    for reg in ("0xFC070000u", "0xFC070004u", "0xFC048060u", "0xFC04801Cu", "0xFC04801Du", "0x40000180u"):
        assert reg in PROF_C
    assert "#define LEVEL 6u" in PROF_C and "#define STOCK_DEFAULT 0x40001252u" in PROF_C


# --- the simulator --------------------------------------------------------------------------------------

def test_a_timer_run_and_its_report(tmp_path):
    ch = chan()
    r = PR.run(ch, 3.0, 997, "auto", "idle", log=quiet)
    assert r.source == "timer" and 2900 <= len(r.samples) <= 3000
    st = ch.profile_status()
    assert st.state == "stopped" and st.samples == len(r.samples)
    res = PR.analyse(r, S.Symbols.build({k: v[0] for k, v in S.STOCK_NAMES.items()}))
    assert 35 < res["idle_pct"] < 55 and abs(res["idle_pct"] + res["busy_pct"] - 100) < 1e-9
    assert abs(res["clocks"]["elapsed_s"] - 3.0) < 0.01 and abs(res["clocks"]["dtim0_hz"] - 132e6) < 1e5
    assert res["functions_pct"]["idle_spin"] == res["idle_pct"]
    assert "5" in res["ipl_pct"] and res["late_us"] is not None and res["clocks"]["overhead_pct"] > 0
    j, m = PR.write(tmp_path, r, res, S.Symbols.build({}))
    assert "**idle**" in m.read_text() and json.loads(j.read_text())["samples"] == len(r.samples)
    assert (tmp_path / "idle.samples.csv").read_text().count("\n") == len(r.samples) + 1
    again = PR.Run.from_json(json.loads((tmp_path / "idle.raw.json").read_text()))
    assert again.samples == r.samples


def test_the_audio_source_is_the_fallback():
    ch = chan(["no_dtim0"])
    r = PR.run(ch, 2.0, 997, "auto", "fallback", log=quiet)
    assert r.source == "audio" and "timer source refused" in r.notes[0] and "bus clock" in r.notes[0]
    assert all(s[2] >> 8 & 7 < 5 for s in r.samples)            # the audio interrupt cannot see itself


def test_the_ring_stops_when_full():
    ch = chan()
    r = PR.run(ch, 8.0, 10000, "timer", "full", log=quiet)
    assert len(r.samples) == SC.CAP and any("filled" in n for n in r.notes)
    assert ch.profile_status().state == "full"


def test_a_running_profile_refuses_a_second_start_and_a_clear():
    ch = chan()
    ch.profile_start(997)
    for fn in (lambda: ch.profile_start(997), ch.profile_clear):
        try:
            fn()
            raise AssertionError("not refused")
        except Exception as e:                                    # StatusError 5
            assert getattr(e, "status", None) == P.BUSY
    assert ch.profile_stop().state == "stopped" and ch.profile_clear().samples == 0


# --- symbols ---------------------------------------------------------------------------------------------

OBJDUMP = """
40001000:\t4eb9 4000 2000 \tjsr 0x40002000
40001006:\t4e75           \trts
40001008:\t4fef fff0      \tlea %sp@(-16),%sp
4000100c:\t203c 4000 3000 \tmovel #1073754112,%d0
40001012:\t23c0 4000 0180 \tmovel %d0,0x40000180
40001018:\t4e75           \trts
40002000:\t4e56 0000      \tlinkw %fp,#0
40002004:\t4e75           \trts
40003000:\t4e73           \trte
"""


def test_objdump_function_starts():
    st = S.parse_objdump(OBJDUMP)
    assert st[0x40002000] == "fn_40002000"                        # a call target
    assert st[0x40001008] == "fn_40001008"                        # a frame opened after an rts
    assert st[0x40003000] == "isr_vec96"                          # installed in the vector table
    assert st[S.IDLE_PC] == "idle_spin" and st[S.AUDIO_ISR] == "audio_isr"


def test_lookup_stock_ours_and_unknown(tmp_path):
    code = {"chunk": {"load": 0x4670C000, "code": "00" * 0x100}, "c_chunk": {"load": 0x46AC0000, "code": "00" * 0x2000},
            "layout": {"c_text_end": 0x46AC1800, "wr_page": 0x4670C010}, "c_text_symbols": {"prof_tick": 0x46AC1000}}
    (tmp_path / "code.json").write_text(json.dumps(code))
    ours, regions = S.ours_from_code_json(tmp_path / "code.json")
    sym = S.Symbols.build(S.parse_objdump(OBJDUMP), ours, regions)
    assert sym.lookup(0x40002002) == ("fn_40002000", "stock")
    assert sym.lookup(0x46AC1004) == ("prof_tick", "ours")
    assert sym.lookup(0x46AC0004) == ("waverider_c+0x4", "ours")       # before its first name
    assert sym.lookup(0x4670C012) == ("wr_page", "ours")
    assert sym.lookup(0x46B00000)[0].startswith("ram_above_bss@")
    assert sym.lookup(0x10)[1] == "unknown"
    assert S.Symbols.from_json(sym.to_json()).lookup(0x46AC1004) == ("prof_tick", "ours")


def test_idle_needs_the_spin_at_mask_0():
    r = PR.Run("t", "timer", 997, "x", "now")
    r.statuses = [dict(state="stopped", source="timer", why=0, record_bytes=12, samples=3, capacity=SC.CAP,
                       period_ticks=132_397, t_start=0, t_now=132_000_000, f_start=0, f_now=1500, isr_ticks=1320,
                       fires=3, late=0, late_max=10, dropped=0, dtim0=0x00130002, dtrr0=0, intc=0, vector96=0, ring=0)]
    r.samples = [(S.IDLE_PC, S.IDLE_TCB, 0x2000, 1), (S.IDLE_PC, S.IDLE_TCB, 0x2500, 1), (0x40002002, 1, 0x2000, 1)]
    res = PR.analyse(r, S.Symbols.build(S.parse_objdump(OBJDUMP)))
    assert round(res["idle_pct"], 3) == round(100 / 3, 3)
    assert res["clocks"]["overhead_pct"] == 100 * 1320 / 132_000_000


# --- compare and the CLI ----------------------------------------------------------------------------------

def test_compare_and_the_cli(tmp_path, capsys):
    from dn2tools.cli import dn2test
    assert dn2test.main(["profile", "--sim", "--seconds", "2", "--label", "A", "--out", str(tmp_path)]) == 0
    assert dn2test.main(["profile", "--sim", "--fault", "no_dtim0", "--seconds", "2", "--label", "B",
                         "--out", str(tmp_path)]) == 0
    capsys.readouterr()
    assert dn2test.main(["profile", "--compare", str(tmp_path / "A.json"), str(tmp_path / "B.json")]) == 0
    out = capsys.readouterr().out
    assert "| idle % |" in out and "| audio_isr |" in out and "B - A" in out
    assert dn2test.main(["profile", "--report", str(tmp_path / "A.raw.json"), "--label", "A2",
                         "--out", str(tmp_path / "again")]) == 0
    assert (tmp_path / "again" / "A.md").exists()
    assert dn2test.main(["profile", "--sim", "--status"]) == 0
    assert "state" in capsys.readouterr().out
