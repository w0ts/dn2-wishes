"""2026-11-21 (eng-simd): the Monomachine-style machines (FM+ STAT / PAR / DYN, DENS, DDRW, WAVE, SID, VO6) re-coded
must give the same floats, bit for bit. The golden runs
(MNM_GOLDEN) are not on every host, so the cases here are made from a fixed seed: notes over the keyboard (the
increment A), knobs at their ends, middles and at random, changed mid-note, retriggers. Each run records its output
words and the machine's state words after every block (sha256), and the instructions a block (bench.Bench, the
model the SHARC runner holds the DSP to).

    python scripts/fm_identity.py record OUT.json      # before the re-code
    python scripts/fm_identity.py check REF.json       # after: every run identical
    python scripts/fm_identity.py check REF.json DENS,DDRW   # these machines only (while working)
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dnfw.md import core as K       # noqa: E402
from dnfw.mnm import bench, ddrw, dens, fm, sid, vo6, wave      # noqa: E402

MACHINES = {"FMSTAT": fm.Stat, "FMPAR": fm.Par, "FMDYN": fm.Dyn, "DENS": dens, "DDRW": ddrw, "WAVE": wave, "SID": sid,
            "VO6": vo6}
CASES, BLOCKS = 24, 40


def cases(name: str) -> list[dict]:
    rnd = random.Random(f"fm_identity/{name}")
    out = []
    for n in range(CASES):
        a0 = int(2 ** rnd.uniform(18.0, 27.5))               # the note's increment, low to high
        knobs = {0: [rnd.choice((0, 64, 127, rnd.randrange(128))) for _ in range(8)]}
        if n == 0:
            knobs[0] = [127] * 8
        elif n == 1:
            knobs[0] = [0] * 8
        for blk in rnd.sample(range(2, BLOCKS), 3):
            knobs[blk] = [rnd.randrange(128) for _ in range(8)]
        trig = {0} | set(rnd.sample(range(5, BLOCKS), 2))
        glide = rnd.random() < 0.5
        A = [int(a0 * (1.0 + (0.002 * b if glide else 0.0))) for b in range(BLOCKS)]
        out.append({"A": A, "knobs": knobs, "trig": trig})
    return out


def run_all() -> dict:
    res = {}
    for name, M in MACHINES.items():
        per, steps, blocks = {}, 0, 0
        for k, c in enumerate(cases(name)):
            b = bench.Bench(M)
            h = hashlib.sha256()
            NW = getattr(M, "N", 48)
            for blk in range(BLOCKS):
                out = b.block(c["A"][blk], 0, c["knobs"].get(blk), blk in c["trig"])
                h.update(b"".join(struct.pack("<f", x) for x in out))
                st = b.L.md.state + 4 * K.S0
                h.update(b"".join(struct.pack("<I", b.mem.get(st + 4 * w) & 0xFFFFFFFF) for w in range(NW)))
                steps += b.steps
                blocks += 1
            per[str(k)] = h.hexdigest()
        res[name] = {"cases": per, "steps_a_block": steps / blocks}
        print(f"{name}: {len(per)} runs, {steps / blocks:.1f} instructions a block", flush=True)
    return res


def main() -> int:
    mode, path = sys.argv[1], pathlib.Path(sys.argv[2])
    if len(sys.argv) > 3:
        for n in [n for n in MACHINES if n not in sys.argv[3].split(",")]:
            del MACHINES[n]
    res = run_all()
    if mode == "record":
        path.write_text(json.dumps(res, indent=1))
        print(f"recorded {path}")
        return 0
    ref = json.loads(path.read_text())
    bad = [] if set(res) <= set(ref) else ["machines missing from the reference"]
    bad += [f"{n} {c}" for n, r in res.items() for c, h in r["cases"].items() if ref[n]["cases"].get(c) != h]
    for n, r in res.items():
        print(f"{n}: {ref[n]['steps_a_block']:.1f} -> {r['steps_a_block']:.1f} instructions a block")
    print(("PASS" if not bad else "FAIL") + f": {sum(len(r['cases']) for r in res.values())} runs, {len(bad)} differ "
          + " ".join(bad[:10]))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
