"""Compile SAFE MODE's kernel chunk ahead of time, for `dnfw mods` (docs/safe-mode.md).

    python scripts/gen_safemode_code.py [--check]

csrc/safemode/kernel.c and question.c (the SAFE MODE question, O2), linked at SM_LOAD (dnfw.waverider.pages), into
src/dnfw/mods/safemode_code.json: the image (its head first, no BSS: the build appends the unpatch table where a BSS
would be), the init entry and the symbols the build and the gate check. --check writes nothing: exit 0 only if the
committed file is what the sources compile to now (the gate's code-fresh step runs it).
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dnfw.patch import cbuild                     # noqa: E402

SRC = ROOT / "csrc" / "safemode"
OUT = ROOT / "src/dnfw/mods/safemode_code.json"
SM_LOAD = 0x476F8100                              # dnfw.waverider.pages.SM_LOAD
ENTRIES = ["sm_init", "sm_refuse7", "sm_isdirty", "sm_head"]


def main() -> int:
    try:
        from dnfw.waverider import pages          # the farm's tree: checked against the RAM map
        assert pages.SM_LOAD == SM_LOAD, "pages.SM_LOAD moved: update SM_LOAD here and in csrc/safemode/sm.h"
    except (ImportError, FileNotFoundError, OSError):
        pass
    code = cbuild.build([SRC / "kernel.c", SRC / "question.c"], base=SM_LOAD, entries=ENTRIES, include=[SRC])
    if code.bss:
        raise SystemExit(f"the kernel has {code.bss} B of BSS: put every variable in .data")
    if code["sm_head"] != SM_LOAD:
        raise SystemExit(f"sm_head is at 0x{code['sm_head']:08x}, not the chunk's first byte")
    spec = {"os": "Digitone II 1.12", "load": SM_LOAD, "init": code["sm_init"], "bss": code.bss,
            "symbols": {k: code[k] for k in ("sm_init", "sm_refuse7", "sm_isdirty", "sm_head", "sm_why", "sm_live", "sm_asked")},
            "const_end": code["__data_start"],    # head, code and constants: the RAM guard's constant span
            "code": code.image.hex()}
    text = (json.dumps(spec, indent=1) + "\n").encode()
    if "--check" in sys.argv[1:]:
        same = OUT.exists() and OUT.read_bytes() == text
        print(f"{OUT.relative_to(ROOT)} {'matches' if same else 'is STALE against'} csrc/safemode")
        return 0 if same else 1
    OUT.write_bytes(text)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(code.image):,} B at 0x{SM_LOAD:08x}, init 0x{code['sm_init']:08x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
