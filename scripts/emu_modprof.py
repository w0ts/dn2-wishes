"""Profile the modulation engine's frame work at its worst case on the ColdFire emulator (read-only measurement):
sm_fast (via stock's smoother entry), mods_fast (MOD SETUP pass), mod_eval (mod_eval_pre, lh_args, lfo_fast, mx_eval).

    modprof.py --build BUILD.syx --snapshot SNAP --out OUT.json [--sweep]

Per call: instructions, by function (the build's layout symbols, stock ranges by 0x...), memory reads and writes by
region, the hottest PCs with their disassembly. --sweep first runs every WAVE x MODE for all LFOs to find the worst."""
from __future__ import annotations

import argparse
import bisect
import collections
import gc
import json
import pathlib
import struct
import sys

TREE = pathlib.Path.cwd()
sys.path.insert(0, str(TREE / "scripts"))
sys.path.insert(0, str(TREE / "src"))
import emu_matrix as MX                 # noqa: E402
import emu_modulation as MO             # noqa: E402

MODS_PASS = 0x400DB390
import os
WORST_DESTS = tuple(int(x) for x in os.environ.get("MP_DESTS", "17,18,9").split(","))               # LFO1 -> LFO3 SPD, LFO2 -> LFO3 MULT, LFO3 -> LFO2 SPD (emu_modulation worst)


def region(a):
    if 0x80000000 <= a < 0x80010000:
        return "sram 0x8000xxxx"
    if 0x40000000 <= a < 0x40300000:
        return "image 0x40xxxxxx"
    if 0x44000000 <= a < 0x46000000:
        return "ddr 0x44-0x45"
    if 0x46000000 <= a < 0x46A00000:
        return "ddr 0x46 (ours)"
    if 0x46A00000 <= a < 0x46A10000:
        return "stack"
    if 0x47000000 <= a < 0x48000000:
        return "ddr 0x47 (wishes)"
    return f"other {a >> 24:#x}"


class Prof:
    def __init__(self, m, sym):
        self.m, self.sym = m, sym
        items = sorted((v, k) for k, v in sym.items() if isinstance(v, int) and v >= 0x40000000)
        self.addrs = [a for a, _ in items]
        self.names = [n for _, n in items]

    def fn(self, pc):
        if 0x40000400 <= pc < 0x40300000 and not (self.addrs and self.addrs[0] <= pc):
            return f"stock_{pc & ~0xff:#x}"
        i = bisect.bisect_right(self.addrs, pc) - 1
        if i < 0:
            return f"stock_{pc & ~0xff:#x}"
        if pc - self.addrs[i] > 0x4000:
            return f"?{pc & ~0xfff:#x}"
        return self.names[i]

    def run(self, fn, *args):
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
        pcs = collections.Counter()
        rd, wr = collections.Counter(), collections.Counter()

        def code(uc, a, s, u):
            pcs[a] += 1

        def mr(uc, acc, a, s, v, u):
            rd[region(a)] += 1

        def mw(uc, acc, a, s, v, u):
            wr[region(a)] += 1
        h = [self.m.uc.hook_add(UC_HOOK_CODE, code), self.m.uc.hook_add(UC_HOOK_MEM_READ, mr),
             self.m.uc.hook_add(UC_HOOK_MEM_WRITE, mw)]
        try:
            self.m.call(fn, *args, limit=4_000_000)
        finally:
            for x in h:
                self.m.uc.hook_del(x)
        return pcs, rd, wr

    def report(self, pcs, rd, wr, top=40):
        byfn = collections.Counter()
        for pc, n in pcs.items():
            byfn[self.fn(pc)] += n
        hot = []
        try:
            import capstone
            cs = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_M68K_040)
        except Exception:
            cs = None
        for pc, n in pcs.most_common(top):
            b = bytes(self.m.read(pc, 10))
            txt = b[:6].hex()
            if cs:
                d = next(cs.disasm(b, pc), None)
                if d:
                    txt = f"{d.mnemonic} {d.op_str}"
            hot.append({"pc": f"{pc:#x}", "fn": self.fn(pc), "n": n, "insn": txt})
        return {"instructions": sum(pcs.values()), "by_function": dict(byfn.most_common()),
                "reads": dict(rd), "writes": dict(wr), "hot": hot,
                "pcs": {f"{k:#x}": v for k, v in sorted(pcs.items())}}


def configure(m, sym, wave, mode, routes):
    for v in range(16):
        m.write(MX.VSOUND + 4 * v, struct.pack(">I", MX.sound(m, v)))
        for k, d in zip((1, 2, 3), WORST_DESTS):
            for f, val in (("SPD", 0x7000 + 0x100 * v), ("MULT", 23 << 8), ("FADE", 0x2000), ("DEST", d << 8),
                           ("WAVE", wave << 8), ("SPH", 0x4000), ("MODE", mode << 8), ("DEP", MX.ATT_FULL)):
                MX.set_cell(m, v, MO.slot(k, f), val)
        if routes:
            r = MX.put_routes(m, sym, v, [(k % 3, 25 + 3 * k, 0x5000 + 0x100 * k) for k in range(MX.LFO)]
                              + [(3 + k // 4, 70 + k, 0x3000 + 0x200 * k) for k in range(8)])
            if r:
                raise SystemExit(f"routes on track {v}: {r:#x}")
    m.flush()
    m.call(sym["mx_poll"])


def frame_total(m, sym, frames, prof=None):
    rate = m.long(MO.RATE)
    o1, o2 = m.alloc(256), m.alloc(256)
    worst = None
    for f in range(frames):
        if prof is None:
            _, a = m.cost(MO.SMOOTHER, MO.SRC)
            _, b = m.cost(MODS_PASS, MO.OUT)
            _, c = m.cost(sym["mod_eval"], MO.OUT, rate, 0xFFFF, 0xFFFF if f % 7 == 0 else 0, o1, o2, 0)
            t = (a, b, c)
        else:
            t = (prof.run(MO.SMOOTHER, MO.SRC), prof.run(MODS_PASS, MO.OUT),
                 prof.run(sym["mod_eval"], MO.OUT, rate, 0xFFFF, 0xFFFF if f % 7 == 0 else 0, o1, o2, 0))
        key = sum(t) if prof is None else sum(sum(x[0].values()) for x in t)
        if worst is None or key > worst[0]:
            worst = (key, t, f)
    return worst


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--build", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sweep", action="store_true")
    p.add_argument("--frames", type=int, default=16)
    p.add_argument("--wave", type=int, default=0)
    p.add_argument("--mode", type=int, default=0)
    p.add_argument("--waves", default="0-13")
    a = p.parse_args()
    sym = json.loads((TREE / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    rep = {"sweep": []}
    best = (0, 0, 0)
    if a.sweep:
        lo, hi = (int(x) for x in a.waves.split("-"))
        for wave in range(lo, hi + 1):
            for mode in range(5):
                m = MX.setup(a.build, a.snapshot)
                configure(m, sym, wave, mode, True)
                key, t, _ = frame_total(m, sym, 8)
                rep["sweep"].append({"wave": wave, "mode": mode, "smooth": t[0], "mods": t[1], "eval": t[2]})
                print(f"wave {wave} mode {mode}: smoother {t[0]}, MOD SETUP {t[1]}, eval {t[2]}, total {key}", flush=True)
                if key > best[0]:
                    best = (key, wave, mode)
                del m
                gc.collect()
    else:
        best = (0, a.wave, a.mode)
    for label, routes in (("worst", True), ("no_routes", False)):
        m = MX.setup(a.build, a.snapshot)
        configure(m, sym, best[1], best[2], routes)
        pr = Prof(m, sym)
        key, t, f = frame_total(m, sym, a.frames, pr)
        rep[label] = {"wave": best[1], "mode": best[2], "frame": f, "total": key,
                      "smoother": pr.report(*t[0]), "mods": pr.report(*t[1]), "eval": pr.report(*t[2])}
        print(f"{label}: wave {best[1]} mode {best[2]} frame {f}: total {key}", flush=True)
        for part in ("smoother", "mods", "eval"):
            r = rep[label][part]
            print(f"  {part}: {r['instructions']} instr; reads {r['reads']}; writes {r['writes']}", flush=True)
            for k, v in list(r["by_function"].items())[:12]:
                print(f"     {k:28s} {v}", flush=True)
    pathlib.Path(a.out).write_text(json.dumps(rep, indent=1))
    print("DONE")


if __name__ == "__main__":
    main()
