"""The stock send FX's state in L2, proved from engine init on (measuring and proof only; opt-stock item 1).

The runner's steps start from a snapshot of engine init run on STOCK code (sw 0x1c1445), and the build's runs copy the
moved block there (sharc_waverider_m5._chorus_copy), which would hide a fault in what the build's own init leaves.
This runs engine init itself on the build without the move (A: dnfw.waverider.dsp.section7 with the patches and the
span left out) and with it (B), then 16 blocks of the stockout step's frames from each image's own init, and prints:

- the moved block after init, B's in L2 against A's in DDR, and all of stock's L1 state;
- per output of sharc_stockout_step (and the block, and stock's L1), the blocks where B differs from A;
- which of the re-pointed instructions init and the blocks executed.

It found, 2026-11-12, that stock's stream loads the chorus's last word (base + 0x1340) as 1.0: the L2 span now loads
the stock stream's initial words, not zeros. About 50 minutes (two engine inits).

    bench_ns112.sh TREE python scripts/prof_stock_fxinit.py --image IMG --digikit DK
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(os.environ.get("DNFW_ROOT", pathlib.Path.cwd()))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import prof_stock_fxmove as PF                                    # noqa: E402
import prof_stock_hotspots as H                                   # noqa: E402
import sharc_stockout_step as SO                                  # noqa: E402
import sharc_waverider_m5 as M5                                   # noqa: E402
import sharc_waverider_voice as V2                                # noqa: E402
from dnfw.waverider import dsp, testtable                         # noqa: E402

fx, m2 = M5.fx, M5.m2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("DT2_SYX"))
    ap.add_argument("--digikit", default=os.environ.get("DNFW_DIGIKIT_SHARC"))
    ap.add_argument("--blocks", type=int, default=16)
    a = ap.parse_args()
    dk = M5.m1.Digikit(pathlib.Path(a.digikit))
    fx.bind(str(pathlib.Path(a.digikit) / "tools"))
    stock = M5.m1.dn2_section7(pathlib.Path(a.image))
    sites = {sw for sw, *_ in dsp.fx_patches()}
    ran = set()
    orig_run = fx.run

    class Last(list):
        def append(self, pc):
            if pc in sites:
                ran.add(pc)

    def run(r, n, f, stop_at=()):
        f.last = Last()
        return orig_run(r, n, f, stop_at)
    fx.run = V2.fx.run = run
    inits = {}
    with tempfile.TemporaryDirectory(dir=M5.OUT) as tmp:
        tmp = pathlib.Path(tmp)
        reader, _, _ = M5.m1.reader_code(False, tmp)
        for name, stream in (("A", PF.without_move(stock)), ("B", dsp.section7(stock))):
            res = V2.run_init(V2.Machine(dk, stream, reader, testtable.table()), tmp / f"init_{name}.snap", True, 0)
            print(name, "init:", res["ok"], res["halt"], res["instructions"], flush=True)
            inits[name] = res["runner"]

    def words(st, at, n):
        return tuple((m2.word(st, at + k) or 0) & 0xFFFFFFFF for k in range(0, n, 4))
    sa, sb = inits["A"].state, inits["B"].state
    print("after init: the block equal:", words(sa, dsp.FX_DDR, dsp.FX_BYTES) == words(sb, dsp.FX_DM, dsp.FX_BYTES),
          "| stock L1 equal:", words(sa, 0x240000, 0x80000) == words(sb, 0x240000, 0x80000))
    bench = H.Bench(pathlib.Path(a.image), a.digikit)
    bench.undo()
    fb = SO.scenario(bench.sound, bench.machines, 16, a.blocks, globals_random=True,
                     silence=(a.blocks // 2, a.blocks - 3))
    caps = {}
    for name in ("A", "B"):
        st, cs, reply = inits[name], [], {}

        def at_out(r):
            reply["at"] = m2.word_reg(r, "R12")
            SO.mark_tx(m2, r.state)
        for b in range(a.blocks):
            r = M5.m4.unpack_call(st, fb(b))
            f = M5.fixups({SO.OUTPUT_CALL_SW: at_out})
            res = run(r, 40_000_000, f)
            if not (res[0] == "halt" and res[1].pc_sw == M5.m4.UNPACK_RETURN):
                print(name, "halt", res[:2])
                break
            o = SO.outputs(m2, r.state, reply.get("at"))
            o["block"] = words(r.state, dsp.FX_DM if name == "B" else dsp.FX_DDR, dsp.FX_BYTES)
            o["stock L1"] = words(r.state, 0x240000, 0x80000)
            cs.append(o)
            st = r
        caps[name] = cs
    for k in caps["A"][0]:
        bad = [b for b in range(min(len(caps["A"]), len(caps["B"]))) if caps["A"][b][k] != caps["B"][b][k]]
        print(f"from each own init: {k}: B differs in blocks {bad}")
    print("FX returns not silent:", any(any(w & 0x7FFFFFFF for w in c["FX returns"]) for c in caps["A"]))
    print(f"re-pointed instructions executed (init and blocks): {len(ran)} of {len(sites)}; never:",
          sorted(f"{s:#x}" for s in sites - ran))


if __name__ == "__main__":
    main()
