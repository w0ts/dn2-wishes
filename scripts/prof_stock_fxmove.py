"""The stock send FX's state from DDR to L2, proved word for word (measuring and proof only; opt-stock item 1).

dnfw.waverider.stockfx moves the stock delay's control words and the chorus's state (DDR 0x80459130..0x8045a6cc)
to L2 by re-pointing 73 stock instructions. This runs the build without the move (A: dnfw.waverider.dsp.section7
with the patches and the span left out) and the build with it (B) over the stockout step's frames (random machine,
FX and master words, trigs, a silence with the sends up and a wake), each on a fresh image, and after every block
requires:

- every output of sharc_stockout_step equal (main, tracks, FX returns, TDM, records, mono buffers);
- all of stock's L1 state (0x240000..0x2c0000) equal;
- B's block in L2 equal to A's block in DDR, word for word;
- no access by B to the old block in DDR;
- every one of the 73 re-pointed instructions executed at least once over the runs (else it is not proved here).

    bench_ns112.sh TREE python scripts/prof_stock_fxmove.py --image IMG --digikit DK [--blocks 16] [--seeds 16,13]
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("DNFW_ROOT", pathlib.Path.cwd()))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import prof_stock_hotspots as H                                   # noqa: E402
import sharc_stockout_step as SO                                  # noqa: E402
from dnfw.waverider import dsp                                    # noqa: E402

M5, fx, m2, m4 = H.M5, H.fx, H.m2, H.m4


def without_move(stock: bytes) -> bytes:
    keep = dsp.fx_patches, dsp.fx_spans
    dsp.fx_patches, dsp.fx_spans = (lambda: []), (lambda stock: [])
    try:
        return dsp.section7(stock)
    finally:
        dsp.fx_patches, dsp.fx_spans = keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("DT2_SYX"))
    ap.add_argument("--digikit", default=os.environ.get("DNFW_DIGIKIT_SHARC"))
    ap.add_argument("--blocks", type=int, default=16)
    ap.add_argument("--seeds", default="16,13")
    ap.add_argument("--out", default="out/stock/fxmove.json")
    a = ap.parse_args()
    B = H.Bench(pathlib.Path(a.image), a.digikit)
    B.undo()
    conc = sys.modules["sharc_core.memory"]._concrete_address
    sites = {sw for sw, *_ in dsp.fx_patches()}
    cur = {"pc": 0, "on": False}
    old_hits = collections.Counter()
    ran = set()
    orig_r, orig_w = fx._dm_read, fx._dm_write

    def note(address):
        if cur["on"]:
            ad = conc(address)
            if ad is not None and dsp.FX_DDR <= ad < dsp.FX_DDR + dsp.FX_BYTES:
                old_hits[cur["pc"]] += 1

    def rd(state, address, width, *x, **k):
        note(address)
        return orig_r(state, address, width, *x, **k)

    def wr(state, address, width, value):
        note(address)
        return orig_w(state, address, width, value)
    for m in list(sys.modules.values()):
        for name, new, o in (("_dm_read", rd, orig_r), ("_dm_write", wr, orig_w)):
            if getattr(m, name, None) is o:
                setattr(m, name, new)

    class Last(list):
        def append(self, pc):
            cur["pc"] = pc
            if pc in sites:
                ran.add(pc)

    img_a = M5.Image(B.dk, without_move(B.stock.stream))
    img_b = M5.Image(B.dk, dsp.section7(B.stock.stream))

    def run(img, fb, moved):
        state = M5.init_on(B.snap, B.m2mach, SO.fresh(img))
        caps, reply = [], {}

        def at_out(r):
            reply["at"] = m2.word_reg(r, "R12")
            SO.mark_tx(m2, r.state)
        for b in range(a.blocks):
            r = m4.unpack_call(state, fb(b))
            f = M5.fixups({SO.OUTPUT_CALL_SW: at_out})
            f.last = Last()
            cur["on"] = moved
            res = fx.run(r, 40_000_000, f)
            cur["on"] = False
            if not (res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN):
                return caps, f"block {b}: {res[:2]}"
            st = r.state
            o = SO.outputs(m2, st, reply.get("at"))
            o["state"] = tuple((m2.word(st, x) or 0) & 0xFFFFFFFF for x in range(*SO.STATE_L1, 4))
            at = dsp.FX_DM if moved else dsp.FX_DDR
            o["fx block"] = tuple((m2.word(st, at + k) or 0) & 0xFFFFFFFF for k in range(0, dsp.FX_BYTES, 4))
            caps.append(o)
            state = r
        return caps, None

    res = {"runs": {}}
    ok = True
    for seed in (int(x) for x in a.seeds.split(",")):
        fb = SO.scenario(B.sound, B.machines, seed, a.blocks, globals_random=True,
                         silence=(a.blocks // 2, a.blocks - 3))
        ca, ha = run(img_a, fb, False)
        cb, hb = run(img_b, fb, True)
        diff = collections.defaultdict(list)
        if not ha and not hb:
            for b, (x, y) in enumerate(zip(ca, cb)):
                for k in x:
                    if x[k] != y[k]:
                        diff[k].append(b)
        sounding = any(any(w & 0x7FFFFFFF for w in c["FX returns"]) for c in ca)
        res["runs"][seed] = {"halts": [ha, hb], "differing (key: blocks)": dict(diff), "FX returns not silent": sounding}
        ok &= not ha and not hb and not diff and sounding
    res["old block accessed by the build with the move (pc: n)"] = {f"{p:#x}": n for p, n in old_hits.items()}
    res["re-pointed instructions never executed"] = sorted(f"{s:#x}" for s in sites - ran)
    res["re-pointed instructions executed"] = f"{len(ran & sites)} of {len(sites)}"
    res["ok"] = ok and not old_hits
    p = pathlib.Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    print("OK" if res["ok"] else "NOT OK")


if __name__ == "__main__":
    main()
