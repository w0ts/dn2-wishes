"""Write csrc/waverider/sharc/ampsw.asm, AMP ON/OFF's two DSP hooks (dnfw.waverider.ampsw, docs/live-select.md).

    python scripts/gen_ampsw_asm.py [--no-resolve]

The text is `dnfw.waverider.ampsw.asm_text()`; every branch target is filled in from selas's own layout at the
object's load address (scripts/sharc_resolve_jumps.py), unless --no-resolve. Assemble it with
`scripts/gen_waverider_sharc.py --assemble`.
"""

from __future__ import annotations

import argparse
import importlib
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "csrc" / "waverider" / "sharc" / "ampsw.asm"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-resolve", action="store_true")
    a = ap.parse_args(argv)
    AS = importlib.import_module("dnfw.waverider.ampsw")
    text = AS.asm_text()
    if not a.no_resolve:
        R = importlib.import_module("sharc_resolve_jumps")
        with tempfile.TemporaryDirectory() as tmp:
            text, be, offs = R.resolve(text, AS.CODE_SW, pathlib.Path(tmp))
        room = AS.CODE_SPAN - 128
        if len(be) > room:
            raise SystemExit(f"ampsw.asm is {len(be)} bytes: {room} fit in its L2 span with 128 bytes of NOPs")
        print(f"resolved at sw {AS.CODE_SW:#x}: {len(offs)} instructions, {len(be)} of {room} bytes")
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
