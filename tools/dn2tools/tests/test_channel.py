"""The test channel (commands 33..43) against the simulator, its wire format against golden bytes, and the
firmware's rules (csrc/devtest) against the host's, read from the C source so the two cannot drift."""

from __future__ import annotations

import pathlib
import re
import struct
import sys

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
REPO = pathlib.Path(__file__).resolve().parents[3]

from dn2tools import keys as K  # noqa: E402
from dn2tools import protocol as P  # noqa: E402
from dn2tools import screen as S  # noqa: E402
from dn2tools.channel import TestChannel  # noqa: E402
from dn2tools.cli import dn2ui  # noqa: E402
from dn2tools.project import Project  # noqa: E402
from dn2tools.sim import DirectUnit  # noqa: E402
from dn2tools.unit import NoTestChannel, Refused, StatusError, request  # noqa: E402

PROJECT = Project.load(SRC / "dn2tools" / "data" / "project.json")
DEVTEST = REPO / "csrc" / "devtest" / "devtest.c"
WHITELIST = REPO / "csrc" / "devtest" / "whitelist.c"


def chan(faults=()):
    return TestChannel(DirectUnit(PROJECT, faults))


# --- the wire format ------------------------------------------------------------------------------

def test_pack7_round_trip_and_golden_request():
    for n in range(0, 40):
        data = bytes((k * 37 + n) & 0xFF for k in range(n))
        assert P.unpack7(P.pack7(data)) == data
    # BUILDINFO, seq 0x0102: header, pack7(01 02 21), F7
    assert P.encode(0x0102, P.BUILDINFO).hex() == "f000203c7d01" + "00010221" + "f7"
    # KEY with one press of SRC (2), at 0 ms, held 80 ms
    args = P.args_key([P.Event(P.PRESS, 2, 0, 80)])
    assert args.hex() == "01" + "0102" + "0000" + "0050"


def test_reply_decode_golden():
    raw = P.reply(7, P.ARM, P.REFUSED, b"\x00\x00\x00\x00\x01\x2c")
    r = P.decode(raw)
    assert (r.seq, r.cmd, r.status, r.data) == (7, P.ARM | 0x80, P.REFUSED, b"\x00\x00\x00\x00\x01\x2c")
    assert P.decode(b"\xF0\x00\x20\x3C\x7D\x02\x00\xF7") is None


def test_the_storage_commands_are_never_encoded():
    for cmd in (2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 20, 25, 26, 27, 28, 29, 30, 31, 39, 44, 99):   # 43: PROFILE since remoteui-5
        with pytest.raises(Refused):
            request(1, cmd)
    for cmd in P.ALLOWED:
        request(1, cmd)


# --- the firmware's rules and layouts, read from the C ----------------------------------------------

def test_func_ok_matches_the_firmware():
    body = re.search(r"static int func_ok\(u32 code\)\s*\{(.*?)\n\}", DEVTEST.read_text(), re.S).group(1)
    codes = set()
    for lo, hi in re.findall(r"code >= (\d+) && code <= (\d+)", body):
        codes |= set(range(int(lo), int(hi) + 1))
    codes |= {int(c) for c in re.findall(r"code == (\d+)", body)}
    assert codes == set(K.FUNC_OK)


def test_switch_defaults_match_the_words():
    text = WHITELIST.read_text()
    defs = [int(d) for d in re.findall(r'= \{"\w+",\s*\d+,\s*\d+,\s*(\d+)\}', text)]
    init = [int(v) for v in re.search(r"dt_sw\[DT_SW_N\][^=]*= \{([^}]*)\}", text).group(1).split(",")]
    assert defs == init and len(defs) == 3
    from dn2tools.sim_channel import SWITCHES
    assert [s[3] for s in SWITCHES] == defs


def test_key_codes_match_the_firmware_wiring():
    text = DEVTEST.read_text()
    assert "wire6[6] = {1, 0, 4, 5, 6, 7}" in text            # codes 49..54 on channel 6
    assert K.code_of("FUNC") == 17 and K.code_of("SETTINGS") == 8 and K.code_of("T16") == 40
    assert K.code_of("syn") == K.code_of("SRC") == 2
    assert K.code_of("PUSHH") == 48


def test_every_reply_fits_the_firmwares_buffer():
    """link.c's rp is 160 bytes: 4 of header and the longest reply's data"""
    assert 4 + 12 + 128 <= 160                                 # SCREEN
    assert 4 + 9 + 16 * 8 <= 160                               # TRACE
    assert 4 + 1 + 12 * 4 + 12 <= 160                          # COUNTERS
    assert 4 + 89 <= 160                                       # STATE (byte 88: the glass inverted)
    assert 4 + 4 + 128 <= 160                                  # PEEK
    assert 4 + 4 + 17 * 4 <= 160                               # PROFILE status
    assert 4 + 9 + P.PROF_PER_READ * P.PROF_RECORD <= 160      # PROFILE READ
    assert "static u8 rp[160]" in (REPO / "csrc" / "sampler" / "link.c").read_text()


# --- reads -----------------------------------------------------------------------------------------

def test_info_switches_peek_counters_trace_state():
    ch = chan()
    i = ch.info()
    assert i.proto == 1 and i.has("SCREEN") and i.has("KEY") and (i.width, i.height, i.chunks) == (128, 64, 8)
    names = [s.name for s in ch.switches()]
    assert names == ["HOLD", "LABELS", "ARMTIME"]
    assert ch.set_switch("hold", 0) == 0
    assert ch.switch_values()[0] == 0
    with pytest.raises(ValueError):
        ch.set_switch("ARMTIME", 5)
    with pytest.raises(StatusError) as e:                     # the firmware's own bound check
        ch.unit.call(P.SWITCH, P.args_switch_set(2, 5))
    assert e.value.status == P.RANGE
    assert ch.peek(0x40001000, 300)[:3] == bytes([0, 1, 2])
    with pytest.raises(StatusError) as e:
        ch.peek(0x50000000, 4)
    assert e.value.status == P.RANGE
    c = ch.counters(reset=True)
    assert c["switch_writes"] == 1 and ch.counters()["switch_writes"] == 0
    nxt, entries = ch.trace()
    assert [e.kind for e in entries][:1] == ["SWITCH"] and nxt == len(entries)
    s = ch.state()
    assert not s.armed and s.held == () and s.fb_front == 0x44623BC8


def test_a_build_without_the_channel_is_named():
    ch = chan(["no_channel"])
    with pytest.raises(NoTestChannel, match="test build"):
        ch.info()


# --- the screen ------------------------------------------------------------------------------------

def test_screen_readout_is_the_drawn_frame():
    ch = chan()
    frame = ch.screen()
    assert frame == ch.unit.sim.channel.frame()
    assert S.rows(S.from_rows(S.rows(frame))) == S.rows(frame)
    png = S.png(frame, 2)
    assert png.startswith(b"\x89PNG") and b"IEND" in png
    assert len(S.text(frame).splitlines()) == 32


def test_screen_survives_a_torn_first_copy():
    ch = chan(["torn"])
    assert len(ch.screen()) == 1024
    assert ch.counters()["screen_torn"] >= 1


# --- arming and keys ---------------------------------------------------------------------------------

def test_keys_need_the_handshake():
    ch = chan()
    with pytest.raises(StatusError) as e:
        ch.send_events([P.Event(P.PRESS, 2, 0, 80)])
    assert e.value.status == P.UNARMED
    nonce = struct.unpack(">I", ch.unit.call(P.ARM, P.args_arm_ask())[:4])[0]
    with pytest.raises(StatusError) as e:                     # a wrong nonce
        ch.unit.call(P.ARM, P.args_arm_confirm(nonce ^ 1))
    assert e.value.status == P.REFUSED
    with pytest.raises(StatusError):                          # the nonce is spent
        ch.unit.call(P.ARM, P.args_arm_confirm(nonce))
    assert ch.arm().armed


def test_func_src_opens_the_list_and_a_turn_moves_the_value():
    ch = chan()
    k = K.Keys(ch, log=None)
    k.arm()
    before = ch.screen()
    k.turn("A", +5)
    assert ch.unit.sim.channel.value == 69
    after_turn = ch.screen()
    assert S.differ(before, after_turn) == 5 * 6              # the bar grew five columns, six rows
    k.press("FUNC+SRC")
    sim = ch.unit.sim.channel
    assert sim.page == 100
    assert sim.events[-4:] == ["down 17", "down 2", "up 2", "up 17"]
    assert k.wait_for_screen(lambda f: f == sim.frame(), timeout=1) is not None
    k.turn("A", +2, push=True)
    assert sim.list_pos == 2
    k.press("NO")
    assert sim.page == 2


def test_every_key_goes_up_by_itself():
    ch = chan()
    k = K.Keys(ch, log=None)
    k.arm()
    k.hold("PLAY", 400, wait=False)
    ch.unit.wait(0.2)
    assert ch.state().held == (20,)
    ch.unit.wait(0.3)
    assert ch.state().held == ()


def test_disarm_and_timeout_let_every_key_go():
    ch = chan()
    k = K.Keys(ch, log=None)
    k.arm()
    k.hold("PLAY", 5000, wait=False)
    ch.unit.wait(0.1)
    assert ch.state().held == (20,)
    k.disarm()
    ch.unit.wait(0.02)
    assert ch.state().held == ()
    ch.set_switch("ARMTIME", 30)
    k.arm()
    k.hold("PLAY", 9000, wait=False)
    ch.unit.wait(5)
    assert ch.state().held == (20,)
    ch.unit.wait(26)
    s = ch.state()
    assert not s.armed and s.held == ()
    assert ch.counters()["auto_disarms"] == 1


def test_the_glass_is_inverted_while_armed_and_upright_after():
    """csrc/devtest dt_present: the glass turns at the UI pass after ARM, back after DISARM or the auto-disarm;
    SCREEN reads the frames upright either way"""
    ch = chan()
    k = K.Keys(ch, log=None)
    assert not ch.state().glass_inverted
    upright = ch.screen()
    k.arm()
    ch.unit.wait(0.02)
    assert ch.state().glass_inverted
    assert ch.screen() == upright                                # the mirror is never inverted
    k.disarm()
    ch.unit.wait(0.02)
    assert not ch.state().glass_inverted
    ch.set_switch("ARMTIME", 30)
    k.arm()
    ch.unit.wait(0.02)
    assert ch.state().glass_inverted
    ch.unit.wait(31)
    s = ch.state()
    assert not s.armed and not s.glass_inverted


def test_state_parses_with_and_without_the_glass_byte():
    d = bytes(88)
    assert P.parse_state(d).glass_inverted is False             # a build before the INVERT capability
    assert P.parse_state(d + b"\x01").glass_inverted is True


def test_the_capability_bits_match_the_firmware():
    text = DEVTEST.read_text()
    bits = {m.group(1): int(m.group(2)) for m in re.finditer(r"#define CAP_(\w+)\s+\(1u << (\d+)\)", text)}
    names = {"INFO": "BUILDINFO"}
    assert {names.get(k, k): v for k, v in bits.items()} == P.CAPS
    assert "| CAP_PROFILE | CAP_INVERT | CAP_USBCFG)" in text   # every bit advertised


# --- REMOTE CONTROL in SETTINGS > SYSTEM > USB CONFIG (csrc/devtest/usbcfg.c, 2026-11-12) ---------------

def test_what_answers_while_off_matches_the_firmware():
    body = re.search(r"static int off_ok\(u32 cmd, u32 sub\)\s*\{\s*return (.*?);\s*\}", DEVTEST.read_text(),
                     re.S).group(1)
    # the firmware's rule, word for word, and the host's table that mirrors it
    assert " ".join(body.split()) == ("cmd == 33 || cmd == 36 || cmd == 37 || cmd == 38 || (cmd == 34 && sub <= 1) "
                                      "|| (cmd == 41 && (sub == 2 || sub == 3))")
    answers = {(c, s) for c in range(30, 46) for s in range(6) if P.off_ok(c, s)}
    assert answers == ({(c, s) for c in (33, 36, 37, 38) for s in range(6)} | {(34, 0), (34, 1), (41, 2), (41, 3)})
    assert not P.off_ok(P.SCREEN, 0) and not P.off_ok(P.KEY, 1) and not P.off_ok(P.PEEK, 0)
    assert not P.off_ok(P.ARM, 0) and not P.off_ok(P.ARM, 1) and not P.off_ok(P.SWITCH, 2)
    assert "#define ST_OFF 7" in DEVTEST.read_text() and P.OFF == 7


def test_remote_control_off_refuses_and_disarms():
    """OFF in USB CONFIG: an armed channel disarms at the next UI pass (the glass turns back), the screen, keys,
    switch writes and the handshake are refused with OFF; the reads still answer, and BUILDINFO says it"""
    ch = chan()
    k = K.Keys(ch, log=None)
    assert ch.info().remote is True and ch.info().has("USBCFG")
    k.arm()
    ch.unit.wait(0.02)
    assert ch.state().glass_inverted
    ch.unit.sim.channel.remote = False
    ch.unit.wait(0.02)
    s = ch.state()                                             # STATE still answers
    assert not s.armed and not s.glass_inverted
    assert P.parse_buildinfo(ch.unit.call(P.BUILDINFO)).remote is False    # info() keeps the first answer
    for call in (ch.screen, lambda: ch.set_switch("ARMTIME", 30), k.arm, lambda: k.press("SRC")):
        with pytest.raises((StatusError, K.Blocked)) as e:
            call()
        if isinstance(e.value, StatusError):
            assert e.value.status == P.OFF
    assert ch.counters()["disarms"] == 1 and ch.counters()["auto_disarms"] == 0
    ch.unit.sim.channel.remote = True                              # back ON: the handshake works again
    k.arm()
    assert ch.state().armed


def test_buildinfo_parses_with_and_without_the_remote_byte():
    d = b"DTB1" + struct.pack(">HBBIBBBB", 1, 1, 0x12, 0xFFF, 3, 128, 64, 8) + bytes(16) + struct.pack(">I", 1000)
    assert P.parse_buildinfo(d).remote is None                 # a build before the USBCFG capability
    assert P.parse_buildinfo(d + b"\x00").remote is False
    assert P.parse_buildinfo(d + b"\x01").remote is True


def test_destructive_keys_are_refused_on_both_sides():
    ch = chan()
    k = K.Keys(ch, log=None)
    k.arm()
    with pytest.raises(K.Blocked):
        k.press("SETTINGS")
    with pytest.raises(K.Blocked):
        k.press("FUNC+YES")
    with pytest.raises(K.Blocked):
        k.press("NO+FUNC")                                    # FUNC over a held NO
    # the firmware refuses even when the host is bypassed
    with pytest.raises(StatusError) as e:
        ch.send_events([P.Event(P.PRESS, 8, 0, 80)])
    assert e.value.status == P.REFUSED
    ch.send_events([P.Event(P.PRESS, 17, 0, 300), P.Event(P.PRESS, 10, 50, 80)])   # FUNC, then YES
    ch.unit.wait(0.4)
    _, tr = ch.trace()
    refused = [e for e in tr if e.kind == "REFUSED"]
    assert [(e.a, P.REFUSE_WHY[e.b]) for e in refused] == [(8, "SETTINGS"), (10, "not with FUNC held")]
    assert "down 10" not in ch.unit.sim.channel.events


def test_allow_destructive_is_explicit():
    ch = chan()
    k = K.Keys(ch, allow_destructive=True, log=None)
    s = k.arm()
    assert s.destructive
    k.press("FUNC+YES")
    assert "down 10" in ch.unit.sim.channel.events


def test_bad_events_are_refused_whole():
    ch = chan()
    ch.arm()
    for ev in ([P.Event(P.PRESS, 99, 0, 80)], [P.Event(P.PRESS, 2, 0, 0)], [P.Event(P.ENCODER, 9, 0, 1)],
               [P.Event(P.ENCODER, 0, 0, 31)], [P.Event(P.PRESS, 2, 20000, 80)]):
        with pytest.raises(StatusError) as e:
            ch.send_events(ev)
        assert e.value.status == P.ARGS
    with pytest.raises(StatusError) as e:                     # sixteen slots: the 17th is busy
        ch.send_events([P.Event(P.PRESS, 25 + j, 5000, 80) for j in range(16)])
        ch.send_events([P.Event(P.PRESS, 2, 5000, 80)])
    assert e.value.status == P.BUSY


def test_event_log(tmp_path):
    ch = chan()
    log = tmp_path / "ev.jsonl"
    k = K.Keys(ch, log=log)
    k.arm()
    k.press("FUNC+SRC")
    lines = log.read_text().splitlines()
    assert '"arm"' in lines[0] and "press FUNC+SRC" in lines[1]


# --- the console commands, on the simulator -------------------------------------------------------

def test_dn2ui_snap_and_refusal(tmp_path, capsys):
    out = tmp_path / "s.png"
    assert dn2ui.main(["--sim", "--quiet", "snap", str(out)]) == 0
    assert out.read_bytes().startswith(b"\x89PNG")
    assert dn2ui._load_png(str(out), 4) == chan().screen()
    assert dn2ui.main(["--sim", "--log", str(tmp_path / "l"), "press", "SETTINGS"]) == 3
    assert "REFUSED" in capsys.readouterr().out
    assert dn2ui.main(["--sim", "--log", str(tmp_path / "l"), "press", "FUNC+SRC"]) == 0


def test_dn2test_inspect_commands(capsys):
    from dn2tools.cli import dn2test
    for cmd in (["info"], ["switches"], ["state"], ["counters"], ["trace"], ["peek", "0x40000000", "32"], ["smoke"]):
        assert dn2test.main(["--sim", *cmd]) == 0, cmd
    assert "SMOKE PASS" in capsys.readouterr().out


def test_ui_scenario_file_runs_on_the_simulator(tmp_path, capsys):
    sc = SRC / "dn2tools" / "data" / "ui" / "machine_list.json"
    assert dn2ui.main(["--sim", "--log", str(tmp_path / "l"), "run", str(sc), "--out", str(tmp_path / "o")]) == 0
    assert "PASS machine_list" in capsys.readouterr().out
    assert sorted(p.name for p in (tmp_path / "o").glob("*.png")) == ["0-page.png", "1-list.png", "2-moved.png", "3-closed.png"]


def test_the_default_port_name_finds_both_usb_modes():
    from dn2tools.unit import find_port
    for name in ("Digitone Audio+MIDI Elektron Digitone II", "Digitone OB Elektron Digitone II"):
        assert find_port(["IAC Driver Bus 1", name], "Elektron Digitone II") == name


# --- remoteui-6: the build's identity ---------------------------------------------------------------

def test_buildinfo_identity_waits_for_the_crc():
    import zlib

    from dn2tools import sim_channel as SC
    ch = chan()
    first = ch.info()
    assert first.identity is not None and not first.identity.ready and first.identity.crc == 0
    ident = ch.identity()
    assert ident.ready and ident.mod_version == "0.48"
    assert (ident.code_lo, ident.code_len, ident.crc) == (SC.SIM_CODE_LO, len(SC.SIM_CODE), zlib.crc32(SC.SIM_CODE))


def test_buildinfo_before_remoteui6_has_no_identity():
    old = b"DTB1" + struct.pack(">HBBIBBBB", 1, 0x01, 0x12, 0x7FF, 3, 128, 64, 8) + b"remoteui-5".ljust(16, b"\0") \
        + struct.pack(">I", 119)
    i = P.parse_buildinfo(old)
    assert i.label == "remoteui-5" and i.identity is None


def test_identity_matches_a_code_json(tmp_path):
    import json
    import zlib

    from dn2tools import buildid
    code = bytes(range(200)) + b"data written at run time"
    f = tmp_path / "waverider_code.json"
    f.write_text(json.dumps({"c_chunk": {"load": 0x46AC0000, "code": code.hex()}}))
    ident = P.BuildId("0.48", 0x46AC0000, 200, zlib.crc32(code[:200]), True, 0, 0)
    ok, line = buildid.match(ident, f)
    assert ok and line.startswith("MATCH")
    ok, line = buildid.match(P.BuildId("0.48", 0x46AC0000, 200, 0x12345678, True, 0, 0), f)
    assert not ok and "NO MATCH" in line
    ok, line = buildid.match(P.BuildId("0.48", 0x46AD0000, 200, 0, True, 0, 0), f)
    assert not ok and "has no code" in line


def test_the_firmware_crc_table_is_zlibs():
    """devtest.c id_step's nibble table, read from the source, gives zlib's CRC-32"""
    import zlib
    src = DEVTEST.read_text()
    body = re.search(r"crc_nib\[16\] = \{(.*?)\};", src, re.S).group(1)
    tab = [int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{8})u", body)]
    assert len(tab) == 16
    data = bytes((k * 151 + 7) & 0xFF for k in range(3000))
    c = 0xFFFFFFFF
    for b in data:                               # the firmware's loop, byte for byte
        c ^= b
        c = (c >> 4) ^ tab[c & 15]
        c = (c >> 4) ^ tab[c & 15]
    assert c ^ 0xFFFFFFFF == zlib.crc32(data)


def test_the_buildinfo_reply_layout_matches_the_firmware():
    """the C writes 36 + 1 (REMOTE) + 8 + 4 + 4 + 4 + 1 + 4 + 4 = 66 bytes, the layout parse_buildinfo reads"""
    src = DEVTEST.read_text()
    block = src[src.index("put32(rp + r, tps); r += 4;"):src.index("} else if (cmd == 34)")]
    assert re.findall(r"put32\(rp \+ r, ([^;]+?)\); r \+= 4;", block)[1:] == [
        "(u32)__image_start", "(u32)(__rodata_end - __image_start)", "s == ID_READY ? id_crc : 0u", "id_ticks",
        "id_slice_max"]
    assert "for (u32 k = 0; k < 8; k++)" in block and "rp[r++] = (u8)(s == ID_READY);" in block
