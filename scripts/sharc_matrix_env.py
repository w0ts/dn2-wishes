"""The matrix's ENV1/ENV2 clone against stock's own AMP envelope, in Elektron's DSP code (the SHARC runner, stock 1.12
section 7): docs/matrix.md, the gate's `envclone` step.

    DT2_SECTIONS=../sec112 python scripts/sharc_matrix_env.py --image STOCK.syx [--json OUT]

Track 0 on WaveTone plays each case of test/test_matrix_c.py CASES (the AMP knobs, note-ons and note-offs at given
blocks): the DSP's own envelope level after every block (its word 0x2547c8, the negated level at the block's end,
found by searching the DSP's memory for the amp's measured gain) against the clone's model (test_matrix_c.model,
the same arithmetic as csrc/matrix env_step, which the host tests and the emulator check hold the C to).

The DSP hears a frame's note-on and note-off one block after the frame the clone takes them in (the clone's block b is
the DSP's b + 1, measured: equal to the last bit through an AHD hold and fall). Each case starts from rest, primed in
the DSP: a note at full level (ATK 0), then REL 0, which sets its level to exactly 0 (the runner's fresh state holds
-0.0312 there, which RSET 0 would carry). The clone steps once a block, the DSP every sample, so where a stage ends
inside a block (the attack reaching full scale, a hold running out) the DSP has gone on for the rest of that block.
Checked: every block within TOL of the DSP's next block, or, at a stage's end only, of the one before or after.
Last line PASS or FAIL.
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
sys.path.insert(0, str(HERE.parent / "test"))

LEVEL = 0x2547C8
SLOT = (81, 82, 83, 84, 85, 91, 92)             # ATK HOLD DEC SUS REL MODE RSET in the frame (dnfw.waverider.frame)
OFF_MASK = 36                                   # the frame's amp note-off word (csrc/hold)
FULL = 0x7FFFFFFF
TOL = 1e-4
PRIME = 4                                       # blocks: a note at full level, REL 0, two at rest
# the gate's run (the runner takes seconds a block): every stage and both modes, a note-off in the attack, RSET off
QUICK = ["ADSR, released in the attack", "AHD, released in the attack", "RSET off: a note-on goes on from the level",
         "the fastest knobs", "AHD, a timed hold (HOLD 4)"]
QUICK_BLOCKS = 120


def run_case(knobs, events, frames, digikit, image):
    import sharc_waverider_m5 as m5
    import stock_units_measure as SU
    from dnfw.waverider import frame as FR
    from dnfw.waverider import voice as V

    class A:
        pass
    A.digikit, A.image = digikit, image
    dk, stock, sound, machines, img = SU._setup(A)
    levels, cur = [], [0]

    def after_amp(r):
        if len(levels) == cur[0]:
            levels.append(-V.bits_f32(m5.m2.word(r.state, LEVEL) or 0))
    with tempfile.TemporaryDirectory() as tmp:
        snap, m2mach = m5.snapshot_path(dk, stock, pathlib.Path(tmp))
        init = m5.init_on(snap, m2mach, img)

        def frames_of(b):
            cur[0] = b
            while len(levels) < b:
                levels.append(None)
            prime = (0, 127, 0, 127, 0, 1, 1)       # ATK 0, SUS 127, REL 0, ADSR, RSET 1
            ev = {0: "on", 1: "off"}.get(b) if b < PRIME else events.get(b - PRIME)
            f = m5.base_frame(sound, machines, t0=SU.WAVETONE, note=60 << 8, trigger=(ev == "on"), overrides=SU.STEADY)
            f.header(FR.FILTER, 0, SU.NO_FILTER)
            for slot, k in zip(SLOT, prime if b < PRIME else knobs):
                f.param(0, slot, k << 8)
            if ev == "off":
                f.trigger(0, masks=(OFF_MASK,))
            return f.to_bytes()
        r = m5.run_blocks(init, frames_of, PRIME + frames + 1, extra_hooks={m5.AMP_RETURN: after_amp})
    if not r["ok"]:
        return None, r.get("halt")
    return levels[PRIME:PRIME + frames + 1], levels[PRIME - 1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--image", type=pathlib.Path, default=pathlib.Path(os.environ.get("DT2_SYX", "")))
    p.add_argument("--digikit", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("DNFW_DIGIKIT_SHARC", HERE.parent.parent / "digikit-wt-sharcemu")))
    p.add_argument("--case", action="append", default=None)
    p.add_argument("--part", default="1/1", help="N/M: every M-th case from the N-th (a long run in pieces)")
    p.add_argument("--quick", action="store_true", help="the gate's run: QUICK's cases, their first QUICK_BLOCKS blocks")
    p.add_argument("--json", default=None)
    p.add_argument("--dump", action="store_true", help="every block: the DSP's level and the clone's")
    a = p.parse_args()
    import test_matrix_c as T
    report, fails = {}, []
    n, m = (int(x) for x in a.part.split("/"))
    for name in (a.case or (QUICK if a.quick else sorted(T.CASES)[n - 1::m])):
        knobs, events, frames = T.CASES[name]
        if a.quick:
            frames = min(frames, QUICK_BLOCKS)
        dsp, rest = run_case(knobs, events, frames, a.digikit, a.image)
        if dsp is None:
            fails.append(f"{name}: the runner halted ({rest})")
            continue
        if rest is None or abs(rest) > 1e-12:
            fails.append(f"{name}: not at rest after the priming note ({rest})")
        clone = [x / FULL for x in T.model(knobs, events, frames)]
        if a.dump:
            print(json.dumps({"case": name, "dsp": [None if d is None else round(d, 6) for d in dsp[1:]],
                              "clone": [round(c, 6) for c in clone]}), flush=True)
        worst, at, lagged = 0.0, None, 0
        for b in range(frames):
            err = abs(clone[b] - dsp[b + 1])                # the DSP's next block (see above)
            if err > TOL:
                near = [dsp[j] for j in (b, b + 2) if j <= frames and dsp[j] is not None]
                err = min([err] + [abs(clone[b] - d) for d in near])
                lagged += err <= TOL
            if err > worst:
                worst, at = err, b
        same = sum(1 for b in range(frames) if abs(clone[b] - dsp[b + 1]) <= TOL)
        report[name] = {"blocks": frames, "worst": worst, "at": at, "next_block": same, "stage_end_lag": lagged}
        print(f"  {'ok  ' if worst <= TOL else 'FAIL'}  {name}: worst {worst:.2e} at block {at}; {same}/{frames} "
              f"blocks within {TOL} of the DSP's next one, {lagged} more one block off at a stage's end", flush=True)
        if worst > TOL:
            fails.append(name)
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=1))
    print(("FAIL: " + "; ".join(fails)) if fails else f"PASS: the clone within {TOL} of stock's AMP envelope, "
          f"{len(report)} cases")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
