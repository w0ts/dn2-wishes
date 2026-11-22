"""Send a Digitone II OS .syx over USB MIDI from the command line: the Wishes builder's "Flash from this page".

A port of tools/web/wishes-flash.js (and the Connect/Flash wiring in tools/web/builder.html), not a new
protocol. What it sends, as Elektron Transfer was recorded sending it (2026-11-21):

  - port: exactly one input and one output whose name holds "Digitone II" (case blind), else it stops.
  - framing: F0 00 20 3C 10 00 <8-in-7 of body> F7; body = seq:u16 BE, 00 00, opcode, payload.
    A reply's body = its own seq:u16, the request's seq:u16, opcode|0x80, payload.
  - Connect: 0x01 Ping, 0x02 SoftwareVersion (2 s each). The device must be a Digitone II (id 0x2B) that lists
    0x50/0x51/0x52 and runs OS 1.12. The flash itself probes once more, right before the start (as the page).
  - 0x50 OsUpgradeStart: file size u32 BE, "sysex\\0", then a flag: 0x01 = the DN2 asks UPGRADE OS NOW?
    itself (Transfer, the page, this script's default); 0x00 = it waits for the host's confirm (--install).
    Reply 0xD0 status 0 within 5 s.
  - 0x51 OsUpgradeWrite: crc u32 BE, length u32 BE, offset u32 BE, the file's bytes; 2,048 a chunk.
    crc = zlib.crc32(chunk, 0xFFFFFFFF) (Transfer's variant). One write outstanding at a time: the next
    goes 5 ms after the 0xD1 reply (3 s timeout; 15 s for the last chunk). Reply status 0 = ok,
    1 = last chunk taken, 2 = bad CRC, 3 = error.
  - Default (Transfer's way, no commit message): after status 1 the DN2 asks UPGRADE OS NOW? on its own
    screen; YES there installs.
  - --install (needs --yes-send): Start's flag is 0x00, and after the last write's status 1, and only then,
    one 0x52 OsUpgradeEnd 01 (commit). Stock 1.12 (read in its code, 2026-11-21; the same meaning as
    elkflash's --no-confirm): Start's flag is OsUpgradeState+32 ("ask on the DN2", 0x4012989e); with it 0,
    the checked image waits ("Waiting for confirm", 0x4012a122). End (handler 0x40126aa6, one u8) with a
    non-zero byte, the bytes received equal to Start's size and the state not failed (5) sets +33 "confirmed"
    (vfn16(1), the same call as YES on the question, lambda 0x401089fc) and posts the "ready" event
    (0x401298c8); the upgrade view then installs (event 20 -> 0x401094e8, PREPARING..., ERASING FLASH...).
    A failed check sets state 5 and End is refused. End 01 is sent once: never after an error, never
    retried, and no cancel follows it (once sent, the install may already run). An End answer other than
    status 0, or none in 5 s: the script stops and says to look at the DN2's screen.
  - On any failure after the start: one 0x52 00 (cancel), waits 1 s for its answer, then stops.

Differences from the page, all on the side of stopping: a bad-CRC reply stops the run (the page resends up to
3 times; --crc-resends N, N <= 3, allows the page's behaviour), and Ctrl-C is the page's Abort button.
Nothing is ever retried by this script: one error or one missing reply ends the run.

It refuses to send unless the file's sha256 matches its record: a .gate.json beside it that clears it
(scripts/web_bundle.cleared, as the builder page), or, for a test file in the main checkout's scratch/flash,
the NAME_TEST.txt beside NAME_TEST.syx whose "sha256 <hex>" line names it (and no "NOT CLEARED").

    python scripts/flash_cli.py --list
    python scripts/flash_cli.py --dry-run FILE.syx
    python scripts/flash_cli.py FILE.syx --yes-send          (sends it: the User's go only)
    python scripts/flash_cli.py FILE.syx --yes-send --install    (sends it and installs it, no YES on the DN2)

mido + python-rtmidi are needed for --list and sending (not for --dry-run); on the Mac they are in
scratch/remoteui/venv (python 3.15).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import queue
import re
import subprocess
import sys
import time
import zlib
from dataclasses import dataclass
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]

HEADER = bytes([0xF0, 0x00, 0x20, 0x3C, 0x10, 0x00])
OP = {"PING": 0x01, "VERSION": 0x02, "START": 0x50, "WRITE": 0x51, "END": 0x52}
ST = {"OK": 0, "LAST": 1, "BAD_CRC": 2, "ERROR": 3}
C = {
    "CHUNK": 2048,
    "PACE_MS": 5,
    "PROBE_TIMEOUT_MS": 2000,
    "START_TIMEOUT_MS": 5000,
    "WRITE_TIMEOUT_MS": 3000,
    "LAST_TIMEOUT_MS": 15000,
    "CANCEL_WAIT_MS": 1000,
    "INSTALL_TIMEOUT_MS": 5000,
    "MAX_CRC_RESENDS": 3,          # the page's; this script's default is 0 (--crc-resends)
    "USB_BUFFER": 0x200000,
    "USB_PACKET_BYTES": 101,
    "DEVICE_ID": 0x2B,
    "TRANSPORT_ID": 0x15,
    "STREAM_ID": 0x10,
    "OS_VERSION": "1.12",
}
PORT_MATCH = re.compile(r"Digitone II", re.I)
# The recording (scratch/flash-capture/capture-20261121-050724.txt, Transfer, 1,245 chunks): 0xD0 after
# 92 ms, then 8.78 ms a chunk (reply + pace) on average, the last reply 1,135 ms. Used only for the estimate.
REC_START_S, REC_CHUNK_S, REC_LAST_S = 0.092, (19.919 - 8.999) / 1244, 1.135


# -- bytes --
def encode87(src: bytes) -> bytes:
    out = bytearray()
    for j in range(0, len(src), 7):
        part = src[j:j + 7]
        acc = 0
        for k in range(7):
            acc <<= 1
            if k < len(part) and part[k] & 0x80:
                acc |= 1
        out.append(acc)
        out.extend(b & 0x7F for b in part)
    return bytes(out)


def decode87(src: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(src), 8):
        acc = src[i]
        for k in range(7):
            if i + 1 + k >= len(src):
                break
            out.append(src[i + 1 + k] | (0x80 if acc & (1 << (6 - k)) else 0))
    return bytes(out)


def crc32(data: bytes) -> int:
    """Transfer's chunk CRC: register init 0, final xor 0xFFFFFFFF."""
    return zlib.crc32(data, 0xFFFFFFFF)


def be32(n: int) -> bytes:
    return (n & 0xFFFFFFFF).to_bytes(4, "big")


def cstr(b: bytes, o: int) -> str:
    end = b.find(0, o)
    return bytes(b[o:end if end >= 0 else len(b)]).decode("latin-1")


def rpc(seq: int, op: int, payload: bytes = b"") -> bytes:
    body = bytes([(seq >> 8) & 0xFF, seq & 0xFF, 0, 0, op]) + bytes(payload)
    return HEADER + encode87(body) + b"\xF7"


@dataclass(frozen=True)
class Reply:
    seq: int
    ref: int
    op: int
    payload: bytes


def parse(raw: bytes) -> Reply | None:
    if not raw or len(raw) < len(HEADER) + 2 or raw[-1] != 0xF7 or raw[:len(HEADER)] != HEADER:
        return None
    body = decode87(raw[len(HEADER):-1])
    if len(body) < 5:
        return None
    return Reply((body[0] << 8) | body[1], (body[2] << 8) | body[3], body[4], body[5:])


def start_payload(size: int, ask: bool = True) -> bytes:
    """ask: the DN2 asks UPGRADE OS NOW? itself (0x01); False: it waits for the host's End 01 (0x00)"""
    return be32(size) + b"sysex\x00" + (b"\x01" if ask else b"\x00")


def chunk_length(size: int, off: int) -> int:
    return min(C["CHUNK"], size - off)


def write_message(seq: int, syx: bytes, off: int) -> bytes:
    n = chunk_length(len(syx), off)
    chunk = syx[off:off + n]
    return rpc(seq, OP["WRITE"], be32(crc32(chunk)) + be32(n) + be32(off) + chunk)


def cancel_message(seq: int) -> bytes:
    return rpc(seq, OP["END"], b"\x00")


def install_message(seq: int) -> bytes:
    return rpc(seq, OP["END"], b"\x01")


def parse_status(p: bytes) -> tuple[int, str]:
    return (p[0] if p else -1), cstr(p, 1)


def parse_write_reply(p: bytes) -> tuple[int, int, str] | None:
    if len(p) < 5:
        return None
    return int.from_bytes(p[0:4], "big"), p[4], cstr(p, 5)


def parse_ping(p: bytes) -> dict | None:
    if len(p) < 2:
        return None
    n = p[1]
    return {"id": p[0], "ops": list(p[2:2 + n]), "name": cstr(p, 2 + n)}


def parse_version(p: bytes) -> dict:
    build = cstr(p, 0)
    return {"build": build, "version": cstr(p, len(build.encode("latin-1")) + 1)}


# -- the checks (wishes-flash.js checkImage / checkDevice) --
def split_messages(syx: bytes) -> tuple[list[tuple[int, int]], str | None]:
    msgs, i = [], 0
    while i < len(syx):
        if syx[i] != 0xF0:
            return msgs, f"byte {i} is not the start of a SysEx message"
        j = i + 1
        while j < len(syx) and syx[j] != 0xF7 and not syx[j] & 0x80:
            j += 1
        if j >= len(syx) or syx[j] != 0xF7:
            return msgs, f"the message at byte {i} has no end"
        msgs.append((i, j + 1))
        i = j + 1
    return msgs, None


def check_image(syx: bytes) -> dict:
    errors: list[str] = []
    res = {"ok": False, "errors": errors, "packets": 0, "usbBytes": 0, "size": len(syx or b"")}
    if not syx:
        errors.append("no file")
        return res
    msgs, err = split_messages(syx)
    if err:
        errors.append(err)
        return res

    def m(k: int) -> bytes:
        return syx[msgs[k][0]:msgs[k][1]]

    def ctl(b: bytes, kind: int) -> bool:
        return (len(b) == 16 and b[1] == 0x00 and b[2] == 0x20 and b[3] == 0x3C and b[5] == 0x00
                and b[6] == 0x7F and b[7] == kind)

    def three(b: bytes, o: int) -> int:
        return (b[o] << 14) | (b[o + 1] << 7) | b[o + 2]

    if len(msgs) < 3:
        errors.append("too few messages for an OS file")
        return res
    head, tail = m(0), m(len(msgs) - 1)
    if not ctl(head, 1):
        errors.append("the first message is not an OS-file header")
        return res
    if not ctl(tail, 2):
        errors.append("the last message is not an OS-file trailer")
    if head[4] != C["TRANSPORT_ID"] or head[8] != C["STREAM_ID"]:
        errors.append("not a Digitone II OS file (another product's)")
    base, seq0, count = head[8], three(head, 9), three(head, 12)
    n = len(msgs) - 2
    if count != n:
        errors.append(f"the header announces {count} data packets, the file has {n}")
    if not errors and (three(tail, 9) != seq0 or three(tail, 12) != count):
        errors.append("header and trailer disagree")
    for k in range(1, n + 1):
        if len(errors) >= 5:
            break
        b = m(k)
        if len(b) != 128 or b[4] != head[4] or b[6] != 0x7E:
            errors.append(f"packet {k} is not a data packet")
            continue
        if three(b, 7) != ((seq0 + k - 1) & 0x1FFFFF):
            errors.append(f"packet {k} is out of order")
        acc = sum(b[7 + i] ^ ((base + i) & 0xFF) for i in range(119))
        if ((base + acc) & 0x7F) != b[126]:
            errors.append(f"packet {k} has a bad checksum")
    res["packets"] = n
    res["usbBytes"] = n * C["USB_PACKET_BYTES"]
    if res["usbBytes"] > C["USB_BUFFER"]:
        errors.append(f"the image decodes to {res['usbBytes']} bytes, over the DN2's 2 MiB receive buffer "
                      f"({C['USB_BUFFER']})")
    res["ok"] = not errors
    return res


def check_device(ping: dict | None, ver: dict | None) -> list[str]:
    errors: list[str] = []
    if not ping:
        errors.append("no Ping answer")
    else:
        if ping["id"] != C["DEVICE_ID"] or not re.match(r"Digitone II\b", ping["name"]):
            errors.append(f"not a Digitone II (id 0x{ping['id']:x})")
        for op in (OP["START"], OP["WRITE"], OP["END"]):
            if op not in ping["ops"]:
                errors.append(f"the device does not list opcode 0x{op:x}")
    if not ver:
        errors.append("no SoftwareVersion answer")
    elif ver["version"] != C["OS_VERSION"]:
        errors.append(f"the DN2 runs OS {ver['version'] or '?'}; this flashes only from OS {C['OS_VERSION']}")
    return errors


# -- the session (wishes-flash.js createFlasher) --
class FlashError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Flasher:
    """send(bytes): one SysEx message out. Every incoming SysEx message (F0..F7) goes to receive(), from any
    thread. One request waits at a time; a missing or wrong answer raises and nothing is retried."""

    def __init__(self, send: Callable[[bytes], None], log: Callable[[str], None] = print,
                 progress: Callable[[int, int], None] | None = None, pace_ms: float = C["PACE_MS"],
                 crc_resends: int = 0, timeouts: dict | None = None):
        if not 0 <= crc_resends <= C["MAX_CRC_RESENDS"]:
            raise ValueError(f"crc_resends must be 0..{C['MAX_CRC_RESENDS']}")
        self.send, self.log = send, log
        self.progress = progress or (lambda done, total: None)
        self.pace_ms, self.crc_resends = pace_ms, crc_resends
        self.t = {**C, **(timeouts or {})}
        self.counter = 0
        self.inbox: queue.Queue[bytes] = queue.Queue()
        self.state = "idle"

    def next_seq(self) -> int:
        self.counter = (self.counter + 1) & 0xFFFF
        return self.counter

    def receive(self, raw: bytes) -> None:
        self.inbox.put(bytes(raw))

    def request(self, op: int, timeout_ms: int, build: Callable[[int], bytes]) -> Reply:
        while not self.inbox.empty():          # anything that came in between requests: not an answer to this one
            self._ignore(self.inbox.get_nowait())
        seq = self.next_seq()
        try:
            self.send(build(seq))
        except Exception as e:  # the port's own error type varies (rtmidi, OSError)
            raise FlashError("send", f"the MIDI port refused the message: {e}") from e
        end = time.monotonic() + timeout_ms / 1000
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise FlashError("timeout", f"no answer to 0x{op:x} in {timeout_ms} ms")
            try:
                raw = self.inbox.get(timeout=left)
            except queue.Empty:
                continue
            r = parse(raw)
            if r and r.op == (op | 0x80) and r.ref == seq:
                return r
            self._ignore(raw, r)

    def _ignore(self, raw: bytes, r: Reply | None = None) -> None:
        r = r or parse(raw)
        if not r:
            self.log(f"ignored a message that is not an Elektron RPC ({len(raw)} B)")
            return
        if len(raw) == 885:
            self.log("a reply of exactly 885 bytes: another application may hold the port (docs/midi-rpc.md)")
        if r.op & 0x80:
            self.log(f"ignored a reply 0x{r.op:x} to request {r.ref} (not this session's)")

    def probe(self) -> dict:
        self.state = "probing"
        try:
            p = parse_ping(self.request(OP["PING"], self.t["PROBE_TIMEOUT_MS"], lambda s: rpc(s, OP["PING"])).payload)
            v = parse_version(self.request(OP["VERSION"], self.t["PROBE_TIMEOUT_MS"],
                                           lambda s: rpc(s, OP["VERSION"])).payload)
        except FlashError:
            self.state = "idle"
            raise
        errors = check_device(p, v)
        self.state = "idle" if errors else "ready"
        return {"ping": p, "version": v, "ok": not errors, "errors": errors}

    def cancel(self, why: str) -> None:
        self.log(f"cancelling: 0x52 00 ({why})")
        try:
            r = self.request(OP["END"], self.t["CANCEL_WAIT_MS"], cancel_message)
            self.log("cancel answered: " + r.payload.hex(" "))
        except FlashError as e:
            self.log(f"cancel: {e}")

    def flash(self, syx: bytes, install: bool = False) -> str:
        if self.state not in ("idle", "ready"):
            raise FlashError("state", f"cannot start while {self.state}")
        img = check_image(syx)
        if not img["ok"]:
            raise FlashError("image", "the file failed its checks: " + "; ".join(img["errors"]))
        dev = self.probe()                     # right before the start, as the page
        if not dev["ok"]:
            raise FlashError("device", "; ".join(dev["errors"]))
        size, started, committed = len(syx), False, False
        self.state = "starting"
        try:
            st, text = parse_status(self.request(OP["START"], self.t["START_TIMEOUT_MS"],
                                                 lambda s: rpc(s, OP["START"], start_payload(size, not install))).payload)
            started = True
            if st != 0:
                raise FlashError("start", f"the DN2 refused the update (status {st}{': ' + text if text else ''})")
            self.state = "writing"
            self.log(f"OsUpgradeStart accepted; {-(-size // C['CHUNK'])} chunks of {C['CHUNK']} B")
            self._write_all(syx)
            if not install:
                self.state = "confirm"
                self.log("the DN2 took the whole file; it now asks UPGRADE OS NOW? on its own screen")
                return self.state
            self.state, committed = "committing", True
            self.log("the DN2 took the whole file and checked it (status 1): 0x52 01, install")
            self._commit()
            self.state = "installing"
            self.log("the DN2 accepted the install: it now writes its flash (PREPARING..., ERASING FLASH...)")
            return self.state
        except (FlashError, KeyboardInterrupt) as e:
            err = e if isinstance(e, FlashError) else FlashError("aborted", "stopped by Ctrl-C")
            if committed:                      # End 01 went out: no cancel, no retry; the DN2's screen tells
                self.state = "unknown"
                raise FlashError(err.code, f"{err} (after the install command 0x52 01: look at the DN2's "
                                           "screen; nothing was cancelled or resent)") from None
            if started or self.state == "starting":
                self.cancel(str(err))
            self.state = "cancelled" if err.code == "aborted" else "failed"
            raise err from None

    def _commit(self) -> None:
        """one 0x52 01 after status 1; status 0 = installing. Never retried."""
        st, text = parse_status(self.request(OP["END"], self.t["INSTALL_TIMEOUT_MS"], install_message).payload)
        if st != 0:
            raise FlashError("install", f"the DN2 refused the install (status {st}{': ' + text if text else ''})")

    def _write_all(self, syx: bytes) -> None:
        size, off, resends = len(syx), 0, 0
        while True:
            n = chunk_length(size, off)
            last = off + n == size
            at = off
            r = self.request(OP["WRITE"], self.t["LAST_TIMEOUT_MS"] if last else self.t["WRITE_TIMEOUT_MS"],
                             lambda s: write_message(s, syx, at))
            w = parse_write_reply(r.payload)
            if not w:
                raise FlashError("reply", "a 0xD1 reply too short to read")
            nxt, st, text = w
            if st == ST["LAST"]:
                if not last or nxt != size:
                    raise FlashError("reply", f'the DN2 said "last chunk" at offset {nxt} of {size}')
                self.progress(size, size)
                return
            if st == ST["BAD_CRC"]:
                resends += 1
                if resends > self.crc_resends:
                    raise FlashError("crc", f"bad CRC at offset {off} (resends allowed: {self.crc_resends})")
                if nxt > off:
                    raise FlashError("reply", f"bad CRC but the DN2 asks for offset {nxt}, past {off}")
                self.log(f"bad CRC at offset {off}: resending from {nxt} ({resends}/{self.crc_resends})")
                off = nxt
            elif st == ST["OK"]:
                if nxt != off + n or last:
                    raise FlashError("reply", f"the DN2 asks for offset {nxt} after the chunk at {off} (+{n})"
                                              f"{', after the last chunk' if last else ''}")
                off, resends = nxt, 0
            else:
                raise FlashError("device", f"the DN2 stopped the update (status {st}{': ' + text if text else ''})")
            self.progress(off, size)
            if self.pace_ms > 0:
                time.sleep(self.pace_ms / 1000)


# -- what may be sent --
def main_checkout() -> pathlib.Path:
    r = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True)
    return (ROOT / r.stdout.strip()).resolve().parent if r.returncode == 0 and r.stdout.strip() else ROOT


def gate_records(path: pathlib.Path) -> list[pathlib.Path]:
    return [p for p in (pathlib.Path(str(path) + ".gate.json"), path.with_suffix(".gate.json")) if p.is_file()]


def test_record_sha(path: pathlib.Path) -> tuple[str | None, str]:
    """NAME_TEST.syx in scratch/flash -> (the sha256 its NAME_TEST.txt names, why not)"""
    flash_dirs = {(main_checkout() / "scratch" / "flash").resolve(), (ROOT / "scratch" / "flash").resolve()}
    if path.resolve().parent not in flash_dirs:
        return None, "not in scratch/flash"
    if not path.name.endswith("_TEST.syx"):
        return None, "not a NAME_TEST.syx file"
    txt = path.with_suffix(".txt")
    if not txt.is_file():
        return None, f"no {txt.name} beside it"
    text = txt.read_text(errors="replace")
    if re.search(r"NOT[ -]CLEARED", text):
        return None, f"{txt.name} says NOT CLEARED"
    shas = re.findall(r"^sha256 ([0-9a-f]{64})\s*$", text, re.M)
    if len(shas) != 1:
        return None, f"{txt.name} names {len(shas)} sha256 lines (want exactly 1)"
    return shas[0], ""


def authorise(path: pathlib.Path, sha: str) -> tuple[bool, str]:
    sys.path.insert(0, str(ROOT / "scripts"))
    from web_bundle import cleared             # the builder page's own verdict on a gate record
    for rec in gate_records(path):
        try:
            record = json.loads(rec.read_text())
        except (OSError, ValueError) as e:
            return False, f"{rec.name} unreadable: {e}"
        if cleared(record, sha):
            return True, f"cleared build: {rec.name} clears sha256 {sha}"
        return False, f"{rec.name} does not clear sha256 {sha}"
    want, why = test_record_sha(path)
    if want is None:
        return False, f"no clearing .gate.json and not a recorded test file ({why})"
    if want != sha:
        return False, f"{path.with_suffix('.txt').name} names sha256 {want}, the file is {sha}"
    return True, f"test file: {path.with_suffix('.txt').name} names sha256 {sha}"


# -- command line --
def estimate_s(size: int) -> float:
    chunks = -(-size // C["CHUNK"])
    return REC_START_S + max(chunks - 1, 0) * REC_CHUNK_S + REC_LAST_S


def describe(path: pathlib.Path, syx: bytes) -> dict:
    img = check_image(syx)
    msgs = 2 + 2 + 1 + -(-len(syx) // C["CHUNK"])     # Connect probe, flash probe, start, writes
    wire = sum(len(m) for m in (rpc(1, OP["PING"]), rpc(2, OP["VERSION"]), rpc(3, OP["PING"]),
                                rpc(4, OP["VERSION"]), rpc(5, OP["START"], start_payload(len(syx)))))
    wire += sum(len(write_message(0, syx, off)) for off in range(0, len(syx), C["CHUNK"]))
    return {"file": str(path), "bytes": len(syx), "sha256": hashlib.sha256(syx).hexdigest(),
            "image_ok": img["ok"], "image_errors": img["errors"], "os_packets": img["packets"],
            "usb_bytes": img["usbBytes"], "chunks": -(-len(syx) // C["CHUNK"]), "messages_out": msgs,
            "bytes_out": wire, "estimate_s": round(estimate_s(len(syx)), 1)}


def need_mido():
    try:
        import mido
        mido.set_backend("mido.backends.rtmidi")
        return mido
    except ImportError as e:
        raise SystemExit(f"needs mido and python-rtmidi ({e}); on the Mac: scratch/remoteui/venv/bin/python") from e


def cmd_list() -> int:
    mido = need_mido()
    for kind, names in (("in", mido.get_input_names()), ("out", mido.get_output_names())):
        for n in names:
            print(f"{kind:3} {'*' if PORT_MATCH.search(n) else ' '} {n}")
    return 0


def cmd_send(path: pathlib.Path, syx: bytes, crc_resends: int, install: bool = False) -> int:
    mido = need_mido()
    ins = [n for n in mido.get_input_names() if PORT_MATCH.search(n)]
    outs = [n for n in mido.get_output_names() if PORT_MATCH.search(n)]
    if len(ins) != 1 or len(outs) != 1:
        print(f"Found {len(ins)} Digitone II input(s) and {len(outs)} output(s): connect exactly one Digitone II "
              "by USB (USB MIDI or Overbridge), close Transfer/Overbridge/other MIDI programs. Nothing sent.")
        return 2
    t0 = time.monotonic()
    last = [-1]

    def progress(done: int, total: int) -> None:
        pct = done * 100 // total
        if pct != last[0] and (pct % 5 == 0 or done == total):
            last[0] = pct
            print(f"  {pct:3d} %  {done:,} / {total:,} B  {time.monotonic() - t0:6.1f} s", flush=True)

    out = mido.open_output(outs[0])
    fl = Flasher(lambda b: out.send(mido.Message("sysex", data=b[1:-1])), log=lambda s: print(s, flush=True),
                 progress=progress, crc_resends=crc_resends)

    def on_msg(m) -> None:
        if m.type == "sysex":
            fl.receive(bytes([0xF0, *m.data, 0xF7]))
    inp = mido.open_input(ins[0], callback=on_msg)
    print(f'ports: in "{ins[0]}", out "{outs[0]}"')
    try:
        d = fl.probe()                         # the page's Connect button
        print(f"Ping and SoftwareVersion answered: {d['ping']['name']} · OS {d['version']['version']} "
              f"(build {d['version']['build']})")
        if not d["ok"]:
            print("Not flashed: " + "; ".join(d["errors"]))
            return 1
        fl.flash(syx, install=install)
        if install:
            print(f"All {len(syx):,} bytes sent, checked by the DN2 and the install accepted in "
                  f"{time.monotonic() - t0:.1f} s. The Digitone II now writes its flash: do not switch it off "
                  "or unplug it until its screen says the upgrade is complete.")
            return 0
        print(f"All {len(syx):,} bytes sent and accepted in {time.monotonic() - t0:.1f} s. The Digitone II now "
              "asks UPGRADE OS NOW? on its own screen: YES installs it, NO keeps the current OS.")
        return 0
    except FlashError as e:
        if fl.state == "unknown":
            print(f"STOPPED after the install command ({e.code}): {e}. Do not switch the DN2 off while its "
                  "screen shows PREPARING... or ERASING FLASH...; nothing is retried by this script.")
            return 1
        print(f"STOPPED ({e.code}): {e}. Nothing is written to the DN2's flash before the install is "
              "confirmed. Switch the DN2 off and on before another try; nothing is retried by this script.")
        return 1
    except KeyboardInterrupt:                 # Ctrl-C before the start (flash() turns its own into FlashError)
        print("STOPPED (aborted): Ctrl-C before the update started. Nothing sent to the DN2's flash.")
        return 1
    finally:
        import threading                       # a CoreMIDI close was seen to hang (dn2tools/unit.py)
        th = threading.Thread(target=lambda: (inp.close(), out.close()), daemon=True)
        th.start()
        th.join(2.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", nargs="?", type=pathlib.Path)
    ap.add_argument("--list", action="store_true", help="print the MIDI ports (* = a Digitone II port)")
    ap.add_argument("--dry-run", action="store_true", help="check and describe FILE; opens no port")
    ap.add_argument("--yes-send", action="store_true", help="really send FILE to the Digitone II")
    ap.add_argument("--crc-resends", type=int, default=0, choices=range(0, C["MAX_CRC_RESENDS"] + 1),
                    help="resend a chunk the DN2 reports a bad CRC for, up to N times (the page: 3; default 0: stop)")
    ap.add_argument("--install", action="store_true",
                    help="with --yes-send: install after the transfer with no YES on the DN2 (Start flag 0, End 01)")
    a = ap.parse_args(argv)
    if a.install and not a.yes_send:
        ap.error("--install needs --yes-send")
    if a.list:
        return cmd_list()
    if not a.file:
        ap.error("FILE is needed (or --list)")
    syx = a.file.read_bytes()
    info = describe(a.file, syx)
    ok, why = authorise(a.file, info["sha256"])
    if a.dry_run:
        for k, v in info.items():
            print(f"{k:13} {v}")
        print(f"{'may send':13} {'yes' if ok else 'NO'}: {why}")
        return 0 if ok and info["image_ok"] else 1
    if not ok:
        print(f"refused: {why}. Nothing sent.")
        return 1
    if not info["image_ok"]:
        print("refused: the file failed its checks: " + "; ".join(info["image_errors"]))
        return 1
    if not a.yes_send:
        print(f"{why}. Not sent: add --yes-send to send it ({info['chunks']} chunks, ~{info['estimate_s']} s).")
        return 1
    print(f"{why}. Sending {a.file.name} ({len(syx):,} B, {info['chunks']} chunks, ~{info['estimate_s']} s).")
    print("--install: the DN2 installs it right after the transfer, with no UPGRADE OS NOW? question."
          if a.install else "The DN2 will ask UPGRADE OS NOW? after the transfer.")
    return cmd_send(a.file, syx, a.crc_resends, a.install)


if __name__ == "__main__":
    sys.exit(main())
