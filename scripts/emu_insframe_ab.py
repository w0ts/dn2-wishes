"""The modulation frame and the inserts' block on two builds, byte for byte (2026-11-21, claude/cf-asm: mx_eval's insert
cells, pack_group / ins_period in assembly).

    emu_insframe_ab.py --a A.syx --syma A_code.json --b B.syx --snapshot S [--frames N] [--seeds 1,2,3]

Run from build B's tree. Both builds from the same worst-case set-up: every voice's three LFOs moving (modprof's
configure), every track 23 routes, about half of them into its inserts' knobs (0xC0 + 7 j + i; the rest into voice
cells and ENV2), all 32 insert records on (every type in turn, random knobs), ENV2 locks on some voices. Each frame:
some tracks' last-played voice moved (sl_lastv, as the note path sets it), a few tracks' trigs with random insert locks
(ins_trig: their groups urgent), now and then a UI change (ins_dirty / ins_hdirty of a track), then the frame (stock's
smoother, MOD SETUP, the evaluator call with mx_eval) and the inserts' block (ins_period). After each frame these must be
the same in A and B: the mirror OUT (16 rows), MOD_RAM, the LFO states, OWNER, the whole matrix state (struct mx_state)
except the insert cells of the voices mx_ins_group does not read this frame (read by nothing: the proof is in the
commit), the insert cells of the two voices it reads, ins_moff, ins_cell, the packet ins_pkt and the inserts' header
state. Prints the instructions a frame of mx_eval and of ins_period (worst and mean) on each build."""
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
import emu_modulation as MO             # noqa: E402
import emu_modprof as MP                # noqa: E402
from emulib import mxlayout             # noqa: E402

AREAS = ((0x800068E4, 34 + 202 * 16), (0x46AF8000, 0x800), (0x44640C18, 1920), (0x80005308, 64))
INS_N, ROW = 14, 101
INS_CELL = 8
INS_SYMS = (("ins_moff", 16 * INS_N * 2), ("ins_cell", 17 * INS_N * 2), ("ins_pkt", 58 * 4), ("ins_rr", 4),
            ("ins_hdirty", 16), ("ins_lk", 16 * INS_N), ("ins_tpg_w", 32))


def records(rng):
    from dnfw.inserts import design as DI
    recs = []
    for i in range(DI.RECORDS):
        ty = 1 + i % 13
        recs.append([ty, rng.randrange(1, 128)] + [rng.randrange(0, 128) for _ in range(6)])
    return recs


def routes(rng, t):
    """23 routes: 15 LFO (src 0..2), 4 ENV1 (3), 4 ENV2 (4); about half into the inserts' knobs"""
    rs = []
    for k in range(23):
        src = k % 3 if k < 15 else (3 if k < 19 else 4)
        if rng.random() < 0.5:
            slot = MX.INS_DEST + rng.randrange(14)
        else:
            slot = rng.choice([25 + 3 * (k % 20), 70 + k % 10])
        rs.append((src, slot, rng.choice([0x0100, 0x2000, 0x3800, 0x4000, 0x4800, 0x6000, 0x7F00, rng.randrange(0x8000)])))
    return rs


class Run:
    def __init__(self, build, snap, sym, seed):
        from dnfw.waverider import pages
        self.sym, self.rng = sym, random.Random(seed)
        m = self.m = MX.setup(build, snap)
        MP.configure(m, sym, self.rng.randrange(14), self.rng.choice([0, 2, 4]), False)
        for t in range(16):
            r = MX.put_routes(m, sym, t, routes(self.rng, t))
            if r:
                raise SystemExit(f"routes on track {t}: {r:#x}")
        m.flush()
        MX.ins_load(m, sym, records(self.rng))
        m.call(sym["mx_poll"])
        m.flush()
        self.mx = pages.MX_RAM
        self.size = m.long(self.mx) & 0xFFFF
        self.e2row = self.mx + mxlayout.of_size(self.size).e2row    # (struct mx_state: emulib/mxlayout.py)
        self.rate = m.long(MO.RATE)
        self.o1, self.o2 = m.alloc(256), m.alloc(256)
        self.lk = m.alloc(16)
        self.cost_mx, self.cost_ins = [], []

    def frame(self, f):
        m, rng, sym = self.m, self.rng, self.sym
        lastv = bytearray(m.read(sym["sl_lastv"], 16))
        for t in range(16):
            if rng.random() < 0.15:
                lastv[t] = rng.choice([0xFF, rng.randrange(16), t])
        m.write(sym["sl_lastv"], bytes(lastv))
        m.flush()
        for t in rng.sample(range(16), rng.choice([0, 0, 1, 2, 4, 16])):
            m.write(self.lk, struct.pack(">7H", *[rng.choice([0xFFFF, rng.randrange(0x8080) & 0x7F7F,
                                                              0xFF00 | rng.randrange(128)]) for _ in range(7)]))
            m.flush()
            m.call(sym["ins_trig"], t, self.lk if rng.random() < 0.9 else 0)
        if rng.random() < 0.05:
            t = rng.randrange(16)
            m.write(sym["ins_hdirty"] + t, b"\x01")
            m.flush()
        m.call(MO.SMOOTHER, MO.SRC)
        m.call(MP.MODS_PASS, MO.OUT)
        g = m.long(sym["ins_rr"]) & 7
        vs = [x for x in (lastv[2 * g], lastv[2 * g + 1]) if x < 16]
        _, c = m.cost(sym["mod_eval"], MO.OUT, self.rate, 0xFFFF, 0xFFFF if f % 7 == 0 else 0, self.o1, self.o2, 0)
        _, n = m.cost(sym["ins_period"])
        self.cost_mx.append(c)
        self.cost_ins.append(n)
        return self.state(vs)

    def state(self, vs):
        m = self.m
        out = [bytes(m.read(at, n)) for at, n in AREAS]
        mx = bytearray(m.read(self.mx, self.size))
        off = self.e2row - self.mx
        keep = {v: bytes(mx[off + 2 * (ROW * v + INS_CELL):off + 2 * (ROW * v + INS_CELL + INS_N)]) for v in vs}
        for v in range(16):
            a = off + 2 * (ROW * v + INS_CELL)
            mx[a:a + 2 * INS_N] = bytes(2 * INS_N)
        out.append(bytes(mx))
        out += [keep[v] for v in sorted(keep)]
        out += [bytes(m.read(self.sym[s], n)) for s, n in INS_SYMS if s in self.sym]
        return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--syma", required=True, help="build A's waverider_code.json")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--frames", type=int, default=200)
    p.add_argument("--seeds", default="1,2,3")
    a = p.parse_args()
    sym = json.loads((TREE / "src/dnfw/mods/waverider_code.json").read_text())["layout"]
    syma = json.loads(pathlib.Path(a.syma).read_text())["layout"]
    bad = 0
    names = [f"area {at:#x}" for at, _ in AREAS] + ["mx_state", "insert cells read"] + [s for s, _ in INS_SYMS]
    for seed in [int(x) for x in a.seeds.split(",")]:
        ra, rb = Run(a.a, a.snapshot, syma, seed), Run(a.b, a.snapshot, sym, seed)
        first = None
        for f in range(a.frames):
            x, y = ra.frame(f), rb.frame(f)
            if x != y and first is None:
                k = next(i for i in range(min(len(x), len(y))) if x[i] != y[i]) if len(x) == len(y) else -1
                first = (f, names[k] if 0 <= k < len(names) else f"part {k} (lengths {len(x)}/{len(y)})")
        for lab, r in (("A", ra), ("B", rb)):
            print(f"seed {seed} {lab}: mod_eval worst {max(r.cost_mx)} mean {sum(r.cost_mx) / len(r.cost_mx):.0f}; "
                  f"ins_period worst {max(r.cost_ins)} mean {sum(r.cost_ins) / len(r.cost_ins):.0f}", flush=True)
        print(f"seed {seed}: {a.frames} frames, " + ("the same" if first is None else f"DIFFER first at frame {first}"),
              flush=True)
        bad += first is not None
        del ra, rb
    print("PASS: the same bytes every frame" if not bad else f"FAIL: {bad} seeds differ")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
