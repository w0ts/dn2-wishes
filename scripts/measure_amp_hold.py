"""Stock 1.12's AMP envelope HOLD (AHD) in Elektron's own DSP code (the SHARC runner, section 7): how many samples
each HOLD knob holds full scale before the fall (docs/matrix.md, csrc/matrix/amp_env.json "hold_blocks").

    DT2_SECTIONS=../sec112 python scripts/measure_amp_hold.py --image STOCK.syx probe [--hold 64] [--blocks 8]
    DT2_SECTIONS=../sec112 python scripts/measure_amp_hold.py --image STOCK.syx fall --hold 3 [--blocks 400]

probe: track 0 on WaveTone (as scripts/sharc_matrix_env.py), a note at ATK 0, HOLD k, DEC 35, SUS 0, AHD, RSET 1, no
note-off; after each block's amp stage the words around the level word (0x2547c8) are printed, so the hold's own
counter can be told apart (a word that steps by the same amount every block while the level holds full scale).
fall: the level after every block until it falls (the hold's length to a block, then to the sample from the fall's
known ratio, as amp_env.json measured HOLD 0)."""

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
SLOT = (81, 82, 83, 84, 85, 91, 92)             # ATK HOLD DEC SUS REL MODE RSET in the frame
PRIME = 4


def run(knobs, blocks, digikit, image, lo, hi):
    """-> per block after the amp stage: {address: word} for LO..HI (step 4), the note on at block PRIME"""
    import sharc_waverider_m5 as m5
    import stock_units_measure as SU
    from dnfw.waverider import frame as FR

    class A:
        pass
    A.digikit, A.image = digikit, image
    dk, stock, sound, machines, img = SU._setup(A)
    seen, cur = [], [0]

    def after_amp(r):
        if len(seen) == cur[0]:
            seen.append({ad: m5.m2.word(r.state, ad) for ad in range(lo, hi, 4)})
    with tempfile.TemporaryDirectory() as tmp:
        snap, m2mach = m5.snapshot_path(dk, stock, pathlib.Path(tmp))
        init = m5.init_on(snap, m2mach, img)

        def frames_of(b):
            cur[0] = b
            while len(seen) < b:
                seen.append(None)
            prime = (0, 127, 0, 127, 0, 1, 1)
            ev = {0: "on", 1: "off"}.get(b) if b < PRIME else ("on" if b == PRIME else None)
            f = m5.base_frame(sound, machines, t0=SU.WAVETONE, note=60 << 8, trigger=(ev == "on"), overrides=SU.STEADY)
            f.header(FR.FILTER, 0, SU.NO_FILTER)
            for slot, k in zip(SLOT, prime if b < PRIME else knobs):
                f.param(0, slot, k << 8)
            if ev == "off":
                f.trigger(0, masks=(36,))
            return f.to_bytes()
        r = m5.run_blocks(init, frames_of, PRIME + blocks + 1, extra_hooks={m5.AMP_RETURN: after_amp})
    return seen[PRIME:] if r["ok"] else None


HOLD_WORDS = {0x2547B8: 1, 0x2547BC: 3}          # the envelope's state words while it holds (read in "probe": HOLD 32, 64)
COUNTER = 0x2547C4                              # the samples since the hold began (32 a block)
FULL_NEG = 0xBF800000                           # the level word at full scale (the negated level, -1.0)


def search(knob, steps, digikit, image, r35):
    """HOLD KNOB's length in samples: each block after the note-on starts again in the hold at full scale with the
    hold's counter poked to a trial value C (the DSP's own state words, as it holds them); the block's level says
    whether the hold ran out inside it (a fall of n samples: the hold is C + 32 - n), after it, or before it.
    A binary search over C; -> (samples, trials) or (None, trials) when STEPS were not enough"""
    import math
    import sharc_waverider_m5 as m5
    import stock_units_measure as SU
    from dnfw.waverider import frame as FR
    from dnfw.waverider import voice as V

    class A:
        pass
    A.digikit, A.image = digikit, image
    dk, stock, sound, machines, img = SU._setup(A)
    st = {"lo": 0, "hi": 1 << 27, "c": None, "found": None, "trials": [], "b": 0}
    lr = math.log(r35)

    def poke_next(r):
        for ad, w in HOLD_WORDS.items():
            m5.m2.poke(r.state, ad, w)
        m5.m2.poke(r.state, 0x2547C8, FULL_NEG)
        c = (st["lo"] + st["hi"]) // 2
        st["c"] = c
        m5.m2.poke(r.state, COUNTER, c)

    def after_amp(r):
        b = st["b"]
        if b < PRIME + 1 or st["found"] is not None or st.get("seen") == b:
            return
        st["seen"] = b                                  # the amp returns once a track: track 0's, the block's first
        if st["c"] is not None:
            lev = -V.bits_f32(m5.m2.word(r.state, 0x2547C8) or 0)
            n = 0 if lev >= 0.9999999 else round(math.log(max(lev, 1e-30)) / lr)
            st["trials"].append((st["c"], n))
            if n == 0:
                st["lo"] = st["c"] + 32
            elif n >= 32:
                st["hi"] = st["c"]
            else:
                st["found"] = st["c"] + 32 - n
                return
            if st["hi"] <= st["lo"]:
                st["found"] = st["lo"]
                return
        st["poke"] = True                               # the next block's dispatch (before its amp stage) pokes

    def at_dispatch(r):
        if st.get("poke"):
            st["poke"] = False
            poke_next(r)
    with tempfile.TemporaryDirectory() as tmp:
        snap, m2mach = m5.snapshot_path(dk, stock, pathlib.Path(tmp))
        init = m5.init_on(snap, m2mach, img)

        def frames_of(b):
            st["b"] = b
            prime = (0, 127, 0, 127, 0, 1, 1)
            knobs = (0, knob, 35, 0, 0, 0, 1)
            ev = {0: "on", 1: "off"}.get(b) if b < PRIME else ("on" if b == PRIME else None)
            f = m5.base_frame(sound, machines, t0=SU.WAVETONE, note=60 << 8, trigger=(ev == "on"), overrides=SU.STEADY)
            f.header(FR.FILTER, 0, SU.NO_FILTER)
            for slot, k in zip(SLOT, prime if b < PRIME else knobs):
                f.param(0, slot, k << 8)
            if ev == "off":
                f.trigger(0, masks=(36,))
            return f.to_bytes()
        import sharc_waverider_m3 as m3
        m5.run_blocks(init, frames_of, PRIME + 2 + steps, extra_hooks={m5.AMP_RETURN: after_amp, m3.DISPATCH: at_dispatch})
    return st["found"], st["trials"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("what", choices=("probe", "fall", "dump", "search"))
    p.add_argument("--image", type=pathlib.Path, default=pathlib.Path(os.environ.get("DT2_SYX", "")))
    p.add_argument("--digikit", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("DNFW_DIGIKIT_SHARC", HERE.parent.parent / "digikit-wt-sharcemu")))
    p.add_argument("--hold", type=int, action="append", default=None)
    p.add_argument("--blocks", type=int, default=8)
    p.add_argument("--lo", type=lambda x: int(x, 0), default=LEVEL - 0x80)
    p.add_argument("--hi", type=lambda x: int(x, 0), default=LEVEL + 0x80)
    p.add_argument("--json", default=None)
    p.add_argument("--steps", type=int, default=30)
    a = p.parse_args()
    if a.what == "search":
        r35 = json.loads((HERE.parent / "csrc/matrix/amp_env.json").read_text())["dec_ratio"]["per_block"][35] ** (1 / 32)
        for h in a.hold or [4]:
            found, trials = search(h, a.steps, a.digikit, a.image, r35)
            print(json.dumps({"hold": h, "samples": found, "trials": trials}), flush=True)
        return 0
    from dnfw.waverider import voice as V
    out = {}
    for h in a.hold or [64]:
        knobs = (0, h, 35, 0, 0, 0, 1)
        lo, hi = (a.lo, a.hi) if a.what in ("probe", "dump") else (LEVEL, LEVEL + 4)
        seen = run(knobs, a.blocks, a.digikit, a.image, lo, hi)
        if seen is None:
            print(f"HOLD {h}: the runner halted", flush=True)
            continue
        if a.what == "dump":
            last = seen[min(2, len(seen) - 1)] or {}
            print(json.dumps({"hold": h, "block2": {f"{ad:#x}": last.get(ad) for ad in range(lo, hi, 4)}}), flush=True)
            out[h] = last
        elif a.what == "probe":
            rows = {}
            for ad in range(lo, hi, 4):
                ws = [s.get(ad) if s else None for s in seen]
                if len(set(ws)) > 1:
                    rows[f"{ad:#x}"] = [None if w is None else f"{w:#010x}" for w in ws]
            print(json.dumps({"hold": h, "changing": rows}), flush=True)
            out[h] = rows
        else:
            lev = [None if not s else -V.bits_f32(s.get(LEVEL) or 0) for s in seen]
            out[h] = lev
            full = next((b for b, x in enumerate(lev) if x is not None and x >= 0.999999), None)
            first = next((b for b, x in enumerate(lev) if full is not None and b > full and x is not None
                          and x < 0.999999), None)
            print(json.dumps({"hold": h, "full_at": full, "first_block_below_full": first,
                              "levels": [None if x is None else round(x, 9) for x in lev]}), flush=True)
    if a.json:
        pathlib.Path(a.json).resolve().write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
