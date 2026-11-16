"""The same note on every voice slot in the SHARC runner (this tree's DSP image): each slot's block after the chain
against slot 0's, bit for bit and in level.

2026-11-14 (opt-host): the coupled emulator and the runner's full-frame replays sounded only voice slot 0 (stock or
ours). Three runner gaps (sharc_dn2_fixups G12 the odd slots' note latch, G13 MODIFY's byte scale, G14 a long word's
modify) and the warm snapshot the engine init left under them. This is their proof: a slot passes when its blocks
are bit-identical to slot 0's, or (--tolerance) its RMS within that many dB. With them: slots 0..15 bit-identical.

Every slot gets the same frame words (track 0's from base_frame, then the machine's own page; note 60, trig at block 1
on masks 34 and 38, as the ColdFire's frames carry it); the other slots stay MIDI.

    python scripts/sharc_slots.py STOCK.syx [--slots 0-15] [--machines stock1,DRONE,JUNO] [--blocks 10]
        [--tolerance 0.5] [--stages] [--json OUT]"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import sharc_waverider_m5 as M  # noqa: E402


# the per-slot chain's call sites in sw 0x1c8ef1 (docs/waverider-feasibility.md): each runs its stage for slots 0..15
STAGES = {0x1C945D: "b8251b", 0x1C946A: "+4dB", 0x1C95CD: "1cdb56", 0x1C9501: "DC blocker", 0x1C95B8: "b8265b",
          0x1C95A3: "base-width", 0x1C98B3: "filter", 0x1C99D0: "amp", M.LOOP_RESUME: "after the machines"}


def stage_gains(trace, slot):
    """each stage's (name, peak in, peak out) on SLOT, from (site, [16 peaks]) taken at each call: a stage's call
    for SLOT is its slot-th in its run of 16; one called once a block is shown with its single reading"""
    out, k, names = [], 0, [x[0] for x in trace]
    while k < len(trace):
        j = k
        while j < len(trace) and names[j] == names[k]:
            j += 1
        calls = trace[k:j] + ([trace[j]] if j < len(trace) else [])
        if j - k == 16:
            out.append((names[k], round(calls[slot][1][slot], 4), round(calls[slot + 1][1][slot], 4)))
        elif j - k == 1:
            out.append((names[k], round(calls[0][1][slot], 4)))
        k = j
    return out


def rms_db(xs) -> float:
    r = math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else 0.0
    return 20 * math.log10(r) if r > 0 else -999.0


def slot_list(spec: str) -> list[int]:
    out = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out += list(range(int(lo), int(hi or lo) + 1))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("image", type=pathlib.Path)
    p.add_argument("--slots", default="0-15")
    p.add_argument("--machines", default="stock1")
    p.add_argument("--blocks", type=int, default=10)
    p.add_argument("--tolerance", type=float, default=None, help="dB: pass on RMS within it, not only bit-exact")
    p.add_argument("--stages", action="store_true", help="each chain stage's peak in and out on the slot")
    p.add_argument("--json", default=None)
    a = p.parse_args()
    FR = M.FR
    from dnfw.mnm import machines as MM                          # noqa: PLC0415
    dkp = pathlib.Path(os.environ.get("DNFW_DIGIKIT_SHARC", "/mnt/d/01_Code/Z_Personal/digikit-wt-sharcemu"))
    dk = M.m1.Digikit(dkp)
    M.fx.bind(str(dkp / "tools"))
    M.m4.IMAGE = a.image
    stock = M.m1.dn2_section7(a.image)
    img = M.Image(dk, M.dsp.section7(stock))
    sound, machines = M.m4.init_sound(a.image)
    slots_all = [i for b in FR.SLOT_BLOCKS for i in range(b[0], b[1] + 1)]
    pages = {"stock1": (1, machines.get(1, {}))}
    for name in MM.NAMES:
        k = MM.NAMES.index(name)
        pages[name] = (MM.TYPES[k], M.mnm_words(k))
    slots = slot_list(a.slots)
    rep, ok_all = {"slots": slots, "machines": {}}, True
    with tempfile.TemporaryDirectory(dir=M.OUT) as tmp:
        snap, m2mach = M.snapshot_path(dk, stock, pathlib.Path(tmp))
        print(f"  warm snapshot {snap.name}", flush=True)
        for name in a.machines.split(","):
            ty, page = pages[name]
            runs = {}
            for s in slots:
                init = M.init_on(snap, m2mach, M.Image(dk, img.stream), warm=True)

                def fb(b, s=s):
                    f = M.base_frame(sound, machines, t0=4, trigger=False)
                    if s != 0:
                        for i in slots_all:
                            f.param(s, i, f.get(FR.slot_offset(0, i)))
                    f.header(FR.MACHINE, s, ty)
                    for i, w in page.items():
                        f.param(s, i, w)
                    f.header(FR.NOTE, s, 0x3C00)
                    if b == 1:
                        f.trigger(s, masks=(34, 38))
                    return f.to_bytes()
                trace, blk = [], {"b": -1}

                def at_d(r, blk=blk):
                    blk["b"] += 1

                def tap(name, trace=trace, blk=blk):
                    def f_(r):
                        if blk["b"] == a.blocks - 1:
                            bs = [M.m2.word(r.state, M.V.TRACK_BUFFERS + 4 * t) for t in range(16)]
                            trace.append((name, [max(abs(x) for x in M.m2.floats(r.state, b_, M.BLOCK)) for b_ in bs]))
                    return f_
                hooks = {M.m3.DISPATCH: at_d, **{pc: tap(n) for pc, n in STAGES.items()}} if a.stages else None
                rr = M.run_blocks(init, fb, a.blocks, extra_hooks=hooks)
                if trace:
                    print(f"    stages on slot {s}, last block: {stage_gains(trace, s)}", flush=True)
                bits = [blk[s] for blk in rr["buffer_bits"]]
                xs = [x for blk in rr["buffers"][4:] for x in blk[s]]
                runs[s] = {"ok": rr["ok"], "bits": bits, "rms_db": round(rms_db(xs), 2),
                           "peaks": [round(max(abs(x) for x in blk[s]), 4) for blk in rr["buffers"]]}
                print(f"  {name} slot {s:2d}: RMS (blocks 4..) {runs[s]['rms_db']} dB, peaks {runs[s]['peaks']}",
                      flush=True)
            ref = runs[slots[0]]
            res = {}
            for s in slots:
                same = runs[s]["bits"] == ref["bits"]
                diff = runs[s]["rms_db"] - ref["rms_db"]
                ok = runs[s]["ok"] and (same or (a.tolerance is not None and abs(diff) <= a.tolerance))
                ok_all &= ok
                res[s] = {"bit_exact": same, "rms_db": runs[s]["rms_db"], "vs_first_db": round(diff, 2), "ok": ok}
            rep["machines"][name] = res
            print(f"  {name}: " + ", ".join(f"{s}:{'=' if r['bit_exact'] else round(r['vs_first_db'], 2)}"
                                           for s, r in res.items()), flush=True)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rep, indent=1))
    print("PASS" if ok_all else "FAIL", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
