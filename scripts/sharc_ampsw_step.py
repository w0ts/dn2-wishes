"""AMP ON/OFF's bypass in Elektron's own DSP code (2026-11-20, the User; dnfw.waverider.ampsw, docs/live-select.md):
the gate's `ampdsp` step, the SHARC runner on this tree's DSP image (dnfw.waverider.dsp.section7).

Voice slot 0 plays SOPHIE (a drum machine of ours) on track 0, slot 1 WaveTone on track 1, each slot on its own track
(the slot map), both triggered, both with an AMP and VOL far from unity (ATK 16, VOL 64: a gain of 0.25). The same
frames are run four times, only the ColdFire's word in the pool (ampsw.pool_off) differing:

  R0  0                       (no word: the build as it plays a project with no drum OFF)
  R1  MAGIC | bit 0           (track 0 OFF)
  R2  MAGIC | every bit but 0 (track 0 ON, every other track OFF)
  R3  0x0000ffff              (bits without the magic: nothing)

PASS when, every block:
  1. R1: slot 0's buffer at the end of VOL's loop is, bit for bit, its buffer as the AMP stage was called (unity: the
     AMP and VOL bypassed), and that block sounds; in R0 it is not (the control: AMP and VOL act there);
  2. R1: every other slot's buffer and stock's AMP level of slot 0 (its envelope moves on as stock's) == R0's;
  3. R2: slot 0's buffer == R0's (ON: stock's AMP and VOL bit for bit); slot 1's bypassed as in 1;
  4. R3: every slot's buffer and the main mix == R0's;
  5. no run halts.

    DT2_SECTIONS=../sec112 python scripts/sharc_ampsw_step.py --image STOCK.syx [--json OUT] [--blocks N]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

ROUTE_FRAME = 0xA5A                             # the frame's slot map: halfword s = slot s's track
VOL, ATK = 90, 81                               # frame indices (dnfw.waverider.frame RECORD_FIELDS)
AMP_LEVEL = 0x2547C8                            # slot 0's AMP level word (the negated level; scripts/sharc_matrix_env.py)
MAIN = (0x268438, 64)                           # the main mix after the block (scripts/sharc_stockout_step.py)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--image", type=pathlib.Path, default=pathlib.Path(os.environ.get("DT2_SYX", "")))
    p.add_argument("--digikit", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("DNFW_DIGIKIT_SHARC", HERE.parent.parent / "digikit-wt-sharcemu")))
    p.add_argument("--blocks", type=int, default=10)
    p.add_argument("--json", default=None)
    a = p.parse_args()
    import sharc_waverider_m5 as M
    from sharc_f32 import sounds
    from dnfw.mnm import machines as MM
    from dnfw.waverider import ampsw as AS
    from dnfw.waverider import dsp
    FR, m2, V = M.FR, M.m2, M.V
    dk = M.m1.Digikit(a.digikit)
    M.fx.bind(str(a.digikit / "tools"))
    M.m4.IMAGE = a.image
    stock = M.m1.dn2_section7(a.image)
    img = M.Image(dk, dsp.section7(stock))
    if "ampsw" not in dsp.objects():
        print("FAIL: this tree's DSP image has no ampsw.asm")
        return 1
    sound, machines = M.m4.init_sound(a.image)
    k = MM.NAMES.index("SOPHIE")
    drum_ty, drum_words = MM.TYPES[k], M.mnm_words(k)
    word_at = dsp.SMP_POOL_DDR + AS.pool_off()

    def frame(b):
        f = M.base_frame(sound, machines, t0=4, trigger=False)
        for s in range(16):
            f.put(ROUTE_FRAME + 2 * s, s)
        for s, ty, words in ((0, drum_ty, drum_words), (1, 1, machines.get(1, {}))):
            f.header(FR.MACHINE, s, ty)
            for i, w in words.items():
                f.param(s, i, w)
            f.param(s, VOL, 0x4000)
            f.param(s, ATK, 0x1000)
            f.header(FR.NOTE, s, 0x3C00)
            if b == 1:
                f.trigger(s, masks=(34, 38))
        return f.to_bytes()

    def run(word):
        init = M.init_on(snap, m2mach, M.Image(dk, img.stream), warm=True)
        m2.poke(init.state, word_at, word)
        pre, post, lev = [], [], []
        cur = {}

        # (2026-11-21: "pre" was hooked at dsp.AMPSW_SW, the object's start, which is hook B's entry after VOL's loop:
        # it read the AMP's output, or DUMMY for a bypassed slot; now at hook A's site, stock's sw 0x1c99b4)
        def at_a(r):                           # hook A's site: every slot's buffer as the AMP stage will get it
            bufs = [m2.word(r.state, V.TRACK_BUFFERS + 4 * t) for t in range(16)]
            cur["pre"] = [[m2.word(r.state, bufs[t] + 4 * i) for i in range(M.BLOCK)] for t in range(16)]

        def at_b(r):                           # after hook B: every slot's buffer after VOL's loop
            bufs = [m2.word(r.state, V.TRACK_BUFFERS + 4 * t) for t in range(16)]
            cur["post"] = [[m2.word(r.state, bufs[t] + 4 * i) for i in range(M.BLOCK)] for t in range(16)]
            cur["lev"] = m2.word(r.state, AMP_LEVEL)
        state, mains, halt = init, [], None
        for b in range(a.blocks):
            cur.clear()
            res = M.run_blocks(state, lambda _b, b=b: frame(b), 1,
                               extra_hooks={AS.SITE_A_SW: at_a, AS.SITE_B_RESUME: at_b})
            if not res.get("ok") or "pre" not in cur or "post" not in cur:
                halt = f"block {b}: {res.get('halt') or 'a hook not reached'}"
                break
            state = res["state"]
            pre.append(cur["pre"])
            post.append(cur["post"])
            lev.append(cur["lev"])
            mains.append(tuple((m2.word(state.state, MAIN[0] + 4 * i) or 0) for i in range(MAIN[1])))
        return {"pre": pre, "post": post, "lev": lev, "main": mains, "halt": halt}

    checks, numbers = {}, {}
    with tempfile.TemporaryDirectory(dir=M.OUT) as tmp:
        snap, m2mach = M.snapshot_path(dk, stock, pathlib.Path(tmp))
        runs = {name: run(w) for name, w in (("R0", 0), ("R1", AS.MAGIC | 1), ("R2", AS.MAGIC | 0xFFFE),
                                             ("R3", 0xFFFF))}
    for name, r in runs.items():
        checks[f"5. {name}: every block returns"] = r["halt"] is None
        numbers[name] = {"halt": r["halt"], "blocks": len(r["post"])}
    if all(r["halt"] is None for r in runs.values()):
        r0, r1, r2, r3 = (runs[n] for n in ("R0", "R1", "R2", "R3"))
        n = len(r0["post"])

        def f32s(ws):
            return [M.V.bits_f32(w or 0) for w in ws]
        bypass1 = [b for b in range(n) if r1["post"][b][0] != r1["pre"][b][0]]
        sound1 = [b for b in range(n) if sounds(r1["pre"][b][0])]
        acts0 = [b for b in range(n) if r0["post"][b][0] != r0["pre"][b][0]]
        checks["1. R1 (track 0 OFF): slot 0 leaves VOL's loop as it reached the AMP stage, bit for bit, every block"] = (
            not bypass1)
        checks["1. R1: slot 0 sounds there (not a silent pass)"] = len(sound1) >= n // 2
        checks["1. control R0: stock's AMP and VOL change slot 0 (bypass off)"] = len(acts0) >= n // 2
        others1 = [b for b in range(n) if r1["post"][b][1:] != r0["post"][b][1:]]
        checks["2. R1: every other slot's buffer == R0's, every block"] = not others1
        checks["2. R1: stock's AMP level of slot 0 moves on as R0's (its state as stock's)"] = r1["lev"] == r0["lev"]
        on2 = [b for b in range(n) if r2["post"][b][0] != r0["post"][b][0]]
        by2 = [b for b in range(n) if r2["post"][b][1] != r2["pre"][b][1]]
        checks["3. R2 (track 0 ON, the rest OFF): slot 0 == R0's, bit for bit, every block"] = not on2
        checks["3. R2: slot 1 (track 1 OFF) bypassed, every block"] = not by2
        same3 = [b for b in range(n) if r3["post"][b] != r0["post"][b] or r3["main"][b] != r0["main"][b]]
        checks["4. R3 (no magic): every slot and the main mix == R0's, every block"] = not same3
        numbers.update({"R1 slot 0 differing blocks": bypass1, "R1 sounding blocks": sound1, "R0 acting blocks": acts0,
                        "R1 others differing": others1, "R2 slot 0 differing": on2, "R2 slot 1 not bypassed": by2,
                        "R3 differing": same3,
                        "slot 0 gain in R0, last block (post / pre peak)": _gain(f32s(r0["post"][-1][0]),
                                                                                 f32s(r0["pre"][-1][0]))})
    for c, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + c, flush=True)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps({"checks": checks, "numbers": numbers}, indent=1, default=str))
    bad = [c for c, ok in checks.items() if not ok]
    print(("FAIL: " + "; ".join(bad)) if bad else
          f"PASS: AMP OFF is unity bit for bit on its slot, ON and every other slot as stock ({a.blocks} blocks x 4 runs)",
          flush=True)
    return 1 if bad else 0


def _gain(post, pre) -> float | None:
    a, b = max(abs(x) for x in post), max(abs(x) for x in pre)
    return round(a / b, 6) if b else None


if __name__ == "__main__":
    raise SystemExit(main())
