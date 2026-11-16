"""Write FDN8's SHARC source, csrc/waverider/sharc/fdn8.asm (docs/fdn8.md).

    python scripts/gen_fdn8_asm.py [--no-resolve]

The program is `dnfw.fdn8.program.program`: the same calls that, run in Python, are the
model held bit for bit to dnfw.fdn8.ref (test/test_fdn8.py), and that the SHARC runner holds
the assembled code to (scripts/sharc_waverider_m5.py, step fdn8). This writes its assembly
text, then fills in every branch target with selas's own layout at its L2 load address
(scripts/sharc_resolve_jumps.py), unless --no-resolve. Assemble it with
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

P = importlib.import_module("dnfw.fdn8.program")
dsp = importlib.import_module("dnfw.waverider.dsp")

OUT = ROOT / "csrc" / "waverider" / "sharc" / "fdn8.asm"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-resolve", action="store_true")
    a = ap.parse_args(argv)
    text = P.program()
    if not a.no_resolve:
        R = importlib.import_module("sharc_resolve_jumps")      # (selas)
        with tempfile.TemporaryDirectory() as tmp:
            text, be, offs = R.resolve(text, dsp.FDN8_SW, pathlib.Path(tmp))
        print(f"resolved at sw {dsp.FDN8_SW:#x}: {len(offs)} instructions, {len(be)} bytes")
    OUT.write_text(text, encoding="utf-8", newline="\n")
    n = sum(1 for ln in text.splitlines() if ln.startswith("      ") and not ln.strip().startswith("//"))
    print(f"wrote {OUT.relative_to(ROOT)}: {n} instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
