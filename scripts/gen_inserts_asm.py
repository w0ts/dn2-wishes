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
import re
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
JSEND = importlib.import_module("dnfw.inserts.jsend")
OUT_JSEND = ROOT / "csrc" / "waverider" / "sharc" / "jsend.asm"


def label_sw(text: str, offs: list, at: int, label: str) -> int:
    """the sw address of LABEL in a resolved TEXT (OFFS: its instructions' byte offsets, AT: its load sw), checked
    against every resolved jump to it in TEXT"""
    k, where = 0, None
    for ln in text.splitlines():
        s = ln.strip()
        if s == f"{label}.:":
            where = k
        elif ln.startswith("      ") and s and not s.startswith(("//", ".")) and ";" in s:
            k += 1
    assert k == len(offs) and where is not None, (label, k, len(offs))
    sw = at + offs[where] // 2
    for m in re.finditer(r"JUMP (0x[0-9a-f]+);\s*// -> " + re.escape(label) + r"\.", text):
        assert int(m.group(1), 16) == sw, (label, m.group(0), hex(sw))
    return sw


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-resolve", action="store_true")
    a = ap.parse_args(argv)
    from dnfw.engines.analog2.filters import design as AD, program as AP     # 2026-11-10: wr_ins -> wr_a2f -> PING
    # 2026-11-21 (DSP room): jsend enters inspost's one JUNO copy (dnfw.inserts.post.juno_call), so its text is made
    # once inspost is resolved (a callable job: the resolved texts so far -> its text)
    jobs = [(P.program(dsp.A2F_SW if AD.BUILT_MODELS else dsp.PING_SW), dsp.INS_SW, OUT),
            (POST.program(), dsp.POST_SW, OUT_POST), (BUS.program(), dsp.INSBUS_SW, OUT_BUS),
            (lambda done: JSEND.program(juno_sw=label_sw(*done[OUT_POST], f"wr_ip_{POST.JUNO_ENTRY}")),
             dsp.JSEND_SW, OUT_JSEND)]
    A2F_OUT = ROOT / "csrc" / "waverider" / "sharc" / "a2f.asm"
    if AD.BUILT_MODELS:
        jobs.append((AP.program(dsp.PING_SW), dsp.A2F_SW, A2F_OUT))
    elif A2F_OUT.exists():
        A2F_OUT.unlink()
    done: dict = {}
    for text, at, out in jobs:
        if callable(text):
            if a.no_resolve:
                raise SystemExit("jsend.asm needs inspost.asm resolved (JUNO's one copy): run without --no-resolve")
            text = text(done)
        if not a.no_resolve:
            R = importlib.import_module("sharc_resolve_jumps")      # (selas)
            with tempfile.TemporaryDirectory() as tmp:
                text, be, offs = R.resolve(text, at, pathlib.Path(tmp))
            print(f"resolved at sw {at:#x}: {len(offs)} instructions, {len(be)} bytes")
            done[out] = (text, offs, at)
        out.write_text(text, encoding="utf-8", newline="\n")
        n = sum(1 for ln in text.splitlines() if ln.startswith("      ") and not ln.strip().startswith("//"))
        print(f"wrote {out.relative_to(ROOT)}: {n} instructions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
