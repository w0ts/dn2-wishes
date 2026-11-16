"""The built image's trackbuf.asm, run the way the firmware runs it, against the same build without it
(measuring and proof only).

The SHARC runner's steps call the per-block routine (sw 0x1c2712) directly, which never passes entry_mark.asm
(the handler's call site, sw 0x1c9fbc). This enters wr_emark at EMARK_SW with TWIN cleared (the first pass),
runs it to its return to the call site, checks what trackbuf.asm left (the 32 pointer words, the 512 copied
words, the twin copy), then runs the blocks. Control: the same build, same frames, without that pass.
After every block all of L1's stock data (0x240000..0x2c0000: the engine's state, the stereo and routing
blocks, the main mix) must be equal word for word (the pointer words and the two buffer areas excepted, the
buffers compared at their own places); and the cost of both.

    bench_ns112.sh TREE python scripts/prof_trackbuf_proof.py --image IMG --digikit DK
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import struct
import sys

ROOT = pathlib.Path(os.environ.get("DNFW_ROOT", pathlib.Path.cwd()))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import prof_stock_hotspots as H                                   # noqa: E402
import prof_stock_relocate as R                                   # noqa: E402
from dnfw.waverider import dsp                                    # noqa: E402
from dnfw.perc import machines as PM                              # noqa: E402

M5, FR, fx, m1, m2, m4 = H.M5, H.FR, H.fx, H.M5.m1, H.m2, H.m4
CALL_SITE_RETURN = 0x1C9FBC
TWIN_WORD = 0x2DE140


def frames(B):
    """FM, WaveTone, FM Drum, Swarmer, PERC (the Machinedrum machines) and MIDI tracks, a filter type each,
    trigs on blocks 1 and 6, the machines rotated on block 4 and 9"""
    types = [0, 1, 2, 3, 5, 4]
    sound, machines = B.sound, B.machines

    def fb(b):
        rot = (b >= 4) + (b >= 9)
        f = M5.base_frame(sound, machines, t0=types[rot % 6], trigger=False,
                          others={t: types[(t + rot) % 6] for t in range(1, 16)})
        for t in range(16):
            f.header(FR.NOTE, t, (36 + 3 * t) << 8)
            f.header(FR.FILTER, t, t % 6)
            if types[(t + rot) % 6] == 5:
                for slot, w in M5.perc_words(t % len(PM.NAMES)).items():
                    f.param(t, slot, w)
            if b in (1, 6):
                f.trigger(t)
        return f.to_bytes()
    return fb


def first_pass(r):
    """wr_emark's first pass on the runner R: TWIN cleared, run to the handler's call site"""
    m2.poke(r.state, TWIN_WORD, 0)
    r.state.pc_sw = dsp.EMARK_SW
    res = fx.run(r, 2_000_000, M5.fixups({}), stop_at=(CALL_SITE_RETURN,))
    assert res[0] == "stop", f"the first pass did not return to the call site: {res[:2]}"
    return res[2]


def run(B, fb, nblocks, with_pass):
    state, out, prof = B.init, [], B.prof
    info = {}
    for b in range(nblocks):
        prof.on = False
        r = m4.unpack_call(state, fb(b))
        if with_pass and b == 0:
            info["pass_instructions"] = first_pass(r)
            r = m4.unpack_call(r, fb(b))          # the call's registers and frame again; memory as the pass left it
        f = M5.fixups({})
        f.last = prof
        prof.on = True
        m0 = [sum(v[g] for v in prof.mem.values()) for g in range(3)]
        res = fx.run(r, 40_000_000, f)
        ok = res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN
        mem = [sum(v[g] for v in prof.mem.values()) - m0[g] for g in range(3)]
        rec = {"b": b, "ok": ok, "instr": res[2], "DDR": mem[2]}
        rec["cycles"] = round(res[2] + H.S * (4 * mem[1] + 10 * mem[2]))
        snap = {a: m2.word(r.state, a) for a in range(0x240000, 0x2C0000, 4)}
        where = dsp.TRACKAUX_DM if with_pass else dsp.TRACKAUX_DDR
        buf = [m2.word(r.state, where + 4 * k) for k in range(576)]      # the extra block, then the 16 buffers
        out.append((rec, snap, buf))
        print("  ", rec, flush=True)
        if not ok:
            break
        state = r
    return out, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("DT2_SYX"))
    ap.add_argument("--digikit", default=os.environ.get("DNFW_DIGIKIT_SHARC"))
    ap.add_argument("--blocks", type=int, default=12)
    ap.add_argument("--out", default="out/stock/trackbuf_proof.json")
    a = ap.parse_args()
    B = H.Bench(pathlib.Path(a.image), a.digikit)
    stock = m1.dn2_section7(pathlib.Path(a.image))
    m5img = M5.Image(B.dk, dsp.section7(stock))
    B.init = M5.init_on(B.snap, B.m2mach, m5img, warm=True)
    fb = frames(B)
    print("control: the build, no first pass", flush=True)
    ctl, _ = run(B, fb, a.blocks, False)
    print("the build with wr_emark's first pass (trackbuf.asm)", flush=True)
    new, info = run(B, fb, a.blocks, True)
    ptr_words = {dsp.TRACKAUX_PTR}
    for t in range(16):
        ptr_words |= {0x254A60 + 4 * t, 0x257EA8 + 4 * t}
    # the pointers and the copy, after the first pass
    st = None
    rows, bad = [], []
    for (rc, sc, bc), (rn, sn, bn) in zip(ctl, new):
        diff = [x for x in sc if x not in ptr_words and sc[x] != sn[x] and not R.tiny(sc[x], sn[x])]
        tiny_n = sum(1 for x in sc if x not in ptr_words and sc[x] != sn[x] and R.tiny(sc[x], sn[x]))
        bdiff = sum(1 for x, y in zip(bc, bn) if x != y)
        ptr_ok = sn[dsp.TRACKAUX_PTR] == dsp.TRACKAUX_DM and all(sn[0x254A60 + 4 * t] == dsp.TRACKBUF_DM + 0x80 * t and
                     sn[0x257EA8 + 4 * t] == dsp.TRACKBUF_DM + 0x80 * t for t in range(16))
        rows.append({"b": rc["b"], "ok": rc["ok"] and rn["ok"], "pointers_at_L1": ptr_ok, "l1_words_differing": len(diff),
                     "first": [[hex(d), hex(sc[d] or 0), hex(sn[d] or 0)] for d in diff[:12]],
                     "denormal_level_differences": tiny_n, "buffer_words_differing": bdiff,
                     "control": {k: rc[k] for k in ("instr", "DDR", "cycles")},
                     "built": {k: rn[k] for k in ("instr", "DDR", "cycles")}})
        if diff or bdiff or not ptr_ok or not (rc["ok"] and rn["ok"]):
            bad.append(rc["b"])
    print(json.dumps({"info": info, "rows": rows}, indent=1))
    print("EQUAL ON EVERY BLOCK" if not bad and rows else f"DIFFERENT ON BLOCKS {bad}")
    p = pathlib.Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"info": info, "rows": rows}))
    B.undo()


if __name__ == "__main__":
    main()
