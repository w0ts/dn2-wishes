"""SAFE MODE's question (O2, csrc/safemode/question.c) on stock 1.12's UI, in the ColdFire emulator.

    DT2_MAIN_IMG=<stock 1.12 section 3> DNFW_EMU_FLAGS='{"weakptr": false}' \\
        bench_ns112.sh TREE python scripts/emu_safemode_question.py BUILD.syx [--png-dir DIR] [--json OUT]

Why a snapshot and not a boot from reset: the from-reset runs (emulib.quickboot, scripts/emu_safeboot.py) never
reach the UI loop's isDirty site 0x4002e464 (measured 2026-11-21: no call of sm_isdirty and no MainScreenView by
1.1 G instructions; one start-up frame only), so the question cannot open there. The stock UI snapshot (ui1200M,
stock 1.12, the UI loop running) is put in the state the kernel's init leaves a SAFE boot in, as far as the
question reads it: the build's kernel chunk copied to SM_LOAD (its init not run: a snapshot is past the loader),
its sm_live set as a SAFE mark leaves it (kind SAFE, applied 1, reason 1), and O2 (`jsr sm_isdirty` at 0x4002e464)
written over stock's `jsr 0x4011d5d4`. Everything else is stock 1.12's own code, as in SAFE MODE. What
scripts/emu_safeboot.py part b proves from reset (MAIN OS = stock + the declared bytes) is not repeated here.

Checks:
  1. the question opens by itself: stock's ConfirmWindow constructor called from the kernel, sm_asked 1, a view of
     its class (0x4020671c) last on MainScreenView's screen, the screen redrawn (a PNG);
  2. YES (the panel's own UART bytes): sm_asked 2, the window gone, no reset;
  3. asked again (the harness clears sm_asked, its one poke), NO: the NORMAL-ONCE mark of this build (kind 2, why 3,
     its CRC) written through the uncached alias, then the reset control register's SOFTRST (the run stops there).
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
from dnfw.mods import platform, safemode as M                  # noqa: E402
from emulib.machine import SNAP, Machine                       # noqa: E402
from emulib.panel import NO, YES, Panel                        # noqa: E402

O2_SITE, ISDIRTY = 0x4002E464, 0x4011D5D4
QUESTION_CTOR, QUESTION_CLASS = 0x40112D0E, 0x4020671C
MAIN_VIEW = 0x44648980
MARK_UC, RCR = 0x476F8000 + 0x08000000, 0xEC090000
MAGIC_MARK = 0x534D4D4B

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def kernel_of(build: pathlib.Path) -> platform.area.CodeChunk:
    sec3 = load(read_image(build)).container.find(3).unpack()
    _, chunks = platform.split(sec3)
    codes = [platform.area.CodeChunk.unpack(d) for c, d in chunks if c == platform.area.CODE]
    return next(c for c in codes if c.load == M.SPEC["load"])


def _ram(a: int) -> bool:
    return 0x40000000 <= a < 0x48000000 and not a & 3


def views(machine: Machine) -> list[int]:
    mv = machine.long(MAIN_VIEW)
    if not _ram(mv) or not _ram(machine.long(mv + 44)):
        return []
    s = machine.long(mv + 44)
    node, out = machine.long(s + 28), []
    for _ in range(32):
        if node == s + 20 or not _ram(node):
            break
        v = machine.long(node + 8)
        out.append(machine.long(v) if _ram(v) else 0)
        node = machine.long(node)
    return out


def main() -> int:
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
    from unicorn.m68k_const import UC_M68K_REG_A7

    ap = argparse.ArgumentParser()
    ap.add_argument("build", type=pathlib.Path)
    ap.add_argument("--snapshot", default=SNAP)
    ap.add_argument("--png-dir", type=pathlib.Path, default=pathlib.Path("out/safemode-question"))
    ap.add_argument("--json", type=pathlib.Path)
    a = ap.parse_args()

    k = kernel_of(a.build)
    sym = M.SPEC["symbols"]
    build_id = struct.unpack_from(">I", k.image, 4)[0]
    machine = Machine(a.snapshot)
    if machine.read(O2_SITE, 6) != bytes.fromhex("4eb9") + struct.pack(">I", ISDIRTY):
        raise SystemExit("the snapshot's 0x4002e464 is not stock's jsr isDirty: a stock 1.12 UI snapshot is needed")
    machine.write(k.load, k.image)                                   # the kernel and its table, as the loader copies
    machine.write(sym["sm_live"], struct.pack(">III", 1, 1, 1))      # kind SAFE, applied, reason 1
    machine.write(MARK_UC, bytes(32))                                # (map the alias page the mark goes through)
    machine.write(O2_SITE, bytes.fromhex("4eb9") + struct.pack(">I", sym["sm_isdirty"]))
    machine.flush()

    st = {"ctor_from": [], "mark": bytearray(32), "reset": False}

    def at_ctor(uc, address, size, user):
        st["ctor_from"].append(struct.unpack(">I", bytes(uc.mem_read(uc.reg_read(UC_M68K_REG_A7), 4)))[0])

    def at_mark(uc, access, addr, size, value, user):
        st["mark"][addr - MARK_UC:addr - MARK_UC + size] = value.to_bytes(size, "big")

    def at_rcr(uc, access, addr, size, value, user):
        if value & 0x80:
            st["reset"] = True
            uc.emu_stop()

    machine.uc.hook_add(UC_HOOK_CODE, at_ctor, begin=QUESTION_CTOR, end=QUESTION_CTOR)
    machine.uc.hook_add(UC_HOOK_MEM_WRITE, at_mark, begin=MARK_UC, end=MARK_UC + 31)
    machine.uc.hook_add(UC_HOOK_MEM_WRITE, at_rcr, begin=RCR, end=RCR)

    panel = Panel(machine, png_dir=str(a.png_dir))
    asked = sym["sm_asked"]
    before = panel.screen("before") if panel.capture.frames else "(none)"
    panel.settle(40_000_000)
    v1, s1 = views(machine), machine.long(asked)
    shot_q = panel.screen("question")
    in_kernel = [f for f in st["ctor_from"] if k.load <= f < k.load + len(k.image)]
    check("the question opens by itself: ConfirmWindow from the kernel, last on MainScreenView's screen",
          s1 == 1 and in_kernel and v1[-1:] == [QUESTION_CLASS],
          f"sm_asked {s1}, ctor from {[hex(f) for f in st['ctor_from']]}, views {[hex(v) for v in v1]}, png {shot_q}")

    panel.tap(YES)
    panel.settle(20_000_000)
    v2, s2 = views(machine), machine.long(asked)
    shot_y = panel.screen("after-yes")
    check("YES: sm_asked 2, the window gone, no reset", s2 == 2 and QUESTION_CLASS not in v2 and not st["reset"],
          f"sm_asked {s2}, views {[hex(v) for v in v2]}, reset {st['reset']}, png {shot_y}")

    machine.write(asked, bytes(4))                                   # the one poke: ask again
    panel.settle(40_000_000)
    v3 = views(machine)
    panel.tap(NO)
    if not st["reset"]:
        panel.settle(20_000_000)
    body = struct.pack(">7I", MAGIC_MARK, 2, build_id, 3, 0, 0, 0)
    want = body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    check("NO: the NORMAL-ONCE mark of this build through the uncached alias, then SOFTRST",
          v3[-1:] == [QUESTION_CLASS] and st["reset"] and bytes(st["mark"]) == want,
          f"asked again {[hex(v) for v in v3]}, reset {st['reset']}, mark {bytes(st['mark']).hex()}, "
          f"sm_asked {machine.long(asked)}")

    print(f"{'PASS' if not failures else 'FAIL'}: {len(failures)} failure(s)")
    if a.json:
        a.json.write_text(json.dumps({"failures": failures, "screens": {"before": before, "question": shot_q,
                                                                       "yes": shot_y}}, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    os.environ.setdefault("DNFW_EMU_FLAGS", '{"weakptr": false}')
    raise SystemExit(main())
