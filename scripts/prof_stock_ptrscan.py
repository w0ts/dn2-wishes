"""Where the stock engine keeps pointers into its 16 DDR track buffers (measuring only).

The 16 mono track buffers are 128 bytes each at 0x804acf90 + 0x80 t in DDR (docs/waverider-dsp-silence.md);
the profile (docs/stock-hotspots) shows the voice dispatch spending ~9,700 DDR accesses a block on them. To
re-point them at L1 every word that holds one of those addresses must move together. This scans L1 and L2 of the
post-init snapshot (and again after two blocks) for any word inside the buffers' span and prints address, value.

    bench_ns112.sh TREE python scripts/prof_stock_ptrscan.py --image IMG --digikit DK
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("DNFW_ROOT", pathlib.Path.cwd()))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import prof_stock_hotspots as H                                   # noqa: E402

M5, fx, m2, m4 = H.M5, H.fx, H.m2, H.m4
LO, HI = int(os.environ.get('SCAN_LO', '0x804ACF90'), 0), int(os.environ.get('SCAN_HI', '0x804AD790'), 0)


def scan(state, label):
    hits = []
    for lo, hi in ((0x240000, 0x300000), (0x20000000, 0x20100000)):
        for a in range(lo, hi, 4):
            w = m2.word(state, a)
            if w is not None and LO <= w < HI:
                hits.append((a, w))
    print(f"{label}: {len(hits)} words in {LO:#x}..{HI:#x}", flush=True)
    for a, w in hits:
        print(f"  {a:#x} = {w:#x}  (+{w - LO:#x} from the span's start)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("DT2_SYX"))
    ap.add_argument("--digikit", default=os.environ.get("DNFW_DIGIKIT_SHARC"))
    a = ap.parse_args()
    B = H.Bench(pathlib.Path(a.image), a.digikit)
    scan(B.init.state, "post-init snapshot")
    state = B.init
    for b in range(2):
        r = m4.unpack_call(state, M5.base_frame(B.sound, B.machines, t0=1, trigger=(b == 1)).to_bytes())
        res = fx.run(r, 40_000_000, M5.fixups({}))
        assert res[0] == "halt", res
        state = r
    scan(state.state, "after 2 blocks")
    B.undo()


if __name__ == "__main__":
    main()
