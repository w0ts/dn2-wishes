"""Where the STOCK Elektron DSP spends its block: a per-PC profile of the unmodified OS image in the
SHARC runner (measuring only: it changes nothing in any build).

Run from a tree root (on gpufarm through the bench namespace, one job at a time):

    bench_ns112.sh TREE python scripts/prof_stock_hotspots.py --job idle --out out/stock/idle.json
    ... --job synth --voices 1,8,16 --out out/stock/synth.json
    ... --job fx --out out/stock/fx.json

Each block is one call of the engine's per-block routine (sw 0x1c2712) on the STOCK section 7, with no
frame clock fed in. For every executed instruction: the pc; for every data access: its region (L1 / L2
0x2xxxxxxx / DDR 0x8xxxxxxx), both counted per pc and per phase (the engine's own call sites: the unpack
and track loop, the voice dispatch, the FX sends, the routing, the output). Cost clock as
docs/dsp-cost.md: cycles = instructions + S (4 L2 + 10 DDR), S = 0.9. The runner does not model the
stalls of DMA waits, instruction fetch from L2 or cache misses: those are not in the numbers.
"""

from __future__ import annotations

import argparse
import bisect
import collections
import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(os.environ.get("DNFW_ROOT", pathlib.Path.cwd()))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import sharc_waverider_m5 as M5                                  # noqa: E402
from dnfw.waverider import dsp                                    # noqa: E402
from dnfw.waverider import frame as FR                            # noqa: E402

P = 666_667
S = float(os.environ.get("DNFW_MEM_SCALE", "0.9"))
m2, m3, m4, fx = M5.m2, M5.m3, M5.m4, M5.fx

# the engine's own call sites (docs/link-research.md section 5, docs/inserts.md): a phase starts at each
PHASE_AT = {0x1C3044: "dispatch", 0x1C3054: "sends", 0x1C305D: "routing", 0x1C307B: "output"}
PHASE0 = "unpack+loop"
STOCK_REVERB_CALL = 0x1C1D11          # docs/fdn8.md: the FX bus's CJUMP to the stock reverb (0xb836bc)

STOCK_MACHINES = {"FM TONE": 0, "WAVETONE": 1, "FM DRUM": 2, "SWARMER": 3}
SEND_CHR, SEND_DEL, SEND_REV = 88, 86, 87      # frame slot indices (docs/fx-master-modulation.md section 5)


class Prof:
    """stands in for Fixups.last: the stepper appends every pc to it before the step"""
    def __init__(self):
        self.on = False
        self.cur = 0
        self.phase = PHASE0
        self.instr = collections.Counter()     # (phase, pc) -> executed instructions
        self.mem = collections.defaultdict(lambda: [0, 0, 0])   # (phase, pc) -> [L1, L2, DDR]
        self.ddr = collections.Counter()       # (phase, address >> 8) -> DDR accesses: where in DDR
        self.l2 = collections.Counter()        # (phase, address >> 8) -> L2 data accesses
        self.ddr_words = collections.Counter()  # (pc, address) -> DDR accesses (word granularity)

    def append(self, pc):
        self.cur = pc
        if self.on:
            self.instr[(self.phase, pc)] += 1


def count_memory(prof):
    """as sharc_waverider_m5._count_memory, but per pc and phase"""
    conc = sys.modules["sharc_core.memory"]._concrete_address

    def region(a):
        a = conc(a)
        if a is None:
            return None, None
        if a >= 0x80000000:
            return 2, a
        return (1 if 0x20000000 <= a < 0x20200000 else 0), a
    orig_r, orig_w = fx._dm_read, fx._dm_write

    def note(address):
        if prof.on:
            g, a = region(address)
            if g is not None:
                prof.mem[(prof.phase, prof.cur)][g] += 1
                if g == 2:
                    prof.ddr[(prof.phase, a >> 8)] += 1
                    prof.ddr_words[(prof.cur, a)] += 1
                elif g == 1:
                    prof.l2[(prof.phase, a >> 8)] += 1

    def rd(state, address, width, *a, **k):
        note(address)
        return orig_r(state, address, width, *a, **k)

    def wr(state, address, width, value):
        note(address)
        return orig_w(state, address, width, value)
    patched = []
    for m in list(sys.modules.values()):
        for name, new, o in (("_dm_read", rd, orig_r), ("_dm_write", wr, orig_w)):
            if getattr(m, name, None) is o:
                patched.append((m, name, o))
                setattr(m, name, new)

    def undo():
        for m, name, o in patched:
            setattr(m, name, o)
    return undo


class Bench:
    def __init__(self, image, digikit):
        self.dk = M5.m1.Digikit(pathlib.Path(digikit))
        fx.bind(str(pathlib.Path(digikit) / "tools"))
        m4.IMAGE = image
        stock = M5.m1.dn2_section7(image)
        self.sound, self.machines = m4.init_sound(image)
        self.stock = M5.Image(self.dk, stock)
        M5.OUT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=M5.OUT) as tmp:
            self.snap, self.m2mach = M5.snapshot_path(self.dk, stock, pathlib.Path(tmp))
        self.init = M5.init_on(self.snap, self.m2mach, self.stock)
        self.prof = Prof()
        self.undo = count_memory(self.prof)
        self._fn = None

    def run(self, frame_fn, nblocks, skip=3, max_steps=40_000_000):
        """nblocks of the stock engine; blocks from SKIP on are profiled. -> per-block totals"""
        state, out, prof = self.init, [], self.prof
        for b in range(nblocks):
            prof.on = b >= skip
            prof.phase = PHASE0

            def mk(ph):
                def h(r):
                    prof.phase = ph
                return h
            hooks = {a: mk(p) for a, p in PHASE_AT.items()}
            r = m4.unpack_call(state, frame_fn(b))
            f = M5.fixups(hooks)
            f.last = prof
            t0 = time.perf_counter()
            n0 = sum(prof.instr.values())
            m0 = [sum(v[g] for v in prof.mem.values()) for g in range(3)]
            res = fx.run(r, max_steps, f)
            ok = res[0] == "halt" and res[1].pc_sw == m4.UNPACK_RETURN
            rec = {"b": b, "ok": ok, "instr": res[2], "wall_s": round(time.perf_counter() - t0, 1)}
            if prof.on:
                rec["profiled"] = sum(prof.instr.values()) - n0
                rec["mem"] = [sum(v[g] for v in prof.mem.values()) - m0[g] for g in range(3)]
                rec["cycles"] = round(rec["instr"] + S * (4 * rec["mem"][1] + 10 * rec["mem"][2]))
            out.append(rec)
            print(f"   block {b}: ok={ok} instr {rec['instr']} mem {rec.get('mem')} cyc {rec.get('cycles')} "
                  f"wall {rec['wall_s']}s", flush=True)
            if not ok:
                rec["halt"] = str(res[1].reason if res[0] == "halt" else res[:2])
                break
            state = r
        return out

    def reset(self):
        self.prof.instr.clear()
        self.prof.mem.clear()
        self.prof.ddr.clear()
        self.prof.ddr_words.clear()
        self.prof.l2.clear()

    def functions(self):
        """sorted function entries (load addresses) of the stock image, and exec -> load"""
        if self._fn is None:
            import sharc_callgraph as CG
            from dnfw.image import bootstream
            regions = bootstream.load_regions(self.stock.stream)
            g = CG.build(regions)
            loaded = [(b, b + len(x)) for b, x in regions]
            self._fn = (CG, sorted(g["entries"]), loaded)
        return self._fn

    def table(self, nsteady):
        """the profile so far -> per phase and per function (exclusive), means per block"""
        CG, entries, loaded = self.functions()
        cache = {}

        def fn_of(pc):
            if pc not in cache:
                la = CG.exec_to_load(pc, loaded)
                i = bisect.bisect_right(entries, la) - 1 if la is not None else -1
                cache[pc] = entries[i] if i >= 0 else -1
            return cache[pc]
        per_fn = collections.defaultdict(lambda: [0, 0, 0, 0])      # fn -> instr, L1, L2, DDR
        per_phase = collections.defaultdict(lambda: [0, 0, 0, 0])
        per_phase_fn = collections.defaultdict(lambda: [0, 0, 0, 0])
        for (ph, pc), n in self.prof.instr.items():
            f = fn_of(pc)
            per_fn[f][0] += n
            per_phase[ph][0] += n
            per_phase_fn[(ph, f)][0] += n
        for (ph, pc), (l1, l2, dd) in self.prof.mem.items():
            f = fn_of(pc)
            for tab in (per_fn[f], per_phase[ph], per_phase_fn[(ph, f)]):
                tab[1] += l1
                tab[2] += l2
                tab[3] += dd

        def row(v):
            ins, l1, l2, dd = (x / nsteady for x in v)
            return {"instr": round(ins), "L1": round(l1), "L2": round(l2), "DDR": round(dd),
                    "est": round(ins + S * (4 * l2 + 10 * dd))}
        fnrows = {f"{f:#x}": row(v) for f, v in per_fn.items()}
        return {"functions": dict(sorted(fnrows.items(), key=lambda kv: -kv[1]["est"])),
                "phases": {k: row(v) for k, v in per_phase.items()},
                "phase_functions": {f"{ph}|{f:#x}": row(v)
                                    for (ph, f), v in sorted(per_phase_fn.items(), key=lambda kv: -kv[1][0])[:400]},
                "ddr_pages": [[ph, f"{pg << 8:#x}", round(n / nsteady)] for (ph, pg), n in
                              sorted(self.prof.ddr.items(), key=lambda kv: -kv[1])[:200]],
                "ddr_words": [[f"{pc:#x}", f"{ad:#x}", n] for (pc, ad), n in
                              sorted(self.prof.ddr_words.items(), key=lambda kv: -kv[1])[:60000]],
                "l2_pages": [[ph, f"{pg << 8:#x}", round(n / nsteady)] for (ph, pg), n in
                             sorted(self.prof.l2.items(), key=lambda kv: -kv[1])[:100]],
                "pcs": [[ph, pc, n] + list(self.prof.mem.get((ph, pc), [0, 0, 0]))
                        for (ph, pc), n in sorted(self.prof.instr.items(), key=lambda kv: -kv[1])[:6000]]}


def synth_frame(B, name, n, *, sends=None, hold=True):
    """n voices (tracks 0..n-1) on stock machine NAME, a note each (C2 up) triggered at block 1 and held;
    SENDS = (chorus, delay, reverb) frame words for every sounding track"""
    typ = STOCK_MACHINES[name]
    sound, machines = B.sound, B.machines

    def fb(b):
        f = M5.base_frame(sound, machines, t0=typ, trigger=False, others={t: typ for t in range(1, n)})
        for t in range(n):
            f.header(FR.NOTE, t, (36 + t) << 8)
            if sends:
                for slot, w in zip((SEND_CHR, SEND_DEL, SEND_REV), sends):
                    f.param(t, slot, w)
            if b == 1:
                f.trigger(t)
        return f.to_bytes()
    return fb


def measure(B, label, fb, blocks, skip, out):
    B.reset()
    recs = B.run(fb, blocks, skip)
    ok = all(r["ok"] for r in recs)
    steady = [r for r in recs if "cycles" in r]
    if not ok or not steady:
        out[label] = {"ok": False, "blocks": recs}
        return
    n = len(steady)
    tab = B.table(n)
    out[label] = {"ok": True, "blocks": recs, "steady": n,
                  "instr": round(sum(r["instr"] for r in steady) / n),
                  "L2": round(sum(r["mem"][1] for r in steady) / n),
                  "DDR": round(sum(r["mem"][2] for r in steady) / n),
                  "cycles": round(sum(r["cycles"] for r in steady) / n),
                  "pct_frame": round(100 * sum(r["cycles"] for r in steady) / n / P, 2), **tab}
    print(f"== {label}: {out[label]['instr']} instr, L2 {out[label]['L2']}, DDR {out[label]['DDR']}, "
          f"{out[label]['cycles']} cyc = {out[label]['pct_frame']} %", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.environ.get("DT2_SYX"), help="Elektron's Digitone_II_OS1.12.syx")
    ap.add_argument("--digikit", default=os.environ.get("DNFW_DIGIKIT_SHARC"))
    ap.add_argument("--job", required=True, choices=("idle", "synth", "fx"))
    ap.add_argument("--machines", default="FM TONE,WAVETONE")
    ap.add_argument("--voices", default="1,8,16")
    ap.add_argument("--blocks", type=int, default=6)
    ap.add_argument("--skip", type=int, default=3)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    B = Bench(pathlib.Path(a.image), a.digikit)
    out = {"image": str(a.image), "S": S}
    try:
        if a.job == "idle":
            measure(B, "idle", lambda b: M5.base_frame(B.sound, B.machines, t0=4, trigger=False).to_bytes(),
                    a.blocks, a.skip, out)
        elif a.job == "synth":
            for name in a.machines.split(","):
                for n in (int(x) for x in a.voices.split(",")):
                    measure(B, f"{name} x{n}", synth_frame(B, name, n), a.blocks, a.skip, out)
        else:
            # the send FX: one FM TONE voice with every send at 0, then each send alone, then all; and the
            # same with 8 voices all sends up (the sends are per track, the FX are global)
            top = 0x7F00
            for label, sends in (("sends 0", (0, 0, 0)), ("chorus send", (top, 0, 0)), ("delay send", (0, top, 0)),
                                 ("reverb send", (0, 0, top)), ("all sends", (top, top, top))):
                measure(B, f"FM TONE x1 {label}", synth_frame(B, "FM TONE", 1, sends=sends), a.blocks, a.skip, out)
            measure(B, "FM TONE x8 all sends", synth_frame(B, "FM TONE", 8, sends=(top, top, top)),
                    a.blocks, a.skip, out)
    finally:
        B.undo()
        p = pathlib.Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out))
        print("written", p)


if __name__ == "__main__":
    main()
