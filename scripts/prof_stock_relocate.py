"""Prototype and proof of item 2 of docs stock-hotspots: the stock engine's 16 mono track buffers moved from
DDR (0x804acf90 + 0x80 t) to L1, by re-pointing the two pointer tables (DM 0x254a60 + 4 t and its
copy at 0x257ea8) before every block, as entry_mark.asm will. The stock image runs twice over the same frames,
once as it is and once relocated; after every block all of L1 (the stock's own data: the pointer tables, the
chain's state, the stereo blocks, the routing and main buffers) must be word-for-word equal, and the 512 buffer
words must equal at the new place what they hold at the old one. Then the cost of both runs.

    bench_ns112.sh TREE python scripts/prof_stock_relocate.py --image IMG --digikit DK [--blocks 12] [--to 0x2e1d00]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("DNFW_ROOT", pathlib.Path.cwd()))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import prof_stock_hotspots as H                                   # noqa: E402

M5, FR, fx, m2, m4 = H.M5, H.FR, H.fx, H.m2, H.m4
OLD = 0x804ACF90
PTR_A = 0x254A60                                     # 16 words
PTR_B = 0x257EA8                                     # 16 contiguous words (measured 2026-11-15)


def ptr_slots():
    return [PTR_A + 4 * t for t in range(16)], [PTR_B + 4 * t for t in range(16)]


def relocate(state, to):
    for t in range(16):
        for tab in ptr_slots():
            m2.poke(state, tab[t], to + 0x80 * t)


def frames(B, nblocks):
    """a mix on all 16 tracks: the four stock machines and MIDI, a filter type on each, notes, a trig on
    blocks 1 and 6, the machines rotated on block 4 and 9"""
    types = [0, 1, 2, 3, 4]
    sound, machines = B.sound, B.machines

    def fb(b):
        rot = (b >= 4) + (b >= 9)
        f = M5.base_frame(sound, machines, t0=types[(0 + rot) % 5], trigger=False,
                          others={t: types[(t + rot) % 5] for t in range(1, 16)})
        for t in range(16):
            f.header(FR.NOTE, t, (36 + 3 * t) << 8)
            f.header(FR.FILTER, t, t % 6)
            if b in (1, 6):
                f.trigger(t)
        return f.to_bytes()
    return fb


def tiny(x, y):
    """both words are floats below 1e-30: the runner's stale-read of the pointer words as audio (the stereo
    blocks at 0x257ee8 overlap the pointer copy at 0x257ea8, and the runner reads them unscaled: docs/inserts.md),
    denormal-level and not on the unit"""
    import struct
    f = lambda w: abs(struct.unpack("<f", struct.pack("<I", (w or 0) & 0xFFFFFFFF))[0])   # noqa: E731
    return f(x) < 1e-30 and f(y) < 1e-30


def run(B, fb, nblocks, to):
    state, out, prof = B.init, [], B.prof
    for b in range(nblocks):
        prof.on = False
        r = m4.unpack_call(state, fb(b))
        if to:
            if b == 0:          # entry_mark.asm's first pass: the buffers' words go with the pointers
                for k in range(512):
                    m2.poke(r.state, to + 4 * k, m2.word(r.state, OLD + 4 * k) or 0)
            relocate(r.state, to)
        f = M5.fixups({})
        f.last = prof
        prof.on = True
        n0 = sum(prof.instr.values())
        m0 = [sum(v[g] for v in prof.mem.values()) for g in range(3)]
        res = fx.run(r, 40_000_000, f)
        ok = res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN
        mem = [sum(v[g] for v in prof.mem.values()) - m0[g] for g in range(3)]
        rec = {"b": b, "ok": ok, "instr": res[2], "L1": mem[0], "L2": mem[1], "DDR": mem[2]}
        rec["cycles"] = round(rec["instr"] + H.S * (4 * mem[1] + 10 * mem[2]))
        snap = {a: m2.word(r.state, a) for a in range(0x240000, 0x2C0000, 4)}
        buf = [m2.word(r.state, (to if to else OLD) + 4 * k) for k in range(512)]
        out.append((rec, snap, buf))
        print("  ", rec, flush=True)
        if not ok:
            break
        state = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("DT2_SYX"))
    ap.add_argument("--digikit", default=os.environ.get("DNFW_DIGIKIT_SHARC"))
    ap.add_argument("--blocks", type=int, default=12)
    ap.add_argument("--to", type=lambda s: int(s, 0), default=0x2E1D00)
    ap.add_argument("--out", default="out/stock/relocate.json")
    a = ap.parse_args()
    B = H.Bench(pathlib.Path(a.image), a.digikit)
    fb = frames(B, a.blocks)
    print("control (stock as it is)", flush=True)
    ctl = run(B, fb, a.blocks, 0)
    print(f"relocated to {a.to:#x}", flush=True)
    new = run(B, fb, a.blocks, a.to)
    ptrs = set(s for tab in ptr_slots() for s in tab)
    bad, rows = [], []
    for (rc, sc, bc), (rn, sn, bn) in zip(ctl, new):
        diff = [a_ for a_ in sc if a_ not in ptrs and sc[a_] != sn[a_] and not tiny(sc[a_], sn[a_])]
        tiny_n = sum(1 for a_ in sc if a_ not in ptrs and sc[a_] != sn[a_] and tiny(sc[a_], sn[a_]))
        bdiff = sum(1 for x, y in zip(bc, bn) if x != y)
        rows.append({"b": rc["b"], "denormal_level_differences": tiny_n, "ok": rc["ok"] and rn["ok"], "l1_words_differing": len(diff), "first": [[hex(d), hex(sc[d] or 0), hex(sn[d] or 0)] for d in diff[:40]],
                     "buffer_words_differing": bdiff, "control": {k: rc[k] for k in ("instr", "DDR", "cycles")},
                     "relocated": {k: rn[k] for k in ("instr", "DDR", "cycles")}})
        if diff or bdiff or not (rc["ok"] and rn["ok"]):
            bad.append(rc["b"])
    print(json.dumps(rows, indent=1))
    print("EQUAL ON EVERY BLOCK" if not bad and rows else f"DIFFERENT ON BLOCKS {bad}")
    p = pathlib.Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows))
    B.undo()


if __name__ == "__main__":
    main()
