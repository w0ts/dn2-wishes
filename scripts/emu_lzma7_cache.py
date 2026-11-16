"""The DSP program decoded once and kept on the +Drive (csrc/waverider/lzma7cache.c, docs/lzma7.md "The cache"):
boots from reset in the ColdFire emulator, one +Drive carried from boot to boot.

    bench_ns112.sh TREE python scripts/emu_lzma7_cache.py BUILD.syx [--limit N] [--tail-limit N] [--json OUT]

The build's own syx is the flash (digikit emu.dspboot, as scripts/emu_lzma7_boot.py). The emulator's eSDHC model
brings the stock driver up; what it reports at the new upload point is recorded. From there to the upload's return
the stock block driver's read and write entries (0x4012c87a, 0x4012ca60) are played by Python, as in
scripts/emu_erase.py (the entry becomes `move.l RESULT,%d0 ; rts`, a hook does the work first), on a +Drive of the
owner's size; after the return they are stock's again. Boots, each from a fresh machine:

- **first**: an empty +Drive: decoded (dn7_status 2), the copy written (dn7c_state 3), its header last;
- **second**: the same +Drive: read from the copy (8, 1), not one write, no decode;
- **corrupt**: one byte of the copy's program flipped: decoded (why 5), written again, the +Drive as after first;
- **newid**: the copy's id changed (another build's copy, its header check redone): decoded (why 2), refreshed;
- **writefail**: an empty +Drive whose every write fails: decoded (state 4), and the boot goes on to --tail-limit.

Every boot: the bytes pushed to the SHARC are 0x03 + section 7 exactly, no fault, the uploader entered after the
eMMC driver's set-up (0x4012be52) and only from dn7_late. The instruction counts from the uploader's entry to its
return are the decode's and the copy's cost (the copy's read time on the unit is the eMMC's, not measured here).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, "/mnt/d/01_Code/Z_Personal/digikit-up")

from dnfw.cli.files import read_image                    # noqa: E402
from dnfw.firmware.load import load                      # noqa: E402
from emu import dspboot                                  # noqa: E402
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE      # noqa: E402
from unicorn.m68k_const import UC_M68K_REG_A2, UC_M68K_REG_A7, UC_M68K_REG_D0   # noqa: E402

UPLOADER, AFTER_DEPACK, EARLY, LATE, AFTER_LATE = 0x400CF4B0, 0x400CF740, 0x400CF086, 0x400CF0F2, 0x400CF0F8
EMMC_SETUP = 0x4012BE52
BLK_READ, BLK_WRITE, BLK_READY, BLK_SECTORS = 0x4012C87A, 0x4012CA60, 0x4461C68C, 0x4461C6B0
PUSHR = 0xEC038034
REPORTER = 0x4011ED4A                                     # the fault reporter (boot112own.py)
RESULT = 0x46A20C00                                       # what a played driver entry returns (emu_erase.py's)
DEVICE = 48_340_992                                       # the owner's Kingston, reconfigured (emu_erase.py)
C_HDR = 0x6E8000

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def be32(uc, va: int) -> int:
    return struct.unpack(">I", bytes(uc.mem_read(va, 4)))[0]


def boot(build: pathlib.Path, image: bytes, lay: dict, disk: dict, *, limit: int, write_fail: bool = False) -> dict:
    holder, pushed, marks, io = {}, bytearray(), {}, []
    state = {"fault": None, "depack": None, "played": False, "saved": {}, "uploads": 0, "emulated": None}

    def pre_start(m):
        st, uc = holder["st"], m.uc

        def mark(name):
            def hook(uc, address, size, user):
                marks.setdefault(name, st["n"])
            return hook

        def on_push(uc, access, addr, size, value, user):
            if (value >> 16) & 0xFFFF == 0x9001:          # CONT | CTAS | PCS0: a data frame
                pushed.append(value & 0xFF)
                marks["last_push"] = st["n"]

        def at_uploader(uc, address, size, user):
            state["uploads"] += 1
            marks.setdefault("uploader", st["n"])

        def at_depack(uc, address, size, user):
            marks.setdefault("after_depack", st["n"])
            state["depack"] = uc.reg_read(UC_M68K_REG_D0)

        def at_late(uc, address, size, user):
            marks.setdefault("late", st["n"])
            state["emulated"] = {"ready": be32(uc, BLK_READY), "sectors": be32(uc, BLK_SECTORS)}
            for va in (BLK_READ, BLK_WRITE, BLK_READY, BLK_SECTORS):
                state["saved"][va] = bytes(uc.mem_read(va, 8 if va in (BLK_READ, BLK_WRITE) else 4))
            stub = bytes.fromhex("2039") + struct.pack(">I", RESULT) + bytes.fromhex("4e75")
            for va in (BLK_READ, BLK_WRITE):
                uc.mem_write(va, stub)
                uc.ctl_remove_cache(va, va + 8)
            uc.mem_write(BLK_READY, struct.pack(">I", 1))
            uc.mem_write(BLK_SECTORS, struct.pack(">I", DEVICE))
            state["played"] = True

        def at_after_late(uc, address, size, user):
            marks.setdefault("uploader_ret", st["n"])
            if state["played"]:
                for va, b in state["saved"].items():
                    uc.mem_write(va, b)
                    uc.ctl_remove_cache(va, va + len(b))
                state["played"] = False

        def driver(write):
            def hook(uc, address, size, user):
                if not state["played"]:
                    return
                sp = uc.reg_read(UC_M68K_REG_A7)
                sector, nbytes, buf = (be32(uc, sp + 4 * k) for k in (1, 2, 3))
                ok = 0 < nbytes <= 0x10000 and sector >= C_HDR and sector + (nbytes + 511) // 512 <= C_HDR + 1 + 2048
                rc = 0
                if not ok or (write and write_fail):
                    rc = -1
                elif write:
                    data = bytes(uc.mem_read(buf, nbytes)) + bytes(-nbytes % 512)
                    for k in range(len(data) // 512):
                        disk[sector + k] = data[512 * k:512 * k + 512]
                else:
                    data = b"".join(disk.get(sector + k, bytes(512)) for k in range((nbytes + 511) // 512))
                    uc.mem_write(buf, data[:nbytes])
                io.append(("W" if write else "R", sector, nbytes, rc, ok))
                uc.mem_write(RESULT, struct.pack(">i", rc))
            return hook

        def at_reporter(uc, address, size, user):
            state["fault"] = (st["n"], bytes(uc.mem_read(uc.reg_read(UC_M68K_REG_A2), 16)).hex())
            uc.emu_stop()

        uc.hook_add(UC_HOOK_MEM_WRITE, on_push, begin=PUSHR, end=PUSHR + 3)
        uc.hook_add(UC_HOOK_CODE, mark("early_site"), begin=EARLY, end=EARLY)
        uc.hook_add(UC_HOOK_CODE, mark("emmc_setup"), begin=EMMC_SETUP, end=EMMC_SETUP)
        uc.hook_add(UC_HOOK_CODE, mark("dn7_late"), begin=lay["dn7_late"], end=lay["dn7_late"])
        uc.hook_add(UC_HOOK_CODE, at_uploader, begin=UPLOADER, end=UPLOADER)
        uc.hook_add(UC_HOOK_CODE, at_depack, begin=AFTER_DEPACK, end=AFTER_DEPACK)
        uc.hook_add(UC_HOOK_CODE, at_late, begin=lay["dn7_late"], end=lay["dn7_late"])
        uc.hook_add(UC_HOOK_CODE, at_after_late, begin=AFTER_LATE, end=AFTER_LATE)
        uc.hook_add(UC_HOOK_CODE, driver(False), begin=BLK_READ, end=BLK_READ)
        uc.hook_add(UC_HOOK_CODE, driver(True), begin=BLK_WRITE, end=BLK_WRITE)
        uc.hook_add(UC_HOOK_CODE, at_reporter, begin=REPORTER, end=REPORTER)

    m, st, stop = dspboot.run(str(build), image, limit=limit, machine_out=holder, pre_start=pre_start)
    uc = m.uc
    words = {n: be32(uc, lay[n]) for n in ("dn7_status", "dn7_length", "dn7c_state", "dn7c_why")}
    return {"pushed": bytes(pushed), "marks": marks, "io": io, "fault": state["fault"], "depack": state["depack"],
            "uploads": state["uploads"], "emulated_driver_at_late": state["emulated"], "instructions_run": st["n"],
            "stop": str(stop), **words,
            "upload_instructions": marks["uploader_ret"] - marks["uploader"]
            if "uploader_ret" in marks and "uploader" in marks else None}


def common(name: str, r: dict, want: bytes) -> None:
    mk = r["marks"]
    check(f"{name}: the SHARC got 0x03 + section 7 exactly", r["pushed"] == want,
          f"{len(r['pushed'])} of {len(want)} B")
    check(f"{name}: no fault", r["fault"] is None, str(r["fault"]))
    check(f"{name}: one upload, entered after the eMMC's set-up, from dn7_late",
          r["uploads"] == 1 and mk.get("emmc_setup", 1 << 62) < mk.get("dn7_late", -1) <= mk.get("uploader", -1)
          and mk.get("early_site", 1 << 62) < mk.get("emmc_setup", -1),
          f"early {mk.get('early_site')}, eMMC set-up {mk.get('emmc_setup')}, late {mk.get('dn7_late')}, "
          f"uploader {mk.get('uploader')}")
    check(f"{name}: every played driver call inside the copy's sectors", all(x[4] for x in r["io"]),
          f"{len(r['io'])} calls")


def summary(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "pushed"} | {"pushed_sha256": hashlib.sha256(r["pushed"]).hexdigest(),
                                                           "pushed_bytes": len(r["pushed"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("build", type=pathlib.Path)
    ap.add_argument("--limit", type=int, default=420_000_000)
    ap.add_argument("--tail-limit", type=int, default=800_000_000)
    ap.add_argument("--layout", default=str(ROOT / "src/dnfw/mods/waverider_code.json"))
    ap.add_argument("--only", default="first,second,corrupt,newid,writefail")
    ap.add_argument("--json", type=pathlib.Path)
    a = ap.parse_args()
    lay = json.loads(pathlib.Path(a.layout).read_text())["layout"]
    fw = load(read_image(a.build))
    image, s7 = fw.container.find(3).unpack(), fw.container.find(7)
    content = s7.unpack()
    want = b"\x03" + content
    n = len(content)
    data_sectors = -(-n // 512)
    only = a.only.split(",")
    out = {"build": a.build.name, "build_sha256": hashlib.sha256(a.build.read_bytes()).hexdigest(),
           "program_bytes": n, "boots": {}}

    disk: dict[int, bytes] = {}
    print("first: an empty +Drive", flush=True)
    r = boot(a.build, image, lay, disk, limit=a.limit)
    out["boots"]["first"] = summary(r)
    common("first", r, want)
    writes = [x for x in r["io"] if x[0] == "W"]
    check("first: decoded, the copy written", (r["dn7_status"], r["dn7c_state"]) == (2, 3),
          f"status {r['dn7_status']}, state {r['dn7c_state']}")
    check("first: header cleared first, program in 64 KB calls, header last",
          len(writes) == 2 + -(-data_sectors * 512 // 0x10000) and writes[0][1] == C_HDR and writes[-1][1] == C_HDR
          and all(w[1] != C_HDR for w in writes[1:-1]), f"{len(writes)} writes")
    hdr = disk.get(C_HDR, bytes(512))
    check("first: the copy is the program byte for byte, its header valid",
          b"".join(disk[C_HDR + 1 + k] for k in range(data_sectors))[:n] == content and hdr[:4] == b"DN7C"
          and struct.unpack(">III", hdr[4:16]) == (1, n, zlib.crc32(content)) and hdr[16:40] == s7.stored[:24]
          and struct.unpack(">I", hdr[40:44])[0] == zlib.crc32(hdr[:40]))
    after_first = dict(disk)

    if "second" in only:
        print("second: the same +Drive", flush=True)
        r = boot(a.build, image, lay, disk, limit=a.limit)
        out["boots"]["second"] = summary(r)
        common("second", r, want)
        check("second: read from the copy, not one write, no decode",
              (r["dn7_status"], r["dn7c_state"]) == (8, 1) and not [x for x in r["io"] if x[0] == "W"],
              f"status {r['dn7_status']}, state {r['dn7c_state']}")
        dec, cop = out["boots"]["first"]["upload_instructions"], r["upload_instructions"]
        out["upload_instructions"] = {"decode_and_write": dec, "copy": cop}
        print(f"  the upload: {dec:,} instructions with the decode (and the copy's write), {cop:,} from the copy",
              flush=True)

    if "corrupt" in only:
        print("corrupt: one byte of the copy flipped", flush=True)
        disk = dict(after_first)
        sec = C_HDR + 1 + data_sectors // 2
        disk[sec] = bytes([disk[sec][0] ^ 0x40]) + disk[sec][1:]
        r = boot(a.build, image, lay, disk, limit=a.limit)
        out["boots"]["corrupt"] = summary(r)
        common("corrupt", r, want)
        check("corrupt: decoded (the program's CRC), written again",
              (r["dn7_status"], r["dn7c_state"], r["dn7c_why"]) == (2, 3, 5) and disk == after_first,
              f"status {r['dn7_status']}, state {r['dn7c_state']}, why {r['dn7c_why']}")

    if "newid" in only:
        print("newid: another build's copy", flush=True)
        disk = dict(after_first)
        h = bytearray(disk[C_HDR])
        h[16 + 7] ^= 1                                    # another byte sum: another stored section 7
        h[40:44] = struct.pack(">I", zlib.crc32(bytes(h[:40])))
        disk[C_HDR] = bytes(h)
        r = boot(a.build, image, lay, disk, limit=a.limit)
        out["boots"]["newid"] = summary(r)
        common("newid", r, want)
        check("newid: decoded (the id), refreshed",
              (r["dn7_status"], r["dn7c_state"], r["dn7c_why"]) == (2, 3, 2) and disk == after_first,
              f"status {r['dn7_status']}, state {r['dn7c_state']}, why {r['dn7c_why']}")

    if "writefail" in only:
        print("writefail: every write fails, the boot runs on", flush=True)
        disk = {}
        r = boot(a.build, image, lay, disk, limit=a.tail_limit, write_fail=True)
        out["boots"]["writefail"] = summary(r)
        common("writefail", r, want)
        check("writefail: decoded, the write failure noted, nothing on the +Drive",
              (r["dn7_status"], r["dn7c_state"]) == (2, 4) and not disk,
              f"status {r['dn7_status']}, state {r['dn7c_state']}")
        check("writefail: the boot ran on to the limit", r["instructions_run"] >= a.tail_limit - 1_000_000,
              f"{r['instructions_run']:,} instructions, stop {r['stop']}")

    out["failures"] = failures
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, default=str))
    print("PASS" if not failures else f"FAIL: {len(failures)}: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
