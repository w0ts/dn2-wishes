"""PARA as one voice: what a chord's slot costs a block (scripts/dsp_cost.py's method: instructions + 4 L2 + 10 DDR),
N notes on one slot (its row: the leader's own note and N - 1 joined, their shadows in the L2 pool), ANALOG 2 and
JUNO at their defaults, against PARA OFF's N slots; and the PARA pass a block. Steady blocks and the note blocks
(docs/paraphonic-onevoice.md).

    python3 scripts/para_onevoice_cost.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "test")]

BLOCKS, STEADY = 10, (4, 5, 6, 7)
OFFS = (0, 4, 7, 11, 14, 16, 19, 23)


def run(n: int, engine: str) -> dict:
    import para_cost as PC
    PC._imports()
    DC, PP = PC.DC, PC.PP
    import test_a2_para as T
    from dnfw.engines.analog2 import para as PA
    from dnfw.perc.dsl import Prog, bits
    lead = T.LEAD
    h = T.setup([lead], para=3 if n else 0, engine=engine)     # (0: PARA OFF, no row: the pass with nothing to do)
    T.ready(h)
    L = h.L
    per, pre = [], []
    for b in range(BLOCKS):
        h.mem.put(PP.NOTE_CELLS + 4 * lead, bits(60.0))
        h.mem.put(PP.BUFFERS + 4 * lead, T.BUFS + 0x100 * lead)
        h.mem.put(PP.TRIG_WORD, (h.mem.get(PP.TRIG_WORD) & 0xFFFF) | ((1 << lead) << 16 if b == 1 else 0))
        h.mem.put(L.C["mcost"], 0)
        if b == 1 and n:                             # the chord's row comes with its note (the ColdFire's order)
            T.write_row(h, lead, {k: (OFFS[k], True, 1) for k in range(n)})
        p = Prog("run", mem=h.mem)
        p.spill = L.md.C["ash"]
        PP.mnm_ages(p, L)
        s0 = p.steps
        PP.para_prepass(p, L)
        pre.append(p.steps - s0)
        c = DC._measure(lambda: DC._first_prog(lambda: PP.run_voice(L, None, lead, mem=h.mem)))
        per.append(PC.tot(c))
    return {"steady": round(sum(per[b] for b in STEADY) / len(STEADY)), "note": round(max(per[1], per[2])),
            "pass_steady": round(sum(pre[b] for b in STEADY) / len(STEADY)), "pass_note": max(pre[1], pre[2]),
            "role": h.mem.get(PA.ROLE + 4 * lead) >> PA.ROLE_SHIFT}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    import para_cost as PC
    PC._imports()
    PC.DC._install()
    out = {}
    for engine in ("ANALOG2", "JUNO"):
        for n in (0, 1, 2, 4, 8):
            r = run(n, engine)
            out[f"{engine} {n}"] = r
            print(engine, n, "notes on one slot:", r, flush=True)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
