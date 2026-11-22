"""scripts/flash_cli.py against the builder page's own code (tools/web/wishes-flash.js), on the host only.

Both sides run a whole session against the same fake Digitone II (in-process; no MIDI port is opened):
the page's createFlasher in node, flash_cli's Flasher here. Every message each side sends (Ping, Version,
Ping, Version, OsUpgradeStart, every OsUpgradeWrite) must be the same, byte for byte, for a real file of
scratch/flash (FLASH_CLI_SYX, or the main checkout's DN2wishes_v0.67.3_b9705c59_TEST.syx; the test skips
without it: firmware is not tracked).
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("flash_cli", ROOT / "scripts" / "flash_cli.py")
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)

SYX_NAME = "DN2wishes_v0.67.3_b9705c59_TEST.syx"

NODE_SESSION = r"""
const fs = require("fs");
const F = require(process.argv[2]);
const syx = new Uint8Array(fs.readFileSync(process.argv[3]));
const sent = [];
let fl, devSeq = 0x700;
function reply(ref, op, payload) {
  devSeq++;
  const body = [(devSeq >> 8) & 0xff, devSeq & 0xff, (ref >> 8) & 0xff, ref & 0xff, op | 0x80, ...payload];
  return Uint8Array.from([0xf0, 0x00, 0x20, 0x3c, 0x10, 0x00, ...F.encode87(body), 0xf7]);
}
function dn2(msg) {
  const r = F.parse(msg), p = r.payload;
  const str = (s) => [...Buffer.from(s, "latin1"), 0];
  if (r.op === 0x01) return reply(r.seq, r.op, [0x2b, 3, 0x50, 0x51, 0x52, ...str("Digitone II fake")]);
  if (r.op === 0x02) return reply(r.seq, r.op, [...str("B123"), ...str("1.12")]);
  if (r.op === 0x50) return reply(r.seq, r.op, [0, 0]);
  if (r.op === 0x51) {
    const len = ((p[4] << 24) | (p[5] << 16) | (p[6] << 8) | p[7]) >>> 0, off = ((p[8] << 24) | (p[9] << 16) | (p[10] << 8) | p[11]) >>> 0;
    const next = off + len, st = next === syx.length ? 1 : 0;
    return reply(r.seq, r.op, [(next >>> 24) & 0xff, (next >>> 16) & 0xff, (next >>> 8) & 0xff, next & 0xff, st, 0]);
  }
  return reply(r.seq, r.op, [0]);
}
fl = F.createFlasher({ paceMs: 0, send: (b) => { sent.push(Buffer.from(b)); const a = dn2(b); setTimeout(() => fl.receive(a), 0); } });
(async () => {
  const d = await fl.probe();
  if (!d.ok) throw new Error(d.errors.join("; "));
  await fl.flash(syx);
  if (fl.state !== "confirm") throw new Error("state " + fl.state);
  const img = F.checkImage(syx);
  fs.writeFileSync(process.argv[4], Buffer.concat(sent.flatMap((b) => { const n = Buffer.alloc(4); n.writeUInt32BE(b.length); return [n, b]; })));
  fs.writeFileSync(process.argv[4] + ".json", JSON.stringify({ n: sent.length, img }));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def fake_dn2(syx_len: int, bad_crc_at: int | None = None, silent_op: int | None = None, end_status: int = 0):
    """-> respond(msg) -> reply bytes or None: the same fake as NODE_SESSION's"""
    dev = [0x700]

    def reply(ref: int, op: int, payload: bytes) -> bytes:
        dev[0] += 1
        body = bytes([(dev[0] >> 8) & 0xFF, dev[0] & 0xFF, (ref >> 8) & 0xFF, ref & 0xFF, op | 0x80]) + payload
        return fc.HEADER + fc.encode87(body) + b"\xF7"

    def respond(msg: bytes) -> bytes | None:
        r = fc.parse(msg)
        if r.op == silent_op:
            return None
        if r.op == 0x01:
            return reply(r.seq, r.op, bytes([0x2B, 3, 0x50, 0x51, 0x52]) + b"Digitone II fake\0")
        if r.op == 0x02:
            return reply(r.seq, r.op, b"B123\x001.12\x00")
        if r.op == 0x50:
            return reply(r.seq, r.op, b"\0\0")
        if r.op == 0x51:
            n, off = int.from_bytes(r.payload[4:8], "big"), int.from_bytes(r.payload[8:12], "big")
            if off == bad_crc_at:
                return reply(r.seq, r.op, fc.be32(off) + b"\x02\0")
            nxt = off + n
            return reply(r.seq, r.op, fc.be32(nxt) + bytes([1 if nxt == syx_len else 0, 0]))
        if r.op == 0x52:
            return reply(r.seq, r.op, bytes([end_status]) + (b"refused\0" if end_status else b""))
        return reply(r.seq, r.op, b"\0")
    return respond


def py_session(syx: bytes, install: bool = False, **kw) -> tuple[list[bytes], object, Exception | None]:
    sent: list[bytes] = []
    respond = fake_dn2(len(syx), **kw)
    fl = None

    def send(b: bytes) -> None:
        sent.append(bytes(b))
        a = respond(b)
        if a is not None:
            fl.receive(a)
    fl = fc.Flasher(send, log=lambda s: None, pace_ms=0, timeouts={"PROBE_TIMEOUT_MS": 200, "WRITE_TIMEOUT_MS": 200,
                                                                    "CANCEL_WAIT_MS": 100,
                                                                    "INSTALL_TIMEOUT_MS": 200})
    err = None
    try:
        assert fl.probe()["ok"]
        fl.flash(syx, install=install)
    except fc.FlashError as e:
        err = e
    return sent, fl, err


def _syx() -> pathlib.Path:
    p = os.environ.get("FLASH_CLI_SYX")
    path = pathlib.Path(p) if p else fc.main_checkout() / "scratch" / "flash" / SYX_NAME
    if not path.is_file():
        pytest.skip(f"no {path} (firmware is not tracked)")
    return path


def test_crc_variant_and_framing():
    assert fc.crc32(b"123456789") == 0xD202D277
    raw = bytes(range(256)) * 3
    assert fc.decode87(fc.encode87(raw)) == raw
    assert fc.parse(fc.rpc(0x1234, 0x51, raw)).payload == raw


def test_same_bytes_as_the_web_page(tmp_path):
    if not shutil.which("node"):
        pytest.skip("no node")
    syx_path = _syx()
    syx = syx_path.read_bytes()
    js = tmp_path / "session.cjs"
    js.write_text(NODE_SESSION)
    out = tmp_path / "web.bin"
    r = subprocess.run(["node", str(js), str(ROOT / "tools" / "web" / "wishes-flash.js"), str(syx_path), str(out)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    web, buf, i = [], out.read_bytes(), 0
    while i < len(buf):
        n = int.from_bytes(buf[i:i + 4], "big")
        web.append(buf[i + 4:i + 4 + n])
        i += 4 + n
    ours, fl, err = py_session(syx)
    assert err is None and fl.state == "confirm"
    chunks = -(-len(syx) // 2048)
    assert len(ours) == len(web) == 4 + 1 + chunks
    for k, (a, b) in enumerate(zip(ours, web)):
        assert a == b, f"message {k} differs"
    assert hashlib.sha256(b"".join(ours)).digest() == hashlib.sha256(b"".join(web)).digest()
    import json
    img = json.loads((tmp_path / "web.bin.json").read_text())["img"]
    mine = fc.check_image(syx)
    assert img["ok"] and mine["ok"] and img["packets"] == mine["packets"] and img["usbBytes"] == mine["usbBytes"]


def test_stops_on_bad_crc_and_cancels():
    syx = _syx().read_bytes()
    sent, fl, err = py_session(syx, bad_crc_at=2048 * 3)
    assert err is not None and err.code == "crc" and fl.state == "failed"
    assert fc.parse(sent[-1]).op == 0x52 and fc.parse(sent[-1]).payload == b"\x00"
    assert sum(fc.parse(m).op == 0x51 for m in sent) == 4          # no resend


def test_stops_on_a_missing_reply_without_retry():
    syx = _syx().read_bytes()
    sent, fl, err = py_session(syx, silent_op=0x51)
    assert err is not None and err.code == "timeout" and fl.state == "failed"
    assert [fc.parse(m).op for m in sent] == [1, 2, 1, 2, 0x50, 0x51, 0x52]


def test_authorise(tmp_path):
    path = _syx()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    ok, why = fc.authorise(path, sha)
    assert ok, why
    assert not fc.authorise(path, "0" * 64)[0]
    other = tmp_path / SYX_NAME                                      # same file outside scratch/flash
    other.write_bytes(b"x")
    other.with_suffix(".txt").write_text(f"sha256 {sha}\n")
    assert not fc.authorise(other, sha)[0]


def ops(sent: list[bytes]) -> list[tuple[int, bytes]]:
    return [(fc.parse(m).op, fc.parse(m).payload) for m in sent]


def test_start_flag():
    assert fc.start_payload(5) == b"\0\0\0\x05sysex\0\x01"
    assert fc.start_payload(5, ask=False) == b"\0\0\0\x05sysex\0\x00"
    assert fc.parse(fc.install_message(7)).payload == b"\x01" and fc.parse(fc.install_message(7)).op == 0x52


def test_default_sends_no_end():
    syx = _syx().read_bytes()
    sent, fl, err = py_session(syx)
    assert err is None and fl.state == "confirm"
    o = ops(sent)
    assert o[4] == (0x50, fc.start_payload(len(syx), ask=True))
    assert all(op != 0x52 for op, _ in o)


def test_install_commits_once_after_status_1():
    syx = _syx().read_bytes()
    sent, fl, err = py_session(syx, install=True)
    assert err is None and fl.state == "installing"
    o = ops(sent)
    assert o[4] == (0x50, fc.start_payload(len(syx), ask=False))
    assert o[-1] == (0x52, b"\x01") and sum(op == 0x52 for op, _ in o) == 1
    assert o[-2][0] == 0x51 and sum(op == 0x51 for op, _ in o) == -(-len(syx) // 2048)


def test_install_never_commits_after_an_error():
    syx = _syx().read_bytes()
    sent, fl, err = py_session(syx, install=True, bad_crc_at=2048 * 3)
    assert err is not None and err.code == "crc" and fl.state == "failed"
    assert [p for op, p in ops(sent) if op == 0x52] == [b"\x00"]          # the cancel only
    sent, fl, err = py_session(syx, install=True, silent_op=0x51)
    assert err is not None and [p for op, p in ops(sent) if op == 0x52] == [b"\x00"]


def test_install_refused_or_unanswered_no_retry_no_cancel():
    syx = _syx().read_bytes()
    for kw, code in (({"end_status": 1}, "install"), ({"silent_op": 0x52}, "timeout")):
        sent, fl, err = py_session(syx, install=True, **kw)
        assert err is not None and err.code == code and fl.state == "unknown"
        assert [p for op, p in ops(sent) if op == 0x52] == [b"\x01"]       # one End 01, no cancel, no resend


def test_install_needs_yes_send():
    with pytest.raises(SystemExit):
        fc.main([str(_syx()), "--install"])
