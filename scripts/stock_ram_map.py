"""The RAM stock OS 1.12 writes, measured (2026-11-16): boot from reset and a stock UI walk.

    DT2_SECTIONS=../sec112 python scripts/stock_ram_map.py STOCK_MAIN_OS.bin --snapshot SNAP \\
        --cards none,CARD.img --seeds 1-6 --out src/dnfw/mods/stock112_writes.json

Each run is an ordinary emulator script under the write map (emulib/writemap.py, DNFW_WRITEMAP) with
the DDR's uncached alias mapped as on the instrument (DNFW_DDR_ALIAS=1):

- `scripts/emu_boot_check.py` on stock's MAIN OS from reset, once per card: a blank +Drive, and a
  card whose active-project header is valid (scripts/drive_card.py), so stock reads its project
  record through the +Drive bounce buffer as a unit with a project does;
- `scripts/emu_waverider_menu.py --stock` from the snapshot, one random walk of stock keys a seed
  (pages, arrows, YES/NO, FUNC menus, trig keys, PLAY, KEYBOARD), the audio interrupt at its rate.

The union of the 256-byte blocks written (CPU, the uncached alias, the emulator's DMA) between
writemap.LO and writemap.HI is written to --out with what made it. dnfw.mods.ramcheck holds every chunk
of ours out of it (test/test_ram_112.py, the gate's `rammap` step).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emulib import writemap                                   # noqa: E402


def walk(seed: int, n: int) -> str:
    """A random walk of stock's own keys (no pokes, no calls: nothing of ours)."""
    rnd = random.Random(seed)
    acts = [
        (6, lambda: [rnd.choice(("up", "down"))]),
        (5, lambda: ["yes"]),
        (5, lambda: ["no"]),
        (3, lambda: ["right"]),
        (3, lambda: ["left"]),
        (4, lambda: [f"tap:{rnd.choice((1, 2, 3, 4, 5))}"]),                    # TRIG, SYN, FLTR, AMP, FX
        (3, lambda: [f"press:{25 + rnd.randrange(16)}", "wait:3", f"release:{25 + rnd.randrange(16)}"]),
        (2, lambda: ["press:17", "wait:2", rnd.choice(("yes", "no", "up", "down")), "wait:2", "release:17"]),
        (1, lambda: ["func-src", "wait:20", rnd.choice(("no", "down", "up")), "wait:4", rnd.choice(("no", "yes"))]),
        (1, lambda: ["tap:20"]),                                                # PLAY
        (1, lambda: ["tap:18"]),                                                # KEYBOARD
        (2, lambda: [f"turn:{rnd.randrange(8)}:{rnd.choice((-3, -1, 1, 3))}"]),
        (3, lambda: [f"wait:{rnd.choice((1, 2, 4))}"]),
    ]
    st = ["wait:2"]
    for _ in range(n):
        st += rnd.choices([f for _w, f in acts], [w for w, _ in acts])[0]()
        st.append(f"wait:{rnd.choice((1, 2, 3))}")
    return ",".join(st)


def run(cmd: list[str], env: dict, log: pathlib.Path) -> tuple[int, float]:
    t = time.time()
    with open(log, "w") as f:
        rc = subprocess.call(cmd, env=env, stdout=f, stderr=subprocess.STDOUT, cwd=HERE.parent)
    return rc, time.time() - t


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stock_main", help="stock 1.12's section_3_MAIN_OS.bin")
    p.add_argument("--snapshot", required=True, help="a stock 1.12 UI snapshot (ui800M)")
    p.add_argument("--cards", default="none", help="comma list: none (blank) or +Drive image paths")
    p.add_argument("--seeds", default="1-4")
    p.add_argument("--steps", type=int, default=40)
    p.add_argument("--work", type=pathlib.Path, required=True)
    p.add_argument("--out", type=pathlib.Path, required=True)
    p.add_argument("--boot-limit", type=int, default=700_000_000)
    p.add_argument("--keep", action="store_true", help="add to WORK's earlier record instead of starting anew")
    a = p.parse_args()

    a.work.mkdir(parents=True, exist_ok=True)
    rec = a.work / "writemap.jsonl"
    if not a.keep:
        rec.unlink(missing_ok=True)
    py = sys.executable
    base_env = {**os.environ, "DNFW_DDR_ALIAS": "1", "DNFW_WRITEMAP": str(rec),
                "DNFW_EMU_FLAGS": '{"weakptr": false}',     # as the gate's snapshot steps (ship_gate EMU_ENV)
                "PYTHONPATH": os.pathsep.join([str(HERE / "gate_trace"), str(HERE.parent / "src"),
                                               os.environ.get("PYTHONPATH", "")])}
    lo, hi = (int(x) for x in a.seeds.split("-")) if "-" in a.seeds else (int(a.seeds), int(a.seeds))
    runs = []
    bdir = a.work / "stock"
    bdir.mkdir(exist_ok=True)
    (bdir / "section_3_MAIN_OS.bin").write_bytes(pathlib.Path(a.stock_main).read_bytes())
    for card in [c for c in a.cards.split(",") if c]:
        env = dict(base_env)
        if card != "none":
            env["DNFW_CARD_IMAGE"] = card
        name = f"boot-{'blank' if card == 'none' else pathlib.Path(card).stem}"
        rc, sec = run([py, "-u", "scripts/emu_boot_check.py", str(bdir / "section_3_MAIN_OS.bin"),
                       "--limit", str(a.boot_limit)], env, a.work / f"{name}.log")
        runs.append({"run": name, "rc": rc, "seconds": round(sec)})
        print(runs[-1], flush=True)
    for seed in range(lo, hi + 1):
        rc, sec = run([py, "-u", "scripts/emu_waverider_menu.py", "--stock", "--build", str(bdir),
                       "--snapshot", a.snapshot, "--isr-frame", "75000", "--steps", walk(seed, a.steps)],
                      base_env, a.work / f"walk-{seed}.log")
        runs.append({"run": f"walk-{seed}", "rc": rc, "seconds": round(sec)})
        print(runs[-1], flush=True)

    blocks: dict[str, list] = {}
    procs = 0
    for line in rec.read_text().splitlines():
        procs += 1
        for b, r in json.loads(line)["blocks"].items():
            m = blocks.setdefault(b, [0, 0, 0, r[3]])
            for k in range(3):
                m[k] += r[k]
    ranges = []
    for b in sorted(int(x, 16) for x in blocks):
        if ranges and ranges[-1][1] == b:
            ranges[-1][1] = b + writemap.BLOCK
        else:
            ranges.append([b, b + writemap.BLOCK])
    out = {"what": "the RAM stock Digitone II OS 1.12 writes between "
                   f"{writemap.LO:#010x} and {writemap.HI:#010x} (256-byte blocks), measured by "
                   "scripts/stock_ram_map.py", "measured": time.strftime("%Y-%m-%d"),
           "runs": runs, "processes": procs,
           "ranges": [[f"{x:#010x}", f"{y:#010x}"] for x, y in ranges],
           "blocks": blocks}
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(blocks)} blocks in {len(ranges)} ranges: " + ", ".join(f"{x:#x}..{y:#x}" for x, y in ranges[:20]))
    return 0 if all(r["rc"] in (0, 1) for r in runs) else 2


if __name__ == "__main__":
    sys.exit(main())
