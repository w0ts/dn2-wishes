"""Write the inserts' SHARC source, csrc/waverider/sharc/inserts.asm (docs/inserts.md).

    python scripts/gen_inserts_asm.py [--no-resolve]

The program is `dnfw.inserts.program.program`: the same calls that, run in Python, are the
model held bit for bit to dnfw.inserts.ref (test/test_inserts.py), and that the SHARC runner holds
the assembled code to (scripts/sharc_waverider_m5.py, step inserts). This writes its assembly
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

P = importlib.import_module("dnfw.inserts.program")
dsp = importlib.import_module("dnfw.waverider.dsp")

OUT = ROOT / "csrc" / "waverider" / "sharc" / "inserts.asm"
POST = importlib.import_module("dnfw.inserts.post")
OUT_POST = ROOT / "csrc" / "waverider" / "sharc" / "inspost.asm"
BUS = importlib.import_module("dnfw.inserts.bus")
OUT_BUS = ROOT / "csrc" / "waverider" / "sharc" / "insbus.asm"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-resolve", action="store_true")
    a = ap.parse_args(argv)
    from dnfw.a2f import design as AD, program as AP     # 2026-11-10: wr_ins -> wr_a2f -> PING
    jobs = [(P.program(dsp.A2F_SW if AD.BUILT_MODELS else dsp.PING_SW), dsp.INS_SW, OUT),
            (POST.program(), dsp.POST_SW, OUT_POST), (BUS.program(), dsp.INSBUS_SW, OUT_BUS)]
    A2F_OUT = ROOT / "csrc" / "waverider" / "sharc" / "a2f.asm"
    if AD.BUILT_MODELS:
        jobs.append((AP.program(dsp.PING_SW), dsp.A2F_SW, A2F_OUT))
    elif A2F_OUT.exists():
        A2F_OUT.unlink()
    for text, at, out in jobs:
        if not a.no_resolve:
            R = importlib.import_module("sharc_resolve_jumps")      # (selas)
            with tempfile.TemporaryDirectory() as tmp:
                text, be, offs = R.resolve(text, at, pathlib.Path(tmp))
            print(f"resolved at sw {at:#x}: {len(offs)} instructions, {len(be)} bytes")
        out.write_text(text, encoding="utf-8", newline="\n")
        n = sum(1 for ln in text.splitlines() if ln.startswith("      ") and not ln.strip().startswith("//"))
        print(f"wrote {out.relative_to(ROOT)}: {n} instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
