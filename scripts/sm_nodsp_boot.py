"""SAFE MODE stage 1 (read-only): stock 1.12 booted from reset with the DSP upload refused.

    bench_ns112.sh TREE python scripts/sm_nodsp_boot.py MODE [--limit N] [--json OUT]

MODE:
  control   stock 1.12 as it is (the uploader decodes and pushes stock's section 7)
  refused   the uploader's depack call (jsr 0x40136820 at 0x400cf73a) is skipped and answers 0x100000,
            the answer SAFE MODE's override O1 would give: the uploader takes its stock error path
            (no byte pushed over DSPI, the DSP left in reset)
  empty     refused, and the boot-flags word 0x40287a60 has bit 0 (the ESM's EMPTY RESET) ORed in at
            MAIN OS's entry: stock's start-up project path without the +Drive project read

The emulator (digikit dspboot via emulib.quickboot) runs no SSI audio interrupt at all, so every mode boots
with no audio frames: what a DSP held in reset would give if the SHARC clocks the TDM link.

After LIMIT instructions, three RPC requests captured from Transfer (scratch/flash-capture, 2026-11-21) are
put through stock's SysEx router 0x4012194e(msg, len, USB) from the idle task's spin (0x400cf246): Ping,
SoftwareVersion, OsUpgradeStart (size 2,549,152, 'sysex', flag 1). The machine then runs on, and the replies
are captured at stock's sender 0x401236d2; the "UPGRADE OS NOW?" question is seen when the ConfirmWindow
constructor 0x40112d0e is called from its RPC site (0x40109a38). No 0x51 or 0x52 is sent: nothing is ever
written to the emulated flash.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/mnt/d/01_Code/Z_Personal/digikit-up")

from emu import symbols                                        # noqa: E402
from emulib import quickboot                                   # noqa: E402
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE            # noqa: E402
from unicorn.m68k_const import (UC_M68K_REG_A7, UC_M68K_REG_D0, UC_M68K_REG_PC,  # noqa: E402
                                UC_M68K_REG_A2)

REPORTER = 0x4011ED4A                     # the 1.12 fault reporter (emu_boot_check)
DEPACK_CALL, DEPACK_RET = 0x400CF73A, 0x400CF740
UPLOADER, UPLOADER_RET = 0x400CF4B0, 0x400CF7EA
PUSHR = 0xEC038034
ENTRY_FLAGS_STORE = 0x400004F2            # right after `move.l (a0),0x40287a60` at 0x400004ec
FLAGS = 0x40287A60
IDLE_SPIN = 0x400CF246
ROUTER, SENDER = 0x4012194E, 0x401236D2
QUESTION_CTOR, UPGRADE_Q_SITE = 0x40112D0E, 0x40109A38
EMMC_READY_POINT = 0x400CF0F2
PROJECT_START = 0x400BB3C0                # the start-up project routine (flags)
PROJECT_READ = 0x400F2168                 # reads the persisted state, then the working project
MRAM_FLAG = 0x405CE858
TASK_CREATE = 0x400012C8
USB = 2
MSG_BUF = 0x47F00000                      # free RAM above BSS (nothing of stock's above 0x466b84d0)

RPC = [
    ("Ping", "f000203c1000200101000001f7"),
    ("SoftwareVersion", "f000203c1000200103000002f7"),
    ("OsUpgradeStart", "f000203c100020011d00005000266065207379736578000001f7"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("control", "refused", "empty"))
    ap.add_argument("--limit", type=int, default=700_000_000)
    ap.add_argument("--after", type=int, default=150_000_000, help="instructions run after the RPC requests")
    ap.add_argument("--json", type=pathlib.Path)
    ap.add_argument("--watch", default="", help="comma list of extra code addresses: hits counted")
    a = ap.parse_args()

    syx = os.environ["DT2_SYX"]                                 # stock 1.12 (bench_ns112.sh)
    image = open(os.path.join(os.environ["DT2_SECTIONS"], "section_3_MAIN_OS.bin"), "rb").read()
    profile = symbols.resolve(image)
    holder = {}
    st = {"frames": 0, "frames_after_rpc": 0, "fault": None, "pushed": 0, "uploader": 0, "uploader_ret": 0,
          "depack_answer": None, "tasks": [], "emmc_ready_point": 0, "project_start_flags": None,
          "project_read": 0, "mram_flag_writes": [], "questions": [], "upgrade_question": 0, "replies": [],
          "rpc_sent": False, "rpc_queue": [], "flags_at_entry": None}

    def pre_start(m):
        uc = m.uc

        def at_frame(uc, address, size, user):
            st["frames"] += 1
            if st["rpc_sent"]:
                st["frames_after_rpc"] += 1

        def at_reporter(uc, address, size, user):
            a2 = uc.reg_read(UC_M68K_REG_A2)
            try:
                rec = bytes(uc.mem_read(a2, 16)).hex()
            except Exception:                                   # noqa: BLE001
                rec = ""
            st["fault"] = {"a2": hex(a2), "record": rec}
            uc.emu_stop()

        def at_push(uc, access, addr, size, value, user):
            if (value >> 16) & 0xFFFF == 0x9001:
                st["pushed"] += 1

        def at_depack(uc, address, size, user):
            if a.mode != "control":                              # skip the call: answer as O1 would
                uc.reg_write(UC_M68K_REG_D0, 0x100000)
                uc.reg_write(UC_M68K_REG_PC, DEPACK_RET)

        def at_depack_ret(uc, address, size, user):
            st["depack_answer"] = uc.reg_read(UC_M68K_REG_D0)

        def at_entry(uc, address, size, user):
            st["flags_at_entry"] = struct.unpack(">I", bytes(uc.mem_read(FLAGS, 4)))[0]
            if a.mode == "empty":
                uc.mem_write(FLAGS, struct.pack(">I", st["flags_at_entry"] | 1))

        def count(key):
            def h(uc, address, size, user):
                st[key] += 1
            return h

        def at_task(uc, address, size, user):
            sp = uc.reg_read(UC_M68K_REG_A7)
            ret, tcb, entry, prio = struct.unpack(">IIII", bytes(uc.mem_read(sp, 16)))
            st["tasks"].append({"from": hex(ret), "entry": hex(entry), "prio": prio,
                                "before_emmc_ready_point": st["emmc_ready_point"] == 0})

        def at_project(uc, address, size, user):
            sp = uc.reg_read(UC_M68K_REG_A7)
            st["project_start_flags"] = hex(struct.unpack(">I", bytes(uc.mem_read(sp + 4, 4)))[0])

        def at_mram(uc, access, addr, size, value, user):
            st["mram_flag_writes"].append(value)

        def at_question(uc, address, size, user):
            sp = uc.reg_read(UC_M68K_REG_A7)
            st["questions"].append(hex(struct.unpack(">I", bytes(uc.mem_read(sp, 4)))[0]))

        def at_sender(uc, address, size, user):
            sp = uc.reg_read(UC_M68K_REG_A7)
            buf, n, abort, port = struct.unpack(">4I", bytes(uc.mem_read(sp + 4, 16)))
            data = bytes(uc.mem_read(buf, n)) if 0 < n < 4096 else b""
            st["replies"].append({"len": n, "port": port, "head": data[:24].hex()})

        def at_spin(uc, address, size, user):
            # the idle task (prio 1) only runs when every other task waits: route one queued request
            if not st["rpc_queue"]:
                return
            name, msg = st["rpc_queue"].pop(0)
            uc.mem_write(MSG_BUF, msg)
            sp = uc.reg_read(UC_M68K_REG_A7) - 16
            uc.mem_write(sp, struct.pack(">IIII", IDLE_SPIN, MSG_BUF, len(msg), USB))
            uc.reg_write(UC_M68K_REG_A7, sp)
            uc.reg_write(UC_M68K_REG_PC, ROUTER)
            st.setdefault("routed", []).append(name)

        uc.hook_add(UC_HOOK_CODE, at_frame, begin=profile.panel_diff, end=profile.panel_diff)
        uc.hook_add(UC_HOOK_CODE, at_reporter, begin=REPORTER, end=REPORTER)
        uc.hook_add(UC_HOOK_MEM_WRITE, at_push, begin=PUSHR, end=PUSHR + 3)
        uc.hook_add(UC_HOOK_CODE, at_depack, begin=DEPACK_CALL, end=DEPACK_CALL)
        uc.hook_add(UC_HOOK_CODE, at_depack_ret, begin=DEPACK_RET, end=DEPACK_RET)
        uc.hook_add(UC_HOOK_CODE, at_entry, begin=ENTRY_FLAGS_STORE, end=ENTRY_FLAGS_STORE)
        uc.hook_add(UC_HOOK_CODE, count("uploader"), begin=UPLOADER, end=UPLOADER)
        uc.hook_add(UC_HOOK_CODE, count("uploader_ret"), begin=UPLOADER_RET, end=UPLOADER_RET)
        uc.hook_add(UC_HOOK_CODE, count("emmc_ready_point"), begin=EMMC_READY_POINT, end=EMMC_READY_POINT)
        uc.hook_add(UC_HOOK_CODE, at_task, begin=TASK_CREATE, end=TASK_CREATE)
        uc.hook_add(UC_HOOK_CODE, at_project, begin=PROJECT_START, end=PROJECT_START)
        uc.hook_add(UC_HOOK_CODE, count("project_read"), begin=PROJECT_READ, end=PROJECT_READ)
        uc.hook_add(UC_HOOK_MEM_WRITE, at_mram, begin=MRAM_FLAG, end=MRAM_FLAG + 3)
        uc.hook_add(UC_HOOK_CODE, at_question, begin=QUESTION_CTOR, end=QUESTION_CTOR)
        uc.hook_add(UC_HOOK_CODE, count("upgrade_question"), begin=UPGRADE_Q_SITE, end=UPGRADE_Q_SITE)
        uc.hook_add(UC_HOOK_CODE, at_sender, begin=SENDER, end=SENDER)
        uc.hook_add(UC_HOOK_CODE, at_spin, begin=IDLE_SPIN, end=IDLE_SPIN)
        st["watch"] = {}
        for w in [int(x, 0) for x in a.watch.split(",") if x]:
            def hit(uc, address, size, user):
                k = hex(address)
                st["watch"][k] = st["watch"].get(k, 0) + 1
                st["watch"].setdefault("first_" + k, "after_rpc" if st["rpc_sent"] else "boot")
            uc.hook_add(UC_HOOK_CODE, hit, begin=w, end=w)

    m, stq, stop = quickboot.run(syx, image, limit=a.limit, machine_out=holder, pre_start=pre_start)
    boot = {"stop": repr(stop), "frames": st["frames"], "fault": st["fault"]}
    print("boot:", json.dumps(boot), flush=True)
    if st["fault"] is None:
        m.ensure(MSG_BUF)
        st["rpc_sent"] = True
        st["rpc_queue"] = [(n, bytes.fromhex(h)) for n, h in RPC]
        uc = m.uc
        try:
            uc.emu_start(uc.reg_read(UC_M68K_REG_PC), 0xFFFFFFFF, count=a.after)
        except Exception as ex:                                 # noqa: BLE001
            st["after_error"] = repr(ex)
    st.pop("rpc_queue", None)
    out = {"mode": a.mode, "limit": a.limit, "after": a.after, **st}
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
