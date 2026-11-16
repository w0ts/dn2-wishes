"""2026-11-13: every Machinedrum machine (TRX, EFM, GND, P-I) must render word for word as the reference source
does (upstream's v0.52 tree: test/data/md_source_v052.json). (md_identity.py, v0.42, holds a re-code to the
golden cases' runs, which need MD_GOLDEN; this one needs only the OS and a reference recorded from source.) A merge that keeps one side's helper and the other
side's caller (v0.52's float TRX filters reading the perf pass's integer coefficients: TRX-CY silent) changes the
output, and nothing else catches it before a build.

Each machine runs in run mode (dnfw.perc.live.Harness: the PERC voice, the model the SHARC runner holds the DSP to,
bit for bit), one voice: at its default knobs, then in variants whose knobs move to random and extreme positions
mid-note (a fixed seed a machine), notes and retriggers on a fixed schedule. Each run's output float words are
hashed (sha256) and its peak kept.

    python scripts/md_source_identity.py record OUT.json [NAME..]   # in the reference tree (git archive v0.52)
    python scripts/md_source_identity.py check REF.json [NAME..]    # here: exit 0 and PASS when every run is identical

Needs MD_OS_BIN and DT2_SECTIONS, as the build does.
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

RUNS = 3                        # the defaults, then two variants
BLOCKS = 64
NOTES = (36, 48, 60, 72)


def machines() -> list[str]:
    from dnfw.md import voice as MDV
    return [m.NAME for m in MDV.MM.MACHINES]


def run(name: str, s: int) -> dict:
    """one run: {'hash', 'peak'}"""
    from dnfw.md import core as MDK, voice as MDV
    from dnfw.perc import live as PL
    k = machines().index(name)
    rnd = random.Random(f"{name}/{s}")
    h = PL.Harness()
    h.words[h.L.md.C["fill"]] = MDK.Z_N
    d = PL.defaults(name)

    def knobs():
        return [rnd.choice((0.0, 1.0, rnd.random(), rnd.random())) for _ in d]
    h.set_controls(k, d if s == 0 else knobs())
    H, peak = hashlib.sha256(), 0.0
    for b in range(BLOCKS):
        if s and b and rnd.random() < 0.06:
            h.set_controls(k, knobs())
        out = h.block(note=float(rnd.choice(NOTES)), trig=b == 0 or rnd.random() < 0.08)
        H.update(struct.pack("<32f", *out))
        peak = max(peak, max(abs(x) for x in out))
    return {"hash": H.hexdigest(), "peak": round(peak, 6)}


def record(names: list[str]) -> dict:
    return {n: [run(n, s) for s in range(RUNS)] for n in names}


def check(ref: dict, names: list[str]) -> list[str]:
    """the differing runs, as text (empty: identical)"""
    bad = []
    for n in names:
        if n not in ref:
            bad.append(f"{n}: not in the reference")
            continue
        for s, want in enumerate(ref[n]):
            got = run(n, s)
            if got["hash"] != want["hash"]:
                bad.append(f"{n} run {s}: output differs (peak {got['peak']} against {want['peak']})")
    return bad


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("record", "check"):
        print(__doc__)
        return 2
    path = pathlib.Path(argv[1])
    names = argv[2:] or machines()
    if argv[0] == "record":
        path.write_text(json.dumps({"runs": RUNS, "blocks": BLOCKS, "machines": record(names)}, indent=1) + "\n")
        print(f"recorded {len(names)} machines into {path}")
        return 0
    ref = json.loads(path.read_text())["machines"]
    bad = check(ref, names)
    for b in bad:
        print(b)
    print("PASS" if not bad else f"FAIL: {len(bad)} runs differ")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
