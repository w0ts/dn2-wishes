"""SAFE MODE's manual entry (STOP held alone at start-up, csrc/safemode/normal.c sm_poll) on a UI snapshot.

    DT2_MAIN_IMG=<stock 1.12 section 3> DNFW_EMU_FLAGS='{"weakptr": false}' \\
        bench_ns112.sh TREE python scripts/emu_safemode_stop.py BUILD.syx [--json OUT]

A from-reset run never reaches the UI loop (scripts/emu_safeboot.py), and sm_poll runs there (wr_poll, at the isDirty
site). So the build is installed over stock 1.12's UI snapshot the way scripts/emu_waverider_menu.py installs it (its
changed runs, then the platform loader's run-time copies: the area's data window and every CODE chunk, the kernel's
among them); sm_poll's clock starts at its first call, so the snapshot's own time does not count. The stock block
driver's read and write are played on a Python +Drive (as emu_safeboot.py does), the eMMC said ready.

Cases (each on a fresh machine; time in stock's panel ticks, 121 a second, as the machine's timers run them):
  stop     STOP (code 21) pressed alone right away and held 160 ticks (1.3 s): the record written once (pending 0,
           safe_tries 0, entered 1, this build), the SAFE mark of this build (kind 1, why 2) through the uncached
           alias, SOFTRST. (It is also the control of the no-entry cases: an entry made is seen.)
  tap      STOP alone for 25 ticks (0.2 s), let go, then 420 ticks (past the 360-tick window): no entry. (2026-11-21,
           main: a STOP pressed once just after power-on, to stop a playing pattern, must not enter SAFE MODE.)
  short    STOP alone for 90 ticks (0.75 s, under SM_STOP_HOLD 121), let go, then 420 ticks: no entry.
  chord    FUNC held first, then STOP, both held 160 ticks: no entry (no record write, no reset).
  none     no key, 160 ticks: no entry.
  For tap, short and stop, stock's button state (0x445a2e30) is read while STOP is down: STOP alone, inside the
  window (the press really reached the firmware's input while sm_poll was looking).
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

from dnfw.cli.files import read_image                          # noqa: E402
from dnfw.firmware.load import load                            # noqa: E402
from dnfw.mods import platform                                 # noqa: E402
from emulib.image import differences                           # noqa: E402
from emulib.machine import SNAP, Machine                       # noqa: E402
from emulib.panel import Panel                                 # noqa: E402

BLK_READ, BLK_WRITE, BLK_READY, BLK_SECTORS = 0x4012C87A, 0x4012CA60, 0x4461C68C, 0x4461C6B0
RESULT, DEVICE, SECTOR = 0x46A20C00, 48_340_992, 0x5FFB00   # v0.69.2: the record's place (dmove.h)
OLD_SECTOR = 0x6E0300                                        # (until v0.69.1)
SM_LOAD, MARK_UC, RCR = 0x476F8100, 0x476F8000 + 0x08000000, 0xEC090000
MAGIC_MARK, MAGIC_REC = 0x534D4D4B, 0x444E3242
STOP, FUNC = (2, 4), (2, 0)                                     # codes 21 and 17
KEYS, TICK = 0x445A2E30, 0x466768B0                            # stock's button state (8 channels); the panel tick
WINDOW, HOLD = 360, 121                                         # normal.c SM_STOP_TICKS, SM_STOP_HOLD
STOP_ALONE = bytes([0, 0, 0x10, 0, 0, 0, 0, 0])
HELD_LO = json.loads((HERE.parent / "src/dnfw/mods/waverider_code.json").read_text())["layout"]["smp_held_lo"]

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def install(machine: Machine, image: bytes) -> None:
    stock = pathlib.Path(os.environ["DT2_SECTIONS"], "section_3_MAIN_OS.bin").read_bytes()
    machine.apply(differences(stock, image))
    for va, blob in platform.runtime(image):
        machine.write(va, blob)
    machine.flush()


def case(image: bytes, script: list[tuple]) -> dict:
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
    from unicorn.m68k_const import UC_M68K_REG_A7

    machine = Machine(SNAP)
    install(machine, image)
    disk: dict[int, bytes] = {}
    r = {"io": [], "mark": bytearray(32), "reset": False, "build": machine.long(SM_LOAD + 4)}
    stub = bytes.fromhex("2039") + struct.pack(">I", RESULT) + bytes.fromhex("4e75")
    for va in (BLK_READ, BLK_WRITE):
        machine.write(va, stub)
    machine.write(BLK_READY, struct.pack(">I", 1))
    machine.write(BLK_SECTORS, struct.pack(">I", DEVICE))
    machine.write(MARK_UC, bytes(32))                           # (map the alias page the mark goes through)
    machine.flush()

    def driver(write):
        def hook(uc, address, size, user):
            sp = uc.reg_read(UC_M68K_REG_A7)
            sector, nbytes, buf = struct.unpack(">III", bytes(uc.mem_read(sp + 4, 12)))
            if write:
                data = bytes(uc.mem_read(buf, nbytes)) + bytes(-nbytes % 512)
                for k in range(len(data) // 512):
                    disk[sector + k] = data[512 * k:512 * k + 512]
            else:
                data = b"".join(disk.get(sector + k, bytes(512)) for k in range((nbytes + 511) // 512))
                uc.mem_write(buf, data[:nbytes])
            r["io"].append(("W" if write else "R", sector, nbytes))
            uc.mem_write(RESULT, struct.pack(">i", 0))
        return hook

    def at_mark(uc, access, addr, size, value, user):
        r["mark"][addr - MARK_UC:addr - MARK_UC + size] = value.to_bytes(size, "big")

    def at_rcr(uc, access, addr, size, value, user):
        if value & 0x80:
            r["reset"] = True
            uc.emu_stop()

    machine.uc.hook_add(UC_HOOK_CODE, driver(False), begin=BLK_READ, end=BLK_READ)
    machine.uc.hook_add(UC_HOOK_CODE, driver(True), begin=BLK_WRITE, end=BLK_WRITE)
    machine.uc.hook_add(UC_HOOK_MEM_WRITE, at_mark, begin=MARK_UC, end=MARK_UC + 31)
    machine.uc.hook_add(UC_HOOK_MEM_WRITE, at_rcr, begin=RCR, end=RCR)
    panel = Panel(machine, png_dir=str(HERE.parent / "out" / "safemode-stop"))
    held = 0
    r["ticks"] = 0
    for step in script:                                         # ("press", key), ("release", key), ("ticks", n)
        if r["reset"]:
            break
        if step[0] == "ticks":
            r["ticks"] += run_ticks(machine, panel, step[1], r)
            continue
        k = step[1]
        if step[0] == "press":
            if k[0] == 2:
                held |= 1 << k[1]
            machine.pc = panel.panelin.press(machine.m, panel.profile, k[0], k[1], held & ~(1 << k[1]))
            r["ticks"] += run_ticks(machine, panel, 4, r)
            r.setdefault("held_after_each", []).append((r["ticks"], hex(machine.long(HELD_LO)),
                                                        machine.read(KEYS, 8).hex()))
        else:
            if k[0] == 2:
                held &= ~(1 << k[1])
            machine.pc = panel.panelin.release(machine.m, panel.profile, k[0], k[1])
    r["record"] = disk.get(SECTOR)
    return r


def run_ticks(machine: Machine, panel: Panel, n: int, r: dict) -> int:
    """run until N of stock's panel ticks have gone (the machine's own timers move it, ~1.1 M instructions a tick),
    or a reset -> the ticks run"""
    done, last = 0, machine.long(TICK) & 0xFFF
    for _ in range(8 * n + 40):
        if done >= n or r["reset"]:
            break
        panel.settle(500_000)
        t = machine.long(TICK) & 0xFFF
        done += (t - last) & 0xFFF
        last = t
    return done


def rec_of(sector: bytes | None) -> dict | None:
    if not sector:
        return None
    w = struct.unpack(">8I", sector[:32])
    return {"magic": w[0], "build": w[2], "pending": w[3], "safe_tries": w[4], "entered": w[5],
            "crc_ok": zlib.crc32(sector[:28]) & 0xFFFFFFFF == w[7]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("build", type=pathlib.Path)
    ap.add_argument("--cases", default="stop,tap,short,chord,none")
    ap.add_argument("--json", type=pathlib.Path)
    a = ap.parse_args()
    image = load(read_image(a.build)).container.find(3).unpack()
    out = {}
    for name in a.cases.split(","):
        script = {"stop": [("press", STOP), ("ticks", 160)],
                  "tap": [("press", STOP), ("ticks", 25), ("release", STOP), ("ticks", WINDOW + 60)],
                  "short": [("press", STOP), ("ticks", 90), ("release", STOP), ("ticks", WINDOW + 60)],
                  "chord": [("press", FUNC), ("press", STOP), ("ticks", 160)],
                  "none": [("ticks", 160)]}[name]
        r = case(image, script)
        rec = rec_of(r["record"])
        body = struct.pack(">7I", MAGIC_MARK, 1, r["build"], 2, 0, 0, 0)
        want = body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        writes = [x for x in r["io"] if x[0] == "W" and x[1] in (SECTOR, OLD_SECTOR)]   # the record's (v0.69.2: the
        # moves' marks, written by the UI's first passes on this empty +Drive, are not the record's)
        if name == "stop":
            check("stop: STOP alone -> the record (pending 0, entered 1, this build), the SAFE mark (why 2), SOFTRST",
                  r["reset"] and bytes(r["mark"]) == want and rec is not None and rec["magic"] == MAGIC_REC
                  and rec["pending"] == 0 and rec["safe_tries"] == 0 and rec["entered"] == 1
                  and rec["build"] == r["build"] and rec["crc_ok"] and writes == [("W", SECTOR, 512)],
                  f"reset {r['reset']}, mark {bytes(r['mark']).hex()}, {rec}, io {r['io']}")
        else:
            check(f"{name}: no entry (no record write, no reset)", not r["reset"] and not writes,
                  f"reset {r['reset']}, io {r['io']}, held {r.get('held_after_each')}, ticks {r['ticks']}")
        if name in ("stop", "tap", "short"):
            seen = r.get("held_after_each") or [(None, None, "")]
            t_at, _lo, keys = seen[0]
            check(f"{name}: STOP alone in stock's button state, inside the window (tick {t_at} < {WINDOW})",
                  bytes.fromhex(keys) == STOP_ALONE and t_at is not None and t_at < WINDOW, f"{seen}")
        if name in ("tap", "short"):
            check(f"{name}: the run went past the window ({r['ticks']} ticks >= {WINDOW})", r["ticks"] >= WINDOW)
        out[name] = {"reset": r["reset"], "io": r["io"], "record": rec, "mark": bytes(r["mark"]).hex(),
                     "ticks": r["ticks"], "held": r.get("held_after_each")}
    print(f"{'PASS' if not failures else 'FAIL'}: {len(failures)} failure(s)")
    if a.json:
        a.json.write_text(json.dumps({"failures": failures, "cases": out}, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    os.environ.setdefault("DNFW_EMU_FLAGS", '{"weakptr": false}')
    raise SystemExit(main())
