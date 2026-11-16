"""Boot a 1.12 build from reset in the ColdFire emulator and check the SHARC upload (docs/lzma7.md).

    bench_ns112.sh TREE python scripts/emu_lzma7_boot.py BUILD.syx [LIMIT] [--json OUT]

The build's own syx is the flash (digikit emu.dspboot, the route that boots 1.12 builds). Recorded:
every byte MAIN OS's uploader (0x400cf4b0) pushes to the SHARC through DSPI PUSHR (0xec038034),
the depack's answer (d0 after the call at 0x400cf73a), and the instruction count at the uploader's
entry, after its depack, at its last push and at its return. PASS when the pushed bytes are 0x03
followed by the build's section 7 exactly as dnfw unpacks it, and no fault was reported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, "/mnt/d/01_Code/Z_Personal/digikit-up")

from dnfw.cli.files import read_image                    # noqa: E402
from dnfw.firmware.load import load                      # noqa: E402
from emu import dspboot                                  # noqa: E402
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE      # noqa: E402
from unicorn.m68k_const import UC_M68K_REG_A2, UC_M68K_REG_D0   # noqa: E402

UPLOADER, AFTER_DEPACK, UPLOADER_RET = 0x400CF4B0, 0x400CF740, 0x400CF7EA
PUSHR = 0xEC038034
REPORTER = 0x4011ED4A                                     # the fault reporter (boot112own.py)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("build", type=pathlib.Path)
    ap.add_argument("limit", type=int, nargs="?", default=800_000_000)
    ap.add_argument("--json", type=pathlib.Path)
    a = ap.parse_args()
    fw = load(read_image(a.build))
    sec3, s7 = fw.container.find(3), fw.container.find(7)
    image = sec3.unpack()
    content = s7.unpack()                                 # None: a section 7 dnfw refuses (the fail-safe test)
    want = b"\x03" + content if content is not None else None
    stored_kind = "lzma7" if s7.stored[8:12] == b"DN7Z" else "aplib"

    holder, pushed, marks, state = {}, bytearray(), {}, {"fault": None, "depack": None}

    def pre_start(m):
        st = holder["st"]

        def on_push(uc, access, addr, size, value, user):
            if (value >> 16) & 0xFFFF == 0x9001:          # CONT | CTAS | PCS0: a data frame
                pushed.append(value & 0xFF)
                marks.setdefault("first_push", st["n"])
                marks["last_push"] = st["n"]

        def at(name):
            def hook(uc, address, size, user):
                marks.setdefault(name, st["n"])
                if name == "after_depack":
                    state["depack"] = uc.reg_read(UC_M68K_REG_D0)
            return hook

        def at_reporter(uc, address, size, user):
            state["fault"] = (st["n"], bytes(uc.mem_read(uc.reg_read(UC_M68K_REG_A2), 16)).hex())
            uc.emu_stop()

        m.uc.hook_add(UC_HOOK_MEM_WRITE, on_push, begin=PUSHR, end=PUSHR + 3)
        m.uc.hook_add(UC_HOOK_CODE, at("uploader"), begin=UPLOADER, end=UPLOADER)
        m.uc.hook_add(UC_HOOK_CODE, at("after_depack"), begin=AFTER_DEPACK, end=AFTER_DEPACK)
        m.uc.hook_add(UC_HOOK_CODE, at("uploader_ret"), begin=UPLOADER_RET, end=UPLOADER_RET)
        m.uc.hook_add(UC_HOOK_CODE, at_reporter, begin=REPORTER, end=REPORTER)

    m, st, stop = dspboot.run(str(a.build), image, limit=a.limit, machine_out=holder, pre_start=pre_start)
    exact = want is not None and bytes(pushed) == want
    out = {
        "build": a.build.name, "build_sha256": hashlib.sha256(a.build.read_bytes()).hexdigest(),
        "section7_stored": stored_kind, "section7_stored_bytes": len(s7.stored),
        "instructions_run": st["n"], "fault": state["fault"],
        "depack_answer": state["depack"], "pushed_bytes": len(pushed), "expected_bytes": len(want) if want else None,
        "pushed_sha256": hashlib.sha256(bytes(pushed)).hexdigest(),
        "pushed_is_section7_exactly": exact, "marks": marks,
        "depack_instructions": (marks["after_depack"] - marks["uploader"])
        if "after_depack" in marks and "uploader" in marks else None,
    }
    if not exact and pushed and want:
        diff = next((i for i, (x, y) in enumerate(zip(pushed, want)) if x != y), min(len(pushed), len(want)))
        out["first_difference"] = diff
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1))
    if want is None:
        # the fail-safe: the uploader must refuse (no byte pushed) and the boot go on without a fault
        ok = not pushed and state["depack"] == 0x100000 and state["fault"] is None
        print("PASS" if ok else "FAIL", "-", "refused, nothing pushed, no fault" if ok else "not refused cleanly")
        return 0 if ok else 1
    ok = exact and state["fault"] is None
    print("PASS" if ok else "FAIL", "-", "the SHARC got section 7 exactly" if exact else "pushed bytes differ")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
