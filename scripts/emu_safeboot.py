"""SAFE MODE from reset in the ColdFire emulator (docs/safe-mode.md; the gate's `safeboot` step).

    bench_ns112.sh TREE python scripts/emu_safeboot.py STOCK.syx BUILD.syx [--parts a,b,...] [--limit N] [--json OUT]

The build's own syx is the flash (digikit dspboot through emulib.quickboot, DNFW_DDR_ALIAS=1: the uncached alias
0x4e/0x4f... is the same memory, as on the unit). The stock block driver's read and write are played by Python on a
+Drive dict between dn7_late and the uploader's return (as scripts/emu_lzma7_cache.py), so the boot record's
reads and writes are seen; a write to the reset control register (0xEC090000) stops the run, as a reset would.
A restart that keeps RAM is a fresh boot with the RAM mark the first one left copied in before it starts.

Parts:
  a  normal boot, empty +Drive: the record written once with pending = 1, nothing else of ours written there;
     no reset, no fault, the SHARC got its program, the UI composed.
  b  the record pending (the last boot never became healthy): the late point writes safe_tries 1, leaves the SAFE
     mark and resets. The restart (the mark copied in): the kernel applied SAFE MODE (sm_why 1); right after the
     loader, MAIN OS in RAM is stock 1.12 except exactly the never-restored runs and the overrides O1, O2, O4;
     boot flag bit 0 set; every later CODE chunk's init never ran; nothing pushed to the SHARC; no record write;
     no fault; the UI composed.
     f (in b's SAFE boot): the empty project: the working project's +Drive read (0x400f21e4) never reached, stock's
     empty project built (0x400bb44c), the MRAM flag 0x405ce858 never set (O4), no "Write project MRAM" job
     (0x4002d03a), no call of the stock block write at all.
  n  the marks the stock UI leaves, from reset (the UI loop itself is never reached from reset: the question's keys
     are scripts/emu_safemode_question.py's, on stock's UI snapshot): a NORMAL-ONCE mark (the question's NO) -> a
     normal boot that counts afresh (pending 1, safe_tries 0), the SHARC programmed; a SAFE mark of the STOP entry
     (why 2) -> SAFE MODE applied, reason 2.
  e  hostile: a mark with a bad CRC, a mark of another build, an erased (0xFF) record, a record of another build,
     a cut record: each a normal boot, no reset.
  t  the mark lost across the reset, twice: the third boot is normal (safe_tries spent) and no reset.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys
import zlib

os.environ.setdefault("DNFW_DDR_ALIAS", "1")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, "/mnt/d/01_Code/Z_Personal/digikit-up")

from dnfw import safemode as T                        # noqa: E402
from dnfw.cli.files import read_image                 # noqa: E402
from dnfw.firmware.load import load                   # noqa: E402
from dnfw.mods import platform, safemode as M         # noqa: E402
from emu import symbols                               # noqa: E402
from emulib import quickboot                          # noqa: E402
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE   # noqa: E402
from unicorn.m68k_const import UC_M68K_REG_A2, UC_M68K_REG_A7   # noqa: E402

REPORTER = 0x4011ED4A
PUSHR = 0xEC038034
RCR = 0xEC090000
AFTER_LATE = 0x400CF0F8
AFTER_LOADER = 0x40000546                  # the first instruction after the loader returns (its nop at 0x40000544)
BLK_READ, BLK_WRITE, BLK_READY, BLK_SECTORS = 0x4012C87A, 0x4012CA60, 0x4461C68C, 0x4461C6B0
RESULT = 0x46A20C00
DEVICE = 48_340_992
SECTOR = 0x5FFB00                           # v0.69.2: the record's place (csrc/include/dmove.h DM_SAFE_NEW)
OLD_SECTOR = 0x6E0300                       # until v0.69.1: moved once by normal.c at the first boot
DM, DM_MAGIC, DM_XOR = 0x5FFC00, 0x444E3256, 0x4D4F5645
MOVE_WRITES = (0x5FF102, DM)                # the inserts' mark, the move record (dmove.c, normal.c, lzma7cache.c)
DSP_NEW = (0x5FF200, 0x5FFA01)              # the DSP program's copy (lzma7cache.c, v0.69.2)


def dm_rec(bits):
    return struct.pack(">4I", DM_MAGIC, DM_MAGIC ^ 0xFFFFFFFF, bits, bits ^ DM_XOR).ljust(512, b"\0")


def moved(disk):
    """a +Drive whose SAFE MODE record has moved already (the move record's SAFE bit)"""
    return {**disk, DM: dm_rec(1)}
FLAGS = 0x40287A60
BSS_START = 0x402FD000                      # stock 1.12's BSS (docs/os112-port.md)
MARK, MAGIC_MARK, MAGIC_REC = 0x476F8000, 0x534D4D4B, 0x444E3242
PROJECT_READ_WORKING = 0x400F21E4                            # flags & 3 == 0: the working project read from the +Drive
EMPTY_PROJECT = 0x400BB44C                                   # stock's empty project (flag bit 0, or a failed load)
MRAM_FLAG, MRAM_JOB = 0x405CE858, 0x4002D03A                 # set by 0x400bb4a0 (O4); the "Write project MRAM" job

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def be32(uc, va):
    return struct.unpack(">I", bytes(uc.mem_read(va, 4)))[0]


def crc(b):
    return zlib.crc32(b) & 0xFFFFFFFF


def mark_bytes(kind, build, why=0, bad_crc=False):
    body = struct.pack(">7I", MAGIC_MARK, kind, build, why, 0, 0, 0)
    return body + struct.pack(">I", crc(body) ^ (1 if bad_crc else 0))


def rec_bytes(build, pending, tries, entered=0):
    body = struct.pack(">7I", MAGIC_REC, 1, build, pending, tries, entered, 0)
    return (body + struct.pack(">I", crc(body))).ljust(512, b"\0")


def rec_of(sector):
    if not sector or len(sector) < 32:
        return None
    w = struct.unpack(">8I", sector[:32])
    return {"magic": w[0], "build": w[2], "pending": w[3], "safe_tries": w[4], "entered": w[5],
            "crc_ok": crc(sector[:28]) == w[7]}


class Build:
    def __init__(self, stock_syx, build_syx):
        self.path = build_syx
        self.stock3 = load(read_image(stock_syx)).container.find(3).unpack()
        self.sec3 = load(read_image(build_syx)).container.find(3).unpack()
        self.base, self.chunks = platform.split(self.sec3)
        codes = [platform.area.CodeChunk.unpack(d) for c, d in self.chunks if c == platform.area.CODE]
        self.kernel = next(c for c in codes if c.load == M.SPEC["load"])
        self.later_inits = [c.init for c in codes if c.load != M.SPEC["load"] and c.init]
        _, self.build, off, n, _ = struct.unpack_from(M.HEAD, self.kernel.image, 0)
        self.table = self.kernel.image[off:off + n]
        self.why_va = M.SPEC["symbols"]["sm_why"]
        self.profile = symbols.resolve(self.stock3)        # (the build jumps at panel_diff's entry: resolve on stock)


def boot(b: Build, disk: dict, *, limit: int, mark: bytes | None = None, stop_after_loader: bool = False) -> dict:
    holder = {}
    r = {"fault": None, "pushed": 0, "io": [], "reset": False, "frames": 0, "inits_run": 0, "after_loader": None,
         "read_working": 0, "empty_project": 0, "mram_job": 0, "mram_set": [], "blk_writes": 0}
    played = {"on": False, "saved": {}}

    def pre_start(m):
        uc = m.uc
        if mark is not None:
            m.ensure(MARK)
            uc.mem_write(MARK, mark)

        def on_push(uc, access, addr, size, value, user):
            if (value >> 16) & 0xFFFF == 0x9001:
                r["pushed"] += 1

        def on_rcr(uc, access, addr, size, value, user):
            if addr == RCR and value & 0x80:
                r["reset"] = True
                r["mark_after_reset"] = bytes(uc.mem_read(MARK, 32))
                uc.emu_stop()

        def at_late(uc, address, size, user):
            for va in (BLK_READ, BLK_WRITE, BLK_READY, BLK_SECTORS):
                played["saved"][va] = bytes(uc.mem_read(va, 8 if va in (BLK_READ, BLK_WRITE) else 4))
            stub = bytes.fromhex("2039") + struct.pack(">I", RESULT) + bytes.fromhex("4e75")
            for va in (BLK_READ, BLK_WRITE):
                uc.mem_write(va, stub)
                uc.ctl_remove_cache(va, va + 8)
            uc.mem_write(BLK_READY, struct.pack(">I", 1))
            uc.mem_write(BLK_SECTORS, struct.pack(">I", DEVICE))
            played["on"] = True

        def at_after_late(uc, address, size, user):
            if played["on"]:
                for va, v in played["saved"].items():
                    uc.mem_write(va, v)
                    uc.ctl_remove_cache(va, va + len(v))
                played["on"] = False

        def driver(write):
            def hook(uc, address, size, user):
                if not played["on"]:
                    return
                sp = uc.reg_read(UC_M68K_REG_A7)
                sector, nbytes, buf = (be32(uc, sp + 4 * k) for k in (1, 2, 3))
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

        def at_reporter(uc, address, size, user):
            r["fault"] = bytes(uc.mem_read(uc.reg_read(UC_M68K_REG_A2), 16)).hex()
            uc.emu_stop()

        def at_frame(uc, address, size, user):
            r["frames"] += 1

        def count(key):
            def h(uc, address, size, user):
                r[key] += 1
            return h

        def at_mram(uc, access, addr, size, value, user):
            if value:
                r["mram_set"].append(value)

        def at_init(uc, address, size, user):
            r["inits_run"] += 1

        def at_after_loader(uc, address, size, user):
            if r["after_loader"] is None:
                r["after_loader"] = bytes(uc.mem_read(T.BASE, T.STOCK_LEN))
                r["flags"] = be32(uc, FLAGS)
                r["why"] = be32(uc, b.why_va)
                r["applied"] = be32(uc, M.SPEC["symbols"]["sm_live"] + 4)
                r["mark_after_init"] = bytes(uc.mem_read(MARK, 32))
                r["reason"] = be32(uc, M.SPEC["symbols"]["sm_live"] + 8)
                if stop_after_loader:
                    uc.emu_stop()

        lay = M.SPEC["symbols"]
        uc.hook_add(UC_HOOK_MEM_WRITE, on_push, begin=PUSHR, end=PUSHR + 3)
        uc.hook_add(UC_HOOK_MEM_WRITE, on_rcr, begin=RCR, end=RCR)
        dn7 = _dn7_late(b)
        uc.hook_add(UC_HOOK_CODE, at_late, begin=dn7, end=dn7)
        uc.hook_add(UC_HOOK_CODE, at_after_late, begin=AFTER_LATE, end=AFTER_LATE)
        uc.hook_add(UC_HOOK_CODE, driver(False), begin=BLK_READ, end=BLK_READ)
        uc.hook_add(UC_HOOK_CODE, driver(True), begin=BLK_WRITE, end=BLK_WRITE)
        uc.hook_add(UC_HOOK_CODE, at_reporter, begin=REPORTER, end=REPORTER)
        uc.hook_add(UC_HOOK_CODE, at_frame, begin=b.profile.panel_diff, end=b.profile.panel_diff)
        uc.hook_add(UC_HOOK_CODE, at_after_loader, begin=AFTER_LOADER, end=AFTER_LOADER)
        for va in b.later_inits:
            uc.hook_add(UC_HOOK_CODE, at_init, begin=va, end=va)
        uc.hook_add(UC_HOOK_CODE, count("read_working"), begin=PROJECT_READ_WORKING, end=PROJECT_READ_WORKING)
        uc.hook_add(UC_HOOK_CODE, count("empty_project"), begin=EMPTY_PROJECT, end=EMPTY_PROJECT)
        uc.hook_add(UC_HOOK_CODE, count("mram_job"), begin=MRAM_JOB, end=MRAM_JOB)
        uc.hook_add(UC_HOOK_CODE, count("blk_writes"), begin=BLK_WRITE, end=BLK_WRITE)
        uc.hook_add(UC_HOOK_MEM_WRITE, at_mram, begin=MRAM_FLAG, end=MRAM_FLAG + 3)
        del lay

    m, st, stop = quickboot.run(str(b.path), b.sec3, limit=limit, machine_out=holder, pre_start=pre_start)
    r["stop"] = repr(stop)
    return r


def _dn7_late(b: Build) -> int:
    """dn7_late's address: the jsr at 0x400cf0f2 in the build"""
    at = 0x400CF0F2 - T.BASE
    op = b.sec3[at:at + 6]
    if op[:2] != b"\x4e\xb9":
        raise SystemExit("0x400cf0f2 is not the build's jsr dn7_late")
    return struct.unpack(">I", op[2:])[0]


def part_a(b, limit):
    disk = {}
    r = boot(b, disk, limit=limit)
    rec = rec_of(disk.get(SECTOR))
    writes = [x for x in r["io"] if x[0] == "W"]
    check("a: no fault, no reset", r["fault"] is None and not r["reset"], f"fault {r['fault']}, stop {r['stop']}")
    check("a: the record written once, pending 1, this build", rec is not None and rec["pending"] == 1
          and rec["build"] == b.build and rec["crc_ok"] and rec["safe_tries"] == 0
          and [w for w in writes if w[1] == SECTOR] == [("W", SECTOR, 512)], f"{rec}, writes {writes[:4]}")
    check("a: our other +Drive writes are DN7C's and the moves' marks only (v0.69.2)",
          all(w[1] == SECTOR or DSP_NEW[0] <= w[1] < DSP_NEW[1] or w[1] in MOVE_WRITES for w in writes)
          and not [w for w in writes if w[1] == OLD_SECTOR], f"{len(writes)} writes")
    m = disk.get(DM, b"")
    check("a: the move record's SAFE and DSP bits set at the first boot (nothing at the old places to copy)",
          len(m) >= 16 and struct.unpack(">4I", m[:16])[0] == DM_MAGIC and struct.unpack(">4I", m[:16])[2] & 3 == 3,
          m[:16].hex())
    check("a: the SHARC got its program, the UI composed", r["pushed"] > 500_000 and r["frames"] > 0,
          f"{r['pushed']:,} B pushed, {r['frames']} frame(s)")
    check("a: SAFE MODE not applied", r.get("applied") == 0 and r.get("why") == 0,
          f"applied {r.get('applied')}, why {r.get('why')}")
    return r


def part_b(b, limit):
    disk = moved({SECTOR: rec_bytes(b.build, 1, 0)})
    r1 = boot(b, disk, limit=limit)
    rec = rec_of(disk.get(SECTOR))
    mk = r1.get("mark_after_reset", b"")
    check("b: pending -> safe_tries 1 written, the SAFE mark left, a reset", r1["reset"] and rec and rec["safe_tries"] == 1
          and rec["pending"] == 1 and mk[:8] == struct.pack(">II", MAGIC_MARK, 1) and r1["pushed"] == 0,
          f"reset {r1['reset']}, {rec}, mark {mk[:12].hex()}, pushed {r1['pushed']}")
    if not r1["reset"]:
        return
    before = dict(disk)
    r = boot(b, disk, limit=limit, mark=mk)
    ram = r["after_loader"] or b""
    stock = b.stock3
    allowed = {va - T.BASE + k for va, _, _ in T.OVERRIDES for k in range(6)}
    allowed |= {FLAGS - T.BASE + k for k in range(4)}  # the boot flags: the bootstrap's word, bit 0 ORed in
    upto = BSS_START - T.BASE                          # (the BSS clear has run by then: stock's image past it is zero)
    diff = [i for i in range(min(len(ram), upto)) if ram[i] != stock[i]]
    odd = [i for i in diff if not T._never(i, 1) and i not in allowed]
    check("b: the kernel applied SAFE MODE", r.get("why") == 1 and r.get("applied") == 1,
          f"why {r.get('why')}, applied {r.get('applied')}")
    check("b: the mark wiped by the init", r.get("mark_after_init") == bytes(32))
    check("b: after the loader, MAIN OS = stock 1.12 + the never-restored runs + O1, O2, O4 + flag bit 0",
          bool(ram) and not odd, f"{len(diff)} B differ, {len(odd)} outside them"
          + (f", first 0x{T.BASE + odd[0]:08x}" if odd else ""))
    check("b: boot flag bit 0 (EMPTY RESET)", (r.get("flags") or 0) & 1 == 1, f"0x{r.get('flags') or 0:08x}")
    check("b: none of our other inits ran", r["inits_run"] == 0, f"{r['inits_run']} of {len(b.later_inits)}")
    check("b: nothing pushed to the SHARC", r["pushed"] == 0, f"{r['pushed']}")
    check("b: SAFE MODE wrote nothing to the +Drive", disk == before and not [x for x in r["io"] if x[0] == "W"])
    check("b: no fault, no reset, the UI composed", r["fault"] is None and not r["reset"] and r["frames"] > 0,
          f"fault {r['fault']}, frames {r['frames']}, stop {r['stop']}")
    check("f: the working project never read from the +Drive; stock's empty project built",
          r["read_working"] == 0 and r["empty_project"] > 0, f"read {r['read_working']}, empty {r['empty_project']}")
    check("f: no MRAM flag set (O4), no 'Write project MRAM' job, no block write at all",
          not r["mram_set"] and r["mram_job"] == 0 and r["blk_writes"] == 0,
          f"flag writes {r['mram_set']}, job {r['mram_job']}, block writes {r['blk_writes']}")


def part_n(b, limit):
    """the two marks the stock UI leaves (question.c's NO, normal.c's STOP entry), from reset; the keys themselves are
    scripts/emu_safemode_question.py's (a from-reset run never reaches the UI loop)"""
    disk = moved({SECTOR: rec_bytes(b.build, 1, 1)})
    r = boot(b, disk, limit=limit, mark=mark_bytes(2, b.build, why=3))
    rec = rec_of(disk.get(SECTOR))
    check("n: a NORMAL-ONCE mark (NO): a normal boot that counts afresh (pending 1, safe_tries 0), the SHARC programmed",
          r["fault"] is None and not r["reset"] and r.get("applied") == 0 and rec and rec["pending"] == 1
          and rec["safe_tries"] == 0 and r["pushed"] > 500_000,
          f"fault {r['fault']}, reset {r['reset']}, applied {r.get('applied')}, {rec}, pushed {r['pushed']:,}")
    r2 = boot(b, {}, limit=limit, mark=mark_bytes(1, b.build, why=2), stop_after_loader=True)
    check("n: a SAFE mark of the STOP entry (why 2): SAFE MODE applied, reason 2 kept for the question",
          r2.get("applied") == 1 and r2.get("reason") == 2,
          f"applied {r2.get('applied')}, reason {r2.get('reason')}, why {r2.get('why')}")


def part_e(b, limit):
    cases = [("a mark with a bad CRC", {}, mark_bytes(1, b.build, bad_crc=True)),
             ("a mark of another build", {}, mark_bytes(1, b.build ^ 1)),
             ("an erased record (0xFF)", moved({SECTOR: b"\xff" * 512}), None),
             ("a record of another build, pending", moved({SECTOR: rec_bytes(b.build ^ 1, 1, 0)}), None),
             ("a cut record (CRC wrong)", moved({SECTOR: rec_bytes(b.build, 1, 0)[:20] + bytes(492)}), None)]
    for name, disk, mark in cases:
        r = boot(b, disk, limit=limit, mark=mark)
        rec = rec_of(disk.get(SECTOR))
        check(f"e: {name}: a normal boot", r["fault"] is None and not r["reset"] and r.get("applied") == 0
              and rec and rec["pending"] == 1 and rec["safe_tries"] == 0 and rec["build"] == b.build,
              f"reset {r['reset']}, applied {r.get('applied')}, {rec}")


def part_t(b, limit):
    disk = moved({SECTOR: rec_bytes(b.build, 1, 0)})
    resets = []
    for k in range(3):
        r = boot(b, disk, limit=limit)                 # the mark is never carried: lost across each reset
        resets.append(r["reset"])
        if r["fault"]:
            break
    rec = rec_of(disk.get(SECTOR))
    check("t: the mark lost twice: two resets, then a normal boot", resets == [True, True, False]
          and rec and rec["safe_tries"] == 2 and rec["pending"] == 1, f"resets {resets}, {rec}")


def part_m(b, limit):
    """v0.69.2: a +Drive as v0.69.1 left it (the record at 0x6E0300, no move record), the last boot never healthy
    (pending): the first boot copies the record to 0x5FFB00, sets the move record's SAFE bit, never writes the old
    sector, and decides on the copy exactly as part b does on a moved record (safe_tries 1, the SAFE mark, a reset)"""
    old = rec_bytes(b.build, 1, 0)
    disk = {OLD_SECTOR: old}
    r = boot(b, disk, limit=limit)
    rec = rec_of(disk.get(SECTOR))
    m = disk.get(DM, b"")
    writes = [x for x in r["io"] if x[0] == "W"]
    check("m: the old record moved: copied to 0x5FFB00, the move record's SAFE bit set, 0x6E0300 never written",
          disk.get(OLD_SECTOR) == old and not [w for w in writes if w[1] == OLD_SECTOR]
          and len(m) >= 16 and struct.unpack(">4I", m[:16])[0] == DM_MAGIC and struct.unpack(">4I", m[:16])[2] & 1,
          f"writes {writes[:6]}, move record {m[:16].hex()}")
    mk = r.get("mark_after_reset", b"")
    check("m: ... and the boot decided on it as on a moved one: safe_tries 1 written, the SAFE mark left, a reset",
          r["reset"] and rec and rec["safe_tries"] == 1 and rec["pending"] == 1
          and mk[:8] == struct.pack(">II", MAGIC_MARK, 1), f"reset {r['reset']}, {rec}, mark {mk[:12].hex()}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stock", type=pathlib.Path)
    ap.add_argument("build", type=pathlib.Path)
    ap.add_argument("--parts", default="a,b")
    ap.add_argument("--limit", type=int, default=800_000_000)   # (a first boot decodes section 7: the UI after ~700 M)
    ap.add_argument("--json", type=pathlib.Path)
    a = ap.parse_args()
    b = Build(a.stock, a.build)
    print(f"build id 0x{b.build:08x}, table {len(b.table):,} B, later inits {len(b.later_inits)}", flush=True)
    for p in a.parts.split(","):
        {"a": part_a, "b": part_b, "e": part_e, "n": part_n, "t": part_t, "m": part_m}[p](b, a.limit)
    print(f"{'PASS' if not failures else 'FAIL'}: {len(failures)} failure(s)")
    if a.json:
        a.json.write_text(json.dumps({"failures": failures}, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
