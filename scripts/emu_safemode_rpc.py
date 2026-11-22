"""The OS update RPC on stock 1.12's UI, plain and in SAFE MODE's state (toward safeboot part c).

    DT2_MAIN_IMG=<stock 1.12 section 3> bench_ns112.sh TREE python scripts/emu_safemode_rpc.py [BUILD.syx]
        [--chunks N] [--yes] [--json OUT]

The stock UI snapshot (ui1200M, stock 1.12, its UI loop running: the main application has registered its RPC methods
and set 0x445fb350) receives requests as USB MIDI delivers them: each whole SysEx message is handed to stock's USB
MIDI receive callback 0x4011f3c0(bytes, len) (registered with 0x4000434a at 0x400cef0a; it parses into port state 1
and posts to the MIDI task's queue 0x445f03e0). The MIDI task (prio 7) then takes it and calls the SysEx router in
its own context, so the RPC handler can post its job to the main application and wait for the answer, as on the
unit. (Calling the router directly from the snapshot's current context gets OsUpgradeStart refused, in stock too.)

Requests (envelope F0 00 20 3C 10 00 <pack7(seq u16, 00 00, opcode, payload)> F7, as Transfer's, captured in
scratch/flash-capture):
  Ping (0x01), SoftwareVersion (0x02), OsUpgradeStart (0x50: size, "sysex", flag 1 = the device asks),
  N x OsUpgradeWrite (0x51: crc32, length, offset, 2,048 B of stock 1.12's own .syx; scratch/web-flash-study.md),
  (--end-cancel: then OsUpgradeEnd (0x52) with 0, elkflash's cancel; Transfer's capture holds no 0x52). Never
  End(1) and never a YES: nothing is committed (flash is written only after the end and the device's own question).

Replies are captured at stock's sender 0x401236d2 and decoded; the "UPGRADE OS NOW?" window is seen at its
constructor call 0x40109a38 and as a view of class 0x4020671c on the screen.

With BUILD.syx the snapshot is first put in the state a SAFE boot's kernel leaves (the kernel chunk, sm_live SAFE,
O2), so SAFE MODE's own question is up when the requests arrive. Without it: stock 1.12 (the control).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import emu_safemode_question as Q                               # noqa: E402
from dnfw.mods import safemode as M                            # noqa: E402
from emulib.machine import SNAP, Machine                       # noqa: E402
from emulib.panel import Panel                                 # noqa: E402

USB_RX = 0x4011F3C0                       # stock's USB MIDI receive callback (bytes, len)
JOB_WAIT = 0x40129DB2                     # 0x40129c56's wait for the main application's answer: jsr 0x4000141a(d2)
MIDI_WAIT = 0x40120A7A                    # the MIDI task's loop: `jsr 0x4000141a` (its event wait), every pass
SENDER, UPGRADE_Q_SITE = 0x401236D2, 0x40109A38
ROUTER, RPC_ENTRY, RPC_ON = 0x4012194E, 0x40126CEC, 0x445FB350
HEAD = bytes.fromhex("f000203c1000")
CHUNK = 2048


def pack7(body: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(body), 7):
        group = body[i:i + 7]
        out.append(sum(0x40 >> k for k, b in enumerate(group) if b & 0x80))
        out += bytes(b & 0x7F for b in group)
    return bytes(out)


def unpack7(data: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(data):
        h = data[i]
        i += 1
        for k in range(7):
            if i >= len(data):
                break
            out.append(data[i] | (0x80 if h & (0x40 >> k) else 0))
            i += 1
    return bytes(out)


def crc(data: bytes) -> int:
    """the chunk CRC Transfer sends (scratch/flash-capture, 1,245 chunks): reflected CRC-32, register 0 at the
    start, the result inverted -- zlib.crc32 continued from 0xFFFFFFFF; plain zlib.crc32 draws status 2 (bad CRC)"""
    return zlib.crc32(data, 0xFFFFFFFF) & 0xFFFFFFFF


def request(seq: int, op: int, payload: bytes = b"") -> bytes:
    return HEAD + pack7(struct.pack(">HHB", seq, 0, op) + payload) + b"\xf7"


def decode(reply: bytes) -> dict:
    if not reply.startswith(HEAD) or not reply.endswith(b"\xf7"):
        return {"raw": reply[:48].hex()}
    body = unpack7(reply[6:-1])
    text = bytes(b for b in body[6:] if 0x20 <= b < 0x7F).decode()
    return {"body": body[:24].hex(), "op": hex(body[4]) if len(body) > 4 else None,
            "status": body[5] if len(body) > 5 else None, "text": text[:60]}


def main() -> int:
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_D2, UC_M68K_REG_PC

    ap = argparse.ArgumentParser()
    ap.add_argument("build", type=pathlib.Path, nargs="?")
    ap.add_argument("--snapshot", default=SNAP)
    ap.add_argument("--chunks", type=int, default=3)
    ap.add_argument("--json", type=pathlib.Path)
    ap.add_argument("--all", action="store_true", help="every chunk of the file (Transfer's whole upload)")
    ap.add_argument("--end-cancel", action="store_true", help="send OsUpgradeEnd(0) after the chunks")
    ap.add_argument("--chunk-settle", type=int, default=40_000_000, help="instructions run after each chunk")
    ap.add_argument("--sender-returns", action="store_true",
                    help="stock's sender returns 1 at once after the capture (no USB host in the emulator)")
    ap.add_argument("--watch", default="", help="comma list of code addresses: hits counted per request")
    a = ap.parse_args()

    image = pathlib.Path(os.environ["DT2_SYX"]).read_bytes()          # stock 1.12's own .syx: what Transfer sends
    machine = Machine(a.snapshot)
    st = {"mode": "safe" if a.build else "stock", "rpc_on": machine.read(RPC_ON, 1)[0], "steps": [],
          "upgrade_question": 0, "hits": {"router": 0, "rpc_entry": 0}}
    if a.build:
        k = Q.kernel_of(a.build)
        sym = M.SPEC["symbols"]
        machine.write(k.load, k.image)
        machine.write(sym["sm_live"], struct.pack(">III", 1, 1, 1))
        machine.write(Q.O2_SITE, bytes.fromhex("4eb9") + struct.pack(">I", sym["sm_isdirty"]))
        machine.flush()
    replies: list[bytes] = []

    def at_sender(uc, address, size, user):
        sp = uc.reg_read(UC_M68K_REG_A7)
        buf, n, _abort, _port = struct.unpack(">4I", bytes(uc.mem_read(sp + 4, 16)))
        replies.append(bytes(uc.mem_read(buf, n)) if 0 < n < 8192 else b"")
        if a.sender_returns:                       # the emulator has no USB host: the send "done" at once
            uc.reg_write(UC_M68K_REG_D0, 1)
            uc.reg_write(UC_M68K_REG_PC, struct.unpack(">I", bytes(uc.mem_read(sp, 4)))[0])
            uc.reg_write(UC_M68K_REG_A7, sp + 4)

    def at_upgrade_q(uc, address, size, user):
        st["upgrade_question"] += 1

    def counter(key):
        def h(uc, address, size, user):
            st["hits"][key] += 1
        return h

    machine.uc.hook_add(UC_HOOK_CODE, at_sender, begin=SENDER, end=SENDER)
    machine.uc.hook_add(UC_HOOK_CODE, at_upgrade_q, begin=UPGRADE_Q_SITE, end=UPGRADE_Q_SITE)
    machine.uc.hook_add(UC_HOOK_CODE, counter("router"), begin=ROUTER, end=ROUTER)
    machine.uc.hook_add(UC_HOOK_CODE, counter("rpc_entry"), begin=RPC_ENTRY, end=RPC_ENTRY)
    for w in [int(x, 0) for x in a.watch.split(",") if x]:
        st["hits"][hex(w)] = 0
        machine.uc.hook_add(UC_HOOK_CODE, counter(hex(w)), begin=w, end=w)
    panel = Panel(machine, png_dir=str(HERE.parent / "out" / f"safemode-rpc-{st['mode']}"))
    panel.settle(40_000_000)                                       # (SAFE: its own question opens first)
    st["views_before"] = [hex(v) for v in Q.views(machine)]
    buf = machine.alloc(8192)
    # The receive callback is entered by the MIDI task itself, at its loop's wait: digikit's `unblock` fakes that
    # wait (its poster is the USB interrupt, not modelled), so the task passes there all the time, and the message it
    # posts is taken on its next pass, as after a real wake-up. (Entered once from the snapshot's own context with a
    # Machine.call, only the first message was ever taken.) A trampoline: jsr USB_RX; addq.l #8,sp; jmp MIDI_WAIT.
    tramp = machine.alloc(16)
    machine.write(tramp, bytes.fromhex("4eb9") + struct.pack(">I", USB_RX) + bytes.fromhex("508f4ef9")
                  + struct.pack(">I", MIDI_WAIT))
    pending: list[int] = []

    def at_wait(uc, address, size, user):
        st["hits"]["midi_loop"] = st["hits"].get("midi_loop", 0) + 1
        if not pending:
            return
        n = pending.pop()
        sp = uc.reg_read(UC_M68K_REG_A7) - 8
        uc.mem_write(sp, struct.pack(">II", buf, n))
        uc.reg_write(UC_M68K_REG_A7, sp)
        uc.reg_write(UC_M68K_REG_PC, tramp)
        st["hits"]["injected"] = st["hits"].get("injected", 0) + 1

    machine.uc.hook_add(UC_HOOK_CODE, at_wait, begin=MIDI_WAIT, end=MIDI_WAIT)

    # The RPC job's answer comes through a semaphore on the MIDI task's stack, posted by the main application when it
    # has run the job. digikit's `unblock` fakes every pend it cannot see a poster for, and a stack semaphore is one:
    # faked, the wait returns at once and the answer byte is still 0 ("Could not initiate OS upgrade", in stock too).
    # Each such semaphore is put in digikit's own exception set the moment it is pended, so the wait is real.
    skip = machine.ev.get("unblock_skip")

    def at_job_wait(uc, address, size, user):
        sem = uc.reg_read(UC_M68K_REG_D2)
        st["hits"]["job_waits"] = st["hits"].get("job_waits", 0) + 1
        if skip is not None:
            skip.add(sem)

    machine.uc.hook_add(UC_HOOK_CODE, at_job_wait, begin=JOB_WAIT, end=JOB_WAIT)
    st["real_job_wait"] = skip is not None
    machine.flush()

    def send(name: str, msg: bytes, settle: int = 30_000_000, quiet: bool = False) -> None:
        before = len(replies)
        machine.write(buf, msg)
        machine.flush()
        if st["hits"].get("midi_loop"):
            pending.append(len(msg))
        else:                                       # parked in the snapshot: the first message wakes it
            machine.call(USB_RX, buf, len(msg))
        panel.settle(settle)
        got = [decode(r) for r in replies[before:]]
        st["steps"].append({"request": name, "bytes": len(msg), "replies": got})
        if not (quiet and len(got) == 1 and got[0].get("status") == 0):
            print(f"  {name}: {got} hits {st['hits']}", flush=True)

    seq = 0x0180
    send("Ping", request(seq + 1, 0x01))
    send("SoftwareVersion", request(seq + 2, 0x02))
    send("OsUpgradeStart", request(seq + 3, 0x50, struct.pack(">I", len(image)) + b"sysex\0" + b"\x01"), 60_000_000)
    st["views_after_start"] = [hex(v) for v in Q.views(machine)]
    st["png_start"] = panel.screen("after-start")
    chunks = -(-len(image) // CHUNK) if a.all else a.chunks
    st["chunks_sent"] = chunks
    for n in range(chunks):
        off = n * CHUNK
        data = image[off:off + CHUNK]
        send(f"OsUpgradeWrite {off}", request(seq + 4 + n, 0x51, struct.pack(">III", crc(data),
                                                                            len(data), off) + data), a.chunk_settle,
             quiet=2 <= n < chunks - 3)
    if a.end_cancel:                     # (Transfer's capture holds no 0x52: its form is elkflash's, unverified)
        send("OsUpgradeEnd(0) cancel", request(seq + 4 + chunks, 0x52, struct.pack(">I", 0)), 40_000_000)
    panel.settle(60_000_000)                                       # (time for the question after the last chunk)
    st["views_after"] = [hex(v) for v in Q.views(machine)]
    st["statuses"] = sorted({r.get("status") for x in st["steps"] for r in x["replies"]}, key=str)
    st["png_end"] = panel.screen("after-end")
    print(json.dumps({k: v for k, v in st.items() if k != "steps"}, indent=1))
    bad = verdict(st["steps"], chunks, len(image))
    print(f"{'PASS' if not bad else 'FAIL'}: {len(bad)} failure(s) {bad}")
    if a.json:
        a.json.write_text(json.dumps({**st, "failures": bad}, indent=1))
    return 1 if bad else 0


def verdict(steps: list[dict], chunks: int, total: int) -> list[str]:
    """what Transfer needs answered (scratch/flash-capture): Ping, SoftwareVersion 1.12, OsUpgradeStart accepted
    (0xD0, status 0), every OsUpgradeWrite accepted (0xD1, status 0, the next offset = this one + its length)"""
    bad = []
    by = {x["request"]: x["replies"] for x in steps}

    def one(name):
        r = by.get(name) or []
        return r[0] if len(r) == 1 else {}
    if one("Ping").get("op") != "0x81":
        bad.append("Ping")
    if one("SoftwareVersion").get("op") != "0x82" or "1.12" not in one("SoftwareVersion").get("text", ""):
        bad.append("SoftwareVersion")
    if one("OsUpgradeStart").get("op") != "0xd0" or one("OsUpgradeStart").get("status") != 0:
        bad.append("OsUpgradeStart")
    for n in range(chunks):
        r = one(f"OsUpgradeWrite {n * CHUNK}")
        body = bytes.fromhex(r.get("body", ""))
        # 0xD1: the next offset (u32) right after the opcode, then the status (Transfer's capture: d1 00000800 00 00;
        # a bad CRC: d1 00000000 02 00)
        nxt = int.from_bytes(body[5:9], "big") if len(body) >= 10 else -1
        status = body[9] if len(body) >= 10 else -1
        last = (n + 1) * CHUNK >= total
        if r.get("op") != "0xd1" or status not in ((0, 1) if last else (0,)) \
                or (not last and nxt != (n + 1) * CHUNK):
            bad.append(f"OsUpgradeWrite {n * CHUNK} (next {nxt})")
    return bad


if __name__ == "__main__":
    os.environ.setdefault("DNFW_EMU_FLAGS", '{"weakptr": false}')
    raise SystemExit(main())
