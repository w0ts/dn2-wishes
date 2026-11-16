"""What the stock send FX write in a silent block (measuring only): for the sends phase of the stock
engine (sw 0x1c1738 and below), every data write by function, with its value, over consecutive silent
blocks. The idle gate (docs: stock-hotspots.md item 1) may skip an FX only if it reproduces every write that
is not a zero into zero: this lists them.

    bench_ns112.sh TREE python scripts/prof_stock_writes.py --image IMG --digikit DK --out out/stock/writes.json
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

M5, fx, m4 = H.M5, H.fx, H.m4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("DT2_SYX"))
    ap.add_argument("--digikit", default=os.environ.get("DNFW_DIGIKIT_SHARC"))
    ap.add_argument("--blocks", type=int, default=6)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    B = H.Bench(pathlib.Path(a.image), a.digikit)
    prof = B.prof
    conc = sys.modules["sharc_core.memory"]._concrete_address
    log = {}                                    # block -> [(phase, pc, addr, value)]
    cur = {"b": -1}
    patched = []
    # the Bench's own wrapper is installed; wrap on top of it (replace the module attribute everywhere)
    wrapped = fx._dm_write
    for m in list(sys.modules.values()):
        if getattr(m, "_dm_write", None) is wrapped:
            patched.append((m, wrapped))

    def wr2(state, address, width, value):
        if prof.phase == "sends" and cur["b"] >= 0:
            ad = conc(address)
            log.setdefault(cur["b"], []).append((prof.cur, ad if ad is not None else -1, (value.value if isinstance(value, fx.Const) else -1) & 0xFFFFFFFF))
        return wrapped(state, address, width, value)
    for m, _ in patched:
        m._dm_write = wr2
    frame = lambda b: M5.base_frame(B.sound, B.machines, t0=4, trigger=False).to_bytes()   # noqa: E731
    state = B.init
    for b in range(a.blocks):
        cur["b"] = b
        prof.phase = H.PHASE0
        hooks = {ad: (lambda ph: lambda r: setattr(prof, "phase", ph))(p) for ad, p in H.PHASE_AT.items()}
        r = m4.unpack_call(state, frame(b))
        f = M5.fixups(hooks)
        f.last = prof
        res = fx.run(r, 40_000_000, f)
        ok = res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN
        print("block", b, ok, len(log.get(b, [])), flush=True)
        if not ok:
            break
        state = r
    for m, orig in patched:
        m._dm_write = orig
    last, prev = a.blocks - 1, a.blocks - 2
    final = {}
    for blk in (prev, last):
        d = {}
        for pc, ad, v in log.get(blk, []):
            d[ad] = (v, pc)                      # the last write to each address in the block
        final[blk] = d
    changing, nonzero = {}, {}
    for ad, (v, pc) in final[last].items():
        v0 = final[prev].get(ad, (None, None))[0]
        if v != 0:
            nonzero[ad] = (v, pc)
        if v0 is not None and v0 != v:
            changing[ad] = (v0, v, pc)
    out = {"writes_last_block": len(log.get(last, [])), "distinct_addresses": len(final[last]),
           "nonzero": {f"{k:#x}": [f"{v:#x}", f"{pc:#x}"] for k, (v, pc) in sorted(nonzero.items())},
           "changing": {f"{k:#x}": [f"{a0:#x}", f"{a1:#x}", f"{pc:#x}"] for k, (a0, a1, pc) in sorted(changing.items())}}
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: (v if not isinstance(v, dict) else len(v)) for k, v in out.items()}))
    B.undo()


if __name__ == "__main__":
    main()
