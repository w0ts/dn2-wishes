"""The code guard, in every emulator step (remoteui-6, 2026-11-12).

The test channel's BUILDINFO names the build by a CRC-32 of the C chunk's code and rodata,
[c_load, c_rodata_end) of src/dnfw/mods/waverider_code.json (csrc/devtest/devtest.c id_step). That
names the code running only while nothing writes into the range. With DNFW_CODEGUARD=1 (the gate sets
it for every emulator step) every write into it is checked against the chunk's own bytes: a loader
copying the image writes the same bytes and passes; any write that changes a byte is recorded with its
PC and callers, and when the process ends `CODEGUARD FAIL ...` is printed and it exits 98, failing the
step. With DNFW_CODEGUARD_LOG=FILE each process appends one JSON line there (range, writes seen, changed),
the evidence that the guard ran."""

from __future__ import annotations

import atexit
import json
import os
import pathlib
import struct
import sys

EXIT = 98
SPEC = pathlib.Path(__file__).resolve().parents[2] / "src/dnfw/mods/waverider_code.json"


def guarded() -> tuple[int, bytes]:
    """-> (start, the bytes that must stay) from the committed layout"""
    spec = json.loads(SPEC.read_text())
    lay = spec["layout"]
    lo, hi = lay["c_load"], lay["c_rodata_end"]
    image = bytes.fromhex(spec["c_chunk"]["code"])
    if spec["c_chunk"]["load"] != lo or not lo < hi <= lo + len(image):
        raise ValueError(f"{SPEC}: the guarded range {lo:#x}..{hi:#x} is not inside the C chunk")
    return lo, image[:hi - lo]


def after_boot(uc) -> str | None:
    """A boot from reset (scripts/emu_boot_check.py): its RAM is cleared and the chunk copied by the
    loader, so the guard there is the range compared whole once the boot has run. -> the failure line
    (`CODEGUARD FAIL ...`), or None when every byte is the chunk's."""
    lo, want = guarded()
    got = bytes(uc.mem_read(lo, len(want)))
    bad = [i for i in range(len(want)) if got[i] != want[i]]
    log = os.environ.get("DNFW_CODEGUARD_LOG")
    if log:
        with open(log, "a") as f:
            f.write(json.dumps({"argv": sys.argv[:3], "range": [f"{lo:#010x}", f"{lo + len(want):#010x}"],
                                "after_boot": True, "changed": len(bad)}) + "\n")
    if not bad:
        return None
    return (f"CODEGUARD FAIL: after the boot, {len(bad)} byte(s) of the C chunk's code or rodata differ from the "
            f"build's, the first at {lo + bad[0]:#010x}")


def install(uc) -> None:
    from unicorn import UC_HOOK_MEM_WRITE
    from unicorn import m68k_const as K
    lo, want = guarded()
    hi = lo + len(want)
    seen = {"writes": 0, "changed": 0, "first": []}

    def wrote(uc, access, address, size, value, user):
        seen["writes"] += 1
        new = (value & ((1 << 8 * size) - 1)).to_bytes(size, "big")
        a, b = max(address, lo), min(address + size, hi)
        if new[a - address:b - address] == want[a - lo:b - lo]:
            return
        seen["changed"] += 1
        if len(seen["first"]) < 8:
            pc = uc.reg_read(K.UC_M68K_REG_PC)
            sp = uc.reg_read(K.UC_M68K_REG_A7)
            try:
                words = struct.unpack(">32I", bytes(uc.mem_read(sp, 128)))
            except Exception:                   # noqa: BLE001
                words = ()
            callers = [f"{v:#010x}" for v in words if 0x40000400 <= v < 0x40220000 or 0x46700000 <= v < 0x46B00000][:6]
            seen["first"].append({"address": f"{address:#010x}", "size": size, "value": f"{value:#x}",
                                  "pc": f"{pc:#010x}", "callers": callers})

    uc.hook_add(UC_HOOK_MEM_WRITE, wrote, begin=lo, end=hi - 1)

    def at_exit():
        log = os.environ.get("DNFW_CODEGUARD_LOG")
        if log:
            with open(log, "a") as f:
                f.write(json.dumps({"argv": sys.argv[:3], "range": [f"{lo:#010x}", f"{hi:#010x}"],
                                    "writes": seen["writes"], "changed": seen["changed"]}) + "\n")
        if seen["changed"]:
            sys.stdout.flush()
            print(f"CODEGUARD FAIL: {seen['changed']} write(s) changed the C chunk's code or rodata "
                  f"({lo:#010x}..{hi:#010x}): {json.dumps(seen['first'])}", flush=True)
            sys.stderr.flush()
            os._exit(EXIT)

    atexit.register(at_exit)
