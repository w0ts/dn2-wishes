"""The sample link's block (csrc/sampler/link.c smp_tdm) on two builds, byte for byte (2026-11-21, claude/cf-asm: its
packet write).

    emu_tdm_ab.py --a A.syx --syma A_code.json --b B.syx --snapshot S [--blocks N] [--seeds 1,2]

Run from build B's tree. Both builds from the same set-up (all 32 insert records on, the READY page's tables: smp_tables
2), then blocks of smp_tdm(H), H 0 or 1 at random; before a block, at random: commands queued (smp_command), TAPE's
PGAIN changed (ins_tpg_gen), a track's trig with insert locks (ins_trig), the AMP ON/OFF mask changed (as_mask), a
blank burst asked (smp_blank_req), a page job started (link.c job_start: the words from STAGE(0) 0x46b10000, sent
in chunks, little-endian). After each block the transmit half H (2 KB, every unit and the sum), the receive
side untouched, and the link's counters must be the same in A and B. Prints smp_tdm's instructions: a block that sends
a packet and one that does not (worst and mean)."""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import struct
import sys

TREE = pathlib.Path.cwd()
sys.path.insert(0, str(TREE / "scripts"))
sys.path.insert(0, str(TREE / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import emu_matrix as MX                 # noqa: E402
import emu_insframe_ab as IA            # noqa: E402

TX = 0x4E6E8100
STATE = ("smp_tdm_sent", "smp_blank_sent", "ins_pkts", "ins_chg", "ins_rr", "ins_due", "as_sent", "smp_rt_sent")


class Run:
    def __init__(self, build, snap, sym, seed, jobs_only=False):
        self.sym, self.rng, self.jobs_only = sym, random.Random(seed), jobs_only
        m = self.m = MX.setup(build, snap)
        MX.ins_load(m, sym, IA.records(self.rng))
        m.write(sym["smp_tables"], struct.pack(">i", 2))
        m.write(TX, bytes(0x1000))
        m.flush()
        self.lk = m.alloc(16)
        self.sent, self.idle, self.jobs = [], [], 0

    def block(self, b):
        m, rng, sym = self.m, self.rng, self.sym
        r = rng.random()
        if self.jobs_only:                              # (--jobs) only page jobs: their chunks go out when nothing else is due
            r = 0.24 if r < 0.05 else 1.0
        if r < 0.08:
            for _ in range(rng.choice([1, 1, 3])):
                m.call(sym["smp_command"], rng.randrange(1, 12), rng.getrandbits(16), rng.getrandbits(16), 0, 0)
        elif r < 0.12:
            m.write(sym["ins_tpg_gen"], struct.pack(">I", (m.long(sym["ins_tpg_gen"]) + 1) & 0xFFFFFFFF))
        elif r < 0.2:
            m.write(self.lk, struct.pack(">7H", *[rng.choice([0xFFFF, rng.randrange(0x8080) & 0x7F7F]) for _ in range(7)]))
            m.flush()
            m.call(sym["ins_trig"], rng.randrange(16), self.lk)
        elif r < 0.22 and "as_mask" in sym:
            m.write(sym["as_mask"], struct.pack(">I", rng.getrandbits(16)))
        elif r < 0.25 and "job_start.constprop.0" in sym:
            n = rng.choice([4, 64, 496, 4 * rng.randrange(1, 600)])   # a page job (sample data): its words go out
            m.write(0x46B10000, bytes(rng.getrandbits(8) for _ in range(n)))   # in chunks over the next blocks (le32)
            m.call(sym["job_start.constprop.0"], 0x2000 + 4 * rng.randrange(64), n)
        elif r < 0.26 and "smp_blank_req" in sym:
            m.write(sym["smp_blank_req"], struct.pack(">I", (m.long(sym["smp_blank_req"]) + 1) & 0xFFFFFFFF))
        m.flush()
        h = rng.randrange(2)
        before = m.long(sym["smp_tdm_sent"])
        _, n = m.cost(sym["smp_tdm"], h)
        (self.sent if m.long(sym["smp_tdm_sent"]) != before else self.idle).append(n)
        if m.long(sym["smp_tdm_sent"]) != before:          # a page job's chunk: its offset (unit 2) in the job's span
            off = struct.unpack(">I", m.read(TX + (h << 11) + 4 * 10, 4))[0] & 0xFFFF
            self.jobs += 0x800 <= off < 0x800 + 64 + 600
        out = [bytes(m.read(TX, 0x1000))]
        out += [bytes(m.read(sym[s], 4)) for s in STATE if s in sym]
        return out


def stats(xs):
    return f"worst {max(xs)} mean {sum(xs) / len(xs):.0f} ({len(xs)})" if xs else "none"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--syma", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--blocks", type=int, default=600)
    p.add_argument("--seeds", default="1,2")
    p.add_argument("--jobs", action="store_true", help="only page jobs (their le32 path)")
    a = p.parse_args()
    def syms(path):
        d = json.loads(pathlib.Path(path).read_text())
        return {**d.get("c_text_symbols", {}), **d["layout"]}
    sym = syms(TREE / "src/dnfw/mods/waverider_code.json")
    syma = syms(a.syma)
    bad = 0
    for seed in [int(x) for x in a.seeds.split(",")]:
        ra, rb = Run(a.a, a.snapshot, syma, seed, a.jobs), Run(a.b, a.snapshot, sym, seed, a.jobs)
        first = None
        for b in range(a.blocks):
            x, y = ra.block(b), rb.block(b)
            if x != y and first is None:
                k = next(i for i in range(len(x)) if x[i] != y[i])
                first = (b, "transmit halves" if k == 0 else STATE[k - 1])
        for lab, r in (("A", ra), ("B", rb)):
            print(f"seed {seed} {lab}: smp_tdm sending {stats(r.sent)}; not sending {stats(r.idle)}; page job chunks "
                  f"{r.jobs}", flush=True)
        print(f"seed {seed}: {a.blocks} blocks, " + ("the same" if first is None else f"DIFFER first at {first}"),
              flush=True)
        bad += first is not None
        del ra, rb
    print("PASS: the same bytes every block" if not bad else f"FAIL: {bad} seeds differ")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
